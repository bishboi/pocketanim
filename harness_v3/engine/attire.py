"""Roles: a figure dressed so it is known at a glance (`ent k person as knight`), and the hats, things held and
clothing details they are made of (people.py draws them on the peg figure).

A role is a set of the person's own modifiers (wear, hat, tool, colour, hair, beard) and of details drawn on the body:
a cape (an ermine trim for a king), a tabard with its emblem, a chain of office, a cross on a chain, a chasuble with
its gold cross, a priest's collar, a sari's drape, a dhoti, a shawl, cross belts, mail, patches, a necklace, beads; a
shield or a book in the other hand; glasses or an eye patch on the face. Anything said on the line wins over the role:
`as king color navy`.
"""

from __future__ import annotations


import numpy as np
from manim import Circle, Dot, Ellipse, Line, VGroup

from look import col

# Each role: the person's modifiers, and its details (`decor`). Colours are the paper look's or hex.
ROLES = {
    # -- kings, queens, the court ------------------------------------------------------------------------------------
    "king": dict(wear="gown", color="#7A1F2B", hat="crown", tool="scepter", beard=True,
                 decor=dict(cape="#8E1B2C", ermine=True, chain="#F2C14E")),
    "queen": dict(wear="gown", color="#5B3A8E", hat="crown", hair="long", tool="orb",
                  decor=dict(cape="#3E2A6E", ermine=True, necklace="#F7F5F0")),
    "lord": dict(wear="coat", color="#2E5E4E", hat="feathercap", beard=True,
                 decor=dict(cape="#24473C", chain="#F2C14E")),
    "lady": dict(wear="gown", color="#2E6E9E", hat="hennin", hair="long", decor=dict(necklace="#F7F5F0")),
    "prince": dict(wear="coat", color="#2F3B8C", hat="circlet", decor=dict(cape="#B83227", chain="#F2C14E")),
    "princess": dict(wear="gown", color="#D46A9A", hat="circlet", hair="long", decor=dict(necklace="#F7F5F0")),
    "jester": dict(wear="tunic", color="#B83227", hat="jester", decor=dict(halves="#F2C14E")),
    # -- war ---------------------------------------------------------------------------------------------------------
    "knight": dict(wear="armor", hat="greathelm", tool="sword",
                   decor=dict(tabard="#F7F5F0", emblem="#B83227", plume="#B83227", offhand="shield")),
    "soldier": dict(wear="tunic", color="#6E6A5E", hat="kettle", tool="spear", decor=dict(mail=True)),
    "archer": dict(wear="tunic", color="#3F6B3A", hat="hood", tool="bow", decor=dict(quiver=True)),
    "roman": dict(wear="tunic", color="#B83227", hat="legion", tool="spear",
                  decor=dict(segments=True, offhand="scutum")),
    "viking": dict(wear="tunic", color="#5B4A3A", hat="viking", tool="axe", beard=True, hair="long",
                   decor=dict(offhand="round_shield")),
    "samurai": dict(wear="robe", color="#2F3B4C", hat="topknot", tool="katana", decor=dict(sash="#B83227")),
    "redcoat": dict(wear="uniform", color="#B83227", hat="tricorn", tool="musket", decor=dict(crossbelts=True)),
    "sepoy": dict(wear="uniform", color="#B83227", hat="pagdi_white", tool="musket", mustache=True,
                  decor=dict(crossbelts=True)),
    "officer": dict(wear="uniform", color="#B83227", hat="pith", mustache=True, tool="sword",
                    decor=dict(sash="#F2C14E")),
    "general": dict(wear="uniform", color="#2F3B4C", hat="bicorne", tool="sword", decor=dict(sash="#B83227")),
    "pirate": dict(wear="coat", color="#3A2A1E", hat="tricorn", tool="sword", beard=True, decor=dict(eyepatch=True)),
    # -- church and learning -------------------------------------------------------------------------------------------
    "bishop": dict(wear="robe", color="#F3EEE4", hat="mitre", tool="crozier", decor=dict(chasuble="#B83227")),
    "pope": dict(wear="robe", color="#F7F5F0", hat="mitre", tool="crozier", decor=dict(chasuble="#F2C14E")),
    "priest": dict(wear="robe", color="#22201E", decor=dict(clerical=True, pendant="#F2C14E")),
    "monk": dict(wear="habit", hat="hood", hair="bald", decor=dict(pendant="#8C6E52")),
    "nun": dict(wear="habit", color="#22201E", hat="wimple", decor=dict(pendant="#F2C14E")),
    "scholar": dict(wear="robe", color="#3A2E5E", hat="mortarboard", tool="book", beard=True),
    "pharaoh": dict(wear="toga", color="#F3EEE4", hat="nemes", tool="crook", decor=dict(collar_gold=True)),
    # -- work --------------------------------------------------------------------------------------------------------
    "peasant": dict(wear="tunic", color="#8C6E52", hat="coif", tool="pitchfork", skin="tan", decor=dict(patches=True)),
    "merchant": dict(wear="coat", color="#6E3A8E", hat="feathercap", tool="bag", decor=dict(chain="#F2C14E")),
    "blacksmith": dict(wear="apron", color="#5B4A3A", tool="hammer", hair="short", beard=True),
    "sailor": dict(wear="shirt", color="#F7F5F0", hat="sailor", decor=dict(stripes="#2F3B4C")),
    "explorer": dict(wear="coat", color="#B59A6A", hat="pith", tool="lantern"),
    "doctor": dict(wear="lab", tool="briefcase", decor=dict(stethoscope=True)),
    "scientist": dict(wear="lab", decor=dict(glasses=True), tool="book"),
    "judge": dict(wear="robe", color="#22201E", hat="wig", tool="gavel", decor=dict(bands=True)),
    "police": dict(wear="uniform", color="#B59A6A", hat="cap", tool="baton", decor=dict(belt="#5B4A3A")),
    "teacher": dict(wear="suit", color="#5B6E8C", tool="pointer", decor=dict(glasses=True)),
    "student": dict(wear="shirt", color="#F7F5F0", tool="book", kid=True, decor=dict(tie="#2F3B8C")),
    "worker": dict(wear="overalls", hat="hardhat", tool="hammer"),
    "chef": dict(wear="apron", color="#F7F5F0", hat="chef"),
    # -- India ---------------------------------------------------------------------------------------------------
    "maharaja": dict(wear="gown", color="#D4A017", hat="mughal", tool="talwar", mustache=True, skin="tan",
                     decor=dict(necklace="#F7F5F0", sash="#B83227")),
    "rani": dict(wear="dress", color="#B83227", hat="tiara", hair="long", skin="tan",
                 decor=dict(sari="#B83227", border="#F2C14E", necklace="#F2C14E")),
    "mughal": dict(wear="gown", color="#F3EEE4", hat="mughal", beard=True, skin="tan",
                   decor=dict(necklace="#F7F5F0", sash="#2E6E4E")),
    "kisan": dict(wear="vest", color="#F3EEE4", hat="pagdi", tool="sickle", skin="brown", mustache=True,
                  decor=dict(dhoti=True)),
    "villager": dict(wear="dress", color="#2E7D74", hat="pallu", skin="brown", hair="bun",
                     decor=dict(sari="#2E7D74", border="#F2C14E")),
    "sadhu": dict(wear="robe", color="#E07B39", hair="bun", longbeard=True, tool="staff", skin="brown",
                  decor=dict(beads="#5B3A1E")),
    "pandit": dict(wear="vest", color="#F3EEE4", hair="bald", tool="scroll", skin="tan",
                   decor=dict(dhoti=True, shawl="#E07B39", tilak=True)),
    "freedom": dict(wear="vest", color="#F3EEE4", hat="topi", skin="tan", tool="flag", decor=dict(shawl="#F3EEE4")),
}
ROLE_NAMES = tuple(ROLES)
ALIASES = {"noble": "lord", "nobleman": "lord", "noblewoman": "lady", "duke": "lord", "baron": "lord",
           "emperor": "king", "empress": "queen", "raja": "maharaja", "maharani": "rani", "farmer": "kisan",
           "serf": "peasant", "villager_woman": "villager", "legionary": "roman", "cardinal": "bishop",
           "friar": "monk", "teacher_woman": "teacher", "british": "officer", "soldier_british": "redcoat",
           "trader": "merchant", "guru": "sadhu", "brahmin": "pandit", "satyagrahi": "freedom", "constable": "police"}


def role(mods: dict) -> dict:
    """A person's modifiers with its role's (`as knight`) under them: what the line says wins."""
    name = str(mods.get("as") or "").lower().strip()
    name = ALIASES.get(name, name)
    if name not in ROLES:
        return mods
    preset = dict(ROLES[name])
    decor = {**preset.pop("decor", {}), **(mods.get("decor") or {})}
    return {**preset, **mods, "decor": decor}


# ---------------------------------------------------------------- hats (the head's frame, a head of radius R) -------

def _poly(points, fill, ink, w):
    from people import _poly as p
    return p(points, fill, ink, w)


def _blob(points, fill, ink, w):
    from people import _blob as b
    return b(points, fill, ink, w)


def _stroke(points, ink, w):
    from people import _stroke as s
    return s(points, ink, w)


def hat(kind: str, ink, ow, R, cloth):
    """(behind the head, over it) for the hats the roles bring; None when the kind is not one of them."""
    from people import _arc
    back, front = VGroup(), VGroup()
    top = R * 0.72
    gold, red, white = "#F2C14E", "#B83227", "#F7F5F0"
    if kind == "greathelm":                     # a knight's: a flat-topped helm, an eye slit, breaths, a plume
        front.add(_poly([(-R * 1.08, -R * 1.05), (R * 1.08, -R * 1.05), (R * 1.12, R * 0.9), (0.0, R * 1.12),
                         (-R * 1.12, R * 0.9)], "#A7AEB3", ink, ow),
                  _poly([(-R * 0.15, R * 0.15), (R * 1.1, R * 0.15), (R * 1.1, R * 0.32), (-R * 0.15, R * 0.32)],
                        "#2B2622", ink, ow * 0.6),
                  _stroke([(0.0, R * 1.1), (0.0, -R * 1.0)], ink, ow * 0.8),
                  *(Dot([R * 0.55 + i * R * 0.17, -R * 0.35 - j * R * 0.18, 0], radius=R * 0.04, color=ink)
                    for i in range(3) for j in range(2)))
        return back, front
    if kind == "kettle":                        # a soldier's wide-brimmed iron hat
        front.add(_poly(_arc(0, R * 0.25, R * 1.05, 0, 180, 18), "#8E969C", ink, ow),
                  _blob([(-R * 1.55, R * 0.22), (R * 1.55, R * 0.22), (R * 1.25, R * 0.36), (-R * 1.25, R * 0.36)],
                        "#8E969C", ink, ow))
        return back, front
    if kind == "legion":                        # a Roman legionary's helmet, its red crest front to back
        front.add(_poly(_arc(0, R * 0.2, R * 1.1, 0, 180, 18), "#C9A66B", ink, ow),
                  _blob([(-R * 1.0, R * 0.95), (-R * 0.3, R * 1.75), (R * 0.6, R * 1.7), (R * 1.0, R * 1.0),
                         (R * 0.3, R * 1.25), (-R * 0.4, R * 1.2)], red, ink, ow),
                  _poly([(R * 0.75, -R * 0.55), (R * 0.95, -R * 0.55), (R * 0.95, R * 0.2), (R * 0.75, R * 0.2)],
                        "#C9A66B", ink, ow * 0.6))
        return back, front
    if kind == "viking":                        # a round iron helmet with a nose guard (no horns: they had none)
        front.add(_poly(_arc(0, R * 0.25, R * 1.08, 0, 180, 18), "#8E969C", ink, ow),
                  _poly([(-R * 0.08, R * 0.3), (R * 0.08, R * 0.3), (R * 0.06, -R * 0.35), (-R * 0.06, -R * 0.35)],
                        "#8E969C", ink, ow * 0.6),
                  _stroke([(-R * 1.0, R * 0.55), (R * 1.0, R * 0.55)], ink, ow * 0.8))
        return back, front
    if kind == "topknot":                       # a samurai's: shaved crown, the knot on top
        front.add(_blob([(-R * 0.25, top + R * 0.2), (R * 0.25, top + R * 0.25), (R * 0.1, top + R * 0.55),
                         (-R * 0.1, top + R * 0.5)], "#2A2320", ink, ow))
        back.add(_blob(_arc(0, 0, R * 1.05, 110, 250, 12), "#2A2320", ink, ow))
        return back, front
    if kind == "wimple":                        # a nun's: a white band round the face, a black veil over and behind
        back.add(_blob([(R * 0.2, R * 1.2), (-R * 0.9, R * 1.15), (-R * 1.6, R * 0.1), (-R * 1.7, -R * 2.4),
                        (R * 0.3, -R * 2.4), (R * 0.4, -R * 1.1)], "#22201E", ink, ow))
        front.add(_blob(_arc(0, R * 0.1, R * 1.22, 25, 200, 16) + [(-R * 0.95, R * 0.3), (0.0, R * 0.75),
                                                                  (R * 0.9, R * 0.5)], "#22201E", ink, ow),
                  _stroke(_arc(0, -R * 0.05, R * 1.02, 30, 330, 24), white, ow * 3.2))
        return back, front
    if kind == "coif":                          # a peasant's linen cap, tied under the chin
        front.add(_blob(_arc(0, R * 0.05, R * 1.12, 10, 200, 16) + [(-R * 1.0, -R * 0.2), (0.0, R * 0.55),
                                                                   (R * 1.0, R * 0.2)], "#E9DFC6", ink, ow),
                  _stroke([(R * 0.95, R * 0.1), (R * 0.6, -R * 0.8), (R * 0.3, -R * 1.05)], ink, ow * 0.6))
        return back, front
    if kind == "feathercap":                    # a lord's or merchant's flat cap with a feather
        c = cloth or "#2E5E4E"
        front.add(_blob([(-R * 1.25, R * 0.62), (R * 1.25, R * 0.66), (R * 1.0, R * 1.05), (-R * 0.9, R * 1.08)],
                        c, ink, ow),
                  _blob([(-R * 0.75, R * 0.9), (-R * 1.45, R * 1.7), (-R * 1.05, R * 1.85), (-R * 0.35, R * 1.0)],
                        white, ink, ow * 0.6))
        return back, front
    if kind == "hennin":                        # a lady's tall cone with a veil
        front.add(_poly([(-R * 0.55, top), (R * 0.45, top + R * 0.2), (-R * 0.6, top + R * 1.25)], "#D46A9A", ink, ow))
        back.add(_blob([(-R * 0.6, top + R * 1.25), (-R * 1.3, top + R * 0.3), (-R * 1.25, -R * 0.6),
                        (-R * 0.9, top + R * 0.3)], "#F7F5F0", ink, ow * 0.6))
        return back, front
    if kind in ("circlet", "tiara"):            # a thin gold band (a prince's, a princess's, a rani's)
        front.add(_stroke(_arc(0, R * 0.25, R * 1.02, 15, 165, 12), gold, ow * 2.2))
        if kind == "tiara":
            front.add(_poly([(-R * 0.25, R * 1.2), (0.0, R * 1.55), (R * 0.25, R * 1.2)], gold, ink, ow * 0.6),
                      Dot([0, R * 1.3, 0], radius=R * 0.08, color=red))
        return back, front
    if kind == "jester":                        # two drooping points with bells
        for s_, c in ((-1, red), (1, gold)):
            front.add(_blob([(0.0, top), (s_ * R * 0.4, top + R * 1.0), (s_ * R * 1.5, top + R * 0.4),
                             (s_ * R * 1.0, top - R * 0.1)], c, ink, ow),
                      Circle(radius=R * 0.13, fill_color=gold, fill_opacity=1, stroke_color=ink,
                             stroke_width=ow * 0.6).move_to([s_ * R * 1.5, top + R * 0.35, 0]))
        front.add(_blob(_arc(0, R * 0.1, R * 1.1, 10, 170, 14) + [(-R * 0.8, R * 0.5), (R * 0.8, R * 0.5)], red, ink, ow))
        return back, front
    if kind == "mortarboard":                   # a scholar's square cap and tassel
        front.add(_blob(_arc(0, R * 0.4, R * 1.0, 0, 180, 14), "#22201E", ink, ow),
                  _poly([(-R * 1.4, top + R * 0.25), (R * 0.2, top + R * 0.55), (R * 1.4, top + R * 0.25),
                         (-R * 0.2, top - R * 0.05)], "#22201E", ink, ow),
                  _stroke([(0.0, top + R * 0.25), (R * 0.9, top + R * 0.2), (R * 1.0, top - R * 0.6)], gold, ow * 1.2))
        return back, front
    if kind == "nemes":                         # a pharaoh's striped headcloth
        back.add(_poly([(-R * 1.1, R * 0.6), (R * 1.1, R * 0.6), (R * 1.5, -R * 1.6), (-R * 1.5, -R * 1.6)],
                       "#F2C14E", ink, ow))
        for i in range(4):
            back.add(_stroke([(-R * 1.4 + i * R * 0.05, -R * 0.9 - i * R * 0.15), (R * 1.4 - i * R * 0.05,
                                                                                  -R * 0.9 - i * R * 0.15)],
                             "#2F5E9E", ow * 1.4))
        front.add(_blob(_arc(0, R * 0.15, R * 1.12, 15, 165, 14) + [(0.0, R * 0.7)], "#F2C14E", ink, ow),
                  _stroke(_arc(0, R * 0.15, R * 0.95, 30, 150, 10), "#2F5E9E", ow * 1.6),
                  Dot([R * 0.15, R * 1.05, 0], radius=R * 0.1, color=red))
        return back, front
    if kind == "bicorne":                       # a general's two-cornered hat, worn sideways
        front.add(_blob([(-R * 1.6, top + R * 0.15), (0.0, top + R * 1.15), (R * 1.6, top + R * 0.15),
                         (0.0, top - R * 0.05)], "#22201E", ink, ow),
                  Circle(radius=R * 0.16, fill_color=red, fill_opacity=1, stroke_color=white,
                         stroke_width=ow).move_to([R * 0.35, top + R * 0.45, 0]))
        return back, front
    if kind == "pith":                          # a sola topi (a pith helmet: a British officer, an explorer)
        front.add(_blob(_arc(0, R * 0.45, R * 1.05, 0, 180, 18), "#E9DFC6", ink, ow),
                  _blob([(-R * 1.55, R * 0.42), (R * 1.6, R * 0.42), (R * 1.3, R * 0.6), (-R * 1.3, R * 0.6)],
                        "#E9DFC6", ink, ow),
                  _stroke([(-R * 1.0, R * 0.62), (R * 1.0, R * 0.62)], "#B59A6A", ow * 1.5))
        return back, front
    if kind == "wig":                           # a judge's white wig
        back.add(_blob([(-R * 1.25, R * 0.8), (-R * 1.6, -R * 1.4), (-R * 0.9, -R * 1.6), (-R * 0.6, R * 0.6)],
                       white, ink, ow))
        for y in (R * 0.2, -R * 0.3, -R * 0.8):
            back.add(_stroke(_arc(-R * 1.15, y, R * 0.28, 90, 270, 8), "#C9C2B2", ow))
        front.add(_blob(_arc(0, R * 0.1, R * 1.15, 20, 175, 16) + [(0.0, R * 0.65)], white, ink, ow))
        return back, front
    if kind == "sailor":
        front.add(_blob(_arc(0, R * 0.55, R * 0.95, 0, 180, 16), white, ink, ow),
                  _poly([(-R * 1.0, R * 0.5), (R * 1.0, R * 0.5), (R * 1.0, R * 0.7), (-R * 1.0, R * 0.7)],
                        "#2F3B4C", ink, ow * 0.6))
        return back, front
    if kind in ("pagdi", "pagdi_white", "mughal"):   # a turban: a farmer's, a sepoy's, an emperor's with its jewel
        c = {"pagdi": "#E07B39", "pagdi_white": "#F3EEE4", "mughal": "#F3EEE4"}[kind]
        if kind == "pagdi" and cloth and cloth != "#F3EEE4":
            c = "#E07B39"
        front.add(_blob([(-R * 1.15, R * 0.15), (-R * 1.2, R * 0.9), (-R * 0.3, R * 1.55), (R * 0.7, R * 1.4),
                         (R * 1.2, R * 0.85), (R * 1.15, R * 0.2), (0.0, R * 0.45)], c, ink, ow),
                  _stroke([(-R * 1.05, R * 0.55), (0.0, R * 1.1), (R * 1.05, R * 0.75)], _shade(c, 0.8), ow),
                  _stroke([(-R * 1.0, R * 0.95), (R * 0.2, R * 1.4)], _shade(c, 0.8), ow))
        if kind == "pagdi":                     # its loose end down the back
            back.add(_blob([(-R * 0.9, R * 0.5), (-R * 1.5, -R * 0.9), (-R * 1.25, -R * 1.0), (-R * 0.7, R * 0.3)],
                           c, ink, ow))
        if kind == "mughal":                    # a jewel and a heron's plume
            front.add(Circle(radius=R * 0.16, fill_color=red, fill_opacity=1, stroke_color=gold,
                             stroke_width=ow * 1.2).move_to([R * 0.55, R * 1.1, 0]),
                      _blob([(R * 0.5, R * 1.25), (R * 0.2, R * 2.1), (R * 0.4, R * 2.1), (R * 0.65, R * 1.3)],
                            white, ink, ow * 0.6))
        return back, front
    if kind == "pallu":                         # a sari's end drawn over the head
        back.add(_blob([(R * 0.3, R * 1.2), (-R * 0.9, R * 1.2), (-R * 1.6, R * 0.0), (-R * 1.6, -R * 2.0),
                        (-R * 0.4, -R * 2.0), (R * 0.2, -R * 0.8)], "#2E7D74", ink, ow))
        front.add(_blob(_arc(0, R * 0.05, R * 1.16, 30, 200, 16) + [(-R * 0.9, R * 0.3), (R * 0.2, R * 0.9)],
                        "#2E7D74", ink, ow),
                  _stroke(_arc(0, R * 0.05, R * 1.16, 30, 200, 16), "#F2C14E", ow * 1.4))
        return back, front
    if kind == "topi":                          # a white cotton cap (a satyagrahi's)
        front.add(_poly([(-R * 0.95, R * 0.62), (R * 0.95, R * 0.62), (R * 0.75, R * 1.05), (-R * 0.75, R * 1.05)],
                        "#F7F5F0", ink, ow),
                  _stroke([(-R * 0.75, R * 1.03), (R * 0.75, R * 1.03)], ink, ow * 0.6))
        return back, front
    return None


def _shade(hex_colour: str, k: float) -> str:
    from people import _shade as s
    return s(hex_colour, k)


# ---------------------------------------------------------------- things held (the hand's frame, the grip at 0) ------

def tool(kind: str, ink, ow, k):
    """The roles' things held; None when the kind is not one of them."""
    from people import _arc
    wood, metal, gold = "#9A6B43", "#B8BEC2", "#F2C14E"
    stick = lambda y0, y1, c=wood, w=4.0: Line([0, y0, 0], [0, y1, 0], stroke_color=c, stroke_width=w * k)  # noqa: E731
    if kind == "scepter":
        return VGroup(stick(-0.12, 0.3, gold, 3.6), Circle(radius=0.03, fill_color=gold, fill_opacity=1,
                                                           stroke_color=ink, stroke_width=ow).move_to([0, 0.32, 0]),
                      Dot([0, 0.32, 0], radius=0.012, color="#B83227"))
    if kind == "orb":
        return VGroup(Circle(radius=0.045, fill_color=gold, fill_opacity=1, stroke_color=ink, stroke_width=ow)
                      .move_to([0.01, 0.05, 0]), _stroke([(0.01, 0.095), (0.01, 0.135)], ink, ow * 1.2),
                      _stroke([(-0.01, 0.118), (0.03, 0.118)], ink, ow * 1.2))
    if kind == "crozier":                       # a bishop's staff, its crook
        return VGroup(stick(-0.3, 0.32, gold, 3.4), _stroke(_arc(0.045, 0.34, 0.045, 180, -60, 12), gold, 3.4 * k))
    if kind == "crook":
        return VGroup(stick(-0.12, 0.18, "#2F5E9E", 3.4), _stroke(_arc(0.03, 0.2, 0.03, 180, 0, 8), gold, 3.4 * k))
    if kind == "pitchfork":
        g = VGroup(stick(-0.3, 0.3))
        for x in (-0.03, 0.0, 0.03):
            g.add(Line([x, 0.3, 0], [x, 0.4, 0], stroke_color=metal, stroke_width=2.4 * k))
        g.add(Line([-0.03, 0.3, 0], [0.03, 0.3, 0], stroke_color=metal, stroke_width=2.4 * k))
        return g
    if kind == "sickle":
        return VGroup(stick(-0.05, 0.05), _stroke(_arc(0.06, 0.08, 0.06, 200, -20, 14), metal, 3.0 * k))
    if kind == "axe":
        return VGroup(stick(-0.08, 0.25), _blob([(0.0, 0.25), (0.07, 0.29), (0.09, 0.2), (0.0, 0.2)], metal, ink, ow))
    if kind == "bow":
        return VGroup(_stroke(_arc(-0.05, 0.03, 0.2, -60, 60, 12), wood, 3.2 * k),
                      Line([0.05, -0.14, 0], [0.05, 0.2, 0], stroke_color=ink, stroke_width=0.8 * k))
    if kind == "musket":
        return VGroup(Line([-0.05, -0.12, 0], [0.0, 0.42, 0], stroke_color=wood, stroke_width=4.2 * k),
                      Line([0.0, 0.3, 0], [0.005, 0.5, 0], stroke_color=metal, stroke_width=2.4 * k))
    if kind == "katana":
        return VGroup(_stroke([(0.0, 0.03), (0.04, 0.22), (0.1, 0.38)], metal, 2.6 * k),
                      Line([-0.02, 0.03, 0], [0.03, 0.02, 0], stroke_color=gold, stroke_width=3 * k),
                      Line([0.0, 0.02, 0], [-0.01, -0.06, 0], stroke_color="#2B2622", stroke_width=3.4 * k))
    if kind == "talwar":                        # a curved Indian sword
        return VGroup(_stroke([(0.0, 0.03), (0.02, 0.2), (0.09, 0.33), (0.15, 0.36)], metal, 3.0 * k),
                      Line([-0.03, 0.03, 0], [0.03, 0.03, 0], stroke_color=gold, stroke_width=3 * k),
                      Line([0.0, 0.03, 0], [0.0, -0.05, 0], stroke_color=gold, stroke_width=3.4 * k))
    if kind == "gavel":
        return VGroup(stick(-0.02, 0.12), _poly([(-0.05, 0.12), (0.05, 0.12), (0.05, 0.17), (-0.05, 0.17)],
                                               "#6B4A2F", ink, ow))
    if kind == "baton":
        return VGroup(stick(-0.04, 0.2, "#3A3631", 4.0))
    return None


def offhand(kind: str, ink, ow, k):
    """What the other hand holds (the hand's frame): a knight's shield, a legionary's, a Viking's round one."""
    gold, red = "#F2C14E", "#B83227"
    if kind == "shield":                        # a heater shield with a red cross
        return VGroup(_blob([(-0.1, 0.12), (0.1, 0.12), (0.09, -0.04), (0.0, -0.15), (-0.09, -0.04)], "#F7F5F0", ink, ow),
                      Line([0.0, 0.11, 0], [0.0, -0.13, 0], stroke_color=red, stroke_width=5 * k),
                      Line([-0.09, 0.05, 0], [0.09, 0.05, 0], stroke_color=red, stroke_width=5 * k))
    if kind == "scutum":
        return VGroup(_poly([(-0.08, 0.17), (0.08, 0.17), (0.08, -0.17), (-0.08, -0.17)], red, ink, ow),
                      Circle(radius=0.03, fill_color=gold, fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.6),
                      _stroke([(-0.06, 0.12), (0.06, 0.12)], gold, ow * 1.2), _stroke([(-0.06, -0.12), (0.06, -0.12)], gold, ow * 1.2))
    if kind == "round_shield":
        return VGroup(Circle(radius=0.12, fill_color="#9A6B43", fill_opacity=1, stroke_color=ink, stroke_width=ow),
                      Circle(radius=0.03, fill_color="#8E969C", fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.6),
                      Line([-0.12, 0, 0], [0.12, 0, 0], stroke_color="#B83227", stroke_width=3 * k))
    if kind == "book":
        from people import _tool
        return _tool("book", ink, ow, k)
    return None


# ---------------------------------------------------------------- on the body (the torso's frame) -------------------

def behind(decor: dict, ink, ow, W: float, y0: float, top: float):
    """What hangs behind the body: a cape."""
    g = VGroup()
    if decor.get("cape"):
        c = col(decor["cape"])
        g.add(_blob([(-W * 0.5, top - 0.02), (W * 0.5, top - 0.02), (W * 0.78, y0 + 0.06), (W * 0.6, y0 - 0.02),
                     (-W * 0.6, y0 - 0.02), (-W * 0.78, y0 + 0.06)], c, ink, ow))
        if decor.get("ermine"):                 # white fur with black tails along its hem
            g.add(_poly([(-W * 0.78, y0 + 0.06), (W * 0.78, y0 + 0.06), (W * 0.6, y0 - 0.02), (-W * 0.6, y0 - 0.02)],
                        "#F7F5F0", ink, ow * 0.6))
            for x in np.linspace(-W * 0.6, W * 0.6, 7):
                g.add(Dot([x, y0 + 0.025, 0], radius=0.007, color=ink))
    return g


def on_body(decor: dict, ink, ow, W: float, y0: float, top: float):
    """What is drawn on the body over its clothes."""
    g = VGroup()
    full = top - y0
    gold, white = "#F2C14E", "#F7F5F0"
    line = lambda pts, c=ink, w=ow: _stroke(pts, c, w)  # noqa: E731
    if decor.get("cape"):                       # its edges over the shoulders, and the ermine collar
        c = col(decor["cape"])
        g.add(_poly([(-W * 0.52, top - 0.01), (-W * 0.34, top - 0.01), (-W * 0.46, y0 + full * 0.3),
                     (-W * 0.52, y0 + full * 0.3)], c, ink, ow * 0.6),
              _poly([(W * 0.52, top - 0.01), (W * 0.34, top - 0.01), (W * 0.46, y0 + full * 0.3),
                     (W * 0.52, y0 + full * 0.3)], c, ink, ow * 0.6))
        if decor.get("ermine"):
            g.add(_blob([(-W * 0.48, top - 0.08), (0.0, top - 0.02), (W * 0.48, top - 0.08), (W * 0.42, top + 0.01),
                         (0.0, top + 0.03), (-W * 0.42, top + 0.01)], white, ink, ow * 0.6),
                  *(Dot([x, top - 0.035, 0], radius=0.006, color=ink) for x in (-0.1, -0.03, 0.04, 0.11)))
    if decor.get("tabard"):                     # a knight's tabard over the armour, its emblem a cross
        g.add(_poly([(-W * 0.3, top - 0.03), (W * 0.3, top - 0.03), (W * 0.34, y0 + 0.02), (-W * 0.34, y0 + 0.02)],
                    col(decor["tabard"]), ink, ow * 0.8))
        e = col(decor.get("emblem") or "#B83227")
        cy = y0 + full * 0.55
        g.add(_poly([(-0.022, cy + 0.12), (0.022, cy + 0.12), (0.022, cy - 0.14), (-0.022, cy - 0.14)], e, e, 0),
              _poly([(-0.085, cy + 0.04), (0.085, cy + 0.04), (0.085, cy - 0.005), (-0.085, cy - 0.005)], e, e, 0))
    if decor.get("chasuble"):                   # a bishop's vestment, its gold Y-cross
        c = col(decor["chasuble"])
        g.add(_blob([(-W * 0.38, top - 0.02), (W * 0.38, top - 0.02), (W * 0.42, y0 + full * 0.25), (0.0, y0 + 0.05),
                     (-W * 0.42, y0 + full * 0.25)], c, ink, ow),
              line([(-0.08, top - 0.03), (0.0, top - 0.12), (0.08, top - 0.03)], gold, ow * 2.2),
              line([(0.0, top - 0.12), (0.0, y0 + 0.1)], gold, ow * 2.2))
    if decor.get("clerical"):                   # a priest's white collar tab
        g.add(_poly([(-0.02, top - 0.005), (0.02, top - 0.005), (0.02, top - 0.04), (-0.02, top - 0.04)], white, ink, ow * 0.5))
    if decor.get("bands"):                      # a judge's white bands
        g.add(_poly([(-0.03, top - 0.01), (0.0, top - 0.01), (-0.005, top - 0.09), (-0.03, top - 0.09)], white, ink, ow * 0.5),
              _poly([(0.0, top - 0.01), (0.03, top - 0.01), (0.03, top - 0.09), (0.005, top - 0.09)], white, ink, ow * 0.5))
    if decor.get("chain"):                      # a chain of office
        c = col(decor["chain"])
        pts = [(x, top - 0.02 - 0.18 * (1 - (x / (W * 0.42)) ** 2)) for x in np.linspace(-W * 0.42, W * 0.42, 11)]
        for x, y in pts:
            g.add(Circle(radius=0.012, fill_opacity=0, stroke_color=c, stroke_width=ow * 1.2).move_to([x, y, 0]))
        g.add(Circle(radius=0.025, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.6)
              .move_to([0, top - 0.22, 0]))
    if decor.get("pendant"):                    # a cross on a cord
        c = col(decor["pendant"])
        g.add(line([(-0.06, top - 0.01), (0.0, top - 0.15), (0.06, top - 0.01)], c, ow * 0.7),
              _poly([(-0.008, top - 0.14), (0.008, top - 0.14), (0.008, top - 0.24), (-0.008, top - 0.24)], c, ink, ow * 0.4),
              _poly([(-0.03, top - 0.17), (0.03, top - 0.17), (0.03, top - 0.185), (-0.03, top - 0.185)], c, ink, ow * 0.4))
    if decor.get("necklace"):                   # pearls
        c = col(decor["necklace"])
        for x in np.linspace(-0.09, 0.09, 9):
            g.add(Circle(radius=0.012, fill_color=c, fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.3)
                  .move_to([x, top - 0.03 - 0.06 * (1 - (x / 0.09) ** 2), 0]))
    if decor.get("beads"):                      # rudraksha beads
        c = col(decor["beads"])
        for x in np.linspace(-0.1, 0.1, 11):
            g.add(Dot([x, top - 0.03 - 0.14 * (1 - (x / 0.1) ** 2), 0], radius=0.011, color=c))
    if decor.get("sash"):                       # a sash from the shoulder across
        c = col(decor["sash"])
        g.add(_poly([(-W * 0.48, top - 0.03), (-W * 0.3, top - 0.03), (W * 0.48, y0 + full * 0.35),
                     (W * 0.48, y0 + full * 0.47)], c, ink, ow * 0.6))
    if decor.get("crossbelts"):                 # white belts crossed over a red coat
        g.add(line([(-W * 0.45, top - 0.03), (W * 0.42, y0 + full * 0.38)], white, ow * 3),
              line([(W * 0.45, top - 0.03), (-W * 0.42, y0 + full * 0.38)], white, ow * 3),
              Circle(radius=0.022, fill_color=gold, fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.5)
              .move_to([0.0, y0 + full * 0.62, 0]))
    if decor.get("belt"):
        c = col(decor["belt"])
        yb = y0 + full * 0.42
        g.add(_poly([(-W / 2, yb), (W / 2, yb), (W / 2, yb + 0.03), (-W / 2, yb + 0.03)], c, ink, ow * 0.6))
    if decor.get("mail"):                       # mail: rows of little rings
        for r in range(5):
            y = top - 0.08 - r * 0.07
            for x in np.linspace(-W * 0.4, W * 0.4, 7):
                g.add(Circle(radius=0.012, fill_opacity=0, stroke_color="#8E969C", stroke_width=ow * 0.6)
                      .move_to([x + (0.015 if r % 2 else 0), y, 0]))
    if decor.get("segments"):                   # a legionary's banded armour
        for y in np.linspace(top - 0.06, y0 + full * 0.5, 5):
            g.add(_poly([(-W * 0.48, y), (W * 0.48, y), (W * 0.48, y - 0.04), (-W * 0.48, y - 0.04)], "#B8BEC2", ink, ow * 0.5))
    if decor.get("patches"):                    # a peasant's patched tunic
        g.add(_poly([(-0.1, y0 + 0.12), (-0.03, y0 + 0.12), (-0.03, y0 + 0.19), (-0.1, y0 + 0.19)], "#C9A66B", ink, ow * 0.6),
              _poly([(0.04, top - 0.2), (0.1, top - 0.2), (0.1, top - 0.14), (0.04, top - 0.14)], "#6B5A44", ink, ow * 0.6))
    if decor.get("halves"):                     # a jester's two colours
        g.add(_poly([(0.0, top - 0.02), (W * 0.48, top - 0.02), (W * 0.48, y0 + 0.02), (0.0, y0 + 0.02)],
                    col(decor["halves"]), ink, ow * 0.6))
    if decor.get("stripes"):                    # a sailor's stripes
        for y in np.linspace(top - 0.1, y0 + full * 0.45, 5):
            g.add(line([(-W * 0.45, y), (W * 0.45, y)], col(decor["stripes"]), ow * 1.6))
    if decor.get("tie"):
        c = col(decor["tie"])
        g.add(_poly([(0.0, top - 0.04), (0.018, top - 0.07), (0.0, top - 0.2), (-0.018, top - 0.07)], c, ink, ow * 0.5))
    if decor.get("stethoscope"):
        g.add(line([(-0.07, top - 0.01), (-0.06, top - 0.15), (0.0, top - 0.22), (0.05, top - 0.16)], "#3A3631", ow * 1.3),
              Circle(radius=0.02, fill_color="#B8BEC2", fill_opacity=1, stroke_color=ink, stroke_width=ow * 0.5)
              .move_to([0.05, top - 0.16, 0]))
    if decor.get("collar_gold"):                # a pharaoh's broad collar
        g.add(_blob([(-W * 0.48, top - 0.02), (W * 0.48, top - 0.02), (W * 0.3, top - 0.13), (0.0, top - 0.16),
                     (-W * 0.3, top - 0.13)], gold, ink, ow * 0.8),
              line([(-W * 0.35, top - 0.08), (0.0, top - 0.11), (W * 0.35, top - 0.08)], "#2F5E9E", ow * 1.4))
    if decor.get("shawl"):                      # a shawl over the shoulders
        c = col(decor["shawl"])
        g.add(_blob([(-W * 0.5, top - 0.02), (W * 0.5, top - 0.02), (W * 0.52, top - 0.22), (0.0, top - 0.1),
                     (-W * 0.52, top - 0.22)], c, ink, ow * 0.8))
    if decor.get("sari"):                       # a sari's drape: from the shoulder across, its border
        c, b = col(decor["sari"]), col(decor.get("border") or "#F2C14E")
        g.add(_poly([(-W * 0.48, top - 0.02), (-W * 0.2, top - 0.02), (W * 0.5, y0 + full * 0.42),
                     (W * 0.5, y0 + full * 0.6)], _shade(c, 0.85), ink, ow * 0.7),
              line([(-W * 0.2, top - 0.02), (W * 0.5, y0 + full * 0.42)], b, ow * 2.0),
              line([(-W * 0.5, y0 + 0.02), (W * 0.5, y0 + 0.02)], b, ow * 2.6))
    if decor.get("dhoti"):                      # a white dhoti from the waist, its folds
        yb = y0 + full * 0.4
        g.add(_poly([(-W / 2, yb), (W / 2, yb), (W / 2, y0 + 0.01), (-W / 2, y0 + 0.01)], "#F7F5F0", ink, ow * 0.8),
              line([(0.0, yb), (-0.02, y0 + 0.02)], "#C9C2B2", ow),
              line([(0.05, yb), (0.07, y0 + 0.06)], "#C9C2B2", ow * 0.8))
    if decor.get("quiver"):
        g.add(_poly([(-W * 0.5, top - 0.02), (-W * 0.36, top + 0.02), (-W * 0.18, y0 + full * 0.35),
                     (-W * 0.32, y0 + full * 0.3)], "#6B4A2F", ink, ow * 0.6),
              *(line([(-W * 0.44 + i * 0.015, top), (-W * 0.48 + i * 0.015, top + 0.06)], "#F7F5F0", ow) for i in range(3)))
    return g


def on_face(decor: dict, ink, ow):
    """What is on the face (the face's frame, the face's middle at 0; it is grown with the face): glasses, an eye
    patch, a tilak."""
    g = VGroup()
    if decor.get("glasses"):
        for x in (-0.027, 0.027):
            g.add(Circle(radius=0.019, fill_opacity=0, stroke_color=ink, stroke_width=ow * 0.8).move_to([x, 0.02, 0]))
        g.add(Line([-0.008, 0.022, 0], [0.008, 0.022, 0], stroke_color=ink, stroke_width=ow * 0.8))
    if decor.get("eyepatch"):
        g.add(Ellipse(width=0.03, height=0.026, fill_color=ink, fill_opacity=1, stroke_width=0).move_to([0.027, 0.02, 0]),
              Line([-0.06, 0.06, 0], [0.06, -0.01, 0], stroke_color=ink, stroke_width=ow * 0.7))
    if decor.get("tilak"):
        g.add(Line([0.0, 0.05, 0], [0.0, 0.075, 0], stroke_color="#C9302C", stroke_width=ow * 1.8))
    return g


def plume(decor: dict, ink, ow, R):
    """A plume on a helmet (the head's frame)."""
    if not decor.get("plume"):
        return VGroup()
    c = col(decor["plume"])
    return VGroup(_blob([(-R * 0.1, R * 1.1), (-R * 0.9, R * 2.0), (-R * 1.6, R * 1.7), (-R * 0.4, R * 1.0)], c, ink, ow))
