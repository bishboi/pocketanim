"""Icons by name, from the engine's downloaded Iconify sets (about 30,000: emoji drawings and silhouettes).

    icon("ship")                       # vox: a flat colour drawing; blueprint: a silhouette in the ink colour
    icon("scroll", style="mono", color="#E5383B", size=1.2)
    icon_names("printing")             # what there is for a word

style: "color" (a colour drawing), "mono" (a silhouette filled with `color`), or None for the look's choice.
"""

from __future__ import annotations

import sys
from pathlib import Path

from manim import SVGMobject

from .base import Piece
from .look import L

ENGINE = Path(__file__).resolve().parents[2]
REPO = ENGINE.parents[1]


def _icons():
    if str(ENGINE) not in sys.path:
        sys.path.insert(0, str(ENGINE))
    import icons as ic
    if not ic.ICONS.is_dir() or not any(ic.ICONS.glob("*.json")):
        # v2 has no copy of the sets: read v1's (harness/lecture/data/icons), never written to.
        for other in (REPO / "harness" / "lecture" / "data" / "icons",):
            if other.is_dir() and any(other.glob("*.json")):
                ic.ICONS = other
                ic._names.cache_clear() if hasattr(ic._names, "cache_clear") else None
                break
    return ic


def icon_names(word: str, limit: int = 10) -> list[dict]:
    """Icons for a word: [{id, set, name, mono}], best first."""
    return _icons().search(word, limit)


class Icon(Piece):
    enter_kind = "shape"


def icon(name: str, size: float = 1.0, color: str | None = None, style: str | None = None) -> Icon:
    """An icon `size` units tall. `name` is a word ("ship") or an exact id ("game-icons:scroll-unfurled")."""
    ic = _icons()
    look = L()
    style = style or ("mono" if look.name == "blueprint" else "color")
    if ":" in name:
        icon_id = name
    else:
        rows = ic.search(name, 30)
        if not rows:
            raise LookupError(f"no icon for {name!r}")
        want_mono = style == "mono"
        pick = next((r for r in rows if r["mono"] == want_mono), rows[0])
        icon_id = pick["id"]
    mono = ic.is_mono(icon_id)
    path = ic.svg_file(icon_id, color or (look.ink if mono else None))
    svg = SVGMobject(str(path))
    if mono or style == "mono":
        svg.set_fill(color or look.ink, opacity=1).set_stroke(width=0)
    svg.scale_to_fit_height(size)
    i = Icon(svg)
    i.icon_id = icon_id
    i.name_part("svg", svg)
    return i
