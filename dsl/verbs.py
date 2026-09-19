"""Shape generation and animation semantics, reimplemented without Manim.

This is the part ticket #9 was worried about: reproducing Manim's animation
behaviour independently, where any mismatch becomes visual drift. Each function
here mirrors a specific piece of Manim and says which, so a future reader can
check it against upstream when Manim changes.
"""

from __future__ import annotations

import math

import numpy as np

NPPC = 4  # Manim's n_points_per_cubic_curve


def bezier(points: np.ndarray):
    """Evaluate the Bezier curve defined by `points` at t."""
    n = len(points) - 1

    def at(t: float) -> np.ndarray:
        return sum(
            math.comb(n, i) * ((1 - t) ** (n - i)) * (t**i) * np.asarray(points[i])
            for i in range(n + 1)
        )

    return at


def partial_bezier(points: np.ndarray, a: float, b: float) -> np.ndarray:
    """Manim's partial_bezier_points: the sub-curve of `points` over [a, b]."""
    if a == 1:
        return np.array([points[-1]] * len(points))
    a_to_1 = np.array([bezier(points[i:])(a) for i in range(len(points))])
    end_prop = (b - a) / (1.0 - a)
    return np.array([bezier(a_to_1[: i + 1])(end_prop) for i in range(len(points))])


def integer_interpolate(start: int, end: int, alpha: float) -> tuple[int, float]:
    """Manim's integer_interpolate: which curve, and how far into it."""
    if alpha >= 1:
        return (end - 1, 1.0)
    if alpha <= 0:
        return (start, 0.0)
    value = int(start + (end - start) * alpha)
    residue = ((end - start) * alpha) % 1
    return (value, residue)


def pointwise_become_partial(points: np.ndarray, a: float, b: float) -> np.ndarray:
    """Manim's VMobject.pointwise_become_partial -- what drives Create/Write."""
    if a <= 0 and b >= 1:
        return points.copy()
    num_curves = len(points) // NPPC
    if num_curves == 0:
        return points.copy()

    lower_index, lower_residue = integer_interpolate(0, num_curves, a)
    upper_index, upper_residue = integer_interpolate(0, num_curves, b)

    if lower_index == upper_index:
        return partial_bezier(
            points[NPPC * lower_index : NPPC * (lower_index + 1)],
            lower_residue,
            upper_residue,
        )

    chunks = [
        partial_bezier(
            points[NPPC * lower_index : NPPC * (lower_index + 1)], lower_residue, 1.0
        )
    ]
    if upper_index > lower_index + 1:
        chunks.append(points[NPPC * (lower_index + 1) : NPPC * upper_index])
    chunks.append(
        partial_bezier(
            points[NPPC * upper_index : NPPC * (upper_index + 1)], 0.0, upper_residue
        )
    )
    return np.vstack(chunks)


def remap_curves(points: np.ndarray, target_curves: int) -> np.ndarray:
    """Resample a path to exactly `target_curves` cubics.

    Mirrors Manim's bezier_remap, used by align_points before interpolating
    between two shapes with different curve counts.
    """
    current = len(points) // NPPC
    if current == 0 or target_curves <= current:
        return points.copy()

    # Distribute the extra curves over the existing ones as evenly as possible.
    split_counts = [target_curves // current] * current
    for i in range(target_curves % current):
        split_counts[i] += 1

    out = []
    for index, count in enumerate(split_counts):
        curve = points[NPPC * index : NPPC * (index + 1)]
        for k in range(count):
            out.append(partial_bezier(curve, k / count, (k + 1) / count))
    return np.vstack(out)


def align(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bring two paths to a common curve count so they can be interpolated."""
    target = max(len(a) // NPPC, len(b) // NPPC)
    return remap_curves(a, target), remap_curves(b, target)


def circle(radius: float, segments: int = 8) -> np.ndarray:
    """Manim's Circle: `segments` cubic arcs, handles at 4/3*tan(d/4)*r."""
    step = 2 * math.pi / segments
    handle = (4 / 3) * math.tan(step / 4) * radius

    points = []
    for i in range(segments):
        t0, t1 = i * step, (i + 1) * step
        p0 = np.array([radius * math.cos(t0), radius * math.sin(t0), 0.0])
        p3 = np.array([radius * math.cos(t1), radius * math.sin(t1), 0.0])
        tangent0 = np.array([-math.sin(t0), math.cos(t0), 0.0])
        tangent1 = np.array([-math.sin(t1), math.cos(t1), 0.0])
        points.extend([p0, p0 + tangent0 * handle, p3 - tangent1 * handle, p3])
    return np.array(points)


def rectangle(width: float, height: float) -> np.ndarray:
    """Manim's Rectangle: same winding as Square, independent extents."""
    w, h = width / 2, height / 2
    corners = [
        np.array([w, h, 0.0]),
        np.array([-w, h, 0.0]),
        np.array([-w, -h, 0.0]),
        np.array([w, -h, 0.0]),
        np.array([w, h, 0.0]),
    ]
    points = []
    for start, end in zip(corners, corners[1:]):
        for t in (0.0, 1 / 3, 2 / 3, 1.0):
            points.append(start + (end - start) * t)
    return np.array(points)


def square(side: float) -> np.ndarray:
    """Manim's Square: corners counter-clockwise from top-right, straight edges."""
    h = side / 2
    corners = [
        np.array([h, h, 0.0]),
        np.array([-h, h, 0.0]),
        np.array([-h, -h, 0.0]),
        np.array([h, -h, 0.0]),
        np.array([h, h, 0.0]),
    ]
    points = []
    for start, end in zip(corners, corners[1:]):
        for t in (0.0, 1 / 3, 2 / 3, 1.0):
            points.append(start + (end - start) * t)
    return np.array(points)
