"""Check the local word aligner (harness/lecture/local_align.py) on real speech, in English and Hindi.

    python -m tools.check_local_align [out_dir]

Speech is made with espeak-ng (any voice will do: the aligner is told the words). Each case is two sentences with
1.5 s of silence between them, so where the second sentence begins is known: its first word must be placed after
the gap, every word in order and inside the audio. Prints one line per case and exits non-zero on a failure;
writes each case's words to out_dir.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "harness" / "lecture"))

import local_align  # noqa: E402

CASES = [
    ("en", "en", "The king granted land to his nobles.", "In return the nobles owed knights to the king."),
    ("hi", "hi", "राजा ने अपने सामंतों को ज़मीन दी।", "बदले में सामंतों ने राजा को सैनिक दिए।"),
    ("hinglish", "hi", "अब हम feudal system समझते हैं।", "इसमें king सबसे ऊपर था।"),
]
GAP = 1.5


def speak(text: str, voice: str, out: Path) -> None:
    subprocess.run(["espeak-ng", "-v", voice, "-s", "150", "-w", str(out), text], check=True)


def join(parts: list[Path], out: Path) -> tuple[float, float]:
    """The parts with GAP s of silence between them; (end of the first, start of the second) in seconds."""
    frames, rate = [], 22050
    for p in parts:
        with wave.open(str(p)) as w:
            rate = w.getframerate()
            frames.append(w.readframes(w.getnframes()))
    silence = b"\x00\x00" * int(rate * GAP)
    with wave.open(str(out), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames[0] + silence + frames[1])
    first = len(frames[0]) / 2 / rate
    return first, first + GAP


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "align-check")
    out.mkdir(parents=True, exist_ok=True)
    if not shutil.which("espeak-ng"):
        print("espeak-ng is not installed")
        return 2
    failed = 0
    for name, voice, one, two in CASES:
        a, b, both = out / f"{name}-1.wav", out / f"{name}-2.wav", out / f"{name}.wav"
        speak(one, voice, a)
        speak(two, voice, b)
        end_one, start_two = join([a, b], both)
        words = local_align.align(both, f"{one} {two}")
        if not words:
            print(f"FAIL {name}: not aligned ({local_align.problem()})")
            failed += 1
            continue
        (out / f"{name}.json").write_text(json.dumps(words, ensure_ascii=False, indent=1))
        n = len(one.split())
        second = words[n] if len(words) > n else None
        ordered = all(x["start"] <= y["start"] for x, y in zip(words, words[1:]))
        ok = (second is not None and abs(second["start"] - start_two) <= 0.4 and ordered
              and abs(words[n - 1]["end"] - end_one) <= 0.6 and len(words) == len((one + " " + two).split()))
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {len(words)} words; second sentence starts at "
              f"{second['start'] if second else None} s (spoken at {start_two:.2f} s); first ends at "
              f"{words[n - 1]['end']} s (spoken until {end_one:.2f} s); in order: {ordered}")
        print("     " + " ".join(f"{w['w']}@{w['start']}" for w in words))
        failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
