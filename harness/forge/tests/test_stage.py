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
    # No collections on disk and no other sources: the tests see only the mock, whatever this machine downloaded.
    (tmp_path / "no-collections").mkdir()
    monkeypatch.setenv("PANIM_ILLUSTRATIONS_DIR", str(tmp_path / "no-collections"))
    for name, path in (("NASA_IMAGES_API", "nasa"), ("MET_API", "met"), ("SMITHSONIAN_API", "si")):
        monkeypatch.setenv(name, f"http://127.0.0.1:{server.server_port}/{path}")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
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
    assert first.count("stage_image") == 1                              # the photo holds its paragraph
    assert "self.illustration(" not in source and "self.icon(" not in source    # no icons anywhere
    assert "show_map" in second
    assert second.index("clear_stage") < second.index("self.mark(")    # the photo leaves when the map is needed
    tractor = second.split("self.beat(")[-1]
    assert "stage_image" not in tractor                                 # the map carries its paragraph
    assert "Photos: " in source.split("self.credits(")[1]

    # A new paragraph, with fetched illustrations switched on: a diagram of its topic.
    script["auto_illustrations"] = True
    script["chapters"][0]["beats"][1]["paragraph"] = True
    source = _compile(script, dict(os.environ))["source"]
    first = source.split("# 02")[0]
    assert "G. Botanist" in first.split("self.beat(")[2]                # the wheat paragraph: the wheat diagram
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
    # One paragraph naming two: their pictures together, as a gallery on its first beat.
    assert "self.gallery(" in beats[0]
    assert "Sunderlal Bahuguna" in beats[0].split("self.gallery(")[1] and "Chipko movement" in beats[0]
    assert "stage_image" not in beats[1] and "gallery" not in beats[1] and "gallery" not in beats[2]
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


@pytest.fixture
def sources(commons, monkeypatch, tmp_path):
    """Every illustration source pointed at the mock, and a local collections folder of our own."""
    import importlib

    import mock_commons as mock

    base = f"http://127.0.0.1:{mock.PORT['value']}"
    monkeypatch.setenv("NASA_IMAGES_API", f"{base}/nasa")
    monkeypatch.setenv("MET_API", f"{base}/met")
    monkeypatch.setenv("SMITHSONIAN_API", f"{base}/si")
    monkeypatch.setenv("OPENROUTER_URL", f"{base}/openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("PANIM_ALLOW_NC", raising=False)
    local = tmp_path / "collections"
    from PIL import Image

    (local / "bioart").mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(local / "bioart" / "plant-cell-structure.png")
    (local / "bioart" / "collection.json").write_text(json.dumps(
        {"name": "NIH BioArt", "license": "Public domain", "credit": "NIH BioArt Source"}))
    (local / "nc-book").mkdir()
    (local / "nc-book" / "collection.json").write_text(json.dumps(
        {"name": "Some NC book", "license": "CC BY-NC-SA 4.0", "non_commercial": True, "credit": "NC"}))
    (local / "nc-book" / "index.json").write_text(json.dumps(
        [{"title": "Mitochondria diagram", "caption": "The parts of a mitochondrion", "alt": "",
          "url": f"{base}/img/Mitochondria.jpg"}]))
    monkeypatch.setenv("PANIM_ILLUSTRATIONS_DIR", str(local))
    import illustrations

    importlib.reload(illustrations)
    yield illustrations, mock


def test_local_collections_and_the_non_commercial_switch(sources, monkeypatch):
    illustrations, _ = sources
    rows = illustrations.find("plant cell structure", genre="biology")
    assert rows[0]["source"] == "local" and rows[0]["credit"] == "NIH BioArt Source" and rows[0]["path"].endswith(".png")
    assert illustrations.find("mitochondria diagram", genre="biology") == [] or \
        all(r["license"] != "CC BY-NC-SA 4.0" for r in illustrations.find("mitochondria diagram", genre="biology"))
    monkeypatch.setenv("PANIM_ALLOW_NC", "1")
    assert illustrations.find("mitochondria diagram", genre="biology")[0]["license"] == "CC BY-NC-SA 4.0"


def test_the_subject_picks_the_sources(sources):
    illustrations, _ = sources
    history = illustrations.find("Akbar", genre="history")
    assert history[0]["source"] == "met" and history[0]["license"] == "CC0" and "Basawan" in history[0]["credit"]
    assert all(r["id"] != "met:12" for r in history)                    # not public domain: skipped
    sword = illustrations.find("Mughal sword", genre="history")
    assert [r["id"] for r in sword if r["source"] == "smithsonian"] == ["si:si1"]   # only CC0 media
    earth = illustrations.find("earth clouds", genre="geography")
    assert earth[0]["source"] == "nasa" and earth[0]["id"] == "nasa:earth01"        # the copyrighted one is skipped


def test_an_ai_illustration_only_when_nothing_else_fits(sources, monkeypatch):
    illustrations, mock = sources
    assert illustrations.find("quantum tunnelling of a unicorn", genre="physics") == []    # no key: no AI
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    illustrations.reset()
    rows = illustrations.find("quantum tunnelling of a unicorn", genre="physics", style="lab")
    assert rows and rows[0]["source"] == "ai" and __import__("pathlib").Path(rows[0]["path"]).stat().st_size > 100
    body = mock.PORT["prompts"][-1]
    assert body["modalities"] == ["image", "text"] and "No words" in body["messages"][0]["content"]
    assert "science-textbook" in body["messages"][0]["content"]
    assert illustrations.find("earth clouds", genre="geography")[0]["source"] == "nasa"     # found: no AI


def test_openstax_index_keeps_own_figures_and_skips_non_commercial(monkeypatch, tmp_path):
    import importlib

    from forge.util import REPO

    sys.path.insert(0, str(REPO / "harness" / "scripts"))
    import fetch_openstax as ox

    importlib.reload(ox)
    pages = {
        "collections/phys.collection.xml": '<md:title>Physics</md:title><md:license url="http://creativecommons.org/'
                                           'licenses/by/4.0/">CC</md:license><col:module document="m1"/>',
        "collections/bio.collection.xml": '<md:title>Biology</md:title><md:license url="http://creativecommons.org/'
                                          'licenses/by-nc-sa/4.0/">CC</md:license><col:module document="m1"/>',
        "modules/m1/index.cnxml": '<title>Waves</title><figure id="f1"><media alt="A wave diagram">'
                                  '<image mime-type="image/png" src="../../media/wave.png"/></media>'
                                  '<caption>The parts of a wave: crest and trough.</caption></figure>'
                                  '<figure id="f2"><media alt="A surfer"><image src="../../media/surf.jpg"/></media>'
                                  '<caption>A surfer rides a wave. (credit: Someone/Flickr)</caption></figure>',
    }
    monkeypatch.setattr(ox, "_get", lambda url: pages[url.split("/main/", 1)[1]])
    monkeypatch.setattr(ox, "TARGET", tmp_path)
    row = ox.index_book("osbooks-x", "collections/phys.collection.xml", "phys", False)
    assert row["license"] == "CC BY 4.0" and row["figures"] == 1       # the credited photo is someone else's
    index = json.loads((tmp_path / "openstax-phys" / "index.json").read_text())
    assert index[0]["caption"].startswith("The parts of a wave") and index[0]["url"].endswith("/media/wave.png")
    assert ox.index_book("osbooks-x", "collections/bio.collection.xml", "bio", False)["skipped"]
    assert not (tmp_path / "openstax-bio").exists()


def test_preview_fades_an_image_when_the_video_does(tmp_path):
    """A picture fading out while a diagram fades in is gone, in the preview, when its own fade ends -- not at
    the end of the whole play, which left new diagrams over a half-visible photo."""
    from forge.util import REPO

    from PIL import Image

    Image.new("RGB", (64, 40), "#3C7A3E").save(tmp_path / "photo.png")
    scene = tmp_path / "swap.py"
    scene.write_text(f'''from manim import *

class Swap(Scene):
    def construct(self):
        photo = ImageMobject({str(tmp_path / "photo.png")!r}).scale_to_fit_width(4)
        self.play(FadeIn(photo), run_time=1)
        self.wait(1)
        box = Square()
        self.play(AnimationGroup(FadeOut(photo, run_time=0.5), FadeIn(box), lag_ratio=1.0), run_time=3)
        self.wait(1)
''')
    out = tmp_path / "build"
    run = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), "Swap",
                          str(out)], capture_output=True, text=True, cwd=REPO)
    assert json.loads(run.stdout.strip().splitlines()[-1])["tier"] == 3
    keys = json.loads((out / "dsl" / "generated" / "Swap.images.json").read_text())[0]["keys"]
    gone = next(k[0] for k in keys if k[1] == 0 and k[0] > 10)
    # The swap play runs from 2 s to 5 s (frames 61-151); the photo's fade is its first third.
    assert 85 <= gone <= 95, keys


def test_boxes_are_solid_and_a_full_figure_clears_the_stage(tmp_path):
    import pocket_lecture as pl
    from manim import ManimColor

    pl.use_style("vox")
    solid = pl._tint_on_bg("#FF0000", 0.12)
    assert isinstance(solid, ManimColor) and solid.to_hex().upper() != "#FF0000"

    from PIL import Image

    Image.new("RGB", (64, 40), "white").save(tmp_path / "f.png")

    class Probe(pl.Lecture):
        def construct(self):
            pass

    scene = Probe()
    scene.stage_items, scene.stage_extra = pl.Group(pl.Square()), [pl.Circle()]
    anim = scene.figure(str(tmp_path / "f.png"), "caption", where="full")
    assert len(scene.stage_items) == 0 and scene.stage_extra == []      # the stage leaves under the figure
    assert len(anim.animations) == 3                                     # the figure in, the two stage parts out
