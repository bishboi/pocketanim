"""Google Cloud Text-to-Speech, Chirp 3 HD voices: the narration voice when a Google key is set.

Chirp 3 HD is Google's most natural voice family (en-US-Chirp3-HD-Charon, hi-IN-Chirp3-HD-Kore...). Each
line is one request to the REST API; the lecture engine caches the result like any other voice
(pocket_lecture.narrate), so a line is paid for once.

Credentials, the first found (OAuth first: some projects refuse API keys for this API, "API keys are not
supported by this API"):
  your Google login    `gcloud auth application-default login`, then `gcloud auth application-default
                       set-quota-project <PROJECT_ID>` (the project with the Text-to-Speech API enabled);
  a service account    GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json;
  an API key           GOOGLE_TTS_API_KEY (or GOOGLE_API_KEY), where the project allows keys.
OAuth needs `pip install google-auth requests` (in harness/requirements.txt).
Settings:
  PANIM_CHIRP_VOICE    a voice name for every style (Charon, Kore, Aoede...); each style has its own otherwise
  PANIM_CHIRP_LANG     the language English lines are spoken in: en-US (default), en-IN, en-GB...
  GOOGLE_TTS_URL       the endpoint (a test points it at a mock)

    .venv/bin/python harness/lecture/chirp.py "Hello there." out.wav        # try it
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
# The Chirp 3 HD voice each lecture style speaks in; the same names exist in every language.
STYLE_VOICES = {"atlas": "Kore", "vox": "Aoede", "cardboard": "Puck", "whiteboard": "Charon", "blueprint": "Orus",
                "chalkboard": "Charon", "parchment": "Iapetus", "lab": "Leda", "cosmos": "Fenrir"}
DEFAULT_VOICE = "Charon"
LANGS = {"en": None, "hi": "hi-IN"}     # None: PANIM_CHIRP_LANG
# English inside a Hindi line is said with an Indian accent, by the same speaker: a teacher switching language.
MIXED_ENGLISH = "en-IN"
SAMPLE_RATE = 24000
# Bumped when the way lines are spoken changes, so cached lines are spoken again (pocket_lecture.audio_file).
REVISION = 2


def _key() -> str | None:
    return os.environ.get("GOOGLE_TTS_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


def _adc_file() -> str | None:
    """The OAuth credentials file google-auth would use: GOOGLE_APPLICATION_CREDENTIALS, else the one
    `gcloud auth application-default login` writes."""
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if path:
        return path if os.path.isfile(path) else None
    if os.environ.get("CLOUDSDK_CONFIG"):
        folder = os.environ["CLOUDSDK_CONFIG"]
    elif os.name == "nt":
        folder = os.path.join(os.environ.get("APPDATA", ""), "gcloud")
    else:
        folder = os.path.join(os.path.expanduser("~"), ".config", "gcloud")
    default = os.path.join(folder, "application_default_credentials.json")
    return default if os.path.isfile(default) else None


def _oauth() -> bool:
    """OAuth credentials are on this machine: then they sign every request, whatever key is also set."""
    return _adc_file() is not None


def configured() -> bool:
    """Chirp can be called here: OAuth credentials (a login or a service account), or an API key."""
    return _oauth() or bool(_key())


def auth() -> str:
    """How requests are signed: "oauth" when credentials are on this machine, else "key"."""
    return "oauth" if _oauth() else "key"


TOKEN_URL = "https://oauth2.googleapis.com/token"
_token_lock = threading.Lock()
_token: dict = {"value": None, "expires": 0.0, "quota": None}


def _read_adc() -> dict:
    with open(_adc_file(), encoding="utf-8") as handle:
        return json.load(handle)


def _new_token() -> tuple[str, float, str | None]:
    """(access token, seconds it lasts, quota project) from the credentials on this machine.

    A gcloud login (authorized_user) is its refresh token exchanged at Google's token endpoint: no library
    needed. A service account or other credentials go through google-auth, else the gcloud command.
    """
    info = _read_adc()
    quota = os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT") or info.get("quota_project_id")
    if info.get("type") == "authorized_user":
        form = urllib.parse.urlencode({"client_id": info["client_id"], "client_secret": info["client_secret"],
                                       "refresh_token": info["refresh_token"], "grant_type": "refresh_token"})
        request = urllib.request.Request(os.environ.get("GOOGLE_OAUTH_TOKEN_URL") or TOKEN_URL, data=form.encode(),
                                         headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                reply = json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Google sign-in {error.code}: {detail}. Run `gcloud auth application-default "
                               "login` again.") from None
        return reply["access_token"], float(reply.get("expires_in", 3600)), quota
    import importlib.util

    if importlib.util.find_spec("google.auth") and importlib.util.find_spec("requests"):
        import google.auth
        import google.auth.transport.requests

        creds, _project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token, 3000.0, quota or getattr(creds, "quota_project_id", None)
    gcloud = shutil.which("gcloud")
    if gcloud:
        token = subprocess.run([gcloud, "auth", "application-default", "print-access-token"], capture_output=True,
                               text=True, timeout=60)
        if token.returncode == 0 and token.stdout.strip():
            return token.stdout.strip(), 3000.0, quota
    raise RuntimeError(f"The credentials in {_adc_file()} ({info.get('type')}) need google-auth: "
                       ".venv/bin/pip install -r harness/requirements.txt")


def _oauth_headers(refresh: bool = False) -> dict:
    """Authorization, and the project Google bills the calls to (a login's quota project; it refuses without)."""
    with _token_lock:
        if refresh or not _token["value"] or time.time() > _token["expires"] - 120:
            value, lasts, quota = _new_token()
            _token.update(value=value, expires=time.time() + lasts, quota=quota)
        headers = {"Authorization": f"Bearer {_token['value']}"}
        if _token["quota"]:
            headers["x-goog-user-project"] = _token["quota"]
        return headers


KEY_REFUSED = ("Google refused the API key: this project's Text-to-Speech accepts OAuth credentials, not keys. "
               "Sign in instead (the key can stay; a login is used first): install the Google Cloud CLI, run "
               "`gcloud auth application-default login`, then `gcloud auth application-default set-quota-project "
               "<PROJECT_ID>` (the project with the Cloud Text-to-Speech API enabled), and restart the app. Or use "
               "a service account: GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json. harness/SETUP.md has the steps.")


def voice_for(style: str | None) -> str:
    """The Chirp 3 HD voice name (Charon) for a lecture style."""
    return os.environ.get("PANIM_CHIRP_VOICE") or STYLE_VOICES.get(style or "", DEFAULT_VOICE)


def language(lang: str) -> str:
    """The BCP-47 code a line in `lang` ('en', 'hi', or already a code such as 'en-IN') is spoken in."""
    if "-" in lang:
        return lang
    return LANGS.get(lang) or os.environ.get("PANIM_CHIRP_LANG") or "en-US"


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")
_HINDI_LETTER = re.compile(r"[\u0900-\u0963\u0971-\u097F]")


def runs(text: str) -> list[tuple[str, str]]:
    """A line as [(language code, text)] runs, each spoken in its own language.

    Words in Devanagari are Hindi (hi-IN). In a line with Hindi in it, a Latin word of three letters or more is
    English (en-IN): "बल (force) एक धक्का है" is three runs. Shorter Latin tokens (F, m, kg) and numbers and
    punctuation go with the run they are in, so a symbol does not break a sentence into bits. A line with no
    Devanagari is one run in the English accent (PANIM_CHIRP_LANG).
    """
    if not _DEVANAGARI.search(text):
        return [(language("en"), text)]
    out: list[list] = []
    for token in re.findall(r"\S+\s*|\s+", text):
        # By letters: the danda (।) and Devanagari digits are punctuation and numbers, not Hindi words.
        hindi = len(_HINDI_LETTER.findall(token))
        latin = len(_LATIN.findall(token))
        if hindi and hindi >= latin:
            kind = "hi-IN"
        elif latin >= 3:
            kind = MIXED_ENGLISH
        else:
            kind = None                                     # goes with its neighbours
        if kind is None or (out and out[-1][0] == kind):
            if out:
                out[-1][1] += token
            else:
                out.append([None, token])
        else:
            if out and out[-1][0] is None:
                out[-1][0] = kind                           # a leading symbol or number joins the first run
                out[-1][1] += token
            else:
                out.append([kind, token])
    return [(code or "hi-IN", chunk.strip()) for code, chunk in out if chunk.strip()]


def _pcm(audio: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(audio)) as handle:
        return handle.readframes(handle.getnframes()), handle.getframerate()


def _trim(pcm: bytes, rate: int, keep: float = 0.04) -> bytes:
    """Without the silence Google leaves at each end of a clip (keeping `keep` seconds), so runs join closely."""
    import numpy as np

    samples = np.frombuffer(pcm, dtype=np.int16)
    loud = np.nonzero(np.abs(samples.astype(np.int32)) > 400)[0]
    if not len(loud):
        return pcm
    pad = int(rate * keep)
    return samples[max(0, loud[0] - pad):min(len(samples), loud[-1] + pad)].tobytes()


def speak(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> bytes:
    """A WAV of one line, each language run spoken with its own language code by the same voice, joined."""
    parts = runs(text)
    if len(parts) == 1:
        return synthesize(parts[0][1], voice, parts[0][0], speed)
    pcm, rate = b"", SAMPLE_RATE
    for index, (code, chunk) in enumerate(parts):
        clip, rate = _pcm(synthesize(chunk, voice, code, speed))
        clip = _trim(clip, rate)
        gap = b"\x00\x00" * int(rate * 0.06) if index else b""
        pcm += gap + clip
    out = io.BytesIO()
    with wave.open(out, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return out.getvalue()


def synthesize(text: str, voice: str = DEFAULT_VOICE, lang: str = "en", speed: float = 1.0) -> bytes:
    """A WAV (16-bit, 24 kHz, mono) of one line. Raises RuntimeError with Google's message when it fails."""
    code = language(lang)
    base = voice.split("-Chirp3-HD-")[-1]                   # the speaker, in this run's language
    name = f"{code}-Chirp3-HD-{base}"
    body = {"input": {"text": text}, "voice": {"languageCode": code, "name": name},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SAMPLE_RATE}}
    if abs(speed - 1.0) > 1e-3:
        body["audioConfig"]["speakingRate"] = round(speed, 2)
    url = os.environ.get("GOOGLE_TTS_URL") or URL
    last = ""
    signed = auth()
    refreshed = False
    for attempt in range(4):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        target = url
        if signed == "oauth":
            headers.update(_oauth_headers(refresh=refreshed))
        else:
            target = f"{url}?key={_key()}"
        request = urllib.request.Request(target, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                audio = json.loads(response.read())["audioContent"]
            return base64.b64decode(audio)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            try:
                last = json.loads(detail)["error"]["message"]
            except Exception:  # noqa: BLE001
                last = detail[:300]
            if error.code == 400 and "speakingRate" in body["audioConfig"] and "rate" in last.lower():
                del body["audioConfig"]["speakingRate"]      # a voice without pace control: its own pace
                continue
            if error.code in (429, 500, 503) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            if error.code == 401 and signed == "oauth" and not refreshed:
                refreshed = True                             # a token that ran out: a fresh one, once
                continue
            if signed == "key" and error.code in (401, 403) and "api key" in last.lower():
                where = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.path.join(
                    os.environ.get("CLOUDSDK_CONFIG") or os.path.join(os.path.expanduser("~"), ".config", "gcloud"),
                    "application_default_credentials.json")
                raise RuntimeError(f"Google TTS {error.code}: {last} -- {KEY_REFUSED} (No login was found at "
                                   f"{where} for the user this app runs as.)") from None
            raise RuntimeError(f"Google TTS {error.code}: {last}") from None
        except urllib.error.URLError as error:
            last = str(error.reason)
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Google TTS unreachable: {last}") from None
    raise RuntimeError(f"Google TTS failed: {last}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    if not configured():
        print("no Google credentials: `gcloud auth application-default login`, GOOGLE_APPLICATION_CREDENTIALS or "
              "GOOGLE_TTS_API_KEY (see harness/SETUP.md)", file=sys.stderr)
        return 1
    audio = speak(sys.argv[1], voice_for(os.environ.get("LECTURE_STYLE")))
    with open(sys.argv[2], "wb") as handle:
        handle.write(audio)
    print(f"wrote {sys.argv[2]} ({len(audio)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
