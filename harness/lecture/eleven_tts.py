"""ElevenLabs (Eleven v4 Turbo by default): an expressive narration voice that says when each word is spoken.

The line is spoken by ElevenLabs' own API, its "with timestamps" endpoint, which returns the audio with the start
and end of every character. Those become the words' times (words()), kept beside the cached line
(pocket_lecture.words_file), and the lecture's animations are timed to them after the voice is made
(align_cues.py). A line may carry audio tags ("[thoughtful]", "[short pause]") and emphasis put in by
voice_director.py; the tags are said as delivery, not words, and are left out of the words' times.

Credentials: ELEVENLABS_API_KEY, in the environment or harness/app/.env.local. PANIM_TTS=eleven picks this voice.
Settings:
  PANIM_ELEVEN_MODEL      the model id (eleven_v4_turbo; eleven_v4 for the slower, most expressive one)
  PANIM_ELEVEN_VOICE      the voice id (a premade or your own voice from the Voice Library)
  PANIM_ELEVEN_LANGUAGE   an ISO 639-1 code to force the language (en, hi); unset: the model detects it
  PANIM_ELEVEN_STABILITY  0..1, lower is more expressive and varied (unset: the voice's own setting)
  PANIM_ELEVEN_PRICE      US dollars per million characters, for the cost shown on the page (unset: not priced)
  ELEVENLABS_URL          the API base (a test points it at a mock)

    .venv/bin/python harness/lecture/eleven_tts.py --check                   # the key, and a test line
    .venv/bin/python harness/lecture/eleven_tts.py "Hello there." out.wav  # try it (the words go to out.words.json)
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import wave

from chirp import _env

NAME = "ElevenLabs Eleven v4 Turbo"
MODEL = "eleven_v4_turbo"
URL = "https://api.elevenlabs.io"
# A clear, neutral premade voice ("Rachel"); PANIM_ELEVEN_VOICE picks another.
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"
SAMPLE_RATE = 24000
OUTPUT_FORMAT = f"pcm_{SAMPLE_RATE}"     # 16-bit PCM, mono
# Bumped when the way lines are spoken changes, so cached lines are spoken again (pocket_lecture.audio_file).
REVISION = 1
TRIES = 6
TIMEOUT = 120
# Requests and their outcomes, for the build's timing log (scripts/prespeak.py reads CALLS).
CALLS: list[dict] = []
_spent = threading.local()


def configured() -> bool:
    return bool(_key())


def _key() -> str | None:
    return _env("ELEVENLABS_API_KEY") or _env("XI_API_KEY") or None


def model() -> str:
    return _env("PANIM_ELEVEN_MODEL") or MODEL


def voice_for(style: str | None) -> str:
    return _env("PANIM_ELEVEN_VOICE") or DEFAULT_VOICE


def last_cost() -> dict:
    """What the last speak() on this thread cost: {"chars", "usd"}."""
    return dict(getattr(_spent, "line", None) or {"chars": 0, "usd": 0.0})


def last_words() -> list[dict]:
    """The words of the last speak() on this thread, as said: [{"w", "start", "end"}] in seconds into its audio."""
    return list(getattr(_spent, "words", None) or [])


# ---------------- the words' times ----------------

def words(characters: list[str], starts: list[float], ends: list[float]) -> list[dict]:
    """Words and their times from ElevenLabs' character alignment: a word runs from its first letter's start to
    its last letter's end. Audio tags ("[sighs]") and the IPA slashes of a pronunciation are delivery, not words:
    they are left out."""
    out: list[dict] = []
    current, begin, finish = "", 0.0, 0.0
    in_tag = False

    def close():
        nonlocal current
        word = current.strip("\"'“”‘’.,;:!?…—–-()")
        if word:
            out.append({"w": word, "start": round(begin, 3), "end": round(finish, 3)})
        current = ""

    for ch, s, e in zip(characters, starts, ends):
        if ch == "[":
            close()
            in_tag = True
            continue
        if in_tag:
            if ch == "]":
                in_tag = False
            continue
        if ch.isspace():
            close()
            continue
        if ch == "/":
            continue
        if not current:
            begin = float(s)
        current += ch
        finish = float(e)
    close()
    return out


# ---------------- speaking ----------------

def _wav(pcm: bytes, rate: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return out.getvalue()


def _body(text: str, speed: float) -> dict:
    body: dict = {"text": text, "model_id": model()}
    settings: dict = {}
    if abs(speed - 1.0) > 1e-3:
        settings["speed"] = max(0.7, min(1.2, speed))       # ElevenLabs' range
    stability = _env("PANIM_ELEVEN_STABILITY")
    if stability:
        settings["stability"] = max(0.0, min(1.0, float(stability)))
    if settings:
        body["voice_settings"] = settings
    language = _env("PANIM_ELEVEN_LANGUAGE")
    if language:
        body["language_code"] = language.strip()
    return body


def synthesize(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> tuple[bytes, int, list[dict]]:
    """(16-bit mono PCM, its sample rate, the words' times) for one line. Refusals that pass (429, 5xx, a dropped
    connection) are waited out and asked again; any other is the line's error, with ElevenLabs' message."""
    key = _key()
    if not key:
        raise RuntimeError("no ElevenLabs API key: set ELEVENLABS_API_KEY in harness/app/.env.local")
    url = f"{(_env('ELEVENLABS_URL') or URL).rstrip('/')}/v1/text-to-speech/{voice}/with-timestamps" \
          f"?output_format={OUTPUT_FORMAT}"
    data = json.dumps(_body(text, speed)).encode()
    call = {"start": time.time() * 1000, "chars": len(text), "tries": 0, "waited": 0.0, "codes": []}
    CALLS.append(call)
    wait = 2.0
    for attempt in range(TRIES):
        call["tries"] = attempt + 1
        request = urllib.request.Request(url, data=data, method="POST", headers={
            "xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                reply = json.loads(response.read())
            break
        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", "replace")[:400]
            call["codes"].append(error.code)
            if error.code not in (429, 500, 502, 503, 504) or attempt == TRIES - 1:
                call["end"] = time.time() * 1000
                raise RuntimeError(f"ElevenLabs {error.code}: {message}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            if attempt == TRIES - 1:
                call["end"] = time.time() * 1000
                raise RuntimeError(f"ElevenLabs could not be reached: {error}") from None
        time.sleep(wait)
        call["waited"] += wait
        wait = min(wait * 2, 30.0)
    call["end"] = time.time() * 1000
    call["ok"] = True
    audio = base64.b64decode(reply.get("audio_base64") or "")
    if not audio:
        raise RuntimeError("ElevenLabs returned no audio")
    if audio[:4] == b"RIFF":
        with wave.open(io.BytesIO(audio)) as handle:
            rate = handle.getframerate()
            audio = handle.readframes(handle.getnframes())
    else:
        rate = SAMPLE_RATE
    align = reply.get("alignment") or reply.get("normalized_alignment") or {}
    said = words(align.get("characters") or [], align.get("character_start_times_seconds") or [],
                 align.get("character_end_times_seconds") or [])
    return audio, rate, said


def speak(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> bytes:
    """A WAV (16-bit, mono) of one line; its words' times are last_words(), its cost last_cost()."""
    pcm, rate, said = synthesize(text, voice, speed)
    price = _env("PANIM_ELEVEN_PRICE")
    chars = len(re.sub(r"\[[^\]]*\]", "", text))
    _spent.line = {"chars": chars, "usd": round(chars * float(price) / 1e6, 6) if price else 0.0}
    _spent.words = said
    return _wav(pcm, rate)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        if not configured():
            print("no ElevenLabs key: set ELEVENLABS_API_KEY")
            return 1
        wav = speak("This is the narration voice.", voice_for(None))
        print(f"ok: {model()} spoke {len(wav)} bytes; words: {last_words()}")
        return 0
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    wav = speak(sys.argv[1], voice_for(None))
    with open(sys.argv[2], "wb") as handle:
        handle.write(wav)
    with open(re.sub(r"\.wav$", "", sys.argv[2]) + ".words.json", "w") as handle:
        json.dump(last_words(), handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
