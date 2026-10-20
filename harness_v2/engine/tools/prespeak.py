"""Speak a lecture scene's lines before Manim runs, several at once, and report progress.

    .venv/bin/python harness_v2/engine/tools/prespeak.py scene.py [progress.json]

Inside Manim each beat's line is spoken when the beat is reached, one after another: a 50-minute lecture is
hundreds of requests in a row, and the page could only say "Speaking the lecture..." for the whole wait. Here
every line of the scene (self.beat("...") and the helpers that speak through it) is spoken first, into the same
cache pocket_lecture.narrate reads (PANIM_AUDIO_DIR), so the render finds each line ready. A voice that can
(Gemini, ElevenLabs) speaks the scene -- a chapter -- whole, in one take (PANIM_TTS_WHOLE, on by default), cut back
into its lines; else a few lines a request, PANIM_TTS_THREADS (default 8) requests at a time.

Progress is written to the progress file as {"phase": "voice", "done": n, "total": N, "beats": B}; the last line
of stdout is {"ok": true, "lines": N, "spoken": k, "beats": B} or {"ok": false, "error": "..."}.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# v2's copy (harness_v2/engine/tools): v2's own lecture engine, never v1's.
ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))


def _value(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


def _arg(call: ast.Call, index: int, name: str):
    """A call's argument by position or keyword, as a Python value (None when it is not a literal)."""
    for keyword in call.keywords:
        if keyword.arg == name:
            return _value(keyword.value)
    return _value(call.args[index]) if len(call.args) > index else None


def beat_lines(source: str) -> list[str]:
    """Every line the scene will speak, in order (a line said twice is listed twice): self.beat("...") and the
    helpers that speak through it (pocket_lecture: title_slide, chapter, recap), as they build their lines, and
    the line of each free-form block (self.free)."""
    out: list[str] = []
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    for call in sorted(calls, key=lambda n: (n.lineno, n.col_offset)):
        name = call.func.attr
        if name == "beat":
            line = _arg(call, 0, "text")
            lines = [line]
        elif name == "free":
            lines = [_arg(call, 1, "text")]
        elif name == "title_slide":
            title, sub = _arg(call, 0, "title"), _arg(call, 1, "sub") or ""
            lines = [_arg(call, 3, "narration") or (f"{title}. {sub}" if isinstance(title, str) else None)]
        elif name == "chapter":
            lines = [_arg(call, 3, "narration")]
        elif name == "recap":
            points, narration = _arg(call, 0, "points"), _arg(call, 1, "narration")
            if narration:
                lines = list(narration)
            elif isinstance(points, (list, tuple)):
                lines = [f"{h}. {b}." for h, b in list(points)[:8]]
            else:
                lines = []
        else:
            continue
        out.extend(line for line in lines if isinstance(line, str) and line.strip())
    return out


def write(progress: Path | None, **state) -> None:
    if progress is None:
        return
    tmp = progress.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(progress)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    progress = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    # The scene's style, as it sets it before importing the engine: Chirp's speaker depends on it.
    style = re.search(r"""os\.environ\.setdefault\(\s*["']LECTURE_STYLE["']\s*,\s*["'](\w+)["']""", source)
    if style:
        os.environ.setdefault("LECTURE_STYLE", style.group(1))
    import pocket_lecture as pl

    lines = beat_lines(source)
    unique = list(dict.fromkeys(lines))
    try:
        mode = pl.voice_mode()
    except pl.VoiceUnavailable as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 0
    if mode == "silent":
        print(json.dumps({"ok": True, "lines": len(unique), "spoken": 0, "beats": len(lines)}))
        return 0
    left = [line for line in unique
            if pl._cached_seconds(pl.audio_file(mode, pl.speechify(line))) is None]
    done = len(unique) - len(left)
    # How the lines still to be spoken are said, marked for an expressive voice first (voice_director.py).
    import voice_director

    director = {"lines": 0, "usd": 0.0}
    if left and voice_director.enabled(mode.split(":", 1)[0]):
        write(progress, phase="direct", done=done, total=len(unique), beats=len(lines))
        todo = [pl.speechify(line) for line in left if pl.delivery(mode, pl.speechify(line)) is None]
        marked, director["usd"] = voice_director.mark(todo, mode.split(":", 1)[0])
        for spoken, said in marked.items():
            pl.delivery_file(mode, spoken).write_text(said, encoding="utf-8")
        director["lines"] = len(marked)
    lock = threading.Lock()
    write(progress, phase="voice", done=done, total=len(unique), beats=len(lines))
    threads = max(1, int(os.environ.get("PANIM_TTS_THREADS", "8")))
    # Lines in order, a few to a request (pocket_lecture.narrate_many): Google allows only so many requests a minute.
    batch_lines = max(1, int(os.environ.get("PANIM_TTS_BATCH", "4") or 4))
    batch_bytes = int(os.environ.get("PANIM_TTS_BATCH_BYTES", "700"))
    # PANIM_TTS_WHOLE (on by default): the scene's lines spoken whole, in one take (a chapter's, up to the voice's
    # WHOLE_CHARS a take, PANIM_TTS_WHOLE_CHARS), so the voice keeps one tone and pace and runs on from line to line;
    # each line then keeps the pause the voice left after it (pocket_lecture.beat_pad). A voice that speaks a line
    # at a time (espeak, Chirp) is asked as before.
    import tts

    speaker = tts.engine(mode.split(":", 1)[0])
    one_take = ((os.environ.get("PANIM_TTS_WHOLE") or "on").strip().lower() not in ("off", "0", "no")
             and hasattr(speaker, "speak_many") and len(left) > 1)
    take_chars = int(os.environ.get("PANIM_TTS_WHOLE_CHARS") or getattr(speaker, "WHOLE_CHARS", 4000))
    batches: list[list[str]] = []
    for line in left:
        if one_take:
            if batches and sum(len(x) + 2 for x in batches[-1]) + len(line) <= take_chars:
                batches[-1].append(line)
            else:
                batches.append([line])
            continue
        size = len(line.encode())
        if (batches and len(batches[-1]) < batch_lines and size < batch_bytes // 2
                and sum(len(x.encode()) for x in batches[-1]) + size <= batch_bytes):
            batches[-1].append(line)
        else:
            batches.append([line])
    if one_take and len(batches) > 1 and len(batches[-1]) < 4:
        # A short last take is joined to the one before (a little over the limit), not spoken apart.
        batches[-2] += batches.pop()
    failed: list[str] = []
    timing: list[dict] = []                       # each batch: lines, when, how long, how it ended

    def timed(batch: list[str]) -> None:
        import time

        start = time.time() * 1000
        outcome = "ok"
        try:
            pl.narrate_many(batch, take=one_take, fallback=batch_lines if one_take else 0)
        except Exception as error:  # noqa: BLE001 -- recorded, then raised as it was
            outcome = type(error).__name__
            raise
        finally:
            timing.append({"lines": len(batch), "chars": sum(len(x) for x in batch), "start": start,
                           "end": time.time() * 1000, "outcome": outcome})

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(timed, batch): batch for batch in batches}
        for future in as_completed(futures):
            try:
                future.result()
            except pl.VoiceUnavailable as error:
                failed.append(str(error))
                for other in futures:
                    other.cancel()               # a refused line stops the lecture: no point paying for the rest
                continue
            except Exception as error:  # noqa: BLE001 -- a dropped connection: the build speaks these lines itself
                print(f"prespeak: {len(futures[future])} line(s) left for the build ({type(error).__name__}: "
                      f"{str(error)[:160]})", file=sys.stderr)
                continue
            with lock:
                done += len(futures[future])
                write(progress, phase="voice", done=done, total=len(unique), beats=len(lines))
    # What the voice cost: the lines spoken now (this build's bill) and every line of the lecture (a line spoken
    # for an earlier build was paid for then). Lines spoken before costs were kept count as unknown.
    spoken_now = sum(pl.line_cost(mode, pl.speechify(line)) or 0.0 for line in left)
    whole = [pl.line_cost(mode, pl.speechify(line)) for line in unique]
    voice = {"usd": round(spoken_now, 6), "lecture_usd": round(sum(c for c in whole if c is not None), 6),
             "spoken": len(left), "lines": len(unique), "unknown": sum(c is None for c in whole),
             "engine": mode.split(":", 1)[0]}
    voice["batches"] = dict(pl.BATCHES)
    voice["director"] = {"lines": director["lines"], "usd": round(director["usd"], 6)}
    voice["usd"] = round(voice["usd"] + director["usd"], 6)
    try:
        import tts

        calls = list(getattr(tts.engine(mode.split(":", 1)[0]), "CALLS", []))
    except Exception:  # noqa: BLE001
        calls = []
    voice["timing"] = {"batches": timing, "calls": calls, "threads": threads, "batch_lines": batch_lines,
                       "whole": one_take, "takes": len(batches) if one_take else 0}
    if one_take:
        print(f"prespeak: the chapter in {len(batches)} take(s): {pl.BATCHES['take_ok']} cut into lines, "
              f"{pl.BATCHES['take_uncut']} not cut and {pl.BATCHES['take_failed']} failed (spoken again "
              f"{batch_lines} lines at a time)", file=sys.stderr)
    if any(pl.BATCHES[k] for k in ("ok", "uncut", "failed")):
        print(f"prespeak: batches of up to {batch_lines} lines: {pl.BATCHES['ok']} cut cleanly, "
              f"{pl.BATCHES['uncut']} not cut (spoken line by line), {pl.BATCHES['failed']} failed"
              + ("" if pl.batching_works() else "; batching turned off for the rest of the run"), file=sys.stderr)
    if failed:
        print(json.dumps({"ok": False, "error": failed[0], "voice": voice}))
        return 0
    write(progress, phase="render", done=0, total=len(lines), beats=len(lines))
    print(json.dumps({"ok": True, "lines": len(unique), "spoken": len(left), "beats": len(lines), "voice": voice}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
