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
from manim.utils import rate_functions
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
        # The figure as laid out may have been scaled (fitted to its card, the template fitted to the stage): each
        # frame's words are made at that scale, not the maker's (a "31 households" grew out of its card counting).
        ref = self._make(self._text)
        self._k = float(self.mobject.height) / float(ref.height) if ref.height > 1e-6 and self.mobject.height > 1e-6 \
            else 1.0
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        if self._parsed is None:
            return
        alpha = min(max(alpha, 0.0), 1.0)
        a = ease_out_cubic(alpha)
        value = self._start + (self._parsed[1] - self._start) * a
        words = self._text if alpha >= 1 else format_number(self._parsed, value)
        made = self._make(words)
        if abs(self._k - 1.0) > 1e-3:
            made.scale(self._k)
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
        parsed = parse_number(text)
        # A rank (3rd, 21st) is not a quantity: counted up it read "2rd" on the way. It simply comes on.
        if parsed is None or re.fullmatch(r"\s*(st|nd|rd|th)\b.*", parsed[4], re.I):
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
    group.panim_stamp = True  # another stamp keeps off it (MotionLecture._stamp_clear)
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


# How a template's parts come on when the script chose it (`enter`): set while the template is built, and while its
# parts said later are (MotionLecture._moment); it overrides each part's own way of coming on.
FORCE_ENTER: str | None = None
ENTRANCES = ("pop", "rise", "drop", "slide", "zoom", "fade", "flip", "write", "unfold", "typewrite", "ink", "stamp",
             "spin", "iris")


def forced() -> str | None:
    return FORCE_ENTER


def enter(mob, how: str | None = None, side: str | None = None, run: float | None = None):
    """How something comes on, by name (the look's own when None):
    pop     grows from small with an overshoot              rise    comes up a little as it fades in
    drop    falls in from above with an overshoot           slide   sweeps in from a side, fast then slow
    zoom    comes from large, settling                      write   written (words) or drawn (lines)
    fade    simply fades in                                 flip    turns in, as a card turned over
    unfold  opens out from a line, top and bottom apart      typewrite  its frame drawn, then its words typed in
    ink     bleeds in slowly from a little larger, as ink    stamp   slammed down with a thud
    spin    turns in a full circle as it grows              iris    opens from a point at its middle
    """
    how = FORCE_ENTER or how or M.get("enter", "pop")
    run = run if run is not None else t("base")
    return _feel(_enter(mob, how, side, run), mob, how)


# How a look's things land (its `energy`): calm ones glide in and stop; lively and punchy ones overshoot a little and
# settle back. (A squash on landing and a pull back before leaving moved the whole picture with a transform, and the
# players lost it: taken out.)
SPRING_HOWS = ("rise", "slide", "zoom")                    # brought in eased, given the look's overshoot


def feel() -> str:
    return str(M.get("energy", "lively"))


def _feel(anim, mob, how: str):
    """An entrance with the look's weight: an overshoot for a lively or punchy look's eased entrances (an easing the
    players have). Calm looks stay as they are."""
    if anim is None or feel() == "calm" or images_only(mob):
        return anim
    if how in SPRING_HOWS and getattr(anim, "rate_func", None) in (ease_out_cubic, ease_out_expo):
        anim.rate_func = ease_out_back
    return anim


def images_only(mob) -> bool:
    """A photo or a picture alone (no words, no shapes): it is not squashed or sprung (a photo is not rubber)."""
    fam = mob.get_family()
    return bool(fam) and all(isinstance(m, ImageMobject) or not getattr(m, "points", np.zeros(0)).size for m in fam)


def _enter(mob, how: str, side: str | None, run: float):
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
    if how == "unfold":
        return timed(baked(Unfold(mob, rate_func=ease_out_cubic)), run, "swish")
    if how == "typewrite":
        words = [m for m in mob.get_family() if isinstance(m, Text)]
        frame = [m for m in mob.submobjects if not any(isinstance(x, Text) for x in m.get_family())]
        if not words:
            return timed(FadeIn(mob, shift=UP * 0.35, rate_func=ease_out_cubic), run, "pop")
        steps = [timed(FadeIn(Group(*frame), scale=0.96, rate_func=smooth), run * 0.6)] if frame else []
        steps += [typewriter(w, run=max(0.4, run)) for w in words[:6]]
        return chain(steps)
    if how == "ink":
        return timed(FadeIn(mob, scale=1.06, rate_func=rate_functions.ease_in_out_sine), max(run, t("slow") * 1.4))
    if how == "stamp":
        return slam(mob, run=run)
    if how == "spin":
        return timed(baked(SpinIn(mob, rate_func=ease_out_cubic)), max(run, t("slow")), "whoosh")
    if how == "iris":
        return timed(FadeIn(mob, scale=0.02, rate_func=ease_out_cubic), run, "whoosh")
    return timed(FadeIn(mob, shift=UP * 0.35, rate_func=ease_out_cubic), run, "pop")


class SpinIn(Animation):
    """Comes on turning (`turns` times round) and growing from small, settling where it was laid out (baked). One
    animation, not a fade and a turn together: begun together, the turn took the faded start and kept it hidden.
    Applied step by step from the last frame's turn and size (a group with a picture in it cannot `become`)."""

    def __init__(self, mob, turns: float = 1.0, start_scale: float = 0.15, **kw):
        self._turns, self._k0 = turns, start_scale
        super().__init__(mob, **kw)

    def begin(self):
        self._centre = self.mobject.get_center().copy()
        self._now = (1.0, 0.0)
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        a = min(max(alpha, 0.0), 1.0)
        k, turn = self._k0 + (1 - self._k0) * a, 2 * math.pi * self._turns * (1 - a)
        k0, t0 = self._now
        self.mobject.rotate(-t0, about_point=self._centre).scale(k / k0, about_point=self._centre)
        self.mobject.rotate(turn, about_point=self._centre)
        self._now = (k, turn)


class Unfold(Animation):
    """Opens out from a flat line at its middle, top and bottom moving apart (baked: the players have no verb for a
    stretch that changes over time). Applied step by step from the last frame's height."""

    def begin(self):
        self._centre = self.mobject.get_center().copy()
        self._now = 1.0
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        f = max(0.02, min(max(alpha, 0.0), 1.0))
        self.mobject.stretch(f / self._now, 1, about_point=self._centre)
        self._now = f


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

def fresh(anim):
    """An `.animate` animation whose end is worked out when it starts, not when it was built. Built earlier in a
    beat that then moved its part (the stage shrunk into half the board for a picture or a card beside it), it took
    the part back to where it had been: a timeline's pointed-at events jumped back full size over the moved one."""
    from manim.animation.transform import _MethodAnimation

    class Fresh(_MethodAnimation):
        def _entering(self) -> bool:
            # Begun in the same play as the part's own entrance (a short line says its name as it comes on), the
            # part stands at the entrance's start (unseen, small): a pulse from there, there and back, ended there.
            for x, (fill, stroke) in zip(self.mobject.get_family(), getattr(self, "_m_settled", None) or []):
                for now, was in ((x.get_fill_opacity, fill), (x.get_stroke_opacity, stroke)):
                    try:
                        if was is not None and float(now()) < was - 0.02:
                            return True
                    except Exception:  # noqa: BLE001
                        pass
            return False

        def begin(self):
            snap = getattr(self, "_m_snap", None)
            # Its look as it was when this was made (as it will be once in) is the one to start from and end in.
            base = snap.copy() if snap is not None and self._entering() else self.mobject.copy()
            target = base.copy()
            for item in self.methods:
                item.method.__func__(target, *item.args, **item.kwargs)
            self.mobject.target = target
            super().begin()
            if base is not None and snap is not None and base is not self.mobject:
                self.starting_mobject = base

    if isinstance(anim, _MethodAnimation):
        anim.__class__ = Fresh

        def settled(x):
            try:
                return float(x.get_fill_opacity()), float(x.get_stroke_opacity())
            except Exception:  # noqa: BLE001 -- a picture: no fill or stroke of its own
                return None, None
        anim._m_settled = [settled(x) for x in anim.mobject.get_family()]
        anim._m_snap = anim.mobject.copy()
    return anim


def pulse(mob, k: float = 1.12, run: float | None = None):
    """A beat of attention: up and back."""
    anim = fresh(mob.animate(rate_func=there_and_back).scale(k).build())
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
    """Scaled in from small with an overshoot (ease_out_back): a verb the players play themselves. Baked (Spring),
    a sign's words came apart in the players while it sprang (only a letter or two drawn, the chip stretched)."""
    return timed(FadeIn(mob, scale=0.3, rate_func=ease_out_back), run or t("base"), "pop")


def draw(mob, run: float | None = None, sfx: str = "draw"):
    """A line or outline drawn on, fast at first."""
    return timed(Create(mob, rate_func=rush_from), run or t("slow"), sfx)


def write(mob, run: float | None = None):
    return timed(Write(mob), run or t("slow"), "type")


def typewriter(text_mob, run: float | None = None):
    """Words typed in, a letter at a time."""
    glyphs = [m for m in text_mob.family_members_with_points() if isinstance(m, VMobject)]
    if len(glyphs) < 2 or len(glyphs) > 300:
        # Faded in directly: through enter(), a template told to come on by typing came back here without end.
        return timed(FadeIn(text_mob, rate_func=smooth), run or t("base"))
    run = run or min(2.4, max(0.5, 0.04 * len(glyphs)))
    return timed(LaggedStart(*[FadeIn(g, rate_func=linear) for g in glyphs], lag_ratio=1.0), run, "type")


def grow_from(mob, edge, run: float | None = None, overshoot: bool = False):
    """Grown out from an edge (a bar from its baseline)."""
    from manim import GrowFromEdge

    return timed(GrowFromEdge(mob, edge, rate_func=ease_out_back if overshoot else ease_out_cubic), run or t("base"))


def move_to(mob, point, run: float | None = None, rate=None):
    anim = fresh(mob.animate(rate_func=rate or ease_out_cubic).move_to(point).build())
    anim.panim_xform = True
    return timed(anim, run or t("base"))


def recolor(mob, colour: str, run: float | None = None):
    return timed(fresh(mob.animate.set_color(colour).build()), run or t("fast"))


def refill(mob, colour: str, opacity: float = 1.0, run: float | None = None):
    return timed(fresh(mob.animate.set_fill(colour, opacity=opacity).build()), run or t("fast"))


def fade_to(mob, opacity: float, run: float | None = None):
    return timed(fresh(mob.animate.set_opacity(opacity).build()), run or t("fast"))


def idle(mob, kind: str | None = None, strength: float = 1.0) -> None:
    """Gentle motion while it is up, played by the players themselves (a drift): a float, a slow drift, none."""
    kind = kind or M.get("idle", "float")
    if kind in ("none", None) or not pl.drifts_on():
        return
    c = mob.get_center()
    if kind == "drift":
        spec = dict(period=19.0, amp=0.07 * strength, scale=0.012 * strength, turn=0.0)
    elif kind == "breathe":     # swelling and settling in place, as a living thing breathes
        spec = dict(period=6.0, amp=0.0, scale=0.03 * strength, turn=0.0)
    elif kind == "sway":        # rocking a little about its middle
        spec = dict(period=5.0, amp=0.0, scale=0.0, turn=0.02 * strength)
    elif kind == "parallax":    # carried slowly across, as a camera passing a scene
        spec = dict(period=32.0, amp=0.22 * strength, scale=0.006 * strength, turn=0.0)
    elif kind == "flicker":     # a quick unsteady tremble, as old film or candlelight
        spec = dict(period=0.9, amp=0.012 * strength, scale=0.008 * strength, turn=0.002 * strength)
    else:   # float, boil
        spec = dict(period=7.0, amp=0.035 * strength, scale=0.006 * strength, turn=0.003 * strength)
    spec.update(cx=float(c[0]), cy=float(c[1]))
    pl.set_drift([mob], spec)


def group_of(*mobs):
    """A group of what is given (pictures and shapes alike)."""
    if any(isinstance(m, ImageMobject) or (isinstance(m, Group) and not isinstance(m, VGroup)) for m in mobs):
        return Group(*mobs)
    return VGroup(*mobs)
