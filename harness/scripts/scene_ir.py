"""Expand a built program into the geometry a browser can draw, as JSON.

The harness previews a scene by playing it, not by asking a server for a
picture per frame. So the interpretation -- Manim's animation semantics, which
took this repo a corpus and a fidelity harness to get right -- stays in Python,
and only the rasterising crosses to the browser. That split is the existing
`PathSink` seam: whoever draws needs paths and colours, nothing more.

What comes back:

    fps      the program's frame rate
    mode     "2d" or "3d"
    shapes   the atlas, each a flat [x, y, x, y, ...] of 2D anchor/handle
             points, four points to a cubic, exactly as Manim stores them
    frames   per frame, a flat list of instance records:
             [shapeIndex, a,b,c,d,e,f, fillRGBA, strokeRGBA, strokeWidth]
             where a..f is the 2D affine already composed

A 3D program returns `mode: "3d"` and no geometry: projection, depth sorting
and shading would all have to be reimplemented in the browser to draw it
faithfully, and a wrong preview is worse than an honest fallback.

Usage:
    python harness/scripts/scene_ir.py <build_dir> <SceneClass>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _from_container(path: Path) -> dict:
    """The sampled container, in the same shape a program expands to.

    Records in the file are snapshots and keyframes. The preview wants one
    picture per frame, which is what ``frame`` reconstructs.
    """
    from exporter.decode import load

    ir = load(path.read_bytes())
    if ir.cameras:
        return {"mode": "3d", "fps": ir.fps, "frames": len(ir.records)}

    shapes = [
        [round(float(v), 4) for point in shape for v in point[:2]]
        for shape in ir.shapes
    ]
    pieces = []
    piece_of = {}
    runs = []
    previous_signature = None
    for index in range(len(ir.records)):
        flat = _flatten(ir.frame(index))
        signature = tuple(
            (row[0], *row[1:7], tuple(row[7]), tuple(row[8]), row[9]) for row in flat
        )
        if signature == previous_signature:
            runs[-1][0] += 1
            continue
        previous_signature = signature
        key = signature
        piece = piece_of.get(key)
        if piece is None:
            piece = len(pieces)
            piece_of[key] = piece
            pieces.append(flat)
        runs.append([1, [piece]])
    return {
        "mode": "2d",
        "fps": ir.fps,
        "shapes": shapes,
        "pieces": pieces,
        "runs": runs,
        "frames": len(ir.records),
    }


def _flatten(instances) -> list:
    flat = []
    for inst in instances:
        t = inst.transform
        flat.append([
            inst.atlas_id,
            round(float(t[0][0]), 5), round(float(t[0][1]), 5),
            round(float(t[1][0]), 5), round(float(t[1][1]), 5),
            round(float(t[0][3]), 5), round(float(t[1][3]), 5),
            list(int(c) for c in inst.fill),
            list(int(c) for c in inst.stroke),
            round(float(inst.stroke_width), 3),
        ])
    return flat


def build(build_dir: Path, scene_class: str) -> dict:
    import os

    container = build_dir / f"{scene_class}.panm"
    if container.is_file():
        return _from_container(container)

    previous = Path.cwd()
    os.chdir(build_dir)
    try:
        from dsl.interpret import load_program

        ir = load_program(f"dsl/generated/{scene_class}.panim")

        if ir.cameras:
            return {"mode": "3d", "fps": ir.fps, "frames": len(ir.records)}

        # The atlas is shared across every frame, which is the whole reason a
        # program is small: ship it once.
        shapes = [
            [round(float(v), 4) for point in shape for v in point[:2]]
            for shape in ir.shapes
        ]

        def flatten(group):
            return _flatten(group)

        # Each object is drawn once and reused. A run is how many frames that
        # combination stays on screen, which is the whole wait in a lecture.
        pieces = []
        piece_of = {}
        runs = []
        total = 0
        previous_signature = None
        for _, instances in ir.records:
            total += 1
            groups = getattr(instances, "groups", None)
            if not groups:
                groups = (instances,)
            signature = tuple(id(group) for group in groups)
            if signature == previous_signature:
                runs[-1][0] += 1
                continue
            previous_signature = signature
            indexes = []
            for group in groups:
                key = id(group)
                index = piece_of.get(key)
                if index is None:
                    index = len(pieces)
                    piece_of[key] = index
                    pieces.append(flatten(group))
                indexes.append(index)
            runs.append([1, indexes])

        return {
            "mode": "2d",
            "fps": ir.fps,
            "shapes": shapes,
            "pieces": pieces,
            "runs": runs,
            "frames": total,
        }
    finally:
        os.chdir(previous)


# Past this, the preview renders a frame at a time. A lecture's reused pieces
# land well under it; the old per-frame copy of the whole scene did not.
MAX_GEOMETRY_BYTES = 256 * 1024 * 1024


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: scene_ir.py <build_dir> <SceneClass>", file=sys.stderr)
        return 2
    build_dir = Path(sys.argv[1])
    try:
        payload = build(build_dir, sys.argv[2])
        count = payload["frames"] if isinstance(payload["frames"], int) else len(payload.get("runs", []))
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        summary = {"mode": payload["mode"], "fps": payload["fps"], "frames": count, "bytes": len(encoded)}
        if payload["mode"] == "2d" and len(encoded) <= MAX_GEOMETRY_BYTES:
            (build_dir / "scene_ir.json").write_bytes(encoded)
            summary["geometry"] = True
        else:
            summary["geometry"] = False
            if payload["mode"] == "2d":
                summary["mode"] = "frames"
        print(json.dumps(summary))
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
