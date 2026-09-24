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


def build(build_dir: Path, scene_class: str) -> dict:
    import os

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

        frames = []
        for _, instances in ir.records:
            flat = []
            for inst in instances:
                t = inst.transform
                flat.append([
                    inst.atlas_id,
                    # 2D affine: the third row and column only matter in 3D.
                    round(float(t[0][0]), 5), round(float(t[0][1]), 5),
                    round(float(t[1][0]), 5), round(float(t[1][1]), 5),
                    round(float(t[0][3]), 5), round(float(t[1][3]), 5),
                    list(int(c) for c in inst.fill),
                    list(int(c) for c in inst.stroke),
                    round(float(inst.stroke_width), 3),
                ])
            frames.append(flat)

        return {"mode": "2d", "fps": ir.fps, "shapes": shapes, "frames": frames}
    finally:
        os.chdir(previous)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: scene_ir.py <build_dir> <SceneClass>", file=sys.stderr)
        return 2
    try:
        print(json.dumps(build(Path(sys.argv[1]), sys.argv[2]), separators=(",", ":")))
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
