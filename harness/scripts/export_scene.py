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
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


FIXED_LAYOUT = re.compile(
    r"^\s*#\s*panim:\s*fixed-layout\b|^\s*def beat\(self|^from\s+pocket_lecture\s+import",
    re.M,
)


def _install_layout(scene_file: Path) -> None:
    """Run the label pass before this scene is imported for export.

    The exporter patches ``Scene.play`` and then imports the file, so the
    import itself is what installs the pass. Corpus scenes never come through
    here, and a scene that already installed it is left alone.
    """
    source = scene_file.read_text()
    if "layout_guard" in source:
        return
    # A lecture engine lays out its own panel, captions and labels on a grid
    # it computes; the guard is for placements a model guessed. Run over a
    # designed layout it shrank panel titles and pushed stacked facts apart.
    if FIXED_LAYOUT.search(source):
        return
    guard = Path(__file__).with_name("layout_guard.py")
    preamble = (
        "import importlib.util as _layout_util\n"
        f"_layout_spec = _layout_util.spec_from_file_location('layout_guard', {str(guard)!r})\n"
        "_layout_mod = _layout_util.module_from_spec(_layout_spec)\n"
        "_layout_spec.loader.exec_module(_layout_mod)\n"
        "_layout_mod.install()\n"
    )
    scene_file.write_text(preamble + source)


def _concrete_scenes(source: str) -> list[str]:
    """Scene classes that actually draw something.

    A lecture file often has an empty base such as ``Lecture(Scene)`` and the
    real films as ``S00_Intro(Lecture)``. The base has no ``construct``.
    """
    found = list(re.finditer(r"^class\s+(\w+)\s*\(([^)]*)\)\s*:", source, re.M))
    bases = {
        match.group(1): [part.strip() for part in match.group(2).split(",")]
        for match in found
    }
    roots = {"Scene", "ThreeDScene", "MovingCameraScene"}

    def is_scene(name: str, seen: tuple[str, ...] = ()) -> bool:
        if name in roots:
            return True
        if name in seen or name not in bases:
            return False
        return any(is_scene(base, seen + (name,)) for base in bases[name])

    names = []
    for index, match in enumerate(found):
        if not is_scene(match.group(1)):
            continue
        end = found[index + 1].start() if index + 1 < len(found) else len(source)
        body = source[match.end():end]
        if re.search(r"^\s+def construct\s*\(", body, re.M):
            names.append(match.group(1))
    return names


def _prepare_playback(scene_file: Path, scene_class: str) -> str:
    """Point playback at the scenes that draw, and let a lecture start.

    Narration in these files shells out to espeak-ng. When that binary is
    missing, a silent stand-in keeps the waits, so the picture still plays.
    Map data and the globe frames are built first when the file defines them.
    One scene that throws does not discard the scenes already recorded.
    """
    source = scene_file.read_text()
    scenes = _concrete_scenes(source)
    chosen = scene_class
    if scenes and chosen not in scenes:
        if len(scenes) == 1:
            chosen = scenes[0]
        else:
            chosen = "HarnessLecture"
            if "class HarnessLecture" not in source:
                base = "Lecture" if re.search(r"^class\s+Lecture\s*\(", source, re.M) else "Scene"
                calls = "\n".join(
                    "        try:\n"
                    f"            {name}.construct(self)\n"
                    "        except Exception as _harness_scene_error:\n"
                    "            print('scene skipped:', _harness_scene_error)\n"
                    "        self.clear()\n"
                    for name in scenes
                )
                source += (
                    f"\n\nclass HarnessLecture({base}):\n"
                    "    def construct(self):\n"
                    f"{calls}\n"
                )
    if "def tts(" in source and "def _harness_silent_tts" not in source:
        source += """

def _harness_silent_tts(text):
    import wave
    dur = max(0.8, len(str(text).split()) * 0.42)
    folder = globals().get("AUD") or "."
    path = __import__("os").path.join(str(folder), "harness_silence.wav")
    __import__("os").makedirs(str(folder), exist_ok=True)
    frames = b"\\x00\\x00" * int(44100 * dur)
    with wave.open(path, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(frames)
    return path, dur

tts = _harness_silent_tts
"""
    if "_harness_boot" not in source and (
        "def setup_assets(" in source or "def render_globe(" in source or "def build_rain(" in source
    ):
        source += """

def _harness_boot():
    import traceback
    here = globals()
    for name, args in (("setup_assets", ()), ("render_globe", (8,)), ("build_rain", ())):
        fn = here.get(name)
        if fn is None:
            continue
        try:
            fn(*args)
        except Exception:
            traceback.print_exc()
    globe = here.get("GLOBE")
    if globe is not None:
        from pathlib import Path
        folder = Path(globe)
        folder.mkdir(parents=True, exist_ok=True)
        if not list(folder.glob("f*.png")):
            from PIL import Image
            Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(folder / "f000.png")

_harness_boot()

from manim import Scene as _HarnessScene
from manim import Wait as _HarnessWait
_harness_prev_play = _HarnessScene.play

def _harness_play(self, *anims, **kwargs):
    try:
        return _harness_prev_play(self, *anims, **kwargs)
    except Exception as _harness_play_error:
        print("animation skipped:", _harness_play_error)
        duration = kwargs.get("run_time")
        if duration is None:
            duration = max((getattr(anim, "run_time", 1) for anim in anims), default=1)
        return _harness_prev_play(self, _HarnessWait(max(float(duration), 0.1)))

_HarnessScene.play = _harness_play
"""
    scene_file.write_text(source)
    return chosen


def export(scene_file: Path, scene_class: str, out_dir: Path) -> dict:
    from dsl.export_dsl import decimate_assets, emit, record_scene

    out_dir.mkdir(parents=True, exist_ok=True)
    # Resolved before the chdir: everything after this is relative to the build.
    scene_file = scene_file.resolve()

    previous = Path.cwd()
    os.chdir(out_dir)
    try:
        _install_layout(scene_file)
        scene_class = _prepare_playback(scene_file, scene_class)
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
            "program": program,
            "program_bytes": len(program),
        }
        # A blocker used to drop the program, so the player had nothing to draw.
        # The parts that did record still play; the blockers say what was left out.
        Path("dsl/generated").mkdir(parents=True, exist_ok=True)
        Path(f"dsl/generated/{scene_class}.panim").write_text(program)
        if not blockers:
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
