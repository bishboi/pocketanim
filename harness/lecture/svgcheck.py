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

MAX_BYTES = 100_000
# What the engine cannot draw (or draws wrong): pictures inside, HTML, scripts, CSS, effects.
FORBIDDEN = {"image": "an embedded picture (draw it with shapes)", "foreignObject": "HTML inside the SVG",
             "script": "a script", "style": "a <style> sheet (put colours on the elements themselves)",
             "filter": "a filter effect", "mask": "a mask", "clipPath": "a clip path", "pattern": "a pattern fill",
             "animateMotion": "animateMotion (use animateTransform type=translate)"}


def check(svg_path: str, expected: list[str] | None = None) -> dict:
    import animsvg

    out = {"ok": False, "errors": [], "warnings": [], "parts": [], "labels": {}, "animated": False}
    path = Path(svg_path)
    if not path.is_file():
        out["errors"].append("no SVG was written")
        return out
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text.encode()) > MAX_BYTES:
        out["errors"].append(f"the SVG is {len(text.encode()) // 1000} KB; keep it under {MAX_BYTES // 1000} KB "
                             "(whole-number coordinates, short path data, repeated detail such as veins or threads in one path each)")
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
    # Readable on a phone: a label's font-size, against the drawing's width, at least about 20 in an 800-wide picture.
    width = (animsvg._nums(root.get("viewBox")) + [0, 0, 800, 600])[2] or 800
    small = [doc.text_spec(el)["text"] for el in doc.texts if doc.text_spec(el)["size"] < 0.022 * width]
    if small:
        out["errors"].append(f"labels too small to read on a phone ({', '.join(repr(t) for t in small[:4])}): "
                             f"font-size at least {round(0.025 * width)} in this viewBox")
    missing = [p for p in expected or [] if p not in out["parts"]]
    if missing:
        # The lecture already reveals and points at these by id: each must be a group of its own.
        out["errors"].append(f"it has no part {', '.join(missing)}: wrap each in <g id=\"...\"> with exactly that id "
                             f"(the parts are {', '.join(expected)})")
    out["ok"] = not out["errors"]
    return out


def board(svg_path: str, style: str = "chalkboard"):
    """The drawing exactly as the lecture's board draws it (pocket_lecture.board_svg), in a 16:9 frame."""
    import pocket_lecture as pl

    pl.use_style(style)
    return pl.board_svg(svg_path, 13.0, 6.8)


def overlaps(drawing) -> list[str]:
    """Labels that sit on each other, as the board sets them (its own font, its own sizes)."""
    boxes = []
    for el, mob, *_ in getattr(drawing, "labels", []):
        words = " ".join("".join(el.itertext()).split())
        (x0, y0), (x1, y1) = mob.get_corner([-1, -1, 0])[:2], mob.get_corner([1, 1, 0])[:2]
        boxes.append((words, x0, y0, x1, y1))
    out = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            # Overlapping by more than a sliver (a fifth of the smaller label's height) both ways.
            pad = 0.2 * min(a[4] - a[2], b[4] - b[2])
            if a[1] < b[3] - pad and b[1] < a[3] - pad and a[2] < b[4] - pad and b[2] < a[4] - pad:
                out.append(f"{a[0]!r} and {b[0]!r}")
    return out


def preview(drawing, png_path: str) -> None:
    """A still of the drawing on the board (its first frame), for the model to look at its own picture."""
    from manim import config
    from manim.camera.camera import Camera

    import pocket_lecture as pl

    config.pixel_width, config.pixel_height = 1280, 720
    camera = Camera(background_color=pl.P.BG)
    camera.capture_mobjects([drawing])
    camera.get_image().convert("RGB").save(png_path)


def main() -> int:
    request = json.load(sys.stdin)
    results = {}
    for figure in request.get("figures", []):
        try:
            result = check(figure["svg"], figure.get("parts"))
            if result.get("ok") and (figure.get("preview") or figure.get("layout", True)):
                drawing = board(figure["svg"], figure.get("style") or "chalkboard")
                clash = overlaps(drawing)
                if clash:
                    result["errors"].append(f"labels overlap: {'; '.join(clash[:4])}. Move them apart (or shorten "
                                            "them) so each sits clear beside what it names")
                    result["ok"] = False
                # Labels the board could not move clear of a line: shown on a patch of the board, but the drawing
                # should leave them room (figures.ts puts this in the look-and-fix round).
                crossed = [" ".join("".join(el.itertext()).split()) for el, mob, *_ in getattr(drawing, "labels", [])
                           if getattr(mob, "backed", False)]
                if crossed:
                    result.setdefault("warnings", []).append(
                        f"labels on a line or a shape: {', '.join(repr(c) for c in crossed[:6])}. Give each room "
                        "beside what it names, clear of every line and arrow (a thin leader line if it must sit apart)")
                if figure.get("preview"):
                    preview(drawing, figure["preview"])
                    result["preview"] = figure["preview"]
            results[figure["id"]] = result
        except Exception as error:  # noqa: BLE001 -- one bad figure does not stop the others
            results[figure["id"]] = {"ok": False, "errors": [f"{type(error).__name__}: {error}"], "parts": []}
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
