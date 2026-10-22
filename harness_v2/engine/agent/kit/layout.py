"""Placing things: frame zones, rows, columns, grids, fitting, keeping inside the frame, and pushing labels apart.
Nothing here owns the frame: each helper moves what it is given and returns it.

    place(map_, "left", pad=0.4)                 # fitted into the left half (zones: ZONES)
    row([a, b, c], gap=0.5).move_to(DOWN)         # side by side
    grid(cards, cols=3)                           # in a grid
    keep_in_frame(label_)                         # nudged back inside the safe frame
    separate(labels)                              # labels pushed apart until none overlap
"""

from __future__ import annotations

import numpy as np
from manim import DOWN, LEFT, ORIGIN, RIGHT, UP, VGroup, config

FW, FH = config.frame_width, config.frame_height

# name: (centre x, centre y, width, height), in frame units (14.2 x 8)
ZONES = {
    "full": (0, 0, FW, FH),
    "center": (0, 0, FW * 0.6, FH * 0.6),
    "left": (-FW / 4, 0, FW / 2, FH),
    "right": (FW / 4, 0, FW / 2, FH),
    "top": (0, FH / 4, FW, FH / 2),
    "bottom": (0, -FH / 4, FW, FH / 2),
    "left_third": (-FW / 3, 0, FW / 3, FH),
    "middle_third": (0, 0, FW / 3, FH),
    "right_third": (FW / 3, 0, FW / 3, FH),
    "left_two_thirds": (-FW / 6, 0, FW * 2 / 3, FH),
    "right_two_thirds": (FW / 6, 0, FW * 2 / 3, FH),
    "upper_left": (-FW / 4, FH / 4, FW / 2, FH / 2),
    "upper_right": (FW / 4, FH / 4, FW / 2, FH / 2),
    "lower_left": (-FW / 4, -FH / 4, FW / 2, FH / 2),
    "lower_right": (FW / 4, -FH / 4, FW / 2, FH / 2),
    "title": (0, FH / 2 - 1.0, FW, 1.6),
    "body": (0, -0.6, FW, FH - 2.0),
}


def zone(name: str, pad: float = 0.4):
    """(centre point, width, height) of a frame zone, less `pad` all round."""
    x, y, w, h = ZONES[name]
    return np.array([x, y, 0.0]), w - 2 * pad, h - 2 * pad


def place(mob, where: str = "center", pad: float = 0.4, grow: bool = False):
    """Fit `mob` into a zone (shrunk to fit; grown to fill too with grow=True) and centre it there."""
    c, w, h = zone(where, pad)
    k = min(w / max(mob.width, 1e-6), h / max(mob.height, 1e-6))
    if k < 1 or grow:
        mob.scale(k)
    return mob.move_to(c)


def row(items, gap: float = 0.4, align=ORIGIN) -> VGroup:
    """Items side by side (VGroup of them; `align` UP/DOWN aligns their tops/bottoms)."""
    g = VGroup(*items)
    return g.arrange(RIGHT, buff=gap, aligned_edge=align)


def column(items, gap: float = 0.3, align=LEFT) -> VGroup:
    g = VGroup(*items)
    return g.arrange(DOWN, buff=gap, aligned_edge=align)


def grid(items, cols: int = 3, gap: float = 0.35) -> VGroup:
    g = VGroup(*items)
    rows = int(np.ceil(len(items) / cols))
    return g.arrange_in_grid(rows=rows, cols=cols, buff=gap)


def fit_to(mob, width: float | None = None, height: float | None = None):
    """Shrink (never grow) to fit."""
    if width and mob.width > width:
        mob.scale_to_fit_width(width)
    if height and mob.height > height:
        mob.scale_to_fit_height(height)
    return mob


def keep_in_frame(mob, margin: float = 0.3, frame=None):
    """Nudge `mob` back inside the frame (or another mobject `frame`, such as the camera's frame), `margin` in."""
    if frame is not None:
        left, right = frame.get_left()[0], frame.get_right()[0]
        bottom, top = frame.get_bottom()[1], frame.get_top()[1]
    else:
        left, right, bottom, top = -FW / 2, FW / 2, -FH / 2, FH / 2
    dx = max(0, left + margin - mob.get_left()[0]) - max(0, mob.get_right()[0] - (right - margin))
    dy = max(0, bottom + margin - mob.get_bottom()[1]) - max(0, mob.get_top()[1] - (top - margin))
    return mob.shift(RIGHT * dx + UP * dy)


def _overlap(a, b, gap):
    return not (a.get_right()[0] + gap <= b.get_left()[0] or b.get_right()[0] + gap <= a.get_left()[0]
                or a.get_top()[1] + gap <= b.get_bottom()[1] or b.get_top()[1] + gap <= a.get_bottom()[1])


def overlaps(mobs, gap: float = 0.0) -> list[tuple[int, int]]:
    """Pairs (i, j) of mobjects whose boxes overlap (with `gap` between them required)."""
    out = []
    for i in range(len(mobs)):
        for j in range(i + 1, len(mobs)):
            if _overlap(mobs[i], mobs[j], gap):
                out.append((i, j))
    return out


def separate(mobs, gap: float = 0.08, fixed=(), steps: int = 60):
    """Push overlapping mobjects (labels) apart, a little at a time, along the axis of least overlap. Those in
    `fixed` (indices) stay put. Returns the mobjects."""
    fixed = set(fixed)
    for _ in range(steps):
        moved = False
        for i, j in overlaps(mobs, gap):
            a, b = mobs[i], mobs[j]
            d = b.get_center() - a.get_center()
            ox = (a.width + b.width) / 2 + gap - abs(d[0])
            oy = (a.height + b.height) / 2 + gap - abs(d[1])
            push = RIGHT * np.sign(d[0] or 1) * ox if ox < oy else UP * np.sign(d[1] or 1) * oy
            if i in fixed and j in fixed:
                continue
            if i in fixed:
                b.shift(push)
            elif j in fixed:
                a.shift(-push)
            else:
                a.shift(-push / 2)
                b.shift(push / 2)
            moved = True
        if not moved:
            break
    return mobs


def spread(mobs, start, end) -> list:
    """Mobjects spaced evenly along a line from `start` to `end`."""
    start, end = np.array(start, dtype=float), np.array(end, dtype=float)
    n = len(mobs)
    for i, m in enumerate(mobs):
        m.move_to(start + (end - start) * (i / max(1, n - 1) if n > 1 else 0.5))
    return mobs


def edge_point(mob, direction) -> np.ndarray:
    """Where a ray from `mob`'s centre along `direction` leaves its bounding box (for arrows that meet a box at its
    edge, square on, whatever the box's shape)."""
    if not hasattr(mob, "get_center"):
        return np.array(mob, dtype=float)              # a point: the ray leaves it where it starts
    c = mob.get_center()
    d = np.array(direction, dtype=float)
    n = np.linalg.norm(d[:2])
    if n < 1e-9:
        return c
    d = d / n
    hw, hh = mob.width / 2, mob.height / 2
    tx = hw / abs(d[0]) if abs(d[0]) > 1e-9 else np.inf
    ty = hh / abs(d[1]) if abs(d[1]) > 1e-9 else np.inf
    return c + d * min(tx, ty)
