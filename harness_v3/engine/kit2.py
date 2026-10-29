"""More of the kit's pieces, each one `ent` placed freely, its parts brought on by the actions as kit.py's are:

    science and maths   numberline A B, plot "x^2" A B, triangle A:x,y B:x,y C:x,y, molecule H2O,
                        equation "2x+3=7" "2x=4" "x=2", circuit "battery>bulb>switch"
    data and civics     race "1900|1950|2000" K:v|v|v ..., parliament K:seats ..., market, climate M:temp:rain ...,
                        chart scatter / chart area (kit.chart)
    storytelling        quiz "QUESTION" "A" "B" "C" answer N, lens "@X,Y" on PIC, split "LEFT" "RIGHT", clock H,
                        odometer V, clipping "HEADLINE", (who and polaroids are drawn in look.py: they hold pictures)
    maps                shade "WHAT" on MAP K:V ..., march P P P, inset on MAP, layers "TOP" ... "BOTTOM", globe LON,LAT
"""

from __future__ import annotations

import math
import re
import zlib

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, RIGHT, UP, Annulus, Arc, Circle, DashedVMobject, Dot, Line, Polygon, Rectangle,
                   RoundedRectangle, VGroup, VMobject)

from look import L, STROKE, Valued, col, label, soft_shadow, text
from kit import PALETTE, Keys, _At, _fmt, even, formula, halo, key, node, para, tipped


def _num(s) -> float:
    return float(str(s).replace(",", "").replace("_", "-").replace("−", "-"))


# ---------------------------------------------------------------- science and maths ----------------------------------

class _Numbers:
    """`NL.3`, `NL.-2.5`: a number's point on a number line (or an x on a plot's curve)."""

    def __init__(self, f):
        self.f = f

    def __contains__(self, k) -> bool:
        try:
            _num(k)
            return True
        except ValueError:
            return False

    def __getitem__(self, k):
        v = _num(k)
        return _At(lambda: self.f(v))

    def __iter__(self):
        return iter(())


class NumberLine(VGroup):
    """A number line from A to B, ticks every `step` (whole numbers by default), its numbers under them. Parts: [line,
    ticks]. Places: `nl.3`."""

    def __init__(self, a: float, b: float, w: float = 11.0, step: float | None = None, c=None):
        super().__init__()
        self.a, self.b = min(a, b), max(a, b)
        span = self.b - self.a or 1
        step = step or next(s for s in (0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 50, 100, 1000) if span / s <= 12)
        self.line = Line(LEFT * w / 2, RIGHT * w / 2, stroke_color=col(c or "ink"), stroke_width=STROKE * 0.55)
        tips = VGroup(tipped([[w / 2 - 0.01, 0, 0], [w / 2 + 0.25, 0, 0]], col(c or "ink"), smooth=False),
                      tipped([[-w / 2 + 0.01, 0, 0], [-w / 2 - 0.25, 0, 0]], col(c or "ink"), smooth=False))
        ticks = VGroup()
        v = math.ceil(self.a / step) * step
        while v <= self.b + 1e-9:
            p = self.point(v)
            big = abs(v - round(v)) < 1e-9
            ticks.add(Line(p + UP * (0.14 if big else 0.08), p + DOWN * (0.14 if big else 0.08),
                           stroke_color=col("ink"), stroke_width=STROKE * 0.4))
            if big or step >= 1:
                ticks.add(even(f"{v:g}".replace("-", "−"), 0.18).move_to(p + DOWN * 0.42))
            v = round(v + step, 6)
        self.add(VGroup(self.line, tips), ticks)
        self.places = _Numbers(self.point)

    def point(self, v: float) -> np.ndarray:
        s, e = self.line.get_start(), self.line.get_end()
        return s + (e - s) * (v - self.a) / ((self.b - self.a) or 1)


SAFE = {k: getattr(math, k) for k in ("sin", "cos", "tan", "sqrt", "log", "log10", "exp", "pi", "e", "fabs")}
SAFE.update(abs=abs, min=min, max=max)


def _fn(expr: str):
    """y = f(x) from words like `x^2 - 1`, `2*sin(x)`, `sqrt(x)` (only arithmetic and math's functions)."""
    src = expr.replace("^", "**").replace("−", "-")
    src = re.sub(r"(\d)\s*([a-z(])", r"\1*\2", src)          # 2x -> 2*x, 3(x+1) -> 3*(x+1)
    src = re.sub(r"\)\s*([a-z(\d])", r")*\1", src)
    if re.search(r"[^\w\s.+\-*/(),]", src) or re.search(r"__|import|lambda", src):
        raise ValueError(f"not a formula I can draw: {expr!r}")
    code = compile(src, "<plot>", "eval")
    for name in code.co_names:
        if name not in SAFE and name != "x":
            raise ValueError(f"{name!r} in {expr!r}: use x, numbers and sin cos tan sqrt log exp pi")
    return lambda x: eval(code, {"__builtins__": {}}, {**SAFE, "x": x})


class Plot(VGroup):
    """Axes with a curve y = f(x) for x from A to B. Parts: [axes, curve]. Places: `pl.2` (the curve at x = 2)."""

    def __init__(self, expr: str, a: float, b: float, w: float = 6.0, h: float = 4.0, c=None, ymin=None, ymax=None):
        super().__init__()
        f = _fn(expr)
        xs = np.linspace(a, b, 160)
        ys = []
        for x in xs:
            try:
                y = float(f(x))
                ys.append(y if math.isfinite(y) else np.nan)
            except (ValueError, ZeroDivisionError, OverflowError):
                ys.append(np.nan)
        ys = np.array(ys)
        lo = float(np.nanmin(ys)) if ymin is None else ymin
        hi = float(np.nanmax(ys)) if ymax is None else ymax
        lo, hi = min(lo, 0.0), max(hi, 0.0)
        if hi - lo < 1e-9:
            hi = lo + 1
        self.box = (a, b, lo, hi, w, h)
        X = lambda x: -w / 2 + w * (x - a) / (b - a)         # noqa: E731
        Y = lambda y: -h / 2 + h * (y - lo) / (hi - lo)       # noqa: E731
        self.X, self.Y, self.f = X, Y, f
        ax = VGroup(tipped([[-w / 2 - 0.1, Y(0), 0], [w / 2 + 0.25, Y(0), 0]], col("ink"), STROKE * 0.4, smooth=False),
                    tipped([[X(max(a, min(0, b))), -h / 2 - 0.1, 0], [X(max(a, min(0, b))), h / 2 + 0.25, 0]],
                           col("ink"), STROKE * 0.4, smooth=False),
                    label("x", 0.13, "ink").move_to([w / 2 + 0.45, Y(0), 0]),
                    label("y", 0.13, "ink").move_to([X(max(a, min(0, b))), h / 2 + 0.5, 0]))
        for v in _nice_ticks(a, b):
            if abs(v) > 1e-9:
                ax.add(Line([X(v), Y(0) - 0.08, 0], [X(v), Y(0) + 0.08, 0], stroke_color=col("ink"), stroke_width=2),
                       even(f"{v:g}", 0.13).move_to([X(v), Y(0) - 0.3, 0]))
        for v in _nice_ticks(lo, hi):
            if abs(v) > 1e-9:
                ax.add(Line([X(max(a, min(0, b))) - 0.08, Y(v), 0], [X(max(a, min(0, b))) + 0.08, Y(v), 0],
                            stroke_color=col("ink"), stroke_width=2),
                       even(f"{v:g}", 0.13).move_to([X(max(a, min(0, b))) - 0.35, Y(v), 0]))
        curve = VGroup()
        run = []
        for x, y in zip(xs, ys):
            if np.isnan(y) or y < lo - (hi - lo) or y > hi + (hi - lo):
                if len(run) > 1:
                    curve.add(VMobject(stroke_color=col(c or "coral"), stroke_width=STROKE * 0.8).set_points_smoothly(run))
                run = []
            else:
                run.append(np.array([X(x), Y(min(max(y, lo), hi)), 0.0]))
        if len(run) > 1:
            curve.add(VMobject(stroke_color=col(c or "coral"), stroke_width=STROKE * 0.8).set_points_smoothly(run))
        self.add(ax, curve)
        self.track = curve[0] if len(curve) else None     # what `along` moves a dot on
        self.places = _Numbers(self._at)

    def _at(self, x: float) -> np.ndarray:
        o = self[0][0][0].get_start()                          # where the axes stand now (they move with the piece)
        a, b, lo, hi, w, h = self.box
        base = np.array([-w / 2 - 0.1, self.Y(0), 0.0])
        return o - base + np.array([self.X(x), self.Y(float(self.f(x))), 0.0])


def _nice_ticks(a: float, b: float) -> list[float]:
    span = (b - a) or 1
    step = next(s for s in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 5000) if span / s <= 8)
    v = math.ceil(a / step) * step
    out = []
    while v <= b + 1e-9:
        out.append(round(v, 6))
        v += step
    return out


def triangle(args: list[str], mods: dict, c=None) -> VGroup:
    """A shape from its corners (`A:0,0 B:4,0 C:1,3`; three or more), each named; `sides` writes each side's length,
    `angles` marks each corner's angle with its degrees. Parts: [shape, corner names, lengths, angles]. Places: `t.A`."""
    pts = {}
    for a in args:
        if ":" in a:
            n, xy = a.split(":", 1)
            x, y = (float(v) for v in xy.split(","))
            pts[n] = np.array([x, y, 0.0])
    if len(pts) < 3:
        raise ValueError("a shape needs three corners or more: A:0,0 B:4,0 C:1,3")
    names = list(pts)
    P = [pts[n] for n in names]
    ctr = sum(P) / len(P)
    shape = Polygon(*P, fill_color=col(c or "accent"), fill_opacity=0.25, stroke_color=col("ink"), stroke_width=STROKE * 0.6)
    corners, lengths, angles = VGroup(), VGroup(), VGroup()
    for i, n in enumerate(names):
        p = P[i]
        out = (p - ctr) / (np.linalg.norm(p - ctr) or 1)
        corners.add(even(n, 0.26, bold=True).move_to(p + out * 0.35), Dot(p, radius=0.05, color=col("ink")))
        q = P[(i + 1) % len(P)]
        if mods.get("sides"):
            mid = (p + q) / 2
            nrm = np.array([-(q - p)[1], (q - p)[0], 0.0])
            nrm = nrm / (np.linalg.norm(nrm) or 1)
            if np.dot(nrm, mid - ctr) < 0:
                nrm = -nrm
            lengths.add(halo(even(f"{np.linalg.norm(q - p):.3g}", 0.18)).move_to(mid + nrm * 0.3))
        if mods.get("angles"):
            r = P[i - 1]
            a1 = math.atan2(*(q - p)[1::-1])
            a2 = math.atan2(*(r - p)[1::-1])
            d = (a2 - a1) % math.tau
            if d > math.pi:
                a1, d = a2, math.tau - d
            angles.add(Arc(radius=0.4, start_angle=a1, angle=d, arc_center=p, stroke_color=col("coral"),
                           stroke_width=STROKE * 0.5))
            mid = a1 + d / 2
            angles.add(even(f"{math.degrees(d):.0f}°", 0.15).move_to(p + 0.72 * np.array([math.cos(mid), math.sin(mid), 0])))
    g = VGroup(shape, corners, lengths, angles)
    g.places = Keys({key(n): Dot(P[i], radius=0.001).set_opacity(0) for i, n in enumerate(names)})
    for d in g.places.values():
        g.add(d)
    return g.move_to(ORIGIN)


# Atoms (CPK colours, in the look's palette) and a few molecules drawn as chemists draw them (x, y per atom).
ATOM = {"H": ("white", 0.26), "C": ("ink", 0.36), "O": ("red", 0.36), "N": ("navy", 0.36), "Cl": ("green", 0.4),
        "Na": ("sky", 0.42), "S": ("gold", 0.4), "P": ("coral", 0.4), "F": ("green", 0.3), "K": ("sky", 0.44),
        "Ca": ("sand", 0.44), "Fe": ("coral", 0.42), "Mg": ("teal", 0.42)}
MOLECULES = {
    "H2O": [("O", 0, 0), ("H", -0.95, -0.7), ("H", 0.95, -0.7)],
    "CO2": [("C", 0, 0), ("O", -1.25, 0), ("O", 1.25, 0)],
    "CH4": [("C", 0, 0), ("H", 0, 1.1), ("H", -1.05, -0.4), ("H", 1.05, -0.4), ("H", 0, -0.95)],
    "NH3": [("N", 0, 0.1), ("H", -1.0, -0.55), ("H", 1.0, -0.55), ("H", 0, -1.1)],
    "O2": [("O", -0.6, 0), ("O", 0.6, 0)], "N2": [("N", -0.6, 0), ("N", 0.6, 0)], "H2": [("H", -0.4, 0), ("H", 0.4, 0)],
    "NaCl": [("Na", -0.7, 0), ("Cl", 0.7, 0)], "HCl": [("H", -0.6, 0), ("Cl", 0.55, 0)],
    "CO": [("C", -0.6, 0), ("O", 0.6, 0)], "SO2": [("S", 0, 0), ("O", -1.1, -0.6), ("O", 1.1, -0.6)],
    "C2H6": [("C", -0.65, 0), ("C", 0.65, 0), ("H", -1.2, 0.95), ("H", -1.2, -0.95), ("H", -1.6, 0),
             ("H", 1.2, 0.95), ("H", 1.2, -0.95), ("H", 1.6, 0)],
}
DOUBLE = {"CO2", "O2", "SO2"}


def _formula_atoms(f: str) -> list[str]:
    out = []
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", f):
        out += [el] * (int(n) if n else 1)
    return out


def molecule(f: str, mods: dict, c=None) -> VGroup:
    """A molecule as balls and sticks: the common ones as chemists draw them, others with the first heavy atom in the
    middle and the rest round it. Parts: one an atom (with its bond in), the formula under them last."""
    f = f.strip()
    spec = MOLECULES.get(f)
    if spec is None:
        atoms = _formula_atoms(f)
        if not atoms:
            raise ValueError(f"not a formula: {f!r}")
        mid = next((a for a in atoms if a != "H"), atoms[0])
        rest = list(atoms)
        rest.remove(mid)
        spec = [(mid, 0, 0)] + [(a, 1.15 * math.cos(math.pi / 2 + math.tau * i / len(rest)),
                                 1.15 * math.sin(math.pi / 2 + math.tau * i / len(rest))) for i, a in enumerate(rest)]
    k = float(mods.get("size") or 1.0)
    pos = [np.array([x * k, y * k, 0.0]) for _, x, y in spec]
    g = VGroup()
    for i, (el, _, _) in enumerate(spec):
        colour, r = ATOM.get(el, ("soft", 0.36))
        ball = VGroup(Circle(radius=r * k, fill_color=col(colour), fill_opacity=1, stroke_color=col("ink"), stroke_width=2),
                      even(el, 0.2 * k, bold=True, color="white" if colour in ("ink", "navy", "red", "green", "teal") else "ink"))
        ball[1].move_to(pos[i])
        ball[0].move_to(pos[i])
        part = VGroup()
        if i:
            # bonded to the middle atom (ethane: each hydrogen to its own carbon)
            a, b = pos[(0 if i < 5 else 1) if f == "C2H6" and i >= 2 else 0], pos[i]
            d = (b - a) / (np.linalg.norm(b - a) or 1)
            n = np.array([-d[1], d[0], 0.0]) * 0.07
            bond = VGroup(*(Line(a + o, b + o, stroke_color=col("ink"), stroke_width=STROKE * 0.6)
                            for o in ((n, -n) if f in DOUBLE else (np.zeros(3),))))
            bond.set_z_index(-1)
            part.add(bond)
        part.add(ball)
        g.add(part)
    g.add(formula(f.replace("2", "_2").replace("3", "_3").replace("4", "_4").replace("6", "_6"), {"size": 0.32})
          .next_to(g, DOWN, buff=0.35))
    return g


def equation(lines: list[str], mods: dict, c=None) -> VGroup:
    """Lines of working, one under another, their `=` signs in a column: `equation "2x+3=7" "2x=4" "x=2"`. Parts: the
    lines (`in eq[1]` as the voice reaches it; `highlight eq[2]` the answer)."""
    size = float(mods.get("size") or 0.42)
    rows = []
    for ln in lines:
        left, eq, right = ln.partition("=")
        L_ = formula(left.strip() or " ", {"size": size}, c)
        R_ = formula(right.strip() or " ", {"size": size}, c) if eq else None
        E_ = formula("=", {"size": size}, c) if eq else None
        rows.append((L_, E_, R_))
    g = VGroup()
    for i, (L_, E_, R_) in enumerate(rows):
        y = -i * size * 2.3
        row = VGroup()
        if E_ is not None:
            E_.move_to([0, y, 0])
            L_.next_to(E_, LEFT, buff=0.22)
            R_.next_to(E_, RIGHT, buff=0.22)
            row.add(L_, E_, R_)
        else:
            row.add(L_.move_to([0, y, 0]))
        g.add(row)
    return g.move_to(ORIGIN)


def circuit(spec: str, mods: dict, c=None) -> VGroup:
    """A circuit round a loop, its parts in order: `circuit "battery>bulb>switch>resistor"` (also cell, lamp,
    ammeter, voltmeter). Parts: the wire, then each component; places by name (`ci.bulb`)."""
    names = [s.strip() for s in spec.split(">") if s.strip()]
    w, h = float(mods.get("w", 6)), float(mods.get("h", 3.4))
    corners = [np.array(p, dtype=float) for p in ([-w / 2, -h / 2, 0], [-w / 2, h / 2, 0], [w / 2, h / 2, 0], [w / 2, -h / 2, 0])]
    sides = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    # components spread along the loop (by length), clockwise from the left side
    total = 2 * (w + h)
    spots = []
    if len(names) <= 4:                  # one a side, in the middle: top, right, bottom, left
        order = [1, 2, 3, 0]
        spots = [((sides[i][0] + sides[i][1]) / 2, (sides[i][1] - sides[i][0]) / np.linalg.norm(sides[i][1] - sides[i][0]))
                 for i in order[:len(names)]]
    for k in range(len(names) if len(names) > 4 else 0):
        s = total * (k + 0.5) / len(names)
        for a, b in sides:
            ln = float(np.linalg.norm(b - a))
            if s <= ln:
                spots.append((a + (b - a) * s / ln, (b - a) / ln))
                break
            s -= ln
    gaps = []
    comps = VGroup()
    g = VGroup()
    g.places = Keys()
    for nm, (p, d) in zip(names, spots):
        comp = _component(nm.lower(), c)
        ang = math.atan2(d[1], d[0])
        comp.rotate(ang).move_to(p)
        out = np.array([np.sign(p[0]) if abs(p[0]) >= w / 2 - 1e-6 else 0, np.sign(p[1]) if abs(p[1]) >= h / 2 - 1e-6 else 0, 0])
        lab = even(nm.replace("_", " "), 0.18).move_to(p + out * 0.62)     # outside the loop
        part = VGroup(comp, lab)
        comps.add(part)
        g.places[key(nm)] = comp
        gaps.append((p, d, 0.45))
    wire = VGroup()
    for a, b in sides:
        cuts = sorted([(float(np.dot(p - a, (b - a) / np.linalg.norm(b - a))), r) for p, d, r in gaps
                       if np.linalg.norm(np.cross(np.append((b - a)[:2], 0), np.append((p - a)[:2], 0))) < 1e-6
                       and -1e-6 <= np.dot(p - a, b - a) <= np.dot(b - a, b - a) + 1e-6])
        u = (b - a) / np.linalg.norm(b - a)
        t = 0.0
        for s, r in cuts:
            if s - r > t:
                wire.add(Line(a + u * t, a + u * (s - r), stroke_color=col("ink"), stroke_width=STROKE * 0.55))
            t = s + r
        if t < np.linalg.norm(b - a):
            wire.add(Line(a + u * t, b, stroke_color=col("ink"), stroke_width=STROKE * 0.55))
    g.add(wire, *comps)
    return g


def _component(name: str, c=None) -> VGroup:
    ink = col("ink")
    if name in ("battery", "cell"):
        return VGroup(Line([-0.45, 0, 0], [-0.1, 0, 0], stroke_color=ink, stroke_width=4),
                      Line([-0.1, 0.32, 0], [-0.1, -0.32, 0], stroke_color=ink, stroke_width=4),
                      Line([0.1, 0.18, 0], [0.1, -0.18, 0], stroke_color=ink, stroke_width=8),
                      Line([0.1, 0, 0], [0.45, 0, 0], stroke_color=ink, stroke_width=4))
    if name in ("bulb", "lamp"):
        r = 0.3
        return VGroup(Line([-0.45, 0, 0], [-r, 0, 0], stroke_color=ink, stroke_width=4),
                      Circle(radius=r, stroke_color=ink, stroke_width=4, fill_color=col(c or "accent"), fill_opacity=0.5),
                      Line([-r * 0.7, -r * 0.7, 0], [r * 0.7, r * 0.7, 0], stroke_color=ink, stroke_width=3),
                      Line([-r * 0.7, r * 0.7, 0], [r * 0.7, -r * 0.7, 0], stroke_color=ink, stroke_width=3),
                      Line([r, 0, 0], [0.45, 0, 0], stroke_color=ink, stroke_width=4))
    if name == "switch":
        return VGroup(Line([-0.45, 0, 0], [-0.25, 0, 0], stroke_color=ink, stroke_width=4),
                      Dot([-0.25, 0, 0], radius=0.05, color=ink), Line([-0.25, 0, 0], [0.22, 0.25, 0], stroke_color=ink, stroke_width=4),
                      Dot([0.25, 0, 0], radius=0.05, color=ink), Line([0.25, 0, 0], [0.45, 0, 0], stroke_color=ink, stroke_width=4))
    if name in ("ammeter", "voltmeter"):
        return VGroup(Line([-0.45, 0, 0], [-0.3, 0, 0], stroke_color=ink, stroke_width=4),
                      Circle(radius=0.3, stroke_color=ink, stroke_width=4, fill_color=col("card"), fill_opacity=1),
                      even("A" if name == "ammeter" else "V", 0.22, bold=True),
                      Line([0.3, 0, 0], [0.45, 0, 0], stroke_color=ink, stroke_width=4))
    # a resistor (and anything else): a box
    return VGroup(Line([-0.45, 0, 0], [-0.3, 0, 0], stroke_color=ink, stroke_width=4),
                  Rectangle(width=0.6, height=0.24, stroke_color=ink, stroke_width=4, fill_color=col("card"), fill_opacity=1),
                  Line([0.3, 0, 0], [0.45, 0, 0], stroke_color=ink, stroke_width=4))


# ---------------------------------------------------------------- data and civics ------------------------------------

class Anchored:
    """Three hidden points carried along when the piece moves or scales: where its own coordinates now are (a piece
    that redraws parts of itself as it counts draws them there)."""

    def _anchor(self):
        self._ref = VGroup(*(Dot(p, radius=0.001).set_opacity(0) for p in (ORIGIN, RIGHT, UP)))
        self.add(self._ref)

    def w(self, p) -> np.ndarray:
        o, x, y = (d.get_center() for d in self._ref)
        p = np.asarray(p, dtype=float)
        return o + p[0] * (x - o) + p[1] * (y - o)

    def k(self) -> float:
        o, x, _ = (d.get_center() for d in self._ref)
        return float(np.linalg.norm(x - o))


class Race(Anchored, Valued, VGroup):
    """Bars that race through the years, sorting themselves as they pass: `race "1900|1950|2000" UK:1|5|9 US:3|4|12`.
    `count RACE 2000` runs it; the year is shown in the corner."""

    def __init__(self, years: list[float], series: dict, w: float = 8.0, h: float = 4.0, mods: dict | None = None, c=None):
        super().__init__()
        self.years, self.series, self.w_, self.h, self.mods = years, series, w, h, mods or {}
        self.names = list(series)
        self.top = max(max(v) for v in series.values()) or 1
        self.row = min(0.8, h / max(1, len(self.names)))
        self.bars = {}
        for i, n in enumerate(self.names):
            colour = col(PALETTE[i % len(PALETTE)])
            bar = Rectangle(width=0.1, height=self.row * 0.62, fill_color=colour, fill_opacity=1, stroke_width=0)
            name = even(n.replace("_", " "), 0.2)
            val = even("0", 0.2, bold=True)
            self.bars[n] = VGroup(bar, name, val)
            self.add(self.bars[n])
        self.yearl = even(f"{years[0]:.0f}", 0.9, bold=True, color="soft")
        self.add(self.yearl)
        self._anchor()
        self.value = years[0]
        self.set_value(years[0])

    def _at(self, n: str, y: float) -> float:
        vs, ys = self.series[n], self.years
        if y <= ys[0]:
            return vs[0]
        for i in range(len(ys) - 1):
            if ys[i] <= y <= ys[i + 1]:
                t = (y - ys[i]) / ((ys[i + 1] - ys[i]) or 1)
                return vs[i] + (vs[i + 1] - vs[i]) * t
        return vs[-1]

    def set_value(self, y: float) -> None:
        vals = {n: self._at(n, y) for n in self.names}
        order = sorted(self.names, key=lambda n: -vals[n])
        left = -self.w_ / 2 + 1.6
        full = self.w_ - 2.6
        for n in self.names:
            bar, name, val = self.bars[n]
            # its row: eased toward its rank (a bar overtaking slides past)
            rank = order.index(n)
            ytarget = self.h / 2 - self.row * (rank + 0.5)
            ycur = getattr(bar, "_y", ytarget)
            yy = ycur + (ytarget - ycur) * 0.25 if abs(ytarget - ycur) > 1e-3 else ytarget
            bar._y = yy
            bw = max(0.04, full * vals[n] / self.top)
            k = self.k()
            new = Rectangle(width=bw * k, height=self.row * 0.62 * k, fill_color=bar.get_fill_color(),
                            fill_opacity=bar.get_fill_opacity(), stroke_width=0).move_to(self.w([left + bw / 2, yy]))
            bar.become(new)
            bar._y = yy
            name.move_to(self.w([left - 0.15, yy]) + LEFT * name.width / 2)
            nv = even(_fmt(round(vals[n], 1), self.mods), 0.2 * k, bold=True)
            nv.move_to(self.w([left + bw + 0.15, yy]) + RIGHT * nv.width / 2).set_opacity(val.get_fill_opacity())
            val.become(nv)
        yl = even(f"{y:.0f}", 0.7 * self.k(), bold=True, color="soft").move_to(self.w([self.w_ / 2 - 0.7, self.h / 2 + 0.45]))
        yl.set_opacity(self.yearl.get_fill_opacity())
        self.yearl.become(yl)
        self.value = y


def parliament(args: list[str], mods: dict, c=None) -> VGroup:
    """Seats in a half circle, row on row, each party's together from the left, with a key: `parliament A:303 B:52`.
    Parts: the parties (each its seats and its key line)."""
    data = []
    for a in args:
        if ":" in a:
            k, v = a.rsplit(":", 1)
            data.append((k.replace("_", " "), int(float(v))))
    total = sum(v for _, v in data) or 1
    r0, r1 = float(mods.get("r", 2.6)) * 0.45, float(mods.get("r", 2.6))
    rows = max(3, min(14, int(math.sqrt(total / 4))))
    seats = []
    for i in range(rows):
        r = r0 + (r1 - r0) * i / max(1, rows - 1)
        n = max(1, round(total * r / sum(r0 + (r1 - r0) * j / max(1, rows - 1) for j in range(rows))))
        seats += [(math.pi * (1 - (k + 0.5) / n), r) for k in range(n)]
    seats = seats[:total] + [(math.pi / 2, r1)] * max(0, total - len(seats))
    seats.sort(key=lambda s: -s[0])                        # from the left
    dot_r = min(0.12, (r1 - r0) / rows * 0.42)
    g = VGroup()
    k = 0
    for j, (name, v) in enumerate(data):
        colour = col(PALETTE[j % len(PALETTE)])
        part = VGroup(*(Dot([r * math.cos(a), r * math.sin(a), 0], radius=dot_r, color=colour) for a, r in seats[k:k + v]))
        k += v
        part.add(VGroup(Dot(radius=0.09, color=colour), label(f"{name} {v}", 0.12, "ink"))
                 .arrange(RIGHT, buff=0.12).move_to([0, -0.45 - 0.32 * j, 0]))
        g.add(part)
    if mods.get("majority"):
        g.add(Line([0, 0, 0], [0, r1 + 0.25, 0], stroke_color=col("ink"), stroke_width=2))
    return g


class Market(Anchored, Valued, VGroup):
    """Supply and demand: two lines and where they cross (the price and the amount sold, dashed to the axes).
    `grow MKT 1` moves demand right by 1 (`grow MKT -1` left); parts: [axes, supply, demand, the crossing]."""

    def __init__(self, w: float = 5.5, h: float = 4.0, c=None):
        super().__init__()
        self.wd, self.h, self.value = w, h, 0.0
        ink = col("ink")
        ax = VGroup(tipped([[-w / 2, -h / 2, 0], [w / 2 + 0.2, -h / 2, 0]], ink, STROKE * 0.4, smooth=False),
                    tipped([[-w / 2, -h / 2, 0], [-w / 2, h / 2 + 0.2, 0]], ink, STROKE * 0.4, smooth=False),
                    label("quantity", 0.12, "ink").move_to([w / 2 - 0.4, -h / 2 - 0.3, 0]),
                    label("price", 0.12, "ink").move_to([-w / 2 - 0.45, h / 2 - 0.1, 0]).rotate(math.pi / 2))
        self.s = (np.array([-w / 2 + 0.4, -h / 2 + 0.4, 0]), np.array([w / 2 - 0.4, h / 2 - 0.4, 0]))
        self.d0 = (np.array([-w / 2 + 0.4, h / 2 - 0.4, 0]), np.array([w / 2 - 0.4, -h / 2 + 0.4, 0]))
        self.supply = VGroup(Line(*self.s, stroke_color=col("teal"), stroke_width=STROKE * 0.8),
                             label("supply", 0.13, "teal").move_to(self.s[1] + UP * 0.25))
        self.demand = VGroup(Line(*self.d0, stroke_color=col(c or "coral"), stroke_width=STROKE * 0.8),
                             label("demand", 0.13, c or "coral").move_to(self.d0[1] + DOWN * 0.25 + LEFT * 0.2))
        self.cross = VGroup()
        self.add(ax, self.supply, self.demand, self.cross)
        self._anchor()
        self._cross()

    def _cross(self):
        dx = self.value
        a, b = self.s
        c_, d = self.d0[0] + RIGHT * dx, self.d0[1] + RIGHT * dx
        A = np.array([[b[0] - a[0], -(d[0] - c_[0])], [b[1] - a[1], -(d[1] - c_[1])]])
        try:
            t, _ = np.linalg.solve(A, (c_ - a)[:2])
        except np.linalg.LinAlgError:
            return
        p = a + (b - a) * t
        ox, oy = -self.wd / 2, -self.h / 2
        op = self.cross.get_fill_opacity() if len(self.cross) else 1.0
        P = self.w(p)
        new = VGroup(Dot(P, radius=0.09, color=col("ink")),
                     DashedVMobject(Line(P, self.w([p[0], oy])), num_dashes=10).set_stroke(col("soft"), 2),
                     DashedVMobject(Line(P, self.w([ox, p[1]])), num_dashes=10).set_stroke(col("soft"), 2))
        if len(self.cross):
            new.set_opacity(op)
            self.cross.become(new)
        else:
            self.cross.add(*new)

    def set_value(self, v: float) -> None:
        self.demand.shift((self.w([v, 0]) - self.w([self.value, 0])))
        self.value = v
        self._cross()


def climate(args: list[str], mods: dict, c=None) -> VGroup:
    """A climate chart: each month's rain as a bar and temperature as a line: `climate J:14:20 F:17:25 ...`
    (month:°C:mm). Parts: the months (each its bar, its point, the line to it)."""
    data = []
    for a in args:
        bits = a.split(":")
        if len(bits) == 3:
            data.append((bits[0], float(bits[1]), float(bits[2])))
    if not data:
        raise ValueError("a climate chart needs months: J:14:20 (month:temperature:rain)")
    w, h = float(mods.get("w", 7)), float(mods.get("h", 3.6))
    tmax, tmin = max(t for _, t, _ in data), min(0, min(t for _, t, _ in data))
    rmax = max(r for _, _, r in data) or 1
    n = len(data)
    g = VGroup()
    base = Line([-w / 2, -h / 2, 0], [w / 2, -h / 2, 0], stroke_color=col("soft"), stroke_width=2)
    prev = None
    for i, (m, t, r) in enumerate(data):
        x = -w / 2 + w * (i + 0.5) / n
        bh = max(0.02, h * 0.85 * r / rmax)
        bar = Rectangle(width=w / n * 0.62, height=bh, fill_color=col("sky"), fill_opacity=0.85, stroke_width=0)
        bar.move_to([x, -h / 2 + bh / 2, 0])
        p = np.array([x, -h / 2 + h * 0.9 * (t - tmin) / ((tmax - tmin) or 1), 0])
        part = VGroup(base) if i == 0 else VGroup()
        part.add(bar, Dot(p, radius=0.07, color=col(c or "coral")), even(m, 0.13).move_to([x, -h / 2 - 0.25, 0]))
        if prev is not None:
            part.add(Line(prev, p, stroke_color=col(c or "coral"), stroke_width=STROKE * 0.7))
        prev = p
        g.add(part)
    g.add(VGroup(label("rain, mm", 0.11, "navy").move_to([-w / 2 + 0.5, h / 2 + 0.2, 0]),
                 label("°C", 0.11, c or "coral").move_to([w / 2 - 0.2, h / 2 + 0.2, 0])))
    return g


def scatter(data, mods, c=None) -> VGroup:
    """Points (x:y), each a dot, on two axes. Parts: [axes], then the points."""
    w, h = float(mods.get("w", 6)), float(mods.get("h", 4))
    xs = [float(k) for k, _ in data]
    ys = [v for _, v in data]
    x0, x1, y0, y1 = min(xs), max(xs), min(0, min(ys)), max(ys)
    X = lambda x: -w / 2 + w * (x - x0) / ((x1 - x0) or 1)   # noqa: E731
    Y = lambda y: -h / 2 + h * (y - y0) / ((y1 - y0) or 1)   # noqa: E731
    ax = VGroup(Line([-w / 2 - 0.2, -h / 2 - 0.2, 0], [w / 2 + 0.2, -h / 2 - 0.2, 0], stroke_color=col("soft"), stroke_width=2),
                Line([-w / 2 - 0.2, -h / 2 - 0.2, 0], [-w / 2 - 0.2, h / 2 + 0.2, 0], stroke_color=col("soft"), stroke_width=2))
    g = VGroup(ax)
    for x, y in zip(xs, ys):
        g.add(Dot([X(x), Y(y), 0], radius=0.09, color=col(c or "coral")).set_stroke(col("ink"), 1.5))
    return g


def area(data, mods, c=None) -> VGroup:
    """A line with the ground under it filled. Parts: [the area, the line, the values]."""
    w, h = float(mods.get("w", 7)), float(mods.get("h", 3.2))
    try:
        xs = [float(k) for k, _ in data]
    except ValueError:
        xs = list(range(len(data)))
    top = max(v for _, v in data) * 1.12 or 1
    pts = [np.array([-w / 2 + w * (x - xs[0]) / ((xs[-1] - xs[0]) or 1), -h / 2 + h * v / top, 0.0])
           for x, (_, v) in zip(xs, data)]
    fill = Polygon(*([pts[0] * [1, 0, 0] + [0, -h / 2, 0]] + pts + [pts[-1] * [1, 0, 0] + [0, -h / 2, 0]]),
                   fill_color=col(c or "accent"), fill_opacity=0.45, stroke_width=0)
    line = VMobject(stroke_color=col(c or "ink"), stroke_width=STROKE * 0.7).set_points_as_corners(pts)
    vals = VGroup(*(VGroup(halo(even(_fmt(v, mods), 0.18, bold=True)).next_to(p, UP, buff=0.12),
                           even(k, 0.12, color="soft").move_to([p[0], -h / 2 - 0.25, 0])) for p, (k, v) in zip(pts, data)))
    return VGroup(fill, line, vals)


# ---------------------------------------------------------------- storytelling ---------------------------------------

def quiz(args: list[str], mods: dict, c=None) -> VGroup:
    """A question and its choices, then the answer shown: `quiz "Which came first?" "Jikji" "Gutenberg" answer 1`.
    Parts: [the question], each choice, [the answer shown] (bring it on after a pause for the viewer to guess)."""
    q, choices = (args[0] if args else ""), args[1:]
    ans = int(mods.get("answer", 1)) - 1
    w = float(mods.get("w", 8))
    head = VGroup(label("quick question", 0.13, "soft"), para(q, 0.36, w, bold=True)).arrange(DOWN, buff=0.18)
    g = VGroup(head)
    cards = []
    n = len(choices)
    cw = min(3.2, (w - 0.3 * (n - 1)) / max(1, n))
    for i, ch in enumerate(choices):
        face = RoundedRectangle(width=cw, height=1.0, corner_radius=0.12, fill_color=col("card"), fill_opacity=1,
                                stroke_color=col("soft"), stroke_width=1.5)
        letter = even("ABCDEF"[i], 0.2, bold=True, color="soft").move_to(face.get_corner(UP + LEFT) + np.array([0.25, -0.25, 0]))
        words = para(ch, 0.24, cw - 0.4)
        card = VGroup(soft_shadow(face), face, letter, words.move_to(face))
        card.move_to([-(n - 1) * (cw + 0.3) / 2 + i * (cw + 0.3), -1.2, 0])
        cards.append(card)
        g.add(card)
    if 0 <= ans < len(cards):
        good = cards[ans]
        reveal = VGroup(RoundedRectangle(width=cw + 0.16, height=1.16, corner_radius=0.16, stroke_color=col("green"),
                                         stroke_width=STROKE * 0.8, fill_opacity=0).move_to(good[1]))
        for i, card in enumerate(cards):
            if i != ans:
                reveal.add(Rectangle(width=cw + 0.05, height=1.05, fill_color=col("bg"), fill_opacity=0.6,
                                     stroke_width=0).move_to(card[1]))
        tick = VMobject(stroke_color=col("green"), stroke_width=STROKE * 1.1)
        o = good[1].get_corner(UP + RIGHT) + np.array([-0.35, -0.3, 0])
        tick.set_points_as_corners([o + np.array([-0.15, 0, 0]), o + np.array([-0.04, -0.12, 0]), o + np.array([0.15, 0.13, 0])])
        reveal.add(tick)
        g.add(reveal)
    head.move_to([0, 0.6, 0])
    return g


def lens(pic, at: str, mods: dict, c=None) -> VGroup:
    """A magnifier on a picture: a ring on a spot (`"@0.6,0.4"`, from its top left) and, beside the picture, that
    spot made `zoom` times bigger in a circle (r), joined by two lines. Parts: [the ring on it, the lines, the lens]."""
    from manim import ImageMobject
    m = getattr(pic, "frame_of", pic)
    fx, fy = (float(v) for v in at.strip("@ ").split(","))
    ul, dr = m.get_corner(UP + LEFT), m.get_corner(DOWN + RIGHT)
    spot = np.array([ul[0] + (dr[0] - ul[0]) * fx, ul[1] + (dr[1] - ul[1]) * fy, 0.0])
    zoom, r = float(mods.get("zoom", 3)), float(mods.get("r", 1.1))
    side = -1 if mods.get("side") == "left" else 1
    centre = np.array([(dr[0] if side > 0 else ul[0]) + side * (r + 0.5), spot[1], 0.0])
    small = r / zoom
    ring = Circle(radius=small, stroke_color=col(c or "coral"), stroke_width=STROKE * 0.6).move_to(spot)
    frame = Circle(radius=r, stroke_color=col(c or "coral"), stroke_width=STROKE * 0.9).move_to(centre)
    inside = None
    if isinstance(m, ImageMobject):
        px = m.pixel_array
        H, W = px.shape[:2]
        cx, cy = fx * W, fy * H
        rad = small / (dr[0] - ul[0]) * W
        x0, x1 = int(max(0, cx - rad)), int(min(W, cx + rad))
        y0, y1 = int(max(0, cy - rad)), int(min(H, cy + rad))
        crop = px[y0:y1, x0:x1].copy()
        if crop.size:
            yy, xx = np.mgrid[0:crop.shape[0], 0:crop.shape[1]]
            outside = (xx - (cx - x0)) ** 2 + (yy - (cy - y0)) ** 2 > rad ** 2
            if crop.shape[2] == 4:
                crop[..., 3] = np.where(outside, 0, crop[..., 3])
            inside = ImageMobject(crop)
            inside.height = 2 * r * crop.shape[0] / (2 * rad)
            inside.move_to(centre + np.array([((x0 + x1) / 2 - cx) / rad * r, -((y0 + y1) / 2 - cy) / rad * r, 0]))
    disc = Circle(radius=r, fill_color=col("card"), fill_opacity=1, stroke_width=0).move_to(centre)
    d = centre - spot
    nrm = np.array([-d[1], d[0], 0.0]) / (np.linalg.norm(d) or 1)
    lines = VGroup(Line(spot + nrm * small, centre + nrm * r, stroke_color=col(c or "coral"), stroke_width=2),
                   Line(spot - nrm * small, centre - nrm * r, stroke_color=col(c or "coral"), stroke_width=2))
    from manim import Group
    big = Group(disc, inside, frame) if inside is not None else VGroup(disc, frame)
    return Group(ring, lines, big)


def split(args: list[str], mods: dict, c=None) -> VGroup:
    """Two halves side by side, each with its heading, a line between: `split "manor" "town"`. Places: `sp.left`,
    `sp.right` (the middle of each half, for `at`). Parts: [left half, right half, the line]."""
    w, h = float(mods.get("w", 13)), float(mods.get("h", 6.4))
    g = VGroup()
    for i, words in enumerate(args[:2] or ["before", "after"]):
        x = (-1 if i == 0 else 1) * w / 4
        face = Rectangle(width=w / 2 - 0.15, height=h, fill_color=col("card" if i == 0 else "sand"), fill_opacity=0.55,
                         stroke_width=0).move_to([x, 0, 0])
        head = even(words.replace("_", " ").upper(), 0.34, bold=True).move_to([x, h / 2 - 0.45, 0])
        bar = Rectangle(width=head.width + 0.3, height=0.1, fill_color=col("soft" if i == 0 else (c or "accent")),
                        fill_opacity=1, stroke_width=0).next_to(head, DOWN, buff=0.1)
        g.add(VGroup(face, head, bar))
    g.add(Line([0, -h / 2, 0], [0, h / 2, 0], stroke_color=col("ink"), stroke_width=STROKE * 0.5))
    g.places = Keys({"left": Dot([-w / 4, -0.3, 0], radius=0.001).set_opacity(0),
                     "right": Dot([w / 4, -0.3, 0], radius=0.001).set_opacity(0)})
    g.add(*g.places.values())
    return g


class Clock(Valued, VGroup):
    """A clock face whose hands show the hour: `clock 9`; `count CLK 17` turns them on to five o'clock."""

    def __init__(self, hours: float, r: float = 1.3, c=None):
        super().__init__()
        self.r = r
        face = Circle(radius=r, fill_color=col("card"), fill_opacity=1, stroke_color=col("ink"), stroke_width=STROKE * 0.7)
        ticks = VGroup()
        for k in range(12):
            a = math.pi / 2 - math.tau * k / 12
            d = np.array([math.cos(a), math.sin(a), 0])
            ticks.add(Line(d * r * (0.82 if k % 3 else 0.74), d * r * 0.92, stroke_color=col("ink"),
                           stroke_width=STROKE * (0.6 if k % 3 == 0 else 0.35)))
        self.hh = Line(ORIGIN, UP * r * 0.5, stroke_color=col("ink"), stroke_width=STROKE * 1.0)
        self.mh = Line(ORIGIN, UP * r * 0.78, stroke_color=col(c or "coral"), stroke_width=STROKE * 0.7)
        self.add(VGroup(soft_shadow(face), face, ticks), self.hh, self.mh, Dot(radius=0.07, color=col("ink")))
        self.value = 0.0
        self.set_value(hours)

    def set_value(self, v: float) -> None:
        c = self[0][1].get_center()
        for hand, ang, ln in ((self.hh, v / 12 * math.tau, 0.5), (self.mh, (v % 1) * math.tau, 0.78)):
            a = math.pi / 2 - ang
            new = Line(c, c + np.array([math.cos(a), math.sin(a), 0]) * self.r * ln,
                       stroke_color=hand.get_stroke_color(), stroke_width=hand.get_stroke_width())
            new.set_stroke(opacity=hand.get_stroke_opacity())
            hand.become(new)
        self.value = v


class Odometer(Valued, VGroup):
    """A number whose digits roll like a counter as it counts (`count OD 1500`): each digit slides up to the next."""

    def __init__(self, v: float, digits: int = 0, size: float = 0.8, prefix: str = "", suffix: str = "", c=None):
        super().__init__()
        self.n = digits or max(1, len(str(int(abs(v)))))
        self.size, self.prefix, self.suffix, self.c = size, prefix, suffix, c
        self.cw = size * 0.78
        box = RoundedRectangle(width=self.n * self.cw + 0.3, height=size * 1.9, corner_radius=0.1,
                               fill_color=col("ink"), fill_opacity=1, stroke_width=0)
        self.cells = VGroup(*(VGroup() for _ in range(self.n)))
        self.add(box, self.cells)
        if prefix:
            self.add(even(prefix, size * 0.7, bold=True).next_to(box, LEFT, buff=0.12))
        if suffix:
            self.add(even(suffix, size * 0.7, bold=True).next_to(box, RIGHT, buff=0.12))
        self.value = v
        self.set_value(v)

    def set_value(self, v: float) -> None:
        v = max(0.0, v)
        box = self[0]
        op = box.get_fill_opacity()
        for i in range(self.n):
            place = 10 ** (self.n - 1 - i)
            d = (v / place) % 10                  # this digit, with how far it has rolled to the next
            low, frac = int(d), d - int(d)
            if place > 1:
                frac = max(0.0, (frac - 0.9) / 0.1) if frac > 0.9 else 0.0   # a digit rolls as the one after it wraps
            x = box.get_left()[0] + 0.15 + self.cw * (i + 0.5)
            y = box.get_center()[1]
            a = even(str(low % 10), self.size, bold=True, color="white").move_to([x, y + frac * self.size * 1.2, 0])
            b = even(str((low + 1) % 10), self.size, bold=True, color="white").move_to([x, y - (1 - frac) * self.size * 1.2, 0])
            a.set_opacity(op * (1 - frac))
            b.set_opacity(op * frac)
            self.cells[i].become(VGroup(a, b))
        self.value = v


def clipping(headline: str, mods: dict, c=None) -> VGroup:
    """A torn newspaper clipping: masthead, date, the headline, columns of text. Parts: [paper, masthead and date,
    headline, columns]."""
    w, h = float(mods.get("w", 5)), float(mods.get("h", 3.6))
    rng = np.random.default_rng(zlib.crc32(headline.encode()) % 997)
    top = [[-w / 2 + w * t, h / 2 + rng.uniform(-0.06, 0.06), 0] for t in np.linspace(0, 1, 18)]
    bottom = [[w / 2 - w * t, -h / 2 + rng.uniform(-0.08, 0.08), 0] for t in np.linspace(0, 1, 18)]
    paper = Polygon(*top, *bottom, fill_color=col("white"), fill_opacity=1, stroke_color=col("sand"), stroke_width=1.5)
    mast = VGroup(even(str(mods.get("sub") or "THE CHRONICLE").upper(), 0.22, bold=True),
                  Line([-w / 2 + 0.3, 0, 0], [w / 2 - 0.3, 0, 0], stroke_color=col("ink"), stroke_width=2))
    mast.arrange(DOWN, buff=0.08).move_to([0, h / 2 - 0.35, 0])
    if mods.get("date"):
        mast.add(label(str(mods["date"]), 0.09, "soft").next_to(mast, DOWN, buff=0.05))
    head = para(headline.upper(), 0.36, w - 0.6, bold=True).next_to(mast, DOWN, buff=0.18)
    cols = VGroup()
    y = head.get_bottom()[1] - 0.25
    while y > -h / 2 + 0.25:
        for k in range(3):
            cw = (w - 0.8) / 3
            x0 = -w / 2 + 0.3 + k * (cw + 0.1)
            ln = cw * (rng.uniform(0.6, 1.0) if rng.random() < 0.25 else 1.0)
            cols.add(Rectangle(width=ln, height=0.05, fill_color=col("soft"), fill_opacity=0.6, stroke_width=0)
                     .move_to([x0 + ln / 2, y, 0]))
        y -= 0.16
    g = VGroup(VGroup(soft_shadow(paper), paper), mast, head, cols)
    if "rot" not in mods:
        g.rotate(math.radians(2.5))
    return g


# ---------------------------------------------------------------- maps -----------------------------------------------

def shade(m, title: str, args: list[str], mods: dict, c=None) -> VGroup:
    """Countries (or states of the map's year) coloured by a value, lightest to strongest, with a key: a choropleth.
    `shade "literacy, %" on eu France:30 Italy:45`. Parts: the countries (lowest first), the key last."""
    import look
    data = []
    for a in args:
        if ":" in a:
            k, v = a.rsplit(":", 1)
            try:
                data.append((k.replace("_", " "), float(v.replace(",", ""))))
            except ValueError:
                pass
    if not data:
        raise ValueError("shade needs values: France:30 Italy:45")
    lo, hi = min(v for _, v in data), max(v for _, v in data)
    ramp = [np.array([int(h_[i:i + 2], 16) for i in (1, 3, 5)]) for h_ in (col("sand"), col(c or "accent"), col("coral"))]

    def tint(v):
        t = (v - lo) / ((hi - lo) or 1)
        a, b, s = (ramp[0], ramp[1], t * 2) if t < 0.5 else (ramp[1], ramp[2], t * 2 - 1)
        rgb = a + (b - a) * s
        return "#" + "".join(f"{int(x):02x}" for x in rgb)
    g = VGroup()
    for name, v in sorted(data, key=lambda x: x[1]):
        try:
            g.add(look.region(m, name, {"opacity": 0.85, "fill": tint(v)}))
        except (KeyError, ValueError):
            continue
    steps = VGroup(*(Rectangle(width=0.32, height=0.2, fill_color=tint(lo + (hi - lo) * k / 5), fill_opacity=0.9,
                               stroke_width=0) for k in range(6))).arrange(RIGHT, buff=0)
    sea = m[0]
    legend = VGroup(label(title, 0.1, "ink"), steps,
                    VGroup(label(f"{lo:g}", 0.09, "ink"), label(f"{hi:g}", 0.09, "ink")))
    legend[2][0].next_to(steps, DOWN, buff=0.06).align_to(steps, LEFT)
    legend[2][1].next_to(steps, DOWN, buff=0.06).align_to(steps, RIGHT)
    legend[0].next_to(steps, UP, buff=0.08).align_to(steps, LEFT)
    back = Rectangle(width=legend.width + 0.3, height=legend.height + 0.25, fill_color=col("card"), fill_opacity=0.9,
                     stroke_color=col("soft"), stroke_width=1).move_to(legend)
    key_ = VGroup(back, legend)
    key_.move_to(sea.get_corner(DOWN + LEFT) + np.array([key_.width / 2 + 0.15, key_.height / 2 + 0.15, 0]))
    g.add(key_)
    return g


def march(points: list, mods: dict, c=None) -> VGroup:
    """A thick arrow that swells along a route (an army, a migration, a trade wind): `march mp.lisbon mp.havana`.
    Draw it on with `in M draw`."""
    pts = [np.array([p[0], p[1], 0.0]) for p in points]
    if len(pts) < 2:
        raise ValueError("a march needs two points or more")
    spine = VMobject().set_points_smoothly(pts) if len(pts) > 2 else VMobject().set_points_as_corners(pts)
    n = 60
    wmax = float(mods.get("width", 1)) * 0.22
    left, right = [], []
    for i in range(n + 1):
        t = i / n * 0.9
        p = spine.point_from_proportion(t)
        q = spine.point_from_proportion(min(1, t + 0.01))
        d = (q - p) / (np.linalg.norm(q - p) or 1)
        nrm = np.array([-d[1], d[0], 0.0])
        wdt = wmax * (0.25 + 0.75 * t / 0.9)
        left.append(p + nrm * wdt)
        right.append(p - nrm * wdt)
    end = spine.point_from_proportion(1.0)
    base = spine.point_from_proportion(0.9)
    d = (end - base) / (np.linalg.norm(end - base) or 1)
    nrm = np.array([-d[1], d[0], 0.0])
    head = [base + nrm * wmax * 2.0, end, base - nrm * wmax * 2.0]
    body = Polygon(*left, *head, *right[::-1], fill_color=col(c or "coral"), fill_opacity=0.85,
                   stroke_color=col(c or "coral"), stroke_width=1)
    g = VGroup(body)
    g.track = spine
    return g


def inset(m, mods: dict, c=None) -> VGroup:
    """A small map of the world in the corner of a map, a box on it where the map is."""
    import look
    from shapely.geometry import box as sbox
    wm = look.GeoMap("world", float(mods.get("w", 2.6)), float(mods.get("h", 1.4)), fill=None)
    lon0, lat0, lon1, lat1 = m.bounds
    a, b = wm.to_screen(lon0, lat0), wm.to_screen(lon1, lat1)
    frame = Rectangle(width=max(0.06, abs(b[0] - a[0])), height=max(0.06, abs(b[1] - a[1])), stroke_color=col(c or "coral"),
                      stroke_width=STROKE * 0.5, fill_opacity=0).move_to((a + b) / 2)
    g = VGroup(wm, frame)
    sea = m[0]
    corner = {"left": DOWN + LEFT, "upleft": UP + LEFT, "upright": UP + RIGHT}.get(str(mods.get("side")), DOWN + RIGHT)
    g.move_to(sea.get_corner(corner) - corner * np.array([g.width / 2 + 0.12, g.height / 2 + 0.12, 0]))
    return g


def layers(args: list[str], mods: dict, c=None) -> VGroup:
    """Layers, the top first: bands one under another (soil, rock, the sea's zones), or `round` as rings of a cut-away
    globe (crust, mantle, outer core, inner core). Parts: the layers."""
    fills = ["sand", "accent", "coral", "red", "gold", "soft", "teal", "navy"]
    g = VGroup()
    g.places = Keys()
    n = len(args)
    if mods.get("round"):
        r = float(mods.get("r", 2.6))
        for i, words in enumerate(args):
            ro = r * (1 - i / n)
            ri = r * (1 - (i + 1) / n)
            ring = Annulus(inner_radius=max(ri, 0.001), outer_radius=ro, fill_color=col(fills[i % len(fills)]),
                           fill_opacity=1, stroke_color=col("ink"), stroke_width=1.5)
            mid = (ro + ri) / 2
            a = math.radians(35 - 18 * i)          # each its own ray, so the names stand apart on the right
            spot = np.array([mid * math.cos(a), mid * math.sin(a), 0])
            t = even(words.replace("_", " ").upper(), 0.15, bold=True)
            t.move_to([r + 0.35 + t.width / 2, r * 0.75 - i * 0.42, 0])
            lead = VGroup(Dot(spot, radius=0.04, color=col("ink")),
                          Line(spot, t.get_left() + LEFT * 0.08, stroke_color=col("ink"), stroke_width=1.5))
            part = VGroup(ring, lead, t)
            g.add(part)
            g.places[key(words)] = part
        return g
    w, h = float(mods.get("w", 7)), float(mods.get("h", 4))
    lh = h / max(1, n)
    for i, words in enumerate(args):
        y = h / 2 - lh * (i + 0.5)
        rng = np.random.default_rng(i + 7)
        top = [[-w / 2 + w * t, y + lh / 2 + (rng.uniform(-0.05, 0.05) if i else 0), 0] for t in np.linspace(0, 1, 14)]
        band = Polygon(*top, [w / 2, y - lh / 2, 0], [-w / 2, y - lh / 2, 0], fill_color=col(fills[i % len(fills)]),
                       fill_opacity=0.9, stroke_color=col("ink"), stroke_width=1)
        t = halo(even(words.replace("_", " ").upper(), 0.18, bold=True)).move_to([0, y, 0])
        part = VGroup(band, t)
        g.add(part)
        g.places[key(words)] = part
    return g


class Globe(VGroup):
    """The Earth as a globe seen from above a place (`globe 10,50`: lon,lat): the sea a disc, the land on it, what is
    on the far side hidden. Places: `gl.paris` (a place on the near side). Parts: [sea, land]."""

    def __init__(self, lon: float, lat: float, r: float = 2.6, c=None):
        super().__init__()
        import geo
        self.lon0, self.lat0, self.r = math.radians(lon), math.radians(lat), r
        sea = Circle(radius=r, fill_color=col("sky"), fill_opacity=0.45, stroke_color=col("soft"), stroke_width=2)
        land = VGroup()
        for _, g_ in geo.countries((-180, -85, 180, 85)):
            for poly in getattr(g_, "geoms", [g_]):
                if poly.area < 0.6:
                    continue
                poly = poly.simplify(0.6, preserve_topology=True)
                pts = [self._p(x, y) for x, y in list(poly.exterior.coords)[:-1]]
                vis = [p for p in pts if p is not None]
                if len(vis) < 3 or len(vis) < 0.8 * len(pts):
                    continue
                m = VMobject(fill_color=col(c or "card"), fill_opacity=1, stroke_color=col("soft"), stroke_width=1)
                m.set_points_as_corners([*vis, vis[0]])
                land.add(m)
        self._ref = VGroup(*(Dot(p, radius=0.001).set_opacity(0) for p in (ORIGIN, RIGHT, UP)))
        self.add(sea, land, VGroup(Circle(radius=r, stroke_color=col("ink"), stroke_width=2.5)), self._ref)
        self.places = _GlobePlaces(self)

    def _p(self, lon, lat):
        lam, phi = math.radians(lon), math.radians(lat)
        cosc = math.sin(self.lat0) * math.sin(phi) + math.cos(self.lat0) * math.cos(phi) * math.cos(lam - self.lon0)
        if cosc < 0:
            return None
        x = self.r * math.cos(phi) * math.sin(lam - self.lon0)
        y = self.r * (math.cos(self.lat0) * math.sin(phi) - math.sin(self.lat0) * math.cos(phi) * math.cos(lam - self.lon0))
        return np.array([x, y, 0.0])

    def to_screen(self, lon, lat):
        p = self._p(lon, lat)
        if p is None:
            raise KeyError("that place is on the far side of the globe")
        o, x, y = (d.get_center() for d in self._ref)
        return o + p[0] * (x - o) + p[1] * (y - o)


class _GlobePlaces:
    def __init__(self, g):
        self.g = g

    def __contains__(self, name) -> bool:
        try:
            self[name]
            return True
        except KeyError:
            return False

    def __getitem__(self, name):
        import geo
        lon, lat = geo.place(name)
        self.g.to_screen(lon, lat)
        return _At(lambda: self.g.to_screen(lon, lat))

    def __iter__(self):
        return iter(())
