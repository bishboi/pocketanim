"""Speak a lecture scene's lines before Manim runs, several at once, and report progress.

    .venv/bin/python harness/scripts/prespeak.py scene.py [progress.json]

Inside Manim each beat's line is spoken when the beat is reached, one after another: a 50-minute lecture is
hundreds of requests in a row, and the page could only say "Speaking the lecture..." for the whole wait. Here
every line of the scene (self.beat("...") and the helpers that speak through it) is spoken first,
PANIM_TTS_THREADS (default 8) at a time, into the same cache pocket_lecture.narrate reads (PANIM_AUDIO_DIR), so
the render finds each line ready.

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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness" / "lecture"))


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
    helpers that speak through it (pocket_lecture: title_slide, chapter, recap), as they build their lines."""
    out: list[str] = []
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    for call in sorted(calls, key=lambda n: (n.lineno, n.col_offset)):
        name = call.func.attr
        if name == "beat":
            line = _arg(call, 0, "text")
            lines = [line]
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
            if not (lambda f: f.exists() and f.stat().st_size > 44)(pl.audio_file(mode, pl.speechify(line)))]
    done = len(unique) - len(left)
    lock = threading.Lock()
    write(progress, phase="voice", done=done, total=len(unique), beats=len(lines))
    threads = max(1, int(os.environ.get("PANIM_TTS_THREADS", "8")))
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(pl.narrate, line) for line in left]
        for future in as_completed(futures):
            try:
                future.result()
            except pl.VoiceUnavailable as error:
                failed.append(str(error))
                for other in futures:
                    other.cancel()               # a refused line stops the lecture: no point paying for the rest
                continue
            with lock:
                done += 1
                write(progress, phase="voice", done=done, total=len(unique), beats=len(lines))
    if failed:
        print(json.dumps({"ok": False, "error": failed[0]}))
        return 0
    write(progress, phase="render", done=0, total=len(lines), beats=len(lines))
    print(json.dumps({"ok": True, "lines": len(unique), "spoken": len(left), "beats": len(lines)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
