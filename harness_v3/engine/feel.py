"""How things feel: a paper world's motion, the hand-drawn texture over it, and the depth the camera finds in it.

    motion      a cut-out slapped down like a sticker (in bigger and turned, its shadow tightening, a small wobble as
                it lands), peeled off and flicked away, slid with a little overshoot and settle; what stands near a
                thing that lands is nudged by it.
    texture     line boil (outlines tremble a little, a few times a second, as drawings redrawn by hand), lines drawn
                by a pen (an uneven speed, a slight wobble in the line itself), paper grain and a soft vignette over
                the frame, moving gently.
    parallax    while the camera travels from one shot to the next, the layers of the paper slide at their own speeds:
                backdrops and maps behind, cut-outs in front, words in front of them.

The renderer (render.py) uses these; the player (player.html) draws the same boil from the timeline's `boil` entry.
A score turns them off with `texture off` and `parallax off` (or V3_TEXTURE=0, V3_PARALLAX=0); `motion plain`
keeps the plain fades (V3_MOTION=plain).
"""

from __future__ import annotations

import math
import os
import zlib

import numpy as np

# ---------------------------------------------------------------- settings -------------------------------------------


def _on(env: str, score_value) -> bool:
    if score_value is not None:
        return bool(score_value)
    return os.environ.get(env, "1").strip().lower() not in ("0", "off", "no", "false")


def texture_on(sc) -> bool:
    return _on("V3_TEXTURE", getattr(sc, "texture", None))


def parallax_on(sc) -> bool:
    return _on("V3_PARALLAX", getattr(sc, "parallax", None))


def motion_on(sc) -> bool:
    m = getattr(sc, "motion", None)
    if m is None:
        m = os.environ.get("V3_MOTION", "paper").strip().lower()
    return m != "plain"


def seed(name: str) -> int:
    return zlib.crc32(name.encode())


# ---------------------------------------------------------------- motion ---------------------------------------------

# Kinds that are paper cut-outs: they come on slapped down and leave peeled off when the score says no way.
CUTOUTS = {"pic", "photo", "portrait", "card", "tag", "flag", "stat", "quote", "doc", "clipping", "polaroids", "who",
           "bubble", "icon", "title", "person"}
# Kinds that land with a nudge to their neighbours.
LANDS = ("slap", "pop", "drop", "stamp")


def settle(t: float) -> float:
    """Eased there, a little past it, and back (a slide that overshoots and settles)."""
    t = min(1.0, max(0.0, t))
    peak, over = 0.74, 0.045
    if t < peak:
        x = t / peak
        e = 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2
        return (1 + over) * e
    x = (t - peak) / (1 - peak)
    return 1 + over - over * (3 * x ** 2 - 2 * x ** 3)


def slap(t: float) -> float:
    """Down fast and a small rebound (a sticker pressed onto the page)."""
    t = min(1.0, max(0.0, t))
    if t < 0.55:
        x = t / 0.55
        return 1 - (1 - x) ** 3
    x = (t - 0.55) / 0.45
    return 1 + 0.05 * math.sin(x * math.pi * 2) * (1 - x)


def wobble_angle(t: float, amp: float) -> float:
    """A turn that dies away as it settles (radians), for a thing landing at t in [0, 1]."""
    return amp * math.cos(t * math.pi * 2.5) * (1 - t) ** 1.6


def pen(t: float) -> float:
    """A pen's progress along a line: a quick start, a hesitation or two, a slower finish (monotone)."""
    t = min(1.0, max(0.0, t))
    base = t * t * (3 - 2 * t)
    v = base + 0.035 * math.sin(t * math.pi * 3) * math.sin(t * math.pi)
    return min(1.0, max(0.0, v))


# ---------------------------------------------------------------- texture --------------------------------------------

BOIL_HZ = 4.0           # how often outlines redraw themselves
BOIL_SHIFT = 0.011      # world units (about one pixel at 720p)
BOIL_TURN = 0.016       # the most an outline's far end moves by turning (world units)


def boil(index: int, step: int) -> tuple[float, float, float]:
    """A drawn outline's tremble at a boil step: (dx, dy, turn in radians per unit of its size), the same in every
    process and in the player (player.html: boil())."""
    h = (index * 73856093 ^ step * 19349663) & 0xFFFFFFFF
    a = ((h & 0x3FF) / 1023.0) * 2 - 1
    b = (((h >> 10) & 0x3FF) / 1023.0) * 2 - 1
    c = (((h >> 20) & 0x3FF) / 1023.0) * 2 - 1
    return a * BOIL_SHIFT, b * BOIL_SHIFT, c


def boils(x) -> bool:
    """An outline that boils: a drawn line (stroked, not filled: never the glyphs of words, never a filled land)."""
    if getattr(x, "no_boil", False):           # (a map's borders, coasts and rivers: measured lines stay put)
        return False
    try:
        return len(x.points) >= 4 and float(x.get_stroke_width()) > 0.5 and float(x.get_stroke_opacity()) > 0.05 \
            and float(x.get_fill_opacity()) < 0.05
    except Exception:  # noqa: BLE001
        return False


def wobbled(m, amount: float = 0.035, name: str = "") -> None:
    """A line made as if by hand: each point pushed a little across a smooth field (the same line every run)."""
    rng = np.random.default_rng(seed(name or "line"))
    k1, k2, k3, k4 = rng.uniform(0.9, 1.6, 4)
    p1, p2 = rng.uniform(0, math.tau, 2)
    for x in m.family_members_with_points():
        if len(x.points) < 4:
            continue
        P = x.points
        dx = amount * np.sin(P[:, 1] * k1 + p1) * np.cos(P[:, 0] * k2)
        dy = amount * np.sin(P[:, 0] * k3 + p2) * np.cos(P[:, 1] * k4)
        x.points[:, 0] += dx
        x.points[:, 1] += dy


def overlay_rgba(w: int = 960, h: int = 540, ink: str = "#2b2118", grain: float = 0.07, vignette: float = 0.22):
    """Paper grain and a soft vignette in one picture: specks of ink and of light, darker toward the corners."""
    from PIL import Image, ImageFilter
    rng = np.random.default_rng(11)
    n = rng.normal(0, 1, (h, w))
    fine = np.asarray(Image.fromarray(((np.clip(n, -3, 3) + 3) / 6 * 255).astype("uint8"))
                      .filter(ImageFilter.GaussianBlur(0.6))).astype(float) / 255.0
    coarse = rng.normal(0, 1, (h // 24, w // 24))
    coarse = np.asarray(Image.fromarray(((coarse - coarse.min()) / (np.ptp(coarse) + 1e-9) * 255).astype("uint8"))
                        .resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(8))).astype(float) / 255.0
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
    vig = np.clip((r - 0.45) / 0.55, 0, 1) ** 1.8 * vignette
    a = vig + grain * np.abs(fine - 0.5) * 2 * (0.6 + 0.4 * coarse)
    rgb = np.array([int(ink[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)
    img = np.zeros((h, w, 4), dtype="uint8")
    light = (fine > 0.62)[..., None]                 # a few specks of light among the dark
    img[..., :3] = np.where(light, 255, rgb[None, None, :]).astype("uint8")
    img[..., 3] = (np.clip(np.where(light[..., 0], a * 0.6, a), 0, 1) * 255).astype("uint8")
    return img


# ---------------------------------------------------------------- parallax -------------------------------------------

DEPTH = {"backdrop": 0.72, "split": 0.8, "map": 0.86, "globe": 0.86, "islands": 0.86, "land": 0.86, "waves": 0.86,
         "weather": 1.0, "pic": 1.07, "photo": 1.07, "portrait": 1.07, "polaroids": 1.07, "clipping": 1.07,
         "card": 1.05, "who": 1.07, "person": 1.07, "nation": 1.07, "country": 1.07, "text": 1.12, "label": 1.12, "tag": 1.12, "title": 1.12,
         "num": 1.12, "stat": 1.1, "quote": 1.08}


def depth(kind: str) -> float:
    return DEPTH.get(kind, 1.0)


def parallax_weight(dist: float, screen_w: float) -> float:
    """How much of its depth a thing shows with the camera `dist` from its shot: none at home (a shot's layout is
    exact while it is looked at, and moves within a shot keep their places) nor a screen away, most between."""
    # (none while the camera is anywhere in the shot, a zoom to a place on its map included: only on the way between)
    x = (dist / screen_w - 0.5) / 0.48
    if x <= 0 or x >= 1:
        return 0.0
    return math.sin(math.pi * x) ** 1.5


# ---------------------------------------------------------------- marks drawn by hand --------------------------------
# A pen's marks on the page: one stroke each, drawn in the order the pen goes (render.py draws them with `pen`).

def _path(points):
    from manim import VMobject
    m = VMobject()
    pts = [np.array([x, y, 0.0]) for x, y in points]
    m.set_points_smoothly(pts)
    return m


def scribble_ring(cx: float, cy: float, w: float, h: float, name: str):
    """A ring drawn round a thing with one stroke: a little more than once round, loose, its end past its start."""
    rng = np.random.default_rng(seed(name))
    a0 = rng.uniform(math.radians(100), math.radians(150))
    turn = rng.uniform(1.12, 1.2) * math.tau
    rx, ry = w / 2 + 0.28, h / 2 + 0.22
    tilt = rng.uniform(-0.08, 0.04)
    p1, p2 = rng.uniform(0, math.tau, 2)
    pts = []
    n = 46
    for i in range(n + 1):
        t = i / n
        a = a0 - turn * t                      # clockwise, as most hands go
        grow = 1.0 + 0.09 * t - 0.03            # a spiral: the stroke ends outside where it began
        wob = 1.0 + 0.035 * math.sin(2 * a + p1) + 0.02 * math.sin(3 * a + p2)
        x, y = rx * grow * wob * math.cos(a), ry * grow * wob * math.sin(a)
        pts.append((cx + x * math.cos(tilt) - y * math.sin(tilt), cy + x * math.sin(tilt) + y * math.cos(tilt)))
    return _path(pts)


def scribble_underline(x0: float, x1: float, y: float, name: str):
    """A swift underline: a slight bow, a little faster at the end, flicked up as the pen leaves."""
    rng = np.random.default_rng(seed(name))
    sag = rng.uniform(0.02, 0.05)
    rise = rng.uniform(-0.03, 0.04)
    pts = []
    L = x1 - x0 + 0.2
    for i in range(14):
        t = i / 13
        pts.append((x0 - 0.12 + L * t, y - sag * math.sin(math.pi * t) + rise * t))
    pts.append((x1 + 0.2, y + rise + 0.07))    # the flick
    return _path(pts)


def scribble_strike(x0: float, x1: float, y: float, name: str):
    rng = np.random.default_rng(seed(name))
    pts = [(x0 - 0.12 + (x1 - x0 + 0.24) * t, y + 0.03 * math.sin(t * 9 + rng.uniform(0, 3)) + (t - 0.5) * 0.06)
           for t in np.linspace(0, 1, 12)]
    return _path(pts)


def scribble_box(x0: float, y0: float, x1: float, y1: float, name: str):
    """A box drawn as four quick strokes, each a little bowed and running past the corners."""
    from manim import VGroup
    rng = np.random.default_rng(seed(name))
    j = lambda: rng.uniform(-0.035, 0.035)  # noqa: E731
    o = 0.09
    sides = [((x0 - o, y1 + j()), (x1 + o, y1 + j())), ((x1 + j(), y1 + o), (x1 + j(), y0 - o)),
             ((x1 + o, y0 + j()), (x0 - o, y0 + j())), ((x0 + j(), y0 - o), (x0 + j(), y1 + o))]
    g = VGroup()
    for (ax, ay), (bx, by) in sides:
        mx, my = (ax + bx) / 2, (ay + by) / 2
        nx, ny = -(by - ay), bx - ax
        k = rng.uniform(-0.012, 0.012)
        g.add(_path([(ax, ay), (mx + nx * k, my + ny * k), (bx, by)]))
    return g


def scribble_tick(x: float, y: float, s: float, name: str):
    pts = [(x, y + s * 0.05), (x + s * 0.3, y - s * 0.38), (x + s * 0.55, y + s * 0.08), (x + s * 1.0, y + s * 0.62)]
    return _path(pts)


def scribble_cross(cx: float, cy: float, s: float, name: str):
    from manim import VGroup
    rng = np.random.default_rng(seed(name))
    a = _path([(cx - s, cy + s), (cx + rng.uniform(-0.05, 0.05), cy + rng.uniform(-0.04, 0.04)), (cx + s * 1.08, cy - s * 1.05)])
    b = _path([(cx + s * 1.02, cy + s * 1.06), (cx, cy + rng.uniform(-0.04, 0.04)), (cx - s * 1.05, cy - s)])
    return VGroup(a, b)


def scribble_highlight(x0: float, x1: float, y0: float, y1: float, name: str):
    """A highlighter's stroke: a band with rough, slanted ends and edges that are not quite straight."""
    from manim import VMobject
    rng = np.random.default_rng(seed(name))
    top = [(x0 + (x1 - x0) * t, y1 + rng.uniform(-0.025, 0.025)) for t in np.linspace(0, 1, 8)]
    bot = [(x1 - (x1 - x0) * t, y0 + rng.uniform(-0.025, 0.025)) for t in np.linspace(0, 1, 8)]
    top[0] = (x0 + 0.06, y1)
    bot[-1] = (x0 - 0.04, y0)
    top[-1] = (x1 + 0.05, y1)
    bot[0] = (x1 - 0.06, y0)
    m = VMobject()
    m.set_points_as_corners([np.array([x, y, 0.0]) for x, y in top + bot + [top[0]]])
    return m
