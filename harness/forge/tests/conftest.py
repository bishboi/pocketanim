import sys
from pathlib import Path

# `forge` is a package in harness/forge; make it importable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os  # noqa: E402

# Narration is Google Chirp 3 HD only, and tests have no Google key: they build silent (the Chirp tests set a
# mock Google and PANIM_VOICE themselves). Subprocesses inherit it.
os.environ.setdefault("PANIM_VOICE", "silent")
os.environ.setdefault("FORGE_VOICE", "silent")
