"""The look and the few primitives: how a word, an icon, dots, a shape or a number is drawn, so every video is in
one style and a score names them in a few words. They are deliberately plain: what makes a video alive is what the
actions do with them (render.py), not the primitives.

Kinds (`ent NAME KIND ARGS [mods]`):
    text "WORDS"            words; `size` (height of a capital, screen units), `bold`, `serif`, `color`, `width`
    icon NAME               a line icon (Lucide); `size`, `color`, `badge COLOR` (on a filled disc), `x N` copies
    circle | rect | blob    a shape; `r` or `w`/`h`, `fill`, `line`, `dashed`
    ring                    a circle's outline; `r`, `color`, `dashed`
    waves N                 N wavy lines (water); `w`, `color`
    islands N               a chain of N islands (a stylised land); `size`, `fill`
    land NAME               a country's coastline (LANDS: japan), its islands as parts, its places as `NAME.place`
    map REGION              a real map (geo.py): a region (europe, british isles, mediterranean...), a country, or
                            "LON0,LAT0,LON1,LAT1"; `year Y` (the states of that time), `names`, `rivers`, `w`/`h`;
                            any place on it as `NAME.place` (`eu.paris`, `eu.constantinople`)
    region "NAME" map M     a country, a state of a year (`year`, else the map's) or a sea, shaded where it is on M;
                            `color`, `opacity`, `outline`
    pin "PLACE" map M       a place marked on M (a ringed dot and its name); `label "..."`, `side left`, `color`
    river "NAME" map M      a river on M; `color`, `width`
    timeline, event, span, chart, pyramid, cycle, flow, quote, doc, title, labels: the bigger pieces (kit.py)
    dots N                  N dots; `grid C` (C columns), `row`, `cluster`; `size`, `color`
    num V                   a number that can count; `prefix`, `suffix`, `size`, `color`
    bar V                   a bar of length V (of `max`, default 10) that can grow; `w` (its full length), `h`, `color`
    arrow A B               an arrow from A to B (entities or X,Y); `curve`, `color`, `dashed`
    path X,Y X,Y ...        a line through points (smooth); `dashed`, `color`, `width`
Every kind takes `at X,Y` (in its shot's frame), `layer`, `rot`, `opacity`, `x N` with `row`/`col`/`grid C` and
`gap` (N copies laid out), `shadow`.
"""

from __future__ import annotations

import math
import os
import re
import zlib
from pathlib import Path

import numpy as np
from manim import (BOLD, DOWN, LEFT, ORIGIN, RIGHT, UP, Arc, Circle, CubicBezier, DashedVMobject, Dot, Group,
                   Line, Rectangle, RoundedRectangle, SVGMobject, Text, VGroup, VMobject, CurvedArrow, Arrow,
                   ParametricFunction, NORMAL, ITALIC, ImageMobject, MarkupText, LineJointType)

import assets

ICONS = Path(__file__).resolve().parent.parent / ".cache" / "package" / "icons"
FONTS = Path(__file__).resolve().parent.parent / ".cache" / "fonts"


def _fonts() -> None:
    """The style's fonts (setup.sh puts them in .cache/fonts), known to Pango whatever the machine has."""
    try:
        import manimpango
        for f in sorted(FONTS.glob("*.ttf")):
            manimpango.register_font(str(f))
    except Exception:  # noqa: BLE001 -- no fonts: the system's are used
        pass


_fonts()

LOOKS = {
    # A warm paper explainer: ink, two strong accents and two soft ones.
    "paper": {"bg": "#F4EEE3", "ink": "#22303C", "soft": "#B9B2A6", "coral": "#E4572E", "teal": "#1B998B",
              "gold": "#F2A541", "navy": "#2E4057", "red": "#C0392B", "white": "#FFFFFF", "sky": "#9FC5E8",
              "green": "#6A994E", "paper": "#F4EEE3", "sand": "#E9DCC4", "font": "Inter Display", "body": "Inter",
              "mono": "IBM Plex Mono", "accent": "#F2A541", "card": "#FFFFFF"},
    # A printed editorial explainer (Video1's look): cream paper, near-black ink, one yellow accent, greys; tall
    # condensed capitals for headlines, small spaced monospace for labels, real objects laid on the paper.
    "editorial": {"bg": "#EFE4C8", "ink": "#1D1C1A", "soft": "#9C9381", "accent": "#F7C514", "gold": "#F7C514",
                  "coral": "#D35836", "teal": "#2E7D74", "navy": "#2F3B4C", "red": "#B83227", "white": "#FBF8F0",
                  "sky": "#8DB3C7", "green": "#5B8C3A", "sand": "#E2D3B0", "grey": "#9A9182", "paper": "#EFE4C8",
                  "card": "#FBF8F0", "font": "Oswald", "body": "Inter", "mono": "IBM Plex Mono"},
}
L = dict(LOOKS["paper"])


def use(look: str) -> None:
    L.clear()
    L.update(LOOKS.get(look, LOOKS["paper"]))
    L["_name"] = look if look in LOOKS else "paper"


def col(name) -> str:
    """A palette colour by name, or a #hex as it is."""
    if not name:
        return L["ink"]
    s = str(name)
    return s if s.startswith("#") else L.get(s, L["ink"])


# ---------------------------------------------------------------- shapes of the style --------------------------------

STROKE = 6           # the style's line, in pixels at 1080p


def shadow(mob, k: float = 1.0):
    """A soft drop shadow under a filled shape (a darker copy, down and right)."""
    s = mob.copy()
    s.set_fill(L["ink"], opacity=0.16).set_stroke(width=0)
    s.shift(np.array([0.07, -0.09, 0]) * k)
    s.set_z_index(mob.z_index - 1)
    return s


DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def for_script(words: str, font: str, headline: bool = True) -> str:
    """The face words are set in: Hindi (Devanagari letters) in Teko for headlines, Hind for the rest (setup.sh
    fetches them; the kit's own faces have no Devanagari)."""
    if DEVANAGARI.search(str(words)):
        return "Teko" if headline else "Hind"
    return font


def text(words: str, size: float = 0.6, bold: bool = False, serif: bool = False, color=None, width: float | None = None,
         italic: bool = False, font: str | None = None):
    font = font or ("DejaVu Serif" if serif else L["font"])
    font = for_script(words, font, headline=font == L["font"])
    t = Text(str(words), font=font, weight=BOLD if bold else NORMAL, slant=ITALIC if italic else NORMAL,
             color=col(color), font_size=48)
    # `size`: a capital's height in screen units (Text's height includes descenders: about 1.35 of a capital).
    t.scale(size * 1.35 / max(t.height, 0.01) if t.height else 1)
    if width and t.width > width:
        t.scale_to_fit_width(width)
    return t


# Line icons are not drawn unless V3_ICONS=1: `icon NAME` is a small hand-drawn picture of the thing instead.
ICONS = os.environ.get("V3_ICONS", "0").strip() == "1"
ICON_WORDS = {"user": "a person", "users": "a small group of people", "coins": "a small pile of coins",
              "landmark": "a classical stone building with columns", "store": "a market stall",
              "map-pin": "a map pin", "badge-check": "a seal of approval", "scroll": "a rolled parchment scroll",
              "swords": "two crossed swords", "crown": "a crown", "church": "a small stone church"}


def icon_words(name: str) -> str:
    """The words a picture is made from for what was an icon's name (`graduation-cap` -> `a graduation cap`)."""
    n = str(name).strip().lower()
    if n in ICON_WORDS:
        return ICON_WORDS[n]
    words = re.sub(r"[-_]+", " ", re.sub(r"[-_]?\d+$", "", n)).strip()
    return f"a {words}" if words else "a small object"


def figure(size: float = 0.4, color=None):
    """A little person drawn with a pen: a round head and a body (a crowd's one; no icon)."""
    c = col(color or "ink")
    head = Circle(radius=size * 0.22, fill_color=c, fill_opacity=1, stroke_width=0).move_to([0, size * 0.32, 0])
    body = Arc(radius=size * 0.38, start_angle=0, angle=math.pi, fill_color=c, fill_opacity=1, stroke_width=0)
    body.move_to([0, -size * 0.18, 0])
    return VGroup(head, body)


def icon(name: str, size: float = 1.2, color=None, badge=None):
    path = ICONS / f"{name}.svg"
    if not path.exists():
        path = ICONS / "circle.svg"
    m = SVGMobject(str(path))
    m.set_fill(opacity=0)
    m.scale_to_fit_height(size * (0.58 if badge else 1.0))
    m.set_stroke(col("white" if badge else color), width=STROKE * (0.9 if badge else 1.0))
    if not badge:
        return m
    disc = Circle(radius=size / 2, fill_color=col(badge), fill_opacity=1, stroke_width=0)
    m.move_to(disc)
    g = VGroup(shadow(disc), disc, m)
    return g


def blob(r: float = 1.0, seed: int = 0, fill=None, wobble: float = 0.12, soft: bool = False):
    """A soft irregular round shape (land, a cloud of something, a region). `soft`: a light tint of its colour with
    a thin edge of the same colour (a region things sit in), else a solid shape with no ink outline."""
    rng = np.random.default_rng(seed)
    k = rng.uniform(-wobble, wobble, 6)
    ph = rng.uniform(0, math.tau, 6)

    def f(t):
        rr = r * (1 + sum(k[i] * math.sin((i + 2) * t + ph[i]) for i in range(3)))
        return np.array([rr * math.cos(t) * 1.25, rr * math.sin(t) * 0.8, 0])
    c = col(fill or "sand")
    m = ParametricFunction(f, t_range=[0, math.tau], fill_color=c, fill_opacity=0.28 if soft else 1,
                           stroke_color=c, stroke_width=STROKE * 0.5, stroke_opacity=0.9 if soft else 0)
    return m


def islands(n: int = 4, size: float = 1.0, fill=None):
    """A chain of islands along a gentle arc, the largest in the middle (a stylised archipelago)."""
    g = VGroup()
    scales = [0.55, 1.25, 0.7, 0.45, 0.4, 0.35][:max(1, n)]
    for i, s in enumerate(scales):
        b = blob(0.9 * s * size, seed=7 + i, fill=fill or "sand", wobble=0.16)
        b.rotate(0.55 + 0.25 * i)
        a = -0.9 + i * (1.8 / max(1, n - 1))
        b.move_to(np.array([math.sin(a) * 2.6 * size, math.cos(a) * 1.4 * size - 1.0 * size, 0]))
        g.add(b)
    return g


# Coastlines (longitude, latitude), drawn simply: a land's islands in order, and its places.
LANDS = {
    "japan": {
        "islands": [
            [(140.0, 41.5), (141.2, 41.8), (142.5, 42.3), (143.3, 42.0), (144.4, 42.9), (145.6, 43.3), (145.2, 44.2),
             (143.0, 44.4), (141.9, 45.4), (141.6, 44.0), (141.3, 43.2), (140.4, 43.3), (139.9, 42.6), (140.4, 42.2)],
            [(130.9, 34.0), (132.0, 34.3), (133.5, 34.4), (135.0, 34.6), (135.5, 34.3), (136.0, 33.5), (136.9, 34.3),
             (137.5, 34.6), (138.8, 34.6), (139.2, 35.0), (139.8, 35.0), (139.7, 35.4), (140.0, 35.0), (140.9, 35.7),
             (140.6, 36.8), (141.0, 38.0), (141.6, 38.9), (141.9, 40.0), (141.5, 41.4), (140.4, 41.2), (139.9, 40.6),
             (140.0, 39.5), (139.7, 38.6), (139.0, 37.9), (138.5, 37.4), (137.3, 36.8), (136.8, 37.3), (136.6, 36.7),
             (135.9, 35.7), (134.5, 35.6), (133.0, 35.5), (132.0, 35.0), (131.0, 34.4)],
            [(132.6, 33.0), (133.2, 33.4), (134.2, 33.2), (134.7, 33.8), (134.6, 34.2), (133.8, 34.4), (133.0, 34.0),
             (132.5, 33.6)],
            [(129.8, 33.2), (130.3, 33.8), (131.0, 33.9), (131.7, 33.6), (131.9, 32.8), (131.4, 31.4), (130.6, 31.1),
             (130.2, 31.4), (130.4, 32.2), (129.9, 32.7)],
        ],
        "places": {"tokyo": (139.7, 35.7), "uraga": (139.75, 35.15), "yokohama": (139.6, 35.45), "osaka": (135.5, 34.7),
                   "kyoto": (135.8, 35.0), "nagasaki": (129.9, 32.8), "hiroshima": (132.5, 34.4),
                   "sendai": (140.9, 38.3), "aomori": (140.7, 40.8), "sapporo": (141.35, 43.06),
                   "kagoshima": (130.6, 31.6)},
        "middle": (137.5, 38.0),
    },
}


def land(name: str, size: float = 1.0, fill=None):
    """A country's coastline (LANDS), its islands as parts (largest first in the list order), its places kept as
    invisible points that move with it (`land.places`: name -> point mobject), so a score can say `japan.tokyo`."""
    spec = LANDS.get(name) or LANDS["japan"]
    mx, my = spec["middle"]
    k = 0.32 * size

    def xy(lon, lat):
        return np.array([(lon - mx) * k, (lat - my) * k * 1.22, 0.0])
    g = VGroup()
    for coast in spec["islands"]:
        m = VMobject(fill_color=col(fill or "sand"), fill_opacity=1, stroke_color=col("ink"), stroke_width=STROKE * 0.55)
        pts = [xy(*p) for p in coast]
        m.set_points_smoothly([*pts, pts[0]])
        g.add(m)
    g.places = {}
    for pname, (lon, lat) in spec["places"].items():
        d = Dot(xy(lon, lat), radius=0.01).set_opacity(0)
        g.places[pname] = d
    # The places ride along as the land moves (a group of their own inside it, after the islands).
    g.add(VGroup(*g.places.values()))
    return g


def waves(n: int = 3, w: float = 12.0, color=None):
    g = VGroup()
    for i in range(n):
        amp, k = 0.09, 2 * math.pi / 1.6
        line = ParametricFunction(lambda x, i=i: np.array([x, amp * math.sin(k * x + i * 1.3), 0]),
                                  t_range=[-w / 2 + i * 0.4, w / 2 - i * 0.4], stroke_color=col(color or "teal"),
                                  stroke_width=STROKE * 0.8, stroke_opacity=0.85 - 0.18 * i)
        line.shift(DOWN * 0.42 * i)
        g.add(line)
    return g


# Icons that read as silhouettes when filled (people in a crowd); others are drawn as lines.
SOLID = {"user", "user-round", "person-standing", "circle", "square", "heart", "star", "house", "home"}


def dots(n: int, layout: str = "grid", cols: int = 10, size: float = 0.16, color=None, shape=None):
    # A dot is small whatever `size` a model writes (it means 1 for an icon); the group stays a compact block.
    # `shape NAME`: each one a small icon (`shape user`: people) instead of a dot.
    n = max(1, min(int(n), 400))
    size = 0.16 if size > 0.5 else min(max(size, 0.05), 0.22)
    if shape and (not ICONS or str(shape) in ("user", "person", "people")):
        one = figure(size * 2.8, color)             # people: little drawn figures (no icons)
        g = VGroup(*[one.copy() for _ in range(n)])
    elif shape and ICONS:
        one = icon(str(shape), size * 2.8, color or "ink")
        if str(shape) in SOLID:                     # a silhouette reads filled; an outline icon stays a line
            one.set_fill(col(color or "ink"), opacity=1)
        g = VGroup(*[one.copy() for _ in range(n)])
    else:
        g = VGroup(*[Dot(radius=size, color=col(color or "coral")) for _ in range(n)])
    if layout == "row":
        g.arrange(RIGHT, buff=size * 0.9)
    elif layout == "cluster":
        rng = np.random.default_rng(n)
        for i, d in enumerate(g):
            a, r = i * 2.39996, size * 2.4 * math.sqrt(i)
            d.move_to([r * math.cos(a), r * math.sin(a), 0])
    else:
        g.arrange_in_grid(cols=max(1, min(cols, n)), buff=size * 0.9)
    if g.width > 6 or g.height > 4:
        g.scale(min(6 / g.width, 4 / g.height))
    return g


def phrase(words: str, size: float, width: float, c=None, bold: bool = False, serif: bool = False) -> VGroup:
    """Words laid out a word a part (wrapped to a width, centred), so each can come on as it is said
    (`in P speak` over the words that say it)."""
    from manim import Text
    ws = [w for w in str(words).split() if w]
    font = for_script(words, "DejaVu Serif" if serif else L["font"])
    ref = Text("H", font=font, weight=BOLD if bold else NORMAL, font_size=48)
    k = size / max(ref.height, 0.01)
    parts = [Text(w, font=font, weight=BOLD if bold else NORMAL, color=col(c), font_size=48).scale(k) for w in ws]
    space, lead = size * 0.42, size * 1.75
    rows, row, x = [], [], 0.0
    for p in parts:
        if row and x + space + p.width > width:
            rows.append(row)
            row, x = [], 0.0
        x += (space if row else 0.0) + p.width
        row.append(p)
    if row:
        rows.append(row)
    g = VGroup()
    for i, row in enumerate(rows):
        total = sum(p.width for p in row) + space * (len(row) - 1)
        x = -total / 2
        for p in row:
            # on one baseline: each word's own bottom put where a "Hg" box's would be
            # on one baseline: a word's bottom is its baseline, less a descender's depth when it has one
            low = size * 0.3 if any(ch in "gjpqy,;" for ch in p.text if hasattr(p, "text")) else 0.0
            p.move_to([x + p.width / 2, 0, 0])
            p.shift([0, -i * lead - (p.get_bottom()[1] + low), 0])
            x += p.width + space
            g.add(p)
    return g.move_to([0, 0, 0])


class Valued:
    """A piece with a value that `count` and `grow` change (`set_value`): a calendar filling, a meter rising."""


# Numbers grouped as India writes them (12,34,56,789: lakh and crore) unless V3_NUMBERS=western (123,456,789).
INDIAN = os.environ.get("V3_NUMBERS", "indian").strip().lower() != "western"


def grouped(v: float, decimals: int = 0) -> str:
    """A number with its digits grouped (Indian: 1,00,000 is a lakh, 1,00,00,000 a crore)."""
    s = f"{abs(v):,.{decimals}f}"
    if INDIAN:
        whole, _, frac = f"{abs(v):.{decimals}f}".partition(".")
        if len(whole) > 3:
            head, tail = whole[:-3], whole[-3:]
            pairs = []
            while len(head) > 2:
                pairs.insert(0, head[-2:])
                head = head[:-2]
            whole = ",".join([head] + pairs + [tail]) if head else ",".join(pairs + [tail])
        s = whole + ("." + frac if frac else "")
    return ("-" if v < 0 else "") + s


class Num(VGroup):
    """A number that can count: its words rebuilt as its value changes, in place."""

    def __init__(self, value: float, prefix: str = "", suffix: str = "", size: float = 1.0, color=None, bold=True):
        super().__init__()
        self.value, self.prefix, self.suffix, self.size_, self.color_, self.bold = value, prefix, suffix, size, color, bold
        self.decimals = 0 if float(value).is_integer() else 1
        self.add(self._make(value))

    def _make(self, v: float):
        s = grouped(v, self.decimals) if abs(v) >= 10000 else f"{v:.{self.decimals}f}"
        return text(f"{self.prefix}{s}{self.suffix}", self.size_, bold=self.bold, color=self.color_)

    def set_value(self, v: float) -> None:
        old = self.submobjects[0]
        new = self._make(v)
        new.move_to(old)
        new.set_opacity(old.get_fill_opacity())
        self.submobjects[0] = new
        self.value = v


class Bar(VGroup):
    """A bar from its left end that can grow to a value (of `top`)."""

    def __init__(self, value: float, top: float = 10, w: float = 6, h: float = 0.55, color=None):
        super().__init__()
        self.value, self.top, self.full, self.h = value, top, w, h
        self.track = RoundedRectangle(width=w, height=h, corner_radius=h / 2, fill_color=col("sand"), fill_opacity=1,
                                      stroke_width=0)
        self.fill_ = RoundedRectangle(width=max(h, w * value / top), height=h, corner_radius=h / 2,
                                      fill_color=col(color or "coral"), fill_opacity=1, stroke_width=0)
        self.fill_.align_to(self.track, LEFT)
        self.add(self.track, self.fill_)

    def set_value(self, v: float) -> None:
        width = max(self.h, self.full * max(0.0, v) / self.top)
        new = RoundedRectangle(width=width, height=self.h, corner_radius=self.h / 2, fill_color=self.fill_.get_fill_color(),
                               fill_opacity=self.fill_.get_fill_opacity(), stroke_width=0)
        new.align_to(self.track, LEFT).set_y(self.track.get_y())
        new.set_z_index(self.fill_.z_index)
        self.fill_.become(new)
        self.value = v


def path(points: list[tuple[float, float]], smooth: bool = True, color=None, width: float = 1.0, dashed: bool = False):
    p = VMobject(stroke_color=col(color or "ink"), stroke_width=STROKE * width)
    pts = [np.array([x, y, 0.0]) for x, y in points]
    if smooth and len(pts) > 2:
        p.set_points_smoothly(pts)
    else:
        p.set_points_as_corners(pts)
    if not dashed:
        return p
    d = DashedVMobject(p, num_dashes=max(8, int(p.get_arc_length() * 3)))
    d.track = p          # the curve itself, for what travels along it
    return d


def arrow(a, b, curve: float = 0.0, color=None, dashed: bool = False):
    if curve:
        m = CurvedArrow(np.array(a), np.array(b), angle=curve, color=col(color or "ink"), stroke_width=STROKE,
                        tip_length=0.28)
    else:
        m = Arrow(np.array(a), np.array(b), buff=0, color=col(color or "ink"), stroke_width=STROKE, tip_length=0.28,
                  max_tip_length_to_length_ratio=0.2)
    return m


def build(kind: str, args: list[str], mods: dict, locate=None, find=None):
    """An entity's drawing (at the origin; render.py places it). `locate(name)`: another entity's place, for an
    arrow between entities; `find(name)`: another entity's drawing (the map a region, pin or river is on: these are
    drawn where they stand on it)."""
    size = float(mods.get("size", 0))
    c = mods.get("color")
    if kind == "text":
        m = text(args[0] if args else "", size or 0.6, bold=bool(mods.get("bold")), serif=bool(mods.get("serif")),
                 color=c, width=mods.get("width"), italic=bool(mods.get("italic")))
    elif kind == "icon":
        if ICONS:
            m = icon(args[0] if args else "circle", size or 1.2, c, mods.get("badge"))
        else:   # no line icons: a small hand-drawn picture of the thing, on its paper cut-out
            m = picture("pic", icon_words(args[0] if args else "circle"), size or 1.2, mods)
    elif kind in ("circle", "rect", "blob", "ring"):
        # `size S`: the shape S across (when neither r nor w/h says)
        r = float(mods.get("r", size / 2 if size else 1.0))
        fill = mods.get("fill")
        if kind == "circle":
            m = Circle(radius=r, fill_color=col(fill or c or "coral"), fill_opacity=1, stroke_width=0)
        elif kind == "ring":
            m = Circle(radius=r, stroke_color=col(c or "ink"), stroke_width=STROKE, fill_opacity=0)
        elif kind == "rect":
            w_, h_ = float(mods.get("w", size or 2)), float(mods.get("h", size * 0.6 if size else 1))
            m = RoundedRectangle(width=w_, height=h_, corner_radius=min(0.18, w_ * 0.2, h_ * 0.2),
                                 fill_color=col(fill or c or "sand"), fill_opacity=1,
                                 stroke_color=col(mods.get("line") or "ink"), stroke_width=STROKE * 0.6 if mods.get("line") else 0)
        else:
            # (crc32, not hash(): hash is salted per process, and chunks of one video render in separate processes)
            m = blob(r, seed=zlib.crc32(str(args).encode()) % 97, fill=fill or c, soft=not fill)
        if mods.get("dashed"):
            m = DashedVMobject(m, num_dashes=40)
    elif kind == "waves":
        m = waves(int(args[0]) if args else 3, float(mods.get("w", 12)), c)
    elif kind == "islands":
        m = islands(int(args[0]) if args else 4, size or 1.0, mods.get("fill"))
    elif kind == "land":
        m = land(args[0] if args else "japan", size or 1.0, mods.get("fill"))
    elif kind == "map":
        m = GeoMap(args[0] if args else "world", float(mods.get("w", 12)), float(mods.get("h", 6.6)),
                   int(mods["year"]) if mods.get("year") is not None else None, bool(mods.get("names")),
                   bool(mods.get("rivers")), mods.get("fill"), bool(mods.get("compass")), bool(mods.get("scale")),
                   str(mods.get("frame") or "classic"), bool(mods.get("provinces")))
    elif kind in ("region", "pin", "river"):
        ref = mods.get("map") or mods.get("on")
        on = find(ref) if find and ref else None
        if not isinstance(on, GeoMap):
            raise ValueError(f"a {kind} is drawn on a map: `on NAME` (a `map` entity)")
        what = args[0] if args else ""
        m = (region(on, what, mods, c) if kind == "region" else pin(on, what, mods, c) if kind == "pin"
             else river(on, what, c, float(mods.get("width", 1))))
    elif kind == "dots":
        n = int(args[0]) if args else 10
        lay = "row" if mods.get("row") else "cluster" if mods.get("cluster") else "grid"
        m = dots(n, lay, int(mods.get("grid", 10)), size or 0.16, c, mods.get("shape"))
    elif kind in KIT:
        import kit
        if kind in ("event", "span", "labels", "bubble"):
            on = find(mods.get("on")) if find and mods.get("on") else None
            want = kit.Timeline if kind in ("event", "span") else (ImageMobject, VGroup, Group)
            if on is None or not isinstance(on, want):
                raise ValueError(f"a {kind} is drawn on a {'timeline' if kind in ('event', 'span') else 'thing'}: "
                                 "`on NAME`")
        if kind == "timeline":
            m = kit.Timeline(kit.year_of(args[0]), kit.year_of(args[1]), float(mods.get("w", 11)), c)
        elif kind == "event":
            m = kit.event(on, args[0], args[1] if len(args) > 1 else "", mods, c)
        elif kind == "span":
            m = kit.span(on, args[0], args[1], args[2] if len(args) > 2 else "", mods, c)
        elif kind == "chart":
            if ":" in str(mods.get("line", "")):        # `chart line 1000:42 ...`: `line` read as a modifier
                args = ["line", str(mods.pop("line"))] + list(args)
            m = kit.chart(args, mods, c)
        elif kind == "labels":
            # a name that is also a switch (`rivers`, `names`, `outline`) was read as one: it is a name here
            import score as _S
            extra = [k_ for k_, v_ in mods.items() if v_ is True and _S.MODS.get(k_, "x") is None]
            m = kit.labels(on, list(args) + extra, mods, c, mods.get("_screen"))
        elif kind in ("pyramid", "cycle", "flow", "compare", "table", "steps", "stat", "venn"):
            m = getattr(kit, kind)(args, mods, c)
        elif kind == "tree":                        # a flow from the top down: kings, lords, knights
            m = kit.flow(args, {**mods, "down": True}, c)
        elif kind == "list":
            m = kit.bullets(args, mods, c)
        elif kind == "calendar":
            m = kit.Calendar(int(float(args[0])) if args else 365, 0, int(mods.get("grid", 31)), c)
        elif kind == "meter":
            m = kit.Meter(float(args[0]) if args else 0, float(mods.get("max", 10)), float(mods.get("h", 3)),
                          args[1] if len(args) > 1 else "", c)
        elif kind == "balance":
            m = kit.Balance(args[0] if args else "", args[1] if len(args) > 1 else "", float(mods.get("w", 5)), c)
        elif kind == "bubble":
            m = kit.bubble(on, args[0] if args else "", mods, c)
        elif kind == "weather":
            m = kit.weather(args[0] if args else "snow", mods, c)
        else:
            m = getattr(kit, kind)(args[0] if args else "", mods, c)
    elif kind == "num":
        m = Num(float(args[0]) if args else 0, mods.get("prefix", ""), mods.get("suffix", ""), size or 1.0, c,
                bold=not mods.get("flat"))
    elif kind == "bar":
        m = Bar(float(args[0]) if args else 0, float(mods.get("max", 10)), float(mods.get("w", 6)), float(mods.get("h", 0.55)), c)
    elif kind == "arrow":
        a = locate(args[0]) if locate else (0, 0, 0)
        b = locate(args[1]) if locate else (1, 0, 0)
        m = arrow(a, b, float(mods.get("curve", 0)), c, bool(mods.get("dashed")))
    elif kind in KIT2:
        m = _kit2(kind, args, mods, size, c, locate, find)
    elif kind == "person":
        import people
        m = people.person(mods, size or 2.8, c)
    elif kind == "animal":
        import zoo
        m = zoo.animal(args[0] if args else "horse", mods, size or 2.6, c)
    elif kind == "prop":
        import props
        m = props.prop(args[0] if args else "crate", mods if not c else {**mods, "color": c}, size or 2.6)
    elif kind in ("nation", "country"):
        import people
        m = people.nation(args[0] if args else "France", mods, size or 2.6, c)
    elif kind == "eyes":
        # big cartoon eyes on a region of a map (`on REGION`), sized to it, or at a place (`at M.place`)
        import acts
        on = find(mods.get("on")) if find and mods.get("on") else None
        w = float(size) if size else (max(0.9, min(3.0, 0.7 * min(on.width, on.height * 1.8))) if on is not None else 1.8)
        m = acts.Eyes(args[0] if args else "angry", w)
        if on is not None:
            m.move_to(getattr(on, "anchor", on.get_center()))
    elif kind == "isotype":
        import acts
        m = acts.isotype(args, mods, size, c)
    elif kind == "note":
        import acts
        m = acts.note(args[0] if args else "", mods, size, c)
    elif kind == "phrase":
        m = phrase(args[0] if args else "", size or 0.5, float(mods.get("w", 9.0)), c, bool(mods.get("bold")),
                   bool(mods.get("serif")))
    elif kind == "who":
        # a person brought in: their picture, name, years and where they were from, as one piece
        p = picture("photo", str(mods.get("img") or f"a portrait of {args[0] if args else 'a person'}"), size or 2.4, mods)
        name = text(str(args[0] if args else "").upper(), 0.34, bold=True)
        col_ = [name]
        if mods.get("sub"):
            col_.append(label(str(mods["sub"]), 0.14, "ink"))
        if mods.get("where"):
            col_.append(label("from " + str(mods["where"]), 0.12, "soft"))
        words = VGroup(*col_).arrange(DOWN, buff=0.14, aligned_edge=LEFT)
        bar = Rectangle(width=0.1, height=words.height + 0.2, fill_color=col(c or "accent"), fill_opacity=1, stroke_width=0)
        words = VGroup(bar.next_to(words, LEFT, buff=0.18), words)
        m = Group(p, words.next_to(p, RIGHT, buff=0.35))
    elif kind == "polaroids":
        # prints dealt on the table, a little askew each: each its picture on a white print, its caption under
        prints = []
        for i, what in enumerate(args):
            ph = picture("photo", what, size or 2.2, {})
            card_ = Rectangle(width=ph.width + 0.3, height=ph.height + 0.75, fill_color=col("white"), fill_opacity=1,
                              stroke_color=col("sand"), stroke_width=1)
            ph.move_to(card_.get_top() + DOWN * (0.15 + ph.height / 2))
            one = Group(soft_shadow(card_), card_, ph)
            one.rotate(math.radians([-5, 4, -2, 6, -4][i % 5]))
            prints.append(one)
        m = Group(*prints).arrange(RIGHT, buff=-0.25)
    elif kind == "backdrop":
        # A photo over the whole screen, softened, behind everything of its shot: a place to stand in.
        what = f"commons:{args[1]}" if len(args) > 1 and args[0] == "commons" else (args[0] if args else "")
        m = picture("photo", what, float(mods.get("w", 16.5)), mods)
    elif kind == "portrait":
        p = picture("photo", str((mods.get("img") or args[0]) if args else ""), size or 2.6, mods)
        name = text(str(args[0] if args else "").upper(), 0.3, bold=True).next_to(p, DOWN, buff=0.2)
        parts = [p, name]
        if mods.get("sub"):
            parts.append(label(str(mods["sub"]), 0.12, "soft").next_to(name, DOWN, buff=0.12))
        m = Group(*parts)
    elif kind in ("pic", "photo"):
        what = f"commons:{args[1]}" if len(args) > 1 and args[0] == "commons" else (args[0] if args else "")
        # big enough to read on the screen: a cut-out at least 1.4 across, a print at least 2.4 (`w`/`h`: a box)
        dflt, low = (3.0, 1.4) if kind == "pic" else (4.6, 2.4)
        if mods.get("w") and not mods.get("h"):
            size = float(mods["w"])
        m = picture(kind, what, max(low, size) if size else dflt, mods)
        if mods.get("alive") and kind == "pic":
            # a thing come alive: its picture a body with legs, arms and a face (every person's verb works)
            import people
            body = getattr(m, "frame_of", m)
            if hasattr(m, "shown") and not hasattr(body, "shown"):
                body.shown = m.shown
            m = people.critter(body, mods, size or 2.6)
    elif kind == "flag":
        m = flag(args[0] if args else "", size or 1.6)
    elif kind == "card":
        m = card(args[0] if args else "", mods, size or 1.0)
    elif kind == "tag":
        m = tag(args[0] if args else "", size or 0.55, mods.get("fill") or c or "accent", None)
    elif kind == "label":
        m = label(args[0] if args else "", size or 0.2, c or "soft")
    elif kind == "path":
        # Its points in its shot's frame (X,Y) or places (`japan.tokyo`), where they are: a path is never moved.
        pts = []
        for a in args:      # a word that is no point, place or entity (a model's "with", "via") is passed over
            try:
                pts.append(tuple(locate(a)[:2]) if locate else tuple(float(v) for v in a.split(",")))
            except (ValueError, TypeError, KeyError):
                continue
        if len(pts) < 2:
            raise ValueError("a path needs two points or more (X,Y, a place, or an entity)")
        m = path(pts, smooth=not mods.get("flat"), color=c, width=float(mods.get("width", 1)), dashed=bool(mods.get("dashed")))
    else:
        raise ValueError(f"no kind {kind!r}")
    if mods.get("shadow") and kind in ("circle", "rect", "blob"):
        m = VGroup(shadow(m), m)
    return m


# The bigger pieces (kit.py), built from these.
KIT = {"timeline", "event", "span", "chart", "pyramid", "cycle", "flow", "quote", "doc", "title", "labels", "compare",
       "table", "list", "steps", "stat", "calendar", "meter", "balance", "venn", "formula", "bubble", "weather",
       "tree"}
# More pieces (kit2.py); `who` and `polaroids` are drawn here (they hold pictures).
KIT2 = {"numberline", "plot", "triangle", "molecule", "equation", "circuit", "race", "parliament", "market", "climate",
        "quiz", "lens", "split", "clock", "odometer", "clipping", "shade", "march", "inset", "layers", "globe"}


# ---------------------------------------------------------------- the kit's pieces -----------------------------------

def _kit2(kind, args, mods, size, c, locate, find):
    import kit2
    num = kit2._num
    if kind in ("lens", "shade", "inset"):
        on = find(mods.get("on")) if find and mods.get("on") else None
        if on is None or (kind != "lens" and not isinstance(on, GeoMap)):
            raise ValueError(f"a {kind} is drawn on a {'picture' if kind == 'lens' else 'map'}: `on NAME`")
        if kind == "lens":
            return kit2.lens(on, args[0] if args else "@0.5,0.5", mods, c)
        if kind == "shade":
            return kit2.shade(on, args[0] if args else "", args[1:], mods, c)
        return kit2.inset(on, mods, c)
    if kind == "numberline":
        return kit2.NumberLine(num(args[0]), num(args[1]), float(mods.get("w", 11)), mods.get("step"), c)
    if kind == "plot":
        return kit2.Plot(args[0], num(args[1]) if len(args) > 1 else -3, num(args[2]) if len(args) > 2 else 3,
                         float(mods.get("w", 6)), float(mods.get("h", 4)), c)
    if kind == "race":
        years = [num(y) for y in args[0].split("|")]
        series = {}
        for a in args[1:]:
            k, v = a.rsplit(":", 1)
            vals = [num(x) for x in v.split("|")]
            series[k] = (vals + [vals[-1]] * len(years))[:len(years)]
        return kit2.Race(years, series, float(mods.get("w", 8)), float(mods.get("h", 4)), mods, c)
    if kind == "market":
        return kit2.Market(float(mods.get("w", 5.5)), float(mods.get("h", 4)), c)
    if kind == "clock":
        return kit2.Clock(num(args[0]) if args else 12, float(mods.get("r", 1.3)), c)
    if kind == "odometer":
        return kit2.Odometer(num(args[0]) if args else 0, int(mods.get("digits", 0)), size or 0.8,
                             mods.get("prefix", ""), mods.get("suffix", ""), c)
    if kind == "globe":
        lon, lat = (num(v) for v in (args[0] if args else "0,20").split(","))
        return kit2.Globe(lon, lat, float(mods.get("r", 2.6)), c)
    if kind == "march":
        pts = []
        for a in args:
            try:
                pts.append(tuple(locate(a)[:2]) if locate else tuple(float(v) for v in a.split(",")))
            except (ValueError, TypeError, KeyError):
                continue
        return kit2.march(pts, mods, c)
    if kind in ("molecule", "circuit", "clipping"):
        return getattr(kit2, kind)(args[0] if args else "", mods, c)
    return getattr(kit2, kind)(args, mods, c)       # triangle, equation, parliament, climate, quiz, split, layers


_SHOWN: dict[str, tuple[float, float]] = {}


def _shown(path) -> tuple[float, float]:
    """How much of a picture's width and height is the picture itself (not the clear margin round a cut-out's
    shadow)."""
    k = str(path)
    if k not in _SHOWN:
        try:
            from PIL import Image
            im = Image.open(k)
            box = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox() if im.mode in ("RGBA", "LA") else None
            _SHOWN[k] = ((box[2] - box[0]) / im.width, (box[3] - box[1]) / im.height) if box else (1.0, 1.0)
        except Exception:  # noqa: BLE001
            _SHOWN[k] = (1.0, 1.0)
    return _SHOWN[k]


def image(path, size: float, box: tuple[float, float] | None = None):
    """A picture whose longest side is `size` (a tall object and a wide one take the same room), measured on what
    shows (a cut-out's clear margin not counted); `box` (w, h): as big as fits in it instead."""
    m = ImageMobject(str(path))
    fx, fy = _shown(path)
    sw, sh = m.width * fx, m.height * fy          # what shows, at the size it was loaded
    k = (min(box[0] / sw, box[1] / sh) if box else size / max(sw, sh))
    m.scale(k)
    return m


def picture(kind: str, prompt: str, width: float, mods: dict):
    """A made picture (assets.py): a cut-out object (`pic`) or a print (`photo`); a placeholder card naming it while
    it is not made."""
    p = assets.path_for(kind, prompt, L.get("_name", "paper"))
    if p.exists():
        box = (float(mods["w"]), float(mods["h"])) if mods.get("w") and mods.get("h") else None
        m = image(p, width, box)
        m.shown = _shown(p)              # how much of its box is the picture (the layout check measures that)
        m.spots = assets.spots(p)        # where its named parts are (a vision model's, kept beside it)
        cr = assets.credit(p)
        if cr and cr.get("needs_credit"):   # an archive picture whose licence asks for its author: said under it
            who = f"{cr.get('artist') or 'Wikimedia Commons'} · {cr.get('license')}"
            g = Group(m, label(who[:70], 0.07, "soft").next_to(m, DOWN, buff=0.06))
            g.spots, g.frame_of = m.spots, m
            return g
        return m
    if assets.is_archive(prompt):
        prompt = assets.archive_query(prompt)
    words = " ".join(prompt.split()[:4]).upper()
    box = RoundedRectangle(width=width, height=width * (0.75 if kind == "photo" else 0.8), corner_radius=0.12,
                           fill_color=col("sand"), fill_opacity=1, stroke_color=col("soft"), stroke_width=2)
    words_m = text(words, 0.16, color="soft", font=L.get("mono"), width=width * 0.85)
    return VGroup(box, words_m.move_to(box))


def flag(code: str, width: float = 1.6):
    """A country's flag, exact (flag-icons), with a thin edge."""
    try:
        return image(assets.flag(code), width)
    except Exception:  # noqa: BLE001 -- an unknown code: a plain card naming it
        box = Rectangle(width=width, height=width * 0.75, fill_color=col("card"), fill_opacity=1,
                        stroke_color=col("soft"), stroke_width=2)
        return VGroup(box, text(code.upper(), width * 0.18, bold=True).move_to(box))


def card(title: str, mods: dict, k: float = 1.0):
    """A paper card laid on the page (Video1's flag cards, the IOU note): optional flag or picture on top, a title in
    the headline face, an optional mono line under it; a soft shadow. `w`/`h` its size."""
    from manim import Group
    has_top = bool(mods.get("flag") or mods.get("img"))
    w = float(mods.get("w", 1.9 if has_top else 3.2)) * k
    h = float(mods.get("h", 2.5 if has_top else 2.0)) * k
    small = min(w, h) < 0.8                  # a token (a note in a pile): its paper edge must still read
    face = Rectangle(width=w, height=h, fill_color=col(mods.get("fill") or "card"), fill_opacity=1,
                     stroke_color=col("soft") if small else col("sand"), stroke_width=2.2 if small else 1.5)
    parts = [soft_shadow(face), face]
    top = face.get_top()[1]
    if mods.get("flag"):
        f = flag(str(mods["flag"]), w * 0.72)
        f.move_to([face.get_center()[0], top - 0.12 * h - f.height / 2, 0])
        parts.append(f)
    elif mods.get("img"):
        f = picture("pic", str(mods["img"]), w * 0.8, {"w": w * 0.8, "h": h * 0.5})   # clear of the title under it
        f.move_to([face.get_center()[0], top - 0.08 * h - f.height / 2, 0])
        parts.append(f)
    if title:
        # the title in proportion to the card: a big note's word stands tall, a token's sits small inside its edge
        size = (0.2 * k) if has_top else min(0.55 * k, h * 0.34)
        t = text(title.upper() if has_top else title, size, bold=True, color="ink", width=w * (0.86 if not small else 0.6))
        t.move_to([face.get_center()[0], (face.get_bottom()[1] + 0.3 * h) if has_top
                   else face.get_center()[1] + (0.04 * h if small else 0), 0])
        parts.append(t)
        if not has_top:
            line = Line(LEFT * w * 0.16, RIGHT * w * 0.16, color=col("accent"),
                        stroke_width=STROKE * (0.9 if not small else 0.35))
            parts.append(line.next_to(t, DOWN, buff=(0.14 * k) if not small else h * 0.08))
    if mods.get("sub"):
        sub = label(str(mods["sub"]), 0.11 * k, "soft")
        sub.move_to([face.get_center()[0], face.get_bottom()[1] + 0.12 * h, 0])
        parts.append(sub)
    return Group(*parts) if any(isinstance(p, ImageMobject) for p in parts) else VGroup(*parts)


def soft_shadow(mob, k: float = 1.0):
    """A soft shadow (three blurred-looking layers) under a flat card."""
    g = VGroup()
    for i, (o, d) in enumerate(((0.06, 0.16), (0.07, 0.1), (0.08, 0.05))):
        s = mob.copy().set_fill(L["ink"], opacity=o).set_stroke(width=0)
        s.scale(1 + d * 0.12).shift(np.array([0.04, -0.07, 0]) * k)
        g.add(s)
    return g


def readable_on(fill) -> str:
    """Ink or white, whichever reads on a colour."""
    h = col(fill).lstrip("#")
    if len(h) != 6:
        return "ink"
    r_, g_, b_ = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return "ink" if 0.299 * r_ + 0.587 * g_ + 0.114 * b_ > 0.55 else "#FFFFFF"


def tag(words: str, size: float = 0.55, fill="accent", color=None):
    """Words set on a block of the accent colour (Video1's 204%, $2 TRILLION A YEAR): a headline number or claim.
    Its words are always ink or white, whichever reads on the block (never the block's own colour)."""
    words_c = color if color and col(color) != col(fill) and readable_on(fill) == readable_on(color) \
        and abs(_lum(color) - _lum(fill)) > 0.45 else readable_on(fill)
    t = text(words.upper(), size, bold=True, color=words_c)
    pad = size * 0.32
    box = Rectangle(width=t.width + pad * 2, height=t.height + pad * 1.5, fill_color=col(fill), fill_opacity=1,
                    stroke_width=0)
    return VGroup(box, t.move_to(box))


def _lum(c) -> float:
    h = col(c).lstrip("#")
    if len(h) != 6:
        return 0.0
    r_, g_, b_ = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.299 * r_ + 0.587 * g_ + 0.114 * b_


def label(words: str, size: float = 0.2, color="soft"):
    """Small spaced capitals in the mono face (DEBT · % OF THE ECONOMY): a heading over a chart, a caption."""
    font = for_script(words, L.get("mono") or L["body"], headline=False)
    t = MarkupText(f'<span letter_spacing="{int(size * 9000)}">{_esc(words.upper())}</span>', font=font,
                   color=col(color), font_size=48)
    t.scale(size * 1.35 / max(t.height, 0.01))
    return t


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def copies(make, n: int, mods: dict):
    """`x N`: N of the entity laid out (`row`, default; `col`; `grid C`), `gap` apart."""
    made = [make() for _ in range(n)]
    g = Group(*made) if any(not isinstance(m, VMobject) for m in made) else VGroup(*made)
    gap = float(mods.get("gap", 0.4))
    if mods.get("col"):
        g.arrange(DOWN, buff=gap)
    elif mods.get("grid"):
        g.arrange_in_grid(cols=int(mods["grid"]), buff=gap)
    elif mods.get("ring"):
        r = float(mods["ring"])
        for i, m in enumerate(g):
            a = math.tau * i / n + math.pi / 2
            m.move_to([r * math.cos(a), r * math.sin(a), 0])
    else:
        g.arrange(RIGHT, buff=gap)
    return g


# ---------------------------------------------------------------- maps (real data: geo.py) ---------------------------

class _Place:
    """A point on a map by (lon, lat), where it is as the map now stands (after any move or scale)."""

    def __init__(self, m, lon: float, lat: float):
        self.m, self.ll = m, (lon, lat)

    def get_center(self):
        return self.m.to_screen(*self.ll)


class _Places:
    """`MAP.NAME`: any place on a map by name (`eu.paris`, `eu.constantinople`, `eu.north_sea`), found when asked."""

    def __init__(self, m):
        self.m, self.found = m, {}
        self.outside: dict[str, tuple[float, float]] = {}   # places beyond the map: drawn at its edge (name -> where)

    def __contains__(self, name) -> bool:
        try:
            self[name]
            return True
        except KeyError:
            return False

    def __getitem__(self, name):
        if name not in self.found:
            import geo
            lon, lat = geo.place(name, self.m.bounds)
            lon0, lat0, lon1, lat1 = self.m.bounds
            if not (lon0 <= lon <= lon1 and lat0 <= lat <= lat1):
                # Beyond the map: drawn at its edge, on the way to where it is (an army "from the east" comes in
                # from the east edge), and said (the layout check names it).
                self.outside[name] = (lon, lat)
                cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
                t = 1.0
                for p, c, lo, hi in ((lon, cx, lon0, lon1), (lat, cy, lat0, lat1)):
                    if p > hi:
                        t = min(t, (hi - c) / (p - c))
                    elif p < lo:
                        t = min(t, (lo - c) / (p - c))
                t *= 0.97
                lon, lat = cx + (lon - cx) * t, cy + (lat - cy) * t
            self.found[name] = _Place(self.m, lon, lat)
        return self.found[name]

    def __iter__(self):
        return iter(self.found)


class GeoMap(VGroup):
    """A real map of a window of the world (geo.py): the sea, the land with today's borders (or, with a `year`, the
    land with the states of that time over it), optional names and rivers. Its parts: [sea, land, borders, rivers,
    names]. Places on it: `NAME.place`."""

    def __init__(self, region: str, w: float = 12.0, h: float = 6.6, year: int | None = None, names: bool = False,
                 rivers: bool = False, fill=None, compass: bool = False, scale: bool = False, frame: str = "plain",
                 provinces: bool = False):
        super().__init__()
        import geo
        from shapely.geometry import box
        # a classic frame (a mat, a degree band, its corners) takes its room from the w x h asked for
        fm = 0.3 if frame == "classic" and min(w, h) > 2.5 else 0.0
        w, h = w - 2 * fm, h - 2 * fm
        lon0, lat0, lon1, lat1 = geo.bounds(region)
        self.region_name = region
        self.k = math.cos(math.radians((lat0 + lat1) / 2))
        # The window widened (or made taller) round its middle to fill w x h: the map takes the room it is given.
        sx, sy = (lon1 - lon0) * self.k, lat1 - lat0
        if sx / sy < w / h:
            grow = (sy * w / h / self.k - (lon1 - lon0)) / 2
            lon0, lon1 = max(-180.0, lon0 - grow), min(180.0, lon1 + grow)
        else:
            grow = (sx * h / w - sy) / 2
            lat0, lat1 = max(-85.0, lat0 - grow), min(85.0, lat1 + grow)
        self.bounds = (lon0, lat0, lon1, lat1)
        self.year = year
        self.s = min(w / ((lon1 - lon0) * self.k), h / (lat1 - lat0))
        self.mid = ((lon0 + lon1) / 2, (lat0 + lat1) / 2)
        self.span = max(lon1 - lon0, lat1 - lat0)
        self.clip = box(*self.bounds)
        sw, sh = (lon1 - lon0) * self.k * self.s, (lat1 - lat0) * self.s
        # Three hidden points carried along when the map moves or scales: where its own coordinates go.
        self._ref = VGroup(*(Dot(p, radius=0.001).set_opacity(0) for p in (ORIGIN, RIGHT, UP)))
        sea = Rectangle(width=sw, height=sh, fill_color=col("sky"), fill_opacity=0.32, stroke_width=0)
        land_c = col(fill or ("card" if L.get("_name") == "editorial" else "sand"))
        land, borders = VGroup(), VGroup()
        self.shapes = {}
        today = geo.countries(self.bounds)
        from shapely.ops import unary_union
        # the land as it really is (Natural Earth's coast): what a state of another year or a region is cut to, so
        # their coasts are the real coast and only their inner borders come from the coarser historical data
        self.land_g = unary_union([g.buffer(0) for _, g in today]).intersection(self.clip.buffer(1.0))
        if year is None:
            for name, g in today:
                mob = self.shape_mob(g, fill=land_c, stroke=col("soft"), width=1.3)
                if len(mob):
                    land.add(mob)
                    self.shapes[name] = g
        else:                                   # today's borders not drawn: the land one shape (no seams in it)
            land.add(*self.shape_mob(self.land_g, fill=land_c, stroke=land_c, width=0.8))
        self.unclaimed = None
        if year is not None:
            self.shapes = {}
            st = geo.states(year, self.bounds)
            # the land no state of that year covers: the strip between the historical data's rough coast and the
            # real one, which each state grows into so it meets the real coast (no sawtooth along the shore)
            try:
                self.unclaimed = self.land_g.difference(unary_union([g.buffer(0) for _, g in st]))
            except Exception:  # noqa: BLE001
                self.unclaimed = None
            for name, g in st:
                g = self.on_land(g)
                mob = self.shape_mob(g, fill=None, stroke=col("grey") if "grey" in L else col("soft"), width=1.5)
                if len(mob):
                    borders.add(mob)
                    self.shapes[name] = g
        if provinces and year is None:
            # the states and provinces inside the countries that fill the window (thin, lighter than borders)
            seen = self.clip.intersection(self.land_g).area or 1.0
            big = {n for n, g in today if g.intersection(self.clip).area > 0.12 * seen}
            for _, admin, g in geo.provinces(self.bounds, {geo.admin_of(n) for n in big}):
                borders.add(*self.shape_mob(g.intersection(self.land_g), fill=None, stroke=col("soft"), width=0.7))
        rv = VGroup()
        if rivers:
            for _, g in geo.rivers(self.bounds):
                rv.add(*self.line_mob(g, col("sky"), 1.6))
        self.add(sea, land, borders, rv, self._names(sw / 2, sh / 2) if names else VGroup(), self._ref)
        if compass:
            self.add(self._compass(sw / 2, sh / 2))
        if scale:
            self.add(self._scale(sw / 2, sh / 2))
        if fm:
            self.add(self._frame(sw / 2, sh / 2, fm))
        elif frame != "none":                   # (`full`: no edge at all, it is the screen)
            sea.set_stroke(col("soft"), 1.5)
        self.places = _Places(self)

    def _frame(self, hw: float, hh: float, fm: float):
        """A map's frame, as an atlas plate has: a cream mat round it with a soft shadow, a double rule with the
        alternating band of a degree scale between (one stretch a round number of degrees), the degrees named in the
        margin, a square at each corner."""
        ink, paper = col("ink"), col("card")

        def ring(ow_, oh_, iw_, ih_, fill, opacity=1.0, stroke=0.0, sc=None, shift=(0.0, 0.0)):
            m = VMobject(fill_color=fill, fill_opacity=opacity, stroke_color=sc or fill, stroke_width=stroke)
            dx, dy = shift
            outer = [np.array([x + dx, y + dy, 0.0]) for x, y in ((-ow_, -oh_), (ow_, -oh_), (ow_, oh_), (-ow_, oh_), (-ow_, -oh_))]
            inner = [np.array([x + dx, y + dy, 0.0]) for x, y in ((-iw_, -ih_), (-iw_, ih_), (iw_, ih_), (iw_, -ih_), (-iw_, -ih_))]
            m.set_points_as_corners(outer)
            m.start_new_path(inner[0])
            m.add_points_as_corners(inner[1:])
            return m
        g = VGroup()
        ow_, oh_, dx, dy = hw + fm, hh + fm, 0.07, 0.09                                  # its shadow, outside it only
        shadow = VMobject(fill_color=ink, fill_opacity=0.13, stroke_width=0)
        shadow.set_points_as_corners([np.array([x, y, 0.0]) for x, y in (
            (-ow_ + dx, -oh_ - dy), (ow_ + dx, -oh_ - dy), (ow_ + dx, oh_ - dy), (ow_, oh_ - dy), (ow_, -oh_),
            (-ow_ + dx, -oh_), (-ow_ + dx, -oh_ - dy))])
        g.add(shadow)
        g.add(ring(hw + fm, hh + fm, hw, hh, paper, 1.0, 1.2, col("soft")))                 # the mat
        band = 0.07
        # the degree band: alternate stretches dark along each side, a round number of degrees each
        lon0, lat0, lon1, lat1 = self.bounds

        def step_for(span_deg, units):
            want = span_deg / max(2.0, units / 0.9)
            return min((s_ for s_ in (0.5, 1, 2, 5, 10, 15, 20, 30, 45, 60) if s_ >= want), default=60)
        lon_step, lat_step = step_for(lon1 - lon0, 2 * hw), step_for(lat1 - lat0, 2 * hh)
        marks = []                              # (where on the side, the degree there) for the names

        def stretches(a0, a1, step):
            first = math.floor(a0 / step) * step
            cuts = [a0] + [first + step * i for i in range(1, int((a1 - first) / step) + 1) if a0 < first + step * i < a1] + [a1]
            return cuts
        lon_cuts, lat_cuts = stretches(lon0, lon1, lon_step), stretches(lat0, lat1, lat_step)
        to_x = lambda lon: (lon - self.mid[0]) * self.k * self.s  # noqa: E731
        to_y = lambda lat: (lat - self.mid[1]) * self.s  # noqa: E731
        for i in range(len(lon_cuts) - 1):
            x0, x1 = to_x(lon_cuts[i]), to_x(lon_cuts[i + 1])
            for y in (hh + band / 2, -hh - band / 2):
                g.add(Rectangle(width=max(0.001, x1 - x0), height=band, fill_color=ink if i % 2 == 0 else paper,
                                fill_opacity=1, stroke_width=0).move_to([(x0 + x1) / 2, y, 0]))
        for i in range(len(lat_cuts) - 1):
            y0, y1 = to_y(lat_cuts[i]), to_y(lat_cuts[i + 1])
            for x in (hw + band / 2, -hw - band / 2):
                g.add(Rectangle(width=band, height=max(0.001, y1 - y0), fill_color=ink if i % 2 == 0 else paper,
                                fill_opacity=1, stroke_width=0).move_to([x, (y0 + y1) / 2, 0]))
        for d_ in (0.0, band):                  # the double rule
            g.add(Rectangle(width=2 * (hw + d_), height=2 * (hh + d_), fill_opacity=0, stroke_color=ink,
                            stroke_width=1.1 if d_ else 1.6))
        for sx in (-1, 1):                      # the corners
            for sy in (-1, 1):
                g.add(Rectangle(width=band, height=band, fill_color=ink, fill_opacity=1, stroke_width=0)
                      .move_to([sx * (hw + band / 2), sy * (hh + band / 2), 0]))
        # the degrees named in the margin (where there is room)
        def deg(v, pos, neg):
            v = round(v, 1)
            return f"{abs(v):g}°{pos if v >= 0 else neg}"
        last = -1e9
        for v in lon_cuts[1:-1]:
            x = to_x(v)
            if x - last < 0.9 or abs(x) > hw - 0.25:
                continue
            last = x
            g.add(label(deg(v, "E", "W"), 0.06, "soft").move_to([x, hh + band + (fm - band) / 2, 0]))
        last = -1e9
        for v in lat_cuts[1:-1]:
            y = to_y(v)
            if y - last < 0.6 or abs(y) > hh - 0.2:
                continue
            last = y
            g.add(label(deg(v, "N", "S"), 0.06, "soft").rotate(math.pi / 2).move_to([-hw - band - (fm - band) / 2, y, 0]))
        return g

    def _compass(self, hw: float, hh: float):
        """North, in the map's top right corner."""
        o = np.array([hw - 0.55, hh - 0.75, 0])
        needle = VMobject(fill_color=col("ink"), fill_opacity=1, stroke_width=0)
        needle.set_points_as_corners([o + UP * 0.4, o + RIGHT * 0.14 + DOWN * 0.1, o + DOWN * 0.02, o + LEFT * 0.14 + DOWN * 0.1,
                                      o + UP * 0.4])
        return VGroup(Circle(radius=0.3, stroke_color=col("ink"), stroke_width=1.5).move_to(o), needle,
                      label("N", 0.1, "ink").move_to(o + UP * 0.58))

    def _scale(self, hw: float, hh: float):
        """A scale bar in the bottom left corner: a round number of kilometres about a sixth of the map across."""
        km_per_unit = 111.32 / self.s                        # a degree of latitude is 111 km
        want = km_per_unit * 2 * hw / 6
        nice = min((v for v in (10, 20, 50, 100, 200, 250, 500, 1000, 2000, 5000) if v >= want * 0.6), default=5000)
        length = nice / km_per_unit
        o = np.array([-hw + 0.4, -hh + 0.35, 0])
        bar = VGroup(Rectangle(width=length / 2, height=0.08, fill_color=col("ink"), fill_opacity=1, stroke_width=0)
                     .move_to(o + RIGHT * length / 4),
                     Rectangle(width=length / 2, height=0.08, fill_color=col("card"), fill_opacity=1,
                               stroke_color=col("ink"), stroke_width=1).move_to(o + RIGHT * length * 3 / 4))
        return VGroup(bar, label(f"{grouped(nice)} km", 0.09, "ink").next_to(bar, UP, buff=0.08).align_to(bar, LEFT))

    # ---- coordinates
    def local(self, lon: float, lat: float) -> np.ndarray:
        return np.array([(lon - self.mid[0]) * self.k * self.s, (lat - self.mid[1]) * self.s, 0.0])

    def to_screen(self, lon: float, lat: float) -> np.ndarray:
        o, x, y = (d.get_center() for d in self._ref)
        p = self.local(lon, lat)
        return o + p[0] * (x - o) + p[1] * (y - o)

    # ---- drawing a shape of the world on it
    def _polys(self, g):
        from shapely.geometry import GeometryCollection, MultiPolygon, Polygon as SPoly
        if g is None or g.is_empty:
            return []
        if isinstance(g, SPoly):
            return [g]
        if isinstance(g, (MultiPolygon, GeometryCollection)):
            return [q for part in g.geoms for q in self._polys(part)]
        return []

    def on_land(self, g):
        """A state's or region's shape cut to the real land (a sea, mostly water, as it is)."""
        land = getattr(self, "land_g", None)
        if land is None or g is None or g.is_empty:
            return g
        try:
            g = g.buffer(0)
            seen = g.intersection(self.clip)
            free = getattr(self, "unclaimed", None)
            grown = g.union(g.buffer(0.35).intersection(free)) if free is not None and not free.is_empty else g
            cut = grown.intersection(land)
        except Exception:  # noqa: BLE001
            return g
        return cut if seen.is_empty or cut.area >= 0.25 * seen.area else g

    def shape_mob(self, g, fill=None, stroke=None, width: float = 1.3, opacity: float = 1.0, screen: bool = False):
        """A shape (lon/lat) clipped to the map, as filled outlines; `screen`: where the map now stands."""
        try:
            g = g.intersection(self.clip)
        except Exception:  # noqa: BLE001
            g = g.buffer(0).intersection(self.clip)
        out = VGroup()
        to = self.to_screen if screen else self.local
        for p in self._polys(g):
            if p.area < self.span ** 2 * 2e-5:
                continue
            p = p.simplify(self.span / 1800, preserve_topology=True)      # (fine enough to zoom in 3x)
            pts = [to(x, y) for x, y in list(p.exterior.coords)[:-1]]
            if len(pts) < 3:
                continue
            m = VMobject(fill_color=fill or "#000000", fill_opacity=opacity if fill else 0,
                         stroke_color=stroke or fill or "#000000", stroke_width=width, stroke_opacity=1 if width else 0)
            m.set_points_as_corners([*pts, pts[0]])
            m.joint_type = LineJointType.ROUND  # (a sharp bend of a border is no spike)
            m.no_boil = True
            out.add(m)
        return out

    def line_mob(self, g, color, width: float, screen: bool = False):
        from shapely.geometry import LineString, MultiLineString
        try:
            g = g.intersection(self.clip)
        except Exception:  # noqa: BLE001
            return VGroup()
        lines = [g] if isinstance(g, LineString) else list(getattr(g, "geoms", []))
        to = self.to_screen if screen else self.local
        out = VGroup()
        for ln in lines:
            if not isinstance(ln, LineString) or ln.length < self.span / 200:
                continue
            ln = ln.simplify(self.span / 1800)
            m = VMobject(stroke_color=color, stroke_width=width)
            m.set_points_as_corners([to(x, y) for x, y in ln.coords])
            m.joint_type = LineJointType.ROUND
            m.no_boil = True
            out.add(m)
        return out

    def _names(self, hw: float, hh: float):
        """The names of the biggest countries (or states) on it that have room, none over another or off the map."""
        sized = []
        for n, g in self.shapes.items():
            try:
                a = g.intersection(self.clip).area / self.clip.area
            except Exception:  # noqa: BLE001
                continue
            if a >= 0.012:
                sized.append((a, n))
        out, boxes = VGroup(), []
        for a, n in sorted(sized, reverse=True)[:14]:
            part = max(self._polys(self.shapes[n].intersection(self.clip)), key=lambda p: p.area, default=None)
            if part is None:
                continue
            pt = part.representative_point()
            t = label(n, 0.1 + 0.08 * min(1.0, a * 5), "ink").set_opacity(0.55).move_to(self.local(pt.x, pt.y))
            bx = (t.get_left()[0] - 0.1, t.get_bottom()[1] - 0.06, t.get_right()[0] + 0.1, t.get_top()[1] + 0.06)
            if (bx[0] < -hw or bx[2] > hw or bx[1] < -hh or bx[3] > hh
                    or any(not (bx[2] < o[0] or o[2] < bx[0] or bx[3] < o[1] or o[3] < bx[1]) for o in boxes)):
                continue
            boxes.append(bx)
            out.add(t)
        return out


def region(m: GeoMap, name: str, mods: dict, c=None):
    """A country (today's), a state of a year (`year`, or the map's), or a sea, shaded on a map where it stands:
    `outline` for its border only."""
    import geo
    year = mods.get("year", m.year)
    g, _ = geo.shape(name, int(year) if year is not None else None, m.bounds)
    if not g.intersects(m.clip):                # a name two things share (Georgia): the one on this map
        alt = geo.province(geo._norm(name.replace("_", " ")), m.bounds)
        if alt is not None and alt[0].intersects(m.clip):
            g = alt[0]
    g = m.on_land(g)
    colour = col(c or mods.get("fill") or "accent")
    if mods.get("outline"):
        return m.shape_mob(g, fill=None, stroke=colour, width=STROKE * 0.6, screen=True)
    out = m.shape_mob(g, fill=colour, stroke=colour, width=2.5, opacity=float(mods.get("opacity", 0.6)), screen=True)
    if not len(out):
        raise ValueError(f"{name!r} is not on this map")
    try:                                        # a point surely inside it (eyes are set there), and how big it shows
        seen = g.intersection(m.clip)
        pt = seen.representative_point() if not seen.is_empty else g.representative_point()
        out.anchor = m.to_screen(pt.x, pt.y)
    except Exception:  # noqa: BLE001
        out.anchor = out.get_center()
    return out


def river(m: GeoMap, name: str, c=None, width: float = 1.0):
    import geo
    out = m.line_mob(geo.river(name), col(c or "teal"), STROKE * 0.6 * width, screen=True)
    if not len(out):
        raise ValueError(f"the river {name!r} is not on this map")
    return out


def pin(m: GeoMap, where: str, mods: dict, c=None):
    """A place marked on a map: a dot in a ring, its name beside it (`label "..."`, or `label ""` for none;
    `side left|right|up|down`). Part 0 is the dot: the pin stands with it on the place."""
    p = m.places[where].get_center()
    colour = col(c or "coral")
    dot = VGroup(Circle(radius=0.17, stroke_color=col("bg"), stroke_width=6),
                 Circle(radius=0.17, stroke_color=colour, stroke_width=2.5),
                 Dot(radius=0.08, color=colour).set_stroke(col("bg"), width=3, background=True)).move_to(p)
    words = mods.get("label", where.replace("_", " "))
    g = VGroup(dot)
    if words:
        side = {"left": LEFT, "up": UP, "down": DOWN}.get(str(mods.get("side", "")), RIGHT)
        t = label(str(words), float(mods.get("size", 0.15)), "ink").next_to(dot, side, buff=0.12)
        sea = m[0]                                  # a name that would run off the map goes on the other side
        if t.get_right()[0] > sea.get_right()[0] - 0.05 or t.get_left()[0] < sea.get_left()[0] + 0.05:
            other = LEFT if t.get_center()[0] > dot.get_center()[0] else RIGHT
            t.next_to(dot, other, buff=0.12)
        g.add(t.set_stroke(col("bg"), width=5, background=True))       # a paper halo: it reads over any shading
    return g
