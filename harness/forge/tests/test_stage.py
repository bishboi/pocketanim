"""The stage: pictures made by the image model as cutouts (never searched for on the web), and the map only when
needed."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from forge.util import LECTURE


@pytest.fixture
def generated(monkeypatch, tmp_path):
    """Pictures made offline: the image model's stand-in (genimage PANIM_IMAGE_FAKE), in a cache of the test's own."""
    monkeypatch.setenv("PANIM_IMAGE_FAKE", "1")
    monkeypatch.delenv("PANIM_IMAGES", raising=False)
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path / "images"))
    sys.path.insert(0, str(LECTURE))
    import importlib

    import genimage
    import images

    importlib.reload(genimage)
    importlib.reload(images)
    genimage.MADE.clear()
    return images


def test_pictures_are_made_never_searched(generated, monkeypatch):
    """A photo, an illustration or a picture beside a label is made by the image model, as a cutout: transparent
    around the subject, trimmed, no border. Nothing is fetched from the web."""
    import urllib.request

    from PIL import Image

    import genimage

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("the web was searched"))
    row = generated.fetch(subject="Mahatma Gandhi")
    assert row and row["source"] == "generated" and row["title"] == "Mahatma Gandhi"
    picture = Image.open(row["png"])
    assert picture.mode == "RGBA" and picture.getpixel((0, 0))[3] == 0 and picture.size[0] < 320
    # Shown as vector shapes, so the phone draws it (a raster would play only as sampled frames).
    assert row["file"].endswith(".svg") and "<path" in open(row["file"]).read()
    assert "CUTOUT" in row["prompt"] and "no border" in row["prompt"] and "No words" in row["prompt"]
    assert len(genimage.MADE) == 1
    again = generated.fetch(subject="Mahatma Gandhi")          # made once: from the cache, nothing paid again
    assert again["file"] == row["file"] and "paid" in again and len(genimage.MADE) == 1
    assert generated.fetch(illustration="a map of the Mughal Empire") is None       # maps are drawn on the map
    assert generated.credit([row]) == f"Pictures made with {genimage.model()}"


def test_no_pictures_without_an_image_model(monkeypatch, tmp_path):
    sys.path.insert(0, str(LECTURE))
    import importlib

    import genimage
    import images

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("PANIM_IMAGE_FAKE", raising=False)
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path / "images"))
    importlib.reload(genimage)
    assert not images.enabled() and images.fetch(subject="Mahatma Gandhi") is None


def _compile(script, env):
    out = subprocess.run([sys.executable, str(LECTURE / "compile_lecture.py"), "-", "--json"], input=json.dumps(script),
                         capture_output=True, text=True, env=env)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_map_only_when_a_beat_points_at_it(generated):
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
    assert "show_map" not in first and "self.board()" in first         # no map where no beat needs one: the board
    assert first.count("stage_image") == 1                              # the photo holds its paragraph
    assert "self.illustration(" not in source and "self.icon(" not in source    # no icons anywhere
    assert "show_map" in second
    assert second.index("clear_stage") < second.index("self.mark(")    # the photo leaves when the map is needed
    tractor = second.split("self.beat(")[-1]
    assert "stage_image" not in tractor                                 # the map carries its paragraph
    assert "Pictures made with" in source.split("self.credits(")[1]


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


def test_a_lecture_of_generated_pictures_plays_on_the_phone(generated, tmp_path):
    """Generated pictures are traced into vector shapes, so a lecture of them is tier 1 (no raster blocker) and
    no frame is drawn around a cutout."""
    import os

    from forge.util import REPO

    script = {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "Animals", "map": False, "narration": "x", "beats": [
            {"say": "A deer in the forest.", "do": [{"op": "picture", "generate": "a red deer, side view"}]},
            {"say": "Two more.", "do": [{"op": "picture", "items": [{"generate": "a fox", "caption": "Fox"},
                                                                    {"generate": "a rabbit", "caption": "Rabbit"}]}]},
            {"say": "Who eats whom.", "do": [{"op": "diagram", "id": "d", "edges": [["g", "r"]], "nodes": [
                {"id": "g", "label": "Grass", "entity": "grass"}, {"id": "r", "label": "Deer"}]}]}]}]}
    result = _compile(script, dict(os.environ))
    assert result["errors"] == [], result["errors"]
    assert len(result["generated"]) == 4                     # deer, fox, rabbit, grass: each made once
    scene = tmp_path / "scene.py"
    scene.write_text(result["source"])
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path / "build")], capture_output=True, text=True, timeout=1500,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    exported = json.loads(out.stdout.strip().splitlines()[-1])
    assert exported["tier"] == 1 and exported["blockers"] == [], exported
