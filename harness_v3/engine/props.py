"""Things drawn with the same pen as the people: a ready shelf, so a shot needs no picture searched for or made.

    ent b prop moneybag [color C] [sign ₹] [open] [size H] at X,Y      (it stands on X,Y: its bottom middle there)

Drawn to the people's scale (size 2.6, a person's, by default: a chest beside a king is a chest's size); a bigger
size shows one alone (size 6-10). Those with a lid open and shut as it plays: `open X`, `shut X` (a chest shows its
gold; a letter its flap; a box, a door). Any of them can be carried, given, thrown, moved.

What is on the shelf, by section, and the other names each thing goes by: shelf.py (the index the prompts and the
asset step read).
"""

from __future__ import annotations

import math
import sys

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


def live(m, kind, anchor=None):
    """Marks a part that moves on its own: a flame (flicker), a flag (wave), sails (spin about `anchor`), smoke (puff),
    steam (steam), a clock's hand (tick about `anchor`). Prop.alive plays them."""
    m.live = (kind, anchor)
    return m


def wheel_of(m):
    """Marks a wheel (it turns as its vehicle is driven: Prop.roll)."""
    m.wheel = True
    return m


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
                  live(blob([(0.0, 0.21), (-0.02, 0.24), (0.0, 0.29), (0.02, 0.24)], "#F2C14E", w * 0.6), "flame"),
                  live(blob([(0.0, 0.215), (-0.008, 0.235), (0.0, 0.26), (0.008, 0.235)], "#E4572E", 0), "flame")), None


def _diya(m, w):
    return VGroup(blob([(-0.12, 0.05), (-0.06, 0.0), (0.06, 0.0), (0.12, 0.05), (0.16, 0.07), (0.0, 0.06)], "#C2552B", w),
                  *(Dot([x, 0.03, 0], radius=0.008, color="#F2C14E") for x in (-0.06, 0.0, 0.06)),
                  live(blob([(0.12, 0.07), (0.11, 0.11), (0.13, 0.17), (0.15, 0.11)], "#F2C14E", w * 0.6), "flame"),
                  live(blob([(0.13, 0.08), (0.125, 0.11), (0.13, 0.14), (0.137, 0.11)], "#E4572E", 0), "flame")), None


def _lantern(m, w):
    return VGroup(stroke(zoo.P._arc(0.0, 0.3, 0.04, 0, 180, 8), zoo.INK, w),
                  poly([(-0.07, 0.28), (0.07, 0.28), (0.0, 0.33)], "#3A3631", w),
                  rect(-0.06, 0.06, 0.06, 0.28, "#FBE7A1", w),
                  live(blob([(0.0, 0.1), (-0.025, 0.15), (0.0, 0.22), (0.025, 0.15)], "#F2A93B", 0), "flame"),
                  *(line((x, 0.06), (x, 0.28), "#3A3631", w * 1.2) for x in (-0.06, 0.0, 0.06)),
                  rect(-0.08, 0.0, 0.08, 0.06, "#3A3631", w)), None


def _campfire(m, w):
    return VGroup(*(poly([(x0, 0.0), (x0 + 0.03, 0.02), (x1 + 0.03, 0.08), (x1, 0.06)], WOOD_D, w) for x0, x1 in
                    ((-0.18, 0.12), (0.18, -0.12))),
                  live(blob([(-0.12, 0.04), (-0.1, 0.18), (-0.04, 0.14), (0.0, 0.32), (0.05, 0.15), (0.1, 0.22), (0.12, 0.04)],
                            "#E4572E", w), "flame"),
                  live(blob([(-0.06, 0.04), (-0.04, 0.14), (0.0, 0.22), (0.04, 0.12), (0.06, 0.04)], "#F2C14E", w * 0.5), "flame"),
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
    """A wooden plough: the long beam, two handles behind, the iron share in front cutting the earth, a small wheel."""
    g = VGroup(tube([(-0.42, 0.42), (-0.15, 0.24), (0.15, 0.12), (0.32, 0.1)], [0.05, 0.05, 0.045, 0.04], WOOD, w),
               tube([(-0.5, 0.5), (-0.28, 0.2), (-0.12, 0.06)], [0.035, 0.035, 0.03], WOOD_D, w),
               tube([(-0.38, 0.52), (-0.18, 0.22), (-0.05, 0.07)], [0.035, 0.035, 0.03], WOOD, w),
               line((-0.53, 0.5), (-0.47, 0.52), WOOD_D, w * 2.6), line((-0.41, 0.52), (-0.35, 0.54), WOOD_D, w * 2.6),
               tube([(0.0, 0.16), (0.04, 0.06)], [0.04, 0.035], WOOD_D, w),
               poly([(-0.06, 0.07), (0.12, 0.07), (0.2, 0.0), (-0.02, 0.0)], IRON, w),
               stroke([(-0.03, 0.035), (0.14, 0.035)], "#C9D0D4", w * 0.8),
               blob([(-0.2, 0.0), (0.3, 0.0), (0.25, 0.03), (-0.15, 0.03)], "#8C6E52", 0))  # turned earth
    wh, _ = _wheel({"color": WOOD_D}, w)
    wh.scale(0.45, about_point=np.array([0.0, 0.0, 0.0])).shift([0.3, 0.0, 0])
    g.add(wh)
    return g, None


def _wheel(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    g = VGroup(Circle(radius=0.2, stroke_color=zoo.INK, stroke_width=w * 4.4).move_to([0, 0.2, 0]),
               Circle(radius=0.2, stroke_color=c, stroke_width=w * 2.6).move_to([0, 0.2, 0]))
    for a in np.linspace(0, math.pi, 7)[:-1]:
        g.add(line((0.19 * math.cos(a), 0.2 + 0.19 * math.sin(a)), (-0.19 * math.cos(a), 0.2 - 0.19 * math.sin(a)), c, w * 1.6))
    g.add(circ(0.0, 0.2, 0.035, tint(c, -0.2), w))
    return wheel_of(g), None


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
          line((0.0, 1.04), (0.0, 1.22), WOOD, w * 1.4), live(poly([(0.0, 1.22), (0.16, 1.17), (0.0, 1.12)], col(m.get("flag") or RED), w * 0.7), "flag"))
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
                  live(blob([(0.0, 1.08), (0.15, 1.1), (0.32, 1.06), (0.32, 0.86), (0.15, 0.9), (0.0, 0.88)], c, w), "flag")), None


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


# -- money and trade (more) ------------------------------------------------------------------------------------------

def _piggybank(m, w):
    c = col(m["color"]) if m.get("color") else "#F2A7B8"
    return VGroup(*(rect(x, 0.0, x + 0.04, 0.06, tint(c, -0.15), w) for x in (-0.12, 0.06)),
                  ell(0.0, 0.14, 0.34, 0.22, c, w), ell(0.17, 0.14, 0.05, 0.07, tint(c, -0.1), w),
                  *(Dot([0.17, 0.14 + d, 0], radius=0.008, color=zoo.INK) for d in (-0.015, 0.015)),
                  poly([(0.06, 0.22), (0.1, 0.3), (0.12, 0.22)], c, w), Dot([0.09, 0.18, 0], radius=0.012, color=zoo.INK),
                  rect(-0.04, 0.245, 0.04, 0.255, "#3A3631", 0), stroke([(-0.17, 0.15), (-0.21, 0.18), (-0.19, 0.12)], c, w),
                  ell(0.0, 0.3, 0.07, 0.03, GOLD, w * 0.6)), None


def _wallet(m, w):
    c = col(m["color"]) if m.get("color") else "#6B4226"
    return VGroup(rect(-0.13, 0.0, 0.13, 0.15, "#7FB27F", w * 0.6).shift([0.02, 0.03, 0]),
                  rrect(-0.15, 0.0, 0.15, 0.16, 0.02, c, w), rrect(0.0, 0.05, 0.16, 0.11, 0.02, tint(c, -0.15), w),
                  Dot([0.12, 0.08, 0], radius=0.012, color=GOLD), stroke([(-0.13, 0.015), (0.13, 0.015)], tint(c, 0.25), w * 0.4)), None


def _card(m, w):
    c = col(m["color"]) if m.get("color") else "#2F3B8C"
    return VGroup(rrect(-0.15, 0.0, 0.15, 0.19, 0.02, c, w), rect(-0.15, 0.13, 0.15, 0.16, "#22201E", 0),
                  rrect(-0.12, 0.06, -0.06, 0.1, 0.01, GOLD, w * 0.6),
                  *(rect(-0.12 + i * 0.06, 0.025, -0.08 + i * 0.06, 0.04, "#F7F5F0", 0) for i in range(4))), None


def _receipt(m, w):
    pts = [(-0.08, 0.0)] + [(-0.08 + i * 0.02, 0.012 * (i % 2)) for i in range(1, 9)] + [(0.08, 0.36), (-0.08, 0.36)]
    return VGroup(poly(pts, "#F7F5F0", w), *(scribble(-0.06, 0.03, y, w * 0.4) for y in np.linspace(0.31, 0.1, 6)),
                  *(letters(str(10 * (i + 1)), 0.055, y, 0.02) for i, y in enumerate(np.linspace(0.31, 0.1, 6))),
                  line((-0.06, 0.07), (0.06, 0.07), zoo.INK, w * 0.6)), None


def _abacus(m, w):
    g = VGroup(rect(-0.2, 0.0, 0.2, 0.32, WOOD, w).set_fill(opacity=0).set_stroke(WOOD, w * 2.4),
               line((-0.2, 0.22), (0.2, 0.22), WOOD_D, w * 1.6))
    cols_ = ["#B83227", "#F2C14E", "#3E7CB1", "#5B8C3A"]
    for i, y in enumerate(np.linspace(0.04, 0.29, 6)):
        g.add(line((-0.19, y), (0.19, y), "#9AA3A9", w * 0.6))
        for j in range(4):
            x = (-0.16 + j * 0.04) if (i + j) % 3 else (0.06 + j * 0.03)
            g.add(ell(x, y, 0.034, 0.03, cols_[i % 4], w * 0.5))
    return g, None


def _safe(m, w):
    return VGroup(rrect(-0.2, 0.0, 0.2, 0.42, 0.02, "#5A5F63", w), rrect(-0.17, 0.04, 0.17, 0.38, 0.02, "#6E747A", w),
                  circ(0.0, 0.24, 0.07, "#9AA3A9", w), circ(0.0, 0.24, 0.02, "#3A3631", w * 0.6),
                  *(line((0.07 * math.cos(a), 0.24 + 0.07 * math.sin(a)), (0.085 * math.cos(a), 0.24 + 0.085 * math.sin(a)), zoo.INK, w * 0.6)
                    for a in np.linspace(0, 2 * math.pi, 13)[:-1]),
                  rect(0.1, 0.1, 0.13, 0.18, GOLD, w * 0.6), *(rect(x, -0.02, x + 0.05, 0.0, "#3A3631", w * 0.6) for x in (-0.18, 0.13))), None


def _stall(m, w):
    c = col(m["color"]) if m.get("color") else RED
    g = VGroup(*(line((x, 0.0), (x, 0.75), WOOD_D, w * 2) for x in (-0.38, 0.38)),
               rect(-0.42, 0.0, 0.42, 0.32, WOOD, w), *(line((-0.42, y), (0.42, y), WOOD_D, w * 0.6) for y in (0.1, 0.2)),
               rect(-0.44, 0.32, 0.44, 0.36, tint(WOOD, 0.1), w))
    for i in range(8):                          # a striped awning, scalloped
        x0 = -0.46 + i * 0.115
        g.add(poly([(x0, 0.82), (x0 + 0.115, 0.82), (x0 + 0.115, 0.68), (x0, 0.68)], c if i % 2 == 0 else "#F7F5F0", w * 0.7),
              blob(zoo.P._arc(x0 + 0.0575, 0.68, 0.0575, 180, 360, 8), c if i % 2 == 0 else "#F7F5F0", w * 0.7))
    for i, x in enumerate(np.linspace(-0.3, 0.3, 7)):
        g.add(circ(x, 0.4, 0.045, ["#D63B2F", "#F2C14E", "#7BB04B", "#E07B39"][i % 4], w * 0.6))
    return g, None


# -- office, learning and the modern world -----------------------------------------------------------------------

def _pencil(m, w):
    return VGroup(poly([(-0.25, 0.03), (0.15, 0.03), (0.15, 0.08), (-0.25, 0.08)], "#F2C14E", w),
                  poly([(0.15, 0.03), (0.25, 0.055), (0.15, 0.08)], "#E8C9A0", w), poly([(0.22, 0.048), (0.25, 0.055), (0.22, 0.062)], "#3A3631", 0),
                  rect(-0.3, 0.03, -0.25, 0.08, "#E07A8A", w), rect(-0.25, 0.03, -0.22, 0.08, "#B8BEC2", w * 0.7),
                  line((-0.22, 0.055), (0.15, 0.055), "#C9962B", w * 0.5)), None


def _notebook(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    return VGroup(rect(-0.12, 0.0, 0.14, 0.32, PAPER, w), rect(-0.13, 0.0, 0.13, 0.32, c, w),
                  rect(-0.08, 0.2, 0.08, 0.26, "#F7F5F0", w * 0.6),
                  *(circ(-0.13, y, 0.012, "#B8BEC2", w * 0.5) for y in np.linspace(0.03, 0.29, 8))), None


def _clipboard(m, w):
    return VGroup(rrect(-0.15, 0.0, 0.15, 0.4, 0.02, WOOD, w), rect(-0.12, 0.03, 0.12, 0.35, PAPER, w * 0.8),
                  rrect(-0.06, 0.34, 0.06, 0.41, 0.015, "#9AA3A9", w),
                  *(VGroup(rect(-0.1, y - 0.015, -0.07, y + 0.015, "#F7F5F0", w * 0.5), scribble(-0.05, 0.1, y, w * 0.4))
                    for y in np.linspace(0.29, 0.09, 5)),
                  *(stroke([(-0.1, y), (-0.088, y - 0.012), (-0.065, y + 0.02)], "#2E7D4E", w * 0.9) for y in np.linspace(0.29, 0.17, 3))), None


def _folder(m, w):
    c = col(m["color"]) if m.get("color") else "#E2B65A"
    return VGroup(poly([(-0.2, 0.0), (0.2, 0.0), (0.2, 0.26), (-0.04, 0.26), (-0.07, 0.29), (-0.2, 0.29)], tint(c, -0.12), w),
                  rect(-0.16, 0.05, 0.17, 0.27, PAPER, w * 0.6), poly([(-0.2, 0.0), (0.2, 0.0), (0.22, 0.22), (-0.18, 0.22)], c, w),
                  letters(str(m.get("label") or ""), 0.01, 0.11, 0.05) if m.get("label") else VGroup()), None


def _typewriter(m, w):
    g = VGroup(rect(-0.14, 0.2, 0.14, 0.36, PAPER, w * 0.7), *(scribble(-0.1, 0.1, y, w * 0.4) for y in (0.32, 0.29, 0.26)),
               rrect(-0.24, 0.17, 0.24, 0.23, 0.03, "#3A3631", w),
               poly([(-0.26, 0.0), (0.26, 0.0), (0.22, 0.18), (-0.22, 0.18)], "#2F3B4C", w))
    for r, y in enumerate((0.04, 0.08, 0.12)):
        for i in range(8 - r):
            g.add(circ(-0.16 + r * 0.02 + i * 0.045, y, 0.016, "#F7F5F0", w * 0.5))
    return g, None


def _laptop(m, w):
    return VGroup(poly([(-0.2, 0.04), (0.2, 0.04), (0.17, 0.3), (-0.17, 0.3)], "#9AA3A9", w).shift([0, 0, 0]),
                  rrect(-0.2, 0.06, 0.2, 0.32, 0.015, "#5A5F63", w), rect(-0.18, 0.08, 0.18, 0.3, "#9FC5DA", w * 0.6),
                  *(rect(-0.15, y, 0.05 + 0.08 * (i % 2), y + 0.015, "#F7F5F0", 0) for i, y in enumerate((0.24, 0.2, 0.16))),
                  poly([(-0.25, 0.0), (0.25, 0.0), (0.21, 0.06), (-0.21, 0.06)], "#B8BEC2", w),
                  rect(-0.05, 0.01, 0.05, 0.03, "#9AA3A9", w * 0.5)), None


def _computer(m, w):
    return VGroup(rect(-0.03, 0.04, 0.03, 0.12, "#B8BEC2", w), rect(-0.12, 0.0, 0.12, 0.04, "#B8BEC2", w),
                  rrect(-0.25, 0.12, 0.25, 0.46, 0.02, "#E9E2D3", w), rect(-0.22, 0.15, 0.22, 0.43, "#3E7CB1", w * 0.6),
                  *(rect(-0.18, y, -0.18 + ln, y + 0.02, "#F7F5F0", 0) for y, ln in ((0.37, 0.25), (0.32, 0.18), (0.27, 0.3))),
                  rect(-0.18, 0.18, -0.05, 0.24, "#F2C14E", 0)), None


def _phone(m, w):
    c = col(m["color"]) if m.get("color") else "#2B2826"
    return VGroup(rrect(-0.08, 0.0, 0.08, 0.32, 0.025, c, w), rrect(-0.068, 0.03, 0.068, 0.29, 0.012, "#9FC5DA", w * 0.5),
                  *(rrect(-0.05 + (i % 3) * 0.035, 0.2 - (i // 3) * 0.04, -0.025 + (i % 3) * 0.035, 0.225 - (i // 3) * 0.04, 0.005,
                          ["#F2C14E", "#E4572E", "#5B8C3A", "#3E7CB1", "#D46A9A", "#F7F5F0"][i], w * 0.3) for i in range(6)),
                  rect(-0.02, 0.3, 0.02, 0.308, "#5A5F63", 0)), None


def _oldphone(m, w):
    c = col(m["color"]) if m.get("color") else "#22201E"
    return VGroup(poly([(-0.16, 0.0), (0.16, 0.0), (0.12, 0.16), (-0.12, 0.16)], c, w), circ(0.0, 0.08, 0.06, "#F3EEE4", w * 0.7),
                  *(Dot([0.04 * math.cos(a), 0.08 + 0.04 * math.sin(a), 0], radius=0.008, color=c) for a in np.linspace(0, 2 * math.pi, 9)[:-1]),
                  tube([(-0.17, 0.2), (0.0, 0.25), (0.17, 0.2)], [0.06, 0.04, 0.06], c, w)), None


def _radio(m, w):
    c = col(m["color"]) if m.get("color") else "#8C5A3C"
    return VGroup(rrect(-0.22, 0.0, 0.22, 0.26, 0.05, c, w), rrect(-0.19, 0.04, 0.02, 0.22, 0.03, "#E9D5A8", w * 0.7),
                  *(line((-0.17, y), (0.0, y), tint("#E9D5A8", -0.3), w * 0.6) for y in np.linspace(0.07, 0.19, 6)),
                  circ(0.12, 0.17, 0.035, "#F3EEE4", w * 0.7), circ(0.12, 0.08, 0.025, "#F3EEE4", w * 0.7),
                  line((0.1, 0.26), (0.2, 0.42), "#9AA3A9", w)), None


def _tv(m, w):
    return VGroup(*(line((x, 0.04), (x * 1.3, -0.0), "#3A3631", w * 1.6) for x in (-0.12, 0.12)),
                  rrect(-0.26, 0.04, 0.26, 0.38, 0.04, "#8C5A3C", w), rrect(-0.22, 0.08, 0.1, 0.34, 0.04, "#9FB5B0", w * 0.8),
                  circ(0.17, 0.27, 0.03, "#F3EEE4", w * 0.6), circ(0.17, 0.17, 0.03, "#F3EEE4", w * 0.6),
                  line((-0.05, 0.38), (-0.15, 0.5), "#9AA3A9", w), line((-0.05, 0.38), (0.06, 0.5), "#9AA3A9", w)), None


def _camera(m, w):
    return VGroup(rrect(-0.18, 0.0, 0.18, 0.18, 0.03, "#3A3631", w), rect(-0.1, 0.18, -0.02, 0.21, "#3A3631", w),
                  circ(0.02, 0.09, 0.07, "#5A5F63", w), circ(0.02, 0.09, 0.045, "#3E7CB1", w * 0.7),
                  circ(0.04, 0.11, 0.012, "#FFFFFF", 0), rect(0.1, 0.13, 0.15, 0.16, "#F7F5F0", w * 0.5)), None


def _microphone(m, w):
    return VGroup(ell(0.0, 0.0, 0.2, 0.04, "#3A3631", w), line((0.0, 0.0), (0.0, 0.35), "#5A5F63", w * 2),
                  rrect(-0.05, 0.33, 0.05, 0.47, 0.05, "#9AA3A9", w),
                  *(line((-0.045, y), (0.045, y), "#5A5F63", w * 0.5) for y in (0.37, 0.4, 0.43))), None


def _megaphone(m, w):
    return VGroup(poly([(-0.18, 0.1), (-0.05, 0.12), (0.18, 0.22), (0.18, 0.0), (-0.05, 0.08)], "#E4572E", w),
                  ell(0.18, 0.11, 0.05, 0.22, "#F7F5F0", w), rect(-0.22, 0.08, -0.17, 0.14, "#3A3631", w),
                  rect(-0.1, -0.02, -0.07, 0.09, "#3A3631", w * 0.8)), None


def _ballotbox(m, w):
    return VGroup(rect(-0.18, 0.0, 0.18, 0.28, "#3E7CB1", w), rect(-0.1, 0.27, 0.1, 0.29, "#22201E", 0),
                  rect(-0.04, 0.24, 0.05, 0.4, "#F7F5F0", w * 0.7).rotate(0.1),
                  stroke([(-0.02, 0.33), (0.0, 0.31), (0.03, 0.36)], "#2E7D4E", w),
                  letters(str(m.get("label") or "VOTE"), 0.0, 0.12, 0.06, "#F7F5F0")), None


def _clock(m, w):
    return VGroup(circ(0.0, 0.2, 0.2, "#8C5A3C", w), circ(0.0, 0.2, 0.16, "#F7F3E8", w * 0.7),
                  *(line((0.13 * math.cos(a), 0.2 + 0.13 * math.sin(a)), (0.15 * math.cos(a), 0.2 + 0.15 * math.sin(a)), zoo.INK, w * 0.8)
                    for a in np.linspace(0, 2 * math.pi, 13)[:-1]),
                  live(line((0.0, 0.2), (0.0, 0.31), zoo.INK, w * 1.4), "tick", (0.0, 0.2)), line((0.0, 0.2), (0.07, 0.17), zoo.INK, w * 1.8),
                  circ(0.0, 0.2, 0.012, RED, 0)), None


def _magnifier(m, w):
    return VGroup(line((0.08, 0.12), (0.28, -0.0), WOOD_D, w * 4), circ(-0.03, 0.2, 0.13, "#9FC5DA", w * 1.2).set_fill(opacity=0.45),
                  Circle(radius=0.13, stroke_color="#C9962B", stroke_width=w * 2.4).move_to([-0.03, 0.2, 0]),
                  stroke(zoo.P._arc(-0.03, 0.2, 0.09, 110, 160, 6), "#FFFFFF", w)), None


def _briefcase(m, w):
    c = col(m["color"]) if m.get("color") else "#6B4226"
    return VGroup(stroke(zoo.P._arc(0.0, 0.24, 0.06, 0, 180, 8), "#3A2A1E", w * 2), rrect(-0.2, 0.0, 0.2, 0.25, 0.025, c, w),
                  line((-0.2, 0.15), (0.2, 0.15), tint(c, -0.25), w * 0.8),
                  *(rect(x - 0.02, 0.13, x + 0.02, 0.17, GOLD, w * 0.5) for x in (-0.12, 0.12))), None


def _stamp(m, w):
    return VGroup(rect(-0.1, 0.0, 0.1, 0.05, "#B83227", w), rect(-0.06, 0.05, 0.06, 0.08, "#3A3631", w * 0.7),
                  line((0.0, 0.08), (0.0, 0.2), WOOD, w * 3), circ(0.0, 0.23, 0.05, WOOD_D, w)), None


def _medal(m, w):
    c = col(m["color"]) if m.get("color") else GOLD
    return VGroup(poly([(-0.07, 0.42), (0.0, 0.2), (0.03, 0.22), (-0.03, 0.42)], "#2F3B8C", w),
                  poly([(0.07, 0.42), (0.0, 0.2), (-0.03, 0.22), (0.03, 0.42)], RED, w),
                  circ(0.0, 0.12, 0.1, c, w), circ(0.0, 0.12, 0.07, tint(c, 0.2), w * 0.5),
                  poly([(0.0, 0.17), (0.015, 0.13), (0.05, 0.13), (0.02, 0.105), (0.03, 0.065), (0.0, 0.09), (-0.03, 0.065),
                        (-0.02, 0.105), (-0.05, 0.13), (-0.015, 0.13)], tint(c, -0.2), 0)), None


def _trophy(m, w):
    return VGroup(rect(-0.12, 0.0, 0.12, 0.06, WOOD_D, w), rect(-0.03, 0.06, 0.03, 0.14, GOLD_D, w),
                  blob([(-0.13, 0.36), (-0.1, 0.2), (0.0, 0.14), (0.1, 0.2), (0.13, 0.36)], GOLD, w),
                  *(stroke(zoo.P._arc(s * 0.13, 0.28, 0.06, 90 if s > 0 else 90, -90 if s > 0 else 270, 8), GOLD_D, w * 2) for s in (-1, 1)),
                  stroke([(-0.06, 0.32), (-0.05, 0.22)], "#FBE3A0", w * 1.5)), None


# -- science and industry --------------------------------------------------------------------------------------

def _flask(m, w):
    c = col(m["color"]) if m.get("color") else "#5BB06B"
    return VGroup(poly([(-0.04, 0.34), (0.04, 0.34), (0.04, 0.22), (0.15, 0.02), (0.13, 0.0), (-0.13, 0.0), (-0.15, 0.02), (-0.04, 0.22)],
                       "#E8F1F4", w),
                  poly([(-0.1, 0.09), (0.1, 0.09), (0.14, 0.02), (0.13, 0.005), (-0.13, 0.005), (-0.14, 0.02)], c, 0),
                  *(circ(x, y, r, tint(c, 0.4), w * 0.4) for x, y, r in ((0.0, 0.14, 0.015), (0.02, 0.2, 0.01), (-0.01, 0.27, 0.008))),
                  rect(-0.05, 0.33, 0.05, 0.36, "#C9C2B2", w * 0.7)), None


def _testtube(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    g = VGroup(rect(-0.2, 0.0, 0.2, 0.04, WOOD, w), rect(-0.2, 0.16, 0.2, 0.2, WOOD, w))
    for x, cc in ((-0.12, c), (0.0, "#E4572E"), (0.12, "#5BB06B")):
        g.add(rrect(x - 0.03, 0.04, x + 0.03, 0.34, 0.03, "#E8F1F4", w * 0.8), rrect(x - 0.026, 0.045, x + 0.026, 0.14, 0.026, cc, 0))
    return g, None


def _microscope(m, w):
    return VGroup(rrect(-0.15, 0.0, 0.15, 0.05, 0.02, "#2F3B4C", w), tube([(0.06, 0.05), (0.1, 0.2), (0.04, 0.34)], [0.06, 0.06, 0.05], "#2F3B4C", w),
                  rect(-0.08, 0.14, 0.06, 0.16, "#5A5F63", w), tube([(-0.06, 0.18), (-0.02, 0.36), (0.0, 0.44)], [0.06, 0.055, 0.04], "#E9E2D3", w),
                  rect(-0.025, 0.43, 0.03, 0.48, "#2F3B4C", w), rect(-0.08, 0.12, -0.02, 0.18, "#5A5F63", w * 0.7)), None


def _magnet(m, w):
    return VGroup(tube([(-0.1, 0.0), (-0.1, 0.2), (0.0, 0.3), (0.1, 0.2), (0.1, 0.0)], [0.08] * 5, RED, w),
                  rect(-0.14, 0.0, -0.06, 0.06, "#C9D0D4", w), rect(0.06, 0.0, 0.14, 0.06, "#C9D0D4", w)), None


def _battery(m, w):
    return VGroup(rrect(-0.08, 0.0, 0.08, 0.34, 0.02, "#2B2826", w), rrect(-0.08, 0.2, 0.08, 0.34, 0.02, GOLD_D, w),
                  rect(-0.03, 0.34, 0.03, 0.37, "#9AA3A9", w), letters("+", 0.0, 0.27, 0.05, "#2B2826")), None


def _gear(m, w):
    c = col(m["color"]) if m.get("color") else "#8E969C"
    pts = []
    for i in range(48):
        a = 2 * math.pi * i / 48
        r = 0.2 if (i // 3) % 2 == 0 else 0.16
        pts.append((r * math.cos(a), 0.2 + r * math.sin(a)))
    return VGroup(poly(pts, c, w), circ(0.0, 0.2, 0.06, tint(c, 0.3), w)), None


def _rocket(m, w):
    return VGroup(blob([(-0.07, 0.15), (-0.07, 0.55), (0.0, 0.72), (0.07, 0.55), (0.07, 0.15)], "#F3EEE4", w),
                  poly([(-0.07, 0.15), (-0.15, 0.05), (-0.07, 0.3)], RED, w), poly([(0.07, 0.15), (0.15, 0.05), (0.07, 0.3)], RED, w),
                  blob([(-0.05, 0.6), (0.0, 0.72), (0.05, 0.6)], RED, w * 0.8), circ(0.0, 0.45, 0.035, "#9FC5DA", w),
                  blob([(-0.05, 0.15), (0.0, -0.05), (0.05, 0.15)], "#F2A93B", w * 0.6), blob([(-0.025, 0.15), (0.0, 0.03), (0.025, 0.15)], "#F7F3E8", 0)), None


def _satellite(m, w):
    g = VGroup(rect(-0.07, 0.15, 0.07, 0.3, GOLD, w), circ(0.0, 0.36, 0.04, "#F7F5F0", w), line((0.0, 0.3), (0.0, 0.33), zoo.INK, w))
    for s in (-1, 1):
        g.add(line((s * 0.07, 0.225), (s * 0.12, 0.225), zoo.INK, w), rect(min(s * 0.12, s * 0.36), 0.18, max(s * 0.12, s * 0.36), 0.27, "#2F5E9E", w),
              *(line((s * x, 0.18), (s * x, 0.27), "#9FC5DA", w * 0.5) for x in (0.18, 0.24, 0.3)))
    return g, None


def _solarpanel(m, w):
    g = VGroup(line((0.0, 0.0), (0.0, 0.18), "#9AA3A9", w * 2), poly([(-0.3, 0.15), (0.26, 0.15), (0.3, 0.42), (-0.26, 0.42)], "#2F5E9E", w))
    for t in (0.33, 0.66):
        g.add(line((-0.3 + 0.56 * t, 0.15), (-0.26 + 0.56 * t, 0.42), "#9FC5DA", w * 0.5))
    g.add(line((-0.28, 0.285), (0.28, 0.285), "#9FC5DA", w * 0.5))
    return g, None


def _windmill(m, w):
    g = VGroup(poly([(-0.16, 0.0), (0.16, 0.0), (0.09, 0.7), (-0.09, 0.7)], "#E8D5B5", w), blob([(-0.11, 0.7), (0.0, 0.82), (0.11, 0.7)], "#B5543C", w),
               blob([(-0.04, 0.0), (-0.04, 0.12), (0.0, 0.16), (0.04, 0.12), (0.04, 0.0)], WOOD_D, w))
    for a in (45, 135, 225, 315):
        r = math.radians(a)
        ca, sa = math.cos(r), math.sin(r)
        g.add(live(poly([(0.03 * -sa, 0.72 + 0.03 * ca), (0.42 * ca - 0.05 * sa, 0.72 + 0.42 * sa + 0.05 * ca),
                    (0.42 * ca + 0.05 * sa, 0.72 + 0.42 * sa - 0.05 * ca), (0.03 * sa, 0.72 - 0.03 * ca)], "#F3EEE4", w * 0.8),
                   "spin", (0.0, 0.72)))
    g.add(circ(0.0, 0.72, 0.035, WOOD_D, w))
    return g, None


def _factory(m, w):
    g = VGroup(rect(0.22, 0.0, 0.34, 0.95, "#8E5A3C", w), *(rect(0.22, y, 0.34, y + 0.04, "#F7F5F0", 0) for y in (0.8, 0.86)),
               poly([(-0.5, 0.0), (0.3, 0.0), (0.3, 0.4), (0.1, 0.55), (0.1, 0.4), (-0.1, 0.55), (-0.1, 0.4), (-0.3, 0.55), (-0.3, 0.4),
                     (-0.5, 0.55)], "#B5643C", w),
               rect(-0.05, 0.0, 0.08, 0.2, "#4A3424", w))
    for x in (-0.4, -0.22, 0.15):
        g.add(rect(x, 0.22, x + 0.1, 0.32, "#F2C14E", w * 0.7))
    if not m.get("plain"):                       # smoke
        g.add(*(live(circ(0.3 + i * 0.07, 1.02 + i * 0.08, 0.05 + i * 0.015, "#B9B2A4", w * 0.5), "puff") for i in range(3)))
    return g, None


def _oilwell(m, w):
    return VGroup(poly([(-0.2, 0.0), (0.2, 0.0), (0.0, 0.8)], "#FFFFFF", w).set_fill(opacity=0).set_stroke("#5A5F63", w * 1.6),
                  *(line((-0.2 + 0.2 * t, 0.8 * t), (0.2 - 0.2 * t, 0.8 * t), "#5A5F63", w) for t in (0.25, 0.5, 0.75)),
                  rect(-0.25, 0.0, 0.25, 0.04, "#3A3631", w), blob([(0.0, 0.8), (-0.05, 0.9), (0.0, 1.0), (0.05, 0.9)], "#22201E", w * 0.6)), None


# -- food and the table ------------------------------------------------------------------------------------------

def _bread(m, w):
    return VGroup(blob([(-0.2, 0.02), (-0.2, 0.1), (-0.1, 0.16), (0.1, 0.16), (0.2, 0.1), (0.2, 0.02), (0.0, 0.0)], "#D9A15A", w),
                  *(stroke([(x - 0.03, 0.07), (x + 0.03, 0.13)], "#A9702E", w) for x in (-0.1, 0.0, 0.1))), None


def _apple(m, w):
    c = col(m["color"]) if m.get("color") else "#D63B2F"
    return VGroup(blob([(0.0, 0.17), (-0.09, 0.18), (-0.12, 0.08), (-0.06, 0.0), (0.0, 0.02), (0.06, 0.0), (0.12, 0.08), (0.09, 0.18)], c, w),
                  line((0.0, 0.17), (0.01, 0.23), WOOD_D, w * 1.4), blob([(0.01, 0.2), (0.07, 0.24), (0.08, 0.2)], "#5B8C3A", w * 0.6),
                  stroke([(-0.07, 0.13), (-0.08, 0.08)], "#FFFFFF", w)), None


def _mango(m, w):
    return VGroup(blob([(0.0, 0.0), (-0.09, 0.06), (-0.1, 0.16), (-0.03, 0.22), (0.06, 0.2), (0.1, 0.1)], "#F2A93B", w),
                  fill_only([(0.06, 0.18), (0.09, 0.1), (0.03, 0.04), (0.02, 0.12)], "#E4572E", 0.5),
                  blob([(-0.03, 0.22), (0.02, 0.27), (0.06, 0.24)], "#5B8C3A", w * 0.6)), None


def _banana(m, w):
    return VGroup(*(tube([(-0.18, 0.12 + d), (0.0, 0.0 + d), (0.18, 0.12 + d)], [0.03, 0.07, 0.03], "#F2D04E", w) for d in (0.05, 0.0)),
                  line((-0.18, 0.17), (-0.22, 0.2), WOOD_D, w * 1.6)), None


def _coconut(m, w):
    return VGroup(circ(0.0, 0.12, 0.12, "#7A5634", w), *(Dot([x, 0.17, 0], radius=0.012, color="#3A2A1E") for x in (-0.03, 0.0, 0.03)),
                  stroke([(-0.08, 0.05), (-0.04, 0.2)], "#5A3E25", w * 0.6)), None


def _wheat(m, w):
    g = VGroup()
    for a in np.linspace(-0.3, 0.3, 5):
        x1, y1 = 0.45 * math.sin(a), 0.45 * math.cos(a)
        g.add(line((0.0, 0.0), (x1, y1), "#C9A050", w * 1.2))
        for k in range(4):
            t = 0.7 + k * 0.08
            g.add(ell(x1 * t, y1 * t, 0.03, 0.05, "#E2C27A", w * 0.5).rotate(-a))
    g.add(stroke([(-0.06, 0.12), (0.06, 0.12)], "#B83227", w * 2.2))
    return g, None


def _bowl(m, w):
    fill = str(m.get("of") or "rice")
    top = {"rice": "#F7F5F0", "dal": "#E2B65A", "soup": "#C2552B", "fruit": "#D63B2F"}.get(fill, "#F7F5F0")
    g = VGroup(blob([(-0.17, 0.1), (-0.18, 0.13), (0.0, 0.17), (0.18, 0.13), (0.17, 0.1)], top, w * 0.7))
    if fill == "rice":
        g.add(*(ell(x, y, 0.02, 0.01, "#FFFFFF", w * 0.3) for x, y in ((-0.06, 0.14), (0.04, 0.15), (0.0, 0.13), (0.09, 0.13))))
    g.add(blob([(-0.18, 0.11), (-0.12, 0.02), (0.0, 0.0), (0.12, 0.02), (0.18, 0.11)], col(m.get("color") or "#3E7CB1"), w),
          stroke([(-0.12, 0.07), (0.12, 0.07)], "#F7F5F0", w * 0.8))
    return g, None


def _thali(m, w):
    g = VGroup(ell(0.0, 0.05, 0.56, 0.12, "#C9D0D4", w), ell(0.0, 0.055, 0.48, 0.09, "#E3E7EA", w * 0.6))
    for x, c in ((-0.17, "#E2B65A"), (-0.06, "#5B8C3A"), (0.05, "#C2552B"), (0.16, "#F7F5F0")):
        g.add(ell(x, 0.075, 0.09, 0.04, "#B8BEC2", w * 0.6), ell(x, 0.08, 0.07, 0.025, c, 0))
    g.add(ell(0.0, 0.03, 0.14, 0.03, "#E8C27A", w * 0.6))
    return g, None


def _teacup(m, w):
    return VGroup(ell(0.0, 0.01, 0.28, 0.04, "#F7F5F0", w), blob([(-0.11, 0.16), (-0.09, 0.05), (0.0, 0.02), (0.09, 0.05), (0.11, 0.16)], "#F7F5F0", w),
                  ell(0.0, 0.16, 0.22, 0.04, "#A0633A", w * 0.7), stroke(zoo.P._arc(0.12, 0.1, 0.04, 90, -90, 8), "#F7F5F0", w * 2.2),
                  live(stroke([(-0.03, 0.19), (-0.05, 0.24), (-0.02, 0.29)], "#C9C2B2", w), "steam"),
                  live(stroke([(0.03, 0.19), (0.01, 0.25), (0.04, 0.3)], "#C9C2B2", w), "steam"),
                  stroke([(-0.1, 0.1), (0.1, 0.1)], "#3E7CB1", w * 0.8)), None


def _kulhad(m, w):
    return VGroup(poly([(-0.07, 0.0), (0.07, 0.0), (0.09, 0.17), (-0.09, 0.17)], "#B5643C", w), ell(0.0, 0.17, 0.18, 0.035, "#C98A55", w * 0.7),
                  live(stroke([(-0.02, 0.2), (-0.04, 0.25), (-0.01, 0.3)], "#C9C2B2", w), "steam")), None


def _fish(m, w):
    c = col(m["color"]) if m.get("color") else "#8EA3B5"
    return VGroup(blob([(-0.18, 0.08), (-0.05, 0.15), (0.12, 0.12), (0.18, 0.08), (0.12, 0.03), (-0.05, 0.01)], c, w),
                  poly([(-0.16, 0.08), (-0.26, 0.15), (-0.24, 0.08), (-0.26, 0.01)], tint(c, -0.15), w),
                  circ(0.12, 0.09, 0.015, "#FFFFFF", w * 0.4), stroke([(0.06, 0.13), (0.07, 0.03)], tint(c, -0.25), w * 0.7)), None


def _milkcan(m, w):
    return VGroup(poly([(-0.1, 0.0), (0.1, 0.0), (0.1, 0.24), (0.05, 0.3), (-0.05, 0.3), (-0.1, 0.24)], "#B8BEC2", w),
                  rect(-0.06, 0.3, 0.06, 0.34, "#9AA3A9", w), *(stroke([(-0.1, y), (0.1, y)], "#8E969C", w * 1.4) for y in (0.06, 0.2)),
                  stroke(zoo.P._arc(-0.1, 0.26, 0.03, 90, 270, 6), "#9AA3A9", w * 1.6)), None


# -- care --------------------------------------------------------------------------------------------------------

def _medkit(m, w):
    return VGroup(stroke(zoo.P._arc(0.0, 0.22, 0.05, 0, 180, 8), "#3A3631", w * 2), rrect(-0.18, 0.0, 0.18, 0.23, 0.025, "#F7F5F0", w),
                  rect(-0.025, 0.05, 0.025, 0.18, RED, 0), rect(-0.065, 0.09, 0.065, 0.14, RED, 0)), None


def _pills(m, w):
    return VGroup(rrect(-0.06, 0.0, 0.06, 0.2, 0.015, "#E9A23B", w).set_fill(opacity=0.85), rrect(-0.07, 0.2, 0.07, 0.26, 0.015, "#F7F5F0", w),
                  rect(-0.05, 0.07, 0.05, 0.13, "#F7F5F0", w * 0.5),
                  *(rrect(x, 0.0, x + 0.07, 0.03, 0.015, c, w * 0.5) for x, c in ((0.09, "#E07A8A"), (0.14, "#9FC5DA")))), None


def _syringe(m, w):
    return VGroup(rect(-0.16, 0.04, 0.1, 0.1, "#E8F1F4", w), rect(-0.1, 0.045, 0.06, 0.095, "#9FC5DA", 0),
                  rect(-0.22, 0.06, -0.16, 0.08, "#9AA3A9", w * 0.7), rect(-0.24, 0.02, -0.22, 0.12, "#9AA3A9", w * 0.7),
                  line((0.1, 0.07), (0.24, 0.07), "#9AA3A9", w * 0.8), rect(-0.18, 0.03, -0.16, 0.11, "#5A5F63", w * 0.5)), None


# -- getting about -----------------------------------------------------------------------------------------------

def wheelset(xs, r, w, c="#2B2826"):
    return [wheel_of(VGroup(circ(x, r, r, c, w), circ(x, r, r * 0.45, "#B8BEC2", w * 0.6),
                            line((x - r * 0.42, r), (x + r * 0.42, r), "#6E747A", w * 0.8),
                            line((x, r * 0.58), (x, r * 1.42), "#6E747A", w * 0.8))) for x in xs]


def _bicycle(m, w):
    c = col(m["color"]) if m.get("color") else RED
    g = VGroup(*(wheel_of(VGroup(Circle(radius=0.14, stroke_color=zoo.INK, stroke_width=w * 1.6).move_to([x, 0.14, 0]),
                                 *(line((x + 0.13 * math.cos(t), 0.14 + 0.13 * math.sin(t)),
                                        (x - 0.13 * math.cos(t), 0.14 - 0.13 * math.sin(t)), "#9AA3A9", w * 0.5)
                                   for t in np.linspace(0, math.pi, 4)[:-1])))
                 for x in (-0.2, 0.22)))
    g.add(*(line(a, b, c, w * 2) for a, b in (((-0.2, 0.14), (0.0, 0.14)), ((0.0, 0.14), (0.12, 0.32)), ((-0.08, 0.3), (0.12, 0.32)),
                                             ((-0.2, 0.14), (-0.08, 0.3)), ((0.0, 0.14), (-0.08, 0.3)), ((0.12, 0.32), (0.22, 0.14)))),
          line((-0.1, 0.34), (-0.04, 0.34), "#3A3631", w * 2.6), line((0.12, 0.32), (0.11, 0.38), c, w * 1.6),
          line((0.07, 0.38), (0.15, 0.38), "#3A3631", w * 2))
    crank = VGroup(circ(0.0, 0.14, 0.03, "#9AA3A9", w * 0.6),       # the chainring and pedals (they turn as it goes)
                   line((-0.055, 0.14), (0.055, 0.14), "#3A3631", w * 1.4),
                   rect(-0.075, 0.13, -0.045, 0.15, "#3A3631", w * 0.5), rect(0.045, 0.13, 0.075, 0.15, "#3A3631", w * 0.5))
    crank.crank = True
    g.add(crank)
    return g, None


def _car(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    g = VGroup(blob([(-0.45, 0.08), (-0.45, 0.2), (-0.25, 0.24), (-0.15, 0.36), (0.15, 0.36), (0.27, 0.24), (0.45, 0.2), (0.45, 0.08)], c, w),
               poly([(-0.12, 0.25), (-0.12, 0.33), (0.0, 0.33), (0.0, 0.25)], "#9FC5DA", w * 0.6),
               poly([(0.03, 0.25), (0.03, 0.33), (0.13, 0.33), (0.22, 0.25)], "#9FC5DA", w * 0.6),
               rect(0.4, 0.14, 0.45, 0.18, "#F2C14E", w * 0.5), line((-0.02, 0.2), (0.06, 0.2), tint(c, -0.3), w))
    g.add(*wheelset((-0.27, 0.27), 0.08, w))
    return g, None


def _bus(m, w):
    c = col(m["color"]) if m.get("color") else "#E2A93B"
    g = VGroup(rrect(-0.6, 0.06, 0.6, 0.55, 0.06, c, w))
    for x in np.linspace(-0.5, 0.3, 5):
        g.add(rect(x, 0.3, x + 0.14, 0.47, "#9FC5DA", w * 0.6))
    g.add(rect(0.42, 0.1, 0.55, 0.47, "#9FC5DA", w * 0.6), line((-0.6, 0.22), (0.6, 0.22), tint(c, -0.3), w * 1.4),
          *wheelset((-0.38, 0.35), 0.09, w))
    return g, None


def _truck(m, w):
    c = col(m["color"]) if m.get("color") else "#5B8C3A"
    g = VGroup(rect(-0.55, 0.12, 0.15, 0.52, tint(c, 0.1), w), *(line((x, 0.14), (x, 0.5), tint(c, -0.2), w * 0.6) for x in np.linspace(-0.45, 0.05, 5)),
               blob([(0.15, 0.1), (0.15, 0.42), (0.36, 0.42), (0.48, 0.25), (0.5, 0.1)], c, w),
               poly([(0.2, 0.26), (0.2, 0.38), (0.33, 0.38), (0.42, 0.26)], "#9FC5DA", w * 0.6))
    g.add(*wheelset((-0.38, -0.15, 0.36), 0.09, w))
    return g, None


def _train(m, w):
    c = col(m["color"]) if m.get("color") else "#2F3B4C"
    g = VGroup(rect(-0.55, 0.12, 0.05, 0.6, c, w), rect(-0.48, 0.38, -0.2, 0.52, "#F2C14E", w * 0.7),
               rrect(0.05, 0.12, 0.5, 0.36, 0.1, tint(c, 0.15), w), rect(0.32, 0.36, 0.4, 0.56, "#22201E", w),
               poly([(0.28, 0.56), (0.44, 0.56), (0.42, 0.6), (0.3, 0.6)], "#22201E", w),
               poly([(0.5, 0.12), (0.62, 0.02), (0.5, 0.02)], RED, w), rect(-0.6, 0.6, 0.1, 0.65, RED, w))
    g.add(*(live(circ(0.38 + i * 0.07, 0.66 + i * 0.07, 0.04 + i * 0.012, "#C9C2B2", w * 0.5), "puff") for i in range(3)))
    g.add(*wheelset((-0.42, -0.15, 0.15, 0.38), 0.1, w, RED))
    g.add(line((-0.42, 0.1), (0.38, 0.1), "#9AA3A9", w * 1.6))
    return g, None


def _rickshaw(m, w):
    """A cycle rickshaw: its seat and folded hood behind, the rider's saddle in front (`ride` a person on it)."""
    c = col(m["color"]) if m.get("color") else "#2E7D4E"
    g = VGroup()
    for x, r in ((-0.2, 0.16), (0.36, 0.13)):
        wh, _ = _wheel({"color": "#3A3631"}, w)
        wh.scale(r / 0.2, about_point=np.array([0.0, 0.0, 0.0])).shift([x, 0.0, 0])
        g.add(wh)
    g.add(line((-0.2, 0.16), (0.36, 0.13), "#3A3631", w * 1.6), line((0.1, 0.15), (0.2, 0.42), "#3A3631", w * 1.6),
          line((0.36, 0.13), (0.32, 0.5), "#3A3631", w * 1.6), line((0.27, 0.5), (0.38, 0.5), "#3A3631", w * 2.2),
          rect(0.15, 0.42, 0.25, 0.45, "#3A3631", w),
          rect(-0.36, 0.3, 0.02, 0.36, RED, w), rect(-0.36, 0.36, -0.3, 0.52, RED, w),
          blob([(-0.4, 0.32), (-0.42, 0.55), (-0.3, 0.7), (-0.05, 0.72), (0.05, 0.6), (-0.1, 0.62), (-0.3, 0.55), (-0.32, 0.32)], c, w),
          *(stroke([(-0.38 + i * 0.08, 0.38 + i * 0.07), (-0.25 + i * 0.06, 0.66)], tint(c, -0.25), w * 0.6) for i in range(3)))
    return g, None


def _autorickshaw(m, w):
    g = VGroup(blob([(-0.38, 0.1), (-0.38, 0.42), (0.18, 0.42), (0.3, 0.32), (0.36, 0.18), (0.36, 0.1)], "#F2C14E", w),
               poly([(-0.4, 0.42), (-0.4, 0.62), (0.15, 0.62), (0.22, 0.42)], "#2B2826", w),
               poly([(0.05, 0.42), (0.15, 0.6), (0.2, 0.42)], "#9FC5DA", w * 0.6),
               poly([(-0.36, 0.2), (-0.36, 0.42), (-0.05, 0.42), (-0.05, 0.2)], "#2E7D4E", w * 0.8),
               rect(-0.33, 0.24, -0.08, 0.38, "#3A3631", w * 0.5),
               line((-0.38, 0.17), (0.36, 0.17), "#2E7D4E", w * 2.4), line((0.2, 0.42), (0.28, 0.5), "#3A3631", w * 1.4),
               rect(0.3, 0.2, 0.36, 0.26, "#F7F5F0", w * 0.6))
    g.add(*wheelset((-0.24, 0.27), 0.09, w))
    return g, None


def _tractor(m, w):
    c = col(m["color"]) if m.get("color") else "#B83227"
    g = VGroup(rect(-0.05, 0.2, 0.4, 0.38, c, w), rect(-0.28, 0.2, -0.02, 0.62, tint(c, -0.1), w),
               rect(-0.24, 0.42, -0.06, 0.58, "#9FC5DA", w * 0.6), rect(0.25, 0.38, 0.29, 0.52, "#3A3631", w * 0.7))
    g.add(wheel_of(VGroup(circ(-0.2, 0.22, 0.22, "#2B2826", w), circ(-0.2, 0.22, 0.1, GOLD, w * 0.6),
                          *(line((-0.2, 0.22), (-0.2 + 0.1 * math.cos(t), 0.22 + 0.1 * math.sin(t)), "#C9962B", w)
                            for t in (0.0, 2.1, 4.2)))),
          wheel_of(VGroup(circ(0.3, 0.12, 0.12, "#2B2826", w), circ(0.3, 0.12, 0.05, GOLD, w * 0.6),
                          line((0.3, 0.12), (0.35, 0.12), "#C9962B", w))))
    return g, None


def _plane(m, w):
    c = col(m["color"]) if m.get("color") else "#F3EEE4"
    return VGroup(poly([(-0.05, 0.22), (0.15, 0.22), (-0.12, 0.02), (-0.2, 0.02)], tint(c, -0.15), w),
                  blob([(-0.55, 0.22), (-0.5, 0.3), (0.4, 0.31), (0.55, 0.25), (0.4, 0.18), (-0.5, 0.17)], c, w),
                  poly([(-0.55, 0.22), (-0.5, 0.45), (-0.4, 0.45), (-0.38, 0.27)], RED, w),
                  poly([(-0.05, 0.25), (0.15, 0.25), (-0.1, 0.4), (-0.18, 0.4)], tint(c, -0.08), w),
                  *(circ(x, 0.255, 0.018, "#9FC5DA", w * 0.4) for x in np.linspace(-0.3, 0.3, 7)),
                  poly([(0.42, 0.28), (0.5, 0.28), (0.46, 0.24)], "#9FC5DA", w * 0.5)), None


def _carriage(m, w):
    c = col(m["color"]) if m.get("color") else "#7A1F2B"
    g = VGroup(line((0.3, 0.3), (0.7, 0.26), WOOD_D, w * 2.4),
               blob([(-0.35, 0.25), (-0.38, 0.55), (-0.3, 0.75), (0.25, 0.75), (0.32, 0.55), (0.3, 0.25)], c, w),
               rect(-0.22, 0.45, 0.17, 0.65, "#9FC5DA", w * 0.6), line((-0.03, 0.45), (-0.03, 0.65), zoo.INK, w * 0.6),
               *(circ(x, 0.78, 0.025, GOLD, w * 0.5) for x in (-0.28, 0.0, 0.23)), stroke([(-0.35, 0.35), (0.3, 0.35)], GOLD, w * 1.4))
    for x, r in ((-0.22, 0.17), (0.22, 0.13)):
        wh, _ = _wheel({"color": GOLD_D}, w)
        wh.scale(r / 0.2, about_point=np.array([0.0, 0.0, 0.0])).shift([x, 0.0, 0])
        g.add(wh)
    return g, None


# -- buildings and places (more) -----------------------------------------------------------------------------------

def _castle(m, w):
    c = col(m["color"]) if m.get("color") else "#B8AE9C"
    g = VGroup()
    for x0, x1, h in ((-0.6, -0.36, 1.0), (0.36, 0.6, 1.0)):
        g.add(rect(x0, 0.0, x1, h, tint(c, -0.05), w), *(rect(x0 + i * 0.08, h, x0 + i * 0.08 + 0.05, h + 0.07, tint(c, -0.05), w * 0.8) for i in range(3)),
              blob([(x0 + 0.08, h - 0.3), (x0 + 0.08, h - 0.2), ((x0 + x1) / 2, h - 0.15), (x1 - 0.08, h - 0.2), (x1 - 0.08, h - 0.3)], "#3A3631", w * 0.6))
    g.add(rect(-0.36, 0.0, 0.36, 0.72, c, w), *(rect(-0.36 + i * 0.1, 0.72, -0.31 + i * 0.1, 0.79, c, w * 0.8) for i in range(8)),
          blob([(-0.14, 0.0), (-0.14, 0.3), (0.0, 0.42), (0.14, 0.3), (0.14, 0.0)], WOOD_D, w),
          *(line((x, 0.0), (x, 0.3), "#3A2A1E", w * 0.6) for x in (-0.07, 0.0, 0.07)),
          *(line((-0.36, y), (0.36, y), tint(c, -0.15), w * 0.4) for y in (0.5, 0.62)),
          line((0.0, 0.79), (0.0, 1.05), WOOD, w * 1.4), live(poly([(0.0, 1.05), (0.18, 1.0), (0.0, 0.95)], col(m.get("flag") or RED), w * 0.7), "flag"))
    return g, None


def _palace(m, w):
    c = col(m["color"]) if m.get("color") else "#F3E3C8"
    g = VGroup(rect(-0.7, 0.0, 0.7, 0.5, c, w), rect(-0.72, 0.5, 0.72, 0.55, tint(c, -0.1), w),
               rect(-0.25, 0.55, 0.25, 0.8, c, w),
               blob([(-0.22, 0.8), (-0.2, 0.95), (-0.1, 1.08), (0.0, 1.18), (0.1, 1.08), (0.2, 0.95), (0.22, 0.8)], "#F7F5F0", w),
               line((0.0, 1.18), (0.0, 1.27), GOLD_D, w * 1.4))
    for x in (-0.55, 0.55):                     # chhatris on the corners
        g.add(*(line((x + d, 0.55), (x + d, 0.7), tint(c, -0.2), w) for d in (-0.07, 0.07)),
              blob([(x - 0.1, 0.7), (x - 0.08, 0.78), (x, 0.84), (x + 0.08, 0.78), (x + 0.1, 0.7)], "#F7F5F0", w))
    for x in np.linspace(-0.55, 0.55, 6):
        g.add(blob([(x - 0.06, 0.08), (x - 0.06, 0.3), (x, 0.38), (x + 0.06, 0.3), (x + 0.06, 0.08)], "#C98A55", w * 0.7))
    g.add(blob([(-0.1, 0.0), (-0.1, 0.32), (0.0, 0.42), (0.1, 0.32), (0.1, 0.0)], "#8E5A3C", w))
    return g, None


def _temple(m, w):
    c = col(m["color"]) if m.get("color") else "#E8B67A"
    g = VGroup(rect(-0.45, 0.0, 0.45, 0.08, tint(c, -0.15), w), rect(-0.35, 0.08, 0.35, 0.45, c, w),
               blob([(-0.25, 0.45), (-0.22, 0.75), (-0.12, 0.95), (0.0, 1.05), (0.12, 0.95), (0.22, 0.75), (0.25, 0.45)], tint(c, 0.05), w))
    for y in (0.58, 0.7, 0.82, 0.92):
        half = 0.25 * (1.05 - y) / 0.6
        g.add(line((-half, y), (half, y), tint(c, -0.25), w * 0.7))
    g.add(circ(0.0, 1.07, 0.035, GOLD, w * 0.7), line((0.0, 1.1), (0.0, 1.22), WOOD_D, w),
          poly([(0.0, 1.22), (0.13, 1.18), (0.0, 1.14)], "#E07B39", w * 0.6),
          blob([(-0.1, 0.08), (-0.1, 0.28), (0.0, 0.36), (0.1, 0.28), (0.1, 0.08)], "#6B3A1E", w),
          *(line((x, 0.08), (x, 0.4), tint(c, -0.2), w * 1.4) for x in (-0.25, -0.17, 0.17, 0.25)))
    return g, None


def _mosque(m, w):
    c = col(m["color"]) if m.get("color") else "#F3EEE4"
    g = VGroup(rect(-0.45, 0.0, 0.45, 0.45, c, w),
               blob([(-0.28, 0.45), (-0.3, 0.6), (-0.18, 0.78), (0.0, 0.86), (0.18, 0.78), (0.3, 0.6), (0.28, 0.45)], "#E9DFC6", w),
               line((0.0, 0.86), (0.0, 0.95), GOLD_D, w), blob([(-0.03, 0.95), (0.0, 1.0), (0.03, 0.95)], GOLD, w * 0.5),
               blob([(-0.12, 0.0), (-0.12, 0.28), (0.0, 0.38), (0.12, 0.28), (0.12, 0.0)], "#3E7C72", w))
    for x in (-0.55, 0.55):
        g.add(rect(x - 0.05, 0.0, x + 0.05, 0.85, c, w), rect(x - 0.07, 0.6, x + 0.07, 0.63, tint(c, -0.15), w * 0.7),
              blob([(x - 0.06, 0.85), (x, 0.97), (x + 0.06, 0.85)], "#E9DFC6", w))
    for x in (-0.3, 0.3):
        g.add(blob([(x - 0.06, 0.12), (x - 0.06, 0.28), (x, 0.34), (x + 0.06, 0.28), (x + 0.06, 0.12)], "#3E7C72", w * 0.7))
    return g, None


def _church(m, w):
    c = col(m["color"]) if m.get("color") else "#E8D5B5"
    return VGroup(rect(-0.45, 0.0, 0.2, 0.45, c, w), poly([(-0.5, 0.43), (-0.12, 0.7), (0.25, 0.43)], "#8E5A3C", w),
                  rect(0.2, 0.0, 0.45, 0.9, tint(c, -0.05), w), poly([(0.17, 0.9), (0.325, 1.2), (0.48, 0.9)], "#8E5A3C", w),
                  line((0.325, 1.2), (0.325, 1.32), GOLD_D, w * 1.4), line((0.28, 1.27), (0.37, 1.27), GOLD_D, w * 1.4),
                  circ(0.325, 0.72, 0.06, "#F7F3E8", w * 0.8),
                  blob([(0.27, 0.0), (0.27, 0.22), (0.325, 0.3), (0.38, 0.22), (0.38, 0.0)], WOOD_D, w),
                  *(blob([(x - 0.05, 0.18), (x - 0.05, 0.32), (x, 0.38), (x + 0.05, 0.32), (x + 0.05, 0.18)], "#9FC5DA", w * 0.7) for x in (-0.3, -0.1))), None


def _school(m, w):
    c = col(m["color"]) if m.get("color") else "#C98A55"
    g = VGroup(rect(-0.6, 0.0, 0.6, 0.5, c, w), poly([(-0.65, 0.48), (0.0, 0.62), (0.65, 0.48)], "#8E3A2C", w),
               rect(-0.15, 0.5, 0.15, 0.78, c, w), poly([(-0.18, 0.76), (0.0, 0.9), (0.18, 0.76)], "#8E3A2C", w),
               circ(0.0, 0.64, 0.06, "#F7F3E8", w * 0.7), line((0.0, 0.64), (0.0, 0.68), zoo.INK, w * 0.6),
               rect(-0.1, 0.0, 0.1, 0.26, "#3E7CB1", w), rect(-0.3, 0.42, 0.3, 0.48, "#F7F3E8", w * 0.5),
               letters(str(m.get("label") or "SCHOOL"), 0.0, 0.45, 0.04))
    for x in (-0.45, -0.28, 0.28, 0.45):
        g.add(rect(x - 0.06, 0.15, x + 0.06, 0.33, "#9FC5DA", w * 0.7))
    return g, None


def _hospital(m, w):
    g = VGroup(rect(-0.5, 0.0, 0.5, 0.75, "#F3EEE4", w), rect(-0.1, 0.0, 0.1, 0.22, "#9FC5DA", w),
               rect(-0.03, 0.55, 0.03, 0.71, RED, 0), rect(-0.08, 0.6, 0.08, 0.66, RED, 0))
    for x in (-0.36, -0.2, 0.2, 0.36):
        for y in (0.3, 0.5):
            g.add(rect(x - 0.05, y, x + 0.05, y + 0.1, "#9FC5DA", w * 0.6))
    return g, None


def _bank(m, w):
    c = col(m["color"]) if m.get("color") else "#E9E2D3"
    g = VGroup(rect(-0.55, 0.0, 0.55, 0.06, tint(c, -0.1), w), rect(-0.5, 0.06, 0.5, 0.1, tint(c, -0.05), w),
               rect(-0.5, 0.52, 0.5, 0.6, c, w), poly([(-0.55, 0.6), (0.0, 0.85), (0.55, 0.6)], c, w),
               letters(str(m.get("label") or "BANK"), 0.0, 0.56, 0.05))
    for x in np.linspace(-0.4, 0.4, 5):
        g.add(rect(x - 0.04, 0.1, x + 0.04, 0.52, c, w), *(line((x + d, 0.12), (x + d, 0.5), tint(c, -0.2), w * 0.4) for d in (-0.015, 0.015)))
    g.add(circ(0.0, 0.72, 0.05, GOLD, w * 0.7))
    return g, None


def _shop(m, w):
    c = col(m["color"]) if m.get("color") else "#E8D5B5"
    g = VGroup(rect(-0.4, 0.0, 0.4, 0.7, c, w), rect(-0.36, 0.08, 0.06, 0.4, "#9FC5DA", w), rect(0.12, 0.0, 0.32, 0.4, WOOD, w),
               rect(-0.4, 0.55, 0.4, 0.68, "#2F3B4C", w), letters(str(m.get("label") or "SHOP"), 0.0, 0.615, 0.06, "#F7F5F0"))
    for i in range(7):
        x0 = -0.42 + i * 0.12
        g.add(poly([(x0, 0.55), (x0 + 0.12, 0.55), (x0 + 0.12, 0.47), (x0, 0.47)], RED if i % 2 == 0 else "#F7F5F0", w * 0.6))
    return g, None


def _skyscraper(m, w):
    c = col(m["color"]) if m.get("color") else "#7E9AB0"
    g = VGroup(rect(-0.2, 0.0, 0.2, 1.4, c, w), rect(-0.12, 1.4, 0.12, 1.5, tint(c, -0.1), w), line((0.0, 1.5), (0.0, 1.68), "#5A5F63", w))
    for y in np.linspace(0.12, 1.3, 12):
        for x in (-0.13, -0.04, 0.05):
            g.add(rect(x, y, x + 0.07, y + 0.06, "#C8DCE8" if int(y * 13 + x * 20) % 3 else "#F2C14E", 0))
    return g, None


def _lighthouse(m, w):
    g = VGroup(poly([(-0.16, 0.0), (0.16, 0.0), (0.09, 0.85), (-0.09, 0.85)], "#F7F5F0", w))
    for y0 in (0.12, 0.42):
        t0, t1 = y0 / 0.85, (y0 + 0.15) / 0.85
        g.add(poly([(-0.16 + 0.07 * t0, y0), (0.16 - 0.07 * t0, y0), (0.16 - 0.07 * t1, y0 + 0.15), (-0.16 + 0.07 * t1, y0 + 0.15)], RED, w * 0.7))
    g.add(rect(-0.12, 0.85, 0.12, 0.88, "#3A3631", w), rect(-0.07, 0.88, 0.07, 1.0, "#FBE7A1", w),
          poly([(-0.1, 1.0), (0.1, 1.0), (0.0, 1.1)], RED, w),
          *(poly([(0.07, 0.96), (0.5, 1.06), (0.5, 0.86)], "#FBE7A1", 0).set_fill(opacity=0.45) for _ in range(1)))
    return g, None


def _bridge(m, w):
    c = col(m["color"]) if m.get("color") else "#B8AE9C"
    pts = [(-0.7, 0.0), (-0.7, 0.3), (0.7, 0.3), (0.7, 0.0), (0.56, 0.0)]
    for cx in (0.3, -0.3):                      # two round arches over the water
        pts += zoo.P._arc(cx, 0.0, 0.24, 0, 180, 14) + [(cx - 0.28, 0.0)]
    pts[-1] = (-0.56, 0.0)
    g = VGroup(poly(pts, c, w), rect(-0.72, 0.3, 0.72, 0.36, tint(c, -0.1), w))
    for x in np.linspace(-0.66, 0.66, 12):
        g.add(line((x, 0.36), (x, 0.44), tint(c, -0.2), w))
    g.add(line((-0.7, 0.44), (0.7, 0.44), tint(c, -0.2), w),
          *(stroke(zoo.P._arc(cx, 0.0, 0.2, 20, 160, 10), tint(c, -0.15), w * 0.6) for cx in (0.3, -0.3)))
    return g, None


def _mountain(m, w):
    return VGroup(poly([(-0.7, 0.0), (-0.2, 0.75), (0.05, 0.45), (0.25, 0.65), (0.7, 0.0)], "#8C8A86", w),
                  poly([(-0.2, 0.75), (-0.3, 0.6), (-0.22, 0.62), (-0.15, 0.55), (-0.1, 0.6)], "#F7F5F0", w * 0.6),
                  poly([(0.25, 0.65), (0.17, 0.55), (0.24, 0.57), (0.3, 0.52), (0.33, 0.56)], "#F7F5F0", w * 0.6),
                  fill_only([(-0.2, 0.75), (-0.05, 0.25), (0.1, 0.0), (0.7, 0.0), (0.25, 0.65), (0.05, 0.45)], "#6E6C68", 0.35, smooth=False)), None


def _cloud(m, w):
    c = col(m["color"]) if m.get("color") else "#FFFFFF"
    puffs = ((-0.18, 0.1, 0.1), (0.18, 0.1, 0.1), (0.0, 0.16, 0.15), (-0.05, 0.08, 0.1))
    g = VGroup(*(circ(x, y, r, c, w) for x, y, r in puffs))
    g.add(*(Circle(radius=r - 0.012, fill_color=c, fill_opacity=1, stroke_width=0).move_to([x, y, 0]) for x, y, r in puffs),
          rect(-0.18, 0.012, 0.18, 0.1, c, 0), line((-0.18, 0.0), (0.18, 0.0), zoo.INK, w))
    return g, None


def _sun(m, w):
    g = VGroup(*(poly([(0.2 * math.cos(a - 0.12), 0.32 + 0.2 * math.sin(a - 0.12)), (0.32 * math.cos(a), 0.32 + 0.32 * math.sin(a)),
                       (0.2 * math.cos(a + 0.12), 0.32 + 0.2 * math.sin(a + 0.12))], "#F2A93B", w * 0.7) for a in np.linspace(0, 2 * math.pi, 13)[:-1]))
    g.add(circ(0.0, 0.32, 0.2, "#F2C14E", w))
    return g, None


def _moon(m, w):
    return VGroup(blob(zoo.P._arc(0.0, 0.2, 0.2, 60, 300, 18) + zoo.P._arc(0.1, 0.2, 0.16, 250, 110, 14), "#F7E9B0", w),
                  *(glint(x, y, 0.03, w) for x, y in ((0.18, 0.38), (0.25, 0.15)))), None


def _flower(m, w):
    c = col(m["color"]) if m.get("color") else "#D46A9A"
    return VGroup(line((0.0, 0.0), (0.0, 0.3), "#5B8C3A", w * 1.6), blob([(0.0, 0.1), (0.1, 0.16), (0.12, 0.12)], "#5B8C3A", w * 0.6),
                  *(circ(0.07 * math.cos(a), 0.36 + 0.07 * math.sin(a), 0.05, c, w * 0.7) for a in np.linspace(0, 2 * math.pi, 7)[:-1]),
                  circ(0.0, 0.36, 0.04, "#F2C14E", w * 0.7)), None


def _lotus(m, w):
    c = col(m["color"]) if m.get("color") else "#E88DB0"
    g = VGroup(ell(0.0, 0.03, 0.5, 0.07, "#4F8A3A", w))
    for a in (-60, -30, 0, 30, 60):
        r = math.radians(a)
        g.add(blob([(0.0, 0.05), (0.13 * math.sin(r) - 0.05 * math.cos(r), 0.12 + 0.1 * math.cos(r)),
                    (0.22 * math.sin(r), 0.05 + 0.22 * math.cos(r)), (0.13 * math.sin(r) + 0.05 * math.cos(r), 0.12 + 0.1 * math.cos(r))],
                   c if a else tint(c, 0.2), w * 0.8))
    return g, None


def _cactus(m, w):
    return VGroup(tube([(0.0, 0.0), (0.0, 0.5)], [0.12, 0.12], "#5B8C3A", w), tube([(-0.06, 0.2), (-0.16, 0.22), (-0.16, 0.36)], [0.07, 0.07, 0.06], "#5B8C3A", w),
                  tube([(0.06, 0.28), (0.15, 0.3), (0.15, 0.42)], [0.07, 0.07, 0.06], "#5B8C3A", w),
                  circ(0.0, 0.53, 0.03, "#D46A9A", w * 0.5)), None


def _mushroom(m, w):
    return VGroup(rrect(-0.05, 0.0, 0.05, 0.14, 0.03, "#F3EEE4", w), blob([(-0.15, 0.12), (-0.12, 0.2), (0.0, 0.25), (0.12, 0.2), (0.15, 0.12)], RED, w),
                  *(circ(x, y, 0.02, "#F7F5F0", 0) for x, y in ((-0.07, 0.18), (0.04, 0.21), (0.09, 0.15)))), None


# -- everyday things, arms and India (more) ------------------------------------------------------------------------

def _ladder(m, w):
    return VGroup(*(line((x, 0.0), (x * 0.8, 0.9), WOOD, w * 2.4) for x in (-0.12, 0.12)),
                  *(line((-0.12 + 0.024 * t, y), (0.12 - 0.024 * t, y), WOOD_D, w * 1.6) for t, y in ((i / 6, 0.1 + i * 0.13) for i in range(7)))), None


def _rope(m, w):
    g = VGroup()
    for k, r in enumerate((0.16, 0.13, 0.1)):
        g.add(Ellipse(width=2 * r + 0.04, height=r, stroke_color=zoo.INK, stroke_width=w * 3.2).move_to([0, 0.08 + k * 0.035, 0]),
              Ellipse(width=2 * r + 0.04, height=r, stroke_color="#C9A066", stroke_width=w * 2).move_to([0, 0.08 + k * 0.035, 0]))
    g.add(stroke([(0.15, 0.08), (0.25, 0.02), (0.3, 0.05)], "#C9A066", w * 2))
    return g, None


def _chain(m, w):
    g = VGroup()
    for i in range(7):
        g.add(Ellipse(width=0.1, height=0.06, stroke_color="#5A5F63", stroke_width=w * 1.8).move_to([-0.3 + i * 0.085, 0.04, 0])
              .rotate(0.0 if i % 2 else 0.0))
    return g, None


def _padlock(m, w):
    return VGroup(stroke(zoo.P._arc(0.0, 0.17, 0.07, 0, 180, 10), "#9AA3A9", w * 3.2), rrect(-0.11, 0.0, 0.11, 0.18, 0.03, GOLD, w),
                  circ(0.0, 0.1, 0.022, "#3A3631", 0), rect(-0.008, 0.04, 0.008, 0.1, "#3A3631", 0)), None


def _umbrella(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    return VGroup(line((0.0, 0.05), (0.0, 0.55), "#3A3631", w * 1.6), stroke(zoo.P._arc(-0.04, 0.05, 0.04, 0, -180, 8), "#3A3631", w * 1.6),
                  blob([(-0.3, 0.5), (-0.2, 0.68), (0.0, 0.75), (0.2, 0.68), (0.3, 0.5), (0.15, 0.53), (0.0, 0.5), (-0.15, 0.53)], c, w)), None


def _gift(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(rect(-0.14, 0.0, 0.14, 0.2, c, w), rect(-0.16, 0.2, 0.16, 0.26, tint(c, 0.08), w),
                  rect(-0.025, 0.0, 0.025, 0.26, GOLD, w * 0.6),
                  blob([(0.0, 0.26), (-0.1, 0.34), (-0.12, 0.28)], GOLD, w * 0.7), blob([(0.0, 0.26), (0.1, 0.34), (0.12, 0.28)], GOLD, w * 0.7)), None


def _balloon(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(stroke([(0.0, 0.0), (0.03, 0.15), (-0.02, 0.3), (0.0, 0.4)], "#3A3631", w * 0.7),
                  blob([(0.0, 0.4), (-0.11, 0.5), (-0.1, 0.64), (0.0, 0.7), (0.1, 0.64), (0.11, 0.5)], c, w),
                  stroke([(-0.06, 0.62), (-0.07, 0.55)], "#FFFFFF", w)), None


def _kite(m, w):
    c = col(m["color"]) if m.get("color") else "#E4572E"
    return VGroup(stroke([(0.0, 0.0), (0.05, 0.15), (-0.03, 0.3), (0.0, 0.42)], "#3A3631", w * 0.6),
                  poly([(0.0, 0.42), (-0.15, 0.6), (0.0, 0.8), (0.15, 0.6)], c, w), poly([(0.0, 0.42), (0.0, 0.8), (0.15, 0.6)], "#F2C14E", w * 0.6),
                  line((-0.15, 0.6), (0.15, 0.6), zoo.INK, w * 0.5)), None


def _ball(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(circ(0.0, 0.1, 0.1, c, w), stroke(zoo.P._arc(0.0, 0.1, 0.1, 100, 260, 10), "#F7F5F0", w * 0.6).shift([0.04, 0, 0]),
                  stroke(zoo.P._arc(0.0, 0.1, 0.1, -80, 80, 10), "#F7F5F0", w * 0.6).shift([-0.04, 0, 0])), None


def _cricketbat(m, w):
    return VGroup(rrect(-0.05, 0.0, 0.05, 0.42, 0.02, "#E8C98A", w), rect(-0.016, 0.42, 0.016, 0.6, "#3A3631", w),
                  stroke([(0.0, 0.05), (0.0, 0.38)], "#C9A066", w * 0.6), circ(0.15, 0.06, 0.06, RED, w),
                  stroke(zoo.P._arc(0.15, 0.06, 0.06, 60, 120, 6), "#F7F5F0", w * 0.6)), None


def _bomb(m, w):
    return VGroup(circ(0.0, 0.14, 0.14, "#2B2826", w), rect(-0.03, 0.27, 0.03, 0.31, "#5A5F63", w),
                  stroke([(0.0, 0.31), (0.04, 0.36), (0.09, 0.35)], "#C9A066", w * 1.2), glint(0.1, 0.36, 0.035, w),
                  stroke(zoo.P._arc(-0.03, 0.17, 0.08, 110, 170, 6), "#6E747A", w)), None


def _broom(m, w):
    return VGroup(line((0.0, 0.18), (0.0, 0.8), WOOD, w * 2.2),
                  poly([(-0.02, 0.2), (0.02, 0.2), (0.12, 0.0), (-0.12, 0.0)], "#D9B45A", w),
                  *(line((x * 0.2, 0.18), (x, 0.0), "#B08A3A", w * 0.5) for x in np.linspace(-0.1, 0.1, 6)),
                  stroke([(-0.04, 0.15), (0.04, 0.15)], RED, w * 2)), None


def _vase(m, w):
    c = col(m["color"]) if m.get("color") else "#2F5E9E"
    return VGroup(blob([(-0.04, 0.38), (-0.05, 0.3), (-0.13, 0.18), (-0.08, 0.02), (0.08, 0.02), (0.13, 0.18), (0.05, 0.3), (0.04, 0.38)], "#F3EEE4", w),
                  stroke([(-0.12, 0.17), (0.12, 0.17)], c, w * 2), stroke([(-0.07, 0.07), (0.07, 0.07)], c, w * 1.4),
                  *(circ(x, 0.25, 0.012, c, 0) for x in (-0.04, 0.0, 0.04))), None


def _rug(m, w):
    c = col(m["color"]) if m.get("color") else "#8E1B2C"
    return VGroup(poly([(-0.5, 0.0), (0.5, 0.0), (0.42, 0.12), (-0.42, 0.12)], c, w),
                  poly([(-0.42, 0.02), (0.42, 0.02), (0.36, 0.1), (-0.36, 0.1)], "#FFFFFF", w).set_fill(opacity=0).set_stroke(GOLD, w),
                  poly([(-0.1, 0.06), (0.0, 0.1), (0.1, 0.06), (0.0, 0.02)], "#2F5E9E", w * 0.6),
                  *(line((x, 0.0), (x * 1.04, -0.03), GOLD, w * 0.6) for x in np.linspace(-0.48, 0.48, 12))), None


def _bunting(m, w):
    g = VGroup(stroke([(-0.6, 0.4), (0.0, 0.3), (0.6, 0.4)], "#3A3631", w * 0.7))
    cols_ = ["#E07B39", "#F7F5F0", "#2E7D4E"] if m.get("india") else ["#B83227", "#F2C14E", "#3E7CB1", "#5B8C3A"]
    for i, x in enumerate(np.linspace(-0.52, 0.52, 9)):
        y = 0.3 + 0.1 * (x / 0.6) ** 2
        g.add(poly([(x - 0.05, y), (x + 0.05, y), (x, y - 0.12)], cols_[i % len(cols_)], w * 0.7))
    return g, None


def _musket(m, w):
    return VGroup(line((-0.4, 0.06), (0.45, 0.14), "#5A5F63", w * 2), poly([(-0.45, 0.0), (-0.1, 0.07), (-0.1, 0.1), (-0.4, 0.09)], WOOD, w),
                  poly([(-0.1, 0.07), (0.3, 0.12), (0.3, 0.14), (-0.1, 0.1)], WOOD, w * 0.8), rect(-0.12, 0.08, -0.07, 0.12, GOLD_D, w * 0.6)), None


def _axe(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.55), WOOD, w * 2.6),
                  blob([(0.0, 0.5), (0.12, 0.56), (0.14, 0.42), (0.0, 0.44)], "#B8BEC2", w), rect(-0.02, 0.43, 0.02, 0.52, "#5A5F63", w * 0.6)), None


def _helmet(m, w):
    return VGroup(blob(zoo.P._arc(0.0, 0.05, 0.16, 0, 180, 16), "#A7AEB3", w),
                  rect(-0.2, 0.03, 0.2, 0.07, "#8E969C", w), stroke([(-0.1, 0.18), (0.0, 0.21), (0.1, 0.18)], "#D6DADD", w * 0.8)), None


def _charpai(m, w):
    g = VGroup(*(rect(x, 0.0, x + 0.04, 0.24, WOOD_D, w) for x in (-0.48, 0.44)),
               rect(-0.5, 0.18, 0.5, 0.23, WOOD, w))
    for x in np.linspace(-0.44, 0.44, 12):
        g.add(line((x, 0.185), (x + 0.04, 0.225), "#E9DFC6", w * 0.6))
    return g, None


def _tiffin(m, w):
    g = VGroup(stroke(zoo.P._arc(0.0, 0.32, 0.07, 0, 180, 10), "#9AA3A9", w * 2), line((0.0, 0.0), (0.0, 0.36), "#9AA3A9", w * 1.2))
    for i in range(3):
        y = i * 0.1
        g.add(rrect(-0.1, y, 0.1, y + 0.1, 0.02, "#C9D0D4", w), line((-0.1, y + 0.02), (0.1, y + 0.02), "#9AA3A9", w * 0.6))
    return g, None


def _lattu(m, w):
    return VGroup(blob([(0.0, 0.0), (-0.1, 0.12), (-0.08, 0.2), (0.08, 0.2), (0.1, 0.12)], "#E4572E", w),
                  stroke([(-0.09, 0.15), (0.09, 0.15)], "#F2C14E", w * 1.4), rect(-0.012, 0.2, 0.012, 0.26, WOOD, w * 0.6)), None


def _rangoli(m, w):
    g = VGroup()
    for r, c in ((0.3, "#E4572E"), (0.22, "#F2C14E"), (0.14, "#D46A9A"), (0.07, "#3E7CB1")):
        pts = [(r * 1.4 * math.cos(a) * (1 + 0.15 * math.cos(8 * a)), 0.2 * (r / 0.3) * math.sin(a) * (1 + 0.15 * math.cos(8 * a)) + 0.21)
               for a in np.linspace(0, 2 * math.pi, 64)]
        g.add(blob(pts, c, w * 0.6))
    return g, None


def _flagindia(m, w):
    g = VGroup(line((0.0, 0.0), (0.0, 1.1), "#9AA3A9", w * 1.8), circ(0.0, 1.11, 0.015, GOLD, w * 0.5))
    for i, c in enumerate(("#FF9933", "#F7F5F0", "#138808")):
        y = 1.06 - i * 0.07
        g.add(live(poly([(0.0, y), (0.32, y), (0.32, y - 0.07), (0.0, y - 0.07)], c, w * 0.6), "flag", (0.0, 0.32)))
    g.add(live(Circle(radius=0.025, stroke_color="#000080", stroke_width=w * 0.8).move_to([0.16, 0.955, 0]), "flag", (0.0, 0.32)))
    return g, None


# -- war and the past ----------------------------------------------------------------------------------------------

def _catapult(m, w):
    g = VGroup(rect(-0.4, 0.08, 0.4, 0.14, WOOD, w), line((-0.3, 0.14), (-0.1, 0.42), WOOD_D, w * 2.6),
               line((0.1, 0.14), (-0.1, 0.42), WOOD_D, w * 2.6), line((-0.32, 0.4), (0.2, 0.62), WOOD, w * 2.4),
               blob([(0.16, 0.6), (0.26, 0.68), (0.3, 0.62), (0.22, 0.56)], WOOD_D, w), circ(0.24, 0.66, 0.05, "#8E969C", w * 0.6))
    g.add(*wheelset((-0.28, 0.28), 0.08, w, WOOD_D))
    return g, None


def _armor(m, w):
    """A suit of armour on its stand."""
    g = VGroup(rect(-0.12, 0.0, 0.12, 0.04, WOOD_D, w), line((0.0, 0.04), (0.0, 0.2), WOOD_D, w * 2),
               rrect(-0.12, 0.2, 0.12, 0.5, 0.05, "#A7AEB3", w), *(line((-0.11, y), (0.11, y), "#7E868C", w * 0.6) for y in (0.28, 0.36, 0.44)),
               ell(-0.16, 0.48, 0.1, 0.08, "#8E969C", w), ell(0.16, 0.48, 0.1, 0.08, "#8E969C", w),
               rrect(-0.08, 0.5, 0.08, 0.68, 0.04, "#A7AEB3", w), rect(-0.02, 0.58, 0.08, 0.6, "#2B2622", 0),
               blob([(0.0, 0.68), (-0.05, 0.78), (0.03, 0.8)], RED, w * 0.6))
    return g, None


def _arrow(m, w):
    return VGroup(line((-0.3, 0.05), (0.25, 0.05), WOOD, w * 1.6), poly([(0.24, 0.02), (0.32, 0.05), (0.24, 0.08)], IRON, w * 0.6),
                  poly([(-0.3, 0.05), (-0.36, 0.09), (-0.26, 0.05), (-0.36, 0.01)], "#F7F5F0", w * 0.6)), None


def _quiver(m, w):
    g = VGroup(*(line((x, 0.3), (x + 0.02, 0.48), WOOD, w * 1.2) for x in (-0.03, 0.0, 0.03)),
               *(poly([(x - 0.015, 0.47), (x + 0.035, 0.47), (x + 0.01, 0.53)], "#F7F5F0", w * 0.5) for x in (-0.03, 0.0, 0.03)),
               rrect(-0.06, 0.0, 0.06, 0.34, 0.03, "#6B4226", w), line((-0.06, 0.25), (0.06, 0.25), "#3A2A1E", w))
    return g, None


def _banner(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(line((0.0, 0.0), (0.0, 1.0), WOOD, w * 2), line((-0.02, 0.92), (0.26, 0.92), WOOD, w * 1.6),
                  live(poly([(0.0, 0.92), (0.26, 0.92), (0.26, 0.5), (0.13, 0.42), (0.0, 0.5)], c, w), "flag"),
                  circ(0.13, 0.7, 0.05, GOLD, w * 0.6), poly([(0.0, 1.0), (0.03, 1.06), (-0.03, 1.06)], GOLD, w * 0.5)), None


def _drum(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(rect(-0.14, 0.0, 0.14, 0.2, c, w), ell(0.0, 0.2, 0.28, 0.07, "#F3EADA", w),
                  *(line((x, 0.0), (x + 0.07, 0.2), GOLD, w * 0.8) for x in (-0.14, -0.04, 0.06)),
                  line((0.1, 0.24), (0.24, 0.36), WOOD, w * 1.4), circ(0.24, 0.36, 0.015, WOOD_D, 0)), None


def _horn(m, w):
    return VGroup(tube([(-0.25, 0.1), (0.0, 0.12), (0.18, 0.16)], [0.02, 0.03, 0.05], GOLD, w),
                  ell(0.2, 0.16, 0.05, 0.14, GOLD_D, w), line((-0.27, 0.1), (-0.24, 0.1), GOLD_D, w * 2)), None


def _chariot(m, w):
    c = col(m["color"]) if m.get("color") else "#B5643C"
    g = VGroup(line((0.15, 0.25), (0.6, 0.22), WOOD_D, w * 2.4),
               blob([(-0.25, 0.18), (-0.25, 0.42), (-0.1, 0.48), (0.15, 0.42), (0.18, 0.18)], c, w),
               stroke([(-0.23, 0.38), (0.15, 0.36)], GOLD, w * 1.4))
    wh, _ = _wheel({"color": WOOD_D}, w)
    wh.scale(0.9, about_point=np.array([0.0, 0.0, 0.0])).shift([-0.05, 0.0, 0])
    g.add(wh)
    return g, None


def _dagger(m, w):
    return VGroup(poly([(-0.012, 0.1), (0.012, 0.1), (0.0, 0.3)], "#C9D0D4", w), rect(-0.04, 0.09, 0.04, 0.105, GOLD, w * 0.6),
                  rect(-0.01, 0.02, 0.01, 0.09, "#5B4A3A", w * 0.6), circ(0.0, 0.015, 0.015, GOLD, w * 0.5)), None


def _mace(m, w):
    g = VGroup(line((0.0, 0.0), (0.0, 0.42), WOOD, w * 2.4), circ(0.0, 0.48, 0.07, "#8E969C", w))
    for a in np.linspace(0, 2 * math.pi, 9)[:-1]:
        g.add(poly([(0.06 * math.cos(a - 0.3), 0.48 + 0.06 * math.sin(a - 0.3)), (0.11 * math.cos(a), 0.48 + 0.11 * math.sin(a)),
                    (0.06 * math.cos(a + 0.3), 0.48 + 0.06 * math.sin(a + 0.3))], "#B8BEC2", w * 0.5))
    return g, None


def _cannonballs(m, w):
    g = VGroup()
    for r, n in ((0, 3), (1, 2), (2, 1)):
        for i in range(n):
            g.add(circ(-0.09 * (n - 1) + i * 0.18, 0.08 + r * 0.15, 0.08, "#2B2826", w * 0.7))
    return g, None


def _tank(m, w):
    c = col(m["color"]) if m.get("color") else "#5B6B3A"
    return VGroup(rrect(-0.45, 0.0, 0.45, 0.16, 0.08, "#3A3631", w),
                  *(circ(x, 0.08, 0.055, "#6E747A", w * 0.6) for x in np.linspace(-0.35, 0.35, 6)),
                  poly([(-0.42, 0.16), (0.42, 0.16), (0.36, 0.28), (-0.38, 0.28)], c, w),
                  rrect(-0.2, 0.28, 0.12, 0.42, 0.05, tint(c, 0.08), w), line((0.1, 0.36), (0.55, 0.38), c, w * 3.2)), None


# -- monuments ----------------------------------------------------------------------------------------------------

def _pyramids(m, w):
    return VGroup(poly([(-0.1, 0.0), (0.3, 0.55), (0.7, 0.0)], "#E2C27A", w), poly([(0.3, 0.55), (0.7, 0.0), (0.45, 0.0)], "#C9A35A", 0),
                  poly([(-0.7, 0.0), (-0.25, 0.75), (0.2, 0.0)], "#E8C988", w), poly([(-0.25, 0.75), (0.2, 0.0), (-0.05, 0.0)], "#CDA866", 0),
                  *(stroke([(-0.25 - 0.4 * t, 0.75 - 0.75 * t), (-0.25 + 0.4 * t, 0.75 - 0.75 * t)], "#B8934E", w * 0.4) for t in (0.3, 0.55, 0.8))), None


def _obelisk(m, w):
    return VGroup(rect(-0.14, 0.0, 0.14, 0.06, "#C9BFA8", w), poly([(-0.08, 0.06), (0.08, 0.06), (0.06, 0.85), (-0.06, 0.85)], "#E2D3B0", w),
                  poly([(-0.06, 0.85), (0.06, 0.85), (0.0, 0.95)], GOLD, w),
                  *(rect(-0.02, y, 0.02, y + 0.04, "#B8A884", 0) for y in (0.25, 0.4, 0.55, 0.7))), None


def _pillar(m, w):
    c = col(m["color"]) if m.get("color") else "#ECE6DA"
    return VGroup(rect(-0.14, 0.0, 0.14, 0.05, tint(c, -0.1), w), rect(-0.1, 0.05, 0.1, 0.8, c, w),
                  *(line((x, 0.06), (x, 0.79), tint(c, -0.15), w * 0.6) for x in (-0.05, 0.0, 0.05)),
                  rect(-0.14, 0.8, 0.14, 0.86, tint(c, -0.1), w),
                  blob([(-0.16, 0.86), (-0.18, 0.9), (0.18, 0.9), (0.16, 0.86)], tint(c, -0.05), w)), None


def _arch(m, w):
    c = col(m["color"]) if m.get("color") else "#E2D3B0"
    pts = [(-0.45, 0.0), (-0.45, 0.85), (0.45, 0.85), (0.45, 0.0), (0.22, 0.0)] + zoo.P._arc(0.0, 0.45, 0.22, 0, 180, 14) + [(-0.22, 0.0)]
    return VGroup(poly(pts, c, w), rect(-0.5, 0.85, 0.5, 0.95, tint(c, -0.1), w),
                  *(line((-0.45, y), (-0.22, y), tint(c, -0.15), w * 0.5) for y in (0.2, 0.4)),
                  *(line((0.22, y), (0.45, y), tint(c, -0.15), w * 0.5) for y in (0.2, 0.4))), None


def _statue(m, w):
    c = col(m["color"]) if m.get("color") else "#9FB5A8"
    return VGroup(rect(-0.18, 0.0, 0.18, 0.25, "#C9BFA8", w), rect(-0.2, 0.25, 0.2, 0.29, "#B8AE9C", w),
                  rrect(-0.09, 0.29, 0.09, 0.62, 0.04, c, w), circ(0.0, 0.7, 0.07, c, w),
                  line((0.08, 0.55), (0.18, 0.8), c, w * 2.6), circ(0.18, 0.82, 0.025, c, w * 0.6),
                  poly([(-0.09, 0.29), (-0.14, 0.29), (-0.09, 0.5)], tint(c, -0.1), w * 0.5)), None


def _fountain(m, w):
    return VGroup(ell(0.0, 0.08, 0.7, 0.16, "#B8AE9C", w), rect(-0.35, 0.0, 0.35, 0.08, "#C9BFA8", w),
                  ell(0.0, 0.12, 0.6, 0.1, "#9FC5DA", w * 0.6), rect(-0.03, 0.12, 0.03, 0.35, "#C9BFA8", w),
                  ell(0.0, 0.36, 0.26, 0.06, "#B8AE9C", w),
                  live(stroke([(0.0, 0.38), (0.06, 0.48), (0.12, 0.38), (0.15, 0.2)], "#9FC5DA", w * 1.2), "steam"),
                  live(stroke([(0.0, 0.38), (-0.06, 0.48), (-0.12, 0.38), (-0.15, 0.2)], "#9FC5DA", w * 1.2), "steam")), None


def _stupa(m, w):
    return VGroup(rect(-0.45, 0.0, 0.45, 0.1, "#C9BFA8", w), blob(zoo.P._arc(0.0, 0.1, 0.36, 0, 180, 18), "#F3EEE4", w),
                  rect(-0.08, 0.46, 0.08, 0.54, "#E2D3B0", w),
                  *(rect(-0.05 + 0.01 * i, 0.54 + i * 0.05, 0.05 - 0.01 * i, 0.58 + i * 0.05, GOLD, w * 0.5) for i in range(4)),
                  line((0.0, 0.74), (0.0, 0.82), GOLD_D, w), stroke([(-0.3, 0.2), (0.3, 0.2)], "#E2D3B0", w * 0.8)), None


# -- India ------------------------------------------------------------------------------------------------------------

def _loom(m, w):
    g = VGroup(*(line((x, 0.0), (x, 0.6), WOOD, w * 2.4) for x in (-0.35, 0.35)), line((-0.38, 0.58), (0.38, 0.58), WOOD_D, w * 2.2),
               line((-0.38, 0.12), (0.38, 0.12), WOOD_D, w * 2.2))
    cols_ = ["#B83227", "#F2C14E", "#2E7D74", "#F7F5F0"]
    for i, x in enumerate(np.linspace(-0.3, 0.3, 13)):
        g.add(line((x, 0.13), (x, 0.57), cols_[i % 4], w * 0.8))
    g.add(rect(-0.3, 0.13, 0.3, 0.3, "#B83227", w * 0.6), *(line((-0.3, y), (0.3, y), GOLD, w * 0.6) for y in (0.18, 0.24)),
          rrect(-0.36, 0.34, 0.36, 0.38, 0.02, WOOD_D, w))
    return g, None


def _kalash(m, w):
    return VGroup(blob([(-0.06, 0.2), (-0.14, 0.12), (-0.1, 0.02), (0.0, 0.0), (0.1, 0.02), (0.14, 0.12), (0.06, 0.2)], GOLD_D, w),
                  stroke([(-0.13, 0.1), (0.13, 0.1)], RED, w * 1.4),
                  *(blob([(0.0, 0.21), (x * 0.18, 0.3), (x * 0.12, 0.22)], "#4F8A3A", w * 0.5) for x in (-1, -0.5, 0.5, 1)),
                  circ(0.0, 0.3, 0.07, "#8C6E52", w), stroke([(-0.05, 0.3), (0.05, 0.3)], RED, w)), None


def _conch(m, w):
    body = blob([(-0.3, 0.1), (-0.16, 0.04), (0.02, 0.02), (0.16, 0.06), (0.3, 0.12), (0.18, 0.18), (0.14, 0.26),
                 (0.05, 0.22), (0.0, 0.3), (-0.08, 0.24), (-0.14, 0.27), (-0.18, 0.18)], "#F7F1E3", w)
    lip = blob([(-0.26, 0.11), (-0.12, 0.07), (0.04, 0.08), (-0.02, 0.15), (-0.14, 0.16)], "#F2B8A6", w * 0.5)
    whorls = [stroke([(0.14 + k * 0.05, 0.08 + k * 0.012), (0.19 + k * 0.03, 0.17 - k * 0.015)], "#CDBF9F", w * 0.6) for k in range(3)]
    ribs = [stroke([(x, 0.05), (x + 0.03, 0.2)], "#DCCFB2", w * 0.5) for x in (-0.06, 0.02, 0.09)]
    return VGroup(body, *ribs, *whorls, lip), None


def _sitar(m, w):
    return VGroup(ell(-0.25, 0.12, 0.3, 0.24, "#C2552B", w), line((-0.15, 0.15), (0.45, 0.42), WOOD, w * 3.2),
                  circ(0.25, 0.33, 0.06, "#C2552B", w * 0.8), *(line((-0.3, 0.12), (0.45, 0.43 - i * 0.01), "#E8E0CC", w * 0.3) for i in range(3)),
                  *(line((0.3 + i * 0.04, 0.37 + i * 0.02), (0.31 + i * 0.04, 0.42 + i * 0.02), GOLD, w * 0.8) for i in range(3))), None


def _tabla(m, w):
    return VGroup(poly([(-0.25, 0.0), (-0.09, 0.0), (-0.07, 0.2), (-0.27, 0.2)], WOOD, w), ell(-0.17, 0.2, 0.2, 0.05, "#3A3631", w * 0.6),
                  blob([(0.05, 0.0), (0.27, 0.0), (0.3, 0.1), (0.24, 0.17), (0.08, 0.17), (0.02, 0.1)], "#9AA3A9", w),
                  ell(0.16, 0.17, 0.22, 0.05, "#3A3631", w * 0.6),
                  *(line((-0.24 + i * 0.05, 0.02), (-0.24 + i * 0.05, 0.19), "#6B4226", w * 0.5) for i in range(4))), None


def _flute(m, w):
    return VGroup(rrect(-0.35, 0.04, 0.35, 0.08, 0.02, "#C9A066", w), *(circ(x, 0.06, 0.008, "#3A2A1E", 0) for x in np.linspace(-0.1, 0.25, 6)),
                  line((-0.3, 0.04), (-0.3, 0.08), RED, w * 1.4), line((0.3, 0.04), (0.3, 0.08), RED, w * 1.4)), None


def _palanquin(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(line((-0.6, 0.45), (0.6, 0.45), WOOD_D, w * 3), rrect(-0.3, 0.2, 0.3, 0.6, 0.05, c, w),
                  rect(-0.15, 0.3, 0.15, 0.52, "#F7E9B0", w * 0.6), blob([(-0.34, 0.6), (0.0, 0.78), (0.34, 0.6)], GOLD, w),
                  *(line((x, 0.6), (x, 0.2), GOLD, w * 0.8) for x in (-0.3, 0.3)), circ(0.0, 0.8, 0.02, RED, 0)), None


def _chulha(m, w):
    return VGroup(blob([(-0.25, 0.0), (-0.24, 0.16), (0.24, 0.16), (0.25, 0.0)], "#B5643C", w),
                  blob(zoo.P._arc(0.0, 0.0, 0.08, 0, 180, 10), "#3A2A1E", w * 0.6),
                  live(blob([(-0.04, 0.0), (0.0, 0.08), (0.04, 0.0)], "#F2A93B", 0), "flame"),
                  blob([(-0.16, 0.16), (-0.18, 0.28), (0.0, 0.32), (0.18, 0.28), (0.16, 0.16)], "#6E747A", w),
                  live(stroke([(0.0, 0.33), (-0.03, 0.4), (0.01, 0.46)], "#C9C2B2", w), "steam")), None


def _handpump(m, w):
    return VGroup(rect(-0.12, 0.0, 0.12, 0.05, "#B8AE9C", w), rect(-0.04, 0.05, 0.04, 0.5, "#3E7C72", w),
                  poly([(0.04, 0.4), (0.18, 0.38), (0.18, 0.34), (0.04, 0.36)], "#3E7C72", w * 0.8),
                  line((-0.03, 0.5), (-0.3, 0.62), "#2E5E57", w * 2), circ(-0.04, 0.5, 0.025, "#2E5E57", w * 0.6),
                  stroke([(0.17, 0.33), (0.17, 0.18)], "#9FC5DA", w * 1.4)), None


def _haystack(m, w):
    return VGroup(blob([(-0.35, 0.0), (-0.3, 0.3), (-0.12, 0.5), (0.0, 0.55), (0.12, 0.5), (0.3, 0.3), (0.35, 0.0)], "#E2C27A", w),
                  *(stroke([(x, 0.05), (x * 0.8 + 0.02, 0.35)], "#C9A050", w * 0.6) for x in np.linspace(-0.25, 0.25, 6)),
                  line((0.2, 0.35), (0.3, 0.7), WOOD, w * 1.4)), None


def _spices(m, w):
    g = VGroup()
    for x, c in ((-0.22, "#E4572E"), (0.0, "#F2C14E"), (0.22, "#7E5A2B")):
        g.add(ell(x, 0.07, 0.2, 0.06, "#C9A066", w * 0.7), blob([(x - 0.09, 0.08), (x, 0.17), (x + 0.09, 0.08)], c, w * 0.6),
              poly([(x - 0.1, 0.07), (x + 0.1, 0.07), (x + 0.07, 0.0), (x - 0.07, 0.0)], "#C9A066", w * 0.7))
    return g, None


# -- science, power and the modern world -------------------------------------------------------------------------

def _dna(m, w):
    g = VGroup()
    ys = np.linspace(0.0, 0.8, 40)
    a = [(0.12 * math.sin(y * 9), y) for y in ys]
    b = [(-0.12 * math.sin(y * 9), y) for y in ys]
    for i in range(0, 40, 4):
        g.add(line(a[i], b[i], ["#E4572E", "#F2C14E", "#2E7D74", "#3E7CB1"][(i // 4) % 4], w * 1.2))
    g.add(stroke(a, "#2F3B8C", w * 1.8), stroke(b, "#B83227", w * 1.8))
    return g, None


def _deskglobe(m, w):
    return VGroup(ell(0.0, 0.02, 0.24, 0.05, WOOD_D, w), line((0.0, 0.02), (0.0, 0.12), WOOD_D, w * 2),
                  circ(0.0, 0.36, 0.22, "#9FC5DA", w),
                  blob([(-0.12, 0.4), (-0.04, 0.5), (0.02, 0.42), (-0.06, 0.32)], "#7BB04B", w * 0.5),
                  blob([(0.05, 0.3), (0.14, 0.36), (0.12, 0.22), (0.04, 0.2)], "#7BB04B", w * 0.5),
                  stroke(zoo.P._arc(0.0, 0.36, 0.26, -120, 120, 16), GOLD_D, w * 1.2)), None


def _compass(m, w):
    return VGroup(circ(0.0, 0.15, 0.15, GOLD_D, w), circ(0.0, 0.15, 0.12, "#F3EADA", w * 0.6),
                  poly([(0.0, 0.25), (0.025, 0.15), (0.0, 0.05), (-0.025, 0.15)], "#3A3631", w * 0.4),
                  poly([(0.0, 0.25), (0.025, 0.15), (-0.025, 0.15)], RED, 0), letters("N", 0.0, 0.29, 0.03, "#3A3631")), None


def _robot(m, w):
    c = col(m["color"]) if m.get("color") else "#9AA3A9"
    return VGroup(rect(-0.1, 0.0, -0.04, 0.15, tint(c, -0.2), w), rect(0.04, 0.0, 0.1, 0.15, tint(c, -0.2), w),
                  rrect(-0.15, 0.15, 0.15, 0.45, 0.04, c, w), rect(-0.08, 0.25, 0.08, 0.37, "#3E7CB1", w * 0.6),
                  *(line((s * 0.15, 0.4), (s * 0.24, 0.2), tint(c, -0.2), w * 2) for s in (-1, 1)),
                  rrect(-0.11, 0.47, 0.11, 0.65, 0.04, c, w), circ(-0.045, 0.56, 0.025, "#9FE3F2", w * 0.5),
                  circ(0.045, 0.56, 0.025, "#9FE3F2", w * 0.5), line((0.0, 0.65), (0.0, 0.72), c, w), circ(0.0, 0.73, 0.018, RED, 0)), None


def _drone(m, w):
    g = VGroup(rrect(-0.12, 0.06, 0.12, 0.13, 0.03, "#3A3631", w), circ(0.0, 0.07, 0.03, "#3E7CB1", w * 0.5))
    for s in (-1, 1):
        g.add(line((0.0, 0.11), (s * 0.28, 0.14), "#3A3631", w * 1.4), ell(s * 0.28, 0.16, 0.2, 0.025, "#B8BEC2", w * 0.5),
              line((s * 0.28, 0.12), (s * 0.28, 0.16), "#3A3631", w))
    return g, None


def _windturbine(m, w):
    g = VGroup(poly([(-0.03, 0.0), (0.03, 0.0), (0.015, 0.9), (-0.015, 0.9)], "#F3EEE4", w), rrect(-0.05, 0.88, 0.07, 0.94, 0.02, "#F3EEE4", w))
    for a in (90, 210, 330):
        r = math.radians(a)
        g.add(live(poly([(0.0, 0.91), (0.5 * math.cos(r) - 0.03 * math.sin(r), 0.91 + 0.5 * math.sin(r) + 0.03 * math.cos(r)),
                         (0.5 * math.cos(r), 0.91 + 0.5 * math.sin(r))], "#FFFFFF", w * 0.8), "spin", (0.0, 0.91)))
    g.add(circ(0.0, 0.91, 0.03, "#C9C2B2", w * 0.6))
    return g, None


def _pylon(m, w):
    g = VGroup(poly([(-0.25, 0.0), (0.25, 0.0), (0.0, 1.0)], "#FFFFFF", w).set_fill(opacity=0).set_stroke("#6E747A", w * 1.4))
    for y in (0.3, 0.55, 0.75):
        half = 0.25 * (1 - y)
        g.add(line((-half, y), (half, y), "#6E747A", w), line((-half - 0.15, y + 0.05), (half + 0.15, y + 0.05), "#6E747A", w * 1.2))
    g.add(*(line((-0.25 * (1 - y0), y0), (0.25 * (1 - y1), y1), "#6E747A", w * 0.6) for y0, y1 in ((0.0, 0.3), (0.3, 0.55))))
    return g, None


def _streetlight(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 1.0), "#3A3631", w * 2.2), stroke([(0.0, 1.0), (0.08, 1.06), (0.2, 1.04)], "#3A3631", w * 2),
                  poly([(0.12, 1.04), (0.28, 1.04), (0.24, 0.98), (0.16, 0.98)], "#3A3631", w),
                  live(poly([(0.16, 0.98), (0.24, 0.98), (0.34, 0.6), (0.06, 0.6)], "#FBE7A1", 0), "puff"),
                  rect(-0.06, 0.0, 0.06, 0.05, "#3A3631", w)), None


def _trafficlight(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.6), "#3A3631", w * 2.2), rrect(-0.08, 0.55, 0.08, 0.95, 0.03, "#2B2826", w),
                  circ(0.0, 0.88, 0.04, "#E4572E", w * 0.5), circ(0.0, 0.75, 0.04, "#6B5A2B", w * 0.5),
                  circ(0.0, 0.62, 0.04, "#2E5E3A", w * 0.5)), None


def _calculator(m, w):
    g = VGroup(rrect(-0.11, 0.0, 0.11, 0.3, 0.02, "#3A3631", w), rect(-0.08, 0.22, 0.08, 0.27, "#C9D6A0", w * 0.5))
    for r in range(4):
        for c_ in range(3):
            g.add(rrect(-0.075 + c_ * 0.055, 0.03 + r * 0.045, -0.04 + c_ * 0.055, 0.06 + r * 0.045, 0.006,
                        "#E4572E" if (r, c_) == (0, 2) else "#9AA3A9", w * 0.3))
    return g, None


def _whiteboard(m, w):
    g = VGroup(line((-0.3, 0.0), (-0.25, 0.3), "#6E747A", w * 1.6), line((0.3, 0.0), (0.25, 0.3), "#6E747A", w * 1.6),
               rect(-0.4, 0.3, 0.4, 0.8, "#F7F7F2", w), rect(-0.4, 0.28, 0.4, 0.3, "#9AA3A9", w * 0.6))
    if str(m.get("of") or "chart") == "chart":         # a rising line drawn on it
        g.add(stroke([(-0.32, 0.38), (-0.15, 0.48), (0.0, 0.44), (0.15, 0.6), (0.32, 0.72)], "#E4572E", w * 1.4),
              line((-0.33, 0.36), (0.34, 0.36), "#3A3631", w * 0.6), line((-0.33, 0.36), (-0.33, 0.76), "#3A3631", w * 0.6))
    if m.get("label"):
        g.add(letters(str(m["label"]), 0.0, 0.7, 0.07, "#2F3B8C"))
    return g, None


def _blackboard(m, w):
    g = VGroup(rect(-0.45, 0.25, 0.45, 0.8, WOOD, w), rect(-0.42, 0.28, 0.42, 0.77, "#2E4A3A", w * 0.6),
               *(line((x, 0.0), (x, 0.28), WOOD_D, w * 2) for x in (-0.35, 0.35)))
    words = str(m.get("label") or "A + B = C")
    g.add(letters(words, 0.0, 0.55, 0.1, "#F7F5F0"), rect(0.25, 0.29, 0.33, 0.31, "#F7F5F0", 0))
    return g, None


def _oilbarrel(m, w):
    c = col(m["color"]) if m.get("color") else "#2F3B4C"
    return VGroup(rrect(-0.12, 0.0, 0.12, 0.36, 0.02, c, w), *(line((-0.12, y), (0.12, y), tint(c, -0.3), w * 1.4) for y in (0.1, 0.26)),
                  ell(0.0, 0.36, 0.24, 0.04, tint(c, 0.2), w * 0.6), circ(0.06, 0.36, 0.012, "#3A3631", 0),
                  blob([(-0.02, 0.15), (0.0, 0.2), (0.02, 0.15), (0.0, 0.13)], "#F2C14E", 0)), None


def _fuelpump(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(rect(-0.14, 0.0, 0.14, 0.05, "#6E747A", w), rrect(-0.12, 0.05, 0.12, 0.55, 0.03, c, w),
                  rect(-0.08, 0.38, 0.08, 0.48, "#F7F5F0", w * 0.6), letters("88.8", 0.0, 0.43, 0.04, "#3A3631"),
                  stroke([(0.12, 0.3), (0.2, 0.28), (0.22, 0.15), (0.18, 0.1)], "#3A3631", w * 1.4),
                  rect(0.12, 0.25, 0.17, 0.32, "#3A3631", w * 0.6)), None


def _container(m, w):
    c = col(m["color"]) if m.get("color") else "#B83227"
    g = VGroup(rect(-0.5, 0.0, 0.5, 0.36, c, w))
    for x in np.linspace(-0.45, 0.45, 15):
        g.add(line((x, 0.03), (x, 0.33), tint(c, -0.2), w * 0.6))
    g.add(rect(-0.5, 0.33, 0.5, 0.36, tint(c, -0.25), 0))
    if m.get("label"):
        g.add(letters(str(m["label"]), 0.0, 0.18, 0.08, "#F7F5F0"))
    return g, None


def _crane(m, w):
    g = VGroup(rect(-0.15, 0.0, 0.15, 0.06, "#3A3631", w), poly([(-0.06, 0.06), (0.06, 0.06), (0.05, 1.1), (-0.05, 1.1)], "#F2C14E", w))
    for y in np.linspace(0.1, 1.0, 8):
        g.add(line((-0.05, y), (0.05, y + 0.1), "#C9962B", w * 0.5))
    g.add(rect(-0.25, 1.1, 0.7, 1.16, "#F2C14E", w), rect(-0.3, 1.0, -0.15, 1.1, "#6E747A", w * 0.6),
          line((0.6, 1.1), (0.6, 0.6), "#3A3631", w * 0.6), poly([(0.57, 0.6), (0.63, 0.6), (0.6, 0.55)], "#3A3631", w * 0.5))
    return g, None


# -- trade and travel (more) ------------------------------------------------------------------------------------------

def _shoppingcart(m, w):
    g = VGroup(poly([(-0.2, 0.1), (0.2, 0.1), (0.26, 0.32), (-0.24, 0.32)], "#FFFFFF", w).set_fill(opacity=0).set_stroke("#6E747A", w * 1.4),
               *(line((x, 0.1), (x * 1.15, 0.32), "#9AA3A9", w * 0.6) for x in (-0.1, 0.0, 0.1)),
               line((-0.22, 0.21), (0.23, 0.21), "#9AA3A9", w * 0.6), line((0.26, 0.32), (0.34, 0.4), "#6E747A", w * 1.4),
               circ(-0.15, 0.03, 0.03, "#3A3631", w * 0.5), circ(0.15, 0.03, 0.03, "#3A3631", w * 0.5))
    if not m.get("empty"):
        g.add(*(circ(x, 0.33, 0.05, c, w * 0.5) for x, c in ((-0.12, "#D63B2F"), (0.0, "#F2C14E"), (0.12, "#7BB04B"))))
    return g, None


def _pricetag(m, w):
    return VGroup(poly([(-0.14, 0.0), (0.12, 0.0), (0.2, 0.08), (0.12, 0.16), (-0.14, 0.16)], "#F2C14E", w),
                  circ(0.13, 0.08, 0.018, "#F3EADA", w * 0.5), letters(str(m.get("sign") or "₹99"), -0.03, 0.08, 0.07, "#3A3631"),
                  stroke([(0.13, 0.08), (0.2, 0.18), (0.16, 0.26)], "#3A3631", w * 0.6)), None


def _cashregister(m, w):
    return VGroup(rect(-0.22, 0.0, 0.22, 0.1, "#3A3631", w), poly([(-0.2, 0.1), (0.2, 0.1), (0.16, 0.26), (-0.18, 0.26)], "#6E747A", w),
                  *(circ(-0.12 + (i % 4) * 0.07, 0.14 + (i // 4) * 0.05, 0.015, "#F3EADA", 0) for i in range(8)),
                  rect(0.04, 0.26, 0.18, 0.36, "#3A3631", w), rect(0.06, 0.28, 0.16, 0.34, "#9FE3A0", w * 0.4),
                  rect(-0.18, 0.02, 0.18, 0.08, GOLD_D, w * 0.5)), None


def _atm(m, w):
    return VGroup(rrect(-0.2, 0.0, 0.2, 0.75, 0.03, "#2F3B4C", w), rect(-0.14, 0.45, 0.14, 0.65, "#9FC5DA", w * 0.6),
                  *(rect(-0.1 + (i % 3) * 0.07, 0.25 + (i // 3) * 0.05, -0.05 + (i % 3) * 0.07, 0.28 + (i // 3) * 0.05, "#F3EADA", 0) for i in range(9)),
                  rect(-0.12, 0.12, 0.12, 0.15, "#1D1C1A", 0), letters("ATM", 0.0, 0.7, 0.04, "#F7F5F0"),
                  rect(-0.07, 0.15, 0.07, 0.2, "#7FB27F", w * 0.4)), None


def _suitcase(m, w):
    c = col(m["color"]) if m.get("color") else "#8E5A3C"
    return VGroup(stroke(zoo.P._arc(0.0, 0.4, 0.06, 0, 180, 8), "#3A2A1E", w * 2), rrect(-0.24, 0.02, 0.24, 0.4, 0.04, c, w),
                  *(line((x, 0.02), (x, 0.4), tint(c, -0.25), w * 1.2) for x in (-0.14, 0.14)),
                  circ(-0.18, 0.0, 0.025, "#3A3631", 0), circ(0.18, 0.0, 0.025, "#3A3631", 0),
                  rect(-0.08, 0.25, 0.02, 0.3, "#F3EADA", w * 0.4)), None


def _backpack(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    return VGroup(rrect(-0.15, 0.0, 0.15, 0.4, 0.07, c, w), rrect(-0.11, 0.04, 0.11, 0.2, 0.04, tint(c, -0.12), w * 0.8),
                  stroke(zoo.P._arc(0.0, 0.4, 0.06, 0, 180, 8), tint(c, -0.3), w * 1.6),
                  line((-0.11, 0.2), (0.11, 0.2), GOLD, w * 0.8), rect(-0.02, 0.15, 0.02, 0.2, GOLD, 0)), None


# -- a home's things ---------------------------------------------------------------------------------------------

def _sofa(m, w):
    c = col(m["color"]) if m.get("color") else "#2E6E9E"
    return VGroup(rrect(-0.45, 0.06, 0.45, 0.45, 0.06, tint(c, -0.1), w), rrect(-0.5, 0.06, -0.36, 0.3, 0.05, c, w),
                  rrect(0.36, 0.06, 0.5, 0.3, 0.05, c, w), rrect(-0.36, 0.14, 0.0, 0.26, 0.04, c, w), rrect(0.0, 0.14, 0.36, 0.26, 0.04, c, w),
                  *(rect(x, 0.0, x + 0.04, 0.06, WOOD_D, w * 0.6) for x in (-0.44, 0.4))), None


def _tablelamp(m, w):
    return VGroup(ell(0.0, 0.015, 0.2, 0.04, GOLD_D, w), line((0.0, 0.02), (0.0, 0.3), GOLD_D, w * 1.6),
                  poly([(-0.14, 0.3), (0.14, 0.3), (0.08, 0.48), (-0.08, 0.48)], "#F7E9B0", w),
                  live(blob([(-0.12, 0.3), (0.12, 0.3), (0.2, 0.08), (-0.2, 0.08)], "#FBE7A1", 0).set_fill(opacity=0.25), "puff")), None


def _mirror(m, w):
    return VGroup(ell(0.0, 0.45, 0.42, 0.62, GOLD_D, w), ell(0.0, 0.45, 0.34, 0.54, "#CFE3EC", w * 0.6),
                  stroke([(-0.08, 0.6), (0.06, 0.4)], "#FFFFFF", w * 1.4), stroke([(0.0, 0.66), (0.08, 0.56)], "#FFFFFF", w),
                  rect(-0.12, 0.0, 0.12, 0.04, WOOD_D, w), line((0.0, 0.04), (0.0, 0.14), WOOD_D, w * 2)), None


def _door(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(rect(-0.25, 0.0, 0.25, 0.9, tint(c, -0.2), w), rect(-0.21, 0.0, 0.21, 0.86, c, w),
                  rect(-0.16, 0.5, 0.16, 0.8, tint(c, 0.08), w * 0.6), rect(-0.16, 0.08, 0.16, 0.42, tint(c, 0.08), w * 0.6),
                  circ(0.15, 0.45, 0.022, GOLD, w * 0.5)), None


def _window(m, w):
    return VGroup(rect(-0.3, 0.0, 0.3, 0.5, "#F3EEE4", w), rect(-0.26, 0.04, 0.26, 0.46, "#9FC5DA", w * 0.6),
                  line((0.0, 0.04), (0.0, 0.46), "#F3EEE4", w * 2), line((-0.26, 0.25), (0.26, 0.25), "#F3EEE4", w * 2),
                  stroke([(-0.2, 0.4), (-0.12, 0.3)], "#FFFFFF", w), rect(-0.34, -0.03, 0.34, 0.0, "#E2D3B0", w * 0.6)), None


def _stairs(m, w):
    c = col(m["color"]) if m.get("color") else "#C9BFA8"
    g = VGroup()
    for i in range(6):
        g.add(rect(-0.45 + i * 0.15, 0.0, 0.45, 0.12 * (i + 1), tint(c, -0.04 * (i % 2)), w))
    return g, None


def _kettle(m, w):
    c = col(m["color"]) if m.get("color") else "#B8BEC2"
    return VGroup(blob([(-0.12, 0.0), (-0.15, 0.12), (-0.08, 0.2), (0.08, 0.2), (0.15, 0.12), (0.12, 0.0)], c, w),
                  tube([(0.12, 0.08), (0.2, 0.14), (0.25, 0.2)], [0.04, 0.03, 0.02], c, w * 0.8),
                  stroke(zoo.P._arc(0.0, 0.2, 0.1, 10, 170, 10), "#3A3631", w * 1.6), circ(0.0, 0.21, 0.02, "#3A3631", 0),
                  live(stroke([(0.26, 0.22), (0.24, 0.3), (0.28, 0.38)], "#C9C2B2", w), "steam")), None


def _pan(m, w):
    return VGroup(ell(0.0, 0.05, 0.4, 0.1, "#3A3631", w), ell(0.0, 0.065, 0.32, 0.06, "#5A5F63", w * 0.4),
                  line((0.2, 0.06), (0.45, 0.1), "#3A3631", w * 2.6),
                  *(ell(x, 0.07, 0.08, 0.04, c, w * 0.4) for x, c in ((-0.06, "#F7F3E8"), (0.06, "#F2C14E")) if m.get("of"))), None


def _plate(m, w):
    g = VGroup(ell(0.0, 0.03, 0.44, 0.08, "#F7F5F0", w), ell(0.0, 0.035, 0.3, 0.05, "#ECE6DA", w * 0.4))
    if str(m.get("of") or "") in ("food", "fruit", "bread"):
        g.add(*(circ(x, 0.07, 0.04, c, w * 0.5) for x, c in ((-0.06, "#D63B2F"), (0.04, "#F2C14E"), (0.0, "#7BB04B"))))
    return g, None


def _bottle(m, w):
    c = col(m["color"]) if m.get("color") else "#5BB06B"
    return VGroup(blob([(-0.06, 0.0), (-0.06, 0.22), (-0.025, 0.28), (-0.025, 0.36), (0.025, 0.36), (0.025, 0.28), (0.06, 0.22), (0.06, 0.0)],
                       c, w).set_fill(opacity=0.85), rect(-0.03, 0.36, 0.03, 0.4, "#8C6E52", w * 0.6),
                  rect(-0.06, 0.08, 0.06, 0.16, "#F3EADA", w * 0.5), stroke([(-0.035, 0.03), (-0.035, 0.2)], "#FFFFFF", w)), None


def _jug(m, w):
    c = col(m["color"]) if m.get("color") else "#C97B4A"
    return VGroup(blob([(-0.08, 0.0), (-0.12, 0.14), (-0.08, 0.26), (0.06, 0.28), (0.12, 0.3), (0.1, 0.22), (0.12, 0.12), (0.08, 0.0)], c, w),
                  stroke(zoo.P._arc(-0.12, 0.16, 0.06, 90, 270, 8), c, w * 2.4), stroke([(-0.1, 0.14), (0.11, 0.14)], "#F3EADA", w)), None


def _mailbox(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(line((0.0, 0.0), (0.0, 0.4), WOOD_D, w * 2.4), blob([(-0.2, 0.4), (-0.2, 0.55), (-0.1, 0.62), (0.2, 0.62), (0.2, 0.4)], c, w),
                  line((0.17, 0.58), (0.17, 0.72), "#3A3631", w), poly([(0.17, 0.72), (0.27, 0.69), (0.17, 0.66)], GOLD, w * 0.5),
                  rect(-0.16, 0.48, -0.04, 0.5, "#3A3631", 0)), None


def _fan(m, w):
    g = VGroup(ell(0.0, 0.015, 0.22, 0.04, "#3A3631", w), line((0.0, 0.02), (0.0, 0.3), "#3A3631", w * 2),
               circ(0.0, 0.42, 0.14, "#FFFFFF", w).set_fill(opacity=0.0))
    for a in (90, 210, 330):
        r = math.radians(a)
        g.add(live(blob([(0.0, 0.42), (0.12 * math.cos(r - 0.4), 0.42 + 0.12 * math.sin(r - 0.4)),
                         (0.12 * math.cos(r + 0.4), 0.42 + 0.12 * math.sin(r + 0.4))], "#9FC5DA", w * 0.6), "spin", (0.0, 0.42)))
    g.add(circ(0.0, 0.42, 0.025, "#3A3631", 0))
    return g, None


def _fridge(m, w):
    c = col(m["color"]) if m.get("color") else "#ECE6DA"
    return VGroup(rrect(-0.2, 0.0, 0.2, 0.95, 0.04, c, w), line((-0.2, 0.62), (0.2, 0.62), tint(c, -0.2), w),
                  line((0.14, 0.7), (0.14, 0.85), "#9AA3A9", w * 2), line((0.14, 0.35), (0.14, 0.55), "#9AA3A9", w * 2),
                  rect(-0.12, 0.75, 0.0, 0.85, "#E4572E", w * 0.4)), None


def _shoe(m, w):
    c = col(m["color"]) if m.get("color") else "#6B4226"
    return VGroup(blob([(-0.18, 0.02), (-0.18, 0.14), (-0.06, 0.15), (0.02, 0.1), (0.18, 0.06), (0.2, 0.02)], c, w),
                  rect(-0.18, 0.0, 0.2, 0.025, "#2B2622", w * 0.6), *(line((-0.05 + i * 0.03, 0.13), (-0.02 + i * 0.03, 0.09), "#F3EADA", w * 0.5) for i in range(3))), None


def _shirt(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    return VGroup(poly([(-0.12, 0.0), (0.12, 0.0), (0.12, 0.28), (0.24, 0.24), (0.28, 0.32), (0.12, 0.42), (0.05, 0.42), (0.0, 0.38),
                        (-0.05, 0.42), (-0.12, 0.42), (-0.28, 0.32), (-0.24, 0.24), (-0.12, 0.28)], c, w),
                  poly([(-0.05, 0.42), (0.0, 0.34), (0.05, 0.42)], tint(c, 0.3), w * 0.5),
                  *(circ(0.0, y, 0.01, "#F7F5F0", 0) for y in (0.1, 0.18, 0.26))), None


# -- weather and nature (more) ---------------------------------------------------------------------------------------

def _pinetree(m, w):
    c = col(m["color"]) if m.get("color") else "#2E5E3A"
    return VGroup(rect(-0.04, 0.0, 0.04, 0.15, "#6B4A2F", w), *(poly([(-0.28 + i * 0.05, 0.12 + i * 0.22), (0.28 - i * 0.05, 0.12 + i * 0.22),
                                                                      (0.0, 0.42 + i * 0.22)], tint(c, 0.06 * i), w) for i in range(3))), None


def _wave(m, w):
    g = VGroup(blob([(-0.5, 0.0), (-0.5, 0.15), (-0.3, 0.3), (-0.05, 0.42), (0.12, 0.38), (0.05, 0.28), (0.15, 0.22), (0.3, 0.1), (0.5, 0.06), (0.5, 0.0)],
                    "#3E7CB1", w),
               stroke([(-0.05, 0.42), (0.12, 0.38), (0.05, 0.28), (0.15, 0.22)], "#F7F5F0", w * 1.6),
               stroke([(-0.4, 0.08), (-0.2, 0.14), (0.0, 0.1)], "#9FC5DA", w))
    return g, None


def _raincloud(m, w):
    g, _ = _cloud({"color": "#9AA3A9"}, w)
    g.shift([0, 0.3, 0])
    g.add(*(live(line((x, 0.22 - (i % 2) * 0.05), (x - 0.03, 0.1 - (i % 2) * 0.05), "#3E7CB1", w * 1.4), "steam") for i, x in enumerate(np.linspace(-0.15, 0.15, 5))))
    return g, None


def _lightning(m, w):
    return VGroup(poly([(0.0, 0.6), (0.14, 0.6), (0.05, 0.36), (0.14, 0.36), (-0.06, 0.0), (0.0, 0.28), (-0.1, 0.28)], "#F2C14E", w)), None


def _snowflake(m, w):
    g = VGroup()
    for a in np.linspace(0, math.pi, 4)[:-1]:
        ca, sa = math.cos(a), math.sin(a)
        g.add(line((-0.15 * ca, 0.2 - 0.15 * sa), (0.15 * ca, 0.2 + 0.15 * sa), "#7FB4D6", w * 1.4))
        for s in (-1, 1):
            p = (s * 0.1 * ca, 0.2 + s * 0.1 * sa)
            g.add(line(p, (p[0] + 0.04 * math.cos(a + s * 0.8 + (0 if s > 0 else math.pi)), p[1] + 0.04 * math.sin(a + s * 0.8 + (0 if s > 0 else math.pi))), "#7FB4D6", w))
    return g, None


def _star(m, w):
    c = col(m["color"]) if m.get("color") else GOLD
    pts = [(0.15 * (1 if i % 2 == 0 else 0.42) * math.cos(math.pi / 2 + i * math.pi / 5),
            0.15 + 0.15 * (1 if i % 2 == 0 else 0.42) * math.sin(math.pi / 2 + i * math.pi / 5)) for i in range(10)]
    return VGroup(poly(pts, c, w), glint(0.04, 0.2, 0.02, w)), None


def _rainbow(m, w):
    g = VGroup()
    for i, c in enumerate(("#E4572E", "#F2A93B", "#F2C14E", "#7BB04B", "#3E7CB1", "#6B4FA0")):
        g.add(stroke(zoo.P._arc(0.0, 0.0, 0.5 - i * 0.05, 0, 180, 30), c, w * 2.4))
    return g, None


def _volcano(m, w):
    return VGroup(poly([(-0.6, 0.0), (-0.14, 0.55), (0.14, 0.55), (0.6, 0.0)], "#6E5A4A", w),
                  poly([(-0.14, 0.55), (-0.06, 0.4), (0.0, 0.5), (0.06, 0.38), (0.14, 0.55)], "#E4572E", w * 0.6),
                  poly([(-0.05, 0.42), (-0.15, 0.1), (-0.08, 0.25), (0.0, 0.05), (0.03, 0.3)], "#F2A93B", 0),
                  *(live(circ(x, y, r, "#8C8A86", w * 0.5), "puff") for x, y, r in ((0.0, 0.66, 0.08), (0.1, 0.78, 0.1), (-0.05, 0.9, 0.12)))), None


def _island(m, w):
    g = VGroup(ell(0.0, 0.03, 1.0, 0.1, "#9FC5DA", w * 0.6), blob([(-0.35, 0.03), (-0.2, 0.12), (0.2, 0.13), (0.35, 0.03)], "#E8D19A", w))
    p, _ = _palm({}, w)
    p.scale(0.6, about_point=np.array([0.0, 0.0, 0.0])).shift([0.05, 0.1, 0])
    g.add(p)
    return g, None


def _leaf(m, w):
    c = col(m["color"]) if m.get("color") else "#5B8C3A"
    return VGroup(blob([(0.0, 0.0), (-0.12, 0.15), (-0.08, 0.35), (0.0, 0.42), (0.08, 0.35), (0.12, 0.15)], c, w),
                  stroke([(0.0, 0.0), (0.0, 0.4)], tint(c, -0.3), w), *(stroke([(0.0, y), (s * 0.07, y + 0.06)], tint(c, -0.3), w * 0.6)
                                                                        for y in (0.12, 0.22) for s in (-1, 1))), None


def _sprout(m, w):
    return VGroup(ell(0.0, 0.02, 0.3, 0.06, "#8C6E52", w), stroke([(0.0, 0.03), (0.0, 0.2)], "#5B8C3A", w * 1.6),
                  blob([(0.0, 0.18), (-0.12, 0.26), (-0.04, 0.2)], "#7BB04B", w * 0.6), blob([(0.0, 0.2), (0.12, 0.3), (0.05, 0.21)], "#7BB04B", w * 0.6)), None


def _beehive(m, w):
    g = VGroup(line((0.0, 0.5), (0.0, 0.62), WOOD_D, w * 1.2))
    for i, (wd, y) in enumerate(((0.16, 0.42), (0.22, 0.32), (0.24, 0.2), (0.2, 0.09))):
        g.add(ell(0.0, y, wd * 2, 0.13, "#E2B65A", w))
    bees = [VGroup(ell(x, y, 0.05, 0.03, GOLD, w * 0.4), line((x - 0.02, y), (x + 0.02, y), "#22201E", w * 0.6))
            for x, y in ((0.3, 0.4), (-0.28, 0.3))]
    g.add(ell(0.0, 0.12, 0.08, 0.06, "#3A2A1E", 0), *bees)
    return g, None


def _nest(m, w):
    return VGroup(*(ell(x, 0.13, 0.08, 0.1, "#F3EEE4", w * 0.6) for x in (-0.05, 0.05, 0.0)),
                  blob([(-0.25, 0.12), (-0.2, 0.02), (0.0, 0.0), (0.2, 0.02), (0.25, 0.12), (0.0, 0.08)], "#8C6E52", w),
                  *(stroke([(-0.22 + i * 0.06, 0.03), (-0.16 + i * 0.06, 0.12)], "#6B4A2F", w * 0.6) for i in range(8))), None


def _logs(m, w):
    g = VGroup()
    for r, n in ((0, 3), (1, 2), (2, 1)):
        for i in range(n):
            x, y = -0.12 * (n - 1) + i * 0.24, 0.1 + r * 0.17
            g.add(circ(x, y, 0.1, "#9A6B43", w), circ(x, y, 0.06, "#C9A066", w * 0.4), circ(x, y, 0.02, "#9A6B43", 0))
    return g, None


# -- care and learning (more) -----------------------------------------------------------------------------------------

def _mask(m, w):
    return VGroup(blob([(-0.18, 0.08), (-0.16, 0.2), (0.0, 0.24), (0.16, 0.2), (0.18, 0.08), (0.0, 0.03)], "#9FD3F0", w),
                  *(stroke([(-0.13, y), (0.13, y)], "#7FB4D6", w * 0.6) for y in (0.1, 0.15, 0.19)),
                  stroke([(-0.18, 0.16), (-0.27, 0.18), (-0.25, 0.08), (-0.18, 0.1)], "#F3EEE4", w),
                  stroke([(0.18, 0.16), (0.27, 0.18), (0.25, 0.08), (0.18, 0.1)], "#F3EEE4", w)), None


def _thermometer(m, w):
    level = float(m.get("of") or 0.7) if str(m.get("of") or "").replace(".", "").isdigit() else 0.7
    return VGroup(rrect(-0.03, 0.06, 0.03, 0.5, 0.03, "#F7F5F0", w), circ(0.0, 0.06, 0.06, RED, w),
                  rect(-0.012, 0.06, 0.012, 0.06 + 0.42 * level, RED, 0),
                  *(line((0.03, y), (0.06, y), "#3A3631", w * 0.5) for y in np.linspace(0.12, 0.46, 7))), None


def _heart(m, w):
    c = col(m["color"]) if m.get("color") else "#D63B2F"
    return VGroup(blob([(0.0, 0.0), (-0.18, 0.16), (-0.17, 0.28), (-0.08, 0.32), (0.0, 0.25), (0.08, 0.32), (0.17, 0.28), (0.18, 0.16)], c, w),
                  stroke([(-0.12, 0.25), (-0.1, 0.18)], "#FFFFFF", w * 1.2)), None


def _gradcap(m, w):
    return VGroup(blob(zoo.P._arc(0.0, 0.06, 0.15, 180, 360, 10) + [(0.15, 0.12), (-0.15, 0.12)], "#22201E", w),
                  poly([(-0.3, 0.14), (0.0, 0.24), (0.3, 0.14), (0.0, 0.04)], "#22201E", w),
                  stroke([(0.0, 0.14), (0.2, 0.14), (0.22, 0.0)], GOLD, w * 1.2), poly([(0.2, 0.02), (0.24, 0.02), (0.22, -0.04)], GOLD, w * 0.5)), None


def _diploma(m, w):
    return VGroup(rrect(-0.25, 0.0, 0.25, 0.1, 0.05, PAPER, w), circ(-0.25, 0.05, 0.05, "#EFE1BE", w),
                  rect(-0.03, 0.0, 0.03, 0.1, RED, w * 0.5), poly([(-0.02, 0.0), (-0.05, -0.08), (0.0, -0.05), (0.05, -0.08), (0.02, 0.0)], RED, w * 0.5)), None


# -- tools ---------------------------------------------------------------------------------------------------------

def _hammer(m, w):
    return VGroup(rrect(-0.02, 0.0, 0.02, 0.3, 0.01, WOOD, w), rrect(-0.09, 0.27, 0.08, 0.34, 0.015, IRON, w),
                  poly([(-0.09, 0.28), (-0.12, 0.3), (-0.09, 0.33)], IRON, w * 0.6)), None


def _saw(m, w):
    teeth = [(0.36 - i * 0.04, 0.06 - (i % 2) * 0.025) for i in range(14)]
    return VGroup(poly([(-0.18, 0.18), (0.36, 0.12), *teeth], "#C9CED2", w),
                  blob([(-0.34, 0.04), (-0.34, 0.2), (-0.16, 0.2), (-0.16, 0.04)], WOOD, w),
                  ell(-0.25, 0.12, 0.09, 0.06, "#F4EFE4", w * 0.6)), None


def _wrench(m, w):
    return VGroup(rrect(-0.025, 0.04, 0.025, 0.3, 0.02, IRON, w),
                  blob([(-0.06, 0.3), (-0.07, 0.36), (-0.03, 0.4), (-0.02, 0.34), (0.02, 0.34), (0.03, 0.4), (0.07, 0.36), (0.06, 0.3)], IRON, w),
                  circ(0.0, 0.05, 0.04, IRON, w), circ(0.0, 0.05, 0.018, "#F4EFE4", w * 0.5)), None


def _screwdriver(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(rrect(-0.035, 0.0, 0.035, 0.14, 0.02, c, w), line((0.0, 0.14), (0.0, 0.32), IRON, w * 2.4),
                  *(line((x, 0.02), (x, 0.12), tint(c, -0.3), w * 0.5) for x in (-0.012, 0.012))), None


def _shovel(m, w):
    return VGroup(line((0.0, 0.22), (0.0, 0.85), WOOD, w * 2.4), rrect(-0.06, 0.82, 0.06, 0.86, 0.02, WOOD_D, w * 0.8),
                  blob([(-0.09, 0.22), (-0.1, 0.08), (0.0, 0.0), (0.1, 0.08), (0.09, 0.22)], IRON, w)), None


def _pickaxe(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.62), WOOD, w * 2.4),
                  blob([(-0.3, 0.5), (-0.12, 0.6), (0.0, 0.63), (0.12, 0.6), (0.3, 0.5), (0.12, 0.56), (0.0, 0.58), (-0.12, 0.56)], IRON, w)), None


def _sickle(m, w):
    return VGroup(rrect(-0.025, 0.0, 0.025, 0.14, 0.015, WOOD, w),
                  blob([(0.0, 0.14), *zoo.P._arc(0.12, 0.26, 0.16, 215, -40, 16), (0.2, 0.18), *zoo.P._arc(0.12, 0.28, 0.12, -30, 200, 14)],
                       "#C9CED2", w)), None


def _hoe(m, w):
    return VGroup(line((-0.05, 0.0), (0.05, 0.8), WOOD, w * 2.4),
                  poly([(0.04, 0.78), (0.18, 0.74), (0.2, 0.62), (0.15, 0.64), (0.04, 0.72)], IRON, w)), None


def _pitchfork(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.62), WOOD, w * 2.4), stroke([(-0.08, 0.82), (-0.08, 0.64), (0.08, 0.64), (0.08, 0.82)], IRON, w * 1.6),
                  line((0.0, 0.62), (0.0, 0.84), IRON, w * 1.6)), None


def _wateringcan(m, w):
    c = col(m["color"]) if m.get("color") else "#4F9A6A"
    return VGroup(tube([(0.1, 0.06), (0.22, 0.16), (0.3, 0.24)], [0.04, 0.03, 0.025], c, w * 0.8),
                  rrect(-0.14, 0.0, 0.12, 0.2, 0.03, c, w), ell(0.31, 0.25, 0.04, 0.06, tint(c, -0.2), w * 0.6),
                  stroke(zoo.P._arc(-0.03, 0.2, 0.08, 0, 180, 10), tint(c, -0.3), w * 1.8)), None


def _wheelbarrow(m, w):
    c = col(m["color"]) if m.get("color") else "#C2552B"
    g = VGroup(line((-0.12, 0.12), (-0.45, 0.3), WOOD_D, w * 1.8), line((-0.1, 0.1), (-0.14, 0.0), WOOD_D, w * 1.6),
               poly([(-0.25, 0.32), (0.22, 0.32), (0.12, 0.14), (-0.12, 0.14)], c, w),
               line((-0.25, 0.32), (0.22, 0.32), tint(c, -0.3), w * 1.4))
    g.add(*wheelset((0.16,), 0.07, w))
    return g, None


def _toolbox(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(rrect(-0.2, 0.0, 0.2, 0.16, 0.02, c, w), rect(-0.2, 0.12, 0.2, 0.16, tint(c, -0.2), w * 0.6),
                  stroke([(-0.07, 0.16), (-0.06, 0.22), (0.06, 0.22), (0.07, 0.16)], "#3A3631", w * 1.6),
                  rect(-0.03, 0.08, 0.03, 0.11, "#C9CED2", w * 0.5)), None


def _scissors(m, w):
    return VGroup(poly([(-0.02, 0.12), (0.24, 0.22), (0.01, 0.15)], "#C9CED2", w), poly([(-0.02, 0.12), (0.24, 0.04), (0.01, 0.09)], "#C9CED2", w),
                  Circle(radius=0.045, stroke_color=RED, stroke_width=w * 2).move_to([-0.08, 0.17, 0]),
                  Circle(radius=0.045, stroke_color=RED, stroke_width=w * 2).move_to([-0.08, 0.06, 0]),
                  circ(0.0, 0.12, 0.012, "#3A3631", 0)), None


def _paintbrush(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    return VGroup(line((0.0, 0.0), (0.0, 0.22), WOOD, w * 2.2), rect(-0.02, 0.22, 0.02, 0.27, "#C9CED2", w * 0.6),
                  blob([(-0.025, 0.27), (-0.02, 0.33), (0.0, 0.37), (0.02, 0.33), (0.025, 0.27)], c, w * 0.6)), None


def _easel(m, w):
    return VGroup(line((-0.18, 0.0), (0.0, 0.85), WOOD, w * 1.8), line((0.18, 0.0), (0.0, 0.85), WOOD, w * 1.8),
                  line((0.0, 0.0), (0.0, 0.8), WOOD_D, w * 1.4), rect(-0.2, 0.3, 0.2, 0.33, WOOD_D, w * 0.6),
                  rect(-0.22, 0.33, 0.22, 0.75, "#FBF8F1", w),
                  blob([(-0.15, 0.4), (-0.05, 0.55), (0.03, 0.47), (0.15, 0.62), (0.15, 0.4)], "#7FB77E", w * 0.4),
                  circ(-0.1, 0.65, 0.035, "#F2C14E", 0)), None


# -- food ----------------------------------------------------------------------------------------------------------

def _cake(m, w):
    c = col(m["color"]) if m.get("color") else "#F2B8C6"
    g = VGroup(ell(0.0, 0.01, 0.4, 0.05, "#E8E0CC", w * 0.6), rect(-0.16, 0.02, 0.16, 0.12, "#F7E1B5", w),
               rect(-0.12, 0.12, 0.12, 0.2, "#F7E1B5", w),
               stroke([(-0.16, 0.12), (-0.12, 0.1), (-0.06, 0.12), (0.0, 0.1), (0.06, 0.12), (0.12, 0.1), (0.16, 0.12)], c, w * 2.4),
               stroke([(-0.12, 0.2), (-0.06, 0.18), (0.0, 0.2), (0.06, 0.18), (0.12, 0.2)], c, w * 2.4))
    for x in (-0.05, 0.05):
        g.add(rect(x - 0.01, 0.2, x + 0.01, 0.26, "#9FC5DA", w * 0.4),
              live(blob([(x, 0.26), (x - 0.012, 0.28), (x, 0.31), (x + 0.012, 0.28)], "#F2A93B", 0), "flame"))
    return g, None


def _pizza(m, w):
    g = VGroup(circ(0.0, 0.0, 0.22, "#E2B65A", w), circ(0.0, 0.0, 0.18, "#F2D27A", w * 0.4))
    for x, y in ((-0.08, 0.06), (0.07, 0.08), (0.0, -0.06), (-0.1, -0.07), (0.1, -0.04)):
        g.add(circ(x, y, 0.03, "#C2552B", w * 0.4))
    for a in (30, 90, 150, 210, 270, 330):
        r = math.radians(a)
        g.add(line((0.0, 0.0), (0.18 * math.cos(r), 0.18 * math.sin(r)), "#C9962B", w * 0.4))
    g.shift([0.0, 0.22, 0])
    return g, None


def _egg(m, w):
    return VGroup(blob([(0.0, 0.0), (0.06, 0.03), (0.07, 0.1), (0.04, 0.17), (0.0, 0.19), (-0.04, 0.17), (-0.07, 0.1), (-0.06, 0.03)],
                       "#F7F1E3", w), stroke([(-0.03, 0.13), (-0.02, 0.15)], "#FFFFFF", w * 1.4)), None


def _carrot(m, w):
    return VGroup(blob([(-0.04, 0.3), (0.04, 0.3), (0.0, 0.0)], "#E8822E", w),
                  *(line((-0.02 + i * 0.012, 0.22 - i * 0.05), (0.02 + i * 0.004, 0.22 - i * 0.05), "#B85F1E", w * 0.6) for i in range(3)),
                  *(tube([(0.0, 0.3), (x, 0.42)], [0.025, 0.012], "#4F9A6A", w * 0.5) for x in (-0.05, 0.0, 0.05))), None


def _tomato(m, w):
    return VGroup(blob([(-0.12, 0.1), (-0.1, 0.02), (0.0, 0.0), (0.1, 0.02), (0.12, 0.1), (0.08, 0.18), (0.0, 0.19), (-0.08, 0.18)], "#D6402B", w),
                  poly([(-0.05, 0.19), (0.0, 0.17), (0.05, 0.19), (0.02, 0.2), (0.0, 0.23), (-0.02, 0.2)], "#4F9A6A", w * 0.5),
                  stroke([(-0.07, 0.13), (-0.05, 0.16)], "#F7B4A6", w * 1.4)), None


def _onion(m, w):
    return VGroup(blob([(0.0, 0.0), (0.1, 0.04), (0.12, 0.11), (0.06, 0.18), (0.02, 0.22), (0.0, 0.27), (-0.02, 0.22), (-0.06, 0.18),
                        (-0.12, 0.11), (-0.1, 0.04)], "#B5476B", w),
                  stroke([(-0.04, 0.03), (-0.07, 0.11), (-0.02, 0.2)], "#D88AA4", w * 0.6),
                  stroke([(0.04, 0.03), (0.06, 0.11), (0.02, 0.2)], "#D88AA4", w * 0.6)), None


def _chili(m, w):
    return VGroup(tube([(0.2, 0.12), (0.08, 0.08), (-0.08, 0.04), (-0.2, 0.02)], [0.07, 0.07, 0.05, 0.01], "#D6402B", w),
                  tube([(0.2, 0.12), (0.25, 0.16), (0.27, 0.22)], [0.04, 0.02, 0.015], "#4F9A6A", w * 0.6)), None


def _grapes(m, w):
    c = col(m["color"]) if m.get("color") else "#7A4C8C"
    g = VGroup(line((0.0, 0.36), (0.02, 0.44), WOOD_D, w * 1.4),
               blob([(0.02, 0.4), (0.12, 0.44), (0.16, 0.38), (0.06, 0.37)], "#4F9A6A", w * 0.6))
    for r, n in ((0.32, 4), (0.25, 3), (0.18, 3), (0.11, 2), (0.04, 1)):
        for i in range(n):
            g.add(circ((i - (n - 1) / 2) * 0.06, r, 0.035, c, w * 0.6))
    return g, None


def _watermelon(m, w):
    return VGroup(blob([*zoo.P._arc(0.0, 0.22, 0.28, 180, 360, 16)], "#3F7D3A", w),
                  blob([*zoo.P._arc(0.0, 0.22, 0.24, 180, 360, 16)], "#E8524A", w * 0.4),
                  line((-0.28, 0.22), (0.28, 0.22), zoo.INK, w),
                  *(ell(x, y, 0.016, 0.026, "#2B2826", 0) for x, y in ((-0.12, 0.14), (0.0, 0.08), (0.12, 0.14), (-0.05, 0.16), (0.07, 0.16)))), None


def _icecream(m, w):
    c = col(m["color"]) if m.get("color") else "#F2B8C6"
    return VGroup(poly([(-0.07, 0.18), (0.07, 0.18), (0.0, 0.0)], "#E2B65A", w),
                  *(line((-0.05 + i * 0.03, 0.18), (0.01 + i * 0.015, 0.04), "#C9962B", w * 0.4) for i in range(3)),
                  blob([(-0.08, 0.18), (-0.09, 0.24), (-0.04, 0.3), (0.0, 0.32), (0.05, 0.3), (0.09, 0.24), (0.08, 0.18)], c, w),
                  circ(0.0, 0.33, 0.018, RED, w * 0.4)), None


def _samosa(m, w):
    return VGroup(poly([(-0.16, 0.0), (0.16, 0.0), (0.0, 0.22)], "#D9A24A", w),
                  stroke([(-0.08, 0.02), (0.0, 0.18)], "#B5803A", w * 0.6), stroke([(0.05, 0.02), (0.03, 0.12)], "#B5803A", w * 0.4),
                  *(circ(x, y, 0.008, "#8A5A2B", 0) for x, y in ((-0.05, 0.06), (0.06, 0.05), (0.01, 0.11)))), None


def _laddoo(m, w):
    g = VGroup(ell(0.0, 0.01, 0.42, 0.06, "#E8E0CC", w * 0.6))
    for x, y in ((-0.11, 0.06), (0.0, 0.06), (0.11, 0.06), (-0.055, 0.15), (0.055, 0.15), (0.0, 0.24)):
        g.add(circ(x, y, 0.055, "#F2A93B", w * 0.7), *(circ(x + dx, y + dy, 0.005, "#C9782B", 0) for dx, dy in ((-0.02, 0.01), (0.015, -0.01), (0.0, 0.025))))
    return g, None


def _sugarcane(m, w):
    g = VGroup()
    for x, h in ((-0.05, 0.9), (0.04, 0.8)):
        g.add(rrect(x - 0.025, 0.0, x + 0.025, h, 0.02, "#C9B45A", w),
              *(line((x - 0.025, y), (x + 0.025, y), "#8A7A2B", w * 0.8) for y in np.arange(0.12, h, 0.14)),
              tube([(x, h), (x - 0.12, h + 0.12)], [0.04, 0.005], "#4F9A6A", w * 0.5),
              tube([(x, h), (x + 0.1, h + 0.14)], [0.04, 0.005], "#4F9A6A", w * 0.5))
    return g, None


def _teapot(m, w):
    c = col(m["color"]) if m.get("color") else "#F3EEE4"
    return VGroup(tube([(0.1, 0.06), (0.2, 0.12), (0.25, 0.2)], [0.05, 0.03, 0.02], c, w * 0.8),
                  stroke(zoo.P._arc(-0.14, 0.11, 0.06, 90, 270, 10), c, w * 3),
                  blob([(-0.14, 0.02), (-0.16, 0.11), (-0.1, 0.19), (0.1, 0.19), (0.16, 0.11), (0.14, 0.02), (0.0, 0.0)], c, w),
                  ell(0.0, 0.2, 0.16, 0.04, tint(c, -0.1), w * 0.6), circ(0.0, 0.23, 0.02, tint(c, -0.2), w * 0.5),
                  stroke([(-0.1, 0.1), (0.1, 0.1)], "#3E7CB1", w * 1.2),
                  live(stroke([(0.26, 0.22), (0.24, 0.3), (0.28, 0.36)], "#C9C2B2", w), "steam")), None


def _roti(m, w):
    g = VGroup(ell(0.0, 0.02, 0.4, 0.06, "#E8E0CC", w * 0.6))
    for i in range(3):
        g.add(ell(0.0, 0.04 + i * 0.015, 0.32, 0.06, "#E8C27E", w * 0.7))
    g.add(*(circ(x, 0.075, 0.01, "#B5803A", 0) for x in (-0.08, 0.02, 0.09)))
    return g, None


def _pressurecooker(m, w):
    return VGroup(rrect(-0.15, 0.0, 0.15, 0.2, 0.04, "#C9CED2", w), ell(0.0, 0.2, 0.32, 0.05, "#B8BEC2", w),
                  rrect(0.12, 0.2, 0.38, 0.24, 0.02, "#2B2826", w), rect(-0.02, 0.22, 0.02, 0.27, "#2B2826", w * 0.6),
                  ell(0.0, 0.28, 0.04, 0.02, "#2B2826", 0),
                  live(stroke([(0.0, 0.29), (-0.03, 0.36), (0.01, 0.43)], "#C9C2B2", w), "steam")), None


def _mortar(m, w):
    return VGroup(line((-0.02, 0.1), (0.14, 0.32), "#8E969C", w * 3.4),
                  blob([(-0.16, 0.16), (-0.12, 0.04), (0.0, 0.0), (0.12, 0.04), (0.16, 0.16)], "#9AA3A9", w),
                  ell(0.0, 0.16, 0.32, 0.05, "#6E747A", w * 0.8)), None


def _gascylinder(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(rrect(-0.11, 0.02, 0.11, 0.36, 0.08, c, w), rect(-0.1, 0.0, 0.1, 0.04, tint(c, -0.3), w * 0.6),
                  line((-0.11, 0.2), (0.11, 0.2), tint(c, -0.25), w * 0.6),
                  stroke([(-0.06, 0.36), (-0.06, 0.42), (0.06, 0.42), (0.06, 0.36)], "#6E747A", w * 1.8),
                  rect(-0.02, 0.36, 0.02, 0.41, "#C9CED2", w * 0.6)), None


# -- music, play, sport --------------------------------------------------------------------------------------------

def _guitar(m, w):
    c = col(m["color"]) if m.get("color") else "#C97A3A"
    return VGroup(blob([(0.0, 0.0), (0.1, 0.03), (0.11, 0.12), (0.07, 0.17), (0.09, 0.24), (0.06, 0.3), (0.0, 0.31),
                        (-0.06, 0.3), (-0.09, 0.24), (-0.07, 0.17), (-0.11, 0.12), (-0.1, 0.03)], c, w),
                  circ(0.0, 0.18, 0.035, "#3A2A1E", w * 0.5), rect(-0.05, 0.06, 0.05, 0.08, "#3A2A1E", w * 0.5),
                  rect(-0.018, 0.3, 0.018, 0.62, WOOD_D, w), rrect(-0.03, 0.6, 0.03, 0.68, 0.01, "#3A2A1E", w),
                  *(line((x, 0.07), (x, 0.62), "#E8E0CC", w * 0.3) for x in (-0.008, 0.008))), None


def _piano(m, w):
    g = VGroup(rect(-0.4, 0.0, 0.4, 0.62, "#2B2826", w), rect(-0.4, 0.3, 0.4, 0.38, "#FBF8F1", w * 0.6),
               *(rect(x, 0.0, x + 0.04, 0.3, "#3A3631", w * 0.6) for x in (-0.38, 0.34)))
    for i in range(16):
        g.add(line((-0.4 + i * 0.05, 0.3), (-0.4 + i * 0.05, 0.38), "#9AA3A9", w * 0.4))
    for i in (1, 2, 4, 5, 6, 8, 9, 11, 12, 13):
        x = -0.4 + i * 0.05
        g.add(rect(x - 0.012, 0.335, x + 0.012, 0.38, "#2B2826", 0))
    g.add(rect(-0.2, 0.44, 0.2, 0.52, "#FBF8F1", w * 0.5), scribble(-0.17, 0.17, 0.48, w * 0.5))
    return g, None


def _harmonium(m, w):
    g = VGroup(rect(-0.3, 0.0, 0.3, 0.16, WOOD, w), rect(-0.3, 0.16, 0.3, 0.2, "#FBF8F1", w * 0.6),
               *(line((-0.3 + i * 0.04, 0.16), (-0.3 + i * 0.04, 0.2), "#9AA3A9", w * 0.3) for i in range(15)),
               poly([(-0.3, 0.2), (0.3, 0.2), (0.24, 0.3), (-0.24, 0.3)], WOOD_D, w),
               *(circ(x, 0.08, 0.018, GOLD, w * 0.4) for x in (-0.2, -0.1, 0.0, 0.1, 0.2)))
    g.add(*(line((-0.34 - i * 0.012, 0.02), (-0.34 - i * 0.012, 0.14), "#6B4A2F", w * 0.8) for i in range(3)))
    return g, None


def _dhol(m, w):
    c = col(m["color"]) if m.get("color") else RED
    return VGroup(rrect(-0.24, 0.02, 0.24, 0.26, 0.1, c, w), ell(-0.24, 0.14, 0.08, 0.24, "#F3EADA", w), ell(0.24, 0.14, 0.08, 0.24, "#F3EADA", w),
                  *(line((-0.2 + i * 0.08, 0.04), (-0.16 + i * 0.08, 0.24), GOLD, w * 0.6) for i in range(5)),
                  stroke([(-0.18, 0.26), (0.0, 0.42), (0.18, 0.26)], "#3A3631", w * 1.2)), None


def _violin(m, w):
    return VGroup(blob([(0.0, 0.0), (0.08, 0.03), (0.08, 0.1), (0.05, 0.14), (0.07, 0.19), (0.05, 0.25), (0.0, 0.26),
                        (-0.05, 0.25), (-0.07, 0.19), (-0.05, 0.14), (-0.08, 0.1), (-0.08, 0.03)], "#A8582B", w),
                  stroke([(-0.03, 0.12), (-0.035, 0.16)], "#3A2A1E", w), stroke([(0.03, 0.12), (0.035, 0.16)], "#3A2A1E", w),
                  rect(-0.012, 0.25, 0.012, 0.42, "#2B2826", w * 0.8), stroke(zoo.P._arc(0.0, 0.44, 0.02, -90, 200, 8), WOOD_D, w * 1.6),
                  line((0.18, -0.02), (-0.14, 0.34), "#E8E0CC", w * 0.6), line((0.18, -0.02), (-0.14, 0.34), WOOD_D, w * 0.3)), None


def _headphones(m, w):
    c = col(m["color"]) if m.get("color") else "#3A3631"
    return VGroup(stroke(zoo.P._arc(0.0, 0.12, 0.13, 10, 170, 14), c, w * 3),
                  rrect(-0.17, 0.0, -0.1, 0.14, 0.03, c, w), rrect(0.1, 0.0, 0.17, 0.14, 0.03, c, w),
                  rrect(-0.15, 0.02, -0.12, 0.12, 0.015, tint(c, 0.4), 0), rrect(0.12, 0.02, 0.15, 0.12, 0.015, tint(c, 0.4), 0)), None


def _speaker(m, w):
    return VGroup(rrect(-0.12, 0.0, 0.12, 0.42, 0.02, "#3A3631", w), circ(0.0, 0.13, 0.08, "#6E747A", w), circ(0.0, 0.13, 0.03, "#2B2826", w * 0.6),
                  circ(0.0, 0.32, 0.045, "#6E747A", w), circ(0.0, 0.32, 0.015, "#2B2826", 0)), None


def _dice(m, w):
    g = VGroup(poly([(-0.1, 0.0), (0.06, 0.0), (0.06, 0.16), (-0.1, 0.16)], "#FBF8F1", w),
               poly([(-0.1, 0.16), (0.06, 0.16), (0.12, 0.21), (-0.04, 0.21)], "#E8E0CC", w),
               poly([(0.06, 0.0), (0.12, 0.05), (0.12, 0.21), (0.06, 0.16)], "#D6CDB8", w))
    g.add(*(circ(x, y, 0.014, RED, 0) for x, y in ((-0.06, 0.12), (-0.02, 0.08), (0.02, 0.04))),
          circ(0.04, 0.185, 0.012, "#2B2826", 0), circ(0.09, 0.08, 0.01, "#2B2826", 0), circ(0.09, 0.14, 0.01, "#2B2826", 0))
    return g, None


def _chessboard(m, w):
    g = VGroup(poly([(-0.32, 0.0), (0.32, 0.0), (0.24, 0.16), (-0.24, 0.16)], "#E8D9B5", w))

    def xs(y, k):
        half = 0.32 - 0.5 * y
        return -half + k * half / 4
    for i in range(4):
        for j in range(8):
            if (i + j) % 2:
                y0, y1 = i * 0.04, (i + 1) * 0.04
                g.add(poly([(xs(y0, j), y0), (xs(y0, j + 1), y0), (xs(y1, j + 1), y1), (xs(y1, j), y1)], "#6B4A2F", 0))
    g.add(rect(-0.32, -0.04, 0.32, 0.0, WOOD_D, w * 0.6))
    for x, c in ((-0.1, "#FBF8F1"), (0.12, "#2B2826")):
        g.add(blob([(x - 0.04, 0.1), (x - 0.025, 0.14), (x - 0.02, 0.22), (x, 0.27), (x + 0.02, 0.22), (x + 0.025, 0.14), (x + 0.04, 0.1)], c, w * 0.8),
              circ(x, 0.28, 0.02, c, w * 0.6))
    return g, None


def _playingcards(m, w):
    g = VGroup()
    for i, a in enumerate((-18, 0, 18)):
        c = rrect(-0.07, 0.0, 0.07, 0.2, 0.015, "#FBF8F1", w)
        sym = letters("♥♠♦"[i], 0.0, 0.1, 0.06, RED if i != 1 else "#2B2826")
        g.add(VGroup(c, sym).rotate(math.radians(-a), about_point=np.array([0.0, -0.05, 0.0])))
    return g, None


def _gamecontroller(m, w):
    return VGroup(blob([(-0.2, 0.02), (-0.22, 0.1), (-0.16, 0.16), (0.16, 0.16), (0.22, 0.1), (0.2, 0.02), (0.12, 0.03), (0.08, 0.07),
                        (-0.08, 0.07), (-0.12, 0.03)], "#3A3631", w),
                  rect(-0.14, 0.1, -0.08, 0.12, "#C9CED2", 0), rect(-0.12, 0.08, -0.1, 0.14, "#C9CED2", 0),
                  *(circ(x, y, 0.014, c, 0) for x, y, c in ((0.1, 0.13, RED), (0.13, 0.1, "#4F9A6A"), (0.07, 0.1, "#3E7CB1"), (0.1, 0.07, GOLD)))), None


def _racket(m, w):
    return VGroup(rrect(-0.02, 0.0, 0.02, 0.18, 0.01, "#3A3631", w), line((0.0, 0.18), (0.0, 0.26), "#9AA3A9", w * 1.4),
                  ell(0.0, 0.38, 0.2, 0.26, "#FBF8F1", w * 1.8).set_fill(opacity=0.0),
                  *(line((x, 0.38 - 0.12 * math.sqrt(max(0.0, 1 - (x / 0.1) ** 2))), (x, 0.38 + 0.12 * math.sqrt(max(0.0, 1 - (x / 0.1) ** 2))),
                         "#C9C2B2", w * 0.3) for x in np.linspace(-0.08, 0.08, 6)),
                  *(line((-0.1 * math.sqrt(max(0.0, 1 - ((y - 0.38) / 0.13) ** 2)), y), (0.1 * math.sqrt(max(0.0, 1 - ((y - 0.38) / 0.13) ** 2)), y),
                         "#C9C2B2", w * 0.3) for y in np.linspace(0.28, 0.48, 6)),
                  ell(0.0, 0.38, 0.2, 0.26, RED, w * 1.8).set_fill(opacity=0.0)), None


def _dumbbell(m, w):
    return VGroup(line((-0.18, 0.08), (0.18, 0.08), "#9AA3A9", w * 3),
                  *(rrect(x - 0.035, 0.0, x + 0.035, 0.16, 0.015, "#3A3631", w) for x in (-0.16, 0.16)),
                  *(rrect(x - 0.025, 0.02, x + 0.025, 0.14, 0.012, "#3A3631", w) for x in (-0.22, 0.22))), None


def _hockeystick(m, w):
    return VGroup(tube([(0.04, 0.85), (0.0, 0.2), (-0.02, 0.06), (-0.08, 0.02), (-0.18, 0.03)], [0.035, 0.035, 0.04, 0.045, 0.04], WOOD, w),
                  rect(0.015, 0.7, 0.055, 0.85, "#3A3631", w * 0.5), circ(0.1, 0.03, 0.03, "#FBF8F1", w * 0.7)), None


# -- tech ----------------------------------------------------------------------------------------------------------

def _printer(m, w):
    return VGroup(rect(-0.16, 0.22, 0.16, 0.32, "#FBF8F1", w * 0.6), scribble(-0.12, 0.1, 0.28, w * 0.4),
                  rrect(-0.25, 0.0, 0.25, 0.22, 0.03, "#C9CED2", w), rect(-0.18, 0.04, 0.18, 0.07, "#3A3631", w * 0.6),
                  circ(0.18, 0.16, 0.015, "#4F9A6A", 0), rect(-0.14, -0.02, 0.14, 0.04, "#FBF8F1", w * 0.5)), None


def _router(m, w):
    return VGroup(rrect(-0.2, 0.0, 0.2, 0.08, 0.03, "#3A3631", w),
                  *(line((x, 0.08), (x + 0.02 * (1 if x > 0 else -1), 0.3), "#3A3631", w * 2) for x in (-0.13, 0.13)),
                  *(circ(x, 0.04, 0.008, "#7FD18B", 0) for x in np.linspace(-0.12, 0.04, 5)),
                  *(stroke(zoo.P._arc(0.0, 0.14, r, 50, 130, 8), "#3E7CB1", w * 1.2) for r in (0.06, 0.11, 0.16))), None


def _satellitedish(m, w):
    return VGroup(line((0.0, 0.0), (0.04, 0.22), "#9AA3A9", w * 2.2), rect(-0.08, 0.0, 0.08, 0.03, "#6E747A", w * 0.6),
                  blob([*zoo.P._arc(0.05, 0.36, 0.2, 200, 340, 12), (0.24, 0.3), (-0.12, 0.28)], "#E8EBED", w).rotate(0.5, about_point=np.array([0.05, 0.3, 0])),
                  line((0.06, 0.28), (0.2, 0.45), "#6E747A", w), circ(0.2, 0.45, 0.018, "#6E747A", w * 0.5)), None


def _cctv(m, w):
    return VGroup(rect(-0.2, 0.3, -0.17, 0.5, "#9AA3A9", w * 0.6), line((-0.17, 0.4), (-0.08, 0.36), "#6E747A", w * 1.6),
                  poly([(-0.1, 0.32), (0.18, 0.28), (0.2, 0.36), (-0.08, 0.42)], "#F3EEE4", w),
                  ell(0.19, 0.32, 0.03, 0.06, "#2B2826", w * 0.6), circ(-0.02, 0.38, 0.01, RED, 0)), None


def _chip(m, w):
    g = VGroup(rrect(-0.14, 0.04, 0.14, 0.32, 0.02, "#2B2826", w), rect(-0.08, 0.1, 0.08, 0.26, "#3A3631", w * 0.5),
               circ(-0.1, 0.28, 0.012, "#6E747A", 0))
    for i in range(5):
        t = -0.1 + i * 0.05
        g.add(line((t, 0.04), (t, 0.0), "#C9A066", w * 1.2), line((t, 0.32), (t, 0.36), "#C9A066", w * 1.2),
              line((-0.14, 0.08 + i * 0.05), (-0.18, 0.08 + i * 0.05), "#C9A066", w * 1.2),
              line((0.14, 0.08 + i * 0.05), (0.18, 0.08 + i * 0.05), "#C9A066", w * 1.2))
    return g, None


def _tablet(m, w):
    return VGroup(rrect(-0.14, 0.0, 0.14, 0.38, 0.03, "#2B2826", w), rect(-0.12, 0.03, 0.12, 0.35, "#9FC5DA", 0),
                  *(rrect(-0.1 + c * 0.07, 0.24 - r * 0.08, -0.05 + c * 0.07, 0.29 - r * 0.08, 0.01, col_, 0)
                    for r in range(3) for c, col_ in enumerate(("#F2C14E", "#E8524A", "#4F9A6A")))), None


def _mobiletower(m, w):
    g = VGroup(line((-0.16, 0.0), (-0.03, 1.3), "#B8BEC2", w * 1.6), line((0.16, 0.0), (0.03, 1.3), "#B8BEC2", w * 1.6))
    for i in range(7):
        y0, y1 = i * 0.17, (i + 1) * 0.17
        a0, a1 = 0.16 - 0.1 * y0, 0.16 - 0.1 * y1
        g.add(line((-a0, y0), (a1, y1), "#B8BEC2", w * 0.6), line((a0, y0), (-a1, y1), "#B8BEC2", w * 0.6))
    g.add(*(rect(x - 0.025, 1.1, x + 0.025, 1.25, "#F3EEE4", w * 0.6) for x in (-0.07, 0.07)),
          circ(0.0, 1.32, 0.02, RED, w * 0.4),
          *(stroke(zoo.P._arc(0.0, 1.32, r, -40, 40, 6), "#3E7CB1", w) for r in (0.08, 0.14)),
          *(stroke(zoo.P._arc(0.0, 1.32, r, 140, 220, 6), "#3E7CB1", w) for r in (0.08, 0.14)))
    return g, None


def _plug(m, w):
    return VGroup(stroke([(0.0, 0.0), (-0.06, 0.06), (0.04, 0.12), (0.0, 0.18)], "#3A3631", w * 2),
                  rrect(-0.08, 0.18, 0.08, 0.34, 0.03, "#FBF8F1", w),
                  *(rect(x - 0.012, 0.34, x + 0.012, 0.44, "#C9A066", w * 0.6) for x in (-0.04, 0.04)),
                  rect(-0.012, 0.34, 0.012, 0.4, "#C9A066", w * 0.6)), None


# -- science -------------------------------------------------------------------------------------------------------

def _atom(m, w):
    g = VGroup()
    for a in (0, 60, 120):
        g.add(Ellipse(width=0.56, height=0.18, stroke_color="#3E7CB1", stroke_width=w * 1.2).rotate(math.radians(a)).move_to([0.0, 0.3, 0]))
    g.add(circ(0.0, 0.3, 0.05, RED, w * 0.8), circ(0.28, 0.3, 0.02, "#3E7CB1", 0),
          circ(-0.14, 0.3 + 0.24, 0.02, "#3E7CB1", 0), circ(-0.14, 0.3 - 0.24, 0.02, "#3E7CB1", 0))
    return g, None


def _molecule(m, w):
    pts = [(0.0, 0.25, RED, 0.07), (-0.2, 0.12, "#FBF8F1", 0.05), (0.2, 0.12, "#FBF8F1", 0.05), (0.06, 0.45, "#3A3631", 0.06),
           (0.24, 0.52, "#FBF8F1", 0.045)]
    g = VGroup(*(line((pts[a][0], pts[a][1]), (pts[b][0], pts[b][1]), "#6E747A", w * 1.6) for a, b in ((0, 1), (0, 2), (0, 3), (3, 4))))
    g.add(*(circ(x, y, r, c, w) for x, y, c, r in pts))
    return g, None


def _virus(m, w):
    c = col(m["color"]) if m.get("color") else "#7FB77E"
    g = VGroup()
    for a in range(0, 360, 36):
        r = math.radians(a)
        g.add(line((0.15 * math.cos(r), 0.25 + 0.15 * math.sin(r)), (0.22 * math.cos(r), 0.25 + 0.22 * math.sin(r)), tint(c, -0.3), w * 1.2),
              circ(0.23 * math.cos(r), 0.25 + 0.23 * math.sin(r), 0.022, RED, w * 0.5))
    g.add(circ(0.0, 0.25, 0.16, c, w), circ(-0.05, 0.28, 0.03, tint(c, -0.2), 0), circ(0.06, 0.21, 0.025, tint(c, -0.2), 0),
          circ(0.03, 0.33, 0.018, tint(c, -0.2), 0))
    return g, None


def _cell(m, w):
    return VGroup(blob([(-0.3, 0.2), (-0.2, 0.04), (0.05, 0.0), (0.28, 0.08), (0.32, 0.26), (0.18, 0.4), (-0.08, 0.42), (-0.26, 0.34)],
                       "#CDE6C3", w),
                  circ(0.02, 0.22, 0.08, "#9A6FB0", w), circ(0.03, 0.23, 0.025, "#6A4580", 0),
                  ell(-0.17, 0.14, 0.1, 0.05, "#F2A93B", w * 0.5), ell(0.18, 0.3, 0.09, 0.045, "#F2A93B", w * 0.5),
                  *(circ(x, y, 0.012, "#4F9A6A", 0) for x, y in ((-0.18, 0.3), (0.2, 0.12), (-0.05, 0.36), (0.12, 0.08)))), None


def _brain(m, w):
    g = VGroup(blob([(-0.22, 0.12), (-0.24, 0.24), (-0.16, 0.34), (-0.04, 0.38), (0.08, 0.38), (0.2, 0.32), (0.25, 0.2), (0.2, 0.08),
                     (0.06, 0.04), (-0.1, 0.05)], "#F2B8C6", w),
               tube([(0.05, 0.06), (0.06, 0.0)], [0.06, 0.04], "#E89AAE", w * 0.6))
    for pts in (((-0.18, 0.2), (-0.1, 0.26), (-0.14, 0.32)), ((-0.06, 0.12), (0.0, 0.2), (-0.04, 0.3)), ((0.06, 0.16), (0.12, 0.24), (0.08, 0.33)),
                ((0.14, 0.12), (0.2, 0.2)), ((-0.16, 0.1), (-0.06, 0.08))):
        g.add(stroke(list(pts), "#C76A85", w * 0.8))
    return g, None


def _skull(m, w):
    return VGroup(blob([(-0.08, 0.0), (-0.1, 0.08), (-0.15, 0.14), (-0.16, 0.26), (-0.08, 0.34), (0.08, 0.34), (0.16, 0.26), (0.15, 0.14),
                        (0.1, 0.08), (0.08, 0.0)], "#F3EEE4", w),
                  blob([(-0.11, 0.18), (-0.1, 0.23), (-0.04, 0.23), (-0.03, 0.17)], "#2B2826", 0),
                  blob([(0.11, 0.18), (0.1, 0.23), (0.04, 0.23), (0.03, 0.17)], "#2B2826", 0),
                  poly([(0.0, 0.15), (-0.02, 0.1), (0.02, 0.1)], "#2B2826", 0),
                  *(line((x, 0.0), (x, 0.06), "#9A9283", w * 0.6) for x in (-0.04, 0.0, 0.04))), None


def _bone(m, w):
    return VGroup(*(circ(x, y, 0.04, "#F3EEE4", w) for x in (-0.22, 0.22) for y in (0.03, 0.11)),
                  rect(-0.21, 0.04, 0.21, 0.1, "#F3EEE4", 0),
                  line((-0.2, 0.04), (0.2, 0.04), zoo.INK, w), line((-0.2, 0.1), (0.2, 0.1), zoo.INK, w)), None


def _tooth(m, w):
    return VGroup(blob([(-0.12, 0.3), (-0.13, 0.22), (-0.1, 0.12), (-0.08, 0.0), (-0.03, 0.02), (0.0, 0.1), (0.03, 0.02), (0.08, 0.0),
                        (0.1, 0.12), (0.13, 0.22), (0.12, 0.3), (0.06, 0.33), (0.0, 0.3), (-0.06, 0.33)], "#FBF8F1", w),
                  stroke([(-0.07, 0.27), (-0.08, 0.2)], "#FFFFFF", w * 1.6)), None


def _prism(m, w):
    g = VGroup(poly([(-0.16, 0.0), (0.16, 0.0), (0.0, 0.3)], "#DDEEF6", w, op=0.85),
               line((-0.55, 0.08), (-0.08, 0.15), "#FBF8F1", w * 2.4), line((-0.55, 0.08), (-0.08, 0.15), zoo.INK, w * 0.4))
    for i, c in enumerate(("#E8524A", "#F2A93B", "#F2D24E", "#4F9A6A", "#3E7CB1", "#7A4C8C")):
        g.add(line((0.08, 0.15), (0.5, 0.22 - i * 0.04), c, w * 1.6))
    return g, None


def _planet(m, w):
    c = col(m["color"]) if m.get("color") else "#E2B65A"
    o = np.array([0.0, 0.25, 0.0])

    def ring(a0, a1):
        return stroke(zoo.P._arc(0.0, 0.25, 0.32, a0, a1, 18), "#C9962B", w * 2.4).stretch(0.22, 1, about_point=o).rotate(-0.25, about_point=o)
    return VGroup(ring(0, 180), circ(0.0, 0.25, 0.18, c, w),
                  stroke([(-0.16, 0.3), (0.16, 0.32)], tint(c, -0.15), w * 1.2), stroke([(-0.17, 0.2), (0.17, 0.22)], tint(c, -0.15), w * 1.2),
                  ring(180, 360)), None


def _earth(m, w):
    return VGroup(circ(0.0, 0.25, 0.25, "#3E7CB1", w),
                  blob([(-0.18, 0.32), (-0.1, 0.42), (0.0, 0.4), (0.02, 0.32), (-0.06, 0.24), (-0.14, 0.22)], "#7FB77E", w * 0.5),
                  blob([(0.04, 0.2), (0.14, 0.26), (0.2, 0.18), (0.14, 0.06), (0.06, 0.08)], "#7FB77E", w * 0.5),
                  blob([(-0.12, 0.12), (-0.06, 0.1), (-0.08, 0.04), (-0.14, 0.06)], "#7FB77E", w * 0.4),
                  stroke(zoo.P._arc(0.0, 0.25, 0.21, 100, 160, 8), "#9FC5DA", w * 1.2)), None


def _comet(m, w):
    return VGroup(*(tube([(0.12, 0.3), (-0.4, 0.3 + dy)], [0.12 - k * 0.03, 0.005], c, 0) for k, (dy, c) in
                    enumerate(((0.06, "#F7E7A6"), (0.0, "#FBEFC4"), (-0.05, "#FFF8E1")))),
                  circ(0.14, 0.3, 0.07, "#F2C14E", w), circ(0.12, 0.32, 0.025, "#FFF8E1", 0)), None


def _bunsen(m, w):
    return VGroup(ell(0.0, 0.02, 0.24, 0.05, "#6E747A", w), rect(-0.03, 0.02, 0.03, 0.3, "#9AA3A9", w),
                  tube([(0.03, 0.06), (0.16, 0.05), (0.26, 0.0)], [0.025, 0.025, 0.025], "#C2552B", w * 0.6),
                  live(blob([(-0.04, 0.3), (-0.02, 0.4), (0.0, 0.48), (0.02, 0.4), (0.04, 0.3)], "#6FA8DC", w * 0.4), "flame"),
                  live(blob([(-0.015, 0.31), (0.0, 0.38), (0.015, 0.31)], "#CFE2F3", 0), "flame")), None


# -- care ----------------------------------------------------------------------------------------------------------

def _stethoscope(m, w):
    return VGroup(stroke([(-0.1, 0.42), (-0.12, 0.3), (-0.06, 0.18), (0.0, 0.16)], "#3A3631", w * 2),
                  stroke([(0.1, 0.42), (0.12, 0.3), (0.06, 0.18), (0.0, 0.16)], "#3A3631", w * 2),
                  stroke([(0.0, 0.16), (0.04, 0.08), (0.14, 0.06), (0.2, 0.1)], "#3A3631", w * 2),
                  circ(0.22, 0.1, 0.045, "#C9CED2", w), circ(0.22, 0.1, 0.02, "#8E969C", 0),
                  *(circ(x, 0.43, 0.015, "#C9CED2", w * 0.5) for x in (-0.1, 0.1))), None


def _bandage(m, w):
    return VGroup(VGroup(rrect(-0.2, 0.0, 0.2, 0.09, 0.04, "#E8BE96", w), rect(-0.06, 0.0, 0.06, 0.09, "#F3DCC2", w * 0.5),
                         *(circ(x, y, 0.006, "#C99A72", 0) for x in (-0.15, -0.11, 0.11, 0.15) for y in (0.03, 0.06)))
                  .rotate(0.4, about_point=np.array([0.0, 0.0, 0.0])).shift([0.0, 0.08, 0])), None


def _wheelchair(m, w):
    g = VGroup(wheel_of(VGroup(Circle(radius=0.2, stroke_color=zoo.INK, stroke_width=w * 2.2).move_to([-0.04, 0.2, 0]),
                               Circle(radius=0.17, stroke_color="#9AA3A9", stroke_width=w * 0.8).move_to([-0.04, 0.2, 0]),
                               *(line((-0.04 + 0.17 * math.cos(t), 0.2 + 0.17 * math.sin(t)), (-0.04 - 0.17 * math.cos(t), 0.2 - 0.17 * math.sin(t)),
                                      "#9AA3A9", w * 0.5) for t in np.linspace(0, math.pi, 4)[:-1]))))
    g.add(stroke([(-0.14, 0.62), (-0.1, 0.3), (0.18, 0.3), (0.2, 0.1)], "#6E747A", w * 1.8),
          rect(-0.1, 0.28, 0.18, 0.32, "#3E7CB1", w * 0.8), rect(-0.13, 0.32, -0.09, 0.58, "#3E7CB1", w * 0.8),
          line((-0.14, 0.62), (-0.24, 0.62), "#3A3631", w * 1.8))
    g.add(*wheelset((0.2,), 0.04, w))
    return g, None


def _ambulance(m, w):
    g = VGroup(rrect(-0.5, 0.08, 0.2, 0.5, 0.04, "#FBF8F1", w),
               blob([(0.2, 0.08), (0.2, 0.4), (0.36, 0.4), (0.48, 0.24), (0.5, 0.08)], "#FBF8F1", w),
               poly([(0.24, 0.26), (0.24, 0.36), (0.34, 0.36), (0.42, 0.26)], "#9FC5DA", w * 0.6),
               rect(-0.5, 0.18, 0.5, 0.22, RED, 0), rect(-0.22, 0.26, -0.1, 0.44, RED, 0), rect(-0.25, 0.29, -0.07, 0.41, RED, 0),
               live(rect(-0.04, 0.5, 0.06, 0.55, "#3E7CB1", w * 0.6), "puff"))
    g.add(*wheelset((-0.32, 0.32), 0.08, w))
    return g, None


# -- getting about -------------------------------------------------------------------------------------------------

def _motorcycle(m, w):
    c = col(m["color"]) if m.get("color") else RED
    g = VGroup(*wheelset((-0.24, 0.24), 0.1, w))
    g.add(line((0.24, 0.1), (0.15, 0.36), "#9AA3A9", w * 1.6), line((0.12, 0.38), (0.2, 0.36), "#3A3631", w * 2.2),
          blob([(-0.16, 0.18), (0.12, 0.18), (0.16, 0.28), (0.04, 0.32), (-0.08, 0.28)], c, w),
          rrect(-0.24, 0.26, -0.02, 0.32, 0.02, "#2B2826", w), rect(-0.08, 0.1, 0.06, 0.18, "#6E747A", w * 0.6),
          line((-0.24, 0.1), (-0.06, 0.16), "#9AA3A9", w * 1.2), line((-0.2, 0.08), (0.04, 0.08), "#9AA3A9", w * 1.2))
    g.scale(1.6, about_point=np.array([0.0, 0.0, 0.0]))       # (a person's scale: wheels at the knee)
    return g, None


def _scooter(m, w):
    c = col(m["color"]) if m.get("color") else "#4FA3A5"
    g = VGroup(*wheelset((-0.22, 0.22), 0.07, w))
    g.add(blob([(-0.3, 0.1), (-0.3, 0.22), (-0.18, 0.28), (-0.04, 0.24), (-0.04, 0.12), (0.12, 0.12), (0.16, 0.36), (0.2, 0.36), (0.24, 0.1)], c, w),
          rrect(-0.28, 0.27, -0.04, 0.32, 0.02, "#3A3631", w), line((0.13, 0.4), (0.24, 0.4), "#3A3631", w * 2),
          circ(0.22, 0.32, 0.025, "#F2C14E", w * 0.5))
    g.scale(1.6, about_point=np.array([0.0, 0.0, 0.0]))       # (a person's scale: wheels at the knee)
    return g, None


def _helicopter(m, w):
    c = col(m["color"]) if m.get("color") else "#3E7CB1"
    g = VGroup(stroke([(-0.3, 0.02), (0.25, 0.02)], "#3A3631", w * 1.6), *(line((x, 0.02), (x + 0.03, 0.1), "#3A3631", w * 1.2) for x in (-0.15, 0.12)),
               tube([(-0.1, 0.26), (-0.4, 0.3), (-0.6, 0.33)], [0.1, 0.05, 0.03], c, w),
               blob([(-0.2, 0.18), (-0.16, 0.34), (0.08, 0.38), (0.24, 0.3), (0.28, 0.18), (0.18, 0.1), (-0.1, 0.1)], c, w),
               blob([(0.06, 0.2), (0.08, 0.34), (0.2, 0.3), (0.25, 0.2)], "#9FC5DA", w * 0.6),
               line((0.0, 0.38), (0.0, 0.44), "#3A3631", w * 1.6))
    g.add(ell(0.0, 0.45, 0.9, 0.03, "#C9C2B2", 0).set_opacity(0.5), line((-0.44, 0.45), (0.44, 0.45), "#3A3631", w * 2.2),
          live(VGroup(line((-0.6, 0.25), (-0.6, 0.41), "#3A3631", w * 1.6), line((-0.68, 0.33), (-0.52, 0.33), "#3A3631", w * 1.6)),
               "spin", (-0.6, 0.33)))
    return g, None


def _hotairballoon(m, w):
    c = col(m["color"]) if m.get("color") else RED
    g = VGroup(blob([(-0.08, 0.38), (-0.26, 0.6), (-0.3, 0.8), (-0.2, 0.98), (0.0, 1.04), (0.2, 0.98), (0.3, 0.8), (0.26, 0.6), (0.08, 0.38)], c, w),
               blob([(-0.04, 0.38), (-0.1, 0.6), (-0.1, 0.8), (-0.06, 0.98), (0.0, 1.04), (0.06, 0.98), (0.1, 0.8), (0.1, 0.6), (0.04, 0.38)], GOLD, w * 0.6),
               *(line((x0, 0.38), (x1, 0.18), "#6B4A2F", w * 0.8) for x0, x1 in ((-0.08, -0.07), (0.08, 0.07))),
               rect(-0.08, 0.04, 0.08, 0.18, WOOD, w), line((-0.08, 0.15), (0.08, 0.15), WOOD_D, w * 0.6),
               live(blob([(-0.025, 0.24), (0.0, 0.33), (0.025, 0.24)], "#F2A93B", 0), "flame"))
    return g, None


def _submarine(m, w):
    c = col(m["color"]) if m.get("color") else "#F2C14E"
    return VGroup(ell(0.0, 0.16, 0.9, 0.3, c, w), rrect(-0.08, 0.28, 0.14, 0.42, 0.04, c, w),
                  line((0.06, 0.42), (0.06, 0.52), "#6E747A", w * 1.6), line((0.06, 0.52), (0.12, 0.52), "#6E747A", w * 1.6),
                  *(circ(x, 0.17, 0.035, "#9FC5DA", w * 0.7) for x in (-0.18, 0.0, 0.18)),
                  poly([(-0.44, 0.16), (-0.52, 0.28), (-0.52, 0.04)], tint(c, -0.2), w),
                  live(VGroup(line((-0.56, 0.1), (-0.56, 0.22), "#6E747A", w * 1.4)), "spin", (-0.56, 0.16))), None


def _sailboat(m, w):
    c = col(m["color"]) if m.get("color") else "#FBF8F1"
    return VGroup(blob([(-0.36, 0.14), (-0.28, 0.02), (0.28, 0.02), (0.38, 0.14)], "#3E5C76", w),
                  line((0.0, 0.14), (0.0, 0.85), WOOD_D, w * 1.8),
                  live(blob([(0.02, 0.82), (0.02, 0.2), (0.3, 0.2)], c, w), "puff"),
                  blob([(-0.02, 0.74), (-0.02, 0.2), (-0.24, 0.2)], tint(c, -0.06), w),
                  live(poly([(0.0, 0.85), (0.12, 0.82), (0.0, 0.79)], RED, w * 0.6), "flag")), None


def _canoe(m, w):
    c = col(m["color"]) if m.get("color") else "#C97A3A"
    return VGroup(blob([(-0.48, 0.16), (-0.36, 0.04), (0.0, 0.0), (0.36, 0.04), (0.48, 0.16), (0.3, 0.1), (-0.3, 0.1)], c, w),
                  stroke([(-0.42, 0.13), (-0.3, 0.1), (0.3, 0.1), (0.42, 0.13)], tint(c, -0.3), w),
                  line((-0.1, 0.0), (0.25, 0.4), WOOD_D, w * 1.6), ell(-0.12, -0.02, 0.06, 0.12, WOOD_D, w * 0.6)), None


def _firetruck(m, w):
    g = VGroup(rrect(-0.6, 0.08, 0.3, 0.42, 0.04, RED, w),
               blob([(0.3, 0.08), (0.3, 0.52), (0.48, 0.52), (0.6, 0.32), (0.6, 0.08)], RED, w),
               poly([(0.34, 0.34), (0.34, 0.47), (0.47, 0.47), (0.55, 0.34)], "#9FC5DA", w * 0.6),
               rect(-0.6, 0.18, 0.3, 0.22, "#F3EEE4", 0),
               *(rect(x, 0.26, x + 0.14, 0.38, tint(RED, -0.2), w * 0.5) for x in (-0.52, -0.32, -0.12)),
               line((-0.55, 0.47), (0.15, 0.62), "#C9CED2", w * 2.4), line((-0.55, 0.43), (0.15, 0.58), "#C9CED2", w * 2.4),
               *(line((-0.45 + i * 0.12, 0.47 + i * 0.026), (-0.45 + i * 0.12, 0.43 + i * 0.026), "#C9CED2", w) for i in range(6)),
               live(rect(0.38, 0.52, 0.46, 0.57, "#3E7CB1", w * 0.6), "puff"))
    g.add(*wheelset((-0.4, -0.2, 0.42), 0.08, w))
    return g, None


def _policecar(m, w):
    g = VGroup(blob([(-0.45, 0.08), (-0.45, 0.2), (-0.25, 0.24), (-0.15, 0.36), (0.15, 0.36), (0.27, 0.24), (0.45, 0.2), (0.45, 0.08)], "#FBF8F1", w),
               rect(-0.45, 0.12, 0.45, 0.18, "#2E4C7E", 0),
               poly([(-0.12, 0.25), (-0.12, 0.33), (0.0, 0.33), (0.0, 0.25)], "#9FC5DA", w * 0.6),
               poly([(0.03, 0.25), (0.03, 0.33), (0.13, 0.33), (0.22, 0.25)], "#9FC5DA", w * 0.6),
               live(rect(-0.06, 0.36, 0.0, 0.4, RED, w * 0.5), "puff"), live(rect(0.0, 0.36, 0.06, 0.4, "#3E7CB1", w * 0.5), "puff"),
               rect(0.4, 0.2, 0.45, 0.24, "#F2C14E", w * 0.5))
    g.add(*wheelset((-0.27, 0.27), 0.08, w))
    return g, None


def _jeep(m, w):
    c = col(m["color"]) if m.get("color") else "#5B6B3A"
    g = VGroup(rect(-0.45, 0.1, 0.45, 0.3, c, w), poly([(-0.3, 0.3), (-0.3, 0.46), (0.1, 0.46), (0.18, 0.3)], tint(c, 0.1), w),
               poly([(-0.06, 0.32), (-0.06, 0.43), (0.08, 0.43), (0.13, 0.32)], "#9FC5DA", w * 0.6),
               rect(-0.27, 0.32, -0.1, 0.43, "#9FC5DA", w * 0.6), rect(0.38, 0.18, 0.45, 0.24, "#F2C14E", w * 0.5),
               circ(-0.5, 0.22, 0.08, "#2B2826", w))
    g.add(*wheelset((-0.27, 0.27), 0.1, w))
    return g, None


def _bulldozer(m, w):
    c = col(m["color"]) if m.get("color") else "#F2C14E"
    g = VGroup(rrect(-0.4, 0.0, 0.2, 0.14, 0.07, "#3A3631", w), *(circ(x, 0.07, 0.045, "#6E747A", w * 0.6) for x in np.linspace(-0.33, 0.13, 5)),
               rect(-0.36, 0.14, 0.18, 0.3, c, w), rect(-0.3, 0.3, -0.02, 0.5, c, w), rect(-0.26, 0.34, -0.06, 0.46, "#9FC5DA", w * 0.6),
               line((-0.36, 0.5), (0.0, 0.5), tint(c, -0.3), w * 1.4), line((0.12, 0.2), (0.32, 0.18), "#6E747A", w * 2.4),
               poly([(0.3, 0.0), (0.44, 0.0), (0.42, 0.34), (0.32, 0.3)], c, w), line((-0.1, 0.3), (-0.1, 0.42), "#3A3631", w * 2))
    return g, None


def _jet(m, w):
    c = col(m["color"]) if m.get("color") else "#8E969C"
    return VGroup(blob([(-0.55, 0.22), (-0.4, 0.28), (0.3, 0.28), (0.6, 0.22), (0.3, 0.16), (-0.4, 0.16)], c, w),
                  poly([(-0.1, 0.22), (0.12, 0.22), (-0.24, -0.02), (-0.34, -0.02)], tint(c, -0.15), w),
                  poly([(-0.42, 0.26), (-0.32, 0.26), (-0.5, 0.46), (-0.56, 0.46)], tint(c, -0.15), w),
                  blob([(0.18, 0.27), (0.24, 0.33), (0.4, 0.3), (0.42, 0.26)], "#9FC5DA", w * 0.6),
                  live(blob([(-0.56, 0.2), (-0.7, 0.22), (-0.56, 0.24)], "#F2A93B", 0), "flame")), None


def _tram(m, w):
    c = col(m["color"]) if m.get("color") else "#C2552B"
    g = VGroup(rrect(-0.6, 0.08, 0.6, 0.55, 0.06, c, w), rect(-0.6, 0.16, 0.6, 0.2, "#F3EEE4", 0),
               *(rect(x, 0.3, x + 0.14, 0.47, "#9FC5DA", w * 0.6) for x in np.linspace(-0.52, 0.38, 6)),
               stroke([(-0.1, 0.55), (0.0, 0.72), (0.15, 0.62), (0.25, 0.8)], "#3A3631", w * 1.4), line((-0.7, 0.8), (0.7, 0.8), "#3A3631", w * 0.8))
    g.add(*wheelset((-0.4, -0.25, 0.25, 0.4), 0.07, w))
    return g, None


# -- places --------------------------------------------------------------------------------------------------------

def _parliament(m, w):
    c = col(m["color"]) if m.get("color") else "#E8DCC4"
    g = VGroup(rect(-0.8, 0.0, 0.8, 0.45, c, w), rect(-0.84, 0.45, 0.84, 0.52, tint(c, -0.08), w),
               *(rect(x - 0.025, 0.04, x + 0.025, 0.45, tint(c, 0.3), w * 0.6) for x in np.linspace(-0.7, 0.7, 13)),
               rect(-0.84, 0.0, 0.84, 0.04, tint(c, -0.15), w * 0.8),
               rect(-0.3, 0.52, 0.3, 0.62, c, w), blob(zoo.P._arc(0.0, 0.62, 0.26, 0, 180, 20), tint(c, -0.05), w),
               *(stroke([(x * 0.26, 0.62), (x * 0.12, 0.82)], tint(c, -0.2), w * 0.6) for x in (-0.6, 0.0, 0.6)),
               line((0.0, 0.88), (0.0, 1.05), "#6E747A", w * 1.2),
               live(poly([(0.0, 1.05), (0.16, 1.01), (0.0, 0.97)], col(m.get("flag") or "#E8822E"), w * 0.6), "flag"))
    return g, None


def _court(m, w):
    c = col(m["color"]) if m.get("color") else "#E8E3D8"
    g = VGroup(rect(-0.6, 0.0, 0.6, 0.06, tint(c, -0.15), w), rect(-0.55, 0.06, 0.55, 0.1, tint(c, -0.08), w),
               *(rect(x - 0.035, 0.1, x + 0.035, 0.6, c, w * 0.8) for x in np.linspace(-0.45, 0.45, 6)),
               rect(-0.58, 0.6, 0.58, 0.67, tint(c, -0.08), w), poly([(-0.6, 0.67), (0.6, 0.67), (0.0, 0.9)], c, w))
    g.add(line((0.0, 0.7), (0.0, 0.84), "#3A3631", w * 0.8), line((-0.06, 0.8), (0.06, 0.8), "#3A3631", w * 0.8),
          stroke([(-0.08, 0.74), (-0.06, 0.8), (-0.04, 0.74)], "#3A3631", w * 0.6), stroke([(0.04, 0.74), (0.06, 0.8), (0.08, 0.74)], "#3A3631", w * 0.6))
    return g, None


def _prison(m, w):
    g = VGroup(rect(-0.5, 0.0, 0.5, 0.7, "#9AA3A9", w),
               *(line((-0.5, y), (0.5, y), "#7E868C", w * 0.4) for y in np.arange(0.1, 0.7, 0.1)),
               rect(-0.3, 0.15, 0.3, 0.55, "#3A3631", w))
    g.add(*(line((x, 0.15), (x, 0.55), "#C9CED2", w * 2.2) for x in np.linspace(-0.24, 0.24, 7)),
          line((-0.3, 0.35), (0.3, 0.35), "#C9CED2", w * 1.6))
    return g, None


def _dam(m, w):
    g = VGroup(poly([(-0.95, -0.06), (0.95, -0.06), (0.9, 0.04), (-0.9, 0.04)], "#6FA8DC", 0),
               poly([(-0.8, 0.0), (-0.8, 0.7), (0.8, 0.7), (0.8, 0.0)], "#C9C2B2", w),
               rect(-0.86, 0.7, 0.86, 0.76, "#B5AD9C", w))
    for x in (-0.5, -0.17, 0.17, 0.5):
        g.add(rect(x - 0.08, 0.04, x + 0.08, 0.22, "#6E747A", w * 0.6),
              live(stroke([(x, 0.04), (x - 0.02, -0.02), (x + 0.02, -0.08)], "#DDEEF6", w * 2.4), "steam"))
    g.add(*(line((x, 0.24), (x, 0.7), "#A8A090", w * 0.5) for x in np.linspace(-0.66, 0.66, 9)))
    return g, None


def _barn(m, w):
    c = col(m["color"]) if m.get("color") else "#A8382B"
    return VGroup(poly([(-0.5, 0.0), (-0.5, 0.5), (-0.3, 0.75), (0.3, 0.75), (0.5, 0.5), (0.5, 0.0)], c, w),
                  stroke([(-0.55, 0.48), (-0.3, 0.78), (0.3, 0.78), (0.55, 0.48)], "#FBF8F1", w * 2),
                  rect(-0.18, 0.0, 0.18, 0.4, tint(c, -0.15), w), line((-0.18, 0.0), (0.18, 0.4), "#FBF8F1", w * 1.4),
                  line((0.18, 0.0), (-0.18, 0.4), "#FBF8F1", w * 1.4), rect(-0.08, 0.5, 0.08, 0.62, "#FBF8F1", w * 0.8)), None


def _silo(m, w):
    return VGroup(rect(-0.16, 0.0, 0.16, 1.0, "#C9CED2", w), blob(zoo.P._arc(0.0, 1.0, 0.16, 0, 180, 12), "#9AA3A9", w),
                  *(line((-0.16, y), (0.16, y), "#9AA3A9", w * 0.5) for y in np.arange(0.12, 1.0, 0.14)),
                  line((0.2, 0.0), (0.2, 1.05), "#6E747A", w * 0.8)), None


def _warehouse(m, w):
    c = col(m["color"]) if m.get("color") else "#8E969C"
    return VGroup(rect(-0.8, 0.0, 0.8, 0.5, c, w), poly([(-0.84, 0.5), (0.0, 0.66), (0.84, 0.5)], tint(c, -0.15), w),
                  *(rect(x - 0.15, 0.0, x + 0.15, 0.34, tint(c, 0.25), w * 0.8) for x in (-0.45, 0.0, 0.45)),
                  *(line((x - 0.15, y), (x + 0.15, y), tint(c, -0.1), w * 0.4) for x in (-0.45, 0.0, 0.45) for y in (0.08, 0.16, 0.24))), None


def _igloo(m, w):
    g = VGroup(blob(zoo.P._arc(0.0, 0.0, 0.42, 0, 180, 20), "#EEF4F8", w))
    for y in (0.12, 0.24, 0.34):
        hw = math.sqrt(0.42 ** 2 - y ** 2)
        g.add(line((-hw, y), (hw, y), "#B8CCD8", w * 0.6))
    g.add(*(line((x, a), (x, b), "#B8CCD8", w * 0.6) for x, a, b in ((-0.25, 0.0, 0.12), (0.2, 0.0, 0.12), (-0.1, 0.12, 0.24), (0.15, 0.24, 0.34))),
          blob([(0.18, 0.0), (0.18, 0.12), (0.26, 0.18), (0.36, 0.12), (0.4, 0.0)], "#EEF4F8", w),
          blob([(0.23, 0.0), (0.23, 0.08), (0.29, 0.12), (0.35, 0.08), (0.35, 0.0)], "#3A3631", 0))
    return g, None


def _pagoda(m, w):
    c = col(m["color"]) if m.get("color") else "#B83227"
    g = VGroup(rect(-0.4, 0.0, 0.4, 0.04, "#9AA3A9", w))
    for i, (hw, y) in enumerate(((0.3, 0.04), (0.24, 0.32), (0.18, 0.56), (0.12, 0.76))):
        h = 0.2 - i * 0.03
        g.add(rect(-hw * 0.75, y, hw * 0.75, y + h, c, w),
              poly([(-hw - 0.12, y + h + 0.05), (-hw, y + h), (hw, y + h), (hw + 0.12, y + h + 0.05), (hw * 0.6, y + h + 0.08), (-hw * 0.6, y + h + 0.08)],
                   "#3A3631", w))
    g.add(line((0.0, 0.98), (0.0, 1.15), GOLD_D, w * 1.6), rect(-0.06, 0.04, 0.06, 0.18, "#3A2A1E", w * 0.6))
    return g, None


def _tajmahal(m, w):
    c = col(m["color"]) if m.get("color") else "#F7F4EC"
    g = VGroup(rect(-0.9, 0.0, 0.9, 0.06, tint(c, -0.1), w))
    for x in (-0.82, 0.82):
        g.add(poly([(x - 0.03, 0.06), (x + 0.03, 0.06), (x + 0.022, 0.8), (x - 0.022, 0.8)], c, w * 0.8),
              *(rect(x - 0.04, y, x + 0.04, y + 0.02, tint(c, -0.1), w * 0.5) for y in (0.3, 0.55, 0.8)),
              blob(zoo.P._arc(x, 0.82, 0.04, 0, 180, 8), c, w * 0.6))
    g.add(rect(-0.5, 0.06, 0.5, 0.5, c, w), blob([(-0.12, 0.06), (-0.12, 0.34), (0.0, 0.44), (0.12, 0.34), (0.12, 0.06)], "#E2DCCC", w * 0.8),
          *(blob([(x - 0.06, y), (x - 0.06, y + 0.1), (x, y + 0.14), (x + 0.06, y + 0.1), (x + 0.06, y)], "#E2DCCC", w * 0.5)
            for x in (-0.33, 0.33) for y in (0.1, 0.3)),
          rect(-0.18, 0.5, 0.18, 0.56, c, w * 0.8),
          blob([(-0.2, 0.56), (-0.24, 0.7), (-0.18, 0.84), (-0.06, 0.94), (0.0, 0.98), (0.06, 0.94), (0.18, 0.84), (0.24, 0.7), (0.2, 0.56)], c, w),
          line((0.0, 0.98), (0.0, 1.08), GOLD_D, w * 1.2),
          *(VGroup(rect(x - 0.06, 0.5, x + 0.06, 0.56, c, w * 0.6), blob(zoo.P._arc(x, 0.56, 0.06, 0, 180, 8), c, w * 0.6)) for x in (-0.38, 0.38)))
    return g, None


def _indiagate(m, w):
    c = col(m["color"]) if m.get("color") else "#D9A27A"
    g = VGroup(rect(-0.5, 0.0, 0.5, 0.04, tint(c, -0.2), w),
               poly([(-0.42, 0.04), (-0.42, 0.95), (0.42, 0.95), (0.42, 0.04), (0.16, 0.04), *zoo.P._arc(0.0, 0.5, 0.16, 0, 180, 12), (-0.16, 0.04)], c, w),
               rect(-0.46, 0.95, 0.46, 1.02, tint(c, -0.1), w), rect(-0.3, 1.02, 0.3, 1.12, c, w),
               blob(zoo.P._arc(0.0, 1.12, 0.12, 0, 180, 10), tint(c, -0.05), w * 0.8),
               *(line((-0.42, y), (0.42, y), tint(c, -0.2), w * 0.5) for y in (0.75, 0.82)),
               letters("INDIA", 0.0, 0.88, 0.04, "#6B4A2F"))
    return g, None


def _eiffeltower(m, w):
    c = col(m["color"]) if m.get("color") else "#8A6F4E"
    g = VGroup(stroke([(-0.42, 0.0), (-0.2, 0.4), (-0.08, 0.9), (-0.02, 1.4), (0.0, 1.6)], c, w * 2),
               stroke([(0.42, 0.0), (0.2, 0.4), (0.08, 0.9), (0.02, 1.4), (0.0, 1.6)], c, w * 2),
               stroke(zoo.P._arc(0.0, 0.0, 0.26, 20, 160, 12), c, w * 1.6),
               rect(-0.26, 0.38, 0.26, 0.44, c, w), rect(-0.12, 0.88, 0.12, 0.92, c, w * 0.8), line((0.0, 1.6), (0.0, 1.72), c, w))
    for y0, y1, a0, a1 in ((0.44, 0.88, 0.2, 0.08), (0.92, 1.4, 0.08, 0.02)):
        for k in range(4):
            ya, yb = y0 + (y1 - y0) * k / 4, y0 + (y1 - y0) * (k + 1) / 4
            xa, xb = a0 + (a1 - a0) * k / 4, a0 + (a1 - a0) * (k + 1) / 4
            g.add(line((-xa, ya), (xb, yb), c, w * 0.4), line((xa, ya), (-xb, yb), c, w * 0.4))
    return g, None


def _colosseum(m, w):
    c = col(m["color"]) if m.get("color") else "#D9C29A"
    g = VGroup(poly([(-0.85, 0.0), (0.85, 0.0), (0.85, 0.55), (0.3, 0.55), (0.4, 0.75), (-0.85, 0.75)], c, w))
    for r, y in enumerate((0.04, 0.24, 0.44)):
        for i in range(9):
            x = -0.78 + i * 0.18
            if y > 0.4 and x > 0.25:
                continue
            g.add(poly([(x, y), *zoo.P._arc(x + 0.05, y + 0.1, 0.05, 180, 0, 8), (x + 0.1, y)], tint(c, -0.35), w * 0.4))
        g.add(line((-0.85, y + 0.18), (0.85 if y < 0.4 else 0.3, y + 0.18), tint(c, -0.2), w * 0.6))
    g.add(*(rect(-0.8 + i * 0.12, 0.62, -0.75 + i * 0.12, 0.7, tint(c, -0.3), w * 0.3) for i in range(9)))
    return g, None


def _greatwall(m, w):
    c = col(m["color"]) if m.get("color") else "#B8AE9C"
    g = VGroup(blob([(-0.9, 0.0), (-0.9, 0.3), (-0.5, 0.45), (-0.1, 0.36), (0.3, 0.52), (0.9, 0.4), (0.9, 0.0)], "#7FB77E", w * 0.6))
    path = [(-0.9, 0.3), (-0.5, 0.45), (-0.1, 0.36), (0.3, 0.52), (0.9, 0.4)]
    g.add(tube(path, [0.12] * 5, c, w))
    for i in range(len(path) - 1):
        (x0, y0), (x1, y1) = path[i], path[i + 1]
        for k in range(4):
            t = (k + 0.5) / 4
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            g.add(rect(x - 0.025, y + 0.06, x + 0.025, y + 0.1, c, w * 0.5))
    for x, y in ((-0.5, 0.45), (0.3, 0.52)):
        g.add(rect(x - 0.08, y - 0.06, x + 0.08, y + 0.2, tint(c, -0.05), w), poly([(x - 0.1, y + 0.2), (x + 0.1, y + 0.2), (x, y + 0.3)], "#6B4A2F", w * 0.8),
              rect(x - 0.025, y + 0.04, x + 0.025, y + 0.12, "#3A3631", 0))
    return g, None


def _powerplant(m, w):
    g = VGroup(rect(-0.2, 0.0, 0.55, 0.35, "#9AA3A9", w), *(rect(x, 0.2, x + 0.08, 0.28, "#9FC5DA", w * 0.5) for x in (-0.12, 0.05, 0.22, 0.39)))
    for x in (-0.55, -0.22):
        side = [(0.17, 0.0), (0.13, 0.25), (0.11, 0.45), (0.115, 0.58), (0.13, 0.7)]
        g.add(poly([(x - a, y) for a, y in side] + [(x + a, y) for a, y in side[::-1]], "#D6D2CA", w),
              live(blob([(x - 0.14, 0.72), (x - 0.18, 0.82), (x - 0.06, 0.92), (x + 0.08, 0.9), (x + 0.16, 0.8), (x + 0.12, 0.72)], "#F3F1EC", w * 0.6), "puff"))
    g.add(rect(0.4, 0.35, 0.47, 0.75, "#B5643C", w), live(circ(0.44, 0.82, 0.05, "#C9C2B2", w * 0.5), "puff"))
    return g, None


# -- papers --------------------------------------------------------------------------------------------------------

def _calendar(m, w):
    g = VGroup(rect(-0.18, 0.0, 0.18, 0.36, "#FBF8F1", w), rect(-0.18, 0.28, 0.18, 0.36, RED, w),
               *(stroke(zoo.P._arc(x, 0.36, 0.02, -30, 210, 8), "#3A3631", w * 1.2) for x in (-0.1, 0.1)))
    for r in range(4):
        for c in range(5):
            g.add(rect(-0.15 + c * 0.062, 0.03 + r * 0.06, -0.11 + c * 0.062, 0.07 + r * 0.06, "#E8E0CC" if (r, c) != (2, 2) else RED, 0))
    return g, None


def _ticket(m, w):
    c = col(m["color"]) if m.get("color") else "#F2C14E"
    return VGroup(blob([(-0.22, 0.0), (-0.22, 0.05), (-0.2, 0.07), (-0.22, 0.09), (-0.22, 0.14), (0.22, 0.14), (0.22, 0.09), (0.2, 0.07),
                        (0.22, 0.05), (0.22, 0.0)], c, w),
                  *(circ(0.1, y, 0.006, tint(c, -0.4), 0) for y in np.linspace(0.02, 0.12, 5)),
                  letters(m.get("label") or "ADMIT", -0.05, 0.07, 0.04, tint(c, -0.6))), None


def _passport(m, w):
    c = col(m["color"]) if m.get("color") else "#2E4C7E"
    return VGroup(rrect(-0.13, 0.0, 0.13, 0.36, 0.02, c, w), Circle(radius=0.06, stroke_color=GOLD, stroke_width=w).move_to([0.0, 0.2, 0]),
                  line((-0.06, 0.2), (0.06, 0.2), GOLD, w * 0.6), line((0.0, 0.14), (0.0, 0.26), GOLD, w * 0.6),
                  letters("PASSPORT", 0.0, 0.31, 0.03, GOLD), rect(-0.06, 0.06, 0.06, 0.08, GOLD, 0)), None


def _idcard(m, w):
    return VGroup(rrect(-0.2, 0.0, 0.2, 0.26, 0.02, "#FBF8F1", w), rect(-0.2, 0.2, 0.2, 0.26, "#E8822E", 0),
                  rect(-0.17, 0.04, -0.05, 0.17, "#C9D6DE", w * 0.5), circ(-0.11, 0.12, 0.025, "#6B6258", 0),
                  blob(zoo.P._arc(-0.11, 0.04, 0.045, 0, 180, 8), "#6B6258", 0),
                  *(scribble(-0.02, x, y, w * 0.5) for x, y in ((0.16, 0.14), (0.12, 0.09), (0.14, 0.05)))), None


def _cheque(m, w):
    return VGroup(rect(-0.32, 0.0, 0.32, 0.16, "#E3F0E6", w), letters("PAY", -0.26, 0.11, 0.025, "#4F7A5A"), scribble(-0.2, 0.14, 0.11, w * 0.5),
                  line((-0.28, 0.06), (0.05, 0.06), "#9AB8A0", w * 0.5), rect(0.12, 0.04, 0.28, 0.08, "#FBF8F1", w * 0.5),
                  scribble(0.14, 0.27, 0.06, w * 0.4), stroke([(0.12, 0.02), (0.18, 0.03), (0.24, 0.01), (0.29, 0.03)], "#2E4C7E", w * 0.8)), None


def _parcel(m, w):
    return VGroup(poly([(-0.2, 0.0), (0.12, 0.0), (0.12, 0.24), (-0.2, 0.24)], "#C99A62", w),
                  poly([(-0.2, 0.24), (0.12, 0.24), (0.2, 0.3), (-0.12, 0.3)], "#D9AE78", w),
                  poly([(0.12, 0.0), (0.2, 0.06), (0.2, 0.3), (0.12, 0.24)], "#B5854E", w),
                  rect(-0.06, 0.0, -0.02, 0.24, "#E8D4AE", w * 0.4), poly([(-0.06, 0.24), (-0.02, 0.24), (0.06, 0.3), (0.02, 0.3)], "#E8D4AE", w * 0.4),
                  rect(-0.17, 0.12, -0.09, 0.19, "#FBF8F1", w * 0.4)), None


# -- regalia, small things -----------------------------------------------------------------------------------------

def _scepter(m, w):
    return VGroup(rrect(-0.02, 0.0, 0.02, 0.5, 0.01, GOLD, w), rect(-0.035, 0.12, 0.035, 0.15, GOLD_D, w * 0.6),
                  rect(-0.035, 0.38, 0.035, 0.41, GOLD_D, w * 0.6), circ(0.0, 0.55, 0.05, GOLD, w), circ(0.0, 0.55, 0.02, RED, w * 0.4),
                  line((0.0, 0.6), (0.0, 0.67), GOLD_D, w * 1.2), line((-0.025, 0.635), (0.025, 0.635), GOLD_D, w * 1.2)), None


def _orb(m, w):
    return VGroup(circ(0.0, 0.11, 0.11, GOLD, w), line((-0.11, 0.11), (0.11, 0.11), GOLD_D, w * 1.4), line((0.0, 0.0), (0.0, 0.22), GOLD_D, w * 1.4),
                  *(circ(x, 0.11, 0.015, RED, 0) for x in (-0.06, 0.06)), line((0.0, 0.22), (0.0, 0.3), GOLD_D, w * 1.6),
                  line((-0.03, 0.265), (0.03, 0.265), GOLD_D, w * 1.6), glint(-0.05, 0.16, 0.025, w)), None


def _ring(m, w):
    return VGroup(Ellipse(width=0.2, height=0.2, stroke_color=GOLD, stroke_width=w * 3.4).move_to([0.0, 0.1, 0]),
                  Ellipse(width=0.2, height=0.2, stroke_color=GOLD_D, stroke_width=w * 0.6).move_to([0.0, 0.1, 0]),
                  poly([(-0.03, 0.2), (0.03, 0.2), (0.045, 0.24), (0.0, 0.29), (-0.045, 0.24)], "#BFE3F2", w * 0.7), glint(0.02, 0.25, 0.02, w)), None


def _necklace(m, w):
    g = VGroup(stroke(zoo.P._arc(0.0, 0.3, 0.2, 200, 340, 16), GOLD, w * 1.2))
    for a in np.linspace(205, 335, 9):
        r = math.radians(a)
        g.add(circ(0.2 * math.cos(r), 0.3 + 0.2 * math.sin(r), 0.018, "#FBF8F1", w * 0.4))
    g.add(blob([(-0.04, 0.1), (0.0, 0.03), (0.04, 0.1), (0.0, 0.13)], "#3EA36A", w * 0.7), glint(0.0, 0.09, 0.015, w))
    return g, None


def _spectacles(m, w):
    return VGroup(Circle(radius=0.07, stroke_color="#3A3631", stroke_width=w * 1.6, fill_color="#DDEEF6", fill_opacity=0.6).move_to([-0.09, 0.08, 0]),
                  Circle(radius=0.07, stroke_color="#3A3631", stroke_width=w * 1.6, fill_color="#DDEEF6", fill_opacity=0.6).move_to([0.09, 0.08, 0]),
                  stroke([(-0.02, 0.09), (0.0, 0.1), (0.02, 0.09)], "#3A3631", w * 1.4),
                  line((-0.16, 0.1), (-0.2, 0.13), "#3A3631", w * 1.4), line((0.16, 0.1), (0.2, 0.13), "#3A3631", w * 1.4)), None


def _sundial(m, w):
    return VGroup(rect(-0.06, 0.0, 0.06, 0.24, "#B8AE9C", w), ell(0.0, 0.26, 0.4, 0.1, "#D6CDB8", w),
                  *(line((0.0, 0.26), (0.17 * math.cos(math.radians(a)), 0.26 + 0.045 * math.sin(math.radians(a))), "#8A8070", w * 0.5)
                    for a in range(0, 360, 30)),
                  poly([(-0.02, 0.27), (0.12, 0.27), (-0.02, 0.38)], "#8E969C", w * 0.7)), None


# -- arms, the law -------------------------------------------------------------------------------------------------

def _crossbow(m, w):
    return VGroup(rrect(-0.3, 0.1, 0.2, 0.14, 0.015, WOOD, w), poly([(-0.3, 0.1), (-0.38, 0.06), (-0.38, 0.14), (-0.3, 0.14)], WOOD_D, w),
                  stroke([(0.12, -0.08), (0.18, 0.12), (0.12, 0.32)], "#6E747A", w * 2.4),
                  line((0.12, -0.08), (-0.05, 0.12), "#E8E0CC", w * 0.6), line((0.12, 0.32), (-0.05, 0.12), "#E8E0CC", w * 0.6),
                  line((-0.05, 0.13), (0.3, 0.13), "#3A3631", w), poly([(0.3, 0.11), (0.35, 0.13), (0.3, 0.15)], IRON, w * 0.5)), None


def _torch(m, w):
    return VGroup(tube([(0.0, 0.0), (0.0, 0.32)], [0.03, 0.05], WOOD, w), rect(-0.035, 0.28, 0.035, 0.34, "#6E747A", w * 0.6),
                  live(blob([(-0.05, 0.34), (-0.06, 0.4), (-0.02, 0.47), (0.0, 0.54), (0.02, 0.47), (0.06, 0.4), (0.05, 0.34)], "#F2A93B", w * 0.4), "flame"),
                  live(blob([(-0.025, 0.35), (0.0, 0.45), (0.025, 0.35)], "#FBE7A1", 0), "flame")), None


def _gavel(m, w):
    return VGroup(ell(0.08, 0.02, 0.24, 0.05, WOOD_D, w), line((-0.2, 0.08), (0.06, 0.22), WOOD, w * 2),
                  VGroup(rrect(-0.06, -0.035, 0.06, 0.035, 0.015, WOOD, w), rect(-0.07, -0.04, -0.05, 0.04, GOLD_D, w * 0.4),
                         rect(0.05, -0.04, 0.07, 0.04, GOLD_D, w * 0.4)).rotate(math.radians(118)).move_to([0.08, 0.24, 0])), None


def _handcuffs(m, w):
    return VGroup(Circle(radius=0.07, stroke_color="#9AA3A9", stroke_width=w * 3).move_to([-0.12, 0.08, 0]),
                  Circle(radius=0.07, stroke_color="#9AA3A9", stroke_width=w * 3).move_to([0.12, 0.08, 0]),
                  *(circ(x, 0.08, 0.014, "#9AA3A9", w * 0.4) for x in (-0.03, 0.0, 0.03)),
                  rect(-0.07, 0.06, -0.04, 0.1, "#6E747A", w * 0.5), rect(0.04, 0.06, 0.07, 0.1, "#6E747A", w * 0.5)), None


def _evm(m, w):
    g = VGroup(rrect(-0.16, 0.0, 0.16, 0.36, 0.02, "#E8E3D8", w), rect(-0.13, 0.03, 0.13, 0.33, "#FBF8F1", w * 0.5))
    for i in range(5):
        y = 0.28 - i * 0.055
        g.add(scribble(-0.11, 0.03, y, w * 0.4), circ(0.08, y, 0.015, "#3E7CB1", w * 0.4), circ(-0.12, y, 0.006, RED if i == 1 else "#C9C2B2", 0))
    return g, None


def _stopsign(m, w):
    pts = [(0.14 * math.cos(math.radians(22.5 + 45 * i)), 0.62 + 0.14 * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]
    return VGroup(line((0.0, 0.0), (0.0, 0.5), "#9AA3A9", w * 1.8), poly(pts, RED, w), letters("STOP", 0.0, 0.62, 0.05, "#FFFFFF")), None


def _fireextinguisher(m, w):
    return VGroup(rrect(-0.07, 0.0, 0.07, 0.36, 0.05, RED, w), rect(-0.05, 0.12, 0.05, 0.22, "#FBF8F1", w * 0.4),
                  rect(-0.02, 0.36, 0.02, 0.4, "#3A3631", w * 0.6), line((-0.02, 0.42), (0.08, 0.44), "#3A3631", w * 1.6),
                  stroke([(0.02, 0.4), (0.12, 0.38), (0.14, 0.26), (0.12, 0.12)], "#3A3631", w * 1.6)), None


def _scarecrow(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.86), WOOD, w * 2), line((-0.36, 0.6), (0.36, 0.6), WOOD, w * 1.6),
                  poly([(-0.14, 0.32), (0.14, 0.32), (0.16, 0.66), (-0.16, 0.66)], "#4F7A9A", w),
                  poly([(-0.3, 0.58), (-0.14, 0.56), (-0.14, 0.66), (-0.3, 0.64)], "#4F7A9A", w * 0.8),
                  poly([(0.3, 0.58), (0.14, 0.56), (0.14, 0.66), (0.3, 0.64)], "#4F7A9A", w * 0.8),
                  *(line((x, 0.6), (x + d, 0.56), "#E2C66A", w * 0.8) for x, d in ((-0.3, -0.05), (-0.3, -0.04), (0.3, 0.05), (0.3, 0.04))),
                  circ(0.0, 0.76, 0.09, "#E8D4AE", w), circ(-0.03, 0.78, 0.01, "#3A3631", 0), circ(0.03, 0.78, 0.01, "#3A3631", 0),
                  stroke([(-0.03, 0.73), (0.0, 0.72), (0.03, 0.73)], "#3A3631", w * 0.6),
                  poly([(-0.16, 0.82), (0.16, 0.82), (0.08, 0.86), (0.05, 0.96), (-0.05, 0.96), (-0.08, 0.86)], "#B5803A", w)), None


def _tornado(m, w):
    g = VGroup()
    for i in range(8):
        y = i * 0.12
        hw = 0.05 + i * 0.045
        g.add(live(Ellipse(width=hw * 2, height=0.06 + i * 0.006, stroke_color="#8E969C", stroke_width=w * 1.6).move_to([0.04 * math.sin(i), y + 0.04, 0]),
                   "steam"))
    return g, None


# -- the first farmers, the first cities ---------------------------------------------------------------------------
CLAY, CLAY_D, MUD, MUD_D, STONE = "#C9A27A", "#A27B55", "#B9925F", "#8C6A42", "#9A948A"


def _kernel(m, w):
    return VGroup(blob([(0.0, 0.0), (0.05, 0.03), (0.06, 0.1), (0.03, 0.17), (0.0, 0.19), (-0.03, 0.17), (-0.06, 0.1), (-0.05, 0.03)],
                       "#D9A84E", w), stroke([(0.0, 0.03), (0.005, 0.1), (0.0, 0.17)], "#A87A2E", w * 0.7)), None


def _handaxe(m, w):
    return VGroup(blob([(0.0, 0.0), (0.09, 0.05), (0.11, 0.16), (0.06, 0.3), (0.0, 0.36), (-0.06, 0.3), (-0.11, 0.16), (-0.09, 0.05)],
                       STONE, w),
                  *(poly(p, tint(STONE, d), w * 0.4) for p, d in (([(-0.05, 0.08), (0.02, 0.06), (0.0, 0.16)], -0.12),
                                                                   ([(0.02, 0.18), (0.07, 0.14), (0.04, 0.27)], 0.12),
                                                                   ([(-0.07, 0.2), (-0.02, 0.22), (-0.03, 0.3)], -0.08)))), None


def _flintknife(m, w):
    return VGroup(poly([(-0.25, 0.04), (0.2, 0.02), (0.3, 0.08), (0.18, 0.12), (-0.25, 0.1)], "#6E6A66", w),
                  *(line((x, 0.04), (x + 0.03, 0.1), "#8E8A85", w * 0.5) for x in (-0.15, -0.05, 0.05, 0.15)),
                  rect(-0.4, 0.035, -0.24, 0.105, WOOD, w), *(line((x, 0.035), (x, 0.105), "#3A2A1E", w * 0.6) for x in (-0.3, -0.27))), None


def _polishedaxe(m, w):
    return VGroup(line((0.0, 0.0), (0.04, 0.6), WOOD, w * 2.6),
                  blob([(0.06, 0.44), (-0.16, 0.4), (-0.22, 0.49), (-0.16, 0.58), (0.06, 0.55)], "#5E6B63", w),
                  stroke([(-0.17, 0.44), (-0.19, 0.53)], "#8FA096", w * 0.8),
                  *(line((-0.01, y), (0.08, y + 0.03), "#C9A066", w * 0.9) for y in (0.43, 0.48, 0.53))), None


def _cavepainting(m, w):
    g = VGroup(blob([(-0.7, 0.0), (-0.75, 0.4), (-0.6, 0.75), (-0.2, 0.85), (0.3, 0.82), (0.65, 0.7), (0.75, 0.35), (0.7, 0.0)], "#C8A47E", w),
               blob([(-0.55, 0.1), (-0.6, 0.4), (-0.45, 0.65), (0.0, 0.72), (0.45, 0.66), (0.58, 0.38), (0.55, 0.1)], "#DDBE96", 0))
    ochre, soot = "#A9472B", "#3A2A1E"
    g.add(blob([(-0.35, 0.4), (-0.3, 0.5), (-0.1, 0.52), (0.0, 0.46), (0.05, 0.5), (0.04, 0.4), (-0.05, 0.36), (-0.3, 0.34)], ochre, 0),
          *(line((x, 0.36), (x + d, 0.24), ochre, w * 1.4) for x, d in ((-0.28, -0.02), (-0.2, 0.01), (-0.08, -0.01), (-0.01, 0.02))),
          stroke([(0.04, 0.5), (0.1, 0.6), (0.06, 0.66)], ochre, w), stroke([(0.02, 0.5), (0.0, 0.62)], ochre, w))
    for x in (0.25, 0.4):
        g.add(circ(x, 0.48, 0.025, soot, 0), line((x, 0.46), (x, 0.36), soot, w * 1.2), line((x, 0.36), (x - 0.04, 0.27), soot, w),
              line((x, 0.36), (x + 0.04, 0.27), soot, w), line((x - 0.05, 0.43), (x + 0.06, 0.45), soot, w))
    g.add(line((0.47, 0.44), (0.0, 0.5), soot, w * 0.8),
          *(VGroup(circ(x, 0.2, 0.035, ochre, 0), *(line((x + 0.03 * math.cos(a), 0.2 + 0.03 * math.sin(a)),
                                                         (x + 0.06 * math.cos(a), 0.2 + 0.06 * math.sin(a)), ochre, w * 0.8)
                                                    for a in np.linspace(0.3, 2.8, 4))) for x in (-0.4, 0.35)))
    return g, None


def _leanto(m, w):
    g = VGroup(poly([(-0.55, 0.0), (0.0, 0.62), (0.55, 0.0)], "#3A2A1E", w),
               poly([(-0.55, 0.0), (0.0, 0.62), (0.08, 0.53), (-0.4, 0.0)], "#7A9A5A", w))
    for k in range(5):
        t = (k + 1) / 6
        g.add(stroke([(-0.55 + 0.15 * t, 0.62 * t * 0.0 + 0.0), (-0.55 + 0.55 * t + 0.04, 0.62 * t)], "#5E7E42", w * 0.6))
    g.add(*(stroke([(0.0 + 0.55 * t, 0.62 * (1 - t)), (0.06 + 0.55 * t, 0.62 * (1 - t) - 0.04)], "#6B8A4C", w * 1.6) for t in np.linspace(0.08, 0.9, 7)),
          line((-0.62, 0.0), (0.05, 0.7), WOOD_D, w * 1.8), line((0.62, 0.0), (-0.05, 0.7), WOOD_D, w * 1.8),
          poly([(-0.7, 0.0), (0.7, 0.0), (0.66, -0.03), (-0.66, -0.03)], "#8C6A42", 0))
    return g, None


def _quern(m, w):
    return VGroup(blob([(-0.32, 0.0), (-0.34, 0.08), (-0.2, 0.14), (0.2, 0.12), (0.34, 0.06), (0.3, 0.0)], STONE, w),
                  blob([(-0.3, 0.1), (0.0, 0.08), (0.3, 0.1), (0.0, 0.12)], tint(STONE, -0.15), 0),
                  blob([(-0.1, 0.12), (-0.11, 0.18), (0.0, 0.21), (0.11, 0.18), (0.1, 0.12)], tint(STONE, 0.1), w),
                  *(circ(x, 0.13, 0.008, "#F3EADA", 0) for x in (-0.22, -0.18, 0.18, 0.23, 0.2))), None


def _barley(m, w):
    g = VGroup()
    for i, a in enumerate((-0.25, -0.08, 0.08, 0.25)):
        top = (0.42 * math.sin(a), 0.62)
        g.add(stroke([(0.0, 0.0), (top[0] * 0.5, 0.3), top], "#C9A44E", w))
        for k in range(5):
            y = top[1] + 0.03 + k * 0.04
            x = top[0] + 0.012 * (k % 2 * 2 - 1)
            g.add(ell(x, y, 0.035, 0.05, "#E2C066", w * 0.4), line((x, y + 0.02), (x + 0.04 * (k % 2 * 2 - 1) + 0.02 * a, y + 0.2), "#E2C066", w * 0.4))
    g.add(rect(-0.05, 0.12, 0.05, 0.16, RED, w * 0.4))
    return g, None


def _millet(m, w):
    g = VGroup(stroke([(0.0, 0.0), (0.02, 0.4), (0.06, 0.62)], "#7FA05A", w * 1.2),
               tube([(0.02, 0.2), (0.16, 0.34), (0.22, 0.32)], [0.035, 0.02, 0.005], "#7FA05A", w * 0.5),
               tube([(0.01, 0.3), (-0.14, 0.44), (-0.2, 0.42)], [0.035, 0.02, 0.005], "#7FA05A", w * 0.5))
    for k in range(9):
        t = k / 8
        x, y = 0.06 + 0.12 * t * t, 0.62 + 0.28 * t - 0.12 * t * t
        g.add(ell(x, y, 0.07, 0.06, "#D9B45A", w * 0.4))
    return g, None


def _riceplant(m, w):
    g = VGroup(blob([(-0.3, 0.0), (0.3, 0.0), (0.26, 0.05), (-0.26, 0.05)], "#7FA8C9", 0))
    for x0, lean in ((-0.08, -0.15), (0.0, 0.0), (0.08, 0.15)):
        g.add(stroke([(x0, 0.0), (x0 + lean * 0.4, 0.3), (x0 + lean, 0.55)], "#6E9A4A", w * 1.2))
    g.add(stroke([(0.0, 0.0), (0.05, 0.4), (0.18, 0.56), (0.26, 0.5)], "#B5A24E", w))
    for k in range(6):
        t = k / 5
        g.add(ell(0.07 + 0.18 * t, 0.44 + 0.13 * math.sin(t * 2.6) - 0.02, 0.035, 0.022, "#E2C066", w * 0.4))
    return g, None


def _lentils(m, w):
    c = col(m["color"]) if m.get("color") else "#D97A3A"
    g = VGroup(ell(0.0, 0.04, 0.5, 0.1, "#C9A066", w), blob([(-0.22, 0.05), (-0.12, 0.13), (0.0, 0.16), (0.12, 0.13), (0.22, 0.05)], c, w * 0.6))
    for i in range(14):
        x = -0.16 + (i % 7) * 0.053
        y = 0.07 + (i // 7) * 0.04 + 0.01 * (i % 3)
        g.add(ell(x, y, 0.035, 0.022, tint(c, 0.15 * ((i % 3) - 1)), w * 0.3))
    return g, None


def _peapod(m, w):
    return VGroup(blob([(-0.25, 0.08), (-0.1, 0.0), (0.12, 0.01), (0.26, 0.08), (0.12, 0.13), (-0.1, 0.13)], "#7FB05A", w),
                  *(circ(x, 0.075, 0.042, "#A6D07A", w * 0.5) for x in (-0.13, -0.04, 0.05, 0.14)),
                  stroke([(-0.25, 0.08), (-0.3, 0.12), (-0.33, 0.1)], "#5E8A3E", w)), None


def _cotton(m, w):
    g = VGroup(line((0.0, 0.0), (0.0, 0.42), "#7A5A3A", w * 1.6), line((0.0, 0.25), (0.14, 0.38), "#7A5A3A", w * 1.2))
    for x, y in ((0.0, 0.48), (0.16, 0.42)):
        g.add(*(circ(x + dx, y + dy, 0.05, "#FBF8F1", w * 0.6) for dx, dy in ((-0.04, 0.0), (0.04, 0.0), (0.0, 0.05), (0.0, -0.02))),
              *(poly([(x, y - 0.05), (x + d * 0.06, y - 0.09), (x + d * 0.02, y - 0.04)], "#7A5A3A", w * 0.4) for d in (-1, 1)))
    return g, None


def _flax(m, w):
    g = VGroup()
    for x, h in ((-0.08, 0.55), (0.0, 0.62), (0.08, 0.5)):
        g.add(stroke([(0.0, 0.0), (x * 0.5, h * 0.5), (x, h)], "#7FA05A", w))
        g.add(*(ell(x + 0.03 * math.cos(a), h + 0.03 * math.sin(a), 0.04, 0.04, "#6FA8DC", w * 0.3) for a in np.linspace(0, 2 * math.pi, 6)[:-1]),
              circ(x, h, 0.012, "#F2C14E", 0))
    g.add(rect(-0.04, 0.1, 0.04, 0.14, "#C9A066", w * 0.4))
    return g, None


def _yarn(m, w):
    c = col(m["color"]) if m.get("color") else "#E8E0CC"
    g = VGroup(circ(0.0, 0.14, 0.14, c, w))
    for a in (-0.6, -0.2, 0.2, 0.6):
        g.add(stroke(zoo.P._arc(0.0, 0.14, 0.12, 120 + a * 60, 300 + a * 60, 10), tint(c, -0.2), w * 0.6))
    g.add(stroke([(0.12, 0.06), (0.22, 0.02), (0.3, 0.04)], tint(c, -0.2), w))
    return g, None


def _spindle(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.5), WOOD, w * 1.4), ell(0.0, 0.12, 0.16, 0.05, CLAY_D, w),
                  ell(0.0, 0.3, 0.07, 0.12, "#E8E0CC", w * 0.6),
                  *(line((-0.035, 0.24 + i * 0.02), (0.035, 0.26 + i * 0.02), "#C9C2B2", w * 0.4) for i in range(5)),
                  stroke([(0.0, 0.5), (0.03, 0.58), (-0.02, 0.66)], "#E8E0CC", w)), None


def _clothbolt(m, w):
    c = col(m["color"]) if m.get("color") else "#C9A66B"
    return VGroup(poly([(0.1, 0.0), (0.42, 0.0), (0.42, 0.04), (0.1, 0.04)], tint(c, 0.1), w),
                  rect(-0.3, 0.0, 0.12, 0.24, c, w), ell(0.12, 0.12, 0.08, 0.24, tint(c, 0.15), w),
                  stroke(zoo.P._arc(0.12, 0.12, 0.05, 0, 330, 10), tint(c, -0.2), w * 0.6),
                  *(line((-0.3, y), (0.12, y), tint(c, -0.15), w * 0.4) for y in (0.08, 0.16))), None


def _storagejar(m, w):
    c = col(m["color"]) if m.get("color") else CLAY
    g = VGroup(blob([(-0.08, 0.0), (-0.2, 0.12), (-0.24, 0.35), (-0.16, 0.52), (-0.1, 0.56), (0.1, 0.56), (0.16, 0.52), (0.24, 0.35),
                     (0.2, 0.12), (0.08, 0.0)], c, w),
               rect(-0.1, 0.56, 0.1, 0.6, tint(c, -0.15), w * 0.8),
               *(stroke([(-0.22, y), (0.0, y - 0.02), (0.22, y)], tint(c, -0.25), w * 0.6) for y in (0.42, 0.46)))
    g.add(*(stroke([(x, 0.3), (x + 0.02, 0.36), (x + 0.04, 0.3)], tint(c, -0.3), w * 0.5) for x in (-0.14, -0.04, 0.06)))
    return g, None


def _copperore(m, w):
    return VGroup(blob([(-0.2, 0.0), (-0.22, 0.1), (-0.12, 0.2), (0.04, 0.22), (0.18, 0.14), (0.2, 0.02)], "#6E625A", w),
                  *(blob([(x - 0.04, y), (x, y + 0.04), (x + 0.05, y + 0.01), (x + 0.01, y - 0.03)], c, 0)
                    for x, y, c in ((-0.1, 0.1, "#3FA37A"), (0.05, 0.14, "#4FB5A5"), (0.1, 0.05, "#2E8F6A"), (-0.03, 0.04, "#5FC0B0"))),
                  circ(-0.14, 0.05, 0.015, "#C97A3A", 0)), None


def _ingot(m, w):
    c = col(m["color"]) if m.get("color") else "#B8733A"
    return VGroup(poly([(-0.3, 0.0), (-0.2, 0.04), (0.2, 0.04), (0.3, 0.0), (0.24, 0.06), (0.3, 0.12), (0.2, 0.09), (-0.2, 0.09),
                        (-0.3, 0.12), (-0.24, 0.06)], c, w),
                  stroke([(-0.18, 0.08), (0.16, 0.08)], tint(c, 0.3), w * 0.8)), None


def _obsidian(m, w):
    return VGroup(poly([(-0.18, 0.0), (0.16, 0.0), (0.2, 0.1), (0.08, 0.22), (-0.06, 0.2), (-0.2, 0.08)], "#2B2826", w),
                  poly([(0.08, 0.22), (0.02, 0.1), (0.16, 0.0), (0.2, 0.1)], "#3E3A44", 0),
                  stroke([(-0.12, 0.08), (-0.04, 0.16)], "#9AA3C0", w * 1.2), glint(0.0, 0.15, 0.025, w)), None


def _seashell(m, w):
    c = col(m["color"]) if m.get("color") else "#F2C8B0"
    g = VGroup(blob([(0.0, 0.0), *zoo.P._arc(0.0, 0.0, 0.2, 20, 160, 12)], c, w),
               rect(-0.05, -0.04, 0.05, 0.0, tint(c, -0.15), w * 0.6))
    for a in (35, 60, 90, 120, 145):
        r = math.radians(a)
        g.add(line((0.0, 0.0), (0.19 * math.cos(r), 0.19 * math.sin(r)), tint(c, -0.2), w * 0.6))
    g.shift([0.0, 0.04, 0])
    return g, None


def _lapis(m, w):
    return VGroup(blob([(-0.16, 0.0), (-0.18, 0.1), (-0.06, 0.2), (0.1, 0.18), (0.18, 0.08), (0.12, 0.0)], "#26519E", w),
                  *(circ(x, y, 0.008, GOLD, 0) for x, y in ((-0.08, 0.08), (0.02, 0.13), (0.08, 0.06), (-0.02, 0.04), (0.1, 0.12))),
                  blob([(-0.1, 0.12), (-0.04, 0.17), (0.02, 0.15)], "#5F86C9", 0), glint(0.06, 0.15, 0.02, w)), None


def _claytablet(m, w):
    c = col(m["color"]) if m.get("color") else CLAY
    g = VGroup(rrect(-0.15, 0.0, 0.15, 0.36, 0.04, c, w))
    for r in range(6):
        y = 0.31 - r * 0.052
        g.add(line((-0.13, y - 0.026), (0.13, y - 0.026), tint(c, -0.15), w * 0.3))
        for k in range(4 + (r % 2)):
            x = -0.11 + k * 0.055 + (r % 2) * 0.01
            g.add(poly([(x, y), (x + 0.025, y + 0.008), (x + 0.012, y - 0.02)], tint(c, -0.4), 0),
                  line((x + 0.012, y - 0.005), (x + 0.03 * ((k + r) % 2), y - 0.02), tint(c, -0.4), w * 0.4))
    return g, None


def _stylus(m, w):
    return VGroup(line((0.0, 0.0), (0.04, 0.42), "#C9B07A", w * 2.4),
                  *(line((0.04 * y / 0.42 - 0.012, y), (0.04 * y / 0.42 + 0.012, y), "#A08A55", w * 0.8) for y in (0.14, 0.28)),
                  poly([(-0.012, 0.0), (0.012, 0.0), (0.0, -0.05)], "#A08A55", w * 0.6)), None


def _claylump(m, w):
    return VGroup(blob([(-0.18, 0.0), (-0.2, 0.08), (-0.1, 0.16), (0.06, 0.17), (0.18, 0.1), (0.18, 0.0)], "#B5875E", w),
                  stroke([(-0.08, 0.12), (0.0, 0.14), (0.08, 0.12)], "#D9AE84", w), circ(0.08, 0.06, 0.02, "#9A6E48", 0)), None


def _ziggurat(m, w):
    c = col(m["color"]) if m.get("color") else MUD
    g = VGroup()
    for i, (hw, h) in enumerate(((0.9, 0.3), (0.62, 0.25), (0.38, 0.22))):
        y = sum(x[1] for x in ((0.9, 0.3), (0.62, 0.25), (0.38, 0.22))[:i])
        g.add(poly([(-hw, y), (hw, y), (hw - 0.04, y + h), (-hw + 0.04, y + h)], tint(c, -0.05 * i), w),
              *(line((-hw + 0.06 + k * (2 * hw - 0.12) / 8, y + 0.02), (-hw + 0.06 + k * (2 * hw - 0.12) / 8, y + h - 0.02), tint(c, -0.2), w * 0.4)
                for k in range(9)))
    g.add(poly([(-0.06, 0.0), (0.06, 0.0), (0.05, 0.55), (-0.05, 0.55)], tint(c, 0.15), w * 0.8),
          *(line((-0.05, y), (0.05, y), tint(c, -0.2), w * 0.4) for y in np.arange(0.05, 0.55, 0.05)),
          rect(-0.16, 0.77, 0.16, 0.95, tint(c, 0.1), w), rect(-0.04, 0.77, 0.04, 0.88, "#3A2A1E", w * 0.5))
    return g, None


def _mudbricks(m, w):
    g = VGroup()
    for r in range(4):
        for k in range(4 - r % 2):
            x = -0.3 + k * 0.2 + (r % 2) * 0.1
            g.add(rrect(x, r * 0.09, x + 0.19, r * 0.09 + 0.085, 0.01, tint(MUD, 0.08 * ((k + r) % 3 - 1)), w * 0.8))
    g.add(*(line((x, 0.02), (x + 0.03, 0.05), "#D9C29A", w * 0.4) for x in (-0.25, -0.02, 0.2)))
    return g, None


def _citywall(m, w):
    c = col(m["color"]) if m.get("color") else MUD
    g = VGroup(rect(-0.9, 0.0, 0.9, 0.55, c, w))
    g.add(*(rect(-0.9 + i * 0.12, 0.55, -0.84 + i * 0.12, 0.62, c, w * 0.6) for i in range(15)),
          *(line((-0.9, y), (0.9, y), tint(c, -0.15), w * 0.3) for y in (0.14, 0.28, 0.42)))
    for x in (-0.75, 0.75):
        g.add(rect(x - 0.14, 0.0, x + 0.14, 0.78, tint(c, -0.05), w), *(rect(x - 0.14 + i * 0.1, 0.78, x - 0.09 + i * 0.1, 0.86, tint(c, -0.05), w * 0.6) for i in range(3)),
              rect(x - 0.025, 0.5, x + 0.025, 0.62, "#3A2A1E", 0))
    g.add(rect(-0.26, 0.0, 0.26, 0.82, tint(c, -0.08), w), *(rect(-0.26 + i * 0.1, 0.82, -0.21 + i * 0.1, 0.9, tint(c, -0.08), w * 0.6) for i in range(6)),
          blob([(-0.13, 0.0), (-0.13, 0.4), *zoo.P._arc(0.0, 0.4, 0.13, 180, 0, 10), (0.13, 0.0)], "#5A4630", w),
          *(line((x, 0.0), (x, 0.45), "#3A2A1E", w * 0.5) for x in (-0.06, 0.0, 0.06)))
    return g, None


def _stele(m, w):
    c = col(m["color"]) if m.get("color") else "#5E5A55"
    g = VGroup(poly([(-0.2, 0.0), (-0.2, 0.62), *zoo.P._arc(0.0, 0.62, 0.2, 180, 0, 14), (0.2, 0.0)], c, w),
               rect(-0.24, -0.02, 0.24, 0.04, tint(c, -0.2), w * 0.8),
               circ(0.0, 0.68, 0.05, tint(c, 0.3), w * 0.4), *(line((0.0, 0.68), (0.08 * math.cos(a), 0.68 + 0.08 * math.sin(a)), tint(c, 0.3), w * 0.4)
                                                               for a in np.linspace(0, 2 * math.pi, 9)[:-1]),
               circ(-0.06, 0.52, 0.025, tint(c, 0.3), 0), rect(-0.08, 0.38, -0.04, 0.49, tint(c, 0.3), 0),
               circ(0.08, 0.52, 0.025, tint(c, 0.3), 0), rect(0.06, 0.38, 0.1, 0.49, tint(c, 0.3), 0))
    for r in range(5):
        y = 0.3 - r * 0.055
        g.add(*(poly([(x, y), (x + 0.02, y + 0.006), (x + 0.01, y - 0.016)], tint(c, 0.35), 0) for x in np.arange(-0.15, 0.15, 0.045)))
    return g, None


def _cylinderseal(m, w):
    g = VGroup(rect(-0.32, 0.0, 0.32, 0.12, "#C9A27A", w * 0.8))
    for i in range(4):
        x = -0.26 + i * 0.16
        g.add(circ(x, 0.085, 0.012, "#7A5A3A", 0), line((x, 0.075), (x, 0.03), "#7A5A3A", w * 0.8),
              line((x - 0.025, 0.06), (x + 0.025, 0.06), "#7A5A3A", w * 0.6), line((x + 0.05, 0.03), (x + 0.07, 0.09), "#7A5A3A", w * 0.6))
    g.add(rect(-0.07, 0.12, 0.07, 0.34, "#2E5E9E", w), ell(0.0, 0.34, 0.14, 0.04, "#3E6EB0", w * 0.6), ell(0.0, 0.34, 0.03, 0.012, "#1A2A40", 0),
          *(stroke([(-0.06, y), (0.0, y + 0.02), (0.06, y)], "#9FC5DA", w * 0.5) for y in (0.17, 0.23, 0.29)),
          line((0.0, 0.35), (0.0, 0.48), WOOD, w * 1.2))
    return g, None


def _claycones(m, w):
    g = VGroup(rect(-0.32, 0.0, 0.32, 0.4, "#D9C29A", w))
    cols = ("#2B2826", "#B83227", "#F3EADA")
    for r in range(7):
        for k in range(10):
            x, y = -0.29 + k * 0.064 + (r % 2) * 0.032, 0.03 + r * 0.055
            if x > 0.3:
                continue
            band = (k + r) // 2 % 3 if r % 3 else (k // 2) % 3
            g.add(circ(x, y, 0.024, cols[band], w * 0.3))
    return g, None


def _potterswheel(m, w):
    return VGroup(ell(0.0, 0.04, 0.5, 0.08, STONE, w), rect(-0.02, 0.06, 0.02, 0.22, WOOD_D, w * 0.6),
                  live(VGroup(ell(0.0, 0.24, 0.44, 0.07, tint(STONE, 0.1), w), line((-0.14, 0.24), (0.14, 0.24), tint(STONE, -0.2), w * 0.5)), "puff"),
                  blob([(-0.1, 0.26), (-0.12, 0.34), (-0.07, 0.42), (-0.05, 0.48), (0.05, 0.48), (0.07, 0.42), (0.12, 0.34), (0.1, 0.26)], CLAY, w),
                  ell(0.0, 0.48, 0.1, 0.025, CLAY_D, w * 0.6)), None


def _lyre(m, w):
    g = VGroup(rect(-0.2, 0.0, 0.2, 0.28, WOOD, w), *(rect(-0.18, y, 0.18, y + 0.04, c, w * 0.3) for y, c in ((0.04, "#F3EADA"), (0.1, "#26519E"), (0.16, "#F3EADA"))),
               line((-0.18, 0.28), (-0.22, 0.8), WOOD_D, w * 2), line((0.18, 0.28), (0.2, 0.76), WOOD_D, w * 2),
               line((-0.24, 0.78), (0.24, 0.74), WOOD_D, w * 2.2))
    g.add(*(line((x, 0.06), (x * 1.05, 0.76 - (x + 0.2) * 0.1), "#E8E0CC", w * 0.4) for x in np.linspace(-0.13, 0.13, 6)))
    g.add(blob([(-0.36, 0.3), (-0.34, 0.48), (-0.26, 0.56), (-0.2, 0.5), (-0.22, 0.3)], GOLD, w),
          poly([(-0.33, 0.52), (-0.42, 0.66), (-0.3, 0.56)], "#3A3631", w * 0.6), poly([(-0.24, 0.55), (-0.2, 0.68), (-0.27, 0.57)], "#3A3631", w * 0.6),
          circ(-0.3, 0.46, 0.014, "#26519E", 0), blob([(-0.36, 0.3), (-0.3, 0.22), (-0.24, 0.3)], "#26519E", w * 0.5))
    return g, None


def _dates(m, w):
    g = VGroup(stroke([(0.0, 0.5), (0.02, 0.36)], "#C9A44E", w * 1.6))
    for k in range(10):
        a = math.radians(200 + k * 14)
        x0, y0 = 0.02 + 0.05 * math.cos(a), 0.34
        x1, y1 = 0.02 + 0.2 * math.cos(a), 0.34 - 0.06 - 0.18 * abs(math.sin(a * 0.7))
        g.add(line((x0, y0), (x1, y1 + 0.03), "#C9A44E", w * 0.6), ell(x1, y1, 0.045, 0.07, "#8A3A1E" if k % 2 else "#A8502A", w * 0.4))
    g.add(*(ell(x, y, 0.045, 0.07, "#9A4422", w * 0.4) for x, y in ((-0.05, 0.12), (0.06, 0.1), (0.0, 0.05))))
    return g, None


def _barge(m, w):
    c = col(m["color"]) if m.get("color") else "#C9B07A"
    g = VGroup(blob([(-0.6, 0.2), (-0.5, 0.06), (0.0, 0.0), (0.5, 0.06), (0.62, 0.26), (0.45, 0.14), (-0.45, 0.14)], c, w),
               *(line((x, 0.04), (x * 1.05, 0.16), tint(c, -0.3), w * 0.6) for x in np.linspace(-0.45, 0.45, 9)),
               stroke([(-0.55, 0.17), (-0.66, 0.3), (-0.62, 0.36)], tint(c, -0.2), w * 2))
    for x in (-0.3, -0.1, 0.1, 0.3):
        g.add(blob([(x - 0.08, 0.14), (x - 0.09, 0.24), (x - 0.04, 0.3), (x + 0.04, 0.3), (x + 0.09, 0.24), (x + 0.08, 0.14)], "#D9C29A", w * 0.8),
              line((x - 0.03, 0.3), (x + 0.03, 0.3), "#8C6A42", w * 1.2))
    g.add(line((0.48, 0.18), (0.6, 0.6), WOOD_D, w * 1.6))
    return g, None


def _shaduf(m, w):
    return VGroup(line((-0.05, 0.0), (0.0, 0.6), WOOD_D, w * 2.4), line((0.12, 0.0), (0.06, 0.6), WOOD_D, w * 2.4),
                  line((-0.45, 0.42), (0.55, 0.78), WOOD, w * 2), circ(0.03, 0.6, 0.02, "#3A3631", 0),
                  blob([(0.5, 0.74), (0.48, 0.68), (0.56, 0.62), (0.64, 0.7), (0.6, 0.78)], STONE, w),
                  line((-0.44, 0.42), (-0.44, 0.12), "#6B4A2F", w * 0.8),
                  blob([(-0.52, 0.12), (-0.5, 0.02), (-0.38, 0.02), (-0.36, 0.12)], CLAY_D, w),
                  blob([(-0.7, -0.03), (-0.7, 0.0), (-0.2, 0.0), (-0.2, -0.03)], "#6FA8DC", 0)), None


def _canal(m, w):
    return VGroup(poly([(-0.8, 0.0), (0.8, 0.0), (0.8, 0.12), (-0.8, 0.12)], "#8C6A42", w * 0.6),
                  poly([(-0.8, 0.02), (0.8, 0.02), (0.8, 0.1), (-0.8, 0.1)], "#6FA8DC", 0),
                  *(stroke([(x, 0.06), (x + 0.06, 0.075), (x + 0.12, 0.06)], "#DDEEF6", w * 0.8) for x in (-0.6, -0.2, 0.2, 0.55)),
                  poly([(-0.85, 0.12), (0.85, 0.12), (0.8, 0.16), (-0.8, 0.16)], "#7FA05A", 0),
                  *(stroke([(x, 0.16), (x + 0.02, 0.24)], "#6E9A4A", w * 0.8) for x in np.linspace(-0.7, 0.7, 12))), None


def _cheese(m, w):
    return VGroup(rect(-0.22, 0.0, 0.22, 0.12, "#F2C96A", w), ell(0.0, 0.0, 0.44, 0.1, "#F2C96A", w).set_z_index(-1),
                  ell(0.0, 0.12, 0.44, 0.1, "#F7D98A", w),
                  poly([(0.0, 0.12), (0.2, 0.15), (0.12, 0.18)], "#E2B65A", w * 0.6),
                  poly([(0.06, 0.0), (0.26, -0.02), (0.26, 0.1), (0.06, 0.12)], "#FBE7A1", w * 0.8),
                  *(circ(x, y, 0.014, "#E2B65A", 0) for x, y in ((-0.1, 0.06), (-0.16, 0.04), (0.14, 0.05), (0.2, 0.07)))), None


def _hide(m, w):
    return VGroup(blob([(-0.3, 0.0), (-0.38, 0.08), (-0.3, 0.16), (-0.34, 0.28), (-0.2, 0.3), (0.0, 0.34), (0.2, 0.3), (0.34, 0.28), (0.3, 0.16),
                        (0.38, 0.08), (0.3, 0.0), (0.0, 0.04)], "#A8784E", w),
                  stroke([(-0.2, 0.17), (0.2, 0.17)], "#8C5E38", w * 0.6), stroke([(-0.12, 0.1), (-0.04, 0.24), (0.1, 0.12)], "#C9966A", w * 0.5)), None


def _oillamp(m, w):
    return VGroup(blob([(-0.18, 0.04), (-0.16, 0.0), (0.12, 0.0), (0.2, 0.04), (0.28, 0.06), (0.2, 0.1), (0.0, 0.12), (-0.16, 0.1)], CLAY, w),
                  ell(-0.02, 0.1, 0.12, 0.03, "#3A2A1E", w * 0.4), stroke([(-0.18, 0.06), (-0.26, 0.1), (-0.2, 0.14)], CLAY_D, w * 1.4),
                  live(blob([(0.25, 0.08), (0.24, 0.13), (0.27, 0.2), (0.3, 0.13), (0.29, 0.08)], "#F2A93B", 0), "flame")), None


def _sealing(m, w):
    return VGroup(blob([(-0.15, 0.0), (-0.18, 0.12), (-0.12, 0.24), (0.12, 0.24), (0.18, 0.12), (0.15, 0.0)], CLAY, w),
                  ell(0.0, 0.25, 0.22, 0.05, CLAY_D, w * 0.6),
                  stroke([(-0.14, 0.24), (-0.02, 0.32), (0.08, 0.26), (0.16, 0.34)], "#8C6A42", w),
                  blob([(-0.07, 0.24), (-0.08, 0.32), (0.0, 0.36), (0.08, 0.31), (0.06, 0.24)], "#B5875E", w),
                  *(line((x, 0.28), (x + 0.015, 0.33), "#7A5A3A", w * 0.5) for x in (-0.04, 0.0, 0.03))), None


def _beacon(m, w):
    return VGroup(poly([(-0.14, 0.0), (0.14, 0.0), (0.1, 0.7), (-0.1, 0.7)], MUD, w),
                  *(line((-0.13 + i * 0.005, y), (0.13 - i * 0.005, y), tint(MUD, -0.2), w * 0.4) for i, y in enumerate((0.18, 0.36, 0.54))),
                  rect(-0.14, 0.7, 0.14, 0.76, tint(MUD, -0.1), w),
                  *(line((x, 0.76), (x + 0.03, 0.8), WOOD_D, w * 1.6) for x in (-0.09, -0.02, 0.05)),
                  live(blob([(-0.1, 0.78), (-0.12, 0.9), (-0.04, 0.98), (0.0, 1.08), (0.04, 0.98), (0.12, 0.9), (0.1, 0.78)], "#F2A93B", w * 0.4), "flame"),
                  live(blob([(-0.05, 0.79), (0.0, 0.92), (0.05, 0.79)], "#FBE7A1", 0), "flame"),
                  live(blob([(0.06, 1.1), (0.0, 1.2), (0.1, 1.3), (0.2, 1.24), (0.16, 1.12)], "#C9C2B2", w * 0.5), "puff")), None


def _tabletshelf(m, w):
    g = VGroup(rect(-0.45, 0.0, 0.45, 0.9, WOOD_D, w))
    for r in range(3):
        y = 0.04 + r * 0.29
        g.add(rect(-0.42, y, 0.42, y + 0.25, "#4A3626", 0), rect(-0.45, y - 0.02, 0.45, y + 0.01, WOOD, w * 0.5))
        for k in range(9):
            x = -0.38 + k * 0.088
            h = 0.17 + 0.04 * ((k + r) % 3 == 0)
            g.add(rrect(x, y + 0.01, x + 0.07, y + 0.01 + h, 0.01, tint(CLAY, 0.08 * ((k + r) % 3 - 1)), w * 0.5))
    g.add(rect(-0.45, 0.88, 0.45, 0.92, WOOD, w * 0.5))
    return g, None


def _eclipse(m, w):
    g = VGroup()
    for a in range(0, 360, 30):
        r = math.radians(a)
        g.add(line((0.2 * math.cos(r), 0.3 + 0.2 * math.sin(r)), (0.3 * math.cos(r), 0.3 + 0.3 * math.sin(r)), "#F2C14E", w * 1.2))
    g.add(circ(0.0, 0.3, 0.17, "#F2C14E", w), circ(0.0, 0.3, 0.15, "#2B2826", 0), stroke(zoo.P._arc(0.0, 0.3, 0.165, 200, 340, 10), "#FBE7A1", w * 1.6))
    return g, None


def _mudhouse(m, w):
    c = col(m["color"]) if m.get("color") else "#C9A27A"
    return VGroup(rect(-0.5, 0.0, 0.5, 0.55, c, w), rect(-0.53, 0.55, 0.53, 0.6, tint(c, -0.15), w),
                  *(line((x, 0.6), (x, 0.66), WOOD_D, w * 1.2) for x in (-0.4, -0.2, 0.0, 0.2, 0.4)),
                  rect(-0.12, 0.0, 0.12, 0.32, "#5A4630", w), rect(-0.14, 0.0, 0.14, 0.03, tint(c, -0.2), w * 0.6),
                  rect(0.24, 0.32, 0.36, 0.42, "#3A2A1E", w * 0.6), rect(-0.36, 0.32, -0.24, 0.42, "#3A2A1E", w * 0.6),
                  *(stroke([(x, y), (x + 0.06, y + 0.01)], tint(c, -0.15), w * 0.4) for x, y in ((-0.4, 0.12), (0.25, 0.18), (-0.2, 0.46), (0.3, 0.5)))), None


def _field(m, w):
    g = VGroup(poly([(-0.9, 0.0), (0.9, 0.0), (0.7, 0.3), (-0.7, 0.3)], "#8C6A42", w))
    for i in range(6):
        t = i / 5
        x0, x1 = -0.75 + 1.5 * t, -0.6 + 1.2 * t
        g.add(line((x0, 0.02), (x1, 0.28), "#6B4E2E", w * 0.8))
        if m.get("of") != "bare":
            for k in range(4):
                s = (k + 0.5) / 4
                x, y = x0 + (x1 - x0) * s, 0.02 + 0.26 * s
                g.add(stroke([(x, y), (x - 0.02, y + 0.06)], "#7FB05A", w * 0.8), stroke([(x, y), (x + 0.02, y + 0.05)], "#7FB05A", w * 0.8))
    return g, None


def _yoke(m, w):
    return VGroup(stroke([(-0.45, 0.2), (-0.3, 0.24), (0.3, 0.24), (0.45, 0.2)], WOOD, w * 3.2),
                  *(stroke(zoo.P._arc(x, 0.18, 0.08, 200, 340, 8), WOOD_D, w * 1.6) for x in (-0.3, 0.3)),
                  line((0.0, 0.24), (0.0, 0.0), "#6B4A2F", w * 1.2), line((0.0, 0.0), (0.45, -0.02), "#6B4A2F", w)), None


def _fishingnet(m, w):
    g = VGroup(line((-0.4, 0.5), (0.4, 0.5), WOOD, w * 1.8))
    rows = [(-0.4 + 0.1 * k, 0.5) for k in range(9)]
    for r in range(1, 5):
        y = 0.5 - r * 0.11
        new = [(-0.4 + 0.1 * k + 0.05 * (r % 2) + 0.02 * math.sin(k + r), y) for k in range(9)]
        for (a, b) in zip(rows, new):
            g.add(line(a, b, "#C9B07A", w * 0.5))
        for (a, b) in zip(rows[1:], new):
            g.add(line(a, b, "#C9B07A", w * 0.5))
        rows = new
    g.add(*(circ(x, 0.06, 0.02, "#E8E0CC", w * 0.4) for x, _ in rows[::2]))
    return g, None


# -- the land: rivers, mountains, coasts, deserts, forests (drawn wide, to stand behind people or alone) -------------
WATER, WATER_D, GRASS, GRASS_D, SAND, SAND_D, SNOW = ("#6FA8DC", "#3E7CB1", "#8DBB6A", "#5E8A3E", "#E8CF9A", "#C9A86A",
                                                      "#F4F7FA")


def ripple_marks(xs, y, w, c="#DDEEF6"):
    return [stroke([(x, y), (x + 0.05, y + 0.012), (x + 0.1, y)], c, w * 0.7) for x in xs]


def _river(m, w):
    c = col(m["color"]) if m.get("color") else WATER
    g = VGroup(fill_only([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.5), (-1.0, 0.5)], GRASS, 1.0, smooth=False))
    bank = [(-1.0, 0.36), (-0.6, 0.3), (-0.2, 0.2), (0.15, 0.14), (0.5, 0.06), (0.8, 0.02), (1.0, 0.0)]
    bank2 = [(1.0, 0.12), (0.75, 0.16), (0.45, 0.22), (0.1, 0.3), (-0.25, 0.38), (-0.6, 0.44), (-1.0, 0.48)]
    g.add(blob(bank + bank2, c, w), *(ripple_marks((x,), y, w)[0] for x, y in ((-0.65, 0.38), (-0.25, 0.28), (0.2, 0.19), (0.6, 0.1))))
    g.add(*(stroke([(x, 0.02), (x - 0.02, 0.08)], GRASS_D, w * 0.6) for x in (-0.9, -0.6, 0.6, 0.9)))
    return g, None


def _lake(m, w):
    return VGroup(ell(0.0, 0.14, 1.5, 0.3, GRASS, 0), ell(0.0, 0.14, 1.2, 0.22, WATER, w),
                  ell(-0.1, 0.17, 0.5, 0.06, "#9FC5DA", 0), *ripple_marks((-0.3, 0.1, 0.3), 0.1, w),
                  *(stroke([(x, 0.2), (x + 0.01, 0.3)], GRASS_D, w * 0.8) for x in (-0.62, -0.58, 0.6, 0.64))), None


def _waterfall(m, w):
    g = VGroup(poly([(-0.6, 0.0), (-0.6, 0.9), (-0.15, 0.95), (-0.15, 0.0)], "#8A8478", w),
               poly([(0.15, 0.0), (0.15, 0.95), (0.6, 0.9), (0.6, 0.0)], "#8A8478", w),
               rect(-0.15, 0.1, 0.15, 0.95, WATER, w * 0.8),
               ell(0.0, 0.08, 0.7, 0.16, WATER_D, w))
    g.add(*(live(stroke([(x, 0.92), (x + 0.01, 0.5), (x - 0.01, 0.15)], "#DDEEF6", w), "steam") for x in (-0.08, 0.0, 0.08)),
          live(VGroup(*(circ(x, 0.12, 0.06, "#F4F7FA", w * 0.4) for x in (-0.18, -0.06, 0.06, 0.18))), "puff"),
          *(blob([(x - 0.12, 0.95), (x, 1.05), (x + 0.12, 0.95)], GRASS, w * 0.6) for x in (-0.4, 0.4)))
    return g, None


def _hills(m, w):
    return VGroup(blob([(-1.0, 0.0), (-1.0, 0.3), (-0.5, 0.55), (0.0, 0.35), (0.0, 0.0)], tint(GRASS, -0.1), w),
                  blob([(-0.3, 0.0), (-0.3, 0.25), (0.2, 0.5), (0.7, 0.3), (1.0, 0.25), (1.0, 0.0)], GRASS, w),
                  *(VGroup(line((x, y), (x, y + 0.07), WOOD_D, w), circ(x, y + 0.1, 0.045, GRASS_D, w * 0.5))
                    for x, y in ((-0.6, 0.45), (0.25, 0.42), (0.55, 0.3)))), None


def _mountainrange(m, w):
    g = VGroup()
    for x, h, c in ((-0.65, 0.75, "#8E8FA0"), (0.55, 0.85, "#8E8FA0"), (-0.05, 1.05, "#7A7C8E")):
        g.add(poly([(x - 0.55, 0.0), (x, h), (x + 0.55, 0.0)], c, w),
              poly([(x - 0.13, h - 0.24), (x, h), (x + 0.13, h - 0.24), (x + 0.05, h - 0.2), (x, h - 0.27), (x - 0.06, h - 0.19)], SNOW, w * 0.6),
              poly([(x, h), (x + 0.55, 0.0), (x + 0.15, 0.0)], tint(c, -0.15), 0))
    return g, None


def _snowpeak(m, w):
    return VGroup(poly([(-0.6, 0.0), (0.0, 1.0), (0.6, 0.0)], "#7A7C8E", w), poly([(0.0, 1.0), (0.6, 0.0), (0.2, 0.0)], "#676979", 0),
                  poly([(-0.24, 0.6), (0.0, 1.0), (0.24, 0.6), (0.12, 0.66), (0.04, 0.58), (-0.06, 0.66)], SNOW, w * 0.7),
                  live(blob([(0.1, 0.95), (0.4, 0.98), (0.55, 0.92), (0.3, 0.9)], "#F4F7FA", 0, op=0.8), "puff")), None


def _valley(m, w):
    return VGroup(poly([(-1.0, 0.0), (-1.0, 0.8), (-0.2, 0.05), (-0.2, 0.0)], "#8E8FA0", w),
                  poly([(1.0, 0.0), (1.0, 0.8), (0.2, 0.05), (0.2, 0.0)], "#7A7C8E", w),
                  poly([(-0.25, 0.0), (0.25, 0.0), (0.12, 0.08), (-0.12, 0.08)], GRASS, w * 0.6),
                  stroke([(0.0, 0.0), (0.04, 0.05), (-0.02, 0.1), (0.0, 0.16)], WATER, w * 2),
                  *(VGroup(line((x, 0.06), (x, 0.12), WOOD_D, w * 0.8), poly([(x - 0.05, 0.1), (x, 0.24), (x + 0.05, 0.1)], GRASS_D, w * 0.5))
                    for x in (-0.18, 0.18))), None


def _desert(m, w):
    return VGroup(blob([(-1.0, 0.0), (-1.0, 0.18), (-0.5, 0.36), (0.0, 0.2), (0.0, 0.0)], SAND, w),
                  blob([(-0.3, 0.0), (-0.3, 0.12), (0.3, 0.42), (1.0, 0.16), (1.0, 0.0)], tint(SAND, 0.08), w),
                  stroke([(0.3, 0.42), (0.45, 0.26), (0.7, 0.18)], SAND_D, w * 0.8),
                  circ(0.6, 0.85, 0.11, "#F2C14E", w * 0.6),
                  *(VGroup(rrect(x - 0.025, 0.2, x + 0.025, 0.42, 0.02, "#5E8A3E", w * 0.6),
                           rrect(x + 0.025, 0.3, x + 0.08, 0.34, 0.015, "#5E8A3E", w * 0.5)) for x in (-0.55,))), None


def _dune(m, w):
    return VGroup(blob([(-0.8, 0.0), (-0.4, 0.2), (0.1, 0.42), (0.35, 0.25), (0.8, 0.0)], SAND, w),
                  poly([(0.1, 0.42), (0.35, 0.25), (0.8, 0.0), (0.3, 0.0)], SAND_D, 0, op=0.6),
                  *(stroke([(x, y), (x + 0.12, y + 0.03), (x + 0.24, y)], SAND_D, w * 0.5) for x, y in ((-0.5, 0.1), (-0.2, 0.2)))), None


def _oasis(m, w):
    g = VGroup(ell(0.0, 0.05, 1.6, 0.18, SAND, w), ell(0.05, 0.08, 0.7, 0.1, WATER, w * 0.8))
    for x, h, lean in ((-0.35, 0.7, -0.15), (0.45, 0.6, 0.15)):
        g.add(stroke([(x, 0.06), (x + lean * 0.4, h * 0.5), (x + lean, h)], WOOD, w * 3))
        for a in (20, 70, 120, 160, 200, 340):
            r = math.radians(a)
            g.add(tube([(x + lean, h), (x + lean + 0.2 * math.cos(r), h + 0.12 * math.sin(r) - 0.04)], [0.06, 0.01], GRASS_D, w * 0.5))
    return g, None


def _forest(m, w):
    g = VGroup()
    for x, h, s in ((-0.7, 0.62, 0.9), (0.6, 0.66, 0.95), (-0.3, 0.8, 1.05), (0.25, 0.86, 1.1), (-0.02, 0.7, 1.0)):
        g.add(rect(x - 0.025, 0.0, x + 0.025, h * 0.4, WOOD_D, w * 0.7),
              poly([(x - 0.2 * s, h * 0.3), (x, h), (x + 0.2 * s, h * 0.3)], tint(GRASS_D, -0.05 + 0.1 * (x > 0)), w),
              poly([(x - 0.16 * s, h * 0.55), (x, h * 1.12), (x + 0.16 * s, h * 0.55)], tint(GRASS_D, 0.05), w))
    return g, None


def _jungle(m, w):
    g = VGroup()
    for x, y, r, c in ((-0.6, 0.45, 0.3, GRASS_D), (0.55, 0.5, 0.32, GRASS_D), (0.0, 0.6, 0.38, "#4F7F3A"),
                       (-0.3, 0.3, 0.25, GRASS), (0.3, 0.32, 0.26, GRASS)):
        g.add(rect(x - 0.03, 0.0, x + 0.03, y, WOOD_D, w * 0.7), circ(x, y + r * 0.6, r, c, w))
    g.add(*(stroke([(x, 0.9), (x + 0.03, 0.5), (x - 0.02, 0.2)], "#3E6E2E", w) for x in (-0.15, 0.2)),
          *(tube([(x, 0.0), (x + d, 0.22)], [0.07, 0.01], "#6E9A4A", w * 0.5) for x, d in ((-0.8, 0.1), (0.8, -0.1), (-0.1, 0.05))))
    return g, None


def _swamp(m, w):
    return VGroup(ell(0.0, 0.1, 1.8, 0.24, "#6E8A6A", w), ell(-0.2, 0.1, 0.6, 0.08, "#8AA58A", 0),
                  *(VGroup(stroke([(x, 0.1), (x + 0.02, 0.45)], "#6B5A3A", w), rrect(x - 0.015, 0.4, x + 0.035, 0.52, 0.02, "#6B4A2F", w * 0.5))
                    for x in (-0.6, -0.5, 0.55, 0.65)),
                  stroke([(0.1, 0.12), (0.12, 0.5), (0.2, 0.62)], "#4E4A3A", w * 2),
                  *(stroke([(0.12, 0.45), (0.12 + d, 0.36)], "#4E4A3A", w) for d in (-0.1, 0.12))), None


def _glacier(m, w):
    return VGroup(poly([(-1.0, 0.0), (-1.0, 0.7), (-0.6, 0.9), (0.0, 0.6), (0.5, 0.8), (1.0, 0.5), (1.0, 0.0)], "#DDEEF6", w),
                  poly([(-0.6, 0.9), (-0.3, 0.3), (0.0, 0.6)], "#BFDCEB", 0), poly([(0.5, 0.8), (0.6, 0.2), (1.0, 0.5)], "#BFDCEB", 0),
                  *(line((x, 0.0), (x + 0.05, 0.3), "#9FC5DA", w * 0.6) for x in (-0.7, -0.2, 0.3, 0.7)),
                  poly([(-1.05, 0.0), (1.05, 0.0), (1.0, -0.05), (-1.0, -0.05)], WATER, 0)), None


def _iceberg(m, w):
    return VGroup(poly([(-0.9, 0.0), (0.9, 0.0), (0.9, 0.06), (-0.9, 0.06)], WATER, 0),
                  poly([(-0.4, 0.06), (-0.25, 0.4), (-0.05, 0.55), (0.1, 0.42), (0.3, 0.48), (0.42, 0.06)], "#F4F7FA", w),
                  poly([(-0.05, 0.55), (0.1, 0.42), (0.0, 0.06), (-0.2, 0.06)], "#DDEEF6", 0),
                  poly([(-0.55, 0.0), (0.6, 0.0), (0.3, -0.5), (-0.3, -0.55)], "#BFDCEB", 0, op=0.6)), None


def _canyon(m, w):
    g = VGroup(poly([(-1.0, 0.0), (-1.0, 0.8), (-0.35, 0.8), (-0.25, 0.5), (-0.15, 0.2), (-0.1, 0.0)], "#C2552B", w),
               poly([(1.0, 0.0), (1.0, 0.8), (0.35, 0.8), (0.28, 0.45), (0.15, 0.2), (0.1, 0.0)], "#A84A26", w),
               poly([(-0.1, 0.0), (0.1, 0.0), (0.06, 0.04), (-0.06, 0.04)], WATER, 0))
    for y in (0.2, 0.4, 0.6):
        g.add(line((-1.0, y), (-0.3 + (0.8 - y) * 0.2, y), "#8E3A1E", w * 0.5), line((1.0, y), (0.3 - (0.8 - y) * 0.15, y), "#7A3218", w * 0.5))
    return g, None


def _cliff(m, w):
    return VGroup(poly([(-0.6, 0.0), (-0.6, 0.85), (0.25, 0.85), (0.3, 0.6), (0.22, 0.35), (0.35, 0.0)], "#8A8478", w),
                  poly([(-0.65, 0.85), (0.3, 0.85), (0.25, 0.92), (-0.6, 0.92)], GRASS, w * 0.7),
                  *(line((x, y), (x + 0.15, y - 0.03), "#6E685E", w * 0.5) for x, y in ((-0.4, 0.6), (-0.2, 0.35), (-0.45, 0.2))),
                  poly([(0.3, 0.0), (0.9, 0.0), (0.9, 0.08), (0.32, 0.08)], WATER, 0)), None


def _cave(m, w):
    return VGroup(blob([(-0.8, 0.0), (-0.7, 0.45), (-0.3, 0.75), (0.25, 0.8), (0.7, 0.5), (0.8, 0.0)], "#8A8478", w),
                  blob([(-0.35, 0.0), (-0.32, 0.28), (-0.1, 0.45), (0.15, 0.42), (0.32, 0.25), (0.35, 0.0)], "#2B2826", w),
                  *(poly([(x - 0.03, 0.42 - d), (x + 0.03, 0.42 - d), (x, 0.32 - d)], "#8A8478", w * 0.4) for x, d in ((-0.12, 0.0), (0.05, 0.01), (0.18, 0.04))),
                  *(stroke([(x, 0.7), (x + 0.03, 0.78)], GRASS_D, w) for x in (-0.3, 0.0, 0.3))), None


def _beach(m, w):
    return VGroup(poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.22), (-1.0, 0.36)], SAND, w * 0.6),
                  poly([(-1.0, 0.36), (1.0, 0.22), (1.0, 0.5), (-1.0, 0.5)], WATER, w * 0.6),
                  stroke([(-1.0, 0.36), (-0.5, 0.31), (0.0, 0.3), (0.5, 0.25), (1.0, 0.22)], "#F4F7FA", w * 2),
                  *ripple_marks((-0.6, -0.1, 0.4), 0.42, w),
                  ell(0.5, 0.06, 0.12, 0.05, "#F2C8B0", w * 0.5), circ(-0.6, 0.85, 0.1, "#F2C14E", w * 0.6)), None


def _ocean(m, w):
    g = VGroup(rect(-1.0, 0.0, 1.0, 0.45, WATER_D, w * 0.6), rect(-1.0, 0.3, 1.0, 0.45, WATER, 0))
    for r in range(3):
        g.add(*(live(stroke([(x, 0.08 + r * 0.13), (x + 0.07, 0.11 + r * 0.13), (x + 0.14, 0.08 + r * 0.13)], "#DDEEF6", w), "steam")
                for x in np.arange(-0.9 + (r % 2) * 0.1, 0.9, 0.3)))
    return g, None


def _coast(m, w):
    return VGroup(rect(-1.0, 0.0, 1.0, 0.45, WATER, w * 0.6),
                  blob([(-1.0, 0.0), (-1.0, 0.6), (-0.4, 0.55), (-0.1, 0.35), (0.1, 0.15), (0.3, 0.0)], GRASS, w),
                  stroke([(-0.1, 0.35), (0.1, 0.15), (0.3, 0.0)], SAND, w * 3),
                  *ripple_marks((0.4, 0.7), 0.25, w), *ripple_marks((0.2, 0.55), 0.1, w)), None


def _delta(m, w):
    g = VGroup(poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.6), (-1.0, 0.6)], GRASS, w * 0.5),
               poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.12), (-1.0, 0.12)], WATER_D, 0))
    for x1 in (-0.7, -0.35, 0.0, 0.35, 0.7):
        g.add(stroke([(0.0, 0.6), (x1 * 0.4, 0.35), (x1, 0.12)], WATER, w * 2.4))
    return g, None


def _plateau(m, w):
    return VGroup(poly([(-1.0, 0.0), (-0.7, 0.55), (0.6, 0.55), (1.0, 0.0)], "#B5875E", w),
                  poly([(-0.72, 0.55), (0.62, 0.55), (0.58, 0.6), (-0.68, 0.6)], GRASS, w * 0.7),
                  line((-0.85, 0.25), (0.85, 0.25), "#9A6E48", w * 0.4),
                  line((-0.78, 0.4), (0.7, 0.4), "#9A6E48", w * 0.4)), None


def _meadow(m, w):
    g = VGroup(blob([(-1.0, 0.0), (-1.0, 0.25), (0.0, 0.32), (1.0, 0.25), (1.0, 0.0)], GRASS, w))
    for i, x in enumerate(np.linspace(-0.85, 0.85, 12)):
        y = 0.1 + 0.12 * ((i * 7) % 5) / 5
        g.add(stroke([(x, y - 0.06), (x, y)], GRASS_D, w * 0.6),
              circ(x, y + 0.015, 0.02, ("#F2C14E", "#F7F5F0", "#D46A9A", "#6FA8DC")[i % 4], w * 0.3))
    return g, None


def _acacia(m, w):
    return VGroup(stroke([(0.0, 0.0), (0.02, 0.3), (-0.12, 0.55)], WOOD_D, w * 3), stroke([(0.02, 0.3), (0.2, 0.55)], WOOD_D, w * 2.2),
                  blob([(-0.55, 0.55), (-0.3, 0.68), (0.2, 0.7), (0.55, 0.6), (0.3, 0.52), (-0.3, 0.5)], "#6E8F3A", w)), None


def _bamboo(m, w):
    g = VGroup()
    for x, h in ((-0.12, 0.95), (0.0, 1.05), (0.12, 0.9)):
        g.add(rect(x - 0.03, 0.0, x + 0.03, h, "#9DB85A", w * 0.8), *(line((x - 0.03, y), (x + 0.03, y), "#5E7A2E", w * 0.8) for y in np.arange(0.15, h, 0.17)))
        g.add(*(tube([(x, y), (x + d * 0.18, y + 0.05)], [0.04, 0.005], "#6E9A4A", w * 0.4) for y, d in ((h * 0.6, 1), (h * 0.8, -1), (h, 1))))
    return g, None


def _banyan(m, w):
    g = VGroup(rect(-0.1, 0.0, 0.1, 0.55, WOOD_D, w),
               *(line((x, 0.6), (x + 0.01, 0.0), "#8C6A42", w * 0.7) for x in (-0.6, -0.45, -0.3, 0.3, 0.45, 0.6)),
               blob([(-0.8, 0.5), (-0.75, 0.75), (-0.4, 0.95), (0.0, 1.0), (0.45, 0.95), (0.8, 0.75), (0.8, 0.5), (0.0, 0.55)], "#4F7F3A", w),
               *(circ(x, y, 0.13, "#5E8A3E", w * 0.4) for x, y in ((-0.45, 0.8), (0.0, 0.88), (0.45, 0.8))))
    return g, None


def _terraces(m, w):
    g = VGroup()
    for i in range(5):
        y = i * 0.15
        hw = 1.0 - i * 0.15
        g.add(poly([(-hw, y), (hw, y), (hw - 0.05, y + 0.15), (-hw + 0.05, y + 0.15)], tint(GRASS, 0.05 * (i % 2)), w * 0.7),
              line((-hw + 0.05, y + 0.13), (hw - 0.05, y + 0.13), "#7FA8C9", w * 1.2),
              *(stroke([(x, y + 0.04), (x, y + 0.1)], GRASS_D, w * 0.5) for x in np.linspace(-hw + 0.15, hw - 0.15, 7)))
    return g, None


def _mangrove(m, w):
    g = VGroup(rect(-1.0, 0.0, 1.0, 0.12, "#5E8A8A", 0))
    for x in (-0.45, 0.4):
        g.add(*(stroke([(x + d, 0.0), (x + d * 0.3, 0.15), (x, 0.3)], WOOD_D, w * 1.2) for d in (-0.2, -0.08, 0.08, 0.2)),
              rect(x - 0.03, 0.3, x + 0.03, 0.5, WOOD_D, w * 0.6), circ(x, 0.62, 0.22, "#4F7F3A", w))
    return g, None


def _reef(m, w):
    g = VGroup(rect(-0.9, 0.0, 0.9, 0.7, "#3E7CB1", w * 0.6), rect(-0.9, 0.0, 0.9, 0.08, SAND, 0))
    for x, c in ((-0.55, "#E07B39"), (-0.1, "#D46A9A"), (0.4, "#F2C14E")):
        g.add(*(stroke([(x, 0.06), (x + d, 0.2), (x + d * 1.4, 0.32)], c, w * 2.4) for d in (-0.08, 0.0, 0.08)))
    g.add(*(VGroup(ell(x, y, 0.12, 0.06, c, w * 0.5), poly([(x - 0.06, y), (x - 0.1, y + 0.03), (x - 0.1, y - 0.03)], c, w * 0.5))
            for x, y, c in ((0.1, 0.5, "#F2C14E"), (-0.4, 0.45, "#E07B39"))),
          *(circ(x, y, 0.015, "#DDEEF6", w * 0.3) for x, y in ((0.2, 0.58), (0.22, 0.63), (-0.32, 0.55))))
    return g, None


def _geyser(m, w):
    return VGroup(ell(0.0, 0.03, 0.7, 0.1, "#B5AD9C", w), ell(0.0, 0.05, 0.2, 0.04, WATER, w * 0.5),
                  live(VGroup(tube([(0.0, 0.05), (0.0, 0.5), (0.0, 0.8)], [0.12, 0.18, 0.28], "#DDEEF6", w * 0.6),
                              *(circ(x, y, 0.07, "#F4F7FA", w * 0.4) for x, y in ((-0.12, 0.85), (0.1, 0.88), (0.0, 0.95)))), "puff")), None


def _crater(m, w):
    return VGroup(ell(0.0, 0.1, 1.4, 0.28, "#9A948A", w), ell(0.0, 0.1, 1.0, 0.18, "#6E685E", w),
                  ell(0.08, 0.08, 0.6, 0.1, "#57524A", 0),
                  *(circ(x, y, 0.03, "#8A8478", w * 0.4) for x, y in ((-0.6, 0.02), (0.62, 0.05), (0.4, 0.22)))), None


def _road(m, w):
    return VGroup(poly([(-1.0, 0.0), (1.0, 0.0), (0.2, 0.6), (-0.2, 0.6)], "#5E5A55", w),
                  *(poly([(-0.02 + 0.015 * k, 0.05 + k * 0.12), (0.02 - 0.015 * k, 0.05 + k * 0.12),
                          (0.016 - 0.012 * k, 0.1 + k * 0.12), (-0.016 + 0.012 * k, 0.1 + k * 0.12)], "#F7F5F0", 0) for k in range(4)),
                  poly([(-1.0, 0.0), (-0.2, 0.6), (-0.28, 0.6), (-1.1, 0.0)], GRASS, 0),
                  poly([(1.0, 0.0), (0.2, 0.6), (0.28, 0.6), (1.1, 0.0)], GRASS, 0)), None


def _trail(m, w):
    return VGroup(blob([(-1.0, 0.0), (-1.0, 0.4), (1.0, 0.4), (1.0, 0.0)], GRASS, 0),
                  stroke([(-0.2, 0.0), (0.1, 0.12), (-0.15, 0.24), (0.05, 0.36)], "#C9A86A", w * 6),
                  *(circ(x, y, 0.02, "#8A8478", w * 0.4) for x, y in ((0.2, 0.08), (-0.3, 0.2), (0.18, 0.3)))), None


def _village(m, w):
    g = VGroup(ell(0.0, 0.0, 2.0, 0.12, GRASS, 0))
    for x, s, c in ((-0.65, 0.9, "#C9A27A"), (-0.2, 1.1, "#D9B98A"), (0.3, 0.95, "#C9A27A"), (0.7, 0.8, "#D9B98A")):
        g.add(rect(x - 0.17 * s, 0.0, x + 0.17 * s, 0.24 * s, c, w), poly([(x - 0.22 * s, 0.24 * s), (x, 0.42 * s), (x + 0.22 * s, 0.24 * s)], "#B5873A", w),
              rect(x - 0.04 * s, 0.0, x + 0.04 * s, 0.13 * s, "#5A4630", w * 0.6))
    g.add(VGroup(rect(0.98, 0.0, 1.02, 0.25, WOOD_D, w * 0.6), circ(1.0, 0.3, 0.1, GRASS_D, w * 0.6)))
    return g, None


def _skyline(m, w):
    c = col(m["color"]) if m.get("color") else "#5B6E8C"
    g = VGroup()
    for x, wd, h in ((-0.85, 0.22, 0.6), (-0.6, 0.18, 0.9), (-0.38, 0.24, 0.7), (-0.12, 0.2, 1.1), (0.1, 0.22, 0.8), (0.34, 0.18, 1.0),
                     (0.56, 0.24, 0.65), (0.82, 0.2, 0.85)):
        g.add(rect(x - wd / 2, 0.0, x + wd / 2, h, tint(c, 0.12 * ((x * 10) % 3 - 1)), w * 0.8),
              *(rect(x - wd / 2 + 0.04 + i * 0.06, y, x - wd / 2 + 0.07 + i * 0.06, y + 0.04, "#F2E3A8", 0)
                for i in range(int(wd / 0.06) - 1) for y in np.arange(0.1, h - 0.05, 0.12)))
    return g, None


def _port(m, w):
    g = VGroup(rect(-1.0, 0.0, 1.0, 0.12, WATER, 0), rect(-1.0, 0.12, -0.1, 0.22, "#8A8478", w),
               VGroup(line((-0.6, 0.22), (-0.6, 0.85), "#E07B39", w * 2), line((-0.6, 0.85), (-0.15, 0.85), "#E07B39", w * 2),
                      line((-0.25, 0.85), (-0.25, 0.55), "#3A3631", w * 0.6), line((-0.6, 0.65), (-0.4, 0.85), "#E07B39", w)),
               *(rect(x, y, x + 0.14, y + 0.08, c_, w * 0.5) for x, y, c_ in ((-0.9, 0.22, "#B83227"), (-0.75, 0.22, "#3E7CB1"),
                                                                              (-0.9, 0.3, "#4F9A6A"))),
               blob([(0.0, 0.18), (0.08, 0.06), (0.85, 0.06), (0.95, 0.2)], "#2F3B4C", w),
               *(rect(x, 0.2, x + 0.12, 0.3, c_, w * 0.5) for x, c_ in ((0.15, "#B83227"), (0.3, "#F2C14E"), (0.45, "#4F9A6A"), (0.6, "#3E7CB1"))),
               rect(0.75, 0.2, 0.88, 0.42, "#F3EEE4", w * 0.6))
    return g, None


def _mine(m, w):
    return VGroup(blob([(-0.8, 0.0), (-0.6, 0.5), (-0.1, 0.7), (0.5, 0.6), (0.8, 0.0)], "#8A7A66", w),
                  poly([(-0.25, 0.0), (-0.25, 0.35), (0.25, 0.35), (0.25, 0.0)], "#2B2826", w),
                  rect(-0.3, 0.33, 0.3, 0.4, WOOD, w), rect(-0.3, 0.0, -0.24, 0.36, WOOD, w), rect(0.24, 0.0, 0.3, 0.36, WOOD, w),
                  line((-0.6, 0.02), (0.6, 0.02), "#6E747A", w * 1.2), line((-0.6, 0.06), (0.6, 0.06), "#6E747A", w * 1.2),
                  VGroup(poly([(0.35, 0.08), (0.62, 0.08), (0.58, 0.2), (0.39, 0.2)], "#6E747A", w), circ(0.42, 0.07, 0.03, "#3A3631", 0),
                         circ(0.56, 0.07, 0.03, "#3A3631", 0), *(circ(x, 0.22, 0.03, "#3A3631", w * 0.3) for x in (0.44, 0.5, 0.56)))), None


def _quarry(m, w):
    g = VGroup()
    for i in range(4):
        y = i * 0.14
        g.add(poly([(-0.9 + i * 0.12, y), (0.9 - i * 0.12, y), (0.9 - i * 0.12, y + 0.14), (-0.9 + i * 0.12, y + 0.14)],
                   tint("#B5AD9C", -0.08 * i), w * 0.8))
    g.add(*(rect(x, 0.0, x + 0.12, 0.08, "#D6CDB8", w * 0.5) for x in (-0.3, -0.1, 0.12)))
    return g, None


def _sunset(m, w):
    g = VGroup(rect(-1.0, 0.0, 1.0, 0.7, "#F2A65A", 0), rect(-1.0, 0.35, 1.0, 0.7, "#E8724A", 0),
               blob(zoo.P._arc(0.0, 0.2, 0.25, 0, 180, 16), "#F7D06A", w), rect(-1.0, 0.0, 1.0, 0.2, "#3E5C82", w * 0.5))
    g.add(*(stroke([(x, 0.1), (x + 0.15, 0.1)], "#F7D06A", w) for x in (-0.15, 0.0)),
          *(stroke([(x, y), (x + 0.05, y + 0.03), (x + 0.1, y)], "#3A2A1E", w * 0.8) for x, y in ((-0.6, 0.55), (-0.45, 0.6))))
    return g, None


def _nightsky(m, w):
    g = VGroup(rect(-1.0, 0.0, 1.0, 0.8, "#1E2A4A", 0), circ(0.6, 0.6, 0.1, "#F4EFD8", w * 0.5), circ(0.64, 0.63, 0.085, "#1E2A4A", 0))
    for i in range(18):
        x, y = -0.95 + (i * 0.37) % 1.8, 0.08 + (i * 0.53) % 0.68
        g.add(live(glint(x, y, 0.02 + 0.01 * (i % 3), w * 0.5), "puff"))
    return g, None


# -- around the house, school and town -------------------------------------------------------------------------

def _clothesline(m, w):
    g = VGroup(line((-0.6, 0.0), (-0.6, 0.6), WOOD_D, w * 1.6), line((0.6, 0.0), (0.6, 0.6), WOOD_D, w * 1.6),
               stroke([(-0.6, 0.58), (0.0, 0.52), (0.6, 0.58)], "#6E6458", w * 0.8))
    for x, c, kind in ((-0.35, "#3E7CB1", 0), (0.0, "#E07B39", 1), (0.32, "#F7F5F0", 0)):
        if kind:
            g.add(poly([(x - 0.12, 0.52), (x + 0.12, 0.52), (x + 0.12, 0.28), (x - 0.12, 0.28)], c, w * 0.7))
        else:
            g.add(poly([(x - 0.1, 0.54), (x + 0.1, 0.54), (x + 0.14, 0.48), (x + 0.07, 0.46), (x + 0.07, 0.3), (x - 0.07, 0.3),
                        (x - 0.07, 0.46), (x - 0.14, 0.48)], c, w * 0.7))
    return g, None


def _cradle(m, w):
    return VGroup(stroke(zoo.P._arc(0.0, 0.3, 0.3, 200, 340, 12), WOOD, w * 3), blob(zoo.P._arc(0.0, 0.32, 0.26, 180, 360, 12), "#F3E1C8", w),
                  line((-0.26, 0.32), (0.26, 0.32), WOOD_D, w * 1.6), *(line((x, 0.32), (x * 1.2, 0.0), WOOD_D, w * 1.4) for x in (-0.22, 0.22)),
                  circ(-0.12, 0.36, 0.06, "#EFC9A6", w * 0.6), blob([(-0.08, 0.32), (0.2, 0.32), (0.18, 0.4), (-0.06, 0.4)], "#9FC5DA", w * 0.6)), None


def _mat(m, w):
    c = col(m["color"]) if m.get("color") else "#C9A44E"
    g = VGroup(poly([(-0.5, 0.0), (0.5, 0.0), (0.4, 0.12), (-0.4, 0.12)], c, w))
    g.add(*(line((-0.45 + i * 0.1, 0.0), (-0.36 + i * 0.08, 0.12), tint(c, -0.2), w * 0.5) for i in range(10)),
          line((-0.47, 0.06), (0.47, 0.06), "#B83227", w * 1.2))
    return g, None


def _pillow(m, w):
    return VGroup(blob([(-0.25, 0.02), (-0.28, 0.1), (-0.25, 0.2), (0.25, 0.2), (0.28, 0.1), (0.25, 0.02)], col(m["color"]) if m.get("color") else "#F3EEE4", w),
                  stroke([(-0.18, 0.12), (0.18, 0.12)], "#C9C2B2", w * 0.5)), None


def _iron(m, w):
    return VGroup(poly([(-0.2, 0.0), (0.22, 0.0), (0.1, 0.12), (-0.2, 0.12)], "#C9CED2", w), poly([(-0.2, 0.0), (0.22, 0.0), (0.2, 0.02), (-0.2, 0.02)], "#6E747A", 0),
                  stroke([(-0.15, 0.12), (-0.12, 0.22), (0.05, 0.22), (0.08, 0.12)], "#3A3631", w * 2),
                  live(stroke([(0.15, 0.06), (0.2, 0.14), (0.16, 0.22)], "#C9C2B2", w * 0.8), "steam")), None


def _sewingmachine(m, w):
    return VGroup(rect(-0.3, 0.0, 0.3, 0.05, WOOD, w), poly([(-0.22, 0.05), (-0.22, 0.3), (0.2, 0.3), (0.2, 0.22), (-0.12, 0.22), (-0.12, 0.05)], "#2B2826", w),
                  rect(0.14, 0.12, 0.2, 0.22, "#2B2826", w * 0.6), line((0.17, 0.12), (0.17, 0.06), "#C9CED2", w * 0.8),
                  circ(-0.26, 0.24, 0.05, "#6E747A", w * 0.6), *(line((x, 0.26), (x + 0.03, 0.29), GOLD, w * 0.5) for x in (-0.05, 0.03))), None


def _washingmachine(m, w):
    return VGroup(rrect(-0.2, 0.0, 0.2, 0.46, 0.03, "#F3EEE4", w), rect(-0.2, 0.36, 0.2, 0.46, "#E0DCD2", w * 0.6),
                  circ(0.0, 0.18, 0.13, "#9AA3A9", w), circ(0.0, 0.18, 0.1, "#9FC5DA", w * 0.6),
                  *(circ(x, 0.41, 0.02, c, 0) for x, c in ((0.1, RED), (0.15, "#4F9A6A"))), rect(-0.16, 0.39, -0.02, 0.43, "#3A3631", 0)), None


def _dustbin(m, w):
    c = col(m["color"]) if m.get("color") else "#4F9A6A"
    return VGroup(poly([(-0.14, 0.0), (0.14, 0.0), (0.17, 0.34), (-0.17, 0.34)], c, w), rrect(-0.19, 0.34, 0.19, 0.39, 0.02, tint(c, -0.2), w),
                  *(line((x, 0.04), (x * 1.15, 0.3), tint(c, -0.25), w * 0.6) for x in (-0.07, 0.0, 0.07)),
                  stroke([(-0.05, 0.39), (-0.04, 0.43), (0.04, 0.43), (0.05, 0.39)], "#3A3631", w * 1.2)), None


def _recycle(m, w):
    g = VGroup()
    for k in range(3):
        a0 = 90 + k * 120 + 15
        a1 = a0 + 85
        g.add(stroke(zoo.P._arc(0.0, 0.25, 0.2, a0, a1, 10), "#4F9A6A", w * 3.2))
        r = math.radians(a1 + 6)
        t = np.array([-math.sin(r), math.cos(r)])
        c = np.array([0.2 * math.cos(r), 0.25 + 0.2 * math.sin(r)])
        nrm = np.array([math.cos(r), math.sin(r)])
        g.add(poly([tuple(c + t * 0.07), tuple(c + nrm * 0.06), tuple(c - nrm * 0.06)], "#4F9A6A", w * 0.5))
    return g, None


def _watertank(m, w):
    return VGroup(*(line((x, 0.0), (x * 0.8, 0.3), "#6E747A", w * 1.6) for x in (-0.18, 0.18)), rect(-0.22, 0.28, 0.22, 0.32, "#6E747A", w * 0.6),
                  rrect(-0.2, 0.32, 0.2, 0.7, 0.05, "#2B2826", w), *(line((-0.2, y), (0.2, y), "#4A4642", w * 0.6) for y in (0.45, 0.58)),
                  ell(0.0, 0.7, 0.24, 0.05, "#3A3631", w * 0.6)), None


def _tap(m, w):
    return VGroup(rect(-0.3, 0.3, -0.22, 0.42, "#9AA3A9", w), tube([(-0.22, 0.36), (0.0, 0.36), (0.06, 0.3), (0.06, 0.24)], [0.05, 0.05, 0.04, 0.04], "#C9CED2", w),
                  rect(-0.12, 0.39, -0.04, 0.46, "#6E747A", w * 0.6), line((-0.17, 0.46), (0.01, 0.46), "#6E747A", w * 1.6),
                  live(VGroup(*(ell(0.06, y, 0.025, 0.04, WATER, w * 0.3) for y in (0.17, 0.08, 0.0))), "steam")), None


def _pipe(m, w):
    return VGroup(rect(-0.8, 0.05, 0.3, 0.15, "#9AA3A9", w), tube([(0.3, 0.1), (0.42, 0.1), (0.48, 0.22), (0.48, 0.5)], [0.1, 0.1, 0.1, 0.1], "#9AA3A9", w),
                  *(rect(x, 0.03, x + 0.04, 0.17, "#6E747A", w * 0.6) for x in (-0.5, -0.1)), rect(0.43, 0.38, 0.53, 0.42, "#6E747A", w * 0.6)), None


def _crayons(m, w):
    g = VGroup(rect(-0.2, 0.0, 0.2, 0.18, "#F2C14E", w), rect(-0.2, 0.05, 0.2, 0.12, "#3E7CB1", w * 0.5))
    for i, c in enumerate((RED, "#E07B39", "#4F9A6A", "#3E7CB1", "#7A4C8C", "#2B2826")):
        x = -0.16 + i * 0.065
        g.add(rect(x - 0.022, 0.18, x + 0.022, 0.3 + 0.02 * (i % 2), c, w * 0.6), poly([(x - 0.022, 0.3 + 0.02 * (i % 2)), (x + 0.022, 0.3 + 0.02 * (i % 2)), (x, 0.35 + 0.02 * (i % 2))], c, w * 0.5))
    return g, None


def _ruler(m, w):
    ticks = [line((x, 0.08), (x, 0.08 - (0.04 if i % 5 == 0 else 0.02)), "#3A3631", w * 0.5)
             for i, x in enumerate(np.linspace(-0.36, 0.36, 21))]
    return VGroup(rect(-0.4, 0.0, 0.4, 0.08, "#F2D27A", w), *ticks), None


def _slate(m, w):
    return VGroup(rect(-0.25, 0.0, 0.25, 0.34, WOOD, w), rect(-0.21, 0.04, 0.21, 0.3, "#2F3A36", w * 0.5),
                  letters(m.get("label") or "a b c", 0.0, 0.17, 0.08, "#F3EEE4")), None


def _qrcode(m, w):
    g = VGroup(rrect(-0.2, 0.0, 0.2, 0.4, 0.02, "#F7F5F0", w))
    import random
    rnd = random.Random(7)
    for i in range(9):
        for j in range(9):
            if (i < 3 and j < 3) or (i < 3 and j > 5) or (i > 5 and j < 3):
                continue
            if rnd.random() < 0.5:
                g.add(rect(-0.16 + i * 0.035, 0.04 + j * 0.035, -0.125 + i * 0.035, 0.075 + j * 0.035, "#22201E", 0))
    for x, y in ((-0.16, 0.04), (-0.16, 0.25), (0.05, 0.25)):
        g.add(rect(x, y, x + 0.105, y + 0.105, "#22201E", 0), rect(x + 0.02, y + 0.02, x + 0.085, y + 0.085, "#F7F5F0", 0),
              rect(x + 0.035, y + 0.035, x + 0.07, y + 0.07, "#22201E", 0))
    return g, None


def _conveyor(m, w):
    g = VGroup(rrect(-0.6, 0.18, 0.6, 0.26, 0.04, "#3A3631", w), *(line((x, 0.0), (x, 0.18), "#6E747A", w * 1.4) for x in (-0.5, 0.5)),
               *(circ(x, 0.22, 0.03, "#9AA3A9", w * 0.4) for x in np.linspace(-0.55, 0.55, 8)))
    g.add(*(rect(x - 0.08, 0.26, x + 0.08, 0.38, "#C99A62", w * 0.8) for x in (-0.35, 0.0, 0.35)))
    return g, None


def _robotarm(m, w):
    return VGroup(rect(-0.18, 0.0, 0.18, 0.08, "#3A3631", w), circ(0.0, 0.12, 0.06, "#F2A93B", w),
                  tube([(0.0, 0.12), (0.15, 0.45)], [0.08, 0.07], "#F2A93B", w), circ(0.15, 0.45, 0.05, "#3A3631", w * 0.6),
                  tube([(0.15, 0.45), (0.42, 0.4)], [0.06, 0.05], "#F2A93B", w),
                  stroke([(0.42, 0.4), (0.5, 0.44), (0.54, 0.4)], "#3A3631", w * 1.6), stroke([(0.42, 0.4), (0.5, 0.36), (0.54, 0.38)], "#3A3631", w * 1.6)), None


def _ecg(m, w):
    return VGroup(rrect(-0.3, 0.0, 0.3, 0.36, 0.03, "#3A3631", w), rect(-0.26, 0.06, 0.26, 0.32, "#1E2A2A", 0),
                  live(stroke([(-0.24, 0.18), (-0.1, 0.18), (-0.06, 0.26), (-0.02, 0.1), (0.02, 0.18), (0.24, 0.18)], "#7FD18B", w), "puff"),
                  letters("72", 0.18, 0.27, 0.04, "#7FD18B")), None


def _hospitalbed(m, w):
    return VGroup(rect(-0.45, 0.18, 0.45, 0.26, "#F7F5F0", w), rect(-0.45, 0.12, 0.45, 0.18, "#9AA3A9", w * 0.6),
                  stroke([(-0.45, 0.12), (-0.45, 0.45)], "#9AA3A9", w * 2), stroke([(0.45, 0.12), (0.45, 0.32)], "#9AA3A9", w * 2),
                  *(line((x, 0.12), (x, 0.03), "#6E747A", w * 1.2) for x in (-0.38, 0.38)), *(circ(x, 0.03, 0.025, "#3A3631", 0) for x in (-0.38, 0.38)),
                  rrect(-0.42, 0.26, -0.2, 0.32, 0.02, "#F3EEE4", w * 0.6), rect(-0.18, 0.24, 0.42, 0.3, "#9FC5DA", w * 0.6)), None


def _xray(m, w):
    g = VGroup(rect(-0.25, 0.0, 0.25, 0.5, "#1E2A3A", w), line((0.0, 0.08), (0.0, 0.44), "#DDEEF6", w * 1.6))
    for k in range(5):
        y = 0.38 - k * 0.06
        g.add(stroke([(0.0, y), (-0.12, y - 0.02), (-0.18, y - 0.06)], "#DDEEF6", w * 0.8), stroke([(0.0, y), (0.12, y - 0.02), (0.18, y - 0.06)], "#DDEEF6", w * 0.8))
    return g, None


def _garbage(m, w):
    return VGroup(blob([(-0.4, 0.0), (-0.35, 0.15), (-0.15, 0.25), (0.1, 0.28), (0.3, 0.18), (0.42, 0.0)], "#6E6458", w),
                  blob([(-0.2, 0.18), (-0.18, 0.32), (-0.05, 0.36), (0.02, 0.24)], "#2B2826", w * 0.7),
                  rect(0.1, 0.2, 0.2, 0.32, "#9FC5DA", w * 0.6), poly([(-0.35, 0.1), (-0.25, 0.22), (-0.2, 0.12)], "#E07B39", w * 0.5),
                  ell(0.25, 0.12, 0.12, 0.06, "#C9CED2", w * 0.5), stroke([(0.05, 0.3), (0.0, 0.4), (0.06, 0.48)], "#9A9283", w * 0.6)), None


def _smog(m, w):
    return VGroup(*(live(blob([(x - 0.3, y), (x - 0.2, y + 0.12), (x, y + 0.16), (x + 0.2, y + 0.12), (x + 0.3, y), (x, y - 0.05)], c, w * 0.4, op=0.85), "puff")
                    for x, y, c in ((-0.45, 0.2, "#9A9488"), (0.1, 0.32, "#8A847A"), (0.5, 0.15, "#A8A398"), (-0.1, 0.05, "#B5AFA4")))), None


def _chargingstation(m, w):
    return VGroup(rrect(-0.12, 0.0, 0.12, 0.6, 0.03, "#4F9A6A", w), rect(-0.08, 0.36, 0.08, 0.52, "#1E2A2A", w * 0.5),
                  poly([(0.0, 0.5), (-0.03, 0.44), (0.0, 0.44), (-0.02, 0.38), (0.04, 0.46), (0.01, 0.46)], "#F2C14E", 0),
                  stroke([(0.12, 0.3), (0.25, 0.25), (0.3, 0.1), (0.35, 0.05)], "#2B2826", w * 1.6), rect(0.33, 0.0, 0.4, 0.08, "#2B2826", w * 0.5)), None


def _trafficcone(m, w):
    return VGroup(rect(-0.14, 0.0, 0.14, 0.03, "#E07B39", w), poly([(-0.1, 0.03), (0.1, 0.03), (0.02, 0.36), (-0.02, 0.36)], "#E07B39", w),
                  poly([(-0.075, 0.12), (0.075, 0.12), (0.06, 0.18), (-0.06, 0.18)], "#F7F5F0", 0),
                  poly([(-0.045, 0.24), (0.045, 0.24), (0.035, 0.28), (-0.035, 0.28)], "#F7F5F0", 0)), None


def _railtrack(m, w):
    g = VGroup(poly([(-1.0, 0.0), (1.0, 0.0), (0.9, 0.08), (-0.9, 0.08)], "#9A948A", 0))
    g.add(*(rect(x - 0.04, 0.01, x + 0.04, 0.07, WOOD_D, w * 0.5) for x in np.linspace(-0.9, 0.9, 12)),
          line((-1.0, 0.025), (1.0, 0.025), "#6E747A", w * 1.6), line((-0.95, 0.055), (0.95, 0.055), "#6E747A", w * 1.6))
    return g, None


def _station(m, w):
    return VGroup(rect(-0.8, 0.0, 0.8, 0.08, "#9A948A", w), *(line((x, 0.08), (x, 0.55), "#6E747A", w * 1.6) for x in (-0.6, 0.0, 0.6)),
                  poly([(-0.85, 0.55), (0.85, 0.55), (0.75, 0.65), (-0.75, 0.65)], "#B83227", w),
                  rect(-0.25, 0.4, 0.25, 0.5, "#F2C14E", w * 0.6), letters(m.get("label") or "STATION", 0.0, 0.45, 0.05, "#22201E"),
                  rect(-0.5, 0.08, -0.2, 0.18, WOOD, w * 0.6), line((0.35, 0.3), (0.35, 0.42), "#3A3631", w), circ(0.35, 0.44, 0.04, "#F7F5F0", w * 0.6)), None


def _busstop(m, w):
    return VGroup(line((-0.3, 0.0), (-0.3, 0.55), "#6E747A", w * 1.6), line((0.3, 0.0), (0.3, 0.55), "#6E747A", w * 1.6),
                  poly([(-0.36, 0.55), (0.36, 0.55), (0.32, 0.6), (-0.32, 0.6)], "#3E7CB1", w), rect(-0.3, 0.15, 0.3, 0.19, WOOD, w * 0.6),
                  line((0.45, 0.0), (0.45, 0.7), "#6E747A", w * 1.2), circ(0.45, 0.72, 0.07, "#4F9A6A", w * 0.6), letters("BUS", 0.45, 0.72, 0.035, "#F7F5F0")), None


def _milestone(m, w):
    return VGroup(poly([(-0.12, 0.0), (0.12, 0.0), (0.12, 0.25), *zoo.P._arc(0.0, 0.25, 0.12, 0, 180, 10), (-0.12, 0.25)], "#F7F5F0", w),
                  blob(zoo.P._arc(0.0, 0.25, 0.12, 0, 180, 10) + [(-0.12, 0.25)], "#E8A23B", w * 0.6),
                  letters(m.get("label") or "12", 0.0, 0.13, 0.06, "#22201E")), None


def _podium(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(poly([(-0.2, 0.0), (0.2, 0.0), (0.24, 0.5), (-0.24, 0.5)], c, w), poly([(-0.28, 0.5), (0.28, 0.5), (0.24, 0.56), (-0.24, 0.56)], tint(c, -0.2), w),
                  circ(0.0, 0.3, 0.07, GOLD, w * 0.6), line((0.12, 0.56), (0.18, 0.68), "#3A3631", w), circ(0.19, 0.7, 0.02, "#3A3631", 0)), None


def _placard(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.5), WOOD, w * 2), rect(-0.28, 0.45, 0.28, 0.78, "#F7F5F0", w),
                  letters(m.get("label") or "JUSTICE", 0.0, 0.615, 0.08, "#B83227")), None


def _inkedfinger(m, w):
    return VGroup(rrect(-0.08, 0.0, 0.08, 0.18, 0.04, "#C08A5E", w), rrect(-0.04, 0.16, 0.04, 0.46, 0.04, "#C08A5E", w),
                  ell(0.0, 0.42, 0.05, 0.06, "#F3D9C4", w * 0.5), line((-0.035, 0.36), (0.035, 0.36), "#3E2A6E", w * 2.4),
                  stroke([(-0.08, 0.14), (0.08, 0.14)], "#A06A44", w * 0.6)), None


def _constitution(m, w):
    return VGroup(rect(-0.22, 0.0, 0.22, 0.34, "#2F3B4C", w), rect(0.18, 0.01, 0.22, 0.33, "#F3EEE4", w * 0.4),
                  Circle(radius=0.06, stroke_color=GOLD, stroke_width=w).move_to([0.0, 0.2, 0]),
                  letters(m.get("label") or "CONSTITUTION", -0.01, 0.07, 0.025, GOLD)), None


def _puppet(m, w):
    return VGroup(line((-0.2, 0.75), (0.2, 0.75), WOOD, w * 1.6), *(line((x, 0.75), (x * 0.9, y), "#9A9283", w * 0.4) for x, y in ((-0.18, 0.4), (0.18, 0.4), (0.0, 0.56))),
                  circ(0.0, 0.5, 0.06, "#EFC9A6", w * 0.7), poly([(-0.05, 0.56), (0.05, 0.56), (0.0, 0.62)], RED, w * 0.4),
                  poly([(-0.08, 0.44), (0.08, 0.44), (0.14, 0.18), (-0.14, 0.18)], RED, w * 0.7),
                  *(line((s * 0.07, 0.42), (s * 0.18, 0.4), "#EFC9A6", w * 1.2) for s in (-1, 1)),
                  line((-0.1, 0.22), (0.1, 0.22), GOLD, w * 1.4)), None


def _rover(m, w):
    g = VGroup(rect(-0.25, 0.14, 0.2, 0.26, "#E8E3D8", w), rect(-0.2, 0.26, 0.15, 0.3, "#C9A44E", w * 0.6),
               line((0.1, 0.3), (0.12, 0.48), "#6E747A", w), rect(0.06, 0.48, 0.2, 0.54, "#3A3631", w * 0.6),
               *(line((x, 0.14), (x * 1.1, 0.06), "#6E747A", w) for x in (-0.22, 0.0, 0.18)))
    g.add(*wheelset((-0.24, 0.0, 0.2), 0.05, w))
    return g, None


def _spacestation(m, w):
    return VGroup(*(rect(x - 0.18, 0.2, x + 0.18, 0.3, "#3E5C82", w * 0.6) for x in (-0.5, 0.5)), *(line((x - 0.18, 0.25), (x + 0.18, 0.25), "#9FC5DA", w * 0.4) for x in (-0.5, 0.5)),
                  line((-0.32, 0.25), (0.32, 0.25), "#9AA3A9", w * 2), rrect(-0.15, 0.18, 0.15, 0.32, 0.05, "#E8E3D8", w),
                  rrect(-0.05, 0.32, 0.05, 0.45, 0.03, "#E8E3D8", w * 0.8), circ(0.0, 0.25, 0.03, "#3A3631", 0)), None


def _galaxy(m, w):
    g = VGroup()
    for k in range(2):
        pts = [(0.03 * t * math.cos(t * 0.9 + k * math.pi), 0.3 + 0.018 * t * math.sin(t * 0.9 + k * math.pi)) for t in np.linspace(0.5, 11, 30)]
        g.add(stroke(pts, "#B9A6E0", w * 2.4))
    g.add(ell(0.0, 0.3, 0.12, 0.08, "#F7EFD8", w * 0.5), *(glint(x, y, 0.015, w * 0.4) for x, y in ((-0.25, 0.42), (0.28, 0.15), (0.2, 0.45), (-0.3, 0.15))))
    return g, None


def _circuit(m, w):
    wire = "#B8733A"
    return VGroup(line((-0.3, 0.1), (0.3, 0.1), wire, w * 1.4), line((0.3, 0.1), (0.3, 0.36), wire, w * 1.4),
                  line((-0.3, 0.4), (0.24, 0.4), wire, w * 1.4), line((-0.3, 0.1), (-0.3, 0.4), wire, w * 1.4),
                  rect(-0.38, 0.18, -0.22, 0.32, "#3A3631", w * 0.8), rect(-0.34, 0.32, -0.26, 0.35, "#C9CED2", w * 0.5),
                  circ(0.3, 0.42, 0.07, "#FBE7A1", w), line((0.27, 0.36), (0.33, 0.36), "#3A3631", w * 0.6),
                  live(VGroup(*(line((0.3 + 0.1 * math.cos(a), 0.42 + 0.1 * math.sin(a)), (0.3 + 0.14 * math.cos(a), 0.42 + 0.14 * math.sin(a)), GOLD, w * 0.8)
                                for a in np.linspace(0.3, 2.8, 4))), "puff"),
                  circ(0.0, 0.1, 0.025, "#3A3631", 0), line((0.0, 0.1), (0.08, 0.16), "#3A3631", w * 1.2)), None


# -- food ---------------------------------------------------------------------------------------------------------

def _jalebi(m, w):
    g = VGroup(ell(0.0, 0.02, 0.44, 0.06, "#E8E0CC", w * 0.6))
    for x, y in ((-0.1, 0.07), (0.08, 0.08), (0.0, 0.14)):
        g.add(stroke([(x + 0.012 * t * math.cos(t), y + 0.007 * t * math.sin(t)) for t in np.linspace(0, 10, 30)], "#F2A93B", w * 2.4))
    return g, None


def _dosa(m, w):
    return VGroup(ell(0.0, 0.03, 0.7, 0.08, "#E8E0CC", w * 0.6), tube([(-0.3, 0.07), (0.0, 0.08), (0.3, 0.07)], [0.08, 0.1, 0.08], "#D9A24A", w),
                  *(stroke([(x, 0.05), (x + 0.03, 0.11)], "#B5803A", w * 0.5) for x in (-0.2, -0.05, 0.1, 0.22)),
                  ell(-0.22, 0.06, 0.1, 0.04, "#F7F5F0", w * 0.5), ell(0.25, 0.06, 0.1, 0.04, "#C2552B", w * 0.5)), None


def _idli(m, w):
    return VGroup(ell(0.0, 0.02, 0.5, 0.07, "#6E9A4A", w * 0.6),
                  *(blob(zoo.P._arc(x, 0.04, 0.08, 0, 180, 10), "#FBF8F1", w * 0.8) for x in (-0.1, 0.08)),
                  blob(zoo.P._arc(0.0, 0.08, 0.08, 0, 180, 10), "#FBF8F1", w * 0.8), ell(0.18, 0.05, 0.1, 0.04, "#F7F5F0", w * 0.4)), None


def _noodles(m, w):
    return VGroup(*(stroke([(x, 0.12), (x + 0.03, 0.2), (x - 0.02, 0.28), (x + 0.02, 0.34)], "#F2D27A", w * 1.4) for x in (-0.08, -0.02, 0.04, 0.1)),
                  blob([(-0.22, 0.14), (-0.16, 0.0), (0.16, 0.0), (0.22, 0.14)], "#B83227", w), line((-0.22, 0.14), (0.22, 0.14), zoo.INK, w),
                  line((0.12, 0.16), (0.3, 0.45), WOOD, w * 1.2), line((0.16, 0.16), (0.34, 0.43), WOOD, w * 1.2)), None


def _burger(m, w):
    return VGroup(blob(zoo.P._arc(0.0, 0.2, 0.2, 0, 180, 14), "#D9A24A", w), *(circ(x, 0.3, 0.008, "#F7F5F0", 0) for x in (-0.08, 0.0, 0.08)),
                  stroke([(-0.21, 0.19), (-0.1, 0.16), (0.0, 0.19), (0.1, 0.16), (0.21, 0.19)], "#6E9A4A", w * 2.4),
                  rrect(-0.2, 0.1, 0.2, 0.16, 0.03, "#6B4226", w), rect(-0.18, 0.15, 0.18, 0.17, "#F2C14E", 0),
                  rrect(-0.2, 0.02, 0.2, 0.1, 0.03, "#D9A24A", w)), None


def _coffee(m, w):
    c = col(m["color"]) if m.get("color") else "#F7F5F0"
    return VGroup(rrect(-0.1, 0.0, 0.1, 0.2, 0.03, c, w), stroke(zoo.P._arc(0.12, 0.1, 0.05, -80, 80, 8), c, w * 2.4),
                  ell(0.0, 0.2, 0.2, 0.04, "#6B4226", w * 0.6),
                  *(live(stroke([(x, 0.22), (x - 0.02, 0.3), (x + 0.01, 0.38)], "#C9C2B2", w * 0.8), "steam") for x in (-0.03, 0.04))), None


def _orange(m, w):
    return VGroup(circ(0.0, 0.12, 0.12, "#F2913B", w), *(circ(x, y, 0.006, "#C9702B", 0) for x, y in ((-0.05, 0.1), (0.04, 0.16), (0.02, 0.06))),
                  tube([(0.0, 0.24), (0.08, 0.29)], [0.04, 0.005], "#4F9A6A", w * 0.5)), None


def _lemon(m, w):
    return VGroup(blob([(-0.14, 0.08), (-0.1, 0.02), (0.1, 0.02), (0.14, 0.08), (0.1, 0.15), (-0.1, 0.15)], "#F2D24E", w),
                  poly([(-0.16, 0.08), (-0.14, 0.06), (-0.14, 0.1)], "#E2B83A", 0), stroke([(-0.06, 0.12), (0.02, 0.13)], "#FBEFA0", w)), None


def _potato(m, w):
    return VGroup(blob([(-0.14, 0.04), (-0.08, 0.0), (0.1, 0.02), (0.16, 0.08), (0.1, 0.15), (-0.08, 0.14)], "#C9A06A", w),
                  *(circ(x, y, 0.008, "#8C6A42", 0) for x, y in ((-0.06, 0.08), (0.04, 0.1), (0.08, 0.05)))), None


def _corn(m, w):
    g = VGroup(blob([(-0.06, 0.05), (-0.07, 0.25), (0.0, 0.42), (0.07, 0.25), (0.06, 0.05)], "#F2C14E", w))
    for y in np.arange(0.08, 0.38, 0.045):
        g.add(line((-0.055, y), (0.055, y), "#D9A23A", w * 0.4))
    g.add(line((0.0, 0.06), (0.0, 0.4), "#D9A23A", w * 0.4),
          blob([(-0.06, 0.0), (-0.16, 0.12), (-0.12, 0.3), (-0.05, 0.1)], "#7FB05A", w * 0.7),
          blob([(0.06, 0.0), (0.16, 0.12), (0.12, 0.3), (0.05, 0.1)], "#6E9A4A", w * 0.7))
    return g, None


def _salt(m, w):
    return VGroup(blob([(-0.35, 0.0), (-0.2, 0.12), (0.0, 0.26), (0.2, 0.12), (0.35, 0.0)], "#F7F7F2", w),
                  *(circ(x, y, 0.008, "#C9CED2", 0) for x, y in ((-0.1, 0.06), (0.05, 0.12), (0.12, 0.05), (-0.02, 0.18))),
                  ell(0.0, 0.0, 0.8, 0.04, "#DDEEF6", 0)), None


# -- history and industry --------------------------------------------------------------------------------------

def _trench(m, w):
    return VGroup(poly([(-1.0, 0.3), (1.0, 0.3), (1.0, 0.42), (-1.0, 0.42)], "#7A6A4E", w * 0.6),
                  poly([(-0.9, 0.0), (0.9, 0.0), (0.9, 0.3), (-0.9, 0.3)], "#5A4A36", w),
                  *(rect(x, 0.0, x + 0.03, 0.3, WOOD, w * 0.5) for x in np.linspace(-0.85, 0.82, 9)),
                  *(VGroup(ell(x, 0.36, 0.14, 0.08, "#E8E0CC", w * 0.5)) for x in (-0.5, 0.4)),
                  rect(-0.9, 0.0, 0.9, 0.04, WOOD_D, w * 0.5)), None


def _barbedwire(m, w):
    g = VGroup(*(line((x, 0.0), (x, 0.42), WOOD_D, w * 1.6) for x in (-0.6, 0.0, 0.6)))
    for y in (0.14, 0.28, 0.4):
        g.add(line((-0.6, y), (0.6, y), "#6E747A", w * 0.8))
        g.add(*(VGroup(line((x - 0.02, y - 0.02), (x + 0.02, y + 0.02), "#6E747A", w * 0.6), line((x - 0.02, y + 0.02), (x + 0.02, y - 0.02), "#6E747A", w * 0.6))
                for x in np.arange(-0.5, 0.55, 0.15)))
    return g, None


def _mushroomcloud(m, w):
    return VGroup(tube([(0.0, 0.0), (0.0, 0.5)], [0.22, 0.14], "#B5AFA4", w * 0.8),
                  live(blob([(-0.45, 0.5), (-0.5, 0.65), (-0.3, 0.82), (0.0, 0.88), (0.3, 0.82), (0.5, 0.65), (0.45, 0.5), (0.0, 0.45)], "#C9C2B2", w), "puff"),
                  blob([(-0.35, 0.55), (0.0, 0.5), (0.35, 0.55), (0.0, 0.62)], "#E8A23B", 0, op=0.7), ell(0.0, 0.03, 0.9, 0.08, "#9A948A", w * 0.5)), None


def _oilrig(m, w):
    g = VGroup(rect(-1.0, 0.0, 1.0, 0.14, WATER, 0), *(line((x, 0.0), (x, 0.4), "#6E747A", w * 1.6) for x in (-0.45, -0.15, 0.15, 0.45)),
               rect(-0.55, 0.4, 0.55, 0.5, "#E07B39", w), rect(-0.4, 0.5, 0.0, 0.66, "#F3EEE4", w * 0.8))
    g.add(line((0.2, 0.5), (0.3, 1.0), "#B83227", w * 1.4), line((0.4, 0.5), (0.3, 1.0), "#B83227", w * 1.4),
          *(line((0.22 + 0.016 * k, 0.6 + k * 0.08), (0.38 - 0.016 * k, 0.6 + k * 0.08), "#B83227", w * 0.6) for k in range(5)),
          live(blob([(0.5, 0.66), (0.55, 0.76), (0.6, 0.66)], "#F2A93B", 0), "flame"), line((0.55, 0.5), (0.55, 0.66), "#6E747A", w))
    return g, None


def _coal(m, w):
    g = VGroup(blob([(-0.35, 0.0), (-0.25, 0.15), (0.0, 0.26), (0.25, 0.15), (0.35, 0.0)], "#2B2826", w))
    g.add(*(poly([(x - 0.04, y), (x, y + 0.04), (x + 0.05, y + 0.01)], "#4A4642", 0) for x, y in ((-0.15, 0.08), (0.05, 0.16), (0.15, 0.06), (-0.02, 0.05))),
          glint(-0.06, 0.18, 0.018, w * 0.5))
    return g, None


def _furnace(m, w):
    return VGroup(poly([(-0.3, 0.0), (0.3, 0.0), (0.22, 0.75), (-0.22, 0.75)], "#8E3A2B", w),
                  *(line((-0.3 + 0.01 * k, y), (0.3 - 0.01 * k, y), "#6E2A1E", w * 0.5) for k, y in enumerate((0.15, 0.3, 0.45, 0.6))),
                  blob([(-0.12, 0.0), (-0.12, 0.18), (0.0, 0.26), (0.12, 0.18), (0.12, 0.0)], "#F2A93B", w),
                  live(blob([(-0.06, 0.02), (0.0, 0.18), (0.06, 0.02)], "#FBE7A1", 0), "flame"),
                  live(blob([(-0.08, 0.78), (0.0, 0.9), (0.15, 0.95), (0.2, 0.85), (0.1, 0.76)], "#9A9488", w * 0.5), "puff")), None


def _steamengine(m, w):
    g = VGroup(rect(-0.6, 0.0, 0.6, 0.06, "#6E5A44", w), rect(-0.5, 0.06, -0.15, 0.42, "#6E747A", w), rect(-0.55, 0.42, -0.1, 0.48, "#4A4642", w * 0.6),
               line((-0.32, 0.48), (0.25, 0.62), "#3A3631", w * 2.4), circ(-0.32, 0.5, 0.025, "#3A3631", 0))
    wheel = VGroup(Circle(radius=0.28, stroke_color="#3A3631", stroke_width=w * 3).move_to([0.3, 0.34, 0]),
                   *(line((0.3, 0.34), (0.3 + 0.27 * math.cos(a), 0.34 + 0.27 * math.sin(a)), "#3A3631", w) for a in np.linspace(0, 2 * math.pi, 7)[:-1]))
    g.add(live(wheel, "spin", (0.3, 0.34)), line((0.25, 0.62), (0.3, 0.34), "#3A3631", w * 1.6),
          rect(-0.45, 0.48, -0.37, 0.75, "#4A4642", w * 0.6), live(blob([(-0.45, 0.78), (-0.5, 0.88), (-0.38, 0.95), (-0.3, 0.86), (-0.36, 0.77)], "#C9C2B2", w * 0.5), "puff"))
    return g, None


def _telegraph(m, w):
    return VGroup(rect(-0.25, 0.0, 0.25, 0.05, WOOD, w), rect(-0.12, 0.05, 0.12, 0.08, "#B8733A", w * 0.6),
                  line((-0.15, 0.1), (0.15, 0.13), "#B8733A", w * 2), circ(0.15, 0.15, 0.035, "#2B2826", w * 0.6),
                  line((-0.15, 0.08), (-0.15, 0.1), "#3A3631", w), stroke([(-0.25, 0.03), (-0.35, 0.06), (-0.45, 0.02)], "#3A3631", w * 0.8),
                  *(rect(-0.2 + i * 0.05, 0.25, -0.17 + i * 0.05 + (0.04 if i % 2 else 0), 0.27, "#3A3631", 0) for i in range(5))), None


# -- around the house -------------------------------------------------------------------------------------------

def _glass(m, w):
    c = col(m["color"]) if m.get("color") else "#9FC5DA"
    return VGroup(poly([(-0.07, 0.0), (0.07, 0.0), (0.09, 0.24), (-0.09, 0.24)], "#EEF4F8", w, op=0.7),
                  poly([(-0.068, 0.01), (0.068, 0.01), (0.083, 0.17), (-0.083, 0.17)], c, 0, op=0.8),
                  stroke([(-0.05, 0.05), (-0.055, 0.2)], "#FFFFFF", w)), None


def _matchbox(m, w):
    return VGroup(rect(-0.14, 0.0, 0.14, 0.1, "#E8E0CC", w), rect(-0.12, 0.02, 0.12, 0.08, "#B83227", w * 0.4),
                  line((0.1, 0.12), (0.26, 0.22), WOOD, w * 1.4), circ(0.27, 0.23, 0.018, "#B83227", 0),
                  live(blob([(0.26, 0.24), (0.28, 0.31), (0.3, 0.24)], "#F2A93B", 0), "flame")), None


def _toothbrush(m, w):
    return VGroup(rrect(-0.25, 0.02, 0.15, 0.05, 0.015, "#3E7CB1", w), rect(0.1, 0.05, 0.2, 0.06, "#3E7CB1", w * 0.5),
                  *(line((x, 0.06), (x, 0.12), "#F7F5F0", w * 1.2) for x in np.linspace(0.11, 0.19, 5)),
                  rect(0.1, 0.12, 0.2, 0.15, "#E8F4F8", w * 0.4)), None


def _soap(m, w):
    return VGroup(rrect(-0.14, 0.0, 0.14, 0.1, 0.04, "#F2B8C6", w), stroke([(-0.06, 0.07), (0.06, 0.07)], "#F7D4DE", w),
                  *(Circle(radius=r, stroke_color="#9FC5DA", stroke_width=w * 0.6).move_to([x, y, 0]) for x, y, r in ((0.12, 0.16, 0.03), (0.05, 0.2, 0.02), (0.16, 0.24, 0.015)))), None


def _comb(m, w):
    return VGroup(rrect(-0.2, 0.08, 0.2, 0.12, 0.015, "#8C5E38", w), *(line((x, 0.08), (x, 0.0), "#8C5E38", w * 1.2) for x in np.linspace(-0.18, 0.18, 14))), None


def _towel(m, w):
    c = col(m["color"]) if m.get("color") else "#7FB5B0"
    return VGroup(line((-0.25, 0.55), (0.25, 0.55), "#9AA3A9", w * 2), poly([(-0.18, 0.55), (0.18, 0.55), (0.18, 0.0), (-0.18, 0.0)], c, w),
                  *(line((-0.18, y), (0.18, y), tint(c, 0.3), w) for y in (0.08, 0.12, 0.44))), None


def _photoframe(m, w):
    return VGroup(rect(-0.2, 0.0, 0.2, 0.28, WOOD, w), rect(-0.16, 0.04, 0.16, 0.24, "#DDEEF6", w * 0.5),
                  circ(-0.03, 0.17, 0.03, "#EFC9A6", w * 0.4), circ(0.05, 0.16, 0.025, "#C08A5E", w * 0.4),
                  blob([(-0.08, 0.04), (-0.07, 0.12), (0.1, 0.12), (0.11, 0.04)], "#3E7CB1", w * 0.4)), None


def _flowerpot(m, w):
    g = VGroup(poly([(-0.12, 0.0), (0.12, 0.0), (0.15, 0.18), (-0.15, 0.18)], "#C2552B", w), rect(-0.16, 0.18, 0.16, 0.22, "#A84A26", w * 0.8))
    for x, h, c in ((-0.06, 0.4, "#F2C14E"), (0.02, 0.46, "#D46A9A"), (0.09, 0.38, "#F7F5F0")):
        g.add(stroke([(x * 0.5, 0.22), (x, h)], "#5E8A3E", w), *(circ(x + 0.03 * math.cos(a), h + 0.03 * math.sin(a), 0.022, c, w * 0.3) for a in np.linspace(0, 2 * math.pi, 6)[:-1]),
              circ(x, h, 0.012, "#B83227", 0))
    return g, None


def _aquarium(m, w):
    return VGroup(rect(-0.3, 0.0, 0.3, 0.32, "#BFE0EE", w, ), rect(-0.3, 0.0, 0.3, 0.04, SAND, 0), rect(-0.31, 0.3, 0.31, 0.34, "#3A3631", w * 0.6),
                  *(stroke([(x, 0.04), (x + 0.02, 0.14), (x - 0.01, 0.22)], "#4F9A6A", w * 1.2) for x in (-0.2, 0.18)),
                  *(VGroup(ell(x, y, 0.08, 0.045, c, w * 0.4), poly([(x - 0.04, y), (x - 0.07, y + 0.025), (x - 0.07, y - 0.025)], c, w * 0.4))
                    for x, y, c in ((-0.02, 0.18, "#E07B39"), (0.12, 0.1, "#F2C14E"))),
                  *(Circle(radius=0.01, stroke_color="#FFFFFF", stroke_width=w * 0.5).move_to([0.0, y, 0]) for y in (0.23, 0.27))), None


def _birdcage(m, w):
    g = VGroup(ell(0.0, 0.02, 0.36, 0.06, GOLD_D, w), blob([(-0.17, 0.03), (-0.17, 0.35), (0.0, 0.48), (0.17, 0.35), (0.17, 0.03)], "#FBF8F1", w, op=0.0))
    g.add(*(line((x, 0.03), (x * 0.4, 0.44), GOLD_D, w * 0.6) for x in np.linspace(-0.16, 0.16, 7)), stroke(zoo.P._arc(0.0, 0.5, 0.04, 0, 360, 10), GOLD_D, w),
          line((-0.12, 0.15), (0.12, 0.15), WOOD, w), ell(0.0, 0.22, 0.1, 0.08, "#F2C14E", w * 0.5), poly([(0.05, 0.23), (0.08, 0.22), (0.05, 0.21)], "#E07B39", 0))
    return g, None


def _flashlight(m, w):
    return VGroup(rrect(-0.2, 0.0, 0.08, 0.08, 0.02, "#3A3631", w), poly([(0.08, -0.01), (0.15, -0.03), (0.15, 0.11), (0.08, 0.09)], "#6E747A", w),
                  rect(-0.06, 0.08, 0.0, 0.1, "#B83227", w * 0.4),
                  live(poly([(0.15, -0.02), (0.55, -0.12), (0.55, 0.2), (0.15, 0.1)], "#FBE7A1", 0, op=0.55), "puff")), None


def _almirah(m, w):
    return VGroup(rect(-0.3, 0.0, 0.3, 0.9, "#8E969C", w), line((0.0, 0.02), (0.0, 0.88), "#5E666C", w),
                  *(rect(x, 0.42, x + 0.02, 0.5, "#3A3631", 0) for x in (-0.05, 0.03)), rect(-0.3, 0.0, 0.3, 0.05, "#5E666C", w * 0.6),
                  *(line((-0.26, y), (-0.06, y), "#A7AEB3", w * 0.5) for y in (0.75, 0.8))), None


def _trunk(m, w):
    c = col(m["color"]) if m.get("color") else "#2F5E7E"
    return VGroup(rect(-0.32, 0.0, 0.32, 0.26, c, w), rect(-0.32, 0.2, 0.32, 0.26, tint(c, -0.2), w * 0.6),
                  *(rect(x, 0.0, x + 0.04, 0.26, "#C9CED2", w * 0.5) for x in (-0.24, 0.2)), rect(-0.04, 0.14, 0.04, 0.22, GOLD, w * 0.6),
                  stroke([(-0.08, 0.26), (-0.06, 0.3), (0.06, 0.3), (0.08, 0.26)], "#3A3631", w * 1.2)), None


def _sieve(m, w):
    g = VGroup(ell(0.0, 0.12, 0.42, 0.12, "#C9CED2", w), ell(0.0, 0.12, 0.36, 0.09, "#E8EBED", 0))
    g.add(*(line((x, 0.08), (x, 0.16), "#9AA3A9", w * 0.4) for x in np.linspace(-0.14, 0.14, 7)),
          *(line((-0.16, y), (0.16, y), "#9AA3A9", w * 0.4) for y in (0.1, 0.12, 0.14)), line((0.21, 0.12), (0.42, 0.14), WOOD, w * 2))
    return g, None


def _rollingpin(m, w):
    return VGroup(ell(0.0, 0.025, 0.44, 0.05, "#E8C27E", w * 0.6), rrect(-0.2, 0.05, 0.2, 0.11, 0.03, "#C9A066", w),
                  *(rrect(x - 0.06, 0.06, x + 0.06, 0.1, 0.02, WOOD, w * 0.7) for x in (-0.26, 0.26))), None


def _tawa(m, w):
    return VGroup(ell(0.0, 0.04, 0.5, 0.09, "#3A3631", w), ell(0.0, 0.06, 0.4, 0.06, "#4A4642", 0), line((0.25, 0.05), (0.45, 0.08), "#3A3631", w * 2),
                  ell(-0.02, 0.07, 0.26, 0.04, "#E8C27E", w * 0.5), *(circ(x, 0.075, 0.008, "#B5803A", 0) for x in (-0.07, 0.02, 0.07))), None


# -- office and tech ---------------------------------------------------------------------------------------------

def _stapler(m, w):
    return VGroup(rrect(-0.22, 0.0, 0.22, 0.05, 0.02, "#3A3631", w), poly([(-0.2, 0.05), (0.22, 0.06), (0.22, 0.12), (-0.18, 0.1)], "#B83227", w),
                  circ(-0.19, 0.075, 0.025, "#9AA3A9", w * 0.5)), None


def _paperclip(m, w):
    return VGroup(stroke([(0.08, 0.04), (0.08, 0.3), *zoo.P._arc(0.0, 0.3, 0.08, 0, 180, 8), (-0.08, 0.06), *zoo.P._arc(0.0, 0.06, 0.05, 180, 360, 8),
                          (0.05, 0.25), *zoo.P._arc(0.015, 0.25, 0.035, 0, 180, 6), (-0.02, 0.1)], "#9AA3A9", w * 1.6)), None


def _smartwatch(m, w):
    return VGroup(rrect(-0.05, -0.0, 0.05, 0.38, 0.03, "#3A3631", w), rrect(-0.1, 0.12, 0.1, 0.28, 0.04, "#2B2826", w),
                  rrect(-0.08, 0.14, 0.08, 0.26, 0.03, "#1E2A3A", 0), letters("10:30", 0.0, 0.22, 0.035, "#7FD18B"),
                  live(stroke([(-0.06, 0.17), (-0.02, 0.17), (0.0, 0.19), (0.02, 0.15), (0.06, 0.17)], "#E8524A", w * 0.6), "puff")), None


def _usb(m, w):
    return VGroup(rrect(-0.2, 0.0, 0.1, 0.1, 0.03, "#3E7CB1", w), rect(0.1, 0.015, 0.22, 0.085, "#C9CED2", w),
                  *(rect(0.15, y, 0.18, y + 0.02, "#3A3631", 0) for y in (0.03, 0.06)), circ(-0.15, 0.05, 0.015, "#F7F5F0", w * 0.4)), None


def _server(m, w):
    g = VGroup(rect(-0.2, 0.0, 0.2, 0.8, "#2B2826", w))
    for i in range(6):
        y = 0.05 + i * 0.125
        g.add(rect(-0.17, y, 0.17, y + 0.1, "#3A3631", w * 0.5), *(line((x, y + 0.03), (x, y + 0.07), "#6E747A", w * 0.5) for x in (-0.12, -0.09, -0.06)),
              live(circ(0.13, y + 0.05, 0.012, "#7FD18B" if i % 3 else "#F2C14E", 0), "puff"))
    return g, None


def _computermouse(m, w):
    return VGroup(blob([(-0.08, 0.0), (-0.1, 0.08), (-0.06, 0.18), (0.06, 0.18), (0.1, 0.08), (0.08, 0.0)], "#E8EBED", w),
                  line((0.0, 0.18), (0.0, 0.11), "#9AA3A9", w * 0.6), line((-0.09, 0.11), (0.09, 0.11), "#9AA3A9", w * 0.6),
                  stroke([(0.0, 0.18), (0.02, 0.26), (0.12, 0.3), (0.2, 0.28)], "#3A3631", w)), None


def _projector(m, w):
    return VGroup(rrect(-0.2, 0.0, 0.15, 0.12, 0.02, "#E8E3D8", w), circ(0.1, 0.06, 0.04, "#3A3631", w * 0.6),
                  live(poly([(0.14, 0.06), (0.6, 0.0), (0.6, 0.36), (0.14, 0.09)], "#FBE7A1", 0, op=0.45), "puff"),
                  rect(0.6, -0.02, 0.62, 0.38, "#F7F5F0", w * 0.6), *(line((x, 0.0), (x, -0.06), "#6E747A", w) for x in (-0.15, 0.1))), None


# -- money ------------------------------------------------------------------------------------------------------

def _billboard(m, w):
    c = col(m["color"]) if m.get("color") else "#E07B39"
    return VGroup(*(line((x, 0.0), (x, 0.45), "#6E747A", w * 1.6) for x in (-0.35, 0.35)), rect(-0.6, 0.45, 0.6, 0.9, "#F7F5F0", w),
                  rect(-0.56, 0.49, 0.56, 0.86, c, w * 0.4), letters(m.get("label") or "SALE!", 0.0, 0.675, 0.14, "#F7F5F0"),
                  line((-0.6, 0.42), (0.6, 0.42), "#6E747A", w)), None


def _vendingmachine(m, w):
    g = VGroup(rect(-0.25, 0.0, 0.25, 0.9, "#B83227", w), rect(-0.2, 0.3, 0.1, 0.84, "#DDEEF6", w * 0.6))
    for r in range(4):
        g.add(*(rrect(x - 0.025, 0.36 + r * 0.12, x + 0.025, 0.44 + r * 0.12, 0.01, c, w * 0.3)
                for x, c in ((-0.15, "#F2C14E"), (-0.07, "#4F9A6A"), (0.03, "#3E7CB1"))))
    g.add(rect(0.13, 0.55, 0.22, 0.7, "#3A3631", w * 0.5), rect(-0.18, 0.08, 0.1, 0.18, "#3A3631", w * 0.6))
    return g, None


def _coinjar(m, w):
    return VGroup(rrect(-0.13, 0.0, 0.13, 0.3, 0.05, "#DDEEF6", w, ), coin_pile(0.0, 0.0, 0.22, 6, w), rect(-0.1, 0.3, 0.1, 0.35, "#B8BEC2", w * 0.6),
                  rect(-0.04, 0.34, 0.04, 0.35, "#3A3631", 0), ell(0.0, 0.42, 0.06, 0.02, GOLD, w * 0.5)), None


# -- getting about ----------------------------------------------------------------------------------------------

def _skateboard(m, w):
    g = VGroup(rrect(-0.32, 0.06, 0.32, 0.1, 0.02, "#E07B39", w), *(rect(x - 0.03, 0.04, x + 0.03, 0.06, "#6E747A", w * 0.4) for x in (-0.2, 0.2)))
    g.add(*wheelset((-0.22, -0.18, 0.18, 0.22), 0.025, w))
    return g, None


def _parachute(m, w):
    c = col(m["color"]) if m.get("color") else RED
    g = VGroup(blob([(-0.45, 0.6), *zoo.P._arc(0.0, 0.6, 0.45, 180, 0, 18), (0.45, 0.6), (0.3, 0.58), (0.15, 0.6), (0.0, 0.58), (-0.15, 0.6), (-0.3, 0.58)], c, w))
    g.add(*(line((0.15 * k, 0.86), (0.15 * k, 0.6), tint(c, 0.3), w * 0.6) for k in (-2, -1, 1, 2)),
          *(line((x, 0.6), (0.0, 0.18), "#6E6458", w * 0.5) for x in (-0.45, -0.15, 0.15, 0.45)), rect(-0.06, 0.04, 0.06, 0.18, "#5B6B3A", w))
    return g, None


def _anchor(m, w):
    return VGroup(line((0.0, 0.05), (0.0, 0.48), "#6E747A", w * 2.6), line((-0.1, 0.4), (0.1, 0.4), "#6E747A", w * 2.2),
                  stroke(zoo.P._arc(0.0, 0.5, 0.04, 0, 360, 10), "#6E747A", w * 1.6), stroke(zoo.P._arc(0.0, 0.2, 0.18, 200, 340, 12), "#6E747A", w * 2.6),
                  *(poly([(s * 0.17, 0.14), (s * 0.24, 0.2), (s * 0.15, 0.22)], "#6E747A", w * 0.5) for s in (-1, 1))), None


def _lifebuoy(m, w):
    ring = [(0.2 * math.cos(t), 0.2 + 0.2 * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 40)]
    hole = [(0.1 * math.cos(t), 0.2 + 0.1 * math.sin(t)) for t in np.linspace(2 * math.pi, 0, 30)]
    g = VGroup(fill_only(ring + hole, "#F7F5F0", 1.0, smooth=False))
    for a in (45, 135, 225, 315):
        r = math.radians(a)
        g.add(poly([(0.1 * math.cos(r - 0.4), 0.2 + 0.1 * math.sin(r - 0.4)), (0.2 * math.cos(r - 0.3), 0.2 + 0.2 * math.sin(r - 0.3)),
                    (0.2 * math.cos(r + 0.3), 0.2 + 0.2 * math.sin(r + 0.3)), (0.1 * math.cos(r + 0.4), 0.2 + 0.1 * math.sin(r + 0.4))], RED, 0))
    g.add(Circle(radius=0.2, stroke_color=zoo.INK, stroke_width=w).move_to([0.0, 0.2, 0]),
          Circle(radius=0.1, stroke_color=zoo.INK, stroke_width=w).move_to([0.0, 0.2, 0]))
    return g, None


def _steeringwheel(m, w):
    return VGroup(Circle(radius=0.2, stroke_color="#2B2826", stroke_width=w * 4).move_to([0.0, 0.22, 0]), circ(0.0, 0.22, 0.05, "#3A3631", w),
                  *(line((0.0, 0.22), (0.19 * math.cos(a), 0.22 + 0.19 * math.sin(a)), "#2B2826", w * 2.4) for a in (math.radians(200), math.radians(340), math.radians(270)))), None


def _tyre(m, w):
    return VGroup(circ(0.0, 0.22, 0.22, "#2B2826", w), circ(0.0, 0.22, 0.12, "#9AA3A9", w), circ(0.0, 0.22, 0.04, "#6E747A", w * 0.6),
                  *(line((0.17 * math.cos(a), 0.22 + 0.17 * math.sin(a)), (0.21 * math.cos(a), 0.22 + 0.21 * math.sin(a)), "#4A4642", w * 0.8)
                    for a in np.linspace(0, 2 * math.pi, 13)[:-1])), None


def _fuelcan(m, w):
    return VGroup(rrect(-0.15, 0.0, 0.15, 0.32, 0.03, RED, w), line((-0.15, 0.0), (0.15, 0.32), tint(RED, -0.25), w * 0.8),
                  line((-0.15, 0.32), (0.15, 0.0), tint(RED, -0.25), w * 0.8),
                  stroke([(-0.1, 0.32), (-0.08, 0.4), (0.04, 0.4), (0.04, 0.32)], "#3A3631", w * 1.6),
                  rect(0.08, 0.32, 0.14, 0.4, "#E2B65A", w * 0.6)), None


# -- play and sport -----------------------------------------------------------------------------------------------

def _wicket(m, w):
    return VGroup(*(rect(x - 0.012, 0.0, x + 0.012, 0.42, "#E8D2A0", w * 0.8) for x in (-0.06, 0.0, 0.06)),
                  *(rect(x - 0.035, 0.42, x + 0.035, 0.44, "#C9A066", w * 0.5) for x in (-0.03, 0.03)),
                  circ(0.2, 0.05, 0.035, RED, w * 0.6)), None


def _goalpost(m, w):
    g = VGroup()
    g.add(*(line((x, 0.53), (x * 0.85, 0.02), "#B5AFA4", w * 0.4) for x in np.linspace(-0.55, 0.55, 9)),
          *(line((-0.55, y), (0.55, y), "#B5AFA4", w * 0.4) for y in (0.15, 0.3, 0.45)))
    g.add(rect(-0.63, 0.0, -0.57, 0.58, "#F7F5F0", w), rect(0.57, 0.0, 0.63, 0.58, "#F7F5F0", w), rect(-0.63, 0.52, 0.63, 0.58, "#F7F5F0", w),
          circ(0.0, 0.06, 0.06, "#F7F5F0", w), poly([(-0.02, 0.07), (0.02, 0.07), (0.0, 0.04)], "#2B2826", 0))
    return g, None


def _basketballhoop(m, w):
    return VGroup(line((0.3, 0.0), (0.3, 0.9), "#6E747A", w * 2.4), rect(0.0, 0.75, 0.32, 1.0, "#F7F5F0", w), rect(0.1, 0.8, 0.22, 0.88, "#F7F5F0", w * 0.6),
                  ell(0.0, 0.78, 0.22, 0.05, "#E07B39", w), *(line((x, 0.77), (x * 0.6, 0.6), "#F7F5F0", w * 0.5) for x in (-0.1, -0.04, 0.04, 0.1)),
                  circ(-0.3, 0.12, 0.1, "#E07B39", w), line((-0.4, 0.12), (-0.2, 0.12), "#2B2826", w * 0.5)), None


def _swing(m, w):
    return VGroup(line((-0.4, 0.0), (-0.3, 0.8), WOOD_D, w * 2), line((0.4, 0.0), (0.3, 0.8), WOOD_D, w * 2), line((-0.35, 0.8), (0.35, 0.8), WOOD_D, w * 2.4),
                  live(VGroup(line((-0.12, 0.8), (-0.12, 0.22), "#6E6458", w * 0.8), line((0.12, 0.8), (0.12, 0.22), "#6E6458", w * 0.8),
                              rect(-0.16, 0.2, 0.16, 0.24, "#E07B39", w * 0.7)), "tick", (0.0, 0.8))), None


def _slide(m, w):
    return VGroup(line((-0.4, 0.0), (-0.4, 0.6), "#6E747A", w * 1.6), line((-0.25, 0.0), (-0.25, 0.6), "#6E747A", w * 1.6),
                  *(line((-0.4, y), (-0.25, y), "#6E747A", w) for y in (0.15, 0.3, 0.45)), rect(-0.42, 0.58, -0.2, 0.62, "#E07B39", w * 0.6),
                  poly([(-0.22, 0.62), (-0.2, 0.56), (0.42, 0.04), (0.5, 0.06), (0.5, 0.1)], "#F2C14E", w)), None


def _seesaw(m, w):
    return VGroup(poly([(-0.08, 0.0), (0.08, 0.0), (0.0, 0.16)], "#6E747A", w), VGroup(rect(-0.55, 0.15, 0.55, 0.2, "#4F9A6A", w),
                  *(rect(x - 0.015, 0.2, x + 0.015, 0.3, "#3A3631", w * 0.4) for x in (-0.45, 0.45))).rotate(0.15, about_point=np.array([0.0, 0.17, 0]))), None


def _marbles(m, w):
    return VGroup(*(VGroup(circ(x, 0.05, 0.05, c, w * 0.6), stroke([(x - 0.02, 0.04), (x + 0.02, 0.07)], tint(c, 0.5), w * 0.8), glint(x - 0.02, 0.07, 0.012, w * 0.3))
                    for x, c in ((-0.2, "#3E7CB1"), (-0.08, "#E07B39"), (0.04, "#4F9A6A"), (0.15, "#B83227"), (0.25, "#7A4C8C")))), None


def _yoyo(m, w):
    return VGroup(line((0.0, 0.4), (0.0, 0.18), "#3A3631", w * 0.6), circ(0.0, 0.42, 0.015, "#3A3631", 0),
                  circ(0.0, 0.1, 0.1, RED, w), circ(0.0, 0.1, 0.03, "#F7F5F0", w * 0.5), stroke(zoo.P._arc(0.0, 0.1, 0.07, 100, 170, 6), "#F7B4A6", w)), None


def _teddybear(m, w):
    c = col(m["color"]) if m.get("color") else "#B5803A"
    return VGroup(*(circ(x, 0.48, 0.05, c, w) for x in (-0.1, 0.1)), ell(0.0, 0.16, 0.3, 0.3, c, w), circ(0.0, 0.4, 0.12, c, w),
                  ell(0.0, 0.36, 0.1, 0.07, tint(c, 0.4), w * 0.5), circ(0.0, 0.38, 0.015, "#2B2826", 0),
                  *(circ(x, 0.43, 0.012, "#2B2826", 0) for x in (-0.04, 0.04)), ell(0.0, 0.14, 0.16, 0.16, tint(c, 0.35), 0),
                  *(ell(x, 0.03, 0.1, 0.07, c, w) for x in (-0.1, 0.1)), *(ell(x, 0.22, 0.07, 0.12, c, w) for x in (-0.16, 0.16))), None


# -- simple machines, weather, the body --------------------------------------------------------------------------

def _pendulum(m, w):
    return VGroup(line((-0.25, 0.8), (0.25, 0.8), WOOD, w * 2.2), line((-0.2, 0.0), (-0.2, 0.8), WOOD, w * 1.6), rect(-0.3, 0.0, 0.0, 0.04, WOOD_D, w * 0.6),
                  live(VGroup(line((0.0, 0.8), (0.0, 0.25), "#6E6458", w * 0.6), circ(0.0, 0.22, 0.05, GOLD, w)), "tick", (0.0, 0.8))), None


def _pulley(m, w):
    return VGroup(line((-0.3, 0.9), (0.3, 0.9), WOOD_D, w * 2.2), line((0.0, 0.9), (0.0, 0.8), "#6E747A", w * 1.4),
                  circ(0.0, 0.72, 0.08, "#9AA3A9", w), circ(0.0, 0.72, 0.02, "#3A3631", 0),
                  line((-0.08, 0.72), (-0.08, 0.15), "#C9A066", w), line((0.08, 0.72), (0.08, 0.35), "#C9A066", w),
                  rect(-0.16, 0.0, 0.0, 0.15, "#8E969C", w), rect(0.02, 0.35, 0.14, 0.45, "#C99A62", w)), None


def _weathervane(m, w):
    return VGroup(line((0.0, 0.0), (0.0, 0.6), "#3A3631", w * 1.6), line((-0.12, 0.35), (0.12, 0.35), "#3A3631", w), line((0.0, 0.25), (0.0, 0.45), "#3A3631", w),
                  letters("N", 0.0, 0.5, 0.05, "#3A3631"), letters("E", 0.17, 0.35, 0.04, "#3A3631"),
                  live(VGroup(line((-0.22, 0.62), (0.18, 0.62), "#3A3631", w * 1.2), poly([(0.18, 0.66), (0.26, 0.62), (0.18, 0.58)], "#3A3631", w * 0.5),
                              poly([(-0.22, 0.62), (-0.3, 0.68), (-0.26, 0.62), (-0.3, 0.56)], "#3A3631", w * 0.5)), "tick", (0.0, 0.62))), None


def _anemometer(m, w):
    g = VGroup(line((0.0, 0.0), (0.0, 0.5), "#6E747A", w * 1.6))
    arms = VGroup()
    for a in (0, 120, 240):
        r = math.radians(a)
        x, y = 0.2 * math.cos(r), 0.5 + 0.06 * math.sin(r)
        arms.add(line((0.0, 0.5), (x, y), "#6E747A", w), blob(zoo.P._arc(x, y, 0.05, 90, 270, 8), "#E8EBED", w * 0.6))
    g.add(live(arms, "spin", (0.0, 0.5)))
    return g, None


def _seismograph(m, w):
    return VGroup(rect(-0.4, 0.0, 0.4, 0.06, "#6E5A44", w), rect(-0.35, 0.06, 0.35, 0.3, "#F7F5F0", w),
                  live(stroke([(-0.33, 0.18), (-0.2, 0.18), (-0.15, 0.26), (-0.1, 0.1), (-0.05, 0.28), (0.0, 0.08), (0.05, 0.22), (0.1, 0.16), (0.33, 0.18)], "#B83227", w), "puff"),
                  line((0.33, 0.18), (0.33, 0.45), "#3A3631", w), circ(0.33, 0.45, 0.03, "#3A3631", 0)), None


def _fossil(m, w):
    g = VGroup(blob([(-0.25, 0.0), (-0.28, 0.15), (-0.15, 0.3), (0.15, 0.3), (0.28, 0.15), (0.25, 0.0)], "#C9BFA8", w))
    g.add(stroke([(0.0 + 0.012 * t * math.cos(t), 0.15 + 0.012 * t * math.sin(t)) for t in np.linspace(0, 11, 40)], "#8A7E66", w * 1.4))
    g.add(*(line((0.0 + 0.012 * t * math.cos(t), 0.15 + 0.012 * t * math.sin(t)), (0.0 + 0.016 * t * math.cos(t), 0.15 + 0.016 * t * math.sin(t)), "#8A7E66", w * 0.6)
            for t in np.linspace(5, 11, 9)))
    return g, None


def _solarsystem(m, w):
    g = VGroup(circ(-0.6, 0.3, 0.16, "#F2C14E", w))
    for i, (r, c, s) in enumerate(((0.3, "#B5AD9C", 0.02), (0.45, "#E2B65A", 0.03), (0.62, "#3E7CB1", 0.035), (0.78, "#C2552B", 0.028), (1.0, "#D9A274", 0.06))):
        g.add(stroke(zoo.P._arc(-0.6, 0.3, r, -35, 35, 12), "#C9C2B2", w * 0.5),
              circ(-0.6 + r * math.cos(math.radians(-25 + i * 12)), 0.3 + r * math.sin(math.radians(-25 + i * 12)), s, c, w * 0.5))
    return g, None


def _eye(m, w):
    return VGroup(blob([(-0.25, 0.12), (-0.1, 0.22), (0.1, 0.22), (0.25, 0.12), (0.1, 0.02), (-0.1, 0.02)], "#FBF8F1", w),
                  circ(0.0, 0.12, 0.08, "#5E8A6A", w * 0.6), circ(0.0, 0.12, 0.035, "#2B2826", 0), circ(0.02, 0.14, 0.012, "#FFFFFF", 0),
                  *(line((x, 0.21 + 0.01 * (1 - abs(x) * 4)), (x * 1.2, 0.27), "#2B2826", w * 0.6) for x in (-0.12, -0.04, 0.04, 0.12))), None


def _lungs(m, w):
    return VGroup(line((0.0, 0.5), (0.0, 0.32), "#E8B4A6", w * 2.4), line((0.0, 0.32), (-0.08, 0.26), "#E8B4A6", w * 1.6), line((0.0, 0.32), (0.08, 0.26), "#E8B4A6", w * 1.6),
                  blob([(-0.04, 0.3), (-0.08, 0.4), (-0.2, 0.38), (-0.28, 0.2), (-0.26, 0.02), (-0.1, 0.04), (-0.04, 0.16)], "#E8848A", w),
                  blob([(0.04, 0.3), (0.08, 0.4), (0.2, 0.38), (0.28, 0.2), (0.26, 0.02), (0.1, 0.04), (0.04, 0.16)], "#E8848A", w),
                  *(stroke([(s * 0.08, 0.26), (s * 0.14, 0.18), (s * 0.18, 0.1)], "#C9606A", w * 0.6) for s in (-1, 1))), None


def _crutch(m, w):
    return VGroup(line((-0.06, 0.1), (-0.04, 0.85), "#9AA3A9", w * 1.6), line((0.06, 0.1), (0.04, 0.85), "#9AA3A9", w * 1.6),
                  line((0.0, 0.1), (0.0, 0.0), "#9AA3A9", w * 2), rrect(-0.09, 0.84, 0.09, 0.9, 0.02, "#3A3631", w * 0.6),
                  rect(-0.05, 0.45, 0.05, 0.5, "#3A3631", w * 0.5), ell(0.0, 0.0, 0.05, 0.02, "#3A3631", 0)), None


# -- the ancient and medieval worlds ------------------------------------------------------------------------------

def _papyrus(m, w):
    g = VGroup(rect(-0.3, 0.0, 0.3, 0.36, "#E8D4A0", w), ell(-0.3, 0.18, 0.06, 0.36, "#D9C08A", w), ell(0.3, 0.18, 0.06, 0.36, "#D9C08A", w))
    for r in range(4):
        y = 0.3 - r * 0.075
        g.add(*(circ(x, y, 0.012, "#5A4630", 0) if (r + k) % 3 == 0 else line((x, y - 0.015), (x, y + 0.015), "#5A4630", w * 0.7) if (r + k) % 3 == 1
                else stroke([(x - 0.015, y), (x, y + 0.015), (x + 0.015, y)], "#5A4630", w * 0.6) for k, x in enumerate(np.arange(-0.22, 0.24, 0.06))))
    return g, None


def _hieroglyphs(m, w):
    g = VGroup(rect(-0.4, 0.0, 0.4, 0.8, "#D9B98A", w))
    ink = "#3E5C82"
    for col_ in range(3):
        x = -0.25 + col_ * 0.25
        g.add(line((x + 0.12, 0.05), (x + 0.12, 0.75), "#B5955E", w * 0.5),
              ell(x, 0.68, 0.1, 0.05, ink, w * 0.5), circ(x + 0.01, 0.68, 0.015, "#F7F5F0", 0),
              poly([(x - 0.05, 0.5), (x + 0.05, 0.5), (x, 0.6)], "#B83227", w * 0.4),
              stroke([(x - 0.05, 0.38), (x - 0.02, 0.44), (x + 0.02, 0.38), (x + 0.05, 0.44)], ink, w),
              VGroup(ell(x, 0.24, 0.06, 0.08, "#4F9A6A", w * 0.4), line((x, 0.2), (x, 0.12), "#4F9A6A", w)),
              circ(x, 0.08, 0.03, "#C2552B", w * 0.4))
    return g, None


def _sphinx(m, w):
    c = "#D9B98A"
    return VGroup(rect(-0.75, 0.0, 0.75, 0.06, tint(c, -0.15), w),
                  poly([(-0.68, 0.06), (-0.68, 0.2), (-0.55, 0.28), (0.18, 0.3), (0.18, 0.06)], c, w),
                  poly([(0.1, 0.06), (0.66, 0.06), (0.66, 0.12), (0.1, 0.12)], c, w), line((0.36, 0.06), (0.36, 0.12), tint(c, -0.3), w * 0.5),
                  poly([(0.08, 0.24), (0.12, 0.6), (0.3, 0.68), (0.48, 0.6), (0.52, 0.24), (0.42, 0.3), (0.42, 0.5), (0.18, 0.5), (0.18, 0.3)],
                       tint(c, -0.08), w),
                  *(line((0.12 + 0.01 * i, 0.55 - i * 0.07), (0.17, 0.55 - i * 0.07), tint(c, -0.3), w * 0.5) for i in range(4)),
                  *(line((0.43, 0.55 - i * 0.07), (0.48 - 0.01 * i, 0.55 - i * 0.07), tint(c, -0.3), w * 0.5) for i in range(4)),
                  rect(0.18, 0.28, 0.42, 0.52, c, w), circ(0.25, 0.44, 0.014, "#3A2A1E", 0), circ(0.35, 0.44, 0.014, "#3A2A1E", 0),
                  line((0.27, 0.34), (0.33, 0.34), "#8C6A42", w * 0.7), rect(0.27, 0.22, 0.33, 0.3, tint(c, -0.1), w * 0.6)), None


def _sarcophagus(m, w):
    return VGroup(blob([(-0.12, 0.0), (-0.16, 0.3), (-0.13, 0.62), (-0.08, 0.76), (0.08, 0.76), (0.13, 0.62), (0.16, 0.3), (0.12, 0.0)], GOLD, w),
                  blob([(-0.08, 0.5), (-0.09, 0.62), (0.0, 0.68), (0.09, 0.62), (0.08, 0.5), (0.0, 0.46)], "#C08A5E", w * 0.6),
                  poly([(-0.13, 0.62), (-0.16, 0.42), (-0.08, 0.5)], "#2E5E9E", w * 0.5), poly([(0.13, 0.62), (0.16, 0.42), (0.08, 0.5)], "#2E5E9E", w * 0.5),
                  *(circ(x, 0.58, 0.01, "#2B2826", 0) for x in (-0.03, 0.03)),
                  *(line((-0.13, y), (0.13, y), "#2E5E9E", w * 1.4) for y in (0.38, 0.32, 0.18)), rect(-0.06, 0.2, 0.06, 0.3, "#B83227", w * 0.4)), None


def _aqueduct(m, w):
    c = "#D9C29A"
    g = VGroup(rect(-0.9, 0.62, 0.9, 0.72, c, w), rect(-0.9, 0.72, 0.9, 0.76, WATER, w * 0.5))
    for i in range(5):
        x = -0.72 + i * 0.36
        g.add(poly([(x - 0.18, 0.0), (x - 0.18, 0.62), (x + 0.18, 0.62), (x + 0.18, 0.0), (x + 0.12, 0.0), *zoo.P._arc(x, 0.38, 0.12, 0, 180, 10), (x - 0.12, 0.0)],
                   c, w))
        g.add(*(poly([(x - 0.09 + 0.06 * k - 0.025, 0.49), (x - 0.09 + 0.06 * k + 0.025, 0.49), (x - 0.09 + 0.06 * k + 0.025, 0.6),
                       (x - 0.09 + 0.06 * k - 0.025, 0.6)], tint(c, -0.3), 0) for k in range(4)))
    return g, None


def _longship(m, w):
    g = VGroup(blob([(-0.65, 0.4), (-0.55, 0.12), (0.0, 0.04), (0.55, 0.12), (0.65, 0.4), (0.5, 0.2), (-0.5, 0.2)], WOOD, w),
               stroke([(-0.65, 0.4), (-0.72, 0.5), (-0.66, 0.56)], WOOD_D, w * 2), stroke([(0.65, 0.4), (0.72, 0.5), (0.66, 0.56)], WOOD_D, w * 2),
               line((0.0, 0.2), (0.0, 0.95), WOOD_D, w * 1.8),
               poly([(-0.28, 0.9), (0.28, 0.9), (0.3, 0.42), (-0.3, 0.42)], "#F3EEE4", w))
    g.add(*(poly([(-0.28 + i * 0.14, 0.9), (-0.21 + i * 0.14, 0.9), (-0.2 + i * 0.14, 0.42), (-0.27 + i * 0.14, 0.42)], RED, 0) for i in range(0, 4, 2)),
          *(circ(x, 0.24, 0.045, ("#E2B65A", RED, "#3E7CB1")[i % 3], w * 0.5) for i, x in enumerate(np.linspace(-0.4, 0.4, 7))))
    return g, None


def _astrolabe(m, w):
    g = VGroup(circ(0.0, 0.25, 0.22, GOLD, w), circ(0.0, 0.25, 0.17, GOLD_D, w * 0.5), circ(0.0, 0.5, 0.04, GOLD, w * 0.8))
    g.add(*(line((0.17 * math.cos(a), 0.25 + 0.17 * math.sin(a)), (0.21 * math.cos(a), 0.25 + 0.21 * math.sin(a)), "#6B4A2F", w * 0.5) for a in np.linspace(0, 2 * math.pi, 25)[:-1]),
          Circle(radius=0.09, stroke_color="#6B4A2F", stroke_width=w * 0.7).move_to([0.03, 0.27, 0]), line((-0.17, 0.2), (0.17, 0.3), "#6B4A2F", w * 1.2),
          circ(0.0, 0.25, 0.015, "#3A3631", 0))
    return g, None


def _guillotine(m, w):
    return VGroup(rect(-0.3, 0.0, 0.3, 0.1, WOOD_D, w), *(rect(x - 0.03, 0.1, x + 0.03, 1.1, WOOD, w) for x in (-0.18, 0.18)),
                  rect(-0.24, 1.08, 0.24, 1.14, WOOD_D, w), poly([(-0.15, 0.85), (0.15, 0.78), (0.15, 0.95), (-0.15, 0.95)], "#C9CED2", w),
                  rect(-0.15, 0.2, 0.15, 0.28, WOOD_D, w), ell(0.0, 0.26, 0.06, 0.05, "#3A2A1E", 0)), None


def _yurt(m, w):
    c = col(m["color"]) if m.get("color") else "#F3EEE4"
    return VGroup(rect(-0.5, 0.0, 0.5, 0.35, c, w), poly([(-0.55, 0.35), (0.0, 0.62), (0.55, 0.35)], tint(c, -0.06), w),
                  *(line((-0.5, y), (0.5, y), "#B83227", w * 1.2) for y in (0.1, 0.28)), *(line((x, 0.35), (x * 0.25, 0.58), "#B83227", w * 0.6) for x in (-0.4, -0.15, 0.15, 0.4)),
                  rect(-0.1, 0.0, 0.1, 0.24, "#B83227", w), rect(-0.07, 0.03, 0.07, 0.2, "#E2B65A", w * 0.4),
                  live(stroke([(0.0, 0.62), (0.03, 0.7), (-0.02, 0.78)], "#C9C2B2", w * 0.8), "steam")), None


def _stepwell(m, w):
    c = "#C9A06A"
    g = VGroup(rect(-0.9, 0.0, 0.9, 0.6, tint(c, -0.1), w))
    for i in range(6):
        hw = 0.85 - i * 0.12
        y = 0.55 - i * 0.09
        g.add(rect(-hw, y - 0.09, hw, y, tint(c, 0.04 * (i % 2)), w * 0.6))
        g.add(*(poly([(-hw + 0.04 + k * 0.1, y - 0.07), (-hw + 0.08 + k * 0.1, y - 0.07), (-hw + 0.08 + k * 0.1, y - 0.02),
                      (-hw + 0.04 + k * 0.1, y - 0.02)], tint(c, -0.3), 0) for k in range(int(hw * 2 / 0.1) - 1)))
    g.add(rect(-0.18, 0.0, 0.18, 0.06, WATER, w * 0.5))
    return g, None


def _torii(m, w):
    c = col(m["color"]) if m.get("color") else "#C9302C"
    return VGroup(*(rect(x - 0.05, 0.0, x + 0.05, 0.75, c, w) for x in (-0.35, 0.35)),
                  rect(-0.5, 0.62, 0.5, 0.68, c, w), poly([(-0.62, 0.8), (0.62, 0.8), (0.55, 0.88), (-0.55, 0.88)], "#2B2826", w),
                  rect(-0.55, 0.75, 0.55, 0.8, c, w), rect(-0.04, 0.68, 0.04, 0.75, c, w * 0.6)), None


def _dhow(m, w):
    c = col(m["color"]) if m.get("color") else WOOD
    return VGroup(blob([(-0.55, 0.26), (-0.4, 0.06), (0.3, 0.04), (0.6, 0.3), (0.3, 0.22), (-0.4, 0.22)], c, w),
                  line((0.0, 0.22), (-0.05, 0.85), WOOD_D, w * 1.6),
                  live(poly([(-0.45, 0.3), (0.35, 0.95), (0.05, 0.3)], "#F3EEE4", w), "puff"), line((-0.45, 0.3), (0.35, 0.95), WOOD_D, w * 1.2)), None


def _junkship(m, w):
    g = VGroup(blob([(-0.6, 0.38), (-0.5, 0.08), (0.45, 0.06), (0.62, 0.36), (0.4, 0.26), (-0.45, 0.26)], "#8C4A2A", w))
    for x, h, wd in ((-0.25, 0.85, 0.3), (0.2, 0.75, 0.26)):
        g.add(line((x, 0.26), (x, h + 0.05), WOOD_D, w * 1.4), poly([(x - wd / 2, 0.36), (x + wd / 2, 0.36), (x + wd / 2 + 0.04, h), (x - wd / 2 + 0.02, h)], "#D9A24A", w))
        g.add(*(line((x - wd / 2, y), (x + wd / 2 + 0.03 * (y - 0.36) / (h - 0.36), y), "#8C5E28", w * 0.6) for y in np.linspace(0.45, h - 0.05, 4)))
    return g, None


def _porcelainvase(m, w):
    g = VGroup(blob([(-0.07, 0.0), (-0.18, 0.15), (-0.16, 0.36), (-0.06, 0.48), (-0.07, 0.6), (0.07, 0.6), (0.06, 0.48), (0.16, 0.36), (0.18, 0.15), (0.07, 0.0)],
                    "#F7F7F2", w))
    g.add(stroke([(-0.17, 0.12), (0.17, 0.12)], "#2E5E9E", w), stroke([(-0.08, 0.5), (0.08, 0.5)], "#2E5E9E", w),
          stroke([(-0.12, 0.2), (-0.05, 0.3), (0.02, 0.22), (0.1, 0.34)], "#2E5E9E", w * 1.2),
          *(circ(x, y, 0.025, "#2E5E9E", w * 0.3) for x, y in ((-0.05, 0.3), (0.1, 0.34), (-0.1, 0.36))))
    return g, None


# -- India --------------------------------------------------------------------------------------------------------

def _chaistall(m, w):
    return VGroup(rect(-0.45, 0.0, 0.45, 0.35, "#C99A62", w), rect(-0.45, 0.35, 0.45, 0.4, WOOD_D, w),
                  *(line((x, 0.4), (x, 0.8), WOOD, w * 1.4) for x in (-0.42, 0.42)), poly([(-0.55, 0.8), (0.55, 0.8), (0.45, 0.72), (-0.45, 0.72)], "#2E7D74", w),
                  rect(-0.3, 0.6, 0.3, 0.7, "#F2C14E", w * 0.6), letters(m.get("label") or "CHAI", 0.0, 0.65, 0.05, "#B83227"),
                  ell(-0.15, 0.48, 0.18, 0.12, "#B8BEC2", w), live(stroke([(-0.15, 0.55), (-0.18, 0.62), (-0.14, 0.68)], "#C9C2B2", w * 0.8), "steam"),
                  *(blob([(x - 0.03, 0.4), (x - 0.035, 0.46), (x + 0.035, 0.46), (x + 0.03, 0.4)], "#C2552B", w * 0.5) for x in (0.1, 0.18, 0.26))), None


def _toran(m, w):
    g = VGroup(line((-0.5, 0.5), (0.5, 0.5), "#3A3631", w * 0.8))
    for i, x in enumerate(np.linspace(-0.45, 0.45, 10)):
        g.add(blob([(x - 0.04, 0.5), (x, 0.36), (x + 0.04, 0.5)], "#4F9A6A" if i % 2 else "#F2A93B", w * 0.4))
    g.add(*(circ(x, 0.5, 0.025, "#E07B39", w * 0.3) for x in np.linspace(-0.4, 0.4, 5)))
    return g, None


def _handfan(m, w):
    g = VGroup(line((0.0, 0.0), (0.0, 0.25), WOOD, w * 1.6))
    for a in np.linspace(20, 160, 8):
        r = math.radians(a)
        g.add(poly([(0.0, 0.22), (0.24 * math.cos(r - 0.1), 0.22 + 0.24 * math.sin(r - 0.1)), (0.24 * math.cos(r + 0.1), 0.22 + 0.24 * math.sin(r + 0.1))],
                   ("#B83227", "#F2C14E")[int(a) % 2], w * 0.5))
    return g, None


def _bangles(m, w):
    return VGroup(*(Ellipse(width=0.24, height=0.07, stroke_color=c, stroke_width=w * 2.4).move_to([0.0, 0.03 + i * 0.03, 0])
                    for i, c in enumerate(("#B83227", GOLD, "#2E7D4E", GOLD, "#B83227")))), None


# -- small bits of nature -------------------------------------------------------------------------------------

def _pebbles(m, w):
    return VGroup(*(ell(x, y, a, b, c, w * 0.6) for x, y, a, b, c in ((-0.15, 0.04, 0.14, 0.08, "#9A948A"), (0.0, 0.035, 0.1, 0.07, "#C9C2B2"),
                                                                      (0.14, 0.04, 0.13, 0.08, "#8A8478"), (-0.05, 0.1, 0.1, 0.06, "#B5AD9C")))), None


def _feather(m, w):
    return VGroup(blob([(0.0, 0.0), (-0.06, 0.15), (-0.07, 0.32), (0.0, 0.45), (0.06, 0.32), (0.05, 0.15)], "#9FC5DA", w),
                  line((0.0, -0.04), (0.0, 0.44), "#F7F5F0", w), *(line((0.0, y), (s * 0.05, y + 0.03), "#6FA8DC", w * 0.4) for y in (0.12, 0.2, 0.28, 0.36) for s in (-1, 1))), None


def _acorn(m, w):
    return VGroup(blob([(-0.06, 0.08), (-0.05, 0.02), (0.0, 0.0), (0.05, 0.02), (0.06, 0.08)], "#B5803A", w),
                  blob(zoo.P._arc(0.0, 0.08, 0.075, 0, 180, 10), "#6B4A2F", w), line((0.0, 0.155), (0.01, 0.19), "#6B4A2F", w * 1.2),
                  *(circ(x, 0.11, 0.006, "#4A3220", 0) for x in (-0.03, 0.0, 0.03))), None


def _pinecone(m, w):
    g = VGroup()
    for r in range(6):
        y = 0.04 + r * 0.05
        hw = 0.09 * math.sin((r + 1) / 7 * math.pi)
        g.add(*(blob([(x - 0.025, y), (x, y + 0.05), (x + 0.025, y)], "#8C5E38", w * 0.5) for x in np.linspace(-hw, hw, max(2, int(hw / 0.03) + 1))))
    g.add(line((0.0, 0.33), (0.0, 0.38), "#6B4A2F", w))
    return g, None


def _spiderweb(m, w):
    g = VGroup()
    for a in np.linspace(0, 2 * math.pi, 9)[:-1]:
        g.add(line((0.0, 0.3), (0.3 * math.cos(a), 0.3 + 0.3 * math.sin(a)), "#9AA3A9", w * 0.5))
    for r in (0.08, 0.15, 0.22, 0.28):
        pts = [(r * math.cos(a), 0.3 + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 9)]
        g.add(*(line(pts[i], pts[i + 1], "#9AA3A9", w * 0.5) for i in range(8)))
    g.add(circ(0.1, 0.32, 0.025, "#2B2826", 0), *(line((0.1, 0.32), (0.1 + 0.04 * math.cos(a), 0.32 + 0.04 * math.sin(a)), "#2B2826", w * 0.5) for a in np.linspace(0, 2 * math.pi, 9)[:-1]))
    return g, None


def _anthill(m, w):
    return VGroup(blob([(-0.3, 0.0), (-0.15, 0.12), (-0.04, 0.24), (0.04, 0.24), (0.15, 0.12), (0.3, 0.0)], "#B5875E", w),
                  ell(0.0, 0.23, 0.05, 0.02, "#3A2A1E", 0), *(circ(x, y, 0.01, "#2B2826", 0) for x, y in ((0.18, 0.04), (0.24, 0.02), (-0.2, 0.05), (0.08, 0.17))),
                  *(stroke([(x, 0.06), (x + 0.03, 0.1)], "#9A6E48", w * 0.5) for x in (-0.12, 0.05))), None


# -- farms and fields; water in all its places (scenes, drawn wide, to stand behind people or alone) -----------------
WHEAT_C, SOIL, SOIL_D, LEAF = "#E2C066", "#8C6A42", "#6B4E2E", "#6E9A4A"


def field_strips(x0, x1, y0, y1, n, colours, w):
    """Fields seen across: strips going back, alternating colours, narrowing to the horizon."""
    g = VGroup()
    for i in range(n):
        a, b = y0 + (y1 - y0) * i / n, y0 + (y1 - y0) * (i + 1) / n
        k0, k1 = 1 - 0.25 * (a - y0) / (y1 - y0), 1 - 0.25 * (b - y0) / (y1 - y0)
        g.add(poly([(x0 * k0, a), (x1 * k0, a), (x1 * k1, b), (x0 * k1, b)], colours[i % len(colours)], w * 0.5))
    return g


# -- water -------------------------------------------------------------------------------------------------------


# -- small things that make a scene: tufts, birds, clouds, glints, shading (used by the farms and the water) ---------

def tufts(xs, y, w, c="#5E8A3E", h=0.05):
    """Little tufts of grass along a line."""
    g = VGroup()
    for i, x in enumerate(xs):
        yy = y + 0.008 * math.sin(i * 2.1)
        g.add(stroke([(x - 0.012, yy), (x - 0.02, yy + h * 0.8)], c, w * 0.5), stroke([(x, yy), (x + 0.003, yy + h)], c, w * 0.5),
              stroke([(x + 0.012, yy), (x + 0.022, yy + h * 0.75)], c, w * 0.5))
    return g


def birds(pts, w, c="#3A3631"):
    return VGroup(*(live(stroke([(x - 0.045 * s, y + 0.012 * s), (x - 0.018 * s, y), (x, y - 0.006 * s), (x + 0.018 * s, y), (x + 0.045 * s, y + 0.012 * s)], c, w * 0.7),
                         "puff") for x, y, s in pts))


def sky_cloud(x, y, s, w):
    return live(blob([(x - 0.22 * s, y), (x - 0.18 * s, y + 0.07 * s), (x - 0.06 * s, y + 0.12 * s), (x + 0.06 * s, y + 0.1 * s), (x + 0.16 * s, y + 0.12 * s),
                      (x + 0.24 * s, y + 0.04 * s), (x + 0.2 * s, y - 0.01 * s)], "#FBFBF8", w * 0.6), "puff")


def glints(pts, w, c="#EAF4FA"):
    return VGroup(*(stroke([(x, y), (x + l, y)], c, w * 1.1) for x, y, l in pts))


def shadow_under(x0, x1, y, w):
    """A soft shadow on the ground under a thing."""
    return fill_only([(x0, y), ((x0 + x1) / 2, y - 0.015), (x1, y), ((x0 + x1) / 2, y + 0.012)], "#3A3631", 0.15)


def flowers(pts, w):
    return VGroup(*(VGroup(stroke([(x, y), (x, y + 0.04)], "#5E8A3E", w * 0.4), circ(x, y + 0.045, 0.012, c, w * 0.2))
                    for (x, y), c in zip(pts, ("#F7F5F0", "#F2C14E", "#D46A9A", "#F7F5F0", "#F2C14E", "#D46A9A") * 4)))


def round_tree(x, y, s, w, c="#5E8A3E"):
    """A leafy tree: trunk, a crown of overlapping lobes, light on one side."""
    return VGroup(stroke([(x, y), (x - 0.005, y + 0.14 * s), (x + 0.03 * s, y + 0.22 * s)], WOOD_D, w * 2.2 * s),
                  *(circ(x + dx * s, y + (0.28 + dy) * s, r * s, tint(c, k), w * 0.5) for dx, dy, r, k in
                    ((-0.08, 0.0, 0.1, -0.08), (0.08, 0.01, 0.1, -0.05), (0.0, 0.08, 0.12, 0.0), (-0.04, 0.03, 0.09, 0.06), (0.05, 0.06, 0.07, 0.12))))


def fence(x0, x1, y, w, h=0.12, n=None):
    n = n or max(2, int((x1 - x0) / 0.12))
    g = VGroup(line((x0, y + h * 0.75), (x1, y + h * 0.75), WOOD, w * 0.9), line((x0, y + h * 0.35), (x1, y + h * 0.35), WOOD, w * 0.9))
    g.add(*(VGroup(line((x, y), (x, y + h), WOOD_D, w * 1.3), poly([(x - 0.008, y + h), (x, y + h + 0.015), (x + 0.008, y + h)], WOOD_D, 0))
            for x in np.linspace(x0, x1, n)))
    return g


def sky_band(x0, x1, y0, y1, w, c="#DCEAF2"):
    return VGroup(fill_only([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], c, 1.0, smooth=False),
                  fill_only([(x0, y0), (x1, y0), (x1, y0 + (y1 - y0) * 0.35), (x0, y0 + (y1 - y0) * 0.35)], "#EEF3E8", 1.0, smooth=False))


# -- farms and fields, drawn in more detail ------------------------------------------------------------------------

def _farmland(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.55, 1.0, w), sky_cloud(-0.55, 0.85, 0.8, w), sky_cloud(0.45, 0.9, 0.6, w),
               birds(((0.05, 0.86, 1.0), (0.15, 0.9, 0.8)), w),
               blob([(-1.0, 0.55), (-0.6, 0.66), (-0.2, 0.62), (0.3, 0.7), (0.7, 0.63), (1.0, 0.66), (1.0, 0.55)], "#9DBF7A", w * 0.4))
    cols = ("#8DBB6A", "#E2C066", "#B5875E", "#A6C97A", "#D9B45A", "#7FA85A")
    strips = field_strips(-1.0, 1.0, 0.0, 0.58, 6, cols, w)
    g.add(strips)
    for i, sub in enumerate(strips):
        pts = sub.get_all_points() if hasattr(sub, "get_all_points") else sub.points
        y0, y1 = pts[:, 1].min(), pts[:, 1].max()
        k = 1 - 0.25 * ((y0 + y1) / 2) / 0.58
        c = cols[i % len(cols)]
        if c in ("#E2C066", "#D9B45A"):          # ripe grain: ears in rows
            g.add(*(stroke([(x, y0 + 0.01), (x + 0.008, y1 - 0.01)], tint(c, -0.25), w * 0.4) for x in np.linspace(-0.92 * k, 0.92 * k, 26)))
        elif c == "#B5875E":                     # ploughed: furrows
            g.add(*(line((-0.95 * k, y), (0.95 * k, y), tint(c, -0.25), w * 0.5) for y in np.linspace(y0 + 0.015, y1 - 0.015, 4)))
        else:                                    # green: rows of young plants
            g.add(*(stroke([(x, y0 + 0.012), (x, y0 + 0.04)], tint(c, -0.3), w * 0.5) for x in np.linspace(-0.92 * k, 0.92 * k, 22)))
    g.add(*(round_tree(x, 0.56, s, w) for x, s in ((-0.75, 0.55), (-0.68, 0.45), (0.15, 0.5), (0.62, 0.55))),
          fence(-1.0, -0.1, 0.0, w, 0.08), shadow_under(-1.0, 1.0, 0.0, w))
    return g, None


def _farm(m, w):
    g, _ = _farmland(m, w)
    barn = VGroup(rect(-0.78, 0.56, -0.38, 0.84, "#A8382B", w), poly([(-0.83, 0.84), (-0.58, 1.02), (-0.33, 0.84)], "#7A2A20", w),
                  stroke([(-0.85, 0.83), (-0.58, 1.04), (-0.31, 0.83)], "#F7F5F0", w * 1.4), rect(-0.66, 0.56, -0.5, 0.74, "#6B2A20", w * 0.7),
                  line((-0.66, 0.56), (-0.5, 0.74), "#F7F5F0", w * 0.7), line((-0.5, 0.56), (-0.66, 0.74), "#F7F5F0", w * 0.7),
                  rect(-0.62, 0.8, -0.54, 0.88, "#F7F5F0", w * 0.5), *(line((-0.78, y), (-0.38, y), "#8E2E22", w * 0.4) for y in (0.62, 0.68, 0.76)))
    house = VGroup(rect(-0.22, 0.56, 0.1, 0.8, "#F3E1C8", w), poly([(-0.27, 0.8), (-0.06, 0.95), (0.15, 0.8)], "#6B4A2F", w),
                   *(line((-0.24 + 0.02 * k, 0.82 + 0.03 * k), (0.12 - 0.02 * k, 0.82 + 0.03 * k), "#5A3E28", w * 0.4) for k in range(4)),
                   rect(-0.1, 0.56, -0.02, 0.7, "#6B4A2F", w * 0.6), circ(-0.035, 0.63, 0.006, GOLD, 0),
                   rect(0.0, 0.66, 0.07, 0.74, "#9FC5DA", w * 0.5), line((0.035, 0.66), (0.035, 0.74), "#F7F5F0", w * 0.4),
                   rect(-0.2, 0.66, -0.13, 0.74, "#9FC5DA", w * 0.5), rect(0.02, 0.86, 0.06, 0.95, "#8C6A42", w * 0.5),
                   live(stroke([(0.04, 0.96), (0.02, 1.02), (0.06, 1.08)], "#C9C2B2", w * 0.7), "steam"))
    silo = VGroup(rect(0.28, 0.56, 0.42, 1.0, "#C9CED2", w), blob(zoo.P._arc(0.35, 1.0, 0.07, 0, 180, 8), "#9AA3A9", w),
                  *(line((0.28, y), (0.42, y), "#9AA3A9", w * 0.4) for y in np.arange(0.62, 1.0, 0.06)))
    hay = VGroup(*(VGroup(ell(x, 0.6, 0.1, 0.07, "#E2C066", w * 0.5), stroke(zoo.P._arc(x, 0.6, 0.03, 0, 330, 8), "#C9A44E", w * 0.4)) for x in (0.52, 0.62)))
    g.add(barn, house, silo, hay, stroke([(-0.06, 0.56), (-0.02, 0.4), (0.06, 0.25), (0.1, 0.0)], "#D9C29A", w * 4))
    return g, None


def _farmhouse(m, w):
    g = VGroup(shadow_under(-0.6, 0.6, 0.0, w), rect(-0.45, 0.0, 0.45, 0.45, "#F3E1C8", w),
               *(line((-0.45, y), (0.45, y), "#E2CDB0", w * 0.4) for y in np.arange(0.06, 0.45, 0.06)),
               poly([(-0.53, 0.45), (0.0, 0.76), (0.53, 0.45)], "#B5643C", w),
               *(line((-0.5 + 0.06 * k, 0.47 + 0.035 * k), (0.5 - 0.06 * k, 0.47 + 0.035 * k), "#8E4A2A", w * 0.5) for k in range(7)),
               rect(-0.09, 0.0, 0.09, 0.27, "#6B4A2F", w * 0.8), rect(-0.07, 0.15, 0.07, 0.25, "#5A3E28", w * 0.4), circ(0.055, 0.12, 0.01, GOLD, 0),
               rect(-0.12, -0.02, 0.12, 0.0, "#B5AD9C", w * 0.5), poly([(-0.14, 0.27), (0.14, 0.27), (0.1, 0.32), (-0.1, 0.32)], "#8E4A2A", w * 0.5))
    for x in (-0.28, 0.28):
        g.add(rect(x - 0.09, 0.2, x + 0.09, 0.34, "#9FC5DA", w * 0.6), line((x, 0.2), (x, 0.34), "#F7F5F0", w * 0.6),
              line((x - 0.09, 0.27), (x + 0.09, 0.27), "#F7F5F0", w * 0.6), rect(x - 0.11, 0.18, x + 0.11, 0.2, "#F7F5F0", w * 0.4),
              *(VGroup(ell(x + dx, 0.17, 0.05, 0.035, "#5E8A3E", w * 0.3), circ(x + dx, 0.185, 0.012, "#D46A9A", 0)) for dx in (-0.05, 0.05)))
    g.add(rect(0.22, 0.6, 0.3, 0.78, "#8C6A42", w * 0.6), rect(0.2, 0.77, 0.32, 0.8, "#6B4A2F", w * 0.5),
          live(stroke([(0.26, 0.81), (0.23, 0.9), (0.28, 0.98)], "#C9C2B2", w * 0.8), "steam"),
          tufts(np.linspace(-0.62, -0.48, 3), 0.0, w), tufts(np.linspace(0.5, 0.64, 3), 0.0, w), fence(0.48, 0.8, 0.0, w, 0.1, 4))
    return g, None


def _wheatfield(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.3, 0.75, w), sky_cloud(0.4, 0.62, 0.7, w), birds(((-0.4, 0.62, 0.9), (-0.3, 0.66, 0.7)), w),
               blob([(-1.0, 0.3), (-0.4, 0.42), (0.2, 0.38), (1.0, 0.44), (1.0, 0.3)], "#B5C98A", w * 0.4),
               poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.36), (-1.0, 0.36)], "#D9B45A", w * 0.5))
    for r in range(5):
        y = 0.04 + r * 0.065
        s = 1.0 - r * 0.12
        for x in np.linspace(-0.97 + 0.04 * (r % 2), 0.97, 22 - 2 * r):
            lean = 0.015 * math.sin(x * 9 + r)
            g.add(stroke([(x, y), (x + lean, y + 0.1 * s)], "#B5913A", w * 0.5),
                  ell(x + lean * 1.2, y + 0.12 * s, 0.022 * s, 0.05 * s, tint(WHEAT_C, 0.06 * ((r + int(x * 10)) % 2)), w * 0.25),
                  stroke([(x + lean * 1.2, y + 0.14 * s), (x + lean * 1.5 + 0.01, y + 0.18 * s)], "#C9A44E", w * 0.3))
    g.add(round_tree(0.8, 0.36, 0.45, w), round_tree(-0.85, 0.36, 0.35, w))
    return g, None


def _cornfield(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.5, 0.85, w), sky_cloud(-0.5, 0.75, 0.7, w),
               poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.08), (-1.0, 0.08)], SOIL, w * 0.5),
               *(line((-1.0, y), (1.0, y), SOIL_D, w * 0.4) for y in (0.025, 0.055)))
    for row, (dy, s, sh) in enumerate(((0.06, 0.8, -0.12), (0.0, 1.0, 0.0))):
        for x in np.linspace(-0.92 + 0.1 * row, 0.92, 10 - row):
            st = "#5E8A3E" if row else "#4F7A34"
            g.add(stroke([(x, 0.03 + dy), (x + 0.01, 0.58 * s + dy)], st, w * 1.4 * s),
                  *(tube([(x, y), (x + d * 0.14 * s, y + 0.1 * s), (x + d * 0.2 * s, y + 0.06 * s)], [0.045 * s, 0.03 * s, 0.004], tint(LEAF, sh), w * 0.4)
                    for y, d in ((0.18 * s + dy, 1), (0.28 * s + dy, -1), (0.4 * s + dy, 1), (0.48 * s + dy, -1))),
                  ell(x + 0.035 * s, 0.36 * s + dy, 0.045 * s, 0.12 * s, "#F2C14E", w * 0.4),
                  tube([(x + 0.035 * s, 0.31 * s + dy), (x + 0.06 * s, 0.42 * s + dy)], [0.05 * s, 0.01], "#8DBB6A", w * 0.3),
                  *(stroke([(x + 0.01, 0.58 * s + dy), (x + d * 0.04, 0.66 * s + dy)], "#C9A44E", w * 0.5) for d in (-1, 0, 1)))
    return g, None


def _paddyfield(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.42, 0.8, w), blob([(-1.0, 0.42), (-0.5, 0.58), (0.0, 0.5), (0.5, 0.62), (1.0, 0.5), (1.0, 0.42)], "#7FA85A", w * 0.4),
               *(round_tree(x, 0.42, 0.4, w, "#4F7F3A") for x in (-0.7, 0.55)),
               poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.42), (-1.0, 0.42)], "#8FB8D4", w * 0.5))
    for y in (0.13, 0.27):
        g.add(poly([(-1.0, y - 0.015), (1.0, y - 0.015), (1.0, y + 0.015), (-1.0, y + 0.015)], "#9A8A5E", w * 0.5),
              tufts(np.linspace(-0.95, 0.95, 12), y + 0.01, w, "#6E9A4A", 0.03))
    for r, y in enumerate((0.03, 0.17, 0.31)):
        for x in np.linspace(-0.92 + 0.05 * r, 0.92, 14):
            g.add(*(stroke([(x, y), (x + d, y + 0.075)], tint("#6E9A4A", -0.1 * (r == 0)), w * 0.55) for d in (-0.018, 0.0, 0.018)),
                  stroke([(x - 0.01, y - 0.005), (x + 0.01, y - 0.005)], "#B5D3E6", w * 0.5))
    g.add(glints(((-0.5, 0.08, 0.08), (0.3, 0.21, 0.1), (-0.1, 0.36, 0.08)), w), sky_cloud(0.0, 0.7, 0.6, w),
          VGroup(poly([(0.42, 0.05), (0.62, 0.05), (0.52, 0.12)], "#E2C27A", w * 0.6), rect(0.5, 0.0, 0.54, 0.05, "#3E5C82", w * 0.5)))
    return g, None


def _orchard(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.2, 0.8, w), poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.24), (-1.0, 0.24)], "#8DBB6A", w * 0.4),
               *(stroke([(x, 0.0), (x + 0.36, 0.22)], "#7FA85A", w * 2) for x in np.linspace(-0.95, 0.55, 5)))
    for r, (y, s) in enumerate(((0.16, 0.75), (0.0, 1.0))):
        for x in np.linspace(-0.8 + 0.18 * r, 0.8, 5 - r):
            g.add(shadow_under(x - 0.12 * s, x + 0.12 * s, y, w), round_tree(x, y, s * 0.9, w, "#5E8A3E"),
                  *(VGroup(circ(x + dx * s, y + (0.27 + dy) * s, 0.02 * s, RED, w * 0.25), circ(x + dx * s - 0.005, y + (0.275 + dy) * s, 0.006 * s, "#F7B4A6", 0))
                    for dx, dy in ((-0.08, 0.02), (0.07, 0.04), (0.0, -0.04), (0.08, -0.02), (-0.04, 0.1), (0.04, 0.12))))
    g.add(*(circ(x, 0.02, 0.016, RED, w * 0.25) for x in (-0.6, -0.55, 0.2, 0.62)),
          VGroup(poly([(0.35, 0.0), (0.5, 0.0), (0.48, 0.08), (0.37, 0.08)], "#C9A066", w * 0.6), *(circ(x, 0.09, 0.02, RED, w * 0.25) for x in (0.39, 0.425, 0.46))))
    return g, None


def _vegetablegarden(m, w):
    g = VGroup(poly([(-0.95, -0.02), (0.95, -0.02), (0.95, 0.5), (-0.95, 0.5)], "#8DBB6A", w * 0.4))
    for i, (y, crop) in enumerate(((0.0, "cabbage"), (0.16, "carrot"), (0.32, "tomato"))):
        g.add(rect(-0.82, y, 0.82, y + 0.1, SOIL, w * 0.6), *(line((-0.8, yy), (0.8, yy), SOIL_D, w * 0.3) for yy in (y + 0.03, y + 0.07)),
              rect(-0.84, y + 0.1, 0.84, y + 0.12, WOOD, w * 0.5))
        for x in np.linspace(-0.72, 0.72, 9):
            if crop == "cabbage":
                g.add(circ(x, y + 0.13, 0.055, "#7FB05A", w * 0.4), *(stroke(zoo.P._arc(x, y + 0.13, r, 30, 150, 6), "#5E8A3E", w * 0.4) for r in (0.03, 0.045)),
                      circ(x, y + 0.13, 0.022, "#B5D88A", 0))
            elif crop == "carrot":
                g.add(*(tube([(x, y + 0.1), (x + d, y + 0.21)], [0.022, 0.003], LEAF, w * 0.3) for d in (-0.025, 0.0, 0.025)),
                      poly([(x - 0.012, y + 0.1), (x + 0.012, y + 0.1), (x, y + 0.08)], "#E8822E", 0))
            else:
                g.add(line((x + 0.03, y + 0.1), (x + 0.03, y + 0.3), WOOD, w * 0.6), stroke([(x, y + 0.1), (x + 0.01, y + 0.26)], "#5E8A3E", w * 0.6),
                      *(tube([(x + 0.005, yy), (x - 0.05, yy + 0.03)], [0.025, 0.003], LEAF, w * 0.3) for yy in (y + 0.15, y + 0.21)),
                      circ(x + 0.02, y + 0.17, 0.022, RED, w * 0.3), circ(x - 0.01, y + 0.22, 0.018, "#E8524A", w * 0.3))
    g.add(VGroup(poly([(0.75, 0.5), (0.95, 0.5), (0.92, 0.62), (0.78, 0.62)], "#4F9A6A", w * 0.7), tube([(0.92, 0.58), (1.02, 0.66)], [0.03, 0.02], "#4F9A6A", w * 0.5)),
          VGroup(line((-0.9, 0.5), (-0.95, 0.8), WOOD, w * 1.2), poly([(-0.92, 0.5), (-0.86, 0.42), (-0.82, 0.5)], "#8E969C", w * 0.5)), fence(-0.95, 0.6, 0.5, w, 0.1))
    return g, None


def _pasture(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.32, 0.8, w), sky_cloud(-0.4, 0.7, 0.8, w), sky_cloud(0.5, 0.66, 0.55, w),
               blob([(-1.0, 0.3), (-0.6, 0.48), (0.0, 0.4), (0.6, 0.52), (1.0, 0.38), (1.0, 0.3)], "#9DBF7A", w * 0.4),
               blob([(-1.0, 0.0), (-1.0, 0.32), (0.0, 0.38), (1.0, 0.32), (1.0, 0.0)], "#8DBB6A", w),
               *(stroke([(x, 0.05), (x + 0.3, 0.3)], "#9CC77A", w * 3) for x in (-0.8, -0.2, 0.4)))
    g.add(fence(-0.95, 0.95, 0.1, w, 0.18, 11), tufts(np.linspace(-0.9, 0.9, 15), 0.02, w), flowers([(x, 0.05 + 0.03 * ((i * 3) % 4)) for i, x in enumerate(np.linspace(-0.85, 0.85, 12))], w),
          round_tree(0.75, 0.32, 0.55, w), VGroup(rect(-0.62, 0.0, -0.5, 0.06, "#9AA3A9", w * 0.6), rect(-0.61, 0.045, -0.51, 0.055, WATER, 0)))
    return g, None


def _irrigatedfields(m, w):
    g = VGroup(poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.62), (-1.0, 0.62)], "#8DBB6A", w * 0.5))
    plots = ((-0.95, -0.15, 0.04, 0.26, WHEAT_C), (0.15, 0.95, 0.04, 0.26, "#A6C97A"), (-0.95, -0.15, 0.36, 0.58, "#A6C97A"), (0.15, 0.95, 0.36, 0.58, WHEAT_C))
    for x0, x1, y0, y1, c in plots:
        g.add(rect(x0, y0, x1, y1, c, w * 0.5))
        if c == WHEAT_C:
            g.add(*(stroke([(x, y0 + 0.02), (x + 0.006, y1 - 0.02)], tint(c, -0.25), w * 0.4) for x in np.linspace(x0 + 0.03, x1 - 0.03, 18)))
        else:
            g.add(*(line((x0 + 0.03, y), (x1 - 0.03, y), tint(c, -0.25), w * 0.4) for y in np.linspace(y0 + 0.03, y1 - 0.03, 5)),
                  *(stroke([(x, y), (x, y + 0.02)], "#5E8A3E", w * 0.4) for x in np.linspace(x0 + 0.05, x1 - 0.05, 9) for y in np.linspace(y0 + 0.03, y1 - 0.05, 4)))
    g.add(rect(-0.08, 0.0, 0.08, 0.62, "#B5875E", w * 0.4), rect(-0.06, 0.0, 0.06, 0.62, WATER, w * 0.5),
          rect(-1.0, 0.28, 1.0, 0.34, "#B5875E", w * 0.4), rect(-1.0, 0.295, 1.0, 0.325, WATER, 0),
          *(rect(x, y, x + 0.03, y + 0.06, WATER, w * 0.3) for x, y in ((-0.55, 0.23), (0.5, 0.23), (-0.55, 0.33), (0.5, 0.33))),
          *(live(stroke([(-0.03, y), (0.0, y + 0.012), (0.03, y)], "#DDEEF6", w * 0.7), "steam") for y in (0.08, 0.2, 0.45, 0.56)),
          VGroup(line((-0.12, 0.6), (-0.12, 0.72), WOOD_D, w), line((-0.18, 0.66), (0.02, 0.74), WOOD, w * 1.4), rect(0.0, 0.62, 0.06, 0.68, CLAY_D, w * 0.5)))
    return g, None


def _teagarden(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.5, 1.0, w), sky_cloud(0.55, 0.88, 0.6, w),
               blob([(-1.0, 0.5), (-0.6, 0.85), (-0.2, 0.8), (0.3, 0.92), (1.0, 0.6), (1.0, 0.5)], "#6E8F7A", w * 0.4),
               blob([(-1.0, 0.0), (-1.0, 0.45), (-0.3, 0.72), (0.4, 0.64), (1.0, 0.42), (1.0, 0.0)], "#7FA85A", w))
    for r in range(6):
        y = 0.05 + r * 0.1
        hw = 0.95 - r * 0.11
        for x in np.linspace(-hw, hw, max(3, int(hw * 7))):
            c = "#4F7F3A" if r % 2 else "#5E8A3E"
            g.add(ell(x, y, 0.15, 0.075, c, w * 0.35), *(circ(x + dx, y + 0.02, 0.006, "#A6D07A", 0) for dx in (-0.03, 0.02)))
    g.add(*(VGroup(stroke([(x, 0.5), (x, 0.72)], WOOD_D, w * 1.2), blob([(x - 0.14, 0.7), (x, 0.82), (x + 0.14, 0.7), (x, 0.66)], "#3E6E2E", w * 0.5))
            for x in (-0.55, 0.3)),
          stroke([(-0.1, 0.0), (0.05, 0.2), (-0.05, 0.4), (0.08, 0.62)], "#C9A86A", w * 2.4),
          VGroup(circ(0.5, 0.33, 0.04, "#A8714A", w * 0.4), poly([(0.46, 0.31), (0.54, 0.31), (0.55, 0.18), (0.45, 0.18)], "#D46A9A", w * 0.4),
                 poly([(0.42, 0.34), (0.5, 0.36), (0.47, 0.26), (0.4, 0.27)], "#C9A66B", w * 0.4)))
    return g, None


def _henhouse(m, w):
    g = VGroup(shadow_under(-0.4, 0.5, 0.0, w), *(line((x, 0.0), (x, 0.15), WOOD_D, w * 1.4) for x in (-0.25, 0.25)),
               rect(-0.3, 0.15, 0.3, 0.45, "#C9A27A", w), *(line((-0.3, y), (0.3, y), "#A8805A", w * 0.4) for y in (0.22, 0.29, 0.36, 0.43)),
               poly([(-0.36, 0.45), (0.0, 0.62), (0.36, 0.45)], "#8C3A2B", w), *(line((-0.33 + 0.04 * k, 0.46 + 0.02 * k), (0.33 - 0.04 * k, 0.46 + 0.02 * k), "#6E2A20", w * 0.4) for k in range(4)),
               blob(zoo.P._arc(0.0, 0.18, 0.08, 0, 180, 8) + [(0.08, 0.18)], "#3A2A1E", w * 0.6),
               rect(0.12, 0.3, 0.24, 0.4, "#3A2A1E", w * 0.5), line((0.18, 0.3), (0.18, 0.4), "#C9A27A", w * 0.5),
               poly([(0.08, 0.15), (0.45, 0.0), (0.52, 0.0), (0.12, 0.17)], WOOD, w * 0.6), *(line((0.15 + 0.07 * k, 0.13 - 0.028 * k), (0.18 + 0.07 * k, 0.14 - 0.028 * k), WOOD_D, w * 0.6) for k in range(4)))
    for x in (-0.45, 0.6):
        g.add(ell(x, 0.07, 0.12, 0.09, "#F7F5F0", w * 0.6), circ(x + 0.05, 0.12, 0.03, "#F7F5F0", w * 0.5), poly([(x + 0.08, 0.12), (x + 0.11, 0.115), (x + 0.08, 0.105)], "#E2A23B", 0),
              poly([(x + 0.04, 0.15), (x + 0.05, 0.17), (x + 0.06, 0.15)], RED, 0), *(line((x + d, 0.03), (x + d, 0.0), "#E2A23B", w * 0.6) for d in (-0.015, 0.015)))
    g.add(*(ell(x, 0.01, 0.025, 0.018, "#C9A06A", w * 0.2) for x in (-0.2, -0.12, 0.35)))
    return g, None


def _seedbed(m, w):
    g = VGroup(poly([(-0.85, 0.0), (0.85, 0.0), (0.75, 0.24), (-0.75, 0.24)], SOIL, w))
    for k in range(5):
        y = 0.025 + k * 0.045
        g.add(stroke([(-0.8 + k * 0.02, y), (0.8 - k * 0.02, y)], SOIL_D, w * 0.7), stroke([(-0.8 + k * 0.02, y + 0.012), (0.8 - k * 0.02, y + 0.012)], "#A8805A", w * 0.4),
              *(ell(x, y + 0.008, 0.022, 0.014, "#E2C066", w * 0.2) for x in np.linspace(-0.65 + k * 0.03, 0.65 - k * 0.03, 10)))
    g.add(VGroup(rect(0.55, 0.2, 0.75, 0.34, "#F3E1C8", w * 0.6), letters("SEEDS", 0.65, 0.27, 0.03, "#6B4A2F"),
                 *(ell(0.7 + d, 0.22, 0.02, 0.012, "#E2C066", 0) for d in (0.05, 0.08))),
          VGroup(stroke([(-0.6, 0.24), (-0.62, 0.36)], "#6E9A4A", w * 0.6), tube([(-0.62, 0.34), (-0.66, 0.38)], [0.025, 0.004], LEAF, w * 0.3)))
    return g, None


def _growthstages(m, w):
    g = VGroup(rect(-0.9, -0.12, 0.9, 0.08, SOIL, w * 0.6), rect(-0.9, 0.06, 0.9, 0.08, "#7FA85A", 0))
    xs = (-0.7, -0.25, 0.2, 0.65)
    g.add(ell(xs[0], 0.0, 0.07, 0.045, "#D9A84E", w * 0.5), stroke([(xs[0], -0.02), (xs[0] + 0.01, -0.05)], "#F3E1C8", w * 0.5),
          stroke([(xs[1], 0.0), (xs[1], 0.18)], "#5E8A3E", w), *(tube([(xs[1], 0.18), (xs[1] + d, 0.24)], [0.04, 0.006], LEAF, w * 0.4) for d in (-0.06, 0.06)),
          *(stroke([(xs[1], 0.0), (xs[1] + d, -0.07)], "#F3E1C8", w * 0.5) for d in (-0.03, 0.02)),
          stroke([(xs[2], 0.0), (xs[2], 0.4)], "#5E8A3E", w * 1.2),
          *(tube([(xs[2], y), (xs[2] + d, y + 0.08)], [0.05, 0.008], LEAF, w * 0.4) for y, d in ((0.15, 0.12), (0.25, -0.12), (0.34, 0.1))),
          *(stroke([(xs[2], 0.0), (xs[2] + d, -0.1)], "#F3E1C8", w * 0.6) for d in (-0.05, 0.0, 0.05)),
          stroke([(xs[3], 0.0), (xs[3], 0.55)], "#5E8A3E", w * 1.4),
          *(tube([(xs[3], y), (xs[3] + d, y + 0.08)], [0.05, 0.008], LEAF, w * 0.4) for y, d in ((0.15, 0.12), (0.27, -0.12), (0.38, 0.12))),
          *(stroke([(xs[3], 0.0), (xs[3] + d, -0.11)], "#F3E1C8", w * 0.6) for d in (-0.07, -0.02, 0.04, 0.08)),
          *(circ(xs[3] + 0.045 * math.cos(a), 0.58 + 0.045 * math.sin(a), 0.032, "#F2C14E", w * 0.3) for a in np.linspace(0, 2 * math.pi, 7)[:-1]),
          circ(xs[3], 0.58, 0.024, "#B5643C", w * 0.3),
          *(VGroup(stroke([(x + 0.13, 0.3), (x + 0.3, 0.3)], "#9A948A", w * 0.8), poly([(x + 0.3, 0.33), (x + 0.34, 0.3), (x + 0.3, 0.27)], "#9A948A", 0)) for x in xs[:3]),
          *(letters(t, x, -0.08, 0.025, "#F3E1C8") for t, x in zip(("SEED", "SPROUT", "PLANT", "FLOWER"), xs)),
          circ(0.0, 0.75, 0.08, "#F2C14E", w * 0.5), *(live(line((0.0, 0.66), (x, 0.4), "#F2C14E", w * 0.4), "puff") for x in (-0.25, 0.2)))
    return g, None


def _roots(m, w):
    g = VGroup(rect(-0.6, -0.55, 0.6, 0.0, SOIL, w * 0.6), *(line((-0.6, y), (0.6, y), SOIL_D, w * 0.3) for y in (-0.15, -0.35)),
               rect(-0.6, 0.0, 0.6, 0.03, "#7FA85A", 0), tufts(np.linspace(-0.55, 0.55, 8), 0.02, w),
               stroke([(0.0, 0.0), (0.0, 0.48)], "#5E8A3E", w * 1.6),
               *(tube([(0.0, y), (d * 0.2, y + 0.1)], [0.07, 0.01], LEAF, w * 0.5) for y, d in ((0.15, 1), (0.25, -1), (0.35, 1), (0.43, -1))))
    for a, l in ((-1.2, 0.3), (-0.6, 0.4), (0.0, 0.45), (0.6, 0.38), (1.2, 0.28)):
        end = (l * math.sin(a), -l * math.cos(a) * 1.0 - 0.02)
        mid = (end[0] * 0.5, end[1] * 0.6)
        g.add(stroke([(0.0, 0.0), mid, end], "#F3E1C8", w * 1.3), stroke([mid, (mid[0] + 0.07, mid[1] - 0.08)], "#F3E1C8", w * 0.6),
              stroke([mid, (mid[0] - 0.06, mid[1] - 0.06)], "#F3E1C8", w * 0.5), stroke([end, (end[0] + 0.03, end[1] - 0.05)], "#F3E1C8", w * 0.4))
    g.add(*(ell(x, y, 0.07, 0.035, "#9AA3A9", w * 0.3) for x, y in ((-0.45, -0.3), (0.42, -0.15), (0.3, -0.45))),
          *(live(circ(x, y, 0.012, WATER, 0), "puff") for x, y in ((-0.2, -0.25), (0.15, -0.3), (0.3, -0.1))),
          VGroup(stroke([(-0.35, -0.1), (-0.3, -0.12), (-0.25, -0.1), (-0.2, -0.13)], "#D88A9A", w * 1.6)))
    return g, None


def _savanna(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.25, 1.0, w, "#F4D9A6"), circ(0.15, 0.62, 0.13, "#F2A93B", w * 0.4),
               blob([(-1.0, 0.25), (-0.5, 0.36), (0.2, 0.32), (1.0, 0.38), (1.0, 0.25)], "#C9B06A", w * 0.4),
               blob([(-1.0, 0.0), (-1.0, 0.27), (0.0, 0.32), (1.0, 0.27), (1.0, 0.0)], "#D9C27A", w),
               birds(((-0.3, 0.8, 1.0), (-0.2, 0.84, 0.8), (-0.12, 0.79, 0.7)), w))
    for x, s in ((-0.55, 1.0), (0.55, 0.75), (0.9, 0.45)):
        b = 0.18
        g.add(shadow_under(x - 0.3 * s, x + 0.3 * s, b, w),
              stroke([(x, b), (x + 0.02, b + 0.28 * s), (x - 0.12 * s, b + 0.48 * s)], WOOD_D, w * 2.6 * s),
              stroke([(x + 0.02, b + 0.28 * s), (x + 0.18 * s, b + 0.48 * s)], WOOD_D, w * 1.8 * s), stroke([(x + 0.01, b + 0.36 * s), (x + 0.05, b + 0.5 * s)], WOOD_D, w * s),
              blob([(x - 0.45 * s, b + 0.48 * s), (x - 0.25 * s, b + 0.6 * s), (x + 0.2 * s, b + 0.62 * s), (x + 0.45 * s, b + 0.54 * s), (x + 0.1 * s, b + 0.46 * s)], "#6E8F3A", w),
              stroke([(x - 0.35 * s, b + 0.52 * s), (x + 0.3 * s, b + 0.55 * s)], "#5A7A2E", w * 0.6))
    g.add(*(stroke([(x, 0.03), (x + 0.02, 0.13)], "#B5A24E", w * 0.6) for x in np.linspace(-0.95, 0.95, 26)),
          *(stroke([(x, 0.03), (x - 0.02, 0.1)], "#C9B05A", w * 0.5) for x in np.linspace(-0.9, 0.9, 20)))
    return g, None


def _hillvillage(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.5, 1.0, w), blob([(-1.0, 0.5), (-0.6, 0.85), (-0.2, 0.78), (0.3, 0.95), (0.8, 0.8), (1.0, 0.6), (1.0, 0.5)], "#8E8FA0", w * 0.4),
               poly([(0.18, 0.88), (0.3, 0.95), (0.42, 0.88)], SNOW, 0),
               blob([(-1.0, 0.0), (-1.0, 0.4), (-0.4, 0.75), (0.2, 0.6), (0.6, 0.72), (1.0, 0.45), (1.0, 0.0)], "#8DBB6A", w))
    for i in range(4):
        g.add(stroke([(-0.9 + 0.05 * i, 0.12 + i * 0.13), (0.9 - 0.05 * i, 0.1 + i * 0.13)], "#7FA85A", w * 0.6))
    for x, y in ((-0.6, 0.45), (-0.35, 0.58), (-0.1, 0.48), (0.15, 0.42), (0.45, 0.55), (0.7, 0.4), (-0.25, 0.28), (0.4, 0.25), (-0.7, 0.2)):
        g.add(rect(x - 0.07, y, x + 0.07, y + 0.1, "#F3E1C8", w * 0.6), poly([(x - 0.09, y + 0.1), (x, y + 0.16), (x + 0.09, y + 0.1)], "#B5643C", w * 0.6),
              rect(x - 0.015, y, x + 0.015, y + 0.05, "#6B4A2F", 0), rect(x + 0.03, y + 0.05, x + 0.055, y + 0.075, "#9FC5DA", 0))
    g.add(stroke([(-0.9, 0.05), (-0.5, 0.2), (0.0, 0.18), (0.5, 0.35), (0.9, 0.3)], "#C9A86A", w * 2.6),
          *(round_tree(x, y, 0.35, w, "#4F7F3A") for x, y in ((-0.85, 0.3), (0.85, 0.35), (0.2, 0.62))),
          live(stroke([(-0.35, 0.74), (-0.38, 0.82), (-0.34, 0.9)], "#C9C2B2", w * 0.7), "steam"))
    return g, None


# -- water, drawn in more detail ------------------------------------------------------------------------------

def _waterdrop(m, w):
    c = col(m["color"]) if m.get("color") else WATER
    return VGroup(fill_only([(-0.12, 0.0), (0.0, -0.015), (0.12, 0.0), (0.0, 0.012)], "#3A3631", 0.12),
                  blob([(0.0, 0.42), (0.05, 0.3), (0.12, 0.18), (0.12, 0.08), (0.06, 0.0), (-0.06, 0.0), (-0.12, 0.08), (-0.12, 0.18), (-0.05, 0.3)], c, w),
                  blob([(0.02, 0.36), (0.08, 0.2), (0.09, 0.08), (0.04, 0.03), (0.06, 0.12), (0.05, 0.24)], tint(c, -0.15), 0),
                  stroke([(-0.06, 0.08), (-0.075, 0.15), (-0.045, 0.23)], "#EAF4FA", w * 1.8), circ(-0.03, 0.28, 0.014, "#EAF4FA", 0),
                  live(VGroup(*(Ellipse(width=r, height=r * 0.25, stroke_color=tint(c, 0.3), stroke_width=w * 0.5).move_to([0.0, -0.005, 0]) for r in (0.3, 0.45))), "puff")), None


def _puddle(m, w):
    return VGroup(blob([(-0.42, 0.03), (-0.3, 0.08), (0.0, 0.07), (0.3, 0.09), (0.44, 0.04), (0.2, 0.0), (-0.2, 0.0)], WATER, w),
                  blob([(-0.3, 0.05), (0.0, 0.06), (0.25, 0.07), (0.1, 0.03)], "#B5D3E6", 0),
                  *(Ellipse(width=r * 2, height=r * 0.45, stroke_color="#EAF4FA", stroke_width=w * 0.6).move_to([x, 0.045, 0]) for x, r in ((0.05, 0.06), (0.05, 0.12), (-0.22, 0.05))),
                  live(VGroup(*(ell(x, 0.2 + k * 0.12, 0.018, 0.045, WATER, w * 0.3) for k, x in enumerate((-0.2, 0.15, 0.3, -0.05)))), "steam"),
                  tufts((-0.48, 0.48), 0.0, w), *(ell(x, 0.0, 0.05, 0.025, "#9A948A", w * 0.3) for x in (-0.36, 0.38))), None


def _pond(m, w):
    g = VGroup(ell(0.0, 0.1, 1.3, 0.28, "#7FA85A", w * 0.5), ell(0.0, 0.1, 1.0, 0.19, WATER_D, w), ell(0.02, 0.11, 0.85, 0.14, WATER, 0),
               glints(((-0.3, 0.14, 0.12), (0.1, 0.08, 0.08), (0.25, 0.15, 0.06)), w))
    for x, y in ((-0.25, 0.1), (0.15, 0.12), (0.3, 0.07)):
        g.add(blob([(x - 0.06, y), (x - 0.03, y + 0.025), (x + 0.05, y + 0.02), (x + 0.06, y), (x + 0.01, y - 0.02), (x, y)], "#6E9A4A", w * 0.4),
              line((x, y), (x + 0.05, y + 0.005), "#4F7A34", w * 0.4))
    g.add(*(circ(x + 0.01, y + 0.02, r, "#F2B8C6", w * 0.3) for x, y, r in ((-0.25, 0.1, 0.022), (0.15, 0.12, 0.018))),
          *(VGroup(stroke([(x, 0.13), (x + 0.01, 0.38)], "#6B5A3A", w), rrect(x - 0.012, 0.3, x + 0.022, 0.4, 0.015, "#6B4A2F", w * 0.4),
                   tube([(x, 0.15), (x + 0.06, 0.3)], [0.02, 0.003], LEAF, w * 0.3)) for x in (0.42, 0.47, 0.52, -0.48, -0.44)),
          VGroup(ell(-0.05, 0.12, 0.1, 0.05, "#F7F5F0", w * 0.5), circ(0.0, 0.16, 0.025, "#2E6E4E", w * 0.4), poly([(0.02, 0.165), (0.05, 0.16), (0.02, 0.155)], "#E2A23B", 0)),
          tufts(np.linspace(-0.6, -0.5, 3), 0.02, w), tufts(np.linspace(0.55, 0.62, 2), 0.02, w))
    return g, None


def _stream(m, w):
    g = VGroup(fill_only([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.5), (-1.0, 0.5)], "#8DBB6A", 1.0, smooth=False))
    path = [(-1.0, 0.42), (-0.5, 0.34), (-0.1, 0.22), (0.3, 0.15), (0.7, 0.05), (1.0, 0.0)]
    g.add(stroke(path, "#B5875E", w * 13), stroke(path, WATER_D, w * 10), stroke(path, WATER, w * 7),
          *(live(stroke([(x, y), (x + 0.04, y - 0.006), (x + 0.08, y - 0.01)], "#EAF4FA", w), "steam") for x, y in ((-0.75, 0.38), (-0.35, 0.29), (0.05, 0.2), (0.45, 0.11), (0.8, 0.03))))
    g.add(*(VGroup(ell(x, y, 0.09, 0.055, "#9A948A", w * 0.5), stroke([(x - 0.03, y + 0.02), (x + 0.02, y + 0.024)], "#C9C2B2", w * 0.5)) for x, y in ((-0.3, 0.3), (0.15, 0.2), (0.6, 0.1), (-0.65, 0.39))),
          tufts(np.linspace(-0.9, -0.4, 6), 0.05, w), tufts(np.linspace(0.2, 0.9, 7), 0.3, w),
          flowers([(x, y) for x, y in ((-0.8, 0.1), (-0.6, 0.15), (0.5, 0.35), (0.7, 0.3), (0.85, 0.38))], w), round_tree(-0.8, 0.45, 0.4, w), round_tree(0.8, 0.45, 0.35, w))
    return g, None


def _spring(m, w):
    return VGroup(blob([(-0.6, 0.0), (-0.52, 0.32), (-0.25, 0.5), (0.15, 0.52), (0.5, 0.35), (0.6, 0.0)], "#9A948A", w),
                  blob([(-0.4, 0.3), (-0.2, 0.42), (0.1, 0.44), (-0.1, 0.36)], "#B5AFA4", 0),
                  *(line((x, y), (x + 0.12, y - 0.02), "#7A746A", w * 0.5) for x, y in ((-0.4, 0.15), (0.2, 0.3), (0.25, 0.1))),
                  blob([(-0.1, 0.18), (-0.06, 0.27), (0.06, 0.27), (0.1, 0.18)], "#2B2826", w * 0.6),
                  live(stroke([(0.0, 0.2), (0.05, 0.12), (0.02, 0.05), (0.08, 0.0)], WATER, w * 3.2), "steam"),
                  live(stroke([(0.0, 0.2), (0.05, 0.12), (0.02, 0.05)], "#EAF4FA", w * 0.8), "steam"),
                  ell(0.12, 0.0, 0.55, 0.09, WATER, w * 0.6), *(Ellipse(width=r, height=r * 0.2, stroke_color="#EAF4FA", stroke_width=w * 0.5).move_to([0.1, 0.0, 0]) for r in (0.12, 0.25)),
                  *(VGroup(stroke([(x, 0.42), (x + 0.02, 0.52)], "#5E8A3E", w), tube([(x, 0.45), (x + 0.06, 0.5)], [0.02, 0.003], LEAF, w * 0.3)) for x in (-0.3, -0.25, 0.3)),
                  blob([(-0.45, 0.28), (-0.38, 0.34), (-0.3, 0.3)], "#7FA85A", w * 0.4), blob([(0.3, 0.35), (0.38, 0.4), (0.45, 0.33)], "#7FA85A", w * 0.4)), None


def _riverbend(m, w):
    g = VGroup(rect(-1.0, 0.0, 1.0, 0.8, "#8DBB6A", w * 0.5))
    for x, y, c in ((-0.85, 0.05, WHEAT_C), (0.55, 0.65, WHEAT_C), (-0.85, 0.62, "#A6C97A"), (0.62, 0.05, "#B5875E")):
        g.add(rect(x, y, x + 0.25, y + 0.12, c, w * 0.3), *(line((x + 0.02, yy), (x + 0.23, yy), tint(c, -0.25), w * 0.3) for yy in (y + 0.04, y + 0.08)))
    path = [(-1.0, 0.65), (-0.6, 0.7), (-0.35, 0.5), (-0.5, 0.25), (-0.2, 0.08), (0.2, 0.2), (0.35, 0.5), (0.65, 0.6), (1.0, 0.45)]
    g.add(stroke(path, "#D9C29A", w * 13), stroke(path, WATER_D, w * 10), stroke(path, WATER, w * 7),
          *(live(stroke([(x, y), (x + 0.05, y + 0.01)], "#EAF4FA", w * 0.8), "steam") for x, y in ((-0.75, 0.68), (-0.45, 0.36), (0.0, 0.12), (0.3, 0.38), (0.8, 0.54))))
    g.add(*(VGroup(circ(x, y, 0.05, "#5E8A3E", w * 0.4), circ(x + 0.03, y + 0.02, 0.035, "#6E9A4A", w * 0.3)) for x, y in ((-0.8, 0.35), (-0.1, 0.45), (0.65, 0.25), (0.0, 0.7), (-0.25, 0.25), (0.15, 0.62))),
          VGroup(rect(0.1, 0.4, 0.2, 0.47, "#F3E1C8", w * 0.4), poly([(0.09, 0.47), (0.15, 0.51), (0.21, 0.47)], "#B5643C", w * 0.4)),
          VGroup(rect(-0.62, 0.48, -0.42, 0.52, WOOD, w * 0.5)), stroke([(0.2, 0.4), (0.4, 0.35), (0.7, 0.4), (1.0, 0.35)], "#C9A86A", w * 1.6))
    return g, None


def _riverbank(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.45, 0.85, w), sky_cloud(0.4, 0.72, 0.6, w), birds(((-0.5, 0.75, 0.9), (-0.4, 0.78, 0.7)), w),
               poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.2), (-1.0, 0.2)], WATER, w * 0.5), poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.07), (-1.0, 0.07)], WATER_D, 0),
               *(live(stroke([(x, y), (x + 0.05, y + 0.012), (x + 0.1, y)], "#EAF4FA", w * 0.7), "steam") for x, y in ((-0.7, 0.1), (-0.2, 0.14), (0.3, 0.09), (0.75, 0.13))),
               poly([(-1.0, 0.18), (-0.7, 0.2), (-0.4, 0.22), (-0.1, 0.2), (0.2, 0.19), (0.6, 0.21), (1.0, 0.22), (1.0, 0.45), (-1.0, 0.45)],
                    "#B5875E", w * 0.6),
               *(line((-1.0, y), (1.0, y + 0.01), "#9A6E48", w * 0.4) for y in (0.28, 0.35)),
               poly([(-1.0, 0.43), (1.0, 0.43), (1.0, 0.5), (-1.0, 0.5)], "#8DBB6A", 0), tufts(np.linspace(-0.95, 0.95, 16), 0.45, w))
    g.add(*(VGroup(stroke([(x, 0.18), (x + 0.02, 0.44)], "#6B5A3A", w), rrect(x + 0.005, 0.38, x + 0.035, 0.47, 0.012, "#6B4A2F", w * 0.4),
                   tube([(x + 0.01, 0.25), (x + 0.07, 0.36)], [0.02, 0.003], LEAF, w * 0.3)) for x in (-0.82, -0.76, -0.7, 0.6, 0.66, 0.72)),
          *(stroke([(x, 0.19), (x - 0.04, 0.3)], "#6E9A4A", w * 0.8) for x in np.linspace(-0.6, 0.5, 10)),
          VGroup(blob([(-0.25, 0.08), (-0.2, 0.03), (0.15, 0.03), (0.2, 0.08)], WOOD, w * 0.6), line((-0.05, 0.08), (0.05, 0.22), WOOD_D, w)),
          round_tree(0.85, 0.48, 0.5, w), round_tree(-0.55, 0.48, 0.4, w))
    return g, None


def _tworivers(m, w):
    g = VGroup(rect(-1.0, 0.0, 1.0, 0.9, "#D9C27A", w * 0.5), blob([(-0.6, 0.88), (0.5, 0.88), (0.12, 0.22), (-0.12, 0.22)], "#8DBB6A", 0))
    for x, y in ((-0.2, 0.7), (0.05, 0.72), (-0.08, 0.55), (0.15, 0.55), (-0.02, 0.4)):
        g.add(rect(x - 0.06, y, x + 0.06, y + 0.06, WHEAT_C, w * 0.3), *(line((x - 0.05, y + d), (x + 0.05, y + d), "#B5913A", w * 0.3) for d in (0.02, 0.04)))
    a = [(-0.75, 0.9), (-0.55, 0.65), (-0.35, 0.45), (-0.15, 0.3), (0.0, 0.18), (0.05, 0.0)]
    b = [(0.7, 0.9), (0.5, 0.7), (0.35, 0.5), (0.15, 0.3), (0.0, 0.18)]
    g.add(stroke(a, WATER_D, w * 6), stroke(b, WATER_D, w * 5), stroke(a, WATER, w * 4), stroke(b, WATER, w * 3),
          *(live(stroke([(x, y), (x + 0.03, y - 0.03)], "#EAF4FA", w * 0.6), "steam") for x, y in ((-0.6, 0.72), (-0.3, 0.42), (0.45, 0.65), (0.22, 0.38))),
          *(stroke([(sx, sy), (ex, ey)], WATER, w * 0.9) for sx, sy, ex, ey in ((-0.3, 0.4, -0.1, 0.5), (0.3, 0.45, 0.1, 0.6), (-0.45, 0.55, -0.25, 0.68))),
          *(VGroup(rect(x - 0.035, y, x + 0.035, y + 0.045, "#C9A27A", w * 0.4)) for x, y in ((-0.12, 0.6), (0.08, 0.48), (0.02, 0.3), (0.12, 0.66))),
          VGroup(rect(-0.05, 0.25, 0.08, 0.32, "#B5873A", w * 0.4), poly([(-0.06, 0.32), (0.015, 0.36), (0.09, 0.32)], "#9A6E30", w * 0.4)),
          *(VGroup(stroke([(x, y), (x + 0.02, y + 0.08)], WOOD, w), *(tube([(x + 0.02, y + 0.08), (x + 0.02 + d, y + 0.1)], [0.02, 0.003], "#5E8A3E", w * 0.3) for d in (-0.04, 0.04)))
            for x, y in ((-0.45, 0.72), (0.3, 0.75), (0.1, 0.18))))
    return g, None


def _floodplain(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.5, 0.85, w), poly([(-1.0, 0.5), (-0.5, 0.6), (0.0, 0.55), (0.6, 0.62), (1.0, 0.55), (1.0, 0.5)], "#C9B06A", w * 0.4),
               poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.52), (-1.0, 0.52)], "#D9C27A", w * 0.5),
               poly([(-1.0, 0.1), (1.0, 0.1), (1.0, 0.4), (-1.0, 0.4)], "#5E4A32", 0, op=0.55),
               poly([(-1.0, 0.19), (1.0, 0.19), (1.0, 0.31), (-1.0, 0.31)], WATER, w * 0.6),
               *(live(stroke([(x, y), (x + 0.05, y + 0.012), (x + 0.1, y)], "#EAF4FA", w * 0.7), "steam") for x, y in ((-0.7, 0.24), (-0.1, 0.26), (0.5, 0.23))))
    g.add(*(VGroup(stroke([(x, 0.32), (x, 0.4)], "#5E8A3E", w * 0.8), stroke([(x, 0.37), (x + 0.02, 0.4)], "#5E8A3E", w * 0.5)) for x in np.linspace(-0.95, 0.95, 22)),
          *(VGroup(stroke([(x, 0.08), (x, 0.17)], "#5E8A3E", w * 0.8), stroke([(x, 0.14), (x - 0.02, 0.17)], "#5E8A3E", w * 0.5)) for x in np.linspace(-0.9, 0.9, 20)),
          *(VGroup(stroke([(x, 0.52), (x + 0.03, 0.66)], WOOD, w * 1.2), *(tube([(x + 0.03, 0.66), (x + 0.03 + d, 0.69)], [0.03, 0.004], "#5E8A3E", w * 0.3) for d in (-0.06, 0.0, 0.06)))
            for x in (-0.6, 0.4)),
          letters("SILT", 0.75, 0.135, 0.035, "#F3E1C8"), sky_cloud(-0.3, 0.75, 0.5, w))
    return g, None


def _flood(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.3, 1.1, w, "#B5C2CC"),
               *(blob([(x - 0.3, 0.95), (x - 0.15, 1.05), (x + 0.1, 1.06), (x + 0.3, 0.97)], "#8E98A2", w * 0.5) for x in (-0.5, 0.35)))
    for x, h in ((-0.55, 0.45), (0.0, 0.55), (0.5, 0.4)):
        g.add(rect(x - 0.18, 0.0, x + 0.18, h, "#F3E1C8", w), poly([(x - 0.22, h), (x, h + 0.2), (x + 0.22, h)], "#B5643C", w),
              *(line((x - 0.2 + 0.03 * k, h + 0.02 + 0.03 * k), (x + 0.2 - 0.03 * k, h + 0.02 + 0.03 * k), "#8E4A2A", w * 0.4) for k in range(4)),
              rect(x - 0.06, h - 0.18, x + 0.06, h - 0.08, "#9FC5DA", w * 0.5), line((x, h - 0.18), (x, h - 0.08), "#F7F5F0", w * 0.5))
    g.add(rect(-1.0, 0.0, 1.0, 0.3, "#6E8AA8", w * 0.6).set_opacity(0.92),
          *(live(stroke([(x, 0.28), (x + 0.07, 0.31), (x + 0.14, 0.28)], "#DDEEF6", w), "steam") for x in np.linspace(-0.9, 0.75, 8)),
          *(live(stroke([(x, y), (x + 0.06, y + 0.01)], "#DDEEF6", w * 0.6), "steam") for x, y in ((-0.7, 0.15), (-0.2, 0.1), (0.35, 0.18), (0.8, 0.08))),
          VGroup(rect(0.66, 0.26, 0.92, 0.31, WOOD, w * 0.6), line((0.7, 0.31), (0.7, 0.36), WOOD_D, w)),
          VGroup(stroke([(-0.85, 0.1), (-0.83, 0.35), (-0.9, 0.48)], WOOD_D, w * 1.6), circ(-0.85, 0.5, 0.1, "#5E8A3E", w * 0.5)),
          *(live(line((x, 0.95), (x - 0.04, 0.8), "#7FA8C9", w * 0.8), "steam") for x in np.linspace(-0.85, 0.85, 12)))
    return g, None


def _drought(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.3, 1.05, w, "#F4D9A6"), poly([(-1.0, 0.0), (1.0, 0.0), (1.0, 0.32), (-1.0, 0.32)], "#C9A06A", w * 0.6),
               poly([(-1.0, 0.25), (1.0, 0.25), (1.0, 0.32), (-1.0, 0.32)], "#D9B47A", 0))
    cracks = (((-0.9, 0.05), (-0.75, 0.12), (-0.6, 0.15), (-0.65, 0.27)), ((-0.6, 0.15), (-0.35, 0.12), (-0.2, 0.22)), ((-0.35, 0.12), (-0.3, 0.02)),
              ((0.0, 0.03), (0.1, 0.15), (0.3, 0.12), (0.5, 0.25)), ((0.1, 0.15), (0.05, 0.27)), ((0.3, 0.12), (0.45, 0.04), (0.7, 0.1), (0.85, 0.22)),
              ((-0.2, 0.22), (-0.05, 0.28)), ((0.7, 0.1), (0.75, 0.02)), ((-0.75, 0.12), (-0.85, 0.2)))
    for pts in cracks:
        g.add(*(line(pts[i], pts[i + 1], "#7A5A3A", w * 1.0) for i in range(len(pts) - 1)))
    g.add(shadow_under(0.4, 0.85, 0.31, w), stroke([(0.6, 0.3), (0.62, 0.6), (0.5, 0.78)], "#6B4A2F", w * 2.6), stroke([(0.62, 0.55), (0.8, 0.72)], "#6B4A2F", w * 1.8),
          stroke([(0.56, 0.7), (0.44, 0.68)], "#6B4A2F", w), stroke([(0.72, 0.64), (0.76, 0.58)], "#6B4A2F", w * 0.8),
          circ(-0.6, 0.85, 0.14, "#F2A93B", w * 0.6), circ(-0.6, 0.85, 0.1, "#F7C35A", 0),
          *(live(line((-0.6 + 0.17 * math.cos(a), 0.85 + 0.17 * math.sin(a)), (-0.6 + 0.24 * math.cos(a), 0.85 + 0.24 * math.sin(a)), "#F2A93B", w * 1.1), "puff")
            for a in np.linspace(0, 2 * math.pi, 11)[:-1]),
          *(live(stroke([(x, 0.34), (x + 0.02, 0.4), (x - 0.01, 0.46)], "#E8C88A", w * 0.6), "steam") for x in (-0.3, 0.0, 0.25)),
          VGroup(ell(-0.25, 0.28, 0.12, 0.04, "#E8E0CC", w * 0.4), stroke([(-0.28, 0.3), (-0.3, 0.33)], "#E8E0CC", w)),
          *(stroke([(x, 0.3), (x + 0.03, 0.36)], "#A89A5A", w * 0.6) for x in (-0.85, -0.82, 0.2)))
    return g, None


def _lagoon(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.25, 0.8, w, "#D6ECF4"), rect(-1.0, 0.0, 1.0, 0.27, WATER_D, w * 0.5),
               *(live(stroke([(x, 0.06 + 0.05 * (i % 3)), (x + 0.06, 0.07 + 0.05 * (i % 3)), (x + 0.12, 0.06 + 0.05 * (i % 3))], "#DDEEF6", w * 0.6), "steam") for i, x in enumerate(np.linspace(-0.95, 0.8, 8))),
               ell(0.0, 0.22, 1.45, 0.32, SAND, w), ell(0.0, 0.22, 1.05, 0.2, "#7FD1C9", w * 0.6), ell(0.05, 0.22, 0.6, 0.1, "#A6E2DA", 0),
               glints(((-0.2, 0.24, 0.1), (0.15, 0.2, 0.08)), w))
    for x in (-0.6, 0.55):
        g.add(shadow_under(x - 0.1, x + 0.15, 0.25, w), stroke([(x, 0.25), (x + 0.03, 0.38), (x + 0.07, 0.5)], WOOD, w * 2),
              *(line((x + 0.015 * k, 0.27 + 0.05 * k), (x + 0.03 + 0.015 * k, 0.27 + 0.05 * k), WOOD_D, w * 0.5) for k in range(5)),
              *(tube([(x + 0.07, 0.5), (x + 0.07 + 0.16 * math.cos(a), 0.5 + 0.09 * math.sin(a) - 0.03)], [0.045, 0.005], "#5E8A3E", w * 0.4) for a in (0.2, 0.9, 1.6, 2.4, 3.1, 3.8)),
              *(circ(x + 0.06 + d, 0.47, 0.018, "#8C6A42", w * 0.3) for d in (-0.015, 0.015)))
    g.add(sky_cloud(0.0, 0.66, 0.6, w), birds(((0.3, 0.6, 0.8),), w))
    return g, None


def _watercycle(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.0, 1.05, w, "#E4F0F6"), rect(-1.0, 0.0, 0.05, 0.14, WATER, w * 0.5),
               *(stroke([(x, 0.1), (x + 0.05, 0.115), (x + 0.1, 0.1)], "#DDEEF6", w * 0.6) for x in (-0.9, -0.6, -0.3)),
               poly([(0.0, 0.0), (0.3, 0.48), (0.48, 0.3), (0.62, 0.52), (0.82, 0.3), (1.0, 0.0)], "#8E8FA0", w),
               poly([(0.24, 0.39), (0.3, 0.48), (0.36, 0.39)], SNOW, 0), poly([(0.57, 0.44), (0.62, 0.52), (0.67, 0.44)], SNOW, 0),
               blob([(0.0, 0.0), (0.0, 0.05), (0.3, 0.1), (0.6, 0.08), (1.0, 0.05), (1.0, 0.0)], "#7FA85A", w * 0.4),
               circ(-0.75, 0.82, 0.11, "#F2C14E", w * 0.6), *(line((-0.75 + 0.14 * math.cos(a), 0.82 + 0.14 * math.sin(a)), (-0.75 + 0.19 * math.cos(a), 0.82 + 0.19 * math.sin(a)), "#F2C14E", w)
                                                           for a in np.linspace(0, 2 * math.pi, 9)[:-1]))
    g.add(*(VGroup(blob([(x - 0.22, 0.76), (x - 0.14, 0.86), (x, 0.9), (x + 0.14, 0.86), (x + 0.22, 0.76)], c, w)) for x, c in ((-0.15, "#FBFBF8"), (0.48, "#C9CED6"))),
          *(live(line((x, 0.72), (x - 0.03, 0.56), WATER, w), "steam") for x in np.linspace(0.32, 0.64, 5)),
          *(live(stroke([(x, 0.16), (x + 0.02, 0.3), (x - 0.01, 0.44)], "#9FC5DA", w * 0.8), "steam") for x in (-0.7, -0.5, -0.3)),
          stroke([(0.8, 0.3), (0.6, 0.22), (0.3, 0.1), (0.05, 0.07)], WATER_D, w * 1.8),
          stroke([(-0.42, 0.52), (-0.32, 0.68), (-0.22, 0.74)], "#3A3631", w * 0.9), poly([(-0.24, 0.77), (-0.18, 0.73), (-0.25, 0.7)], "#3A3631", 0),
          stroke([(0.1, 0.86), (0.22, 0.92), (0.28, 0.9)], "#3A3631", w * 0.9), poly([(0.26, 0.93), (0.31, 0.89), (0.25, 0.87)], "#3A3631", 0),
          stroke([(0.3, 0.02), (0.1, 0.02)], "#3A3631", w * 0.9), poly([(0.1, 0.045), (0.05, 0.02), (0.1, -0.005)], "#3A3631", 0),
          *(letters(t, x, y, 0.028, "#3A3631") for t, x, y in (("EVAPORATION", -0.5, 0.36), ("CONDENSATION", 0.15, 1.0), ("RAIN", 0.68, 0.62), ("RUN-OFF", 0.45, 0.16))))
    return g, None


def _soillayers(m, w):
    g = VGroup()
    layers = ((0.08, "#5E8A3E", ""), (0.18, "#6B4E2E", "TOPSOIL"), (0.18, "#9A7A52", "SUBSOIL"), (0.2, "#B5AD9C", "ROCK"))
    top = 0.64
    for h, c, lab in layers:
        y0 = top - h
        g.add(rect(-0.6, y0, 0.6, top, c, w * 0.6))
        if lab == "TOPSOIL":
            g.add(*(circ(x, y, 0.006, tint(c, 0.3), 0) for x, y in ((-0.5, top - 0.05), (-0.2, top - 0.12), (0.1, top - 0.07), (0.3, top - 0.14), (-0.35, top - 0.15))),
                  stroke([(-0.35, top - 0.08), (-0.3, top - 0.1), (-0.25, top - 0.08), (-0.2, top - 0.11)], "#D88A9A", w * 1.4))
        if lab == "SUBSOIL":
            g.add(*(ell(x, y, 0.06, 0.035, tint(c, -0.2), w * 0.3) for x, y in ((-0.4, top - 0.1), (0.05, top - 0.06), (0.25, top - 0.13))))
        if lab == "ROCK":
            g.add(*(line((x, y0 + 0.02), (x + 0.1, top - 0.02), tint(c, -0.25), w * 0.5) for x in (-0.5, -0.1, 0.3)),
                  *(line((x, y0 + 0.1), (x + 0.15, y0 + 0.09), tint(c, -0.25), w * 0.5) for x in (-0.3, 0.1)))
        if lab:
            g.add(letters(lab, 0.38, (y0 + top) / 2, 0.04, "#F7F5F0"))
        top = y0
    g.add(*(stroke([(x, 0.56), (x + 0.02, 0.48), (x - 0.01, 0.4)], "#F3E1C8", w * 0.6) for x in (-0.45, -0.15, 0.15)),
          tufts(np.linspace(-0.55, 0.55, 10), 0.64, w), VGroup(stroke([(0.45, 0.64), (0.45, 0.82)], "#5E8A3E", w), circ(0.45, 0.84, 0.03, "#F2C14E", w * 0.3)))
    return g, None


def _groundwater(m, w):
    g, _ = _soillayers(m, w)
    g.add(rect(-0.6, 0.06, 0.6, 0.2, WATER, 0).set_opacity(0.75), stroke([(-0.6, 0.2), (0.6, 0.2)], WATER_D, w * 1.4),
          *(live(stroke([(x, 0.13), (x + 0.04, 0.14), (x + 0.08, 0.13)], "#DDEEF6", w * 0.5), "steam") for x in (-0.5, -0.2, 0.25)),
          letters("WATER TABLE", -0.3, 0.13, 0.035, "#F7F5F0"),
          rect(-0.01, 0.12, 0.05, 0.7, "#9AA3A9", w * 0.6), rect(0.0, 0.12, 0.04, 0.2, WATER, 0),
          VGroup(rect(-0.04, 0.7, 0.08, 0.84, "#3E7CB1", w * 0.6), line((0.08, 0.8), (0.18, 0.8), "#3E7CB1", w), line((-0.04, 0.82), (-0.14, 0.9), "#3A3631", w * 1.2),
                 live(VGroup(*(ell(0.18, y, 0.018, 0.035, WATER, w * 0.3) for y in (0.74, 0.68))), "steam")),
          *(live(VGroup(stroke([(x, 0.56), (x, 0.24)], "#9FC5DA", w * 0.6), poly([(x - 0.015, 0.26), (x, 0.22), (x + 0.015, 0.26)], "#9FC5DA", 0)), "steam") for x in (-0.45, 0.35)))
    return g, None


def _ghats(m, w):
    g = VGroup(sky_band(-1.0, 1.0, 0.46, 1.1, w, "#F4DCC0"), circ(0.75, 0.95, 0.08, "#F2A93B", w * 0.4),
               rect(-1.0, 0.0, 1.0, 0.16, WATER, w * 0.5), glints(((-0.6, 0.06, 0.12), (0.1, 0.1, 0.1), (0.6, 0.05, 0.08)), w, "#F7D9A0"))
    for i in range(5):
        y = 0.16 + i * 0.06
        g.add(rect(-1.0, y, 1.0, y + 0.06, tint("#D9B98A", 0.05 * (i % 2)), w * 0.5), line((-1.0, y + 0.058), (1.0, y + 0.058), "#B5955E", w * 0.4))
    for x, h in ((-0.7, 0.4), (-0.25, 0.55), (0.3, 0.45), (0.75, 0.35)):
        g.add(rect(x - 0.15, 0.46, x + 0.15, 0.46 + h, "#E8C9A0", w), *(line((x - 0.15, 0.46 + y), (x + 0.15, 0.46 + y), "#D4B086", w * 0.4) for y in np.arange(0.06, h, 0.08)),
              *(blob(zoo.P._arc(x + d, 0.46 + h * 0.4, 0.04, 0, 180, 6) + [(x + d + 0.04, 0.46 + h * 0.2)], "#6B4A2F", w * 0.4) for d in (-0.07, 0.07)),
              rect(x - 0.16, 0.46 + h - 0.03, x + 0.16, 0.46 + h, "#C9A880", w * 0.4),
              poly([(x - 0.17, 0.46 + h), (x, 0.56 + h), (x + 0.17, 0.46 + h)], "#C2552B", w * 0.7), line((x, 0.56 + h), (x, 0.63 + h), "#6E747A", w * 0.6),
              live(poly([(x, 0.63 + h), (x + 0.06, 0.61 + h), (x, 0.59 + h)], "#E07B39", w * 0.3), "flag"))
    g.add(*(VGroup(line((x, 0.28), (x, 0.4), WOOD_D, w), blob([(x - 0.12, 0.4), (x, 0.47), (x + 0.12, 0.4)], c, w * 0.6)) for x, c in ((-0.5, "#E07B39"), (0.45, "#2E7D74"))),
          VGroup(blob([(-0.25, 0.06), (-0.2, 0.01), (0.2, 0.01), (0.25, 0.06)], WOOD, w * 0.6), poly([(-0.12, 0.06), (0.12, 0.06), (0.1, 0.12), (-0.1, 0.12)], "#F2C14E", w * 0.4)),
          *(live(VGroup(circ(x, 0.17, 0.012, "#F2A93B", 0)), "flame") for x in (-0.35, -0.3, 0.15)))
    return g, None


def _waterwheel(m, w):
    g = VGroup(rect(-0.8, 0.0, 0.8, 0.14, WATER, w * 0.5), *(live(stroke([(x, 0.07), (x + 0.06, 0.08), (x + 0.12, 0.07)], "#DDEEF6", w * 0.6), "steam") for x in (-0.7, -0.3, 0.4)),
               rect(-0.55, 0.0, -0.45, 0.75, WOOD_D, w), rect(0.45, 0.0, 0.55, 0.75, WOOD_D, w),
               *(line((x, 0.1), (x, 0.7), "#5A3E28", w * 0.4) for x in (-0.5, 0.5)))
    wheel = VGroup(Circle(radius=0.4, stroke_color=WOOD, stroke_width=w * 3.4).move_to([0.0, 0.45, 0]),
                   Circle(radius=0.34, stroke_color=WOOD_D, stroke_width=w * 0.8).move_to([0.0, 0.45, 0]),
                   *(line((0.0, 0.45), (0.4 * math.cos(a), 0.45 + 0.4 * math.sin(a)), WOOD, w * 1.2) for a in np.linspace(0, 2 * math.pi, 9)[:-1]),
                   *(VGroup(rect(0.4 * math.cos(a) - 0.045, 0.45 + 0.4 * math.sin(a) - 0.04, 0.4 * math.cos(a) + 0.045, 0.45 + 0.4 * math.sin(a) + 0.04, CLAY, w * 0.5),
                            rect(0.4 * math.cos(a) - 0.035, 0.45 + 0.4 * math.sin(a) + 0.02, 0.4 * math.cos(a) + 0.035, 0.45 + 0.4 * math.sin(a) + 0.035, WATER, 0))
                     for a in np.linspace(0, 2 * math.pi, 9)[:-1]))
    g.add(live(wheel, "spin", (0.0, 0.45)), circ(0.0, 0.45, 0.05, "#3A3631", w * 0.6), line((-0.5, 0.75), (0.5, 0.75), WOOD_D, w * 1.6),
          rect(0.5, 0.58, 0.95, 0.64, "#B5875E", w * 0.6), live(stroke([(0.38, 0.62), (0.6, 0.62), (0.95, 0.62)], WATER, w * 2.6), "steam"),
          live(VGroup(*(ell(0.42, y, 0.02, 0.04, WATER, w * 0.3) for y in (0.55, 0.48))), "steam"),
          tufts(np.linspace(-0.78, -0.6, 3), 0.14, w), tufts(np.linspace(0.6, 0.78, 3), 0.14, w))
    return g, None


SHELF = {name[1:]: fn for name, fn in globals().items() if name.startswith("_") and callable(fn) and name[1:].isalpha()
         and name not in ("_annotations",)}
import shelf as _index  # noqa: E402
from shelf import ALIASES  # noqa: E402  (the other names things go by: shelf.py)
NAMES = tuple(sorted(SHELF))
if set(SHELF) != set(_index.NAMES):          # every drawn thing in the index, and nothing there undrawn
    print(f"props: shelf.py and the drawings differ: {sorted(set(SHELF) ^ set(_index.NAMES))}", file=sys.stderr)


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
        # what moves on its own, its points kept in the thing's own frame; its wheels
        import zlib
        self.phase = (zlib.crc32(self.name.encode()) % 100) / 16.0
        self.lives = []
        for x in g.get_family():
            tag = getattr(x, "live", None)
            if tag:
                kind, anchor = tag
                parts = [(y, y.points[:, :2].copy()) for y in x.family_members_with_points()]
                if not parts:
                    continue
                allp = np.vstack([b for _, b in parts])
                if anchor is None:
                    anchor = ((allp[:, 0].min() + allp[:, 0].max()) / 2, allp[:, 1].min()) if kind in ("flame", "steam") \
                        else (allp[:, 0].min(), allp[:, 0].max() - allp[:, 0].min()) if kind == "flag" \
                        else ((allp[:, 0].min() + allp[:, 0].max()) / 2, (allp[:, 1].min() + allp[:, 1].max()) / 2)
                self.lives.append((kind, np.array(anchor, dtype=float), parts))
        self.wheels = [x for x in g.get_family() if getattr(x, "wheel", False)]
        self.cranks = [x for x in g.get_family() if getattr(x, "crank", False)]
        self.rolled = 0.0
        self.f = 1.0
        if lid is not None:
            self.lid, hinge, self.how, self.reach = lid
            self.hinge = np.array(hinge, dtype=float)
            self.lid_base = [(x, x.points[:, :2].copy()) for x in self.lid.family_members_with_points()]
        if mods.get("open"):
            self.set_open(1.0)

    # -- its own frame, and things that move by themselves -----------------------------------------------------------
    def _frame(self):
        o, xr, yr = (d.get_center() for d in self._ref)
        return o, (xr - o) / 0.1, (yr - o) / 0.1

    def alive(self, t: float) -> None:
        """Flames flicker, flags wave, sails turn, smoke and steam drift (at time t, seconds)."""
        if not self.lives:
            return
        o, ex, ey = self._frame()
        t = t + self.phase
        for kind, anc, parts in self.lives:
            for y, base in parts:
                q = base.copy()
                if kind == "flame":
                    sy = 1 + 0.13 * math.sin(9.3 * t) + 0.06 * math.sin(23.0 * t + 1.0)
                    sx = 1 - 0.5 * (sy - 1) + 0.03 * math.sin(14.0 * t)
                    q = anc + (q - anc) * np.array([sx, sy])
                    q[:, 0] += 0.01 * math.sin(7.0 * t) * (q[:, 1] - anc[1]) / 0.05
                elif kind == "flag":
                    x0, length = anc
                    d = np.clip((q[:, 0] - x0) / max(length, 1e-3), 0.0, 1.0)
                    q[:, 1] += 0.045 * np.sin(6.5 * t - 9.0 * (q[:, 0] - x0)) * d
                elif kind in ("spin", "tick"):
                    a = (-1.1 if kind == "spin" else -0.35) * t
                    ca, sa = math.cos(a), math.sin(a)
                    q = anc + (q - anc) @ np.array([[ca, sa], [-sa, ca]])
                elif kind == "puff":
                    k = 1 + 0.12 * math.sin(2.2 * t + anc[0] * 20)
                    q = anc + (q - anc) * k
                    q[:, 1] += 0.02 * math.sin(1.6 * t + anc[0] * 10)
                elif kind == "steam":
                    q[:, 0] += 0.012 * np.sin(5.0 * t + 40.0 * q[:, 1])
                y.points = o + np.outer(q[:, 0], ex) + np.outer(q[:, 1], ey)

    # -- vehicles ------------------------------------------------------------------------------------------------
    def facing(self) -> float:
        return self.f

    def feet(self) -> np.ndarray:
        return self.get_bottom()

    def turn(self) -> None:
        """Turned round to go the other way (its own frame turns with it)."""
        self.stretch(-1, 0, about_point=self.get_center())
        self.f = -self.f

    def roll(self, d: float) -> None:
        """Its wheels turned by a distance travelled."""
        self.rolled += d
        r0 = max(self.wheels[0].width / 2, 1e-3) if self.wheels else 1.0
        for wh in self.wheels:
            r = max(wh.width / 2, 1e-3)
            wh.rotate(-self.f * d / r, about_point=wh.get_center())
        for cr in self.cranks:                  # pedals: slower than the wheels (geared)
            cr.rotate(-self.f * d / r0 * 0.55, about_point=cr.submobjects[0].get_center())

    def saddle(self) -> np.ndarray:
        """Where a rider sits (a vehicle's seat; inside one that has no open seat)."""
        import handle
        o, ex, ey = self._frame()
        x, y = handle.VEHICLE_SEATS.get(self.name, (0.0, self.height / max(np.linalg.norm(ey), 1e-6) * 0.4))
        return o + x * ex + y * ey

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
