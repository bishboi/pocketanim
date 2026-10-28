#!/bin/bash
# The engine's environment, once: the system libraries (cairo, pango, pkg-config, ffmpeg, node), a Python venv in
# ../.venv3 with the packages, the line icons (Lucide, from npm) and the offline voices (Piper), into .cache.
# macOS: the libraries come from Homebrew. Linux: apt-get (with sudo).
set -e
cd "$(dirname "$0")"
T0=$SECONDS
step() { echo; echo "==> [$((SECONDS - T0)) s] $*"; }
export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# ---- system libraries
step "system libraries"
if [ "$(uname)" = "Darwin" ]; then
  if ! command -v brew >/dev/null; then
    echo "Homebrew is needed for cairo, pango and ffmpeg: install it from https://brew.sh, then run ./setup.sh again"; exit 1
  fi
  need=()
  for p in pkg-config cairo pango ffmpeg node; do brew list --formula "$p" >/dev/null 2>&1 || need+=("$p"); done
  if [ ${#need[@]} -gt 0 ]; then
    echo "brew install ${need[*]}   (ffmpeg and pango bring many dependencies: this can take 10-20 minutes the first time)"
    brew install "${need[@]}"
  else
    echo "already installed: pkg-config cairo pango ffmpeg node"
  fi
  export PKG_CONFIG_PATH="$(brew --prefix)/lib/pkgconfig:$(brew --prefix)/share/pkgconfig:${PKG_CONFIG_PATH:-}"
elif command -v apt-get >/dev/null; then
  pkgs=(libcairo2-dev libpango1.0-dev pkg-config ffmpeg)
  missing=$(for p in "${pkgs[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done)
  if [ -n "$missing" ]; then
    echo "apt-get install $missing"; sudo apt-get update -q && sudo apt-get install -y $missing
  fi
  command -v npm >/dev/null || { echo "npm (Node.js) is needed for the icons: install it, then run ./setup.sh again"; exit 1; }
fi

# ---- Python 3.10-3.13 (the voice and Whisper packages have no wheels for newer ones yet)
step "python"
PY=""
for c in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(not ((3, 10) <= sys.version_info[:2] <= (3, 13)))'; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10-3.13 is needed (found: $(python3 --version 2>&1)). macOS: brew install python@3.12; then run ./setup.sh again"
  exit 1
fi
if [ -x ../.venv3/bin/python ] && ! ../.venv3/bin/python -c 'import sys; sys.exit(not ((3, 10) <= sys.version_info[:2] <= (3, 13)))'; then
  echo "../.venv3 has an unsupported Python: remove it (rm -r ../.venv3) and run ./setup.sh again"; exit 1
fi
[ -x ../.venv3/bin/python ] || { echo "making ../.venv3 with $($PY --version)"; "$PY" -m venv ../.venv3; }
../.venv3/bin/python -m pip install -q --upgrade pip
step "python packages (manim, piper, faster-whisper: a few hundred MB; pycairo is compiled on macOS)"
../.venv3/bin/python -m pip install --progress-bar on -r requirements.txt 2>&1 | grep --line-buffered -E "^(Collecting|Building|Successfully|ERROR|error)|Downloading .*MB" || true
../.venv3/bin/python -c "import manim, piper, faster_whisper" || { echo "the Python packages did not install: run ../.venv3/bin/python -m pip install -r requirements.txt to see why"; exit 1; }

# ---- icons and voices
step "icons and voices"
mkdir -p .cache/voices
[ -d .cache/package ] || (cd .cache && npm pack lucide-static@0.454.0 >/dev/null && tar xzf lucide-static-0.454.0.tgz)
for v in en_US-ryan-high en_US-lessac-high; do
  [ -f ".cache/voices/$v.onnx" ] || (cd .cache/voices && ../../../.venv3/bin/python -m piper.download_voices "$v")
done

step "done"
echo "ready. Put your keys in harness_v3/.env.local (cp .env.example .env.local), then:"
echo "  ../.venv3/bin/python engine/server.py --port 8300      and open http://localhost:8300"
