"""QA: the contact sheet and the output checks.

The contact sheet is one frame per beat, tiled and labelled with the beat's
id (c3.b05), taken after the beat's animation has landed: the page a person
reviews a preview from, and the ids `forge revise` takes.

The output gate measures what was delivered: integrated loudness (-17 LUFS
+-1), music at least duck_db under the speech, and length within 10% of the
target.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(path)], capture_output=True, text=True, timeout=60).stdout
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def has_audio(path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60).stdout
    return bool(out.strip())


def loudness(path) -> float | None:
    """Integrated loudness in LUFS (EBU R128), or None for silence."""
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null",
                             "-"], capture_output=True, text=True, timeout=1800)
    found = re.findall(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", result.stderr)
    if not found or found[-1] == "-inf":
        return None
    value = float(found[-1])
    return None if value <= -70 else value


def read_log(path) -> list[dict]:
    rows = []
    if path and Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def frame(video, seconds: float, out: Path, width: int = 320) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0.0, seconds):.3f}", "-i", str(video),
                             "-frames:v", "1", "-vf", f"scale={width}:-2", str(out)], capture_output=True, timeout=120)
    return result.returncode == 0 and out.exists()


def contact_sheet(job, renders: dict, labels: dict, out: Path, columns: int = 6) -> dict:
    """One frame per beat. `labels` maps chapter id -> the id of each logged beat, in order."""
    from PIL import Image, ImageDraw, ImageFont

    thumbs = job.path("qa", "frames")
    tiles = []
    for chapter_id, result in renders.items():
        if result.get("error"):
            continue
        beats = [r for r in read_log(result["log"]) if r["kind"] == "beat"]
        names = labels.get(chapter_id, [])
        length = duration(result["video"])
        for index, row in enumerate(beats):
            nxt = beats[index + 1]["start"] if index + 1 < len(beats) else length
            at = min(row["start"] + max(row["seconds"] * 0.8, 0.5), nxt - 0.1)
            name = names[index] if index < len(names) else f"x{index + 1}"
            path = thumbs / f"{chapter_id}.{name}.png"
            if frame(result["video"], at, path):
                tiles.append({"chapter": chapter_id, "beat": name, "time": round(at, 2), "file": str(path),
                              "text": row["text"]})
    if not tiles:
        return {"file": None, "tiles": []}
    first = Image.open(tiles[0]["file"])
    w, h = first.size
    band = 22
    rows = -(-len(tiles) // columns)
    sheet = Image.new("RGB", (columns * w, rows * (h + band)), "#111111")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    for i, tile in enumerate(tiles):
        x, y = (i % columns) * w, (i // columns) * (h + band)
        sheet.paste(Image.open(tile["file"]).convert("RGB").resize((w, h)), (x, y + band))
        draw.text((x + 6, y + 3), f"{tile['chapter']}.{tile['beat']}  {tile['text'][:34]}", fill="#E8E0CC", font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return {"file": str(out), "tiles": tiles}


def audio_check(video, speech=None, music=None, target_seconds: float | None = None, duck_db: float = 15) -> dict:
    """The output gate's measurements, each with its pass/fail."""
    out = {}
    lufs = loudness(video)
    out["loudness_lufs"] = lufs
    out["loudness_ok"] = lufs is not None and abs(lufs + 17) <= 1.0
    if speech and music and Path(music).exists():
        s, m = loudness(speech), loudness(music)
        gap = None if s is None else (99.0 if m is None else round(s - m, 1))
        out["music_under_speech_db"] = gap
        out["music_ok"] = gap is not None and gap >= duck_db
    else:
        out["music_under_speech_db"] = None
        out["music_ok"] = True
    seconds = duration(video)
    out["seconds"] = round(seconds, 1)
    if target_seconds:
        out["target_seconds"] = round(target_seconds, 1)
        out["length_ratio"] = round(seconds / target_seconds, 3)
        out["length_ok"] = abs(seconds / target_seconds - 1) <= 0.10
    return out
