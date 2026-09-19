"""Decode the pocketanim IR back into atlas geometry and per-frame instances.

The inverse of `ir.serialise`. Used by the reference renderer, and by anything
that needs to inspect a .panm without Manim present.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

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


def load(blob: bytes) -> DecodedIR:
    size = struct.calcsize(HEADER)
    magic, version, _flags, fps, n_records, n_atlas, *bounds = struct.unpack(
        HEADER, blob[:size]
    )
    if magic != MAGIC:
        raise ValueError(f"not a pocketanim IR: {magic!r}")

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

    return DecodedIR(fps=fps, shapes=shapes, records=records, cameras=cameras)
