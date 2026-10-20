"""The motion engine's compiler (beta): a beat script to a scene on motion.MotionLecture.

It is the lecture compiler (compile_lecture.py) with more: everything a beat script says compiles as it does there
-- the same checks, the same mends, the same pictures -- and plays in motion, in a look; and a beat may also use the
motion templates (title, counter, chart, units, cards, stamp, kpi, chain, list, versus, donut, document, polaroids,
emphasis; and hierarchy, exchange, plan, lineage, lifespan, analogy, myth, ritual, share, calendar,
converge, table, ask: motion_more.py), each with `on`: the words it lands on. The reference is MOTION_ENGINE.md.

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
    "emphasis": {"need": ["target"], "args": ["target", "how", "color"]},
    # The shapes of a history, a society or an argument (motion_more.py).
    "hierarchy": {"need": ["tiers"], "args": ["tiers", "title", "kicker", "badge", "build", "id"]},
    "exchange": {"need": ["left", "right", "flows"], "args": ["left", "right", "flows", "title", "kicker", "id"]},
    "plan": {"need": ["zones"], "args": ["zones", "title", "kicker", "file", "id"]},
    "lineage": {"need": ["people"], "args": ["people", "title", "kicker", "id"]},
    "lifespan": {"need": ["people"], "args": ["people", "range", "marks", "title", "kicker", "id"]},
    "analogy": {"need": ["pairs"], "args": ["pairs", "left", "right", "title", "kicker", "stamp", "id"]},
    "myth": {"need": ["wrong", "right"], "args": ["wrong", "right", "label", "title", "kicker", "on", "id"]},
    "ritual": {"need": ["steps"], "args": ["steps", "objects", "seal", "title", "kicker", "id"]},
    "share": {"need": ["total", "part"], "args": ["total", "part", "unit", "label", "part_label", "rest_label", "on",
                                                  "title", "kicker", "id"]},
    "calendar": {"need": [], "args": ["days", "seasons", "title", "kicker", "id"]},
    "converge": {"need": ["to", "sources"], "args": ["to", "sources", "direction", "title", "kicker", "id"]},
    "table": {"need": ["columns", "rows"], "args": ["columns", "rows", "title", "kicker", "highlight", "id"]},
    "ask": {"need": ["text"], "args": ["text", "answer", "kicker", "on", "id"]},
}
# Put over what is on the stage (after the beat's pictures go up), not a picture of their own.
OVERLAY_OPS = {"stamp", "emphasis"}
# Templates no longer drawn: left out of a script that still has them, with a note.
RETIRED_MOTION = {"callout": "callouts are no longer drawn"}
CHART_KINDS = ("column", "bar", "line")
LIST_MARKS = ("bullet", "number", "check")
EMPHASES = ("pulse", "circle", "underline", "highlight", "box", "glow", "shake", "dim")
TIMELINE_STYLES = ("track", "ribbon", "cards", "road", "vertical")
ZONE_KINDS = ("field", "wood", "water", "pasture", "building", "church", "marsh", "road")
PLAN_CELLS = ("nw", "n", "ne", "w", "center", "e", "sw", "s", "se")
UNIT_SHAPES = ("sack", "coin", "box")
ENERGIES = tuple(motion_looks.ENERGY)
SIDES = ("center", "top", "bottom", "left", "right")
# Pictures in these are made large (a print, a page's portrait, a side's picture), not as small pictures by words.
BIG_PICTURES = {"polaroids", "document", "versus", "plan"}
MOST = {"cards": 6, "chain": 7, "list": 7, "kpi": 4, "polaroids": 5, "chart": 12, "hierarchy": 6, "exchange": 4,
        "plan": 12, "lineage": 8, "lifespan": 7, "analogy": 6, "ritual": 6, "calendar": 6, "converge": 8,
        "table": 5}


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
    elif kind in ("document", "plan") and isinstance(op.get("picture"), dict):
        out.append(("its picture", op["picture"]))
    elif kind in ("hierarchy", "lineage", "ritual"):
        key = {"hierarchy": "tiers", "lineage": "people", "ritual": "objects"}[kind]
        for k, item in enumerate(op.get(key) or []):
            if isinstance(item, dict) and isinstance(item.get("picture"), dict):
                out.append((f"{key[:-1]} {k + 1}", item["picture"]))
    elif kind in ("exchange", "converge"):
        for side in (("left", "right") if kind == "exchange" else ("to",)):
            s = op.get(side)
            if isinstance(s, dict) and isinstance(s.get("picture"), dict):
                out.append((f"its {side}", s["picture"]))
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
                if kind in RETIRED_MOTION:
                    notes.append(f"{fixed}{at}: {kind} left out: {RETIRED_MOTION[kind]}")
                    continue
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
    elif kind == "share":
        total, part = _num(op.get("total")), _num(op.get("part"))
        if total is None or part is None or not 0 < part < total:
            return "its total and part are numbers, the part smaller than the total"
        if total > 20:
            notes.append(f"{fixed}{at}: share total kept to 20 pieces (scaled: {int(part)} in {int(total)})")
            part, total = max(1, round(part * 20 / total)), 20
        op["total"], op["part"] = int(total), int(part)
        if op.get("unit") is not None and op["unit"] not in UNIT_SHAPES:
            op["unit"] = "sack"
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
    elif kind == "stamp":
        if op.get("at") is not None and op["at"] not in SIDES:
            op["at"] = "center"
    elif kind in ("hierarchy", "lineage", "ritual", "converge", "plan", "lifespan", "calendar", "table", "analogy",
                  "exchange"):
        problem = _mend_more(op, kind, at, notes, most)
        if problem:
            return problem
    if kind in BIG_PICTURES:
        for _, spec in _pictures(op):
            spec["_big"] = True
    return None


def _mend_more(op: dict, kind: str, at: str, notes: list[str], most: int | None) -> str | None:
    """The templates of motion_more.py checked and mended (see MOTION_ENGINE.md §3)."""
    fixed = cl.FIXED

    def cut(key: str, items: list) -> list:
        if most and len(items) > most:
            notes.append(f"{fixed}{at}: {kind} cut to its first {most} {key}")
        return items[:most] if most else items
    if kind == "hierarchy":
        tiers = _items(op, "tiers", "label")
        for t in tiers:
            _picture_in(t)
        tiers = [t for t in tiers if t.get("label")]
        if len(tiers) < 2:
            return "a hierarchy needs two tiers or more, each with a label"
        op["tiers"] = cut("tiers", tiers)
        if op.get("build") not in (None, "up", "down"):
            op["build"] = "up"
        if isinstance(op.get("badge"), str):
            op["badge"] = {"text": op["badge"]}
    elif kind == "exchange":
        for side in ("left", "right"):
            if isinstance(op.get(side), str):
                op[side] = {"title": op[side]}
            if not isinstance(op.get(side), dict) or not op[side].get("title"):
                return f"its {side} party needs a title"
            _picture_in(op[side])
        flows = [f for f in op.get("flows") or [] if isinstance(f, dict) and f.get("text")]
        if not flows:
            return "its flows are {from: left|right, text, on}"
        op["flows"] = cut("flows", flows)
    elif kind == "plan":
        _picture_in(op)
        zones = _items(op, "zones", "label")
        for z in zones:
            if z.get("kind") is not None and z["kind"] not in ZONE_KINDS:
                notes.append(f"{fixed}{at}: plan zone kind {z['kind']!r} is not one of {', '.join(ZONE_KINDS)}; field is used")
                z["kind"] = "field"
            if z.get("at") is not None and z["at"] not in PLAN_CELLS:
                z.pop("at")
        op["zones"] = cut("zones", [z for z in zones if z.get("label")])
        if not op["zones"]:
            return "its zones each need a label"
    elif kind == "lineage":
        people = _items(op, "people", "name")
        for p in people:
            _picture_in(p)
        people = [p for p in people if p.get("name")]
        if len(people) < 2:
            return "a lineage needs two people or more, each with a name"
        op["people"] = cut("people", people)
    elif kind == "lifespan":
        import timeline_dates as td

        people = [p for p in op.get("people") or [] if isinstance(p, dict) and p.get("name")]
        good = [p for p in people if td.year(p.get("from")) is not None and td.year(p.get("to")) is not None
                and td.year(p.get("to")) > td.year(p.get("from"))]
        if len(good) < len(people):
            notes.append(f"{fixed}{at}: lifespan: a life needs from and to as years (to after from); "
                         f"{len(people) - len(good)} left out")
        if not good:
            return "its people each need a name, from and to (years)"
        op["people"] = cut("people", good)
    elif kind == "analogy":
        pairs = [p for p in op.get("pairs") or [] if (isinstance(p, dict) and p.get("a") and p.get("b"))
                 or (isinstance(p, (list, tuple)) and len(p) >= 2)]
        if not pairs:
            return "its pairs are [a, b] or {a, b, on}"
        op["pairs"] = cut("pairs", pairs)
    elif kind == "ritual":
        steps = _items(op, "steps", "text")
        if not steps:
            return "a ritual needs its steps"
        op["steps"] = cut("steps", steps)
        objects = _items(op, "objects", "name")
        for o in objects:
            _picture_in(o)
        op["objects"] = objects[:4]
        if isinstance(op.get("seal"), str):
            op["seal"] = {"text": op["seal"]}
    elif kind == "converge":
        if isinstance(op.get("to"), str):
            op["to"] = {"label": op["to"]}
        if not isinstance(op.get("to"), dict) or not op["to"].get("label"):
            return "its `to` needs a label"
        _picture_in(op["to"])
        op["sources"] = cut("sources", _items(op, "sources", "label"))
        if not op["sources"]:
            return "it needs its sources"
        if op.get("direction") not in (None, "in", "out"):
            op["direction"] = "in"
    elif kind == "table":
        cols = [str(c) for c in op.get("columns") or []]
        if not 2 <= len(cols) <= 4:
            if len(cols) < 2:
                return "a table needs two columns or more"
            notes.append(f"{fixed}{at}: a table has 2 to 4 columns; cut to its first 4")
        op["columns"] = cols[:4]
        rows = [r for r in op.get("rows") or [] if isinstance(r, dict) and r.get("label")]
        if not rows:
            return "its rows are {label, cells, on}"
        op["rows"] = cut("rows", rows)
    elif kind == "calendar":
        if not (op.get("days") or op.get("seasons")):
            return "a calendar needs days or seasons"
        op["days"] = (op.get("days") or [])[:6]
        op["seasons"] = (op.get("seasons") or [])[:6]
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


# Templates whose `on` is the moment inside them (the correction, the share lifted out, the answer), not when they
# come on: they come on with the line (or on their own words, as any picture).
INNER_ON = {"myth", "share", "ask"}


def _patched_op_said(op: dict, parts: dict, asked: list):
    if op.get("on") and op.get("op") not in INNER_ON:
        return str(op["on"])
    if op.get("op") in INNER_ON:
        return _ORIG["_op_said"]({k: v for k, v in op.items() if k != "on"}, parts, asked)
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
    # How to teach is the writer's on the motion engine: only what is needed to draw the video is checked (the
    # lecture compiler's teaching rules -- empty stretches, plain language, text-heavy beats, the panel's points --
    # are off unless the script turns them on).
    script.setdefault("teaching_rules", False)
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
