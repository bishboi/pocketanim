"""Speak a chapter from its transcript lines and align every word: the chapter's narration track and its word times.

    .venv/bin/python harness_v2/engine/tools/chapter_voice.py <lines.json> <out_dir> [progress.json]

`lines.json` is {"lines": ["...", ...]}: the chapter's sentences, in order, as the transcript has them. Nothing about
scenes is needed: the voice comes first, and the video is built to it.

1. SPEAK: a voice that can (Gemini, ElevenLabs) says the chapter whole, in one take (pocket_lecture.narrate_many),
   cut back into its lines, each keeping the pause the voice left after it; else line by line. The lines go into
   the shared cache (PANIM_AUDIO_DIR), keyed by voice and words, so a line said again is not paid for again. For
   Gemini and ElevenLabs the voice director marks the lines for delivery first.
2. ALIGN: when each word is said (pocket_lecture.line_words): from the voice (ElevenLabs), else Whisper here
   (local_align.py), else an estimate (the words spread over the line's spoken stretches), marked `"est"`.
3. LAY OUT: the lines one after another on one track, each followed by its pause (pocket_lecture.beat_pad), written
   as <out_dir>/chapter.wav, with every word's time on that track.

Writes <out_dir>/timing.json and prints it as the last line of stdout:
    {"ok": true, "seconds", "track": "chapter.wav", "source": "voice"|"whisper"|"estimate"|"mixed",
     "lines": [{"n", "text", "start", "end", "words": [{"w", "start", "end"}]}], "voice": {cost...}}
or {"ok": false, "error": "..."}.
"""

from __future__ import annotations

import json
import os
import sys
import wave
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RATE, CHANNELS = 44100, 2


def write(progress: Path | None, **state) -> None:
    if progress is None:
        return
    tmp = progress.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(progress)


def _read(path: str):
    """A spoken line's samples as int16 (frames, 2) at 44.1 kHz: the engine writes its lines so (_finish)."""
    import numpy as np

    with wave.open(path) as w:
        channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"{path}: not 16-bit")
    samples = np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
    if channels == 1:
        samples = np.repeat(samples, 2, axis=1)
    if rate != RATE:
        # Resampled by index: only a line made without ffmpeg is at another rate.
        index = (np.arange(int(len(samples) * RATE / rate)) * rate / RATE).astype(int)
        samples = samples[np.minimum(index, len(samples) - 1)]
    return samples[:, :2]


def speak(lines: list[str], progress: Path | None) -> dict:
    """Every line spoken into the cache (a chapter's take where the voice can), as prespeak.py does."""
    import pocket_lecture as pl
    import tts
    import voice_director

    mode = pl.voice_mode()
    if mode == "silent":
        return {"engine": "silent", "usd": 0.0, "spoken": 0, "lines": len(lines)}
    engine = mode.split(":", 1)[0]
    unique = list(dict.fromkeys(lines))
    left = [line for line in unique if pl._cached_seconds(pl.audio_file(mode, pl.speechify(line))) is None]
    director = 0.0
    if left and voice_director.enabled(engine):
        write(progress, phase="direct", done=len(unique) - len(left), total=len(unique))
        todo = [pl.speechify(line) for line in left if pl.delivery(mode, pl.speechify(line)) is None]
        marked, director = voice_director.mark(todo, engine)
        for spoken, said in marked.items():
            pl.delivery_file(mode, spoken).write_text(said, encoding="utf-8")
    write(progress, phase="voice", done=len(unique) - len(left), total=len(unique))
    speaker = tts.engine(engine)
    one_take = ((os.environ.get("PANIM_TTS_WHOLE") or "on").strip().lower() not in ("off", "0", "no")
                and hasattr(speaker, "speak_many") and len(left) > 1)
    take_chars = int(os.environ.get("PANIM_TTS_WHOLE_CHARS") or getattr(speaker, "WHOLE_CHARS", 4000))
    takes: list[list[str]] = []
    for line in left:
        if one_take and takes and sum(len(x) + 2 for x in takes[-1]) + len(line) <= take_chars:
            takes[-1].append(line)
        else:
            takes.append([line])
    if one_take and len(takes) > 1 and len(takes[-1]) < 4:
        takes[-2] += takes.pop()
    done = len(unique) - len(left)
    for take in takes:
        if one_take:
            pl.narrate_many(take, take=True, fallback=4)
        for line in take:
            pl.narrate(line)
        done += len(take)
        write(progress, phase="voice", done=done, total=len(unique))
    spent = sum(pl.line_cost(mode, pl.speechify(line)) or 0.0 for line in left)
    return {"engine": engine, "voice": mode.split(":", 1)[1], "usd": round(spent + director, 6),
            "director_usd": round(director, 6), "spoken": len(left), "lines": len(unique),
            "takes": len(takes) if one_take else 0}


def lay_out(lines: list[str], out_dir: Path, progress: Path | None) -> dict:
    """The chapter's track and every word's time on it."""
    import numpy as np

    import pocket_lecture as pl

    pieces, rows, sources = [], [], set()
    clock = 0.0
    for n, line in enumerate(lines):
        write(progress, phase="align", done=n, total=len(lines))
        path, seconds = pl.narrate(line)
        pad = pl.beat_pad(line)
        words = None
        if path:
            samples = _read(path)
            seconds = len(samples) / RATE
            words = pl.line_words(line)
        else:
            samples = np.zeros((int(seconds * RATE), CHANNELS), dtype="<i2")
        if words:
            estimated = any(w.get("est") for w in words)
            sources.add("estimate" if estimated else ("voice" if pl.voice_mode().startswith("eleven") else "whisper"))
        else:
            # No words to be had (a silent build, or a line the aligner could not read): spread over the line.
            sources.add("estimate")
            said = pl.speechify(line).split()
            step = seconds / max(1, len(said))
            words = [{"w": w, "start": k * step, "end": (k + 1) * step, "est": True} for k, w in enumerate(said)]
        rows.append({
            "n": n, "text": line, "start": round(clock, 3), "end": round(clock + seconds, 3),
            "words": [{"w": w["w"], "start": round(clock + float(w["start"]), 3),
                       "end": round(clock + float(w["end"]), 3), **({"est": True} if w.get("est") else {})}
                      for w in words],
        })
        pieces.append(samples)
        pieces.append(np.zeros((int(pad * RATE), CHANNELS), dtype="<i2"))
        clock += seconds + pad
    track = np.concatenate(pieces) if pieces else np.zeros((0, CHANNELS), dtype="<i2")
    out = out_dir / "chapter.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(track.tobytes())
    source = sources.pop() if len(sources) == 1 else ("mixed" if sources else "estimate")
    return {"seconds": round(len(track) / RATE, 3), "track": out.name, "source": source, "lines": rows}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    lines = [str(x).strip() for x in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["lines"]]
    lines = [x for x in lines if x]
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    progress = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    import pocket_lecture as pl

    try:
        voice = speak(lines, progress)
        result = {"ok": True, **lay_out(lines, out_dir, progress), "voice": voice}
    except pl.VoiceUnavailable as error:
        result = {"ok": False, "error": str(error)}
    (out_dir / "timing.json").write_text(json.dumps(result, ensure_ascii=False))
    write(progress, phase="done", done=len(lines), total=len(lines))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
