"""The motion engine's compiler (beta): a beat script to a scene on motion.MotionLecture.

It is the lecture compiler (compile_lecture.py) with more: everything a beat script says compiles as it does there
-- the same checks, the same mends, the same pictures -- and plays in motion, in a look; and a beat may also use the
motion templates (title, counter, chart, units, cards, stamp, kpi, chain, list, versus, donut, document, polaroids,
emphasis; and hierarchy, exchange, plan, lineage, lifespan, analogy, myth, ritual, share, calendar,
converge, table, ask: motion_more.py; venn, quadrant, funnel, gauge, scale, iceberg, before_after, ranking:
motion_forms.py), each with `on`: the words it lands on, and many with a `layout` (the same content in another form)
and `enter` (how its parts come on). The reference is MOTION_ENGINE.md.

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
import re
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
    # What overlaps, sits between, narrows, measures, weighs, hides, changes or ranks (motion_forms.py).
    "venn": {"need": ["sets"], "args": ["sets", "overlap", "title", "kicker", "id"]},
    "quadrant": {"need": ["x", "y"], "args": ["x", "y", "items", "cells", "title", "kicker", "id"]},
    "funnel": {"need": ["stages"], "args": ["stages", "title", "kicker", "id"]},
    "gauge": {"need": ["value"], "args": ["value", "min", "max", "label", "low", "high", "text", "sub", "invert",
                                          "title", "kicker", "id"]},
    "scale": {"need": ["left", "right"], "args": ["left", "right", "tips", "title", "kicker", "id"]},
    "iceberg": {"need": ["below"], "args": ["above", "below", "waterline", "title", "kicker", "id"]},
    "before_after": {"need": ["before", "after"], "args": ["before", "after", "change", "title", "kicker", "id"]},
    "ranking": {"need": ["items"], "args": ["items", "order", "unit", "highlight", "title", "kicker", "id"]},
    # History and storytelling (motion_story.py).
    "cause_web": {"need": ["causes", "effect"], "args": ["causes", "effect", "title", "kicker", "id"]},
    "portrait_card": {"need": ["name"], "args": ["name", "dates", "role", "file", "facts", "title", "kicker", "id"]},
    "source_vs_reality": {"need": ["source", "reality"], "args": ["source", "reality", "verdict", "title", "kicker", "id"]},
    "population_pyramid": {"need": ["groups"], "args": ["groups", "left_label", "right_label", "unit", "title", "kicker",
                                                        "id"]},
    "migration_flow": {"need": ["regions", "flows"], "args": ["regions", "flows", "unit", "title", "kicker", "id"]},
    "quote_reveal": {"need": ["text"], "args": ["text", "who", "file", "highlight", "title", "kicker", "id"]},
    "newspaper": {"need": ["headline"], "args": ["headline", "paper", "date", "sub", "file", "title", "kicker", "id"]},
    "letter": {"need": ["text"], "args": ["text", "to", "sign", "date", "title", "kicker", "id"]},
    "countdown": {"need": ["steps", "event"], "args": ["steps", "event", "title", "kicker", "id"]},
    # Numbers and explanations (motion_explain.py).
    "race_bars": {"need": ["frames"], "args": ["frames", "unit", "title", "kicker", "id"]},
    "waterfall": {"need": ["start", "steps"], "args": ["start", "steps", "total", "unit", "title", "kicker", "id"]},
    "stacked_area": {"need": ["series", "years"], "args": ["series", "years", "unit", "title", "kicker", "id"]},
    "slope": {"need": ["items"], "args": ["items", "left_label", "right_label", "unit", "title", "kicker", "id"]},
    "dot_compare": {"need": ["groups"], "args": ["groups", "title", "kicker", "id"]},
    "split_number": {"need": ["value", "parts"], "args": ["value", "parts", "label", "unit", "title", "kicker", "id"]},
    "zoom_in": {"need": ["picture"], "args": ["file", "box", "label", "note", "on", "title", "kicker", "id"]},
    "layers": {"need": ["layers"], "args": ["layers", "title", "kicker", "id"]},
    "cycle_wheel": {"need": ["steps"], "args": ["steps", "center", "title", "kicker", "id"]},
    "checklist": {"need": ["claim", "criteria"], "args": ["claim", "criteria", "verdict", "title", "kicker", "id"]},
    "pros_cons": {"need": [], "args": ["pros", "cons", "lean", "verdict", "title", "kicker", "id"]},
    "mind_map": {"need": ["center", "branches"], "args": ["center", "branches", "title", "kicker", "id"]},
}
# Written as another operation: a story on the map is the map's journey, its stops named with their dates.
SUGAR_OPS = {"map_story"}
# The ways a template may be laid out (`layout`), the first its default.
LAYOUTS = {
    "counter": ("big", "ring", "bar", "badge"),
    "list": ("column", "grid", "pills", "steps"),
    "chain": ("row", "column", "zigzag"),
    "cards": ("row", "grid", "fan"),
    "versus": ("cards", "split", "stack"),
    "kpi": ("row", "grid", "column"),
}
# How any template's parts may come on (`enter`; motion_kit.ENTRANCES). Left out: each part's own way.
ENTRANCES = ("pop", "rise", "drop", "slide", "zoom", "fade", "flip", "write", "unfold", "typewrite", "ink", "stamp",
             "spin", "iris")
IDLES = tuple(motion_looks.IDLES)
# A picture's camera on the motion engine, beside the lecture engine's moves (bob, sway, breathe, drift).
CAMERA_MOVES = ("kenburns", "pan", "pullback")
RANK_ORDERS = ("up", "down")
for _kind, _spec in MOTION_OPS.items():
    if _kind in LAYOUTS:
        _spec["args"].insert(len(_spec["args"]) - 1, "layout")
    if _kind not in ("stamp", "emphasis"):
        _spec["args"].insert(len(_spec["args"]) - (1 if _spec["args"][-1] == "id" else 0), "enter")
MOTION_OPS["counter"]["args"].insert(-1, "max")
# Put over what is on the stage (after the beat's pictures go up), not a picture of their own.
OVERLAY_OPS = {"stamp", "emphasis"}
# Templates no longer drawn: left out of a script that still has them, with a note.
RETIRED_MOTION = {"callout": "callouts are no longer drawn"}
CHART_KINDS = ("column", "bar", "line")
LIST_MARKS = ("bullet", "number", "check")
EMPHASES = ("pulse", "circle", "underline", "highlight", "box", "glow", "shake", "dim", "spotlight", "rack", "magnify",
            "wiggle", "bounce", "wash", "strike", "sweep")
TIMELINE_STYLES = ("track", "ribbon", "cards", "road", "vertical")
ZONE_KINDS = ("field", "wood", "water", "pasture", "building", "church", "marsh", "road")
PLAN_CELLS = ("nw", "n", "ne", "w", "center", "e", "sw", "s", "se")
UNIT_SHAPES = ("sack", "coin", "box")
ENERGIES = tuple(motion_looks.ENERGY)
SIDES = ("center", "top", "bottom", "left", "right")
# Pictures in these are made large (a print, a page's portrait, a side's picture), not as small pictures by words.
BIG_PICTURES = {"polaroids", "document", "versus", "plan", "before_after", "portrait_card", "zoom_in", "quote_reveal",
                "newspaper"}
MOST = {"cards": 6, "chain": 7, "list": 7, "kpi": 4, "polaroids": 5, "chart": 12, "hierarchy": 6, "exchange": 4,
        "plan": 12, "lineage": 8, "lifespan": 7, "analogy": 6, "ritual": 6, "calendar": 6, "converge": 8,
        "table": 5, "venn": 3, "quadrant": 8, "funnel": 6, "ranking": 7, "iceberg": 5}


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
    elif kind in ("document", "plan", "portrait_card", "zoom_in", "quote_reveal", "newspaper") \
            and isinstance(op.get("picture"), dict):
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
    elif kind in ("versus", "before_after"):
        for side in (("left", "right") if kind == "versus" else ("before", "after")):
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
    if script.get("idle") is not None and script["idle"] not in IDLES:
        notes.append(f"{fixed}idle {script['idle']!r} is not one of {', '.join(IDLES)}; the look's own is used")
        script.pop("idle")
    if script.get("timeline") is not None and script["timeline"] not in TIMELINE_STYLES:
        notes.append(f"{fixed}timeline {script['timeline']!r} is not one of {', '.join(TIMELINE_STYLES)}; track is used")
        script.pop("timeline")
    for c, chapter in enumerate(script.get("chapters") or []):
        for b, beat in enumerate(chapter.get("beats") or []):
            at = f"chapter {c + 1} beat {b + 1}"
            _word_ids(beat, at, notes)
            ops = beat.get("do") if isinstance(beat.get("do"), list) else []
            kept = []
            for op in ops:
                if not isinstance(op, dict):
                    continue
                kind = op.get("op")
                _when(op, at, notes)
                if kind == "timeline" and op.get("style") is not None and op["style"] not in TIMELINE_STYLES:
                    notes.append(f"{fixed}{at}: timeline style {op['style']!r} is not one of "
                                 f"{', '.join(TIMELINE_STYLES)}; track is used")
                    op.pop("style")
                if kind in SUGAR_OPS:
                    made = _map_story(op, at, notes)
                    if made is not None:
                        kept.append(made)
                    continue
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
                _mend_form(op, kind, at, notes)
                problem = _mend(op, at, notes)
                if problem:
                    notes.append(f"{fixed}{at}: {kind} left out: {problem}")
                    continue
                kept.append(op)
            beat["do"] = kept
    return notes


# A word of its line by its number (w0 its first word, counted as the line is written, split at spaces).
WORD_ID = re.compile(r"^\s*w(\d+)\s*$")
_PUNCT = ".,;:!?\"'“”‘’()[]—–-…।॥"


def _word_ids(beat: dict, at: str, notes: list[str]) -> None:
    """Every `on` given as a word's number in its line (`"w7"`, as the scene writer is shown the voiced line) made
    the words of the line from it: as few as are said there first (an anchor is the first place its words are said),
    so the compiler's anchors read it as any other."""
    words = [w.strip(_PUNCT) for w in str(beat.get("say") or "").split()]
    low = [w.lower() for w in words]

    def first(seq: list[str]) -> int:
        n = len(seq)
        return next((i for i in range(len(low) - n + 1) if low[i:i + n] == seq), -1)

    def phrase(k: int) -> str | None:
        while k < len(words) and not words[k]:
            k += 1                                  # a dash or a mark on its own: the word after it
        if k >= len(words):
            return None
        for n in range(1, 6):
            seq = low[k:k + n]
            if first(seq) == k:
                return " ".join(words[k:k + n])
        return " ".join(words[k:k + 5])

    def walk(value) -> None:
        if isinstance(value, dict):
            on = value.get("on")
            m = WORD_ID.match(on) if isinstance(on, str) else None
            if m:
                said = phrase(int(m.group(1)))
                if said is None:
                    notes.append(f"{cl.FIXED}{at}: \"on\": {on!r} is past the line's last word ({len(words)} words, "
                                 f"w0 to w{max(0, len(words) - 1)}): it comes on in its turn")
                    value.pop("on")
                else:
                    value["on"] = said
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    walk(beat.get("do"))


def _when(op: dict, at: str, notes: list[str]) -> None:
    """`delay` (seconds after its words, 0 to 3) and `in_pause` (a stamp or an emphasis played in the quiet after its
    line) read and mended."""
    if "delay" in op:
        v = _num(op.get("delay"))
        if v is None or v < 0:
            notes.append(f"{cl.FIXED}{at}: {op.get('op')} delay {op.get('delay')!r} is not seconds (0 to 3); left out")
            op.pop("delay")
        else:
            op["delay"] = round(min(v, 3.0), 2)
    if "in_pause" in op:
        on = op.get("in_pause") in (True, "true", 1)
        if on and op.get("op") not in OVERLAY_OPS:
            notes.append(f"{cl.FIXED}{at}: {op.get('op')} in_pause left out: only a stamp or an emphasis lands in the "
                         "quiet after a line (a picture comes on with its words; use delay)")
            on = False
        if on:
            op["in_pause"] = True
        else:
            op.pop("in_pause")


def _map_story(op: dict, at: str, notes: list[str]) -> dict | None:
    """A story on the map (`map_story`: stops [{place, date?, label?}], color?) as the map's journey: the route drawn
    behind a traveller, each stop named with its date as it is reached."""
    stops = [s if isinstance(s, dict) else {"place": str(s)} for s in op.get("stops") or []]
    stops = [s for s in stops if s.get("place")]
    if len(stops) < 2:
        notes.append(f"{cl.FIXED}{at}: map_story left out: it needs two stops or more, each with a place")
        return None
    labels = [" · ".join(str(x) for x in (s.get("label") or s["place"], s.get("date")) if x) for s in stops]
    out = {"op": "journey", "stops": [s["place"] for s in stops], "labels": labels}
    for k in ("color", "on"):
        if op.get(k) is not None:
            out[k] = op[k]
    if any(isinstance(s.get("picture"), dict) for s in stops):
        out["pictures"] = [s.get("picture") for s in stops]
    return out


def _mend_form(op: dict, kind: str, at: str, notes: list[str]) -> None:
    """A template's `layout` and `enter` checked: an unknown one is left out (its default is used), with a note."""
    fixed = cl.FIXED
    if op.get("layout") is not None:
        ways = LAYOUTS.get(kind)
        if not ways:
            notes.append(f"{fixed}{at}: {kind} has no layouts; layout {op['layout']!r} left out")
            op.pop("layout")
        elif op["layout"] not in ways:
            notes.append(f"{fixed}{at}: {kind} layout {op['layout']!r} is not one of {', '.join(ways)}; {ways[0]} is used")
            op.pop("layout")
    if op.get("enter") is not None and (op["enter"] not in ENTRANCES or kind in ("stamp", "emphasis")):
        notes.append(f"{fixed}{at}: {kind} enter {op['enter']!r} is not one of {', '.join(ENTRANCES)}; left out")
        op.pop("enter")


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
            # A point is words, or {text, on} to come on as said (kept a dict, never written out as one).
            s["points"] = [({"text": str(p["text"]), **({"on": str(p["on"])} if p.get("on") else {})}
                            if isinstance(p, dict) else str(p))
                           for p in s.get("points") or [] if not isinstance(p, dict) or p.get("text")][:4]
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
    elif kind in STORY_KINDS:
        problem = _mend_story(op, kind, at, notes)
        if problem:
            return problem
    elif kind in ("venn", "quadrant", "funnel", "gauge", "scale", "iceberg", "before_after", "ranking"):
        problem = _mend_forms(op, kind, at, notes, most)
        if problem:
            return problem
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


STORY_KINDS = ("cause_web", "portrait_card", "source_vs_reality", "population_pyramid", "migration_flow", "quote_reveal",
               "newspaper", "letter", "countdown", "race_bars", "waterfall", "stacked_area", "slope", "dot_compare",
               "split_number", "zoom_in", "layers", "cycle_wheel", "checklist", "pros_cons", "mind_map")


def _mend_story(op: dict, kind: str, at: str, notes: list[str]) -> str | None:
    """The templates of motion_story.py and motion_explain.py checked and mended (MOTION_ENGINE.md §3): lists of
    words or objects read as objects, counts cut to what fits, a template missing what it shows left out."""
    fixed = cl.FIXED

    def objs(key: str, text_key: str, most: int) -> list:
        items = _items(op, key, text_key)
        if len(items) > most:
            notes.append(f"{fixed}{at}: {kind} cut to its first {most} {key}")
        return items[:most]
    if kind == "cause_web":
        op["causes"] = objs("causes", "text", 6)
        if not op["causes"]:
            return "it needs its causes"
    elif kind == "portrait_card":
        _picture_in(op)
        op["facts"] = objs("facts", "text", 3)
    elif kind == "source_vs_reality":
        for side in ("source", "reality"):
            if isinstance(op.get(side), str):
                op[side] = {"text": op[side]}
            if not isinstance(op.get(side), dict) or not op[side].get("text"):
                return f"its {side} needs its text"
    elif kind == "population_pyramid":
        groups = [g for g in op.get("groups") or [] if isinstance(g, dict) and g.get("label")
                  and _num(g.get("left")) is not None and _num(g.get("right")) is not None]
        if len(groups) < 2:
            return "its groups are {label, left, right} (two or more)"
        op["groups"] = groups[:10]
    elif kind == "migration_flow":
        op["regions"] = objs("regions", "name", 6)
        flows = [f for f in op.get("flows") or [] if isinstance(f, dict) and f.get("from") and f.get("to")]
        if len(op["regions"]) < 2 or not flows:
            return "it needs two regions or more and flows {from, to, value}"
        op["flows"] = flows[:8]
    elif kind in ("quote_reveal", "newspaper"):
        _picture_in(op)
    elif kind == "countdown":
        op["steps"] = objs("steps", "text", 6)
        if isinstance(op.get("event"), str):
            op["event"] = {"text": op["event"]}
        if not op["steps"] or not isinstance(op.get("event"), dict) or not op["event"].get("text"):
            return "it needs its steps and an event"
    elif kind == "race_bars":
        frames = [f for f in op.get("frames") or [] if isinstance(f, dict) and isinstance(f.get("values"), dict)
                  and f["values"]]
        if not frames:
            return "its frames are {at, values: {name: number}, on}"
        frames[0].setdefault("on", "start")
        op["frames"] = frames[:8]
    elif kind == "waterfall":
        if isinstance(op.get("start"), (int, float, str)):
            op["start"] = {"label": "Start", "value": op["start"]}
        steps = [s for s in op.get("steps") or [] if isinstance(s, dict) and _num(s.get("value")) is not None]
        if not steps or not isinstance(op.get("start"), dict) or _num(op["start"].get("value")) is None:
            return "it needs a start {label, value} and steps {label, value: +n or -n}"
        # Drawn with the template: not timed by a word of the line its label happens to look like.
        op["start"].setdefault("on", "start")
        op["steps"] = steps[:8]
    elif kind == "stacked_area":
        series = [x for x in op.get("series") or [] if isinstance(x, dict) and isinstance(x.get("values"), list)]
        if not series or len(op.get("years") or []) < 2:
            return "it needs its years (two or more) and series {label, values}"
        op["series"] = series[:6]
    elif kind == "slope":
        items = [i for i in op.get("items") or [] if isinstance(i, dict) and _num(i.get("from")) is not None
                 and _num(i.get("to")) is not None]
        if not items:
            return "its items are {label, from, to}"
        op["items"] = items[:7]
    elif kind == "dot_compare":
        groups = [g for g in op.get("groups") or [] if isinstance(g, dict) and _num(g.get("part")) is not None]
        if not groups:
            return "its groups are {label, part, total}"
        op["groups"] = groups[:4]
    elif kind == "split_number":
        parts = [x for x in op.get("parts") or [] if isinstance(x, dict) and _num(x.get("value")) is not None]
        if not parts:
            return "its parts are {label, value}"
        op["parts"] = parts[:6]
    elif kind == "zoom_in":
        _picture_in(op)
        if not isinstance(op.get("picture"), dict):
            return "it needs a picture ({\"generate\": ...} or {\"figure\": ...})"
        box = op.get("box")
        if box is not None and not (isinstance(box, list) and len(box) == 4 and all(_num(v) is not None for v in box)):
            notes.append(f"{fixed}{at}: zoom_in box is [x0, y0, x1, y1] from 0 to 1; its middle is used")
            op.pop("box")
    elif kind == "layers":
        op["layers"] = objs("layers", "label", 6)
        if len(op["layers"]) < 2:
            return "it needs two layers or more"
    elif kind == "cycle_wheel":
        op["steps"] = objs("steps", "label", 8)
        if len(op["steps"]) < 3:
            return "a cycle needs three steps or more"
    elif kind == "checklist":
        op["criteria"] = objs("criteria", "text", 6)
        if not op["criteria"]:
            return "it needs its criteria"
    elif kind == "pros_cons":
        op["pros"], op["cons"] = objs("pros", "text", 5), objs("cons", "text", 5)
        if not op["pros"] and not op["cons"]:
            return "it needs pros or cons"
        if op.get("lean") is not None and op["lean"] not in ("pros", "cons", "even"):
            op.pop("lean")
    elif kind == "mind_map":
        op["branches"] = objs("branches", "label", 8)
        if not op["branches"]:
            return "it needs its branches"
    return None


def _mend_forms(op: dict, kind: str, at: str, notes: list[str], most: int | None) -> str | None:
    """The templates of motion_forms.py checked and mended (see MOTION_ENGINE.md §3)."""
    fixed = cl.FIXED

    def cut(key: str, items: list) -> list:
        if most and len(items) > most:
            notes.append(f"{fixed}{at}: {kind} cut to its first {most} {key}")
        return items[:most] if most else items
    if kind == "venn":
        sets = [s for s in _items(op, "sets", "label") if s.get("label")]
        if len(sets) < 2:
            return "a venn needs two or three sets, each with a label"
        op["sets"] = cut("sets", sets)
        if isinstance(op.get("overlap"), str):
            op["overlap"] = {"text": op["overlap"]}
    elif kind == "quadrant":
        for axis in ("x", "y"):
            a = op.get(axis)
            if isinstance(a, str):
                op[axis] = {"label": a}
            elif not isinstance(a, (dict, list)):
                return f"its {axis} axis is [low end, high end] or {{label, low, high}}"
        items = [i for i in _items(op, "items", "text") if i.get("text")]
        for i in items:
            for c in ("x", "y"):
                v = _num(i.get(c))
                if v is not None:
                    i[c] = max(0.0, min(1.0, v / 100 if v > 1 else v))
        op["items"] = cut("items", items)
        if op.get("cells") is not None and not isinstance(op["cells"], dict):
            notes.append(f"{fixed}{at}: quadrant cells is {{tl, tr, bl, br}}; left out")
            op.pop("cells")
    elif kind == "funnel":
        stages = [s for s in _items(op, "stages", "label") if s.get("label")]
        if len(stages) < 2:
            return "a funnel needs two stages or more"
        op["stages"] = cut("stages", stages)
    elif kind == "gauge":
        v = _num(op.get("value"))
        if v is None:
            return "its value is a number"
        lo, hi = _num(op.get("min"), 0.0), _num(op.get("max"), 100.0)
        if hi is None or lo is None or hi <= lo:
            notes.append(f"{fixed}{at}: gauge min and max read as 0 and 100")
            lo, hi = 0.0, 100.0
        op["value"], op["min"], op["max"] = v, lo, hi
    elif kind == "scale":
        for side in ("left", "right"):
            if isinstance(op.get(side), str):
                op[side] = {"title": op[side]}
            if not isinstance(op.get(side), dict) or not op[side].get("title"):
                return f"its {side} side needs a title"
            op[side]["items"] = _items(op[side], "items", "text")[:4]
        if op.get("tips") is not None and op["tips"] not in ("left", "right", "even"):
            op.pop("tips")
    elif kind == "iceberg":
        op["above"] = _items(op, "above", "text")[:3]
        op["below"] = cut("below", _items(op, "below", "text"))
        if not op["below"]:
            return "an iceberg needs what is below"
    elif kind == "before_after":
        for side in ("before", "after"):
            if isinstance(op.get(side), str):
                op[side] = {"title": op[side]}
            if not isinstance(op.get(side), dict) or not op[side].get("title"):
                return f"its {side} needs a title"
            _picture_in(op[side])
            op[side]["points"] = [str(p.get("text", "")) if isinstance(p, dict) else str(p)
                                  for p in op[side].get("points") or []][:4]
    elif kind == "ranking":
        items = [i for i in _items(op, "items", "label") if i.get("label")]
        if len(items) < 2:
            return "a ranking needs two places or more"
        op["items"] = cut("places", items)
        if op.get("order") is not None and op["order"] not in RANK_ORDERS:
            notes.append(f"{fixed}{at}: ranking order {op['order']!r} is not one of {', '.join(RANK_ORDERS)}; up is used")
            op.pop("order")
    return None


# ---------------------------------------------------------------- the compiler, extended ---------------------------

_ORIG = {}


def _patched_pictures_of(op: dict):
    # The current engine's templates have their pictures from compile_lecture itself (TEMPLATE_OPS).
    return _ORIG["pictures_of"](op) + (_pictures(op) if op.get("op") in set(MOTION_OPS) - cl.TEMPLATE_OPS else [])


def _patched_picture_fetch(spec: dict):
    fetch = _ORIG["_picture_fetch"](spec)
    if fetch and isinstance(spec, dict) and spec.get("_big") and fetch.get("op") == "illustration":
        fetch = {k: v for k, v in fetch.items() if k not in ("look",)}
        fetch["aspect"] = "4:3"
    return fetch


# Templates whose `on` is the moment inside them (the correction, the share lifted out, the answer), not when they
# come on: they come on with the line (or on their own words, as any picture).
INNER_ON = {"myth", "share", "ask", "zoom_in"}


def _inner_on(op: dict) -> bool:
    """Whether the op's `on` is a moment inside it: a question's only with an answer to time (a question alone comes
    on at its `on`: taken for an answer's cue, it came on with the line, over the beat's earlier pictures)."""
    if op.get("op") == "ask":
        return bool(str(op.get("answer") or "").strip())
    return op.get("op") in INNER_ON


def _patched_op_said(op: dict, parts: dict, asked: list):
    inner = _inner_on(op)
    if str(op.get("on") or "").strip() == "start" and not inner:
        return None                                  # as the line begins (compile_lecture.anchors)
    if op.get("on") and not inner:
        return str(op["on"])
    if inner:
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
    call = _op_call_motion(op)
    if call and not call.startswith("*") and op.get("hold") and op.get("id") and \
            (op.get("op") in MOTION_OPS or op.get("op") == "timeline") and "self.holding(" not in call:
        # Parts held back for a later line's reveal (MotionLecture.holding; BEAT_SCRIPT.md §5.9).
        call = f"self.holding({cl._q(str(op['id']))}, {[str(x) for x in op['hold']]!r}, lambda: {call})"
    if call and not call.startswith("*") and (op.get("delay") or op.get("in_pause")):
        # Its moment moved: after its words by `delay`, or into the quiet after the line (MotionLecture._m_when).
        call = f"self._m_when({call}, after={float(op.get('delay') or 0):g}, pause={bool(op.get('in_pause'))})"
    return call


def _op_call_motion(op: dict):
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
    if script.get("idle"):
        head.append(f"os.environ.setdefault(\"MOTION_IDLE\", {cl._q(str(script['idle']))})")
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


def _patched_paragraphs(beats: list, is_map_op=None) -> list[list[int]]:
    """The pause after each line, on the motion engine: the voice's own (the gap it left there in the chapter's take,
    pocket_lecture.beat_pad), and a paragraph's longer hold only where the writer marked `"paragraph": true`. Read by
    the lecture compiler, almost every beat here puts up a picture of its own and so closed a paragraph: 0.8 s of
    quiet after every sentence where the voice paused 0.3 s, and not the quiet the scene writer was shown. Everything
    else that groups beats into paragraphs (a picture held through one) is as the lecture compiler's."""
    if sys._getframe(1).f_code.co_name != "compile_script":
        return _ORIG["paragraphs"](beats, is_map_op)
    out: list[list[int]] = []
    for index, beat in enumerate(beats):
        if not out or (isinstance(beat, dict) and beat.get("paragraph")):
            out.append([index])
        else:
            out[-1].append(index)
    return out


def _map_points(chapter: dict) -> list:
    """The places a map run's arrows, paths, journeys and markers name or give (lon, lat)."""
    out = []
    for beat in chapter.get("beats") or []:
        for op in beat.get("do") or []:
            if not isinstance(op, dict):
                continue
            kind = op.get("op")
            if kind in ("path", "arrow"):
                out += list(op.get("points") or [])
            elif kind == "journey":
                out += list(op.get("stops") or [])
            elif kind == "marker":
                out.append(op.get("place") or op.get("lonlat"))
    return [p for p in out if p]


def _patched_chapter_frame(chapter: dict, region: dict | None):
    """The current engine's frame for a map run (compile_lecture._chapter_frame), widened to take in the places an
    arrow, a path, a journey or a marker reaches outside the region: a map of "Western Europe" leaves out Spain and
    Italy, and an arrow of the Germanic peoples into them ran off the screen."""
    box = _ORIG["_chapter_frame"](chapter, region)
    if not region:
        return box
    try:
        import pocket_lecture as pl

        bounds = pl.map_bounds(region)
        home = None if pl.region_kind(region) == "area" else region.get("country")
    except Exception:  # noqa: BLE001
        return box
    if not bounds:
        return box
    lons, lats = [], []
    for where in _map_points(chapter):
        try:
            lon, lat = pl.place(where, home, bounds) if isinstance(where, str) else (float(where[0]), float(where[1]))
        except Exception:  # noqa: BLE001 -- a place the gazetteer does not know is passed over
            continue
        lons.append(lon)
        lats.append(lat)
    if box is None and pl.region_kind(region) == "area" and len(lons) >= 2:
        # The whole map of an area is fitted to its own countries' land (lonlat_bounds), not the box it is looked
        # up in: fitted to every place the run reaches instead, with room round them (more under them, where the
        # caption sits) so an arrow's head is never at the screen's edge.
        pad = max(2.0, 0.18 * max(max(lons) - min(lons), max(lats) - min(lats)))
        return (round(min(lons) - pad, 2), round(min(lats) - pad * 1.6, 2), round(max(lons) + pad, 2),
                round(max(lats) + pad, 2))
    base = box or tuple(bounds)
    out = [(lon, lat) for lon, lat in zip(lons, lats)
           if not (base[0] <= lon <= base[2] and base[1] <= lat <= base[3])]
    if not out:
        return box
    pad = 2.0
    x0 = min([base[0]] + [p[0] - pad for p in out])
    y0 = min([base[1]] + [p[1] - pad for p in out])
    x1 = max([base[2]] + [p[0] + pad for p in out])
    y1 = max([base[3]] + [p[1] + pad for p in out])
    return (round(max(x0, -180.0), 2), round(max(y0, -85.0), 2), round(min(x1, 180.0), 2), round(min(y1, 85.0), 2))


def install() -> None:
    """Extend compile_lecture, in this process, with the motion templates."""
    if _ORIG:
        return
    for name in ("pictures_of", "_picture_fetch", "_op_said", "beat_order", "_op_call", "lint", "compile_script", "paragraphs",
                 "_chapter_frame"):
        _ORIG[name] = getattr(cl, name)
    cl.KIT_OPS.update(MOTION_OPS)
    cl.PICTURE_MOVES = tuple(dict.fromkeys((*cl.PICTURE_MOVES, *CAMERA_MOVES)))
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
    cl.paragraphs = _patched_paragraphs
    cl._chapter_frame = _patched_chapter_frame
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
