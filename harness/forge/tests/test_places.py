"""Place lookups for map lectures: every source in order, and the lint that stops a bad name before a render."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from forge.util import LECTURE, REPO  # noqa: F401 -- puts the lecture engine on sys.path

import pocket_lecture as pl


def _row(name, alternates, lat, lon, cc, pop):
    return "\t".join(["1", name, name, ",".join(alternates), str(lat), str(lon), "P", "PPL", cc, "", "", "", "", "",
                      str(pop), "", "", "Asia/Kolkata", "2024-01-01"]) + "\n"


@pytest.fixture
def gazetteer(tmp_path, monkeypatch):
    path = tmp_path / "cities.txt"
    path.write_text(
        _row("Mahmudabad", ["महमूदाबाद"], 27.30, 81.12, "IN", 45000)
        + _row("Fakeville", [], 39.8, -89.64, "US", 116000)
        + _row("Fakeville", [], 42.1, -72.59, "US", 155000)
        + _row("Dhaka", ["Dacca"], 23.71, 90.41, "BD", 10000000),
        encoding="utf-8")
    monkeypatch.setattr(pl, "GEONAMES", path)
    monkeypatch.setenv("PANIM_GEOCODE", "0")
    pl._geonames.cache_clear()
    yield
    pl._geonames.cache_clear()


def test_renamed_cities_both_ways():
    assert pl.place("Prayagraj", "India") == pl.place("Allahabad", "India")
    assert pl.place("Bangalore", "India") == pl.place("Bengaluru", "India")


def test_extra_places():
    lon, lat = pl.place("Lakhimpur Kheri", "India")
    assert 80 < lon < 81.5 and 27.5 < lat < 28.5


def test_geonames(gazetteer):
    assert pl.place("Mahmudabad", "India") == (81.12, 27.30)
    assert pl.place("महमूदाबाद", "India") == (81.12, 27.30)          # an alternate name, in Devanagari
    assert pl.place("Fakeville", "United States of America") == (-72.59, 42.1)     # the most populous
    # Looked up in the country first, then anywhere (Harappa on a map of India): Nepal has none, India's is found.
    assert pl.place("Mahmudabad", "Nepal") == (81.12, 27.30)
    with pytest.raises(KeyError):
        pl.place("Nowhere At All", "Nepal")


def test_an_unknown_place_is_left_out(monkeypatch):
    monkeypatch.setenv("PANIM_GEOCODE", "0")
    script = {"title": "T", "style": "vox", "region": {"country": "India"},
              "chapters": [{"title": "A", "narration": "x", "beats": [
                  {"say": "one two three four five six seven eight", "do": [{"op": "marker", "place": "Nowhere Town"}]}]}]}
    out = subprocess.run([sys.executable, str(LECTURE / "compile_lecture.py"), "-", "--check"],
                         input=json.dumps(script), capture_output=True, text=True, env={**__import__("os").environ})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert not result["errors"]
    assert any(w.startswith("fixed:") and "no place named 'Nowhere Town'" in w for w in result["warnings"])
