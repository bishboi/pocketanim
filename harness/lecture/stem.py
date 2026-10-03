"""STEM boards: labelled diagrams, graphs and worked solutions, drawn in Manim.

A lecture for mathematics, physics or chemistry teaches on a board: the whole frame, no side panel. On it:

* sketch   a labelled diagram from primitives (line, arrow, rect, circle, polygon, spring, ground, angle, dim,
           dot, text, curve) in a 10 x 6 box, each part with an id so it can be revealed a beat at a time;
* presets  the diagrams physics keeps drawing, built from the same primitives with their parts named:
           incline (a block on a wedge, friction, forces and their components), pulley (Atwood machine, block
           on a table), piston (gas, pressure, force, heat), spring, pendulum, projectile, circuit, lever, lens;
* graph    axes with curves, points, guide lines, a shaded area, a tangent, data points, added item by item;
* work     a worked solution, a line per beat, beside the figure it works on;
* problem  a long question: its statement across the top, its figure on the left, its solution on the right.

The geometry here (the presets) is plain data, so the compiler can check a script's ids without Manim; the
drawing is BoardMixin, which pocket_lecture's MapLecture inherits.
"""

from __future__ import annotations

import math
import re

W, H = 10.0, 6.0          # the sketch box every preset and sketch is laid out in (y up)

PRIMITIVES = {"line", "arrow", "rect", "circle", "polygon", "spring", "ground", "angle", "dim", "dot", "text",
              "curve"}
PRESETS = ("incline", "pulley", "piston", "spring", "pendulum", "projectile", "circuit", "lever", "lens")


# ════════════════════════════════════════════════════════════════════════
#  Presets: the diagrams physics keeps drawing, as named primitives
# ════════════════════════════════════════════════════════════════════════

def _v(a, b, t=1.0):
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


def _add(p, d, k=1.0):
    return [p[0] + d[0] * k, p[1] + d[1] * k]


def _lab(labels: dict, key: str, default: str) -> str:
    return str((labels or {}).get(key, default))


def incline(angle: float = 30, labels: dict | None = None, forces=("mg", "N"), friction: bool = False,
            components: bool = False, applied: str | None = None, motion: str = "down", **_) -> list[dict]:
    """A block on a wedge. forces: any of mg, N, f (friction), F (applied, up or down the slope: `applied`);
    components: mg sinθ along the slope and mg cosθ into it (dashed). Ids: ground, wedge, theta, block, mg, N,
    f, F, mg_sin, mg_cos, motion."""
    a = math.radians(max(10.0, min(60.0, float(angle))))
    base = min(8.0, 4.4 / math.tan(a))
    o = [1.0, 0.9]
    top = [o[0] + base, o[1] + base * math.tan(a)]
    right = [o[0] + base, o[1]]
    along, normal = [math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]
    bw, bh = 1.3, 0.8
    foot = _v(o, top, 0.5)
    c = _add(_add(foot, normal, bh / 2), along, 0)
    out = [{"id": "ground", "type": "ground", "from": [0.3, o[1]], "to": [9.7, o[1]]},
           {"id": "wedge", "type": "polygon", "points": [o, right, top], "fill": "DUNE"},
           {"id": "theta", "type": "angle", "at": o, "from": right, "to": top, "label": _lab(labels, "theta", "θ")},
           {"id": "block", "type": "rect", "at": c, "w": bw, "h": bh, "angle": math.degrees(a), "fill": "RIVER",
            "label": _lab(labels, "block", "m")}]
    forces = [str(f) for f in forces or []]
    if friction and "f" not in forces:
        forces.append("f")
    if applied and "F" not in forces:
        forces.append("F")
    if "mg" in forces:
        out.append({"id": "mg", "type": "arrow", "from": c, "to": [c[0], c[1] - 1.7], "color": "ROSE",
                    "label": _lab(labels, "mg", "mg")})
    if "N" in forces:
        out.append({"id": "N", "type": "arrow", "from": c, "to": _add(c, normal, 1.5), "color": "GREEN",
                    "label": _lab(labels, "N", "N")})
    up = 1 if motion == "down" else -1            # friction opposes the motion
    if "f" in forces:
        start = _add(c, along, up * bw / 2)
        out.append({"id": "f", "type": "arrow", "from": start, "to": _add(start, along, up * 1.2), "color": "GOLD",
                    "label": _lab(labels, "f", "f = μN")})
    if "F" in forces:
        sign = 1 if (applied or "up") == "up" else -1
        start = _add(c, along, -sign * bw / 2)
        out.append({"id": "F", "type": "arrow", "from": _add(start, along, -sign * 1.3), "to": start,
                    "color": "VIOLET", "label": _lab(labels, "F", "F")})
    if components:
        g = 1.7
        out.append({"id": "mg_sin", "type": "arrow", "from": c, "to": _add(c, along, -g * math.sin(a)),
                    "color": "ROSE", "dashed": True, "label": _lab(labels, "mg_sin", "mg sinθ")})
        out.append({"id": "mg_cos", "type": "arrow", "from": c, "to": _add(c, normal, -g * math.cos(a)),
                    "color": "ROSE", "dashed": True, "label": _lab(labels, "mg_cos", "mg cosθ")})
    if labels and labels.get("motion"):
        start = _add(_add(c, normal, 0.9), along, 0.4 * up)
        out.append({"id": "motion", "type": "arrow", "from": start, "to": _add(start, along, -up * 1.0),
                    "color": "MUTED", "label": str(labels["motion"])})
    return out


def pulley(kind: str = "atwood", labels: dict | None = None, forces=("T", "W"), friction: bool = False,
           accel: bool = False, **_) -> list[dict]:
    """kind atwood: two masses over a fixed pulley. kind table: a block on a table pulled by a hanging mass.
    Ids: ceiling|table, pulley, rope, m1, m2, T1, T2, W1, W2 (and N, f on the table; a1, a2 with accel)."""
    forces = [str(f) for f in forces or []]
    m1, m2 = _lab(labels, "m1", "m₁"), _lab(labels, "m2", "m₂")
    if kind == "table":
        out = [{"id": "table", "type": "ground", "from": [0.4, 3.0], "to": [7.0, 3.0]},
               {"id": "leg", "type": "line", "from": [6.8, 3.0], "to": [6.8, 0.5]},
               {"id": "pulley", "type": "circle", "at": [7.35, 3.35], "r": 0.35, "fill": "MUTED"},
               {"id": "m1", "type": "rect", "at": [3.4, 3.45], "w": 1.5, "h": 0.9, "fill": "RIVER", "label": m1},
               {"id": "rope", "type": "line", "from": [4.15, 3.45], "to": [7.35, 3.7], "color": "CREAM"},
               {"id": "rope2", "type": "line", "from": [7.7, 3.35], "to": [7.7, 2.0], "color": "CREAM"},
               {"id": "m2", "type": "rect", "at": [7.7, 1.5], "w": 0.9, "h": 1.0, "fill": "ROSE", "label": m2}]
        if "T" in forces:
            out += [{"id": "T1", "type": "arrow", "from": [4.15, 3.45], "to": [5.4, 3.45], "color": "GOLD",
                     "label": _lab(labels, "T1", "T")},
                    {"id": "T2", "type": "arrow", "from": [7.7, 2.0], "to": [7.7, 2.9], "color": "GOLD",
                     "label": _lab(labels, "T2", "T")}]
        if "W" in forces:
            out += [{"id": "W1", "type": "arrow", "from": [3.4, 3.0], "to": [3.4, 1.8], "color": "ROSE",
                     "label": _lab(labels, "W1", "m₁g")},
                    {"id": "W2", "type": "arrow", "from": [7.7, 1.0], "to": [7.7, 0.0], "color": "ROSE",
                     "label": _lab(labels, "W2", "m₂g")}]
        if "N" in forces:
            out.append({"id": "N", "type": "arrow", "from": [3.4, 3.9], "to": [3.4, 5.1], "color": "GREEN",
                        "label": _lab(labels, "N", "N")})
        if friction or "f" in forces:
            out.append({"id": "f", "type": "arrow", "from": [2.65, 3.45], "to": [1.5, 3.45], "color": "GOLD",
                        "label": _lab(labels, "f", "f")})
        if accel:
            out += [{"id": "a1", "type": "arrow", "from": [2.9, 4.4], "to": [4.0, 4.4], "color": "MUTED",
                     "label": "a"},
                    {"id": "a2", "type": "arrow", "from": [8.6, 1.9], "to": [8.6, 0.9], "color": "MUTED", "label": "a"}]
        return out
    out = [{"id": "ceiling", "type": "ground", "from": [3.3, 5.7], "to": [6.7, 5.7], "side": "above"},
           {"id": "rod", "type": "line", "from": [5.0, 5.7], "to": [5.0, 4.6]},
           {"id": "pulley", "type": "circle", "at": [5.0, 4.6], "r": 0.6, "fill": "MUTED"},
           {"id": "rope", "type": "line", "from": [4.4, 4.6], "to": [4.4, 2.5], "color": "CREAM"},
           {"id": "rope2", "type": "line", "from": [5.6, 4.6], "to": [5.6, 1.9], "color": "CREAM"},
           {"id": "m1", "type": "rect", "at": [4.4, 2.0], "w": 0.9, "h": 1.0, "fill": "RIVER", "label": m1},
           {"id": "m2", "type": "rect", "at": [5.6, 1.3], "w": 1.0, "h": 1.2, "fill": "ROSE", "label": m2}]
    if "T" in forces:
        out += [{"id": "T1", "type": "arrow", "from": [4.4, 2.5], "to": [4.4, 3.6], "color": "GOLD",
                 "label": _lab(labels, "T1", "T")},
                {"id": "T2", "type": "arrow", "from": [5.6, 1.9], "to": [5.6, 3.0], "color": "GOLD",
                 "label": _lab(labels, "T2", "T")}]
    if "W" in forces:
        out += [{"id": "W1", "type": "arrow", "from": [4.4, 1.5], "to": [4.4, 0.4], "color": "ROSE",
                 "label": _lab(labels, "W1", "m₁g")},
                {"id": "W2", "type": "arrow", "from": [5.6, 0.7], "to": [5.6, -0.3], "color": "ROSE",
                 "label": _lab(labels, "W2", "m₂g")}]
    if accel:
        out += [{"id": "a1", "type": "arrow", "from": [3.4, 1.6], "to": [3.4, 2.6], "color": "MUTED", "label": "a"},
                {"id": "a2", "type": "arrow", "from": [6.6, 1.8], "to": [6.6, 0.8], "color": "MUTED", "label": "a"}]
    return out


def piston(labels: dict | None = None, force: bool = True, heat: bool = False, pressure: bool = True,
           **_) -> list[dict]:
    """A gas in a cylinder under a piston. Ids: cylinder, piston, rod, gas, F, P (pressure arrows), V, Q (heat)."""
    out = [{"id": "cylinder", "type": "polygon", "points": [[2.5, 5.2], [2.5, 0.8], [7.5, 0.8], [7.5, 5.2]],
            "open": True, "fill": None},
           {"id": "gas", "type": "rect", "at": [5.0, 2.05], "w": 4.9, "h": 2.4, "fill": "RIVER", "stroke": False,
            "label": _lab(labels, "V", "gas: P, V, T")},
           {"id": "piston", "type": "rect", "at": [5.0, 3.45], "w": 4.95, "h": 0.4, "fill": "MUTED"},
           {"id": "rod", "type": "line", "from": [5.0, 3.65], "to": [5.0, 5.0], "color": "MUTED"}]
    if force:
        out.append({"id": "F", "type": "arrow", "from": [5.0, 6.1], "to": [5.0, 5.05], "color": "ROSE",
                    "label": _lab(labels, "F", "F")})
    if pressure:
        out.append({"id": "P", "type": "group", "items": [
            {"type": "arrow", "from": [4.0, 2.9], "to": [4.0, 3.2], "color": "GOLD"},
            {"type": "arrow", "from": [6.0, 2.9], "to": [6.0, 3.2], "color": "GOLD"},
            {"type": "arrow", "from": [3.3, 2.0], "to": [2.7, 2.0], "color": "GOLD"},
            {"type": "arrow", "from": [6.7, 2.0], "to": [7.3, 2.0], "color": "GOLD",
             "label": _lab(labels, "P", "P")}]})
    if heat:
        out.append({"id": "Q", "type": "arrow", "from": [5.0, -0.4], "to": [5.0, 0.7], "color": "ROSE",
                    "label": _lab(labels, "Q", "heat Q")})
    return out


def spring(labels: dict | None = None, displacement: bool = True, force: bool = True, **_) -> list[dict]:
    """A block on a spring, fixed to a wall. Ids: wall, ground, spring, block, F, x."""
    out = [{"id": "wall", "type": "ground", "from": [1.0, 1.2], "to": [1.0, 4.2], "side": "left"},
           {"id": "ground", "type": "ground", "from": [1.0, 1.2], "to": [9.5, 1.2]},
           {"id": "spring", "type": "spring", "from": [1.0, 1.95], "to": [5.2, 1.95], "coils": 8},
           {"id": "block", "type": "rect", "at": [5.95, 1.95], "w": 1.5, "h": 1.5, "fill": "RIVER",
            "label": _lab(labels, "block", "m")}]
    if force:
        # Above the spring, on the block's side: the restoring force.
        out.append({"id": "F", "type": "arrow", "from": [5.6, 3.1], "to": [4.1, 3.1], "color": "ROSE",
                    "label": _lab(labels, "F", "F = −kx")})
    if displacement:
        out.append({"id": "x", "type": "dim", "from": [4.2, 0.55], "to": [5.2, 0.55], "label": _lab(labels, "x", "x")})
    return out


def pendulum(angle: float = 25, labels: dict | None = None, forces=("T", "mg"), **_) -> list[dict]:
    """A bob on a string from a support. Ids: support, rest, string, bob, theta, swing, T, mg, L."""
    a = math.radians(max(5.0, min(60.0, float(angle))))
    pivot, length = [5.0, 5.6], 4.2
    bob = [pivot[0] + length * math.sin(a), pivot[1] - length * math.cos(a)]
    out = [{"id": "support", "type": "ground", "from": [3.8, 5.6], "to": [6.2, 5.6], "side": "above"},
           {"id": "rest", "type": "line", "from": pivot, "to": [5.0, pivot[1] - length], "dashed": True,
            "color": "MUTED"},
           {"id": "string", "type": "line", "from": pivot, "to": bob, "color": "CREAM",
            "label": _lab(labels, "L", "L")},
           {"id": "theta", "type": "angle", "at": pivot, "from": [5.0, 1.0], "to": bob, "r": 1.0,
            "label": _lab(labels, "theta", "θ")},
           {"id": "swing", "type": "curve", "dashed": True, "color": "MUTED",
            "points": [[pivot[0] + length * math.sin(t), pivot[1] - length * math.cos(t)]
                       for t in (-a, -a / 2, 0, a / 2, a)]},
           {"id": "bob", "type": "circle", "at": bob, "r": 0.35, "fill": "RIVER", "label": _lab(labels, "bob", "m")}]
    if "T" in (forces or []):
        out.append({"id": "T", "type": "arrow", "from": bob, "to": _v(bob, pivot, 0.35), "color": "GOLD",
                    "label": _lab(labels, "T", "T")})
    if "mg" in (forces or []):
        out.append({"id": "mg", "type": "arrow", "from": bob, "to": [bob[0], bob[1] - 1.4], "color": "ROSE",
                    "label": _lab(labels, "mg", "mg")})
    return out


def projectile(angle: float = 45, labels: dict | None = None, components: bool = True, **_) -> list[dict]:
    """A launch at an angle: the path, the launch velocity and its parts, the greatest height and the range.
    Ids: ground, path, u, ux, uy, theta, H, R, top."""
    a = math.radians(max(10.0, min(80.0, float(angle))))
    start, rng = [0.8, 0.8], 8.4
    height = min(4.4, rng * math.tan(a) / 4)
    pts = [[start[0] + rng * t, start[1] + 4 * height * t * (1 - t)] for t in [i / 16 for i in range(17)]]
    u = [1.6 * math.cos(a), 1.6 * math.sin(a)]
    out = [{"id": "ground", "type": "ground", "from": [0.3, 0.8], "to": [9.7, 0.8]},
           {"id": "path", "type": "curve", "points": pts, "dashed": True, "color": "CREAM"},
           {"id": "u", "type": "arrow", "from": start, "to": _add(start, u), "color": "GOLD",
            "label": _lab(labels, "u", "u")},
           {"id": "theta", "type": "angle", "at": start, "from": [3.0, 0.8], "to": _add(start, u), "r": 0.7,
            "label": _lab(labels, "theta", "θ")},
           {"id": "top", "type": "dot", "at": [start[0] + rng / 2, start[1] + height]},
           {"id": "H", "type": "dim", "from": [start[0] + rng / 2 + 0.4, start[1]],
            "to": [start[0] + rng / 2 + 0.4, start[1] + height], "label": _lab(labels, "H", "H")},
           {"id": "R", "type": "dim", "from": [start[0], 0.25], "to": [start[0] + rng, 0.25],
            "label": _lab(labels, "R", "R")}]
    if components:
        out += [{"id": "ux", "type": "arrow", "from": start, "to": [start[0] + u[0], start[1]], "color": "GREEN",
                 "dashed": True, "label": _lab(labels, "ux", "u cosθ")},
                {"id": "uy", "type": "arrow", "from": start, "to": [start[0], start[1] + u[1]], "color": "GREEN",
                 "dashed": True, "label": _lab(labels, "uy", "u sinθ")}]
    return out


def _zigzag(a, b, n=6, amp=0.22) -> list:
    """A resistor between a and b: straight leads, a zigzag in the middle."""
    d = [b[0] - a[0], b[1] - a[1]]
    length = math.hypot(*d) or 1.0
    ux, uy = d[0] / length, d[1] / length
    nx, ny = -uy, ux
    pts = [a, _v(a, b, 0.25)]
    for k in range(1, 2 * n):
        t = 0.25 + 0.5 * k / (2 * n)
        side = amp if k % 2 else -amp
        pts.append([a[0] + d[0] * t + nx * side, a[1] + d[1] * t + ny * side])
    return pts + [_v(a, b, 0.75), b]


def circuit(kind: str = "series", labels: dict | None = None, resistors=("R₁", "R₂"), current: bool = True,
            **_) -> list[dict]:
    """A battery and resistors, in series or in parallel. Ids: battery, wire, R1, R2 (R3...), I, V."""
    names = [str(r) for r in (resistors or ["R"])][:3]
    out = [{"id": "battery", "type": "group", "items": [
               {"type": "line", "from": [1.5, 2.6], "to": [1.5, 3.4], "width": 6},
               {"type": "line", "from": [1.8, 2.8], "to": [1.8, 3.2], "width": 6},
               {"type": "text", "at": [0.9, 3.0], "text": _lab(labels, "V", "V")}]},
           {"id": "wire", "type": "group", "items": [
               {"type": "line", "from": [1.5, 3.0], "to": [1.0, 3.0]}, {"type": "line", "from": [1.0, 3.0], "to": [1.0, 5.0]},
               {"type": "line", "from": [1.8, 3.0], "to": [2.4, 3.0]}, {"type": "line", "from": [2.4, 3.0], "to": [2.4, 1.0]},
               {"type": "line", "from": [2.4, 1.0], "to": [9.0, 1.0]}, {"type": "line", "from": [9.0, 1.0], "to": [9.0, 5.0]}]}]
    if kind == "parallel":
        out[1]["items"] += [{"type": "line", "from": [1.0, 5.0], "to": [3.5, 5.0]},
                            {"type": "line", "from": [7.5, 5.0], "to": [9.0, 5.0]}]
        ys = [5.0, 3.9, 2.8][:len(names)]
        for k, (name, y) in enumerate(zip(names, ys), 1):
            if y != 5.0:
                out[1]["items"] += [{"type": "line", "from": [3.5, 5.0], "to": [3.5, y]},
                                    {"type": "line", "from": [7.5, 5.0], "to": [7.5, y]}]
            out.append({"id": f"R{k}", "type": "curve", "sharp": True, "points": _zigzag([3.5, y], [7.5, y], 5),
                        "color": "GOLD", "label": name})
    else:
        span = 8.0 / len(names)
        x = 1.0
        for k, name in enumerate(names, 1):
            a, b = [x, 5.0], [x + span, 5.0]
            out.append({"id": f"R{k}", "type": "curve", "sharp": True, "points": _zigzag(a, b, 5), "color": "GOLD",
                        "label": name})
            x += span
    if current:
        out.append({"id": "I", "type": "arrow", "from": [5.0, 1.0], "to": [3.6, 1.0], "color": "ROSE",
                    "label": _lab(labels, "I", "I")})
    return out


def lever(labels: dict | None = None, loads=("W₁", "W₂"), **_) -> list[dict]:
    """A beam on a fulcrum with a load on each side. Ids: fulcrum, beam, L1, L2, d1, d2, ground."""
    out = [{"id": "ground", "type": "ground", "from": [1.0, 1.0], "to": [9.0, 1.0]},
           {"id": "fulcrum", "type": "polygon", "points": [[4.4, 1.0], [5.6, 1.0], [5.0, 2.2]], "fill": "DUNE"},
           {"id": "beam", "type": "rect", "at": [5.0, 2.32], "w": 8.4, "h": 0.24, "fill": "MUTED"},
           {"id": "L1", "type": "arrow", "from": [1.6, 4.0], "to": [1.6, 2.5], "color": "ROSE",
            "label": str(list(loads)[0] if loads else "W₁")},
           {"id": "L2", "type": "arrow", "from": [8.0, 4.0], "to": [8.0, 2.5], "color": "ROSE",
            "label": str(list(loads)[1] if loads and len(loads) > 1 else "W₂")},
           {"id": "d1", "type": "dim", "from": [1.6, 1.6], "to": [5.0, 1.6], "label": _lab(labels, "d1", "d₁")},
           {"id": "d2", "type": "dim", "from": [5.0, 1.6], "to": [8.0, 1.6], "label": _lab(labels, "d2", "d₂")}]
    return out


def lens(labels: dict | None = None, kind: str = "convex", rays: bool = True, **_) -> list[dict]:
    """A thin lens forming an image: the principal axis, the lens, focal points, object, rays, image.
    Ids: axis, lens, F1, F2, object, ray1, ray2, image."""
    out = [{"id": "axis", "type": "line", "from": [0.2, 3.0], "to": [9.8, 3.0], "dashed": True, "color": "MUTED"},
           {"id": "lens", "type": "curve", "color": "RIVER", "width": 5,
            "points": [[5.0, 5.3], [5.35, 3.0], [5.0, 0.7], [4.65, 3.0], [5.0, 5.3]] if kind == "convex"
            else [[4.7, 5.3], [5.05, 3.0], [4.7, 0.7], [5.3, 0.7], [4.95, 3.0], [5.3, 5.3], [4.7, 5.3]]},
           {"id": "F1", "type": "dot", "at": [3.0, 3.0], "label": "F"},
           {"id": "F2", "type": "dot", "at": [7.0, 3.0], "label": "F"},
           {"id": "object", "type": "arrow", "from": [1.8, 3.0], "to": [1.8, 4.3], "color": "GOLD",
            "label": _lab(labels, "object", "object")}]
    if kind == "convex":
        img_x = 5.0 + 1 / (1 / 2.0 - 1 / 3.2)       # 1/v - 1/u = 1/f with u = -3.2, f = 2
        mag = -(img_x - 5.0) / 3.2
        tip = [img_x, 3.0 + 1.3 * mag]
        if rays:
            out += [{"id": "ray1", "type": "curve", "sharp": True, "color": "ROSE",
                     "points": [[1.8, 4.3], [5.0, 4.3], tip]},
                    {"id": "ray2", "type": "line", "from": [1.8, 4.3], "to": tip, "color": "ROSE"}]
        out.append({"id": "image", "type": "arrow", "from": [img_x, 3.0], "to": tip, "color": "GREEN",
                    "label": _lab(labels, "image", "image")})
    return out


PRESET_FUNCS = {"incline": incline, "pulley": pulley, "piston": piston, "spring": spring, "pendulum": pendulum,
                "projectile": projectile, "circuit": circuit, "lever": lever, "lens": lens}


# ════════════════════════════════════════════════════════════════════════
#  Motion: a diagram that moves while it is explained
# ════════════════════════════════════════════════════════════════════════

# What each preset does when it is set going: the block slides down the wedge, the bob swings, the ball flies.
MOTIONS = {"incline": "slide", "pendulum": "swing", "projectile": "fly", "spring": "oscillate", "pulley": "pull",
           "lever": "tilt", "piston": "press", "circuit": "pulse", "lens": "pulse"}
MOTION_KINDS = {"slide", "swing", "fly", "oscillate", "pull", "tilt", "press", "move", "turn", "pulse"}
# Kinds that need a particular preset; move, turn and pulse work on any sketch.
MOTION_PRESET = {"slide": "incline", "swing": "pendulum", "fly": "projectile", "oscillate": "spring",
                 "pull": "pulley", "tilt": "lever", "press": "piston"}


def motion_problem(preset: str | None, ids: list[str], op: dict) -> str | None:
    """What stops a motion op, given the diagram's preset kind (None for a sketch) and its part ids."""
    kind = op.get("kind") or (MOTIONS.get(preset) if preset else None)
    if not kind:
        return ("'motion' on a sketch needs kind: move (parts, by: [dx, dy]), turn (parts, angle, about: [x, y]) "
                "or pulse (parts)")
    if kind not in MOTION_KINDS:
        return f"motion kind {kind!r} is not one of {', '.join(sorted(MOTION_KINDS))}"
    if kind in MOTION_PRESET and preset != MOTION_PRESET[kind]:
        return f"motion {kind!r} is for a {MOTION_PRESET[kind]} diagram; on this one use move, turn or pulse"
    parts = [str(x) for x in op.get("parts") or []]
    unknown = [x for x in parts if x not in ids]
    if unknown:
        return f"motion parts: no part {unknown[0]!r} (its parts: {', '.join(ids) or 'none named'})"
    if kind in ("move", "turn", "pulse") and not parts:
        return f"motion {kind!r} needs parts: the ids of the parts that move"
    if kind == "move" and not (isinstance(op.get("by"), (list, tuple)) and len(op["by"]) == 2):
        return "motion move needs by: [dx, dy], how far the parts move, in the sketch's units"
    if kind == "turn" and (op.get("angle") is None or not (isinstance(op.get("about"), (list, tuple))
                                                           and len(op["about"]) == 2)):
        return "motion turn needs angle (degrees, + is anticlockwise) and about: [x, y], the point it turns about"
    return None


def _attached(elements: list[dict], moving: list[str], pad: float = 0.45) -> list[str]:
    """The arrows and marks that ride on the moving bodies: anything starting on (or just off) a moving block or
    ball goes with it (its weight, its normal force, the friction on it)."""
    boxes = []
    for e in elements:
        if str(e.get("id")) in moving and isinstance(e.get("at"), (list, tuple)):
            x, y = (float(v) for v in e["at"])
            hw = float(e.get("w", 2 * float(e.get("r", 0.5)))) / 2 + pad
            hh = float(e.get("h", 2 * float(e.get("r", 0.5)))) / 2 + pad
            boxes.append((x - hw, y - hh, x + hw, y + hh))
    out = []
    for e in elements:
        key = str(e.get("id"))
        if key in moving or e.get("type") not in ("arrow", "dot", "text") or not isinstance(e.get("from", e.get("at")),
                                                                                          (list, tuple)):
            continue
        x, y = (float(v) for v in e.get("from", e.get("at")))
        if any(a <= x <= c and b <= y <= d for a, b, c, d in boxes):
            out.append(key)
    return out


def motion_plan(preset: str | None, params: dict, elements: list[dict], op: dict) -> tuple[list[dict], bool]:
    """The steps of a motion, in sketch units, and whether it goes back to where it started (there and back, so
    the diagram stays as labelled). Steps: {"move": ids, "by": [dx, dy]}; {"turn": ids, "deg": d, "about": [x, y]};
    {"stretch": id, "fixed": [x, y], "end": [x, y], "by": [dx, dy]} (a rope or spring that lengthens or shortens);
    {"ball": [x, y], "r": r, "about": [x, y], "deg": d} (a ball that flies along an arc); {"pulse": ids}."""
    kind = op.get("kind") or MOTIONS.get(preset or "", "pulse")
    params = params or {}
    dist = float(op.get("distance") or 0)
    back = op.get("back")
    if kind == "slide":
        a = math.radians(max(10.0, min(60.0, float(params.get("angle", 30)))))
        sign = -1 if str(params.get("motion", "down")) == "down" else 1
        d = dist or 1.6
        ids = ["block"] + _attached(elements, ["block"])
        steps = [{"move": ids, "by": [sign * d * math.cos(a), sign * d * math.sin(a)]}]
    elif kind == "swing":
        a = max(5.0, min(60.0, float(params.get("angle", 25))))
        steps = [{"turn": ["string", "bob"] + _attached(elements, ["bob"]), "deg": -2 * a, "about": [5.0, 5.6]}]
    elif kind == "fly":
        a = math.radians(max(10.0, min(80.0, float(params.get("angle", 45)))))
        x0, y0, rng = 0.8, 0.8, 8.4
        h = min(4.4, rng * math.tan(a) / 4)
        cy = y0 + (h * h - (rng / 2) ** 2) / (2 * h)       # the circle through the launch, the top and the landing
        r = y0 + h - cy
        sweep = 2 * math.degrees(math.asin(min(1.0, (rng / 2) / r)))
        steps = [{"ball": [x0, y0], "r": 0.2, "about": [x0 + rng / 2, cy], "deg": -sweep}]
        back = False if back is None else back
    elif kind == "oscillate":
        d = dist or 0.9
        steps = [{"move": ["block"] + _attached(elements, ["block"]), "by": [d, 0.0]},
                 {"stretch": "spring", "fixed": [1.0, 1.95], "end": [5.2, 1.95], "by": [d, 0.0]}]
    elif kind == "pull":
        d = dist or 0.8
        if params.get("kind") == "table":
            steps = [{"move": ["m1"] + _attached(elements, ["m1"]), "by": [d, 0.0]},
                     {"stretch": "rope", "fixed": [7.35, 3.7], "end": [4.15, 3.45], "by": [d, 0.0]},
                     {"move": ["m2"] + _attached(elements, ["m2"]), "by": [0.0, -d]},
                     {"stretch": "rope2", "fixed": [7.7, 3.35], "end": [7.7, 2.0], "by": [0.0, -d]}]
        else:
            # The heavier side goes down: m2 unless the script says m1.
            down = "m1" if str(op.get("heavier", "m2")) == "m1" else "m2"
            up = "m2" if down == "m1" else "m1"
            ends = {"m1": ("rope", [4.4, 4.6], [4.4, 2.5]), "m2": ("rope2", [5.6, 4.6], [5.6, 1.9])}
            steps = [{"move": [down] + _attached(elements, [down]), "by": [0.0, -d]},
                     {"stretch": ends[down][0], "fixed": ends[down][1], "end": ends[down][2], "by": [0.0, -d]},
                     {"move": [up] + _attached(elements, [up]), "by": [0.0, d]},
                     {"stretch": ends[up][0], "fixed": ends[up][1], "end": ends[up][2], "by": [0.0, d]}]
    elif kind == "tilt":
        steps = [{"turn": ["beam", "L1", "L2"], "deg": float(op.get("angle", -8)), "about": [5.0, 2.32]}]
    elif kind == "press":
        d = dist or 0.8
        steps = [{"move": ["piston", "rod", "F"], "by": [0.0, -d]}]
    elif kind == "move":
        steps = [{"move": [str(x) for x in op.get("parts") or []], "by": [float(v) for v in op["by"]]}]
    elif kind == "turn":
        steps = [{"turn": [str(x) for x in op.get("parts") or []], "deg": float(op["angle"]),
                  "about": [float(v) for v in op["about"]]}]
    else:
        parts = [str(x) for x in op.get("parts") or []]
        if not parts:
            parts = [str(e["id"]) for e in elements if e.get("id") is not None
                     and (e.get("type") == "arrow" or str(e["id"]).startswith(("ray", "R", "I")))]
        steps = [{"pulse": parts}]
    if op.get("parts") and kind not in ("move", "turn", "pulse"):
        # The script may name the parts that ride along: they replace the preset's own choice.
        for step in steps:
            for key in ("move", "turn"):
                if key in step and step is steps[0]:
                    step[key] = [str(x) for x in op["parts"]]
    return steps, (True if back is None else bool(back))


def preset_elements(kind: str, params: dict) -> list[dict]:
    """A preset diagram's primitives: {"id", "type", ...} in the 10 x 6 box."""
    return PRESET_FUNCS[kind](**{k: v for k, v in (params or {}).items() if k not in ("op", "id", "show", "title")})


def element_ids(elements: list[dict]) -> list[str]:
    return [str(e["id"]) for e in elements if e.get("id") is not None]


def sketch_problem(op: dict) -> str | None:
    """What stops a sketch (or preset) op, if anything."""
    kind = op.get("op")
    if kind == "sketch":
        items = op.get("items") or []
        if not items or not isinstance(items, list):
            return ("'sketch' needs items: primitives in a 10 x 6 box, e.g. {\"id\":\"b\",\"type\":\"rect\",\"at\":[5,2],"
                    "\"w\":1.5,\"h\":1,\"label\":\"m\"} (types: " + ", ".join(sorted(PRIMITIVES)) + ")")
        for item in items:
            if not isinstance(item, dict) or item.get("type") not in PRIMITIVES | {"group"}:
                return f"sketch item {item!r}: type must be one of {', '.join(sorted(PRIMITIVES))}"
        return None
    try:
        preset_elements(kind, op)
    except (TypeError, ValueError, KeyError, IndexError) as error:
        return f"{kind}: {error}"
    return None


def op_elements(op: dict) -> list[dict]:
    """The primitives a sketch or preset op draws."""
    if op.get("op") == "sketch":
        return list(op.get("items") or [])
    return preset_elements(op["op"], op)


# ════════════════════════════════════════════════════════════════════════
#  Graph items
# ════════════════════════════════════════════════════════════════════════

GRAPH_KINDS = {"curve", "point", "vline", "hline", "area", "tangent", "segment", "data", "label"}


def graph_problem(op: dict) -> str | None:
    items = op.get("items") or []
    if not items:
        return ("'graph' needs items: [{\"id\":\"c\",\"kind\":\"curve\",\"expr\":\"x^2\",\"label\":\"y = x²\"}, "
                "{\"id\":\"p\",\"kind\":\"point\",\"at\":[2,4],\"label\":\"(2, 4)\"}, ...] (kinds: "
                + ", ".join(sorted(GRAPH_KINDS)) + ")")
    x = op.get("x") or [-5, 5]
    try:
        if len(x) != 2 or float(x[0]) >= float(x[1]):
            return "graph x must be [min, max]"
    except (TypeError, ValueError):
        return "graph x must be [min, max]"
    from pocket_lecture import safe_function
    import numpy as np

    for item in items:
        if not isinstance(item, dict) or item.get("kind") not in GRAPH_KINDS:
            return f"graph item {item!r}: kind must be one of {', '.join(sorted(GRAPH_KINDS))}"
        if item["kind"] in ("curve", "area", "tangent"):
            try:
                safe_function(str(item.get("expr", "")))(np.linspace(float(x[0]), float(x[1]), 5))
            except Exception as error:  # noqa: BLE001
                return f"graph {item.get('id') or item['kind']}: {error}"
        if item["kind"] == "point" and not (isinstance(item.get("at"), list) and len(item["at"]) == 2):
            return "a graph point needs at: [x, y]"
    return None


def _label_text(text) -> str:
    """A label as it reads: TeX-ish m_1, v^2, \\theta become m₁, v², θ."""
    import pocket_lecture as pl

    text = str(text)
    return pl.unicode_math(text) if re.search(r"[_^\\]", text) else text


# ════════════════════════════════════════════════════════════════════════
#  Drawing: the board, sketches, graphs, worked solutions, problems
# ════════════════════════════════════════════════════════════════════════

# The board: the whole frame below the key-point strip and above the caption (centre x, centre y, w, h).
BOARD = (0.0, -0.13, 13.5, 5.65)
STRIP_Y = 3.1
LABEL_SIZE = 20


def _nice_step(span: float) -> float:
    raw = span / 6 if span > 0 else 1.0
    power = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * power:
            return m * power
    return 10 * power


def _with_companions(show: list[str], ids: list[str]) -> list[str]:
    """What a `show` list means: a part's own pieces come with it (rope2 with rope, the leg with the table,
    the rod with the ceiling), so a script naming the rope never leaves a block hanging in the air."""
    companions = {"table": ("leg",), "ceiling": ("rod",), "rope": ("rope2", "rope3"), "wedge": ("ground",)}
    out = list(show)
    for name in show:
        for other in ids:
            if other not in out and (re.fullmatch(re.escape(name) + r"\d+", other)
                                     or other in companions.get(name, ())):
                out.append(other)
    return out


def _bounds(mobs):
    import numpy as np

    pts = [m.get_all_points() for m in mobs if len(m.get_all_points())]
    if not pts:
        return None
    arr = np.vstack(pts)
    return arr[:, 0].min(), arr[:, 1].min(), arr[:, 0].max(), arr[:, 1].max()


def _fit_into(mobs, box, margin: float = 0.12) -> None:
    """Shrink and centre a drawing's parts together so all of them, labels too, sit inside the box."""
    import numpy as np

    b = _bounds(mobs)
    if b is None:
        return
    cx, cy, w, h = box
    bw, bh = max(b[2] - b[0], 1e-3), max(b[3] - b[1], 1e-3)
    f = min((w - 2 * margin) / bw, (h - 2 * margin) / bh, 1.0)
    centre = np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2, 0.0])
    shift = np.array([cx, cy, 0.0]) - centre
    for m in mobs:
        if f < 1.0:
            m.scale(f, about_point=centre)
        m.shift(shift)


def _moving(builder):
    """A part's `.animate` move as an animation the exporter writes as a move of that part (an `xform` verb with
    its rate), not as a morph into a copy: in a group, Manim makes the builder a transform, which the program
    played by keeping the part where it was and adding a moved copy."""
    anim = builder.build()
    anim.panim_xform = True
    return anim


def _labels_and_ink(mobs):
    labels, ink = [], []
    for mob in mobs:
        for part in mob.get_family():
            if getattr(part, "is_label", False):
                labels.append(part)
    label_family = {id(x) for lab in labels for x in lab.get_family()}
    for mob in mobs:
        for part in mob.family_members_with_points():
            if id(part) not in label_family:
                ink.append(part)
    return labels, ink


def curve_samples(points, per_curve: int = 8):
    """Points along a VMobject's cubic curves (x, y), not only its anchors: a long straight edge has anchors at
    its ends alone, and a label across its middle would not touch one."""
    import numpy as np

    pts = np.asarray(points, dtype=float)
    n = len(pts) // 4 * 4
    if n < 4:
        return pts[:, :2]
    b = pts[:n].reshape(-1, 4, 3)
    t = np.linspace(0.0, 1.0, per_curve)[:, None, None]
    curve = ((1 - t) ** 3) * b[:, 0] + 3 * ((1 - t) ** 2) * t * b[:, 1] + 3 * (1 - t) * t * t * b[:, 2] \
        + (t ** 3) * b[:, 3]
    return curve.reshape(-1, 3)[:, :2]


def _settle_labels(mobs, box, gap: float = 0.06) -> None:
    """Move each label that sits on a line, on a filled part or on another label to the nearest clear spot
    around where it was put (up to about a label's size away), and keep it inside the box."""
    import numpy as np

    labels, ink = _labels_and_ink(mobs)
    if not labels:
        return
    parts = [curve_samples(part.points, 24) for part in ink if len(part.points) >= 2]
    # Whose each label and shape is, and the bodies (a ball, a block) another element's label must not sit in.
    owner = {}
    for index, mob in enumerate(mobs):
        for part in mob.get_family():
            owner.setdefault(id(part), index)
    bodies = []
    for part in ink:
        if type(part).__name__ in ("Circle", "Rectangle", "Polygon", "Square", "RoundedRectangle") and part.width > 0.2 \
                and part.height > 0.2:
            b = _bounds([part])
            bodies.append((owner.get(id(part)), b))
    cx, cy, w, h = box
    lo_x, hi_x, lo_y, hi_y = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    placed = []

    def box_of(centre, lab):
        return (centre[0] - lab.width / 2 - gap, centre[1] - lab.height / 2 - gap,
                centre[0] + lab.width / 2 + gap, centre[1] + lab.height / 2 + gap)

    def cost(b, own, mine=None):
        # Each line or shape the label sits on counts once, however long the stretch under it.
        c = -own
        area = max((b[2] - b[0]) * (b[3] - b[1]), 1e-6)
        for who, q in bodies:
            if who == mine:
                continue
            ox = min(b[2], q[2]) - max(b[0], q[0])
            oy = min(b[3], q[3]) - max(b[1], q[1])
            if ox > 0 and oy > 0 and ox * oy > 0.25 * area:
                c += 3          # inside another part's body: "Kick F" written across the ball
        for pts in parts:
            if ((pts[:, 0] > b[0]) & (pts[:, 0] < b[2]) & (pts[:, 1] > b[1]) & (pts[:, 1] < b[3])).any():
                c += 1
        for p in placed:
            ox = min(b[2], p[2]) - max(b[0], p[0])
            oy = min(b[3], p[3]) - max(b[1], p[1])
            if ox > 0 and oy > 0:
                c += 40 + 200 * ox * oy
        # Out of the box: pushed back in by the fit later, but shrinking the whole drawing for it costs.
        c += 2 * (max(0, lo_x - b[0]) + max(0, b[2] - hi_x) + max(0, lo_y - b[1]) + max(0, b[3] - hi_y))
        return c

    for lab in labels:
        home = lab.get_center()[:2].copy()
        # A label may sit on its own element's anchor: only a crossing, not a touch, counts against it.
        own = 0
        mine = owner.get(id(lab))
        best, best_cost = home, cost(box_of(home, lab), own, mine)
        if best_cost <= 0:
            placed.append(box_of(home, lab))
            continue
        step_x, step_y = lab.width / 2 + 0.12, lab.height / 2 + 0.1
        for reach in (0.6, 1.0, 1.5, 2.1):
            for ang in range(0, 360, 30):
                t = math.radians(ang)
                at = home + np.array([math.cos(t) * step_x * reach, math.sin(t) * step_y * reach])
                c = cost(box_of(at, lab), own, mine) + 0.25 * reach
                if c < best_cost - 1e-6:
                    best, best_cost = at, c
            if best_cost <= 0.25 * reach:
                break
        lab.move_to([best[0], best[1], 0])
        placed.append(box_of(best, lab))


class BoardMixin:
    """The board layout and the STEM drawings, for pocket_lecture's MapLecture."""

    board_mode = False

    # ---------------- the board layout ----------------
    def board(self) -> None:
        """Teach on the whole frame: no side panel; panel titles and facts become one short key-point strip."""
        self.board_mode = True
        self.STAGE = BOARD
        self.strip = {"title": None, "point": None}

    def leave_board(self) -> None:
        self.board_mode = False
        self.__dict__.pop("STAGE", None)

    def _strip(self, title=None, point=None, clear=False):
        """Put a title and/or a key point in the strip over the board; the old ones fade."""
        import pocket_lecture as pl
        from manim import AnimationGroup, FadeIn, FadeOut, LEFT, RIGHT

        going, coming = [], []
        if clear or title is not None:
            for k in ("title", "point"):
                if self.strip.get(k) is not None:
                    going.append(FadeOut(self.strip[k]))
                    self.strip[k] = None
        if point is not None and self.strip.get("point") is not None:
            going.append(FadeOut(self.strip["point"]))
            self.strip["point"] = None
        left = -6.7
        if title is not None:
            self.strip["title"] = title.move_to([left, STRIP_Y, 0], aligned_edge=LEFT)
            title.set_z_index(pl.Z_PANEL_TEXT)
            coming.append(FadeIn(title, shift=RIGHT * 0.15))
        if point is not None:
            head = self.strip.get("title")
            x = head.get_right()[0] + 0.45 if head is not None else left
            pl.fit(point, 6.7 - x)
            self.strip["point"] = point.move_to([x, STRIP_Y, 0], aligned_edge=LEFT)
            point.set_z_index(pl.Z_PANEL_TEXT)
            coming.append(FadeIn(point, shift=RIGHT * 0.15))
        if not going and not coming:
            return None
        return AnimationGroup(AnimationGroup(*going), AnimationGroup(*coming), lag_ratio=0.5) if going else \
            AnimationGroup(*coming)

    def board_title(self, title: str, sub: str | None = None):
        import pocket_lecture as pl
        from manim import BOLD, VGroup, RIGHT

        text = title.upper() if pl.TH["upper"] else title
        head = VGroup(pl.T(text, 32, pl.P.TITLE, font=pl.TH["serif"], weight=BOLD))
        if sub:
            head.add(pl.T(sub, 21, pl.P.MUTED))
            head.arrange(RIGHT, buff=0.25, aligned_edge=[0, -1, 0])
        pl.fit(head, 7.5)
        return self._strip(title=head)

    def board_point(self, text: str, color: str | None = None):
        import pocket_lecture as pl
        from manim import Dot, VGroup, RIGHT

        dot = Dot(radius=0.07, color=color or pl.P.SAND)
        line = pl.T(str(text), 23, color or pl.P.CREAM)
        return self._strip(point=VGroup(dot, line).arrange(RIGHT, buff=0.18))

    def board_stat(self, value: str, label: str, color: str | None = None):
        import pocket_lecture as pl
        from manim import BOLD, VGroup, RIGHT, DOWN

        group = VGroup(pl.T(str(value), 26, color or pl.P.GOLD, font=pl.TH["serif"], weight=BOLD),
                       pl.T(str(label), 18, pl.P.MUTED)).arrange(RIGHT, buff=0.2, aligned_edge=DOWN)
        return self._strip(point=group)

    def board_bars(self, items, color: str | None = None, unit: str = ""):
        """A bar chart across the board."""
        import pocket_lecture as pl
        from manim import Rectangle, VGroup, LEFT, RIGHT, Group

        cx, cy, w, h = self.STAGE
        items = list(items)[:8]
        top = max((float(v) for _, v in items), default=1.0) or 1.0
        rows = VGroup()
        for name, value in items:
            label = pl.fit(pl.T(str(name), 20, pl.P.CREAM), 3.0)
            bar = Rectangle(width=max(0.05, 7.0 * float(value) / top), height=0.42, fill_color=color or pl.P.SAND,
                            fill_opacity=0.9, stroke_width=0)
            num = pl.T(f"{float(value):g}{unit}", 18, pl.P.MUTED)
            rows.add(VGroup(label, bar, num))
        width = max((r[0].width for r in rows), default=1.0)
        for i, r in enumerate(rows):
            r[0].move_to([-width, -i * 0.65, 0], aligned_edge=RIGHT)
            r[1].move_to([0.2, -i * 0.65, 0], aligned_edge=LEFT)
            r[2].next_to(r[1], RIGHT, buff=0.15)
        self._fit_stage(rows, grow=1.2)
        return self._to_stage(Group(rows))

    # ---------------- geometry helpers ----------------
    @staticmethod
    def _colour(name, default):
        import pocket_lecture as pl

        if not name:
            return default
        text = str(name)
        if text.startswith("#"):
            return text
        return getattr(pl.P, text.upper(), default)

    def _mapper(self, elements: list[dict], box, margin: float = 0.55):
        """A function from sketch units to frame points, fitting every element's points into `box`."""
        import numpy as np

        pts = []

        def collect(e):
            for key in ("from", "to", "at"):
                if isinstance(e.get(key), (list, tuple)) and len(e[key]) == 2:
                    pts.append(e[key])
            for p in e.get("points") or []:
                pts.append(p)
            if e.get("type") == "rect":
                # Its rotated corners (a circle round it made a long thin beam count as tall as it is long).
                x, y = (float(v) for v in e["at"])
                hw, hh = float(e.get("w", 1)) / 2, float(e.get("h", 1)) / 2
                t = math.radians(float(e.get("angle", 0)))
                c, si = math.cos(t), math.sin(t)
                pts.extend([[x + dx * c - dy * si, y + dx * si + dy * c] for dx in (-hw, hw) for dy in (-hh, hh)])
            if e.get("type") == "circle":
                x, y = e["at"]
                r = float(e.get("r", 0.5))
                pts.extend([[x - r, y - r], [x + r, y + r]])
            for sub in e.get("items") or []:
                collect(sub)

        for e in elements:
            collect(e)
        arr = np.array(pts, dtype=float) if pts else np.array([[0, 0], [W, H]], dtype=float)
        lo, hi = arr.min(axis=0), arr.max(axis=0)
        span = np.maximum(hi - lo, 1e-3)
        cx, cy, w, h = box
        s = min((w - 2 * margin) / span[0], (h - 2 * margin) / span[1], 1.4)
        mid = (lo + hi) / 2

        def to(p):
            return np.array([cx + (float(p[0]) - mid[0]) * s, cy + (float(p[1]) - mid[1]) * s, 0.0])

        return to, s

    def _label(self, text, at, direction=None, color=None, size=LABEL_SIZE):
        import numpy as np
        import pocket_lecture as pl

        mob = pl.T(_label_text(text), size, color or pl.P.CREAM)
        mob.is_label = True            # _settle_labels may move it off a line or another label
        if direction is None:
            return mob.move_to(at)
        d = np.array(direction, dtype=float)
        n = np.linalg.norm(d) or 1.0
        d = d / n
        offset = (abs(d[0]) * mob.width / 2 + abs(d[1]) * mob.height / 2) + 0.12
        return mob.move_to(np.array(at) + d * offset)

    def _element(self, e: dict, to, s: float):
        """One primitive as a mobject (with its label)."""
        import numpy as np
        import pocket_lecture as pl
        from manim import (Arc, Arrow, Circle, DashedLine, DashedVMobject, Dot, DoubleArrow, Line, Polygon,
                           Rectangle, VGroup, VMobject, UP, DOWN, LEFT, RIGHT)

        kind = e.get("type")
        ink = self._colour(e.get("color"), pl.P.CREAM)
        width = float(e.get("width", 4))
        label = e.get("label")
        parts = []
        if kind == "group":
            return VGroup(*[self._element(sub, to, s) for sub in e.get("items") or []])
        if kind in ("line", "arrow"):
            a, b = to(e["from"]), to(e["to"])
            if kind == "arrow":
                if e.get("dashed"):
                    body = DashedLine(a, b, color=ink, stroke_width=4, dash_length=0.12)
                    body.add_tip(tip_length=0.2, tip_width=0.18)
                else:
                    body = Arrow(a, b, buff=0, color=ink, stroke_width=6, tip_length=0.24,
                                 max_tip_length_to_length_ratio=0.35, max_stroke_width_to_length_ratio=12)
                parts.append(body)
                if label:
                    parts.append(self._label(label, b, b - a, ink))
            else:
                body = DashedLine(a, b, color=ink, stroke_width=width, dash_length=0.12) if e.get("dashed") \
                    else Line(a, b, color=ink, stroke_width=width)
                parts.append(body)
                if label:
                    d = b - a
                    parts.append(self._label(label, (a + b) / 2, np.array([-d[1], d[0], 0]), ink))
        elif kind == "rect":
            fill = self._colour(e.get("fill"), None)
            rect = Rectangle(width=float(e.get("w", 1)) * s, height=float(e.get("h", 1)) * s,
                             stroke_color=self._colour(e.get("color"), fill or pl.P.CREAM),
                             stroke_width=0 if e.get("stroke") is False else 3,
                             fill_color=pl._tint_on_bg(fill, 0.55) if fill else pl.P.BG,
                             fill_opacity=1 if fill else 0)
            turn = math.radians(float(e.get("angle", 0)))
            rect.rotate(turn).move_to(to(e["at"]))
            parts.append(rect)
            if label:
                at = rect.get_center()
                tag = self._label(label, at, None, pl.P.HI if fill else ink)
                inner_w, inner_h = float(e.get("w", 1)) * s, float(e.get("h", 1)) * s
                if abs(math.sin(turn)) > 0.7:
                    inner_w, inner_h = inner_h, inner_w
                if e.get("_busy"):
                    # Forces start at its centre: the name goes above the block, clear of their arrows.
                    tag = self._label(label, rect.get_top(), UP, ink)
                elif tag.width > inner_w - 0.12 or tag.height > inner_h - 0.08:
                    # A thin bat or a small block: the name goes beside it, not across its edges.
                    tag = self._label(label, rect.get_right(), RIGHT, ink)
                parts.append(tag)
        elif kind == "circle":
            fill = self._colour(e.get("fill"), None)
            circle = Circle(radius=float(e.get("r", 0.5)) * s, color=self._colour(e.get("color"), fill or ink),
                            stroke_width=3, fill_color=pl._tint_on_bg(fill, 0.55) if fill else pl.P.BG,
                            fill_opacity=1 if fill else 0).move_to(to(e["at"]))
            parts.append(circle)
            if e.get("type") == "circle" and fill:
                parts.append(Dot(circle.get_center(), radius=0.05, color=ink))
            if label:
                tag = self._label(label, circle.get_center(), None, ink)
                if tag.width > circle.width * 0.8 or tag.height > circle.height * 0.6:
                    # Too small to hold its name: the name sits outside the rim, up and to the right.
                    d = np.array([1.0, 1.0, 0.0]) / math.sqrt(2)
                    tag = self._label(label, circle.get_center() + d * circle.width / 2, d, ink)
                parts.append(tag)
        elif kind == "polygon":
            pts = [to(p) for p in e["points"]]
            fill = self._colour(e.get("fill"), None)
            if e.get("open"):
                body = VMobject(color=self._colour(e.get("color"), ink), stroke_width=width).set_points_as_corners(pts)
            else:
                body = Polygon(*pts, color=self._colour(e.get("color"), fill or ink), stroke_width=3,
                               fill_color=pl._tint_on_bg(fill, 0.45) if fill else pl.P.BG, fill_opacity=1 if fill else 0)
            parts.append(body)
            if label:
                parts.append(self._label(label, np.mean(pts, axis=0), None, ink))
        elif kind == "spring":
            a, b = to(e["from"]), to(e["to"])
            d = b - a
            length = np.linalg.norm(d) or 1.0
            u, n = d / length, np.array([-d[1], d[0], 0]) / length
            coils = int(e.get("coils", 8))
            pts = [a, a + u * length * 0.1]
            for k in range(1, 2 * coils):
                pts.append(a + u * length * (0.1 + 0.8 * k / (2 * coils)) + n * (0.22 if k % 2 else -0.22))
            pts += [a + u * length * 0.9, b]
            parts.append(VMobject(color=ink, stroke_width=4).set_points_as_corners(pts))
            if label:
                parts.append(self._label(label, (a + b) / 2 + n * 0.3, n, ink))
        elif kind == "ground":
            a, b = to(e["from"]), to(e["to"])
            d = b - a
            length = np.linalg.norm(d) or 1.0
            u = d / length
            side = {"below": np.array([0, -1, 0]), "above": np.array([0, 1, 0]), "left": np.array([-1, 0, 0]),
                    "right": np.array([1, 0, 0])}.get(e.get("side", "below"), np.array([0, -1, 0]))
            parts.append(Line(a, b, color=self._colour(e.get("color"), pl.P.MUTED), stroke_width=4))
            count = max(3, int(length / 0.28))
            for k in range(count + 1):
                p = a + u * length * k / count
                parts.append(Line(p, p + side * 0.2 - u * 0.16, color=pl.P.MUTED, stroke_width=2))
        elif kind == "angle":
            v = to(e["at"])
            r1, r2 = to(e["from"]) - v, to(e["to"]) - v
            a1, a2 = math.atan2(r1[1], r1[0]), math.atan2(r2[1], r2[0])
            delta = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
            radius = float(e.get("r", 0.9)) * s * 0.75
            parts.append(Arc(radius=radius, start_angle=a1, angle=delta, arc_center=v,
                             color=self._colour(e.get("color"), pl.P.GOLD), stroke_width=3))
            if label:
                mid = a1 + delta / 2
                parts.append(self._label(label, v + np.array([math.cos(mid), math.sin(mid), 0]) * (radius + 0.28),
                                         None, self._colour(e.get("color"), pl.P.GOLD)))
        elif kind == "dim":
            a, b = to(e["from"]), to(e["to"])
            parts.append(DoubleArrow(a, b, buff=0, color=pl.P.MUTED, stroke_width=2.5, tip_length=0.15,
                                     max_tip_length_to_length_ratio=0.3))
            if label:
                d = b - a
                parts.append(self._label(label, (a + b) / 2, np.array([-d[1], d[0], 0]), pl.P.MUTED))
        elif kind == "dot":
            p = to(e["at"])
            parts.append(Dot(p, radius=0.08, color=ink))
            if label:
                parts.append(self._label(label, p, UP + RIGHT * 0.6, ink))
        elif kind == "text":
            parts.append(pl.T(_label_text(e.get("text", "")), float(e.get("size", LABEL_SIZE)), ink).move_to(to(e["at"])))
        elif kind == "curve":
            pts = [to(p) for p in e["points"]]
            body = VMobject(color=ink, stroke_width=width)
            body.set_points_as_corners(pts) if e.get("sharp") else body.set_points_smoothly(pts)
            if e.get("dashed"):
                body = DashedVMobject(body, num_dashes=max(12, int(len(pts) * 3)))
            parts.append(body)
            if label:
                last, before = pts[-1], pts[-2] if len(pts) > 1 else pts[-1] + LEFT
                mid = pts[len(pts) // 2]
                parts.append(self._label(label, mid, UP if e.get("sharp") else last - before, ink))
        return VGroup(*parts)

    # ---------------- sketches and presets ----------------
    def _build_sketch(self, key: str, elements: list[dict], box, show=None, movable=()):
        """Draw the elements into `box`; record them for reveal and focus. Returns what shows now. `movable`: parts
        a motion will move, drawn as objects of their own (_show_movable) rather than in the picture, which the
        program draws as one piece: moved out of it, a part left its copy behind."""
        from manim import VGroup

        to, s = self._mapper(elements, box)
        starts = {(round(float(e["from"][0]), 2), round(float(e["from"][1]), 2)) for e in elements
                  if e.get("type") == "arrow" and isinstance(e.get("from"), (list, tuple))}
        elements = [{**e, "_busy": True} if e.get("type") == "rect" and isinstance(e.get("at"), (list, tuple))
                    and (round(float(e["at"][0]), 2), round(float(e["at"][1]), 2)) in starts else e for e in elements]
        nodes, first, unnamed = {}, [], []
        ids = [str(e["id"]) for e in elements if e.get("id") is not None]
        shown = set(ids if show is None else _with_companions([str(x) for x in show], ids))
        detach = [i for i in ids if i in {str(m) for m in movable or ()} and i in shown]
        shown -= set(detach)
        built = []
        for e in elements:
            mob = self._element(e, to, s)
            built.append(mob)
            if e.get("id") is not None:
                nodes[str(e["id"])] = mob
                if str(e["id"]) not in shown:
                    continue
            else:
                unnamed.append(mob)
            first.append(mob)          # in the script's order: a part listed later is drawn over one before
        # Every part, shown now or later, is laid out together: a label clear of every line and label, and
        # the whole drawing, labels included, inside its box.
        _settle_labels(built, box)
        before = _bounds(built)
        _fit_into(built, box)
        after = _bounds(built)
        # Where a sketch point is on the frame, for motion: the mapping, then the fit's shrink and shift. The anchor
        # (the biggest part) follows the drawing if it later slides aside, so the mapping is measured again then.
        anchor = max(nodes.values(), key=lambda m: m.width + m.height) if nodes else None
        place = to
        if before and after:
            import numpy as np

            f = (after[2] - after[0]) / max(before[2] - before[0], 1e-6)
            c0 = np.array([(before[0] + before[2]) / 2, (before[1] + before[3]) / 2, 0.0])
            c1 = np.array([(after[0] + after[2]) / 2, (after[1] + after[3]) / 2, 0.0])
            place = lambda p, to=to, f=f, c0=c0, c1=c1: c1 + (to(p) - c0) * f  # noqa: E731
        self.diagrams[key] = {"nodes": nodes, "edges": [], "shown": shown, "focus": None, "draw": True,
                              "elements": elements, "place": place,
                              "anchor": (anchor, anchor.get_center().copy(), anchor.width) if anchor else None,
                              "detach": detach}
        self._next_keys.add(key)
        self._next_pending.extend(m for i, m in nodes.items() if i not in shown)
        return VGroup(*first)

    def _titled(self, title, box):
        """A heading at the top of a box, and the box left under it."""
        import pocket_lecture as pl
        from manim import BOLD

        if not title:
            return None, box
        cx, cy, w, h = box
        head = pl.fit(pl.T(title.upper() if pl.TH["upper"] else title, 22, pl.P.TITLE, font=pl.TH["serif"],
                           weight=BOLD), w - 0.3)
        head.move_to([cx, cy + h / 2 - head.height / 2 - 0.05, 0])
        return head, (cx, cy - 0.3, w, h - 0.6)

    def _problem_drawing(self, build):
        """While a problem is on the board, a new drawing replaces the problem's figure, not the problem."""
        from manim import AnimationGroup, FadeIn, FadeOut

        box = self._problem["fig_box"]
        before = set(self._stage_keys)
        body = build(box)
        leaving = []
        for key in before:
            if key in self.diagrams:
                self.diagrams[key]["gone"] = True      # the old figure leaves: its parts are not revealed later
                # and the parts of it revealed since leave with it.
                for node in self.diagrams[key]["nodes"].values():
                    if node in self.stage_extra:
                        self.stage_extra.remove(node)
                        leaving.append(node)
                    if node in self.stage_pending:
                        self.stage_pending.remove(node)
        self._stage_keys = set(self._next_keys)
        self._next_keys = set()
        old = self._problem.get("figure")
        self._problem["figure"] = self._stage_add(body)
        self.stage_pending = [*self.stage_pending, *self._next_pending]
        self._next_pending = []
        if old is not None and old in self.stage_extra:
            self.stage_extra.remove(old)
        going = [FadeOut(m) for m in [old, *leaving] if m is not None]
        if not going:
            return FadeIn(body)
        return AnimationGroup(AnimationGroup(*going), FadeIn(body), lag_ratio=1.0)

    def _in_problem(self) -> bool:
        return self.board_mode and self._solving() and self._problem.get("fig_box") is not None \
            and not self._beat_new

    def _show_movable(self, key: str, anim):
        """The drawing's animation with its movable parts drawn in beside it, as parts of their own."""
        from manim import AnimationGroup

        d = self.diagrams.get(key) or {}
        parts = self.reveal_nodes(key, d.get("detach") or []) if d.get("detach") else None
        if anim is None or parts is None:
            return anim or parts
        # After the picture is in (and the one before it gone): drawn with it, they sat over the leaving picture.
        return AnimationGroup(anim, parts, lag_ratio=1.0)

    def sketch(self, key: str, elements, show=None, title: str | None = None, movable=()):
        """A labelled diagram from primitives (see stem.PRIMITIVES), on the stage."""
        from manim import Group, VGroup

        if self._in_problem():
            return self._show_movable(key, self._problem_drawing(
                lambda box: self._build_sketch(key, list(elements), box, show, movable)))
        head, box = self._titled(title, self.STAGE)
        body = self._build_sketch(key, list(elements), box, show, movable)
        return self._show_movable(key, self._to_stage(Group(VGroup(*([head] if head else []), body))))

    def preset(self, key: str, kind: str, params: dict | None = None, show=None, title: str | None = None,
               movable=()):
        """A physics diagram by name (incline, pulley, piston, spring, pendulum, projectile, circuit, lever, lens)."""
        drawn = self.sketch(key, preset_elements(kind, params or {}), show, title, movable)
        if key in self.diagrams:
            self.diagrams[key]["preset"] = (kind, dict(params or {}))
        return drawn

    def motion(self, key: str, spec: dict | None = None):
        """Set a diagram going while it is explained (stem.motion_plan): the block slides down the wedge, the bob
        swings, the masses of a pulley move, the ball flies along its path; or any parts of a sketch moved,
        turned or pulsed. By default it goes there and back, so the diagram is left as it was labelled."""
        import numpy as np
        from manim import AnimationGroup, Dot, Indicate, Rotate, there_and_back, smooth
        import pocket_lecture as pl

        d = self.diagrams.get(key)
        if not d or d.get("gone") or not d.get("elements"):
            return None
        preset, params = d.get("preset") or (None, {})
        steps, back = motion_plan(preset, params, d["elements"], spec or {})
        # The drawing may have moved or shrunk since it was laid out (beside a card, into a problem's figure box).
        k, shift = 1.0, np.zeros(3)
        if d.get("anchor"):
            mob, centre, width = d["anchor"]
            k = mob.width / width if width else 1.0
            shift = mob.get_center() - centre * k

        def at(p):
            return d["place"](p) * k + shift

        def vec(v):
            return at([v[0], v[1]]) - at([0.0, 0.0])

        rate = there_and_back if back else smooth
        live = lambda ids: [d["nodes"][i] for i in ids if i in d["nodes"] and i in d["shown"]]  # noqa: E731
        anims = []
        for step in steps:
            if "move" in step:
                for node in live(step["move"]):
                    anims.append(_moving(node.animate(rate_func=rate).shift(vec(step["by"]))))
            elif "turn" in step:
                for node in live(step["turn"]):
                    anims.append(Rotate(node, angle=np.radians(step["deg"]), about_point=at(step["about"]),
                                        rate_func=rate))
            elif "stretch" in step:
                for node in live([step["stretch"]]):
                    fixed, end = np.array(step["fixed"], float), np.array(step["end"], float)
                    long = np.linalg.norm(end + np.array(step["by"], float) - fixed)
                    f = long / max(np.linalg.norm(end - fixed), 1e-6)
                    pin = at(fixed)
                    anims.append(_moving(node.animate(rate_func=rate).scale(f)
                                         .shift((pin - node.get_center()) * (1 - f))))
            elif "ball" in step:
                ball = Dot(at(step["ball"]), radius=max(0.08, float(np.linalg.norm(vec([step["r"], 0])))),
                           color=pl.P.GOLD).set_z_index(pl.Z_MARK + 12)
                self.add(self._stage_add(ball))
                anims.append(Rotate(ball, angle=np.radians(step["deg"]), about_point=at(step["about"]),
                                    rate_func=rate if back else smooth))
            elif "pulse" in step:
                anims += [Indicate(node, color=pl.P.GOLD) for node in live(step["pulse"])]
        return AnimationGroup(*anims) if anims else None

    # ---------------- graphs ----------------
    def _build_graph(self, key: str, spec: dict, box):
        import numpy as np
        import pocket_lecture as pl
        from manim import (Axes, DashedLine, Dot, Line, VGroup, UP, RIGHT, DOWN, LEFT)

        x0, x1 = (float(v) for v in (spec.get("x") or [-5, 5]))
        items = [dict(i) for i in spec.get("items") or []]
        fns = {}
        ys = []
        for i in items:
            if i.get("kind") in ("curve", "area", "tangent"):
                f = pl.safe_function(str(i["expr"]))
                fns[id(i)] = f
                a, b = (float(v) for v in (i.get("x") or [x0, x1]))
                vals = np.asarray(f(np.linspace(a, b, 200)), dtype=float)
                ys.extend(vals[np.isfinite(vals)].tolist())
            if i.get("kind") in ("point",):
                ys.append(float(i["at"][1]))
            if i.get("kind") == "data":
                ys.extend(float(p[1]) for p in i.get("points") or [])
            if i.get("kind") == "hline":
                ys.append(float(i.get("y", 0)))
        if spec.get("y"):
            y0, y1 = (float(v) for v in spec["y"])
        else:
            lo, hi = (min(ys), max(ys)) if ys else (-1.0, 1.0)
            lo, hi = min(lo, 0.0) if lo > 0 and lo < (hi - lo) * 0.5 else lo, hi
            pad = (hi - lo) * 0.12 or 1.0
            y0, y1 = lo - pad, hi + pad
        cx, cy, w, h = box
        xs = float(spec.get("x_step") or _nice_step(x1 - x0))
        ystep = float(spec.get("y_step") or _nice_step(y1 - y0))
        if not spec.get("y"):
            y0, y1 = math.floor(y0 / ystep) * ystep, math.ceil(y1 / ystep) * ystep
        def places(step, start):
            return 0 if float(step).is_integer() else 1 if round(step * 10, 6).is_integer() else 2
        axes = Axes(x_range=[x0, x1, xs], y_range=[y0, y1, ystep], x_length=w - 1.8, y_length=h - 1.0, tips=True,
                    axis_config={"color": pl.P.MUTED, "stroke_width": 2.5, "include_numbers": True,
                                 "font_size": 22, "tip_length": 0.18, "tip_width": 0.16},
                    x_axis_config={"decimal_number_config": {"num_decimal_places": places(xs, x0)}},
                    y_axis_config={"decimal_number_config": {"num_decimal_places": places(ystep, y0)}})
        axes.move_to([cx - 0.2, cy + 0.1, 0])
        for number in [*getattr(axes.x_axis, "numbers", []), *getattr(axes.y_axis, "numbers", [])]:
            number.set_color(pl.P.MUTED)
        xl = pl.T(_label_text(spec.get("x_label", "x")), 20, pl.P.MUTED)
        xl.next_to(axes.x_axis.get_end(), DOWN, buff=0.45).align_to(axes.x_axis.get_end(), RIGHT)
        yl = pl.T(_label_text(spec.get("y_label", "y")), 20, pl.P.MUTED).next_to(axes.y_axis.get_end(), RIGHT, buff=0.15)
        tones = [pl.P.SAND, pl.P.RIVER, pl.P.ROSE, pl.P.GREEN, pl.P.GOLD, pl.P.VIOLET]
        nodes = {}
        for k, i in enumerate(items):
            ink = self._colour(i.get("color"), tones[k % len(tones)])
            kind = i["kind"]
            parts = []
            if kind in ("curve", "area", "tangent"):
                f = fns[id(i)]
                a, b = (float(v) for v in (i.get("x") or [x0, x1]))

                def clip(t, f=f):
                    return float(np.clip(f(t), y0, y1))
                graph = axes.plot(clip, x_range=[a, b, (b - a) / 200], color=ink, stroke_width=5,
                                  use_smoothing=False)
                if kind == "curve":
                    parts.append(graph)
                    if i.get("label"):
                        # Beside the curve near its end, inside the axes.
                        t = a + (b - a) * 0.85
                        at = axes.c2p(t, clip(t))
                        tag = pl.T(_label_text(i["label"]), 20, ink).next_to(at, UP + LEFT * 0.2, buff=0.15)
                        if tag.get_right()[0] > cx + w / 2 - 0.1:
                            tag.shift(LEFT * (tag.get_right()[0] - (cx + w / 2 - 0.1)))
                        parts.append(tag)
                elif kind == "area":
                    area = axes.get_area(graph, x_range=[a, b], color=ink, opacity=0.35)
                    parts.append(area)
                    if i.get("label"):
                        parts.append(pl.T(_label_text(i["label"]), 20, pl.P.HI).move_to(area.get_center()))
                else:
                    at = float(i["at"])
                    slope = (f(at + 1e-4) - f(at - 1e-4)) / 2e-4
                    half = (x1 - x0) / 6
                    p = axes.c2p(at, f(at))
                    line = Line(axes.c2p(at - half, f(at) - slope * half), axes.c2p(at + half, f(at) + slope * half),
                                color=ink, stroke_width=3)
                    parts += [line, Dot(p, radius=0.07, color=ink)]
                    if i.get("label"):
                        parts.append(pl.T(_label_text(i["label"]), 18, ink).next_to(line.get_end(), UP, buff=0.1))
            elif kind == "point":
                x, y = (float(v) for v in i["at"])
                p = axes.c2p(x, y)
                if i.get("guides", True):
                    parts += [DashedLine(axes.c2p(x, max(y0, min(0, y1))), p, color=pl.P.MUTED, stroke_width=2),
                              DashedLine(axes.c2p(max(x0, min(0, x1)), y), p, color=pl.P.MUTED, stroke_width=2)]
                parts.append(Dot(p, radius=0.09, color=ink))
                if i.get("label"):
                    parts.append(pl.T(_label_text(i["label"]), 20, ink).next_to(p, UP + RIGHT * 0.5, buff=0.08))
            elif kind in ("vline", "hline"):
                if kind == "vline":
                    x = float(i.get("x", 0))
                    a, b = axes.c2p(x, y0), axes.c2p(x, y1)
                else:
                    y = float(i.get("y", 0))
                    a, b = axes.c2p(x0, y), axes.c2p(x1, y)
                parts.append(DashedLine(a, b, color=ink, stroke_width=3))
                if i.get("label"):
                    parts.append(pl.T(_label_text(i["label"]), 18, ink).next_to(b, UP if kind == "vline" else RIGHT * 0 + UP, buff=0.1))
            elif kind == "segment":
                a, b = axes.c2p(*[float(v) for v in i["from"]]), axes.c2p(*[float(v) for v in i["to"]])
                parts.append(Line(a, b, color=ink, stroke_width=4))
                if i.get("label"):
                    parts.append(pl.T(_label_text(i["label"]), 18, ink).next_to((a + b) / 2, UP, buff=0.12))
            elif kind == "data":
                pts = [axes.c2p(float(p[0]), float(p[1])) for p in i.get("points") or []]
                if i.get("line") and len(pts) > 1:
                    from manim import VMobject
                    parts.append(VMobject(color=ink, stroke_width=3).set_points_as_corners(pts))
                parts += [Dot(p, radius=0.08, color=ink) for p in pts]
                if i.get("label") and pts:
                    parts.append(pl.T(_label_text(i["label"]), 18, ink).next_to(pts[-1], UP, buff=0.12))
            elif kind == "label":
                parts.append(pl.T(_label_text(i.get("text", "")), 20, ink).move_to(axes.c2p(*[float(v) for v in i["at"]])))
            if kind not in ("label", "area"):
                for part in parts:
                    if type(part).__name__ == "Text":
                        part.is_label = True
            nodes[str(i.get("id") or f"_{k}")] = VGroup(*parts)
        _settle_labels([axes, xl, yl, *nodes.values()], box)
        _fit_into([axes, xl, yl, *nodes.values()], box)
        shown = set(nodes if spec.get("show") is None else [str(x) for x in spec["show"]])
        self.diagrams[key] = {"nodes": nodes, "edges": [], "shown": shown, "focus": None, "draw": True}
        self._next_keys.add(key)
        self._next_pending.extend(m for i, m in nodes.items() if i not in shown)
        return VGroup(axes, xl, yl, *[m for i, m in nodes.items() if i in shown])

    def graph(self, key: str, spec: dict, title: str | None = None):
        """Axes with items (curve, point, vline, hline, area, tangent, segment, data, label), on the stage."""
        from manim import Group, VGroup

        if self._in_problem():
            return self._problem_drawing(lambda box: self._build_graph(key, spec, box))
        head, box = self._titled(title, self.STAGE)
        body = self._build_graph(key, spec, box)
        return self._to_stage(Group(VGroup(*([head] if head else []), body)))

    # ---------------- worked solutions ----------------
    @staticmethod
    def _is_prose(line: str) -> bool:
        """A sentence rather than maths: words outside \\text{} and outside TeX's own commands and their
        arguments (\\rm total, \\mathrm{ext} are maths), or Hindi outside \\text{}."""
        bare = re.sub(r"\\(?:text|mathrm|textrm|mathbf|operatorname|rm|it|bf)\s*\{[^{}]*\}", "", line)
        bare = re.sub(r"\\(?:rm|it|bf)\s+\w+|[_^]\{[^{}]*\}|\\[a-zA-Z]+", "", bare)
        if re.search(r"[\u0900-\u097F]", bare):
            return True
        # Three words in a row is a sentence; a lone unit or name (total, max) is not.
        return bool(re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}\s+[A-Za-z]{2,}", bare))

    def _work_line(self, line: str, width: float):
        """One line of working: typeset maths (MathTex, drawn as text without LaTeX), or a sentence."""
        import pocket_lecture as pl
        from manim import MathTex

        text = str(line)
        size = 30
        if not self._is_prose(text):
            try:
                mob = MathTex(text, color=pl.P.CREAM, font_size=size + 4)
                return pl.fit(mob, width)
            except Exception:  # noqa: BLE001 -- TeX LaTeX cannot compile: the same line as text
                pass
        return pl.fit(pl.T(pl.wrap(pl.unicode_math(text) if re.search(r"[_^\\]", text) else text, 48), 22,
                           pl.P.CREAM, line_spacing=0.9), width)

    def _stage_aside(self, box):
        """Move what is on the stage (and its parts still to come) into `box`, making room beside it."""
        from manim import Group

        body = getattr(self, "stage_body", None)
        if body is None:
            return None
        # Sized by what shows, but moved as the group that was put on stage (with its card, invisible on the
        # board): moving a part of a shown group left the exporter a transform its preview could not play.
        whole = Group(body, *self.stage_extra, *self.stage_pending)
        cx, cy, w, h = box
        f = min(w / max(whole.width, 0.01), h / max(whole.height, 0.01), 1.0)
        return self._move_stage(f, whole.get_center(), box)

    def _new_column(self, key, area, title, anims):
        """Where a working's lines go: the top of `area`, under its title if it has one."""
        import pocket_lecture as pl
        from manim import BOLD, FadeIn, LEFT

        ax, ay, aw, ah = area
        w = {"x": ax - aw / 2 + 0.1, "top": ay + ah / 2 - 0.1, "bottom": ay - ah / 2 + 0.05, "width": aw - 0.2,
             "lines": []}
        w["y"] = w["top"]
        if title:
            head = pl.fit(pl.T(title.upper() if pl.TH["upper"] else title, 20, pl.P.SAND, weight=BOLD), w["width"])
            head.move_to([w["x"], w["y"], 0], aligned_edge=LEFT + [0, 1, 0])
            self._stage_add(head)
            anims.append(FadeIn(head))
            w["y"] = head.get_bottom()[1] - 0.2
        self.works[key] = w
        return w

    def work(self, key: str, lines=(), title: str | None = None, box: bool = False):
        """Lines of a worked solution, one group per beat, under the last; `box` rings the last line (the
        answer). The first call for a key places the working: in the problem's solution area, beside the
        figure on the stage (moved aside), or across the stage."""
        import pocket_lecture as pl
        from manim import (AnimationGroup, Create, FadeIn, FadeOut, Group, LaggedStart, SurroundingRectangle, Write,
                           LEFT, RIGHT)

        anims = []
        w = self.works.get(key)
        if w is None and self.works:
            # A second working on the same stage continues the first one's column, under it: moving the
            # stage aside again shrank the first working to a corner.
            w = next(iter(self.works.values()))
            if w["lines"]:
                w["y"] -= 0.2
            self.works[key] = w
        asides = [m for m in self.stage_extra if getattr(m, "is_aside", False)]
        if w is None and asides and self._problem is None and self.board_mode:
            # A card beside the drawing (a definition, an equation): the working takes its half of the board.
            area = asides[0].aside_box
            for m in asides:
                self.stage_extra.remove(m)
            anims.append(AnimationGroup(*[FadeOut(m) for m in asides]))
            w = self._new_column(key, area, title, anims)
        if w is None:
            if self._problem is not None:
                area = self._problem["work"]
            else:
                cx, cy, sw, sh = self.STAGE
                if getattr(self, "stage_body", None) is not None and self.board_mode:
                    left = (cx - sw / 4 - 0.1, cy, sw / 2 - 0.3, sh)
                    moved = self._stage_aside(left)
                    if moved:
                        anims.append(moved)
                    area = (cx + sw / 4 + 0.1, cy, sw / 2 - 0.3, sh)
                else:
                    if getattr(self, "stage_body", None) is None:
                        anims.append(self._to_stage(Group()))       # an empty stage the working belongs to
                    # A column of reading width in the middle of the board, not lines strung along its top edge.
                    area = (cx, cy, min(sw, 9.0), sh - 0.4)
            w = self._new_column(key, area, title, anims)
        new = []
        for line in lines or []:
            mob = self._work_line(line, w["width"])
            mob.move_to([w["x"], w["y"], 0], aligned_edge=LEFT + [0, 1, 0])
            w["y"] = mob.get_bottom()[1] - 0.24
            new.append(mob)
        # Past the bottom: the working scrolls up, and the oldest lines leave over the top.
        overflow = w["bottom"] - w["y"] - 0.24 if new and w["y"] < w["bottom"] else 0
        if overflow > 0:
            old = w["lines"]
            shift = [0, overflow + 0.1, 0]
            going = [m for m in old if m.get_top()[1] + overflow + 0.1 > w["top"]]
            staying = [m for m in old if m not in going]
            for m in new:
                m.shift(shift)
            w["y"] += overflow + 0.1
            rings = w.setdefault("rings", {})
            # An answer's ring goes where its line goes: left behind, it boxed the lines scrolling past it.
            going += [rings.pop(id(m)) for m in list(going) if id(m) in rings]
            staying_rings = [rings[id(m)] for m in staying if id(m) in rings]
            scroll = [FadeOut(m) for m in going] + [m.animate.shift(shift) for m in [*staying, *staying_rings]]
            for m in going:
                if m in self.stage_extra:
                    self.stage_extra.remove(m)
            w["lines"] = staying
            anims.append(AnimationGroup(*scroll))
        for m in new:
            self._stage_add(m)
            w["lines"].append(m)
        if new:
            anims.append(LaggedStart(*[Write(m) if not hasattr(m, "text") else FadeIn(m, shift=RIGHT * 0.15)
                                       for m in new], lag_ratio=0.6))
        if box and w["lines"]:
            last = w["lines"][-1]
            ring = SurroundingRectangle(last, color=pl.P.GOLD, buff=0.12, corner_radius=0.08, stroke_width=4)
            w.setdefault("rings", {})[id(last)] = ring
            if self._problem is not None:
                # The answer is boxed: what comes next is new teaching, not more of this problem.
                self._problem["answered"] = True
            w["y"] -= 0.14          # the ring's own room, so the next line starts below it
            self._stage_add(ring)
            anims.append(Create(ring))
        if not anims:
            return None
        return LaggedStart(*anims, lag_ratio=0.8)

    # ---------------- problems ----------------
    def problem(self, key: str, text: str, title: str | None = None, given=(), find: str | None = None,
                figure: dict | None = None):
        """A long question on the board: its statement across the top, its figure on the left (a sketch, a
        preset or a graph), and room on the right for the solution (work)."""
        import pocket_lecture as pl
        from manim import BOLD, Group, Line, VGroup, LEFT, RIGHT

        cx, cy, w, h = self.STAGE
        top = cy + h / 2
        from manim import RoundedRectangle

        tag = pl.T((title or "Problem").upper(), 20, pl.P.BG, weight=BOLD)
        chip = RoundedRectangle(corner_radius=0.08, width=tag.width + 0.3, height=tag.height + 0.18,
                                   fill_color=pl.P.SAND, fill_opacity=1, stroke_width=0)
        tag.move_to(chip)
        head = VGroup(chip, tag).move_to([cx - w / 2 + 0.1, top - 0.2, 0], aligned_edge=LEFT + [0, 1, 0])
        chars = int(80 * (w / 13.5))
        body = pl.fit(pl.T(pl.wrap(_label_text(text) if re.search(r"[_^\\]", str(text)) else str(text), chars), 25,
                           pl.P.CREAM, line_spacing=0.9), w - 0.3)
        body.next_to(head, RIGHT, buff=0.3, aligned_edge=[0, 1, 0])
        if body.get_right()[0] > cx + w / 2:
            body.next_to(head, [0, -1, 0], buff=0.15, aligned_edge=LEFT)
        statement = VGroup(head, body)
        rule_y = statement.get_bottom()[1] - 0.18
        track = Line([cx - w / 2 + 0.1, rule_y, 0], [cx + w / 2 - 0.1, rule_y, 0], color=pl.P.MUTED, stroke_width=2,
                     stroke_opacity=0.5)
        below_top = rule_y - 0.1
        below_h = below_top - (cy - h / 2)
        fig_box = (cx - w / 4 - 0.1, below_top - below_h / 2, w / 2 - 0.3, below_h)
        work_box = (cx + w / 4 + 0.1, below_top - below_h / 2, w / 2 - 0.3, below_h)
        parts = [statement, track]
        going = self._stage_leaving()
        drawing = None
        if figure:
            fkey = str(figure.get("id") or f"{key}_figure")
            if figure.get("op") == "graph":
                drawing = self._build_graph(fkey, figure, fig_box)
            else:
                drawing = self._build_sketch(fkey, op_elements(figure), fig_box, figure.get("show"),
                                             figure.get("movable") or ())
                if figure.get("op") in PRESETS:
                    self.diagrams[fkey]["preset"] = (figure["op"], {k: v for k, v in figure.items()
                                                                    if k not in ("op", "id", "show")})
        else:
            work_box = (cx, below_top - below_h / 2, w, below_h)
        lines = []
        if given:
            lines.append("Given: " + ",  ".join(_label_text(g) for g in given))
        if find:
            lines.append("Find: " + _label_text(find))
        wx, wy, ww, wh = work_box
        y = wy + wh / 2 - 0.1
        for line in lines:
            mob = pl.fit(pl.T(pl.wrap(line, 44), 22, pl.P.MUTED, line_spacing=0.9), ww - 0.2)
            mob.move_to([wx - ww / 2 + 0.1, y, 0], aligned_edge=LEFT + [0, 1, 0])
            y = mob.get_bottom()[1] - 0.12
            parts.append(mob)
        solution_h = (y - 0.12) - (wy - wh / 2)
        self._problem = {"key": key, "work": (wx, (y - 0.12) - solution_h / 2, ww, solution_h),
                         "fig_box": fig_box if figure else None, "figure": drawing}
        group = Group(VGroup(*parts))
        new = Group(self._stage_card(), group)
        new.set_z_index(pl.Z_MARK + 10)
        self.stage_items, self.stage_body = new, group
        self.stage_pending, self._next_pending = self._next_pending, []
        self._stage_keys, self._next_keys = set(self._next_keys), set()
        self._question = {"track": track, "answer": None}
        from manim import AnimationGroup, FadeIn

        show = FadeIn(new)
        if drawing is not None:
            self._stage_add(drawing)
            show = AnimationGroup(show, FadeIn(drawing))
            if figure and figure.get("op") != "graph":
                show = self._show_movable(str(figure.get("id") or f"{key}_figure"), show)
        return AnimationGroup(AnimationGroup(*going, run_time=0.5), show, lag_ratio=1.0) if going else show

