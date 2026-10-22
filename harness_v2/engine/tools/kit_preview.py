"""Preview a piece of the kit (or any Manim code) before using it: the code runs as the body of a KitScene's
construct() in the chosen look, rendered small; the last frame comes back, and a sheet of frames when it moves.

    .venv/bin/python harness_v2/engine/tools/kit_preview.py <workspace> <code.py> <out_dir> [look] [width]

<code.py> is the body only (no class, no def), with `self` the scene:
    m = Map("east asia"); self.add(m); self.play(m.shade("Japan"))

Runs in the workspace (its assets/ are there) with no narration. Prints JSON as the last line:
    {"ok": true, "still": <png>, "sheet": <png or null>, "seconds": <the animation's length>}
or {"ok": false, "error": "..."}.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
AGENT = ENGINE / "agent"
SECRET = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)


def main(argv: list[str]) -> dict:
    ws, code_file, out_dir = Path(argv[0]).resolve(), Path(argv[1]).resolve(), Path(argv[2]).resolve()
    look = argv[3] if len(argv) > 3 and argv[3] else "vox"
    width = int(argv[4]) if len(argv) > 4 else 960
    out_dir.mkdir(parents=True, exist_ok=True)
    body = code_file.read_text(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="kit_preview_", dir=out_dir))
    scene = tmp / "_kit_preview.py"
    scene.write_text("from kit import *\n\n\nclass Preview(KitScene):\n"
                     f"    look = {look!r}\n\n    def construct(self):\n"
                     + textwrap.indent(body.rstrip() + "\n", " " * 8)
                     + "        self.wait(1 / 15)\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not SECRET.search(k)}
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(ws), str(AGENT), env.get("PYTHONPATH", "")) if p)
    env["PANIM_NARRATION_DIR"] = str(tmp)            # no timing there: a silent scene
    height = width * 9 // 16
    cmd = [sys.executable, "-m", "manim", "render", "--resolution", f"{width},{height}", "--frame_rate", "15",
           "--media_dir", str(tmp / "media"), "--disable_caching", "-v", "WARNING", str(scene), "Preview"]
    r = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True,
                       timeout=int(os.environ.get("PANIM_KIT_PREVIEW_SECONDS", "240")))
    if r.returncode != 0:
        err = (r.stderr or r.stdout).strip()
        # The useful end of a traceback, with the scene's line numbers turned back into the snippet's.
        err = re.sub(r'File ".*?_kit_preview\.py", line (\d+)',
                     lambda m: f"your code, line {max(1, int(m.group(1)) - 7)}", err)
        return {"ok": False, "error": err[-2500:]}
    videos = sorted((tmp / "media").rglob("Preview.mp4"))
    images = sorted((tmp / "media").rglob("Preview*.png"))
    still = out_dir / f"{tmp.name}-still.png"
    sheet = None
    seconds = 0.0
    if videos:
        video = videos[0]
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(video)], capture_output=True, text=True)
        seconds = float(probe.stdout.strip() or 0)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.4", "-i", str(video), "-update", "1",
                        str(still)], check=False)
        if seconds > 0.3:
            sheet = out_dir / f"{tmp.name}-sheet.png"
            make_sheet(video, seconds, sheet, tmp)
    elif images:
        images[-1].replace(still)
    if not still.exists():
        return {"ok": False, "error": "nothing was drawn"}
    return {"ok": True, "still": str(still), "sheet": str(sheet) if sheet else None, "seconds": round(seconds, 2)}


def make_sheet(video: Path, seconds: float, out: Path, tmp: Path, n: int = 6) -> None:
    from PIL import Image, ImageDraw

    frames = []
    for i in range(n):
        t = seconds * (i + 0.5) / n
        f = tmp / f"f{i}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=480:-1", str(f)], check=False)
        if f.exists():
            frames.append((t, Image.open(f).convert("RGB")))
    if not frames:
        return
    w, h = frames[0][1].size
    sheet = Image.new("RGB", (w * 3, h * ((len(frames) + 2) // 3)), "#111")
    for i, (t, im) in enumerate(frames):
        x, y = (i % 3) * w, (i // 3) * h
        sheet.paste(im, (x, y))
        ImageDraw.Draw(sheet).text((x + 6, y + 4), f"{t:.1f}s", fill="#ff3")
    sheet.save(out)


if __name__ == "__main__":
    try:
        print(json.dumps(main(sys.argv[1:])))
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "the preview took too long"}))
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}))
