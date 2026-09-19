"""Shapes plus text -- the tier-1 + tier-2 hybrid.

Text is the dominant blocker across the corpus (Write, Text, MathTex, Tex and
Code are all the same underlying problem). LaTeX cannot run on device and Manim
hands us outlines with no glyph identity, so text can never be *program*; it has
to be a referenced asset.

This scene is the smallest thing that exercises both tiers at once: geometry
that ships as a program, and text that ships as an asset the program points at.
"""

from manim import *


class TextHybrid(Scene):
    def construct(self):
        title = Text("pocketanim", font_size=48).to_edge(UP)
        self.add(title)

        circle = Circle(radius=1.8, color=BLUE, stroke_width=6)
        self.play(Create(circle), run_time=2)

        target = Square(side_length=2.8, color=YELLOW, stroke_width=6)
        self.play(Transform(circle, target), run_time=2)
        self.wait(1)
