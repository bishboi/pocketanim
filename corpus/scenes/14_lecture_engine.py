"""A narrated map lecture, built on harness/lecture/pocket_lecture.

What the other corpus scenes do not have and a lecture is made of: captions
over everything at z=60, a fact panel whose titles replace each other, groups
faded out as one after being brought in child by child, dim-then-highlight
fills, lagged reveals nested inside concurrent ones, fractional beat lengths
and a background colour that is not black.

Network-free on purpose: the "map" is a hand-digitised outline pushed through
the same Cartopy projection a real one uses, so the scene exports anywhere
without Natural Earth. Narration is silent (PANIM_VOICE=silent), so beat
lengths come from word counts and the program is reproducible.

Export with:
    PANIM_VOICE=silent python -m dsl.export_dsl corpus/scenes/14_lecture_engine.py LectureEngine --write
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("LECTURE_STYLE", "vox")
os.environ.setdefault("PANIM_VOICE", "silent")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness" / "lecture"))

from pocket_lecture import *  # noqa: E402,F403
from shapely.geometry import Polygon as Outline  # noqa: E402 -- after: Manim has a Polygon too

# A coarse outline of peninsular India, lon/lat. Schematic by design.
OUTLINE = Outline([
    (68.2, 23.6), (70.2, 20.9), (72.8, 19.0), (73.4, 16.0), (74.8, 12.8), (76.3, 9.8), (77.5, 8.1),
    (78.3, 9.0), (79.9, 10.3), (80.3, 13.1), (80.2, 15.8), (82.3, 16.9), (84.9, 19.3), (86.9, 20.8),
    (88.6, 21.8), (89.0, 25.9), (88.1, 26.6), (85.0, 27.1), (81.6, 28.3), (79.0, 30.5), (77.4, 32.5),
    (74.6, 34.4), (74.3, 32.1), (71.5, 28.1), (70.0, 26.1), (68.2, 23.6),
])
DECCAN = Outline([(74.0, 16.0), (79.5, 16.0), (80.5, 21.5), (74.5, 22.0)])


class LectureEngine(MapLecture):
    SECTIONS = ["Introduction", "The peninsula"]

    @property
    def focus(self):
        return OUTLINE

    def base(self, opacity: float = 0.08):
        fr = self.frame
        land = fr.poly(OUTLINE, fill_color=TH.get("land", P.SAND), fill_opacity=1, stroke_width=0)
        land.set_z_index(Z_LAND)
        outline = fr.poly(OUTLINE, fill_opacity=0, stroke_color=TH.get("map_stroke", P.CREAM), stroke_width=2.2)
        outline.set_z_index(Z_OUTLINE)
        return VGroup(land), VGroup(), outline

    def construct(self):
        self.chapter(1, "The peninsula", "A schematic map", "Chapter one. The peninsula.")
        self.show_map()
        self.beat("The peninsula narrows to a point in the south.",
                  self.panel_title("Shape", "A triangle of land"),
                  self.fact("About 2,000 km from north to south"))
        self.beat("The Tropic of Cancer crosses its middle.",
                  self.graticule(lat=23.44, color=P.GOLD, label="Tropic of Cancer"),
                  self.big_stat("23.44°", "Latitude of the Tropic of Cancer", P.GOLD))
        plateau = self.region_fill(DECCAN, P.DUNE, 0.7)
        self.beat("An old plateau fills the south.", self.panel_title("The Deccan"), FadeIn(plateau),
                  self.mark((78.5, 17.4), "Hyderabad", P.ROSE))
        self.beat("Its rivers mostly run east.",
                  self.path([(73.6, 19.9), (76.0, 19.1), (79.0, 18.3), (81.8, 16.9)], P.RIVER),
                  plateau.animate.set_fill(opacity=0.2),
                  self.bar_chart([("Godavari", 1465), ("Krishna", 1400), ("Kaveri", 800)], P.RIVER, " km"))
        self.beat("The monsoon arrives from the south-west.",
                  self.flow([(69.0, 11.0), (72.0, 14.5), (75.0, 18.5), (77.5, 22.0)], P.TEAL))
        self.outro_fade()
