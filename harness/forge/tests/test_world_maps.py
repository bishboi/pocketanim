"""Maps of more than one country: the world, a continent, a world region ({"area": "Asia"}, {"area": "South Asia"},
or a country name that is none, {"country": "World"}). A script asked for {"country": "World"} and the build failed
in show_map ("no country named 'World'"); such a region is now an area of Natural Earth's countries, drawn whole,
in Robinson when it spans the world, and checked by the compiler so a wrong one goes back to the writer."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import pocket_lecture as pl  # noqa: E402

from test_sims_more import REPO  # noqa: E402


@pytest.mark.parametrize("region,kind", [
    ({"country": "World"}, "area"), ({"area": "World"}, "area"), ({"area": "Asia"}, "area"),
    ({"country": "Europe"}, "area"), ({"area": "South Asia"}, "area"), ({"area": "Middle East"}, "area"),
    ({"area": "Western Europe"}, "area"), ({"area": "Indian subcontinent"}, "area"),
    ({"country": "India"}, "country"), ({"state": "Kerala", "country": "India"}, "state"),
])
def test_regions_resolve(region, kind):
    assert pl.region_kind(region) == kind


def test_areas_hold_their_countries():
    assert len(pl.area_members("World")) > 200
    south = set(pl.area_members("South Asia"))
    assert {"India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal"} <= south and "China" not in south
    assert "Saudi Arabia" in pl.area_members("Middle East")
    assert pl.area_members("Narnia") == ()


def test_the_compiler_checks_the_region():
    def script(region):
        return {"title": "T", "style": "chalkboard", "region": region,
                "chapters": [{"title": "A", "beats": [{"say": "London and Delhi, far apart.",
                                                       "do": [{"op": "marker", "place": "London"},
                                                              {"op": "marker", "place": "New Delhi"}]}]}]}
    assert not cl.lint(script({"country": "World"}))[0]       # places anywhere, not looked up in a "World"
    errors = cl.lint(script({"country": "Narnia"}))[0]
    assert any("no country, state, continent or world area named 'Narnia'" in e and '"area": "World"' in e
               for e in errors), errors


def test_a_world_map_lecture_builds(tmp_path):
    """The lecture that failed: a map of the world, with markers, a country filled and a voyage."""
    script = {"title": "Voyages", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
              "region": {"country": "World"}, "chapters": [{"title": "The world", "beats": [
                  {"say": "London and Delhi, on opposite sides of a continent.",
                   "do": [{"op": "marker", "place": "London"}, {"op": "marker", "place": "New Delhi", "label": "Delhi"}]},
                  {"say": "India, filled in on the world map.", "do": [{"op": "state", "name": "India"}]},
                  {"say": "Vasco da Gama sailed from Lisbon round Africa to Calicut.",
                   "do": [{"op": "journey", "stops": ["Lisbon", [18.47, -34.36], "Kozhikode"],
                           "labels": ["Lisbon", "Cape of Good Hope", "Calicut"]}]}]}]}
    assert not cl.lint(script)[0]
    scene = tmp_path / "scene.py"
    scene.write_text(cl.compile_script(script))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path)], capture_output=True, text=True, timeout=1500,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [], result
    assert not [s for s in result.get("skipped") or [] if "map" in s.lower() or "World" in s], result["skipped"]


def test_a_map_of_europe_does_not_reach_infinity():
    """Natural Earth's Europe holds all of Russia: projected for Europe, its far east went to infinity."""
    from manim import VGroup

    class Probe(pl.MapLecture):
        REGION = {"area": "Europe"}

    pl.use_style("chalkboard")
    scene = Probe.__new__(Probe)
    nb, inner, outline = scene.base()
    assert len(outline) and len(inner) and isinstance(nb, VGroup)


def test_maps_draw_india_as_india_does():
    """Every map draws India's borders as India does: the whole of Jammu and Kashmir and Ladakh, with PoK,
    Gilgit-Baltistan and Aksai Chin; Pakistan and China without them."""
    from shapely.geometry import Point

    muzaffarabad, gilgit, aksai_chin = Point(73.47, 34.37), Point(74.31, 35.92), Point(79.5, 35.2)
    india = pl.country("India")
    assert all(india.contains(p) for p in (muzaffarabad, gilgit, aksai_chin))
    assert not pl.country("Pakistan").contains(gilgit) and not pl.country("China").contains(aksai_chin)
    assert pl.state("Jammu and Kashmir", "India").contains(muzaffarabad)
    ladakh = pl.state("Ladakh", "India")
    assert ladakh.contains(gilgit) and ladakh.contains(aksai_chin)
    assert ladakh.bounds[1] > 30                                   # no slivers from the rest of India
    assert {"Azad Kashmir", "Northern Areas"}.isdisjoint(dict(pl.states_of("Pakistan")))
    # On a map of the world or of South Asia, India's outline is the same.
    assert pl.area("South Asia").contains(gilgit) and pl.area("World").contains(aksai_chin)
    assert pl.countries_dataset() == "admin_0_countries_ind" and pl.countries_dataset("default") == "admin_0_countries"
