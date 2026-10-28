#!/bin/bash
# The engine's environment: Python packages (needs libcairo2-dev, libpango1.0-dev, pkg-config, ffmpeg), the line
# icons (Lucide, from npm) and an offline voice (Piper), into harness_v3/.cache.
set -e
cd "$(dirname "$0")"
python3 -m venv ../.venv3
../.venv3/bin/pip install -q -r requirements.txt
mkdir -p .cache/voices
(cd .cache && npm pack lucide-static@0.454.0 >/dev/null && tar xzf lucide-static-0.454.0.tgz)
(cd .cache/voices && ../../../.venv3/bin/python -m piper.download_voices en_US-ryan-high)
