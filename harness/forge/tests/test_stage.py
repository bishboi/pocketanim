"""The stage: photos (Wikimedia Commons, reusable licences only), illustrations, and the map only when needed."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import threading
from http.server import HTTPServer

import pytest

from forge.util import LECTURE

sys.path.insert(0, str(LECTURE / "tests"))
import mock_commons  # noqa: E402


@pytest.fixture
def commons(monkeypatch, tmp_path):
    server = HTTPServer(("127.0.0.1", 0), mock_commons.Handler)
    mock_commons.PORT["value"] = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("COMMONS_API", f"http://127.0.0.1:{server.server_port}/w/api.php")
    monkeypatch.setenv("OPENVERSE_API", f"http://127.0.0.1:{server.server_port}/openverse/")
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path / "images"))
    import images

    importlib.reload(images)
    yield images
    server.shutdown()


def test_only_reusable_photos_and_their_credits(commons):
    rows = commons.search("sugarcane")
    assert [r["id"] for r in rows] == ["File:Sugarcane field in Uttar Pradesh.jpg"]     # "All rights reserved" skipped
    assert rows[0]["credit"] == "A. Farmer, CC BY-SA 4.0, via Wikimedia Commons"
    got = commons.fetch(query="wheat")
    assert got and got["license"] == "CC0" and __import__("pathlib").Path(got["file"]).stat().st_size > 1000
    assert "Wheat harvest India (B. Grower, CC0" in commons.credit([got])


def _compile(script, env):
    out = subprocess.run([sys.executable, str(LECTURE / "compile_lecture.py"), "-", "--json"], input=json.dumps(script),
                         capture_output=True, text=True, env=env)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_map_only_when_a_beat_points_at_it(commons):
    import os

    beat = lambda say, *ops: {"say": say, "do": list(ops)}  # noqa: E731
    script = {"title": "T", "style": "vox", "region": {"state": "Uttar Pradesh", "country": "India"}, "chapters": [
        {"title": "Crops", "narration": "One.", "beats": [
            beat("Sugarcane feeds the sugar mills of the west.", {"op": "photo", "query": "sugarcane"}),
            beat("In winter the farmers sow wheat across the plain."),
            beat("Wheat is the main crop of the cool season.")]},
        {"title": "Where", "narration": "Two.", "beats": [
            beat("The wheat harvest comes every April.", {"op": "photo", "query": "wheat"}),
            beat("The sugarcane belt lies around Meerut.", {"op": "marker", "place": "Meerut"}),
            beat("Tractors changed farming after the green revolution.")]}]}
    result = _compile(script, dict(os.environ))
    assert result["errors"] == []
    source = result["source"]
    first, second = source.split("# 02")
    assert "show_map" not in first and "add_panel" in first            # no map where no beat needs one
    assert first.count("stage_image") == 2                              # a photo, then a diagram of the wheat beat
    assert "G. Botanist" in first.split("self.beat(")[3]                # the wheat beat: the wheat plant diagram
    assert "self.illustration(" not in source and "self.icon(" not in source    # no icons anywhere
    assert "show_map" in second
    assert second.index("clear_stage") < second.index("self.mark(")    # the photo leaves when the map is needed
    tractor = second.split("self.beat(")[-1]
    assert "stage_image" in tractor                                     # the tractor beat covers the map again
    credits = source.split("self.credits(")[1]
    assert "Photos: " in credits and "H. Drafter" in credits and "G. Botanist" in credits
    assert "Company logo" not in source


def test_illustrations_are_educational_and_reusable(commons):
    rows = commons.illustrations("water cycle")
    assert rows and rows[0]["id"] == "File:Water cycle diagram.svg" and rows[0]["license"] == "CC BY 4.0"
    assert all("logo" not in r["title"].lower() for r in commons.illustrations("wheat tractor water"))
    got = commons.fetch(illustration="water cycle")
    assert got and got["file"].endswith(".png")
    # Already shown: not offered again, even from the cache.
    again = commons.fetch(illustration="water cycle", avoid={"File:Water cycle diagram.svg"})
    assert again is None or again["id"] != "File:Water cycle diagram.svg"


def test_icon_ops_become_markers_facts_and_illustrations():
    from compile_lecture import no_icons

    script = {"chapters": [{"beats": [{"say": "x", "do": [
        {"op": "icon", "name": "game-icons:sugar-cane", "places": ["Meerut", [77.5, 29.9]]},
        {"op": "icon", "name": "wheat", "label": "Rabi: wheat"},
        {"op": "illustration", "icon": "fluent-emoji-flat:tractor", "title": "Machines"}]}]}]}
    ops = no_icons(script)["chapters"][0]["beats"][0]["do"]
    assert ops == [{"op": "marker", "place": "Meerut", "label": "Sugar cane"},
                   {"op": "marker", "lonlat": [77.5, 29.9], "label": ""},
                   {"op": "fact", "text": "Rabi: wheat"},
                   {"op": "illustration", "query": "tractor", "caption": "Machines"}]


@pytest.fixture
def wikipedia(commons, monkeypatch):
    import mock_commons as mock

    monkeypatch.setenv("WIKIPEDIA_API", f"http://127.0.0.1:{mock.PORT['value']}/wiki/{{lang}}/w/api.php")
    return commons


def test_wikipedia_picture_of_a_named_subject(wikipedia):
    images = wikipedia
    row = images.portrait("Chipko Movement")                    # a redirect: any capitalisation
    assert row and row["id"] == "File:Chipko movement women hugging trees.jpg" and row["source"] == "wikipedia"
    assert images.portrait("चिपको आन्दोलन")["subject"] == "Chipko movement"   # Hindi article -> English picture
    assert images.portrait("Some Film") is None                  # a non-free local image is not used
    assert images.portrait("Nobody Anywhere") is None
    found = images.find("Sunderlal Bahuguna")
    assert found[0]["source"] == "wikipedia" and found[0]["license"] == "CC BY 2.0"


def test_named_people_and_movements_get_their_picture(wikipedia):
    import os

    import mock_commons as mock

    beat = lambda say, *ops, **kw: {"say": say, "do": list(ops), **kw}  # noqa: E731
    script = {"title": "Forests", "style": "parchment", "chapters": [
        {"title": "People", "narration": "One.", "beats": [
            beat("In the Himalayas, Sunderlal Bahuguna walked from village to village."),
            beat("गाँव की महिलाओं ने पेड़ों को गले लगाया।", about="Chipko movement"),
            beat("Nobody Anywhere is not a real person."),
            beat("Here the book's own figure shows the forest.", {"op": "figure", "id": "fig1"})]}],
        "figures": {"fig1": {"file": str(LECTURE / "tests" / "mock_commons.py"), "caption": "A forest"}}}
    env = {**os.environ, "WIKIPEDIA_API": f"http://127.0.0.1:{mock.PORT['value']}/wiki/{{lang}}/w/api.php"}
    result = _compile(script, env)
    assert result["errors"] == [], result["errors"]
    source = result["source"].split("# 01")[1]
    beats = source.split("self.beat(")[1:]
    assert "stage_image" in beats[0] and "Sunderlal Bahuguna" in beats[0].split("stage_image")[1]
    assert "stage_image" in beats[1] and "Chipko movement" in beats[1].split("stage_image")[1]
    assert "stage_image" not in beats[2] and "stage_image" not in beats[3]
    assert "Sunderlal Bahuguna portrait" in result["source"].split("self.credits(")[1]


def test_preview_carries_images_and_keeps_time(tmp_path):
    """A photo fades in with its caption and out again: the program keeps the caption and the fade's time,
    and the image track places the photo for the preview."""
    from forge.util import REPO

    from PIL import Image

    Image.new("RGB", (64, 40), "#3C7A3E").save(tmp_path / "photo.png")
    scene = tmp_path / "photo_scene.py"
    scene.write_text(f'''from manim import *

class PhotoScene(Scene):
    def construct(self):
        image = ImageMobject({str(tmp_path / "photo.png")!r}).scale_to_fit_width(4).shift(LEFT * 2)
        caption = Text("A forest").scale(0.5).next_to(image, DOWN)
        group = Group(image, caption)
        self.play(FadeIn(group), run_time=1)
        self.wait(2)
        self.play(FadeOut(group), run_time=1)
        self.play(FadeIn(ImageMobject({str(tmp_path / "photo.png")!r})), run_time=1)
        self.wait(1)
''')
    out = tmp_path / "build"
    run = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "PhotoScene", str(out)], capture_output=True, text=True, cwd=REPO)
    result = json.loads(run.stdout.strip().splitlines()[-1])
    assert result["blockers"] == ["raster image (ImageMobject): the phone plays sampled frames"], result
    assert result["images"] == 2
    program = result["program"]
    assert "fade " in program and "fadeout " in program            # the caption still fades in and out
    track = json.loads((out / "dsl" / "generated" / "PhotoScene.images.json").read_text())
    first = track[0]["keys"]
    assert first[0][1] == 0 and max(k[1] for k in first) == 1 and first[-1][1] == 0   # fades in, then out
    assert (out / "dsl" / "generated" / "images" / track[0]["asset"]).is_file()
    ul_x, ul_y, ur_x = first[1][2], first[1][3], first[1][4]
    assert abs((ur_x - ul_x) - 4) < 0.01 and ul_x < -3.9            # 4 units wide, shifted left

    from dsl.interpret import parse, timeline_frames

    frames = timeline_frames(parse(program)["timeline"], 30)
    assert abs(frames / 30 - 6.0) < 0.2                              # every play kept its time, the image-only fade too
