"""Google Cloud Text-to-Speech, Chirp 3 HD voices: the narration voice when a Google key is set.

Chirp 3 HD is Google's most natural voice family (en-US-Chirp3-HD-Charon, hi-IN-Chirp3-HD-Kore...). Each
line is one request to the REST API; the lecture engine caches the result like any other voice
(pocket_lecture.narrate), so a line is paid for once.

Credentials, either:
  GOOGLE_TTS_API_KEY   an API key with the Cloud Text-to-Speech API enabled (GOOGLE_API_KEY works too), or
  GOOGLE_APPLICATION_CREDENTIALS   a service-account JSON file (needs `pip install google-auth`).
Settings:
  PANIM_CHIRP_VOICE    a voice name for every style (Charon, Kore, Aoede...); each style has its own otherwise
  PANIM_CHIRP_LANG     the language English lines are spoken in: en-US (default), en-IN, en-GB...
  GOOGLE_TTS_URL       the endpoint (a test points it at a mock)

    .venv/bin/python harness/lecture/chirp.py "Hello there." out.wav        # try it
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from functools import lru_cache

URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
# The Chirp 3 HD voice each lecture style speaks in; the same names exist in every language.
STYLE_VOICES = {"atlas": "Kore", "vox": "Aoede", "cardboard": "Puck", "whiteboard": "Charon", "blueprint": "Orus",
                "chalkboard": "Charon", "parchment": "Iapetus", "lab": "Leda", "cosmos": "Fenrir"}
DEFAULT_VOICE = "Charon"
LANGS = {"en": None, "hi": "hi-IN"}     # None: PANIM_CHIRP_LANG
SAMPLE_RATE = 24000


def _key() -> str | None:
    return os.environ.get("GOOGLE_TTS_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


def configured() -> bool:
    """Chirp can be called here: an API key, or service-account credentials google-auth can use."""
    if _key():
        return True
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path or not os.path.isfile(path):
        return False
    import importlib.util

    return importlib.util.find_spec("google.auth") is not None


@lru_cache(None)
def _credentials():
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return creds, google.auth.transport.requests.Request()


def _token() -> str:
    creds, request = _credentials()
    if not creds.valid:
        creds.refresh(request)
    return creds.token


def voice_for(style: str | None) -> str:
    """The Chirp 3 HD voice name (Charon) for a lecture style."""
    return os.environ.get("PANIM_CHIRP_VOICE") or STYLE_VOICES.get(style or "", DEFAULT_VOICE)


def language(lang: str) -> str:
    """The BCP-47 code a line in `lang` ('en', 'hi') is spoken in."""
    return LANGS.get(lang) or os.environ.get("PANIM_CHIRP_LANG") or "en-US"


def synthesize(text: str, voice: str = DEFAULT_VOICE, lang: str = "en", speed: float = 1.0) -> bytes:
    """A WAV (16-bit, 24 kHz, mono) of one line. Raises RuntimeError with Google's message when it fails."""
    code = language(lang)
    name = voice if "-Chirp3-HD-" in voice else f"{code}-Chirp3-HD-{voice}"
    body = {"input": {"text": text}, "voice": {"languageCode": code, "name": name},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SAMPLE_RATE}}
    if abs(speed - 1.0) > 1e-3:
        body["audioConfig"]["speakingRate"] = round(speed, 2)
    url = os.environ.get("GOOGLE_TTS_URL") or URL
    last = ""
    for attempt in range(4):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        target = url
        if _key():
            target = f"{url}?key={_key()}"
        else:
            headers["Authorization"] = f"Bearer {_token()}"
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
        print("no Google credentials: set GOOGLE_TTS_API_KEY (see harness/SETUP.md)", file=sys.stderr)
        return 1
    audio = synthesize(sys.argv[1], voice_for(os.environ.get("LECTURE_STYLE")))
    with open(sys.argv[2], "wb") as handle:
        handle.write(audio)
    print(f"wrote {sys.argv[2]} ({len(audio)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
