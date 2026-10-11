"""The image model's check (genimage.py --check, the app's "test" button on the Pictures row) and what a compile
reports of it: a model that fails says why, so a lecture with only SVG drawings is told apart from a broken model."""

from __future__ import annotations

import importlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path


def _server(status: int, body: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def gen(monkeypatch, tmp_path):
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path))
    monkeypatch.delenv("PANIM_IMAGE_FAKE", raising=False)
    monkeypatch.delenv("PANIM_IMAGES", raising=False)
    import genimage

    return importlib.reload(genimage)


def test_the_check_makes_a_picture_and_traces_it(gen, monkeypatch):
    monkeypatch.setenv("PANIM_IMAGE_FAKE", "1")
    got = gen.check()
    assert got["ok"] and got["png"].startswith("data:image/png;base64,")
    assert got["svg"] is None or got["paths"] > 0


def test_the_check_says_the_key_is_missing(gen, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    got = gen.check()
    assert not got["ok"] and "OPENROUTER_API_KEY" in got["error"]


def test_a_model_that_is_not_an_image_model_is_named(gen, monkeypatch):
    server = _server(200, {"choices": [{"message": {"content": "I cannot draw."}}]})
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "some/text-model")
    got = gen.check()
    server.shutdown()
    assert not got["ok"] and "some/text-model returned no image" in got["error"] and "I cannot draw" in got["error"]


def test_an_http_error_is_reported_and_a_lecture_records_it(gen, monkeypatch):
    server = _server(404, {"error": {"message": "No endpoints found for bad/model"}})
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "bad/model")
    got = gen.check()
    assert "HTTP 404" in got["error"] and "No endpoints found" in got["error"]
    assert gen.generate("a steam locomotive") is None
    server.shutdown()
    report = gen.report()
    assert report["asked"] == 1 and report["made"] == 0 and report["model"] == "bad/model"
    assert "HTTP 404" in report["failed"][0]["error"] and report["failed"][0]["what"] == "a steam locomotive"


def test_a_lecture_without_a_key_says_so(gen, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert gen.generate("a steam locomotive") is None
    assert "OPENROUTER_API_KEY" in gen.report()["failed"][0]["error"]
