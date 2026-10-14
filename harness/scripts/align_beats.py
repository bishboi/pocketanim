"""Time a lecture scene's animations to its narration, after the voice has said every line (scripts/prespeak.py).

    .venv/bin/python harness/scripts/align_beats.py scene.py out.py

Writes the scene with its timing slots filled in (harness/lecture/align_cues.py) to out.py; the last line of
stdout is {"ok": true, "beats": B, "timed": T, "aligned": A, "usd": x, "model": m} (or {"ok": false, "error"}).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness" / "lecture"))


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    style = re.search(r"""os\.environ\.setdefault\(\s*["']LECTURE_STYLE["']\s*,\s*["'](\w+)["']""", source)
    if style:
        import os

        os.environ.setdefault("LECTURE_STYLE", style.group(1))
    import align_cues
    import pocket_lecture as pl

    try:
        mode = pl.voice_mode()
    except pl.VoiceUnavailable as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 0
    if mode == "silent" or not align_cues.enabled(mode.split(":", 1)[0]):
        Path(sys.argv[2]).write_text(source, encoding="utf-8")
        print(json.dumps({"ok": True, "beats": 0, "timed": 0, "aligned": 0, "usd": 0.0, "model": None}))
        return 0

    def seconds_of(text: str):
        return pl._cached_seconds(pl.audio_file(mode, pl.speechify(text)))

    aligned, report = align_cues.align(source, pl.line_words, seconds_of)
    Path(sys.argv[2]).write_text(aligned, encoding="utf-8")
    print(json.dumps({"ok": True, **report}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
