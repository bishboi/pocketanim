"""How things come on: a small vocabulary of modern entrances, for pictures and cards and for text, that a lecture's
script can choose per op ("enter", "text", "time") and the engine otherwise picks by what is coming on.

    enter   fade | rise | drop | from-left | from-right | pop | zoom | cascade
            rise and drop come up from below or down from above; from-left / from-right slide in from that side;
            pop grows out of a smaller copy with a little overshoot; zoom settles down from a little larger; cascade
            brings a group's parts in one after another.
    text    type | words | write | fade | rise
            type writes the letters one after another (a typewriter); words brings the words in one after another,
            each rising into place; write is the pen's stroke then fill; fade and rise as above, the text whole.
    time    seconds the entrance takes (0.25 to 2.5); by default a quick one (FAST, NORMAL), the modern pace.

Every entrance is a fade carrying a shift and a size, eased (ease_out_cubic, ease_out_expo, ease_out_back), or a
lagged run of those: the phone's players have each of them (a `fade` with shift=, from= and rate=), so the phone
plays them as the video does, not as a recorded clip.
"""

from __future__ import annotations

import os

from manim import (DOWN, LEFT, RIGHT, UP, AnimationGroup, FadeIn, LaggedStart, Text, VMobject, Write,
                   linear)
from manim.utils.rate_functions import ease_out_back, ease_out_cubic, ease_out_expo

ENTER = ("fade", "rise", "drop", "from-left", "from-right", "pop", "zoom", "cascade")
TEXT = ("type", "words", "write", "fade", "rise")
FAST, NORMAL = 0.45, 0.7          # seconds: a small thing (a point, a label), a picture or a card
LONGEST = 2.5
TYPE_MOST = 70                    # letters typed one by one at most; a longer text comes in a word at a time

# What a script chose for the op being built now (Lecture.styled), and what the lecture uses where it chose nothing.
CHOSEN: dict = {}
DEFAULTS = {"picture": "rise", "card": "pop", "point": "from-right", "title": "words", "text": "words"}


def pace(default: float) -> float:
    """The time an entrance takes: the script's choice for this op, else `default`; PANIM_MOTION_SPEED scales all
    (0.5 twice as fast, 2 half as fast)."""
    run = CHOSEN.get("time")
    if run is None:
        try:
            run = default * float(os.environ.get("PANIM_MOTION_SPEED", "1") or 1)
        except ValueError:
            run = default
    return min(max(float(run), 0.25), LONGEST)


def chosen_enter(kind: str) -> str:
    how = CHOSEN.get("enter")
    return how if how in ENTER else DEFAULTS.get(kind, "rise")


def chosen_text(kind: str = "text") -> str:
    how = CHOSEN.get("text")
    return how if how in TEXT else DEFAULTS.get(kind, DEFAULTS["text"])


def _timed(anim, run: float):
    anim.run_time = run
    anim.panim_run = run
    return anim


def enter(mob, how: str | None = None, run: float | None = None, kind: str = "picture"):
    """`mob` coming on, as `how` (ENTER) takes it, in `run` seconds."""
    how = how if how in ENTER else chosen_enter(kind)
    run = pace(NORMAL if kind in ("picture", "card") else FAST) if run is None else run
    reach = max(0.25, min(0.9, 0.12 * max(getattr(mob, "width", 1.0), 1.0)))
    if how == "cascade":
        parts = [m for m in getattr(mob, "submobjects", []) if m.get_family()]
        if len(parts) > 1:
            return _timed(LaggedStart(*[FadeIn(m, shift=UP * 0.3, rate_func=ease_out_cubic) for m in parts],
                                      lag_ratio=0.18), run)
        how = "rise"
    if how == "rise":
        anim = FadeIn(mob, shift=UP * 0.35, rate_func=ease_out_cubic)
    elif how == "drop":
        anim = FadeIn(mob, shift=DOWN * 0.35, rate_func=ease_out_cubic)
    elif how == "from-left":
        anim = FadeIn(mob, shift=RIGHT * reach, rate_func=ease_out_expo)
    elif how == "from-right":
        anim = FadeIn(mob, shift=LEFT * reach, rate_func=ease_out_expo)
    elif how == "pop":
        anim = FadeIn(mob, scale=0.82, rate_func=ease_out_back)
    elif how == "zoom":
        anim = FadeIn(mob, scale=1.12, rate_func=ease_out_expo)
    else:
        anim = FadeIn(mob, rate_func=ease_out_cubic)
    return _timed(anim, run)


def texts_in(mob) -> list:
    """The texts of a group, outermost first (a card's words, not each letter)."""
    out, todo = [], [mob]
    while todo:
        m = todo.pop(0)
        if isinstance(m, Text):
            out.append(m)
        else:
            todo.extend(getattr(m, "submobjects", []))
    return out


def _words(text: Text) -> list:
    """A text's letters grouped into its words (Text has one part per letter that is not a space)."""
    from manim import VGroup

    letters = list(text.submobjects)
    counts = [len(word) for word in str(getattr(text, "original_text", getattr(text, "text", ""))).split()]
    if sum(counts) != len(letters) or not counts:
        return []
    out, at = [], 0
    for n in counts:
        out.append(VGroup(*letters[at:at + n]))
        at += n
    return out


def write_text(text, how: str | None = None, run: float | None = None, kind: str = "text"):
    """A text coming on as `how` (TEXT) has it."""
    how = how if how in TEXT else chosen_text(kind)
    letters = list(getattr(text, "submobjects", [])) if isinstance(text, Text) else []
    if how == "type" and not (1 < len(letters) <= TYPE_MOST):
        how = "words"
    if how == "words" and isinstance(text, Text) and len(_words(text)) < 2:
        how = "rise"
    if run is None:
        run = pace(FAST + min(len(letters), 60) * (0.012 if how == "type" else 0.006))
    if how == "type":
        return _timed(LaggedStart(*[FadeIn(m, rate_func=linear) for m in letters], lag_ratio=0.5), run)
    if how == "words":
        words = _words(text)
        return _timed(LaggedStart(*[FadeIn(w, shift=UP * 0.12, rate_func=ease_out_cubic) for w in words],
                                  lag_ratio=0.35), run)
    if how == "write":
        return _timed(Write(text), max(run, 0.8))
    return enter(text, "rise" if how == "rise" else "fade", run, kind)


def appear(mob, kind: str = "card", run: float | None = None):
    """A card, a point or a title coming on: its words as the text style has them, the rest of it (a backing, a
    bullet, a bar) with the entrance's motion, quicker, so the words land on something already there."""
    words = texts_in(mob)
    how = CHOSEN.get("text") if CHOSEN.get("text") in TEXT else None
    if not words or (how is None and CHOSEN.get("enter") in ENTER):
        return enter(mob, None, run, kind)
    ids = {id(x) for w in words for x in w.get_family()}
    rest = [m for m in mob.get_family() if id(m) not in ids and isinstance(m, VMobject) and len(m.points)
            and not any(id(x) in ids for x in m.get_family())]
    run = pace(NORMAL if kind == "card" else FAST) if run is None else run
    backing = [enter(m, None, run * 0.6, kind) for m in _outermost(rest)]
    lines = [write_text(w, how, None, "title" if kind == "title" else "text") for w in words]
    total = max([run, *[a.run_time for a in lines]])
    anim = AnimationGroup(*backing, LaggedStart(*lines, lag_ratio=0.6) if len(lines) > 1 else lines[0],
                          lag_ratio=0.25 if backing else 0)
    return _timed(anim, total)


def _outermost(mobs: list) -> list:
    ids = {id(m) for m in mobs}
    return [m for m in mobs if not any(id(p) in ids for p in _parents(m, mobs))]


def _parents(m, mobs) -> list:
    return [p for p in mobs if p is not m and any(x is m for x in p.get_family()[1:])]
