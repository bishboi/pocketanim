"""The runtime: a score played on one clock, the narration under it.

    python render.py score.txt voice_dir out.mp4 [--quality h|m|l] [--from S --to S]

Every action of the score is a tween with its own start and end (the words it is pinned to), and one clock drives
them all, frame by frame: any number of actions overlap, a move and a float and a pulse on the same thing add up,
and the camera travels over the canvas while things happen. Nothing waits for anything else to finish, and nothing
is a slide: what is up stays up until an action takes it off.

VERBS (TIME VERB TARGET [ARGS]):
    in T [fade|pop|rise|drop|slide-left|slide-right|draw|write|grow|unfold] [stagger S]
    out T [fade|shrink|drop] [stagger S]
    move T to X,Y | to ENT | by DX,DY [arc A]       (X,Y in T's shot frame)
    along T PATH                                     (T travels a path or arrow entity)
    morph A B [stagger S]                            (A becomes B: B must not be up yet)
    color T COLOR | dim T [OPACITY] | lift T (back to full)
    scale T K | spin T DEG | pulse T | shake T
    count NUM V | grow BAR V
    ring T [COLOR] | mark T [COLOR]                  (a ring drawn round it, a line drawn under it; they leave with it)
    flow PATH [n N] [COLOR]                          (dots travel the path over the action's time)
    float T [AMP]                                    (bobs gently over the action's time, or to the end)
    cam SHOT | cam ENT [zoom Z] | cam SHOT X,Y [zoom Z] | cam wide
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from manim import (DOWN, LEFT, RIGHT, UP, Circle, Create, Dot, Ellipse, Group, ImageMobject, Line, Mobject,
                   MovingCameraScene, ReplacementTransform, VGroup, VMobject, Write, config, rate_functions,
                   tempconfig)
from manim.utils.color import ManimColor, interpolate_color

import look
import score as S

LEAD = 0.18             # an action lands on its word: it starts this much before it
DEFAULT_RUN = {"in": 0.7, "out": 0.5, "move": 0.9, "along": 1.6, "morph": 0.9, "color": 0.6, "dim": 0.5, "lift": 0.5,
               "scale": 0.7, "spin": 0.8, "pulse": 0.55, "shake": 0.5, "count": 1.2, "grow": 1.0, "ring": 0.6,
               "mark": 0.5, "flow": 2.0, "cam": 1.4}
TAIL = 3.2              # seconds held after the last word


# ---------------------------------------------------------------- helpers ----------------------------------------------

def leaves(m):
    """The drawn pieces of a mobject: its shapes with points, and its pictures."""
    return [x for x in m.get_family() if (isinstance(x, VMobject) and len(x.points)) or isinstance(x, ImageMobject)] or [m]


def has_picture(m) -> bool:
    return any(isinstance(x, ImageMobject) for x in m.get_family())


class Alpha:
    """A mobject's opacity as a share of its own (recorded once): fade in and out, dim and lift without losing what
    its parts' own opacities were."""

    def __init__(self, m):
        self.base = []
        for x in leaves(m):
            try:
                self.base.append((x, float(x.get_fill_opacity()), float(x.get_stroke_opacity())))
            except Exception:  # noqa: BLE001
                self.base.append((x, 1.0, 1.0))
        self.now = 1.0

    def set(self, a: float) -> None:
        self.now = a
        for x, f, s in self.base:
            if isinstance(x, ImageMobject):
                x.set_opacity(max(0.0, min(1.0, a)))      # from the picture's own alpha
                continue
            x.set_fill(opacity=f * a, family=False)
            x.set_stroke(opacity=s * a, family=False)


class Tween:
    def __init__(self, t0: float, t1: float, rate=rate_functions.smooth):
        self.t0, self.t1, self.rate = t0, max(t1, t0 + 1e-3), rate
        self.started = self.done = False

    def start(self) -> None: ...
    def step(self, a: float) -> None: ...
    def stop(self) -> None: ...


class Call(Tween):
    def __init__(self, t0, t1, start=None, step=None, stop=None, rate=rate_functions.smooth):
        super().__init__(t0, t1, rate)
        self._start, self._step, self._stop = start, step, stop

    def start(self):
        if self._start:
            self._start()

    def step(self, a):
        if self._step:
            self._step(a)

    def stop(self):
        if self._stop:
            self._stop()


# ---------------------------------------------------------------- the scene ----------------------------------------------

class ScoreScene(MovingCameraScene):
    SCORE: S.Score
    WORDS: dict
    WAV: str | None = None
    FRAMES: tuple[int, int] | None = None     # a chunk of the video (frames from, to), else all of it
    FPS: int = 30
    SOUND: bool = True

    def construct(self):
        sc, words = self.SCORE, self.WORDS
        look.use(sc.look)
        self.camera.background_color = ManimColor(look.L["bg"])
        self.E: dict[str, Mobject] = {}          # entity name -> its mobject
        self.alpha: dict[int, Alpha] = {}
        self.marks: dict[str, list] = {}         # entity name -> rings and lines drawn on it
        self.up: set[int] = set()                # what is on the screen
        self.tweens: list[Tween] = []
        self.clock = 0.0
        self._paper()
        self._build()
        self._spread()
        for act in sc.acts:
            n = len(self.tweens)
            try:
                self._schedule(act)
            except Exception as e:  # noqa: BLE001 -- one action that cannot be played is left out, said
                print(f"score line {act.line}: {act.verb} left out: {e}", file=sys.stderr)
                del self.tweens[n:]
            for tw in self.tweens[n:]:
                tw.line, tw.verb = act.line, act.verb
        self._introduce_the_rest()
        self.tweens.sort(key=lambda t: t.t0)
        first = next((a for a in sc.acts if a.verb == "cam"), None)
        f = self.camera.frame
        shot = next(iter(sc.shots.values()))
        f.move_to([shot.x, shot.y, 0]).set_width(S.SCREEN_W / shot.zoom)
        if first:
            self._cam_target(first)            # opens where the first camera move goes
        f0, f1 = self.FRAMES or (0, frames_of(sc.end + TAIL, self.FPS))
        if self.WAV and self.SOUND and f0 == 0:
            self.add_sound(self.WAV)
        driver = Mobject()
        driver.add_updater(lambda m, dt: self._tick(dt))
        # Right above the paper in the drawing order: manim draws what comes before its first updated mobject once,
        # as a still image, at the start of the wait. Only the paper is still; every entity is drawn each frame (a
        # chunk starting mid-video froze a ghost of what was up then under the live frame).
        driver.set_z_index(-99)
        self.add(driver)
        self.clock = 0.0
        self._tick(0.0)
        for _ in range(f0):
            # A chunk plays the timeline up to its start, undrawn, frame by frame as the whole video would: what
            # it shows from there is the same frame for frame, so the chunks join without a seam.
            self._tick(1.0 / self.FPS)
        self.wait((f1 - f0 - 0.5) / self.FPS)   # exactly f1 - f0 frames

    # ------------------------------------------------------------ the canvas -------------------------------------------
    def _paper(self) -> None:
        """A paper texture under the whole canvas: soft blotches of light and shade, very faint."""
        xs = [s.x for s in self.SCORE.shots.values()] or [0]
        ys = [s.y for s in self.SCORE.shots.values()] or [0]
        w = (max(xs) - min(xs)) + S.SCREEN_W * 3
        h = (max(ys) - min(ys)) + S.SCREEN_H * 3
        rng = np.random.default_rng(3)
        small = rng.normal(0, 1, (36, 64))
        from PIL import Image, ImageFilter
        img = Image.fromarray(((small - small.min()) / (np.ptp(small) + 1e-9) * 255).astype("uint8"))
        img = img.resize((1280, 720), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))
        a = np.asarray(img).astype(float) / 255.0
        bg = np.array([int(look.L["bg"][i:i + 2], 16) for i in (1, 3, 5)], dtype=float)
        rgb = np.clip(bg[None, None, :] * (0.965 + 0.06 * a[..., None]), 0, 255).astype("uint8")
        tex = ImageMobject(rgb)
        tex.stretch_to_fit_width(w).stretch_to_fit_height(h)
        tex.move_to([(max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, 0])
        tex.set_z_index(-100)
        self.add(tex)
        self.paper = tex

    def _build(self) -> None:
        """Every entity drawn: paths after what they name, then arrows and what is spread `on` a path. One that cannot be drawn (a word
        where a point should be) is left out, said in the notes, with the actions on it; the rest plays."""
        sc = self.SCORE
        ents = list(sc.ents.values())
        paths = [e for e in ents if e.kind == "path"]
        last = [e for e in ents if e.kind == "arrow" or (e.mods.get("on") and e.kind != "path")]   # on a path
        for e in [e for e in ents if e not in paths and e not in last] + paths + last:
            try:
                self._make(e)
            except Exception as ex:  # noqa: BLE001
                sc.notes.append(f"line {e.line}: {e.name} ({e.kind}) left out: {ex}")
                self.E.pop(e.name, None)
        for name in [n for n in sc.ents if n not in self.E]:
            del sc.ents[name]

    # Kinds a layout mend may move: what a small model places by number. Lands, seas, paths, arrows and rings are
    # placed against other things on purpose, and an entity placed on another (`at ENT`, `on PATH`) is meant there.
    SPREAD = {"icon", "text", "rect", "circle", "blob", "num", "bar", "dots", "pic", "photo", "flag", "card", "tag",
              "label"}
    HOLDERS = {"rect", "circle", "blob", "card", "photo"}

    def _holder(self, e: S.Ent) -> bool:
        """A shape that things are put on: a box, a disc, a region, an icon on its badge."""
        return e.kind in self.HOLDERS or (e.kind == "icon" and bool(e.mods.get("badge")))

    def _spread(self) -> None:
        """Things of one shot up at the same time that partly overlap are pushed apart (the later one moves, along
        the shorter way out, kept on its shot's screen). One inside the other (a label on a box, an icon on its
        badge) is left: that is meant."""
        sc = self.SCORE
        times = self._up_times()
        for shot in sc.shots.values():
            ents = [e for e in sc.ents.values() if e.shot == shot.name and e.kind in self.SPREAD
                    and not e.mods.get("on") and not (isinstance(e.mods.get("at"), str) and e.mods["at"] in self.E)]
            def holds(big, small) -> bool:
                # Only a shape holds things (a box, a disc, a region): a long title's box is not a card.
                return big is not small and self._holder(big) and self._inside(self.E[small.name], self.E[big.name])
            # What sits on another (a badge on its box, a label on its card) moves with it, and is not moved itself.
            riders = {e.name: [x for x in ents if holds(e, x)] for e in ents}
            for e in ents:                      # nothing hangs off its shot's screen (a long title, a far `at`)
                before = self.E[e.name].get_center().copy()
                self._on_screen(self.E[e.name], shot)
                if not np.allclose(before, self.E[e.name].get_center()):
                    for x in riders[e.name]:
                        self.E[x.name].shift(self.E[e.name].get_center() - before)
            ridden = {x.name for xs in riders.values() for x in xs}
            for _ in range(3):
                moved = False
                for j, b in enumerate(ents):
                    if b.name in ridden:
                        continue
                    for a in ents[:j]:
                        if a.name in ridden or a in riders[b.name] or b in riders[a.name]:
                            continue
                        (a0, a1), (b0, b1) = times.get(a.name, (0, 1e9)), times.get(b.name, (0, 1e9))
                        if a1 <= b0 or b1 <= a0:
                            continue
                        push = self._apart(self.E[a.name], self.E[b.name], self._holder(a), self._holder(b))
                        if push is None:
                            continue
                        group = [self.E[b.name]] + [self.E[x.name] for x in riders[b.name]]
                        before = self.E[b.name].get_center().copy()
                        self.E[b.name].shift(push)
                        self._on_screen(self.E[b.name], shot)
                        for m in group[1:]:
                            m.shift(self.E[b.name].get_center() - before)
                        sc.notes.append(f"{b.name} moved off {a.name} (they overlapped)")
                        moved = True
                if not moved:
                    break

    def _up_times(self) -> dict[str, tuple[float, float]]:
        """When each entity comes on and goes (by the actions that bring it and take it away)."""
        t_in: dict[str, float] = {}
        t_out: dict[str, float] = {}
        base = lambda ref: [re.sub(r"\[.*", "", x) for x in ref.split(",")]  # noqa: E731
        for a in self.SCORE.acts:
            if a.verb == "in":
                for n in base(a.target):
                    t_in[n] = min(t_in.get(n, 1e9), a.t0)
            elif a.verb == "out":
                for n in base(a.target):
                    t_out[n] = min(t_out.get(n, 1e9), a.t0)
            elif a.verb == "morph" and a.args:
                for n in base(a.target):
                    t_out[n] = min(t_out.get(n, 1e9), a.t0 + 0.5)
                for n in base(a.args[0]):
                    t_in[n] = min(t_in.get(n, 1e9), a.t0 + 0.5)
        return {n: (t_in.get(n, 0.0), t_out.get(n, 1e9)) for n in self.SCORE.ents}

    @staticmethod
    def _apart(a, b, a_holds: bool = True, b_holds: bool = True, gap: float = 0.3):
        """How far b must move to clear a, or None (apart, or one inside a shape that holds it)."""
        al, ar, ab, at = a.get_left()[0], a.get_right()[0], a.get_bottom()[1], a.get_top()[1]
        bl, br, bb, bt = b.get_left()[0], b.get_right()[0], b.get_bottom()[1], b.get_top()[1]
        ox, oy = min(ar, br) - max(al, bl), min(at, bt) - max(ab, bb)
        if ox <= 0 or oy <= 0:
            return None
        if (b_holds and ScoreScene._inside(a, b)) or (a_holds and ScoreScene._inside(b, a)):
            return None
        if ox * oy < 0.04 * min((ar - al) * (at - ab), (br - bl) * (bt - bb)):
            return None                       # a corner touching: let be
        ca, cb = a.get_center(), b.get_center()
        if ox < oy:
            return np.array([(ox + gap) * (1 if cb[0] >= ca[0] else -1), 0.0, 0.0])
        return np.array([0.0, (oy + gap) * (1 if cb[1] >= ca[1] else -1), 0.0])

    @staticmethod
    def _inside(small, big, e: float = 0.35) -> bool:
        return (small.get_left()[0] >= big.get_left()[0] - e and small.get_right()[0] <= big.get_right()[0] + e
                and small.get_bottom()[1] >= big.get_bottom()[1] - e and small.get_top()[1] <= big.get_top()[1] + e)

    def _on_screen(self, m, shot) -> None:
        if m.width > S.SCREEN_W / shot.zoom - 0.8:
            m.scale_to_fit_width(S.SCREEN_W / shot.zoom - 0.8)
        # (a margin that also allows for the camera's slow push in over a long shot)
        o, hw, hh = np.array([shot.x, shot.y, 0.0]), S.SCREEN_W / shot.zoom / 2 - 0.55, S.SCREEN_H / shot.zoom / 2 - 0.45
        dx = max(0.0, (o[0] - hw) - m.get_left()[0]) - max(0.0, m.get_right()[0] - (o[0] + hw))
        dy = max(0.0, (o[1] - hh) - m.get_bottom()[1]) - max(0.0, m.get_top()[1] - (o[1] + hh))
        m.shift([dx, dy, 0.0])

    def _origin(self, shot: str) -> np.ndarray:
        s = self.SCORE.shots.get(shot)
        return np.array([s.x, s.y, 0.0]) if s else np.zeros(3)

    def _locate(self, ref: str, shot: str) -> np.ndarray:
        if ref in self.E:
            return self.E[ref].get_center()
        if "." in ref and ref.split(".", 1)[0] in self.E:
            # A place on a land (`japan.tokyo`).
            ent, place = ref.split(".", 1)
            places = getattr(self.E[ent], "places", {})
            if place not in places:
                raise ValueError(f"{ent} has no place {place!r} ({', '.join(places)})")
            return places[place].get_center()
        x, y = (float(v) for v in ref.split(","))
        return self._origin(shot) + np.array([x, y, 0.0])

    def _make(self, e: S.Ent) -> None:
        def one():
            return look.build(e.kind, e.args, e.mods, locate=lambda r: self._locate(r, e.shot))
        m = look.copies(one, int(e.mods["x"]), e.mods) if int(e.mods.get("x", 1)) > 1 else one()
        if e.mods.get("rot"):
            m.rotate(math.radians(float(e.mods["rot"])))
        if e.kind not in ("land", "waves", "path", "arrow", "islands") and (m.width > 12 or m.height > 7):
            m.scale(min(12 / m.width, 7 / m.height))      # nothing bigger than the screen
        if e.mods.get("on") and len(m.submobjects) > 1:
            # Its copies (or dots) spread along a path, evenly.
            track = self._track(self.E[e.mods["on"]])
            n = len(m.submobjects)
            for i, part in enumerate(m.submobjects):
                part.move_to(track.point_from_proportion((i + 0.5) / n))
        elif e.kind not in ("arrow", "path"):
            at = e.mods.get("at", (0.0, 0.0))
            where = self._locate(at, e.shot) if isinstance(at, str) else self._origin(e.shot) + np.array([at[0], at[1], 0.0])
            m.move_to(where)
        if e.mods.get("nudge"):
            m.shift(np.array([*e.mods["nudge"], 0.0]))
        layer = int(e.mods.get("layer", -1 if e.kind in ("blob", "islands") else 0))   # a region sits under what is on it
        m.set_z_index(layer * 10 + (5 if e.kind in ("text", "num") else 0))
        if e.mods.get("opacity") is not None:
            Alpha(m).set(float(e.mods["opacity"]))
        self.E[e.name] = m

    # ------------------------------------------------------------ targets ----------------------------------------------
    def _targets(self, ref: str) -> list:
        out = []
        for one in ref.split(","):
            m = re.match(r"^([\w\-]+)(?:\[(\-?\d*)(?::(\-?\d*))?\])?$", one.strip())
            if not m or m.group(1) not in self.E:
                raise ValueError(f"no entity {one!r}")
            mob = self.E[m.group(1)]
            if m.group(2) is None and m.group(3) is None:
                out.append((m.group(1), mob))
                continue
            parts = list(mob.submobjects)
            a = int(m.group(2)) if m.group(2) else 0
            if ":" in one:
                b = int(m.group(3)) if m.group(3) else len(parts)
                out += [(m.group(1), p) for p in parts[a:b]]
            else:
                out.append((m.group(1), parts[a]))
        return out

    def _alpha(self, m) -> Alpha:
        if id(m) not in self.alpha:
            self.alpha[id(m)] = Alpha(m)
        return self.alpha[id(m)]

    def _show(self, name: str, m) -> None:
        """Put an entity on the screen (all its parts hidden but this one: each part comes on by its own tween)."""
        whole = self.E[name]
        if id(whole) not in self.up:
            self.up.add(id(whole))
            if whole is not m:
                for p in whole.submobjects:
                    self._alpha(p).set(0.0)
            else:
                self._alpha(whole).set(0.0)
            self.add(whole)

    # ------------------------------------------------------------ the clock --------------------------------------------
    DRIFT = 0.005           # the camera's slow push in while no camera move runs (a share of the view a second)

    def _tick(self, dt: float) -> None:
        # The clock is the frame's own time (frames / fps), not a sum of steps: every engine that plays the score
        # (the render, its chunks, the timeline for the player) starts each action on the same frame.
        if dt > 0:
            self._frame_no = getattr(self, "_frame_no", 0) + 1
            self.clock = self._frame_no / self.FPS
        else:
            self.clock += dt
        t = self.clock
        if dt and not any(isinstance(tw, Call) and getattr(tw, "camera", False) and tw.t0 <= t <= tw.t1 for tw in self.tweens):
            # Never quite still: the view creeps in, as a camera on a slow dolly.
            self.camera.frame.scale(1 - self.DRIFT * dt)
        for tw in self.tweens:
            if tw.done or t < tw.t0:
                continue
            try:
                if not tw.started:
                    tw.started = True
                    tw.start()
                a = min(1.0, (t - tw.t0) / (tw.t1 - tw.t0))
                tw.step(tw.rate(a))
                if a >= 1.0:
                    tw.done = True
                    tw.stop()
            except Exception as e:  # noqa: BLE001 -- an action that fails as it plays is dropped, said; the rest plays
                tw.done = True
                print(f"score line {getattr(tw, 'line', '?')}: {getattr(tw, 'verb', 'an action')} stopped as it played: "
                      f"{type(e).__name__}: {e}", file=sys.stderr)
        # What is drawn this frame is what is up now: manim keeps the list it took when the wait began, and a part
        # replaced since (a number counting, a bar growing) would be drawn twice, the stale one under the live one.
        if getattr(self, "moving_mobjects", None) is not None:
            self.moving_mobjects = [m for m in self.mobjects if m is not self.paper]

    # ------------------------------------------------------------ actions ----------------------------------------------
    def _span(self, act: S.Act, lead: bool = True) -> tuple[float, float]:
        t0 = act.t0 - (LEAD if lead else 0.0)
        t1 = act.t1 if act.t1 is not None else t0 + DEFAULT_RUN.get(act.verb, 0.7)
        return max(0.0, t0), t1

    def _opt(self, act: S.Act, key: str, default=None, kind=float):
        if key in act.args:
            i = act.args.index(key)
            if i + 1 < len(act.args):
                return kind(act.args[i + 1])
        return default

    def _staggered(self, items: list, t0: float, t1: float, stagger: float | None):
        """Each of several things given its own slice of the time, `stagger` apart (or spread over it)."""
        n = len(items)
        if n <= 1:
            return [(items[0], t0, t1)] if items else []
        if stagger is None:
            stagger = min(0.12, (t1 - t0) * 0.5 / (n - 1))
        run = max(0.3, (t1 - t0) - stagger * (n - 1))
        return [(it, t0 + i * stagger, t0 + i * stagger + run) for i, it in enumerate(items)]

    def _schedule(self, act: S.Act) -> None:
        v = act.verb
        if v == "cam":
            return self._cam(act)
        t0, t1 = self._span(act, lead=v not in ("float", "flow"))
        how = act.args[0] if act.args and not re.match(r"^[\d\-.,]+$", act.args[0]) and act.args[0] not in ("to", "by", "stagger", "n", "arc") else None
        stagger = self._opt(act, "stagger")
        if v == "in":
            items = self._targets(act.target)
            if len(items) == 1 and stagger is not None and len(items[0][1].submobjects) > 1:
                items = [(items[0][0], p) for p in items[0][1].submobjects]
            for (name, m), a0, a1 in self._staggered(items, t0, t1, stagger):
                self._in(name, m, a0, a1, how or "fade")
        elif v == "out":
            items = self._targets(act.target)
            if len(items) == 1 and stagger is not None and len(items[0][1].submobjects) > 1:
                items = [(items[0][0], p) for p in items[0][1].submobjects]
            for (name, m), a0, a1 in self._staggered(items, t0, t1, stagger):
                self._out(name, m, a0, a1, how or "fade")
        elif v == "move":
            for (name, m), a0, a1 in self._staggered(self._targets(act.target), t0, t1, stagger):
                self._move(name, m, act, a0, a1)
        elif v == "along":
            (name, m), = self._targets(act.target)[:1]
            self._along(m, self._track(self.E[act.args[0]]), t0, t1)
        elif v == "morph":
            a = self._targets(act.target)
            b = self._targets(act.args[0])
            if len(a) == 1 and len(b) == 1 and stagger is not None:
                pa, pb = a[0][1].submobjects, b[0][1].submobjects
                if len(pa) == len(pb) > 1:
                    a = [(a[0][0], p) for p in pa]
                    b = [(b[0][0], p) for p in pb]
            for ((na, ma), (nb, mb)), a0, a1 in self._staggered(list(zip(a, b)), t0, t1, stagger):
                self._morph(na, ma, nb, mb, a0, a1)
        elif v in ("color", "dim", "lift"):
            for (name, m), a0, a1 in self._staggered(self._targets(act.target), t0, t1, stagger):
                if v == "color":
                    self._color(m, look.col(act.args[0] if act.args else "coral"), a0, a1)
                else:
                    self._fade_to(m, float(act.args[0]) if v == "dim" and act.args else (0.3 if v == "dim" else 1.0), a0, a1)
        elif v in ("scale", "spin", "pulse", "shake"):
            for (name, m), a0, a1 in self._staggered(self._targets(act.target), t0, t1, stagger):
                if v == "scale":
                    self._scale(m, float(act.args[0]) if act.args else 1.2, a0, a1)
                elif v == "spin":
                    self._spin(m, float(act.args[0]) if act.args else 360, a0, a1)
                elif v == "pulse":
                    self._pulse(m, a0, a1)
                else:
                    self._shake(m, a0, a1)
        elif v in ("count", "grow"):
            if not act.args:
                raise ValueError(f"{v} needs the value to reach (`{v} NAME 42`)")
            to = float(re.sub(r"[^\d.\-]", "", act.args[0]) or 0)
            for m in self._valued(act.target, v):
                (self._count if v == "count" else self._grow)(m, to, t0, t1)
        elif v in ("ring", "mark"):
            for (name, m) in self._targets(act.target):
                self._mark(name, m, v, look.col(act.args[0] if act.args else "coral"), t0, t1)
        elif v == "flow":
            self._flow(self._track(self.E[act.target]), int(self._opt(act, "n", 6, int)),
                       look.col(next((x for x in act.args if x in look.L), "coral")), t0, t1)
        elif v == "float":
            amp = float(act.args[0]) if act.args else 0.08
            end = t1 if act.t1 is not None else self.SCORE.end + TAIL
            for (name, m) in self._targets(act.target):
                self._float(m, amp, t0, end)
        else:
            raise ValueError(f"no verb {v!r}")

    @staticmethod
    def _track(m):
        """The curve a path or an arrow is drawn on (a dashed one keeps it aside), for what travels along it."""
        t = getattr(m, "track", None)
        if t is not None:
            return t
        return m if len(m.points) else next((x for x in m.get_family() if len(x.points)), m)

    # ------------------------------------------------------------ verbs ------------------------------------------------
    def _in(self, name, m, t0, t1, how) -> None:
        al = self._alpha(m)
        state = {}

        def start():
            self._show(name, m)
            c = m.get_center()
            if how in ("draw", "write") and not has_picture(m):
                al.set(1.0)
                anim = (Write(m) if how == "write" else Create(m, lag_ratio=0.05))
                anim.begin()
                state["anim"] = anim
                return
            al.set(0.0)
            state["k"], state["d"] = 1.0, np.zeros(3)
            if how in ("pop", "grow"):
                state["k0"] = 0.2 if how == "pop" else 0.01
                m.scale(state["k0"], about_point=c)
                state["k"] = state["k0"]
            off = {"rise": DOWN * 0.5, "drop": UP * 0.7, "slide-left": RIGHT * 2.2, "slide-right": LEFT * 2.2}.get(how)
            if off is not None:
                m.shift(off)
                state["d"] = off.copy()
            if how == "unfold":
                m.stretch(0.02, 1)
                state["s"] = 0.02

        def step(a):
            if "anim" in state:
                state["anim"].interpolate(a)
                return
            al.set(min(1.0, a * 1.6) if how in ("pop", "grow") else a)
            if "k0" in state:
                k = state["k0"] + (1 - state["k0"]) * a
                m.scale(max(k, 1e-3) / state["k"])
                state["k"] = max(k, 1e-3)
            if state["d"].any():
                target = state["d"] * (1 - a)
                m.shift(target - state["d"])
                state["d"] = target
            if "s" in state:
                s = 0.02 + 0.98 * a
                m.stretch(s / state["s"], 1)
                state["s"] = s

        def stop():
            if "anim" in state:
                state["anim"].interpolate(1)
                state["anim"].finish()
        rate = {"pop": rate_functions.ease_out_back, "grow": rate_functions.ease_out_back, "drop": rate_functions.ease_out_back,
                "slide-left": rate_functions.ease_out_cubic, "slide-right": rate_functions.ease_out_cubic,
                "rise": rate_functions.ease_out_cubic, "draw": rate_functions.ease_in_out_sine,
                "write": rate_functions.linear}.get(how, rate_functions.smooth)
        self.tweens.append(Call(t0, t1, start, step, stop, rate))

    def _out(self, name, m, t0, t1, how) -> None:
        al = self._alpha(m)
        state = {}

        def start():
            state["a0"] = al.now
            state["k"], state["d"] = 1.0, np.zeros(3)

        def step(a):
            al.set(state["a0"] * (1 - a))
            if how == "shrink":
                k = max(1 - 0.8 * a, 0.05)
                m.scale(k / state["k"])
                state["k"] = k
            if how == "drop":
                d = DOWN * 0.8 * a
                m.shift(d - state["d"])
                state["d"] = d

        def stop():
            for mk in self.marks.get(name, []) if m is self.E.get(name) else []:
                self.remove(mk)
            if m is self.E.get(name):
                self.remove(m)
                self.up.discard(id(m))
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.ease_in_cubic if how == "drop" else rate_functions.smooth))
        for mk in self.marks.get(name, []):
            self._fade_to(mk, 0.0, t0, t1)

    def _dest(self, name: str, m, act: S.Act) -> np.ndarray:
        shot = self.SCORE.ents[name].shot if name in self.SCORE.ents else ""
        if "to" in act.args:
            ref = act.args[act.args.index("to") + 1]
            return self._locate(ref, shot)
        if "by" in act.args:
            dx, dy = (float(v) for v in act.args[act.args.index("by") + 1].split(","))
            return m.get_center() + np.array([dx, dy, 0.0])
        raise ValueError("move needs `to X,Y`, `to ENT` or `by DX,DY`")

    def _move(self, name, m, act, t0, t1) -> None:
        arc = self._opt(act, "arc", 0.0)
        state = {}

        def start():
            state["p0"] = m.get_center().copy()
            state["p1"] = self._dest(name, m, act)
            state["at"] = np.zeros(3)

        def step(a):
            p0, p1 = state["p0"], state["p1"]
            d = p1 - p0
            n = np.array([-d[1], d[0], 0.0])
            n = n / (np.linalg.norm(n) + 1e-9)
            off = d * a + n * arc * math.sin(math.pi * a) * np.linalg.norm(d) * 0.35
            m.shift(off - state["at"])
            state["at"] = off
        self.tweens.append(Call(t0, t1, start, step, None, rate_functions.ease_in_out_cubic))

    def _along(self, m, path, t0, t1) -> None:
        state = {}

        def start():
            state["at"] = m.get_center().copy()

        def step(a):
            p = path.point_from_proportion(min(max(a, 0), 1))
            m.shift(p - state["at"])
            state["at"] = p
        self.tweens.append(Call(t0, t1, start, step, None, rate_functions.ease_in_out_sine))

    def _morph(self, na, ma, nb, mb, t0, t1) -> None:
        state = {}

        def start():
            self._show(na, ma)
            if id(self.E[nb]) not in self.up:
                self.up.add(id(self.E[nb]))
                if self.E[nb] is not mb:
                    for p in self.E[nb].submobjects:
                        self._alpha(p).set(0.0)
            self._alpha(mb).set(1.0)
            anim = ReplacementTransform(ma, mb)
            anim._setup_scene(self)
            anim.begin()
            state["anim"] = anim

        def step(a):
            state["anim"].interpolate(a)

        def stop():
            anim = state["anim"]
            anim.interpolate(1)
            anim.finish()
            anim.clean_up_from_scene(self)
            whole = self.E[nb]
            if whole is not mb and whole not in self.mobjects:
                self.add(whole)
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.ease_in_out_cubic))

    def _color(self, m, c, t0, t1) -> None:
        state = {}

        def start():
            state["from"] = [(x, x.get_fill_color(), x.get_stroke_color(), x.get_fill_opacity() > 0.01,
                              x.get_stroke_width() > 0) for x in leaves(m) if isinstance(x, VMobject)]

        def step(a):
            for x, f, s, filled, stroked in state["from"]:
                if filled:
                    x.set_fill(interpolate_color(f, ManimColor(c), a), family=False)
                if stroked:
                    x.set_stroke(interpolate_color(s, ManimColor(c), a), family=False)
        self.tweens.append(Call(t0, t1, start, step))

    def _fade_to(self, m, to: float, t0, t1) -> None:
        al = self._alpha(m)
        state = {}

        def start():
            state["a0"] = al.now

        self.tweens.append(Call(t0, t1, start, lambda a: al.set(state["a0"] + (to - state["a0"]) * a)))

    def _scale(self, m, k, t0, t1) -> None:
        state = {"k": 1.0}

        def step(a):
            kk = k ** a
            m.scale(kk / state["k"])
            state["k"] = kk
        self.tweens.append(Call(t0, t1, None, step, None, rate_functions.ease_out_back if k > 1 else rate_functions.smooth))

    def _spin(self, m, deg, t0, t1) -> None:
        state = {"r": 0.0}

        def step(a):
            r = math.radians(deg) * a
            m.rotate(r - state["r"])
            state["r"] = r
        self.tweens.append(Call(t0, t1, None, step))

    def _pulse(self, m, t0, t1) -> None:
        state = {"k": 1.0}

        def step(a):
            k = 1 + 0.16 * math.sin(math.pi * a)
            m.scale(k / state["k"])
            state["k"] = k
        self.tweens.append(Call(t0, t1, None, step, None, rate_functions.linear))

    def _shake(self, m, t0, t1) -> None:
        state = {"x": 0.0}

        def step(a):
            x = 0.12 * math.sin(a * 6 * math.pi) * (1 - a)
            m.shift(RIGHT * (x - state["x"]))
            state["x"] = x
        self.tweens.append(Call(t0, t1, None, step, None, rate_functions.linear))

    def _valued(self, ref: str, verb: str) -> list:
        """The numbers or bars an action changes: the target itself, or each one inside it (`num x3`)."""
        out = []
        for name, m in self._targets(ref):
            # (not hasattr: manim answers any `set_...` name on any mobject)
            if isinstance(m, (look.Num, look.Bar)):
                out.append(m)
            else:
                out += [p for p in m.get_family() if isinstance(p, (look.Num, look.Bar))]
        if not out:
            kind = self.SCORE.ents.get(re.sub(r"\[.*", "", ref.split(",")[0]))
            raise ValueError(f"{verb} needs a num or a bar ({ref} is {'a ' + kind.kind if kind else 'not one'})")
        return out

    def _count(self, m, to, t0, t1) -> None:
        state = {}

        def start():
            state["v0"] = float(m.value)

        self.tweens.append(Call(t0, t1, start, lambda a: m.set_value(state["v0"] + (to - state["v0"]) * a), None,
                                rate_functions.ease_out_cubic))

    def _grow(self, m, to, t0, t1) -> None:
        state = {}

        def start():
            state["v0"] = float(m.value)

        self.tweens.append(Call(t0, t1, start, lambda a: m.set_value(state["v0"] + (to - state["v0"]) * a), None,
                                rate_functions.ease_out_cubic))

    def _mark(self, name, m, kind, c, t0, t1) -> None:
        state = {}

        def start():
            if kind == "ring":
                mk = Ellipse(width=m.width + 0.6, height=m.height + 0.45, stroke_color=c, stroke_width=look.STROKE)
                mk.rotate(-0.08).move_to(m)
            else:
                mk = Line(m.get_corner(DOWN + LEFT) + DOWN * 0.12, m.get_corner(DOWN + RIGHT) + DOWN * 0.12,
                          stroke_color=c, stroke_width=look.STROKE)
            mk.set_z_index(m.z_index + 2)
            self.marks.setdefault(name, []).append(mk)
            self.add(mk)
            anim = Create(mk)
            anim.begin()
            state["anim"] = anim

        def step(a):
            state["anim"].interpolate(a)

        def stop():
            state["anim"].interpolate(1)
            state["anim"].finish()
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.ease_in_out_sine))

    def _flow(self, path, n, c, t0, t1) -> None:
        ds = [Dot(radius=0.09, color=c) for _ in range(n)]
        for d in ds:
            d.set_z_index(path.z_index + 1)

        def start():
            for d in ds:
                d.set_opacity(0)
                self.add(d)

        def step(a):
            for i, d in enumerate(ds):
                p = (a * 2.2 + i / n) % 1.0
                d.move_to(path.point_from_proportion(p))
                edge = min(p, 1 - p) * 8
                d.set_opacity(min(1.0, edge) * (1 - max(0.0, (a - 0.9) * 10)))

        def stop():
            for d in ds:
                self.remove(d)
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.linear))

    def _float(self, m, amp, t0, t1) -> None:
        state = {"y": 0.0}
        phase = (len(self.tweens) * 0.618) % 1 * math.tau     # the same in every chunk's process

        def step(a):
            t = t0 + a * (t1 - t0)
            y = amp * math.sin(t * 1.7 + phase)
            m.shift(UP * (y - state["y"]))
            state["y"] = y
        self.tweens.append(Call(t0, t1, None, step, None, rate_functions.linear))

    # ------------------------------------------------------------ the camera -------------------------------------------
    def _cam_target(self, act: S.Act) -> tuple[np.ndarray, float]:
        sc = self.SCORE
        zoom = self._opt(act, "zoom")
        ref = act.target
        if ref == "wide":
            xs = [s.x for s in sc.shots.values()]
            ys = [s.y for s in sc.shots.values()]
            c = np.array([(max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, 0])
            w = max(max(xs) - min(xs) + S.SCREEN_W, (max(ys) - min(ys) + S.SCREEN_H) * 16 / 9)
            return c, w * 1.1
        if ref in sc.shots:
            s = sc.shots[ref]
            c = np.array([s.x, s.y, 0.0])
            xy = next((a for a in act.args if re.match(r"^-?[\d.]+,-?[\d.]+$", a)), None)
            if xy:
                c = c + np.array([*(float(v) for v in xy.split(",")), 0.0])
            return c, S.SCREEN_W / (zoom or s.zoom)
        if ref not in self.E:
            # A place (`japan.tokyo`): the camera to it, as close as the zoom says.
            return self._locate(ref, ""), S.SCREEN_W / (zoom or 2.0)
        m = self.E[ref]
        w = max(m.width * 1.9, m.height * 1.9 * 16 / 9, 3.0)
        return m.get_center().copy(), (S.SCREEN_W / zoom) if zoom else w

    def _cam(self, act: S.Act) -> None:
        t0, t1 = act.t0 - 0.35, (act.t1 if act.t1 is not None else act.t0 - 0.35 + DEFAULT_RUN["cam"])
        f = self.camera.frame
        state = {}

        def start():
            state["c0"], state["w0"] = f.get_center().copy(), f.width
            state["c1"], state["w1"] = self._cam_target(act)

        def step(a):
            f.move_to(state["c0"] + (state["c1"] - state["c0"]) * a)
            # The width eases in log space, so a zoom feels even.
            f.set_width(math.exp(math.log(state["w0"]) + (math.log(state["w1"]) - math.log(state["w0"])) * a))
        tw = Call(max(0.0, t0), t1, start, step, None, rate_functions.ease_in_out_sine)
        tw.camera = True
        self.tweens.append(tw)

    def _introduce_the_rest(self) -> None:
        """An entity no action brings on fades in as its shot starts (the first action there): never a thing
        sitting still from the first frame. In the first shot, at the start, it is simply there."""
        sc = self.SCORE
        named = set()
        for a in sc.acts:
            if a.verb in ("in",):
                named |= {re.sub(r"\[.*", "", x) for x in a.target.split(",")}
            if a.verb == "morph" and a.args:
                named |= {re.sub(r"\[.*", "", x) for x in a.args[0].split(",")}
        starts: dict[str, float] = {}
        for a in sc.acts:
            sh = S.shot_of(sc, a.target)
            if sh:
                starts[sh] = min(starts.get(sh, 1e9), a.t0)
        for name, m in self.E.items():
            if name in named:
                continue
            t = starts.get(sc.ents[name].shot, 0.0) if name in sc.ents else 0.0
            if t <= 0.5:
                self.up.add(id(m))
                self.add(m)
            else:
                self._in(name, m, max(0.0, t - 0.3), t + 0.4, "fade")


RES = {"h": (1920, 1080, 30), "m": (1280, 720, 30), "l": (854, 480, 15)}


def frames_of(seconds: float, fps: int) -> int:
    return int(round(seconds * fps))


def jobs_default() -> int:
    """How many chunks render at once: V3_RENDER_JOBS, else half the machine's cores (at most 8)."""
    env = os.environ.get("V3_RENDER_JOBS", "").strip()
    return max(1, int(env)) if env.isdigit() else max(1, min(8, (os.cpu_count() or 2) // 2))


def _one(sc: S.Score, words: dict, voice_dir: Path, out: Path, quality: str, frames=None, sound=True,
         media: Path | None = None) -> None:
    ScoreScene.SCORE, ScoreScene.WORDS = sc, words
    ScoreScene.WAV = str(voice_dir / "voice.wav")
    ScoreScene.FRAMES, ScoreScene.SOUND = frames, sound
    w, h, fps = RES[quality]
    ScoreScene.FPS = fps
    with tempconfig({"pixel_width": w, "pixel_height": h, "frame_rate": fps, "media_dir": str(media or out.parent / "media"),
                     "output_file": out.stem, "disable_caching": True, "verbosity": "WARNING",
                     "progress_bar": "none"}):
        scene = ScoreScene()
        scene.render()
        made = Path(scene.renderer.file_writer.movie_file_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(made, out)


def render(score_text: str, voice_dir: Path, out: Path, quality: str = "h", span=None, jobs: int | None = None) -> list[str]:
    """The video. Long ones are cut into `jobs` chunks rendered at once, each in its own process, then joined and
    the voice laid under them. Returns the notes (lines left out or mended)."""
    words = json.loads((voice_dir / "words.json").read_text())
    sc = S.parse(score_text, words["words"], float(words["seconds"]))
    fps = RES[quality][2]
    total = frames_of(sc.end + TAIL, fps)
    if span:
        _one(sc, words, voice_dir, out, quality, (frames_of(span[0], fps), min(total, frames_of(span[1], fps))))
        return sc.notes
    jobs = jobs or jobs_default()
    if jobs <= 1 or total < 20 * fps:
        _one(sc, words, voice_dir, out, quality)
        return sc.notes
    parts = out.parent / ".parts"
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir(parents=True)
    (parts / "video.score").write_text(score_text)
    cuts = [round(total * k / jobs) for k in range(jobs + 1)]
    procs = []
    for k in range(jobs):
        cmd = [sys.executable, __file__, str(parts / "video.score"), str(voice_dir), str(parts / f"part{k}.mp4"),
               "--quality", quality, "--frames", f"{cuts[k]}:{cuts[k + 1]}", "--nosound", "--media", str(parts / f"media{k}")]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    outs = [p.communicate() for p in procs]
    for p, (o, e) in zip(procs, outs):
        if p.returncode != 0:
            raise RuntimeError(f"a chunk of the render failed:\n{(e or o)[-1500:]}")
    notes = [l[6:] for l in outs[0][0].splitlines() if l.startswith("note: ")]
    said = []
    for o, e in outs:
        said += [l for l in e.splitlines() if l.startswith("score line") and l not in said]
    for l in said:
        print(l, file=sys.stderr)
    (parts / "list.txt").write_text("".join(f"file 'part{k}.mp4'\n" for k in range(jobs)))
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(parts / "list.txt"),
                    "-i", str(voice_dir / "voice.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", str(out)], check=True)
    shutil.rmtree(parts, ignore_errors=True)
    return notes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("score")
    ap.add_argument("voice")
    ap.add_argument("out")
    ap.add_argument("--quality", default="m")
    ap.add_argument("--from", dest="t_from", type=float)
    ap.add_argument("--to", dest="t_to", type=float)
    ap.add_argument("--jobs", type=int, help="chunks rendered at once (default: V3_RENDER_JOBS, else half the cores)")
    ap.add_argument("--frames", help=argparse.SUPPRESS)        # a chunk (from:to), for render() itself
    ap.add_argument("--nosound", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--media", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.frames:
        words = json.loads((Path(a.voice) / "words.json").read_text())
        sc = S.parse(Path(a.score).read_text(), words["words"], float(words["seconds"]))
        f0, f1 = (int(x) for x in a.frames.split(":"))
        _one(sc, words, Path(a.voice), Path(a.out), a.quality, (f0, f1), not a.nosound, Path(a.media) if a.media else None)
        for n in sc.notes:
            print("note:", n)
        return
    span = (a.t_from or 0.0, a.t_to) if a.t_to else None
    notes = render(Path(a.score).read_text(), Path(a.voice), Path(a.out), a.quality, span, a.jobs)
    for n in notes:
        print("note:", n)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
