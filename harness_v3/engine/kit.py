"""The kit's bigger pieces (after v2's kit), each one `ent` a score places freely and the actions bring on part by part:
a piece's parts are its submobjects, so `in soc[1]` brings on the second level as the voice names it, and `in soc
stagger .3` all of them in turn. Places on a piece are `NAME.KEY` (a year on a timeline, a node of a flow), as places
on a map are.

    timeline Y0 Y1          an axis of years; `w`; places: `tl.1347`, `tl.500bc`
    event YEAR "WORDS" on TL     a card on a stem at its year, kept clear of the others (above, else below)
    span Y0 Y1 "WORDS" on TL     a band along the axis
    chart line|bars|donut K:V K:V ...    built from real values; `suffix`, `prefix`, `w`, `h`, `col` (bars upright)
    pyramid "TOP" ... "BOTTOM"   levels, top first; places by their words
    cycle "A" "B" "C"            round a circle, an arrow to the next; `label` in the middle
    flow "A>B>C" "B>D:label"     nodes and arrows laid out in layers (left to right; `down`); `NAME*` a key node;
                                 an arrow's words after `:` on the node it goes to; places by node
    quote "WORDS"                a quotation with a big quote mark; `who`
    doc "TITLE"                  a page of a document; `sub`, `seal`
    title "WORDS"                a section opening: big words on a highlighter, `sub` a small line over them
    labels "PART" "PART" on PIC  a picture's parts named: a dot on each, a line out to its name (where the parts are
                                 is found by a vision model after the pictures are made; `"PART@0.4,0.2"` gives it)
"""

from __future__ import annotations

import math
import re
import zlib

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, RIGHT, UP, AnnularSector, Circle, Dot, Line, Polygon, Rectangle,
                   RoundedRectangle, VGroup, VMobject)

from look import L, STROKE, col, label, soft_shadow, text


def key(s) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower().replace("*", "")).strip("_")


class Keys(dict):
    """Places on a piece by name, matched loosely (`fl.Market`, `fl.market`, `fl.the_market`)."""

    def __contains__(self, k) -> bool:
        return self._find(k) is not None

    def __getitem__(self, k):
        hit = self._find(k)
        if hit is None:
            raise KeyError(k)
        return hit

    def _find(self, k):
        k = key(k)
        if dict.__contains__(self, k):
            return dict.__getitem__(self, k)
        for name in dict.keys(self):
            if k and (name.startswith(k) or name.endswith(k) or k in name.split("_")):
                return dict.__getitem__(self, name)
        return None


def halo(m, width: float = 6):
    """A paper edge round words: they read over lines and colour."""
    return m.set_stroke(col("bg"), width=width, background=True)


def lines_of(words: str, per: int) -> list[str]:
    out, cur = [], ""
    for w in str(words).split():
        if cur and len(cur) + 1 + len(w) > per:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return out + ([cur] if cur else [])


def para(words: str, size: float, width: float, **kw) -> VGroup:
    """Words wrapped to a width, one text a line, centred."""
    per = max(8, int(width / (size * 0.62)))
    g = VGroup(*(text(ln, size, **kw) for ln in lines_of(words, per)))
    g.arrange(DOWN, buff=size * 0.45)
    if g.width > width:
        g.scale_to_fit_width(width)
    return g


def node(words: str, k: float = 1.0, fill=None, sub: str | None = None, min_w: float = 1.6) -> VGroup:
    """A paper card with words in the headline face (a flow's node, a timeline's event)."""
    t = text(str(words).replace("_", " ").upper(), 0.27 * k, color="ink")
    if t.width > 3.4 * k:
        t.scale_to_fit_width(3.4 * k)
    parts = [t]
    if sub:
        s = label(sub, 0.1 * k, "soft")
        parts.insert(0, s)
    inner = VGroup(*parts).arrange(DOWN, buff=0.1 * k)
    w = max(min_w * k, inner.width + 0.5 * k)
    h = inner.height + 0.42 * k
    face = Rectangle(width=w, height=h, fill_color=col(fill or "card"), fill_opacity=1, stroke_color=col("soft"),
                     stroke_width=1.5)
    return VGroup(soft_shadow(face), face, inner.move_to(face))


def tipped(points, color, width: float = STROKE * 0.6, smooth: bool = True) -> VGroup:
    """A line through points with a filled arrowhead at its end."""
    pts = [np.array(p, dtype=float) for p in points]
    line = VMobject(stroke_color=color, stroke_width=width)
    if smooth and len(pts) > 2:
        line.set_points_smoothly(pts)
    else:
        line.set_points_as_corners(pts)
    end = line.point_from_proportion(1.0)
    before = line.point_from_proportion(0.97 if line.get_arc_length() > 0.6 else 0.85)
    d = end - before
    d = d / (np.linalg.norm(d) or 1)
    n = np.array([-d[1], d[0], 0.0])
    s = 0.2
    tip = Polygon(end, end - d * s * 1.3 + n * s * 0.6, end - d * s * 1.3 - n * s * 0.6, fill_color=color,
                  fill_opacity=1, stroke_width=0)
    return VGroup(line, tip)


def edge_point(m, toward) -> np.ndarray:
    """Where the line from a box's middle toward a point leaves the box."""
    c = m.get_center()
    d = np.array(toward, dtype=float) - c
    hw, hh = m.width / 2 + 0.08, m.height / 2 + 0.08
    if abs(d[0]) < 1e-6 and abs(d[1]) < 1e-6:
        return c
    k = min(hw / abs(d[0]) if abs(d[0]) > 1e-6 else 1e9, hh / abs(d[1]) if abs(d[1]) > 1e-6 else 1e9)
    return c + d * k


# ---------------------------------------------------------------- timeline ------------------------------------------

def year_of(s) -> float:
    s = str(s).strip().lower().replace(" ", "")
    m = re.match(r"^(-?\d+(?:\.\d+)?)(bc|bce|ad|ce)?$", s)
    if not m:
        raise ValueError(f"not a year: {s!r} (1347, 500bc)")
    v = float(m.group(1))
    return -v if m.group(2) in ("bc", "bce") else v


def year_words(y: float) -> str:
    y = int(round(y))
    return f"{-y} BC" if y < 0 else str(y)


class _At:
    def __init__(self, f):
        self.f = f

    def get_center(self):
        return self.f()


class _Years:
    def __init__(self, tl):
        self.tl = tl

    def __contains__(self, k) -> bool:
        try:
            year_of(k)
            return True
        except ValueError:
            return False

    def __getitem__(self, k):
        y = year_of(k)
        return _At(lambda: self.tl.point(y))

    def __iter__(self):
        return iter(())


class Timeline(VGroup):
    """An axis of years with ticks; its parts: [axis, ticks]."""

    def __init__(self, y0: float, y1: float, w: float = 11.0, color=None):
        super().__init__()
        self.y0, self.y1 = (y0, y1) if y1 > y0 else (y1, y0)
        span = self.y1 - self.y0
        step = next((s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000) if span / s <= 8), 10000)
        self.axis = Line(LEFT * w / 2, RIGHT * w / 2, stroke_color=col(color or "ink"), stroke_width=STROKE * 0.55)
        ticks = VGroup()
        y = math.ceil(self.y0 / step) * step
        while y <= self.y1 + 1e-9:
            p = self.point(y)
            ticks.add(Line(p + UP * 0.1, p + DOWN * 0.1, stroke_color=col("ink"), stroke_width=STROKE * 0.4),
                      label(year_words(y), 0.12, "soft").move_to(p + DOWN * 0.34))
            y += step
        self.add(self.axis, ticks)
        self.used: list[tuple[float, float, int]] = []     # the events' boxes: (x0, x1, row; + above, - below)
        self.places = _Years(self)

    def point(self, y: float) -> np.ndarray:
        a, b = self.axis.get_start(), self.axis.get_end()
        return a + (b - a) * (y - self.y0) / ((self.y1 - self.y0) or 1)


def event(tl: Timeline, year: str, words: str, mods: dict, c=None) -> VGroup:
    """A card on a stem at its year: above the axis where there is room, else below, else a row further out."""
    y = year_of(year)
    p = tl.point(y)
    card = node(words, float(mods.get("size") or 0.8), fill=mods.get("fill"), sub=year_words(y), min_w=1.2)
    w = card.width
    want = [1, -1] if mods.get("side") != "down" else [-1, 1]
    row = next(r for r in [s * lvl for lvl in (1, 2, 3, 4) for s in want]
               if all(r != u[2] or p[0] + w / 2 + 0.12 < u[0] or u[1] < p[0] - w / 2 - 0.12 for u in tl.used))
    tl.used.append((p[0] - w / 2, p[0] + w / 2, row))
    sign = 1 if row > 0 else -1
    # (below the axis, clear of the years and of a span's words)
    dy = 0.55 + (abs(row) - 1) * (card.height + 0.25) + card.height / 2 + (0.75 if sign < 0 else 0)
    card.move_to(p + UP * sign * dy)
    edge = card.get_bottom() if sign > 0 else card.get_top()
    colour = col(c or "ink")
    stem = VGroup(Line(p, [p[0], edge[1], 0], stroke_color=colour, stroke_width=STROKE * 0.35),
                  Dot(p, radius=0.08, color=col(c or "accent")).set_stroke(col("ink"), width=2))
    return VGroup(stem, card)


def span(tl: Timeline, a: str, b: str, words: str, mods: dict, c=None) -> VGroup:
    pa, pb = tl.point(year_of(a)), tl.point(year_of(b))
    band = Rectangle(width=max(0.08, abs(pb[0] - pa[0])), height=0.24, fill_color=col(c or "accent"),
                     fill_opacity=float(mods.get("opacity", 0.85)), stroke_width=0).move_to((pa + pb) / 2)
    side = DOWN if mods.get("side") == "down" else UP
    t = halo(label(words, float(mods.get("size") or 0.12), "ink")).next_to(band, side, buff=0.12 if side is UP else 0.5)
    return VGroup(band, t)


# ---------------------------------------------------------------- charts --------------------------------------------

PALETTE = ["accent", "coral", "teal", "navy", "sky", "green", "soft"]


def _data(args) -> list[tuple[str, float]]:
    out = []
    for a in args:
        if ":" not in a:
            continue
        k, v = a.rsplit(":", 1)
        try:
            out.append((k.replace("_", " "), float(v.replace(",", ""))))
        except ValueError:
            continue
    if not out:
        raise ValueError("a chart needs values: KEY:VALUE (1300:73 England:2)")
    return out


def _fmt(v: float, mods: dict) -> str:
    s = f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"
    return f"{mods.get('prefix', '')}{s}{mods.get('suffix', '')}"


def chart(args: list[str], mods: dict, c=None) -> VGroup:
    how = args[0] if args and ":" not in args[0] else "bars"
    data = _data(args)
    if how == "line":
        return _line(data, mods, c)
    if how == "donut":
        return _donut(data, mods)
    return _bars(data, mods, c)


def _line(data, mods, c) -> VGroup:
    w, h = float(mods.get("w", 7)), float(mods.get("h", 3.4))
    try:
        xs = [float(k) for k, _ in data]
    except ValueError:
        xs = list(range(len(data)))
    x0, x1 = min(xs), max(xs)
    top = max(v for _, v in data) * 1.12 or 1
    pts = [np.array([-w / 2 + w * (x - x0) / ((x1 - x0) or 1), -h / 2 + h * v / top, 0.0]) for x, (_, v) in zip(xs, data)]
    base = Line([-w / 2 - 0.2, -h / 2, 0], [w / 2 + 0.2, -h / 2, 0], stroke_color=col("soft"), stroke_width=2)
    colour = col(c or "ink")
    g = VGroup()
    for i, (p, (k, v)) in enumerate(zip(pts, data)):
        dot = Dot(p, radius=0.09, color=col("accent")).set_stroke(colour, width=2.5)
        val = text(_fmt(v, mods), 0.24, bold=True).next_to(dot, UP, buff=0.14)
        xl = label(k, 0.12, "soft").move_to([p[0], -h / 2 - 0.3, 0])
        part = VGroup(base) if i == 0 else VGroup(Line(pts[i - 1], p, stroke_color=colour, stroke_width=STROKE * 0.7))
        part.add(dot, halo(val), xl)
        g.add(part)
    return g


def _bars(data, mods, c) -> VGroup:
    w, h = float(mods.get("w", 7)), float(mods.get("h", 3.4))
    top = max(v for _, v in data) or 1
    big = max(range(len(data)), key=lambda i: data[i][1])
    g = VGroup()
    if mods.get("col"):                                 # upright columns over a baseline
        n = len(data)
        cw = min(1.1, w / n * 0.6)
        for i, (k, v) in enumerate(data):
            x = -w / 2 + w * (i + 0.5) / n
            bh = max(0.04, (h - 0.6) * v / top)
            bar = Rectangle(width=cw, height=bh, fill_color=col(c or ("accent" if i == big else "grey" if "grey" in L else "soft")),
                            fill_opacity=1, stroke_width=0).move_to([x, -h / 2 + bh / 2, 0])
            g.add(VGroup(bar, text(_fmt(v, mods), 0.22, bold=True).next_to(bar, UP, buff=0.1),
                         label(k, 0.11, "ink").move_to([x, -h / 2 - 0.28, 0])))
        return g
    n = len(data)
    row = min(0.9, h / n)
    lw = 1.9
    full = w - lw - 1.3
    for i, (k, v) in enumerate(data):
        y = h / 2 - row * (i + 0.5)
        name = label(k, 0.13, "ink")
        name.move_to([-w / 2 + lw - name.width / 2 - 0.15, y, 0])
        bw = max(0.05, full * v / top)
        bar = Rectangle(width=bw, height=row * 0.58, fill_color=col(c or ("accent" if i == big else "grey" if "grey" in L else "soft")),
                        fill_opacity=1, stroke_width=0).move_to([-w / 2 + lw + bw / 2, y, 0])
        val = text(_fmt(v, mods), 0.22, bold=True).next_to(bar, RIGHT, buff=0.15)
        g.add(VGroup(name, bar, val))
    return g


def _hit(a, b, gap: float = 0.08) -> bool:
    return not (a.get_right()[0] + gap < b.get_left()[0] or b.get_right()[0] + gap < a.get_left()[0]
                or a.get_top()[1] + gap < b.get_bottom()[1] or b.get_top()[1] + gap < a.get_bottom()[1])


def _donut(data, mods) -> VGroup:
    r = float(mods.get("r", 1.6))
    total = sum(v for _, v in data) or 1
    g = VGroup()
    a = math.pi / 2
    for i, (k, v) in enumerate(data):
        ang = math.tau * v / total
        sec = AnnularSector(inner_radius=r * 0.56, outer_radius=r, angle=-ang, start_angle=a,
                            fill_color=col(PALETTE[i % len(PALETTE)]), fill_opacity=1, stroke_color=col("bg"),
                            stroke_width=3)
        mid = a - ang / 2
        d = np.array([math.cos(mid), math.sin(mid), 0.0])
        t = label(f"{k} {_fmt(v, mods)}", 0.13, "ink")
        for out in (0.3, 0.6, 0.9, 1.2):               # a small slice beside another: its name further out
            t.move_to(d * (r + out) + RIGHT * (t.width / 2 if d[0] >= 0 else -t.width / 2) * (abs(d[0]) > 0.25))
            if not any(_hit(t, o[1]) for o in g):
                break
        g.add(VGroup(sec, halo(t)))
        a -= ang
    if mods.get("label"):
        g.add(text(str(mods["label"]).upper(), 0.24, bold=True).move_to(ORIGIN))
    return g


# ---------------------------------------------------------------- diagrams ------------------------------------------

def pyramid(levels: list[str], mods: dict, c=None) -> VGroup:
    """Levels, the top first: the top a triangle, each one under it wider (`inverted`: the other way up)."""
    w, h = float(mods.get("w", 6)), float(mods.get("h", 4))
    n = max(1, len(levels))
    gap = 0.07
    lh = (h - gap * (n - 1)) / n
    fills = [c or "accent", "sand", "card", "sand", "card", "sand"]
    g = VGroup()
    g.places = Keys()
    for i, words in enumerate(levels):
        y_top = h / 2 - i * (lh + gap)
        y_bot = y_top - lh
        wt = w * (i / n) if not mods.get("inverted") else w * (1 - i / n)
        wb = w * ((i + 1) / n) if not mods.get("inverted") else w * (1 - (i + 1) / n)
        pts = [[-wt / 2, y_top, 0], [wt / 2, y_top, 0], [wb / 2, y_bot, 0], [-wb / 2, y_bot, 0]]
        if wt < 0.01:
            pts = [[0, y_top, 0], [wb / 2, y_bot, 0], [-wb / 2, y_bot, 0]]
        if wb < 0.01:
            pts = [[-wt / 2, y_top, 0], [wt / 2, y_top, 0], [0, y_bot, 0]]
        shape = Polygon(*pts, fill_color=col(fills[i % len(fills)]), fill_opacity=1, stroke_color=col("soft"),
                        stroke_width=1.5)
        room = max(wt, wb) * (0.42 if min(wt, wb) < 0.01 else 0.8)
        t = text(str(words).replace("_", " ").upper(), min(0.3, lh * 0.3), color="ink")
        if t.width > room:
            t.scale_to_fit_width(room)
        ty = (y_bot + lh * 0.33) if (wt < 0.01) else (y_top - lh * 0.33) if wb < 0.01 else (y_top + y_bot) / 2
        t.move_to([0, ty, 0])
        part = VGroup(shape, t)
        g.add(part)
        g.places[key(words)] = part
    return g


def cycle(items: list[str], mods: dict, c=None) -> VGroup:
    """Things round a circle, clockwise from the top, each with an arrow on to the next (the last back to the
    first). Parts: the first node; then each arrow with the node it reaches (the last also the arrow home)."""
    n = len(items)
    r = float(mods.get("r", 2.0))
    rx, ry = r * 1.3, r
    nodes = [node(it, float(mods.get("size") or 0.9)) for it in items]
    th = [math.pi / 2 - math.tau * i / n for i in range(n)]
    for nd, t in zip(nodes, th):
        nd.move_to([rx * math.cos(t), ry * math.sin(t), 0])
    colour = col(c or "ink")

    def arc(i):
        j = (i + 1) % n
        da = (max(nodes[i].width, nodes[i].height) / 2 + 0.25) / r
        db = (max(nodes[j].width, nodes[j].height) / 2 + 0.3) / r
        a0, a1 = th[i] - min(da, math.pi / n * 0.8), th[i] - math.tau / n + min(db, math.pi / n * 0.8)
        pts = [[rx * math.cos(a0 + (a1 - a0) * s), ry * math.sin(a0 + (a1 - a0) * s), 0] for s in np.linspace(0, 1, 12)]
        return tipped(pts, colour)
    g = VGroup(VGroup(nodes[0]))
    for i in range(1, n):
        part = VGroup(arc(i - 1), nodes[i])
        if i == n - 1 and n > 1:
            part.add(arc(n - 1))
        g.add(part)
    g.places = Keys({key(it): nd for it, nd in zip(items, nodes)})
    if mods.get("label"):
        g.add(text(str(mods["label"]).upper(), 0.3, bold=True))
    return g


def flow(args: list[str], mods: dict, c=None) -> VGroup:
    """A flow diagram: `"farm>market>town"` (a chain), `"market>lord:rent"` (an arrow with its words), `"farm"` (a
    node alone); `town*` a key node. Laid out in layers by the longest way in (left to right, or `down`), each layer's
    nodes in the order of what leads to them. Parts: the nodes in that order, each with the arrows that join it to
    the ones before."""
    order: list[str] = []
    stars: set[str] = set()
    edges: list[tuple[str, str, str]] = []

    def name(s):
        s = s.strip()
        if s.endswith("*"):
            s = s[:-1].strip()
            stars.add(s)
        if s and s not in order:
            order.append(s)
        return s
    for tok in args:
        segs = [x for x in tok.split(">")]
        prev = None
        for seg in segs:
            nm, _, words = seg.partition(":")
            nm = name(nm)
            if not nm:
                continue
            if prev is not None:
                edges.append((prev, nm, words.strip()))
            prev = nm
    if not order:
        raise ValueError('a flow needs nodes: "a>b>c"')
    # Layers by the longest way in, an arrow back to a node already on the way (a loop) set aside.
    succ = {n: [b for a, b, _ in edges if a == n] for n in order}
    back: set[tuple[str, str]] = set()
    state: dict[str, int] = {}

    def visit(u):
        state[u] = 1
        for v in succ[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif v not in state:
                visit(v)
        state[u] = 2
    for n in order:
        if n not in state:
            visit(n)
    layer = {n: 0 for n in order}
    for _ in range(len(order)):
        for a, b, _w in edges:
            if (a, b) not in back and a != b:
                layer[b] = max(layer[b], layer[a] + 1)
    k = float(mods.get("size") or 1.0)
    boxes = {n: node(n, k, fill=("accent" if n in stars else None)) for n in order}
    down = bool(mods.get("down"))
    nl = max(layer.values()) + 1
    cols = [[n for n in order if layer[n] == i] for i in range(nl)]
    said = max([label(w, 0.11 * k, "ink").width for _, _, w in edges if w] or [0])
    along = ((max(b.height for b in boxes.values()) + 1.0) if down
             else (max(b.width for b in boxes.values()) + max(1.2, said + 0.6)))
    across = (max(b.width for b in boxes.values()) + 0.5) if down else (max(b.height for b in boxes.values()) + 0.7)
    pos: dict[str, float] = {}
    for i, col_ in enumerate(cols):
        if i:   # under what leads to them, on average (fewer crossings)
            col_.sort(key=lambda n: np.mean([pos[a] for a, b, _ in edges if b == n and a in pos] or [0]))
        for j, n in enumerate(col_):
            pos[n] = (j - (len(col_) - 1) / 2) * across
            p = np.array([pos[n], -i * along, 0.0]) if down else np.array([i * along, -pos[n], 0.0])
            boxes[n].move_to(p)
    colour = col(c or "ink")
    arrows: dict[tuple[str, str], VGroup] = {}
    for a, b, words in edges:
        A, B = boxes[a], boxes[b]
        same = layer[a] == layer[b] or (a, b) in back
        p0, p1 = edge_point(A, B.get_center()), edge_point(B, A.get_center())
        if same:                    # a loop or a step within a layer: bowed aside
            d = p1 - p0
            nrm = np.array([-d[1], d[0], 0.0]) / (np.linalg.norm(d) or 1)
            mid = (p0 + p1) / 2 + nrm * max(0.8, np.linalg.norm(d) * 0.3)
            p0, p1 = edge_point(A, mid), edge_point(B, mid)
            ar = tipped([p0, mid, p1], colour)
        else:
            ar = tipped([p0, p1], colour, smooth=False)
        if words:
            t = halo(label(words, 0.11 * k, "ink"))
            mid = ar[0].point_from_proportion(0.5)
            d = p1 - p0
            nrm = np.array([-d[1], d[0], 0.0]) / (np.linalg.norm(d) or 1)
            t.move_to(mid + nrm * 0.22 * (1 if nrm[1] >= 0 else -1))
            ar.add(t)
        arrows[(a, b)] = ar
    shown = [n for col_ in cols for n in col_]
    rank = {n: i for i, n in enumerate(shown)}
    g = VGroup()
    for n in shown:
        part = VGroup(*(ar for (a, b), ar in arrows.items() if max(rank[a], rank[b]) == rank[n]), boxes[n])
        g.add(part)
    g.move_to(ORIGIN)
    w, h = float(mods.get("w", 12)), float(mods.get("h", 5.6))
    if g.width > w or g.height > h:
        g.scale(min(w / g.width, h / g.height))
    g.places = Keys({key(n): boxes[n] for n in order})
    return g


# ---------------------------------------------------------------- paper things --------------------------------------

def quote(words: str, mods: dict, c=None) -> VGroup:
    w = float(mods.get("w", 8))
    size = float(mods.get("size") or 0.4)
    body = para(f"{words}", size, w, serif=True, italic=True, color=c or "ink")
    mark = text("“", size * 1.5, bold=True, color="accent", font=L.get("font"))
    mark.next_to(body, LEFT, buff=0.2).align_to(body, UP).shift(UP * size * 0.4)
    g = VGroup(mark, body)
    if mods.get("who"):
        g.add(label(f"— {mods['who']}", 0.14, "soft").next_to(body, DOWN, buff=0.3).align_to(body, RIGHT))
    return g


def doc(title: str, mods: dict, c=None) -> VGroup:
    w, h = float(mods.get("w", 3.2)), float(mods.get("h", 4.2))
    face = Rectangle(width=w, height=h, fill_color=col(mods.get("fill") or "card"), fill_opacity=1,
                     stroke_color=col("sand"), stroke_width=1.5)
    head = VGroup(para(title.upper(), 0.22, w * 0.8, color="ink"))
    if mods.get("sub"):
        head.add(label(str(mods["sub"]), 0.1, "soft"))
    head.arrange(DOWN, buff=0.12).move_to(face.get_top() + DOWN * (0.3 + head.height / 2))
    rng = np.random.default_rng(zlib.crc32(title.encode()) % 997)
    rows = VGroup()
    y = head.get_bottom()[1] - 0.35
    while y > face.get_bottom()[1] + 0.4:
        lw = w * 0.76 * (rng.uniform(0.55, 1.0) if rng.random() < 0.3 else 1.0)
        rows.add(RoundedRectangle(width=lw, height=0.07, corner_radius=0.035, fill_color=col("soft"), fill_opacity=0.55,
                                  stroke_width=0).move_to([face.get_left()[0] + w * 0.12 + lw / 2, y, 0]))
        y -= 0.24
    g = VGroup(VGroup(soft_shadow(face), face), head, rows)
    if mods.get("seal"):
        s = Circle(radius=0.38, fill_color=col(c or "red"), fill_opacity=1, stroke_width=0)
        ring = Circle(radius=0.29, stroke_color=col("white"), stroke_width=2, fill_opacity=0)
        letter = text(title.strip()[:1].upper(), 0.24, bold=True, color="white")
        g.add(VGroup(s, ring, letter.move_to(s)).move_to(face.get_corner(DOWN + RIGHT) + np.array([-0.55, 0.6, 0])))
    if "rot" not in mods:
        g.rotate(math.radians(-2))          # a page laid on the paper, a little askew
    return g


def title(words: str, mods: dict, c=None) -> VGroup:
    size = float(mods.get("size") or 0.85)
    t = text(words.upper(), size, bold=True, color="ink")
    if mods.get("width") and t.width > float(mods["width"]):
        t.scale_to_fit_width(float(mods["width"]))
    bar = Rectangle(width=t.width + 0.4, height=t.height * 0.55, fill_color=col(c or "accent"), fill_opacity=1,
                    stroke_width=0)
    bar.move_to(t.get_bottom() + UP * bar.height * 0.45)
    g = VGroup(bar, t)
    if mods.get("sub"):
        g.add(label(str(mods["sub"]), 0.16, "ink").next_to(t, UP, buff=0.3).align_to(t, LEFT))
    return g


# ---------------------------------------------------------------- a picture's parts named ---------------------------

def labels(pic, names: list[str], mods: dict, c=None, screen: tuple[float, float] | None = None) -> VGroup:
    """Each part of a picture named: a dot where it is, a line out to its name beside the picture (left of it for a
    part on its left half). Where a part is: `"NAME@X,Y"` (0..1 from the picture's top left), else as found in the
    picture by a vision model (the assets step, kept beside the picture), else spread down its middle."""
    ul, dr = pic.get_corner(UP + LEFT), pic.get_corner(DOWN + RIGHT)
    found = getattr(pic, "spots", {}) or {}
    spots = []
    for i, raw in enumerate(names):
        nm, _, at = raw.partition("@")
        fx, fy = None, None
        if at:
            try:
                fx, fy = (float(v) for v in at.split(","))
            except ValueError:
                pass
        if fx is None and key(nm) in found:
            fx, fy = found[key(nm)]
        if fx is None:
            fx, fy = 0.5, (i + 1) / (len(names) + 1)
        p = np.array([ul[0] + (dr[0] - ul[0]) * fx, ul[1] + (dr[1] - ul[1]) * fy, 0.0])
        side = -1 if fx < 0.5 else 1
        if screen:                          # a name that would run off the screen goes on the other side
            tw = label(nm.replace("_", " "), float(mods.get("size") or 0.15)).width + 0.45
            if side < 0 and ul[0] - tw < screen[0]:
                side = 1
            elif side > 0 and dr[0] + tw > screen[1]:
                side = -1
        spots.append((nm.replace("_", " "), p, side))
    colour = col(c or "ink")
    size = float(mods.get("size") or 0.15)
    out: list[VGroup | None] = [None] * len(spots)
    for side in (-1, 1):
        mine = sorted([i for i, s in enumerate(spots) if s[2] == side], key=lambda i: -spots[i][1][1])
        ys: list[float] = []
        for i in mine:
            y = spots[i][1][1]
            if ys and ys[-1] - y < 0.42:
                y = ys[-1] - 0.42
            ys.append(y)
        for i, y in zip(mine, ys):
            nm, p, _ = spots[i]
            t = halo(label(nm, size, "ink"))
            x = (ul[0] - 0.35 - t.width / 2) if side < 0 else (dr[0] + 0.35 + t.width / 2)
            t.move_to([x, y, 0])
            end = np.array([x + (t.width / 2 + 0.1) * (1 if side < 0 else -1), y, 0])
            dot = Dot(p, radius=0.07, color=colour).set_stroke(col("bg"), width=4, background=True)
            ln = Line(p, end, stroke_color=colour, stroke_width=STROKE * 0.35)
            out[i] = VGroup(dot, ln, t)
    return VGroup(*out)
