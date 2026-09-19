"""Interpret a .panim DSL program into renderable frames -- without Manim.

This is the prototype for shipping the *program* instead of sampled geometry.
It deliberately imports nothing from Manim: the whole question is whether an
independent runtime can reproduce Manim's output, and calling Manim to find out
would be circular. Everything here -- surface tessellation, the camera model,
the rate function -- is reimplemented from Manim's documented behaviour.

Output is a DecodedIR, so the existing reference renderer and fidelity harness
work unchanged.

Usage:
    python -m dsl.interpret dsl/surface_orbit.panim
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exporter.decode import DecodedInstance, DecodedIR
from exporter.ir import REC_SNAPSHOT, SHADE_IN_3D

# Scene defaults, matching Manim's ThreeDCamera. In a real format these live in
# the header; here they are implicit so the program stays minimal.
FOCAL_DISTANCE = 20.0
ZOOM = 1.0
GAMMA = 0.0
FRAME_CENTRE = np.zeros(3)
LIGHT_SOURCE = np.array([-7.0, -9.0, 10.0])

SAFE_FUNCS = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan, "exp": np.exp,
    "sqrt": np.sqrt, "abs": np.abs, "pi": np.pi, "log": np.log,
}


def smooth(t: float, inflection: float = 10.0) -> float:
    """Manim's default rate function."""
    def sigmoid(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-x))

    error = sigmoid(-inflection / 2)
    return min(max((sigmoid(inflection * (t - 0.5)) - error) / (1 - 2 * error), 0.0), 1.0)


def rotation_z(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rotation_x(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def camera_matrix(phi: float, theta: float, gamma: float = GAMMA) -> np.ndarray:
    """Manim composes rot_z(gamma) @ rot_x(-phi) @ rot_z(-theta - 90deg)."""
    result = np.identity(3)
    for matrix in (
        rotation_z(-theta - math.pi / 2),
        rotation_x(-phi),
        rotation_z(gamma),
    ):
        result = matrix @ result
    return result


def hex_rgb(text: str) -> tuple[int, int, int]:
    text = text.lstrip("#")
    return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))


def tessellate(expr: str, u_range, v_range, res) -> list[np.ndarray]:
    """Build surface faces exactly as Manim's Surface does.

    Manim lays each face out as a flat quad in UV space via set_points_as_corners
    -- which puts cubic control points at 0, 1/3, 2/3, 1 along each straight
    edge -- and then maps every control point through the surface function.
    Four edges of four points gives the 16 points per face Manim produces.
    """
    u_res, v_res = res
    us = np.linspace(u_range[0], u_range[1], u_res + 1)
    vs = np.linspace(v_range[0], v_range[1], v_res + 1)

    def height(u, v):
        return eval(expr, {"__builtins__": {}}, {**SAFE_FUNCS, "u": u, "v": v})

    faces = []
    for i in range(u_res):
        for j in range(v_res):
            u1, u2 = us[i], us[i + 1]
            v1, v2 = vs[j], vs[j + 1]
            corners = [(u1, v1), (u2, v1), (u2, v2), (u1, v2), (u1, v1)]

            points = []
            for (ua, va), (ub, vb) in zip(corners, corners[1:]):
                for t in (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0):
                    u = ua + (ub - ua) * t
                    v = va + (vb - va) * t
                    points.append([u, v, height(u, v)])
            faces.append(np.array(points, dtype=np.float64))
    return faces


def parse(text: str) -> dict:
    """Parse the line-based DSL into a scene description."""
    scene = {
        "fps": 30,
        "mode": "3d",
        "surfaces": [],
        "shapes": {},
        "assets": {},
        "timeline": [],
        "phi": 0.0,
        "theta": 0.0,
    }
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        verb, *rest = line.split()
        args = {}
        positional = []
        for token in rest:
            if "=" in token:
                key, value = token.split("=", 1)
                args[key] = value
            else:
                positional.append(token)

        if verb == "scene":
            scene["fps"] = int(args.get("fps", 30))
            if positional:
                scene["mode"] = positional[0]
        elif verb in ("circle", "square"):
            name = positional[0]
            scene["shapes"][name] = {
                "kind": verb,
                "size": float(args.get("r") or args.get("s")),
                "stroke": hex_rgb(args["stroke"]),
                "width": float(args.get("w", 4)),
            }
        elif verb == "text":
            scene["assets"][positional[0]] = args["asset"]
        elif verb == "create":
            scene["timeline"].append(("create", positional[0], float(args["t"])))
        elif verb == "transform":
            scene["timeline"].append(
                ("transform", positional[0], positional[1], float(args["t"]))
            )
        elif verb == "surface":
            scene["surfaces"].append(
                {
                    "name": positional[0] if positional else "S",
                    "fn": args["fn"],
                    "u": [float(x) for x in args["u"].split(",")],
                    "v": [float(x) for x in args["v"].split(",")],
                    "res": [int(x) for x in args["res"].split(",")],
                    "colors": [hex_rgb(c) for c in args["fill"].split(",")],
                    "alpha": float(args.get("alpha", 1.0)),
                    "stroke": float(args.get("stroke", 0.0)),
                }
            )
        elif verb == "camera":
            scene["phi"] = math.radians(float(args.get("phi", 0)))
            scene["theta"] = math.radians(float(args.get("theta", 0)))
        elif verb == "move":
            scene["timeline"].append(
                ("move", math.radians(float(args["phi"])), math.radians(float(args["theta"])),
                 float(args["t"]))
            )
        elif verb == "spin":
            scene["timeline"].append(("spin", float(args["rate"]), float(args["t"])))
        elif verb == "wait":
            scene["timeline"].append(("wait", float(args["t"])))
    return scene


def geometry_for(spec: dict) -> np.ndarray:
    from dsl.verbs import circle, square

    return circle(spec["size"]) if spec["kind"] == "circle" else square(spec["size"])


def build_2d(scene: dict) -> DecodedIR:
    """Expand a 2D shape scene into per-frame geometry.

    Note what is *not* happening here: nothing is stored per frame in the
    shipped artefact. The program is 120 bytes; this expansion is what a device
    runtime does live. The DecodedIR is only a vehicle for the reference
    renderer so the existing comparison harness can be reused.
    """
    from dsl.verbs import align, pointwise_become_partial

    from exporter.decode import load as load_ir

    fps = scene["fps"]
    shapes: list[np.ndarray] = []
    records: list[tuple[int, list[DecodedInstance]]] = []
    live: dict[str, dict] = {}

    # Tier-2 assets: glyph geometry the program references rather than
    # describes. Loaded once and drawn on every frame, which is also why a
    # library-wide asset cache amortises text toward zero.
    static: list[DecodedInstance] = []
    for asset in scene["assets"].values():
        from dsl.library import load_text_asset

        path = Path("dsl/generated/assets") / f"{asset}.panm"
        glyphs, asset_instances = load_text_asset(path)
        offset = len(shapes)
        shapes.extend(glyphs)
        for inst in asset_instances:
            static.append(
                DecodedInstance(
                    slot=1000 + len(static),
                    atlas_id=inst.atlas_id + offset,
                    transform=inst.transform,
                    fill=inst.fill,
                    stroke=inst.stroke,
                    stroke_width=inst.stroke_width,
                )
            )

    def emit(points: np.ndarray, stroke, width):
        shapes.append(points)
        records.append(
            (
                REC_SNAPSHOT,
                static
                + [
                    DecodedInstance(
                        slot=0,
                        atlas_id=len(shapes) - 1,
                        transform=np.hstack([np.identity(3), np.zeros((3, 1))]),
                        fill=(0, 0, 0, 0),
                        stroke=(*stroke, 255),
                        stroke_width=width,
                    )
                ],
            )
        )

    for step in scene["timeline"]:
        if step[0] == "create":
            _, name, duration = step
            spec = scene["shapes"][name]
            full = geometry_for(spec)
            live[name] = {"points": full, "stroke": spec["stroke"], "width": spec["width"]}
            for frame in range(int(duration * fps)):
                alpha = smooth((frame + 1) / (duration * fps))
                emit(pointwise_become_partial(full, 0.0, alpha), spec["stroke"], spec["width"])

        elif step[0] == "transform":
            _, source, target, duration = step
            target_spec = scene["shapes"][target]
            start, end = align(live[source]["points"], geometry_for(target_spec))
            c0 = np.array(live[source]["stroke"], dtype=float)
            c1 = np.array(target_spec["stroke"], dtype=float)
            for frame in range(int(duration * fps)):
                alpha = smooth((frame + 1) / (duration * fps))
                colour = tuple(int(round(x)) for x in c0 + (c1 - c0) * alpha)
                emit(start + (end - start) * alpha, colour, live[source]["width"])
            live[source] = {
                "points": end,
                "stroke": target_spec["stroke"],
                "width": live[source]["width"],
            }

        elif step[0] == "wait":
            current = next(iter(live.values()))
            for _ in range(int(step[1] * fps)):
                emit(current["points"], current["stroke"], current["width"])

    return DecodedIR(fps=fps, shapes=shapes, records=records, cameras=None)


def build(scene: dict) -> DecodedIR:
    if scene["mode"] == "2d":
        return build_2d(scene)

    shapes: list[np.ndarray] = []
    template: list[DecodedInstance] = []

    for surface in scene["surfaces"]:
        faces = tessellate(surface["fn"], surface["u"], surface["v"], surface["res"])
        u_res, v_res = surface["res"]
        alpha = int(surface["alpha"] * 255)
        for index, face in enumerate(faces):
            i, j = divmod(index, v_res)
            colour = surface["colors"][(i + j) % len(surface["colors"])]
            centre = face.mean(axis=0)
            shapes.append(face - centre)

            normal = plane_normal(face)
            transform = np.hstack([np.identity(3), centre.reshape(3, 1)])
            template.append(
                DecodedInstance(
                    slot=len(template),
                    atlas_id=len(shapes) - 1,
                    transform=transform,
                    fill=(*colour, alpha),
                    stroke=(*colour, alpha),
                    stroke_width=surface["stroke"],
                    flags=SHADE_IN_3D,
                    normal=normal,
                )
            )

    cameras = camera_track(scene)
    records = [(REC_SNAPSHOT, list(template)) for _ in cameras]
    return DecodedIR(fps=scene["fps"], shapes=shapes, records=records, cameras=cameras)


def plane_normal(points: np.ndarray) -> np.ndarray:
    centred = points - points.mean(axis=0)
    _, _, vh = np.linalg.svd(centred, full_matrices=False)
    normal = vh[2]
    return -normal if normal[2] < 0 else normal


def camera_track(scene: dict) -> list[np.ndarray]:
    """Expand the timeline into one camera record per frame."""
    fps = scene["fps"]
    phi, theta = scene["phi"], scene["theta"]
    track: list[np.ndarray] = []

    def emit():
        track.append(
            np.concatenate(
                [
                    FRAME_CENTRE,
                    [FOCAL_DISTANCE, ZOOM],
                    camera_matrix(phi, theta).reshape(9),
                    LIGHT_SOURCE,
                ]
            )
        )

    for step in scene["timeline"]:
        if step[0] == "move":
            _, target_phi, target_theta, duration = step
            start_phi, start_theta = phi, theta
            for frame in range(int(duration * fps)):
                alpha = smooth((frame + 1) / (duration * fps))
                phi = start_phi + (target_phi - start_phi) * alpha
                theta = start_theta + (target_theta - start_theta) * alpha
                emit()
        elif step[0] == "spin":
            _, rate, duration = step
            for _ in range(int(duration * fps)):
                theta += rate / fps
                emit()
        elif step[0] == "wait":
            for _ in range(int(step[1] * fps)):
                emit()
    return track


def load_program(path: str) -> DecodedIR:
    return build(parse(Path(path).read_text()))


if __name__ == "__main__":
    ir = load_program(sys.argv[1])
    raw = Path(sys.argv[1]).stat().st_size
    print(f"program bytes      {raw}")
    print(f"atlas shapes       {len(ir.shapes)}")
    print(f"frames             {len(ir.records)}")
