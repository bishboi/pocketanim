"""What every kit piece is: a plain Manim group (VGroup, or Group when it holds a picture) that knows how it enters,
leaves and is pointed at in its look, and has named parts.

    card = Card("Sima Qian")           # a VGroup: move it, scale it, animate it like any Manim object
    self.play(card.appear())           # its own entrance in the current look
    self.play(card.emphasize())        # its own way of saying "this one"
    card.part("title")                 # a named part, to animate on its own
"""

from __future__ import annotations

from manim import Group, VGroup


class PieceMixin:
    """appear / disappear / emphasize, and named parts. Mixed into VGroup and Group."""

    enter_kind = "shape"       # "text", "shape" or "line": which default entrance of the look it takes

    def _init_piece(self):
        self._parts = {}
        self._enter_how = None

    def name_part(self, name: str, mob):
        self._parts[name] = mob
        return mob

    def part(self, name: str):
        """A named part (KeyError lists the names it has)."""
        try:
            return self._parts[name]
        except KeyError:
            raise KeyError(f"no part {name!r}; parts: {', '.join(self._parts) or 'none'}") from None

    @property
    def parts(self) -> dict:
        return dict(self._parts)

    def entering(self, how: str):
        """Set how this piece appears by default (any entrance name motion.enter knows)."""
        self._enter_how = how
        return self

    def appear(self, how: str | None = None, run: float | None = None, **kw):
        """The piece coming on in the current look (or `how`: motion.ENTRANCES)."""
        from .motion import enter
        return enter(self, how or self._enter_how, run=run, kind=self.enter_kind, **kw)

    def disappear(self, how: str | None = None, run: float | None = None, **kw):
        from .motion import leave
        return leave(self, how, run=run, **kw)

    def emphasize(self, how: str | None = None, run: float | None = None, **kw):
        from .motion import emph
        return emph(self, how, run=run, **kw)


class Piece(PieceMixin, VGroup):
    def __init__(self, *mobs, **kw):
        VGroup.__init__(self, *mobs, **kw)
        self._init_piece()


class PictureGroup(PieceMixin, Group):
    """A piece holding a picture (ImageMobject is not a VMobject, so it lives in a Group)."""

    def __init__(self, *mobs, **kw):
        Group.__init__(self, *mobs, **kw)
        self._init_piece()
