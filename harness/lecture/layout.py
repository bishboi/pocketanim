"""Nothing drawn over anything else: the lecture engine's layout pass, run on every line before it plays.

Each part of the engine lays out its own things (the stage's picture and its labels, the panel's points, the map's
places), and each does that well; what none of them sees is the others, nor what an earlier line left on the screen.
So before a line's pictures play, this pass looks at what the line brings on and at what is already there, and
settles every clash before anything is drawn:

  - what the line brings on is kept inside the frame (above the caption, under the chapter's heading);
  - a thing left over from an earlier line (a card, a stat, a quote, a free drawing's leftover) that the new one
    would cover goes as the line begins, instead of sitting under it;
  - a thing of its own the line brings on that lands on something that stays is moved to the nearest clear place
    (or made a little smaller), where it can be;
  - what cannot be settled that way (two of the engine's own layouts on each other) is counted and logged, with
    the line, so it is seen and mended in the layout that made it.

Things are compared by their ink: words, pictures and filled shapes, not the empty boxes round them; lines and
outlines may cross. A layout's own parts (a diagram's nodes, a map's labels, a picture's labels) are that layout's
business and are not compared with each other.
"""

from __future__ import annotations

import json
import os

import numpy as np

BIG = 0.5              # share of the frame past which a filled shape is a backdrop, not a thing
HIT = 0.04             # share of the smaller of two inks they may share before it is a clash
GAP = 0.06             # what a moved thing keeps clear of others by
STEPS = (0.15, 0.3, 0.45, 0.6, 0.8, 1.0, 1.3, 1.6)


def _box(mob):
    lo, hi = mob.get_corner([-1, -1, 0]), mob.get_corner([1, 1, 0])
    box = (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))
    if not all(np.isfinite(box)) or box[2] - box[0] < 1e-3 and box[3] - box[1] < 1e-3:
        return None
    return box


def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _shared(a, b) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def ink(mob, frame_area: float) -> list:
    """Boxes of what a mobject really shows: its words (each text whole), its pictures, its filled shapes; not what
    is decoration (_art_decorated), a backdrop, a cover, or see-through."""
    from manim import ImageMobject, Text

    out = []

    def walk(m) -> None:
        if getattr(m, "_art_decorated", False) or getattr(m, "is_map_cover", False):
            return
        if isinstance(m, (ImageMobject, Text)) or type(m).__name__ in ("MathTex", "Tex", "MarkupText"):
            box = _box(m)
            visible = True
            if not isinstance(m, ImageMobject):
                try:
                    visible = m.get_fill_opacity() > 0.2 or m.get_stroke_opacity() > 0.2
                except Exception:  # noqa: BLE001
                    visible = True
            if box is not None and visible:
                out.append(box)
            return
        points = getattr(m, "points", None)
        if points is not None and len(points) >= 4:
            try:
                filled = float(m.get_fill_opacity()) > 0.3
            except Exception:  # noqa: BLE001
                filled = False
            box = _box(m) if filled else None
            if box is not None and _area(box) < BIG * frame_area:
                out.append(box)
        for sub in m.submobjects:
            walk(sub)

    walk(mob)
    return out


def _walk(anims):
    for anim in anims:
        if anim is None:
            continue
        subs = getattr(anim, "animations", None)
        if subs:
            yield from _walk(subs)
        else:
            yield anim


class Layout:
    """What is where on a lecture's screen, by whose layout it is (stage, panel, map, caption, chrome, or its own)."""

    def __init__(self, scene):
        from manim import config

        self.scene = scene
        self.frame = (-config.frame_width / 2, -config.frame_height / 2, config.frame_width / 2,
                      config.frame_height / 2)
        self.frame_area = config.frame_width * config.frame_height
        groups = {
            "stage": [getattr(scene, "stage_items", None), *getattr(scene, "stage_extra", []),
                      *getattr(scene, "stage_pending", []), *getattr(scene, "_next_pending", [])],
            "panel": [getattr(scene, "panel", None), getattr(scene, "panel_items", None)],
            "caption": [getattr(scene, "cap", None)],
            "chrome": [getattr(scene, "chrome", None)],
        }
        self.owner: dict[int, str] = {}
        for name, mobs in groups.items():
            for m in mobs:
                if m is not None:
                    for sub in m.get_family():
                        self.owner.setdefault(id(sub), name)

    def whose(self, mob) -> str:
        """The layout a mobject belongs to; "own" for a thing no layout manages."""
        found = self.owner.get(id(mob))
        if found:
            return found
        import pocket_lecture as pl

        z = float(getattr(mob, "z_index", 0) or 0)
        if z <= pl.Z_BACK + 1:
            return "backdrop"
        if getattr(self.scene, "_map_on", False) and z <= pl.Z_MARK + 5:
            return "map"
        if getattr(mob, "_panim_above", False) or z >= pl.Z_CAPTION:
            return "overlay"
        return "own"

    def free(self, kind: str) -> bool:
        return kind == "own"


def make_room(scene, given: list, text: str = "") -> list:
    """The line's pictures [(animation, cue)], with the line's clashes settled (see the module's notes): things moved
    before they are drawn, and fades for leftovers the new ones would cover put first. Counted in the chapter's sync
    report (pocket_lecture.SYNC): moved, cleared, clashes left."""
    from manim import FadeOut

    import pocket_lecture as pl

    layout = Layout(scene)
    on_screen = {id(m) for top in scene.mobjects for m in top.get_family()}
    leaving: set = set()
    arriving = []
    for anim in _walk([a for a, _ in given]):
        mob = getattr(anim, "mobject", None)
        if mob is None:
            continue
        if getattr(anim, "remover", False):
            leaving.update(id(m) for m in mob.get_family())
        elif anim.is_introducer() and id(mob) not in on_screen and all(mob is not a for a in arriving):
            arriving.append(mob)
    if not arriving:
        return given
    arrived = {id(m) for a in arriving for m in a.get_family()}
    standing = [m for m in scene.mobjects if id(m) not in leaving and id(m) not in arrived
                and m is not getattr(scene, "chrome", None)]
    counts = pl.SYNC.setdefault(scene.__dict__.get("_chapter_no", 0), {"beats": 0, "on_words": 0, "pointed": 0})
    issues, clears = [], []
    x0, y0, x1, y1 = layout.frame
    cap = getattr(scene, "cap", None)
    floor = y0 + 0.2
    if cap is not None and _box(cap) is not None:
        floor = max(floor, _box(cap)[3] + 0.08)
    placed = []                                             # (layout, ink) of what this line brings, as settled
    for mob in arriving:
        kind = layout.whose(mob)
        if kind in ("backdrop", "overlay", "caption", "chrome"):
            continue
        boxes = ink(mob, layout.frame_area)
        if not boxes:
            continue
        if layout.free(kind):
            _keep_in(mob, (x0 + 0.15, floor, x1 - 0.15, y1 - 0.15))
            boxes = ink(mob, layout.frame_area)
        against = [(layout.whose(s), s, ink(s, layout.frame_area)) for s in standing]
        against = [(k, s, b) for k, s, b in against if b and k not in ("backdrop", "overlay")]

        def clashes(boxes, strict=False, against=against, kind=kind):
            """What these boxes land on; `strict`: any touch at all (where a thing is moved to)."""
            def hit(a, b):
                return _shared(a, b) > (0.0 if strict else HIT * max(min(_area(a), _area(b)), 1e-3))

            out = []
            for k, s, other in against:
                if k == kind and k != "own" or {k, kind} == {"stage", "map"}:
                    continue                                # a layout's own parts; the stage covers the map
                if any(hit(a, b) for a in boxes for b in other):
                    out.append((k, s, other))
            for k, other in placed:
                if k == kind and k != "own" or {k, kind} == {"stage", "map"}:
                    continue
                if any(hit(a, b) for a in boxes for b in other):
                    out.append((k, None, other))
            return out

        hits = clashes(boxes)
        for k, s, other in list(hits):
            if s is not None and k == "own" and not getattr(s, "_panim_keep", False):
                # A leftover of an earlier line under the new thing: it goes as the line begins.
                clears.append(s)
                standing.remove(s)
                against[:] = [a for a in against if a[1] is not s]
        hits = clashes(boxes)
        if hits and layout.free(kind) and not getattr(mob, "_panim_anchored", False):
            spot = _clear_spot(mob, boxes, clashes, (x0 + 0.15, floor, x1 - 0.15, y1 - 0.15))
            if spot is not None:
                mob.shift(spot)
                counts["moved"] = counts.get("moved", 0) + 1
                boxes = ink(mob, layout.frame_area)
                hits = clashes(boxes)
        for k, s, other in hits:
            issues.append(f"{kind} over {k}: " + _name(mob) + " / " + (_name(s) if s is not None else "this line's"))
        placed.append((kind, boxes))
    if clears:
        counts["cleared"] = counts.get("cleared", 0) + len(clears)
        given = [(FadeOut(s, run_time=0.4), [0.0, 0.4] if any(c for _, c in given) else None) for s in clears] \
            + list(given)
    if issues:
        counts["clashes"] = counts.get("clashes", 0) + len(issues)
        target = os.environ.get("PANIM_LAYOUT_LOG")
        if target:
            with open(target, "a", encoding="utf-8") as out:
                out.write(json.dumps({"say": text[:160], "clashes": issues[:8]}, ensure_ascii=False) + "\n")
    return given


def _keep_in(mob, area) -> None:
    """A thing of its own inside the frame's free area: made smaller to fit, then moved in."""
    box = _box(mob)
    if box is None:
        return
    w, h = box[2] - box[0], box[3] - box[1]
    factor = min(1.0, (area[2] - area[0]) / max(w, 1e-3), (area[3] - area[1]) / max(h, 1e-3))
    if factor < 0.995:
        mob.scale(factor)
        box = _box(mob)
    dx = max(0.0, area[0] - box[0]) - max(0.0, box[2] - area[2])
    dy = max(0.0, area[1] - box[1]) - max(0.0, box[3] - area[3])
    if abs(dx) > 1e-3 or abs(dy) > 1e-3:
        mob.shift(np.array([dx, dy, 0.0]))


def _clear_spot(mob, boxes, clashes, area):
    """The smallest move (up, down, left, right, the diagonals, further each round) that clears every clash and
    stays in the area; None when there is none within reach."""
    lo = min(b[0] for b in boxes), min(b[1] for b in boxes)
    hi = max(b[2] for b in boxes), max(b[3] for b in boxes)
    for step in STEPS:
        for dx, dy in ((0, 1), (0, -1), (-1, 0), (1, 0), (-1, 1), (1, 1), (-1, -1), (1, -1)):
            d = np.array([dx * step, dy * step, 0.0])
            if lo[0] + d[0] < area[0] or hi[0] + d[0] > area[2] or lo[1] + d[1] < area[1] or hi[1] + d[1] > area[3]:
                continue
            # Clear by a small gap, not merely below the clash's share.
            moved = [(b[0] + d[0] - GAP, b[1] + d[1] - GAP, b[2] + d[0] + GAP, b[3] + d[1] + GAP) for b in boxes]
            if not clashes(moved, True):
                return d
    return None


def _name(mob) -> str:
    from manim import Text

    for m in mob.get_family():
        if isinstance(m, Text) and getattr(m, "original_text", ""):
            return repr(m.original_text[:30])
    return type(mob).__name__
