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


def espeak_lines(lines: list[str], out: Path) -> dict | None:
    """The same result from espeak-ng, when Kokoro cannot run here.

    Robotic, but offline and instant, and a scene with a voice beats a scene
    with an error where its voice should be. None if espeak is missing too.
    """
    import shutil
    import subprocess
    import wave

    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    files, durations, frames = [], [], []
    rate = 22050
    for index, line in enumerate(lines):
        part = out.with_name(f"{out.stem}-{index:03d}.wav")
        subprocess.run([binary, "-v", "en-gb", "-s", "148", "-w", str(part), line], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        with wave.open(str(part)) as handle:
            rate = handle.getframerate()
            data = handle.readframes(handle.getnframes())
            durations.append(round(handle.getnframes() / rate, 2))
        frames.append(b"\x00\x00" * int(rate * 0.55) + data)
        files.append(str(part))
    with wave.open(str(out), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(frames))
    return {"ok": True, "engine": "espeak", "sample_rate": rate, "durations": durations, "files": files,
            "out": str(out)}


def fallback(lines: list[str], out: Path, reason: str) -> int:
    result = espeak_lines(lines, out)
    if result is None:
        print(json.dumps({"ok": False, "error": reason}))
        return 0
    result["note"] = f"Kokoro unavailable ({reason}); spoken with espeak-ng"
    print(json.dumps(result))
    return 0


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

    out = Path(str(job.get("out") or "/tmp/pocketanim-narration.wav"))
    try:
        import numpy as np
        import soundfile as sf
        from kokoro_onnx import Kokoro
    except ImportError as error:
        return fallback(lines, out, f"{error}. Install with: .venv/bin/pip install kokoro-onnx soundfile")

    model = WEIGHTS / "kokoro-v1.0.onnx"
    voices = WEIGHTS / "voices-v1.0.bin"
    try:
        ensure(model, MODEL_URL)
        ensure(voices, VOICES_URL)
    except Exception as error:  # noqa: BLE001
        # A partial download would be mistaken for weights next time.
        for weight in (model, voices):
            if weight.exists() and weight.stat().st_size < 1_000_000:
                weight.unlink()
        return fallback(lines, out, f"could not fetch Kokoro weights: {error}")

    voice = str(job.get("voice") or "af_sarah")
    kokoro = Kokoro(str(model), str(voices))
    chunks = []
    durations = []
    files = []
    sample_rate = 24000
    out.parent.mkdir(parents=True, exist_ok=True)
    for index, line in enumerate(lines):
        samples, sample_rate = kokoro.create(line, voice=voice, speed=1.0, lang="en-us")
        samples = np.asarray(samples, dtype=np.float32)
        gap = np.zeros(int(sample_rate * 0.55), dtype=np.float32)
        chunks.append(gap)
        chunks.append(samples)
        durations.append(round(len(samples) / sample_rate, 2))
        # One file per line as well, so the scene can start each where its
        # beat starts (self.add_sound) rather than as one track from t=0.
        part = out.with_name(f"{out.stem}-{index:03d}.wav")
        sf.write(str(part), samples, sample_rate, subtype="PCM_16")
        files.append(str(part))
    sf.write(str(out), np.concatenate(chunks), sample_rate, subtype="PCM_16")
    print(json.dumps({"ok": True, "sample_rate": sample_rate, "durations": durations, "files": files,
                      "out": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
