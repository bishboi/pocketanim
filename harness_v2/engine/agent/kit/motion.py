"""How things move: entrances, exits, emphasis, staggering, idle drift. Every function returns a Manim Animation
(or adds an updater), so it goes straight into self.play(...).

    self.play(enter(card, "pop"))                    # one entrance by name (ENTRANCES)
    self.play(stagger([a, b, c], "rise", lag=0.15))  # one after another, overlapping
    self.play(emph(word, "pulse"))                   # say "this one" (EMPHASES)
    self.play(leave(card, "sink"))                   # an exit (EXITS)
    drift(photo)                                     # a slow idle creep while it is on screen (stop_drift to end)

With `how=None` a piece takes its look's own default (vox pops shapes and lifts text; blueprint draws outlines and
types text), so changing the look changes the motion too.
"""

from __future__ import annotations

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, RIGHT, UP, Animation, AnimationGroup, Create, DrawBorderThenFill, FadeIn,
                   FadeOut, Flash, GrowFromCenter, GrowFromEdge, ImageMobject, LaggedStart, Mobject, ShrinkToCenter,
                   SpinInFromNothing, Text, Uncreate, Unwrite, VMobject, Wiggle, Write, there_and_back, linear,
                   smooth)
from manim import rate_functions as rf

from .look import L

SIDES = {"left": LEFT, "right": RIGHT, "up": UP, "down": DOWN, "top": UP, "bottom": DOWN}


def _side(side, default=LEFT):
    if side is None:
        return default
    if isinstance(side, str):
        return SIDES[side]
    return np.array(side, dtype=float)


def _vector_only(mob: Mobject) -> bool:
    return not any(isinstance(m, ImageMobject) for m in mob.get_family())


def _texts(mob: Mobject) -> list:
    return [m for m in mob.get_family() if isinstance(m, Text)]


class Present(Animation):
    """Holds a piece in the scene for the length of its parts' animations (so the piece itself, not only its parts,
    is on stage: a later FadeOut of the piece takes all of it away)."""

    def interpolate_mobject(self, alpha: float) -> None:
        pass


def owned(piece: Mobject, anim: Animation) -> Animation:
    """An animation of a piece's parts that brings the whole piece on stage with it."""
    return AnimationGroup(Present(piece, run_time=anim.get_run_time()), anim)


class TypeIn(Animation):
    """Letters coming on one by one (a typewriter), for any piece that holds text; other shapes fade in with it."""

    def __init__(self, mob: Mobject, **kw):
        super().__init__(mob, rate_func=kw.pop("rate_func", linear), **kw)
        self._panim_bake = True

    def begin(self):
        glyphs = []
        for t in _texts(self.mobject):
            glyphs.extend(t.submobjects or [t])
        self.glyphs = glyphs or [self.mobject]
        self.others = [m for m in self.mobject.get_family() if isinstance(m, VMobject) and not m.submobjects
                       and m not in self.glyphs and not any(m in g.get_family() for g in self.glyphs)]
        self.fill = {id(m): (m.get_fill_opacity(), m.get_stroke_opacity()) for m in self.glyphs + self.others}
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        shown = int(round(alpha * len(self.glyphs)))
        for i, g in enumerate(self.glyphs):
            f, s = self.fill.get(id(g), (1, 1))
            on = i < shown
            g.set_fill(opacity=f if on else 0).set_stroke(opacity=s if on else 0)
        for m in self.others:
            f, s = self.fill[id(m)]
            k = min(1.0, alpha * 4)
            m.set_fill(opacity=f * k).set_stroke(opacity=s * k)


class Unfold(Animation):
    """Opens from one edge (a scroll unrolling, a banner, a bar): stretched from nothing along one axis."""

    def __init__(self, mob: Mobject, edge=LEFT, **kw):
        self.edge = np.array(edge, dtype=float)
        super().__init__(mob, **kw)

    def begin(self):
        self.anchor = self.mobject.get_critical_point(self.edge).copy()
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        self.mobject.become(self.starting_mobject.copy())
        k = max(1e-3, alpha)
        dim = 0 if abs(self.edge[0]) > 0 else 1
        self.mobject.stretch(k, dim, about_point=self.anchor)


class Spring(Animation):
    """Grows from a point with a damped wobble (a springy pop)."""

    def interpolate_mobject(self, alpha: float) -> None:
        self.mobject.become(self.starting_mobject.copy())
        k = 1 - np.exp(-6 * alpha) * np.cos(10 * alpha)
        self.mobject.scale(max(1e-3, k))


class Shake(Animation):
    def __init__(self, mob, amount: float = 0.12, **kw):
        self.amount = amount
        super().__init__(mob, rate_func=linear, **kw)

    def interpolate_mobject(self, alpha: float) -> None:
        self.mobject.become(self.starting_mobject.copy())
        self.mobject.shift(RIGHT * self.amount * np.sin(alpha * 6 * 2 * np.pi) * (1 - alpha))


class Pulse(Animation):
    def __init__(self, mob, k: float = 1.12, **kw):
        self.k = k
        super().__init__(mob, rate_func=there_and_back, **kw)

    def interpolate_mobject(self, alpha: float) -> None:
        self.mobject.become(self.starting_mobject.copy())
        self.mobject.scale(1 + (self.k - 1) * alpha)


class Bounce(Animation):
    def __init__(self, mob, height: float = 0.3, **kw):
        self.h = height
        super().__init__(mob, rate_func=linear, **kw)

    def interpolate_mobject(self, alpha: float) -> None:
        self.mobject.become(self.starting_mobject.copy())
        self.mobject.shift(UP * self.h * abs(np.sin(alpha * 2 * np.pi)) * (1 - alpha))


class Tint(Animation):
    """Takes on a colour and goes back (there and back)."""

    def __init__(self, mob, color, **kw):
        self.color = color
        super().__init__(mob, rate_func=there_and_back, **kw)

    def interpolate_mobject(self, alpha: float) -> None:
        self.mobject.become(self.starting_mobject.copy())
        for m in self.mobject.get_family():
            if isinstance(m, VMobject) and not m.submobjects:
                if m.get_fill_opacity() > 0:
                    m.set_fill(interp_color(m.get_fill_color(), self.color, alpha))
                if m.get_stroke_opacity() > 0 and m.get_stroke_width() > 0:
                    m.set_stroke(interp_color(m.get_stroke_color(), self.color, alpha))


def interp_color(a, b, t):
    from manim import ManimColor
    return ManimColor(a).interpolate(ManimColor(b), t)


ENTRANCES = ("fade", "rise", "drop", "slide", "pop", "grow", "grow_left", "grow_up", "draw", "write", "type",
             "unfold", "unfold_down", "zoom", "spin", "stamp", "spring", "instant")
EXITS = ("fade", "sink", "lift", "slide", "shrink", "zoom", "unwrite", "uncreate", "instant")
EMPHASES = ("pulse", "wiggle", "shake", "flash", "bounce", "tint")


def _default(kind: str) -> str:
    look = L()
    return {"text": look.enter_text, "line": look.enter_line}.get(kind, look.enter_shape)


def enter(mob: Mobject, how: str | None = None, side=None, run: float | None = None, kind: str = "shape",
          **kw) -> Animation:
    """mob coming on. `how` (ENTRANCES): fade, rise, drop, slide (from `side`), pop, grow, grow_left, grow_up, draw,
    write, type, unfold (from the left), unfold_down, zoom (from big), spin, stamp (slammed down), spring, instant.
    Default: the look's own for the piece's kind (text, shape, line)."""
    look = L()
    how = how or _default(kind)
    run = run if run is not None else look.run
    vector = _vector_only(mob)
    if how in ("draw", "write", "type", "uncreate") and not vector:
        how = "pop" if how == "draw" else "rise"
    if how == "fade":
        return FadeIn(mob, run_time=run, rate_func=smooth, **kw)
    if how == "rise":
        return FadeIn(mob, shift=UP * 0.3, scale=0.97, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "drop":
        return FadeIn(mob, shift=DOWN * 0.4, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "slide":
        d = _side(side, LEFT)
        return FadeIn(mob, shift=-d * 1.5, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "pop":
        if look.overshoot > 0:
            return GrowFromCenter(mob, run_time=run, rate_func=rf.ease_out_back, **kw)
        return GrowFromCenter(mob, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "grow":
        return GrowFromCenter(mob, run_time=run, rate_func=smooth, **kw)
    if how == "grow_left":
        return GrowFromEdge(mob, LEFT, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "grow_up":
        return GrowFromEdge(mob, DOWN, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "draw":
        filled = any(isinstance(m, VMobject) and m.get_fill_opacity() > 0.05 for m in mob.get_family())
        if filled and not _texts(mob):
            return DrawBorderThenFill(mob, run_time=run * 1.4, rate_func=smooth, **kw)
        if _texts(mob):
            return Write(mob, run_time=run * 1.4, **kw)
        return Create(mob, run_time=run * 1.4, rate_func=smooth, **kw)
    if how == "write":
        return Write(mob, run_time=run * 1.5, **kw)
    if how == "type":
        n = sum(len(t.submobjects) for t in _texts(mob)) or 10
        return TypeIn(mob, run_time=kw.pop("run_time", max(run, min(2.5, n * 0.035))), **kw)
    if how == "unfold":
        return Unfold(mob, LEFT, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "unfold_down":
        return Unfold(mob, UP, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "zoom":
        return FadeIn(mob, scale=1.6, run_time=run, rate_func=rf.ease_out_cubic, **kw)
    if how == "spin":
        return SpinInFromNothing(mob, run_time=run, **kw)
    if how == "stamp":
        return FadeIn(mob, scale=2.2, run_time=min(run, 0.35), rate_func=rf.ease_in_quad, **kw)
    if how == "spring":
        return Spring(mob, run_time=max(run, 0.8), rate_func=linear, **kw)
    if how == "instant":
        return FadeIn(mob, run_time=1 / 30, **kw)
    raise ValueError(f"no entrance {how!r}; entrances: {', '.join(ENTRANCES)}")


def leave(mob: Mobject, how: str | None = None, side=None, run: float | None = None, **kw) -> Animation:
    """mob going off. `how` (EXITS): fade (default), sink, lift, slide (to `side`), shrink, zoom, unwrite,
    uncreate, instant."""
    look = L()
    how = how or "fade"
    run = run if run is not None else look.run * 0.8
    if how in ("unwrite", "uncreate") and not _vector_only(mob):
        how = "fade"
    if how == "fade":
        return FadeOut(mob, run_time=run, **kw)
    if how == "sink":
        return FadeOut(mob, shift=DOWN * 0.3, run_time=run, rate_func=look.ease_out, **kw)
    if how == "lift":
        return FadeOut(mob, shift=UP * 0.3, run_time=run, rate_func=look.ease_out, **kw)
    if how == "slide":
        return FadeOut(mob, shift=_side(side, LEFT) * 1.5, run_time=run, rate_func=look.ease_out, **kw)
    if how == "shrink":
        return ShrinkToCenter(mob, run_time=run, **kw) if _vector_only(mob) else FadeOut(mob, scale=0.3,
                                                                                            run_time=run, **kw)
    if how == "zoom":
        return FadeOut(mob, scale=1.5, run_time=run, **kw)
    if how == "unwrite":
        return Unwrite(mob, run_time=run * 1.2, **kw)
    if how == "uncreate":
        return Uncreate(mob, run_time=run * 1.2, **kw)
    if how == "instant":
        return FadeOut(mob, run_time=1 / 30, **kw)
    raise ValueError(f"no exit {how!r}; exits: {', '.join(EXITS)}")


def emph(mob: Mobject, how: str | None = None, run: float | None = None, color=None, **kw) -> Animation:
    """Point at mob without changing it for good. `how` (EMPHASES): pulse (default), wiggle, shake, flash, bounce,
    tint (to `color`, and back). For a lasting mark use marks (circle, highlight, underline)."""
    look = L()
    how = how or "pulse"
    run = run if run is not None else 0.7
    if how == "pulse":
        return Pulse(mob, k=kw.pop("k", 1.12), run_time=run)
    if how == "wiggle":
        return Wiggle(mob, run_time=max(run, 0.8), **kw)
    if how == "shake":
        return Shake(mob, run_time=max(run, 0.5), **kw)
    if how == "flash":
        return Flash(mob, color=color or look.accent, line_length=0.3, flash_radius=max(mob.width, mob.height) / 2 + 0.2,
                     run_time=run, **kw)
    if how == "bounce":
        return Bounce(mob, run_time=max(run, 0.6), **kw)
    if how == "tint":
        return Tint(mob, color or look.accent, run_time=max(run, 1.0))
    raise ValueError(f"no emphasis {how!r}; emphases: {', '.join(EMPHASES)}")


def stagger(items, how: str | None = None, lag: float | None = None, run: float | None = None, side=None,
            kind: str | None = None) -> Animation:
    """Items entering one after another, overlapping: `lag` seconds between starts. Items may be mobjects (each
    enters with `how`) or animations (played as they are)."""
    look = L()
    run = run if run is not None else look.run
    lag = lag if lag is not None else look.lag
    anims = []
    for it in items:
        if isinstance(it, Animation):
            anims.append(it)
        elif hasattr(it, "appear") and how is None:
            anims.append(it.appear(run=run))
        else:
            anims.append(enter(it, how, side=side, run=run, kind=kind or getattr(it, "enter_kind", "shape")))
    if not anims:
        return Animation(Mobject(), run_time=0.01)
    longest = max(a.get_run_time() for a in anims)
    return LaggedStart(*anims, lag_ratio=min(1.0, lag / max(longest, 1e-3)))


def chain(anims) -> Animation:
    """Animations played one after the other (each starts when the one before ends)."""
    return LaggedStart(*anims, lag_ratio=1.0)


def later(anim: Animation, delay: float) -> Animation:
    """`anim` starting `delay` seconds into the play it is part of (its mobject hidden until then if it enters)."""
    if delay <= 0:
        return anim
    return LaggedStart(Animation(Mobject(), run_time=delay, remover=True), anim, lag_ratio=1.0)


def together(anims) -> Animation:
    return AnimationGroup(*anims)


def sweep_headline(h, run: float | None = None) -> Animation:
    """A headline coming on in its look: vox sweeps the highlighter under the words as they rise; blueprint types
    the words and rules the line under them."""
    look = L()
    run = run if run is not None else look.run
    words = h.part("words")
    mark = h.parts.get("mark")
    if mark is None:
        return owned(h, enter(words, None, run=run, kind="text"))
    if look.name == "blueprint":
        return owned(h, LaggedStart(enter(words, "type", run=run), Create(mark, run_time=run * 0.8), lag_ratio=0.6))
    return owned(h, LaggedStart(enter(words, "rise", run=run * 0.8),
                                GrowFromEdge(mark, LEFT, run_time=run * 0.9, rate_func=rf.ease_out_cubic),
                                lag_ratio=0.35))


# ---------------------------------------------------------------- idle motion --------------------------------------
def drift(mob: Mobject, speed: float = 0.04, zoom: float = 0.006, direction=None) -> Mobject:
    """A slow creep while it is on screen (Vox's documentary drift): moves `speed` units a second (along
    `direction`, default up-right) and grows by `zoom` a second. stop_drift(mob) ends it."""
    d = np.array(direction if direction is not None else (0.8, 0.3, 0), dtype=float)
    d = d / (np.linalg.norm(d) or 1)

    def creep(m, dt):
        m.shift(d * speed * dt)
        m.scale(1 + zoom * dt)

    mob._kit_drift = creep
    mob.add_updater(creep)
    return mob


def bob(mob: Mobject, height: float = 0.05, period: float = 3.0) -> Mobject:
    """A gentle float up and down (a cutout breathing on the page). stop_drift(mob) ends it."""
    state = {"t": 0.0, "y": 0.0}

    def float_(m, dt):
        state["t"] += dt
        y = height * np.sin(2 * np.pi * state["t"] / period)
        m.shift(UP * (y - state["y"]))
        state["y"] = y

    mob._kit_drift = float_
    mob.add_updater(float_)
    return mob


def stop_drift(mob: Mobject) -> Mobject:
    f = getattr(mob, "_kit_drift", None)
    if f is not None:
        mob.remove_updater(f)
        mob._kit_drift = None
    return mob
