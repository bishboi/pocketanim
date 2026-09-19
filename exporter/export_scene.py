"""Export a Manim scene to the pocketanim IR.

Hooks CairoRenderer.update_frame, which Manim calls once per frame with the
live scene, walks the Mobject tree, and resolves every point-bearing submobject
into an atlas reference plus an affine transform.

Snapshots are emitted at animation boundaries and whenever the set of visible
objects changes; other frames emit only instances whose values changed.

Usage:
    python -m exporter.export_scene <scene_file.py> <SceneClass> [-o out.panm]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .ir import REC_KEYFRAME, REC_SNAPSHOT, SHADE_IN_3D, Atlas, Instance, serialise


def rgba(color, opacity) -> tuple[int, int, int, int]:
    try:
        r, g, b = color.to_rgb()
    except AttributeError:
        r = g = b = 0.0
    return (
        int(np.clip(r, 0, 1) * 255),
        int(np.clip(g, 0, 1) * 255),
        int(np.clip(b, 0, 1) * 255),
        int(np.clip(float(opacity), 0, 1) * 255),
    )


def unit_normal(mob, points: np.ndarray) -> np.ndarray:
    """Surface normal for shading.

    Prefers Manim's own value, but some mobjects (ThreeDAxes' shading helpers)
    override get_unit_normal with an incompatible signature, so fall back to
    deriving it from the geometry.
    """
    try:
        value = np.asarray(mob.get_unit_normal(), dtype=np.float64).reshape(3)
        if np.isfinite(value).all() and np.linalg.norm(value) > 1e-9:
            return value
    except (TypeError, ValueError, AttributeError):
        pass

    # Plane fit by SVD. Its sign is arbitrary, which would band a surface with
    # alternating light and dark faces, so orient every normal into the same
    # hemisphere. Winding-order cross products were tried and are worse here:
    # these are Bezier control points, not polygon vertices.
    centred = points - points.mean(axis=0)
    try:
        _, _, vh = np.linalg.svd(centred, full_matrices=False)
        normal = vh[2]
    except np.linalg.LinAlgError:
        return np.array([0.0, 0.0, 1.0])

    return -normal if normal[2] < 0 else normal


def _call(mob, name, fallback):
    """Prefer Manim's getter over the raw attribute.

    The scalar attributes can be stale: Manim keeps the authoritative values in
    fill_rgbas/stroke_rgbas, and `mob.fill_opacity` reads 0 for Text and Code
    glyphs that render fully opaque. Reading the attribute silently produced
    invisible text.
    """
    getter = getattr(mob, name, None)
    if callable(getter):
        try:
            value = getter()
            if value is not None:
                return value
        except (TypeError, ValueError, IndexError, AttributeError):
            pass
    return fallback


def read_style(mob):
    return (
        rgba(
            _call(mob, "get_fill_color", getattr(mob, "fill_color", None)),
            _call(mob, "get_fill_opacity", getattr(mob, "fill_opacity", 0) or 0),
        ),
        rgba(
            _call(mob, "get_stroke_color", getattr(mob, "stroke_color", None)),
            _call(mob, "get_stroke_opacity", getattr(mob, "stroke_opacity", 0) or 0),
        ),
        float(_call(mob, "get_stroke_width", getattr(mob, "stroke_width", 0) or 0) or 0),
    )


class Exporter:
    def __init__(self, keyframe_stride: int = 1):
        self.atlas = Atlas()
        self.records: list[tuple[int, dict[int, Instance]]] = []
        self.slots: dict[int, int] = {}          # id(mob) -> slot
        self.last_atlas: dict[int, int] = {}     # slot -> atlas id
        self.previous: dict[int, Instance] = {}
        self.force_snapshot = True
        self.snapshots = 0
        # Sample instance updates every Nth frame; the device interpolates
        # between them. This is the quality dial -- higher stride trades
        # smoothness for size, and costs nothing in geometry.
        self.keyframe_stride = max(1, keyframe_stride)
        self.frame_index = -1
        self.cameras: list[np.ndarray] = []

    @staticmethod
    def read_camera(scene) -> np.ndarray | None:
        """Capture ThreeDCamera state as 14 floats, or None for a 2D scene."""
        camera = getattr(scene, "camera", None)
        if camera is None or not hasattr(camera, "get_rotation_matrix"):
            return None
        # `rotation_matrix` is a cached field that Manim only refreshes inside
        # capture_mobjects, i.e. during the render. Reading it here -- before
        # the render -- returned the *previous* frame's orientation, so the
        # camera track lagged its own geometry by one frame. The error was
        # invisible wherever the camera was momentarily still and grew with
        # camera speed, which is why it looked like a projection bug.
        generate = getattr(camera, "generate_rotation_matrix", None)
        rotation = generate() if generate else camera.get_rotation_matrix()
        return np.concatenate(
            [
                np.asarray(camera.frame_center, dtype=np.float64).reshape(3),
                [float(camera.get_focal_distance()), float(camera.get_zoom())],
                np.asarray(rotation, dtype=np.float64).reshape(9),
                np.asarray(camera.light_source.get_location(), dtype=np.float64).reshape(3),
            ]
        )

    def hold(self, camera) -> None:
        """Repeat the previous frame once.

        Manim writes a frozen `wait` without re-rendering, so those frames
        arrive as a gap in playback time rather than as calls. Without filling
        them the IR is shorter than the scene and every later frame plays early.
        """
        self.records.append((REC_KEYFRAME, {}))
        if camera is not None:
            self.cameras.append(self.cameras[-1] if self.cameras else camera)
        self.frame_index += 1

    def pad_to(self, target: int, camera=None) -> None:
        while self.frame_index + 1 < target:
            self.hold(camera)

    def capture(self, scene, frame: int | None = None):
        camera = self.read_camera(scene)

        # Index by playback frame, not by call. Recording one entry per call
        # made the IR shorter than the scene and mistimed everything after the
        # first animation; a frozen `wait` produces no call at all, so those
        # frames exist only as elapsed time and have to be filled in.
        if frame is not None:
            if frame <= self.frame_index:
                return
            self.pad_to(frame, camera)

        if camera is not None:
            self.cameras.append(camera)
        current: dict[int, Instance] = {}

        for mob in scene.mobjects:
            for sub in mob.get_family():
                pts = getattr(sub, "points", None)
                if pts is None or len(pts) < 4:
                    continue
                points = np.asarray(pts, dtype=np.float64)

                slot = self.slots.setdefault(id(sub), len(self.slots))
                atlas_id, transform = self.atlas.resolve(points, self.last_atlas.get(slot))
                self.last_atlas[slot] = atlas_id

                fill, stroke, width = read_style(sub)
                shaded = bool(getattr(sub, "shade_in_3d", False))
                flags = SHADE_IN_3D if shaded else 0
                normal = unit_normal(sub, points) if shaded else None
                current[slot] = Instance(atlas_id, transform, fill, stroke, width, flags, normal)

        self.frame_index += 1
        set_changed = current.keys() != self.previous.keys()

        if self.force_snapshot or set_changed:
            self.records.append((REC_SNAPSHOT, current))
            self.snapshots += 1
            self.force_snapshot = False
            self.previous = current
            return

        if self.frame_index % self.keyframe_stride:
            self.records.append((REC_KEYFRAME, {}))
            return  # not a keyframe: leave `previous` alone so deltas accumulate

        changed = {
            slot: inst
            for slot, inst in current.items()
            if slot not in self.previous or inst.key() != self.previous[slot].key()
        }
        self.records.append((REC_KEYFRAME, changed))
        self.previous = current


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_file")
    ap.add_argument("scene_class")
    ap.add_argument("-o", "--out")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument(
        "--keyframe-stride",
        type=int,
        default=1,
        help="emit instance updates every Nth frame (3 = 10fps at 30fps source)",
    )
    args = ap.parse_args()

    from manim import Scene, tempconfig
    from manim.renderer.cairo_renderer import CairoRenderer

    exporter = Exporter(keyframe_stride=args.keyframe_stride)
    original_update = CairoRenderer.update_frame
    original_play = Scene.play

    renderer_state = {"renderer": None, "fps": 30}

    in_static = {"depth": 0}
    original_static = CairoRenderer.save_static_frame_data

    def patched_static(self, scene, static_mobjects):
        in_static["depth"] += 1
        try:
            return original_static(self, scene, static_mobjects)
        finally:
            in_static["depth"] -= 1

    def patched_update(self, scene, *a, **kw):
        # Manim renders the static layer through update_frame too, to cache it.
        # That is a partial render -- only the static mobjects, and no frame is
        # written for it -- so it must not be counted as a frame. Both call
        # sites pass a mobject list, so the static one is detected by wrapping
        # save_static_frame_data rather than by inspecting arguments.
        if in_static["depth"]:
            return original_update(self, scene, *a, **kw)

        renderer_state["renderer"] = self
        renderer_state["fps"] = int(getattr(self.camera, "frame_rate", 30) or 30)
        exporter.capture(scene, round(float(self.time) * renderer_state["fps"]))
        return original_update(self, scene, *a, **kw)

    def patched_play(self, *a, **kw):
        exporter.force_snapshot = True  # animation boundary
        return original_play(self, *a, **kw)

    CairoRenderer.update_frame = patched_update
    CairoRenderer.save_static_frame_data = patched_static
    Scene.play = patched_play

    path = Path(args.scene_file).resolve()
    sys.path.insert(0, str(path.parent))
    module = __import__(path.stem)
    scene_cls = getattr(module, args.scene_class)

    try:
        with tempconfig(
            {
                "quality": "medium_quality",
                "write_to_movie": False,
                "verbosity": "ERROR",
                "progress_bar": "none",
            }
        ):
            scene_cls().render()
    finally:
        CairoRenderer.update_frame = original_update
        CairoRenderer.save_static_frame_data = original_static
        Scene.play = original_play

    # A trailing static wait produces no render at all, so the last frames of
    # the scene exist only as elapsed time. Without this the IR ends early and
    # the closing hold is simply missing.
    renderer = renderer_state["renderer"]
    if renderer is not None:
        exporter.pad_to(
            round(float(renderer.time) * renderer_state["fps"]),
            exporter.cameras[-1] if exporter.cameras else None,
        )

    blob = serialise(exporter.atlas, exporter.records, fps=30,
                     cameras=exporter.cameras or None)

    atlas_points = sum(len(s) for s in exporter.atlas.shapes)
    total_instances = sum(len(r[1]) for r in exporter.records)
    lookups = exporter.atlas.hits + exporter.atlas.misses

    report = {
        "scene": args.scene_class,
        "frames": len(exporter.records),
        "snapshots": exporter.snapshots,
        "atlas_shapes": len(exporter.atlas.shapes),
        "atlas_points": atlas_points,
        "atlas_hit_rate": round(exporter.atlas.hits / max(lookups, 1), 4),
        "affine_reuses": exporter.atlas.affine_hits,
        "instances_emitted": total_instances,
        "ir_bytes": len(blob),
        "keyframe_stride": args.keyframe_stride,
    }

    width = max(len(k) for k in report)
    for k, v in report.items():
        print(f"{k:<{width}}  {v}")

    if args.out:
        Path(args.out).write_bytes(blob)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
