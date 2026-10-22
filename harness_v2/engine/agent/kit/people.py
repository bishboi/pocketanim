"""Illustrated people, flat and simple (Vox's explainer figures): a bust with hair, hat, beard, glasses and clothes
chosen, a plain silhouette for someone with no known likeness, and small standing figures for crowds.

    person(hat="official", beard="long", clothes="robe")       # a Han-dynasty official (Sima Qian)
    person(hat="scholar", beard="long", clothes="robe", skin="#F2D3B3")   # Matteo Ricci in a scholar's cap
    person(hair="short", beard="mustache", glasses=True, clothes="suit")  # a Meiji-era scholar
    person(silhouette=True)                                     # no likeness known
    crowd(12)                                                   # a row of small figures

Every part is named (head, hair, hat, beard, glasses, body), so a figure can be recoloured or animated in parts.
"""

from __future__ import annotations

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, PI, RIGHT, UP, Annulus, AnnularSector, Arc, ArcPolygon, Circle, Dot, Ellipse,
                   Line, Polygon, Rectangle, RoundedRectangle, Sector, VGroup, VMobject)

from .base import Piece
from .look import L

SKINS = {"light": "#F2D3B3", "medium": "#D9A77C", "tan": "#C68B59", "brown": "#8D5A3B", "dark": "#5E3B26"}
HAIR = {"black": "#1E1A18", "brown": "#5B3A24", "grey": "#9A948C", "white": "#E6E2DA", "red": "#9E4A2A"}


class Person(Piece):
    enter_kind = "shape"


def _blob(points, color, opacity=1.0):
    v = VMobject(stroke_width=0, fill_color=color, fill_opacity=opacity)
    v.set_points_smoothly([np.array([x, y, 0]) for x, y in points] + [np.array([*points[0], 0])])
    return v


def person(hair: str = "short", hat: str | None = None, beard: str | None = None, glasses: bool = False,
           clothes: str = "suit", skin: str = "medium", hair_color: str = "black", clothes_color: str | None = None,
           silhouette: bool = False, face: bool = True, height: float = 2.6) -> Person:
    """A bust, `height` tall. hair: short, bald, long, topknot, tonsure, side, bun. hat: official (a Chinese
    official's winged cap), scholar (a square black cap), cap (a soft cap), top, bowler, turban, none. beard:
    mustache, goatee, long, full, none. clothes: suit, robe (crossed collar), kimono, cassock, shirt, uniform."""
    look = L()
    skin_c = SKINS.get(skin, skin)
    hair_c = HAIR.get(hair_color, hair_color)
    ink = look.ink if look.name == "blueprint" else "#1B1B1B"
    cloth = clothes_color or {"suit": "#2F3640", "robe": "#7A2E2E", "kimono": "#33415C", "cassock": "#1B1B1B",
                              "shirt": "#E9E3D6", "uniform": "#3E4A2F"}.get(clothes, "#2F3640")
    if silhouette:
        skin_c = hair_c = cloth = look.muted if look.name == "blueprint" else "#3A3530"

    p = Person()
    # body: shoulders as a rounded mound
    body = _blob([(-1.25, -1.3), (-1.18, -0.55), (-0.75, -0.18), (0, -0.08), (0.75, -0.18), (1.18, -0.55),
                  (1.25, -1.3)], cloth)
    neck = Rectangle(width=0.36, height=0.35, stroke_width=0, fill_color=skin_c, fill_opacity=1).move_to(UP * 0.02)
    head = Ellipse(width=0.92, height=1.1, stroke_width=0, fill_color=skin_c, fill_opacity=1).move_to(UP * 0.68)
    ears = VGroup(*(Ellipse(width=0.16, height=0.26, stroke_width=0, fill_color=skin_c, fill_opacity=1)
                    .move_to(head.get_center() + RIGHT * s * 0.46 + DOWN * 0.02) for s in (-1, 1)))
    p.add(body, neck, ears, head)
    p.name_part("body", body)
    p.name_part("head", head)

    collar = VGroup()
    if not silhouette:
        if clothes == "suit":
            shirt = Polygon(LEFT * 0.26 + DOWN * 0.12, RIGHT * 0.26 + DOWN * 0.12, DOWN * 0.75, stroke_width=0,
                            fill_color="#F4F1EA", fill_opacity=1)
            tie = Polygon(UP * -0.14 + LEFT * 0.06, UP * -0.14 + RIGHT * 0.06, DOWN * 0.62 + RIGHT * 0.08,
                          DOWN * 0.72, DOWN * 0.62 + LEFT * 0.08, stroke_width=0, fill_color=look.accent, fill_opacity=1)
            lapels = VGroup(Polygon(LEFT * 0.26 + DOWN * 0.12, LEFT * 0.5 + DOWN * 0.2, DOWN * 0.85 + LEFT * 0.05,
                                    stroke_width=0, fill_color="#20262E", fill_opacity=1),
                            Polygon(RIGHT * 0.26 + DOWN * 0.12, RIGHT * 0.5 + DOWN * 0.2, DOWN * 0.85 + RIGHT * 0.05,
                                    stroke_width=0, fill_color="#20262E", fill_opacity=1))
            collar.add(shirt, tie, lapels)
        elif clothes in ("robe", "kimono"):
            under = "#EDE6D6" if clothes == "robe" else "#D9D2C2"
            collar.add(Polygon(LEFT * 0.3 + DOWN * 0.1, RIGHT * 0.32 + DOWN * 0.1, DOWN * 0.9 + RIGHT * 0.35,
                               stroke_width=0, fill_color=under, fill_opacity=1),
                       Line(LEFT * 0.32 + DOWN * 0.1, DOWN * 0.95 + RIGHT * 0.4, stroke_color="#1B1B1B", stroke_width=3),
                       Line(RIGHT * 0.32 + DOWN * 0.1, DOWN * 0.5 + RIGHT * 0.05, stroke_color="#1B1B1B", stroke_width=3))
        elif clothes == "cassock":
            collar.add(Rectangle(width=0.4, height=0.1, stroke_width=0, fill_color="#F4F1EA", fill_opacity=1)
                       .move_to(DOWN * 0.13))
        elif clothes == "shirt":
            collar.add(Polygon(LEFT * 0.3 + DOWN * 0.1, DOWN * 0.38, LEFT * 0.05 + DOWN * 0.1, stroke_width=0,
                               fill_color="#D2CBBE", fill_opacity=1),
                       Polygon(RIGHT * 0.3 + DOWN * 0.1, DOWN * 0.38, RIGHT * 0.05 + DOWN * 0.1, stroke_width=0,
                               fill_color="#D2CBBE", fill_opacity=1))
        elif clothes == "uniform":
            collar.add(*(Dot(DOWN * (0.3 + 0.22 * i), radius=0.04, color="#D9B44A") for i in range(3)))
        p.add(collar)
    p.name_part("collar", collar)

    hc = head.get_center()
    top = head.get_top()
    hair_m = VGroup()
    if hair == "short":
        hair_m.add(_blob([(-0.47, 0.05), (-0.5, 0.35), (-0.3, 0.6), (0, 0.66), (0.3, 0.6), (0.5, 0.35), (0.47, 0.05),
                          (0.35, 0.28), (0, 0.4), (-0.35, 0.28)], hair_c).move_to(hc + UP * 0.33))
    elif hair == "side":
        hair_m.add(_blob([(-0.48, 0.0), (-0.5, 0.36), (-0.25, 0.62), (0.15, 0.66), (0.48, 0.45), (0.5, 0.05),
                          (0.3, 0.3), (-0.05, 0.42), (-0.3, 0.2)], hair_c).move_to(hc + UP * 0.33))
    elif hair == "long":
        hair_m.add(_blob([(-0.5, -0.65), (-0.56, 0.2), (-0.35, 0.6), (0, 0.68), (0.35, 0.6), (0.56, 0.2),
                          (0.5, -0.65), (0.38, -0.2), (0.4, 0.25), (0, 0.38), (-0.4, 0.25), (-0.38, -0.2)], hair_c)
                   .move_to(hc + UP * 0.1))
    elif hair == "topknot":
        hair_m.add(_blob([(-0.47, 0.05), (-0.5, 0.35), (-0.3, 0.6), (0, 0.66), (0.3, 0.6), (0.5, 0.35), (0.47, 0.05),
                          (0.3, 0.32), (0, 0.42), (-0.3, 0.32)], hair_c).move_to(hc + UP * 0.33),
                   Circle(radius=0.17, stroke_width=0, fill_color=hair_c, fill_opacity=1).move_to(top + UP * 0.12))
    elif hair == "bun":
        hair_m.add(_blob([(-0.47, 0.05), (-0.5, 0.35), (-0.3, 0.6), (0, 0.66), (0.3, 0.6), (0.5, 0.35), (0.47, 0.05),
                          (0.3, 0.32), (0, 0.42), (-0.3, 0.32)], hair_c).move_to(hc + UP * 0.33),
                   Circle(radius=0.2, stroke_width=0, fill_color=hair_c, fill_opacity=1).move_to(hc + UP * 0.45 + RIGHT * 0.42))
    elif hair == "tonsure":
        hair_m.add(AnnularSector(inner_radius=0.0, outer_radius=0.52, angle=PI * 0.9, start_angle=PI * 0.05,
                                 fill_color=hair_c, fill_opacity=1, stroke_width=0).stretch(0.55, 1).move_to(hc + UP * 0.3),
                   Ellipse(width=0.42, height=0.14, stroke_width=0, fill_color=skin_c, fill_opacity=1).move_to(top + DOWN * 0.08))
    p.add(hair_m)
    p.name_part("hair", hair_m)

    feat = VGroup()
    if face and not silhouette:
        eye_y = hc[1] + 0.02
        for s in (-1, 1):
            feat.add(Dot([hc[0] + s * 0.18, eye_y, 0], radius=0.045, color="#1B1B1B"))
            feat.add(Line([hc[0] + s * 0.1, eye_y + 0.13, 0], [hc[0] + s * 0.27, eye_y + 0.15, 0],
                          stroke_color=hair_c if hair != "bald" else "#3A2E26", stroke_width=4))
        feat.add(Arc(radius=0.1, start_angle=-PI * 0.8, angle=PI * 0.6, stroke_color="#7A4E3A", stroke_width=3)
                 .move_to(hc + DOWN * 0.27))
    p.add(feat)
    p.name_part("face", feat)

    beard_m = VGroup()
    bc = hair_c if not silhouette else skin_c
    if beard == "mustache":
        beard_m.add(_blob([(-0.2, 0), (-0.05, 0.06), (0, 0.03), (0.05, 0.06), (0.2, 0), (0.05, -0.04), (-0.05, -0.04)],
                          bc).move_to(hc + DOWN * 0.18))
    elif beard == "goatee":
        beard_m.add(_blob([(-0.12, 0), (0.12, 0), (0.08, -0.22), (0, -0.28), (-0.08, -0.22)], bc).move_to(hc + DOWN * 0.42))
    elif beard == "long":
        beard_m.add(_blob([(-0.3, 0.05), (-0.15, 0.1), (0, 0.08), (0.15, 0.1), (0.3, 0.05), (0.18, -0.45), (0, -0.75),
                           (-0.18, -0.45)], bc).move_to(hc + DOWN * 0.55),
                    _blob([(-0.22, 0), (0, 0.05), (0.22, 0), (0, -0.05)], bc).move_to(hc + DOWN * 0.17))
    elif beard == "full":
        beard_m.add(_blob([(-0.47, 0.15), (-0.4, -0.2), (-0.2, -0.45), (0, -0.5), (0.2, -0.45), (0.4, -0.2),
                           (0.47, 0.15), (0.25, -0.05), (0, -0.1), (-0.25, -0.05)], bc).move_to(hc + DOWN * 0.38))
    p.add(beard_m)
    p.name_part("beard", beard_m)

    glass = VGroup()
    if glasses and not silhouette:
        for s in (-1, 1):
            glass.add(Circle(radius=0.13, stroke_color="#1B1B1B", stroke_width=3).move_to(hc + RIGHT * s * 0.18 + UP * 0.02))
        glass.add(Line(hc + LEFT * 0.05 + UP * 0.04, hc + RIGHT * 0.05 + UP * 0.04, stroke_color="#1B1B1B", stroke_width=3))
    p.add(glass)
    p.name_part("glasses", glass)

    hat_m = VGroup()
    hat_c = "#1B1B1B" if not silhouette else skin_c
    if hat == "official":
        hat_m.add(_blob([(-0.42, 0), (-0.4, 0.3), (-0.2, 0.48), (0.2, 0.48), (0.4, 0.3), (0.42, 0)], hat_c)
                  .move_to(top + DOWN * 0.02),
                  RoundedRectangle(width=1.6, height=0.09, corner_radius=0.04, stroke_width=0, fill_color=hat_c,
                                   fill_opacity=1).move_to(top + DOWN * 0.06))
    elif hat == "scholar":
        hat_m.add(Polygon(LEFT * 0.48, RIGHT * 0.48, RIGHT * 0.44 + UP * 0.5, LEFT * 0.44 + UP * 0.5, stroke_width=0,
                          fill_color=hat_c, fill_opacity=1).move_to(top + UP * 0.12))
    elif hat == "cap":
        hat_m.add(_blob([(-0.5, 0), (-0.45, 0.3), (-0.1, 0.5), (0.4, 0.42), (0.62, 0.15), (0.5, 0)],
                        "#A23B2D" if not silhouette else skin_c).move_to(top + UP * 0.02))
    elif hat == "top":
        hat_m.add(Rectangle(width=0.62, height=0.7, stroke_width=0, fill_color=hat_c, fill_opacity=1).move_to(top + UP * 0.32),
                  Rectangle(width=1.0, height=0.08, stroke_width=0, fill_color=hat_c, fill_opacity=1).move_to(top + DOWN * 0.02))
    elif hat == "bowler":
        hat_m.add(Sector(radius=0.4, angle=PI, fill_color=hat_c, fill_opacity=1, stroke_width=0).move_to(top + UP * 0.14),
                  Rectangle(width=1.0, height=0.07, stroke_width=0, fill_color=hat_c, fill_opacity=1).move_to(top + DOWN * 0.03))
    elif hat == "turban":
        hat_m.add(_blob([(-0.52, 0), (-0.5, 0.35), (-0.2, 0.55), (0.25, 0.55), (0.5, 0.35), (0.52, 0)],
                        "#E3B341" if not silhouette else skin_c).move_to(top + UP * 0.08))
    p.add(hat_m)
    p.name_part("hat", hat_m)

    if look.name == "blueprint" and not silhouette:
        for m in p.get_family():
            if isinstance(m, VMobject) and m.get_fill_opacity() > 0:
                m.set_stroke(look.ink, width=1.6, opacity=0.9)
    p.scale_to_fit_height(height)
    return p


def figure(color: str | None = None, height: float = 1.0) -> Piece:
    """A small standing figure (a crowd's member, a "people" icon)."""
    look = L()
    c = color or look.ink
    head = Circle(radius=0.16, stroke_width=0, fill_color=c, fill_opacity=1).move_to(UP * 0.82)
    body = RoundedRectangle(width=0.46, height=0.62, corner_radius=0.2, stroke_width=0, fill_color=c, fill_opacity=1)
    body.move_to(UP * 0.36)
    legs = VGroup(*(RoundedRectangle(width=0.16, height=0.4, corner_radius=0.07, stroke_width=0, fill_color=c,
                                     fill_opacity=1).move_to(DOWN * 0.08 + RIGHT * s * 0.1) for s in (-1, 1)))
    f = Piece(legs, body, head)
    f.scale_to_fit_height(height)
    return f


def crowd(n: int = 10, colors=None, height: float = 0.9, rows: int = 1, gap: float = 0.12) -> Piece:
    """n small figures in rows, coloured from `colors` (default: ink with every third in the accent)."""
    look = L()
    colors = colors or [look.ink, look.ink, look.accent]
    per_row = int(np.ceil(n / rows))
    g = Piece()
    for i in range(n):
        f = figure(colors[i % len(colors)], height=height)
        g.add(f)
    g.arrange_in_grid(rows=rows, cols=per_row, buff=gap)
    return g
