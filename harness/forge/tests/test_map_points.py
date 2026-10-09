"""Points on a map are where the places are (pocket_lecture.place, compile_lecture._resolve_map_points): a model's
own [lon, lat] was often tens of kilometres off, historic sites were not found at all, a name two towns share
went to the wrong one, and a site across the border (Harappa on a map of India) was refused."""

from __future__ import annotations

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import pocket_lecture as pl  # noqa: E402


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    monkeypatch.setenv("PANIM_GEOCODE", "0")


@pytest.mark.parametrize("name,where", [
    ("Lothal", (72.25, 22.52)), ("Dandi", (72.80, 20.89)), ("Plassey", (88.25, 23.80)), ("Palashi", (88.25, 23.80)),
    ("Kalinga", (85.84, 20.19)), ("Harappa", (72.86, 30.63)), ("Bodh Gaya", (84.99, 24.70)), ("Jaipur", (75.79, 26.91)),
])
def test_teaching_places_are_found_where_they_are(name, where):
    found = pl.place(name, "India", pl.map_bounds({"country": "India"}))
    assert cl._km(found, where) < 15, found


def test_a_shared_name_goes_to_the_one_on_the_map():
    bihar = pl.map_bounds({"state": "Bihar", "country": "India"})
    assert cl._km(pl.place("Aurangabad", "India", bihar), (84.37, 24.75)) < 20          # Bihar's, not Maharashtra's
    assert cl._km(pl.place("Aurangabad", "India"), (75.34, 19.88)) < 20                # the bigger one otherwise


def _script(ops):
    return {"title": "T", "style": "chalkboard", "region": {"country": "India"},
            "chapters": [{"title": "A", "beats": [{"say": "Here, on the map, is where it happened.", "do": ops}]}]}


def test_guessed_coordinates_give_way_to_the_place():
    script = _script([
        {"op": "marker", "lonlat": [70.0, 25.0], "label": "Lothal"},                    # guessed, 300 km off
        {"op": "marker", "place": "Dandi", "lonlat": [71.0, 19.0]},                      # a name and a guess
        {"op": "journey", "stops": ["Sabarmati Ashram", [73.5, 21.5]], "labels": ["Sabarmati", "Dandi"]},
        {"op": "arrow", "points": ["Delhi", "Agra"]},
    ])
    errors, warnings = cl.lint(script)
    assert not errors, errors
    ops = script["chapters"][0]["beats"][0]["do"]
    assert cl._km(ops[0]["lonlat"], (72.25, 22.52)) < 5 and any("Lothal" in w and "km from where it is" in w
                                                                for w in warnings)
    assert "lonlat" not in ops[1]
    assert cl._km(ops[2]["stops"][1], (72.80, 20.89)) < 5
    assert all(isinstance(p, list) and len(p) == 2 for p in ops[3]["points"])
    assert cl._km(ops[3]["points"][1], (78.01, 27.18)) < 15
    assert "self.flow([(" in cl.compile_script(script)


def test_a_point_off_the_map_is_refused():
    errors = cl.lint(_script([{"op": "marker", "lonlat": [-74.0, 40.7], "label": "Somewhere"}]))[0]
    assert any("is off this map" in e for e in errors), errors
