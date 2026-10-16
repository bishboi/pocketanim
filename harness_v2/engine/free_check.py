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
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CACHE = HERE / ".cache" / "free"
# Bump when the probe's checks change: cached verdicts from before are stale.
REVISION = 2

# The board a block draws on: the whole frame between the title strip and the caption (stem.BOARD).
AREA = (-6.9, 6.9, -3.05, 2.85)
SLACK = 0.15
MAX_CODE = 6000
# Quality: words must read on a phone. Text below this font size is too small (a 6-inch phone shows the board's
# 14 units in about 13 cm).
MIN_FONT = 20
# Two pieces of text whose boxes share more than this part of the smaller one overlap.
TEXT_OVERLAP = 0.12
# A line crossing the middle of a piece of text (its box shrunk by this much on each side) runs through the words.
TEXT_CORE = 0.2
# A block's animations may run this much longer than its line before the narration is left far behind.
OVERRUN = 2.0
OVERRUN_SECONDS = 4.0
PROBE_TIMEOUT = int(os.environ.get("PANIM_MANIM_CHECK_SECONDS", "120"))
# Probe processes at once: a script's blocks are checked in parallel, each process a share of them, so one slow
# block no longer holds up (or times out) the rest.
PROBE_PARALLEL = max(1, int(os.environ.get("PANIM_MANIM_CHECK_PARALLEL", "4") or 4))
# When the probes were at work ([start, end], ms since the epoch), for the lecture's timing.
SPANS: list[list[float]] = []

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
    # Counted without its comments and blank lines: explaining the code does not make it too long.
    size = sum(len(line.rstrip()) + 1 for line in code.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    if size > MAX_CODE:
        return [f"{size} characters (without comments); at most {MAX_CODE}: split it over the beats that say each part"]
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


def _named_parts(mob, path: str, labels) -> list:
    """Name tags for a picture's parts, each on the part where the label finder saw it (genimage.locate), drawn over
    the picture; none when the finder cannot be asked."""
    import manim

    try:
        import genimage
        import pocket_lecture as pl

        found = genimage.locate(path, [str(x) for x in labels]) or []
    except Exception:  # noqa: BLE001 -- no label finder: the picture without names, rather than guessed ones
        return []
    lo, hi = mob.get_corner(manim.DL), mob.get_corner(manim.UR)
    tags = []
    for entry in found:
        if len(entry) < 3:
            continue
        name, x, y = str(entry[0]), float(entry[1]), float(entry[2])
        point = [lo[0] + x * (hi[0] - lo[0]), hi[1] - y * (hi[1] - lo[1]), 0]
        tag = pl.Lecture._label_tag(None, name, 3.2, 18)
        tag.move_to(point)
        tag.shift(manim.UP * min(0.3, max(0.0, hi[1] - tag.get_top()[1])))
        tag.set_z_index(1)
        tags.append(tag)
    return tags


def picture(what: str, height: float = 2.0, width: float | None = None, labels=None):
    """A picture of a real thing for a block (`picture("a steam locomotive, side view", height=2)`): the cutout the
    illustration model made in the lecture's style -- the same one a diagram's node or a map's label would show --
    at most `height` tall and `width` wide. The compiler has it made before the block runs (pictures_in). Where it
    could not be made, a labelled frame of the same size stands in, so the figure still reads."""
    import manim

    width = float(width) if width else float(height) * 1.8
    try:
        import pocket_lecture as pl

        path = pl.thing_picture(str(what))
        mob = pl.cutout_mob(path, width, float(height))
        # Under the block's own lines and words: drawn after them, it hid the lines pointing at it.
        mob.set_z_index(-0.5)
        tags = _named_parts(mob, path, labels) if labels else []
        if tags:
            named = manim.Group(mob, *tags)
            named.panim_picture = str(what)
            return named
    except Exception:  # noqa: BLE001 -- not made (no image model, refused, offline): a stand-in, not a crash
        frame = manim.RoundedRectangle(corner_radius=0.1, width=width * 0.8, height=float(height) * 0.8,
                                       stroke_opacity=0.6, stroke_width=2)
        words = manim.Text(str(what)[:40], font_size=20)
        if words.width > frame.width - 0.2:
            words.scale_to_fit_width(frame.width - 0.2)
        mob = manim.VGroup(frame, words)
    mob.panim_picture = str(what)
    return mob


def pictures_in(code: str | None) -> list[str]:
    """The pictures a block asks for (`picture("...")` with the description written out), to be made first."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "picture":
            arg = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "what"), None)
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.strip():
                out.append(arg.value.strip())
    return list(dict.fromkeys(out))


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
    # Words on a patch of the board, so a line or another equation under them never makes them unreadable.
    import backed_text

    names.update(backed_text.classes(bg))
    names["picture"] = picture
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


# ---------------------------------------------------------------- the quick reading of a figure's code
#
# Two mistakes that break a block in the render, found by reading the code (no Manim runs, so it costs nothing and
# stays on when the probe is switched off, PANIM_MANIM_CHECK=off): a name a later beat uses that no block of the
# figure made where later beats can see it, and a keyword a Manim class does not take (Circle(width=2)). Only what
# would surely fail is reported: anything the reading cannot be sure of is let through, for the render to find.

# Errors reported for one block at most: the first few say what is wrong; the model mends the rest with them.
MAX_STATIC = 3


_NAMES: dict | None = None


def _namespace_values() -> dict:
    """The names a block runs with before it makes any of its own (namespace()), with the builtins it may use."""
    global _NAMES
    if _NAMES is None:
        try:
            _NAMES = {**namespace(None), **SAFE_BUILTINS}
        except Exception:  # noqa: BLE001 -- without Manim nothing can be said of names: none are reported
            _NAMES = {}
    return _NAMES


def _top_level_names(tree: ast.Module) -> set[str]:
    """Names a block leaves for the beats after it: made at its top level (in an if or a for too), not inside a
    function or a comprehension."""
    made: set[str] = set()

    def visit(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                made.add(node.name)
                continue
            for sub in _walk_outside_scopes(node):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    made.add(sub.id)
            for field in ("body", "orelse"):
                inner = getattr(node, field, None)
                if isinstance(inner, list):
                    visit(inner)

    visit(tree.body)
    return made


def _walk_outside_scopes(node):
    """The node and what is under it, but not inside a function, a lambda or a comprehension (their own names)."""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ListComp, ast.SetComp,
                              ast.DictComp, ast.GeneratorExp, ast.stmt)):
            continue
        yield from _walk_outside_scopes(child)


def _any_names(tree: ast.Module) -> set[str]:
    """Every name the block binds anywhere: a variable, a function's parameter, a loop's or comprehension's."""
    made: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            made.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            made.add(node.name)
        elif isinstance(node, ast.arg):
            made.add(node.arg)
        elif isinstance(node, ast.alias):
            made.add((node.asname or node.name).split(".")[0])
    return made


_KEYWORDS: dict = {}


def _keywords_of(cls) -> set[str] | None:
    """The keywords a Manim class takes, from its __init__ and those it hands its other keywords up to; None when
    that cannot be known for sure (an __init__ that takes **kwargs and the chain ends without saying)."""
    if cls in _KEYWORDS:
        return _KEYWORDS[cls]
    import inspect

    taken: set[str] = set()
    closed = False
    for klass in cls.__mro__:
        init = klass.__dict__.get("__init__")
        if init is None or klass is object:
            continue
        try:
            params = inspect.signature(init).parameters.values()
        except (TypeError, ValueError):
            break
        taken |= {p.name for p in params if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}
        try:
            # A keyword an __init__ reads out of its **kwargs by name ("kwargs.pop('width')") is taken too.
            source = inspect.getsource(init)
            taken |= set(_QUOTED.findall(source))
        except (OSError, TypeError):
            pass
        if not any(p.kind == p.VAR_KEYWORD for p in params):
            closed = True
            break
    _KEYWORDS[cls] = taken if closed else None
    return _KEYWORDS[cls]


_QUOTED = re.compile(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""")

# What to write instead of a keyword a shape does not take, when it is one the model reaches for often.
_INSTEAD = {"width": "make it, then .scale_to_fit_width(w) (or a size keyword the class takes)",
            "height": "make it, then .scale_to_fit_height(h) (or a size keyword the class takes)",
            "size": "make it, then .scale(k) or .scale_to_fit_width(w)",
            "position": "make it, then .move_to([x, y, 0])", "pos": "make it, then .move_to([x, y, 0])",
            "center": "make it, then .move_to([x, y, 0])", "opacity": "fill_opacity= or stroke_opacity=",
            "fill": "fill_color= (with fill_opacity=)", "thickness": "stroke_width=", "line_width": "stroke_width=",
            "text_color": "color=", "fontsize": "font_size=", "size_font": "font_size="}


def static_problems(group: dict) -> list[str]:
    """What surely breaks a figure's blocks, read from their code: a name used before any block of the figure made
    it where it can be seen, and a keyword a Manim class does not take. Each: "<where>: the manim block ..."."""
    names = _namespace_values()
    if not names:
        return []
    import manim

    seen: set[str] = set()                  # made at the top level of the figure's earlier blocks
    hidden: dict[str, str] = {}             # made only inside a function or loop of an earlier block: where
    problems: list[str] = []
    for block in group["blocks"]:
        try:
            tree = ast.parse(block["code"])
        except SyntaxError:
            return problems                 # check_code says so
        own = _any_names(tree)
        found: list[str] = []
        # A name inside a function is looked up when the function is called, perhaps after a later beat made it:
        # only names read where the block runs them are sure to fail.
        in_functions = {id(n) for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.Lambda))
                        for n in ast.walk(f)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and id(node) not in in_functions:
                name = node.id
                if name in names or name in seen or name in own or any(f" uses {name} " in f for f in found):
                    continue
                if name in hidden:
                    found.append(f"{block['where']}: the manim block uses {name} (line {node.lineno}), but "
                                 f"{hidden[name]} makes {name} only inside a function or a comprehension, where "
                                 "later beats cannot see it (NameError): make it at the top level of that block "
                                 "(or return it and assign the result), or make it again here before using it")
                else:
                    found.append(f"{block['where']}: the manim block uses {name} (line {node.lineno}), which no "
                                 f"block of the figure {group['key']!r} made before (NameError): make it at the "
                                 "top level of this block or an earlier beat's block of the same figure, or use a "
                                 "name Manim has")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.keywords:
                cls = names.get(node.func.id)
                if node.func.id in own or not isinstance(cls, type) or not issubclass(cls, manim.Mobject):
                    continue
                takes = _keywords_of(cls)
                if takes is None:
                    continue
                for kw in node.keywords:
                    if kw.arg is None or kw.arg in takes:
                        continue
                    advice = _INSTEAD.get(kw.arg)
                    found.append(f"{block['where']}: the manim block calls {node.func.id}({kw.arg}=...) (line "
                                 f"{node.lineno}), but {node.func.id} takes no keyword {kw.arg!r} (TypeError: "
                                 "unexpected keyword argument)" + (f": {advice}" if advice else
                                 f"; it takes {', '.join(sorted(k for k in takes if not k.startswith('_'))[:14])}"))
        problems += found[:MAX_STATIC]
        top = _top_level_names(tree)
        seen |= top
        for name in own - top - seen:
            hidden.setdefault(name, block["where"].replace("chapter", "the block of chapter"))
    return problems


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
        # No probe: what surely breaks a block is read from its code instead (the probe, when it runs, finds the
        # same in the run and says more).
        for group in runnable:
            errors += static_problems(group)
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
    shares = [todo[k::PROBE_PARALLEL] for k in range(min(PROBE_PARALLEL, len(todo)))]

    def probe(share: list) -> list[str]:
        """One probe process for a share of the blocks: their errors, each id's verdict cached."""
        import time

        start = time.time() * 1000
        try:
            with tempfile.TemporaryDirectory() as folder:
                groups_file, result_file = Path(folder) / "groups.json", Path(folder) / "result.json"
                groups_file.write_text(json.dumps({"style": style, "groups": share}))
                try:
                    run = subprocess.run([sys.executable, str(Path(__file__)), "--probe", str(groups_file),
                                          str(result_file)], cwd=str(REPO), capture_output=True, text=True,
                                         timeout=PROBE_TIMEOUT)
                except subprocess.TimeoutExpired:
                    return [f"the manim blocks ({', '.join(g['key'] for g in share)}) did not finish running in "
                            f"{PROBE_TIMEOUT} s: keep each block to a few animations"]
                if not result_file.exists():
                    tail = (run.stderr or run.stdout or "").strip().splitlines()[-3:]
                    return ["the manim blocks could not be checked: " + " | ".join(tail)[:400]]
                results = json.loads(result_file.read_text())
            found_all: list[str] = []
            for group in share:
                found = results.get(group["key"], [])
                (CACHE / f"{_digest(group, style)}.json").write_text(json.dumps(found))
                found_all += found
            return found_all
        finally:
            SPANS.append([start, time.time() * 1000, [g["key"] for g in share]])

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=len(shares)) as pool:
        for found in pool.map(probe, shares):
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
    base = {id(m) for m in scene.mobjects}
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
        # How it reads: the words on the board once this block has run, among everything this id has drawn.
        owned = [m for m in scene.mobjects if id(m) not in base and len(m.get_family())]
        layout = layout_faults(owned)
        if layout:
            errors.append(f"{where}: the drawing does not read cleanly: " + "; ".join(layout[:4]))
        x0, x1, y0, y1 = AREA
        for m in scene.mobjects:
            if id(m) in before or not len(m.get_family()):
                continue
            # A ValueTracker keeps its number in its points; it is never drawn (a tracker at 40 degrees is not ink).
            if type(m).__name__ in ("ValueTracker", "ComplexValueTracker"):
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


TEXT_TYPES = ("Text", "MarkupText", "Paragraph", "MathTex", "Tex", "SingleStringMathTex", "DecimalNumber", "Integer",
              "Variable")


def _words(mob) -> str:
    """What a piece of text says, for a message."""
    for attr in ("original_text", "tex_string", "text"):
        value = getattr(mob, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()[:40]
    return type(mob).__name__


def _box(mob):
    """Its bounds; a text's are its words', not the patch of board behind them (backed_text)."""
    import numpy as np

    words = [p for p in mob.family_members_with_points() if not getattr(p, "is_backing", False)]
    if words and len(words) < len(mob.family_members_with_points()):
        pts = np.concatenate([p.points for p in words])
        return float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())
    lo, hi = mob.get_corner(np.array([-1, -1, 0])), mob.get_corner(np.array([1, 1, 0]))
    return float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])


def _shown(mob) -> bool:
    """Whether anything of it is drawn (a faded-out or empty part is not)."""
    for part in mob.family_members_with_points():
        try:
            if part.get_stroke_opacity() > 0.05 or part.get_fill_opacity() > 0.05:
                return True
        except Exception:  # noqa: BLE001 -- a mobject without VMobject styling (an image): it is drawn
            return True
    return False


def layout_faults(roots) -> list[str]:
    """What makes a drawing hard to read, among the mobjects a block has on the board: words too small for a phone,
    two pieces of text on top of each other, a line running through words. [] when it reads cleanly."""
    import numpy as np

    texts, inside = [], set()
    for root in roots:
        for mob in root.get_family():
            if id(mob) in inside or type(mob).__name__ not in TEXT_TYPES:
                continue
            inside.update(id(m) for m in mob.get_family())
            if mob.has_points() or any(m.has_points() for m in mob.get_family()):
                if _shown(mob) and mob.width > 0.02:
                    texts.append(mob)
    faults: list[str] = []
    for mob in texts:
        size = getattr(mob, "font_size", None)
        try:
            size = float(size) if size is not None else None
        except (TypeError, ValueError):
            size = None
        if size is not None and size < MIN_FONT - 0.5:
            faults.append(f"the text {_words(mob)!r} is font size {size:.0f}: at least {MIN_FONT} to read on a phone")
    boxes = [_box(m) for m in texts]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = boxes[i], boxes[j]
            w = min(a[2], b[2]) - max(a[0], b[0])
            h = min(a[3], b[3]) - max(a[1], b[1])
            if w <= 0 or h <= 0:
                continue
            smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1e-9
            if w * h / smaller > TEXT_OVERLAP:
                faults.append(f"the texts {_words(texts[i])!r} and {_words(texts[j])!r} overlap: move one clear "
                              "of the other (next_to with a buff, or arrange)")
    text_parts = set(inside)
    lines = []
    for root in roots:
        for part in root.family_members_with_points():
            if id(part) in text_parts or not hasattr(part, "get_stroke_width"):
                continue
            try:
                stroked = part.get_stroke_width() > 0 and part.get_stroke_opacity() > 0.2
            except Exception:  # noqa: BLE001
                stroked = False
            if stroked and len(part.points) >= 4:
                lines.append(part)
    crossed = set()
    for k, mob in enumerate(texts):
        x0, y0, x1, y1 = boxes[k]
        dx, dy = (x1 - x0) * TEXT_CORE, (y1 - y0) * TEXT_CORE
        core = (x0 + dx, y0 + dy, x1 - dx, y1 - dy)
        if core[2] <= core[0] or core[3] <= core[1]:
            continue
        for part in lines:
            px0, py0, px1, py1 = _box(part)
            if px1 < core[0] or px0 > core[2] or py1 < core[1] or py0 > core[3]:
                continue
            pts = np.asarray(part.points)
            n = len(pts) // 4
            if not n:
                continue
            t = np.linspace(0, 1, 12)[:, None]
            curves = pts[: n * 4].reshape(n, 4, 3)
            sample = (((1 - t) ** 3)[None] * curves[:, 0:1] + (3 * (1 - t) ** 2 * t)[None] * curves[:, 1:2]
                      + (3 * (1 - t) * t ** 2)[None] * curves[:, 2:3] + (t ** 3)[None] * curves[:, 3:4]).reshape(-1, 3)
            hit = ((sample[:, 0] > core[0]) & (sample[:, 0] < core[2]) & (sample[:, 1] > core[1])
                   & (sample[:, 1] < core[3]))
            if hit.any() and id(mob) not in crossed:
                crossed.add(id(mob))
                faults.append(f"a line runs through the text {_words(mob)!r}: move the label beside what it names "
                              "(next_to with a buff), or the line around it")
                break
    return list(dict.fromkeys(faults))


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
