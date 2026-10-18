"""The motion engine's primitives: words, cards and marks in the look's design, and the motions that bring them on,
point at them and take them away -- each one a play the phones' players have (FadeIn with shift, scale and rate,
Create, Write, `.animate` moves and scales, lagged groups), or, where nothing they have will do (a number counting,
a spring, a shake), a play marked to be baked into a small clip by the exporter (`_panim_bake`).

Everything here reads the look (motion.M, set by MotionLecture) at call time. Every animation carries `panim_run`,
the seconds it wants: the beat plays it for that long when it can (motion.MotionLecture._on_words).
"""

from __future__ import annotations

import math
import re

import numpy as np
from manim import (BOLD, DOWN, LEFT, ORIGIN, RIGHT, UP, Animation, AnimationGroup, Circle, Create, Dot,
                   FadeIn, FadeOut, Group, ImageMobject, LaggedStart, Line, Rectangle, RoundedRectangle, Text,
                   VGroup, VMobject, Write, linear, there_and_back)
from manim.utils.rate_functions import (ease_in_cubic, ease_out_back, ease_out_cubic, ease_out_expo, rush_from,
                                        rush_into, smooth)

import pocket_lecture as pl

# The look in use (motion_looks.motion_of): set by MotionLecture as the scene starts.
M: dict = {}


def t(name: str) -> float:
    return float((M.get("t") or {}).get(name, {"fast": 0.35, "base": 0.6, "slow": 1.0, "stagger": 0.12,
                                                 "hold": 0.25}[name]))


def col(name: str) -> str:
    """A look colour: accent, second, stamp, good, bad, card, card_ink, card_stroke, accent_ink. A classic style
    (no look of its own) takes them from its palette."""
    if M.get("classic"):
        P = pl.P
        return {"accent": P.GOLD, "second": P.RIVER, "stamp": P.ROSE, "good": P.GREEN, "bad": P.ROSE,
                "card": pl.TH.get("nb_fill", P.BG), "card_ink": P.CREAM, "card_stroke": pl.TH.get("nb_stroke", P.MUTED),
                "accent_ink": P.BG}.get(name, P.SAND)
    return M.get(name) or pl.P.SAND


def font(kind: str) -> str:
    """The look's font for a kind of words: kicker (small capitals over a figure), head, number, body."""
    if M.get("classic"):
        return {"kicker": pl.TH["sans"], "head": pl.TH["serif"], "number": pl.TH["serif"]}.get(kind, pl.TH["sans"])
    return M.get(f"{kind}_font") or pl.TH["sans"]


def timed(anim, run: float, sfx: str | None = None):
    """An animation marked with the seconds it wants (and the sound it makes)."""
    if anim is None:
        return None
    anim.panim_run = float(run)
    # Its own length too: inside a group, each part takes its share by its length.
    try:
        anim.run_time = float(run)
    except AttributeError:
        pass
    if sfx:
        anim.panim_sfx = sfx
    return anim


def baked(anim):
    """A play the players have no verbs for (a counter, a spring, a shake): baked into a clip by the exporter."""
    anim._panim_bake = True
    return anim


# ---------------------------------------------------------------- words --------------------------------------------

def spaced(text: str) -> str:
    """Capitals with air between the letters, for a kicker: "DEBT · % OF THE ECONOMY"."""
    return " ".join(str(text).upper()) if len(str(text)) <= 14 else str(text).upper()


def kicker(text: str, size: float = 17, color: str | None = None):
    """The small mono line over a figure or a chart ("A GOVERNMENT BOND")."""
    return pl.T(str(text).upper(), size, color or pl.P.MUTED, font=font("kicker"), weight=BOLD)


def head(text: str, size: float = 40, color: str | None = None, upper: bool | None = None):
    words = str(text)
    if upper if upper is not None else pl.TH.get("upper"):
        words = words.upper()
    return pl.T(words, size, color or pl.P.TITLE, font=font("head"), weight=BOLD)


def body(text: str, size: float = 22, color: str | None = None, width: int = 34):
    return pl.T(pl.wrap(str(text), width), size, color or pl.P.CREAM, font=font("body"), line_spacing=0.9)


def number(text: str, size: float = 64, color: str | None = None):
    return pl.T(str(text), size, color or pl.P.TITLE, font=font("number"), weight=BOLD)


NUMBER = re.compile(r"^(?P<pre>[^\d\-+.]*?)(?P<sign>[+\-−]?)(?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)(?P<post>.*)$")


def parse_number(text: str):
    """A figure as (prefix, value, decimals, grouped, suffix): "$14.06B" -> ("$", 14.06, 2, False, "B");
    "2,525 km" -> ("", 2525, 0, True, " km"). None when it is not a figure."""
    m = NUMBER.match(str(text).strip())
    if not m:
        return None
    raw = m.group("num")
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    sign = m.group("sign").replace("−", "-")
    if sign == "-":
        value = -value
    return (m.group("pre"), value, decimals, "," in raw, m.group("post"), sign == "+")


def format_number(parsed, value: float) -> str:
    pre, _, decimals, grouped, post, plus = parsed
    body_ = f"{abs(value):,.{decimals}f}" if grouped else f"{abs(value):.{decimals}f}"
    sign = "-" if value < 0 else ("+" if plus else "")
    return f"{pre}{sign}{body_}{post}"


class CountUp(Animation):
    """A figure counting up to its value (from `start`), the words rebuilt each frame, easing out as it lands.
    Baked: the players have no verb for words that change."""

    def __init__(self, holder, text: str, make, start: float = 0.0, **kw):
        self._parsed = parse_number(text)
        self._make = make
        self._text = text
        self._start = start
        super().__init__(holder, **kw)
        self._panim_bake = True

    def begin(self):
        self._centre = self.mobject.get_center().copy()
        self._anchor = getattr(self.mobject, "_count_left", None)
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        if self._parsed is None:
            return
        alpha = min(max(alpha, 0.0), 1.0)
        a = ease_out_cubic(alpha)
        value = self._start + (self._parsed[1] - self._start) * a
        words = self._text if alpha >= 1 else format_number(self._parsed, value)
        made = self._make(words)
        # Kept left-aligned where the figure was laid out (a number that grows does not jitter about its middle),
        # or about its centre.
        if self._anchor is not None:
            made.move_to(self._anchor, aligned_edge=LEFT)
        else:
            made.move_to(self._centre)
        # It comes on as it starts counting: invisible before (a lagged group starts every part at once), popping
        # up from small over its first fifth.
        if alpha <= 0:
            made.set_opacity(0)
        elif alpha < 0.2:
            k = ease_out_back(alpha / 0.2)
            made.scale(max(0.05, 0.55 + 0.45 * k))
            made.set_opacity(min(1.0, alpha / 0.12))
        self.mobject.become(made)


def counter(text: str, make, start: float = 0.0):
    """The figure as it ends (lay it out where it goes), with `.count_anim(run)`: the play that counts it up from
    `start`, or None when the words hold no number (they simply come on)."""
    final = make(text)

    def anim(run: float | None = None, centre: bool = False):
        if parse_number(text) is None:
            return None
        final._count_left = None if centre else final.get_left().copy()
        return timed(baked(CountUp(final, text, make, start=start, rate_func=linear)), run or t("slow"), "count")

    final.count_anim = anim
    return final


# ---------------------------------------------------------------- cards and marks -----------------------------------

def shadow_of(shape, offset=None, opacity=None):
    """A soft shadow under a card: three copies of its outline, each a little larger and fainter, offset down."""
    dx, dy, op = M.get("shadow") or (0.05, -0.08, 0.25)
    if offset is not None:
        dx, dy = offset
    if opacity is not None:
        op = opacity
    layers = VGroup()
    for k, grow in enumerate((0.0, 0.05, 0.11)):
        s = shape.copy().set_stroke(width=0).set_fill("#000000", opacity=op * (0.5, 0.3, 0.18)[k])
        if shape.width > 0.01:
            s.scale((shape.width + grow) / shape.width)
        s.shift(RIGHT * dx + UP * dy)
        layers.add(s)
    return pl._flat(layers)


def card(width: float, height: float, fill: str | None = None, stroke: str | None = None, radius: float | None = None,
         shadow: bool = True, stroke_width: float = 1.4):
    """A card in the look: its colour, a hairline edge, round corners, a soft shadow. A VGroup (shadow, face);
    `.face` is the card."""
    radius = M.get("radius", 0.08) if radius is None else radius
    face = RoundedRectangle(corner_radius=min(radius, height / 2, width / 2), width=width, height=height,
                            fill_color=fill or col("card"), fill_opacity=1, stroke_color=stroke or col("card_stroke"),
                            stroke_width=stroke_width)
    group = VGroup()
    if shadow:
        group.add(shadow_of(face))
    group.add(face)
    group.face = face
    pl._flat(group)
    return group


def chip(text: str, fill: str | None = None, ink: str | None = None, size: float = 18, pad: float = 0.16):
    """A label on a solid block of the accent ("8% ABROAD")."""
    words = pl.T(str(text).upper() if pl.TH.get("upper") else str(text), size, ink or col("accent_ink"),
                 font=font("head"), weight=BOLD)
    back = Rectangle(width=words.width + 2 * pad, height=words.height + 1.3 * pad, stroke_width=0,
                     fill_color=fill or col("accent"), fill_opacity=1)
    words.move_to(back)
    return pl._flat(VGroup(back, words))


def stamp(text: str, color: str | None = None, angle: float = -12, size: float = 34):
    """A rubber stamp: the words in capitals in a double-ruled box, in the stamp colour, turned a little."""
    colour = color or col("stamp")
    words = pl.T(str(text).upper(), size, colour, font=font("head"), weight=BOLD)
    inner = RoundedRectangle(corner_radius=0.08, width=words.width + 0.5, height=words.height + 0.4,
                             stroke_color=colour, stroke_width=4, fill_opacity=0)
    outer = RoundedRectangle(corner_radius=0.12, width=words.width + 0.72, height=words.height + 0.62,
                             stroke_color=colour, stroke_width=2.2, fill_opacity=0)
    words.move_to(inner)
    group = pl._flat(VGroup(outer, inner, words))
    group.rotate(angle * math.pi / 180)
    return group


def check_mark(size: float = 0.42, color: str | None = None):
    pts = [np.array([-0.5, 0.0, 0]), np.array([-0.15, -0.35, 0]), np.array([0.55, 0.45, 0])]
    mark = VMobject(stroke_color=color or col("good"), stroke_width=9).set_points_as_corners([p * size for p in pts])
    return pl._flat(mark)


def cross_mark(size: float = 0.4, color: str | None = None):
    c = color or col("bad")
    a = Line(np.array([-0.5, -0.5, 0]) * size, np.array([0.5, 0.5, 0]) * size, stroke_color=c, stroke_width=9)
    b = Line(np.array([-0.5, 0.5, 0]) * size, np.array([0.5, -0.5, 0]) * size, stroke_color=c, stroke_width=9)
    return pl._flat(VGroup(a, b))


def arrow_between(a, b, color: str | None = None, curve: float = 0.0, width: float = 5):
    """A drawn arrow from one thing to the next, its shaft drawn on (Create) and its head popping at the end."""
    from manim import ArcBetweenPoints, Triangle

    start, end = a, b
    colour = color or pl.P.MUTED
    if abs(curve) > 1e-3:
        shaft = ArcBetweenPoints(start, end, angle=curve, stroke_color=colour, stroke_width=width)
    else:
        shaft = Line(start, end, stroke_color=colour, stroke_width=width)
    direction = shaft.point_from_proportion(1.0) - shaft.point_from_proportion(0.96)
    angle = math.atan2(direction[1], direction[0])
    tip = Triangle(fill_color=colour, fill_opacity=1, stroke_width=0).scale(0.11)
    tip.rotate(angle - math.pi / 2).move_to(end)
    return pl._flat(VGroup(shaft, tip))


def hand_ellipse(mob, color: str | None = None, width: float = 5, pad: float = 0.22):
    """A ring drawn round something by hand: an ellipse a little wobbly, its end running past its start."""
    w, h = mob.width / 2 + pad, mob.height / 2 + pad * 0.8
    c = mob.get_center()
    rng = np.random.default_rng(int(abs(w * 1000 + h * 100)) % 997)
    pts = []
    for k in range(40):
        a = 2 * math.pi * (k / 36) + 0.5
        r = 1 + 0.035 * math.sin(3 * a + rng.uniform(0, 1)) + 0.02 * (k / 40)
        pts.append(c + np.array([w * r * math.cos(a), h * r * math.sin(a), 0]))
    ring = VMobject(stroke_color=color or col("stamp"), stroke_width=width).set_points_smoothly(pts)
    return pl._flat(ring)


def underline(mob, color: str | None = None, width: float = 6):
    """A marker's stroke under some words, a little curved."""
    left, right = mob.get_corner(DOWN + LEFT), mob.get_corner(DOWN + RIGHT)
    y = left[1] - 0.08
    pts = [np.array([left[0] + (right[0] - left[0]) * s, y + 0.035 * math.sin(s * math.pi) - 0.02 * s, 0])
           for s in np.linspace(0, 1, 9)]
    line = VMobject(stroke_color=color or col("accent"), stroke_width=width).set_points_smoothly(pts)
    return pl._flat(line)


def highlighter(mob, color: str | None = None):
    """A highlighter's stroke behind some words (drawn left to right with Create): a thick translucent line as tall
    as the words. Put it under them (z) and Create it."""
    h = mob.height * 1.05
    px = h * pl.config.pixel_height / pl.config.frame_height
    a = mob.get_left() + LEFT * 0.06
    b = mob.get_right() + RIGHT * 0.06
    tone = color or (pl.TH.get("highlight") if not M.get("classic") or pl.TH.get("highlight") else None) or col("accent")
    line = Line(a, b, stroke_color=tone, stroke_width=px * 1.02, stroke_opacity=0.85)
    line._z_offset = -0.5          # under the words it marks (motion.MotionLecture puts it there)
    return pl._flat(line)


def glow(mob, color: str | None = None, layers: int = 3):
    """A glow round a shape: its outline copied a few times, wider and fainter each time."""
    colour = color or col("accent")
    out = VGroup()
    for k in range(layers):
        g = mob.copy().set_fill(opacity=0).set_stroke(colour, width=6 + 9 * k, opacity=0.22 / (k + 1))
        out.add(g)
    return pl._flat(out)


# ---------------------------------------------------------------- entrances ----------------------------------------
SIDE = {"left": LEFT, "right": RIGHT, "up": UP, "down": DOWN, "top": UP, "bottom": DOWN}


def enter(mob, how: str | None = None, side: str | None = None, run: float | None = None):
    """How something comes on, by name (the look's own when None):
    pop     grows from small with an overshoot              rise    comes up a little as it fades in
    drop    falls in from above with an overshoot           slide   sweeps in from a side, fast then slow
    zoom    comes from large, settling                      write   written (words) or drawn (lines)
    fade    simply fades in                                 flip    turns in, as a card turned over
    """
    how = how or M.get("enter", "pop")
    run = run if run is not None else t("base")
    images = any(isinstance(m, ImageMobject) for m in mob.get_family())
    if how == "write":
        if images or not isinstance(mob, VMobject):
            how = "rise"
        else:
            return timed(Write(mob) if _wordy(mob) else Create(mob, rate_func=rush_from), max(run, t("slow")), "draw")
    if how == "pop":
        return timed(FadeIn(mob, scale=0.55, rate_func=ease_out_back), run, "pop")
    if how == "drop":
        return timed(FadeIn(mob, shift=DOWN * 0.7, rate_func=ease_out_back), run, "pop")
    if how == "slide":
        v = SIDE.get(str(side or "right").lower(), RIGHT)
        return timed(FadeIn(mob, shift=-v * 1.6, rate_func=ease_out_expo), run, "swish")
    if how == "zoom":
        return timed(FadeIn(mob, scale=1.35, rate_func=ease_out_cubic), run, "whoosh")
    if how == "flip":
        return timed(FadeIn(mob, scale=0.85, shift=UP * 0.25, rate_func=ease_out_back), run, "pop")
    if how == "fade":
        return timed(FadeIn(mob, rate_func=smooth), run)
    return timed(FadeIn(mob, shift=UP * 0.35, rate_func=ease_out_cubic), run, "pop")


def _wordy(mob) -> bool:
    return any(isinstance(m, Text) for m in mob.get_family())


def leave(mob, how: str | None = None, side: str | None = None, run: float | None = None):
    how = how or M.get("exit", "fade")
    run = run if run is not None else t("fast")
    if how == "slide":
        v = SIDE.get(str(side or "left").lower(), LEFT)
        return timed(FadeOut(mob, shift=v * 1.6, rate_func=rush_into), run, "swish")
    if how == "shrink":
        return timed(FadeOut(mob, scale=0.7, rate_func=rush_into), run)
    if how == "drop":
        return timed(FadeOut(mob, shift=DOWN * 0.8, rate_func=ease_in_cubic), run)
    return timed(FadeOut(mob, rate_func=rush_into), run)


def stagger(anims: list, run: float | None = None, lag: float | None = None):
    """Things one after another, each starting before the last has landed (overlapping action)."""
    anims = [a for a in anims if a is not None]
    if not anims:
        return None
    if len(anims) == 1:
        return anims[0]
    lag = lag if lag is not None else max(0.08, min(0.6, t("stagger") / max(t("base"), 0.1) * 2.2))
    each = max(float(getattr(a, "panim_run", t("base"))) for a in anims)
    total = run if run is not None else each * (1 + lag * (len(anims) - 1))
    group = LaggedStart(*anims, lag_ratio=lag)
    sounds = [getattr(a, "panim_sfx", None) for a in anims]
    return timed(group, total, next((s for s in sounds if s), None))


def together(anims: list, run: float | None = None):
    anims = [a for a in anims if a is not None]
    if not anims:
        return None
    if len(anims) == 1 and run is None:
        return anims[0]
    run = run if run is not None else max(float(getattr(a, "panim_run", t("base"))) for a in anims)
    sounds = [getattr(a, "panim_sfx", None) for a in anims]
    return timed(AnimationGroup(*anims), run, next((s for s in sounds if s), None))


def chain(anims: list, run: float | None = None):
    """One after another: each starts as the one before lands."""
    anims = [a for a in anims if a is not None]
    if not anims:
        return None
    if len(anims) == 1:
        return anims[0]
    total = run if run is not None else sum(float(getattr(a, "panim_run", t("base"))) for a in anims)
    sounds = [getattr(a, "panim_sfx", None) for a in anims]
    return timed(AnimationGroup(*anims, lag_ratio=1.0), total, next((s for s in sounds if s), None))


# ---------------------------------------------------------------- emphasis -----------------------------------------

def pulse(mob, k: float = 1.12, run: float | None = None):
    """A beat of attention: up and back."""
    anim = mob.animate(rate_func=there_and_back).scale(k).build()
    anim.panim_xform = True
    return timed(anim, run or t("base"), "tick")


def slam(mob, run: float | None = None):
    """A stamp landing: from large, hard into place (ease in), with a thud."""
    return timed(FadeIn(mob, scale=2.1, rate_func=ease_in_cubic), run or t("fast") * 0.9, "stamp")


class Shake(Animation):
    """A quick shake side to side, dying away (baked)."""

    def __init__(self, mob, amount: float = 0.09, wiggles: int = 4, **kw):
        self._amount, self._wiggles = amount, wiggles
        super().__init__(mob, **kw)
        self._panim_bake = True

    def begin(self):
        self._home = self.mobject.get_center().copy()
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        dx = self._amount * math.sin(alpha * self._wiggles * 2 * math.pi) * (1 - alpha)
        self.mobject.move_to(self._home + RIGHT * dx)


def shake(mob, run: float | None = None):
    return timed(Shake(mob, rate_func=linear), run or t("base"), "tick")


class Spring(Animation):
    """Scale from nothing on a spring that overshoots twice and settles (baked)."""

    def begin(self):
        self._home = self.mobject.copy()
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        import motion_looks

        k = max(motion_looks.ease_out_elastic(alpha), 0.001)
        self.mobject.become(self._home.copy().scale(k))


def spring_in(mob, run: float | None = None):
    anim = Spring(mob, rate_func=linear)
    anim._panim_bake = True
    return timed(anim, run or t("slow"), "pop")


def draw(mob, run: float | None = None, sfx: str = "draw"):
    """A line or outline drawn on, fast at first."""
    return timed(Create(mob, rate_func=rush_from), run or t("slow"), sfx)


def write(mob, run: float | None = None):
    return timed(Write(mob), run or t("slow"), "type")


def typewriter(text_mob, run: float | None = None):
    """Words typed in, a letter at a time."""
    glyphs = [m for m in text_mob.family_members_with_points() if isinstance(m, VMobject)]
    if len(glyphs) < 2 or len(glyphs) > 300:
        return enter(text_mob, "fade", run=run)
    run = run or min(2.4, max(0.5, 0.04 * len(glyphs)))
    return timed(LaggedStart(*[FadeIn(g, rate_func=linear) for g in glyphs], lag_ratio=1.0), run, "type")


def grow_from(mob, edge, run: float | None = None, overshoot: bool = False):
    """Grown out from an edge (a bar from its baseline)."""
    from manim import GrowFromEdge

    return timed(GrowFromEdge(mob, edge, rate_func=ease_out_back if overshoot else ease_out_cubic), run or t("base"))


def move_to(mob, point, run: float | None = None, rate=None):
    anim = mob.animate(rate_func=rate or ease_out_cubic).move_to(point).build()
    anim.panim_xform = True
    return timed(anim, run or t("base"))


def recolor(mob, colour: str, run: float | None = None):
    return timed(mob.animate.set_color(colour).build(), run or t("fast"))


def refill(mob, colour: str, opacity: float = 1.0, run: float | None = None):
    return timed(mob.animate.set_fill(colour, opacity=opacity).build(), run or t("fast"))


def fade_to(mob, opacity: float, run: float | None = None):
    return timed(mob.animate.set_opacity(opacity).build(), run or t("fast"))


def idle(mob, kind: str | None = None, strength: float = 1.0) -> None:
    """Gentle motion while it is up, played by the players themselves (a drift): a float, a slow drift, none."""
    kind = kind or M.get("idle", "float")
    if kind in ("none", None) or not pl.drifts_on():
        return
    c = mob.get_center()
    if kind == "drift":
        spec = dict(period=19.0, amp=0.07 * strength, scale=0.012 * strength, turn=0.0)
    else:   # float, boil
        spec = dict(period=7.0, amp=0.035 * strength, scale=0.006 * strength, turn=0.003 * strength)
    spec.update(cx=float(c[0]), cy=float(c[1]))
    pl.set_drift([mob], spec)


def group_of(*mobs):
    """A group of what is given (pictures and shapes alike)."""
    if any(isinstance(m, ImageMobject) or (isinstance(m, Group) and not isinstance(m, VGroup)) for m in mobs):
        return Group(*mobs)
    return VGroup(*mobs)
