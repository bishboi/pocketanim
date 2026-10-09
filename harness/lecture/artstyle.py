"""Art styles: how a lecture's pictures are drawn, apart from the template that sets the whole film's look.

A template (pocket_lecture.THEMES: atlas, chalkboard, vox...) is the frame: the background, the fonts, the panel and
captions. An art style is the hand that draws what goes on the stage and the map: the sims, diagrams, charts, the
SVG drawings and figures, the map itself. The same chalkboard lecture can carry blueprint line drawings, or richly
shaded detailed ones.

Every picture is still ordinary vector shapes, so whatever the style draws plays on the phone as it renders in
Manim. A style works in two passes:

* paint(mob): each shape's colours, opacities and line widths, worked out from what the picture asked for. It is
  idempotent and cheap, so a live picture (a sim) is painted again after every step, and its motion still repeats
  exactly (a loop is stored once).
* decorate(mob): extras for a still picture, added as children of the shape they belong to, so they fade, move and
  are revealed with it: a sheen and rim on a detailed shape, chalk dust, pencil hatching, a neon glow, a
  watercolour wash. Moving pictures are never decorated: an extra drawn once would stay behind as the shape moved.

Text is never restyled: it belongs to the template.
"""

from __future__ import annotations

import math
import os

import numpy as np

ART_STYLES: dict[str, dict] = {
    "clean": dict(label="Clean", summary="Flat colours and crisp lines, as the template draws them."),
    "detailed": dict(label="Detailed", summary="Shaded, outlined shapes with highlights and rims; a relief map."),
    "blueprint": dict(label="Blueprint", summary="Fine technical line drawings on faint fills, construction marks."),
    "chalk": dict(label="Chalk", summary="Soft pastel chalk lines with a hand-drawn wobble and dust."),
    "sketch": dict(label="Sketch", summary="Pencil outlines with cross-hatched shading, as in a notebook."),
    "neon": dict(label="Neon", summary="Glowing lines of light over dark, translucent shapes."),
    "watercolour": dict(label="Watercolour", summary="Layered translucent washes with soft edges and thin ink lines."),
}

# The font each style writes its pictures' words in (labels, a node's name, a sim's readout); titles, the panel
# and the captions keep the template's. None: the template's own. A font not on this machine falls back to it too.
ART_FONTS = {
    "clean": None, "detailed": "Source Sans 3", "blueprint": "IBM Plex Mono", "chalk": "Cabin Sketch",
    "sketch": "Architects Daughter", "neon": "Quicksand", "watercolour": "Caveat",
}

# The art a template draws with when none is chosen.
TEMPLATE_ART = {
    "atlas": "detailed", "vox": "clean", "cardboard": "watercolour", "whiteboard": "sketch",
    "blueprint": "blueprint", "chalkboard": "chalk", "parchment": "sketch", "lab": "detailed", "cosmos": "neon",
}

ART = "clean"

# The most shapes one picture decorates, and the largest shape (in points) that is: a map's coastline or a
# drawing's thousand-point outline gains little from a sheen and costs the phone a lot.
MAX_DECORATED = 260
MAX_POINTS = 1600


def use(name: str | None, template: str | None = None) -> str:
    """Pick the art style; "auto" or nothing takes the template's own."""
    global ART
    name = (name or "auto").strip().lower()
    if name == "watercolor":
        name = "watercolour"
    if name in ("", "auto", "default"):
        name = TEMPLATE_ART.get(template or "", "clean")
    if name not in ART_STYLES:
        raise KeyError(f"unknown art style {name!r}; one of auto, {', '.join(ART_STYLES)}")
    ART = name
    return ART


def current() -> str:
    return ART


# ----------------------------------------------------------------------------------------------- colours


def _rgb(colour) -> np.ndarray:
    if colour is None:
        return np.zeros(3)
    if hasattr(colour, "to_rgb"):
        return np.array(colour.to_rgb(), float)
    text = str(colour).lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    return np.array([int(text[i:i + 2], 16) / 255 for i in (0, 2, 4)], float)


def _hex(rgb) -> str:
    r, g, b = (int(round(min(1.0, max(0.0, float(c))) * 255)) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(a, b, f: float) -> str:
    return _hex(_rgb(a) * (1 - f) + _rgb(b) * f)


def _lum(colour) -> float:
    r, g, b = _rgb(colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _bg() -> str:
    import pocket_lecture as pl

    return getattr(pl.P, "BG", "#000000")


def dark_board() -> bool:
    return _lum(_bg()) < 0.45


def ink() -> str:
    """The style's line colour against the board: light on a dark one, dark on a light one."""
    if ART == "blueprint":
        return "#EAF2FF" if dark_board() else "#0E3A66"
    if ART == "sketch":
        return "#ECECEC" if dark_board() else "#2B2B2B"
    return "#FFFFFF" if dark_board() else "#1B1B1B"


def _vivid(colour, amount: float = 0.25) -> str:
    """Brighter and more saturated: a colour as light."""
    rgb = _rgb(colour)
    top = rgb.max() or 1.0
    return _hex(np.clip(rgb / top * (1 - amount) + amount + (rgb - rgb.mean()) * 0.4, 0, 1))


# ----------------------------------------------------------------------------------------------- shapes


TEXT_CLASSES: tuple = ()


def _text_classes() -> tuple:
    global TEXT_CLASSES
    if not TEXT_CLASSES:
        from manim import MarkupText, MathTex, Paragraph, SingleStringMathTex, Tex, Text

        TEXT_CLASSES = (Text, MarkupText, Paragraph, SingleStringMathTex, MathTex, Tex)
    return TEXT_CLASSES


def _shapes(mob):
    """(shape, is_text) for every VMobject in mob with points of its own, decorations left out."""
    from manim import VMobject

    texts = _text_classes()
    out = []

    def walk(m, in_text):
        if getattr(m, "_art_deco", False):
            return
        in_text = in_text or isinstance(m, texts) or getattr(m, "_art_text", False)
        if isinstance(m, VMobject) and len(m.points):
            out.append((m, in_text))
        for sub in m.submobjects:
            walk(sub, in_text)

    walk(mob, False)
    return out


def _style_of(m):
    try:
        fill = m.get_fill_color().to_hex()
        stroke = m.get_stroke_color().to_hex()
    except Exception:  # noqa: BLE001 -- an odd mobject keeps its look
        return None
    return (fill.upper(), round(float(m.get_fill_opacity()), 4), stroke.upper(),
            round(float(m.get_stroke_opacity()), 4), round(float(m.get_stroke_width()), 3))


def _size(m) -> float:
    """How big the shape itself is: its own points, not its children (its extras among them)."""
    pts = m.points
    if not len(pts):
        return 0.0
    span = pts.max(axis=0) - pts.min(axis=0)
    return float(max(span[0], span[1]))


def _closed(m) -> bool:
    pts = m.points
    return len(pts) >= 4 and np.linalg.norm(pts[0] - pts[-1]) < 1e-3 * max(_size(m), 1e-3) + 1e-6


def _styled(base, closed: bool, size: float):
    """The style's (fill, fill opacity, stroke, stroke opacity, width) for a shape that asked for `base`."""
    fill, fo, stroke, so, w = base
    filled = fo > 0.04
    stroked = so > 0.04 and w > 0.3
    line = stroke if stroked else fill
    if ART == "detailed":
        if filled and not stroked and size > 0.12:
            return fill, fo, mix(fill, "#000000", 0.4), min(1.0, fo + 0.2), 2.2
        return fill, fo, stroke, so, w * 1.15 if stroked else w
    if ART == "blueprint":
        k = ink()
        if filled and size > 0.12:
            return mix(fill, k, 0.25), min(fo, 0.14), mix(line, k, 0.4), 1.0, min(max(w, 1.8), 3.0) if stroked else 2.0
        if filled:
            return mix(fill, k, 0.3), fo, stroke, so, w
        return fill, fo, mix(stroke, k, 0.4), so, min(max(w, 1.4), 3.2)
    if ART == "chalk":
        pastel = "#FFFFFF" if dark_board() else "#F7F3E8"
        if filled and size > 0.12:
            new_stroke = mix(line, pastel, 0.2)
            return mix(fill, pastel, 0.2), fo * 0.55, new_stroke, 0.92, max(w, 2.6) if stroked else 2.6
        return mix(fill, pastel, 0.2), fo, mix(stroke, pastel, 0.2), so * 0.92, w * 1.1
    if ART == "sketch":
        k = ink()
        if filled and size > 0.12:
            return fill, fo * 0.35, mix(line, k, 0.6), 1.0, min(max(w, 1.8), 3.2) if stroked else 2.0
        return fill, fo, mix(stroke, k, 0.6), so, min(max(w, 1.4), 3.2)
    if ART == "neon":
        if filled and size > 0.12:
            return _vivid(fill, 0.1), fo * 0.25, _vivid(line), 1.0, max(w * 1.2, 3.0) if stroked else 3.0
        return _vivid(fill, 0.1), fo, _vivid(stroke), so, max(w * 1.2, 2.5) if stroked else w
    if ART == "watercolour":
        if filled and size > 0.12:
            edge = mix(line if stroked else fill, "#000000" if not dark_board() else "#FFFFFF", 0.3)
            return fill, fo * 0.6, edge, 0.85, max(min(w * 0.6, 1.6), 1.0)
        return fill, fo, stroke, so, w * 0.8 if stroked else w
    return base


def paint(mob) -> None:
    """Colour every shape in mob as the art style draws it. Each of a shape's five values (fill, its opacity,
    stroke, its opacity, width) is worked out from what the picture asked for: a value the picture has not changed
    since the last paint keeps the value it asked for then, one it changed (a sim's step faded a dot) is what it
    asks for now. Painting never feeds on its own output, so a width is never widened twice."""
    if ART == "clean" or mob is None:
        return
    for m, is_text in _shapes(mob):
        if is_text:
            continue
        now = _style_of(m)
        painted = getattr(m, "_art_painted", None)
        if now is None or now == painted:
            continue
        if painted is None:
            base = now
        else:
            base = tuple(n if n != p else b for n, p, b in zip(now, painted, m._art_base))
        fill, fo, stroke, so, w = _styled(base, _closed(m), _size(m))
        m.set_fill(fill, opacity=fo, family=False)
        m.set_stroke(stroke, width=w, opacity=so, family=False)
        m._art_base = base
        m._art_painted = _style_of(m)


# ----------------------------------------------------------------------------------------------- decorations


def _noise(points: np.ndarray, amount: float, seed: float = 0.0) -> np.ndarray:
    """A hand's wobble that depends only on where a point is, so a curve's shared end points stay joined."""
    x, y = points[:, 0], points[:, 1]
    dx = np.sin(3.1 * x + 1.7 * y + seed) + 0.5 * np.sin(7.3 * y - 2.1 * x + seed * 2)
    dy = np.cos(2.3 * x - 2.9 * y + seed) + 0.5 * np.cos(6.1 * x + 3.7 * y + seed * 3)
    out = points.copy()
    out[:, 0] += amount * dx / 1.5
    out[:, 1] += amount * dy / 1.5
    return out


def _deco(m, child) -> None:
    child._art_deco = True
    for sub in child.get_family():
        sub._art_deco = True
    m.add(child)


def _outline_copy(m):
    from manim import VMobject

    c = VMobject()
    c.points = m.points.copy()
    return c


def _simple(m) -> bool:
    """A shape a sheen sits well on: one that nearly fills its box (a box, a circle, an ellipse), so a smaller copy
    of it moved up and to the left stays inside it. A triangle or a mountain's outline does not."""
    pts = m.points
    if len(pts) < 4 or not _closed(m) or len(pts) > 400:
        return False
    n = len(pts) // 4 * 4
    curves = pts[:n, :2].reshape(-1, 4, 2)
    middles = (curves[:, 0] + 3 * curves[:, 1] + 3 * curves[:, 2] + curves[:, 3]) / 8
    outline = np.stack([curves[:, 0], middles], axis=1).reshape(-1, 2)
    x, y = outline[:, 0], outline[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    span = pts.max(axis=0) - pts.min(axis=0)
    box = float(span[0] * span[1])
    return box > 1e-6 and area / box > 0.7

def _hatch_lines(m, spacing: float, angle: float = math.radians(40)):
    """Segments of parallel lines that lie inside the shape (even-odd), for pencil shading."""
    subpaths = m.get_subpaths() if hasattr(m, "get_subpaths") else [m.points]
    edges = []
    for sp in subpaths:
        anchors = np.asarray(sp)[::4, :2] if len(sp) >= 4 else np.asarray(sp)[:, :2]
        if len(sp) >= 4:
            anchors = np.vstack([anchors, np.asarray(sp)[-1, :2]])
        if len(anchors) < 3:
            continue
        edges.append(np.stack([anchors[:-1], anchors[1:]], axis=1))
    if not edges:
        return []
    seg = np.concatenate(edges)
    c, s = math.cos(angle), math.sin(angle)
    rot = np.array([[c, s], [-s, c]])               # into the frame where hatch lines are horizontal
    back = rot.T
    a = seg[:, 0] @ rot.T
    b = seg[:, 1] @ rot.T
    lo, hi = min(a[:, 1].min(), b[:, 1].min()), max(a[:, 1].max(), b[:, 1].max())
    out = []
    y = lo + spacing / 2
    while y < hi and len(out) < 80:
        crosses = (a[:, 1] - y) * (b[:, 1] - y) < 0
        if crosses.any():
            t = (y - a[crosses, 1]) / (b[crosses, 1] - a[crosses, 1])
            xs = np.sort(a[crosses, 0] + t * (b[crosses, 0] - a[crosses, 0]))
            for x0, x1 in zip(xs[0::2], xs[1::2]):
                if x1 - x0 > spacing * 0.4:
                    p0 = np.array([x0 + spacing * 0.15, y]) @ back.T
                    p1 = np.array([x1 - spacing * 0.15, y]) @ back.T
                    out.append((p0, p1))
        y += spacing
    return out


def _about(points: np.ndarray, scale: float, offset) -> np.ndarray:
    """Points scaled about their own centre and shifted."""
    if not len(points):
        return points
    centre = (points.min(axis=0) + points.max(axis=0)) / 2
    return (points - centre) * scale + centre + np.asarray(offset, float)


def _shape_part(points: np.ndarray, scale, offset) -> np.ndarray:
    """Points scaled about their centre by (sx, sy) and moved by offset times the shape's own width and height."""
    if not len(points):
        return points
    lo, hi = points.min(axis=0), points.max(axis=0)
    centre, span = (lo + hi) / 2, hi - lo
    out = points - centre
    out[:, 0] *= scale[0]
    out[:, 1] *= scale[1]
    out[:, 0] += centre[0] + offset[0] * span[0]
    out[:, 1] += centre[1] + offset[1] * span[1]
    return out


def _sheen(points: np.ndarray) -> np.ndarray:
    """Where light catches a shape: a round spot up and to the left on a roundish one, a strip down the left of a
    long bar (as on a cylinder), along the top of a wide one."""
    if not len(points):
        return points
    span = points.max(axis=0) - points.min(axis=0)
    w, h = float(span[0]), float(span[1])
    if h > 1.6 * w:
        return _shape_part(points, (0.22, 0.86), (-0.26, 0.0))
    if w > 1.6 * h:
        return _shape_part(points, (0.88, 0.24), (0.0, 0.26))
    return _shape_part(points, (0.45, 0.45), (-0.16, 0.16))


def _look(m):
    """(fill, fill opacity, stroke, stroke opacity, width, size, closed) as the shape is now."""
    return (m.get_fill_color().to_hex(), float(m.get_fill_opacity()), m.get_stroke_color().to_hex(),
            float(m.get_stroke_opacity()), float(m.get_stroke_width()), _size(m), _closed(m))


def _recipes(m, live: bool) -> list:
    """The extras a shape gets in this art style, as makers: maker(parent) -> (points, fill, fill opacity, stroke,
    stroke opacity, width), worked out from the parent as it is now. A moving shape keeps the ones whose points
    follow its own one for one; hatching (a count of lines that changes with the shape) is for still ones."""
    fill, fo, stroke, so, w, size, closed = _look(m)
    filled = fo > 0.04 and size > 0.15
    stroked = so > 0.04 and w > 0.5
    out = []

    def add(maker):
        out.append(maker)

    if ART == "detailed":
        if filled and closed and _simple(m):
            add(lambda p: (_shape_part(p.points, (0.92, 0.92), (0.04, -0.05)),
                           mix(p.get_fill_color().to_hex(), "#000000", 0.35), min(0.35, p.get_fill_opacity() * 0.45),
                           "#000000", 0.0, 0.0))
            add(lambda p: (_sheen(p.points), mix(p.get_fill_color().to_hex(), "#FFFFFF", 0.7),
                           min(0.35, p.get_fill_opacity() * 0.45), "#000000", 0.0, 0.0))
        if filled and closed:
            add(lambda p: (_about(p.points, max(0.0, 1 - 0.08 / max(_size(p), 0.1)), [0, 0, 0]),
                           "#000000", 0.0, mix(p.get_fill_color().to_hex(), "#FFFFFF", 0.5),
                           0.45 * min(1.0, p.get_fill_opacity() * 1.5), 1.1))
        elif stroked and w >= 2.0 and not closed:
            add(lambda p: (p.points.copy(), "#000000", 0.0, mix(p.get_stroke_color().to_hex(), "#FFFFFF", 0.55),
                           0.55 * p.get_stroke_opacity(), max(0.8, p.get_stroke_width() * 0.35)))
    elif ART == "chalk":
        if stroked and size > 0.2:
            add(lambda p: (_noise(_about(p.points, 1.0, [0.012, -0.009, 0]), 0.01, seed=1.7), "#000000", 0.0,
                           p.get_stroke_color().to_hex(), p.get_stroke_opacity() * 0.35,
                           max(p.get_stroke_width() * 0.5, 0.8)))
        if filled and closed and size > 0.3 and not live:
            add(("hatch", 0.075, math.radians(62), 0.32, 1.4, "fill", 0.006))
    elif ART == "sketch":
        if filled and closed and size > 0.3 and not live:
            add(("hatch", max(0.09, size / 22), math.radians(40), 0.6, 1.0, "ink", 0.0))
            if size > 1.2:
                add(("hatch", max(0.12, size / 16), math.radians(-35), 0.35, 0.8, "ink", 0.0))
    elif ART == "neon":
        if stroked or (filled and size > 0.12):
            for width, opacity in ((2.6, 0.16), (5.0, 0.07)):
                add(lambda p, width=width, opacity=opacity: (
                    p.points.copy(), "#000000", 0.0, p.get_stroke_color().to_hex(),
                    opacity * p.get_stroke_opacity(), p.get_stroke_width() * width))
    elif ART == "watercolour":
        if filled and closed:
            for scale, shift, seed in ((1.03, [0.02, -0.015, 0], 3.0), (0.94, [-0.02, 0.02, 0], 5.0)):
                add(lambda p, scale=scale, shift=shift, seed=seed: (
                    _noise(_about(p.points, scale, shift), 0.02 * min(_size(p), 1.5), seed=seed),
                    p.get_fill_color().to_hex(), min(0.18, p.get_fill_opacity() * 0.35), "#000000", 0.0, 0.0))
    elif ART == "blueprint":
        from manim import Circle

        if filled and size > 0.5 and isinstance(m, Circle) and not live:
            add(("cross",))
    return out


def _still_extra(m, recipe):
    """A hatching or a pair of centre lines, drawn once on a still shape."""
    from manim import VMobject

    fill, fo, stroke, so, w, size, closed = _look(m)
    child = VMobject()
    if recipe[0] == "hatch":
        _, spacing, angle, opacity, width, colour, wobble = recipe
        lines = _hatch_lines(m, spacing, angle)
        if not lines:
            return None
        for p0, p1 in lines:
            child.start_new_path(np.array([p0[0], p0[1], 0.0]))
            child.add_line_to(np.array([p1[0], p1[1], 0.0]))
        if wobble:
            child.points = _inside(_noise(child.points, wobble, seed=2.3), m)
        tone = mix(fill, "#FFFFFF" if dark_board() else "#000000", 0.15) if colour == "fill" else mix(fill, ink(), 0.35)
        child.set_fill(opacity=0).set_stroke(tone, width=width, opacity=opacity * max(fo, 0.5))
        return child
    if recipe[0] == "cross":
        centre, r = m.get_center(), size / 2
        for d in (np.array([1.0, 0, 0]), np.array([0, 1.0, 0])):
            child.start_new_path(centre - d * r)
            child.add_line_to(centre + d * r)
        child.set_fill(opacity=0).set_stroke(ink(), width=0.8, opacity=0.45)
        return child
    return None


def _inside(points: np.ndarray, parent) -> np.ndarray:
    """Points kept within the parent's own box. An extra is a child of its shape, and Manim measures a shape with
    its children: one that stuck out moved the shape's centre, so a step that put the shape somewhere (move_to)
    put it a little off, and a little differently each frame."""
    own = parent.points
    if not len(own) or not len(points):
        return points
    lo, hi = own.min(axis=0), own.max(axis=0)
    return np.clip(points, lo, hi)


def _apply(child, made, parent=None) -> None:
    points, fill, fo, stroke, so, w = made
    points = np.asarray(points, float)
    child.points = _inside(points, parent) if parent is not None else points
    child.set_fill(fill, opacity=float(fo), family=False)
    child.set_stroke(stroke, width=float(w), opacity=float(so), family=False)


def _decorate_shape(m, live: bool) -> None:
    from manim import VMobject

    if not live and ART in ("chalk", "sketch") and not getattr(m, "_art_wobbled", False):
        size = _size(m)
        m.points = _noise(m.points, min(0.012 if ART == "chalk" else 0.008, 0.02 * size + 0.003))
        m._art_wobbled = True
    children = []
    for recipe in _recipes(m, live):
        if callable(recipe):
            child = VMobject()
            _apply(child, recipe(m), m)
            child._art_make = recipe
        else:
            child = _still_extra(m, recipe)
            if child is None:
                continue
        _deco(m, child)
        children.append(child)
    m._art_decos = children


def _refresh(m) -> None:
    """A moving shape's extras, worked out again from where and how it is now."""
    for child in getattr(m, "_art_decos", ()):
        make = getattr(child, "_art_make", None)
        if make is None:
            continue
        _apply(child, make(m), m)
        if child not in m.submobjects:
            m.add(child)


def decorate(mob, skip=None, live: bool = False) -> None:
    """The art style's extras (see the module's note). `skip`: ids of shapes to leave bare. Live shapes get only
    the extras that follow them; others get everything."""
    if ART == "clean" or mob is None:
        return
    done = 0
    for m, is_text in _shapes(mob):
        if is_text or getattr(m, "_art_decorated", False):
            continue
        if getattr(m, "_art_live", False) != live:
            continue
        if skip and id(m) in skip:
            continue
        if len(m.points) > MAX_POINTS or done >= MAX_DECORATED:
            continue
        m._art_decorated = True
        try:
            _decorate_shape(m, live)
        except Exception:  # noqa: BLE001 -- an extra that cannot be drawn is left out
            continue
        done += 1


def dress(mob, skip=None) -> None:
    """Paint a picture and decorate its parts: the still ones with everything, the moving ones with what follows."""
    if ART == "clean" or mob is None:
        return
    paint(mob)
    decorate(mob, skip)
    decorate(mob, skip, live=True)


def mark_live(mob, scope=None) -> None:
    """A picture whose parts move: painted every frame, given only extras that follow it."""
    for m in mob.get_family():
        if not getattr(m, "_art_deco", False):
            m._art_live = True
    if scope is not None:
        mob._art_scope = scope


def live_paint(mob) -> None:
    """After a live picture's step: its colours, and its extras moved and coloured with it."""
    if ART == "clean":
        return
    scope = getattr(mob, "_art_scope", mob)
    paint(scope)
    decorate(scope, live=True)
    for m, is_text in _shapes(scope):
        if not is_text and getattr(m, "_art_decos", None):
            _refresh(m)


# ----------------------------------------------------------------------------------------------- maps


def map_jitter(default: float) -> float:
    return {"chalk": 0.012, "sketch": 0.007, "watercolour": 0.004}.get(ART, default)


def dress_map(neighbours, lines, outline, focus_poly=None) -> None:
    """The base map in the art style: line-only for a blueprint, glowing coasts for neon, a relief-like double
    coastline when detailed, hatched neighbours in a sketch, a wash of land in watercolour."""
    from manim import VMobject

    if ART == "clean":
        return
    k = ink()
    if ART == "blueprint":
        for m in neighbours.get_family():
            if len(m.points):
                m.set_fill(mix(m.get_fill_color().to_hex(), k, 0.2), opacity=0.05, family=False)
                m.set_stroke(k, width=0.8, opacity=0.5, family=False)
        for m in lines.get_family():
            if len(m.points):
                m.set_stroke(k, width=0.7, opacity=0.45, family=False)
        for m in outline.get_family():
            if len(m.points):
                m.set_stroke(k, width=2.0, opacity=1.0, family=False)
                m.set_fill(k, opacity=0.06, family=False)
        return
    if ART == "detailed":
        for m in list(outline.get_family()):
            if len(m.points) and not getattr(m, "_art_deco", False):
                halo = _outline_copy(m)
                halo.set_fill(opacity=0).set_stroke(mix(m.get_stroke_color().to_hex(), "#5AB4F0", 0.6),
                                                     width=8, opacity=0.18)
                _deco(m, halo)
                inner = _outline_copy(m)
                inner.set_fill(opacity=0).set_stroke(m.get_stroke_color().to_hex(), width=0.8, opacity=0.5)
                inner.scale(0.985)
                _deco(m, inner)
        return
    if ART == "neon":
        for m in list(outline.get_family()) + list(lines.get_family()):
            if len(m.points) and not getattr(m, "_art_deco", False):
                colour = _vivid(m.get_stroke_color().to_hex())
                m.set_stroke(colour, family=False)
                for width, opacity in ((7, 0.14), (14, 0.06)):
                    glow = _outline_copy(m)
                    glow.set_fill(opacity=0).set_stroke(colour, width=width, opacity=opacity)
                    _deco(m, glow)
        return
    if ART == "sketch":
        hatched = 0
        for m in neighbours.get_family():
            if len(m.points) and not getattr(m, "_art_deco", False) and hatched < 40 and _size(m) > 0.3:
                m.set_fill(opacity=min(float(m.get_fill_opacity()), 0.25), family=False)
                lines_ = _hatch_lines(m, spacing=0.14)
                if lines_:
                    hatch = VMobject()
                    for p0, p1 in lines_:
                        hatch.start_new_path(np.array([p0[0], p0[1], 0.0]))
                        hatch.add_line_to(np.array([p1[0], p1[1], 0.0]))
                    hatch.set_fill(opacity=0).set_stroke(k, width=0.7, opacity=0.35)
                    _deco(m, hatch)
                    hatched += 1
        for m in outline.get_family():
            if len(m.points):
                m.set_stroke(k, family=False)
        return
    if ART == "chalk":
        for m in outline.get_family():
            if len(m.points) and not getattr(m, "_art_deco", False):
                dust = _outline_copy(m).shift([0.015, -0.01, 0])
                dust.set_fill(opacity=0).set_stroke(m.get_stroke_color().to_hex(), width=1.0, opacity=0.35)
                _deco(m, dust)
        return
    if ART == "watercolour":
        for m in list(outline.get_family()):
            if len(m.points) and not getattr(m, "_art_deco", False):
                for scale, alpha in ((1.0, 0.16), (0.97, 0.12)):
                    wash = _outline_copy(m).scale(scale)
                    wash.points = _noise(wash.points, 0.03, seed=scale * 7)
                    wash.set_fill(m.get_stroke_color().to_hex(), opacity=alpha).set_stroke(width=0)
                    _deco(m, wash)
        return


def stage_marks(box):
    """Marks the art style puts round the stage: a blueprint's corner registration ticks. Empty for the others."""
    from manim import VGroup, VMobject

    marks = VGroup()
    if ART != "blueprint":
        return marks
    cx, cy, w, h = box
    k = ink()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = cx + sx * (w / 2 + 0.1), cy + sy * (h / 2 + 0.1)
            corner = VMobject().set_points_as_corners([[x - sx * 0.35, y, 0], [x, y, 0], [x, y - sy * 0.35, 0]])
            corner.set_stroke(k, width=1.2, opacity=0.55).set_fill(opacity=0)
            marks.add(corner)
    return marks


ENV = "LECTURE_ART"


def from_env(template: str | None) -> str:
    try:
        return use(os.environ.get(ENV), template)
    except KeyError:
        return use("auto", template)


# ----------------------------------------------------------------------------------------------- picture words


_DRAWING = [0]
_INSTALLED: set = set()
_FETCHED: list = []


def _installed() -> set:
    if not _INSTALLED:
        import subprocess

        try:
            out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=20).stdout
        except Exception:  # noqa: BLE001 -- no fontconfig: every style writes in the template's fonts
            out = ""
        for line in out.splitlines():
            for name in line.split(","):
                _INSTALLED.add(name.strip().lower())
        _INSTALLED.add("")
    return _INSTALLED


def font() -> str | None:
    """The art style's font for words in a picture, when one is being drawn and the font is here; else None."""
    if not _DRAWING[0]:
        return None
    name = ART_FONTS.get(ART)
    if not name:
        return None
    if name.lower() not in _installed() and not _FETCHED:
        # Not on this machine yet: the styles' fonts are fetched once (offline, the template's font is used).
        _FETCHED.append(True)
        try:
            import pocket_lecture

            pocket_lecture.setup_fonts()
        except Exception:  # noqa: BLE001
            pass
        _INSTALLED.clear()
    return name if name.lower() in _installed() else None


class drawing:
    """While a picture is being built (or a live one stepped), its words are written in the art style's font.
    Usable as `with drawing():` or as a decorator on a method that builds a picture."""

    def __init__(self, fn=None):
        self.fn = fn
        if fn is not None:
            import functools

            functools.update_wrapper(self, fn)

    def __enter__(self):
        _DRAWING[0] += 1
        return self

    def __exit__(self, *exc):
        _DRAWING[0] -= 1
        return False

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        import functools

        return functools.partial(self.__call__, obj)

    def __call__(self, *args, **kwargs):
        with drawing():
            return self.fn(*args, **kwargs)


def drawn_by(cls, names) -> None:
    """Make these methods of cls build their pictures' words in the art style's font."""
    for name in names:
        fn = cls.__dict__.get(name)
        if fn is not None and not isinstance(fn, drawing):
            setattr(cls, name, drawing(fn))
