"""Verify the IR round-trips: Manim's frames vs the reference renderer's.

Exports a scene while capturing Manim's own rendered frames, then decodes the
IR and re-renders the same frame indices, and reports per-pixel agreement.

This is what turns "perceptually identical" from an aspiration into a number,
and it is the oracle the Android renderer should later be tested against.

Usage:
    python -m tools.verify_fidelity <scene_file.py> <SceneClass> [--every N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exporter.decode import load
from exporter.export_scene import Exporter
from exporter.ir import serialise
from exporter.reference_render import render_frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_file")
    ap.add_argument("scene_class")
    ap.add_argument("--every", type=int, default=15, help="sample every Nth frame")
    ap.add_argument("--dump", help="directory to write comparison PNGs into")
    args = ap.parse_args()

    from manim import Scene, tempconfig
    from manim.renderer.cairo_renderer import CairoRenderer

    exporter = Exporter()
    reference: dict[int, np.ndarray] = {}
    original_update = CairoRenderer.update_frame
    original_play = Scene.play
    counter = {"n": -1}

    def patched_update(self, scene, *a, **kw):
        exporter.capture(scene)
        result = original_update(self, scene, *a, **kw)
        counter["n"] += 1
        if counter["n"] % args.every == 0:
            frame = self.get_frame()
            reference[counter["n"]] = np.asarray(frame)[:, :, :3].copy()
        return result

    def patched_play(self, *a, **kw):
        exporter.force_snapshot = True
        return original_play(self, *a, **kw)

    CairoRenderer.update_frame = patched_update
    Scene.play = patched_play

    path = Path(args.scene_file).resolve()
    sys.path.insert(0, str(path.parent))
    module = __import__(path.stem)
    scene_cls = getattr(module, args.scene_class)

    try:
        with tempconfig(
            {
                "quality": "medium_quality",
                "write_to_movie": False,
                "verbosity": "ERROR",
                "progress_bar": "none",
            }
        ):
            scene_cls().render()
    finally:
        CairoRenderer.update_frame = original_update
        Scene.play = original_play

    ir = load(serialise(exporter.atlas, exporter.records, fps=30,
                        cameras=exporter.cameras or None))

    rows = []
    for index, expected in sorted(reference.items()):
        if index >= len(ir.records):
            continue
        actual = render_frame(ir, index, expected.shape[1], expected.shape[0])
        diff = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
        mae = float(diff.mean())
        bad = float((diff.max(axis=2) > 24).mean())
        ink = float((expected.max(axis=2) > 24).mean())
        rows.append((index, mae, bad, ink))

        if args.dump:
            out = Path(args.dump)
            out.mkdir(parents=True, exist_ok=True)
            try:
                from PIL import Image

                Image.fromarray(
                    np.concatenate([expected, actual], axis=1)
                ).save(out / f"{args.scene_class}_{index:05d}.png")
            except ImportError:
                pass

    if not rows:
        print("no frames compared")
        return

    print(f"{'frame':>7} {'MAE':>8} {'%pixels off':>12} {'%ink':>8}")
    for index, mae, bad, ink in rows:
        print(f"{index:>7} {mae:>8.2f} {bad * 100:>11.2f}% {ink * 100:>7.2f}%")

    mean_mae = sum(r[1] for r in rows) / len(rows)
    mean_bad = sum(r[2] for r in rows) / len(rows)
    print(f"\n{args.scene_class}: mean MAE {mean_mae:.2f}, mean pixels off {mean_bad * 100:.2f}%")


if __name__ == "__main__":
    main()
