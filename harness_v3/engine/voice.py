"""The narration: spoken, and every word's time.

    python voice.py narration.txt out_dir [--voice en_US-ryan-high] [--pause 0.45]

Each line of the narration file is a sentence, spoken by itself (Piper, an offline neural voice; or, with
ELEVENLABS_API_KEY set, ElevenLabs later) and joined with a pause between, so the quiet between ideas is ours. Then
Whisper hears the whole take and each of the script's own words is given the time it is said (the transcript's words
matched to the script's in order), so a score can say "w12" and mean the twelfth word as written.

Writes out_dir/voice.wav and out_dir/words.json: {"seconds", "lines": [{"text", "start", "end"}],
"words": [{"i", "w", "start", "end", "line"}]}.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
VOICES = HERE.parent / ".cache" / "voices"
RATE = 22050


def words_of(text: str) -> list[str]:
    """A line's words as a score counts them: split at spaces."""
    return [w for w in text.split() if w.strip()]


def _plain(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def speak(lines: list[str], out: Path, voice: str, pause: float, speed: float) -> list[tuple[float, float]]:
    """Every line spoken and joined, a pause between them; each line's (start, end) in the take."""
    from piper import PiperVoice, SynthesisConfig

    model = PiperVoice.load(str(VOICES / f"{voice}.onnx"))
    config = SynthesisConfig(length_scale=speed)
    frames, spans, at = bytearray(), [], 0.0
    width = 2
    lead = int(0.3 * model.config.sample_rate) * width
    frames += b"\0" * lead
    at = 0.3
    print(f"speaking {len(lines)} lines ({voice})", flush=True)
    for k, line in enumerate(lines):
        print(f"progress: {k}/{len(lines)} lines spoken", flush=True)
        chunk = bytearray()
        rate = model.config.sample_rate
        for audio in model.synthesize(line, syn_config=config):
            chunk += audio.audio_int16_bytes
        seconds = len(chunk) / width / rate
        spans.append((at, at + seconds))
        frames += chunk
        gap = int(pause * rate) * width
        frames += b"\0" * gap
        at += seconds + pause
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(width)
        wf.setframerate(model.config.sample_rate)
        wf.writeframes(bytes(frames))
    return spans


def _samples16k(wav: Path):
    """The take as Whisper hears it (mono float32 at 16 kHz), read here: Whisper's own reader goes through PyAV,
    whose API changes between versions (av 19 dropped an argument it passes)."""
    import numpy as np

    with wave.open(str(wav), "rb") as wf:
        rate, width, chans = wf.getframerate(), wf.getsampwidth(), wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    x = np.frombuffer(raw, dtype={1: np.uint8, 2: np.int16, 4: np.int32}[width]).astype(np.float32)
    x = (x - 128) / 128 if width == 1 else x / float(2 ** (8 * width - 1))
    if chans > 1:
        x = x.reshape(-1, chans).mean(axis=1)
    if rate != 16000:
        n = int(round(len(x) * 16000 / rate))
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    return x


def timed_words(wav: Path, lines: list[str], spans: list[tuple[float, float]]) -> list[dict]:
    """Each written word with when it is said: Whisper's words matched to the script's in order; a word it did not
    hear takes its neighbours' times (spread evenly between them)."""
    from faster_whisper import WhisperModel

    model = WhisperModel("base.en", device="cpu", compute_type="int8", download_root=str(HERE.parent / ".cache" / "whisper"))
    segments, _ = model.transcribe(_samples16k(wav), word_timestamps=True, language="en")
    heard = [(w.word.strip(), float(w.start), float(w.end)) for s in segments for w in (s.words or [])]
    script = [(li, w) for li, line in enumerate(lines) for w in words_of(line)]
    a = [_plain(w) for _, w in script]
    b = [_plain(w) for w, _, _ in heard]
    times: list[tuple[float, float] | None] = [None] * len(script)
    for block in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            _, s, e = heard[block.b + k]
            times[block.a + k] = (s, e)
    # A word not heard (a number said in words, a name): spread between its line's known neighbours.
    for i, t in enumerate(times):
        if t is not None:
            continue
        li = script[i][0]
        j = i - 1
        while j >= 0 and (times[j] is None or script[j][0] != li):
            j -= 1
        k = i + 1
        while k < len(times) and (times[k] is None or script[k][0] != li):
            k += 1
        lo = times[j][1] if j >= 0 and script[j][0] == li else spans[li][0]
        hi = times[k][0] if k < len(times) and script[k][0] == li else spans[li][1]
        n = k - j - 1 if k - j - 1 > 0 else 1
        step = (hi - lo) / (n + 0)
        pos = i - j - 1
        times[i] = (lo + step * pos, lo + step * (pos + 1))
    return [{"i": i, "w": w, "start": round(times[i][0], 3), "end": round(times[i][1], 3), "line": li}
            for i, (li, w) in enumerate(script)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("narration")
    ap.add_argument("out")
    ap.add_argument("--voice", default="en_US-ryan-high")
    ap.add_argument("--pause", type=float, default=0.45)
    ap.add_argument("--speed", type=float, default=1.05, help="Piper's length scale: above 1 is slower")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lines = [l.strip() for l in Path(a.narration).read_text().splitlines() if l.strip()]
    wav = out / "voice.wav"
    spans = speak(lines, wav, a.voice, a.pause, a.speed)
    print(f"progress: {len(lines)}/{len(lines)} lines spoken", flush=True)
    print("hearing every word's time (Whisper; its model is fetched the first time)", flush=True)
    words = timed_words(wav, lines, spans)
    seconds = spans[-1][1] + 0.6
    (out / "words.json").write_text(json.dumps({
        "seconds": round(seconds, 3),
        "lines": [{"text": l, "start": round(s, 3), "end": round(e, 3)} for l, (s, e) in zip(lines, spans)],
        "words": words}, indent=1))
    print(f"{len(lines)} lines, {len(words)} words, {seconds:.1f} s")


if __name__ == "__main__":
    main()
