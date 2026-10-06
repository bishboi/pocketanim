"""Check SVG figures the model wrote (harness/app/lib/figures.ts) before a lecture uses them.

Each SVG is read the way the lecture engine will draw it (animsvg.make), so what passes here draws. Reported back
for each: whether it is usable, what is wrong (sent to the model to fix), its parts (the <g id> groups a lecture
reveals and points at) with the words in each, and whether it moves.

    python harness/lecture/svgcheck.py < figures.json      # {"figures": [{"id": "fig3", "svg": "path.svg"}]}
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

MAX_BYTES = 60_000
# What the engine cannot draw (or draws wrong): pictures inside, HTML, scripts, CSS, effects.
FORBIDDEN = {"image": "an embedded picture (draw it with shapes)", "foreignObject": "HTML inside the SVG",
             "script": "a script", "style": "a <style> sheet (put colours on the elements themselves)",
             "filter": "a filter effect", "mask": "a mask", "clipPath": "a clip path", "pattern": "a pattern fill",
             "animateMotion": "animateMotion (use animateTransform type=translate)"}


def check(svg_path: str) -> dict:
    import animsvg

    out = {"ok": False, "errors": [], "warnings": [], "parts": [], "labels": {}, "animated": False}
    path = Path(svg_path)
    if not path.is_file():
        out["errors"].append("no SVG was written")
        return out
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text.encode()) > MAX_BYTES:
        out["errors"].append(f"the SVG is {len(text.encode()) // 1000} KB; keep it under {MAX_BYTES // 1000} KB "
                             "(fewer, simpler shapes: a teaching diagram, not a picture)")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        out["errors"].append(f"not well-formed XML: {error}")
        return out
    if animsvg.local(root.tag) != "svg":
        out["errors"].append("the root element must be <svg>")
        return out
    if not root.get("viewBox"):
        out["errors"].append('the <svg> needs a viewBox (viewBox="0 0 800 500")')
    seen = {animsvg.local(el.tag) for el in root.iter()}
    for tag, what in FORBIDDEN.items():
        if tag in seen:
            out["errors"].append(f"it uses <{tag}>, {what}: the board cannot draw it")
    try:
        palette = {name: "#888888" for name in animsvg.TOKENS}
        doc = animsvg.Doc(animsvg.paint(text, palette))
    except Exception as error:  # noqa: BLE001 -- the reason goes back to the model
        out["errors"].append(f"cannot read it: {type(error).__name__}: {error}")
        return out
    if not doc.leaves:
        out["errors"].append("it draws nothing (no path, rect, circle, line, polyline, polygon or ellipse)")
        return out
    out["animated"] = bool(doc.anims)
    if doc.anims and not doc.quick:
        slow = sorted({a.attr for a in doc.anims if a.attr not in animsvg.QUICK})
        out["errors"].append(f"it animates {', '.join(slow)}: move parts with animateTransform (translate, rotate, "
                             "scale) and fade them with opacity instead, so its parts can still be revealed")
    try:
        drawing = animsvg.make(animsvg.paint(text, palette), height=4.0, strokes=True)
    except Exception as error:  # noqa: BLE001
        out["errors"].append(f"cannot draw it: {type(error).__name__}: {error}")
        return out
    if not drawing.quick:
        out["warnings"].append("some shapes could not be told apart, so the figure shows as one part")
    parts, _ = drawing.parts()
    out["parts"] = list(parts)
    for key in parts:
        words = [doc.text_spec(el)["text"] for el in doc.texts if doc.part_of(el) == key]
        out["labels"][key] = " / ".join(words)[:80]
    if len(out["parts"]) < 2 and len(doc.leaves) > 3:
        out["errors"].append('group the figure\'s parts in <g id="..."> (a short id for each thing the lecture '
                             "will point at: the block, each force, each label's object)")
    if not doc.texts:
        out["warnings"].append("it has no <text> labels")
    out["ok"] = not out["errors"]
    return out


def main() -> int:
    request = json.load(sys.stdin)
    results = {}
    for figure in request.get("figures", []):
        try:
            results[figure["id"]] = check(figure["svg"])
        except Exception as error:  # noqa: BLE001 -- one bad figure does not stop the others
            results[figure["id"]] = {"ok": False, "errors": [f"{type(error).__name__}: {error}"], "parts": []}
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
