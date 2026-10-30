"""Animals drawn with the same pen as the people, posed the same way, and ridden.

    ent h animal horse [color C] [mood FACE] [plain] [face left] [size H] at X,Y        (its feet at X,Y)

Kinds: horse pony donkey zebra | cow ox bull buffalo | elephant | camel | dog wolf fox | cat tiger lion leopard |
sheep goat pig deer rat bear | chicken rooster peacock duck eagle bird crow parrot.

An animal is a person to the renderer (people.Person): the same pose numbers drive it, so a person's verbs work on
it: walk and run (a four-legged gait: the legs in diagonal pairs), turn, jump, nod, look, emote and talk (the same
doodle face, set on its head), carry (what it carries goes on its back), sit (it lies down). Its own: graze (the head
down to the grass), rear (up on its hind legs), fly (a bird: its wings beating, along an arc). A person rides one:
`ride P H` (P hops up into the saddle and goes where it goes, facing its way), `dismount P [to X,Y]`.

Each animal is drawn in body units, a person's (the peg figure is about 0.9 tall): a horse's back is 0.6 up, so a
rider sits on it in proportion. Its parts (the body, the head and neck, each leg, the tail, a wing) are rigid shapes
turned about their joints by the pose.
"""

from __future__ import annotations

import math

import numpy as np
from manim import Circle, Dot, Ellipse, Line, VGroup, VMobject

import people as P
from look import col

INK = None                                     # set per animal (the look's ink)


def tint(hex_colour: str, k: float) -> str:
    """A colour toward white (k > 0) or black (k < 0)."""
    h = hex_colour.lstrip("#")
    if len(h) != 6:
        return hex_colour
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    if k >= 0:
        r, g, b = (int(v + (255 - v) * k) for v in (r, g, b))
    else:
        r, g, b = (int(v * (1 + k)) for v in (r, g, b))
    return "#%02X%02X%02X" % (r, g, b)


def blob(pts, fill, w, ink=None, op=1.0):
    return P._blob(pts, fill, ink or INK, w, op)


def poly(pts, fill, w, ink=None, op=1.0):
    return P._poly(pts, fill, ink or INK, w, op)


def stroke(pts, c, w):
    return P._stroke(pts, c, w)


def fill_only(pts, fill, op=1.0, smooth=True):
    m = VMobject(fill_color=fill, fill_opacity=op, stroke_width=0)
    q = [np.array([x, y, 0.0]) for x, y in pts]
    (m.set_points_smoothly if smooth else m.set_points_as_corners)([*q, q[0]])
    return m


def tube(centre, widths, fill, w, ink=None):
    """A tapering limb along a centre line (a trunk, a neck, a tail): its outline, filled."""
    c = np.array(centre, dtype=float)
    n = len(c)
    left, right = [], []
    for i in range(n):
        d = c[min(i + 1, n - 1)] - c[max(i - 1, 0)]
        d = d / (np.linalg.norm(d) or 1.0)
        nrm = np.array([-d[1], d[0]])
        left.append(c[i] + nrm * widths[i] / 2)
        right.append(c[i] - nrm * widths[i] / 2)
    return blob([tuple(p) for p in left + right[::-1]], fill, w, ink)


# ---------------------------------------------------------------- limbs ----------------------------------------------

def leg(L, wt, wb, coat, ow, foot="hoof", foot_c="#3A2E26", bend=0.0):
    """A leg hanging from its joint (0, 0) to the ground (0, -L): tapering, a knee, a hoof, a paw or a toe."""
    k = -L * 0.5
    pts = [(-wt / 2, 0.05), (wt / 2, 0.05), (wt * 0.42 + bend, k), (wb / 2 + bend * 0.4, -L + 0.03),
           (-wb / 2 + bend * 0.4, -L + 0.03), (-wt * 0.42 + bend, k)]
    g = VGroup(blob(pts, coat, ow))
    x0 = bend * 0.4
    if foot == "hoof":
        g.add(poly([(x0 - wb * 0.62, -L + 0.045), (x0 + wb * 0.62, -L + 0.045), (x0 + wb * 0.72, -L),
                    (x0 - wb * 0.6, -L)], foot_c, ow * 0.8))
    elif foot == "paw":
        g.add(Ellipse(width=wb * 1.6, height=wb * 0.75, fill_color=coat, fill_opacity=1, stroke_color=INK,
                      stroke_width=ow * 0.8).move_to([x0 + wb * 0.25, -L + wb * 0.3, 0]))
        for i in (-1, 0, 1):
            g.add(Line([x0 + wb * 0.25 + i * wb * 0.35, -L + wb * 0.05, 0], [x0 + wb * 0.25 + i * wb * 0.35,
                                                                               -L + wb * 0.3, 0],
                       stroke_color=INK, stroke_width=ow * 0.5))
    elif foot == "pad":                         # an elephant's: toenails along the front
        g.add(poly([(x0 - wb / 2, -L + 0.01), (x0 + wb / 2, -L + 0.01), (x0 + wb / 2, -L), (x0 - wb / 2, -L)],
                   tint(coat, -0.2), ow * 0.6))
        for i in (-1, 0, 1):
            g.add(Ellipse(width=wb * 0.2, height=wb * 0.13, fill_color="#F1E8D4", fill_opacity=1, stroke_color=INK,
                          stroke_width=ow * 0.5).move_to([x0 + wb * 0.18 + i * wb * 0.25, -L + wb * 0.08, 0]))
    return g


def bird_leg(L, c, ow):
    """A bird's thin leg and three toes."""
    return VGroup(Line([0, 0, 0], [0, -L + 0.004, 0], stroke_color=c, stroke_width=ow * 1.5),
                  *(Line([0, -L + 0.004, 0], [dx, -L, 0], stroke_color=c, stroke_width=ow * 1.3)
                    for dx in (0.035, 0.012, -0.02)))


def ear(pts, c, inner, ow):
    g = VGroup(blob(pts, c, ow))
    if inner:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        g.add(fill_only([(cx + (x - cx) * 0.55, cy + (y - cy) * 0.55) for x, y in pts], inner))
    return g


def scallop(cx, cy, rx, ry, n, depth, fill, ow, a0=0, a1=360):
    """A woolly cloud: an ellipse whose edge bulges out in n puffs."""
    pts = []
    for i in range(n * 6 + 1):
        t = math.radians(a0 + (a1 - a0) * i / (n * 6))
        bump = depth * abs(math.sin(i * math.pi / 6))
        pts.append((cx + (rx + bump) * math.cos(t), cy + (ry + bump) * math.sin(t)))
    return blob(pts, fill, ow)


# ---------------------------------------------------------------- the species ----------------------------------------
# Each draws its parts, x toward the face, the ground at y 0, and gives its joints:
#   front, back: where the near legs hang from (the far ones a little behind); neck: where the head turns; tail;
#   saddle: where a rider sits (and what it carries goes); face: the eyes' middle in the head's frame, and face_k
# Parts: body (over the legs), legs {fn bn ff bf} (near and far, front and back; a bird: fn bn), head (behind the
# body: a neck goes into it), over (the head's parts over the body: an elephant's ear), tail, wing, extra (on the body)

def _horse(c, ow, kind, mods):
    coat = {"horse": "#9A6B43", "pony": "#C79B6B", "donkey": "#9A938A", "zebra": "#F4F1EA"}[kind]
    coat = col(mods["color"]) if mods.get("color") else coat
    mane = {"horse": "#3A2A1E", "pony": "#F1E3C4", "donkey": "#4A4440", "zebra": "#22201E"}[kind]
    s = 0.82 if kind in ("donkey", "pony") else 1.0
    dark, light = tint(coat, -0.18), tint(coat, 0.35)
    L = 0.4 * s
    body = VGroup(blob([(0.38 * s, L + 0.07 * s), (0.36 * s, L + 0.16 * s), (0.15 * s, L + 0.2 * s),
                        (0.0, L + 0.185 * s), (-0.3 * s, L + 0.22 * s), (-0.42 * s, L + 0.15 * s),
                        (-0.43 * s, L + 0.03 * s), (-0.3 * s, L - 0.07 * s), (0.0, L - 0.09 * s),
                        (0.25 * s, L - 0.07 * s), (0.37 * s, L - 0.02 * s)], coat, ow))
    body.add(fill_only([(0.25 * s, L - 0.05 * s), (0.0, L - 0.075 * s), (-0.28 * s, L - 0.055 * s),
                        (-0.1 * s, L - 0.02 * s), (0.15 * s, L - 0.025 * s)], light, 0.7))
    if kind in ("donkey",):
        body.add(fill_only([(0.3 * s, L - 0.02 * s), (0.0, L - 0.08 * s), (-0.3 * s, L - 0.05 * s),
                            (-0.1 * s, L + 0.0), (0.2 * s, L + 0.0)], "#EDE7DD"))
        body.add(stroke([(0.18 * s, L + 0.19 * s), (0.2 * s, L + 0.02 * s)], "#4A4440", ow * 1.3))   # its cross
    if kind == "zebra":
        for i, x in enumerate(np.linspace(-0.36, 0.3, 9)):
            body.add(stroke([(x * s - 0.02, L + 0.19 * s), (x * s + 0.01, L + 0.07 * s), (x * s - 0.01, L - 0.04 * s)],
                            "#22201E", ow * (2.6 if i % 2 else 2.0)))
    lw = 0.085 * s
    legs = {n: leg(L, lw, 0.05 * s, coat if n[1] == "n" else dark, ow, "hoof",
                   bend=0.015 if n[0] == "b" else 0.0) for n in ("fn", "bn", "ff", "bf")}
    if kind == "zebra":
        for n, lg in legs.items():
            for y in np.linspace(-0.08, -L + 0.1, 4):
                lg.add(stroke([(-lw * 0.42, y), (lw * 0.42, y - 0.012)], "#22201E", ow * 1.6))
    head = VGroup()
    neckhead = [(-0.08 * s, 0.0), (-0.05 * s, 0.13 * s), (0.04 * s, 0.25 * s), (0.12 * s, 0.31 * s),
                (0.2 * s, 0.29 * s), (0.31 * s, 0.2 * s), (0.36 * s, 0.13 * s), (0.335 * s, 0.085 * s),
                (0.25 * s, 0.09 * s), (0.17 * s, 0.13 * s), (0.13 * s, 0.05 * s), (0.11 * s, -0.04 * s)]
    long_ear = kind == "donkey"
    e = ([(0.07 * s, 0.29 * s), (0.02 * s, 0.47 * s), (0.11 * s, 0.31 * s)] if long_ear else
         [(0.08 * s, 0.3 * s), (0.085 * s, 0.39 * s), (0.125 * s, 0.31 * s)])
    head.add(ear([(x - 0.03 * s, y - 0.005) for x, y in e], dark, None, ow))
    head.add(blob(neckhead, coat, ow))
    head.add(fill_only([(0.27 * s, 0.19 * s), (0.345 * s, 0.13 * s), (0.33 * s, 0.09 * s), (0.25 * s, 0.1 * s)],
                       light if kind != "zebra" else "#3A3631", 0.9))
    head.add(Dot([0.315 * s, 0.14 * s, 0], radius=0.009 * s, color=INK))
    if kind == "zebra":
        for x in np.linspace(-0.04, 0.16, 5):
            head.add(stroke([(x * s, 0.03 * s + x * 1.2 * s), (x * s + 0.07 * s, 0.0 + x * 1.0 * s)], "#22201E", ow * 1.8))
    head.add(ear(e, coat, tint(coat, -0.35), ow))
    if kind in ("donkey", "zebra"):              # a short upright mane
        head.add(blob([(-0.075 * s, 0.02 * s), (-0.07 * s, 0.14 * s), (0.02 * s, 0.27 * s), (0.08 * s, 0.31 * s),
                       (0.05 * s, 0.25 * s), (-0.02 * s, 0.13 * s), (-0.04 * s, 0.02 * s)], mane, ow * 0.8))
    else:                                       # a flowing mane and a forelock
        head.add(blob([(-0.1 * s, -0.02 * s), (-0.1 * s, 0.13 * s), (0.0, 0.26 * s), (0.09 * s, 0.33 * s),
                       (0.06 * s, 0.25 * s), (0.02 * s, 0.19 * s), (-0.02 * s, 0.1 * s), (-0.035 * s, 0.0)], mane, ow),
                 blob([(0.1 * s, 0.31 * s), (0.17 * s, 0.31 * s), (0.15 * s, 0.25 * s), (0.12 * s, 0.27 * s)], mane, ow * 0.7))
    extra = VGroup()
    saddle = (0.0, L + 0.205 * s)
    if not mods.get("plain") and kind in ("horse", "pony"):
        blanket = col(mods.get("cloth") or "#B83227")
        extra.add(poly([(-0.12 * s, L + 0.2 * s), (0.15 * s, L + 0.2 * s), (0.13 * s, L + 0.04 * s),
                        (-0.11 * s, L + 0.04 * s)], blanket, ow * 0.8),
                  stroke([(-0.11 * s, L + 0.055 * s), (0.13 * s, L + 0.055 * s)], "#F2C14E", ow * 1.4),
                  blob([(-0.13 * s, L + 0.26 * s), (-0.1 * s, L + 0.21 * s), (0.0, L + 0.2 * s), (0.11 * s, L + 0.21 * s),
                        (0.13 * s, L + 0.25 * s), (0.1 * s, L + 0.18 * s), (-0.09 * s, L + 0.18 * s)], "#6B4226", ow),
                  Line([0.0, L + 0.18 * s, 0], [0.0, L - 0.03 * s, 0], stroke_color="#3A2A1E", stroke_width=ow * 1.2),
                  poly([(-0.02 * s, L - 0.03 * s), (0.02 * s, L - 0.03 * s), (0.025 * s, L - 0.05 * s),
                        (-0.025 * s, L - 0.05 * s)], "#B8BEC2", ow * 0.6))
        head.add(stroke([(0.15 * s, 0.27 * s), (0.25 * s, 0.13 * s)], "#3A2A1E", ow * 1.2),      # a bridle
                 stroke([(0.26 * s, 0.19 * s), (0.31 * s, 0.1 * s)], "#3A2A1E", ow * 1.2),
                 Dot([0.25 * s, 0.13 * s, 0], radius=0.008 * s, color="#F2C14E"))
        saddle = (0.0, L + 0.21 * s)
    if kind == "donkey" and not mods.get("plain"):  # panniers
        extra.add(poly([(-0.16 * s, L + 0.18 * s), (0.08 * s, L + 0.18 * s), (0.06 * s, L - 0.01 * s),
                        (-0.14 * s, L - 0.01 * s)], "#C9A66B", ow * 0.8),
                  *(stroke([(-0.15 * s, y), (0.07 * s, y)], "#9A7B4F", ow * 0.7) for y in (L + 0.12 * s, L + 0.06 * s)))
    tail_c = mane
    if kind in ("donkey", "zebra"):
        tail = VGroup(tube([(0, 0), (-0.04 * s, -0.08 * s), (-0.05 * s, -0.22 * s)], [0.025 * s, 0.02 * s, 0.015 * s], coat, ow * 0.8),
                      blob([(-0.035 * s, -0.2 * s), (-0.07 * s, -0.22 * s), (-0.07 * s, -0.3 * s), (-0.04 * s, -0.32 * s),
                            (-0.03 * s, -0.24 * s)], tail_c, ow * 0.8))
    else:
        tail = VGroup(blob([(0.01, 0.015), (-0.07 * s, 0.0), (-0.11 * s, -0.12 * s), (-0.11 * s, -0.3 * s),
                            (-0.06 * s, -0.34 * s), (-0.05 * s, -0.2 * s), (-0.01 * s, -0.06 * s)], tail_c, ow))
    return dict(body=body, legs=legs, head=head, tail=tail, extra=extra, L=L,
                front=(0.27 * s, L), back=(-0.29 * s, L + 0.02 * s), far=-0.05 * s,
                neck=(0.3 * s, L + 0.1 * s), tailroot=(-0.42 * s, L + 0.17 * s), saddle=saddle,
                face=(0.19 * s, 0.235 * s), face_k=0.95 * s, width=0.85 * s, coat=coat)


def _bovine(c, ow, kind, mods):
    coat = {"cow": "#F4F1EA", "ox": "#ECE6DA", "bull": "#5A3A2A", "buffalo": "#3A3631"}[kind]
    coat = col(mods["color"]) if mods.get("color") else coat
    dark = tint(coat, -0.15)
    L = 0.33
    body = VGroup(blob([(0.36, L + 0.12), (0.33, L + 0.25), (0.1, L + 0.28), (-0.2, L + 0.28), (-0.4, L + 0.27),
                        (-0.45, L + 0.12), (-0.4, L - 0.03), (-0.1, L - 0.06), (0.2, L - 0.05), (0.35, L + 0.02)],
                       coat, ow))
    if kind == "cow":                           # its patches and an udder
        for pts in ([(-0.3, L + 0.26), (-0.12, L + 0.27), (-0.1, L + 0.15), (-0.22, L + 0.09), (-0.32, L + 0.16)],
                    [(0.05, L + 0.2), (0.18, L + 0.22), (0.2, L + 0.1), (0.08, L + 0.06)],
                    [(-0.42, L + 0.1), (-0.36, L + 0.12), (-0.35, L + 0.02), (-0.41, L + 0.0)]):
            body.add(blob(pts, "#2A2522", 0))
        body.add(blob([(-0.24, L - 0.045), (-0.12, L - 0.05), (-0.13, L - 0.11), (-0.23, L - 0.11)], "#F2A7A0", ow * 0.8))
    if kind == "ox":                            # an Indian bullock's hump and dewlap
        body.add(blob([(0.14, L + 0.27), (0.2, L + 0.35), (0.28, L + 0.34), (0.32, L + 0.25)], coat, ow),
                 blob([(0.33, L + 0.05), (0.4, L - 0.04), (0.42, L + 0.08)], coat, ow * 0.8))
    legs = {n: leg(L, 0.085, 0.055, coat if n[1] == "n" else dark, ow, "hoof", foot_c="#2A2522") for n in
            ("fn", "bn", "ff", "bf")}
    head = VGroup()
    hc = coat if kind != "cow" else "#F4F1EA"
    horn = "#F1E8D4" if kind != "buffalo" else "#A39E96"
    hornw = {"cow": 0.05, "ox": 0.1, "bull": 0.09, "buffalo": 0.13}[kind]
    if kind == "buffalo":                       # wide horns swept back
        head.add(tube([(0.0, 0.07), (-0.08, 0.1), (-0.15, 0.06), (-0.16, -0.01)], [0.05, 0.04, 0.025, 0.01], horn, ow))
    head.add(ear([(-0.01, 0.04), (-0.1, 0.03), (-0.04, 0.0)], dark, None, ow))
    head.add(blob([(-0.05, -0.02), (-0.03, 0.07), (0.06, 0.1), (0.14, 0.07), (0.2, -0.02), (0.22, -0.1),
                   (0.17, -0.14), (0.09, -0.12), (0.02, -0.09)], hc, ow))
    head.add(blob([(0.13, -0.06), (0.22, -0.07), (0.22, -0.13), (0.15, -0.14)], "#E8A99A" if kind == "cow" else tint(coat, -0.25), ow * 0.8),
             Dot([0.2, -0.095, 0], radius=0.008, color=INK))
    if kind == "cow":
        head.add(blob([(0.02, 0.07), (0.1, 0.09), (0.09, 0.02), (0.03, 0.03)], "#2A2522", 0))
    if kind != "buffalo":
        head.add(tube([(0.05, 0.08), (0.06, 0.08 + hornw * 0.6), (0.02, 0.08 + hornw)], [0.03, 0.022, 0.006], horn, ow * 0.8))
    if kind == "ox" and not mods.get("plain"):  # painted horns and a garland, as at Pongal
        head.add(tube([(0.05, 0.08), (0.06, 0.08 + hornw * 0.6), (0.02, 0.08 + hornw)], [0.03, 0.022, 0.006], "#3E7CB1", ow * 0.8))
    head.add(ear([(0.0, 0.05), (-0.1, 0.05), (-0.05, 0.015)], hc, "#E8A99A", ow))
    tail = VGroup(tube([(0, 0), (-0.03, -0.1), (-0.04, -0.26)], [0.028, 0.02, 0.016], coat, ow * 0.8),
                  blob([(-0.03, -0.24), (-0.065, -0.27), (-0.055, -0.34), (-0.025, -0.33)], "#2A2522", ow * 0.7))
    extra = VGroup()
    if kind == "ox" and not mods.get("plain"):
        extra.add(*(Dot([x, L + 0.24 - 0.05 * (1 - ((x - 0.3) / 0.06) ** 2), 0], radius=0.012, color=["#E4572E", "#F2C14E"][i % 2])
                    for i, x in enumerate(np.linspace(0.24, 0.36, 6))))
    return dict(body=body, legs=legs, head=head, tail=tail, extra=extra, L=L, front=(0.26, L + 0.02),
                back=(-0.32, L + 0.02), far=-0.05, neck=(0.34, L + 0.18), tailroot=(-0.44, L + 0.24),
                saddle=(-0.05, L + 0.28 + (0.0 if kind != "ox" else 0.0)), face=(0.09, 0.03), face_k=1.05,
                width=0.85, coat=coat)


def _elephant(c, ow, kind, mods):
    coat = col(mods["color"]) if mods.get("color") else "#9EA3A8"
    dark = tint(coat, -0.18)
    L = 0.42
    body = VGroup(blob([(0.42, L + 0.18), (0.36, L + 0.4), (0.05, L + 0.48), (-0.3, L + 0.45), (-0.5, L + 0.3),
                        (-0.5, L + 0.05), (-0.35, L - 0.08), (0.1, L - 0.08), (0.38, L + 0.0)], coat, ow))
    body.add(*(stroke([(-0.46, y), (-0.4, y - 0.01)], dark, ow * 0.8) for y in (L + 0.1, L + 0.15)))
    royal = not mods.get("plain")
    extra = VGroup()
    saddle = (-0.05, L + 0.47)
    if royal:                                   # a caparison: red cloth, a gold border, tassels
        extra.add(blob([(-0.3, L + 0.44), (0.18, L + 0.47), (0.22, L + 0.12), (0.0, L + 0.06), (-0.33, L + 0.12)],
                       "#B83227", ow),
                  stroke([(-0.32, L + 0.15), (0.0, L + 0.09), (0.21, L + 0.15)], "#F2C14E", ow * 2.2),
                  *(Circle(radius=0.016, fill_color="#F2C14E", fill_opacity=1, stroke_color=INK, stroke_width=ow * 0.5)
                    .move_to([x, L + 0.1 - 0.025 * math.sin((x + 0.3) * 6), 0]) for x in np.linspace(-0.28, 0.17, 6)),
                  *(Dot([x, y, 0], radius=0.01, color="#F2C14E") for x, y in ((-0.15, L + 0.3), (0.05, L + 0.32),
                                                                               (-0.05, L + 0.22))))
        if mods.get("howdah"):                   # a canopied seat on top
            extra.add(poly([(-0.22, L + 0.46), (0.12, L + 0.48), (0.12, L + 0.6), (-0.22, L + 0.58)], "#D4A017", ow),
                      *(Line([x, L + 0.58, 0], [x, L + 1.3, 0], stroke_color="#8C6E2E", stroke_width=ow * 1.6)
                        for x in (-0.24, 0.14)),
                      blob([(-0.3, L + 1.28), (-0.05, L + 1.46), (0.19, L + 1.29), (-0.05, L + 1.24)], "#B83227", ow),
                      stroke([(-0.3, L + 1.28), (-0.05, L + 1.24), (0.19, L + 1.29)], "#F2C14E", ow * 1.6),
                      Dot([-0.05, L + 1.48, 0], radius=0.015, color="#F2C14E"))
            saddle = (-0.05, L + 0.6)
    legs = {n: leg(L, 0.17, 0.155, coat if n[1] == "n" else dark, ow, "pad") for n in ("fn", "bn", "ff", "bf")}
    head = VGroup(blob([(-0.12, -0.05), (-0.08, 0.14), (0.05, 0.22), (0.17, 0.17), (0.24, 0.05), (0.25, -0.08),
                        (0.15, -0.12), (-0.02, -0.14)], coat, ow))
    trunk = tube([(0.21, -0.04), (0.27, -0.16), (0.28, -0.3), (0.31, -0.4), (0.36, -0.42), (0.38, -0.38)],
                 [0.12, 0.1, 0.075, 0.06, 0.045, 0.035], coat, ow)
    head.add(trunk, *(stroke([(0.22 + i * 0.012, -0.12 - i * 0.07), (0.31 + i * 0.008, -0.13 - i * 0.07)], dark, ow * 0.7)
                      for i in range(4)))
    head.add(tube([(0.17, -0.1), (0.25, -0.17), (0.33, -0.18)], [0.04, 0.028, 0.008], "#F7F3E8", ow * 0.8))
    if royal:                                   # a gold forehead plate
        head.add(blob([(0.06, 0.2), (0.15, 0.19), (0.17, 0.15), (0.1, 0.15)], "#F2C14E", ow * 0.8),
                 Dot([0.12, 0.175, 0], radius=0.011, color="#B83227"))
    over = VGroup(blob([(-0.02, 0.15), (-0.16, 0.18), (-0.24, 0.06), (-0.22, -0.13), (-0.12, -0.24), (-0.03, -0.15),
                        (0.02, 0.0)], tint(coat, -0.08), ow),
                  stroke([(-0.06, 0.1), (-0.17, 0.08), (-0.18, -0.08), (-0.1, -0.16)], tint(coat, -0.28), ow * 0.8))
    tail = VGroup(tube([(0, 0), (-0.04, -0.1), (-0.05, -0.24)], [0.03, 0.024, 0.016], coat, ow * 0.8),
                  blob([(-0.04, -0.23), (-0.07, -0.25), (-0.06, -0.3), (-0.04, -0.29)], "#4A4440", ow * 0.6))
    return dict(body=body, legs=legs, head=head, over=over, tail=tail, extra=extra, L=L, front=(0.25, L + 0.02),
                back=(-0.33, L + 0.02), far=-0.07, neck=(0.4, L + 0.25), tailroot=(-0.5, L + 0.28), saddle=saddle,
                face=(0.12, 0.07), face_k=1.1, width=1.0, coat=coat)


def _camel(c, ow, kind, mods):
    coat = col(mods["color"]) if mods.get("color") else "#C9A066"
    dark, light = tint(coat, -0.15), tint(coat, 0.3)
    L = 0.5
    body = VGroup(blob([(0.3, L + 0.08), (0.27, L + 0.2), (0.12, L + 0.25), (0.02, L + 0.42), (-0.1, L + 0.43),
                        (-0.2, L + 0.28), (-0.34, L + 0.2), (-0.37, L + 0.08), (-0.25, L - 0.04), (0.15, L - 0.04)],
                       coat, ow))
    extra = VGroup()
    if not mods.get("plain"):                   # a saddle blanket over the hump, tassels
        extra.add(blob([(-0.18, L + 0.33), (-0.06, L + 0.45), (0.06, L + 0.38), (0.1, L + 0.16), (-0.18, L + 0.14)],
                       "#B83227", ow * 0.9),
                  stroke([(-0.18, L + 0.16), (0.1, L + 0.18)], "#F2C14E", ow * 2),
                  *(Dot([x, L + 0.13, 0], radius=0.011, color=["#F2C14E", "#2E6E9E"][i % 2]) for i, x in
                    enumerate(np.linspace(-0.16, 0.08, 6))))
    legs = {n: leg(L, 0.07, 0.04, coat if n[1] == "n" else dark, ow, "paw", bend=0.02 if n[0] == "b" else -0.01)
            for n in ("fn", "bn", "ff", "bf")}
    head = VGroup(ear([(0.24, 0.26), (0.22, 0.31), (0.27, 0.28)], dark, None, ow),
                  blob([(-0.05, 0.08), (0.08, 0.04), (0.17, 0.08), (0.2, 0.2), (0.25, 0.28), (0.34, 0.28),
                        (0.39, 0.24), (0.38, 0.2), (0.32, 0.18), (0.26, 0.15), (0.22, 0.04), (0.14, -0.06),
                        (0.02, -0.06)], coat, ow),
                  blob([(0.33, 0.215), (0.39, 0.22), (0.38, 0.19), (0.33, 0.185)], light, 0),
                  stroke([(0.365, 0.205), (0.385, 0.2)], INK, ow * 0.8),
                  stroke([(0.34, 0.185), (0.38, 0.19)], INK, ow * 0.8))
    if not mods.get("plain"):
        head.add(stroke([(0.24, 0.25), (0.3, 0.19), (0.36, 0.19)], "#B83227", ow * 1.4))
    tail = VGroup(tube([(0, 0), (-0.03, -0.1), (-0.03, -0.22)], [0.025, 0.02, 0.014], coat, ow * 0.8),
                  blob([(-0.02, -0.2), (-0.05, -0.22), (-0.045, -0.28), (-0.02, -0.27)], dark, ow * 0.6))
    return dict(body=body, legs=legs, head=head, tail=tail, extra=extra, L=L, front=(0.2, L + 0.02),
                back=(-0.25, L + 0.02), far=-0.04, neck=(0.27, L + 0.13), tailroot=(-0.36, L + 0.16),
                saddle=(-0.04, L + 0.43), face=(0.29, 0.25), face_k=0.75, width=0.75, coat=coat)


def _canine(c, ow, kind, mods):
    coat = {"dog": "#C9874B", "wolf": "#8C8A86", "fox": "#D9682B"}[kind]
    coat = col(mods["color"]) if mods.get("color") else coat
    dark, light = tint(coat, -0.18), "#F6EFE2"
    s = {"dog": 1.0, "wolf": 1.25, "fox": 0.95}[kind]
    L = 0.19 * s
    body = VGroup(blob([(0.2 * s, L + 0.06 * s), (0.17 * s, L + 0.13 * s), (-0.05 * s, L + 0.13 * s),
                        (-0.2 * s, L + 0.12 * s), (-0.23 * s, L + 0.04 * s), (-0.17 * s, L - 0.035 * s),
                        (0.05 * s, L - 0.03 * s), (0.18 * s, L - 0.01 * s)], coat, ow))
    body.add(fill_only([(0.19 * s, L + 0.04 * s), (0.17 * s, L - 0.01 * s), (0.05 * s, L - 0.025 * s),
                        (0.08 * s, L + 0.02 * s)], light))
    legs = {n: leg(L, 0.05 * s, 0.035 * s, coat if n[1] == "n" else dark, ow, "paw") for n in ("fn", "bn", "ff", "bf")}
    head = VGroup()
    pointy = kind != "dog"
    if pointy:
        head.add(ear([(0.0, 0.09 * s), (0.01, 0.17 * s), (0.05 * s, 0.1 * s)], dark, None, ow))
    head.add(blob([(-0.04 * s, -0.02 * s), (-0.03 * s, 0.07 * s), (0.03 * s, 0.12 * s), (0.09 * s, 0.11 * s),
                   (0.13 * s, 0.07 * s), (0.2 * s, 0.045 * s), (0.21 * s, 0.015 * s), (0.15 * s, -0.01 * s),
                   (0.07 * s, -0.04 * s), (0.0, -0.05 * s)], coat, ow))
    head.add(fill_only([(0.12 * s, 0.03 * s), (0.2 * s, 0.035 * s), (0.2 * s, 0.01 * s), (0.12 * s, -0.01 * s),
                        (0.08 * s, -0.035 * s), (0.06 * s, 0.0)], light),
             Ellipse(width=0.035 * s, height=0.025 * s, fill_color=INK, fill_opacity=1, stroke_width=0)
             .move_to([0.205 * s, 0.04 * s, 0]))
    if pointy:
        head.add(ear([(0.03 * s, 0.1 * s), (0.06 * s, 0.19 * s), (0.09 * s, 0.1 * s)], coat, "#F2C4B4", ow))
    else:                                       # a floppy ear
        head.add(blob([(0.02 * s, 0.11 * s), (0.07 * s, 0.11 * s), (0.06 * s, 0.02 * s), (0.03 * s, -0.01 * s),
                       (0.0, 0.03 * s)], dark, ow))
    if kind == "dog" and not mods.get("plain"):
        head.add(stroke([(-0.03 * s, -0.035 * s), (0.04 * s, -0.045 * s)], "#B83227", ow * 2.4),
                 Circle(radius=0.012 * s, fill_color="#F2C14E", fill_opacity=1, stroke_color=INK,
                        stroke_width=ow * 0.5).move_to([0.03 * s, -0.06 * s, 0]))
    if kind == "fox":
        tail = VGroup(blob([(0.0, 0.0), (-0.08 * s, 0.03 * s), (-0.16 * s, 0.0), (-0.2 * s, -0.06 * s),
                            (-0.12 * s, -0.06 * s), (-0.04 * s, -0.04 * s)], coat, ow),
                      blob([(-0.16 * s, 0.0), (-0.2 * s, -0.06 * s), (-0.15 * s, -0.06 * s)], light, ow * 0.7))
    elif kind == "wolf":
        tail = VGroup(blob([(0.0, 0.0), (-0.07 * s, -0.02 * s), (-0.13 * s, -0.1 * s), (-0.12 * s, -0.14 * s),
                            (-0.05 * s, -0.08 * s)], coat, ow))
    else:
        tail = VGroup(tube([(0, 0), (-0.06 * s, 0.05 * s), (-0.08 * s, 0.12 * s)], [0.035 * s, 0.03 * s, 0.012 * s],
                           coat, ow))
    return dict(body=body, legs=legs, head=head, tail=tail, extra=VGroup(), L=L, front=(0.13 * s, L),
                back=(-0.15 * s, L), far=-0.03 * s, neck=(0.17 * s, L + 0.1 * s), tailroot=(-0.21 * s, L + 0.1 * s),
                saddle=(-0.02 * s, L + 0.13 * s), face=(0.07 * s, 0.065 * s), face_k=0.7 * s, width=0.45 * s,
                coat=coat)


def _feline(c, ow, kind, mods):
    coat = {"cat": "#E3A15A", "tiger": "#E07B2A", "lion": "#D9A85C", "leopard": "#E3B868"}[kind]
    coat = col(mods["color"]) if mods.get("color") else coat
    dark, light = tint(coat, -0.18), "#F6EFE2"
    s = {"cat": 0.75, "tiger": 1.5, "lion": 1.5, "leopard": 1.3}[kind]
    L = 0.17 * s
    body = VGroup(blob([(0.2 * s, L + 0.06 * s), (0.16 * s, L + 0.12 * s), (-0.08 * s, L + 0.12 * s),
                        (-0.22 * s, L + 0.11 * s), (-0.24 * s, L + 0.03 * s), (-0.17 * s, L - 0.035 * s),
                        (0.05 * s, L - 0.03 * s), (0.18 * s, L - 0.01 * s)], coat, ow))
    body.add(fill_only([(0.16 * s, L - 0.01 * s), (0.0, L - 0.03 * s), (-0.17 * s, L - 0.025 * s),
                        (-0.05 * s, L + 0.0), (0.12 * s, L + 0.01 * s)], light, 0.9))
    legs = {n: leg(L, 0.055 * s, 0.04 * s, coat if n[1] == "n" else dark, ow, "paw") for n in ("fn", "bn", "ff", "bf")}
    if kind == "tiger":
        for x in np.linspace(-0.2, 0.12, 7):
            body.add(blob([(x * s, L + 0.12 * s), (x * s + 0.025 * s, L + 0.115 * s), (x * s + 0.01 * s, L + 0.04 * s),
                           (x * s - 0.005 * s, L + 0.06 * s)], "#22201E", 0))
        for lg in legs.values():
            for y in (-0.05 * s, -0.1 * s):
                lg.add(stroke([(-0.022 * s, y), (0.018 * s, y - 0.008 * s)], "#22201E", ow * 1.6))
    if kind == "leopard":
        for i, (x, y) in enumerate((x, y) for x in np.linspace(-0.2, 0.14, 7) for y in (0.03, 0.08)):
            body.add(Circle(radius=0.012 * s, fill_opacity=0, stroke_color="#4A3424", stroke_width=ow * 1.4)
                     .move_to([x * s + (0.02 * s if i % 2 else 0), L + y * s, 0]))
    head = VGroup()
    if kind == "lion" and not mods.get("cub"):
        head.add(scallop(0.04 * s, 0.05 * s, 0.1 * s, 0.11 * s, 9, 0.02 * s, "#9A5B2A", ow))
    head.add(ear([(0.0, 0.08 * s), (0.015 * s, 0.14 * s) if kind == "cat" else (0.005 * s, 0.125 * s), (0.045 * s, 0.1 * s)],
                 dark, None, ow))
    head.add(blob([(-0.03 * s, -0.01 * s), (-0.025 * s, 0.07 * s), (0.04 * s, 0.11 * s), (0.11 * s, 0.09 * s),
                   (0.15 * s, 0.04 * s), (0.15 * s, 0.0), (0.1 * s, -0.035 * s), (0.02 * s, -0.04 * s)], coat, ow))
    head.add(fill_only([(0.08 * s, 0.01 * s), (0.15 * s, 0.02 * s), (0.14 * s, -0.02 * s), (0.08 * s, -0.035 * s)], light),
             poly([(0.13 * s, 0.03 * s), (0.155 * s, 0.03 * s), (0.142 * s, 0.012 * s)], "#C9706A", ow * 0.5))
    for dy in (0.0, -0.012 * s):                 # whiskers
        head.add(Line([0.12 * s, 0.0 + dy, 0], [0.21 * s, 0.01 * s + dy * 1.5, 0], stroke_color=INK, stroke_width=ow * 0.45))
    if kind == "tiger":
        for x in (0.03, 0.06):
            head.add(stroke([(x * s, 0.1 * s), (x * s + 0.01 * s, 0.07 * s)], "#22201E", ow * 1.4))
    head.add(ear([(0.03 * s, 0.09 * s), (0.06 * s, 0.15 * s) if kind == "cat" else (0.05 * s, 0.135 * s), (0.09 * s, 0.09 * s)],
                 coat, "#F2C4B4", ow))
    if kind in ("cat", "leopard"):
        tail = VGroup(tube([(0, 0), (-0.09 * s, 0.02 * s), (-0.14 * s, 0.1 * s), (-0.12 * s, 0.17 * s)],
                           [0.03 * s, 0.028 * s, 0.025 * s, 0.02 * s], coat, ow))
    else:
        tail = VGroup(tube([(0, 0), (-0.08 * s, -0.04 * s), (-0.14 * s, -0.12 * s), (-0.13 * s, -0.17 * s)],
                           [0.03 * s, 0.026 * s, 0.022 * s, 0.018 * s], coat, ow))
        if kind == "lion":
            tail.add(blob([(-0.12 * s, -0.15 * s), (-0.16 * s, -0.17 * s), (-0.15 * s, -0.22 * s), (-0.11 * s, -0.2 * s)],
                          "#9A5B2A", ow * 0.7))
        if kind == "tiger":
            tail.add(*(stroke([(x * s, y * s + 0.012 * s), (x * s + 0.012 * s, y * s - 0.012 * s)], "#22201E", ow * 1.4)
                       for x, y in ((-0.06, -0.025), (-0.1, -0.07), (-0.13, -0.12))))
    return dict(body=body, legs=legs, head=head, tail=tail, extra=VGroup(), L=L, front=(0.12 * s, L),
                back=(-0.16 * s, L), far=-0.03 * s, neck=(0.17 * s, L + 0.09 * s), tailroot=(-0.23 * s, L + 0.08 * s),
                saddle=(-0.03 * s, L + 0.12 * s), face=(0.07 * s, 0.05 * s), face_k=0.62 * s, width=0.45 * s,
                coat=coat)


def _small(c, ow, kind, mods):
    """Sheep, goat, pig, deer, rat, bear."""
    coat = {"sheep": "#F4F1EA", "goat": "#E9E2D3", "pig": "#F2B6A8", "deer": "#B97A45", "rat": "#8C8A86",
            "bear": "#6B4226"}[kind]
    coat = col(mods["color"]) if mods.get("color") else coat
    dark, light = tint(coat, -0.18), "#F6EFE2"
    s = {"sheep": 1.0, "goat": 0.95, "pig": 1.0, "deer": 1.1, "rat": 0.45, "bear": 1.6}[kind]
    L = {"sheep": 0.17, "goat": 0.2, "pig": 0.11, "deer": 0.3, "rat": 0.06, "bear": 0.15}[kind] * s
    legc = "#3A3631" if kind == "sheep" else coat
    foot = "paw" if kind in ("rat", "bear") else "hoof"
    legs = {n: leg(L, (0.05 if kind != "bear" else 0.07) * s, (0.035 if kind != "bear" else 0.055) * s,
                   legc if n[1] == "n" else tint(legc, -0.2), ow, foot) for n in ("fn", "bn", "ff", "bf")}
    if kind == "sheep":
        body = VGroup(scallop(-0.02 * s, L + 0.08 * s, 0.2 * s, 0.11 * s, 10, 0.022 * s, coat, ow))
    elif kind == "pig":
        body = VGroup(blob([(0.2 * s, L + 0.08 * s), (0.15 * s, L + 0.18 * s), (-0.1 * s, L + 0.2 * s),
                            (-0.22 * s, L + 0.12 * s), (-0.2 * s, L + 0.0), (0.0, L - 0.04 * s), (0.17 * s, L - 0.02 * s)],
                           coat, ow))
    elif kind == "bear":
        body = VGroup(blob([(0.18 * s, L + 0.07 * s), (0.12 * s, L + 0.17 * s), (-0.05 * s, L + 0.2 * s),
                            (-0.2 * s, L + 0.16 * s), (-0.23 * s, L + 0.05 * s), (-0.15 * s, L - 0.03 * s),
                            (0.1 * s, L - 0.03 * s)], coat, ow))
    else:
        body = VGroup(blob([(0.2 * s, L + 0.06 * s), (0.16 * s, L + 0.13 * s), (-0.05 * s, L + 0.12 * s),
                            (-0.2 * s, L + 0.12 * s), (-0.23 * s, L + 0.04 * s), (-0.16 * s, L - 0.035 * s),
                            (0.05 * s, L - 0.03 * s), (0.18 * s, L - 0.01 * s)], coat, ow))
        body.add(fill_only([(0.17 * s, L - 0.01 * s), (0.0, L - 0.03 * s), (-0.15 * s, L - 0.025 * s),
                            (-0.05 * s, L + 0.0), (0.12 * s, L + 0.01 * s)], light, 0.85))
    if kind == "deer":
        body.add(*(Dot([x * s, L + y * s, 0], radius=0.008 * s, color="#F6EFE2")
                   for x, y in ((-0.12, 0.09), (-0.06, 0.1), (0.0, 0.09), (-0.09, 0.06), (-0.03, 0.06), (0.05, 0.08))))
    head = VGroup()
    if kind == "sheep":
        head.add(ear([(-0.01, 0.04 * s), (-0.07 * s, 0.03 * s), (-0.02 * s, 0.0)], "#3A3631", None, ow),
                 blob([(-0.03 * s, 0.02 * s), (0.02 * s, 0.07 * s), (0.09 * s, 0.05 * s), (0.13 * s, -0.02 * s),
                       (0.1 * s, -0.06 * s), (0.03 * s, -0.05 * s)], "#3A3631", ow),
                 scallop(0.0, 0.06 * s, 0.05 * s, 0.035 * s, 5, 0.01 * s, coat, ow * 0.8))
        face, fk = (0.07 * s, 0.015 * s), 0.6 * s
    elif kind == "goat":
        head.add(tube([(0.03 * s, 0.07 * s), (0.0, 0.13 * s), (-0.05 * s, 0.14 * s), (-0.07 * s, 0.1 * s)],
                      [0.025 * s, 0.022 * s, 0.016 * s, 0.006 * s], "#8C8478", ow * 0.8),
                 ear([(0.0, 0.05 * s), (-0.07 * s, 0.03 * s), (-0.01, 0.02 * s)], dark, None, ow),
                 blob([(-0.03 * s, 0.0), (-0.01 * s, 0.07 * s), (0.06 * s, 0.08 * s), (0.13 * s, 0.0), (0.14 * s, -0.04 * s),
                       (0.1 * s, -0.05 * s), (0.02 * s, -0.04 * s)], coat, ow),
                 blob([(0.07 * s, -0.04 * s), (0.11 * s, -0.045 * s), (0.08 * s, -0.11 * s)], "#C9C2B2", ow * 0.7))
        face, fk = (0.06 * s, 0.035 * s), 0.6 * s
    elif kind == "pig":
        head.add(blob([(-0.04 * s, 0.0), (-0.02 * s, 0.09 * s), (0.07 * s, 0.1 * s), (0.13 * s, 0.05 * s),
                       (0.14 * s, -0.03 * s), (0.08 * s, -0.06 * s), (0.0, -0.05 * s)], coat, ow),
                 Ellipse(width=0.04 * s, height=0.06 * s, fill_color=tint(coat, -0.12), fill_opacity=1, stroke_color=INK,
                         stroke_width=ow * 0.8).move_to([0.145 * s, 0.01 * s, 0]),
                 *(Dot([0.15 * s, 0.01 * s + d, 0], radius=0.005 * s, color=INK) for d in (-0.012 * s, 0.012 * s)),
                 blob([(0.02 * s, 0.08 * s), (0.06 * s, 0.14 * s), (0.08 * s, 0.08 * s)], tint(coat, -0.1), ow * 0.8))
        face, fk = (0.06 * s, 0.04 * s), 0.7 * s
    elif kind == "deer":
        if not mods.get("doe"):
            for sx in (1.0, 0.7):                # antlers
                head.add(stroke([(0.03 * s, 0.08 * s), (0.0, 0.17 * s * sx), (-0.04 * s, 0.24 * s * sx)], "#8C6E52", ow * 1.6),
                         stroke([(0.0, 0.15 * s * sx), (0.04 * s, 0.21 * s * sx)], "#8C6E52", ow * 1.4),
                         stroke([(-0.02 * s, 0.2 * s * sx), (-0.08 * s, 0.22 * s * sx)], "#8C6E52", ow * 1.2))
        head.add(ear([(0.0, 0.06 * s), (-0.07 * s, 0.1 * s), (-0.01 * s, 0.03 * s)], dark, "#F2C4B4", ow),
                 blob([(-0.03 * s, 0.0), (0.0, 0.08 * s), (0.06 * s, 0.08 * s), (0.15 * s, 0.01 * s), (0.15 * s, -0.02 * s),
                       (0.08 * s, -0.03 * s), (0.0, -0.04 * s)], coat, ow),
                 Dot([0.15 * s, 0.0, 0], radius=0.009 * s, color=INK))
        face, fk = (0.055 * s, 0.04 * s), 0.6 * s
    elif kind == "rat":
        head.add(blob([(-0.04 * s, 0.0), (0.0, 0.07 * s), (0.06 * s, 0.06 * s), (0.17 * s, 0.0), (0.06 * s, -0.04 * s)],
                      coat, ow),
                 Circle(radius=0.035 * s, fill_color=tint(coat, -0.1), fill_opacity=1, stroke_color=INK,
                        stroke_width=ow).move_to([0.0, 0.08 * s, 0]),
                 Circle(radius=0.02 * s, fill_color="#F2B6A8", fill_opacity=1, stroke_width=0).move_to([0.0, 0.08 * s, 0]),
                 Dot([0.17 * s, 0.0, 0], radius=0.01 * s, color="#E07A7A"))
        face, fk = (0.07 * s, 0.03 * s), 0.45 * s
    else:                                       # bear
        head.add(Circle(radius=0.03 * s, fill_color=coat, fill_opacity=1, stroke_color=INK, stroke_width=ow)
                 .move_to([0.0, 0.09 * s, 0]),
                 blob([(-0.04 * s, 0.0), (-0.02 * s, 0.08 * s), (0.06 * s, 0.1 * s), (0.11 * s, 0.05 * s), (0.15 * s, 0.02 * s),
                       (0.14 * s, -0.03 * s), (0.04 * s, -0.05 * s)], coat, ow),
                 fill_only([(0.08 * s, 0.03 * s), (0.15 * s, 0.02 * s), (0.14 * s, -0.025 * s), (0.08 * s, -0.03 * s)],
                           "#C9A27A"),
                 Ellipse(width=0.03 * s, height=0.02 * s, fill_color=INK, fill_opacity=1, stroke_width=0)
                 .move_to([0.145 * s, 0.015 * s, 0]))
        face, fk = (0.05 * s, 0.05 * s), 0.65 * s
    if kind == "pig":
        tail = VGroup(stroke([(0, 0), (-0.025 * s, 0.02 * s), (-0.035 * s, -0.005 * s), (-0.02 * s, -0.01 * s),
                              (-0.03 * s, 0.03 * s)], tint(coat, -0.1), ow * 1.2))
    elif kind == "rat":
        tail = VGroup(stroke([(0, 0), (-0.12 * s, -0.04 * s), (-0.24 * s, 0.02 * s), (-0.32 * s, 0.0)], "#E3A1A0", ow * 1.2))
    elif kind == "sheep":
        tail = VGroup(scallop(-0.02 * s, -0.01 * s, 0.03 * s, 0.03 * s, 4, 0.006 * s, coat, ow * 0.8))
    else:
        tail = VGroup(blob([(0.0, 0.0), (-0.04 * s, 0.03 * s), (-0.05 * s, 0.0), (-0.02 * s, -0.02 * s)],
                           coat if kind != "deer" else "#F6EFE2", ow * 0.8))
    neck = {"sheep": (0.17, 0.1), "goat": (0.17, 0.1), "pig": (0.18, 0.1), "deer": (0.17, 0.11), "rat": (0.17, 0.05),
            "bear": (0.16, 0.1)}[kind]
    return dict(body=body, legs=legs, head=head, tail=tail, extra=VGroup(), L=L, front=(0.12 * s, L),
                back=(-0.14 * s, L), far=-0.03 * s, neck=(neck[0] * s, L + neck[1] * s),
                tailroot=(-0.21 * s, L + 0.09 * s), saddle=(-0.02 * s, L + 0.15 * s), face=face, face_k=fk,
                width=0.45 * s, coat=coat)


def _bird(c, ow, kind, mods):
    coat = {"chicken": "#F4F1EA", "rooster": "#C2552B", "peacock": "#1F6FA8", "duck": "#F4F1EA", "eagle": "#6B4226",
            "bird": "#8C8A86", "crow": "#2B2826", "parrot": "#3FA34D"}[kind]
    coat = col(mods["color"]) if mods.get("color") else coat
    dark = tint(coat, -0.2)
    s = {"chicken": 0.9, "rooster": 1.0, "peacock": 1.3, "duck": 0.9, "eagle": 1.4, "bird": 0.55, "crow": 0.75,
         "parrot": 0.8}[kind]
    L = (0.08 if kind not in ("peacock",) else 0.14) * s
    legc = "#E8A33C" if kind != "crow" else "#3A3631"
    body = VGroup(blob([(0.1 * s, L + 0.1 * s), (0.04 * s, L + 0.17 * s), (-0.08 * s, L + 0.16 * s),
                        (-0.15 * s, L + 0.12 * s), (-0.12 * s, L + 0.03 * s), (0.0, L - 0.01 * s), (0.09 * s, L + 0.03 * s)],
                       coat, ow))
    tail = VGroup()
    if kind == "rooster":
        for i, cc in enumerate(("#1F3B2E", "#2E6E4E", "#1F3B2E")):
            tail.add(tube([(0, 0), (-0.06 * s, 0.08 * s + i * 0.01), (-0.1 * s, 0.1 * s - i * 0.03), (-0.12 * s, 0.02 * s - i * 0.03)],
                          [0.03 * s, 0.03 * s, 0.022 * s, 0.006 * s], cc, ow * 0.7))
    elif kind == "peacock":
        if mods.get("display"):                  # the train raised in a fan
            for i, a in enumerate(np.linspace(40, 170, 9)):
                r = 0.42 * s
                x, y = r * math.cos(math.radians(a)) - 0.05 * s, r * math.sin(math.radians(a))
                tail.add(tube([(0, 0), (x * 0.6, y * 0.6), (x, y)], [0.03 * s, 0.05 * s, 0.07 * s], "#2E7D4E", ow * 0.6),
                         Circle(radius=0.026 * s, fill_color="#F2C14E", fill_opacity=1, stroke_width=0).move_to([x, y, 0]),
                         Circle(radius=0.015 * s, fill_color="#1F6FA8", fill_opacity=1, stroke_width=0).move_to([x, y, 0]))
        else:                                   # trailing behind
            tail.add(blob([(0.0, 0.02 * s), (-0.2 * s, 0.0), (-0.4 * s, -0.08 * s), (-0.42 * s, -0.12 * s),
                           (-0.2 * s, -0.08 * s), (0.0, -0.03 * s)], "#2E7D4E", ow))
            for x in np.linspace(-0.36, -0.1, 5):
                y = -0.06 * s * (x / -0.36)
                tail.add(Circle(radius=0.016 * s, fill_color="#F2C14E", fill_opacity=1, stroke_width=0).move_to([x * s, y - 0.01 * s, 0]),
                         Circle(radius=0.009 * s, fill_color="#1F6FA8", fill_opacity=1, stroke_width=0).move_to([x * s, y - 0.01 * s, 0]))
    elif kind == "eagle":
        tail.add(poly([(0.0, 0.02 * s), (-0.12 * s, 0.0), (-0.12 * s, -0.06 * s), (0.0, -0.03 * s)], "#F4F1EA", ow))
    else:
        tail.add(blob([(0.0, 0.02 * s), (-0.07 * s, 0.07 * s if kind in ("chicken", "duck") else 0.02 * s),
                       (-0.09 * s, 0.04 * s if kind in ("chicken", "duck") else -0.02 * s), (0.0, -0.03 * s)], dark, ow))
    head = VGroup()
    beak = "#E8A33C" if kind not in ("eagle", "parrot", "crow") else {"eagle": "#F2C14E", "parrot": "#3A3631",
                                                                       "crow": "#3A3631"}[kind]
    hc = "#F4F1EA" if kind == "eagle" else ("#2E7D74" if kind == "duck" and mods.get("mallard") else coat)
    if kind == "duck":
        head.add(blob([(0.03 * s, 0.03 * s), (0.11 * s, 0.035 * s), (0.12 * s, 0.015 * s), (0.04 * s, 0.0)], beak, ow * 0.8))
    elif kind == "parrot":
        head.add(blob([(0.04 * s, 0.05 * s), (0.08 * s, 0.05 * s), (0.09 * s, 0.0), (0.07 * s, -0.02 * s), (0.05 * s, 0.01 * s)],
                      beak, ow * 0.8))
    else:
        head.add(poly([(0.04 * s, 0.045 * s), (0.04 * s, 0.015 * s), (0.1 * s if kind != "eagle" else 0.09 * s,
                                                                         0.025 * s if kind != "eagle" else 0.005 * s)],
                      beak, ow * 0.8))
    head.add(Circle(radius=0.05 * s, fill_color=hc, fill_opacity=1, stroke_color=INK, stroke_width=ow)
             .move_to([0.0, 0.03 * s, 0]))
    if kind in ("chicken", "rooster"):           # a comb and a wattle
        head.add(blob([(-0.03 * s, 0.07 * s), (-0.02 * s, 0.1 * s), (0.0, 0.085 * s), (0.015 * s, 0.11 * s),
                       (0.03 * s, 0.08 * s), (0.04 * s, 0.065 * s)], "#D63B2F", ow * 0.7),
                 blob([(0.03 * s, 0.0), (0.05 * s, -0.005 * s), (0.04 * s, -0.04 * s), (0.025 * s, -0.03 * s)], "#D63B2F", ow * 0.6))
    if kind == "peacock":
        head.add(*(Line([0.0, 0.07 * s, 0], [dx * s, 0.13 * s, 0], stroke_color=INK, stroke_width=ow * 0.6) for dx in (-0.02, 0.0, 0.02)),
                 *(Dot([dx * s, 0.13 * s, 0], radius=0.009 * s, color="#1F6FA8") for dx in (-0.02, 0.0, 0.02)))
    wing = VGroup(blob([(0.03 * s, 0.03 * s), (-0.03 * s, 0.06 * s), (-0.12 * s, 0.03 * s), (-0.15 * s, -0.02 * s),
                        (-0.06 * s, -0.04 * s)], dark if kind != "eagle" else tint(coat, -0.1), ow))
    wing.add(*(stroke([(-0.06 * s - i * 0.025 * s, 0.03 * s), (-0.09 * s - i * 0.02 * s, -0.02 * s)], tint(dark, -0.25), ow * 0.6)
               for i in range(3)))
    if kind == "rooster":
        body.add(blob([(0.1 * s, L + 0.1 * s), (0.05 * s, L + 0.17 * s), (0.0, L + 0.12 * s), (0.04 * s, L + 0.06 * s)], "#E8A33C", 0))
    legs = {"fn": bird_leg(L + 0.02 * s, legc, ow), "bn": bird_leg(L + 0.02 * s, tint(legc, -0.15), ow)}
    return dict(body=body, legs=legs, head=head, tail=tail, wing=wing, extra=VGroup(), L=L + 0.02 * s,
                front=(0.02 * s, L + 0.02 * s), back=(-0.03 * s, L + 0.02 * s), far=0.0,
                neck=(0.07 * s, L + 0.15 * s), tailroot=(-0.13 * s, L + 0.1 * s), wingroot=(0.02 * s, L + 0.1 * s),
                saddle=(-0.03 * s, L + 0.16 * s), face=(0.012 * s, 0.035 * s), face_k=0.42 * s, width=0.3 * s,
                coat=coat, bird=True)


SPECIES = {"horse": _horse, "pony": _horse, "donkey": _horse, "zebra": _horse,
           "cow": _bovine, "ox": _bovine, "bull": _bovine, "buffalo": _bovine,
           "elephant": _elephant, "camel": _camel,
           "dog": _canine, "wolf": _canine, "fox": _canine,
           "cat": _feline, "tiger": _feline, "lion": _feline, "leopard": _feline,
           "sheep": _small, "goat": _small, "pig": _small, "deer": _small, "rat": _small, "bear": _small,
           "chicken": _bird, "rooster": _bird, "peacock": _bird, "duck": _bird, "eagle": _bird, "bird": _bird,
           "crow": _bird, "parrot": _bird}
ALIASES = {"mule": "donkey", "ass": "donkey", "bullock": "ox", "zebu": "ox", "calf": "cow", "hen": "chicken",
           "cock": "rooster", "puppy": "dog", "hound": "dog", "kitten": "cat", "lamb": "sheep", "boar": "pig",
           "stag": "deer", "mouse": "rat", "pigeon": "bird", "sparrow": "bird", "dove": "bird", "hawk": "eagle",
           "falcon": "eagle", "steed": "horse", "stallion": "horse", "mare": "horse", "panther": "leopard",
           "cheetah": "leopard", "jackal": "fox", "peafowl": "peacock", "goose": "duck", "rabbit": "rat"}
KINDS = tuple(SPECIES) + tuple(ALIASES)
RIDEABLE = ("horse", "pony", "donkey", "zebra", "ox", "bull", "buffalo", "elephant", "camel", "tiger", "lion")


def species(name: str) -> str:
    n = str(name or "horse").lower()
    n = ALIASES.get(n, n)
    return n if n in SPECIES else "horse"


# ---------------------------------------------------------------- the animal -----------------------------------------

class Animal(P.Person):
    D = {"HIP": 0.3, "TORSO": 0.2, "NECK": 0.0, "HEAD": 0.1, "UPPER": 0.1, "FORE": 0.1, "THIGH": 0.1, "SHIN": 0.1}

    def __init__(self, kind: str, mods: dict | None = None, c=None, size: float = 2.6):
        global INK
        VGroup.__init__(self)
        mods = dict(mods or {})
        if c and not mods.get("color"):
            mods["color"] = c
        self.mods = mods
        self.kind = species(kind)
        k = size / 1.8
        INK = ink = col("ink")
        self.ow = ow = 2.0 * k
        sp = SPECIES[self.kind](c, ow, self.kind, mods)
        self.sp = sp
        self.bird = bool(sp.get("bird"))
        self.skin = self.cloth = sp["coat"]
        self.body_w = sp["width"] * 0.5
        self.stride = sp["L"] * 0.9 + 0.05             # how far a step carries it (render: the walk's phase)
        self.rigid = []
        self.rest = dict(P.REST)
        self.rest.update(P.MOODS.get(str(mods.get("mood") or "calm").lower(), P.MOODS["calm"]))
        self.rest.update(fl1=0.0, bl1=0.0, fl2=0.0, bl2=0.0, rear=0.0, flap=0.0, graze=0.0)
        self.alpha_now = 1.0
        self.hands = {}
        self.arms = {}
        self.legs = {}

        def rigid(m, part):
            for x in m.family_members_with_points():
                self.rigid.append((x, x.points[:, :2].copy(), part))
            return m

        self.add(rigid(Ellipse(width=sp["width"] * 1.1, height=0.05 + sp["width"] * 0.04, fill_color=ink,
                               fill_opacity=0.12, stroke_width=0), "ground"))
        legs = sp["legs"]
        if "tail" in sp:
            self.add(rigid(sp["tail"], "tail"))
        for n in ("ff", "bf"):
            if n in legs:
                self.add(rigid(legs[n], "leg_" + n))
        if self.bird and "wing" in sp:          # the far wing, behind (seen when it beats)
            far_wing = sp["wing"].copy().set_fill(tint(sp["coat"], -0.3))
            self.add(rigid(far_wing, "wing_far"))
        for n in ("fn", "bn"):
            self.add(rigid(legs[n], "leg_" + n))
        self.add(rigid(sp["head"], "head"))
        self.torso_m = rigid(sp["body"], "body")
        self.add(self.torso_m)
        self.add(rigid(sp["extra"], "body"))
        if "over" in sp:
            self.add(rigid(sp["over"], "head"))
        if self.bird and "wing" in sp:
            self.add(rigid(sp["wing"], "wing"))
        self.head = sp["head"]
        self.neck = Line([0, 0, 0], [0, 0.1, 0], stroke_width=0, stroke_opacity=0)
        self.face_k = sp["face_k"] * 1.6
        self._build_face(ink, ow * 0.9, sp["coat"], tint(sp["coat"], -0.5), "none", mods)
        self.hand = Dot(radius=0.001).set_opacity(0)
        self._ref = VGroup(*(Dot([x, y, 0], radius=0.001).set_opacity(0) for x, y in ((0, 0.5), (0.1, 0.5), (0, 0.6))))
        self.add(self.neck, self.hand, self._ref)
        self.pose = dict(self.rest)
        self.pose["face"] = -1.0 if mods.get("face") == "left" else 1.0
        self.set_pose(self.pose)

    def sit_target(self) -> dict:
        """Lying down: the legs folded under, the head up."""
        q = dict(self.pose)
        q.update(drop=1.0, fl1=0.0, bl1=0.0)
        return q

    def saddle(self) -> np.ndarray:
        """Where a rider sits now, in the world."""
        return self._world(self._B(self.sp["saddle"]))

    # -- the pose ------------------------------------------------------------------------------------------------
    def _B(self, q):
        """A point on the body (its own frame) where the pose has it (unmirrored)."""
        x, y = q
        px, py = self._piv
        ca, sa = math.cos(self._pitch), math.sin(self._pitch)
        dx, dy = x - px, y - py
        return np.array([px + ca * dx - sa * dy, py + sa * dx + ca * dy + self._lift])

    def _world(self, q):
        o, ex, ey = self._frame
        return o + q[0] * self._f * ex + (q[1] - 0.5) * ey

    def set_pose(self, p: dict) -> None:
        self.pose = dict(p)
        sp = self.sp
        f = self.facing()
        self._f = f
        o, xr, yr = (d.get_center() for d in self._ref)
        ex, ey = (xr - o) / 0.1, (yr - o) / 0.1
        self._frame = (o, ex, ey)
        L = sp["L"]
        lie = max(0.0, min(1.0, p.get("drop", 0.0)))
        rear = p.get("rear", 0.0)
        fly = p.get("flap", 0.0) > 0 or p.get("flying", 0.0) > 0
        self._piv = sp["back"]
        self._pitch = rear * 0.62
        self._lift = p["bob"] * L * 1.6 - lie * L * 0.72 + p.get("breath", 0.0) * 0.3
        # the legs: in diagonal pairs (a bird: one and the other), folded when it lies, kicking up when it rears
        swing = {"fn": p["fl1"], "bn": p["bl1"], "ff": p["bl1"], "bf": p["fl1"]}
        frames = {}

        def put(name, root, ang, sy=1.0):
            R = self._B(root)
            ang = ang + self._pitch
            ca, sa = math.cos(ang), math.sin(ang)
            M = np.array([[ca, -sa * sy], [sa, ca * sy]])
            frames[name] = (R, M)
        for n in ("fn", "bn", "ff", "bf"):
            front = n[0] == "f"
            root = sp["front"] if front else sp["back"]
            if n[1] == "f":
                root = (root[0] + sp["far"], root[1])
            a = swing[n] * (0.75 if not self.bird else 1.0)
            if front and rear:
                a += rear * 1.5
            elif rear:                          # the hind legs stay planted as the body tips up
                a -= self._pitch * 0.9
            if fly and self.bird:
                a = -1.2
            put("leg_" + n, root, a, 1.0 - 0.72 * lie)
        put("body", sp["back"], 0.0)
        frames["body"] = (self._B((0.0, 0.0)), np.array([[math.cos(self._pitch), -math.sin(self._pitch)],
                                                         [math.sin(self._pitch), math.cos(self._pitch)]]))
        g = p.get("graze", 0.0)
        head_ang = -p.get("nod", 0.0) * 0.6 - g * 1.55 + (0.15 * lie) - rear * 0.4
        nx, ny = sp["neck"]
        put("head", (nx, ny - g * L * 0.3), head_ang)    # (grazing: the neck reaches down from the shoulders)
        wag = 0.25 * (p["fl1"]) + p.get("breath", 0.0) * 25.0
        put("tail", sp["tailroot"], wag)
        if self.bird:
            flap = p.get("flap", 0.0)
            put("wing", sp["wingroot"], flap * 1.6)
            put("wing_far", sp["wingroot"], flap * 1.9)
        frames["ground"] = (np.array([0.0, 0.0]), np.eye(2))
        for x, base, part in self.rigid:
            R, M = frames[part]
            body = base @ M.T + R
            x.points = o + np.outer(body[:, 0] * f, ex) + np.outer(body[:, 1] - 0.5, ey)
        # the face, on the head
        R, M = frames["head"]
        fp = M @ np.array(sp["face"]) + R
        self._pose_face(p, o, ex, ey, np.array([fp[0] * f, fp[1]]), f, 0.75)
        self.hand.move_to(self._world(self._B(sp["saddle"])))


# How much bigger than its drawing each is at the people's scale (a horse's back near a person's shoulder)
SCALE = {"horse": 1.4, "pony": 1.25, "donkey": 1.3, "zebra": 1.35, "cow": 1.35, "ox": 1.35, "bull": 1.4,
         "buffalo": 1.4, "elephant": 1.45, "camel": 1.35, "tiger": 1.1, "lion": 1.1, "bear": 1.1, "deer": 1.15}


def animal(kind: str, mods: dict, size: float, c=None) -> Animal:
    """An animal at the people's scale (size 2.6, a person's), its lines as wide as theirs."""
    size = size or 2.6
    a = Animal(kind, mods, c, size)
    a.scale(size * SCALE.get(species(kind), 1.0), about_point=np.array([0.0, 0.0, 0.0]))
    return a


# ---------------------------------------------------------------- riding ---------------------------------------------

def rider_pose(rider) -> dict:
    """A person in the saddle: sitting, the hands forward on the reins."""
    q = dict(rider.pose)
    q.update(rider.sit_target())
    q.update(fa1=0.95, fa2=1.35, ba1=0.8, ba2=1.25, lean=0.06)
    if not isinstance(rider, P.Peg):           # a jointed figure: astride, the legs down the flank
        q.update(fl1=1.25, fl2=0.15, bl1=1.05, bl2=0.05, drop=0.0)
    for key in ("face", "mouth") + P.FACE_KEYS:
        q[key] = rider.pose.get(key, q.get(key))
    return q


def rider_seat(rider) -> np.ndarray:
    """The point of a person that sits on the saddle: the bottom of a peg figure, a jointed one's hips."""
    p = rider.pose
    if isinstance(rider, P.Peg):
        return rider.w((0.0, rider.D["HIP"] - p.get("drop", 0.0) + p.get("bob", 0.0) - 0.035))
    return rider.w((0.0, rider.D["HIP"] - p.get("drop", 0.0)))
