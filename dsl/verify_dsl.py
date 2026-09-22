"""Compare a DSL program's output against Manim's own frames.

The honest test of the program-shipping claim: the DSL side never touches
Manim -- it generates geometry and the camera track itself -- so agreement
means an independent runtime really can reproduce the scene.

Usage:
    python -m dsl.verify_dsl dsl/surface_orbit.panim corpus/scenes/07_surface_orbit.py SurfaceOrbit
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsl.interpret import load_program
from exporter.reference_render import render_frame

# Below this much ink, a frame is too nearly empty for "of ink" to mean
# anything -- a few dozen pixels, where antialiasing alone moves the ratio by
# tens of points. About 200 pixels at 480p.
INK_FLOOR = 0.0005


def main():
    program_path, scene_file, scene_class = sys.argv[1:4]
    every = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    dump = sys.argv[5] if len(sys.argv) > 5 else None

    ir = load_program(program_path)

    from manim import tempconfig
    from manim.renderer.cairo_renderer import CairoRenderer

    reference: dict[int, np.ndarray] = {}
    original = CairoRenderer.update_frame

    in_static = {"depth": 0}
    original_static = CairoRenderer.save_static_frame_data

    def patched_static(self, scene, static_mobjects):
        in_static["depth"] += 1
        try:
            return original_static(self, scene, static_mobjects)
        finally:
            in_static["depth"] -= 1

    def patched(self, scene, *a, **kw):
        # Manim renders the static layer through update_frame too, to cache it.
        # That is a partial render -- only the static mobjects, and no frame is
        # written for it -- so it must not be counted as a frame. Both call
        # sites pass a mobject list, so the static one is detected by wrapping
        # save_static_frame_data rather than by inspecting arguments.
        if in_static["depth"]:
            return original(self, scene, *a, **kw)

        # Index by playback time, not by call count. `update_frame` fires twice
        # at every animation boundary -- both renders land on the same output
        # frame -- so counting calls drifted one frame per animation and read
        # as a camera error rather than as a misalignment. `renderer.time` is
        # how many frames have actually been written, which is the frame this
        # render is about to become.
        index = round(float(self.time) * ir.fps)
        result = original(self, scene, *a, **kw)
        if index % every == 0:
            reference[index] = np.asarray(self.get_frame())[:, :, :3].copy()
        return result

    CairoRenderer.update_frame = patched
    CairoRenderer.save_static_frame_data = patched_static
    path = Path(scene_file).resolve()
    sys.path.insert(0, str(path.parent))
    module = __import__(path.stem)
    try:
        with tempconfig(
            {
                "quality": "medium_quality",
                "write_to_movie": False,
                "verbosity": "ERROR",
                "progress_bar": "none",
            }
        ):
            getattr(module, scene_class)().render()
    finally:
        CairoRenderer.update_frame = original
        CairoRenderer.save_static_frame_data = original_static

    print(f"program bytes       {Path(program_path).stat().st_size}")
    print(f"manim frames        {max(reference) + 1} (sampled every {every})")
    print(f"dsl frames          {len(ir.records)}")
    print()
    # "of ink" is the column that matters, and it took a real defect to learn
    # that. A scene of thin outlines on black is under 1% ink, so drawing every
    # shape in the wrong place moves well under 1% of the *frame* and sails
    # through a gate set on that. Measured against the ink instead, the same
    # frame reads 114% -- more than the whole drawing moved. Sparse line art
    # needs a denominator that knows how sparse it is.
    print(f"{'frame':>7} {'MAE':>8} {'%pixels off':>12} {'%ink':>8} {'of ink':>9}")

    rows = []
    thin = 0
    for index, expected in sorted(reference.items()):
        if index >= len(ir.records):
            continue
        actual = render_frame(ir, index, expected.shape[1], expected.shape[0])
        diff = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
        mae = float(diff.mean())
        bad = float((diff.max(axis=2) > 24).mean())
        ink = float((expected.max(axis=2) > 24).mean())
        # A blank frame has no ink and cannot disagree about any of it.
        relative = bad / ink if ink > 0 else 0.0
        # The first frames of a reveal hold a few dozen lit pixels, and a ratio
        # over a denominator that small is noise: one frame of ConcurrentPlay
        # read 106% of its ink while differing on 0.00% of the frame, which is
        # antialiasing on a stroke a few pixels long. Such a frame is printed
        # with its ratio marked and left out of the worst-frame summary, so the
        # headline number stays a statement about drawings that exist.
        enough = ink >= INK_FLOOR
        rows.append((mae, bad, relative, enough))
        if not enough:
            thin += 1
        print(
            f"{index:>7} {mae:>8.2f} {bad * 100:>11.2f}% {ink * 100:>7.2f}% "
            f"{relative * 100:>8.1f}%{'' if enough else ' *'}"
        )

        if dump:
            out = Path(dump)
            out.mkdir(parents=True, exist_ok=True)
            from PIL import Image

            Image.fromarray(np.concatenate([expected, actual], axis=1)).save(
                out / f"dsl_{index:05d}.png"
            )

    if rows:
        scored = [r for r in rows if r[3]] or rows
        worst = max(r[2] for r in scored)
        note = f" ({thin} too thin to score, marked *)" if thin else ""
        print(
            f"\nmean MAE {sum(r[0] for r in rows) / len(rows):.2f}, "
            f"mean pixels off {sum(r[1] for r in rows) / len(rows) * 100:.2f}%, "
            f"worst frame {worst * 100:.1f}% of its ink{note}"
        )


if __name__ == "__main__":
    main()
