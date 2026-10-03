"""Illustrations for diagrams: drawn for the lecture (illustrator.py), or Bioicons science drawings."""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import bioicons  # noqa: E402
import illustrator  # noqa: E402

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="#7CC36E" stroke="#111"/></svg>'


@pytest.fixture
def recraft(monkeypatch, tmp_path):
    asked = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            asked.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            url = "data:image/svg+xml;base64," + base64.b64encode(SVG.encode()).decode()
            body = {"choices": [{"message": {"content": None, "images": [{"image_url": {"url": url}}]}}],
                    "usage": {"cost": 0.08}}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/api/v1/chat/completions")
    monkeypatch.delenv("PANIM_DRAWINGS", raising=False)
    monkeypatch.setattr(illustrator, "FOLDER", tmp_path / "drawings")
    yield asked
    server.shutdown()


def test_a_drawing_is_made_once_in_the_board_style_and_kept(recraft):
    path = illustrator.draw("a cow grazing")
    assert path.read_text().startswith("<svg") and illustrator.cost_of("a cow grazing") == 0.08
    (request,) = recraft
    assert request["model"] == "recraft/recraft-v4.1-vector" and request["modalities"] == ["image"]
    assert "thick dark outlines" in request["messages"][0]["content"] and request["messages"][0]["content"].endswith("a cow grazing")
    illustrator.draw("a cow grazing")
    assert len(recraft) == 1                                     # kept: not asked for, nor paid for, again


def test_a_word_is_drawn_and_a_library_id_is_not(recraft, monkeypatch):
    import pocket_lecture as pl

    assert pl.drawing_subject("cow") == "cow"
    assert pl.drawing_subject("draw:a deer at a river") == "a deer at a river"
    assert pl.drawing_subject("bioicons:cc-0/x/y/neuron") is None
    monkeypatch.setenv("PANIM_DRAWINGS", "library")
    assert pl.drawing_subject("cow") is None                     # drawings off: the library's


def test_prespeak_finds_the_drawings_a_scene_names():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("prespeak", Path(__file__).resolve().parents[2] / "scripts" / "prespeak.py")
    prespeak = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prespeak)
    source = '''
class S(MapLecture):
    def construct(self):
        self.beat("x", self.diagram("d", "flow", [{"id": "a", "label": "A", "entity": "cow"}, {"id": "b", "label": "B"}]))
        self.beat("y", self.define("Neuron", "a nerve cell", "bioicons:cc-0/c/a/neuron"))
        self.beat("z", self.icon("wheat", "Punjab"))
'''
    assert prespeak.drawing_names(source) == ["cow", "bioicons:cc-0/c/a/neuron", "wheat"]


def test_bioicons_search_by_name_and_category(monkeypatch, tmp_path):
    folder = tmp_path / "bioicons"
    (folder / "cc-by-4.0" / "Neuroscience" / "Ann_Lee").mkdir(parents=True)
    (folder / "cc-by-4.0" / "Neuroscience" / "Ann_Lee" / "pyramidal_neuron.svg").write_text(SVG)
    (folder / "mit" / "Lab_apparatus" / "Bo").mkdir(parents=True)
    (folder / "mit" / "Lab_apparatus" / "Bo" / "burette.svg").write_text(SVG)
    monkeypatch.setattr(bioicons, "FOLDER", folder)
    bioicons._index.cache_clear()
    (hit,) = bioicons.search("neurons")
    assert hit["id"] == "bioicons:cc-by-4.0/Neuroscience/Ann_Lee/pyramidal_neuron" and hit["licence"] == "CC BY 4.0"
    assert bioicons.file(hit["id"]).is_file()
    assert "Ann Lee (CC BY 4.0)" in bioicons.credit([hit["id"]])
    bioicons._index.cache_clear()
