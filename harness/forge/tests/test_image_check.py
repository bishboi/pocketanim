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


def test_an_image_only_model_is_asked_on_the_image_api(gen, monkeypatch):
    """OpenRouter refuses an image-only model on chat completions ("use the /api/v1/images endpoint"): it is asked
    on the Image API instead, and the picture comes back from data[0].b64_json."""
    import base64

    png = gen._stand_in("an apple")
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            calls.append((self.path, body))
            if self.path.endswith("/chat/completions"):
                status, reply = 404, {"error": {"message": "meta/muse-image is an image generation model and cannot be "
                                                           "used with the chat/completions endpoint. Use the "
                                                           "/api/v1/images endpoint instead."}}
            else:
                status, reply = 200, {"data": [{"b64_json": base64.b64encode(png).decode()}], "usage": {"cost": 0.04}}
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/api/v1/chat/completions")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "meta/muse-image")
    got = gen.check()
    row = gen.generate("a steam locomotive")
    server.shutdown()
    assert got["ok"] and got["usd"] == 0.04, got.get("error")
    assert row and row["usd"] == 0.04
    paths = [p for p, _ in calls]
    assert paths[0] == "/api/v1/chat/completions" and paths[1] == "/api/v1/images"
    assert paths[2] == "/api/v1/images"                      # remembered: asked on the Image API from then on
    assert calls[1][1] == {"model": "meta/muse-image", "prompt": calls[1][1]["prompt"]}


def _refusing_server(refused: str, png: bytes):
    """Chat completions that refuse `refused` (not in this region) and answer any other model with a picture."""
    import base64

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            calls.append(body["model"])
            if body["model"] == refused:
                status, reply = 403, {"error": {"message": "This model is not available in your region."}}
            else:
                url = "data:image/png;base64," + base64.b64encode(png).decode()
                status, reply = 200, {"choices": [{"message": {"images": [{"image_url": {"url": url}}]}}],
                                      "usage": {"cost": 0.02}}
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, calls


def test_a_model_not_available_here_is_reported_and_never_swapped(gen, monkeypatch):
    """No fallback: a model that refuses is reported for every picture, asked once, and no other model is used."""
    server, calls = _refusing_server("meta/muse-image", gen._stand_in("x"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/api/v1/chat/completions")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "meta/muse-image")
    rows = [gen.generate(w) for w in ("a knight", "a manor")]
    got = gen.check()
    server.shutdown()
    assert rows == [None, None] and set(calls) == {"meta/muse-image"}
    report = gen.report()
    assert report["model"] == "meta/muse-image" and "fallback" not in report
    assert all("not available in your region" in f["error"] for f in report["failed"])
    assert not got["ok"] and got["model"] == "meta/muse-image" and "not available in your region" in got["error"]


def test_a_refusing_model_is_asked_once_a_compile(gen, monkeypatch):
    server, calls = _refusing_server("meta/muse-image", gen._stand_in("x"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_URL", f"http://127.0.0.1:{server.server_port}/api/v1/chat/completions")
    monkeypatch.setenv("PANIM_IMAGE_MODEL", "meta/muse-image")
    assert gen.generate("a knight") is None and gen.generate("a manor") is None
    server.shutdown()
    assert calls == ["meta/muse-image"]
    assert len(gen.report()["failed"]) == 2
