"""A compiled scene's voice, for v2's Voice step: after prespeak.py has spoken every line, what each line is, and the
scene's animations timed to the words (align_cues.py) with the timing model's answer, asked by the app.

    voice_scene.py lines scene.py               every line spoken: its words, audio, length, cost, word times
    voice_scene.py items scene.py               the beats the timing model times: each one's line, words, parts
    voice_scene.py cues scene.py answer.json out.py
                                                the answer's times checked and written into the scene as cues=

Each prints one JSON object (the last line of stdout). The app makes the timing model's call itself, so it is
recorded like every other call (app/lib/voice.ts): the prompt here is align_cues's own (SYSTEM and its items).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _style(source: str) -> None:
    import os

    style = re.search(r"""os\.environ\.setdefault\(\s*["']LECTURE_STYLE["']\s*,\s*["'](\w+)["']""", source)
    if style:
        os.environ.setdefault("LECTURE_STYLE", style.group(1))


def _words(pl, mode: str, text: str) -> tuple[list[dict] | None, str]:
    """A line's word times and where they came from: the voice, the aligner here, an estimate, or none."""
    import local_align

    kept = pl.words_file(pl.audio_file(mode, pl.speechify(text))).exists()
    said = pl.line_words(text)
    if not said:
        return None, local_align.problem() or "no word times"
    if any(w.get("est") for w in said):
        return said, "estimated"
    return said, "voice" if kept else "aligned"


def lines(source: str) -> dict:
    import pocket_lecture as pl
    from prespeak import beat_lines

    mode = pl.voice_mode()
    out = []
    for text in dict.fromkeys(beat_lines(source)):
        spoken = pl.speechify(text)
        wav = pl.audio_file(mode, spoken)
        seconds = pl._cached_seconds(wav)
        row = {"text": text, "spoken": spoken, "seconds": None, "file": None, "usd": pl.line_cost(mode, spoken),
               "delivery": pl.delivery(mode, spoken)}
        if seconds is not None:
            tight, _, length = pl._tight(wav)
            words, source_of = _words(pl, mode, text)
            top = float(length)
            words = [{**w, "start": round(min(float(w["start"]), top), 3), "end": round(min(float(w["end"]), top), 3)}
                     for w in words or []] or None
            row.update(seconds=round(float(length), 3), file=tight, words=words, words_from=source_of)
        out.append(row)
    import local_align

    return {"ok": True, "mode": mode, "lines": out,
            "aligner": local_align.problem() or f"Whisper {(local_align._env('PANIM_ALIGN_WHISPER') or 'small')} "
                                                "through faster-whisper"}


def items(source: str) -> dict:
    import align_cues
    import pocket_lecture as pl

    mode = pl.voice_mode()
    out = []
    for k, beat in enumerate(align_cues.beats(source)):
        seconds = pl._cached_seconds(pl.audio_file(mode, pl.speechify(beat["text"])))
        words = pl.line_words(beat["text"]) if seconds else None
        if seconds:
            seconds = pl._tight(pl.audio_file(mode, pl.speechify(beat["text"])))[2]
        row = {"id": k, "kind": beat["kind"], "text": beat["text"], "parts": beat["parts"],
               "seconds": round(float(seconds), 3) if seconds else None}
        if words and seconds:
            row["item"] = align_cues._item(k, beat, words, float(seconds))
            row["words"] = words
        else:
            row["why"] = "the line is not spoken yet" if not seconds else "no word times for the line"
        out.append(row)
    return {"ok": True, "system": align_cues.SYSTEM, "beats": out}


def cues(source: str, answer: dict, target: Path) -> dict:
    import align_cues
    import pocket_lecture as pl

    mode = pl.voice_mode()
    found = align_cues.beats(source)
    edits, rows = [], []
    by_id = {}
    for entry in answer.get("beats") or []:
        try:
            by_id[int(entry.get("id"))] = entry
        except (TypeError, ValueError, AttributeError):
            continue
    for k, beat in enumerate(found):
        entry = by_id.get(k)
        row = {"id": k, "text": beat["text"][:200]}
        if entry is None:
            row["why"] = "no times for this beat"
        else:
            seconds = pl._tight(pl.audio_file(mode, pl.speechify(beat["text"])))[2]
            timed = align_cues.check(beat, entry, float(seconds))
            if timed is None:
                row["why"] = f"the times did not fit its {len(beat['parts'])} animation(s): {json.dumps(entry)[:160]}"
            else:
                edits.append((beat, timed))
                row["cues"] = timed
        rows.append(row)
    target.write_text(align_cues.write_cues(source, edits), encoding="utf-8")
    return {"ok": True, "aligned": len(edits), "beats": rows}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    what, scene = sys.argv[1], Path(sys.argv[2])
    source = scene.read_text(encoding="utf-8")
    _style(source)
    import pocket_lecture as pl

    try:
        if what == "lines":
            result = lines(source)
        elif what == "items":
            result = items(source)
        elif what == "cues":
            result = cues(source, json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")), Path(sys.argv[4]))
        else:
            result = {"ok": False, "error": f"unknown: {what}"}
    except pl.VoiceUnavailable as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
