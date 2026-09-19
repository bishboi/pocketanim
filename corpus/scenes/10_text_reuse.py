"""A second text scene, to measure library-wide glyph amortisation.

"animation" reuses letters already in the library from "pocketanim", so if the
shared atlas works this scene should add almost no new glyph geometry and cost
only its instance records.
"""

from manim import *


class TextReuse(Scene):
    def construct(self):
        title = Text("animation", font_size=48).to_edge(UP)
        self.add(title)

        circle = Circle(radius=1.5, color=GREEN, stroke_width=6)
        self.play(Create(circle), run_time=2)
        self.wait(1)
