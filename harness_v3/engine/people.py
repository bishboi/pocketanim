"""People drawn with a pen, who move: little cartoon figures (a round head with a face and hair, clothes, outlined
limbs, hands and shoes, a soft shadow at their feet) posed over time.

    ent ann person as ROLE (attire.py: king, knight, nun, bishop, peasant, maharaja...: a whole outfit; what the line
                   adds wins)
    ent ann person [wear shirt|tunic|robe|habit|dress|gown|coat|suit|armor|apron|toga|uniform|lab|overalls|vest]
                   [color C] [hair short|long|bob|bun|ponytail|curly|spiky|bald[-black|brown|blonde|red|grey|white]]
                   [beard | longbeard] [mustache] [skin fair|light|tan|brown|dark]
                   [mood FACE (MOODS below)] [stubble]
                   [hat top|bowler|cap|beret|straw|cowboy|crown|helmet|tricorn|mitre|turban|hood|veil|chef|hardhat|
                        wreath|headscarf]
                   [tool book|scroll|quill|coin|bag|sword|shield|staff|spear|flag|sign|hammer|pickaxe|torch|lantern|
                         basket|cane|pointer|briefcase]
                   [seat] [old] [kid] [face left] [size H] at X,Y          (its feet at X,Y)

A person is a pose (the angles of the body, arms and legs, where the face looks, how open the mouth is) drawn where
the figure now stands, so a person moved, scaled or turned on the page poses there. Every part that does not bend
(the head with its hair and hat, the clothes, a hand with what it holds, a shoe) is one rigid shape carried by the
pose, so the timeline keeps it as one shape and a transform. The renderer's verbs set poses over time (render.py):
walk, run, point, wave, talk, carry, sit, stand, turn, cheer, shrug, think, bow, jump, nod.

Angles are in radians from straight down, toward the way the figure faces.
"""

from __future__ import annotations

import math
import os
import zlib

import numpy as np
from manim import Circle, Dot, Ellipse, Line, Mobject, VGroup, VMobject

import attire
from look import STROKE, col

# A body one unit tall (feet at 0): where each part is, and how long. The head is big: a cartoon's proportions.
HIP, TORSO, NECK, HEAD = 0.41, 0.25, 0.03, 0.115
UPPER, FORE, THIGH, SHIN = 0.14, 0.14, 0.215, 0.195

REST = {"lean": 0.0, "fa1": 0.14, "fa2": 0.22, "ba1": -0.12, "ba2": -0.06, "fl1": 0.07, "fl2": 0.0, "bl1": -0.07,
        "bl2": -0.07, "drop": 0.0, "face": 1.0, "mouth": 0.0, "bob": 0.0, "nod": 0.0, "blink": 0.0, "breath": 0.0}
# The face, every part a number the pose eases (so one look turns into another as it plays):
#   smile -1 frown .. 1 grin; smirk -1..1 (one corner up); wavy 0..1 (an uneasy, wobbly mouth); grin 0..1 (open, a
#   D); tongue 0..1 (out, in the grin); mouth 0..1 (open round: talking, surprise)
#   brow -1 low .. 1 raised; frown -1 (inner ends up: sad) .. 1 (drawn in: cross); lids 0 open .. 1 shut (heavy
#   lids: smug, suspicious, sleepy); gaze -1 down .. 1 up; side -1 .. 1 (the eyes slide away from / toward the way it
#   faces: a side-eye)
#   eyes drawn otherwise: xeyes (x x: dazed), squint (> <: pain, effort), joy (^ ^: delight), shades (sunglasses)
#   on the head: sweat (a drop: nerves), anger (a bolt), blush (/// on the cheeks), tears
FACE = {"smile": 0.2, "smirk": 0.0, "wavy": 0.0, "grin": 0.0, "tongue": 0.0, "mouth": 0.0, "brow": 0.0, "frown": 0.0,
        "lids": 0.1, "gaze": 0.0, "side": 0.0, "xeyes": 0.0, "squint": 0.0, "joy": 0.0, "shades": 0.0,
        "sweat": 0.0, "anger": 0.0, "blush": 0.0, "tears": 0.0}
REST.update(FACE)
KEYS = tuple(REST)
FACE_KEYS = tuple(FACE)


def _mood(**k) -> dict:
    return {**FACE, **k}


# Expressions (`mood NAME` to begin with, `emote P NAME` to ease into one as it plays).
MOODS = {
    "happy": _mood(smile=0.85, brow=0.15, lids=0.05),
    "calm": _mood(smile=0.25, lids=0.25),
    "joy": _mood(joy=1, smile=0.9, blush=0.5, brow=0.3),
    "laugh": _mood(joy=1, grin=1, brow=0.45),
    "excited": _mood(grin=1, smile=1, brow=0.7, lids=0.0, blush=0.3),
    "playful": _mood(grin=1, tongue=1, smirk=0.3, lids=0.15, brow=0.3),
    "proud": _mood(smile=0.7, lids=0.35, gaze=0.45, brow=0.2),
    "smug": _mood(smile=0.5, smirk=1, lids=0.55, brow=0.55, frown=0.2),
    "cool": _mood(shades=1, smirk=0.8, smile=0.4),
    "sad": _mood(smile=-0.85, frown=-0.9, brow=0.3, lids=0.35, gaze=-0.45),
    "crying": _mood(smile=-0.9, frown=-1, brow=0.4, lids=0.3, tears=1, wavy=0.3, gaze=-0.3),
    "angry": _mood(smile=-0.55, frown=1, brow=-0.45, lids=0.35, anger=1),
    "furious": _mood(smile=-0.8, frown=1, brow=-0.6, lids=0.3, anger=1, mouth=0.45),
    "annoyed": _mood(smile=-0.3, wavy=0.4, frown=0.35, lids=0.55, side=0.6),
    "suspicious": _mood(smile=-0.1, frown=0.45, brow=-0.2, lids=0.5, side=1),
    "surprised": _mood(smile=0.0, brow=1, lids=0.0, mouth=0.6),
    "shocked": _mood(smile=0.0, brow=1, lids=0.0, mouth=0.95, sweat=1),
    "scared": _mood(smile=-0.3, wavy=1, brow=0.9, frown=-0.7, lids=0.0, sweat=1),
    "worried": _mood(smile=-0.3, wavy=0.7, brow=0.55, frown=-0.6),
    "nervous": _mood(smile=0.0, wavy=1, brow=0.3, sweat=1, side=-0.7),
    "embarrassed": _mood(smile=0.0, wavy=0.8, blush=1, brow=0.4, side=-0.8, gaze=-0.3, sweat=0.5),
    "confused": _mood(smile=0.0, wavy=0.6, brow=0.6, frown=0.2, side=0.3, sweat=0.3),
    "think": _mood(smile=0.0, smirk=0.4, brow=0.3, frown=0.3, gaze=1, side=0.5),
    "dazed": _mood(xeyes=1, wavy=1, smile=0.0),
    "pained": _mood(squint=1, smile=-0.7, frown=0.5, sweat=0.6),
    "sleepy": _mood(lids=0.85, smile=0.0, mouth=0.15, brow=-0.1),
    "disgusted": _mood(smile=-0.5, wavy=0.6, frown=0.6, lids=0.4, side=-0.4),
}
MOODS.update({"neutral": MOODS["calm"], "cry": MOODS["crying"], "shy": MOODS["embarrassed"], "thinking": MOODS["think"],
              "fear": MOODS["scared"], "mad": MOODS["angry"], "glad": MOODS["happy"], "sly": MOODS["smug"]})

SKIN = {"fair": "#F6DCC4", "light": "#EFC9A6", "tan": "#D9A274", "brown": "#A8714A", "dark": "#6E4429"}
HAIR = {"black": "#2A2320", "brown": "#6B4226", "blonde": "#D9AA4E", "red": "#B4532A", "grey": "#A9A49B",
        "white": "#EEEAE2"}
SHOE = "#2B2622"


def walk_pose(phase: float, run: bool = False) -> dict:
    """The walk cycle at a phase (radians): legs and arms swinging opposite, a knee bending as its foot comes through
    (a run: wider, the knees higher, the body leaning in)."""
    s, k = math.sin(phase), (1.35 if run else 1.0)
    p = dict(REST)
    p["fl1"] = 0.42 * s * k
    p["fl2"] = p["fl1"] - (0.55 + 0.5 * run) * max(0.0, math.cos(phase))
    p["bl1"] = -0.42 * s * k
    p["bl2"] = p["bl1"] - (0.55 + 0.5 * run) * max(0.0, -math.cos(phase))
    p["fa1"] = -0.38 * s * k
    p["fa2"] = p["fa1"] + (0.35 + 0.9 * run)
    p["ba1"] = 0.38 * s * k
    p["ba2"] = p["ba1"] + (0.35 + 0.9 * run)
    p["bob"] = (0.018 + 0.02 * run) * abs(math.cos(phase))
    p["lean"] = 0.2 if run else 0.06
    return p


def sit_pose(seat: bool) -> dict:
    p = dict(REST)
    if seat:                                    # on its stool: thighs level, shins down
        p.update(drop=HIP - 0.22, fl1=math.pi / 2, fl2=0.05, bl1=math.pi / 2 - 0.12, bl2=-0.05, fa1=0.35, fa2=1.1,
                 ba1=0.25, ba2=1.0)
    else:                                       # on the ground, knees up
        p.update(drop=HIP - 0.06, fl1=2.0, fl2=-0.4, bl1=1.7, bl2=-0.6, fa1=0.6, fa2=1.6, ba1=0.4, ba2=1.4,
                 lean=0.12)
    return p


def carry_pose() -> dict:
    p = dict(REST)
    p.update(fa1=0.45, fa2=1.55, ba1=0.35, ba2=1.45)
    return p


# Poses some verbs move toward (only the keys named are theirs; render.py blends them in and out).
GESTURES = {
    "cheer": {"fa1": 2.7, "fa2": 2.9, "ba1": 2.5, "ba2": 2.8, "smile": 1.0, "mouth": 0.6, "brow": 0.4},
    "shrug": {"fa1": 0.5, "fa2": 2.0, "ba1": 0.45, "ba2": 1.9, "nod": -0.12, "brow": 0.8, "smile": -0.2},
    "think": {"fa1": 0.25, "fa2": 2.75, "nod": 0.12, "gaze": 1.0, "frown": 0.35, "smile": -0.1},
    "bow": {"lean": 0.75, "fa1": 0.5, "fa2": 0.5, "ba1": 0.45, "ba2": 0.45},
}


def mix(a: dict, b: dict, k: float) -> dict:
    return {key: a[key] + (b[key] - a[key]) * k for key in KEYS}


def _pick(seq, seed: int, salt: str):
    return seq[zlib.crc32(f"{seed}{salt}".encode()) % len(seq)]


def _blob(points, fill, ink, w, opacity=1.0) -> VMobject:
    """A closed shape through the points, smooth, filled and outlined (a hand-drawn shape, not a ruled one)."""
    m = VMobject(fill_color=fill, fill_opacity=opacity, stroke_color=ink, stroke_width=w)
    pts = [np.array([x, y, 0.0]) for x, y in points]
    m.set_points_smoothly([*pts, pts[0]])
    return m


def _poly(points, fill, ink, w, opacity=1.0) -> VMobject:
    m = VMobject(fill_color=fill, fill_opacity=opacity, stroke_color=ink, stroke_width=w)
    pts = [np.array([x, y, 0.0]) for x, y in points]
    m.set_points_as_corners([*pts, pts[0]])
    return m


def _arc(cx, cy, r, a0, a1, n=24):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in np.linspace(a0, a1, n)]


def _stroke(points, ink, w) -> VMobject:
    m = VMobject(stroke_color=ink, stroke_width=w, fill_opacity=0)
    m.set_points_smoothly([np.array([x, y, 0.0]) for x, y in points])
    return m


class Person(VGroup):
    def __init__(self, mods: dict | None = None, c=None, size: float = 1.8):
        super().__init__()
        mods = attire.role(mods or {})
        self.mods = mods
        seed = zlib.crc32(str(mods.get("_name", "")).encode())
        k = size / 1.8                          # line widths are on the screen: kept in step with the figure's size
        ink = col("ink")
        self.ow = ow = 2.2 * k                  # the outline
        old = bool(mods.get("old"))
        skin = SKIN.get(str(mods.get("skin") or ""), None) or _pick(list(SKIN.values()), seed, "skin")
        hair_s, _, hair_c = str(mods.get("hair") or _pick(["short", "short", "bob", "curly", "long", "bun", "spiky"],
                                                            seed, "hair")).partition("-")
        hair = HAIR.get(hair_c) or (HAIR["grey"] if old else _pick([HAIR["black"], HAIR["brown"], HAIR["brown"],
                                                                     HAIR["blonde"], HAIR["red"]], seed, "hc"))
        wear = str(mods.get("wear") or "shirt").lower()
        spec = WEAR.get(wear, WEAR["shirt"])
        cloth = col(mods.get("color") or c) if (mods.get("color") or c) else (
            spec["color"] if spec["color"] else col(_pick(["coral", "teal", "navy", "gold", "green", "sky"], seed, "c")))
        arms = skin if spec["arms"] == "skin" else (spec["arms"] or cloth)
        legs = skin if spec["legs"] == "skin" else (col(spec["legs"]) if spec["legs"] else cloth)
        self.skin, self.cloth = skin, cloth
        self.rigid: list[tuple] = []            # (shape, its points where its part's own frame is, the part)
        self.rest = dict(REST)
        self.rest.update(MOODS.get(str(mods.get("mood") or "happy").lower(), MOODS["happy"]))
        self.alpha_now = 1.0                    # how far it has faded in (render.Alpha tells it: refade)
        if old:
            self.rest["lean"] = 0.1

        def rigid(m, part):
            for x in m.family_members_with_points():
                self.rigid.append((x, x.points[:, :2].copy(), part))
            return m

        # -- the ground, a seat -------------------------------------------------------------------------------------
        self.add(rigid(Ellipse(width=0.34, height=0.05, fill_color=ink, fill_opacity=0.12, stroke_width=0), "ground"))
        self.seat = None
        if mods.get("seat"):
            wood = "#9A6B43"
            self.seat = rigid(VGroup(
                _poly([(-0.14, 0.2), (0.15, 0.2), (0.15, 0.235), (-0.14, 0.235)], wood, ink, ow),
                Line([-0.1, 0.2, 0], [-0.13, 0, 0], stroke_color=ink, stroke_width=ow * 2),
                Line([0.11, 0.2, 0], [0.14, 0, 0], stroke_color=ink, stroke_width=ow * 2),
                Line([-0.115, 0.08, 0], [0.125, 0.08, 0], stroke_color=ink, stroke_width=ow)), "ground")
            self.add(self.seat)

        # -- limbs: a line in the cloth's colour over a darker one (outlined), a hand, a shoe -----------------------
        lw, aw = 5.6 * k, 4.6 * k

        def limb(colour, width):
            under = Line([0, 0, 0], [0, -0.1, 0], stroke_color=ink, stroke_width=width + 2 * ow)
            over = Line([0, 0, 0], [0, -0.1, 0], stroke_color=colour, stroke_width=width)
            return under, over

        def shoe():
            return rigid(Ellipse(width=0.085, height=0.04, fill_color=SHOE, fill_opacity=1, stroke_width=0)
                         .move_to([0.022, 0.016, 0]), "_")

        def hand():
            return rigid(Circle(radius=0.022, fill_color=skin, fill_opacity=1, stroke_color=ink, stroke_width=ow), "_")

        self.hair_back = VGroup()
        self.legs = {n: limb(legs, lw) for n in ("bl", "bs", "fl", "fs")}
        self.arms = {n: limb(arms, aw) for n in ("ba", "bf", "fa", "ff")}
        self.shoes = {"b": shoe(), "f": shoe()}
        self.hands = {"b": hand(), "f": hand()}
        for (n, part) in (("b", "foot_b"), ("f", "foot_f")):
            self._retag(self.shoes[n], part)
        for (n, part) in (("b", "hand_b"), ("f", "hand_f")):
            self._retag(self.hands[n], part)

        # -- the head: hair behind it, the head, the face, hair over it, a beard, a hat -----------------------------
        R = HEAD
        hat = str(mods.get("hat") or "").lower()
        covered = hat in COVERED
        back, front = _hair(hair_s if not covered else "none", hair, ink, ow, R)
        hb, hf = _hat(hat, ink, ow, R, cloth)
        hf.add(attire.plume(mods.get("decor") or {}, ink, ow, R))
        self.add(rigid(hb, "head"))
        self.add(rigid(back, "head"))
        self.add(*self.legs["bl"], *self.legs["bs"], self.shoes["b"], *self.arms["ba"], *self.arms["bf"],
                 self.hands["b"])
        self.add(*self.legs["fl"], *self.legs["fs"], self.shoes["f"])
        self.torso_m = rigid(_garment(wear, spec, cloth, ink, ow, skin), "torso")
        self.add(self.torso_m)
        self.neck = Line([0, 0, 0], [0, 0.1, 0], stroke_color=skin, stroke_width=aw)
        self.add(self.neck)
        self.head = Circle(radius=R, fill_color=skin, fill_opacity=1, stroke_color=ink, stroke_width=ow)
        self.add(rigid(self.head, "head"))
        ear = Circle(radius=0.02, fill_color=skin, fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.8).move_to([-0.092, -0.012, 0])
        if not covered:
            self.add(rigid(ear, "head"))
        self.add(rigid(front, "head"))
        if mods.get("beard") or mods.get("longbeard"):
            long = bool(mods.get("longbeard")) or old
            self.add(rigid(_beard(hair, ink, ow, R, long), "face"))
        self._build_face(ink, ow, skin, hair, hair_s, mods)
        self.add(rigid(hf, "head"))
        # -- the front arm, with what its hand holds ----------------------------------------------------------------
        self.tool = _tool(str(mods.get("tool") or ("cane" if old else "")).lower(), ink, ow, k)
        self.add(*self.arms["fa"], *self.arms["ff"])
        if self.tool is not None:
            self.add(rigid(self.tool, "hand_f"))
        self.add(self.hands["f"])
        self.hand = Dot(radius=0.001).set_opacity(0)
        self.hand_b = Dot(radius=0.001).set_opacity(0)      # the other hand (for a second thing held)
        self.offhand_m = None
        # Where the figure's own coordinates are now (carried along as it is moved, scaled or turned).
        self._ref = VGroup(*(Dot([x, y, 0], radius=0.001).set_opacity(0) for x, y in ((0, 0.5), (0.1, 0.5), (0, 0.6))))
        self.add(self.hand, self.hand_b, self._ref)
        self.pose = dict(self.rest)
        self.pose["face"] = -1.0 if mods.get("face") == "left" else 1.0
        self.set_pose(self.pose)

    @property
    def core(self):
        """The figure itself, its head and body (not what it holds out: a sword's tip, a staff), for what it covers."""
        parts = [x for x in (getattr(self, "torso_m", None), getattr(self, "head", None)) if x is not None]
        return VGroup(*parts) if parts else self

    def sit_target(self) -> dict:
        """The pose it sits in (a peg figure has its own)."""
        return sit_pose(self.seat is not None)

    # the body's measures (a country character has its own)
    D = {"HIP": HIP, "TORSO": TORSO, "NECK": NECK, "HEAD": HEAD, "UPPER": UPPER, "FORE": FORE, "THIGH": THIGH,
         "SHIN": SHIN}
    hips = ((0.0, 0.0), (0.0, 0.0))            # where each leg leaves the hip (front, back), x toward the face
    shoulders = ((0.0, 0.0), (0.0, 0.0))       # where each arm leaves the shoulders
    face_k = 1.0                               # the face's size

    # -- the face -----------------------------------------------------------------------------------------------------
    def _build_face(self, ink, ow, skin, hair, hair_s, mods) -> None:
        """Eyes (whites, pupils, lids), and the other eyes they may become (x x, > <, ^ ^, sunglasses); brows; the
        mouths (a curve that smiles, frowns and smirks; a wavy one; an open one; a grin with a tongue); sweat, an anger
        bolt, blush, tears. What shows of each is set by the pose (set_pose), so faces turn into one another."""
        dark = "#5A1F1F"
        self.fixed: list[tuple] = []            # (shape, its points about its own middle, where it goes)
        self.feats: list[tuple] = []            # (shape, its own fill and line opacity, how much of it shows)

        def fixed(m, where):
            for x in m.family_members_with_points():
                self.fixed.append((x, x.points[:, :2].copy(), where))
            return m

        def feat(m, weight):
            if not len(m.points) and not m.submobjects:      # (posed later: given points now, so it is known)
                m.set_points_as_corners([np.array([-0.01, 0.0, 0.0]), np.array([0.01, 0.0, 0.0]),
                                         np.array([0.0, 0.01, 0.0])])
            for x in m.family_members_with_points():
                self.feats.append((x, float(x.get_fill_opacity()), float(x.get_stroke_opacity()), weight))
            return m

        def normal(p):
            return 1 - min(1.0, max(p["xeyes"], p["squint"], p["joy"], p["shades"]))

        def open_m(p):
            k = min(1.0, max(0.0, (p["mouth"] - 0.06) / 0.2))
            return k * k * (3 - 2 * k)
        self.whites, self.pupils, self.lids, self.brows = [], [], [], []
        for i in range(2):
            w_ = feat(fixed(Ellipse(width=0.036, height=0.044, fill_color="#FFFFFF", fill_opacity=1, stroke_color=ink,
                                    stroke_width=ow * 0.9), ("eye", i)), normal)
            pu = feat(fixed(Circle(radius=0.0105, fill_color=ink, fill_opacity=1, stroke_width=0), ("pupil", i)), normal)
            shine = feat(fixed(Circle(radius=0.0035, fill_color="#FFFFFF", fill_opacity=1, stroke_width=0)
                               .move_to([0.004, 0.004, 0]), ("pupil", i)), normal)
            lid = feat(VMobject(fill_color=skin, fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.9), normal)
            self.whites.append(w_)
            self.pupils.append(pu)
            self.lids.append(lid)
            self.add(w_, pu, shine, lid)
        for i in range(2):                      # the other eyes, in the same places
            s_ = 1 if i == 0 else -1            # (which way is toward the middle)
            x = VGroup(Line([-0.014, 0.014, 0], [0.014, -0.014, 0]), Line([-0.014, -0.014, 0], [0.014, 0.014, 0]))
            x.set_stroke(ink, ow * 1.2)
            sq = VMobject(stroke_color=ink, stroke_width=ow * 1.2, fill_opacity=0)
            sq.set_points_as_corners([np.array([-s_ * 0.014, 0.013, 0]), np.array([s_ * 0.014, 0.0, 0]),
                                      np.array([-s_ * 0.014, -0.013, 0])])
            jy = _stroke(_arc(0, -0.012, 0.017, 20, 160, 9), ink, ow * 1.2)
            self.add(feat(fixed(x, ("eye", i)), lambda p: p["xeyes"]), feat(fixed(sq, ("eye", i)), lambda p: p["squint"]),
                     feat(fixed(jy, ("eye", i)), lambda p: p["joy"]))
        shades = VGroup(Ellipse(width=0.046, height=0.034, fill_color="#1D1C1A", fill_opacity=1, stroke_width=0).shift([-0.026, 0, 0]),
                        Ellipse(width=0.046, height=0.034, fill_color="#1D1C1A", fill_opacity=1, stroke_width=0).shift([0.026, 0, 0]),
                        Line([-0.004, 0.006, 0], [0.004, 0.006, 0], stroke_color="#1D1C1A", stroke_width=ow * 1.2),
                        Circle(radius=0.005, fill_color="#FFFFFF", fill_opacity=0.8, stroke_width=0).shift([-0.032, 0.008, 0]),
                        Circle(radius=0.005, fill_color="#FFFFFF", fill_opacity=0.8, stroke_width=0).shift([0.02, 0.008, 0]))
        self.add(feat(fixed(shades, ("eyes", 0)), lambda p: p["shades"]))
        brow_c = _shade(hair, 0.5) if hair_s not in ("bald", "none") else ink
        for i in range(2):
            b = Line([0, 0, 0], [0.03, 0, 0], stroke_color=brow_c, stroke_width=ow * 1.6)
            self.brows.append(b)
            self.add(b)
        # the mouths
        self.smile = feat(VMobject(stroke_color=ink, stroke_width=ow * 1.2, fill_opacity=0),
                          lambda p: 1 - min(1.0, max(p["wavy"], p["grin"], open_m(p))))
        self.wavy = feat(VMobject(stroke_color=ink, stroke_width=ow * 1.1, fill_opacity=0),
                         lambda p: p["wavy"] * (1 - p["grin"]) * (1 - open_m(p)))
        self.mouth = feat(Ellipse(width=0.04, height=0.012, fill_color=dark, fill_opacity=1, stroke_color=ink,
                                  stroke_width=ow * 0.7), lambda p: open_m(p) * (1 - p["grin"]))
        grin = VGroup(_poly(_arc(0, 0.0, 0.03, 180, 360, 12), dark, ink, ow * 0.9),
                      Line([-0.03, 0.0, 0], [0.03, 0.0, 0], stroke_color="#FFFFFF", stroke_width=ow * 1.4))
        tongue = _blob([(-0.012, -0.012), (0.0, -0.042), (0.014, -0.012)], "#E07A7A", ink, ow * 0.7)
        self.add(self.smile, self.wavy, self.mouth, feat(fixed(grin, ("mouth", 0)), lambda p: p["grin"]),
                 feat(fixed(tongue, ("mouth", 0)), lambda p: p["grin"] * p["tongue"]))
        # on the head
        drop = _blob([(0.0, 0.022), (0.012, -0.004), (0.0, -0.016), (-0.012, -0.004)], "#9FD3F0", ink, ow * 0.8)
        bolt = _poly([(0.0, 0.03), (0.02, 0.03), (0.006, 0.008), (0.02, 0.008), (-0.008, -0.03), (0.002, -0.004),
                      (-0.012, -0.004)], "#F7C514", ink, ow * 0.7)
        blush = VGroup(*(Line([x - 0.006, -0.032, 0], [x + 0.004, -0.018, 0]) for x in (-0.06, -0.05, -0.04, 0.04, 0.05, 0.06)))
        blush.set_stroke("#E0607A", ow * 1.0)
        tears = VGroup(*(_blob([(s_ * 0.025, -0.002), (s_ * 0.031, -0.04), (s_ * 0.025, -0.05), (s_ * 0.019, -0.04)],
                               "#9FD3F0", ink, ow * 0.6) for s_ in (-1, 1)))
        self.add(feat(fixed(drop, ("side", 0)), lambda p: p["sweat"]), feat(fixed(bolt, ("bolt", 0)), lambda p: p["anger"]),
                 feat(fixed(blush, ("face", 0)), lambda p: p["blush"]), feat(fixed(tears, ("face", 0)), lambda p: p["tears"]))
        if mods.get("stubble"):
            dots = VGroup(*(Dot([x, y, 0], radius=0.003, color=_shade(hair, 0.7)) for x in np.linspace(-0.07, 0.07, 9)
                            for y in (-0.06, -0.075, -0.09) if x * x / 0.0064 + (y + 0.02) ** 2 / 0.0064 < 1.0))
            self.add(fixed(dots, ("face", 0)))
        if mods.get("mustache"):
            self.add(fixed(_blob([(-0.03, -0.03), (0.0, -0.022), (0.03, -0.03), (0.034, -0.042), (0.0, -0.036),
                                  (-0.034, -0.042)], hair, ink, ow * 0.6), ("face", 0)))
        self.add(fixed(_face("", ink, ow, HEAD), ("face", 0)))
        self.add(fixed(attire.on_face(mods.get("decor") or {}, ink, ow), ("face", 0)))
        self.managed_ids = {id(x) for x, *_ in self.feats}

    def refade(self, a: float) -> None:
        """As it fades (render.Alpha): the face's parts at their own share of it."""
        self.alpha_now = a
        self._show_face(self.pose)

    def _show_face(self, p: dict) -> None:
        a = self.alpha_now
        for x, fo, so, weight in self.feats:
            k = max(0.0, min(1.0, weight(p))) * a
            x.set_fill(opacity=fo * k, family=False)
            x.set_stroke(opacity=so * k, family=False)

    def _pose_face(self, p: dict, o, ex, ey, face, f: float, turn: float) -> None:
        k = self.face_k

        def Wv(pts):                            # body frame -> the world, many points at once (the face at its size)
            pts = np.asarray(pts, dtype=float)
            if k != 1.0:
                pts = face + (pts - face) * k
            return o + np.outer(pts[:, 0], ex) + np.outer(pts[:, 1] - 0.5, ey)
        squeeze = 1 - 0.22 * abs(turn)
        eyes = [face + np.array([(i - 0.5) * 0.054 * squeeze, 0.02 + 0.006 * p["gaze"]]) for i in range(2)]
        look = np.array([0.0065 * p["side"] * f, 0.007 * p["gaze"]])
        where = {("eye", 0): eyes[0], ("eye", 1): eyes[1], ("pupil", 0): eyes[0] + look,
                 ("pupil", 1): eyes[1] + look, ("eyes", 0): face + np.array([0.0, 0.02]),
                 ("mouth", 0): face + np.array([0.004 * p["smirk"] * f, -0.052]),
                 ("side", 0): face + np.array([-0.075 * f, 0.075]), ("bolt", 0): face + np.array([0.06 * f, 0.1]),
                 ("face", 0): face}
        for x, base, at in self.fixed:
            b = base.copy()
            if at[0] in ("side", "bolt"):
                b[:, 0] *= f
            x.points = Wv(b + where[at])
        # lids: the skin over the top of each eye, down to `lids` (and a blink), tilted by `frown` (cross: the inner
        # end low; sad: the outer end low)
        shut = max(0.0, min(1.0, p["lids"] + p["blink"]))
        a_, b_ = 0.018, 0.022
        for i, (lid, c) in enumerate(zip(self.lids, eyes)):
            inner = 1.0 if i == 0 else -1.0
            h = b_ * (1 - 2 * shut) if shut > 0.01 else b_ * 1.02
            t0 = math.asin(max(-0.999, min(0.999, h / b_)))
            ang = np.linspace(t0, math.pi - t0, 12)
            pts = [(a_ * 1.08 * math.cos(t), b_ * 1.08 * math.sin(t)) for t in ang]
            pts = pts + [pts[0]]
            tilt = -0.35 * p["frown"] * inner
            ca, sa = math.cos(tilt), math.sin(tilt)
            pts = [(c[0] + ca * x - sa * y, c[1] + sa * x + ca * y) for x, y in pts]
            lid.set_points_as_corners(list(Wv(pts)))
        # brows: over each eye, raised by `brow`, the inner end drawn down by `frown` (up when sad); lower with the lids
        for i, (b, c) in enumerate(zip(self.brows, eyes)):
            inner = 1.0 if i == 0 else -1.0
            by = c[1] + 0.033 + 0.014 * p["brow"] - 0.008 * max(0.0, p["lids"] - 0.3)
            tilt = 0.014 * p["frown"]
            b.put_start_and_end_on(Wv([[c[0] - inner * 0.02, by + tilt * 0.3]])[0],
                                   Wv([[c[0] + inner * 0.02, by - tilt]])[0])
        # mouths
        sm = max(-1.0, min(1.0, p["smile"]))
        sk = 0.014 * p["smirk"] * f
        w_ = 0.027 * (1 + 0.25 * abs(sm))
        my = face[1] - 0.052
        self.smile.set_points_smoothly([np.array([q[0], q[1], 0.0]) for q in Wv([
            (face[0] - w_, my + 0.013 * sm - sk), (face[0] - w_ / 3, my - 0.008 * sm - sk * 0.3),
            (face[0] + w_ / 3, my - 0.008 * sm + sk * 0.3), (face[0] + w_, my + 0.013 * sm + sk)])])
        self.wavy.set_points_smoothly([np.array([q[0], q[1], 0.0]) for q in Wv([
            (face[0] + x, my + 0.006 * math.sin(k * 2.2)) for k, x in enumerate(np.linspace(-0.028, 0.028, 6))])])
        mh = max(0.004, 0.008 + 0.042 * max(0.0, min(1.0, p["mouth"])))
        base = Ellipse(width=0.04, height=mh).move_to([face[0], my - 0.002, 0])
        self.mouth.points = Wv(base.points[:, :2])
        self._show_face(p)

    def _retag(self, m, part) -> None:
        ids = {id(x) for x in m.family_members_with_points()}
        self.rigid = [(x, b, part if id(x) in ids else p) for x, b, p in self.rigid]

    # -- where its own coordinates are now --------------------------------------------------------------------------
    def w(self, p) -> np.ndarray:
        o, x, y = (d.get_center() for d in self._ref)
        return o + (p[0] - 0.0) * (x - o) / 0.1 + (p[1] - 0.5) * (y - o) / 0.1

    def unit(self) -> float:
        o, _, y = (d.get_center() for d in self._ref)
        return float(np.linalg.norm(y - o)) / 0.1

    def feet(self) -> np.ndarray:
        return self.w((0.0, 0.0))

    def facing(self) -> float:
        return 1.0 if self.pose["face"] >= 0 else -1.0

    # -- the pose ------------------------------------------------------------------------------------------------
    def set_pose(self, p: dict) -> None:
        self.pose = dict(p)
        f = self.facing()
        o, xr, yr = (d.get_center() for d in self._ref)
        ex, ey = (xr - o) / 0.1, (yr - o) / 0.1

        def W(q):
            return o + q[0] * ex + (q[1] - 0.5) * ey

        def d(a):                               # a direction at an angle from down, toward the face
            return np.array([f * math.sin(a), -math.cos(a)])

        D = self.D
        lean = p["lean"]
        up = np.array([f * math.sin(lean), math.cos(lean)])
        hip = np.array([0.0, D["HIP"] - p["drop"] + p["bob"] + p.get("breath", 0.0) * 0.4])
        sh = hip + (D["TORSO"] + p.get("breath", 0.0)) * up
        nod = lean + p.get("nod", 0.0)
        hup = np.array([f * math.sin(nod), math.cos(nod)])
        neck_top = sh + D["NECK"] * up
        head = neck_top + D["HEAD"] * 0.92 * hup + np.array([0.0, D.get("FACE_UP", 0.0)])
        ca_, sa_ = math.cos(-f * lean), math.sin(-f * lean)

        def off(v):                             # a point on the body (x toward the face), turned with its lean
            x, y = v[0] * f, v[1]
            return np.array([ca_ * x - sa_ * y, sa_ * x + ca_ * y])
        hf, hb = hip + off(self.hips[0]), hip + off(self.hips[1])
        sf, sb = sh + off(self.shoulders[0]), sh + off(self.shoulders[1])

        def seg(pair, a, b):
            if np.linalg.norm(a - b) > 1e-4:
                for m in pair:
                    m.put_start_and_end_on(W(a), W(b))

        fk, bk = hf + D["THIGH"] * d(p["fl1"]), hb + D["THIGH"] * d(p["bl1"])
        ff_, bf_ = fk + D["SHIN"] * d(p["fl2"]), bk + D["SHIN"] * d(p["bl2"])
        seg(self.legs["fl"], hf, fk)
        seg(self.legs["fs"], fk, ff_)
        seg(self.legs["bl"], hb, bk)
        seg(self.legs["bs"], bk, bf_)
        fe, be = sf + D["UPPER"] * d(p["fa1"]), sb + D["UPPER"] * d(p["ba1"])
        fh, bh = fe + D["FORE"] * d(p["fa2"]), be + D["FORE"] * d(p["ba2"])
        seg(self.arms["fa"], sf, fe)
        seg(self.arms["ff"], fe, fh)
        seg(self.arms["ba"], sb, be)
        seg(self.arms["bf"], be, bh)
        seg((self.neck,), sh, head)
        turn = max(-1.0, min(1.0, p["face"]))
        face = head + 0.045 * turn * np.array([math.cos(nod), -f * math.sin(nod)])
        # each rigid part's place and turn in the body's frame (mirrored to face the way it looks)
        parts = {"ground": (np.array([0.0, 0.0]), 0.0), "torso": (hip, -f * lean), "head": (head, -f * nod),
                 "face": (face, -f * nod), "foot_f": (ff_, 0.0), "foot_b": (bf_, 0.0), "hand_f": (fh, 0.0),
                 "hand_b": (bh, 0.0), "body": (hip, -f * lean)}
        frames = {}
        for name, (P, ang) in parts.items():
            ca, sa = math.cos(ang), math.sin(ang)
            g = 1.0 if name == "body" else f        # a country's shape is never turned over (east stays east)
            frames[name] = (P, np.array([[ca * g, -sa], [sa * g, ca]]))
        for x, base, part in self.rigid:
            P, M = frames[part]
            body = base @ M.T + P
            x.points = o + np.outer(body[:, 0], ex) + np.outer(body[:, 1] - 0.5, ey)
        self._pose_face(p, o, ex, ey, face, f, turn)
        self.hand.move_to(W(fh))
        self.hand_b.move_to(W(bh))


class Nation(Person):
    """A country as a character (as drawn in a margin): its real shape for a body, stick legs and arms, the same doodle
    face and every verb a person has: `ent fr nation France [color C] [mood FACE] [year 1500] [named | label "WORDS"] [tool T]
    [face left] [size H] at X,Y` (its feet there). Its shape is never turned over: east stays east as it turns."""

    D = {"HIP": 0.2, "TORSO": 0.27, "NECK": 0.0, "HEAD": 0.0, "UPPER": 0.14, "FORE": 0.13, "THIGH": 0.105,
         "SHIN": 0.095, "FACE_UP": 0.03}
    face_k = 1.7

    def __init__(self, country: str, mods: dict | None = None, c=None, size: float = 2.6):
        VGroup.__init__(self)
        import geo
        mods = mods or {}
        self.mods = mods
        seed = zlib.crc32(str(mods.get("_name", country)).encode())
        k = size / 1.8
        ink = col("ink")
        self.ow = ow = 2.4 * k
        fill = col(mods.get("color") or c) if (mods.get("color") or c) else \
            col(_pick(["coral", "teal", "navy", "gold", "green", "sky", "red"], seed, "c"))
        self.skin, self.cloth = fill, fill
        self.rigid = []
        self.rest = dict(REST)
        self.rest.update(fa1=0.35, fa2=0.25, ba1=-0.35, ba2=-0.25, fl1=0.04, fl2=0.0, bl1=-0.04, bl2=0.0)
        self.rest.update(MOODS.get(str(mods.get("mood") or "happy").lower(), MOODS["happy"]))
        self.alpha_now = 1.0

        def rigid(m, part):
            for x in m.family_members_with_points():
                self.rigid.append((x, x.points[:, :2].copy(), part))
            return m

        # the body: the country's shape (its main land and what lies near it), fitted to the body's box
        year = mods.get("year")
        g, self.country = geo.shape(country, int(year) if year else None)
        g = geo._biggest(g)
        parts = [p for p in getattr(g, "geoms", [g])]
        big = max(p.area for p in parts)
        parts = [p for p in parts if p.area > big * 0.02]
        lat = sum(p.centroid.y for p in parts) / len(parts)
        kx = math.cos(math.radians(lat))
        rings = [[(x * kx, y) for x, y in p.simplify(math.sqrt(big) / 90, preserve_topology=True).exterior.coords]
                 for p in parts]
        xs = [x for r in rings for x, _ in r]
        ys = [y for r in rings for _, y in r]
        bw, bh = 0.8, 0.62
        sc = min(bw / (max(xs) - min(xs)), bh / (max(ys) - min(ys)))
        cx, y0 = (max(xs) + min(xs)) / 2, min(ys)
        self.body_w = (max(xs) - min(xs)) * sc
        body = VGroup()
        for r in rings:
            pts = [np.array([(x - cx) * sc, (y - y0) * sc - 0.015, 0.0]) for x, y in r[:-1]]
            if len(pts) >= 3:
                m = VMobject(fill_color=fill, fill_opacity=1, stroke_color=ink, stroke_width=ow * 1.1)
                m.set_points_smoothly([*pts, pts[0]])
                body.add(m)
        self.hips = ((0.075, 0.0), (-0.075, 0.0))
        self.shoulders = ((self.body_w * 0.4, -0.06), (-self.body_w * 0.4, -0.06))
        self._stick_rig(body, mods, k, self.country)

    def _stick_rig(self, body, mods: dict, k: float, name: str) -> None:
        """Stick legs and arms in ink, round a body (a country's shape, a picture), the doodle face over it."""
        ink, ow, fill = col("ink"), self.ow, self.skin

        def rigid(m, part):
            for x in m.family_members_with_points():
                self.rigid.append((x, x.points[:, :2].copy(), part))
            return m

        # stick limbs, feet and hands in ink
        lw = 3.2 * k

        def stick():
            return (Line([0, 0, 0], [0, -0.1, 0], stroke_color=ink, stroke_width=lw),
                    Line([0, 0, 0], [0, -0.1, 0], stroke_color=ink, stroke_width=lw * 0.5))
        self.legs = {n: stick() for n in ("bl", "bs", "fl", "fs")}
        self.arms = {n: stick() for n in ("ba", "bf", "fa", "ff")}
        self.shoes = {n: rigid(Ellipse(width=0.075, height=0.028, fill_color=ink, fill_opacity=1, stroke_width=0)
                               .move_to([0.022, 0.012, 0]), "foot_" + n) for n in ("b", "f")}
        self.hands = {n: rigid(Circle(radius=0.014, fill_color=ink, fill_opacity=1, stroke_width=0), "hand_" + n)
                      for n in ("b", "f")}
        self.neck = Line([0, 0, 0], [0, 0.1, 0], stroke_opacity=0, stroke_width=0)
        self.head = rigid(Circle(radius=0.12, stroke_width=0, fill_opacity=0), "head")   # where words come from
        self.seat = None
        self.add(rigid(Ellipse(width=0.5, height=0.05, fill_color=ink, fill_opacity=0.12, stroke_width=0), "ground"))
        self.add(*self.legs["bl"], *self.legs["bs"], self.shoes["b"], *self.arms["ba"], *self.arms["bf"],
                 self.hands["b"], *self.legs["fl"], *self.legs["fs"], self.shoes["f"])
        self.add(rigid(body, "body"), self.neck, self.head)
        self._build_face(ink, ow, fill, ink, "none", mods)
        self.tool = _tool(str(mods.get("tool") or "").lower(), ink, ow, k)
        self.add(*self.arms["fa"], *self.arms["ff"])
        if self.tool is not None:
            self.add(rigid(self.tool, "hand_f"))
        self.add(self.hands["f"])
        if mods.get("named") or mods.get("label"):      # its name under its feet (`named`, or `label "WORDS"`)
            from look import label
            words = mods["label"] if isinstance(mods.get("label"), str) else name
            t = label(str(words), 0.05, "ink").move_to([0.0, -self.D["HIP"] - 0.05, 0])
            self.add(rigid(t, "body"))          # (never turned over: it reads as it faces either way)
        self.hand = Dot(radius=0.001).set_opacity(0)
        self.hand_b = Dot(radius=0.001).set_opacity(0)
        self.offhand_m = getattr(self, "offhand_m", None)
        self._ref = VGroup(*(Dot([x, y, 0], radius=0.001).set_opacity(0) for x, y in ((0, 0.5), (0.1, 0.5), (0, 0.6))))
        self.add(self.hand, self.hand_b, self._ref)
        self.pose = dict(self.rest)
        self.pose["face"] = -1.0 if mods.get("face") == "left" else 1.0
        self.set_pose(self.pose)


class Critter(Nation):
    """A thing come alive (`pic "a teapot" alive`): its picture for a body, stick legs and arms, the doodle face on it,
    and every verb a person has. The picture is never turned over."""

    face_k = 2.3

    def __init__(self, pic, mods: dict | None = None, size: float = 2.6):
        VGroup.__init__(self)
        mods = mods or {}
        self.mods = mods
        k = size / 1.8
        self.ow = 2.4 * k
        self.skin = self.cloth = col("card")
        self.rigid = []
        self.rest = dict(REST)
        self.rest.update(fa1=0.35, fa2=0.25, ba1=-0.35, ba2=-0.25, fl1=0.04, fl2=0.0, bl1=-0.04, bl2=0.0)
        self.rest.update(MOODS.get(str(mods.get("mood") or "happy").lower(), MOODS["happy"]))
        self.alpha_now = 1.0
        # the picture fitted to the body's box (its foot on the hips), what shows of it measured (a cut-out's margin)
        fx, fy = getattr(pic, "shown", (1.0, 1.0))
        w, h = pic.width * fx, pic.height * fy
        sc = min(0.72 / w, 0.72 / h)
        pic.scale(sc)
        w, h = w * sc, h * sc
        pic.move_to([0.0, h / 2 - 0.02, 0.0])  # (its margin is even round it: what shows stands on the hips)
        self.body_w = w
        self.D = dict(Nation.D, TORSO=0.48 * h, FACE_UP=0.05 * h)
        self.hips = ((0.08 * min(1.0, w / 0.4), 0.0), (-0.08 * min(1.0, w / 0.4), 0.0))
        self.shoulders = ((w * 0.46, -0.1 * h), (-w * 0.46, -0.1 * h))
        self._stick_rig(pic, mods, k, str(mods.get("_name", "")))

    # (a picture is no VMobject: taken as any Mobject is)
    def add(self, *mobjects):
        return Mobject.add(self, *mobjects)

    def _assert_valid_submobjects(self, submobjects):
        return Mobject._assert_valid_submobjects_internal(self, submobjects, Mobject)

    def get_points_defining_boundary(self):
        return Mobject.get_points_defining_boundary(self)


def critter(pic, mods: dict, size: float) -> Critter:
    size = size or 2.6
    m = Critter(pic, mods, size)
    m.scale(size, about_point=np.array([0.0, 0.0, 0.0]))
    return m


def nation(country: str, mods: dict, size: float, c=None) -> Nation:
    size = size or 2.6
    n = Nation(country, mods, c, size)
    n.scale(size, about_point=np.array([0.0, 0.0, 0.0]))
    return n


# ---------------------------------------------------------------- clothes --------------------------------------------

# What each kind of clothes is: its hem (below the hip, in body units), how wide it is there and at the waist, the
# colour of the sleeves and legs ("skin": bare), and its own colour when none is said (None: one picked).
WEAR = {
    "shirt": dict(hem=-0.02, hw=0.066, ww=0.064, arms=None, legs="navy", color=None),
    "vest": dict(hem=-0.02, hw=0.066, ww=0.064, arms="#F3EEE4", legs="navy", color=None),
    "tunic": dict(hem=-0.15, hw=0.105, ww=0.066, arms=None, legs="#7E7466", color=None),
    "robe": dict(hem=-0.35, hw=0.13, ww=0.072, arms=None, legs="skin", color="#8C6E52"),
    "habit": dict(hem=-0.36, hw=0.13, ww=0.074, arms=None, legs="skin", color="#5E4B3C"),
    "dress": dict(hem=-0.22, hw=0.17, ww=0.056, arms="skin", legs="skin", color=None),
    "gown": dict(hem=-0.37, hw=0.19, ww=0.056, arms=None, legs="skin", color=None),
    "coat": dict(hem=-0.2, hw=0.1, ww=0.072, arms=None, legs="#3A3631", color=None),
    "suit": dict(hem=-0.06, hw=0.074, ww=0.068, arms=None, legs=None, color="#2F3B4C"),
    "armor": dict(hem=-0.11, hw=0.095, ww=0.07, arms="#8E969C", legs="#8E969C", color="#A7AEB3"),
    "apron": dict(hem=-0.02, hw=0.066, ww=0.064, arms=None, legs="#4A4238", color=None),
    "toga": dict(hem=-0.34, hw=0.13, ww=0.074, arms="skin", legs="skin", color="#F3EEE4"),
    "uniform": dict(hem=-0.08, hw=0.08, ww=0.07, arms=None, legs="#2F3B4C", color="#B83227"),
    "lab": dict(hem=-0.22, hw=0.1, ww=0.072, arms="#F7F5F0", legs="#3A3631", color="#F7F5F0"),
    "overalls": dict(hem=-0.02, hw=0.066, ww=0.064, arms=None, legs="#3E5C82", color="#E9D5A8"),
}


def _garment(wear: str, spec: dict, cloth, ink, ow, skin) -> VGroup:
    T = TORSO
    sw, ww, hw, hem = 0.078, spec["ww"], spec["hw"], spec["hem"]
    wy = 0.06 if hem < -0.05 else 0.1
    from manim import Polygon
    body = Polygon(*(np.array([x, y, 0.0]) for x, y in ((-sw, T - 0.005), (sw, T - 0.005), (ww, wy), (hw, hem),
                                                        (-hw, hem), (-ww, wy))),
                   fill_color=cloth, fill_opacity=1, stroke_color=ink, stroke_width=ow)
    _round(body, 0.025)
    g = VGroup(body)
    line = lambda pts, c=ink, w=ow: _stroke(pts, c, w)  # noqa: E731
    dark = _shade(cloth, 0.72)
    if wear in ("shirt", "vest", "apron", "overalls"):
        g.add(line([(-0.03, T - 0.005), (0.0, T - 0.05), (0.03, T - 0.005)]))         # a collar
    if wear == "vest":
        g.add(_poly([(0.012, T - 0.03), (sw - 0.008, T - 0.01), (ww, 0.0), (0.012, -0.0)], dark, ink, ow),
              _poly([(-0.012, T - 0.03), (-sw + 0.008, T - 0.01), (-ww, 0.0), (-0.012, -0.0)], dark, ink, ow))
    if wear in ("tunic", "robe", "habit", "uniform", "armor"):
        belt = {"habit": "#E2D3B0", "robe": _shade(cloth, 0.6), "armor": "#5B4A3A"}.get(wear, "#4A3A2C")
        g.add(_poly([(-ww - 0.004, 0.035), (ww + 0.004, 0.035), (ww + 0.004, 0.06), (-ww - 0.004, 0.06)], belt, ink, ow))
        if wear == "habit":                     # a rope belt's ends hanging
            g.add(line([(0.03, 0.04), (0.035, -0.08), (0.03, -0.12)], "#E2D3B0", ow * 1.8))
    if wear in ("coat", "lab", "suit", "uniform"):
        g.add(line([(0.0, T - 0.04), (0.0, hem + 0.01)], ink, ow * 0.8))
    if wear == "coat" or wear == "uniform":
        for y in (0.17, 0.11, 0.05) if wear == "coat" else (0.18, 0.13, 0.08, 0.02):
            for x in ((0.02,) if wear == "coat" else (-0.022, 0.022)):
                g.add(Dot([x, y, 0], radius=0.009, color="#F2C14E" if wear == "uniform" else ink))
    if wear == "uniform":                       # epaulettes
        for s in (-1, 1):
            g.add(_poly([(s * 0.04, T + 0.003), (s * 0.088, T + 0.003), (s * 0.088, T - 0.015), (s * 0.04, T - 0.015)],
                        "#F2C14E", ink, ow * 0.7))
    if wear == "suit":
        g.add(_poly([(-0.028, T - 0.005), (0.028, T - 0.005), (0.0, T - 0.11)], "#F7F5F0", ink, ow * 0.7),
              _poly([(0.0, T - 0.03), (0.012, T - 0.05), (0.0, T - 0.12), (-0.012, T - 0.05)], "#B83227", ink, ow * 0.6))
    if wear == "lab":
        g.add(_poly([(0.025, 0.12), (0.06, 0.12), (0.06, 0.08), (0.025, 0.08)], cloth, ink, ow * 0.7))
    if wear == "apron":
        g.add(_poly([(-0.05, T - 0.08), (0.05, T - 0.08), (0.065, -0.16), (-0.065, -0.16)], "#F3EEE4", ink, ow),
              line([(-0.035, T - 0.08), (0.0, T - 0.01), (0.035, T - 0.08)], ink, ow * 0.8))
    if wear == "overalls":
        g.add(_poly([(-0.045, T - 0.085), (0.045, T - 0.085), (0.06, -0.02), (-0.06, -0.02)], "#3E5C82", ink, ow),
              Dot([-0.03, T - 0.1, 0], radius=0.008, color="#F2C14E"), Dot([0.03, T - 0.1, 0], radius=0.008, color="#F2C14E"))
    if wear == "toga":                          # a sash from the shoulder across
        g.add(_poly([(-sw + 0.01, T), (-sw + 0.05, T), (hw - 0.01, hem + 0.12), (hw - 0.04, hem + 0.06)],
                    "#B83227", ink, ow * 0.8))
    if wear == "armor":                         # plates and rivets
        for y in (0.2, 0.14, 0.08):
            g.add(line([(-ww + 0.01, y), (0.0, y - 0.012), (ww - 0.01, y)], ink, ow * 0.7))
        for x in (-0.04, 0.0, 0.04):
            g.add(line([(x, -0.0), (x * 1.3, hem + 0.01)], ink, ow * 0.6))
    if wear in ("dress", "gown"):
        g.add(line([(-ww, wy), (0.0, wy - 0.012), (ww, wy)], dark, ow * 1.6))
    return g


def _round(m, r) -> None:
    try:
        m.round_corners(r)
    except Exception:  # noqa: BLE001 -- a plain VMobject (no corners to round): as it is
        pass


def _lighter(hex_colour: str, k: float) -> str:
    """A colour mixed toward white (a near arm lifted off the body behind it)."""
    h = hex_colour.lstrip("#")
    if len(h) != 6:
        return hex_colour
    return "#%02X%02X%02X" % tuple(int(int(h[i:i + 2], 16) + (255 - int(h[i:i + 2], 16)) * k) for i in (0, 2, 4))


def _shade(hex_colour: str, k: float) -> str:
    h = hex_colour.lstrip("#")
    if len(h) != 6:
        return hex_colour
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(min(255, int(v * k)) for v in (r, g, b))


# ---------------------------------------------------------------- hair, face, beard ----------------------------------

def _hair(style: str, hair, ink, ow, R):
    """Hair behind the head and over it, in the head's frame (x toward the face, the head's centre at 0)."""
    back, front = VGroup(), VGroup()
    if style in ("none", "bald", ""):
        if style == "bald":                     # a fringe round the back
            back.add(_blob(_arc(-0.01, 0.0, R * 1.04, 120, 230, 10) + _arc(-0.01, 0.0, R * 0.8, 230, 120, 10),
                           hair, ink, ow))
        return back, front
    cap = _arc(0.0, 0.0, R * 1.07, 25, 205, 18) + [(-R * 0.82, R * -0.05), (-R * 0.5, R * 0.35), (R * 0.05, R * 0.55),
                                                    (R * 0.55, R * 0.62)]
    if style == "spiky":
        pts = []
        for i, a in enumerate(np.linspace(20, 205, 13)):
            r = R * (1.32 if i % 2 else 1.04)
            pts.append((r * math.cos(math.radians(a)), r * math.sin(math.radians(a))))
        front.add(_poly(pts + [(-R * 0.82, -R * 0.05), (-R * 0.4, R * 0.4), (R * 0.4, R * 0.62)], hair, ink, ow))
        return back, front
    if style == "curly":
        for a in np.linspace(15, 215, 9):
            x, y = R * 0.98 * math.cos(math.radians(a)), R * 0.98 * math.sin(math.radians(a))
            front.add(Circle(radius=R * 0.36, fill_color=hair, fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.8)
                      .move_to([x, y, 0]))
        return back, front
    front.add(_blob(cap, hair, ink, ow))
    if style in ("long", "bob"):
        low = -1.75 if style == "long" else -0.95
        back.add(_blob([(-R * 0.2, R * 1.0), (-R * 1.1, R * 0.7), (-R * 1.28, -R * 0.2), (-R * 1.18, R * low),
                        (-R * 0.3, R * low - 0.01), (R * 0.2, R * (low * 0.5)), (R * 0.4, R * 0.4)], hair, ink, ow))
    elif style == "bun":
        back.add(Circle(radius=R * 0.42, fill_color=hair, fill_opacity=1, stroke_color=ink, stroke_width=ow)
                 .move_to([-R * 0.82, R * 0.72, 0]))
    elif style == "ponytail":
        back.add(_blob([(-R * 0.8, R * 0.55), (-R * 1.45, R * 0.2), (-R * 1.6, -R * 0.9), (-R * 1.3, -R * 1.3),
                        (-R * 1.15, -R * 0.4), (-R * 0.85, R * 0.1)], hair, ink, ow))
    return back, front


def _beard(hair, ink, ow, R, long: bool) -> VMobject:
    low = -R * (1.75 if long else 1.15)
    return _blob([(-R * 0.62, -R * 0.05), (-R * 0.5, -R * 0.75), (-R * 0.05, low), (R * 0.55, -R * 0.85),
                  (R * 0.62, -R * 0.15), (R * 0.3, -R * 0.42), (0.0, -R * 0.48), (-R * 0.3, -R * 0.42)], hair, ink, ow)


def _face(mood: str, ink, ow, R) -> VGroup:
    """What the face shows that does not move (the eyes, brows and mouth are posed: Person.set_pose): its cheeks."""
    g = VGroup()
    for s in (-1, 1):                           # cheeks
        g.add(Circle(radius=0.016, fill_color="#E58B7B", fill_opacity=0.35, stroke_width=0).move_to([s * 0.045, -0.028, 0]))
    return g


# ---------------------------------------------------------------- hats -----------------------------------------------

def _hat(kind: str, ink, ow, R, cloth):
    """A hat in the head's frame: (what goes behind the head, what goes over it)."""
    back, front = VGroup(), VGroup()
    top = R * 0.72
    if not kind:
        return back, front
    more = attire.hat(kind, ink, ow, R, cloth)
    if more is not None:
        return more
    if kind == "top":
        front.add(_poly([(-0.07, top), (0.07, top), (0.075, top + 0.17), (-0.075, top + 0.17)], ink, ink, ow),
                  _poly([(-0.071, top + 0.01), (0.071, top + 0.01), (0.072, top + 0.04), (-0.072, top + 0.04)], "#B83227", ink, ow * 0.5),
                  Ellipse(width=0.25, height=0.035, fill_color=ink, fill_opacity=1, stroke_width=0).move_to([0, top, 0]))
    elif kind == "bowler":
        front.add(_blob(_arc(0, top, 0.095, 0, 180, 14), ink, ink, ow),
                  Ellipse(width=0.24, height=0.034, fill_color=ink, fill_opacity=1, stroke_width=0).move_to([0, top, 0]))
    elif kind == "cap":
        c = cloth if cloth else col("coral")
        front.add(_blob(_arc(-0.005, top - 0.03, 0.118, 0, 180, 16), c, ink, ow),
                  Ellipse(width=0.13, height=0.03, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow).move_to([0.115, top - 0.025, 0]),
                  Dot([0, top + 0.088, 0], radius=0.01, color=ink))
    elif kind == "beret":
        front.add(Ellipse(width=0.27, height=0.08, fill_color="#B83227", fill_opacity=1, stroke_color=ink, stroke_width=ow)
                  .rotate(0.18).move_to([-0.02, top + 0.02, 0]),
                  Line([-0.02, top + 0.06, 0], [-0.01, top + 0.085, 0], stroke_color=ink, stroke_width=ow * 1.5))
    elif kind in ("straw", "cowboy"):
        c = "#E2C27A" if kind == "straw" else "#8A5A36"
        brim = (Ellipse(width=0.38, height=0.055, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow).move_to([0, top - 0.005, 0])
                if kind == "straw" else _blob([(-0.2, top + 0.03), (-0.1, top - 0.015), (0.1, top - 0.015), (0.2, top + 0.03),
                                               (0.12, top + 0.005), (-0.12, top + 0.005)], c, ink, ow))
        crown = _blob([(-0.08, top), (-0.075, top + 0.085), (0.0, top + 0.07 if kind == "cowboy" else top + 0.095),
                       (0.075, top + 0.085), (0.08, top)], c, ink, ow)
        band = _poly([(-0.079, top + 0.008), (0.079, top + 0.008), (0.078, top + 0.028), (-0.078, top + 0.028)],
                     "#B83227" if kind == "straw" else "#3A2A1E", ink, ow * 0.5)
        front.add(crown, band, brim)
    elif kind == "crown":
        pts = [(-0.085, top - 0.01), (0.085, top - 0.01), (0.095, top + 0.1), (0.05, top + 0.045), (0.0, top + 0.115),
               (-0.05, top + 0.045), (-0.095, top + 0.1)]
        front.add(_poly(pts, "#F2C14E", ink, ow), *(Dot([x, top + 0.02, 0], radius=0.011, color="#B83227") for x in (-0.045, 0, 0.045)))
    elif kind == "helmet":
        front.add(_poly(_arc(0, R * 0.15, R * 1.12, 0, 180, 22), "#A7AEB3", ink, ow),
                  _poly([(-R * 1.16, R * 0.08), (R * 1.16, R * 0.08), (R * 1.16, R * 0.22), (-R * 1.16, R * 0.22)],
                        "#8E969C", ink, ow * 0.8),
                  _poly([(R * 0.62, -R * 0.42), (R * 0.76, -R * 0.42), (R * 0.76, R * 0.12), (R * 0.62, R * 0.12)],
                        "#8E969C", ink, ow * 0.7))
    elif kind == "tricorn":
        front.add(_blob([(-0.17, top + 0.02), (-0.06, top - 0.01), (0.14, top), (0.2, top + 0.06), (0.06, top + 0.12),
                         (-0.1, top + 0.11)], ink, ink, ow),
                  _stroke([(-0.13, top + 0.04), (0.0, top + 0.03), (0.15, top + 0.05)], "#F2C14E", ow))
    elif kind == "mitre":
        front.add(_blob([(-0.075, top), (0.075, top), (0.07, top + 0.13), (0.0, top + 0.22), (-0.07, top + 0.13)],
                        "#F7F5F0", ink, ow),
                  _poly([(-0.012, top), (0.012, top), (0.012, top + 0.2), (-0.012, top + 0.2)], "#F2C14E", ink, ow * 0.5))
    elif kind == "turban":
        front.add(_blob([(-R * 1.08, R * 0.1), (-R * 1.05, R * 0.95), (0.0, R * 1.45), (R * 1.05, R * 0.95), (R * 1.08, R * 0.25),
                         (R * 0.4, R * 0.42), (-R * 0.4, R * 0.42)], "#F3EEE4", ink, ow),
                  _stroke([(-R * 0.95, R * 0.55), (0.0, R * 1.05), (R * 0.95, R * 0.7)], "#C9BEA8", ow),
                  Dot([R * 0.55, R * 0.62, 0], radius=0.014, color="#B83227"))
    elif kind in ("hood", "veil", "headscarf"):
        c = {"hood": _shade(cloth, 0.85) if cloth else "#5E4B3C", "veil": "#22201E", "headscarf": "#2E7D74"}[kind]
        low = {"hood": -R * 1.6, "veil": -R * 2.3, "headscarf": -R * 1.1}[kind]
        back.add(_blob([(R * 0.35, R * 1.25), (-R * 0.7, R * 1.3), (-R * 1.45, R * 0.4), (-R * 1.45, low),
                        (R * 0.2, low + 0.02), (R * 0.75, -R * 0.6), (R * 1.25, R * 0.3)], c, ink, ow))
        front.add(_blob(_arc(0, 0, R * 1.18, 15, 190, 16) + [(-R * 0.9, R * 0.15), (0.0, R * 0.62), (R * 0.85, R * 0.35)],
                        c, ink, ow))
        if kind == "veil":
            front.add(_blob([(-R * 0.85, R * 0.32), (0.0, R * 0.78), (R * 0.95, R * 0.42), (R * 0.9, R * 0.22),
                             (0.0, R * 0.55), (-R * 0.85, R * 0.12)], "#F7F5F0", ink, ow * 0.7))
    elif kind == "chef":
        front.add(_poly([(-0.07, top), (0.07, top), (0.07, top + 0.06), (-0.07, top + 0.06)], "#F7F5F0", ink, ow),
                  *(Circle(radius=0.055, fill_color="#F7F5F0", fill_opacity=1, stroke_color=ink, stroke_width=ow)
                    .move_to([x, top + 0.1 + y, 0]) for x, y in ((-0.05, 0.0), (0.05, 0.0), (0.0, 0.035))))
    elif kind == "hardhat":
        front.add(_blob(_arc(0, top - 0.04, 0.12, 0, 180, 16), "#F2C14E", ink, ow),
                  Ellipse(width=0.29, height=0.035, fill_color="#F2C14E", fill_opacity=1, stroke_color=ink,
                          stroke_width=ow).move_to([0.01, top - 0.04, 0]),
                  _stroke([(0, top - 0.04), (0, top + 0.08)], ink, ow * 0.7))
    elif kind == "wreath":
        for a in np.linspace(25, 200, 9):
            x, y = R * 1.0 * math.cos(math.radians(a)), R * 1.0 * math.sin(math.radians(a))
            front.add(Ellipse(width=0.05, height=0.025, fill_color="#5B8C3A", fill_opacity=1, stroke_color=ink,
                              stroke_width=ow * 0.5).rotate(math.radians(a + 90)).move_to([x, y, 0]))
    return back, front


# ---------------------------------------------------------------- what a hand holds ----------------------------------

def _tool(kind: str, ink, ow, k):
    """A thing held in the front hand, in the hand's frame (the grip at 0, x toward the face)."""
    if not kind:
        return None
    more = attire.tool(kind, ink, ow, k)
    if more is not None:
        return more
    wood, metal, gold = "#9A6B43", "#B8BEC2", "#F2C14E"
    stick = lambda y0, y1, c=wood, w=4.0: Line([0, y0, 0], [0, y1, 0], stroke_color=c, stroke_width=w * k)  # noqa: E731
    if kind == "book":
        return VGroup(_poly([(-0.01, -0.05), (0.08, -0.05), (0.08, 0.07), (-0.01, 0.07)], "#B83227", ink, ow),
                      _poly([(0.065, -0.045), (0.075, -0.045), (0.075, 0.065), (0.065, 0.065)], "#F7F5F0", ink, ow * 0.4))
    if kind == "scroll":
        return VGroup(_poly([(-0.02, -0.07), (0.03, -0.07), (0.03, 0.08), (-0.02, 0.08)], "#EFE1BE", ink, ow),
                      Ellipse(width=0.06, height=0.02, fill_color="#D9C49A", fill_opacity=1, stroke_color=ink, stroke_width=ow).move_to([0.005, 0.08, 0]),
                      Ellipse(width=0.06, height=0.02, fill_color="#D9C49A", fill_opacity=1, stroke_color=ink, stroke_width=ow).move_to([0.005, -0.07, 0]))
    if kind == "quill":
        return VGroup(_blob([(0.0, -0.01), (0.03, 0.06), (0.05, 0.16), (0.02, 0.12), (0.005, 0.05)], "#F7F5F0", ink, ow),
                      Line([0, -0.01, 0], [-0.008, -0.04, 0], stroke_color=ink, stroke_width=ow * 1.5))
    if kind == "coin":
        return VGroup(Circle(radius=0.035, fill_color=gold, fill_opacity=1, stroke_color=ink, stroke_width=ow).move_to([0.02, 0.02, 0]))
    if kind == "bag":
        return VGroup(_blob([(-0.04, -0.03), (-0.055, -0.1), (0.0, -0.13), (0.055, -0.1), (0.04, -0.03), (0.0, -0.015)],
                            "#C9A66B", ink, ow),
                      _stroke([(-0.02, -0.025), (0.02, -0.025)], ink, ow * 1.5))
    if kind == "sword":                         # held up and forward, away from the face
        return VGroup(_poly([(-0.009, 0.04), (0.009, 0.04), (0.007, 0.3), (0.0, 0.33), (-0.007, 0.3)], metal, ink, ow),
                      _poly([(-0.045, 0.03), (0.045, 0.03), (0.045, 0.045), (-0.045, 0.045)], gold, ink, ow * 0.7),
                      stick(-0.03, 0.03, "#5B4A3A", 3.5)).rotate(-0.75, about_point=np.zeros(3))
    if kind == "shield":
        return VGroup(_blob([(0.0, 0.11), (0.09, 0.09), (0.085, -0.04), (0.04, -0.12), (-0.005, -0.04)], "#2F3B4C", ink, ow),
                      _stroke([(0.045, 0.09), (0.045, -0.09)], gold, ow * 1.8), _stroke([(0.005, 0.03), (0.085, 0.03)], gold, ow * 1.8))
    if kind == "staff":
        return VGroup(stick(-0.28, 0.32), Circle(radius=0.022, fill_color=wood, fill_opacity=1, stroke_color=ink,
                                                  stroke_width=ow).move_to([0, 0.33, 0]))
    if kind == "spear":
        return VGroup(stick(-0.28, 0.36), _poly([(-0.02, 0.35), (0.02, 0.35), (0.0, 0.44)], metal, ink, ow))
    if kind == "flag":
        return VGroup(stick(-0.05, 0.66, ink, 2.6), _blob([(0.0, 0.66), (0.1, 0.64), (0.2, 0.65), (0.19, 0.55),
                                                           (0.1, 0.54), (0.0, 0.55)], "#B83227", ink, ow))
    if kind == "sign":
        return VGroup(stick(-0.05, 0.3), _poly([(-0.14, 0.27), (0.14, 0.27), (0.14, 0.42), (-0.14, 0.42)], "#F7F5F0", ink, ow))
    if kind == "hammer":
        return VGroup(stick(-0.04, 0.15), _poly([(-0.035, 0.14), (0.06, 0.14), (0.06, 0.19), (-0.035, 0.19)], "#5A5F63", ink, ow))
    if kind == "pickaxe":
        return VGroup(stick(-0.06, 0.2), _blob([(-0.11, 0.15), (0.0, 0.215), (0.11, 0.15), (0.0, 0.19)], metal, ink, ow))
    if kind == "torch":
        return VGroup(stick(-0.05, 0.12, "#6B4A2F", 4.5),
                      _blob([(-0.03, 0.12), (-0.02, 0.18), (0.0, 0.24), (0.02, 0.18), (0.03, 0.12)], "#E4572E", ink, ow * 0.6),
                      _blob([(-0.014, 0.125), (0.0, 0.2), (0.014, 0.125)], gold, gold, 0))
    if kind == "lantern":
        return VGroup(_stroke([(0, 0.0), (0, -0.03)], ink, ow),
                      _poly([(-0.035, -0.03), (0.035, -0.03), (0.035, -0.11), (-0.035, -0.11)], "#FBE7A1", ink, ow),
                      _poly([(-0.045, -0.025), (0.045, -0.025), (0.0, 0.0)], ink, ink, ow))
    if kind == "basket":
        return VGroup(_stroke(_arc(0.0, -0.06, 0.06, 20, 160, 8), "#9A6B43", ow * 1.6),
                      _blob([(-0.08, -0.06), (0.08, -0.06), (0.06, -0.13), (-0.06, -0.13)], "#C9A66B", ink, ow),
                      _stroke([(-0.07, -0.09), (0.07, -0.09)], "#9A6B43", ow))
    if kind == "cane":
        return VGroup(stick(-0.3, 0.0, "#6B4A2F", 3.5),
                      _stroke(_arc(0.03, 0.0, 0.03, 180, 0, 8), "#6B4A2F", 3.5 * k))
    if kind == "pointer":
        return VGroup(Line([0, 0, 0], [0.32, 0.2, 0], stroke_color=wood, stroke_width=2.6 * k),
                      Dot([0.32, 0.2, 0], radius=0.012, color="#B83227"))
    if kind == "briefcase":
        return VGroup(_poly([(-0.07, -0.04), (0.07, -0.04), (0.07, -0.14), (-0.07, -0.14)], "#6B4A2F", ink, ow),
                      _stroke(_arc(0, -0.04, 0.025, 0, 180, 6), ink, ow * 1.4))
    return VGroup(_poly([(-0.01, -0.05), (0.08, -0.05), (0.08, 0.07), (-0.01, 0.07)], "#B83227", ink, ow))  # a book


# ---------------------------------------------------------------- the peg figure -------------------------------------
# The default figure (V3_FIGURE=peg; `style stick` for the jointed one): a peg doll, as history explainers draw
# people: a big round head over a rounded body, the clothes painted on it, thin ink arms, no legs (it waddles and
# hops as it walks), the same doodle face and every verb.

FIGURE = os.environ.get("V3_FIGURE", "peg").strip().lower()
# hats that hide the hair
COVERED = ("hood", "veil", "headscarf", "turban", "helmet", "greathelm", "kettle", "legion", "viking", "wimple",
           "coif", "nemes", "pagdi", "pagdi_white", "mughal", "pallu", "wig", "jester", "pith", "topknot")


class Peg(Person):
    D = {"HIP": 0.03, "TORSO": 0.5, "NECK": 0.0, "HEAD": 0.2, "UPPER": 0.12, "FORE": 0.11, "THIGH": 0.004,
         "SHIN": 0.004, "FACE_UP": -0.01}
    face_k = 1.75
    W = 0.37                                   # the body's width
    R = 0.205                                  # the head's radius

    def __init__(self, mods: dict | None = None, c=None, size: float = 2.6):
        VGroup.__init__(self)
        mods = attire.role(mods or {})
        self.mods = mods
        seed = zlib.crc32(str(mods.get("_name", "")).encode())
        k = size / 1.8
        ink = col("ink")
        self.ow = ow = 2.2 * k
        old = bool(mods.get("old"))
        skin = SKIN.get(str(mods.get("skin") or ""), None) or _pick(list(SKIN.values()), seed, "skin")
        hair_s, _, hair_c = str(mods.get("hair") or _pick(["short", "short", "bob", "curly", "long", "bun", "bald"],
                                                            seed, "hair")).partition("-")
        hair = HAIR.get(hair_c) or (HAIR["grey"] if old else _pick([HAIR["black"], HAIR["brown"], HAIR["brown"],
                                                                     HAIR["blonde"], HAIR["red"]], seed, "hc"))
        wear = str(mods.get("wear") or "shirt").lower()
        spec = WEAR.get(wear, WEAR["shirt"])
        cloth = col(mods.get("color") or c) if (mods.get("color") or c) else (
            spec["color"] if spec["color"] else col(_pick(["coral", "teal", "navy", "gold", "green", "sky"], seed, "c")))
        legs = skin if spec["legs"] == "skin" else (col(spec["legs"]) if spec["legs"] else cloth)
        self.skin, self.cloth = skin, cloth
        self.rigid = []
        decor = mods.get("decor") or {}
        self.rest = dict(REST)
        self.rest.update(fa1=0.32, fa2=0.22, ba1=-0.15, ba2=-0.08)    # the right arm a little out from the body
        self.rest.update(MOODS.get(str(mods.get("mood") or "happy").lower(), MOODS["happy"]))
        self.alpha_now = 1.0
        self.body_w = self.W
        if old:
            self.rest["lean"] = 0.08

        def rigid(m, part):
            for x in m.family_members_with_points():
                self.rigid.append((x, x.points[:, :2].copy(), part))
            return m

        self.add(rigid(Ellipse(width=0.46, height=0.06, fill_color=ink, fill_opacity=0.12, stroke_width=0), "ground"))
        self.seat = None
        if mods.get("seat"):
            wood = "#9A6B43"
            self.seat = rigid(VGroup(
                _poly([(-0.2, 0.11), (0.2, 0.11), (0.2, 0.15), (-0.2, 0.15)], wood, ink, ow),
                Line([-0.16, 0.11, 0], [-0.18, 0, 0], stroke_color=ink, stroke_width=ow * 2),
                Line([0.16, 0.11, 0], [0.18, 0, 0], stroke_color=ink, stroke_width=ow * 2)), "ground")
            self.add(self.seat)
        # no legs: the jointed figure's leg lines kept (the walk drives them) but never drawn
        nothing = lambda: (Line([0, 0, 0], [0, -0.01, 0], stroke_width=0, stroke_opacity=0),)  # noqa: E731
        self.legs = {n: nothing() for n in ("bl", "bs", "fl", "fs")}
        aw = 2.8 * k
        sleeve = skin if spec["arms"] == "skin" else (spec["arms"] or cloth)
        # sleeves: the cloth's colour over an ink line (an outlined arm), the far one a shade darker
        # (the near, right arm thicker and lighter, so it reads over the body; the far one darker, thinner)
        self.arms = {n: (Line([0, 0, 0], [0, -0.1, 0], stroke_color=ink, stroke_width=aw * (3.0 if n[0] == "f" else 2.3)),
                         Line([0, 0, 0], [0, -0.1, 0], stroke_color=_lighter(sleeve, 0.2) if n[0] == "f" else _shade(sleeve, 0.88),
                              stroke_width=aw * (1.9 if n[0] == "f" else 1.35))) for n in ("ba", "bf", "fa", "ff")}
        self.hands = {n: rigid(Circle(radius=0.029 if n == "f" else 0.022, fill_color=skin if n == "f" else _shade(skin, 0.92), fill_opacity=1,
                                      stroke_color=ink, stroke_width=ow * (1.0 if n == "f" else 0.8)), "hand_" + n)
                      for n in ("b", "f")}
        # shoes peeping from under the body (they hop with it)
        self.shoes = {n: rigid(Ellipse(width=0.1, height=0.045, fill_color=SHOE if n == "f" else _shade(SHOE, 1.25),
                                       fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.6)
                               .move_to([0.03, -0.02, 0]), "foot_" + n) for n in ("b", "f")}
        R = self.R
        hat = str(mods.get("hat") or "").lower()
        covered = hat in COVERED
        back, front = _hair(hair_s if not covered else "none", hair, ink, ow, R)
        hb, hf = _hat(hat, ink, ow, HEAD, cloth)
        hf.add(attire.plume(decor, ink, ow, HEAD))
        for g in (hb, hf):                      # hats are cut for the jointed figure's head: grown to this one
            g.scale(R / HEAD, about_point=np.zeros(3))
        self.hair_back = back
        self.add(rigid(hb, "head"), rigid(back, "head"))
        H = self.D["TORSO"] + 0.08
        self.add(rigid(attire.behind(decor, ink, ow, self.W, -0.035, H), "torso"))
        self.add(self.shoes["b"], self.shoes["f"])
        self.add(*self.arms["ba"], *self.arms["bf"])
        held = attire.offhand(str(decor.get("offhand") or ""), ink, ow, k)
        if held is None:
            self.add(self.hands["b"])
        self.torso_m = rigid(_peg_body(wear, spec, cloth, legs, ink, ow, skin, self.W, H), "torso")
        self.add(self.torso_m, rigid(attire.on_body(decor, ink, ow, self.W, -0.035, H), "torso"))
        self.neck = Line([0, 0, 0], [0, 0.1, 0], stroke_width=0, stroke_opacity=0)
        self.add(self.neck)
        self.head = Circle(radius=R, fill_color=skin, fill_opacity=1, stroke_color=ink, stroke_width=ow)
        self.add(rigid(self.head, "head"))
        # a little shading on the head's far side, and an ear
        self.add(rigid(_shade_side(R, _shade(skin, 0.9)), "head"))
        if not covered and hair_s not in ("long",):
            self.add(rigid(VGroup(Circle(radius=R * 0.2, fill_color=skin, fill_opacity=1, stroke_color=ink,
                                         stroke_width=ow * 0.8).move_to([-R * 0.82, -R * 0.08, 0]),
                                  Circle(radius=R * 0.09, fill_color=_shade(skin, 0.85), fill_opacity=1,
                                         stroke_width=0).move_to([-R * 0.8, -R * 0.08, 0])), "head"))
        self.add(rigid(front, "head"))
        if mods.get("beard") or mods.get("longbeard"):
            self.add(rigid(_beard(hair, ink, ow, R * 0.75, bool(mods.get("longbeard")) or old)
                           .shift(np.array([0.0, -R * 0.25, 0.0])), "face"))
        self._build_face(ink, ow, skin, hair, hair_s, mods)
        self.add(rigid(hf, "head"))
        self.tool = _tool(str(mods.get("tool") or ("cane" if old else "")).lower(), ink, ow, k)
        self.add(*self.arms["fa"], *self.arms["ff"])
        if self.tool is not None:
            self.add(rigid(self.tool, "hand_f"))
        self.add(self.hands["f"])
        if held is not None:                    # a shield (in the far hand, carried over the body: in front)
            self.add(self.hands["b"], rigid(held, "hand_b"))
        self.offhand_m = held
        self.hand = Dot(radius=0.001).set_opacity(0)
        self.hand_b = Dot(radius=0.001).set_opacity(0)
        self.offhand_m = getattr(self, "offhand_m", None)
        self._ref = VGroup(*(Dot([x, y, 0], radius=0.001).set_opacity(0) for x, y in ((0, 0.5), (0.1, 0.5), (0, 0.6))))
        self.add(self.hand, self.hand_b, self._ref)
        self.pose = dict(self.rest)
        self.pose["face"] = -1.0 if mods.get("face") == "left" else 1.0
        self.set_pose(self.pose)

    hips = ((0.06, 0.0), (-0.06, 0.0))
    shoulders = ((0.17, -0.13), (-0.17, -0.13))

    def set_pose(self, p: dict) -> None:
        """As a person's, but with no legs to walk on: the leg swing a walk gives becomes a rock from side to side
        and a little hop."""
        swing = p.get("fl1", 0.0) - REST["fl1"]
        q = dict(p)
        q["lean"] = p["lean"] + 0.16 * swing
        q["bob"] = p["bob"] + 0.035 * min(1.0, abs(swing) / 0.42)
        super().set_pose(q)
        self.pose = dict(p)

    def sit_target(self) -> dict:
        q = dict(REST)
        q.update(drop=-0.12 if self.seat is not None else 0.04, fa1=0.35, fa2=1.0, ba1=0.25, ba2=0.9, lean=-0.04)
        return q


def _shade_side(R, c):
    """A crescent of shade along the far side of a round head (the light from the front)."""
    pts = _arc(0, 0, R * 0.97, 110, 250, 14) + _arc(R * 0.22, 0, R * 0.86, 245, 115, 14)
    m = VMobject(fill_color=c, fill_opacity=0.55, stroke_width=0)
    m.set_points_smoothly([np.array([x, y, 0.0]) for x, y in pts] + [np.array([pts[0][0], pts[0][1], 0.0])])
    return m


def _peg_body(wear: str, spec: dict, cloth, legs, ink, ow, skin, W: float, H: float) -> VGroup:
    """A peg figure's body (the hips at 0, its foot a little under): the clothes painted on a rounded block."""
    from manim import RoundedRectangle
    y0 = -0.035
    full = H - y0
    body = RoundedRectangle(width=W, height=full, corner_radius=W * 0.32, fill_color=cloth, fill_opacity=1,
                            stroke_width=0).move_to([0, (H + y0) / 2, 0])
    g = VGroup(body)
    dark = _shade(cloth, 0.72)
    # shade down the far side, a light down the near one (a rounded body, lit from the front)
    side = VMobject(fill_color=_shade(cloth, 0.84), fill_opacity=0.75, stroke_width=0)
    side.set_points_smoothly([np.array([x, y, 0.0]) for x, y in (
        (-W / 2 + 0.004, y0 + full * 0.22), (-W / 2 + 0.01, H - full * 0.2), (-W / 2 + 0.055, H - full * 0.12),
        (-W / 2 + 0.07, H - full * 0.3), (-W / 2 + 0.065, y0 + full * 0.25), (-W / 2 + 0.03, y0 + full * 0.08),
        (-W / 2 + 0.004, y0 + full * 0.22))])
    g.add(side, _stroke([(W / 2 - 0.045, H - full * 0.22), (W / 2 - 0.035, H - full * 0.45)], "#FFFFFF", ow * 1.1)
          .set_stroke(opacity=0.35))
    line = lambda pts, c=ink, w=ow: _stroke(pts, c, w)  # noqa: E731
    long_ = wear in ("dress", "gown", "robe", "habit", "toga", "tunic")
    if not long_ and legs != cloth:             # trousers below the waist
        band = RoundedRectangle(width=W, height=full * 0.38, corner_radius=W * 0.12, fill_color=legs, fill_opacity=1,
                                stroke_width=0).move_to([0, y0 + full * 0.19, 0])
        g.add(band, line([(-W / 2 + 0.01, y0 + full * 0.38), (W / 2 - 0.01, y0 + full * 0.38)], _shade(legs, 0.7), ow * 0.8),
              line([(0.0, y0 + 0.01), (0.0, y0 + full * 0.3)], _shade(legs, 0.6), ow * 0.6))
    top = H - 0.02
    if wear in ("shirt", "suit", "coat", "uniform", "lab", "vest", "overalls", "apron"):
        g.add(_poly([(-0.07, top), (0.0, top - 0.08), (-0.025, top + 0.005)], "#F7F5F0", ink, ow * 0.6),
              _poly([(0.07, top), (0.0, top - 0.08), (0.025, top + 0.005)], "#F7F5F0", ink, ow * 0.6))
    if wear == "suit":
        g.add(_poly([(0.0, top - 0.07), (0.016, top - 0.1), (0.0, top - 0.24), (-0.016, top - 0.1)], "#B83227", ink, ow * 0.5),
              line([(-0.07, top), (-0.02, top - 0.2)], dark, ow * 1.2), line([(0.07, top), (0.02, top - 0.2)], dark, ow * 1.2))
    if wear in ("coat", "uniform", "lab"):
        g.add(line([(0.0, top - 0.08), (0.0, y0 + full * 0.4)], ink, ow * 0.7))
        for y in np.linspace(top - 0.12, y0 + full * 0.46, 3):
            g.add(Dot([0.03, y, 0], radius=0.009, color="#F2C14E" if wear == "uniform" else ink))
    if wear == "vest" or wear == "overalls":    # straps over the shirt (braces)
        c_ = "#5B4A3A" if wear == "vest" else "#3E5C82"
        g.add(line([(-0.09, top + 0.01), (-0.08, y0 + full * 0.38)], c_, ow * 2.2),
              line([(0.09, top + 0.01), (0.08, y0 + full * 0.38)], c_, ow * 2.2))
    if wear == "apron":
        g.add(_poly([(-0.12, top - 0.12), (0.12, top - 0.12), (0.14, y0 + 0.04), (-0.14, y0 + 0.04)], "#F3EEE4", ink, ow * 0.8))
    if wear in ("tunic", "robe", "habit", "armor", "uniform"):
        belt = {"habit": "#E2D3B0", "robe": _shade(cloth, 0.6), "armor": "#5B4A3A"}.get(wear, "#4A3A2C")
        yb = y0 + full * 0.45
        g.add(_poly([(-W / 2, yb), (W / 2, yb), (W / 2, yb + 0.03), (-W / 2, yb + 0.03)], belt, ink, ow * 0.6))
    if wear == "toga":
        g.add(_poly([(-W / 2 + 0.03, top), (-W / 2 + 0.11, top), (W / 2 - 0.02, y0 + 0.12), (W / 2 - 0.07, y0 + 0.05)],
                    "#B83227", ink, ow * 0.6))
    if wear == "armor":
        for y in np.linspace(top - 0.08, y0 + 0.08, 4):
            g.add(line([(-W / 2 + 0.03, y), (W / 2 - 0.03, y)], ink, ow * 0.6))
    if wear in ("dress", "gown"):
        g.add(_poly([(-0.06, top), (0.06, top), (0.0, top - 0.06)], "#F7F5F0", ink, ow * 0.6),
              line([(-W / 2 + 0.02, y0 + full * 0.55), (W / 2 - 0.02, y0 + full * 0.55)], dark, ow * 1.2))
    # the head's shadow on the top of the body
    g.add(Ellipse(width=W * 0.62, height=0.05, fill_color=ink, fill_opacity=0.13, stroke_width=0).move_to([0.01, H - 0.012, 0]))
    outline = RoundedRectangle(width=W, height=full, corner_radius=W * 0.32, fill_opacity=0, stroke_color=ink,
                               stroke_width=ow).move_to([0, (H + y0) / 2, 0])
    g.add(outline)
    return g


def person(mods: dict, size: float, c=None) -> Person:
    mods = attire.role(mods)
    size = (size or 2.8) * (0.66 if mods.get("kid") else 1.0)
    style = str(mods.get("style") or FIGURE).lower()
    p = (Person if style == "stick" else Peg)(mods, c, size)
    p.scale(size, about_point=np.array([0.0, 0.0, 0.0]))
    return p
