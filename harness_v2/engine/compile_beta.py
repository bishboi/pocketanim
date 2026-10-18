"""Compile a beta-engine script (BETA_ENGINE.md) into a Manim scene on beta_engine.BetaLecture.

    python compile_beta.py script.json -o scene.py
    python compile_beta.py - --json < script.json      # {"source", "errors", "warnings", "minutes", ...}

The script is the beat script's frame (title, style, art, chapters, each with its beats and their `say`), with each
beat's visuals as slides of boxes: `layout` (starts a slide), `elements` (what the slide holds, each in a slot or a
box), `animate` (how and on which words each comes on, is pointed at, leaves or moves), `clear`. What cannot be
used is mended or left out with a warning, so a script always plays; only a script with no words to say is refused.
Pictures are made here, as compile_lecture makes them (images.fetch, genimage.locate for their labels).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import beta_engine as be

HERE = Path(__file__).resolve().parent
WPM = 143
ALIASES = {"bullets": "list", "points": "list", "picture": "image", "photo": "image", "chart": "bars",
           "formula": "equation", "stat": "number"}
STEP_KEYS = ("in", "emphasis", "out", "move")


def _q(text) -> str:
    return json.dumps(str(text), ensure_ascii=False)


def _kind(el: dict) -> str | None:
    """An element's kind: given as `kind`, or the key that holds its content ({"text": ...}, {"list": [...]})."""
    kind = el.get("kind")
    kind = ALIASES.get(kind, kind)
    if kind in be.ELEMENT_KINDS:
        return kind
    # "text" last: a shape, a number or an icon may carry words of its own.
    for key in [k for k in be.ELEMENT_KINDS if k != "text"] + list(ALIASES) + ["text"]:
        if key in el:
            return ALIASES.get(key, key)
    return None


def _element(el: dict, where: str, slots: dict, say: str, script: dict, notes: list) -> dict | None:
    """One element as the runtime builds it ({id, kind, slot|box, ...}), or None (with a note) when unusable."""
    if not isinstance(el, dict):
        notes.append(f"{where}: an element must be an object, left out")
        return None
    eid = str(el.get("id") or "").strip()
    kind = _kind(el)
    if not eid or not re.fullmatch(r"[\w-]+", eid):
        notes.append(f"{where}: an element needs an id (letters, digits, - or _), left out")
        return None
    if kind is None:
        notes.append(f"{where}: element {eid!r} has no kind (one of {', '.join(be.ELEMENT_KINDS)}), left out")
        return None
    out: dict = {"id": eid, "kind": kind}
    box = el.get("box")
    if box is not None:
        if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box) \
                and 0 <= box[0] < 1 and 0 <= box[1] < 1 and 0 < box[2] <= 1 and 0 < box[3] <= 1:
            out["box"] = [float(min(v, 1)) for v in box]
        else:
            notes.append(f"{where}: {eid!r} box must be [x, y, w, h] as shares of the board (0-1); put in a slot")
    if "box" not in out and kind != "arrow":
        slot = el.get("slot")
        if slot not in slots:
            if slot is not None:
                notes.append(f"{where}: {eid!r} slot {slot!r} is not in this layout ({', '.join(slots)}); "
                             f"put in {next(iter(slots))!r}")
            slot = next(iter(slots))
        out["slot"] = slot
    for key in ("color", "align", "style"):
        if el.get(key):
            out[key] = el[key]
    value = el.get(kind) if kind in el else next((el[a] for a, k in ALIASES.items() if k == kind and a in el), None)
    if kind == "text":
        text = el.get("text") if isinstance(el.get("text"), str) else value
        if not str(text or "").strip():
            notes.append(f"{where}: text {eid!r} has no words, left out")
            return None
        out["text"] = str(text)
        if out.get("style") not in be.TEXT_STYLES:
            if out.get("style"):
                notes.append(f"{where}: {eid!r} style {out['style']!r} unknown ({', '.join(be.TEXT_STYLES)}); body")
            out["style"] = "body"
    elif kind == "list":
        items = el.get("items") if isinstance(el.get("items"), list) else value if isinstance(value, list) else []
        items = [str(x) for x in items if str(x).strip()]
        if not items:
            notes.append(f"{where}: list {eid!r} has no items, left out")
            return None
        if len(items) > 8:
            notes.append(f"{where}: list {eid!r} has {len(items)} items, the first 8 kept")
        out["items"] = items[:8]
        out["numbered"] = bool(el.get("numbered"))
    elif kind == "number":
        spec = value if isinstance(value, dict) else {"value": value if value is not None else el.get("value")}
        if spec.get("value") in (None, ""):
            notes.append(f"{where}: number {eid!r} has no value, left out")
            return None
        out["value"] = str(spec["value"])
        if spec.get("label") or el.get("label"):
            out["label"] = str(spec.get("label") or el.get("label"))
    elif kind == "shape":
        shape = value if isinstance(value, str) else el.get("shape") or "box"
        out["shape"] = shape if shape in ("box", "circle", "pill") else "box"
        if el.get("text"):
            out["text"] = str(el["text"])
    elif kind == "equation":
        tex = value if isinstance(value, str) else el.get("tex")
        if not str(tex or "").strip():
            notes.append(f"{where}: equation {eid!r} has no tex, left out")
            return None
        out["tex"] = str(tex)
        if el.get("label"):
            out["label"] = str(el["label"])
    elif kind == "bars":
        spec = value if isinstance(value, dict) else {"items": value if isinstance(value, list) else el.get("items")}
        rows = []
        for row in spec.get("items") or []:
            label, number = (row.get("label"), row.get("value")) if isinstance(row, dict) else \
                (row[0], row[1]) if isinstance(row, (list, tuple)) and len(row) >= 2 else (None, None)
            try:
                rows.append([str(label), float(number)])
            except (TypeError, ValueError):
                continue
        if not rows:
            notes.append(f"{where}: bars {eid!r} need items [[label, number], ...], left out")
            return None
        out["items"] = rows[:8]
        if spec.get("title") or el.get("title"):
            out["title"] = str(spec.get("title") or el.get("title"))
    elif kind == "icon":
        name = value if isinstance(value, str) else el.get("name")
        if not str(name or "").strip():
            notes.append(f"{where}: icon {eid!r} has no name, left out")
            return None
        out["name"] = str(name)
        if el.get("label"):
            out["label"] = str(el["label"])
    elif kind == "arrow":
        spec = value if isinstance(value, dict) else el
        if not spec.get("from") or not spec.get("to"):
            notes.append(f"{where}: arrow {eid!r} needs from and to (element ids), left out")
            return None
        out.update({"from": str(spec["from"]), "to": str(spec["to"])})
        if spec.get("label"):
            out["label"] = str(spec["label"])
    elif kind == "timeline":
        spec = value if isinstance(value, dict) else el
        events = []
        for e in spec.get("events") or []:
            if isinstance(e, dict) and e.get("date") and e.get("label"):
                events.append([str(e["date"]), str(e["label"])])
            elif isinstance(e, (list, tuple)) and len(e) >= 2:
                events.append([str(e[0]), str(e[1])])
        if len(events) < 2:
            notes.append(f"{where}: timeline {eid!r} needs at least 2 events, left out")
            return None
        out["events"] = events[:10]
        for key in ("title", "range", "spans", "scale"):
            if spec.get(key):
                out[key] = spec[key]
    elif kind == "image":
        return _image(el, value, out, where, say, script, notes)
    return out


def _image(el: dict, value, out: dict, where: str, say: str, script: dict, notes: list) -> dict | None:
    """A picture: made by the image model ({"generate": ...}), one of the book's figures ({"figure": id}) or a file;
    its labels located on it (genimage.locate)."""
    spec = value if isinstance(value, dict) else {"generate": value} if isinstance(value, str) else el
    labels = [str(x).strip()[:32] for x in spec.get("labels") or el.get("labels") or [] if str(x).strip()][:6]
    file = None
    if spec.get("figure"):
        figure = (script.get("figures") or {}).get(str(spec["figure"]))
        file = figure.get("file") if isinstance(figure, dict) else None
        if not file:
            notes.append(f"{where}: image {out['id']!r}: no figure {spec['figure']!r} in this lecture, left out")
            return None
    elif spec.get("file"):
        file = str(spec["file"]) if Path(str(spec["file"])).is_file() else None
        if not file:
            notes.append(f"{where}: image {out['id']!r}: no file {spec['file']!r}, left out")
            return None
    elif spec.get("generate"):
        import images

        row = images.fetch(subject=str(spec["generate"]), parts=labels or None, context=say,
                           scene=bool(spec.get("scene")), aspect=spec.get("aspect"))
        file = (row or {}).get("png") or (row or {}).get("file")
        if not file:
            notes.append(f"{where}: image {out['id']!r}: the image model gave no picture of "
                         f"{str(spec['generate'])[:60]!r}, left out")
            return None
    else:
        notes.append(f"{where}: image {out['id']!r} needs generate, figure or file, left out")
        return None
    out["file"] = str(file)
    if spec.get("scene"):
        out["scene"] = True
    if labels and re.search(r"\.(png|jpe?g|webp)$", str(file), re.I):
        import genimage

        found = genimage.locate(str(file), labels)
        if found:
            out["labels"] = found
            missed = [x for x in labels if x not in {str(r[0]) for r in found}]
            if missed:
                notes.append(f"{where}: image {out['id']!r}: not found on the picture, so not labelled: "
                             f"{', '.join(missed)}")
        else:
            notes.append(f"{where}: image {out['id']!r}: its labels could not be placed (no model to find the parts)")
    return out


def _step(step, where: str, known: set, parts_of: dict, say: str, notes: list) -> dict | None:
    """One animation step, checked: its target on the slide, its preset known, its word in the line."""
    if not isinstance(step, dict):
        notes.append(f"{where}: an animate step must be an object, left out")
        return None
    ref = str(step.get("id") or "").strip()
    head = ref.split(".")[0]
    if head not in known:
        notes.append(f"{where}: animate names {ref!r}, which is not on this slide, left out")
        return None
    if "." in ref and parts_of.get(head) is not None and ref.split(".", 1)[1] not in parts_of[head]:
        notes.append(f"{where}: {head!r} has no part {ref.split('.', 1)[1]!r} (its parts: "
                     f"{', '.join(parts_of[head]) or 'none'}), left out")
        return None
    out = {"id": ref}
    given = [k for k in STEP_KEYS if step.get(k)]
    key = given[0] if given else "in"
    value = step.get(key) or "fade"
    allowed = {"in": be.ENTRANCES, "emphasis": be.EMPHASES, "out": be.EXITS}.get(key)
    if allowed and value not in allowed:
        notes.append(f"{where}: {ref!r} {key} {value!r} unknown (one of {', '.join(allowed)}); "
                     f"{'fade' if key != 'emphasis' else 'pulse'}")
        value = "fade" if key != "emphasis" else "pulse"
    out[key] = value
    for k in ("from", "to", "color", "with", "after"):
        if step.get(k):
            out[k] = str(step[k])
    for k in ("delay", "dur"):
        if step.get(k) is not None:
            try:
                out[k] = max(0.0, min(float(step[k]), 6.0))
            except (TypeError, ValueError):
                pass
    if step.get("on"):
        phrase = str(step["on"]).strip()
        words = re.findall(r"[\w']+", phrase.lower())
        line = re.findall(r"[\w']+", say.lower())
        if words and not any(line[i:i + len(words)] == words for i in range(len(line))):
            notes.append(f"{where}: {ref!r} is on {phrase!r}, which the line does not say: it follows the step "
                         f"before")
        else:
            out["on"] = phrase
    return out


def _parts_of(el: dict) -> list | None:
    """The parts an element's id.part names: a list's or a chart's items by number, a picture's labels by name."""
    if el["kind"] in ("list", "bars"):
        return [str(i) for i in range(len(el["items"]))]
    if el["kind"] == "image":
        return [be._slug(r[0]) for r in el.get("labels") or []]
    return None


def lint_and_build(script: dict) -> tuple[list, list, list]:
    """(errors, warnings, chapters as [{title, narration, steps: [("slide", layout, elements) | ("beat", say,
    spec, pause)]}])."""
    errors, notes = [], []
    chapters_out = []
    chapters = script.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return ["the script needs chapters: [{title, beats: [...]}]"], [], []
    for ci, chapter in enumerate(chapters, 1):
        beats = chapter.get("beats") if isinstance(chapter, dict) else None
        if not isinstance(beats, list) or not beats:
            errors.append(f"chapter {ci}: it needs beats")
            continue
        steps: list = []
        slide_at = None             # index into steps of the slide being filled
        slide_layout = "full"
        known: set = set()
        parts_of: dict = {}
        for bi, beat in enumerate(beats, 1):
            where = f"chapter {ci} beat {bi}"
            say = str((beat or {}).get("say") or "").strip() if isinstance(beat, dict) else ""
            if not say:
                errors.append(f"{where}: it needs say (the words said)")
                continue
            layout = beat.get("layout")
            if layout is not None and layout not in be.LAYOUTS:
                notes.append(f"{where}: layout {layout!r} unknown ({', '.join(be.LAYOUTS)}); full")
                layout = "full"
            if layout is not None or slide_at is None:
                slide_layout = layout or "full"
                steps.append(("slide", slide_layout, []))
                slide_at = len(steps) - 1
                known, parts_of = set(), {}
            slots = be.LAYOUTS[slide_layout]
            enter = []
            for el in beat.get("elements") or []:
                made = _element(el, where, slots, say, script, notes)
                if made is None:
                    continue
                if made["id"] in known:
                    notes.append(f"{where}: {made['id']!r} is already on this slide, left out (start a new slide "
                                 f"with a layout to use the id again)")
                    continue
                if made["kind"] == "arrow" and not {made["from"], made["to"]} <= known | {e["id"] for e in
                                                                                         steps[slide_at][2]}:
                    notes.append(f"{where}: arrow {made['id']!r} joins an element not on this slide, left out")
                    continue
                steps[slide_at][2].append(made)
                known.add(made["id"])
                parts_of[made["id"]] = _parts_of(made)
                enter.append(made["id"])
            animate = []
            for step in beat.get("animate") or []:
                checked = _step(step, where, known, parts_of, say, notes)
                if checked is not None:
                    animate.append(checked)
            spec: dict = {"enter": enter, "animate": animate}
            if beat.get("clear"):
                spec["clear"] = True
            try:
                pause = max(0.0, min(float(beat.get("pause") or 0), 2.0))
            except (TypeError, ValueError):
                pause = 0.0
            steps.append(("beat", say, spec, pause))
        chapters_out.append({"title": str(chapter.get("title") or f"Chapter {ci}"),
                             "narration": str(chapter.get("narration") or chapter.get("title") or ""),
                             "steps": steps})
    return errors, notes, chapters_out


def compile_source(script: dict, chapters: list, scene_class: str = "GeneratedScene") -> str:
    out = [
        f'"""{script.get("title", "Lecture")}: compiled from a beta-engine script by compile_beta.py."""',
        "import os",
        "import sys",
        "",
        f"os.environ.setdefault(\"LECTURE_STYLE\", {_q(script.get('style') or 'chalkboard')})",
        f"os.environ.setdefault(\"LECTURE_ART\", {_q(str(script.get('art') or 'auto'))})",
        "from manim import *  # noqa: E402,F403",
        "from pocket_lecture import *  # noqa: E402,F403",
        "from beta_engine import BetaLecture  # noqa: E402",
        "",
        "",
        f"class {scene_class}(BetaLecture):",
        f"    SECTIONS = {['Introduction'] + [c['title'] for c in chapters]!r}",
        "",
        "    def construct(self):",
    ]
    if script.get("title"):
        intro = script.get("intro") or f"{script['title']}. {script.get('sub', '')}".strip()
        out.append(f"        self.title_slide({_q(script['title'])}, {_q(script.get('sub', ''))}, narration={_q(intro)})")
    for index, chapter in enumerate(chapters, 1):
        out += ["", f"        # {index:02d}  {' '.join(chapter['title'].split())}",
                f"        self.chapter({index}, {_q(chapter['title'])}, \"\", {_q(chapter['narration'])})",
                "        self.board()"]
        for step in chapter["steps"]:
            if step[0] == "slide":
                out.append(f"        self.beta_slide({_q(step[1])}, {step[2]!r})")
            else:
                _, say, spec, pause = step
                pad = f", pad=BEAT_PAD + {pause:g}" if pause else ""
                out.append(f"        self.beat({_q(say)}, spec={spec!r}{pad})")
    if script.get("title"):
        out.append("        self.outro_fade()")
    return "\n".join(out) + "\n"


def minutes(chapters: list) -> float:
    words = sum(len(s[1].split()) for c in chapters for s in c["steps"] if s[0] == "beat")
    return words / WPM


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("script")
    ap.add_argument("-o", "--out")
    ap.add_argument("--json", action="store_true", help="print {source, errors, warnings, minutes, ...} as JSON")
    ap.add_argument("--class", dest="scene_class", default="GeneratedScene")
    args = ap.parse_args()
    text = sys.stdin.read() if args.script == "-" else Path(args.script).read_text()
    try:
        script = json.loads(text)
        if not isinstance(script, dict):
            raise ValueError("the script must be a JSON object")
    except ValueError as error:
        if args.json:
            print(json.dumps({"source": None, "errors": [f"not a JSON beta script: {error}"], "warnings": []}))
            return 1
        raise
    os.environ.setdefault("LECTURE_STYLE", str(script.get("style") or "chalkboard"))
    errors, warnings, chapters = lint_and_build(script)
    source = None if errors else compile_source(script, chapters, args.scene_class)
    if args.json:
        import genimage

        print(json.dumps({"source": source, "errors": errors, "warnings": warnings,
                          "minutes": round(minutes(chapters), 2), "engine": "beta",
                          "generated": genimage.MADE, "images": genimage.report()}))
        return 1 if errors else 0
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    for warning in warnings:
        print("warning:", warning, file=sys.stderr)
    if args.out:
        Path(args.out).write_text(source)
    else:
        sys.stdout.write(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
