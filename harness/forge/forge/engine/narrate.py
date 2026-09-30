"""Narrate: speak every line once, before any frame is drawn.

The scene engine looks a line's audio up by a hash of its voice and its
spoken text (pocket_lecture.narrate). This stage fills that cache for every
line the compiled scenes will say, with Google Chirp 3 HD, so the renders never wait on a voice and a
revised job re-speaks only the lines that changed.

It also writes timeline.json (each line's measured seconds, each chapter's
runtime against its share of the target) and runs the phoneme audit.
"""

from __future__ import annotations

import os
import re
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from forge.engine.compile import chapter_lines
from forge.util import write_json

CHIRP_THREADS = 6    # Chirp lines in flight at once (each is one request)


def voice_mode(style: dict) -> str:
    """The PANIM_VOICE value for this job: gemini:<voice> (Gemini 3.8 Flash TTS), chirp:<voice> (PANIM_TTS=chirp),
    or silent.

    FORGE_VOICE=silent (or PANIM_VOICE=silent) builds without narration, for tests; otherwise the voice must be
    set up, and a job without it stops here with the reason (pocket_lecture.VoiceUnavailable).
    """
    import pocket_lecture as pl
    import tts

    if "silent" in (os.environ.get("FORGE_VOICE"), os.environ.get("PANIM_VOICE")):
        return "silent"
    name = tts.engine_name()
    speaker = tts.engine(name)
    if not speaker.configured():
        raise pl.VoiceUnavailable(tts.setup_hint() + " FORGE_VOICE=silent builds without narration.")
    voice = style.get("voice") or {}
    chosen = os.environ.get("PANIM_TTS_VOICE") or os.environ.get("PANIM_CHIRP_VOICE") or voice.get("chirp")
    return f"{name}:{chosen or speaker.voice_for(style.get('engine_theme'))}"


def _seconds(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / float(handle.getframerate())


def _cache_path(folder: Path, mode: str, spoken: str) -> Path:
    """The engine's own cache file for the line (pocket_lecture.audio_file), in this job's audio folder."""
    import pocket_lecture as pl

    return folder / pl.audio_file(mode, spoken).name


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
    if left:
        # One request a line (a request a language run), several at once; the engine writes the cache, and a line
        # Google refuses stops the job with Google's message.
        with ThreadPoolExecutor(max_workers=CHIRP_THREADS) as pool:
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
        estimate = sum(r["seconds"] + pl.BEAT_PAD for r in rows) + 3.0      # cards, map draw, fades
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
