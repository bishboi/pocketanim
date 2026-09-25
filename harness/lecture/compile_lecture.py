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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STYLES = ("atlas", "vox", "cardboard", "whiteboard", "blueprint", "chalkboard")
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
    return 0.0


def lint(script: dict) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors stop compilation; warnings are layout advice.

    The checks the guide asks for before any render: unknown operations,
    map operations without a map, captions longer than two lines, a panel
    that overflows into the caption, a beat whose animations would outlast
    its narration.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if script.get("style", "atlas") not in STYLES:
        errors.append(f"style must be one of {', '.join(STYLES)}")
    has_map = bool(script.get("region"))
    chapters = script.get("chapters") or []
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
                if kind not in {"panel", "fact", "stat", "bars", "clear"} | MAP_OPS:
                    errors.append(f"{at}: unknown op {kind!r}")
                    continue
                if kind in MAP_OPS and not has_map:
                    errors.append(f"{at}: '{kind}' needs a map; give the script a region")
                if kind in MAP_OPS and not (chapter.get("map", True)):
                    errors.append(f"{at}: '{kind}' in a chapter with map=false")
                need = {"panel": ["title"], "fact": ["text"], "stat": ["value", "label"], "bars": ["items"],
                        "river": ["name"], "state": ["name"], "path": ["points"], "arrow": ["points"]}
                for field in need.get(kind, []):
                    if not op.get(field):
                        errors.append(f"{at}: '{kind}' needs {field}")
                if kind == "marker" and not (op.get("place") or op.get("lonlat")):
                    errors.append(f"{at}: 'marker' needs place or lonlat")
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
    return errors, warnings


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
    if kind == "graticule":
        axis = f"lat={float(op['lat']):g}" if op.get("lat") is not None else f"lon={float(op['lon']):g}"
        color = f", color={_colour(op.get('color'))}" if op.get("color") else ""
        label = f", label={_q(op['label'])}" if op.get("label") else ""
        return f"self.graticule({axis}{color}{label})"
    raise ValueError(kind)


def compile_script(script: dict, scene_class: str = "GeneratedScene", engine_path: str | None = None) -> str:
    """The Manim source for a script. Raises ValueError with the lint errors."""
    errors, _ = lint(script)
    if errors:
        raise ValueError("\n".join(errors))
    style = script.get("style", "atlas")
    region = script.get("region")
    chapters = script["chapters"]
    sections = ["Introduction"] + [c["title"] for c in chapters]
    if script.get("recap"):
        sections.append("Recap")
    base = "MapLecture" if region else "Lecture"

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
        if region and chapter.get("map", True):
            out.append("        self.show_map()")
        else:
            out.append("        self.add_panel()")
        for beat in chapter.get("beats") or []:
            calls = [_op_call(op) for op in beat.get("do") or []]
            args = "".join(f",\n                  {call}" for call in calls)
            rt = f", rt={float(beat['rt']):g}" if beat.get("rt") else ""
            out.append(f"        self.beat({_q(beat['say'])}{args}{rt})")
        out.append("        self.outro_fade()")
    if script.get("recap"):
        out += ["", "        # Recap"]
        points = ", ".join(f"({_q(h)}, {_q(b)})" for h, b in script["recap"])
        out.append(f"        self.section({len(sections) - 1})")
        out.append(f"        self.recap([{points}])")
    if script.get("credits"):
        out.append(f"        self.credits({_q(script['credits'])})")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("script")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true", help="lint only; print errors and warnings as JSON")
    ap.add_argument("--json", action="store_true",
                    help="print {source, errors, warnings} as one JSON object, for the harness app")
    ap.add_argument("--class", dest="scene_class", default="GeneratedScene")
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
    errors, warnings = lint(script)
    if args.json:
        source = None if errors else compile_script(script, args.scene_class)
        print(json.dumps({"source": source, "errors": errors, "warnings": warnings}))
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
