"""The video agent's tools that need Python: render its scene, see frames of it, and play it as the phone does.

    agent_tools.py render <workspace> <file.py> <Scene> <draft|final> [from_s to_s]
    agent_tools.py frames <video.mp4> <out_dir> <offset_s> <width> <t> [<t> ...]
    agent_tools.py sheet  <video.mp4> <out.png> [every_seconds [offset_s]]
    agent_tools.py phone  <workspace> <file.py> <Scene> <out_dir> <video.mp4|-> [samples]

Each prints one JSON object as its last line.

- render: Manim renders the scene in the workspace at 30 fps (the phone's rate, so its clock is the program's):
  draft 854x480, final 1280x720; with from/to only that stretch of the chapter (the plays before it run undrawn).
  A small sheet of the render comes with it. {"ok", "video", "seconds", "offset", "section", "sheet", "sheet_times",
  "audit", "error"}.
- frames: the video's frames at those times (on the chapter's clock; the video starts at offset), as PNGs. {"ok", "frames": [{"t", "file"}]}.
- sheet: one picture of frames every N seconds (default: about 16 frames over the video), each stamped with its
  time. {"ok", "file", "times"}.
- phone: the scene exported as the phone plays it (tools/export_scene.py: faithful, every play as Manim draws it),
  the web player's geometry made (tools/scene_ir.py), and the phone's frames compared with the video's at `samples`
  times spread over it (tools/phone_check.py). {"ok", "tier", "blockers", "seconds", "bytes", "check": {...},
  "worst": {"t", "phone", "manim"}, "narration"}.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ENGINE = TOOLS.parent
AGENT = ENGINE / "agent"
PY = sys.executable
FPS = 30


def _tail(text: str, lines: int = 18) -> str:
    rows = [r.rstrip() for r in text.replace("\x1b", "").splitlines() if r.strip()]
    at = next((i for i, r in enumerate(rows) if r.startswith("Traceback")), None)
    rows = rows[at:] if at is not None else rows
    return "\n".join(rows[-lines:])[-2400:]


SECRET = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH", re.I)


def _env(workspace: Path) -> dict:
    """The environment the agent's scene runs in: no keys or secrets (what it prints goes back to the model)."""
    env = {k: v for k, v in os.environ.items() if not SECRET.search(k)}
    env.update(PANIM_NARRATION_DIR=str(workspace), PYTHONDONTWRITEBYTECODE="1")
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(workspace), str(AGENT), env.get("PYTHONPATH", "")) if p)
    return env


def _seconds(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True)
    try:
        return round(float(out.stdout.strip()), 3)
    except ValueError:
        return 0.0


def render(workspace: Path, file: str, scene: str, quality: str, start: float = 0.0, end: float = 0.0) -> dict:
    size = "1280,720" if quality == "final" else "854,480"
    # PANIM_RENDER_NAME: where it goes (renders/<name>.mp4), so a render made ahead does not overwrite the one in use.
    name = os.environ.get("PANIM_RENDER_NAME") or quality
    media = workspace / "renders" / name
    shutil.rmtree(media, ignore_errors=True)
    audit = workspace / "audit.json"
    audit.unlink(missing_ok=True)
    window = workspace / ".render_window"
    window.unlink(missing_ok=True)
    env = _env(workspace)
    if start or end:
        env.update(PANIM_RENDER_FROM=f"{start:g}" if start else "", PANIM_RENDER_TO=f"{end:g}" if end else "")
    # Manim run with the audit installed first (agent/audit.py): what the render measures about itself.
    runner = "import sys, audit; audit.install(); from manim.__main__ import main; sys.argv = ['manim'] + sys.argv[1:]; main()"
    proc = subprocess.run(
        [PY, "-c", runner, "render", file, scene, "--fps", str(FPS), "-r", size, "--disable_caching",
         "--media_dir", str(media), "--progress_bar", "none", "-v", "WARNING"],
        cwd=workspace, env=env, capture_output=True, text=True, timeout=int(os.environ.get("PANIM_AGENT_RENDER_SECONDS", "1500")))
    videos = [p for p in media.rglob("*.mp4") if "partial_movie_files" not in p.parts]
    if proc.returncode != 0 or not videos:
        return {"ok": False, "error": _tail(proc.stderr + proc.stdout) or "the render made no video"}
    section = bool(start or end)
    video = workspace / "renders" / (f"{name}-section.mp4" if section else f"{name}.mp4")
    shutil.copyfile(videos[0], video)
    measured = json.loads(audit.read_text()) if audit.is_file() and not section else None
    # Where the video starts on the chapter's clock (a section render starts at its window).
    offset = float(window.read_text()) if section and window.is_file() else 0.0
    # A sheet of it comes with every render: what the agent looks at first, without a turn of its own.
    seconds = _seconds(video)
    shown = sheet(video, workspace / "renders" / f"sheet-{int(time.time() * 1000)}.png",
                  max(0.5, seconds / 12), offset=offset, tile=(320, 180))
    return {"ok": True, "video": str(video), "seconds": seconds, "audit": measured, "offset": offset, "section": section,
            "sheet": shown.get("file"), "sheet_times": shown.get("times"),
            "warnings": _tail(proc.stderr, 6) if proc.stderr.strip() else ""}


def _frame(video: Path, t: float, out: Path, width: int = 960) -> bool:
    proc = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
                           "-frames:v", "1", "-vf", f"scale={width}:-2", str(out)], capture_output=True)
    return proc.returncode == 0 and out.is_file()


def frames(video: Path, out_dir: Path, times: list[float], offset: float = 0.0, width: int = 640) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for t in times:
        out = out_dir / f"frame_{t:07.2f}.png"
        if _frame(video, t - offset, out, width):
            rows.append({"t": t, "file": str(out)})
    return {"ok": bool(rows), "frames": rows}


def sheet(video: Path, out: Path, every: float | None, offset: float = 0.0, tile: tuple[int, int] = (480, 270)) -> dict:
    from PIL import Image, ImageDraw

    seconds = _seconds(video)
    if seconds <= 0:
        return {"ok": False, "error": "the video has no length"}
    step = every or max(1.0, seconds / 16)
    times = [round(k * step + step / 2, 2) for k in range(int(seconds // step) or 1) if k * step + step / 2 < seconds]
    tiles, (w, h) = [], tile
    work = out.parent / (out.stem + "_tiles")
    work.mkdir(parents=True, exist_ok=True)
    for t in times:
        f = work / f"{t:07.2f}.png"
        if _frame(video, t, f, w):
            im = Image.open(f).convert("RGB").resize((w, h))
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, 64, 20], fill=(0, 0, 0))
            d.text((5, 4), f"{t + offset:6.1f}s", fill=(255, 255, 255))
            tiles.append(im)
    shutil.rmtree(work, ignore_errors=True)
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    board = Image.new("RGB", (cols * w, max(1, rows) * h), (20, 20, 20))
    for k, im in enumerate(tiles):
        board.paste(im, ((k % cols) * w, (k // cols) * h))
    board.save(out)
    return {"ok": True, "file": str(out), "times": [round(t + offset, 2) for t in times]}


def phone(workspace: Path, file: str, scene: str, out_dir: Path, video: str, samples: int) -> dict:
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = _env(workspace)
    proc = subprocess.run([PY, str(TOOLS / "export_scene.py"), str(workspace / file), scene, str(out_dir)],
                          env=env, capture_output=True, text=True, timeout=int(os.environ.get("PANIM_AGENT_EXPORT_SECONDS", "1800")))
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"ok": False, "error": _tail(proc.stderr) or "the export said nothing"}
    if result.get("tier") is None:
        return {"ok": False, "error": result.get("error") or _tail(proc.stderr)}
    # The web player's geometry (scene_ir.json, cut into segments when long), written by scene_ir.py itself.
    ir = subprocess.run([PY, str(TOOLS / "scene_ir.py"), str(out_dir), scene], env=env, capture_output=True, text=True)
    try:
        geometry = json.loads(ir.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        geometry = {"error": _tail(ir.stderr) or "no geometry"}
    generated = out_dir / "dsl" / "generated"
    # The program and what it draws with (its clips, pictures, glyphs); the narration travels apart (compressed when
    # a library is packed for the phone).
    size = sum(p.stat().st_size for p in generated.rglob("*") if p.is_file() and p.suffix != ".wav") if generated.is_dir() else 0
    summary = {"ok": True, "tier": result.get("tier"), "blockers": result.get("blockers") or [],
               "bytes": size, "narration": (result.get("narration") or {}).get("file"),
               "geometry": geometry.get("geometry", False), "geometry_error": geometry.get("error")}
    sys.path.insert(0, str(TOOLS))
    sys.path.insert(0, str(ENGINE.parents[1]))
    from phone_check import check

    from dsl.interpret import load_program, timeline_frames, parse  # noqa: F401

    program = (generated / f"{scene}.panim").read_text()
    total = timeline_frames(parse(program)["timeline"], FPS) / FPS
    summary["seconds"] = round(total, 2)
    times = [round(total * (k + 0.5) / samples, 2) for k in range(samples)] if samples else []
    compared = check(out_dir, scene, None if video == "-" else Path(video), out_dir / "check", times)
    judged = [f for f in compared["frames"] if "ok" in f]
    summary["check"] = {"ok": compared["ok"], "frames": len(compared["frames"]),
                        "differ": [{"t": f["t"], "mean": f["mean"], "differ": f["differ"]} for f in judged if not f["ok"]]}
    if judged:
        worst = max(judged, key=lambda f: (f["differ"], f["mean"]))
        summary["worst"] = {"t": worst["t"], "phone": worst["phone"], "manim": worst.get("manim"),
                            "mean": worst["mean"], "differ": worst["differ"]}
    summary["ok"] = not summary["blockers"] and compared["ok"] is not False
    return summary


def facts() -> dict:
    """What the agent would otherwise spend turns looking up: the fonts (the long tail of Noto scripts left out), the
    Python it has and the map data that is there offline."""
    import glob
    import re

    families = set()
    listed = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout.splitlines()
    for line in listed:
        f = line.split(",")[0].strip()
        if not f:
            continue
        if f.startswith("Noto ") and not re.search(r"Devanagari|CJK|Emoji|^Noto (Sans|Serif|Mono)$", f):
            continue
        if f.startswith("Latin Modern") and f not in ("Latin Modern Roman", "Latin Modern Sans", "Latin Modern Mono"):
            continue
        families.add(f)
    out = {"ok": True, "fonts": sorted(families)}
    try:
        import manim
        out["manim"] = manim.__version__
    except ImportError:
        pass
    try:
        import cartopy
        data = str(cartopy.config["data_dir"])
        out["natural_earth"] = {"dir": data, "files": sorted({Path(p).stem for p in glob.glob(data + "/**/*.shp", recursive=True)})}
    except Exception:  # noqa: BLE001 -- no map data is a fact too
        pass
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    kind, args = sys.argv[1], sys.argv[2:]
    try:
        if kind == "render":
            result = render(Path(args[0]).resolve(), args[1], args[2], args[3] if len(args) > 3 else "draft",
                            float(args[4]) if len(args) > 4 else 0.0, float(args[5]) if len(args) > 5 else 0.0)
        elif kind == "frames":
            # frames <video> <out> <offset> <width> <t>...
            result = frames(Path(args[0]), Path(args[1]), [float(t) for t in args[4:]], float(args[2]), int(args[3]))
        elif kind == "sheet":
            result = sheet(Path(args[0]), Path(args[1]), float(args[2]) if len(args) > 2 else None,
                           float(args[3]) if len(args) > 3 else 0.0)
        elif kind == "facts":
            result = facts()
        elif kind == "phone":
            result = phone(Path(args[0]).resolve(), args[1], args[2], Path(args[3]).resolve(), args[4],
                           int(args[5]) if len(args) > 5 else 12)
        else:
            result = {"ok": False, "error": f"no tool {kind!r}"}
    except subprocess.TimeoutExpired as error:
        result = {"ok": False, "error": f"stopped: over {error.timeout} s"}
    except Exception as error:  # noqa: BLE001 -- the agent is told why
        result = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
