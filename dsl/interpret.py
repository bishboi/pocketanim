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
from dataclasses import replace
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

# Yielded once by every verb when its set-up is done and before its first
# frame. Manim begins every animation in a play() before it interpolates any,
# so two verbs on one object -- Create and Indicate on a river -- each capture
# the object as it was before either moved. A `par` begins all its members
# through this; a sequence begins each member when it is reached.
BEGUN = object()


def begin(generator):
    """Run a verb's set-up. Returns the generator, positioned at frame 0."""
    try:
        first = next(generator)
    except StopIteration:
        return iter(())
    if first is not BEGUN:
        raise RuntimeError("verb yielded a frame before beginning")
    return generator


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


def there_and_back(t: float) -> float:
    return smooth(2 * t if t < 0.5 else 2 * (1 - t))


def rush_into(t: float) -> float:
    return 2 * smooth(t / 2)


def rush_from(t: float) -> float:
    return 2 * smooth(t / 2 + 0.5) - 1


def slow_into(t: float) -> float:
    return math.sqrt(max(0.0, 1 - (1 - t) ** 2))


def double_smooth(t: float) -> float:
    return 0.5 * smooth(2 * t) if t < 0.5 else 0.5 * (1 + smooth(2 * t - 1))


RATE_FUNCS = {
    "smooth": smooth,
    "linear": linear,
    "there_and_back": there_and_back,
    "rush_into": rush_into,
    "rush_from": rush_from,
    "slow_into": slow_into,
    "double_smooth": double_smooth,
}


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
        # Draw order. Manim sorts what it draws by z_index, stably, so a
        # caption at z=60 sits over a map added after it. Absent means 0,
        # which keeps every program written before `z=` existed unchanged.
        "z": {},
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
            if "z" in args:
                scene["z"][name] = float(args["z"])
        elif verb in ("text", "geom"):
            scene["assets"][positional[0]] = (verb, args["asset"])
            if "z" in args:
                scene["z"][positional[0]] = float(args["z"])
        elif verb in ("create", "uncreate"):
            # `lag` is Create's lag_ratio across a group's children. Only an
            # asset has children; a primitive is one path and ignores it.
            scene["timeline"].append(
                (verb, positional[0], float(args["t"]), args.get("rate", "smooth"),
                 float(args["lag"]) if "lag" in args else None)
            )
        elif verb == "transform":
            scene["timeline"].append(
                ("transform", positional[0], positional[1], float(args["t"]),
                 args.get("rate", "smooth"), float(args.get("arc", 0)))
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
            scene["zoom"] = float(args.get("zoom", ZOOM))
        elif verb == "move":
            scene["timeline"].append((
                "move",
                math.radians(float(args["phi"])) if "phi" in args else None,
                math.radians(float(args["theta"])) if "theta" in args else None,
                float(args["t"]),
                float(args["zoom"]) if "zoom" in args else None,
            ))
        elif verb == "spin":
            scene["timeline"].append(
                ("spin", float(args["rate"]), float(args["t"]), args.get("about", "theta"))
            )
        elif verb == "morph":
            scene["timeline"].append(
                ("morph", positional[0], positional[1], float(args["t"]))
            )
        elif verb in ("show", "hide"):
            scene["timeline"].append((verb, positional[0]))
        elif verb in ("fade", "fadeout"):
            shift = [float(x) for x in args.get("shift", "0,0").split(",")]
            scene["timeline"].append(
                (verb, positional[0], float(args["t"]), shift, float(args.get("from", 1.0)))
            )
        elif verb == "write":
            scene["timeline"].append(("write", positional[0], float(args["t"])))
        elif verb == "unwrite":
            scene["timeline"].append(("unwrite", positional[0], float(args["t"])))
        elif verb == "grow":
            at = [float(x) for x in args["at"].split(",")] if "at" in args else None
            scene["timeline"].append(("grow", positional[0], float(args["t"]), at))
        elif verb == "rotate":
            scene["timeline"].append(
                ("rotate", positional[0], math.radians(float(args["deg"])),
                 [float(x) for x in args.get("at", "0,0").split(",")],
                 float(args["t"]), args.get("rate", "smooth"))
            )
        elif verb == "indicate":
            scene["timeline"].append(("indicate", positional[0], float(args["t"])))
        elif verb == "fill":
            color = hex_rgb(args["color"]) if "color" in args else None
            scene["timeline"].append((
                "fill", positional[0], color,
                float(args["opacity"]) if "opacity" in args else None,
                float(args["t"]),
            ))
        elif verb == "stroke":
            color = hex_rgb(args["color"]) if "color" in args else None
            scene["timeline"].append((
                "stroke", positional[0], color,
                float(args["w"]) if "w" in args else None,
                float(args["opacity"]) if "opacity" in args else None,
                float(args["t"]),
            ))
        elif verb == "xform":
            by_xy = args.get("by_xy", "0,0").split(",")
            scene["timeline"].append(
                ("xform", positional[0], float(args.get("by", 1.0)),
                 [float(by_xy[0]), float(by_xy[1])], float(args["t"]))
            )
        elif verb == "laggedgrow":
            at = [float(x) for x in args["at"].split(",")] if "at" in args else None
            scene["timeline"].append(
                ("laggedgrow", positional[0], float(args["lag"]),
                 [int(x) for x in args["groups"].split(",")], float(args["t"]), at)
            )
        elif verb == "lag":
            scene["timeline"].append((
                "lag", int(args["n"]), float(args["ratio"]),
                [int(x) for x in args["runs"].split(",")], float(args["t"]),
            ))
        elif verb == "par":
            # A marker, not a verb: it claims the next `n` timeline entries and
            # gives them one shared clock. Manim's play(A(), B()) runs its
            # animations together, and consecutive verbs cannot say that.
            scene["timeline"].append(("par", int(args["n"]), float(args["t"])))
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
    from dsl.verbs import align, draw_border_then_fill, pointwise_become_partial

    fps = scene["fps"]
    shapes: list[np.ndarray] = []
    records: list[tuple[int, list[DecodedInstance]]] = []
    cameras: list[np.ndarray] = []
    objects: dict[str, dict] = {}

    identity = np.hstack([np.identity(3), np.zeros((3, 1))])
    is_3d = scene["mode"] == "3d"
    camera_state = {"phi": scene["phi"], "theta": scene["theta"]}

    def camera_record() -> np.ndarray:
        return np.concatenate([
            FRAME_CENTRE,
            [FOCAL_DISTANCE, scene.get("zoom", ZOOM)],
            camera_matrix(camera_state["phi"], camera_state["theta"]).reshape(9),
            LIGHT_SOURCE,
        ])

    # Surfaces declared as program become objects like anything else.
    for surface in scene["surfaces"]:
        faces = tessellate(surface["fn"], surface["u"], surface["v"], surface["res"])
        _, v_res = surface["res"]
        alpha = int(surface["alpha"] * 255)
        instances = []
        for index, face in enumerate(faces):
            i, j = divmod(index, v_res)
            colour = surface["colors"][(i + j) % len(surface["colors"])]
            centre = face.mean(axis=0)
            shapes.append(face - centre)
            instances.append((
                len(shapes) - 1,
                np.hstack([np.identity(3), centre.reshape(3, 1)]),
                (*colour, alpha), (*colour, alpha), surface["stroke"],
            ))
        objects[surface["name"]] = {
            "kind": "asset", "visible": True, "centre": np.zeros(3),
            "xform": identity.copy(), "instances": instances,
            "glyph_ids": list(range(len(instances))),
            "normals": [plane_normal(face) for face in faces],
        }

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
            "flags": [inst.flags for inst in instances],
            "normals": [inst.normal for inst in instances],
            # Library-relative ids, kept so two assets can be matched glyph for
            # glyph even though each is offset into the combined shape list.
            "glyph_ids": [inst.atlas_id for inst in instances],
            "z": scene["z"].get(name, 0.0),
        }

    def new_shape(name: str, alpha: float = 1.0) -> dict:
        spec = scene["shapes"][name]
        return {
            "kind": "shape", "visible": True, "points": geometry_for(spec),
            "alpha": alpha, "stroke": spec["stroke"], "width": spec["width"],
            "fill": (0, 0, 0, 0), "z": scene["z"].get(name, 0.0),
        }

    class _Snapshot(list):
        groups: tuple

    def emit():
        frame = _Snapshot()
        groups = []
        staged = [obj for obj in objects.values() if obj.get("visible", True)]
        staged.sort(key=lambda obj: obj.get("z", 0.0))
        for obj in staged:
            if obj["kind"] == "asset":
                # Position and glyph list are replaced, not edited, when they
                # change. An object that sits still is the same picture every
                # frame, so a lecture does not recompose its map 30 times a
                # second.
                # The slot offset is part of the token: slots are frame-wide
                # (DecodedIR.frame resolves instances by slot), so an object's
                # cached list is only reusable while the same number of
                # instances precedes it. Numbering each object from zero made
                # every object after the first overwrite the one before it.
                offset = len(frame)
                token = (id(obj["instances"]), id(obj["xform"]), offset)
                drawn = obj.get("_drawn")
                if drawn is None or drawn[0] != token:
                    normals = obj.get("normals")
                    flags = obj.get("flags")
                    built = []
                    for index, (atlas_id, transform, fill, stroke, width) in enumerate(
                        obj["instances"]
                    ):
                        normal = normals[index] if normals and index < len(normals) else None
                        if flags is not None and index < len(flags):
                            flag = flags[index]
                        else:
                            flag = SHADE_IN_3D if normal is not None else 0
                        built.append(
                            DecodedInstance(
                                slot=offset + index,
                                atlas_id=atlas_id,
                                transform=compose(obj["xform"], transform),
                                fill=fill,
                                stroke=stroke,
                                stroke_width=width,
                                flags=flag,
                                normal=normal,
                            )
                        )
                    drawn = (token, built)
                    obj["_drawn"] = drawn
                frame.extend(drawn[1])
                groups.append(drawn[1])
            else:
                offset = len(frame)
                token = (id(obj["points"]), tuple(obj["stroke"]), obj.get("alpha", 1.0),
                         obj["width"], tuple(obj.get("fill", (0, 0, 0, 0))))
                drawn = obj.get("_drawn")
                if drawn is not None and drawn[0] == token and drawn[1][0].slot != offset:
                    # Same picture, new position in the draw order: keep the
                    # atlas entry, renumber the slot.
                    drawn = (token, [replace(drawn[1][0], slot=offset)])
                    obj["_drawn"] = drawn
                if drawn is None or drawn[0] != token:
                    shapes.append(obj["points"])
                    drawn = (token, [
                        DecodedInstance(
                            slot=offset,
                            atlas_id=len(shapes) - 1,
                            transform=identity.copy(),
                            fill=(*obj.get("fill", (0, 0, 0, 0))[:3],
                                  int(obj.get("fill", (0, 0, 0, 0))[3] * obj.get("alpha", 1.0))),
                            stroke=(*obj["stroke"], int(255 * obj.get("alpha", 1.0))),
                            stroke_width=obj["width"],
                        )
                    ])
                    obj["_drawn"] = drawn
                frame.extend(drawn[1])
                groups.append(drawn[1])
        frame.groups = tuple(groups)
        records.append((REC_SNAPSHOT, frame))
        if is_3d:
            cameras.append(camera_record())

    # Rewrite create-on-asset to revealseq in a PRE-PASS. Appending the
    # rewritten step to the list being iterated pushed every asset reveal to
    # the end of the timeline, so camera moves ran before the things they were
    # meant to be looking at.
    timeline_steps = []
    for step in scene["timeline"]:
        if step[0] == "create" and name_is_asset(objects, step[1]):
            # Manim's Create on a group lags its children, which is the same
            # reveal Write performs on glyphs.
            lag = step[4] if len(step) > 4 and step[4] is not None else 1.0
            timeline_steps.append(("revealseq", step[1], step[2], lag))
        else:
            timeline_steps.append(step)

    # Manim renders the scene's opening state once, at t=0, before the first
    # animation's first step. Without it every frame after was one early and
    # the closing frame was missing -- which read as a camera error because it
    # showed up as the wrong orientation, not as a wrong length.
    opened = {"done": False}

    def play_step(step):
        """One verb, as a generator that yields once per frame it occupies.

        Yielding rather than emitting is what lets several verbs share a clock:
        the driver below advances a whole group one frame at a time and emits
        once per round. Sequential playback is the same generator, drained.
        """
        if step[0] in ("create", "uncreate"):
            _, name, duration, rate_name = step[:4]
            removing = step[0] == "uncreate"
            rate = RATE_FUNCS[rate_name]
            objects[name] = new_shape(name)
            full = objects[name]["points"]
            yield BEGUN
            for frame_index in range(int(duration * fps)):
                alpha = rate((frame_index + 1) / (duration * fps))
                if removing:
                    alpha = 1.0 - alpha
                objects[name]["points"] = pointwise_become_partial(full, 0.0, alpha)
                yield
            objects[name]["points"] = np.zeros_like(full) if removing else full
            if removing:
                objects[name]["visible"] = False

        elif step[0] == "grow":
            # GrowFromCenter on a primitive. Assets use laggedgrow instead.
            _, name, duration, *rest = step
            forced = rest[0] if rest else None
            if name not in objects:
                objects[name] = new_shape(name)
            obj = objects[name]
            obj["visible"] = True
            total = max(int(duration * fps), 1)
            if obj["kind"] == "asset":
                base = [tuple(inst) for inst in obj["instances"]]
                if forced is not None:
                    centre = np.array([
                        forced[0], forced[1],
                        forced[2] if len(forced) > 2 else 0.0,
                    ])
                else:
                    corners = [
                        shapes[aid] @ transform[:, :3].T + transform[:, 3]
                        for aid, transform, _, _, _ in base
                    ]
                    stacked = np.vstack(corners) if corners else np.zeros((1, 3))
                    centre = (stacked.min(axis=0) + stacked.max(axis=0)) / 2.0
                yield BEGUN
                for frame_index in range(total):
                    scale = smooth((frame_index + 1) / total)
                    grow = np.hstack([
                        np.identity(3) * scale,
                        ((1 - scale) * centre).reshape(3, 1),
                    ])
                    obj["instances"] = [
                        (aid, compose(grow, transform), fill, stroke, width)
                        for aid, transform, fill, stroke, width in base
                    ]
                    yield
                obj["instances"] = base
            else:
                base_points = obj["points"].copy()
                if forced is not None:
                    centre = np.array([forced[0], forced[1], forced[2] if len(forced) > 2 else 0.0])
                else:
                    centre = (base_points.min(axis=0) + base_points.max(axis=0)) / 2.0
                yield BEGUN
                for frame_index in range(total):
                    scale = smooth((frame_index + 1) / total)
                    obj["points"] = centre + (base_points - centre) * scale
                    yield
                obj["points"] = base_points

        elif step[0] == "transform":
            _, source, target, duration, rate_name, *rest = step
            arc = rest[0] if rest else 0.0
            rate = RATE_FUNCS[rate_name]
            target_spec = scene["shapes"][target]
            start_pts, end_pts = align(objects[source]["points"], geometry_for(target_spec))
            c0 = np.array(objects[source]["stroke"], dtype=float)
            c1 = np.array(target_spec["stroke"], dtype=float)
            yield BEGUN
            for frame_index in range(int(duration * fps)):
                alpha = rate((frame_index + 1) / (duration * fps))
                delta = end_pts - start_pts
                bulge = math.sin(math.pi * alpha) * arc
                perp = np.column_stack([
                    -delta[:, 1], delta[:, 0], np.zeros(len(delta)),
                ])
                objects[source]["points"] = start_pts + delta * alpha + perp * bulge
                objects[source]["stroke"] = tuple(
                    int(round(x)) for x in c0 + (c1 - c0) * alpha
                )
                yield

        elif step[0] == "stroke":
            _, name, color, width, opacity, duration = step
            obj = objects[name]
            total = max(int(duration * fps), 1)
            if obj["kind"] == "shape":
                c0 = np.array(obj["stroke"], dtype=float)
                w0 = float(obj["width"])
                a0 = float(obj.get("alpha", 1.0))
                c1 = np.array(color if color is not None else obj["stroke"], dtype=float)
                w1 = w0 if width is None else float(width)
                a1 = a0 if opacity is None else float(opacity)
                yield BEGUN
                for frame_index in range(total):
                    alpha = smooth((frame_index + 1) / total)
                    obj["stroke"] = tuple(int(round(x)) for x in c0 + (c1 - c0) * alpha)
                    obj["width"] = w0 + (w1 - w0) * alpha
                    obj["alpha"] = a0 + (a1 - a0) * alpha
                    yield
            else:
                base = [tuple(i) for i in obj["instances"]]
                yield BEGUN
                for frame_index in range(total):
                    alpha = smooth((frame_index + 1) / total)
                    grown = []
                    for aid, transform, fill, stroke, old_w in base:
                        rgb = stroke[:3] if color is None else tuple(
                            int(round(a + (b - a) * alpha)) for a, b in zip(stroke[:3], color)
                        )
                        channel = stroke[3] if opacity is None else int(round(
                            stroke[3] + (opacity * 255 - stroke[3]) * alpha
                        ))
                        new_w = old_w if width is None else old_w + (width - old_w) * alpha
                        grown.append((aid, transform, fill, (*rgb, channel), new_w))
                    obj["instances"] = grown
                    yield
        elif step[0] == "xform":
            _, name, factor, offset_xy, duration = step
            obj = objects[name]
            shift = np.array([offset_xy[0], offset_xy[1], 0.0])

            # A primitive carries its geometry directly rather than as instances
            # under an object transform, so the matrix has to be applied to its
            # points. `.animate.scale(...).shift(...)` on a Circle is ordinary
            # Manim and this branch used to assume every target was an asset.
            is_shape = obj["kind"] == "shape"
            if is_shape:
                base_points = obj["points"].copy()
                centre = (base_points.min(axis=0) + base_points.max(axis=0)) / 2.0
                base = None
            else:
                base = obj["xform"].copy()
                centre = obj.get("centre", np.zeros(3))

            yield BEGUN
            for frame_index in range(int(duration * fps)):
                alpha = smooth((frame_index + 1) / (duration * fps))
                scale = 1.0 + (factor - 1.0) * alpha
                # Manim scales about the object's centre, then translates.
                step_linear = np.identity(3) * scale
                step_translation = (1 - scale) * centre + shift * alpha
                step_matrix = np.hstack([step_linear, step_translation.reshape(3, 1)])
                if is_shape:
                    obj["points"] = (
                        base_points @ step_matrix[:, :3].T + step_matrix[:, 3]
                    )
                else:
                    obj["xform"] = compose(step_matrix, base)
                yield

        elif step[0] in ("write", "revealseq") and step[1] not in objects:
            # write targets an asset; a shape reaching here means the exporter
            # emitted a verb for something it never declared as an asset.
            raise KeyError(f"write target {step[1]!r} was never declared")

        elif step[0] in ("write", "revealseq"):
            # Manim lags each submobject. Write uses lag_ratio min(4/n, 0.2);
            # Create on a group uses 1.0, i.e. strictly one child at a time.
            _, name, duration, *rest = step
            obj = objects[name]
            # Revealing a thing puts it on stage. Without this the object
            # stayed hidden for the whole reveal and only appeared at its
            # trailing show verb.
            obj["visible"] = True
            base = [tuple(inst) for inst in obj["instances"]]
            count = max(len(base), 1)
            sequential = step[0] == "revealseq"
            if sequential:
                lag = rest[0] if rest else 1.0
            else:
                lag = min(4.0 / count, 0.2)
            span = 1.0 / (1.0 + lag * (count - 1))
            total = int(duration * fps)
            yield BEGUN
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
                    if sequential:
                        # Create on a group: a plain partial reveal, eased.
                        partial = pointwise_become_partial(shapes[aid], 0.0, smooth(local))
                        shapes.append(partial)
                        revealed.append((len(shapes) - 1, transform, fill, stroke, width))
                    else:
                        revealed.append(
                            draw_border_then_fill(shapes, aid, transform, fill, stroke, width, local)
                        )
                obj["instances"] = revealed
                yield
            obj["instances"] = base

        elif step[0] == "laggedgrow":
            # Manim's LaggedStart(*[GrowFromCenter(child) ...], lag_ratio=r).
            # Each child scales up from a point at its own centre. The group's
            # clock is linear and each child's is smooth -- the same two-level
            # timing as Write, so the stagger arithmetic is shared with it.
            _, name, lag, group_sizes, duration, *rest = step
            forced_at = rest[0] if rest else None
            obj = objects[name]
            obj["visible"] = True
            base = [tuple(inst) for inst in obj["instances"]]
            flags = obj.get("flags")
            normals = obj.get("normals")

            # Children occupy contiguous runs of instances; the program carries
            # the run lengths because the instance list alone has no notion of
            # which faces belong to which sphere.
            spans = []
            cursor = 0
            for size in group_sizes:
                spans.append((cursor, cursor + size))
                cursor += size
            if cursor != len(base):
                # The run lengths and the baked asset disagree. Growing the
                # whole object as one child still plays the beat; refusing
                # here drops the rest of the lecture.
                spans = [(0, len(base))]

            # Centres are measured, not shipped: GrowFromCenter grows about the
            # child's own bounding-box centre, which the geometry already knows.
            # GrowFromPoint ships one shared point instead.
            if forced_at is not None:
                point = np.array([
                    forced_at[0], forced_at[1],
                    forced_at[2] if len(forced_at) > 2 else 0.0,
                ])
                centres = [point for _ in spans]
            else:
                centres = []
                for lo_i, hi_i in spans:
                    corners = [
                        shapes[aid] @ transform[:, :3].T + transform[:, 3]
                        for aid, transform, _, _, _ in base[lo_i:hi_i]
                    ]
                    stacked = np.vstack(corners) if corners else np.zeros((1, 3))
                    centres.append((stacked.min(axis=0) + stacked.max(axis=0)) / 2.0)

            count = max(len(spans), 1)
            window = 1.0 / (1.0 + lag * (count - 1))
            total = int(duration * fps)
            yield BEGUN
            for frame_index in range(total):
                alpha = (frame_index + 1) / total
                grown = []
                kept = []
                for group_index, (lo_i, hi_i) in enumerate(spans):
                    start = group_index * lag * window
                    local = min(max((alpha - start) / window, 0.0), 1.0)
                    if local <= 0:
                        continue
                    scale = smooth(local)
                    # p -> c + s(p - c), which is this affine composed onto
                    # whatever transform the instance already carries.
                    grow = np.hstack([
                        np.identity(3) * scale,
                        ((1 - scale) * centres[group_index]).reshape(3, 1),
                    ])
                    for index in range(lo_i, hi_i):
                        aid, transform, fill, stroke, width = base[index]
                        grown.append(
                            (aid, compose(grow, transform), fill, stroke, width)
                        )
                        kept.append(index)
                # Flags and normals are indexed by position, so dropping the
                # not-yet-grown children would otherwise shade each sphere with
                # another sphere's normals.
                obj["instances"] = grown
                if flags is not None:
                    obj["flags"] = [flags[i] for i in kept]
                if normals is not None:
                    obj["normals"] = [normals[i] for i in kept]
                yield
            obj["instances"] = base
            if flags is not None:
                obj["flags"] = flags
            if normals is not None:
                obj["normals"] = normals

        elif step[0] == "morph":
            _, source, target, duration = step
            src, dst = objects[source], objects[target]
            src["visible"] = True
            dst["visible"] = False

            # Pair instances sharing a glyph id, in order; anything left over
            # on either side fades rather than morphing into an unrelated shape.
            pending: dict[int, list[int]] = {}
            for index, glyph in enumerate(dst["glyph_ids"]):
                pending.setdefault(glyph, []).append(index)

            pairs, orphans = [], []
            for index, glyph in enumerate(src["glyph_ids"]):
                queue = pending.get(glyph)
                if queue:
                    pairs.append((index, queue.pop(0)))
                else:
                    orphans.append(index)
            arrivals = [i for queue in pending.values() for i in queue]

            src_base = [tuple(i) for i in src["instances"]]
            dst_base = [tuple(i) for i in dst["instances"]]

            yield BEGUN
            for frame_index in range(int(duration * fps)):
                alpha = smooth((frame_index + 1) / (duration * fps))
                built = []
                for si, di in pairs:
                    a_id, a_t, a_fill, a_stroke, a_w = src_base[si]
                    _, b_t, b_fill, b_stroke, b_w = dst_base[di]
                    built.append((
                        a_id,
                        a_t + (b_t - a_t) * alpha,
                        tuple(int(round(x + (y - x) * alpha))
                              for x, y in zip(a_fill, b_fill)),
                        tuple(int(round(x + (y - x) * alpha))
                              for x, y in zip(a_stroke, b_stroke)),
                        a_w + (b_w - a_w) * alpha,
                    ))
                for si in orphans:
                    a_id, a_t, a_fill, a_stroke, a_w = src_base[si]
                    fade_out = 1.0 - alpha
                    built.append((a_id, a_t,
                                  (*a_fill[:3], int(a_fill[3] * fade_out)),
                                  (*a_stroke[:3], int(a_stroke[3] * fade_out)), a_w))
                for di in arrivals:
                    b_id, b_t, b_fill, b_stroke, b_w = dst_base[di]
                    built.append((b_id, b_t,
                                  (*b_fill[:3], int(b_fill[3] * alpha)),
                                  (*b_stroke[:3], int(b_stroke[3] * alpha)), b_w))
                src["instances"] = built
                yield
            src["instances"] = dst_base
            src["glyph_ids"] = list(dst["glyph_ids"])

            # Manim's TransformMatchingTex leaves the *target* on stage and takes
            # the source off it. The blend is carried by the source object, so
            # without this the source stayed visible holding the target's content
            # while the target's own trailing `show` drew the same thing again --
            # harmless for one morph, and cumulative for a chain of them. Three
            # morphs left three stale equations superimposed on the fourth, at
            # 255% of the frame's ink, under a frame-relative mean of 0.31%.
            src["visible"] = False
            dst["visible"] = True

        elif step[0] in ("fade", "fadeout"):
            _, name, duration, *rest = step
            shift = np.array([*(rest[0] if rest else [0.0, 0.0]), 0.0])[:3]
            fading_in = step[0] == "fade"
            if name in objects:
                objects[name]["visible"] = True
            # A declared shape only enters the scene when something animates
            # it in; fade is one of those entry points, not just create.
            if name not in objects:
                objects[name] = new_shape(name, alpha=0.0)
            obj = objects[name]
            from_scale = float(rest[1]) if len(rest) > 1 else 1.0
            # Manim's _Fade interpolates from a faded copy that FadeIn shifts
            # by -shift and FadeOut by +shift, scaled about its own centre.
            # Point by point that is c + (p - c)*scale + sign*shift*(1 - shown).
            # FadeIn used to travel +shift: things rose into place from above.
            sign = -1.0 if fading_in else 1.0
            rest_points = obj["points"].copy() if obj["kind"] == "shape" else None
            base = [tuple(i) for i in obj["instances"]] if obj["kind"] == "asset" else None
            base_xform = obj["xform"].copy() if base is not None else None
            moves = bool(np.any(shift) or from_scale != 1.0)
            if base is not None and moves:
                corners = [
                    shapes[aid] @ compose(base_xform, transform)[:, :3].T
                    + compose(base_xform, transform)[:, 3]
                    for aid, transform, _, _, _ in base
                ]
                stacked = np.vstack(corners) if corners else np.zeros((1, 3))
                asset_centre = (stacked.min(axis=0) + stacked.max(axis=0)) / 2.0
            yield BEGUN
            for frame_index in range(int(duration * fps)):
                alpha = smooth((frame_index + 1) / (duration * fps))
                shown = alpha if fading_in else 1.0 - alpha
                scale = from_scale + (1.0 - from_scale) * shown
                offset = sign * shift * (1.0 - shown)
                if base is None:
                    obj["alpha"] = shown
                    if rest_points is not None:
                        centre = (rest_points.min(axis=0) + rest_points.max(axis=0)) / 2.0
                        obj["points"] = centre + (rest_points - centre) * scale + offset
                else:
                    if moves:
                        motion = np.hstack([
                            np.identity(3) * scale,
                            ((1 - scale) * asset_centre + offset).reshape(3, 1),
                        ])
                        obj["xform"] = compose(motion, base_xform)
                    obj["instances"] = [
                        (aid, transform,
                         (*fill[:3], int(fill[3] * shown)),
                         (*stroke[:3], int(stroke[3] * shown)),
                         width)
                        for aid, transform, fill, stroke, width in base
                    ]
                yield
            if base is None:
                obj["alpha"] = 1.0 if fading_in else 0.0
                if rest_points is not None:
                    obj["points"] = rest_points if fading_in else rest_points + shift
                if not fading_in:
                    obj["visible"] = False
            else:
                obj["instances"] = base
                obj["xform"] = base_xform
                if not fading_in:
                    obj["visible"] = False

        elif step[0] == "fill":
            # `.animate.set_fill`. On an asset every instance's fill moves to
            # the colour and/or opacity given -- set_fill applies to the whole
            # family, including members that had no fill, as Manim's does.
            _, name, color, opacity, duration = step
            obj = objects[name]
            total = max(int(duration * fps), 1)
            if obj["kind"] == "shape":
                f0 = np.array(obj.get("fill", (0, 0, 0, 0)), dtype=float)
                f1 = f0.copy()
                if color is not None:
                    f1[:3] = color
                if opacity is not None:
                    f1[3] = opacity * 255
                yield BEGUN
                for frame_index in range(total):
                    alpha = smooth((frame_index + 1) / total)
                    obj["fill"] = tuple(int(x + 0.5) for x in f0 + (f1 - f0) * alpha)
                    yield
            else:
                base = [tuple(i) for i in obj["instances"]]
                yield BEGUN
                for frame_index in range(total):
                    alpha = smooth((frame_index + 1) / total)
                    changed = []
                    for aid, transform, fill, stroke, width in base:
                        rgb = fill[:3] if color is None else tuple(
                            int(a + (b - a) * alpha + 0.5) for a, b in zip(fill[:3], color)
                        )
                        channel = fill[3] if opacity is None else int(
                            fill[3] + (opacity * 255 - fill[3]) * alpha + 0.5
                        )
                        changed.append((aid, transform, (*rgb, channel), stroke, width))
                    obj["instances"] = changed
                    yield

        elif step[0] == "move":
            _, target_phi, target_theta, duration, *rest = step
            target_zoom = rest[0] if rest else None
            start_phi, start_theta = camera_state["phi"], camera_state["theta"]
            start_zoom = scene.get("zoom", ZOOM)
            total = int(duration * fps)
            yield BEGUN
            for frame_index in range(total):
                alpha = smooth((frame_index + 1) / total)
                if target_phi is not None:
                    camera_state["phi"] = start_phi + (target_phi - start_phi) * alpha
                if target_theta is not None:
                    camera_state["theta"] = start_theta + (target_theta - start_theta) * alpha
                if target_zoom is not None:
                    scene["zoom"] = start_zoom + (target_zoom - start_zoom) * alpha
                yield

        elif step[0] == "spin":
            # Manim's ambient rotation advances once per frame except on the
            # wait's last frame, which repeats the previous orientation.
            # Measured on both spinning scenes. Without it the trailing hold
            # sits 0.57 deg out for a whole second -- and the harness never
            # compares the hold, so it would not have shown up there.
            _, rate, duration, *rest = step
            about = rest[0] if rest else "theta"
            total = int(duration * fps)
            yield BEGUN
            for frame_index in range(total):
                if frame_index < total - 1:
                    if about == "phi":
                        camera_state["phi"] += rate / fps
                    else:
                        camera_state["theta"] += rate / fps
                yield

        elif step[0] == "rotate":
            _, name, radians_total, at, duration, rate_name = step
            rate_fn = RATE_FUNCS[rate_name]
            obj = objects[name]
            origin = np.array([at[0], at[1], 0.0])
            total = max(int(duration * fps), 1)
            if obj["kind"] == "shape":
                base_points = obj["points"].copy()
                yield BEGUN
                for frame_index in range(total):
                    ang = radians_total * rate_fn((frame_index + 1) / total)
                    c, s = math.cos(ang), math.sin(ang)
                    rel = base_points - origin
                    obj["points"] = np.column_stack([
                        c * rel[:, 0] - s * rel[:, 1],
                        s * rel[:, 0] + c * rel[:, 1],
                        rel[:, 2],
                    ]) + origin
                    yield
            else:
                base_inst = [tuple(i) for i in obj["instances"]]
                yield BEGUN
                for frame_index in range(total):
                    ang = radians_total * rate_fn((frame_index + 1) / total)
                    c, s = math.cos(ang), math.sin(ang)
                    ox, oy = origin[0], origin[1]
                    rot = np.array([
                        [c, -s, 0.0, ox * (1 - c) + oy * s],
                        [s, c, 0.0, oy * (1 - c) - ox * s],
                        [0.0, 0.0, 1.0, 0.0],
                    ])
                    obj["instances"] = [
                        (aid, compose(rot, transform), fill, stroke, width)
                        for aid, transform, fill, stroke, width in base_inst
                    ]
                    yield
                obj["instances"] = base_inst

        elif step[0] == "indicate":
            # A short there-and-back scale to 1.2 about the object's centre.
            _, name, duration = step
            obj = objects[name]
            total = max(int(duration * fps), 1)
            if obj["kind"] == "shape":
                base_points = obj["points"].copy()
                centre = (base_points.min(axis=0) + base_points.max(axis=0)) / 2.0
                yield BEGUN
                for frame_index in range(total):
                    pulse = there_and_back((frame_index + 1) / total)
                    scale = 1.0 + 0.2 * pulse
                    obj["points"] = centre + (base_points - centre) * scale
                    yield
                obj["points"] = base_points
            else:
                base_inst = [tuple(i) for i in obj["instances"]]
                corners = [
                    shapes[aid] @ transform[:, :3].T + transform[:, 3]
                    for aid, transform, _, _, _ in base_inst
                ]
                stacked = np.vstack(corners) if corners else np.zeros((1, 3))
                centre = (stacked.min(axis=0) + stacked.max(axis=0)) / 2.0
                yield BEGUN
                for frame_index in range(total):
                    pulse = there_and_back((frame_index + 1) / total)
                    scale = 1.0 + 0.2 * pulse
                    grow = np.hstack([
                        np.identity(3) * scale,
                        ((1 - scale) * centre).reshape(3, 1),
                    ])
                    obj["instances"] = [
                        (aid, compose(grow, transform), fill, stroke, width)
                        for aid, transform, fill, stroke, width in base_inst
                    ]
                    yield
                obj["instances"] = base_inst

        elif step[0] == "unwrite":
            _, name, duration = step
            obj = objects[name]
            obj["visible"] = True
            base = [tuple(inst) for inst in obj["instances"]]
            count = max(len(base), 1)
            lag = min(4.0 / count, 0.2)
            span = 1.0 / (1.0 + lag * (count - 1))
            total = max(int(duration * fps), 1)
            yield BEGUN
            for frame_index in range(total):
                alpha = 1.0 - (frame_index + 1) / total
                revealed = []
                for i, (aid, transform, fill, stroke, width) in enumerate(base):
                    start = i * lag * span
                    local = min(max((alpha - start) / span, 0.0), 1.0)
                    if local <= 0:
                        continue
                    revealed.append((aid, transform, fill, stroke, width))
                obj["instances"] = revealed
                yield
            obj["instances"] = []
            obj["visible"] = False

        elif step[0] == "wait":
            yield BEGUN
            for _ in range(int(step[1] * fps)):
                yield

    def frames_of(node) -> int:
        """How many frames a (possibly folded) step occupies.

        Mirrors each branch of play_step: most verbs run int(t * fps) frames,
        and the ones that guard with max(..., 1) run at least one.
        """
        kind = node[0]
        if kind == "parallel":
            return max((frames_of(m) for m in node[1]), default=0)
        if kind == "sequence":
            return sum(frames_of(m) for m in node[1])
        if kind == "laggroup":
            return int(node[2] * fps)
        if kind in ("show", "hide"):
            return 0
        if kind == "wait":
            return int(node[1] * fps)
        if kind in ("move", "spin"):
            return int(node[3 if kind == "move" else 2] * fps)
        if kind in ("grow", "indicate", "unwrite"):
            return max(int(node[2] * fps), 1)
        if kind in ("stroke", "fill"):
            return max(int(node[-1] * fps), 1)
        if kind == "rotate":
            return max(int(node[4] * fps), 1)
        if kind == "xform":
            return int(node[4] * fps)
        if kind == "laggedgrow":
            return int(node[4] * fps)
        if kind in ("transform", "morph"):
            return int(node[3] * fps)
        return int(node[2] * fps)

    def fold(steps):
        """Fold `par` and `lag` headers into nodes, as the phone's builder does.

        Both headers claim the lines after them, and a `lag` can sit inside a
        `par` -- a beat that pops a marker while the panel changes. This used
        to understand `lag` only at the top level, so a nested one played its
        children all at once. Show and hide are not verbs: inside a `par`
        window they are carried out to follow it.
        """
        out = []
        cursor = 0
        while cursor < len(steps):
            step = steps[cursor]
            cursor += 1
            if step[0] == "par":
                members, carried = [], []
                while len(members) < step[1] and cursor < len(steps):
                    nxt = steps[cursor]
                    cursor += 1
                    (carried if nxt[0] in ("show", "hide") else members).append(nxt)
                if members:
                    out.append(("parallel", fold(members)))
                out.extend(carried)
            elif step[0] == "lag":
                children = []
                for run in step[3]:
                    inner = fold(steps[cursor:cursor + run])
                    cursor += run
                    if len(inner) == 1:
                        children.append(inner[0])
                    elif inner:
                        children.append(("sequence", inner))
                if children:
                    out.append(("laggroup", step[2], step[4], children))
            else:
                out.append(step)
        return out

    def play_node(node):
        """A folded step as a generator: BEGUN once set up, then one per frame."""
        kind = node[0]
        if kind == "parallel":
            running = [begin(play_node(member)) for member in node[1]]
            yield BEGUN
            while running:
                alive = []
                for runner in running:
                    try:
                        next(runner)
                        alive.append(runner)
                    except StopIteration:
                        pass  # its epilogue has run; it holds its last state
                if alive:
                    yield
                running = alive
        elif kind == "sequence":
            yield BEGUN
            for member in node[1]:
                yield from begin(play_node(member))
        elif kind == "laggroup":
            # Manim's LaggedStart: child i starts after the earlier children's
            # run times times the ratio, and the whole is stretched onto the
            # group's own run time. Frame for frame what the phone does. A
            # child begins when its turn comes: begun early, a fade-in would
            # put its object on stage at full opacity before it had started.
            _, ratio, duration, children = node
            counts = [frames_of(child) for child in children]
            run_times = [count / fps for count in counts]
            starts_at = [0.0]
            for i in range(len(children) - 1):
                starts_at.append(starts_at[-1] + run_times[i] * ratio)
            max_end = max(
                (starts_at[i] + run_times[i] for i in range(len(children))), default=1.0
            )
            total = int(duration * fps)
            runners = [None] * len(children)
            produced = [0] * len(children)
            yield BEGUN
            for frame in range(total):
                internal = (frame + 1) / max(total, 1) * max(max_end, 1e-6)
                for i, child in enumerate(children):
                    if counts[i] <= 0 or run_times[i] <= 0:
                        continue
                    local = min(max((internal - starts_at[i]) / run_times[i], 0.0), 1.0)
                    if local <= 0:
                        continue
                    if runners[i] is None:
                        runners[i] = begin(play_node(child))
                    target = min(max(int(local * counts[i]) - 1, 0), counts[i] - 1)
                    while produced[i] <= target:
                        try:
                            next(runners[i])
                        except StopIteration:
                            produced[i] = counts[i]
                            break
                        produced[i] += 1
                yield
            for i, child in enumerate(children):
                # Settle every child's end state, as the phone's exit() does.
                runner = runners[i] if runners[i] is not None else begin(play_node(child))
                for _ in runner:
                    pass
        elif kind in ("show", "hide"):
            obj = objects.get(node[1])
            if obj is not None:
                obj["visible"] = kind == "show"
            yield BEGUN
        else:
            generator = begin(play_step(node))
            yield BEGUN
            yield from generator

    for step in fold(timeline_steps):
        if step[0] in ("show", "hide"):
            # `hide` names something Manim took off stage. It may name an object
            # this interpreter never put on one -- a fadeout drops its object
            # outright -- so a hide for an absent name is a no-op rather than an
            # error.
            obj = objects.get(step[1])
            if obj is not None:
                obj["visible"] = step[0] == "show"
            elif step[0] == "show":
                raise KeyError(f"show target {step[1]!r} was never declared")
            continue

        # After any leading `show`, so objects added before the first play are
        # on stage in the opening frame, as they are in Manim.
        if not opened["done"]:
            opened["done"] = True
            emit()

        # A wait does not change the picture. One snapshot, repeated, keeps the
        # frame count Manim would have rendered without copying the scene
        # thousands of times. A lecture is mostly these holds.
        if step[0] == "wait":
            n = int(step[1] * fps)
            if n > 0:
                emit()
                last = records[-1]
                records.extend((last,) * (n - 1))
                if is_3d:
                    cameras.extend((cameras[-1],) * (n - 1))
            continue

        for _ in begin(play_node(step)):
            emit()

    return DecodedIR(
        fps=fps, shapes=shapes, records=records, cameras=cameras if is_3d else None
    )


def build(scene: dict) -> DecodedIR:
    """Expand a parsed program into frames.

    There used to be a second, 3D-only builder here, kept from before 2D and 3D
    were unified. It was unreachable -- `build_2d` handles any program with a
    timeline, and a program without one has nothing to draw -- and it carried
    its own copy of the timeline semantics, so a fix applied to one path would
    silently not apply to the other. Three bugs in this project were an
    animation quietly taking the wrong branch; a duplicate branch nobody runs
    is the same hazard waiting.
    """
    return build_2d(scene)


def plane_normal(points: np.ndarray) -> np.ndarray:
    centred = points - points.mean(axis=0)
    _, _, vh = np.linalg.svd(centred, full_matrices=False)
    normal = vh[2]
    return -normal if normal[2] < 0 else normal


def load_program(path: str) -> DecodedIR:
    return build(parse(Path(path).read_text()))


if __name__ == "__main__":
    ir = load_program(sys.argv[1])
    raw = Path(sys.argv[1]).stat().st_size
    print(f"program bytes      {raw}")
    print(f"atlas shapes       {len(ir.shapes)}")
    print(f"frames             {len(ir.records)}")
