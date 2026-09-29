"""Google Chirp 3 HD narration: the request it sends, the voice it picks, and the fallback when Google refuses."""

from __future__ import annotations

import base64
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import chirp  # noqa: E402


def _wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 24000)
    return buf.getvalue()


@pytest.fixture
def google(monkeypatch):
    """A local stand-in for texttospeech.googleapis.com: records requests; `state["fail"]` makes it refuse."""
    state = {"requests": [], "fail": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            state["requests"].append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            if state["fail"]:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "API not enabled"}}).encode())
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"audioContent": base64.b64encode(_wav()).decode()}).encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_URL", f"http://127.0.0.1:{server.server_port}/v1/text:synthesize")
    yield state
    server.shutdown()


def test_chirp_request_names_the_voice_language_and_pace(google):
    audio = chirp.synthesize("Force is a push.", "Charon", "en", 0.9)
    assert audio[:4] == b"RIFF"
    path, body = google["requests"][0]
    assert path.endswith("?key=test-key")
    assert body["voice"] == {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Charon"}
    assert body["audioConfig"]["speakingRate"] == 0.9
    chirp.synthesize("बल", "Charon", "hi")
    assert google["requests"][1][1]["voice"]["name"] == "hi-IN-Chirp3-HD-Charon"


def test_a_refusal_is_an_error_with_google_s_message(google):
    google["fail"] = True
    with pytest.raises(RuntimeError, match="API not enabled"):
        chirp.synthesize("Hello.")


def test_the_engine_speaks_with_chirp_when_a_key_is_set(google, monkeypatch, tmp_path):
    import pocket_lecture as pl

    monkeypatch.setenv("PANIM_AUDIO_DIR", str(tmp_path))
    monkeypatch.setenv("PANIM_VOICE", "auto")
    assert pl.voice_mode().startswith("chirp:")
    wav, seconds = pl.narrate("Friction slows a rolling ball.")
    assert wav and seconds > 0.5
    monkeypatch.delenv("GOOGLE_TTS_API_KEY")
    assert not pl.voice_mode().startswith("chirp:")
