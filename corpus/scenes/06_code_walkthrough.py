"""Syntax-highlighted code walkthrough.

Stresses: many small styled glyph runs, revealed progressively, then replaced.
Unlike the LaTeX scene this is a font/text-shaping problem rather than a
per-glyph morphing one, and it is the case that decides whether the IR needs
a text representation distinct from baked LaTeX outlines.
"""

from manim import *

BEFORE = """def integrate(f, a, b, n=1000):
    h = (b - a) / n
    total = 0.0
    for i in range(n):
        total += f(a + i * h)
    return total * h
"""

AFTER = """def integrate(f, a, b, n=1000):
    h = (b - a) / n
    total = 0.5 * (f(a) + f(b))
    for i in range(1, n):
        total += f(a + i * h)
    return total * h
"""


class CodeWalkthrough(Scene):
    def construct(self):
        title = Text("Trapezoid correction", font_size=32).to_edge(UP)
        self.play(Write(title))

        before = Code(
            code_string=BEFORE,
            language="python",
            add_line_numbers=True,
            formatter_style="monokai",
        ).scale(0.8)

        self.play(Write(before), run_time=3)
        self.wait(0.5)

        highlight = SurroundingRectangle(before, color=YELLOW, buff=0.15)
        self.play(Create(highlight))
        self.wait(0.5)

        after = (
            Code(
                code_string=AFTER,
                language="python",
                add_line_numbers=True,
                formatter_style="monokai",
            )
            .scale(0.8)
            .move_to(before)
        )

        self.play(FadeOut(highlight))
        self.play(Transform(before, after), run_time=2)
        self.wait(1)
