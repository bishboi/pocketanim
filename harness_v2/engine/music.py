"""A quiet music bed under a lecture's voice (every lecture): made here, by formula, so nothing is fetched or
licensed, and the same moment of the lecture always sounds the same.

The bed is a function of time on the lecture's own clock: a pad of soft chords (four chords, four seconds each,
crossfaded), and for livelier looks plucked notes of the chord in eighths and, for punchy ones, a soft low pulse on
the beat. A line's piece of it (`piece`) is cut from that clock where the line plays, so the pieces laid one after
another are one continuous bed. Each piece is ducked under the line's words: low while a word is said, up a little
in a pause of 0.6 s or more, with 150 ms ramps, so the voice is never covered.

Settings:
  PANIM_MUSIC        off (or 0) for no music; on (default) for the look's mood
  PANIM_MUSIC_GAIN   decibels added to the bed (default 0: -24 dB under the voice, -16 dB in its pauses)
"""

from __future__ import annotations

import hashlib
import os
import wave
from pathlib import Path

import numpy as np

RATE = 22050
UNDER, OVER = -24.0, -16.0     # dB of the bed under the voice and in its pauses
PAUSE = 0.6                    # seconds of quiet between words before the bed comes up
RAMP = 0.15                    # seconds the bed takes to dip or come up
CHORD = 4.0                    # seconds a chord

# A minor, F, C, G: calm, a little hopeful, never resolved, so it loops without an ending.
CHORDS = np.array([[220.00, 261.63, 329.63],
                   [174.61, 220.00, 261.63],
                   [196.00, 261.63, 329.63],
                   [196.00, 246.94, 293.66]])
MOODS = {"calm": dict(pluck=0.0, pulse=0.0, step=0.6),
         "lively": dict(pluck=0.22, pulse=0.0, step=0.3),
         "punchy": dict(pluck=0.18, pulse=0.30, step=0.3125)}


def enabled() -> bool:
    return os.environ.get("PANIM_MUSIC", "on").strip().lower() not in ("off", "0", "no", "none")


def _gain() -> float:
    try:
        return float(os.environ.get("PANIM_MUSIC_GAIN", "0") or 0)
    except ValueError:
        return 0.0


def bed(mood: str, t0: float, seconds: float) -> np.ndarray:
    """The bed from `t0` for `seconds` on the lecture's clock, peak about 1."""
    spec = MOODS.get(mood, MOODS["lively"])
    t = t0 + np.arange(int(round(max(seconds, 0.0) * RATE))) / RATE
    if not len(t):
        return np.zeros(0, dtype=np.float32)
    k = (t // CHORD).astype(int)
    now, nxt = CHORDS[k % len(CHORDS)], CHORDS[(k + 1) % len(CHORDS)]
    blend = np.clip(((t % CHORD) - (CHORD - 0.6)) / 0.6, 0, 1)[:, None]

    def tone(f, tt):
        return np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt)

    # The chord before crossfaded into the next over a chord's last 0.6 s.
    pad = (tone(now, t[:, None]) * (1 - blend) + tone(nxt, t[:, None]) * blend).sum(axis=1)
    pad *= 0.85 + 0.15 * np.sin(2 * np.pi * t / 8.0)
    out = 0.5 * pad / 3.0
    if spec["pluck"]:
        step = spec["step"]
        n = (t // step).astype(int)
        dt = t - n * step
        notes = CHORDS[((n * step) // CHORD).astype(int) % len(CHORDS)]
        order = np.array([0, 1, 2, 1])
        f = notes[np.arange(len(n)), order[n % 4]] * 2.0
        out += spec["pluck"] * (np.sin(2 * np.pi * f * dt) + 0.3 * np.sin(4 * np.pi * f * dt)) * np.exp(-dt * 7.0)
    if spec["pulse"]:
        beat = spec["step"] * 2
        n = (t // beat).astype(int)
        dt = t - n * beat
        phase = 45.0 * dt + 45.0 * (1 - np.exp(-dt * 20.0)) / 20.0
        out += spec["pulse"] * np.sin(2 * np.pi * phase) * np.exp(-dt * 9.0)
    peak = float(np.abs(out).max()) or 1.0
    return (out / max(peak, 1.0)).astype(np.float32)


def ducking(words: list, seconds: float) -> np.ndarray:
    """The bed's gain (linear) through a line: UNDER while its words are said, OVER in pauses of PAUSE or more."""
    n = int(round(max(seconds, 0.0) * RATE))
    level = np.full(n, OVER, dtype=np.float32)
    spans = sorted((max(0.0, float(w["start"]) - 0.1), float(w["end"]) + 0.15) for w in words or [])
    merged: list[list[float]] = []
    for a, b in spans:
        if merged and a - merged[-1][1] < PAUSE:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for a, b in merged:
        level[int(a * RATE):int(b * RATE)] = UNDER
    width = max(1, int(RAMP * RATE))
    level = np.convolve(np.pad(level, (width // 2, width - width // 2 - 1), mode="edge"),
                        np.ones(width) / width, mode="valid")[:n]
    return (10 ** ((level + _gain()) / 20)).astype(np.float32)


def piece(mood: str, t0: float, seconds: float, words: list, cache: Path) -> str | None:
    """A line's piece of the bed, ducked under its words, as a wav file (made once); None when there is none."""
    if not enabled() or seconds <= 0.05:
        return None
    key = hashlib.sha1(repr((mood, round(t0, 3), round(seconds, 3), _gain(),
                             [(round(float(w["start"]), 3), round(float(w["end"]), 3)) for w in words or []]))
                       .encode()).hexdigest()[:16]
    out = cache / f"bed-{key}.wav"
    if out.exists():
        return str(out)
    sound = bed(mood, t0, seconds) * ducking(words, seconds)
    edge = min(len(sound) // 2, int(0.015 * RATE))
    if edge:
        ramp = np.linspace(0, 1, edge, dtype=np.float32)
        sound[:edge] *= ramp
        sound[-edge:] *= ramp[::-1]
    cache.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(f".{os.getpid()}.part")
    with wave.open(str(part), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes((np.clip(sound, -1, 1) * 32767).astype("<i2").tobytes())
    part.replace(out)
    return str(out)
