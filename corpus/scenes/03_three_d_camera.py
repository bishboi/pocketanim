"""3D scene with a camera move.

Stresses: whether 3D can replay on a 2D substrate. Manim's Cairo renderer has
no z-buffer -- it projects to 2D Beziers in painter order -- so this scene
should replay exactly on Skia Canvas provided the IR carries 3D vertices and
the camera rather than flattened output.

The surface is non-self-occluding, which is what makes painter order
sufficient here. Contrast with 05, which is not.
"""

from manim import *


class ThreeDCamera(ThreeDScene):
    def construct(self):
        axes = ThreeDAxes(
            x_range=[-3, 3, 1], y_range=[-3, 3, 1], z_range=[-2, 2, 1]
        )

        surface = Surface(
            lambda u, v: axes.c2p(u, v, 0.6 * np.sin(u) * np.cos(v)),
            u_range=[-3, 3],
            v_range=[-3, 3],
            resolution=(24, 24),
            fill_opacity=0.7,
            checkerboard_colors=[BLUE_D, BLUE_E],
        )

        self.set_camera_orientation(phi=60 * DEGREES, theta=-45 * DEGREES)
        self.play(Create(axes))
        self.play(Create(surface), run_time=2)

        # Camera move: the payload-critical case. If the IR carries the camera
        # track rather than baked frames, this costs almost nothing.
        self.move_camera(phi=45 * DEGREES, theta=45 * DEGREES, run_time=3)
        self.begin_ambient_camera_rotation(rate=0.3)
        self.wait(3)
        self.stop_ambient_camera_rotation()
        self.wait(1)
