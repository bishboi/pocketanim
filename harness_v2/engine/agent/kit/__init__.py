"""The kit: building blocks for explainer videos in Manim, in a chosen look (vox, blueprint).

    from kit import *            # everything below, plus manim's own names

Optional: use any of it, none of it, or take pieces apart. Every piece is an ordinary Manim mobject; every
animation an ordinary Manim animation. The catalog with examples is KIT.md; kit_preview shows any piece before
you use it.
"""

from manim import *  # noqa: F401,F403  (the kit's users write plain Manim beside it)

from .base import Piece, PictureGroup  # noqa: F401
from .cards import (book, card, checklist, chip, clipping, document, panel, portrait, scroll, shadow_of, shelf,  # noqa: F401
                    stat, sticky, tag)
from .charts import Bars, Donut, LineChart, Units, Versus, bars, donut, line_chart, units, versus  # noqa: F401
from .diagrams import Chain, Cycle, Flow, Hub, Network, Pyramid, Tree, node  # noqa: F401
from .images import commons, commons_search, photo, surface, treat  # noqa: F401
from .layout import (ZONES, column, edge_point, fit_to, grid, keep_in_frame, overlaps, place, row, separate, spread,  # noqa: F401
                     zone)
from .look import BLUEPRINT, LOOKS, VOX, L, Look, look, looking, register, use  # noqa: F401
from .maps import Map  # noqa: F401
from .marks import (arrow, box, bracket, callout, circle, cross, dimension, highlight, spotlight, stamp,  # noqa: F401
                    strike, tick, underline)
from .motion import (EMPHASES, ENTRANCES, EXITS, bob, chain, drift, emph, enter, later, leave, owned, stagger,  # noqa: F401
                     stop_drift, together)
from .people import crowd, figure, person  # noqa: F401
from .scene import KitScene  # noqa: F401
from .text import (caption, count, fit, headline, kicker, label, number, quote, script_of, text,  # noqa: F401
                   title_card)
from .timeline import Timeline  # noqa: F401
from .icons import icon, icon_names  # noqa: F401
