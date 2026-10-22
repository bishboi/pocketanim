"""Charts that build themselves: bars (growing, with values counting up), a donut, a grid of units (one in five,
60 of 100), a line chart that draws itself, and a versus (two sides compared).

    b = bars({"China": 1400, "India": 1420, "Japan": 125}, unit="M"); self.play(b.appear())
    self.play(b.highlight("Japan"))
    d = donut({"Official": 40, "Scholarly": 25, "Popular": 20, "Religious": 15})
    u = units(100, 23, label="23 of 100")
    l = line_chart([(1800, 300), (1850, 410), (1900, 440), (1950, 550)], x_label="year")
    v = versus("Insiders", ["court historians", "scholars"], "Outsiders", ["travellers", "missionaries"])
"""

from __future__ import annotations

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, PI, RIGHT, UP, Animation, AnimationGroup, AnnularSector, Create, Dot, FadeIn,
                   GrowFromEdge, LaggedStart, Line, Rectangle, RoundedRectangle, VGroup, VMobject)

from manim import rate_functions as rf

from .base import Piece
from .look import L
from .text import Count, Number, number, text


def _fmt(v: float, unit: str = "") -> str:
    s = f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.1f}"
    return f"{s}{unit}"


class Bars(Piece):
    enter_kind = "shape"

    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 1.2
        edge = DOWN if self.vertical else LEFT
        anims = [FadeIn(self.part("names"), run_time=run * 0.4), Create(self.part("base"), run_time=run * 0.4)]
        anims.append(LaggedStart(*(GrowFromEdge(b, edge, run_time=run) for b in self.bars_), lag_ratio=0.12))
        anims.append(LaggedStart(*(Count(v, run_time=run) for v in self.values_), lag_ratio=0.12))
        return owned(self, AnimationGroup(*anims))

    def highlight(self, name: str, color: str | None = None, dim: float = 0.3, run: float = 0.6):
        """One bar in the accent colour, the others dimmed."""
        c = color or L().accent
        anims = []
        for n, b in zip(self.names_, self.bars_):
            anims.append(b.animate(run_time=run).set_fill(c, opacity=1) if n == name else
                         b.animate(run_time=run).set_fill(opacity=dim))
        return AnimationGroup(*anims)

    def bar(self, name: str):
        return self.bars_[self.names_.index(name)]


def bars(data: dict, width: float = 8.0, height: float = 4.5, vertical: bool = False, unit: str = "",
         colors=None, size: float = 24, max_value: float | None = None) -> Bars:
    """Bars for {name: value}: horizontal (names on the left) by default, `vertical=True` for columns."""
    look = L()
    names, vals = list(data), [float(v) for v in data.values()]
    top = max_value or max(vals) or 1
    g = Bars()
    g.vertical = vertical
    g.names_, g.bars_, g.values_ = names, [], []
    name_mobs = VGroup()
    n = len(names)
    if vertical:
        slot = width / n
        bw = slot * 0.62
        base = Line(LEFT * width / 2, RIGHT * width / 2, color=look.ink, stroke_width=look.stroke * 0.7)
        base.shift(DOWN * height / 2)
        for i, (nm, v) in enumerate(zip(names, vals)):
            x = -width / 2 + slot * (i + 0.5)
            h = max(0.02, v / top * (height - 0.8))
            c = colors[i % len(colors)] if colors else (look.color(i) if look.name == "blueprint" else look.ink)
            bar = Rectangle(width=bw, height=h, stroke_width=0 if look.name == "vox" else 2, stroke_color=c,
                            fill_color=c, fill_opacity=0.9 if look.name == "vox" else 0.4)
            bar.move_to([x, -height / 2 + h / 2, 0])
            lab = text(nm, size=size, color=look.ink, width=slot * 0.95)
            lab.next_to([x, -height / 2, 0], DOWN, buff=0.15)
            val = number(_fmt(v, unit), size=size, color=look.ink, role="mono")
            val.next_to(bar, UP, buff=0.1)
            g.add(bar, val)
            g.bars_.append(bar)
            g.values_.append(val)
            name_mobs.add(lab)
    else:
        slot = height / n
        bh = slot * 0.6
        labels = [text(nm, size=size, color=look.ink, weight=True) for nm in names]
        lw = max(l.width for l in labels) + 0.25
        x0 = -width / 2 + lw
        base = Line([x0, height / 2, 0], [x0, -height / 2, 0], color=look.ink, stroke_width=look.stroke * 0.7)
        for i, (lab, v) in enumerate(zip(labels, vals)):
            y = height / 2 - slot * (i + 0.5)
            w = max(0.02, v / top * (width - lw - 1.4))
            c = (colors[i % len(colors)] if colors else (look.color(i) if look.name == "blueprint" else look.ink))
            bar = Rectangle(width=w, height=bh, stroke_width=0 if look.name == "vox" else 2, stroke_color=c,
                            fill_color=c, fill_opacity=0.9 if look.name == "vox" else 0.4)
            bar.move_to([x0 + w / 2, y, 0])
            lab.next_to([x0, y, 0], LEFT, buff=0.2)
            val = number(_fmt(v, unit), size=size, color=look.ink, role="mono")
            val.next_to(bar, RIGHT, buff=0.12)
            g.add(bar, val)
            g.bars_.append(bar)
            g.values_.append(val)
            name_mobs.add(lab)
    g.add(base, name_mobs)
    g.name_part("base", base)
    g.name_part("names", name_mobs)
    return g


class Sweep(Animation):
    """An annular sector opening round its circle from its start angle (a donut slice being dealt)."""

    def __init__(self, sector: AnnularSector, **kw):
        self.spec = dict(inner_radius=sector.inner_radius, outer_radius=sector.outer_radius, angle=sector.angle,
                         start_angle=sector.start_angle)
        # Where the slice now is, and how big: built at the origin, the slice may since have been moved and scaled.
        ref = AnnularSector(**self.spec)
        self.k = sector.width / max(ref.width, 1e-6)
        ref.scale(self.k, about_point=ORIGIN)
        self.offset = sector.get_center() - ref.get_center()
        super().__init__(sector, **kw)

    def interpolate_mobject(self, alpha: float) -> None:
        k = rf.ease_out_cubic(alpha)
        new = AnnularSector(**{**self.spec, "angle": self.spec["angle"] * max(k, 1e-3)})
        new.scale(self.k, about_point=ORIGIN).shift(self.offset)
        new.match_style(self.starting_mobject)
        self.mobject.become(new)


class Donut(Piece):
    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 1.4
        return owned(self, AnimationGroup(
            LaggedStart(*(Sweep(s, run_time=run / max(1, len(self.slices_)) * 1.5) for s in self.slices_), lag_ratio=0.7),
            LaggedStart(*(FadeIn(t, run_time=0.4) for t in self.part("labels")), lag_ratio=0.3)))

    def pop(self, name: str, run: float = 0.6):
        """One slice pulled out a little."""
        i = self.names_.index(name)
        s = self.slices_[i]
        mid = self.angles_[i]
        return s.animate(run_time=run).shift(np.array([np.cos(mid), np.sin(mid), 0]) * 0.25)


def donut(data: dict, radius: float = 2.0, thickness: float = 0.7, colors=None, size: float = 22,
          centre: str | None = None, percent: bool = True) -> Donut:
    """A donut of {name: value}, labelled outside with names (and percentages); `centre` words in the hole."""
    look = L()
    total = sum(float(v) for v in data.values()) or 1
    g = Donut()
    g.names_, g.slices_, g.angles_ = list(data), [], []
    labels = VGroup()
    start = PI / 2
    for i, (nm, v) in enumerate(data.items()):
        ang = -2 * PI * float(v) / total
        c = colors[i % len(colors)] if colors else look.color(i)
        s = AnnularSector(inner_radius=radius - thickness, outer_radius=radius, angle=ang, start_angle=start,
                          fill_color=c, fill_opacity=0.95 if look.name == "vox" else 0.45,
                          stroke_color=look.bg if look.name == "vox" else c, stroke_width=3)
        mid = start + ang / 2
        g.angles_.append(mid)
        words = f"{nm}  {round(100 * float(v) / total)}%" if percent else nm
        t = text(words, size=size, color=look.ink, weight=True)
        direction = np.array([np.cos(mid), np.sin(mid), 0])
        t.move_to(direction * (radius + 0.35) + direction * np.array([t.width / 2, t.height / 2, 0]) * 1.05)
        g.add(s)
        g.slices_.append(s)
        labels.add(t)
        start += ang
    g.add(labels)
    g.name_part("labels", labels)
    if centre:
        c = text(centre, size=size * 1.3, role="head", width=(radius - thickness) * 1.6)
        g.add(c)
        g.name_part("centre", c)
    return g


class Units(Piece):
    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 1.4
        anims = [LaggedStart(*(FadeIn(u, scale=0.4, run_time=0.25) for u in self.units_), lag_ratio=0.05,
                             run_time=run)]
        if "label" in self.parts:
            anims.append(FadeIn(self.part("label"), run_time=run * 0.5))
        return owned(self, AnimationGroup(*anims))

    def fill(self, k: int | None = None, color: str | None = None, run: float = 1.0):
        """Colour the first `k` units (default: the count given) one after another."""
        c = color or L().accent
        k = self.marked if k is None else k
        return LaggedStart(*(u.animate(run_time=0.2).set_fill(c, opacity=1) for u in self.units_[:k]),
                           lag_ratio=0.15, run_time=run)


def units(total: int = 100, marked: int = 0, cols: int | None = None, shape: str = "square", size: float = 0.28,
          gap: float = 0.08, color: str | None = None, label: str | None = None, marked_now: bool = False) -> Units:
    """A grid of `total` units; .fill() colours `marked` of them (or marked_now=True colours them from the start).
    shape: square, dot or person."""
    from .people import figure
    look = L()
    cols = cols or int(np.ceil(np.sqrt(total * 1.6)))
    base_c = look.faint if look.name == "vox" else look.muted
    mark_c = color or look.accent
    g = Units()
    g.marked = marked
    g.units_ = []
    for i in range(total):
        if shape == "dot":
            u = Dot(radius=size / 2, color=base_c)
        elif shape == "person":
            u = figure(base_c, height=size * 1.6)
        else:
            u = Rectangle(width=size, height=size, stroke_width=0 if look.name == "vox" else 1.2, stroke_color=look.muted,
                          fill_color=base_c, fill_opacity=1 if look.name == "vox" else 0.2)
        if marked_now and i < marked:
            u.set_fill(mark_c, opacity=1)
        g.units_.append(u)
    grid = VGroup(*g.units_).arrange_in_grid(cols=cols, buff=gap)
    g.add(grid)
    g.name_part("grid", grid)
    if label:
        t = text(label, size=28, weight=True, color=mark_c)
        t.next_to(grid, DOWN, buff=0.3)
        g.add(t)
        g.name_part("label", t)
    return g


class LineChart(Piece):
    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 2.0
        return owned(self, AnimationGroup(FadeIn(self.part("axes"), run_time=run * 0.3),
                                          *(Create(l, run_time=run, rate_func=lambda t: t) for l in self.lines_),
                                          FadeIn(self.part("labels"), run_time=run * 0.5)))


def line_chart(series, width: float = 9.0, height: float = 4.5, x_label: str | None = None,
               y_label: str | None = None, colors=None, size: float = 20, names=None, dots: bool = True) -> LineChart:
    """A line (or several: a list of point lists) of (x, y) points, drawn left to right."""
    look = L()
    many = series and isinstance(series[0][0], (list, tuple))
    lines = series if many else [series]
    xs = [p[0] for s in lines for p in s]
    ys = [p[1] for s in lines for p in s]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(0, min(ys)), max(ys) * 1.1 or 1
    def at(x, y):
        return np.array([-width / 2 + (x - x0) / ((x1 - x0) or 1) * width, -height / 2 + (y - y0) / ((y1 - y0) or 1) * height, 0])
    axes = VGroup(Line(at(x0, y0), at(x1, y0), color=look.ink, stroke_width=2),
                  Line(at(x0, y0), at(x0, y1), color=look.ink, stroke_width=2))
    labels = VGroup()
    years = all(float(x).is_integer() and -3000 < x < 2200 for x in xs)
    for x in np.linspace(x0, x1, min(6, len(set(xs)))):
        t = text(str(int(round(x))) if years else _fmt(x), size=size, role="mono", color=look.muted)
        t.next_to(at(x, y0), DOWN, buff=0.12)
        labels.add(t)
    for y in np.linspace(y0, y1, 4)[1:]:
        t = text(_fmt(round(y) if y1 - y0 > 10 else y), size=size, role="mono", color=look.muted)
        t.next_to(at(x0, y), LEFT, buff=0.12)
        labels.add(t)
    if x_label:
        labels.add(text(x_label, size=size, color=look.muted).next_to(axes[0], DOWN, buff=0.55))
    if y_label:
        labels.add(text(y_label, size=size, color=look.muted).rotate(PI / 2).next_to(axes[1], LEFT, buff=0.75))
    g = LineChart(axes, labels)
    g.name_part("axes", axes)
    g.name_part("labels", labels)
    g.lines_ = []
    for i, s in enumerate(lines):
        c = colors[i % len(colors)] if colors else look.color(i)
        v = VMobject(stroke_color=c, stroke_width=look.stroke * 1.2)
        v.set_points_as_corners([at(x, y) for x, y in s])
        g.add(v)
        g.lines_.append(v)
        if dots:
            g.add(VGroup(*(Dot(at(x, y), radius=0.06, color=c) for x, y in s)))
        if names and i < len(names):
            t = text(names[i], size=size, color=c, weight=True).next_to(at(*s[-1]), RIGHT, buff=0.15)
            labels.add(t)
    return g


class Versus(Piece):
    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 0.6
        l, r = self.part("left"), self.part("right")
        return owned(self, AnimationGroup(FadeIn(l, shift=RIGHT * 0.4, run_time=run), FadeIn(r, shift=LEFT * 0.4, run_time=run),
                                          FadeIn(self.part("vs"), scale=1.6, run_time=run)))


def versus(left_title: str, left_items, right_title: str, right_items, colors=None, width: float = 12.0,
           size: float = 26) -> Versus:
    """Two sides compared: a title and points on each side, a "vs" between."""
    from .cards import panel
    look = L()
    c1, c2 = colors or (look.palette[0], look.palette[2])
    half = width / 2 - 0.5

    def side(title, items, c):
        t = text(title, size=size * 1.4, role="head", color=c, width=half - 0.4)
        rows = VGroup(*(VGroup(Dot(radius=0.06, color=c), text(it, size=size, width=half - 0.8)).arrange(RIGHT, buff=0.2)
                        for it in items)).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
        stack = VGroup(t, rows).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
        p = panel(half, stack.height + 0.7)
        stack.move_to(p.box)
        return VGroup(p, stack)

    l, r = side(left_title, left_items, c1), side(right_title, right_items, c2)
    h = max(l.height, r.height)
    l.move_to(LEFT * (half / 2 + 0.5))
    r.move_to(RIGHT * (half / 2 + 0.5))
    vs = text("vs", size=size * 1.5, role="head", color=look.accent)
    g = Versus(l, r, vs)
    g.name_part("left", l)
    g.name_part("right", r)
    g.name_part("vs", vs)
    return g

