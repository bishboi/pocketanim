"""Layout for hierarchies: a whole above its kinds, each kind above its own kinds, as a textbook (or a UML chart of
diagram types) draws a classification. The main thing is at the top; its subcategories sit in a row under it, each
centred over its own subcategories, and so on down, however deep.

Two ways of laying out a group of leaves (kinds with no kinds of their own) are tried for the whole tree:

* in a row, each parent centred over its children (a tidy tree): the clearest, when the board is wide enough;
* stacked in a column under their parent, joined by a spine down its left side (an org chart's compact form):
  a tree with many leaves then grows down instead of across, and is drawn bigger.

The one that lets the tree be drawn biggest on the board wins. Connectors are drawn the classic way: from each
child straight up to a bar shared with its siblings, along the bar, and up into the parent, where an open
triangle marks "is a kind of".

Everything here is plain numbers: pocket_lecture.Lecture._hierarchy draws the boxes and the connectors.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# A tree drawn at least this big (board units per layout unit) reads well: it is kept as a plain tree.
READABLE = 0.85


@dataclass
class Tree:
    centres: dict                       # node id -> (x, y), y up
    connectors: list                    # (parent, child, [(x, y), ...] from the child to the parent)
    joins: dict = field(default_factory=dict)  # parent -> (x, y): where its connectors meet it (the triangle)
    width: float = 0.0
    height: float = 0.0
    stacked: dict = field(default_factory=dict)  # parent -> columns its leaves are stacked in
    depth: dict = field(default_factory=dict)  # node id -> level (0 at the top)


def structure(ids: list[str], edges) -> tuple[list[str], dict, dict]:
    """(roots, children, parent) from edges [from, to, ...]: each node keeps the first parent that names it, and
    an edge that would close a loop is dropped (a hierarchy has none)."""
    children: dict = {i: [] for i in ids}
    parent: dict = {}

    def above(a, b):                    # is b an ancestor of a (or a itself)?
        while a is not None:
            if a == b:
                return True
            a = parent.get(a)
        return False

    for e in edges:
        a, b = str(e[0]), str(e[1])
        if a not in children or b not in children or b in parent or a == b or above(a, b):
            continue
        parent[b] = a
        children[a].append(b)
    roots = [i for i in ids if i not in parent]
    return roots, children, parent


def is_tree(ids: list[str], edges) -> bool:
    """A flow that is really a hierarchy: one top, every other node with exactly one parent, no loops, and some
    node with two or more kinds under it."""
    if not edges:
        return False
    ins: dict = {}
    for e in edges:
        ins[str(e[1])] = ins.get(str(e[1]), 0) + 1
    if any(v > 1 for v in ins.values()):
        return False
    roots, children, parent = structure(ids, edges)
    if len(roots) != 1 or len(parent) != len(ids) - 1 or len(parent) != len(edges):
        return False
    return any(len(c) > 1 for c in children.values())


def layout(ids: list[str], edges, sizes: dict, board: tuple[float, float] = (12.6, 6.0), gap_x: float = 0.4,
           gap_y: float = 0.75, indent: float = 0.45, gap_stack: float = 0.22) -> Tree:
    """Where each box goes and how each connector runs. sizes: id -> (width, height) of its box."""
    roots, children, _ = structure(ids, edges)
    leafy = [p for p in ids if len(children[p]) >= 2 and all(not children[c] for c in children[p])]

    def fit(stacked):
        tree = _place(ids, roots, children, sizes, stacked, gap_x, gap_y, indent, gap_stack)
        return min(board[0] / max(tree.width, 1e-6), board[1] / max(tree.height, 1e-6)), tree

    # Kept as a plain tree when that is drawn big enough to read. Otherwise the groups of leaves at each depth go in
    # a row (0) or in 1-3 stacked columns, the same for every group at that depth (siblings drawn alike): changed a
    # depth at a time while the tree can be drawn bigger (by more than a little: a row is clearer on a near tie).
    best = fit({})
    if best[0] >= READABLE or not leafy:
        return best[1]
    depth = {}
    for r in roots:
        stack = [(r, 0)]
        while stack:
            v, d = stack.pop()
            depth[v] = d
            stack.extend((c, d + 1) for c in children[v])
    tiers = sorted({depth[p] for p in leafy})
    choice = {d: 0 for d in tiers}

    def stacked(ch):
        return {p: min(ch[depth[p]], len(children[p])) for p in leafy if ch[depth[p]]}

    for _ in range(3 * len(tiers) + 1):
        improved = False
        for d in tiers:
            for columns in range(0, 4):
                if columns == choice[d]:
                    continue
                trial = {**choice, d: columns}
                got = fit(stacked(trial))
                if got[0] > best[0] * 1.03:
                    best, choice, improved = got, trial, True
        if not improved:
            break
    return best[1]


def _place(ids, roots, children, sizes, stacked, gap_x, gap_y, indent, gap_stack) -> Tree:
    """stacked: parent -> how many columns its leaves are stacked in."""
    depth: dict = {}

    def mark(v, d):
        depth[v] = d
        for c in children[v]:
            mark(c, d + 1)

    for r in roots:
        mark(r, 0)
    parent_of = {c: p for p, kids in children.items() for c in kids}
    # Each level is a row as tall as its tallest box; a stacked column hangs below its parent's row instead.
    levels = max(depth.values()) + 1
    row_h = [0.0] * levels
    for v in ids:
        if parent_of.get(v) not in stacked:
            row_h[depth[v]] = max(row_h[depth[v]], sizes[v][1])

    def columns(p):                     # p's leaves, column by column
        kids, m = children[p], stacked[p]
        per = -(-len(kids) // m)
        return [kids[k:k + per] for k in range(0, len(kids), per)]

    def column_height(p):
        return max(sum(sizes[c][1] for c in col) + gap_stack * (len(col) - 1) for col in columns(p))

    drop = gap_y * 0.75                 # from a parent's row to the top of its columns

    # Each row starts below the one above it, and below every stacked column hanging from two or more rows up.
    tops = [0.0]
    for d in range(1, levels):
        top = tops[d - 1] - row_h[d - 1] - gap_y
        for p in stacked:
            if depth[p] <= d - 2:
                top = min(top, tops[depth[p]] - row_h[depth[p]] - drop - column_height(p) - gap_y)
        tops.append(top)

    width: dict = {}

    def column_width(col):
        return indent + max(sizes[c][0] for c in col)

    def span(v):
        if v in stacked:
            cols = columns(v)
            inner = sum(column_width(col) for col in cols) + gap_x * (len(cols) - 1)
            w = max(sizes[v][0], inner)
        elif children[v]:
            w = max(sizes[v][0], sum(span(c) for c in children[v]) + gap_x * (len(children[v]) - 1))
        else:
            w = sizes[v][0]
        width[v] = w
        return w

    centres: dict = {}
    spines: dict = {}                   # stacked parent -> [(spine x, its column's leaves)]

    def put(v, left):
        w, h = sizes[v]
        top = tops[depth[v]]
        if v in stacked:
            cols = columns(v)
            inner = sum(column_width(col) for col in cols) + gap_x * (len(cols) - 1)
            x = left + width[v] / 2
            centres[v] = (x, top - h / 2)
            x0 = x - inner / 2
            spines[v] = []
            for col in cols:
                yy = top - row_h[depth[v]] - drop
                for c in col:
                    cw, ch = sizes[c]
                    centres[c] = (x0 + indent + cw / 2, yy - ch / 2)
                    yy -= ch + gap_stack
                spines[v].append((x0 + indent / 2, col))
                x0 += column_width(col) + gap_x
            return
        if children[v]:
            inner = sum(width[c] for c in children[v]) + gap_x * (len(children[v]) - 1)
            x0 = left + (width[v] - inner) / 2
            for c in children[v]:
                put(c, x0)
                x0 += width[c] + gap_x
            first, last = centres[children[v][0]][0], centres[children[v][-1]][0]
            centres[v] = ((first + last) / 2, top - h / 2)
        else:
            centres[v] = (left + w / 2, top - h / 2)

    left = 0.0
    for r in roots:
        span(r)
        put(r, left)
        left += width[r] + gap_x * 2

    connectors, joins = [], {}
    for p in ids:
        kids = children[p]
        if not kids:
            continue
        px, py = centres[p]
        bottom = py - sizes[p][1] / 2
        joins[p] = (px, bottom)
        if p in stacked:
            bar = bottom - drop * 0.45
            for spine, col in spines[p]:
                for c in col:
                    cx, cy = centres[c]
                    points = [(cx - sizes[c][0] / 2, cy), (spine, cy), (spine, bar), (px, bar), (px, bottom)]
                    connectors.append((p, c, points))
            continue
        child_top = max(centres[c][1] + sizes[c][1] / 2 for c in kids)
        bar = bottom - (bottom - child_top) * 0.5
        for c in kids:
            cx, cy = centres[c]
            top = cy + sizes[c][1] / 2
            points = [(cx, top), (cx, bar), (px, bar), (px, bottom)]
            if abs(cx - px) < 1e-6:
                points = [(cx, top), (px, bottom)]
            connectors.append((p, c, points))

    xs = [centres[v][0] - sizes[v][0] / 2 for v in centres] + [centres[v][0] + sizes[v][0] / 2 for v in centres]
    ys = [centres[v][1] - sizes[v][1] / 2 for v in centres] + [centres[v][1] + sizes[v][1] / 2 for v in centres]
    x_mid, y_mid = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    centres = {v: (x - x_mid, y - y_mid) for v, (x, y) in centres.items()}
    connectors = [(p, c, [(x - x_mid, y - y_mid) for x, y in pts]) for p, c, pts in connectors]
    joins = {p: (x - x_mid, y - y_mid) for p, (x, y) in joins.items()}
    return Tree(centres, connectors, joins, max(xs) - min(xs), max(ys) - min(ys), dict(stacked), depth)


def overlaps(tree: Tree, sizes: dict, pad: float = 0.02) -> list[tuple[str, str]]:
    """Pairs of boxes that overlap (none, in a good layout)."""
    out = []
    ids = list(tree.centres)
    for i, a in enumerate(ids):
        ax, ay = tree.centres[a]
        aw, ah = sizes[a]
        for b in ids[i + 1:]:
            bx, by = tree.centres[b]
            bw, bh = sizes[b]
            if abs(ax - bx) < (aw + bw) / 2 - pad and abs(ay - by) < (ah + bh) / 2 - pad:
                out.append((a, b))
    return out
