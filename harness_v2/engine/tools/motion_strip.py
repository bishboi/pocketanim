"""Frames of a rendered video laid out as a contact sheet, each stamped with its time: how a motion plays, seen at
a glance (the motion engine's checks: frames are compared against the references in harness_v2/sample).

    python harness_v2/engine/tools/motion_strip.py video.mp4 sheet.png [--every 0.5] [--from 0] [--to 20] [--cols 6]
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def frames(video: str, every: float, start: float, end: float | None, out_dir: Path) -> list[tuple[float, Path]]:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                           capture_output=True, text=True)
    duration = float(probe.stdout.strip() or 0)
    end = min(end if end is not None else duration, duration)
    out = []
    t = start
    k = 0
    while t <= end + 1e-6:
        target = out_dir / f"f{k:04d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", str(target)],
                       check=False)
        if target.exists():
            out.append((t, target))
        t += every
        k += 1
    return out


def sheet(shots: list[tuple[float, Path]], target: str, cols: int, width: int = 480) -> None:
    from PIL import Image, ImageDraw

    if not shots:
        raise SystemExit("no frames")
    first = Image.open(shots[0][1])
    h = int(first.height * width / first.width)
    rows = (len(shots) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * width, rows * (h + 22)), "white")
    draw = ImageDraw.Draw(canvas)
    for i, (t, path) in enumerate(shots):
        img = Image.open(path).convert("RGB").resize((width, h))
        x, y = (i % cols) * width, (i // cols) * (h + 22)
        canvas.paste(img, (x, y))
        draw.text((x + 6, y + h + 4), f"{t:.1f}s", fill="black")
    canvas.save(target)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--every", type=float, default=0.5)
    ap.add_argument("--from", dest="start", type=float, default=0.0)
    ap.add_argument("--to", dest="end", type=float, default=None)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--width", type=int, default=480)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        shots = frames(args.video, args.every, args.start, args.end, Path(tmp))
        sheet(shots, args.out, args.cols, args.width)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
