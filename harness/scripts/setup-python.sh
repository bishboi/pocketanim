#!/bin/sh
# Create the repo venv the harness already looks for, and install Manim into it.
#
# The Next app shells out to ../../.venv/bin/python. Without that interpreter,
# export dies on `import manim` inside the system Python, which does not have it.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

pick_python() {
  for candidate in python3.13 python3.12 python3.11 python3.14 python3; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
      command -v "$candidate"
      return 0
    fi
  done
  echo "Manim 0.21 needs Python 3.11 or newer. Install it, then rerun this script." >&2
  echo "  brew install python@3.13" >&2
  return 1
}

PY=$(pick_python)
echo "Using $PY ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"

if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  "$PY" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r harness/requirements.txt
.venv/bin/python -c 'import manim; print("manim", manim.__version__)'

# The place-name gazetteer lectures look towns up in (about 10 MB, once).
# A failed download is not fatal: the engine falls back to Natural Earth.
if [ ! -s harness/lecture/data/geonames/cities.txt ]; then
  .venv/bin/python harness/scripts/fetch_gazetteer.py || echo "Gazetteer not downloaded; rerun harness/scripts/fetch_gazetteer.py later."
fi

# The icon library lectures draw crops, minerals and animals from (about 53 MB, once).
if [ ! -s harness/lecture/data/icons/game-icons.json ]; then
  .venv/bin/python harness/scripts/fetch_icons.py || echo "Icons not downloaded; rerun harness/scripts/fetch_icons.py later."
fi
