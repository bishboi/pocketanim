"""The engine's timelines: the classic timeline (dates in proportion, periods, pictures) brought on in motion,
and four more styles. In every style each event comes on as the line says its date or its words (or one after the
other when it does not), and a later line that names an event points at it.

    track      the classic layout: the track drawn from the left, the scale's years ticking in, the periods
               sweeping along under it; each event's ring pops on the track, the lit line runs on to it, its stem
               is drawn and its date and words drop in beyond.
    ribbon     a thick band of eras (the periods, or the stretches between events) sweeping in block by block, each
               era named inside it; the events as flags planted above it.
    cards      a line across the middle; each event a card (its date on a chip, its words, its picture) hung from
               it on a short string, above and below in turn, dealt in.
    road       a winding road drawn across the board; a marker travels along it from stop to stop, each stop's sign
               springing up as it arrives.
    vertical   a line down the left; each event a row (the date large, its words beside it), a dot sliding down to
               it as it comes.
"""

from __future__ import annotations

import math

import numpy as np
from manim import (BOLD, DOWN, LEFT, RIGHT, UP, AnimationGroup, Circle, Create, Dot, FadeIn, Group, Line,
                   ImageMobject, RoundedRectangle, Triangle, UpdateFromAlphaFunc, VGroup, VMobject, linear)
from manim.utils.rate_functions import ease_out_back, ease_out_cubic, ease_out_expo, rush_from

import motion_kit as K
import pocket_lecture as pl
import timeline_dates as td

STYLES = ("track", "ribbon", "cards", "road", "vertical")


def _events(scene, events) -> list[tuple]:
    return [tuple(e) + (None,) * (3 - len(e)) for e in list(events)[:scene.TIMELINE_MOST]]


def build(scene, events, title, range_, spans, scale, style: str):
    style = style if style in STYLES else "track"
    events = _events(scene, events)
    if not events:
        return None
    if style == "track":
        return _track(scene, events, title, range_, spans, scale)
    return {"ribbon": _ribbon, "cards": _cards, "road": _road, "vertical": _vertical}[style](scene, events, title,
                                                                                             range_, spans, scale)


def _said(date, label) -> list[str]:
    return [str(x) for x in (label, date) if str(x or "").strip()]


def _on_words(scene, ev, build_) -> None:
    """An event's moment: on its words (its label first, else its date), or in its turn."""
    scene._moment(_said(ev[0], ev[1]), build_)


def _positions(events, width, range_, scale):
    """Where each event sits across `width` (centred on 0): by its year when every date is one, else evenly."""
    years = [td.year(e[0]) for e in events]
    proportional = scale != "even" and len(events) >= 2 and all(y is not None for y in years) and len(set(years)) > 1
    if not proportional:
        slot = width / max(len(events), 1)
        return [-width / 2 + slot * (k + 0.5) for k in range(len(events))], None
    lo, hi = min(years), max(years)
    if range_ and len(range_) == 2:
        a, b = td.year(range_[0]), td.year(range_[1])
        if a is not None and b is not None and b > a:
            lo, hi = a, b
    pad = max((hi - lo) * 0.06, 0.5)
    lo, hi = lo - pad, hi + pad
    return [-width / 2 + (y - lo) / (hi - lo) * width for y in years], (lo, hi)


# ---------------------------------------------------------------- track: the classic layout, in motion -------------

def _track(scene, events, title, range_, spans, scale):
    """The engine's own timeline laid out as it lays it out (pocket_lecture.big_timeline), its parts then brought on
    in order: no event is drawn until its moment."""
    captured = []
    keep = scene._to_stage

    def capture(group, *a, **k):
        captured.append(group)
        return None

    scene._to_stage = capture
    try:
        pl.MapLecture.big_timeline(scene, [e for e in events], title, range=range_, spans=spans, scale=scale)
    finally:
        scene._to_stage = keep
    if not captured:
        return None
    whole = captured[0]                      # Group(parts) -> parts = Group(drawing[, title])
    parts = whole[0]
    drawing = parts[0]
    head = parts[1] if len(parts.submobjects) > 1 else None
    track, lit = drawing[0], drawing[1]
    rest = list(drawing.submobjects[2:])
    marks = rest[-len(events):] if len(rest) >= len(events) else []
    extras = rest[:len(rest) - len(marks)]
    # The lit line: pieces from one event's node to the next, each drawn as its event comes.
    y = track.get_center()[1]
    left, right = track.get_left()[0], track.get_right()[0]
    xs = [m[0].get_center()[0] for m in marks]
    order = sorted(range(len(marks)), key=lambda k: xs[k])
    tone = pl.P.SAND
    pieces = []
    last = left
    for k in order:
        seg = Line([last, y, 0], [xs[k], y, 0], stroke_color=tone, stroke_width=4, stroke_opacity=0.95)
        pieces.append((k, seg))
        last = xs[k]
    drawing.remove(lit)
    entrance = [K.typewriter(head, run=0.7) if head is not None else None,
                K.draw(track, run=K.t("slow")),
                K.stagger([K.enter(x, "fade", run=K.t("base")) for x in extras], lag=0.3) if extras else None]
    whole.set_z_index(pl.Z_MARK + 10)
    anim = scene._show(scene._next_id("timeline"), whole, K.stagger([a for a in entrance if a is not None], lag=0.5),
                       idle=False)
    hidden = [m for m in marks] + [seg for _, seg in pieces]
    scene._hold_back(whole, hidden)
    for k, seg in pieces:
        node, stem, head_ = marks[k][0], marks[k][1], marks[k][2]

        def come(heard, node=node, stem=stem, head_=head_, seg=seg):
            return K.chain([K.draw(seg, run=K.t("fast"), sfx="swish"),
                            K.timed(FadeIn(node, scale=0.2, rate_func=ease_out_back), K.t("fast"), "pop"),
                            K.together([K.draw(stem, run=K.t("fast")),
                                        K.timed(FadeIn(head_, shift=(UP if head_.get_center()[1] > y else DOWN) * 0.4,
                                                       rate_func=ease_out_back), K.t("base"))])])
        _on_words(scene, events[k], come)
    return anim


# ---------------------------------------------------------------- ribbon ------------------------------------------

def _ribbon(scene, events, title, range_, spans, scale):
    P = pl.P
    cx, cy, w, h = scene.STAGE
    width = w - 0.8
    xs, span_years = _positions(events, width, range_, scale)
    tones = [getattr(P, t_) for t_ in scene.SPAN_TONES]
    blocks = []
    if spans and span_years:
        lo, hi = span_years
        for k, sp in enumerate(spans[:6]):
            a, b = td.year(sp[0]), td.year(sp[1])
            if a is None or b is None:
                continue
            x0 = -width / 2 + (min(a, b) - lo) / (hi - lo) * width
            x1 = -width / 2 + (max(a, b) - lo) / (hi - lo) * width
            blocks.append((x0, x1, str(sp[2]) if len(sp) > 2 else "", tones[k % len(tones)]))
    if not blocks:
        # No periods given: the band is cut into the stretches between the events, unnamed (an event is a moment,
        # not an era: named after the events, the band only said the flags' words again, squeezed small).
        edges = [-width / 2] + [(a + b) / 2 for a, b in zip(xs, xs[1:])] + [width / 2]
        blocks = [(edges[k], edges[k + 1], "", tones[k % len(tones)]) for k in range(len(events))]
    band_h = 1.1
    band = VGroup()
    for x0, x1, name, tone in blocks:
        rect = RoundedRectangle(corner_radius=0.06, width=max(0.1, x1 - x0 - 0.04), height=band_h, stroke_width=0,
                                fill_color=tone, fill_opacity=0.92).move_to([(x0 + x1) / 2, 0, 0])
        word = pl.T((name.upper() if pl.TH.get("upper") else name) or " ", 26, P.BG, weight=BOLD, font=K.font("head"))
        if word.width > rect.width - 0.2:
            word.scale_to_fit_width(max(0.2, rect.width - 0.2))
        word.move_to(rect)
        band.add(VGroup(rect, word))
    tags = []
    for date, label, pic in events:
        chip = pl.ui_chip(str(date), K.col("accent"), 26)
        words = pl.fit(pl.T(pl.wrap(str(label), 18), 24, P.CREAM, weight=BOLD), 3.0)
        tags.append(VGroup(chip, words).arrange(DOWN, buff=0.08, aligned_edge=LEFT))
    # A thin axis the whole width under the band: a flag outside every period (a date after the last one) stands
    # on it, not on nothing.
    spans_x = sorted((x0, x1) for x0, x1, _, _ in blocks)
    axis = VGroup()
    at = -width / 2 - 0.15
    for x0, x1 in [*spans_x, (width / 2 + 0.15, width / 2 + 0.15)]:
        if x0 - at > 0.05:
            axis.add(Line([at, 0, 0], [x0, 0, 0], stroke_color=P.MUTED, stroke_width=3))
        at = max(at, x1)
    flags = [VGroup(pole, tag) for pole, tag in _plant(xs, tags, band_h / 2, -band_h / 2, width, P.CREAM,
                                                     inside=lambda x: any(a - 0.02 <= x <= b + 0.02 for a, b in spans_x))]
    body = VGroup(axis, band, *flags)
    whole, top = scene._titled(body, title, None)
    scene._fit(whole, scene._box(), grow=1.15)
    entrance = K.stagger([scene._title_in(top), K.draw(axis, run=K.t("base")) if len(axis) else None,
                          K.stagger([K.chain([K.grow_from(b[0], LEFT, run=K.t("base")),
                                              K.enter(b[1], "pop", run=K.t("fast"))]) for b in band], lag=0.35)],
                         lag=0.5)
    anim = scene._show(scene._next_id("timeline"), whole, entrance, idle=False)
    scene._hold_back(whole, flags)
    for k, f in enumerate(flags):
        def plant(heard, f=f):
            up = f[1].get_center()[1] > f[0].get_start()[1]
            return K.chain([K.grow_from(f[0], DOWN if up else UP, run=K.t("fast")),
                            K.timed(FadeIn(f[1], shift=(DOWN if up else UP) * 0.3, rate_func=ease_out_back), K.t("base"),
                                    "pop")])
        _on_words(scene, events[k], plant)
        for s in _said(events[k][0], events[k][1]):
            scene._part("tl", s, f)
    return anim


def _plant(xs, tags, top: float, bottom: float, width: float, colour, inside=None) -> list:
    """Each event's flag placed beside the band: its pole from the band's edge at its x, its tag at the pole's end.
    Tried above the band and below it, ever further out, each to the right of its pole or (near the right end) to
    its left, and put where its tag touches no tag already placed, its pole crosses none, and no pole crosses it.
    Each flag was laid on the first level whose last tag it cleared: a later, higher pole ran up through the tags
    under it, and the tags piled up over each other near the end of the band."""
    row = max((t.height for t in tags), default=0.5) + 0.22
    gap = 0.1
    boxes: list[tuple] = []          # (x0, y0, x1, y1) of each tag placed
    poles: list[tuple] = []          # (x, y0, y1) of each pole placed
    out = []

    def clear(box, pole) -> bool:
        x0, y0, x1, y1 = box
        if x0 < -width / 2 - 0.3 or x1 > width / 2 + 0.3:
            return False
        for a0, b0, a1, b1 in boxes:
            if x0 < a1 + gap and x1 > a0 - gap and y0 < b1 + gap and y1 > b0 - gap:
                return False
            px, p0, p1 = pole
            if a0 - gap < px < a1 + gap and min(p0, p1) < b1 and max(p0, p1) > b0:
                return False
        for px, p0, p1 in poles:
            if x0 - gap < px < x1 + gap and min(p0, p1) < y1 and max(p0, p1) > y0:
                return False
        return True

    order = sorted(range(len(tags)), key=lambda k: xs[k])
    placed: dict[int, tuple] = {}
    for k in order:
        x, tag = xs[k], tags[k]
        tw, th = tag.width, tag.height
        choice = None
        for level in range(8):
            for up in (True, False):
                lift = 0.45 + level * row
                y_base = top + lift if up else bottom - lift
                y0, y1 = (y_base, y_base + th) if up else (y_base - th, y_base)
                for right in (True, False):
                    x0 = x - 0.04 if right else x + 0.04 - tw
                    box = (x0, y0, x0 + tw, y1)
                    pole = (x, top if up else bottom, y_base)
                    if clear(box, pole):
                        choice = (box, pole, up)
                        break
                if choice:
                    break
            if choice:
                break
        if choice is None:
            # Nowhere clear (a crowded band): the next level out above, on its own.
            lift = 0.45 + len(boxes) * row
            box = (x - 0.04, top + lift, x - 0.04 + tw, top + lift + th)
            choice = (box, (x, top, top + lift), True)
        box, pole, up = choice
        boxes.append(box)
        poles.append(pole)
        placed[k] = choice
    for k in range(len(tags)):
        box, pole, up = placed[k]
        tag = tags[k]
        tag.move_to([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2, 0])
        # From the band's edge; from the axis (y = 0) where no period lies under it.
        start = pole[1] if inside is None or inside(pole[0]) else 0.0
        stick = Line([pole[0], start, 0], [pole[0], pole[2], 0], stroke_color=colour, stroke_width=3)
        out.append((stick, tag))
    return out


# ---------------------------------------------------------------- cards --------------------------------------------

def _cards(scene, events, title, range_, spans, scale):
    P = pl.P
    cx, cy, w, h = scene.STAGE
    width = w - 0.6
    n = len(events)
    xs, _ = _positions(events, width, range_, "even")
    cw = min(2.5, width / n * 1.7 - 0.2) if n > 4 else min(2.6, width / n - 0.25)
    line = Line([-width / 2, 0, 0], [width / 2, 0, 0], stroke_color=P.MUTED, stroke_width=3)
    cards = []
    for k, (date, label, pic) in enumerate(events):
        up = k % 2 == 0 if n > 4 else False
        chip = pl.ui_chip(str(date), K.col("accent"), 26, K.col("accent_ink"))
        words = pl.fit(pl.T(pl.wrap(str(label), 16), 24, K.col("card_ink"), weight=BOLD), cw - 0.3)
        inner = [chip, words]
        img = scene._picture(pic, 1.1, cw - 0.3, motion="none") if pic else None
        if img is not None:
            inner.append(img)
        content = K.group_of(*inner).arrange(DOWN, buff=0.12)
        face = K.card(cw, content.height + 0.4)
        content.move_to(face.face)
        card = K.group_of(face, content)
        gap = 0.45
        card.move_to([xs[k], (gap + card.height / 2) * (1 if up else -1), 0])
        string = Line([xs[k], 0, 0], [xs[k], (gap) * (1 if up else -1), 0], stroke_color=P.MUTED, stroke_width=2)
        pin = Dot([xs[k], 0, 0], radius=0.08, color=K.col("accent"))
        card.rotate((2.5 if k % 2 else -2.5) * math.pi / 180)
        cards.append(K.group_of(string, pin, card))
    body = K.group_of(line, *cards)
    whole, top = scene._titled(body, title, None)
    scene._fit(whole, scene._box(), grow=1.1)
    entrance = K.stagger([scene._title_in(top), K.draw(line, run=K.t("slow"))], lag=0.5)
    anim = scene._show(scene._next_id("timeline"), whole, entrance, idle=False)
    scene._hold_back(whole, cards)
    for k, c in enumerate(cards):
        string, pin, card = c[0], c[1], c[2]

        def hang(heard, string=string, pin=pin, card=card):
            down = card.get_center()[1] < string.get_start()[1]
            return K.chain([K.timed(FadeIn(pin, scale=0.2, rate_func=ease_out_back), K.t("fast"), "pop"),
                            K.together([K.draw(string, run=K.t("fast")),
                                        K.timed(FadeIn(card, shift=(DOWN if down else UP) * 0.8, rate_func=ease_out_back),
                                                K.t("base"), "swish")])])
        _on_words(scene, events[k], hang)
        for s in _said(events[k][0], events[k][1]):
            scene._part("tl", s, card)
    return anim


# ---------------------------------------------------------------- road --------------------------------------------

def _road(scene, events, title, range_, spans, scale):
    P = pl.P
    cx, cy, w, h = scene.STAGE
    width = w - 1.2
    n = len(events)
    amp = 0.9

    def at(s):
        x = -width / 2 + s * width
        return np.array([x, amp * math.sin(s * math.pi * 2.2 + 0.4), 0])

    samples = [at(s) for s in np.linspace(0, 1, 90)]
    road = VMobject(stroke_color=pl._tint_on_bg(P.MUTED, 0.6), stroke_width=26).set_points_smoothly(samples)
    centre = VMobject(stroke_color=P.BG, stroke_width=3).set_points_smoothly(samples)
    from manim import DashedVMobject

    dashes = DashedVMobject(centre, num_dashes=40)
    xs, _ = _positions(events, 1.0, range_, scale)
    shares = [min(0.98, max(0.02, x + 0.5)) for x in xs]
    stops = []
    for k, (date, label, pic) in enumerate(events):
        p = at(shares[k])
        up = math.cos(shares[k] * math.pi * 2.2 + 0.4) <= 0 if False else (k % 2 == 0)
        pin = VGroup(Circle(radius=0.2, stroke_color=P.BG, stroke_width=4, fill_color=K.col("accent"),
                            fill_opacity=1)).move_to(p)
        chip = pl.ui_chip(str(date), K.col("second") if not K.M.get("classic") else P.RIVER, 24)
        words = pl.fit(pl.T(pl.wrap(str(label), 16), 24, P.CREAM, weight=BOLD), 2.8)
        sign = VGroup(chip, words).arrange(DOWN, buff=0.08)
        sign.next_to(pin, UP if up else DOWN, buff=0.3)
        stops.append(VGroup(pin, sign))
    walker = VGroup(Circle(radius=0.17, stroke_width=0, fill_color=K.col("stamp"), fill_opacity=1),
                    Circle(radius=0.3, stroke_width=0, fill_color=K.col("stamp"), fill_opacity=0.25))
    walker.move_to(at(0))
    body = VGroup(road, dashes, *stops, walker)
    whole, top = scene._titled(body, title, None)
    scene._fit(whole, scene._box(), grow=1.1)
    entrance = K.stagger([scene._title_in(top), K.together([K.draw(road, run=K.t("slow") * 1.4),
                                                            K.draw(dashes, run=K.t("slow") * 1.4)]),
                          K.enter(walker, "pop", run=K.t("fast"))], lag=0.5)
    anim = scene._show(scene._next_id("timeline"), whole, entrance, idle=False)
    scene._hold_back(whole, stops)
    # The walker goes on along the road to each stop as it comes (baked: a dot following a curve).
    state = {"s": 0.0}
    for k, stop in enumerate(stops):
        def arrive(heard, k=k, stop=stop):
            s0, s1 = state["s"], shares[k]
            state["s"] = max(s0, s1)
            p0 = road.point_from_proportion(_proportion(road, s0))
            run = K.t("slow")

            def walk(mob, alpha, s0=s0, s1=s1):
                s = s0 + (s1 - s0) * ease_out_cubic(alpha)
                mob.move_to(road.point_from_proportion(_proportion(road, s)))
            moving = K.baked(K.timed(UpdateFromAlphaFunc(walker, walk, rate_func=linear), run, "swish"))
            pin, sign = stop[0], stop[1]
            return K.chain([moving, K.timed(FadeIn(pin, scale=0.3, rate_func=ease_out_back), K.t("fast"), "pop"),
                            K.spring_in(sign, run=K.t("slow"))])
        _on_words(scene, events[k], arrive)
        for s in _said(events[k][0], events[k][1]):
            scene._part("tl", s, stop)
    return anim


def _proportion(path, share: float) -> float:
    """The share along a road (0..1 across the board) as a share of the road's length (its curve is not even)."""
    return min(1.0, max(0.0, share))


# ---------------------------------------------------------------- vertical ----------------------------------------

def _vertical(scene, events, title, range_, spans, scale):
    P = pl.P
    n = len(events)
    gap = min(1.0, 5.0 / max(n, 1))
    rows = []
    for k, (date, label, pic) in enumerate(events):
        year = K.number(str(date), 34, K.col("accent"))
        words = pl.fit(K.body(str(label), 24, P.CREAM, 44), 6.5)
        rows.append((year, words))
    date_w = max(r[0].width for r in rows)
    spine_x = date_w + 0.45
    marks = []
    for k, (year, words) in enumerate(rows):
        yy = -k * gap
        year.move_to([date_w, yy, 0], aligned_edge=RIGHT)
        dot = Dot([spine_x, yy, 0], radius=0.1, color=K.col("accent"))
        words.move_to([spine_x + 0.4, yy, 0], aligned_edge=LEFT)
        marks.append(VGroup(year, dot, words))
    spine = Line([spine_x, 0.35, 0], [spine_x, -(n - 1) * gap - 0.35, 0], stroke_color=P.MUTED, stroke_width=3)
    head = Dot([spine_x, 0.35, 0], radius=0.14, color=K.col("stamp"))
    body = VGroup(spine, *marks, head)
    whole, top = scene._titled(body, title, None)
    scene._fit(whole, scene._box(), grow=1.1, margin=0.8)
    entrance = K.stagger([scene._title_in(top), K.draw(spine, run=K.t("slow")), K.enter(head, "pop", run=K.t("fast"))],
                         lag=0.5)
    anim = scene._show(scene._next_id("timeline"), whole, entrance, idle=False)
    scene._hold_back(whole, marks)
    for k, m in enumerate(marks):
        def come(heard, m=m):
            slide = K.move_to(head, m[1].get_center(), run=K.t("base"), rate=ease_out_cubic)
            return K.chain([slide, K.together([K.timed(FadeIn(m[0], shift=RIGHT * 0.4, rate_func=ease_out_expo), K.t("base"), "swish"),
                                               K.timed(FadeIn(m[1], scale=0.2, rate_func=ease_out_back), K.t("fast")),
                                               K.timed(FadeIn(m[2], shift=LEFT * 0.4, rate_func=ease_out_expo), K.t("base"))])])
        _on_words(scene, events[k], come)
        for s in _said(events[k][0], events[k][1]):
            scene._part("tl", s, m)
    return anim
