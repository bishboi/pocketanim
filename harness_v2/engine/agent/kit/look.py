"""Looks: everything a piece's style comes from (colours, fonts, surfaces, strokes, how things move).

    from kit import *
    use("blueprint")          # every piece made after this is drawn in the blueprint look
    L().accent                # the current look's accent colour

A look is a plain dataclass; `use(look("vox", accent="#2A9D8F"))` changes one thing in a look, and `use()` inside a
`with looking("blueprint"):` block switches only for what is made inside it.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field, replace

from manim import rate_functions as rf


@dataclass(frozen=True)
class Look:
    name: str
    # surfaces
    bg: str                    # the stage colour
    surface: str               # "paper" (a grain texture), "grid" (a drafting grid) or "plain"
    ink: str                   # text and lines
    muted: str                 # secondary text, ticks, faint lines
    faint: str                 # the faintest lines (grids, tracks)
    accent: str                # the one colour that says "look here"
    mark: str                  # the highlighter / emphasis colour
    palette: tuple             # series colours, in order (charts, lifespans, diagram groups)
    # cards and boxes
    card: str                  # a card's fill
    card_edge: str             # a card's outline
    card_opacity: float        # 0 for outlined-only cards
    radius: float              # corner radius
    shadow: bool               # cards cast a soft shadow
    shadow_color: str
    tilt: float                # degrees of the casual tilt cards and photos get (0: square to the frame)
    stroke: float              # the standard line width
    dashed_lines: bool         # connectors and routes dashed
    # maps
    land: str
    land_edge: str
    water: str
    land_opacity: float
    # type
    head: str                  # headline font (Latin)
    body: str                  # body font (Latin)
    serif: str                 # quotes, titles of books
    hand: str                  # handwritten annotations
    mono: str                  # numbers, codes, dimensions
    deva: str                  # Devanagari (Hindi) body
    deva_head: str             # Devanagari headline
    cjk: str                   # Chinese / Japanese characters
    head_upper: bool           # headlines in capitals
    head_weight: str           # "BOLD" or "NORMAL"
    # motion
    run: float = 0.6           # an ordinary entrance's length
    lag: float = 0.12          # the gap between staggered items
    ease: object = rf.ease_out_cubic     # entrances
    ease_out: object = rf.ease_in_cubic  # exits
    overshoot: float = 0.08    # how far a pop / spring goes past its size (0: none)
    enter_text: str = "rise"   # the default entrance of text
    enter_shape: str = "pop"   # the default entrance of shapes and cards
    enter_line: str = "draw"   # the default entrance of lines, routes and outlines
    photo: str = "cutout"      # how photographs are treated (images.treat)
    extra: dict = field(default_factory=dict)

    def color(self, i: int) -> str:
        """The i-th series colour (wraps)."""
        return self.palette[i % len(self.palette)]


VOX = Look(
    name="vox", bg="#F1E9DA", surface="paper", ink="#1B1B1B", muted="#6F6656", faint="#CFC3AC",
    accent="#E5383B", mark="#FFD23F",
    palette=("#E5383B", "#2A9D8F", "#3D6FA3", "#F08A3C", "#7B5EA7", "#C9A227", "#5C8A3A"),
    card="#FFFDF7", card_edge="#1B1B1B", card_opacity=1.0, radius=0.06, shadow=True, shadow_color="#5A4A33",
    tilt=2.0, stroke=4.0, dashed_lines=True,
    land="#E2D6BF", land_edge="#B9A98C", water="#F1E9DA", land_opacity=1.0,
    head="Oswald", body="Hind", serif="Playfair Display", hand="Kalam", mono="IBM Plex Mono",
    deva="Hind", deva_head="Hind", cjk="WenQuanYi Zen Hei", head_upper=True, head_weight="BOLD",
    run=0.6, lag=0.12, ease=rf.ease_out_back, ease_out=rf.ease_in_cubic, overshoot=0.08,
    enter_text="rise", enter_shape="pop", enter_line="draw", photo="cutout",
)

BLUEPRINT = Look(
    name="blueprint", bg="#123E6B", surface="grid", ink="#EAF4FF", muted="#9CC3E8", faint="#2E5F8F",
    accent="#FFB347", mark="#5FD4FF",
    palette=("#FFB347", "#5FD4FF", "#FF6F7D", "#B7F27D", "#E3B7FF", "#FFE066", "#7EE0C3"),
    card="#164A7E", card_edge="#EAF4FF", card_opacity=0.55, radius=0.0, shadow=False, shadow_color="#0A2440",
    tilt=0.0, stroke=3.0, dashed_lines=True,
    land="#1B5288", land_edge="#9CC3E8", water="#123E6B", land_opacity=0.65,
    head="IBM Plex Mono", body="Hind", serif="IBM Plex Mono", hand="Architects Daughter",
    mono="IBM Plex Mono", deva="Hind", deva_head="Hind", cjk="WenQuanYi Zen Hei", head_upper=True,
    head_weight="BOLD",
    run=0.7, lag=0.1, ease=rf.ease_in_out_sine, ease_out=rf.ease_in_out_sine, overshoot=0.0,
    enter_text="type", enter_shape="draw", enter_line="draw", photo="duotone",
)

LOOKS = {"vox": VOX, "blueprint": BLUEPRINT}
_current = [VOX]


def look(name: str | Look = "vox", **changes) -> Look:
    """A look by name ("vox", "blueprint"), with any of its fields changed: look("vox", accent="#2A9D8F")."""
    base = name if isinstance(name, Look) else LOOKS[str(name).lower()]
    return replace(base, **changes) if changes else base


def use(name: str | Look = "vox", **changes) -> Look:
    """Make a look current: every piece made after this is drawn in it."""
    _current[0] = look(name, **changes)
    return _current[0]


def L() -> Look:
    """The current look."""
    return _current[0]


@contextlib.contextmanager
def looking(name: str | Look, **changes):
    """Pieces made inside the block are drawn in another look; the one before comes back after it."""
    before = _current[0]
    _current[0] = look(name, **changes)
    try:
        yield _current[0]
    finally:
        _current[0] = before


def register(new: Look) -> Look:
    """Add a look of your own under its name."""
    LOOKS[new.name] = new
    return new
