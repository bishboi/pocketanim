"""Maps are drawn one way only: Natural Earth's geometry projected through Cartopy (pocket_lecture.MapFrame). A map
asked of anything else -- an SVG drawing, a block of free Manim, an illustration, a photo, a picture search's map
file, an AI picture -- is refused (mapguard.py), and an art style colours the map's lines without moving them."""

from __future__ import annotations

import numpy as np
import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import artstyle  # noqa: E402
import compile_lecture as cl  # noqa: E402
import images  # noqa: E402
import illustrations  # noqa: E402
import mapguard  # noqa: E402


MAPS = ["A map of the Mughal Empire at its height", "the outline of India with its states",
        "Trade routes across the Indian Ocean", "The Dandi March from Sabarmati to Dandi",
        "political map of Europe in 1914", "the borders between France and Spain",
        "Continents and oceans of the world", "the extent of the Roman Empire under Trajan",
        "states of India coloured by rainfall", "Vasco da Gama's voyage around Africa", "The Silk Road",
        "the route from Delhi to Agra", "the coastlines of South America"]
NOT_MAPS = ["A concept map of photosynthesis", "a function maps x to y", "the border of the cell membrane",
            "A plant cell in cross-section", "the journey of a Red blood cell", "the shape of the Earth",
            "Mind map of the causes of the First World War", "states of matter: solid, liquid, gas",
            "a heat map of the data", "the water cycle over land and sea", "A volcano in cross-section",
            "A light ray from air to glass", "the spread of the infection through the body"]


@pytest.mark.parametrize("text", MAPS)
def test_a_map_is_recognised(text):
    assert mapguard.is_map(text)


@pytest.mark.parametrize("text", NOT_MAPS)
def test_what_is_not_a_map_is_left_alone(text):
    assert not mapguard.is_map(text)


def test_manim_that_draws_a_map_is_recognised():
    assert mapguard.code_draws_map("coast = VMobject().set_points_as_corners(pts)")
    assert mapguard.code_draws_map("pts = [(lon, lat) for lon, lat in rows]")
    assert mapguard.code_draws_map("t = Text('Map of Asia')")
    assert mapguard.code_draws_map("# the outline of India\nshape = Polygon(*pts)")
    assert not mapguard.code_draws_map("vals = list(map(lambda v: v * 2, xs))\nborder = Rectangle()")
    assert not mapguard.code_draws_map("wedge = Polygon(*pts)\nself.play(Create(wedge))")


def _script(op, region=True):
    script = {"title": "T", "style": "chalkboard",
              "chapters": [{"title": "A", "map": False, "beats": [{"say": "Here it is, as it was.", "do": [op]}]}]}
    if region:
        script["region"] = {"country": "India"}
    return script


@pytest.mark.parametrize("op", [
    {"op": "draw", "id": "empire", "what": "A map of the Mughal Empire at its height", "parts": ["empire"]},
    {"op": "manim", "id": "m", "code": "coast = Polygon(*india_outline)\nself.play(Create(coast))"},
    {"op": "illustration", "query": "map of the Roman Empire"},
    {"op": "photo", "query": "Silk Road trade routes"},
    {"op": "gallery", "items": [{"illustration": "political map of Europe in 1914", "caption": "Europe"},
                                {"subject": "Otto von Bismarck"}]},
])
def test_the_compiler_refuses_a_map_drawn_any_other_way(op):
    errors = cl.lint(_script(op))[0]
    assert any("is never drawn as a picture" in e for e in errors), errors


def test_the_compiler_lets_other_pictures_through():
    op = {"op": "draw", "id": "cell", "what": "A plant cell in cross-section with its organelles",
          "parts": ["wall", "nucleus"]}
    assert not any("never drawn as a picture" in e for e in cl.lint(_script(op, region=False))[0])


def test_picture_searches_drop_map_files():
    for title in ("File:India-locator-map-blank.svg", "File:Rajasthan in India (disputed hatched).svg",
                  "File:Kerala in India.svg", "File:Mughal Empire map.png"):
        assert images.is_map_row({"title": title}), title
    for title in ("File:Taj Mahal in Agra.jpg", "File:Hawa Mahal 2011.jpg", "File:Water cycle diagram.svg"):
        assert not images.is_map_row({"title": title}), title


def test_the_ai_never_draws_a_map(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(illustrations, "CACHE", None)          # would fail if it got as far as drawing
    assert illustrations.ai("a map of the Mughal Empire") == []


@pytest.fixture
def _india():
    import pocket_lecture as pl

    pl.use_style("chalkboard")
    frame = pl.MapFrame(pl.country("India"))
    yield pl, frame
    artstyle.use("auto", "chalkboard")


@pytest.mark.parametrize("art", list(artstyle.ART_STYLES))
def test_an_art_style_never_moves_the_map(art, _india):
    """The chalk and sketch styles wobbled coastlines, watercolour washed past them and the detailed style drew a
    second, shrunk coastline: every extra a style puts on the map now lies on Natural Earth's own line, or (hatching)
    inside it."""
    from manim import VGroup

    pl, frame = _india
    artstyle.use(art)
    outline = frame.poly(pl.country("India"), simplify=0.004, min_area=0.00005, fill_color="#C8B88A",
                         fill_opacity=0.1, stroke_color="#FFFFFF", stroke_width=2.2)
    fill = frame.poly(pl.state("Rajasthan", "India"), fill_color="#E07A5F", fill_opacity=0.6, stroke_width=0)
    river = frame.line(pl.river("Ganges"), stroke_color="#4FA3D9", stroke_width=5)
    shapes = [m for group in (outline, fill, river) for m in group]
    before = [m.points.copy() for m in shapes]
    artstyle.dress_map(VGroup(), VGroup(), outline)
    for group in (fill, river):
        artstyle.dress(group)
    for m, points in zip(shapes, before):
        assert np.array_equal(m.points, points)
        lo, hi = points[:, :2].min(axis=0) - 1e-6, points[:, :2].max(axis=0) + 1e-6
        for extra in m.submobjects:
            if not len(extra.points):
                continue
            same = extra.points.shape == points.shape and np.allclose(extra.points, points)
            inside = (extra.points[:, :2] >= lo).all() and (extra.points[:, :2] <= hi).all()
            assert same or inside, f"{art}: an extra off the map's line"
