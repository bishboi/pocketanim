"""The motion engine's compiler (beta): a beat script to a scene on motion.MotionLecture.

It is the lecture compiler (compile_lecture.py) with more: everything a beat script says compiles as it does there
-- the same checks, the same mends, the same pictures -- and plays in motion, in a look; and a beat may also use the
motion templates (title, counter, chart, units, cards, stamp, kpi, chain, list, versus, donut, document, polaroids,
callout, emphasis), each with `on`: the words it lands on. The reference is MOTION_ENGINE.md.

    .venv/bin/python harness_v2/engine/compile_motion.py script.json -o scene.py
    .venv/bin/python harness_v2/engine/compile_motion.py - --json < script.json

A script for it says `"engine": "motion"` and may set:

    look        the motion look: paper, newsroom, chalk, data, studio, sketch (motion_looks.py). Without one, the
                script's classic `style` is used, moving as its nearest look does.
    energy      calm, lively (default) or punchy: how fast everything moves.
    transition  how one picture gives way to the next: slide, push, wipe, dissolve, zoom, page, cut (the look's own
                by default).
    timeline    the default style of a timeline: track, ribbon, cards, road, vertical.

Nothing of compile_lecture is changed: it is imported and extended here, for this process only.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import compile_lecture as cl  # noqa: E402
import motion_looks  # noqa: E402

ENGINE = "motion"

# The motion templates: what each needs, and the arguments its engine call takes (motion.MotionLecture.m_<op>).
MOTION_OPS: dict[str, dict] = {
    "title": {"need": ["text"], "args": ["text", "kicker", "sub", "highlight", "id"]},
    "counter": {"need": ["value"], "args": ["value", "label", "kicker", "delta", "trend", "color", "sub", "start", "id"]},
    "chart": {"need": ["items"], "args": ["items", "kind", "title", "kicker", "unit", "highlight", "reference", "marks",
                                          "source", "id"]},
    "units": {"need": [], "args": ["total", "groups", "title", "kicker", "unit", "cols", "fly", "id"]},
    "cards": {"need": ["items"], "args": ["items", "title", "kicker", "stamp", "id"]},
    "stamp": {"need": ["text"], "args": ["text", "color", "angle", "at"]},
    "kpi": {"need": ["cards"], "args": ["cards", "title", "kicker", "id"]},
    "chain": {"need": ["steps"], "args": ["steps", "title", "kicker", "loop", "id"]},
    "list": {"need": ["items"], "args": ["items", "title", "kicker", "mark", "id"]},
    "versus": {"need": ["left", "right"], "args": ["left", "right", "title", "kicker", "id"]},
    "donut": {"need": ["value"], "args": ["value", "total", "label", "sub", "color", "text", "id"]},
    "document": {"need": ["text"], "args": ["text", "title", "highlight", "source", "file", "id"]},
    "polaroids": {"need": ["items"], "args": ["items", "title", "kicker", "id"]},
    "callout": {"need": ["text"], "args": ["text", "color", "at"]},
    "emphasis": {"need": ["target"], "args": ["target", "how", "color"]},
}
# Put over what is on the stage (after the beat's pictures go up), not a picture of their own.
OVERLAY_OPS = {"stamp", "callout", "emphasis"}
CHART_KINDS = ("column", "bar", "line")
LIST_MARKS = ("bullet", "number", "check")
EMPHASES = ("pulse", "circle", "underline", "highlight", "box", "glow", "shake", "dim")
TIMELINE_STYLES = ("track", "ribbon", "cards", "road", "vertical")
ENERGIES = tuple(motion_looks.ENERGY)
SIDES = ("center", "top", "bottom", "left", "right")
# Pictures in these are made large (a print, a page's portrait, a side's picture), not as small pictures by words.
BIG_PICTURES = {"polaroids", "document", "versus"}
MOST = {"cards": 6, "chain": 7, "list": 7, "kpi": 4, "polaroids": 5, "chart": 12}


# ---------------------------------------------------------------- the script's own fields --------------------------

def _look(script: dict) -> tuple[str | None, list[str]]:
    """The motion look, and the script's classic style set to the one the look rests on when it named none."""
    notes = []
    look = script.get("look")
    style = script.get("style")
    if look is None and style in motion_looks.LOOKS:
        look = style
    if look is not None and look not in motion_looks.LOOKS:
        notes.append(f"{cl.FIXED}look {look!r} is not one of {', '.join(motion_looks.LOOKS)}; the style's own motion is "
                     "used")
        look = None
    if look is not None and (style is None or style in motion_looks.LOOKS):
        script["style"] = motion_looks.BASE[look]
    return look, notes


def _pictures(op: dict) -> list[tuple[str, dict]]:
    """(where, picture) for each picture a motion template carries."""
    kind = op.get("op")
    out = []
    if kind in ("cards", "polaroids"):
        for k, item in enumerate(op.get("items") or []):
            if isinstance(item, dict) and isinstance(item.get("picture"), dict):
                out.append((f"item {k + 1}", item["picture"]))
    elif kind == "chain":
        for k, step in enumerate(op.get("steps") or []):
            if isinstance(step, dict) and isinstance(step.get("picture"), dict):
                out.append((f"step {k + 1}", step["picture"]))
    elif kind == "document" and isinstance(op.get("picture"), dict):
        out.append(("its picture", op["picture"]))
    elif kind == "versus":
        for side in ("left", "right"):
            s = op.get(side)
            if isinstance(s, dict) and isinstance(s.get("picture"), dict):
                out.append((f"its {side} side", s["picture"]))
    return out


def _num(value, default=None):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def motion_fixes(script: dict) -> list[str]:
    """The motion templates checked and mended: a template missing what it shows is left out (with a note); counts
    cut to what fits; unknown kinds, marks and styles set to the default; a picture given as an item's own keys
    moved into its `picture`. Notes as compile_lecture's (fixed: ...)."""
    notes: list[str] = []
    fixed = cl.FIXED
    if script.get("energy") is not None and script["energy"] not in ENERGIES:
        notes.append(f"{fixed}energy {script['energy']!r} is not one of {', '.join(ENERGIES)}; lively is used")
        script["energy"] = "lively"
    if script.get("transition") is not None and script["transition"] not in motion_looks.TRANSITIONS:
        notes.append(f"{fixed}transition {script['transition']!r} is not one of {', '.join(motion_looks.TRANSITIONS)}; "
                     "the look's own is used")
        script.pop("transition")
    if script.get("timeline") is not None and script["timeline"] not in TIMELINE_STYLES:
        notes.append(f"{fixed}timeline {script['timeline']!r} is not one of {', '.join(TIMELINE_STYLES)}; track is used")
        script.pop("timeline")
    for c, chapter in enumerate(script.get("chapters") or []):
        for b, beat in enumerate(chapter.get("beats") or []):
            at = f"chapter {c + 1} beat {b + 1}"
            ops = beat.get("do") if isinstance(beat.get("do"), list) else []
            kept = []
            for op in ops:
                if not isinstance(op, dict):
                    continue
                kind = op.get("op")
                if kind == "timeline" and op.get("style") is not None and op["style"] not in TIMELINE_STYLES:
                    notes.append(f"{fixed}{at}: timeline style {op['style']!r} is not one of "
                                 f"{', '.join(TIMELINE_STYLES)}; track is used")
                    op.pop("style")
                if kind not in MOTION_OPS:
                    kept.append(op)
                    continue
                missing = [f for f in MOTION_OPS[kind]["need"] if op.get(f) in (None, "", [], {})]
                if missing:
                    notes.append(f"{fixed}{at}: {kind} left out: it needs {', '.join(missing)}")
                    continue
                problem = _mend(op, at, notes)
                if problem:
                    notes.append(f"{fixed}{at}: {kind} left out: {problem}")
                    continue
                kept.append(op)
            beat["do"] = kept
    return notes


def _items(op: dict, key: str, text_key: str) -> list:
    """A list of strings or objects as objects ({text_key: ...})."""
    out = []
    for it in op.get(key) or []:
        if isinstance(it, dict):
            out.append(it)
        elif isinstance(it, (str, int, float)):
            out.append({text_key: str(it)})
    return out


def _picture_in(item: dict) -> None:
    """A picture written as an item's own key ({"generate": ...}) moved into its `picture`."""
    if isinstance(item.get("picture"), dict):
        return
    for key in ("generate", "figure", "draw"):
        if item.get(key):
            item["picture"] = {key: item.pop(key)}
            return


def _mend(op: dict, at: str, notes: list[str]) -> str | None:
    kind = op["op"]
    fixed = cl.FIXED
    most = MOST.get(kind)
    if kind == "chart":
        if op.get("kind", "column") not in CHART_KINDS:
            notes.append(f"{fixed}{at}: chart kind {op['kind']!r} is not one of {', '.join(CHART_KINDS)}; column is used")
            op["kind"] = "column"
        rows = []
        for it in op.get("items") or []:
            if isinstance(it, dict) and _num(it.get("value")) is not None:
                rows.append({**it, "label": str(it.get("label", "")), "value": _num(it["value"])})
            elif isinstance(it, (list, tuple)) and len(it) >= 2 and _num(it[1]) is not None:
                rows.append({"label": str(it[0]), "value": _num(it[1])})
        if len(rows) < (2 if op.get("kind") == "line" else 1):
            return "its items are [label, number] pairs (a line needs two or more)"
        if len(rows) > (60 if op.get("kind") == "line" else most):
            notes.append(f"{fixed}{at}: chart cut to its first {most} items")
            rows = rows[:60 if op.get("kind") == "line" else most]
        op["items"] = rows
        if op.get("reference") is not None:
            ref = op["reference"]
            if isinstance(ref, (int, float)):
                op["reference"] = {"value": ref, "label": ""}
            elif not isinstance(ref, dict) or _num(ref.get("value")) is None:
                notes.append(f"{fixed}{at}: chart reference is {{value, label}}; left out")
                op.pop("reference")
    elif kind == "units":
        total = int(_num(op.get("total"), 100) or 100)
        if not 1 <= total <= 400:
            notes.append(f"{fixed}{at}: units total kept between 1 and 400")
        op["total"] = max(1, min(total, 400))
        groups = [g for g in op.get("groups") or [] if isinstance(g, dict) and _num(g.get("n")) is not None]
        used = 0
        for g in groups:
            g["n"] = int(max(0, min(_num(g["n"]), op["total"] - used)))
            used += g["n"]
        op["groups"] = groups
        if op.get("fly") is not None and not (isinstance(op["fly"], dict) and _num(op["fly"].get("n"))):
            notes.append(f"{fixed}{at}: units fly is {{n, label, on}}; left out")
            op.pop("fly")
    elif kind in ("cards", "polaroids"):
        items = _items(op, "items", "title" if kind == "cards" else "caption")
        for it in items:
            _picture_in(it)
        if kind == "polaroids":
            items = [it for it in items if isinstance(it.get("picture"), dict)]
            if not items:
                return "each print needs a picture ({\"generate\": ...} or {\"figure\": ...})"
        if len(items) > most:
            notes.append(f"{fixed}{at}: {kind} cut to {most}")
        op["items"] = items[:most]
        if kind == "cards" and op.get("stamp") is not None:
            if isinstance(op["stamp"], str):
                op["stamp"] = {"text": op["stamp"]}
            elif not isinstance(op["stamp"], dict) or not op["stamp"].get("text"):
                op.pop("stamp")
    elif kind == "kpi":
        cards = [c for c in op.get("cards") or [] if isinstance(c, dict) and c.get("value") not in (None, "")]
        if not cards:
            return "its cards each need a value"
        if len(cards) > most:
            notes.append(f"{fixed}{at}: kpi cut to {most} cards")
        op["cards"] = [{**c, "value": str(c["value"])} for c in cards[:most]]
    elif kind == "chain":
        steps = _items(op, "steps", "label")
        for s in steps:
            _picture_in(s)
        if len(steps) < 2:
            return "a chain needs two steps or more"
        if len(steps) > most:
            notes.append(f"{fixed}{at}: chain cut to {most} steps")
        op["steps"] = steps[:most]
    elif kind == "list":
        items = _items(op, "items", "text")
        if len(items) > most:
            notes.append(f"{fixed}{at}: list cut to {most} items")
        op["items"] = items[:most]
        if op.get("mark", "bullet") not in LIST_MARKS:
            notes.append(f"{fixed}{at}: list mark {op['mark']!r} is not one of {', '.join(LIST_MARKS)}; bullet is used")
            op["mark"] = "bullet"
    elif kind == "versus":
        for side in ("left", "right"):
            s = op.get(side)
            if isinstance(s, str):
                op[side] = s = {"title": s}
            if not isinstance(s, dict) or not s.get("title"):
                return f"its {side} side needs a title"
            _picture_in(s)
            s["points"] = [str(p) for p in s.get("points") or []][:4]
    elif kind == "donut":
        if _num(op.get("value")) is None:
            return "its value is a number"
        op["value"] = _num(op["value"])
        op["total"] = _num(op.get("total"), 100) or 100
    elif kind == "document":
        _picture_in(op)
        hl = op.get("highlight")
        op["highlight"] = [str(h) for h in (hl if isinstance(hl, list) else [hl] if hl else [])]
        lost = [h for h in op["highlight"] if h.lower() not in " ".join(str(op["text"]).split()).lower()]
        if lost:
            notes.append(f"{fixed}{at}: highlight {', '.join(repr(x) for x in lost)} is not in the document's text; left out")
            op["highlight"] = [h for h in op["highlight"] if h not in lost]
    elif kind == "emphasis":
        if op.get("how", "pulse") not in EMPHASES:
            notes.append(f"{fixed}{at}: emphasis how {op['how']!r} is not one of {', '.join(EMPHASES)}; pulse is used")
            op["how"] = "pulse"
    elif kind in ("stamp", "callout"):
        if op.get("at") is not None and op["at"] not in SIDES:
            op["at"] = "center" if kind == "stamp" else "right"
    if kind in BIG_PICTURES:
        for _, spec in _pictures(op):
            spec["_big"] = True
    return None


# ---------------------------------------------------------------- the compiler, extended ---------------------------

_ORIG = {}


def _patched_pictures_of(op: dict):
    return _ORIG["pictures_of"](op) + (_pictures(op) if op.get("op") in MOTION_OPS else [])


def _patched_picture_fetch(spec: dict):
    fetch = _ORIG["_picture_fetch"](spec)
    if fetch and isinstance(spec, dict) and spec.get("_big") and fetch.get("op") == "illustration":
        fetch = {k: v for k, v in fetch.items() if k not in ("look",)}
        fetch["aspect"] = "4:3"
    return fetch


def _patched_op_said(op: dict, parts: dict, asked: list):
    if op.get("on"):
        return str(op["on"])
    return _ORIG["_op_said"](op, parts, asked)


def _patched_beat_order(ops: list) -> list:
    ordered = _ORIG["beat_order"](ops)
    return [o for o in ordered if not (isinstance(o, dict) and o.get("op") in OVERLAY_OPS)] + \
        [o for o in ordered if isinstance(o, dict) and o.get("op") in OVERLAY_OPS]


def _file_of(spec):
    value = cl._picture_value(spec) if isinstance(spec, dict) else None
    return value[1] if value and value[0] == "image" else None


def _clean(value):
    """A value as plain data for the engine's call (no private keys, no pictures' specs: their files instead)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).startswith("_"):
                continue
            if k == "picture":
                f = _file_of(v)
                if f:
                    out["file"] = f
                continue
            out[str(k)] = _clean(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _patched_op_call(op: dict):
    kind = op.get("op")
    if kind in MOTION_OPS:
        args = {}
        for name in MOTION_OPS[kind]["args"]:
            if name == "file":
                f = _file_of(op.get("picture"))
                if f:
                    args["file"] = f
                continue
            if op.get(name) is not None:
                args[name] = _clean(op[name])
        if kind == "chart" and op.get("highlight") is not None:
            args["highlight"] = _clean(op["highlight"])
        return f"self.m_{kind}(**{args!r})"
    call = _ORIG["_op_call"](op)
    if kind == "timeline" and call and op.get("style"):
        call = call[:-1] + f", style={str(op['style'])!r})"
    return call


def _patched_lint(script: dict, *a, **kw):
    notes = _prepare(script)
    errors, warnings = _ORIG["lint"](script, *a, **kw)
    return errors, notes + warnings


def _prepare(script: dict) -> list[str]:
    """The script made ready for the lecture compiler, once: its look read, its templates mended."""
    if script.get("_motion_ready") is not None:
        return []
    look, notes = _look(script)
    notes += motion_fixes(script)
    script["_motion_ready"] = {"look": look}
    return notes


def _patched_compile_script(script: dict, scene_class: str = "GeneratedScene", engine_path: str | None = None) -> str:
    _prepare(script)
    source = _ORIG["compile_script"](script, scene_class, engine_path)
    look = (script.get("_motion_ready") or {}).get("look")
    style = script.get("style", "atlas")
    head = [f"os.environ.setdefault(\"MOTION_LOOK\", {cl._q(look or '')})"]
    if script.get("energy"):
        head.append(f"os.environ.setdefault(\"MOTION_ENERGY\", {cl._q(str(script['energy']))})")
    if script.get("transition"):
        head.append(f"os.environ.setdefault(\"MOTION_TRANSITION\", {cl._q(str(script['transition']))})")
    if script.get("timeline"):
        head.append(f"os.environ.setdefault(\"MOTION_TIMELINE\", {cl._q(str(script['timeline']))})")
    marker = f"os.environ.setdefault(\"LECTURE_STYLE\", {cl._q(style)})"
    if marker not in source:
        raise ValueError("motion: the compiled scene does not set its style where expected")
    source = source.replace(marker, "\n".join([marker, *head]), 1)
    # The engine lays out its own words (as a lecture scene does): the exporter's label pass, for placements a
    # model guessed, must not move them (tools/export_scene.FIXED_LAYOUT reads this line).
    source = source.replace("from pocket_lecture import *  # noqa: E402,F403",
                            "# panim: fixed-layout (the motion engine lays out its own words)\n"
                            "from motion import *  # noqa: E402,F403 -- the motion engine (beta), over pocket_lecture", 1)
    source = source.replace(f"class {scene_class}(MapLecture):", f"class {scene_class}(MotionLecture):", 1)
    source = source.replace("compiled from a beat script by harness/lecture/compile_lecture.py",
                            "compiled from a beat script by harness_v2/engine/compile_motion.py (the motion engine, beta)", 1)
    compile(source, "scene.py", "exec")
    return source


def install() -> None:
    """Extend compile_lecture, in this process, with the motion templates."""
    if _ORIG:
        return
    for name in ("pictures_of", "_picture_fetch", "_op_said", "beat_order", "_op_call", "lint", "compile_script"):
        _ORIG[name] = getattr(cl, name)
    cl.KIT_OPS.update(MOTION_OPS)
    cl.RETIRED_OPS.difference_update(MOTION_OPS)        # "counter" was a retired classic op; here it is a template
    pictures = set(MOTION_OPS) - OVERLAY_OPS
    # What counts as a picture for the checks (a paragraph's visual, a chapter's opening, the next picture).
    for name in ("VISUAL_OPS", "PICTURE_OPS", "STAGE_PICTURES", "_NEW_PICTURE"):
        getattr(cl, name).update(pictures)
    cl.pictures_of = _patched_pictures_of
    cl._picture_fetch = _patched_picture_fetch
    cl._op_said = _patched_op_said
    cl.beat_order = _patched_beat_order
    cl._op_call = _patched_op_call
    cl.lint = _patched_lint
    cl.compile_script = _patched_compile_script
    motion_looks.register_all()


def compile_script(script: dict, scene_class: str = "GeneratedScene", engine_path: str | None = None) -> str:
    install()
    errors, _ = cl.lint(script)
    if errors:
        raise ValueError("\n".join(errors))
    return cl.compile_script(script, scene_class, engine_path)


def check(script: dict) -> tuple[list[str], list[str]]:
    install()
    return cl.lint(copy.deepcopy(script))


if __name__ == "__main__":
    install()
    raise SystemExit(cl.main())
