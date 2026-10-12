"""Maps that show the past and the land: states as they stood in a year (historical.py), labels that ride their
arrows, a locator inset on a zoomed map, and mountains drawn in line."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402

REPO = LECTURE.parent.parent


def _square(lon0, lat0, lon1, lat1):
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]}


@pytest.fixture()
def maps(tmp_path, monkeypatch):
    """A historical map of 1600 with two states, and no network."""
    import historical

    folder = tmp_path / "historical"
    folder.mkdir()
    features = [
        {"type": "Feature", "properties": {"NAME": "Mughal Empire", "SUBJECTO": "Mughal Empire"},
         "geometry": _square(68, 20, 88, 34)},
        {"type": "Feature", "properties": {"NAME": "Golkonda", "SUBJECTO": "Golkonda"},
         "geometry": _square(76, 14, 82, 19)},
        {"type": "Feature", "properties": {"NAME": "Kandahar", "SUBJECTO": "Mughal Empire"},
         "geometry": _square(64, 30, 67, 33)},
    ]
    text = json.dumps({"type": "FeatureCollection", "features": features})
    (folder / "world_1600.geojson").write_text(text + " " * 1000)
    monkeypatch.setenv("PANIM_HISTORICAL_DIR", str(folder))
    monkeypatch.setenv("PANIM_HISTORICAL_FETCH", "0")
    historical._features.cache_clear()
    yield folder
    historical._features.cache_clear()


def test_a_state_is_found_as_it_stood_in_the_nearest_year(maps):
    import historical

    assert historical.nearest(1605) == 1600 and historical.nearest(-250) == -200
    shape, name, year = historical.empire("Mughals", 1605)
    assert name == "Mughal Empire" and year == 1600
    assert shape.bounds[0] <= 64.01                                   # with Kandahar, subject to it
    assert historical.empire("Vijayanagara", 1600) is None
    assert historical.empire("Mughal Empire", 1800) is None          # no 1800 map here, and none fetched


def test_the_compiler_reads_years_and_drops_a_state_the_map_does_not_have(maps):
    assert cl._year_of("c. 1600") == 1600 and cl._year_of("250 BC") == -250 and cl._year_of(1526) == 1526
    script = {"title": "T", "style": "parchment", "region": {"country": "India"}, "auto_visuals": False,
              "place_figures": False, "chapters": [{"title": "A", "beats": [
                  {"say": "The Mughals ruled the north.", "do": [{"op": "empire", "name": "Mughal Empire",
                                                                  "year": "c. 1600"}]},
                  {"say": "And a kingdom that never was.", "do": [{"op": "empire", "name": "Atlantis",
                                                                   "year": 1600}]}]}]}
    errors, warnings = cl.lint(script)
    assert not errors
    beats = script["chapters"][0]["beats"]
    assert beats[0]["do"] == [{"op": "empire", "name": "Mughal Empire", "year": 1600}]
    assert beats[1]["do"] == []
    assert any("Atlantis" in w for w in warnings)
    source = cl.compile_script(script)
    assert 'self.empire("Mughal Empire", 1600)' in source


def test_a_labelled_arrow_and_relief_compile():
    script = {"title": "T", "style": "parchment", "region": {"country": "India"}, "auto_visuals": False,
              "place_figures": False, "chapters": [{"title": "A", "beats": [
                  {"say": "The Himalayas wall the north.", "do": [{"op": "relief", "names": ["Himalayas"]}]},
                  {"say": "Spices went from Delhi to Surat.", "do": [{"op": "arrow", "points": [[77.2, 28.6],
                                                                                              [72.8, 21.2]],
                                                                      "label": "spices"}]}]}]}
    assert cl.lint(script)[0] == []
    source = cl.compile_script(script)
    assert "self.relief(['Himalayas'])" in source
    assert 'label="spices"' in source


def test_the_map_draws_the_past_the_land_and_where_it_is(maps, tmp_path):
    """The engine: an empire filled and named, an arrow's label riding to its middle clear of other labels, the
    mountains with hill marks, and a locator inset only when the map is zoomed well in."""
    import pocket_lecture as pl

    class Probe(pl.MapLecture):
        REGION = dict(country="India")

        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene._map_taken = []
    assert scene.locator() is None                                    # the whole country: no inset
    shown = scene.empire("Mughal Empire", 1600)
    assert shown is not None and scene.empire("Atlantis", 1600) is None
    arrow = scene.flow([(77.2, 28.6), (72.8, 21.2)], label="spices")
    tag = arrow.animations[0].animations[-1].mobject
    middle = arrow.animations[0].animations[1].mobject.point_from_proportion(0.5)
    assert abs(tag.get_center()[1] - middle[1]) < 1.5
    relief = scene.relief(["Himalayas"])
    assert relief is not None
    marks = relief.animations[1].animations
    assert len(marks) >= 10
    scene.use_frame((76.5, 26.5, 78.5, 28.0))
    scene._map_taken = []
    inset = scene.locator()
    assert inset is not None and inset.get_left()[0] >= -pl.config.frame_width / 2
    assert inset[2].width < inset[1].width / 3                        # the view's box, small inside the country


def test_new_map_ops_export_to_the_phone_as_lines(maps, tmp_path):
    script = {"title": "Mughals", "style": "parchment", "region": {"country": "India"}, "auto_visuals": False,
              "place_figures": False, "chapters": [
                  {"title": "North", "beats": [
                      {"say": "The Mughal Empire held the north.", "do": [{"op": "empire", "name": "Mughal Empire",
                                                                           "year": 1600}]},
                      {"say": "Spices went from Delhi to Surat.", "do": [
                          {"op": "arrow", "points": [[77.2, 28.6], [72.8, 21.2]], "label": "spices"}]}]},
                  {"title": "Near Agra", "beats": [
                      {"say": "Agra and Mathura lie close.", "do": [
                          {"op": "marker", "lonlat": [78.01, 27.18], "label": "Agra"},
                          {"op": "marker", "lonlat": [77.67, 27.49], "label": "Mathura"}]}]}]}
    assert cl.lint(json.loads(json.dumps(script)))[0] == []
    source = cl.compile_script(json.loads(json.dumps(script)))
    assert "self.use_frame(" in source
    (tmp_path / "scene.py").write_text(source)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"),
                          str(tmp_path / "scene.py"), "GeneratedScene", str(tmp_path)], capture_output=True, text=True,
                         timeout=1500, env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [], result


def test_a_country_or_region_is_shaded_not_a_dot():
    """A marker naming an area big enough to see on the map (a country, a region of one) becomes that area shaded
    with its name on it; a town stays a dot. England and Normandy are found from Natural Earth's divisions."""
    script = {"title": "T", "style": "parchment", "teaching_rules": False, "auto_visuals": False,
              "place_figures": False, "region": {"area": "Western Europe"}, "chapters": [{"title": "A", "beats": [
                  {"say": "England and France.", "do": [{"op": "marker", "place": "England", "label": "England"},
                                                         {"op": "marker", "place": "France"}]},
                  {"say": "Normandy and Paris.", "do": [{"op": "marker", "place": "Normandy"},
                                                        {"op": "marker", "place": "Paris", "label": "Paris"}]}]}]}
    errors, warnings = cl.lint(script)
    assert errors == [], errors
    beats = script["chapters"][0]["beats"]
    assert [op["op"] for op in beats[0]["do"]] == ["state", "state"]
    assert beats[0]["do"][1]["label"] == "France"
    assert [op["op"] for op in beats[1]["do"]] == ["state", "marker"]               # Paris stays a dot
    assert sum("is an area: shaded" in w for w in warnings) == 3
    code = cl.compile_script(script)
    assert 'self.fill_state("England", None, 0.6, label="England")' in code


def test_each_area_in_its_own_tone_and_named_once():
    import pocket_lecture as pl

    class Probe(pl.MapLecture):
        REGION = dict(area="Western Europe")

        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.show_map()
    scene._map_taken = []
    scene.play(scene.fill_state("England", label="England"), scene.fill_state("France", label="France"), run_time=0.1)
    fills = scene._shaded
    tone = lambda m: m.get_family()[-1].get_fill_color()  # noqa: E731 -- a piece of the shading, not its group
    assert tone(fills["england"][0]) != tone(fills["france"][0])
    first = fills["england"]
    scene.play(scene.fill_state("England", pl.P.ROSE, label="England"), run_time=0.1)
    on = [m for m in scene.mobjects if any(m is x for x in first)]
    assert on == []                                                                  # the old shading and name went
