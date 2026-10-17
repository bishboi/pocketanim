"""An offline voice: espeak-ng on this machine (PANIM_TTS=espeak). v2's own, for a lecture's narration tried with no
key and no cost (and the checks): robotic, but every line is spoken, timed and aligned like a real voice's.

The same shape as the other voices (tts.py): configured(), voice_for(style), speak(text, voice, speed) -> WAV bytes,
model(), NAME, REVISION, last_cost().

Settings: PANIM_ESPEAK (the program, default espeak-ng), PANIM_ESPEAK_VOICE (default en-gb; hi for Hindi lines).
"""

from __future__ import annotations

import shutil
import subprocess

from chirp import _env

NAME = "espeak-ng (offline)"
REVISION = 1
DEFAULT_VOICE = "en-gb"


def _program() -> str | None:
    return shutil.which(_env("PANIM_ESPEAK") or "espeak-ng") or shutil.which("espeak")


def configured() -> bool:
    return _program() is not None


def model() -> str:
    return "espeak-ng"


def voice_for(style: str | None) -> str:
    return _env("PANIM_ESPEAK_VOICE") or DEFAULT_VOICE


def last_cost() -> dict:
    return {"usd": 0.0, "chars": 0}


def speak(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> bytes:
    program = _program()
    if not program:
        raise RuntimeError("espeak-ng is not installed (apt install espeak-ng)")
    if any(0x0900 <= ord(c) <= 0x097F for c in text):
        voice = "hi"
    words_a_minute = str(int(165 * max(0.5, min(2.0, speed))))
    done = subprocess.run([program, "-v", voice, "-s", words_a_minute, "--stdout", text], capture_output=True,
                          timeout=120)
    if done.returncode != 0 or len(done.stdout) <= 44:
        raise RuntimeError(f"espeak-ng could not speak the line: {done.stderr.decode('utf-8', 'replace')[:200]}")
    return done.stdout
