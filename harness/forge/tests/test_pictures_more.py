"""Pictures that do more: a whole scene instead of a cutout, the same person drawn alike in every picture of a
lecture (the first picture of them sent to the model as a reference), and pictures that move once drawn."""

from __future__ import annotations

import base64
import importlib
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402


def _png() -> str:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (160, 90), (255, 255, 255))
    ImageDraw.Draw(image).rectangle((40, 20, 120, 70), fill=(180, 60, 40))
    out = io.BytesIO()
    image.save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


@pytest.fixture
def model(monkeypatch, tmp_path):
    """genimage against a local stand-in for the image model, which keeps every request it is sent."""
    asked: list[dict] = []
    picture = _png()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            asked.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))))
            data = json.dumps({"choices": [{"message": {"images": [{"image_url": {"url": picture}}]}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "test/image-model")
    monkeypatch.setenv("PANIM_IMAGE_API", "chat")
    for name in ("PANIM_IMAGE_FAKE", "PANIM_IMAGES", "PANIM_IMAGE_PROXY", "PANIM_IMAGE_REFERENCE"):
        monkeypatch.delenv(name, raising=False)
    import genimage

    gen = importlib.reload(genimage)
    yield gen, asked
    server.shutdown()


def _text_of(request: dict) -> str:
    content = request["messages"][0]["content"]
    return content if isinstance(content, str) else " ".join(p.get("text", "") for p in content)


def test_a_scene_is_drawn_whole_and_kept_apart_from_cutouts(model):
    gen, asked = model
    scene = gen.generate("a village market in Mughal India", scene=True)
    cutout = gen.generate("a village market in Mughal India")
    assert scene and cutout and scene["png"] != cutout["png"]        # one is not reused for the other
    assert "SCENE" in _text_of(asked[0]) and "CUTOUT" not in _text_of(asked[0])
    assert "CUTOUT" in _text_of(asked[1])
    from PIL import Image

    assert Image.open(scene["png"]).getpixel((2, 2))[:3] == (255, 255, 255)      # its setting kept
    assert Image.open(cutout["png"]).convert("RGBA").getpixel((0, 0))[3] == 0     # cut out of its background
    assert json.loads(open(scene["png"][:-4] + ".json").read())["scene"] is True


def test_a_person_is_drawn_like_their_first_picture(model):
    gen, asked = model
    first = gen.generate("Emperor Akbar, a portrait")
    later = gen.generate("Emperor Akbar riding an elephant into battle")
    other = gen.generate("a camel caravan crossing a desert")
    assert first and later and other
    sent = asked[1]["messages"][0]["content"]
    assert isinstance(sent, list) and sent[0]["type"] == "image_url"            # the first picture, sent with it
    assert "REFERENCE IMAGE shows Emperor Akbar, a portrait" in _text_of(asked[1])
    assert later.get("like") == "Emperor Akbar, a portrait"
    assert isinstance(asked[0]["messages"][0]["content"], str)                 # nothing to match yet
    assert isinstance(asked[2]["messages"][0]["content"], str)                 # no one named in common


def test_the_compiler_carries_scene_and_move():
    assert cl._photo_key({"op": "illustration", "query": "a market", "scene": True}).endswith("|scene")
    script = {"title": "T", "style": "parchment", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "A", "map": False, "beats": [
            {"say": "A ship sails for India.", "do": [{"op": "picture", "generate": "a Portuguese carrack",
                                                       "move": "drift"}]},
            {"say": "A flag flies.", "do": [{"op": "picture", "generate": "a flag", "move": "spin"}]}]}]}
    errors, warnings = cl.lint(script)
    assert not errors
    beats = script["chapters"][0]["beats"]
    assert beats[0]["do"][0]["move"] == "drift" and "move" not in beats[1]["do"][0]
    assert any("'spin' left out" in w for w in warnings)


@pytest.mark.parametrize("kind", ["bob", "sway", "breathe", "drift"])
def test_a_picture_moves_once_it_is_drawn_and_comes_back(kind):
    import pocket_lecture as pl
    from manim import Square

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    image = Square(1.0)
    scene.add(image)
    start = image.get_center().copy(), image.width
    scene._move_picture(image, [], kind)
    tick = scene._live[-1]["updater"]
    seen = []
    for frame in range(1, 30 * 30 + 1):
        scene.last_t = frame / 30
        tick(image, 1 / 30)
        seen.append((image.get_center().copy(), image.width, image.get_top()[1]))
        if frame == 30 * 3:
            assert abs(seen[-1][0] - start[0]).max() < 1e-6 and abs(seen[-1][1] - start[1]) < 1e-6   # still drawing
    moved = max(abs(c - start[0]).max() + abs(w - start[1]) for c, w, _ in seen)
    assert 0.01 < moved < 0.8


def test_an_emblem_and_a_split_picture_compile(monkeypatch, tmp_path):
    monkeypatch.setenv("PANIM_IMAGE_FAKE", "1")
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.delenv("PANIM_IMAGES", raising=False)
    import genimage

    importlib.reload(genimage)
    cl.script_photos.clear()
    script = {"title": "Feudal Society", "style": "parchment", "emblem": "a golden crown", "auto_visuals": False,
              "place_figures": False, "chapters": [{"title": "A", "map": False, "beats": [
                  {"say": "A knight served his lord.", "do": [{"op": "picture", "generate": "a medieval knight",
                                                               "points": ["Fought for his lord", "Held a fief"]}]}]}]}
    source = cl.compile_script(script)
    assert "    EMBLEM = " in source and "gen-" in source.split("EMBLEM = ")[1].splitlines()[0]
    assert "points=['Fought for his lord', 'Held a fief']" in source
    plain = cl.compile_script({**script, "emblem": None})
    assert "EMBLEM" not in plain


def test_each_style_turns_its_chapters_its_own_way(monkeypatch):
    import pocket_lecture as pl
    from manim import Square

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    monkeypatch.delenv("PANIM_TRANSITION", raising=False)
    try:
        kinds = {}
        for style in ("parchment", "chalkboard", "whiteboard", "atlas"):
            pl.use_style(style)
            scene = Probe()
            kinds[style] = scene.transition_kind()
        assert kinds == {"parchment": "page", "chalkboard": "smudge", "whiteboard": "wipe", "atlas": "fade"}
        monkeypatch.setenv("PANIM_TRANSITION", "wipe")
        assert Probe().transition_kind() == "wipe"
        pl.use_style("parchment")
        monkeypatch.setenv("PANIM_TRANSITION", "page")
        scene = Probe()
        scene.setup()
        sheet = scene._sweeper("page")
        assert sheet.width > pl.config.frame_width and sheet.z_index == pl.Z_CHROME - 0.5
    finally:
        pl.use_style("atlas")


def test_an_emblem_that_is_a_picture_not_shapes_is_shown(tmp_path, monkeypatch):
    """An emblem the tracer could not turn into shapes is its PNG: shown on the title, the card and the chapter tag."""
    import pocket_lecture as pl
    from manim import tempconfig
    from PIL import Image

    emblem = tmp_path / "gen-emblem.png"
    Image.new("RGBA", (64, 64), (200, 160, 40, 255)).save(emblem)
    monkeypatch.setenv("PANIM_VOICE", "silent")

    class Probe(pl.MapLecture):
        EMBLEM = str(emblem)
        SECTIONS = ["Intro", "Growth"]

        def construct(self):
            self.title_slide("CHAPTER 13", "Plant Growth", narration="Chapter thirteen.")
            self.chapter(1, "Growth", "", "Growth.")
            assert any(isinstance(m, pl.ImageMobject) for m in self.chrome.get_family())

    with tempconfig({"dry_run": True, "media_dir": str(tmp_path), "disable_caching": True}):
        Probe().render()


def test_a_model_that_takes_words_only_is_asked_again_without_the_reference(monkeypatch, tmp_path):
    """recraft and the like answer a request with a picture in it with HTTP 404 "No endpoints found that support
    image input": the picture is asked for again in words alone, and that model is not sent a reference again."""
    asked: list[dict] = []
    picture = _png()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            asked.append(body)
            if isinstance(body["messages"][0]["content"], list):
                status, reply = 404, {"error": {"message": "No endpoints found that support image input"}}
            else:
                status, reply = 200, {"choices": [{"message": {"images": [{"image_url": {"url": picture}}]}}]}
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "recraft/words-only")
    monkeypatch.setenv("PANIM_IMAGE_API", "chat")
    for name in ("PANIM_IMAGE_FAKE", "PANIM_IMAGES", "PANIM_IMAGE_PROXY", "PANIM_IMAGE_REFERENCE"):
        monkeypatch.delenv(name, raising=False)
    import genimage

    gen = importlib.reload(genimage)
    try:
        assert gen.generate("a Mongol warrior on horseback")
        second = gen.generate("a Mongol horse bow")
        third = gen.generate("a Mongol yurt")
        emblem = gen.generate("a Mongol saddle, a simple bold emblem", match=False)
    finally:
        server.shutdown()
    assert second and third and emblem and not second.get("like")
    kinds = [isinstance(a["messages"][0]["content"], list) for a in asked]
    assert kinds == [False, True, False, False, False]          # one refused try, then words alone from then on
    assert gen.report()["failed"] == []


@pytest.fixture
def two_models(monkeypatch, tmp_path):
    """A stand-in OpenRouter with two image models and a checker that reads images: the checker finds a label
    missing in the first redraw and none in the second."""
    asked: list[dict] = []
    picture = _png()
    verdicts = [{"labels": ["nucleus", "cell wall"], "missing": ["cell wall"], "wrong": [], "structure_ok": True,
                 "notes": "the cell wall label is gone"},
                {"labels": ["nucleus", "cell wall"], "missing": [], "wrong": [], "structure_ok": True, "notes": ""}]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            asked.append(body)
            if body["model"] == "test/vision":
                reply = {"choices": [{"message": {"content": json.dumps(verdicts.pop(0) if verdicts else {})}}]}
            elif body["model"] == "test/muse" and self.path.endswith("/images"):
                reply = {"data": [{"b64_json": picture.split(",", 1)[1]}], "usage": {"cost": 0.01}}
            elif body["model"] == "test/muse":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "test/muse is an image generation model and cannot "
                                                                  "be used with chat/completions. Use the /api/v1/images "
                                                                  "endpoint instead."}}).encode())
                return
            elif body["model"] == "test/words-only" and isinstance(body["messages"][0]["content"], list):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "No endpoints found that support image input"}}).encode())
                return
            else:
                reply = {"choices": [{"message": {"images": [{"image_url": {"url": picture}}]}}]}
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "test/illustrations")
    monkeypatch.setenv("PANIM_DIAGRAM_MODEL", "test/diagrams")
    monkeypatch.setenv("PANIM_LABEL_MODEL", "test/vision")
    monkeypatch.setenv("PANIM_IMAGE_API", "chat")
    for name in ("PANIM_IMAGE_FAKE", "PANIM_IMAGES", "PANIM_IMAGE_PROXY", "PANIM_IMAGE_REFERENCE"):
        monkeypatch.delenv(name, raising=False)
    import genimage

    gen = importlib.reload(genimage)
    figure = tmp_path / "fig3.png"
    figure.write_bytes(base64.b64decode(picture.split(",", 1)[1]))
    yield gen, asked, figure
    server.shutdown()


def test_illustrations_and_labelled_pictures_go_to_their_own_models(two_models):
    gen, asked, _ = two_models
    assert gen.generate("a village market")["model"] == "test/illustrations"
    assert gen.generate("a medieval knight", parts=["helmet", "shield"])["model"] == "test/diagrams"
    assert [a["model"] for a in asked] == ["test/illustrations", "test/diagrams"]
    assert gen.report()["diagram_model"] == "test/diagrams"


def test_a_book_diagram_is_redrawn_from_itself_and_its_labels_checked(two_models):
    gen, asked, figure = two_models
    row = gen.redraw(str(figure), "Fig. 3: a plant cell", "parchment", "the lesson on cells")
    assert row.get("file") and row["ok"] is True and row["model"] == "test/diagrams"
    draws = [a for a in asked if a["model"] == "test/diagrams"]
    checks = [a for a in asked if a["model"] == "test/vision"]
    assert len(draws) == 2 and len(checks) == 2                       # redrawn once more with what was wrong
    first, second = (_text_of(d) for d in draws)
    assert draws[0]["messages"][0]["content"][0]["type"] == "image_url"    # the book's figure, sent with it
    assert "EVERY LABEL" in first and "sepia" in first and "LAST TRY WAS WRONG" not in first
    assert "LAST TRY WAS WRONG" in second and "cell wall" in second
    again = gen.redraw(str(figure), "Fig. 3: a plant cell", "parchment")
    assert again["file"] == row["file"] and len(asked) == 4              # kept: not drawn again


def test_a_diagram_whose_labels_never_come_right_keeps_the_closest_try(two_models, monkeypatch):
    """The book's own picture is never shown: when no try passes the label check, the closest one is kept, and its
    check says what is still off."""
    gen, asked, figure = two_models
    monkeypatch.setenv("PANIM_DIAGRAM_TRIES", "1")
    row = gen.redraw(str(figure), "Fig. 3: a plant cell", "lab")
    assert "error" not in row and row["file"].endswith(".png") and row["ok"] is False
    assert "cell wall" in row["check"]["missing"] + row["check"]["wrong"]


def test_a_words_only_diagram_model_is_told_to_be_changed(two_models, monkeypatch):
    gen, asked, figure = two_models
    monkeypatch.setenv("PANIM_DIAGRAM_MODEL", "test/words-only")
    row = gen.redraw(str(figure), "Fig. 3", "lab")
    assert "takes words only" in row["error"] and "PANIM_DIAGRAM_MODEL" in row["error"]


def test_an_image_api_diagram_model_like_muse_is_sent_the_figure_in_input_references(two_models, monkeypatch):
    """meta/muse-image is served only through OpenRouter's Image API: the book's figure goes with the words in
    input_references (image to image), and the redraw is checked and redone as on chat."""
    gen, asked, figure = two_models
    monkeypatch.setenv("PANIM_DIAGRAM_MODEL", "test/muse")
    monkeypatch.delenv("PANIM_IMAGE_API", raising=False)
    row = gen.redraw(str(figure), "Fig. 3: a plant cell", "lab")
    assert "error" not in row and row["ok"] is True and row["model"] == "test/muse" and row["usd"] == 0.02
    images = [a for a in asked if a["model"] == "test/muse" and "prompt" in a]
    assert len(images) == 2                                           # redrawn once more with what was wrong
    for a in images:
        ref = a["input_references"]
        assert len(ref) == 1 and ref[0]["type"] == "image_url"
        assert ref[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "REDRAW THE ATTACHED FIGURE" in images[0]["prompt"] and "LAST TRY WAS WRONG" in images[1]["prompt"]
