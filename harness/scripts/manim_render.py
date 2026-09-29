"""`python -m manim ...` with the same arguments, able to render MathTex and Tex without LaTeX installed.

Without LaTeX, Manim stops a scene with "FileNotFoundError: No such file or directory: 'latex'". This installs
harness/lecture/nolatex.py first, which draws TeX mobjects from Pango text when LaTeX is missing (and does
nothing when it is installed), then runs Manim's own command line.

    python harness/scripts/manim_render.py render -qm scene.py SceneClass
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lecture"))

import nolatex  # noqa: E402

nolatex.install()

from manim.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.argv[0] = "manim"
    main()
