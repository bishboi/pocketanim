"""Things drawn with the same pen as the people: a ready shelf, so a shot needs no picture searched for or made.

    ent b prop moneybag [color C] [sign ₹] [open] [size H] at X,Y      (it stands on X,Y: its bottom middle there)

Drawn to the people's scale (size 2.6, a person's, by default: a chest beside a king is a chest's size); a bigger
size shows one alone (size 6-10). Those with a lid open and shut as it plays: `open X`, `shut X` (a chest shows its
gold; a letter its flap; a box, a door). Any of them can be carried, given, thrown, moved.

Money, trade: moneybag coins coin goldbars cash gem crown chest piggybank wallet card receipt abacus safe stall scales
Writing, office: book books openbook ledger scroll letter document charter newspaper oldmap quill inkwell seal pencil
                 notebook clipboard folder stamp typewriter briefcase ballotbox
Modern: laptop computer phone oldphone radio tv camera microphone megaphone clock lightbulb battery
Science, industry: flask testtube microscope magnet gear telescope rocket satellite solarpanel windmill factory oilwell
                   printingpress
Home: table desk chair stool throne bench bookshelf lectern bed charpai rug vase broom umbrella ladder rope chain
      padlock key bell goblet hourglass gift balloon kite ball cricketbat trophy medal lattu rangoli
Containers: barrel crate box sack basket pot jar bucket milkcan tiffin
Food: bread apple mango banana coconut wheat bowl thali teacup kulhad fish
Care: medkit pills syringe
Light: candle diya lantern campfire
Arms: sword shield spear bow axe musket cannon bomb helmet
Work: anvil plough wheel charkha
Getting about: cart carriage bicycle rickshaw autorickshaw car bus truck tractor train plane boat ship
Places: house hut tent well tower castle palace temple mosque church school hospital bank shop skyscraper lighthouse
        bridge gate fence signpost flagpole flagindia bunting
Nature: tree palm bush rock mountain cloud sun moon flower lotus cactus mushroom
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


SHELF = {name[1:]: fn for name, fn in globals().items() if name.startswith("_") and callable(fn) and name[1:].isalpha()
         and name not in ("_annotations",)}
ALIASES = {"bag": "moneybag", "purse": "moneybag", "money": "moneybag", "gold": "coins", "treasure": "chest",
           "coinpile": "coins", "notes": "cash", "banknotes": "cash", "jewel": "gem", "diamond": "gem",
           "ruby": "gem", "tome": "book", "paper": "document", "contract": "document", "deed": "charter",
           "decree": "charter", "treaty": "charter", "envelope": "letter", "map": "oldmap", "featherpen": "quill",
           "throne_chair": "throne", "cupboard": "bookshelf", "shelf": "bookshelf", "grain": "sack", "matka": "pot",
           "amphora": "jar", "lamp": "diya", "fire": "campfire", "plow": "plough",
           "spinningwheel": "charkha", "balance": "scales", "timer": "hourglass", "chalice": "goblet", "idea": "lightbulb",
           "press": "printingpress", "door": "gate", "sign": "signpost",
           "flag": "flagpole", "wagon": "cart", "bullockcart": "cart", "cottage": "hut", "home": "house",
           "moneybox": "piggybank", "creditcard": "card", "bill": "receipt", "vault": "safe", "marketstall": "stall",
           "pen": "pencil", "copy": "notebook", "file": "folder", "files": "folder", "mobile": "phone",
           "smartphone": "phone", "telephone": "oldphone", "television": "tv", "mic": "microphone",
           "loudspeaker": "megaphone", "ballot": "ballotbox", "watch": "clock", "magnifyingglass": "magnifier",
           "cup": "trophy", "award": "medal", "beaker": "flask", "chemistry": "flask", "cog": "gear",
           "spaceship": "rocket", "solar": "solarpanel", "mill": "factory", "oil": "oilwell", "loaf": "bread",
           "rice": "bowl", "food": "thali", "chai": "kulhad", "tea": "teacup", "milk": "milkcan",
           "medicine": "pills", "firstaid": "medkit", "injection": "syringe", "vaccine": "syringe", "cycle": "bicycle",
           "bike": "bicycle", "auto": "autorickshaw", "tuktuk": "autorickshaw", "locomotive": "train",
           "aeroplane": "plane", "airplane": "plane", "coach": "carriage", "fortress": "castle", "fort": "castle",
           "mahal": "palace", "mandir": "temple", "masjid": "mosque", "cathedral": "church", "college": "school",
           "store": "shop", "building": "skyscraper", "hill": "mountain", "peak": "mountain", "rose": "flower",
           "lock": "padlock", "present": "gift", "cricket": "cricketbat", "explosive": "bomb", "carpet": "rug",
           "flags": "bunting", "rifle": "musket", "tiranga": "flagindia", "indianflag": "flagindia", "cot": "charpai",
           "top": "lattu", "dabba": "tiffin"}
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
