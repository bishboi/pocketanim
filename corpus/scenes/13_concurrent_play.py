"""Several animations in one play(), which Manim runs together.

The corpus gap behind the second of the three tier-1-but-wrong defects. Every
other scene here animates one thing per play(), so nothing ever exercised the
case where Manim runs two at once -- and the exporter emitted them as
consecutive verbs, which played for the sum of their durations instead of the
longest, and showed them one after the other.

Deliberately dull, again. Two shapes created together, then two moved together,
so a failure means concurrency was lost and nothing else.
"""

from manim import *


class ConcurrentPlay(Scene):
    def construct(self):
        left = Circle(radius=0.9, color=BLUE_C).shift(LEFT * 3)
        right = Square(side_length=1.6, color=YELLOW_C).shift(RIGHT * 3)

        self.play(Create(left), Create(right), run_time=2)
        self.wait(0.5)
        self.play(
            left.animate.shift(UP * 1.5),
            right.animate.shift(DOWN * 1.5),
            run_time=1.5,
        )
        self.wait(1)
