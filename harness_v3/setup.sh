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
ok() { "$1" -c 'import sys; sys.exit(not ((3, 10) <= sys.version_info[:2] <= (3, 13)))' 2>/dev/null; }
find_py() {
  PY=""
  for c in python3.12 python3.11 python3.13 python3.10 python3 \
           /opt/homebrew/opt/python@3.12/bin/python3.12 /usr/local/opt/python@3.12/bin/python3.12; do
    if command -v "$c" >/dev/null && ok "$c"; then PY="$(command -v "$c")"; return; fi
  done
}
find_py
if [ -z "$PY" ] && [ "$(uname)" = "Darwin" ]; then
  echo "no Python 3.10-3.13 (found $(python3 --version 2>&1)): brew install python@3.12"
  brew install python@3.12
  find_py
fi
if [ -z "$PY" ]; then
  echo "Python 3.10-3.13 is needed (found: $(python3 --version 2>&1)): install python 3.12, then run ./setup.sh again"
  exit 1
fi
if [ -x ../.venv3/bin/python ] && ! ok ../.venv3/bin/python; then
  echo "../.venv3 was made with $(../.venv3/bin/python --version 2>&1), which the voice cannot use: making it again"
  rm -rf ../.venv3
fi
[ -x ../.venv3/bin/python ] || { echo "making ../.venv3 with $($PY --version)"; "$PY" -m venv ../.venv3; }
../.venv3/bin/python -m pip install -q --upgrade pip
step "python packages (manim, piper, faster-whisper: a few hundred MB; pycairo is compiled on macOS)"
../.venv3/bin/python -m pip install --progress-bar on -r requirements.txt 2>&1 | grep --line-buffered -E "^(Collecting|Building|Successfully|ERROR|error)|Downloading .*MB" || true
../.venv3/bin/python -c "import manim, piper, faster_whisper" || { echo "the Python packages did not install: run ../.venv3/bin/python -m pip install -r requirements.txt to see why"; exit 1; }
cp requirements.txt ../.venv3/requirements.installed   # start.sh sets up again when requirements.txt changes

# ---- icons and voices
step "icons and voices"
mkdir -p .cache/voices
[ -d .cache/package ] || (cd .cache && npm pack --silent lucide-static@0.454.0 >/dev/null 2>&1 && tar xzf lucide-static-0.454.0.tgz)
# The kit: its fonts (headlines, labels, body) and the world's flags (exact, never made by a model).
mkdir -p .cache/fonts
GF=https://raw.githubusercontent.com/google/fonts/main/ofl
for f in "oswald/Oswald%5Bwght%5D.ttf:Oswald[wght].ttf" "ibmplexmono/IBMPlexMono-Medium.ttf:IBMPlexMono-Medium.ttf" \
         "ibmplexmono/IBMPlexMono-Regular.ttf:IBMPlexMono-Regular.ttf" "inter/Inter%5Bopsz,wght%5D.ttf:Inter.ttf"; do
  [ -f ".cache/fonts/${f#*:}" ] || curl -sfL -o ".cache/fonts/${f#*:}" "$GF/${f%%:*}" || echo "could not fetch the font ${f#*:}"
done
[ -d .cache/flagpkg/package/flags ] || (cd .cache && npm pack --silent flag-icons@7.2.3 >/dev/null 2>&1 && mkdir -p flagpkg \
  && tar xzf flag-icons-7.2.3.tgz -C flagpkg)
# Real maps: Natural Earth's countries, coasts, seas, rivers and towns (about 25 MB, once; a year's borders come later).
# Each file at most 3 minutes; one that does not come is fetched when a map first needs it.
step "map data (about 25 MB, once)"
mkdir -p .cache/geo
NE=https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson
for f in ne_50m_admin_0_countries ne_50m_admin_0_map_units ne_10m_populated_places_simple ne_50m_rivers_lake_centerlines \
         ne_10m_geography_marine_polys ne_50m_geography_regions_points ne_10m_admin_0_countries; do
  [ -f ".cache/geo/$f.geojson" ] && continue
  echo "  $f"
  curl -fL --connect-timeout 15 --max-time 180 --progress-bar -o ".cache/geo/$f.part" "$NE/$f.geojson" \
    && mv ".cache/geo/$f.part" ".cache/geo/$f.geojson" || { rm -f ".cache/geo/$f.part"; echo "  could not fetch $f (it is fetched when a map first needs it)"; }
done
step "browser for the player export, voices"
# The player's MP4 export runs the player in headless Chromium (Playwright's own, about 150 MB, once).
../.venv3/bin/python -m playwright install chromium >/dev/null 2>&1 || echo "could not fetch Chromium for the player export (python -m playwright install chromium)"
for v in en_US-ryan-high en_US-lessac-high; do
  [ -f ".cache/voices/$v.onnx" ] || (cd .cache/voices && ../../../.venv3/bin/python -m piper.download_voices "$v")
done

step "done"
echo "ready. Put your keys in harness_v3/.env.local (cp .env.example .env.local), then:"
echo "  ../.venv3/bin/python engine/server.py --port 8300      and open http://localhost:8300"
