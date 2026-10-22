"""More motion templates (beta: MOTION_ENGINE.md §3): the shapes a history, a society or an argument takes, each
building part by part on the words that name it. A mixin of motion.MotionLecture (it uses the lecture's template
plumbing: _titled, _fit, _show, _hold_back, _moment, _part).

    hierarchy   tiers stacked as a pyramid, built from the bottom (or the top) as each is named
    exchange    two parties, what each gives the other drawn across as an arrow on its words
    plan        a site's plan: zones (fields in strips, woods, water, buildings...) tinted and named as said
    lineage     a family or a dynasty: each generation joined to the one before as it is named
    lifespan    lives as bars on one scale of years, each swept from birth to death
    analogy     matched pairs, A is to B as C is to D, each pair joined on its words
    myth        the wrong idea, struck through and stamped, the right one sliding in under it
    ritual      a ceremony on a parchment: its steps written in, its objects laid out, a seal pressed at the end
    share       a whole in equal pieces (sacks, coins), the share taken lifted out and named
    calendar    a year as a ring of months: seasons swept round it, days pinned on it (one may move)
    converge    many places joined to one (or one spreading to many), the arrows drawn as each is named
    table       a few columns compared row by row, each row filled in as it is said
    ask         a question set large; its answer coming in under it when the line gives it
"""

from __future__ import annotations

import math
import re

import numpy as np
from manim import (BOLD, DOWN, LEFT, RIGHT, UP, AnnularSector, Arc, Circle, DashedVMobject, Dot, FadeIn, Group,
                   ImageMobject, Line, Polygon, Rectangle, RoundedRectangle, VGroup, VMobject)
from manim.utils.rate_functions import ease_out_back, ease_out_cubic, ease_out_expo

import motion_kit as K
import motion_looks
import pocket_lecture as pl
import timeline_dates as td
from pocket_lecture import Z_MARK, fit

Z_TEMPLATE = Z_MARK + 10
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
CELLS = {"nw": (0, 0), "n": (1, 0), "ne": (2, 0), "w": (0, 1), "center": (1, 1), "e": (2, 1), "sw": (0, 2),
         "s": (1, 2), "se": (2, 2)}
CELL_ORDER = ["center", "n", "s", "w", "e", "nw", "ne", "sw", "se"]
ZONE_KINDS = ("field", "wood", "water", "pasture", "building", "church", "marsh", "road")
UNIT_SHAPES = ("sack", "coin", "box")


def _ink(fill: str) -> str:
    """Dark or light words for a fill, whichever reads."""
    try:
        return "#111111" if pl._luminance(str(fill)) > 0.45 else "#FFFFFF"
    except Exception:  # noqa: BLE001
        return "#111111"


def _said(on, *names) -> list[str]:
    """What a part comes on at: its `on` alone when given (the line's words, chosen), else whichever of its names the
    line says first. Offered beside `on`, a name said earlier (a share's "to the Church" matched the line's opening
    "The Church") brought the part on before its words."""
    if str(on or "").strip():
        return [str(on)]
    return [str(n) for n in names if str(n or "").strip()]


def _day_of_year(text) -> float | None:
    """A day as the year's share of days gone: "25 December", "Dec 25", "April" (its middle)."""
    words = str(text or "").strip().lower()
    if not words:
        return None
    month = next((k for k, m in enumerate(MONTHS) if re.search(rf"\b{m[:3].lower()}", words)), None)
    if month is None:
        return None
    day = re.search(r"\b(\d{1,2})\b", words)
    d = min(int(day.group(1)), MONTH_DAYS[month]) if day else MONTH_DAYS[month] / 2
    return sum(MONTH_DAYS[:month]) + d


class MoreTemplates:
    """The templates of this module, as MotionLecture's m_<op> methods."""

    # ---------------------------------------------------------------- shared ------------------------------------
    def _tones(self, n: int) -> list[str]:
        P = pl.P
        base = [K.col("accent"), K.col("second"), K.col("stamp"), P.SAND, K.col("good"), P.RIVER]
        return [base[k % len(base)] for k in range(n)]

    @staticmethod
    def _pic(file, height: float, width: float):
        if not file:
            return None
        try:
            m = ImageMobject(motion_looks.dress(str(file), "plain")[0])
            m.scale_to_fit_height(height)
            if m.width > width:
                m.scale_to_fit_width(width)
            return m
        except Exception:  # noqa: BLE001 -- shown without its picture
            return None

    # ---------------------------------------------------------------- hierarchy --------------------------------
    def m_hierarchy(self, tiers, title: str | None = None, kicker: str | None = None, badge=None,
                    build: str = "up", id: str | None = None):
        """Tiers stacked as a pyramid (the first given at the top), each with its role beside it; built from the
        bottom up (or `build: "down"`) as each is named; a `badge` ({tier, text, on}) slammed beside a tier."""
        P = pl.P
        specs = [t if isinstance(t, dict) else {"label": str(t)} for t in (tiers or [])][:6]
        if len(specs) < 2:
            return None
        tid = id or self._next_id("hierarchy")
        n = len(specs)
        th, top_w, bot_w = 1.0, 2.6, 8.8
        height = n * th
        tones = self._tones(n)
        rows = []
        for k, s in enumerate(specs):
            y1 = height / 2 - k * th
            y0 = y1 - th + 0.07
            w1 = top_w + (bot_w - top_w) * k / n
            w0 = top_w + (bot_w - top_w) * (k + 1) / n
            shape = Polygon([-w1 / 2, y1, 0], [w1 / 2, y1, 0], [w0 / 2, y0, 0], [-w0 / 2, y0, 0], stroke_width=0,
                            fill_color=tones[k], fill_opacity=1)
            word = fit(K.head(str(s.get("label", "")), 28, _ink(tones[k])), min(w0, w1) * 0.84)
            word.move_to([0, (y0 + y1) / 2, 0])
            parts = [shape, word]
            if s.get("role"):
                role = K.body(str(s["role"]), 22, P.CREAM, 26)
                role.move_to([bot_w / 2 + 0.55 + role.width / 2, (y0 + y1) / 2, 0])
                lead = Line([w0 / 2 + 0.08, (y0 + y1) / 2, 0], [bot_w / 2 + 0.45, (y0 + y1) / 2, 0],
                            stroke_color=P.MUTED, stroke_width=2)
                parts += [lead, role]
            pic = self._pic(s.get("file"), th * 0.9, 1.4)
            if pic is not None:
                pic.move_to([-bot_w / 2 - 0.35 - pic.width / 2, (y0 + y1) / 2, 0])
                parts.append(pic)
            rows.append((s, K.group_of(*parts)))
        chip = None
        if isinstance(badge, dict) and badge.get("text"):
            at = next((r for s, r in rows if str(s.get("label", "")).lower() == str(badge.get("tier", "")).lower()),
                      rows[len(rows) // 2][1])
            chip = K.chip(str(badge["text"]), K.col("stamp"), "#FFFFFF", 22)
            # Laid out with the pyramid (so it is fitted with it), beside the tier and its role.
            chip.next_to(at, RIGHT, buff=0.3)
            chip.set_z_index(Z_TEMPLATE + 3)
        body = K.group_of(*[r for _, r in rows], *([chip] if chip is not None else []))
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.2)
        order = list(reversed(rows)) if build != "down" else rows
        first = order[0][1]
        entrance = K.stagger([self._title_in(top), K.timed(FadeIn(first, shift=UP * 0.5, rate_func=ease_out_back),
                                                           K.t("base"), "pop")], lag=0.5)
        for s, r in rows:
            self._part(tid, s.get("label"), r, point=lambda r=r: K.pulse(r, 1.05))
        for s, r in order[1:]:
            self._moment(_said(s.get("on"), s.get("label")),
                         lambda heard, r=r: K.timed(FadeIn(r, shift=(UP if build != "down" else DOWN) * 0.5,
                                                           rate_func=ease_out_back), K.t("base"), "pop"))
        if chip is not None:
            self._moment(_said(badge.get("on"), badge["text"]), lambda heard, chip=chip: K.slam(chip))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [r for _, r in order[1:]] + ([chip] if chip is not None else []))
        return anim

    # ---------------------------------------------------------------- exchange ---------------------------------
    def m_exchange(self, left, right, flows, title: str | None = None, kicker: str | None = None,
                   id: str | None = None):
        """Two parties on the two sides; each of `flows` ({from: left|right, text, on}) drawn across between them as
        an arrow from the one who gives it, its words on a chip, as the line says it."""
        tid = id or self._next_id("exchange")
        sides = []
        for s, tone in ((left, K.col("accent")), (right, K.col("second"))):
            s = s if isinstance(s, dict) else {"title": str(s or "")}
            pic = self._pic(s.get("file"), 1.6, 2.6)
            name = fit(K.head(str(s.get("title", "")), 32, K.col("card_ink")), 2.8)
            sub = fit(K.body(str(s["sub"]), 18, K.col("card_ink"), 22), 2.8) if s.get("sub") else None
            stack = [m for m in (pic, name, sub) if m is not None]
            content = (Group if pic is not None else VGroup)(*stack).arrange(DOWN, buff=0.18)
            face = K.card(3.3, max(2.3, content.height + 0.6))
            content.move_to(face.face)
            band = Rectangle(width=3.3, height=0.12, stroke_width=0, fill_color=tone, fill_opacity=1)
            band.move_to(face.face.get_top() + DOWN * 0.06)
            sides.append((s, tone, K.group_of(face, band, content)))
        (ls, ltone, lcard), (rs, rtone, rcard) = sides
        lcard.move_to([-4.5, 0, 0])
        rcard.move_to([4.5, 0, 0])
        specs = [f for f in (flows or []) if isinstance(f, dict) and f.get("text")][:4]
        if not specs:
            return None
        gap = 1.1
        made = []
        for k, f in enumerate(specs):
            y = (len(specs) - 1) * gap / 2 - k * gap
            who = str(f.get("from", "left")).lower()
            from_left = who in ("left", str(ls.get("title", "")).lower()) or who not in ("right", str(rs.get("title", "")).lower())
            tone = ltone if from_left else rtone
            a, b = ([-2.6, y, 0], [2.6, y, 0]) if from_left else ([2.6, y, 0], [-2.6, y, 0])
            arrow = K.arrow_between(np.array(a), np.array(b), tone, width=7)
            chip = K.chip(str(f["text"]), tone, _ink(tone), 22)
            fit(chip, 4.6)
            chip.move_to([0, y + 0.36, 0])
            made.append((f, VGroup(arrow, chip), arrow, chip))
        body = K.group_of(lcard, rcard, *[m for _, m, _, _ in made])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top),
                              K.together([K.timed(FadeIn(lcard, shift=RIGHT * 2, rate_func=ease_out_expo), K.t("base"), "swish"),
                                          K.timed(FadeIn(rcard, shift=LEFT * 2, rate_func=ease_out_expo), K.t("base"))])],
                             lag=0.5)
        for s, _, c in sides:
            self._part(tid, s.get("title"), c, point=lambda c=c: K.pulse(c, 1.04))
        for f, m, arrow, chip in made:
            self._part(tid, f.get("text"), m, point=lambda m=m: K.pulse(m, 1.06))
            self._moment(_said(f.get("on"), f.get("text")),
                         lambda heard, arrow=arrow, chip=chip: K.chain([K.draw(arrow, run=K.t("base"), sfx="swish"),
                                                                        K.enter(chip, "pop", run=K.t("fast"))]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [m for _, m, _, _ in made])
        return anim

    # ---------------------------------------------------------------- plan -------------------------------------
    def _zone_art(self, kind: str, x0: float, y0: float, x1: float, y1: float, tint: bool = False):
        """A zone of a plan drawn in its kind: field strips, trees, water, grass, buildings, marsh, a road."""
        P = pl.P
        w, h = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        fills = {"field": "#E9D48B", "wood": "#7FA66A", "water": "#8DB9D8", "pasture": "#B8D68E", "building": "#E3CBA8",
                 "church": "#E3CBA8", "marsh": "#9DB7A5", "road": None}
        fill = fills.get(kind, "#D8D0BF")
        art = VGroup()
        if kind == "road":
            if w >= h:
                art.add(Line([x0, cy, 0], [x1, cy, 0], stroke_color="#8C7B63", stroke_width=12))
            else:
                art.add(Line([cx, y0, 0], [cx, y1, 0], stroke_color="#8C7B63", stroke_width=12))
            return pl._flat(art)
        art.add(Rectangle(width=w, height=h, stroke_color="#6B5E4B", stroke_width=1.5, fill_color=fill,
                          fill_opacity=0.55 if tint else 1).move_to([cx, cy, 0]))
        if tint:
            return pl._flat(art)
        rng = np.random.default_rng(int(abs(x0 * 97 + y0 * 31)) % 1000)
        if kind == "field":
            strips = max(3, int(w / 0.28))
            for k in range(1, strips):
                x = x0 + w * k / strips
                art.add(Line([x, y0 + 0.05, 0], [x, y1 - 0.05, 0], stroke_color="#B8A15A", stroke_width=1.6))
        elif kind == "wood":
            for _ in range(max(4, int(w * h * 5))):
                r = rng.uniform(0.09, 0.16)
                art.add(Circle(radius=r, stroke_width=0, fill_color="#4F7A3D", fill_opacity=1).move_to(
                    [rng.uniform(x0 + r, x1 - r), rng.uniform(y0 + r, y1 - r), 0]))
        elif kind in ("water", "marsh"):
            rows = max(2, int(h / 0.3))
            for k in range(1, rows):
                y = y0 + h * k / rows
                pts = [np.array([x0 + 0.1 + (w - 0.2) * s, y + 0.04 * math.sin(s * 14), 0]) for s in np.linspace(0, 1, 18)]
                line = VMobject(stroke_color="#4E7FA8" if kind == "water" else "#5B7F6A", stroke_width=1.6)
                art.add(line.set_points_smoothly(pts))
        elif kind == "pasture":
            for _ in range(max(5, int(w * h * 8))):
                art.add(Dot([rng.uniform(x0 + 0.08, x1 - 0.08), rng.uniform(y0 + 0.08, y1 - 0.08), 0], radius=0.025,
                            color="#6E9A4E"))
        elif kind in ("building", "church"):
            size = min(0.42, w * 0.3, h * 0.45)
            for k in range(1 if kind == "church" else max(1, min(4, int(w / (size * 1.6))))):
                x = cx if kind == "church" else x0 + w * (k + 0.5) / max(1, min(4, int(w / (size * 1.6))))
                base = Rectangle(width=size, height=size * 0.7, stroke_color="#5A4632", stroke_width=1.5,
                                 fill_color="#C9A37A", fill_opacity=1).move_to([x, cy - size * 0.1, 0])
                roof = Polygon([x - size * 0.6, cy + size * 0.25, 0], [x + size * 0.6, cy + size * 0.25, 0],
                               [x, cy + size * 0.65, 0], stroke_width=0, fill_color="#8C4A32", fill_opacity=1)
                art.add(base, roof)
                if kind == "church":
                    art.add(Line([x, cy + size * 0.65, 0], [x, cy + size * 1.0, 0], stroke_color="#5A4632", stroke_width=3),
                            Line([x - size * 0.13, cy + size * 0.87, 0], [x + size * 0.13, cy + size * 0.87, 0],
                                 stroke_color="#5A4632", stroke_width=3))
        return pl._flat(art)

    def m_plan(self, zones, title: str | None = None, kicker: str | None = None, file: str | None = None,
               id: str | None = None):
        """A site's plan on a board: each zone ({label, kind, at | box, on}) drawn in its kind (strips of field,
        trees, water, grass, buildings, marsh, a road) and named as the line says it. `at` is a place on a 3 x 3
        grid (nw, n, ne, w, center, e, sw, s, se); with a picture (a book's plan), `box` [x0, y0, x1, y1] (0 to 1
        across and down it) marks the zone on the picture, tinted."""
        tid = id or self._next_id("plan")
        specs = [z if isinstance(z, dict) else {"label": str(z)} for z in (zones or [])][:12]
        if not specs:
            return None
        width, height = 10.6, 5.6
        board = K.card(width + 0.3, height + 0.3)
        pic = self._pic(file, height, width) if file else None
        made = []
        if pic is not None:
            lo, hi = pic.get_corner(DOWN + LEFT), pic.get_corner(UP + RIGHT)
            pw, ph = hi[0] - lo[0], hi[1] - lo[1]
            for s in specs:
                box = s.get("box")
                if not (isinstance(box, (list, tuple)) and len(box) == 4):
                    continue
                u0, v0, u1, v1 = (float(v) for v in box)
                x0, x1 = lo[0] + u0 * pw, lo[0] + u1 * pw
                y0, y1 = hi[1] - v1 * ph, hi[1] - v0 * ph
                made.append((s, self._zone_art(str(s.get("kind", "field")), x0, y0, x1, y1, tint=True), (x0, y0, x1, y1)))
        else:
            free = [c for c in CELL_ORDER if c not in {str(s.get("at", "")).lower() for s in specs}]
            cells: dict[str, list] = {}
            for s in specs:
                at = str(s.get("at", "")).lower()
                if at not in CELLS:
                    at = free.pop(0) if free else "center"
                cells.setdefault(at, []).append(s)
            cw, ch = width / 3, height / 3
            for at, members in cells.items():
                col_, row_ = CELLS[at]
                cx0 = -width / 2 + col_ * cw
                cy1 = height / 2 - row_ * ch
                for k, s in enumerate(members):
                    x0 = cx0 + cw * k / len(members) + 0.05
                    x1 = cx0 + cw * (k + 1) / len(members) - 0.05
                    y0, y1 = cy1 - ch + 0.05, cy1 - 0.05
                    kind = str(s.get("kind", "field")).lower()
                    made.append((s, self._zone_art(kind if kind in ZONE_KINDS else "field", x0, y0, x1, y1), (x0, y0, x1, y1)))
        zones_shown = []
        for s, art, (x0, y0, x1, y1) in made:
            chip = K.chip(str(s.get("label", "")), K.col("card"), K.col("card_ink"), 21, pad=0.1)
            fit(chip, max(0.6, x1 - x0 - 0.1))
            chip.move_to([(x0 + x1) / 2, y1 - chip.height / 2 - 0.08, 0])
            zones_shown.append((s, K.group_of(art, chip), art, chip))
        parts = [board, *([pic] if pic is not None else []), *[z for _, z, _, _ in zones_shown]]
        body = K.group_of(*parts)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.enter(board, "fade", run=K.t("base")),
                              K.enter(pic, "fade", run=K.t("base")) if pic is not None else None], lag=0.4)
        for s, z, art, chip in zones_shown:
            self._part(tid, s.get("label"), z, point=lambda z=z: K.pulse(z, 1.04))
            self._moment(_said(s.get("on"), s.get("label")),
                         lambda heard, art=art, chip=chip: K.chain([K.timed(FadeIn(art, scale=0.96, rate_func=ease_out_cubic),
                                                                            K.t("base")),
                                                                    K.enter(chip, "pop", run=K.t("fast"))]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [z for _, z, _, _ in zones_shown])
        return anim

    # ---------------------------------------------------------------- lineage ----------------------------------
    def m_lineage(self, people, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A family or a dynasty: each person ({name, dates, role, picture, parent, via, on}) a card joined to their
        `parent` (by default the one before), the link named by `via` ("son", "succeeds"); a single line of
        descent runs left to right, a family branches down. Each joins as the line names them."""
        P = pl.P
        tid = id or self._next_id("lineage")
        specs = [p if isinstance(p, dict) else {"name": str(p)} for p in (people or [])][:8]
        if len(specs) < 2:
            return None
        names = [str(s.get("name", "")).lower() for s in specs]
        parent = []
        for k, s in enumerate(specs):
            p = s.get("parent")
            if p is None:
                parent.append(k - 1 if k else None)
            else:
                parent.append(names.index(str(p).lower()) if str(p).lower() in names[:k] else (k - 1 if k else None))
        chain_line = all(parent[k] == k - 1 for k in range(1, len(specs)))
        cards = []
        for s in specs:
            pic = self._pic(s.get("file"), 1.2, 2.2)
            name = fit(K.head(str(s.get("name", "")), 26, K.col("card_ink")), 2.4)
            dates = K.kicker(str(s["dates"]), 16, K.col("accent")) if s.get("dates") else None
            role = fit(K.body(str(s["role"]), 17, K.col("card_ink"), 22), 2.4) if s.get("role") else None
            stack = [m for m in (pic, name, dates, role) if m is not None]
            content = (Group if pic is not None else VGroup)(*stack).arrange(DOWN, buff=0.12)
            face = K.card(2.7, content.height + 0.45)
            content.move_to(face.face)
            cards.append(K.group_of(face, content))
        if chain_line:
            Group(*cards).arrange(RIGHT, buff=1.2, aligned_edge=UP)
        else:
            depth = []
            for k in range(len(specs)):
                depth.append(0 if parent[k] is None else depth[parent[k]] + 1)
            levels: dict[int, list[int]] = {}
            for k, d in enumerate(depth):
                levels.setdefault(d, []).append(k)
            for d, members in levels.items():
                for j, k in enumerate(members):
                    cards[k].move_to([(j - (len(members) - 1) / 2) * 3.2, -d * 2.9, 0])
        links = []
        for k in range(1, len(specs)):
            p = parent[k]
            if p is None:
                links.append(None)
                continue
            a, b = cards[p], cards[k]
            if chain_line:
                line = K.arrow_between(a.get_right() + RIGHT * 0.08, b.get_left() + LEFT * 0.08, K.col("accent"), width=5)
                mid = (a.get_right() + b.get_left()) / 2
            else:
                top = a.get_bottom() + DOWN * 0.05
                bottom = b.get_top() + UP * 0.05
                knee = (top[1] + bottom[1]) / 2
                line = pl._flat(VGroup(Line(top, [top[0], knee, 0], stroke_color=K.col("accent"), stroke_width=4),
                                       Line([top[0], knee, 0], [bottom[0], knee, 0], stroke_color=K.col("accent"), stroke_width=4),
                                       Line([bottom[0], knee, 0], bottom, stroke_color=K.col("accent"), stroke_width=4)))
                mid = np.array([bottom[0], knee, 0])
            parts = [line]
            via = specs[k].get("via")
            if via:
                tag = K.chip(str(via), K.col("card"), K.col("card_ink"), 15, pad=0.08)
                tag.move_to(mid + UP * (0.3 if chain_line else 0))
                parts.append(tag)
            links.append(VGroup(*parts))
        body = K.group_of(*cards, *[l_ for l_ in links if l_ is not None])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.enter(cards[0], "pop")], lag=0.5)
        hidden = []
        for k, (s, c) in enumerate(zip(specs, cards)):
            self._part(tid, s.get("name"), c, point=lambda c=c: K.pulse(c, 1.05))
            if k == 0:
                continue
            link = links[k - 1]
            hidden += [c] + ([link] if link is not None else [])
            self._moment(_said(s.get("on"), s.get("name")),
                         lambda heard, c=c, link=link: K.chain([*([K.draw(link, run=K.t("base"))] if link is not None else []),
                                                                K.enter(c, "pop", run=K.t("base"))]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, hidden)
        return anim

    # ---------------------------------------------------------------- lifespan ---------------------------------
    def m_lifespan(self, people, range=None, marks=None, title: str | None = None, kicker: str | None = None,
                   id: str | None = None):
        """Lives as bars on one scale of years ({name, from, to, note, on}), each swept from birth to death as the
        line names them; `marks` ({at, label, on}) are dashed lines down at a year."""
        P = pl.P
        tid = id or self._next_id("lifespan")
        specs = []
        for p in (people or [])[:7]:
            if not isinstance(p, dict):
                continue
            a, b = td.year(p.get("from")), td.year(p.get("to"))
            if a is None or b is None or b <= a:
                continue
            specs.append({**p, "_a": a, "_b": b})
        if not specs:
            return None
        lo, hi = min(s["_a"] for s in specs), max(s["_b"] for s in specs)
        if range and len(range) == 2 and td.year(range[0]) is not None and td.year(range[1]) is not None:
            lo, hi = min(lo, td.year(range[0])), max(hi, td.year(range[1]))
        pad = max((hi - lo) * 0.05, 2)
        lo, hi = lo - pad, hi + pad
        width = 11.0

        def x(year):
            return -width / 2 + (year - lo) / (hi - lo) * width
        span = hi - lo
        step = next(s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000) if span / s <= 8)
        axis_y = -0.3 - len(specs) * 0.75
        axis = VGroup(Line([-width / 2, axis_y, 0], [width / 2, axis_y, 0], stroke_color=P.MUTED, stroke_width=3))
        first = math.ceil(lo / step) * step
        for yr in np.arange(first, hi, step):
            tick = Line([x(yr), axis_y, 0], [x(yr), axis_y - 0.12, 0], stroke_color=P.MUTED, stroke_width=2)
            label = K.kicker(td.label(int(yr)) if hasattr(td, "label") else str(int(yr)), 15)
            label.next_to(tick, DOWN, buff=0.06)
            axis.add(tick, label)
        tones = self._tones(len(specs))
        bars = []
        for k, s in enumerate(specs):
            y = -k * 0.75
            w = max(0.15, x(s["_b"]) - x(s["_a"]))
            bar = RoundedRectangle(corner_radius=0.12, width=w, height=0.48, stroke_width=0, fill_color=tones[k],
                                   fill_opacity=1).move_to([x(s["_a"]) + w / 2, y, 0])
            name = K.head(str(s.get("name", "")), 20, _ink(tones[k]))
            dates = K.kicker(f"{s.get('from')}–{s.get('to')}", 14, P.MUTED)
            if name.width < w - 0.25:
                name.move_to(bar)
            else:
                name.set_color(P.CREAM).next_to(bar, RIGHT, buff=0.15)
            dates.next_to(bar, DOWN, buff=0.04).align_to(bar, LEFT)
            bars.append((s, VGroup(bar, name, dates), bar))
        guides = []
        for m in (marks or [])[:4]:
            if not isinstance(m, dict) or td.year(m.get("at")) is None:
                continue
            gx = x(td.year(m["at"]))
            line = DashedVMobject(Line([gx, 0.5, 0], [gx, axis_y, 0], stroke_color=K.col("stamp"), stroke_width=3), num_dashes=24)
            tag = K.chip(str(m.get("label") or m["at"]), K.col("stamp"), "#FFFFFF", 16)
            tag.next_to(line, UP, buff=0.06)
            guides.append((m, VGroup(line, tag)))
        body = VGroup(axis, *[b for _, b, _ in bars], *[g for _, g in guides])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.draw(axis, run=K.t("slow"))], lag=0.5)
        for s, group, bar in bars:
            self._part(tid, s.get("name"), group, point=lambda g=group: K.pulse(g, 1.04))
            self._moment(_said(s.get("on"), s.get("name")),
                         lambda heard, group=group, bar=bar: K.chain([K.grow_from(bar, LEFT, run=K.t("slow")),
                                                                      K.together([K.enter(group[1], "fade", run=K.t("fast")),
                                                                                  K.enter(group[2], "fade", run=K.t("fast"))])]))
        for m, g in guides:
            self._moment(_said(m.get("on"), m.get("label"), m.get("at")),
                         lambda heard, g=g: K.chain([K.draw(g[0], run=K.t("base")), K.enter(g[1], "pop", run=K.t("fast"))]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [b for _, b, _ in bars] + [g for _, g in guides])
        return anim

    # ---------------------------------------------------------------- analogy ----------------------------------
    def m_analogy(self, pairs, left=None, right=None, title: str | None = None, kicker: str | None = None,
                  stamp=None, id: str | None = None):
        """Matched pairs, A is to B as C is to D: two headed columns, each pair ([a, b] or {a, b, on}) joined by an
        arrow as the line says it; a `stamp` across them at the end."""
        P = pl.P
        tid = id or self._next_id("analogy")
        specs = []
        for p in (pairs or [])[:6]:
            if isinstance(p, dict) and p.get("a") and p.get("b"):
                specs.append(p)
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                specs.append({"a": str(p[0]), "b": str(p[1])})
        if not specs:
            return None
        cw = 4.4
        rows = []
        for k, s in enumerate(specs):
            y = -k * 0.95
            a = K.card(cw, 0.72)
            a_words = fit(K.head(str(s["a"]), 24, K.col("card_ink")), cw - 0.3).move_to(a.face)
            b = K.card(cw, 0.72)
            b_words = fit(K.head(str(s["b"]), 24, K.col("card_ink")), cw - 0.3).move_to(b.face)
            ga, gb = VGroup(a, a_words).move_to([-3.4, y, 0]), VGroup(b, b_words).move_to([3.4, y, 0])
            arrow = K.arrow_between(np.array([-3.4 + cw / 2 + 0.15, y, 0]), np.array([3.4 - cw / 2 - 0.15, y, 0]),
                                    K.col("accent"), width=5)
            rows.append((s, VGroup(ga, arrow, gb), ga, arrow, gb))
        heads = VGroup()
        for side, x in ((left, -3.4), (right, 3.4)):
            if side:
                text = side.get("title") if isinstance(side, dict) else side
                heads.add(K.kicker(str(text), 20, K.col("accent")).move_to([x, 0.75, 0]))
        body = VGroup(heads, *[r for _, r, _, _, _ in rows])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.enter(heads, "fade") if len(heads) else None], lag=0.4)
        for s, r, ga, arrow, gb in rows:
            self._part(tid, s["a"], r, point=lambda r=r: K.pulse(r, 1.04))
            self._moment(_said(s.get("on"), s["a"], s["b"]),
                         lambda heard, ga=ga, arrow=arrow, gb=gb: K.chain([
                             K.timed(FadeIn(ga, shift=RIGHT * 0.6, rate_func=ease_out_expo), K.t("base"), "swish"),
                             K.draw(arrow, run=K.t("fast")),
                             K.timed(FadeIn(gb, shift=LEFT * 0.6, rate_func=ease_out_expo), K.t("base"))]))
        if stamp:
            stamp = stamp if isinstance(stamp, dict) else {"text": str(stamp)}
            big = K.stamp(str(stamp["text"]), size=46, angle=-8)
            big.move_to(body.get_center())
            big.set_z_index(Z_TEMPLATE + 4)

            def slam(heard, big=big):
                self._stage_add(big)
                return K.slam(big)
            self._moment(_said(stamp.get("on"), stamp["text"]), slam)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [r for _, r, _, _, _ in rows])
        return anim

    # ---------------------------------------------------------------- myth -------------------------------------
    def m_myth(self, wrong: str, right: str, label: str = "Not quite", title: str | None = None,
               kicker: str | None = None, on: str | None = None, id: str | None = None):
        """The wrong idea on a card; as the line gives the right one (`on`, else its first words), the wrong one is
        struck through and stamped (`label`), and the right one slides in under it."""
        P = pl.P
        tid = id or self._next_id("myth")
        width = 9.5
        w_kick = K.kicker("We might think", 17, P.MUTED)
        w_words = fit(K.body(str(wrong), 30, K.col("card_ink"), 40), width - 0.8)
        w_stack = VGroup(w_kick, w_words).arrange(DOWN, buff=0.15, aligned_edge=LEFT)
        w_face = K.card(width, w_stack.height + 0.6)
        w_stack.move_to(w_face.face)
        wrong_card = VGroup(w_face, w_stack)
        strike = Line(w_words.get_left() + LEFT * 0.1, w_words.get_right() + RIGHT * 0.1, stroke_color=K.col("stamp"),
                      stroke_width=6)
        seal = K.stamp(str(label or "Not quite"), size=30, angle=-8)
        seal.move_to(w_face.face.get_corner(UP + RIGHT) + LEFT * (seal.width / 2 + 0.2) + DOWN * 0.15)
        r_kick = K.kicker("In fact", 17, K.col("good"))
        r_words = fit(K.body(str(right), 30, K.col("card_ink"), 40), width - 1.4)
        tick = K.check_mark(0.42, K.col("good"))
        r_line = VGroup(tick, r_words).arrange(RIGHT, buff=0.25, aligned_edge=UP)
        r_stack = VGroup(r_kick, r_line).arrange(DOWN, buff=0.15, aligned_edge=LEFT)
        r_face = K.card(width, r_stack.height + 0.6, stroke=K.col("good"), stroke_width=3)
        r_stack.move_to(r_face.face)
        right_card = VGroup(r_face, r_stack)
        VGroup(wrong_card, right_card).arrange(DOWN, buff=0.45)
        strike.move_to(w_words)
        seal.move_to(w_face.face.get_corner(UP + RIGHT) + LEFT * (seal.width / 2 + 0.2) + DOWN * 0.15)
        body = VGroup(wrong_card, right_card, strike, seal)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.enter(wrong_card, "rise")], lag=0.5)
        self._part(tid, wrong, wrong_card)
        self._part(tid, right, right_card)
        said = on or " ".join(str(right).split()[:3])

        def turn(heard):
            return K.chain([K.draw(strike, run=K.t("fast"), sfx="swish"), K.slam(seal),
                            K.timed(FadeIn(right_card, shift=UP * 0.6, rate_func=ease_out_back), K.t("base"), "pop")])
        self._moment(_said(said), turn)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [strike, seal, right_card])
        return anim

    # ---------------------------------------------------------------- ritual -----------------------------------
    def m_ritual(self, steps, objects=None, seal=None, title: str | None = None, kicker: str | None = None,
                 id: str | None = None):
        """A ceremony on a parchment: its `steps` ({text, on}) written in one by one as they are said, its
        `objects` ({name, picture, on}) laid out beside it, a `seal` ({text, on}) pressed at the end."""
        P = pl.P
        tid = id or self._next_id("ritual")
        specs = [s if isinstance(s, dict) else {"text": str(s)} for s in (steps or [])][:6]
        if not specs:
            return None
        lines = []
        for k, s in enumerate(specs):
            num = K.number(f"{k + 1}", 26, K.col("accent"))
            words = K.body(str(s.get("text", "")), 24, K.col("card_ink"), 34)
            lines.append((s, VGroup(num, words).arrange(RIGHT, buff=0.25, aligned_edge=UP)))
        head = K.head(str(title or "The ceremony"), 30, K.col("card_ink"))
        text = VGroup(head, *[l_ for _, l_ in lines]).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        face = K.card(max(6.8, text.width + 0.9), text.height + 0.9)
        text.move_to(face.face)
        sheet = K.group_of(face, text)
        objs = []
        for o in (objects or [])[:4]:
            o = o if isinstance(o, dict) else {"name": str(o)}
            pic = self._pic(o.get("file"), 1.0, 1.8)
            name = K.chip(str(o.get("name", "")), K.col("second"), _ink(K.col("second")), 18)
            item = Group(pic, name).arrange(DOWN, buff=0.1) if pic is not None else VGroup(name)
            objs.append((o, item))
        tray = Group(*[i for _, i in objs]).arrange(DOWN, buff=0.35) if objs else None
        if tray is not None:
            tray.next_to(sheet, RIGHT, buff=1.0)
        mark = None
        if seal:
            seal = seal if isinstance(seal, dict) else {"text": str(seal)}
            disc = Circle(radius=0.62, stroke_width=0, fill_color=K.col("stamp"), fill_opacity=1)
            ring = Circle(radius=0.52, stroke_color="#FFFFFF", stroke_width=2, fill_opacity=0)
            word = fit(K.head(str(seal["text"]), 18, "#FFFFFF", upper=True), 0.9)
            mark = VGroup(disc, ring, word)
            mark.move_to(face.face.get_corner(DOWN + RIGHT) + LEFT * 1.1 + UP * 0.8)
            mark.rotate(-0.2)
            mark.set_z_index(Z_TEMPLATE + 3)
        body = K.group_of(sheet, *([tray] if tray is not None else []))
        whole, _ = self._titled(body, None, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([K.enter(face, "rise"), K.typewriter(head, run=0.6)], lag=0.4)
        hidden = []
        for s, line in lines:
            hidden.append(line)
            self._part(tid, s.get("text"), line, point=lambda l_=line: K.pulse(l_, 1.04))
            self._moment(_said(s.get("on"), s.get("text")),
                         lambda heard, line=line: K.together([K.enter(line[0], "pop", run=K.t("fast")),
                                                              K.typewriter(line[1], run=1.0)]))
        for o, item in objs:
            hidden.append(item)
            self._part(tid, o.get("name"), item, point=lambda i=item: K.pulse(i, 1.08))
            self._moment(_said(o.get("on"), o.get("name")), lambda heard, item=item: K.enter(item, "drop"))
        if mark is not None:
            def press(heard, mark=mark):
                self._stage_add(mark)
                return K.slam(mark)
            self._moment(_said(seal.get("on"), seal["text"]), press)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, hidden)
        return anim

    # ---------------------------------------------------------------- share ------------------------------------
    def _unit(self, shape: str):
        P = pl.P
        if shape == "coin":
            return VGroup(Circle(radius=0.32, stroke_color="#8C6D1F", stroke_width=3, fill_color="#E2B33C", fill_opacity=1),
                          Circle(radius=0.22, stroke_color="#8C6D1F", stroke_width=1.5, fill_opacity=0))
        if shape == "box":
            return VGroup(RoundedRectangle(corner_radius=0.05, width=0.62, height=0.62, stroke_color=P.MUTED, stroke_width=2,
                                           fill_color=P.SAND, fill_opacity=1))
        body = RoundedRectangle(corner_radius=0.2, width=0.6, height=0.72, stroke_color="#7A5E3A", stroke_width=2,
                                fill_color="#D9B98A", fill_opacity=1)
        neck = Polygon([-0.14, 0.36, 0], [0.14, 0.36, 0], [0.2, 0.52, 0], [-0.2, 0.52, 0], stroke_color="#7A5E3A",
                       stroke_width=2, fill_color="#C9A671", fill_opacity=1)
        tie = Line([-0.16, 0.38, 0], [0.16, 0.38, 0], stroke_color="#5A3E22", stroke_width=3)
        return VGroup(body, neck, tie)

    def m_share(self, total: int = 10, part: int = 1, unit: str = "sack", label: str | None = None,
                part_label: str | None = None, rest_label: str | None = None, on: str | None = None,
                title: str | None = None, kicker: str | None = None, id: str | None = None):
        """A whole in equal pieces (sacks, coins, boxes) in a row; as the line names the share (`on`, else its
        `part_label`), that many are coloured, lifted out and named, and "1 in 10" is set beside them."""
        P = pl.P
        tid = id or self._next_id("share")
        total = max(2, min(int(total or 10), 20))
        part = max(1, min(int(part or 1), total - 1))
        units = [self._unit(unit if unit in UNIT_SHAPES else "sack") for _ in range(total)]
        per_row = total if total <= 10 else math.ceil(total / 2)
        grid = VGroup(*units).arrange_in_grid(rows=math.ceil(total / per_row), cols=per_row, buff=0.3)
        taken = units[-part:]
        rest = VGroup(*units[:-part])
        rest_tag = K.kicker(str(rest_label), 18, P.MUTED).next_to(grid, DOWN, buff=0.35).align_to(grid, LEFT) \
            if rest_label else None
        ratio = K.number(f"{part} in {total}", 54, K.col("accent"))
        ratio.next_to(grid, RIGHT, buff=0.8)
        share_tag = K.chip(str(part_label or label or "the share"), K.col("accent"), _ink(K.col("accent")), 22)
        share_tag.next_to(VGroup(*taken), UP, buff=0.75)
        parts = [grid, ratio, share_tag] + ([rest_tag] if rest_tag is not None else [])
        body = VGroup(*parts)
        whole, top = self._titled(body, title or label, kicker)
        self._fit(whole, self._box(), grow=1.2)
        entrance = K.stagger([self._title_in(top), K.stagger([K.enter(u, "pop", run=K.t("fast")) for u in units], lag=0.12),
                              K.enter(rest_tag, "fade") if rest_tag is not None else None], lag=0.4)
        self._part(tid, part_label or label, VGroup(*taken), point=lambda: K.pulse(VGroup(*taken), 1.08))

        def lift(heard):
            moves = [K.timed(K.fresh(u.animate(rate_func=ease_out_back).shift(UP * 0.55).set_fill(K.col("accent"), opacity=1).build()),
                             K.t("base"), "pop") for u in taken]
            return K.chain([K.stagger(moves, lag=0.15), K.together([K.enter(share_tag, "pop", run=K.t("fast")),
                                                                     K.typewriter(ratio, run=0.6)])])
        self._moment(_said(on, part_label, label), lift)
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [share_tag, ratio])
        return anim

    # ---------------------------------------------------------------- calendar ---------------------------------
    def m_calendar(self, days=None, seasons=None, title: str | None = None, kicker: str | None = None,
                   id: str | None = None):
        """A year as a ring of months (January at the top, clockwise): `seasons` ({from, to, label, on}) swept round
        it, `days` ({at, label, moves: [from, to], on}) pinned on it as they are said; a day that `moves` spans its
        range, dashed."""
        P = pl.P
        tid = id or self._next_id("calendar")
        R = 2.3

        def angle(doy):
            return math.pi / 2 - 2 * math.pi * doy / 365

        def at(a, r):
            return np.array([r * math.cos(a), r * math.sin(a), 0])
        ring = Circle(radius=R, stroke_color=P.MUTED, stroke_width=5)
        months = VGroup()
        for k, m in enumerate(MONTHS):
            a = angle(sum(MONTH_DAYS[:k]))
            months.add(Line(at(a, R - 0.1), at(a, R + 0.1), stroke_color=P.MUTED, stroke_width=2))
            mid = angle(sum(MONTH_DAYS[:k]) + MONTH_DAYS[k] / 2)
            months.add(K.kicker(m[:3], 19, P.MUTED).move_to(at(mid, R + 0.45)))
        tones = self._tones(6)
        arcs = []
        for k, s in enumerate((seasons or [])[:6]):
            if not isinstance(s, dict):
                continue
            a0, a1 = _day_of_year(s.get("from")), _day_of_year(s.get("to"))
            if a0 is None or a1 is None:
                continue
            span = (a1 - a0) % 365 or 365
            sector = AnnularSector(inner_radius=R - 0.45, outer_radius=R - 0.08, angle=-2 * math.pi * span / 365,
                                   start_angle=angle(a0), fill_color=tones[k], fill_opacity=0.85, stroke_width=0)
            mid = angle(a0 + span / 2)
            word = K.body(str(s.get("label", "")), 24, P.CREAM, 14).move_to(at(mid, R - 1.0))
            arcs.append((s, VGroup(sector, word)))
        pins = []
        for d in (days or [])[:6]:
            if not isinstance(d, dict):
                continue
            moves = d.get("moves") if isinstance(d.get("moves"), (list, tuple)) and len(d["moves"]) == 2 else None
            if moves:
                m0, m1 = _day_of_year(moves[0]), _day_of_year(moves[1])
                if m0 is None or m1 is None:
                    continue
                doy = m0 + ((m1 - m0) % 365) / 2
                band = DashedVMobject(Arc(radius=R + 0.02, start_angle=angle(m0), angle=-2 * math.pi * ((m1 - m0) % 365) / 365,
                                          stroke_color=K.col("stamp"), stroke_width=9), num_dashes=10)
            else:
                doy = _day_of_year(d.get("at"))
                if doy is None:
                    continue
                band = None
            a = angle(doy)
            dot = Dot(at(a, R), radius=0.14, color=K.col("stamp"))
            tag = K.chip(str(d.get("label", "")) + (" (moves)" if moves else ""), K.col("stamp"), "#FFFFFF", 24)
            # Beside the ring, on the side the day is on, at its height (kept clear of the tags already there).
            side = 1 if math.cos(a) >= 0 else -1
            y = max(-R, min(R, R * math.sin(a)))
            taken = [o[-1] for _, o in pins if (o[-1].get_center()[0] > 0) == (side > 0)]
            for o in sorted(taken, key=lambda m: -m.get_center()[1]):
                if abs(o.get_center()[1] - y) < (o.height + tag.height) / 2 + 0.12:
                    y = o.get_center()[1] - (o.height + tag.height) / 2 - 0.12
            tag.move_to([side * (R + 0.9 + tag.width / 2), y, 0])
            edge = tag.get_left() if side > 0 else tag.get_right()
            lead = Line(at(a, R + 0.18), edge + LEFT * side * 0.08, stroke_color=K.col("stamp"), stroke_width=2.5)
            pins.append((d, VGroup(*([band] if band is not None else []), dot, lead, tag)))
        body = VGroup(ring, months, *[a_ for _, a_ in arcs], *[p for _, p in pins])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.draw(ring, run=K.t("slow")),
                              K.stagger([K.enter(m, "fade", run=K.t("fast")) for m in months], lag=0.05)], lag=0.4)
        for s, a_ in arcs:
            self._part(tid, s.get("label"), a_, point=lambda a_=a_: K.pulse(a_, 1.04))
            self._moment(_said(s.get("on"), s.get("label")),
                         lambda heard, a_=a_: K.chain([K.timed(FadeIn(a_[0], scale=0.9, rate_func=ease_out_cubic), K.t("base")),
                                                       K.enter(a_[1], "fade", run=K.t("fast"))]))
        for d, p in pins:
            self._part(tid, d.get("label"), p, point=lambda p=p: K.pulse(p, 1.08))
            self._moment(_said(d.get("on"), d.get("label"), d.get("at")),
                         lambda heard, p=p: K.chain([*([K.draw(p[0], run=K.t("base"))] if len(p) == 4 else []),
                                                     K.enter(p[-3], "pop", run=K.t("fast")),
                                                     K.draw(p[-2], run=K.t("fast")), K.enter(p[-1], "pop", run=K.t("fast"))]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [a_ for _, a_ in arcs] + [p for _, p in pins])
        return anim

    # ---------------------------------------------------------------- converge ---------------------------------
    def m_converge(self, to, sources, direction: str = "in", title: str | None = None, kicker: str | None = None,
                   id: str | None = None):
        """Many places (or people) joined to one: `to` ({label, picture}) in the middle, each of `sources` ({label,
        on}) round it, its arrow drawn in to the middle (or out, `direction: "out"`) as the line names it."""
        tid = id or self._next_id("converge")
        centre_spec = to if isinstance(to, dict) else {"label": str(to or "")}
        specs = [s if isinstance(s, dict) else {"label": str(s)} for s in (sources or [])][:8]
        if not specs:
            return None
        pic = self._pic(centre_spec.get("file"), 1.3, 2.4)
        name = fit(K.head(str(centre_spec.get("label", "")), 30, K.col("card_ink")), 2.6)
        content = (Group if pic is not None else VGroup)(*[m for m in (pic, name) if m is not None]).arrange(DOWN, buff=0.12)
        face = K.card(3.0, content.height + 0.5, stroke=K.col("accent"), stroke_width=3)
        content.move_to(face.face)
        centre = K.group_of(face, content)
        n = len(specs)
        rx, ry = 4.8, 2.3
        made = []
        for k, s in enumerate(specs):
            a = math.pi / 2 - 2 * math.pi * k / n - (math.pi / n if n % 2 == 0 else 0)
            p = np.array([rx * math.cos(a), ry * math.sin(a), 0])
            chip = K.chip(str(s.get("label", "")), K.col("second"), _ink(K.col("second")), 20)
            chip.move_to(p)
            unit = -p / max(np.linalg.norm(p), 1e-6)
            # From the chip's edge facing the middle to the centre card's edge facing the chip.
            start = p + unit * (min(chip.width, chip.height * 3) / 2 + 0.1)
            stop = np.array([math.copysign(min(abs(p[0]) * 0.35, face.width / 2 + 0.12), p[0]),
                             math.copysign(min(abs(p[1]) * 0.6, face.height / 2 + 0.12), p[1]), 0])
            a_, b_ = (start, stop) if direction != "out" else (stop, start)
            arrow = K.arrow_between(a_, b_, K.col("accent"), width=4)
            made.append((s, VGroup(arrow, chip), arrow, chip))
        body = K.group_of(centre, *[m for _, m, _, _ in made])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.enter(centre, "pop")], lag=0.5)
        self._part(tid, centre_spec.get("label"), centre, point=lambda: K.pulse(centre, 1.06))
        for s, m, arrow, chip in made:
            self._part(tid, s.get("label"), m, point=lambda m=m: K.pulse(m, 1.06))
            self._moment(_said(s.get("on"), s.get("label")),
                         lambda heard, arrow=arrow, chip=chip: K.chain([K.enter(chip, "pop", run=K.t("fast")),
                                                                        K.draw(arrow, run=K.t("base"), sfx="swish")]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [m for _, m, _, _ in made])
        return anim

    # ---------------------------------------------------------------- table ------------------------------------
    def m_table(self, columns, rows, title: str | None = None, kicker: str | None = None, highlight=None,
                id: str | None = None):
        """A few columns (2-4) compared row by row: the headings first, then each row ({label, cells, on}) filled
        in as the line says it; the `highlight` column in the stamp colour."""
        P = pl.P
        tid = id or self._next_id("table")
        cols = [str(c) for c in (columns or [])][:4]
        specs = [r for r in (rows or []) if isinstance(r, dict)][:5]
        if len(cols) < 2 or not specs:
            return None
        label_w, total_w = 2.9, 11.6
        cw = (total_w - label_w) / len(cols)
        hot = [str(h).lower() for h in (highlight if isinstance(highlight, list) else [highlight] if highlight else [])]
        heads = VGroup()
        for j, c in enumerate(cols):
            tone = K.col("stamp") if c.lower() in hot else K.col("accent")
            chip = K.chip(c, tone, _ink(tone), 22)
            fit(chip, cw - 0.2)
            chip.move_to([-total_w / 2 + label_w + cw * (j + 0.5), 0, 0])
            heads.add(chip)
        made = []
        y = -0.75
        for k, r in enumerate(specs):
            label = fit(K.head(str(r.get("label", "")), 20, P.CREAM), label_w - 0.2)
            cells = [fit(K.body(str(v), 19, P.CREAM, 18), cw - 0.25) for v in (r.get("cells") or [])[:len(cols)]]
            h = max([label.height] + [c.height for c in cells]) + 0.35
            yc = y - h / 2
            label.move_to([-total_w / 2 + label.width / 2 + 0.1, yc, 0])
            for j, c in enumerate(cells):
                c.move_to([-total_w / 2 + label_w + cw * (j + 0.5), yc, 0])
                if cols[j].lower() in hot:
                    c.set_color(K.col("stamp"))
            rule = Line([-total_w / 2, y, 0], [total_w / 2, y, 0], stroke_color=P.MUTED, stroke_width=1.5)
            made.append((r, VGroup(rule, label, *cells), label, cells))
            y -= h
        body = VGroup(heads, *[m for _, m, _, _ in made])
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([self._title_in(top), K.stagger([K.enter(h, "pop", run=K.t("fast")) for h in heads], lag=0.15)],
                             lag=0.4)
        for r, m, label, cells in made:
            self._part(tid, r.get("label"), m, point=lambda m=m: K.pulse(m, 1.03))
            self._moment(_said(r.get("on"), r.get("label")),
                         lambda heard, m=m, label=label, cells=cells: K.chain([
                             K.together([K.draw(m[0], run=K.t("fast")),
                                         K.timed(FadeIn(label, shift=RIGHT * 0.4, rate_func=ease_out_expo), K.t("base"))]),
                             K.stagger([K.enter(c, "rise", run=K.t("fast")) for c in cells], lag=0.25)]))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [m for _, m, _, _ in made])
        return anim

    # ---------------------------------------------------------------- ask --------------------------------------
    def m_ask(self, text: str, answer: str | None = None, kicker: str | None = "Our question", on: str | None = None,
              id: str | None = None):
        """A question set large beside a question mark; when the line gives its `answer` (`on`, else the answer's
        first words), the answer comes in under it with a tick and the question steps back."""
        P = pl.P
        if id and answer:
            answered = self._answer_ask(id, answer, on)
            if answered is not False:
                return answered
        tid = id or self._next_id("ask")
        disc = Circle(radius=0.62, stroke_width=0, fill_color=K.col("accent"), fill_opacity=1)
        mark = VGroup(disc, K.head("?", 54, _ink(K.col("accent")), upper=False).move_to(disc))
        kick = K.kicker(str(kicker or "Our question"), 18, K.col("accent"))
        words = K.head(pl.wrap(str(text), 30), 40, P.TITLE, upper=False)
        stack = VGroup(kick, words).arrange(DOWN, buff=0.18, aligned_edge=LEFT)
        q = VGroup(mark, stack).arrange(RIGHT, buff=0.45, aligned_edge=UP)
        parts = [q]
        a_line = None
        if answer:
            tick = K.check_mark(0.42, K.col("good"))
            a_words = K.body(str(answer), 28, P.CREAM, 44)
            a_line = VGroup(tick, a_words).arrange(RIGHT, buff=0.3, aligned_edge=UP)
            a_line.next_to(q, DOWN, buff=0.6).align_to(stack, LEFT)
            parts.append(a_line)
        body = VGroup(*parts)
        whole, _ = self._titled(body, None, None)
        h0 = whole.height
        self._fit(whole, self._box(), grow=1.2, margin=0.9)
        whole._m_ask = {"q": q, "stack": stack, "words": words, "k": whole.height / max(h0, 1e-3),
                        "answered": a_line is not None}
        entrance = K.stagger([K.timed(FadeIn(mark, scale=0.3, rate_func=ease_out_back), K.t("fast"), "pop"),
                              K.typewriter(kick, run=0.5), K.typewriter(words, run=min(1.6, 0.03 * len(str(text)) + 0.4))],
                             lag=0.4)
        self._part(tid, text, q, point=lambda: K.pulse(q, 1.04))
        if a_line is not None:
            said = on or " ".join(str(answer).split()[:3])

            def reply(heard):
                return K.chain([K.fade_to(words, 0.55, run=K.t("fast")),
                                K.together([K.draw(a_line[0], run=K.t("fast"), sfx="tick"),
                                            K.typewriter(a_line[1], run=min(2.2, 0.03 * len(str(answer)) + 0.4))])])
            self._moment(_said(said), reply)
        anim = self._show(tid, whole, entrance)
        if a_line is not None:
            self._hold_back(whole, [a_line])
        return anim

    def _answer_ask(self, tid: str, answer: str, on: str | None):
        """The answer to a question still up (an `ask` with the id of the one on the stage, now with its `answer`):
        it comes in under that question, made room for, instead of the question coming on a second time. False when
        that question is not up (or is answered)."""
        import stem

        whole = self._mwhole.get(tid)
        spec = getattr(whole, "_m_ask", None)
        if whole is None or not spec or spec["answered"] or whole is not self.stage_body or not self._shown(whole):
            return False
        spec["answered"] = True
        P = pl.P
        k = spec["k"]
        tick = K.check_mark(0.42, K.col("good"))
        a_words = K.body(str(answer), 28, P.CREAM, 44)
        a_line = VGroup(tick, a_words).arrange(RIGHT, buff=0.3, aligned_edge=UP).scale(k)
        cx, cy, w, h = self._box()
        gap = 0.6 * k
        tall = whole.height + gap + a_line.height
        f = min(1.0, (h - 0.9) / max(tall, 1e-3))
        c0 = np.array(whole.get_center(), dtype=float)
        to = np.array([c0[0], cy + tall * f / 2 - whole.height * f / 2, 0.0])
        # The answer laid out under the question where the question is going: its left under the question's words,
        # its top a gap under the question's foot, both as they will stand (scaled f about the middle, moved).
        a_line.scale(f)
        left = (spec["stack"].get_left()[0] - c0[0]) * f + to[0]
        foot = (spec["q"].get_bottom()[1] - c0[1]) * f + to[1]
        a_line.move_to([left + a_line.width / 2, foot - gap * f - a_line.height / 2, 0.0])
        pl.follow_drift([whole], f, c0, to - c0)
        a_line.set_z_index(Z_TEMPLATE + 1)
        self.stage_pending.append(a_line)
        words = spec["words"]
        room = stem._moving(whole.animate(rate_func=ease_out_cubic).scale(f).move_to(to)) \
            if f < 0.999 or np.linalg.norm(to - c0) > 0.02 else None
        if room is not None:
            # Known as a move to come (a stamp of this beat is placed where the question will stand).
            room._m_room = {"parts": [], "f": f, "c0": c0, "c1": to, "ids": {id(x) for x in whole.get_family()}}
            self._m_moves = [m for m in self.__dict__.get("_m_moves", []) if not m.get("done")] + [room._m_room]

        def reply(heard):
            answer_in = K.together([K.draw(a_line[0], run=K.t("fast"), sfx="tick"),
                                    K.typewriter(a_line[1], run=min(2.2, 0.03 * len(str(answer)) + 0.4))])
            if room is None:
                return K.chain([K.fade_to(words, 0.55, run=K.t("fast")), answer_in])
            # Moved to make room, the question is not stepped back: a group begins all its parts at once, and the
            # fade, begun before the move, held the words where they had been (the answer came in over them).
            return K.chain([K.timed(room, K.t("base"), "swish"), answer_in])
        self._moment(_said(on or " ".join(str(answer).split()[:3])), reply)
        return None
