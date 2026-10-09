"""Live pictures: things that move continuously while a line is said (the `sim` op, and the graph and sketch
steps `trace`, `sweep`, `counter` and the continuous motions).

Each builder draws its picture into a box and returns a `Live`: the picture, and `step(t, p)`, which puts it in its
state `t` seconds after the line started moving it, `p` (0 to 1) of the way through the line. A *loop* (an orbit,
a wave, a beating heart) runs on `t`; a *process* (a titration, cell division, a decay) runs on `p` and ends where
the line does. The engine (stem.py) attaches `step` as an updater for the length of the line; the exporter
(dsl/export_dsl.py) bakes whatever it moves into a clip the phone plays as program, not video.

Everything here is plain Manim: pictures of points and paths, Pango text for the numbers (MathTex would run LaTeX
for every frame's value), and deterministic motion (a seeded random generator), so a build is the same every time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

SIMS = ("orbit", "wave", "collision", "field", "refraction", "titration", "mitosis", "heart", "gas", "decay")
LOOPS = {"orbit", "wave", "field", "heart", "gas"}

# What each sim takes, for the lint and for the model's prompt.
SIM_PARAMS = {
    "orbit": "period (s, 4), radius, vectors (true: v and a arrows), labels {body, centre}",
    "wave": "wave (travelling | standing | superpose), amplitude (1), wavelength (3), speed (1.5), "
            "labels {wave}",
    "collision": "m1 (2), m2 (1), u1 (3), u2 (-1), elastic (true), labels {left, right}",
    "field": "charges ([[+1, -2, 0], [-1, 2, 0]]: q, x, y), lines (12), test (true: a test charge drifts)",
    "refraction": "n1 (1.5), n2 (1.0), from_deg (10), to_deg (70), labels {top, bottom}",
    "titration": "kind (strong | weak), indicator (phenolphthalein | methyl orange), equivalence (25 mL)",
    "mitosis": "stages (true: the stage named as it goes)",
    "heart": "bpm (72), flow (true: blood moving through)",
    "gas": "particles (24), speed (1), hot (false)",
    "decay": "atoms (64), half_life (s of the line, 0.35 of it), curve (true)",
}


@dataclass
class Live:
    body: object
    step: Callable[[float, float], None]
    mode: str = "loop"                 # "loop": runs on t; "process": runs on p over the line
    parts: dict = field(default_factory=dict)


def _engine():
    import pocket_lecture as pl

    return pl


def _num(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    return text.replace("-", "−")


def _readout(label: str, size: float = 22, color=None):
    """A text readout that can be re-set every frame (Pango text, cached per string)."""
    pl = _engine()
    mob = pl.T(label, size, color or pl.P.CREAM)

    def put(text: str, at=None):
        new = pl.T(text, size, color or pl.P.CREAM)
        new.move_to(at if at is not None else mob.get_center())
        if at is None:
            new.align_to(mob, np.array([-1, 0, 0]))
        mob.become(new)

    return mob, put


def _frame(box, pad=0.25):
    cx, cy, w, h = box
    return cx - w / 2 + pad, cx + w / 2 - pad, cy - h / 2 + pad, cy + h / 2 - pad


# ---------------------------------------------------------------- sims

def orbit(params: dict, box) -> Live:
    from manim import Arrow, Circle, DashedVMobject, Dot, VGroup, VMobject

    pl = _engine()
    cx, cy, w, h = box
    r = float(params.get("radius") or min(w, h) * 0.32)
    period = float(params.get("period") or 4.0)
    centre = np.array([cx, cy - 0.1, 0.0])
    labels = params.get("labels") or {}
    path = DashedVMobject(Circle(radius=r, color=pl.P.MUTED, stroke_width=2).move_to(centre), num_dashes=40)
    hub = Dot(centre, radius=0.12, color=pl.P.GOLD)
    hub_label = pl.T(str(labels.get("centre", "")), 18, pl.P.MUTED).next_to(hub, np.array([0, -1, 0]), buff=0.15)
    body = Dot(centre + np.array([r, 0, 0]), radius=0.16, color=pl.P.RIVER)
    body_label = pl.T(str(labels.get("body", "")), 18, pl.P.RIVER)
    trail = VMobject(stroke_color=pl.P.RIVER, stroke_width=4, stroke_opacity=0.6)
    vectors = params.get("vectors", True)
    v = Arrow(ORIGIN3, ORIGIN3 + np.array([1, 0, 0]), color=pl.P.GREEN, buff=0, stroke_width=5)
    a = Arrow(ORIGIN3, ORIGIN3 + np.array([1, 0, 0]), color=pl.P.ROSE, buff=0, stroke_width=5)
    v_label, a_label = pl.T("v", 20, pl.P.GREEN), pl.T("a", 20, pl.P.ROSE)
    parts = [path, trail, hub, hub_label, body, body_label]
    if vectors:
        parts += [v, a, v_label, a_label]
    group = VGroup(*parts)

    def step(t: float, p: float) -> None:
        angle = 2 * math.pi * t / period
        u = np.array([math.cos(angle), math.sin(angle), 0.0])
        tangent = np.array([-math.sin(angle), math.cos(angle), 0.0])
        at = centre + r * u
        body.move_to(at)
        body_label.next_to(body, u, buff=0.12)
        back = np.linspace(max(0.0, angle - 1.6), angle, 24)
        points = [centre + r * np.array([math.cos(b), math.sin(b), 0.0]) for b in back]
        trail.set_points_as_corners(points) if len(points) > 1 else None
        if vectors:
            v.put_start_and_end_on(at, at + tangent * r * 0.55)
            a.put_start_and_end_on(at, at - u * r * 0.45)
            v_label.next_to(v.get_end(), tangent, buff=0.1)
            a_label.next_to(a.get_end(), -u + tangent * 0.3, buff=0.08)

    step(0.0, 0.0)
    return Live(group, step, "loop")


ORIGIN3 = np.zeros(3)


def wave(params: dict, box) -> Live:
    from manim import DashedLine, Dot, Line, VGroup, VMobject

    pl = _engine()
    x0, x1, y0, y1 = _frame(box, 0.45)
    kind = str(params.get("wave") or params.get("wave_kind") or params.get("kind") or "travelling")
    lam = float(params.get("wavelength") or 3.0)
    amp = min(float(params.get("amplitude") or 1.0), (y1 - y0) / (5 if kind == "superpose" else 3))
    speed = float(params.get("speed") or 1.5)
    k = 2 * math.pi / lam
    omega = k * speed
    mid = (y0 + y1) / 2
    xs = np.linspace(x0, x1, 140)
    axis = DashedLine([x0, mid, 0], [x1, mid, 0], color=pl.P.MUTED, stroke_width=1.5, dash_length=0.12)
    curves = []
    tones = [pl.P.RIVER, pl.P.ROSE, pl.P.GOLD]
    count = 3 if kind == "superpose" else 1
    for i in range(count):
        curves.append(VMobject(stroke_color=tones[i], stroke_width=5 if i == count - 1 else 3,
                               stroke_opacity=1 if i == count - 1 else 0.7))
    marker = Dot(radius=0.11, color=pl.P.GOLD)
    marks = VGroup()
    if kind == "standing":
        for n in range(0, 40):
            x = x0 + n * lam / 2
            if x > x1 + 1e-6:
                break
            marks.add(pl.T("N", 16, pl.P.MUTED).move_to([x, mid - 0.3, 0]))
    bracket = VGroup()
    if kind == "travelling" and x0 + lam < x1:
        a, b = x0 + lam * 0.25, x0 + lam * 1.25
        bracket = VGroup(Line([a, y1 - 0.2, 0], [b, y1 - 0.2, 0], color=pl.P.MUTED, stroke_width=2),
                         pl.T("λ", 22, pl.P.MUTED).move_to([(a + b) / 2, y1 - 0.02, 0]))
    group = VGroup(axis, marks, bracket, *curves, marker)

    def ys(t):
        if kind == "standing":
            return [2 * amp / 2 * np.sin(k * (xs - x0)) * math.cos(omega * t)]
        if kind == "superpose":
            one = amp / 2 * np.sin(k * (xs - x0) - omega * t)
            two = amp / 2 * np.sin(1.5 * k * (xs - x0) - 1.3 * omega * t + 0.7)
            return [one, two, one + two]
        return [amp * np.sin(k * (xs - x0) - omega * t)]

    def step(t: float, p: float) -> None:
        for curve, y in zip(curves, ys(t)):
            curve.set_points_smoothly([np.array([x, mid + v, 0.0]) for x, v in zip(xs, y)])
        # One particle of the medium: it moves up and down, not along.
        xm = x0 + (x1 - x0) * 0.62
        ym = float(np.interp(xm, xs, ys(t)[-1]))
        marker.move_to([xm, mid + ym, 0])

    step(0.0, 0.0)
    return Live(group, step, "loop")


def collision(params: dict, box) -> Live:
    from manim import Line, Rectangle, RoundedRectangle, VGroup

    pl = _engine()
    x0, x1, y0, y1 = _frame(box, 0.35)
    m1, m2 = float(params.get("m1") or 2.0), float(params.get("m2") or 1.0)
    u1, u2 = float(params.get("u1") if params.get("u1") is not None else 3.0), \
        float(params.get("u2") if params.get("u2") is not None else -1.0)
    elastic = params.get("elastic", True)
    if elastic:
        v1 = ((m1 - m2) * u1 + 2 * m2 * u2) / (m1 + m2)
        v2 = ((m2 - m1) * u2 + 2 * m1 * u1) / (m1 + m2)
    else:
        v1 = v2 = (m1 * u1 + m2 * u2) / (m1 + m2)
    labels = params.get("labels") or {}
    track_y = y0 + (y1 - y0) * 0.55
    track = Line([x0, track_y, 0], [x1, track_y, 0], color=pl.P.MUTED, stroke_width=3)

    def cart(mass, tone, name):
        width = 0.7 + 0.25 * mass
        box_ = RoundedRectangle(corner_radius=0.08, width=width, height=0.6, fill_color=tone, fill_opacity=0.85,
                                stroke_color=tone)
        tag = pl.T(name or f"{mass:g} kg", 18, pl.P.BG if hasattr(pl.P, "BG") else "#000000").move_to(box_)
        return VGroup(box_, tag)

    a = cart(m1, pl.P.RIVER, str(labels.get("left", "")))
    b = cart(m2, pl.P.ROSE, str(labels.get("right", "")))
    span = (x1 - x0)
    meet = x0 + span * 0.5
    bars_y = y0 + 0.5
    scale = (span * 0.35) / max(abs(m1 * u1), abs(m2 * u2), abs(m1 * u1 + m2 * u2), 1e-6)
    title = pl.T("momentum", 18, pl.P.MUTED).move_to([x0 + 0.9, bars_y + 0.75, 0])
    bar_a, bar_b, bar_t = (Rectangle(width=0.01, height=0.22, fill_opacity=0.9, stroke_width=0) for _ in range(3))
    bar_a.set_fill(pl.P.RIVER)
    bar_b.set_fill(pl.P.ROSE)
    bar_t.set_fill(pl.P.GOLD)
    total_label, put_total = _readout("total", 18, pl.P.GOLD)
    group = VGroup(track, a, b, title, bar_a, bar_b, bar_t, total_label)

    def bar(rect, value, row):
        width = max(abs(value) * scale, 0.02)
        rect.stretch_to_fit_width(width)
        start = meet if value >= 0 else meet - width
        rect.move_to([start + width / 2, bars_y + 0.4 - row * 0.32, 0])

    def step(t: float, p: float) -> None:
        # Before: they close in; at p = 0.5 they touch; after: their new velocities.
        gap = (a[0].width + b[0].width) / 2
        travel = span * 0.32
        if p < 0.5:
            q = p / 0.5
            xa = meet - gap / 2 - travel * (1 - q) * (abs(u1) / max(abs(u1) + abs(u2), 1e-6) * 2)
            xb = meet + gap / 2 + travel * (1 - q) * (abs(u2) / max(abs(u1) + abs(u2), 1e-6) * 2)
            va, vb = u1, u2
        else:
            q = (p - 0.5) / 0.5
            xa = meet - gap / 2 + v1 * q * travel / max(abs(u1), abs(v1), abs(v2), 1e-6)
            xb = meet + gap / 2 + v2 * q * travel / max(abs(u1), abs(v1), abs(v2), 1e-6)
            if not elastic:
                xb = xa + gap
            va, vb = v1, v2
        a.move_to([xa, track_y + 0.32, 0])
        b.move_to([xb, track_y + 0.32, 0])
        bar(bar_a, m1 * va, 0)
        bar(bar_b, m2 * vb, 1)
        bar(bar_t, m1 * va + m2 * vb, 2)
        total = m1 * va + m2 * vb
        # on the side of the middle the total bar does not reach, level with it
        side = -1 if total >= 0 else 1
        put_total(f"total p = {_num(total, 1)}", [meet + side * span * 0.2, bars_y + 0.4 - 2 * 0.32, 0])

    step(0.0, 0.0)
    return Live(group, step, "process")


def field(params: dict, box) -> Live:
    from manim import Arrow, Circle, Dot, VGroup, VMobject

    pl = _engine()
    cx, cy, w, h = box
    scale = min(w, h) / 6.0
    charges = params.get("charges") or [[1, -2, 0], [-1, 2, 0]]
    charges = [(float(q), cx + float(x) * scale, cy + float(y) * scale) for q, x, y in charges]
    x0, x1, y0, y1 = _frame(box, 0.2)

    def e_at(p):
        e = np.zeros(2)
        for q, x, y in charges:
            d = p - np.array([x, y])
            r2 = max(float(d @ d), 0.02)
            e += q * d / r2 ** 1.5
        return e

    def line_from(q, x, y, angle):
        sign = 1 if q > 0 else -1
        p = np.array([x, y]) + 0.22 * np.array([math.cos(angle), math.sin(angle)])
        pts = [p.copy()]
        for _ in range(400):
            e = e_at(p) * sign
            n = float(np.linalg.norm(e))
            if n < 1e-6:
                break
            p = p + 0.05 * e / n
            pts.append(p.copy())
            if not (x0 < p[0] < x1 and y0 < p[1] < y1):
                break
            if any(np.hypot(p[0] - cx2, p[1] - cy2) < 0.18 for _, cx2, cy2 in charges):
                break
        return pts

    count = int(params.get("lines") or 12)
    lines = VGroup()
    paths = []
    for q, x, y in charges:
        if q == 0:
            continue
        n = max(4, int(count * abs(q) / max(abs(c[0]) for c in charges)))
        for i in range(n):
            pts = line_from(q, x, y, 2 * math.pi * i / n)
            if len(pts) > 3:
                curve = VMobject(stroke_color=pl.P.MUTED, stroke_width=2, stroke_opacity=0.8)
                curve.set_points_smoothly([np.array([a, b, 0.0]) for a, b in pts[::3]])
                lines.add(curve)
                if q > 0:
                    paths.append(pts)
    bodies = VGroup()
    for q, x, y in charges:
        tone = pl.P.ROSE if q > 0 else pl.P.RIVER
        bodies.add(Circle(radius=0.2, color=tone, fill_color=tone, fill_opacity=0.9).move_to([x, y, 0]))
        bodies.add(pl.T("+" if q > 0 else "−", 24, "#FFFFFF").move_to([x, y, 0]))
    test = Dot(radius=0.09, color=pl.P.GOLD)
    force = Arrow(ORIGIN3, ORIGIN3 + np.array([0.5, 0, 0]), color=pl.P.GOLD, buff=0, stroke_width=4)
    show_test = params.get("test", True) and paths
    group = VGroup(lines, bodies, *([test, force] if show_test else []))
    route = max(paths, key=len) if paths else None

    def step(t: float, p: float) -> None:
        if not show_test or route is None:
            return
        n = len(route)
        i = int((t * 25) % n)
        at = np.array([route[i][0], route[i][1], 0.0])
        test.move_to(at)
        e = e_at(route[i])
        d = e / max(float(np.linalg.norm(e)), 1e-6) * 0.6
        force.put_start_and_end_on(at, at + np.array([d[0], d[1], 0.0]))

    step(0.0, 0.0)
    return Live(group, step, "loop")


def refraction(params: dict, box) -> Live:
    from manim import DashedLine, Line, Rectangle, VGroup

    pl = _engine()
    cx, cy, w, h = box
    n1, n2 = float(params.get("n1") or 1.5), float(params.get("n2") or 1.0)
    a0, a1 = float(params.get("from_deg") or 10), float(params.get("to_deg") or 70)
    labels = params.get("labels") or {}
    top = Rectangle(width=w - 0.4, height=h / 2 - 0.2, fill_color=pl.P.RIVER, fill_opacity=0.12 * n1,
                    stroke_width=0).move_to([cx, cy + h / 4 - 0.05, 0])
    bottom = Rectangle(width=w - 0.4, height=h / 2 - 0.2, fill_color=pl.P.RIVER, fill_opacity=0.12 * n2,
                       stroke_width=0).move_to([cx, cy - h / 4 + 0.05, 0])
    o = np.array([cx, cy, 0.0])
    boundary = Line([cx - w / 2 + 0.2, cy, 0], [cx + w / 2 - 0.2, cy, 0], color=pl.P.MUTED, stroke_width=3)
    normal = DashedLine([cx, cy + h / 2 - 0.4, 0], [cx, cy - h / 2 + 0.4, 0], color=pl.P.MUTED, stroke_width=2)
    tags = VGroup(pl.T(str(labels.get("top", f"n₁ = {n1:g}")), 18, pl.P.MUTED).move_to([cx - w / 2 + 1.1, cy + 0.35, 0]),
                  pl.T(str(labels.get("bottom", f"n₂ = {n2:g}")), 18, pl.P.MUTED).move_to([cx - w / 2 + 1.1, cy - 0.35, 0]))
    length = min(w, h) / 2 - 0.5
    incident = Line(o + np.array([-1, 1, 0]), o, color=pl.P.GOLD, stroke_width=5)
    refracted = Line(o, o + np.array([1, -1, 0]), color=pl.P.GOLD, stroke_width=5)
    reflected = Line(o, o + np.array([1, 1, 0]), color=pl.P.ROSE, stroke_width=4)
    read1, put1 = _readout("θ₁", 20, pl.P.GOLD)
    read2, put2 = _readout("θ₂", 20, pl.P.GOLD)
    note, put_note = _readout(" ", 20, pl.P.ROSE)
    critical = math.degrees(math.asin(n2 / n1)) if n1 > n2 else None
    group = VGroup(top, bottom, boundary, normal, tags, incident, refracted, reflected, read1, read2, note)

    def step(t: float, p: float) -> None:
        theta = math.radians(a0 + (a1 - a0) * p)
        start = o + length * np.array([-math.sin(theta), math.cos(theta), 0.0])
        incident.put_start_and_end_on(start, o)
        s = n1 * math.sin(theta) / n2
        if s < 1:
            phi = math.asin(s)
            refracted.put_start_and_end_on(o, o + length * np.array([math.sin(phi), -math.cos(phi), 0.0]))
            refracted.set_stroke(opacity=1)
            reflected.set_stroke(opacity=0.25)
            put2(f"θ₂ = {math.degrees(phi):.0f}°", o + np.array([1.4, -0.45, 0]))
            put_note(" ", o + np.array([0, -length - 0.1, 0]))
        else:
            refracted.put_start_and_end_on(o, o + np.array([0.001, 0, 0]))
            refracted.set_stroke(opacity=0)
            reflected.set_stroke(opacity=1)
            put2("θ₂: none", o + np.array([1.4, -0.45, 0]))
            put_note("total internal reflection", o + np.array([0, -length * 0.6, 0]))
        reflected.put_start_and_end_on(o, o + length * np.array([math.sin(theta), math.cos(theta), 0.0]))
        put1(f"θ₁ = {math.degrees(theta):.0f}°" + (f"  (critical {critical:.0f}°)" if critical else ""),
             o + np.array([-1.6, 0.45, 0]))

    step(0.0, 0.0)
    return Live(group, step, "process")


def titration(params: dict, box) -> Live:
    from manim import Axes, Dot, Polygon, VGroup, VMobject

    pl = _engine()
    cx, cy, w, h = box
    eq = float(params.get("equivalence") or 25.0)
    weak = str(params.get("kind") or "strong") == "weak"
    indicator = str(params.get("indicator") or "phenolphthalein")
    end_v = eq * 2
    axes = Axes(x_range=[0, end_v, end_v / 5], y_range=[0, 14, 2], x_length=w * 0.58, y_length=h * 0.7,
                axis_config={"color": pl.P.MUTED, "stroke_width": 2, "include_numbers": True, "font_size": 18})
    axes.move_to([cx - w * 0.17, cy, 0])
    xl = pl.T("volume of base (mL)", 16, pl.P.MUTED).next_to(axes.x_axis, np.array([0, -1, 0]), buff=0.4)
    yl = pl.T("pH", 18, pl.P.MUTED).next_to(axes.y_axis.get_end(), np.array([1, 0, 0]), buff=0.12)

    def ph(v):
        start = 3.0 if weak else 1.0
        rise = 1.0 / (1.0 + math.exp(-(v - eq) / (eq * 0.035)))
        before = start + (2.0 if weak else 0.8) * min(v / eq, 1.0)
        return before + (12.5 - before) * rise

    curve = VMobject(stroke_color=pl.P.GOLD, stroke_width=5)
    point = Dot(radius=0.09, color=pl.P.GOLD)
    fx = cx + w * 0.33
    flask = Polygon([fx - 0.25, cy + 1.2, 0], [fx + 0.25, cy + 1.2, 0], [fx + 0.25, cy + 0.6, 0],
                    [fx + 0.95, cy - 0.9, 0], [fx - 0.95, cy - 0.9, 0], [fx - 0.25, cy + 0.6, 0],
                    color=pl.P.CREAM, stroke_width=3)
    liquid = Polygon([fx - 0.62, cy - 0.2, 0], [fx + 0.62, cy - 0.2, 0], [fx + 0.92, cy - 0.85, 0],
                     [fx - 0.92, cy - 0.85, 0], stroke_width=0, fill_opacity=0.85)
    read, put = _readout("pH", 22, pl.P.CREAM)
    name = pl.T(indicator, 16, pl.P.MUTED).next_to(flask, np.array([0, -1, 0]), buff=0.25)
    group = VGroup(axes, xl, yl, curve, point, liquid, flask, name, read)
    acid, base = ("#F2F2F2", "#E85FA5") if indicator.startswith("phenol") else ("#E0483B", "#F2C14E")

    def colour(value):
        lo, hi = (8.2, 10.0) if indicator.startswith("phenol") else (3.1, 4.4)
        return _mix(acid, base, min(1.0, max(0.0, (value - lo) / (hi - lo))))

    def step(t: float, p: float) -> None:
        v = end_v * p
        xs = np.linspace(0, max(v, 1e-3), max(2, int(80 * p) + 2))
        curve.set_points_as_corners([axes.c2p(x, ph(x)) for x in xs])
        point.move_to(axes.c2p(v, ph(v)))
        liquid.set_fill(colour(ph(v)), opacity=0.85)
        put(f"pH {ph(v):.1f}   {v:.0f} mL", [fx, cy + 1.6, 0])

    step(0.0, 0.0)
    return Live(group, step, "process")


def _mix(a: str, b: str, q: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * q):02X}" for x, y in zip(ca, cb))


def mitosis(params: dict, box) -> Live:
    from manim import Dot, Line, VGroup, VMobject

    pl = _engine()
    cx, cy, w, h = box
    r = min(w, h) * 0.3
    centre = np.array([cx, cy - 0.15, 0.0])
    membrane = VMobject(stroke_color=pl.P.GREEN, stroke_width=5, fill_color=pl.P.GREEN, fill_opacity=0.08)
    nucleus = VMobject(stroke_color=pl.P.VIOLET, stroke_width=3)
    pairs = 4
    tones = [pl.P.ROSE, pl.P.RIVER, pl.P.GOLD, pl.P.TEAL if hasattr(pl.P, "TEAL") else pl.P.GREEN]
    rng = np.random.default_rng(7)
    home = [centre + np.array([rng.uniform(-0.45, 0.45) * r, rng.uniform(-0.45, 0.45) * r, 0]) for _ in range(pairs)]
    angle0 = [rng.uniform(0, math.pi) for _ in range(pairs)]
    halves = [(Line(ORIGIN3, ORIGIN3 + np.array([0, 0.35, 0]), color=tones[i % 4], stroke_width=7),
               Line(ORIGIN3, ORIGIN3 + np.array([0, 0.35, 0]), color=tones[i % 4], stroke_width=7)) for i in range(pairs)]
    spindle = VGroup(*[Line(ORIGIN3, ORIGIN3 + np.array([1, 0, 0]), color=pl.P.MUTED, stroke_width=1.5,
                            stroke_opacity=0.6) for _ in range(pairs * 2)])
    poles = VGroup(Dot(radius=0.07, color=pl.P.MUTED), Dot(radius=0.07, color=pl.P.MUTED))
    stage, put_stage = _readout("interphase", 24, pl.P.TITLE)
    names = ["interphase", "prophase", "metaphase", "anaphase", "telophase", "cytokinesis"]
    group = VGroup(membrane, nucleus, spindle, poles, *[x for pair in halves for x in pair], stage)

    def ease(x):
        x = min(max(x, 0.0), 1.0)
        return x * x * (3 - 2 * x)

    def step(t: float, p: float) -> None:
        s = p * 5.0                       # 0..5 across the six stages
        index = min(int(s), 5)
        # The membrane: a circle that stretches, then pinches in two.
        stretch = 1.0 + 0.35 * ease(s - 3) if s > 3 else 1.0
        pinch = ease(s - 4) if s > 4 else 0.0
        pts = []
        for a in np.linspace(0, 2 * math.pi, 120):
            rx = r * stretch
            ry = r * (1 - 0.92 * pinch * (1 - abs(math.cos(a))) ** 2)
            pts.append(centre + np.array([rx * math.cos(a), ry * math.sin(a), 0]))
        membrane.set_points_smoothly(pts)
        # The nucleus fades as the chromosomes condense, and comes back in each daughter.
        fade = 1 - ease(s - 0.6) if s < 3.5 else ease(s - 4.2)
        if s < 3.5:
            nuc = [centre + np.array([0.6 * r * math.cos(a), 0.6 * r * math.sin(a), 0]) for a in np.linspace(0, 2 * math.pi, 60)]
        else:
            nuc = [centre + np.array([sx * r * stretch * 0.5 + 0.35 * r * math.cos(a), 0.35 * r * math.sin(a), 0])
                   for sx in (-1, 1) for a in np.linspace(0, 2 * math.pi, 30)]
        nucleus.set_points_as_corners(nuc)
        nucleus.set_stroke(opacity=max(fade, 0.0))
        # Chromosomes: loose (thin, faint), condensed, lined up at the equator, pulled to the poles.
        line_up = ease(s - 1.6)
        apart = ease(s - 2.8)
        for i, (a, b) in enumerate(halves):
            y = (i - (pairs - 1) / 2) * r * 0.32
            target = centre + np.array([0, y, 0])
            pos = home[i] * (1 - line_up) + target * line_up
            ang = angle0[i] * (1 - line_up) + (math.pi / 2) * line_up
            d = np.array([math.cos(ang), math.sin(ang), 0]) * 0.17
            sep = apart * r * stretch * 0.62
            a.put_start_and_end_on(pos - d + np.array([-0.05 - sep, 0, 0]), pos + d + np.array([-0.05 - sep, 0, 0]))
            b.put_start_and_end_on(pos - d + np.array([0.05 + sep, 0, 0]), pos + d + np.array([0.05 + sep, 0, 0]))
            width = 3 + 4 * ease(s - 0.5)
            a.set_stroke(width=width, opacity=0.5 + 0.5 * ease(s - 0.5))
            b.set_stroke(width=width, opacity=0.5 + 0.5 * ease(s - 0.5))
        spindle_on = ease(s - 1.3) * (1 - ease(s - 4.0))
        left = centre + np.array([-r * stretch * 0.92, 0, 0])
        right = centre + np.array([r * stretch * 0.92, 0, 0])
        poles[0].move_to(left)
        poles[1].move_to(right)
        poles.set_opacity(spindle_on)
        for j, line in enumerate(spindle):
            a, b = halves[j // 2]
            end = (a if j % 2 == 0 else b).get_center()
            line.put_start_and_end_on(left if j % 2 == 0 else right, end)
            line.set_stroke(opacity=0.6 * spindle_on)
        if params.get("stages", True):
            put_stage(names[index], centre + np.array([0, r + 0.55, 0]))

    step(0.0, 0.0)
    return Live(group, step, "process")


def heart(params: dict, box) -> Live:
    from manim import Dot, VGroup, VMobject

    pl = _engine()
    cx, cy, w, h = box
    size = min(w, h) * 0.034
    centre = np.array([cx, cy, 0.0])
    bpm = float(params.get("bpm") or 72)

    def outline(k):
        pts = []
        for a in np.linspace(0, 2 * math.pi, 120):
            x = 16 * math.sin(a) ** 3
            y = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
            pts.append(centre + np.array([x, y, 0]) * size * k)
        return pts

    shape = VMobject(stroke_color=pl.P.ROSE, stroke_width=5, fill_color=pl.P.ROSE, fill_opacity=0.25)
    shape.set_points_smoothly(outline(1.0))
    septum = VMobject(stroke_color=pl.P.ROSE, stroke_width=3, stroke_opacity=0.7)
    septum.set_points_as_corners([centre + np.array([0, 4, 0]) * size, centre + np.array([0, -12, 0]) * size])
    loop = []
    for a in np.linspace(0, 2 * math.pi, 200):
        loop.append(centre + np.array([math.cos(a) * 26 * size, math.sin(a) * 15 * size, 0]))
    cells = VGroup(*[Dot(radius=0.07) for _ in range(18)])
    tags = VGroup(pl.T("lungs", 18, pl.P.RIVER).move_to(centre + np.array([0, 17.5, 0]) * size),
                  pl.T("body", 18, pl.P.ROSE).move_to(centre + np.array([0, -17.5, 0]) * size))
    rate, put = _readout(f"{bpm:g} beats per minute", 18, pl.P.MUTED)
    group = VGroup(tags, cells, shape, septum, rate)
    flow = params.get("flow", True)
    if not flow:
        cells.set_opacity(0)

    def step(t: float, p: float) -> None:
        beat = (t * bpm / 60.0) % 1.0
        k = 1.0 + 0.09 * math.exp(-((beat - 0.12) / 0.07) ** 2) + 0.05 * math.exp(-((beat - 0.35) / 0.06) ** 2)
        shape.set_points_smoothly(outline(k))
        if flow:
            n = len(loop)
            for i, cell in enumerate(cells):
                j = int((i * n / len(cells) + t * 40) % n)
                at = loop[j]
                cell.move_to(at)
                # Oxygen-poor (blue) on the way back to the lungs, rich (red) after them.
                cell.set_color(pl.P.ROSE if at[0] > centre[0] else pl.P.RIVER)
        put(f"{bpm:g} beats per minute", centre + np.array([0, -21.5, 0]) * size)

    step(0.0, 0.0)
    return Live(group, step, "loop")


def gas(params: dict, box) -> Live:
    from manim import Dot, Rectangle, VGroup

    pl = _engine()
    x0, x1, y0, y1 = _frame(box, 0.6)
    n = int(params.get("particles") or 24)
    speed = float(params.get("speed") or 1.0) * (1.6 if params.get("hot") else 1.0)
    walls = Rectangle(width=x1 - x0, height=y1 - y0, color=pl.P.CREAM, stroke_width=4).move_to(
        [(x0 + x1) / 2, (y0 + y1) / 2, 0])
    rng = np.random.default_rng(11)
    start = np.column_stack([rng.uniform(x0 + 0.2, x1 - 0.2, n), rng.uniform(y0 + 0.2, y1 - 0.2, n)])
    vel = rng.normal(0, 1, (n, 2)) * speed * 1.4
    dots = VGroup(*[Dot(radius=0.09, color=pl.P.GOLD if params.get("hot") else pl.P.RIVER) for _ in range(n)])
    group = VGroup(walls, dots)
    lo = np.array([x0 + 0.1, y0 + 0.1])
    hi = np.array([x1 - 0.1, y1 - 0.1])

    def bounce(p, span):
        # A wall reflects: fold the free path back into the box (exact for any t).
        q = np.mod(p - lo, 2 * span)
        return lo + np.where(q > span, 2 * span - q, q)

    def step(t: float, p: float) -> None:
        span = hi - lo
        where = bounce(start + vel * t, span)
        for dot, at in zip(dots, where):
            dot.move_to([at[0], at[1], 0])

    step(0.0, 0.0)
    return Live(group, step, "loop")


def decay(params: dict, box) -> Live:
    from manim import Axes, Dot, VGroup, VMobject

    pl = _engine()
    cx, cy, w, h = box
    n = int(params.get("atoms") or 64)
    side = int(math.ceil(math.sqrt(n)))
    half = float(params.get("half_life") or 0.35)        # as a share of the line
    rng = np.random.default_rng(5)
    life = rng.exponential(half / math.log(2), n)
    grid_w = min(w * 0.42, h * 0.75)
    gap = grid_w / side
    ox = cx - w * 0.25 - grid_w / 2 + gap / 2
    oy = cy + grid_w / 2 - gap / 2
    atoms = VGroup(*[Dot([ox + (i % side) * gap, oy - (i // side) * gap, 0], radius=gap * 0.3, color=pl.P.GOLD)
                     for i in range(n)])
    axes = Axes(x_range=[0, 1, 0.25], y_range=[0, n, max(1, n // 4)], x_length=w * 0.38, y_length=h * 0.5,
                axis_config={"color": pl.P.MUTED, "stroke_width": 2}).move_to([cx + w * 0.24, cy, 0])
    curve = VMobject(stroke_color=pl.P.GOLD, stroke_width=4)
    read, put = _readout(f"{n} left", 20, pl.P.CREAM)
    group = VGroup(atoms, axes, curve, read)
    show_curve = params.get("curve", True)
    if not show_curve:
        axes.set_opacity(0)

    def step(t: float, p: float) -> None:
        alive = life > p
        for dot, on in zip(atoms, alive):
            dot.set_color(pl.P.GOLD if on else pl.P.MUTED)
            dot.set_opacity(1.0 if on else 0.35)
        if show_curve:
            xs = np.linspace(0, max(p, 1e-3), max(2, int(60 * p) + 2))
            curve.set_points_as_corners([axes.c2p(x, float((life > x).sum())) for x in xs])
        put(f"{int(alive.sum())} of {n} left", [cx - w * 0.25, cy - grid_w / 2 - 0.45, 0])

    step(0.0, 0.0)
    return Live(group, step, "process")


def counter(params: dict, box) -> Live:
    """A value counting from one number to another over the line: a big readout, with a bar that fills or a dial
    whose needle turns ("style": "bar" | "dial" | "number")."""
    from manim import Arc, Line, Rectangle, VGroup

    pl = _engine()
    cx, cy, w, h = box
    lo, hi = float(params.get("from", 0)), float(params.get("to", 100))
    top = float(params.get("max", max(abs(lo), abs(hi)) or 1.0))
    decimals = int(params.get("decimals", 0 if float(hi).is_integer() and float(lo).is_integer() else 1))
    unit = str(params.get("unit") or "")
    style = str(params.get("style") or "bar")
    ink = pl.P.GOLD
    label = pl.T(str(params.get("label") or ""), 26, pl.P.MUTED).move_to([cx, cy + h * 0.28, 0])
    value, put = _readout(" ", 64, ink)
    parts = [label, value]
    if style == "bar":
        frame = Rectangle(width=w * 0.7, height=0.45, color=pl.P.MUTED, stroke_width=3).move_to([cx, cy - h * 0.22, 0])
        fill = Rectangle(width=0.01, height=0.41, stroke_width=0, fill_color=ink, fill_opacity=0.9)
        parts += [frame, fill]
    elif style == "dial":
        r = min(w, h) * 0.28
        centre = np.array([cx, cy - h * 0.3, 0])
        arc = Arc(radius=r, start_angle=math.pi, angle=-math.pi, color=pl.P.MUTED, stroke_width=6).move_arc_center_to(centre)
        needle = Line(centre, centre + np.array([-r * 0.9, 0, 0]), color=ink, stroke_width=6)
        parts += [arc, needle]
    group = VGroup(*parts)

    def step(t: float, p: float) -> None:
        v = lo + (hi - lo) * (p * p * (3 - 2 * p))
        put(f"{_num(v, decimals)} {unit}".strip(), [cx, cy + (0.05 if style != "number" else 0) * h, 0])
        share = min(1.0, max(0.0, abs(v) / top))
        if style == "bar":
            width = max(frame.width * share, 0.01)
            fill.stretch_to_fit_width(width)
            fill.move_to([frame.get_left()[0] + width / 2, frame.get_center()[1], 0])
        elif style == "dial":
            angle = math.pi * (1 - share)
            needle.put_start_and_end_on(centre, centre + 0.9 * r * np.array([math.cos(angle), math.sin(angle), 0]))

    step(0.0, 0.0)
    return Live(group, step, "process")


BUILDERS = {"orbit": orbit, "wave": wave, "collision": collision, "field": field, "refraction": refraction,
            "titration": titration, "mitosis": mitosis, "heart": heart, "gas": gas, "decay": decay}


# The rest of the sims (sims_more.py): their builders, what they take, and whether they loop.
import sims_more as _more  # noqa: E402 -- after Live and the helpers it uses are defined

for _kind, (_builder, _settings) in _more.MORE.items():
    BUILDERS[_kind] = _builder
    SIM_PARAMS[_kind] = _settings
SIMS = tuple(BUILDERS)
LOOPS = LOOPS | {k for k, (b, _) in _more.MORE.items() if k in _more.LOOPING}


def sim_problem(op: dict) -> str | None:
    kind = str(op.get("kind") or "")
    if kind not in BUILDERS:
        return f"sim kind must be one of {', '.join(SIMS)} (got {kind!r})"
    params = {**(op.get("params") or {}), **op}
    if kind == "wave" and str(params.get("wave") or params.get("wave_kind") or (op.get("params") or {}).get("kind")
                              or "travelling") not in ("travelling", "standing", "superpose"):
        return "a wave is travelling, standing or superpose (\"wave\": \"standing\")"
    return None
