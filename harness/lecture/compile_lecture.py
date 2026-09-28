"""Compile a lecture beat script (JSON) into a Manim scene on pocket_lecture.

The guide's cheap path: a model writes a short structured script -- beats of
narration plus the few operations that go with each -- and this turns it into
engine calls. The output is ordinary, readable Manim, so it can be edited by
hand in the web editor, exported to the phone, or rendered by `manim`.

A script:

    {
      "title": "India", "sub": "The geography of a subcontinent",
      "style": "vox",                                  # a pocket_lecture style
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
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STYLES = ("atlas", "vox", "cardboard", "whiteboard", "blueprint", "chalkboard", "parchment", "lab", "cosmos")
PALETTE = {"SAND", "DUNE", "TERRA", "RUST", "TEAL", "RIVER", "GREEN", "OLIVE", "CREAM", "MUTED",
           "ROSE", "GOLD", "VIOLET", "HI", "MOUNT"}
MAP_OPS = {"marker", "river", "path", "arrow", "state", "dim", "graticule"}
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


WORD_SECONDS = 0.42      # about 143 words a minute: pocket_lecture.estimate_seconds
BEAT_PAD = 0.45          # the hold after each beat (Lecture.beat)


def _say_seconds(text: str) -> float:
    return max(1.2, len(str(text).split()) * WORD_SECONDS) + BEAT_PAD


def estimate_minutes(script: dict) -> float:
    """How long the lecture will run: narration at speaking pace plus cards, map draws and fades."""
    seconds = 0.0
    if script.get("title"):
        seconds += _say_seconds(script.get("intro") or script["title"]) + 1.6
    for chapter in script.get("chapters") or []:
        seconds += _say_seconds(chapter.get("narration", "")) + 0.8 + 1.4 + 1.0     # card, map, outro
        seconds += sum(_say_seconds(b.get("say", "")) for b in chapter.get("beats") or [])
    for head, body in script.get("recap") or []:
        seconds += _say_seconds(f"{head}. {body}")
    if script.get("credits"):
        seconds += 5.0
    return seconds / 60


def lint(script: dict, min_minutes: float | None = None) -> tuple[list[str], list[str]]:
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
        for key in ("title", "narration"):
            if not chapter.get(key):
                errors.append(f"{where}: missing {key}")
        used = 0.0
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            at = f"{where} beat {bi}"
            say = str(beat.get("say") or "").strip()
            if not say:
                errors.append(f"{at}: no narration ('say')")
            elif len(say) > 184:
                warnings.append(f"{at}: the caption runs past two lines ({len(say)} characters); split the beat")
            ops = beat.get("do") or []
            if len(ops) > 5:
                warnings.append(f"{at}: {len(ops)} operations in one beat; the eye cannot follow more than about four")
            for op in ops:
                kind = op.get("op")
                if kind not in {"panel", "fact", "stat", "bars", "clear", "icon", "figure", "photo",
                                "illustration"} | KIT_OPS | MAP_OPS:
                    errors.append(f"{at}: unknown op {kind!r}")
                    continue
                if kind in MAP_OPS and not has_map:
                    errors.append(f"{at}: '{kind}' needs a map; give the script a region")
                if kind in MAP_OPS and chapter.get("map") is False:
                    errors.append(f"{at}: '{kind}' in a chapter with map=false")
                need = {"panel": ["title"], "fact": ["text"], "stat": ["value", "label"], "bars": ["items"],
                        "river": ["name"], "state": ["name"], "path": ["points"], "arrow": ["points"]}
                for field in need.get(kind, []):
                    if not op.get(field):
                        errors.append(f"{at}: '{kind}' needs {field}")
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
                if kind == "figure":
                    figure = (script.get("figures") or {}).get(str(op.get("id")))
                    if not figure:
                        known = ", ".join(sorted(script.get("figures") or {})) or "none (no document was uploaded)"
                        errors.append(f"{at}: no figure {op.get('id')!r}; the figures are: {known}")
                    elif not Path(str(figure.get("file", ""))).is_file():
                        errors.append(f"{at}: figure {op.get('id')!r} has no image file")
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
    warnings += _bare_stretches(script)
    e, w = _plain_language(script)
    errors += e
    warnings += w
    e, w = _text_heavy(script)
    errors += e
    warnings += w
    minutes = estimate_minutes(script)
    if min_minutes and chapters and minutes < min_minutes * 0.85:
        beats = sum(len(c.get("beats") or []) for c in chapters)
        words = sum(len(str(b.get("say", "")).split()) for c in chapters for b in c.get("beats") or [])
        need = int((min_minutes * 60 - (minutes * 60 - words * WORD_SECONDS)) / WORD_SECONDS) - words
        errors.append(f"the lecture runs about {minutes:.1f} min ({beats} beats, {words} words of narration); "
                      f"it must run at least {min_minutes:g} min. Add about {max(need, 50)} more words of narration: "
                      "more beats in each chapter and more chapters, each beat a new fact from the content, "
                      "not repetition. Keep every existing beat that is right.")
    return errors, warnings


script_photos: dict = {}


def _photo_key(op: dict) -> str:
    if op.get("op") == "illustration":
        return f"illustration|{op.get('image') or ''}|{op.get('query') or ''}"
    return f"{op.get('image') or ''}|{op.get('query') or ''}|{op.get('subject') or ''}"


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
        elif not images.enabled():
            out.append(f"{at}: internet photos are off here; use a document figure, a diagram you draw (process, "
                       "timeline, equation, plot) or drop the photo")
        else:
            what = op.get("image") or (f"subject {op['subject']!r}" if op.get("subject") else f"query {op.get('query')!r}")
            out.append(f"{at}: no reusable photo for {what}; use find_image and pick a title it returns, "
                       "or show an illustration (find_illustration) instead")
    return out


KIT_OPS = {"molecule", "equation", "plot", "process", "timeline", "quote"}
VISUAL_OPS = {"photo", "figure", "illustration"} | KIT_OPS


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
PICTURE_OPS = {"photo", "figure", "illustration", "molecule", "equation", "plot", "bars"}
NOT_A_FIGURE = re.compile(r"\b(QR|bar ?code|logo|watermark)\b|क्यूआर", re.I)


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


def _plain_language(script: dict) -> tuple[list[str], list[str]]:
    """Lines read out of the source book, and sentences too long to follow by ear.

    A lecture explains: it says a textbook sentence in everyday words, with an
    example. A few quoted phrases are fine; a script that is mostly the book's
    own sentences is an error.
    """
    errors, warnings = [], []
    source = _word_list(script.get("source_text") or "")
    grams = {tuple(source[i:i + COPY_RUN]) for i in range(len(source) - COPY_RUN + 1)}
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
    if len(wordy) > max(3, len(beats) * 0.3):
        return [f"{len(wordy)} of {len(beats)} beats show only boxes of words (process or quote) on the stage. "
                "Show pictures instead: an educational illustration or diagram (find_illustration, described in English "
                "even in a Hindi lecture), a photo (find_image) or a document figure. Keep process for at most "
                "two real sequences per chapter."], warnings
    return [], warnings


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


def _bare_stretches(script: dict) -> list[str]:
    """Advice: long runs of beats in a map-less chapter with no picture."""
    out = []
    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        if _map_chapter(chapter, bool(script.get("region"))):
            continue
        run = 0
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            if any(op.get("op") in VISUAL_OPS for op in beat.get("do") or []):
                run = 0
                continue
            run += 1
            if run == 4:
                out.append(f"chapter {ci} beat {bi}: four beats without a picture; add a photo, a figure or an "
                           "illustration (the compiler fills gaps with diagrams, but a chosen picture is better)")
    return out


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


def auto_visuals(chapter: dict, is_map_op=None, genre: str | None = None) -> list[dict | None]:
    """A picture for each beat that needs one, else None.

    On a map chapter, a beat that points at the map keeps it; a beat about
    something else covers it with a picture, and the next map beat brings it back.

    In order: a molecule or equation (sciences) or a timeline (history) the
    beat itself contains; Wikipedia's picture of a person, movement or place it
    names; else an educational illustration or diagram of what it explains
    (Wikimedia Commons, Openverse). No icons. A picture the script chose itself
    stays up through the next beat before an automatic one replaces it.
    """
    import images

    beats = chapter.get("beats") or []
    lookups = SUBJECT_LOOKUPS * 2       # names (photos) and topics (illustrations) share it
    out: list[dict | None] = []
    showing: set[str] = set()
    hold = 0
    is_map_op = is_map_op or _points_at_map
    for index, beat in enumerate(beats):
        if any(is_map_op(op) for op in beat.get("do") or []):
            # A beat about where things are: the map is the picture.
            out.append(None)
            showing, hold = set(), 0
            continue
        if any(op.get("op") in VISUAL_OPS for op in beat.get("do") or []):
            out.append(None)
            showing, hold = set(), 1
            continue
        say = beat.get("say", "")
        kit_op = None
        if genre in ("chemistry", "biology", "physics", "mathematics") and hold <= 0:
            equation = _equation_in(say)
            named = []
            if genre in ("chemistry", "biology"):
                import molecules

                named = [m for m in molecules.find_in_text(say) if f"molecule:{m}" not in showing]
            if equation and f"equation:{equation}" not in showing:
                kit_op, showing = {"op": "equation", "tex": equation}, {f"equation:{equation}"}
            elif named:
                kit_op, showing = {"op": "molecule", "name": named[0]}, {f"molecule:{named[0]}"}
        if genre == "history" and index == 0 and not any(
                op.get("op") == "timeline" for b in beats for op in b.get("do") or []):
            events = _timeline_of(chapter)
            if events:
                kit_op, showing = {"op": "timeline", "events": events}, {"timeline"}
        if not kit_op and lookups > 0 and images.enabled():
            # A person, movement, monument or event the book has no picture of: Wikipedia's picture of it.
            for subject in named_subjects(beat):
                if f"photo:{subject}" in showing or lookups <= 0:
                    continue
                lookups -= 1
                row = images.fetch(subject=subject)
                if row:
                    op = {"op": "photo", "subject": subject, "caption": subject}
                    script_photos[_photo_key(op)] = row
                    kit_op, showing = op, {f"photo:{subject}"}
                    break
        if kit_op:
            out.append(kit_op)
            continue
        # An educational illustration or diagram of what the beat explains (Commons, Openverse), kept up for
        # two beats: a picture that changes every sentence is hard to read.
        if hold <= 0 and lookups > 0 and images.enabled():
            for query in picture_queries(beat, chapter, genre, index):
                if f"query:{query}" in showing or lookups <= 0:
                    continue
                lookups -= 1
                row = images.fetch(illustration=query, avoid=USED_PICTURES, genre=genre, style=STYLE_NOW["style"])
                if row:
                    op = {"op": "illustration", "query": query, "caption": ""}
                    script_photos[_photo_key(op)] = row
                    USED_PICTURES.add(row["id"])
                    kit_op, showing, hold = op, {f"query:{query}"}, 1
                    break
            if kit_op:
                out.append(kit_op)
                continue
        out.append(None)
        hold -= 1
    return out


# Pictures a lecture has shown, so one diagram does not stand for several topics (reset per compile), and the
# lecture's style, which an AI illustration is drawn in.
USED_PICTURES: set = set()
STYLE_NOW = {"style": None}
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
        return f"self.mark({where}{label}{color}{side})"
    if kind == "river":
        color = f", {_colour(op.get('color'))}" if op.get("color") else ""
        return f"self.river({_q(op['name'])}{color})"
    if kind in ("path", "arrow"):
        pts = ", ".join(f"({float(x):g}, {float(y):g})" for x, y in op["points"])
        color = f", {_colour(op.get('color'))}" if op.get("color") else ""
        method = "path" if kind == "path" else "flow"
        return f"self.{method}([{pts}]{color})"
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
        events = ", ".join(f"({_q(d)}, {_q(l)})" for d, l in op["events"])
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
        return (f"self.figure({_q(figure['file'])}, {_q(caption)}, "
                f"where={_q(op.get('where', 'panel'))})")
    if kind == "graticule":
        axis = f"lat={float(op['lat']):g}" if op.get("lat") is not None else f"lon={float(op['lon']):g}"
        color = f", color={_colour(op.get('color'))}" if op.get("color") else ""
        label = f", label={_q(op['label'])}" if op.get("label") else ""
        return f"self.graticule({axis}{color}{label})"
    raise ValueError(kind)


script_figures: dict = {}


def compile_script(script: dict, scene_class: str = "GeneratedScene", engine_path: str | None = None) -> str:
    """The Manim source for a script. Raises ValueError with the lint errors."""
    errors, _ = lint(script)
    if errors:
        raise ValueError("\n".join(errors))
    script_figures.clear()
    script_figures.update(script.get("figures") or {})
    USED_PICTURES.clear()
    STYLE_NOW["style"] = script.get("style")
    import illustrations

    illustrations.reset()        # a new lecture: re-read the collections on disk, a fresh AI budget
    if script.get("place_figures", True):
        place_figures(script)
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
                   f"{_q(chapter['narration'])})")
        on_map = _map_chapter(chapter, bool(region))
        out.append("        self.show_map()" if on_map else "        self.add_panel()")
        fills = auto_visuals(chapter, genre=script.get("genre")) if script.get("auto_visuals", True) else []
        staged = False
        for bi, beat in enumerate(chapter.get("beats") or []):
            ops = list(beat.get("do") or [])
            if bi < len(fills) and fills[bi]:
                ops.append(fills[bi])
            points_at_map = any(op.get("op") in MAP_OPS or (op.get("op") == "icon" and _icon_spots(op)) for op in ops)
            calls = []
            if staged and points_at_map:
                calls.append("self.clear_stage()")      # back to the map
                staged = False
            for op in ops:
                if op.get("op") in ("photo", "illustration") and op.get("where", "stage") == "stage" or \
                        op.get("op") == "figure" and op.get("where") == "stage" or op.get("op") in KIT_OPS:
                    staged = True
            calls += [call for call in (_op_call(op) for op in ops) if call]
            args = "".join(f",\n                  {call}" for call in calls)
            rt = f", rt={float(beat['rt']):g}" if beat.get("rt") else ""
            out.append(f"        self.beat({_q(beat['say'])}{args}{rt})")
        out.append("        self.outro_fade()")
    if script.get("recap"):
        out += ["", "        # Recap"]
        points = ", ".join(f"({_q(h)}, {_q(b)})" for h, b in script["recap"])
        out.append(f"        self.section({len(sections) - 1})")
        out.append(f"        self.recap([{points}])")
    uses_icons = any(op.get("op") in ("icon", "illustration") for c in chapters for b in c.get("beats") or []
                     for op in b.get("do") or []) or any("illustration" in line for line in out)
    if script.get("credits") or uses_icons or script_photos:
        import images

        line = script.get("credits") or ("Map data: Natural Earth · Animation: Manim" if region else "Animation: Manim")
        photos = images.credit(script_photos.values())
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
    errors, warnings = lint(script, args.min_minutes)
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
