"""Warm what the first build of a lecture would otherwise pay for, once, when the server starts.

The web app runs this in the background as it starts (app/instrumentation.ts). It imports Manim and the lecture
engine (their bytecode, and the font lookup Pango does on first use), runs LaTeX for the formulas most lectures
have, and lays out a line in each style's fonts, into the cache every build shares (export_scene.manim_cache). The
first lecture's build then starts where a second one would. Nothing here is needed: a failure is printed and
ignored.

    python harness/scripts/warm_caches.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "harness" / "lecture"))
sys.path.insert(0, str(HERE))

# Formulas nearly every STEM lecture writes, and the pieces of the rest (a fraction, a power, a root, Greek).
FORMULAS = [
    r"x", r"y", r"=", r"+", r"-", r"\times", r"\div", r"x^2", r"\frac{a}{b}", r"\sqrt{x}", r"\pi", r"\theta",
    r"\alpha", r"\Delta", r"\sum", r"F = ma", r"v = u + at", r"E = mc^2", r"a^2 + b^2 = c^2", r"y = mx + c",
]


def main() -> int:
    started = time.time()
    os.environ.setdefault("PANIM_VOICE", "silent")
    from export_scene import manim_cache, share_caches

    share_caches()
    import nolatex

    nolatex.install()
    from manim import MathTex, Text, config, tempconfig

    import pocket_lecture

    fonts = sorted({theme[key] for theme in pocket_lecture.THEMES.values() for key in ("sans", "serif") if theme.get(key)})
    done = {"formulas": 0, "fonts": 0}
    with tempconfig({"verbosity": "ERROR", "progress_bar": "none", "tex_dir": config.tex_dir, "text_dir": config.text_dir}):
        for formula in FORMULAS:
            try:
                MathTex(formula)
                done["formulas"] += 1
            except Exception as error:  # noqa: BLE001 -- a warm-up never fails the server
                print(f"warm: {formula!r}: {error}", file=sys.stderr)
                break                       # no LaTeX: the rest would fail the same way
        for font in fonts:
            try:
                Text("The lecture begins 0123456789", font=font)
                done["fonts"] += 1
            except Exception as error:  # noqa: BLE001
                print(f"warm: font {font}: {error}", file=sys.stderr)
    print(f"warm: {done['formulas']} formulas and {done['fonts']} fonts in {manim_cache()} "
          f"({time.time() - started:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
