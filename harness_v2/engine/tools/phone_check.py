"""How the phone draws an exported scene, beside what Manim drew: frames and how far apart they are.

The program the exporter wrote is played by the repo's own interpreter (dsl/interpret.py, the phone's semantics)
and drawn by the reference renderer (exporter/reference_render.py, the oracle the Kotlin and Swift players are held
to). Each asked time is drawn from it and taken from the Manim video at the same time, and the two are compared:
the mean difference (0-255 per channel) and the share of pixels that differ by more than 48. A frame over the limit
is one the phone would show differently from Manim.

Usage:
    python harness_v2/engine/tools/phone_check.py <build_dir> <SceneClass> <video.mp4|-> <out_dir> <t> [<t> ...]

Prints one JSON object: {"frames": [{"t", "phone", "manim", "mean", "differ", "ok"}], "ok", "seconds"}. With `-`
for the video, only the phone's frames are drawn.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

WIDTH, HEIGHT = 960, 540
# A frame differs when more than this share of its pixels differs by more than DIFFER (antialiasing and video
# compression stay well under both).
MEAN_LIMIT = 12.0
SHARE_LIMIT = 0.04
DIFFER = 48


def _manim_frame(video: Path, index: int, fps: int):
    """The video's frame `index`: ffmpeg starts at the first frame at or after the time asked, so it is asked for
    half a frame early (a frame's own time, rounded in the file, can fall just before it)."""
    import numpy as np

    t = max(0.0, (index - 0.5) / fps)

    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"scale={WIDTH}:{HEIGHT}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout
    if len(raw) < WIDTH * HEIGHT * 3:
        return None
    return np.frombuffer(raw[:WIDTH * HEIGHT * 3], dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)


def check(build_dir: Path, scene_class: str, video: Path | None, out_dir: Path, times: list[float]) -> dict:
    import numpy as np
    from PIL import Image

    from dsl.interpret import load_program
    from exporter.reference_render import render_frame

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    video = video.resolve() if video else None
    previous = Path.cwd()
    os.chdir(build_dir)
    try:
        ir = load_program(f"dsl/generated/{scene_class}.panim")
    finally:
        os.chdir(previous)
    count = len(ir.records)
    frames = []
    for t in times:
        index = max(0, min(count - 1, int(round(t * ir.fps))))
        phone = render_frame(ir, index, WIDTH, HEIGHT)
        name = f"phone_{t:07.2f}.png"
        Image.fromarray(phone).save(out_dir / name)
        row = {"t": t, "phone": str(out_dir / name)}
        if video is not None:
            manim = _manim_frame(video, index, ir.fps)
            if manim is not None:
                mname = f"manim_{t:07.2f}.png"
                Image.fromarray(manim).save(out_dir / mname)
                delta = np.abs(phone.astype(np.int16) - manim.astype(np.int16))
                row.update(manim=str(out_dir / mname), mean=round(float(delta.mean()), 2),
                           differ=round(float((delta.max(axis=2) > DIFFER).mean()), 4))
                row["ok"] = row["mean"] <= MEAN_LIMIT and row["differ"] <= SHARE_LIMIT
        frames.append(row)
    judged = [f for f in frames if "ok" in f]
    return {"frames": frames, "ok": all(f["ok"] for f in judged) if judged else None,
            "seconds": round(count / ir.fps, 2)}


def main() -> int:
    if len(sys.argv) < 6:
        print(__doc__.strip().splitlines()[-4], file=sys.stderr)
        return 2
    build_dir, scene_class, video, out_dir = sys.argv[1:5]
    times = [float(t) for t in sys.argv[5:]]
    result = check(Path(build_dir), scene_class, None if video == "-" else Path(video), Path(out_dir), times)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
