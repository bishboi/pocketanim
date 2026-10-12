"""Pictures that do more: a whole scene instead of a cutout, the same person drawn alike in every picture of a
lecture (the first picture of them sent to the model as a reference), and pictures that move once drawn."""

from __future__ import annotations

import base64
import importlib
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

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
            elif body["model"] == "test/filtered" or (body["model"] == "test/picky"
                                                      and "KEEP THE DIAGRAM FAITHFUL" in json.dumps(body)):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "The response was filtered due to the prompt "
                                                                  "triggering our content management policy."}}).encode())
                return
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
    assert "EVERY LABEL" in first and "LAST TRY WAS WRONG" not in first
    # In the template's look (parchment draws as a pencil-and-ink sketch, in its ink and colours), with no
    # background of its own: the board's colour it is drawn on is cut away.
    import pocket_lecture as pl

    assert "pencil-and-ink sketch" in first and "BEAUTIFULLY" in first and "NO BACKGROUND" in first
    assert pl.THEMES["parchment"]["bg"] in first and pl.THEMES["parchment"]["pal"]["CREAM"] in first
    from PIL import Image

    saved = Image.open(row["file"])
    assert saved.mode == "RGBA" and saved.size[0] < 160 and saved.getpixel((0, 0))[3] == 0      # trimmed, see-through
    assert saved.getpixel((saved.size[0] // 2, saved.size[1] // 2))[3] == 255                     # the figure kept
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
    assert "REFERENCE IMAGE" in images[0]["prompt"] and "LAST TRY WAS WRONG" in images[1]["prompt"]


def test_a_filtered_redraw_is_asked_again_in_plainer_words(two_models, monkeypatch):
    """A content filter that blocks the full redraw prompt: the same model is asked once more in the plainest words
    (no lesson text), and that picture is kept."""
    gen, asked, figure = two_models
    monkeypatch.setenv("PANIM_DIAGRAM_MODEL", "test/picky")
    row = gen.redraw(str(figure), "Fig. 3: a plant cell", "lab", "the lesson on cells")
    assert "error" not in row and row["model"] == "test/picky"
    draws = [json.dumps(a) for a in asked if a["model"] == "test/picky"]
    assert "KEEP THE DIAGRAM FAITHFUL" in draws[0] and "KEEP THE DIAGRAM FAITHFUL" not in draws[1]
    assert "the lesson on cells" not in draws[1] and "plant cell" in draws[1]
    assert "test/picky" not in gen.REFUSED                         # one blocked picture is not a refusal


def test_a_figure_the_filter_always_blocks_goes_to_the_fallback_models(two_models, monkeypatch):
    gen, asked, figure = two_models
    monkeypatch.setenv("PANIM_DIAGRAM_MODEL", "test/filtered")
    row = gen.redraw(str(figure), "Fig. 3: a plant cell", "lab")
    assert "content management policy" in row["error"] and "test/filtered" not in gen.REFUSED
    assert len([a for a in asked if a["model"] == "test/filtered"]) == 2        # full words, then plainest
    monkeypatch.setenv("PANIM_DIAGRAM_FALLBACK_MODELS", "test/filtered, test/diagrams")
    other = figure.with_name("fig4.png")
    other.write_bytes(figure.read_bytes())
    row = gen.redraw(str(other), "Fig. 4: a plant cell", "parchment")
    assert "error" not in row and row["model"] == "test/diagrams" and "(fallback)" in row["credit"]
    assert row["file"].endswith(".png")


def test_a_filtered_illustration_does_not_stop_the_next_one(two_models, monkeypatch):
    """Before, one filtered picture marked the model refused, and every later picture of the compile was skipped
    with the same message. Now only that one fails; a fallback, when set, makes it."""
    gen, asked, _ = two_models
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "test/filtered")
    assert gen.generate("a battle scene") is None
    assert gen.generate("a village well") is None
    assert len([a for a in asked if a["model"] == "test/filtered"]) == 2       # the second was still asked
    monkeypatch.setenv("PANIM_IMAGE_FALLBACK_MODELS", "test/illustrations")
    row = gen.generate("a temple gate")
    assert row and row["model"] == "test/illustrations" and "(fallback)" in row["credit"]


def test_a_figure_that_must_look_as_in_the_book_is_redrawn_close_to_it_not_restyled(two_models):
    """The figure model said EXACT (its look is what is taught): the redraw keeps the book's own drawing and
    colours, only cleaned, with the model's note; the template's art style is not imposed."""
    gen, asked, figure = two_models
    row = gen.redraw(str(figure), "Fig. 3: a plant cell", "parchment", faithful=True,
                     how="a stained microscope view: keep the purple stain")
    assert "error" not in row and row["faithful"] is True
    first = _text_of([a for a in asked if a["model"] == "test/diagrams"][0])
    assert "LOOKS JUST LIKE IT" in first and "Do NOT restyle it" in first and "keep the purple stain" in first
    assert "pencil-and-ink sketch" not in first and "BEAUTIFULLY" not in first
    styled = gen.redraw(str(figure), "Fig. 3: a plant cell", "parchment")
    assert styled["file"] != row["file"]                               # kept apart: a faithful and a styled redraw


def test_a_picture_with_its_own_background_keeps_it():
    """Only a flat colour around a figure is cut away: a photograph or a scene (corners unlike) keeps its own."""
    from PIL import Image

    import genimage as gen

    def png(corners):
        image = Image.new("RGB", (60, 40), (250, 250, 250))
        for (x, y), colour in zip([(0, 0), (59, 0), (0, 39), (59, 39)], corners):
            image.putpixel((x, y), colour)
        out = io.BytesIO()
        image.save(out, "PNG")
        return out.getvalue()

    assert gen.flat_background(png([(250, 250, 250)] * 4))
    assert not gen.flat_background(png([(250, 250, 250), (30, 90, 160), (120, 80, 40), (250, 250, 250)]))


def test_a_compiles_pictures_are_made_at_once_and_the_real_pass_finds_them_made(monkeypatch, tmp_path):
    """The compiler asked for its pictures one by one (10-40 s each, one after another). Now a first pass notes
    them down, they are made several at once (with their labels found), and the real pass asks for nothing new."""
    import time

    picture = _png()
    calls: list[str] = []
    busy = {"now": 0, "most": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            with lock:
                busy["now"] += 1
                busy["most"] = max(busy["most"], busy["now"])
            time.sleep(0.3)
            with lock:
                busy["now"] -= 1
            drawing = "image" in (body.get("modalities") or [])
            calls.append("draw" if drawing else "labels")
            message = ({"images": [{"image_url": {"url": picture}}]} if drawing
                       else {"content": json.dumps({"points": [{"label": "helmet", "x": 0.5, "y": 0.3}]})})
            data = json.dumps({"choices": [{"message": message}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "test/image-model")
    monkeypatch.setenv("PANIM_LABEL_MODEL", "test/vision")
    monkeypatch.setenv("PANIM_IMAGE_API", "chat")
    for name in ("PANIM_IMAGE_FAKE", "PANIM_IMAGES", "PANIM_IMAGE_PROXY", "PANIM_IMAGE_PARALLEL"):
        monkeypatch.delenv(name, raising=False)
    import genimage

    gen = importlib.reload(genimage)
    cl.script_photos.clear()
    things = ["a Portuguese carrack", "a spice market", "a monsoon sky", "a medieval knight"]
    script = {"title": "T", "style": "parchment", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "A", "map": False, "beats": [
            {"say": f"Look at this {k}.", "do": [{"op": "picture", "generate": what,
                                                  **({"labels": ["helmet"]} if "knight" in what else {})}]}
            for k, what in enumerate(things)]}]}
    try:
        cl.prefetch_pictures(script)
        made = list(calls)
        assert made.count("draw") == 4 and made.count("labels") == 1
        assert busy["most"] > 1                                          # several at once
        source = cl.compile_script(script)
    finally:
        server.shutdown()
    assert calls == made                                                  # the real pass asked for nothing new
    assert source.count("/gen-") >= 4 and "collect-" not in source and "helmet" in source
    assert len(gen.SPANS) == 5 and gen.report()["failed"] == []


def test_a_persons_later_picture_waits_only_for_their_first(monkeypatch, tmp_path):
    """Pictures start at once; one of a person already in an earlier one waits for that first picture only (it is
    drawn to match it), not for every other picture."""
    import time

    monkeypatch.setenv("PANIM_IMAGE_FAKE", "1")
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.delenv("PANIM_IMAGES", raising=False)
    import genimage

    gen = importlib.reload(genimage)
    when: dict[str, list[float]] = {}

    def slow(what, **_):
        start = time.time()
        time.sleep(0.4 if what == "Akbar on his throne" else 0.1)
        when[what] = [start, time.time()]
        return None

    monkeypatch.setattr(gen, "generate", slow)
    gen.prefetch([{"what": w, "labels": []} for w in
                  ["Akbar on his throne", "a spice market", "Akbar on horseback", "a monsoon sky"]])
    assert when["Akbar on horseback"][0] >= when["Akbar on his throne"][1] - 0.01      # after his first picture
    assert when["a monsoon sky"][0] < when["Akbar on his throne"][1]                   # not held up by it
    assert gen.PREFETCHED["pictures"] == 4
    assert gen.PREFETCHED["made"] == 0 and gen.PREFETCHED["failed"] == 4      # none came back: none counted made


def test_a_prefetch_says_how_many_failed_and_why(monkeypatch, tmp_path):
    """Pictures the image model refused are counted as failed, with its first reason, not as made."""
    monkeypatch.setenv("PANIM_IMAGE_FAKE", "1")
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.delenv("PANIM_IMAGES", raising=False)
    import genimage

    gen = importlib.reload(genimage)
    png = tmp_path / "x.png"

    def some(what, **_):
        if what.startswith("a "):
            return {"png": str(png)}
        gen.FAILED.append({"what": what, "model": "m", "error": "HTTP 403: not available in your region"})
        return None

    monkeypatch.setattr(gen, "generate", some)
    gen.prefetch([{"what": w, "labels": []} for w in ["a ship", "a market", "Akbar", "Babur"]])
    assert (gen.PREFETCHED["made"], gen.PREFETCHED["failed"]) == (2, 2)
    assert "region" in gen.PREFETCHED["error"] and gen.FAILED == []         # the real pass reports them, once
