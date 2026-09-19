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
    renderer_state = {"renderer": None, "fps": 30}

    in_static = {"depth": 0}
    original_static = CairoRenderer.save_static_frame_data

    def patched_static(self, scene, static_mobjects):
        in_static["depth"] += 1
        try:
            return original_static(self, scene, static_mobjects)
        finally:
            in_static["depth"] -= 1

    def patched_update(self, scene, *a, **kw):
        # Manim renders the static layer through update_frame too, to cache it.
        # That is a partial render -- only the static mobjects, and no frame is
        # written for it -- so it must not be counted as a frame. Both call
        # sites pass a mobject list, so the static one is detected by wrapping
        # save_static_frame_data rather than by inspecting arguments.
        if in_static["depth"]:
            return original_update(self, scene, *a, **kw)

        # Index by playback frame, not by call: update_frame fires twice at
        # every animation boundary and both renders become the same output
        # frame, so counting calls drifted one frame per animation.
        renderer_state["renderer"] = self
        renderer_state["fps"] = int(getattr(self.camera, "frame_rate", 30) or 30)
        index = round(float(self.time) * renderer_state["fps"])
        exporter.capture(scene, index)
        result = original_update(self, scene, *a, **kw)
        if index % args.every == 0:
            frame = self.get_frame()
            reference[index] = np.asarray(frame)[:, :, :3].copy()
        return result

    def patched_play(self, *a, **kw):
        exporter.force_snapshot = True
        return original_play(self, *a, **kw)

    CairoRenderer.update_frame = patched_update
    CairoRenderer.save_static_frame_data = patched_static
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
        CairoRenderer.save_static_frame_data = original_static
        Scene.play = original_play

    renderer = renderer_state["renderer"]
    if renderer is not None:
        exporter.pad_to(
            round(float(renderer.time) * renderer_state["fps"]),
            exporter.cameras[-1] if exporter.cameras else None,
        )

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
