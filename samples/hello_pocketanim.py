"""A small Manim scene, written the way anyone would write one.

This is the sample the player app ships with, and it is deliberately ordinary:
a title, a shape, a transform, a move. Nothing here is chosen to flatter the
exporter. What makes it interesting is what it becomes -- a few hundred bytes
of program that the phone runs, rather than a video file it downloads.

    manim -pql samples/hello_pocketanim.py HelloPocketanim   # the video
    python -m dsl.export_dsl samples/hello_pocketanim.py HelloPocketanim --write
"""

from manim import *


class HelloPocketanim(Scene):
    def construct(self):
        title = Text("pocketanim", font_size=56)
        self.play(Write(title), run_time=1.5)
        self.wait(0.5)
        self.play(title.animate.scale(0.45).shift(UP * 2.8), run_time=1)

        circle = Circle(radius=1.3, color=BLUE_C, stroke_width=6)
        self.play(Create(circle), run_time=1.2)
        self.wait(0.5)

        square = Square(side_length=2.3, color=YELLOW_C, stroke_width=6)
        self.play(Transform(circle, square), run_time=1.5)
        self.wait(0.5)

        self.play(circle.animate.scale(1.4).shift(LEFT * 3), run_time=1.5)
        self.wait(1)
