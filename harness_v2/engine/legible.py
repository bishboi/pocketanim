"""What keeps a frame readable whatever drew it (a template, a block of model-written Manim):

- legible(scene, mobjects): each piece of text about to be shown is read against what it actually sits on -- the
  card, chip or bar under it, else the board -- and a colour that reads under NEED:1 there (the accent's yellow on a
  cream board) is taken to the nearest shade of it that does (pocket_lecture.readable). Text over a picture is left
  as drawn: what is under it is not one colour.
- clearing(scene, old, animations): a block of Manim drawing over what an earlier block of its figure left (a new
  picture over the last one, words over words) takes the old part away as the new one comes.
- keep_shape(mob): a picture that only ever scales as a whole -- stretched to a width or a height it kept its other
  side, and its labels no longer sat on what they name.
"""

from __future__ import annotations

import types

NEED = 3.2              # the contrast large text must have against what it sits on
NEED_SMALL = 4.5        # and smaller words (a line under SMALL_LINE tall)
SMALL_LINE = 0.42
OVERLAP_TEXT = 0.2      # words over words: this share of the smaller covered and the old words go
OVERLAP_SHAPE = 0.3     # a picture or a filled shape over an old part: this share of the old part covered
MIN_SHAPE = 0.6         # a filled shape smaller than this (in square units) clears nothing


def _text_kinds():
    from manim import MarkupText, Paragraph, SingleStringMathTex, Text

    return (Text, MarkupText, Paragraph, SingleStringMathTex)


def _box(m):
    try:
        if not len(m.get_family()) or (m.width < 1e-3 and m.height < 1e-3):
            return None
        return (m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1])
    except Exception:  # noqa: BLE001 -- a mobject with no points yet
        return None


def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))) \
        if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3] else 0.0


def _z(m) -> float:
    return max((getattr(x, "z_index", 0) or 0) for x in m.get_family())


def _hex(colour) -> str | None:
    try:
        return colour.to_hex()[:7].upper()
    except Exception:  # noqa: BLE001
        return None


def _ground(scene, text, roots) -> str | None:
    """The colour under a piece of text: the topmost solid shape beneath its middle that is wider than it, else
    the board's. None when a picture lies under it (not one colour)."""
    import pocket_lecture as pl
    from manim import ImageMobject, VMobject, config

    centre = text.get_center()
    tb = _box(text)
    if tb is None:
        return None
    own = {id(x) for x in text.get_family()}
    top_z = _z(text)
    kinds = _text_kinds()
    best, order = None, 0
    seen: set[int] = set()

    def walk(m):
        nonlocal best, order
        if id(m) in seen or id(m) in own:
            return
        seen.add(id(m))
        b = _box(m)
        if b is None or not (b[0] <= centre[0] <= b[2] and b[1] <= centre[1] <= b[3]):
            return
        if isinstance(m, kinds):
            return
        order += 1
        z = getattr(m, "z_index", 0) or 0
        if z <= top_z:
            if isinstance(m, ImageMobject):
                full = m.width >= config.frame_width * 0.95 and m.height >= config.frame_height * 0.95
                if z > pl.Z_BACK and not full:
                    key = (z, order)
                    if best is None or key >= best[0]:
                        best = (key, None)
            elif isinstance(m, VMobject) and len(m.points) and m.get_fill_opacity() >= 0.5 \
                    and _area(b) >= _area(tb) * 0.9:
                key = (z, order)
                if best is None or key >= best[0]:
                    best = (key, _hex(m.get_fill_color()))
        for sub in m.submobjects:
            walk(sub)

    for root in roots:
        walk(root)
    if best is None:
        return str(pl.TH.get("bg") or pl.P.BG)
    return best[1]


def legible(scene, mobjects) -> int:
    """Each piece of text among `mobjects` (and inside them) made to read on what it sits on. Returns how many
    were changed."""
    import pocket_lecture as pl
    from manim import VMobject

    kinds = _text_kinds()
    texts, stack, seen = [], list(mobjects), set()
    while stack:
        m = stack.pop()
        if m is None or id(m) in seen:
            continue
        seen.add(id(m))
        if isinstance(m, kinds):
            texts.append(m)
            continue
        stack.extend(getattr(m, "submobjects", []) or [])
    if not texts:
        return 0
    roots = list({id(r): r for r in [*scene.mobjects, *mobjects]}.values())
    changed = 0
    for text in texts:
        if getattr(text, "panim_keep_colour", False):
            continue
        ground = _ground(scene, text, roots)
        if not ground:
            continue
        # Small words need more than large ones (WCAG: 4.5 for body text, 3 for large).
        lines = str(getattr(text, "text", "") or getattr(text, "original_text", "")).count("\n") + 1
        need = NEED_SMALL if text.height / max(lines, 1) < SMALL_LINE else NEED
        for glyph in text.get_family():
            if not isinstance(glyph, VMobject) or not len(glyph.points) or glyph.get_fill_opacity() < 0.5:
                continue
            was = _hex(glyph.get_fill_color())
            if not was:
                continue
            now = pl.readable(was, ground, need)
            if now.upper() != was:
                glyph.set_fill(now, opacity=glyph.get_fill_opacity())
                changed += 1
    return changed


# ---------------------------------------------------------------- a figure drawn over itself ----------------------

def units(mobjects) -> list:
    """The parts of a drawing as one sees them: a piece of text, a picture, a shape, a small group (a box with its
    label); a large group is looked into once more."""
    from manim import ImageMobject

    kinds = _text_kinds()
    out = []

    def add(m, depth):
        b = _box(m)
        if b is None:
            return
        whole = isinstance(m, kinds) or isinstance(m, ImageMobject) or not m.submobjects or \
            getattr(m, "panim_picture", None)
        if whole or depth >= 2 or _area(b) < 4.0:
            out.append(m)
            return
        for sub in m.submobjects:
            add(sub, depth + 1)

    for m in mobjects:
        add(m, 0)
    return out


def _kind(m) -> str:
    from manim import ImageMobject, VMobject

    if isinstance(m, _text_kinds()):
        return "text"
    family = m.get_family()
    if isinstance(m, ImageMobject) or getattr(m, "panim_picture", None) or \
            any(isinstance(x, ImageMobject) for x in family):
        return "picture"
    filled = [x for x in family if isinstance(x, VMobject) and len(x.points) and x.get_fill_opacity() >= 0.4]
    if filled:
        return "shape"
    if any(isinstance(x, _text_kinds()) for x in family):
        return "text"
    return "line"


def clearing(scene, old: list, animations) -> list:
    """The parts of `old` (what earlier blocks of a figure drew) that what this play brings on is drawn over: a new
    picture or shape over an old part, new words over old words. A label put on an old picture is not over it."""
    import backed_text

    on_screen = {id(x) for m in scene.mobjects for x in m.get_family()}
    moving = {id(x) for a in backed_text.arriving_in(animations) for x in a.get_family()}
    coming = []
    for anim in _leaves(animations):
        m = getattr(anim, "mobject", None)
        if m is not None and id(m) not in on_screen and not getattr(anim, "remover", False):
            coming.extend(units([m]))
    if not coming:
        return []
    going = []
    for u in old:
        if id(u) not in on_screen or id(u) in moving:
            continue
        ub = _box(u)
        if ub is None or _area(ub) < 1e-4:
            continue
        try:
            if max((x.get_fill_opacity() for x in u.get_family() if hasattr(x, "get_fill_opacity")), default=1) < 0.05 \
                    and not any(getattr(x, "pixel_array", None) is not None for x in u.get_family()):
                continue
        except Exception:  # noqa: BLE001
            pass
        uk = _kind(u)
        for n in coming:
            nb = _box(n)
            if nb is None:
                continue
            nk = _kind(n)
            inter = _inter(ub, nb)
            if not inter:
                continue
            small = min(_area(ub), _area(nb)) or 1e-6
            if nk == "text" and uk == "text" and inter > OVERLAP_TEXT * small:
                going.append(u)
                break
            if nk in ("picture", "shape") and (nk == "picture" or _area(nb) >= MIN_SHAPE) and \
                    inter > OVERLAP_SHAPE * _area(ub) and not (uk == "picture" and _area(nb) < 0.5 * _area(ub)):
                going.append(u)
                break
    return going


def _leaves(animations) -> list:
    out, todo = [], list(animations)
    while todo:
        a = todo.pop(0)
        subs = getattr(a, "animations", None)
        if subs:
            todo.extend(subs)
        else:
            out.append(a)
    return out


# ---------------------------------------------------------------- pictures keep their shape -----------------------

def _stretch_whole(self, factor, dim, **kwargs):
    """A picture stretched along one side is scaled whole instead (keep_shape)."""
    return self.scale(factor, **kwargs)


def keep_shape(mob):
    """`mob` scales only as a whole: stretch, stretch_to_fit_width/height and rescale_to_fit(stretch=True) keep
    its proportions (a copy keeps the rule)."""
    mob.stretch = types.MethodType(_stretch_whole, mob)
    return mob
