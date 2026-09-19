"""Molecular structure: many small occluding 3D solids.

Stresses the one case painter order cannot express. Manim's Cairo renderer has
no z-buffer, so overlapping opaque spheres are drawn in list order rather than
depth order -- the artefact this scene exists to expose and measure.

Also the extreme of the object-count axis: hundreds of separate mobjects with
low point counts each, where draw-call batching matters more than path
throughput. Built from Manim primitives rather than RDKit so the corpus has no
chemistry dependency; the geometry is what is being measured, not the science.
"""

from manim import *

# Caffeine-like skeleton: (x, y, z, element). Coordinates are illustrative.
ATOMS = [
    (0.0, 0.0, 0.0, "C"), (1.2, 0.5, 0.2, "N"), (2.3, -0.3, -0.1, "C"),
    (2.0, -1.6, -0.4, "C"), (0.7, -2.0, -0.5, "N"), (-0.4, -1.2, -0.2, "C"),
    (-1.6, -1.7, -0.3, "O"), (3.5, 0.2, 0.0, "O"), (1.4, 1.9, 0.5, "C"),
    (0.4, -3.4, -0.8, "C"), (3.0, -2.6, -0.6, "N"), (4.2, -2.2, -0.4, "C"),
    (2.8, -3.9, -0.9, "C"), (-1.0, 1.0, 0.3, "H"), (5.1, -2.8, -0.5, "H"),
]

BONDS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (5, 6), (2, 7),
    (1, 8), (4, 9), (3, 10), (10, 11), (10, 12), (0, 13), (11, 14),
]

COLORS = {"C": GREY_B, "N": BLUE_D, "O": RED_D, "H": WHITE}
RADII = {"C": 0.28, "N": 0.26, "O": 0.26, "H": 0.16}


class MolecularStructure(ThreeDScene):
    def construct(self):
        self.set_camera_orientation(phi=70 * DEGREES, theta=-50 * DEGREES, zoom=0.9)

        atoms = VGroup()
        for x, y, z, el in ATOMS:
            atoms.add(
                Sphere(radius=RADII[el], resolution=(12, 12))
                .set_color(COLORS[el])
                .move_to([x, y, z])
            )

        bonds = VGroup()
        for i, j in BONDS:
            a = np.array(ATOMS[i][:3], dtype=float)
            b = np.array(ATOMS[j][:3], dtype=float)
            bonds.add(
                Line3D(start=a, end=b, thickness=0.035, color=GREY_D)
            )

        molecule = VGroup(bonds, atoms).move_to(ORIGIN)

        self.play(FadeIn(bonds), run_time=1)
        self.play(LaggedStart(*[GrowFromCenter(a) for a in atoms], lag_ratio=0.04), run_time=2)

        # Camera orbit: geometry is static, only the camera moves. This is the
        # case that made 3D 17.8x smaller as IR than as video.
        self.begin_ambient_camera_rotation(rate=0.5)
        self.wait(5)
        self.stop_ambient_camera_rotation()
        self.wait(1)
