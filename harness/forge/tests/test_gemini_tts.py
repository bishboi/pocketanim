"""Gemini 3.8 Flash-Lite TTS, the narration voice, against a stand-in for the Gemini API."""

from __future__ import annotations

import base64
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import gemini_tts  # noqa: E402


def _pcm(seconds: float = 0.3) -> bytes:
    return b"\x10\x27\xf0\xd8" * int(24000 * seconds / 2)


@pytest.fixture
def gemini(monkeypatch):
    state = {"requests": [], "fail": [], "wav": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
            if state["fail"]:
                code, message = state["fail"].pop(0)
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"code": code, "message": message}}).encode())
                return
            audio, mime = _pcm(), "audio/L16;codec=pcm;rate=24000"
            if state["wav"]:
                out = io.BytesIO()
                with wave.open(out, "w") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(24000)
                    handle.writeframes(audio)
                audio, mime = out.getvalue(), "audio/wav"
            reply = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime,
                                                                           "data": base64.b64encode(audio).decode()}}]},
                                     "finishReason": "STOP"}]}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(reply).encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setenv("GEMINI_TTS_URL", f"http://127.0.0.1:{server.server_port}/v1beta/models")
    monkeypatch.delenv("PANIM_TTS", raising=False)
    monkeypatch.setattr(gemini_tts.time, "sleep", lambda s: None)
    yield state
    server.shutdown()


def test_a_hinglish_line_is_one_request_with_the_voice_and_model(gemini):
    audio = gemini_tts.speak("अच्छा बच्चों, अब normal reaction समझते हैं।", "Kore")
    assert audio[:4] == b"RIFF"
    (request,) = gemini["requests"]
    assert request["path"] == "/v1beta/models/gemini-3.8-flash-lite-tts:generateContent"
    assert request["key"] == "gem-key"
    config = request["body"]["generationConfig"]
    assert config["responseModalities"] == ["AUDIO"]
    assert config["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert request["body"]["contents"][0]["parts"][0]["text"] == "अच्छा बच्चों, अब normal reaction समझते हैं।"


def test_a_wav_reply_is_read_too(gemini):
    gemini["wav"] = True
    with wave.open(io.BytesIO(gemini_tts.speak("Hello there.", "Charon"))) as handle:
        assert handle.getframerate() == 24000 and handle.getnframes() > 0


def test_rate_limits_are_waited_out_and_a_refused_key_says_what_to_set(gemini):
    gemini["fail"] = [(429, "Resource exhausted"), (503, "overloaded")]
    assert gemini_tts.speak("One line.", "Charon")[:4] == b"RIFF"
    assert len(gemini["requests"]) == 3
    gemini["fail"] = [(403, "API key not valid")]
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gemini_tts.speak("Another line.", "Charon")


def test_no_instruction_is_sent_by_default(gemini):
    gemini_tts.speak("Line.", "Charon")
    assert "systemInstruction" not in gemini["requests"][0]["body"]


def test_a_model_that_refuses_an_instruction_reads_without_it_from_then_on(gemini, monkeypatch):
    monkeypatch.setenv("PANIM_TTS_STYLE", "teacher")
    monkeypatch.setattr(gemini_tts, "_REFUSES_INSTRUCTION", False)
    gemini["fail"] = [(400, "Developer instruction is not enabled for this model")]
    gemini_tts.speak("नमस्ते बच्चों!", "Charon")
    gemini_tts.speak("Second line.", "Charon")
    bodies = [r["body"] for r in gemini["requests"]]
    assert "systemInstruction" in bodies[0]
    assert all("systemInstruction" not in b for b in bodies[1:]) and len(bodies) == 3


def test_the_engine_narrates_with_gemini_by_default(gemini, monkeypatch, tmp_path):
    import pocket_lecture as pl

    monkeypatch.setenv("PANIM_AUDIO_DIR", str(tmp_path))
    monkeypatch.setenv("PANIM_VOICE", "auto")
    assert pl.voice_mode().startswith("gemini:")
    wav, seconds = pl.narrate("नमस्ते बच्चों।")
    assert wav and seconds > 0
    monkeypatch.setenv("PANIM_TTS", "chirp")
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path / "none"))
    monkeypatch.delenv("GOOGLE_TTS_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(pl.VoiceUnavailable, match="Chirp"):
        pl.voice_mode()


def test_no_key_says_where_to_put_it(monkeypatch):
    import pocket_lecture as pl

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("PANIM_TTS", raising=False)
    monkeypatch.setenv("PANIM_VOICE", "auto")
    with pytest.raises(pl.VoiceUnavailable, match="GEMINI_API_KEY"):
        pl.voice_mode()


def test_every_style_is_spoken_by_achird(monkeypatch):
    monkeypatch.delenv("PANIM_TTS_VOICE", raising=False)
    assert {gemini_tts.voice_for(s) for s in ("atlas", "vox", "chalkboard", None)} == {"Achird"}
    monkeypatch.setenv("PANIM_TTS_VOICE", "Kore")
    assert gemini_tts.voice_for("vox") == "Kore"


def test_the_engine_asks_for_achird(gemini, monkeypatch, tmp_path):
    import pocket_lecture as pl

    monkeypatch.delenv("PANIM_TTS_VOICE", raising=False)
    monkeypatch.setenv("PANIM_AUDIO_DIR", str(tmp_path))
    monkeypatch.setenv("PANIM_VOICE", "auto")
    assert pl.voice_mode() == "gemini:Achird"
    pl.narrate("अब आगे बढ़ते हैं।")
    voice = gemini["requests"][-1]["body"]["generationConfig"]["speechConfig"]["voiceConfig"]
    assert voice["prebuiltVoiceConfig"]["voiceName"] == "Achird"


def test_prespeak_finds_every_line_the_scene_will_say():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "prespeak.py"
    spec = importlib.util.spec_from_file_location("prespeak", path)
    prespeak = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prespeak)
    source = '''
class S(MapLecture):
    def construct(self):
        self.title_slide("Laws of Motion", "Newton's laws", narration="आज हम Newton के laws समझेंगे।")
        self.chapter(1, "Force", "push", "Chapter one. Force.")
        self.beat("A block on a table.", self.sketch("s", []))
        self.beat(text="The same line.")
        self.recap([("Force", "A push or a pull"), ("Mass", "How much matter")])
'''
    assert prespeak.beat_lines(source) == ["आज हम Newton के laws समझेंगे।", "Chapter one. Force.",
                                           "A block on a table.", "The same line.", "Force. A push or a pull.",
                                           "Mass. How much matter."]


def test_a_line_costs_what_google_counted_or_an_estimate(gemini, monkeypatch):
    monkeypatch.setattr(gemini_tts.time, "time", lambda: 1790000000)          # before the 2027 price change
    monkeypatch.delenv("PANIM_TTS_PRICE", raising=False)
    gemini_tts.speak("Hello there.", "Achird")
    spent = gemini_tts.last_cost()
    # No usageMetadata in the stand-in's reply: text at 4 characters a token, audio at 25 tokens a second.
    assert spent["in"] == 3 and spent["out"] == round(0.3 * 25)
    assert abs(spent["usd"] - (3 * 0.50 + spent["out"] * 6.00) / 1e6) < 1e-12
    assert gemini_tts.price("gemini-3.8-flash-tts") == (0.50, 9.00)
    monkeypatch.setattr(gemini_tts.time, "time", lambda: 1800000000)          # 2027: both rates double
    assert gemini_tts.price("gemini-3.8-flash-lite-tts") == (1.00, 12.00)
    monkeypatch.setenv("PANIM_TTS_PRICE", "0.25,3")
    assert gemini_tts.price() == (0.25, 3.0)


def test_a_spoken_line_keeps_its_cost_beside_it(gemini, monkeypatch, tmp_path):
    import pocket_lecture as pl

    monkeypatch.setenv("PANIM_AUDIO_DIR", str(tmp_path))
    monkeypatch.setenv("PANIM_VOICE", "auto")
    pl.narrate("बल एक धक्का है।")
    mode = pl.voice_mode()
    cost = pl.line_cost(mode, pl.speechify("बल एक धक्का है।"))
    assert cost is not None and cost > 0
    assert pl.line_cost(mode, "never spoken") is None


def test_every_line_is_spoken_with_an_indian_language_code(gemini, monkeypatch):
    monkeypatch.delenv("PANIM_TTS_LANGUAGE", raising=False)
    monkeypatch.setattr(gemini_tts, "_REFUSED_LANGUAGES", set())
    gemini_tts.speak("अच्छा बच्चों, अब normal reaction समझते हैं।", "Achird")
    gemini_tts.speak("Option B, newton, is the SI unit of force.", "Achird")
    codes = [r["body"]["generationConfig"]["speechConfig"].get("languageCode") for r in gemini["requests"]]
    assert codes == ["hi-IN", "en-IN"]          # Hindi and Hinglish as hi-IN; an all-English line in Indian English
    monkeypatch.setenv("PANIM_TTS_LANGUAGE", "hi-IN")
    gemini_tts.speak("Newton.", "Achird")
    monkeypatch.setenv("PANIM_TTS_LANGUAGE", "none")
    gemini_tts.speak("Newton.", "Achird")
    codes = [r["body"]["generationConfig"]["speechConfig"].get("languageCode") for r in gemini["requests"][2:]]
    assert codes == ["hi-IN", None]


def test_a_language_code_the_model_refuses_is_dropped_not_fatal(gemini, monkeypatch):
    monkeypatch.delenv("PANIM_TTS_LANGUAGE", raising=False)
    monkeypatch.setattr(gemini_tts, "_REFUSED_LANGUAGES", set())
    gemini["fail"] = [(400, "Unsupported language code: en-IN")]
    assert gemini_tts.speak("Newton.", "Achird")[:4] == b"RIFF"
    gemini_tts.speak("Watt.", "Achird")
    codes = [r["body"]["generationConfig"]["speechConfig"].get("languageCode") for r in gemini["requests"]]
    assert codes == ["en-IN", None, None]       # refused once: not sent again this run
    gemini_tts.speak("नमस्ते।", "Achird")
    assert gemini["requests"][-1]["body"]["generationConfig"]["speechConfig"]["languageCode"] == "hi-IN"
