"""The narration spoken by Google's Gemini TTS (gemini-3.8-flash-lite-tts by default), a line a call, several at
once, through the Gemini API's Interactions endpoint (GEMINI_API_KEY). Each line comes back as WAV (24 kHz, mono,
16-bit); its silence at either end is trimmed, so the lines' times are where the voice is.

    V3_TTS_MODEL    gemini-3.8-flash-lite-tts (or gemini-3.8-flash-tts, the fuller one)
    V3_TTS_STYLE    how it is said (speech_metadata.style); the language's own style when blank
    V3_TTS_JOBS     lines spoken at once (4)

Hinglish is told how to sound (Hindi words said as Hindi, English words in an Indian English accent); its words are
timed by where the pauses fall in each line (Whisper does not hear Roman-letter Hindi as written), see voice.py.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor

import numpy as np

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = os.environ.get("V3_TTS_MODEL", "gemini-3.8-flash-lite-tts")
RATE = 24000
VOICES = ("Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus",
          "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
          "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia",
          "Sadaltager", "Sulafat")
STYLES = {
    "en": "a warm, clear documentary narrator, unhurried, curious",
    "hinglish": "a friendly Indian explainer speaking natural Hinglish: Hindi words said as Hindi, English words in "
                "an Indian English accent, warm and conversational, unhurried",
    "hi": "a warm, clear Hindi documentary narrator, unhurried",
    "character": "in character, as a person in the story speaking their own line, vivid and natural",
}


def voices_for(who: list[str], narrator: str, given: dict) -> dict:
    """A voice for each character: the one the narration names (`@monk = Charon`), else one picked from its name,
    never the narrator's, and no two alike while there are voices to spare."""
    out, taken = {}, {narrator}
    for w in who:
        v = given.get(w)
        if v and v.split(":")[-1] in VOICES:
            out[w] = v.split(":")[-1]
            taken.add(out[w])
    import zlib
    for w in who:
        if w in out:
            continue
        free = [v for v in VOICES if v not in taken] or [v for v in VOICES if v != narrator]
        out[w] = free[zlib.crc32(w.encode()) % len(free)]
        taken.add(out[w])
    return out


def key() -> str:
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if not k:
        raise RuntimeError("no GEMINI_API_KEY: put it in harness_v3/.env.local for Gemini TTS (or pick a Piper voice)")
    return k


def _pcm(wav_bytes: bytes) -> np.ndarray:
    """A WAV (or bare 16-bit PCM at 24 kHz) as float samples at RATE."""
    if wav_bytes[:4] == b"RIFF":
        with wave.open(io.BytesIO(wav_bytes)) as w:
            rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
    else:
        rate, ch, width, raw = RATE, 1, 2, wav_bytes
    a = np.frombuffer(raw, dtype={1: np.int8, 2: np.int16, 4: np.int32}[width]).astype(np.float32)
    a /= float(2 ** (8 * width - 1))
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if rate != RATE:
        n = int(round(len(a) * RATE / rate))
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    return a


def _trim(a: np.ndarray, floor: float = 0.012) -> np.ndarray:
    """The silence at either end cut off (a few milliseconds kept)."""
    loud = np.flatnonzero(np.abs(a) > floor)
    if not len(loud):
        return a
    pad = int(0.03 * RATE)
    return a[max(0, loud[0] - pad): min(len(a), loud[-1] + pad)]


def say(text: str, voice: str, style: str, model: str | None = None, tries: int = 5) -> np.ndarray:
    """One line spoken: its samples at RATE, trimmed."""
    body = {"model": model or MODEL,
            "input": [{"type": "user_input", "content": [{
                "type": "text", "text": text,
                "annotations": [{"type": "speech_metadata", "style": style}] if style else []}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": key(), "Content-Type": "application/json"})
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.loads(r.read())
            data = None
            for st in out.get("steps", []):
                if st.get("type") == "model_output":
                    for c in st.get("content", []):
                        if c.get("type") == "audio" and c.get("data"):
                            data = c["data"]
            data = data or (out.get("output_audio") or {}).get("data")
            if not data:
                raise RuntimeError(f"no audio in the answer: {json.dumps(out)[:300]}")
            return _trim(_pcm(base64.b64decode(data)))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"
            if e.code not in (408, 429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
            last = str(e)
        time.sleep(2 ** k)
    raise RuntimeError(f"Gemini TTS failed on {text[:60]!r}: {last}")


def speak(lines: list[str], voice: str, style: str, pause: float, on_line=None) -> tuple[np.ndarray, list]:
    """Every line in one voice and style (speak_lines)."""
    return speak_lines([(ln, voice, style) for ln in lines], pause, on_line)


def speak_lines(lines: list[tuple[str, str, str]], pause: float, on_line=None) -> tuple[np.ndarray, list]:
    """Every line spoken, each (text, voice, style), V3_TTS_JOBS at once, joined with a pause between:
    (samples, [(start, end)])."""
    jobs = max(1, int(os.environ.get("V3_TTS_JOBS", "4")))
    done = [0]

    def one(job):
        a = say(*job)
        done[0] += 1
        if on_line:
            on_line(done[0])
        return a
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        clips = list(pool.map(one, lines))
    gap = np.zeros(int(pause * RATE), dtype=np.float32)
    out, spans, at = [np.zeros(int(0.3 * RATE), dtype=np.float32)], [], 0.3
    for c in clips:
        spans.append((at, at + len(c) / RATE))
        out += [c, gap]
        at += len(c) / RATE + pause
    return np.concatenate(out), spans
