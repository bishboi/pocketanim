"""Decode the pocketanim IR back into atlas geometry and per-frame instances.

The inverse of `ir.serialise`. Used by the reference renderer, and by anything
that needs to inspect a .panm without Manim present.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

from .ir import CAMERA_FLOATS, FLAG_CAMERA, MAGIC, REC_SNAPSHOT, SHADE_IN_3D

HEADER = "<4sHHHII6f"
INSTANCE = "<IIB"  # slot, atlas_id, flags


@dataclass
class DecodedInstance:
    slot: int
    atlas_id: int
    transform: np.ndarray  # 3x4
    fill: tuple[int, int, int, int]
    stroke: tuple[int, int, int, int]
    stroke_width: float
    flags: int = 0
    normal: np.ndarray | None = None


@dataclass
class DecodedIR:
    fps: int
    shapes: list[np.ndarray]          # dequantised canonical geometry
    records: list[tuple[int, list[DecodedInstance]]]
    cameras: list[np.ndarray] | None = None
    # The quantisation box the atlas was encoded against. Kept because a
    # consumer cannot recover it from the points: nothing guarantees some
    # point actually lands on each extreme.
    lo: np.ndarray | None = None
    hi: np.ndarray | None = None
    # The frame's clear colour as (r, g, b). A program carries it on its
    # `scene` line; a sampled container predates it and means black.
    background: tuple[int, int, int] = (0, 0, 0)
    # A program's raster pictures (dsl.interpret's `image` lines) and the folder their PNGs are in.
    images: list = field(default_factory=list)
    image_dir: object = None

    def frame(self, index: int) -> list[DecodedInstance]:
        """Resolve frame `index` to its full ordered instance list.

        Walks back to the preceding snapshot and replays keyframes forward.
        Keyframes carry absolute values, so replay is overwrite, never
        accumulation -- the property that makes seeking exact.
        """
        start = index
        while start > 0 and self.records[start][0] != REC_SNAPSHOT:
            start -= 1

        order: list[int] = []
        state: dict[int, DecodedInstance] = {}
        for kind, instances in self.records[start : index + 1]:
            if kind == REC_SNAPSHOT:
                order = [i.slot for i in instances]
                state = {i.slot: i for i in instances}
            else:
                for inst in instances:
                    if inst.slot not in state:
                        order.append(inst.slot)
                    state[inst.slot] = inst
        return [state[s] for s in order if s in state]


def _varint(blob: bytes, offset: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = blob[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7


def _load_v2(blob: bytes, size: int, flags: int, fps: int, n_records: int, n_atlas: int, bounds) -> DecodedIR:
    """Version 2 (tools/panm_compact.py): delta-coded points, z left out of a flat scene, each instance stored as
    what changed since its slot's previous one. Decodes to exactly what the version 1 it was made from does."""
    lo = np.array(bounds[:3], dtype=np.float64)
    hi = np.array(bounds[3:], dtype=np.float64)
    span = np.where(hi - lo < 1e-9, 1.0, hi - lo)
    offset = size
    cameras: list[np.ndarray] | None = None
    if flags & FLAG_CAMERA:
        raw = np.frombuffer(blob, dtype="<f4", count=n_records * CAMERA_FLOATS, offset=offset)
        offset += n_records * CAMERA_FLOATS * 4
        cameras = [row.astype(np.float64) for row in raw.reshape(n_records, CAMERA_FLOATS)]
    axes = 2 if flags & 2 else 3
    shift = (flags >> 4) & 0xF
    shapes: list[np.ndarray] = []
    elided = bool(flags & 8)

    def point(at: int, prev: list) -> tuple[list, int]:
        for axis in range(axes):
            z, at = _varint(blob, at)
            prev[axis] += (z >> 1) ^ -(z & 1)
        return [prev[0] << shift, prev[1] << shift, prev[2] << shift], at

    for _ in range(n_atlas):
        count, offset = _varint(blob, offset)
        prev = [0, 0, 0]
        if elided and count % 4 == 0 and count:
            cubics = count // 4
            codes_at, offset = offset, offset + (cubics + 3) // 4
            raw = np.zeros((count, 3), dtype=np.float64)
            straight = []
            end = None
            for k in range(cubics):
                code = (blob[codes_at + k // 4] >> (2 * (k % 4))) & 3
                if code & 1:
                    a = end
                else:
                    a, offset = point(offset, prev)
                if code & 2:
                    h1 = h2 = None
                else:
                    h1, offset = point(offset, prev)
                    h2, offset = point(offset, prev)
                b, offset = point(offset, prev)
                raw[4 * k] = a
                raw[4 * k + 3] = b
                if code & 2:
                    straight.append(k)
                else:
                    raw[4 * k + 1], raw[4 * k + 2] = h1, h2
                end = b
            pts = raw / 65535.0 * span + lo
            for k in straight:
                a, b = pts[4 * k], pts[4 * k + 3]
                pts[4 * k + 1] = a + (b - a) / 3.0
                pts[4 * k + 2] = a + 2.0 * (b - a) / 3.0
            shapes.append(pts)
            continue
        raw = np.zeros((count, 3), dtype=np.float64)
        for p in range(count):
            raw[p], offset = point(offset, prev)
        shapes.append(raw / 65535.0 * span + lo)
    records: list[tuple[int, list[DecodedInstance]]] = []
    last: dict[int, list] = {}
    for _ in range(n_records):
        kind = blob[offset]
        offset += 1
        n_inst, offset = _varint(blob, offset)
        instances: list[DecodedInstance] = []
        for _ in range(n_inst):
            slot, offset = _varint(blob, offset)
            mask = blob[offset]
            offset += 1
            f = list(last.get(slot, [0, 0, None, None, None, None, None, None]))
            if mask & 1:
                f[0], offset = _varint(blob, offset)
            if mask & 2:
                f[1] = blob[offset]
                offset += 1
            for bit, index, length in ((2, 2, 18), (3, 3, 12), (4, 4, 4), (5, 5, 4), (6, 6, 2)):
                if mask & (1 << bit):
                    f[index] = blob[offset:offset + length]
                    offset += length
            if mask & 128:
                f[7] = blob[offset:offset + 6]
                offset += 6
            last[slot] = f
            linear = np.frombuffer(f[2], dtype="<f2", count=9).reshape(3, 3)
            translation = np.frombuffer(f[3], dtype="<f4", count=3)
            (width_raw,) = struct.unpack("<H", f[6])
            normal = np.frombuffer(f[7], dtype="<f2", count=3).astype(np.float64) \
                if f[1] & SHADE_IN_3D and f[7] is not None else None
            transform = np.hstack([linear.astype(np.float64), translation.astype(np.float64).reshape(3, 1)])
            instances.append(DecodedInstance(slot, f[0], transform, tuple(f[4]), tuple(f[5]), width_raw / 64.0,
                                             f[1], normal))
        records.append((kind, instances))
    return DecodedIR(fps=fps, shapes=shapes, records=records, cameras=cameras, lo=lo, hi=hi)


def load(blob: bytes) -> DecodedIR:
    size = struct.calcsize(HEADER)
    magic, version, _flags, fps, n_records, n_atlas, *bounds = struct.unpack(
        HEADER, blob[:size]
    )
    if magic != MAGIC:
        raise ValueError(f"not a pocketanim IR: {magic!r}")
    if version == 2:
        return _load_v2(blob, size, _flags, fps, n_records, n_atlas, bounds)

    lo = np.array(bounds[:3], dtype=np.float64)
    hi = np.array(bounds[3:], dtype=np.float64)
    span = np.where(hi - lo < 1e-9, 1.0, hi - lo)

    offset = size

    cameras: list[np.ndarray] | None = None
    if _flags & FLAG_CAMERA:
        raw = np.frombuffer(
            blob, dtype="<f4", count=n_records * CAMERA_FLOATS, offset=offset
        )
        offset += n_records * CAMERA_FLOATS * 4
        cameras = [row.astype(np.float64) for row in raw.reshape(n_records, CAMERA_FLOATS)]

    shapes: list[np.ndarray] = []
    for _ in range(n_atlas):
        (count,) = struct.unpack_from("<I", blob, offset)
        offset += 4
        raw = np.frombuffer(blob, dtype="<u2", count=count * 3, offset=offset)
        offset += count * 3 * 2
        shapes.append(raw.reshape(count, 3).astype(np.float64) / 65535.0 * span + lo)

    records: list[tuple[int, list[DecodedInstance]]] = []
    for _ in range(n_records):
        kind, n_inst = struct.unpack_from("<BI", blob, offset)
        offset += 5
        instances: list[DecodedInstance] = []
        for _ in range(n_inst):
            slot, atlas_id, inst_flags = struct.unpack_from(INSTANCE, blob, offset)
            offset += 9
            linear = np.frombuffer(blob, dtype="<f2", count=9, offset=offset).reshape(3, 3)
            offset += 18
            translation = np.frombuffer(blob, dtype="<f4", count=3, offset=offset)
            offset += 12
            fill = tuple(blob[offset : offset + 4])
            stroke = tuple(blob[offset + 4 : offset + 8])
            offset += 8
            (width_raw,) = struct.unpack_from("<H", blob, offset)
            offset += 2
            normal = None
            if inst_flags & SHADE_IN_3D:
                normal = np.frombuffer(blob, dtype="<f2", count=3, offset=offset).astype(np.float64)
                offset += 6

            transform = np.hstack(
                [linear.astype(np.float64), translation.astype(np.float64).reshape(3, 1)]
            )
            instances.append(
                DecodedInstance(slot, atlas_id, transform, fill, stroke, width_raw / 64.0, inst_flags, normal)
            )
        records.append((kind, instances))

    return DecodedIR(fps=fps, shapes=shapes, records=records, cameras=cameras, lo=lo, hi=hi)
