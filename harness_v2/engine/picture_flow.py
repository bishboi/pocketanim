"""A flow diagram drawn as ONE picture by the image model, then cut into its parts so the board can build it as it
is spoken of (the `picture_flow` op).

The model is asked for every step as a picture of its own, well apart, and every arrow as one thick arrow with a
gap at both ends, on a plain white background (genimage FLOW_FRAME). The background is cut away (genimage.cutout),
so each picture and each arrow is a separate patch of the picture: split() finds the patches, names each step's
(by the label finder's point on it, genimage.locate, or by where the layout puts it when that cannot be asked), and
gives each arrow the patches lying along the line between the two steps it joins. Each part is saved as a picture
of its own, cut to its patch, with where it sat in the whole; the engine (MapLecture.picture_flow) lays them out
as the picture was and brings each in on its words, the arrow into a step first.

A picture whose parts cannot be told apart (one patch, or fewer patches than steps) is not cut: the compiler
draws the flow as a built diagram instead (compile_lecture), and says so.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

MOST_STEPS = 6
SPLIT_VERSION = 2


def default_edges(ids: list[str], kind: str) -> list[list[str]]:
    """A flow joins its steps in order; a cycle joins the last back to the first."""
    edges = [[ids[k], ids[k + 1]] for k in range(len(ids) - 1)]
    if kind == "cycle" and len(ids) > 2:
        edges.append([ids[-1], ids[0]])
    return edges


def layout_words(n: int, kind: str) -> str:
    if kind == "cycle":
        return "arranged round a big circle, clockwise, the first at the top"
    if n <= 4:
        return "in one row from left to right"
    return f"in two rows: the first {math.ceil(n / 2)} left to right along the top, the rest left to right below"


def describe(about: str, steps: list[str], edges: list[tuple[int, int]], kind: str) -> str:
    """What the image model is asked to draw: the pictures in order, where they go, and each arrow."""
    pictures = "; ".join(f"({k + 1}) {s}" for k, s in enumerate(steps))
    arrows = ", ".join(f"from {a + 1} to {b + 1}" for a, b in edges)
    topic = f" about {about.strip()}" if about and about.strip() else ""
    return (f"A picture-diagram for a school lesson{topic}: {len(steps)} separate pictures "
            f"{layout_words(len(steps), kind)}: {pictures}. Bold arrows show the flow, one arrow for each of these "
            f"and no others: {arrows}; each arrow starts next to the picture it comes from and ends next to the "
            f"picture it goes to.")


def make(about: str, steps: list[str], edges: list[tuple[int, int]], kind: str, style: str | None,
         context: str | None = None) -> dict | None:
    """The one picture (genimage row with `file`), or None when it cannot be made."""
    import genimage

    return genimage.generate(describe(about, steps, edges, kind), style, context=context, kind="diagram",
                             aspect="16:9", match=False, flow=True)


def stand_in(what: str) -> bytes:
    """What a fake image model (PANIM_IMAGE_FAKE) draws for a picture-diagram: a coloured disc for each picture, in
    the layout asked for, and a dark arrow for each arrow asked for, all apart on white (PNG bytes)."""
    import io
    import re

    from PIL import Image, ImageDraw

    n = int((re.search(r"(\d+) separate pictures", what) or [0, 3])[1])
    cycle = "round a big circle" in what
    pairs = [(int(a) - 1, int(b) - 1) for a, b in re.findall(r"from (\d+) to (\d+)", what)]
    w, h = 1536, 1024
    if cycle:
        spots = [(w / 2 + 340 * math.sin(2 * math.pi * k / n), h / 2 - 340 * math.cos(2 * math.pi * k / n))
                 for k in range(n)]
    elif n <= 4:
        spots = [(w * (k + 0.5) / n, h / 2) for k in range(n)]
    else:
        top = math.ceil(n / 2)
        spots = [(w * (k + 0.5) / top, h * 0.28) for k in range(top)] + \
                [(w * (k + 0.5) / (n - top), h * 0.72) for k in range(n - top)]
    r = min(130, 0.32 * w / max(n if not cycle else 3, 1))
    tones = ["#C0392B", "#27AE60", "#2980B9", "#8E44AD", "#D68910", "#16A085"]
    image = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(image)
    for k, (x, y) in enumerate(spots):
        draw.ellipse((x - r, y - r, x + r, y + r), fill=tones[k % len(tones)])
    for a, b in pairs:
        if not (0 <= a < n and 0 <= b < n):
            continue
        (ax, ay), (bx, by) = spots[a], spots[b]
        d = math.hypot(bx - ax, by - ay) or 1
        ux, uy = (bx - ax) / d, (by - ay) / d
        sx, sy, ex, ey = ax + ux * (r + 40), ay + uy * (r + 40), bx - ux * (r + 40), by - uy * (r + 40)
        draw.line((sx, sy, ex - ux * 30, ey - uy * 30), fill="#222222", width=22)
        draw.polygon([(ex, ey), (ex - ux * 46 - uy * 30, ey - uy * 46 + ux * 30),
                      (ex - ux * 46 + uy * 30, ey - uy * 46 - ux * 30)], fill="#222222")
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _points(png: Path, names: list[str]) -> dict[str, tuple[float, float]] | None:
    """Where the label finder sees each step (0..1 across and down), or None when it cannot be asked."""
    import genimage

    if genimage._fake():
        return None                 # a fake label finder spreads its points down the middle: not where things are
    found = genimage.locate(str(png), names)
    if not found:
        return None
    out = {}
    for row in found:
        if len(row) >= 3:
            out[str(row[0])] = (float(row[1]), float(row[2]))
    return out if len(out) == len(names) else None


def _order_by_layout(boxes: list[tuple], n: int, kind: str) -> list[int]:
    """The n biggest patches, in the order the layout asked for: left to right (in rows), or clockwise from the
    top for a cycle. Indices into `boxes` ((x0, y0, x1, y1, area))."""
    big = sorted(range(len(boxes)), key=lambda i: -boxes[i][4])[:n]
    centre = lambda i: ((boxes[i][0] + boxes[i][2]) / 2, (boxes[i][1] + boxes[i][3]) / 2)  # noqa: E731
    if kind == "cycle":
        cx = sum(centre(i)[0] for i in big) / len(big)
        cy = sum(centre(i)[1] for i in big) / len(big)
        # Clockwise from the top in picture coordinates (y down).
        return sorted(big, key=lambda i: (math.atan2(centre(i)[0] - cx, -(centre(i)[1] - cy))) % (2 * math.pi))
    if n <= 4:
        return sorted(big, key=lambda i: centre(i)[0])
    ys = sorted(centre(i)[1] for i in big)
    split = (ys[0] + ys[-1]) / 2
    top = sorted([i for i in big if centre(i)[1] <= split], key=lambda i: centre(i)[0])
    bottom = sorted([i for i in big if centre(i)[1] > split], key=lambda i: centre(i)[0])
    return top + bottom


def _segment_distance(p, a, b) -> tuple[float, float]:
    """(distance from p to the segment a-b, where along it 0..1)."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length <= 1e-9:
        return math.hypot(p[0] - ax, p[1] - ay), 0.0
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy)), t


def split(png_path: str, names: list[str], edges: list[tuple[int, int]], kind: str) -> dict | None:
    """The picture cut into its parts: {"size": [w, h], "nodes": [[file, x0, y0, x1, y1] per step],
    "edges": [[file, x0, y0, x1, y1] or None per edge]}, boxes in the picture's pixels. Kept beside it. None when
    its parts cannot be told apart."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage

    png = Path(str(png_path))
    if not png.is_file():
        return None
    data = png.read_bytes()
    key = hashlib.sha256(data + json.dumps([names, edges, kind, SPLIT_VERSION]).encode()).hexdigest()[:12]
    kept = png.with_name(f"{png.stem}.flow-{key}.json")
    if kept.exists():
        try:
            found = json.loads(kept.read_text())
            if all(Path(row[0]).is_file() for row in found["nodes"]):
                return found
        except (ValueError, KeyError, TypeError, IndexError):
            pass
    image = Image.open(png).convert("RGBA")
    rgba = np.asarray(image)
    h, w = rgba.shape[:2]
    solid = rgba[..., 3] > 40
    # A picture's own small gaps (a hoof apart from its leg) closed, so it is one patch; arrows are kept apart
    # from pictures by the prompt's gaps, which are wider.
    joined = ndimage.binary_closing(solid, iterations=max(2, min(w, h) // 200))
    labels, count = ndimage.label(joined)
    if count < len(names):
        return None
    slices = ndimage.find_objects(labels)
    areas = ndimage.sum(np.ones_like(labels), labels, index=range(1, count + 1))
    least = 0.0015 * w * h
    boxes = []                      # (x0, y0, x1, y1, area) per patch, by label - 1
    for k, sl in enumerate(slices):
        boxes.append((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop, float(areas[k])))
    big = [i for i in range(count) if boxes[i][4] >= least]
    if len(big) < len(names):
        return None
    centre = lambda i: ((boxes[i][0] + boxes[i][2]) / 2, (boxes[i][1] + boxes[i][3]) / 2)  # noqa: E731

    # The steps: the patch under the label finder's point for each, else the layout's order.
    steps: list[int] | None = None
    points = _points(png, names)
    if points:
        chosen = []
        for name in names:
            px, py = points[name][0] * w, points[name][1] * h
            at = int(labels[min(h - 1, max(0, int(py))), min(w - 1, max(0, int(px)))]) - 1
            if at < 0 or at not in big:
                # Its point on no picture (between two, on an arrow): the finder is not trusted; the layout is.
                chosen = []
                break
            chosen.append(at)
        steps = chosen if len(chosen) == len(names) and len(set(chosen)) == len(chosen) else None
    if steps is None:
        steps = _order_by_layout([boxes[i] if i in big else (0, 0, 0, 0, 0) for i in range(count)], len(names), kind)

    # The rest: an arrow's (along the line between the two steps it joins), else the nearest step's.
    owner_nodes: dict[int, list[int]] = {k: [steps[k]] for k in range(len(steps))}
    owner_edges: dict[int, list[int]] = {e: [] for e in range(len(edges))}
    taken = set(steps)
    for i in range(count):
        if i in taken:
            continue
        c = centre(i)
        best_edge, best = None, None
        for e, (a, b) in enumerate(edges):
            ca, cb = centre(steps[a]), centre(steps[b])
            d, t = _segment_distance(c, ca, cb)
            span = math.hypot(cb[0] - ca[0], cb[1] - ca[1])
            reach = max(0.28 * span, 0.05 * max(w, h))
            if 0.08 < t < 0.92 and d < reach and (best is None or d < best):
                best_edge, best = e, d
        if best_edge is not None and boxes[i][4] >= 0.0002 * w * h:
            owner_edges[best_edge].append(i)
        else:
            near = min(range(len(steps)), key=lambda k: math.hypot(centre(steps[k])[0] - c[0],
                                                                   centre(steps[k])[1] - c[1]))
            owner_nodes[near].append(i)

    out_dir = png.parent
    grown = ndimage.binary_dilation(solid, iterations=1)

    def save(parts: list[int], tag: str):
        if not parts:
            return None
        mask = np.isin(labels, [p + 1 for p in parts]) & grown
        ys, xs = np.nonzero(mask)
        if not len(xs):
            return None
        pad = 4
        x0, x1 = max(0, int(xs.min()) - pad), min(w, int(xs.max()) + 1 + pad)
        y0, y1 = max(0, int(ys.min()) - pad), min(h, int(ys.max()) + 1 + pad)
        piece = rgba[y0:y1, x0:x1].copy()
        piece[..., 3] = np.where(mask[y0:y1, x0:x1], piece[..., 3], 0)
        target = out_dir / f"{png.stem}.flow-{key}-{tag}.png"
        Image.fromarray(piece, "RGBA").save(target, optimize=True)
        return [str(target), x0, y0, x1, y1]

    nodes = [save(owner_nodes[k], f"n{k}") for k in range(len(steps))]
    if any(n is None for n in nodes):
        return None
    found = {"size": [w, h], "nodes": nodes,
             "edges": [save(owner_edges[e], f"e{e}") for e in range(len(edges))]}
    kept.write_text(json.dumps(found))
    return found
