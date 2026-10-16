"""Text a free-form block writes, on a patch of the board.

A block's words were drawn straight on whatever was under them: a ray, a grid line, another equation left where
the next one was written. Each Text, MathTex, Tex and MarkupText a block makes carries a patch of the board's
colour behind it, as part of it, so it moves, fades, transforms and leaves with its words, in the video and in the
program the editor and the phone play (the patch is the first shape of the text's family, so it is drawn first).

The patch is out of the way of the code that made the words: `eq[0]`, `eq[1:3]`, `for part in eq` and `len(eq)`
see the words only, a colour given to the words (`set_color`, `Indicate`, `color=GOLD`) leaves the patch the board's
colour, and TransformMatchingTex (the block's own, keyed for it) pairs the old patch with the new one.
"""

from __future__ import annotations

import manim

PAD_X, PAD_Y = 0.09, 0.07


class Backing(manim.RoundedRectangle):
    """The patch behind a text: the board's colour, whatever colour its words are given; its opacity follows them."""

    tex_string = ""          # TransformMatchingTex keys parts by their TeX: the old patch goes to the new one
    is_backing = True

    def __init__(self, colour, width: float, height: float, opacity: float = 1.0):
        self._locked = False
        super().__init__(corner_radius=min(0.06, height / 3), width=width, height=height, stroke_width=0,
                         fill_color=colour, fill_opacity=opacity)
        self._locked = True

    def set_fill(self, color=None, opacity=None, family=True):
        return super().set_fill(None if getattr(self, "_locked", False) else color, opacity, family)

    def set_stroke(self, color=None, width=None, opacity=None, background=False, family=True):
        if getattr(self, "_locked", False):
            return self          # never an outline: a Write or a colour would have drawn its edge
        return super().set_stroke(color, width, opacity, background, family)

    def set_color(self, color=None, family=True):
        return self if getattr(self, "_locked", False) else super().set_color(color, family)


def _back(text, colour) -> None:
    if text.width < 1e-3 or text.height < 1e-3 or any(isinstance(s, Backing) for s in text.submobjects):
        return
    patch = Backing(colour, text.width + 2 * PAD_X, text.height + 2 * PAD_Y).move_to(text.get_center())
    patch.set_z_index(text.z_index)
    text.add_to_back(patch)


class _Words:
    """What the block's code sees of a backed text: its words, not the patch."""

    def _words(self):
        return [m for m in self.submobjects if not isinstance(m, Backing)]

    def __getitem__(self, value):
        words = self._words()
        if isinstance(value, slice):
            return manim.VGroup(*words[value])
        return words[value]

    def __iter__(self):
        return iter(self._words())

    def __len__(self):
        return len(self._words())


class TransformMatchingTex(manim.TransformMatchingTex):
    """Manim's, with the patch of a backed text keyed like a part: the old patch goes to the new one."""

    @staticmethod
    def get_mobject_key(mobject):
        if isinstance(mobject, Backing):
            return ""
        return manim.TransformMatchingTex.get_mobject_key(mobject)


def classes(colour) -> dict:
    """The block's Text, MathTex, Tex and MarkupText, each backed with the board's `colour`. Same names as Manim's,
    so the exporter and every check that reads a type's name see what they always saw."""

    def backed(base):
        def __init__(self, *args, **kwargs):
            base.__init__(self, *args, **kwargs)
            _back(self, colour)

        return type(base.__name__, (_Words, base), {"__init__": __init__, "__module__": base.__module__})

    out = {name: backed(getattr(manim, name)) for name in ("Text", "MathTex", "Tex", "MarkupText")}
    out["TransformMatchingTex"] = TransformMatchingTex
    return out


def _closed(mob) -> bool:
    import numpy as np

    pts = getattr(mob, "points", None)
    return pts is not None and len(pts) >= 4 and bool(np.allclose(pts[0], pts[-1], atol=1e-3))


def _bounds(points):
    return points[:, 0].min(), points[:, 1].min(), points[:, 0].max(), points[:, 1].max()


def settle(scene, arriving) -> None:
    """Before words go on the board: words inside a closed shape (a table's cell, a node's circle, a labelled box)
    already have that shape behind them, and the patch only showed as a dark box in a coloured cell. Their patch
    goes. Words anywhere else keep theirs."""
    import numpy as np

    on_stage = {id(x) for top in scene.mobjects for x in top.get_family()}
    mobs = list(arriving)
    texts = [x for m in mobs for x in m.get_family()
             if id(x) not in on_stage and any(isinstance(s, Backing) for s in x.submobjects)]
    if not texts:
        return
    shapes = [x for top in [*scene.mobjects, *mobs] for x in top.get_family()
              if not isinstance(x, Backing) and _closed(x)]
    for text in texts:
        words = [p.points for p in text.family_members_with_points() if not isinstance(p, Backing)]
        if not words:
            continue
        x0, y0, x1, y1 = _bounds(np.concatenate(words))
        area = max((x1 - x0) * (y1 - y0), 1e-4)
        inside = set(map(id, text.get_family()))
        for shape in shapes:
            if id(shape) in inside:
                continue
            sx0, sy0, sx1, sy1 = _bounds(shape.points)
            if sx0 <= x0 + 0.02 and sy0 <= y0 + 0.02 and sx1 >= x1 - 0.02 and sy1 >= y1 - 0.02:
                filled = shape.get_fill_opacity() > 0.1
                if filled or (sx1 - sx0) * (sy1 - sy0) <= 30 * area:
                    text.remove(*[s for s in text.submobjects if isinstance(s, Backing)])
                    break


def arriving_in(animations) -> list:
    """What a play may put on the board: each animation's object and the shape it becomes."""
    out, todo = [], list(animations)
    while todo:
        anim = todo.pop(0)
        todo.extend(getattr(anim, "animations", None) or [])
        for attr in ("mobject", "target_mobject", "_panim_target"):
            mob = getattr(anim, attr, None)
            if mob is not None:
                out.append(mob)
    return out
