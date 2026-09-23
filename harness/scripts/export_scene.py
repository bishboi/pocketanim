"""Export one generated Manim scene to a pocketanim program, as JSON.

The harness's output is not a video. It is the same artifact the phone already
plays: a `.panim` program plus its baked assets. So the harness does not need a
renderer -- it needs the exporter that is already in this repo, addressed as a
tool rather than as a command-line program.

Two things the CLI in `dsl/export_dsl.py` does that a harness cannot live with:

* It writes into `dsl/generated`, which is the corpus. A generated scene must
  not land there, so this runs with the working directory set to the build's
  own output directory. Every relative path the exporter writes -- assets, the
  glyph atlas -- follows it, which is why the chdir is the isolation rather
  than a convenience.
* It prints prose. This prints one JSON object, so the caller gets the tier and
  the blockers as data. The blockers are the whole point: a blocker means the
  scene is honest about falling to tier 3, and an empty list with tier 1 is the
  only combination that means the program is faithful.

Usage:
    python harness/scripts/export_scene.py <scene.py> <SceneClass> <out_dir>
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def export(scene_file: Path, scene_class: str, out_dir: Path) -> dict:
    from dsl.export_dsl import decimate_assets, emit, record_scene

    out_dir.mkdir(parents=True, exist_ok=True)
    # Resolved before the chdir: everything after this is relative to the build.
    scene_file = scene_file.resolve()

    previous = Path.cwd()
    os.chdir(out_dir)
    try:
        rec = record_scene(str(scene_file), scene_class)
        mode = "3d" if any(
            d.startswith(("surface", "camera")) for d in rec.declarations
        ) else "2d"
        program = emit(rec, mode)
        blockers = list(dict.fromkeys(rec.blockers))

        result = {
            "scene": scene_class,
            "tier": 3 if blockers else 1,
            "blockers": blockers,
            "program": None if blockers else program,
            "program_bytes": 0 if blockers else len(program),
        }
        if not blockers:
            Path("dsl/generated").mkdir(parents=True, exist_ok=True)
            Path(f"dsl/generated/{scene_class}.panim").write_text(program)
            simplified = decimate_assets(rec, program)
            if simplified:
                result["simplified"] = simplified
        # Assets are what the program references; naming them here saves the
        # caller from having to know the exporter's layout.
        assets = sorted(p.name for p in Path("dsl/generated/assets").glob("*.panm")) \
            if Path("dsl/generated/assets").is_dir() else []
        result["assets"] = assets
        return result
    finally:
        os.chdir(previous)


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    scene_file, scene_class, out_dir = sys.argv[1:4]
    try:
        result = export(Path(scene_file), scene_class, Path(out_dir))
    except Exception as error:  # noqa: BLE001 -- the caller wants the reason
        # A generated scene that does not even import is an ordinary outcome
        # here, not a crash: it is the first thing the edit loop has to report.
        print(json.dumps({
            "scene": scene_class,
            "tier": None,
            "error": f"{type(error).__name__}: {error}",
        }))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
