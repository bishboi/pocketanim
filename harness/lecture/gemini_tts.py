"""Gemini 3.8 Flash-Lite TTS: the narration voice (Google's Gemini API, generally available since September 2026).

Gemini's speech model reads a whole line in one request, Hindi and English together: a Hinglish sentence
("अब normal reaction समझते हैं") needs no cutting into language runs, as Chirp 3 HD did, and the switch between
the two sounds like one teacher talking. Its 30 prebuilt voices have the same names as Chirp's (Charon, Kore,
Aoede...); every lecture is spoken by Achird. The lecture engine caches each line
(pocket_lecture.narrate), so a line is paid for once.

Credentials: a Gemini API key from Google AI Studio (aistudio.google.com/apikey), as GEMINI_API_KEY (or
GOOGLE_API_KEY), in the environment or harness/app/.env.local.
Settings:
  PANIM_TTS_MODEL      the model (gemini-3.8-flash-lite-tts: fast and cheap; gemini-3.8-flash-tts: more expressive)
  PANIM_TTS_VOICE      another prebuilt voice (Charon, Kore, Aoede...); the speaker is Achird otherwise
  PANIM_TTS_LANGUAGE   the language and accent each line is spoken in: "auto" (default) says a line with Hindi in it
                       as hi-IN and an all-English line as en-IN (Indian English), so no line comes out in an
                       American or British accent; or one BCP-47 code for every line (hi-IN, en-IN, ...); "none"
                       lets the model guess from the words, as before
  PANIM_TTS_STYLE      how to read, sent as an instruction, for a model that takes one ("teacher" for the built-in
                       one); off by default, as the Gemini 3.8 TTS models refuse instructions
  GEMINI_TTS_URL       the endpoint base (a test points it at a mock)

    .venv/bin/python harness/lecture/gemini_tts.py --check                  # the key, and a test line
    .venv/bin/python harness/lecture/gemini_tts.py "Hello there." out.wav # try it
"""

from __future__ import annotations

import base64
import http.client
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
import urllib.request
import wave

from chirp import ENV_FILE, _env, _pcm, _pieces, _trim

NAME = "Gemini 3.8 Flash-Lite TTS"
MODEL = "gemini-3.8-flash-lite-tts"
URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_VOICE = "Achird"      # the narration speaker for every lecture style
SAMPLE_RATE = 24000            # Gemini's speech is 16-bit PCM, mono, 24 kHz
# Bumped when the way lines are spoken changes, so cached lines are spoken again (pocket_lecture.audio_file).
REVISION = 2                   # 2: every line spoken with its language code (an Indian accent)
# A line longer than this is spoken a few sentences at a time (the model takes up to 8,192 tokens, but a long
# request is slower and, when it fails, costs the whole line again).
CHUNK_BYTES = int(os.environ.get("PANIM_TTS_CHUNK_BYTES", "2400"))
TRIES = 7
_REFUSES_INSTRUCTION = False
_REFUSED_LANGUAGES: set[str] = set()      # codes the model said it does not speak: not sent again this run
DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# PANIM_TTS_STYLE=teacher sends this; any other text is sent as it is. Off by default (see synthesize).
STYLE = ("Read this aloud as a warm, patient teacher explaining to a class: clearly, at an easy pace, with "
         "natural pauses. Hindi words in Hindi, English terms in English, as an Indian teacher speaks.")


def language_setting() -> str:
    return (_env("PANIM_TTS_LANGUAGE") or "auto").strip()


def language_for(text: str) -> str | None:
    """The BCP-47 code a piece of text is spoken in, or None to let the model guess. Left to guess, the model read
    some Hindi lines, and most English terms, in an American accent: an Indian teacher's class wants hi-IN for
    Hindi and Hinglish, and Indian English (en-IN) for a line all in English."""
    setting = language_setting()
    if setting.lower() in ("none", "off", "0"):
        return None
    if setting.lower() == "auto":
        code = "hi-IN" if DEVANAGARI.search(text) else "en-IN"
    else:
        code = setting
    return None if code in _REFUSED_LANGUAGES else code


def _key() -> str | None:
    return _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY") or None


def configured() -> bool:
    return bool(_key())


def model() -> str:
    return _env("PANIM_TTS_MODEL") or MODEL


def voice_for(style: str | None) -> str:
    """The prebuilt voice lectures are spoken in: Achird for every style, or PANIM_TTS_VOICE."""
    return _env("PANIM_TTS_VOICE") or DEFAULT_VOICE


# US dollars per million tokens: (text in, audio out), at Google's list price for the standard tier. Both double on
# 1 January 2027, when the launch price ends. PANIM_TTS_PRICE="in,out" sets another (a batch or priority tier).
PRICES = {"gemini-3.8-flash-lite-tts": (0.50, 6.00), "gemini-3.8-flash-tts": (0.50, 9.00)}
AUDIO_TOKENS_PER_SECOND = 25
_spent = threading.local()
# Every request to Google, for the build's timing log: characters, how long it took, the tries and the seconds spent
# waiting out refusals (429: the per-minute quota), and how it ended.
CALLS: list[dict] = []


def price(model_id: str | None = None) -> tuple[float, float]:
    custom = _env("PANIM_TTS_PRICE")
    if custom:
        try:
            a, b = (float(x) for x in custom.split(","))
            return a, b
        except ValueError:
            pass
    base = PRICES.get(model_id or model(), PRICES[MODEL])
    return (base[0] * 2, base[1] * 2) if time.time() >= 1798761600 else base      # 2027-01-01 UTC


def cost(text_tokens: float, audio_tokens: float, model_id: str | None = None) -> float:
    rate_in, rate_out = price(model_id)
    return (text_tokens * rate_in + audio_tokens * rate_out) / 1e6


def last_cost() -> dict:
    """What the last speak() on this thread cost: {"in", "out", "usd"} (tokens, and US dollars)."""
    return dict(getattr(_spent, "line", None) or {"in": 0, "out": 0, "usd": 0.0})


def _count(reply: dict, text: str, pcm: bytes, rate: int) -> None:
    """Add one reply's tokens to the line being spoken: Google's own count (usageMetadata), or an estimate from the
    text and the audio's length when a reply has none."""
    usage = reply.get("usageMetadata") or {}
    text_tokens = usage.get("promptTokenCount") or max(1, len(text) // 4)
    audio_tokens = usage.get("candidatesTokenCount") or round(len(pcm) / 2 / max(rate, 1) * AUDIO_TOKENS_PER_SECOND)
    line = getattr(_spent, "line", None)
    if line is not None:
        line["in"] += int(text_tokens)
        line["out"] += int(audio_tokens)
        line["usd"] = cost(line["in"], line["out"])


def _audio_of(reply: dict) -> tuple[bytes, int]:
    """(PCM, sample rate) from a generateContent reply: base64 inline data, raw PCM (audio/L16;rate=24000) or a
    WAV."""
    for candidate in reply.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            data = part.get("inlineData") or part.get("inline_data")
            if not data or not data.get("data"):
                continue
            audio = base64.b64decode(data["data"])
            if audio[:4] == b"RIFF":
                return _pcm(audio)
            rate = re.search(r"rate=(\d+)", str(data.get("mimeType") or data.get("mime_type") or ""))
            return audio, int(rate.group(1)) if rate else SAMPLE_RATE
    reason = ", ".join(str(c.get("finishReason")) for c in reply.get("candidates") or []) or \
        str((reply.get("promptFeedback") or {}).get("blockReason") or "no audio")
    raise RuntimeError(f"{NAME} returned no audio ({reason})")


def synthesize(text: str, voice: str = DEFAULT_VOICE) -> tuple[bytes, int]:
    """(PCM, sample rate) for one piece of text. Raises RuntimeError with Google's message when it fails."""
    global _REFUSES_INSTRUCTION
    body = {
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    code = language_for(text)
    if code:
        body["generationConfig"]["speechConfig"]["languageCode"] = code
    # An instruction only when asked for: the Gemini 3.8 TTS models refuse one ("Developer instruction is not enabled
    # for this model"). Once refused, it is not sent again this run.
    style = _env("PANIM_TTS_STYLE")
    if style and style != "none" and not _REFUSES_INSTRUCTION:
        body["systemInstruction"] = {"parts": [{"text": STYLE if style == "teacher" else style}]}
    url = f"{_env('GEMINI_TTS_URL') or URL}/{model()}:generateContent"
    last = ""
    call = {"chars": len(text), "start": time.time() * 1000, "tries": 0, "waited": 0.0, "codes": []}
    CALLS.append(call)
    try:
        return _synthesize(body, url, call)
    finally:
        call["end"] = time.time() * 1000


def _synthesize(body: dict, url: str, call: dict) -> tuple[bytes, int]:
    global _REFUSES_INSTRUCTION
    text = body["contents"][0]["parts"][0]["text"]
    last = ""
    for attempt in range(TRIES):
        call["tries"] = attempt + 1
        request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
            "Content-Type": "application/json; charset=utf-8", "x-goog-api-key": _key() or ""})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                reply = json.loads(response.read())
            pcm, rate = _audio_of(reply)
            _count(reply, text, pcm, rate)
            call["ok"] = True
            return pcm, rate
        except urllib.error.HTTPError as error:
            call["codes"].append(error.code)
            detail = error.read().decode("utf-8", "replace")
            try:
                last = json.loads(detail)["error"]["message"]
            except Exception:  # noqa: BLE001
                last = detail[:300]
            if error.code == 400 and "systemInstruction" in body and re.search(r"(system|developer).?instruction", last, re.I):
                _REFUSES_INSTRUCTION = True             # a model that takes no instruction: read as it is
                del body["systemInstruction"]
                continue
            speech = body["generationConfig"]["speechConfig"]
            if error.code == 400 and "languageCode" in speech and re.search(r"language", last, re.I):
                _REFUSED_LANGUAGES.add(speech.pop("languageCode"))   # not one it speaks: let it pick, as before
                print(f"{NAME}: {last} (spoken without a language code)", file=sys.stderr)
                continue
            if error.code in (429, 500, 502, 503, 504) and attempt < TRIES - 1:
                # A long lecture is thousands of lines: the per-minute quota runs out, and is waited out.
                wait = error.headers.get("Retry-After") if error.headers else None
                pause = float(wait) if wait and wait.isdigit() else min(60, 2 ** attempt * (4 if error.code == 429 else 1))
                call["waited"] += pause
                time.sleep(pause)
                continue
            if error.code in (401, 403) or "API key" in last:
                raise RuntimeError(f"{NAME} {error.code}: {last} -- check GEMINI_API_KEY (a key from "
                                   "aistudio.google.com/apikey) in harness/app/.env.local") from None
            raise RuntimeError(f"{NAME} {error.code}: {last}") from None
        except urllib.error.URLError as error:
            last = str(error.reason)
            if attempt < TRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"{NAME} unreachable: {last}") from None
        except (OSError, http.client.HTTPException) as error:
            call["codes"].append(type(error).__name__)
            # The connection dropped partway through the reply (ConnectionResetError, a read timeout, an incomplete
            # read): the same request again, then a RuntimeError the caller reports, never a crash of the batch.
            last = f"{type(error).__name__}: {error}"
            if attempt < TRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"{NAME} connection failed: {last}") from None
        except RuntimeError as error:                   # an answer with no audio in it: once more, then give up
            last = str(error)
            if attempt < 1:
                continue
            raise
    raise RuntimeError(f"{NAME} failed: {last}")


def _tempo(pcm: bytes, rate: int, speed: float) -> bytes:
    """The speech at `speed` (0.85 = slower) without changing its pitch, through ffmpeg's atempo. Gemini has no
    speaking-rate setting; without ffmpeg the line keeps its own pace."""
    if abs(speed - 1.0) < 1e-3 or not shutil.which("ffmpeg"):
        return pcm
    run = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
                          "-af", f"atempo={max(0.5, min(2.0, speed)):.3f}", "-f", "s16le", "-ar", str(rate), "-ac", "1",
                          "pipe:1"], input=pcm, capture_output=True, timeout=120)
    return run.stdout if run.returncode == 0 and run.stdout else pcm


def speak(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> bytes:
    _spent.line = {"in": 0, "out": 0, "usd": 0.0}       # last_cost() reads it after
    return _speak(text, voice, speed)


def _speak(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> bytes:
    """A WAV (16-bit, mono) of one line, Hindi and English read together; a long line a few sentences at a time."""
    pcm, rate = b"", SAMPLE_RATE
    for index, piece in enumerate(_pieces(text, CHUNK_BYTES)):
        clip, rate = synthesize(piece, voice)
        clip = _trim(clip, rate)
        pcm += (b"\x00\x00" * int(rate * 0.18) if index else b"") + clip
    pcm = _tempo(pcm, rate, speed)
    out = io.BytesIO()
    with wave.open(out, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return out.getvalue()


# ---------------- several lines in one request ----------------
# Google's TTS allows only so many requests a minute (about 10-15 on most keys): one request a line made a lecture
# of 400 lines take half an hour of waiting out "429 Too Many Requests". Lines are spoken a few at a time instead,
# one request for several, and the audio is cut back into lines at the pauses between them.
BATCH_LINES = max(1, int(os.environ.get("PANIM_TTS_BATCH", "4") or 4))
BATCH_BYTES = int(os.environ.get("PANIM_TTS_BATCH_BYTES", "700"))
_FRAME = 0.01              # seconds a frame, when looking for pauses


def _pauses(samples, rate: int) -> list[tuple[float, float]]:
    """The quiet stretches inside speech, (middle, length) in seconds, from frames of 10 ms."""
    import numpy as np

    size = max(1, int(rate * _FRAME))
    frames = len(samples) // size
    if frames < 3:
        return []
    level = np.sqrt((samples[:frames * size].astype(np.float64).reshape(frames, size) ** 2).mean(axis=1))
    quiet = level < max(250.0, 0.06 * float(np.percentile(level, 95)))
    out, start = [], None
    for index, still in enumerate(quiet):
        if still and start is None:
            start = index
        elif not still and start is not None:
            if start > 0:                                   # not the silence before the first word
                out.append(((start + index) / 2 * _FRAME, (index - start) * _FRAME))
            start = None
    return out                                               # the silence after the last word is left out


def split_lines(pcm: bytes, rate: int, texts: list[str]) -> list[bytes] | None:
    """`pcm`, the lines `texts` spoken one after another, cut into one clip a line; None when the cuts cannot be
    trusted (a missing pause, a cut far from where its words put it), so the lines are spoken one by one instead.

    Each line ends about where its share of the words puts it (`texts`' lengths); for each, the pause chosen is the
    best by being long and near that point, in order (dynamic programming over the pauses)."""
    import numpy as np

    samples = np.frombuffer(pcm, dtype=np.int16)
    n = len(texts)
    if n == 1:
        return [pcm]
    total = len(samples) / rate
    weights = [max(1, len(t)) for t in texts]
    expected = list(np.cumsum(weights)[:-1] / sum(weights) * total)
    pauses = [p for p in _pauses(samples, rate) if p[1] >= 0.12]
    if len(pauses) < n - 1:
        return None
    longest = sorted((p[1] for p in pauses), reverse=True)[n - 2]
    scale = max(0.6, total / n * 0.35)                # how far a cut may sit from its expected point

    def cost(k: int, j: int) -> float:
        middle, length = pauses[j]
        return ((middle - expected[k]) / scale) ** 2 - 2.0 * min(length, 1.5)

    m = len(pauses)
    best = [[float("inf")] * m for _ in range(n - 1)]
    back = [[-1] * m for _ in range(n - 1)]
    for j in range(m):
        best[0][j] = cost(0, j)
    for k in range(1, n - 1):
        run, arg = float("inf"), -1
        for j in range(m):
            if j - 1 >= 0 and best[k - 1][j - 1] < run:
                run, arg = best[k - 1][j - 1], j - 1
            if arg >= 0:
                best[k][j] = run + cost(k, j)
                back[k][j] = arg
    end = min(range(m), key=lambda j: best[n - 2][j])
    if best[n - 2][end] == float("inf"):
        return None
    chosen = [end]
    for k in range(n - 2, 0, -1):
        chosen.append(back[k][chosen[-1]])
    chosen.reverse()
    cuts = []
    for k, j in enumerate(chosen):
        middle, length = pauses[j]
        # A cut must sit on a real break (as long as the shorter of the breaks between lines would be) and near
        # where its words put it; else the lines are spoken one by one.
        if length < min(0.25, 0.6 * longest) or abs(middle - expected[k]) > scale * 1.6:
            return None
        cuts.append(int(middle * rate))
    bounds = [0, *cuts, len(samples)]
    return [samples[a:b].tobytes() for a, b in zip(bounds, bounds[1:])]


def _wav(pcm: bytes, rate: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return out.getvalue()


def speak_many(texts: list[str], voice: str = DEFAULT_VOICE, speed: float = 1.0) -> list[tuple[bytes, dict]] | None:
    """Several lines in one request: [(WAV, cost {"in", "out", "usd"})] a line, in order, the request's cost shared
    by each line's length of speech; None when the audio cannot be cut back into the lines (they are then spoken one
    at a time). The lines are read as paragraphs, so the voice pauses between them."""
    texts = [t.strip() for t in texts]
    if len(texts) < 2 or any(not t for t in texts):
        return None
    _spent.line = {"in": 0, "out": 0, "usd": 0.0}
    pcm, rate = synthesize("\n\n".join(texts), voice)
    spent = dict(_spent.line)
    clips = split_lines(_trim(pcm, rate), rate, texts)
    if clips is None:
        return None
    clips = [_tempo(_trim(clip, rate), rate, speed) for clip in clips]
    length = sum(len(c) for c in clips) or 1
    out = []
    for clip in clips:
        share = len(clip) / length
        out.append((_wav(clip, rate), {"in": round(spent["in"] * share), "out": round(spent["out"] * share),
                                       "usd": spent["usd"] * share, "batched": len(texts)}))
    return out


def check() -> int:
    """Whether a key is set and Gemini speaks with it (one short line)."""
    env_file = os.environ.get("PANIM_ENV_FILE", ENV_FILE)
    print(f"settings file    : {os.path.normpath(env_file) if env_file and os.path.isfile(env_file) else 'none'}")
    print(f"model            : {model()}")
    print(f"key              : {'set' if configured() else 'NONE -- put GEMINI_API_KEY=... in harness/app/.env.local'}")
    if not configured():
        return 1
    try:
        audio = speak("नमस्ते बच्चों। आज हम force के बारे में पढ़ेंगे।", voice_for(os.environ.get("LECTURE_STYLE")))
    except RuntimeError as error:
        print(f"Google said      : {error}")
        return 1
    print(f"Google spoke     : {len(audio)} bytes of audio. The voice is ready.")
    return 0


def main() -> int:
    if sys.argv[1:] == ["--check"]:
        return check()
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    if not configured():
        print("no Gemini API key: set GEMINI_API_KEY (harness/SETUP.md)", file=sys.stderr)
        return 1
    audio = speak(sys.argv[1], voice_for(os.environ.get("LECTURE_STYLE")))
    with open(sys.argv[2], "wb") as handle:
        handle.write(audio)
    print(f"wrote {sys.argv[2]} ({len(audio)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
