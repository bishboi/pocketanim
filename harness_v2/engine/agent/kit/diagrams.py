"""Diagrams that lay themselves out: a flow (layered left to right or top down), a tree, a cycle, a hub with spokes,
a pyramid, a network (who influenced whom), a cause chain. Nodes are cards in the look; edges are arrows. Each
diagram can build itself in order, focus on some nodes (the rest dimmed), and send a pulse along an edge.

    f = Flow(["Rulers", "History office", "Official history"], [("Rulers", "History office"),
             ("History office", "Official history", "writes")])
    self.play(f.appear())                       # nodes in order, each edge drawn once both its ends are on
    self.play(f.focus("History office"))        # the others dimmed
    self.play(f.pulse("Rulers", "History office"))
    n = Network({"Naito": "Naito Konan", "Kyoto": "Kyoto Univ."}, [("Naito", "Kyoto")])
    t = Tree({"Sources": {"Inside": {"Official": {}, "Scholarly": {}}, "Outside": {"Travellers": {}}}})

Node specs: a plain string, or {"name": ..., "label": ..., "shape": box|pill|circle|diamond|card, "color": ...,
"icon": "scroll", "key": True (filled in the accent)}.
"""

from __future__ import annotations

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, PI, RIGHT, UP, AnimationGroup, Arrow, Circle, Create, CurvedArrow,
                   DashedVMobject, Dot, FadeIn, GrowFromCenter, LaggedStart, Line, MoveAlongPath, Polygon, Rectangle,
                   RoundedRectangle, VGroup, VMobject)

from .base import Piece
from .layout import edge_point
from .look import L
from .text import fit, label, text


class Node(Piece):
    enter_kind = "shape"


def node(words: str, shape: str = "box", color: str | None = None, key: bool = False, icon_name: str | None = None,
         width: float = 2.6, size: float = 24) -> Node:
    """A diagram node: words in a shape (box, pill, circle, diamond, card) in the look; `key` fills it in the
    accent; `icon_name` puts an icon above the words."""
    from .cards import shadow_of
    look = L()
    vox = look.name == "vox"
    c = color or (look.accent if key else None)
    ink = ("#FFFFFF" if c and vox else look.ink)
    t = text(words, size=size, weight=True, color=ink, width=width - 0.35, align="center")
    content = VGroup(t)
    if icon_name:
        from .icons import icon
        try:
            ic = icon(icon_name, size=0.7)
            content = VGroup(ic, t).arrange(DOWN, buff=0.12)
        except Exception:
            pass
    w, h = max(content.width + 0.45, 1.0), content.height + 0.35
    fill = c or look.card
    style = dict(fill_color=fill, fill_opacity=(1 if vox else (0.45 if c else look.card_opacity)),
                 stroke_color=c or look.card_edge, stroke_width=0 if vox and not c else (0 if vox else 2))
    if vox and not c:
        style["stroke_width"] = 2.2
        style["stroke_color"] = look.ink
    if shape == "pill":
        body = RoundedRectangle(width=w + 0.2, height=h, corner_radius=h / 2, **style)
    elif shape == "circle":
        body = Circle(radius=max(w, h) / 2 + 0.05, **style)
    elif shape == "diamond":
        d = max(w, h) * 0.85
        body = Polygon(UP * d, RIGHT * d * 1.2, DOWN * d, LEFT * d * 1.2, **style)
    else:
        body = RoundedRectangle(width=w, height=h, corner_radius=0.1 if vox else 0.0, **style)
    content.move_to(body)
    parts = [shadow_of(body)] if look.shadow and shape in ("card", "box", "pill") else []
    n = Node(*parts, body, content)
    n.name_part("body", body)
    n.name_part("words", t)
    return n


def _spec(s):
    if isinstance(s, dict):
        return s["name"], s
    return str(s), {"name": str(s)}


class Diagram(Piece):
    """Nodes by name and edges by (from, to); the shared verbs of every diagram."""
    enter_kind = "shape"

    def __init__(self):
        super().__init__()
        self.nodes: dict[str, Node] = {}
        self.edges: dict[tuple, Piece] = {}
        self.order: list[str] = []

    def _make_nodes(self, specs, **defaults):
        for s in specs:
            name, d = _spec(s)
            n = node(d.get("label", name), shape=d.get("shape", defaults.get("shape", "box")), color=d.get("color"),
                     key=d.get("key", False), icon_name=d.get("icon"), width=d.get("width", defaults.get("width", 2.6)),
                     size=d.get("size", defaults.get("size", 24)))
            self.nodes[name] = n
            self.order.append(name)

    def node(self, name: str) -> Node:
        return self.nodes[name]

    def edge(self, a: str, b: str) -> Piece:
        return self.edges[(a, b)]

    def _edge(self, a: str, b: str, words: str | None = None, curve: float = 0.0, elbow: bool = False,
              color: str | None = None) -> Piece:
        look = L()
        c = color or (look.ink if look.name == "vox" else look.muted)
        na, nb = self.nodes[a], self.nodes[b]
        pa, pb = na.get_center(), nb.get_center()
        d = (pb - pa) / (np.linalg.norm(pb - pa) or 1)
        ba, bb = na.part("body"), nb.part("body")
        pa, pb = ba.get_center(), bb.get_center()
        d = (pb - pa) / (np.linalg.norm(pb - pa) or 1)
        start, end = edge_point(ba, d), edge_point(bb, -d)
        if elbow:
            mid_y = (start[1] + end[1]) / 2
            start = na.part("body").get_bottom()
            end = nb.part("body").get_top()
            mid_y = (start[1] + end[1]) / 2
            path = VMobject(stroke_color=c, stroke_width=look.stroke * 0.7)
            path.set_points_as_corners([start, [start[0], mid_y, 0], [end[0], mid_y, 0], end])
            tip = Arrow(end + UP * 0.3, end, buff=0, color=c, stroke_width=look.stroke * 0.7, tip_length=0.18,
                        max_tip_length_to_length_ratio=0.6)
            e = Piece(path, tip)
            e.path = path
        elif curve:
            arr = CurvedArrow(start, end, angle=curve, color=c, stroke_width=look.stroke * 0.8, tip_length=0.2)
            e = Piece(arr)
            e.path = arr
        else:
            arr = Arrow(start, end, buff=0.08, color=c, stroke_width=look.stroke * 0.8, tip_length=0.2,
                        max_tip_length_to_length_ratio=0.25)
            e = Piece(arr)
            e.path = arr
        if words:
            lab = label(words, size=20, color=look.ink, role="hand" if look.name == "vox" else "mono")
            lab.move_to(e.path.point_from_proportion(0.5) + UP * 0.25)
            e.add(lab)
            e.name_part("label", lab)
        e.enter_kind = "line"
        self.edges[(a, b)] = e
        return e

    def _assemble(self):
        for n in self.order:
            self.add(self.nodes[n])
        for e in self.edges.values():
            self.add(e)
        for e in self.edges.values():
            e.set_z_index(-1)

    def appear(self, how=None, run=None, **kw):
        """Nodes in order; each edge drawn as soon as both its ends are on."""
        if how:
            return super().appear(how, run, **kw)
        from .motion import enter, owned
        run = run if run is not None else 0.5
        anims, shown = [], set()
        for name in self.order:
            anims.append(enter(self.nodes[name], None, run=run))
            shown.add(name)
            for (a, b), e in self.edges.items():
                if b == name and a in shown or a == name and b in shown:
                    anims.append(Create(e, run_time=run))
        return owned(self, LaggedStart(*anims, lag_ratio=0.55))

    def reveal(self, *names, run: float = 0.5):
        """Bring on only these nodes (and edges between nodes already on): build a diagram as the voice names its
        parts."""
        from .motion import enter
        anims = [enter(self.nodes[n], None, run=run) for n in names]
        on = set(names) | getattr(self, "_on", set())
        anims += [Create(e, run_time=run) for (a, b), e in self.edges.items()
                  if (a in names or b in names) and a in on and b in on]
        self._on = on
        return LaggedStart(*anims, lag_ratio=0.4)

    def _faded(self, mob, k: float):
        """A copy of `mob` with every part's fill and stroke opacity at k times what it had at first."""
        if not hasattr(mob, "_kit_base"):
            mob._kit_base = [(m.get_fill_opacity(), m.get_stroke_opacity()) for m in mob.get_family()]
        target = mob.copy()
        for m, (f, st) in zip(target.get_family(), mob._kit_base):
            m.set_fill(opacity=f * k, family=False)
            m.set_stroke(opacity=st * k, family=False)
        return target

    def focus(self, *names, dim: float = 0.25, run: float = 0.6):
        """These nodes (and edges between them) stay; everything else dims."""
        from manim import Transform
        keep = set(names)
        anims = []
        for n, m in self.nodes.items():
            anims.append(Transform(m, self._faded(m, 1 if n in keep else dim), run_time=run))
        for (a, b), e in self.edges.items():
            anims.append(Transform(e, self._faded(e, 1 if a in keep and b in keep else dim), run_time=run))
        return AnimationGroup(*anims)

    def unfocus(self, run: float = 0.6):
        from manim import Transform
        return AnimationGroup(*(Transform(m, self._faded(m, 1), run_time=run)
                                for m in list(self.nodes.values()) + list(self.edges.values())))

    def pulse(self, a: str, b: str, color: str | None = None, run: float = 1.0):
        """A dot travelling along the edge a -> b."""
        e = self.edges[(a, b)]
        d = Dot(radius=0.1, color=color or L().accent)
        d.move_to(e.path.point_from_proportion(0))
        from manim import FadeOut
        return LaggedStart(MoveAlongPath(d, e.path, run_time=run), FadeOut(d, run_time=0.15), lag_ratio=1.0)


class Flow(Diagram):
    def __init__(self, nodes, edges, direction: str = "right", gap: float = 1.0, layer_gap: float | None = None,
                 size: float = 24, width: float = 2.6, max_width: float = 13.0, max_height: float = 7.0):
        """Nodes laid out in layers by their edges (sources first), `direction` right or down; edges (a, b) or
        (a, b, "label")."""
        super().__init__()
        self._make_nodes(nodes, size=size, width=width)
        edges = [tuple(e) for e in edges]
        layer = {n: 0 for n in self.order}
        for _ in range(len(self.order)):
            for e in edges:
                layer[e[1]] = max(layer[e[1]], layer[e[0]] + 1)
        layers: dict[int, list[str]] = {}
        for n in self.order:
            layers.setdefault(layer[n], []).append(n)
        horizontal = direction == "right"
        pos = {}
        lg = layer_gap or (max(n.width for n in self.nodes.values()) + gap if horizontal else
                           max(n.height for n in self.nodes.values()) + gap)
        for li, names in layers.items():
            if li > 0:
                def bary(n):
                    preds = [pos[e[0]][1] if horizontal else -pos[e[0]][0] for e in edges if e[1] == n and e[0] in pos]
                    return np.mean(preds) if preds else 0
                names.sort(key=bary, reverse=horizontal)
            span = [self.nodes[n].height if horizontal else self.nodes[n].width for n in names]
            total = sum(span) + gap * 0.6 * (len(names) - 1)
            cur = total / 2
            for n, s in zip(names, span):
                c = cur - s / 2
                pos[n] = (li * lg, c) if horizontal else (-c, -li * lg)
                cur -= s + gap * 0.6
        for n, (x, y) in pos.items():
            self.nodes[n].move_to([x, y, 0])
        for e in edges:
            self._edge(e[0], e[1], e[2] if len(e) > 2 else None)
        self._assemble()
        self.move_to(ORIGIN)
        fit(self, max_width, max_height)


class Tree(Diagram):
    def __init__(self, tree: dict, gap: float = 0.4, level_gap: float = 1.4, size: float = 22, width: float = 2.4,
                 max_width: float = 13.0, max_height: float = 7.0):
        """A hierarchy from a nested dict {root: {child: {grandchild: {}}}}, top down, with elbow connectors."""
        super().__init__()
        specs, links = [], []

        def walk(d, parent=None):
            for k, v in d.items():
                specs.append(k)
                if parent is not None:
                    links.append((parent, k))
                walk(v or {}, k)

        walk(tree)
        self._make_nodes(specs, size=size, width=width)
        children = {n: [b for a, b in links if a == n] for n in self.order}
        root = self.order[0]
        widths = {}

        def span(n):
            if not children[n]:
                widths[n] = self.nodes[n].width
            else:
                widths[n] = max(self.nodes[n].width, sum(span(c) for c in children[n]) + gap * (len(children[n]) - 1))
            return widths[n]

        span(root)

        def place(n, x, depth):
            self.nodes[n].move_to([x, -depth * level_gap, 0])
            kids = children[n]
            if not kids:
                return
            total = sum(widths[c] for c in kids) + gap * (len(kids) - 1)
            cur = x - total / 2
            for c in kids:
                place(c, cur + widths[c] / 2, depth + 1)
                cur += widths[c] + gap

        place(root, 0, 0)
        for a, b in links:
            self._edge(a, b, elbow=True)
        self._assemble()
        self.move_to(ORIGIN)
        fit(self, max_width, max_height)


class Cycle(Diagram):
    def __init__(self, items, radius: float = 2.6, size: float = 22, width: float = 2.2):
        """Items round a circle, each arrow curving to the next (a cycle)."""
        super().__init__()
        self._make_nodes(items, size=size, width=width)
        k = len(self.order)
        for i, n in enumerate(self.order):
            a = PI / 2 - 2 * PI * i / k
            self.nodes[n].move_to([radius * np.cos(a) * 1.25, radius * np.sin(a), 0])
        for i, n in enumerate(self.order):
            self._edge(n, self.order[(i + 1) % k], curve=-PI / max(3, k))
        self._assemble()


class Hub(Diagram):
    def __init__(self, centre, items, radius: float = 3.0, size: float = 22, width: float = 2.3,
                 outward: bool = True):
        """A centre node with items round it, spokes from the centre (outward) or to it."""
        super().__init__()
        cname, cspec = _spec(centre)
        cspec = {**cspec, "key": cspec.get("key", True)}
        self._make_nodes([cspec] + list(items), size=size, width=width)
        others = self.order[1:]
        k = len(others)
        for i, n in enumerate(others):
            a = PI / 2 - 2 * PI * i / k
            self.nodes[n].move_to([radius * np.cos(a) * 1.35, radius * np.sin(a) * 0.95, 0])
        for n in others:
            self._edge(cname, n) if outward else self._edge(n, cname)
        self._assemble()


class Chain(Diagram):
    def __init__(self, items, gap: float = 0.9, size: float = 22, width: float = 2.3, max_width: float = 13.0):
        """Cause and effect, left to right: each item an arrow to the next."""
        super().__init__()
        self._make_nodes(items, size=size, width=width)
        VGroup(*self.nodes.values()).arrange(RIGHT, buff=gap)
        for a, b in zip(self.order, self.order[1:]):
            self._edge(a, b)
        self._assemble()
        self.move_to(ORIGIN)
        fit(self, max_width)


class Network(Diagram):
    def __init__(self, nodes, edges, layout: str = "spring", radius: float = 3.0, size: float = 20,
                 width: float = 2.2, seed: int = 2, max_width: float = 13.0, max_height: float = 7.0):
        """People or ideas joined by lines (who influenced whom): `nodes` a list of specs or {name: label}; edges
        (a, b) or (a, b, label). layout: spring (a force layout) or circle."""
        super().__init__()
        if isinstance(nodes, dict):
            nodes = [{"name": k, "label": v} for k, v in nodes.items()]
        self._make_nodes(nodes, shape="pill", size=size, width=width)
        names = self.order
        k = len(names)
        idx = {n: i for i, n in enumerate(names)}
        angles = np.linspace(0, 2 * PI, k, endpoint=False)
        pos = np.stack([np.cos(angles) * radius * 1.3, np.sin(angles) * radius], axis=1)
        if layout == "spring" and k > 2:
            rng = np.random.default_rng(seed)
            pos += rng.normal(0, 0.1, pos.shape)
            E = [(idx[e[0]], idx[e[1]]) for e in edges]
            for step in range(300):
                disp = np.zeros_like(pos)
                for i in range(k):
                    d = pos[i] - pos
                    dist = np.linalg.norm(d, axis=1) + 1e-3
                    disp[i] += (d / dist[:, None] * (2.2 ** 2 / dist)[:, None]).sum(axis=0)
                for i, j in E:
                    d = pos[i] - pos[j]
                    dist = np.linalg.norm(d) + 1e-3
                    f = d / dist * dist ** 2 / 2.2
                    disp[i] -= f
                    disp[j] += f
                disp -= pos * 0.05
                t = 0.3 * (1 - step / 300) + 0.01
                lens = np.linalg.norm(disp, axis=1) + 1e-6
                pos += disp / lens[:, None] * np.minimum(lens, t)[:, None]
            pos -= pos.mean(axis=0)
            span = np.ptp(pos, axis=0) + 1e-6
            pos = pos / span * np.array([radius * 2.8, radius * 1.9])
        for n, (x, y) in zip(names, pos):
            self.nodes[n].move_to([x, y, 0])
        for e in edges:
            self._edge(e[0], e[1], e[2] if len(e) > 2 else None)
            # an undirected look: arrows thin to lines in a network
        self._assemble()
        self.move_to(ORIGIN)
        fit(self, max_width, max_height)


class Pyramid(Piece):
    def __init__(self, levels, width: float = 7.0, height: float = 5.0, colors=None, size: float = 24,
                 inverted: bool = False):
        """Levels from the top down (the few at the top, the many at the bottom); `inverted` flips it."""
        super().__init__()
        look = L()
        n = len(levels)
        h = height / n
        self.levels_ = []
        for i, words in enumerate(levels):
            top_w = width * (i / n)
            bot_w = width * ((i + 1) / n)
            if inverted:
                top_w, bot_w = width * (1 - i / n), width * (1 - (i + 1) / n)
            y = height / 2 - h * i
            c = colors[i % len(colors)] if colors else look.color(i)
            shape = Polygon([-top_w / 2, y, 0], [top_w / 2, y, 0], [bot_w / 2, y - h, 0], [-bot_w / 2, y - h, 0],
                            fill_color=c, fill_opacity=0.9 if look.name == "vox" else 0.35,
                            stroke_color=look.bg if look.name == "vox" else c, stroke_width=4 if look.name == "vox" else 2)
            t = text(words, size=size, weight=True, color="#FFFFFF" if look.name == "vox" else look.ink,
                     width=max(1.2, (top_w + bot_w) / 2 * 0.8), align="center")
            narrow = min(top_w, bot_w)
            room = (narrow + max(top_w, bot_w)) / 2 if narrow > 0.5 else max(top_w, bot_w) * 0.45
            fit(t, max(0.6, room * 0.8), h * (0.8 if narrow > 0.5 else 0.45))
            t.move_to([0, y - h * (0.62 if not inverted else 0.38) if narrow > 0.5 else
                       (y - h * 0.75 if not inverted else y - h * 0.25), 0])
            lvl = VGroup(shape, t)
            self.add(lvl)
            self.levels_.append(lvl)

    def level(self, i: int):
        return self.levels_[i]

    def appear(self, how=None, run=None, **kw):
        if how:
            return super().appear(how, run, **kw)
        from .motion import owned
        run = run if run is not None else 0.5
        order = self.levels_[::-1]
        return owned(self, LaggedStart(*(FadeIn(l, shift=UP * 0.2, run_time=run) for l in order), lag_ratio=0.5))
