"""Download every library a lecture draws on, once, and report what is ready.

    .venv/bin/python harness/scripts/fetch_all.py            # everything
    .venv/bin/python harness/scripts/fetch_all.py --skip maps

What it gets, and where it goes:

  gazetteer  GeoNames towns (about 150,000 place names)     harness/lecture/data/geonames/  ~10 MB
  maps       Natural Earth borders, states, rivers, towns   Cartopy's data folder            ~40 MB
  fonts      the styles' Google Fonts                       ~/.fonts (Linux), ~/Library/Fonts (macOS)
  latex      TinyTeX, for typeset equations (fetch_latex.py) ~/.TinyTeX, ~/Library/TinyTeX  ~250 MB

The narration voice is Gemini TTS, an online service: nothing to download, a key to set (SETUP.md).
There are no picture libraries: a lecture's pictures are made by an image model (genimage.py), drawn as SVGs, or
built in Manim. Molecules (PubChem) and PDF conversion (Datalab) are fetched per lecture, as needed.
Every step is safe to rerun: what is already here is skipped.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
LECTURE = SCRIPTS.parent / "lecture"
STEPS = ("gazetteer", "maps", "fonts", "latex")


def run(script: str) -> bool:
    return subprocess.run([sys.executable, str(SCRIPTS / script)]).returncode == 0


def maps() -> bool:
    """Natural Earth layers the map engine reads: Cartopy downloads each on first use."""
    import cartopy.io.shapereader as shpreader

    layers = [("cultural", "admin_0_countries"), ("cultural", "admin_1_states_provinces"),
              ("cultural", "populated_places"), ("physical", "rivers_lake_centerlines")]
    for category, name in layers:
        print(f"natural earth: {name}", flush=True)
        shpreader.natural_earth(resolution="10m", category=category, name=name)
    return True


def fonts() -> bool:
    sys.path.insert(0, str(LECTURE))
    import pocket_lecture

    pocket_lecture.setup_fonts()
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--skip", action="append", default=[], choices=STEPS, help="leave one out; repeat for more")
    args = ap.parse_args()
    actions = {"gazetteer": lambda: run("fetch_gazetteer.py"), "maps": maps, "fonts": fonts,
               "latex": lambda: run("fetch_latex.py")}
    report = {}
    for step in STEPS:
        if step in args.skip:
            report[step] = "skipped"
            continue
        print(f"\n== {step} ==", flush=True)
        try:
            report[step] = "ready" if actions[step]() else "FAILED"
        except Exception as error:  # noqa: BLE001 -- report it and carry on with the rest
            report[step] = f"FAILED ({error})"
    print("\n" + "\n".join(f"  {step:10} {state}" for step, state in report.items()))
    return 0 if all(not s.startswith("FAILED") for s in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
