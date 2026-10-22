"""Yet more motion templates (beta: MOTION_ENGINE.md §3): the shapes an explanation takes that a list or a chart does
not -- what overlaps, where things sit between two qualities, what narrows, how far along a scale, which side weighs
more, what lies hidden, what changed, who ranks where. Each builds part by part on the words that name it. A mixin of
motion.MotionLecture (it uses the lecture's template plumbing: _titled, _fit, _show, _hold_back, _moment, _part).

    venn          two or three sets as circles drawn in one by one; what they share named in the overlap
    quadrant      two qualities as axes; things placed in the four fields between them as each is said
    funnel        stages narrowing down, each slid in with its figure as it is named
    gauge         a dial from low to high, its needle swinging to the value as the figure counts up
    scale         a balance: what each side holds dropped onto its pan, the beam tipping to the heavier
    iceberg       what is seen above the waterline, then the much larger part below it as the view sinks
    before_after  a state, then a wipe across it to what it became, the change named on the divide
    ranking       a leaderboard: places come in (from the last up, or the first down), the top one crowned
"""

from __future__ import annotations

import math

import numpy as np
from manim import (DOWN, LEFT, RIGHT, UP, Arc, Circle, DashedLine, Dot, FadeIn, Group, Line, Polygon, Rectangle,
                   RoundedRectangle, Triangle, VGroup)
from manim.utils.rate_functions import ease_out_back, ease_out_cubic, ease_out_expo, smooth

import motion_kit as K
import pocket_lecture as pl
from pocket_lecture import Z_MARK, fit

Z_TEMPLATE = Z_MARK + 10


def _ink(fill: str) -> str:
    try:
        return "#111111" if pl._luminance(str(fill)) > 0.45 else "#FFFFFF"
    except Exception:  # noqa: BLE001
        return "#111111"


def _said(on, *names) -> list[str]:
    if str(on or "").strip():
        return [str(on)]
    return [str(n) for n in names if str(n or "").strip()]


def _spec(item, key: str) -> dict:
    return item if isinstance(item, dict) else {key: str(item)}


class FormTemplates:
    """The templates of this module, as MotionLecture's m_<op> methods."""

    # ---------------------------------------------------------------- venn --------------------------------------
    def m_venn(self, sets, overlap=None, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """Two or three sets ({label, items?, on}) as circles drawn one by one on their words, each named outside and
        its own few items inside; `overlap` ({text, on}) is what they share, written where they all meet."""
        P = pl.P
        specs = [_spec(s, "label") for s in (sets or [])][:3]
        if len(specs) < 2:
            return None
        tid = id or self._next_id("venn")
        n = len(specs)
        r = 2.0
        tones = self._tones(n)
        if n == 2:
            centres = [np.array([-1.25, 0, 0]), np.array([1.25, 0, 0])]
        else:
            centres = [np.array([-1.15, 0.65, 0]), np.array([1.15, 0.65, 0]), np.array([0, -1.3, 0])]
        made = []
        for k, (s, c, tone) in enumerate(zip(specs, centres, tones)):
            ring = Circle(radius=r, stroke_color=tone, stroke_width=5, fill_color=tone, fill_opacity=0.18).move_to(c)
            name = K.head(str(s.get("label", "")), 30, tone)
            fit(name, 3.6)
            out = (c - (sum(centres) / n))
            out = out / (np.linalg.norm(out) or 1)
            name.move_to(c + out * (r + 0.1) + (UP * 0.35 if n == 2 else 0))
            if n == 2:
                name.next_to(ring, UP, buff=0.15)
            inner = VGroup(*[fit(K.body(str(it), 19, P.CREAM, 16), 1.7) for it in (s.get("items") or [])[:3]])
            if len(inner):
                inner.arrange(DOWN, buff=0.12)
                inner.move_to(c + out * r * 0.45)
            made.append((s, ring, name, inner))
        mid = None
        if overlap:
            o = _spec(overlap, "text")
            mid = fit(K.head(str(o.get("text", "")), 22, P.TITLE, upper=False), 1.5 if n == 3 else 1.3)
            mid.move_to(sum(centres) / n + (DOWN * 0.15 if n == 3 else 0))
            plate = RoundedRectangle(width=mid.width + 0.24, height=mid.height + 0.18, corner_radius=0.08, stroke_width=0,
                                     fill_color=K.col("card"), fill_opacity=0.92).move_to(mid)
            mid = VGroup(plate, mid)
        body = VGroup(*[VGroup(ring, name, inner) for _, ring, name, inner in made], *([mid] if mid else []))
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.2)

        def ring_in(ring, name, inner):
            return K.chain([K.together([K.timed(FadeIn(ring, scale=0.6, rate_func=ease_out_back), K.t("base"), "pop"),
                                        K.enter(name, "rise", run=K.t("fast"))]),
                            *([K.stagger([K.enter(i, "fade", run=K.t("fast")) for i in inner], lag=0.3)] if len(inner) else [])])
        s0, ring0, name0, inner0 = made[0]
        entrance = K.stagger([self._title_in(top), ring_in(ring0, name0, inner0)], lag=0.5)
        self._part(tid, s0.get("label"), ring0, point=lambda m=ring0: K.pulse(m, 1.05))
        held = []
        for s, ring, name, inner in made[1:]:
            group = VGroup(ring, name, inner)
            held.append(group)
            self._part(tid, s.get("label"), ring, point=lambda m=ring: K.pulse(m, 1.05))
            self._moment(_said(s.get("on"), s.get("label")), lambda heard, a=ring, b=name, c=inner: ring_in(a, b, c))
        if mid is not None:
            held.append(mid)
            o = _spec(overlap, "text")
            self._part(tid, o.get("text"), mid, point=lambda m=mid: K.pulse(m, 1.1))
            self._moment(_said(o.get("on"), o.get("text")), lambda heard, m=mid: K.slam(m))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, held)
        return anim

    # ---------------------------------------------------------------- quadrant ----------------------------------
    def m_quadrant(self, x, y, items=None, cells=None, title: str | None = None, kicker: str | None = None,
                   id: str | None = None):
        """Two qualities as axes (`x`, `y`: [low end, high end] or {label, low, high}); the four fields between them
        named (`cells`: {tl, tr, bl, br}); each thing ({text, x, y: 0 to 1, on}) dropped at its place as it is said."""
        P = pl.P
        tid = id or self._next_id("quadrant")
        w, h = 8.6, 5.2

        def ends(a):
            if isinstance(a, dict):
                return str(a.get("low", "")), str(a.get("high", "")), str(a.get("label", ""))
            if isinstance(a, (list, tuple)):
                return (str(a[0]) if a else "", str(a[1]) if len(a) > 1 else "", "")
            return "", "", str(a or "")
        xl, xh, xn = ends(x)
        yl, yh, yn = ends(y)
        frame = Rectangle(width=w, height=h, stroke_color=P.MUTED, stroke_width=1.5, fill_opacity=0)
        tones = {"tr": K.col("good"), "tl": K.col("accent"), "br": K.col("second"), "bl": P.MUTED}
        fields = VGroup()
        for key, (sx, sy) in {"tl": (-1, 1), "tr": (1, 1), "bl": (-1, -1), "br": (1, -1)}.items():
            f = Rectangle(width=w / 2, height=h / 2, stroke_width=0, fill_color=tones[key], fill_opacity=0.1)
            f.move_to([sx * w / 4, sy * h / 4, 0])
            fields.add(f)
        xa = Line([-w / 2, 0, 0], [w / 2, 0, 0], stroke_color=P.CREAM, stroke_width=4)
        ya = Line([0, -h / 2, 0], [0, h / 2, 0], stroke_color=P.CREAM, stroke_width=4)
        tips = VGroup(*[Triangle(fill_color=P.CREAM, fill_opacity=1, stroke_width=0).scale(0.12).rotate(a).move_to(p)
                        for a, p in ((-math.pi / 2, [w / 2, 0, 0]), (0, [0, h / 2, 0]))])
        words = VGroup()
        for text, at, edge in ((xl, [-w / 2, -0.3, 0], LEFT), (xh, [w / 2, -0.3, 0], RIGHT),
                               (yl, [0.15, -h / 2 + 0.2, 0], LEFT), (yh, [0.15, h / 2 - 0.2, 0], LEFT)):
            if text:
                m = fit(K.kicker(text, 16, P.MUTED), w / 2 - 0.4)
                m.move_to(at, aligned_edge=edge)
                words.add(m)
        if xn:
            words.add(fit(K.kicker(xn, 18, P.CREAM), w - 1).next_to(frame, DOWN, buff=0.2))
        if yn:
            words.add(fit(K.kicker(yn, 18, P.CREAM), h - 1).rotate(math.pi / 2).next_to(frame, LEFT, buff=0.2))
        names = VGroup()
        for key, (sx, sy) in {"tl": (-1, 1), "tr": (1, 1), "bl": (-1, -1), "br": (1, -1)}.items():
            text = (cells or {}).get(key) if isinstance(cells, dict) else None
            if text:
                m = fit(K.head(str(text), 26, tones[key]), w / 2 - 0.6)
                m.set_opacity(0.85)
                m.move_to([sx * (w / 2 - 0.3 - m.width / 2), sy * (h / 2 - 0.3 - m.height / 2), 0])
                names.add(m)
        made = []
        for k, it in enumerate([_spec(i, "text") for i in (items or [])][:8]):
            def at(v, size):
                try:
                    return (min(1.0, max(0.0, float(v))) - 0.5) * (size - 0.8)
                except (TypeError, ValueError):
                    return {"low": -0.3, "high": 0.3}.get(str(v).lower(), 0.0) * size
            px, py = at(it.get("x", 0.5), w), at(it.get("y", 0.5), h)
            dot = Dot([px, py, 0], radius=0.13, color=K.col("stamp"))
            tag = K.chip(str(it.get("text", "")), K.col("card"), K.col("card_ink"), 17)
            fit(tag, 2.6)
            tag.next_to(dot, RIGHT if px < w / 2 - 2.8 else LEFT, buff=0.12)
            made.append((it, VGroup(dot, tag)))
        body = VGroup(fields, frame, xa, ya, tips, words, names, *[m for _, m in made])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.2)
        entrance = K.stagger([self._title_in(top),
                              K.together([K.draw(xa, run=K.t("base")), K.draw(ya, run=K.t("base")),
                                          K.enter(fields, "fade", run=K.t("base"))]),
                              K.together([K.enter(tips, "fade", run=K.t("fast")),
                                          K.stagger([K.typewriter(m, run=0.5) for m in words], lag=0.2)]),
                              K.stagger([K.enter(m, "pop", run=K.t("fast")) for m in names], lag=0.2) if len(names) else None],
                             lag=0.5)
        for it, m in made:
            self._part(tid, it.get("text"), m, point=lambda m=m: K.pulse(m, 1.15))
            self._moment(_said(it.get("on"), it.get("text")),
                         lambda heard, m=m: K.together([K.timed(FadeIn(m[0], scale=2.5, rate_func=ease_out_back),
                                                                K.t("fast"), "pop"),
                                                        K.enter(m[1], "slide", side="left", run=K.t("base"))]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [m for _, m in made])
        return anim

    # ---------------------------------------------------------------- funnel ------------------------------------
    def m_funnel(self, stages, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """Stages ({label, value?, on}) as bands narrowing downwards, the first widest: each slid in with its figure
        counting as it is named."""
        P = pl.P
        specs = [_spec(s, "label") for s in (stages or [])][:6]
        if len(specs) < 2:
            return None
        tid = id or self._next_id("funnel")
        n = len(specs)
        bh, gap, top_w, bot_w = 0.85, 0.12, 9.0, 2.6
        tones = self._tones(n)
        made = []
        for k, s in enumerate(specs):
            y1 = -k * (bh + gap)
            w1 = top_w - (top_w - bot_w) * k / n
            w0 = top_w - (top_w - bot_w) * (k + 1) / n
            band = Polygon([-w1 / 2, y1, 0], [w1 / 2, y1, 0], [w0 / 2, y1 - bh, 0], [-w0 / 2, y1 - bh, 0],
                           stroke_width=0, fill_color=tones[k], fill_opacity=1)
            name = fit(K.head(str(s.get("label", "")), 24, _ink(tones[k])), w0 - 0.5)
            parts = [band, name]
            if s.get("value") not in (None, ""):
                num = K.counter(str(s["value"]), lambda wds, c=_ink(tones[k]): K.number(wds, 30, c))
                fit(num, 2.2)
                row = VGroup(name, num).arrange(RIGHT, buff=0.35)
                if row.width > w0 - 0.4:
                    row.scale((w0 - 0.4) / row.width)
                row.move_to(band)
                parts = [band, row]
                count = num
            else:
                name.move_to(band)
                count = None
            made.append((s, VGroup(*parts), band, count))
        body = VGroup(*[m for _, m, _, _ in made])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.2)

        def band_in(m, band, count):
            anims = [K.timed(FadeIn(band, shift=DOWN * 0.5, rate_func=ease_out_back), K.t("base"), "pop")]
            if count is None:
                anims.append(K.enter(m[1], "fade", run=K.t("base")))
            else:
                c = count.count_anim(run=K.t("slow"), centre=True)
                anims += [K.enter(m[1][0], "fade", run=K.t("fast")), c if c is not None else K.enter(count, "pop")]
            return K.together(anims)
        s0, m0, b0, c0 = made[0]
        entrance = K.stagger([self._title_in(top), band_in(m0, b0, c0)], lag=0.5)
        for k, (s, m, band, count) in enumerate(made):
            self._part(tid, s.get("label"), m, point=lambda m=m: K.pulse(m, 1.05))
            if k:
                self._moment(_said(s.get("on"), s.get("label")), lambda heard, m=m, b=band, c=count: band_in(m, b, c))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [m for _, m, _, _ in made[1:]])
        return anim

    # ---------------------------------------------------------------- gauge -------------------------------------
    def m_gauge(self, value, min: float = 0, max: float = 100, label: str = "", low: str | None = None,
                high: str | None = None, text: str | None = None, sub: str | None = None, invert: bool = False,
                title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A dial from `min` to `max` (its ends named `low` and `high`), coloured from bad to good (`invert`: good to
        bad): the needle swings from the low end to the value as the figure (`text`, else the value) counts up."""
        P = pl.P
        tid = id or self._next_id("gauge")
        lo, hi = float(min), float(max)
        if hi <= lo:
            hi = lo + 1
        share = float(np.clip((float(value) - lo) / (hi - lo), 0, 1))
        r = 2.6
        bands = VGroup()
        cols = [K.col("bad"), K.col("stamp"), K.col("accent"), K.col("good")]
        if invert:
            cols = cols[::-1]
        for k, c in enumerate(cols):
            a0 = math.pi - math.pi * k / 4
            bands.add(Arc(radius=r, start_angle=a0, angle=-math.pi / 4 + 0.02, stroke_color=c, stroke_width=26))
        ticks = VGroup(*[Line(r * 0.82 * np.array([math.cos(a), math.sin(a), 0]), r * 0.9 * np.array([math.cos(a), math.sin(a), 0]),
                              stroke_color=P.MUTED, stroke_width=2) for a in np.linspace(math.pi, 0, 11)])
        needle = VGroup(Polygon([0, 0.09, 0], [r * 0.86, 0, 0], [0, -0.09, 0], stroke_width=0, fill_color=P.TITLE,
                                fill_opacity=1),
                        Dot(radius=0.17, color=P.TITLE))
        needle.rotate(math.pi, about_point=np.zeros(3))
        figure = text or (f"{float(value):g}")
        num = K.counter(str(figure), lambda w: K.number(w, 60, P.TITLE))
        num.move_to(DOWN * 0.75)
        parts = [bands, ticks, needle, num]
        if low:
            parts.append(fit(K.kicker(str(low), 16, P.MUTED), 2.4).move_to([-r, -0.35, 0]))
        if high:
            parts.append(fit(K.kicker(str(high), 16, P.MUTED), 2.4).move_to([r, -0.35, 0]))
        if label:
            parts.append(fit(K.body(str(label), 26, P.CREAM, 34), 6.5).next_to(num, DOWN, buff=0.25))
        if sub:
            parts.append(fit(K.body(str(sub), 18, P.MUTED, 44), 6.5).next_to(parts[-1], DOWN, buff=0.15))
        body = VGroup(*parts)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.2)
        pivot = needle[1].get_center()
        swing = K.timed(needle.animate(rate_func=ease_out_back).rotate(-math.pi * share, about_point=pivot).build(),
                        K.t("slow") * 1.5, "swish")
        swing.panim_xform = True
        count = num.count_anim(run=K.t("slow") * 1.5, centre=True)
        entrance = K.stagger([self._title_in(top),
                              K.stagger([K.draw(b, run=K.t("fast")) for b in bands], lag=0.3),
                              K.together([K.enter(ticks, "fade", run=K.t("fast")), K.enter(needle, "pop", run=K.t("fast"))]),
                              K.together([swing, count if count is not None else K.enter(num, "pop")]),
                              *[K.enter(m, "rise", run=K.t("fast")) for m in parts[4:]]], lag=0.4)
        self._part(tid, label or figure, needle, point=lambda: K.pulse(num, 1.12))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- scale (a balance) ----------------------------
    def m_scale(self, left, right, tips: str | None = None, title: str | None = None, kicker: str | None = None,
                id: str | None = None):
        """A balance: each side ({title, items: [text | {text, on}], weight?}) its own pan; each item dropped onto its
        pan as it is said; the beam tips to the heavier side (`tips`: left, right or even; else by weight, else by
        how many items) once the last item is down."""
        P = pl.P
        tid = id or self._next_id("scale")
        sides = [_spec(left, "title"), _spec(right, "title")]
        beam_w = 7.2
        post = Line([0, -2.6, 0], [0, 0.3, 0], stroke_color=P.MUTED, stroke_width=8)
        foot = Polygon([-1.1, -2.9, 0], [1.1, -2.9, 0], [0.5, -2.55, 0], [-0.5, -2.55, 0], stroke_width=0,
                       fill_color=P.MUTED, fill_opacity=1)
        beam = Line([-beam_w / 2, 0.3, 0], [beam_w / 2, 0.3, 0], stroke_color=P.CREAM, stroke_width=10)
        pivot = Dot([0, 0.3, 0], radius=0.16, color=K.col("accent"))
        pans, loads, held = [], [], []
        for k, s in enumerate(sides):
            sx = (-1 if k == 0 else 1) * beam_w / 2
            tone = K.col("accent") if k == 0 else K.col("second")
            strings = VGroup(Line([sx, 0.3, 0], [sx - 1.0, -1.3, 0], stroke_color=P.MUTED, stroke_width=2),
                             Line([sx, 0.3, 0], [sx + 1.0, -1.3, 0], stroke_color=P.MUTED, stroke_width=2))
            dish = Arc(radius=1.15, start_angle=-math.pi * 0.1, angle=-math.pi * 0.8, stroke_color=tone,
                       stroke_width=8).move_to([sx, -1.55, 0])
            name = fit(K.head(str(s.get("title", "")), 26, tone), 3.2).move_to([sx, -2.35, 0])
            items = [_spec(i, "text") for i in (s.get("items") or [])][:4]
            stack = VGroup()
            for j, it in enumerate(items):
                chip = K.chip(str(it.get("text", "")), tone, _ink(tone), 16)
                fit(chip, 2.3)
                chip.move_to([sx, -1.1 + j * 0.42, 0])
                stack.add(chip)
                loads.append((it, chip))
            pans.append(VGroup(strings, dish, name, stack))
        body = VGroup(foot, post, beam, pivot, *pans)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        lw = float(sides[0].get("weight") or 0) or len(sides[0].get("items") or [])
        rw = float(sides[1].get("weight") or 0) or len(sides[1].get("items") or [])
        side = str(tips or ("left" if lw > rw else "right" if rw > lw else "even")).lower()
        angle = {"left": 1, "right": -1}.get(side, 0) * 0.16
        centre = pivot.get_center()
        entrance = K.stagger([self._title_in(top),
                              K.together([K.enter(foot, "rise", run=K.t("fast")), K.draw(post, run=K.t("fast"))]),
                              K.together([K.draw(beam, run=K.t("base")), K.enter(pivot, "pop", run=K.t("fast"))]),
                              K.stagger([K.together([K.draw(p[0], run=K.t("fast")), K.draw(p[1], run=K.t("fast")),
                                                     K.enter(p[2], "rise", run=K.t("fast"))]) for p in pans], lag=0.3)],
                             lag=0.4)
        last = len(loads) - 1
        for j, (it, chip) in enumerate(loads):
            held.append(chip)
            self._part(tid, it.get("text"), chip, point=lambda m=chip: K.pulse(m, 1.1))

            def land(heard, chip=chip, final=(j == last)):
                anims = [K.timed(FadeIn(chip, shift=DOWN * 1.2, rate_func=ease_out_back), K.t("base"), "pop")]
                if final and angle:
                    # Every part of the balance turns about the pivot: the pans (and what is on them) stay level.
                    turn = K.timed(beam.animate(rate_func=smooth).rotate(angle, about_point=centre).build(),
                                   K.t("slow"), "swish")
                    turn.panim_xform = True
                    shifts = []
                    for k, p in enumerate(pans):
                        dy = (beam_w / 2) * math.sin(angle) * (-1 if k == 0 else 1) * whole_scale[0]
                        mv = K.timed(p.animate(rate_func=smooth).shift(UP * dy).build(), K.t("slow"))
                        mv.panim_xform = True
                        shifts.append(mv)
                    anims.append(K.together([turn, *shifts]))
                return K.chain(anims)
            self._moment(_said(it.get("on"), it.get("text")), land)
        whole_scale = [beam.get_length() / beam_w]
        for s, p in zip(sides, pans):
            self._part(tid, s.get("title"), p, point=lambda m=p: K.pulse(m, 1.04))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, held)
        return anim

    # ---------------------------------------------------------------- iceberg -----------------------------------
    def m_iceberg(self, above, below, waterline: str | None = None, title: str | None = None,
                  kicker: str | None = None, id: str | None = None):
        """What is seen (`above`: [text | {text, on}]) on the iceberg's tip over the waterline; then the much larger
        part under it (`below`) rising into view as the first hidden thing is said, each hidden thing written on
        the ice as it is named."""
        P = pl.P
        tid = id or self._next_id("iceberg")
        ups = [_spec(i, "text") for i in (above or [])][:3]
        downs = [_spec(i, "text") for i in (below or [])][:5]
        if not downs:
            return None
        ice, deep = "#EAF4FA", "#9CC3DA"
        tip = Polygon([-1.6, 0, 0], [-0.7, 1.2, 0], [0.1, 1.9, 0], [0.9, 0.9, 0], [1.8, 0, 0], stroke_width=0,
                      fill_color=ice, fill_opacity=1)
        mass = Polygon([-1.8, 0, 0], [1.95, 0, 0], [3.4, -1.6, 0], [2.9, -3.6, 0], [1.0, -4.8, 0], [-1.6, -4.5, 0],
                       [-3.3, -2.8, 0], [-3.0, -1.0, 0], stroke_width=0, fill_color=deep, fill_opacity=1)
        sea = Rectangle(width=11.5, height=5.3, stroke_width=0, fill_color=K.col("second"), fill_opacity=0.16)
        sea.move_to([0, -2.65, 0])
        line = DashedLine([-5.75, 0, 0], [5.75, 0, 0], stroke_color=K.col("second"), stroke_width=3, dash_length=0.18)
        tag = fit(K.kicker(str(waterline or "the waterline"), 15, K.col("second")), 3.5)
        tag.move_to([5.6, 0.25, 0], aligned_edge=RIGHT)
        top_words = VGroup(*[fit(K.head(str(u.get("text", "")), 26, "#123047", upper=False), 2.6) for u in ups])
        if len(top_words):
            top_words.arrange(DOWN, buff=0.08).move_to([0.05, 0.8, 0])
            if top_words.height > 1.3:
                top_words.scale(1.3 / top_words.height)
        low_words = VGroup(*[fit(K.head(str(d.get("text", "")), 28, "#0E2A3D", upper=False), 4.8) for d in downs])
        low_words.arrange(DOWN, buff=0.22).move_to([0.05, -2.45, 0])
        if low_words.height > 3.5:
            low_words.scale(3.5 / low_words.height)
        body = VGroup(sea, mass, line, tag, tip, top_words, low_words)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.25)
        entrance = K.stagger([self._title_in(top),
                              K.together([K.enter(sea, "fade", run=K.t("base")), K.draw(line, run=K.t("base")),
                                          K.enter(tag, "fade", run=K.t("fast"))]),
                              K.timed(FadeIn(tip, shift=UP * 0.8, rate_func=ease_out_back), K.t("base"), "pop"),
                              K.stagger([K.enter(m, "pop", run=K.t("fast")) for m in top_words], lag=0.3)], lag=0.4)
        self._part(tid, "above", tip, point=lambda: K.pulse(tip, 1.05))
        for u, m in zip(ups, top_words):
            self._part(tid, u.get("text"), m, point=lambda m=m: K.pulse(m, 1.1))
        first = True
        for d, m in zip(downs, low_words):
            self._part(tid, d.get("text"), m, point=lambda m=m: K.pulse(m, 1.08))
            if first:
                self._moment(_said(d.get("on"), d.get("text")),
                             lambda heard, m=m: K.chain([K.timed(FadeIn(mass, shift=UP * 0.6, rate_func=ease_out_cubic),
                                                                 K.t("slow"), "whoosh"),
                                                         K.enter(m, "rise", run=K.t("fast"))]))
                first = False
            else:
                self._moment(_said(d.get("on"), d.get("text")), lambda heard, m=m: K.enter(m, "rise", run=K.t("base")))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [mass, *low_words])
        return anim

    # ---------------------------------------------------------------- before / after ----------------------------
    def m_before_after(self, before, after, change: str | None = None, title: str | None = None,
                       kicker: str | None = None, id: str | None = None):
        """A state (`before`: {title, points?, value?, file?}) set across the stage; then, on `after`'s words, a bar
        wipes across it and the new state (`after`) takes its place beside the old one, the old one dimmed; `change`
        is written on the divide (an arrow, "1850 → 1900", "after the reform")."""
        P = pl.P
        tid = id or self._next_id("before_after")
        sides = []
        for s, tone, word in ((_spec(before, "title"), P.MUTED, "BEFORE"), (_spec(after, "title"), K.col("accent"), "AFTER")):
            cw = 5.0
            kick = K.kicker(str(s.get("label") or word), 16, tone)
            name = fit(K.head(str(s.get("title", "")), 32, P.TITLE if tone == P.MUTED else tone), cw - 0.4)
            big = K.number(str(s["value"]), 64, tone if tone != P.MUTED else P.TITLE) if s.get("value") else None
            pic = self._pic(s.get("file"), 1.9, cw - 0.4)
            pts = [fit(K.body("• " + str(p.get("text", "") if isinstance(p, dict) else p), 22, P.CREAM, 30), cw - 0.3)
                   for p in (s.get("points") or [])[:4]]
            stack = [m for m in (kick, pic, name, big) if m is not None] + pts
            col = (VGroup if pic is None else Group)(*stack).arrange(DOWN, buff=0.2, aligned_edge=LEFT)
            sides.append((s, col))
        (bs, bcol), (as_, acol) = sides
        bcol.move_to([-3.1, 0, 0])
        acol.move_to([3.1, 0, 0])
        bar = Rectangle(width=0.16, height=max(bcol.height, acol.height) + 0.8, stroke_width=0,
                        fill_color=K.col("stamp"), fill_opacity=1).move_to([0, 0, 0])
        label = None
        if change:
            label = K.chip(str(change), K.col("stamp"), _ink(K.col("stamp")), 18)
            fit(label, 3.0)
            label.move_to(bar.get_top() + DOWN * 0.3)
        group = Group(bcol, acol, bar, *([label] if label else []))
        whole, top = self._titled(group, title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        entrance = K.stagger([self._title_in(top), K.enter(bcol, "rise", run=K.t("base"))], lag=0.5)
        self._part(tid, bs.get("title"), bcol, point=lambda: K.pulse(bcol, 1.04))
        self._part(tid, as_.get("title"), acol, point=lambda: K.pulse(acol, 1.04))
        def wipe(heard):
            # The bar sweeps in from the left across the old state, which steps back as it passes.
            sweep = K.timed(FadeIn(bar, shift=RIGHT * 4.0, rate_func=ease_out_expo), K.t("base"), "whoosh")
            anims = [K.together([sweep, K.fade_to(bcol, 0.45, run=K.t("base"))]),
                     K.timed(FadeIn(acol, shift=LEFT * 1.0, rate_func=ease_out_cubic), K.t("base"), "swish")]
            if label is not None:
                anims.append(K.slam(label))
            return K.chain(anims)
        self._moment(_said(as_.get("on"), as_.get("title")), wipe)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [acol, bar] + ([label] if label else []))
        return anim

    # ---------------------------------------------------------------- ranking -----------------------------------
    def m_ranking(self, items, order: str = "up", unit: str = "", highlight=None, title: str | None = None,
                  kicker: str | None = None, id: str | None = None):
        """A leaderboard: places ({label, value?, note?, on}; the first given is first place), each a row with its
        big place number and, given values, a bar to scale; they come in from the last place up (`order: "up"`, a
        countdown) or from the first down, each on its words; the first place (or `highlight`) crowned."""
        P = pl.P
        specs = [_spec(i, "label") for i in (items or [])][:7]
        if len(specs) < 2:
            return None
        tid = id or self._next_id("ranking")
        n = len(specs)
        vals = []
        for s in specs:
            try:
                vals.append(float(str(s.get("value", "")).replace(",", "").rstrip("%")))
            except ValueError:
                vals.append(None)
        top_v = max([v for v in vals if v is not None] or [0]) or 1
        hot = str(highlight or specs[0].get("label", "")).lower()
        rows = []
        rh, bar_w = 0.78, 5.0
        for k, (s, v) in enumerate(zip(specs, vals)):
            y = -k * (rh + 0.14)
            is_hot = str(s.get("label", "")).lower() == hot
            tone = K.col("stamp") if is_hot else K.col("accent")
            place = K.number(str(k + 1), 40, tone)
            place.move_to([-5.1, y, 0])
            name = fit(K.head(str(s.get("label", "")), 24, P.TITLE if is_hot else P.CREAM), 3.4)
            name.move_to([-4.4, y, 0], aligned_edge=LEFT)
            parts = [place, name]
            bar = None
            if v is not None:
                bar = Rectangle(width=max(0.08, bar_w * v / top_v), height=rh * 0.55, stroke_width=0,
                                fill_color=tone, fill_opacity=0.9)
                bar.move_to([-0.6, y, 0], aligned_edge=LEFT)
                fig = K.number(f"{s.get('value')}{unit}", 22, P.CREAM)
                fig.next_to(bar, RIGHT, buff=0.15)
                parts += [bar, fig]
            elif s.get("note"):
                parts.append(fit(K.body(str(s["note"]), 20, P.MUTED, 40), 5.4).move_to([-0.6, y, 0], aligned_edge=LEFT))
            if is_hot:
                crown = K.chip("★", K.col("stamp"), _ink(K.col("stamp")), 18).next_to(place, LEFT, buff=0.12)
                parts.append(crown)
            rows.append((s, VGroup(*parts), bar))
        body = VGroup(*[r for _, r, _ in rows])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.2)

        def row_in(r, bar):
            anims = [K.timed(FadeIn(VGroup(*[m for m in r if m is not bar]), shift=RIGHT * 0.8, rate_func=ease_out_expo),
                             K.t("base"), "swish")]
            if bar is not None:
                anims.append(K.grow_from(bar, LEFT, run=K.t("base")))
            return K.together(anims)
        seq = list(range(n))[::-1] if str(order).lower() != "down" else list(range(n))
        first = seq[0]
        s0, r0, b0 = rows[first]
        entrance = K.stagger([self._title_in(top), row_in(r0, b0)], lag=0.5)
        for k, (s, r, bar) in enumerate(rows):
            self._part(tid, s.get("label"), r, point=lambda r=r: K.pulse(r, 1.05))
        for k in seq[1:]:
            s, r, bar = rows[k]
            self._moment(_said(s.get("on"), s.get("label")), lambda heard, r=r, bar=bar: row_in(r, bar))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [rows[k][1] for k in seq[1:]])
        return anim
