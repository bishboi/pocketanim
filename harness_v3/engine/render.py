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
    cam SHOT via page|tear|whip | cam SHOT via dive [into REF]   (dive: into a thing, which opens on the next shot)
    bring T to SHOT [X,Y]                            (T travels on the screen with the camera into another shot)
    chapter "TITLE"                                  (the chapter bar along the bottom moves on to it)
    walk P to X,Y|ENT|MAP.place | point P at REF | wave P | talk P ["WORDS"] | carry P THING | sit P | stand P
        | turn P left|right                          (a person's poses)

The paper world (feel.py): a cut-out comes on slapped down and leaves peeled off unless the score says how; moves
overshoot a little and settle; what lands nudges its neighbours; outlines boil and lines are drawn by a pen; grain and
a vignette lie over the frame; the layers slide at their own speeds as the camera travels between shots.
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

from manim import (DOWN, LEFT, RIGHT, UP, Circle, Create, Dot, Ellipse, Group, ImageMobject, Line, Mobject, Rectangle,
                   RoundedRectangle, Polygon,
                   MovingCameraScene, ReplacementTransform, VGroup, VMobject, Write, config, rate_functions,
                   tempconfig)
from manim.utils.color import ManimColor, interpolate_color

import feel
import look
import score as S

LEAD = 0.18             # an action lands on its word: it starts this much before it
# Kinds drawn on another piece (`on NAME` / `map NAME`), where they stand on it.
ON_PARENT = ("region", "pin", "river", "event", "span", "labels", "bubble", "lens", "shade", "inset")
# The marks a verb draws, and each one's colour when none is said.
MARKS = {"ring": "coral", "circle": "coral", "mark": "coral", "underline": "coral", "highlight": "accent",
         "strike": "red", "box": "coral", "tick": "green", "cross": "red", "stamp": "red", "callout": "ink"}
SIDES = ("left", "right", "up", "down")
# Putting a thing against another (`below X`...), and what goes beside a piece's part when put `at` it.
REL = ("below", "above", "left", "right")
PIECES = {"flow", "tree", "pyramid", "cycle", "compare", "table", "steps", "list", "venn", "chart", "layers", "circuit"}
BESIDE_KINDS = {"pic", "photo", "icon", "tag", "card", "label", "text", "num", "flag", "dots", "stat", "portrait",
                "person", "phrase", "nation", "country"}
HUD_Z = 970             # what stays on the screen (captions, the chapter bar) over everything but the grain

DEFAULT_RUN = {"in": 0.7, "out": 0.5, "move": 0.9, "along": 1.6, "morph": 0.9, "color": 0.6, "dim": 0.5, "lift": 0.5,
               "scale": 0.7, "spin": 0.8, "pulse": 0.55, "shake": 0.5, "count": 1.2, "grow": 1.0, "ring": 0.6,
               "mark": 0.5, "flow": 2.0, "cam": 1.4, "circle": 0.6, "underline": 0.5, "highlight": 0.6, "strike": 0.4,
               "box": 0.6, "tick": 0.4, "cross": 0.4, "stamp": 0.3, "callout": 0.8, "bracket": 0.6, "spotlight": 0.6,
               "pan": 6.0, "type": 1.2, "fill": 1.0, "connect": 0.8, "follow": 2.0, "tip": 1.0, "era": 1.6, "glow": 0.8,
               "walk": 2.0, "point": 0.6, "wave": 1.6, "talk": 2.0, "carry": 0.8, "sit": 0.7, "stand": 0.6,
               "turn": 0.4, "bring": 1.4, "chapter": 0.1, "run": 1.2, "cheer": 1.4, "shrug": 1.0,
               "think": 1.6, "bow": 1.2, "jump": 0.9, "nod": 0.8, "emote": 0.5, "dance": 3.0, "clap": 1.6,
               "facepalm": 1.8, "laugh": 1.8, "cry": 2.4, "shiver": 1.6, "kick": 0.7, "look": 0.5, "faint": 1.0,
               "hug": 1.6}
PERSON_VERBS = ("walk", "run", "point", "wave", "talk", "carry", "sit", "stand", "turn", "cheer", "shrug", "think",
                "bow", "jump", "nod", "emote", "dance", "clap", "facepalm", "laugh", "cry", "shiver", "kick", "look",
                "faint", "hug")
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
        self.m = m
        self.base = []
        managed = getattr(m, "managed_ids", set())     # a person's face parts: it fades them itself (refade)
        for x in leaves(m):
            if id(x) in managed:
                continue
            try:
                self.base.append((x, float(x.get_fill_opacity()), float(x.get_stroke_opacity())))
            except Exception:  # noqa: BLE001
                self.base.append((x, 1.0, 1.0))
        self.now = 1.0

    def set(self, a: float) -> None:
        self.now = a
        if isinstance(self.m, look.Num) and self.base and self.m.submobjects and \
                not any(self.base[0][0] is x for x in self.m.submobjects[0].get_family()):
            self.base = [(x, 1.0, 1.0) for x in leaves(self.m)]     # a number redrawn as it counts
        for x, f, s in self.base:
            if isinstance(x, ImageMobject):
                x.set_opacity(max(0.0, min(1.0, a)))      # from the picture's own alpha
                continue
            x.set_fill(opacity=f * a, family=False)
            x.set_stroke(opacity=s * a, family=False)
        if hasattr(self.m, "refade"):
            self.m.refade(a)


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
    BOIL: bool = True                          # outlines tremble as drawn (the player draws its own from the timeline)

    def construct(self):
        sc, words = self.SCORE, self.WORDS
        look.use(sc.look)
        self.camera.background_color = ManimColor(look.L["bg"])
        self.E: dict[str, Mobject] = {}          # entity name -> its mobject
        self.alpha: dict[int, Alpha] = {}
        self.marks: dict[str, list] = {}         # entity name -> rings and lines drawn on it
        self.fills: dict[str, dict] = {}         # entity name -> the level a `fill` has brought it to
        self.follows: list[list] = []            # [mark, what it marks, where that was, a fill's record]: kept together
        self.up: set[int] = set()                # what is on the screen
        self.tweens: list[Tween] = []
        self.clock = 0.0
        self.texture, self.motion = feel.texture_on(sc), feel.motion_on(sc)
        self.parallax = feel.parallax_on(sc)
        self.hud: list[list] = []                # [mobject, scale it was placed at, centre it was placed at]
        self.hud_hooks: list = []
        self.boiled: list = []                   # the trembles applied this frame, undone at the next
        self.boil_ids: dict[int, int] = {}
        self._paper()
        self._build()
        self._spread()
        self._depths()
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
        self._weather()
        self._blinks()
        self._numbers_said()
        self._captions()
        self._progress()
        self._overlay()
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
        self._drawing = (0, f1 - f0, max(1, (f1 - f0) // 100))    # (drawn, to draw, say every)
        print(f"progress: 0/{f1 - f0} frames drawn", flush=True)
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
        # What stands on another piece (a map's regions, a timeline's events, a picture's labels) and paths are drawn
        # after what they name.
        paths = [e for e in ents if e.kind in ("path", "march") or e.kind in ON_PARENT]
        last = [e for e in ents if e.kind == "arrow" or (e.mods.get("on") and e.kind != "path" and e.kind not in ON_PARENT)]
        rel = [e for e in ents if any(isinstance(e.mods.get(k), str) for k in REL)
               or (isinstance(e.mods.get("at"), str) and e.mods["at"].split(".", 1)[0] in sc.ents and e not in paths)]
        first = [e for e in ents if e not in paths and e not in last and e not in rel]
        rel = [e for e in rel if e not in paths and e not in last]
        # what is placed against another thing waits for it (a chain: each pass places what it can)
        placed = {e.name for e in first}
        for _ in range(len(rel) + 1):
            ready = [e for e in rel if all(self._against(e, x) in placed or self._against(e, x) not in sc.ents
                                           for x in (*REL, "at"))]
            first += ready
            placed |= {e.name for e in ready}
            rel = [e for e in rel if e not in ready]
            if not rel:
                break
        for e in first + rel + paths + last:
            try:
                self._make(e)
            except Exception as ex:  # noqa: BLE001
                sc.notes.append(f"line {e.line}: {e.name} ({e.kind}) left out: {ex}")
                self.E.pop(e.name, None)
        for name in [n for n in sc.ents if n not in self.E]:
            del sc.ents[name]
        self._declutter_pins()

    def _declutter_pins(self) -> None:
        """Pins' names on one map kept off each other: each name not given a side goes to the side (right, left,
        above, below its dot) that covers the fewest of the names and dots already there."""
        sc = self.SCORE
        maps: dict[str, list[str]] = {}
        for n, e in sc.ents.items():
            if e.kind == "pin" and n in self.E and len(self.E[n]) > 1:
                maps.setdefault(str(e.mods.get("on")), []).append(n)

        def box(m):
            lo, hi = m.get_corner(DOWN + LEFT), m.get_corner(UP + RIGHT)
            return lo[0], lo[1], hi[0], hi[1]

        def cover(a, b):
            w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
            return max(0.0, w) * max(0.0, h)
        for pins in maps.values():
            if len(pins) < 2:
                continue
            taken = [box(self.E[n][0]) for n in pins]                  # every dot
            for n in pins:
                dot, words = self.E[n][0], self.E[n][1]
                if sc.ents[n].mods.get("side"):
                    taken.append(box(words))
                    continue
                best, where = None, None
                for side in (RIGHT, LEFT, UP, DOWN):
                    words.next_to(dot, side, buff=0.12)
                    b = box(words)
                    k = sum(cover(b, t) for t in taken) + (0.001 if side is not RIGHT else 0.0)
                    if best is None or k < best - 1e-6:
                        best, where = k, side
                words.next_to(dot, where, buff=0.12)
                taken.append(box(words))

    # Kinds a layout mend may move: what a small model places by number. Lands, seas, paths, arrows and rings are
    # placed against other things on purpose, and an entity placed on another (`at ENT`, `on PATH`) is meant there.
    SPREAD = {"icon", "text", "rect", "circle", "blob", "num", "bar", "dots", "pic", "photo", "flag", "card", "tag",
              "label", "timeline", "chart", "pyramid", "cycle", "flow", "quote", "doc", "title", "compare", "table",
              "list", "steps", "stat", "calendar", "meter", "balance", "venn", "formula", "portrait", "tree",
              "numberline", "plot", "triangle", "molecule", "equation", "circuit", "race", "parliament", "market",
              "climate", "quiz", "clock", "odometer", "clipping", "layers", "globe", "who", "polaroids", "person",
              "nation", "country"}
    HOLDERS = {"rect", "circle", "blob", "card", "photo", "split"}

    def _holder(self, e: S.Ent) -> bool:
        """A shape that things are put on: a box, a disc, a region, an icon on its badge."""
        return e.kind in self.HOLDERS or (e.kind == "icon" and bool(e.mods.get("badge")))

    def _spread(self) -> None:
        """Things of one shot up at the same time that partly overlap are pushed apart (the later one moves, along
        the shorter way out, kept on its shot's screen). One inside the other (a label on a box, an icon on its
        badge) is left: that is meant, as is one given another `layer` (a rat over the ship)."""
        sc = self.SCORE
        times = self._up_times()
        for shot in sc.shots.values():
            ents = [e for e in sc.ents.values() if e.shot == shot.name and e.kind in self.SPREAD
                    and not e.mods.get("on") and not isinstance(e.mods.get("at"), str)
                    and not any(isinstance(e.mods.get(k), str) for k in REL)]
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
                        if a.mods.get("layer") != b.mods.get("layer"):     # one put over the other on purpose
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

    SIDE_OF = {"center": None, "centre": None, "middle": None, "left": LEFT, "right": RIGHT, "top": UP, "up": UP,
               "bottom": DOWN, "down": DOWN}

    def _locate(self, ref: str, shot: str) -> np.ndarray:
        if ref in self.E:
            return self.E[ref].get_center()
        base, _, side = ref.rpartition(".")
        if base and side in self.SIDE_OF and (base in self.E or "[" in base):
            # a thing's or a part's middle or edge (`cmp[0].left`, `card.top`)
            m = self._targets(base)[0][1]
            d = self.SIDE_OF[side]
            return m.get_center() if d is None else m.get_critical_point(d)
        if "[" in ref and re.match(r"^[\w\-]+\[\-?\d+\]$", ref) and ref.split("[")[0] in self.E:
            return self._targets(ref)[0][1].get_center()
        if "." in ref and ref.split(".", 1)[0] in self.E:
            # A place on a land (`japan.tokyo`).
            ent, place = ref.split(".", 1)
            places = getattr(self.E[ent], "places", {})
            if place not in places:
                raise ValueError(f"{ent} has no place {place!r} ({', '.join(places)})")
            return places[place].get_center()
        x, y = (float(v) for v in ref.split(","))
        return self._origin(shot) + np.array([x, y, 0.0])

    @staticmethod
    def _against(e: S.Ent, key: str) -> str:
        v = e.mods.get(key)
        return v.split(".", 1)[0] if isinstance(v, str) else ""

    def _relation(self, e: S.Ent):
        """Where a thing is put against another, if it is: `below X`, `above X`, `left X`, `right X` (X a thing or a
        named part of a piece: `below fl.economic`); and a picture, icon or words put `at` a piece's part (a flow's
        node, a pyramid's level) goes beside it, not over it (`side up|down|left|right`, below by default)."""
        for k in REL:
            if isinstance(e.mods.get(k), str):
                return k, e.mods[k]
        at = e.mods.get("at")
        if isinstance(at, str) and "." in at and e.kind in BESIDE_KINDS:
            base = self.SCORE.ents.get(at.split(".", 1)[0])
            if base is not None and base.kind in PIECES:
                side = {"up": "above", "down": "below", "left": "left", "right": "right"}.get(str(e.mods.get("side")), "below")
                return side, at
        return None

    def _beside(self, m, how: str, ref: str, e: S.Ent) -> None:
        """`m` put against `ref`'s edge (`gap` apart, 0.3 by default), centred along it."""
        base, _, part = ref.partition(".")
        target = None
        if ref in self.E:
            target = self.E[ref]
        elif part and base in self.E:
            hit = getattr(self.E[base], "places", {})[part] if part in getattr(self.E[base], "places", {}) else None
            target = hit if isinstance(hit, Mobject) else None
            if target is None and hit is not None:     # a point (a year, a town): beside the point
                p = hit.get_center()
                lo = hi = np.array(p)
            elif target is None:
                raise ValueError(f"{base} has no part {part!r}")
        else:
            raise ValueError(f"no thing {ref!r} to put it {how}")
        if target is not None:
            target = getattr(target, "core", target)
            lo, hi = target.get_corner(DOWN + LEFT), target.get_corner(UP + RIGHT)
        gap = float(e.mods.get("gap", 0.3)) if e.mods.get("x") is None else 0.3
        c = (lo + hi) / 2
        w, h = m.width, m.height

        def spot(side):
            return {"below": [c[0], lo[1] - gap - h / 2], "above": [c[0], hi[1] + gap + h / 2],
                    "left": [lo[0] - gap - w / 2, c[1]], "right": [hi[0] + gap + w / 2, c[1]]}[side]
        to = spot(how)
        if part and base in self.E and target is not None:
            # Beside a piece's part: the first side (the one asked for first) that keeps clear of its other parts.
            others = [getattr(p, "core", p) for p in self.E[base].submobjects if p is not target
                      and getattr(p, "core", p) is not target]

            def clear(xy):
                x0, y0, x1, y1 = xy[0] - w / 2, xy[1] - h / 2, xy[0] + w / 2, xy[1] + h / 2
                return not any(min(x1, q.get_right()[0]) > max(x0, q.get_left()[0]) + 0.05 and
                               min(y1, q.get_top()[1]) > max(y0, q.get_bottom()[1]) + 0.05 for q in others)
            for side in (how, *[x for x in ("below", "right", "above", "left") if x != how]):
                if clear(spot(side)):
                    to = spot(side)
                    break
        m.move_to([to[0], to[1], 0.0])

    def _make(self, e: S.Ent) -> None:
        if e.kind == "labels":                  # the shot's screen, so names stay on it
            o = self._origin(e.shot)
            e.mods["_screen"] = (o[0] - S.SCREEN_W / 2 + 0.3, o[0] + S.SCREEN_W / 2 - 0.3)

        if e.kind in ("person", "nation", "country"):
            e.mods.setdefault("_name", e.name)      # its looks picked from its name when the score does not say
        def one():
            return look.build(e.kind, e.args, e.mods, locate=lambda r: self._locate(r, e.shot),
                              find=lambda n: self.E.get(n))
        m = look.copies(one, int(e.mods["x"]), e.mods) if int(e.mods.get("x", 1)) > 1 else one()
        if e.mods.get("rot"):
            m.rotate(math.radians(float(e.mods["rot"])))
        if self.texture and e.kind in ("arrow", "path"):
            feel.wobbled(m, 0.028, e.name)          # a line drawn by hand
        on_map = e.kind in ON_PARENT        # drawn where it stands on its map, timeline or picture
        if (e.kind not in ("land", "waves", "path", "arrow", "islands", "map", "backdrop", "weather", "march") and not on_map
                and (m.width > 12 or m.height > 7)):
            m.scale(min(12 / m.width, 7 / m.height))      # nothing bigger than the screen
        if e.mods.get("on") and len(m.submobjects) > 1 and not on_map:
            # Its copies (or dots) spread along a path, evenly.
            track = self._track(self.E[e.mods["on"]])
            n = len(m.submobjects)
            for i, part in enumerate(m.submobjects):
                part.move_to(track.point_from_proportion((i + 0.5) / n))
        elif e.kind not in ("arrow", "path") and not on_map:
            at = e.mods.get("at", (0.0, 0.0))
            where = self._locate(at, e.shot) if isinstance(at, str) else self._origin(e.shot) + np.array([at[0], at[1], 0.0])
            m.move_to(where)
            if e.kind in ("person", "nation", "country"):     # a figure stands where it is put: its feet there
                m.shift(where - m.feet())
            rel = self._relation(e)
            if rel:
                self._beside(m, rel[0], rel[1], e)
        if e.mods.get("nudge"):
            m.shift(np.array([*e.mods["nudge"], 0.0]))
        if e.kind == "map" and e.shot in self.SCORE.shots:
            # Kept on its screen as it is placed, before anything is drawn on it (its regions and pins follow).
            self._on_screen(m, self.SCORE.shots[e.shot])
        # A region sits under what is on it; a map under its regions, a pin over them.
        layer = int(e.mods.get("layer", -5 if e.kind == "backdrop" else -3 if e.kind == "split" else -2 if e.kind == "map"
                               else -1 if e.kind in ("blob", "islands", "region", "river")
                               else 1 if e.kind in ("pin", "labels", "bubble") else 4 if e.kind == "weather" else 0))
        if e.kind == "backdrop" and e.mods.get("opacity") is None:
            e.mods["opacity"] = 0.3                 # softened: the shot's things stand out on it
        m.set_z_index(layer * 10 + (5 if e.kind in ("text", "num") else 0))
        if e.mods.get("opacity") is not None:
            Alpha(m).set(float(e.mods["opacity"]))
        self.E[e.name] = m

    # ------------------------------------------------------------ targets ----------------------------------------------
    def _targets(self, ref: str) -> list:
        out = []
        for one in ref.split(","):
            base, _, part = one.strip().partition(".")
            if part and base in self.E and part in getattr(self.E[base], "places", {}):
                hit = self.E[base].places[part]       # a named part of a piece (`fl.town`, `soc.nobles`)
                if isinstance(hit, Mobject):
                    out.append((base, hit))
                    continue
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
    CREEP = 0.035           # and how far it goes at most after a camera move

    def _tick(self, dt: float) -> None:
        drawing = getattr(self, "_drawing", None)
        if drawing and dt > 0:
            n, total, every = drawing
            n += 1
            self._drawing = (n, total, every)
            if n % every == 0 or n >= total - 1:
                print(f"progress: {min(n + 1, total)}/{total} frames drawn", flush=True)
        # The clock is the frame's own time (frames / fps), not a sum of steps: every engine that plays the score
        # (the render, its chunks, the timeline for the player) starts each action on the same frame.
        if dt > 0:
            self._frame_no = getattr(self, "_frame_no", 0) + 1
            self.clock = self._frame_no / self.FPS
        else:
            self.clock += dt
        t = self.clock
        self._unboil()
        if any(isinstance(tw, Call) and getattr(tw, "camera", False) and tw.t0 <= t <= tw.t1 for tw in self.tweens):
            self._crept = 0.0                   # a camera move: the creep starts again after it
        elif dt and getattr(self, "_crept", 0.0) < self.CREEP:
            # Never quite still: the view creeps in, as a camera on a slow dolly; at most CREEP of the view after a
            # camera move, so a long shot does not crop what was placed near its edges.
            self.camera.frame.scale(1 - self.DRIFT * dt)
            self._crept = getattr(self, "_crept", 0.0) + self.DRIFT * dt
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
        if self.parallax:
            self._parallax()
        # A mark goes where what it marks goes (a ring round a thing that then moves, a fill in a box that slides).
        for rec in self.follows:
            mk, what, last, fill = rec
            c = what.get_center()
            if not np.allclose(c, last, atol=1e-4):
                mk.shift(c - last)
                if fill is not None:
                    fill["base"] += (c - last)[1]
                rec[2] = c.copy()
        self._place_hud()
        if self.BOIL and self.texture and dt:
            self._boil()
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
        if v == "in" and how == "speak" and any(self._kind(n) not in ("phrase", "text", "label", "tag", "title", "quote")
                                                for n, _ in self._targets(act.target)):
            how = None                          # (only words are spoken on: anything else comes on its own way)
        if v == "in" and how == "speak":
            for name, m in self._targets(act.target):
                end = act.t1 if act.t1 is not None else t0 + 0.38 * max(1, len(m.submobjects))
                self._speak(name, m, act, t0, end)
        elif v == "in":
            items = self._targets(act.target)
            if len(items) == 1 and stagger is not None and len(items[0][1].submobjects) > 1:
                items = [(items[0][0], p) for p in items[0][1].submobjects]
            for (name, m), a0, a1 in self._staggered(items, t0, t1, stagger):
                self._in(name, m, a0, a1, how or self._default_way(name, m, "in"))
        elif v == "out":
            items = self._targets(act.target)
            if len(items) == 1 and stagger is not None and len(items[0][1].submobjects) > 1:
                items = [(items[0][0], p) for p in items[0][1].submobjects]
            for (name, m), a0, a1 in self._staggered(items, t0, t1, stagger):
                self._out(name, m, a0, a1, how or self._default_way(name, m, "out"))
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
                    to = float(act.args[0]) if v == "dim" and act.args else (0.3 if v == "dim" else 1.0)
                    self._fade_to(m, to, a0, a1)
                    if m is self.E.get(name):           # its marks (a ring, a highlight) dim with it
                        self._fade_marks(name, to, a0, a1)
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
        elif v == "pan":
            # Slowly into a picture (a camera over a still): `pan T [zoom K] [by DX,DY]`.
            k = float(self._opt(act, "zoom", 1.12))
            by = self._opt(act, "by", "0,0", str)
            d = np.array([*(float(x) for x in by.split(",")), 0.0])
            for (name, m) in self._targets(act.target):
                self._pan(m, k, d, t0, t1 if act.t1 is not None else t0 + DEFAULT_RUN["pan"])
        elif v == "type":
            for (name, m) in self._targets(act.target):
                self._type(name, m, t0, t1)
        elif v == "fill":
            to = float(next((a for a in act.args if re.match(r"^[\d.]+$", a)), "1"))
            colour = look.col(next((a for a in act.args if a in look.L), "sky"))
            for (name, m) in self._targets(act.target):
                self._fill(name, m, min(1.0, to / 100 if to > 1 else to), colour, t0, t1)
        elif v == "connect":
            (na, ma), = self._targets(act.target)[:1]
            (nb, mb), = self._targets(act.args[0])[:1]
            words = next((a for a in act.args[1:] if a not in look.L), "")
            self._connect(na, ma, mb, words, look.col(next((a for a in act.args[1:] if a in look.L), "ink")), t0, t1)
        elif v == "follow":
            (name, m), = self._targets(act.target)[:1]
            self._follow(m, self._opt(act, "zoom"), t0, t1)
        elif v == "tip":
            import kit
            way = {"left": -0.2, "right": 0.2}.get(act.args[0] if act.args else "level", 0.0)
            for (name, m) in self._targets(act.target):
                if isinstance(m, kit.Balance):
                    self._tip(m, way, t0, t1)
        elif v == "era":
            # A map's states as they stood in another year, crossfaded in (empires rising and falling).
            (name, m), = self._targets(act.target)[:1]
            if not isinstance(m, look.GeoMap):
                raise ValueError("era is a map's: `era MAP YEAR`")
            self._era(name, m, int(float(act.args[0])), t0, t1)
        elif v == "glow":
            colour = look.col(next((a for a in act.args if a in look.L), "accent"))
            for (name, m) in self._targets(act.target):
                if m is self.E[name] and self._kind(name) == "pin":
                    m = m[0]                    # a pin glows at its dot, not round its name
                self._glow(name, m, colour, t0, t1)
        elif v == "spotlight":
            self._spotlight(act.target, float(self._opt(act, "dim", 0.22)), t0, t1)
        elif v == "bracket":
            items = self._targets(act.target)
            words = next((a for a in act.args if a not in look.L), "")
            colour = look.col(next((a for a in act.args if a in look.L), "ink"))
            self._mark(items[0][0], Group(*(m for _, m in items)), "bracket", colour, t0, t1, words)
        elif v in MARKS:
            words = next((a for a in act.args if a not in look.L and a not in SIDES), "")
            side = next((a for a in act.args if a in SIDES), None)
            colour = look.col(next((a for a in act.args if a in look.L), MARKS[v]))
            for (name, m) in self._targets(act.target):
                if m is self.E[name] and self.SCORE.ents[name].kind == "pin":
                    m = m[0]                # a pin is marked at its dot, not round its name
                self._mark(name, m, v, colour, t0, t1, words, side)
        elif v == "flow":
            self._flow(self._track(self.E[act.target]), int(self._opt(act, "n", 6, int)),
                       look.col(next((x for x in act.args if x in look.L), "coral")), t0, t1)
        elif v in PERSON_VERBS:
            self._person(act, t0, t1)
        elif v == "bring":
            (name, m), = self._targets(act.target)[:1]
            self._bring(name, m, act, t0, t1 if act.t1 is not None else t0 + DEFAULT_RUN["bring"])
        elif v == "chapter":
            pass                                # the chapter bar reads these (_progress)
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
    def _kind(self, name: str) -> str:
        e = self.SCORE.ents.get(name)
        return e.kind if e else ""

    def _default_way(self, name, m, way: str) -> str:
        """How a thing comes on or goes when the score does not say: a paper cut-out slapped down and peeled off, a
        person stepping up, the rest faded."""
        kind = self._kind(name)
        if not self.motion or m is not self.E.get(name):
            return "fade"
        if kind in ("person", "nation", "country"):
            return "rise" if way == "in" else "fade"
        if kind in feel.CUTOUTS:
            return "slap" if way == "in" else "peel"
        return "fade"

    def _in(self, name, m, t0, t1, how) -> None:
        al = self._alpha(m)
        state = {}
        if how == "slap":
            return self._slap(name, m, t0, t1)
        kind = self._kind(name)
        pen = how == "draw" and self.texture and kind in ("arrow", "path", "river", "march")

        def start():
            self._show(name, m)
            c = m.get_center()
            if how in ("draw", "write") and not has_picture(m):
                al.set(1.0)
                anim = (Write(m) if how == "write" else Create(m, lag_ratio=0.05))
                anim.begin()
                state["anim"] = anim
                if pen:                         # the pen's nib, at the head of the line as it is drawn
                    nib = Dot(radius=0.055, color=look.col("ink")).set_z_index(max(x.z_index for x in m.get_family()) + 1)
                    state["nib"], state["track"] = nib, self._track(m)
                    self.add(nib)
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
                if "nib" in state:
                    state["nib"].move_to(state["track"].point_from_proportion(min(1.0, max(0.0, a))))
                return
            al.set(min(1.0, a * 1.6) if how in ("pop", "grow") else min(1.0, max(0.0, a)))
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
            if "nib" in state:
                self.remove(state["nib"])
        rate = {"pop": rate_functions.ease_out_back, "grow": rate_functions.ease_out_back, "drop": rate_functions.ease_out_back,
                "slide-left": feel.settle if self.motion else rate_functions.ease_out_cubic,
                "slide-right": feel.settle if self.motion else rate_functions.ease_out_cubic,
                "rise": rate_functions.ease_out_cubic, "draw": feel.pen if pen else rate_functions.ease_in_out_sine,
                "write": rate_functions.linear}.get(how, rate_functions.smooth)
        self.tweens.append(Call(t0, t1, start, step, stop, rate))
        if self.motion and how in ("pop", "drop") and m is self.E.get(name):
            self._nudge(name, m, t0 + (t1 - t0) * 0.6)

    @staticmethod
    def _undo(m, st) -> None:
        """A tween's own turn, shift and scale of a thing taken off it (see _redo)."""
        k, r, d, p = st["tf"]
        if k != 1.0:
            m.scale(1 / k, about_point=p + d)
        if d.any():
            m.shift(-d)
        if r:
            m.rotate(-r, about_point=p)

    @staticmethod
    def _redo(m, st, k: float, r: float, d) -> None:
        """Turned by r about the tween's pivot, shifted by d and scaled by k: each step undoes the last first, so
        what other tweens do to the thing meanwhile is kept and nothing is left over at the end."""
        p = st["pivot"]
        d = np.asarray(d, dtype=float)
        if r:
            m.rotate(r, about_point=p)
        if d.any():
            m.shift(d)
        if k != 1.0:
            m.scale(k, about_point=p + d)
        st["tf"] = (k, r, d, p)

    def _slap(self, name, m, t0, t1) -> None:
        """A cut-out slapped down: in bigger and turned, its shadow tightening under it, a small wobble as it lands."""
        al = self._alpha(m)
        st = {}
        sign = 1 if feel.seed(name + str(round(t0, 2))) % 2 else -1
        t1 = max(t1, t0 + 0.55)

        def start():
            self._show(name, m)
            al.set(0.0)
            st["pivot"] = m.get_center().copy()
            st["tf"] = (1.0, 0.0, np.zeros(3), st["pivot"])
            w, h = max(m.width, 0.2), max(m.height, 0.2)
            sh = RoundedRectangle(width=w, height=h, corner_radius=min(w, h) * 0.06, fill_color=look.L["ink"],
                                  fill_opacity=0.0, stroke_width=0).move_to(st["pivot"])
            sh.set_z_index(min(x.z_index for x in m.get_family()) - 1)
            st["sh"], st["sh_at"], st["sh_k"] = sh, np.zeros(3), 1.0
            self.add(sh)

        def step(a):
            self._undo(m, st)
            e = feel.slap(a)
            k = 1.22 + (1.0 - 1.22) * e
            land = 0.55
            r = sign * 0.12 * (1 - min(1.0, a / land)) ** 2 if a < land else feel.wobble_angle((a - land) / (1 - land), sign * -0.035)
            self._redo(m, st, k, r, np.zeros(3))
            al.set(min(1.0, a * 4))
            sh = st["sh"]                       # the shadow: wide and far while it falls, tight as it lands
            off = np.array([0.32, -0.42, 0.0]) * (1 - min(1.0, a / land)) + np.array([0.05, -0.07, 0.0])
            sk = 1.0 + 0.12 * (1 - min(1.0, a / land))
            sh.shift(off - st["sh_at"])
            sh.scale(sk / st["sh_k"])
            st["sh_at"], st["sh_k"] = off, sk
            sh.set_fill(opacity=0.2 * min(1.0, a * 3) * (1 - max(0.0, (a - land) / (1 - land))))

        def stop():
            self._undo(m, st)
            st["tf"] = (1.0, 0.0, np.zeros(3), st["pivot"])
            al.set(1.0)
            self.remove(st["sh"])
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.linear))
        self._nudge(name, m, t0 + (t1 - t0) * 0.55)

    def _nudge(self, name, m, t) -> None:
        """What stands near a thing that lands is pushed a little away from it, and comes back (follow-through)."""
        if not self.motion:
            return
        st = {}
        parents = {e.mods.get("on") for e in self.SCORE.ents.values()} | {e.mods.get("map") for e in self.SCORE.ents.values()}
        still = {"map", "backdrop", "region", "river", "pin", "weather", "labels", "split", "globe", "path", "arrow",
                 "march", "shade", "inset", "lens", "land", "waves", "islands", "event", "span", "bubble"}

        def start():
            here = self.SCORE.ents[name].shot if name in self.SCORE.ents else None
            c = m.get_center()
            st["near"] = []
            for n, mob in self.E.items():
                e = self.SCORE.ents.get(n)
                if n == name or e is None or e.shot != here or e.kind in still or n in parents or id(mob) not in self.up:
                    continue
                if mob.width > 6 or mob.height > 4 or self._alpha(mob).now < 0.05:
                    continue
                d = mob.get_center() - c
                dist = float(np.linalg.norm(d[:2]))
                if 0.05 < dist < 3.2:
                    st["near"].append([mob, d / dist * 0.075 * (1 - dist / 3.2), np.zeros(3)])

        def step(a):
            for rec in st["near"]:
                off = rec[1] * math.sin(math.pi * a) * (1 - 0.3 * a)
                rec[0].shift(off - rec[2])
                rec[2] = off

        def stop():
            for rec in st["near"]:
                rec[0].shift(-rec[2])
        self.tweens.append(Call(t, t + 0.42, start, step, stop, rate_functions.linear))

    def _out(self, name, m, t0, t1, how) -> None:
        al = self._alpha(m)
        st = {}
        sign = 1 if feel.seed(name) % 2 else -1

        def start():
            st["a0"] = al.now
            st["pivot"] = (m.get_corner(DOWN + (LEFT if sign > 0 else RIGHT)) if how == "peel" else m.get_center()).copy()
            st["tf"] = (1.0, 0.0, np.zeros(3), st["pivot"])

        def step(a):
            self._undo(m, st)
            if how == "peel":
                # a corner lifted, then flicked away
                lift = min(1.0, a / 0.35)
                fly = max(0.0, (a - 0.35) / 0.65) ** 2
                r = sign * (0.07 * lift + 0.45 * fly)
                d = np.array([sign * 2.0 * fly, 1.6 * fly, 0.0])
                self._redo(m, st, 1.0 + 0.05 * lift, r, d)
                al.set(st["a0"] * (1 - max(0.0, (a - 0.45) / 0.55)))
                return
            al.set(st["a0"] * (1 - a))
            k = max(1 - 0.8 * a, 0.05) if how == "shrink" else 1.0
            d = DOWN * 0.8 * a if how == "drop" else np.zeros(3)
            self._redo(m, st, k, 0.0, d)

        def stop():
            for mk in self.marks.get(name, []) if m is self.E.get(name) else []:
                self.remove(mk)
            if m is self.E.get(name):
                self.remove(m)
                self.up.discard(id(m))
            self._undo(m, st)                   # back as it was, should it come on again
            st["tf"] = (1.0, 0.0, np.zeros(3), st["pivot"])
        if how == "peel":
            t1 = max(t1, t0 + 0.6)
        rate = rate_functions.ease_in_cubic if how == "drop" else rate_functions.linear if how == "peel" else rate_functions.smooth
        self.tweens.append(Call(t0, t1, start, step, stop, rate))
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
        # A cut-out slid on the page: past its place a little and back, tilting the way it goes.
        paper = self.motion and self._kind(name) in feel.CUTOUTS | {"text", "label", "num", "icon", "dots"}

        def start():
            state["p0"] = m.get_center().copy()
            state["p1"] = self._dest(name, m, act)
            state["at"] = np.zeros(3)
            state["r"], state["c"] = 0.0, None

        def step(a):
            if state["r"]:
                m.rotate(-state["r"], about_point=state["c"])
                state["r"] = 0.0
            p0, p1 = state["p0"], state["p1"]
            d = p1 - p0
            n = np.array([-d[1], d[0], 0.0])
            n = n / (np.linalg.norm(n) + 1e-9)
            off = d * a + n * arc * math.sin(math.pi * min(a, 1.0)) * np.linalg.norm(d) * 0.35
            m.shift(off - state["at"])
            state["at"] = off
            if paper and abs(d[0]) > 0.3:
                r = -math.copysign(1.0, d[0]) * 0.055 * math.sin(math.pi * min(1.0, max(0.0, a)))
                state["c"] = m.get_center().copy()
                m.rotate(r, about_point=state["c"])
                state["r"] = r

        def stop():
            if state["r"]:
                m.rotate(-state["r"], about_point=state["c"])
                state["r"] = 0.0
        self.tweens.append(Call(t0, t1, start, step, stop, feel.settle if self.motion else rate_functions.ease_in_out_cubic))

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
        if has_picture(ma) or has_picture(mb):
            return self._swap(na, ma, nb, mb, t0, t1)
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

    def _swap(self, na, ma, nb, mb, t0, t1) -> None:
        """One thing becoming another where a picture is in it (no points to blend): the first goes to the second's
        place and size as it fades, the second comes on over it."""
        st = {}

        def start():
            self._show(na, ma)
            if id(self.E[nb]) not in self.up:
                self._show(nb, mb)
            st["a"], st["b"] = self._alpha(ma), self._alpha(mb)
            st["a0"] = st["a"].now
            st["b"].set(0.0)
            st["c0"], st["c1"] = ma.get_center().copy(), mb.get_center().copy()
            st["k"] = 1.0
            st["k1"] = max(mb.width / max(ma.width, 1e-3), 0.05)
            st["at"] = np.zeros(3)

        def step(a):
            d = (st["c1"] - st["c0"]) * a
            ma.shift(d - st["at"])
            st["at"] = d
            k = 1 + (st["k1"] - 1) * a
            ma.scale(k / st["k"])
            st["k"] = k
            st["a"].set(st["a0"] * (1 - a))
            st["b"].set(min(1.0, a * 1.4))

        def stop():
            if ma is self.E.get(na):
                self.remove(ma)
                self.up.discard(id(ma))
            ma.scale(1 / st["k"])
            ma.shift(-st["at"])
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

    def _fade_marks(self, name, to: float, t0, t1) -> None:
        state = {}

        def start():
            state["al"] = [(self._alpha(mk), self._alpha(mk).now) for mk in self.marks.get(name, [])]

        def step(a):
            for al, a0 in state["al"]:
                al.set(a0 + (to - a0) * a)
        self.tweens.append(Call(t0, t1, start, step, None))

    def _fade_to(self, m, to: float, t0, t1) -> None:
        al = self._alpha(m)
        state = {}

        def start():
            state["a0"] = al.now

        self.tweens.append(Call(t0, t1, start, lambda a: al.set(state["a0"] + (to - state["a0"]) * a)))

    def _scale(self, m, k, t0, t1) -> None:
        k = max(float(k), 0.01)                 # to nothing: as small as a speck (0 would undo nothing after it)
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
            if isinstance(m, (look.Num, look.Bar, look.Valued)):
                out.append(m)
            else:
                out += [p for p in m.get_family() if isinstance(p, (look.Num, look.Bar, look.Valued))]
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

    def _mark(self, name, m, kind, c, t0, t1, words: str = "", side: str | None = None) -> None:
        """A mark drawn on (or by) a thing, staying until the thing goes: ring, underline, highlight, strike, box,
        tick, cross, stamp "WORDS", callout "WORDS", bracket "WORDS"."""
        state = {}

        def start():
            core = getattr(m, "core", m)        # a piece's part marked at its heart (a step, a node), not its lines
            ul, dr = core.get_corner(UP + LEFT), core.get_corner(DOWN + RIGHT)
            w, h = dr[0] - ul[0], ul[1] - dr[1]
            c0 = (ul + dr) / 2
            zs = [x.z_index for x in m.get_family()] or [0]
            z = max(zs)
            how = "draw"
            hand = self.texture and kind in ("ring", "circle", "mark", "underline", "strike", "box", "tick", "cross",
                                             "highlight")
            key = f"{name}{kind}{t0:.2f}"
            if hand:                            # drawn by a pen, one stroke (feel.py)
                pen_w = look.STROKE * 1.15
                if kind in ("ring", "circle"):
                    mk = feel.scribble_ring(c0[0], c0[1], w, h, key)
                elif kind in ("mark", "underline"):
                    mk = feel.scribble_underline(ul[0], dr[0], dr[1] - 0.13, key)
                elif kind == "strike":
                    mk = feel.scribble_strike(ul[0], dr[0], c0[1], key)
                elif kind == "box":
                    mk = feel.scribble_box(ul[0] - 0.16, dr[1] - 0.14, dr[0] + 0.16, ul[1] + 0.14, key)
                    pen_w = look.STROKE * 0.85
                elif kind == "tick":
                    s = max(0.45, min(0.8, h * 0.6))
                    mk = feel.scribble_tick(dr[0] + 0.3, c0[1], s, key)
                    pen_w = look.STROKE * 1.3
                elif kind == "cross":
                    mk = feel.scribble_cross(c0[0], c0[1], max(0.5, min(w, h) * 0.75) / 2, key)
                    pen_w = look.STROKE * 1.4
                else:                           # highlight: a marker's band, swept on
                    if h > 0.9:
                        mk = feel.scribble_highlight(ul[0] - 0.15, dr[0] + 0.15, dr[1] - 0.12, ul[1] + 0.12, key)
                        mk.set_fill(c, opacity=0.3)
                    else:
                        mk = feel.scribble_highlight(ul[0] - 0.15, dr[0] + 0.15, dr[1] + 0.02, dr[1] + h * 0.66 + 0.06, key)
                        mk.set_fill(c, opacity=0.6)
                    mk.set_stroke(width=0)
                    z = min(zs) - 3
                    how = "sweep"
                if kind != "highlight":
                    mk.set_stroke(c, width=pen_w, opacity=0.95)
                    mk.set_fill(opacity=0)
            elif kind in ("ring", "circle"):
                mk = Ellipse(width=w + 0.6, height=h + 0.45, stroke_color=c, stroke_width=look.STROKE)
                mk.rotate(-0.08).move_to(c0)
            elif kind in ("mark", "underline"):
                mk = Line([ul[0], dr[1] - 0.12, 0], [dr[0], dr[1] - 0.12, 0], stroke_color=c, stroke_width=look.STROKE)
            elif kind == "strike":
                mk = Line([ul[0] - 0.1, c0[1], 0], [dr[0] + 0.1, c0[1], 0], stroke_color=c, stroke_width=look.STROKE)
            elif kind == "box":
                mk = RoundedRectangle(width=w + 0.4, height=h + 0.32, corner_radius=0.12, stroke_color=c,
                                      stroke_width=look.STROKE * 0.7, fill_opacity=0).move_to(c0)
            elif kind == "highlight":
                if h > 0.9:                             # not a line of words: a soft wash behind the whole of it
                    mk = Rectangle(width=w + 0.3, height=h + 0.25, fill_color=c, fill_opacity=0.3, stroke_width=0)
                    mk.move_to(c0)
                else:
                    mk = Rectangle(width=w + 0.3, height=h * 0.62 + 0.1, fill_color=c, fill_opacity=0.6, stroke_width=0)
                    mk.move_to([c0[0], dr[1] + h * 0.33, 0])
                z = min(zs) - 3                         # under the words it marks
                how = "sweep"
            elif kind == "tick":
                s = max(0.45, min(0.8, h * 0.6))
                o = np.array([dr[0] + 0.35, c0[1], 0])
                mk = VMobject(stroke_color=c, stroke_width=look.STROKE * 1.2)
                mk.set_points_as_corners([o + np.array([0, 0, 0]), o + np.array([s * 0.35, -s * 0.4, 0]),
                                          o + np.array([s, s * 0.5, 0])])
            elif kind == "cross":
                s = max(0.5, min(w, h) * 0.75) / 2
                mk = VGroup(Line(c0 + np.array([-s, s, 0]), c0 + np.array([s, -s, 0])),
                            Line(c0 + np.array([-s, -s, 0]), c0 + np.array([s, s, 0]))).set_stroke(c, width=look.STROKE * 1.4)
            elif kind == "stamp":
                t = look.text((words or "yes").upper(), 0.42, bold=True, color=c)
                frame = RoundedRectangle(width=t.width + 0.5, height=t.height + 0.4, corner_radius=0.08, stroke_color=c,
                                         stroke_width=look.STROKE * 0.8, fill_color=look.col("bg"), fill_opacity=0.35)
                mk = VGroup(frame, t.move_to(frame)).rotate(-0.21).move_to(c0)
                how = "stamp"
            elif kind == "callout":
                d = {"left": LEFT, "right": RIGHT, "up": UP, "down": DOWN}.get(side or "", UP + RIGHT)
                t = look.label(words or "", 0.15, "ink").set_stroke(look.col("bg"), width=6, background=True)
                far = c0 + np.array([d[0] * (w / 2 + 0.9), d[1] * (h / 2 + 0.7), 0])
                t.move_to(far + np.array([np.sign(d[0]) * t.width / 2, np.sign(d[1]) * 0.12, 0]))
                start_pt = c0 + np.array([d[0] * w / 2, d[1] * h / 2, 0]) * 0.85
                mk = VGroup(Dot(start_pt, radius=0.06, color=c), Line(start_pt, far, stroke_color=c, stroke_width=look.STROKE * 0.4), t)
            elif kind == "bracket":
                from manim import Brace
                mk = VGroup(Brace(m, RIGHT, buff=0.2, color=c, sharpness=1.2))
                if words:
                    mk.add(look.label(words, 0.15, "ink").next_to(mk[0], RIGHT, buff=0.15))
            else:
                raise ValueError(f"no mark {kind!r}")
            mk.set_z_index(z + 2)
            self.marks.setdefault(name, []).append(mk)
            self.follows.append([mk, core, core.get_center().copy(), None])
            self.add(mk)
            state["mk"] = mk
            if how == "draw":
                anim = Create(mk) if kind not in ("callout", "bracket", "box", "cross") else \
                    Create(mk, lag_ratio=0.3 if kind != "box" else 0.85)
                anim.begin()
                state["anim"] = anim
                if hand and kind not in ("cross", "box"):    # the pen's nib at the head of the stroke
                    nib = Dot(radius=0.05, color=c).set_z_index(z + 3)
                    state["nib"] = nib
                    self.add(nib)
            elif how == "sweep":
                state["w"], state["left"] = mk.width, mk.get_left().copy()
                mk.stretch_to_fit_width(0.01).move_to(state["left"] + RIGHT * 0.005)
            else:
                state["al"] = Alpha(mk)
                state["k"] = 1.0

        def step(a):
            mk = state["mk"]
            if "anim" in state:
                state["anim"].interpolate(a)
                if "nib" in state:
                    if len(mk.points):           # the head of the stroke drawn so far
                        state["nib"].move_to(mk.points[-1])
            elif "w" in state:
                mk.stretch_to_fit_width(max(0.01, state["w"] * a))
                mk.move_to(state["left"] + RIGHT * mk.width / 2)
            else:                               # a stamp: down hard from bigger
                k = 1.0 + 0.8 * (1 - a)
                mk.scale(k / state["k"])
                state["k"] = k
                state["al"].set(min(1.0, a * 2.2))

        def stop():
            if "anim" in state:
                state["anim"].interpolate(1)
                state["anim"].finish()
            if "nib" in state:
                self.remove(state["nib"])
        rate = {"stamp": rate_functions.ease_in_cubic}.get(kind, feel.pen if self.texture else rate_functions.ease_in_out_sine)
        self.tweens.append(Call(t0, t1, start, step, stop, rate))

    def _pan(self, m, k, d, t0, t1) -> None:
        state = {"k": 1.0, "d": np.zeros(3)}

        def step(a):
            kk = k ** a
            m.scale(kk / state["k"])
            m.shift(d * a - state["d"])
            state["k"], state["d"] = kk, d * a
        self.tweens.append(Call(t0, t1, None, step, None, rate_functions.linear))

    def _type(self, name, m, t0, t1) -> None:
        """Words coming on letter by letter."""
        glyphs = [x for x in m.family_members_with_points()]
        state = {}

        def start():
            self._show(name, m)
            self._alpha(m).set(1.0)
            state["al"] = [Alpha(g) for g in glyphs]
            for al in state["al"]:
                al.set(0.0)

        def step(a):
            n = int(round(a * len(glyphs)))
            for i, al in enumerate(state["al"]):
                al.set(1.0 if i < n else 0.0)
        self.tweens.append(Call(t0, t1, start, step, None, rate_functions.linear))

    def _fill(self, name, m, to, c, t0, t1) -> None:
        """A shape filling from the bottom, as with water: to a share of its height."""
        state = {}

        def start():
            ul, dr = m.get_corner(UP + LEFT), m.get_corner(DOWN + RIGHT)
            fills = self.fills.setdefault(name, {})
            if "mk" not in fills:
                mk = Rectangle(width=(dr[0] - ul[0]) * 0.86, height=0.01, fill_color=c, fill_opacity=0.6, stroke_width=0)
                mk.move_to([(ul[0] + dr[0]) / 2, dr[1] + 0.005 + (ul[1] - dr[1]) * 0.03, 0])
                mk.set_z_index(max(x.z_index for x in m.get_family()) + 1)
                fills.update(mk=mk, h=0.0, full=(ul[1] - dr[1]) * 0.94, base=dr[1] + (ul[1] - dr[1]) * 0.03)
                self.marks.setdefault(name, []).append(mk)
                self.follows.append([mk, m, m.get_center().copy(), fills])
                self.add(mk)
            state["h0"] = fills["h"]
            state["f"] = fills

        def step(a):
            f = state["f"]
            h = state["h0"] + (to - state["h0"]) * a
            f["mk"].stretch_to_fit_height(max(0.01, f["full"] * h))
            f["mk"].move_to([f["mk"].get_center()[0], f["base"] + f["mk"].height / 2, 0])
            f["h"] = h
        self.tweens.append(Call(t0, t1, start, step, None, rate_functions.ease_in_out_sine))

    def _connect(self, name, a, b, words, c, t0, t1) -> None:
        """An arrow drawn from one thing to another as the voice joins them (it goes when the first goes)."""
        import kit
        state = {}

        def start():
            p0, p1 = kit.edge_point(a, b.get_center()), kit.edge_point(b, a.get_center())
            mk = kit.tipped([p0, p1], c, smooth=False)
            if words:
                t = kit.halo(look.label(words, 0.13, "ink"))
                d = p1 - p0
                nrm = np.array([-d[1], d[0], 0.0]) / (np.linalg.norm(d) or 1)
                mk.add(t.move_to((p0 + p1) / 2 + nrm * 0.25 * (1 if nrm[1] >= 0 else -1)))
            mk.set_z_index(max(x.z_index for x in a.get_family()) + 1)
            self.marks.setdefault(name, []).append(mk)
            self.follows.append([mk, a, a.get_center().copy(), None])
            self.add(mk)
            anim = Create(mk, lag_ratio=0.2)
            anim.begin()
            state["anim"] = anim

        def stop():
            state["anim"].interpolate(1)
            state["anim"].finish()
        self.tweens.append(Call(t0, t1, start, lambda x: state["anim"].interpolate(x), stop, rate_functions.ease_in_out_sine))

    def _follow(self, m, zoom, t0, t1) -> None:
        """The camera keeps a moving thing in the middle (`follow ship`), easing after it."""
        f = self.camera.frame

        def step(a):
            f.move_to(f.get_center() + (m.get_center() - f.get_center()) * 0.12)
            if zoom:
                w = S.SCREEN_W / float(zoom)
                f.set_width(f.width + (w - f.width) * 0.06)
        tw = Call(t0, t1, None, step, None, rate_functions.linear)
        tw.camera = True
        self.tweens.append(tw)

    def _tip(self, m, to, t0, t1) -> None:
        state = {}

        def start():
            state["a0"] = m.tilt
        self.tweens.append(Call(t0, t1, start, lambda a: m.set_tilt(state["a0"] + (to - state["a0"]) * a), None,
                                rate_functions.ease_out_back))

    def _weather(self) -> None:
        """Snow or rain keeps falling while it is up: each flake where its start, speed and the time put it (the
        same in every chunk)."""
        for name, e in self.SCORE.ents.items():
            m = self.E.get(name)
            if e.kind != "weather" or m is None:
                continue
            c0 = m.get_center().copy()
            w, h = m.size

            def step(a, m=m, c0=c0, w=w, h=h):
                f = self.camera.frame
                # Still while it is not up or the camera is elsewhere: nothing to draw, nothing to record.
                if id(m) not in self.up or self._alpha(m).now < 0.01 or \
                        np.linalg.norm(f.get_center() - c0) > f.width * 0.9:
                    return
                t = self.clock
                for p, (x, y, speed, ph) in zip(m.submobjects, m.seeds):
                    yy = (y + h / 2 - speed * t) % h - h / 2
                    xx = x + (0.25 * math.sin(t * 0.9 + ph) if m.how == "snow" else -0.2 * speed * t % 0.01)
                    p.move_to(c0 + np.array([xx, yy, 0.0]))
            self.tweens.append(Call(0.0, self.SCORE.end + TAIL, None, step, None, rate_functions.linear))

    def _era(self, name, m, year: int, t0, t1) -> None:
        import geo
        state = {}

        def start():
            new = VGroup()
            for _, g in geo.states(year, m.bounds):
                new.add(*m.shape_mob(g, fill=None, stroke=look.col("grey") if "grey" in look.L else look.col("soft"),
                                     width=1.5, screen=True))
            new.set_z_index(max(x.z_index for x in m.get_family()) + 1)
            self.marks.setdefault(name, []).append(new)
            self.follows.append([new, m, m.get_center().copy(), None])
            self.add(new)
            state["new"], state["old"] = Alpha(new), self._alpha(m[2])
            state["o0"] = state["old"].now
            state["new"].set(0.0)

        def step(a):
            state["new"].set(a)
            state["old"].set(state["o0"] * (1 - a))
        self.tweens.append(Call(t0, t1, start, step, None, rate_functions.smooth))

    def _glow(self, name, m, c, t0, t1) -> None:
        """A soft light behind a thing (rings of the colour, fainter outward); it stays and follows the thing."""
        state = {}

        def start():
            core = getattr(m, "core", m)
            if max(core.width, core.height) > 3.2:
                # a big thing (a map, a row of cards): a soft glow round its edge, not a disc the size of the screen
                halo = VGroup(*(RoundedRectangle(width=core.width + 0.12 * k, height=core.height + 0.12 * k,
                                                 corner_radius=0.15 + 0.06 * k, fill_color=c, fill_opacity=0.07,
                                                 stroke_width=0) for k in range(5))).move_to(core)
            else:
                r = max(core.width, core.height) / 2
                halo = VGroup(*(Circle(radius=r * (1.0 + 0.1 * k), fill_color=c, fill_opacity=0.09, stroke_width=0)
                                for k in range(6))).move_to(core)
            halo.set_z_index(min(x.z_index for x in m.get_family()) - 2)
            self.marks.setdefault(name, []).append(halo)
            self.follows.append([halo, core, core.get_center().copy(), None])
            self.add(halo)
            state["al"] = Alpha(halo)
            state["al"].set(0.0)
        self.tweens.append(Call(t0, t1, start, lambda a: state["al"].set(a), None, rate_functions.smooth))

    def _sheet(self, how: str, t0, t1) -> None:
        """A sheet of paper drawn across the screen while the camera moves under it (a page turned; `tear`: its edges
        torn), so one place gives way to the next."""
        f = self.camera.frame
        rng = np.random.default_rng(int(t0 * 1000) % 9973)
        h = 1.0
        if how == "tear":
            left = [[-0.55 + rng.uniform(-0.03, 0.03), y, 0] for y in np.linspace(0.6, -0.6, 22)]
            right = [[0.55 + rng.uniform(-0.03, 0.03), y, 0] for y in np.linspace(-0.6, 0.6, 22)]
            sheet = Polygon(*left, *right, fill_color=look.col("card"), fill_opacity=1, stroke_color=look.col("sand"),
                            stroke_width=2)
        else:
            sheet = VGroup(Rectangle(width=1.1, height=1.2, fill_color=look.col("card"), fill_opacity=1, stroke_width=0),
                           Rectangle(width=0.03, height=1.2, fill_color=look.L["ink"], fill_opacity=0.12,
                                     stroke_width=0).shift(LEFT * 0.565))
        sheet.set_z_index(950)
        state = {"w": 1.0}

        def start():
            self.add(sheet)

        def step(a):
            w = f.width
            sheet.scale(w / state["w"])
            state["w"] = w
            sheet.move_to(f.get_center() + RIGHT * w * 1.15 * (1 - 2 * a))

        def stop():
            self.remove(sheet)
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.linear))

    def _spotlight(self, target: str, dim: float, t0, t1) -> None:
        """Everything else up in the target's shot veiled (`lift` brings a thing back)."""
        names = {n for n, _ in self._targets(target)}
        shot = self.SCORE.ents[next(iter(names))].shot
        state = {}

        def start():
            others = [n for n, e in self.SCORE.ents.items() if e.shot == shot and n not in names and n in self.E
                      and id(self.E[n]) in self.up and e.mods.get("on") not in names]   # its labels stay lit
            mobs = [self.E[n] for n in others] + [mk for n in others for mk in self.marks.get(n, [])]
            state["al"] = [(self._alpha(m), self._alpha(m).now) for m in mobs]

        def step(a):
            for al, a0 in state["al"]:
                al.set(a0 + (min(a0, dim) - a0) * a)
        self.tweens.append(Call(t0, t1, start, step, None))

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

    # ------------------------------------------------------------ people -----------------------------------------------
    def _person(self, act: S.Act, t0, t1) -> None:
        """A person's poses over time: each verb sets only its own part of the pose (a walk its legs, a talk its
        mouth), so a person can talk while walking."""
        import people as P
        (name, m), = self._targets(act.target)[:1]
        if not isinstance(m, P.Person):
            raise ValueError(f"{act.verb} is a person's (`ent NAME person`): {name} is a {self._kind(name)}")
        v = act.verb
        legs = ("fl1", "fl2", "bl1", "bl2", "bob", "drop", "lean")
        arms = ("fa1", "fa2", "ba1", "ba2")
        dur = max(t1 - t0, 0.05)
        st = {}
        blend = min(0.35, dur / 2)
        back = v in ("wave", "talk", "cheer", "shrug", "bow", "jump", "nod")   # these end where they began

        def eased(tt: float) -> float:
            k = min(1.0, tt / blend) if blend > 0 else 1.0
            if back:
                k = min(k, max(0.0, (dur - tt) / blend))
            return k * k * (3 - 2 * k)

        def pose_to(target: dict, keys, tt: float) -> None:
            k = eased(tt)
            p = dict(m.pose)
            for key in keys:
                p[key] = st["p0"][key] + (target[key] - st["p0"][key]) * k
            m.set_pose(p)

        if v in ("walk", "run"):
            def start():
                st["p0"] = dict(m.pose)
                st["f0"] = m.feet().copy()
                st["f1"] = self._dest(name, m, act)
                st["at"] = st["f0"].copy()
                m.pose["face"] = 1.0 if st["f1"][0] >= st["f0"][0] else -1.0

            def step(a):
                tt = a * dur
                pos = st["f0"] + (st["f1"] - st["f0"]) * rate_functions.ease_in_out_sine(a)
                m.shift(pos - m.feet())
                gone = float(np.linalg.norm(pos - st["f0"]))
                phase = gone / max((0.42 if v == "run" else 0.3) * m.unit(), 1e-3) * math.pi / 2
                ramp = min(1.0, tt / 0.25, max(0.0, (dur - tt) / 0.25))
                target = P.mix(m.rest, P.walk_pose(phase, v == "run"), ramp)
                keys = legs + (() if getattr(m, "carrying", False) else arms)
                p = dict(m.pose)
                for key in keys:
                    p[key] = target[key]
                p["drop"] = 0.0
                m.set_pose(p)
            self.tweens.append(Call(t0, t1, start, step, None, rate_functions.linear))
            return
        if v == "point":
            ref = act.args[act.args.index("at") + 1] if "at" in act.args else (act.args[0] if act.args else "")

            def start():
                st["p0"] = dict(m.pose)
                goal = self._locate(ref, self.SCORE.ents[name].shot)
                sh = m.w((0.0, P.HIP + P.TORSO))
                face = 1.0 if goal[0] >= sh[0] else -1.0
                d = goal - sh
                ang = math.atan2(face * d[0], -d[1])
                st["target"] = {**st["p0"], "fa1": ang, "fa2": ang, "face": face}

            def step(a):
                pose_to(st["target"], arms[:2] + ("face",), a * dur)
            self.tweens.append(Call(t0, max(t1, t0 + 0.5), start, step, None, rate_functions.linear))
            return

        def start():
            st["p0"] = dict(m.pose)
            if v == "carry":
                m.carrying = True

        if v == "wave":
            def step(a):
                tt = a * dur
                target = {**st["p0"], "fa1": 2.55, "fa2": 2.55 + 0.5 * math.sin(tt * 9.0)}
                pose_to(target, arms[:2], tt)
        elif v == "talk":
            seed = feel.seed(name) % 7

            def step(a):
                tt = a * dur
                o = 0.5 + 0.5 * math.sin(tt * 13.0 + seed) * math.sin(tt * 4.1 + seed * 0.7)
                target = {**st["p0"], "mouth": abs(o)}
                pose_to(target, ("mouth",), tt)
            words = next((x for x in act.args if x not in look.L), "")
            if words:
                self._talk_bubble(name, m, words, t0, t1)
        elif v in ("sit", "stand"):
            def step(a):
                if v == "stand" and getattr(m, "fallen", 0.0):        # up again from a faint
                    ang = m.fallen * (1 - min(1.0, a * 1.5))
                    m.rotate(ang - m.fallen, about_point=m.feet())
                    m.fallen = ang
                target = P.sit_pose(m.seat is not None) if v == "sit" else dict(m.rest)
                target["face"], target["mouth"] = st["p0"]["face"], st["p0"]["mouth"]
                if v == "stand" and getattr(m, "carrying", False):
                    target.update({k: P.carry_pose()[k] for k in arms})
                pose_to(target, legs + arms, a * dur)
        elif v == "emote":
            # a face: `emote P happy|laugh|calm|sad|angry|surprised|worried|scared|think|proud` (held)
            mood = P.MOODS.get((act.args[0] if act.args else "happy").lower(), P.MOODS["happy"])

            def step(a):
                pose_to({**st["p0"], **mood}, P.FACE_KEYS, a * dur)
        elif v in P.GESTURES:
            gesture = P.GESTURES[v]
            back = v != "think" and back

            def step(a):
                tt = a * dur
                target = {**st["p0"], **gesture}
                if v == "cheer":                # a little bounce while the arms are up
                    target["bob"] = 0.03 * abs(math.sin(tt * 7.0))
                    keys = tuple(gesture) + ("bob",)
                else:
                    keys = tuple(gesture)
                pose_to(target, keys, tt)
        elif v == "jump":
            def step(a):
                # down first (knees bent, arms back), then up and back down, landing soft
                p = dict(m.pose)
                crouch = math.sin(math.pi * min(1.0, a / 0.3)) if a < 0.3 else 0.0
                hop = math.sin(math.pi * (a - 0.3) / 0.7) if a >= 0.3 else 0.0
                p["drop"] = 0.05 * crouch
                p["bob"] = 0.24 * hop
                for key, low, high in (("fl1", 0.55, 0.5), ("fl2", -0.45, -0.3), ("bl1", 0.45, 0.3), ("bl2", -0.55, -0.4),
                                       ("fa1", -0.5, 2.3), ("fa2", -0.3, 2.5), ("ba1", -0.6, 2.1), ("ba2", -0.4, 2.4)):
                    p[key] = st["p0"][key] + (low - st["p0"][key]) * crouch + (high - st["p0"][key]) * hop
                p["smile"] = st["p0"]["smile"] + (1.0 - st["p0"]["smile"]) * hop
                m.set_pose(p)
        elif v == "nod":
            def step(a):
                p = dict(m.pose)
                p["nod"] = 0.22 * math.sin(a * math.pi * 4) * (1 - a)
                m.set_pose(p)
        elif v in ("dance", "clap", "facepalm", "laugh", "cry", "shiver", "kick"):
            moods = {"dance": "joy", "clap": "happy", "facepalm": "annoyed", "laugh": "laugh", "cry": "crying",
                     "shiver": "scared", "kick": "angry"}
            face = P.MOODS[moods[v]]
            back = v not in ()

            def step(a):
                tt = a * dur
                q = dict(st["p0"])
                q.update(face)
                if v == "dance":                # arms up and swinging, legs stepping, a bounce on the beat
                    s1 = math.sin(tt * 7.0)
                    q.update(fa1=2.3 + 0.5 * s1, fa2=2.6 + 0.4 * s1, ba1=2.3 - 0.5 * s1, ba2=2.6 - 0.4 * s1,
                             fl1=0.35 * s1, fl2=0.35 * s1 - 0.3 * max(0.0, s1), bl1=-0.35 * s1,
                             bl2=-0.35 * s1 - 0.3 * max(0.0, -s1), bob=0.035 * abs(math.sin(tt * 7.0)),
                             lean=0.12 * math.sin(tt * 3.5))
                    keys = ("fa1", "fa2", "ba1", "ba2", "fl1", "fl2", "bl1", "bl2", "bob", "lean") + P.FACE_KEYS
                elif v == "clap":               # hands meeting in front, again and again
                    s1 = math.sin(tt * 13.0)
                    q.update(fa1=0.95, ba1=1.15, fa2=1.55 + 0.45 * s1, ba2=1.75 - 0.45 * s1)
                    keys = ("fa1", "fa2", "ba1", "ba2") + P.FACE_KEYS
                elif v == "facepalm":           # a hand to the face, the head bowed
                    q.update(fa1=0.25, fa2=2.95, nod=0.28, lids=0.7)
                    keys = ("fa1", "fa2", "nod") + P.FACE_KEYS
                elif v == "laugh":              # bent with it, shaking
                    q.update(lean=0.18 + 0.05 * math.sin(tt * 17.0), bob=0.012 * abs(math.sin(tt * 17.0)),
                             fa1=0.9, fa2=2.2)
                    keys = ("lean", "bob", "fa1", "fa2") + P.FACE_KEYS
                elif v == "cry":                # shoulders shaking, head down, a hand to the eyes
                    q.update(bob=0.008 * math.sin(tt * 13.0), nod=0.2, fa1=0.3, fa2=2.7)
                    keys = ("bob", "nod", "fa1", "fa2") + P.FACE_KEYS
                elif v == "shiver":             # trembling all over, arms held in
                    q.update(lean=0.035 * math.sin(tt * 45.0), fa1=0.6, fa2=2.3, ba1=0.5, ba2=2.2,
                             fl1=0.04 * math.sin(tt * 45.0))
                    keys = ("lean", "fa1", "fa2", "ba1", "ba2", "fl1") + P.FACE_KEYS
                else:                           # kick: the front leg swung out and back
                    sw = math.sin(math.pi * min(1.0, tt / max(dur, 0.1)))
                    q.update(fl1=-0.3 + 1.7 * sw, fl2=-0.2 + 1.4 * sw, lean=-0.15 * sw, fa1=-0.4 * sw, ba1=0.6 * sw)
                    keys = ("fl1", "fl2", "lean", "fa1", "ba1") + P.FACE_KEYS
                pose_to(q, keys, tt)
        elif v == "look":
            # the face and eyes to a thing (`look P at T`), and held
            ref = act.args[act.args.index("at") + 1] if "at" in act.args else (act.args[0] if act.args else "")

            def step(a):
                if "goal" not in st:
                    st["goal"] = self._locate(ref, self.SCORE.ents[name].shot)
                goal = st["goal"]
                c = m.head.get_center()
                face = 1.0 if goal[0] >= c[0] else -1.0
                up = max(-1.0, min(1.0, (goal[1] - c[1]) / 2.0))
                pose_to({**st["p0"], "face": face, "side": 1.0, "gaze": up}, ("face", "side", "gaze"), a * dur)
        elif v == "faint":
            # falls flat (back to its feet with `stand`): the whole figure turned about its feet
            def step(a):
                p = dict(m.pose)
                p.update({k_: st["p0"][k_] + (P.MOODS["dazed"][k_] - st["p0"][k_]) * min(1.0, a * 2) for k_ in P.FACE_KEYS})
                m.set_pose(p)
                ang = -m.facing() * (math.pi / 2) * rate_functions.ease_in_quad(a)
                d_ = ang - getattr(m, "fallen", 0.0)
                m.rotate(d_, about_point=m.feet())
                m.fallen = ang
        elif v == "hug":
            # two figures meet and hold each other: P walks to the other, both arms round
            other = act.args[0] if act.args else ""
            (on, om), = self._targets(other)[:1]

            def step(a):
                if "f0" not in st:
                    st["f0"] = m.feet().copy()
                    side = 1.0 if om.feet()[0] >= st["f0"][0] else -1.0
                    # close enough to hold: their bodies just touching (a country is wider than a person)
                    gap = max(0.32 * m.unit(), 0.42 * (getattr(m, "body_w", 0.2) * m.unit() +
                                                       getattr(om, "body_w", 0.2) * getattr(om, "unit", m.unit)()))
                    st["f1"] = om.feet() - np.array([side * gap, 0, 0])
                    m.pose["face"] = side
                    if isinstance(om, P.Person):
                        om.pose["face"] = -side
                        om.set_pose(om.pose)
                walk_a = min(1.0, a / 0.5)
                m.shift(st["f0"] + (st["f1"] - st["f0"]) * rate_functions.ease_in_out_sine(walk_a) - m.feet())
                arms = max(0.0, (a - 0.4) / 0.6)
                for who in (m, om):
                    if not isinstance(who, P.Person):
                        continue
                    p = dict(who.pose)
                    p.update(fa1=p["fa1"] + (1.25 - p["fa1"]) * arms, fa2=p["fa2"] + (2.0 - p["fa2"]) * arms,
                             ba1=p["ba1"] + (1.25 - p["ba1"]) * arms, ba2=p["ba2"] + (2.0 - p["ba2"]) * arms,
                             smile=p["smile"] + (0.95 - p["smile"]) * arms, joy=p["joy"] + (0.9 - p["joy"]) * arms)
                    who.set_pose(p)
        elif v == "turn":
            def step(a):
                face = -1.0 if (act.args and act.args[0] == "left") else 1.0 if act.args else -st["p0"]["face"]
                pose_to({**st["p0"], "face": face}, ("face",), a * dur)
        elif v == "carry":
            thing = act.args[0] if act.args else ""
            (tn, tm), = self._targets(thing)[:1]

            def step(a):
                pose_to(P.carry_pose(), arms, a * dur)
            self._carried(m, tn, tm, t0, t1)
        else:
            raise ValueError(f"no verb {v!r}")
        self.tweens.append(Call(t0, t1, start, step, None, rate_functions.linear))

    def _blinks(self) -> None:
        """Every person blinks now and then (each on its own rhythm), while it is up."""
        import people as P
        for name, m in self.E.items():
            if not isinstance(m, P.Person):
                continue
            seed = feel.seed(name)
            period, shift = 2.8 + (seed % 19) / 10, (seed % 7) * 0.41

            def step(_a, m=m, period=period, shift=shift):
                if id(m) not in self.up:
                    return
                ph = (self.clock + shift) % period
                b = max(0.0, 1 - abs(ph - 0.07) / 0.07) if ph < 0.14 else 0.0
                # never quite still: a slow breath (a few frames' steps, so a held figure is mostly kept as it was)
                br = round(0.006 * math.sin((self.clock + shift) * 2 * math.pi / 3.6), 3)
                if abs(b - m.pose.get("blink", 0.0)) > 1e-3 or abs(br - m.pose.get("breath", 0.0)) > 1e-4:
                    p = dict(m.pose)
                    p["blink"], p["breath"] = b, br
                    m.set_pose(p)
            self.tweens.append(Call(0.0, self.SCORE.end + TAIL, None, step, None, rate_functions.linear))

    def _carried(self, m, tn, tm, t0, t1) -> None:
        """A thing taken into a person's hands: it goes there as the arms come up, then goes where the hands go."""
        st = {}

        def start():
            if id(self.E[tn]) not in self.up:
                self._show(tn, tm)
                self._alpha(tm).set(1.0)
            st["at"] = tm.get_center().copy()

        def step(a):
            goal = m.hand.get_center() + UP * tm.height * 0.4
            p = st["at"] + (goal - st["at"]) * a
            tm.shift(p - tm.get_center())

        def stop():
            self.follows.append([tm, m.hand, m.hand.get_center().copy(), None])
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.ease_in_out_sine))

    def _talk_bubble(self, name, m, words, t0, t1) -> None:
        import kit
        st = {}

        def start():
            b = kit.bubble(m.head, words, {"size": 0.2, "w": 2.6})
            b.set_z_index(max(x.z_index for x in m.get_family()) + 2)
            st["b"], st["al"] = b, Alpha(b)
            st["al"].set(0.0)
            self.follows.append([b, m.head, m.head.get_center().copy(), None])
            self.add(b)

        def step(a):
            tt = a * (t1 - t0)
            st["al"].set(min(1.0, tt / 0.2, max(0.0, (t1 - t0 - tt) / 0.25)))

        def stop():
            self.remove(st["b"])
        self.tweens.append(Call(t0, max(t1, t0 + 0.8), start, step, stop, rate_functions.linear))

    # ------------------------------------------------------------ carried over -----------------------------------------
    def _bring(self, name, m, act: S.Act, t0, t1) -> None:
        """A thing that travels on the screen with the camera into another shot, and stays there (`bring T to SHOT
        [X,Y]`, best at the time of the camera move)."""
        shot = act.args[act.args.index("to") + 1] if "to" in act.args else (act.args[0] if act.args else "")
        if shot not in self.SCORE.shots:
            raise ValueError(f"bring needs a shot to go to: `bring {name} to SHOT [X,Y]`")
        xy = next((a for a in act.args if re.match(r"^-?[\d.]+,-?[\d.]+$", a)), None)
        f = self.camera.frame
        st = {}

        def start():
            s = self.SCORE.shots[shot]
            w1 = S.SCREEN_W / s.zoom
            st["rel0"] = (m.get_center() - f.get_center()) / f.width
            dest = np.array([s.x, s.y, 0.0]) + (np.array([*(float(v) for v in xy.split(",")), 0.0]) if xy else st["rel0"] * w1)
            st["rel1"] = (dest - np.array([s.x, s.y, 0.0])) / w1
            st["fw"] = f.width
            self.still.add(name)                # no parallax while it rides on the screen

        def step(a):
            m.scale(f.width / st["fw"])
            st["fw"] = f.width
            rel = st["rel0"] + (st["rel1"] - st["rel0"]) * a
            m.shift(f.get_center() + rel * f.width - m.get_center())

        def stop():
            self.SCORE.ents[name].shot = shot
            self.home[name] = self._origin(shot)
            self.still.discard(name)
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.ease_in_out_sine))

    # ------------------------------------------------------------ depth ------------------------------------------------
    def _depths(self) -> None:
        """Each thing's depth on the paper (feel.DEPTH): what stands on another piece or against it shares its depth."""
        sc = self.SCORE
        self.home: dict[str, np.ndarray] = {}
        self.depth: dict[str, float] = {}
        self.offset: dict[str, np.ndarray] = {}
        self.still: set[str] = set()

        def of(n: str, seen=()) -> float:
            e = sc.ents.get(n)
            if e is None or n in seen:
                return 1.0
            for key in ("on", "map", *REL, "at"):
                ref = e.mods.get(key)
                if isinstance(ref, str):
                    base = ref.split(".", 1)[0]
                    if base in sc.ents and base != n:
                        return of(base, (*seen, n))
            return feel.depth(e.kind)
        for n, e in sc.ents.items():
            if n in self.E and e.shot in sc.shots:
                k = of(n)
                if abs(k - 1.0) > 1e-3:
                    self.depth[n] = k
                    self.home[n] = self._origin(e.shot)
                    self.offset[n] = np.zeros(3)

    def _parallax(self) -> None:
        f = self.camera.frame
        c, fw = f.get_center(), f.width
        zoomed_out = min(1.0, max(0.0, (1.6 * S.SCREEN_W - fw) / (0.4 * S.SCREEN_W)))
        for n, k in self.depth.items():
            m = self.E.get(n)
            if m is None or n in self.still:
                continue
            d = c - self.home[n]
            w = feel.parallax_weight(float(np.linalg.norm(d[:2])), S.SCREEN_W) * zoomed_out
            off = d * (1.0 - k) * w
            off[2] = 0.0
            last = self.offset[n]
            if np.abs(off - last).max() > 1e-5:
                m.shift(off - last)             # (its marks follow it: self.follows)
                self.offset[n] = off

    # ------------------------------------------------------------ on the screen ----------------------------------------
    def _hud_add(self, m, x: float, y: float) -> None:
        """A thing kept on the screen (x, y in screen widths and heights from its centre), whatever the camera does."""
        m.move_to([x * S.SCREEN_W, y * S.SCREEN_H, 0])
        self.hud.append([m, 1.0, np.zeros(3)])

    def _place_hud(self) -> None:
        f = self.camera.frame
        k, c = f.width / S.SCREEN_W, f.get_center().copy()
        c[2] = 0.0
        for rec in self.hud:
            m, k0, c0 = rec
            if abs(k - k0) < 1e-9 and np.allclose(c, c0, atol=1e-9):
                continue
            m.shift(-c0)
            m.scale(k / k0, about_point=np.zeros(3))
            m.shift(c)
            for x in m.family_members_with_points():     # a line's width is in world units: kept on the screen too
                if isinstance(x, VMobject) and x.get_stroke_width() > 0:
                    x.set_stroke(width=x.get_stroke_width() * k / k0, family=False)
            rec[1], rec[2] = k, c
        for hook in self.hud_hooks:             # what is drawn on the screen afresh each frame (the chapter bar's fill)
            hook(k, c)

    def _overlay(self) -> None:
        """Paper grain and a soft vignette over the frame, drifting a little."""
        if not self.texture:
            return
        img = ImageMobject(feel.overlay_rgba(ink=look.L["ink"]))
        img.stretch_to_fit_width(S.SCREEN_W * 1.06).stretch_to_fit_height(S.SCREEN_H * 1.06)
        img.set_z_index(990)
        self._hud_add(img, 0.0, 0.0)
        self.add(img)
        st = {"at": np.zeros(3)}

        def step(a):
            t = self.clock
            k = self.camera.frame.width / S.SCREEN_W
            off = np.array([0.1 * math.sin(t * 0.23), 0.07 * math.cos(t * 0.17), 0.0]) * k
            img.shift(off - st["at"] * k / st.get("k", k))
            st["at"], st["k"] = off, k
        self.tweens.append(Call(0.0, self.SCORE.end + TAIL, None, step, None, rate_functions.linear))

    def _boil(self) -> None:
        """Drawn outlines tremble a little, a few times a second (undone before the next frame's actions)."""
        n = int(self.clock * feel.BOIL_HZ)
        out = []
        for root in self.mobjects:
            if root is getattr(self, "paper", None):
                continue
            for x in root.family_members_with_points():
                if not isinstance(x, VMobject) or getattr(x, "z_index", 0) >= 900 or not feel.boils(x):
                    continue
                i = self.boil_ids.setdefault(id(x), len(self.boil_ids))
                dx, dy, turn = feel.boil(i, n)
                P = x.points
                lo, hi = P[:, :2].min(axis=0), P[:, :2].max(axis=0)
                cx, cy = (lo + hi) / 2
                r = max(0.2, float(np.linalg.norm(hi - lo)) / 2)
                ang = max(-0.03, min(0.03, turn * feel.BOIL_TURN / r))
                ca, sa = math.cos(ang), math.sin(ang)
                X, Y = P[:, 0] - cx, P[:, 1] - cy
                P[:, 0], P[:, 1] = cx + ca * X - sa * Y + dx, cy + sa * X + ca * Y + dy
                out.append((x, dx, dy, ang, cx, cy))
        self.boiled = out

    def _unboil(self) -> None:
        for x, dx, dy, ang, cx, cy in self.boiled:
            P = x.points
            if not len(P):
                continue
            ca, sa = math.cos(-ang), math.sin(-ang)
            X, Y = P[:, 0] - dx - cx, P[:, 1] - dy - cy
            P[:, 0], P[:, 1] = cx + ca * X - sa * Y, cy + sa * X + ca * Y
        self.boiled = []

    # ------------------------------------------------------------ words said -------------------------------------------
    def _numbers_said(self) -> None:
        """A number that comes on as the voice says it counts up to itself while it is said (unless the score
        counts it): from the word's start to its end, when a word nearby holds its digits."""
        sc = self.SCORE
        words = self.WORDS.get("words", []) if isinstance(self.WORDS, dict) else []
        counted = {re.sub(r"\[.*", "", x) for a in sc.acts if a.verb in ("count", "grow") for x in a.target.split(",")}
        for a in sc.acts:
            if a.verb != "in":
                continue
            for x in a.target.split(","):
                n = re.sub(r"\[.*", "", x.strip())
                e, m = sc.ents.get(n), self.E.get(n)
                if e is None or e.kind != "num" or n in counted or not isinstance(m, look.Num):
                    continue
                v = float(m.value)
                if abs(v) < 10 or (1000 <= v <= 2100 and v.is_integer() and not m.prefix and not m.suffix):
                    continue                    # a small number or a year stays as it is
                digits = re.sub(r"\D", "", f"{v:.0f}")
                said = next((w for w in words if a.t0 - 1.0 <= float(w["start"]) <= a.t0 + 3.0
                             and re.sub(r"\D", "", str(w.get("w", ""))) == digits), None)
                t0 = max(0.0, a.t0 - LEAD)
                t1 = max(float(said["end"]), t0 + 0.6) if said else t0 + 1.0

                def start(m=m):
                    m.set_value(0.0)

                def step(k, m=m, v=v):
                    m.set_value(v * k)
                self.tweens.append(Call(t0, t1, start, step, None, rate_functions.ease_out_cubic))
                counted.add(n)

    def _speak(self, name, m, act: S.Act, t0, t1) -> None:
        """A phrase's words come on one by one as the voice says them (over the action's words)."""
        parts = list(m.submobjects) or [m]
        words = self.WORDS.get("words", []) if isinstance(self.WORDS, dict) else []
        said = [w for w in words if t0 - 0.05 <= float(w["start"]) <= t1 + 0.05]
        if len(said) >= len(parts):
            times = [float(w["start"]) - 0.08 for w in said[:len(parts)]]
        else:
            times = [t0 + (t1 - t0) * i / max(1, len(parts)) for i in range(len(parts))]
        self.tweens.append(Call(t0, t0 + 0.01, lambda: (self._show(name, m), self._alpha(m).set(1.0),
                                                        [self._alpha(p).set(0.0) for p in parts]), None, None))
        for p, t in zip(parts, times):
            self._rise_word(p, max(t0, t), max(t0, t) + 0.28)

    def _rise_word(self, p, t0, t1) -> None:
        al = self._alpha(p)
        st = {"d": DOWN * 0.12}

        def start():
            p.shift(st["d"])

        def step(a):
            al.set(a)
            d = DOWN * 0.12 * (1 - a)
            p.shift(d - st["d"])
            st["d"] = d
        self.tweens.append(Call(t0, t1, start, step, None, rate_functions.ease_out_cubic))

    def _captions(self) -> None:
        """The narration's words along the bottom of the screen, a few at a time, the word being said lit."""
        sc = self.SCORE
        on = sc.captions if sc.captions is not None else os.environ.get("V3_CAPTIONS", "0").strip() == "1"
        words = self.WORDS.get("words", []) if isinstance(self.WORDS, dict) else []
        if not on or not words:
            return
        chunks, cur = [], []
        for i, w in enumerate(words):
            cur.append(w)
            nxt = words[i + 1] if i + 1 < len(words) else None
            end = re.search(r"[.,;:?!]$", str(w["w"])) or nxt is None or float(nxt["start"]) - float(w["end"]) > 0.45
            if len(cur) >= 7 or (end and len(cur) >= 3) or nxt is None:
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        st = {"k": -1, "m": None}

        def make(chunk):
            g = look.phrase(" ".join(str(w["w"]) for w in chunk), 0.26, 12.0, "ink")
            pill = RoundedRectangle(width=g.width + 0.6, height=g.height + 0.34, corner_radius=0.2,
                                    fill_color=look.col("card"), fill_opacity=0.88, stroke_width=0).move_to(g)
            box = VGroup(pill, g).set_z_index(HUD_Z)
            return box

        def step(_a):
            t = self.clock
            k = next((i for i, c in enumerate(chunks) if float(c[0]["start"]) - 0.15 <= t <= float(c[-1]["end"]) + 0.3), -1)
            if k != st["k"]:
                if st["m"] is not None:
                    self.remove(st["m"])
                    self.hud = [r for r in self.hud if r[0] is not st["m"]]
                st["k"], st["m"] = k, None
                if k >= 0:
                    st["m"] = make(chunks[k])
                    self._hud_add(st["m"], 0.0, -0.4)
                    self.add(st["m"])
                    self._place_hud()
            if st["m"] is None:
                return
            for w, part in zip(chunks[k], st["m"][1]):
                now = float(w["start"]) - 0.05 <= t < float(w["end"]) + 0.05
                done = t >= float(w["end"])
                part.set_fill(look.col("coral") if now else look.col("ink") if done else look.col("soft"))
        self.tweens.append(Call(0.0, sc.end + TAIL, None, step, None, rate_functions.linear))

    def _progress(self) -> None:
        """The chapter bar along the bottom: how far the video has gone, a tick at each chapter, the chapter's name."""
        sc = self.SCORE
        chapters = [(a.t0, a.target) for a in sc.acts if a.verb == "chapter"]
        on = sc.progress if sc.progress is not None else bool(chapters)
        if not on:
            return
        total = sc.end + TAIL
        x0, x1, y = -0.44 * S.SCREEN_W, 0.44 * S.SCREEN_W, -0.465 * S.SCREEN_H
        track = Line([x0, y, 0], [x1, y, 0], stroke_color=look.col("soft"), stroke_width=3, stroke_opacity=0.45)
        ticks = VGroup(*(Dot([x0 + (x1 - x0) * t / total, y, 0], radius=0.045, color=look.col("soft"))
                         for t, _ in chapters if t > 0.5))
        fill = Line([x0, y, 0], [x0 + 0.01, y, 0], stroke_color=look.col("coral"), stroke_width=5).set_z_index(HUD_Z + 1)
        names = [look.label(str(c), 0.13, "ink").move_to([x0, y + 0.22, 0], aligned_edge=LEFT) for _, c in chapters]
        bar = VGroup(track, ticks).set_z_index(HUD_Z)
        self.hud.append([bar, 1.0, np.zeros(3)])  # (laid out on the screen as it is; the fill is put each frame)
        self.add(bar, fill)
        for nm in names:
            nm.set_z_index(HUD_Z)
            self.hud.append([nm, 1.0, np.zeros(3)])
        al = [Alpha(nm) for nm in names]
        for a in al:
            a.set(0.0)
        st = {"k": -1}

        def place(k, c):
            t = self.clock
            fill.put_start_and_end_on(np.array([c[0] + x0 * k, c[1] + y * k, 0]),
                                      np.array([c[0] + (x0 + max(0.01, (x1 - x0) * min(1.0, t / total))) * k, c[1] + y * k, 0]))
            fill.set_stroke(width=5 * k)
        self.hud_hooks.append(place)

        def step(_a):
            t = self.clock
            cur = max((i for i, (t0, _) in enumerate(chapters) if t0 - 0.2 <= t), default=-1)
            for i, a in enumerate(al):
                since = t - chapters[i][0] + 0.2
                if i == cur:
                    a.set(min(1.0, since / 0.4))
                elif a.now > 0:
                    a.set(max(0.0, a.now - 1 / 12))
                if a.now > 0 and nm_up[i] is False:
                    self.add(names[i])
                    nm_up[i] = True
        nm_up = [False] * len(names)
        self.tweens.append(Call(0.0, sc.end + TAIL, None, step, None, rate_functions.linear))

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
        via = self._opt(act, "via", None, str)
        if via == "dive":
            return self._dive(act, max(0.0, t0), max(t1, max(0.0, t0) + 1.8))
        if via in ("page", "tear"):
            t1 = max(t1, max(0.0, t0) + 1.1)          # the sheet needs a moment to cross
            self._sheet(via, max(0.0, t0), t1)
            rate = rate_functions.ease_in_out_cubic   # the move made while the sheet hides it
        elif via == "whip":
            t1 = max(0.0, t0) + min(t1 - max(0.0, t0), 0.45)
            rate = rate_functions.ease_in_out_expo if hasattr(rate_functions, "ease_in_out_expo") else rate_functions.smooth
        else:
            rate = rate_functions.ease_in_out_sine
        tw = Call(max(0.0, t0), t1, start, step, None, rate)
        tw.camera = True
        self.tweens.append(tw)

    def _dive(self, act: S.Act, t0, t1) -> None:
        """Into a thing (a pin, a picture) until it fills the screen, and out of it onto the next shot: `cam SHOT via
        dive into REF`. The paper closes over the view as it goes in, and opens on the new place."""
        f = self.camera.frame
        ref = self._opt(act, "into", None, str)
        st = {}
        iris = Circle(radius=1.0, fill_color=look.col("bg"), fill_opacity=1, stroke_color=look.col("ink"),
                      stroke_width=look.STROKE * 0.5).set_z_index(945)

        def start():
            st["c0"], st["w0"] = f.get_center().copy(), f.width
            st["c1"], st["w1"] = self._cam_target(act)
            st["p"] = self._locate(ref, "") if ref else st["c0"].copy()
            st["r"] = 1.0
            st["al"] = Alpha(iris)
            iris.move_to(st["p"]).scale(0.01)
            st["r"] = 0.01
            self.add(iris)

        def step(a):
            if a < 0.5:                         # in: toward the thing, closer and closer; the paper closes over
                k = rate_functions.ease_in_cubic(a / 0.5)
                f.move_to(st["c0"] + (st["p"] - st["c0"]) * min(1.0, k * 1.4))
                f.set_width(math.exp(math.log(st["w0"]) + (math.log(st["w0"] / 9) - math.log(st["w0"])) * k))
                r = max(0.01, f.width * 0.75 * max(0.0, (k - 0.45) / 0.55))
                iris.move_to(st["p"])
                st["al"].set(1.0)
            else:                               # out: the new place, from close in, opening as the camera draws back
                k = rate_functions.ease_out_cubic((a - 0.5) / 0.5)
                f.move_to(st["c1"])
                f.set_width(math.exp(math.log(st["w1"] / 6) + (math.log(st["w1"]) - math.log(st["w1"] / 6)) * k))
                iris.move_to(st["c1"])
                r = f.width * 0.75 * (1 + 0.6 * k)
                st["al"].set(max(0.0, 1 - k * 1.6))
            iris.scale(r / st["r"])
            iris.set_stroke(width=look.STROKE * 0.5 * f.width / S.SCREEN_W)
            st["r"] = r

        def stop():
            self.remove(iris)
            f.move_to(st["c1"])
            f.set_width(st["w1"])
        tw = Call(t0, t1, start, step, stop, rate_functions.linear)
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


def _soundtrack(sc, voice_dir: Path) -> Path:
    """The voice with the score's small sounds and music under it (sound.py), else the voice alone."""
    try:
        import sound
        out = voice_dir / "soundtrack.wav"
        sound.mix(sc, voice_dir / "voice.wav", out)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"soundtrack not made ({e}): the voice alone", file=sys.stderr)
        return voice_dir / "voice.wav"


def frames_of(seconds: float, fps: int) -> int:
    return int(round(seconds * fps))


def jobs_default() -> int:
    """How many chunks render at once: V3_RENDER_JOBS, else half the machine's cores (at most 8)."""
    env = os.environ.get("V3_RENDER_JOBS", "").strip()
    return max(1, int(env)) if env.isdigit() else max(1, min(8, (os.cpu_count() or 2) // 2))


def _one(sc: S.Score, words: dict, voice_dir: Path, out: Path, quality: str, frames=None, sound=True,
         media: Path | None = None) -> None:
    ScoreScene.SCORE, ScoreScene.WORDS = sc, words
    ScoreScene.WAV = str(_soundtrack(sc, voice_dir) if sound else voice_dir / "voice.wav")
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
        print(f"drawing {total} frames in one process", flush=True)
        _one(sc, words, voice_dir, out, quality)
        return sc.notes
    parts = out.parent / ".parts"
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir(parents=True)
    (parts / "video.score").write_text(score_text)
    cuts = [round(total * k / jobs) for k in range(jobs + 1)]
    print(f"drawing {total} frames in {jobs} chunks at once", flush=True)
    procs, done, outs = [], [0] * jobs, [([], []) for _ in range(jobs)]
    for k in range(jobs):
        cmd = [sys.executable, __file__, str(parts / "video.score"), str(voice_dir), str(parts / f"part{k}.mp4"),
               "--quality", quality, "--frames", f"{cuts[k]}:{cuts[k + 1]}", "--nosound", "--media", str(parts / f"media{k}")]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
                                      env={**os.environ, "PYTHONUNBUFFERED": "1"}))

    def pump(k: int, stream, buf: list) -> None:
        for line in iter(stream.readline, ""):
            m = re.match(r"^progress: (\d+)/(\d+)", line)
            if m:
                done[k] = int(m.group(1))
            else:
                buf.append(line)
        stream.close()

    import threading
    readers = [threading.Thread(target=pump, args=(k, p.stdout, outs[k][0]), daemon=True) for k, p in enumerate(procs)]
    readers += [threading.Thread(target=pump, args=(k, p.stderr, outs[k][1]), daemon=True) for k, p in enumerate(procs)]
    for t in readers:
        t.start()
    import time as _time
    last = -1
    while any(p.poll() is None for p in procs):
        _time.sleep(0.5)
        if sum(done) != last:
            last = sum(done)
            print(f"progress: {last}/{total} frames drawn", flush=True)
    for t in readers:
        t.join(timeout=5)
    outs = [("".join(o), "".join(e)) for o, e in outs]
    for p, (o, e) in zip(procs, outs):
        if p.returncode != 0:
            raise RuntimeError(f"a chunk of the render failed:\n{(e or o)[-1500:]}")
    print(f"progress: {total}/{total} frames drawn", flush=True)
    print("joining the chunks and laying the voice under them", flush=True)
    notes = [l[6:] for l in outs[0][0].splitlines() if l.startswith("note: ")]
    said = []
    for o, e in outs:
        said += [l for l in e.splitlines() if l.startswith("score line") and l not in said]
    for l in said:
        print(l, file=sys.stderr)
    (parts / "list.txt").write_text("".join(f"file 'part{k}.mp4'\n" for k in range(jobs)))
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(parts / "list.txt"),
                    "-i", str(_soundtrack(sc, voice_dir)), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
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
