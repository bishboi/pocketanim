"""Things drawn with the same pen as the people: a ready shelf, so a shot needs no picture searched for or made.

    ent b prop moneybag [color C] [sign ₹] [open] [size H] at X,Y      (it stands on X,Y: its bottom middle there)

Drawn to the people's scale (size 2.6, a person's, by default: a chest beside a king is a chest's size); a bigger
size shows one alone (size 6-10). Those with a lid open and shut as it plays: `open X`, `shut X` (a chest shows its
gold; a letter its flap; a box, a door). Any of them can be carried, given, thrown, moved.

Money: moneybag coins coin goldbars cash gem crown chest
Writing: book books openbook ledger scroll letter document charter newspaper oldmap quill inkwell seal
Furniture: table desk chair stool throne bench bookshelf lectern bed
Containers: barrel crate box sack basket pot jar bucket
Light: candle diya lantern campfire
Tools and arms: sword shield spear bow cannon anvil plough wheel charkha scales hourglass key bell goblet telescope
                lightbulb printingpress
Places: tree palm bush rock well tent hut house tower gate fence signpost flagpole cart boat ship
"""

from __future__ import annotations

import math

import numpy as np
from manim import Circle, Dot, Ellipse, Line, RoundedRectangle, Text, VGroup

import zoo
from look import col
from zoo import blob, fill_only, poly, stroke, tint, tube

GOLD, GOLD_D, WOOD, WOOD_D, IRON, PAPER, RED, CLOTH = ("#F2C14E", "#C9962B", "#9A6B43", "#6B4A2F", "#8E969C",
                                                       "#F3EADA", "#B83227", "#C9A66B")


def rect(x0, y0, x1, y1, fill, w):
    return poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill, w)


def rrect(x0, y0, x1, y1, r, fill, w):
    return RoundedRectangle(width=x1 - x0, height=y1 - y0, corner_radius=r, fill_color=fill, fill_opacity=1,
                            stroke_color=zoo.INK, stroke_width=w).move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])


def circ(x, y, r, fill, w):
    return Circle(radius=r, fill_color=fill, fill_opacity=1, stroke_color=zoo.INK, stroke_width=w).move_to([x, y, 0])


def ell(x, y, a, b, fill, w):
    return Ellipse(width=a, height=b, fill_color=fill, fill_opacity=1, stroke_color=zoo.INK, stroke_width=w).move_to([x, y, 0])


def line(a, b, c, w):
    return Line([a[0], a[1], 0], [b[0], b[1], 0], stroke_color=c, stroke_width=w)


def glint(x, y, r, w):
    """A little four-pointed shine."""
    return poly([(x, y + r), (x + r * 0.25, y + r * 0.25), (x + r, y), (x + r * 0.25, y - r * 0.25), (x, y - r),
                 (x - r * 0.25, y - r * 0.25), (x - r, y), (x - r * 0.25, y + r * 0.25)], "#FFFBEA", w * 0.4)


def coin_pile(x, y, wd, rows, w):
    g = VGroup()
    for r in range(rows):
        n = max(1, int((rows - r) * 2))
        for i in range(n):
            cx = x - wd / 2 + (i + 0.5 + 0.5 * (r % 2)) * wd / (n + 0.5)
            g.add(ell(cx, y + 0.012 + r * 0.018, 0.045, 0.022, GOLD, w * 0.6))
    return g


def letters(txt, x, y, h, c="#3A3631"):
    t = Text(txt, font="Caveat", color=c, weight="BOLD")
    t.scale_to_fit_height(h).move_to([x, y, 0])
    return t


def scribble(x0, x1, y, w, c="#6B6258"):
    """A line of handwriting."""
    n = 10
    pts = [(x0 + (x1 - x0) * i / n, y + 0.004 * math.sin(i * 2.3)) for i in range(n + 1)]
    return stroke(pts, c, w)


# ---------------------------------------------------------------- the shelf ----------------------------------------
# Each returns (what is drawn, the lid or None, the hinge, how it opens: "swing" or "flip", how far)

def _moneybag(m, w):
    c = col(m["color"]) if m.get("color") else "#C9A66B"
    g = VGroup(blob([(-0.03, 0.17), (-0.1, 0.1), (-0.11, 0.03), (-0.06, 0.0), (0.06, 0.0), (0.11, 0.03), (0.1, 0.1),
                     (0.03, 0.17)], c, w),
               blob([(-0.035, 0.17), (-0.06, 0.21), (-0.02, 0.2), (0.0, 0.225), (0.02, 0.2), (0.06, 0.21), (0.035, 0.17)],
                    tint(c, -0.1), w),
               stroke([(-0.04, 0.168), (0.04, 0.168)], "#6B4A2F", w * 2.0),
               fill_only([(-0.08, 0.1), (-0.05, 0.03), (-0.03, 0.08)], tint(c, 0.3), 0.7))
    g.add(letters(str(m.get("sign") or "$"), 0.0, 0.075, 0.07, "#6B4A2F"))
    if not m.get("plain"):
        g.add(coin_pile(0.13, 0.0, 0.1, 2, w))
    return g, None


def _coins(m, w):
    g = VGroup(coin_pile(0.0, 0.0, 0.26, 4, w))
    for x, h in ((-0.05, 5), (0.06, 4)):          # two stacks
        for i in range(h):
            g.add(ell(x, 0.07 + i * 0.016, 0.06, 0.024, GOLD, w * 0.6))
    g.add(glint(0.03, 0.17, 0.02, w), glint(-0.09, 0.08, 0.015, w))
    return g, None


def _coin(m, w):
    sign = str(m.get("sign") or "")
    g = VGroup(circ(0.0, 0.1, 0.1, GOLD_D, w), circ(-0.008, 0.1, 0.092, GOLD, w * 0.7),
               Circle(radius=0.072, stroke_color=GOLD_D, stroke_width=w * 0.8).move_to([-0.008, 0.1, 0]))
    if sign:
        g.add(letters(sign, -0.008, 0.1, 0.08, GOLD_D))
    else:                                       # a ruler's head in profile
        g.add(blob([(-0.03, 0.06), (-0.035, 0.12), (0.0, 0.15), (0.03, 0.13), (0.035, 0.1), (0.02, 0.06)], GOLD_D, 0))
    g.add(glint(0.05, 0.16, 0.02, w))
    return g, None


def _goldbars(m, w):
    g = VGroup()
    for (x, y) in ((-0.07, 0.0), (0.07, 0.0), (0.0, 0.045)):
        g.add(poly([(x - 0.065, y), (x + 0.065, y), (x + 0.05, y + 0.045), (x - 0.05, y + 0.045)], GOLD, w),
              poly([(x - 0.05, y + 0.045), (x + 0.05, y + 0.045), (x + 0.04, y + 0.052), (x - 0.04, y + 0.052)],
                   "#FBE3A0", w * 0.6))
    g.add(glint(0.05, 0.11, 0.02, w))
    return g, None


def _cash(m, w):
    c = col(m["color"]) if m.get("color") else "#7FB27F"
    g = VGroup()
    for i in range(5):
        y = i * 0.012
        g.add(rect(-0.13 + i * 0.004, y, 0.13 + i * 0.004, y + 0.012, tint(c, -0.1 * (i % 2)), w * 0.6))
    g.add(rect(-0.11, 0.06, 0.13, 0.16, c, w), Circle(radius=0.03, stroke_color=tint(c, -0.4), stroke_width=w * 0.8)
          .move_to([0.01, 0.11, 0]), letters(str(m.get("sign") or "$"), 0.01, 0.11, 0.04, tint(c, -0.45)),
          rect(-0.03, 0.0, 0.0, 0.17, "#E6D3A3", w * 0.5))
    return g, None


def _gem(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    g = VGroup(poly([(-0.08, 0.1), (-0.04, 0.14), (0.04, 0.14), (0.08, 0.1), (0.0, 0.0)], c, w),
               poly([(-0.08, 0.1), (0.08, 0.1), (0.0, 0.0)], tint(c, -0.2), w * 0.6),
               poly([(-0.04, 0.14), (0.04, 0.14), (0.02, 0.1), (-0.02, 0.1)], tint(c, 0.4), w * 0.6),
               glint(0.06, 0.15, 0.02, w))
    return g, None


def _crown(m, w):
    g = VGroup(poly([(-0.12, 0.0), (0.12, 0.0), (0.14, 0.13), (0.07, 0.07), (0.0, 0.16), (-0.07, 0.07), (-0.14, 0.13)],
                    GOLD, w),
               rect(-0.12, 0.0, 0.12, 0.03, GOLD_D, w * 0.7),
               *(circ(x, 0.015, 0.012, c, w * 0.4) for x, c in ((-0.06, RED), (0.0, "#3E7CB1"), (0.06, RED))),
               *(circ(x, y, 0.012, "#F7F5F0", w * 0.4) for x, y in ((-0.14, 0.135), (0.0, 0.165), (0.14, 0.135))))
    if m.get("cushion"):
        g.shift([0, 0.05, 0])
        g.add_to_back(blob([(-0.18, 0.0), (0.18, 0.0), (0.2, 0.05), (0.0, 0.07), (-0.2, 0.05)], RED, w))
    return g, None


def _chest(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    g = VGroup()
    inside = VGroup(rect(-0.2, 0.17, 0.2, 0.22, "#3A2A1E", w * 0.6),          # inside, dark, and the gold heaped
                    coin_pile(0.0, 0.17, 0.36, 4, w), glint(-0.08, 0.27, 0.025, w), glint(0.09, 0.24, 0.02, w),
                    circ(0.04, 0.24, 0.018, RED, w * 0.5), circ(-0.03, 0.25, 0.015, "#3E7CB1", w * 0.5))
    if m.get("empty"):
        inside = VGroup(rect(-0.2, 0.17, 0.2, 0.2, "#3A2A1E", w * 0.6))
    g.add(inside)
    g.add(rect(-0.22, 0.0, 0.22, 0.2, c, w),
          *(line((-0.22, y), (0.22, y), tint(c, -0.25), w * 0.7) for y in (0.065, 0.13)),
          rect(-0.22, 0.0, -0.18, 0.2, IRON, w * 0.7), rect(0.18, 0.0, 0.22, 0.2, IRON, w * 0.7),
          rect(-0.025, 0.12, 0.025, 0.19, GOLD, w * 0.7), Dot([0, 0.145, 0], radius=0.008, color=zoo.INK))
    lid = VGroup(blob([(-0.22, 0.2), (-0.21, 0.27), (-0.12, 0.31), (0.0, 0.32), (0.12, 0.31), (0.21, 0.27),
                       (0.22, 0.2)], tint(c, 0.08), w),
                 rect(-0.22, 0.2, -0.18, 0.28, IRON, w * 0.6), rect(0.18, 0.2, 0.22, 0.28, IRON, w * 0.6),
                 rect(-0.025, 0.19, 0.025, 0.24, GOLD, w * 0.7))
    g.add(lid)
    return g, (lid, (-0.22, 0.2), "swing", 1.9)


def _book(m, w):
    c = col(m["color"]) if m.get("color") else "#8E1B2C"
    g = VGroup(poly([(-0.09, 0.0), (0.07, 0.0), (0.09, 0.02), (0.09, 0.24), (-0.07, 0.24), (-0.09, 0.22)], "#F3EEE4", w),
               *(line((0.075, 0.03 + i * 0.03), (0.075, 0.2 + 0.0), "#C9C2B2", w * 0.4) for i in range(1)),
               poly([(-0.09, 0.0), (0.07, 0.0), (0.07, 0.22), (-0.09, 0.22)], c, w),
               rect(-0.09, 0.0, -0.06, 0.22, tint(c, -0.25), w * 0.7),
               rect(-0.04, 0.13, 0.05, 0.18, tint(c, 0.3), w * 0.5),
               *(line((-0.03, y), (0.04, y), tint(c, -0.35), w * 0.5) for y in (0.145, 0.165)))
    if m.get("gold", True):
        g.add(*(line((-0.06, y), (0.07, y), GOLD, w * 0.8) for y in (0.03, 0.19)))
    return g, None


def _books(m, w):
    g = VGroup()
    specs = [(-0.0, 0.0, 0.34, 0.06, "#2E5E4E"), (0.02, 0.06, 0.3, 0.055, "#8E1B2C"), (-0.02, 0.115, 0.32, 0.05, "#2F3B8C"),
             (0.01, 0.165, 0.26, 0.05, "#D4A017")]
    for x, y, wd, h, c in specs:
        g.add(rect(x - wd / 2, y, x + wd / 2, y + h, c, w), rect(x + wd / 2 - 0.02, y + 0.008, x + wd / 2, y + h - 0.008, "#F3EEE4", w * 0.5),
              line((x - wd / 2 + 0.04, y + 0.004), (x - wd / 2 + 0.04, y + h - 0.004), GOLD, w * 0.8))
    return g, None


def _openbook(m, w):
    g = VGroup(blob([(-0.25, 0.02), (0.0, 0.0), (0.25, 0.02), (0.26, 0.04), (0.0, 0.02), (-0.26, 0.04)], "#6B2A1E", w))
    for s in (-1, 1):
        g.add(poly([(0.0, 0.03), (s * 0.24, 0.05), (s * 0.24, 0.24), (s * 0.12, 0.25), (0.0, 0.22)], PAPER, w))
        for i in range(6):
            y = 0.2 - i * 0.025
            g.add(scribble(s * 0.03, s * 0.21, y + 0.005 * s * 0, w * 0.5))
    g.add(line((0.0, 0.03), (0.0, 0.22), "#C9BFA8", w))
    return g, None


def _ledger(m, w):
    g, _ = _openbook(m, w)
    for s in (-1, 1):
        for x in (0.15, 0.19):
            g.add(line((s * x, 0.06), (s * x, 0.22), "#C0392B", w * 0.4))
        for i in range(5):
            g.add(letters(str((i * 37) % 90 + 10), s * 0.17, 0.2 - i * 0.03, 0.018, "#3A3631"))
    return g, None


def _scroll(m, w):
    g = VGroup(rect(-0.1, 0.03, 0.1, 0.3, PAPER, w),
               *(scribble(-0.07, 0.07, y, w * 0.5) for y in np.linspace(0.26, 0.08, 6)),
               rrect(-0.13, 0.0, 0.13, 0.045, 0.02, "#E2D3B0", w), rrect(-0.13, 0.29, 0.13, 0.335, 0.02, "#E2D3B0", w),
               circ(-0.13, 0.022, 0.014, WOOD, w * 0.6), circ(0.13, 0.022, 0.014, WOOD, w * 0.6),
               circ(-0.13, 0.312, 0.014, WOOD, w * 0.6), circ(0.13, 0.312, 0.014, WOOD, w * 0.6))
    if m.get("rolled"):
        g = VGroup(rrect(-0.15, 0.0, 0.15, 0.07, 0.03, PAPER, w), stroke([(-0.02, 0.0), (-0.02, 0.07)], RED, w * 2),
                   circ(-0.02, 0.035, 0.018, RED, w * 0.6))
    return g, None


def _letter(m, w):
    c = col(m["color"]) if m.get("color") else "#F3EEE4"
    inside = VGroup(rect(-0.13, 0.05, 0.13, 0.2, PAPER, w * 0.7),
                    *(scribble(-0.1, 0.1, y, w * 0.4) for y in (0.17, 0.14, 0.11)))
    body = VGroup(rect(-0.15, 0.0, 0.15, 0.18, c, w),
                  stroke([(-0.15, 0.0), (0.0, 0.09), (0.15, 0.0)], tint(c, -0.2), w * 0.7))
    flap = VGroup(poly([(-0.15, 0.18), (0.15, 0.18), (0.0, 0.07)], tint(c, -0.06), w),
                  circ(0.0, 0.08, 0.024, RED, w * 0.6))
    return VGroup(inside, body, flap), (flap, (0.0, 0.18), "flip", 1.0)


def _document(m, w):
    g = VGroup(poly([(-0.13, 0.0), (0.13, 0.0), (0.13, 0.32), (-0.1, 0.32), (-0.13, 0.29)], PAPER, w),
               poly([(-0.13, 0.29), (-0.1, 0.29), (-0.1, 0.32)], tint(PAPER, -0.12), w * 0.6),
               rect(-0.09, 0.26, 0.05, 0.28, "#6B6258", 0),
               *(scribble(-0.09, 0.09, y, w * 0.5) for y in np.linspace(0.23, 0.09, 6)),
               stroke([(0.02, 0.04), (0.04, 0.06), (0.06, 0.035), (0.08, 0.055), (0.1, 0.04)], "#2F3B8C", w))
    return g, None


def _charter(m, w):
    g = VGroup(poly([(-0.15, 0.03), (0.15, 0.0), (0.16, 0.36), (-0.14, 0.37)], "#EFE1BE", w),
               *(scribble(-0.11, 0.12, y, w * 0.5) for y in np.linspace(0.3, 0.12, 7)),
               letters(str(m.get("label") or "Charter"), 0.0, 0.335, 0.04, "#6B2A1E"),
               poly([(-0.02, 0.05), (0.0, -0.06), (0.02, -0.03), (0.04, -0.07), (0.05, 0.04)], RED, w * 0.6),
               circ(0.015, 0.05, 0.04, "#A0281F", w), circ(0.015, 0.05, 0.026, "#C0392B", w * 0.5))
    return g, None


def _newspaper(m, w):
    g = VGroup(rect(-0.18, 0.0, 0.18, 0.3, "#EDE8DC", w),
               letters(str(m.get("label") or "THE TIMES"), 0.0, 0.27, 0.035, "#22201E"),
               line((-0.16, 0.245), (0.16, 0.245), "#22201E", w),
               rect(-0.16, 0.13, 0.0, 0.23, "#B9B2A4", w * 0.5),
               *(scribble(0.02, 0.16, y, w * 0.4, "#8C857A") for y in np.linspace(0.22, 0.14, 4)),
               *(scribble(-0.16, 0.16, y, w * 0.4, "#8C857A") for y in np.linspace(0.11, 0.03, 4)))
    return g, None


def _oldmap(m, w):
    g = VGroup(poly([(-0.25, 0.0), (0.25, 0.02), (0.24, 0.3), (-0.24, 0.32)], "#EFE1BE", w),
               blob([(-0.18, 0.08), (-0.1, 0.22), (-0.02, 0.2), (0.0, 0.1), (-0.08, 0.05)], "#C9D6A0", w * 0.6),
               blob([(0.06, 0.14), (0.14, 0.26), (0.2, 0.18), (0.16, 0.08)], "#C9D6A0", w * 0.6),
               stroke([(-0.1, 0.12), (0.0, 0.16), (0.08, 0.14), (0.16, 0.16)], RED, w * 0.8),
               letters("x", 0.16, 0.165, 0.04, RED),
               circ(0.19, 0.06, 0.03, "#EFE1BE", w * 0.6), line((0.19, 0.03), (0.19, 0.09), "#6B4A2F", w * 0.6),
               line((0.16, 0.06), (0.22, 0.06), "#6B4A2F", w * 0.6))
    return g, None


def _quill(m, w):
    g = VGroup(*_inkwell(m, w)[0], blob([(0.02, 0.1), (0.07, 0.22), (0.13, 0.38), (0.09, 0.34), (0.05, 0.25), (0.02, 0.15)],
                                        "#F7F5F0", w),
               stroke([(0.025, 0.1), (0.1, 0.33)], "#C9C2B2", w * 0.6))
    return g, None


def _inkwell(m, w):
    return VGroup(poly([(-0.05, 0.0), (0.05, 0.0), (0.06, 0.06), (0.03, 0.09), (-0.03, 0.09), (-0.06, 0.06)], "#2F3B4C", w),
                  ell(0.0, 0.095, 0.06, 0.015, "#22201E", w * 0.6),
                  fill_only([(-0.04, 0.01), (-0.045, 0.05), (-0.025, 0.07), (-0.03, 0.02)], "#5E6E86")), None


def _seal(m, w):
    return VGroup(circ(0.0, 0.07, 0.07, "#A0281F", w), circ(0.0, 0.07, 0.048, "#C0392B", w * 0.5),
                  letters(str(m.get("sign") or "R"), 0.0, 0.07, 0.05, "#7A1F17")), None


def _table(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    g = VGroup(rect(-0.3, 0.3, 0.3, 0.34, c, w), rect(-0.28, 0.27, 0.28, 0.3, tint(c, -0.2), w * 0.7),
               *(poly([(x - 0.02, 0.27), (x + 0.02, 0.27), (x + 0.015, 0.0), (x - 0.015, 0.0)], tint(c, -0.1), w)
                 for x in (-0.25, 0.25)),
               line((-0.22, 0.32), (0.22, 0.32), tint(c, 0.2), w * 0.6))
    if m.get("cloth"):
        g.add(poly([(-0.31, 0.345), (0.31, 0.345), (0.33, 0.2), (-0.33, 0.2)], col(m["cloth"]), w))
    return g, None


def _desk(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    g = VGroup(rect(-0.32, 0.31, 0.32, 0.35, tint(c, 0.08), w), rect(0.06, 0.0, 0.3, 0.31, c, w),
               *(rect(0.08, y, 0.28, y + 0.08, tint(c, -0.08), w * 0.7) for y in (0.03, 0.12, 0.21)),
               *(Dot([0.18, y + 0.04, 0], radius=0.008, color=GOLD) for y in (0.03, 0.12, 0.21)),
               poly([(-0.29, 0.31), (-0.26, 0.31), (-0.26, 0.0), (-0.29, 0.0)], tint(c, -0.1), w))
    return g, None


def _chair(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(rect(-0.12, 0.2, -0.09, 0.52, tint(c, -0.1), w), rect(-0.12, 0.42, 0.0, 0.48, c, w * 0.8),
                  rect(-0.12, 0.2, 0.13, 0.24, c, w),
                  *(rect(x, 0.0, x + 0.025, 0.2, tint(c, -0.15), w * 0.8) for x in (-0.11, 0.1)),
                  rect(-0.12, 0.33, -0.09, 0.36, tint(c, -0.25), 0)), None


def _stool(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(ell(0.0, 0.2, 0.24, 0.05, c, w), line((-0.08, 0.19), (-0.1, 0.0), tint(c, -0.2), w * 2.4),
                  line((0.08, 0.19), (0.1, 0.0), tint(c, -0.2), w * 2.4), line((-0.09, 0.08), (0.09, 0.08), tint(c, -0.2), w * 1.4)), None


def _throne(m, w):
    c = col(m["color"]) if m.get("color") else RED
    g = VGroup(blob([(-0.2, 0.2), (-0.21, 0.6), (-0.12, 0.72), (0.0, 0.78), (0.12, 0.72), (0.21, 0.6), (0.2, 0.2)], GOLD, w),
               blob([(-0.15, 0.24), (-0.15, 0.58), (0.0, 0.68), (0.15, 0.58), (0.15, 0.24)], c, w),
               circ(0.0, 0.72, 0.03, RED, w * 0.6),
               rect(-0.26, 0.18, 0.26, 0.26, GOLD_D, w), rect(-0.22, 0.24, 0.22, 0.3, c, w),
               rect(-0.26, 0.26, -0.2, 0.42, GOLD, w), rect(0.2, 0.26, 0.26, 0.42, GOLD, w),
               *(rect(x, 0.0, x + 0.05, 0.18, GOLD_D, w) for x in (-0.25, 0.2)),
               *(Dot([x, 0.47, 0], radius=0.012, color="#F7F5F0") for x in (-0.07, 0.0, 0.07)))
    return g, None


def _bench(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(rect(-0.4, 0.18, 0.4, 0.22, c, w), *(rect(x, 0.0, x + 0.04, 0.18, tint(c, -0.15), w) for x in (-0.36, 0.32))), None


def _bookshelf(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    g = VGroup(rect(-0.3, 0.0, 0.3, 0.9, tint(c, -0.15), w), rect(-0.27, 0.03, 0.27, 0.87, "#4A3424", w * 0.6))
    cols = ["#8E1B2C", "#2E5E4E", "#2F3B8C", "#D4A017", "#6B4226", "#3E7CB1", "#B83227"]
    for r, y in enumerate((0.03, 0.31, 0.59)):
        g.add(rect(-0.28, y + 0.25, 0.28, y + 0.28, c, w * 0.6))
        x = -0.26
        i = r * 3
        while x < 0.22:
            bw = 0.035 + 0.01 * ((i * 7) % 3)
            bh = 0.2 + 0.02 * ((i * 5) % 3)
            g.add(rect(x, y, x + bw, y + bh, cols[i % len(cols)], w * 0.5),
                  line((x + 0.005, y + bh - 0.03), (x + bw - 0.005, y + bh - 0.03), GOLD, w * 0.5))
            x += bw + 0.004
            i += 1
    return g, None


def _lectern(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(poly([(-0.06, 0.0), (0.06, 0.0), (0.04, 0.42), (-0.04, 0.42)], tint(c, -0.1), w),
                  rect(-0.12, 0.0, 0.12, 0.04, c, w),
                  poly([(-0.18, 0.4), (0.18, 0.46), (0.18, 0.5), (-0.18, 0.44)], c, w)), None


def _bed(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(rect(-0.45, 0.0, -0.41, 0.45, c, w), rect(0.41, 0.0, 0.45, 0.32, c, w),
                  rect(-0.41, 0.12, 0.41, 0.2, tint(c, -0.15), w),
                  rrect(-0.41, 0.2, 0.41, 0.28, 0.03, "#F3EEE4", w), rrect(-0.4, 0.27, -0.2, 0.34, 0.03, "#FFFFFF", w),
                  rrect(-0.18, 0.2, 0.41, 0.3, 0.03, col(m.get("cloth") or "#3E7CB1"), w)), None


def _barrel(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    g = VGroup(blob([(-0.12, 0.0), (-0.15, 0.17), (-0.12, 0.34), (0.12, 0.34), (0.15, 0.17), (0.12, 0.0)], c, w),
               *(stroke([(x * 0.8, 0.01), (x, 0.17), (x * 0.8, 0.33)], tint(c, -0.2), w * 0.6) for x in (-0.07, 0.0, 0.07)),
               *(stroke([(-0.135 * k, y), (0.135 * k, y)], IRON, w * 2.2) for y, k in ((0.05, 0.9), (0.29, 0.9), (0.17, 1.08))),
               ell(0.0, 0.34, 0.24, 0.04, tint(c, -0.15), w * 0.8))
    return g, None


def _crate(m, w):
    c = col(m["color"]) if m.get("color") else "#C9A066"
    g = VGroup(rect(-0.16, 0.0, 0.16, 0.28, c, w), rect(-0.13, 0.03, 0.13, 0.25, tint(c, 0.1), w * 0.6),
               line((-0.13, 0.03), (0.13, 0.25), tint(c, -0.25), w * 2.4))
    if m.get("label"):
        g.add(letters(str(m["label"]), 0.0, 0.14, 0.05, "#6B4A2F"))
    return g, None


def _box(m, w):
    c = col(m["color"]) if m.get("color") else "#C9A066"
    inside = VGroup(rect(-0.15, 0.2, 0.15, 0.24, "#6B4A2F", w * 0.5))
    g = VGroup(inside, rect(-0.16, 0.0, 0.16, 0.22, c, w), line((-0.16, 0.18), (0.16, 0.18), tint(c, -0.2), w * 0.6))
    lid = VGroup(rect(-0.17, 0.21, 0.17, 0.25, tint(c, 0.05), w))
    g.add(lid)
    return g, (lid, (-0.17, 0.21), "swing", 1.8)


def _sack(m, w):
    c = col(m["color"]) if m.get("color") else "#D9C49A"
    g = VGroup(blob([(-0.04, 0.3), (-0.13, 0.22), (-0.15, 0.06), (-0.1, 0.0), (0.1, 0.0), (0.15, 0.06), (0.13, 0.22),
                     (0.04, 0.3)], c, w),
               blob([(-0.04, 0.3), (-0.07, 0.35), (0.0, 0.33), (0.07, 0.35), (0.04, 0.3)], tint(c, -0.08), w * 0.8),
               stroke([(-0.045, 0.3), (0.045, 0.3)], "#6B4A2F", w * 2.0),
               stroke([(-0.08, 0.1), (-0.03, 0.18)], tint(c, -0.2), w * 0.6), stroke([(0.05, 0.06), (0.09, 0.15)], tint(c, -0.2), w * 0.6))
    if m.get("label"):
        g.add(letters(str(m["label"]), 0.0, 0.14, 0.05, "#6B4A2F"))
    return g, None


def _basket(m, w):
    g = VGroup()
    fill = str(m.get("of") or "fruit")
    if fill != "none":
        cols = {"fruit": ["#D63B2F", "#F2C14E", "#E07B39", "#7BB04B"], "bread": ["#D9A15A", "#C98A44"],
                "flowers": ["#D46A9A", "#F2C14E", "#F7F5F0"], "grain": ["#E2C27A"], "fish": ["#8EA3B5"]}.get(fill, ["#D63B2F", "#F2C14E"])
        for i, x in enumerate(np.linspace(-0.12, 0.12, 6)):
            g.add(circ(x, 0.17 + 0.02 * math.sin(i * 2.1), 0.04, cols[i % len(cols)], w * 0.7))
    g.add(stroke(zoo.P._arc(0.0, 0.16, 0.13, 10, 170, 12), "#8C6E2E", w * 1.6),
          poly([(-0.17, 0.17), (0.17, 0.17), (0.13, 0.0), (-0.13, 0.0)], "#C9A066", w),
          *(line((-0.15 + i * 0.03, 0.16), (-0.12 + i * 0.025, 0.01), "#9A7B4F", w * 0.5) for i in range(11)),
          *(stroke([(-0.16, y), (0.16, y)], "#9A7B4F", w * 0.6) for y in (0.06, 0.11)))
    return g, None


def _pot(m, w):
    c = col(m["color"]) if m.get("color") else "#B5643C"
    return VGroup(blob([(-0.06, 0.22), (-0.15, 0.14), (-0.12, 0.03), (0.0, 0.0), (0.12, 0.03), (0.15, 0.14), (0.06, 0.22)], c, w),
                  ell(0.0, 0.225, 0.14, 0.035, tint(c, -0.15), w),
                  stroke([(-0.13, 0.12), (0.13, 0.12)], "#F3EADA", w * 1.2),
                  *(Dot([x, 0.095, 0], radius=0.008, color="#F3EADA") for x in np.linspace(-0.1, 0.1, 6))), None


def _jar(m, w):
    c = col(m["color"]) if m.get("color") else "#C97B4A"
    return VGroup(blob([(-0.04, 0.38), (-0.05, 0.3), (-0.13, 0.22), (-0.1, 0.08), (0.0, 0.0), (0.1, 0.08), (0.13, 0.22),
                        (0.05, 0.3), (0.04, 0.38)], c, w),
                  stroke([(-0.05, 0.33), (-0.12, 0.33), (-0.11, 0.25)], c, w * 2.4), stroke([(0.05, 0.33), (0.12, 0.33), (0.11, 0.25)], c, w * 2.4),
                  stroke([(-0.11, 0.18), (0.11, 0.18)], "#22201E", w * 1.4)), None


def _bucket(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(stroke(zoo.P._arc(0.0, 0.2, 0.11, 0, 180, 12), IRON, w * 1.2),
                  poly([(-0.11, 0.2), (0.11, 0.2), (0.09, 0.0), (-0.09, 0.0)], c, w),
                  *(stroke([(-0.105, y), (0.105, y)], IRON, w * 1.6) for y in (0.04, 0.16)),
                  ell(0.0, 0.2, 0.22, 0.03, "#5B8FB9", w * 0.6)), None


def _candle(m, w):
    return VGroup(ell(0.0, 0.01, 0.14, 0.03, GOLD_D, w), rect(-0.03, 0.01, 0.03, 0.2, "#F7F3E8", w),
                  fill_only([(-0.03, 0.2), (-0.02, 0.17), (0.0, 0.19)], "#E6DCC8"),
                  line((0.0, 0.2), (0.0, 0.215), zoo.INK, w),
                  blob([(0.0, 0.21), (-0.02, 0.24), (0.0, 0.29), (0.02, 0.24)], "#F2C14E", w * 0.6),
                  blob([(0.0, 0.215), (-0.008, 0.235), (0.0, 0.26), (0.008, 0.235)], "#E4572E", 0)), None


def _diya(m, w):
    return VGroup(blob([(-0.12, 0.05), (-0.06, 0.0), (0.06, 0.0), (0.12, 0.05), (0.16, 0.07), (0.0, 0.06)], "#C2552B", w),
                  *(Dot([x, 0.03, 0], radius=0.008, color="#F2C14E") for x in (-0.06, 0.0, 0.06)),
                  blob([(0.12, 0.07), (0.11, 0.11), (0.13, 0.17), (0.15, 0.11)], "#F2C14E", w * 0.6),
                  blob([(0.13, 0.08), (0.125, 0.11), (0.13, 0.14), (0.137, 0.11)], "#E4572E", 0)), None


def _lantern(m, w):
    return VGroup(stroke(zoo.P._arc(0.0, 0.3, 0.04, 0, 180, 8), zoo.INK, w),
                  poly([(-0.07, 0.28), (0.07, 0.28), (0.0, 0.33)], "#3A3631", w),
                  rect(-0.06, 0.06, 0.06, 0.28, "#FBE7A1", w),
                  blob([(0.0, 0.1), (-0.025, 0.15), (0.0, 0.22), (0.025, 0.15)], "#F2A93B", 0),
                  *(line((x, 0.06), (x, 0.28), "#3A3631", w * 1.2) for x in (-0.06, 0.0, 0.06)),
                  rect(-0.08, 0.0, 0.08, 0.06, "#3A3631", w)), None


def _campfire(m, w):
    return VGroup(*(poly([(x0, 0.0), (x0 + 0.03, 0.02), (x1 + 0.03, 0.08), (x1, 0.06)], WOOD_D, w) for x0, x1 in
                    ((-0.18, 0.12), (0.18, -0.12))),
                  blob([(-0.12, 0.04), (-0.1, 0.18), (-0.04, 0.14), (0.0, 0.32), (0.05, 0.15), (0.1, 0.22), (0.12, 0.04)],
                       "#E4572E", w),
                  blob([(-0.06, 0.04), (-0.04, 0.14), (0.0, 0.22), (0.04, 0.12), (0.06, 0.04)], "#F2C14E", w * 0.5),
                  *(circ(x, 0.015, 0.035, "#8E969C", w * 0.7) for x in (-0.2, -0.12, 0.12, 0.2))), None


def _sword(m, w):
    return VGroup(poly([(-0.018, 0.12), (0.018, 0.12), (0.014, 0.58), (0.0, 0.63), (-0.014, 0.58)], "#C9D0D4", w),
                  line((0.0, 0.14), (0.0, 0.56), "#9AA3A9", w * 0.6),
                  rect(-0.08, 0.1, 0.08, 0.125, GOLD, w * 0.8), rect(-0.015, 0.02, 0.015, 0.1, "#5B4A3A", w * 0.8),
                  circ(0.0, 0.015, 0.02, GOLD, w * 0.7)), None


def _shield(m, w):
    c = col(m["color"]) if m.get("color") else "#2F5E9E"
    return VGroup(blob([(-0.17, 0.4), (0.17, 0.4), (0.16, 0.14), (0.0, 0.0), (-0.16, 0.14)], c, w),
                  blob([(-0.13, 0.37), (0.13, 0.37), (0.12, 0.15), (0.0, 0.04), (-0.12, 0.15)], tint(c, 0.1), w * 0.5),
                  poly([(-0.02, 0.33), (0.02, 0.33), (0.02, 0.08), (-0.02, 0.08)], GOLD, w * 0.6),
                  poly([(-0.11, 0.25), (0.11, 0.25), (0.11, 0.21), (-0.11, 0.21)], GOLD, w * 0.6)), None


def _spear(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.85), WOOD, w * 3), poly([(-0.03, 0.84), (0.03, 0.84), (0.0, 0.98)], "#C9D0D4", w),
                  stroke([(-0.02, 0.8), (0.02, 0.8)], RED, w * 2)), None


def _bow(m, w):
    return VGroup(stroke(zoo.P._arc(-0.25, 0.3, 0.32, -60, 60, 16), WOOD, w * 3),
                  line((-0.09, 0.02), (-0.09, 0.58), "#3A3631", w * 0.6),
                  line((-0.2, 0.3), (0.12, 0.3), WOOD_D, w * 1.2), poly([(0.12, 0.28), (0.12, 0.32), (0.16, 0.3)], IRON, w * 0.6)), None


def _cannon(m, w):
    return VGroup(tube([(-0.3, 0.18), (0.0, 0.22), (0.3, 0.27)], [0.16, 0.13, 0.1], "#3A3631", w),
                  ell(0.31, 0.27, 0.04, 0.1, "#22201E", w), circ(-0.32, 0.18, 0.04, "#3A3631", w),
                  stroke([(-0.18, 0.26), (-0.18, 0.12)], GOLD_D, w * 1.2), stroke([(0.1, 0.29), (0.1, 0.16)], GOLD_D, w * 1.2),
                  poly([(-0.25, 0.1), (0.1, 0.1), (0.05, 0.16), (-0.2, 0.16)], WOOD, w),
                  circ(-0.1, 0.1, 0.1, WOOD_D, w), circ(-0.1, 0.1, 0.03, IRON, w * 0.6),
                  *(line((-0.1, 0.1), (-0.1 + 0.09 * math.cos(a), 0.1 + 0.09 * math.sin(a)), WOOD, w) for a in np.linspace(0, math.pi, 4)),
                  *(circ(0.3 + i * 0.07, 0.03, 0.03, "#22201E", w * 0.6) for i in range(2))), None


def _anvil(m, w):
    return VGroup(poly([(-0.1, 0.0), (0.1, 0.0), (0.06, 0.08), (0.05, 0.14), (-0.05, 0.14), (-0.06, 0.08)], "#5A5F63", w),
                  blob([(-0.16, 0.14), (0.12, 0.14), (0.2, 0.2), (0.12, 0.22), (-0.16, 0.22)], "#6E747A", w),
                  stroke([(-0.14, 0.21), (0.1, 0.21)], "#9AA3A9", w * 0.8)), None


def _plough(m, w):
    return VGroup(line((-0.4, 0.3), (0.1, 0.08), WOOD, w * 3.2), line((0.1, 0.08), (0.25, 0.02), WOOD, w * 3.2),
                  poly([(0.2, 0.0), (0.32, 0.0), (0.26, 0.06)], IRON, w), line((-0.4, 0.3), (-0.45, 0.42), WOOD, w * 2.6),
                  line((0.05, 0.1), (0.05, 0.0), WOOD_D, w * 2.6)), None


def _wheel(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    g = VGroup(Circle(radius=0.2, stroke_color=zoo.INK, stroke_width=w * 4.4).move_to([0, 0.2, 0]),
               Circle(radius=0.2, stroke_color=c, stroke_width=w * 2.6).move_to([0, 0.2, 0]))
    for a in np.linspace(0, math.pi, 7)[:-1]:
        g.add(line((0.19 * math.cos(a), 0.2 + 0.19 * math.sin(a)), (-0.19 * math.cos(a), 0.2 - 0.19 * math.sin(a)), c, w * 1.6))
    g.add(circ(0.0, 0.2, 0.035, tint(c, -0.2), w))
    return g, None


def _charkha(m, w):
    g, _ = _wheel({"color": "#8C6E2E"}, w)
    g.shift([-0.12, 0.05, 0])
    g.add(rect(-0.4, 0.0, 0.32, 0.04, WOOD, w), line((-0.12, 0.04), (-0.12, 0.22), WOOD_D, w * 2),
          line((0.22, 0.04), (0.22, 0.13), WOOD_D, w * 2), circ(0.22, 0.14, 0.02, WOOD, w * 0.6),
          stroke([(0.08, 0.25), (0.22, 0.15)], "#F7F5F0", w * 0.6), stroke([(0.08, 0.05), (0.22, 0.13)], "#F7F5F0", w * 0.6))
    return g, None


def _scales(m, w):
    g = VGroup(rect(-0.1, 0.0, 0.1, 0.03, GOLD_D, w), line((0.0, 0.03), (0.0, 0.42), GOLD_D, w * 2),
               line((-0.22, 0.4), (0.22, 0.4), GOLD_D, w * 2), circ(0.0, 0.43, 0.02, GOLD, w * 0.6))
    for s in (-1, 1):
        g.add(line((s * 0.22, 0.4), (s * 0.15, 0.22), GOLD_D, w * 0.6), line((s * 0.22, 0.4), (s * 0.29, 0.22), GOLD_D, w * 0.6),
              poly([(s * 0.13, 0.22), (s * 0.31, 0.22), (s * 0.27, 0.18), (s * 0.17, 0.18)], GOLD, w))
    return g, None


def _hourglass(m, w):
    return VGroup(rect(-0.1, 0.0, 0.1, 0.03, WOOD, w), rect(-0.1, 0.3, 0.1, 0.33, WOOD, w),
                  blob([(-0.07, 0.3), (0.07, 0.3), (0.01, 0.165), (0.07, 0.03), (-0.07, 0.03), (-0.01, 0.165)], "#E8F1F4", w * 0.8),
                  poly([(-0.045, 0.24), (0.045, 0.24), (0.0, 0.17)], "#E2C27A", 0),
                  poly([(-0.06, 0.035), (0.06, 0.035), (0.0, 0.1)], "#E2C27A", 0),
                  line((0.0, 0.17), (0.0, 0.1), "#E2C27A", w * 0.6),
                  *(line((x, 0.03), (x, 0.3), WOOD_D, w * 1.4) for x in (-0.085, 0.085))), None


def _key(m, w):
    return VGroup(Circle(radius=0.05, stroke_color=zoo.INK, stroke_width=w * 3.6).move_to([-0.12, 0.06, 0]),
                  Circle(radius=0.05, stroke_color=GOLD, stroke_width=w * 2).move_to([-0.12, 0.06, 0]),
                  rect(-0.07, 0.05, 0.15, 0.075, GOLD, w), rect(0.1, 0.0, 0.12, 0.05, GOLD, w * 0.8),
                  rect(0.13, 0.015, 0.15, 0.05, GOLD, w * 0.8)), None


def _bell(m, w):
    return VGroup(blob([(-0.14, 0.04), (-0.1, 0.18), (-0.06, 0.26), (0.0, 0.28), (0.06, 0.26), (0.1, 0.18), (0.14, 0.04)], GOLD, w),
                  rrect(-0.16, 0.02, 0.16, 0.05, 0.015, GOLD_D, w), circ(0.0, 0.01, 0.03, GOLD_D, w * 0.7),
                  stroke([(-0.06, 0.22), (-0.09, 0.08)], "#FBE3A0", w * 1.2)), None


def _goblet(m, w):
    return VGroup(ell(0.0, 0.01, 0.14, 0.03, GOLD_D, w), line((0.0, 0.01), (0.0, 0.12), GOLD_D, w * 2.4),
                  blob([(-0.08, 0.24), (-0.07, 0.16), (0.0, 0.12), (0.07, 0.16), (0.08, 0.24)], GOLD, w),
                  ell(0.0, 0.24, 0.16, 0.03, "#8E1B2C", w * 0.6), circ(0.0, 0.18, 0.015, RED, w * 0.4)), None


def _telescope(m, w):
    return VGroup(tube([(-0.2, 0.3), (0.0, 0.38), (0.2, 0.46)], [0.05, 0.065, 0.08], "#B8892E", w),
                  *(line((x, 0.0), (0.0, 0.33), WOOD_D, w * 1.6) for x in (-0.12, 0.0, 0.12)),
                  ell(0.205, 0.465, 0.03, 0.08, "#9FC5DA", w * 0.6)), None


def _lightbulb(m, w):
    return VGroup(*(line((0.12 * math.cos(a), 0.22 + 0.12 * math.sin(a)), (0.17 * math.cos(a), 0.22 + 0.17 * math.sin(a)), GOLD_D, w)
                    for a in np.linspace(0.3, math.pi - 0.3, 5)),
                  blob([(-0.04, 0.08), (-0.09, 0.17), (-0.07, 0.27), (0.0, 0.3), (0.07, 0.27), (0.09, 0.17), (0.04, 0.08)], "#FBE7A1", w),
                  stroke([(-0.02, 0.1), (-0.015, 0.18), (0.0, 0.15), (0.015, 0.18), (0.02, 0.1)], "#C9962B", w * 0.8),
                  rect(-0.04, 0.0, 0.04, 0.08, "#9AA3A9", w), *(line((-0.04, y), (0.04, y), "#6E747A", w * 0.6) for y in (0.025, 0.05))), None


def _printingpress(m, w):
    return VGroup(rect(-0.3, 0.0, -0.25, 0.9, WOOD, w), rect(0.25, 0.0, 0.3, 0.9, WOOD, w), rect(-0.32, 0.85, 0.32, 0.92, WOOD_D, w),
                  line((0.0, 0.85), (0.0, 0.55), IRON, w * 3), line((-0.18, 0.7), (0.18, 0.7), WOOD_D, w * 2.6),
                  rect(-0.18, 0.47, 0.18, 0.55, "#5A5F63", w), rect(-0.25, 0.32, 0.25, 0.4, WOOD_D, w),
                  rect(-0.16, 0.4, 0.16, 0.44, PAPER, w * 0.7), rect(-0.25, 0.3, 0.25, 0.32, WOOD, 0)), None


# -- places and big things ---------------------------------------------------------------------------------------

def _tree(m, w):
    c = col(m["color"]) if m.get("color") else "#5B8C3A"
    g = VGroup(poly([(-0.06, 0.0), (0.06, 0.0), (0.045, 0.6), (-0.045, 0.6)], "#7A5634", w),
               stroke([(0.02, 0.45), (0.12, 0.62)], "#7A5634", w * 2.4))
    for x, y, r in ((-0.2, 0.75, 0.2), (0.18, 0.78, 0.2), (0.0, 0.95, 0.25), (-0.05, 0.7, 0.18), (0.12, 1.02, 0.15)):
        g.add(circ(x, y, r, c, w))
    g.add(*(fill_only(zoo.P._arc(x + 0.04, y + 0.04, r * 0.5, 0, 360, 12), tint(c, 0.2), 0.6) for x, y, r in ((-0.2, 0.75, 0.2), (0.0, 0.95, 0.25))))
    if m.get("fruit"):
        g.add(*(circ(x, y, 0.025, "#D63B2F", w * 0.5) for x, y in ((-0.2, 0.68), (0.15, 0.75), (0.05, 0.9), (-0.08, 1.0))))
    return g, None


def _palm(m, w):
    g = VGroup(tube([(0.0, 0.0), (0.04, 0.4), (0.12, 0.85)], [0.08, 0.065, 0.05], "#A7804F", w))
    for i in range(6):
        g.add(stroke([(0.07, 0.38 + i * 0.08), (0.11, 0.39 + i * 0.08)], "#7A5634", w * 0.8))
    for a in (-160, -120, -60, -20, 20, 160):
        r = 0.36
        ex, ey = 0.12 + r * math.cos(math.radians(a)) * 1.1, 0.86 + r * 0.5 * math.sin(math.radians(a)) - 0.08
        g.add(tube([(0.12, 0.86), ((0.12 + ex) / 2, 0.92 + 0.02 * math.sin(math.radians(a))), (ex, ey)], [0.06, 0.07, 0.01], "#4F8A3A", w))
    g.add(*(circ(0.1 + dx, 0.82, 0.03, "#6B4A2F", w * 0.6) for dx in (-0.03, 0.02)))
    return g, None


def _bush(m, w):
    c = col(m["color"]) if m.get("color") else "#5B8C3A"
    return VGroup(*(circ(x, y, r, c, w) for x, y, r in ((-0.12, 0.1, 0.1), (0.12, 0.1, 0.1), (0.0, 0.16, 0.13))),
                  rect(-0.2, 0.0, 0.2, 0.05, c, 0)), None


def _rock(m, w):
    return VGroup(blob([(-0.2, 0.0), (-0.18, 0.12), (-0.05, 0.2), (0.1, 0.17), (0.2, 0.06), (0.18, 0.0)], "#9A9690", w),
                  stroke([(-0.08, 0.14), (0.0, 0.08), (0.05, 0.12)], "#77736C", w * 0.7)), None


def _well(m, w):
    return VGroup(rect(-0.22, 0.0, 0.22, 0.25, "#B8AE9C", w),
                  *(line((-0.22, y), (0.22, y), "#8E8576", w * 0.6) for y in (0.08, 0.16)),
                  ell(0.0, 0.25, 0.44, 0.06, "#4A4440", w), line((-0.2, 0.25), (-0.2, 0.6), WOOD, w * 2.6),
                  line((0.2, 0.25), (0.2, 0.6), WOOD, w * 2.6), poly([(-0.27, 0.58), (0.0, 0.72), (0.27, 0.58)], "#8E1B2C", w),
                  line((-0.2, 0.5), (0.2, 0.5), WOOD_D, w * 1.8), line((0.0, 0.5), (0.0, 0.36), "#3A3631", w * 0.6),
                  rect(-0.04, 0.3, 0.04, 0.36, WOOD, w * 0.7)), None


def _tent(m, w):
    c = col(m["color"]) if m.get("color") else "#E9DFC6"
    return VGroup(poly([(-0.45, 0.0), (0.0, 0.7), (0.45, 0.0)], c, w),
                  poly([(-0.1, 0.0), (0.0, 0.42), (0.1, 0.0)], tint(c, -0.4), w),
                  line((0.0, 0.7), (0.0, 0.82), WOOD, w * 1.6), poly([(0.0, 0.82), (0.12, 0.78), (0.0, 0.74)], RED, w * 0.6),
                  stroke([(-0.3, 0.23), (0.3, 0.23)], tint(c, -0.15), w * 0.8)), None


def _hut(m, w):
    c = col(m["color"]) if m.get("color") else "#C9A066"
    return VGroup(rect(-0.32, 0.0, 0.32, 0.4, c, w), rect(-0.07, 0.0, 0.07, 0.26, WOOD_D, w),
                  blob([(-0.45, 0.36), (0.0, 0.78), (0.45, 0.36), (0.0, 0.42)], "#B59A4A", w),
                  *(stroke([(x, 0.4 + 0.3 * (1 - abs(x) / 0.45)), (x * 1.08, 0.36)], "#8C7330", w * 0.6) for x in np.linspace(-0.35, 0.35, 8)),
                  rect(0.14, 0.18, 0.25, 0.28, "#4A3424", w * 0.8)), None


def _house(m, w):
    c = col(m["color"]) if m.get("color") else "#E8D5B5"
    g = VGroup(rect(-0.38, 0.0, 0.38, 0.55, c, w), poly([(-0.45, 0.53), (0.0, 0.9), (0.45, 0.53)], "#B5543C", w),
               rect(-0.08, 0.0, 0.08, 0.3, WOOD, w), Dot([0.05, 0.15, 0], radius=0.01, color=GOLD),
               rect(0.22, 0.62, 0.3, 0.82, "#8E5A3C", w))
    for x in (-0.26, 0.2):
        g.add(rect(x - 0.06, 0.3, x + 0.06, 0.44, "#9FC5DA", w), line((x, 0.3), (x, 0.44), zoo.INK, w * 0.6),
              line((x - 0.06, 0.37), (x + 0.06, 0.37), zoo.INK, w * 0.6))
    return g, None


def _tower(m, w):
    c = col(m["color"]) if m.get("color") else "#B8AE9C"
    g = VGroup(rect(-0.18, 0.0, 0.18, 0.95, c, w))
    for i in range(4):
        g.add(rect(-0.22 + i * 0.12, 0.95, -0.14 + i * 0.12, 1.04, c, w))
    g.add(rect(-0.22, 0.9, 0.22, 0.96, tint(c, -0.1), w), blob([(-0.06, 0.0), (-0.06, 0.18), (0.0, 0.24), (0.06, 0.18), (0.06, 0.0)], WOOD_D, w),
          blob([(-0.03, 0.55), (-0.03, 0.66), (0.0, 0.7), (0.03, 0.66), (0.03, 0.55)], "#3A3631", w),
          *(line((-0.18, y), (0.18, y), tint(c, -0.2), w * 0.5) for y in (0.3, 0.45, 0.78)),
          line((0.0, 1.04), (0.0, 1.22), WOOD, w * 1.4), poly([(0.0, 1.22), (0.16, 1.17), (0.0, 1.12)], col(m.get("flag") or RED), w * 0.7))
    return g, None


def _gate(m, w):
    c = col(m["color"]) if m.get("color") else "#B8AE9C"
    g = VGroup(rect(-0.45, 0.0, -0.25, 0.85, c, w), rect(0.25, 0.0, 0.45, 0.85, c, w),
               blob([(-0.25, 0.0), (-0.25, 0.5), (0.0, 0.68), (0.25, 0.5), (0.25, 0.0)], "#3A2A1E", w))
    doors = VGroup(blob([(-0.25, 0.0), (-0.25, 0.5), (0.0, 0.68), (0.25, 0.5), (0.25, 0.0)], WOOD, w),
                   line((0.0, 0.0), (0.0, 0.68), WOOD_D, w), *(line((-0.24, y), (0.24, y), IRON, w * 1.4) for y in (0.15, 0.4)))
    g.add(rect(-0.47, 0.82, 0.47, 0.9, tint(c, -0.1), w), doors)
    return g, (doors, (0.0, 0.0), "fold", 1.0)


def _fence(m, w):
    g = VGroup(*(line((-0.45, y), (0.45, y), WOOD, w * 2.4) for y in (0.12, 0.26)))
    for x in np.linspace(-0.42, 0.42, 6):
        g.add(poly([(x - 0.025, 0.0), (x + 0.025, 0.0), (x + 0.025, 0.32), (x, 0.36), (x - 0.025, 0.32)], "#C9A066", w))
    return g, None


def _signpost(m, w):
    g = VGroup(rect(-0.025, 0.0, 0.025, 0.7, WOOD, w),
               poly([(-0.02, 0.6), (0.3, 0.6), (0.36, 0.555), (0.3, 0.51), (-0.02, 0.51)], "#E2C27A", w),
               poly([(0.02, 0.45), (-0.28, 0.45), (-0.34, 0.405), (-0.28, 0.36), (0.02, 0.36)], "#E2C27A", w))
    if m.get("label"):
        g.add(letters(str(m["label"]), 0.15, 0.555, 0.05))
    return g, None


def _flagpole(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(line((0.0, 0.0), (0.0, 1.1), "#9AA3A9", w * 1.8), circ(0.0, 1.11, 0.015, GOLD, w * 0.5),
                  blob([(0.0, 1.08), (0.15, 1.1), (0.32, 1.06), (0.32, 0.86), (0.15, 0.9), (0.0, 0.88)], c, w)), None


def _cart(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    g = VGroup(line((0.2, 0.2), (0.62, 0.12), WOOD_D, w * 2.6), rect(-0.35, 0.2, 0.25, 0.36, c, w),
               *(line((x, 0.2), (x, 0.36), tint(c, -0.2), w * 0.6) for x in (-0.2, -0.05, 0.1)))
    wh, _ = _wheel({"color": WOOD_D}, w)
    wh.scale(0.75, about_point=np.array([0.0, 0.0, 0.0])).shift([-0.05, 0.0, 0])
    if m.get("load"):
        g.add_to_back(*(circ(x, 0.38, 0.06, "#D9C49A", w * 0.7) for x in (-0.25, -0.12, 0.02, 0.15)))
    g.add(wh)
    return g, None


def _boat(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(blob([(-0.45, 0.2), (-0.35, 0.05), (0.0, 0.0), (0.35, 0.05), (0.45, 0.2)], c, w),
                  stroke([(-0.42, 0.16), (0.42, 0.16)], tint(c, -0.25), w * 0.8),
                  line((0.25, 0.18), (0.55, 0.42), WOOD_D, w * 1.6), line((-0.1, 0.18), (-0.1, 0.65), WOOD_D, w * 1.6),
                  poly([(-0.08, 0.63), (-0.08, 0.24), (0.25, 0.26)], "#F3EEE4", w)), None


def _ship(m, w):
    c = col(m["color"]) if m.get("color") else WOOD_D
    g = VGroup(blob([(-0.6, 0.35), (-0.5, 0.1), (0.0, 0.0), (0.5, 0.08), (0.65, 0.38), (0.4, 0.3), (-0.4, 0.3)], c, w),
               stroke([(-0.52, 0.22), (0.58, 0.24)], GOLD_D, w * 1.2),
               *(circ(x, 0.17, 0.025, "#22201E", w * 0.5) for x in np.linspace(-0.3, 0.35, 5)),
               rect(-0.6, 0.3, -0.38, 0.45, tint(c, 0.15), w))
    for x, h in ((-0.15, 1.15), (0.25, 0.95)):
        g.add(line((x, 0.3), (x, h), "#5B4A3A", w * 2),
              blob([(x - 0.2, h - 0.12), (x + 0.2, h - 0.12), (x + 0.22, h - 0.4), (x, h - 0.35), (x - 0.22, h - 0.4)], "#F3EEE4", w),
              blob([(x - 0.17, h - 0.45), (x + 0.17, h - 0.45), (x + 0.19, h - 0.68), (x, h - 0.63), (x - 0.19, h - 0.68)], "#F3EEE4", w),
              poly([(x, h), (x + 0.12, h - 0.03), (x, h - 0.06)], col(m.get("flag") or RED), w * 0.6))
    g.add(line((0.25, 0.85), (0.72, 0.4), "#5B4A3A", w * 0.8), poly([(0.3, 0.8), (0.62, 0.48), (0.3, 0.48)], "#F3EEE4", w))
    return g, None


SHELF = {name[1:]: fn for name, fn in globals().items() if name.startswith("_") and callable(fn) and name[1:].isalpha()
         and name not in ("_annotations",)}
ALIASES = {"bag": "moneybag", "purse": "moneybag", "money": "moneybag", "gold": "coins", "treasure": "chest",
           "coinpile": "coins", "notes": "cash", "banknotes": "cash", "jewel": "gem", "diamond": "gem",
           "ruby": "gem", "tome": "book", "paper": "document", "contract": "document", "deed": "charter",
           "decree": "charter", "treaty": "charter", "envelope": "letter", "map": "oldmap", "pen": "quill",
           "throne_chair": "throne", "cupboard": "bookshelf", "shelf": "bookshelf", "grain": "sack", "matka": "pot",
           "amphora": "jar", "lamp": "diya", "fire": "campfire", "gun": "cannon", "plow": "plough",
           "spinningwheel": "charkha", "balance": "scales", "timer": "hourglass", "cup": "goblet", "idea": "lightbulb",
           "press": "printingpress", "castle": "tower", "fort": "tower", "door": "gate", "sign": "signpost",
           "flag": "flagpole", "wagon": "cart", "bullockcart": "cart", "cottage": "hut", "home": "house"}
NAMES = tuple(sorted(SHELF))


def known(name: str) -> str | None:
    n = str(name or "").lower().replace("-", "").replace("_", "")
    n = ALIASES.get(n, n)
    return n if n in SHELF else None


class Prop(VGroup):
    """A drawn thing; one with a lid opens and shuts (set_open), its lid turned or folded about its hinge."""

    def __init__(self, name: str, mods: dict, size: float):
        super().__init__()
        zoo.INK = col("ink")
        k = size / 1.8
        w = 2.0 * k
        self.name = known(name) or "crate"
        g, lid = SHELF[self.name](dict(mods), w)
        self.add(g)
        self.lid = None
        self.open_k = 0.0
        self._ref = VGroup(*(Dot([x, y, 0], radius=0.001).set_opacity(0) for x, y in ((0, 0), (0.1, 0), (0, 0.1))))
        self.add(self._ref)
        if lid is not None:
            self.lid, hinge, self.how, self.reach = lid
            self.hinge = np.array(hinge, dtype=float)
            self.lid_base = [(x, x.points[:, :2].copy()) for x in self.lid.family_members_with_points()]
        if mods.get("open"):
            self.set_open(1.0)

    def set_open(self, k: float) -> None:
        if self.lid is None:
            return
        self.open_k = k
        o, xr, yr = (d.get_center() for d in self._ref)
        ex, ey = (xr - o) / 0.1, (yr - o) / 0.1
        h = self.hinge
        if self.how == "swing":                 # turned back about its hinge
            a = self.reach * k
            M = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        elif self.how == "flip":                # folded up over its hinge (a letter's flap)
            M = np.array([[1.0, 0.0], [0.0, 1.0 - 2.0 * k]])
        else:                                   # doors folding away to the sides
            M = np.array([[max(0.04, 1.0 - k), 0.0], [0.0, 1.0]])
        for x, base in self.lid_base:
            q = (base - h) @ M.T + h
            x.points = o + np.outer(q[:, 0], ex) + np.outer(q[:, 1], ey)


def prop(name: str, mods: dict, size: float) -> Prop:
    size = size or 2.6
    p = Prop(name, mods, size)
    p.scale(size, about_point=np.array([0.0, 0.0, 0.0]))
    return p
