"""Move labels and captions off each other and off the drawing.

The scene agent places text by guessing. This runs when that scene is imported
for export, before any geometry is baked, and only shifts mobjects that are
not on stage yet. Objects already recorded stay where the program put them.
"""

from __future__ import annotations

import math

import numpy as np

# Manim's default frame is 14.22 by 8. Stay inside a margin so glyphs are not
# cut by the edge of the phone picture.
FRAME_W = 14.222222222222221
FRAME_H = 8.0
MARGIN = 0.42
SAFE = (
    -FRAME_W / 2 + MARGIN,
    -FRAME_H / 2 + MARGIN,
    FRAME_W / 2 - MARGIN,
    FRAME_H / 2 - MARGIN,
)
TEXT_GAP = 0.28
SHAPE_GAP = 0.16
STROKE_PAD = 0.2

TEXT_TYPES = frozenset(
    {
        "Text",
        "MarkupText",
        "Paragraph",
        "MathTex",
        "Tex",
        "SingleStringMathTex",
        "Title",
        "BulletedList",
        "Code",
        "DecimalNumber",
        "Integer",
    }
)
CLOSED_TYPES = frozenset(
    {
        "Circle",
        "Dot",
        "Ellipse",
        "Square",
        "Rectangle",
        "RoundedRectangle",
        "Polygon",
        "RegularPolygon",
        "Star",
        "Triangle",
        "SurroundingRectangle",
        "Annulus",
        "Sector",
        "ArcPolygon",
    }
)
THREED_TYPES = frozenset(
    {
        "Sphere",
        "Line3D",
        "Dot3D",
        "Surface",
        "ThreeDAxes",
        "Arrow3D",
        "Cylinder",
        "Cone",
        "Cube",
        "Prism",
    }
)


def install() -> None:
    """Wrap the scene methods the exporter already patched.

    Import order is the contract: the exporter replaces ``Scene.play`` and
    then imports the scene, so this wrapper runs first and the bake sees the
    corrected positions.
    """
    from manim import Scene

    if getattr(Scene, "_layout_guard", False):
        return
    Scene._layout_guard = True
    previous_play = Scene.play
    previous_add = Scene.add

    def play(self, *animations, **kwargs):
        try:
            settle(self, _arrivals(animations))
        except Exception:
            pass
        return previous_play(self, *animations, **kwargs)

    def add(self, *mobjects, **kwargs):
        try:
            settle(self, list(mobjects))
        except Exception:
            pass
        return previous_add(self, *mobjects, **kwargs)

    Scene.play = play
    Scene.add = add


def _arrivals(animations) -> list:
    found = []
    for anim in animations:
        subs = getattr(anim, "animations", None)
        if subs:
            found.extend(_arrivals(subs))
            continue
        name = type(anim).__name__
        if name in ("FadeOut", "Uncreate", "Unwrite", "Wait") or getattr(anim, "remover", False):
            continue
        mob = getattr(anim, "mobject", None)
        if mob is not None:
            found.append(mob)
    return found


def _box(mob):
    try:
        low = mob.get_corner([-1, -1, 0])
        high = mob.get_corner([1, 1, 0])
    except Exception:
        return None
    minx, miny = float(low[0]), float(low[1])
    maxx, maxy = float(high[0]), float(high[1])
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        return None
    if maxx - minx < 1e-4 and maxy - miny < 1e-4:
        return None
    return (minx, miny, maxx, maxy)


def _stage_ids(scene) -> set[int]:
    ids: set[int] = set()
    for mob in getattr(scene, "mobjects", ()):
        for sub in mob.get_family():
            ids.add(id(sub))
    return ids


def _on_stage(ids: set[int], mob) -> bool:
    return any(id(sub) in ids for sub in mob.get_family())


def _has_3d(mobs) -> bool:
    for mob in mobs:
        for sub in mob.get_family():
            if type(sub).__name__ in THREED_TYPES:
                return True
    return False


def _texts(mob) -> list:
    if type(mob).__name__ in TEXT_TYPES:
        return [mob]
    found = []
    for sub in getattr(mob, "submobjects", ()):
        found.extend(_texts(sub))
    return found


def _shapes(mob, out: list) -> None:
    name = type(mob).__name__
    if name in TEXT_TYPES or name in ("ImageMobject", "AbstractImageMobject"):
        return
    points = getattr(mob, "points", None)
    if points is not None and len(points) >= 4 and name not in ("VGroup", "Group"):
        out.append(mob)
    for sub in getattr(mob, "submobjects", ()):
        _shapes(sub, out)


def _filled(mob) -> bool:
    try:
        return float(mob.get_fill_opacity()) > 0.2
    except Exception:
        return False


def _closed(mob) -> bool:
    if type(mob).__name__ in CLOSED_TYPES or _filled(mob):
        return True
    try:
        return bool(mob.is_closed())
    except Exception:
        return False


def _is_card(shape, text) -> bool:
    if type(shape).__name__ not in ("Rectangle", "RoundedRectangle", "Square"):
        return False
    if not _filled(shape):
        return False
    shape_box = _box(shape)
    text_box = _box(text)
    if shape_box is None or text_box is None:
        return False
    cx = (text_box[0] + text_box[2]) / 2
    cy = (text_box[1] + text_box[3]) / 2
    inside = shape_box[0] < cx < shape_box[2] and shape_box[1] < cy < shape_box[3]
    roomy = (shape_box[2] - shape_box[0]) > (text_box[2] - text_box[0]) * 1.2 and (
        shape_box[3] - shape_box[1]
    ) > (text_box[3] - text_box[1]) * 1.2
    return inside and roomy


def _overlap(a, b, gap: float) -> float:
    ox = min(a[2], b[2] + gap) - max(a[0], b[0] - gap)
    oy = min(a[3], b[3] + gap) - max(a[1], b[1] - gap)
    if ox <= 0 or oy <= 0:
        return 0.0
    return ox * oy


def _mtv(a, b, gap: float):
    """Smallest move of box ``a`` that clears box ``b`` plus ``gap``."""
    eb = (b[0] - gap, b[1] - gap, b[2] + gap, b[3] + gap)
    ox = min(a[2], eb[2]) - max(a[0], eb[0])
    oy = min(a[3], eb[3]) - max(a[1], eb[1])
    if ox <= 1e-6 or oy <= 1e-6:
        return None
    acx = (a[0] + a[2]) / 2
    acy = (a[1] + a[3]) / 2
    bcx = (b[0] + b[2]) / 2
    bcy = (b[1] + b[3]) / 2
    if ox < oy:
        return (-ox, 0.0) if acx <= bcx else (ox, 0.0)
    return (0.0, -oy) if acy <= bcy else (0.0, oy)


def _clamp_delta(box, safe) -> tuple[float, float]:
    dx = 0.0
    dy = 0.0
    if box[0] < safe[0]:
        dx = safe[0] - box[0]
    elif box[2] > safe[2]:
        dx = safe[2] - box[2]
    if box[1] < safe[1]:
        dy = safe[1] - box[1]
    elif box[3] > safe[3]:
        dy = safe[3] - box[3]
    return dx, dy


def _fit(mob) -> None:
    box = _box(mob)
    if box is None:
        return
    width = box[2] - box[0]
    height = box[3] - box[1]
    room_w = SAFE[2] - SAFE[0]
    room_h = SAFE[3] - SAFE[1]
    factor = min(1.0, room_w / width, room_h / height)
    if factor < 0.995:
        mob.scale(factor)
        box = _box(mob)
        if box is None:
            return
    dx, dy = _clamp_delta(box, SAFE)
    if abs(dx) > 1e-4 or abs(dy) > 1e-4:
        mob.shift(np.array([dx, dy, 0.0]))


def _stroke_push(text_box, shape):
    """Push when a label actually sits on an open stroke, not merely in its box."""
    points = getattr(shape, "points", None)
    if points is None or len(points) < 4:
        return None
    anchors = np.asarray(points[::4], dtype=float)
    if len(anchors) == 0:
        return None
    cx = (text_box[0] + text_box[2]) / 2
    cy = (text_box[1] + text_box[3]) / 2
    half = 0.5 * min(text_box[2] - text_box[0], text_box[3] - text_box[1])
    pad = STROKE_PAD + half
    nearest = None
    nearest_d = None
    for px, py, *_ in anchors:
        if text_box[0] - STROKE_PAD <= px <= text_box[2] + STROKE_PAD and (
            text_box[1] - STROKE_PAD <= py <= text_box[3] + STROKE_PAD
        ):
            dx = cx - px
            dy = cy - py
            dist = math.hypot(dx, dy) or 1e-6
            if nearest_d is None or dist < nearest_d:
                nearest = (dx / dist, dy / dist, dist)
                nearest_d = dist
    if nearest is None or nearest[2] >= pad:
        return None
    move = pad - nearest[2]
    return nearest[0] * move, nearest[1] * move


def _clear(movable, pinned_text, shapes) -> bool:
    """One pass. True means every label is in frame and clear of the drawing."""
    moved = False
    for index, text in enumerate(movable):
        box = _box(text)
        if box is None:
            continue
        dx, dy = _clamp_delta(box, SAFE)
        if abs(dx) > 1e-3 or abs(dy) > 1e-3:
            text.shift(np.array([dx, dy, 0.0]))
            moved = True
            continue
        push = None
        pen = 0.0
        for other in list(pinned_text) + movable[:index]:
            other_box = _box(other)
            if other_box is None:
                continue
            hit = _overlap(box, other_box, TEXT_GAP)
            step = _mtv(box, other_box, TEXT_GAP)
            if step is not None and hit > pen:
                push = step
                pen = hit
        for shape in shapes:
            if _is_card(shape, text):
                continue
            if _closed(shape):
                shape_box = _box(shape)
                if shape_box is None:
                    continue
                hit = _overlap(box, shape_box, SHAPE_GAP)
                step = _mtv(box, shape_box, SHAPE_GAP)
            else:
                step = _stroke_push(box, shape)
                hit = 0.0 if step is None else abs(step[0]) + abs(step[1])
            if step is not None and hit > pen:
                push = step
                pen = hit
        if push is None or (abs(push[0]) < 1e-3 and abs(push[1]) < 1e-3):
            continue
        text.shift(np.array([push[0], push[1], 0.0]))
        moved = True
    if moved:
        return False
    return not _still_collides(movable, pinned_text, shapes)


def _still_collides(movable, pinned_text, shapes) -> bool:
    for index, text in enumerate(movable):
        box = _box(text)
        if box is None:
            continue
        if _clamp_delta(box, SAFE) != (0.0, 0.0):
            return True
        for other in list(pinned_text) + movable[:index]:
            other_box = _box(other)
            if other_box is not None and _overlap(box, other_box, TEXT_GAP) > 0:
                return True
        for shape in shapes:
            if _is_card(shape, text) or not _closed(shape):
                continue
            shape_box = _box(shape)
            if shape_box is not None and _overlap(box, shape_box, SHAPE_GAP) > 0:
                return True
    return False


def settle(scene, arrivals: list) -> None:
    """Fit new mobjects into the frame and pull their labels off the drawing."""
    if not arrivals:
        return
    ids = _stage_ids(scene)
    fresh = []
    seen = set()
    for mob in arrivals:
        if id(mob) in seen or _on_stage(ids, mob):
            continue
        seen.add(id(mob))
        fresh.append(mob)
    if not fresh:
        return
    stage = list(getattr(scene, "mobjects", ()))
    if _has_3d(fresh) or _has_3d(stage):
        return

    for mob in fresh:
        _fit(mob)

    pinned = []
    for mob in stage:
        pinned.extend(_texts(mob))
    shapes: list = []
    for mob in stage:
        _shapes(mob, shapes)
    for mob in fresh:
        _shapes(mob, shapes)
    movable = []
    for mob in fresh:
        movable.extend(_texts(mob))
    if not movable and not any(_box(mob) and _clamp_delta(_box(mob), SAFE) != (0.0, 0.0) for mob in fresh):
        return

    for _ in range(2):
        for _pass in range(28):
            if _clear(movable, pinned, shapes):
                return
        for mob in fresh:
            mob.scale(0.86)
            _fit(mob)
