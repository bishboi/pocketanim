#!/bin/bash
# The app: sets up what is missing (./setup.sh), then serves it on http://localhost:8300 (or the port given).
cd "$(dirname "$0")"
ok() { [ -x ../.venv3/bin/python ] && ../.venv3/bin/python -c '
import sys, importlib.util as u
sys.exit(not ((3, 10) <= sys.version_info[:2] <= (3, 13) and all(u.find_spec(m) for m in ("manim", "piper", "faster_whisper"))))' 2>/dev/null \
  && cmp -s requirements.txt ../.venv3/requirements.installed \
  && ls .cache/voices/*.onnx >/dev/null 2>&1 && [ -d .cache/package/icons ]; }
if ! ok; then
  echo "setting up first (./setup.sh)…"
  ./setup.sh || exit 1
fi
exec ../.venv3/bin/python engine/server.py --port "${1:-8300}"
