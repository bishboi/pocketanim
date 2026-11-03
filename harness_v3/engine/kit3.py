"""Still more of the kit's pieces, the shapes an argument or a set of numbers takes (as the second engine's motion
templates drew them), each one `ent` placed freely, its parts brought on by the actions as kit.py's are:

    funnel "VISITORS:1000" "SIGNUPS:300" "BUYERS:40"     narrowing bands, each with its number
    iceberg "WHAT IS SEEN" "BELOW" "BELOW" ...           the tip above the water, the rest named below it
    ranking "China:1400" "India:1380" "USA:330" ...      places in order, medals for the first three, bars to scale
    mindmap "CENTRE" "BRANCH" "BRANCH" ...               a centre and its branches round it
    checklist "ITEM" "ITEM" ... [done N]                 boxes, the first N ticked
    proscons "FOR:a|b|c" "AGAINST:d|e"                   two columns, a plus and a minus on each line
    kpi "LABEL:VALUE:CHANGE" ...                         number cards in a row, an arrow up or down by each change
    beforeafter "BEFORE:words" "AFTER:words"             two cards, the second brighter, an arrow between
    progress 70 "WORDS"                                  a bar filled to a share, its number at the end
    quadrant "X AXIS" "Y AXIS" "TOP LEFT" "TOP RIGHT" "BOTTOM LEFT" "BOTTOM RIGHT"   a two-by-two, its axes named

Each piece's parts come on one after another (`in NAME stagger S`, `in NAME[2]`), and its named parts are places
(`highlight fn.buyers`, `tick cl.eggs`).
"""

from __future__ import annotations

import math

import numpy as np
from manim import DOWN, LEFT, RIGHT, UP, Circle, Line, Polygon, Rectangle, RoundedRectangle, VGroup, VMobject

from look import STROKE, col, label, soft_shadow, text
from kit import PALETTE, Keys, even, halo, key, node, para


def _split(a: str) -> list[str]:
    return [x.replace("_", " ") for x in str(a).split(":")]


def _num(s: str):
    try:
        return float(str(s).replace(",", "").replace("%", "").replace("₹", "").replace("$", "").strip() or "x")
    except ValueError:
        return None


def _card(w: float, h: float, fill="card", r: float = 0.12):
    face = RoundedRectangle(width=w, height=h, corner_radius=r, fill_color=col(fill), fill_opacity=1, stroke_color=col("soft"),
                            stroke_width=1.5)
    return VGroup(soft_shadow(face), face)


def _tick(o, s: float, colour):
    m = VMobject(stroke_color=colour, stroke_width=STROKE * 1.1)
    m.set_points_as_corners([o + np.array([-s * 0.5, 0.0, 0]), o + np.array([-s * 0.15, -s * 0.38, 0]), o + np.array([s * 0.55, s * 0.45, 0])])
    return m


def funnel(args: list[str], mods: dict, c=None) -> VGroup:
    w, h = float(mods.get("w", 6.0)), float(mods.get("h", 4.0))
    n = max(1, len(args))
    g = VGroup()
    g.places = Keys()
    lh = h / n
    for i, a in enumerate(args):
        words = _split(a)
        top, bot = w * (1 - 0.62 * i / n), w * (1 - 0.62 * (i + 1) / n)
        y = h / 2 - lh * (i + 0.5)
        band = Polygon([-top / 2, y + lh / 2 - 0.04, 0], [top / 2, y + lh / 2 - 0.04, 0], [bot / 2, y - lh / 2 + 0.04, 0], [-bot / 2, y - lh / 2 + 0.04, 0],
                       fill_color=col(c or PALETTE[i % len(PALETTE)]), fill_opacity=0.95 - 0.08 * i, stroke_color=col("ink"), stroke_width=1.5)
        name = even(words[0].upper(), min(0.26, lh * 0.3), bold=True, color="card")
        if name.width > bot - 0.3:
            name.scale_to_fit_width(max(0.5, bot - 0.3))
        name.move_to([0, y, 0])
        part = VGroup(band, name)
        if len(words) > 1:
            part.add(text(words[1], 0.34, bold=True, color="ink").move_to([top / 2 + 0.25, y, 0], aligned_edge=LEFT))
        g.add(part)
        g.places[key(words[0])] = part
    return g


def iceberg(args: list[str], mods: dict, c=None) -> VGroup:
    w = float(mods.get("w", 7.0))
    above, below = (args[0] if args else "WHAT IS SEEN"), args[1:]
    sea = Rectangle(width=w, height=3.1, fill_color=col("sky"), fill_opacity=0.55, stroke_width=0).move_to([0, -1.55, 0])
    line = Line([-w / 2, 0, 0], [w / 2, 0, 0], stroke_color=col("navy"), stroke_width=STROKE * 0.5)
    tip = Polygon([-0.9, 0, 0], [-0.4, 0.9, 0], [0.05, 1.35, 0], [0.45, 0.8, 0], [0.95, 0, 0], fill_color=col("card"), fill_opacity=1,
                  stroke_color=col("ink"), stroke_width=1.8)
    body = Polygon([-0.9, 0, 0], [0.95, 0, 0], [1.9, -1.2, 0], [1.4, -2.6, 0], [-0.2, -3.0, 0], [-1.8, -2.3, 0], [-2.0, -1.0, 0],
                   fill_color=col("sky"), fill_opacity=0.9, stroke_color=col("ink"), stroke_width=1.5)
    g = VGroup(VGroup(sea, line, body, tip))
    g.places = Keys()
    top = even(str(above).replace("_", " ").upper(), 0.28, bold=True).move_to([0.0, 1.75, 0])
    g.add(top)
    g.places[key(above)] = top
    for i, words in enumerate(below):
        t = halo(even(str(words).replace("_", " ").upper(), 0.22, bold=True)).move_to([-0.05 + 0.15 * (i % 2), -0.55 - i * (2.2 / max(1, len(below))), 0])
        g.add(t)
        g.places[key(words)] = t
    return g


def ranking(args: list[str], mods: dict, c=None) -> VGroup:
    w = float(mods.get("w", 7.0))
    rows = [_split(a) for a in args]
    vals = [_num(r[1]) if len(r) > 1 else None for r in rows]
    top = max([v for v in vals if v is not None] or [1])
    g = VGroup()
    g.places = Keys()
    rh = min(0.85, 4.6 / max(1, len(rows)))
    for i, r in enumerate(rows):
        y = (len(rows) - 1) * rh / 2 - i * rh
        medal = ("#F2C14E", "#C9CED2", "#D49A6A")[i] if i < 3 else col("card")
        badge = VGroup(Circle(radius=rh * 0.36, fill_color=medal, fill_opacity=1, stroke_color=col("ink"), stroke_width=1.5),
                       even(str(i + 1), rh * 0.3, bold=True)).move_to([-w / 2 + rh * 0.4, y, 0])
        name = even(r[0].upper(), rh * 0.3, bold=True).move_to([-w / 2 + rh + 0.15, y, 0], aligned_edge=LEFT)
        part = VGroup(badge, name)
        if vals[i] is not None:
            x0 = -w / 2 + 3.2
            bw = max(0.1, (w - 4.2) * vals[i] / top)
            part.add(Rectangle(width=bw, height=rh * 0.5, fill_color=col(c or ("accent" if i == 0 else "soft")), fill_opacity=0.9,
                               stroke_width=0).move_to([x0 + bw / 2, y, 0]),
                     label(r[1], rh * 0.28, "ink").move_to([x0 + bw + 0.15, y, 0], aligned_edge=LEFT))
        g.add(part)
        g.places[key(r[0])] = part
    return g


def mindmap(args: list[str], mods: dict, c=None) -> VGroup:
    centre, branches = (args[0] if args else "IDEA"), args[1:]
    r = float(mods.get("r", 2.6))
    hub = node(centre, 1.1, fill=c or "accent")
    g = VGroup(hub)
    g.places = Keys()
    g.places[key(centre)] = hub
    n = max(1, len(branches))
    for i, b in enumerate(branches):
        a = math.pi / 2 - 2 * math.pi * i / n
        p = np.array([r * 1.35 * math.cos(a), r * 0.85 * math.sin(a), 0])
        card = node(b, 0.75, fill=PALETTE[(i + 1) % len(PALETTE)] if mods.get("colour") else None).move_to(p)
        mid = p * 0.5 + np.array([0.25 * math.sin(a), -0.25 * math.cos(a), 0])
        wire = VMobject(stroke_color=col(PALETTE[(i + 1) % len(PALETTE)]), stroke_width=STROKE * 0.7)
        wire.set_points_smoothly([np.zeros(3) + p * 0.18, mid, p * 0.82])
        part = VGroup(wire, card)
        g.add(part)
        g.places[key(b)] = part
    return g


def checklist(args: list[str], mods: dict, c=None) -> VGroup:
    done = int(mods.get("done", 0))
    w = float(mods.get("w", 6.0))
    g = VGroup()
    g.places = Keys()
    for i, words in enumerate(args):
        box = RoundedRectangle(width=0.42, height=0.42, corner_radius=0.06, fill_color=col("card"), fill_opacity=1,
                               stroke_color=col("ink"), stroke_width=2)
        t = para(words, 0.3, w - 0.8)
        row = VGroup(box, t).arrange(RIGHT, buff=0.3, aligned_edge=UP)
        if i < done:
            row.add(_tick(box.get_center() + np.array([0.02, 0.0, 0]), 0.36, col(c or "green")),
                    Line(t.get_left(), t.get_right(), stroke_color=col("soft"), stroke_width=1.5).move_to(t))
        g.add(row)
        g.places[key(words)] = row
    g.arrange(DOWN, buff=0.32, aligned_edge=LEFT)
    return g


def proscons(args: list[str], mods: dict, c=None) -> VGroup:
    w = float(mods.get("w", 9.0))
    sides = [_split(a) for a in args[:2]] or [["PROS", ""], ["CONS", ""]]
    g = VGroup()
    g.places = Keys()
    for k, side in enumerate(sides):
        head, items = side[0], (side[1].split("|") if len(side) > 1 and side[1] else [])
        colour = col("green") if k == 0 else col("coral")
        x = (-1 if k == 0 else 1) * w / 4
        col_ = VGroup()
        title = VGroup(RoundedRectangle(width=w / 2 - 0.4, height=0.6, corner_radius=0.1, fill_color=colour, fill_opacity=1, stroke_width=0),
                       even(head.upper(), 0.22, bold=True, color="card"))
        title[1].move_to(title[0])
        col_.add(title)
        for it in items:
            mark = VGroup(Circle(radius=0.15, fill_color=colour, fill_opacity=1, stroke_width=0), even("+" if k == 0 else "−", 0.22, bold=True, color="card"))
            mark[1].move_to(mark[0])
            row = VGroup(mark, para(it.replace("_", " "), 0.24, w / 2 - 1.1)).arrange(RIGHT, buff=0.22, aligned_edge=UP)
            col_.add(row)
            g.places[key(it)] = row
        col_.arrange(DOWN, buff=0.28, aligned_edge=LEFT).move_to([x, 0, 0], aligned_edge=UP)
        col_.shift(UP * 1.6)
        g.add(col_)
        g.places[key(head)] = col_
    g.add(Line([0, 1.7, 0], [0, -1.8, 0], stroke_color=col("soft"), stroke_width=1.5))
    return g


def kpi(args: list[str], mods: dict, c=None) -> VGroup:
    cards = [_split(a) for a in args]
    n = max(1, len(cards))
    cw = min(3.2, float(mods.get("w", 11.0)) / n - 0.3)
    g = VGroup()
    g.places = Keys()
    for i, parts in enumerate(cards):
        name, value = parts[0], (parts[1] if len(parts) > 1 else "")
        change = parts[2] if len(parts) > 2 else ""
        face = _card(cw, 1.9)
        v = text(value, 0.55, bold=True, color=c or "ink")
        if v.width > cw - 0.4:
            v.scale_to_fit_width(cw - 0.4)
        inner = VGroup(label(name.upper(), 0.12, "soft"), v)
        if change:
            up = not change.strip().startswith("-") and not change.strip().startswith("−")
            colour = col("green") if up else col("red")
            arrow = Polygon([-0.09, -0.06, 0], [0.09, -0.06, 0], [0, 0.1, 0], fill_color=colour, fill_opacity=1, stroke_width=0)
            if not up:
                arrow.rotate(math.pi)
            inner.add(VGroup(arrow, label(change, 0.14, "green" if up else "red")).arrange(RIGHT, buff=0.1))
        inner.arrange(DOWN, buff=0.16).move_to(face[1])
        card = VGroup(face, inner).move_to([-(n - 1) * (cw + 0.3) / 2 + i * (cw + 0.3), 0, 0])
        g.add(card)
        g.places[key(name)] = card
    return g


def beforeafter(args: list[str], mods: dict, c=None) -> VGroup:
    sides = [_split(a) for a in args[:2]]
    while len(sides) < 2:
        sides.append(["BEFORE" if not sides else "AFTER", ""])
    w = float(mods.get("w", 10.0))
    cw = (w - 1.6) / 2
    g = VGroup()
    g.places = Keys()
    for k, side in enumerate(sides):
        head, words = side[0], (side[1] if len(side) > 1 else "")
        face = _card(cw, 3.0, fill="card")
        band = RoundedRectangle(width=cw, height=0.6, corner_radius=0.12, fill_color=col("soft" if k == 0 else (c or "accent")), fill_opacity=1,
                                stroke_width=0).move_to(face[1].get_top() + DOWN * 0.3)
        title = even(head.upper(), 0.22, bold=True, color="card").move_to(band)
        body = VGroup(*(para(ln.replace("_", " ").strip(), 0.28, cw - 0.5) for ln in words.split("|") if ln.strip()))
        body.arrange(DOWN, buff=0.22)
        if body.height > 2.1:
            body.scale_to_fit_height(2.1)
        body.move_to(face[1].get_center() + DOWN * 0.25)
        card = VGroup(face, band, title, body).move_to([(-1 if k == 0 else 1) * (cw / 2 + 0.8), 0, 0])
        if k == 0:
            card.set_opacity(0.85)
        g.add(card)
        g.places[key(head)] = card
        if k == 0:
            arrow = Polygon([-0.45, 0.18, 0], [0.15, 0.18, 0], [0.15, 0.4, 0], [0.55, 0, 0], [0.15, -0.4, 0], [0.15, -0.18, 0], [-0.45, -0.18, 0],
                            fill_color=col(c or "accent"), fill_opacity=1, stroke_color=col("ink"), stroke_width=1.5)
            g.add(arrow)
    return g


def progress(args: list[str], mods: dict, c=None) -> VGroup:
    share = max(0.0, min(100.0, _num(args[0]) if args and _num(args[0]) is not None else 50.0))
    words = args[1] if len(args) > 1 else ""
    w = float(mods.get("w", 7.0))
    track = RoundedRectangle(width=w, height=0.5, corner_radius=0.25, fill_color=col("sand"), fill_opacity=1, stroke_color=col("ink"), stroke_width=1.5)
    fill = RoundedRectangle(width=max(0.5, w * share / 100), height=0.5, corner_radius=0.25, fill_color=col(c or "accent"), fill_opacity=1,
                            stroke_width=0).move_to(track.get_left(), aligned_edge=LEFT)
    num = text(f"{share:g}%", 0.34, bold=True, color="ink").next_to(track, RIGHT, buff=0.25)
    g = VGroup(VGroup(track, fill), num)
    if words:
        g.add(even(str(words).replace("_", " ").upper(), 0.17, bold=True).next_to(track, UP, buff=0.18, aligned_edge=LEFT))
    return g


def quadrant(args: list[str], mods: dict, c=None) -> VGroup:
    w, h = float(mods.get("w", 7.0)), float(mods.get("h", 4.6))
    xname, yname = (args[0] if args else ""), (args[1] if len(args) > 1 else "")
    cells = list(args[2:6]) + [""] * (4 - len(args[2:6]))
    g = VGroup()
    g.places = Keys()
    axes = VGroup(Line([-w / 2, 0, 0], [w / 2, 0, 0], stroke_color=col("ink"), stroke_width=2),
                  Line([0, -h / 2, 0], [0, h / 2, 0], stroke_color=col("ink"), stroke_width=2),
                  Polygon([w / 2, 0.1, 0], [w / 2 + 0.2, 0, 0], [w / 2, -0.1, 0], fill_color=col("ink"), fill_opacity=1, stroke_width=0),
                  Polygon([-0.1, h / 2, 0], [0, h / 2 + 0.2, 0], [0.1, h / 2, 0], fill_color=col("ink"), fill_opacity=1, stroke_width=0),
                  label(str(xname).replace("_", " ").upper(), 0.13, "soft").move_to([w / 2 - 0.6, -0.25, 0]),
                  label(str(yname).replace("_", " ").upper(), 0.13, "soft").rotate(math.pi / 2).move_to([-0.25, h / 2 - 0.7, 0]))
    g.add(axes)
    for i, (sx, sy) in enumerate(((-1, 1), (1, 1), (-1, -1), (1, -1))):
        box = Rectangle(width=w / 2 - 0.2, height=h / 2 - 0.2, fill_color=col(PALETTE[i % len(PALETTE)]), fill_opacity=0.18, stroke_width=0)
        box.move_to([sx * w / 4, sy * h / 4, 0])
        part = VGroup(box)
        if cells[i]:
            part.add(para(str(cells[i]), 0.24, w / 2 - 0.6, bold=True).move_to(box))
            g.places[key(cells[i])] = part
        g.add(part)
    return g


BUILD = {"funnel": funnel, "iceberg": iceberg, "ranking": ranking, "mindmap": mindmap, "checklist": checklist,
         "proscons": proscons, "kpi": kpi, "beforeafter": beforeafter, "progress": progress,
         "quadrant": quadrant}
