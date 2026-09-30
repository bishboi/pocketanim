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
def google(monkeypatch, tmp_path):
    """A local stand-in for texttospeech.googleapis.com: records requests; `state["fail"]` makes it refuse."""
    state = {"requests": [], "headers": [], "token_requests": [], "fail": False, "status": 403,
             "message": "API not enabled"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path == "/token":
                state["token_requests"].append(self.rfile.read(int(self.headers["Content-Length"])).decode())
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"access_token": "access-from-refresh", "expires_in": 3599}).encode())
                return
            state["requests"].append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            state["headers"].append(dict(self.headers))
            if state["fail"]:
                self.send_response(state["status"])
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": state["message"]}}).encode())
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"audioContent": base64.b64encode(_wav()).decode()}).encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "test-key")
    # No OAuth credentials from this machine (a real gcloud login would be used first).
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path / "no-gcloud"))
    monkeypatch.setenv("GOOGLE_TTS_URL", f"http://127.0.0.1:{server.server_port}/v1/text:synthesize")
    state["token_url"] = f"http://127.0.0.1:{server.server_port}/token"
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
    # No other voice: without a key the lecture stops with the reason, rather than switching voice.
    monkeypatch.delenv("GOOGLE_TTS_API_KEY")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(pl.VoiceUnavailable, match="GOOGLE_TTS_API_KEY"):
        pl.voice_mode()
    monkeypatch.setenv("PANIM_VOICE", "silent")
    assert pl.voice_mode() == "silent"


def test_a_refused_line_stops_the_lecture(google, monkeypatch, tmp_path):
    import pocket_lecture as pl

    monkeypatch.setenv("PANIM_AUDIO_DIR", str(tmp_path))
    monkeypatch.setenv("PANIM_VOICE", "auto")
    google["fail"] = True
    with pytest.raises(pl.VoiceUnavailable, match="API not enabled"):
        pl.narrate("A line Google refuses.")


def test_a_line_is_spoken_a_language_run_at_a_time():
    assert chirp.runs("बल एक धक्का है।") == [("hi-IN", "बल एक धक्का है।")]
    assert chirp.runs("Force is a push.")[0][1] == "Force is a push."
    parts = chirp.runs("बल (Force) क्या है? F = ma यानी force बराबर mass गुणा acceleration।")
    assert [code for code, _ in parts] == ["hi-IN", "en-IN", "hi-IN", "en-IN", "hi-IN", "en-IN", "hi-IN", "en-IN"]
    assert parts[-1] == ("en-IN", "acceleration।")          # the danda is punctuation, not Hindi
    assert chirp.runs("3 kg की गेंद")[0] == ("hi-IN", "3 kg की गेंद")    # a unit stays in its sentence


def test_a_mixed_line_asks_google_in_each_language_with_one_speaker(google):
    audio = chirp.speak("न्यूटन ने force की परिभाषा दी।", "Charon", 0.9)
    assert audio[:4] == b"RIFF"
    voices = [body["voice"] for _, body in google["requests"]]
    assert voices == [{"languageCode": "hi-IN", "name": "hi-IN-Chirp3-HD-Charon"},
                      {"languageCode": "en-IN", "name": "en-IN-Chirp3-HD-Charon"},
                      {"languageCode": "hi-IN", "name": "hi-IN-Chirp3-HD-Charon"}]


def test_hindi_lines_say_units_in_hindi():
    import pocket_lecture as pl

    said = pl.speechify("गेंद 5 m/s से चलती है, यानी 20% तेज़।")
    assert "मीटर प्रति सेकंड" in said and "प्रतिशत" in said and "percent" not in said
    assert "percent" in pl.speechify("It is 20% faster.")


def test_a_gcloud_login_signs_before_a_key_without_extra_packages(google, monkeypatch, tmp_path):
    """Some projects refuse API keys for Text-to-Speech. A `gcloud auth application-default login` on this machine
    signs every request: its refresh token is exchanged for an access token (no google-auth needed), and its quota
    project is sent as Google requires."""
    folder = tmp_path / "gcloud"
    folder.mkdir()
    (folder / "application_default_credentials.json").write_text(json.dumps({
        "type": "authorized_user", "client_id": "cid", "client_secret": "secret", "refresh_token": "refresh",
        "quota_project_id": "parikshanai"}))
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(folder))
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_URL", google["token_url"])
    chirp._token.update(value=None, expires=0.0, quota=None)
    assert chirp.auth() == "oauth" and chirp.configured()
    chirp.synthesize("Hello.", "Charon")
    token_request = google["token_requests"][-1]
    assert "grant_type=refresh_token" in token_request and "refresh_token=refresh" in token_request
    path, _ = google["requests"][-1]
    headers = {k.lower(): v for k, v in google["headers"][-1].items()}
    assert "key=" not in path                                  # the key is set, but the login signs
    assert headers["authorization"] == "Bearer access-from-refresh"
    assert headers["x-goog-user-project"] == "parikshanai"
    chirp._token.update(value=None, expires=0.0, quota=None)


def test_a_refused_key_says_how_to_sign_in(google):
    google.update(fail=True, status=401, message="API keys are not supported by this API. Expected OAuth2 access token")
    with pytest.raises(RuntimeError, match="gcloud auth application-default login"):
        chirp.synthesize("Hello.")


def test_the_quota_project_comes_from_gcloud_when_the_login_has_none(google, monkeypatch, tmp_path):
    """A new `gcloud auth application-default login` forgets set-quota-project: gcloud's own project is used."""
    folder = tmp_path / "gcloud"
    (folder / "configurations").mkdir(parents=True)
    (folder / "application_default_credentials.json").write_text(json.dumps({
        "type": "authorized_user", "client_id": "cid", "client_secret": "secret", "refresh_token": "refresh"}))
    (folder / "active_config").write_text("work")
    (folder / "configurations" / "config_work").write_text("[core]\nproject = parikshanai\naccount = a@b.c\n")
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(folder))
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_URL", google["token_url"])
    for name in ("GOOGLE_CLOUD_QUOTA_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT", "CLOUDSDK_CORE_PROJECT"):
        monkeypatch.delenv(name, raising=False)
    chirp._token.update(value=None, expires=0.0, quota=None)
    chirp.synthesize("Hello.", "Charon")
    headers = {k.lower(): v for k, v in google["headers"][-1].items()}
    assert headers["x-goog-user-project"] == "parikshanai"
    monkeypatch.setenv("GOOGLE_CLOUD_QUOTA_PROJECT", "other")           # the setting wins
    assert chirp.quota_project() == "other"
    chirp._token.update(value=None, expires=0.0, quota=None)


def test_a_missing_quota_project_says_how_to_set_it(google, monkeypatch, tmp_path):
    folder = tmp_path / "gcloud"
    folder.mkdir()
    (folder / "application_default_credentials.json").write_text(json.dumps({
        "type": "authorized_user", "client_id": "cid", "client_secret": "secret", "refresh_token": "refresh"}))
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(folder))
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_URL", google["token_url"])
    for name in ("GOOGLE_CLOUD_QUOTA_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT", "CLOUDSDK_CORE_PROJECT"):
        monkeypatch.delenv(name, raising=False)
    chirp._token.update(value=None, expires=0.0, quota=None)
    google.update(fail=True, status=403, message="The texttospeech.googleapis.com API requires a quota project, "
                                                 "which is not set by default.")
    with pytest.raises(RuntimeError, match="set-quota-project YOUR_PROJECT_ID"):
        chirp.synthesize("Hello.")
    chirp._token.update(value=None, expires=0.0, quota=None)
