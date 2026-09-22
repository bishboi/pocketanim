"""Primitives that are not at the origin.

The corpus gap that let a real defect live: every other scene here was written
against what the exporter already supported, so nothing ever placed a circle or
a square away from (0, 0). The exporter emitted no position for either, the
interpreters had always parsed one, and no test disagreed with anything.

Deliberately dull. Three primitives, three positions, drawn one at a time so
that a failure here means "the position was lost" and nothing else.
"""

from manim import *


class PositionedPrimitives(Scene):
    def construct(self):
        circle = Circle(radius=0.8, color=BLUE_C).shift(LEFT * 3.5 + UP * 1.5)
        square = Square(side_length=1.4, color=YELLOW_C).shift(RIGHT * 3.5 + UP * 1.5)
        # Rectangle is the control: it has always carried `at=`, so if this one
        # moves and the others do not, the difference is the emitter.
        rect = Rectangle(width=2.2, height=1.1, color=GREEN_C).shift(DOWN * 2)

        self.play(Create(circle), run_time=1)
        self.play(Create(square), run_time=1)
        self.play(Create(rect), run_time=1)
        self.wait(1)
