import sys
from pathlib import Path

# `forge` is a package in harness/forge; make it importable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os  # noqa: E402

# Narration is Gemini 3.8 Flash TTS (or Chirp 3 HD), and tests have no Google key: they build silent (the voice tests set a
# mock Google and PANIM_VOICE themselves). Subprocesses inherit it.
os.environ.setdefault("PANIM_VOICE", "silent")
os.environ.setdefault("FORGE_VOICE", "silent")
# Settings from harness/app/.env.local stay out of tests (chirp._env reads it for terminal commands).
os.environ.setdefault("PANIM_ENV_FILE", "")
