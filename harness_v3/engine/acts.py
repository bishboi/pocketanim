"""More of what the score can say, kept beside render.py (ScoreScene takes these in as a mixin):

    react P idea|question|exclaim|shock|love|zzz|anger|sweat|sparkle [COLOR]   a doodle pops over a head (or a thing)
    annex A B                       B goes over to A: its colour turns A's, its border flashes (B shown if not up)
    travel T PATH [trail off]       a vehicle along a route: it turns to face its way, tilts with the slope, bobs,
                                    and the route is drawn behind it as dashes
    give A B THING | throw A B THING | shake A B | push A B | tug A B [THING]
    argue A B ["WORDS" ...] | whisper A B "WORDS"                                two people at once

and two kinds of thing:

    isotype N "WHAT" [per K] [shape person|coin|book|house|box|drop|tree|bread] [cols C] [lit L] [img "..."]
                    a picture row: N/K little figures, a key "each = K WHAT"; its parts are the figures
    note "WORDS" [to T]             a handwritten margin note, a curved arrow to T
"""

from __future__ import annotations

import math
import re

import numpy as np
from manim import (DOWN, LEFT, RIGHT, UP, Arc, ArcBetweenPoints, Circle, DashedVMobject, Dot, Ellipse, Group,
                   ImageMobject, Line, Polygon, Rectangle, RoundedRectangle, VGroup, VMobject, rate_functions)

import feel
import look

REACTIONS = ("idea", "question", "exclaim", "shock", "love", "zzz", "anger", "sweat", "sparkle")
PAIR_VERBS = ("give", "throw", "shake", "push", "tug", "argue", "whisper")
RUN = {"react": 1.6, "annex": 1.2, "travel": 3.0, "give": 1.4, "throw": 1.3, "shake": 1.8, "push": 1.2, "tug": 2.4,
       "argue": 3.0, "whisper": 2.0}
HAND = "Caveat"                                 # the margin notes' handwriting (setup.sh fetches it)


# ---------------------------------------------------------------- drawings -------------------------------------------

def _heart(s: float, c) -> VMobject:
    pts = []
    for t in np.linspace(0, 2 * math.pi, 40):
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append(np.array([x, y, 0.0]) * s / 32)
    m = VMobject(fill_color=c, fill_opacity=1, stroke_color=look.col("ink"), stroke_width=1.6)
    m.set_points_smoothly(pts)
    return m


def _star(s: float, c) -> VMobject:
    pts = []
    for i in range(8):
        r = s if i % 2 == 0 else s * 0.28
        a = math.pi / 2 + i * math.pi / 4
        pts.append(np.array([r * math.cos(a), r * math.sin(a), 0.0]))
    return Polygon(*pts, fill_color=c, fill_opacity=1, stroke_color=look.col("ink"), stroke_width=1.2)


def _drop(s: float, c) -> VMobject:
    pts = [np.array([0.0, s, 0.0])]
    for a in np.linspace(0.15 * math.pi, 0.85 * math.pi, 14):
        pts.append(np.array([s * 0.55 * math.cos(a + math.pi), s * 0.55 * math.sin(a + math.pi) - 0.0, 0.0]))
    m = VMobject(fill_color=c, fill_opacity=1, stroke_color=look.col("ink"), stroke_width=1.6)
    m.set_points_smoothly([*pts, pts[0]])
    return m


def _glyph(ch: str, s: float, c) -> VMobject:
    t = look.text(ch, s, bold=True, color=c)
    t.set_stroke(look.col("bg"), width=5, background=True)
    return t


def reaction(kind: str, s: float = 0.5, c=None) -> VGroup:
    """A reaction mark (as in a comic's margin) about `s` tall, centred on 0: its parts in the order they come on."""
    ink = look.col("ink")
    k = kind if kind in REACTIONS else "exclaim"
    if k == "idea":
        cc = look.col(c or "gold")
        bulb = Circle(radius=s * 0.3, fill_color=cc, fill_opacity=1, stroke_color=ink, stroke_width=2).shift(UP * s * 0.08)
        base = RoundedRectangle(width=s * 0.26, height=s * 0.18, corner_radius=s * 0.04, fill_color="#9AA0A6",
                                fill_opacity=1, stroke_color=ink, stroke_width=1.6).shift(DOWN * s * 0.3)
        rays = VGroup(*(Line(UP * s * 0.42, UP * s * 0.58, stroke_color=ink, stroke_width=2.4)
                        .rotate(a, about_point=UP * s * 0.08) for a in (-1.2, -0.6, 0.0, 0.6, 1.2)))
        return VGroup(base, bulb, rays)
    if k in ("question", "exclaim"):
        g = VGroup(_glyph("?" if k == "question" else "!", s * 0.85, c or ("navy" if k == "question" else "coral")))
        if k == "exclaim":
            g.add(_glyph("!", s * 0.6, c or "coral").rotate(-0.25).shift(RIGHT * s * 0.3 + DOWN * s * 0.08))
        return g
    if k == "shock":
        cc = look.col(c or "ink")
        return VGroup(*(Line(UP * s * 0.18, UP * s * 0.55, stroke_color=cc, stroke_width=3.2).rotate(a, about_point=ORIGIN3)
                        for a in (-1.0, -0.5, 0.0, 0.5, 1.0)))
    if k == "love":
        cc = look.col(c or "red")
        return VGroup(_heart(s * 0.5, cc).shift(LEFT * s * 0.2), _heart(s * 0.36, cc).shift(RIGHT * s * 0.25 + UP * s * 0.3),
                      _heart(s * 0.26, cc).shift(LEFT * s * 0.05 + UP * s * 0.62))
    if k == "zzz":
        cc = c or "navy"
        return VGroup(_glyph("z", s * 0.32, cc), _glyph("z", s * 0.44, cc).shift(RIGHT * s * 0.28 + UP * s * 0.3),
                      _glyph("Z", s * 0.56, cc).shift(RIGHT * s * 0.62 + UP * s * 0.68))
    if k == "anger":                            # the four bent strokes of a popping vein
        cc = look.col(c or "red")
        g = VGroup()
        for i in range(4):
            a = Arc(radius=s * 0.16, start_angle=math.pi, angle=-math.pi / 2, stroke_color=cc, stroke_width=4.2)
            a.shift(np.array([-s * 0.04, -s * 0.04, 0]))
            g.add(a.rotate(i * math.pi / 2, about_point=ORIGIN3))
        return g
    if k == "sweat":
        return VGroup(_drop(s * 0.32, look.col(c or "sky")), _drop(s * 0.2, look.col(c or "sky")).shift(RIGHT * s * 0.22 + UP * s * 0.25))
    cc = look.col(c or "gold")                  # sparkle
    return VGroup(_star(s * 0.3, cc), _star(s * 0.18, cc).shift(RIGHT * s * 0.38 + UP * s * 0.3),
                  _star(s * 0.14, cc).shift(LEFT * s * 0.32 + UP * s * 0.38))


ORIGIN3 = np.zeros(3)


def _unit(shape: str, s: float, c) -> VMobject:
    """One figure of a picture row, about `s` tall, centred on 0."""
    ink = look.col("ink")
    ow = 1.6
    if shape == "coin":
        return VGroup(Circle(radius=s * 0.45, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow),
                      Circle(radius=s * 0.32, stroke_color=ink, stroke_width=ow * 0.7, fill_opacity=0))
    if shape == "book":
        return VGroup(Rectangle(width=s * 0.7, height=s * 0.9, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow),
                      Line([-s * 0.25, -s * 0.45, 0], [-s * 0.25, s * 0.45, 0], stroke_color=ink, stroke_width=ow))
    if shape == "house":
        return VGroup(Rectangle(width=s * 0.7, height=s * 0.5, fill_color=c, fill_opacity=1, stroke_color=ink,
                                stroke_width=ow).shift(DOWN * s * 0.2),
                      Polygon([-s * 0.45, s * 0.05, 0], [s * 0.45, s * 0.05, 0], [0, s * 0.45, 0], fill_color=c,
                              fill_opacity=1, stroke_color=ink, stroke_width=ow))
    if shape == "drop":
        return _drop(s * 0.5, c).move_to(ORIGIN3)
    if shape == "tree":
        return VGroup(Rectangle(width=s * 0.12, height=s * 0.35, fill_color="#8A5A36", fill_opacity=1, stroke_color=ink,
                                stroke_width=ow).shift(DOWN * s * 0.3),
                      Circle(radius=s * 0.34, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow).shift(UP * s * 0.1))
    if shape == "bread":
        return VGroup(Ellipse(width=s * 0.95, height=s * 0.55, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow),
                      *(Line([x - s * 0.06, -s * 0.12, 0], [x + s * 0.06, s * 0.12, 0], stroke_color=ink, stroke_width=ow)
                        for x in (-s * 0.22, 0.0, s * 0.22)))
    if shape == "box":
        return Rectangle(width=s * 0.8, height=s * 0.8, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow)
    return look.figure(s, None).set_fill(c)  # a person


def isotype(args: list, mods: dict, size: float, c=None):
    """A picture row (an isotype): N/K figures in rows, `lit L` of them in the accent colour, a key under them."""
    n = float(re.sub(r"[^\d.]", "", str(args[0])) or 10) if args else 10.0
    what = str(args[1]) if len(args) > 1 else ""
    per = float(mods.get("per") or 1)
    count = max(1, min(200, round(n / per)))
    shape = str(mods.get("shape") or "person").lower()
    s = size or 0.46
    cols = int(mods.get("cols") or min(10, max(4, math.ceil(math.sqrt(count * 2.2)))))
    lit = int(mods.get("lit") or 0)
    base = look.col(c or "ink" if shape == "person" else c or "sand")
    accent = look.col("accent")
    gap = s * 0.3
    units = []
    img = mods.get("img")
    for i in range(count):
        colour = accent if i < lit else base
        if img:
            u = look.picture("pic", str(img), s, {})
            u = getattr(u, "frame_of", u)
        else:
            u = _unit(shape, s, colour)
        r, k = divmod(i, cols)
        u.move_to([k * (s + gap), -r * (s + gap * 1.4), 0])
        units.append(u)
    grid = Group(*units) if any(isinstance(u, ImageMobject) for u in units) else VGroup(*units)
    grid.move_to(ORIGIN3)
    key_unit = (look.picture("pic", str(img), s * 0.7, {}) if img else _unit(shape, s * 0.7, base))
    key_unit = getattr(key_unit, "frame_of", key_unit)
    amount = f"{per:,.0f}" if per == int(per) else f"{per:g}"
    words = look.label(f"= {amount} {what}".strip() if per != 1 or what else "", 0.15, "ink")
    key = Group(key_unit, words) if isinstance(key_unit, ImageMobject) else VGroup(key_unit, words)
    words.next_to(key_unit, RIGHT, buff=0.12)
    key.next_to(grid, DOWN, buff=0.35).align_to(grid, LEFT)
    out = Group(*units, key) if isinstance(grid, Group) or isinstance(key, Group) else VGroup(*units, key)
    return out.move_to(ORIGIN3)


def note(words: str, mods: dict, size: float, c=None) -> VGroup:
    """A handwritten note in the margin, a little askew (its arrow is drawn when it is placed: note_arrow)."""
    lines = [ln.strip() for ln in re.split(r"\s*/\s*|\n", str(words)) if ln.strip()] or [""]
    w = float(mods.get("w", 4.2))
    ink = c or "navy"
    rows = VGroup(*(look.text(ln, size or 0.34, color=ink, font=HAND, width=w) for ln in lines))
    rows.arrange(DOWN, buff=(size or 0.34) * 0.35, aligned_edge=LEFT)
    g = VGroup(rows)
    if not mods.get("rot"):                     # (a `rot` said is turned by render)
        g.rotate(math.radians(-4))
    return g


def note_arrow(n, target, c=None) -> VMobject:
    """A hand-drawn curved arrow from a note to what it is about, ending a little short of it."""
    a_c, b_c = n.get_center(), target.get_center()
    d = b_c - a_c
    # from the note's edge toward the target, to the target's edge toward the note (boxes, so near enough)
    def edge(m, toward):
        w, h = m.width / 2, m.height / 2
        v = toward - m.get_center()
        k = min(w / max(abs(v[0]), 1e-6), h / max(abs(v[1]), 1e-6))
        return m.get_center() + v * min(k, 1.0)
    a = edge(n, b_c) + d / max(np.linalg.norm(d), 1e-6) * 0.12
    b = edge(target, a_c) - d / max(np.linalg.norm(d), 1e-6) * 0.15
    bend = -0.7 if d[0] >= 0 else 0.7
    ink = look.col(c or "navy")
    arc = ArcBetweenPoints(a, b, angle=bend, stroke_color=ink, stroke_width=look.STROKE * 0.9)
    tip = arc.points[-1]
    back = arc.points[-1] - arc.points[-2]
    if np.linalg.norm(back) < 1e-6:
        back = b - a
    back = back / np.linalg.norm(back) * 0.22
    head = VGroup(Line(tip, tip - _rot(back, 0.5), stroke_color=ink, stroke_width=look.STROKE * 0.9),
                  Line(tip, tip - _rot(back, -0.5), stroke_color=ink, stroke_width=look.STROKE * 0.9))
    g = VGroup(arc, head)
    feel.wobbled(arc, 0.02, "note")
    return g


def _rot(v, a):
    ca, sa = math.cos(a), math.sin(a)
    return np.array([ca * v[0] - sa * v[1], sa * v[0] + ca * v[1], 0.0])


# ---------------------------------------------------------------- the actions ----------------------------------------

class MoreActs:
    """Actions for render.ScoreScene (it has self.tweens, self.E, _targets, _show, _alpha, follows...)."""

    def _more(self, act, t0, t1) -> bool:
        """Plays one of these verbs; False: not one of them."""
        v = act.verb
        if v in ("emote", "look"):
            if not isinstance(self.E.get(act.target), Eyes):
                return False                    # (a person's: render's own)
            self._eyes(act, t0, t1)
        elif v == "react":
            self._react(act, t0, t1)
        elif v == "annex":
            self._annex(act, t0, t1)
        elif v == "travel":
            self._travel(act, t0, t1)
        elif v in PAIR_VERBS:
            if v == "shake" and not (act.args and act.args[0] in self.E):
                return False                    # `shake T`: a thing shaken (render's own)
            self._pair(act, t0, t1)
        else:
            return False
        return True

    # -- eyes -----------------------------------------------------------------------------------------------------
    def _eyes(self, act, t0, t1) -> None:
        """`emote E MOOD`: a blink, and it opens in the new mood. `look E at T`: the pupils turn to it."""
        from render import Call
        m = self.E[act.target]
        st = {}
        if act.verb == "emote":
            mood = act.args[0] if act.args else "angry"

            def step(a):
                if a >= 0.5 and not st.get("swapped"):
                    st["swapped"] = True
                    m.set_mood(mood, blink=1.0)
                m._draw(blink=math.sin(math.pi * a))
            self.tweens.append(Call(t0, max(t1, t0 + 0.45), None, step, None, rate_functions.linear))
        else:
            ref = act.args[act.args.index("at") + 1] if "at" in act.args else (act.args[0] if act.args else "")

            def start():
                goal = self._locate(ref, self.SCORE.ents[act.target].shot)
                st["g0"], st["g1"] = m.gaze.copy(), (goal - m.get_center())[:2]

            def step(a):
                d = st["g1"]
                n = float(np.linalg.norm(d))
                g1 = d / n * 0.55 if n > 1e-6 else np.zeros(2)
                m.gaze = st["g0"] + (g1 - st["g0"]) * a
                m._draw()
            self.tweens.append(Call(t0, max(t1, t0 + 0.4), start, step, None, rate_functions.smooth))

    # -- react ------------------------------------------------------------------------------------------------------
    def _react(self, act, t0, t1) -> None:
        import people as P
        from render import Alpha, Call
        kind = next((a for a in act.args if a in REACTIONS), "exclaim")
        colour = next((a for a in act.args if a in look.L), None)
        for name, m in self._targets(act.target):
            person = isinstance(m, P.Person)
            st = {}

            def start(m=m, person=person, st=st):
                if person:
                    s = max(0.45, min(1.1, m.unit() * 0.32))
                    anchor = m.head
                    f = m.facing()
                    top = anchor.get_top()
                    off = {"sweat": np.array([-f * s * 0.55, -s * 0.15, 0]),
                           "anger": np.array([f * s * 0.45, s * 0.2, 0]),
                           "zzz": np.array([f * s * 0.5, s * 0.5, 0])}.get(kind, np.array([f * s * 0.2, s * 0.62, 0]))
                    at = (anchor.get_center() if kind == "sweat" else top) + off
                else:
                    s = max(0.45, min(0.9, max(m.width, m.height) * 0.3))
                    anchor = m
                    at = m.get_corner(UP + RIGHT) + np.array([-s * 0.1, s * 0.45, 0])
                g = reaction(kind, s, colour)
                g.move_to(at)
                zs = [x.z_index for x in m.get_family()] or [0]
                g.set_z_index(max(zs) + 4)
                st.update(g=g, al=Alpha(g), anchor=anchor, last=anchor.get_center().copy(), k=1.0, s=s,
                          c=g.get_center().copy(), rise=0.0)
                st["al"].set(0.0)
                self.add(g)

            def step(a, st=st, t0=t0, t1=t1):
                g = st["g"]
                c = st["anchor"].get_center()
                g.shift(c - st["last"])
                st["c"] = st["c"] + (c - st["last"])
                st["last"] = c.copy()
                tt, dur = a * (t1 - t0), max(t1 - t0, 0.3)
                # pops up big, settles, a little life while it is up, and fades at the end
                pop = min(1.0, tt / 0.22)
                k = (0.3 + 0.95 * pop) if pop < 1 else 1.0 + 0.25 * math.exp(-(tt - 0.22) * 12) * math.cos((tt - 0.22) * 30)
                if kind in ("love", "zzz", "sweat"):
                    k = min(1.0, k)
                g.scale(max(k, 0.05) / st["k"], about_point=st["c"])
                st["k"] = max(k, 0.05)
                if kind in ("love", "zzz"):     # drifting up
                    r = 0.25 * st["s"] * tt
                    g.shift(UP * (r - st["rise"]))
                    st["c"] = st["c"] + UP * (r - st["rise"])
                    st["rise"] = r
                elif kind == "sweat":           # sliding down
                    r = -0.15 * st["s"] * min(tt, 1.0)
                    g.shift(UP * (r - st["rise"]))
                    st["c"] = st["c"] + UP * (r - st["rise"])
                    st["rise"] = r
                st["al"].set(min(1.0, tt / 0.12, max(0.0, (dur - tt) / 0.3)))

            def stop(st=st):
                self.remove(st["g"])
            self.tweens.append(Call(t0, max(t1, t0 + 0.6), start, step, stop, rate_functions.linear))

    # -- annex ------------------------------------------------------------------------------------------------------
    def _fill_of(self, m):
        import people as P
        if isinstance(m, P.Person):
            return m.skin
        for x in m.family_members_with_points():
            if isinstance(x, VMobject) and x.get_fill_opacity() > 0.05:
                return x.get_fill_color()
        return look.col("coral")

    def _annex(self, act, t0, t1) -> None:
        from manim.utils.color import interpolate_color
        from render import Call
        taker = act.target
        (bn, bm), = self._targets(act.args[0])[:1] if act.args else ((None, None),)
        if bm is None:
            raise ValueError("annex needs what is taken: `annex A B`")
        if taker in self.E:
            colour = self._fill_of(self.E[taker])
            edge = next((x.get_stroke_color() for x in self.E[taker].family_members_with_points()
                         if isinstance(x, VMobject) and x.get_stroke_width() > 0.3 and x.get_stroke_opacity() > 0.3), colour)
        else:
            colour = edge = look.col(taker)
        st = {}
        leaves = [x for x in bm.family_members_with_points() if isinstance(x, VMobject)]

        def start():
            if id(self.E[bn]) not in self.up:
                self._show(bn, bm)
                self._alpha(bm).set(1.0)
                st["fresh"] = True
            st["c0"] = [(x, x.get_fill_color(), x.get_stroke_width(), x.get_fill_opacity(), x.get_stroke_color())
                        for x in leaves]

        def step(a):
            # the colour floods over it; its border flares as it changes hands
            flare = math.sin(math.pi * min(1.0, a * 1.3))
            k = rate_functions.smooth(a)
            for x, c0, w0, f0, s0 in st["c0"]:
                if f0 > 0.02 or st.get("fresh"):
                    x.set_fill(interpolate_color(c0, colour, k), family=False)
                x.set_stroke(interpolate_color(s0, edge, k), width=w0 * (1 + 1.6 * flare), family=False)
        self.tweens.append(Call(t0, t1, start, step, None, rate_functions.linear))
        self._pulse(bm, t0 + (t1 - t0) * 0.3, t1)

    # -- travel -----------------------------------------------------------------------------------------------------
    def _travel(self, act, t0, t1) -> None:
        from render import Call
        (name, m), = self._targets(act.target)[:1]
        if not act.args or act.args[0] not in self.E:
            raise ValueError("travel needs a path: `travel T PATH`")
        track = self._track(self.E[act.args[0]])
        e = self.SCORE.ents.get(name)
        faces = -1.0 if e is not None and e.mods.get("face") == "left" else 1.0     # how its picture is drawn
        trail = "off" not in act.args
        bob = float(self._opt(act, "bob", 0.05))
        st = {}

        def start():
            if id(self.E[name]) not in self.up:
                self._show(name, m)
                self._alpha(m).set(1.0)
            st.update(face=faces, tilt=0.0, bob=0.0)
            m.move_to(track.point_from_proportion(0.0))
            if trail:
                n = max(6, int(track.get_arc_length() / 0.32))
                dashes = DashedVMobject(track.copy().set_stroke(look.col("ink"), width=look.STROKE * 0.55, opacity=0.6),
                                        num_dashes=n, dashed_ratio=0.55)
                dashes.set_z_index(min(x.z_index for x in m.get_family()) - 1)
                for d in dashes.submobjects:
                    d.set_stroke(opacity=0.0)
                st["dashes"] = dashes.submobjects
                self.add(dashes)
                self.marks.setdefault(name, []).append(dashes)

        def step(a):
            p = track.point_from_proportion(min(a, 0.999))
            q = track.point_from_proportion(min(a + 0.01, 1.0)) if a < 0.99 else p + (p - track.point_from_proportion(0.98))
            d = q - p
            if abs(d[0]) > 1e-4:                # it turns to face the way it goes
                way = 1.0 if d[0] > 0 else -1.0
                if way != st["face"]:
                    m.stretch(-1, 0)            # (mirrored about its centre)
                    st["face"] = way
                    st["tilt"] = -st["tilt"]
            ang = math.atan2(d[1], abs(d[0])) * (1 if st["face"] > 0 else -1) if np.linalg.norm(d) > 1e-5 else st["tilt"]
            ang = max(-0.35, min(0.35, ang)) * 0.7
            tilt = st["tilt"] + (ang - st["tilt"]) * 0.25
            m.rotate(tilt - st["tilt"])
            st["tilt"] = tilt
            b = bob * math.sin(a * (t1 - t0) * 7.0)
            m.move_to(p + UP * b)
            if "dashes" in st:
                k = int(a * len(st["dashes"]))
                for i, dsh in enumerate(st["dashes"][:k]):
                    if i >= st.get("shown", 0):
                        dsh.set_stroke(opacity=0.6)
                st["shown"] = max(st.get("shown", 0), k)

        def stop():
            if abs(st["tilt"]) > 1e-4:
                m.rotate(-st["tilt"])
                st["tilt"] = 0.0
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.ease_in_out_sine))

    # -- two at once ------------------------------------------------------------------------------------------------
    def _pair(self, act, t0, t1) -> None:
        import people as P
        from render import Call
        v = act.verb
        (an, am), = self._targets(act.target)[:1]
        if not act.args:
            raise ValueError(f"{v} needs the other: `{v} A B`")
        (bn, bm), = self._targets(act.args[0])[:1]
        if not isinstance(am, P.Person):
            raise ValueError(f"{v} is a person's (`ent NAME person`): {an} is a {self._kind(an)}")
        b_person = isinstance(bm, P.Person)
        thing = next(((n, m) for n, m in (self._targets(x)[0] for x in act.args[1:] if x in self.E)), None)
        words = [x for x in act.args[1:] if x not in self.E and x not in look.L and x not in ("at", "to")]
        dur = max(t1 - t0, 0.3)
        st = {}

        def unit(m):
            return m.unit() if isinstance(m, P.Person) else 1.0

        def toward(src, dst_pt):
            """The arm angle (from down, toward the face) that points src's shoulder at a point, and its facing."""
            sh = src.w((0.0, src.D["HIP"] + src.D["TORSO"]))
            face = 1.0 if dst_pt[0] >= sh[0] else -1.0
            d = dst_pt - sh
            return math.atan2(face * d[0], -d[1]), face

        def blend(p0, target, keys, k):
            p = dict(p0)
            for key in keys:
                p[key] = p0[key] + (target[key] - p0[key]) * k
            return p

        def env(tt, rise=0.25, fall=0.3):
            k = min(1.0, tt / rise, max(0.0, (dur - tt) / fall))
            return k * k * (3 - 2 * k)

        def close_in(a, gap_k=0.55, walk=0.4):
            """A walks up to B (if not near) over the first part of the action."""
            if "f0" not in st:
                st["f0"] = am.feet().copy()
                side = 1.0 if bm.get_center()[0] >= st["f0"][0] else -1.0
                bw = getattr(bm, "body_w", 0.2) * unit(bm) if b_person else bm.width / 2
                gap = max(0.55 * unit(am), gap_k * (getattr(am, "body_w", 0.2) * unit(am) + bw) + 0.25 * unit(am))
                goal = (bm.feet() if b_person else bm.get_center()) - np.array([side * gap, 0, 0])
                goal[1] = st["f0"][1]
                near = abs(bm.get_center()[0] - st["f0"][0]) <= gap * 1.15
                st["f1"] = st["f0"] if near else goal
                st["side"] = side
                am.pose["face"] = side
                if b_person:
                    bm.pose["face"] = -side
                    bm.set_pose(bm.pose)
            k = rate_functions.ease_in_out_sine(min(1.0, a / walk))
            am.shift(st["f0"] + (st["f1"] - st["f0"]) * k - am.feet())
            moving = 0 < a < walk and np.linalg.norm(st["f1"] - st["f0"]) > 0.05
            if moving:                          # legs stepping as it goes
                gone = float(np.linalg.norm(am.feet() - st["f0"]))
                wp = P.walk_pose(gone / max(0.3 * unit(am), 1e-3) * math.pi / 2)
                p = dict(am.pose)
                for key in ("fl1", "fl2", "bl1", "bl2", "bob"):
                    p[key] = wp[key]
                am.set_pose(p)
            elif "legs" not in st and a >= walk:
                st["legs"] = True
                p = dict(am.pose)
                for key in ("fl1", "fl2", "bl1", "bl2", "bob"):
                    p[key] = am.rest[key]
                am.set_pose(p)

        def start():
            st["a0"] = dict(am.pose)
            if b_person:
                st["b0"] = dict(bm.pose)
            if thing is not None:
                tn, tm = thing
                if id(self.E[tn]) not in self.up:
                    self._show(tn, tm)
                    self._alpha(tm).set(1.0)
                    tm.move_to(self._grip(am, tm).get_center() + UP * tm.height * 0.4)
                st["t0"] = tm.get_center().copy()
                st["hand_a"] = self._holder_of(am, tm) or self._grip(am, tm)     # the hand it goes from
                self._use_hand(am, st["hand_a"])
                # whatever was keeping it in A's hands lets go: it is passed on
                self.follows[:] = [r for r in self.follows if r[0] is not tm]
            if v == "tug":
                rope = VMobject(stroke_color="#9A6B43", stroke_width=look.STROKE * 1.1)
                rope.set_points_as_corners([am.hand.get_center(), bm.get_center()])
                rope.set_z_index(max(x.z_index for x in am.get_family()) + 1)
                st["rope"] = rope
                self.add(rope)
            if v in ("argue", "whisper"):
                st["bubbles"] = []

        def step(a):
            tt = a * dur
            k = env(tt)
            if v in ("give", "shake", "push", "tug", "whisper"):
                close_in(a, gap_k={"shake": 0.5, "push": 0.42, "tug": 1.6, "give": 0.85, "whisper": 0.42}[v],
                         walk={"tug": 0.15}.get(v, 0.35))
            if v == "give":
                reach = max(0.0, min(1.0, (a - 0.3) / 0.25)) * min(1.0, max(0.0, (1 - a) / 0.15))
                ang, face = toward(am, bm.get_center() if not b_person else bm.hand.get_center())
                am.set_pose(blend(st["a0"], {**st["a0"], "fa1": ang * 0.9, "fa2": ang, "smile": 0.8}, ("fa1", "fa2", "smile"), reach))
                if b_person:
                    bang, _ = toward(bm, am.hand.get_center())
                    bm.set_pose(blend(st["b0"], {**st["b0"], "fa1": bang * 0.9, "fa2": bang, "smile": 0.9, "joy": 0.6},
                                      ("fa1", "fa2", "smile", "joy"), reach))
                if thing is not None:
                    tn, tm = thing
                    hand_a = st["hand_a"].get_center() + UP * tm.height * 0.4
                    if b_person and "hand_b" not in st:
                        st["hand_b"] = self._grip(bm, tm)
                    goal = (st["hand_b"].get_center() if b_person else bm.get_top()) + UP * tm.height * 0.4
                    h = max(0.0, min(1.0, (a - 0.45) / 0.35))
                    pos = (hand_a if a < 0.45 else hand_a + (goal - hand_a) * rate_functions.smooth(h)) + UP * 0.3 * math.sin(math.pi * h)
                    tm.move_to(pos)
            elif v == "throw":
                goal_pt = bm.hand.get_center() if b_person else bm.get_center()
                ang, face = toward(am, goal_pt)
                am.pose["face"] = face
                wind = min(1.0, a / 0.3)
                fling = max(0.0, min(1.0, (a - 0.3) / 0.15))
                fa = st["a0"]["fa1"] + (-0.9 - st["a0"]["fa1"]) * wind * (1 - fling) + (2.2 - st["a0"]["fa1"]) * fling * (1 - max(0.0, (a - 0.8) / 0.2))
                am.set_pose({**am.pose, "fa1": fa, "fa2": fa + 0.3, "lean": 0.12 * fling * (1 - a)})
                if b_person:
                    catch = max(0.0, min(1.0, (a - 0.55) / 0.2))
                    bang, _ = toward(bm, am.get_center())
                    bm.set_pose(blend(st["b0"], {**st["b0"], "fa1": bang, "fa2": bang + 0.2, "ba1": bang - 0.2,
                                                 "ba2": bang, **P.MOODS["surprised"]},
                                      ("fa1", "fa2", "ba1", "ba2") + P.FACE_KEYS, catch * min(1.0, (1 - a) / 0.2 + 0.4)))
                if thing is not None:
                    tn, tm = thing
                    if a < 0.42:
                        tm.move_to(st["hand_a"].get_center() + UP * tm.height * 0.3)
                        st["from"] = tm.get_center().copy()
                    else:
                        h = min(1.0, (a - 0.42) / 0.45)
                        start_pt = st.get("from", tm.get_center())
                        goal = goal_pt + UP * tm.height * 0.3
                        arc_h = 0.25 * np.linalg.norm(goal - start_pt) + 0.5
                        tm.move_to(start_pt + (goal - start_pt) * h + UP * arc_h * math.sin(math.pi * h))
                        spin = 2 * math.pi * h * (0 if h >= 1 else 1)
                        tm.rotate(spin - st.get("spin", 0.0))
                        st["spin"] = spin
            elif v == "shake":
                pump = 0.18 * math.sin(max(0.0, tt - 0.35 * dur) * 14.0) if a > 0.4 else 0.0
                reach = max(0.0, min(1.0, (a - 0.3) / 0.12)) * min(1.0, max(0.0, (1 - a) / 0.12))
                target = {"fa1": 0.95 + pump, "fa2": 1.45 + pump, "smile": 0.9, "joy": 0.5}
                am.set_pose(blend(st["a0"], {**st["a0"], **target}, tuple(target), reach))
                if b_person:
                    bm.set_pose(blend(st["b0"], {**st["b0"], **target}, tuple(target), reach))
            elif v == "push":
                shove = max(0.0, min(1.0, (a - 0.35) / 0.2))
                back = min(1.0, max(0.0, (1 - a) / 0.25))
                am.set_pose(blend(st["a0"], {**st["a0"], "fa1": 1.45, "fa2": 1.55, "ba1": 1.35, "ba2": 1.5,
                                             "lean": 0.22, **P.MOODS["angry"]},
                                  ("fa1", "fa2", "ba1", "ba2", "lean") + P.FACE_KEYS, shove * back))
                if "bstart" not in st:
                    st["bstart"] = bm.get_center().copy() if not b_person else bm.feet().copy()
                slide = rate_functions.ease_out_cubic(max(0.0, min(1.0, (a - 0.45) / 0.4)))
                off = np.array([st.get("side", 1.0) * 0.35 * unit(am) * slide, 0, 0])
                if b_person:
                    bm.shift(st["bstart"] + off - bm.feet())
                    bm.set_pose(blend(st["b0"], {**st["b0"], "lean": -0.25, "fa1": 2.2, "ba1": 2.5, **P.MOODS["shocked"]},
                                      ("lean", "fa1", "ba1") + P.FACE_KEYS, math.sin(math.pi * slide) if slide < 1 else 0.0)
                                if a < 0.95 else {**bm.pose, **P.MOODS["annoyed"]})
                else:
                    bm.move_to(st["bstart"] + off)
            elif v == "tug":
                pull = math.sin(tt * 5.0)
                for who, p0, sgn in ((am, st["a0"], 1.0), (bm, st.get("b0"), -1.0)):
                    if not isinstance(who, P.Person):
                        continue
                    ang, _ = toward(who, (bm if who is am else am).get_center())
                    q = {**p0, "fa1": ang, "fa2": ang, "ba1": ang - 0.1, "ba2": ang, "lean": -0.22 + 0.07 * pull * sgn,
                         "fl1": 0.45, "fl2": 0.1, "bl1": -0.2, "bl2": -0.3, **P.MOODS["furious" if sgn > 0 else "angry"]}
                    who.set_pose(blend(p0, q, ("fa1", "fa2", "ba1", "ba2", "lean", "fl1", "fl2", "bl1", "bl2") + P.FACE_KEYS, k))
                    if who is am:
                        am.shift(RIGHT * st.get("side", 1.0) * -0.006 * pull)
                ends = [am.hand.get_center(), bm.hand.get_center() if b_person else bm.get_center()]
                mid = (ends[0] + ends[1]) / 2 + DOWN * 0.08 * (1 - abs(pull))
                st["rope"].set_points_smoothly([ends[0], mid, ends[1]])
                if thing is not None:
                    thing[1].move_to(mid)
            elif v == "argue":
                said = words or ["#@%!", "?!", "No!", "#@!"]
                n = max(2, len(said))
                turn = min(n - 1, int(a * n))
                who, other = (am, bm) if turn % 2 == 0 else (bm, am)
                for x, p0 in ((am, st["a0"]), (bm, st.get("b0"))):
                    if not isinstance(x, P.Person):
                        continue
                    talking = x is who
                    o = 0.5 + 0.5 * math.sin(tt * 15.0 + (0 if x is am else 2))
                    q = {**p0, **P.MOODS["angry" if talking else "annoyed"], "mouth": abs(o) if talking else 0.0,
                         "lean": 0.12 if talking else -0.04, "fa1": 1.2 if talking else p0["fa1"],
                         "fa2": 2.0 + 0.4 * math.sin(tt * 9.0) if talking else p0["fa2"]}
                    q = blend(p0, q, ("mouth", "lean", "fa1", "fa2") + P.FACE_KEYS, k)
                    q["face"] = 1.0 if (other.get_center()[0] >= x.get_center()[0]) else -1.0
                    x.set_pose(q)
                if st.get("turn") != turn:
                    st["turn"] = turn
                    for b in st["bubbles"]:
                        self.remove(b)
                    st["bubbles"] = []
                    if isinstance(who, P.Person):
                        import kit
                        bub = kit.bubble(who.head, said[turn % len(said)], {"size": 0.2, "w": 2.4})
                        bub.set_z_index(max(x.z_index for x in who.get_family()) + 2)
                        self.add(bub)
                        st["bubbles"] = [bub]
                        st["anchor"], st["at"] = who.head, who.head.get_center().copy()
                if st["bubbles"]:
                    c = st["anchor"].get_center()
                    st["bubbles"][0].shift(c - st["at"])
                    st["at"] = c.copy()
            elif v == "whisper":
                cup = max(0.0, min(1.0, (a - 0.3) / 0.15)) * min(1.0, max(0.0, (1 - a) / 0.15))
                am.set_pose(blend(st["a0"], {**st["a0"], "fa1": 0.35, "fa2": 2.75, "lean": 0.18, "nod": 0.1,
                                             **P.MOODS["playful"]}, ("fa1", "fa2", "lean", "nod") + P.FACE_KEYS, cup))
                if b_person and a > 0.55:
                    hear = min(1.0, (a - 0.55) / 0.2)
                    bm.set_pose(blend(st["b0"], {**st["b0"], **P.MOODS["surprised"]}, P.FACE_KEYS, hear))
                if words and not st["bubbles"] and a > 0.35:
                    import kit
                    bub = kit.bubble(am.head, words[0], {"size": 0.15, "w": 2.0})
                    for x in bub.family_members_with_points():
                        if isinstance(x, Line):
                            x.set_stroke(opacity=0.6)
                    bub.set_z_index(max(x.z_index for x in am.get_family()) + 2)
                    self.add(bub)
                    st["bubbles"] = [bub]
                if st["bubbles"] and st["bubbles"][0] is not None and a > 0.85:
                    self.remove(st["bubbles"][0])
                    st["bubbles"] = [None]

        def stop():
            if "rope" in st:
                self.remove(st["rope"])
            for b in st.get("bubbles", []):
                if b is not None:
                    self.remove(b)
            if v in ("tug", "argue"):           # back to standing as they were
                for x, p0 in ((am, st["a0"]), (bm, st.get("b0"))):
                    if isinstance(x, P.Person):
                        x.set_pose({**x.pose, **{k_: p0[k_] for k_ in ("fa1", "fa2", "ba1", "ba2", "lean", "fl1",
                                                                         "fl2", "bl1", "bl2", "mouth")}})
            if thing is not None and v in ("give", "throw"):
                tn, tm = thing
                if b_person:                    # it stays in B's hands (a free one)
                    hb = st.get("hand_b") or self._grip(bm, tm)
                    self._use_hand(bm, hb)
                    self.follows.append([tm, hb, hb.get_center().copy(), None])
                    bm.carrying = True
                    bm.set_pose({**bm.pose, **{k_: P.carry_pose()[k_] for k_ in ("fa1", "fa2", "ba1", "ba2")}})
                    tm.move_to(hb.get_center() + UP * tm.height * 0.4)
                if st.get("hand_a") is not None:
                    self._free_hand(am, st["hand_a"])
                am.carrying = any(r[1] in (am.hand, getattr(am, "hand_b", None)) for r in self.follows)
            if v == "throw" and abs(st.get("spin", 0.0)) > 1e-4 and thing is not None:
                thing[1].rotate(-st["spin"])
        self.tweens.append(Call(t0, t1, start, step, stop, rate_functions.linear))


# ---------------------------------------------------------------- eyes on a map --------------------------------------

EYE_MOODS = {
    # brow tilt (+: inner ends down, cross), brow height, pupil size, lids (0 open .. 1 shut), pupils' look
    "angry": (0.42, 0.0, 0.42, 0.18, (0.0, -0.12)), "furious": (0.6, -0.05, 0.36, 0.3, (0.0, -0.1)),
    "sad": (-0.4, 0.05, 0.42, 0.35, (0.0, -0.3)), "worried": (-0.3, 0.12, 0.34, 0.0, (0.0, 0.0)),
    "scared": (-0.25, 0.25, 0.24, 0.0, (0.0, 0.0)), "surprised": (0.0, 0.3, 0.26, 0.0, (0.0, 0.0)),
    "suspicious": (0.2, -0.02, 0.4, 0.55, (0.35, 0.0)), "smug": (-0.08, 0.06, 0.4, 0.5, (0.2, 0.1)),
    "happy": (-0.1, 0.16, 0.42, 0.0, (0.0, 0.1)), "calm": (0.0, 0.08, 0.4, 0.15, (0.0, 0.0)),
    "sleepy": (0.0, 0.02, 0.4, 0.7, (0.0, -0.2)),
}


class Eyes(VGroup):
    """A pair of big cartoon eyes and brows set on a region of a map (a country glaring at its neighbour): `ent e
    eyes angry on REGION` (or `at M.place`), `size W` across; `emote E MOOD` changes the look (with a blink),
    `look E at T` turns the pupils."""

    def __init__(self, mood: str = "angry", w: float = 1.8):
        super().__init__()
        ink, white = look.col("ink"), "#FFFFFF"
        r = w / 4.4
        self.r, self.w = r, w
        self.whites = [Circle(radius=r, fill_color=white, fill_opacity=1, stroke_color=ink, stroke_width=r * 9)
                       .move_to([s_ * r * 1.12, 0, 0]) for s_ in (-1, 1)]
        self.pupils = [Circle(radius=r * 0.4, fill_color=ink, fill_opacity=1, stroke_width=0) for _ in range(2)]
        self.lids = [VMobject(fill_color="#E9E2D2", fill_opacity=1, stroke_color=ink, stroke_width=r * 6) for _ in range(2)]
        self.brows = [Polygon(*[np.zeros(3)] * 4, fill_color=ink, fill_opacity=1, stroke_width=0) for _ in range(2)]
        self.add(*self.whites, *self.pupils, *self.lids, *self.brows)
        self.gaze = np.zeros(2)
        self.mood = None
        self.set_mood(mood)

    def set_mood(self, mood: str, blink: float = 0.0) -> None:
        tilt, high, ps, lids, gaze = EYE_MOODS.get(str(mood).lower(), EYE_MOODS["angry"])
        self.mood, self.cfg = mood, (tilt, high, ps, lids, gaze)
        self._draw(blink)

    def _draw(self, blink: float = 0.0) -> None:
        tilt, high, ps, lids, gaze = self.cfg
        r = self.r
        for i, s_ in enumerate((-1, 1)):
            c = self.whites[i].get_center()
            look_ = np.array([*(np.array(gaze) + self.gaze), 0.0])
            p = self.pupils[i]
            p.scale_to_fit_width(2 * r * ps)
            p.move_to(c + look_ * r * 0.45)
            shut = max(0.0, min(1.0, max(lids, blink)))
            # the lid: the top of the eye down to `shut`
            h = r * (1 - 2 * shut)
            t0 = math.asin(max(-0.999, min(0.999, h / r)))
            pts = [c + np.array([r * math.cos(t), r * math.sin(t), 0.0]) for t in np.linspace(t0, math.pi - t0, 16)]
            lid = self.lids[i]
            if shut > 0.02:
                lid.set_points_as_corners([*pts, pts[0]])
                lid.set_opacity(1)
            else:
                lid.set_points_as_corners([c, c + RIGHT * 1e-3, c])
                lid.set_fill(opacity=0).set_stroke(opacity=0)
            # the brow: a thick bar over the eye, its inner end down by `tilt`
            y = c[1] + r * (1.15 + high) - r * 0.25 * shut
            # the inner end (toward the other eye) down by `tilt` (cross), up when it is negative (sad)
            a = np.array([c[0] - s_ * r * 0.85, y - tilt * r * 0.4, 0.0])
            b = np.array([c[0] + s_ * r * 1.0, y + tilt * r * 0.4, 0.0])
            th = r * 0.32
            n = np.array([0.0, th / 2, 0.0])
            self.brows[i].set_points_as_corners([a - n, b - n, b + n, a + n, a - n])

    def look_toward(self, d) -> None:
        v = np.array(d[:2], dtype=float)
        n = float(np.linalg.norm(v))
        self.gaze = v / n * 0.55 if n > 1e-6 else np.zeros(2)
        self._draw()
