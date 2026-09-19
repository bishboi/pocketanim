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

from .ir import REC_KEYFRAME, REC_SNAPSHOT, Atlas, Instance, serialise


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


def read_style(mob):
    return (
        rgba(getattr(mob, "fill_color", None), getattr(mob, "fill_opacity", 0) or 0),
        rgba(getattr(mob, "stroke_color", None), getattr(mob, "stroke_opacity", 0) or 0),
        float(getattr(mob, "stroke_width", 0) or 0),
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

    def capture(self, scene):
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
                current[slot] = Instance(atlas_id, transform, fill, stroke, width)

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

    def patched_update(self, scene, *a, **kw):
        exporter.capture(scene)
        return original_update(self, scene, *a, **kw)

    def patched_play(self, *a, **kw):
        exporter.force_snapshot = True  # animation boundary
        return original_play(self, *a, **kw)

    CairoRenderer.update_frame = patched_update
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
        Scene.play = original_play

    blob = serialise(exporter.atlas, exporter.records, fps=30)

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
