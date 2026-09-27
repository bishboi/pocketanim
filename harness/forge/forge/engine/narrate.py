"""Narrate: speak every line once, before any frame is drawn.

The scene engine looks a line's audio up by a hash of its voice and its
spoken text (pocket_lecture.narrate). This stage fills that cache for every
line the compiled scenes will say -- Kokoro in batches when it can run,
espeak-ng in parallel otherwise -- so the renders never wait on a voice and a
revised job re-speaks only the lines that changed.

It also writes timeline.json (each line's measured seconds, each chapter's
runtime against its share of the target) and runs the phoneme audit.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from forge.engine.compile import chapter_lines
from forge.util import REPO, write_json

KOKORO_SCRIPT = REPO / "harness" / "scripts" / "kokoro_speak.py"
KOKORO_WEIGHTS = REPO / "harness" / "models" / "kokoro-v1.0.onnx"
PAD = 0.45           # the hold after each beat (Lecture.beat's pad)
BATCH = 40


def kokoro_ready() -> bool:
    return importlib.util.find_spec("kokoro_onnx") is not None and KOKORO_WEIGHTS.exists()


def voice_mode(style: dict) -> str:
    """The PANIM_VOICE value for this style: kokoro:<voice>, espeak or silent.

    FORGE_VOICE in the environment wins (a test run can force espeak).
    """
    forced = os.environ.get("FORGE_VOICE")
    if forced:
        return forced
    voice = style.get("voice") or {}
    engine = voice.get("engine", "auto")
    espeak = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
    if engine in ("kokoro", "auto") and kokoro_ready():
        return f"kokoro:{voice.get('name', 'af_sarah')}"
    if engine == "silent":
        return "silent"
    return "espeak" if espeak else "silent"


def _seconds(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / float(handle.getframerate())


def _cache_path(folder: Path, mode: str, spoken: str) -> Path:
    return folder / f"{hashlib.md5(f'{mode}|{spoken}'.encode()).hexdigest()[:12]}.wav"


def _finish(raw: Path, out: Path) -> None:
    """The house treatment every line gets: band-limit, level, 44.1 kHz stereo."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                    "highpass=f=70,loudnorm=I=-17:TP=-2,apad=pad_dur=0.1", "-ar", "44100", "-ac", "2", str(out)],
                   check=True, timeout=120)


def _kokoro_batch(job, voice: str, todo: list[tuple[str, Path]], lang: str = "en-us") -> list[str]:
    """Speak lines with Kokoro, BATCH at a time. Returns the lines it could not speak."""
    failed = []
    scratch = job.path("audio", "_batch")
    scratch.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        out = scratch / f"b{start:04d}.wav"
        request = json.dumps({"voice": voice, "lines": [s for s, _ in chunk], "out": str(out), "lang": lang})
        try:
            result = subprocess.run([sys.executable, str(KOKORO_SCRIPT)], input=request, capture_output=True,
                                    text=True, timeout=1800)
            reply = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception as error:  # noqa: BLE001 -- these lines fall back to espeak
            job.log(f"kokoro failed: {error}")
            failed += [s for s, _ in chunk]
            continue
        files = reply.get("files") or []
        if not reply.get("ok") or len(files) != len(chunk):
            job.log(f"kokoro: {reply.get('error') or 'no per-line files'}")
            failed += [s for s, _ in chunk]
            continue
        for (spoken, target), part in zip(chunk, files):
            _finish(Path(part), target)
            Path(part).unlink(missing_ok=True)
        out.unlink(missing_ok=True)
    shutil.rmtree(scratch, ignore_errors=True)
    return failed


def narrate_job(job, template: dict, style: dict) -> dict:
    import pocket_lecture as pl

    outline = job.read("outline.json")
    mode = voice_mode(style)
    folder = job.path("audio")
    folder.mkdir(exist_ok=True)
    os.environ["PANIM_AUDIO_DIR"] = str(folder)
    os.environ["PANIM_VOICE"] = mode
    pl.SAY.update(job.lexicon)

    per_chapter = {}
    todo: dict[str, Path] = {}
    said: dict[str, str] = {}          # spoken text -> the caption it came from
    for chapter in outline["chapters"]:
        lines = chapter_lines(job, chapter, job.script(chapter["id"]), outline)
        per_chapter[chapter["id"]] = lines
        if mode == "silent":
            continue
        for line in lines:
            spoken = pl.speechify(line)
            path = _cache_path(folder, mode, spoken)
            if not (path.exists() and path.stat().st_size > 44):
                todo[spoken] = path
                said[spoken] = line

    job.log(f"narrate: {sum(len(v) for v in per_chapter.values())} lines, {len(todo)} to speak ({mode})")
    left = list(todo.items())
    if left and mode.startswith("kokoro"):
        failed = set()
        voice = mode.split(":", 1)[1]
        for lang in sorted({pl.spoken_lang(sp) for sp, _ in left}):
            group = [(sp, p) for sp, p in left if pl.spoken_lang(sp) == lang]
            if lang == "en":
                failed |= set(_kokoro_batch(job, voice, group))
            else:
                own = voice if voice.startswith(lang[0]) else pl.KOKORO_VOICES[lang]
                failed |= set(_kokoro_batch(job, own, group, lang))
        left = [(s, p) for s, p in left if s in failed]
    if left:
        # espeak through the engine's own path, which writes the same cache
        # file name for this mode.
        if mode.startswith("kokoro"):
            os.environ["PANIM_VOICE"] = "espeak"
            for spoken, path in left:
                wav, _ = pl.narrate(said[spoken])
                if wav:
                    shutil.copy(wav, path)
            os.environ["PANIM_VOICE"] = mode
        else:
            with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as pool:
                list(pool.map(lambda item: pl.narrate(said[item[0]]), left))

    timeline = {"voice": mode, "chapters": [], "total_seconds": 0.0,
                "target_seconds": round(outline["target_minutes"] * 60, 1)}
    for chapter in outline["chapters"]:
        rows = []
        for line in per_chapter[chapter["id"]]:
            spoken = pl.speechify(line)
            path = _cache_path(folder, mode, spoken)
            if mode != "silent" and path.exists():
                seconds = _seconds(path)
            else:
                seconds = pl.estimate_seconds(spoken)
                path = None
            rows.append({"text": line, "seconds": round(seconds, 3), "wav": str(path) if path else None})
        estimate = sum(r["seconds"] + PAD for r in rows) + 3.0      # cards, map draw, fades
        timeline["chapters"].append({"id": chapter["id"], "title": chapter["title"], "lines": rows,
                                     "seconds": round(estimate, 1), "target_seconds": chapter["target_seconds"]})
        timeline["total_seconds"] += estimate
    timeline["total_seconds"] = round(timeline["total_seconds"], 1)
    warnings = []
    for row in timeline["chapters"]:
        ratio = row["seconds"] / max(row["target_seconds"], 1.0)
        if ratio < 0.4 or ratio > 2.0:
            warnings.append(f"{row['id']} ({row['title']}) runs {row['seconds']:.0f}s against a share of "
                            f"{row['target_seconds']:.0f}s")
    timeline["warnings"] = warnings
    write_json(job.path("timeline.json"), timeline)
    return timeline


# ════════════════════════════════════════════════════════════════════════
#  Phoneme audit
# ════════════════════════════════════════════════════════════════════════

ACRONYM = re.compile(r"\b[A-Z]{2,}\b")


def audit(job) -> dict:
    """Names the voice has no respelling for, and capitals it will spell out.

    Advisory: it writes qa/phonemes.json and suggests lexicon rows; a person
    (or the planner, next time) decides the respellings.
    """
    import pocket_lecture as pl
    from forge.workers import names_in

    timeline = job.read("timeline.json") or {}
    known = set(pl.SAY) | set(job.lexicon)
    unknown: dict[str, list[str]] = {}
    acronyms: dict[str, list[str]] = {}
    for chapter in timeline.get("chapters", []):
        for row in chapter["lines"]:
            for name in names_in(row["text"]):
                for word in name.split():
                    if word not in known and len(word) > 3 and not word.isascii():
                        unknown.setdefault(word, []).append(chapter["id"])
                if name not in known and any(not w.isascii() or re.search(r"[aeiou]{3}|[^aeiou\W]{4}", w.lower())
                                             for w in name.split()):
                    unknown.setdefault(name, []).append(chapter["id"])
            for word in ACRONYM.findall(row["text"]):
                if word not in known:
                    acronyms.setdefault(word, []).append(chapter["id"])
    report = {"voice": timeline.get("voice"),
              "unknown_names": {k: sorted(set(v)) for k, v in unknown.items()},
              "acronyms": {k: sorted(set(v)) for k, v in acronyms.items()},
              "note": "Add respellings to lexicon.yaml; captions keep the correct spelling."}
    write_json(job.path("qa", "phonemes.json"), report)
    return report
