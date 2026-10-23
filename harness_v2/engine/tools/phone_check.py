"""How the phone draws an exported scene, beside what Manim drew: frames and how far apart they are.

The program the exporter wrote is played by the repo's own interpreter (dsl/interpret.py, the phone's semantics)
and drawn by the reference renderer (exporter/reference_render.py, the oracle the Kotlin and Swift players are held
to). Each asked time is drawn from it and taken from the Manim video at the same time, and the two are compared:
the mean difference (0-255 per channel) and the share of pixels that differ by more than 48. A frame over the limit
is one the phone would show differently from Manim.

Usage:
    python harness_v2/engine/tools/phone_check.py <build_dir> <SceneClass> <video.mp4|-> <out_dir> <t> [<t> ...]

Prints one JSON object: {"frames": [{"t", "phone", "manim", "mean", "differ", "ok"}], "ok", "seconds"}. With `-`
for the video, only the phone's frames are drawn. A time `T@P` compares the video at T with the program at P (the
two clocks lined up by the caller, as tools/chapter_qa.py does by where each line's voice starts). `--slack N`: a
frame that differs is compared again with the program's frames up to N either side, and the closest is judged.
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


def check(build_dir: Path, scene_class: str, video: Path | None, out_dir: Path, times: list[float],
          slack: int = 0) -> dict:
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
        # A time, or (the video's time, the program's): the program's clock can run a little apart from the video's
        # over a long scene (verbs run whole frames), and a check lines the two up by where each line's voice starts.
        t, p = (t, t) if not isinstance(t, (tuple, list)) else t
        index = max(0, min(count - 1, int(round(p * ir.fps))))
        at = max(0, int(round(t * ir.fps)))
        phone = render_frame(ir, index, WIDTH, HEIGHT)
        name = f"phone_{t:07.2f}.png"
        Image.fromarray(phone).save(out_dir / name)
        row = {"t": t, "phone": str(out_dir / name), **({"program": round(p, 3)} if p != t else {})}
        if video is not None:
            manim = _manim_frame(video, at, ir.fps)
            if manim is not None:
                mname = f"manim_{t:07.2f}.png"
                Image.fromarray(manim).save(out_dir / mname)
                def judged(frame):
                    delta = np.abs(frame.astype(np.int16) - manim.astype(np.int16))
                    return round(float(delta.mean()), 2), round(float((delta.max(axis=2) > DIFFER).mean()), 4)

                mean, differ = judged(phone)
                # `slack`: the program's frames this many either side may stand in, when the two clocks are lined up
                # only to within a frame or two (a fast wipe is a different picture two frames later).
                for k in [d for step in range(1, slack + 1) for d in (step, -step)]:
                    if mean <= MEAN_LIMIT and differ <= SHARE_LIMIT:
                        break
                    near = index + k
                    if 0 <= near < count:
                        frame = render_frame(ir, near, WIDTH, HEIGHT)
                        m2, d2 = judged(frame)
                        if (m2, d2) < (mean, differ):
                            mean, differ, phone = m2, d2, frame
                            row["shifted"] = k
                            Image.fromarray(phone).save(out_dir / name)
                row.update(manim=str(out_dir / mname), mean=mean, differ=differ)
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
    rest = sys.argv[5:]
    slack = 0
    if "--slack" in rest:
        at = rest.index("--slack")
        slack = int(rest[at + 1])
        rest = rest[:at] + rest[at + 2:]
    times = [tuple(float(x) for x in t.split("@")) if "@" in t else float(t) for t in rest]
    result = check(Path(build_dir), scene_class, None if video == "-" else Path(video), Path(out_dir), times, slack)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
