"""The motion engine (beta): the lecture engine's beats, voice and timing, with everything on screen designed and
animated as a modern explainer is -- in a look (motion_looks.py), with motion built into each template.

A scene compiled by compile_motion.py:

    os.environ.setdefault("LECTURE_STYLE", "vox")       # the classic style the look rests on (the voice tools read it)
    os.environ.setdefault("MOTION_LOOK", "paper")
    from motion import *

    class GeneratedScene(MotionLecture):
        def construct(self):
            self.chapter(1, "Japan's debt", "", "Japan's debt")
            self.board()
            self.beat("Japan owes more than twice its economy.",
                      self.safe(lambda: self.m_chart({...}), "chapter 1 beat 1 chart", said="Japan"))

What changes from the classic engine (MapLecture), which this extends:

* THE LOOK: colours, fonts, a texture on the board, cards with soft shadows, pictures dressed as stickers, cards,
  polaroids or newsprint (motion_looks.dress), all from the look.
* TEMPLATES (m_*): a counter, charts (columns, bars, a line), a grid of units, cards dealt in a row, a stamp, data
  cards, a chain of steps, a list, a versus, a donut, a document with phrases highlighted, polaroids, a headline,
  and the classic operations redrawn (stat, bars, timeline in five styles, compare, define, quote,
  equation, process, pictures, chapter cards). Each brings itself on in a choreography: its parts in order, each
  the way it should move, one overlapping the next.
* MOMENTS ON WORDS: a template's parts come on (or are pointed at) as the line says them: a column as its country
  is named, a group of units as it is said, a step of a chain, a phrase of a document highlighted. The same words
  on a later line point at it again, in the look's way.
* TRANSITIONS: one picture gives way to the next as the look has it: slides, pushes, a coloured wipe, a dissolve,
  a zoom.
* IDLE MOTION: what is up keeps moving gently (a drift the players play themselves), so nothing is ever frozen.
* SOUND: each motion its sound (sfx.py): pops, swishes, a stamp's thud, a counter's ticks.

Every animation is one the exporter writes as the players' verbs, or a play marked to be baked into a clip (a
counter, a spring, a shake): the phones need nothing new.
"""

from __future__ import annotations

import math
import os
import re
from types import SimpleNamespace

import numpy as np
from manim import *  # noqa: F403 -- a scene `from motion import *` gets Manim's names, as from pocket_lecture
from manim.utils.rate_functions import ease_in_cubic, ease_out_back, ease_out_cubic, ease_out_expo, rush_from, rush_into

import motion_kit as K
import motion_looks
from motion_more import MoreTemplates
import pocket_lecture as pl
from pocket_lecture import *  # noqa: F403 -- the engine's names, for the compiled scene
from pocket_lecture import (BEAT_PAD, PARAGRAPH_PAD, Z_MARK, MapLecture, _flat, fit, said_at, set_drift, wrap)

motion_looks.register_all()
LOOK = os.environ.get("MOTION_LOOK") or ""
if LOOK in pl.THEMES:
    pl.use_style(LOOK)
    os.environ["LECTURE_STYLE"] = LOOK
K.M.update(motion_looks.motion_of(pl.STYLE, os.environ.get("MOTION_ENERGY") or None,
                                  {"transition": os.environ.get("MOTION_TRANSITION") or None}))

Z_TEMPLATE = Z_MARK + 10
TITLE_ROOM = 0.75           # the band at the top of a template its title takes


def _slug(text) -> str:
    return re.sub(r"[^\w]+", "-", str(text).strip().lower()).strip("-")


def _P():
    return pl.P


class MotionLecture(MoreTemplates, MapLecture):
    """A lecture in a look, every template animated (see the module's notes)."""

    # ---------------------------------------------------------------- set-up ----------------------------------------
    def setup(self):
        super().setup()
        self.M = K.M
        self._mparts: dict[str, dict] = {}      # template id -> {part name: mobject}
        self._wipe_old: list = []               # what a wipe takes away as the next line begins
        self._lead = 0.0                         # seconds a transition took of the line before its pictures
        self._m_count = 0
        if not self.M.get("classic"):
            tex = motion_looks.texture_file(self.M.get("texture", "paper"), pl.P.BG)
            if tex is not None:
                fw, fh = config.frame_width, config.frame_height
                board = ImageMobject(str(tex))
                board.stretch_to_fit_width(fw + 0.3)
                board.stretch_to_fit_height(fh + 0.2)
                board.set_z_index(pl.Z_BACK - 1)
                board.is_backdrop = True
                board._panim_static = True
                self.add(board)

    def play(self, *animations, **kwargs):
        """The engine's play; then the groups Manim put on the screen to hold a lagged group's parts are taken off
        again (quietly: the exporter never had them on its stage), so a part left in one is not a stray that stays
        up -- over the next picture -- after its picture leaves."""
        containers, leaves = [], []

        def walk(anim):
            subs = getattr(anim, "animations", None)
            if subs:
                group = getattr(anim, "group", None)
                if group is not None:
                    containers.append(group)
                for sub in subs:
                    walk(sub)
            elif getattr(anim, "mobject", None) is not None and not getattr(anim, "remover", False):
                leaves.append(anim.mobject)

        for anim in animations:
            walk(anim)
        # Words in the accent's yellow on a cream board, or a block's GOLD on a white card, made to read on what they
        # sit on (legible.py).
        import backed_text
        import legible

        legible.legible(self, backed_text.arriving_in(animations))
        super().play(*animations, **kwargs)
        # A part brought on by itself (a FadeIn of one word of a heading) went on the screen alone: what it belongs
        # to (the stage's picture, a part added to it) is put on the screen whole instead, so it leaves whole. Only
        # for the stage's pictures: what the engine draws elsewhere (a recap, the panel) is left as it does it.
        holders = [m for m in [self.stage_items, *self.stage_extra, *self.stage_pending] if m is not None]
        if not holders:
            return
        held = {id(x) for h in holders for x in h.get_family()}
        ids = {id(g) for g in containers}
        # What is on the screen before the containers go: a holder seen only through one (the stage's picture moved
        # aside by a lagged group) is put back whole below, not taken off with it.
        seen = {id(x) for m in self.mobjects for x in m.get_family()}
        for g in [m for m in self.mobjects if id(m) in ids]:
            if any(id(x) in held for x in g.get_family()):
                self.mobjects.remove(g)
        top = {id(m) for m in self.mobjects}
        for h in holders:
            if id(h) in top:
                continue
            family = {id(x) for x in h.get_family()}
            members = [m for m in self.mobjects if id(m) in family]
            if not members:
                if id(h) in seen and not any(id(h) in {id(x) for x in m.get_family()} for m in self.mobjects):
                    self.mobjects.append(h)
                    top = {id(m) for m in self.mobjects}
                continue
            for m in members:
                self.mobjects.remove(m)
            self.mobjects.append(h)
            top = {id(m) for m in self.mobjects}

    def _next_id(self, kind: str) -> str:
        self._m_count += 1
        return f"{kind}{self._m_count}"

    # ---------------------------------------------------------------- stage: entrances, exits, transitions -------
    def _to_stage(self, group, draw=None, still: bool = False, entrance=None):
        """As the engine's, with the look's entrance for a picture that brings none of its own (a photo, a cutout,
        a card), and a slide or push in from the side the old one leaves by."""
        if entrance is None and not still and (not draw or all(isinstance(m, ImageMobject) or
                                                              not isinstance(m, VMobject) for m in draw)):
            how = {"slide": "slide", "push": "rise", "zoom": "zoom", "page": "slide"}.get(
                self.M.get("transition"), self.M.get("enter", "pop"))
            if how == "write":
                how = "rise"
            entrance = K.enter(group, how, side="right", run=K.t("base"))
            K.idle(group)
            draw = None
        anim = super()._to_stage(group, draw=draw, still=still, entrance=entrance)
        if anim is not None and entrance is not None and getattr(entrance, "panim_run", None):
            run = float(entrance.panim_run) + (0.35 if isinstance(anim, AnimationGroup) and anim is not entrance
                                               and getattr(anim, "lag_ratio", 0) == 1.0 else 0)
            K.timed(anim, run, getattr(entrance, "panim_sfx", None))
        return anim

    def _stage_leaving(self) -> list:
        """The engine's fade-outs for what leaves the stage, made the look's exit: slid out (the way the next
        comes from), pushed up, zoomed past; for a wipe, taken away under the wipe as the next line begins."""
        going = super()._stage_leaving()
        kind = self.M.get("transition", "slide")
        out = []
        for anim in going:
            if not isinstance(anim, FadeOut) or getattr(anim, "mobject", None) is None:
                out.append(anim)
                continue
            mob = anim.mobject
            if kind == "wipe":
                self._wipe_old.append(mob)
            elif kind in ("slide", "page"):
                out.append(K.timed(FadeOut(mob, shift=LEFT * 2.2, rate_func=rush_into), K.t("fast"), "swish"))
            elif kind == "push":
                out.append(K.timed(FadeOut(mob, shift=UP * 1.2, rate_func=rush_into), K.t("fast"), "swish"))
            elif kind == "zoom":
                out.append(K.timed(FadeOut(mob, scale=1.25, rate_func=rush_into), K.t("fast"), "whoosh"))
            elif kind == "cut":
                out.append(K.timed(FadeOut(mob, run_time=0.05), 0.05))
            else:
                out.append(anim)
        return out

    def _speak(self, wav, seconds: float) -> None:
        """The line's voice; then, under it, a wipe across the board when the look wipes from one picture to the
        next (the old picture taken away under it)."""
        super()._speak(wav, seconds)
        old = [m for m in self._wipe_old if any(m is x for x in self.mobjects)]
        self._wipe_old = []
        if not old:
            return
        fw, fh = config.frame_width, config.frame_height
        bx, by, bw, bh = self.STAGE
        sheet = Rectangle(width=bw + 1.0, height=bh + 0.6, stroke_width=0, fill_color=K.col("accent"),
                          fill_opacity=1).move_to([bx - fw, by, 0])
        sheet.set_z_index(Z_MARK + 40)
        edge = Rectangle(width=0.12, height=bh + 0.6, stroke_width=0, fill_color=K.col("card"), fill_opacity=1)
        edge.next_to(sheet, RIGHT, buff=0)
        edge.set_z_index(Z_MARK + 40)
        wipe = VGroup(sheet, edge)
        _flat(wipe)
        self.add(wipe)
        run = K.t("fast")
        anim = wipe.animate(rate_func=ease_out_cubic).move_to([bx, by, 0])
        self.play(K.timed(anim.build(), run, "swish"), run_time=run)
        self.remove(*old)
        self.play(wipe.animate(rate_func=ease_in_cubic).move_to([bx + fw, by, 0]), run_time=run)
        self.remove(wipe)
        self._lead += 2 * run

    def _wait_until(self, elapsed: float, until: float, swaps) -> float:
        # A transition played at the line's start took its time from the line: the line's clock counts it.
        if self._lead:
            elapsed += self._lead
            self._lead = 0.0
        return super()._wait_until(elapsed, until, swaps)

    def _cue_plan(self, given: list, extra: list, seconds: float, default: float) -> list:
        """As the engine's, each animation given the time it asked for (panim_run) instead of a blanket one."""
        fixed = []
        for anim, cue in given:
            run = getattr(anim, "panim_run", None)
            if run is not None and isinstance(cue, (list, tuple)) and cue:
                cue = [cue[0], float(run)]
            elif run is not None and not cue:
                cue = [0.0, float(run)]
            fixed.append((anim, cue))
        return super()._cue_plan(fixed, extra, seconds, default)

    def _pointers(self, words, seconds: float, hinted: set) -> list:
        """The engine's pointing at things the line names again, done the look's way for a template's part."""
        out = []
        coming = self.__dict__.get("_m_arriving") or set()
        for anim, cue in super()._pointers(words, seconds, hinted):
            mob = getattr(anim, "mobject", None)
            if mob is not None and any(id(x) in coming for x in mob.get_family()):
                # Brought on by this line (an event on its date, said here): a pulse on it as well fought its
                # entrance, and the flag never showed.
                continue
            point = getattr(mob, "_m_point", None)
            if point is not None and type(anim).__name__ == "ScaleInPlace":
                made = point()
                if made is not None:
                    out.append((made, [cue[0], float(getattr(made, "panim_run", 0.7))]))
                    continue
            out.append((anim, cue))
        return out

    # ---------------------------------------------------------------- template plumbing ---------------------------
    def _part(self, tid: str, name, mob, point=None) -> None:
        """A named part of a template: pointed at (point(), or a pulse) when a later line says its name."""
        if not str(name or "").strip():
            return
        self._mparts.setdefault(tid, {})[_slug(name)] = mob
        mob._m_point = point or (lambda m=mob: K.pulse(m, 1.1))
        self.name_part(str(name), mob)

    def _box(self, title: bool = False) -> tuple:
        """Where a template goes: the stage, less the band its title takes."""
        cx, cy, w, h = self.STAGE
        if title:
            return (cx, cy - TITLE_ROOM / 2, w, h - TITLE_ROOM)
        return (cx, cy, w, h)

    def _fit(self, mob, box, grow: float = 1.0, margin: float = 0.25):
        cx, cy, w, h = box
        k = min((w - margin) / max(mob.width, 0.01), (h - margin) / max(mob.height, 0.01), grow)
        if k < 1 or grow > 1:
            mob.scale(k)
        mob.move_to([cx, cy, 0])
        return mob

    def _titled(self, body, title: str | None, kicker: str | None = None):
        """A template under its title: a kicker (the mono line) and/or a heading over it, left-aligned to it.
        Returns (whole, the title's group or None)."""
        heads = []
        if kicker:
            heads.append(K.kicker(kicker, 18))
        if title:
            heads.append(K.head(title, 30))
        if not heads:
            return body, None
        top = VGroup(*heads).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
        whole = K.group_of(top, body)
        top.next_to(body, UP, buff=0.35).align_to(body, LEFT)
        return whole, top

    def _title_in(self, top):
        if top is None:
            return None
        anims = []
        for m in top:
            anims.append(K.typewriter(m, run=min(1.0, K.t("base") * 1.4)) if self.M.get("enter") != "write"
                         else K.write(m, run=K.t("base")))
        return K.stagger(anims, lag=0.4)

    def _show(self, tid: str, whole, entrance, on: str | None = None, idle: bool = True):
        """Put a template on the stage with its choreography; it keeps idling while up."""
        whole.set_z_index(Z_TEMPLATE)
        if idle:
            K.idle(whole)
        anim = self._to_stage(whole, entrance=entrance)
        self._settle_z(whole)
        if anim is not None and on:
            anim.panim_said = str(on)
        return anim

    @staticmethod
    def _settle_z(mob) -> None:
        """Parts that sit under the rest (a highlighter's stroke under its words, a page under its text): set below
        the template's level once the stage has set everything to it."""
        for x in mob.get_family():
            off = x.__dict__.get("_z_offset")
            if off is not None:
                x.set_z_index(Z_TEMPLATE + float(off))

    def _stage_add(self, mob):
        out = super()._stage_add(mob)
        self._settle_z(mob)
        return out

    def _on_words(self, given: list, words, seconds: float, text: str) -> list:
        """The engine's; a moment that may be said in more than one way (an event by its words or by its date) is
        timed by whichever the line says."""
        self._m_arriving = set()
        if words:
            for anim, _ in given:
                alts = getattr(anim, "panim_alts", None)
                if alts:
                    heard = [(self._said(words, a), a) for a in alts]
                    heard = [(t_, a) for t_, a in heard if t_ is not None]
                    if heard:
                        anim.panim_said = min(heard)[1]
        return super()._on_words(given, words, seconds, text)

    def _moment(self, say, build, run: float | None = None) -> None:
        """Something that happens when the line says `say` (or, said nowhere, in its turn after the template); `say`
        may be a list of ways the line may say it."""
        alts = [str(x) for x in say if str(x or "").strip()] if isinstance(say, (list, tuple)) else None
        if alts:
            say = alts[0]
        def made(heard):
            anim = build(heard)
            # Parts held back until now (a chain's next step) are the stage's from now on: they leave with it.
            if anim is not None:
                within = set()
                todo = [anim]
                while todo:
                    a = todo.pop()
                    todo.extend(getattr(a, "animations", None) or [])
                    if getattr(a, "mobject", None) is not None:
                        within.update(id(x) for x in a.mobject.get_family())
                for m in list(self.stage_pending):
                    if any(id(x) in within for x in m.family_members_with_points()):
                        self.stage_pending.remove(m)
                        self.stage_extra.append(m)
                # Coming on in this line: not pointed at in it too (_pointers).
                self.__dict__.setdefault("_m_arriving", set()).update(within)
            if anim is not None and run is not None and getattr(anim, "panim_run", None) is None:
                K.timed(anim, run)
            return anim
        self.queue_on_words(str(say or ""), made)
        if alts and len(alts) > 1:
            self.__dict__["_word_queue"][-1].panim_alts = alts

    # ================================================================ templates =====================================

    # ---------------------------------------------------------------- a headline ----------------------------------
    def m_title(self, text: str, kicker: str | None = None, sub: str | None = None, highlight: str | None = None,
                id: str | None = None):
        """A headline on its own: big words rising in one after another, a highlight block drawn behind one word,
        a kicker typed over it and a line under it."""
        tid = id or self._next_id("title")
        words = str(text).split()
        size = 80 if len(text) < 22 else 68 if len(text) < 40 else 54
        line_words = []
        for w in words:
            line_words.append(K.head(w, size))
        lines, row, width = [], [], 0.0
        limit = min(self.STAGE[2] - 1.0, 9.5)
        for m in line_words:
            if row and width + m.width + 0.25 > limit:
                lines.append(row)
                row, width = [], 0.0
            row.append(m)
            width += m.width + 0.25
        if row:
            lines.append(row)
        block = VGroup(*[VGroup(*r).arrange(RIGHT, buff=0.25, aligned_edge=DOWN) for r in lines]).arrange(
            DOWN, buff=0.2, aligned_edge=LEFT)
        parts = [block]
        top = K.kicker(kicker, 20, K.col("accent") if self.M.get("classic") else None) if kicker else None
        if top is not None:
            top.next_to(block, UP, buff=0.3, aligned_edge=LEFT)
            parts.insert(0, top)
        low = K.body(sub, 26, pl.P.MUTED, 50) if sub else None
        if low is not None:
            low.next_to(block, DOWN, buff=0.35, aligned_edge=LEFT)
            parts.append(low)
        whole = VGroup(*parts)
        self._fit(whole, self._box(), grow=1.15, margin=1.0)
        lit = None
        if highlight:
            target = [m for m in line_words if _slug(m.text if hasattr(m, "text") else "") in _slug(highlight)
                      or _slug(highlight) in _slug(getattr(m, "text", ""))]
            if target:
                lit = K.highlighter(VGroup(*target))
                whole.add_to_back(lit)
                # The marked words in the board's own dark or light, to read on the highlighter.
                ink = "#111111" if pl._luminance(lit.get_stroke_color().to_hex()) > 0.35 else "#FFFFFF"
                for m in target:
                    m.set_color(ink)
        rule = K.underline(block, K.col("accent"), 7) if not lit else None
        if rule is not None:
            whole.add(rule)
        anims = []
        if top is not None:
            anims.append(K.typewriter(top, run=0.6))
        anims.append(K.stagger([K.timed(FadeIn(m, shift=UP * 0.45, rate_func=ease_out_back), K.t("base"))
                                for m in line_words], lag=0.25))
        if lit is not None:
            anims.append(K.draw(lit, run=K.t("base")))
        if rule is not None:
            anims.append(K.draw(rule, run=K.t("base")))
        if low is not None:
            anims.append(K.enter(low, "rise"))
        entrance = K.stagger(anims, lag=0.55)
        for m in line_words:
            self._part(tid, getattr(m, "text", ""), m)
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- a figure counting up ------------------------
    def m_counter(self, value: str, label: str = "", kicker: str | None = None, delta: str | None = None,
                  trend: str | None = None, color: str | None = None, sub: str | None = None,
                  start: float = 0.0, id: str | None = None):
        """A big figure counting up to its value, its kicker typed over it, its label rising under it, and a change
        (▲ +50%) popping beside it."""
        tid = id or self._next_id("counter")
        tone = pl.role(color) if color else K.col("accent")

        def make(words):
            return K.number(words, 120, tone)

        num = K.counter(str(value), make, start=start)
        parts = [num]
        top = K.kicker(kicker, 22) if kicker else None
        lab = K.body(label, 30, pl.P.CREAM, 40) if label else None
        if lab is not None:
            lab.next_to(num, DOWN, buff=0.3)
        change = None
        if delta:
            up = (trend or ("down" if str(delta).strip().startswith(("-", "−")) else "up")) != "down"
            arrow = Triangle(fill_color=K.col("good" if up else "bad"), fill_opacity=1, stroke_width=0).scale(0.16)
            if not up:
                arrow.rotate(math.pi)
            words = K.number(str(delta), 44, K.col("good" if up else "bad"))
            change = VGroup(arrow, words).arrange(RIGHT, buff=0.12)
            change.next_to(num, RIGHT, buff=0.45).align_to(num, DOWN)
        whole = VGroup(*[m for m in (top, num, change, lab) if m is not None])
        if top is not None:
            top.next_to(num, UP, buff=0.3)
        if sub:
            low = K.body(sub, 22, pl.P.MUTED, 50)
            low.next_to(lab if lab is not None else num, DOWN, buff=0.22)
            whole.add(low)
        self._fit(whole, self._box(), grow=1.1, margin=0.8)
        count = num.count_anim(run=K.t("slow") * 1.3, centre=True)
        anims = [K.typewriter(top, run=0.6) if top is not None else None,
                 count if count is not None else K.enter(num, "pop")]
        if lab is not None:
            anims.append(K.enter(lab, "rise"))
        if change is not None:
            anims.append(K.timed(FadeIn(change, scale=0.4, rate_func=ease_out_back), K.t("fast"), "pop"))
        if sub:
            anims.append(K.enter(whole[-1], "fade"))
        entrance = K.stagger(anims, lag=0.5)
        self._part(tid, label, num, point=lambda: K.pulse(num, 1.08))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- charts -------------------------------------
    def m_chart(self, items, kind: str = "column", title: str | None = None, kicker: str | None = None,
                unit: str = "", highlight=None, reference=None, colors=None, marks=None, source: str | None = None,
                id: str | None = None, values=None):
        """A chart that builds itself. items: [[label, value], ...] or [{label, value, on?, color?, note?}].

        column  the baseline drawn, the columns rising from it one after another, each value popping over its
                column, the labels under them; the `highlight` column in the accent, the rest muted. A `reference`
                ({value, label}) is a dashed line drawn across at its value, its label at its end.
        bar     the same lying down: a track for each, the bar sweeping out along it, the value at its end.
        line    the axes, then the line drawn left to right with a dot riding its end and the last value beside
                it; `marks` ([{at, label}]) are dashed lines down at those x values, each labelled.
        Each item comes up again (its column lit) when a later line names it; with `on`, it is lit as said."""
        tid = id or self._next_id("chart")
        rows = []
        for it in items or []:
            if isinstance(it, dict):
                rows.append({"label": str(it.get("label", "")), "value": float(it.get("value", 0) or 0),
                             "on": it.get("on"), "color": it.get("color"), "note": it.get("note"),
                             "text": it.get("text")})
            elif isinstance(it, (list, tuple)) and len(it) >= 2:
                rows.append({"label": str(it[0]), "value": float(it[1] or 0), "on": None, "color": None,
                             "note": None, "text": None})
        rows = rows[:12]
        if not rows:
            return None
        hl = {_slug(h) for h in (highlight if isinstance(highlight, (list, tuple)) else [highlight]) if h}
        if kind == "line":
            return self._line_chart(tid, rows, title, kicker, unit, reference, marks, source)
        if kind == "bar":
            return self._bar_chart(tid, rows, title, kicker, unit, hl, reference, source)
        return self._column_chart(tid, rows, title, kicker, unit, hl, reference, source)

    def _value_text(self, row, unit: str) -> str:
        if row.get("text"):
            return str(row["text"])
        v = row["value"]
        words = f"{v:,.0f}" if abs(v) >= 1000 and float(v).is_integer() else f"{v:g}"
        return f"{words}{unit}"

    def _column_chart(self, tid, rows, title, kicker, unit, hl, reference, source):
        P = pl.P
        n = len(rows)
        top_v = max([r["value"] for r in rows] + ([float(reference.get("value", 0))] if isinstance(reference, dict) else []))
        top_v = top_v or 1.0
        H, slot = 3.6, min(1.25, 10.5 / n)
        bw = slot * 0.62
        width = slot * n
        base = Line([-width / 2 - 0.2, 0, 0], [width / 2 + 0.2, 0, 0], stroke_color=P.CREAM, stroke_width=3)
        cols, values, labels = VGroup(), VGroup(), VGroup()
        muted = K.col("second") if not self.M.get("classic") else P.MUTED
        for k, r in enumerate(rows):
            x = -width / 2 + slot * (k + 0.5)
            lit = _slug(r["label"]) in hl
            tone = pl.role(r["color"]) if r.get("color") else (K.col("accent") if lit or not hl and False else muted)
            if not hl and not r.get("color"):
                tone = K.col("accent") if k == max(range(n), key=lambda i: rows[i]["value"]) else muted
            hgt = max(0.04, H * r["value"] / top_v)
            col = Rectangle(width=bw, height=hgt, stroke_color=P.CREAM if lit else tone,
                            stroke_width=3 if lit else 0, fill_color=tone, fill_opacity=1)
            col.move_to([x, hgt / 2, 0])
            val = K.number(self._value_text(r, unit), 30 if lit else 24, P.CREAM if not lit else P.TITLE)
            fit(val, slot * 0.92)
            val.next_to(col, UP, buff=0.1)
            lab = fit(pl.T(str(r["label"]), 19, P.CREAM, weight=BOLD), slot * 0.95)
            lab.next_to([x, 0, 0], DOWN, buff=0.18)
            cols.add(col)
            values.add(val)
            labels.add(lab)
        chart = VGroup(base, cols, values, labels)
        ref = None
        if isinstance(reference, dict) and reference.get("value") is not None:
            y = H * float(reference["value"]) / top_v
            dash = DashedLine([-width / 2 - 0.2, y, 0], [width / 2 + 0.4, y, 0], dash_length=0.12,
                              stroke_color=P.CREAM, stroke_width=2.5, stroke_opacity=0.85)
            tag = K.kicker(str(reference.get("label", "")), 17, P.CREAM).next_to(dash, RIGHT, buff=0.15)
            ref = VGroup(dash, tag)
            chart.add(ref)
        whole, top = self._titled(chart, title, kicker)
        if source:
            note = pl.T(str(source).upper(), 12, P.MUTED, fine=True).next_to(chart, DOWN, buff=0.35).align_to(chart, LEFT)
            whole.add(note)
        self._fit(whole, self._box(), grow=1.2)
        lag = 0.14 if n > 4 else 0.25
        grow = K.stagger([K.grow_from(c, DOWN, run=K.t("slow") * 0.8) for c in cols], lag=lag)
        pops = K.stagger([K.timed(FadeIn(v, shift=UP * 0.15, rate_func=ease_out_back), K.t("fast"), "pop")
                          for v in values], lag=lag)
        labs = K.stagger([K.enter(lb, "rise", run=K.t("fast")) for lb in labels], lag=lag * 0.6)
        anims = [self._title_in(top), K.draw(base, run=K.t("fast")),
                 K.stagger([grow, pops], lag=0.55), labs]
        if ref is not None:
            anims.append(K.chain([K.draw(ref[0], run=K.t("base")), K.enter(ref[1], "pop", run=K.t("fast"))]))
        entrance = K.stagger([a for a in anims if a is not None], lag=0.4)
        for k, r in enumerate(rows):
            bar = VGroup(cols[k], values[k], labels[k])

            def point(k=k):
                return K.together([K.pulse(cols[k], 1.06), K.pulse(values[k], 1.25)], run=K.t("base"))
            self._part(tid, r["label"], bar, point=point)
            if r.get("on"):
                self._moment(r["on"], lambda heard, k=k: K.together([K.refill(cols[k], K.col("accent")),
                                                                     K.pulse(cols[k], 1.06)]) if heard else None)
        return self._show(tid, whole, entrance)

    def _bar_chart(self, tid, rows, title, kicker, unit, hl, reference, source):
        P = pl.P
        n = len(rows)
        top_v = max(r["value"] for r in rows) or 1.0
        full, thick = 7.4, min(0.5, 3.8 / n)
        muted = K.col("second") if not self.M.get("classic") else P.MUTED
        lines = VGroup()
        bars, nums = [], []
        biggest = max(range(n), key=lambda i: rows[i]["value"])
        for k, r in enumerate(rows):
            lit = _slug(r["label"]) in hl or (not hl and k == biggest)
            tone = pl.role(r["color"]) if r.get("color") else (K.col("accent") if lit else muted)
            label = fit(pl.T(str(r["label"]), 21, P.CREAM, weight=BOLD), 3.0)
            track = RoundedRectangle(corner_radius=thick / 2, width=full, height=thick, stroke_width=0,
                                     fill_color=pl._tint_on_bg(tone, 0.14), fill_opacity=1)
            bar = RoundedRectangle(corner_radius=thick / 2, width=max(thick, full * r["value"] / top_v), height=thick,
                                   stroke_width=0, fill_color=tone, fill_opacity=1)
            num = K.number(self._value_text(r, unit), 24, P.CREAM)
            lines.add(VGroup(label, track, bar, num))
            bars.append(bar)
            nums.append(num)
        lw = max(r[0].width for r in lines)
        gap = thick + 0.35
        for k, r in enumerate(lines):
            y = -k * gap
            r[0].move_to([-lw - 0.25, y, 0], aligned_edge=RIGHT)
            r[1].move_to([0, y, 0], aligned_edge=LEFT)
            r[2].move_to([0, y, 0], aligned_edge=LEFT)
            r[3].next_to(r[2], RIGHT, buff=0.18)
        whole, top = self._titled(lines, title, kicker)
        if source:
            whole.add(pl.T(str(source).upper(), 12, P.MUTED, fine=True).next_to(lines, DOWN, buff=0.3).align_to(lines, LEFT))
        self._fit(whole, self._box(), grow=1.2)
        rows_in = []
        for r in lines:
            rows_in.append(K.together([K.enter(r[0], "rise", run=K.t("fast")), K.enter(r[1], "fade", run=K.t("fast")),
                                       K.chain([K.grow_from(r[2], LEFT, run=K.t("slow")),
                                                K.timed(FadeIn(r[3], shift=LEFT * 0.2, rate_func=ease_out_back),
                                                        K.t("fast"), "pop")])]))
        entrance = K.stagger([self._title_in(top), K.stagger(rows_in, lag=0.3)], lag=0.5)
        for k, rw in enumerate(rows):
            row = lines[k]
            self._part(tid, rw["label"], row, point=lambda k=k: K.together(
                [K.pulse(bars[k], 1.05), K.pulse(nums[k], 1.25)], run=K.t("base")))
            if rw.get("on"):
                self._moment(rw["on"], lambda heard, k=k: K.refill(bars[k], K.col("accent")) if heard else None)
        return self._show(tid, whole, entrance)

    def _line_chart(self, tid, rows, title, kicker, unit, reference, marks, source):
        P = pl.P
        xs = list(range(len(rows)))
        try:
            xs_num = [float(r["label"]) for r in rows]
            if len(set(xs_num)) == len(xs_num):
                xs = xs_num
        except ValueError:
            pass
        ys = [r["value"] for r in rows]
        lo, hi = min(ys), max(ys)
        lo = min(lo, 0) if lo >= 0 and lo < hi * 0.4 else lo - (hi - lo) * 0.1
        hi = hi + (hi - lo) * 0.08
        W_, H_ = 9.0, 3.8
        x0, x1 = min(xs), max(xs)

        def at(x, y):
            return np.array([-W_ / 2 + (x - x0) / max(x1 - x0, 1e-9) * W_, -H_ / 2 + (y - lo) / max(hi - lo, 1e-9) * H_, 0])

        axis = VGroup(Line(at(x0, lo), at(x1, lo) + RIGHT * 0.2, stroke_color=P.MUTED, stroke_width=2.5),
                      Line(at(x0, lo), at(x0, hi), stroke_color=P.MUTED, stroke_width=2.5))
        grid = VGroup()
        for k in range(1, 4):
            y = lo + (hi - lo) * k / 4
            grid.add(Line(at(x0, y), at(x1, y), stroke_color=P.MUTED, stroke_width=1, stroke_opacity=0.35))
            grid.add(pl.T(f"{y:,.0f}" if abs(hi) >= 100 else f"{y:.2g}", 14, P.MUTED, fine=True).next_to(at(x0, y), LEFT, buff=0.12))
        ticks = VGroup()
        step = max(1, len(rows) // 6)
        for k in range(0, len(rows), step):
            ticks.add(pl.T(str(rows[k]["label"]), 15, P.MUTED).next_to(at(xs[k], lo), DOWN, buff=0.12))
        tone = K.col("accent")
        curve = VMobject(stroke_color=tone, stroke_width=6).set_points_as_corners([at(x, y) for x, y in zip(xs, ys)])
        dot = Dot(at(xs[0], ys[0]), radius=0.11, color=tone)
        halo = Circle(radius=0.22, stroke_width=0, fill_color=tone, fill_opacity=0.3).move_to(dot)
        end_val = K.number(self._value_text(rows[-1], unit), 28, tone).next_to(at(xs[-1], ys[-1]), RIGHT, buff=0.25)
        chart = VGroup(grid, axis, ticks, curve, halo, dot, end_val)
        bands = VGroup()
        for m in marks or []:
            if not isinstance(m, dict) or m.get("at") is None:
                continue
            try:
                xv = float(m["at"])
            except (TypeError, ValueError):
                continue
            if not x0 <= xv <= x1:
                continue
            dash = DashedLine(at(xv, lo), at(xv, hi), dash_length=0.1, stroke_color=P.CREAM, stroke_width=2,
                              stroke_opacity=0.8)
            tag = K.kicker(str(m.get("label", "")), 15, P.CREAM).next_to(dash, UP, buff=0.08)
            bands.add(VGroup(dash, tag))
        chart.add(bands)
        whole, top = self._titled(chart, title, kicker)
        if source:
            whole.add(pl.T(str(source).upper(), 12, P.MUTED, fine=True).next_to(chart, DOWN, buff=0.3).align_to(chart, LEFT))
        self._fit(whole, self._box(), grow=1.2)
        # The line drawn with its dot riding the end (baked: a dot following a curve as it is drawn).
        run = max(K.t("slow") * 2.0, 1.4)

        def ride(mob, alpha):
            mob.move_to(curve.point_from_proportion(min(max(rush_from(alpha), 0.0), 1.0)))

        rider = VGroup(halo, dot)
        drawing = K.chain([K.timed(FadeIn(rider, scale=0.3, rate_func=ease_out_back), K.t("fast"), "pop"),
                           K.together([K.timed(Create(curve, rate_func=rush_from), run),
                                       K.baked(K.timed(UpdateFromAlphaFunc(rider, ride, rate_func=linear), run))],
                                      run=run)])
        anims = [self._title_in(top), K.together([K.draw(axis, run=K.t("base")), K.enter(grid, "fade"),
                                                 K.enter(ticks, "fade")]),
                 drawing, K.timed(FadeIn(end_val, shift=LEFT * 0.2, rate_func=ease_out_back), K.t("fast"), "pop")]
        if len(bands):
            anims.append(K.stagger([K.chain([K.draw(b[0], run=K.t("base")), K.enter(b[1], "pop", run=K.t("fast"))])
                                    for b in bands], lag=0.5))
        entrance = K.stagger([a for a in anims if a is not None], lag=0.5)
        self._part(tid, rows[-1]["label"], end_val)
        for b, m in zip(bands, [m for m in marks or [] if isinstance(m, dict)]):
            self._part(tid, m.get("label"), b)
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- a grid of units ----------------------------
    def m_units(self, total: int = 100, groups=None, title: str | None = None, kicker: str | None = None,
                unit: str = "", cols: int | None = None, fly=None, id: str | None = None):
        """A grid of small units (bonds, people, tonnes), popping in in a wave from the corner; each group then
        coloured as it is said, its label stamped beside the grid; `fly` ({n, label, on}) sends the last n units
        flying off to one side in a loose pile, labelled."""
        P = pl.P
        tid = id or self._next_id("units")
        self._unit_tags = []
        total = int(max(1, min(int(total or 100), 400)))
        cols = int(cols or (10 if total <= 120 else 20))
        rows_n = math.ceil(total / cols)
        size = min(0.62, 7.0 / cols, 4.4 / rows_n)
        tile_w, tile_h = size * 1.25, size * 0.68
        tiles = VGroup()
        plain = K.col("card")
        for k in range(total):
            r, c = divmod(k, cols)
            tile = RoundedRectangle(corner_radius=0.03, width=tile_w * 0.86, height=tile_h * 0.8, stroke_width=1,
                                    stroke_color=K.col("card_stroke"), fill_color=plain, fill_opacity=1)
            tile.move_to([c * tile_w, -r * tile_h, 0])
            if unit and total <= 60:
                word = pl.T(str(unit).upper(), 11, K.col("card_ink"), fine=True)
                fit(word, tile_w * 0.6)
                word.move_to(tile)
                tile = VGroup(tile, word)
            tiles.add(tile)
        grid = VGroup(tiles)
        whole, top = self._titled(grid, title, kicker)
        pile = None
        fly_n = 0
        if isinstance(fly, dict) and int(fly.get("n", 0) or 0) > 0:
            fly_n = min(int(fly["n"]), total)
        if fly_n:
            room = VGroup(*[Rectangle(width=tile_w, height=tile_h) for _ in range(min(fly_n, 12))])
            room.arrange_in_grid(cols=2, buff=0.15).next_to(grid, RIGHT, buff=1.4)
            pile = room
            pile = VGroup(*[m.copy().set_opacity(0) for m in room])
            whole.add(pile)
        self._fit(whole, self._box(), grow=1.3)
        # In a wave from the top-left corner, row by row with the columns overlapping.
        wave = K.stagger([K.timed(FadeIn(t_, scale=0.3, rate_func=ease_out_back), K.t("fast")) for t_ in tiles],
                         run=min(2.6, 0.9 + 0.012 * total), lag=0.06 if total > 60 else 0.12)
        entrance = K.stagger([self._title_in(top), wave], lag=0.6)
        start = 0
        for g in groups or []:
            if not isinstance(g, dict):
                continue
            n = int(g.get("n", 0) or 0)
            members = VGroup(*tiles[start:start + n])
            start += n
            if not len(members):
                continue
            tone = pl.role(g["color"]) if g.get("color") else K.col("accent")
            label = K.chip(str(g.get("label", "")), tone, K.col("accent_ink"), 20) if g.get("label") else None
            if label is not None:
                # Under the grid, from where its units start; a second group's beside the first's.
                label.next_to(grid, DOWN, buff=0.25).align_to(members, LEFT)
                taken = [m for m in self.__dict__.get("_unit_tags", []) if m.get_right()[0] + 0.2 > label.get_left()[0]
                         and abs(m.get_center()[1] - label.get_center()[1]) < 0.1]
                if taken:
                    label.next_to(taken[-1], RIGHT, buff=0.3)
                self.__dict__.setdefault("_unit_tags", []).append(label)
                label.set_z_index(Z_TEMPLATE + 2)

            def colour(heard, members=members, tone=tone, label=label):
                fills = [K.timed(K.fresh(m.animate.set_fill(tone, opacity=1).build() if isinstance(m, VMobject) and
                                         not isinstance(m, VGroup) else m[0].animate.set_fill(tone, opacity=1).build()),
                                 K.t("fast")) for m in members]
                anims = [K.stagger(fills, run=min(1.4, 0.4 + 0.01 * len(fills)), lag=0.05)]
                if label is not None:
                    self._stage_add(label)
                    anims.append(K.slam(label) if not self.M.get("classic") else K.enter(label, "pop"))
                return K.chain(anims)
            self._moment(g.get("on") or g.get("label"), colour)
            self._part(tid, g.get("label"), members, point=lambda members=members: K.pulse(members, 1.04))
        if fly_n and pile is not None:
            movers = list(tiles[total - fly_n:])
            spots = [s.get_center() for s in pile]
            rng = np.random.default_rng(3)
            tag = K.chip(str(fly.get("label", "")), K.col("accent"), K.col("accent_ink"), 22) if fly.get("label") else None
            if tag is not None:
                tag.next_to(pile, DOWN, buff=0.35)
                tag.set_z_index(Z_TEMPLATE + 2)

            def away(heard, movers=movers, spots=spots, tag=tag):
                moves = []
                for k, m in enumerate(movers):
                    spot = spots[k % len(spots)] + np.array([rng.uniform(-0.08, 0.08), rng.uniform(-0.06, 0.06), 0])
                    a = m.animate(rate_func=ease_out_expo).move_to(spot).rotate(rng.uniform(-0.25, 0.25)).build()
                    moves.append(K.timed(a, K.t("base")))
                anims = [K.stagger(moves, lag=0.08)]
                if tag is not None:
                    self._stage_add(tag)
                    anims.append(K.enter(tag, "pop"))
                return K.chain(anims)
            self._moment(fly.get("on") or fly.get("label"), away)
        return self._show(tid, whole, entrance, idle=False)

    # ---------------------------------------------------------------- cards dealt in a row -----------------------
    def m_cards(self, items, title: str | None = None, kicker: str | None = None, stamp=None, id: str | None = None):
        """Cards dealt in from below one after another, each turned a little: a picture (or a big word) and its
        title; a mark on a card (check, cross or a word stamped) lands as it is said; `stamp` ({text, on}) slams
        across them all."""
        P = pl.P
        tid = id or self._next_id("cards")
        specs = [it if isinstance(it, dict) else {"title": str(it)} for it in (items or [])][:6]
        if not specs:
            return None
        n = len(specs)
        cw = min(2.9, 11.5 / n - 0.35)
        ch = cw * 1.25
        cards = []
        rng = np.random.default_rng(5)
        for k, s in enumerate(specs):
            face = K.card(cw, ch)
            inner = []
            pic = None
            if s.get("file"):
                try:
                    path, _ = motion_looks.dress(str(s["file"]), "plain")
                    pic = ImageMobject(path)
                    pic.scale_to_fit_width(cw * 0.78)
                    if pic.height > ch * 0.58:
                        pic.scale_to_fit_height(ch * 0.58)
                except Exception:  # noqa: BLE001 -- a card without its picture
                    pic = None
            if pic is None and s.get("big"):
                pic = K.number(str(s["big"]), 54, K.col("card_ink"))
                fit(pic, cw * 0.8)
            name = fit(K.head(str(s.get("title", "")), 24, K.col("card_ink")), cw * 0.86)
            sub = fit(pl.T(str(s.get("sub")), 16, K.col("card_ink")), cw * 0.86) if s.get("sub") else None
            stack = [m for m in (pic, name, sub) if m is not None]
            content = Group(*stack).arrange(DOWN, buff=0.18) if any(isinstance(m, ImageMobject) for m in stack) \
                else VGroup(*stack).arrange(DOWN, buff=0.18)
            content.move_to(face.face)
            if content.height > ch * 0.92:
                content.scale(ch * 0.92 / content.height)
            whole_card = K.group_of(face, content)
            whole_card.rotate((rng.uniform(1.5, 4.0) * (-1 if k % 2 else 1)) * math.pi / 180)
            cards.append((s, whole_card))
        row = Group(*[c for _, c in cards]).arrange(RIGHT, buff=0.35)
        whole, top = self._titled(row, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        deal = K.stagger([K.timed(FadeIn(c, shift=UP * 1.4, rate_func=ease_out_back), K.t("base"), "swish")
                          for _, c in cards], lag=0.3)
        entrance = K.stagger([self._title_in(top), deal], lag=0.6)
        for s, c in cards:
            self._part(tid, s.get("title"), c, point=lambda c=c: K.pulse(c, 1.05))
            mark = s.get("mark")
            if mark:
                if mark in ("check", "yes", "tick"):
                    sign = K.check_mark(0.55)
                elif mark in ("cross", "no", "x"):
                    sign = K.cross_mark(0.5)
                else:
                    sign = K.stamp(str(mark), size=22, angle=-14)
                    fit(sign, c.width * 0.95)
                sign.move_to(c.get_center() + UP * c.height * 0.12)
                sign.set_z_index(Z_TEMPLATE + 3)

                def land(heard, sign=sign, mark=mark):
                    self._stage_add(sign)
                    if mark in ("check", "yes", "tick", "cross", "no", "x"):
                        return K.draw(sign, run=K.t("fast"), sfx="tick")
                    return K.slam(sign)
                self._moment(s.get("on") or s.get("title"), land)
        if isinstance(stamp, dict) and stamp.get("text"):
            big = K.stamp(str(stamp["text"]), size=54, angle=-9)
            big.scale_to_fit_width(min(row.width * 0.6, 7.0))
            big.move_to(row)
            big.set_z_index(Z_TEMPLATE + 4)

            def slam(heard, big=big):
                self._stage_add(big)
                return K.slam(big)
            self._moment(stamp.get("on") or stamp["text"], slam)
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- a stamp --------------------------------------
    def m_stamp(self, text: str, color: str | None = None, angle: float = -10, at: str = "center"):
        """A rubber stamp slammed onto what is up ("CLEARED", "DEFAULT"), with a thud; alone, on the board."""
        mark = K.stamp(str(text), pl.role(color) if color else None, angle=angle, size=60)
        body = self.stage_body
        if body is not None:
            fit(mark, max(2.0, body.width * 0.7))
            spot = {"center": body.get_center(), "top": body.get_top() + DOWN * mark.height * 0.7,
                    "bottom": body.get_bottom() + UP * mark.height * 0.7, "right": body.get_right() + LEFT * mark.width * 0.6,
                    "left": body.get_left() + RIGHT * mark.width * 0.6}.get(at, body.get_center())
            mark.move_to(spot)
            mark.set_z_index(Z_TEMPLATE + 5)
            self._stage_add(mark)
            return K.chain([K.slam(mark), K.shake(body, run=K.t("fast"))]) if not isinstance(body, Group) or \
                isinstance(body, VGroup) else K.slam(mark)
        self._fit(mark, self._box(), grow=1.0, margin=3)
        return self._show(self._next_id("stamp"), mark, K.slam(mark), idle=False)

    # ---------------------------------------------------------------- data cards -----------------------------------
    def m_kpi(self, cards, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """Data cards side by side (two to four): each a label in mono capitals, a big figure counting up, a change
        with its arrow (▲ green, ▼ red) and a note; dealt in one after another, each figure counting as it lands."""
        P = pl.P
        tid = id or self._next_id("kpi")
        specs = [c for c in (cards or []) if isinstance(c, dict)][:4]
        if not specs:
            return None
        n = len(specs)
        cw = min(4.2, 12.0 / n - 0.3)
        ch = 3.2
        made, counts = [], []
        for s in specs:
            face = K.card(cw, ch)
            label = fit(K.kicker(str(s.get("label", "")), 18, K.col("card_ink") if not self.M.get("classic") else P.MUTED), cw - 0.5)
            tone = pl.role(s["color"]) if s.get("color") else K.col("accent")

            def make(words, tone=tone):
                return K.number(words, 66, tone)
            num = K.counter(str(s.get("value", "")), make)
            fit(num, cw - 0.5)
            stack = [label, num]
            if s.get("delta"):
                up = not str(s["delta"]).strip().startswith(("-", "−")) if s.get("trend") is None else s["trend"] != "down"
                tri = Triangle(fill_color=K.col("good" if up else "bad"), fill_opacity=1, stroke_width=0).scale(0.12)
                if not up:
                    tri.rotate(math.pi)
                d = VGroup(tri, K.number(str(s["delta"]), 30, K.col("good" if up else "bad"))).arrange(RIGHT, buff=0.1)
                stack.append(d)
            if s.get("note"):
                stack.append(fit(K.body(str(s["note"]), 18, K.col("card_ink"), 28), cw - 0.5))
            content = VGroup(*stack).arrange(DOWN, buff=0.18, aligned_edge=LEFT)
            content.move_to(face.face).align_to(face.face, LEFT).shift(RIGHT * 0.3)
            if content.height > ch - 0.4:
                content.scale((ch - 0.4) / content.height)
            made.append((s, VGroup(face, content), num, content))
        row = VGroup(*[m[1] for m in made]).arrange(RIGHT, buff=0.3)
        whole, top = self._titled(row, title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        deals = []
        for s, c, num, content in made:
            count = num.count_anim(run=K.t("slow") * 1.2)
            rest = [m for m in content if m is not num]
            deals.append(K.chain([K.timed(FadeIn(c[0], shift=UP * 0.6, rate_func=ease_out_cubic), K.t("base"), "swish"),
                                  K.together([count if count is not None else K.enter(num, "pop"),
                                              K.stagger([K.enter(m, "rise", run=K.t("fast")) for m in rest], lag=0.3)])]))
            self._part(tid, s.get("label"), c, point=lambda c=c: K.pulse(c, 1.04))
        entrance = K.stagger([self._title_in(top), K.stagger(deals, lag=0.35)], lag=0.5)
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- a chain of steps ---------------------------
    def m_chain(self, steps, title: str | None = None, kicker: str | None = None, loop: bool = False,
                id: str | None = None):
        """Steps in a row joined by arrows: each step's card pops in and the arrow to it is drawn as the line says
        it (or one after another); `loop` draws an arrow from the last back round to the first."""
        P = pl.P
        tid = id or self._next_id("chain")
        specs = [s if isinstance(s, dict) else {"label": str(s)} for s in (steps or [])][:7]
        if len(specs) < 2:
            return None
        n = len(specs)
        cw = min(2.6, 12.0 / n - 0.55)
        made = []
        for k, s in enumerate(specs):
            pic = None
            if s.get("file"):
                try:
                    pic = ImageMobject(motion_looks.dress(str(s["file"]), "plain")[0])
                    pic.scale_to_fit_height(1.3)
                    if pic.width > cw * 0.85:
                        pic.scale_to_fit_width(cw * 0.85)
                except Exception:  # noqa: BLE001
                    pic = None
            words = fit(K.head(str(s.get("label", "")), 22, K.col("card_ink")), cw - 0.3)
            num = K.chip(str(k + 1), K.col("accent"), K.col("accent_ink"), 16) if not pic else None
            inner = [m for m in (pic, words) if m is not None]
            content = Group(*inner).arrange(DOWN, buff=0.15) if pic is not None else VGroup(*inner)
            face = K.card(cw, max(1.0, content.height + 0.5))
            content.move_to(face.face)
            parts = [face, content]
            if num is not None:
                num.move_to(face.face.get_corner(UL) + RIGHT * 0.05 + DOWN * 0.05)
                parts.append(num)
            made.append((s, K.group_of(*parts)))
        row = Group(*[m for _, m in made]).arrange(RIGHT, buff=0.55)
        arrows = []
        for (_, a), (_, b) in zip(made, made[1:]):
            arrows.append(K.arrow_between(a.get_right() + RIGHT * 0.06, b.get_left() + LEFT * 0.06, K.col("accent"), width=5))
        back = None
        if loop:
            first, last = made[0][1], made[-1][1]
            back = K.arrow_between(last.get_bottom() + DOWN * 0.08, first.get_bottom() + DOWN * 0.08, K.col("accent"),
                                   curve=-1.0, width=4)
        whole_parts = [row, *arrows] + ([back] if back is not None else [])
        body = Group(*whole_parts)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.4)
        first_in = K.enter(made[0][1], "pop")
        entrance = K.stagger([self._title_in(top), first_in], lag=0.6)
        for k, (s, m) in enumerate(made):
            self._part(tid, s.get("label"), m, point=lambda m=m: K.pulse(m, 1.06))
            if k == 0:
                continue
            arrow = arrows[k - 1]

            def step(heard, m=m, arrow=arrow, last=(k == n - 1)):
                anims = [K.draw(arrow, run=K.t("fast")), K.enter(m, "pop", run=K.t("base"))]
                if last and back is not None:
                    anims.append(K.draw(back, run=K.t("base")))
                return K.chain(anims)
            # Not on the stage until said: kept with the template, out of sight.
            self.stage_pending.append(m) if False else None
            self._moment(s.get("on") or s.get("label"), step)
        hidden = [m for _, m in made[1:]] + arrows + ([back] if back is not None else [])
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, hidden)
        return anim

    def _hold_back(self, whole, hidden) -> None:
        """Parts of a template that come on later (on their words): taken out of the group the stage shows, kept as
        the stage's parts to come (they move and leave with it)."""
        for m in hidden:
            for holder in [whole, *whole.get_family()]:
                if any(m is x for x in getattr(holder, "submobjects", [])):
                    holder.remove(m)
            m.set_z_index(Z_TEMPLATE + 1)
            self.stage_pending.append(m)

    # ---------------------------------------------------------------- a list --------------------------------------
    def m_list(self, items, title: str | None = None, kicker: str | None = None, mark: str = "bullet",
               id: str | None = None):
        """Points that come in one at a time as they are said, each sliding in from the left with its mark (a
        bullet, its number, or a tick drawn)."""
        P = pl.P
        tid = id or self._next_id("list")
        specs = [it if isinstance(it, dict) else {"text": str(it)} for it in (items or [])][:7]
        if not specs:
            return None
        rows = []
        for k, s in enumerate(specs):
            if mark == "number":
                sign = K.chip(str(k + 1), K.col("accent"), K.col("accent_ink"), 22)
            elif mark == "check":
                sign = K.check_mark(0.38)
            else:
                sign = Square(side_length=0.2, stroke_width=0, fill_color=K.col("accent"), fill_opacity=1).rotate(math.pi / 4)
            words = K.body(str(s.get("text", "")), 30, P.CREAM, 40)
            rows.append((s, VGroup(sign, words).arrange(RIGHT, buff=0.3, aligned_edge=UP)))
            sign.align_to(words[0] if len(words.submobjects) and False else words, UP).shift(DOWN * 0.06)
        block = VGroup(*[r for _, r in rows]).arrange(DOWN, buff=0.38, aligned_edge=LEFT)
        whole, top = self._titled(block, title, kicker)
        self._fit(whole, self._box(), grow=1.6, margin=0.8)
        first = rows[0][1]
        entrance = K.stagger([self._title_in(top), self._row_in(first, mark)], lag=0.5)
        for k, (s, r) in enumerate(rows):
            self._part(tid, s.get("text"), r, point=lambda r=r: K.together([K.pulse(r[0], 1.3)]))
            if k == 0:
                continue
            self._moment(s.get("on") or s.get("text"), lambda heard, r=r: self._row_in(r, mark))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [r for _, r in rows[1:]])
        return anim

    def _row_in(self, row, mark):
        sign, words = row
        sign_in = K.draw(sign, run=K.t("fast"), sfx="tick") if mark == "check" else \
            K.timed(FadeIn(sign, scale=0.3, rate_func=ease_out_back), K.t("fast"), "pop")
        return K.together([sign_in, K.timed(FadeIn(words, shift=RIGHT * 0.5, rate_func=ease_out_expo), K.t("base"), "swish")])

    # ---------------------------------------------------------------- versus ---------------------------------------
    def m_versus(self, left: dict, right: dict, title: str | None = None, kicker: str | None = None,
                 id: str | None = None):
        """Two sides: their cards sweep in from the two edges, a VS badge slams between them, then each side's
        points come in. Each side's title is pointed at when said again."""
        P = pl.P
        tid = id or self._next_id("versus")
        sides = []
        for s, tone in ((left or {}, K.col("accent")), (right or {}, K.col("second"))):
            cw = 5.0
            name = fit(K.head(str(s.get("title", "")), 34, tone if not self.M.get("classic") else P.TITLE), cw - 0.5)
            pts = [fit(K.body("• " + str(p), 22, K.col("card_ink"), 32), cw - 0.6) for p in (s.get("points") or [])[:4]]
            big = K.number(str(s["value"]), 58, tone) if s.get("value") else None
            pic = None
            if s.get("file"):
                try:
                    pic = ImageMobject(motion_looks.dress(str(s["file"]), "plain")[0])
                    pic.scale_to_fit_height(1.6)
                except Exception:  # noqa: BLE001
                    pic = None
            stack = [m for m in (pic, name, big) if m is not None] + pts
            content = (Group if pic is not None else VGroup)(*stack).arrange(DOWN, buff=0.2)
            face = K.card(cw, max(3.2, content.height + 0.6))
            content.move_to(face.face)
            band = Rectangle(width=cw, height=0.12, stroke_width=0, fill_color=tone, fill_opacity=1)
            band.move_to(face.face.get_top() + DOWN * 0.06)
            sides.append((s, K.group_of(face, band, content), content, pts))
        lcard, rcard = sides[0][1], sides[1][1]
        pair = Group(lcard, rcard).arrange(RIGHT, buff=1.6)
        badge_c = Circle(radius=0.55, stroke_width=0, fill_color=K.col("stamp"), fill_opacity=1)
        badge = VGroup(badge_c, K.head("VS", 34, "#FFFFFF", upper=True).move_to(badge_c)).move_to(pair)
        body = Group(pair, badge)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        entrance = K.stagger([
            self._title_in(top),
            K.together([K.timed(FadeIn(lcard, shift=RIGHT * 2.5, rate_func=ease_out_expo), K.t("base"), "swish"),
                        K.timed(FadeIn(rcard, shift=LEFT * 2.5, rate_func=ease_out_expo), K.t("base"))]),
            K.slam(badge),
        ], lag=0.6)
        for s, c, content, pts in sides:
            self._part(tid, s.get("title"), c, point=lambda c=c: K.pulse(c, 1.04))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- a donut --------------------------------------
    def m_donut(self, value: float, total: float = 100, label: str = "", sub: str | None = None,
                color: str | None = None, text: str | None = None, id: str | None = None):
        """A part of a whole: a ring's track, the part swept round it, the figure counting up in the middle."""
        P = pl.P
        tid = id or self._next_id("donut")
        share = max(0.0, min(1.0, float(value) / float(total or 100)))
        tone = pl.role(color) if color else K.col("accent")
        r = 1.6
        track = Circle(radius=r, stroke_color=pl._tint_on_bg(tone, 0.18), stroke_width=34, fill_opacity=0)
        arc = Arc(radius=r, start_angle=math.pi / 2, angle=-2 * math.pi * max(share, 0.002), stroke_color=tone,
                  stroke_width=34)
        figure = text or (f"{value:g}%" if float(total or 100) == 100 else f"{value:g}")
        num = K.counter(str(figure), lambda w: K.number(w, 64, P.TITLE))
        num.move_to(ORIGIN)
        parts = [track, arc, num]
        lab = K.body(label, 26, P.CREAM, 30) if label else None
        if lab is not None:
            lab.next_to(track, RIGHT, buff=0.7)
            parts.append(lab)
        if sub:
            s = K.body(sub, 20, P.MUTED, 34)
            s.next_to(lab if lab is not None else track, DOWN, buff=0.2).align_to(lab if lab is not None else track, LEFT)
            parts.append(s)
        whole = VGroup(*parts)
        self._fit(whole, self._box(), grow=1.35, margin=0.8)
        count = num.count_anim(run=K.t("slow") * 1.4, centre=True)
        anims = [K.draw(track, run=K.t("base")),
                 K.together([K.timed(Create(arc, rate_func=ease_out_cubic), K.t("slow") * 1.4, "draw"),
                             count if count is not None else K.enter(num, "pop")], run=K.t("slow") * 1.4)]
        anims += [K.enter(m, "rise") for m in parts[3:]]
        entrance = K.stagger(anims, lag=0.5)
        self._part(tid, label, arc, point=lambda: K.pulse(arc, 1.05))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- a document, its phrases highlighted ---------
    def m_document(self, text: str, title: str | None = None, highlight=None, source: str | None = None,
                   file: str | None = None, id: str | None = None):
        """A page of words (a memoir, a law, a letter) dropped onto the board, its title over it; each phrase in
        `highlight` swept with the highlighter as the line says it (or one after another), and a picture of the
        writer beside it when one is given."""
        P = pl.P
        tid = id or self._next_id("doc")
        ink = K.col("card_ink")
        paper_w = 7.2
        heading = fit(K.head(title, 34, ink), paper_w - 0.8) if title else None
        words = pl.T(wrap(str(text), 46), 22, ink, font=K.font("body"), line_spacing=1.0)
        fit(words, paper_w - 0.8)
        stack = VGroup(*[m for m in (heading, words) if m is not None]).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        page = K.card(paper_w, stack.height + 0.9, fill="#FBF8F1" if not self.M.get("classic") else K.col("card"),
                      stroke="#E2DACA" if not self.M.get("classic") else None, radius=0.03)
        page._z_offset = -1
        stack.move_to(page.face)
        doc = VGroup(page, stack)
        if source:
            doc.add(pl.T(str(source), 14, P.MUTED, fine=True).next_to(page, DOWN, buff=0.12).align_to(page, RIGHT))
        pieces = [doc]
        pic = None
        if file:
            try:
                path, _ = motion_looks.dress(str(file), "card" if self.M.get("photo") != "polaroid" else "polaroid")
                pic = ImageMobject(path)
                pic.scale_to_fit_height(min(4.4, page.height))
                pic.rotate(-0.04)
            except Exception:  # noqa: BLE001
                pic = None
        body = Group(pic, doc).arrange(RIGHT, buff=0.5) if pic is not None else doc
        self._fit(body, self._box(), grow=1.1)
        anims = []
        if pic is not None:
            anims.append(K.timed(FadeIn(pic, shift=RIGHT * 1.0, rate_func=ease_out_expo), K.t("base"), "whoosh"))
        anims.append(K.timed(FadeIn(page, shift=UP * 0.8, rate_func=ease_out_back), K.t("base"), "swish"))
        anims.append(K.stagger([K.enter(m, "fade", run=K.t("base")) for m in stack], lag=0.4))
        if source:
            anims.append(K.enter(doc[-1], "fade", run=K.t("fast")))
        entrance = K.stagger(anims, lag=0.45)
        for phrase in (highlight if isinstance(highlight, (list, tuple)) else [highlight] if highlight else []):
            glyphs = _phrase_glyphs(words, str(text), str(phrase))
            if not glyphs:
                continue
            marks = []
            for line in _by_line(glyphs):
                marks.append(K.highlighter(VGroup(*line), "#FFD23F" if not self.M.get("classic") else None))

            def sweep(heard, marks=marks):
                for m in marks:
                    self._stage_add(m)
                return K.chain([K.draw(m, run=K.t("base") * 0.8, sfx="draw") for m in marks])
            self._moment(phrase, sweep)
            self._part(tid, phrase, VGroup(*glyphs))
        return self._show(tid, body, entrance)

    # ---------------------------------------------------------------- polaroids ------------------------------------
    def m_polaroids(self, items, title: str | None = None, kicker: str | None = None, id: str | None = None):
        """Photos dealt onto the board as prints, each turned a little and overlapping the last, captioned under;
        each one lifted and brought forward as it is said."""
        P = pl.P
        tid = id or self._next_id("prints")
        specs = [it for it in (items or []) if isinstance(it, dict) and it.get("file")][:5]
        if not specs:
            return None
        n = len(specs)
        how = "polaroid" if self.M.get("photo") in ("polaroid", "card", "tape") else self.M.get("photo", "polaroid")
        if how == "rounded":
            how = "polaroid"
        prints = []
        rng = np.random.default_rng(9)
        for k, s in enumerate(specs):
            try:
                path, box = motion_looks.dress(str(s["file"]), how)
            except Exception:  # noqa: BLE001
                continue
            img = ImageMobject(path)
            img.scale_to_fit_height(3.6 if n <= 3 else 3.0)
            parts = [img]
            if s.get("caption"):
                cap = fit(pl.T(str(s["caption"]), 22, "#2B2620", font=K.font("kicker")), img.width * 0.8)
                cap.move_to(img.get_bottom() + UP * img.height * (1 - box[3]) * 0.55)
                parts.append(cap)
            pr = Group(*parts)
            pr.rotate(rng.uniform(3, 7) * (-1 if k % 2 else 1) * math.pi / 180)
            prints.append((s, pr))
        if not prints:
            return None
        row = Group(*[p for _, p in prints]).arrange(RIGHT, buff=-0.35 if n > 3 else 0.2)
        whole, top = self._titled(row, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        for k, (_, p) in enumerate(prints):
            p.set_z_index(Z_TEMPLATE + k * 0.01)
        deal = K.stagger([K.timed(FadeIn(p, shift=UP * 1.6 + RIGHT * 0.4, scale=1.15, rate_func=ease_out_cubic),
                                  K.t("base"), "whoosh") for _, p in prints], lag=0.35)
        entrance = K.stagger([self._title_in(top), deal], lag=0.5)
        for s, p in prints:
            self._part(tid, s.get("caption"), p, point=lambda p=p: K.pulse(p, 1.07))
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- pointing on purpose ----------------------------
    def m_emphasis(self, target: str, how: str = "pulse", color: str | None = None):
        """Point at a part of a template on screen ("chart1.Japan", or a part's name alone): pulse, circle (a ring
        drawn round it), underline, highlight, box, glow, shake, or dim (the rest of its template faded back)."""
        mob, tid = self._find_part(target)
        if mob is None:
            pl.skipped(f"motion: nothing on the screen called {target!r} to point at")
            return None
        colour = pl.role(color) if color else None
        made = self._emphasis(mob, tid, how, colour)
        # The last mark goes as the next is made: one thing pointed at at a time.
        here = {id(x) for m in self.mobjects for x in m.get_family()}
        old = [m for m in self.__dict__.get("_marks", []) if id(m) in here]
        self._marks = list(getattr(made, "_m_marks", []))
        undim = [K.fade_to(m, 1.0) for m in self.__dict__.pop("_dimmed", []) if id(m) in here]
        if how == "dim":
            self._dimmed = [m for name, m in self._mparts.get(tid, {}).items() if m is not mob and isinstance(m, VMobject)]
        if undim and made is not None:
            made = K.together([*undim, made])
        if old and made is not None:
            for m in old:
                if m in self.stage_extra:
                    self.stage_extra.remove(m)
            return K.together([K.together([K.leave(m, "fade") for m in old]), made])
        return made

    def _emphasis(self, mob, tid, how: str, colour):
        def marked(anim, mark):
            if anim is not None:
                anim._m_marks = [mark]
            return anim
        if how == "circle":
            ring = K.hand_ellipse(mob, colour or K.col("stamp"))
            ring.set_z_index(Z_TEMPLATE + 4)
            self._stage_add(ring)
            return marked(K.draw(ring, run=K.t("base")), ring)
        if how == "underline":
            line = K.underline(mob, colour)
            line.set_z_index(Z_TEMPLATE + 4)
            self._stage_add(line)
            return marked(K.draw(line, run=K.t("base")), line)
        if how == "highlight":
            mark = K.highlighter(mob, colour)
            mark.set_stroke(opacity=0.5)
            mark.set_z_index(Z_TEMPLATE + 0.5)
            self._stage_add(mark)
            return marked(K.draw(mark, run=K.t("base")), mark)
        if how == "box":
            frame = pl.hud_frame(mob.width + 0.3, mob.height + 0.3, colour).move_to(mob)
            frame.set_z_index(Z_TEMPLATE + 4)
            self._stage_add(frame)
            return marked(K.timed(FadeIn(frame, scale=1.2, rate_func=ease_out_back), K.t("fast"), "tick"), frame)
        if how == "glow":
            halo = K.glow(mob if isinstance(mob, VMobject) else SurroundingRectangle(mob, buff=0.05), colour)
            halo.set_z_index(Z_TEMPLATE - 0.2)
            self._stage_add(halo)
            return marked(K.together([K.enter(halo, "fade", run=K.t("base")), K.pulse(mob, 1.06)]), halo)
        if how == "shake":
            return K.shake(mob)
        if how == "dim":
            others = [m for name, m in self._mparts.get(tid, {}).items() if m is not mob]
            return K.together([K.fade_to(m, 0.25) for m in others if isinstance(m, VMobject)] + [K.pulse(mob, 1.08)])
        return K.pulse(mob, 1.12)

    def _find_part(self, target: str):
        """A named part on the screen now (an old template's parts are gone with it)."""
        target = str(target or "")
        here = {id(x) for m in self.mobjects for x in m.get_family()}
        live = {tid: {k: m for k, m in parts.items() if any(id(x) in here for x in m.family_members_with_points())}
                for tid, parts in self._mparts.items()}
        if "." in target:
            tid, name = target.split(".", 1)
            mob = live.get(tid, {}).get(_slug(name))
            if mob is not None:
                return mob, tid
        for tid in reversed(list(live)):
            mob = live[tid].get(_slug(target.split(".")[-1]))
            if mob is not None:
                return mob, tid
        return None, None

    # ================================================================ the classic operations, in motion ============

    def board_stat(self, value: str, label: str, color: str | None = None):
        return self.m_counter(value, label, color=color)

    def board_bars(self, items, color: str | None = None, unit: str = ""):
        rows = [[str(a), float(b)] for a, b in items]
        return self.m_chart(rows, kind="column" if len(rows) <= 8 and max(len(r[0]) for r in rows) <= 12 else "bar",
                            unit=unit, highlight=None)

    def board_point(self, text: str, color: str | None = None):
        """The board's key point: a pill in the strip, popped in with the look's accent bar."""
        anim = super().board_point(text, color)
        point = self.strip.get("point")
        if anim is None or point is None:
            return anim
        return K.timed(AnimationGroup(*[a for a in getattr(anim, "animations", [anim]) if not isinstance(a, FadeIn)
                                        or getattr(a, "mobject", None) is not point],
                                      FadeIn(point, shift=RIGHT * 0.6, rate_func=ease_out_expo)), K.t("base"), "swish")

    def compare_cards(self, columns, title: str | None = None):
        cols = [c for c in columns or [] if isinstance(c, dict)]
        if len(cols) == 2 and self.board_mode:
            return self.m_versus(cols[0], cols[1], title=title)
        if self.board_mode and len(cols) >= 2:
            return self.m_cards([{"title": c.get("title"), "sub": " · ".join(c.get("points") or [])} for c in cols],
                                title=title)
        return super().compare_cards(columns, title)

    def define(self, term: str, meaning: str, entity: str | None = None):
        """A word and its meaning: the term set large with the highlighter swept under it, the meaning typed in
        under it on a card."""
        if not self.board_mode:
            return super().define(term, meaning, entity)
        P = pl.P
        word = K.head(term, 60, P.TITLE)
        mark = K.highlighter(word)
        if pl._luminance(mark.get_stroke_color().to_hex()) > 0.35:
            word.set_color("#111111")
        kick = K.kicker("Definition", 18)
        text = K.body(meaning, 30, P.CREAM, 38)
        block = VGroup(kick, VGroup(mark, word), text).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        mark.move_to(word).align_to(word, LEFT).shift(LEFT * 0.06 + DOWN * word.height * 0.15)
        self._fit(block, self._box(), grow=1.1, margin=1.2)
        block.is_text_card = True
        entrance = K.stagger([K.typewriter(kick, run=0.5), K.enter(word, "pop"), K.draw(mark, run=K.t("base")),
                              K.typewriter(text, run=min(2.0, 0.035 * len(meaning) + 0.4))], lag=0.55)
        tid = self._next_id("define")
        self._part(tid, term, word)
        beside = self._beside_picture(block)
        if beside is not None:
            return beside
        return self._show(tid, block, entrance)

    TAG_KEEP = 0.75   # a picture's label tags shrink no smaller than this when the picture moves aside

    def _move_stage(self, f: float, centre, box):
        """The engine's, but a labelled picture's tags keep a readable size (TAG_KEEP) as the picture shrinks into
        half the board: scaled with it they went to a few pixels high."""
        if f >= self.TAG_KEEP or self.M.get("classic"):
            return super()._move_stage(f, centre, box)
        tags = [piece["tag"] for view in self.__dict__.get("_views", []) if self._view_on(view)
                for piece in view["parts"].values()]
        shown = [t for t in tags if any(t is m for m in self.stage_extra)]
        waiting = [t for t in tags if any(t is m for m in self.stage_pending)]
        self.stage_extra = [m for m in self.stage_extra if all(m is not t for t in shown)]
        anim = super()._move_stage(f, centre, box)
        self.stage_extra.extend(shown)
        if anim is None and not shown:
            return anim
        centre = np.array(centre, dtype=float)
        shift = np.array([box[0], box[1], 0]) - centre
        grow = self.TAG_KEEP / f
        for tag in waiting:
            # Put there already with the picture (not shown yet): grown back about where it now sits.
            tag.scale(grow)
        slides = []
        for tag in shown:
            to = (np.array(tag.get_center(), dtype=float) - centre) * f + centre + shift
            slides.append(tag.animate.scale(self.TAG_KEEP).move_to(to))
        pl.follow_drift(shown, f, centre, shift)
        return AnimationGroup(*([anim] if anim is not None else []), *slides)

    def _beside_picture(self, card):
        """A card about the picture on the stage (a definition, a quotation) set beside it, as the engine does: the
        picture moves into the left half, its labels and the light on its parts with it, and the card takes the
        right. Put up in the picture's place, the card hid the picture the line was still talking about. None when
        no picture is up (or this beat brought one: the two are laid out together then)."""
        body = getattr(self, "stage_body", None)
        if body is None or self._beat_new or not any(isinstance(m, ImageMobject) for m in body.get_family()):
            return None
        card.set_z_index(Z_TEMPLATE)
        return self._aside(card, grow=1.2)

    def quote(self, text: str, who: str = ""):
        """A quotation: big quote marks drop in, the words typed onto a card, the speaker's name slides in."""
        if not self.board_mode:
            return super().quote(text, who)
        P = pl.P
        marks = K.head("“", 140, K.col("accent"), upper=False)
        words = K.body(text, 32, K.col("card_ink"), 44)
        name = K.kicker(f"— {who}", 20, K.col("card_ink")) if who else None
        stack = VGroup(*[m for m in (words, name) if m is not None]).arrange(DOWN, buff=0.35, aligned_edge=RIGHT)
        face = K.card(stack.width + 1.4, stack.height + 1.0)
        stack.move_to(face.face)
        marks.move_to(face.face.get_corner(UL) + RIGHT * 0.45 + DOWN * 0.15)
        whole = VGroup(face, stack, marks)
        self._fit(whole, self._box(), grow=1.1, margin=0.8)
        beside = self._beside_picture(whole)
        if beside is not None:
            return beside
        entrance = K.stagger([K.timed(FadeIn(face, shift=UP * 0.6, rate_func=ease_out_cubic), K.t("base"), "swish"),
                              K.timed(FadeIn(marks, shift=DOWN * 0.5, rate_func=ease_out_back), K.t("fast"), "pop"),
                              K.typewriter(words, run=min(2.6, 0.03 * len(text) + 0.4)),
                              K.enter(name, "slide", side="right") if name is not None else None], lag=0.5)
        return self._show(self._next_id("quote"), whole, entrance)

    def process(self, steps, title: str | None = None, cycle: bool = False):
        if not self.board_mode:
            return super().process(steps, title, cycle)
        return self.m_chain([{"label": str(s)} for s in steps], title=title, loop=cycle)

    def equation(self, tex: str, label: str | None = None):
        """A law written on, a box drawn round it, its name under it."""
        anim = super().equation(tex, label)
        body = self.stage_body
        # Only round an equation that has the board to itself (beside a drawing, it is a card at the side).
        if anim is None or body is None or not self.board_mode or not any(body is m for m in self._beat_new):
            return anim
        try:
            frame = SurroundingRectangle(body[0] if len(body.submobjects) > 1 else body, buff=0.3,
                                         color=K.col("accent"), stroke_width=4, corner_radius=0.08)
        except Exception:  # noqa: BLE001
            return anim
        frame.set_z_index(Z_TEMPLATE + 1)
        self._stage_add(frame)
        return K.timed(AnimationGroup(anim, K.draw(frame, run=K.t("base")), lag_ratio=0.75),
                       K.t("slow") + K.t("base"))

    # ---------------------------------------------------------------- pictures, dressed --------------------------
    def stage_image(self, path: str, caption: str = "", credit: str = "", labels=(), move: str | None = None,
                    points=()):
        """The engine's picture, dressed the look's way first (a sticker's white edge, a card, a polaroid, a
        newsprint duotone), its labels moved onto the dressed picture; it comes on the look's way and floats."""
        if self.M.get("classic") or (self._full_screen() and not pl.is_cutout(path)):
            return super().stage_image(path, caption, credit, labels, move, points)
        how = "sticker" if pl.is_cutout(path) else self.M.get("photo", "card")
        if pl.is_cutout(path) and not self.M.get("sticker", True):
            how = "plain"
        try:
            dressed, (x0, y0, x1, y1) = motion_looks.dress(str(path), how)
        except Exception as error:  # noqa: BLE001 -- shown as it is
            pl.skipped(f"motion: the picture was not dressed ({type(error).__name__}: {error})"[:200])
            return super().stage_image(path, caption, credit, labels, move, points)
        moved = []
        for row in labels or ():
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            r = list(row)
            r[1] = x0 + float(r[1]) * (x1 - x0)
            r[2] = y0 + float(r[2]) * (y1 - y0)
            if len(r) >= 7:
                r[3] = x0 + float(r[3]) * (x1 - x0)
                r[4] = y0 + float(r[4]) * (y1 - y0)
                r[5] = x0 + float(r[5]) * (x1 - x0)
                r[6] = y0 + float(r[6]) * (y1 - y0)
            moved.append(tuple(r))
        views = self.__dict__.setdefault("_views", [])
        before = len(views)
        shown = super().stage_image(dressed, caption, credit, moved, move, points)
        if len(views) > before:
            # The shade round a named part covers the photo only, not the dressed edge and shadow round it (a grey
            # block over the page): where the photo is in the picture as the engine trims it.
            _, trim = pl.trim_box(dressed)
            content = pl.remap_labels([("", 0.5, 0.5, x0, y0, x1, y1)], trim)[0][3:7]
            for view in views[before:]:
                view["content"] = tuple(float(v) for v in content)
        return shown

    # ---------------------------------------------------------------- a picture's labels, in the look ------------
    def _label_tag(self, text: str, room: float, size: float = 17):
        """A picture's label as a chip of the look's accent (its heading font), fitted to the room it has."""
        if self.M.get("classic"):
            return super()._label_tag(text, room, size)
        tag = K.chip(text, size=size + 1, pad=0.12)
        if tag.width > room - 0.2:
            tag.scale((room - 0.2) / tag.width)
        return tag

    def _in_look(self, pieces: list) -> list:
        """A label's box, line and dot in the look's accent instead of the house gold."""
        if self.M.get("classic"):
            return pieces
        accent = K.col("accent")
        for piece in pieces:
            frame = piece.get("frame")
            if frame is not None and len(frame.submobjects) > 1:
                frame[1].set_stroke(accent)
            if piece.get("line") is not None:
                piece["line"].set_stroke(accent)
            if piece.get("dot") is not None:
                piece["dot"].set_fill(accent)
        return pieces

    def _shade(self, view, name: str):
        """The rest of a labelled picture shaded round the part being talked about, drawn as a picture of its own
        from the picture's own shape (its alpha): dark wherever the picture is, clear over the part (feathered).
        Dark panels over its box shaded the transparent corners of a cutout, and a dressed card's edge and shadow,
        grey on the page."""
        image = view["image"]
        pixels = getattr(image, "pixel_array", None)
        if self.M.get("classic") or pixels is None or pixels.ndim != 3 or pixels.shape[2] < 4:
            return super()._shade(view, name)
        import hashlib

        from PIL import Image, ImageFilter

        rows, cols = pixels.shape[:2]
        u0, v0, u1, v1 = view["parts"][name]["box"]
        lo, hi = self._where(image)
        w, h = max(hi[0] - lo[0], 1e-6), max(hi[1] - lo[1], 1e-6)
        pad_u, pad_v = 0.12 / w, 0.12 / h
        key = hashlib.sha1(pixels[::7, ::7].tobytes() + repr((rows, cols, u0, v0, u1, v1, self.SHADE)).encode())
        out = motion_looks.CACHE / f"shade-{key.hexdigest()[:16]}.png"
        if not out.exists():
            motion_looks.CACHE.mkdir(parents=True, exist_ok=True)
            # The lit part: a soft-edged hole, so the light reads as a spotlight rather than a cut.
            hole = Image.new("L", (cols, rows), 0)
            from PIL import ImageDraw

            ImageDraw.Draw(hole).rounded_rectangle(
                [max(0, (u0 - pad_u) * cols), max(0, (v0 - pad_v) * rows), min(cols, (u1 + pad_u) * cols),
                 min(rows, (v1 + pad_v) * rows)], radius=max(2, int(0.02 * max(rows, cols))), fill=255)
            hole = np.asarray(hole.filter(ImageFilter.GaussianBlur(max(1.5, 0.008 * max(rows, cols)))), dtype=float) / 255
            alpha = pixels[..., 3].astype(float) / 255 * self.SHADE * (1 - hole)
            rgba = np.zeros((rows, cols, 4), dtype=np.uint8)
            rgba[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
            part = out.with_suffix(f".{os.getpid()}.part.png")
            Image.fromarray(rgba, "RGBA").save(part)
            os.replace(part, out)
        shade = ImageMobject(str(out))
        shade.stretch_to_fit_width(w)
        shade.stretch_to_fit_height(h)
        shade.move_to([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0])
        shade.set_z_index(self.Z_LOOK)
        shade._panim_z = self.Z_LOOK
        shade._art_none = True
        set_drift([shade], view.get("drift"))
        return Group(shade)

    def _label_layout(self, image, labels, width: float) -> list:
        return self._in_look(super()._label_layout(image, labels, width))

    def _labels_on(self, image, labels) -> list:
        return self._in_look(super()._labels_on(image, labels))

    # ---------------------------------------------------------------- the timeline, in motion and in styles -------
    def big_timeline(self, events, title: str | None = None, range=None, spans=None, scale: str | None = None,
                     style: str | None = None):
        import motion_timeline

        style = style or os.environ.get("MOTION_TIMELINE") or "track"
        try:
            return motion_timeline.build(self, events, title, range, spans, scale, style)
        except Exception as error:  # noqa: BLE001 -- the engine's own, still timeline
            pl.skipped(f"motion: the {style} timeline fell back to the still one ({type(error).__name__}: {error})"[:240])
            return super().big_timeline(events, title, range=range, spans=spans, scale=scale)

    # ---------------------------------------------------------------- chapter cards and the title ---------------
    def chapter_card(self, num: int, title: str, sub: str):
        """The chapter's card in the look: its number large in the accent, the kicker CHAPTER over it, the title in
        the heading font, a bar of the accent under it."""
        P = pl.P
        n = K.number(f"{num:02d}", 120, K.col("accent"))
        kick = K.kicker(f"Chapter {num}", 20)
        t = fit(K.head(title, 58, P.TITLE), 11.5)
        s = fit(K.body(sub, 26, P.MUTED, 60), 11.5) if sub else VGroup()
        rule = Rectangle(width=min(t.width, 6), height=0.12, stroke_width=0, fill_color=K.col("accent"), fill_opacity=1)
        card = VGroup(n, kick, t, rule, s)
        n.move_to(UP * 1.6)
        kick.next_to(n, DOWN, buff=0.15)
        t.next_to(kick, DOWN, buff=0.35)
        rule.next_to(t, DOWN, buff=0.25)
        s.next_to(rule, DOWN, buff=0.25)
        card.move_to(UP * 0.35)
        card.set_z_index(pl.Z_CARD)
        return card

    def chapter(self, num: int, title: str, sub: str, narration: str) -> None:
        """The engine's chapter start, its card coming on the look's way: the number springs in, the kicker is
        typed, the title's words rise one after another, the bar is drawn; the card then sweeps away."""
        self._chapter_no = int(num)
        self._chapter_title = title
        for hook in pl.CHAPTER_HOOKS:
            hook(self, num)
        if self.on_stage():
            self.outro_fade(0.6)
        self._log("chapter", number=num, title=title)
        if self.SECTIONS:
            self.section(num)
        card = self.chapter_card(num, title, sub)
        n, kick, t, rule, s = card
        words = t
        intro = K.stagger([K.timed(FadeIn(n, scale=0.4, rate_func=ease_out_back), K.t("base"), "chapter"),
                           K.typewriter(kick, run=0.5),
                           K.timed(FadeIn(words, shift=UP * 0.5, rate_func=ease_out_expo), K.t("base")),
                           K.grow_from(rule, LEFT, run=K.t("base")),
                           K.enter(s, "fade") if len(s.submobjects) else None], lag=0.4)
        intro.panim_sfx = "chapter"
        mark = self.emblem(1.0)
        if mark is not None:
            mark.next_to(card, UP, buff=0.3).set_z_index(pl.Z_CARD)
            if mark.get_top()[1] > config.frame_height / 2 - 0.7:
                mark.shift(DOWN * (mark.get_top()[1] - config.frame_height / 2 + 0.7))
            intro = AnimationGroup(intro, FadeIn(mark, scale=0.6, rate_func=ease_out_back))
            card = Group(*card, mark)
        self.beat(narration, intro, rt=2.2)
        self.play(FadeOut(card, shift=UP * 1.2, rate_func=rush_into), run_time=0.6)

    def title_slide(self, title: str, sub: str = "", tag: str = "AN ILLUSTRATED LECTURE", narration: str = ""):
        P = pl.P
        head_ = fit(K.head(title, 84, P.TITLE), 12)
        line = fit(K.body(sub, 30, P.MUTED, 60), 12) if sub else VGroup()
        label = K.kicker(tag, 18, K.col("accent"))
        bar = Rectangle(width=min(head_.width, 7), height=0.14, stroke_width=0, fill_color=K.col("accent"),
                        fill_opacity=1)
        mark = self.emblem(1.3)
        group = Group(*([mark] if mark is not None else []), label, head_, bar, line).arrange(DOWN, buff=0.3)
        group.move_to(UP * 0.4)
        group.set_z_index(pl.Z_CARD)
        opening = K.stagger([K.timed(FadeIn(mark, scale=0.5, rate_func=ease_out_back), K.t("base")) if mark else None,
                             K.typewriter(label, run=0.7),
                             K.timed(FadeIn(head_, shift=UP * 0.6, scale=0.9, rate_func=ease_out_expo), K.t("slow")),
                             K.grow_from(bar, LEFT, run=K.t("base")), K.enter(line, "fade") if sub else None], lag=0.4)
        opening.panim_sfx = "intro"
        self.beat(narration or f"{title}. {sub}", opening, rt=3.0)
        self.play(FadeOut(group, shift=UP * 1.0, rate_func=rush_into), run_time=0.7)


# ---------------------------------------------------------------- phrases in a block of words -------------------------

def _phrase_glyphs(text_mob, source: str, phrase: str) -> list:
    """The glyphs of `phrase` in a Text built from `source` (wrapped): the Text's glyphs are its characters less
    the spaces and line breaks, in order."""
    flat = re.sub(r"\s+", " ", source)
    spot = flat.lower().find(phrase.lower().strip())
    if spot < 0:
        return []
    glyphs = [m for m in text_mob.submobjects]
    if len(glyphs) == 1 and len(glyphs[0].submobjects) > 1:
        glyphs = list(glyphs[0].submobjects)
    before = len(re.sub(r"\s", "", flat[:spot]))
    count = len(re.sub(r"\s", "", phrase))
    chars = re.sub(r"\s", "", flat)
    if len(glyphs) != len(chars):
        return []
    return glyphs[before:before + count]


def _by_line(glyphs: list) -> list:
    """Glyphs grouped by the line they sit on."""
    lines: list[list] = []
    for g in glyphs:
        if lines and abs(lines[-1][-1].get_center()[1] - g.get_center()[1]) < g.height * 0.6 + 0.05:
            lines[-1].append(g)
        else:
            lines.append([g])
    return lines
