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
from motion_explain import ExplainTemplates
from motion_forms import FormTemplates
from motion_more import MoreTemplates
from motion_story import StoryTemplates
import pocket_lecture as pl
from pocket_lecture import *  # noqa: F403 -- the engine's names, for the compiled scene
from pocket_lecture import (BEAT_PAD, PARAGRAPH_PAD, Z_MARK, MapLecture, _flat, fit, said_at, set_drift, wrap)

motion_looks.register_all()
LOOK = os.environ.get("MOTION_LOOK") or ""
if LOOK in pl.THEMES:
    pl.use_style(LOOK)
    os.environ["LECTURE_STYLE"] = LOOK
K.M.update(motion_looks.motion_of(pl.STYLE, os.environ.get("MOTION_ENERGY") or None,
                                  {"transition": os.environ.get("MOTION_TRANSITION") or None,
                                   "idle": os.environ.get("MOTION_IDLE") or None}))

Z_TEMPLATE = Z_MARK + 10
TITLE_ROOM = 0.75           # the band at the top of a template its title takes


def land_lead(run: float) -> float:
    """How long before its word an animation of `run` seconds starts, so it has arrived as the word is heard: the
    looks' eases do most of their travel in the first third of the run (ease_out_cubic is 70% there at 0.33), so a
    little more than a third of it, with the engine's SYNC_LEAD the least and 0.45 s the most (a long choreography
    has its first part up early in it; earlier, a thing is up before the voice has come to it)."""
    return round(min(0.45, max(pl.SYNC_LEAD, 0.12 + 0.3 * float(run))), 3)


def _slug(text) -> str:
    return re.sub(r"[^\w]+", "-", str(text).strip().lower()).strip("-")


def _P():
    return pl.P


class MotionLecture(StoryTemplates, ExplainTemplates, FormTemplates, MoreTemplates, MapLecture):
    """A lecture in a look, every template animated (see the module's notes)."""

    # ---------------------------------------------------------------- set-up ----------------------------------------
    def setup(self):
        super().setup()
        self.M = K.M
        self._mparts: dict[str, dict] = {}      # template id -> {part name: mobject}
        self._mwhole: dict[str, object] = {}    # template id -> the whole template (emphasis on its id)
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
        animations = (*animations, *self._room_moves(animations))
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

        # Read against what stays: the picture leaving in this same play (fading out under the new one) is not
        # what the new words will sit on, and words made to read on it came out faint on the bare board.
        leaving = set()

        def gone(anim):
            for sub in getattr(anim, "animations", None) or []:
                gone(sub)
            if getattr(anim, "remover", False) and getattr(anim, "mobject", None) is not None:
                leaving.update(id(x) for x in anim.mobject.get_family())
        for anim in animations:
            gone(anim)
        def kept(m):
            # The scene's tree without what is leaving (a template held in the stage's group goes with its group
            # kept): a stand-in group over the parts that stay, the parts themselves untouched.
            if id(m) in leaving:
                return None
            if not any(id(x) in leaving for x in m.get_family()):
                return m
            return Group(*[k for k in (kept(c) for c in m.submobjects) if k is not None])
        staying = SimpleNamespace(mobjects=[k for k in (kept(m) for m in self.mobjects) if k is not None]) \
            if leaving else self
        arriving = backed_text.arriving_in(animations)
        if leaving:
            arriving = [k for k in (kept(m) for m in arriving) if k is not None]
        legible.legible(staying, arriving)
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
            how = {"slide": "slide", "push": "rise", "zoom": "zoom", "page": "slide", "whip": "slide", "stack": "rise",
                   "flash": "fade", "turn": "flip", "match": "iris"}.get(self.M.get("transition"), self.M.get("enter", "pop"))
            if how == "write":
                how = "rise"
            if self.__dict__.pop("_m_pullback", False):
                # A picture that comes on as the camera pulls back from close on it.
                entrance = K.timed(FadeIn(group, scale=1.5, rate_func=ease_out_cubic), K.t("slow") * 2.2, "whoosh")
            elif self.M.get("transition") == "whip":
                entrance = K.timed(FadeIn(group, shift=LEFT * 6, rate_func=ease_out_expo), K.t("fast") * 1.4, "whoosh")
            elif self.M.get("transition") == "stack":
                entrance = K.timed(FadeIn(group, shift=UP * 3.2, rate_func=ease_out_cubic), K.t("base"), "swish")
            else:
                entrance = K.enter(group, how, side="right", run=K.t("base"))
            K.idle(group)
            draw = None
        leaving = self._carry_from(group) if not still and self._replaces(group) else []
        anim = super()._to_stage(group, draw=draw, still=still, entrance=entrance)
        if anim is not None and entrance is not None and getattr(entrance, "panim_run", None):
            run = float(entrance.panim_run) + (0.35 if isinstance(anim, AnimationGroup) and anim is not entrance
                                               and getattr(anim, "lag_ratio", 0) == 1.0 else 0)
            K.timed(anim, run, getattr(entrance, "panim_sfx", None))
        glides = self._carry_into(group, leaving)
        if anim is not None and glides:
            run = max(float(getattr(anim, "panim_run", 0) or 0), self.CARRY_RUN)
            anim = K.timed(AnimationGroup(anim, *glides), run, getattr(anim, "panim_sfx", None))
        return anim

    # ---------------------------------------------------------------- continuity: a match cut -------------------
    # When the next picture shows a word or a figure the one leaving shows too (a counter's "60%" in the next card,
    # a term defined and then a headline), that word does not simply go with the old picture: a copy of it flies
    # to its place in the new one, taking its size, and dissolves into it as the new picture's own word comes on.
    # The old picture's word is hidden as the copy takes off. A fade with a shift and a scale (the players' own).
    CARRY_RUN = 0.8          # seconds the carried word takes to reach its new place
    CARRY_MOST = 2           # words carried at one change of picture

    @staticmethod
    def _carry_key(m) -> str:
        text = str(getattr(m, "text", "") or "").strip()
        return re.sub(r"\s+", " ", text).lower()

    def _replaces(self, group) -> bool:
        """Whether the engine's _to_stage takes the picture up away for this one (not a card put in the panel beside
        it, nor a second picture of the same beat put beside the first): only then is anything carried across."""
        body = self.stage_body
        if self._panel_up() and getattr(group, "is_text_card", False) and body is not None \
                and not getattr(body, "is_text_card", False) and len(body.get_family()) > 1:
            return False
        return not (len(self._beat_new) == 1 and body is self._beat_new[0] and len(group.get_family()) > 1
                    and body is not None and len(body.get_family()) > 1)

    def _carry_from(self, group) -> list:
        """(old, new) pairs: words of the template(s) leaving the stage that the new picture shows too, the same
        words in a like size (a headline's word is not carried into a chart's small label)."""
        if not isinstance(group, Mobject):
            return []
        new_family = {id(x) for x in group.get_family()}
        on_screen = {id(x) for top in self.mobjects for x in top.get_family()}
        old_wholes = [w for w in self._mwhole.values() if id(w) not in new_family and id(w) in on_screen]
        if not old_wholes:
            return []
        texts = lambda mobs: [m for w in mobs for m in w.get_family()  # noqa: E731
                              if isinstance(m, Text) and len(self._carry_key(m)) >= 2 and m.get_fill_opacity() > 0.5]
        olds = texts(old_wholes)
        pairs, used = [], set()
        for n in texts([group]):
            key = self._carry_key(n)
            if key in pl.SAY_STOP or not re.search(r"\w", key):
                continue
            o = next((o for o in olds if id(o) not in used and self._carry_key(o) == key
                      and 0.4 <= n.height / max(o.height, 1e-3) <= 2.5), None)
            if o is None:
                continue
            used.add(id(o))
            pairs.append((o, n))
            if len(pairs) >= self.CARRY_MOST:
                break
        return pairs

    def _carry_into(self, group, pairs: list) -> list:
        """The flights of the carried words, from where they stand to their places in the new picture (where it now
        stands): a copy of each, the old picture's own hidden from now (so its exit does not take a second one)."""
        glides = []
        for o, n in pairs:
            flier = o.copy()
            pl.set_drift([flier], None)
            flier.set_z_index(Z_TEMPLATE + 5)
            self.add(flier)
            o.set_opacity(0)
            k = n.height / max(o.height, 1e-3)
            glides.append(K.timed(FadeOut(flier, shift=n.get_center() - o.get_center(), scale=k, rate_func=smooth),
                                  self.CARRY_RUN, "swish"))
        return glides

    def _beside(self, group):
        """The engine's picture and words side by side, with room made when the words come: a template up keeps the
        whole stage until the card beside it is said, and slides to its half as the card comes on, instead of standing
        small in one half with the other empty all the line. Its parts still to come on (a timeline's next event)
        follow it when the move plays (_room_moves): those up by then move with it, the rest are put in their place
        unseen, to come on there."""
        import stem

        first = self.stage_body
        whole = first is not None and any(first is w for w in self._mwhole.values())
        if not whole or getattr(group, "is_text_card", False) is False or getattr(first, "is_text_card", False) \
                or self._panel_up():
            return super()._beside(group)
        parts = [m for m in [*self.stage_pending, *self.stage_extra] if m is not first]
        c0, w0 = np.array(first.get_center(), dtype=float), float(first.width)
        anim = super()._beside(group)
        if self.stage_body is not first or first.width <= 0 or w0 <= 0:
            return anim
        c1 = np.array(first.get_center(), dtype=float)
        f = float(first.width) / w0
        # Back to the whole stage until the card comes (the picture and its parts, as the engine moved them).
        for m in [first, *parts]:
            m.scale(1 / f, about_point=c1).shift(c0 - c1)
        pl.follow_drift([first, *parts], 1 / f, c1, c0 - c1)
        room = stem._moving(first.animate(rate_func=smooth).scale(f, about_point=c0).shift(c1 - c0))
        K.timed(room, K.t("base"), "swish")
        room._m_room = {"parts": parts, "f": f, "c0": c0, "c1": c1,
                        "ids": {id(x) for m in [first, *parts] for x in m.get_family()}}
        self._m_moves = [m for m in self.__dict__.get("_m_moves", []) if not m.get("done")] + [room._m_room]
        pl.follow_drift([first, *parts], f, c0, c1 - c0)
        return AnimationGroup(room, anim) if anim is not None else room

    def _room_moves(self, animations) -> list:
        """For a room-making move about to play (_beside): the moves of the picture's parts up on the screen now,
        made the same way; the parts not up yet are put where the move takes them, unseen (they come on there)."""
        extra = []
        on_screen = {id(x) for top in self.mobjects for x in top.get_family()}
        todo = list(animations)
        while todo:
            a = todo.pop()
            todo.extend(getattr(a, "animations", None) or [])
            also = getattr(a, "_m_also", None)
            if also and not also.get("done"):
                also["done"] = True
                for m in also["parts"]:
                    # What of it is up: the part itself, or its pieces put up one by one (a typed line's letters).
                    fam = {id(x) for x in m.get_family()}
                    # Gone in the first third, with the picture it belonged to (the play's run is the whole change).
                    extra += [FadeOut(top, rate_func=lambda t: min(1.0, 3.0 * t)) for top in self.mobjects
                              if id(top) in fam]
            room = getattr(a, "_m_room", None)
            if not room or room.get("done"):
                continue
            import stem

            room["done"] = True
            f, c0, c1 = room["f"], room["c0"], room["c1"]
            for m in room["parts"]:
                if id(m) in on_screen:
                    extra.append(stem._moving(m.animate(rate_func=smooth).scale(f, about_point=c0).shift(c1 - c0)))
                else:
                    m.scale(f, about_point=c0).shift(c1 - c0)
        return extra

    def _stage_leaving(self) -> list:
        """The engine's fade-outs for what leaves the stage, made the look's exit: slid out (the way the next
        comes from), pushed up, zoomed past; for a wipe, taken away under the wipe as the next line begins."""
        staged = {id(m) for m in [self.stage_items, *self.stage_extra]}
        # Parts of the leaving picture still to come on when this was built (a question's answer, said earlier in
        # the line than the next picture): up by the time the picture leaves, they leave with it (_room_moves).
        pending = list(self.stage_pending)
        going = super()._stage_leaving()
        kind = self.M.get("transition", "slide")
        out = []
        for anim in going:
            if not isinstance(anim, FadeOut) or getattr(anim, "mobject", None) is None:
                out.append(anim)
                continue
            mob = anim.mobject
            if kind == "wipe" and id(mob) not in staged:
                # Not the stage's picture (a mark left on the map, a stray): it fades as the picture comes, in its
                # turn. Wiped away as the line began, the map went with it while the line's first words were on it.
                out.append(anim)
            elif kind == "wipe":
                self._wipe_old.append(mob)
            elif kind in ("slide", "page"):
                out.append(K.timed(FadeOut(mob, shift=LEFT * 2.2, rate_func=rush_into), K.t("fast"), "swish"))
            elif kind == "push":
                out.append(K.timed(FadeOut(mob, shift=UP * 1.2, rate_func=rush_into), K.t("fast"), "swish"))
            elif kind == "zoom":
                out.append(K.timed(FadeOut(mob, scale=1.25, rate_func=rush_into), K.t("fast"), "whoosh"))
            elif kind == "cut":
                out.append(K.timed(FadeOut(mob, run_time=0.05), 0.05))
            elif kind == "whip":
                out.append(K.timed(FadeOut(mob, shift=LEFT * 6, rate_func=rush_into), K.t("fast"), "whoosh"))
            elif kind == "stack":
                out.append(K.timed(FadeOut(mob, scale=0.9, rate_func=smooth), K.t("base")))
            elif kind == "flash":
                out.append(K.timed(FadeOut(mob, scale=1.03, rate_func=rush_into), 0.12))
            elif kind == "turn":
                out.append(K.timed(FadeOut(mob, shift=LEFT * 1.5, scale=0.85, rate_func=rush_into), K.t("fast"), "swish"))
            elif kind == "match":
                out.append(K.timed(FadeOut(mob, scale=2.4, rate_func=rush_into), K.t("base"), "whoosh"))
            else:
                out.append(anim)
        if pending and out:
            out[0]._m_also = {"parts": pending}
        elif pending and kind == "wipe":
            self._wipe_old.extend(pending)
        return out

    def beat(self, text: str, *anims, rt: float | None = None, pad: float | None = None, cues: list | None = None) -> float:
        """The engine's; a line that wipes to a new picture covers the old one just before its voice (_speak), and
        takes that time back from its own pause after it, so the chapter is as long as before."""
        if self._wipe_old:
            pad = max(0.12, (pl.beat_pad(text) if pad is None else pad) - K.t("fast"))
        later = [a for a in anims if getattr(a, "panim_in_pause", False)]
        if not later:
            return super().beat(text, *anims, rt=rt, pad=pad, cues=cues)
        # A stamp or an emphasis the writer put in the quiet after the line (`in_pause`): the line and the rest as
        # ever, then these in the pause it leaves, the pause no longer than it was unless they need more.
        keep = [i for i, a in enumerate(anims) if not any(a is x for x in later)]
        now = [anims[i] for i in keep]
        if cues is not None and len(cues) == len(anims):
            cues = [cues[i] for i in keep]
        full = pl.beat_pad(text) if pad is None else pad
        seconds = super().beat(text, *now, rt=rt, pad=0.05, cues=cues)
        run = max(float(getattr(a, "panim_run", 0.5) or 0.5) for a in later)
        self.play(*later)
        rest = full - 0.05 - run
        if rest > 0.02:
            self.wait(rest)
        return seconds

    def _m_when(self, anim, after: float = 0.0, pause: bool = False):
        """An operation's moment moved by its writer (compile_motion._when): `delay` seconds after its words, or
        into the quiet after its line (`pause`)."""
        if anim is not None:
            try:
                if after:
                    anim.panim_after = float(after)
                if pause:
                    anim.panim_in_pause = True
            except AttributeError:
                pass
        return anim

    def _speak(self, wav, seconds: float) -> None:
        """The line's voice; when the look wipes from one picture to the next, the sheet covers the old picture just
        before the voice begins and uncovers the board under its first words: the cut lands as the line starts, and
        what the line names first is not held back behind a wipe that took the line's first half second."""
        old = [m for m in self._wipe_old if any(m is x for x in self.mobjects)]
        self._wipe_old = []
        if not old:
            super()._speak(wav, seconds)
            return
        # Never over the line before: the cover waits for its voice to end (as the engine's _speak does).
        still = self.__dict__.get("_voice_until", 0.0) - float(getattr(self.renderer, "time", 0.0) or 0.0)
        if still > 0.02:
            self.wait(still)
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
        super()._speak(wav, seconds)
        self.play(wipe.animate(rate_func=ease_in_cubic).move_to([bx + fw, by, 0]), run_time=run)
        self.remove(wipe)
        self._lead += run

    def _wait_until(self, elapsed: float, until: float, swaps) -> float:
        # A transition played at the line's start took its time from the line: the line's clock counts it.
        if self._lead:
            elapsed += self._lead
            self._lead = 0.0
        return super()._wait_until(elapsed, until, swaps)

    def _cue_plan(self, given: list, extra: list, seconds: float, default: float) -> list:
        """As the engine's, each animation given the time it asked for (panim_run) instead of a blanket one; and one
        timed to a word lands on it: started early by as much of its run as it takes to arrive (land_lead), not by
        the engine's fixed SYNC_LEAD, so a long entrance is not still coming on after its word."""
        heard = self.__dict__.get("_word_cues") or {}
        fixed = []
        for anim, cue in given:
            at = heard.get(id(cue)) if isinstance(cue, list) else None
            run = getattr(anim, "panim_run", None)
            if run is not None:
                run = min(float(run), motion_looks.TEMPLATE_MOST)  # a whole entrance quick enough to finish before the next
            if run is not None and isinstance(cue, (list, tuple)) and cue:
                cue = [cue[0], float(run)]
            elif run is not None and not cue:
                cue = [0.0, float(run)]
            if at is not None and isinstance(cue, (list, tuple)) and cue:
                cue = [round(max(0.0, at - land_lead(cue[1] if len(cue) > 1 and cue[1] else pl.PrimitiveRun.SHOW)), 3),
                       *cue[1:]]
            after = float(getattr(anim, "panim_after", 0.0) or 0.0)
            if after:
                # Its writer's own delay after its words (a beat's breath before a verdict lands).
                cue = [round(float(cue[0]) + after, 3), *cue[1:]] if isinstance(cue, (list, tuple)) and cue \
                    else [round(after, 3), run]
            fixed.append((anim, cue))
        return super()._cue_plan(fixed, extra, seconds, default)

    def _pointers(self, words, seconds: float, hinted: set) -> list:
        """The engine's pointing at things the line names again, done the look's way for a template's part; the
        first part of a large template the line names is pushed in on instead (_push_on), as a camera would."""
        out = []
        coming = self.__dict__.get("_m_arriving") or set()
        pushed: set = set()
        for anim, cue in super()._pointers(words, seconds, hinted):
            mob = getattr(anim, "mobject", None)
            if mob is not None and any(id(x) in coming for x in mob.get_family()):
                # Brought on by this line (an event on its date, said here): a pulse on it as well fought its
                # entrance, and the flag never showed.
                continue
            if mob is not None and any(id(x) in pushed for x in mob.get_family()):
                # On the template the camera pushed in on: built where it stood before the push, a mark would sit
                # beside its part; the push is this line's pointing.
                continue
            point = getattr(mob, "_m_point", None)
            if point is not None and not self._shown(mob):
                # A part not on the screen yet (its template's later words bring it on): a bracket drawn round it
                # framed an empty space.
                continue
            if point is not None and type(anim).__name__ == "ScaleInPlace":
                if not pushed:
                    push = self._push_on(mob, float(cue[0]), seconds)
                    if push:
                        out.extend(push)
                        pushed = {id(x) for x in push[0][0].mobject.get_family()}
                        continue
                made = point()
                if made is not None:
                    out.append((made, [cue[0], float(getattr(made, "panim_run", 0.7))]))
                    continue
            out.append((anim, cue))
        return out

    def _shown(self, mob) -> bool:
        """Whether a part is on the screen now: in the scene and not faded out."""
        here = {id(x) for top in self.mobjects for x in top.get_family()}
        fam = [x for x in mob.get_family() if id(x) in here]
        if not fam:
            return False
        def seen(x):
            try:
                return max(float(x.get_fill_opacity()), float(x.get_stroke_opacity())) > 0.05
            except Exception:
                return float(getattr(x, "opacity", 1) or 0) > 0.05
        return any(seen(x) for x in fam)

    PUSH = 1.12              # how far the camera pushes in on a part of a template the line names again
    PUSH_RUN = 0.7           # seconds in, and as many back out

    def _push_on(self, part, start: float, seconds: float) -> list:
        """A camera push on a part of a large template the line names again: the whole template scaled up about the
        part and drawn a third of the way to the stage's middle, held while the line is on it, and eased back before
        the line ends (both written as moves the players apply, stem._moving). [] when the template is small (a
        push on a card says nothing a pulse does not), or the line leaves too little time to come back."""
        import stem

        whole = next((self._mwhole.get(tid) for tid, parts in self._mparts.items()
                      if any(p is part for p in parts.values())), None)
        if whole is None or not any(whole is m for top in self.mobjects for m in top.get_family()):
            return []
        cx, cy, w, h = self.STAGE
        if whole.width < w * 0.55 and whole.height < h * 0.55:
            return []
        back_at = min(seconds - 0.25, start + self.PUSH_RUN + 1.6)
        if back_at - start < self.PUSH_RUN + 0.5:
            return []
        p = np.array(part.get_center(), dtype=float)
        shift = (np.array([cx, cy, 0.0]) - p) * 0.33
        f = self.PUSH
        # The part pushed on stays whole on the screen (a margin in): the push is about it, so it is scaled about
        # its own centre and only the shift can carry it out; the shift is cut back to keep it in.
        half = np.array([part.width, part.height, 0.0]) * f / 2
        lim = np.array([config.frame_width / 2 - 0.35, config.frame_height / 2 - 0.35, 0.0])
        lo, hi = -lim + half, lim - half
        target = p + shift
        if np.all(lo[:2] <= hi[:2]):
            target[:2] = np.clip(target[:2], lo[:2], hi[:2])
        else:
            return []           # a part too large to push on and keep whole
        shift = target - p
        go = stem._moving(whole.animate(rate_func=smooth).scale(f, about_point=p).shift(shift))
        K.timed(go, self.PUSH_RUN, "whoosh")
        # Built now, played later: the way back is from where the push left it (the exact inverse).
        whole.scale(f, about_point=p).shift(shift)
        back = stem._moving(whole.animate(rate_func=smooth).scale(1 / f, about_point=p + shift).shift(-shift))
        whole.scale(1 / f, about_point=p + shift).shift(-shift)
        K.timed(back, self.PUSH_RUN)
        go.panim_camera = back.panim_camera = True
        return [(go, [round(max(0.0, start), 3), self.PUSH_RUN]), (back, [round(back_at, 3), self.PUSH_RUN])]

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
        self._mwhole[tid] = whole
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
        force = K.FORCE_ENTER

        def made(heard):
            # Built as its words come, in the way its template was told to bring its parts on (`enter`).
            before, K.FORCE_ENTER = K.FORCE_ENTER, force
            try:
                anim = build(heard)
            finally:
                K.FORCE_ENTER = before
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
                    # Kept: the board's check (legible.py) reads it on the bare board, before its stroke is drawn.
                    m.panim_keep_colour = True
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
                  start: float = 0.0, layout: str = "big", max=None, id: str | None = None):
        """A big figure counting up to its value, its kicker typed over it, its label rising under it, and a change
        (▲ +50%) popping beside it. `layout`: big (the figure alone), ring (the figure inside a ring that sweeps
        round to value/max), bar (the figure over a bar that fills to value/max), badge (the figure on a round
        seal, its label beside it)."""
        if layout in ("ring", "bar", "badge"):
            return self._counter_shaped(value, label, kicker, color, sub, start, layout, max, id)
        tid = id or self._next_id("counter")
        tone = pl.role(color) if color else K.col("accent")

        def make(words):
            return K.number(words, 120, tone)

        # A year (1949, 1905) is not a quantity to count up from nothing: mid-count the screen read "1913" while the
        # voice said 1949. It rolls up from a few decades before instead, landing as it is said.
        if not start and re.fullmatch(r"\s*1[0-9]{3}\s*|\s*20[0-9]{2}\s*", str(value)):
            start = float(int(str(value).strip()) - 40)
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

    def _counter_shaped(self, value, label, kicker, color, sub, start, layout, most, id):
        """A counter in a ring, over a bar, or on a seal (m_counter's `layout`)."""
        P = pl.P
        tid = id or self._next_id("counter")
        tone = pl.role(color) if color else K.col("accent")
        parsed = K.parse_number(str(value))
        try:
            share = float(np.clip(parsed[1] / float(most), 0, 1)) if parsed and most else 1.0
        except (TypeError, ValueError, ZeroDivisionError):
            share = 1.0
        if not start and re.fullmatch(r"\s*1[0-9]{3}\s*|\s*20[0-9]{2}\s*", str(value)):
            start = float(int(str(value).strip()) - 40)
        size = {"ring": 76, "bar": 96, "badge": 64}[layout]
        ink = _ink_on(tone) if layout == "badge" else P.TITLE
        num = K.counter(str(value), lambda w: K.number(w, size, ink), start=start)
        lab = K.body(label, 28, P.CREAM, 34) if label else None
        top = K.kicker(kicker, 20) if kicker else None
        anims = []
        if layout == "ring":
            r = 1.75
            track = Circle(radius=r, stroke_color=pl._tint_on_bg(tone, 0.18), stroke_width=22, fill_opacity=0)
            arc = Arc(radius=r, start_angle=math.pi / 2, angle=-2 * math.pi * max(share, 0.002), stroke_color=tone,
                      stroke_width=22)
            fit(num, r * 1.5)
            num.move_to(ORIGIN)
            shape = VGroup(track, arc, num)
            if lab is not None:
                lab.next_to(track, DOWN, buff=0.35)
            grow = K.timed(Create(arc, rate_func=ease_out_cubic), K.t("slow") * 1.3, "draw")
            anims += [K.draw(track, run=K.t("base")), grow]
        elif layout == "bar":
            bw = 8.0
            track = RoundedRectangle(width=bw, height=0.42, corner_radius=0.21, stroke_width=0,
                                     fill_color=pl._tint_on_bg(tone, 0.18), fill_opacity=1)
            fill_bar = RoundedRectangle(width=max(0.42, bw * share), height=0.42, corner_radius=0.21, stroke_width=0,
                                        fill_color=tone, fill_opacity=1)
            fill_bar.align_to(track, LEFT)
            num.next_to(track, UP, buff=0.3).align_to(track, LEFT)
            shape = VGroup(track, fill_bar, num)
            if lab is not None:
                lab.next_to(track, DOWN, buff=0.3).align_to(track, LEFT)
            anims += [K.enter(track, "fade", run=K.t("fast"))]
        else:
            seal = Circle(radius=1.45, stroke_width=0, fill_color=tone, fill_opacity=1)
            ring = Circle(radius=1.3, stroke_color=_ink_on(tone), stroke_width=2.5, fill_opacity=0)
            fit(num, 2.2)
            num.move_to(ORIGIN)
            shape = VGroup(seal, ring, num)
            if lab is not None:
                lab.next_to(seal, RIGHT, buff=0.5)
            anims += [K.timed(FadeIn(VGroup(seal, ring), scale=0.4, rate_func=ease_out_back), K.t("base"), "pop"),
                      "count"]
        parts = [m for m in (top, shape, lab) if m is not None]
        if top is not None:
            top.next_to(shape, UP, buff=0.35).align_to(shape if layout != "badge" else shape, LEFT)
        if sub:
            low = K.body(sub, 22, P.MUTED, 50)
            low.next_to(lab if lab is not None else shape, DOWN, buff=0.2)
            if lab is not None:
                low.align_to(lab, LEFT)
            parts.append(low)
        whole = VGroup(*parts)
        self._fit(whole, self._box(), grow=1.15, margin=0.8)
        count = num.count_anim(run=K.t("slow") * 1.3, centre=layout != "bar")

        def made(a):
            if a in ("count", "count+"):
                return count if count is not None else K.enter(num, "pop")
            return a
        seq = [made(a) if isinstance(a, str) else a for a in anims]
        if layout == "ring":
            seq = [seq[0], K.together([seq[1], made("count")])]
        elif layout == "bar":
            seq = [seq[0], K.together([K.grow_from(shape[1], LEFT, run=K.t("slow") * 1.3), made("count")])]
        steps = [K.typewriter(top, run=0.6) if top is not None else None, *seq]
        if lab is not None:
            steps.append(K.enter(lab, "rise"))
        if sub:
            steps.append(K.enter(parts[-1], "fade"))
        self._part(tid, label, shape, point=lambda: K.pulse(num, 1.08))
        return self._show(tid, whole, K.stagger(steps, lag=0.5))

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
    def m_cards(self, items, title: str | None = None, kicker: str | None = None, stamp=None, layout: str = "row",
                id: str | None = None):
        """Cards dealt in from below one after another, each turned a little: a picture (or a big word) and its
        title; a mark on a card (check, cross or a word stamped) lands as it is said; `stamp` ({text, on}) slams
        across them all. `layout`: row (side by side), grid (in two rows, larger), fan (overlapping like a hand of
        cards, spread round a point)."""
        P = pl.P
        tid = id or self._next_id("cards")
        specs = [it if isinstance(it, dict) else {"title": str(it)} for it in (items or [])][:6]
        if not specs:
            return None
        n = len(specs)
        if layout not in ("grid", "fan"):
            layout = "row"
        per_row = math.ceil(n / 2) if layout == "grid" and n > 3 else n
        cw = min(2.9, 11.5 / per_row - 0.35) if layout != "fan" else 3.0
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
            if layout != "fan":
                whole_card.rotate((rng.uniform(1.5, 4.0) * (-1 if k % 2 else 1)) * math.pi / 180)
            cards.append((s, whole_card))
        if layout == "fan":
            # Spread round a point under the hand, each a little further turned, the later ones over the earlier.
            spread = min(18.0, 64.0 / max(n - 1, 1))
            hub = np.array([0, -ch * 2.4, 0])
            for k, (_, c) in enumerate(cards):
                angle = (k - (n - 1) / 2) * spread * math.pi / 180
                c.move_to(ORIGIN).rotate(-angle, about_point=hub)
                c.set_z_index(Z_TEMPLATE + k * 0.01)
            row = Group(*[c for _, c in cards])
        elif layout == "grid" and n > 3:
            row = Group(*[c for _, c in cards]).arrange_in_grid(cols=per_row, buff=(0.35, 0.45))
        else:
            row = Group(*[c for _, c in cards]).arrange(RIGHT, buff=0.35)
        whole, top = self._titled(row, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        deal = K.stagger([K.enter(c, None, run=K.t("base")) if K.forced() else
                          K.timed(FadeIn(c, shift=UP * 1.4, rate_func=ease_out_back), K.t("base"), "swish")
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
        mark._m_stamp = True
        body = self.stage_body
        if body is not None and getattr(body, "_m_stamp", False):
            body = None                     # a stamp alone on the board: the new one replaces it, never lands on it
        here = {id(x) for m in self.mobjects for x in m.get_family()}
        old = [m for m in self.__dict__.get("_m_stamps", []) if any(id(x) in here for x in m.get_family())]
        self._m_stamps = [mark]
        if body is not None:
            fit(mark, max(2.0, body.width * 0.7))
            spot = {"center": body.get_center(), "top": body.get_top() + DOWN * mark.height * 0.7,
                    "bottom": body.get_bottom() + UP * mark.height * 0.7, "right": body.get_right() + LEFT * mark.width * 0.6,
                    "left": body.get_left() + RIGHT * mark.width * 0.6}.get(at, body.get_center())
            if at == "center":
                spot = self._stamp_clear(body, mark, spot)
            mark.move_to(spot)
            mark.set_z_index(Z_TEMPLATE + 5)
            self._stage_add(mark)
            # Not shaken while a move of it is to play this beat: the shake, built where it stands now, put it back.
            landed = K.chain([K.slam(mark), K.shake(body, run=K.t("fast"))]) if (not isinstance(body, Group) or
                                                                                isinstance(body, VGroup)) \
                and not self._moving_now(body) else K.slam(mark)
            if old:
                # An earlier stamp still on the picture is lifted off as the new one lands: never two on top of each other.
                landed = K.together([K.together([K.leave(m, "fade") for m in old]), landed])
            return landed
        self._fit(mark, self._box(), grow=1.0, margin=3)
        return self._show(self._next_id("stamp"), mark, K.slam(mark), idle=False)

    def _after_moves(self, mob):
        """(lower left, upper right) of `mob` once the moves of the stage this beat has made (_m_moves) have played."""
        lo, hi = np.array(mob.get_corner(DL), dtype=float), np.array(mob.get_corner(UR), dtype=float)
        fam = {id(x) for x in mob.get_family()}
        for spec in self.__dict__.get("_m_moves", []):
            if not spec.get("done") and fam & spec["ids"]:
                f, c0, c1 = spec["f"], spec["c0"], spec["c1"]
                lo, hi = (lo - c0) * f + c1, (hi - c0) * f + c1
        return lo, hi

    def _moving_now(self, mob) -> bool:
        fam = {id(x) for x in mob.get_family()}
        return any(not spec.get("done") and fam & spec["ids"] for spec in self.__dict__.get("_m_moves", []))

    def _stamp_clear(self, body, mark, spot):
        """Where a stamp on words lands, half its width: of the places round the words (under, over, on a corner,
        beside), the one over the least of them, inside the stage, as they will stand once this beat's moves and the
        parts still to come (a question's answer) are in (a stamp over a timeline hid its dates and titles). A
        picture still takes it in its middle."""
        texts = [x for m in [body, *self.stage_pending] for x in m.get_family()
                 if type(x).__name__ in ("Text", "MarkupText", "Paragraph") and len(x.submobjects)]
        if not any(type(x).__name__ in ("Text", "MarkupText", "Paragraph") for x in body.get_family()):
            return spot
        fit(mark, min(4.2, max(2.0, body.width * 0.5)))
        boxes = [self._after_moves(x) for x in texts]
        ends = [self._after_moves(m) for m in [body, *self.stage_pending]]
        lo = np.min([e[0] for e in ends], axis=0)
        hi = np.max([e[1] for e in ends], axis=0)
        cx, cy, w, h = self._box()
        mw, mh = mark.width, mark.height
        mid = (lo + hi) / 2
        spots = [(mid[0], lo[1] - mh * 0.2), (mid[0], hi[1] + mh * 0.2),
                 (hi[0] - mw * 0.4, lo[1] + mh * 0.4), (hi[0] - mw * 0.4, hi[1] - mh * 0.4),
                 (hi[0] + mw * 0.3, mid[1]), (lo[0] - mw * 0.3, mid[1])]

        def cover(x, y):
            x0, x1, y0, y1 = x - mw / 2, x + mw / 2, y - mh / 2, y + mh / 2
            return sum(max(0.0, min(x1, b[1][0]) - max(x0, b[0][0])) * max(0.0, min(y1, b[1][1]) - max(y0, b[0][1]))
                       for b in boxes)
        best = None
        for x, y in spots:
            x = float(np.clip(x, cx - w / 2 + mw / 2, cx + w / 2 - mw / 2))
            y = float(np.clip(y, cy - h / 2 + mh / 2, cy + h / 2 - mh / 2))
            score = cover(x, y)
            if best is None or score < best[0] - 1e-6:
                best = (score, x, y)
        return np.array([best[1], best[2], 0.0])

    # ---------------------------------------------------------------- data cards -----------------------------------
    def m_kpi(self, cards, title: str | None = None, kicker: str | None = None, layout: str = "row",
              id: str | None = None):
        """Data cards (two to four): each a label in mono capitals, a big figure counting up, a change with its arrow
        (▲ green, ▼ red) and a note; dealt in one after another, each figure counting as it lands. `layout`: row
        (side by side), grid (two by two), column (wide strips one under another, the figure at the right)."""
        P = pl.P
        tid = id or self._next_id("kpi")
        specs = [c for c in (cards or []) if isinstance(c, dict)][:4]
        if not specs:
            return None
        n = len(specs)
        if layout not in ("grid", "column"):
            layout = "row"
        per_row = 2 if layout == "grid" and n > 2 else n if layout == "row" else 1
        cw = min(4.2, 12.0 / per_row - 0.3) if layout != "column" else 8.6
        ch = 3.2 if layout != "column" else 1.5
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
            if layout == "column":
                # The words at the left, the figure (and its change) at the right of the strip.
                change = stack[2] if s.get("delta") else None
                words = VGroup(*[m for m in stack if m is not num and m is not change])
                words.arrange(DOWN, buff=0.12, aligned_edge=LEFT)
                fig = VGroup(num, *([change] if change is not None else [])).arrange(RIGHT, buff=0.25)
                fit(fig, cw * 0.42)
                fit(words, cw * 0.5)
                content = VGroup(words, fig)
                words.move_to(face.face).align_to(face.face, LEFT).shift(RIGHT * 0.3)
                fig.move_to(face.face).align_to(face.face, RIGHT).shift(LEFT * 0.3)
                if content.height > ch - 0.25:
                    content.scale((ch - 0.25) / content.height)
            else:
                content = VGroup(*stack).arrange(DOWN, buff=0.18, aligned_edge=LEFT)
                content.move_to(face.face).align_to(face.face, LEFT).shift(RIGHT * 0.3)
                if content.height > ch - 0.4:
                    content.scale((ch - 0.4) / content.height)
            made.append((s, VGroup(face, content), num, content))
        if layout == "column":
            row = VGroup(*[m[1] for m in made]).arrange(DOWN, buff=0.25)
        elif layout == "grid" and n > 2:
            row = VGroup(*[m[1] for m in made]).arrange_in_grid(cols=2, buff=0.3)
        else:
            row = VGroup(*[m[1] for m in made]).arrange(RIGHT, buff=0.3)
        whole, top = self._titled(row, title, kicker)
        self._fit(whole, self._box(), grow=1.15)
        deals = []
        for s, c, num, content in made:
            count = num.count_anim(run=K.t("slow") * 1.2)
            rest = [m for m in content if m is not num] if layout != "column" else \
                [content[0], *[m for m in content[1] if m is not num]]
            card_in = K.enter(c[0], None) if K.forced() else \
                K.timed(FadeIn(c[0], shift=UP * 0.6, rate_func=ease_out_cubic), K.t("base"), "swish")
            deals.append(K.chain([card_in,
                                  K.together([count if count is not None else K.enter(num, "pop"),
                                              K.stagger([K.enter(m, "rise", run=K.t("fast")) for m in rest], lag=0.3)])]))
            self._part(tid, s.get("label"), c, point=lambda c=c: K.pulse(c, 1.04))
        entrance = K.stagger([self._title_in(top), K.stagger(deals, lag=0.35)], lag=0.5)
        return self._show(tid, whole, entrance)

    # ---------------------------------------------------------------- a chain of steps ---------------------------
    def m_chain(self, steps, title: str | None = None, kicker: str | None = None, loop: bool = False,
                layout: str = "row", id: str | None = None):
        """Steps joined by arrows: each step's card pops in and the arrow to it is drawn as the line says it (or one
        after another); `loop` draws an arrow from the last back round to the first. `layout`: row (left to right),
        column (top to bottom, wide cards), zigzag (a snake: along a first row, then back along a second)."""
        P = pl.P
        tid = id or self._next_id("chain")
        specs = [s if isinstance(s, dict) else {"label": str(s)} for s in (steps or [])][:7]
        if len(specs) < 2:
            return None
        n = len(specs)
        if layout not in ("column", "zigzag"):
            layout = "row"
        per_row = n if layout == "row" else math.ceil(n / 2) if layout == "zigzag" else 1
        cw = min(2.6, 12.0 / per_row - 0.55) if layout != "column" else 5.2
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
        cards = [m for _, m in made]
        if layout == "row":
            row = Group(*cards).arrange(RIGHT, buff=0.55)
        elif layout == "column":
            row = Group(*cards).arrange(DOWN, buff=0.45)
        else:
            top_row = Group(*cards[:per_row]).arrange(RIGHT, buff=0.55)
            low_row = Group(*cards[per_row:][::-1]).arrange(RIGHT, buff=0.55)
            low_row.next_to(top_row, DOWN, buff=0.75).align_to(top_row, RIGHT)
            row = Group(top_row, low_row)
        arrows = []
        for a, b in zip(cards, cards[1:]):
            d = b.get_center() - a.get_center()
            if abs(d[1]) > abs(d[0]):
                s0, s1 = (a.get_bottom() + DOWN * 0.06, b.get_top() + UP * 0.06) if d[1] < 0 else \
                    (a.get_top() + UP * 0.06, b.get_bottom() + DOWN * 0.06)
            else:
                s0, s1 = (a.get_right() + RIGHT * 0.06, b.get_left() + LEFT * 0.06) if d[0] > 0 else \
                    (a.get_left() + LEFT * 0.06, b.get_right() + RIGHT * 0.06)
            arrows.append(K.arrow_between(s0, s1, K.col("accent"), width=5))
        back = None
        if loop:
            first, last = made[0][1], made[-1][1]
            if layout == "column":
                back = K.arrow_between(last.get_right() + RIGHT * 0.08, first.get_right() + RIGHT * 0.08,
                                       K.col("accent"), curve=1.0, width=4)
            elif layout == "zigzag":
                back = K.arrow_between(last.get_left() + LEFT * 0.08, first.get_left() + LEFT * 0.08,
                                       K.col("accent"), curve=-1.0, width=4)
            else:
                back = K.arrow_between(last.get_bottom() + DOWN * 0.08, first.get_bottom() + DOWN * 0.08,
                                       K.col("accent"), curve=-1.0, width=4)
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
               layout: str = "column", id: str | None = None):
        """Points that come in one at a time as they are said, each with its mark (a bullet, its number, or a tick
        drawn). `layout`: column (a column of lines, each sliding in from the left), grid (tiles in two columns, each
        dealt in), pills (rounded chips flowing in rows, each popping in), steps (a staircase, each point a step
        down and to the right of the one before)."""
        P = pl.P
        tid = id or self._next_id("list")
        specs = [it if isinstance(it, dict) else {"text": str(it)} for it in (items or [])][:7]
        if not specs:
            return None
        if layout not in ("grid", "pills", "steps"):
            layout = "column"

        def sign_for(k):
            if mark == "number" or (layout == "steps" and mark == "bullet"):
                return K.chip(str(k + 1), K.col("accent"), K.col("accent_ink"), 22)
            if mark == "check":
                return K.check_mark(0.38)
            return Square(side_length=0.2, stroke_width=0, fill_color=K.col("accent"), fill_opacity=1).rotate(math.pi / 4)
        rows = []
        for k, s in enumerate(specs):
            text = str(s.get("text", ""))
            if layout == "pills":
                tone = self._tones(len(specs))[k]
                pill = K.chip(text, tone, _ink_on(tone), 26, pad=0.24)
                rows.append((s, pill))
                continue
            sign = sign_for(k)
            if layout == "grid":
                words = K.body(text, 26, K.col("card_ink"), 24)
                inner = VGroup(sign, words).arrange(RIGHT, buff=0.25, aligned_edge=UP)
                face = K.card(max(4.6, inner.width + 0.6), inner.height + 0.6)
                inner.move_to(face.face)
                rows.append((s, K.group_of(face, inner)))
                continue
            words = K.body(text, 30, P.CREAM, 40)
            rows.append((s, VGroup(sign, words).arrange(RIGHT, buff=0.3, aligned_edge=UP)))
        if layout == "grid":
            block = Group(*[r for _, r in rows]).arrange_in_grid(cols=2 if len(rows) > 2 else len(rows), buff=0.35,
                                                                  flow_order="rd")
        elif layout == "pills":
            lines, line = [], []
            for _, r in rows:
                line.append(r)
                if len(line) == 3:
                    lines.append(VGroup(*line).arrange(RIGHT, buff=0.3))
                    line = []
            if line:
                lines.append(VGroup(*line).arrange(RIGHT, buff=0.3))
            block = VGroup(*lines).arrange(DOWN, buff=0.35)
        else:
            block = VGroup(*[r for _, r in rows]).arrange(DOWN, buff=0.38, aligned_edge=LEFT)
            if layout == "steps":
                for k, (_, r) in enumerate(rows):
                    r.shift(RIGHT * 0.7 * k)
        whole, top = self._titled(block, title, kicker)
        self._fit(whole, self._box(), grow=1.6, margin=0.8)

        def row_in(r):
            if layout == "column" or layout == "steps":
                return self._row_in(r, mark)
            if layout == "pills":
                return K.enter(r, "pop", run=K.t("base"))
            return K.enter(r, "drop", run=K.t("base"))
        first = rows[0][1]
        entrance = K.stagger([self._title_in(top), row_in(first)], lag=0.5)
        for k, (s, r) in enumerate(rows):
            point = (lambda r=r: K.together([K.pulse(r[0], 1.3)])) if layout in ("column", "steps") else \
                (lambda r=r: K.pulse(r, 1.06))
            self._part(tid, s.get("text"), r, point=point)
            if k == 0:
                continue
            self._moment(s.get("on") or s.get("text"), lambda heard, r=r: row_in(r))
        anim = self._show(tid, whole, entrance)
        self._hold_back(whole, [r for _, r in rows[1:]])
        return anim

    def _row_in(self, row, mark):
        sign, words = row
        sign_in = K.draw(sign, run=K.t("fast"), sfx="tick") if mark == "check" else \
            K.timed(FadeIn(sign, scale=0.3, rate_func=ease_out_back), K.t("fast"), "pop")
        words_in = K.enter(words, None, run=K.t("base")) if K.forced() else \
            K.timed(FadeIn(words, shift=RIGHT * 0.5, rate_func=ease_out_expo), K.t("base"), "swish")
        return K.together([sign_in, words_in])

    # ---------------------------------------------------------------- versus ---------------------------------------
    def m_versus(self, left: dict, right: dict, title: str | None = None, kicker: str | None = None,
                 layout: str = "cards", id: str | None = None):
        """Two sides: they sweep in from the two edges, a VS badge slams between them, then each side's points come
        in. Each side's title is pointed at when said again. `layout`: cards (two cards side by side), split (the
        stage cut in two halves of colour, a line down the middle), stack (one card over the other, VS between)."""
        P = pl.P
        tid = id or self._next_id("versus")
        if layout not in ("split", "stack"):
            layout = "cards"
        if layout == "split":
            return self._versus_split(left or {}, right or {}, title, kicker, tid)
        sides = []
        for s, tone in ((left or {}, K.col("accent")), (right or {}, K.col("second"))):
            cw = 5.0 if layout == "cards" else 9.0
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
        pair = Group(lcard, rcard).arrange(RIGHT if layout == "cards" else DOWN, buff=1.6 if layout == "cards" else 0.9)
        badge_c = Circle(radius=0.55, stroke_width=0, fill_color=K.col("stamp"), fill_opacity=1)
        badge = VGroup(badge_c, K.head("VS", 34, "#FFFFFF", upper=True).move_to(badge_c)).move_to(pair)
        body = Group(pair, badge)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.1)
        a, b = (RIGHT, LEFT) if layout == "cards" else (DOWN, UP)
        sweep = K.together([K.enter(lcard, None), K.enter(rcard, None)]) if K.forced() else \
            K.together([K.timed(FadeIn(lcard, shift=a * 2.5, rate_func=ease_out_expo), K.t("base"), "swish"),
                        K.timed(FadeIn(rcard, shift=b * 2.5, rate_func=ease_out_expo), K.t("base"))])
        entrance = K.stagger([self._title_in(top), sweep, K.slam(badge)], lag=0.6)
        for s, c, content, pts in sides:
            self._part(tid, s.get("title"), c, point=lambda c=c: K.pulse(c, 1.04))
        return self._show(tid, whole, entrance)

    def _versus_split(self, left: dict, right: dict, title, kicker, tid):
        """Versus as the stage cut in two: each half washed in its side's colour and wiped in from its edge, a line
        down the middle, the VS badge slammed on it; each side's title, figure and points set in its half."""
        P = pl.P
        hw, hh = 6.2, 5.6
        halves, contents = [], []
        for k, (s, tone) in enumerate(((left, K.col("accent")), (right, K.col("second")))):
            wash = Rectangle(width=hw, height=hh, stroke_width=0, fill_color=tone, fill_opacity=0.16)
            wash.move_to([(-1 if k == 0 else 1) * hw / 2, 0, 0])
            name = fit(K.head(str(s.get("title", "")), 40, tone if not self.M.get("classic") else P.TITLE), hw - 1.0)
            big = K.number(str(s["value"]), 72, tone) if s.get("value") else None
            pic = self._pic(s.get("file"), 1.8, hw - 1.2)
            pts = [fit(K.body("• " + str(p), 24, P.CREAM, 30), hw - 1.0) for p in (s.get("points") or [])[:4]]
            stack = [m for m in (pic, name, big) if m is not None] + pts
            content = (Group if pic is not None else VGroup)(*stack).arrange(DOWN, buff=0.25)
            if content.height > hh - 0.6:
                content.scale((hh - 0.6) / content.height)
            content.move_to(wash)
            halves.append((s, wash, content))
            contents.append(content)
        line = Line([0, -hh / 2, 0], [0, hh / 2, 0], stroke_color=P.CREAM, stroke_width=3)
        badge_c = Circle(radius=0.6, stroke_width=0, fill_color=K.col("stamp"), fill_opacity=1)
        badge = VGroup(badge_c, K.head("VS", 34, "#FFFFFF", upper=True).move_to(badge_c))
        body = Group(*[h[1] for h in halves], line, *contents, badge)
        whole, top = self._titled(body, title, kicker)
        self._fit(whole, self._box(), grow=1.05, margin=0.3)
        (ls, lw, lc), (rs, rw, rc) = halves
        entrance = K.stagger([
            self._title_in(top),
            K.together([K.timed(FadeIn(lw, shift=RIGHT * 1.5, rate_func=ease_out_expo), K.t("base"), "swish"),
                        K.timed(FadeIn(rw, shift=LEFT * 1.5, rate_func=ease_out_expo), K.t("base")),
                        K.draw(line, run=K.t("base"))]),
            K.together([K.enter(lc, "rise"), K.enter(rc, "rise")]),
            K.slam(badge),
        ], lag=0.5)
        self._part(tid, ls.get("title"), lc, point=lambda: K.pulse(lc, 1.04))
        self._part(tid, rs.get("title"), rc, point=lambda: K.pulse(rc, 1.04))
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
                # Under the print, one size for every print (a long caption on two lines, not shrunk on its own:
                # squeezed into the print's thin edge, a long one came out a third the size of a short one).
                words = str(s["caption"])
                chars = max(12, int(img.width * 5.2))
                cap = pl.T(pl.wrap(words, chars) if len(words) > chars else words, 20, pl.P.CREAM, font=K.font("kicker"),
                           line_spacing=0.85)
                fit(cap, img.width * 1.05)
                cap.next_to(img, DOWN, buff=0.14)
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
        staged = {id(x) for m in [self.stage_items, *self.stage_extra, *self.stage_pending,
                                  getattr(self, "panel_items", None), getattr(self, "panel", None)]
                  if m is not None for x in m.get_family()}
        if self._mwhole.get(tid) is not None and id(self._mwhole[tid]) not in staged:
            # Its template is still on the screen but is leaving in this beat (a card put up in its place before
            # the mark was made): a mark made on it stayed behind over the new picture.
            pl.skipped(f"motion: {target!r} is leaving the screen in this line; not pointed at")
            return None
        colour = pl.role(color) if color else None
        made = self._emphasis(mob, tid, how, colour)
        self._follow_moves(mob, getattr(made, "_m_marks", []))
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
        if how in ("spotlight", "rack"):
            # Everything else on the stage stepped back (spotlight: faded; rack: faded further and shrunk a hair, as a
            # camera racks focus), the part brought forward.
            fam = {id(x) for x in mob.get_family()}
            # The template's other named parts (a chart's other columns, a list's other points).
            pool = [m for m in self._mparts.get(tid, {}).values() if m is not mob]
            others = [m for m in pool if not ({id(x) for x in m.get_family()} & fam) and isinstance(m, VMobject)]
            back = [K.fade_to(m, 0.2 if how == "rack" else 0.3) for m in others]
            if how == "rack":
                back += [K.timed(K.fresh(m.animate.scale(0.97).build()), K.t("base")) for m in others]
            self._dimmed = others
            return K.together(back + [K.pulse(mob, 1.12 if how == "spotlight" else 1.06)])
        if how == "magnify":
            # A lens the size of a hand glass: on a tall part (a chart's column), over its top, where its figure is.
            r = min(max(mob.width, mob.height) * 0.58 + 0.1, 1.3)
            lens = Circle(radius=r, stroke_color=colour or K.col("accent"), stroke_width=6).move_to(mob)
            if mob.height > 2.2 * r:
                lens.move_to([mob.get_center()[0], mob.get_top()[1] - r * 0.9, 0])
            handle = Line(lens.point_at_angle(-math.pi / 4), lens.point_at_angle(-math.pi / 4) + np.array([0.6, -0.6, 0]),
                          stroke_color=colour or K.col("accent"), stroke_width=10)
            glass = VGroup(lens, handle)
            glass.set_z_index(Z_TEMPLATE + 4)
            self._stage_add(glass)
            return marked(K.together([K.timed(FadeIn(glass, scale=1.4, rate_func=ease_out_back), K.t("base"), "pop"),
                                      K.pulse(mob, 1.3, run=K.t("slow"))]), glass)
        if how == "wiggle":
            from manim import Wiggle
            return K.timed(K.baked(Wiggle(mob, scale_value=1.08, rotation_angle=0.08)), K.t("slow"), "pop")
        if how == "bounce":
            up = K.fresh(mob.animate(rate_func=there_and_back).shift(UP * 0.35).build())
            up.panim_xform = True
            return K.timed(up, K.t("base"), "pop")
        if how == "wash":
            tone = colour or K.col("accent")
            shapes = [x for x in mob.family_members_with_points() if isinstance(x, VMobject)
                      and not isinstance(x, Text) and x.get_fill_opacity() > 0.05]
            return K.together([K.refill(x, tone, opacity=max(0.6, float(x.get_fill_opacity()))) for x in shapes] or
                              [K.pulse(mob, 1.08)])
        if how == "strike":
            # Corner to corner, a little past it: across a narrow column as plainly as across a line of words.
            line = Line(mob.get_corner(DL) + np.array([-0.12, -0.08, 0]), mob.get_corner(UR) + np.array([0.12, 0.08, 0]),
                        stroke_color=colour or K.col("stamp"), stroke_width=8)
            line.set_z_index(Z_TEMPLATE + 4)
            self._stage_add(line)
            return marked(K.draw(line, run=K.t("base"), sfx="draw"), line)
        if how == "sweep":
            band = Rectangle(width=mob.width + 0.2, height=0.14, stroke_width=0, fill_color=colour or K.col("accent"),
                             fill_opacity=1).next_to(mob, DOWN, buff=0.06)
            band.set_z_index(Z_TEMPLATE + 4)
            self._stage_add(band)
            return marked(K.grow_from(band, LEFT, run=K.t("base")), band)
        return K.pulse(mob, 1.12)

    def _find_part(self, target: str):
        """A named part on the screen now (an old template's parts are gone with it), by its name or "<id>.<name>";
        or a whole template by its id."""
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
        # A template's own id: the whole template, while it is up.
        whole = self.__dict__.get("_mwhole", {}).get(target)
        if whole is not None and any(id(x) in here for x in whole.family_members_with_points()):
            return whole, target
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
        """_move_stage_tags, remembered (_m_moves) so a mark this beat puts on the picture after the move was made
        (an `emphasis` box, ordered after the card that moved it) goes where the picture goes (_room_moves)."""
        ids = {id(x) for m in [self.stage_items, *self.stage_extra, *self.stage_pending] for x in m.get_family()}
        cover, holder = self.__dict__.get("_cover"), self.__dict__.get("_cover_holder")
        here = {id(x) for top in self.mobjects for x in top.get_family()}
        unseen = cover is not None and holder and id(holder) not in here \
            and any(cover is m for m in holder.submobjects)
        anim = self._move_stage_tags(f, centre, box)
        if unseen and getattr(self, "_cover_holder", None) is False:
            # The engine takes the map's cover out of the picture's card so it keeps the map's size, and puts it up
            # at once: but this picture has not come on yet, and the cover hid the map (and the marker the line
            # puts on it first) from the line's start. Back in the card, at the map's size, it comes on with it.
            self.remove(cover)
            holder.add(cover)
            self._cover_holder = holder
        if anim is not None:
            c0 = np.array(centre, dtype=float)
            anim._m_room = {"parts": [], "f": f, "c0": c0, "c1": np.array([box[0], box[1], 0.0]), "ids": ids}
            self._m_moves = [m for m in self.__dict__.get("_m_moves", []) if not m.get("done")] + [anim._m_room]
        return anim

    def _follow_moves(self, target, marks) -> None:
        """Marks made on `target` (a part of the picture) while a move of it is still to play: they go with it."""
        fam = {id(x) for x in target.get_family()}
        for spec in self.__dict__.get("_m_moves", []):
            if not spec.get("done") and fam & spec["ids"]:
                spec["parts"].extend(m for m in marks if m is not None)

    def _move_stage_tags(self, f: float, centre, box):
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
    # The camera on a picture (its `move`, on the motion engine): a drift the players apply (kenburns: a slow push
    # in and out with a little travel; pan: carried slowly across), or how it comes on (pullback: from close, out).
    CAMERA_MOVES = {"kenburns": dict(period=22.0, amp=0.16, scale=0.09, turn=0.0),
                    "pan": dict(period=28.0, amp=0.45, scale=0.04, turn=0.0)}

    def stage_image(self, path: str, caption: str = "", credit: str = "", labels=(), move: str | None = None,
                    points=()):
        camera = move if move in (*self.CAMERA_MOVES, "pullback") else None
        if camera:
            move = None
        if camera == "pullback":
            self._m_pullback = True
        shown = self._stage_image_look(path, caption, credit, labels, move, points)
        self.__dict__.pop("_m_pullback", None)
        body = getattr(self, "stage_body", None)
        if camera in self.CAMERA_MOVES and body is not None and pl.drifts_on():
            c = body.get_center()
            pl.set_drift([body], dict(self.CAMERA_MOVES[camera], cx=float(c[0]), cy=float(c[1])))
        return shown

    def _stage_image_look(self, path: str, caption: str = "", credit: str = "", labels=(), move: str | None = None,
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


def _ink_on(fill: str) -> str:
    """Dark or light words for a fill, whichever reads."""
    try:
        return "#111111" if pl._luminance(str(fill)) > 0.45 else "#FFFFFF"
    except Exception:  # noqa: BLE001
        return "#111111"


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


# ---------------------------------------------------------------- a template's entrance, chosen ----------------------

def _entering(fn):
    """A template that takes `enter` (pop, rise, drop, slide, zoom, fade, flip, write): its parts come on that way,
    as it is built and as each is said later (motion_kit.FORCE_ENTER, carried by _moment)."""
    import functools

    @functools.wraps(fn)
    def call(self, *args, enter: str | None = None, **kwargs):
        if not enter or enter not in K.ENTRANCES:
            return fn(self, *args, **kwargs)
        before, K.FORCE_ENTER = K.FORCE_ENTER, enter
        try:
            return fn(self, *args, **kwargs)
        finally:
            K.FORCE_ENTER = before
    return call


for _name in [n for n in dir(MotionLecture) if n.startswith("m_") and n not in ("m_stamp", "m_emphasis")]:
    setattr(MotionLecture, _name, _entering(getattr(MotionLecture, _name)))
