"""A three-minute lesson: the duration the corpus was extrapolating to.

Every other corpus scene is 6-14.5 s, which made the IR-versus-video figures at
3 minutes an extrapolation rather than a measurement (§11). The two costs scale
differently -- video pays per second of runtime, IR pays per *change* -- so the
ratio is duration-sensitive and cannot be extended by multiplying.

Built to be representative rather than favourable: roughly half its runtime is
spent holding still while a viewer reads, which is what a real explainer does
and is also exactly where the two encodings diverge most. The geometry is
modest and repetitive on purpose; the variable under test is duration.
"""

from manim import *

PALETTE = [BLUE_D, TEAL_D, GREEN_D, YELLOW_D, RED_D, PURPLE_D]

SECTIONS = [
    ("Sampling", "Store the result at every frame"),
    ("Programs", "Store the computation once"),
    ("Atlases", "Store each shape once"),
    ("Cameras", "Store the viewpoint, not the view"),
    ("Tiers", "Fall back only where you must"),
    ("Fidelity", "Measure it, do not assert it"),
]


class LongLesson(Scene):
    def construct(self):
        title = Text("Shipping the computation", font_size=44).to_edge(UP)
        self.play(Write(title), run_time=2)
        self.wait(3)

        for index, (heading, body) in enumerate(SECTIONS):
            colour = PALETTE[index % len(PALETTE)]

            label = Text(heading, font_size=36, color=colour).shift(UP * 1.6)
            caption = Text(body, font_size=24).next_to(label, DOWN, buff=0.6)

            self.play(FadeIn(label), run_time=1)
            self.play(Write(caption), run_time=2)
            self.wait(4)

            # A shape per section, created then transformed: the cheap case for
            # a program and the expensive one for video, which pays for every
            # frame of the motion regardless.
            ring = Circle(radius=1.1, color=colour, stroke_width=6).shift(DOWN * 1.4)
            self.play(Create(ring), run_time=2)
            self.wait(2)

            box = Square(side_length=2.0, color=colour, stroke_width=6).shift(DOWN * 1.4)
            self.play(Transform(ring, box), run_time=2)
            self.wait(3)

            self.play(ring.animate.scale(1.35).shift(RIGHT * 0.8), run_time=2)
            self.wait(3)

            self.play(FadeOut(ring), run_time=1)
            self.play(FadeOut(caption), run_time=1)
            self.play(FadeOut(label), run_time=1)
            self.wait(1)

        closing = Text("IR cost scales with change.", font_size=32).shift(DOWN * 0.5)
        self.play(Write(closing), run_time=2)
        self.wait(5)
        self.play(FadeOut(closing), run_time=1)
        self.play(FadeOut(title), run_time=1)
        self.wait(2)
