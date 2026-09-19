"""2D plot and geometry sequence.

Stresses: the case that defeats keyframe-based formats. ValueTracker plus
always_redraw means geometry is an arbitrary function of time, recomputed
from scratch every frame rather than interpolated between keyframes.

Also carries a high static path count (Riemann rectangles) so that static
and morphing geometry can be measured separately -- Skia caches the former
and re-tessellates the latter.
"""

from manim import *


class PlotGeometry(Scene):
    def construct(self):
        axes = Axes(
            x_range=[0, 5, 1],
            y_range=[0, 5, 1],
            axis_config={"include_numbers": True},
        )
        labels = axes.get_axis_labels(x_label="x", y_label="f(x)")
        self.play(Create(axes), Write(labels))

        curve = axes.plot(lambda x: 0.4 * x**2, x_range=[0, 3.5], color=BLUE)
        self.play(Create(curve))

        # High static path count: 40 rectangles Skia should be able to cache.
        rects = axes.get_riemann_rectangles(
            curve, x_range=[0, 3.5], dx=0.0875, input_sample_type="right"
        )
        self.play(Create(rects), run_time=2)
        self.wait(0.5)
        self.play(FadeOut(rects))

        # Morphing geometry: recomputed every frame from the tracker.
        t = ValueTracker(0.5)

        tangent = always_redraw(
            lambda: axes.plot(
                lambda x: 0.8 * t.get_value() * (x - t.get_value())
                + 0.4 * t.get_value() ** 2,
                x_range=[max(0, t.get_value() - 1.2), min(3.5, t.get_value() + 1.2)],
                color=YELLOW,
            )
        )
        dot = always_redraw(
            lambda: Dot(axes.c2p(t.get_value(), 0.4 * t.get_value() ** 2), color=RED)
        )
        readout = always_redraw(
            lambda: MathTex(f"f'({t.get_value():.2f}) = {0.8 * t.get_value():.2f}")
            .scale(0.8)
            .to_corner(UR)
        )

        self.play(Create(tangent), FadeIn(dot), Write(readout))
        self.play(t.animate.set_value(3.2), run_time=4, rate_func=smooth)
        self.play(t.animate.set_value(1.0), run_time=3, rate_func=smooth)
        self.wait(1)
