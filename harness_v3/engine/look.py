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
import zlib
from pathlib import Path

import numpy as np
from manim import (BOLD, DOWN, LEFT, ORIGIN, RIGHT, UP, Arc, Circle, CubicBezier, DashedVMobject, Dot, Group,
                   Line, Rectangle, RoundedRectangle, SVGMobject, Text, VGroup, VMobject, CurvedArrow, Arrow,
                   ParametricFunction, NORMAL, ITALIC, ImageMobject, MarkupText)

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


def text(words: str, size: float = 0.6, bold: bool = False, serif: bool = False, color=None, width: float | None = None,
         italic: bool = False, font: str | None = None):
    font = font or ("DejaVu Serif" if serif else L["font"])
    t = Text(str(words), font=font, weight=BOLD if bold else NORMAL, slant=ITALIC if italic else NORMAL,
             color=col(color), font_size=48)
    # `size`: a capital's height in screen units (Text's height includes descenders: about 1.35 of a capital).
    t.scale(size * 1.35 / max(t.height, 0.01) if t.height else 1)
    if width and t.width > width:
        t.scale_to_fit_width(width)
    return t


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


def dots(n: int, layout: str = "grid", cols: int = 10, size: float = 0.16, color=None):
    # A dot is small whatever `size` a model writes (it means 1 for an icon); the group stays a compact block.
    n = max(1, min(int(n), 400))
    size = 0.16 if size > 0.5 else min(max(size, 0.05), 0.22)
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


class Num(VGroup):
    """A number that can count: its words rebuilt as its value changes, in place."""

    def __init__(self, value: float, prefix: str = "", suffix: str = "", size: float = 1.0, color=None, bold=True):
        super().__init__()
        self.value, self.prefix, self.suffix, self.size_, self.color_, self.bold = value, prefix, suffix, size, color, bold
        self.decimals = 0 if float(value).is_integer() else 1
        self.add(self._make(value))

    def _make(self, v: float):
        s = f"{v:,.{self.decimals}f}" if abs(v) >= 10000 else f"{v:.{self.decimals}f}"
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


def build(kind: str, args: list[str], mods: dict, locate=None):
    """An entity's drawing (at the origin; render.py places it). `locate(name)`: another entity's place, for an
    arrow between entities."""
    size = float(mods.get("size", 0))
    c = mods.get("color")
    if kind == "text":
        m = text(args[0] if args else "", size or 0.6, bold=bool(mods.get("bold")), serif=bool(mods.get("serif")),
                 color=c, width=mods.get("width"), italic=bool(mods.get("italic")))
    elif kind == "icon":
        m = icon(args[0] if args else "circle", size or 1.2, c, mods.get("badge"))
    elif kind in ("circle", "rect", "blob", "ring"):
        r = float(mods.get("r", 1.0))
        fill = mods.get("fill")
        if kind == "circle":
            m = Circle(radius=r, fill_color=col(fill or c or "coral"), fill_opacity=1, stroke_width=0)
        elif kind == "ring":
            m = Circle(radius=r, stroke_color=col(c or "ink"), stroke_width=STROKE, fill_opacity=0)
        elif kind == "rect":
            m = RoundedRectangle(width=float(mods.get("w", 2)), height=float(mods.get("h", 1)), corner_radius=0.18,
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
    elif kind == "dots":
        n = int(args[0]) if args else 10
        lay = "row" if mods.get("row") else "cluster" if mods.get("cluster") else "grid"
        m = dots(n, lay, int(mods.get("grid", 10)), size or 0.16, c)
    elif kind == "num":
        m = Num(float(args[0]) if args else 0, mods.get("prefix", ""), mods.get("suffix", ""), size or 1.0, c,
                bold=not mods.get("flat"))
    elif kind == "bar":
        m = Bar(float(args[0]) if args else 0, float(mods.get("max", 10)), float(mods.get("w", 6)), float(mods.get("h", 0.55)), c)
    elif kind == "arrow":
        a = locate(args[0]) if locate else (0, 0, 0)
        b = locate(args[1]) if locate else (1, 0, 0)
        m = arrow(a, b, float(mods.get("curve", 0)), c, bool(mods.get("dashed")))
    elif kind in ("pic", "photo"):
        m = picture(kind, args[0] if args else "", size or (2.6 if kind == "pic" else 3.6), mods)
    elif kind == "flag":
        m = flag(args[0] if args else "", size or 1.6)
    elif kind == "card":
        m = card(args[0] if args else "", mods, size or 1.0)
    elif kind == "tag":
        m = tag(args[0] if args else "", size or 0.55, mods.get("fill") or "accent", c)
    elif kind == "label":
        m = label(args[0] if args else "", size or 0.2, c or "soft")
    elif kind == "path":
        # Its points in its shot's frame (X,Y) or places (`japan.tokyo`), where they are: a path is never moved.
        pts = [tuple(locate(a)[:2]) if locate else tuple(float(v) for v in a.split(",")) for a in args]
        m = path(pts, smooth=not mods.get("flat"), color=c, width=float(mods.get("width", 1)), dashed=bool(mods.get("dashed")))
    else:
        raise ValueError(f"no kind {kind!r}")
    if mods.get("shadow") and kind in ("circle", "rect", "blob"):
        m = VGroup(shadow(m), m)
    return m


# ---------------------------------------------------------------- the kit's pieces -----------------------------------

def image(path, size: float):
    """A picture whose longest side is `size` (a tall object and a wide one take the same room)."""
    m = ImageMobject(str(path))
    if m.height > m.width:
        m.height = size
    else:
        m.width = size
    return m


def picture(kind: str, prompt: str, width: float, mods: dict):
    """A made picture (assets.py): a cut-out object (`pic`) or a print (`photo`); a placeholder card naming it while
    it is not made."""
    p = assets.path_for(kind, prompt, L.get("_name", "paper"))
    if p.exists():
        return image(p, width)
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
    face = Rectangle(width=w, height=h, fill_color=col(mods.get("fill") or "card"), fill_opacity=1,
                     stroke_color=col("sand"), stroke_width=1.5)
    parts = [soft_shadow(face), face]
    top = face.get_top()[1]
    if mods.get("flag"):
        f = flag(str(mods["flag"]), w * 0.72)
        f.move_to([face.get_center()[0], top - 0.12 * h - f.height / 2, 0])
        parts.append(f)
    elif mods.get("img"):
        f = picture("pic", str(mods["img"]), w * 0.8, {})
        f.move_to([face.get_center()[0], top - 0.08 * h - f.height / 2, 0])
        parts.append(f)
    if title:
        t = text(title.upper() if has_top else title, (0.2 if has_top else 0.55) * k, bold=True, color="ink",
                 width=w * 0.86)
        t.move_to([face.get_center()[0], (face.get_bottom()[1] + 0.3 * h) if has_top else face.get_center()[1], 0])
        parts.append(t)
        if not has_top:
            line = Line(LEFT * w * 0.16, RIGHT * w * 0.16, color=col("accent"), stroke_width=STROKE * 0.9)
            parts.append(line.next_to(t, DOWN, buff=0.14 * k))
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


def tag(words: str, size: float = 0.55, fill="accent", color=None):
    """Words set on a block of the accent colour (Video1's 204%, $2 TRILLION A YEAR): a headline number or claim."""
    t = text(words.upper(), size, bold=True, color=color or "ink")
    pad = size * 0.32
    box = Rectangle(width=t.width + pad * 2, height=t.height + pad * 1.5, fill_color=col(fill), fill_opacity=1,
                    stroke_width=0)
    return VGroup(box, t.move_to(box))


def label(words: str, size: float = 0.2, color="soft"):
    """Small spaced capitals in the mono face (DEBT · % OF THE ECONOMY): a heading over a chart, a caption."""
    font = L.get("mono") or L["body"]
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
