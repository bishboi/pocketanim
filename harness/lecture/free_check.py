"""Free-form Manim in a lecture: the `manim` op, its sandbox, and its check before a render.

The beat script's drawings (sketch, the physics presets, graph...) are a menu: reliable, laid out and pointed at by
the compiler, but a banked road came out as a block on a wedge labelled "car". A beat may instead carry a short
block of Manim, written as the body of construct():

    {"say": "...", "do": [{"op": "manim", "id": "pulley", "code": "wedge = Polygon(...)\\nself.play(Create(wedge))"}]}

Beats with the same id share their variables, in order, so a figure is built over several beats and its parts
moved, ringed and transformed as each sentence is said. The engine (stem.BoardMixin.free) speaks the beat's line,
runs its block, and holds for what is left of the line; what the blocks drew leaves the board when the next
picture arrives.

Model-written code runs in a sandbox: the AST is checked here (no imports, no dunders, no files, no exec, nothing
of the scene but play, wait and add), and the code runs with Manim's names, numpy and a few builtins only. Before
a script is accepted each id's blocks are run in a probe scene under the exporter (dsl/export_dsl.record_scene),
which only steps animations to their end, so a block that raises, draws off the board, runs far longer than its
line, or uses an animation the phone cannot play is refused with the reason. Results are cached by the code.

    python free_check.py --probe groups.json result.json     (run by verify(), in a subprocess)
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CACHE = HERE / ".cache" / "free"
# Bump when the probe's checks change: cached verdicts from before are stale.
REVISION = 1

# The board a block draws on: the whole frame between the title strip and the caption (stem.BOARD).
AREA = (-6.9, 6.9, -3.05, 2.85)
SLACK = 0.15
MAX_CODE = 6000
# A block's animations may run this much longer than its line before the narration is left far behind.
OVERRUN = 2.0
OVERRUN_SECONDS = 4.0
PROBE_TIMEOUT = int(os.environ.get("PANIM_MANIM_CHECK_SECONDS", "240"))

SAFE_BUILTINS = {
    name: getattr(__builtins__, name) if not isinstance(__builtins__, dict) else __builtins__[name]
    for name in ("abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance", "len",
                 "list", "map", "max", "min", "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple",
                 "zip", "True", "False", "None", "ValueError", "ZeroDivisionError")
}
# What a block may use of the scene. Everything else (camera, mobjects, renderer, sound, clear...) belongs to the
# lecture: a block that cleared every mobject took the caption and the chapter's chrome with it.
SCENE_ALLOWED = {"play", "wait", "add", "remove", "bring_to_front", "bring_to_back"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr",
                   "setattr", "delattr", "input", "breakpoint", "help", "exit", "quit", "memoryview", "type",
                   "object", "super", "classmethod", "staticmethod", "property", "config", "os", "sys",
                   "subprocess", "Path", "shutil"}
FORBIDDEN_CALLS = {"save_image", "to_file", "write_to_file", "set_camera_orientation", "move_camera"}


def check_code(code: str) -> list[str]:
    """What is not allowed in a block, or [] when it may run."""
    if not isinstance(code, str) or not code.strip():
        return ["no code"]
    if len(code) > MAX_CODE:
        return [f"{len(code)} characters; at most {MAX_CODE}: split it over the beats that say each part"]
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        return [f"a syntax error on line {error.lineno}: {error.msg}"]
    problems: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            problems.append(f"line {line}: no imports (Manim's names and np are already there)")
        elif isinstance(node, ast.ClassDef):
            problems.append(f"line {line}: no classes (helper functions are fine)")
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await, ast.AsyncFor,
                               ast.AsyncWith, ast.Try, ast.With)):
            problems.append(f"line {line}: {type(node).__name__.lower()} is not allowed")
        elif isinstance(node, ast.While):
            problems.append(f"line {line}: no while loops (use for ... in range(...))")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                problems.append(f"line {line}: no private attributes ({node.attr})")
            elif isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr not in SCENE_ALLOWED:
                problems.append(f"line {line}: self.{node.attr} is the lecture's; a block uses self.play, "
                                "self.wait, self.add and self.remove only")
            elif node.attr in FORBIDDEN_CALLS:
                problems.append(f"line {line}: {node.attr} is not allowed")
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") or node.id in FORBIDDEN_NAMES:
                problems.append(f"line {line}: {node.id} is not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 800:
            problems.append(f"line {line}: a string of {len(node.value)} characters")
    return list(dict.fromkeys(problems))[:6]


def namespace(scene) -> dict:
    """The names a block runs with: Manim's, numpy as np, the board's bounds, the style's colours, the scene."""
    import manim
    import numpy as np

    names = {k: getattr(manim, k) for k in dir(manim) if not k.startswith("_")}
    for unsafe in ("config", "tempconfig", "logger", "console", "Scene", "ThreeDScene", "MovingCameraScene"):
        names.pop(unsafe, None)
    try:
        import pocket_lecture as pl

        ink, muted, bg = pl.P.CREAM, pl.P.MUTED, pl.P.BG
        colours = {k: getattr(pl.P, k) for k in ("SAND", "DUNE", "TERRA", "CREAM", "MUTED", "GOLD", "ROSE", "RIVER",
                                                  "TEAL", "GREEN", "VIOLET") if hasattr(pl.P, k)}
    except Exception:  # noqa: BLE001 -- the probe may run without the engine's style
        ink, muted, bg, colours = "#FFFFFF", "#9E9E9E", "#000000", {}
    names.update(np=np, self=scene, INK=ink, MUTED_INK=muted, BACKGROUND=bg, PALETTE=colours,
                 BOARD_LEFT=AREA[0], BOARD_RIGHT=AREA[1], BOARD_BOTTOM=AREA[2], BOARD_TOP=AREA[3])
    names["__builtins__"] = dict(SAFE_BUILTINS)
    return names


def run_block(code: str, names: dict, label: str) -> None:
    """Run one block in its id's names. The check runs again here: the script reached the engine through the
    compiler, but nothing else should ever run model-written code without it."""
    problems = check_code(code)
    if problems:
        raise ValueError(f"{label}: " + "; ".join(problems))
    exec(compile(code, label, "exec"), names)  # noqa: S102 -- checked above, restricted names


# ---------------------------------------------------------------- the check before a render

def blocks_of(script: dict) -> list[dict]:
    """The script's manim blocks, grouped by id in order: [{key, blocks: [{where, code, seconds}]}]."""
    import compile_lecture as cl

    groups: dict[str, dict] = {}
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            for op in beat.get("do") or []:
                if isinstance(op, dict) and op.get("op") == "manim":
                    key = free_key(op, ci)
                    group = groups.setdefault(key, {"key": key, "blocks": []})
                    group["blocks"].append({"where": f"chapter {ci} beat {bi}", "code": str(op.get("code") or ""),
                                            "seconds": round(cl._say_seconds(str(beat.get("say") or "")), 2)})
    return list(groups.values())


def free_key(op: dict, chapter: int) -> str:
    return str(op.get("id") or f"manim{chapter}")


def _digest(group: dict, style: str) -> str:
    raw = json.dumps({"r": REVISION, "s": style, "b": [[b["code"], b["seconds"]] for b in group["blocks"]]})
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def verify(script: dict) -> list[str]:
    """Errors for the script's manim blocks: the sandbox's rules, then a run of each id's blocks in a probe scene.
    Each id's verdict is cached by its code, so a script sent again with one block changed reruns that id only."""
    groups = blocks_of(script)
    if not groups:
        return []
    errors: list[str] = []
    runnable = []
    for group in groups:
        bad = False
        for block in group["blocks"]:
            problems = check_code(block["code"])
            if problems:
                bad = True
                errors.append(f"{block['where']}: the manim code is not allowed: " + "; ".join(problems))
        if not bad:
            runnable.append(group)
    if os.environ.get("PANIM_MANIM_CHECK") == "off":
        return errors
    style = str(script.get("style") or "atlas")
    CACHE.mkdir(parents=True, exist_ok=True)
    todo = []
    for group in runnable:
        cached = CACHE / f"{_digest(group, style)}.json"
        if cached.exists():
            errors += json.loads(cached.read_text())
        else:
            todo.append(group)
    if not todo:
        return errors
    with tempfile.TemporaryDirectory() as folder:
        groups_file, result_file = Path(folder) / "groups.json", Path(folder) / "result.json"
        groups_file.write_text(json.dumps({"style": style, "groups": todo}))
        try:
            run = subprocess.run([sys.executable, str(Path(__file__)), "--probe", str(groups_file), str(result_file)],
                                 cwd=str(REPO), capture_output=True, text=True, timeout=PROBE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return errors + [f"the manim blocks ({', '.join(g['key'] for g in todo)}) did not finish running in "
                             f"{PROBE_TIMEOUT} s: keep each block to a few animations"]
        if not result_file.exists():
            tail = (run.stderr or run.stdout or "").strip().splitlines()[-3:]
            return errors + ["the manim blocks could not be checked: " + " | ".join(tail)[:400]]
        results = json.loads(result_file.read_text())
    for group in todo:
        found = results.get(group["key"], [])
        (CACHE / f"{_digest(group, style)}.json").write_text(json.dumps(found))
        errors += found
    return errors


# ---------------------------------------------------------------- the probe (a subprocess)

PROBE = '''
import json, sys
sys.path.insert(0, {lecture!r})
import pocket_lecture as pl
pl.use_style({style!r})
from manim import Scene
import free_check
from dsl import export_dsl

GROUPS = json.loads({groups!r})
RESULT = {{}}


class FreeProbe(Scene):
    def construct(self):
        self.camera.background_color = pl.P.BG
        for group in GROUPS:
            RESULT[group["key"]] = free_check.probe_group(self, group, export_dsl)
            for m in list(self.mobjects):
                self.remove(m)
'''


def probe_group(scene, group: dict, export_dsl) -> list[str]:
    """Run one id's blocks in order; what each got wrong."""
    import traceback

    import numpy as np

    errors: list[str] = []
    names = namespace(scene)
    rec = getattr(export_dsl, "ACTIVE", None)
    for block in group["blocks"]:
        where = block["where"]
        before = {id(m) for m in scene.mobjects}
        blocked = len(rec.blockers) if rec is not None else 0
        start = scene.renderer.time
        try:
            run_block(block["code"], names, f"<{group['key']}>")
        except Exception as error:  # noqa: BLE001 -- the model's code: its error is the message
            frames = [f for f in traceback.extract_tb(error.__traceback__) if f.filename == f"<{group['key']}>"]
            line = f" (line {frames[-1].lineno}: {frames[-1].line or ''})" if frames else ""
            errors.append(f"{where}: the manim code failed{line}: {type(error).__name__}: {str(error)[:300]}")
            break
        spent = scene.renderer.time - start
        if rec is not None and len(rec.blockers) > blocked:
            new = list(dict.fromkeys(rec.blockers[blocked:]))
            errors.append(f"{where}: the phone player cannot play {'; '.join(new[:3])}. Use plain Create, Write, "
                          "FadeIn/FadeOut, GrowArrow, Transform, Indicate, .animate (shift, move_to, next_to, scale, "
                          "rotate, set_color, set_opacity) with the default rate function")
        if spent > block["seconds"] * OVERRUN + OVERRUN_SECONDS:
            errors.append(f"{where}: its animations run {spent:.1f} s but its line is said in about "
                          f"{block['seconds']:.1f} s: keep a block to what its sentence says, and put the rest on "
                          "the next beats")
        x0, x1, y0, y1 = AREA
        for m in scene.mobjects:
            if id(m) in before or not len(m.get_family()):
                continue
            try:
                if not m.has_points() and not any(s.has_points() for s in m.get_family()):
                    continue
                lo, hi = m.get_corner(np.array([-1, -1, 0])), m.get_corner(np.array([1, 1, 0]))
            except Exception:  # noqa: BLE001
                continue
            if lo[0] < x0 - SLACK or hi[0] > x1 + SLACK or lo[1] < y0 - SLACK or hi[1] > y1 + SLACK:
                errors.append(f"{where}: a {type(m).__name__} reaches ({lo[0]:.1f}, {lo[1]:.1f})-({hi[0]:.1f}, "
                              f"{hi[1]:.1f}), off the board: keep everything in x {x0} to {x1}, y {y0} to {y1} "
                              "(the title strip is above, the caption below)")
                break
    return errors[:6]


def _probe_main(groups_file: str, result_file: str) -> int:
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(REPO / "harness" / "scripts"))
    os.environ.setdefault("PANIM_VOICE", "silent")
    try:
        import nolatex

        nolatex.install()
    except Exception:  # noqa: BLE001 -- with LaTeX installed it is not needed
        pass
    data = json.loads(Path(groups_file).read_text())
    from dsl import export_dsl

    with tempfile.TemporaryDirectory() as folder:
        scene_file = Path(folder) / "free_probe.py"
        scene_file.write_text(PROBE.format(lecture=str(HERE), style=data["style"], groups=json.dumps(data["groups"])))
        cwd = os.getcwd()
        os.chdir(folder)        # the exporter writes its assets beside the scene, never into the corpus
        try:
            export_dsl.record_scene(str(scene_file), "FreeProbe")
            module = sys.modules.get("free_probe")
            result = module.RESULT if module else {}
        except Exception as error:  # noqa: BLE001
            module = sys.modules.get("free_probe")
            result = dict(module.RESULT) if module else {}
            for group in data["groups"]:
                result.setdefault(group["key"], [f"{group['blocks'][0]['where']}: the manim code could not run: "
                                                 f"{type(error).__name__}: {str(error)[:300]}"])
        finally:
            os.chdir(cwd)
    for group in data["groups"]:
        result.setdefault(group["key"], [])
    Path(result_file).write_text(json.dumps(result))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--probe":
        raise SystemExit(_probe_main(sys.argv[2], sys.argv[3]))
    print(__doc__)
