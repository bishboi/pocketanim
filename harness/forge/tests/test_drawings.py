"""Illustrations for diagrams: open libraries (drawlib.py: CocoMaterial, Arcadia's Drawing Open) and Bioicons."""

from __future__ import annotations

import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import bioicons  # noqa: E402
import drawlib  # noqa: E402

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="#7CC36E" stroke="#111"/></svg>'


@pytest.fixture
def libraries(monkeypatch, tmp_path):
    """Stand-ins for CocoMaterial's API (two pages) and the Drawing Open record on Zenodo."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("library/Zebrafish/zebrafish_silhouette.svg", SVG.replace("#7CC36E", "#000"))
        z.writestr("library/Zebrafish/zebrafish_tricolor.svg", SVG)
        z.writestr("library/Tardigrade/tardigrade_tricolor.svg", SVG)
    pages = {
        1: {"next": "page2", "results": [
            {"id": 7, "name": "cow", "tags": "animal,farm,cattle", "svg_content": "<svg/>", "colored_svg_content": SVG},
            {"id": 8, "name": "solar panel", "tags": "energy,sun", "svg_content": SVG, "colored_svg_content": None}]},
        2: {"next": None, "results": [{"id": 9, "name": "barn", "tags": "farm,building", "svg_content": SVG}]},
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.startswith("/coco"):
                body = json.dumps(pages[int(self.path.rsplit("=", 1)[1])]).encode()
            elif self.path == "/record":
                body = json.dumps({"files": [{"key": "arcadia-organism-library-v1.0.zip",
                                              "links": {"self": f"http://127.0.0.1:{port}/zip"}}]}).encode()
            else:
                body = archive.getvalue()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(drawlib, "COCO_API", f"http://127.0.0.1:{port}/coco?page_size=100&page={{page}}")
    monkeypatch.setattr(drawlib, "ARCADIA_RECORD", f"http://127.0.0.1:{port}/record")
    monkeypatch.setattr(drawlib, "FOLDER", tmp_path / "drawlib")
    drawlib._index.cache_clear()
    yield drawlib
    drawlib._index.cache_clear()
    server.shutdown()


def test_the_libraries_download_with_names_and_tags(libraries):
    assert libraries.fetch() == {"coco": 3, "arcadia": 2}
    assert (libraries.FOLDER / "coco" / "7-cow.svg").read_text() == SVG          # the coloured version
    assert libraries.search("cows")[0]["id"] == "coco:7-cow"
    assert libraries.search("cattle")[0]["id"] == "coco:7-cow"                 # by a tag
    assert libraries.best("solar panels") == "coco:8-solar-panel"
    assert libraries.best("solar eclipse") is None                             # half a match is not the thing
    assert libraries.file("arcadia:zebrafish").read_text() == SVG              # the tricolour drawing, not the silhouette
    assert libraries.credit(["coco:7-cow", "arcadia:zebrafish", "bioicons:x"]) == (
        "Illustrations: CocoMaterial (CC0), Drawing Open, Arcadia Science (CC0)")


def test_a_word_is_drawn_from_the_library_before_the_emoji(libraries):
    import pocket_lecture as pl

    libraries.fetch()
    assert pl.drawing_source("cow")[1] == "coco:7-cow"
    assert pl.drawing_source("draw:barn")[1] == "coco:9-barn"                  # an old "draw:" name still works
    assert pl.drawing_source("arcadia:tardigrade")[1] == "arcadia:tardigrade"
    assert "coco:7-cow" in pl.USED_DRAWINGS
    path, found = pl.drawing_source("tree")                                    # no library drawing: the emoji set's
    assert not found.startswith(("coco:", "arcadia:")) and path.is_file()


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
