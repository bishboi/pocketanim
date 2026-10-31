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


def even(words: str, size: float, bold: bool = False, color="ink"):
    """Words whose capitals are `size` tall whatever letters they hold (rows of a table, a list, a comparison read as
    one size; `text` fits each one's own height)."""
    from manim import BOLD, NORMAL, Text
    from look import for_script
    kw = dict(font=for_script(words, L["font"]), weight=BOLD if bold else NORMAL, font_size=48)
    ref = Text("H", **kw)
    t = Text(str(words), color=col(color), **kw)
    return t.scale(size / max(ref.height, 0.01))


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
    # Above the axis first (two rows), then below: a timeline low on the screen keeps its cards on it.
    order = [1, 2, -1, -2, 3, -3, 4, -4] if mods.get("side") != "down" else [-1, -2, 1, 2, -3, 3, -4, 4]
    row = next(r for r in order
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
    from look import grouped
    s = grouped(v, 0 if float(v).is_integer() else 1)
    return f"{mods.get('prefix', '')}{s}{mods.get('suffix', '')}"


def chart(args: list[str], mods: dict, c=None) -> VGroup:
    how = args[0] if args and ":" not in args[0] else "bars"
    data = _data(args)
    if how == "line":
        return _line(data, mods, c)
    if how == "donut":
        return _donut(data, mods)
    if how in ("stack", "waffle"):
        return (stack if how == "stack" else waffle)(data, mods, c)
    if how in ("scatter", "area"):
        import kit2
        return getattr(kit2, how)(data, mods, c)
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
    def crosses(p0, mid, p1, skip) -> bool:
        """Whether the arrow (through `mid`, or straight) runs over a card that is not its own."""
        ctrl = 2 * mid - (p0 + p1) / 2 if mid is not None else (p0 + p1) / 2
        for t in np.linspace(0.08, 0.92, 24):
            q = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * ctrl + t ** 2 * p1
            for n, bx in boxes.items():
                if n in skip:
                    continue
                c_ = bx.get_center()
                if abs(q[0] - c_[0]) < bx.width / 2 + 0.1 and abs(q[1] - c_[1]) < bx.height / 2 + 0.1:
                    return True
        return False
    for a, b, words in edges:
        A, B = boxes[a], boxes[b]
        same = layer[a] == layer[b] or (a, b) in back
        p0, p1 = edge_point(A, B.get_center()), edge_point(B, A.get_center())
        d = p1 - p0
        nrm = np.array([-d[1], d[0], 0.0]) / (np.linalg.norm(d) or 1)
        mid = None
        if same:                    # a loop or a step within a layer: bowed aside
            mid = (p0 + p1) / 2 + nrm * max(0.8, np.linalg.norm(d) * 0.3)
        elif crosses(p0, None, p1, {a, b}):
            # an arrow past a layer would run over the cards between: bowed round them, the side with room
            for bow in (0.6, 0.9, 1.2, 1.6, 2.0, 2.6):
                hit = None
                for side in (1, -1):
                    cand = (p0 + p1) / 2 + nrm * side * max(bow, np.linalg.norm(d) * bow * 0.25)
                    q0, q1 = edge_point(A, cand), edge_point(B, cand)
                    if not crosses(q0, cand, q1, {a, b}):
                        hit = cand
                        break
                if hit is not None:
                    mid = hit
                    break
            if mid is None:
                mid = (p0 + p1) / 2 + nrm * max(2.0, np.linalg.norm(d) * 0.5)
        if mid is not None:
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
        part.core = boxes[n]
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

def _land_spots(m, n: int) -> list:
    """n points spread over a map's own country (or its land), far apart: where unnamed parts are pointed at."""
    try:
        import geo
        from shapely.geometry import Point
        try:
            g, _ = geo.shape(m.region_name, None, m.bounds)
            g = g.intersection(m.clip)
        except Exception:  # noqa: BLE001
            g = m.land_g.intersection(m.clip)
        if g.is_empty:
            return []
        g = g.buffer(-0.04 * m.span) if not g.buffer(-0.04 * m.span).is_empty else g
        x0, y0, x1, y1 = g.bounds
        cand = [(x0 + (x1 - x0) * (i + 0.5) / 14, y0 + (y1 - y0) * (j + 0.5) / 14) for i in range(14) for j in range(14)]
        cand = [c for c in cand if g.contains(Point(*c))]
        if not cand:
            return []
        c0 = g.representative_point()
        picks = [min(cand, key=lambda c: (c[0] - c0.x) ** 2 + (c[1] - c0.y) ** 2)]
        while len(picks) < min(n, len(cand)):     # each next one the farthest from those picked
            picks.append(max(cand, key=lambda c: min((c[0] - q[0]) ** 2 + (c[1] - q[1]) ** 2 for q in picks)))
        return [np.array(m.to_screen(x, y), dtype=float) for x, y in picks]
    except Exception:  # noqa: BLE001
        return []


def labels(pic, names: list[str], mods: dict, c=None, screen: tuple[float, float] | None = None) -> VGroup:
    """Each part of a picture or a map named: the part lit (on a map, a named region shaded; else a soft ring round
    the spot), a dot on it, a line out to its name. Where a part is: `"NAME@X,Y"` (0..1 from the picture's top
    left), else as found in the picture by a vision model (the assets step), else on a map the place or region of
    that name, else spread over the picture. The names go beside the picture when the screen has room there, else
    on the picture as paper chips beside their parts (never off the screen). Each label is its own part: they come
    on one after another."""
    from manim import RoundedRectangle
    import look
    found = getattr(pic, "spots", {}) or {}
    pic = getattr(pic, "frame_of", pic)        # the picture itself, not its credit line
    is_map = isinstance(pic, look.GeoMap)
    ul, dr = pic.get_corner(UP + LEFT), pic.get_corner(DOWN + RIGHT)
    pw, ph = dr[0] - ul[0], ul[1] - dr[1]
    colour = col(c or "accent")
    size = float(mods.get("size") or 0.2)
    spots = []                                  # (name, point, lit part or None)
    free = [(0.32, 0.3), (0.68, 0.36), (0.4, 0.62), (0.7, 0.7), (0.25, 0.8), (0.55, 0.18), (0.5, 0.5)]
    for i, raw in enumerate(names):
        nm, _, at = raw.partition("@")
        fx = fy = None
        lit = None
        if at:
            try:
                fx, fy = (float(v) for v in at.split(","))
            except ValueError:
                pass
        if fx is None and key(nm) in found:
            fx, fy = found[key(nm)]
        p = None
        proper = nm[:1].isupper()               # a name (Brittany, Alps), not a kind of land (forests, plains)
        if fx is None and is_map and proper:    # a region of that name shaded, or a place of that name
            try:
                lit = look.region(pic, nm, {"opacity": 0.4}, c or "accent")
                p = np.array(lit.anchor, dtype=float)
            except Exception:  # noqa: BLE001
                lit = None
                try:
                    q = pic.places[nm].get_center()
                    if nm not in pic.places.outside:
                        p = np.array(q, dtype=float)
                except Exception:  # noqa: BLE001
                    p = None
        if p is None and fx is None and is_map:  # a part of the land with no name of its own: spread over the country
            n0 = getattr(pic, "_label_n", 0)      # (other labels on this map took the first spots)
            land = _land_spots(pic, n0 + len(names))
            if land:
                p = land[(n0 + i) % len(land)]
        if p is None:
            if fx is None:
                fx, fy = free[i % len(free)]
            p = np.array([ul[0] + pw * fx, ul[1] - ph * fy, 0.0])
        spots.append((nm.replace("_", " "), p, lit))
    # where the names go: beside the picture if the screen has room there, else on it
    words = [halo(label(nm, size, "ink"), 7) for nm, _, _ in spots]
    widest = max((t.width for t in words), default=0) + 0.6
    room_l = screen is None or ul[0] - widest >= screen[0]
    room_r = screen is None or dr[0] + widest <= screen[1]
    out = []
    # chips and names already set on this picture (by this line or another labels line on it): none lands on another
    if not hasattr(pic, "_label_chips"):
        pic._label_chips, pic._label_ys = [], {-1: [], 1: []}
    placed = pic._label_chips
    for (nm, p, lit), t in zip(spots, words):
        side = -1 if p[0] < (ul[0] + dr[0]) / 2 else 1
        part = VGroup()
        if lit is not None:
            part.add(lit)
        else:                                   # a soft ring round the spot: the part it names
            part.add(Circle(radius=0.32, fill_color=colour, fill_opacity=0.28, stroke_color=colour, stroke_width=3)
                     .move_to(p))
        dot = Dot(p, radius=0.075, color=col("ink")).set_stroke(col("bg"), width=4, background=True)
        outside = (room_l if side < 0 else room_r) or (room_r if side < 0 else room_l)
        if outside:
            if not (room_l if side < 0 else room_r):
                side = -side
            x = (ul[0] - 0.35 - t.width / 2) if side < 0 else (dr[0] + 0.35 + t.width / 2)
            y = p[1]
            for _ in range(20):                 # names on one side kept a line apart
                near = [y_ for y_ in pic._label_ys[side] if abs(y_ - y) < t.height + 0.22]
                if not near:
                    break
                y = min(near) - (t.height + 0.24) if y <= max(near) else max(near) + t.height + 0.24
            pic._label_ys[side].append(y)
            t.move_to([x, y, 0])
            chip = t
            end = np.array([x + (t.width / 2 + 0.1) * (1 if side < 0 else -1), y, 0])
        else:                                   # a paper chip on the picture beside its part, clear of the others
            box = RoundedRectangle(width=t.width + 0.3, height=t.height + 0.24, corner_radius=0.08, fill_color=col("bg"),
                                   fill_opacity=0.96, stroke_color=col("ink"), stroke_width=1.6)
            chip = VGroup(box, t.move_to(box))
            cw, ch = chip.width, chip.height
            x_lo, x_hi = ul[0] + cw / 2 + 0.1, dr[0] - cw / 2 - 0.1
            y_lo, y_hi = dr[1] + ch / 2 + 0.1, ul[1] - ch / 2 - 0.1
            if screen is not None and len(screen) == 4:
                x_lo, x_hi = max(x_lo, screen[0] + cw / 2), min(x_hi, screen[1] - cw / 2)
                y_lo, y_hi = max(y_lo, screen[2] + ch / 2), min(y_hi, screen[3] - ch / 2)
            dots = [q for _, q, _ in spots]

            def clash(c_):
                if any(abs(c_[0] - b[0]) < (cw + b[2]) / 2 + 0.1 and abs(c_[1] - b[1]) < (ch + b[3]) / 2 + 0.1
                       for b in placed):
                    return 2.0
                return sum(1.0 for q in dots if abs(c_[0] - q[0]) < cw / 2 + 0.3 and abs(c_[1] - q[1]) < ch / 2 + 0.3)
            best, score = None, 1e9
            for dist in (0.6, 0.95, 1.4, 1.9):
                for ang in (135, 45, 180, 0, 225, 315, 90, 270):
                    if side > 0:
                        ang = 180 - ang     # (a part on the right: its name to its left first)
                    r_ = math.radians(ang)
                    c_ = p + np.array([math.cos(r_) * (dist + cw / 2), math.sin(r_) * (dist * 0.8 + ch / 2), 0.0])
                    c_[0] = min(max(c_[0], x_lo), x_hi)
                    c_[1] = min(max(c_[1], y_lo), y_hi)
                    sc_ = clash(c_) * 10 + dist
                    if sc_ < score:
                        best, score = c_, sc_
                if score < 10:
                    break
            at = best
            chip.move_to(at)
            placed.append((at[0], at[1], cw, ch))
            end = np.array([at[0] + (cw / 2) * (1 if at[0] < p[0] else -1), at[1], 0.0])
            if abs(at[0] - p[0]) < cw / 2:      # right over or under it: the line to the chip's near edge
                end = np.array([p[0], at[1] + (ch / 2) * (1 if at[1] < p[1] else -1), 0.0])
        ln = Line(p, end, stroke_color=col("ink"), stroke_width=STROKE * 0.35)
        part.add(ln, dot, chip)
        out.append(part)
    pic._label_n = getattr(pic, "_label_n", 0) + len(names)
    return VGroup(*out)


# ---------------------------------------------------------------- lists, tables, comparisons -------------------------

def compare(args: list[str], mods: dict, c=None) -> VGroup:
    """Two sides and their rows: `compare "manor" "town" "labour:wages" "lord:guild"`. Parts: the heads, then a row
    each (left, an arrow, right). The left words end and the right words start either side of a gap the arrows
    cross, so long words never run into them."""
    heads = [a for a in args if ":" not in a][:2] or ["before", "after"]
    rows = [a.split(":", 1) for a in args if ":" in a]
    size = float(mods.get("size") or 0.24)
    lefts = [even(a.replace("_", " "), size) for a, _ in rows]
    rights = [even(b.replace("_", " "), size, bold=True) for _, b in rows]
    hl = even(heads[0].replace("_", " ").upper(), size * 1.45, bold=True)
    hr = even(heads[-1].replace("_", " ").upper(), size * 1.45, bold=True)
    gap = 0.6 + size * 4                                  # the arrows' room in the middle
    head = VGroup()
    for t, colour, side in ((hl, "soft", -1), (hr, c or "accent", 1)):
        t.move_to([side * (gap / 2 + t.width / 2), 0, 0])
        bar = Rectangle(width=t.width + 0.3, height=0.12, fill_color=col(colour), fill_opacity=1, stroke_width=0)
        head.add(VGroup(t, bar.next_to(t, DOWN, buff=0.1)))
    g = VGroup(head)
    g.places = Keys()
    y = -0.85
    for (a, b), la, lb in zip(rows, lefts, rights):
        la.move_to([-gap / 2 - la.width / 2, y, 0])
        lb.move_to([gap / 2 + lb.width / 2, y, 0])
        ar = tipped([[-gap / 2 + 0.2, y, 0], [gap / 2 - 0.2, y, 0]], col("soft"), STROKE * 0.4, smooth=False)
        row = VGroup(la, ar, lb)
        row.core = VGroup(la, lb)
        g.add(row)
        g.places[f"r{len(g) - 1}"] = row
        g.places[key(a)] = la
        g.places[key(b)] = lb
        y -= size * 3.1
    return g.move_to(ORIGIN)


def table(args: list[str], mods: dict, c=None) -> VGroup:
    """Rows of cells split by `|`, the first the heads: `table "crop|season" "wheat|autumn"`. Parts: a row each;
    cells are TABLE.r2c1 (row 2, column 1; the heads are row 0)."""
    rows = [[x.strip().replace("_", " ") for x in a.split("|")] for a in args]
    n = max(len(r) for r in rows)
    size = float(mods.get("size") or 0.24)
    cells = [[even(x.upper() if i == 0 else x, size * (0.9 if i == 0 else 1), bold=i == 0)
              for x in r + [""] * (n - len(r))] for i, r in enumerate(rows)]
    cw = [max(cells[i][j].width for i in range(len(rows))) + 0.6 for j in range(n)]
    rh = size * 2.4
    total = sum(cw)
    g = VGroup()
    g.places = Keys()
    for i, r in enumerate(cells):
        y = -i * rh
        band = Rectangle(width=total, height=rh, stroke_width=0, fill_opacity=1,
                         fill_color=col(c or "accent") if i == 0 else col("card" if i % 2 else "bg"))
        band.move_to([total / 2, y, 0])
        row = VGroup(band)
        x = 0.0
        for j, t in enumerate(r):
            t.move_to([x + 0.3 + t.width / 2, y, 0])
            row.add(t)
            g.places[f"r{i}c{j + 1}"] = t
            x += cw[j]
        row.add(Line([0, y - rh / 2, 0], [total, y - rh / 2, 0], stroke_color=col("soft"), stroke_width=1))
        g.add(row)
    return g.move_to(ORIGIN)


def bullets(args: list[str], mods: dict, c=None) -> VGroup:
    """Items one under another, a dot (or `numbered`) before each. Parts: the items."""
    size = float(mods.get("size") or 0.3)
    g = VGroup()
    g.places = Keys()
    for i, it in enumerate(args):
        if mods.get("numbered"):
            mark = VGroup(Circle(radius=size * 0.62, fill_color=col(c or "accent"), fill_opacity=1, stroke_width=0),
                          text(str(i + 1), size * 0.8, bold=True, color="ink"))
        else:
            mark = VGroup(Dot(radius=size * 0.22, color=col(c or "accent")))
        t = even(it.replace("_", " "), size)
        row = VGroup(mark, t.next_to(mark, RIGHT, buff=size * 0.6))
        row.move_to([0, -i * size * 2.1, 0]).align_to([0, 0, 0], LEFT)
        g.add(row)
        g.places[key(it)] = row
    return g.move_to(ORIGIN)


def steps(args: list[str], mods: dict, c=None) -> VGroup:
    """Numbered steps in a row, joined: `steps "plough" "sow" "harvest"`. Parts: the steps (each with the line in)."""
    n = len(args)
    w = float(mods.get("w", min(12, 3 * n)))
    g = VGroup()
    g.places = Keys()
    xs = [-w / 2 + w * (i + 0.5) / n for i in range(n)]
    for i, (x, it) in enumerate(zip(xs, args)):
        disc = Circle(radius=0.38, fill_color=col(c or "accent"), fill_opacity=1, stroke_color=col("ink"), stroke_width=2)
        num = text(str(i + 1), 0.3, bold=True, color="ink")
        words = even(it.replace("_", " ").upper(), 0.2)
        if words.width > w / n - 0.2:
            words.scale_to_fit_width(w / n - 0.2)
        part = VGroup(disc.move_to([x, 0, 0]), num.move_to([x, 0, 0]), words.move_to([x, -0.75, 0]))
        part.core = VGroup(*part.submobjects)   # a mark goes round the step, not the line into it
        if i:
            part.add(Line([xs[i - 1] + 0.42, 0, 0], [x - 0.42, 0, 0], stroke_color=col("ink"), stroke_width=STROKE * 0.4))
        g.add(part)
        g.places[key(it)] = part
    return g


def stat(args: list[str], mods: dict, c=None) -> VGroup:
    """A big figure with its meaning under it: `stat 20 "of Europe died" suffix "%"`; it counts (`count st 20`)."""
    from look import Num
    raw = str(args[0]) if args else "0"         # `stat 60%`, `stat "$2.5"`, `stat 1,200`: the number and its signs
    m_ = re.search(r"-?\d[\d,]*\.?\d*", raw)
    v = float(m_.group(0).replace(",", "")) if m_ else 0.0
    prefix = mods.get("prefix", raw[:m_.start()] if m_ else "")
    suffix = mods.get("suffix", raw[m_.end():] if m_ else "")
    n = Num(v, prefix, suffix, float(mods.get("size") or 1.3), c)
    words = label(args[1] if len(args) > 1 else str(mods.get("sub") or ""), 0.17, "ink")
    bar = Rectangle(width=max(n.width, words.width) + 0.3, height=0.1, fill_color=col("accent"), fill_opacity=1,
                    stroke_width=0)
    return VGroup(n, VGroup(bar.next_to(n, DOWN, buff=0.15), words.next_to(bar, DOWN, buff=0.2)))


# ---------------------------------------------------------------- measures -------------------------------------------

from look import Valued  # noqa: E402


class Calendar(Valued, VGroup):
    """Days as a grid of small squares; `count CAL N` fills the first N (a year passing)."""

    def __init__(self, days: int, value: float = 0, cols: int = 31, c=None):
        super().__init__()
        days = max(1, min(int(days), 400))
        self.on, self.off = col(c or "accent"), col("sand")
        s = 0.12
        for i in range(days):
            self.add(Rectangle(width=s, height=s, fill_color=self.off, fill_opacity=1, stroke_color=col("soft"),
                               stroke_width=0.5).move_to([(i % cols) * (s + 0.04), -(i // cols) * (s + 0.04), 0]))
        self.value = 0
        self.set_value(value)

    def set_value(self, v: float) -> None:
        n = int(round(v))
        for i, sq in enumerate(self.submobjects):
            sq.set_fill(self.on if i < n else self.off, family=False)
        self.value = v


class Meter(Valued, VGroup):
    """A thermometer: a tube filled to a value (of `max`); `grow M V` moves it; its words under it."""

    def __init__(self, value: float, top: float = 10, h: float = 3.0, words: str = "", c=None):
        super().__init__()
        self.top, self.h, self.value = top, h, value
        self.tube = RoundedRectangle(width=0.42, height=h, corner_radius=0.21, fill_color=col("card"), fill_opacity=1,
                                     stroke_color=col("ink"), stroke_width=2.5)
        self.bulb = Circle(radius=0.36, fill_color=col(c or "red"), fill_opacity=1, stroke_color=col("ink"),
                           stroke_width=2.5).move_to(self.tube.get_bottom() + DOWN * 0.18)
        self.colour = col(c or "red")
        self.level = self._level(value)
        ticks = VGroup(*(Line([0.25, -h / 2 + h * k / 5, 0], [0.42, -h / 2 + h * k / 5, 0], stroke_color=col("ink"),
                              stroke_width=2) for k in range(1, 5)))
        self.add(self.tube, self.level, self.bulb, ticks)
        if words:
            self.add(label(words, 0.13, "ink").next_to(self.bulb, DOWN, buff=0.2))

    def _level(self, v: float):
        lh = max(0.05, (self.h - 0.2) * max(0.0, min(v, self.top)) / self.top)
        return Rectangle(width=0.22, height=lh, fill_color=self.colour, fill_opacity=1, stroke_width=0).move_to(
            self.tube.get_bottom() + UP * (lh / 2 + 0.05))

    def set_value(self, v: float) -> None:
        new = self._level(v)
        new.set_z_index(self.level.z_index)
        new.set_fill(opacity=self.level.get_fill_opacity())
        self.level.become(new)
        self.value = v


class Balance(VGroup):
    """A balance: a post, a beam, a pan hanging at each end with its words. `tip B left|right|level` tilts it.
    Parts: [stand, beam, left pan, right pan]."""

    def __init__(self, left: str, right: str, w: float = 5.0, c=None):
        super().__init__()
        self.half = w / 2
        ink = col("ink")
        stand = VGroup(Line([0, -1.6, 0], [0, 0.9, 0], stroke_color=ink, stroke_width=STROKE * 0.7),
                       Polygon([-0.7, -1.6, 0], [0.7, -1.6, 0], [0, -1.15, 0], fill_color=ink, fill_opacity=1,
                               stroke_width=0),
                       Dot([0, 0.9, 0], radius=0.09, color=ink))
        self.pivot = np.array([0, 0.9, 0])
        self.beam = Line(self.pivot + LEFT * self.half, self.pivot + RIGHT * self.half, stroke_color=ink,
                         stroke_width=STROKE * 0.8)
        self.pans = []
        for side, words in ((-1, left), (1, right)):
            hang = VGroup(Line([0, 0, 0], [-0.55, -1.0, 0], stroke_color=ink, stroke_width=2),
                          Line([0, 0, 0], [0.55, -1.0, 0], stroke_color=ink, stroke_width=2))
            dish = Polygon([-0.8, -1.0, 0], [0.8, -1.0, 0], [0.5, -1.3, 0], [-0.5, -1.3, 0],
                           fill_color=col(c or "accent"), fill_opacity=1, stroke_color=ink, stroke_width=2)
            t = text(words.replace("_", " ").upper(), 0.22, bold=True, color="ink").move_to([0, -1.6, 0])
            pan = VGroup(hang, dish, t)
            pan.hook = self.pivot + RIGHT * side * self.half
            pan.shift(pan.hook)
            self.pans.append(pan)
        self.tilt = 0.0
        self.add(stand, self.beam, *self.pans)

    def set_tilt(self, a: float) -> None:
        """The beam at angle `a` (positive: the right side down), the pans hanging straight from its ends."""
        p = self.beam.get_center()
        self.beam.rotate(-(a - self.tilt), about_point=p)
        for side, pan in zip((-1, 1), self.pans):
            end = p + np.array([side * self.half * math.cos(a), -side * self.half * math.sin(a), 0])
            hook = pan[0][0].get_start()
            pan.shift(end - hook)
        self.tilt = a


# ---------------------------------------------------------------- more diagrams and charts ----------------------------

def venn(args: list[str], mods: dict, c=None) -> VGroup:
    """Two or three overlapping circles, each named; `label "WORDS"` in what they share. Parts: the circles, then
    the shared words."""
    names = args[:3] or ["a", "b"]
    r = float(mods.get("r", 1.6))
    fills = ["accent", "teal", "coral"]
    centres = ([[-r * 0.55, 0, 0], [r * 0.55, 0, 0]] if len(names) == 2 else
               [[-r * 0.55, r * 0.32, 0], [r * 0.55, r * 0.32, 0], [0, -r * 0.6, 0]])
    g = VGroup()
    g.places = Keys()
    for i, (nm, cpt) in enumerate(zip(names, centres)):
        circ = Circle(radius=r, fill_color=col(fills[i]), fill_opacity=0.35, stroke_color=col(fills[i]),
                      stroke_width=STROKE * 0.5).move_to(cpt)
        out = np.array(cpt) / (np.linalg.norm(cpt) or 1)
        t = halo(even(nm.replace("_", " ").upper(), 0.24, bold=True))
        # each name outside its circle, away from what they share
        t.move_to(np.array(cpt) + (out * (r + 0.2) + UP * 0.0 if len(names) == 3 else UP * (r + 0.3) + out * r * 0.3))
        part = VGroup(circ, t)
        g.add(part)
        g.places[key(nm)] = part
    if mods.get("label"):
        g.add(halo(label(str(mods["label"]), 0.14, "ink")).move_to(ORIGIN))
    return g


def stack(data, mods, c=None) -> VGroup:
    """Shares of a whole in one bar, each named under its part. Parts: the shares."""
    w, h = float(mods.get("w", 9)), 0.7
    total = sum(v for _, v in data) or 1
    g = VGroup()
    x = -w / 2
    for i, (k, v) in enumerate(data):
        bw = w * v / total
        seg = Rectangle(width=max(0.02, bw), height=h, fill_color=col(PALETTE[i % len(PALETTE)]), fill_opacity=1,
                        stroke_color=col("bg"), stroke_width=2).move_to([x + bw / 2, 0, 0])
        t = label(f"{k} {_fmt(v, mods)}", 0.12, "ink")
        t.move_to([x + bw / 2, (-0.65 if i % 2 == 0 else 0.65), 0])
        g.add(VGroup(seg, t))
        x += bw
    return g


def waffle(data, mods, c=None) -> VGroup:
    """A hundred squares shared out (`chart waffle died:20 lived:80`). Parts: the shares, each its squares and name."""
    total = sum(v for _, v in data) or 1
    counts = [round(100 * v / total) for _, v in data]
    counts[-1] = 100 - sum(counts[:-1])
    s, gap = 0.22, 0.05
    g = VGroup()
    i = 0
    for j, ((k, v), n) in enumerate(zip(data, counts)):
        sq = VGroup()
        for _ in range(max(0, n)):
            sq.add(Rectangle(width=s, height=s, fill_color=col(PALETTE[j % len(PALETTE)]), fill_opacity=1,
                             stroke_width=0).move_to([(i % 10) * (s + gap), -(i // 10) * (s + gap), 0]))
            i += 1
        g.add(VGroup(sq))
    side = VGroup()
    for j, (part, (k, v)) in enumerate(zip(g, data)):
        key_sq = Rectangle(width=0.22, height=0.22, fill_color=col(PALETTE[j % len(PALETTE)]), fill_opacity=1,
                           stroke_width=0)
        t = label(f"{k} {_fmt(v, mods)}", 0.13, "ink").next_to(key_sq, RIGHT, buff=0.15)
        row = VGroup(key_sq, t).move_to([10 * (s + gap) + 0.5, -j * 0.45, 0]).align_to([10 * (s + gap) + 0.3, 0, 0], LEFT)
        part.add(row)
    return g.move_to(ORIGIN)


# ---------------------------------------------------------------- words in the scene ---------------------------------

def formula(words: str, mods: dict, c=None):
    """A formula set as text: `_x` or `_{..}` below, `^x` or `^{..}` above, `*` a times sign, `->` an arrow
    (H_2O, x^2 + y^2, 6CO_2 + 6H_2O -> C_6H_12O_6)."""
    from manim import MarkupText
    from look import _esc
    s = _esc(words).replace("-&gt;", "→").replace("*", "×")
    s = re.sub(r"_\{([^}]*)\}", r"<sub>\1</sub>", s)
    s = re.sub(r"\^\{([^}]*)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"_(\d+|[A-Za-z])", r"<sub>\1</sub>", s)           # H_2O, C_6H_12O_6, x_i
    s = re.sub(r"\^(\d+[+\-]?|[A-Za-z+\-])", r"<sup>\1</sup>", s)   # x^2, Ca^2+, e^x
    font = L.get("body") or "Inter"
    t = MarkupText(s, font=font, color=col(c or "ink"), font_size=48)
    ref = MarkupText("H", font=font, font_size=48)     # scaled by a capital's height, whatever the glyphs (an "=")
    t.scale(float(mods.get("size") or 0.5) / max(ref.height, 0.01) * 0.8)
    return VGroup(t)


def bubble(m, words: str, mods: dict, c=None) -> VGroup:
    """A speech bubble over a thing (a person's picture), its tail to it: `bubble "I am free!" on youth`."""
    side = -1 if mods.get("side") == "left" else 1
    body = para(words, float(mods.get("size") or 0.24), float(mods.get("w", 3.2)), color="ink")
    box = RoundedRectangle(width=body.width + 0.5, height=body.height + 0.4, corner_radius=0.22,
                           fill_color=col(c or "card"), fill_opacity=1, stroke_color=col("ink"), stroke_width=2)
    top = m.get_top()
    box.move_to(top + np.array([side * (box.width / 2 - 0.2), 0.45 + box.height / 2, 0]))
    base = box.get_bottom()[1]
    bx = top[0] + side * 0.35
    tail = Polygon([bx, base + 0.02, 0], [bx + side * 0.45, base + 0.02, 0], [top[0] + side * 0.05, top[1] + 0.1, 0],
                   fill_color=col(c or "card"), fill_opacity=1, stroke_width=0)
    edge = VGroup(Line([bx, base, 0], [top[0] + side * 0.05, top[1] + 0.1, 0]),
                  Line([bx + side * 0.45, base, 0], [top[0] + side * 0.05, top[1] + 0.1, 0])).set_stroke(col("ink"), 2)
    return VGroup(box, tail, edge, body.move_to(box))


# ---------------------------------------------------------------- the weather ----------------------------------------

def weather(how: str, mods: dict, c=None) -> VGroup:
    """Snow or rain over the whole screen; render.py keeps it falling while it is up (`in snow fade`). Each flake's
    start and speed are kept (`seeds`), so every chunk of a video draws the same fall."""
    how = how or "snow"
    n = int(mods.get("n", 70 if how == "snow" else 90))
    w, h = float(mods.get("w", 14.4)), float(mods.get("h", 8.2))
    rng = np.random.default_rng(zlib.crc32(how.encode()) + n)
    g = VGroup()
    g.seeds = []
    g.size = (w, h)
    for _ in range(n):
        x, y = rng.uniform(-w / 2, w / 2), rng.uniform(-h / 2, h / 2)
        if how == "rain":
            p = Line([0, 0, 0], [-0.08, -0.38, 0], stroke_color=col(c or "navy"), stroke_width=2, stroke_opacity=0.5)
            speed = rng.uniform(5.5, 7.5)
        else:
            r = rng.uniform(0.03, 0.07)
            p = Dot(radius=r, color=col(c or "white")).set_opacity(0.9)
            speed = rng.uniform(0.5, 1.1)
        g.add(p.move_to([x, y, 0]))
        g.seeds.append((x, y, speed, rng.uniform(0, math.tau)))
    g.how = how
    return g
