"""Try to express a Manim scene as a DSL program; report precisely why not.

This is the other half of the program-shipping idea. The interpreter proved a
DSL program can reproduce Manim; this decides whether a given scene can be
*written* as one.

It observes a scene by intercepting play/wait and the camera methods, then maps
what it saw onto DSL verbs. Anything unrecognised is recorded as a blocker
rather than guessed at -- a wrong guess would ship a subtly incorrect animation,
whereas a blocker just falls back to the sampled IR.

The blocker list is the useful output: it is a measured, prioritised list of
what the DSL vocabulary is missing.

Usage:
    python -m dsl.export_dsl <scene_file.py> <SceneClass>
"""

from __future__ import annotations

import inspect
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class Recorder:
    def __init__(self):
        self.declarations: list[str] = []
        self.timeline: list[str] = []
        self.blockers: list[str] = []
        self.names: dict[int, str] = {}
        self.counter = 0

    def name_for(self, mob) -> str:
        if id(mob) not in self.names:
            self.names[id(mob)] = chr(ord("A") + self.counter % 26)
            self.counter += 1
        return self.names[id(mob)]

    def hex_of(self, mob) -> str:
        try:
            return str(mob.get_stroke_color()).upper()
        except Exception:
            return "#FFFFFF"

    def declare(self, mob) -> str | None:
        """Emit a declaration for a mobject, or record why we cannot."""
        from manim import Circle, Square, Surface

        # Non-drawable scaffolding: ValueTracker stores its value *as* a
        # point, so emptiness is the wrong test. Fewer than four points cannot
        # form a cubic, which is the same filter the sampled exporter uses.
        points = getattr(mob, "points", None)
        drawable = points is not None and len(points) >= 4
        if not drawable and not mob.submobjects:
            return None

        name = self.name_for(mob)
        if any(d.split()[1] == name for d in self.declarations):
            return name

        if isinstance(mob, Circle):
            radius = float(mob.width / 2)
            self.declarations.append(
                f"circle {name} r={radius:g} stroke={self.hex_of(mob)} "
                f"w={float(mob.get_stroke_width()):g}"
            )
            return name

        if isinstance(mob, Square):
            self.declarations.append(
                f"square {name} s={float(mob.width):g} stroke={self.hex_of(mob)} "
                f"w={float(mob.get_stroke_width()):g}"
            )
            return name

        if isinstance(mob, Surface):
            expr = surface_expression(mob)
            if expr is None:
                self.blockers.append(
                    f"Surface function is not a recognisable expression "
                    f"(needs a declarative form or source that parses)"
                )
                return None
            u0, u1 = mob.u_range
            v0, v1 = mob.v_range
            res = getattr(mob, "resolution", (24, 24))
            colours = ",".join(str(c).upper() for c in (mob.checkerboard_colors or ["#FFFFFF"]))
            self.declarations.append(
                f"surface {name} fn={expr} u={u0:g},{u1:g} v={v0:g},{v1:g} "
                f"res={res[0]},{res[1]} fill={colours} "
                f"alpha={float(mob.fill_opacity):g} stroke={float(mob.get_stroke_width()):g}"
            )
            return name

        self.blockers.append(f"unsupported mobject: {type(mob).__name__}")
        return None


def surface_expression(mob) -> str | None:
    """Recover a surface's z expression from its lambda source, if possible.

    A production exporter would want a declarative surface form in the authoring
    API rather than source scraping. This is enough to measure coverage.
    """
    # Surface.func is a method wrapper; the authored lambda is on _func.
    func = getattr(mob, "_func", None) or getattr(mob, "func", None)
    if func is None:
        return None
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return None

    match = re.search(r"np\.array\(\[\s*u\s*,\s*v\s*,\s*([^\]]+)\]\)", source)
    if not match:
        return None
    expr = match.group(1).strip().rstrip(",")
    # The DSL is whitespace-tokenised, so the expression must not contain
    # spaces -- emitting "0.6 * sin(u)" produced a program that would not parse.
    expr = expr.replace("np.", "").replace(" ", "")
    return expr if re.fullmatch(r"[0-9a-zA-Z_+\-*/()., ]+", expr) else None


def record_scene(scene_file: str, scene_class: str) -> Recorder:
    from manim import Scene, tempconfig
    from manim.animation.creation import Create
    from manim.animation.transform import Transform
    from manim.animation.animation import Wait
    from manim.scene.three_d_scene import ThreeDScene

    rec = Recorder()
    originals = {
        "play": Scene.play,
        "add": Scene.add,
        "move_camera": ThreeDScene.move_camera,
        "set_orientation": ThreeDScene.set_camera_orientation,
        "begin_spin": ThreeDScene.begin_ambient_camera_rotation,
        "stop_spin": ThreeDScene.stop_ambient_camera_rotation,
    }
    state = {"spin_rate": None, "in_camera_move": False}

    def patched_play(self, *animations, **kwargs):
        run_time = kwargs.get("run_time")
        for anim in animations:
            duration = run_time if run_time is not None else getattr(anim, "run_time", 1.0)

            # move_camera drives the camera through play internally. Those
            # animations are already captured by the move_camera patch, so
            # counting them again would report a false blocker.
            if state["in_camera_move"]:
                continue

            # Scene.wait routes through play as a Wait animation, which is
            # linear by definition -- not a rate function we need to support.
            if isinstance(anim, Wait):
                if state["spin_rate"] is not None:
                    rec.timeline.append(f"spin rate={state['spin_rate']:g} t={duration:g}")
                else:
                    rec.timeline.append(f"wait t={duration:g}")
                continue

            rate = getattr(anim, "rate_func", None)
            if rate is not None and rate.__name__ != "smooth":
                rec.blockers.append(f"non-default rate_func: {rate.__name__}")

            if isinstance(anim, Create):
                name = rec.declare(anim.mobject)
                if name:
                    rec.timeline.append(f"create {name} t={duration:g}")
            elif isinstance(anim, Transform):
                source = rec.declare(anim.mobject)
                target = rec.declare(anim.target_mobject)
                if source and target:
                    rec.timeline.append(f"transform {source} {target} t={duration:g}")
            else:
                rec.blockers.append(f"unsupported animation: {type(anim).__name__}")
        return originals["play"](self, *animations, **kwargs)

    def patched_add(self, *mobjects, **kw):
        # Objects put on stage directly rather than animated in. Missing these
        # produced a program that claimed tier 1 while drawing nothing.
        for mob in mobjects:
            rec.declare(mob)
        return originals["add"](self, *mobjects, **kw)

    def patched_orientation(self, phi=None, theta=None, **kw):
        parts = []
        if phi is not None:
            parts.append(f"phi={math.degrees(phi):g}")
        if theta is not None:
            parts.append(f"theta={math.degrees(theta):g}")
        rec.declarations.append("camera " + " ".join(parts))
        return originals["set_orientation"](self, phi=phi, theta=theta, **kw)

    def patched_move_camera(self, phi=None, theta=None, run_time=3.0, **kw):
        parts = []
        if phi is not None:
            parts.append(f"phi={math.degrees(phi):g}")
        if theta is not None:
            parts.append(f"theta={math.degrees(theta):g}")
        rec.timeline.append("move " + " ".join(parts) + f" t={run_time:g}")
        state["in_camera_move"] = True
        try:
            return originals["move_camera"](
                self, phi=phi, theta=theta, run_time=run_time, **kw
            )
        finally:
            state["in_camera_move"] = False

    def patched_spin(self, rate=0.02, **kw):
        state["spin_rate"] = rate
        return originals["begin_spin"](self, rate=rate, **kw)

    def patched_stop_spin(self, **kw):
        state["spin_rate"] = None
        return originals["stop_spin"](self, **kw)

    Scene.play = patched_play
    Scene.add = patched_add
    ThreeDScene.move_camera = patched_move_camera
    ThreeDScene.set_camera_orientation = patched_orientation
    ThreeDScene.begin_ambient_camera_rotation = patched_spin
    ThreeDScene.stop_ambient_camera_rotation = patched_stop_spin

    path = Path(scene_file).resolve()
    sys.path.insert(0, str(path.parent))
    module = __import__(path.stem)

    try:
        with tempconfig(
            {
                "quality": "low_quality",
                "write_to_movie": False,
                "verbosity": "ERROR",
                "progress_bar": "none",
            }
        ):
            getattr(module, scene_class)().render()
    finally:
        Scene.play = originals["play"]
        Scene.add = originals["add"]
        ThreeDScene.move_camera = originals["move_camera"]
        ThreeDScene.set_camera_orientation = originals["set_orientation"]
        ThreeDScene.begin_ambient_camera_rotation = originals["begin_spin"]
        ThreeDScene.stop_ambient_camera_rotation = originals["stop_spin"]

    return rec


def emit(rec: Recorder, mode: str, fps: int = 30) -> str:
    lines = [f"scene {mode} fps={fps}"] + rec.declarations + rec.timeline
    return "\n".join(lines) + "\n"


def main():
    scene_file, scene_class = sys.argv[1:3]
    rec = record_scene(scene_file, scene_class)

    mode = "3d" if any(d.startswith(("surface", "camera")) for d in rec.declarations) else "2d"
    program = emit(rec, mode)

    print(f"=== {scene_class} ===")
    if rec.blockers:
        print("TIER 3 (falls back to sampled IR)")
        for blocker in dict.fromkeys(rec.blockers):
            print(f"  blocked by: {blocker}")
    else:
        print(f"TIER 1 ({len(program)} bytes)")
        print(program)


if __name__ == "__main__":
    main()
