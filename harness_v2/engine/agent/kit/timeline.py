"""Timelines: an axis of years (BCE written as such), events with stems that never overlap, spans (eras,
dynasties), lifespans in rows below the axis (who lived when, and when they were where), and a "now" marker that
moves along it.

    tl = Timeline(1200, 1950, width=12).shift(UP)    # place (move, scale) the axis first: what is made from it
                                                      # afterwards is laid out where it then stands
    self.play(tl.appear())
    e = tl.event(1869, "Meiji history bureau"); self.play(e.appear())
    s = tl.span(960, 1279, "Song dynasty"); self.play(s.appear())
    p = tl.lifespan("Marco Polo", 1254, 1324, stay=(1274, 1290, "in China")); self.play(p.appear())
    n = tl.marker(1500, "here"); self.play(n.appear()); self.play(n.move(1800))
"""

from __future__ import annotations

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, RIGHT, UP, AnimationGroup, Create, Dot, FadeIn, GrowFromEdge, LaggedStart,
                   Line, Rectangle, RoundedRectangle, Triangle, VGroup)

from .base import Piece
from .layout import FH, FW, overlaps
from .look import L
from .text import label, text


def _overlap_area(a, b, gap: float = 0.1) -> float:
    w = min(a.get_right()[0], b.get_right()[0]) - max(a.get_left()[0], b.get_left()[0]) + gap
    h = min(a.get_top()[1], b.get_top()[1]) - max(a.get_bottom()[1], b.get_bottom()[1]) + gap
    return max(0.0, w) * max(0.0, h)


def year_text(y: float, bce: bool) -> str:
    y = int(round(y))
    if y < 0:
        return f"{-y} BCE"
    return f"{y} CE" if bce and y > 0 and y < 1000 else str(y)


def _nice_step(span: float) -> float:
    for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000):
        if span / s <= 9:
            return s
    return 5000


class Timeline(Piece):
    enter_kind = "line"

    def __init__(self, start: float, end: float, width: float = 12.0, step: float | None = None,
                 labels: bool = True, size: float = 20, color: str | None = None):
        """An axis from `start` to `end` (negative years are BCE), `width` units long, centred at the origin, with
        a tick and its year every `step` years (a round step by default)."""
        super().__init__()
        look = L()
        self.look = look
        self.start, self.end, self.width_ = float(start), float(end), float(width)
        self.bce = start < 0
        c = color or look.ink
        self._ref = VGroup(Dot(ORIGIN, radius=0.001), Dot(RIGHT, radius=0.001), Dot(UP, radius=0.001)).set_opacity(0)
        self.add(self._ref)
        axis = Line(self._local(start), self._local(end), color=c,
                    stroke_width=look.stroke * (1.4 if look.name == "vox" else 0.8))
        self.add(axis)
        self.name_part("axis", axis)
        step = step or _nice_step(end - start)
        ticks, nums = VGroup(), VGroup()
        first = np.ceil(start / step) * step
        for y in np.arange(first, end + 1e-6, step):
            p = self._local(y)
            ticks.add(Line(p + UP * 0.1, p + DOWN * 0.1, color=c, stroke_width=look.stroke * 0.7))
            if labels:
                t = text(year_text(y, self.bce), size=size, role="mono", color=look.muted)
                t.next_to(p, DOWN, buff=0.18)
                nums.add(t)
        self.add(ticks, nums)
        self.name_part("ticks", ticks)
        self.name_part("years", nums)
        self._above: list = []
        self._below: list = list(nums)
        self._rows: list[list[tuple[float, float]]] = []
        self._floor = (nums[0].get_bottom()[1] if len(nums) else -0.3)    # relative to the axis's origin
        self.row_gap = 0.55

    # ---- coordinates
    def _local(self, year: float) -> np.ndarray:
        return np.array([(year - (self.start + self.end) / 2) / (self.end - self.start) * self.width_, 0.0, 0.0])

    def x(self, year: float) -> np.ndarray:
        """Where `year` is on the axis as it now stands."""
        loc = self._local(year)
        o, xx, _ = (d.get_center() for d in self._ref)
        return o + loc[0] * (xx - o)

    def _unit(self):
        o, xx, yy = (d.get_center() for d in self._ref)
        return xx - o, yy - o

    # ---- things on it
    def event(self, year: float, words: str, side: str | None = None, color: str | None = None, size: float = 22,
              width: float = 2.3) -> Piece:
        """A moment: a dot on the axis, a stem, and its words on a card. The card goes above the axis where there is
        room (moved sideways or up until it clears every other label), else below; `side` ("up"/"down") forces one."""
        look = self.look
        c = color or look.accent
        p = self.x(year)
        _, uy = self._unit()
        unit_y = uy / (np.linalg.norm(uy) or 1)
        lab = label(f"{words}", size=size, color=look.ink, backing=True, weight=True) if look.name == "blueprint" \
            else _event_card(words, year_text(year, self.bce), size, width, c)
        box = lab[1] if look.name != "blueprint" else lab          # the card without its shadow
        sides = [side == "up"] if side else [True, False]
        best, least = None, None
        for up in sides:
            others = self._above if up else self._below
            sign = 1 if up else -1
            base = 0.6 if up else 0.75
            for level in (base, base + 0.4, base + 0.8, base + 1.2, base + 1.6, base + 2.0):
                for k in (0, 0.55, -0.55, 1.1, -1.1, 1.65, -1.65, 2.2, -2.2):
                    lab.move_to(p + unit_y * (level + lab.height / 2) * sign + RIGHT * k * lab.width)
                    inside = abs(box.get_left()[0]) < FW / 2 - 0.15 and abs(box.get_right()[0]) < FW / 2 - 0.15 and \
                        abs(box.get_top()[1]) < FH / 2 - 0.1 and abs(box.get_bottom()[1]) < FH / 2 - 0.1
                    if not inside:
                        continue
                    hit = sum(_overlap_area(box, o) for o in others)
                    if hit == 0:
                        best = (up, lab.get_center().copy())
                        break
                    if least is None or hit < least[0]:
                        least = (hit, (up, lab.get_center().copy()))
                if best is not None:
                    break
            if best is not None:
                break
        up, where = best or (least[1] if least else (True, p + unit_y * (0.7 + lab.height / 2)))
        lab.move_to(where)
        (self._above if up else self._below).append(box)
        if not up:
            self._floor = min(self._floor, box.get_bottom()[1] - self._ref[0].get_center()[1])
        edge = box.get_bottom() if up else box.get_top()
        x = min(max(p[0], box.get_left()[0] + 0.15), box.get_right()[0] - 0.15)
        stem = Line(p, [x, edge[1], 0], color=c, stroke_width=2)
        dot = Dot(p, radius=0.09, color=c)
        e = Event(stem, dot, lab)
        e.name_part("dot", dot)
        e.name_part("stem", stem)
        e.name_part("label", lab)
        return e

    def span(self, a: float, b: float, words: str | None = None, color: str | None = None, height: float = 0.32,
             above: bool = True, size: float = 22) -> Piece:
        """A stretch of years (a dynasty, an era) as a band along the axis, with its name over it."""
        look = self.look
        c = color or look.palette[1]
        pa, pb = self.x(a), self.x(b)
        _, uy = self._unit()
        unit_y = uy / (np.linalg.norm(uy) or 1)
        band = Rectangle(width=abs(pb[0] - pa[0]), height=height, stroke_width=0 if look.name == "vox" else 2,
                         stroke_color=c, fill_color=c, fill_opacity=0.85 if look.name == "vox" else 0.3)
        band.move_to((pa + pb) / 2 + unit_y * (height / 2 + 0.02) * (1 if above else -1))
        s = Span(band)
        s.name_part("band", band)
        if words:
            t = text(words, size=size, weight=True, color=look.ink)
            t.next_to(band, UP if above else DOWN, buff=0.1)
            s.add(t)
            s.name_part("label", t)
            (self._above if above else self._below).append(t)
        return s

    def lifespan(self, name: str, a: float, b: float, color: str | None = None, row: int | None = None,
                 stay: tuple | None = None, size: float = 22, years: bool = True) -> Piece:
        """Someone's life as a bar in a row under the axis (rows fill so bars never overlap), the name on it and the
        years at its ends; `stay` = (from, to, words) marks a stretch inside it (when they were somewhere)."""
        look = self.look
        c = color or look.color(sum(len(r) for r in self._rows))
        if row is None:
            row = 0
            while row < len(self._rows) and any(not (b < x0 or a > x1) for x0, x1 in self._rows[row]):
                row += 1
        while len(self._rows) <= row:
            self._rows.append([])
        self._rows[row].append((a - (self.end - self.start) * 0.08, b + (self.end - self.start) * 0.08))
        pa, pb = self.x(a), self.x(b)
        if not hasattr(self, "_row_top"):
            self._row_top = self._floor - 0.45
        y0 = self._row_top - row * self.row_gap
        bar = RoundedRectangle(width=max(0.12, abs(pb[0] - pa[0])), height=0.36, corner_radius=0.08 if look.name == "vox" else 0,
                               stroke_width=0 if look.name == "vox" else 2, stroke_color=c, fill_color=c,
                               fill_opacity=0.9 if look.name == "vox" else 0.35)
        bar.move_to([(pa[0] + pb[0]) / 2, self._ref[0].get_center()[1] + y0, 0])
        n = text(name, size=size, weight=True, color="#FFFFFF" if look.name == "vox" else look.ink)
        name_left = False
        if n.width + 0.2 < bar.width:
            n.move_to(bar)
        else:
            n.next_to(bar, RIGHT, buff=0.12).set_color(look.ink)
            if n.get_right()[0] > FW / 2 - 0.2:
                n.next_to(bar, LEFT, buff=0.12)
                name_left = True
        life = Lifespan(bar, n)
        life.name_part("bar", bar)
        life.name_part("name", n)
        if years:
            ya = text(year_text(a, self.bce), size=size * 0.7, role="mono", color=look.muted)
            yb = text(year_text(b, self.bce), size=size * 0.7, role="mono", color=look.muted)
            inside = n.get_left()[0] >= bar.get_left()[0] - 1e-6 and n.get_right()[0] <= bar.get_right()[0] + 1e-6
            if inside:
                ya.next_to(bar, LEFT, buff=0.1)
                yb.next_to(bar, RIGHT, buff=0.1)
                life.add(ya, yb)
            elif name_left:
                ya = text(f"{year_text(a, self.bce)}–{year_text(b, self.bce)}", size=size * 0.7, role="mono",
                          color=look.muted).next_to(n, DOWN, buff=0.04)
                life.add(ya)
            else:
                ya.next_to(bar, LEFT, buff=0.1)
                life.add(ya)
            life.name_part("years", ya)
        if stay:
            s0, s1 = stay[0], stay[1]
            qa, qb = self.x(s0), self.x(s1)
            hl = Rectangle(width=abs(qb[0] - qa[0]), height=0.5, stroke_color=look.ink if look.name == "vox" else look.accent,
                           stroke_width=3, fill_opacity=0).move_to([(qa[0] + qb[0]) / 2, bar.get_center()[1], 0])
            life.add(hl)
            life.name_part("stay", hl)
            if len(stay) > 2 and stay[2]:
                st = text(stay[2], size=size * 0.75, role="hand" if look.name == "vox" else "mono", color=look.ink)
                st.next_to(hl, DOWN, buff=0.06)
                life.add(st)
                life.name_part("stay_label", st)
        return life

    def marker(self, year: float, words: str | None = None, color: str | None = None) -> "Marker":
        """A pointer on the axis ("we are here"); .move(year) slides it."""
        look = self.look
        c = color or look.accent
        tri = Triangle(fill_color=c, fill_opacity=1, stroke_width=0).scale(0.14).rotate(np.pi)
        tri.move_to(self.x(year) + UP * 0.28)
        m = Marker(tri)
        m.timeline = self
        m.name_part("pointer", tri)
        if words:
            t = text(words, size=20, role="hand" if look.name == "vox" else "mono", color=c)
            t.next_to(tri, UP, buff=0.08)
            m.add(t)
            m.name_part("label", t)
        return m

    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 1.2
        return owned(self, AnimationGroup(
            Create(self.part("axis"), run_time=run),
            LaggedStart(*(FadeIn(t, run_time=0.25) for t in self.part("ticks")), lag_ratio=0.15, run_time=run),
            LaggedStart(*(FadeIn(t, shift=UP * 0.1, run_time=0.3) for t in self.part("years")), lag_ratio=0.15,
                        run_time=run)))


def _event_card(words: str, when: str, size: float, width: float, color) -> VGroup:
    look = L()
    t = text(words, size=size, weight=True, color=look.ink, width=width)
    y = text(when, size=size * 0.8, role="mono", color=color, weight=True)
    stack = VGroup(y, t).arrange(DOWN, aligned_edge=LEFT, buff=0.06)
    box = RoundedRectangle(width=stack.width + 0.3, height=stack.height + 0.24, corner_radius=0.06, stroke_width=0,
                           fill_color=look.card, fill_opacity=1).move_to(stack)
    from .cards import shadow_of
    return VGroup(shadow_of(box), box, stack)


class Event(Piece):
    enter_kind = "shape"

    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 0.7
        return owned(self, LaggedStart(FadeIn(self.part("dot"), scale=0.3, run_time=run * 0.4),
                                       Create(self.part("stem"), run_time=run * 0.5),
                                       FadeIn(self.part("label"), shift=UP * 0.15, run_time=run * 0.6), lag_ratio=0.4))


class Span(Piece):
    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 0.8
        anims = [GrowFromEdge(self.part("band"), LEFT, run_time=run)]
        if "label" in self.parts:
            anims.append(FadeIn(self.part("label"), run_time=run))
        return owned(self, AnimationGroup(*anims))


class Lifespan(Piece):
    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 0.9
        rest = [m for k, m in self.parts.items() if k not in ("bar",)]
        return owned(self, AnimationGroup(GrowFromEdge(self.part("bar"), LEFT, run_time=run),
                                          *(FadeIn(m, run_time=run * 0.6) for m in rest)))


class Marker(Piece):
    def move(self, year: float, run: float = 1.2):
        """Slide the marker to `year`."""
        target = self.timeline.x(year) + UP * 0.28
        return self.animate(run_time=run).shift(target - self.part("pointer").get_center())
