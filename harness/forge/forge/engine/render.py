"""Render: chapter scenes to MP4, in parallel, cached by content.

A chapter's render is keyed by its scene source, the engine's own source, the
quality and the voice. A revised beat changes one chapter's source, so only
that chapter renders again; the rest come from build/renders.

Each render also writes a beat log (PANIM_BEAT_LOG): where every beat and
chapter card started in rendered time. Subtitles, chapter marks and the
contact sheet are cut from it, so they follow what the video actually did.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from forge.util import LECTURE, REPO, digest, read_json

QUALITY = {"l": "480p15", "m": "720p30", "h": "1080p60", "k": "2160p60"}


def engine_hash() -> str:
    return digest(LECTURE / "pocket_lecture.py")


def _render_one(job, chapter_id: str, entry: dict, quality: str, voice: str) -> dict:
    source = Path(entry["file"])
    key = digest(source, engine_hash(), quality, voice)
    renders = job.path("build", "renders")
    renders.mkdir(parents=True, exist_ok=True)
    video = renders / f"{chapter_id}-{quality}-{key}.mp4"
    log = renders / f"{chapter_id}-{quality}-{key}.jsonl"
    if video.exists() and log.exists():
        return {"chapter": chapter_id, "video": str(video), "log": str(log), "cached": True}
    media = job.path("build", "media")
    partial = log.with_suffix(".partial")
    partial.unlink(missing_ok=True)
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": os.pathsep.join([str(LECTURE), str(REPO), env.get("PYTHONPATH", "")]),
        "PANIM_VOICE": voice, "PANIM_AUDIO_DIR": str(job.path("audio")), "PANIM_BEAT_LOG": str(partial),
    })
    command = [sys.executable, "-m", "manim", "render", f"-q{quality}", "--disable_caching", "--progress_bar", "none",
               "--media_dir", str(media), "-o", f"{chapter_id}.mp4", str(source), entry["class"]]
    result = subprocess.run(command, cwd=job.path("build"), env=env, capture_output=True, text=True, timeout=7200)
    produced = media / "videos" / source.stem / QUALITY[quality] / f"{chapter_id}.mp4"
    if result.returncode != 0 or not produced.exists():
        tail = (result.stderr or result.stdout or "")[-4000:]
        (renders / f"{chapter_id}.err").write_text(tail, encoding="utf-8")
        return {"chapter": chapter_id, "error": tail.strip().splitlines()[-1] if tail.strip() else "manim failed",
                "stderr": str(renders / f"{chapter_id}.err")}
    shutil.move(str(produced), video)
    partial.replace(log) if partial.exists() else log.write_text("")
    return {"chapter": chapter_id, "video": str(video), "log": str(log), "cached": False}


def render(job, quality: str, voice: str, only: list[str] | None = None) -> dict:
    manifest = read_json(job.path("build", "manifest.json"))
    if not manifest:
        raise RuntimeError("nothing compiled; run the compile stage first")
    todo = [(cid, entry) for cid, entry in manifest.items() if not only or cid in only]
    workers = int(os.environ.get("FORGE_WORKERS") or max(1, min(4, (os.cpu_count() or 2))))
    job.log(f"render: {len(todo)} chapter(s) at -q{quality}, {workers} at a time")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda item: _render_one(job, item[0], item[1], quality, voice), todo))
    out = {r["chapter"]: r for r in results}
    for r in results:
        if r.get("error"):
            job.log(f"render {r['chapter']} failed: {r['error']}")
        else:
            job.log(f"render {r['chapter']}: {'cached' if r['cached'] else 'done'}")
    return out


def preview(job, voice: str) -> dict:
    """480p15: cheap enough to watch the whole film before paying for the final."""
    return render(job, "l", voice)


def final(job, voice: str, quality: str = "m") -> dict:
    return render(job, quality, voice)
