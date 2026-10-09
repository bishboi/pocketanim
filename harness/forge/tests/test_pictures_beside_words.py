"""Pictures beside words: a diagram's node, a timeline's event and a map marker's label may carry a picture (a web
photo, a book figure, a drawing made for the lecture, a library drawing), and nothing covers anything else -- the
diagram lays out each box with its picture, the timeline keeps each event inside its slot, and the map's labels are
placed where no label, picture or marker is (pocket_lecture.place_label)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import pocket_lecture as pl  # noqa: E402

from test_sims_more import REPO  # noqa: E402

FIXTURES = REPO / "harness" / "forge" / "tests" / "fixtures" / "figures"


@pytest.fixture
def photos(tmp_path):
    from PIL import Image

    files = {}
    for name, colour in (("granite", "#B8A898"), ("basalt", "#3A3A3A"), ("fort", "#B0503A"), ("taj", "#E0D8C8")):
        files[name] = tmp_path / f"{name}.jpg"
        Image.new("RGB", (320, 220), colour).save(files[name])
    return {k: {"file": str(v), "caption": k} for k, v in files.items()}


def _lecture(figures):
    return {
        "title": "Pictures", "style": "chalkboard", "art": "clean", "figures": figures, "place_figures": False,
        "auto_visuals": False, "region": {"country": "India"},
        "chapters": [
            {"title": "Rocks", "map": False, "beats": [
                {"say": "Rocks come in families; here is what two of the igneous ones look like.",
                 "do": [{"op": "diagram", "id": "rocks", "kind": "hierarchy", "nodes": [
                     {"id": "rock", "label": "Rock"}, {"id": "ig", "label": "Igneous"},
                     {"id": "sed", "label": "Sedimentary", "picture": {"entity": "mountain"}},
                     {"id": "granite", "label": "Granite", "picture": {"figure": "granite"}},
                     {"id": "basalt", "label": "Basalt", "picture": {"figure": "basalt"}}],
                     "edges": [["rock", "ig"], ["rock", "sed"], ["ig", "granite"], ["ig", "basalt"]]}]}]},
            {"title": "Mughals", "map": False, "beats": [
                {"say": "From the first battle to the great tomb, and the long decline after it.",
                 "do": [{"op": "timeline", "events": [
                     ["1526", "Panipat", {"figure": "fort"}], ["1556", "Akbar"],
                     ["1632", "Taj Mahal begun", {"figure": "taj"}],
                     {"date": "1857", "label": "The end", "picture": {"draw": "a ruin", "svg": str(FIXTURES / "circuit.svg")}}]}]}]},
            {"title": "Around Agra", "beats": [
                {"say": "Delhi was the capital, with its fort.",
                 "do": [{"op": "marker", "place": "Delhi", "picture": {"figure": "fort"}}]},
                {"say": "Agra, close by, has the Taj Mahal, and Mathura lies between them.",
                 "do": [{"op": "marker", "place": "Agra", "picture": {"figure": "taj"}},
                        {"op": "marker", "place": "Mathura"}]}]},
        ]}


def test_pictures_are_checked_and_resolved(photos):
    script = _lecture(photos)
    assert not cl.lint(script)[0]
    bad = _lecture(photos)
    bad["chapters"][0]["beats"][0]["do"][0]["nodes"][3]["picture"] = {"figure": "nope"}
    assert any("no book figure 'nope'" in e for e in cl.lint(bad)[0])
    two = _lecture(photos)
    two["chapters"][2]["beats"][0]["do"][0]["picture"] = {"figure": "fort", "entity": "fort"}
    assert any("a picture is one of" in e for e in cl.lint(two)[0])
    mapped = _lecture(photos)
    mapped["chapters"][1]["beats"][0]["do"][0]["events"][1].append({"illustration": "map of the Mughal Empire"})
    assert any("is never drawn as a picture" in e for e in cl.lint(mapped)[0])
    # A picture that was never drawn, or whose file is gone, leaves its words alone.
    assert cl._picture_value({"draw": "x"}) is None and cl._picture_value({"draw": "x", "svg": "/no/such.svg"}) is None
    assert cl._picture_value({"entity": "cow"}) == ("entity", "cow")


def test_web_pictures_count_towards_the_budget(monkeypatch, photos):
    monkeypatch.delenv("PANIM_WEB_PICTURES", raising=False)
    op = {"op": "diagram", "id": "d", "kind": "flow", "nodes": [
        {"id": "a", "label": "A", "picture": {"subject": "Marie Curie"}},
        {"id": "b", "label": "B", "picture": {"query": "radium"}}, {"id": "c", "label": "C", "picture": {"figure": "fort"}}]}
    script = {"title": "T", "style": "chalkboard", "figures": photos,
              "chapters": [{"title": "A", "beats": [{"say": "Here they are.", "do": [op]}]}]}
    assert len(cl.web_pictures(script)) == 2                       # the book's own figure is not from the web


def _dummy_map():
    taken = []
    return SimpleNamespace(_taken=lambda: taken), taken


def test_map_labels_never_overlap():
    """Labels for a tight cluster of places (as a zoomed-out map has around Delhi and Agra): each placed clear of
    every label and dot before it, on the map, clear of the panel."""
    from manim import Text

    scene, taken = _dummy_map()
    points = [np.array([x, y, 0.0]) for x, y in [(-3.0, 1.0), (-2.9, 0.9), (-3.05, 0.8), (-2.85, 1.1), (-3.1, 1.05),
                                                  (-2.95, 0.95), (-3.0, 0.85), (-2.8, 1.0)]]
    for q in points:                                                   # reserved, as a chapter does
        taken.append((q[0] - 0.13, q[1] - 0.13, q[0] + 0.13, q[1] + 0.13))
    reserved = len(taken)
    tags = []
    for k, q in enumerate(points):
        tag = Text(f"Place number {k}", font_size=20)
        pl.MapLecture.place_label(scene, tag, q, 0.17)
        tags.append(tag)
    boxes = [pl._bbox(t) for t in tags]
    for i in range(len(boxes)):
        assert boxes[i][2] <= pl.PANEL_X                              # never under the panel
        for j in range(i + 1, len(boxes)):
            assert pl._overlap(boxes[i], boxes[j]) == 0, (i, j)
        for d in taken[:reserved]:                                    # no label covers a dot
            assert pl._overlap(boxes[i], d) == 0, i


def test_timeline_events_never_touch(tmp_path, photos):
    """Wide photos on every event: shrunk until no two events on a side touch."""
    built = {}

    class Probe(pl.MapLecture):
        def _to_stage(self, group, draw=None):
            built["group"] = group

    scene = Probe.__new__(Probe)
    scene.STAGE = (-2.0, 0.0, 9.0, 6.0)
    pl.use_style("chalkboard")
    wide = [("1526", "Panipat, the first battle", ("image", photos["fort"]["file"]))] * 7
    scene.big_timeline(wide)
    timeline = built["group"][0][0]
    marks = list(timeline[1:])
    assert not pl._touching([m[1:] for m in marks])


def test_pictures_play_on_the_phone(tmp_path, photos):
    """Built and exported: drawn pictures are shapes in the program, photos go on the image track."""
    scene = tmp_path / "scene.py"
    scene.write_text(cl.compile_script(_lecture(photos)))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path)], capture_output=True, text=True, timeout=1500,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    # Photos are always reported (the phone draws them from the image track), and nothing else blocks.
    assert set(result["blockers"]) <= {"raster image (ImageMobject): the phone plays sampled frames"}, result
    assert not result.get("skipped"), result["skipped"]
    track = json.loads((tmp_path / "dsl" / "generated" / "GeneratedScene.images.json").read_text())
    assert len(track) == 6                                  # 2 rock photos, 2 timeline photos, 2 marker photos
