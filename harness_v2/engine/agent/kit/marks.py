"""Marks that point at something and stay: highlight, circle, underline, arrow, strike, box, bracket, callout,
stamp, tick and cross, dimension lines, a spotlight. In vox they look drawn by hand (a marker on paper); in
blueprint they are drafting marks (clean, dashed, with end ticks).

    m = circle(word)            # a mark around `word`, not yet on stage
    self.play(m.appear())       # drawn on (each mark draws itself in its look)
    self.play(FadeOut(m))       # an ordinary mobject from then on

Every mark takes `color=` (default: the look's accent or highlighter colour).
"""

from __future__ import annotations

import numpy as np
from manim import (DL, DOWN, DR, LEFT, ORIGIN, PI, RIGHT, UL, UP, UR, Arc, Arrow, Circle, Cutout, CurvedArrow, DashedVMobject,
                   Dot, Line, Polygon, Rectangle, RoundedRectangle, Text, VGroup, VMobject, config)

from .base import Piece
from .layout import edge_point
from .look import L
from .text import label, text


def _hand() -> bool:
    return L().name != "blueprint"


def _wobble(points: np.ndarray, amount: float, seed: int) -> np.ndarray:
    """Points nudged by a smooth noise (a hand's line, not a ruler's)."""
    rng = np.random.default_rng(seed)
    n = len(points)
    k = max(3, n // 8)
    knots = rng.normal(0, amount, (k, 2))
    xs = np.linspace(0, 1, k)
    t = np.linspace(0, 1, n)
    out = points.copy()
    out[:, 0] += np.interp(t, xs, knots[:, 0])
    out[:, 1] += np.interp(t, xs, knots[:, 1])
    return out


def _path(points: np.ndarray, color, width) -> VMobject:
    v = VMobject(stroke_color=color, stroke_width=width)
    v.set_points_smoothly([np.array([p[0], p[1], 0]) for p in points])
    return v


class Mark(Piece):
    enter_kind = "line"


def _dash(v: VMobject) -> VMobject:
    return DashedVMobject(v, num_dashes=max(8, int(v.get_arc_length() / 0.18)), dashed_ratio=0.6)


def highlight(target, color=None, opacity: float = 0.85, pad: float = 0.08) -> Mark:
    """A highlighter stroke behind `target` (vox: a marker-yellow swipe; blueprint: a translucent cyan band).
    It sits behind the target (z_index - 1). Appears by sweeping from the left."""
    look = L()
    c = color or look.mark
    w, h = target.width + 2 * pad, target.height * (0.62 if _hand() else 1.0) + 2 * pad
    bar = Polygon(*[np.array(p) for p in (
        (-w / 2, -h / 2 + 0.02, 0), (w / 2, -h / 2, 0), (w / 2 - 0.03, h / 2, 0), (-w / 2 + 0.02, h / 2 - 0.03, 0))],
        stroke_width=0, fill_color=c, fill_opacity=opacity if _hand() else 0.3)
    bar.move_to(target.get_center() + (DOWN * target.height * 0.12 if _hand() else ORIGIN))
    bar.set_z_index(target.z_index - 1)
    m = Mark(bar)
    m.entering("grow_left")
    return m


def circle(target, color=None, width: float | None = None, pad: float = 0.22, seed: int = 3) -> Mark:
    """A loop drawn around `target` (vox: a marker loop that overshoots its start; blueprint: a dashed ellipse)."""
    look = L()
    c = color or look.accent
    sw = width or look.stroke * 1.2
    a, b = target.width / 2 + pad, target.height / 2 + pad
    cx, cy = target.get_center()[:2]
    if _hand():
        t = np.linspace(0.15 * PI, 2.25 * PI, 90)
        pts = np.stack([cx + a * 1.04 * np.cos(t), cy + b * 1.1 * np.sin(t)], axis=1)
        pts = _wobble(pts, min(a, b) * 0.06, seed)
        return Mark(_path(pts, c, sw))
    e = Circle(radius=1, stroke_color=c, stroke_width=sw).stretch(a, 0).stretch(b, 1).move_to(target)
    return Mark(_dash(e))


def underline(target, color=None, width: float | None = None, gap: float = 0.08, seed: int = 5) -> Mark:
    """A line under `target` (vox: a quick marker stroke; blueprint: a ruled line with end ticks)."""
    look = L()
    c = color or look.accent
    sw = width or look.stroke * 1.3
    y = target.get_bottom()[1] - gap
    x0, x1 = target.get_left()[0] - 0.05, target.get_right()[0] + 0.1
    if _hand():
        pts = np.stack([np.linspace(x0, x1, 30), y + np.linspace(0.02, -0.04, 30)], axis=1)
        return Mark(_path(_wobble(pts, 0.015, seed), c, sw))
    line = Line([x0, y, 0], [x1, y, 0], color=c, stroke_width=sw)
    ticks = VGroup(*(Line(UP * 0.1, DOWN * 0.1, color=c, stroke_width=sw).move_to(p) for p in (line.get_start(), line.get_end())))
    return Mark(line, ticks)


def strike(target, color=None, width: float | None = None, seed: int = 9) -> Mark:
    """A line through `target` (crossed out)."""
    look = L()
    c = color or look.accent
    sw = width or look.stroke * 1.3
    x0, x1 = target.get_left()[0] - 0.08, target.get_right()[0] + 0.08
    y = target.get_center()[1]
    pts = np.stack([np.linspace(x0, x1, 24), np.linspace(y - 0.05, y + 0.06, 24)], axis=1)
    return Mark(_path(_wobble(pts, 0.012, seed) if _hand() else pts, c, sw))


def box(target, color=None, width: float | None = None, pad: float = 0.15) -> Mark:
    """A frame around `target` (vox: a loose marker box; blueprint: a dashed box with corner ticks)."""
    look = L()
    c = color or look.accent
    sw = width or look.stroke
    r = Rectangle(width=target.width + 2 * pad, height=target.height + 2 * pad, stroke_color=c, stroke_width=sw)
    r.move_to(target)
    if _hand():
        pts = np.array([p[:2] for p in r.get_vertices()] + [r.get_vertices()[0][:2] + np.array([0.12, 0.04])])
        dense = np.concatenate([np.linspace(pts[i], pts[i + 1], 12) for i in range(len(pts) - 1)])
        v = VMobject(stroke_color=c, stroke_width=sw)
        v.set_points_as_corners([np.array([p[0], p[1], 0]) for p in _wobble(dense, 0.02, 11)])
        return Mark(v)
    corners = VGroup()
    for v in r.get_vertices():
        corners.add(Dot(v, radius=0.035, color=c))
    return Mark(_dash(r), corners)


def arrow(start, end, color=None, width: float | None = None, curve: float = 0.35, tip: float = 0.22,
          label_text: str | None = None, label_size: float = 22) -> Mark:
    """An arrow from `start` to `end` (points or mobjects: it stops short of a mobject's edge). Curved by `curve`
    (0: straight). Vox: a marker arrow; blueprint: a thin drafting arrow. `label_text` sits at its middle."""
    look = L()
    c = color or look.accent
    sw = width or look.stroke * 1.1

    def pt(x, toward):
        if hasattr(x, "get_center"):
            centre = x.get_center()
            d = np.array(toward) - centre
            d = d / (np.linalg.norm(d) or 1)
            return edge_point(x, d) + d * 0.1
        return np.array(x, dtype=float)

    a0 = start.get_center() if hasattr(start, "get_center") else np.array(start, dtype=float)
    b0 = end.get_center() if hasattr(end, "get_center") else np.array(end, dtype=float)
    a, b = pt(start, b0), pt(end, a0)
    if curve:
        arr = CurvedArrow(a, b, angle=-curve * PI / 1.5, color=c, stroke_width=sw, tip_length=tip)
    else:
        arr = Arrow(a, b, buff=0, color=c, stroke_width=sw, tip_length=tip, max_tip_length_to_length_ratio=0.3)
    m = Mark(arr)
    m.name_part("arrow", arr)
    if label_text:
        lab = label(label_text, size=label_size, color=c, role="hand" if _hand() else "mono")
        mid = arr.point_from_proportion(0.5)
        normal = np.array([-(b - a)[1], (b - a)[0], 0])
        normal = normal / (np.linalg.norm(normal) or 1)
        lab.move_to(mid + normal * (lab.height / 2 + 0.15) * (1 if curve >= 0 else -1))
        m.add(lab)
        m.name_part("label", lab)
    return m


def callout(target, words: str, side=None, distance: float = 1.4, color=None, size: float = 24,
            width: float = 3.5) -> Mark:
    """A note pointing at `target`: words placed to one side (`side`: a direction like UP+RIGHT; default the side
    with most room) and a leader line to it (vox: handwriting and a marker line; blueprint: mono and a dot-ended
    leader)."""
    look = L()
    c = color or look.ink
    centre = target.get_center() if hasattr(target, "get_center") else np.array(target, dtype=float)
    if side is None:
        x, y = centre[:2]
        side = np.array([-1 if x > 0 else 1, -1 if y > 0 else 1, 0]) / np.sqrt(2)
    side = np.array(side, dtype=float)
    side = side / (np.linalg.norm(side) or 1)
    note = text(words, size=size, role="hand" if _hand() else "mono", color=c, width=width)
    anchor = edge_point(target, side)
    note.move_to(anchor + side * distance + side * np.array([note.width / 2, note.height / 2, 0]))
    end = edge_point(note, -side)
    lead = Line(end - side * 0.08, anchor + side * 0.06, color=look.accent if _hand() else c, stroke_width=look.stroke * 0.8)
    dot = Dot(anchor + side * 0.06, radius=0.05, color=lead.get_color())
    m = Mark(lead, dot, note)
    m.name_part("line", lead)
    m.name_part("words", note)
    return m


def bracket(target, words: str | None = None, side=RIGHT, color=None, size: float = 24) -> Mark:
    """A brace along one side of `target` (a group of items) with words beside it."""
    from manim import Brace
    look = L()
    c = color or look.accent
    br = Brace(target, direction=np.array(side, dtype=float), color=c, sharpness=1.2)
    m = Mark(br)
    m.name_part("brace", br)
    if words:
        t = text(words, size=size, role="hand" if _hand() else "mono", color=c, width=3.5)
        t.next_to(br, np.array(side, dtype=float), buff=0.15)
        m.add(t)
        m.name_part("words", t)
    return m


def stamp(words: str, color=None, angle: float = -12, size: float = 40) -> Mark:
    """A rubber stamp ("OFFICIAL", "PROPAGANDA?", "सत्यापित"): a double-ruled box, tilted. Enters slammed down."""
    look = L()
    c = color or look.accent
    t = text(words, size=size, role="head", color=c, weight=True)
    outer = RoundedRectangle(width=t.width + 0.5, height=t.height + 0.4, corner_radius=0.08, stroke_color=c,
                             stroke_width=look.stroke * 1.4).move_to(t)
    inner = RoundedRectangle(width=t.width + 0.32, height=t.height + 0.22, corner_radius=0.05, stroke_color=c,
                             stroke_width=look.stroke * 0.6).move_to(t)
    m = Mark(outer, inner, t)
    m.rotate(angle * PI / 180)
    m.set_opacity(0.9)
    m.entering("stamp")
    m.enter_kind = "shape"
    return m


def tick(size: float = 0.5, color=None) -> Mark:
    look = L()
    c = color or look.palette[1]
    v = VMobject(stroke_color=c, stroke_width=look.stroke * 2)
    v.set_points_as_corners([LEFT * 0.5 + UP * 0.05, DOWN * 0.4 + LEFT * 0.1, RIGHT * 0.55 + UP * 0.55])
    v.scale(size)
    return Mark(v)


def cross(size: float = 0.5, color=None) -> Mark:
    look = L()
    c = color or look.accent
    a = Line(UL * 0.5, DR * 0.5, color=c, stroke_width=look.stroke * 2)
    b = Line(UR * 0.5, DL * 0.5, color=c, stroke_width=look.stroke * 2)
    return Mark(VGroup(a, b).scale(size))


def dimension(a, b, words: str | None = None, offset: float = 0.4, color=None, size: float = 20) -> Mark:
    """A drafting dimension between points a and b (the blueprint way to say "this far" / "this long"): extension
    lines, a double-headed line, and the measure written on it."""
    from manim import DoubleArrow
    look = L()
    c = color or look.muted
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    d = b - a
    n = np.array([-d[1], d[0], 0])
    n = n / (np.linalg.norm(n) or 1) * offset
    ext = VGroup(Line(a, a + n * 1.2, color=c, stroke_width=1.5), Line(b, b + n * 1.2, color=c, stroke_width=1.5))
    dim = DoubleArrow(a + n, b + n, buff=0, color=c, stroke_width=2, tip_length=0.15)
    m = Mark(ext, dim)
    if words:
        t = label(words, size=size, color=c, role="mono")
        t.move_to((a + b) / 2 + n * 1.0 + n / (np.linalg.norm(n) or 1) * 0.22)
        m.add(t)
        m.name_part("words", t)
    return m


def spotlight(target, dim: float = 0.6, pad: float = 0.25, color=None) -> Mark:
    """Everything dimmed but `target` (a dark veil with a hole round it). Fade it in and out."""
    look = L()
    veil = Rectangle(width=config.frame_width * 3, height=config.frame_height * 3)
    hole = RoundedRectangle(width=target.width + 2 * pad, height=target.height + 2 * pad, corner_radius=0.15)
    hole.move_to(target)
    cut = Cutout(veil.move_to(target), hole, fill_color=color or ("#000000" if look.name == "blueprint" else "#1B1B1B"),
                 fill_opacity=dim, stroke_width=0)
    cut.set_z_index(max(target.z_index, 0) + 5)
    m = Mark(cut)
    m.entering("fade")
    return m

