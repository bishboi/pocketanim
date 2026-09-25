"""Speak narration lines with Kokoro and write one wav.

Reads a JSON object on stdin:
    {"voice": "af_sarah", "lines": ["First sentence.", "Second."], "out": "/tmp/narration.wav"}

Prints one JSON object:
    {"ok": true, "sample_rate": 24000, "durations": [1.8, 2.1], "out": "..."}

A missing package or a missing weight file is an ordinary result, not a crash
the page cannot explain.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = ROOT / "harness" / "models"
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"


def ensure(path: Path, url: str) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, path)


def main() -> int:
    try:
        job = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        print(json.dumps({"ok": False, "error": f"bad request: {error}"}))
        return 1

    if job.get("check"):
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            print(json.dumps({"ok": False, "error": "kokoro-onnx is not installed"}))
            return 0
        print(json.dumps({"ok": True}))
        return 0

    lines = [str(line).strip() for line in job.get("lines") or [] if str(line).strip()]
    if not lines:
        print(json.dumps({"ok": False, "error": "no narration lines"}))
        return 1

    try:
        import numpy as np
        import soundfile as sf
        from kokoro_onnx import Kokoro
    except ImportError as error:
        print(json.dumps({"ok": False, "error": f"{error}. Install with: .venv/bin/pip install kokoro-onnx soundfile"}))
        return 0

    model = WEIGHTS / "kokoro-v1.0.onnx"
    voices = WEIGHTS / "voices-v1.0.bin"
    try:
        ensure(model, MODEL_URL)
        ensure(voices, VOICES_URL)
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"could not fetch Kokoro weights: {error}"}))
        return 0

    voice = str(job.get("voice") or "af_sarah")
    out = Path(str(job.get("out") or "/tmp/pocketanim-narration.wav"))
    kokoro = Kokoro(str(model), str(voices))
    chunks = []
    durations = []
    sample_rate = 24000
    for line in lines:
        samples, sample_rate = kokoro.create(line, voice=voice, speed=1.0, lang="en-us")
        gap = np.zeros(int(sample_rate * 0.55), dtype=np.float32)
        chunks.append(gap)
        chunks.append(np.asarray(samples, dtype=np.float32))
        durations.append(round(len(samples) / sample_rate, 2))
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), np.concatenate(chunks), sample_rate)
    print(json.dumps({"ok": True, "sample_rate": sample_rate, "durations": durations, "out": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
