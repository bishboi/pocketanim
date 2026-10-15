"""The .panm container, version 2: the same scene in fewer bytes, for the phone library.

Version 1 (exporter/ir.py) stores every point as three uint16 (x, y, z) and every instance of every frame in full
(49 bytes: slot, atlas id, flags, a float16 3x3, a float32 translation, two colours, a width). Version 2 keeps
the same instances bit for bit and the same points to within a quarter of a pixel at 1080p (bit for bit with
lossless=True), and stores them leaner:

    header      as v1 (<4sHHHII6f), version 2; flag 2 (FLAT) when every point's z is the same (a 2D scene);
                flags bits 4-7: how many low bits of each coordinate were rounded away (POINT_STEP: a quarter of
                a pixel at 1080p; 0 for a lossless file and for a 3D scene)
    cameras     as v1, when flag 1 (CAMERA)
    atlas       per shape: varint point count, then per point and axis (x, y, and z unless FLAT) the zigzag varint
                of its quantised value minus the previous point's (the first against 0): neighbouring points of an
                outline are close, so most deltas take one byte instead of two
    records     per record: u8 kind, varint instance count; per instance: varint slot, u8 mask of the fields that
                differ from that slot's previous instance in the file (any earlier record), then those fields, in
                order: 1 varint atlas id, 2 u8 flags, 4 float16[9] linear, 8 float32[3] translation, 16 rgba fill,
                32 rgba stroke, 64 u16 width (x64), 128 float16[3] normal. A slot seen for the first time has all its
                fields. A part that only moves costs its translation, not the whole instance.

Usage (a check, not a step: tools/build_library.py packs assets with it):
    python -m tools.panm_compact <asset.panm> ...     # sizes before and after, and that both decode alike
"""

from __future__ import annotations

import struct
import sys

HEADER = "<4sHHHII6f"
FLAG_CAMERA = 1
FLAG_FLAT = 2
# Points left out where the reader can make them (flat scenes): a cubic's start that is the previous cubic's end,
# and the two handles of a straight segment (at a third and two thirds of the way). Per shape whose point count is
# a multiple of four, before its deltas: two bits a cubic, four cubics a byte -- bit 1 start left out, bit 2
# handles left out.
FLAG_ELIDED = 8
CAMERA_FLOATS = 17
SHADE_IN_3D = 1


def _varint(value: int, out: bytearray) -> None:
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return


def _zigzag(value: int) -> int:
    return (value << 1) ^ (value >> 63)


# How fine a point needs to be: a quarter of a pixel on a 1080p screen (the frame is 14.22 units across 1920
# pixels), still under half a pixel with the stage pushed in 1.8x. Points finer than that are rounded to it.
POINT_STEP = 0.0018


def _shift_for(span: float) -> int:
    """How many low bits of a uint16 coordinate over `span` units are finer than POINT_STEP."""
    step = span / 65535.0 if span > 1e-9 else 1.0
    shift = 0
    while shift < 6 and step * (1 << (shift + 1)) <= POINT_STEP:
        shift += 1
    return shift


def _elide(points: list) -> tuple[list, list]:
    """Per cubic of a shape (four points each): its code (bit 1: its start is the previous cubic's end; bit 2: it
    is straight, its handles at a third and two thirds within a step) and the points still to be written."""
    codes, kept = [], []
    end = None
    for k in range(len(points) // 4):
        a, h1, h2, b = points[4 * k:4 * k + 4]
        code = 0
        if a == end:
            code |= 1
        if all(abs(h1[i] - (a[i] + (b[i] - a[i]) / 3)) <= 1 and abs(h2[i] - (a[i] + 2 * (b[i] - a[i]) / 3)) <= 1
               for i in range(len(a))):
            code |= 2
        codes.append(code)
        if not code & 1:
            kept.append(a)
        if not code & 2:
            kept += [h1, h2]
        kept.append(b)
        end = b
    return codes, kept


def encode(blob: bytes, lossless: bool = False) -> bytes:
    """A version 1 container as version 2. A container that is not version 1 is returned as it is. Unless
    `lossless`, points are rounded to POINT_STEP (flags bits 4-7 hold how many low bits were dropped)."""
    size = struct.calcsize(HEADER)
    magic, version, flags, fps, n_records, n_atlas, *bounds = struct.unpack(HEADER, blob[:size])
    if version != 1:
        return blob
    offset = size
    cameras = b""
    if flags & FLAG_CAMERA:
        cameras = blob[offset:offset + n_records * CAMERA_FLOATS * 4]
        offset += len(cameras)

    shapes = []
    for _ in range(n_atlas):
        (count,) = struct.unpack_from("<I", blob, offset)
        offset += 4
        shapes.append(struct.unpack_from(f"<{count * 3}H", blob, offset))
        offset += count * 6
    flat_z = {pts[k] for pts in shapes for k in range(2, len(pts), 3)}
    flat = len(flat_z) <= 1 and (not flat_z or flat_z == {0})
    # One rounding for all axes, from the widest: a scene is drawn at one scale.
    shift = 0 if lossless or (flags & FLAG_CAMERA) else _shift_for(max(bounds[3] - bounds[0], bounds[4] - bounds[1]))

    elide = flat and not lossless
    out = bytearray(struct.pack(HEADER, magic, 2, flags | (FLAG_FLAT if flat else 0) | (FLAG_ELIDED if elide else 0)
                                | (shift << 4), fps, n_records, n_atlas, *bounds))
    out += cameras
    axes = 2 if flat else 3
    half = (1 << shift) >> 1
    top = 65535 >> shift
    for pts in shapes:
        count = len(pts) // 3
        _varint(count, out)
        points = [tuple(min((pts[p * 3 + axis] + half) >> shift, top) for axis in range(axes)) for p in range(count)]
        if elide and count % 4 == 0:
            codes, kept = _elide(points)
            for i in range(0, len(codes), 4):
                byte = 0
                for j, code in enumerate(codes[i:i + 4]):
                    byte |= code << (2 * j)
                out.append(byte)
            points = kept
        prev = [0, 0, 0]
        for point in points:
            for axis in range(axes):
                _varint(_zigzag(point[axis] - prev[axis]), out)
                prev[axis] = point[axis]

    last: dict[int, tuple] = {}
    for _ in range(n_records):
        kind, n_inst = struct.unpack_from("<BI", blob, offset)
        offset += 5
        out.append(kind)
        _varint(n_inst, out)
        for _ in range(n_inst):
            slot, atlas_id, inst_flags = struct.unpack_from("<IIB", blob, offset)
            offset += 9
            linear = blob[offset:offset + 18]
            offset += 18
            translation = blob[offset:offset + 12]
            offset += 12
            fill = blob[offset:offset + 4]
            stroke = blob[offset + 4:offset + 8]
            offset += 8
            width = blob[offset:offset + 2]
            offset += 2
            normal = None
            if inst_flags & SHADE_IN_3D:
                normal = blob[offset:offset + 6]
                offset += 6
            fields = (atlas_id, inst_flags, linear, translation, fill, stroke, width, normal)
            before = last.get(slot)
            mask = 0
            for bit, (now, was) in enumerate(zip(fields, before or (None,) * 8)):
                if bit == 7:
                    if now is not None and (before is None or now != was):
                        mask |= 1 << bit
                elif before is None or now != was:
                    mask |= 1 << bit
            _varint(slot, out)
            out.append(mask)
            if mask & 1:
                _varint(atlas_id, out)
            if mask & 2:
                out.append(inst_flags)
            for bit, data in ((2, linear), (3, translation), (4, fill), (5, stroke), (6, width)):
                if mask & (1 << bit):
                    out += data
            if mask & 128:
                out += normal
            last[slot] = fields
    if offset != len(blob):
        raise ValueError(f"version 1 container has {len(blob) - offset} bytes past its records")
    return bytes(out)


def main(argv: list[str]) -> int:
    sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])
    import numpy as np

    from exporter.decode import load

    total_v1 = total_v2 = 0
    for path in argv:
        v1 = open(path, "rb").read()
        v2 = encode(v1)
        a, b = load(v1), load(encode(v1, lossless=True))
        worst = max((float(np.abs(x - y).max()) for x, y in zip(a.shapes, load(v2).shapes) if len(x)), default=0.0)
        if worst > 2 * POINT_STEP:
            print(f"{path}: rounding moved a point {worst:.4f} units, more than {2 * POINT_STEP}")
            return 1
        same = len(a.shapes) == len(b.shapes) and all(np.array_equal(x, y) for x, y in zip(a.shapes, b.shapes)) \
            and len(a.records) == len(b.records)
        for (ka, ia), (kb, ib) in zip(a.records, b.records):
            same = same and ka == kb and len(ia) == len(ib) and all(
                p.slot == q.slot and p.atlas_id == q.atlas_id and p.flags == q.flags and p.fill == q.fill
                and p.stroke == q.stroke and p.stroke_width == q.stroke_width
                and np.array_equal(p.transform, q.transform)
                and ((p.normal is None and q.normal is None) or np.array_equal(p.normal, q.normal))
                for p, q in zip(ia, ib))
        total_v1 += len(v1)
        total_v2 += len(v2)
        print(f"{path}: {len(v1):,} -> {len(v2):,} B  {'same' if same else 'DIFFERENT'}")
        if not same:
            return 1
    print(f"total {total_v1:,} -> {total_v2:,} B ({100 * total_v2 / max(total_v1, 1):.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
