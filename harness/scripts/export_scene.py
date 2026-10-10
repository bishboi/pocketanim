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
# The lecture engine, so a scene can `from pocket_lecture import *`.
sys.path.insert(0, str(REPO / "harness" / "lecture"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Without LaTeX, a scene's MathTex and Tex are drawn from Pango text rather than failing (nolatex.py).
import nolatex  # noqa: E402

nolatex.install()


FIXED_LAYOUT = re.compile(
    r"^\s*#\s*panim:\s*fixed-layout\b|^\s*def beat\(self|^from\s+pocket_lecture\s+import",
    re.M,
)



def _made_pictures() -> dict:
    """What the image model made in this process (genimage.MADE), as {count, usd, items}."""
    made = [m for m in (getattr(sys.modules.get("genimage"), "MADE", None) or []) if m.get("made")]
    return {"count": len(made), "usd": round(sum(float(m.get("usd") or 0) for m in made), 6), "items": made}

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
                    "            if type(_harness_scene_error).__name__ == 'VoiceUnavailable':\n"
                    "                raise\n"
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


def manim_cache() -> Path:
    """Where every build keeps Manim's LaTeX and text renders (PANIM_MANIM_CACHE): one folder for all of them.

    Manim keeps them under the working directory, and a build runs in its own fresh folder, so every build ran
    LaTeX again for every formula it had and Pango for every caption -- the same ones, lecture after lecture. The
    files are named by a hash of what they draw, so builds share them safely; warm_caches.py fills it at start."""
    return Path(os.environ.get("PANIM_MANIM_CACHE") or REPO / "harness" / ".cache" / "manim").resolve()


def share_caches() -> None:
    from manim import config

    cache = manim_cache()
    for key, folder in (("tex_dir", "Tex"), ("text_dir", "texts")):
        (cache / folder).mkdir(parents=True, exist_ok=True)
        config[key] = str(cache / folder)


# ---------------------------------------------------------------------------------------------------------------
# Chapters built side by side. A lecture is one scene, and its build ran on one core at about real time. Its
# chapters are split into windows, one build process each (record_scene's window: the chapters before a window
# run without recording, so it opens on the stage they left), and the windows' programs are joined in order.

CHAPTER_CALL = re.compile(r"^\s+self\.chapter\((\d+),", re.M)


def _workers() -> int:
    """How many builds at once: PANIM_BUILD_WORKERS, else the machine's cores (1 turns this off)."""
    try:
        return max(1, int(os.environ.get("PANIM_BUILD_WORKERS") or os.cpu_count() or 1))
    except ValueError:
        return 1


def _windows(source: str, workers: int) -> list[tuple[int, int]]:
    """The chapters each build records, (first, last), in order; [] when building whole is as quick. Chapters are
    weighed by their beats, so each window has about the same share of the lecture."""
    marks = list(CHAPTER_CALL.finditer(source))
    numbers = [int(m.group(1)) for m in marks]
    if workers < 2 or len(numbers) < 2 or numbers != list(range(1, len(numbers) + 1)):
        return []
    weights = []
    for k, mark in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(source)
        # A moving picture is baked frame by frame and costs several plain beats; a diagram or drawing a couple.
        weights.append(1 + source.count("self.beat(", mark.start(), end)
                       + 4 * source.count("self.sim(", mark.start(), end)
                       + 2 * sum(source.count(f"self.{op}(", mark.start(), end)
                                 for op in ("diagram", "svg_figure", "journey", "trace", "counter")))
    count = min(workers, len(numbers))
    total = sum(weights)
    windows, start, acc = [], 1, 0.0
    for k, weight in enumerate(weights, 1):
        acc += weight
        left = len(numbers) - k                              # chapters still to place
        wanted = count - len(windows) - 1                     # windows still to open after this one
        if wanted > 0 and (acc >= total * (len(windows) + 1) / count or left == wanted):
            windows.append((start, k))
            start = k + 1
    windows.append((start, len(numbers)))
    return [w for w in windows if w[0] <= w[1]]


def _name(index: int) -> str:
    """The k-th object name, as the recorder gives them (A..Z, A1..Z1, ...)."""
    letter = chr(ord("A") + index % 26)
    return letter if index < 26 else f"{letter}{index // 26}"


def _export_parallel(scene_file: Path, scene_class: str, windows: list[tuple[int, int]]) -> dict | None:
    """Build each window in its own process and join them (the working directory is the build's). None when a
    window failed: the caller builds the scene whole instead."""
    import shutil
    import subprocess

    here = Path.cwd()
    chunks = here / "dsl" / "chunks"
    shutil.rmtree(chunks, ignore_errors=True)
    library = here / "dsl" / "generated" / "library.atlas"
    library.parent.mkdir(parents=True, exist_ok=True)
    library.unlink(missing_ok=True)
    procs = []
    for k, (first, last) in enumerate(windows):
        out = chunks / f"w{k}"
        env = {**os.environ, "PANIM_CHUNK": f"{first}:{last}", "PANIM_GLYPH_LIBRARY": str(library),
               "PANIM_BUILD_WORKERS": "1"}
        procs.append((out, subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), str(scene_file), scene_class, str(out)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)))
    parts = []
    for out, proc in procs:
        stdout, stderr = proc.communicate()
        try:
            result = json.loads(stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            result = None
        if proc.returncode != 0 or not result or result.get("tier") is None or "timeline" not in result:
            sys.stderr.write(f"chapter window {out.name} failed; building the lecture whole\n{stderr[-2000:]}\n")
            return None
        parts.append((out, result))
    joined = _join(parts, scene_class)
    shutil.rmtree(chunks, ignore_errors=True)
    return joined


def _join(parts: list[tuple[Path, dict]], scene_class: str) -> dict:
    """One program from the windows' programs, in order: their objects renamed so no two share a name, their
    sounds and pictures moved to where their window starts, their assets gathered (where two windows baked the
    same artwork at different detail, the finer is kept)."""
    import shutil

    from dsl.export_dsl import PROGRAM_FPS
    from dsl.interpret import parse, timeline_frames

    generated = Path("dsl/generated")
    (generated / "assets").mkdir(parents=True, exist_ok=True)
    declarations: list[str] = []
    timeline: list[str] = []
    sounds: list = []
    images: list = []
    skipped: list[str] = []
    blockers: list[str] = []
    ai = {"count": 0, "usd": 0.0, "items": []}
    detail: dict[str, float] = {}           # asset -> the zoom it was baked for
    counter = 0
    frames = 0
    header = None
    simplified = None
    for out, result in parts:
        program_lines = result["program"].splitlines()
        header = header or program_lines[0]
        if program_lines and program_lines[0].startswith("scene 3d"):
            header = program_lines[0]
        names = {}
        for line in result["declarations"]:
            bits = line.split(" ")
            if len(bits) > 1 and bits[1] not in names:
                names[bits[1]] = _name(counter)
                counter += 1

        def renamed(line: str) -> str:
            return " ".join(names.get(token, token) for token in line.split(" "))

        declarations += [renamed(line) for line in result["declarations"]]
        timeline += [renamed(line) for line in result["timeline"]]
        offset = frames / PROGRAM_FPS
        sounds += [(at + offset, path, gain) for at, path, gain in result.get("sounds") or []]
        for image in result.get("images_track") or []:
            image = dict(image)
            image["keys"] = [[key[0] + frames, *key[1:]] for key in image["keys"]]
            images.append(image)
        frames += timeline_frames(parse("\n".join(result["timeline"]))["timeline"], PROGRAM_FPS)
        skipped += [s for s in result.get("skipped") or [] if s not in skipped]
        blockers += [b for b in result.get("blockers") or [] if b not in blockers]
        made = result.get("ai_images") or {}
        ai["count"] += made.get("count", 0)
        ai["usd"] += made.get("usd", 0.0)
        ai["items"] += made.get("items", [])
        scale = float((result.get("simplified") or {}).get("max_scale") or 1.0)
        if result.get("simplified") and (simplified is None or scale > simplified.get("max_scale", 0)):
            simplified = result["simplified"]
        for asset in (out / "dsl" / "generated" / "assets").glob("*.panm"):
            target = generated / "assets" / asset.name
            if not target.exists() or (scale > detail.get(asset.name, 0) and target.read_bytes() != asset.read_bytes()):
                shutil.copyfile(asset, target)
                detail[asset.name] = scale
        pictures = out / "dsl" / "generated" / "images"
        if pictures.is_dir():
            (generated / "images").mkdir(parents=True, exist_ok=True)
            for picture in pictures.iterdir():
                if not (generated / "images" / picture.name).exists():
                    shutil.copyfile(picture, generated / "images" / picture.name)
    program = "\n".join([header, *declarations, *timeline]) + "\n"
    return {"program": program, "sounds": sounds, "images_track": images, "skipped": skipped,
            "blockers": blockers, "ai_images": ai, "simplified": simplified, "windows": len(parts)}


def export(scene_file: Path, scene_class: str, out_dir: Path) -> dict:
    from dsl.export_dsl import decimate_assets, emit, record_scene

    out_dir.mkdir(parents=True, exist_ok=True)
    # Resolved before the chdir: everything after this is relative to the build.
    scene_file = scene_file.resolve()

    previous = Path.cwd()
    os.chdir(out_dir)
    try:
        share_caches()
        chunk = os.environ.get("PANIM_CHUNK")
        if not chunk:
            # A window's build finds the scene prepared by the build that started it (and must not write it
            # while the other windows read it).
            _install_layout(scene_file)
            scene_class = _prepare_playback(scene_file, scene_class)
        window = tuple(int(x) for x in chunk.split(":")) if chunk else None
        joined = None
        if window is None and "pocket_lecture" in scene_file.read_text():
            windows = _windows(scene_file.read_text(), _workers())
            if len(windows) > 1:
                joined = _export_parallel(scene_file, scene_class, windows)
        if joined is not None:
            program = joined["program"]
            blockers = joined["blockers"]
            rec = None
            result = {
                "scene": scene_class,
                "skipped": joined["skipped"],
                "ai_images": joined["ai_images"],
                "tier": 3 if blockers else 1,
                "blockers": blockers,
                "program": program,
                "program_bytes": len(program),
                "windows": joined["windows"],
            }
            if joined["simplified"]:
                result["simplified"] = joined["simplified"]
            Path("dsl/generated").mkdir(parents=True, exist_ok=True)
            Path(f"dsl/generated/{scene_class}.panim").write_text(program)
            sounds, images_track = joined["sounds"], joined["images_track"]
        else:
            rec = record_scene(str(scene_file), scene_class, window)
            mode = "3d" if any(
                d.startswith(("surface", "camera")) for d in rec.declarations
            ) else "2d"
            program = emit(rec, mode)
            blockers = list(dict.fromkeys(rec.blockers))

            lecture = sys.modules.get("pocket_lecture")
            result = {
                "scene": scene_class,
                # Pictures left out because they could not be drawn (pocket_lecture.Lecture.safe), with their beats.
                "skipped": list(getattr(lecture, "SKIPPED", []) or []),
                # Pictures the image model made during this build (genimage.py), and what they cost.
                "ai_images": _made_pictures(),
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
            sounds, images_track = rec.sounds, getattr(rec, "images", None)
            if window is not None:
                # A window's build hands its parts to the build that joins them (_join); it mixes no narration.
                result.update(declarations=rec.declarations, timeline=rec.timeline, sounds=rec.sounds,
                              images_track=images_track or [])
                return result
        # Assets are what the program references; naming them here saves the
        # caller from having to know the exporter's layout.
        assets = sorted(p.name for p in Path("dsl/generated/assets").glob("*.panm")) \
            if Path("dsl/generated/assets").is_dir() else []
        result["assets"] = assets
        # Photos and figures: not in the program (no verb carries pixels), but
        # the browser preview draws them from this track (scene_ir.py).
        if images_track:
            Path(f"dsl/generated/{scene_class}.images.json").write_text(json.dumps(images_track))
            result["images"] = len(images_track)
        if sounds:
            from dsl.export_dsl import PROGRAM_FPS
            from dsl.interpret import parse, timeline_frames
            from narration import mix

            frames = timeline_frames(parse(program)["timeline"], PROGRAM_FPS)
            # Beside the program, where tools/build_library looks for it.
            track = Path(f"dsl/generated/{scene_class}.narration.wav")
            result["narration"] = mix(sounds, frames / PROGRAM_FPS, track.resolve())
            result["narration"]["file"] = str(track)
        # The exporter's verdict, as `export_dsl --write` records it: the
        # library builder ships a program only with one, so a build from here
        # can be packed for the phone as it stands.
        Path(f"dsl/generated/{scene_class}.tier.json").write_text(json.dumps(
            {k: result[k] for k in ("scene", "tier", "blockers", "program_bytes")}, indent=2) + "\n")
        return result
    finally:
        os.chdir(previous)


def _where(error: BaseException, scene_file: str) -> str:
    """Where an error happened, for a one-line report: the innermost frame, and the scene's own line it was
    running (a lecture's beat), so "IndexError: too many indices" names the file, the line and the beat."""
    import traceback

    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return ""
    inner = frames[-1]
    parts = [f"at {Path(inner.filename).name}:{inner.lineno} in {inner.name}"]
    scene = Path(scene_file).name
    mine = [f for f in frames if Path(f.filename).name == scene]
    if mine and mine[-1] is not inner:
        line = (mine[-1].line or "").strip()
        parts.append(f"scene line {mine[-1].lineno}: {line[:160]}")
    return " (" + "; ".join(parts) + ")"


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
        import traceback

        traceback.print_exc(file=sys.stderr)
        print(json.dumps({
            "scene": scene_class,
            "tier": None,
            "error": f"{type(error).__name__}: {error}{_where(error, scene_file)}",
        }))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
