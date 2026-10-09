"""Layout for flowcharts: processes that branch, join, decide and loop back, laid out the way a good textbook draws
them, in ranks that follow the flow.

The steps are the standard layered (Sugiyama) ones, kept small enough to read:

1. Loops are found (an edge back to a step still on the way to it) and set aside: they are drawn round the
   outside of the chart, not through it.
2. Each step gets a rank: one more than the furthest step that leads to it, so every arrow points forward.
3. An arrow that skips ranks gets a waypoint in each rank it crosses, so it runs through a gap and never through
   a box.
4. Steps in each rank are ordered to cross as few arrows as possible (the average place of their neighbours,
   swept forward and back), and, with lanes, kept in their lane's band.
5. Ranks run left to right or top to bottom, whichever lets the chart be drawn bigger on the board.

Everything here is plain numbers: pocket_lecture.flowchart draws the boxes and the arrows.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Layout:
    direction: str                      # "right" (ranks left to right) or "down" (ranks top to bottom)
    centres: dict                       # node id -> (x, y)
    routes: list                        # (a, b, [(x, y), ...] waypoints between them, back: bool)
    lanes: list = field(default_factory=list)    # (name, low, high): a lane's band across the flow
    rank_of: dict = field(default_factory=dict)


def _back_edges(ids: list[str], edges: list[tuple[str, str]]) -> set[int]:
    """Indices of the edges that close a loop, found depth first from the steps in the order given."""
    out: dict[str, list[int]] = {i: [] for i in ids}
    for k, (a, b) in enumerate(edges):
        out[a].append(k)
    state: dict[str, int] = {}
    back: set[int] = set()

    def visit(v: str) -> None:
        state[v] = 1
        for k in out[v]:
            w = edges[k][1]
            if state.get(w) == 1:
                back.add(k)
            elif w not in state:
                visit(w)
        state[v] = 2

    sources = [i for i in ids if not any(b == i for a, b in edges if a != b)] or ids[:1]
    for s in sources + ids:
        if s not in state:
            visit(s)
    return back


def _ranks(ids, forward) -> dict[str, int]:
    rank = {i: 0 for i in ids}
    for _ in range(len(ids) + 1):
        changed = False
        for a, b in forward:
            if rank[b] < rank[a] + 1:
                rank[b] = rank[a] + 1
                changed = True
        if not changed:
            break
    # A step with nothing before it sits just before the first step it leads to, not back at the start.
    for i in ids:
        if not any(b == i for _, b in forward):
            after = [rank[b] for a, b in forward if a == i]
            if after:
                rank[i] = max(rank[i], min(after) - 1)
    return rank


def layout(ids: list[str], edges: list[tuple[str, str]], sizes: dict, lanes: dict | None = None,
           direction: str = "auto", board: tuple[float, float] = (12.6, 6.0), gap_rank: float = 1.25,
           gap_step: float = 0.55) -> Layout:
    """Where each step goes and which way each arrow runs. sizes: id -> (width, height) of its box; lanes: id ->
    lane name (steps of a lane share a band across the flow)."""
    edges = [(a, b) for a, b in edges if a in sizes and b in sizes and a != b]
    back = _back_edges(ids, edges)
    forward = [e for k, e in enumerate(edges) if k not in back]
    rank = _ranks(ids, forward)
    n_ranks = max(rank.values()) + 1

    # Waypoints for arrows that skip ranks.
    layers: list[list[str]] = [[] for _ in range(n_ranks)]
    for i in ids:
        layers[rank[i]].append(i)
    chains: list[tuple[str, str, list[str]]] = []
    dummy_size = (0.35, 0.35)
    all_sizes = dict(sizes)
    for k, (a, b) in enumerate(forward):
        chain = []
        for r in range(rank[a] + 1, rank[b]):
            d = f"__{k}_{r}"
            all_sizes[d] = dummy_size
            layers[r].append(d)
            chain.append(d)
        chains.append((a, b, chain))
    links: list[tuple[str, str]] = []
    for a, b, chain in chains:
        path = [a, *chain, b]
        links += list(zip(path, path[1:]))
    lane_names: list[str] = []
    lane_of: dict[str, int] = {}
    if lanes:
        for i in ids:
            name = lanes.get(i)
            if name and name not in lane_names:
                lane_names.append(name)
        for i in ids:
            lane_of[i] = lane_names.index(lanes[i]) if lanes.get(i) in lane_names else 0
        for a, b, chain in chains:
            for d in chain:
                lane_of[d] = lane_of[a] if lane_of[a] == lane_of[b] else max(lane_of[a], lane_of[b])

    # Order within ranks: barycentre sweeps, lanes kept apart.
    order = {v: p for layer in layers for p, v in enumerate(layer)}
    preds: dict[str, list[str]] = {}
    succs: dict[str, list[str]] = {}
    for a, b in links:
        succs.setdefault(a, []).append(b)
        preds.setdefault(b, []).append(a)

    def sweep(layer, neighbours):
        def key(v):
            near = neighbours.get(v) or []
            centre = sum(order[u] for u in near) / len(near) if near else order[v]
            return (lane_of.get(v, 0), centre, order[v])
        layer.sort(key=key)
        for p, v in enumerate(layer):
            order[v] = p

    for layer in layers:
        layer.sort(key=lambda v: (lane_of.get(v, 0), order[v]))
        for p, v in enumerate(layer):
            order[v] = p
    for _ in range(6):
        for layer in layers[1:]:
            sweep(layer, preds)
        for layer in reversed(layers[:-1]):
            sweep(layer, succs)

    def place(dirn: str) -> tuple[dict, list, float, float]:
        """Centres for ranks running `dirn`; with the chart's width and height."""
        along = 0 if dirn == "right" else 1             # the axis ranks advance on
        across = 1 - along

        def extent(v, axis):
            return all_sizes[v][axis]

        # Rank positions along the flow.
        rank_pos, at = [], 0.0
        for layer in layers:
            thick = max(extent(v, along) for v in layer) if layer else 0.5
            rank_pos.append(at + thick / 2)
            at += thick + gap_rank
        # Places across the flow: lanes get bands; a band is as wide as its widest rank.
        centres: dict = {}
        bands = []
        groups = sorted({lane_of.get(v, 0) for layer in layers for v in layer}) if lane_names else [0]
        start = 0.0
        for g in groups:
            need = 0.0
            for layer in layers:
                members = [v for v in layer if (lane_of.get(v, 0) if lane_names else 0) == g]
                if members:
                    need = max(need, sum(extent(v, across) for v in members) + gap_step * (len(members) - 1))
            need = max(need, 0.8)
            for r, layer in enumerate(layers):
                members = [v for v in layer if (lane_of.get(v, 0) if lane_names else 0) == g]
                if not members:
                    continue
                total = sum(extent(v, across) for v in members) + gap_step * (len(members) - 1)
                pos = start + (need - total) / 2
                for v in members:
                    c = pos + extent(v, across) / 2
                    xy = [0.0, 0.0]
                    xy[along] = rank_pos[r]
                    xy[across] = c
                    centres[v] = tuple(xy)
                    pos += extent(v, across) + gap_step
            bands.append((lane_names[g] if lane_names else "", start - gap_step / 2, start + need + gap_step / 2))
            start += need + gap_step * (2.2 if lane_names else 1)
        span_along = at - gap_rank
        span_across = start - gap_step * (2.2 if lane_names else 1)
        # Screen y grows upward: ranks top to bottom run down, places across a "right" chart run down too.
        flipped = {}
        for v, (x, y) in centres.items():
            if dirn == "right":
                flipped[v] = (x - span_along / 2, -(y - span_across / 2))
            else:
                flipped[v] = (x - span_across / 2, -(y - span_along / 2))
        lanes_out = []
        for name, lo, hi in bands:
            if dirn == "right":
                lanes_out.append((name, -(hi - span_across / 2), -(lo - span_across / 2)))
            else:
                lanes_out.append((name, lo - span_across / 2, hi - span_across / 2))
        width, height = (span_along, span_across) if dirn == "right" else (span_across, span_along)
        return flipped, lanes_out, width, height

    choices = ["right", "down"] if direction == "auto" else [direction]
    best = None
    for dirn in choices:
        centres, lanes_out, width, height = place(dirn)
        scale = min(board[0] / max(width, 0.1), board[1] / max(height, 0.1))
        if best is None or scale > best[0] * 1.08:
            best = (scale, dirn, centres, lanes_out)
    _, dirn, centres, lanes_out = best

    routes = []
    for a, b, chain in chains:
        routes.append((a, b, [centres[d] for d in chain], False))
    for k in sorted(back):
        a, b = edges[k]
        routes.append((a, b, [], True))
    return Layout(direction=dirn, centres={i: centres[i] for i in ids}, routes=routes,
                  lanes=lanes_out if lane_names else [], rank_of=rank)


def crossings(lay: Layout, edges) -> int:
    """How many pairs of forward arrows cross between neighbouring ranks (for tests: a good order has few)."""
    segs = []
    for a, b, way, back in lay.routes:
        if back:
            continue
        pts = [lay.centres[a], *way, lay.centres[b]]
        segs += list(zip(pts, pts[1:]))
    count = 0
    axis = 0 if lay.direction == "right" else 1
    other = 1 - axis
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            (p1, q1), (p2, q2) = segs[i], segs[j]
            if abs(p1[axis] - p2[axis]) > 1e-6 or abs(q1[axis] - q2[axis]) > 1e-6:
                continue
            if (p1[other] - p2[other]) * (q1[other] - q2[other]) < -1e-9:
                count += 1
    return count
