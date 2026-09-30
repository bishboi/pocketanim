"""Check a lecture's layout at the end of every beat: text on text, text or drawings on pictures, text off the frame.

A lecture is laid out by code, not by eye, and a layout bug shows only in some beats of some lectures. This
plays the scene with its animations skipped (each one jumps to its end state, so a 20-minute lecture takes
a minute or two), and after every narration beat measures what is on screen:

- text over text: two labels, lines or captions whose boxes overlap;
- over a picture: text, or part of a drawing, on a photo or a PDF figure;
- off the frame: text that runs past the frame's safe margin;
- over a line: a drawing's line running through a label (reported, not counted as an error).

It prints one line per problem and a summary, and writes `audit.json`. With `--frames`, it also saves a
picture of every beat's end, and a contact sheet of them, so the problems can be seen.

    .venv/bin/python harness/scripts/lecture_audit.py scene.py GeneratedScene out/ [--frames]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lecture"))

FRAME_W, FRAME_H = 14.222222222222221, 8.0
EDGE = 0.08          # how far past the frame's edge text may reach
TEXT_TYPES = ("Text", "MarkupText", "Paragraph", "MathTex", "Tex", "SingleStringMathTex", "DecimalNumber",
              "Integer")


def _box(mob):
    low, high = mob.get_corner([-1, -1, 0]), mob.get_corner([1, 1, 0])
    return float(low[0]), float(low[1]), float(high[0]), float(high[1])


def _overlap(a, b) -> float:
    """The overlapping area as a share of the smaller box."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return (w * h) / smaller if smaller > 1e-6 else 0.0


def _grow(box, by: float):
    return box[0] - by, box[1] - by, box[2] + by, box[3] + by


def _visible(mob) -> bool:
    if type(mob).__name__ == "ImageMobject":
        return float(mob.__dict__.get("fill_opacity", 1.0)) > 0.1
    try:
        fill = float(mob.get_fill_opacity())
    except Exception:  # noqa: BLE001
        fill = 0.0
    try:
        stroke = float(mob.get_stroke_opacity()) if float(mob.get_stroke_width()) > 0 else 0.0
    except Exception:  # noqa: BLE001
        stroke = 0.0
    return max(fill, stroke) > 0.1


def _units(scene):
    """What is on screen, as (kind, owner, mobject): text units, pictures, and the leaves of drawings."""
    out = []

    def walk(mob, owner):
        name = type(mob).__name__
        if name in TEXT_TYPES:
            leaves = [m for m in mob.family_members_with_points() if _visible(m)]
            if leaves:
                out.append(("text", owner, mob, leaves))
            return
        if name == "ImageMobject":
            if _visible(mob):
                out.append(("image", owner, mob, None))
            return
        if len(mob.points) and _visible(mob):
            out.append(("ink", owner, mob, None))
        for sub in mob.submobjects:
            walk(sub, owner)

    for index, top in enumerate(scene.mobjects):
        if not getattr(top, "is_backdrop", False):
            walk(top, index)
    return out


def _text_box(leaves):
    import numpy as np

    pts = np.vstack([m.points for m in leaves])
    return float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())


def _crosses(mob, box, inset: float = 0.04) -> bool:
    """A line's points pass through the inside of a box."""
    from stem import curve_samples

    if len(mob.points) < 2:
        return False
    samples = curve_samples(mob.points)
    x0, y0, x1, y1 = box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset
    inside = (samples[:, 0] > x0) & (samples[:, 0] < x1) & (samples[:, 1] > y0) & (samples[:, 1] < y1)
    return bool(inside.any())


def _is_backing(mob, text_boxes) -> bool:
    """A filled card or box that text sits on by design (a caption's backing, an option's box)."""
    try:
        return float(mob.get_fill_opacity()) > 0.1 and any(
            _overlap(_box(mob), t) > 0.9 and (_box(mob)[2] - _box(mob)[0]) >= (t[2] - t[0]) for t in text_boxes)
    except Exception:  # noqa: BLE001
        return False


def check(scene) -> list[dict]:
    """The layout problems on screen now."""
    units = _units(scene)
    texts = [(owner, mob, _text_box(leaves)) for kind, owner, mob, leaves in units if kind == "text"]
    images = [(owner, mob, _box(mob)) for kind, owner, mob, _ in units if kind == "image"]
    inks = [(owner, mob) for kind, owner, mob, _ in units if kind == "ink"]
    found = []

    def name(mob):
        text = getattr(mob, "text", None) or getattr(mob, "tex_string", None) or type(mob).__name__
        return str(text)[:40]

    for i, (oa, a, ba) in enumerate(texts):
        if ba[0] < -FRAME_W / 2 - EDGE or ba[2] > FRAME_W / 2 + EDGE or ba[1] < -FRAME_H / 2 - EDGE \
                or ba[3] > FRAME_H / 2 + EDGE:
            found.append({"kind": "off the frame", "a": name(a), "box": [round(v, 2) for v in ba]})
        for ob, b, bb in texts[i + 1:]:
            share = _overlap(ba, bb)
            if share > 0.12:
                found.append({"kind": "text over text", "a": name(a), "b": name(b), "share": round(share, 2)})
            elif _overlap(_grow(ba, 0.04), _grow(bb, 0.04)) > 0.02:
                found.append({"kind": "text touching text", "a": name(a), "b": name(b)})
        for oi, image, bi in images:
            if _overlap(ba, bi) > 0.12:
                found.append({"kind": "text over a picture", "a": name(a), "b": "picture",
                              "share": round(_overlap(ba, bi), 2)})
    for i, (oa, a, ba) in enumerate(images):
        for ob, b, bb in images[i + 1:]:
            if _overlap(ba, bb) > 0.05:
                found.append({"kind": "picture over picture", "share": round(_overlap(ba, bb), 2)})
    text_boxes = [bt for _, _, bt in texts]
    frames_of = {id(i): None for _, i, _ in images}
    for owner, ink in inks:
        box = _box(ink)
        if (box[2] - box[0]) > FRAME_W * 0.9 and (box[3] - box[1]) > FRAME_H * 0.9:
            continue            # the backdrop
        for oi, image, bi in images:
            # A picture's own frame hugs it; anything else drawn on it covers the picture.
            if _overlap(box, bi) > 0.2 and not (abs(box[0] - bi[0]) < 0.05 and abs(box[2] - bi[2]) < 0.05):
                if (box[2] - box[0]) * (box[3] - box[1]) > 0.02 and not _is_backing(ink, [bi]):
                    found.append({"kind": "drawing over a picture", "a": type(ink).__name__,
                                  "share": round(_overlap(box, bi), 2)})
                    break
        if _is_backing(ink, text_boxes):
            continue
        for ot, text, bt in texts:
            if type(ink).__name__ in ("Rectangle", "RoundedRectangle", "SurroundingRectangle", "BackgroundRectangle"):
                # A box round text (an answer ring, an option) is fine; one edge cutting through it is not.
                if _overlap(box, bt) > 0.95:
                    continue
            if _crosses(ink, bt):
                found.append({"kind": "line through text", "a": name(text), "b": type(ink).__name__})
                break
    del frames_of
    return found


SERIOUS = {"text over text", "text over a picture", "off the frame", "picture over picture",
           "drawing over a picture"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scene_file")
    parser.add_argument("scene_class")
    parser.add_argument("out", nargs="?", default="audit")
    parser.add_argument("--frames", action="store_true", help="save a picture of every beat's end")
    parser.add_argument("--quiet", action="store_true", help="only the summary")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PANIM_VOICE", "silent")
    scene_path = Path(args.scene_file).resolve()
    sys.path.insert(0, str(scene_path.parent))

    import nolatex

    nolatex.install()
    from manim import config, tempconfig

    import pocket_lecture as pl

    beats: list[dict] = []
    original_beat = pl.MapLecture.beat

    def beat(self, text, *anims, **kw):
        result = original_beat(self, text, *anims, **kw)
        index = len(beats)
        problems = check(self)
        record = {"beat": index, "text": text[:80], "problems": problems}
        beats.append(record)
        if args.frames:
            from PIL import Image

            self.renderer.update_frame(self, ignore_skipping=True)
            Image.fromarray(self.renderer.get_frame()).save(out / f"beat{index:03d}.png")
        return result

    pl.MapLecture.beat = beat

    import importlib.util

    spec = importlib.util.spec_from_file_location("audited_scene", scene_path)
    module = importlib.util.module_from_spec(spec)
    with tempconfig({"quality": "low_quality", "write_to_movie": False, "save_last_frame": False,
                     "disable_caching": True, "media_dir": str(out / "media"), "verbosity": "ERROR",
                     "progress_bar": "none"}):
        config.skip_animations = True
        spec.loader.exec_module(module)
        scene = getattr(module, args.scene_class)()
        scene.renderer.skip_animations = True
        scene.renderer._original_skipping_status = True
        scene.render()

    serious = 0
    for record in beats:
        for problem in record["problems"]:
            if problem["kind"] in SERIOUS:
                serious += 1
            if not args.quiet:
                print(f"beat {record['beat']:3d}  {problem['kind']:22s} {problem.get('a', '')!r} "
                      f"{problem.get('b', '')!r} {problem.get('share', '')}")
    (out / "audit.json").write_text(json.dumps(beats, ensure_ascii=False, indent=1))
    if args.frames and beats:
        _sheet(out, len(beats))
    kinds: dict = {}
    for record in beats:
        for problem in record["problems"]:
            kinds[problem["kind"]] = kinds.get(problem["kind"], 0) + 1
    print(json.dumps({"beats": len(beats), "serious": serious, "by_kind": kinds}, ensure_ascii=False))
    return 1 if serious else 0


def _sheet(out: Path, count: int, columns: int = 4, rows: int = 4) -> None:
    """Contact sheets of the beat pictures, 16 to a page, each numbered."""
    from PIL import Image, ImageDraw

    per = columns * rows
    for page in range(0, count, per):
        tiles = [Image.open(out / f"beat{i:03d}.png").convert("RGB") for i in range(page, min(page + per, count))]
        w, h = 427, 240
        sheet = Image.new("RGB", (w * columns, h * rows), "black")
        for k, tile in enumerate(tiles):
            tile = tile.resize((w, h))
            ImageDraw.Draw(tile).text((4, h - 14), str(page + k), fill=(255, 80, 80))
            sheet.paste(tile, ((k % columns) * w, (k // columns) * h))
        sheet.save(out / f"sheet{page // per:02d}.png")


if __name__ == "__main__":
    raise SystemExit(main())
