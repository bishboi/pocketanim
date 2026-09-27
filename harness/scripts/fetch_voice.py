"""Download Kokoro-82M, the voice lectures speak with (about 350 MB), installing kokoro-onnx if needed.

Without it a lecture falls back to espeak-ng, and with neither its video is silent.

    .venv/bin/python harness/scripts/fetch_voice.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kokoro_speak import MODEL_URL, VOICES_URL, WEIGHTS, ensure  # noqa: E402


def main() -> int:
    missing = [p for p in ("kokoro_onnx", "soundfile") if importlib.util.find_spec(p) is None]
    if missing:
        print(f"installing {', '.join(missing)}", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kokoro-onnx", "soundfile"], check=True)
    for name, url in (("kokoro-v1.0.onnx", MODEL_URL), ("voices-v1.0.bin", VOICES_URL)):
        path = WEIGHTS / name
        if path.exists() and path.stat().st_size < 1_000_000:
            path.unlink()                      # a partial download from an earlier attempt
        print(f"{name}: {'already here' if path.exists() else 'downloading'}", flush=True)
        try:
            ensure(path, url)
        except Exception as error:  # noqa: BLE001
            path.unlink(missing_ok=True)
            print(f"could not download {name}: {error}", file=sys.stderr)
            return 1
    print(f"Kokoro is ready in {WEIGHTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
