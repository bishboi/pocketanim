"""Compare the shipping player's renderer against the Cairo oracle.

The player's core is platform-neutral: the only thing it asks of a platform is
a PathSink. Android backs that with Skia; the desktop harness backs it with
Java2D. So the *same Kotlin* that runs on the phone can be run here and checked
against exporter/reference_render.py, which is the oracle the spec names.

What this proves: the decode, the transforms, the camera projection, the depth
sort, the shading and the subpath splitting agree with the format's definition.

What it cannot prove: that Skia rasterises like Cairo. Nothing run on this
machine can. Antialiasing differs between Cairo, Java2D and Skia, so edge
pixels always disagree a little -- the number to watch is whether the
disagreement stays on edges or covers areas.

Usage:
    python -m tools.verify_player <scene.panm> [--every N] [--dump DIR]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exporter.decode import load
from exporter.reference_render import render_frame


def load_scene(path: Path):
    """Either tier. A .panim is a program the reference interpreter expands;
    a .panm is already sampled frames. The player accepts both too, which is
    the point -- past the interpreter nothing can tell the tiers apart."""
    if path.suffix == ".panim":
        from dsl.interpret import load_program

        return load_program(str(path))
    return load(path.read_bytes())

CLASSES = Path("player/build/classes")


def kotlin_render(scene: Path, frame: int, out: Path) -> np.ndarray:
    subprocess.run(
        ["java", "-cp", f"{CLASSES / 'core'}:{CLASSES / 'desktop'}:{CLASSES / 'kotlin-stdlib.jar'}",
         "com.pocketanim.desktop.VerifyKt", str(scene), "render", str(frame), str(out)],
        check=True, capture_output=True, text=True,
    )
    from PIL import Image

    return np.asarray(Image.open(out).convert("RGB"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--every", type=int, default=30)
    ap.add_argument("--dump", help="directory for side-by-side PNGs")
    args = ap.parse_args()

    if not (CLASSES / "core").exists():
        print("player not built -- run player/build.sh first")
        return 2

    path = Path(args.scene)
    ir = load_scene(path)
    scratch = Path(args.dump) if args.dump else Path("/tmp/panim-render")
    scratch.mkdir(parents=True, exist_ok=True)

    print(f"{'frame':>7} {'MAE':>8} {'%pixels off':>12} {'%ink':>8}")
    rows = []
    for index in range(0, len(ir.records), args.every):
        expected = render_frame(ir, index, 1280, 720)
        actual = kotlin_render(path, index, scratch / f"kt_{index:05d}.png")

        diff = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
        mae = float(diff.mean())
        bad = float((diff.max(axis=2) > 24).mean())
        ink = float((expected.max(axis=2) > 24).mean())
        rows.append((mae, bad))
        print(f"{index:>7} {mae:>8.2f} {bad * 100:>11.2f}% {ink * 100:>7.2f}%")

        if args.dump:
            from PIL import Image

            Image.fromarray(np.concatenate([expected, actual], axis=1)).save(
                scratch / f"cmp_{index:05d}.png"
            )

    if not rows:
        print("no frames compared")
        return 1

    print(
        f"\nmean MAE {sum(r[0] for r in rows) / len(rows):.2f}, "
        f"mean pixels off {sum(r[1] for r in rows) / len(rows) * 100:.2f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
