"""Measure what an IR exporter could extract from a Manim scene.

Hooks CairoRenderer.update_frame, which Manim calls once per rendered frame with
the live scene, and walks the Mobject tree recording Bezier geometry. Answers
three questions the map depends on:

  1. Is per-frame vector geometry extractable at all, and via public API?
  2. How much geometry is there per frame (path and point counts)?
  3. What fraction MORPHS between frames versus staying static?

(3) is the load-bearing one. Skia caches paths but re-tessellates any path whose
points changed, so the static/morphing split drives both renderer cost and IR
size: static geometry is stored once, morphing geometry costs bytes every frame.

Usage:
    python tools/probe_scene_geometry.py <scene_file.py> <SceneClass> [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BYTES_PER_POINT = 3 * 4  # x, y, z as float32


def collect(scene):
    """Snapshot every point-bearing mobject in the scene as {id: (hash, n_points)}."""
    out = {}
    for mob in scene.mobjects:
        for sub in mob.get_family():
            pts = getattr(sub, "points", None)
            if pts is None or len(pts) == 0:
                continue
            arr = np.asarray(pts, dtype=np.float64)
            out[id(sub)] = (hash(arr.tobytes()), len(arr))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_file")
    ap.add_argument("scene_class")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    from manim import config, tempconfig
    from manim.renderer.cairo_renderer import CairoRenderer

    frames: list[dict] = []
    original = CairoRenderer.update_frame

    def patched(self, scene, *a, **kw):
        snap = collect(scene)
        prev = frames[-1]["snap"] if frames else {}
        static_pts = morph_pts = new_pts = 0
        for key, (h, n) in snap.items():
            if key not in prev:
                new_pts += n
            elif prev[key][0] == h:
                static_pts += n
            else:
                morph_pts += n
        frames.append(
            {
                "snap": snap,
                "mobjects": len(snap),
                "points": sum(n for _, n in snap.values()),
                "static_points": static_pts,
                "morph_points": morph_pts,
                "new_points": new_pts,
            }
        )
        return original(self, scene, *a, **kw)

    CairoRenderer.update_frame = patched

    path = Path(args.scene_file).resolve()
    sys.path.insert(0, str(path.parent))
    module = __import__(path.stem)
    scene_cls = getattr(module, args.scene_class)

    with tempconfig(
        {
            "quality": "medium_quality",
            "write_to_movie": False,
            "verbosity": "ERROR",
            "progress_bar": "none",
        }
    ):
        scene_cls().render()

    CairoRenderer.update_frame = original

    if not frames:
        print("No frames captured.")
        return

    n = len(frames)
    total_pts = [f["points"] for f in frames]
    morph = [f["morph_points"] for f in frames]
    static = [f["static_points"] for f in frames]

    # Naive IR: every frame stores all its geometry.
    naive = sum(total_pts) * BYTES_PER_POINT
    # Cached IR: static geometry stored once, only morphing geometry per frame.
    cached = (sum(morph) + sum(f["new_points"] for f in frames)) * BYTES_PER_POINT

    fps = 30
    report = {
        "scene": args.scene_class,
        "frames": n,
        "duration_s": round(n / fps, 2),
        "mobjects_per_frame_max": max(f["mobjects"] for f in frames),
        "points_per_frame_mean": round(float(np.mean(total_pts)), 1),
        "points_per_frame_max": int(max(total_pts)),
        "morphing_points_per_frame_mean": round(float(np.mean(morph)), 1),
        "morphing_fraction": round(sum(morph) / max(sum(total_pts), 1), 4),
        "ir_naive_bytes": naive,
        "ir_static_cached_bytes": cached,
        "ir_cached_saving_x": round(naive / max(cached, 1), 1),
    }

    width = max(len(k) for k in report)
    for k, v in report.items():
        print(f"{k:<{width}}  {v}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
