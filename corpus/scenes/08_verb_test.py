"""Create and Transform -- the animation verbs the DSL prototype must reproduce.

These are the two that matter. Create drives pointwise_become_partial, which
changes the point count every frame; Transform aligns two paths with different
curve counts and interpolates. If an independent runtime can reproduce these,
it can reproduce most of Manim's 2D vocabulary.
"""

from manim import *


class VerbTest(Scene):
    def construct(self):
        circle = Circle(radius=2, color=BLUE, stroke_width=6)
        self.play(Create(circle), run_time=2)

        target = Square(side_length=3, color=YELLOW, stroke_width=6)
        self.play(Transform(circle, target), run_time=2)
        self.wait(1)
