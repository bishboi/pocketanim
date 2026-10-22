"""Motion templates for numbers and explanations (beta: MOTION_ENGINE.md §3): figures that race and re-sort, steps up
and down to a total, shares stacked over time, then-and-now slopes, dot grids side by side, a number broken into its
parts; a picture zoomed into, layers peeled apart, a cycle on a wheel, a checklist against a claim, pros against cons,
a mind map. Each builds part by part on the words that name it. A mixin of motion.MotionLecture.

    race_bars     bars for each thing at each moment (a year), re-sorting and stretching as the moments are said
    waterfall     a start, each gain or loss stepping up or down from the last, then the total
    stacked_area  shares of a whole over time, layer on layer, each swept in from the left as it is named
    slope         then and now on two posts, each thing joined by a line rising or falling, as said
    dot_compare   grids of dots side by side, each one's part filled ("1 in 4" against "1 in 20")
    split_number  a big total that breaks apart into its parts, each a block of a bar with its figure
    zoom_in       a picture, a box round one part; the view pushes in on it and names it as it is said
    layers        a stack of slabs peeled apart one by one, each named
    cycle_wheel   steps round a ring, a pointer travelling to each as it is said
    checklist     a claim, its criteria ticked or crossed one by one, a verdict at the end
    pros_cons     two columns filling as said; the balance leaning to the stronger at the end
    mind_map      an idea at the middle, branches growing out to their ideas (and theirs) as they are named
"""

from __future__ import annotations

import math

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, RIGHT, UP, Circle, Dot, FadeIn, Group, Line, Polygon, Rectangle, RoundedRectangle,
                   Square, Transform, Triangle, VGroup, VMobject)
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


def _num(v, default=None):
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return default


def _fmt(v: float, unit: str = "") -> str:
    text = f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.1f}"
    return f"{text}{unit}"


class ExplainTemplates:
    """The templates of this module, as MotionLecture's m_<op> methods."""

    # ---------------------------------------------------------------- race_bars ---------------------------------
    def m_race_bars(self, frames, unit: str = "", title: str | None = None, kicker: str | None = None,
                    id: str | None = None):
        """Bars for each thing at each moment: `frames` [{at: "1700", values: {name: number}, on}], the first shown
        with the template; at each next moment's words the bars stretch to their new lengths and re-sort, largest at
        the top, the moment's label rolling over in the corner."""
        P = pl.P
        tid = id or self._next_id("race_bars")
        fr = [f for f in (frames or []) if isinstance(f, dict) and isinstance(f.get("values"), dict)][:8]
        if not fr:
            return None
        names = []
        for f in fr:
            for k in f["values"]:
                if k not in names:
                    names.append(k)
        names = names[:8]
        tones = dict(zip(names, self._tones(len(names))))
        most = max([_num(v, 0) or 0 for f in fr for v in f["values"].values()] + [1])
        bw, rh, gap = 7.6, 0.6, 0.18

        def layout(f):
            vals = {n: _num(f["values"].get(n), 0) or 0 for n in names}
            order = sorted(names, key=lambda n: -vals[n])
            rows = {}
            for k, n in enumerate(order):
                y = -k * (rh + gap)
                bar = Rectangle(width=max(0.06, bw * vals[n] / most), height=rh, stroke_width=0, fill_color=tones[n],
                                fill_opacity=1).move_to([-2.6, y, 0], aligned_edge=LEFT)
                name = fit(K.head(str(n), 22, P.CREAM), 2.2).move_to([-2.8, y, 0], aligned_edge=RIGHT)
                fig = K.number(_fmt(vals[n], unit), 22, P.CREAM).next_to(bar, RIGHT, buff=0.15)
                rows[n] = VGroup(name, bar, fig)
            stamp = K.number(str(f.get("at", "")), 64, P.MUTED).move_to([bw - 3.2, -(len(names) - 1) * (rh + gap), 0],
                                                                        aligned_edge=RIGHT)
            return rows, stamp
        rows0, stamp0 = layout(fr[0])
        # An unseen ruler from (0, 0) to (1, 0) in the layout's own units: after the board is fitted to the stage it
        # says how every later moment's layout is to be scaled and moved to stand where this one does.
        ruler = Line([0, 0, 0], [1, 0, 0], stroke_width=0).set_opacity(0)
        board = VGroup(*[rows0[n] for n in names], stamp0, ruler)
        whole, top = self._titled(board, title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        origin, k_scale = ruler.get_start().copy(), float(ruler.get_length())
        entrance = K.stagger([self._title_in(top),
                              K.stagger([K.together([K.enter(rows0[n][0], "fade", run=K.t("fast")),
                                                     K.grow_from(rows0[n][1], LEFT, run=K.t("base")),
                                                     K.enter(rows0[n][2], "fade", run=K.t("fast"))]) for n in names],
                                        lag=0.15),
                              K.enter(stamp0, "pop")], lag=0.4)
        for n in names:
            self._part(tid, n, rows0[n], point=lambda m=rows0[n]: K.pulse(m, 1.05))
        for f in fr[1:]:
            def move(heard, f=f):
                rows, stamp = layout(f)
                VGroup(*[rows[n] for n in names], stamp).scale(k_scale, about_point=np.zeros(3)).shift(origin)
                anims = [Transform(rows0[n], rows[n]) for n in names] + [Transform(stamp0, stamp)]
                return K.baked(K.timed(K.together(anims), K.t("slow") * 1.4, "swish"))
            self._moment(_said(f.get("on"), f.get("at")), move)
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- waterfall ---------------------------------
    def m_waterfall(self, start, steps, total: str | None = "Total", unit: str = "", title: str | None = None,
                    kicker: str | None = None, id: str | None = None):
        """A start (`start`: {label, value}), then each gain or loss (`steps`: {label, value: +n or -n, on}) stepping
        up in green or down in red from where the last left off, joined by dashed ties; the `total` bar at the end."""
        P = pl.P
        tid = id or self._next_id("waterfall")
        st = _spec(start, "label")
        sv = _num(st.get("value"), 0) or 0
        specs = [s for s in (steps or []) if isinstance(s, dict) and _num(s.get("value")) is not None][:8]
        if not specs:
            return None
        levels = [sv]
        for s in specs:
            levels.append(levels[-1] + _num(s["value"]))
        top_v = max(levels + [0]) or 1
        low_v = min(levels + [0])
        span = top_v - low_v or 1
        hgt, n = 4.2, len(specs) + 2
        cw = min(1.3, 11.0 / n - 0.25)

        def y(v):
            return (v - low_v) / span * hgt - hgt / 2
        cols = []
        x = -((n - 1) * (cw + 0.25)) / 2

        def column(label, a, b, tone, fig):
            bar = Rectangle(width=cw, height=max(0.05, abs(y(b) - y(a))), stroke_width=0, fill_color=tone, fill_opacity=1)
            bar.move_to([x, (y(a) + y(b)) / 2, 0])
            lab = fit(K.kicker(str(label), 14, P.CREAM), cw + 0.4).move_to([x, -hgt / 2 - 0.35, 0])
            num = fit(K.number(fig, 20, P.CREAM), cw + 0.3).next_to(bar, UP, buff=0.1)
            return VGroup(bar, lab, num)
        cols.append((st, column(st.get("label", "Start"), 0, sv, K.col("accent"), _fmt(sv, unit)), sv))
        level = sv
        for s in specs:
            x += cw + 0.25
            v = _num(s["value"])
            c = column(s.get("label", ""), level, level + v, K.col("good") if v >= 0 else K.col("bad"),
                       ("+" if v >= 0 else "−") + _fmt(abs(v), unit))
            cols.append((s, c, level + v))
            level += v
        x += cw + 0.25
        cols.append(({"label": total}, column(total or "Total", 0, level, K.col("second"), _fmt(level, unit)), level))
        ties = VGroup()
        for (_, a, va), (_, b, _) in zip(cols, cols[1:-1] + [cols[-1]]):
            ties.add(Line([a[0].get_right()[0], y(va), 0], [b[0].get_left()[0], y(va), 0], stroke_color=P.MUTED,
                          stroke_width=2).set_stroke(opacity=0.7))
        base = Line([-(n * (cw + 0.25)) / 2, y(0), 0], [(n * (cw + 0.25)) / 2, y(0), 0], stroke_color=P.MUTED,
                    stroke_width=2)
        body = VGroup(base, ties, *[c for _, c, _ in cols])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.15)

        def col_in(c, up=True):
            return K.together([K.grow_from(c[0], DOWN if up else UP, run=K.t("base")), K.enter(c[1], "fade", run=K.t("fast")),
                               K.enter(c[2], "pop", run=K.t("fast"))])
        entrance = K.stagger([self._title_in(top), K.draw(base, run=K.t("fast")), col_in(cols[0][1])], lag=0.4)
        for k, (s, c, _) in enumerate(cols):
            self._part(tid, s.get("label"), c, point=lambda m=c: K.pulse(m, 1.06))
            if k == 0:
                continue
            tie = ties[k - 1]
            v = _num(s.get("value"), 1) or 1
            self._moment(_said(s.get("on"), s.get("label")),
                         lambda heard, c=c, tie=tie, up=(v >= 0 or k == len(cols) - 1):
                         K.chain([K.draw(tie, run=K.t("fast")), col_in(c, up)]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [c for _, c, _ in cols[1:]] + list(ties))
        return anim

    # ---------------------------------------------------------------- stacked_area ------------------------------
    def m_stacked_area(self, series, years, unit: str = "", title: str | None = None, kicker: str | None = None,
                       id: str | None = None):
        """Shares of a whole over time: `series` [{label, values, on}] stacked one on another over `years`, each layer
        swept in from the left as it is named, its name on it."""
        P = pl.P
        tid = id or self._next_id("stacked_area")
        xs = [str(y) for y in (years or [])][:24]
        specs = [s for s in (series or []) if isinstance(s, dict) and isinstance(s.get("values"), list)][:6]
        if len(xs) < 2 or not specs:
            return None
        m = len(xs)
        vals = [[_num(v, 0) or 0 for v in (s["values"] + [0] * m)[:m]] for s in specs]
        tot = [sum(col) for col in zip(*vals)]
        most = max(tot + [1])
        w, h = 9.6, 4.4
        X = [-w / 2 + w * i / (m - 1) for i in range(m)]
        base = [0.0] * m
        tones = self._tones(len(specs))
        layers = []
        for s, row, tone in zip(specs, vals, tones):
            topv = [b + v for b, v in zip(base, row)]
            pts = [[X[i], -h / 2 + h * topv[i] / most, 0] for i in range(m)] + \
                  [[X[i], -h / 2 + h * base[i] / most, 0] for i in reversed(range(m))]
            area = Polygon(*pts, stroke_color=tone, stroke_width=2, fill_color=tone, fill_opacity=0.85)
            j = int(np.argmax([t - b for t, b in zip(topv, base)]))
            mid = [X[j] if 0 < j < m - 1 else X[m // 2], -h / 2 + h * (topv[j] + base[j]) / 2 / most, 0]
            name = fit(K.head(str(s.get("label", "")), 20, _ink(tone)), 2.6).move_to(mid)
            layers.append((s, VGroup(area, name)))
            base = topv
        axis = Line([-w / 2, -h / 2, 0], [w / 2, -h / 2, 0], stroke_color=P.MUTED, stroke_width=2)
        ticks = VGroup(*[fit(K.kicker(xs[i], 13, P.MUTED), 1.2).move_to([X[i], -h / 2 - 0.3, 0])
                         for i in range(m) if i in (0, m - 1) or (m <= 8) or i % max(1, m // 6) == 0])
        body = VGroup(axis, ticks, *[l for _, l in layers])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.15)

        def sweep(layer):
            return K.together([K.grow_from(layer[0], LEFT, run=K.t("slow")), K.enter(layer[1], "fade", run=K.t("base"))])
        entrance = K.stagger([self._title_in(top), K.draw(axis, run=K.t("fast")), K.enter(ticks, "fade"),
                              sweep(layers[0][1])], lag=0.35)
        for k, (s, layer) in enumerate(layers):
            self._part(tid, s.get("label"), layer, point=lambda m=layer: K.pulse(m, 1.03))
            if k:
                self._moment(_said(s.get("on"), s.get("label")), lambda heard, m=layer: sweep(m))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [l for _, l in layers[1:]])
        return anim

    # ---------------------------------------------------------------- slope -------------------------------------
    def m_slope(self, items, left_label: str = "Then", right_label: str = "Now", unit: str = "",
                title: str | None = None, kicker: str | None = None, id: str | None = None):
        """Then and now on two posts: each thing ({label, from, to, on}) a dot on each post joined by a line, green
        rising or red falling, drawn as it is said, its figures at the ends."""
        P = pl.P
        tid = id or self._next_id("slope")
        specs = [s for s in (items or []) if isinstance(s, dict) and _num(s.get("from")) is not None
                 and _num(s.get("to")) is not None][:7]
        if not specs:
            return None
        allv = [_num(s["from"]) for s in specs] + [_num(s["to"]) for s in specs]
        lo, hi = min(allv), max(allv)
        span = hi - lo or 1
        h, xl, xr = 4.2, -2.6, 2.6

        def y(v):
            return (v - lo) / span * h - h / 2
        posts = VGroup(Line([xl, -h / 2 - 0.2, 0], [xl, h / 2 + 0.2, 0], stroke_color=P.MUTED, stroke_width=3),
                       Line([xr, -h / 2 - 0.2, 0], [xr, h / 2 + 0.2, 0], stroke_color=P.MUTED, stroke_width=3))
        heads = VGroup(fit(K.head(str(left_label), 26, P.CREAM), 2.6).move_to([xl, h / 2 + 0.65, 0]),
                       fit(K.head(str(right_label), 26, P.CREAM), 2.6).move_to([xr, h / 2 + 0.65, 0]))
        made = []
        for s in specs:
            a, b = _num(s["from"]), _num(s["to"])
            tone = K.col("good") if b > a else K.col("bad") if b < a else P.MUTED
            pa, pb = [xl, y(a), 0], [xr, y(b), 0]
            line = Line(pa, pb, stroke_color=tone, stroke_width=6)
            da, db = Dot(pa, radius=0.11, color=tone), Dot(pb, radius=0.11, color=tone)
            la = fit(K.body(f"{s.get('label', '')} {_fmt(a, unit)}", 18, P.CREAM, 40), 3.2).next_to(da, LEFT, buff=0.15)
            lb = fit(K.number(_fmt(b, unit), 20, tone), 1.8).next_to(db, RIGHT, buff=0.15)
            made.append((s, VGroup(line, da, db, la, lb)))
        body = VGroup(posts, heads, *[m for _, m in made])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.15)

        def draw_in(m):
            return K.chain([K.together([K.enter(m[1], "pop", run=K.t("fast")), K.enter(m[3], "fade", run=K.t("fast"))]),
                            K.draw(m[0], run=K.t("base")),
                            K.together([K.enter(m[2], "pop", run=K.t("fast")), K.enter(m[4], "pop", run=K.t("fast"))])])
        entrance = K.stagger([self._title_in(top), K.together([K.draw(posts, run=K.t("base")), K.enter(heads, "rise")]),
                              draw_in(made[0][1])], lag=0.4)
        for k, (s, m) in enumerate(made):
            self._part(tid, s.get("label"), m, point=lambda m=m: K.pulse(m[0], 1.06))
            if k:
                self._moment(_said(s.get("on"), s.get("label")), lambda heard, m=m: draw_in(m))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [m for _, m in made[1:]])
        return anim

    # ---------------------------------------------------------------- dot_compare -------------------------------
    def m_dot_compare(self, groups, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """Grids of dots side by side (two to four groups, {label, part, total: 100 or less, on}), each grid's part
        filling in its colour as it is said, its share written under it ("1 in 4")."""
        P = pl.P
        tid = id or self._next_id("dot_compare")
        specs = [g for g in (groups or []) if isinstance(g, dict) and _num(g.get("part")) is not None][:4]
        if not specs:
            return None
        tones = self._tones(len(specs))
        made = []
        for g, tone in zip(specs, tones):
            total = int(max(1, min(100, _num(g.get("total"), 100) or 100)))
            part = int(max(0, min(total, round(_num(g["part"], 0) or 0))))
            cols = 10 if total > 25 else 5
            dots = VGroup(*[Circle(radius=0.1, stroke_width=0, fill_color=P.MUTED, fill_opacity=0.35) for _ in range(total)])
            dots.arrange_in_grid(cols=cols, buff=0.08)
            lit = VGroup(*[d.copy().set_fill(tone, opacity=1) for d in list(dots)[:part]])
            share = g.get("text") or f"{part} in {total}"
            lab = VGroup(fit(K.number(str(share), 30, tone), 3.0), fit(K.body(str(g.get("label", "")), 20, P.CREAM, 24), 3.0))
            lab.arrange(DOWN, buff=0.1).next_to(dots, DOWN, buff=0.3)
            made.append((g, VGroup(dots, lit, lab)))
        body = VGroup(*[m for _, m in made]).arrange(RIGHT, buff=1.0, aligned_edge=UP)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.2)

        def fill(m):
            return K.chain([K.stagger([K.timed(FadeIn(d, scale=0.3, rate_func=ease_out_back), 0.2) for d in m[1]],
                                      run=K.t("slow")) if len(m[1]) else K.enter(m[2], "pop"),
                            K.enter(m[2], "rise", run=K.t("fast"))])
        entrance = K.stagger([self._title_in(top),
                              K.stagger([K.enter(m[0], "fade", run=K.t("base")) for _, m in made], lag=0.2),
                              fill(made[0][1])], lag=0.4)
        for k, (g, m) in enumerate(made):
            self._part(tid, g.get("label"), m, point=lambda m=m: K.pulse(m, 1.05))
            if k:
                self._moment(_said(g.get("on"), g.get("label")), lambda heard, m=m: fill(m))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [VGroup(m[1], m[2]) for _, m in made[1:]])
        return anim

    # ---------------------------------------------------------------- split_number ------------------------------
    def m_split_number(self, value, parts, label: str = "", unit: str = "", title: str | None = None,
                       kicker: str | None = None, id: str | None = None):
        """A big total (`value`, its `label` under it) over a bar; the bar breaks apart into its `parts`
        ({label, value, on}), each block sized to its share and named with its figure as it is said."""
        P = pl.P
        tid = id or self._next_id("split_number")
        specs = [p for p in (parts or []) if isinstance(p, dict) and _num(p.get("value")) is not None][:6]
        if not specs:
            return None
        total = _num(value) or sum(_num(p["value"]) for p in specs) or 1
        big = K.counter(str(value), lambda w: K.number(w, 96, P.TITLE))
        lab = fit(K.body(str(label), 26, P.CREAM, 40), 8) if label else None
        bw, bh = 10.0, 0.9
        whole_bar = Rectangle(width=bw, height=bh, stroke_width=0, fill_color=K.col("accent"), fill_opacity=0.25)
        tones = self._tones(len(specs))
        blocks, x = [], -bw / 2
        for p, tone in zip(specs, tones):
            w = max(0.15, bw * (_num(p["value"]) / total))
            blk = Rectangle(width=w - 0.06, height=bh, stroke_width=0, fill_color=tone, fill_opacity=1)
            blk.move_to([x + w / 2, 0, 0])
            tag = VGroup(fit(K.number(_fmt(_num(p["value"]), unit), 22, tone), max(1.0, w + 0.6)),
                         fit(K.kicker(str(p.get("label", "")), 13, P.CREAM), max(1.0, w + 0.6))).arrange(DOWN, buff=0.06)
            tag.next_to(blk, DOWN, buff=0.2)
            blocks.append((p, VGroup(blk, tag)))
            x += w
        stack = VGroup(big, *([lab] if lab else [])).arrange(DOWN, buff=0.15)
        stack.next_to(whole_bar, UP, buff=0.5)
        # The tags alternate high and low when blocks are narrow, so their words do not run into each other.
        for k, (_, b) in enumerate(blocks):
            if k % 2 and b[0].width < 2.0:
                b[1].shift(DOWN * 0.75)
        body = VGroup(stack, whole_bar, *[b for _, b in blocks])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        count = big.count_anim(run=K.t("slow"), centre=True)
        entrance = K.stagger([self._title_in(top), K.together([count if count is not None else K.enter(big, "pop"),
                                                               K.grow_from(whole_bar, LEFT, run=K.t("slow"))]),
                              *([K.enter(lab, "rise")] if lab else [])], lag=0.4)
        for p, b in blocks:
            self._part(tid, p.get("label"), b, point=lambda m=b: K.pulse(m, 1.05))
            self._moment(_said(p.get("on"), p.get("label")),
                         lambda heard, m=b: K.chain([K.timed(FadeIn(m[0], shift=UP * 0.4, rate_func=ease_out_back),
                                                             K.t("base"), "pop"), K.enter(m[1], "rise", run=K.t("fast"))]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [b for _, b in blocks])
        return anim

    # ---------------------------------------------------------------- zoom_in -----------------------------------
    def m_zoom_in(self, file: str | None = None, box=None, label: str = "", note: str | None = None, on: str | None = None,
                  title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A picture; on `on` a box is drawn round one part of it (`box`: [x0, y0, x1, y1] from 0 to 1 across and
        down) and the view pushes in on that part, its `label` (and `note`) set beside it."""
        P = pl.P
        tid = id or self._next_id("zoom_in")
        pic = self._pic(file, 5.2, 9.5)
        if pic is None:
            return None
        bx = [float(v) for v in (box or [0.35, 0.35, 0.65, 0.65])][:4]
        x0, y0, x1, y1 = [min(1.0, max(0.0, v)) for v in bx]
        whole, top = self._titled(Group(pic), title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        lo, hi = pic.get_corner(DOWN + LEFT), pic.get_corner(UP + RIGHT)
        W, H = hi[0] - lo[0], hi[1] - lo[1]
        c = np.array([lo[0] + W * (x0 + x1) / 2, hi[1] - H * (y0 + y1) / 2, 0])
        bw, bh = max(0.3, W * (x1 - x0)), max(0.3, H * (y1 - y0))
        frame = pl.hud_frame(bw, bh, K.col("stamp")).move_to(c)
        frame.set_z_index(Z_TEMPLATE + 3)
        k = min(2.6, 0.55 * self.STAGE[2] / bw, 0.6 * self.STAGE[3] / bh)
        target = np.array([self.STAGE[0] - self.STAGE[2] * 0.12, self.STAGE[1], 0])
        tag_words = [fit(K.head(str(label), 28, _ink(K.col("stamp"))), 4)] if label else []
        tag = None
        if tag_words:
            tag = K.chip(str(label), K.col("stamp"), _ink(K.col("stamp")), 22)
            if note:
                tag = VGroup(tag, fit(K.body(str(note), 20, P.CREAM, 30), 4.2)).arrange(DOWN, buff=0.15, aligned_edge=LEFT)
            tag.move_to([self.STAGE[0] + self.STAGE[2] * 0.33, self.STAGE[1], 0])
            tag.set_z_index(Z_TEMPLATE + 4)
        entrance = K.stagger([self._title_in(top), K.enter(pic, None)], lag=0.4)
        self._part(tid, label or "picture", pic, point=lambda: K.pulse(frame, 1.08))
        import stem

        def push(heard):
            moving = Group(pic, frame)
            push_in = stem._moving(moving.animate(rate_func=smooth).scale(k, about_point=c).shift(target - c))
            steps = [K.timed(FadeIn(frame, scale=1.3, rate_func=ease_out_back), K.t("fast"), "tick"),
                     K.timed(push_in, K.t("slow") * 1.4, "whoosh")]
            if tag is not None:
                steps.append(K.enter(tag, "slide", side="right"))
            return K.chain(steps)
        self._moment(_said(on, label), push)
        anim = self._show(tid, whole, entrance)
        self.stage_pending.append(frame)
        if tag is not None:
            self.stage_pending.append(tag)
        return anim

    # ---------------------------------------------------------------- layers ------------------------------------
    def m_layers(self, layers, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A stack of slabs seen from above at an angle (`layers` [{label, note?, on}], the top one first), lying
        together; each is lifted apart from the one under it and named as it is said."""
        P = pl.P
        tid = id or self._next_id("layers")
        specs = [_spec(l, "label") for l in (layers or [])][:6]
        if len(specs) < 2:
            return None
        n = len(specs)
        tones = self._tones(n)
        sw, sd, th = 4.6, 1.3, 0.28
        slabs = []
        for k, (s, tone) in enumerate(zip(specs, tones)):
            top_face = Polygon([-sw / 2, 0, 0], [0, sd / 2, 0], [sw / 2, 0, 0], [0, -sd / 2, 0], stroke_color="#00000033",
                               stroke_width=1, fill_color=tone, fill_opacity=1)
            front_l = Polygon([-sw / 2, 0, 0], [0, -sd / 2, 0], [0, -sd / 2 - th, 0], [-sw / 2, -th, 0], stroke_width=0,
                              fill_color=pl._tint_on_bg(tone, 0.7) if hasattr(pl, "_tint_on_bg") else tone, fill_opacity=1)
            front_r = Polygon([sw / 2, 0, 0], [0, -sd / 2, 0], [0, -sd / 2 - th, 0], [sw / 2, -th, 0], stroke_width=0,
                              fill_color=tone, fill_opacity=0.75)
            slab = VGroup(front_l, front_r, top_face)
            words = fit(K.head(str(s.get("label", "")), 22, P.CREAM), 3.4)
            note = fit(K.body(str(s["note"]), 17, P.MUTED, 34), 3.6) if s.get("note") else None
            tag = VGroup(words, *([note] if note else [])).arrange(DOWN, buff=0.06, aligned_edge=LEFT)
            slabs.append((s, slab, tag))
        gap0, gap1 = th + 0.02, 1.15
        for k, (s, slab, tag) in enumerate(slabs):
            slab.move_to([-1.6, (n - 1 - k) * gap0, 0])
            slab.set_z_index(Z_TEMPLATE + (n - k) * 0.01)
        body = VGroup(*[VGroup(slab, tag) for _, slab, tag in slabs])
        # Laid out opened, to fit the stage that way; then closed again for the start.
        opened = [np.array([-1.6, ((n - 1) / 2 - k) * gap1, 0]) for k in range(n)]
        for k, (s, slab, tag) in enumerate(slabs):
            slab.move_to(opened[k])
            tag.next_to(slab, RIGHT, buff=0.6)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        open_pos = [slab.get_center().copy() for _, slab, _ in slabs]
        mid = sum(open_pos) / n
        closed = [mid + (open_pos[k] - mid) * (gap0 / gap1) for k in range(n)]
        for k, (_, slab, _) in enumerate(slabs):
            slab.move_to(closed[k])
        entrance = K.stagger([self._title_in(top), K.stagger([K.enter(slab, "rise", run=K.t("fast"))
                                                              for _, slab, _ in slabs[::-1]], lag=0.2)], lag=0.4)
        import stem
        for k, (s, slab, tag) in enumerate(slabs):
            self._part(tid, s.get("label"), slab, point=lambda m=slab: K.pulse(m, 1.05))
            lift = stem._moving(slab.animate(rate_func=ease_out_cubic).shift(open_pos[k] - closed[k]))
            self._moment(_said(s.get("on"), s.get("label")),
                         lambda heard, lift=lift, tag=tag: K.chain([K.timed(lift, K.t("base"), "swish"),
                                                                    K.enter(tag, "slide", side="left", run=K.t("fast"))]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [tag for _, _, tag in slabs])
        return anim

    # ---------------------------------------------------------------- cycle_wheel -------------------------------
    def m_cycle_wheel(self, steps, center: str | None = None, title: str | None = None, kicker: str | None = None,
                      id: str | None = None):
        """Steps ({label, on}) round a ring with arrows between them, `center` written in the middle; a pointer
        travels round to each step as it is said, lighting it."""
        P = pl.P
        tid = id or self._next_id("cycle_wheel")
        specs = [_spec(s, "label") for s in (steps or [])][:8]
        if len(specs) < 3:
            return None
        n = len(specs)
        r = 2.35
        ring = Circle(radius=r, stroke_color=P.MUTED, stroke_width=3).set_stroke(opacity=0.5)
        nodes = []
        for k, s in enumerate(specs):
            a = math.pi / 2 - 2 * math.pi * k / n
            p = np.array([r * math.cos(a), r * math.sin(a), 0])
            words = fit(K.head(str(s.get("label", "")), 20, K.col("card_ink")), 2.2)
            face = RoundedRectangle(width=words.width + 0.5, height=words.height + 0.4, corner_radius=0.12, stroke_width=2,
                                    stroke_color=K.col("card_stroke"), fill_color=K.col("card"), fill_opacity=1)
            node = VGroup(face, words.move_to(face)).move_to(p)
            nodes.append((s, node, a))
        arrows = VGroup()
        for k in range(n):
            a0, a1 = nodes[k][2], nodes[(k + 1) % n][2]
            mid = (a0 + (a1 - a0 if a1 < a0 else a1 - a0 - 2 * math.pi) / 2)
            tip = Triangle(fill_color=K.col("accent"), fill_opacity=1, stroke_width=0).scale(0.13)
            tip.rotate(mid - math.pi).move_to([r * math.cos(mid), r * math.sin(mid), 0])
            arrows.add(tip)
        pointer = Dot(radius=0.2, color=K.col("accent")).move_to(nodes[0][1].get_center() + DOWN * 0.0)
        hub = None
        if center:
            hub = fit(K.head(str(center), 30, P.TITLE), 2.6)
        body = VGroup(ring, arrows, *[nd for _, nd, _ in nodes], *([hub] if hub is not None else []))
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        cen = ring.get_center()
        # On the ring's inside, by the first step (not over its name); it turns about the middle from step to step.
        pointer.move_to(cen + (nodes[0][1].get_center() - cen) * 0.68)
        pointer.set_z_index(Z_TEMPLATE + 3)
        entrance = K.stagger([self._title_in(top), K.draw(ring, run=K.t("base")),
                              K.stagger([K.enter(nd, "pop", run=K.t("fast")) for _, nd, _ in nodes], lag=0.15),
                              K.enter(arrows, "fade"), *([K.enter(hub, "rise")] if hub is not None else [])], lag=0.35)
        for k, (s, nd, a) in enumerate(nodes):
            self._part(tid, s.get("label"), nd, point=lambda m=nd: K.pulse(m, 1.1))
            if k == 0:
                # The pointer comes to the first step (no pulse: said with the line's start, a pulse fought the
                # step's own coming on and left it hidden).
                self._moment(_said(s.get("on"), s.get("label")),
                             lambda heard: K.enter(pointer, "pop", run=K.t("fast")))
                continue
            step = -2 * math.pi / n
            spot = cen + (nd.get_center() - cen) * 0.68

            def go(heard, nd=nd, step=step, spot=spot):
                # Round the ring to its step (an arc of the step's angle between two points of a circle about the
                # middle is that circle), worked out as it starts: a Rotate from where the pointer stood as it began
                # came on with it in a short line, and left it unseen.
                turn = K.baked(K.timed(K.fresh(pointer.animate(rate_func=smooth, path_arc=step).move_to(spot).build()),
                                       K.t("base"), "swish"))
                return K.chain([turn, K.pulse(nd, 1.15)])
            self._moment(_said(s.get("on"), s.get("label")), go)
        anim = self._show(tid, whole, entrance)
        self.stage_pending.append(pointer)
        return anim

    # ---------------------------------------------------------------- checklist ---------------------------------
    def m_checklist(self, claim: str, criteria, verdict: str | None = None, title: str | None = None,
                    kicker: str | None = None, id: str | None = None):
        """A claim set at the top; its criteria ({text, met: true/false, on}) under it, each ticked or crossed as it
        is said; the `verdict` stamped at the end."""
        P = pl.P
        tid = id or self._next_id("checklist")
        specs = [_spec(c, "text") for c in (criteria or [])][:6]
        if not specs:
            return None
        head = fit(K.head(pl.wrap(str(claim), 34), 32, P.TITLE, upper=False), 9.5)
        rows = []
        for c in specs:
            box = Square(side_length=0.48, stroke_color=P.CREAM, stroke_width=3, fill_opacity=0)
            words = fit(K.body(str(c.get("text", "")), 26, P.CREAM, 44), 8.0)
            met = c.get("met", True)
            met = not (str(met).lower() in ("false", "no", "0", "none") or met is False)
            sign = K.check_mark(0.42, K.col("good")) if met else K.cross_mark(0.36, K.col("bad"))
            sign.move_to(box)
            row = VGroup(box, words).arrange(RIGHT, buff=0.35)
            rows.append((c, row, sign))
        block = VGroup(*[r for _, r, _ in rows]).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        body = VGroup(head, block).arrange(DOWN, buff=0.5, aligned_edge=LEFT)
        for c, row, sign in rows:
            sign.move_to(row[0])
        signs = VGroup(*[s for _, _, s in rows])
        stamp = None
        if verdict:
            stamp = K.stamp(str(verdict), K.col("stamp"), angle=-10, size=44)
            fit(stamp, 4.0)
            # Beside the criteria, by the last: over them it hid the very words it judged.
            stamp.next_to(block, RIGHT, buff=0.6).align_to(block, DOWN)
        whole, top = self._titled(VGroup(body, signs, *([stamp] if stamp is not None else [])), title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        entrance = K.stagger([self._title_in(top), K.typewriter(head, run=0.8),
                              K.stagger([K.enter(r, "fade", run=K.t("fast")) for _, r, _ in rows], lag=0.2)], lag=0.4)
        last = len(rows) - 1
        for k, (c, row, sign) in enumerate(rows):
            self._part(tid, c.get("text"), row, point=lambda m=row: K.pulse(m, 1.05))

            def tick(heard, sign=sign, final=(k == last)):
                steps = [K.draw(sign, run=K.t("fast"), sfx="tick")]
                if final and stamp is not None:
                    steps.append(K.slam(stamp))
                return K.chain(steps)
            self._moment(_said(c.get("on"), c.get("text")), tick)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, list(signs) + ([stamp] if stamp is not None else []))
        if stamp is not None:
            stamp.set_z_index(Z_TEMPLATE + 4)
        return anim

    # ---------------------------------------------------------------- pros_cons ---------------------------------
    def m_pros_cons(self, pros, cons, lean: str | None = None, verdict: str | None = None, title: str | None = None,
                    kicker: str | None = None, id: str | None = None):
        """Two columns, FOR and AGAINST: each point ({text, on}) dropped into its column as it is said; at the end a
        bar under them leans to the stronger side (`lean`: pros, cons or even; else the longer column), with the
        `verdict` on it."""
        P = pl.P
        tid = id or self._next_id("pros_cons")
        ps, cs = [_spec(p, "text") for p in (pros or [])][:5], [_spec(c, "text") for c in (cons or [])][:5]
        if not ps and not cs:
            return None
        cw = 5.2
        cols, items = [], []
        for name, specs, tone, sign in (("FOR", ps, K.col("good"), "+"), ("AGAINST", cs, K.col("bad"), "−")):
            head = VGroup(Rectangle(width=cw, height=0.7, stroke_width=0, fill_color=tone, fill_opacity=1),
                          K.head(name, 26, _ink(tone)))
            head[1].move_to(head[0])
            rows = []
            for s in specs:
                mark = K.head(sign, 30, tone)
                words = fit(K.body(str(s.get("text", "")), 22, P.CREAM, 30), cw - 0.8)
                rows.append((s, VGroup(mark, words).arrange(RIGHT, buff=0.25, aligned_edge=UP)))
            col = VGroup(head, *[r for _, r in rows]).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
            for _, r in rows:
                r.shift(RIGHT * 0.2)
            cols.append(col)
            items += rows
        pair = VGroup(*cols).arrange(RIGHT, buff=0.8, aligned_edge=UP)
        side = str(lean or ("pros" if len(ps) > len(cs) else "cons" if len(cs) > len(ps) else "even")).lower()
        beam = Line([-cw, 0, 0], [cw, 0, 0], stroke_color=P.CREAM, stroke_width=8)
        pivot = Triangle(fill_color=P.MUTED, fill_opacity=1, stroke_width=0).scale(0.3).next_to(beam, DOWN, buff=0)
        verdict_m = fit(K.chip(str(verdict), K.col("accent"), _ink(K.col("accent")), 20), 4.0) if verdict else None
        bal = VGroup(beam, pivot, *([verdict_m.next_to(pivot, DOWN, buff=0.2)] if verdict_m else []))
        bal.next_to(pair, DOWN, buff=0.7)
        body = VGroup(pair, bal)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        angle = {"pros": 0.12, "cons": -0.12}.get(side, 0.0)
        entrance = K.stagger([self._title_in(top), K.stagger([K.enter(c[0], "drop", run=K.t("base")) for c in cols], lag=0.3),
                              K.together([K.draw(beam, run=K.t("base")), K.enter(pivot, "fade")])], lag=0.4)
        for s, r in items:
            self._part(tid, s.get("text"), r, point=lambda m=r: K.pulse(m, 1.06))
            self._moment(_said(s.get("on"), s.get("text")), lambda heard, m=r: K.enter(m, "drop", run=K.t("base")))
        tilt_at = (items[-1][0].get("on") or items[-1][0].get("text")) if items else None
        if angle or verdict_m is not None:
            def tilt(heard):
                steps = []
                if angle:
                    t = K.timed(beam.animate(rate_func=ease_out_back).rotate(angle, about_point=beam.get_center()).build(),
                                K.t("slow"), "swish")
                    t.panim_xform = True
                    steps.append(t)
                if verdict_m is not None:
                    steps.append(K.enter(verdict_m, "pop"))
                return K.chain(steps)
            self._moment(_said(tilt_at), tilt)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [r for _, r in items] + ([verdict_m] if verdict_m is not None else []))
        return anim

    # ---------------------------------------------------------------- mind_map ----------------------------------
    def m_mind_map(self, center, branches, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """An idea at the middle (`center`); `branches` ({label, on, children?: [text]}) growing out round it as
        curved stems, each idea in a coloured pill, its own smaller ideas budding off it."""
        P = pl.P
        tid = id or self._next_id("mind_map")
        specs = [_spec(b, "label") for b in (branches or [])][:8]
        if not specs:
            return None
        c = _spec(center, "text")
        core_words = fit(K.head(str(c.get("text", "")), 32, _ink(K.col("accent"))), 3.0)
        core = VGroup(Circle(radius=max(0.75, core_words.width / 2 + 0.25), stroke_width=0, fill_color=K.col("accent"),
                             fill_opacity=1), core_words)
        n = len(specs)
        tones = self._tones(n)
        made = []
        for k, (b, tone) in enumerate(zip(specs, tones)):
            a = math.pi / 2 - 2 * math.pi * k / n + (math.pi / n if n % 2 == 0 else 0)
            p = np.array([4.0 * math.cos(a), 2.6 * math.sin(a), 0])
            pill = K.chip(str(b.get("label", "")), tone, _ink(tone), 30, pad=0.24)
            fit(pill, 3.4)
            pill.move_to(p)
            out = np.array([math.cos(a), math.sin(a), 0])
            s0 = core[0].get_center() + out * core[0].width / 2
            stem_ = K.arrow_between(s0, pill.get_center() - out * (min(pill.width, pill.height) / 2 + 0.05), tone,
                                    curve=0.25, width=6)[0]
            # Its own ideas in a short column on its outer side (left or right of it, or above or below it).
            kids = VGroup(*[fit(K.body(str(ch), 20, P.CREAM, 22), 2.6) for ch in (b.get("children") or [])[:3]])
            if len(kids):
                side = (RIGHT if out[0] > 0 else LEFT) if abs(out[0]) > 0.45 else (UP if out[1] > 0 else DOWN)
                kids.arrange(DOWN, buff=0.08, aligned_edge=LEFT if side is RIGHT else RIGHT if side is LEFT else ORIGIN)
                kids.next_to(pill, side, buff=0.25)
            made.append((b, VGroup(stem_, pill, kids)))
        body = VGroup(*[m for _, m in made], core)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.timed(FadeIn(core, scale=0.4, rate_func=ease_out_back), K.t("base"), "pop")],
                             lag=0.4)
        self._part(tid, c.get("text"), core, point=lambda: K.pulse(core, 1.08))
        for b, m in made:
            self._part(tid, b.get("label"), m[1], point=lambda m=m: K.pulse(m[1], 1.1))
            self._moment(_said(b.get("on"), b.get("label")),
                         lambda heard, m=m: K.chain([K.draw(m[0], run=K.t("fast")), K.enter(m[1], "pop", run=K.t("fast")),
                                                     *([K.stagger([K.enter(x, "fade", run=K.t("fast")) for x in m[2]], lag=0.2)]
                                                       if len(m[2]) else [])]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [m for _, m in made])
        return anim
