"""Compile a lecture beat script (JSON) into a Manim scene on pocket_lecture.

The guide's cheap path: a model writes a short structured script -- beats of
narration plus the few operations that go with each -- and this turns it into
engine calls. The output is ordinary, readable Manim, so it can be edited by
hand in the web editor, exported to the phone, or rendered by `manim`.

A script:

    {
      "title": "India", "sub": "The geography of a subcontinent",
      "style": "vox",                                  # a pocket_lecture style: the template, the film's frame
      "art": "blueprint",                              # how its pictures are drawn (artstyle.py); "auto": the style's
      "region": {"country": "India", "view": "ind"},   # omit for no map
      "intro": "Welcome to this lecture on India.",
      "chapters": [
        {"title": "Rivers", "sub": "Two great families",
         "narration": "Chapter one. The rivers of India.",
         "map": true,
         "beats": [
           {"say": "The Ganga is India's longest river.",
            "do": [{"op": "panel", "title": "Rivers"},
                   {"op": "river", "name": "Ganges"},
                   {"op": "stat", "value": "2,525 km", "label": "Ganga: longest river", "color": "RIVER"}]}
         ]}
      ],
      "recap": [["Rivers", "Snow-fed and rain-fed"]],
      "credits": "Map data: Natural Earth · Animation: Manim"
    }

Operations (colours are palette names -- SAND, RIVER, GOLD, ROSE, TEAL,
GREEN, VIOLET, MUTED, CREAM, HI ... -- or #RRGGBB):

    panel      title, sub?            clear the panel and head it
    fact       text, color?           a bulleted line
    stat       value, label, color?   a big number
    bars       items [[label, n]], unit?, color?
    clear                             empty the panel
    marker     place | lonlat [lon, lat], label?, color?, side? (left/right/up/down)
    river      name, color?           a Natural Earth river
    path       points [[lon, lat]...], color?   a hand-digitised line
    arrow      points [[lon, lat]...], color?   a curved arrow (winds, routes)
    state      name, color?, opacity? fill one state or province
    dim        opacity?               fade the filled layers down
    graticule  lat | lon, label?, color?

Usage:
    python harness/lecture/compile_lecture.py script.json [-o scene.py] [--check]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STYLES = ("atlas", "vox", "cardboard", "whiteboard", "blueprint", "chalkboard", "parchment", "lab", "cosmos")
# Art styles (artstyle.ART_STYLES), and "auto" for the one the template draws with.
ARTS = ("auto", "clean", "detailed", "blueprint", "chalk", "sketch", "neon", "watercolour")
PALETTE = {"SAND", "DUNE", "TERRA", "RUST", "TEAL", "RIVER", "GREEN", "OLIVE", "CREAM", "MUTED",
           "ROSE", "GOLD", "VIOLET", "HI", "MOUNT"}
MAP_OPS = {"marker", "river", "path", "arrow", "state", "dim", "graticule", "journey", "empire", "relief"}
SIDES = {"left": "LEFT", "right": "RIGHT", "up": "UP", "down": "DOWN"}

# The panel runs from y = 2.35 down to the caption's top, near -2.85. These
# are the heights each item takes there, for the overflow check.
PANEL_ROOM = 5.2


def _q(text) -> str:
    """A Python string literal. json.dumps is valid Python for plain strings."""
    return json.dumps(str(text), ensure_ascii=False)


def _colour(value, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    if text.upper() in PALETTE:
        return f"P.{text.upper()}"
    if text.startswith("#") and len(text) in (4, 7):
        return _q(text.upper())
    raise ValueError(f"colour {value!r} is neither a palette name nor #RRGGBB")


def _panel_height(op: dict) -> float:
    kind = op.get("op")
    if kind == "panel":
        return 0.95 + (0.35 if op.get("sub") else 0.0)
    if kind == "fact":
        lines = max(1, -(-len(str(op.get("text", ""))) // 36))
        return lines * 0.33 + 0.22
    if kind == "stat":
        return 1.05
    if kind == "bars":
        return len(op.get("items") or []) * 0.42 + 0.3
    if kind == "icon" and not _icon_spots(op):
        return 0.87
    if kind == "figure" and op.get("where", "panel") == "panel":
        return 3.2
    if kind == "photo" and op.get("where") == "panel":
        return 3.2
    return 0.0


# The teaching pace, as pocket_lecture.PACES has it (PANIM_PACE): voice speed, the hold after each line, the
# hold at a paragraph's end. Kept here too so a lint-only install needs no engine.
PACES = {"slow": (1.0, 1.4, 2.8), "relaxed": (1.0, 0.9, 1.8), "brisk": (1.0, 0.45, 0.9)}
VOICE_SPEED, BEAT_PAD, PARAGRAPH_PAD = PACES.get(os.environ.get("PANIM_PACE", "slow"), PACES["slow"])
WORD_SECONDS = 0.42 / VOICE_SPEED     # about 143 words a minute at normal speed: pocket_lecture.estimate_seconds
THINK_SECONDS = 7.0                   # a question's time to think (pocket_lecture.THINK_SECONDS)
MAX_PAUSE = 2.0                       # a beat's "pause", at most


def _say_seconds(text: str) -> float:
    return max(1.2, len(str(text).split()) * WORD_SECONDS) + BEAT_PAD


def _think_seconds(op: dict) -> float:
    try:
        return min(15.0, max(2.0, float(op.get("think", THINK_SECONDS))))
    except (TypeError, ValueError):
        return THINK_SECONDS


def _pause(beat: dict) -> float:
    try:
        return min(MAX_PAUSE, max(0.0, float(beat.get("pause") or 0)))
    except (TypeError, ValueError):
        return 0.0


def _beat_seconds(beats: list) -> float:
    """The chapter's beats: their lines, the longer pause closing each paragraph, questions' time to think."""
    seconds = sum(_say_seconds(b.get("say", "")) + _pause(b) for b in beats)
    seconds += (PARAGRAPH_PAD - BEAT_PAD) * len(paragraphs(beats))
    seconds += sum(_think_seconds(op) for b in beats for op in b.get("do") or []
                   if op.get("op") == "question" or op.get("op") == "problem" and op.get("think"))
    return seconds


def estimate_minutes(script: dict) -> float:
    """How long the lecture will run: narration at speaking pace, its pauses, plus cards, map draws and fades."""
    seconds = 0.0
    if script.get("title"):
        seconds += _say_seconds(script.get("intro") or script["title"]) + 1.6
    for chapter in script.get("chapters") or []:
        seconds += _say_seconds(chapter.get("narration") or chapter.get("title", "")) + 0.8 + 1.4 + 1.0     # card, map, outro
        seconds += _beat_seconds(chapter.get("beats") or [])
    for head, body in script.get("recap") or []:
        seconds += _say_seconds(f"{head}. {body}")
    if script.get("credits"):
        seconds += 5.0
    return seconds / 60


def _pairs(value):
    """A point list as [[x, y], ...]: a flat [x1, y1, x2, y2] paired up, an [x, y, z] cut to [x, y]. A model
    writes both, and a list of the wrong shape reached numpy as a one-dimensional array mid-render."""
    if not isinstance(value, list):
        return value
    if value and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
        return [[value[i], value[i + 1]] for i in range(0, len(value) - 1, 2)]
    out = []
    for p in value:
        if isinstance(p, (list, tuple)) and len(p) >= 2 and all(isinstance(v, (int, float)) for v in p[:2]):
            out.append([p[0], p[1]])
        else:
            out.append(p)
    return out


POINT_KEYS = ("from", "to", "at", "about", "by")


def _normalise_points(value) -> None:
    """Every point list and point in an op, at any depth (a map path, a problem's figure),
    in the shapes the engine draws from (_pairs)."""
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "points":
                value[key] = _pairs(item)
            elif key in POINT_KEYS and isinstance(item, list) and len(item) >= 3 and \
                    all(isinstance(v, (int, float)) for v in item[:3]) and not any(isinstance(v, list) for v in item):
                value[key] = item[:2]
            else:
                _normalise_points(item)
    elif isinstance(value, list):
        for item in value:
            _normalise_points(item)


# ---------------- one form for each thing; mechanical fixes, made without the writer ----------------
# One op for any picture: {"op": "picture", "subject" | "query" | "image" | "illustration" | "figure" | "draw" |
# "items", caption?}; with items it is a gallery. The older ops (photo, illustration, figure, draw) still read.
# Diagrams are a flow (a chain, a hierarchy or a flowchart, by its connections), a cycle or a hub; "steps": true
# numbers a chain. The older kinds still read: flowchart, tree, hierarchy, categories, steps.
DIAGRAM_ALIASES = {"flowchart": "flow", "tree": "flow", "hierarchy": "flow", "categories": "flow", "steps": "flow"}
FIXED = "fixed: "            # a warning that says what the compiler mended by itself; the writer is not asked


def _picture_op(op: dict, fallback_id: str) -> dict:
    """The picture op as the op it amounts to (photo, illustration, figure, draw, or with items a gallery)."""
    rest = {k: v for k, v in op.items() if k != "op"}
    if rest.get("items"):
        return {**rest, "op": "gallery"}
    if rest.get("draw"):
        what = rest.pop("draw")
        return _drawn_picture({**rest, "op": "draw", "id": rest.get("id") or fallback_id, "what": what})
    if rest.get("figure"):
        figure = rest.pop("figure")
        return {**rest, "op": "figure", "id": figure}
    if rest.get("generate"):
        query = rest.pop("generate")
        return {**rest, "op": "illustration", "query": query}
    if rest.get("illustration"):
        query = rest.pop("illustration")
        return {**rest, "op": "illustration", "query": query}
    if rest.get("subject") or rest.get("query") or rest.get("image"):
        return {**rest, "op": "photo"}
    return op


def _part_words(parts) -> list[str]:
    """A draw op's part ids as the words labelled on its picture ("cell_wall" -> "cell wall"), at most 6."""
    words = [re.sub(r"[_-]+", " ", str(p)).strip() for p in parts or [] if str(p).strip()]
    return [w for w in words if w and w.lower() not in ("picture", "whole", "all")][:6]


def _drawn_picture(op: dict) -> dict:
    """A `draw` op (a detailed picture described in words, its parts named) as the picture it is now: made by the
    diagram model, every part it names labelled by the board (genimage.locate), shown whole on the stage. Nothing
    is drawn as an SVG; a picture's parts are not revealed one by one (its reveals and focuses are left out)."""
    labels = _part_words(op.get("labels") or op.get("parts"))
    out = {"op": "illustration", "query": str(op.get("what") or op.get("query") or ""), "diagram": True,
           "_drawn": str(op.get("id") or "")}
    if labels:
        out["labels"] = labels
    caption = op.get("caption") or op.get("title")
    if caption:
        out["caption"] = str(caption)
    if op.get("move") in PICTURE_MOVES:
        out["move"] = op["move"]
    return out


def _canonical_diagram(op: dict) -> None:
    if op.get("drawn") == "picture":
        # Drawn as one picture (picture_flow): what each step shows is told to the image model with the rest, not
        # made as a picture of its own.
        for node in op.get("nodes") or []:
            if isinstance(node, dict):
                picture = node.pop("picture", None)
                said = (picture.get("generate") if isinstance(picture, dict) else None) or node.pop("entity", None)
                node["_show"] = node.get("_show") or str(said or node.get("label") or node.get("id") or "").strip()
        return
    # A node's drawing is a picture the image model makes (a library drawing or an emoji is not used any more).
    for node in op.get("nodes") or []:
        if isinstance(node, dict) and node.get("entity"):
            entity = node.pop("entity")
            node.setdefault("picture", {"generate": _thing_op(entity)["query"]})
    kind = str(op.get("kind") or "flow")
    if kind == "steps":
        op["steps"] = True
    if kind in ("tree", "hierarchy", "categories") and not op.get("edges"):
        ids = [str(n.get("id")) for n in op.get("nodes") or [] if isinstance(n, dict) and n.get("id")]
        if len(ids) > 1:
            op["edges"] = [[ids[0], i] for i in ids[1:]]       # the whole over its kinds
    op["kind"] = DIAGRAM_ALIASES.get(kind, kind)


def canonical_ops(script: dict) -> None:
    """Each picture op as the op it amounts to and each diagram kind as one of flow, cycle, hub (in place)."""
    for c, chapter in enumerate(script.get("chapters") or []):
        for b, beat in enumerate(chapter.get("beats") or []):
            ops = beat.get("do")
            if not isinstance(ops, list):
                continue
            for k, op in enumerate(ops):
                if not isinstance(op, dict):
                    continue
                if op.get("op") == "picture":
                    ops[k] = op = _picture_op(op, f"picture{c + 1}_{b + 1}_{k + 1}")
                if op.get("op") == "draw":
                    ops[k] = op = _drawn_picture(op)
                if op.get("_drawn"):
                    script.setdefault("_pictured", []).append(op["_drawn"])
                if op.get("op") == "problem" and isinstance(op.get("figure"), dict) and op["figure"].get("op") == "picture":
                    op["figure"] = _picture_op(op["figure"], f"{op.get('id') or 'problem'}_figure")
                if op.get("op") == "diagram":
                    _canonical_diagram(op)
                if op.get("op") in ("define", "compare"):
                    # Their library drawing is gone: a define card and a comparison are words (a picture beside
                    # them is a picture op of its own).
                    op.pop("entity", None)
                    for column in op.get("columns") or []:
                        if isinstance(column, dict):
                            column.pop("entity", None)
                for _, spec in pictures_of(op):
                    if isinstance(spec, dict) and spec.get("entity") and not spec.get("generate"):
                        spec["generate"] = _thing_op(spec.pop("entity"))["query"]
                    if isinstance(spec, dict) and spec.get("draw") and not spec.get("generate"):
                        spec["generate"] = str(spec.pop("draw"))       # made as a picture, never drawn as an SVG


def _drop(op: dict, at: str, why: str, notes: list[str]) -> None:
    op["_drop"] = True
    notes.append(f"{FIXED}{at}: left out {op.get('op')!r}: {why}")


def _purge(script: dict) -> None:
    """Take out the ops marked to drop."""
    for chapter in script.get("chapters") or []:
        for beat in chapter.get("beats") or []:
            if isinstance(beat.get("do"), list):
                beat["do"] = [op for op in beat["do"] if not (isinstance(op, dict) and op.get("_drop"))]


def _year_of(value) -> int | None:
    """A year as a number: 1600, "1600", "c. 1600", "250 BC" (-250), "AD 100"."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    hit = re.search(r"(\d{1,4})\s*(BCE?|B\.C\.)?", str(value or ""), re.I)
    if not hit:
        return None
    return -int(hit.group(1)) if hit.group(2) else int(hit.group(1))


def _historical(name, year: int):
    """historical.empire for a lint check: the state as found, None when the map has no such state, True when the
    map cannot be had here (no network): the engine then decides."""
    try:
        import historical

        if historical.path(year) is None:
            return True
        return historical.empire(str(name), year)
    except Exception:  # noqa: BLE001 -- no shapely here: leave it to the engine
        return True


def _emblem_op(script: dict) -> dict:
    """The picture op that makes a lecture's emblem: one simple motif for the whole series."""
    what = str(script["emblem"]).strip()[:120]
    # Not drawn to match another picture: an emblem is a motif, not a person already shown.
    return {"op": "illustration", "query": f"{what}, a simple bold emblem", "optional": True, "_emblem": True,
            **SMALL_PICTURE}


def _emblem_file(script: dict) -> str | None:
    if not (isinstance(script.get("emblem"), str) and script["emblem"].strip()):
        return None
    row = script_photos.get(_photo_key(_emblem_op(script)))
    return str(row["file"]) if row and row.get("file") else None


def _fix_unusable(script: dict, has_map: bool) -> list[str]:
    """Ops that cannot be drawn as written and need no new words to mend: an unknown op, a map op with no map,
    one missing what it draws, a picture whose kind is not one of the picture keys. Each is left out (a broken
    picture beside a label is dropped and the label stays), with a note."""
    notes: list[str] = []
    _still_timelines(script)
    figures = script.get("figures") or {}
    known = {"panel", "fact", "stat", "bars", "clear", "icon", "figure", "photo", "illustration"} \
        | KIT_OPS | MAP_OPS | BUILD_OPS | STEP_OPS | WORK_OPS | FREE_OPS
    need = {"panel": ["title"], "fact": ["text"], "stat": ["value", "label"], "bars": ["items"],
            "river": ["name"], "state": ["name"], "path": ["points"], "arrow": ["points"], "icon": ["name"],
            "empire": ["name"]}
    # Pictures shown whole (a book figure shown as its picture, a draw op made as a picture): no parts to reveal.
    pictured: set[str] = {str(x) for x in script.get("_pictured") or []}
    for c, chapter in enumerate(script.get("chapters") or []):
        for b, beat in enumerate(chapter.get("beats") or []):
            at = f"chapter {c + 1} beat {b + 1}"
            ops = beat.get("do") if isinstance(beat.get("do"), list) else []
            beat["do"] = ops = [op for op in ops if isinstance(op, dict)]
            for op in ops:
                kind = op.get("op")
                if kind in ("reveal", "focus", "zoom") and str(op.get("diagram")) in pictured:
                    _drop(op, at, f"{op.get('diagram')!r} is shown whole as a picture, with no parts", notes)
                    continue
                if kind in RETIRED_OPS:
                    _drop(op, at, "it is no longer built: free-form Manim draws it (a manim op)", notes)
                    continue
                if kind not in known:
                    _drop(op, at, "no such op", notes)
                    continue
                if kind in MAP_OPS and not has_map:
                    _drop(op, at, "it needs a map and the script has no region", notes)
                    continue
                if kind in MAP_OPS and chapter.get("map") is False:
                    _drop(op, at, "its chapter has no map (map: false)", notes)
                    continue
                missing = [f for f in need.get(kind, []) if not op.get(f)]
                if kind == "marker" and not (op.get("place") or op.get("lonlat")):
                    missing.append("place")
                if kind == "photo" and not (op.get("image") or op.get("query") or op.get("subject")):
                    missing.append("subject")
                if kind == "illustration" and not (op.get("query") or op.get("image")):
                    missing.append("query")
                if kind == "graticule" and op.get("lat") is None and op.get("lon") is None:
                    missing.append("lat or lon")
                if kind == "journey":
                    stops = op.get("stops") if isinstance(op.get("stops"), list) else []
                    op["stops"] = [x for x in stops if isinstance(x, str) or (
                        isinstance(x, (list, tuple)) and len(x) == 2 and all(isinstance(v, (int, float)) for v in x))]
                    if len(op["stops"]) < 2:
                        missing.append("two stops")
                if kind == "gallery" and op.get("layout") is not None and op["layout"] not in GALLERY_LAYOUTS:
                    notes.append(f"{FIXED}{at}: a gallery's layout is one of {', '.join(GALLERY_LAYOUTS)}; "
                                 f"{op['layout']!r} left out")
                    op.pop("layout")
                if kind in ("illustration", "photo") and op.get("move") is not None \
                        and op.get("move") not in PICTURE_MOVES:
                    notes.append(f"{FIXED}{at}: a picture's move is one of {', '.join(PICTURE_MOVES)}; "
                                 f"{op.get('move')!r} left out (it holds still)")
                    op.pop("move")
                if kind == "empire":
                    year = _year_of(op.get("year"))
                    if year is None:
                        missing.append("year")
                    else:
                        op["year"] = year
                        found = _historical(op.get("name"), year) if op.get("name") else True
                        if found is None:
                            _drop(op, at, f"no state named {op.get('name')!r} on the historical map of {year}", notes)
                            continue
                if kind == "figure" and str(op.get("id")) not in figures:
                    _drop(op, at, f"no book figure {op.get('id')!r}", notes)
                    continue
                if missing:
                    _drop(op, at, f"it has no {missing[0]}", notes)
                    continue
                if kind == "compare":
                    columns = [c for c in (op.get("columns") if isinstance(op.get("columns"), list) else [])
                               if isinstance(c, dict) and (c.get("title") or c.get("points"))]
                    for j, column in enumerate(columns):
                        if not column.get("title"):
                            column["title"] = f"Side {j + 1}"
                        if not isinstance(column.get("points"), list):
                            column["points"] = [str(column["points"])] if column.get("points") else []
                        column["points"] = [str(p) for p in column["points"]][:4]
                    if len(columns) > 3:
                        notes.append(f"{FIXED}{at}: compare cut to its first 3 columns")
                        columns = columns[:3]
                    op["columns"] = columns
                    if len(columns) == 1:
                        # One column compares nothing: its title and points, as a card.
                        only = columns[0]
                        text = only["title"] + (": " + "; ".join(only["points"]) if only["points"] else "")
                        op.clear()
                        op.update(_card_op(only["title"], "; ".join(only["points"])))
                        notes.append(f"{FIXED}{at}: a compare of one column shown as a card ({text[:60]})")
                        continue
                    if not columns:
                        _drop(op, at, "it has no columns", notes)
                        continue
                if kind == "timeline":
                    events = [e for e in (op.get("events") if isinstance(op.get("events"), list) else [])
                              if (isinstance(e, (list, tuple)) and len(e) >= 2) or (isinstance(e, dict) and e.get("label"))]
                    op["events"] = events
                    _fix_timeline(op, at, notes)
                    events = op["events"]
                    if len(events) == 1:
                        # One date is not a timeline: the date and what happened, as a card.
                        e = events[0]
                        date, label = (e[0], e[1]) if isinstance(e, (list, tuple)) else (e.get("date"), e.get("label"))
                        text = f"{date}: {label}" if date not in (None, "") else str(label)
                        op.clear()
                        op.update(_card_op(str(date or ""), str(label)) if date not in (None, "") else {"op": "fact", "text": text})
                        notes.append(f"{FIXED}{at}: a timeline of one event shown as a card ({text[:60]})")
                        continue
                if kind in KIT_OPS:
                    problem = _kit_problem(op)
                    if problem:
                        # Cannot be drawn as written: left out, and the narration over it stands.
                        _drop(op, at, problem, notes)
                        continue
                if kind == "figure" and script.get("rebuild_figures") and not op.get("photo"):
                    # A figure in the table is its redraw (the diagram model's copy, never the book's own picture):
                    # shown whole, as a picture.
                    op["photo"] = True
                    pictured.add(str(op.get("id")))
                    notes.append(f"{FIXED}{at}: figure {op.get('id')!r} shown as its redrawn picture")
                if kind == "figure" and op.get("show") and (figures[str(op["id"])] or {}).get("parts"):
                    parts = [str(p) for p in figures[str(op["id"])]["parts"]]
                    _keep_known(op, "show", parts, at, notes)
                if kind == "gallery":
                    items = op.get("items") if isinstance(op.get("items"), list) else []
                    kept = [i for i in items if not (isinstance(i, dict) and i.get("figure")
                                                     and str(i["figure"]) not in figures)]
                    if len(kept) < len(items):
                        notes.append(f"{FIXED}{at}: gallery item(s) of book figures that do not exist left out")
                        op["items"] = kept
                for where, spec in pictures_of(op):
                    problem = _picture_problem(spec, figures)
                    if problem:
                        _forget_picture(op, spec)
                        notes.append(f"{FIXED}{at}: {where}: picture left out ({problem}); its words stand alone")
    _purge(script)
    return notes


TIMELINE_MOST = 10       # events on one timeline (pocket_lecture.big_timeline)


def _fix_timeline(op: dict, at: str, notes: list[str]) -> None:
    """v2: a timeline's range, spans and scale read as years (timeline_dates), and what will not do left out with a
    note: a range that names no two years, a span that does not, events outside the range, events past ten."""
    import timeline_dates as td

    years = [td.year(e[0] if isinstance(e, (list, tuple)) else e.get("date")) for e in op["events"]]
    rng = op.get("range")
    if rng is not None:
        a, b = (td.year(rng[0]), td.year(rng[1])) if isinstance(rng, (list, tuple)) and len(rng) == 2 else (None, None)
        if a is None or b is None or a == b:
            notes.append(f"{FIXED}{at}: a timeline's range is two dates [from, to]; {rng!r} left out")
            op.pop("range")
        else:
            lo, hi = min(a, b), max(a, b)
            op["range"] = [str(rng[0]), str(rng[1])] if a <= b else [str(rng[1]), str(rng[0])]
            if all(y is not None for y in years):
                kept = [e for e, y in zip(op["events"], years) if lo <= y <= hi]
                if len(kept) < len(op["events"]):
                    notes.append(f"{FIXED}{at}: {len(op['events']) - len(kept)} timeline event(s) outside its range "
                                 f"{op['range'][0]}-{op['range'][1]} left out")
                    op["events"] = kept
                    years = [y for y in years if lo <= y <= hi]
    if op.get("spans") is not None:
        spans = []
        for sp in op["spans"] if isinstance(op["spans"], list) else []:
            if isinstance(sp, dict):
                sp = [sp.get("from"), sp.get("to"), sp.get("label") or ""]
            if isinstance(sp, (list, tuple)) and len(sp) >= 2 and td.year(sp[0]) is not None \
                    and td.year(sp[1]) is not None and td.year(sp[0]) != td.year(sp[1]):
                spans.append([str(sp[0]), str(sp[1]), str(sp[2]) if len(sp) > 2 and sp[2] else ""])
            else:
                notes.append(f"{FIXED}{at}: a timeline span is [from, to, label] with two dates; {sp!r} left out")
        op["spans"] = spans[:6]
        if not spans:
            op.pop("spans")
    if op.get("scale") not in (None, "even", "years"):
        notes.append(f"{FIXED}{at}: a timeline's scale is \"even\" or left out; {op['scale']!r} left out")
        op.pop("scale")
    if (op.get("range") or op.get("spans")) and (not years or any(y is None for y in years) or op.get("scale") == "even"):
        notes.append(f"{FIXED}{at}: not every date of this timeline reads as a year, so it is spaced evenly and its "
                     "range and spans are left out")
        op.pop("range", None)
        op.pop("spans", None)
    if len(op["events"]) > TIMELINE_MOST:
        notes.append(f"{FIXED}{at}: a timeline shows at most {TIMELINE_MOST} events; the first {TIMELINE_MOST} kept")
        op["events"] = op["events"][:TIMELINE_MOST]


def _card_op(head: str, body: str) -> dict:
    """A card on the stage: the head big, the body under it. A fact on a board is only a chip in the strip at its
    top, so a beat whose one picture was mended into a fact showed an empty stage."""
    return {"op": "define", "term": head, "meaning": body} if head and body else {"op": "fact", "text": head or body}


def _forget_picture(op: dict, spec) -> None:
    """Take one picture off the node, event, label or stop that carries it."""
    for n in op.get("nodes") or []:
        if isinstance(n, dict) and n.get("picture") is spec:
            n.pop("picture")
    events = op.get("events") or []
    for k, e in enumerate(events):
        if isinstance(e, dict) and e.get("picture") is spec:
            e.pop("picture")
        elif isinstance(e, list) and len(e) > 2 and e[2] is spec:
            events[k] = e[:2]
    if op.get("picture") is spec:
        op.pop("picture")
    if isinstance(op.get("pictures"), list):
        op["pictures"] = [None if p is spec else p for p in op["pictures"]]


def _keep_known(op: dict, field: str, ids: list[str], at: str, notes: list[str]) -> None:
    """Names in op[field] that are none of `ids`, left out."""
    given = [str(x) for x in op.get(field) or []]
    kept = [x for x in given if x in ids]
    if len(kept) < len(given):
        notes.append(f"{FIXED}{at}: {op.get('op')} {op.get('id') or op.get('diagram') or ''} {field}: no part "
                     f"{', '.join(repr(x) for x in given if x not in ids)} (left out)")
        if kept:
            op[field] = kept
        else:
            op.pop(field)


def _fix_diagram(op: dict, at: str, notes: list[str]) -> None:
    """A diagram's mechanical faults: an unknown kind, a shape, style or motion it does not have, an edge to no
    node, a show of no node, too many items in a node."""
    if op.get("kind", "flow") not in DIAGRAM_KINDS:
        notes.append(f"{FIXED}{at}: diagram {op.get('id')!r}: no kind {op.get('kind')!r}; drawn as a flow")
        op["kind"] = "flow"
    nodes = [n for n in op.get("nodes") or [] if isinstance(n, dict)]
    ids = [str(n.get("id")) for n in nodes if n.get("id")]
    motions = set(NODE_ANIMS) | {"none", "auto"}
    for n in nodes:
        if n.get("shape") and str(n["shape"]) not in FLOW_SHAPES:
            notes.append(f"{FIXED}{at}: diagram node {n.get('id')!r}: no shape {n['shape']!r} (a plain box)")
            n.pop("shape")
        if n.get("anim") is not None and str(n["anim"]) not in motions:
            notes.append(f"{FIXED}{at}: diagram node {n.get('id')!r}: no motion {n['anim']!r} (moves as its thing does)")
            n.pop("anim")
        if isinstance(n.get("items"), list) and len(n["items"]) > 5:
            notes.append(f"{FIXED}{at}: diagram node {n.get('id')!r}: items cut to the first 5")
            n["items"] = n["items"][:5]
    _edges_as_lists(op)
    edges = op.get("edges") or []
    if isinstance(edges, list):
        kept = [e for e in edges if isinstance(e, list) and len(e) >= 2 and str(e[0]) in ids and str(e[1]) in ids]
        if len(kept) < len(edges):
            notes.append(f"{FIXED}{at}: diagram {op.get('id')!r}: {len(edges) - len(kept)} edge(s) to no node left out")
        for e in kept:
            if len(e) > 3 and e[3] and str(e[3]) not in EDGE_STYLES:
                e[3] = "solid"
        op["edges"] = kept
    _keep_known(op, "show", ids, at, notes)


STEP_DIAGRAM_OPS = {"reveal", "focus", "zoom"}
# The ops that put up a picture a later step can name by its id.
PICTURE_HOLDERS = {"diagram", "draw", "figure", "problem"}


def _fix_steps(script: dict) -> list[str]:
    """Steps that point at what is not there, mended: a reveal, focus or zoom of no picture
    drawn earlier in its chapter is left out; a reveal's unknown parts are left out (and the reveal, if none is
    left); a focus on no part is left out; a zoom on no part zooms on the whole; an answer or option with no
    question before it is left out; a picture's "show" of no part leaves that name out."""
    notes: list[str] = []
    figures = script.get("figures") or {}
    for c, chapter in enumerate(script.get("chapters") or []):
        known: dict[str, list[str] | None] = {}
        choices: list | None = None
        for b, beat in enumerate(chapter.get("beats") or []):
            at = f"chapter {c + 1} beat {b + 1}"
            for op in beat.get("do") or []:
                if not isinstance(op, dict):
                    continue
                kind = op.get("op")
                if kind == "diagram":
                    _fix_diagram(op, at, notes)
                if kind in STEP_DIAGRAM_OPS:
                    key = str(op.get("diagram") or "")
                    if key not in known:
                        _drop(op, at, f"no picture {key!r} is drawn earlier in this chapter", notes)
                        continue
                    parts = known[key]
                    if parts is not None and kind == "reveal":
                        _keep_known(op, "nodes", parts, at, notes)
                        if not op.get("nodes"):
                            _drop(op, at, f"none of its nodes is a part of {key!r}", notes)
                    elif parts is not None and kind == "focus" and str(op.get("node") or "") not in parts:
                        _drop(op, at, f"{key!r} has no part {op.get('node')!r}", notes)
                    elif parts is not None and kind == "zoom" and op.get("node") is not None \
                            and str(op["node"]) not in parts:
                        notes.append(f"{FIXED}{at}: zoom: {key!r} has no part {op['node']!r}; zooms on the whole")
                        op.pop("node")
                    continue
                if kind == "answer" and choices is None:
                    _drop(op, at, "no question is asked before it in this chapter", notes)
                    continue
                if kind == "option" and (not choices or _choice_index(choices, op.get("choice")) is None):
                    _drop(op, at, f"no question with a choice {op.get('choice')!r} before it", notes)
                    continue
                if kind == "question":
                    choices = op.get("choices") if isinstance(op.get("choices"), list) else []
                    continue
                if kind == "problem" and isinstance(op.get("figure"), dict) and op["figure"].get("op") in RETIRED_OPS:
                    notes.append(f"{FIXED}{at}: left out the problem's {op['figure'].get('op')!r} figure: it is no "
                                 "longer built (draw it with a manim op on the beats before)")
                    op.pop("figure")
                if kind == "draw" and op.get("show"):
                    parts = _diagram_parts(op, figures)
                    if parts is not None:
                        _keep_known(op, "show", parts, at, notes)
                if op.get("id") and kind in PICTURE_HOLDERS:
                    key = str(op["id"])
                    if kind == "problem":
                        known[key] = []
                        if isinstance(op.get("figure"), dict):
                            known[f"{key}_figure"] = _diagram_parts(op["figure"], figures)
                    else:
                        known[key] = _diagram_parts(op, figures)
    _purge(script)
    return notes


def mechanical_fixes(script: dict, has_map: bool) -> list[str]:
    """Everything the compiler mends by itself, in place, before the checks: what it did, as warnings that start
    with "fixed: " (shown in the log, never sent back to the writer)."""
    canonical_ops(script)
    notes = _fix_unusable(script, has_map)
    notes += _split_manim_beats(script)
    notes += _fix_steps(script)
    notes += _build_with_speech(script)
    reveals: list[str] = []
    _complete_reveals(script, reveals, script.get("figures") or {})
    return notes + reveals


def _split_manim_beats(script: dict) -> list[str]:
    """A manim op shares a beat with other ops: the beat becomes two, the figure on one and the rest on the other,
    in the order they were written, the line's sentences shared between them. A line of one sentence keeps the
    figure, and the other ops go to the next beat (or the one before) that is not a figure. Sending the section
    back for it rewrote the whole section and its figures."""
    notes: list[str] = []
    for c, chapter in enumerate(script.get("chapters") or []):
        beats = chapter.get("beats") or []
        out: list = []
        moved: list[tuple[int, list]] = []          # (index in out, ops) for a one-sentence line
        for b, beat in enumerate(beats):
            ops = beat.get("do") if isinstance(beat, dict) and isinstance(beat.get("do"), list) else []
            manim = [op for op in ops if isinstance(op, dict) and op.get("op") == "manim"]
            rest = [op for op in ops if not (isinstance(op, dict) and op.get("op") == "manim")]
            if len(manim) != 1 or not rest:
                out.append(beat)
                continue
            at = f"chapter {c + 1} beat {b + 1}"
            figure_first = ops.index(manim[0]) < ops.index(rest[0])
            said = [x for x in re.split(r"(?<=[.?!।])\s+", str(beat.get("say") or "").strip()) if x]
            if len(said) >= 2:
                half = (len(said) + 1) // 2
                first, second = " ".join(said[:half]), " ".join(said[half:])
                one = {**beat, "say": first, "do": manim if figure_first else rest}
                two = {k: v for k, v in beat.items() if k not in ("lines", "at")}
                two.update({"say": second, "do": rest if figure_first else manim})
                one.pop("lines", None)
                out += [one, two]
                notes.append(f"{FIXED}{at}: its manim figure and its other ops put on beats of their own")
            else:
                out.append({**beat, "do": manim})
                moved.append((len(out) - 1, rest))
                notes.append(f"{FIXED}{at}: its other ops moved off the manim figure's beat")
        for at_out, rest in moved:
            # The next beat that is not a figure, else the one before; with neither, the ops are left out.
            near = [k for k in range(at_out + 1, len(out))] + [k for k in range(at_out - 1, -1, -1)]
            home = next((k for k in near if isinstance(out[k], dict)
                         and not any(isinstance(op, dict) and op.get("op") == "manim" for op in out[k].get("do") or [])),
                        None)
            if home is not None:
                out[home] = {**out[home], "do": [*(out[home].get("do") or []), *rest]}
        if beats:
            chapter["beats"] = out
    return notes


# A picture that stays up this many beats at most is built along them (_build_with_speech).
SPEECH_REACH = 6
# Ops that put a new picture on the stage: the diagram before is gone, so it is built no further.
_NEW_PICTURE = {"diagram", "draw", "figure", "picture", "photo", "illustration", "gallery", "compare", "define",
                "timeline", "process", "quote", "problem", "manim", "equation"}


def _named_pos(label: str, said: str) -> int:
    """Where in a line a part is first named (its whole label, or the first of its longer words): to order them."""
    low, said = label.lower().strip(), said.lower()
    if low and low in said:
        return said.index(low)
    words = [w for w in re.findall(r"\w+", low) if len(w) > 3]
    hits = [said.find(w) for w in words if w in said]
    return min(hits) if hits else len(said)


def _named_in(label: str, said: str) -> bool:
    """Whether a line names a diagram's part: its whole label, or every longer word of it."""
    label, said = label.lower().strip(), said.lower()
    if not label:
        return False
    if label in said:
        return True
    # Words with their vowel signs (Devanagari and the other Indic scripts' marks are not \w): "समाज", not "सम".
    words = [w for w in re.findall(r"(?:[\w']|[\u0900-\u0DFF])+", label) if len(w) > 3]
    return bool(words) and all(re.search(rf"\b{re.escape(w)}", said) for w in words)


def _build_with_speech(script: dict) -> list[str]:
    """A diagram put up whole while the lines after it name its parts one by one is built in step with them: the
    parts its own line names (or its first) come first, and each other part arrives on the line that names it,
    as a teacher draws on a board while talking. Only for a diagram the script shows whole and never reveals
    itself; its parts no later line names are there from the start."""
    notes: list[str] = []
    for c, chapter in enumerate(script.get("chapters") or []):
        beats = chapter.get("beats") or []
        stepped = {str(op.get("diagram")) for b in beats for op in b.get("do") or []
                   if isinstance(op, dict) and op.get("op") in ("reveal", "focus", "zoom")}
        for i, beat in enumerate(beats):
            for op in beat.get("do") or []:
                if not (isinstance(op, dict) and op.get("op") == "diagram" and op.get("id")
                        and op.get("show") is None and str(op["id"]) not in stepped):
                    continue
                nodes = [n for n in op.get("nodes") or [] if isinstance(n, dict) and n.get("id") is not None]
                if len(nodes) < 3:
                    continue
                label = {str(n["id"]): str(n.get("label") or n["id"]) for n in nodes}
                own = str(beat.get("say") or "")
                # The parts its own line names, in the order it names them: the first is drawn with the diagram,
                # each other arrives on its own words (a reveal of its own on this beat, timed by the engine).
                here = sorted((i_ for i_ in label if _named_in(label[i_], own)),
                              key=lambda i_: _named_pos(label[i_], own))
                first = here[:1] or [str(nodes[0]["id"])]
                now = here[1:]
                later: dict[int, list[str]] = {}
                placed = set(first) | set(now)
                for j in range(i + 1, min(len(beats), i + 1 + SPEECH_REACH)):
                    ops = [o for o in beats[j].get("do") or [] if isinstance(o, dict)]
                    if any(o.get("op") in _NEW_PICTURE for o in ops):
                        break
                    said = str(beats[j].get("say") or "")
                    named = [n for n in label if n not in placed and _named_in(label[n], said)]
                    if named:
                        later[j] = named
                        placed.update(named)
                if len(now) + sum(len(v) for v in later.values()) < 2:
                    continue
                # What no line names is there from the start, so nothing is left off.
                op["show"] = [n for n in label if n in first or n not in placed]
                for n in now:
                    beat.setdefault("do", []).append({"op": "reveal", "diagram": str(op["id"]), "nodes": [n]})
                for j, named in later.items():
                    beats[j].setdefault("do", []).append({"op": "reveal", "diagram": str(op["id"]), "nodes": named})
                notes.append(f"{FIXED}chapter {c + 1} beat {i + 1}: diagram {op['id']!r} built as it is spoken of "
                             f"({len(placed) - len(first)} parts arrive on the words that name them)")
    return notes



def lint(script: dict, min_minutes: float | None = None, min_questions: int | None = None,
         min_examples: int | None = None, min_problems: int | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors stop compilation; warnings are layout advice.

    The checks the guide asks for before any render: unknown operations,
    map operations without a map, captions longer than two lines, a panel
    that overflows into the caption, a beat whose animations would outlast
    its narration.
    """
    no_icons(script)
    errors: list[str] = []
    warnings: list[str] = []
    no_key_points(script, warnings)
    anchors(script, errors, warnings)
    if script.get("style", "atlas") not in STYLES:
        errors.append(f"style must be one of {', '.join(STYLES)}")
    if str(script.get("art") or "auto").lower().replace("watercolor", "watercolour") not in ARTS:
        errors.append(f"art must be one of {', '.join(ARTS)}")
    if script.get("region") and not isinstance(script["region"], dict):
        errors.append('region must be an object, e.g. {"country": "India", "view": "ind"}, or left out for no map')
        script = {**script, "region": None}
    region_notes = _fix_region(script)
    warnings += region_notes
    warnings += _use_places(script)
    has_map = bool(script.get("region"))
    # What needs no new words is mended here (and said in the warnings, "fixed: ..."); the rest are errors.
    warnings += mechanical_fixes(script, has_map)
    if has_map:
        e, w = _resolve_map_points(script)
        errors += e
        warnings += w
    chapters = script.get("chapters") or []
    places: list[tuple[str, str]] = []
    icon_names: list[tuple[str, str]] = []
    photos: list[tuple[str, dict]] = []
    # What each beat is teaching, for the pictures made there: the image model is told what the picture is for.
    contexts: dict[str, dict] = {}
    if not chapters:
        errors.append("a lecture needs at least one chapter")
    for ci, chapter in enumerate(chapters, 1):
        where = f"chapter {ci}"
        diagrams: dict = {}          # diagram id -> node ids, for the chapter's reveal and focus
        # A chapter card without its own narration says the chapter's title: a missing line cost a whole turn.
        if not chapter.get("title"):
            errors.append(f"{where}: missing title")
        used = 0.0
        beats_here = chapter.get("beats") or []
        for bi, beat in enumerate(beats_here, 1):
            at = f"{where} beat {bi}"
            say = str(beat.get("say") or "").strip()
            following = str((beats_here[bi] if bi < len(beats_here) else {}).get("say") or "").strip()
            contexts[at] = {"lecture": script.get("title"), "subject": script.get("subject") or script.get("genre"),
                            "chapter": chapter.get("title"), "said": " ".join(x for x in (say, following) if x)}
            if not say:
                errors.append(f"{at}: no narration ('say')")
            elif len(say) > 184:
                warnings.append(f"{at}: the caption runs past two lines ({len(say)} characters); split the beat")
            ops = beat.get("do") or []
            _normalise_points(ops)
            if len(ops) > 5:
                warnings.append(f"{at}: {len(ops)} operations in one beat; the eye cannot follow more than about four")
            for op in ops:
                kind = op.get("op")
                drawn_map = map_drawn_by(op)
                if drawn_map:
                    errors.append(f"{at}: {drawn_map}")
                    continue
                wrong_maker = _maker_problem(op, script.get("genre"))
                if wrong_maker:
                    errors.append(f"{at}: {wrong_maker}")
                    continue
                unsaid = _labels_unsaid(op, [say] + [str(b.get("say") or "") for b in beats_here[bi:bi + 2]])
                # A label with its own anchor (its "on", anchors) is said by those words.
                unsaid = [x for x in unsaid if x not in (beat.get("_spoken_as") or {})]
                if unsaid:
                    warnings.append(f"{at}: the picture's labels {', '.join(repr(x) for x in unsaid)} are never said "
                                    "while it is up; say each label's words in this line or the next two (each label "
                                    "comes on, and the camera moves in on its part, as its name is said)")
                # (`part`, not `where`: that is the chapter's name, and every later beat's warnings were put under
                # the last picture's part -- "node 'fields' beat 23" for "chapter 4 beat 23".)
                for part, spec in pictures_of(op):
                    problem = _picture_problem(spec, script.get("figures") or {})
                    if problem:
                        errors.append(f"{at}: {part}: {problem}")
                    elif _picture_fetch(spec):
                        fetch = _picture_fetch(spec)
                        fetch["_beside"] = _beside_words(op, spec)
                        photos.append((at, fetch))
                if kind == "manim":
                    if not isinstance(op.get("code"), str) or not op["code"].strip():
                        errors.append(f"{at}: a manim op needs its code: the Python that draws this beat")
                    import free_check
                    import mapguard

                    # The pictures its code asks for (picture("...")), made now like an icon's, so the block finds
                    # them made; a picture of a map is refused, as anywhere.
                    for what in free_check.pictures_in(op.get("code")):
                        if mapguard.is_map(what):
                            errors.append(f"{at}: picture({what!r}) asks for a map; {mapguard.MAP_ADVICE}")
                        else:
                            icon_names.append((at, what))
                    if len(ops) > 1:
                        errors.append(f"{at}: a manim beat carries only its manim op; draw the rest in its code, "
                                      "or put the other ops on beats of their own")
                    if op.get("area") not in (None, "full", "left"):
                        errors.append(f"{at}: a manim op's area is \"left\" (the figure in the left half, a working "
                                      "or card beside it) or \"full\" (the default)")
                    continue
                if kind in BUILD_OPS | STEP_OPS | WORK_OPS:
                    problem = _build_problem(op, diagrams, script.get("figures") or {})
                    if problem:
                        errors.append(f"{at}: {problem}")
                    if kind == "gallery" and not problem:
                        photos.extend((at, item) for item in _gallery_fetches(op))
                # (An unknown op, a map op with no map and one missing what it draws were left out above.)
                if kind == "journey" and has_map:
                    places.extend((at, str(x)) for x in op["stops"] if isinstance(x, str))
                if kind == "marker" and op.get("place") and has_map:
                    places.append((at, str(op["place"])))
                if kind == "icon":
                    icon_names.append((at, str(op["name"])))
                    spots = _icon_spots(op)
                    if spots and not has_map:
                        errors.append(f"{at}: an icon at a place needs a map; give the script a region, or drop place")
                    elif spots:
                        places.extend((at, str(p)) for p in spots if isinstance(p, str))
                if kind == "photo":
                    photos.append((at, op))
                if kind in KIT_OPS:
                    problem = _kit_problem(op)
                    if problem:
                        errors.append(f"{at}: {problem}")
                if kind == "illustration":
                    if not any(o is not op and isinstance(o, dict) and o.get("op") in STAGE_PICTURES for o in ops):
                        # The line's only picture: it has the screen to itself (pocket_lecture._full_picture), so it
                        # is made in the screen's shape, a whole scene unless it is a labelled diagram.
                        op.setdefault("aspect", "16:9")
                        if not op.get("diagram") and not _labels_of(op) and not op.get("_emblem"):
                            op.setdefault("scene", True)
                    photos.append((at, op))
                if kind == "problem" and isinstance(op.get("figure"), dict) and op["figure"].get("op") == "draw":
                    # A problem's figure described in words: made by the diagram model like any detailed picture.
                    photos.append((at, {**_drawn_picture(op["figure"]), "optional": True}))
                if kind == "figure":
                    figure = (script.get("figures") or {}).get(str(op.get("id"))) or {}
                    if not Path(str(figure.get("file", ""))).is_file():
                        errors.append(f"{at}: figure {op.get('id')!r} has no image file")
                for field in ("color",):
                    if op.get(field) is not None:
                        try:
                            _colour(op[field])
                        except ValueError as error:
                            errors.append(f"{at}: {error}")
                if kind in ("panel", "clear"):
                    used = 0.0
                used += _panel_height(op)
                if used > PANEL_ROOM:
                    warnings.append(f"{at}: the panel overflows into the caption; start a new panel")
                    used = _panel_height(op)
    region_problem, home = _region_problem(script.get("region"))
    if region_problem:
        errors.append(region_problem)
    else:
        errors += _unknown_places(places, home, script.get("region"))
    # A flow drawn as one picture: made now and cut into its parts (or built as a diagram, said why).
    warnings += _picture_flows(script)
    # An icon is a picture of the thing it names, made by the illustration model now (the engine finds it made).
    photos.extend((at, _thing_op(name)) for at, name in icon_names)
    if isinstance(script.get("emblem"), str) and script["emblem"].strip():
        # The lecture's emblem: one small picture, made like any other (optional: no emblem if it cannot be made).
        photos.append(("the lecture's emblem", _emblem_op(script)))
    errors += _unfetched_photos(photos, script.get("genre"), script.get("style"), contexts)
    warnings += [f"{at}: no reusable illustration for {' '.join(str(op.get('query') or op.get('image') or '').split())!r}; it is left out "
                 "(try another description with find_illustration)" for at, op in photos
                 if op.get("op") == "illustration" and _photo_key(op) not in script_photos]
    if script.get("teaching_rules") is False:
        # How to teach is the writer's (the app's lectures, from a transcript): only what the video needs to be
        # drawn is checked, and the free Manim blocks run.
        if not any(e.startswith(("chapter", "a lecture")) and "manim" in e for e in errors):
            import free_check

            errors += free_check.verify(script)
        return errors, warnings
    e, w = _bare_stretches(script)
    errors += e
    warnings += w
    e, w = _plain_language(script)
    errors += e
    warnings += w
    e, w = _text_heavy(script)
    errors += e
    warnings += w
    e, w = _language_mix(script)
    errors += e
    warnings += w
    e, w = _problem_depth(script) if min_problems else ([], [])
    errors += e
    warnings += w
    e, w = _book_questions(script, whole=bool(min_minutes))
    errors += e
    warnings += w
    if not any(e.startswith(("chapter", "a lecture")) and "manim" in e for e in errors):
        import free_check

        errors += free_check.verify(script)
    e, w = _teaching(script, min_questions, min_examples, min_problems)
    e2, w2 = _panel_text(script)
    e, w = e + e2, w + w2
    # A written lecture (one given a length to reach) must teach; elsewhere (an offline test script, a hand-made
    # one) the same checks are advice.
    errors += e if min_minutes else []
    warnings += w + ([] if min_minutes else e)
    # (_panel_text rides with them: an offline test script puts every line in the panel.)
    minutes = estimate_minutes(script)
    if min_minutes and chapters and minutes < min_minutes * 0.85:
        beats = sum(len(c.get("beats") or []) for c in chapters)
        words = sum(len(str(b.get("say", "")).split()) for c in chapters for b in c.get("beats") or [])
        need = int((min_minutes * 60 - (minutes * 60 - words * WORD_SECONDS)) / WORD_SECONDS) - words
        errors.append(f"the lecture runs about {minutes:.1f} min ({beats} beats, {words} words of narration); "
                      f"it must run at least {min_minutes:g} min. Add about {max(need, 50)} more words of narration "
                      "by teaching more of the content: a step or idea left out, an example from daily life, a "
                      "hard term explained, a worked problem, a question for the class. Never restate what is "
                      "already said. Keep every existing beat that is right.")
    return errors, warnings


script_photos: dict = {}


def _photo_key(op: dict) -> str:
    named = "|".join(_labels_of(op))
    labelled = f"|labels:{named}" if named else ""
    if op.get("op") == "illustration":
        scene = "|scene" if op.get("scene") else ""
        diagram = "|diagram" if op.get("diagram") else ""
        shape = "".join(f"|{op[k]}" for k in ("aspect", "look") if op.get(k))
        return f"illustration|{op.get('image') or ''}|{op.get('query') or ''}{labelled}{scene}{diagram}{shape}"
    return f"{op.get('image') or ''}|{op.get('query') or ''}|{op.get('subject') or ''}{labelled}"


def _labels_of(op: dict) -> list[str]:
    """The parts a picture labels ("labels": ["crown", "sceptre"]): short names, at most 6."""
    labels = op.get("labels") if isinstance(op.get("labels"), list) else []
    return [str(x).strip()[:32] for x in labels if str(x).strip()][:6]


def _with_labels(row: dict | None, op: dict) -> dict | None:
    """The picture's row with where its labels go (genimage.locate), for a generated picture that names parts."""
    labels = _labels_of(op)
    picture = (row or {}).get("png") or (row or {}).get("file")
    if not row or not labels or not picture or not re.search(r"\.(png|jpe?g|webp)$", str(picture), re.I):
        return row
    import genimage

    found = genimage.locate(picture, labels)
    return {**row, "labels": found} if found else row


# ---------------- pictures in diagrams, timelines and map labels ----------------
# A diagram's node, a timeline's event, a map marker (and a journey's stop) may carry a picture beside its words:
#   {"subject": "Mahatma Gandhi"}     Wikipedia's picture of a person, place or thing (a photo from the web)
#   {"query": "steam locomotive"}     a photo found by these words (from the web)
#   {"illustration": "water cycle"}   an educational illustration (from the web)
#   {"figure": "fig3"}                one of the book's figures (its redrawn picture when it has one)
#   {"draw": "A steam engine, side view"}   an older name for generate (nothing is drawn as an SVG)
#   {"entity": "cow"}                 a drawing from the library
# How a picture on the stage may move once drawn (pocket_lecture PICTURE_MOVES): a boat bobs, a flag or a tree
# sways, a heart or a lung breathes, a ship or a caravan drifts on across the stage.
PICTURE_MOVES = ("bob", "sway", "breathe", "drift")
# A diagram node's `anim`: its picture moves this way while the diagram is up (pocket_lecture NODE_MOVES).
NODE_ANIMS = ("bob", "hop", "sway", "shake", "flicker", "spin", "pulse", "breathe", "drift")
PICTURE_KEYS = ("generate", "subject", "query", "illustration", "figure", "draw", "entity")


def _timeline_events(op: dict) -> list[tuple]:
    """A timeline's events as (date, label, picture or None): from [date, label], [date, label, picture] or
    {date, label, picture}."""
    out = []
    for e in op.get("events") or []:
        if isinstance(e, dict):
            out.append((e.get("date", ""), e.get("label", ""), e.get("picture")))
        elif isinstance(e, (list, tuple)) and len(e) >= 2:
            out.append((e[0], e[1], e[2] if len(e) > 2 else None))
    return out


def pictures_of(op: dict) -> list[tuple[str, dict]]:
    """(where, picture) for each picture an op carries in a node, an event or a label."""
    kind = op.get("op")
    out = []
    if kind == "diagram":
        out = [(f"node {n.get('id')!r}", n["picture"]) for n in op.get("nodes") or []
               if isinstance(n, dict) and n.get("picture") is not None]
    elif kind == "timeline":
        out = [(f"event {d!r}", pic) for d, _, pic in _timeline_events(op) if pic is not None]
    elif kind == "marker" and op.get("picture") is not None:
        out = [("its label", op["picture"])]
    elif kind == "journey":
        out = [(f"stop {k + 1}", pic) for k, pic in enumerate(op.get("pictures") or []) if pic is not None]
    return out


def _picture_problem(spec, figures: dict) -> str | None:
    if not isinstance(spec, dict) or len([k for k in PICTURE_KEYS if spec.get(k)]) != 1:
        return ("a picture is one of {\"generate\": \"<what the image model makes>\"}, "
                "or {\"figure\": \"<book figure id>\"}")
    if spec.get("figure") and str(spec["figure"]) not in figures:
        return f"no book figure {spec['figure']!r} for a picture"
    return None


def _picture_fetch(spec: dict) -> dict | None:
    """The web fetch a picture needs, as the photo op it amounts to (optional: a picture that cannot be found
    leaves its words alone)."""
    if spec.get("subject"):
        return {"op": "photo", "subject": str(spec["subject"]), "optional": True}
    if spec.get("query"):
        return {"op": "photo", "query": str(spec["query"]), "optional": True}
    if spec.get("illustration") or spec.get("generate"):
        return {"op": "illustration", "query": str(spec.get("generate") or spec["illustration"]), "optional": True,
                **SMALL_PICTURE}
    return None


def _chapter_spots(chapter: dict) -> list[str]:
    """The places a map chapter's markers and journeys stop at, as the engine's arguments (names or (lon, lat))."""
    out = []
    for beat in chapter.get("beats") or []:
        for op in beat.get("do") or []:
            if not isinstance(op, dict):
                continue
            where = []
            if op.get("op") == "marker":
                where = [op.get("place") or op.get("lonlat")]
            elif op.get("op") == "journey":
                where = list(op.get("stops") or [])
            for w in where:
                if isinstance(w, str) and w:
                    out.append(_q(w))
                elif isinstance(w, (list, tuple)) and len(w) == 2:
                    out.append(f"({float(w[0]):g}, {float(w[1]):g})")
    return list(dict.fromkeys(out))


# A map chapter is zoomed to the places it shows, with this much room round them (a share of their spread), never
# closer than MIN_SPAN degrees across, and not at all when they spread over most of the map anyway.
ZOOM_ROOM = 0.35
MIN_SPAN = (12.0, 8.0)          # degrees of longitude, latitude
ZOOM_WHEN_UNDER = 0.6           # zoom only when the places take less than this share of the map's width and height


def _chapter_frame(chapter: dict, region: dict | None) -> tuple | None:
    """The lon/lat box a map chapter is fitted to: the places it marks, the journeys and arrows it draws and the
    areas it fills, with room round them, so the class sees them large and close instead of a whole continent
    with a few dots on it. None to show the whole map (nothing is pointed at, or it is spread over most of it)."""
    if not region:
        return None
    try:
        import pocket_lecture as pl

        bounds = pl.map_bounds(region)
        home = None if pl.region_kind(region) == "area" else region.get("country")
    except Exception:  # noqa: BLE001 -- no engine here, or a region it does not know: the whole map
        return None
    if not bounds:
        return None
    lons: list[float] = []
    lats: list[float] = []

    def add(where) -> None:
        try:
            if isinstance(where, str):
                lon, lat = pl.place(where, home, bounds)
            else:
                lon, lat = float(where[0]), float(where[1])
        except Exception:  # noqa: BLE001 -- a place the gazetteer does not know is passed over
            return
        if pl._inside((lon, lat), bounds):
            lons.append(lon)
            lats.append(lat)

    for beat in chapter.get("beats") or []:
        for op in beat.get("do") or []:
            if not isinstance(op, dict):
                continue
            kind = op.get("op")
            if kind == "marker":
                add(op.get("place") or op.get("lonlat"))
            elif kind == "journey":
                for stop in op.get("stops") or []:
                    add(stop)
            elif kind in ("path", "arrow"):
                for point in op.get("points") or []:
                    add(point)
            elif kind == "icon":
                for spot in _icon_spots(op):
                    add(spot)
            elif kind == "empire" and op.get("name") and _year_of(op.get("year")) is not None:
                found = _historical(op["name"], _year_of(op.get("year")))
                if isinstance(found, tuple):
                    x0, y0, x1, y1 = found[0].intersection(pl._box(bounds)).bounds or bounds
                    lons.extend([x0, x1])
                    lats.extend([y0, y1])
            elif kind == "state" and op.get("name"):
                try:
                    shape = pl.state(op["name"], home) if home else pl.country_home(op["name"])
                except Exception:  # noqa: BLE001
                    try:
                        shape = pl.country_home(op["name"])
                    except Exception:  # noqa: BLE001
                        try:
                            shape = pl.area_shape(op["name"], home)
                        except Exception:  # noqa: BLE001
                            continue
                x0, y0, x1, y1 = shape.bounds
                lons.extend([x0, x1])
                lats.extend([y0, y1])
    if not lons:
        return None
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    pad = max(lon1 - lon0, lat1 - lat0) * ZOOM_ROOM
    lon0, lon1, lat0, lat1 = lon0 - pad, lon1 + pad, lat0 - pad, lat1 + pad
    # Never closer than MIN_SPAN: one place is shown with its surroundings, not as a dot on a blank page.
    for k, (lo, hi) in enumerate(((lon0, lon1), (lat0, lat1))):
        short = MIN_SPAN[k] - (hi - lo)
        if short > 0:
            lo, hi = lo - short / 2, hi + short / 2
        if k == 0:
            lon0, lon1 = lo, hi
        else:
            lat0, lat1 = lo, hi
    b0, b1, b2, b3 = bounds
    if (lon1 - lon0) > ZOOM_WHEN_UNDER * (b2 - b0) and (lat1 - lat0) > ZOOM_WHEN_UNDER * (b3 - b1):
        return None
    # On the globe: room padded past a pole or the date line is a map no projection can draw.
    lon0, lon1 = max(lon0, -180.0), min(lon1, 180.0)
    lat0, lat1 = max(lat0, -85.0), min(lat1, 85.0)
    return (round(lon0, 2), round(lat0, 2), round(lon1, 2), round(lat1, 2))


def _picture_value(spec) -> tuple | None:
    """A picture as the engine takes it: ("image", file), ("entity", name), or None (not found or not made: the
    words stand alone)."""
    value = _picture_found(spec)
    return value if value is None or value[0] == "entity" or Path(value[1]).exists() else None


def _picture_found(spec) -> tuple | None:
    if not isinstance(spec, dict):
        return None
    if spec.get("entity"):
        return ("entity", str(spec["entity"]))
    if spec.get("figure"):
        figure = script_figures.get(str(spec["figure"])) or {}
        return ("image", str(figure["file"])) if figure.get("file") else None
    fetch = _picture_fetch(spec)
    row = script_photos.get(_photo_key(fetch)) if fetch else None
    return ("image", str(row["file"])) if row and row.get("file") else None


def _labels_arg(row: dict) -> str:
    """stage_image's labels: [(text, x, y), ...] where the label finder put them, each with its part's box
    (text, x, y, x0, y0, x1, y1) when it gave one."""
    found = [(str(r[0]), *(float(v) for v in r[1:7 if len(r) >= 7 else 3])) for r in row.get("labels") or []
             if isinstance(r, (list, tuple)) and len(r) >= 3]
    return f", labels={found!r}" if found else ""


def _picture_arg(spec) -> str:
    return repr(_picture_value(spec))


def _beside_words(op: dict, spec) -> str:
    """The words a picture sits beside: its diagram node's label, its timeline event's, its map label's."""
    for n in op.get("nodes") or []:
        if isinstance(n, dict) and n.get("picture") is spec:
            return str(n.get("label") or "")
    for e in op.get("events") or []:
        if isinstance(e, dict) and e.get("picture") is spec:
            return f"{e.get('date', '')} {e.get('label', '')}".strip()
        if isinstance(e, list) and len(e) > 2 and e[2] is spec:
            return f"{e[0]} {e[1]}"
    return str(op.get("label") or op.get("place") or "")


def picture_context(context: dict | None, op: dict) -> str:
    """What a picture is for, told to the image model: the lecture and its subject, the chapter, what the teacher
    says while it is up, the words it sits beside and its caption. Short (at most ~700 characters)."""
    context = context or {}
    parts = []
    if context.get("lecture"):
        parts.append(f"a school lesson video, \"{str(context['lecture'])[:120]}\""
                     + (f" ({str(context['subject'])[:40]})" if context.get("subject") else ""))
    if context.get("chapter"):
        parts.append(f"the part about \"{str(context['chapter'])[:100]}\"")
    lines = []
    if context.get("said"):
        lines.append(f"It is on screen while the teacher says: \"{str(context['said'])[:420]}\"")
    if op.get("_beside"):
        lines.append(f"It sits beside the words \"{str(op['_beside'])[:80]}\".")
    if op.get("caption"):
        lines.append(f"Its caption: \"{str(op['caption'])[:120]}\".")
    head = ("It is for " + ", in ".join(parts) + ".") if parts else ""
    return " ".join(x for x in [head, *lines] if x)


def _unfetched_photos(photos: list[tuple[str, dict]], genre: str | None = None, style: str | None = None,
                      contexts: dict[str, dict] | None = None) -> list[str]:
    """Make every picture now (cached), so the scene draws local files; report the ones that failed. Each is made
    knowing what it is for (picture_context): the lesson, the chapter, the lines said over it."""
    if not photos:
        return []
    import images

    out = []
    for at, op in photos:
        key = _photo_key(op)
        if key in script_photos:
            continue
        context = picture_context((contexts or {}).get(at), op)
        if op.get("op") == "illustration":
            row = images.fetch(op.get("image"), illustration=op.get("query"), genre=genre, style=style,
                               parts=_labels_of(op), context=context, scene=bool(op.get("scene")),
                               match=not op.get("_emblem"), kind="diagram" if op.get("diagram") else None,
                               aspect=op.get("aspect"), look=op.get("look")) \
                if images.enabled() else None
            if row:
                script_photos[key] = _with_labels(row, op)
            # else: dropped at compile, and said as a warning (see lint): a missing diagram is no reason to stop
            continue
        row = images.fetch(op.get("image"), op.get("query"), op.get("subject"), parts=_labels_of(op),
                           context=context) if images.enabled() else None
        if row:
            script_photos[key] = _with_labels(row, op)
        elif op.get("optional"):
            continue
        elif not images.enabled():
            out.append(f"{at}: pictures cannot be made here (no image model: OPENROUTER_API_KEY, or PANIM_IMAGES=0); "
                       "build it in Manim instead (a diagram or a manim op)")
        else:
            what = op.get("subject") or op.get("query") or op.get("image")
            out.append(f"{at}: the image model made no picture of {what!r} (refused, or offline); describe it "
                       "another way, or build it in Manim")
    return out


KIT_OPS = {"molecule", "equation", "process", "timeline", "quote"}
# Built on the stage: several pictures at once, diagrams with pictures, a word and its meaning, a comparison,
# a question for the class; and for mathematics and the sciences (stem.py): a drawing made from its description
# and long problems.
STEM_OPS = {"draw", "problem"}
BUILD_OPS = {"gallery", "diagram", "define", "compare", "question"} | STEM_OPS
# The small built drawings there were once (physics presets, sketches, graphs, plots, motions, sims, counters):
# free-form Manim draws all of these now (a manim op). A script that still uses one has it left out, with a note.
RETIRED_OPS = {"incline", "pulley", "piston", "spring", "pendulum", "projectile", "circuit", "lever", "lens",
               "sketch", "graph", "plot", "motion", "trace", "sweep", "sim", "counter"}
# A worked solution: lines added beside the figure on the stage (or on a problem's solution side).
WORK_OPS = {"work"}
# Subjects taught on the board (no side panel) unless the script says otherwise.
BOARD_GENRES = {"physics", "chemistry", "mathematics"}
# The next step of what is already on the stage: more of a diagram, a ring around one of its nodes, the answer
# to the question, one of its choices marked right or wrong while it is explained, the camera closer on a part.
STEP_OPS = {"reveal", "focus", "answer", "option", "zoom"}
QUESTION = "?question"       # the key a chapter's question goes under among its diagrams, for lint
DIAGRAM_KINDS = {"flow", "cycle", "hub", "pyramid"}          # (the older kinds are read as these: DIAGRAM_ALIASES)
# A flowchart's step shapes (pocket_lecture._flow_node) and the edge styles it draws.
FLOW_SHAPES = ("process", "decision", "start", "end", "io", "store", "note")
EDGE_STYLES = ("solid", "dashed", "bold")
# A beat drawn by a block of Manim the model wrote (free_check.py): the only op on its beat.
FREE_OPS = {"manim"}
VISUAL_OPS = {"photo", "figure", "illustration"} | KIT_OPS | BUILD_OPS | FREE_OPS


def beat_order(ops: list[dict]) -> list[dict]:
    """A beat's ops in the order they can be laid out: clearing the stage first, then what goes up on it, then
    what adds to it (working, reveals, a ring, the answer). A model often writes the clear last or the working
    before its figure; played as written, the clear wiped the beat's own working, and the working took the
    whole board before the figure arrived. Otherwise the order stays as written."""
    def rank(op):
        kind = op.get("op") if isinstance(op, dict) else None
        if kind == "unstage":
            return 0
        if kind in WORK_OPS or kind in STEP_OPS:
            return 2
        return 1
    return sorted(ops, key=rank)


def map_drawn_by(op: dict) -> str | None:
    """A map asked of anything but the map (mapguard): a picture described in words, a block of Manim, an illustration or photo
    of a map. Returns why it is refused."""
    import mapguard

    kind = op.get("op")
    if kind == "manim" and mapguard.code_draws_map(op.get("code")):
        return f"this manim block draws a map of its own; {mapguard.MAP_ADVICE}"
    drawn = op if kind == "draw" else op.get("figure") if kind == "problem" and isinstance(op.get("figure"), dict) else None
    if drawn is not None and drawn.get("op") == "draw" and mapguard.is_map(f"{drawn.get('what') or ''} "
                                                                           f"{drawn.get('title') or ''}"):
        return f"the picture {drawn.get('id') or op.get('id')!r} is a map; {mapguard.MAP_ADVICE}"
    asked = [op] if kind in ("illustration", "photo") else _gallery_items(op) if kind == "gallery" else []
    asked += [spec for _, spec in pictures_of(op) if isinstance(spec, dict)]
    for item in asked:
        text = " ".join(str(item.get(k) or "") for k in ("query", "image", "illustration", "draw"))
        if mapguard.is_map(text):
            return f"{text.strip()!r} is a map; {mapguard.MAP_ADVICE}"
    return None


# Which maker draws what (the writer's guide: app/lib/lecture.ts, CHOOSING THE VISUAL). Two mistakes are sent back:
# a structure of living things drawn in Manim (a heart, a nephron, a flower in section: shapes Manim reduces to
# blobs and boxes; the diagram model draws them as a textbook does), and a graph asked of the diagram model (an image
# model draws axes and curves by eye; Manim plots them exactly).
COMPLEX_LIFE = re.compile(
    r"\b(?:heart|kidneys?|nephrons?|neurons?|brain|eyes?ball|human eye|ear|lungs?|alveol\w*|stomach|intestines?|"
    r"liver|pancreas|skeleton|skull|teeth|tooth|skin|digestive system|respiratory system|circulatory system|"
    r"nervous system|excretory system|reproductive system|flower|stamens?|pistil|carpel|anther|ovules?|"
    r"leaf (?:in )?(?:cross[- ])?section|cross[- ]section of (?:a |the )?(?:leaf|stem|root)|root hair|stomata|"
    r"chloroplasts?|mitochondri\w*|organelles?|(?:plant|animal|bacterial) cell|cell structure|villus|villi|"
    r"embryo|foetus|fetus|uterus|placenta|sperm|ovum|bacteri(?:um|a) structure|virus structure)\b", re.I)
GRAPH_ASK = re.compile(
    r"\b(?:graph|plot(?:ted)?|axes|x[- ]axis|y[- ]axis|coordinate plane|number line|bar chart|histogram|"
    r"pie chart|line chart|scatter|curve of|function of x|velocity[- ]time|distance[- ]time|v-t|x-t)\b", re.I)
_PICTURE_CALL = re.compile(r"""picture\(\s*(?:what\s*=\s*)?(['"])(?:(?!\1).)*\1""")


def _labels_unsaid(op: dict, lines: list[str]) -> list[str]:
    """A picture's labels ("labels" on a picture, draw or photo) that none of these lines says: their words in the
    narration, a plural or a possessive taken as the word."""
    if op.get("op") not in ("picture", "illustration", "photo", "draw") or not isinstance(op.get("labels"), list):
        return []
    def forms(word: str) -> set[str]:
        return {word, word[:-1] if word.endswith("s") else word, word[:-2] if word.endswith("es") else word}

    said = set().union(*[forms(w) for w in re.findall(r"\w+", " ".join(lines).lower())] or [set()])
    out = []
    for label in _labels_of(op):
        words = [w for w in re.findall(r"\w+", label.lower()) if len(w) > 2] or re.findall(r"\w+", label.lower())
        if words and not all(forms(w) & said for w in words):
            out.append(label)
    return out


def _maker_problem(op: dict, genre: str | None) -> str | None:
    """A picture given to the maker that draws it worst: in a biology lecture, a complex structure of a living thing
    in Manim (the diagram model draws those); in any lecture, a graph asked of the diagram model (Manim plots it)."""
    kind = op.get("op")
    if kind == "manim" and genre == "biology":
        # What the block or its plan says it draws; a picture it places (picture("...")) is the illustrator's.
        text = _PICTURE_CALL.sub("", f"{op.get('plan') or ''} {op.get('code') or ''}")
        found = COMPLEX_LIFE.search(text)
        if found and not GRAPH_ASK.search(text):
            return (f"the manim figure {op.get('id')!r} draws {found.group(0)!r}: a structure of a living thing is drawn "
                    "by the diagram model, labelled as in a textbook: {\"op\":\"picture\",\"draw\":\"<it, in words>\","
                    "\"labels\":[...]} -- keep manim for graphs, simple shapes that move (particles diffusing, a "
                    "membrane, a cell dividing as circles) and working")
    asked = []
    if kind == "picture" and op.get("draw"):
        asked.append(str(op["draw"]))
    if kind == "illustration" and op.get("diagram"):              # a draw, as canonical_ops leaves it
        asked.append(str(op.get("query") or ""))
    if kind == "draw":
        asked.append(f"{op.get('what') or ''} {op.get('title') or ''}")
    if kind == "problem" and isinstance(op.get("figure"), dict) and op["figure"].get("op") == "draw":
        asked.append(str(op["figure"].get("what") or ""))
    asked += [str(spec.get("draw") or "") for _, spec in pictures_of(op) if isinstance(spec, dict) and spec.get("draw")]
    for text in asked:
        found = GRAPH_ASK.search(text)
        if found:
            return (f"{text.strip()[:80]!r} asks the diagram model for a {found.group(0)!r}: graphs, plots and number "
                    "lines are drawn exactly in manim ({\"op\":\"manim\"}), the diagram model only draws structures")
    return None


GALLERY_MOST = 6
# The shape and look of a small picture (a diagram's step, a timeline's event, a map's label, an icon, the emblem): a
# square child's drawing the board draws on, outline first.
SMALL_PICTURE = {"aspect": "1:1", "look": "child"}
# What else, on a line, shares the screen with a picture.
STAGE_PICTURES = {"illustration", "photo", "figure", "gallery", "diagram", "define", "compare", "question", "draw",
                  "problem", "work", "manim", "molecule", "equation", "timeline", "process", "quote"}
GALLERY_LAYOUTS = ("spotlight", "grid")


def _gallery_items(op: dict) -> list[dict]:
    """A gallery's items as fetchable operations: {op: photo, subject|image|query} or {op: illustration, query}
    or {op: figure, id}; each keeps its caption."""
    out = []
    for item in list(op.get("items") or [])[:GALLERY_MOST]:
        if not isinstance(item, dict):
            continue
        caption = item.get("caption") or item.get("subject") or ""
        say = str(item.get("say") or "")
        if item.get("draw") and not item.get("generate"):
            item = {**item, "generate": item["draw"]}           # a drawing in a gallery: made as a picture
        if item.get("figure"):
            out.append({"op": "figure", "id": str(item["figure"]), "caption": caption, "say": say})
        elif item.get("generate") or item.get("illustration"):
            # Several to a screen: each made in a smaller, squarer shape than a picture alone.
            out.append({"op": "illustration", "query": item.get("generate") or item["illustration"], "caption": caption,
                        "say": say, "aspect": "4:3", "scene": True})
        elif item.get("subject") or item.get("image") or item.get("query"):
            out.append({"op": "photo", **{k: item[k] for k in ("subject", "image", "query") if item.get(k)},
                        "caption": caption, "say": say})
    return out


def _gallery_fetches(op: dict) -> list[dict]:
    """A gallery's pictures to download; one that cannot be found is left out of the gallery, not an error."""
    return [{**item, "optional": True} for item in _gallery_items(op) if item["op"] != "figure"]


def _build_problem(op: dict, diagrams: dict, figures: dict) -> str | None:
    """What stops a gallery, diagram, definition, comparison, reveal or focus, if anything."""
    kind = op["op"]
    if kind == "gallery":
        items = _gallery_items(op)
        if not items:
            return ("a picture's items are 2-4 of {generate (what the image model makes) or figure (a book figure "
                    "id), caption}")
        missing = [i["id"] for i in items if i["op"] == "figure" and i["id"] not in figures]
        if missing:
            return f"gallery: no figure {missing[0]!r}"
    if kind == "diagram":
        key = str(op.get("id") or "")
        nodes = op.get("nodes") or []
        if not key:
            return "'diagram' needs an id (reveal and focus refer to it)"
        if op.get("kind", "flow") not in DIAGRAM_KINDS:
            return f"diagram kind must be one of {', '.join(sorted(DIAGRAM_KINDS))}"
        _edges_as_lists(op)
        # A flow that is a hierarchy goes as deep and wide as a classification needs; a flowchart up to 16.
        import hierarchy

        flow = op.get("kind", "flow") == "flow"
        ids = [str(n.get("id")) for n in nodes if isinstance(n, dict)]
        most = (20 if hierarchy.is_tree(ids, op.get("edges") or []) else 16) if flow else 9
        if not 2 <= len(nodes) <= most or not all(isinstance(n, dict) and n.get("id") and n.get("label") for n in nodes):
            return (f"'diagram' needs 2-{most} nodes, each {{id, label, entity?, items?"
                    + (", shape?, lane?" if flow else "") + "}")
        bad_shape = [n["id"] for n in nodes if n.get("shape") and str(n["shape"]) not in FLOW_SHAPES]
        if bad_shape:
            return f"diagram node {bad_shape[0]!r}: shape is one of {', '.join(FLOW_SHAPES)}"
        bad_items = [n["id"] for n in nodes if n.get("items") is not None
                     and (not isinstance(n["items"], list) or len(n["items"]) > 5)]
        if bad_items:
            return f"diagram node {bad_items[0]!r}: items must be a list of at most 5 short lines"
        ids = [str(n["id"]) for n in nodes]
        if len(set(ids)) != len(ids):
            return "diagram node ids must be different"
        bad = [e for e in op.get("edges") or [] if not isinstance(e, list) or len(e) < 2
               or str(e[0]) not in ids or str(e[1]) not in ids]
        if bad:
            return f"diagram edge {bad[0]!r} must join two node ids: [from, to, label?, style?]"
        styled = [e for e in op.get("edges") or [] if len(e) > 3 and e[3] and str(e[3]) not in EDGE_STYLES]
        if styled:
            return f"diagram edge {styled[0]!r}: style is one of {', '.join(EDGE_STYLES)}"
        unknown = [str(x) for x in op.get("show") or [] if str(x) not in ids]
        if unknown:
            return f"diagram show: no node {unknown[0]!r}"
        motions = set(NODE_ANIMS) | {"none", "auto"}
        wrong = [n for n in nodes if n.get("anim") is not None and str(n["anim"]) not in motions]
        if wrong:
            return (f"diagram node {wrong[0]['id']!r}: anim is one of {', '.join(sorted(motions))} "
                    "(leave it out and its picture holds still)")
        diagrams[key] = ids
    if kind in STEM_OPS | WORK_OPS:
        return _stem_problem(op, diagrams)
    if kind == "question":
        choices = op.get("choices") or []
        if not str(op.get("text") or "").strip():
            return "'question' needs text: the question, in the lecture's language"
        if not isinstance(choices, list) or len(choices) == 1 or len(choices) > 5:
            return "question choices must be 2-5 short answers, or left out for an open question"
        if choices and op.get("answer") is not None and _answer_index(op) is None:
            return (f"question answer {op['answer']!r} is not one of its choices; give the right choice's "
                    "letter (\"B\") or its text")
        diagrams[QUESTION] = [str(c) for c in choices]
    if kind == "answer":
        if QUESTION not in diagrams:
            return "'answer' needs a question asked earlier in this chapter (with its answer)"
        return None
    if kind == "option":
        if not diagrams.get(QUESTION):
            return "'option' needs a question with choices asked earlier in this chapter"
        if _choice_index(diagrams[QUESTION], op.get("choice")) is None:
            return (f"option choice {op.get('choice')!r} is not one of the question's choices; give its letter "
                    "(\"A\") or its text")
        return None
    if kind in STEP_OPS:
        key = str(op.get("diagram") or "")
        if key not in diagrams:
            return f"'{kind}' needs diagram: the id of a diagram drawn earlier in this chapter"
        if kind == "zoom":
            node = op.get("node")
            if node is not None and str(node) not in diagrams[key]:
                return f"zoom node: no part {node!r} in {key!r} ({', '.join(diagrams[key]) or 'none named'})"
            if op.get("scale") is not None and not 1.1 <= float(op["scale"]) <= 3:
                return "zoom scale is between 1.1 and 3 (how much closer)"
            return None
        wanted = [str(x) for x in (op.get("nodes") or [])] if kind == "reveal" else [str(op.get("node") or "")]
        if not wanted or any(w not in diagrams[key] for w in wanted):
            return f"{kind}: nodes must be ids of diagram {key!r} ({', '.join(diagrams[key])})"
    if kind == "define" and not (op.get("term") and op.get("meaning")):
        return "'define' needs term and meaning (in plain words)"
    if kind == "compare":
        columns = op.get("columns") or []
        if not 2 <= len(columns) <= 3 or not all(isinstance(c, dict) and c.get("title") for c in columns):
            return "'compare' needs 2-3 columns, each {title, entity?, points: [up to 4 short lines]}"
    return None


PART_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,23}")


def _draw_problem(op: dict) -> str | None:
    """A problem's figure described in words (made by the diagram model, compile_lecture._drawn_picture): what it
    shows, and the parts it names (labelled on it)."""
    what = str(op.get("what") or "").strip()
    if len(what) < 12:
        return ("'draw' needs what: the picture in words, every part, label, arrow and number on it "
                "(\"a block on a 30° smooth incline; its weight mg straight down; the normal force N ...\")")
    parts = op.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= 14:
        return "'draw' needs parts: 1-14 ids, one for each thing the lecture will point at ([\"wedge\", \"block\", \"mg\"])"
    bad = [p for p in parts if not isinstance(p, str) or not PART_ID.fullmatch(p)]
    if bad:
        return f"draw part {bad[0]!r}: a part id is a short name of letters, digits and _ (\"mg\", \"r1\", \"cell_wall\")"
    if len(set(parts)) != len(parts):
        return "draw parts must be different"
    unknown = [str(x) for x in op.get("show") or [] if str(x) not in parts]
    if unknown:
        return f"draw {op.get('id')!r} show: no part {unknown[0]!r} (its parts: {', '.join(parts)})"
    if op.get("moves") is not None and not str(op["moves"]).strip():
        return "draw moves: what moves and how, in words, or leave it out for a still picture"
    return None


def _stem_problem(op: dict, diagrams: dict) -> str | None:
    """What stops a drawing, worked solution or problem; records the parts reveal can show."""
    kind = op["op"]
    if kind == "work":
        if not op.get("id"):
            return "'work' needs an id (later lines of the same solution use it)"
        lines = op.get("lines")
        if not isinstance(lines, list) or not lines or not all(isinstance(x, str) and x.strip() for x in lines):
            return "'work' needs lines: [\"F = ma\", \"a = F/m\"] (TeX for maths; a line with words is shown as text)"
        return None
    key = str(op.get("id") or "")
    if not key:
        return f"'{kind}' needs an id (reveal and focus refer to it)"
    if kind == "draw":
        problem = _draw_problem(op)
        if problem:
            return problem
        diagrams[key] = [str(p) for p in op["parts"]]
        diagrams[f"?kind:{key}"] = "draw"
        return None
    if not str(op.get("text") or "").strip():
        return "'problem' needs text: the question, in full"
    figure = op.get("figure")
    if figure is not None:
        if not isinstance(figure, dict) or figure.get("op") != "draw":
            return ("a problem's figure is a draw op ({\"op\":\"draw\",\"what\":...,\"parts\":[...]}), or leave it "
                    "out and draw the figure with a manim op on the beats before")
        inner = _stem_problem({**figure, "id": figure.get("id") or f"{key}_figure"}, diagrams)
        if inner:
            return f"problem figure: {inner}"
    diagrams[key] = []
    return None


def _choice_index(choices: list, choice) -> int | None:
    """Which of `choices` a choice names: a letter (A-E, "(b)"), a 1-based number or the choice's own text."""
    choices = [str(c).strip() for c in choices]
    if choice is None or not choices:
        return None
    if isinstance(choice, int) and not isinstance(choice, bool):
        return choice - 1 if 1 <= choice <= len(choices) else None
    text = str(choice).strip()
    letter = re.fullmatch(r"\(?([A-Ea-e])[).]?", text)
    if letter and "ABCDE".index(letter.group(1).upper()) < len(choices):
        return "ABCDE".index(letter.group(1).upper())
    number = re.fullmatch(r"\(?([1-5])[).]?", text)
    if number and int(number.group(1)) <= len(choices):
        return int(number.group(1)) - 1
    lowered = [c.lower() for c in choices]
    return lowered.index(text.lower()) if text.lower() in lowered else None


def _answer_index(op: dict) -> int | None:
    """The right choice of a question with choices: its answer as a letter (A-E), a 1-based number or the
    choice's own text. None when it names no choice."""
    return _choice_index(op.get("choices") or [], op.get("answer"))


def _kit_problem(op: dict) -> str | None:
    """What stops a subject-kit drawing, if anything."""
    kind = op["op"]
    if kind == "molecule":
        if not op.get("name"):
            return "'molecule' needs name (a name, a formula such as H2O, or SMILES)"
        try:
            import molecules

            if molecules.resolve(str(op["name"])) is None:
                return (f"no molecule {op['name']!r}: use a common name, a formula (H2O, C6H12O6) or a SMILES "
                        "string")
        except ImportError:
            return "molecules need RDKit: .venv/bin/pip install rdkit"
    if kind == "equation" and not str(op.get("tex") or "").strip():
        return "'equation' needs tex (E = mc^2)"
    if kind == "process" and not 2 <= len(op.get("steps") or []) <= 8:
        return "'process' needs 2 to 8 steps"
    if kind == "timeline" and len(op.get("events") or []) < 2:
        return "'timeline' needs at least two [date, label] events"
    if kind == "quote" and not op.get("text"):
        return "'quote' needs text"
    return None


# ---------------- explaining, not reading out the book ----------------
COPY_RUN = 8            # this many words in a row, word for word from the source, is reading the book aloud
LONG_SENTENCE = 26      # words; a spoken sentence longer than this loses a listener
TEXT_OPS = {"process", "quote"}
PICTURE_OPS = {"photo", "figure", "illustration", "molecule", "equation", "bars", "gallery", "diagram",
               "define", "compare", "reveal", "focus", "work"} | STEM_OPS
NOT_A_FIGURE = re.compile(r"\b(QR|bar ?code|logo|watermark)\b|क्यूआर", re.I)


def book_figure_count(script: dict) -> int:
    return sum(1 for f in (script.get("figures") or {}).values()
               if not NOT_A_FIGURE.search(str((f or {}).get("caption", ""))))


def _word_list(text: str) -> list[str]:
    """Lower-case words in any script (Devanagari's vowel signs are marks, so \\w alone would split them)."""
    return re.findall(r"[\w\u0900-\u097F]+", str(text).lower())


def _copied(say: str, grams: set) -> str | None:
    """The first run of COPY_RUN words the line shares with the source, or None."""
    words = _word_list(say)
    for i in range(len(words) - COPY_RUN + 1):
        if tuple(words[i:i + COPY_RUN]) in grams:
            return " ".join(words[i:i + COPY_RUN])
    return None


DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# Hindi written in Latin letters: the voice reads Latin letters as English, so "matlab" comes out wrong.
ROMAN_HINDI = re.compile(r"\b(hai|hain|hota|hoti|hote|matlab|yaani|yani|kya|kyun|kyunki|nahi|nahin|aur|toh|lekin|"
                         r"agar|jab|tab|isliye|dekho|samjho|chalo|hum|aap|yeh|woh|kaise|kitna|jaise|wala|wali|mein|"
                         r"ko|ka|ki|ke|se|par|bhi|sirf|bahut|accha|achha|thoda)\b", re.I)
# Keys whose values are never shown or spoken: names, ids, drawing words, expressions.
NOT_SHOWN = {"op", "id", "type", "kind", "diagram", "node", "nodes", "show", "entity", "subject", "query", "expr",
             "color", "fill", "figure", "image", "name", "place", "about", "where", "tone", "side", "dashed", "style",
             "region", "view", "country", "state", "say", "narration", "intro", "source_text", "figures", "genre",
             "language", "credits", "from_figure", "from_book", "choice", "book_questions", "_index", "_movable", "movable", "parts", "by",
             "about", "heavier", "distance", "back", "anim", "what", "moves", "svg", "_draw_error", "art", "shape",
             "layout"}


def _shown_strings(value, key: str = "") -> list[str]:
    """The words an op or a script puts on the screen."""
    if key in NOT_SHOWN:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in _shown_strings(v, str(k))]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _shown_strings(v, key)]
    return []


def _language_mix(script: dict) -> tuple[list[str], list[str]]:
    """A Hinglish lecture (script "language": "hinglish"): spoken in Hindi with English terms, Hindi in Devanagari
    and English in Latin letters (each run is voiced in its own language), and every word on screen in English."""
    language = str(script.get("language") or "").lower()
    if language != "hinglish":
        return [], []
    errors: list[str] = []
    beats = [(f"chapter {ci + 1} beat {bi + 1}", b) for ci, c in enumerate(script.get("chapters") or [])
             for bi, b in enumerate(c.get("beats") or [])]
    spoken = [(at, str(b.get("say", ""))) for at, b in beats]
    english_only = [at for at, say in spoken if say and not DEVANAGARI.search(say)]
    roman = [f"{at} (\"{m.group(0)}\")" for at, say in spoken for m in [ROMAN_HINDI.search(say)]
             if m and len(ROMAN_HINDI.findall(say)) >= 2]
    hindi_only = [at for at, say in spoken if say and not re.search(r"[A-Za-z]{3,}", say)]
    if spoken and len(english_only) > len(spoken) // 5:
        errors.append(f"{len(english_only)} of {len(spoken)} beats are spoken in English only (e.g. "
                      f"{', '.join(english_only[:3])}). This is a Hinglish lecture: say each line in simple Hindi in "
                      "Devanagari, keeping the subject's terms in English: \"Force मतलब एक push या pull है।\"")
    if roman:
        errors.append(f"Hindi written in Latin letters in {len(roman)} beat(s), e.g. {'; '.join(roman[:3])}: the voice "
                      "reads Latin letters as English. Write the Hindi words in Devanagari (है, मतलब, यानी, और) and "
                      "only the English words in Latin letters.")
    warnings: list[str] = []
    if spoken and len(hindi_only) > len(spoken) // 3:
        # A teacher may write an English term in Devanagari (फोर्स, टेंशन) and the Hindi voice says it well:
        # advice, not an error.
        warnings.append(f"{len(hindi_only)} of {len(spoken)} beats have no English words (e.g. "
                      f"{', '.join(hindi_only[:3])}). Hinglish keeps the subject's terms in English (force, "
                      "acceleration, friction), as a teacher in class says them; do not translate them into pure Hindi.")
    shown = []
    for at, beat in beats:
        for op in beat.get("do") or []:
            for text in _shown_strings(op):
                if DEVANAGARI.search(text):
                    shown.append(f"{at} {op.get('op')} (\"{text[:40]}\")")
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        for key in ("title", "sub"):
            if DEVANAGARI.search(str(chapter.get(key) or "")):
                shown.append(f"chapter {ci} {key}")
    for key in ("title", "sub"):
        if DEVANAGARI.search(str(script.get(key) or "")):
            shown.append(f"the lecture's {key}")
    if DEVANAGARI.search(json.dumps(script.get("recap") or [], ensure_ascii=False)):
        shown.append("the recap")
    if shown:
        errors.append(f"Hindi on the screen in {len(shown)} place(s), e.g. {'; '.join(shown[:4])}. In a Hinglish "
                      "lecture only the narration is Hinglish: titles, headings, key points, definitions, labels, "
                      "questions, problems, working and the recap are in English.")
    return errors, warnings


def _plain_language(script: dict) -> tuple[list[str], list[str]]:
    """Lines read out of the source book, and sentences too long to follow by ear.

    A lecture explains: it says a textbook sentence in everyday words, with an
    example. A few quoted phrases are fine; a script that is mostly the book's
    own sentences is an error.
    """
    errors, warnings = [], []
    source = _word_list(script.get("source_text") or "")
    grams = {tuple(source[i:i + COPY_RUN]) for i in range(len(source) - COPY_RUN + 1)}
    # The book's own questions are read out as they are written, then explained: not copying.
    for q in script.get("book_questions") or []:
        words = _word_list(" ".join([str(q.get("text") or "")] + [str(c) for c in q.get("choices") or []]))
        grams -= {tuple(words[i:i + COPY_RUN]) for i in range(len(words) - COPY_RUN + 1)}
    beats = [(f"chapter {ci + 1} beat {bi + 1}", b) for ci, c in enumerate(script.get("chapters") or [])
             for bi, b in enumerate(c.get("beats") or [])]
    copied = []
    for at, beat in beats:
        say = str(beat.get("say", ""))
        run = _copied(say, grams) if grams else None
        if run:
            copied.append(f"{at} (\"{run}\")")
        for sentence in re.split(r"[.!?।]+", say):
            if len(sentence.split()) > LONG_SENTENCE:
                warnings.append(f"{at}: a {len(sentence.split())}-word sentence is hard to follow by ear; "
                                "split it into two short ones")
                break
    if copied and len(copied) > max(2, len(beats) // 5):
        errors.append(f"{len(copied)} of {len(beats)} beats read the book word for word, e.g. {'; '.join(copied[:4])}. "
                      "Explain instead: say each idea in simple everyday words, as a teacher would to a 12-year-old, "
                      "with short sentences, a plain meaning for every hard term, and an example from daily life.")
    else:
        warnings += [f"{c}: word for word from the book; say it in simpler words" for c in copied]
    return errors, warnings


def _text_heavy(script: dict) -> tuple[list[str], list[str]]:
    """A lecture whose stage is mostly boxes of words (process, quote) instead of pictures."""
    beats = [b for c in script.get("chapters") or [] for b in c.get("beats") or []]
    if len(beats) < 6:
        return [], []
    wordy = [b for b in beats if {op.get("op") for op in b.get("do") or []} & TEXT_OPS
             and not {op.get("op") for op in b.get("do") or []} & PICTURE_OPS]
    figures = script.get("figures") or {}
    warnings = [f"figure {op.get('id')} is a QR code or logo, not a diagram; drop it"
                for b in beats for op in b.get("do") or []
                if op.get("op") == "figure" and NOT_A_FIGURE.search(str((figures.get(str(op.get("id"))) or {}).get("caption", "")))]
    fresh = [b for b in beats if {op.get("op") for op in b.get("do") or []} & (VISUAL_OPS - {"process", "quote", "question", "problem"})]
    if len(beats) >= 8 and len(fresh) > len(beats) * 0.6:
        warnings.append(f"{len(fresh)} of {len(beats)} beats put up a new picture: that is a picture a sentence. "
                        "Plan the stage a paragraph (3-5 beats) at a time: one diagram revealed across the "
                        "paragraph (reveal, focus), one gallery, one map sequence; beats in between leave it up.")
    if len(wordy) > max(3, len(beats) * 0.3):
        return [f"{len(wordy)} of {len(beats)} beats show only boxes of words (process or quote) on the stage. "
                "Show pictures instead: an educational illustration or diagram (find_illustration, described in English "
                "even in a Hindi lecture), a photo (find_image) or a document figure. Keep process for at most "
                "two real sequences per chapter."], warnings
    return [], warnings


# Words a line gives an example or a comparison with, in English and Hindi.
EXAMPLE_WORDS = re.compile(r"\b(for example|for instance|example|e\.g\.|imagine|such as|think of|just like|like when|suppose|"
                           r"say you|picture this)\b|जैसे|उदाहरण|मान लो|मान लीजिए|मान लें|कल्पना|सोचो|सोचिए", re.I)


def teaching_plan(minutes: float, source_words: int = 0) -> dict:
    """How deep a lecture of this length goes.

    The content decides the topics (about one every 350 words of a source; a bare topic is split by the time
    there is). The minutes a topic gets decide how many examples each statement has and how many questions
    the class is asked.
    """
    if source_words > 400:
        topics = min(15, max(2, round(source_words / 350)))
    else:
        topics = min(12, max(2, round(minutes / 3)))
    per_topic = minutes / topics
    # One example makes an idea clear; a second only where there is time for a hard one. More was repetition.
    examples = 1 if per_topic < 4 else 2
    problems = 1 if per_topic < 2 else 2 if per_topic < 4 else 3
    questions = 0.5 if per_topic < 2 else 1 if per_topic < 4 else 2 if per_topic < 7 else 3
    return {"minutes": minutes, "topics": topics, "examples": examples, "questions_per_topic": questions,
            # A short video of a long chapter cannot ask a question every topic: at most one every 2 minutes,
            # and an example beat every 50 seconds or so.
            "min_questions": min(max(1, round(topics * questions)), max(1, int(minutes // 2))),
            "min_examples": min(max(2, round(topics * 2 * examples * 0.5)), max(2, round(minutes * 1.2))),
            "problems_per_topic": problems,
            # A problem solved from the very basics takes about 4 minutes, its theory about as long.
            "min_problems": min(topics * problems, max(1, int(minutes // 7)))}


PANEL_FACTS = 3          # key points a side panel (a map chapter's) holds under its title
PANEL_FACT_CHARS = 70


def _panel_text(script: dict) -> tuple[list[str], list[str]]:
    """Too much text beside the map: more than PANEL_FACTS points under one panel title, or long ones. (On the
    board a fact is one line in the strip, replaced by the next.)"""
    errors = []
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        # A side panel is only beside the map, on the beats of a run of them that puts facts in it.
        paneled = {bi for first, last in _map_runs(chapter, bool(script.get("region")))
                   if _fills_panel(_run_of(chapter, first, last)) for bi in range(first + 1, last + 1)}
        count = 0
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            if bi not in paneled:
                continue
            for op in beat.get("do") or []:
                if op.get("op") in ("panel", "clear"):
                    count = 0
                if op.get("op") in ("fact", "stat"):
                    count += 1
                    text = str(op.get("text") or op.get("label") or "")
                    if count == PANEL_FACTS + 1:
                        errors.append(f"chapter {ci} beat {bi}: more than {PANEL_FACTS} points in one panel; the "
                                      "narration says the rest (or start a new panel for a new topic)")
                    if len(text) > PANEL_FACT_CHARS:
                        errors.append(f"chapter {ci} beat {bi}: a panel point of {len(text)} characters; keep it "
                                      f"under {PANEL_FACT_CHARS}, a few words the narration expands on")
    return errors, []


# The fewest lines of working a problem's solution shows: a problem solved in two
# or three lines skipped the steps a beginner needs.
MIN_WORK_LINES = 6
# The fewest times a problem's figure is pointed at (reveal or focus) while it is read and solved:
# its diagram explained, not only shown.
MIN_FIGURE_STEPS = 3



def _problem_depth(script: dict) -> tuple[list[str], list[str]]:
    """Each long problem solved from the very basics: at least MIN_WORK_LINES lines of working between it and the
    next problem (its own solution, the work ops with its id or after it in its chapter), and a problem with a
    figure walked through on it: MIN_FIGURE_STEPS reveals or focuses on the figure's parts."""
    errors: list[str] = []
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        current, lines, at, figure, pointed = None, 0, "", None, 0

        def close():
            if current is not None and figure and pointed < MIN_FIGURE_STEPS:
                errors.append(
                    f"{at}: problem {current.get('id')!r} has a figure, pointed at {pointed} time(s) while it is solved. "
                    "Explain the diagram: before solving, go through its parts (what each label, arrow and angle "
                    f"stands for) and come back to it in the steps that use it, at least {MIN_FIGURE_STEPS} times in "
                    f"all, with {{\"op\":\"focus\",\"diagram\":\"{figure}\",\"node\":...}} or "
                    f"{{\"op\":\"reveal\",\"diagram\":\"{figure}\",\"nodes\":[...]}} on the beat that names the part.")
            if current is not None and lines < MIN_WORK_LINES:
                errors.append(
                    f"{at}: problem {current.get('id')!r} is solved in {lines} line(s) of working. Solve it from the very "
                    f"basics, at least {MIN_WORK_LINES} lines, one small step each, one or two a beat as they are said: "
                    "the given values and their unit conversions, the law and its formula, each operation on its own "
                    "line (\"divide both sides by m\"), the numbers put in one at a time, the arithmetic, the units, "
                    "and the boxed answer.")

        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            for op in beat.get("do") or []:
                if op.get("op") == "problem":
                    close()
                    current, lines, at, pointed = op, 0, f"chapter {ci} beat {bi}", 0
                    shown = op.get("figure")
                    figure = (shown.get("id") or f"{op.get('id')}_figure") if isinstance(shown, dict) else None
                elif op.get("op") == "work" and current is not None:
                    lines += len(op.get("lines") or [])
                elif op.get("op") in ("reveal", "focus") and figure and str(op.get("diagram")) == figure:
                    pointed += 1
        close()
    return errors, []


def _book_questions(script: dict, whole: bool = True) -> tuple[list[str], list[str]]:
    """The questions of an uploaded book, each asked and explained: on the stage with its choices
    ({"op":"question","from_book":"3",...}), then every choice marked and explained ({"op":"option"}), then the
    answer. `whole`: the script is the whole lecture, so a book question it never asks is an error too."""
    errors: list[str] = []
    asked: dict[str, dict] = {}
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        current, explained, at = None, set(), ""

        def close():
            if current is None or not current.get("from_book"):
                return
            choices = current.get("choices") or []
            left = [("ABCDE"[i]) for i in range(len(choices)) if i not in explained]
            if left:
                errors.append(f"{at}: book question {current['from_book']} explains option(s) {', '.join(left)} "
                              "nowhere. After the question, give every choice a beat of its own: "
                              '{"op":"option","choice":"A"} while the narration says what it means and why it is '
                              "right or wrong; then the answer.")

        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            for op in beat.get("do") or []:
                if op.get("op") == "question":
                    close()
                    current, explained, at = op, set(), f"chapter {ci} beat {bi}"
                    if op.get("from_book") is not None:
                        asked[str(op["from_book"]).strip()] = op
                elif op.get("op") == "option" and current is not None:
                    index = _choice_index(current.get("choices") or [], op.get("choice"))
                    if index is not None:
                        explained.add(index)
        close()
    for q in script.get("book_questions") or []:
        n = str(q.get("n")).strip()
        op = asked.get(n)
        want = [str(c) for c in q.get("choices") or []]
        if op is None:
            if whole:
                errors.append(f"the book's question {n} (\"{str(q.get('text') or '')[:80]}\") is never asked. Every "
                              "question of the book is put on the stage, "
                              f'{{"op":"question","from_book":"{n}","text":...,"choices":[...]}}, and explained in full.')
        elif len(want) >= 2 and len(op.get("choices") or []) != len(want):
            errors.append(f"book question {n} has {len(want)} choices; show all of them on its card, in the book's order")
    return errors, []


def _teaching(script: dict, min_questions: int | None = None, min_examples: int | None = None,
              min_problems: int | None = None) -> tuple[list[str], list[str]]:
    """A lecture that teaches rather than recites: questions for the class between topics, examples; as many
    as the chosen length's teaching plan asks for, when there is one."""
    errors, warnings = [], []
    chapters = script.get("chapters") or []
    beats = [b for c in chapters for b in c.get("beats") or []]
    if len(beats) < 12:
        return errors, warnings
    # A long worked problem is a question for the class too.
    asked = [op for b in beats for op in b.get("do") or [] if op.get("op") in ("question", "problem")]
    problems = [op for op in asked if op.get("op") == "problem"]
    if min_problems and len(problems) < min_problems:
        errors.append(f"the lecture works {len(problems)} long problem(s); at this length it should work at least "
                      f"{min_problems}: after each concept's theory, 2-3 problems ({{\"op\":\"problem\",...}} with its "
                      "figure), each solved in detail over several beats ({\"op\":\"work\",...}, one step a beat, the "
                      "answer boxed).")
    if asked and min_questions and len(asked) < min_questions:
        errors.append(f"the lecture asks the class {len(asked)} question(s); at this length it should ask at least "
                      f"{min_questions}. Add questions after the topics that have none, each answered and explained "
                      "on the next beat.")
    if not asked:
        errors.append("the lecture asks the class no questions. Between topics, put a question on the stage "
                      '({"op":"question","text":"...","choices":["...","..."],"answer":"B"}), leave time to think, '
                      'then answer it on the next beat ({"op":"answer"}) and explain why: at least one per chapter.')
    for ci, chapter in enumerate(chapters, 1):
        ops = [op for b in chapter.get("beats") or [] for op in b.get("do") or []]
        if asked and len(chapter.get("beats") or []) >= 6 and not any(op.get("op") in ("question", "problem")
                                                                     for op in ops):
            warnings.append(f"chapter {ci}: no question for the class; ask one after its main idea")
        if any(op.get("op") == "question" and op.get("answer") is not None for op in ops) and \
                not any(op.get("op") == "answer" for op in ops):
            warnings.append(f"chapter {ci}: a question's answer is never shown; add {{\"op\":\"answer\"}} to the "
                            "beat after it that explains the answer")
    lang_text = " ".join(str(b.get("say", "")) for b in beats)
    letters = [c for c in lang_text if c.isalpha()]
    known = letters and sum(c.isascii() or "ऀ" <= c <= "ॿ" for c in letters) / len(letters) > 0.8
    examples = sum(bool(EXAMPLE_WORDS.search(str(b.get("say", "")))) for b in beats)
    wanted = max(2, len(beats) // 15, min_examples or 0)
    if known and examples < wanted:
        errors.append(f"only {examples} of {len(beats)} beats give an example; at this length there should be at "
                      f"least {wanted}. Teach every idea with examples from a student's daily life (\"for example...\", "
                      "\"imagine...\", \"जैसे...\"), each in a beat of its own, for each important statement.")
    return errors, warnings


# ---------------- no icons: illustrations, diagrams, markers and words instead ----------------
def _icon_words(name: str) -> str:
    """'game-icons:sugar-cane' -> 'sugar cane'."""
    return re.sub(r"[-_]+", " ", str(name).split(":", 1)[-1]).strip()


def no_icons(script: dict) -> dict:
    """Rewrite icon operations into what a lecture shows instead of icons (in place; safe to repeat).

    An icon illustration becomes an educational illustration or diagram of the same thing (Commons, Openverse);
    an icon at a place becomes a labelled marker; an icon in the panel becomes a fact line.
    """
    for chapter in script.get("chapters") or []:
        for beat in chapter.get("beats") or []:
            out = []
            for op in beat.get("do") or []:
                kind = op.get("op")
                if kind == "illustration" and op.get("icon") and not (op.get("query") or op.get("image")):
                    out.append({"op": "illustration", "query": _icon_words(op["icon"]),
                                "caption": op.get("title") or op.get("caption") or ""})
                elif kind == "icon":
                    label = op.get("label") or _icon_words(op.get("name", "")).capitalize()
                    spots = _icon_spots(op)
                    for spot in spots:
                        where = {"place": spot} if isinstance(spot, str) else {"lonlat": list(spot)}
                        out.append({"op": "marker", **where, "label": label if spot == spots[0] else ""})
                    if not spots and label:
                        out.append({"op": "fact", "text": label})
                else:
                    out.append(op)
            beat["do"] = out
    return script


def _fills_panel(chapter: dict, figures: dict | None = None) -> bool:
    """Whether a map chapter puts anything in the side panel beyond its title (a fact, a stat, a bar chart, an icon
    or a figure in the panel). Without, it is drawn wide: the map across the whole frame, no empty panel."""
    for beat in chapter.get("beats") or []:
        for op in beat.get("do") or []:
            if not isinstance(op, dict):
                continue
            kind = op.get("op")
            if kind in ("fact", "stat", "bars"):
                return True
            if kind == "icon" and not _icon_spots(op):
                return True
            if kind == "photo" and op.get("where") == "panel":
                return True
            if kind == "figure":
                if op.get("where", "panel") == "panel":
                    return True
    return False


def _map_chapter(chapter: dict, has_region: bool) -> bool:
    """A chapter with beats on the map: one beat points at the map, and the chapter is not told not to."""
    if not has_region or chapter.get("map") is False:
        return False
    return any(op.get("op") in MAP_OPS or (op.get("op") == "icon" and _icon_spots(op))
               for b in chapter.get("beats") or [] for op in b.get("do") or [])


def _stages_picture(op: dict) -> bool:
    """Whether an op puts a picture of its own on the stage (a photo, a diagram, a template, a manim figure)."""
    kind = op.get("op")
    return (kind in ("photo", "illustration") and op.get("where", "stage") == "stage" or
            kind == "figure" and op.get("where") == "stage" or
            kind in KIT_OPS | BUILD_OPS | STEM_OPS | WORK_OPS | FREE_OPS)


def _map_runs(chapter: dict, has_region: bool, fills: list | None = None) -> list[tuple[int, int]]:
    """The runs of a chapter's beats taught on the map, as (first, last + 1) beat indexes. Every chapter is on the
    board; the map comes in on a beat that points at it and stays through the beats after it until one puts up a
    picture of its own with nothing on the map (a diagram, a photo, a manim figure), when it goes. A beat that
    points at the map and shows a picture too keeps the map, the picture over it. The beats just before a run that
    show nothing of their own (a panel title, a fact) are on the map too: what they put up is the map's."""
    if not _map_chapter(chapter, has_region):
        return []
    runs, start, floor = [], None, 0       # floor: the first beat after the last picture of the board's own
    for bi, beat in enumerate(chapter.get("beats") or []):
        ops = [op for op in beat.get("do") or [] if isinstance(op, dict)]
        if fills and bi < len(fills) and fills[bi]:
            ops.append(fills[bi])
        if any(_points_at_map(op) for op in ops):
            if start is None:
                start = floor
        elif any(_stages_picture(op) for op in ops):
            if start is not None:
                runs.append((start, bi))
                start = None
            floor = bi + 1
    if start is not None:
        runs.append((start, len(chapter.get("beats") or [])))
    return runs


def _run_of(chapter: dict, first: int, last: int) -> dict:
    """A run of a chapter's beats, as a chapter of its own (for its frame, its places and its panel)."""
    return {**chapter, "beats": (chapter.get("beats") or [])[first:last]}


BARE_OPENING = 3         # beats a chapter may open with before something is on the stage (an error)


def _bare_stretches(script: dict) -> tuple[list[str], list[str]]:
    """(errors, warnings) about beats with nothing on the stage. A picture stays up until the next one (a chapter's
    map, its diagrams, its figures), so the stage is only ever empty where a chapter opens without one: three beats
    of that (half a minute of an empty board) is an error. Long runs that go on talking over the same picture are
    advice."""
    errors, warnings = [], []
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        # The map is the picture of the beats on it.
        on_map = _map_chapter(chapter, bool(script.get("region")))
        beats = chapter.get("beats") or []
        opening = 0
        for beat in beats:
            if any(op.get("op") in VISUAL_OPS | WORK_OPS or op.get("op") == "manim" or on_map and _points_at_map(op)
                   for op in beat.get("do") or []):
                break
            opening += 1
        # Only where the writer draws the pictures (sciences, mathematics): elsewhere the compiler puts up photos
        # of what a paragraph names (auto_visuals).
        drawn_here = script.get("genre") in BOARD_GENRES or any(
            op.get("op") in STEM_OPS | WORK_OPS for b in beats for op in b.get("do") or [])
        if opening >= BARE_OPENING and drawn_here:
            errors.append(f"chapter {ci} ({chapter.get('title', '')!r}): its first {opening} beats show nothing on "
                          "the stage. Put up the chapter's first picture on its first beat (a diagram, a "
                          "manim drawing, a figure, a define card), and build on it as the narration goes on")
        run = 0
        for bi, beat in enumerate(beats, 1):
            # Revealing more of a drawing, or adding to a worked solution, keeps the picture going.
            if any(op.get("op") in VISUAL_OPS | STEP_OPS | WORK_OPS or on_map and _points_at_map(op)
                   for op in beat.get("do") or []):
                run = 0
                continue
            run += 1
            if run == 6:
                warnings.append(f"chapter {ci} beat {bi}: six beats talking over the same picture; show the next "
                                "thing being explained (a new diagram, or reveal more of this one)")
    return errors, warnings


FIGURE_STOP = set("""figure fig the and for with from this that shows show showing into over under between
of in on at to a an by is are was were its their our your as or""".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z\u0900-\u097f]{3,}", str(text).lower()) if w not in FIGURE_STOP}


def place_figures(script: dict) -> int:
    """Put every document figure the script did not show where the narration talks about it.

    A figure goes to the beat whose words best overlap its caption, else in
    document order; never on a beat that already shows a picture or points at
    the map, and at most one figure every two beats. Returns how many it placed.
    """
    figures = script.get("figures") or {}
    beats = [(ci, bi, b) for ci, c in enumerate(script.get("chapters") or []) for bi, b in enumerate(c.get("beats") or [])]
    if not figures or not beats:
        return 0
    used = {str(op.get("id")) for _, _, b in beats for op in b.get("do") or [] if op.get("op") == "figure"}
    waiting = [fid for fid in figures if fid not in used
               and not NOT_A_FIGURE.search(str((figures[fid] or {}).get("caption", "")))]
    budget = max(0, len(beats) // 2 - len(used))
    taken = {i for i, (_, _, b) in enumerate(beats)
             if any(op.get("op") in VISUAL_OPS or _points_at_map(op) for op in b.get("do") or [])}
    # Nor while a problem is being solved or a working is being written: a figure there took the problem,
    # its drawing and its working off the board in mid-solution.
    solving, chapter = False, None
    for i, (ci, _, b) in enumerate(beats):
        kinds = {op.get("op") for op in b.get("do") or []}
        if ci != chapter:
            solving, chapter = False, ci
        if "problem" in kinds:
            solving = True
        elif kinds & (VISUAL_OPS - {"problem", "define", "equation", "question"}):
            solving = False
        # A question or its answer is about the drawing on the board: a figure there would take it away.
        if solving or kinds & (WORK_OPS | STEP_OPS | {"question", "answer"}):
            taken.add(i)
    placed = 0
    for order, fid in enumerate(waiting):
        if placed >= budget:
            break
        caption = _words(figures[fid].get("caption", ""))
        free = [i for i in range(len(beats)) if i not in taken and i - 1 not in taken and i + 1 not in taken] or \
            [i for i in range(len(beats)) if i not in taken]
        if not free:
            break
        scored = sorted(free, key=lambda i: -len(caption & _words(beats[i][2].get("say", ""))))
        best = scored[0]
        if not caption & _words(beats[best][2].get("say", "")):
            # No beat names it: keep the document's order across the lecture.
            target = round((order + 0.5) / len(waiting) * (len(beats) - 1))
            best = min(free, key=lambda i: abs(i - target))
        beats[best][2].setdefault("do", []).append({"op": "figure", "id": fid, "where": "stage"})
        taken.add(best)
        placed += 1
    return placed


def _points_at_map(op: dict) -> bool:
    return op.get("op") in MAP_OPS or (op.get("op") == "icon" and bool(_icon_spots(op)))


EQUATION = re.compile(r"((?:[A-Za-z0-9_^()·+\-*/ ]*[A-Za-z][A-Za-z0-9_^()·+\-*/ ]*)(?:=|->|→)"
                      r"(?:[A-Za-z0-9_^()·+\-*/ ]*[A-Za-z0-9][A-Za-z0-9_^()·+\-*/ ]*))")
YEAR_EVENT = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")


MATH_STOP = {"is", "as", "it", "of", "to", "in", "on", "at", "by", "an", "or", "if", "so", "we", "be", "the", "and",
             "that", "this", "with", "into", "then", "its"}


def _mathy(token: str) -> bool:
    t = token.strip(".,;:")
    if not t or t.lower() in MATH_STOP:
        return False
    return bool(re.fullmatch(r"[+\-*/·^()=→]+|->|\d+(\.\d+)?|[A-Za-z]{1,2}\d*|\d*(?:[A-Z][a-z]?\d*)+|"
                             r"[A-Za-z0-9()]*[\^/*][A-Za-z0-9()^/*]*", t))


def _equation_in(text: str) -> str | None:
    """The formula a sentence states (F = ma, CH4 + 2O2 -> CO2 + 2H2O), or None.

    From the = or -> outward, only over maths-like tokens: variables, numbers,
    chemical formulas and operators, so the sentence around it stays out.
    """
    tokens = (text or "").replace("→", " -> ").split()
    for i, tok in enumerate(tokens):
        if tok not in ("=", "->"):
            continue
        lo = i
        while lo > 0 and _mathy(tokens[lo - 1]):
            lo -= 1
        hi = i
        while hi + 1 < len(tokens) and _mathy(tokens[hi + 1]):
            hi += 1
        if lo == i or hi == i:
            continue
        found = " ".join(t.strip(".,;:") for t in tokens[lo:hi + 1])
        if tok == "->":
            found = re.sub(r"(?<=[A-Za-z)])(\d+)", lambda m: "_" + (m.group(1) if len(m.group(1)) == 1
                                                                        else "{" + m.group(1) + "}"), found)
        return found
    return None


def _timeline_of(chapter: dict) -> list[list[str]] | None:
    """[year, who or what] from a history chapter's beats, when it names three or more years."""
    events, seen = [], set()
    months = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December", "The", "In", "On", "At", "By", "After", "Before", "When"}
    for beat in chapter.get("beats") or []:
        say = beat.get("say", "")
        for m in YEAR_EVENT.finditer(say):
            if m.group(1) in seen:
                continue
            seen.add(m.group(1))
            names = [w.strip(",.;:'’s") for w in re.findall(r"\b[A-Z][a-zA-Z'’-]+", say) if w.strip(",.;:") not in months]
            label = " ".join(dict.fromkeys(names))[:22] or " ".join(say[m.end():].split()[:3]).strip(" ,.;:")
            events.append([m.group(1), label])
    events.sort()
    return events[:7] if len(events) >= 3 else None


# Capitalised words that start sentences or name no one: not subjects to look up.
NAME_STOP = set("""
I A An The This That These Those It Its He She His Her They Their We Our You Your Chapter Today Here There Then
In On At Of And But Or So As When While After Before During From To For With By Now Next Later First Finally
Many Most Some Every Each One Two Three Let Look See Why What Who How Where Which Imagine Think Remember
India Indian Indians Hindi English Earth Sun Moon North South East West January February March April May June
July August September October November December Monday Tuesday Wednesday Thursday Friday Saturday Sunday
""".split())
_NAME = re.compile(r"[A-Z][a-zA-Z'’.-]+(?:\s+(?:of|the|de|ud|al|and|-)?\s*[A-Z][a-zA-Z'’.-]+)*")


def named_subjects(beat: dict, limit: int = 2) -> list[str]:
    """What a beat is about, to look up a picture of: its `about` (a name the writer gave, in English), else the
    proper names in its English narration (people, movements, monuments, events: "Sunderlal Bahuguna",
    "Chipko Movement", "Battle of Plassey")."""
    about = beat.get("about")
    if about:
        return [str(a) for a in (about if isinstance(about, list) else [about]) if str(a).strip()][:limit]
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?।;:])\s+", str(beat.get("say", ""))):
        sentence = sentence.strip()
        for m in _NAME.finditer(sentence):
            words = m.group(0).split()
            while words and words[0] in NAME_STOP:
                words = words[1:]
            while words and words[-1] in ("of", "the", "and", "-"):
                words = words[:-1]
            if not words or all(w in NAME_STOP for w in words):
                continue
            if len(words) == 1 and m.start() == 0 and m.group(0) == words[0]:
                continue            # one capitalised word opening a sentence is just a capital letter
            name = " ".join(words).rstrip(".’'")
            if len(name) > 2 and name not in out:
                out.append(name)
    return out[:limit]


PARAGRAPH_MAX = 5        # beats a picture may hold without the script asking for a new one


def paragraphs(beats: list, is_map_op=None) -> list[list[int]]:
    """The beats in paragraphs: a paragraph starts at the chapter's start, at a beat marked "paragraph": true,
    at a beat that puts up its own picture (a map, a diagram, a photo...), and after PARAGRAPH_MAX beats unless
    the beat goes on with the picture already up."""
    is_map_op = is_map_op or _points_at_map
    out: list[list[int]] = []
    for index, beat in enumerate(beats):
        ops = beat.get("do") or []
        fresh = beat.get("paragraph") or any(op.get("op") in VISUAL_OPS or is_map_op(op) for op in ops)
        # A beat that goes on with the picture (reveals more of it, rings a part, adds working) stays in its
        # paragraph however long it runs: splitting there cleared the picture in the middle of its build.
        continues = any(op.get("op") in STEP_OPS | WORK_OPS for op in ops)
        if not out or fresh or (len(out[-1]) >= PARAGRAPH_MAX and not continues):
            out.append([index])
        else:
            out[-1].append(index)
    return out


# Narration that explains a structure: the one time a structural formula on the stage teaches more than the name.
STRUCTURE_TALK = re.compile(
    r"\b(structur\w*|bond(?:s|ed|ing)?|formula|atoms?|ring|shape|geometr\w*|functional group|isomer\w*|chain|"
    r"hydroxyl|carboxyl|amino group|carbonyl|lone pair|tetrahedr\w*|planar|linear|bent|helix|helical|"
    r"base pair\w*|backbone|polymer\w*|monomer\w*|single bond|double bond|triple bond|covalent)\b|"
    # Hindi has no word boundaries here: बंध alone matched संबंध (a relationship), आकार any size.
    r"संरचना|आबंध|सूत्र|परमाणु|वलय|आकृति|श्रृंखला|समावयव|क्रियात्मक समूह",
    re.IGNORECASE)


def _unneeded_molecules(script: dict, drop: bool = False) -> list[str]:
    """The molecule ops that are not needed: the same molecule again in a chapter, or one on a beat (and the beat
    after it) that explains no structure -- a substance only named ("water is everywhere in the body") is said,
    not drawn. With `drop`, they are taken out of the script."""
    notes: list[str] = []
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        beats = chapter.get("beats") or []
        in_chapter: set[str] = set()
        for bi, beat in enumerate(beats, 1):
            ops = beat.get("do")
            if not isinstance(ops, list):
                continue
            said = str(beat.get("say") or "")
            after = str(beats[bi].get("say") or "") if bi < len(beats) else ""
            keep = []
            for op in ops:
                if not (isinstance(op, dict) and op.get("op") == "molecule"):
                    keep.append(op)
                    continue
                name = str(op.get("name") or "").strip().lower()
                why = None
                if name in in_chapter:
                    why = "it is already on the board in this chapter"
                # The structure may be explained on the next beat, when that beat is about the same molecule.
                elif not STRUCTURE_TALK.search(said) and not (name and name in after.lower()
                                                              and STRUCTURE_TALK.search(after)):
                    why = "the narration explains no structure here (its bonds, shape or groups)"
                if why:
                    notes.append(f"chapter {ci} beat {bi}: the molecule {op.get('name')!r} is left out: {why}. "
                                 "Show a structural formula only where its structure is being explained.")
                    if drop:
                        continue
                else:
                    in_chapter.add(name)
                keep.append(op)
            if drop:
                beat["do"] = keep
    return notes


def auto_visuals(chapter: dict, is_map_op=None, genre: str | None = None) -> list[dict | None]:
    """What the stage shows where the script chose nothing, a paragraph at a time -- never a picture a sentence.

    A paragraph that opens without a picture of its own (see `paragraphs`) gets, on its first beat:
    - a molecule or equation its beats contain (sciences), or a timeline of the chapter's years (history,
      the first paragraph);
    - else pictures of the people, communities and places it names (Wikipedia's picture of each; two or
      three together as a gallery);
    - else, only when the script sets "auto_illustrations": true, a fetched illustration of its topic;
    - else nothing new: the last paragraph's picture stays up (a board is never left empty mid-chapter), and a
      diagram the writer builds is always better than a guessed image.
    The picture then holds through the paragraph.
    """
    import images

    beats = chapter.get("beats") or []
    out: list[dict | None] = [None] * len(beats)
    is_map_op = is_map_op or _points_at_map
    shown_molecules = {str(op.get("name")).lower() for b in beats for op in b.get("do") or []
                       if isinstance(op, dict) and op.get("op") == "molecule"}
    auto_molecules = 0
    for group in paragraphs(beats, is_map_op):
        first = beats[group[0]]
        ops = first.get("do") or []
        if any(is_map_op(op) for op in ops):
            continue                # the map is the picture (compile clears the stage for it)
        if any(op.get("op") in VISUAL_OPS for op in ops):
            continue
        text = " ".join(str(beats[i].get("say", "")) for i in group)
        pick = None
        if genre in ("chemistry", "biology", "physics", "mathematics"):
            equation = next((e for e in (_equation_in(str(beats[i].get("say", ""))) for i in group) if e), None)
            if equation:
                pick = {"op": "equation", "tex": equation}
            elif genre in ("chemistry", "biology") and STRUCTURE_TALK.search(text) and auto_molecules < 1:
                # A structural formula only where the paragraph explains a structure (its bonds, its shape, its
                # groups), once a chapter, and never one already shown: a molecule for every substance named made
                # every chemistry and biology video a parade of ball-and-stick drawings.
                import molecules

                named = [n for n in molecules.find_in_text(text) if n not in shown_molecules]
                if named:
                    pick = {"op": "molecule", "name": named[0]}
                    shown_molecules.add(named[0])
                    auto_molecules += 1
        if not pick and genre == "history" and group[0] == 0 and not any(
                op.get("op") == "timeline" for b in beats for op in b.get("do") or []):
            events = _timeline_of(chapter)
            if events:
                pick = {"op": "timeline", "events": events}
        # (No picture is added here: whether a paragraph gets a picture, and of what kind -- one the image model
        # makes (an illustration or a detailed diagram), or Manim -- is the writer's judgement.)
        if pick:
            out[group[0]] = pick
        # Nothing new for this paragraph: the last picture stays up. Taking it down left the board empty while
        # the teacher went on explaining it (every fifth beat of a long explanation, in sciences with no photos).
    return out


# Pictures a lecture has shown, so one diagram does not stand for several topics (reset per compile), and the
# lecture's style, which an AI illustration is drawn in.
USED_PICTURES: set = set()
# The pictures the compiler chose itself for paragraphs without one: (chapter, beat, op), 1-based (pictures_used).
AUTO_PICTURES: list = []
STYLE_NOW: dict = {"style": None, "auto_illustrations": False}

PLAIN = set("""
about above after again against almost along also although always among another around because become before
being below between both came come could does doing down during each even every first from further have having
here into itself just know known large like made make many more most much must near never next only other over
own part same should since small some such than that their them then there these they thing things this those
though three through today together under until upon very want were what when where which while whole will with
within without would your called means mean each other people place places important different example because
often usually really almost called across towards toward still again later early every whole across
""".split())


def picture_queries(beat: dict, chapter: dict, genre: str | None, index: int) -> list[str]:
    """What to search an illustration or diagram for: the writer's `picture` (English), else the beat's key
    terms in English narration (with the chapter's title for context), else the chapter's own title on its
    first beat."""
    if beat.get("picture"):
        return [str(beat["picture"])]
    title = str(chapter.get("title", ""))
    latin_title = title if re.search(r"[A-Za-z]{3}", title) and not re.search(r"[\u0900-\u097F]", title) else ""
    def stem(word: str) -> str:
        return re.sub(r"(ies|es|s)$", "", word.lower())

    words = [w.lower() for w in re.findall(r"[A-Za-z][a-z]{3,}", str(beat.get("say", ""))) if w.lower() not in PLAIN]
    # A topic word recurs: rank a beat's words by how often the chapter uses them, then by length.
    chapter_text = " ".join([title] + [str(b.get("say", "")) for b in chapter.get("beats") or []]).lower()
    counts: dict[str, int] = {}
    for w in re.findall(r"[a-z]{4,}", chapter_text):
        counts[stem(w)] = counts.get(stem(w), 0) + 1
    queries = []
    if words:
        key = sorted(dict.fromkeys(words), key=lambda w: (counts.get(stem(w), 0), len(w)), reverse=True)[:2]
        queries.append(" ".join(key))
        if latin_title:
            queries.append(f"{latin_title} {key[0]}")
    if index == 0 and latin_title:
        queries.append(latin_title)
    return queries[:2]


def _icon_spots(op: dict) -> list:
    """Where an icon op puts its icons on the map: [] for the panel."""
    if op.get("places"):
        return list(op["places"])
    if op.get("place"):
        return [op["place"]]
    if op.get("lonlat"):
        return [tuple(op["lonlat"])]
    return []


def _picture_flows(script: dict) -> list[str]:
    """Each diagram drawn as one picture ("drawn": "picture", a flow or a cycle of 2 to MOST_STEPS steps): the
    image model draws it whole (picture_flow.make), and it is cut into its steps and arrows (picture_flow.split),
    kept on the op for the engine (`_parts`). One that cannot be drawn so -- another kind, too many steps, a
    picture not made, or one whose parts cannot be told apart -- is built as a diagram instead, and said so."""
    import picture_flow

    notes = []
    for c, chapter in enumerate(script.get("chapters") or []):
        for b, beat in enumerate(chapter.get("beats") or []):
            for op in beat.get("do") or []:
                if not (isinstance(op, dict) and op.get("op") == "diagram" and op.get("drawn") == "picture"):
                    continue
                at = f"chapter {c + 1} beat {b + 1}"
                nodes = [n for n in op.get("nodes") or [] if isinstance(n, dict) and n.get("id") is not None]
                kind = str(op.get("kind") or "flow")
                ids = [str(n["id"]) for n in nodes]
                edges = [[str(e[0]), str(e[1]), *([str(e[2])] if len(e) > 2 and e[2] else [])]
                         for e in op.get("edges") or [] if isinstance(e, (list, tuple)) and len(e) >= 2
                         and str(e[0]) in ids and str(e[1]) in ids] or picture_flow.default_edges(ids, kind)
                why = None
                if kind not in ("flow", "cycle"):
                    why = f"a {kind} is built, not drawn as one picture (only a flow or a cycle is)"
                elif not 2 <= len(nodes) <= picture_flow.MOST_STEPS:
                    why = f"{len(nodes)} steps (one picture holds 2 to {picture_flow.MOST_STEPS})"
                parts = None
                if why is None:
                    steps = [str(n.get("_show") or n.get("label") or n["id"]) for n in nodes]
                    pairs = [(ids.index(e[0]), ids.index(e[1])) for e in edges]
                    made = picture_flow.make(str(op.get("about") or op.get("title") or ""), steps, pairs, kind,
                                             script.get("style"), context=str(beat.get("say") or ""))
                    if made is None or not made.get("file"):
                        why = "its picture could not be made"
                    else:
                        op["_file"] = made["file"]          # the picture itself, for the record (pictures_used)
                        names = [str(n.get("label") or n["id"]) for n in nodes]
                        parts = picture_flow.split(made["file"], names, pairs, kind)
                        if parts is None:
                            # Its parts not apart (drawn touching, or as a whole scene): the picture is still the
                            # one shown, whole, each step boxed, named and lit in it as it is said.
                            import genimage

                            op["_whole"] = {"file": made["file"], "labels": genimage.locate(made["file"], names) or []}
                            notes.append(f"{FIXED}{at}: diagram {op.get('id')!r}: its picture's steps could not be "
                                         "drawn on one by one (they touch); shown whole, each step lit as it is said")
                            continue
                if parts is None:
                    op.pop("drawn", None)
                    op.pop("_parts", None)
                    for node in nodes:
                        show = node.pop("_show", None)
                        if show and not node.get("picture"):
                            node["picture"] = {"generate": _thing_op(show)["query"]}
                    notes.append(f"{FIXED}{at}: diagram {op.get('id')!r} built as a diagram: {why}")
                    continue
                op["_parts"] = parts
                op["_edges"] = edges
    return notes


def _thing_op(name: str) -> dict:
    """The picture op that makes the picture of a thing an icon names (pocket_lecture.thing_picture makes the same
    one, so the scene finds it made): an old library id's words only ("coco:7-cow" -> "cow")."""
    import re as _re

    text = _re.sub(r"^(?:[a-z0-9]+(?:-[a-z0-9]+)*):(?=\S)", "", str(name or "").strip())
    text = _re.sub(r"[-_]+", " ", _re.sub(r"^\d+[-_]", "", text)).strip()
    return {"op": "illustration", "query": text, "optional": True, **SMALL_PICTURE}


def _km(a, b) -> float:
    import math

    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, h)))


# A coordinate further than this from where the gazetteer has the place it is labelled with is the model's guess,
# and is replaced.
GUESS_KM = 30


# How big an area must be on the map (its share of the map's width or height) to be shaded rather than marked
# with a dot: a country across a fifth of the map is its land; a city-state or a small district stays a dot.
AREA_SHADE_SHARE = 0.06


def _areas_shaded(script: dict, pl, home, bounds) -> list[str]:
    """Markers that name an area (a country, a state or province, a region) big enough to see on this map become
    that area shaded, its name written on it (a "state" op): a country drawn as one dot at its middle looked like
    a town. Towns, sites and areas too small to see on the map stay dots. Returns the notes (fixed: ...)."""
    notes: list[str] = []
    box = pl._box(bounds) if bounds else None
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            ops = beat.get("do") if isinstance(beat.get("do"), list) else []
            for k, op in enumerate(ops):
                if not (isinstance(op, dict) and op.get("op") == "marker" and isinstance(op.get("place"), str)
                        and not op.get("lonlat") and not op.get("picture")):
                    continue
                name = op["place"]
                if pl.is_water(name):
                    continue                     # a sea or a strait is named on the water, not filled in
                try:
                    shape = pl.area_shape(name, home)
                except Exception:  # noqa: BLE001 -- not an area: a town or a site, a dot
                    continue
                seen = shape.intersection(box) if box is not None else shape
                if seen.is_empty:
                    continue
                x0, y0, x1, y1 = seen.bounds
                share = max((x1 - x0) / max(bounds[2] - bounds[0], 1e-6), (y1 - y0) / max(bounds[3] - bounds[1], 1e-6)) \
                    if bounds else 1.0
                if share < AREA_SHADE_SHARE:
                    continue
                ops[k] = {"op": "state", "name": name, "label": op.get("label") or name,
                          **({"color": op["color"]} if op.get("color") else {}),
                          **({k2: op[k2] for k2 in ("at",) if op.get(k2)})}
                notes.append(f"{FIXED}chapter {ci} beat {bi}: {name!r} is an area: shaded on the map, not a dot")
    return notes


def _clean_places(script: dict) -> tuple[dict, list[str]]:
    """The script's own places (filled by the map agent, harness/scripts/map_agent.py) that can be drawn, and a note
    for each that cannot: a point is [lon, lat]; an area names provinces ("states") or gives an outline of at least
    three [lon, lat] points."""
    places = script.get("places")
    if not places:
        return {}, []
    if not isinstance(places, dict):
        return {}, [f"{FIXED}places: not an object of name -> place; left out"]
    kept, notes = {}, []

    def pair(p):
        return isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p) \
            and -180 <= p[0] <= 180 and -90 <= p[1] <= 90

    for name, spec in places.items():
        if not isinstance(spec, dict):
            notes.append(f"{FIXED}places: {name!r} is not an object; left out")
            continue
        point = spec.get("lonlat")
        outline = spec.get("outline")
        states = spec.get("states")
        ok_point = point is not None and pair(point)
        ok_outline = isinstance(outline, list) and len(outline) >= 3 and all(pair(p) for p in outline)
        ok_states = isinstance(states, list) and states and all(isinstance(x, str) for x in states)
        if not (ok_point or ok_outline or ok_states):
            notes.append(f"{FIXED}places: {name!r} has no [lon, lat], outline or provinces it can be drawn from; "
                         "left out")
            continue
        kept[str(name)] = {k: v for k, v in spec.items()
                           if k not in ("lonlat", "outline", "states") or
                           (k == "lonlat" and ok_point) or (k == "outline" and ok_outline) or (k == "states" and ok_states)}
    return kept, notes


def _use_places(script: dict) -> list[str]:
    """The script's own places, for every lookup from here on (pocket_lecture.set_places)."""
    kept, notes = _clean_places(script)
    if script.get("places") is not None:
        script["places"] = kept
    try:
        import pocket_lecture as pl
    except Exception:  # noqa: BLE001 -- no engine here (a lint-only install)
        return notes
    region = script.get("region") if isinstance(script.get("region"), dict) else {}
    pl.set_places(kept, region.get("country"))
    return notes


def _resolve_map_points(script: dict) -> tuple[list[str], list[str]]:
    """Where the map's points really are, before anything is drawn: a model's own [lon, lat] is often far off.

    A marker that names its place is drawn at the place (its lonlat dropped); one given only lonlat and a label the
    gazetteer knows is moved there when the two are more than GUESS_KM apart; a journey's [lon, lat] stops are
    checked against their labels the same way; an arrow's or path's points may be place names, looked up. What
    cannot be found, or is off the map, is left out (a marker, a journey's stop, an arrow's point; a journey or
    arrow left with fewer than two goes too), each with a warning. Returns (errors, warnings)."""
    try:
        import pocket_lecture as pl
    except Exception:  # noqa: BLE001 -- no engine here (a lint-only install): the render will say
        return [], []
    region = script.get("region") or {}
    problem, home = _region_problem(region)
    if problem:
        return [], []
    bounds = pl.map_bounds(region)
    warnings: list[str] = _areas_shaded(script, pl, home, bounds)

    def known(name):
        try:
            return pl.place(str(name), home, bounds)
        except KeyError:
            return None

    def where(at, point, label):
        """The point (or where its label really is), or None when it cannot be found or is off the map."""
        if isinstance(point, str):
            found = known(point)
            if found is None:
                warnings.append(f"{FIXED}{at}: no place named {point!r}" + (f" in {home}" if home else "")
                                + "; left out")
                return None
            if bounds and not pl._inside(found, bounds):
                warnings.append(f"{FIXED}{at}: {point!r} is off this map; left out")
                return None
            return point
        point = [float(point[0]), float(point[1])]
        if label:
            found = known(label)
            if found and pl._inside(found, bounds) and _km(point, found) > GUESS_KM:
                warnings.append(f"{FIXED}{at}: {label!r} was given at {point}, {_km(point, found):.0f} km from where "
                                f"it is; drawn at {[round(found[0], 4), round(found[1], 4)]}")
                point = [round(found[0], 4), round(found[1], 4)]
        if bounds and not pl._inside(point, bounds):
            warnings.append(f"{FIXED}{at}: {label or point!r} at {point} is off this map; left out")
            return None
        return point

    def is_point(p):
        return isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)

    for c, chapter in enumerate(script.get("chapters") or []):
        for b, beat in enumerate(chapter.get("beats") or []):
            at = f"chapter {c + 1} beat {b + 1}"
            for op in beat.get("do") or []:
                if not isinstance(op, dict):
                    continue
                kind = op.get("op")
                if kind == "marker":
                    if op.get("place"):
                        op.pop("lonlat", None)                 # the name is where it is
                        if where(at, str(op["place"]), None) is None:
                            op["_drop"] = True
                    elif is_point(op.get("lonlat")):
                        op["lonlat"] = where(at, op["lonlat"], op.get("label"))
                        if op["lonlat"] is None:
                            op["_drop"] = True
                elif kind == "journey" and isinstance(op.get("stops"), list):
                    labels = op.get("labels") if isinstance(op.get("labels"), list) else None
                    pictures = op.get("pictures") if isinstance(op.get("pictures"), list) else None
                    keep = []
                    for k, s in enumerate(op["stops"]):
                        label = labels[k] if labels and k < len(labels) else None
                        point = where(at, s, label) if isinstance(s, str) or is_point(s) else s
                        if point is not None:
                            keep.append(k)
                            op["stops"][k] = point
                    if len(keep) < len(op["stops"]):
                        op["stops"] = [op["stops"][k] for k in keep]
                        if labels:
                            op["labels"] = [labels[k] for k in keep if k < len(labels)]
                        if pictures:
                            op["pictures"] = [pictures[k] for k in keep if k < len(pictures)]
                    if len(op["stops"]) < 2:
                        warnings.append(f"{FIXED}{at}: journey left out: fewer than two of its stops are on the map")
                        op["_drop"] = True
                elif kind in ("arrow", "path") and isinstance(op.get("points"), list):
                    points = []
                    for p in op["points"]:
                        if isinstance(p, str):
                            if where(at, p, None) is not None:
                                found = known(p)
                                points.append([round(found[0], 4), round(found[1], 4)])
                        else:
                            points.append(p)
                    op["points"] = points
                    if len(points) < 2:
                        warnings.append(f"{FIXED}{at}: {kind} left out: fewer than two of its points are on the map")
                        op["_drop"] = True
    _purge(script)
    return [], warnings


# Regions a script names that Natural Earth knows by another name (England is part of the United Kingdom there).
REGION_ALIASES = {
    "england": "United Kingdom", "scotland": "United Kingdom", "wales": "United Kingdom",
    "northern ireland": "United Kingdom", "britain": "United Kingdom", "great britain": "United Kingdom",
    "uk": "United Kingdom", "the uk": "United Kingdom", "holland": "Netherlands", "persia": "Iran",
    "burma": "Myanmar", "siam": "Thailand", "ceylon": "Sri Lanka", "prussia": "Germany", "bohemia": "Czechia",
    "czech republic": "Czechia", "usa": "United States of America", "united states": "United States of America",
    "america": "United States of America", "the united states": "United States of America",
    "russia": "Russia", "soviet union": "Russia", "ussr": "Russia", "gaul": "France", "frankish kingdom": "France",
    "francia": "France", "holy roman empire": "Germany", "hindustan": "India", "bharat": "India",
}


def _fix_region(script: dict) -> list[str]:
    """A region the map cannot draw as named, mended without new words: a name Natural Earth knows otherwise
    (England -> the United Kingdom); a country named as an area or the other way round; and, failing those, no
    map at all (its map ops are then left out, each with a note) instead of the whole section sent back."""
    region = script.get("region")
    if not isinstance(region, dict) or not region:
        return []
    problem, _ = _region_problem(region)
    if not problem:
        return []
    name = str(region.get("area") or region.get("continent") or region.get("country") or region.get("state") or "")
    alias = REGION_ALIASES.get(re.sub(r"\s+", " ", name.strip().lower()))
    tries = []
    if alias:
        tries.append({"country": alias, **({"view": region["view"]} if region.get("view") else {})})
    if region.get("state") and region.get("country"):
        tries.append({"country": region["country"]})
    if region.get("country") and not region.get("state"):
        tries.append({"area": region["country"]})
    if region.get("area"):
        tries.append({"country": region["area"]})
    for candidate in tries:
        if not _region_problem(candidate)[0]:
            script["region"] = candidate
            return [f"{FIXED}region {name!r} drawn as {next(iter(candidate.values()))!r}"]
    script["region"] = None
    return [f"{FIXED}region {name!r} is no country, state or area the map knows: the lecture has no map"]


def _region_problem(region) -> tuple[str | None, str | None]:
    """(why the script's region cannot be drawn, or None; the country its places are looked up in). A region is a
    country, a state with its country, or an area: the world, a continent, a world region (pocket_lecture)."""
    if not isinstance(region, dict) or not region:
        return None, None
    try:
        from pocket_lecture import region_kind
    except Exception:  # noqa: BLE001 -- no engine here (a lint-only install): the render will say
        return None, region.get("country")
    try:
        kind = region_kind(region)
    except KeyError as error:
        return (f"region: {str(error).strip(chr(34))}. A region is a country ({{\"country\": \"India\"}}), a state "
                f"({{\"state\": \"Kerala\", \"country\": \"India\"}}) or an area: the world, a continent or a world "
                f"region ({{\"area\": \"World\"}}, {{\"area\": \"Asia\"}}, {{\"area\": \"South Asia\"}}, "
                f"{{\"area\": \"Middle East\"}})"), None
    return None, None if kind == "area" else region.get("country")


def _unknown_places(places: list[tuple[str, str]], country: str | None, region: dict | None = None) -> list[str]:
    """Marker places the gazetteer cannot find, or finds only off this map: caught here, not halfway through a
    render."""
    if not places:
        return []
    try:
        import pocket_lecture as pl
    except Exception:  # noqa: BLE001 -- no engine here (a lint-only install): the render will say
        return []
    bounds = pl.map_bounds(region) if region else None
    out = []
    for at, name in places:
        try:
            found = pl.place(name, country, bounds)
            if not pl._inside(found, bounds):
                out.append(f"{at}: {name!r} is at {[round(found[0], 2), round(found[1], 2)]}, off this map; name a "
                           "place on it (or widen the region)")
        except KeyError:
            out.append(f"{at}: no place named {name!r}" + (f" in {country}" if country else "")
                       + "; use the modern town it is in, or a nearby larger town (a guessed lon/lat is usually wrong)")
    return out


def _diagram_labels(op: dict) -> dict:
    """A diagram's (or a drawing's) part ids and the names written on them."""
    if op.get("op") == "draw":
        return {str(p): str(p).replace("_", " ") for p in op.get("parts") or []}
    return {str(n.get("id")): str(n.get("label") or n.get("id")) for n in op.get("nodes") or []
            if isinstance(n, dict) and n.get("id") is not None}


def _op_said(op: dict, parts: dict, asked: list) -> str | list[str] | None:
    """The words a picture shows, so it starts as the narration says them: a marker's place, a shaded area's name,
    a diagram part revealed or pointed at, a term defined, a choice marked; for any other picture with words on it
    (a card, a chart, a timeline, a new diagram), the words it shows, to come on with the first of them said
    (_shown_words). None for one that acts as the line begins (UNSAID_OPS) or shows no words."""
    kind = op.get("op")
    on = op.get("on")
    if isinstance(on, str) and on.strip():
        # The words the scene writer named for it (anchors); "start": as the line begins.
        return None if on.strip() == "start" else on.strip()
    if kind in ("marker", "state", "river", "empire"):
        return str(op.get("label") or op.get("place") or op.get("name") or "") or None
    if kind in ("arrow", "path", "graticule"):
        return str(op.get("label") or "") or None
    if kind == "relief":
        names = op.get("names") if isinstance(op.get("names"), list) else []
        return str(names[0]) if names else None
    if kind == "reveal":
        nodes = [str(n) for n in op.get("nodes") or []]
        return (parts.get(str(op.get("diagram"))) or {}).get(nodes[0]) if nodes else None
    if kind in ("focus", "zoom"):
        node = op.get("node")
        return (parts.get(str(op.get("diagram"))) or {}).get(str(node)) if node is not None else None
    if kind == "define":
        return str(op.get("term") or "") or None
    if kind == "option":
        index = _choice_index(asked, op.get("choice")) if asked else None
        return asked[index] if index is not None else None
    if kind in UNSAID_OPS:
        return None
    return _shown_words(op) or None


def no_key_points(script: dict, warnings: list[str]) -> None:
    """The board has no key point (v2: stem.board_point draws nothing): a "fact" on a board chapter is left out, with
    a note. A side panel (the script's "layout": "panel") keeps its points."""
    if script.get("layout") == "panel":
        return
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            ops = beat.get("do") if isinstance(beat, dict) else None
            if not isinstance(ops, list):
                continue
            kept = [op for op in ops if not (isinstance(op, dict) and op.get("op") == "fact")]
            if len(kept) < len(ops):
                warnings.append(f"fixed: chapter {ci} beat {bi}: the board has no key point; its fact left out "
                                "(the line's words are its caption)")
                beat["do"] = kept


# ---------------- anchors: the words each picture lands on ----------------
# The scene writer names, on each operation and on each part inside one (a node, a step, an event, a label, an
# item), the words of its line it lands on: "on": "<the words, copied from the line>", or "start" (with the line).
# They are checked here against the line as the voice will say it, mended to the line's own words when a word or
# two is off, and refused (the writer asked again) when they are not in the line at all.

NAMED_BY = ("label", "text", "title", "name", "term", "date")


def _closest(spoken: list[str], wanted: str) -> str | None:
    """The run of the line's words most like `wanted` (a word misspelt, a plural, a matra dropped), when it is close
    enough to be the same words; None when no run is."""
    import difflib

    size = max(1, len(wanted.split()))
    target = wanted.lower()
    best, found = 0.0, None
    for n in {max(1, size - 1), size, size + 1}:
        for i in range(0, max(1, len(spoken) - n + 1)):
            run = " ".join(spoken[i:i + n]).strip(".,;:!?।॥\"'“”‘’()")
            score = difflib.SequenceMatcher(None, run.lower(), target).ratio()
            if score > best:
                best, found = score, run
    return found if best >= 0.75 else None


def _short_word_phrase(spoken: list[str], wanted: str) -> str | None:
    """For an anchor of one short word (two letters or fewer, too short to be found on its own) that the line says:
    the two words it is said with (the word before it and it, or it and the word after), which can be found."""
    import pocket_lecture as pl

    token = pl._say_tokens(wanted)
    if len(token) != 1 or len(token[0]) > 2 or token[0].isdigit():
        return None
    said = [pl._say_tokens(w) for w in spoken]
    for k, toks in enumerate(said):
        if token[0] in toks:
            pair = spoken[k - 1:k + 1] if k > 0 else spoken[k:k + 2]
            phrase = " ".join(pair).strip(".,;:!?।॥\"'“”‘’()")
            return phrase if len(pair) == 2 else None
    return None


def anchors(script: dict, errors: list[str], warnings: list[str]) -> None:
    """Each operation's and each part's "on" checked against its line (pocket_lecture.said_at, on the line as it is
    spoken): kept when the line says it, mended to the line's own words when nearly, refused when not. A part's
    anchor is kept on the beat (`_spoken_as`, its name to its words) for the engine to time the part by
    (Lecture.spoken_as); on the current engine it is taken off the part itself, which the engine does not read. A
    picture's label may be {"name", "on"}: it becomes its name."""
    import pocket_lecture as pl

    motion = script.get("engine") == "motion"
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            if not isinstance(beat, dict):
                continue
            spoken = pl.speechify(str(beat.get("say") or "")).split()
            words = [{"w": w, "start": float(k)} for k, w in enumerate(spoken)]
            alias: dict[str, str] = {}

            def check(holder: dict, where: str, name: str | None = None) -> None:
                on = holder.get("on")
                if on is None:
                    return
                if not isinstance(on, str) or not on.strip():
                    holder.pop("on", None)
                    return
                on = on.strip()
                if on.lower() == "start":
                    holder["on"] = "start"
                    return
                if pl.said_at(words, on) is None:
                    near = _closest(spoken, on)
                    short = _short_word_phrase(spoken, on)
                    if short is not None:
                        # A small word (है, थे, गए, "Wu") is too short to find on its own: the words round it.
                        near = short
                    if near is None or pl.said_at(words, near) is None:
                        errors.append(f"chapter {ci} beat {bi}: {where}: \"on\": {on!r} is not in its line; copy the "
                                      "words it lands on from the line exactly as written (or \"start\")")
                        holder.pop("on", None)
                        return
                    warnings.append(f"fixed: chapter {ci} beat {bi}: {where}: \"on\": {on!r} is {near!r} in its line")
                    on = near
                holder["on"] = on
                if name:
                    alias[name] = on

            def inside(value, where: str, depth: int = 0) -> None:
                if depth > 4:
                    return
                if isinstance(value, list):
                    for k, item in enumerate(value):
                        if isinstance(item, dict) and set(item) <= {"name", "on"} and "name" in item:
                            # A picture's label as {"name", "on"}: its name, its words kept by name.
                            check(item, f"{where} {item['name']!r}", str(item["name"]))
                            value[k] = str(item["name"])
                            continue
                        inside(item, where, depth + 1)
                elif isinstance(value, dict):
                    name = next((str(value[k]) for k in NAMED_BY if isinstance(value.get(k), (str, int, float))
                                 and str(value[k]).strip()), None)
                    if "on" in value:
                        check(value, f"{where} {name!r}" if name else where, name)
                        if not motion:
                            value.pop("on", None)
                    for key, inner in value.items():
                        if key != "on":
                            inside(inner, where, depth + 1)

            for op in beat.get("do") or []:
                if not isinstance(op, dict):
                    continue
                where = str(op.get("op") or "operation")
                check(op, where)
                for key, inner in op.items():
                    if key != "on":
                        inside(inner, where)
            if alias:
                beat["_spoken_as"] = alias


# Operations that are not a thing the narration names: they act as the line begins (or as their own `think` says).
UNSAID_OPS = {"clear", "unstage", "manim", "answer", "emphasis", "zoom", "camera", "pause", "think", "map_in",
              "map_away", "recap"}
# Words too common to time a picture by: said anywhere, they would bring it on before the line comes to it.
COMMON_WORDS = set("""the and for are was were with that this these those from into onto than then them they their
there here which while whom whose its his her hers our ours your yours has have had not
but all any each one two very more most less much many some such also just only over under about after before
between through during without within upon been being will would could should can may might must shall does did
done make made like way ways part parts thing things kind kinds""".split())


def _shown_words(op: dict) -> list[str]:
    """The words a picture puts on the screen (its title, text, labels, its items' names), as words to time it by:
    it comes on as the line says the first of them (pocket_lecture.Lecture._on_words), 0.2 s before it. A picture
    shows what is being said, as it is said: a card that came on as the line began was up seconds before its words.
    Common words, short words and the image model's prompts are left out."""
    texts: list[str] = []

    def take(value, depth=0):
        if depth > 4 or value is None:
            return
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            texts.append(str(value))
        elif isinstance(value, dict):
            for key, inner in value.items():
                if key in SHOWN_KEYS:
                    take(inner, depth + 1)
        elif isinstance(value, (list, tuple)):
            for inner in value:
                take(inner, depth + 1)

    kind = op.get("op")
    if kind in PICTURE_OPS:
        # A picture is what the line is about: on its caption or title, else as the line begins. Its labels are
        # its parts, each coming on with its own words.
        take(op.get("caption"))
        take(op.get("title"))
    elif kind == "diagram":
        # On its title or a node drawn at first; the nodes revealed later have their own words.
        take(op.get("title"))
        shown = {str(x) for x in op.get("show") or []}
        for node in op.get("nodes") or []:
            if isinstance(node, dict) and (not shown or str(node.get("id")) in shown):
                take(node.get("label"))
    else:
        for key, value in op.items():
            if key in SHOWN_KEYS:
                take(value)
    out: list[str] = []
    for text in texts:
        for word in re.findall(r"[\w\u0900-\u0963\u0966-\u0DFF][\w'\u0900-\u0963\u0966-\u0DFF.,]*", text):
            word = word.strip("'.,")
            if (len(word) >= 3 or word.isdigit() and len(word) >= 2) and word.lower() not in COMMON_WORDS \
                    and word not in out:
                out.append(word)
    return out[:16]


PICTURE_OPS = {"picture", "figure", "draw", "illustration", "photo", "gallery", "polaroids", "image"}
# The keys whose values are words on the screen (not an image model's prompt, an id or a colour).
SHOWN_KEYS = {"title", "sub", "text", "label", "labels", "term", "meaning", "caption", "value", "name", "kicker",
              "items", "steps", "events", "columns", "points", "nodes", "left", "right", "cards", "groups", "big",
              "wrong", "right", "part_label", "rest_label", "lines", "tex", "date", "highlight", "headline", "stops",
              "tiers", "rows", "headers", "fly", "quote", "who", "answer_text", "choices"}


def _op_call(op: dict) -> str:
    kind = op["op"]
    if kind == "panel":
        sub = f", {_q(op['sub'])}" if op.get("sub") else ""
        return f"self.panel_title({_q(op['title'])}{sub})"
    if kind == "fact":
        color = _colour(op.get("color"))
        return f"self.fact({_q(op['text'])}" + (f", {color}, {color}" if color else "") + ")"
    if kind == "stat":
        color = _colour(op.get("color"))
        return f"self.big_stat({_q(op['value'])}, {_q(op['label'])}" + (f", {color}" if color else "") + ")"
    if kind == "bars":
        items = ", ".join(f"({_q(label)}, {float(value):g})" for label, value in op["items"])
        extra = f", {_colour(op.get('color'), 'None')}, {_q(op.get('unit', ''))}"
        return f"self.bar_chart([{items}]{extra})"
    if kind == "clear":
        return "self.clear_panel()"
    if kind == "marker":
        where = _q(op["place"]) if op.get("place") else f"({float(op['lonlat'][0])}, {float(op['lonlat'][1])})"
        label = f", label={_q(op['label'])}" if op.get("label") else ""
        color = f", color={_colour(op.get('color'))}" if op.get("color") else ""
        side = f", d={SIDES[op['side']]}" if op.get("side") in SIDES else ""
        picture = f", picture={_picture_arg(op['picture'])}" if op.get("picture") else ""
        return f"self.mark({where}{label}{color}{side}{picture})"
    if kind == "river":
        color = f", {_colour(op.get('color'))}" if op.get("color") else ""
        return f"self.river({_q(op['name'])}{color})"
    if kind in ("path", "arrow"):
        pts = ", ".join(f"({float(x):g}, {float(y):g})" for x, y in op["points"])
        color = f", {_colour(op.get('color'))}" if op.get("color") else ""
        method = "path" if kind == "path" else "flow"
        label = f", label={_q(op['label'])}" if kind == "arrow" and op.get("label") else ""
        return f"self.{method}([{pts}]{color}{label})"
    if kind == "relief":
        names = [str(n) for n in op["names"]] if isinstance(op.get("names"), list) else None
        label = "" if op.get("label", True) else ", label=False"
        return f"self.relief({names!r}{label})"
    if kind == "empire":
        color = f", color={_colour(op.get('color'))}" if op.get("color") else ""
        label = f", label={_q(op['label'])}" if op.get("label") else ""
        return f"self.empire({_q(op['name'])}, {int(op['year'])}{color}{label})"
    if kind == "journey":
        stops = ", ".join(_q(x) if isinstance(x, str) else f"({float(x[0]):g}, {float(x[1]):g})" for x in op["stops"])
        color = f", color={_colour(op.get('color'))}" if op.get("color") else ""
        labels = f", labels={[str(x) for x in op['labels']]!r}" if isinstance(op.get("labels"), list) else ""
        pictures = (f", pictures=[{', '.join(_picture_arg(p) for p in op['pictures'])}]"
                    if isinstance(op.get("pictures"), list) and any(op["pictures"]) else "")
        return f"self.journey([{stops}]{color}{labels}{pictures})"
    if kind == "state":
        # No colour: the engine gives each area a tone of its own.
        color = _colour(op.get("color")) if op.get("color") else "None"
        label = f", label={_q(op['label'])}" if op.get("label") else ""
        return f"self.fill_state({_q(op['name'])}, {color}, {float(op.get('opacity', 0.6)):g}{label})"
    if kind == "dim":
        return f"*self.dim(opacity={float(op.get('opacity', 0.15)):g})"
    if kind == "icon":
        color = f", color={_colour(op.get('color'))}" if op.get("color") else ""
        label = f", label={_q(op['label'])}" if op.get("label") else ""
        spots = _icon_spots(op)
        if not spots:
            return f"self.panel_icon({_q(op['name'])}{label}{color})"
        where = ", ".join(_q(p) if isinstance(p, str) else f"({float(p[0])}, {float(p[1])})" for p in spots)
        size = f", size={float(op['size']):g}" if op.get("size") else ""
        return f"self.icon({_q(op['name'])}, [{where}]{color}{size}{label})"
    if kind == "photo":
        row = script_photos[_photo_key(op)]
        where = op.get("where", "stage")
        caption = op.get("caption") or ""
        if where == "stage":
            return f"self.stage_image({_q(row['file'])}, {_q(caption)}, credit={_q(_shown_credit(row))}{_labels_arg(row)})"
        return f"self.figure({_q(row['file'])}, {_q(caption)}, where={_q(where)})"
    if kind == "molecule":
        label = f", {_q(op['label'])}" if op.get("label") else ""
        return f"self.molecule({_q(op['name'])}{label})"
    if kind == "equation":
        label = f", {_q(op['label'])}" if op.get("label") else ""
        return f"self.equation({_q(op['tex'])}{label})"
    if kind == "process":
        title = f", {_q(op['title'])}" if op.get("title") else ", None"
        return f"self.process([{', '.join(_q(x) for x in op['steps'])}]{title}, cycle={bool(op.get('cycle'))})"
    if kind == "timeline":
        events = ", ".join(f"({_q(d)}, {_q(lab)}, {_picture_arg(pic)})" for d, lab, pic in _timeline_events(op))
        title = f", {_q(op['title'])}" if op.get("title") else ""
        # v2: the years the track covers, periods shaded along it, even spacing (timeline_dates, big_timeline).
        extra = ""
        if op.get("range"):
            extra += f", range=({_q(op['range'][0])}, {_q(op['range'][1])})"
        if op.get("spans"):
            extra += ", spans=[" + ", ".join(f"({_q(a)}, {_q(b)}, {_q(t)})" for a, b, t in op["spans"]) + "]"
        if op.get("scale") == "even":
            extra += ', scale="even"'
        return f"self.big_timeline([{events}]{title}{extra})"
    if kind == "quote":
        return f"self.quote({_q(op['text'])}, {_q(op.get('who', ''))})"
    if kind == "illustration":
        row = script_photos.get(_photo_key(op))
        if not row:
            return None            # nothing reusable was found: the beat plays without it
        move = f", move={_q(op['move'])}" if op.get("move") in PICTURE_MOVES else ""
        points = [str(x) for x in op["points"] if str(x).strip()][:5] if isinstance(op.get("points"), list) else []
        listed = f", points={points!r}" if points and not _labels_of(op) else ""
        return (f"self.stage_image({_q(row['file'])}, {_q(op.get('caption') or '')}, credit={_q(_shown_credit(row))}"
                f"{_labels_arg(row)}{move}{listed})")
    if kind == "figure":
        figure = script_figures[str(op["id"])]
        caption = op.get("caption") or figure.get("caption") or ""
        credit = f", credit={_q(figure['credit'])}" if figure.get("credit") else ""
        return (f"self.figure({_q(figure['file'])}, {_q(caption)}, "
                f"where={_q(op.get('where', 'panel'))}{credit})")
    if kind == "unstage":
        return "self.clear_stage()"
    if kind == "gallery":
        shown = []
        for item in _gallery_items(op):
            if item["op"] == "figure":
                figure = script_figures.get(item["id"])
                if figure:
                    shown.append((figure["file"], item.get("caption") or figure.get("caption", ""), item.get("say", "")))
                continue
            row = script_photos.get(_photo_key(item))
            if row:
                shown.append((row["file"], item.get("caption") or "", item.get("say", "")))
        if not shown:
            return None
        if len(shown) == 1:
            # The book's own figure, alone: shown whole on the stage (figure), never cut to fill the screen.
            if any(item["op"] == "figure" for item in _gallery_items(op)):
                return f"self.figure({_q(shown[0][0])}, {_q(shown[0][1])}, where=\"stage\")"
            return f"self.stage_image({_q(shown[0][0])}, {_q(shown[0][1])})"
        items = ", ".join(f"({_q(f)}, {_q(c)}, {_q(w)})" for f, c, w in shown)
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        layout = f", layout={_q(op['layout'])}" if op.get("layout") in GALLERY_LAYOUTS else ""
        return f"self.gallery([{items}]{title}{layout})"
    if kind == "diagram" and op.get("_whole"):
        # Its picture, whole, its steps named and lit in it as they are said (stage_image's labels).
        title = op.get("title") or op.get("about") or ""
        return (f"self.stage_image({_q(op['_whole']['file'])}, {_q(str(title))}"
                f"{_labels_arg(op['_whole'])})")
    if kind == "diagram" and op.get("_parts"):
        # Drawn as one picture, cut into its parts (picture_flow).
        nodes = [{"id": str(n["id"]), "label": str(n.get("label") or n["id"])} for n in op["nodes"]]
        show = f", show={[str(x) for x in op['show']]!r}" if op.get("show") else ""
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        return (f"self.picture_flow({_q(str(op['id']))}, {nodes!r}, {op['_edges']!r}, {op['_parts']!r}"
                f"{title}{show})")
    if kind == "diagram":
        _edges_as_lists(op)
        nodes = [{"id": str(n["id"]), "label": str(n["label"]), **({"entity": str(n["entity"])} if n.get("entity") else {}),
                  **({"items": [str(i) for i in n["items"]][:5]} if n.get("items") else {}),
                  **({"anim": str(n["anim"])} if n.get("anim") else {}),
                  **({k: str(n[k]) for k in ("shape", "lane", "tone", "kind") if n.get(k)}),
                  **({"picture": _picture_value(n["picture"])} if _picture_value(n.get("picture")) else {})}
                 for n in op["nodes"]]
        edges = [[str(e[0]), str(e[1])] + ([str(e[2]) if len(e) > 2 and e[2] else ""] if len(e) > 2 else [])
                 + ([str(e[3])] if len(e) > 3 and e[3] and str(e[3]) != "solid" else []) for e in op.get("edges") or []]
        edges = [e[:2] if len(e) == 3 and not e[2] else e for e in edges]
        show = f", show={[str(x) for x in op['show']]!r}" if op.get("show") else ""
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        numbered = ", numbered=True" if op.get("steps") else ""
        return (f"self.diagram({_q(str(op['id']))}, {_q(op.get('kind', 'flow'))}, {nodes!r}, {edges!r}"
                f"{title}{show}{_diagram_motion(op)}{numbered})")
    if kind == "reveal":
        return f"self.reveal_nodes({_q(str(op['diagram']))}, {[str(x) for x in op['nodes']]!r})"
    if kind == "focus":
        return f"self.spotlight({_q(str(op['diagram']))}, {_q(str(op['node']))})"
    if kind == "define":
        entity = f", entity={_q(op['entity'])}" if op.get("entity") else ""
        return f"self.define({_q(op['term'])}, {_q(op['meaning'])}{entity})"
    if kind in STEM_OPS | WORK_OPS:
        return _stem_call(op)
    if kind == "question":
        choices = [str(c) for c in op.get("choices") or []][:5]
        answer = _answer_index(op) if choices else (str(op["answer"]) if op.get("answer") else None)
        extra = f", {choices!r}" if choices else ""
        extra += f", answer={answer!r}" if answer is not None else ""
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        return f"self.question({_q(op['text'])}{extra}{title})"
    if kind == "answer":
        return "self.answer()"
    if kind == "zoom":
        node = _q(str(op["node"])) if op.get("node") is not None else "None"
        return f"self.zoom({_q(str(op['diagram']))}, {node}, {float(op.get('scale') or 1.8)!r})"
    if kind == "option":
        return f"self.option({op.get('_index', 0)!r}" + (
            f", right={bool(op['right'])!r})" if op.get("right") is not None else ")")
    if kind == "compare":
        columns = [{"title": str(c["title"]), "points": [str(p) for p in (c.get("points") or [])][:4],
                    **({"entity": str(c["entity"])} if c.get("entity") else {})} for c in op["columns"]]
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        return f"self.compare_cards({columns!r}{title})"
    if kind == "graticule":
        axis = f"lat={float(op['lat']):g}" if op.get("lat") is not None else f"lon={float(op['lon']):g}"
        color = f", color={_colour(op.get('color'))}" if op.get("color") else ""
        label = f", label={_q(op['label'])}" if op.get("label") else ""
        return f"self.graticule({axis}{color}{label})"
    raise ValueError(kind)


script_figures: dict = {}


def _clean(value):
    """A value for the scene source: plain data only (dicts, lists, strings, numbers, booleans, None)."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _edges_as_lists(op: dict) -> None:
    """A diagram's edges as [from, to, label?, style?]: an edge written as {from, to, label, style} is put that way."""
    edges = op.get("edges")
    if not isinstance(edges, list):
        return
    out = []
    for e in edges:
        if isinstance(e, dict) and (e.get("from") is not None or e.get("to") is not None):
            e = [e.get("from"), e.get("to"), e.get("label") or "", e.get("style") or ""]
            while len(e) > 2 and not e[-1]:
                e.pop()
        out.append(e)
    op["edges"] = out


def _diagram_motion(op: dict) -> str:
    """A diagram's moving-picture switches as call arguments: animate (drawings that move) and flow (dots along
    its arrows), only when the script set them."""
    out = ""
    if op.get("animate") is not None:
        out += f", animate={bool(op['animate'])!r}"
    if op.get("flow") is not None:
        out += f", flow={bool(op['flow'])!r}"
    return out


def _stem_call(op: dict) -> str | None:
    kind = op["op"]
    key = str(op.get("id") or "")
    title = f", title={_q(op['title'])}" if op.get("title") else ""
    if kind == "work":
        box = ", box=True" if op.get("box") else ""
        return f"self.work({_q(key)}, {_clean(op['lines'])!r}{title}{box})"
    if kind == "draw":
        return None        # canonical_ops makes every draw op a picture; one met here had none made: left out
    extra = ""
    if op.get("given"):
        extra += f", given={[str(g) for g in op['given']]!r}"
    if op.get("find"):
        extra += f", find={_q(op['find'])}"
    if op.get("figure"):
        figure = {**op["figure"], "id": op["figure"].get("id") or f"{key}_figure"}
        # Its picture, made by the diagram model (lint asked for it); without one, the problem has no figure.
        row = script_photos.get(_photo_key(_drawn_picture(figure)))
        if row and row.get("file"):
            extra += f", figure={_clean({**figure, 'file': str(row['file'])})!r}"
    return f"self.problem({_q(key)}, {_q(op['text'])}{title}{extra})"


def board_chapter(script: dict, chapter: dict) -> bool:
    """A chapter taught on the board: the whole frame for its pictures, and a one-line key-point strip instead of
    a side panel of text. Every chapter is, whatever the style, unless the script sets "layout": "panel" (and then
    a chapter building STEM drawings still is). Its beats on the map show the map in their turn (_map_runs)."""
    if script.get("layout") == "panel":
        return any(op.get("op") in STEM_OPS | WORK_OPS | FREE_OPS for b in chapter.get("beats") or []
                   for op in b.get("do") or [])
    return True


def _still_timelines(script: dict) -> int:
    """A timeline is still: a timeline_zoom sim (a timeline that zooms from a century into a decade) becomes the
    timeline of its events, shown at once. Returns how many were changed."""
    changed = 0
    for chapter in script.get("chapters") or []:
        for beat in chapter.get("beats") or []:
            ops = beat.get("do") or []
            for k, op in enumerate(ops):
                if isinstance(op, dict) and op.get("op") == "sim" and op.get("kind") == "timeline_zoom":
                    params = {**(op.get("params") or {}), **op}
                    events = [list(e)[:2] for e in params.get("events") or [] if isinstance(e, (list, tuple)) and len(e) >= 2]
                    if len(events) >= 2:
                        ops[k] = {"op": "timeline", "events": events[:7],
                                  **({"title": op["title"]} if op.get("title") else {})}
                        changed += 1
    return changed


def _resolve_options(script: dict) -> None:
    """Each option op's choice as the index of the question up when it is said (lint has checked it names one)."""
    for chapter in script.get("chapters") or []:
        choices: list = []
        for beat in chapter.get("beats") or []:
            for op in beat.get("do") or []:
                if op.get("op") == "question":
                    choices = op.get("choices") or []
                elif op.get("op") == "option":
                    op["_index"] = _choice_index(choices, op.get("choice"))


def _diagram_parts(op: dict, figures: dict | None = None) -> list[str] | None:
    """The part ids of a picture an op puts up that "show" and reveal can name, or None when it has none."""
    kind = op.get("op")
    try:
        if kind == "diagram":
            return [str(n.get("id")) for n in op.get("nodes") or [] if isinstance(n, dict) and n.get("id")]
        if kind == "draw":
            return [str(p) for p in op.get("parts") or []]
        if kind == "figure":
            return [str(p) for p in ((script_figures if figures is None else figures).get(str(op.get("id")))
                                     or {}).get("parts") or []]
    except Exception:  # noqa: BLE001 -- a picture whose parts cannot be read is left as it is
        return None
    return None


def _complete_reveals(script: dict, notes: list[str] | None = None, figures: dict | None = None) -> int:
    """Parts of a picture its script never shows: a "show" that starts with some parts and reveals that never
    name the others left them off the board for good (a force never drawn, a diagram's last node missing).
    Each such part joins the picture's last reveal in its chapter, or, when nothing of it is ever revealed, the
    whole picture is drawn at once. Returns how many parts were brought back; says so in `notes`."""
    added = 0
    for c, chapter in enumerate(script.get("chapters") or []):
        pictures: dict[str, tuple[dict, list[str]]] = {}
        revealed: dict[str, set] = {}
        last_reveal: dict[str, dict] = {}
        for beat in chapter.get("beats") or []:
            for op in beat.get("do") or []:
                if not isinstance(op, dict):
                    continue
                if op.get("op") == "reveal":
                    key = str(op.get("diagram"))
                    revealed.setdefault(key, set()).update(str(n) for n in op.get("nodes") or [])
                    last_reveal[key] = op
                    continue
                # The picture an op puts up, under the name reveals use (a problem's figure is "<id>_figure").
                holders = [(op, op.get("id"))]
                if op.get("op") == "problem" and isinstance(op.get("figure"), dict):
                    holders.append((op["figure"], f"{op.get('id')}_figure"))
                for holder, key in holders:
                    if not key or holder.get("show") is None:
                        continue
                    parts = _diagram_parts(holder, figures)
                    if parts:
                        pictures[str(key)] = (holder, parts)
                        revealed.pop(str(key), None)
                        last_reveal.pop(str(key), None)
        for key, (holder, parts) in pictures.items():
            shown = {str(x) for x in holder.get("show") or []} | revealed.get(key, set())
            missing = [p for p in parts if p not in shown]
            if not missing:
                continue
            if key in last_reveal:
                last_reveal[key]["nodes"] = [*(last_reveal[key].get("nodes") or []), *missing]
                how = "join its last reveal"
            else:
                holder.pop("show", None)            # nothing of it is ever revealed: all of it, at once
                how = "are drawn with it from the start"
            added += len(missing)
            if notes is not None:
                notes.append(f"{FIXED}chapter {c + 1}: {key!r}: parts never revealed ({', '.join(missing)}) {how}")
    return added


def _shown_credit(row: dict) -> str:
    """The credit line under a picture: none for one the image model made (the closing credits name the model)."""
    return "" if row.get("source") == "generated" else str(row.get("credit") or "")


def _picture_row(op: dict) -> dict | None:
    """The fetched file behind a photo or illustration op (script_photos), or None."""
    row = script_photos.get(_photo_key(op))
    return row if row and row.get("file") and Path(str(row["file"])).is_file() else None


def pictures_used(script: dict) -> list[dict]:
    """Every web or library picture a compiled script shows, with its context, for the record of what a lecture
    used (app/lib/media.ts): its file; what it shows (the subject, the query, the title it was found by); where it
    came from (source, credit, licence, url); and where it is (the chapter, the beat, the line said over it, what it
    sits beside). Call after compile_script."""
    out: list[dict] = []
    chapters = script.get("chapters") or []

    def add(op: dict, ci: int, bi: int, role: str, beside: str | None = None):
        row = _picture_row(op)
        if not row:
            return
        chapter = chapters[ci - 1] if 0 < ci <= len(chapters) else {}
        beat = (chapter.get("beats") or [{}])[bi - 1] if 0 < bi <= len(chapter.get("beats") or []) else {}
        what = op.get("subject") or op.get("query") or op.get("image") or row.get("title") or ""
        out.append({
            "file": str(row["file"]),
            "kind": "illustration" if op.get("op") == "illustration" else "photo",
            "description": str(row.get("title") or what) if not op.get("subject") else str(op["subject"]),
            "found_by": {k: op[k] for k in ("subject", "query", "image") if op.get(k)},
            "source": {k: row[k] for k in ("source", "credit", "license", "artist", "url", "page", "id") if row.get(k)},
            "role": role,
            "context": {k: v for k, v in {
                "chapter": ci, "chapter_title": chapter.get("title"), "section": chapter.get("section"), "beat": bi,
                "line": beat.get("say"), "caption": op.get("caption"), "beside": beside}.items() if v not in (None, "")},
        })

    for ci, chapter in enumerate(chapters, 1):
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            for op in beat.get("do") or []:
                if not isinstance(op, dict):
                    continue
                kind = op.get("op")
                if kind in ("photo", "illustration"):
                    add(op, ci, bi, "shown on the stage")
                elif kind == "gallery":
                    for item in _gallery_items(op):
                        if item["op"] != "figure":
                            add(item, ci, bi, "in a gallery")
                elif kind == "diagram" and op.get("_file"):
                    # A flow drawn as one picture: the picture itself, and how it is revealed.
                    parts = op.get("_parts") or {}
                    steps = len(parts.get("nodes") or [])
                    arrows = sum(1 for e in parts.get("edges") or [] if e)
                    how = (f"a flow drawn as one picture: {steps} steps and {arrows} arrows drawn on in it as they are said"
                           if op.get("_parts") else "a flow drawn as one picture: shown whole, its steps lit as they are "
                           "said (they touch, so they cannot be drawn on one by one)")
                    chapter = chapters[ci - 1]
                    out.append({"file": str(op["_file"]), "kind": "illustration",
                                "description": str(op.get("about") or op.get("title") or op.get("id") or ""),
                                "found_by": {}, "source": {"source": "generated"}, "role": how,
                                "parts": [[str(n.get("label") or n.get("id")), *(row[1:] if row else [])]
                                          for n, row in zip(op.get("nodes") or [], parts.get("nodes") or [])],
                                "context": {"chapter": ci, "chapter_title": chapter.get("title"), "beat": bi,
                                            "line": beat.get("say")}})
                for where, spec in pictures_of(op):
                    fetch = _picture_fetch(spec) if isinstance(spec, dict) else None
                    if fetch:
                        add(fetch, ci, bi, f"beside a {kind} label", where)
    for ci, bi, op in AUTO_PICTURES:
        items = _gallery_items(op) if op.get("op") == "gallery" else [op]
        for item in items:
            if item.get("op") in ("photo", "illustration"):
                add(item, ci, bi, "chosen for the paragraph by the compiler")
    return out


def compile_script(script: dict, scene_class: str = "GeneratedScene", engine_path: str | None = None) -> str:
    """The Manim source for a script. Raises ValueError with the lint errors."""
    errors, _ = lint(script)
    if errors:
        raise ValueError("\n".join(errors))
    script_figures.clear()
    script_figures.update(script.get("figures") or {})
    USED_PICTURES.clear()
    AUTO_PICTURES.clear()
    STYLE_NOW["style"] = script.get("style")
    STYLE_NOW["auto_illustrations"] = bool(script.get("auto_illustrations"))
    _resolve_options(script)
    _unneeded_molecules(script, drop=True)
    _complete_reveals(script)
    # With rebuild_figures the book's diagrams are drawn in Manim, never dropped in as pictures.
    if script.get("place_figures", True) and not script.get("rebuild_figures"):
        place_figures(script)
    for chapter in script.get("chapters") or []:
        for beat in chapter.get("beats") or []:
            for op in beat.get("do") or []:
                if isinstance(op, dict):
                    op.pop("from_figure", None)          # a note for the checks, not an argument to draw with
                    if op.get("op") == "figure":
                        op.pop("photo", None)
    style = script.get("style", "atlas")
    region = script.get("region")
    chapters = script["chapters"]
    sections = ["Introduction"] + [c["title"] for c in chapters]
    if script.get("recap"):
        sections.append("Recap")
    # MapLecture's layout (the stage or map on the left, the panel on the right)
    # serves a lecture with no region too; it only draws a map when told to.
    base = "MapLecture"

    out = [
        f'"""{script.get("title", "Lecture")}: compiled from a beat script by harness/lecture/compile_lecture.py."""',
        "import os",
        "import sys",
        "",
        f"os.environ.setdefault(\"LECTURE_STYLE\", {_q(style)})",
        f"os.environ.setdefault(\"LECTURE_ART\", {_q(str(script.get('art') or 'auto'))})",
    ]
    if engine_path:
        out.append(f"sys.path.insert(0, {_q(engine_path)})")
    out += [
        "from manim import *  # noqa: E402,F403",
        "from pocket_lecture import *  # noqa: E402,F403",
    ]
    if script.get("places"):
        # The lecture's own places (the map agent's), for every place, area and range the scene looks up.
        home = (region or {}).get("country")
        out.append(f"set_places({_clean(script['places'])!r}, {_q(home) if home else 'None'})")
    out += [
        "",
        "",
        f"class {scene_class}({base}):",
    ]
    if region:
        fields = ", ".join(f"{k}={_q(v)}" for k, v in region.items() if v)
        out.append(f"    REGION = dict({fields})")
    out.append(f"    SECTIONS = [{', '.join(_q(s) for s in sections)}]")
    emblem = _emblem_file(script)
    if emblem:
        out.append(f"    EMBLEM = {_q(emblem)}")
    out += ["", "    def construct(self):"]
    if script.get("title"):
        intro = script.get("intro") or f"{script['title']}. {script.get('sub', '')}".strip()
        out.append(f"        self.title_slide({_q(script['title'])}, {_q(script.get('sub', ''))}, narration={_q(intro)})")
    for index, chapter in enumerate(chapters, 1):
        # On one line: a title with a line break in it would carry the rest of the title out of the comment.
        out += ["", f"        # {index:02d}  {' '.join(str(chapter['title']).split())}"]
        out.append(f"        self.chapter({index}, {_q(chapter['title'])}, {_q(chapter.get('sub', ''))}, "
                   f"{_q(chapter.get('narration') or chapter['title'])})")
        fills = auto_visuals(chapter, genre=script.get("genre")) if script.get("auto_visuals", True) else []
        AUTO_PICTURES.extend((index, bi + 1, fill) for bi, fill in enumerate(fills) if fill)
        # Every chapter is on the board (or its side panel); the map comes in for the runs of beats on it.
        on_board = board_chapter(script, chapter)
        runs = {first: last for first, last in _map_runs(chapter, bool(region), fills)}
        if 0 not in runs:
            out.append("        self.board()" if on_board else "        self.add_panel()")
        map_until = None                        # the beat the map's run ends at, while the map is up
        staged = False
        parts_named: dict[str, dict] = {}       # a diagram's part ids -> their names, for the words that say them
        asked: list[str] = []                   # the choices of the question up
        # A paragraph ends with a longer pause, so an idea settles before the next begins.
        closing = {group[-1] for group in paragraphs(chapter.get("beats") or [])}
        for bi, beat in enumerate(chapter.get("beats") or []):
            if map_until is not None and bi == map_until:
                out.append(f"        self.map_away(board={on_board})")
                map_until, staged = None, False
            if bi in runs:
                # Fitted to the places this run shows (or the whole map when they are all over it), across the
                # whole frame unless it puts facts in a side panel; every place it will mark spoken for now, so
                # no label set early covers a later marker's dot.
                run = _run_of(chapter, bi, runs[bi])
                box = _chapter_frame(run, script.get("region"))
                spots = _chapter_spots(run)
                wide = not _fills_panel(run, script.get("figures"))
                places = f", places=[{', '.join(spots)}]" if spots else ""
                out.append(f"        self.map_in({box!r}{places}, wide={wide})")
                map_until, staged = runs[bi], False
            if beat.get("_spoken_as"):
                # The words each part of this line's pictures lands on (its "on"), by the part's name (anchors).
                out.append(f"        self.spoken_as({beat['_spoken_as']!r})")
            ops = beat_order(list(beat.get("do") or []))
            free = next((op for op in ops if op.get("op") == "manim"), None)
            if free is not None:
                # Drawn by the model's own Manim (free_check.py, stem.BoardMixin.free).
                import free_check

                pad = "PARAGRAPH_PAD" if bi in closing else "BEAT_PAD"
                if _pause(beat):
                    pad = f"{pad} + {_pause(beat):g}"
                elif bi not in closing:
                    pad = "None"                        # the beat's own hold (pocket_lecture.beat_pad)
                # "left": the figure is drawn in the board's left half, so a working or a card stays beside it
                # while later blocks explain it (stem.BoardMixin.free).
                area = ', area="left"' if free.get("area") == "left" else ""
                out.append(f"        self.free({_q(free_check.free_key(free, index))}, {_q(beat['say'])}, "
                           f"{_q(free['code'])}, pad={pad}{area})")
                staged = True
                continue
            if bi < len(fills) and fills[bi]:
                ops.append(fills[bi])
            points_at_map = any(op.get("op") in MAP_OPS or (op.get("op") == "icon" and _icon_spots(op)) for op in ops)
            calls = []
            if staged and points_at_map:
                calls.append("self.clear_stage()")      # back to the map
                staged = False
            for op in ops:
                if op.get("op") in ("photo", "illustration") and op.get("where", "stage") == "stage" or \
                        op.get("op") == "figure" and op.get("where") == "stage" or op.get("op") in KIT_OPS | BUILD_OPS:
                    staged = True
                if op.get("op") in STEM_OPS | WORK_OPS:
                    staged = True
                if op.get("op") == "unstage":
                    staged = False
            # Each picture is built through self.safe: one the engine cannot draw is left out with its reason and
            # its beat, not the whole lecture stopped. With it, the words it shows: it starts as they are said.
            for op in ops:
                if op.get("op") in ("diagram", "draw"):
                    parts_named[str(op.get("id"))] = _diagram_labels(op)
                if op.get("op") == "question":
                    asked = [str(c) for c in op.get("choices") or []]
                call = _op_call(op)
                if call and call.startswith("*"):
                    # Spread into the beat's calls (the dim op's animations): "lambda: *x" does not parse.
                    calls.append(call)
                elif call:
                    what = f"chapter {index} beat {bi + 1} {op.get('op')}"
                    said = _op_said(op, parts_named, asked)
                    said = (f", said={_q(said)}" if isinstance(said, str) else f", said=[{', '.join(_q(w) for w in said)}]") \
                        if said else ""
                    calls.append(f"self.safe(lambda: {call}, {_q(what)}{said})")
            args = "".join(f",\n                  {call}" for call in calls)
            rt = f", rt={float(beat['rt']):g}" if beat.get("rt") else ""
            pad = "PARAGRAPH_PAD" if bi in closing else ""
            if _pause(beat):
                pad = f"{pad or 'BEAT_PAD'} + {_pause(beat):g}"
            pad = f", pad={pad}" if pad else ""
            out.append(f"        self.beat({_q(beat['say'])}{args}{rt}{pad})")
            for op in ops:
                if op.get("op") == "question" or op.get("op") == "problem" and op.get("think"):
                    out.append(f"        self.think({_think_seconds(op):g})")
        out.append("        self.outro_fade()")
    if script.get("recap"):
        out += ["", "        # Recap"]
        points = ", ".join(f"({_q(h)}, {_q(b)})" for h, b in script["recap"])
        out.append(f"        self.section({len(sections) - 1})")
        out.append(f"        self.recap([{points}])")
    uses_icons = any(op.get("op") in ("icon", "illustration") for c in chapters for b in c.get("beats") or []
                     for op in b.get("do") or []) or any("illustration" in line for line in out)
    # The web's photos shown in place of the book's own (figures.lookalike) are credited with the others.
    web_figures = [{"title": f.get("caption") or fid, "credit": f["credit"]} for fid, f in script_figures.items()
                   if f.get("web") and f.get("credit")]
    # Only the pictures this lecture shows (their files are in its source): the table of pictures found lives as long
    # as the process, and a lecture compiled after another got the last one's credits.
    drawn = "\n".join(out)
    shown = [row for row in script_photos.values() if row.get("file") and str(row["file"]) in drawn]
    if script.get("credits") or uses_icons or shown or web_figures:
        import images

        line = script.get("credits") or ("Map data: Natural Earth · Animation: Manim" if region else "Animation: Manim")
        photos = images.credit([*shown, *web_figures])
        out.append(f"        self.credits({_q(line)}" + (f", extra={_q(photos)}" if photos else "") + ")")
    source = "\n".join(out) + "\n"
    try:
        compile(source, "scene.py", "exec")
    except SyntaxError as error:
        # Text the script carried broke out of its place in the code: said here, not by the build an hour later.
        raise ValueError(f"the compiled scene does not parse, line {error.lineno}: {error.msg}: "
                         f"{(error.text or '').strip()[:160]}") from error
    return source


def prefetch_pictures(script: dict, scene_class: str = "GeneratedScene") -> None:
    """Every picture the script will ask the image models for, made several at once before the compile: a first
    pass through the checks and the code with the pictures only noted down (genimage.collecting), then made in
    parallel (genimage.prefetch); the real pass then finds each made. Without it they were made one after another,
    10-40 s each. PANIM_IMAGE_PARALLEL=1 turns it off."""
    import copy

    import genimage

    if genimage.parallel() <= 1 or not genimage.enabled():
        return
    check = os.environ.get("PANIM_MANIM_CHECK")
    os.environ["PANIM_MANIM_CHECK"] = "off"           # the Manim blocks are checked in the real pass
    # What the compile keeps of the pictures it found: the noting-down pass's stand-ins must not stay there.
    photos, figures = dict(script_photos), dict(script_figures)
    try:
        with genimage.collecting() as requests:
            draft = copy.deepcopy(script)
            try:
                if not lint(draft)[0]:
                    compile_script(draft, scene_class)
            except Exception:  # noqa: BLE001 -- the real pass reports it
                pass
    finally:
        script_photos.clear()
        script_photos.update(photos)
        script_figures.clear()
        script_figures.update(figures)
        if check is None:
            os.environ.pop("PANIM_MANIM_CHECK", None)
        else:
            os.environ["PANIM_MANIM_CHECK"] = check
    genimage.prefetch(requests)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("script")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true", help="lint only; print errors and warnings as JSON")
    ap.add_argument("--json", action="store_true",
                    help="print {source, errors, warnings} as one JSON object, for the harness app")
    ap.add_argument("--class", dest="scene_class", default="GeneratedScene")
    ap.add_argument("--min-minutes", type=float, default=None,
                    help="an error when the script's estimated running time is well under this")
    ap.add_argument("--min-questions", type=int, default=None,
                    help="with --min-minutes: an error when the lecture asks the class fewer questions")
    ap.add_argument("--min-examples", type=int, default=None,
                    help="with --min-minutes: an error when fewer beats give an example")
    ap.add_argument("--min-problems", type=int, default=None,
                    help="with --min-minutes: an error when the lecture works fewer long problems")
    ap.add_argument("--pictures-only", action="store_true",
                    help="only make the pictures the script asks for (into the cache), several at once, and print "
                         "what was made as JSON: a section's pictures made in the background while the lecture is "
                         "still being written")
    ap.add_argument("--embed-path", action="store_true",
                    help="put this engine's folder on sys.path in the output, for running `manim` directly")
    args = ap.parse_args()
    text = sys.stdin.read() if args.script == "-" else Path(args.script).read_text()
    try:
        script = json.loads(text)
        if not isinstance(script, dict):
            raise ValueError("the script must be a JSON object")
    except ValueError as error:
        if args.json:
            print(json.dumps({"source": None, "errors": [f"not a JSON beat script: {error}"], "warnings": []}))
            return 1
        raise
    if args.pictures_only:
        import genimage

        if genimage.parallel() > 1:
            prefetch_pictures(script, args.scene_class)
        else:                                          # one at a time: the compile itself asks for them
            compile_script(script, args.scene_class) if not lint(script)[0] else None
        print(json.dumps({"generated": genimage.MADE, "images": genimage.report(), "image_spans": genimage.SPANS,
                          "prefetch": genimage.PREFETCHED, "calls": genimage.CALLS}))
        return 0
    import time as _time

    phases: dict[str, float] = {}
    mark = _time.time()
    if args.json or not args.check:
        prefetch_pictures(script, args.scene_class)
    phases["pictures"], mark = round(_time.time() - mark, 2), _time.time()
    errors, warnings = lint(script, args.min_minutes, args.min_questions, args.min_examples, args.min_problems)
    phases["checks"], mark = round(_time.time() - mark, 2), _time.time()
    if args.json:
        source = None if errors else compile_script(script, args.scene_class)
        phases["code"] = round(_time.time() - mark, 2)
        phases["manim_checks"] = round(sum((b - a) for a, b, *_ in __import__("free_check").SPANS) / 1000, 2)
        print(json.dumps({"source": source, "errors": errors, "warnings": warnings,
                          "minutes": round(estimate_minutes(script), 2),
                          "pictures": pictures_used(script) if source else [],
                          # Pictures the image model made during this compile, and what each cost (genimage.py).
                          "generated": __import__("genimage").MADE,
                          # What the script asked of the image model, and why any picture was not made.
                          "images": __import__("genimage").report(),
                          # When the image models and the Manim checks were at work (ms since the epoch).
                          "image_spans": __import__("genimage").SPANS,
                          "probe_spans": __import__("free_check").SPANS,
                          "prefetch": __import__("genimage").PREFETCHED,
                          # Where the compile's time went, and each model request it made, for the timing log.
                          "phases": phases, "calls": __import__("genimage").CALLS}))
        return 1 if errors else 0
    if args.check:
        print(json.dumps({"errors": errors, "warnings": warnings}))
        return 1 if errors else 0
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    for warning in warnings:
        print("warning:", warning, file=sys.stderr)
    source = compile_script(script, args.scene_class, str(HERE) if args.embed_path else None)
    if args.out:
        Path(args.out).write_text(source)
    else:
        sys.stdout.write(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
