"""When each word of a spoken line is said, found on this machine: for a voice that does not say (Gemini, Chirp).

ElevenLabs returns its words' times with the audio (eleven_tts.py). Other voices return only audio, so the line's
own words are aligned to it here, by a small multilingual speech model run locally: Whisper (small by default, about
460 MB, 99 languages, Hindi and English among them; tiny, at 75 MB, timed Hinglish words loosely) through faster-whisper (CTranslate2, CPU). It is not asked what
was said -- it is given the words, and where its attention moves in the audio as it reads each of them gives the
word's start and end (forced alignment, the way faster-whisper times words). A line longer than Whisper's 30 s
window is cut at the pauses near each 28 s and its words shared out by length.

Settings:
  PANIM_LOCAL_ALIGN        off to never align locally (the animations then play as their lines begin)
  PANIM_ALIGN_WHISPER      the model: small (default), tiny or base (quicker, looser), medium or large-v3-turbo
                           (more accurate, larger, slower on a CPU), or a folder
                           holding a CTranslate2 Whisper model
  PANIM_ALIGN_WHISPER_DIR  where a downloaded model is kept (harness/lecture/.cache/whisper)

The first use downloads the model (from Hugging Face, as faster-whisper does); a machine without faster-whisper
or the model aligns nothing, and says why once.

    .venv/bin/python harness/lecture/local_align.py line.wav "The words of the line."
"""

from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

from chirp import _env

HERE = Path(__file__).resolve().parent
RATE = 16000
WINDOW = 28.0              # seconds a piece, inside Whisper's 30 s window
_lock = threading.Lock()
_model = None
_problem: str | None = None


def enabled() -> bool:
    return (_env("PANIM_LOCAL_ALIGN") or "on").strip().lower() not in ("off", "0", "no")


def problem() -> str | None:
    """Why lines cannot be aligned here, once that is known (None: they can, or it has not been tried)."""
    return _problem


def _load():
    """The Whisper model, loaded once (and downloaded the first time); None when it cannot be."""
    global _model, _problem
    with _lock:
        if _model is not None or _problem is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            _problem = "faster-whisper is not installed (pip install faster-whisper)"
            return None
        name = (_env("PANIM_ALIGN_WHISPER") or "small").strip()
        root = _env("PANIM_ALIGN_WHISPER_DIR") or str(HERE / ".cache" / "whisper")
        try:
            _model = WhisperModel(name, device="cpu", compute_type="int8", download_root=root, num_workers=4,
                                  cpu_threads=2)
        except Exception as error:  # noqa: BLE001 -- no network for the first download, a broken folder
            _problem = f"the Whisper model {name!r} could not be loaded: {str(error)[:200]}"
            return None
        return _model


def language_of(text: str) -> str:
    """Whisper's language for a line: Hindi when it has Devanagari (Hinglish too), else what the letters say."""
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    for lang, pattern in (("bn", r"[ঀ-৿]"), ("ta", r"[஀-௿]"), ("te", r"[ఀ-౿]"),
                          ("gu", r"[઀-૿]"), ("pa", r"[਀-੿]"), ("kn", r"[ಀ-೿]"),
                          ("ml", r"[ഀ-ൿ]"), ("ur", r"[؀-ۿ]"), ("zh", r"[一-鿿]"),
                          ("ja", r"[぀-ヿ]"), ("ko", r"[가-힯]"), ("ru", r"[Ѐ-ӿ]")):
        if re.search(pattern, text):
            return lang
    return "en"


def _clean(word: str) -> str:
    return word.strip().strip("\"'“”‘’.,;:!?…—–-()[]")


def _pieces(audio, text: str) -> list[tuple[float, float, str]]:
    """(start, end, words) pieces of at most WINDOW seconds: cut at the quietest moment near each limit, and the
    words shared out by their length."""
    import numpy as np

    total = len(audio) / RATE
    if total <= WINDOW + 1.5:
        return [(0.0, total, text)]
    cuts = [0.0]
    frame = int(0.02 * RATE)
    while total - cuts[-1] > WINDOW + 1.5:
        lo, hi = cuts[-1] + WINDOW - 6.0, cuts[-1] + WINDOW
        a, b = int(lo * RATE), int(hi * RATE)
        window = audio[a:b]
        energy = np.array([float(np.mean(window[i:i + frame] ** 2)) for i in range(0, max(1, len(window) - frame), frame)])
        cuts.append(lo + (int(np.argmin(energy)) * frame) / RATE if len(energy) else hi)
    cuts.append(total)
    words = text.split()
    sizes = [len(w) + 1 for w in words]
    whole = float(sum(sizes)) or 1.0
    groups: list[list[str]] = [[] for _ in range(len(cuts) - 1)]
    before = 0.0
    for word, size in zip(words, sizes):
        middle = (before + size / 2) / whole * total          # where the word falls, by its share of the line
        k = next((i for i in range(len(cuts) - 1) if middle < cuts[i + 1]), len(cuts) - 2)
        groups[k].append(word)
        before += size
    out = [(cuts[k], cuts[k + 1], " ".join(group)) for k, group in enumerate(groups)]
    return [p for p in out if p[2]]


FRAME = 0.02               # seconds a loudness frame
PAUSE = 0.2                # a quiet stretch this long is a pause between words, not a consonant's closure


def pauses(audio) -> list[tuple[float, float]]:
    """The pauses in a line's audio, (start, end) in seconds: stretches of PAUSE or more far quieter than its
    speech."""
    import numpy as np

    n = int(FRAME * RATE)
    if len(audio) < n:
        return []
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    loud = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    speech = float(np.percentile(loud, 90)) if len(loud) else 0.0
    quiet = loud < max(speech * 0.08, 1e-4)
    out, begin = [], None
    for i, q in enumerate(list(quiet) + [False]):
        if q and begin is None:
            begin = i
        elif not q and begin is not None:
            if (i - begin) * FRAME >= PAUSE:
                out.append((begin * FRAME, i * FRAME))
            begin = None
    return out


def snap_to_speech(words: list[dict], audio) -> list[dict]:
    """Words moved out of the pauses: the model's times run each word on until the next one begins, through any
    silence between them (and sometimes past it), and can start the word after a pause inside it. A word a pause
    begins inside ends where the pause begins; a word starting in one starts where it ends."""
    gaps = pauses(audio)
    for w in words:
        for a, b in gaps:
            if a < w["start"] < b:
                w["start"] = round(min(b, max(w["end"], b)), 3)
            if w["start"] < a < w["end"]:
                w["end"] = round(a, 3)            # a pause that begins inside a word ends it
        w["end"] = max(w["end"], w["start"])
    return words


def _read_16k(wav: str | Path):
    """A line's audio as 16 kHz mono floats, with the wave module alone (no Whisper needed)."""
    import wave

    import numpy as np

    with wave.open(str(wav)) as handle:
        channels, width, rate = handle.getnchannels(), handle.getsampwidth(), handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError("not 16-bit")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != RATE and len(data):
        target = int(round(len(data) * RATE / rate))
        data = np.interp(np.linspace(0, len(data) - 1, target), np.arange(len(data)), data).astype(np.float32)
    return data


def estimate(wav: str | Path, text: str) -> list[dict] | None:
    """v2's stand-in when Whisper cannot be had (PANIM_ALIGN_ESTIMATE=off to have none): the line's words shared
    out over its spoken stretches (between its pauses) by their length. Each word is marked "est": an estimate,
    which pocket_lecture.line_words does not keep, so the real aligner times the line once it can."""
    if (_env("PANIM_ALIGN_ESTIMATE") or "on").strip().lower() in ("off", "0", "no"):
        return None
    words = [w for w in (_clean(x) for x in text.split()) if w]
    if not words:
        return None
    try:
        audio = _read_16k(wav)
    except (OSError, ValueError, EOFError):
        return None
    total = len(audio) / RATE
    if total <= 0:
        return None
    spoken, at = [], 0.0
    for a, b in pauses(audio):
        if a > at:
            spoken.append((at, a))
        at = b
    if total > at:
        spoken.append((at, total))
    spoken = spoken or [(0.0, total)]
    voiced = sum(b - a for a, b in spoken)

    def real(t: float) -> float:
        """A time on the voiced stretches laid end to end, as a time in the line."""
        for a, b in spoken:
            if t <= b - a:
                return a + t
            t -= b - a
        return spoken[-1][1]

    weights = [len(w) + 1 for w in words]
    unit = voiced / sum(weights)
    out, at = [], 0.0
    for word, weight in zip(words, weights):
        start, end = real(at + 1e-6), real(at + weight * unit - 1e-6)
        out.append({"w": word, "start": round(start, 3), "end": round(max(start, end), 3), "est": True})
        at += weight * unit
    return out


def align(wav: str | Path, text: str) -> list[dict] | None:
    """The line's words as said, [{"w", "start", "end"}] in seconds into its audio; None when it cannot be done."""
    if not enabled() or not text.strip():
        return None
    model = _load()
    if model is None:
        return estimate(wav, text)
    from faster_whisper import decode_audio
    from faster_whisper.tokenizer import Tokenizer

    audio = decode_audio(str(wav), sampling_rate=RATE)
    language = language_of(text)
    tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task="transcribe", language=language)
    out: list[dict] = []
    for start, end, words in _pieces(audio, text):
        clip = audio[int(start * RATE):int(end * RATE)]
        features = model.feature_extractor(clip)
        frames = min(features.shape[-1], 3000)
        segment = features[:, :3000]
        if segment.shape[-1] < 3000:
            import numpy as np

            segment = np.pad(segment, ((0, 0), (0, 3000 - segment.shape[-1])))
        encoded = model.encode(segment)
        tokens = tokenizer.encode(" " + words.strip())
        found = model.find_alignment(tokenizer, [tokens], encoded, frames)
        for item in found[0] if found else []:
            word = _clean(item["word"])
            if word:
                out.append({"w": word, "start": round(start + float(item["start"]), 3),
                            "end": round(start + float(item["end"]), 3)})
    out = snap_to_speech(out, audio)
    # In order and inside the line, as a later step expects.
    total = len(audio) / RATE
    floor = 0.0
    for w in out:
        w["start"] = round(min(max(w["start"], floor), total), 3)
        w["end"] = round(min(max(w["end"], w["start"]), total), 3)
        floor = w["start"]
    return out or None


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    words = align(sys.argv[1], sys.argv[2])
    if words is None:
        print(f"not aligned: {problem() or 'nothing to align'}")
        return 1
    print(json.dumps(words, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
