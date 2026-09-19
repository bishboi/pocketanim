"""Parametric surface under a camera orbit -- the DSL prototype's target.

Deliberately narrow. This isolates the claim being tested: procedural geometry
plus a camera track, which is where the 99.97% reduction was measured. It has
no axes, no text, and no entry animation, so a fidelity result reflects
geometry generation and camera replication rather than animation semantics.
"""

from manim import *


class SurfaceOrbit(ThreeDScene):
    def construct(self):
        surface = Surface(
            lambda u, v: np.array([u, v, 0.6 * np.sin(u) * np.cos(v)]),
            u_range=[-3, 3],
            v_range=[-3, 3],
            resolution=(24, 24),
            fill_opacity=0.7,
            checkerboard_colors=[BLUE_D, BLUE_E],
            stroke_width=0.5,
        )

        self.set_camera_orientation(phi=60 * DEGREES, theta=-45 * DEGREES)
        self.add(surface)

        self.move_camera(phi=45 * DEGREES, theta=45 * DEGREES, run_time=3)
        self.begin_ambient_camera_rotation(rate=0.3)
        self.wait(3)
        self.stop_ambient_camera_rotation()
        self.wait(1)
