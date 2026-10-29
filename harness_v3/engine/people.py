"""Stick-figure people drawn with a pen, who move: `ent ann person [hat top|cap|crown|helmet|hood] [tool book|staff|
flag|hammer|sign|coin|spear|quill] [seat] [color C] [size H] [face left] at X,Y`.

A person is a pose (the angles of the body, arms and legs, where the face looks, how open the mouth is) drawn where
the figure now stands, so a person moved, scaled or turned on the page poses there. The renderer's verbs set poses
over time (render.py): `walk P to X,Y|ENT|MAP.place`, `point P at REF`, `wave P`, `talk P ["words"]`,
`carry P THING`, `sit P`, `stand P`, `turn P left|right`.

Angles are in radians from straight down, toward the way the figure faces.
"""

from __future__ import annotations

import math

import numpy as np
from manim import Circle, Dot, Ellipse, Line, Polygon, Rectangle, VGroup

from look import STROKE, col

# A body one unit tall (feet at 0): where each part is, and how long.
HIP, TORSO, NECK, HEAD = 0.45, 0.3, 0.035, 0.1
UPPER, FORE, THIGH, SHIN = 0.17, 0.16, 0.235, 0.215

REST = {"lean": 0.0, "fa1": 0.12, "fa2": 0.2, "ba1": -0.1, "ba2": -0.05, "fl1": 0.06, "fl2": 0.0, "bl1": -0.06,
        "bl2": -0.06, "drop": 0.0, "face": 1.0, "mouth": 0.0, "bob": 0.0}
KEYS = tuple(REST)


def walk_pose(phase: float) -> dict:
    """The walk cycle at a phase (radians): legs and arms swinging opposite, a knee bending as its foot comes through."""
    s = math.sin(phase)
    p = dict(REST)
    p["fl1"] = 0.42 * s
    p["fl2"] = p["fl1"] - 0.55 * max(0.0, math.cos(phase))
    p["bl1"] = -0.42 * s
    p["bl2"] = p["bl1"] - 0.55 * max(0.0, -math.cos(phase))
    p["fa1"] = -0.38 * s
    p["fa2"] = p["fa1"] + 0.35
    p["ba1"] = 0.38 * s
    p["ba2"] = p["ba1"] + 0.35
    p["bob"] = 0.018 * abs(math.cos(phase))
    p["lean"] = 0.06
    return p


def sit_pose(seat: bool) -> dict:
    p = dict(REST)
    if seat:                                    # on its stool: thighs level, shins down
        p.update(drop=HIP - 0.24, fl1=math.pi / 2, fl2=0.05, bl1=math.pi / 2 - 0.12, bl2=-0.05, fa1=0.35, fa2=1.1,
                 ba1=0.25, ba2=1.0)
    else:                                       # on the ground, knees up
        p.update(drop=HIP - 0.06, fl1=2.0, fl2=-0.4, bl1=1.7, bl2=-0.6, fa1=0.6, fa2=1.6, ba1=0.4, ba2=1.4,
                 lean=0.12)
    return p


def carry_pose() -> dict:
    p = dict(REST)
    p.update(fa1=0.45, fa2=1.55, ba1=0.35, ba2=1.45)
    return p


def mix(a: dict, b: dict, k: float) -> dict:
    return {key: a[key] + (b[key] - a[key]) * k for key in KEYS}


class Person(VGroup):
    def __init__(self, mods: dict | None = None, c=None):
        super().__init__()
        mods = mods or {}
        self.mods = mods
        ink = col(c or "ink")
        w = STROKE * 0.7
        line = lambda: Line([0, 0, 0], [0, -0.1, 0], stroke_color=ink, stroke_width=w)  # noqa: E731
        self.seat = None
        if mods.get("seat"):
            self.seat = VGroup(Line([-0.13, 0.22, 0], [0.15, 0.22, 0]), Line([-0.1, 0.22, 0], [-0.13, 0, 0]),
                               Line([0.12, 0.22, 0], [0.15, 0, 0])).set_stroke(col("soft"), w * 0.8)
            self.add(self.seat)
        self.bl, self.bs, self.ba, self.bf = line(), line(), line(), line()     # the back leg and arm
        for x in (self.bl, self.bs, self.ba, self.bf):
            x.set_stroke(opacity=0.75)
        self.body = line()
        self.fl, self.fs, self.fa, self.ff = line(), line(), line(), line()     # the front leg and arm
        self.head = Circle(radius=HEAD, fill_color=col("card"), fill_opacity=1, stroke_color=ink, stroke_width=w)
        self.eyes = VGroup(Dot(radius=0.011, color=ink), Dot(radius=0.011, color=ink))
        self.mouth = Ellipse(width=0.045, height=0.012, fill_color=ink, fill_opacity=1, stroke_width=0)
        self.add(self.bl, self.bs, self.ba, self.bf, self.body, self.fl, self.fs, self.head, self.eyes, self.mouth,
                 self.fa, self.ff)
        self.hat = _hat(str(mods.get("hat") or ""), ink, w)
        if self.hat is not None:
            self.add(self.hat)
        self.tool = _tool(str(mods.get("tool") or ""), ink, w)
        if self.tool is not None:
            self.add(self.tool)
        if mods.get("color"):                   # a shirt: the body line drawn thick in the colour
            self.body.set_stroke(col(mods["color"]), width=w * 2.4)
        self.hand = Dot(radius=0.001).set_opacity(0)
        # Where the figure's own coordinates are now (carried along as it is moved, scaled or turned).
        self._ref = VGroup(*(Dot([x, y, 0], radius=0.001).set_opacity(0) for x, y in ((0, 0.5), (0.1, 0.5), (0, 0.6))))
        self.add(self.hand, self._ref)
        self.pose = dict(REST)
        self.pose["face"] = -1.0 if mods.get("face") == "left" else 1.0
        self.walked = 0.0
        self.set_pose(self.pose)

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

        def d(a):                               # a direction at an angle from down, toward the face
            return np.array([f * math.sin(a), -math.cos(a)])

        hip = np.array([0.0, HIP - p["drop"] + p["bob"]])
        sh = hip + TORSO * np.array([f * math.sin(p["lean"]), math.cos(p["lean"])])
        neck = sh + NECK * np.array([f * math.sin(p["lean"]), math.cos(p["lean"])])
        head = neck + HEAD * np.array([f * math.sin(p["lean"]), math.cos(p["lean"])])
        W = lambda q: self.w(q)  # noqa: E731

        def seg(m, a, b):
            if np.linalg.norm(a - b) > 1e-4:
                m.put_start_and_end_on(W(a), W(b))

        seg(self.body, hip, sh)
        fk, bk = hip + THIGH * d(p["fl1"]), hip + THIGH * d(p["bl1"])
        seg(self.fl, hip, fk)
        seg(self.fs, fk, fk + SHIN * d(p["fl2"]))
        seg(self.bl, hip, bk)
        seg(self.bs, bk, bk + SHIN * d(p["bl2"]))
        fe, be = sh + UPPER * d(p["fa1"]), sh + UPPER * d(p["ba1"])
        fh = fe + FORE * d(p["fa2"])
        seg(self.fa, sh, fe)
        seg(self.ff, fe, fh)
        seg(self.ba, sh, be)
        seg(self.bf, be, be + FORE * d(p["ba2"]))
        self.head.move_to(W(head))
        turn = max(-1.0, min(1.0, p["face"]))   # the eyes slide round the head as it turns
        for i, e in enumerate(self.eyes):
            e.move_to(W(head + np.array([turn * 0.045 + (i - 0.5) * 0.035 * (1 - 0.5 * abs(turn)), 0.018])))
        mh = max(0.004, 0.012 + 0.035 * max(0.0, min(1.0, p["mouth"]))) * self.unit()
        self.mouth.stretch_to_fit_height(mh)
        self.mouth.move_to(W(head + np.array([turn * 0.035, -0.045])))
        if self.hat is not None:
            top = W(head + np.array([0.0, HEAD * 0.75]))
            self.hat.shift(top - self.hat.get_bottom())
        self.hand.move_to(W(fh))
        if self.tool is not None:
            self.tool.shift(W(fh) - self.tool.get_center())


def _hat(kind: str, ink, w):
    k = kind.lower()
    if not k:
        return None
    if k == "top":
        g = VGroup(Rectangle(width=0.13, height=0.13, fill_color=ink, fill_opacity=1, stroke_width=0).shift([0, 0.08, 0]),
                   Line([-0.11, 0.015, 0], [0.11, 0.015, 0], stroke_color=ink, stroke_width=w))
    elif k == "crown":
        g = Polygon([-0.09, 0, 0], [0.09, 0, 0], [0.1, 0.1, 0], [0.05, 0.05, 0], [0, 0.11, 0], [-0.05, 0.05, 0],
                    [-0.1, 0.1, 0], fill_color=col("accent"), fill_opacity=1, stroke_color=ink, stroke_width=w * 0.6)
    elif k == "helmet":
        from manim import Arc
        g = VGroup(Arc(radius=0.11, start_angle=0, angle=math.pi, stroke_color=ink, stroke_width=w,
                       fill_color=col("soft"), fill_opacity=1).shift([0, -0.02, 0]))
    elif k == "hood":
        from manim import Arc
        g = VGroup(Arc(radius=0.135, start_angle=-0.3, angle=math.pi + 0.6, stroke_color=ink, stroke_width=w).shift([0, -0.07, 0]))
    else:                                       # a cap
        g = VGroup(Polygon([-0.1, 0, 0], [0.1, 0, 0], [0.07, 0.06, 0], [-0.07, 0.06, 0], fill_color=col(kind if kind in ("coral", "navy", "teal") else "coral"),
                           fill_opacity=1, stroke_color=ink, stroke_width=w * 0.6),
                   Line([0.05, 0.005, 0], [0.16, 0.005, 0], stroke_color=ink, stroke_width=w))
    return g


def _tool(kind: str, ink, w):
    k = kind.lower()
    if not k:
        return None
    if k in ("staff", "spear"):
        g = VGroup(Line([0, -0.25, 0], [0, 0.32, 0], stroke_color=col("sand") if k == "staff" else ink, stroke_width=w))
        if k == "spear":
            g.add(Polygon([-0.025, 0.32, 0], [0.025, 0.32, 0], [0, 0.4, 0], fill_color=ink, fill_opacity=1, stroke_width=0))
    elif k == "flag":
        g = VGroup(Line([0, -0.05, 0], [0, 0.42, 0], stroke_color=ink, stroke_width=w * 0.8),
                   Polygon([0, 0.42, 0], [0.2, 0.36, 0], [0, 0.29, 0], fill_color=col("coral"), fill_opacity=1, stroke_width=0))
    elif k == "sign":
        g = VGroup(Line([0, -0.05, 0], [0, 0.3, 0], stroke_color=ink, stroke_width=w * 0.8),
                   Rectangle(width=0.3, height=0.16, fill_color=col("card"), fill_opacity=1, stroke_color=ink,
                             stroke_width=w * 0.6).shift([0, 0.36, 0]))
    elif k == "hammer":
        g = VGroup(Line([0, -0.02, 0], [0, 0.16, 0], stroke_color=col("sand"), stroke_width=w),
                   Rectangle(width=0.11, height=0.05, fill_color=ink, fill_opacity=1, stroke_width=0).shift([0, 0.17, 0]))
    elif k == "quill":
        g = VGroup(Polygon([0, 0, 0], [0.04, 0.2, 0], [0.01, 0.2, 0], fill_color=col("card"), fill_opacity=1,
                           stroke_color=ink, stroke_width=w * 0.5))
    elif k == "coin":
        g = VGroup(Circle(radius=0.04, fill_color=col("accent"), fill_opacity=1, stroke_color=ink, stroke_width=w * 0.5))
    else:                                       # a book
        g = VGroup(Rectangle(width=0.12, height=0.15, fill_color=col("coral"), fill_opacity=1, stroke_color=ink,
                             stroke_width=w * 0.5))
    return g


def person(mods: dict, size: float, c=None) -> Person:
    p = Person(mods, c)
    p.scale(size or 1.8, about_point=np.array([0.0, 0.0, 0.0]))
    return p
