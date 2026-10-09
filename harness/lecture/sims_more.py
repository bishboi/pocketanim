"""More live pictures for the `sim` op (live.py has the first ten): simulations for physics, chemistry, biology,
mathematics, geography and economics, and the board's teaching formats that build up while a line is said
(manipulatives for primary maths, geometry constructions, a balance scale for equations, a timeline that zooms,
data stories, a cross-section that peels, flip cards of differences).

Each builder draws into a box and returns a live.Live, exactly as live.py's do: `step(t, p)` puts the picture in
its state t seconds into the line and p (0 to 1) of the way through it. A "loop" runs on t (a pendulum swinging),
a "process" on p and ends where the line ends (a Punnett square filling in). The exporter bakes the motion into
clips the phone plays as vectors. Motion is deterministic (seeded), so a build is the same every time.
"""

from __future__ import annotations

import math
import re

import numpy as np



# live.py merges this module's sims into its own at import; so this module reaches into live.py only when a picture
# is built, and either can be imported first.
def Live(*args, **kwargs):  # noqa: N802 -- stands in for live.Live
    from live import Live as _Live

    return _Live(*args, **kwargs)


def _frame(*args, **kwargs):
    from live import _frame as frame

    return frame(*args, **kwargs)


def _readout(*args, **kwargs):
    from live import _readout as readout

    return readout(*args, **kwargs)

ORIGIN3 = np.zeros(3)
UP3, DOWN3, LEFT3, RIGHT3 = (np.array(v, dtype=float) for v in ([0, 1, 0], [0, -1, 0], [-1, 0, 0], [1, 0, 0]))


def _pl():
    import pocket_lecture as pl

    return pl


def _part(p: float, a: float, b: float) -> float:
    """How far p is through the stretch a..b of the line (0 before, 1 after)."""
    return float(min(1.0, max(0.0, (p - a) / max(b - a, 1e-9))))


def _ease(x: float) -> float:
    return x * x * (3 - 2 * x)


def _pt(x: float, y: float) -> np.ndarray:
    return np.array([float(x), float(y), 0.0])


def _tones():
    pl = _pl()
    return [pl.P.RIVER, pl.P.ROSE, pl.P.GOLD, pl.P.GREEN, pl.P.VIOLET, pl.P.TEAL, pl.P.TERRA, pl.P.SAND]


def _show(mob, on: bool, opacity: float = 1.0) -> None:
    """Show or hide a part without taking it off the picture (a clip keeps the same members every frame). Shown
    again, each piece gets back its own opacity (a translucent fill stays translucent), times `opacity`."""
    for part in mob.get_family():
        kept = getattr(part, "_panim_alpha", None)
        if kept is None:
            try:
                kept = (float(part.get_fill_opacity()), float(part.get_stroke_opacity()))
            except Exception:  # noqa: BLE001 -- a part without colours
                continue
            part._panim_alpha = kept
        part.set_fill(opacity=kept[0] * opacity if on else 0.0, family=False)
        part.set_stroke(opacity=kept[1] * opacity if on else 0.0, family=False)


_SUBS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def formula(text: str) -> str:
    """H2O as H₂O: digits after an element or a bracket become subscripts (a leading coefficient stays)."""
    return re.sub(r"(?<=[A-Za-z)\]])(\d+)", lambda m: m.group(1).translate(_SUBS), str(text))


def _along(points: list, s: float) -> np.ndarray:
    """The point a fraction s of the way along a polyline."""
    pts = [np.asarray(p, dtype=float) for p in points]
    lengths = [float(np.linalg.norm(b - a)) for a, b in zip(pts, pts[1:])]
    total = sum(lengths) or 1.0
    goal = (s % 1.0) * total
    for (a, b), length in zip(zip(pts, pts[1:]), lengths):
        if goal <= length:
            return a + (b - a) * (goal / max(length, 1e-9))
        goal -= length
    return pts[-1]


def _partial(mob, full, f: float) -> None:
    """`mob` as the first fraction f of `full` (a line or an arc being drawn)."""
    f = min(1.0, max(0.0, f))
    if f <= 0.0:
        mob.set_points(np.zeros((0, 3)))
        return
    mob.pointwise_become_partial(full, 0.0, f)


# ================================================================= physics

def pendulum_period(params: dict, box) -> Live:
    """Pendulums of different lengths side by side: the longer swings slower (T = 2π√(L/g))."""
    from manim import Dot, Line, VGroup

    pl = _pl()
    cx, cy, w, h = box
    lengths = [float(x) for x in (params.get("lengths") or [0.5, 1.0, 2.0])][:4]
    g = float(params.get("g") or 9.8)
    amp = math.radians(float(params.get("angle") or 18))
    top = cy + h * 0.36
    longest = max(lengths)
    scale = h * 0.5 / longest
    tones = _tones()
    support = Line(_pt(cx - w * 0.42, top), _pt(cx + w * 0.42, top), color=pl.P.MUTED, stroke_width=6)
    title = pl.T("T = 2π √(L / g)", 24, pl.P.GOLD).move_to(_pt(cx, top + 0.4))
    swings = []
    group = VGroup(support, title)
    for i, length in enumerate(lengths):
        x = cx - w * 0.36 + w * 0.72 * (i + 0.5) / len(lengths)
        pivot = _pt(x, top)
        r = length * scale
        string = Line(pivot, pivot + _pt(0, -r), color=pl.P.CREAM, stroke_width=3)
        bob = Dot(pivot + _pt(0, -r), radius=0.17, color=tones[i % len(tones)])
        period = 2 * math.pi * math.sqrt(length / g)
        label = pl.T(f"L = {length:g} m   T = {period:.1f} s", 18, tones[i % len(tones)])
        label.move_to(_pt(x, top - longest * scale - 0.6))
        group.add(string, bob, label)
        swings.append((pivot, r, period, string, bob))

    def step(t: float, p: float) -> None:
        for pivot, r, period, string, bob in swings:
            angle = amp * math.cos(2 * math.pi * t / period)
            end = pivot + r * _pt(math.sin(angle), -math.cos(angle))
            string.put_start_and_end_on(pivot, end)
            bob.move_to(end)

    step(0.0, 0.0)
    return Live(group, step, "loop")


def projectile_angle(params: dict, box) -> Live:
    """Balls launched at several angles one after another, each path left drawn: 45° goes farthest, and angles
    that add to 90° land together."""
    from manim import Dot, Line, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    angles = [float(a) for a in (params.get("angles") or [15, 30, 45, 60, 75])][:6]
    u = float(params.get("speed") or 20.0)
    g = float(params.get("g") or 9.8)
    ranges = [u * u * math.sin(2 * math.radians(a)) / g for a in angles]
    heights = [(u * math.sin(math.radians(a))) ** 2 / (2 * g) for a in angles]
    scale = min(w * 0.6 / max(ranges), h * 0.6 / max(heights))
    x0, y0 = cx - w * 0.42, cy - h * 0.32
    ground = Line(_pt(x0 - 0.2, y0), _pt(x0 + w * 0.66, y0), color=pl.P.MUTED, stroke_width=4)
    tones = _tones()
    paths, legend, ball = [], VGroup(), Dot(radius=0.12, color=pl.P.CREAM)
    group = VGroup(ground)
    for i, a in enumerate(angles):
        path = VMobject(stroke_color=tones[i % len(tones)], stroke_width=4)
        paths.append(path)
        group.add(path)
        row = pl.T(f"{a:g}°   R = {ranges[i]:.1f} m", 20, tones[i % len(tones)])
        row.move_to(_pt(cx + w * 0.34, cy + h * 0.3 - i * 0.48))
        legend.add(row)
    note = pl.T(f"u = {u:g} m/s", 20, pl.P.MUTED).move_to(_pt(cx + w * 0.34, cy + h * 0.3 - len(angles) * 0.48))
    group.add(legend, note, ball)

    def flight(i: int, f: float) -> list:
        a = math.radians(angles[i])
        total = 2 * u * math.sin(a) / g
        ts = np.linspace(0, total * f, max(2, int(40 * f) + 2))
        return [_pt(x0 + scale * u * math.cos(a) * s, y0 + scale * (u * math.sin(a) * s - g * s * s / 2)) for s in ts]

    def step(t: float, p: float) -> None:
        n = len(angles)
        for i in range(n):
            f = _part(p, i / n, (i + 0.9) / n)
            if f > 0:
                pts = flight(i, f)
                paths[i].set_points_as_corners(pts)
                if f < 1:
                    ball.move_to(pts[-1])
            else:
                paths[i].set_points_as_corners([_pt(x0, y0), _pt(x0 + 1e-3, y0)])
            legend[i].set_opacity(1.0 if f >= 1 else 0.25)

    step(0.0, 0.0)
    return Live(group, step, "process")


def _rect_path(cx, cy, w, h):
    return [_pt(cx - w / 2, cy - h / 2), _pt(cx - w / 2, cy + h / 2), _pt(cx + w / 2, cy + h / 2),
            _pt(cx + w / 2, cy - h / 2), _pt(cx - w / 2, cy - h / 2)]


def _bulb(at, brightness: float):
    from manim import Circle, Line, VGroup

    pl = _pl()
    glow = Circle(radius=0.42, stroke_width=0, fill_color=pl.P.GOLD, fill_opacity=0.15 + 0.6 * brightness).move_to(at)
    glass = Circle(radius=0.26, color=pl.P.CREAM, stroke_width=3, fill_color=pl.P.GOLD,
                   fill_opacity=0.2 + 0.75 * brightness).move_to(at)
    cross = VGroup(Line(at + _pt(-0.18, -0.18), at + _pt(0.18, 0.18)), Line(at + _pt(-0.18, 0.18), at + _pt(0.18, -0.18)))
    cross.set_stroke(pl.P.CREAM, 2)
    return VGroup(glow, glass, cross)


def _cell(at):
    from manim import Line, VGroup

    pl = _pl()
    return VGroup(Line(at + _pt(-0.3, 0.12), at + _pt(0.3, 0.12), color=pl.P.CREAM, stroke_width=5),
                  Line(at + _pt(-0.16, -0.12), at + _pt(0.16, -0.12), color=pl.P.CREAM, stroke_width=5))


def circuit_brightness(params: dict, box) -> Live:
    """The same two bulbs in series and in parallel: in series each gets half the voltage and glows dim; in
    parallel each gets all of it and glows bright, and four times the current flows from the cell."""
    from manim import Dot, Line, Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    volts = float(params.get("voltage") or 6)
    cw, ch = w * 0.38, h * 0.5
    group = VGroup()
    dots = []
    for side, kind in ((-1, "series"), (1, "parallel")):
        ox, oy = cx + side * w * 0.24, cy + 0.15
        frame = Rectangle(width=cw, height=ch, color=pl.P.MUTED, stroke_width=4).move_to(_pt(ox, oy))
        cell = _cell(_pt(ox - cw / 2, oy))
        gap = Line(_pt(ox - cw / 2, oy - 0.2), _pt(ox - cw / 2, oy + 0.2), color=pl.P.BG, stroke_width=10)
        group.add(frame, gap, cell)
        if kind == "series":
            for k in (-1, 1):
                group.add(_bulb(_pt(ox + k * cw * 0.22, oy + ch / 2), 0.25))
            note = f"series: each bulb {volts / 2:g} V, dim"
            routes = [_rect_path(ox, oy, cw, ch)]
            speeds = [0.12]
        else:
            rung = Line(_pt(ox - cw / 2, oy), _pt(ox + cw / 2, oy), color=pl.P.MUTED, stroke_width=4)
            group.add(rung, _bulb(_pt(ox, oy + ch / 2), 1.0), _bulb(_pt(ox, oy), 1.0))
            note = f"parallel: each bulb {volts:g} V, bright"
            routes = [_rect_path(ox, oy, cw, ch),
                      [_pt(ox - cw / 2, oy - ch / 2), _pt(ox - cw / 2, oy), _pt(ox + cw / 2, oy), _pt(ox + cw / 2, oy - ch / 2),
                       _pt(ox - cw / 2, oy - ch / 2)]]
            speeds = [0.24, 0.24]
        group.add(pl.T(kind.capitalize(), 24, pl.P.GOLD).move_to(_pt(ox, oy + ch / 2 + 0.7)))
        group.add(pl.T(note, 18, pl.P.CREAM).move_to(_pt(ox, oy - ch / 2 - 0.45)))
        for route, speed in zip(routes, speeds):
            for k in range(6):
                dot = Dot(radius=0.06, color=pl.P.RIVER)
                group.add(dot)
                dots.append((dot, route, speed, k / 6))

    def step(t: float, p: float) -> None:
        for dot, route, speed, phase in dots:
            dot.move_to(_along(route, phase + speed * t))

    step(0.0, 0.0)
    return Live(group, step, "loop")


def magnetic_wire(params: dict, box) -> Live:
    """A wire seen end on, its current out of the page: the field is circles round it, running anticlockwise
    (the right-hand rule), weaker farther out; compass needles line up along them."""
    from manim import Circle, Dot, Line, Polygon, VGroup

    pl = _pl()
    cx, cy, w, h = box
    out = str(params.get("current") or "out") != "in"
    centre = _pt(cx, cy)
    wire = Circle(radius=0.28, color=pl.P.CREAM, stroke_width=4, fill_color=pl.P.TERRA, fill_opacity=0.6).move_to(centre)
    mark = Dot(centre, radius=0.07, color=pl.P.CREAM) if out else VGroup(
        Line(centre + _pt(-0.15, -0.15), centre + _pt(0.15, 0.15)), Line(centre + _pt(-0.15, 0.15), centre + _pt(0.15, -0.15))
    ).set_stroke(pl.P.CREAM, 4)
    radii = [0.7, 1.2, 1.75, min(w, h) * 0.42]
    rings = VGroup(*[Circle(radius=r, color=pl.P.MUTED, stroke_width=2).move_to(centre) for r in radii])
    sign = 1 if out else -1
    heads = []
    group = VGroup(rings, wire, mark)
    for r in radii:
        for k in range(4):
            tip = Polygon(_pt(0.14, 0), _pt(-0.1, 0.09), _pt(-0.1, -0.09), stroke_width=0, fill_color=pl.P.RIVER,
                          fill_opacity=1)
            group.add(tip)
            heads.append((tip, r, k * math.pi / 2))
    needles = []
    for k in range(8):
        angle = k * math.pi / 4 + math.pi / 8
        at = centre + 2.3 * _pt(math.cos(angle), math.sin(angle)) if min(w, h) * 0.42 > 2.4 else centre + 1.45 * _pt(
            math.cos(angle), math.sin(angle))
        north = Line(at, at, color=pl.P.ROSE, stroke_width=6)
        south = Line(at, at, color=pl.P.CREAM, stroke_width=6)
        group.add(north, south)
        needles.append((at, angle, north, south))
    note = pl.T("current out of the page" if out else "current into the page", 20, pl.P.GOLD)
    note.move_to(_pt(cx, cy - h * 0.46))
    group.add(note)

    def step(t: float, p: float) -> None:
        for tip, r, phase in heads:
            angle = phase + sign * t * 0.9 / r
            tip.become(Polygon(_pt(0.14, 0), _pt(-0.1, 0.09), _pt(-0.1, -0.09), stroke_width=0, fill_color=pl.P.RIVER,
                               fill_opacity=1).rotate(angle + sign * math.pi / 2, about_point=ORIGIN3)
                       .move_to(centre + r * _pt(math.cos(angle), math.sin(angle))))
        for at, angle, north, south in needles:
            d = sign * _pt(-math.sin(angle), math.cos(angle)) * 0.22
            north.put_start_and_end_on(at, at + d)
            south.put_start_and_end_on(at - d, at)

    step(0.0, 0.0)
    return Live(group, step, "loop")


def lens_image(params: dict, box) -> Live:
    """An object moving toward a convex lens, and its image found by two rays: beyond 2F small, real and upside
    down; at 2F the same size; between F and 2F bigger; inside F virtual, upright and bigger."""
    from manim import Ellipse, Line, VGroup

    pl = _pl()
    cx, cy, w, h = box
    f = w * 0.12
    u0 = float(params.get("from_u") or -3.0) * f
    u1 = float(params.get("to_u") or -0.6) * f
    h0 = min(h * 0.2, 0.9)
    axis = Line(_pt(cx - w / 2 + 0.1, cy), _pt(cx + w / 2 - 0.1, cy), color=pl.P.MUTED, stroke_width=2)
    lens = Ellipse(width=0.36, height=h * 0.62, color=pl.P.RIVER, stroke_width=3, fill_color=pl.P.RIVER,
                   fill_opacity=0.2).move_to(_pt(cx, cy))
    marks = VGroup()
    for k, name in ((-2, "2F"), (-1, "F"), (1, "F"), (2, "2F")):
        x = cx + k * f
        marks.add(Line(_pt(x, cy - 0.1), _pt(x, cy + 0.1), color=pl.P.MUTED, stroke_width=3),
                  pl.T(name, 16, pl.P.MUTED).move_to(_pt(x, cy - 0.32)))
    obj = Line(_pt(0, 0), _pt(0, 1), color=pl.P.GOLD, stroke_width=6).add_tip(tip_length=0.2)
    img = Line(_pt(0, 0), _pt(0, 1), color=pl.P.ROSE, stroke_width=6).add_tip(tip_length=0.2)
    ray1a = Line(ORIGIN3, RIGHT3, color=pl.P.GOLD, stroke_width=3)
    ray1b = Line(ORIGIN3, RIGHT3, color=pl.P.GOLD, stroke_width=3)
    ray2 = Line(ORIGIN3, RIGHT3, color=pl.P.GOLD, stroke_width=3)
    back1 = Line(ORIGIN3, RIGHT3, color=pl.P.GOLD, stroke_width=2, stroke_opacity=0.5)
    back2 = Line(ORIGIN3, RIGHT3, color=pl.P.GOLD, stroke_width=2, stroke_opacity=0.5)
    read, put = _readout(" ", 20, pl.P.CREAM)
    kind, put_kind = _readout(" ", 22, pl.P.ROSE)
    group = VGroup(axis, lens, marks, ray1a, ray1b, ray2, back1, back2, obj, img, read, kind)
    left, right = cx - w / 2 + 0.15, cx + w / 2 - 0.15

    def arrow(mob, x, height):
        tip = 0.2 if abs(height) > 0.25 else max(abs(height) * 0.6, 0.05)
        new = Line(_pt(x, cy), _pt(x, cy + height if abs(height) > 1e-3 else cy + 1e-3), stroke_width=6,
                   color=mob.get_color()).add_tip(tip_length=tip)
        mob.become(new)

    def ray_to_edge(start, through, edge_x):
        """Along start -> through until the ray reaches edge_x or the top or bottom of the box."""
        d = through - start
        if abs(d[0]) < 1e-9:
            return through
        s = (edge_x - start[0]) / d[0]
        if abs(d[1]) > 1e-9:
            limit = (cy + h / 2 - 0.1 if d[1] * s > 0 else cy - h / 2 + 0.1) - start[1]
            s = min(s, limit / d[1]) if (limit / d[1]) > 0 else s
        return start + d * s

    def step(t: float, p: float) -> None:
        u = u0 + (u1 - u0) * _ease(p)
        xo = cx + u
        top = _pt(xo, cy + h0)
        arrow(obj, xo, h0)
        inv = 1 / f + 1 / u
        lens_hit = _pt(cx, cy + h0)
        ray1a.put_start_and_end_on(top, lens_hit)
        focus = _pt(cx + f, cy)
        ray1b.put_start_and_end_on(lens_hit, ray_to_edge(lens_hit, focus, right))
        ray2.put_start_and_end_on(top, ray_to_edge(top, _pt(cx, cy), right))
        if abs(inv) < 1e-3:
            _show(img, False), _show(back1, False), _show(back2, False)
            put("u = %.1f f, image at infinity" % (u / f), _pt(cx, cy + h * 0.42))
            put_kind("rays leave parallel: no image", _pt(cx, cy - h * 0.42))
            return
        v = 1 / inv
        m = v / u
        hi = m * h0
        xi = cx + v
        visible = left < xi < right and abs(hi) < h * 0.45
        if visible:
            arrow(img, xi, hi)
        _show(img, visible)
        virtual = v < 0
        if virtual:
            back1.put_start_and_end_on(lens_hit, ray_to_edge(lens_hit, focus, max(left, xi)))
            back2.put_start_and_end_on(top, ray_to_edge(top, _pt(cx, cy), max(left, xi)))
        _show(back1, virtual, 0.5), _show(back2, virtual, 0.5)
        size = "magnified" if abs(m) > 1.05 else "diminished" if abs(m) < 0.95 else "same size"
        put(f"u = {u / f:.1f} f    v = {v / f:.1f} f    m = {m:.1f}", _pt(cx, cy + h * 0.42))
        put_kind(("virtual, upright, " if virtual else "real, inverted, ") + size, _pt(cx, cy - h * 0.42))

    step(0.0, 0.0)
    return Live(group, step, "process")


def sound(params: dict, box) -> Live:
    """Sound as a longitudinal wave: air particles bunch into compressions and spread into rarefactions that travel
    away from the speaker, while each particle only moves back and forth; the pressure wave drawn below."""
    from manim import Dot, Line, Polygon, VGroup, VMobject

    pl = _pl()
    x0, x1, y0, y1 = _frame(box, 0.4)
    lam = float(params.get("wavelength") or (x1 - x0) / 3)
    speed = float(params.get("speed") or 1.2)
    k = 2 * math.pi / lam
    omega = k * speed
    amp = lam / 10
    rows, cols = 6, 34
    top, bottom = y1 - 0.2, y0 + (y1 - y0) * 0.42
    speaker = Polygon(_pt(x0, top - 0.6), _pt(x0 + 0.35, top - 0.3), _pt(x0 + 0.35, bottom + 0.3), _pt(x0, bottom + 0.6),
                      color=pl.P.CREAM, stroke_width=3, fill_color=pl.P.MUTED, fill_opacity=0.5)
    start = x0 + 0.6
    xs = np.linspace(start, x1, cols)
    ys = np.linspace(bottom, top, rows)
    dots = VGroup(*[Dot(_pt(x, y), radius=0.05, color=pl.P.RIVER) for y in ys for x in xs])
    mid = y0 + (y1 - y0) * 0.18
    axis = Line(_pt(start, mid), _pt(x1, mid), color=pl.P.MUTED, stroke_width=2)
    pressure = VMobject(stroke_color=pl.P.GOLD, stroke_width=4)
    c_tag = pl.T("compression", 18, pl.P.GOLD)
    r_tag = pl.T("rarefaction", 18, pl.P.MUTED)
    label = pl.T("pressure", 16, pl.P.MUTED).move_to(_pt(start - 0.1, mid + 0.45)).align_to(axis, LEFT3)
    group = VGroup(speaker, dots, axis, pressure, label, c_tag, r_tag)

    def step(t: float, p: float) -> None:
        i = 0
        for _ in ys:
            for x in xs:
                dots[i].set_x(x + amp * math.sin(k * (x - start) - omega * t))
                i += 1
        line = np.linspace(start, x1, 120)
        pressure.set_points_smoothly([_pt(x, mid + 0.45 * -math.cos(k * (x - start) - omega * t)) for x in line])
        # The first compression and rarefaction past the speaker, named where they are.
        phase = (omega * t) % (2 * math.pi)
        xc = start + (phase + math.pi) / k
        while xc > x1 - 0.8:
            xc -= lam
        xr = xc + lam / 2 if xc + lam / 2 < x1 - 0.8 else xc - lam / 2
        c_tag.move_to(_pt(max(xc, start + 0.7), top + 0.32))
        r_tag.move_to(_pt(max(xr, start + 0.7), top + 0.32))

    step(0.0, 0.0)
    return Live(group, step, "loop")


# ================================================================= chemistry

def atoms_in(text: str) -> dict:
    """{element: count} in a formula: H2O, Ca(OH)2, Fe2(SO4)3."""
    def parse(s: str, i: int = 0):
        counts: dict = {}
        while i < len(s):
            if s[i] in "([":
                inner, i = parse(s, i + 1)
                m = re.match(r"\d+", s[i:])
                mult = int(m.group()) if m else 1
                i += len(m.group()) if m else 0
                for k, v in inner.items():
                    counts[k] = counts.get(k, 0) + v * mult
            elif s[i] in ")]":
                return counts, i + 1
            else:
                m = re.match(r"([A-Z][a-z]?)(\d*)", s[i:])
                if not m:
                    i += 1
                    continue
                counts[m.group(1)] = counts.get(m.group(1), 0) + int(m.group(2) or 1)
                i += len(m.group())
        return counts, i

    return parse(str(text).replace(" ", ""))[0]


def balance_equation(params: dict, box) -> Live:
    """An equation balanced one coefficient at a time, with every element's atoms counted on each side (green when
    the two sides match): H₂ + O₂ → H₂O becomes 2H₂ + O₂ → 2H₂O."""
    from manim import Dot, VGroup

    pl = _pl()
    cx, cy, w, h = box
    reactants = [(str(f), int(n)) for f, n in (params.get("reactants") or [["H2", 2], ["O2", 1]])]
    products = [(str(f), int(n)) for f, n in (params.get("products") or [["H2O", 2]])]
    species = reactants + products
    elements = []
    for f, _ in species:
        for el in atoms_in(f):
            if el not in elements:
                elements.append(el)
    tones = _tones()
    line, put_line = _readout(" ", 40, pl.P.CREAM)
    rows = []
    group = VGroup(line)
    head = VGroup(pl.T("atom", 20, pl.P.MUTED).move_to(_pt(cx - 2.6, cy + 0.2)),
                  pl.T("left", 20, pl.P.MUTED).move_to(_pt(cx - 0.6, cy + 0.2)),
                  pl.T("right", 20, pl.P.MUTED).move_to(_pt(cx + 2.4, cy + 0.2)))
    group.add(head)
    for i, el in enumerate(elements[:5]):
        y = cy - 0.35 - i * 0.6
        name = pl.T(el, 24, tones[i % len(tones)]).move_to(_pt(cx - 2.6, y))
        left, put_left = _readout(" ", 22, pl.P.CREAM)
        right, put_right = _readout(" ", 22, pl.P.CREAM)
        dots_l = VGroup(*[Dot(radius=0.07, color=tones[i % len(tones)]) for _ in range(12)])
        dots_r = VGroup(*[Dot(radius=0.07, color=tones[i % len(tones)]) for _ in range(12)])
        group.add(name, left, right, dots_l, dots_r)
        rows.append((el, y, put_left, put_right, left, right, dots_l, dots_r))
    verdict, put_verdict = _readout(" ", 24, pl.P.GREEN)
    group.add(verdict)

    def side(items, coeffs):
        return " + ".join((f"{c} " if c > 1 else "") + formula(f) for (f, _), c in zip(items, coeffs))

    def step(t: float, p: float) -> None:
        n = len(species)
        coeffs = [1] * n
        for i in range(n):
            if p >= 0.15 + 0.7 * (i + 1) / n:
                coeffs[i] = species[i][1]
        put_line(f"{side(reactants, coeffs[:len(reactants)])}  →  {side(products, coeffs[len(reactants):])}",
                 _pt(cx, cy + 1.3))
        balanced = True
        for el, y, put_left, put_right, left, right, dots_l, dots_r in rows:
            nl = sum(atoms_in(f).get(el, 0) * c for (f, _), c in zip(reactants, coeffs[:len(reactants)]))
            nr = sum(atoms_in(f).get(el, 0) * c for (f, _), c in zip(products, coeffs[len(reactants):]))
            same = nl == nr
            balanced = balanced and same
            put_left(str(nl), _pt(cx - 1.6, y))
            put_right(str(nr), _pt(cx + 1.4, y))
            left.set_color(pl.P.GREEN if same else pl.P.ROSE)
            right.set_color(pl.P.GREEN if same else pl.P.ROSE)
            for dots, count, x in ((dots_l, nl, cx - 1.15), (dots_r, nr, cx + 1.85)):
                for k, d in enumerate(dots):
                    d.move_to(_pt(x + k * 0.2, y))
                    _show(d, k < count)
        put_verdict("balanced ✓" if balanced else " ", _pt(cx, cy - 0.45 - len(rows) * 0.6))

    step(0.0, 0.0)
    return Live(group, step, "process")


PH_THINGS = [["battery acid", 0.5], ["lemon juice", 2.2], ["vinegar", 2.9], ["tomato", 4.3], ["milk", 6.6],
             ["pure water", 7.0], ["blood", 7.4], ["baking soda", 8.4], ["soap", 10.0], ["bleach", 12.6]]


def _ph_colour(ph: float):
    from manim import ManimColor, interpolate_color

    stops = [(0, "#E5383B"), (3, "#F48C06"), (5, "#FFD60A"), (7, "#52B788"), (9, "#4895EF"), (11, "#3F37C9"),
             (14, "#7209B7")]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if ph <= b:
            return interpolate_color(ManimColor(ca), ManimColor(cb), (ph - a) / (b - a))
    return ManimColor(stops[-1][1])


def ph_scale(params: dict, box) -> Live:
    """The pH scale, 0 to 14, coloured as universal indicator, with everyday substances put on it one by one:
    acids below 7, neutral at 7, bases above."""
    from manim import Line, Rectangle, Triangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    things = [(str(n), float(v)) for n, v in (params.get("substances") or PH_THINGS)][:10]
    width = w * 0.86
    left = cx - width / 2
    y = cy - 0.2
    bar = VGroup(*[Rectangle(width=width / 15, height=0.6, stroke_width=0, fill_color=_ph_colour(i + 0.5),
                             fill_opacity=1).move_to(_pt(left + width * (i + 0.5) / 15, y)) for i in range(15)])
    numbers = VGroup(*[pl.T(str(i), 18, pl.P.CREAM).move_to(_pt(left + width * (i + 0.5) / 15, y - 0.55))
                       for i in range(15)])
    zones = VGroup(pl.T("acid", 22, "#F48C06").move_to(_pt(left + width * 0.2, y - 1.05)),
                   pl.T("neutral", 22, "#52B788").move_to(_pt(left + width * 7.5 / 15, y - 1.05)),
                   pl.T("base (alkali)", 22, "#4895EF").move_to(_pt(left + width * 0.8, y - 1.05)))
    marks = []
    group = VGroup(bar, numbers, zones)
    for i, (name, ph) in enumerate(things):
        x = left + width * (ph + 0.5) / 15
        level = i % 4
        top = y + 0.55 + level * 0.5
        pointer = Triangle(fill_color=pl.P.CREAM, fill_opacity=1, stroke_width=0).scale(0.1).rotate(math.pi)
        pointer.move_to(_pt(x, y + 0.42))
        stem = Line(_pt(x, y + 0.5), _pt(x, top - 0.12), color=pl.P.MUTED, stroke_width=2)
        label = pl.T(f"{name} {ph:g}", 17, pl.P.CREAM).move_to(_pt(x, top + 0.05))
        group.add(stem, pointer, label)
        marks.append((stem, pointer, label))

    def step(t: float, p: float) -> None:
        for i, mobs in enumerate(marks):
            on = p >= 0.08 + 0.8 * i / len(marks)
            for m in mobs:
                _show(m, on)

    step(0.0, 0.0)
    return Live(group, step, "process")


def electrolysis(params: dict, box) -> Live:
    """Current through a solution: positive ions drift to the cathode (−), negative ions to the anode (+), and gas
    bubbles up at each electrode."""
    from manim import Circle, Line, Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    cation, anion = str(params.get("cation") or "H⁺"), str(params.get("anion") or "OH⁻")
    gas_c, gas_a = str(params.get("cathode_gas") or "H₂"), str(params.get("anode_gas") or "O₂")
    bw, bh = w * 0.5, h * 0.55
    by = cy - h * 0.12
    liquid = Rectangle(width=bw, height=bh * 0.8, stroke_width=0, fill_color=pl.P.RIVER, fill_opacity=0.25)
    liquid.move_to(_pt(cx, by - bh * 0.1))
    beaker = VGroup(Line(_pt(cx - bw / 2, by + bh / 2), _pt(cx - bw / 2, by - bh / 2)),
                    Line(_pt(cx - bw / 2, by - bh / 2), _pt(cx + bw / 2, by - bh / 2)),
                    Line(_pt(cx + bw / 2, by - bh / 2), _pt(cx + bw / 2, by + bh / 2))).set_stroke(pl.P.CREAM, 4)
    ex = bw * 0.3
    cathode = Rectangle(width=0.22, height=bh * 0.85, stroke_width=0, fill_color=pl.P.MUTED, fill_opacity=1)
    anode = cathode.copy()
    cathode.move_to(_pt(cx - ex, by + bh * 0.1))
    anode.move_to(_pt(cx + ex, by + bh * 0.1))
    top = by + bh / 2 + 0.9
    wire = VGroup(Line(cathode.get_top(), _pt(cx - ex, top)), Line(_pt(cx - ex, top), _pt(cx - 0.35, top)),
                  Line(_pt(cx + 0.35, top), _pt(cx + ex, top)), Line(_pt(cx + ex, top), anode.get_top()))
    wire.set_stroke(pl.P.CREAM, 3)
    group = VGroup(liquid, beaker, cathode, anode, wire, _cell(_pt(cx, top)))
    group.add(pl.T(f"cathode (−)  {gas_c}", 18, pl.P.RIVER).next_to(beaker, DOWN3, buff=0.15).align_to(beaker, LEFT3))
    group.add(pl.T(f"anode (+)  {gas_a}", 18, pl.P.ROSE).next_to(beaker, DOWN3, buff=0.15).align_to(beaker, RIGHT3))
    rng = np.random.default_rng(7)
    ions = []
    lo_x, hi_x = cx - ex + 0.3, cx + ex - 0.3
    lo_y, hi_y = by - bh * 0.45, by + bh * 0.25
    for k in range(16):
        positive = k % 2 == 0
        tone = pl.P.RIVER if positive else pl.P.ROSE
        ion = VGroup(Circle(radius=0.16, color=tone, fill_color=tone, fill_opacity=0.35, stroke_width=2),
                     pl.T(cation if positive else anion, 12, pl.P.CREAM))
        group.add(ion)
        ions.append((ion, positive, rng.uniform(0, 1), rng.uniform(lo_y, hi_y)))
    bubbles = []
    for k in range(10):
        b = Circle(radius=0.06 + 0.03 * (k % 3), color=pl.P.CREAM, stroke_width=2)
        group.add(b)
        bubbles.append((b, k % 2 == 0, k / 10))

    def step(t: float, p: float) -> None:
        for ion, positive, phase, y in ions:
            s = (phase + 0.12 * t) % 1.0
            x = hi_x - (hi_x - lo_x) * s if positive else lo_x + (hi_x - lo_x) * s
            ion.move_to(_pt(x, y))
        for b, at_cathode, phase in bubbles:
            s = (phase + 0.35 * t) % 1.0
            x = (cx - ex if at_cathode else cx + ex) + (0.22 if at_cathode else -0.22) * (1 if int(phase * 10) % 4 < 2 else 0.6)
            b.move_to(_pt(x, lo_y + (by + bh * 0.3 - lo_y) * s))

    step(0.0, 0.0)
    return Live(group, step, "loop")


def _bounce(x0: float, v: float, t: float, lo: float, hi: float) -> float:
    """A coordinate moving at v and bouncing between lo and hi (a triangle wave)."""
    span = hi - lo
    s = ((x0 - lo) + v * t) % (2 * span)
    return lo + (s if s <= span else 2 * span - s)


def states(params: dict, box) -> Live:
    """Particles as they are heated: a solid's fixed rows that only vibrate, a liquid's particles sliding past each
    other at the bottom of the box, a gas's flying everywhere; a thermometer rising beside them."""
    from manim import Dot, Line, Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    side = min(w * 0.5, h * 0.75)
    bx = cx - w * 0.12
    frame = Rectangle(width=side, height=side, color=pl.P.CREAM, stroke_width=4).move_to(_pt(bx, cy))
    lo_x, hi_x = bx - side / 2 + 0.15, bx + side / 2 - 0.15
    lo_y, hi_y = cy - side / 2 + 0.15, cy + side / 2 - 0.15
    n = 6
    rng = np.random.default_rng(3)
    lattice = [(lo_x + (hi_x - lo_x) * (i + 0.5) / n, lo_y + (side * 0.45) * (j + 0.5) / n * 1.0)
               for j in range(n) for i in range(n)]
    seeds = [(rng.uniform(lo_x, hi_x), rng.uniform(lo_y, hi_y), rng.uniform(-1, 1), rng.uniform(-1, 1),
              rng.uniform(0, 6.3)) for _ in lattice]
    dots = VGroup(*[Dot(radius=0.13, color=pl.P.RIVER) for _ in lattice])
    tx = cx + w * 0.3
    tube = Rectangle(width=0.3, height=side, color=pl.P.CREAM, stroke_width=3).move_to(_pt(tx, cy))
    mercury = Rectangle(width=0.2, height=0.1, stroke_width=0, fill_color=pl.P.ROSE, fill_opacity=1)
    marks = VGroup(*[Line(_pt(tx + 0.18, cy - side / 2 + side * f), _pt(tx + 0.32, cy - side / 2 + side * f),
                          color=pl.P.MUTED, stroke_width=2) for f in (1 / 3, 2 / 3)])
    name, put_name = _readout(" ", 30, pl.P.GOLD)
    group = VGroup(frame, dots, tube, mercury, marks, name)

    def step(t: float, p: float) -> None:
        heat = _ease(p)
        solid, gas = 1 - _part(heat, 0.25, 0.42), _part(heat, 0.6, 0.78)
        liquid = 1 - solid - gas
        for k, d in enumerate(dots):
            lx, ly = lattice[k]
            x0, y0, vx, vy, ph = seeds[k]
            jiggle = 0.03 + 0.05 * heat
            sx = lx + jiggle * math.sin(7 * t + ph)
            sy = ly + jiggle * math.cos(9 * t + ph)
            # A liquid: near the bottom, wandering past its neighbours.
            wx = _bounce(lx, 0.25 * vx, t, lo_x, hi_x)
            wy = min(_bounce(ly, 0.12 * vy, t, lo_y, lo_y + side * 0.45), lo_y + side * 0.45)
            gx = _bounce(x0, 1.6 * vx, t, lo_x, hi_x)
            gy = _bounce(y0, 1.6 * vy, t, lo_y, hi_y)
            d.move_to(_pt(solid * sx + liquid * wx + gas * gx, solid * sy + liquid * wy + gas * gy))
        level = max(0.1, side * (0.08 + 0.85 * heat))
        mercury.stretch_to_fit_height(level)
        mercury.move_to(_pt(tx, cy - side / 2 + level / 2))
        state = "solid" if heat < 0.33 else "liquid" if heat < 0.69 else "gas"
        put_name(f"{state}   (heated: {int(heat * 100)}%)", _pt(bx, cy + side / 2 + 0.4))

    step(0.0, 0.0)
    return Live(group, step, "process")


def rusting(params: dict, box) -> Live:
    """Three nails over a week: in air with water it rusts; in boiled water under oil (no air), or in dry air (no
    water), it stays bright. Rusting needs both air and water."""
    from manim import Dot, Line, Rectangle, RoundedRectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    days = int(params.get("days") or 7)
    tubes = [("air + water", True), ("boiled water + oil", False), ("dry air", False)]
    rng = np.random.default_rng(11)
    group = VGroup()
    spots = []
    for i, (label, rusts) in enumerate(tubes):
        x = cx + (i - 1) * w * 0.28
        glass = RoundedRectangle(corner_radius=0.3, width=0.9, height=h * 0.6, color=pl.P.CREAM, stroke_width=3)
        glass.move_to(_pt(x, cy))
        group.add(glass)
        if i < 2:
            water = Rectangle(width=0.8, height=h * 0.32, stroke_width=0, fill_color=pl.P.RIVER, fill_opacity=0.3)
            water.move_to(_pt(x, cy - h * 0.12))
            group.add(water)
        if i == 1:
            group.add(Rectangle(width=0.8, height=0.14, stroke_width=0, fill_color=pl.P.GOLD, fill_opacity=0.7)
                      .move_to(_pt(x, cy + h * 0.05)))
        nail = Line(_pt(x, cy + h * 0.22), _pt(x, cy - h * 0.24), color="#9AA5B1", stroke_width=10)
        head = Line(_pt(x - 0.18, cy + h * 0.22), _pt(x + 0.18, cy + h * 0.22), color="#9AA5B1", stroke_width=8)
        group.add(nail, head)
        group.add(pl.T(label, 17, pl.P.CREAM).move_to(_pt(x, cy - h * 0.38)))
        if rusts:
            for _ in range(26):
                y = rng.uniform(cy - h * 0.24, cy + h * 0.2)
                d = Dot(_pt(x + rng.uniform(-0.05, 0.05), y), radius=rng.uniform(0.04, 0.08), color="#B5651D")
                group.add(d)
                spots.append((d, rng.uniform(0.1, 0.9)))
    clock, put_clock = _readout(" ", 26, pl.P.GOLD)
    verdict, put_verdict = _readout(" ", 22, pl.P.CREAM)
    group.add(clock, verdict)

    def step(t: float, p: float) -> None:
        for d, when in spots:
            _show(d, p >= when)
        put_clock(f"day {min(days, int(p * days) + 1)} of {days}", _pt(cx, cy + h * 0.44))
        put_verdict("rusting needs air and water" if p > 0.9 else " ", _pt(cx, cy - h * 0.47))

    step(0.0, 0.0)
    return Live(group, step, "process")


# ================================================================= biology

DIGESTION = [("mouth", "chewing; saliva turns starch into sugar"),
             ("oesophagus", "food pushed down by muscles (peristalsis)"),
             ("stomach", "acid and pepsin start digesting protein"),
             ("small intestine", "bile and enzymes finish digestion; nutrients absorbed into the blood"),
             ("large intestine", "water absorbed; what is left leaves the body")]


def digestion(params: dict, box) -> Live:
    """A bite of food travelling down the gut, each organ named with what happens there as it passes, the food
    getting smaller as it is digested."""
    from manim import Circle, Dot, Ellipse, Line, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    gx = cx - w * 0.2
    s = min(h / 5.4, w / 8.0)
    # mouth, oesophagus, stomach, small intestine (coiled), large intestine (round the coils), rectum.
    organs = {
        "mouth": [_pt(gx, cy + 2.5 * s)],
        "oesophagus": [_pt(gx, cy + 1.9 * s), _pt(gx, cy + 1.1 * s)],
        "stomach": [_pt(gx + 0.45 * s, cy + 0.8 * s), _pt(gx + 0.85 * s, cy + 0.45 * s), _pt(gx + 0.35 * s, cy + 0.15 * s)],
        "small intestine": [_pt(gx - 0.6 * s, cy - 0.15 * s), _pt(gx + 0.6 * s, cy - 0.45 * s), _pt(gx - 0.6 * s, cy - 0.75 * s),
                            _pt(gx + 0.6 * s, cy - 1.05 * s), _pt(gx - 0.2 * s, cy - 1.3 * s), _pt(gx + 1.3 * s, cy - 1.35 * s)],
        "large intestine": [_pt(gx + 1.45 * s, cy - 0.5 * s), _pt(gx + 1.3 * s, cy + 0.05 * s), _pt(gx - 1.25 * s, cy + 0.05 * s),
                            _pt(gx - 1.3 * s, cy - 1.0 * s), _pt(gx - 1.15 * s, cy - 1.8 * s), _pt(gx - 0.8 * s, cy - 2.4 * s)],
    }
    route = [pt for pts in organs.values() for pt in pts]
    tube = VMobject(stroke_color=pl.P.TERRA, stroke_width=20, stroke_opacity=0.55)
    tube.set_points_smoothly(route)
    stomach = Ellipse(width=1.2 * s, height=0.85 * s, color=pl.P.TERRA, stroke_width=4, fill_color=pl.P.TERRA,
                      fill_opacity=0.35).rotate(-0.5).move_to(_pt(gx + 0.55 * s, cy + 0.5 * s))
    mouth = Circle(radius=0.22 * s, color=pl.P.TERRA, stroke_width=4).move_to(organs["mouth"][0])
    samples = [tube.point_from_proportion(k / 400) for k in range(401)]

    def proportion(point):
        return min(range(401), key=lambda k: float(np.linalg.norm(samples[k] - point))) / 400

    stops = [0.0] + [proportion(pts[0]) for name, pts in organs.items() if name != "mouth"]
    places = {"mouth": (organs["mouth"][0], RIGHT3), "oesophagus": (organs["oesophagus"][0], LEFT3),
              "stomach": (organs["stomach"][1], RIGHT3), "small intestine": (organs["small intestine"][3], RIGHT3),
              "large intestine": (organs["large intestine"][3], LEFT3)}
    tags = VGroup()
    for name, _ in DIGESTION:
        at, side = places[name]
        tag = pl.T(name, 19, pl.P.MUTED).next_to(at, side, buff=0.45 * s)
        tags.add(tag, Line(at + side * 0.12 * s, tag.get_edge_center(-side), color=pl.P.MUTED, stroke_width=1))
    food = Dot(radius=0.18, color=pl.P.GOLD)
    now, put_now = _readout(" ", 26, pl.P.GOLD)
    what, put_what = _readout(" ", 20, pl.P.CREAM)
    group = VGroup(tube, stomach, mouth, tags, food, now, what)

    def step(t: float, p: float) -> None:
        at = 0.01 + 0.98 * p
        food.move_to(tube.point_from_proportion(at))
        food.set_width(0.36 * (1 - 0.6 * _part(p, 0.4, 0.8)))
        stage = max(i for i, s0 in enumerate(stops) if at >= s0)
        for i in range(len(DIGESTION)):
            tags[2 * i].set_color(pl.P.GOLD if i == stage else pl.P.MUTED)
        name, text = DIGESTION[stage]
        x = cx + w * 0.24
        put_now(name, _pt(x, cy + 0.7))
        put_what(pl.wrap(text, 30), _pt(x, cy - 0.2))

    step(0.0, 0.0)
    return Live(group, step, "process")


def double_circulation(params: dict, box) -> Live:
    """Blood going round twice: right side of the heart to the lungs and back to the left side (pulmonary), left
    side to the body and back to the right (systemic); blue without oxygen, red with it."""
    from manim import Dot, RoundedRectangle, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    red, blue = "#E5383B", "#4895EF"
    cw, chh = 1.1, 0.75
    ra, la = _pt(cx - 0.65, cy + 0.42), _pt(cx + 0.65, cy + 0.42)
    rv, lv = _pt(cx - 0.65, cy - 0.42), _pt(cx + 0.65, cy - 0.42)
    group = VGroup()
    for at, name, tone in ((ra, "RA", blue), (la, "LA", red), (rv, "RV", blue), (lv, "LV", red)):
        group.add(RoundedRectangle(corner_radius=0.15, width=cw, height=chh, color=tone, stroke_width=4, fill_color=tone,
                                   fill_opacity=0.25).move_to(at), pl.T(name, 20, pl.P.CREAM).move_to(at))
    ly, by = cy + h * 0.36, cy - h * 0.36
    lungs = RoundedRectangle(corner_radius=0.3, width=w * 0.34, height=0.8, color=pl.P.ROSE, stroke_width=3)
    lungs.move_to(_pt(cx, ly))
    body = RoundedRectangle(corner_radius=0.3, width=w * 0.5, height=0.8, color=pl.P.TERRA, stroke_width=3)
    body.move_to(_pt(cx, by))
    group.add(lungs, pl.T("lungs: blood takes in oxygen", 18, pl.P.CREAM).move_to(lungs),
              body, pl.T("body: oxygen used, carbon dioxide picked up", 18, pl.P.CREAM).move_to(body))
    side = w * 0.2
    # One loop through all of it: RA -> RV -> lungs -> LA -> LV -> body -> RA.
    loop = [ra, rv, _pt(cx - side, rv[1]), _pt(cx - side, ly), _pt(cx + side, ly), _pt(cx + side, la[1]), la, lv,
            _pt(cx + side * 1.7, lv[1]), _pt(cx + side * 1.7, by), _pt(cx - side * 1.7, by), _pt(cx - side * 1.7, ra[1]),
            ra]
    for a, b, tone in ((2, 4, blue), (4, 6, red), (7, 10, red), (10, 12, blue)):
        pipe = VMobject(stroke_color=tone, stroke_width=6, stroke_opacity=0.5)
        pipe.set_points_as_corners(loop[a:b + 1])
        group.add(pipe)
    group.add(pl.T("pulmonary circulation", 18, pl.P.MUTED).move_to(_pt(cx - side - 1.4, (ly + rv[1]) / 2)),
              pl.T("systemic circulation", 18, pl.P.MUTED).move_to(_pt(cx + side * 1.7 + 1.4, (by + lv[1]) / 2)))
    lengths = np.cumsum([0] + [float(np.linalg.norm(b - a)) for a, b in zip(loop, loop[1:])])
    oxygen_from = lengths[4] / lengths[-1]          # leaving the lungs
    oxygen_to = lengths[10] / lengths[-1]           # leaving the body
    drops = [Dot(radius=0.09) for _ in range(18)]
    group.add(*drops)

    def step(t: float, p: float) -> None:
        for k, d in enumerate(drops):
            s = (k / len(drops) + 0.06 * t) % 1.0
            d.move_to(_along(loop, s))
            d.set_color(red if oxygen_from <= s < oxygen_to else blue)

    step(0.0, 0.0)
    return Live(group, step, "loop")


def photosynthesis(params: dict, box) -> Live:
    """A leaf making food: sunlight, carbon dioxide from the air and water from the roots go in; oxygen goes out
    and glucose is made; then the equation."""
    from manim import Arrow, Circle, Dot, Ellipse, Line, VGroup

    pl = _pl()
    cx, cy, w, h = box
    leaf = Ellipse(width=2.6, height=1.4, color=pl.P.GREEN, stroke_width=4, fill_color=pl.P.GREEN, fill_opacity=0.35)
    leaf.rotate(0.35).move_to(_pt(cx, cy + 0.2))
    vein = Line(leaf.point_from_proportion(0.5), leaf.point_from_proportion(0.0), color=pl.P.GREEN, stroke_width=3)
    sun = Circle(radius=0.38, color=pl.P.GOLD, fill_color=pl.P.GOLD, fill_opacity=0.9).move_to(_pt(cx - w * 0.32, cy + h * 0.33))
    rays = VGroup(*[Line(sun.get_center() + 0.5 * _pt(math.cos(a), math.sin(a)), sun.get_center() + 0.75 * _pt(math.cos(a), math.sin(a)),
                         color=pl.P.GOLD, stroke_width=3) for a in np.linspace(0, 2 * math.pi, 9)[:-1]])
    centre = leaf.get_center()
    flows = [  # (start, end, label, colour, inward)
        (sun.get_center() + _pt(0.5, -0.3), centre + _pt(-0.8, 0.4), "sunlight", pl.P.GOLD, True),
        (_pt(cx - w * 0.38, cy - 0.3), centre + _pt(-1.0, -0.2), "carbon dioxide (CO₂)\nfrom the air", pl.P.MUTED, True),
        (_pt(cx - 0.9, cy - h * 0.3), centre + _pt(-0.2, -0.6), "water (H₂O)\nfrom the roots", pl.P.RIVER, True),
        (centre + _pt(1.1, 0.3), _pt(cx + w * 0.36, cy + h * 0.25), "oxygen (O₂)\nout to the air", pl.P.CREAM, False),
        (centre + _pt(0.6, -0.5), _pt(cx + w * 0.3, cy - h * 0.25), "glucose (C₆H₁₂O₆)\nstored as starch", pl.P.SAND, False),
    ]
    group = VGroup(leaf, vein, sun, rays)
    arrows = []
    for start, end, label, tone, inward in flows:
        arrow = Arrow(start, end, buff=0, color=tone, stroke_width=6, max_tip_length_to_length_ratio=0.12)
        tag = pl.T(label, 17, tone)
        tag.next_to(arrow.get_start() if inward else arrow.get_end(), DOWN3 if start[1] < cy else UP3, buff=0.12)
        beads = VGroup(*[Dot(radius=0.06, color=tone) for _ in range(3)])
        group.add(arrow, tag, beads)
        arrows.append((arrow, tag, beads, start, end))
    equation = pl.T("6CO₂ + 6H₂O  →  C₆H₁₂O₆ + 6O₂   (light, chlorophyll)", 22, pl.P.GOLD)
    equation.move_to(_pt(cx + w * 0.12, cy - h * 0.47))
    group.add(equation)

    def step(t: float, p: float) -> None:
        for i, (arrow, tag, beads, start, end) in enumerate(arrows):
            on = p >= (0.05 + 0.13 * i)
            for m in (arrow, tag):
                _show(m, on)
            for k, b in enumerate(beads):
                b.move_to(start + (end - start) * ((k / 3 + 0.4 * t) % 1.0))
                _show(b, on)
        _show(equation, p >= 0.75)

    step(0.0, 0.0)
    return Live(group, step, "process")


def punnett(params: dict, box) -> Live:
    """Mendel's cross in a Punnett square: each parent's alleles along the sides, every box filled in turn with the
    offspring's genotype, then the ratio of genotypes and of what they look like."""
    from manim import Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    parents = [str(x) for x in (params.get("parents") or ["Tt", "Tt"])][:2]
    traits = params.get("traits") or {"T": "tall", "t": "short"}
    a, b = parents[0][:2], parents[1][:2]
    big = next((c for c in a + b if c.isupper()), (a + b)[0])
    dominant_word = str(traits.get(big, "dominant"))
    recessive_word = str(traits.get(big.lower(), "recessive"))
    size = min(h * 0.26, 1.5)
    ox, oy = cx - size * 0.6, cy + size * 0.15
    cells, heads = [], VGroup()
    group = VGroup(pl.T(f"{a}  ×  {b}", 30, pl.P.GOLD).move_to(_pt(ox, oy + size * 1.55)))
    for j, allele in enumerate(b):
        heads.add(pl.T(allele, 34, pl.P.ROSE).move_to(_pt(ox + (j - 0.5) * size, oy + size * 1.05)))
    for i, allele in enumerate(a):
        heads.add(pl.T(allele, 34, pl.P.RIVER).move_to(_pt(ox - size * 1.05, oy - (i - 0.5) * size)))
    group.add(heads)
    for i, ai in enumerate(a):
        for j, bj in enumerate(b):
            geno = "".join(sorted(ai + bj, key=lambda c: (c.islower(), c)))
            dom = any(c.isupper() for c in geno)
            at = _pt(ox + (j - 0.5) * size, oy - (i - 0.5) * size)
            box_ = Rectangle(width=size, height=size, color=pl.P.CREAM, stroke_width=3,
                             fill_color=pl.P.GREEN if dom else pl.P.SAND, fill_opacity=0.35)
            box_.move_to(at)
            text = pl.T(geno, 34, pl.P.CREAM).move_to(at)
            group.add(box_, text)
            cells.append((box_, text, geno, dom))
    counts: dict = {}
    for _, _, geno, _ in cells:
        counts[geno] = counts.get(geno, 0) + 1
    look = sum(1 for c in cells if c[3])
    ratio = pl.T("  :  ".join(f"{n} {g}" for g, n in sorted(counts.items(), key=lambda kv: (kv[0].islower(), kv[0]))),
                 26, pl.P.CREAM)
    looks = pl.T(f"{look} {dominant_word}  :  {4 - look} {recessive_word}", 26, pl.P.GOLD)
    ratio.move_to(_pt(cx + w * 0.26, cy + 0.35))
    looks.move_to(_pt(cx + w * 0.26, cy - 0.35))
    group.add(ratio, looks)

    def step(t: float, p: float) -> None:
        _show(heads, p >= 0.05)
        for k, (box_, text, _, _) in enumerate(cells):
            on = p >= 0.18 + 0.14 * k
            box_.set_fill(opacity=0.35 if on else 0.0)
            _show(text, on)
        _show(ratio, p >= 0.78)
        _show(looks, p >= 0.86)

    step(0.0, 0.0)
    return Live(group, step, "process")


FOOD_WEB = [{"name": "grass", "level": 0}, {"name": "grasshopper", "level": 1, "eats": ["grass"]},
            {"name": "rabbit", "level": 1, "eats": ["grass"]}, {"name": "frog", "level": 2, "eats": ["grasshopper"]},
            {"name": "snake", "level": 3, "eats": ["frog", "rabbit"]}, {"name": "hawk", "level": 3, "eats": ["rabbit", "snake"]}]


def food_web(params: dict, box) -> Live:
    """A food web, energy flowing up from the plants; then one species is taken away: what it ate grows in
    number, what ate it goes short."""
    from manim import Arrow, Dot, Line, Rectangle, RoundedRectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    species = [dict(s) for s in (params.get("species") or FOOD_WEB)][:9]
    gone = str(params.get("remove") or "frog")
    levels = sorted({int(s.get("level", 0)) for s in species})
    where = {}
    for lv in levels:
        row = [s for s in species if int(s.get("level", 0)) == lv]
        for k, s in enumerate(row):
            where[s["name"]] = _pt(cx - w * 0.12 + (k - (len(row) - 1) / 2) * w * 0.26,
                                   cy - h * 0.38 + (h * 0.76) * levels.index(lv) / max(len(levels) - 1, 1))
    group = VGroup()
    arrows, beads = [], []
    for s in species:
        for prey in s.get("eats") or []:
            if prey in where and s["name"] in where:
                a = Arrow(where[prey], where[s["name"]], buff=0.45, color=pl.P.MUTED, stroke_width=3,
                          max_tip_length_to_length_ratio=0.1)
                group.add(a)
                arrows.append((a, prey, s["name"]))
                bead = Dot(radius=0.06, color=pl.P.GOLD)
                group.add(bead)
                beads.append((bead, a))
    bars, nodes = {}, {}
    for s in species:
        at = where[s["name"]]
        card = RoundedRectangle(corner_radius=0.15, width=1.9, height=0.62, color=pl.P.GREEN if s.get("level", 0) == 0
                                else pl.P.CREAM, stroke_width=3, fill_color=pl.P.BG, fill_opacity=1).move_to(at)
        name = pl.T(s["name"], 20, pl.P.CREAM).move_to(at)
        frame = Rectangle(width=0.18, height=0.8, color=pl.P.MUTED, stroke_width=1).next_to(card, RIGHT3, buff=0.1)
        fill = Rectangle(width=0.14, height=0.4, stroke_width=0, fill_color=pl.P.GREEN, fill_opacity=0.9)
        group.add(card, name, frame, fill)
        bars[s["name"]] = (frame, fill)
        nodes[s["name"]] = VGroup(card, name)
    cross = VGroup(Line(_pt(-0.5, -0.3), _pt(0.5, 0.3)), Line(_pt(-0.5, 0.3), _pt(0.5, -0.3))).set_stroke(pl.P.ROSE, 6)
    if gone in where:
        cross.move_to(where[gone])
    note, put_note = _readout(" ", 20, pl.P.GOLD)
    group.add(cross, note)
    prey_of_gone = {prey for s in species if s["name"] == gone for prey in s.get("eats") or []}
    eaters_of_gone = {s["name"] for s in species if gone in (s.get("eats") or [])}

    def step(t: float, p: float) -> None:
        removing = _ease(_part(p, 0.45, 0.8))
        for bead, a in beads:
            bead.move_to(a.get_start() + (a.get_end() - a.get_start()) * ((0.35 * t + hash(id(a)) % 7 / 7) % 1.0))
        for name, (frame, fill) in bars.items():
            share = 0.5
            if name in prey_of_gone:
                share = 0.5 + 0.45 * removing
            elif name in eaters_of_gone:
                share = 0.5 - 0.35 * removing
            elif name == gone:
                share = 0.5 * (1 - removing)
            height = max(0.02, frame.height * share)
            fill.stretch_to_fit_height(height)
            fill.move_to(_pt(frame.get_center()[0], frame.get_bottom()[1] + height / 2))
            fill.set_color(pl.P.ROSE if share < 0.45 else pl.P.GREEN)
        for a, prey, eater in arrows:
            a.set_opacity(1 - 0.8 * removing if gone in (prey, eater) else 1)
        if gone in nodes:
            nodes[gone].set_opacity(1 - 0.6 * removing)
        _show(cross, removing > 0.05)
        if removing > 0.5:
            up = ", ".join(sorted(prey_of_gone)) or "nothing"
            down = ", ".join(sorted(eaters_of_gone)) or "nothing"
            put_note(f"without the {gone}: more {up}; less food for {down}", _pt(cx, cy + h * 0.48))
        else:
            put_note("energy flows from plants up the food web", _pt(cx, cy + h * 0.48))

    step(0.0, 0.0)
    return Live(group, step, "process")


# ================================================================= mathematics

def _axes(x_range, y_range, width, height, at, numbers=True):
    from manim import Axes

    pl = _pl()
    axes = Axes(x_range=list(x_range), y_range=list(y_range), x_length=width, y_length=height,
                axis_config={"color": pl.P.MUTED, "stroke_width": 2, "include_numbers": numbers, "font_size": 18})
    return axes.move_to(at)


def unit_circle(params: dict, box) -> Live:
    """A point going round the unit circle, its height carried across to a graph: the sine wave is the circle's
    height against the angle."""
    from manim import Circle, DashedLine, Dot, Line, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    period = float(params.get("period") or 6.0)
    r = min(h * 0.32, w * 0.14)
    centre = _pt(cx - w * 0.33, cy)
    circle = Circle(radius=r, color=pl.P.MUTED, stroke_width=3).move_to(centre)
    cross = VGroup(Line(centre + _pt(-r - 0.2, 0), centre + _pt(r + 0.2, 0)),
                   Line(centre + _pt(0, -r - 0.2), centre + _pt(0, r + 0.2))).set_stroke(pl.P.MUTED, 2)
    gx0, gx1 = cx - w * 0.12, cx + w * 0.45
    axis = Line(_pt(gx0, cy), _pt(gx1, cy), color=pl.P.MUTED, stroke_width=2)
    ticks = VGroup()
    for k, name in ((1, "π/2"), (2, "π"), (3, "3π/2"), (4, "2π")):
        x = gx0 + (gx1 - gx0) * k / 4
        ticks.add(Line(_pt(x, cy - 0.08), _pt(x, cy + 0.08), color=pl.P.MUTED, stroke_width=2),
                  pl.T(name, 16, pl.P.MUTED).move_to(_pt(x, cy - 0.35)))
    radius = Line(centre, centre + _pt(r, 0), color=pl.P.CREAM, stroke_width=4)
    height = Line(centre, centre, color=pl.P.GOLD, stroke_width=5)
    dot = Dot(radius=0.1, color=pl.P.GOLD)
    carry = DashedLine(centre, centre + _pt(1, 0), color=pl.P.GOLD, stroke_width=2)
    pen = Dot(radius=0.1, color=pl.P.GOLD)
    wave = VMobject(stroke_color=pl.P.GOLD, stroke_width=4)
    read, put = _readout(" ", 22, pl.P.CREAM)
    group = VGroup(circle, cross, axis, ticks, wave, radius, height, carry, dot, pen, read)

    def step(t: float, p: float) -> None:
        angle = (2 * math.pi * t / period) % (2 * math.pi)
        at = centre + r * _pt(math.cos(angle), math.sin(angle))
        radius.put_start_and_end_on(centre, at)
        height.put_start_and_end_on(_pt(at[0], cy), at + _pt(0, 1e-3))
        dot.move_to(at)
        x = gx0 + (gx1 - gx0) * angle / (2 * math.pi)
        pen.move_to(_pt(x, at[1]))
        carry.put_start_and_end_on(at, _pt(x, at[1]) + _pt(1e-3, 0))
        xs = np.linspace(0, max(angle, 1e-3), max(2, int(angle * 20)))
        wave.set_points_as_corners([_pt(gx0 + (gx1 - gx0) * a / (2 * math.pi), cy + r * math.sin(a)) for a in xs])
        put(f"θ = {math.degrees(angle):.0f}°    sin θ = {math.sin(angle):.2f}", _pt(cx, cy + h * 0.44))

    step(0.0, 0.0)
    return Live(group, step, "loop")


def area_fill(params: dict, box) -> Live:
    """The area under a curve found with rectangles: 2, then 4, 8, 16... thinner ones, their total closing in on
    the true area (the integral)."""
    from manim import Polygon, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    expr = str(params.get("expr") or "x^2")
    a, b = float(params.get("from", 0)), float(params.get("to", 2))
    f = pl.safe_function(expr)
    xs = np.linspace(a, b, 400)
    ys = np.array([float(f(x)) for x in xs])
    top = max(float(ys.max()), 0.0) * 1.15 or 1.0
    bottom = min(float(ys.min()), 0.0)
    exact = float(np.trapezoid(ys, xs)) if hasattr(np, "trapezoid") else float(np.trapz(ys, xs))
    axes = _axes([a, b, (b - a) / 4], [bottom, top, (top - bottom) / 4], w * 0.62, h * 0.72, _pt(cx - w * 0.15, cy))
    curve = VMobject(stroke_color=pl.P.GOLD, stroke_width=5)
    curve.set_points_smoothly([axes.c2p(x, y) for x, y in zip(xs[::8], ys[::8])])
    bars = VGroup(*[Polygon(ORIGIN3, RIGHT3, UP3, stroke_color=pl.P.CREAM, stroke_width=1, fill_color=pl.P.RIVER,
                            fill_opacity=0.45) for _ in range(64)])
    read, put = _readout(" ", 24, pl.P.CREAM)
    truth = pl.T(f"exact area = {exact:.3f}", 22, pl.P.GOLD).move_to(_pt(cx + w * 0.32, cy - 0.5))
    label = pl.T(f"y = {expr}", 22, pl.P.GOLD).next_to(axes, UP3, buff=0.1)
    group = VGroup(axes, bars, curve, read, truth, label)

    def step(t: float, p: float) -> None:
        n = 2 ** min(6, 1 + int(p * 6))
        width = (b - a) / n
        total = 0.0
        for k, bar in enumerate(bars):
            if k < n:
                x = a + k * width
                y = float(f(x + width / 2))
                total += y * width
                bar.set_points_as_corners([axes.c2p(x, 0), axes.c2p(x, y), axes.c2p(x + width, y), axes.c2p(x + width, 0),
                                           axes.c2p(x, 0)])
                bar.set_fill(opacity=0.45)
                bar.set_stroke(opacity=1)
            else:
                bar.set_fill(opacity=0)
                bar.set_stroke(opacity=0)
        put(f"{n} rectangles: {total:.3f}", _pt(cx + w * 0.32, cy + 0.3))

    step(0.0, 0.0)
    return Live(group, step, "process")


def probability(params: dict, box) -> Live:
    """Tossing a coin (or rolling a die) again and again: early on the share of heads jumps about; after many
    trials it settles near the probability, 1/2 (or 1/6)."""
    from manim import DashedLine, Rectangle, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    dice = str(params.get("trial") or "coin") == "dice"
    trials = int(params.get("trials") or 300)
    rng = np.random.default_rng(int(params.get("seed") or 5))
    outcomes = rng.integers(1, 7 if dice else 3, size=trials)
    hit = (outcomes == 6) if dice else (outcomes == 1)
    expected = 1 / 6 if dice else 0.5
    faces = 6 if dice else 2
    names = [str(k) for k in range(1, 7)] if dice else ["heads", "tails"]
    axes = _axes([0, trials, trials / 5], [0, 1, 0.25], w * 0.5, h * 0.62, _pt(cx + w * 0.18, cy - 0.1))
    line = VMobject(stroke_color=pl.P.GOLD, stroke_width=4)
    goal = DashedLine(axes.c2p(0, expected), axes.c2p(trials, expected), color=pl.P.GREEN, stroke_width=3)
    goal_tag = pl.T(f"probability {'1/6' if dice else '1/2'}", 18, pl.P.GREEN).next_to(goal, UP3, buff=0.08).align_to(goal, RIGHT3)
    ylab = pl.T(f"share of {'sixes' if dice else 'heads'}", 18, pl.P.MUTED).next_to(axes, UP3, buff=0.1)
    bx = cx - w * 0.3
    bar_w = min(0.7, w * 0.3 / faces)
    frames, fills, tags = VGroup(), [], VGroup()
    for k in range(faces):
        x = bx + (k - (faces - 1) / 2) * (bar_w + 0.15)
        frames.add(Rectangle(width=bar_w, height=h * 0.55, color=pl.P.MUTED, stroke_width=1).move_to(_pt(x, cy)))
        fill = Rectangle(width=bar_w - 0.06, height=0.01, stroke_width=0, fill_color=pl.P.RIVER, fill_opacity=0.9)
        fills.append(fill)
        tags.add(pl.T(names[k], 16, pl.P.CREAM).move_to(_pt(x, cy - h * 0.32)))
    read, put = _readout(" ", 22, pl.P.CREAM)
    group = VGroup(axes, goal, goal_tag, ylab, line, frames, *fills, tags, read)

    def step(t: float, p: float) -> None:
        n = max(1, int(trials * p))
        share = np.cumsum(hit[:n]) / np.arange(1, n + 1)
        idx = np.unique(np.linspace(0, n - 1, min(n, 150)).astype(int))
        line.set_points_as_corners([axes.c2p(i + 1, float(share[i])) for i in idx] if len(idx) > 1
                                   else [axes.c2p(1, float(share[0])), axes.c2p(1.01, float(share[0]))])
        counts = np.bincount(outcomes[:n], minlength=faces + 1)[1:faces + 1]
        biggest = max(int(counts.max()), 1)
        for k, fill in enumerate(fills):
            height = max(0.01, frames[k].height * counts[k] / max(biggest, n / faces * 1.6))
            fill.stretch_to_fit_height(height)
            fill.move_to(_pt(frames[k].get_center()[0], frames[k].get_bottom()[1] + height / 2))
        put(f"{n} {'rolls' if dice else 'tosses'}:  {share[-1]:.2f}", _pt(cx + w * 0.18, cy + h * 0.44))

    step(0.0, 0.0)
    return Live(group, step, "process")


def transform_graph(params: dict, box) -> Live:
    """A graph moved by changing its equation: y = a·f(b(x − h)) + k: h shifts it sideways, k up, a stretches it
    up (a negative flips it over), b squeezes it sideways; the original stays faint beneath."""
    from manim import VGroup, VMobject

    pl = _pl()
    cx, cy, w, h_ = box
    expr = str(params.get("expr") or "x^2")
    f = pl.safe_function(expr)
    sh, sk = (list(params.get("shift") or [2, 1]) + [0, 0])[:2]
    sa, sb = (list(params.get("stretch") or [1, 1]) + [1, 1])[:2]
    reflect = str(params.get("reflect") or "")
    if reflect == "x":
        sa = -abs(sa)
    elif reflect == "y":
        sb = -abs(sb)
    xr = [float(v) for v in (params.get("x") or [-5, 5])]
    yr = [float(v) for v in (params.get("y") or [-5, 5])]
    axes = _axes([xr[0], xr[1], 1], [yr[0], yr[1], 1], w * 0.6, h_ * 0.86, _pt(cx - w * 0.12, cy), numbers=False)
    xs = np.linspace(xr[0], xr[1], 240)

    def points(fn):
        out = []
        for x in xs:
            y = float(fn(x))
            if math.isfinite(y) and yr[0] - 0.5 <= y <= yr[1] + 0.5:
                out.append(axes.c2p(x, min(max(y, yr[0]), yr[1])))
        return out or [axes.c2p(0, 0), axes.c2p(0.01, 0)]

    base = VMobject(stroke_color=pl.P.MUTED, stroke_width=3, stroke_opacity=0.6)
    base.set_points_as_corners(points(f))
    moved = VMobject(stroke_color=pl.P.GOLD, stroke_width=5)
    read, put = _readout(" ", 26, pl.P.GOLD)
    original = pl.T(f"y = {expr}", 20, pl.P.MUTED).move_to(_pt(cx + w * 0.34, cy + 0.6))
    group = VGroup(axes, base, moved, read, original)

    def step(t: float, p: float) -> None:
        e = _ease(p)
        a = 1 + (float(sa) - 1) * e
        b = 1 + (float(sb) - 1) * e
        hh, kk = float(sh) * e, float(sk) * e
        moved.set_points_as_corners(points(lambda x: a * f(b * (x - hh)) + kk))
        hh, kk, a, b = round(hh, 1), round(kk, 1), round(a, 1), round(b, 1)
        inner = "x" if abs(hh) < 1e-6 else f"x {'−' if hh > 0 else '+'} {abs(hh):.1f}"
        inner = inner if abs(b - 1) < 1e-6 else f"{b:.1f}({inner})"
        outer = f"f({inner})" if abs(a - 1) < 1e-6 else f"{a:.1f}·f({inner})"
        put(f"y = {outer}" + ("" if abs(kk) < 1e-6 else f" {'+' if kk > 0 else '−'} {abs(kk):.1f}"),
            _pt(cx + w * 0.34, cy - 0.1))

    step(0.0, 0.0)
    return Live(group, step, "process")


# ================================================================= geography and economics

def water_cycle(params: dict, box) -> Live:
    """The water cycle going round: the sun warms the sea and vapour rises (evaporation), cools into a cloud
    (condensation), the wind carries it over the hills where it rains (precipitation), and rivers carry it back
    to the sea (runoff)."""
    from manim import Circle, Dot, Ellipse, Line, Polygon, Rectangle, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    ground = cy - h * 0.3
    sea = Rectangle(width=w * 0.42, height=h * 0.18, stroke_width=0, fill_color=pl.P.RIVER, fill_opacity=0.55)
    sea.move_to(_pt(cx - w * 0.29, ground - h * 0.06))
    land = Polygon(_pt(cx - w * 0.08, ground - h * 0.15), _pt(cx - w * 0.08, ground), _pt(cx + w * 0.2, cy + h * 0.08),
                   _pt(cx + w * 0.3, cy + h * 0.02), _pt(cx + w * 0.48, ground), _pt(cx + w * 0.48, ground - h * 0.15),
                   stroke_width=0, fill_color=pl.P.SAND, fill_opacity=0.6)
    sun = Circle(radius=0.42, color=pl.P.GOLD, fill_color=pl.P.GOLD, fill_opacity=0.9).move_to(_pt(cx - w * 0.4, cy + h * 0.36))
    river = VMobject(stroke_color=pl.P.RIVER, stroke_width=5)
    river_pts = [_pt(cx + w * 0.22, cy + h * 0.02), _pt(cx + w * 0.12, ground + 0.2), _pt(cx, ground + 0.05),
                 _pt(cx - w * 0.1, ground - 0.02)]
    river.set_points_smoothly(river_pts)
    cloud = VGroup(*[Ellipse(width=1.2, height=0.6, stroke_width=0, fill_color=pl.P.CREAM, fill_opacity=0.9)
                     .shift(_pt(dx, dy)) for dx, dy in ((0, 0), (0.6, 0.15), (1.1, 0), (0.55, -0.12))])
    tags = {"evaporation": _pt(cx - w * 0.29, cy - 0.1), "condensation": _pt(cx - w * 0.02, cy + h * 0.44),
            "precipitation": _pt(cx + w * 0.4, cy + h * 0.24), "runoff": _pt(cx + w * 0.02, ground - 0.35)}
    rates = params.get("rates") or {}
    labels = VGroup(*[pl.T(name + (f" ({rates[name]})" if name in rates else ""), 18, pl.P.GOLD).move_to(at)
                      for name, at in tags.items()])
    vapour = [Dot(radius=0.05, color=pl.P.CREAM) for _ in range(10)]
    rain = [Line(ORIGIN3, _pt(0, -0.18), color=pl.P.RIVER, stroke_width=3) for _ in range(12)]
    flow = [Dot(radius=0.06, color=pl.P.CREAM) for _ in range(5)]
    group = VGroup(sea, land, river, sun, cloud, labels, *vapour, *rain, *flow)
    period = float(params.get("period") or 8.0)

    def step(t: float, p: float) -> None:
        phase = (t / period) % 1.0
        # The cloud drifts from over the sea to over the hills and back.
        x = cx - w * 0.25 + w * 0.45 * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
        cloud.move_to(_pt(x, cy + h * 0.3))
        for k, d in enumerate(vapour):
            s = (k / len(vapour) + 0.25 * t) % 1.0
            d.move_to(_pt(cx - w * 0.44 + w * 0.32 * ((k * 0.37) % 1.0), ground + (cy + h * 0.22 - ground) * s))
            d.set_opacity(1 - s)
        raining = x > cx + w * 0.05
        for k, drop in enumerate(rain):
            s = (k / len(rain) + 0.9 * t) % 1.0
            drop.move_to(_pt(x - 0.4 + 1.6 * ((k * 0.43) % 1.0), cy + h * 0.2 - (cy + h * 0.2 - (cy - h * 0.05)) * s))
            drop.set_opacity(0.9 if raining else 0)
        for k, d in enumerate(flow):
            d.move_to(_along(river_pts, (k / len(flow) + 0.2 * t) % 1.0))

    step(0.0, 0.0)
    return Live(group, step, "loop")


def supply_demand(params: dict, box) -> Live:
    """Supply and demand curves and where they cross (the price and quantity the market settles at); then one
    curve shifts and the crossing moves: demand up raises both price and quantity, supply up lowers the price."""
    from manim import DashedLine, Dot, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    shift = str(params.get("shift") or "demand_up")
    amount = float(params.get("amount") or 2.0)
    axes = _axes([0, 10, 2], [0, 10, 2], w * 0.55, h * 0.78, _pt(cx - w * 0.12, cy), numbers=False)
    qlab = pl.T("quantity", 18, pl.P.MUTED).next_to(axes.x_axis, DOWN3, buff=0.15)
    plab = pl.T("price", 18, pl.P.MUTED).next_to(axes.y_axis, UP3, buff=0.1)

    def demand(q, d=0.0):
        return 8.5 - 0.7 * q + d

    def supply(q, s=0.0):
        return 1.5 + 0.7 * q - s

    def line_of(fn):
        mob = VMobject(stroke_width=5)
        mob.set_points_as_corners([axes.c2p(q, fn(q)) for q in np.linspace(0, 10, 30) if 0 <= fn(q) <= 10])
        return mob

    d0 = line_of(demand).set_stroke(pl.P.ROSE, 3, opacity=0.4)
    s0 = line_of(supply).set_stroke(pl.P.RIVER, 3, opacity=0.4)
    d1 = VMobject(stroke_color=pl.P.ROSE, stroke_width=5)
    s1 = VMobject(stroke_color=pl.P.RIVER, stroke_width=5)
    d_tag, s_tag = pl.T("D", 22, pl.P.ROSE), pl.T("S", 22, pl.P.RIVER)
    point = Dot(radius=0.11, color=pl.P.GOLD)
    guide_x = DashedLine(ORIGIN3, RIGHT3, color=pl.P.GOLD, stroke_width=2)
    guide_y = DashedLine(ORIGIN3, RIGHT3, color=pl.P.GOLD, stroke_width=2)
    read, put = _readout(" ", 22, pl.P.CREAM)
    group = VGroup(axes, qlab, plab, d0, s0, d1, s1, d_tag, s_tag, guide_x, guide_y, point, read)

    def step(t: float, p: float) -> None:
        e = _ease(_part(p, 0.3, 0.85))
        dd = amount * e * (1 if shift == "demand_up" else -1 if shift == "demand_down" else 0)
        ss = amount * e * (1 if shift == "supply_up" else -1 if shift == "supply_down" else 0)
        d1.set_points_as_corners([axes.c2p(q, demand(q, dd)) for q in np.linspace(0, 10, 30) if 0 <= demand(q, dd) <= 10])
        s1.set_points_as_corners([axes.c2p(q, supply(q, ss)) for q in np.linspace(0, 10, 30) if 0 <= supply(q, ss) <= 10])
        d_tag.next_to(d1.get_end(), RIGHT3, buff=0.1)
        s_tag.next_to(s1.get_end(), RIGHT3, buff=0.1)
        q = (8.5 + dd - 1.5 + ss) / 1.4
        price = demand(q, dd)
        point.move_to(axes.c2p(q, price))
        guide_x.put_start_and_end_on(axes.c2p(0, price), axes.c2p(q, price))
        guide_y.put_start_and_end_on(axes.c2p(q, 0), axes.c2p(q, price))
        put(f"price {price:.1f}    quantity {q:.1f}", _pt(cx + w * 0.33, cy + 0.2))

    step(0.0, 0.0)
    return Live(group, step, "process")


def compound_interest(params: dict, box) -> Live:
    """Money growing year by year at compound interest (interest on the interest) beside simple interest: the bars
    pull away from the straight line more each year."""
    from manim import Dot, Line, Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    principal = float(params.get("principal") or 10000)
    rate = float(params.get("rate") or 10) / 100
    years = max(2, min(int(params.get("years") or 10), 30))
    money = str(params.get("currency") or "₹")
    final = principal * (1 + rate) ** years
    x0, y0 = cx - w * 0.42, cy - h * 0.36
    width, height = w * 0.6, h * 0.7
    bar_w = width / years * 0.7
    axis = Line(_pt(x0, y0), _pt(x0 + width, y0), color=pl.P.MUTED, stroke_width=2)
    bars, dots = [], []
    group = VGroup(axis)
    for n in range(1, years + 1):
        x = x0 + width * (n - 0.5) / years
        bar = Rectangle(width=bar_w, height=0.01, stroke_width=0, fill_color=pl.P.GREEN, fill_opacity=0.85)
        dot = Dot(radius=0.07, color=pl.P.ROSE)
        tag = pl.T(str(n), 14, pl.P.MUTED).move_to(_pt(x, y0 - 0.22))
        group.add(bar, dot, tag)
        bars.append((bar, x, principal * (1 + rate) ** n))
        dots.append((dot, x, principal * (1 + rate * n)))
    legend = VGroup(pl.T("compound: interest on the interest", 18, pl.P.GREEN), pl.T("simple: the same each year", 18, pl.P.ROSE))
    legend.arrange(DOWN3, aligned_edge=LEFT3, buff=0.15).move_to(_pt(cx + w * 0.33, cy + h * 0.28))
    read, put = _readout(" ", 22, pl.P.CREAM)
    group.add(legend, read)

    def money_text(v):
        return f"{money}{v:,.0f}"

    def step(t: float, p: float) -> None:
        shown = p * years
        for k, ((bar, x, amount), (dot, _, simple)) in enumerate(zip(bars, dots)):
            grow = min(1.0, max(0.0, shown - k))
            hgt = max(0.01, height * amount / final * grow)
            bar.stretch_to_fit_height(hgt)
            bar.move_to(_pt(x, y0 + hgt / 2))
            dot.move_to(_pt(x, y0 + height * simple / final))
            _show(dot, grow > 0.99)
            bar.set_opacity(0.85 if grow > 0 else 0)
        year = min(years, max(1, int(math.ceil(shown))))
        put(f"year {year}:  {money_text(principal * (1 + rate) ** year)}\n(simple: {money_text(principal * (1 + rate * year))})",
            _pt(cx + w * 0.33, cy - 0.3))

    step(0.0, 0.0)
    return Live(group, step, "process")


def seasons(params: dict, box) -> Live:
    """The Earth going round the Sun with its axis tilted the same way all year: the half facing the Sun is day;
    when the north leans toward the Sun it is summer there (June), away from it winter (December)."""
    from manim import Circle, Ellipse, Line, Sector, VGroup

    pl = _pl()
    cx, cy, w, h = box
    period = float(params.get("period") or 10.0)
    tilt = math.radians(23.5)
    rx, ry = w * 0.36, h * 0.3
    sun = Circle(radius=0.55, color=pl.P.GOLD, fill_color=pl.P.GOLD, fill_opacity=0.95).move_to(_pt(cx, cy))
    orbit = Ellipse(width=2 * rx, height=2 * ry, color=pl.P.MUTED, stroke_width=2).move_to(_pt(cx, cy))
    months = VGroup()
    for angle, name in ((0, "June: summer in the north"), (math.pi, "December: winter in the north"),
                        (math.pi / 2, "September"), (3 * math.pi / 2, "March")):
        at = _pt(cx + (rx + 0.2) * math.cos(angle), cy + (ry + 0.55) * math.sin(angle))
        months.add(pl.T(name, 17, pl.P.MUTED).move_to(at))
    r = 0.45
    earth = Circle(radius=r, color=pl.P.RIVER, fill_color=pl.P.RIVER, fill_opacity=0.9)
    night = Sector(radius=r, angle=math.pi, fill_color="#0B1320", fill_opacity=0.8, stroke_width=0)
    axis = Line(ORIGIN3, UP3, color=pl.P.CREAM, stroke_width=3)
    north = pl.T("N", 14, pl.P.CREAM)
    read, put = _readout(" ", 22, pl.P.GOLD)
    group = VGroup(orbit, months, sun, earth, night, axis, north, read)

    def step(t: float, p: float) -> None:
        angle = (2 * math.pi * t / period) % (2 * math.pi)
        at = _pt(cx + rx * math.cos(angle), cy + ry * math.sin(angle))
        earth.move_to(at)
        away = math.atan2(at[1] - cy, at[0] - cx)
        night.become(Sector(radius=r, angle=math.pi, start_angle=away - math.pi / 2, fill_color="#0B1320",
                            fill_opacity=0.8, stroke_width=0).move_arc_center_to(at))
        # The axis leans the same way all year (toward the Sun's side at June, on the right).
        lean = _pt(-math.sin(tilt), math.cos(tilt))
        axis.put_start_and_end_on(at - lean * (r + 0.25), at + lean * (r + 0.25))
        north.move_to(at + lean * (r + 0.42))
        # The north pole leans left: toward the Sun when the Earth is on the right (June), away on the left.
        toward = math.cos(angle)
        season = "summer" if toward > 0.4 else "winter" if toward < -0.4 else "autumn" if math.sin(angle) > 0 else "spring"
        put(f"northern hemisphere: {season}", _pt(cx, cy - h * 0.46))

    step(0.0, 0.0)
    return Live(group, step, "loop")


# ================================================================= the board's teaching formats

def numberline(params: dict, box) -> Live:
    """Hops along a number line, each with its jump drawn and labelled (+3, −4), ending on the answer: addition and
    subtraction as moving along the line."""
    from manim import ArcBetweenPoints, Dot, Line, VGroup

    pl = _pl()
    cx, cy, w, h = box
    lo, hi = float(params.get("from", 0)), float(params.get("to", 10))
    tick = float(params.get("step") or (1 if hi - lo <= 20 else 5))
    start = float(params.get("start", lo))
    hops = [float(x) for x in (params.get("hops") or [3, 2])][:6]
    left, right = cx - w * 0.44, cx + w * 0.44
    y = cy - h * 0.12

    def x_of(v):
        return left + (right - left) * (v - lo) / (hi - lo)

    line = Line(_pt(left - 0.2, y), _pt(right + 0.2, y), color=pl.P.CREAM, stroke_width=4)
    marks = VGroup()
    v = lo
    while v <= hi + 1e-9:
        marks.add(Line(_pt(x_of(v), y - 0.12), _pt(x_of(v), y + 0.12), color=pl.P.CREAM, stroke_width=3),
                  pl.T(f"{v:g}", 20, pl.P.MUTED).move_to(_pt(x_of(v), y - 0.42)))
        v += tick
    frog = Dot(radius=0.16, color=pl.P.GOLD)
    arcs, fulls, tags = [], [], []
    at = start
    tones = _tones()
    group = VGroup(line, marks)
    for i, hop in enumerate(hops):
        a, b = _pt(x_of(at), y + 0.05), _pt(x_of(at + hop), y + 0.05)
        full = ArcBetweenPoints(a, b, angle=-math.pi / 2 if hop > 0 else math.pi / 2, color=tones[i % len(tones)],
                                stroke_width=4)
        arc = full.copy()
        tag = pl.T(f"{'+' if hop > 0 else '−'}{abs(hop):g}", 22, tones[i % len(tones)])
        tag.move_to((a + b) / 2 + _pt(0, 0.35 + abs(b[0] - a[0]) * 0.28))
        group.add(arc, tag)
        arcs.append(arc)
        fulls.append(full)
        tags.append(tag)
        at += hop
    total = start + sum(hops)
    sentence = f"{start:g} " + " ".join(f"{'+' if x > 0 else '−'} {abs(x):g}" for x in hops) + f" = {total:g}"
    answer = pl.T(sentence, 30, pl.P.GOLD).move_to(_pt(cx, cy - h * 0.38))
    group.add(frog, answer)

    def step(t: float, p: float) -> None:
        n = len(hops)
        where = start
        for i in range(n):
            f = _ease(_part(p, 0.08 + 0.75 * i / n, 0.08 + 0.75 * (i + 1) / n))
            _partial(arcs[i], fulls[i], f)
            _show(tags[i], f > 0.5)
            if f > 0:
                where = sum(hops[:i], start) + hops[i] * f
        frog.move_to(_pt(x_of(where), y + 0.25 + 0.0))
        _show(answer, p > 0.88)

    step(0.0, 0.0)
    return Live(group, step, "process")


def _frac(text: str) -> tuple[int, int]:
    a, _, b = str(text).partition("/")
    return max(0, int(a or 0)), max(1, int(b or 1))


def fractions(params: dict, box) -> Live:
    """Fraction bars the same length, each cut into its equal parts and shaded part by part, one under another, so
    equal fractions line up and bigger ones reach farther."""
    from manim import DashedLine, Line, Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    items = [_frac(x) for x in (params.get("fractions") or ["1/2", "2/4", "3/8"])][:5]
    width = w * 0.62
    left = cx - w * 0.36
    row_h = min(0.7, h * 0.7 / len(items))
    tones = _tones()
    cells, labels = [], VGroup()
    group = VGroup()
    for i, (num, den) in enumerate(items):
        y = cy + h * 0.3 - i * (row_h + 0.25)
        row = []
        for k in range(den):
            cell = Rectangle(width=width / den, height=row_h, color=pl.P.CREAM, stroke_width=2,
                             fill_color=tones[i % len(tones)], fill_opacity=0)
            cell.move_to(_pt(left + width * (k + 0.5) / den, y))
            group.add(cell)
            row.append((cell, k < num))
        cells.append(row)
        labels.add(pl.T(f"{num}/{den}", 28, tones[i % len(tones)]).move_to(_pt(left + width + 0.7, y)))
    group.add(labels)
    values = [n / d for n, d in items]
    order = sorted(range(len(items)), key=lambda k: -values[k])
    parts = []
    for k in order:
        if parts and abs(values[k] - values[order[order.index(k) - 1]]) < 1e-9:
            parts.append(" = ")
        elif parts:
            parts.append(" > ")
        n, d = items[k]
        parts.append(f"{n}/{d}")
    verdict = pl.T("".join(parts), 30, pl.P.GOLD).move_to(_pt(cx, cy - h * 0.42))
    mark = DashedLine(_pt(left + width * max(values), cy + h * 0.38), _pt(left + width * max(values), cy - h * 0.3),
                      color=pl.P.GOLD, stroke_width=2)
    group.add(mark, verdict)
    del Line

    def step(t: float, p: float) -> None:
        n = len(cells)
        for i, row in enumerate(cells):
            f = _part(p, 0.05 + 0.7 * i / n, 0.05 + 0.7 * (i + 1) / n)
            shaded = sum(1 for _, on in row if on)
            for k, (cell, on) in enumerate(row):
                cell.set_fill(opacity=0.75 if on and f * shaded > k + 0.01 else 0.0)
        _show(mark, p > 0.8)
        _show(verdict, p > 0.85)

    step(0.0, 0.0)
    return Live(group, step, "process")


def placevalue(params: dict, box) -> Live:
    """A number built from place-value blocks: hundreds as flats of a hundred, tens as rods of ten, ones as cubes,
    then written in expanded form (243 = 200 + 40 + 3)."""
    from manim import Line, Rectangle, Square, VGroup

    pl = _pl()
    cx, cy, w, h = box
    number = max(0, min(int(params.get("number") or 243), 999))
    hundreds, tens, ones = number // 100, number // 10 % 10, number % 10
    unit = min(0.13, h * 0.5 / 10)
    cols = [cx - w * 0.3, cx, cx + w * 0.28]
    group = VGroup()
    heads = VGroup()
    for x, name, count, tone in zip(cols, ("hundreds", "tens", "ones"), (hundreds, tens, ones),
                                    (pl.P.RIVER, pl.P.GREEN, pl.P.GOLD)):
        heads.add(pl.T(f"{name}: {count}", 24, tone).move_to(_pt(x, cy + h * 0.4)))
    group.add(heads)
    blocks = []
    top = cy + h * 0.25
    for k in range(hundreds):
        flat = VGroup(Square(side_length=10 * unit, stroke_color=pl.P.CREAM, stroke_width=2, fill_color=pl.P.RIVER,
                             fill_opacity=0.6))
        for g in range(1, 10):
            flat.add(Line(_pt(-5 * unit + g * unit, -5 * unit), _pt(-5 * unit + g * unit, 5 * unit), stroke_width=1,
                          color=pl.P.CREAM, stroke_opacity=0.5),
                     Line(_pt(-5 * unit, -5 * unit + g * unit), _pt(5 * unit, -5 * unit + g * unit), stroke_width=1,
                          color=pl.P.CREAM, stroke_opacity=0.5))
        flat.move_to(_pt(cols[0] - 0.9 + (k % 3) * (10 * unit + 0.15) + k // 3 * 0.12, top - 5 * unit - k // 3 * 0.12))
        group.add(flat)
        blocks.append((flat, 0, k / max(hundreds, 1)))
    for k in range(tens):
        rod = Rectangle(width=unit, height=10 * unit, stroke_color=pl.P.CREAM, stroke_width=2, fill_color=pl.P.GREEN,
                        fill_opacity=0.7)
        rod.move_to(_pt(cols[1] - 4.5 * (unit + 0.06) + k * (unit + 0.06), top - 5 * unit))
        group.add(rod)
        blocks.append((rod, 1, k / max(tens, 1)))
    for k in range(ones):
        cube = Square(side_length=unit * 1.6, stroke_color=pl.P.CREAM, stroke_width=2, fill_color=pl.P.GOLD,
                      fill_opacity=0.8)
        cube.move_to(_pt(cols[2] - 0.5 + (k % 3) * (unit * 1.6 + 0.08), top - unit - (k // 3) * (unit * 1.6 + 0.08)))
        group.add(cube)
        blocks.append((cube, 2, k / max(ones, 1)))
    expanded = f"{number} = " + " + ".join(str(v) for v in (hundreds * 100, tens * 10, ones) if v) if number else "0"
    sentence = pl.T(expanded, 34, pl.P.CREAM).move_to(_pt(cx, cy - h * 0.38))
    group.add(sentence)

    def step(t: float, p: float) -> None:
        for block, column, order in blocks:
            _show(block, p >= 0.05 + 0.25 * column + 0.2 * order)
        for k, head in enumerate(heads):
            _show(head, p >= 0.05 + 0.25 * k)
        _show(sentence, p > 0.85)

    step(0.0, 0.0)
    return Live(group, step, "process")


def _circle_hits(c1, r1, c2, r2):
    """The two points where two circles cross (above and below the line of centres)."""
    d = float(np.linalg.norm(c2 - c1))
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    hgt = math.sqrt(max(r1 * r1 - a * a, 0.0))
    mid = c1 + (c2 - c1) * a / d
    off = _pt(-(c2 - c1)[1], (c2 - c1)[0]) / d * hgt
    return mid + off, mid - off


def construction(params: dict, box) -> Live:
    """A ruler-and-compass construction drawn step by step, each step said as it is drawn: a perpendicular bisector,
    an angle bisector, an equilateral triangle, or a triangle from its three sides."""
    from manim import Arc, Dot, Line, VGroup

    pl = _pl()
    cx, cy, w, h = box
    kind = str(params.get("construction") or "perpendicular_bisector")
    s = min(w, h) * 0.22
    steps = []          # (instruction, [(full mobject, colour)], [points to name])
    names = VGroup()

    def arc_at(centre, radius, mid_angle, spread=0.9):
        return Arc(radius=radius, start_angle=mid_angle - spread / 2, angle=spread, arc_center=centre)

    def name(text, at, d):
        names.add(pl.T(text, 22, pl.P.CREAM).move_to(at + d * 0.3))

    if kind == "angle_bisector":
        o = _pt(cx - 2 * s, cy - s)
        a = o + 3.6 * s * _pt(1, 0)
        b = o + 3.6 * s * _pt(math.cos(1.05), math.sin(1.05))
        r = 1.6 * s
        c, d = o + r * _pt(1, 0), o + r * _pt(math.cos(1.05), math.sin(1.05))
        e = max(_circle_hits(c, 1.3 * s, d, 1.3 * s), key=lambda q: float(np.linalg.norm(q - o)))   # beyond C and D
        ray = o + (e - o) * 3.4 * s / float(np.linalg.norm(e - o))
        steps = [("Draw the angle AOB.", [Line(o, a), Line(o, b)]),
                 ("With O as centre, draw an arc cutting OA at C and OB at D.", [arc_at(o, r, 0.52, 1.4)]),
                 ("With C and D as centres and the same radius, draw arcs that cross at E.",
                  [arc_at(c, 1.3 * s, 1.55, 0.7), arc_at(d, 1.3 * s, 0.0, 0.7)]),
                 ("Join OE: it bisects the angle (∠AOE = ∠EOB).", [Line(o, ray)])]
        for text, at, dd in (("O", o, _pt(-1, -0.5)), ("A", a, _pt(0.6, -0.6)), ("B", b, _pt(-0.5, 0.6)),
                             ("C", c, _pt(0.3, -0.8)), ("D", d, _pt(-0.8, 0.3)), ("E", e, _pt(0.7, 0.4))):
            name(text, at, dd)
    elif kind in ("equilateral_triangle", "triangle_sss"):
        sides = [float(x) for x in (params.get("sides") or [5, 4, 3])][:3] if kind == "triangle_sss" else [4, 4, 4]
        base, side_b, side_c = sides
        unit = 3.6 * s / max(sides)
        bpt, cpt = _pt(cx - base * unit / 2, cy - s), _pt(cx + base * unit / 2, cy - s)
        apt = _circle_hits(bpt, side_c * unit, cpt, side_b * unit)[0]
        mid_b = math.atan2(*(apt - bpt)[:2][::-1])
        mid_c = math.atan2(*(apt - cpt)[:2][::-1])
        steps = [(f"Draw BC = {base:g} cm.", [Line(bpt, cpt)]),
                 (f"With B as centre, radius {side_c:g} cm, draw an arc.", [arc_at(bpt, side_c * unit, mid_b, 0.8)]),
                 (f"With C as centre, radius {side_b:g} cm, draw an arc cutting it at A.",
                  [arc_at(cpt, side_b * unit, mid_c, 0.8)]),
                 ("Join AB and AC: the triangle is drawn.", [Line(bpt, apt), Line(cpt, apt)])]
        for text, at, dd in (("A", apt, _pt(0, 1)), ("B", bpt, _pt(-1, -0.5)), ("C", cpt, _pt(1, -0.5))):
            name(text, at, dd)
    else:
        a, b = _pt(cx - 1.8 * s, cy - 0.2 * s), _pt(cx + 1.8 * s, cy - 0.2 * s)
        r = 2.4 * s
        p_, q_ = _circle_hits(a, r, b, r)
        m = (a + b) / 2
        steps = [("Draw the line segment AB.", [Line(a, b)]),
                 ("With A as centre and more than half AB as radius, draw arcs above and below.",
                  [arc_at(a, r, 0.72, 0.5), arc_at(a, r, -0.72, 0.5)]),
                 ("With B as centre and the same radius, draw arcs cutting them at P and Q.",
                  [arc_at(b, r, math.pi - 0.72, 0.5), arc_at(b, r, math.pi + 0.72, 0.5)]),
                 ("Join PQ: it cuts AB at M, at right angles, and AM = MB.", [Line(p_, q_)])]
        for text, at, dd in (("A", a, _pt(-1, 0)), ("B", b, _pt(1, 0)), ("P", p_, _pt(0, 1)), ("Q", q_, _pt(0, -1)),
                             ("M", m, _pt(0.6, -0.6))):
            name(text, at, dd)
    group = VGroup()
    drawn = []
    tones = [pl.P.CREAM, pl.P.MUTED, pl.P.MUTED, pl.P.GOLD]
    for k, (_, mobs) in enumerate(steps):
        for full in mobs:
            full.set_stroke(tones[min(k, 3)], 4 if k in (0, len(steps) - 1) else 3)
            mob = full.copy()
            group.add(mob)
            drawn.append((k, mob, full))
    pencil = Dot(radius=0.07, color=pl.P.GOLD)
    words, put_words = _readout(" ", 22, pl.P.CREAM)
    group.add(names, pencil, words)

    def step(t: float, p: float) -> None:
        n = len(steps)
        current = 0
        for k, mob, full in drawn:
            f = _ease(_part(p, 0.04 + 0.86 * k / n, 0.04 + 0.86 * (k + 0.85) / n))
            _partial(mob, full, f)
            if 0 < f < 1:
                pencil.move_to(full.point_from_proportion(f))
            if f > 0:
                current = k
        _show(pencil, p < 0.9)
        _show(names, p > 0.05)
        put_words(f"{current + 1}. {steps[current][0]}", _pt(cx, cy - h * 0.44))

    step(0.0, 0.0)
    return Live(group, step, "process")


def balance(params: dict, box) -> Live:
    """An equation as a balance: the same thing done to both pans keeps it level, step by step to the answer
    (2x + 3 = 11, take 3 from both sides, halve both sides, x = 4)."""
    from manim import Arc, Line, Polygon, VGroup

    pl = _pl()
    cx, cy, w, h = box
    lines = [str(x) for x in (params.get("steps") or ["2x + 3 = 11", "2x = 8", "x = 4"])][:6]
    notes = [str(x) for x in (params.get("notes") or ["take 3 from both sides", "halve both sides"])]
    sides = [(a.strip(), b.strip()) for a, _, b in (ln.partition("=") for ln in lines)]
    pivot = _pt(cx, cy - h * 0.05)
    arm = w * 0.3
    stand = Polygon(pivot, pivot + _pt(-0.45, -1.3), pivot + _pt(0.45, -1.3), color=pl.P.MUTED, stroke_width=3,
                    fill_color=pl.P.MUTED, fill_opacity=0.4)
    beam = Line(pivot - _pt(arm, 0), pivot + _pt(arm, 0), color=pl.P.CREAM, stroke_width=6)
    pans = []
    group = VGroup(stand, beam)
    for sign in (-1, 1):
        string = Line(ORIGIN3, RIGHT3, color=pl.P.MUTED, stroke_width=2)
        dish = Arc(radius=1.0, start_angle=math.pi, angle=math.pi, color=pl.P.CREAM, stroke_width=4)
        text, put = _readout(" ", 34, pl.P.GOLD)
        group.add(string, dish, text)
        pans.append((sign, string, dish, put))
    note, put_note = _readout(" ", 22, pl.P.CREAM)
    group.add(note)

    def step(t: float, p: float) -> None:
        n = len(sides)
        span = 0.85 / max(n - 1, 1)
        stage = min(n - 1, int(p / span)) if n > 1 else 0
        inside = (p - stage * span) / span if n > 1 and stage < n - 1 else 0.0
        # Within a change: the left pan changes first (the beam dips), then the right (level again).
        left_done = inside > 0.35 and stage < n - 1
        right_done = inside > 0.7 and stage < n - 1
        tip = math.radians(7) * (1 if left_done and not right_done else 0)
        for sign, string, dish, put in pans:
            end = pivot + sign * arm * _pt(math.cos(tip), -sign * math.sin(tip))
            string.put_start_and_end_on(end, end + _pt(0, -1.1))
            dish.move_to(end + _pt(0, -1.6))
            changed = left_done if sign < 0 else right_done
            words = sides[stage + 1 if changed else stage][0 if sign < 0 else 1]
            put(words, end + _pt(0, -1.25))
        beam.put_start_and_end_on(pivot + arm * _pt(-math.cos(tip), math.sin(tip)),
                                  pivot + arm * _pt(math.cos(tip), -math.sin(tip)))
        if stage < n - 1 and inside > 0.05:
            put_note(notes[stage] if stage < len(notes) else "the same to both sides", _pt(cx, cy + h * 0.4))
        else:
            put_note(lines[stage] if stage == n - 1 else lines[0], _pt(cx, cy + h * 0.4))

    step(0.0, 0.0)
    return Live(group, step, "process")


def timeline_zoom(params: dict, box) -> Live:
    """A timeline that starts wide (a century or more) and zooms into a decade: events spread out as the years
    open up, the ones outside the window slide away."""
    from manim import Dot, Line, VGroup

    pl = _pl()
    cx, cy, w, h = box
    events = [(float(e[0]), str(e[1])) for e in (params.get("events") or [
        [1857, "First War of Independence"], [1885, "Congress founded"], [1919, "Jallianwala Bagh"],
        [1930, "Dandi March"], [1942, "Quit India"], [1947, "Independence"], [1950, "Republic"]])][:12]
    years = [y for y, _ in events]
    wide = [float(x) for x in (params.get("range") or [min(years) - 5, max(years) + 5])]
    zoom = [float(x) for x in (params.get("zoom") or [1940, 1950])]
    left, right = cx - w * 0.44, cx + w * 0.44
    y = cy
    axis = Line(_pt(left, y), _pt(right, y), color=pl.P.CREAM, stroke_width=4)
    ticks = [(Line(ORIGIN3, UP3, color=pl.P.MUTED, stroke_width=2), _readout(" ", 16, pl.P.MUTED)) for _ in range(12)]
    marks = []
    group = VGroup(axis)
    for tick, (text, _) in ticks:
        group.add(tick, text)
    for i, (year, what) in enumerate(events):
        dot = Dot(radius=0.1, color=pl.P.GOLD)
        stem = Line(ORIGIN3, UP3, color=pl.P.MUTED, stroke_width=2)
        tag = pl.T(f"{year:g}  {what}", 18, pl.P.CREAM)
        group.add(stem, dot, tag)
        marks.append((year, dot, stem, tag, 1 if i % 2 == 0 else -1))
    window, put_window = _readout(" ", 24, pl.P.GOLD)
    group.add(window)

    def step(t: float, p: float) -> None:
        z = _ease(_part(p, 0.35, 0.7))
        # Zoom in a log scale of the span, so it does not rush at the end.
        span0, span1 = wide[1] - wide[0], zoom[1] - zoom[0]
        span = span0 * (span1 / span0) ** z
        mid = (wide[0] + wide[1]) / 2 + ((zoom[0] + zoom[1]) / 2 - (wide[0] + wide[1]) / 2) * z
        a, b = mid - span / 2, mid + span / 2

        def x_of(v):
            # Off the window: parked at its edge, hidden (far off the board, it made the clip's picture huge).
            return min(max(left + (right - left) * (v - a) / (b - a), left), right)

        every = next(s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500) if span / s <= 11)
        first = math.ceil(a / every) * every
        for k, (tick, (text, put)) in enumerate(ticks):
            v = first + k * every
            inside = v <= b
            tick.put_start_and_end_on(_pt(x_of(v), y - 0.12), _pt(x_of(v), y + 0.12))
            put(f"{v:g}" if inside else " ", _pt(x_of(v), y - 0.4))
            _show(tick, inside)
        for k, (year, dot, stem, tag, side) in enumerate(marks):
            inside = a <= year <= b
            x = x_of(year)
            level = side * (0.75 + 0.55 * (k // 2 % 2))
            dot.move_to(_pt(x, y))
            stem.put_start_and_end_on(_pt(x, y), _pt(x, y + level - 0.15 * side))
            tag.move_to(_pt(x, y + level + 0.1 * side))
            for m in (dot, stem, tag):
                _show(m, inside and p > 0.04 * k)
        put_window(f"{a:.0f} – {b:.0f}", _pt(cx, cy + h * 0.44))

    step(0.0, 0.0)
    return Live(group, step, "process")


# ----------------------------------------------------------------- data stories

def bar_race(params: dict, box) -> Live:
    """A bar-chart race: each year the bars grow and overtake each other, sorted biggest at the top, the year
    ticking by."""
    from manim import Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    years = [str(y) for y in (params.get("years") or [2000, 2005, 2010, 2015, 2020])]
    series = {str(k): [float(v) for v in vals] for k, vals in (params.get("series") or {
        "China": [1211, 1088, 6087, 11062, 14687], "USA": [10252, 13037, 15049, 18206, 21060],
        "Japan": [4968, 4831, 5759, 4445, 5040], "India": [468, 820, 1676, 2104, 2667],
        "Germany": [1950, 2846, 3400, 3360, 3890]}).items()}
    unit = str(params.get("unit") or "")
    top = int(params.get("top") or 8)
    names = list(series)[:12]
    tones = _tones()
    row_h = h * 0.68 / min(top, len(names))
    left = cx - w * 0.3
    bars = {}
    group = VGroup()
    for i, name in enumerate(names):
        bar = Rectangle(width=0.1, height=row_h * 0.75, stroke_width=0, fill_color=tones[i % len(tones)], fill_opacity=0.9)
        label = pl.T(name, 20, pl.P.CREAM)
        value, put = _readout(" ", 18, pl.P.CREAM)
        group.add(bar, label, value)
        bars[name] = (bar, label, put)
    year, put_year = _readout(" ", 54, pl.P.GOLD)
    caption = pl.T(str(params.get("label") or ""), 20, pl.P.MUTED).move_to(_pt(cx, cy + h * 0.45))
    group.add(year, caption)

    def at(name, f):
        vals = series[name]
        i = min(int(f), len(vals) - 1)
        j = min(i + 1, len(vals) - 1)
        return vals[i] + (vals[j] - vals[i]) * (f - i)

    def ranks(f):
        order = sorted(names, key=lambda n: -at(n, f))
        return {n: k for k, n in enumerate(order)}

    def step(t: float, p: float) -> None:
        f = p * (len(years) - 1)
        lo, hi = ranks(math.floor(f)), ranks(min(math.ceil(f), len(years) - 1))
        frac = _ease(f - math.floor(f))
        biggest = max(at(n, f) for n in names) or 1.0
        for name, (bar, label, put) in bars.items():
            rank = lo[name] + (hi[name] - lo[name]) * frac
            y = cy + h * 0.3 - rank * row_h
            v = at(name, f)
            length = max(0.05, w * 0.55 * v / biggest)
            bar.stretch_to_fit_width(length)
            bar.move_to(_pt(left + length / 2, y))
            label.move_to(_pt(left - 0.2, y)).align_to(_pt(left - 0.2, y, ), RIGHT3)
            put(f"{v:,.0f} {unit}".strip(), _pt(left + length + 0.6, y))
            visible = rank < top - 0.01
            for m in (bar, label):
                _show(m, visible, 0.9 if m is bar else 1.0)
        put_year(years[min(int(round(f)), len(years) - 1)], _pt(cx + w * 0.38, cy - h * 0.32))

    step(0.0, 0.0)
    return Live(group, step, "process")


def pyramid(params: dict, box) -> Live:
    """A population pyramid, men on the left and women on the right, age groups up the middle; with a later year it
    changes shape as the years pass (a young country growing older)."""
    from manim import Line, Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    ages = [str(a) for a in (params.get("ages") or ["0–9", "10–19", "20–29", "30–39", "40–49", "50–59", "60–69", "70+"])]
    male = [float(v) for v in (params.get("male") or [12.5, 11.8, 10.6, 8.9, 7.0, 5.2, 3.3, 1.6])]
    female = [float(v) for v in (params.get("female") or [11.6, 11.0, 10.2, 8.7, 6.9, 5.3, 3.6, 2.0])]
    later = params.get("later") or {}
    male2 = [float(v) for v in (later.get("male") or male)]
    female2 = [float(v) for v in (later.get("female") or female)]
    first_year, last_year = str(params.get("year") or ""), str(later.get("year") or "")
    n = len(ages)
    biggest = max(male + female + male2 + female2) or 1.0
    half = w * 0.36
    row_h = h * 0.72 / n
    base = cy - h * 0.36
    middle = Line(_pt(cx, base), _pt(cx, base + n * row_h), color=pl.P.MUTED, stroke_width=2)
    group = VGroup(middle, pl.T("men", 22, pl.P.RIVER).move_to(_pt(cx - half * 0.6, cy + h * 0.44)),
                   pl.T("women", 22, pl.P.ROSE).move_to(_pt(cx + half * 0.6, cy + h * 0.44)))
    bars = []
    for i, age in enumerate(ages):
        y = base + (i + 0.5) * row_h
        m = Rectangle(width=0.1, height=row_h * 0.85, stroke_width=0, fill_color=pl.P.RIVER, fill_opacity=0.85)
        f = Rectangle(width=0.1, height=row_h * 0.85, stroke_width=0, fill_color=pl.P.ROSE, fill_opacity=0.85)
        group.add(m, f, pl.T(age, 15, pl.P.CREAM).move_to(_pt(cx, y)))
        bars.append((y, m, f, i))
    year, put_year = _readout(" ", 34, pl.P.GOLD)
    group.add(year)

    def step(t: float, p: float) -> None:
        grow = _ease(_part(p, 0.0, 0.25))
        change = _ease(_part(p, 0.4, 0.9)) if later else 0.0
        for y, m, f, i in bars:
            mv = (male[i] + (male2[i] - male[i]) * change) * grow
            fv = (female[i] + (female2[i] - female[i]) * change) * grow
            lm, lf = max(0.02, half * mv / biggest), max(0.02, half * fv / biggest)
            m.stretch_to_fit_width(lm).move_to(_pt(cx - 0.45 - lm / 2, y))
            f.stretch_to_fit_width(lf).move_to(_pt(cx + 0.45 + lf / 2, y))
        shown = last_year if later and change > 0.5 else first_year
        put_year(shown or " ", _pt(cx + w * 0.38, cy + h * 0.3))

    step(0.0, 0.0)
    return Live(group, step, "process")


def trend(params: dict, box) -> Live:
    """A quantity over time drawn as it happened, a dot riding the line with its value, the highest point marked at
    the end (GDP over the years, temperature, population)."""
    from manim import Dot, VGroup, VMobject

    pl = _pl()
    cx, cy, w, h = box
    points = [(float(a), float(b)) for a, b in (params.get("points") or [
        [1991, 270], [1996, 400], [2001, 480], [2006, 940], [2011, 1820], [2016, 2290], [2021, 3150]])]
    unit = str(params.get("unit") or "")
    xs, ys = [a for a, _ in points], [b for _, b in points]
    y_lo = min(0.0, min(ys))
    y_hi = max(ys) * 1.12
    step_x = max(1, round((xs[-1] - xs[0]) / 5))
    axes = _axes([xs[0], xs[-1], step_x], [y_lo, y_hi, (y_hi - y_lo) / 4], w * 0.7, h * 0.68, _pt(cx - w * 0.05, cy - 0.1),
                 numbers=False)
    from manim import VGroup as _Group

    ticks = _Group(*[pl.T(f"{x:g}", 15, pl.P.MUTED).move_to(axes.c2p(x, y_lo) + _pt(0, -0.3)) for x in xs],
                   *[pl.T(f"{v:,.0f}", 15, pl.P.MUTED).next_to(axes.c2p(xs[0], v), LEFT3, buff=0.15)
                     for v in np.linspace(y_lo, max(ys), 3)])
    line = VMobject(stroke_color=pl.P.GOLD, stroke_width=5)
    dot = Dot(radius=0.1, color=pl.P.GOLD)
    read, put = _readout(" ", 22, pl.P.CREAM)
    title = pl.T(str(params.get("label") or ""), 22, pl.P.MUTED).next_to(axes, UP3, buff=0.15)
    peak = max(range(len(points)), key=lambda k: ys[k])
    peak_tag = pl.T(f"highest: {ys[peak]:,.0f} {unit} ({xs[peak]:g})".strip(), 20, pl.P.GREEN)
    peak_tag.next_to(axes.c2p(xs[peak], ys[peak]), UP3, buff=0.2)
    group = VGroup(axes, ticks, title, line, dot, read, peak_tag)

    def value(x):
        return float(np.interp(x, xs, ys))

    def step(t: float, p: float) -> None:
        upto = xs[0] + (xs[-1] - xs[0]) * _part(p, 0.03, 0.85)
        sample = [x for x in xs if x < upto] + [upto]
        pts = [axes.c2p(x, value(x)) for x in sample]
        line.set_points_as_corners(pts if len(pts) > 1 else pts + [pts[0] + _pt(1e-3, 0)])
        dot.move_to(pts[-1])
        put(f"{upto:.0f}: {value(upto):,.0f} {unit}".strip() if p <= 0.88 else " ", pts[-1] + _pt(0, 0.45))
        _show(peak_tag, p > 0.88)

    step(0.0, 0.0)
    return Live(group, step, "process")


def columns(params: dict, box) -> Live:
    """Columns that grow one after another with their values (rainfall by month, marks by subject), the tallest
    picked out at the end."""
    from manim import Line, Rectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    labels = [str(x) for x in (params.get("labels") or ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                                                          "Oct", "Nov", "Dec"])]
    values = [float(v) for v in (params.get("values") or [20, 25, 30, 35, 70, 520, 680, 600, 340, 90, 25, 10])]
    unit = str(params.get("unit") or "")
    n = min(len(labels), len(values))
    biggest = max(values[:n]) or 1.0
    width = w * 0.82
    left = cx - width / 2
    base = cy - h * 0.34
    tall = h * 0.62
    slot = width / n
    axis = Line(_pt(left, base), _pt(left + width, base), color=pl.P.MUTED, stroke_width=2)
    title = pl.T(str(params.get("label") or ""), 22, pl.P.MUTED).move_to(_pt(cx, cy + h * 0.44))
    group = VGroup(axis, title)
    bars = []
    best = max(range(n), key=lambda k: values[k])
    for k in range(n):
        x = left + slot * (k + 0.5)
        bar = Rectangle(width=slot * 0.7, height=0.01, stroke_width=0, fill_color=pl.P.RIVER, fill_opacity=0.85)
        tag = pl.T(labels[k], 16, pl.P.CREAM).move_to(_pt(x, base - 0.25))
        num = pl.T(f"{values[k]:g}", 15, pl.P.CREAM)
        group.add(bar, tag, num)
        bars.append((bar, num, x, values[k], k))
    unit_tag = pl.T(unit, 16, pl.P.MUTED).move_to(_pt(left - 0.3, base + tall + 0.1))
    group.add(unit_tag)

    def step(t: float, p: float) -> None:
        for bar, num, x, v, k in bars:
            f = _ease(_part(p, 0.05 + 0.75 * k / n, 0.05 + 0.75 * (k + 1.5) / n))
            hgt = max(0.01, tall * v / biggest * f)
            bar.stretch_to_fit_height(hgt)
            bar.move_to(_pt(x, base + hgt / 2))
            bar.set_color(pl.P.GOLD if k == best and p > 0.88 else pl.P.RIVER)
            num.move_to(_pt(x, base + hgt + 0.2))
            _show(num, f > 0.95)

    step(0.0, 0.0)
    return Live(group, step, "process")


# ----------------------------------------------------------------- layers and differences

EARTH = [["crust", "5–70 km, solid rock"], ["mantle", "about 2,900 km, hot rock that flows slowly"],
         ["outer core", "liquid iron and nickel"], ["inner core", "solid iron, about 5,400 °C"]]


def layers(params: dict, box) -> Live:
    """A cut-away that peels from the outside in, one layer at a time: each named with a note as it is reached
    (the Earth's layers, a fruit, the atmosphere, soil)."""
    from manim import Line, Rectangle, Sector, VGroup

    pl = _pl()
    cx, cy, w, h = box
    rows = []
    for item in (params.get("layers") or EARTH)[:7]:
        if isinstance(item, dict):
            rows.append((str(item.get("name", "")), str(item.get("note", ""))))
        elif isinstance(item, (list, tuple)):
            rows.append((str(item[0]), str(item[1]) if len(item) > 1 else ""))
        else:
            rows.append((str(item), ""))
    shape = str(params.get("shape") or "circle")
    tones = [pl.P.SAND, pl.P.TERRA, pl.P.GOLD, pl.P.ROSE, pl.P.RIVER, pl.P.GREEN, pl.P.VIOLET]
    n = len(rows)
    group = VGroup()
    pieces, tags = [], []
    if shape == "stack":
        top, height = cy + h * 0.38, h * 0.72
        for i, (name, note) in enumerate(rows):
            band = Rectangle(width=w * 0.38, height=height / n, stroke_color=pl.P.BG, stroke_width=2,
                             fill_color=tones[i % len(tones)], fill_opacity=0.8)
            band.move_to(_pt(cx - w * 0.22, top - height * (i + 0.5) / n))
            tag = pl.T(name + (f": {note}" if note else ""), 20, pl.P.CREAM)
            tag.next_to(band, RIGHT3, buff=0.5)
            lead = Line(band.get_right(), tag.get_left(), color=pl.P.MUTED, stroke_width=2)
            group.add(band, lead, tag)
            pieces.append(band)
            tags.append((tag, lead))
    else:
        big = min(h * 0.42, w * 0.25)
        centre = _pt(cx - w * 0.22, cy)
        for i, (name, note) in enumerate(rows):
            r = big * (1 - i / n)
            # The front half cut away (a quarter wedge): the layers show as rings inside.
            wedge = Sector(radius=r, angle=1.5 * math.pi, start_angle=math.pi / 2, stroke_color=pl.P.BG, stroke_width=2,
                           fill_color=tones[i % len(tones)], fill_opacity=0.85).move_arc_center_to(centre)
            cut = Sector(radius=r, angle=math.pi / 2, start_angle=0, stroke_color=pl.P.BG, stroke_width=2,
                         fill_color=tones[i % len(tones)], fill_opacity=0.85).move_arc_center_to(centre)
            point = centre + (r - big / n / 2) * _pt(math.cos(math.pi / 4), math.sin(math.pi / 4))
            tag = pl.T(name + (f": {note}" if note else ""), 19, pl.P.CREAM)
            tag.move_to(_pt(cx + w * 0.22, cy + h * 0.32 - i * (h * 0.64 / max(n - 1, 1))))
            lead = Line(point, tag.get_left() + _pt(-0.1, 0), color=pl.P.MUTED, stroke_width=2)
            group.add(wedge, cut)
            pieces.append(cut)
            tags.append((tag, lead))
        for tag, lead in tags:
            group.add(lead, tag)
    del pieces

    def step(t: float, p: float) -> None:
        for i, (tag, lead) in enumerate(tags):
            on = p >= 0.06 + 0.8 * i / n
            _show(tag, on)
            _show(lead, on)
            tag.set_color(pl.P.GOLD if on and p < 0.06 + 0.8 * (i + 1) / n else pl.P.CREAM)

    step(0.0, 0.0)
    return Live(group, step, "process")


def differences(params: dict, box) -> Live:
    """Flip cards of differences: two headings, and row after row a pair of cards turns over to show how the two
    differ on one point (plant and animal cells, mitosis and meiosis)."""
    from manim import RoundedRectangle, VGroup

    pl = _pl()
    cx, cy, w, h = box
    left_title = str(params.get("left") or "Plant cell")
    right_title = str(params.get("right") or "Animal cell")
    rows = [(str(a), str(b)) for a, b in (params.get("rows") or [
        ["has a cell wall", "no cell wall"], ["large central vacuole", "small vacuoles, if any"],
        ["chloroplasts make food", "no chloroplasts"], ["regular, boxy shape", "round, irregular shape"]])][:6]
    n = len(rows)
    col_w = w * 0.4
    row_h = min(0.95, h * 0.7 / n)
    heads = VGroup(pl.T(left_title, 28, pl.P.GREEN).move_to(_pt(cx - w * 0.22, cy + h * 0.4)),
                   pl.T(right_title, 28, pl.P.ROSE).move_to(_pt(cx + w * 0.22, cy + h * 0.4)))
    group = VGroup(heads)
    cards = []
    for i, (a, b) in enumerate(rows):
        y = cy + h * 0.28 - (i + 0.5) * (row_h + 0.12)
        for x, text, tone in ((cx - w * 0.22, a, pl.P.GREEN), (cx + w * 0.22, b, pl.P.ROSE)):
            card = RoundedRectangle(corner_radius=0.12, width=col_w, height=row_h, color=tone, stroke_width=2,
                                    fill_color=tone, fill_opacity=0.15).move_to(_pt(x, y))
            words = pl.T(pl.wrap(text, 34), 18, pl.P.CREAM).move_to(_pt(x, y))
            if words.width > col_w - 0.3:
                words.scale_to_fit_width(col_w - 0.3)
            pair = VGroup(card, words)
            group.add(pair)
            cards.append((pair, i, x, y))
    full = {id(pair): pair.copy() for pair, *_ in cards}

    def step(t: float, p: float) -> None:
        for pair, i, x, y in cards:
            f = _ease(_part(p, 0.05 + 0.85 * i / n, 0.05 + 0.85 * (i + 0.6) / n))
            # A card turning over: it grows from a line to its full height.
            pair.become(full[id(pair)].copy().stretch(max(f, 0.02), 1).move_to(_pt(x, y)))
            _show(pair, f > 0.02)

    step(0.0, 0.0)
    return Live(group, step, "process")


# ================================================================= registry (live.py merges it into BUILDERS)

# kind: (builder, its settings for the prompt and the lint, "loop" | "process")
MORE: dict = {}


def _register(kind: str, builder, settings: str) -> None:
    MORE[kind] = (builder, settings)


_register("pendulum_period", pendulum_period, "lengths ([0.5, 1, 2] m), g (9.8), angle (18°): T read out for each")
_register("projectile_angle", projectile_angle, "angles ([15, 30, 45, 60, 75]), speed (20 m/s), g: one after another")
_register("circuit_brightness", circuit_brightness, "voltage (6): two bulbs in series (dim) beside parallel (bright)")
_register("magnetic_wire", magnetic_wire, "current (out | in): field circles round a wire, compass needles")
_register("lens_image", lens_image, "from_u (-3), to_u (-0.6), in focal lengths: the object walks in, image follows")
_register("sound", sound, "wavelength, speed: compressions and rarefactions, pressure wave below")
_register("balance_equation", balance_equation, "reactants [[\"H2\", 2], [\"O2\", 1]], products [[\"H2O\", 2]] "
          "(formula, its coefficient): coefficients set one by one, atoms counted each side")
_register("ph_scale", ph_scale, "substances ([[name, pH], ...]; everyday ones by default): put on the scale one by one")
_register("electrolysis", electrolysis, "cation (H⁺), anion (OH⁻), cathode_gas (H₂), anode_gas (O₂): ions drift, gas bubbles")
_register("states", states, "the particles of a solid, then liquid, then gas as it is heated, with a thermometer")
_register("digestion", digestion, "food travels down the gut, each organ named with what happens there")
_register("double_circulation", double_circulation, "blood round heart, lungs and body; blue without oxygen, red with it")
_register("photosynthesis", photosynthesis, "a leaf: light, CO₂ and water in; oxygen out, glucose made; then the equation")
_register("punnett", punnett, "parents ([\"Tt\", \"Tt\"]), traits ({\"T\": \"tall\", \"t\": \"short\"}): the square "
          "fills, then the ratios")
_register("food_web", food_web, "species ([{name, level, eats: [...]}], a pond/grassland web by default), remove "
          "(\"frog\"): energy flows up; take one away and its prey grows, its predators go short")
_register("unit_circle", unit_circle, "period (6 s): a point round the circle, its height drawn out as the sine wave")
_register("area_fill", area_fill, "expr (\"x^2\"), from (0), to (2): 2, 4, 8 ... 64 rectangles closing in on the area")
_register("probability", probability, "trial (coin | dice), trials (300), seed: the share of heads (sixes) settles at 1/2 (1/6)")
_register("transform_graph", transform_graph, "expr (\"x^2\"), shift ([h, k]), stretch ([a, b]), reflect (x | y), x, y "
          "(ranges): y = a·f(b(x − h)) + k moving from y = f(x)")
_register("water_cycle", water_cycle, "rates ({evaporation: \"...\"}, optional), period: evaporation, condensation, "
          "precipitation, runoff going round")
_register("supply_demand", supply_demand, "shift (demand_up | demand_down | supply_up | supply_down), amount (2): the "
          "curve moves, the equilibrium price and quantity follow")
_register("compound_interest", compound_interest, "principal (10000), rate (10 %), years (10), currency (₹): compound "
          "bars beside simple interest")
_register("seasons", seasons, "period (10 s): the Earth round the Sun, axis tilted, day and night, the north's season")
_register("numberline", numberline, "from (0), to (10), start (2), hops ([3, 2, -4]), step (tick spacing): jumps "
          "drawn and labelled, the sum written")
_register("fractions", fractions, "fractions ([\"1/2\", \"2/4\", \"3/8\"]): equal bars cut and shaded, then compared")
_register("placevalue", placevalue, "number (243, up to 999): hundreds flats, tens rods, ones cubes, then expanded form")
_register("construction", construction, "construction (perpendicular_bisector | angle_bisector | equilateral_triangle | "
          "triangle_sss), sides ([5, 4, 3] cm, for triangle_sss): ruler and compass, step by step, each step written")
_register("balance", balance, "steps ([\"2x + 3 = 11\", \"2x = 8\", \"x = 4\"]), notes ([\"take 3 from both sides\", "
          "...]): the equation as a balance, the same done to both pans")
_register("timeline_zoom", timeline_zoom, "events ([[year, \"what\"], ...]), range ([from, to], all of them), zoom "
          "([1940, 1950]): a wide timeline zooming into a decade")
_register("bar_race", bar_race, "years ([...]), series ({name: [a value a year]}), unit, top (8), label: bars "
          "overtaking each other year by year")
_register("pyramid", pyramid, "ages ([\"0–9\", ...]), male ([%]), female ([%]), year, later ({year, male, female}): "
          "a population pyramid changing shape")
_register("trend", trend, "points ([[year, value], ...]), unit, label: a line drawn over time, the highest marked")
_register("columns", columns, "labels ([\"Jan\", ...]), values ([...]), unit, label: columns growing one by one "
          "(rainfall by month), the tallest picked out")
_register("layers", layers, "layers ([[name, note], ...], outside first; the Earth's by default), shape (circle | "
          "stack): a cut-away named layer by layer")
_register("differences", differences, "left (\"Plant cell\"), right (\"Animal cell\"), rows ([[left point, right "
          "point], ...]): flip cards of differences, row by row")
_register("rusting", rusting, "days (7): nails in air + water, boiled water + oil, dry air; only the first rusts")

# The sims that run as loops (on t) rather than once over the line.
LOOPING = {"pendulum_period", "circuit_brightness", "magnetic_wire", "sound", "electrolysis", "double_circulation",
           "unit_circle", "water_cycle", "seasons"}
