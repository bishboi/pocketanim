"""Decimate imported artwork to the detail a screen can actually show.

Measured on a low-end phone: CartopyMap spends 96 ms per frame rasterising
62,054 path verbs, three times its whole budget. Its coastline is 10,296 cubic
segments averaging **0.6 pixels each** -- about 1.7 segments per pixel. The
detail is real, it is just finer than any display in the product.

This is an exporter concern rather than a renderer one. The device cannot know
that a shape is over-detailed; the exporter knows the target resolution and can
decide once, at export, for every playback.

Only imported artwork is decimated. Glyphs and primitives are already minimal --
a letter is a few dozen curves -- so there is nothing to win and a shape to
lose.
"""

from __future__ import annotations

import numpy as np

# Manim's frame width in scene units; the horizontal extent of the screen.
FRAME_WIDTH = 14.222222222222221

NPPC = 4  # points per cubic


def pixels_per_unit(width_px: int) -> float:
    return width_px / FRAME_WIDTH


def subpaths(points: np.ndarray, atol: float = 1e-6):
    """Split a Manim point array where one cubic stops feeding the next.

    Simplification must not weld two subpaths together: a coastline is many
    separate islands, and joining them would draw land across open water.
    """
    curves = len(points) // NPPC
    start = 0
    for i in range(1, curves):
        previous_end = points[NPPC * (i - 1) + 3]
        this_start = points[NPPC * i]
        if not np.allclose(previous_end, this_start, atol=atol):
            yield points[NPPC * start : NPPC * i]
            start = i
    if curves:
        yield points[NPPC * start :]


def _rdp_mask(pts: np.ndarray, tolerance: float) -> np.ndarray:
    """Ramer-Douglas-Peucker, iterative so a long coastline cannot blow the stack."""
    n = len(pts)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        line = pts[last] - pts[first]
        length = np.linalg.norm(line)
        span = pts[first + 1 : last]
        if length < 1e-12:
            # Degenerate span: measure from the point itself.
            distances = np.linalg.norm(span - pts[first], axis=1)
        else:
            t = ((span - pts[first]) @ line) / (length ** 2)
            projected = pts[first] + np.outer(t, line)
            distances = np.linalg.norm(span - projected, axis=1)
        index = int(np.argmax(distances))
        if distances[index] > tolerance:
            split = first + 1 + index
            keep[split] = True
            stack.append((first, split))
            stack.append((split, last))

    return keep


def simplify_subpath(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Decimate one subpath, returning straight cubics through the kept points.

    The curves are genuinely curved -- control points sit up to 0.35 of the
    chord off it -- but over a 0.6-pixel segment that bend is a fifth of a
    pixel. Straight cubics between retained endpoints therefore cost far less
    than the RDP tolerance itself, and the total error stays bounded by it.
    """
    curves = len(points) // NPPC
    if curves < 2:
        return points

    ends = np.vstack([points[0:1], points[3::NPPC]])
    keep = _rdp_mask(ends, tolerance)
    kept = ends[keep]
    if len(kept) < 2:
        return points

    out = np.empty(((len(kept) - 1) * NPPC, 3), dtype=points.dtype)
    for i in range(len(kept) - 1):
        a, b = kept[i], kept[i + 1]
        delta = b - a
        out[NPPC * i + 0] = a
        out[NPPC * i + 1] = a + delta / 3.0
        out[NPPC * i + 2] = a + delta * (2.0 / 3.0)
        out[NPPC * i + 3] = b
    return out


def simplify_shape(
    points: np.ndarray,
    tolerance: float,
    min_curves: int = 64,
) -> np.ndarray:
    """Decimate a shape if it is detailed enough to be worth decimating.

    `min_curves` keeps glyphs and primitives untouched. They are already at the
    floor, and reshaping a letter to save four curves would be a bad trade.
    """
    if len(points) // NPPC < min_curves:
        return points

    pieces = [simplify_subpath(piece, tolerance) for piece in subpaths(points)]
    pieces = [p for p in pieces if len(p) >= NPPC]
    return np.vstack(pieces) if pieces else points


def tolerance_for(width_px: int, error_px: float = 0.5, scale: float = 1.0) -> float:
    """Scene-unit tolerance for a screen width, an error budget and a zoom.

    `scale` is the largest magnification the animation applies to the artwork.
    Decimating without it would meet the budget at rest and miss it by exactly
    the zoom factor at the moment a viewer is looking closest -- which is the
    moment the detail was kept for.
    """
    return error_px / (pixels_per_unit(width_px) * scale)


def linear_scale(transforms: np.ndarray) -> np.ndarray:
    """Magnification of each row-major 3x4 transform in `transforms`.

    sqrt(max row norm * max column norm) bounds the spectral norm from above,
    and is exactly the scale factor for a similarity transform, which is what
    scaling, rotating and shifting a mobject produces.
    """
    linear = transforms[..., :3]
    rows = np.linalg.norm(linear, axis=-1).max(axis=-1)
    columns = np.linalg.norm(linear, axis=-2).max(axis=-1)
    return np.sqrt(rows * columns)
