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


def export_text_asset(mob, path: Path) -> int:
    """Bake a text mobject's glyphs into a standalone asset file.

    Text can never be *program*: Manim hands us outlines with no glyph
    identity, and LaTeX cannot run on device. So it ships as tier 2 -- a
    deduplicated atlas the program points at. Assets are content-addressed so
    the same words across a library resolve to one cached file.
    """
    import numpy as np

    from exporter.export_scene import read_style
    from exporter.ir import REC_SNAPSHOT, Atlas, Instance, serialise

    atlas = Atlas()
    instances: dict[int, Instance] = {}
    for index, sub in enumerate(mob.get_family()):
        points = getattr(sub, "points", None)
        if points is None or len(points) < 4:
            continue
        atlas_id, transform = atlas.resolve(np.asarray(points, dtype=np.float64))
        fill, stroke, width = read_style(sub)
        instances[index] = Instance(atlas_id, transform, fill, stroke, width)

    blob = serialise(atlas, [(REC_SNAPSHOT, instances)], fps=30)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return len(blob)


class Recorder:
    def __init__(self):
        self.assets: dict[str, int] = {}
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

    def is_asset(self, name: str) -> bool:
        return any(
            d.startswith(("text ", "geom ")) and d.split()[1] == name
            for d in self.declarations
        )

    @staticmethod
    def is_primitive(mob) -> bool:
        from manim import Circle, Square

        return isinstance(mob, (Circle, Square)) or type(mob).__name__ in (
            "Rectangle", "SurroundingRectangle"
        )

    def hex_of(self, mob) -> str:
        try:
            return str(mob.get_stroke_color()).upper()
        except Exception:
            return "#FFFFFF"

    def declare(self, mob) -> str | None:
        """Emit a declaration for a mobject, or record why we cannot."""
        import hashlib

        from manim import Circle, Square, Surface
        from manim.mobject.text.tex_mobject import SingleStringMathTex
        from manim.mobject.text.text_mobject import Text

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

        if type(mob).__name__ in ("Rectangle", "SurroundingRectangle"):
            centre = mob.get_center()
            self.declarations.append(
                f"rect {name} wh={float(mob.width):g},{float(mob.height):g} "
                f"at={centre[0]:g},{centre[1]:g} stroke={self.hex_of(mob)} "
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

        if type(mob).__name__ in ("VGroup", "Group") and mob.submobjects:
            # A group of recognisable primitives stays program; a group of
            # arbitrary imported geometry becomes a tier-2 asset. Baking the
            # whole group in one go keeps its internal structure intact.
            if all(self.is_primitive(child) for child in mob.submobjects):
                for child in mob.submobjects:
                    self.declare(child)
                return name
            from dsl.library import export_standalone_asset

            digest = hashlib.sha1(geometry_digest(mob)).hexdigest()[:10]
            asset = Path("dsl/generated/assets") / f"{digest}.panm"
            self.assets[digest] = export_standalone_asset(mob, asset)
            self.declarations.append(f"geom {name} asset={digest}")
            return name

        if isinstance(mob, (Text, SingleStringMathTex)) or type(mob).__name__ in (
            "MathTex", "Tex", "Code", "MarkupText"
        ):
            # Hash the actual geometry, not a text attribute: Code exposes no
            # .text, so two different code blocks at the same centre collided
            # onto one asset and the program referenced the wrong content.
            digest = hashlib.sha1(geometry_digest(mob)).hexdigest()[:10]
            asset = Path("dsl/generated/assets") / f"{digest}.panm"
            from dsl.library import GlyphLibrary, export_text_instances

            library = GlyphLibrary()
            self.assets[digest] = export_text_instances(mob, asset, library)
            library.save()
            self.declarations.append(f"text {name} asset={digest}")
            return name

        self.blockers.append(f"unsupported mobject: {type(mob).__name__}")
        return None


def geometry_digest(mob) -> bytes:
    """Content-address a mobject by its actual geometry and styling."""
    import numpy as np

    parts = []
    for sub in mob.get_family():
        points = getattr(sub, "points", None)
        if points is None or len(points) < 4:
            continue
        parts.append(np.asarray(points, dtype=np.float64).tobytes())
        parts.append(str(sub.get_fill_color()).encode())
    return b"".join(parts) or repr(type(mob)).encode()


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


def affine_verb(methods, target: str, duration: float) -> str | None:
    """Map a whole .animate chain onto one DSL verb, if every step is affine.

    Chained methods run *concurrently* over the animation's run_time -- emitting
    one verb per method would play them in sequence and stretch the scene.
    """
    import numpy as np

    parts = []
    for entry in methods:
        name = entry.method.__name__
        if name == "scale" and entry.args:
            parts.append(f"by={float(entry.args[0]):g}")
        elif name == "shift" and entry.args:
            vector = np.asarray(entry.args[0], dtype=float).reshape(3)
            parts.append(f"by_xy={vector[0]:g},{vector[1]:g}")
        else:
            return None
    return f"xform {target} " + " ".join(parts) + f" t={duration:g}" if parts else None


def record_scene(scene_file: str, scene_class: str) -> Recorder:
    from manim import Scene, tempconfig
    from manim.animation.creation import Create
    from manim.animation.creation import Write
    from manim.animation.fading import FadeIn, FadeOut
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
            rate_name = rate.__name__ if rate is not None else "smooth"
            if rate_name not in ("smooth", "linear"):
                rec.blockers.append(f"non-default rate_func: {rate_name}")
            suffix = "" if rate_name == "smooth" else f" rate={rate_name}"

            if isinstance(anim, Write):
                # Write reveals each glyph in turn. On a text asset that is a
                # lagged per-glyph reveal, not a single partial path.
                name = rec.declare(anim.mobject)
                if name:
                    rec.timeline.append(f"write {name} t={duration:g}")
                else:
                    rec.blockers.append("Write target could not be declared")
            elif isinstance(anim, FadeOut):
                name = rec.declare(anim.mobject)
                if name:
                    rec.timeline.append(f"fadeout {name} t={duration:g}")
                else:
                    rec.blockers.append("FadeOut target could not be declared")
            elif isinstance(anim, FadeIn):
                # FadeIn subclasses Transform, so it must be tested first --
                # and its target_mobject is not a separate declarable shape.
                name = rec.declare(anim.mobject)
                if name:
                    rec.timeline.append(f"fade {name} t={duration:g}")
                else:
                    rec.blockers.append("FadeIn target could not be declared")
            elif isinstance(anim, Create):
                name = rec.declare(anim.mobject)
                if name:
                    rec.timeline.append(f"create {name} t={duration:g}{suffix}")
                else:
                    rec.blockers.append("Create target could not be declared")
            elif isinstance(anim, Transform):
                source = rec.declare(anim.mobject)
                target = rec.declare(anim.target_mobject)
                # Morphing one baked asset into another is glyph-level
                # matching -- the same capability as TransformMatchingTex --
                # and the runtime cannot do it. Emitting the verb anyway would
                # ship a program that crashes or renders the wrong thing.
                if source and target and not (
                    rec.is_asset(source) or rec.is_asset(target)
                ):
                    rec.timeline.append(
                        f"transform {source} {target} t={duration:g}{suffix}"
                    )
                elif source and target:
                    rec.blockers.append(
                        "Transform between baked assets (needs glyph-level matching)"
                    )
                else:
                    # Never drop an animation silently: a missing verb shifts
                    # the whole timeline and the program renders the wrong thing.
                    rec.blockers.append(
                        f"{type(anim).__name__} operands could not be declared"
                    )
            elif type(anim).__name__ == "_AnimationBuilder":
                target = rec.declare(anim.mobject)
                if target:
                    verb = affine_verb(anim.methods, target, duration)
                    if verb:
                        rec.timeline.append(verb)
                    else:
                        names = ", ".join(e.method.__name__ for e in anim.methods)
                        rec.blockers.append(f"unsupported .animate method: {names}")
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
