"""STEM boards: worked solutions and problems on the whole frame, and free-form Manim drawn on it.

A lecture for mathematics, physics or chemistry teaches on a board: the whole frame, no side panel. On it:

* free     a drawing in the model's own Manim (free_check.py), built over the beats that explain it;
* work     a worked solution, a line per beat, beside the figure it works on;
* problem  a long question: its statement across the top, its figure on the left, its solution on the right;
* zoom     the camera closer on a part of a figure.

The drawing is BoardMixin, which pocket_lecture's MapLecture inherits.
"""

from __future__ import annotations

import math
import re

def _label_text(text) -> str:
    """A label as it reads: TeX-ish m_1, v^2, \\theta become m₁, v², θ."""
    import pocket_lecture as pl

    text = str(text)
    return pl.unicode_math(text) if re.search(r"[_^\\]", text) else text


# ════════════════════════════════════════════════════════════════════════
#  Drawing: the board, sketches, graphs, worked solutions, problems
# ════════════════════════════════════════════════════════════════════════

# The board: the whole frame below the key-point strip and above the caption (centre x, centre y, w, h).
BOARD = (0.0, -0.13, 13.5, 5.65)
STRIP_Y = 3.1
LABEL_SIZE = 20


def _bounds(mobs):
    import numpy as np

    pts = [m.get_all_points() for m in mobs if len(m.get_all_points())]
    if not pts:
        return None
    arr = np.vstack(pts)
    return arr[:, 0].min(), arr[:, 1].min(), arr[:, 0].max(), arr[:, 1].max()


def _moving(builder):
    """A part's `.animate` move as an animation the exporter writes as a move of that part (an `xform` verb with
    its rate), not as a morph into a copy: in a group, Manim makes the builder a transform, which the program
    played by keeping the part where it was and adding a moved copy."""
    anim = builder.build()
    anim.panim_xform = True
    return anim


def _labels_and_ink(mobs):
    labels, ink = [], []
    for mob in mobs:
        for part in mob.get_family():
            if getattr(part, "is_label", False):
                labels.append(part)
    label_family = {id(x) for lab in labels for x in lab.get_family()}
    for mob in mobs:
        for part in mob.family_members_with_points():
            if id(part) not in label_family:
                ink.append(part)
    return labels, ink


def curve_samples(points, per_curve: int = 8):
    """Points along a VMobject's cubic curves (x, y), not only its anchors: a long straight edge has anchors at
    its ends alone, and a label across its middle would not touch one."""
    import numpy as np

    pts = np.asarray(points, dtype=float)
    n = len(pts) // 4 * 4
    if n < 4:
        return pts[:, :2]
    b = pts[:n].reshape(-1, 4, 3)
    t = np.linspace(0.0, 1.0, per_curve)[:, None, None]
    curve = ((1 - t) ** 3) * b[:, 0] + 3 * ((1 - t) ** 2) * t * b[:, 1] + 3 * (1 - t) * t * t * b[:, 2] \
        + (t ** 3) * b[:, 3]
    return curve.reshape(-1, 3)[:, :2]


def _settle_labels(mobs, box, gap: float = 0.06, backing=None) -> list:
    """Move each label that sits on a line, on a filled part or on another label to the nearest clear spot
    around where it was put (up to about a label's size away), and keep it inside the box.

    With `backing` (the board's colour), a label that no clear spot was found for gets a patch of the board behind
    it, so the line under it stops short of the words instead of running through them. Returns the labels that
    still sit on a line (backed or not)."""
    import numpy as np

    labels, ink = _labels_and_ink(mobs)
    if not labels:
        return []
    parts = [curve_samples(part.points, 24) for part in ink if len(part.points) >= 2]
    # Whose each label and shape is, and the bodies (a ball, a block) another element's label must not sit in.
    owner = {}
    for index, mob in enumerate(mobs):
        for part in mob.get_family():
            owner.setdefault(id(part), index)
    bodies = []
    for part in ink:
        if type(part).__name__ in ("Circle", "Rectangle", "Polygon", "Square", "RoundedRectangle") and part.width > 0.2 \
                and part.height > 0.2:
            b = _bounds([part])
            bodies.append((owner.get(id(part)), b))
    cx, cy, w, h = box
    lo_x, hi_x, lo_y, hi_y = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    placed = []
    crossing = []

    def box_of(centre, lab):
        return (centre[0] - lab.width / 2 - gap, centre[1] - lab.height / 2 - gap,
                centre[0] + lab.width / 2 + gap, centre[1] + lab.height / 2 + gap)

    def cost(b, own, mine=None):
        # Each line or shape the label sits on counts once, however long the stretch under it.
        c = -own
        area = max((b[2] - b[0]) * (b[3] - b[1]), 1e-6)
        for who, q in bodies:
            if who == mine:
                continue
            ox = min(b[2], q[2]) - max(b[0], q[0])
            oy = min(b[3], q[3]) - max(b[1], q[1])
            if ox > 0 and oy > 0 and ox * oy > 0.25 * area:
                c += 3          # inside another part's body: "Kick F" written across the ball
        for pts in parts:
            if ((pts[:, 0] > b[0]) & (pts[:, 0] < b[2]) & (pts[:, 1] > b[1]) & (pts[:, 1] < b[3])).any():
                c += 1
        for p in placed:
            ox = min(b[2], p[2]) - max(b[0], p[0])
            oy = min(b[3], p[3]) - max(b[1], p[1])
            if ox > 0 and oy > 0:
                c += 40 + 200 * ox * oy
        # Out of the box: pushed back in by the fit later, but shrinking the whole drawing for it costs.
        c += 2 * (max(0, lo_x - b[0]) + max(0, b[2] - hi_x) + max(0, lo_y - b[1]) + max(0, b[3] - hi_y))
        return c

    for lab in labels:
        home = lab.get_center()[:2].copy()
        # A label may sit on its own element's anchor: only a crossing, not a touch, counts against it.
        own = 0
        mine = owner.get(id(lab))
        best, best_cost = home, cost(box_of(home, lab), own, mine)
        if best_cost <= 0:
            placed.append(box_of(home, lab))
            continue
        step_x, step_y = lab.width / 2 + 0.12, lab.height / 2 + 0.1
        for reach in (0.6, 1.0, 1.5, 2.1):
            for ang in range(0, 360, 30):
                t = math.radians(ang)
                at = home + np.array([math.cos(t) * step_x * reach, math.sin(t) * step_y * reach])
                c = cost(box_of(at, lab), own, mine) + 0.25 * reach
                if c < best_cost - 1e-6:
                    best, best_cost = at, c
            if best_cost <= 0.25 * reach:
                break
        lab.move_to([best[0], best[1], 0])
        placed.append(box_of(best, lab))
        b = box_of(best, lab)
        if any(((pts[:, 0] > b[0]) & (pts[:, 0] < b[2]) & (pts[:, 1] > b[1]) & (pts[:, 1] < b[3])).any()
               for pts in parts):
            crossing.append(lab)
            if backing is not None:
                _back(lab, backing)
    return crossing


def _back(label, colour) -> None:
    """A patch of the board behind a label (part of it: it moves, fades and is revealed with it)."""
    from manim import RoundedRectangle

    if getattr(label, "backed", False):
        return
    patch = RoundedRectangle(corner_radius=0.06, width=label.width + 0.14, height=label.height + 0.1, stroke_width=0,
                             fill_color=colour, fill_opacity=1).move_to(label.get_center())
    patch.is_backing = True
    label.add_to_back(patch)
    label.backed = True


def _light(colour) -> bool:
    """A light background: white text and lines would not show on it."""
    from manim import ManimColor

    r, g, b = ManimColor(colour).to_rgb()
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55


def _ink(mobjects, ink) -> None:
    """Manim's default white, on a light style's board, in the style's ink instead."""
    from manim import VMobject

    for root in mobjects:
        for m in getattr(root, "get_family", lambda: [])():
            if not isinstance(m, VMobject):
                continue
            try:
                if m.get_stroke_width() > 0 and m.get_stroke_color().to_hex().upper().startswith("#FFFFFF"):
                    m.set_stroke(color=ink)
                if m.get_fill_opacity() > 0 and m.get_fill_color().to_hex().upper().startswith("#FFFFFF"):
                    m.set_fill(color=ink)
            except Exception:  # noqa: BLE001 -- a part without colours
                continue


def ink_animations(animations, ink) -> None:
    """_ink over what a play is about to show: each animation's object and target, through groups."""
    stack = list(animations)
    found = []
    while stack:
        anim = stack.pop()
        stack.extend(getattr(anim, "animations", []) or [])
        for name in ("mobject", "target_mobject"):
            m = getattr(anim, name, None)
            if m is not None:
                found.append(m)
    _ink(found, ink)


class BoardMixin:
    """The board layout and the STEM drawings, for pocket_lecture's MapLecture."""

    board_mode = False

    # ---------------- the board layout ----------------
    def board(self) -> None:
        """Teach on the whole frame: no side panel; panel titles and facts become one short key-point strip."""
        self.board_mode = True
        self.STAGE = BOARD
        self.strip = {"title": None, "point": None}

    def leave_board(self) -> None:
        self.board_mode = False
        self.__dict__.pop("STAGE", None)

    def _strip(self, title=None, point=None, clear=False):
        """Put a title and/or a key point in the strip over the board; the old ones fade."""
        import pocket_lecture as pl
        from manim import AnimationGroup, FadeIn, FadeOut, LEFT, RIGHT

        going, coming = [], []
        if clear or title is not None:
            for k in ("title", "point"):
                if self.strip.get(k) is not None:
                    going.append(FadeOut(self.strip[k]))
                    self.strip[k] = None
        if point is not None and self.strip.get("point") is not None:
            going.append(FadeOut(self.strip["point"]))
            self.strip["point"] = None
        left = -6.7
        if title is not None:
            self.strip["title"] = title.move_to([left, STRIP_Y, 0], aligned_edge=LEFT)
            title.set_z_index(pl.Z_PANEL_TEXT)
            coming.append(FadeIn(title, shift=RIGHT * 0.15))
        if point is not None:
            head = self.strip.get("title")
            x = head.get_right()[0] + 0.45 if head is not None else left
            pl.fit(point, 6.7 - x)
            self.strip["point"] = point.move_to([x, STRIP_Y, 0], aligned_edge=LEFT)
            point.set_z_index(pl.Z_PANEL_TEXT)
            coming.append(FadeIn(point, shift=RIGHT * 0.15))
        if not going and not coming:
            return None
        return AnimationGroup(AnimationGroup(*going), AnimationGroup(*coming), lag_ratio=0.5) if going else \
            AnimationGroup(*coming)

    def board_title(self, title: str, sub: str | None = None):
        import pocket_lecture as pl
        from manim import BOLD, LEFT, VGroup, RIGHT

        from manim import RoundedRectangle

        text = title.upper() if pl.TH["upper"] else title
        head = VGroup(pl.T(text, 32, pl.P.TITLE, font=pl.TH["serif"], weight=BOLD))
        if sub:
            head.add(pl.T(sub, 21, pl.P.MUTED))
            head.arrange(RIGHT, buff=0.25, aligned_edge=[0, -1, 0])
        pl.fit(head, 7.3)
        # A slim pill of the accent before the topic's name.
        mark = pl._flat(RoundedRectangle(corner_radius=0.035, width=0.07, height=head[0].height * 1.1,
                                         fill_color=pl.P.SAND, fill_opacity=1, stroke_width=0))
        mark.next_to(head, LEFT, buff=0.18).align_to(head[0], [0, 0, 0]).set_y(head[0].get_center()[1])
        return self._strip(title=VGroup(mark, head))

    def board_point(self, text: str, color: str | None = None):
        import pocket_lecture as pl
        from manim import Dot, VGroup, RIGHT

        from manim import RoundedRectangle

        # The key point in a soft pill: a dot of the accent, then the words.
        dot = Dot(radius=0.07, color=color or pl.P.SAND)
        line = pl.T(str(text), 23, color or pl.P.CREAM)
        words = VGroup(dot, line).arrange(RIGHT, buff=0.18)
        pill = pl._flat(RoundedRectangle(corner_radius=(words.height + 0.24) / 2, width=words.width + 0.5,
                                         height=words.height + 0.24, fill_color=pl._tint_on_bg(color or pl.P.SAND, 0.12),
                                         fill_opacity=1, stroke_color=pl._tint_on_bg(color or pl.P.SAND, 0.45),
                                         stroke_width=1.2))
        words.move_to(pill)
        return self._strip(point=VGroup(pill, words))

    def board_stat(self, value: str, label: str, color: str | None = None):
        import pocket_lecture as pl
        from manim import BOLD, VGroup, RIGHT, DOWN

        group = VGroup(pl.T(str(value), 26, color or pl.P.GOLD, font=pl.TH["serif"], weight=BOLD),
                       pl.T(str(label), 18, pl.P.MUTED)).arrange(RIGHT, buff=0.2, aligned_edge=DOWN)
        return self._strip(point=group)

    def board_bars(self, items, color: str | None = None, unit: str = ""):
        """A bar chart across the board: each bar a rounded bar on a faint track of the full length, its value in
        bold at its end; the bars grow out from the left one after another."""
        import pocket_lecture as pl
        from manim import (BOLD, AnimationGroup, FadeIn, GrowFromEdge, LaggedStart, LEFT, RIGHT, Group,
                           RoundedRectangle, VGroup)

        cx, cy, w, h = self.STAGE
        items = list(items)[:8]
        top = max((float(v) for _, v in items), default=1.0) or 1.0
        tone = color or pl.P.SAND
        full, thick = 7.0, 0.44
        rows = VGroup()
        for name, value in items:
            label = pl.fit(pl.T(str(name), 20, pl.P.CREAM, weight=BOLD), 3.0)
            track = pl._flat(RoundedRectangle(corner_radius=thick / 2, width=full, height=thick,
                                              fill_color=pl._tint_on_bg(tone, 0.12), fill_opacity=1, stroke_width=0))
            length = max(thick, full * float(value) / top)
            bar = pl._flat(RoundedRectangle(corner_radius=thick / 2, width=length, height=thick, fill_color=tone,
                                            fill_opacity=1, stroke_width=0))
            num = pl.T(f"{float(value):g}{unit}", 19, pl.P.CREAM, weight=BOLD)
            rows.add(VGroup(label, track, bar, num))
        width = max((r[0].width for r in rows), default=1.0)
        for i, r in enumerate(rows):
            y = -i * 0.72
            r[0].move_to([-width, y, 0], aligned_edge=RIGHT)
            r[1].move_to([0.2, y, 0], aligned_edge=LEFT)
            r[2].move_to([0.2, y, 0], aligned_edge=LEFT)
            r[3].next_to(r[2], RIGHT, buff=0.18)
            if r[3].get_right()[0] > r[1].get_right()[0] + 0.05 and r[2].width > r[3].width + 0.5:
                # A bar near full length: its value inside its end, in the board's colour.
                r[3].set_color(pl.P.BG).next_to(r[2].get_right(), LEFT, buff=0.18)
        self._fit_stage(rows, grow=1.2)
        entrance = LaggedStart(*[AnimationGroup(FadeIn(r[0], shift=RIGHT * 0.15), FadeIn(r[1]),
                                                GrowFromEdge(r[2], LEFT), FadeIn(r[3], shift=LEFT * 0.1))
                                 for r in rows], lag_ratio=0.25)
        return self._to_stage(Group(rows), entrance=entrance)

    def _colour(name, default):
        import pocket_lecture as pl

        if not name:
            return default
        text = str(name)
        if text.startswith("#"):
            return text
        return getattr(pl.P, text.upper(), default)

    # ---------------- free-form Manim (free_check.py) ----------------
    def free(self, key: str, text: str, code: str, pad: float | None = None, area: str | None = None,
             cues: list | None = None) -> float:
        """One beat drawn by a block of model-written Manim: the line is spoken, the block runs (its plays land
        while the line is said), and the rest of the line is held. Blocks with the same key share their names, so
        a figure built on one beat is moved, ringed or transformed on the next; the first block of a key clears
        the stage. What the blocks leave on the board goes with the stage, at the next picture or the chapter's
        end. `area` "left" (its first block's): the figure is drawn in the board's left half, so a working, a
        question or a card goes in the right half without moving it, and stays while later blocks explain it."""
        import free_check
        import numpy as np
        import pocket_lecture as pl
        from manim import FadeIn, FadeOut, Group

        pad = pl.BEAT_PAD if pad is None else pad
        if getattr(self, "_free_key", None) != key:
            going = self._stage_leaving()
            if self._full_figure is not None:
                going.append(FadeOut(self._full_figure))
                self._full_figure = None
            if going:
                self.play(*going, run_time=0.5)
            self._free_key = key
            self._free_beat = 0
            self._free_names = free_check.namespace(self)
            self._free_owned = []
            self._free_group = None
            self._free_area = "left" if area == "left" else "full"
        else:
            # The figure goes on after something else took the stage (a question card, a definition): that goes,
            # and the figure's parts it faded come back, so the next block draws on its own figure, not over a card.
            mine = getattr(self, "_free_group", None)
            others = [m for m in [self.stage_items, *self.stage_extra]
                      if m is not mine and (len(m.get_family()) > 1 or len(m.points))]
            if getattr(self, "_free_area", "full") == "left" and mine is not None and self.stage_body is mine:
                # A figure in the left half: what sits wholly in the right half (the working, a question, a card)
                # stays while this block explains the figure.
                others = [m for m in others if m.get_left()[0] < self.STAGE[0] - 0.15]
            if others or (self.stage_body is not None and self.stage_body is not mine):
                self._free_going_on = True          # the figure that goes on keeps its parts
                try:
                    going = [a for a in self._stage_leaving() if a.mobject is not mine]
                finally:
                    self._free_going_on = False
                here = {id(x) for m in self.mobjects for x in m.get_family()}
                # Its parts come back only from under a card (a question, a definition, an equation) that was set
                # over or beside it. A picture, a diagram or a timeline that took the stage ended the figure: its old
                # words brought back landed over the next block's (a block draws again what it needs).
                carded = all(any(getattr(x, flag, False) for x in m.get_family()
                                 for flag in ("is_text_card", "is_aside", "is_term_strip")) for m in others)
                if not carded:
                    self._free_owned = [m for m in self._free_owned if id(m) in here]
                    mine = self._free_group = Group(*self._free_owned) if self._free_owned else None
                    self._free_home = None
                back = [FadeIn(m) for m in self._free_owned if id(m) not in here]
                # Moved aside for a working or a card beside it: home again, where its blocks draw.
                home = getattr(self, "_free_home", None)
                if mine is not None and home is not None and mine.width > 0.01 and \
                        (abs(mine.width - home[1]) > 0.01 or np.linalg.norm(mine.get_center() - home[0]) > 0.01):
                    back.append(_moving(mine.animate.scale(home[1] / mine.width).move_to(home[0])))
                if going or back:
                    self.play(*going, *back, run_time=0.5)
                # Home again, where its coordinates hold: what redraws itself (always_redraw, a tracker's sweep)
                # goes on, frozen only while the figure was moved aside.
                for x in (mine.get_family() if mine is not None else []):
                    for u in x.__dict__.pop("panim_held_updaters", []):
                        x.add_updater(u)
        wav, seconds = pl.narrate(text)
        self._log("beat", text=text, seconds=round(seconds, 3), wav=wav)
        pl._progress_beat()
        cap = self.caption(text)
        self._speak(wav, seconds)
        if self.cap is not None:
            self.remove(self.cap)
        self.add(cap)
        self.cap = cap
        before = {id(m) for m in self.mobjects}
        start = self.renderer.time
        self._free_ink = _light(pl.P.BG)
        # Which of the figure's blocks this is, so a failure names it ("manim block 'fig5' beat 2") and the repair
        # after the build (harness/app/lib/manimcoder.ts repairBuiltManim) knows which block to mend.
        self._free_beat = getattr(self, "_free_beat", 0) + 1
        try:
            # A block that fails here (it passed the check before the render) leaves out the rest of its drawing;
            # the line is still spoken, and the reason is reported with the build.
            # Words a block puts inside a cell, a node or a box need no patch of board behind them (backed_text).
            import backed_text

            plays, adds = type(self).play, type(self).add

            played = [0]
            waiting = [False]

            def play(*animations, **kwargs):
                if waiting[0]:
                    return plays(self, *animations, **kwargs)        # the hold a cue asks for (Scene.wait)
                # `cues` (align_cues.py, after the voice is made): when each of the block's plays starts, in
                # seconds into the line, so it lands on the words it goes with; a play the block reaches later
                # than its cue starts at once.
                index = played[0]
                played[0] += 1
                cue = cues[index] if cues and index < len(cues) else None
                if isinstance(cue, (int, float)):
                    gap = start + float(cue) - self.renderer.time
                    if gap > 0.02:
                        waiting[0] = True
                        try:
                            type(self).wait(self, gap)
                        finally:
                            waiting[0] = False
                backed_text.settle(self, backed_text.arriving_in(animations))
                return plays(self, *animations, **kwargs)

            def add(*mobjects):
                backed_text.settle(self, mobjects)
                return adds(self, *mobjects)

            self.play, self.add = play, add
            self.safe(lambda: free_check.run_block(code, self._free_names, f"<{key}>"),
                      f"manim block {key!r} beat {self._free_beat}")
        finally:
            self.__dict__.pop("play", None)
            self.__dict__.pop("add", None)
            self._free_ink = None
        spent = self.renderer.time - start
        new = [m for m in self.mobjects if id(m) not in before]
        if _light(pl.P.BG):
            _ink(new, pl.P.CREAM)
        # Parts moved with the figure are inside a group on the scene now (a move plays on the group), not top level.
        here = {id(x) for m in self.mobjects for x in m.get_family()}
        previous = self._free_group
        # A part swapped in a figure that was moved (ReplacementTransform(ray, new_ray), become) takes the old
        # part's place inside the figure's group, not on the scene's top level: it is the figure's too, or the
        # next move left it behind at full size, drawn over what came beside the figure.
        grouped = [x for m in self.mobjects for x in m.get_family() if getattr(x, "free_key", None) == key]
        swapped = [m for g in {id(g): g for g in grouped}.values() for m in g.submobjects]
        owned = [m for m in [*self._free_owned, *new, *swapped] if id(m) in here and m is not self.cap]
        self._free_owned = list({id(m): m for m in owned}.values())
        # What else is on the stage and still showing (a working, a card beside a figure in the left half) stays
        # with it; the blocks' drawing is the stage's now: the next picture, or the chapter's end, takes it away.
        kept = [m for m in self.stage_extra if m is not previous and any(id(x) in here for x in m.get_family())]
        self._free_group = Group(*self._free_owned) if self._free_owned else None
        self.stage_extra = ([self._free_group] if self._free_group is not None else []) + kept
        if self._free_group is not None:
            if self._free_area == "left" and self._free_group.get_right()[0] > self.STAGE[0] + 0.3:
                # Drawn past the left half after all: treated as a whole-board figure (moved aside for a working).
                self._free_area = "full"
                self._log("free_area", key=key, note="drawn past the left half; moved aside instead")
            self._free_group.free_area = self._free_area
            self._free_group.free_key = key
        # The figure is the stage's drawing: a working, a question or a card that comes next goes beside it (the
        # figure moved into the left half) instead of over it, and the figure's next block moves it home first.
        self.stage_body = self._free_group
        self._free_home = (self._free_group.get_center().copy(), self._free_group.width) \
            if self._free_group is not None else None
        self._beat_new, self._beat_revealed, self._beat_asides, self._beat_added = [], [], [], []
        rest = seconds + pad - spent
        if rest > 0.02:
            self.wait(rest)
        self._voice_done(pad)
        return seconds

    # ---------------- live pictures (live.py) ----------------
    def _live_start(self, mob, step, mode: str = "loop", keep: bool = False):
        """Run `step(t, p)` on `mob` every frame from now: t seconds since it started, p (0..1) through the line
        it starts on. It stops when the next line starts, unless `keep` (then when its picture leaves)."""
        state = {"t": 0.0, "frames": 0}
        from manim import config

        fps = float(config.frame_rate or 30)
        import artstyle

        # Its parts move, so the art style paints them after every step and adds no extras that would stay behind.
        artstyle.mark_live(mob)
        drawn = step

        def step(t, p):  # noqa: F811 -- the step, then the art style's colours on what it changed
            with artstyle.drawing():          # a readout it writes is in the art style's font
                drawn(t, p)
            artstyle.live_paint(mob)

        def updater(_mob, dt):
            # Once per frame: a part inside two groups on stage is updated twice a frame, and counting both ran
            # its clock at double speed (a trace done halfway through its line).
            key = (getattr(self.renderer, "num_plays", 0), round(float(getattr(self, "last_t", 0.0)), 6))
            if key == state.get("key"):
                return
            state["key"] = key
            # The clock counts frames, not the seconds between them: the exporter samples a play in steps of its
            # length over its frame count (not quite 1/30 s), and a motion that repeats every 120 frames must
            # come back to exactly the same drawing, or its clip cannot be stored once and played round.
            if dt > 0:
                state["frames"] += 1
            state["t"] = state["frames"] / fps
            span = max(float(getattr(self, "_beat_span", 4.0)), 0.5)
            try:
                step(state["t"], min(1.0, state["t"] / span) if mode == "process" else 0.0)
            except Exception as error:  # noqa: BLE001 -- one live picture that fails stops moving; the lecture goes on
                import pocket_lecture as pl

                mob.remove_updater(updater)
                pl.SKIPPED.append(f"a live picture stopped: {type(error).__name__}: {error}"[:300])

        mob.add_updater(updater)
        if not hasattr(self, "_live"):
            self._live = []
        self._live.append({"mob": mob, "updater": updater, "keep": keep, "fresh": True})

    def _live_next(self) -> None:
        """At a new line: the live pictures of the line before stop (kept ones go on while they are on stage)."""
        on_stage = {id(m) for top in self.mobjects for m in top.get_family()}
        going = []
        for entry in getattr(self, "_live", []):
            if entry["fresh"]:
                entry["fresh"] = False
                going.append(entry)
            elif entry["keep"] and id(entry["mob"]) in on_stage:
                going.append(entry)
            else:
                entry["mob"].remove_updater(entry["updater"])
        self._live = going

    def zoom(self, key: str, node: str | None = None, scale: float = 1.8, inside: bool = False):
        """Move in on a part of the picture on the stage (scaled up about it and brought to the middle), or, with
        no node, back out to the whole picture. `inside`: no further in than keeps the whole picture on the stage
        (a focus's own push in), the part as near the middle as that allows."""
        import numpy as np
        from manim import DL, UR, AnimationGroup

        d = self.diagrams.get(key)
        body = getattr(self, "stage_body", None)
        if not d or d.get("gone") or body is None:
            return None
        zoomed = getattr(self, "_zoomed", {})
        self._zoomed = zoomed
        # each piece on the stage moves by itself: a new Group around them would be added to the scene as a
        # second copy of the picture
        on_stage = set(map(id, self.get_mobject_family_members()))
        # A picture written in piece by piece is on the scene as its pieces, not as one group: those move.
        whole = {id(m) for m in body.get_family()}
        pieces = [body] if id(body) in on_stage else [m for m in self.mobjects if id(m) in whole]
        parts, seen = [], set()
        for m in [*pieces, *self.stage_extra]:
            if id(m) in on_stage and id(m) not in seen:
                seen.add(id(m))
                parts.append(m)

        def baked(*anims):
            # the phone gets this as a clip of whole frames (export_dsl asks_to_bake): the parts sit inside the
            # stage card, and a verb for one would move a copy of it over the unmoved picture
            group = AnimationGroup(*anims)
            group._panim_bake = True
            return group

        if not parts:
            return None
        # The parts not on the screen yet move too: the ones this beat brings in (a node revealed with this
        # focus) and the ones still to come. Left where they were, a node revealed with the focus came in at its old
        # size beside the moved picture, and the ring meant for it circled an empty patch.
        moving = {id(x) for m in parts for x in m.get_family()}
        waiting, seen_w = [], set()
        for m in [*self.stage_extra, *getattr(self, "stage_pending", []), *d.get("nodes", {}).values(),
                  *(e[2] for e in d.get("edges", ()))]:
            if id(m) in moving or id(m) in seen_w:
                continue
            seen_w.update(id(x) for x in m.get_family())
            waiting.append(m)
        record = zoomed.get(key)

        def undo(m):
            # back to the picture as it was before the move in
            if record:
                f0, about0, middle0 = record
                m.shift(about0 - middle0).scale(1 / f0, about_point=about0)
            return m

        def flat(p):
            if not record:
                return np.array(p, dtype=float)
            f0, about0, middle0 = record
            return (np.array(p, dtype=float) - middle0) / f0 + about0

        if node is None:
            if not record:
                return None
            zoomed.pop(key)
            self._zoom_place = undo
            for m in waiting:
                undo(m)
            return baked(*(undo(m.animate) for m in parts))
        if node not in d.get("nodes", {}):
            return None
        box = self.STAGE
        if any(getattr(m, "is_aside", False) for m in self.stage_extra):
            box = self._halves()[0]
        cx, cy, w, h = box
        # How far in: as asked, but never past the stage. Grown past it, the picture ran under the chapter's heading
        # and the caption, and its labels over each other.
        every = [m for m in [*parts, *waiting] if len(m.get_family()) and (m.width > 1e-3 or m.height > 1e-3)]
        lows = [flat(m.get_corner(DL)) for m in every]
        highs = [flat(m.get_corner(UR)) for m in every]
        x0, y0 = min(p[0] for p in lows), min(p[1] for p in lows)
        x1, y1 = max(p[0] for p in highs), max(p[1] for p in highs)
        f = max(1.1, min(float(scale or 1.8), 3.0))
        about = flat(d["nodes"][node].get_center())
        middle = np.array([cx, cy, 0.0])
        if inside:
            fit = min((w - 0.3) / max(x1 - x0, 0.01), (h - 0.3) / max(y1 - y0, 0.01))
            f = min(f, fit)
            if f < 1.1 and not record:
                return None
            f = max(f, 1.0)
            # The part as near the middle as the picture allows, the whole picture inside the stage.
            mx = min(max(cx, cx - w / 2 + 0.15 - f * (x0 - about[0])), cx + w / 2 - 0.15 - f * (x1 - about[0]))
            my = min(max(cy, cy - h / 2 + 0.15 - f * (y0 - about[1])), cy + h / 2 - 0.15 - f * (y1 - about[1]))
            middle = np.array([mx, my, 0.0])

        def place(m):
            undo(m)
            return m.scale(f, about_point=about).shift(middle - about)

        zoomed[key] = (f, about, middle)
        self._zoom_place = place
        for m in waiting:
            place(m)
        return baked(*(place(m.animate) for m in parts))

    def _zoom_follow(self, f: float, centre, shift) -> None:
        """The stage's picture was scaled by f about `centre` and shifted (to make room for a card beside it): a
        picture moved in on is still moved in on, and moving back out has to land where the picture now is."""
        import numpy as np

        for key, (f0, about0, middle0) in list(getattr(self, "_zoomed", {}).items()):
            moved = lambda p: (np.array(p, dtype=float) - centre) * f + centre + shift  # noqa: E731
            self._zoomed[key] = (f0, moved(about0), moved(middle0))

    # ---------------- worked solutions ----------------
    @staticmethod
    def _is_prose(line: str) -> bool:
        """A sentence rather than maths: words outside \\text{} and outside TeX's own commands and their
        arguments (\\rm total, \\mathrm{ext} are maths), or Hindi outside \\text{}."""
        bare = re.sub(r"\\(?:text|mathrm|textrm|mathbf|operatorname|rm|it|bf)\s*\{[^{}]*\}", "", line)
        bare = re.sub(r"\\(?:rm|it|bf)\s+\w+|[_^]\{[^{}]*\}|\\[a-zA-Z]+", "", bare)
        if re.search(r"[\u0900-\u097F]", bare):
            return True
        # Three words in a row is a sentence; a lone unit or name (total, max) is not.
        return bool(re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}\s+[A-Za-z]{2,}", bare))

    def _work_line(self, line: str, width: float):
        """One line of working: typeset maths (MathTex, drawn as text without LaTeX), or a sentence."""
        import pocket_lecture as pl
        from manim import MathTex

        text = str(line)
        size = 30
        if not self._is_prose(text):
            try:
                mob = MathTex(text, color=pl.P.CREAM, font_size=size + 4)
                return pl.fit(mob, width)
            except Exception:  # noqa: BLE001 -- TeX LaTeX cannot compile: the same line as text
                pass
        return pl.fit(pl.T(pl.wrap(pl.unicode_math(text) if re.search(r"[_^\\]", text) else text, 48), 22,
                           pl.P.CREAM, line_spacing=0.9), width)

    def _stage_aside(self, box):
        """Move what is on the stage (and its parts still to come) into `box`, making room beside it."""
        from manim import Group

        body = getattr(self, "stage_body", None)
        if body is None:
            return None
        # Sized by what shows, but moved as the group that was put on stage (with its card, invisible on the
        # board): moving a part of a shown group left the exporter a transform its preview could not play.
        whole = Group(body, *self.stage_extra, *self.stage_pending)
        cx, cy, w, h = box
        f = min(w / max(whole.width, 0.01), h / max(whole.height, 0.01), 1.0)
        return self._move_stage(f, whole.get_center(), box)

    def _new_column(self, key, area, title, anims):
        """Where a working's lines go: the top of `area`, under its title if it has one."""
        import pocket_lecture as pl
        from manim import BOLD, FadeIn, LEFT

        ax, ay, aw, ah = area
        w = {"x": ax - aw / 2 + 0.1, "top": ay + ah / 2 - 0.1, "bottom": ay - ah / 2 + 0.05, "width": aw - 0.2,
             "lines": []}
        w["y"] = w["top"]
        if title:
            head = pl.fit(pl.T(title.upper() if pl.TH["upper"] else title, 20, pl.P.SAND, weight=BOLD), w["width"])
            head.move_to([w["x"], w["y"], 0], aligned_edge=LEFT + [0, 1, 0])
            self._stage_add(head)
            anims.append(FadeIn(head))
            w["y"] = head.get_bottom()[1] - 0.2
        self.works[key] = w
        return w

    def work(self, key: str, lines=(), title: str | None = None, box: bool = False):
        """Lines of a worked solution, one group per beat, under the last; `box` rings the last line (the
        answer). The first call for a key places the working: in the problem's solution area, beside the
        figure on the stage (moved aside), or across the stage."""
        import pocket_lecture as pl
        from manim import (AnimationGroup, Create, FadeIn, FadeOut, Group, LaggedStart, SurroundingRectangle, Write,
                           LEFT, RIGHT)

        anims = []
        w = self.works.get(key)
        if w is None and self.works:
            # A second working on the same stage continues the first one's column, under it: moving the
            # stage aside again shrank the first working to a corner.
            w = next(iter(self.works.values()))
            if w["lines"]:
                w["y"] -= 0.2
            self.works[key] = w
        asides = [m for m in self.stage_extra if getattr(m, "is_aside", False)]
        if w is None and asides and self._problem is None and self.board_mode:
            # A card beside the drawing (a definition, an equation): the working takes its half of the board.
            area = asides[0].aside_box
            for m in asides:
                self.stage_extra.remove(m)
            anims.append(AnimationGroup(*[FadeOut(m) for m in asides]))
            w = self._new_column(key, area, title, anims)
        if w is None:
            if self._problem is not None:
                area = self._problem["work"]
            else:
                cx, cy, sw, sh = self.STAGE
                body = getattr(self, "stage_body", None)
                whole = Group(body, *self.stage_extra, *self.stage_pending) if body is not None else None
                if whole is not None and self.board_mode and whole.width > 2.4 * max(whole.height, 0.01) and \
                        getattr(body, "free_area", None) != "left":
                    # A wide, flat picture (a timeline, a chain across the board) halved beside the working had
                    # labels too small to read: it keeps the board's width along the top, the working goes below.
                    top_h = min(sh * 0.42, whole.height * sw / whole.width + 0.2)
                    top = (cx, cy + sh / 2 - top_h / 2, sw - 0.3, top_h)
                    moved = self._stage_aside(top)
                    if moved:
                        anims.append(moved)
                    area = (cx, cy - top_h / 2 - 0.1, min(sw, 9.0), sh - top_h - 0.3)
                elif body is not None and self.board_mode:
                    left = (cx - sw / 4 - 0.1, cy, sw / 2 - 0.3, sh)
                    moved = self._stage_aside(left)
                    if moved:
                        anims.append(moved)
                    area = (cx + sw / 4 + 0.1, cy, sw / 2 - 0.3, sh)
                else:
                    if getattr(self, "stage_body", None) is None:
                        anims.append(self._to_stage(Group()))       # an empty stage the working belongs to
                    # A column of reading width in the middle of the board, not lines strung along its top edge.
                    area = (cx, cy, min(sw, 9.0), sh - 0.4)
            w = self._new_column(key, area, title, anims)
        new = []
        for line in lines or []:
            mob = self._work_line(line, w["width"])
            mob.move_to([w["x"], w["y"], 0], aligned_edge=LEFT + [0, 1, 0])
            w["y"] = mob.get_bottom()[1] - 0.24
            new.append(mob)
        # Past the bottom: the working scrolls up, and the oldest lines leave over the top.
        overflow = w["bottom"] - w["y"] - 0.24 if new and w["y"] < w["bottom"] else 0
        if overflow > 0:
            old = w["lines"]
            shift = [0, overflow + 0.1, 0]
            going = [m for m in old if m.get_top()[1] + overflow + 0.1 > w["top"]]
            staying = [m for m in old if m not in going]
            for m in new:
                m.shift(shift)
            w["y"] += overflow + 0.1
            rings = w.setdefault("rings", {})
            # An answer's ring goes where its line goes: left behind, it boxed the lines scrolling past it.
            going += [rings.pop(id(m)) for m in list(going) if id(m) in rings]
            staying_rings = [rings[id(m)] for m in staying if id(m) in rings]
            scroll = [FadeOut(m) for m in going] + [m.animate.shift(shift) for m in [*staying, *staying_rings]]
            for m in going:
                if m in self.stage_extra:
                    self.stage_extra.remove(m)
            w["lines"] = staying
            anims.append(AnimationGroup(*scroll))
        for m in new:
            self._stage_add(m)
            w["lines"].append(m)
        if new:
            anims.append(LaggedStart(*[Write(m) if not hasattr(m, "text") else FadeIn(m, shift=RIGHT * 0.15)
                                       for m in new], lag_ratio=0.6))
        if box and w["lines"]:
            last = w["lines"][-1]
            ring = SurroundingRectangle(last, color=pl.P.GOLD, buff=0.12, corner_radius=0.08, stroke_width=4)
            w.setdefault("rings", {})[id(last)] = ring
            if self._problem is not None:
                # The answer is boxed: what comes next is new teaching, not more of this problem.
                self._problem["answered"] = True
            w["y"] -= 0.14          # the ring's own room, so the next line starts below it
            self._stage_add(ring)
            anims.append(Create(ring))
        if not anims:
            return None
        return LaggedStart(*anims, lag_ratio=0.8)

    # ---------------- problems ----------------
    def problem(self, key: str, text: str, title: str | None = None, given=(), find: str | None = None,
                figure: dict | None = None):
        """A long question on the board: its statement across the top, its figure on the left (a drawing made from
        its description), and room on the right for the solution (work)."""
        import pocket_lecture as pl
        from manim import BOLD, Group, Line, VGroup, LEFT, RIGHT

        cx, cy, w, h = self.STAGE
        top = cy + h / 2
        from manim import RoundedRectangle

        tag = pl.T((title or "Problem").upper(), 20, pl.P.BG, weight=BOLD)
        chip = RoundedRectangle(corner_radius=0.08, width=tag.width + 0.3, height=tag.height + 0.18,
                                   fill_color=pl.P.SAND, fill_opacity=1, stroke_width=0)
        tag.move_to(chip)
        head = VGroup(chip, tag).move_to([cx - w / 2 + 0.1, top - 0.2, 0], aligned_edge=LEFT + [0, 1, 0])
        chars = int(80 * (w / 13.5))
        body = pl.fit(pl.T(pl.wrap(_label_text(text) if re.search(r"[_^\\]", str(text)) else str(text), chars), 25,
                           pl.P.CREAM, line_spacing=0.9), w - 0.3)
        body.next_to(head, RIGHT, buff=0.3, aligned_edge=[0, 1, 0])
        if body.get_right()[0] > cx + w / 2:
            body.next_to(head, [0, -1, 0], buff=0.15, aligned_edge=LEFT)
        statement = VGroup(head, body)
        rule_y = statement.get_bottom()[1] - 0.18
        track = Line([cx - w / 2 + 0.1, rule_y, 0], [cx + w / 2 - 0.1, rule_y, 0], color=pl.P.MUTED, stroke_width=2,
                     stroke_opacity=0.5)
        below_top = rule_y - 0.1
        below_h = below_top - (cy - h / 2)
        fig_box = (cx - w / 4 - 0.1, below_top - below_h / 2, w / 2 - 0.3, below_h)
        work_box = (cx + w / 4 + 0.1, below_top - below_h / 2, w / 2 - 0.3, below_h)
        parts = [statement, track]
        going = self._stage_leaving()
        drawing = None
        if figure:
            if figure.get("op") == "draw" and figure.get("file"):
                # The figure made by the diagram model from its description (compile_lecture), shown whole.
                fcx, fcy, fw, fh = fig_box
                drawing = pl.cutout_mob(figure["file"], fw - 0.2, fh - 0.2).move_to([fcx, fcy, 0])
        else:
            work_box = (cx, below_top - below_h / 2, w, below_h)
        lines = []
        if given:
            lines.append("Given: " + ",  ".join(_label_text(g) for g in given))
        if find:
            lines.append("Find: " + _label_text(find))
        wx, wy, ww, wh = work_box
        y = wy + wh / 2 - 0.1
        for line in lines:
            mob = pl.fit(pl.T(pl.wrap(line, 44), 22, pl.P.MUTED, line_spacing=0.9), ww - 0.2)
            mob.move_to([wx - ww / 2 + 0.1, y, 0], aligned_edge=LEFT + [0, 1, 0])
            y = mob.get_bottom()[1] - 0.12
            parts.append(mob)
        solution_h = (y - 0.12) - (wy - wh / 2)
        self._problem = {"key": key, "work": (wx, (y - 0.12) - solution_h / 2, ww, solution_h),
                         "fig_box": fig_box if drawing is not None else None, "figure": drawing}
        group = Group(VGroup(*parts))
        new = Group(self._stage_card(), group)
        new.set_z_index(pl.Z_MARK + 10)
        self.stage_items, self.stage_body = new, group
        self.stage_pending, self._next_pending = self._next_pending, []
        self._stage_keys, self._next_keys = set(self._next_keys), set()
        self._question = {"track": track, "answer": None}
        from manim import AnimationGroup, FadeIn

        show = FadeIn(new)
        if drawing is not None:
            self._stage_add(drawing)
            show = AnimationGroup(show, FadeIn(drawing))
        return AnimationGroup(AnimationGroup(*going, run_time=0.5), show, lag_ratio=1.0) if going else show


# The pictures these build write their words in the art style's font (artstyle.drawing).
import artstyle as _artstyle  # noqa: E402

_artstyle.drawn_by(BoardMixin, ("free", "board_bars"))
