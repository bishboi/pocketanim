"""Hierarchies drawn as a textbook draws them (hierarchy.py, pocket_lecture._hierarchy): the main thing on top, its
subcategories below it, theirs below them. And a book's figures, each shown the way that suits it
(app/lib/figures.ts): a photograph made again by the image model as a cutout (genimage.py), a simple diagram
built on the board, the rest redrawn as SVG; with fewer new web pictures the more figures the book has."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from forge.util import LECTURE

import compile_lecture as cl  # noqa: E402
import hierarchy as hi  # noqa: E402

from test_sims_more import REPO  # noqa: E402


APP = REPO / "harness" / "app"

UML = ["diagram", "behaviour", "structure", "activity", "state", "usecase", "interaction", "comm", "overview", "seq",
       "timing", "cls", "comp", "obj", "composite", "deploy", "package", "profile"]
UML_EDGES = [("diagram", "behaviour"), ("diagram", "structure"), ("behaviour", "activity"), ("behaviour", "state"),
             ("behaviour", "interaction"), ("behaviour", "usecase"), ("interaction", "comm"),
             ("interaction", "overview"), ("interaction", "seq"), ("interaction", "timing"), ("structure", "cls"),
             ("structure", "comp"), ("structure", "obj"), ("structure", "composite"), ("structure", "deploy"),
             ("structure", "package"), ("structure", "profile")]
ROCKS = ["rock", "ig", "sed", "met", "granite", "basalt", "sand", "lime", "marble", "slate"]
ROCK_EDGES = [("rock", "ig"), ("rock", "sed"), ("rock", "met"), ("ig", "granite"), ("ig", "basalt"), ("sed", "sand"),
              ("sed", "lime"), ("met", "marble"), ("met", "slate")]


def _sizes(ids, w=1.9, h=0.8):
    return {i: (w, h) for i in ids}


# ---------------------------------------------------------------------------------------------- hierarchies


def test_a_tree_is_recognised():
    assert hi.is_tree(ROCKS, ROCK_EDGES)
    assert not hi.is_tree(["a", "b", "c"], [("a", "b"), ("b", "c")])              # a chain is a flow
    assert not hi.is_tree(["a", "b", "c"], [("a", "b"), ("a", "c"), ("b", "c")])  # c has two parents
    assert not hi.is_tree(["a", "b", "c"], [("a", "b"), ("a", "c"), ("c", "a")])  # a loop


@pytest.mark.parametrize("ids,edges", [(ROCKS, ROCK_EDGES), (UML, UML_EDGES)])
def test_the_main_thing_is_on_top_and_every_kind_below_its_parent(ids, edges):
    sizes = _sizes(ids)
    tree = hi.layout(ids, edges, sizes)
    assert hi.overlaps(tree, sizes) == []
    top = max(tree.centres.values(), key=lambda c: c[1])
    assert tree.centres[ids[0]] == top
    for a, b in edges:
        assert tree.centres[b][1] < tree.centres[a][1], (a, b)
    # Connectors run straight up and across (right angles), from the child to its parent's bottom.
    for p, c, pts in tree.connectors:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            assert abs(x0 - x1) < 1e-9 or abs(y0 - y1) < 1e-9
        px, py = tree.centres[p]
        assert abs(pts[-1][0] - px) < 1e-9 and abs(pts[-1][1] - (py - sizes[p][1] / 2)) < 1e-9


def test_a_small_tree_stays_a_plain_tree_with_parents_centred():
    sizes = _sizes(ROCKS)
    tree = hi.layout(ROCKS, ROCK_EDGES, sizes)
    assert tree.stacked == {}
    for parent in ("ig", "sed", "met"):
        kids = [c for p, c in ROCK_EDGES if p == parent]
        middle = sum(tree.centres[k][0] for k in kids) / len(kids)
        assert abs(tree.centres[parent][0] - middle) < 1e-9


def test_a_wide_tree_stacks_leaves_to_be_drawn_bigger():
    sizes = _sizes(UML)
    tree = hi.layout(UML, UML_EDGES, sizes)
    plain = hi.layout(UML, UML_EDGES, sizes, board=(1000, 6.0))       # a board wide enough never stacks
    assert plain.stacked == {} and tree.stacked
    scale = lambda t: min(12.6 / t.width, 6.0 / t.height)              # noqa: E731
    assert scale(tree) > 1.5 * scale(plain)


def _script(op, figures=None):
    script = {"title": "T", "style": "chalkboard",
              "chapters": [{"title": "A", "beats": [{"say": "Here are the kinds, each with kinds of its own.", "do": [op]}]}]}
    if figures:
        script["figures"] = figures
    return script


def test_the_compiler_takes_a_twenty_box_hierarchy():
    nodes = [{"id": i, "label": i.title()} for i in UML]
    op = {"op": "diagram", "id": "uml", "kind": "hierarchy", "nodes": nodes, "edges": [list(e) for e in UML_EDGES]}
    assert not cl.lint(_script(op))[0]
    many = {**op, "nodes": nodes + [{"id": f"x{k}", "label": "X"} for k in range(3)],
            "edges": [list(e) for e in UML_EDGES] + [[UML[0], f"x{k}"] for k in range(3)]}
    assert any("2-20 nodes" in e for e in cl.lint(_script(many))[0])


def test_a_hierarchy_plays_on_the_phone(tmp_path):
    """Compiled, built and exported: a flow that only branches downwards is drawn as a hierarchy, revealed a level
    at a time, and the phone's program carries every box."""
    nodes = [{"id": i, "label": i.title()} for i in ROCKS]
    script = {"title": "Rocks", "style": "chalkboard", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "Kinds of rock", "map": False, "narration": "Rocks.", "beats": [
            {"say": "Every rock belongs to one of three families.",
             "do": [{"op": "diagram", "id": "rocks", "kind": "flow", "nodes": nodes,
                     "edges": [list(e) for e in ROCK_EDGES], "show": ["rock", "ig", "sed", "met"]}]},
            {"say": "Each family has members you will meet in the field.",
             "do": [{"op": "reveal", "diagram": "rocks", "nodes": ROCKS[4:]}]}]}]}
    assert not cl.lint(script)[0]
    scene = tmp_path / "scene.py"
    scene.write_text(cl.compile_script(script))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path)], capture_output=True, text=True, timeout=1500,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [], result
    program = (tmp_path / "dsl" / "generated" / "GeneratedScene.panim").read_text()
    assert not result.get("skipped"), result
    # On the stage (z 20-21): a shape for every box and every connector, the first level and then the revealed one.
    staged = [line for line in program.splitlines() if line.startswith("geom ") and line.endswith(("z=20", "z=21"))]
    assert len(staged) == len(ROCKS) + len(ROCK_EDGES)


# ---------------------------------------------------------------------------------------------- web pictures


FIGS = {f"fig{k}": {"file": f"/tmp/fig{k}.png", "caption": f"Figure {k}"} for k in range(1, 6)}


def test_a_book_with_many_figures_keeps_every_web_picture(monkeypatch):
    monkeypatch.setattr(cl, "_unfetched_photos", lambda *a, **k: [])
    gallery = {"op": "gallery", "items": [{"subject": "Marie Curie"}, {"subject": "Pierre Curie"}]}
    script = _script(json.loads(json.dumps(gallery)), FIGS)
    warnings = cl.lint(script)[1]
    assert len(script["chapters"][0]["beats"][0]["do"][0]["items"]) == 2
    assert not any("from the web" in w for w in warnings)


def test_no_picture_is_added_without_the_writer(monkeypatch):
    """Whether a paragraph gets a picture, and which kind (generated, an SVG, Manim), is the writer's judgement:
    the compiler adds none of its own (it used to look the people a paragraph names up on Wikipedia)."""
    import images

    monkeypatch.setattr(images, "fetch", lambda **kw: pytest.fail(f"a picture was fetched: {kw}"))
    chapter = {"title": "People", "beats": [{"say": f"{name} changed the world.", "paragraph": True}
                                            for name in ("Gandhi", "Nehru", "Patel", "Bose")]}
    cl.USED_PICTURES.clear()
    assert not [p for p in cl.auto_visuals(chapter, genre="history") if p]


def test_a_photo_figure_shows_the_web_photo_with_its_credit():
    cl.script_figures.clear()
    cl.script_figures.update({"fig1": {"file": "/tmp/ganges.jpg", "caption": "The Ganges", "credit": "C. Boatman, PD",
                                       "web": True}})
    call = cl._op_call({"op": "figure", "id": "fig1", "where": "stage"})
    assert "credit='C. Boatman, PD'" in call or 'credit="C. Boatman, PD"' in call


# ---------------------------------------------------------------------------------------------- lookalike photos


class _Model(BaseHTTPRequestHandler):
    """OpenRouter as the figure drawer meets it: the book's figure is a photo of the Ganges; asked for a picture
    (modalities: image), the image model returns one on a plain white background."""
    CALLS: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = body["messages"]
        flat = json.dumps(messages)
        images = flat.count('"image_url"')
        if "image" in (body.get("modalities") or []):
            from PIL import Image, ImageDraw

            picture = Image.new("RGB", (300, 200), (255, 255, 255))
            ImageDraw.Draw(picture).rectangle((80, 50, 220, 150), fill=(40, 90, 160))
            out = io.BytesIO()
            picture.save(out, "PNG")
            _Model.CALLS.append(("generate", flat))
            message = {"content": "", "images": [{"image_url": {
                "url": "data:image/png;base64," + __import__("base64").b64encode(out.getvalue()).decode()}}]}
        else:
            message = {"content": "PHOTO: Ganges river at Varanasi ghats\nSUBJECT: -"}
            _Model.CALLS.append(("decide", images))
        data = json.dumps({"choices": [{"message": message}], "usage": {"cost": 0.001}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def figures_js(tmp_path_factory):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    out = tmp_path_factory.mktemp("figlib")
    built = subprocess.run([str(tsc), "lib/figures.ts", "--outDir", str(out), "--module", "commonjs", "--target",
                            "es2022", "--skipLibCheck", "--esModuleInterop"], cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    return out / "figures.js"


@pytest.fixture
def servers(tmp_path):
    model = HTTPServer(("127.0.0.1", 0), _Model)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    _Model.CALLS = []
    yield {"model": model.server_port}
    model.shutdown()


def _book_photo(path: Path):
    from PIL import Image

    image = Image.new("RGB", (500, 320), "#3E7CB1")
    out = io.BytesIO()
    image.save(out, format="JPEG")
    path.write_bytes(out.getvalue())


def _draw(figures_js: Path, servers: dict, tmp_path: Path, figure: Path, **extra):
    script = (f"const f = require({json.dumps(str(figures_js))});"
              f"f.drawFigures([{{id: 'fig1', file: {json.dumps(str(figure))}, caption: 'The Ganges at Varanasi'}}], "
              f"{{key: 'k', model: 'm', markdown: '', repo: {json.dumps(str(REPO))}, python: {json.dumps(sys.executable)}}})"
              ".then((r) => console.log(JSON.stringify(r)));")
    env = {"PATH": os.environ["PATH"], "NODE_PATH": str(APP / "node_modules"), "OPENROUTER_API_KEY": "k",
           "OPENROUTER_URL": f"http://127.0.0.1:{servers['model']}/v1/chat/completions",
           "PANIM_IMAGE_CACHE": str(tmp_path / "images"), "PANIM_SVG_REVIEWS": "0", **extra}
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120, env=env)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])["fig1"]


def test_a_book_photo_is_made_again_by_the_image_model_as_a_cutout(figures_js, servers, tmp_path):
    """No web search: the figure model says what the photograph shows, and the image model makes it again, cut out
    on transparent with no border."""
    from PIL import Image

    figure = tmp_path / "fig1.jpg"
    _book_photo(figure)
    drawn = _draw(figures_js, servers, tmp_path, figure)
    assert drawn["photo"] and drawn["looked"] and drawn["query"] == "Ganges river at Varanasi ghats"
    assert drawn["generated"]["file"].endswith(".svg")                       # traced into vector shapes
    made = Image.open(drawn["generated"]["file"][:-4] + ".png")
    assert made.mode == "RGBA" and made.getpixel((0, 0))[3] == 0          # the white around it is gone
    assert made.size[0] < 300 and made.size[1] < 200                        # trimmed to the subject
    kinds = [k for k, _ in _Model.CALLS]
    assert kinds == ["decide", "generate"]
    asked = _Model.CALLS[1][1]
    assert "Ganges river at Varanasi ghats" in asked and "CUTOUT" in asked and "no border" in asked
    # Kept beside the figure: a second lecture from the book asks nothing again.
    _Model.CALLS = []
    again = _draw(figures_js, servers, tmp_path, figure)
    assert again["generated"]["file"] == drawn["generated"]["file"] and _Model.CALLS == []


def test_without_an_image_model_the_book_photo_stays(figures_js, servers, tmp_path):
    figure = tmp_path / "fig1.jpg"
    _book_photo(figure)
    drawn = _draw(figures_js, servers, tmp_path, figure, PANIM_IMAGES="0")
    assert drawn["photo"] and drawn["looked"] and "generated" not in drawn
