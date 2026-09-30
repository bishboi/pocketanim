"""Speak a scene's narration lines with the narration voice (Gemini 3.8 Flash TTS; Chirp 3 HD with PANIM_TTS=chirp)
and write one wav, plus one per line.

Reads a JSON object on stdin:
    {"lines": ["First sentence.", "Second."], "out": "/tmp/narration.wav", "style": "vox", "voice"?: "Kore",
     "speed"?: 0.9}

Prints one JSON object:
    {"ok": true, "sample_rate": 24000, "durations": [1.8, 2.1], "files": [...], "out": "..."}
or {"ok": false, "error": "..."} when the voice is not set up or Google refuses a line: there is no other voice.
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness" / "lecture"))

import tts  # noqa: E402

voice_engine = tts.engine()

GAP = 0.55          # seconds of silence before each line in the joined track


def main() -> int:
    try:
        job = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        print(json.dumps({"ok": False, "error": f"bad request: {error}"}))
        return 1
    if job.get("check"):
        print(json.dumps({"ok": voice_engine.configured()}))
        return 0
    lines = [str(line).strip() for line in job.get("lines") or [] if str(line).strip()]
    if not lines:
        print(json.dumps({"ok": False, "error": "no narration lines"}))
        return 1
    if not voice_engine.configured():
        print(json.dumps({"ok": False, "error": tts.setup_hint()}))
        return 0
    out = Path(str(job.get("out") or "/tmp/pocketanim-narration.wav"))
    out.parent.mkdir(parents=True, exist_ok=True)
    voice = str(job.get("voice") or job.get("chirp_voice") or voice_engine.voice_for(job.get("style")))
    files, durations, frames = [], [], []
    rate = voice_engine.SAMPLE_RATE
    try:
        for index, line in enumerate(lines):
            part = out.with_name(f"{out.stem}-{index:03d}.wav")
            part.write_bytes(voice_engine.speak(line, voice, float(job.get("speed") or 1.0)))
            with wave.open(str(part)) as handle:
                rate = handle.getframerate()
                data = handle.readframes(handle.getnframes())
                durations.append(round(handle.getnframes() / rate, 2))
            frames.append(b"\x00\x00" * int(rate * GAP) + data)
            files.append(str(part))
    except RuntimeError as error:
        print(json.dumps({"ok": False, "error": f"{voice_engine.NAME} could not speak: {error}"}))
        return 0
    with wave.open(str(out), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(frames))
    print(json.dumps({"ok": True, "engine": tts.engine_name(), "sample_rate": rate, "durations": durations, "files": files,
                      "out": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
