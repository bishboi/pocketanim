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
        # Pristine geometry per baked asset, kept so the asset can be baked a
        # second time once the tightest zoom in the program is known.
        self.snapshots: dict[str, list] = {}
        self.declarations: list[str] = []
        self.timeline: list[str] = []
        self.blockers: list[str] = []
        self.names: dict[int, str] = {}
        self.counter = 0
        # Mobjects whose geometry is already inside a declared group asset.
        # Manim's introducer animations add each child to the scene on
        # clean-up, and declaring those again would put every atom on stage
        # twice -- once through the group, once on its own.
        self.covered: set[int] = set()

    def name_for(self, mob) -> str:
        """Unique short name. Wrapping at 26 silently aliased two objects onto
        one name in a 26-declaration scene, so names extend past Z."""
        if id(mob) not in self.names:
            index = self.counter
            letter = chr(ord("A") + index % 26)
            suffix = index // 26
            self.names[id(mob)] = letter if suffix == 0 else f"{letter}{suffix}"
            self.counter += 1
        return self.names[id(mob)]

    def primitive_is_faithful(self, mob) -> bool:
        """Whether a `circle`/`square`/`rect` declaration reproduces `mob`.

        Checked against the mobject's own anchors rather than against a
        regenerated primitive, because the two differ by construction: Manim
        builds a circle's handles at d_theta/3 and `dsl.verbs.circle` at
        (4/3)tan(d_theta/4), a 1.3% difference that is not an error and must
        not be read as one. The anchors are exact on both sides.
        """
        import numpy as np

        from manim import Circle

        # The declarations carry one opaque stroke and no fill.
        if float(mob.get_fill_opacity()) > 0:
            return False
        if not np.isclose(float(mob.get_stroke_opacity()), 1.0):
            return False

        points = np.asarray(getattr(mob, "points", []), dtype=float)
        if len(points) < 4:
            return False
        # The start anchor of each cubic; handles say nothing about the shape's
        # placement, and a closed primitive's anchors are its corners.
        anchors = points[::4, :2] - np.asarray(mob.get_center(), dtype=float)[:2]

        if isinstance(mob, Circle):
            # A stretched circle is an ellipse, and its anchors are not all one
            # radius from the centre.
            radii = np.hypot(anchors[:, 0], anchors[:, 1])
            return bool(np.allclose(radii, float(mob.width) / 2, rtol=1e-3, atol=1e-6))

        # A rotated square or rectangle has anchors off the axis-aligned
        # corners, and `mob.width` is then its bounding box rather than a side.
        half = np.array([float(mob.width) / 2, float(mob.height) / 2])
        if not np.all(half > 0):
            return False
        return bool(
            np.allclose(np.abs(anchors[:, 0]), half[0], rtol=1e-3, atol=1e-6)
            and np.allclose(np.abs(anchors[:, 1]), half[1], rtol=1e-3, atol=1e-6)
        )

    def declared(self, name: str) -> bool:
        return any(d.split()[1] == name for d in self.declarations)

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

        # A primitive declaration carries a size, a centre and a stroke, and
        # nothing else -- so it can only be used where that is the whole of the
        # mobject. `Square(fill_opacity=1)` came out as an empty outline,
        # `Square(2).rotate(PI/4)` as an axis-aligned square of its bounding
        # box (2.83 rather than 2), and `Circle(1).stretch(2, 0)` as a circle
        # of radius 2. All three at tier 1, with no blocker, because the
        # emitter read `mob.width` and never asked whether the shape it was
        # about to name was the shape it had.
        #
        # Falling through rather than blocking: the geom path below bakes any
        # mobject exactly, style included, and stays tier 1. A faithful
        # primitive is smaller, not more correct.
        faithful = self.primitive_is_faithful(mob)

        # `at=` on every primitive, not just Rectangle. Both interpreters have
        # always read it for all three -- the reader was built for a field the
        # writer never sent, so a circle anywhere but the origin was quietly
        # drawn at the origin. corpus/scenes/12_positioned_primitives.py is the
        # scene that would have caught it, and did not exist.
        if faithful and isinstance(mob, Circle):
            radius = float(mob.width / 2)
            centre = mob.get_center()
            self.declarations.append(
                f"circle {name} r={radius:g} at={centre[0]:g},{centre[1]:g} "
                f"stroke={self.hex_of(mob)} w={float(mob.get_stroke_width()):g}"
            )
            return name

        if faithful and isinstance(mob, Square):
            centre = mob.get_center()
            self.declarations.append(
                f"square {name} s={float(mob.width):g} at={centre[0]:g},{centre[1]:g} "
                f"stroke={self.hex_of(mob)} w={float(mob.get_stroke_width()):g}"
            )
            return name

        if faithful and type(mob).__name__ in ("Rectangle", "SurroundingRectangle"):
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
                # Not every Surface is a parseable expression -- Sphere is a
                # Surface, and axes.c2p closures are not expressions at all.
                # Geometry always has a tier-2 fallback, so bake rather than
                # block; only an inexpressible animation forces tier 3.
                expr = None
        if isinstance(mob, Surface) and expr is not None:
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
            # Always bake a group, even one of recognisable primitives. The
            # earlier special case declared the *children* and returned the
            # *group's* name, which no declaration ever defined -- so verbs
            # referenced a name the runtime had never seen. The DSL has no
            # group concept, so one name must mean one declared thing.
            from dsl.library import export_standalone_asset, snapshot_family

            digest = hashlib.sha1(geometry_digest(mob)).hexdigest()[:10]
            asset = Path("dsl/generated/assets") / f"{digest}.panm"
            snapshot = snapshot_family(mob)
            self.snapshots[digest] = snapshot
            self.assets[digest] = export_standalone_asset(snapshot, asset)
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

        # Geometry we cannot express as program is still shippable as a
        # tier-2 asset, which beats dropping the whole scene to sampled IR.
        # Only an inexpressible *animation* should force tier 3.
        if drawable or mob.submobjects:
            from dsl.library import export_standalone_asset, snapshot_family

            digest = hashlib.sha1(geometry_digest(mob)).hexdigest()[:10]
            asset = Path("dsl/generated/assets") / f"{digest}.panm"
            snapshot = snapshot_family(mob)
            self.snapshots[digest] = snapshot
            self.assets[digest] = export_standalone_asset(snapshot, asset)
            self.declarations.append(f"geom {name} asset={digest}")
            return name

        self.blockers.append(f"unsupported mobject: {type(mob).__name__}")
        return None


def instance_partition(group) -> list[int] | None:
    """Instance counts per direct child, matching the asset baker's filter.

    A baked group is a flat instance list, so a per-child animation needs to
    know where each child's run begins. This counts with exactly the same
    `len(points) >= 4` test `export_standalone_asset` applies, because a
    disagreement of one would misalign every subsequent child.
    """
    points = getattr(group, "points", None)
    if points is not None and len(points) >= 4:
        # The baker would emit the container itself first, shifting every run.
        return None
    return [
        sum(
            1
            for sub in child.get_family()
            if getattr(sub, "points", None) is not None and len(sub.points) >= 4
        )
        for child in group.submobjects
    ]


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
    from manim.animation.transform_matching_parts import TransformMatchingAbstractBase
    from manim.animation.composition import LaggedStart
    from manim.animation.fading import FadeIn, FadeOut
    from manim.animation.growing import GrowFromPoint
    from manim.animation.transform import Transform
    from manim.animation.animation import Wait
    from manim.scene.three_d_scene import ThreeDScene

    # TransformMatchingTex consumes its target_mobject in __init__ and never
    # stores it, so capture the operands at construction.
    matching_init = TransformMatchingAbstractBase.__init__

    def patched_matching_init(self, mobject, target_mobject, *a, **kw):
        self._panim_source = mobject
        self._panim_target = target_mobject
        return matching_init(self, mobject, target_mobject, *a, **kw)

    TransformMatchingAbstractBase.__init__ = patched_matching_init

    rec = Recorder()
    originals = {
        "play": Scene.play,
        "add": Scene.add,
        "remove": Scene.remove,
        "move_camera": ThreeDScene.move_camera,
        "set_orientation": ThreeDScene.set_camera_orientation,
        "begin_spin": ThreeDScene.begin_ambient_camera_rotation,
        "stop_spin": ThreeDScene.stop_ambient_camera_rotation,
    }
    state = {"spin_rate": None, "in_camera_move": False}

    def animation_blockers(anim) -> None:
        """Name the animation arguments the verb set cannot carry.

        The same class as the camera audit, on the other side of `play`: each
        of these is read off the animation and then dropped, leaving a
        well-formed program that plays something else. Measured, not guessed:

          FadeIn(square, shift=UP*2)     faded in place
          Uncreate(circle)               played forwards and left it on stage
          Transform(a, b, path_arc=PI/2) travelled in a straight line
          Write(text, reverse=True)      wrote instead of un-writing

        Blocked rather than implemented, as with the camera: there is no corpus
        scene for any of them, and tier 3 draws them correctly today where a
        new verb would be an unmeasured code path.
        """
        import numpy as np

        name = type(anim).__name__

        # FadeIn/FadeOut travel and scale while they fade; `fade` carries a
        # name and a duration.
        shift = getattr(anim, "shift_vector", None)
        if shift is not None and not np.allclose(np.asarray(shift, dtype=float), 0.0):
            rec.blockers.append(f"{name} with shift=")
        scale = getattr(anim, "scale_factor", None)
        if scale is not None and not np.isclose(float(scale), 1.0):
            rec.blockers.append(f"{name} with scale=")
        if getattr(anim, "target_position", None) is not None:
            rec.blockers.append(f"{name} with target_position=")

        # Transform's points follow an arc rather than the straight line both
        # interpreters draw.
        arc = getattr(anim, "path_arc", None)
        if arc is not None and not np.isclose(float(arc), 0.0):
            rec.blockers.append(f"{name} with path_arc=")

        # Write(reverse=True), and Unwrite, un-write and then remove.
        if getattr(anim, "reverse", False):
            rec.blockers.append(f"{name} plays in reverse")

        # Uncreate is Create with the rate function reversed and the mobject
        # removed at the end, so it reached the Create branch and exported as a
        # forward create.
        if isinstance(anim, Create):
            if getattr(anim, "remover", False):
                rec.blockers.append(f"{name} un-draws and removes its target")
            if not np.isclose(float(anim.lag_ratio), 1.0):
                rec.blockers.append(f"{name} with lag_ratio={float(anim.lag_ratio):g}")
        elif isinstance(anim, Write):
            # Both interpreters recompute Manim's default rather than reading
            # one, so an explicit lag_ratio would be silently ignored.
            children = max(len(anim.mobject.family_members_with_points()), 1)
            if not np.isclose(float(anim.lag_ratio), min(4.0 / children, 0.2)):
                rec.blockers.append(f"{name} with lag_ratio={float(anim.lag_ratio):g}")

    def patched_play(self, *animations, **kwargs):
        run_time = kwargs.get("run_time")
        emitted_before = len(rec.timeline)
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

            animation_blockers(anim)

            # play(rate_func=...) applies to every animation in the call, and
            # Manim sets it on each one -- but through compile_animation_data,
            # which runs inside the real play(), after this. Reading only the
            # animation's own attribute therefore saw the default: a
            # `play(Create(c), rate_func=linear)` exported as an eased `create`
            # with no rate= at all, at tier 1 and with no blocker.
            rate = kwargs.get("rate_func") or getattr(anim, "rate_func", None)
            rate_name = rate.__name__ if rate is not None else "smooth"
            if rate_name not in ("smooth", "linear"):
                rec.blockers.append(f"non-default rate_func: {rate_name}")
            suffix = "" if rate_name == "smooth" else f" rate={rate_name}"

            if isinstance(anim, TransformMatchingAbstractBase):
                # This IS glyph-level matching -- it subclasses AnimationGroup
                # rather than Transform, so it needs its own branch, but it maps
                # onto exactly the morph verb.
                source = rec.declare(anim._panim_source)
                target = rec.declare(anim._panim_target)
                if source and target:
                    rec.timeline.append(f"morph {source} {target} t={duration:g}")
                else:
                    rec.blockers.append(
                        "TransformMatchingTex operands could not be declared"
                    )
            elif isinstance(anim, LaggedStart):
                # A staggered per-child animation over one group. Only the
                # grow family is expressible today; anything else is named in
                # the blocker so the gap stays measured rather than guessed at.
                import numpy as np

                parts = list(anim.animations)
                kinds = sorted({type(a).__name__ for a in parts})
                grows = parts and all(isinstance(a, GrowFromPoint) for a in parts)
                from_centre = grows and all(
                    np.allclose(a.point, a.mobject.get_center(), atol=1e-6)
                    for a in parts
                )
                # LaggedStart's own .mobject is empty: introducer animations
                # are excluded from the group it builds. So assemble the group
                # from the sub-animations' targets, in their animation order.
                from manim import VGroup

                group = VGroup(*[a.mobject for a in parts]) if from_centre else None
                name = rec.declare(group) if group is not None else None
                sizes = instance_partition(group) if name else None
                if name and sizes and len(sizes) == len(parts):
                    rec.timeline.append(
                        f"laggedgrow {name} lag={float(anim.lag_ratio):g} "
                        f"groups={','.join(str(s) for s in sizes)} t={duration:g}"
                    )
                    for part in parts:
                        rec.covered.update(
                            id(sub) for sub in part.mobject.get_family()
                        )
                elif not grows:
                    rec.blockers.append(
                        f"LaggedStart over {', '.join(kinds) or 'nothing'}"
                    )
                elif not from_centre:
                    rec.blockers.append("LaggedStart grows from a point off centre")
                else:
                    rec.blockers.append("LaggedStart group could not be partitioned")
            elif isinstance(anim, Write):
                # Write reveals each glyph in turn. On a text asset that is a
                # lagged per-glyph reveal, not a single partial path.
                name = rec.declare(anim.mobject)
                if not name:
                    rec.blockers.append("Write target could not be declared")
                elif not rec.is_asset(name):
                    # Write reveals an asset one submobject at a time. A
                    # primitive has none to lag, and the interpreter raises
                    # rather than guess -- so this used to export at tier 1 and
                    # then crash the player. A blocker sends it to tier 3, which
                    # draws it correctly, which is what the tiers are for.
                    rec.blockers.append(
                        f"Write on a primitive: {type(anim.mobject).__name__}"
                    )
                else:
                    rec.timeline.append(f"write {name} t={duration:g}")
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
                    # Glyph-level matching: both operands are baked assets, so
                    # match their instances by atlas id -- the shared library
                    # already gives identical glyphs identical ids, which is
                    # exactly the correspondence TransformMatchingTex computes
                    # from TeX structure.
                    rec.timeline.append(
                        f"morph {source} {target} t={duration:g}{suffix}"
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
                elif type(anim.mobject).__name__ == "ValueTracker":
                    # The fundamental limit of program-shipping: a ValueTracker
                    # drives always_redraw closures, so geometry is arbitrary
                    # Python recomputed per frame. It cannot be a verb.
                    rec.blockers.append(
                        "ValueTracker drives always_redraw (arbitrary per-frame Python)"
                    )
                else:
                    # Same missing-else that silently dropped FadeIn. Seven
                    # seconds of this scene vanished with no blocker recorded.
                    rec.blockers.append(
                        f".animate on undeclarable {type(anim.mobject).__name__}"
                    )
            else:
                rec.blockers.append(f"unsupported animation: {type(anim).__name__}")
        # Structural guard. Three separate bugs silently dropped an
        # animation by falling through a branch with no else, each time
        # shifting the whole timeline and rendering the wrong thing. A play()
        # that produced no verb is always a drop, whatever the cause.
        if not state["in_camera_move"] and len(rec.timeline) == emitted_before:
            kinds = ", ".join(type(a).__name__ for a in animations)
            rec.blockers.append(f"play() produced no verb ({kinds})")

        # One play(), several animations: Manim runs them together. Consecutive
        # verbs run them one after another, so the scene played for the sum of
        # their durations and showed them in sequence -- for play(Create(a),
        # Create(b), run_time=2), four seconds of the wrong thing. `par` claims
        # the verbs this call produced and gives them one clock.
        produced = len(rec.timeline) - emitted_before
        if produced > 1:
            spans = [
                run_time if run_time is not None else getattr(anim, "run_time", 1.0)
                for anim in animations
                if not isinstance(anim, Wait)
            ]
            # Manim's play ends when its longest animation does.
            if spans:
                rec.timeline.insert(
                    emitted_before, f"par n={produced} t={max(spans):g}"
                )
        return originals["play"](self, *animations, **kwargs)

    def patched_add(self, *mobjects, **kw):
        # Objects put on stage directly rather than animated in. Missing these
        # produced a program that claimed tier 1 while drawing nothing.
        for mob in mobjects:
            if id(mob) in rec.covered:
                continue
            name = rec.declare(mob)
            if name:
                # Declaring a thing is not the same as it being on stage.
                # Without this, every asset drew from frame 0.
                rec.timeline.append(f"show {name}")
        return originals["add"](self, *mobjects, **kw)

    def patched_remove(self, *mobjects, **kw):
        # Manim takes things off stage as well as putting them on, and until
        # this existed the program had no way to say so. TransformMatchingTex
        # adds its working groups through add() and drops them again in
        # clean_up_from_scene; without the removal they stayed on our stage for
        # the rest of the scene. Three morphs ended with three stale equations
        # drawn over the fourth -- 237% of that frame's ink, under a
        # frame-relative mean of 0.29%, which is why the gate never saw it.
        #
        # Only things already named and declared: Manim removes internal copies
        # (TransformMatchingTex's fade target, for one) that were never on our
        # stage, and declaring one here would invent an asset out of a removal.
        for mob in mobjects:
            name = rec.names.get(id(mob))
            if name and rec.declared(name):
                rec.timeline.append(f"hide {name}")
        return originals["remove"](self, *mobjects, **kw)

    def patched_orientation(self, phi=None, theta=None, **kw):
        parts = []
        if phi is not None:
            parts.append(f"phi={math.degrees(phi):g}")
        if theta is not None:
            parts.append(f"theta={math.degrees(theta):g}")
        # zoom was read off this call and thrown away, and the IR has carried a
        # zoom field all along -- so MolecularStructure's zoom=0.9 exported at
        # tier 1, with no blocker, and drew the whole molecule 1/0.9 = 11%
        # too large in every frame of the scene.
        zoom = kw.get("zoom")
        if zoom is not None:
            parts.append(f"zoom={float(zoom):g}")
        camera_blockers(kw)
        rec.declarations.append("camera " + " ".join(parts))
        return originals["set_orientation"](self, phi=phi, theta=theta, **kw)

    def camera_blockers(kw, animated=False):
        """Name the camera parameters the program cannot carry.

        The interpreters fix gamma, focal distance and frame centre at Manim's
        defaults, so a scene that sets one renders from the wrong camera with
        nothing recorded. `zoom` is expressible as a declaration but not as an
        animation, so an animated one is a blocker too.
        """
        for key in ("gamma", "focal_distance", "frame_center"):
            if kw.get(key) is not None:
                rec.blockers.append(f"camera {key} is not expressible")
        if animated and kw.get("zoom") is not None:
            rec.blockers.append("move_camera animates zoom")

    def patched_move_camera(self, phi=None, theta=None, run_time=3.0, **kw):
        camera_blockers(kw, animated=True)
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
        # Manim can spin about theta, phi or gamma. The `spin` verb means theta
        # in both interpreters, so anything else used to rotate the camera about
        # the wrong axis for the whole scene -- tier 1, no blocker. Blocked
        # rather than implemented: there is no corpus scene spinning about phi,
        # and an unmeasured camera path is worth less than a tier-3 fallback
        # that is measured.
        about = kw.get("about", "theta")
        if about != "theta":
            rec.blockers.append(f"ambient camera rotation about {about}")
        state["spin_rate"] = rate
        return originals["begin_spin"](self, rate=rate, **kw)

    def patched_stop_spin(self, **kw):
        state["spin_rate"] = None
        return originals["stop_spin"](self, **kw)

    Scene.play = patched_play
    Scene.add = patched_add
    Scene.remove = patched_remove
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
        TransformMatchingAbstractBase.__init__ = matching_init
        Scene.play = originals["play"]
        Scene.add = originals["add"]
        Scene.remove = originals["remove"]
        ThreeDScene.move_camera = originals["move_camera"]
        ThreeDScene.set_camera_orientation = originals["set_orientation"]
        ThreeDScene.begin_ambient_camera_rotation = originals["begin_spin"]
        ThreeDScene.stop_ambient_camera_rotation = originals["stop_spin"]

    return rec


# What the decimation is aimed at. A phone's long edge at the top of the range
# the player targets, and a pixel of error there at the tightest zoom the
# program reaches -- so anywhere else in the animation the error is smaller.
# Exported artwork is decimated against these; nothing else is touched.
REFERENCE_WIDTH_PX = 2400
ERROR_PX = 1.0


def program_max_scale(program: str) -> float:
    """The largest magnification the program ever applies to anything.

    Read off the verbs rather than off the interpreter's transforms: those
    compose the atlas's own canonicalisation, which normalises a coastline to a
    unit box and would be read as a 2.9x zoom that no viewer ever sees.

    `xform ... by=` is the vocabulary's only magnifying verb, and it composes,
    so successive ones on the same object multiply. `create`, `write` and the
    grow verbs animate from nothing up to the size the asset was baked at,
    which needs no extra detail. A future verb that magnifies would have to be
    added here; the fidelity harness is what would catch its absence.
    """
    cumulative: dict[str, float] = {}
    largest = 1.0
    for line in program.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] != "xform":
            continue
        factor = 1.0
        for token in parts[2:]:
            if token.startswith("by="):
                factor = float(token[3:])
        name = parts[1]
        cumulative[name] = cumulative.get(name, 1.0) * factor
        largest = max(largest, cumulative[name])
    return largest


def decimate_assets(rec: Recorder, program: str) -> dict:
    """Re-bake the program's imported artwork at the detail a screen can show.

    Runs after recording because the tolerance depends on the whole program:
    the same coastline needs three times the detail in a scene that zooms into
    it as in one that does not.
    """
    from dsl.library import export_standalone_asset
    from exporter.simplify import simplify_shape, tolerance_for

    if not rec.snapshots:
        return {}

    scale = program_max_scale(program)
    tolerance = tolerance_for(REFERENCE_WIDTH_PX, ERROR_PX, scale)

    # Counted over the snapshot on both sides, not over the baked atlas: the
    # atlas deduplicates, so reading the "after" out of the file reported a
    # molecule's 11,760 drawn curves shrinking to the 60 distinct ones it is
    # built from, which is not a saving and not what the device draws.
    before = after = 0
    for digest, snapshot in rec.snapshots.items():
        for points, *_ in snapshot:
            before += len(points) // 4
            after += len(simplify_shape(points, tolerance)) // 4
        asset = Path("dsl/generated/assets") / f"{digest}.panm"
        rec.assets[digest] = export_standalone_asset(snapshot, asset, tolerance)

    return {
        "reference_width_px": REFERENCE_WIDTH_PX,
        "error_px": ERROR_PX,
        "max_scale": round(scale, 3),
        "tolerance": round(tolerance, 6),
        "curves_before": before,
        "curves_after": after,
    }


def emit(rec: Recorder, mode: str, fps: int = 30) -> str:
    lines = [f"scene {mode} fps={fps}"] + rec.declarations + rec.timeline
    return "\n".join(lines) + "\n"


def main():
    scene_file, scene_class = sys.argv[1:3]
    write = "--write" in sys.argv[3:]
    rec = record_scene(scene_file, scene_class)

    mode = "3d" if any(d.startswith(("surface", "camera")) for d in rec.declarations) else "2d"
    program = emit(rec, mode)
    blockers = list(dict.fromkeys(rec.blockers))

    print(f"=== {scene_class} ===")
    if blockers:
        print("TIER 3 (falls back to sampled IR)")
        for blocker in blockers:
            print(f"  blocked by: {blocker}")
    else:
        print(f"TIER 1 ({len(program)} bytes)")
        print(program)

    if write:
        # The exporter is the only thing that knows whether a program is
        # faithful, so it records the verdict rather than leaving it to be
        # inferred from which files exist. A stale program from a run that
        # later grew a blocker silently shipped a scene missing 2.5 seconds.
        import json

        out = Path("dsl/generated")
        out.mkdir(parents=True, exist_ok=True)
        target = out / f"{scene_class}.panim"
        verdict = {
            "scene": scene_class,
            "tier": 3 if blockers else 1,
            "blockers": blockers,
            "program_bytes": 0 if blockers else len(program),
        }
        if blockers:
            target.unlink(missing_ok=True)
        else:
            target.write_text(program)
            simplified = decimate_assets(rec, program)
            if simplified:
                verdict["simplified"] = simplified
                print(
                    f"decimated artwork: {simplified['curves_before']} -> "
                    f"{simplified['curves_after']} curves "
                    f"({simplified['error_px']}px at {simplified['max_scale']}x)"
                )
        (out / f"{scene_class}.tier.json").write_text(
            json.dumps(verdict, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
