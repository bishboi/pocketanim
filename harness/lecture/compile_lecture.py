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
MAP_OPS = {"marker", "river", "path", "arrow", "state", "dim", "graticule", "journey"}
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
MAX_PAUSE = 8.0                       # a beat's "pause", at most


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
    """Every point list and point in an op, at any depth (a sketch's items, a graph's items, a problem's figure),
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


def _point_problems(op: dict) -> list[str]:
    """A curve or polygon with fewer than two points, at any depth: nothing to draw (Manim cannot)."""
    out = []
    stack = [op]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("type") in ("curve", "polygon") and len([p for p in item.get("points") or []
                                                                  if isinstance(p, list) and len(p) == 2]) < 2:
                out.append(f"its {item.get('type')} {item.get('id') or ''} needs at least two points, as [[x, y], ...]")
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return out


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
    if script.get("style", "atlas") not in STYLES:
        errors.append(f"style must be one of {', '.join(STYLES)}")
    if str(script.get("art") or "auto").lower().replace("watercolor", "watercolour") not in ARTS:
        errors.append(f"art must be one of {', '.join(ARTS)}")
    if script.get("region") and not isinstance(script["region"], dict):
        errors.append('region must be an object, e.g. {"country": "India", "view": "ind"}, or left out for no map')
        script = {**script, "region": None}
    has_map = bool(script.get("region"))
    chapters = script.get("chapters") or []
    places: list[tuple[str, str]] = []
    icon_names: list[tuple[str, str]] = []
    photos: list[tuple[str, dict]] = []
    if not chapters:
        errors.append("a lecture needs at least one chapter")
    for ci, chapter in enumerate(chapters, 1):
        where = f"chapter {ci}"
        diagrams: dict = {}          # diagram id -> node ids, for the chapter's reveal and focus
        # A chapter card without its own narration says the chapter's title: a missing line cost a whole turn.
        if not chapter.get("title"):
            errors.append(f"{where}: missing title")
        used = 0.0
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            at = f"{where} beat {bi}"
            say = str(beat.get("say") or "").strip()
            if not say:
                errors.append(f"{at}: no narration ('say')")
            elif len(say) > 184:
                warnings.append(f"{at}: the caption runs past two lines ({len(say)} characters); split the beat")
            ops = beat.get("do") or []
            _normalise_points(ops)
            for op in ops:
                if isinstance(op, dict):
                    errors.extend(f"{at}: {kind_problem}" for kind_problem in _point_problems(op))
            if len(ops) > 5:
                warnings.append(f"{at}: {len(ops)} operations in one beat; the eye cannot follow more than about four")
            for op in ops:
                kind = op.get("op")
                if kind not in {"panel", "fact", "stat", "bars", "clear", "icon", "figure", "photo",
                                "illustration"} | KIT_OPS | MAP_OPS | BUILD_OPS | STEP_OPS | WORK_OPS | FREE_OPS:
                    errors.append(f"{at}: unknown op {kind!r}")
                    continue
                drawn_map = map_drawn_by(op)
                if drawn_map:
                    errors.append(f"{at}: {drawn_map}")
                    continue
                for where, spec in pictures_of(op):
                    problem = _picture_problem(spec, script.get("figures") or {})
                    if problem:
                        errors.append(f"{at}: {where}: {problem}")
                    elif _picture_fetch(spec):
                        photos.append((at, _picture_fetch(spec)))
                    elif spec.get("draw") and script.get("drawn") and not spec.get("svg"):
                        warnings.append(f"{at}: {where}: the picture {spec['draw']!r} could not be drawn"
                                        f"{': ' + str(spec['_draw_error']) if spec.get('_draw_error') else ''}; "
                                        "its words are shown alone")
                if kind == "manim":
                    if not isinstance(op.get("code"), str) or not op["code"].strip():
                        errors.append(f"{at}: a manim op needs its code: the Python that draws this beat")
                    if len(ops) > 1:
                        errors.append(f"{at}: a manim beat carries only its manim op; draw the rest in its code, "
                                      "or put the other ops on beats of their own")
                    if _map_chapter(chapter, has_map):
                        errors.append(f"{at}: a manim beat draws on the board; give its chapter \"map\": false")
                    continue
                if kind in BUILD_OPS | STEP_OPS | WORK_OPS:
                    problem = _build_problem(op, diagrams, script.get("figures") or {})
                    if problem:
                        errors.append(f"{at}: {problem}")
                    if kind == "gallery" and not problem:
                        photos.extend((at, item) for item in _gallery_fetches(op))
                if kind in MAP_OPS and not has_map:
                    errors.append(f"{at}: '{kind}' needs a map; give the script a region")
                if kind in MAP_OPS and chapter.get("map") is False:
                    errors.append(f"{at}: '{kind}' in a chapter with map=false")
                need = {"panel": ["title"], "fact": ["text"], "stat": ["value", "label"], "bars": ["items"],
                        "river": ["name"], "state": ["name"], "path": ["points"], "arrow": ["points"]}
                for field in need.get(kind, []):
                    if not op.get(field):
                        errors.append(f"{at}: '{kind}' needs {field}")
                if kind == "journey":
                    stops = op.get("stops")
                    if not isinstance(stops, list) or len(stops) < 2:
                        errors.append(f"{at}: 'journey' needs stops: two or more places, in order "
                                      "([\"Sabarmati\", \"Dandi\"]) or [lon, lat] pairs")
                    else:
                        bad = [x for x in stops if not (isinstance(x, str) or (isinstance(x, (list, tuple))
                               and len(x) == 2 and all(isinstance(v, (int, float)) for v in x)))]
                        if bad:
                            errors.append(f"{at}: journey stop {bad[0]!r} is a place name or [lon, lat]")
                        elif has_map:
                            places.extend((at, str(x)) for x in stops if isinstance(x, str))
                if kind == "marker" and not (op.get("place") or op.get("lonlat")):
                    errors.append(f"{at}: 'marker' needs place or lonlat")
                elif kind == "marker" and op.get("place") and has_map:
                    places.append((at, str(op["place"])))
                if kind == "icon":
                    if not op.get("name"):
                        errors.append(f"{at}: 'icon' needs name")
                    else:
                        icon_names.append((at, str(op["name"])))
                    spots = _icon_spots(op)
                    if spots and not has_map:
                        errors.append(f"{at}: an icon at a place needs a map; give the script a region, or drop place")
                    elif spots:
                        places.extend((at, str(p)) for p in spots if isinstance(p, str))
                if kind == "photo":
                    if not (op.get("image") or op.get("query") or op.get("subject")):
                        errors.append(f"{at}: 'photo' needs image (a Commons title from find_image), subject "
                                      "(a person, movement, monument or place, by its English name) or query")
                    else:
                        photos.append((at, op))
                if kind in KIT_OPS:
                    problem = _kit_problem(op)
                    if problem:
                        errors.append(f"{at}: {problem}")
                if kind == "illustration":
                    if not (op.get("query") or op.get("image")):
                        errors.append(f"{at}: 'illustration' needs query (what it should show, in English: "
                                      "\"water cycle diagram\") or image (a title from find_illustration)")
                    else:
                        photos.append((at, op))
                drawn_op = op if kind == "draw" else (op.get("figure") if kind == "problem" and isinstance(
                    op.get("figure"), dict) and op["figure"].get("op") == "draw" else None)
                if drawn_op is not None and script.get("drawn") and not drawn_op.get("svg"):
                    # The drawing step ran (harness/app/lib/drawings.ts) and could not make this one.
                    errors.append(f"{at}: the picture {drawn_op.get('id') or op.get('id')!r} could not be drawn"
                                  f"{': ' + str(drawn_op['_draw_error']) if drawn_op.get('_draw_error') else ''}. "
                                  "Describe it again more simply (fewer things, each named), or show it another way.")
                if kind == "figure":
                    figure = (script.get("figures") or {}).get(str(op.get("id")))
                    if not figure:
                        known = ", ".join(sorted(script.get("figures") or {})) or "none (no document was uploaded)"
                        errors.append(f"{at}: no figure {op.get('id')!r}; the figures are: {known}")
                    elif figure.get("svg") and not op.get("photo"):
                        # Drawn as an SVG (the model redrew the book's diagram): shown with its parts to reveal.
                        if not Path(str(figure["svg"])).is_file():
                            errors.append(f"{at}: figure {op.get('id')!r} has no SVG file")
                        parts = [str(x) for x in figure.get("parts") or []]
                        unknown = [str(x) for x in op.get("show") or [] if str(x) not in parts]
                        if unknown:
                            errors.append(f"{at}: figure {op.get('id')!r} has no part {unknown[0]!r} "
                                          f"(its parts: {', '.join(parts) or 'none'})")
                        diagrams[str(op.get("id"))] = parts
                    elif not Path(str(figure.get("file", ""))).is_file():
                        errors.append(f"{at}: figure {op.get('id')!r} has no image file")
                    elif script.get("rebuild_figures") and not op.get("photo"):
                        errors.append(f"{at}: figure {op.get('id')!r} is the book's picture shown as it is. Build it in "
                                      "Manim instead (sketch, preset, graph, diagram, compare; draw only what those "
                                      "cannot show well), with "
                                      f"\"from_figure\":\"{op.get('id')}\" on that op. Only a photograph may be shown as "
                                      "it is, with \"photo\": true.")
                if kind == "graticule" and op.get("lat") is None and op.get("lon") is None:
                    errors.append(f"{at}: 'graticule' needs lat or lon")
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
    errors += _unknown_places(places, (script.get("region") or {}).get("country"))
    errors += _unknown_icons(icon_names)
    errors += _unfetched_photos(photos, script.get("genre"), script.get("style"))
    warnings += [f"{at}: no reusable illustration for {op.get('image') or op.get('query')!r}; it is left out "
                 "(try another description with find_illustration)" for at, op in photos
                 if op.get("op") == "illustration" and _photo_key(op) not in script_photos]
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
    errors += _web_pictures_problem(script)
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
                      "by teaching in more depth: after each statement from the content, explain what it means in "
                      "easy words, give two or three examples from daily life, explain every hard term, add what "
                      "a student should also know beyond the book, say the key idea again in other words, and "
                      "ask the class a question. Keep every existing beat that is right.")
    return errors, warnings


script_photos: dict = {}


def _photo_key(op: dict) -> str:
    if op.get("op") == "illustration":
        return f"illustration|{op.get('image') or ''}|{op.get('query') or ''}"
    return f"{op.get('image') or ''}|{op.get('query') or ''}|{op.get('subject') or ''}"


# ---------------- pictures in diagrams, timelines and map labels ----------------
# A diagram's node, a timeline's event, a map marker (and a journey's stop) may carry a picture beside its words:
#   {"subject": "Mahatma Gandhi"}     Wikipedia's picture of a person, place or thing (a photo from the web)
#   {"query": "steam locomotive"}     a photo found by these words (from the web)
#   {"illustration": "water cycle"}   an educational illustration (from the web)
#   {"figure": "fig3"}                one of the book's figures (its SVG drawing when it has one)
#   {"draw": "A steam engine, side view"}   drawn for the lecture as an SVG (drawings.ts)
#   {"entity": "cow"}                 a drawing from the library
PICTURE_KEYS = ("subject", "query", "illustration", "figure", "draw", "entity")


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
        return ("a picture is one of {\"subject\": \"<a person, place or thing>\"}, {\"query\": \"<photo search>\"}, "
                "{\"illustration\": \"<what it shows>\"}, {\"figure\": \"<book figure id>\"}, "
                "{\"draw\": \"<what to draw>\"} or {\"entity\": \"<library drawing>\"}")
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
    if spec.get("illustration"):
        return {"op": "illustration", "query": str(spec["illustration"]), "optional": True}
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


def _picture_value(spec) -> tuple | None:
    """A picture as the engine takes it: ("image", file), ("svg", file), ("entity", name), or None (not found or
    not drawn: the words stand alone)."""
    value = _picture_found(spec)
    return value if value is None or value[0] == "entity" or Path(value[1]).exists() else None


def _picture_found(spec) -> tuple | None:
    if not isinstance(spec, dict):
        return None
    if spec.get("entity"):
        return ("entity", str(spec["entity"]))
    if spec.get("draw"):
        return ("svg", str(spec["svg"])) if spec.get("svg") else None
    if spec.get("figure"):
        figure = script_figures.get(str(spec["figure"])) or {}
        if figure.get("svg"):
            return ("svg", str(figure["svg"]))
        return ("image", str(figure["file"])) if figure.get("file") else None
    fetch = _picture_fetch(spec)
    row = script_photos.get(_photo_key(fetch)) if fetch else None
    return ("image", str(row["file"])) if row and row.get("file") else None


def _picture_arg(spec) -> str:
    return repr(_picture_value(spec))


def _unfetched_photos(photos: list[tuple[str, dict]], genre: str | None = None, style: str | None = None) -> list[str]:
    """Download every photo now (cached), so the scene draws local files; report the ones that failed."""
    if not photos:
        return []
    import images

    out = []
    for at, op in photos:
        key = _photo_key(op)
        if key in script_photos:
            continue
        if op.get("op") == "illustration":
            row = images.fetch(op.get("image"), illustration=op.get("query"), genre=genre, style=style) \
                if images.enabled() else None
            if row:
                script_photos[key] = row
            # else: dropped at compile, and said as a warning (see lint): a missing diagram is no reason to stop
            continue
        row = images.fetch(op.get("image"), op.get("query"), op.get("subject")) if images.enabled() else None
        if row:
            script_photos[key] = row
        elif op.get("optional"):
            continue
        elif not images.enabled():
            out.append(f"{at}: internet photos are off here; use a document figure, a diagram you draw (process, "
                       "timeline, equation, plot) or drop the photo")
        else:
            what = op.get("image") or (f"subject {op['subject']!r}" if op.get("subject") else f"query {op.get('query')!r}")
            out.append(f"{at}: no reusable photo for {what}; use find_image and pick a title it returns, "
                       "or show an illustration (find_illustration) instead")
    return out


KIT_OPS = {"molecule", "equation", "plot", "process", "timeline", "quote"}
# Built on the stage: several pictures at once, diagrams of SVG drawings, a word and its meaning, a comparison,
# a question for the class; and for mathematics and the sciences (stem.py): labelled sketches, the physics
# presets (incline, pulley...), graphs and long problems.
from stem import PRESETS  # noqa: E402

STEM_OPS = {"draw", "sketch", "graph", "problem"} | set(PRESETS)
# Live pictures (live.py): a simulation that moves while its line is said, a counting number.
LIVE_OPS = {"sim", "counter"}
BUILD_OPS = {"gallery", "diagram", "define", "compare", "question"} | STEM_OPS | LIVE_OPS
# A worked solution: lines added beside the figure on the stage (or on a problem's solution side).
WORK_OPS = {"work"}
# Subjects taught on the board (no side panel) unless the script says otherwise.
BOARD_GENRES = {"physics", "chemistry", "mathematics"}
# The next step of what is already on the stage: more of a diagram, a ring around one of its nodes, the answer
# to the question, one of its choices marked right or wrong while it is explained, a diagram set moving.
STEP_OPS = {"reveal", "focus", "answer", "option", "motion", "trace", "sweep", "zoom"}
QUESTION = "?question"       # the key a chapter's question goes under among its diagrams, for lint
DIAGRAM_KINDS = {"flow", "flowchart", "cycle", "tree", "hub", "categories", "steps", "hierarchy"}
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
    """A map asked of anything but the map (mapguard): an SVG drawing, a block of Manim, an illustration or photo
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


def _gallery_items(op: dict) -> list[dict]:
    """A gallery's items as fetchable operations: {op: photo, subject|image|query} or {op: illustration, query}
    or {op: figure, id}; each keeps its caption."""
    out = []
    for item in list(op.get("items") or [])[:4]:
        if not isinstance(item, dict):
            continue
        caption = item.get("caption") or item.get("subject") or ""
        if item.get("figure"):
            out.append({"op": "figure", "id": str(item["figure"]), "caption": caption})
        elif item.get("illustration"):
            out.append({"op": "illustration", "query": item["illustration"], "caption": caption})
        elif item.get("subject") or item.get("image") or item.get("query"):
            out.append({"op": "photo", **{k: item[k] for k in ("subject", "image", "query") if item.get(k)},
                        "caption": caption})
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
            return ("'gallery' needs items: 2-4 of {subject|image|query|figure|illustration, caption} "
                    "(people, communities, places)")
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
        # A hierarchy (tree, categories) goes as deep and wide as a classification needs; a flowchart up to 16.
        tree_kind = op.get("kind", "flow") in ("tree", "categories", "hierarchy")
        most = 20 if tree_kind else 16 if op.get("kind", "flow") in ("flow", "flowchart") else 9
        if not 2 <= len(nodes) <= most or not all(isinstance(n, dict) and n.get("id") and n.get("label") for n in nodes):
            return (f"'diagram' needs 2-{most} nodes, each {{id, label, entity?, items?"
                    + (", shape?, lane?" if most == 16 else "") + "}")
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
        import animsvg

        motions = set(animsvg.MOTIONS) | {"none", "auto"}
        wrong = [n for n in nodes if n.get("anim") is not None and str(n["anim"]) not in motions]
        if wrong:
            return (f"diagram node {wrong[0]['id']!r}: anim is one of {', '.join(sorted(motions))} "
                    "(leave it out and the drawing moves the way its thing does, if it does)")
        diagrams[key] = ids
    if kind in STEM_OPS | WORK_OPS:
        return _stem_problem(op, diagrams)
    if kind in LIVE_OPS:
        return _live_problem(op, diagrams)
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
        if kind in ("trace", "sweep"):
            return _graph_step_problem(op, key, diagrams)
        if kind == "zoom":
            node = op.get("node")
            if node is not None and str(node) not in diagrams[key]:
                return f"zoom node: no part {node!r} in {key!r} ({', '.join(diagrams[key]) or 'none named'})"
            if op.get("scale") is not None and not 1.1 <= float(op["scale"]) <= 3:
                return "zoom scale is between 1.1 and 3 (how much closer)"
            return None
        if kind == "motion":
            import stem

            return stem.motion_problem(diagrams.get(f"?kind:{key}"), list(diagrams[key]), op)
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


def _graph_step_problem(op: dict, key: str, diagrams: dict) -> str | None:
    """A trace (a point riding a curve) or a sweep (a curve redrawn as a parameter changes) on a graph."""
    import pocket_lecture as pl

    kind = op["op"]
    if diagrams.get(f"?kind:{key}") != "graph":
        return f"'{kind}' works on a graph: {key!r} is not one drawn in this chapter"
    if kind == "trace":
        curve = op.get("curve")
        if curve is not None and str(curve) not in diagrams.get(f"?curves:{key}", []):
            return (f"trace curve: {curve!r} is not a curve of {key!r} "
                    f"({', '.join(diagrams.get(f'?curves:{key}', [])) or 'give its curve an id'})")
        if not diagrams.get(f"?curves:{key}"):
            return f"trace needs a curve on {key!r} (an item {{\"kind\": \"curve\", \"id\": ...}})"
        if op.get("readout") not in (None, "value", "slope", "area"):
            return "trace readout is value, slope or area"
        return None
    param = str(op.get("param") or "a")
    if not re.fullmatch(r"[a-zA-Z]\w{0,7}", param) or param == "x":
        return "sweep param is a short name other than x (\"a\", \"k\")"
    try:
        f = pl.safe_function(str(op.get("expr") or ""), (param,))
        f(1.0, **{param: 1.0})
    except Exception as error:  # noqa: BLE001 -- the reason goes back to the model
        return f"sweep expr must be an expression in x and {param} (\"{param}*x^2\"): {error}"
    for end in ("from", "to"):
        if not isinstance(op.get(end, 0), (int, float)):
            return f"sweep {end} must be a number"
    return None


def _live_problem(op: dict, diagrams: dict) -> str | None:
    import live

    key = str(op.get("id") or "")
    if not key:
        return f"'{op['op']}' needs an id"
    if op["op"] == "sim":
        problem = live.sim_problem(op)
        if problem:
            return problem
    else:
        for end in ("from", "to"):
            if not isinstance(op.get(end), (int, float)):
                return f"counter needs {end}: a number (it counts from one to the other over the line)"
        if op.get("style", "bar") not in ("bar", "dial", "number"):
            return "counter style is bar, dial or number"
    diagrams[key] = []
    diagrams[f"?kind:{key}"] = op["op"]
    return None


PART_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,23}")


def _draw_problem(op: dict) -> str | None:
    """A picture to be drawn as an SVG from its description (harness/app/lib/drawings.ts): what it shows, its
    parts (the ids its <g> groups get, for reveal and focus), what moves in it, if anything."""
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
    """What stops a sketch, preset, graph, worked solution or problem; records the parts reveal can show."""
    import stem

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
        if not key:
            return "'draw' needs an id (reveal and focus refer to it)"
        problem = _draw_problem(op)
        if problem:
            return problem
        diagrams[key] = [str(p) for p in op["parts"]]
        diagrams[f"?kind:{key}"] = "draw"
        return None
    if kind == "problem":
        if not str(op.get("text") or "").strip():
            return "'problem' needs text: the question, in full"
        figure = op.get("figure")
        if figure is not None:
            if not isinstance(figure, dict) or figure.get("op") not in {"draw", "sketch", "graph"} | set(stem.PRESETS):
                return ("a problem's figure is a sketch, a graph or a preset: {\"op\":\"incline\",\"angle\":30,...} "
                        "(or a draw op, only for what those cannot show)")
            inner = _stem_problem({**figure, "id": figure.get("id") or f"{key}_figure"}, diagrams)
            if inner:
                return f"problem figure: {inner}"
        diagrams[key] = []
        return None
    if kind == "graph":
        problem = stem.graph_problem(op)
        if problem:
            return problem
        ids = [str(i.get("id")) for i in op.get("items") or [] if i.get("id")]
        diagrams[f"?kind:{key}"] = "graph"
        diagrams[f"?curves:{key}"] = [str(i.get("id")) for i in op.get("items") or []
                                      if i.get("id") and i.get("kind") == "curve"]
    else:
        problem = stem.sketch_problem(op)
        if problem:
            return problem
        ids = stem.element_ids(stem.op_elements(op))
        if kind in stem.PRESETS:
            diagrams[f"?kind:{key}"] = kind          # what a motion on it can do (stem.MOTIONS)
    unknown = [str(x) for x in op.get("show") or [] if str(x) not in ids]
    if unknown:
        return f"{kind} {key} show: no part {unknown[0]!r} (its parts: {', '.join(ids) or 'none named'})"
    diagrams[key] = ids
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
    if kind == "plot":
        exprs = op.get("exprs") or ([op["expr"]] if op.get("expr") else [])
        if not exprs:
            return "'plot' needs expr (a function of x, e.g. x^2 - 3*x) or exprs"
        x = op.get("x") or [-5, 5]
        if len(x) != 2 or float(x[0]) >= float(x[1]):
            return "'plot' x must be [min, max]"
        import numpy as np
        from pocket_lecture import safe_function

        for e in exprs:
            try:
                safe_function(str(e))(np.linspace(float(x[0]), float(x[1]), 5))
            except Exception as error:  # noqa: BLE001
                return f"plot: {error}"
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
PICTURE_OPS = {"photo", "figure", "illustration", "molecule", "equation", "plot", "bars", "gallery", "diagram",
               "define", "compare", "reveal", "focus", "work", "trace", "sweep", "motion"} | STEM_OPS | LIVE_OPS
NOT_A_FIGURE = re.compile(r"\b(QR|bar ?code|logo|watermark)\b|क्यूआर", re.I)


def book_figure_count(script: dict) -> int:
    return sum(1 for f in (script.get("figures") or {}).values()
               if not NOT_A_FIGURE.search(str((f or {}).get("caption", ""))))


def web_budget(script: dict) -> int | None:
    """How many new pictures from the web (photos, illustrations, gallery items) a lecture may add: no limit
    without a book, fewer the more figures the book has of its own (they come first), PANIM_WEB_PICTURES if set.
    The app's prompt says the same (document.ts webBudget)."""
    figures = book_figure_count(script)
    if os.environ.get("PANIM_WEB_PICTURES", "").strip().isdigit():
        return int(os.environ["PANIM_WEB_PICTURES"])
    if not figures:
        return None
    return max(1, 10 - 2 * figures)


def web_pictures(script: dict) -> list[str]:
    """Where the script asks for a picture from the web: one entry per photo, illustration or gallery item."""
    out = []
    for c, chapter in enumerate(script.get("chapters") or []):
        for b, beat in enumerate(chapter.get("beats") or []):
            for op in beat.get("do") or []:
                if not isinstance(op, dict):
                    continue
                kind = op.get("op")
                if kind in ("photo", "illustration"):
                    out.append(f"chapter {c + 1} beat {b + 1}")
                elif kind == "gallery":
                    out += [f"chapter {c + 1} beat {b + 1}" for item in _gallery_items(op) if item["op"] != "figure"]
                out += [f"chapter {c + 1} beat {b + 1}" for _, spec in pictures_of(op)
                        if isinstance(spec, dict) and _picture_fetch(spec)]
    return out


def _web_pictures_problem(script: dict) -> list[str]:
    budget = web_budget(script)
    if budget is None:
        return []
    asked = web_pictures(script)
    if len(asked) <= budget:
        return []
    return [f"{asked[budget]}: the book has {book_figure_count(script)} figures of its own, so the lecture adds at "
            f"most {budget} new picture{'s' if budget != 1 else ''} from the web (photo, illustration, gallery item); "
            f"this script asks for {len(asked)}. Show the book's figures (figure ops) and build diagrams instead"]


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
             "about", "heavier", "distance", "back", "anim", "what", "moves", "svg", "_draw_error", "art", "shape"}


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
    """How deep a lecture of this length goes (the app's lib/lecture.ts teachingPlan, the same formula).

    The content decides the topics (about one every 350 words of a source; a bare topic is split by the time
    there is). The minutes a topic gets decide how many examples each statement has and how many questions
    the class is asked.
    """
    if source_words > 400:
        topics = min(15, max(2, round(source_words / 350)))
    else:
        topics = min(12, max(2, round(minutes / 3)))
    per_topic = minutes / topics
    examples = 1 if per_topic < 1.5 else 2 if per_topic < 3 else 3 if per_topic < 5 else 4
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
        if not _map_chapter(chapter, bool(script.get("region"))):
            continue
        count = 0
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
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


# The fewest lines of working a problem's solution shows (app/lib/solving.ts MIN_WORK_LINES): a problem solved in two
# or three lines skipped the steps a beginner needs.
MIN_WORK_LINES = 6
# The fewest times a problem's figure is pointed at (reveal or focus) while it is read and solved
# (app/lib/solving.ts MIN_FIGURE_STEPS): its diagram explained, not only shown.
MIN_FIGURE_STEPS = 3



# Narration that tells of something moving: a motion op plays only on such a beat. Set going on a beat that is about
# a formula or a force balance, a still diagram jumping about looked forced, not explained.
MOVING_SAYS = re.compile(
    r"\b(slid|slide|slip|mov(?:e|es|ed|ing)\b|motion|fall|fell|drop|swing|swung|oscillat|vibrat|roll|accelerat|"
    r"decelerat|throw|thrown|fl(?:y|ies|ew|ying)\b|launch|land(?:s|ed|ing)?\b|rotat|spin|tip(?:s|ped|ping)?\b|"
    r"tilt|push|pull|compress|stretch|expand|ris(?:e|es|ing)\b|goes (?:up|down|round|around)|speeds? up|slow|bounc|"
    r"collid|travel|turn(?:s|ed|ing)? (?:round|around|about)|watch|flow|stream|current|orbit|revolv|circl|"
    r"pump|beat(?:s|ing)?\b|drift|spread|diffus|wave|ripple|swirl|circulat)"
    r"|फिसल|गिर|लुढ़क|झूल|दोलन|घूम|उछ|फेंक|उड़|टकरा|धकेल|धक्का|खींच|खिंच|दब|फैल|सिकुड़|हिल|मुड़|ऊपर जा|नीचे जा|"
    r"चलती|चलता|चलने|गति कर|देखो|बह|परिक्रमा|धड़क|फैल",
    re.IGNORECASE)
# How often one diagram is set moving in a lecture: once to show what happens, once more when the solution uses it.
MAX_MOTIONS = 2


def _unneeded_motions(script: dict, drop: bool = False) -> list[str]:
    """The motion ops that are not needed: on a beat whose narration tells of nothing moving, or a diagram set
    moving more than MAX_MOTIONS times. A pulse (a part glowing as it is named) is not a motion. With `drop`, they
    are taken out of the script, so the video animates only where the narration describes motion."""
    notes: list[str] = []
    moved: dict[str, int] = {}
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            ops = beat.get("do")
            if not isinstance(ops, list):
                continue
            keep = []
            for op in ops:
                if not (isinstance(op, dict) and op.get("op") == "motion") or op.get("kind") == "pulse":
                    keep.append(op)
                    continue
                key = str(op.get("diagram"))
                why = None
                if not MOVING_SAYS.search(str(beat.get("say") or "")):
                    why = "its narration does not describe anything moving"
                elif moved.get(key, 0) >= MAX_MOTIONS:
                    why = f"{key!r} has already moved {MAX_MOTIONS} times"
                if why:
                    notes.append(f"chapter {ci} beat {bi}: the motion of {key!r} is left out: {why}. Animate a diagram "
                                 "only on the beat that says what moves, and how.")
                    if drop:
                        continue
                else:
                    moved[key] = moved.get(key, 0) + 1
                keep.append(op)
            if drop:
                beat["do"] = keep
    return notes


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


def _map_chapter(chapter: dict, has_region: bool) -> bool:
    """A chapter draws its map only when a beat points at the map, and never when told not to."""
    if not has_region or chapter.get("map") is False:
        return False
    return any(op.get("op") in MAP_OPS or (op.get("op") == "icon" and _icon_spots(op))
               for b in chapter.get("beats") or [] for op in b.get("do") or [])


BARE_OPENING = 3         # beats a chapter may open with before something is on the stage (an error)


def _bare_stretches(script: dict) -> tuple[list[str], list[str]]:
    """(errors, warnings) about beats with nothing on the stage. A picture stays up until the next one (a chapter's
    map, its diagrams, its figures), so the stage is only ever empty where a chapter opens without one: three beats
    of that (half a minute of an empty board) is an error. Long runs that go on talking over the same picture are
    advice."""
    errors, warnings = [], []
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        if _map_chapter(chapter, bool(script.get("region"))):
            continue
        beats = chapter.get("beats") or []
        opening = 0
        for beat in beats:
            if any(op.get("op") in VISUAL_OPS | WORK_OPS or op.get("op") == "manim" for op in beat.get("do") or []):
                break
            opening += 1
        # Only where the writer draws the pictures (sciences, mathematics): elsewhere the compiler puts up photos
        # of what a paragraph names (auto_visuals).
        drawn_here = script.get("genre") in BOARD_GENRES or any(
            op.get("op") in STEM_OPS | WORK_OPS for b in beats for op in b.get("do") or [])
        if opening >= BARE_OPENING and drawn_here:
            errors.append(f"chapter {ci} ({chapter.get('title', '')!r}): its first {opening} beats show nothing on "
                          "the stage. Put up the chapter's first picture on its first beat (a diagram, a preset, a "
                          "sketch, a graph, a figure, a define card), and build on it as the narration goes on")
        run = 0
        for bi, beat in enumerate(beats, 1):
            # Revealing more of a drawing, or adding to a worked solution, keeps the picture going.
            if any(op.get("op") in VISUAL_OPS | STEP_OPS | WORK_OPS for op in beat.get("do") or []):
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
SUBJECT_LOOKUPS = 6          # Wikipedia lookups per chapter, at most: a compile stays quick


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
    lookups = SUBJECT_LOOKUPS * 2
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
        if not pick and images.enabled() and _web_left() > 0:
            # People, communities and places the paragraph names: their pictures, together.
            found = []
            names = []
            for i in group:
                # Mathematics and the sciences build their pictures: a photo only of someone the writer names.
                if genre in BOARD_GENRES and not beats[i].get("about"):
                    continue
                names += [n for n in named_subjects(beats[i], limit=3) if n not in names]
            for subject in names[:4]:
                if lookups <= 0 or len(found) >= min(3, _web_left()):
                    break
                lookups -= 1
                row = images.fetch(subject=subject)
                if row and row["id"] not in USED_PICTURES:
                    item = {"op": "photo", "subject": subject, "caption": subject}
                    script_photos[_photo_key(item)] = row
                    USED_PICTURES.add(row["id"])
                    found.append(item)
            _web_used(len(found))
            if len(found) == 1:
                pick = found[0]
            elif found:
                pick = {"op": "gallery", "items": [{"subject": f["subject"], "caption": f["caption"]} for f in found]}
        # Biology is taught with pictures of what it is about (a cell, a leaf, a heart): a paragraph left without one
        # gets a textbook illustration of its topic, as an explicit "auto_illustrations" gives any lecture.
        if not pick and (STYLE_NOW.get("auto_illustrations") or genre == "biology") and images.enabled() \
                and lookups > 0 and _web_left() > 0:
            for query in picture_queries(first, chapter, genre, group[0]):
                lookups -= 1
                row = images.fetch(illustration=query, avoid=USED_PICTURES, genre=genre, style=STYLE_NOW["style"])
                if row:
                    pick = {"op": "illustration", "query": query, "caption": ""}
                    script_photos[_photo_key(pick)] = row
                    USED_PICTURES.add(row["id"])
                    _web_used(1)
                    break
        if pick:
            out[group[0]] = pick
        # Nothing new for this paragraph: the last picture stays up. Taking it down left the board empty while
        # the teacher went on explaining it (every fifth beat of a long explanation, in sciences with no photos).
    return out


# Pictures a lecture has shown, so one diagram does not stand for several topics (reset per compile), and the
# lecture's style, which an AI illustration is drawn in.
USED_PICTURES: set = set()
STYLE_NOW: dict = {"style": None, "auto_illustrations": False, "web_left": None}


def _web_left() -> float:
    left = STYLE_NOW.get("web_left")
    return float("inf") if left is None else left


def _web_used(n: int) -> None:
    if STYLE_NOW.get("web_left") is not None:
        STYLE_NOW["web_left"] = max(0, STYLE_NOW["web_left"] - n)
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


def _unknown_icons(names: list[tuple[str, str]]) -> list[str]:
    if not names:
        return []
    import icons

    if not icons.available():
        return [f"{names[0][0]}: icons are not installed; run harness/scripts/fetch_icons.py, or drop the icon ops"]
    out = []
    for at, name in names:
        # A science drawing or an open-library illustration: not an icon-set name.
        if str(name).startswith(("draw:", "bioicons:", "coco:", "arcadia:", "clip:")):
            continue
        if icons.resolve(name) is None:
            out.append(f"{at}: no icon for {name!r}; search with find_icon and use a name it returns, "
                       "or a simpler word (wheat, factory, cow, dam)")
    return out


def _unknown_places(places: list[tuple[str, str]], country: str | None) -> list[str]:
    """Marker places the gazetteer cannot find: caught here, not halfway through a render."""
    if not places:
        return []
    try:
        from pocket_lecture import place
    except Exception:  # noqa: BLE001 -- no engine here (a lint-only install): the render will say
        return []
    out = []
    for at, name in places:
        try:
            place(name, country)
        except KeyError:
            out.append(f"{at}: no place named {name!r}" + (f" in {country}" if country else "")
                       + "; use a nearby larger town, or give its position as lonlat [lon, lat] instead of place")
    return out


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
        return f"self.{method}([{pts}]{color})"
    if kind == "journey":
        stops = ", ".join(_q(x) if isinstance(x, str) else f"({float(x[0]):g}, {float(x[1]):g})" for x in op["stops"])
        color = f", color={_colour(op.get('color'))}" if op.get("color") else ""
        labels = f", labels={[str(x) for x in op['labels']]!r}" if isinstance(op.get("labels"), list) else ""
        pictures = (f", pictures=[{', '.join(_picture_arg(p) for p in op['pictures'])}]"
                    if isinstance(op.get("pictures"), list) and any(op["pictures"]) else "")
        return f"self.journey([{stops}]{color}{labels}{pictures})"
    if kind == "state":
        color = _colour(op.get("color"), "P.SAND")
        return f"self.fill_state({_q(op['name'])}, {color}, {float(op.get('opacity', 0.6)):g})"
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
            return f"self.stage_image({_q(row['file'])}, {_q(caption)}, credit={_q(row['credit'])})"
        return f"self.figure({_q(row['file'])}, {_q(caption)}, where={_q(where)})"
    if kind == "molecule":
        label = f", {_q(op['label'])}" if op.get("label") else ""
        return f"self.molecule({_q(op['name'])}{label})"
    if kind == "equation":
        label = f", {_q(op['label'])}" if op.get("label") else ""
        return f"self.equation({_q(op['tex'])}{label})"
    if kind == "plot":
        exprs = op.get("exprs") or [op["expr"]]
        x = op.get("x") or [-5, 5]
        names = op.get("names") or []
        return (f"self.plot([{', '.join(_q(e) for e in exprs)}], ({float(x[0])}, {float(x[1])}), "
                f"{_q(op['label']) if op.get('label') else 'None'}, {_q(op.get('x_label', 'x'))}, "
                f"{_q(op.get('y_label', 'y'))}, [{', '.join(_q(n) for n in names)}])")
    if kind == "process":
        title = f", {_q(op['title'])}" if op.get("title") else ", None"
        return f"self.process([{', '.join(_q(x) for x in op['steps'])}]{title}, cycle={bool(op.get('cycle'))})"
    if kind == "timeline":
        events = ", ".join(f"({_q(d)}, {_q(lab)}, {_picture_arg(pic)})" for d, lab, pic in _timeline_events(op))
        title = f", {_q(op['title'])}" if op.get("title") else ""
        return f"self.big_timeline([{events}]{title})"
    if kind == "quote":
        return f"self.quote({_q(op['text'])}, {_q(op.get('who', ''))})"
    if kind == "illustration":
        row = script_photos.get(_photo_key(op))
        if not row:
            return None            # nothing reusable was found: the beat plays without it
        return f"self.stage_image({_q(row['file'])}, {_q(op.get('caption') or '')}, credit={_q(row['credit'])})"
    if kind == "figure":
        figure = script_figures[str(op["id"])]
        caption = op.get("caption") or figure.get("caption") or ""
        if figure.get("svg") and not op.get("photo"):
            show = f", show={[str(x) for x in op['show']]!r}" if op.get("show") else ""
            return f"self.svg_figure({_q(str(op['id']))}, {_q(figure['svg'])}, {_q(str(caption)[:160])}{show})"
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
                    shown.append((figure["file"], item.get("caption") or figure.get("caption", "")))
                continue
            row = script_photos.get(_photo_key(item))
            if row:
                shown.append((row["file"], item.get("caption") or ""))
        if not shown:
            return None
        if len(shown) == 1:
            return f"self.stage_image({_q(shown[0][0])}, {_q(shown[0][1])})"
        items = ", ".join(f"({_q(f)}, {_q(c)})" for f, c in shown)
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        return f"self.gallery([{items}]{title})"
    if kind == "diagram":
        _edges_as_lists(op)
        nodes = [{"id": str(n["id"]), "label": str(n["label"]), **({"entity": str(n["entity"])} if n.get("entity") else {}),
                  **({"items": [str(i) for i in n["items"]][:5]} if n.get("items") else {}),
                  **({"anim": str(n["anim"])} if n.get("anim") else {}),
                  **({k: str(n[k]) for k in ("shape", "lane", "tone") if n.get(k)}),
                  **({"picture": _picture_value(n["picture"])} if _picture_value(n.get("picture")) else {})}
                 for n in op["nodes"]]
        edges = [[str(e[0]), str(e[1])] + ([str(e[2]) if len(e) > 2 and e[2] else ""] if len(e) > 2 else [])
                 + ([str(e[3])] if len(e) > 3 and e[3] and str(e[3]) != "solid" else []) for e in op.get("edges") or []]
        edges = [e[:2] if len(e) == 3 and not e[2] else e for e in edges]
        show = f", show={[str(x) for x in op['show']]!r}" if op.get("show") else ""
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        return (f"self.diagram({_q(str(op['id']))}, {_q(op.get('kind', 'flow'))}, {nodes!r}, {edges!r}"
                f"{title}{show}{_diagram_motion(op)})")
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
    if kind == "motion":
        spec = _clean({k: v for k, v in op.items() if k not in ("op", "diagram")})
        return f"self.motion({_q(str(op['diagram']))}, {spec!r})"
    if kind in ("trace", "sweep"):
        spec = _clean({k: v for k, v in op.items() if k not in ("op", "diagram")})
        return f"self.{kind}({_q(str(op['diagram']))}, {spec!r})"
    if kind == "zoom":
        node = _q(str(op["node"])) if op.get("node") is not None else "None"
        return f"self.zoom({_q(str(op['diagram']))}, {node}, {float(op.get('scale') or 1.8)!r})"
    if kind == "sim":
        params = _clean({**(op.get("params") or {}),
                         **{k: v for k, v in op.items() if k not in ("op", "id", "kind", "title", "keep", "params")}})
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        keep = ", keep=True" if op.get("keep") else ""
        return f"self.sim({_q(str(op['id']))}, {_q(str(op['kind']))}, {params!r}{title}{keep})"
    if kind == "counter":
        spec = _clean({k: v for k, v in op.items() if k not in ("op", "id", "title")})
        title = f", title={_q(op['title'])}" if op.get("title") else ""
        return f"self.counter({_q(str(op['id']))}, {spec!r}{title})"
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


def _stem_call(op: dict) -> str:
    import stem

    kind = op["op"]
    key = str(op.get("id") or "")
    title = f", title={_q(op['title'])}" if op.get("title") else ""
    show = f", show={[str(x) for x in op['show']]!r}" if op.get("show") else ""
    if kind == "work":
        box = ", box=True" if op.get("box") else ""
        return f"self.work({_q(key)}, {_clean(op['lines'])!r}{title}{box})"
    movable = f", movable={op['_movable']!r}" if op.get("_movable") else ""
    if kind == "draw":
        if op.get("svg"):
            return f"self.svg_figure({_q(key)}, {_q(op['svg'])}, {_q(op['title']) if op.get('title') else 'None'}{show})"
        # Not drawn (no drawing step ran, or it failed): its parts as labelled boxes, so reveals still land.
        import stem

        return f"self.sketch({_q(key)}, {stem._parts_as_cards(op)!r}{show}{title})"
    if kind == "sketch":
        return f"self.sketch({_q(key)}, {_clean(op['items'])!r}{show}{title}{movable})"
    if kind == "graph":
        spec = _clean({k: v for k, v in op.items() if k not in ("op", "id", "title")})
        return f"self.graph({_q(key)}, {spec!r}{title})"
    if kind == "problem":
        extra = ""
        if op.get("given"):
            extra += f", given={[str(g) for g in op['given']]!r}"
        if op.get("find"):
            extra += f", find={_q(op['find'])}"
        if op.get("figure"):
            figure = _clean({**op["figure"], "id": op["figure"].get("id") or f"{key}_figure"})
            extra += f", figure={figure!r}"
        return f"self.problem({_q(key)}, {_q(op['text'])}{title}{extra})"
    params = _clean({k: v for k, v in op.items() if k not in ("op", "id", "show", "title", "_movable")})
    assert kind in stem.PRESETS
    return f"self.preset({_q(key)}, {_q(kind)}, {params!r}{show}{title}{movable})"


def board_chapter(script: dict, chapter: dict) -> bool:
    """A chapter taught on the board: the whole frame for its pictures, and a one-line key-point strip instead of
    a side panel of text. Every chapter without a map is, whatever the style, unless the script sets
    "layout": "panel" (and then a chapter building STEM drawings still is). A map chapter keeps its panel."""
    if _map_chapter(chapter, bool(script.get("region"))):
        return False
    if script.get("layout") == "panel":
        return any(op.get("op") in STEM_OPS | WORK_OPS | FREE_OPS | LIVE_OPS for b in chapter.get("beats") or []
                   for op in b.get("do") or [])
    return True


def _resolve_motion(script: dict) -> None:
    """The parts each diagram's motions move, on the op that draws it (`_movable` on a sketch or preset, `movable`
    on a problem's figure): the engine draws those as objects of their own, so they move without leaving a copy."""
    import stem

    for chapter in script.get("chapters") or []:
        drawn: dict[str, tuple] = {}          # diagram id -> (the dict that draws it, its field, preset kind, elements)
        for beat in chapter.get("beats") or []:
            for op in beat.get("do") or []:
                kind = op.get("op")
                if kind in stem.PRESETS or kind == "sketch":
                    drawn[str(op.get("id"))] = (op, "_movable", kind if kind in stem.PRESETS else None,
                                                stem.op_elements(op))
                elif kind == "problem" and isinstance(op.get("figure"), dict) and op["figure"].get("op") not in ("graph", "draw"):
                    figure = op["figure"]
                    fkind = figure.get("op") if figure.get("op") in stem.PRESETS else None
                    drawn[str(figure.get("id") or f"{op.get('id')}_figure")] = (figure, "movable", fkind,
                                                                                 stem.op_elements(figure))
                elif kind == "motion" and str(op.get("diagram")) in drawn:
                    owner, field, preset, elements = drawn[str(op.get("diagram"))]
                    steps, _ = stem.motion_plan(preset, owner, elements, op)
                    ids = {i for step in steps for i in [*step.get("move", []), *step.get("turn", []),
                                                         *([step["stretch"]] if "stretch" in step else [])]}
                    owner[field] = sorted(set(owner.get(field) or []) | ids)


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


def _diagram_parts(op: dict) -> list[str] | None:
    """The part ids of a picture an op puts up that "show" and reveal can name, or None when it has none."""
    import stem

    kind = op.get("op")
    try:
        if kind == "diagram":
            return [str(n.get("id")) for n in op.get("nodes") or [] if isinstance(n, dict) and n.get("id")]
        if kind == "draw":
            return [str(p) for p in op.get("parts") or []]
        if kind == "figure":
            return [str(p) for p in (script_figures.get(str(op.get("id"))) or {}).get("parts") or []]
        if kind == "graph":
            return [str(i.get("id")) for i in op.get("items") or [] if i.get("id")]
        if kind == "sketch" or kind in stem.PRESETS:
            return list(stem.element_ids(stem.op_elements(op)))
    except Exception:  # noqa: BLE001 -- a picture whose parts cannot be read is left as it is
        return None
    return None


def _complete_reveals(script: dict) -> int:
    """Parts of a picture its script never shows: a "show" that starts with some parts and reveals that never
    name the others left them off the board for good (a force never drawn, a diagram's last node missing).
    Each such part joins the picture's last reveal in its chapter, or, when nothing of it is ever revealed, the
    whole picture is drawn at once. Returns how many parts were brought back."""
    added = 0
    for chapter in script.get("chapters") or []:
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
                    parts = _diagram_parts(holder)
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
            else:
                holder.pop("show", None)            # nothing of it is ever revealed: all of it, at once
            added += len(missing)
    return added


def compile_script(script: dict, scene_class: str = "GeneratedScene", engine_path: str | None = None) -> str:
    """The Manim source for a script. Raises ValueError with the lint errors."""
    errors, _ = lint(script)
    if errors:
        raise ValueError("\n".join(errors))
    script_figures.clear()
    script_figures.update(script.get("figures") or {})
    USED_PICTURES.clear()
    STYLE_NOW["style"] = script.get("style")
    STYLE_NOW["auto_illustrations"] = bool(script.get("auto_illustrations"))
    # What is left of the web-picture budget once the script's own are counted: the paragraphs' automatic
    # pictures take no more than that (none at all when a book with many figures has used it up).
    budget = web_budget(script)
    STYLE_NOW["web_left"] = None if budget is None else max(0, budget - len(web_pictures(script)))
    import illustrations

    illustrations.reset()        # a new lecture: re-read the collections on disk, a fresh AI budget
    _resolve_options(script)
    _unneeded_motions(script, drop=True)
    _unneeded_molecules(script, drop=True)
    _resolve_motion(script)
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
        "",
        "",
        f"class {scene_class}({base}):",
    ]
    if region:
        fields = ", ".join(f"{k}={_q(v)}" for k, v in region.items() if v)
        out.append(f"    REGION = dict({fields})")
    out.append(f"    SECTIONS = [{', '.join(_q(s) for s in sections)}]")
    out += ["", "    def construct(self):"]
    if script.get("title"):
        intro = script.get("intro") or f"{script['title']}. {script.get('sub', '')}".strip()
        out.append(f"        self.title_slide({_q(script['title'])}, {_q(script.get('sub', ''))}, narration={_q(intro)})")
    for index, chapter in enumerate(chapters, 1):
        out += ["", f"        # {index:02d}  {chapter['title']}"]
        out.append(f"        self.chapter({index}, {_q(chapter['title'])}, {_q(chapter.get('sub', ''))}, "
                   f"{_q(chapter.get('narration') or chapter['title'])})")
        on_map = _map_chapter(chapter, bool(region))
        out.append("        self.show_map()" if on_map else
                   "        self.board()" if board_chapter(script, chapter) else "        self.add_panel()")
        if on_map:
            # Every place the chapter will mark, spoken for now: no label set early covers a later marker's dot.
            spots = _chapter_spots(chapter)
            if spots:
                out.append(f"        self.reserve_places([{', '.join(spots)}])")
        fills = auto_visuals(chapter, genre=script.get("genre")) if script.get("auto_visuals", True) else []
        staged = False
        # A paragraph ends with a longer pause, so an idea settles before the next begins.
        closing = {group[-1] for group in paragraphs(chapter.get("beats") or [])}
        for bi, beat in enumerate(chapter.get("beats") or []):
            ops = beat_order(list(beat.get("do") or []))
            free = next((op for op in ops if op.get("op") == "manim"), None)
            if free is not None:
                # Drawn by the model's own Manim (free_check.py, stem.BoardMixin.free).
                import free_check

                pad = "PARAGRAPH_PAD" if bi in closing else "BEAT_PAD"
                if _pause(beat):
                    pad = f"{pad} + {_pause(beat):g}"
                out.append(f"        self.free({_q(free_check.free_key(free, index))}, {_q(beat['say'])}, "
                           f"{_q(free['code'])}, pad={pad})")
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
            # its beat, not the whole lecture stopped.
            for op in ops:
                call = _op_call(op)
                if call:
                    what = f"chapter {index} beat {bi + 1} {op.get('op')}"
                    calls.append(f"self.safe(lambda: {call}, {_q(what)})")
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
    if script.get("credits") or uses_icons or script_photos or web_figures:
        import images

        line = script.get("credits") or ("Map data: Natural Earth · Animation: Manim" if region else "Animation: Manim")
        photos = images.credit([*script_photos.values(), *web_figures])
        out.append(f"        self.credits({_q(line)}" + (f", extra={_q(photos)}" if photos else "") + ")")
    return "\n".join(out) + "\n"


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
    errors, warnings = lint(script, args.min_minutes, args.min_questions, args.min_examples, args.min_problems)
    if args.json:
        source = None if errors else compile_script(script, args.scene_class)
        print(json.dumps({"source": source, "errors": errors, "warnings": warnings,
                          "minutes": round(estimate_minutes(script), 2)}))
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
