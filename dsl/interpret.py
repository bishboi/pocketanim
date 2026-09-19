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


def linear(t: float) -> float:
    """Manim's linear rate function -- the default for Write and Wait."""
    return t


RATE_FUNCS = {"smooth": smooth, "linear": linear}


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
        elif verb in ("circle", "square", "rect"):
            name = positional[0]
            scene["shapes"][name] = {
                "kind": verb,
                "size": float(args.get("r") or args.get("s") or 0),
                "extent": [float(x) for x in args["wh"].split(",")] if "wh" in args else None,
                "stroke": hex_rgb(args["stroke"]),
                "width": float(args.get("w", 4)),
                "at": [float(x) for x in args.get("at", "0,0").split(",")],
            }
        elif verb in ("text", "geom"):
            scene["assets"][positional[0]] = (verb, args["asset"])
        elif verb == "create":
            scene["timeline"].append(
                ("create", positional[0], float(args["t"]), args.get("rate", "smooth"))
            )
        elif verb == "transform":
            scene["timeline"].append(
                ("transform", positional[0], positional[1], float(args["t"]),
                 args.get("rate", "smooth"))
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
        elif verb == "show":
            scene["timeline"].append(("show", positional[0]))
        elif verb in ("fade", "fadeout", "write"):
            scene["timeline"].append((verb, positional[0], float(args["t"])))
        elif verb == "xform":
            by_xy = args.get("by_xy", "0,0").split(",")
            scene["timeline"].append(
                ("xform", positional[0], float(args.get("by", 1.0)),
                 [float(by_xy[0]), float(by_xy[1])], float(args["t"]))
            )
        elif verb == "wait":
            scene["timeline"].append(("wait", float(args["t"])))
    return scene


def geometry_for(spec: dict) -> np.ndarray:
    from dsl.verbs import circle, rectangle, square

    if spec["kind"] == "circle":
        points = circle(spec["size"])
    elif spec["kind"] == "rect":
        points = rectangle(*spec["extent"])
    else:
        points = square(spec["size"])

    at = spec.get("at") or [0.0, 0.0]
    return points + np.array([at[0], at[1], 0.0])


def name_is_asset(objects: dict, name: str) -> bool:
    return objects.get(name, {}).get("kind") == "asset"


def compose(outer: np.ndarray, inner: np.ndarray) -> np.ndarray:
    """Apply an object-level transform on top of an instance transform."""
    linear = outer[:, :3] @ inner[:, :3]
    translation = outer[:, :3] @ inner[:, 3] + outer[:, 3]
    return np.hstack([linear, translation.reshape(3, 1)])


def build_2d(scene: dict) -> DecodedIR:
    """Expand a 2D scene into per-frame geometry.

    Note what is *not* shipped: nothing here is stored per frame in the
    artefact. The program is ~120 bytes and the assets are cached; this
    expansion is what a device runtime does live. The DecodedIR is only a
    vehicle so the existing reference renderer and harness can be reused.
    """
    from dsl.library import load_standalone_asset, load_text_asset
    from dsl.verbs import align, pointwise_become_partial

    fps = scene["fps"]
    shapes: list[np.ndarray] = []
    records: list[tuple[int, list[DecodedInstance]]] = []
    objects: dict[str, dict] = {}

    identity = np.hstack([np.identity(3), np.zeros((3, 1))])

    for name, (kind, asset_id) in scene["assets"].items():
        path = Path("dsl/generated/assets") / f"{asset_id}.panm"
        geometry, instances = (
            load_text_asset(path) if kind == "text" else load_standalone_asset(path)
        )
        offset = len(shapes)
        shapes.extend(geometry)

        bounds = [
            geometry[inst.atlas_id] @ inst.transform[:, :3].T + inst.transform[:, 3]
            for inst in instances
        ]
        stacked = np.vstack(bounds) if bounds else np.zeros((1, 3))
        centre = (stacked.min(axis=0) + stacked.max(axis=0)) / 2.0

        objects[name] = {
            "kind": "asset",
            "visible": False,
            "centre": centre,
            "xform": identity.copy(),
            "instances": [
                (inst.atlas_id + offset, inst.transform, inst.fill, inst.stroke,
                 inst.stroke_width)
                for inst in instances
            ],
        }

    def emit():
        frame: list[DecodedInstance] = []
        for obj in objects.values():
            if not obj.get("visible", True):
                continue
            if obj["kind"] == "asset":
                for atlas_id, transform, fill, stroke, width in obj["instances"]:
                    frame.append(
                        DecodedInstance(
                            slot=len(frame),
                            atlas_id=atlas_id,
                            transform=compose(obj["xform"], transform),
                            fill=fill,
                            stroke=stroke,
                            stroke_width=width,
                        )
                    )
            else:
                shapes.append(obj["points"])
                frame.append(
                    DecodedInstance(
                        slot=len(frame),
                        atlas_id=len(shapes) - 1,
                        transform=identity.copy(),
                        fill=(0, 0, 0, 0),
                        stroke=(*obj["stroke"], int(255 * obj.get("alpha", 1.0))),
                        stroke_width=obj["width"],
                    )
                )
        records.append((REC_SNAPSHOT, frame))

    timeline_steps = list(scene["timeline"])
    for step in timeline_steps:
        if step[0] == "show":
            objects[step[1]]["visible"] = True
            continue

        if step[0] == "create" and name_is_asset(objects, step[1]):
            # Manim's Create on a group lags its children, which is the same
            # reveal Write performs on glyphs.
            objects[step[1]]["visible"] = True
            timeline_steps.append(("write", step[1], step[2]))
            continue

        if step[0] == "create":
            _, name, duration, rate_name = step
            rate = RATE_FUNCS[rate_name]
            spec = scene["shapes"][name]
            full = geometry_for(spec)
            objects[name] = {
                "kind": "shape", "visible": True, "points": full, "alpha": 1.0,
                "stroke": spec["stroke"], "width": spec["width"],
            }
            for frame_index in range(int(duration * fps)):
                alpha = rate((frame_index + 1) / (duration * fps))
                objects[name]["points"] = pointwise_become_partial(full, 0.0, alpha)
                emit()
            objects[name]["points"] = full

        elif step[0] == "transform":
            _, source, target, duration, rate_name = step
            rate = RATE_FUNCS[rate_name]
            target_spec = scene["shapes"][target]
            start_pts, end_pts = align(objects[source]["points"], geometry_for(target_spec))
            c0 = np.array(objects[source]["stroke"], dtype=float)
            c1 = np.array(target_spec["stroke"], dtype=float)
            for frame_index in range(int(duration * fps)):
                alpha = rate((frame_index + 1) / (duration * fps))
                objects[source]["points"] = start_pts + (end_pts - start_pts) * alpha
                objects[source]["stroke"] = tuple(
                    int(round(x)) for x in c0 + (c1 - c0) * alpha
                )
                emit()

        elif step[0] == "xform":
            _, name, factor, offset_xy, duration = step
            obj = objects[name]
            base = obj["xform"].copy()
            centre = obj.get("centre", np.zeros(3))
            shift = np.array([offset_xy[0], offset_xy[1], 0.0])
            for frame_index in range(int(duration * fps)):
                alpha = smooth((frame_index + 1) / (duration * fps))
                scale = 1.0 + (factor - 1.0) * alpha
                # Manim scales about the object's centre, then translates.
                step_linear = np.identity(3) * scale
                step_translation = (1 - scale) * centre + shift * alpha
                step_matrix = np.hstack([step_linear, step_translation.reshape(3, 1)])
                obj["xform"] = compose(step_matrix, base)
                emit()

        elif step[0] == "write" and step[1] not in objects:
            # write targets an asset; a shape reaching here means the exporter
            # emitted a verb for something it never declared as an asset.
            raise KeyError(f"write target {step[1]!r} was never declared")

        elif step[0] == "write":
            # Manim's Write lags each submobject; lag_ratio defaults to
            # min(4/n, 0.2). Each glyph is drawn progressively over its slot.
            _, name, duration = step
            obj = objects[name]
            base = [tuple(inst) for inst in obj["instances"]]
            count = max(len(base), 1)
            lag = min(4.0 / count, 0.2)
            span = 1.0 / (1.0 + lag * (count - 1))
            total = int(duration * fps)
            for frame_index in range(total):
                alpha = (frame_index + 1) / total
                revealed = []
                for i, (aid, transform, fill, stroke, width) in enumerate(base):
                    start = i * lag * span
                    local = min(max((alpha - start) / span, 0.0), 1.0)
                    if local <= 0:
                        continue
                    if local >= 1:
                        revealed.append((aid, transform, fill, stroke, width))
                        continue
                    partial = pointwise_become_partial(shapes[aid], 0.0, smooth(local))
                    shapes.append(partial)
                    revealed.append((len(shapes) - 1, transform, fill, stroke, width))
                obj["instances"] = revealed
                emit()
            obj["instances"] = base

        elif step[0] == "fadeout":
            _, name, duration = step
            if name in objects:
                objects[name]["visible"] = True
            obj = objects[name]
            base = [tuple(i) for i in obj["instances"]] if obj["kind"] == "asset" else None
            for frame_index in range(int(duration * fps)):
                alpha = 1.0 - smooth((frame_index + 1) / (duration * fps))
                if base is None:
                    obj["alpha"] = alpha
                else:
                    obj["instances"] = [
                        (aid, transform,
                         (*fill[:3], int(fill[3] * alpha)),
                         (*stroke[:3], int(stroke[3] * alpha)),
                         width)
                        for aid, transform, fill, stroke, width in base
                    ]
                emit()
            if base is None:
                objects.pop(name, None)
            else:
                obj["instances"] = []

        elif step[0] == "fade":
            _, name, duration = step
            if name in objects:
                objects[name]["visible"] = True
            # A declared shape only enters the scene when something animates
            # it in; fade is one of those entry points, not just create.
            if name not in objects:
                spec = scene["shapes"][name]
                objects[name] = {
                    "kind": "shape", "visible": True, "points": geometry_for(spec),
                    "alpha": 0.0,
                    "stroke": spec["stroke"], "width": spec["width"],
                }
            obj = objects[name]
            base = [tuple(i) for i in obj["instances"]] if obj["kind"] == "asset" else None
            for frame_index in range(int(duration * fps)):
                alpha = smooth((frame_index + 1) / (duration * fps))
                if base is None:
                    obj["alpha"] = alpha
                else:
                    obj["instances"] = [
                        (aid, transform,
                         (*fill[:3], int(fill[3] * alpha)),
                         (*stroke[:3], int(stroke[3] * alpha)),
                         width)
                        for aid, transform, fill, stroke, width in base
                    ]
                emit()
            if base is None:
                obj["alpha"] = 1.0
            else:
                obj["instances"] = base

        elif step[0] == "wait":
            for _ in range(int(step[1] * fps)):
                emit()

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
        elif step[0] == "write" and step[1] not in objects:
            # write targets an asset; a shape reaching here means the exporter
            # emitted a verb for something it never declared as an asset.
            raise KeyError(f"write target {step[1]!r} was never declared")

        elif step[0] == "write":
            # Manim's Write lags each submobject; lag_ratio defaults to
            # min(4/n, 0.2). Each glyph is drawn progressively over its slot.
            _, name, duration = step
            obj = objects[name]
            base = [tuple(inst) for inst in obj["instances"]]
            count = max(len(base), 1)
            lag = min(4.0 / count, 0.2)
            span = 1.0 / (1.0 + lag * (count - 1))
            total = int(duration * fps)
            for frame_index in range(total):
                alpha = (frame_index + 1) / total
                revealed = []
                for i, (aid, transform, fill, stroke, width) in enumerate(base):
                    start = i * lag * span
                    local = min(max((alpha - start) / span, 0.0), 1.0)
                    if local <= 0:
                        continue
                    if local >= 1:
                        revealed.append((aid, transform, fill, stroke, width))
                        continue
                    partial = pointwise_become_partial(shapes[aid], 0.0, smooth(local))
                    shapes.append(partial)
                    revealed.append((len(shapes) - 1, transform, fill, stroke, width))
                obj["instances"] = revealed
                emit()
            obj["instances"] = base

        elif step[0] == "fadeout":
            _, name, duration = step
            if name in objects:
                objects[name]["visible"] = True
            obj = objects[name]
            base = [tuple(i) for i in obj["instances"]] if obj["kind"] == "asset" else None
            for frame_index in range(int(duration * fps)):
                alpha = 1.0 - smooth((frame_index + 1) / (duration * fps))
                if base is None:
                    obj["alpha"] = alpha
                else:
                    obj["instances"] = [
                        (aid, transform,
                         (*fill[:3], int(fill[3] * alpha)),
                         (*stroke[:3], int(stroke[3] * alpha)),
                         width)
                        for aid, transform, fill, stroke, width in base
                    ]
                emit()
            if base is None:
                objects.pop(name, None)
            else:
                obj["instances"] = []

        elif step[0] == "fade":
            _, name, duration = step
            if name in objects:
                objects[name]["visible"] = True
            # A declared shape only enters the scene when something animates
            # it in; fade is one of those entry points, not just create.
            if name not in objects:
                spec = scene["shapes"][name]
                objects[name] = {
                    "kind": "shape", "visible": True, "points": geometry_for(spec),
                    "alpha": 0.0,
                    "stroke": spec["stroke"], "width": spec["width"],
                }
            obj = objects[name]
            base = [tuple(i) for i in obj["instances"]] if obj["kind"] == "asset" else None
            for frame_index in range(int(duration * fps)):
                alpha = smooth((frame_index + 1) / (duration * fps))
                if base is None:
                    obj["alpha"] = alpha
                else:
                    obj["instances"] = [
                        (aid, transform,
                         (*fill[:3], int(fill[3] * alpha)),
                         (*stroke[:3], int(stroke[3] * alpha)),
                         width)
                        for aid, transform, fill, stroke, width in base
                    ]
                emit()
            if base is None:
                obj["alpha"] = 1.0
            else:
                obj["instances"] = base

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
