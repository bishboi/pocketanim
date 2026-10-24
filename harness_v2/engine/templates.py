"""The motion engine's templates on the current engine: a list, cards, a table, a stamp, a donut, a venn... drawn and
choreographed as the motion engine designed them (motion.py and its mixins), in the current engine's own style.

The current engine owns the primitives; the motion engine adds its looks on top. What the current engine takes from
the motion engine is each template's drawing and its designed choreography (its parts coming on in turn, each on its
words), never the motion engine's look: no texture, no dressed pictures, no transitions between pictures, no idle
motion, no sound effects and no automatic pulses on stressed words. The template's colours and fonts are the style's
(motion_kit in its "classic" mode), and it is put on the stage and laid out by the current engine (`_to_stage`, the
two-at-once layout, the strict chapter's pointing).

A compiled current-engine scene's class is `TemplateLecture` (compile_lecture). A template is called as the motion
engine calls it (`self.m_list(...)`), with the template's `enter` (how its parts come on) when the script gives one.
"""

from __future__ import annotations

import os

import motion_kit as K
import pocket_lecture as pl
from manim import Group
from pocket_lecture import MapLecture

import motion
from motion import MotionLecture, Z_TEMPLATE
from motion_explain import ExplainTemplates
from motion_forms import FormTemplates
from motion_more import MoreTemplates
from motion_story import StoryTemplates

# The motion engine's helpers the templates are drawn with (motion.py's own, never one that overrides the current
# engine's stage or timing: `_to_stage`, `_on_words` and `_stage_add` stay the current engine's, with what the
# templates need added below; `_moment` is motion.py's, with parts held for a later line added below).
_SHARED = ["_after_moves", "_bar_chart", "_box", "_carry_from", "_carry_into", "_carry_key", "_column_chart",
           "_counter_shaped", "_emphasis", "_find_part", "_fit", "_follow_moves", "_hold_back", "_key_of", "_line_chart",
           "_m_legible", "_moving_now", "_next_id", "_part", "_replaces", "_row_in", "_settle_z", "_shown",
           "_stamp_clear", "_title_in", "_titled", "_value_text", "_versus_split"]
# The templates of motion.py itself (the mixins' are inherited).
_TEMPLATES = ["m_cards", "m_chain", "m_chart", "m_counter", "m_document", "m_donut", "m_emphasis", "m_kpi", "m_list",
              "m_polaroids", "m_stamp", "m_title", "m_units", "m_versus"]

# The current engine's own pace: things glide in and stop (no overshoot on an eased entrance), and nothing idles.
CURRENT_MOTION = {"energy": "calm", "idle": "none"}


class TemplateLecture(StoryTemplates, ExplainTemplates, FormTemplates, MoreTemplates, MapLecture):
    """The current engine, able to draw the motion engine's templates (see the module's notes)."""

    CROSS = MotionLecture.CROSS
    CARRY_RUN = MotionLecture.CARRY_RUN
    CARRY_MOST = MotionLecture.CARRY_MOST

    def setup(self):
        super().setup()
        K.SOUNDS = False
        K.M.update(CURRENT_MOTION)
        self.M = K.M
        self._mparts: dict[str, dict] = {}
        self._mwhole: dict[str, object] = {}
        self._m_count = 0

    def _show(self, tid: str, whole, entrance, on: str | None = None, idle: bool = True):
        """A template on the stage with its choreography (motion.py's, without the idle motion)."""
        whole.set_z_index(Z_TEMPLATE)
        self._mwhole[tid] = whole
        anim = self._to_stage(whole, entrance=entrance)
        self._settle_z(whole)
        if anim is not None and on:
            anim.panim_said = str(on)
        for holder in self.__dict__.pop("_m_open", []):
            holder._m_owner = anim
        return anim

    # ---------------------------------------------------------------- parts held for a later line -----------------
    # A template's parts the script holds back (`hold`: their names) do not come on in its own line: each moment the
    # template sets up for one is kept (by the template's id and the part's name) instead of being waited for in the
    # line, and a later line's `reveal` (`of`: the template, `parts`: their names) waits for them there.

    def holding(self, tid: str, names, make):
        """A template made with these parts held back for a later line's reveal."""
        self._m_hold = (str(tid), {pl._norm(n) for n in names or []})
        try:
            return make()
        finally:
            self.__dict__.pop("_m_hold", None)

    def _moment(self, say, build, run: float | None = None) -> None:
        hold = self.__dict__.get("_m_hold")
        if hold:
            alts = say if isinstance(say, (list, tuple)) else [say]
            key = next((pl._norm(a) for a in alts if pl._norm(a) in hold[1]), None)
            if key is not None:
                self.__dict__.setdefault("_m_held", {}).setdefault(hold[0], {})[key] = (say, build, run, K.FORCE_ENTER)
                return
        MotionLecture._moment(self, say, build, run)

    def reveal_held(self, tid: str, names, on: str | None = None):
        """A template's held parts brought on in this line: on `on` (the reveal's words), else each on its own
        name as the line says it, else in its turn. None (the parts come by their moments)."""
        held = self.__dict__.get("_m_held", {}).get(str(tid), {})
        whole = self._mwhole.get(str(tid))
        if whole is None or not self._shown(whole):
            pl.skipped(f"reveal: {tid!r} is not on the screen")
            return None
        for name in names or []:
            got = held.pop(pl._norm(name), None)
            if got is None:
                pl.skipped(f"reveal: {tid!r} holds no part {name!r}")
                continue
            say, build, run, force = got
            before, K.FORCE_ENTER = K.FORCE_ENTER, force
            try:
                MotionLecture._moment(self, on or say, build, run)
            finally:
                K.FORCE_ENTER = before
            # Its template is up already (no owner to wait for).
            self.__dict__.get("_m_open", []).clear()
        return None

    def _stage_add(self, mob):
        out = super()._stage_add(mob)
        self._settle_z(mob)
        return out

    def _on_words(self, given: list, words, seconds: float, text: str) -> list:
        """The engine's; a moment that may be said in more than one way (an event by its words or by its date) is
        timed by whichever the line says, and a template's part never comes on before its template."""
        if words:
            for anim, _ in given:
                alts = getattr(anim, "panim_alts", None)
                if alts:
                    heard = [(self._said(words, a), a) for a in alts]
                    heard = [(t_, a) for t_, a in heard if t_ is not None]
                    if heard:
                        anim.panim_said = min(heard)[1]
        out = super()._on_words(given, words, seconds, text)
        start = lambda c: float(c[0]) if isinstance(c, (list, tuple)) and c else 0.0  # noqa: E731
        owners = {id(a): c for a, c in out}
        moved = False
        for i, (a, c) in enumerate(out):
            owner = getattr(a, "_m_owner", None)
            oc = owners.get(id(owner)) if owner is not None else None
            if oc is None:
                continue
            run = float(oc[1]) if isinstance(oc, (list, tuple)) and len(oc) > 1 and oc[1] else 0.6
            floor = start(oc) + min(0.6, run * 0.5)
            if start(c) < floor:
                out[i] = (a, [round(floor, 3), *(c[1:] if isinstance(c, (list, tuple)) else [None])])
                moved = True
        if moved:
            out.sort(key=lambda g: start(g[1]))
        return out


for _name in [*_SHARED, *_TEMPLATES]:
    setattr(TemplateLecture, _name, MotionLecture.__dict__[_name])

__all__ = ["TemplateLecture"]
