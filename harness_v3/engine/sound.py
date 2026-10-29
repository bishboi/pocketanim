"""The soundtrack: the voice, with small sounds where things happen and a quiet music bed under it, ducked while the
voice speaks. Every sound is made here from numbers (no sound files): a soft pop as a thing pops in, a scratch as
one is drawn, a thud as a stamp lands, a chime on a tick, a buzz on a cross, a whoosh as the camera goes to another
shot, a rustle as a page turns.

    mix(score, voice.wav, soundtrack.wav)

A score sets it: `music calm|warm|tense|none` (default: V3_MUSIC, calm), `sound off` (no effects; default V3_SOUND=1).
The same events at the same times in the render and in the player's timeline.
"""

from __future__ import annotations

import math
import os
import wave
from pathlib import Path

import numpy as np

RATE = 22050


def _read(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        n, ch, width, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype={1: np.int8, 2: np.int16, 4: np.int32}[width]).astype(np.float32)
    a /= float(2 ** (8 * width - 1))
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, rate


def _write(path: Path, a: np.ndarray, rate: int) -> None:
    a = np.clip(a, -1.0, 1.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((a * 32767).astype(np.int16).tobytes())


def _env(n: int, attack: float, rate: int, decay: float) -> np.ndarray:
    t = np.arange(n) / rate
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _noise(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n).astype(np.float32)


def _smooth(x: np.ndarray, k: int) -> np.ndarray:
    """A plain moving average (a soft low-pass)."""
    if k <= 1:
        return x
    return np.convolve(x, np.ones(k) / k, mode="same")


# ---------------------------------------------------------------- the small sounds -----------------------------------

def pop(rate: int, seed: int = 0) -> np.ndarray:
    n = int(0.09 * rate)
    t = np.arange(n) / rate
    f = 520 + 900 * (t / t[-1])                         # a quick rising blip
    return 0.55 * np.sin(2 * np.pi * np.cumsum(f) / rate) * _env(n, 0.004, rate, 0.03)


def scratch(rate: int, seed: int = 0) -> np.ndarray:
    n = int(0.35 * rate)
    x = _noise(n, seed) - _smooth(_noise(n, seed), 6)    # a high, papery hiss
    wob = 0.6 + 0.4 * np.sin(np.arange(n) / rate * 2 * np.pi * 14)
    return 0.12 * x * wob * _env(n, 0.03, rate, 0.18)


def thud(rate: int, seed: int = 0) -> np.ndarray:
    n = int(0.35 * rate)
    t = np.arange(n) / rate
    body = np.sin(2 * np.pi * (95 - 40 * t / t[-1]) * t) * _env(n, 0.002, rate, 0.09)
    click = _smooth(_noise(n, seed), 3) * _env(n, 0.0005, rate, 0.012)
    return 0.9 * body + 0.35 * click


def chime(rate: int, seed: int = 0) -> np.ndarray:
    n = int(0.6 * rate)
    t = np.arange(n) / rate
    return 0.32 * (np.sin(2 * np.pi * 1320 * t) + 0.5 * np.sin(2 * np.pi * 1980 * t)) * _env(n, 0.003, rate, 0.18)


def buzz(rate: int, seed: int = 0) -> np.ndarray:
    n = int(0.22 * rate)
    t = np.arange(n) / rate
    sq = np.sign(np.sin(2 * np.pi * 140 * t))
    return 0.16 * _smooth(sq, 8) * _env(n, 0.005, rate, 0.12)


def whoosh(rate: int, seed: int = 0, length: float = 0.7) -> np.ndarray:
    n = int(length * rate)
    t = np.linspace(0, 1, n)
    x = _smooth(_noise(n, seed), 14) - _smooth(_noise(n, seed), 60)
    shape = np.sin(np.pi * t) ** 2                      # swells and fades
    return 0.5 * x * shape


def rustle(rate: int, seed: int = 0) -> np.ndarray:
    n = int(0.9 * rate)
    x = _noise(n, seed) - _smooth(_noise(n, seed), 4)
    grains = (np.random.default_rng(seed + 1).random(n) > 0.997).astype(np.float32)
    grains = np.convolve(grains, np.exp(-np.arange(300) / 40), mode="same")
    shape = np.sin(np.pi * np.linspace(0, 1, n))
    return 0.1 * x * shape + 0.25 * grains * shape * _noise(n, seed + 2)


SOUNDS = {"pop": pop, "scratch": scratch, "thud": thud, "chime": chime, "buzz": buzz, "whoosh": whoosh, "rustle": rustle}


def events(sc) -> list[tuple[float, str]]:
    """When each small sound plays: (seconds, sound), from the score's actions (at most one every 0.12 s)."""
    out = []
    lead = 0.12                                         # actions start a little before their word
    last_shot = None
    for a in sorted(sc.acts, key=lambda a: a.t0):
        how = a.args[0] if a.args else ""
        if a.verb == "in" and how in ("pop", "drop", "grow"):
            out.append((a.t0 - lead + 0.05, "pop"))
        elif a.verb == "in" and how in ("draw", "write"):
            out.append((a.t0 - lead, "scratch"))
        elif a.verb == "stamp":
            out.append((a.t0 - lead + 0.25, "thud"))
        elif a.verb == "tick":
            out.append((a.t0 - lead + 0.2, "chime"))
        elif a.verb == "cross":
            out.append((a.t0 - lead + 0.15, "buzz"))
        elif a.verb == "cam":
            shot = a.target if a.target in sc.shots else None
            via = a.args[a.args.index("via") + 1] if "via" in a.args and a.args.index("via") + 1 < len(a.args) else ""
            if via in ("page", "tear"):
                out.append((a.t0 - 0.35, "rustle"))
            elif shot and last_shot and shot != last_shot or a.target == "wide":
                out.append((a.t0 - 0.35, "whoosh"))
            if shot:
                last_shot = shot
    out.sort()
    kept = []
    for t, s in out:
        if t >= 0 and (not kept or t - kept[-1][0] >= 0.12):
            kept.append((t, s))
    return kept


# ---------------------------------------------------------------- the music bed --------------------------------------

MOODS = {
    # chords as semitones above the key's root, four seconds each; a key and how bright the voices are
    "calm": (57, [(0, 4, 7, 12), (-3, 0, 4, 9), (-7, -3, 0, 5), (-5, -1, 2, 7)], 0.5),     # A: I vi IV V
    "warm": (55, [(0, 4, 7, 11), (-3, 0, 4, 7), (5, 9, 12, 16), (2, 5, 9, 12)], 0.55),     # G: Imaj7 vi7 IV ii
    "tense": (52, [(0, 3, 7, 12), (-4, 0, 3, 8), (-2, 2, 5, 10), (-5, -1, 2, 7)], 0.45),   # E minor: i VI VII v
}


def _note(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def music(seconds: float, mood: str, rate: int) -> np.ndarray:
    """A slow pad of chords (soft tones, each fading into the next) with a low root under them."""
    root, chords, bright = MOODS.get(mood, MOODS["calm"])
    n = int(seconds * rate)
    out = np.zeros(n, dtype=np.float32)
    span = 4.0
    k = 0
    t0 = 0.0
    while t0 < seconds:
        chord = chords[k % len(chords)]
        m = int(min(span + 1.5, seconds - t0 + 1.5) * rate)
        t = np.arange(m) / rate
        env = np.minimum(1, t / 1.2) * np.clip((span + 1.5 - t) / 1.5, 0, 1)      # slow in, overlapping out
        tone = np.zeros(m, dtype=np.float32)
        for s in chord:
            f = _note(root + s)
            tone += np.sin(2 * np.pi * f * t) + bright * 0.3 * np.sin(2 * np.pi * 2 * f * t + 0.5)
        tone += 0.8 * np.sin(2 * np.pi * _note(root + chord[0] - 12) * t)      # the root an octave down
        tone *= (1 + 0.04 * np.sin(2 * np.pi * 0.25 * t)) * env / (len(chord) + 1)
        a = int(t0 * rate)
        b = min(n, a + m)
        out[a:b] += tone[: b - a]
        t0 += span
        k += 1
    return out


def duck(voice: np.ndarray, rate: int) -> np.ndarray:
    """How loud the music may be at each moment: down while the voice speaks, back up in its pauses (eased)."""
    win = int(0.05 * rate)
    pad = (-len(voice)) % win
    v = np.abs(np.concatenate([voice, np.zeros(pad, dtype=np.float32)])).reshape(-1, win).mean(axis=1)
    speaking = (v > max(0.01, np.percentile(v, 60) * 0.35)).astype(np.float32)
    g = np.empty_like(speaking)
    level = 1.0
    for i, s in enumerate(speaking):
        target = 0.35 if s else 1.0
        level += (target - level) * (0.5 if target < level else 0.08)   # down fast, up slowly
        g[i] = level
    return np.repeat(g, win)[: len(voice)]


# ---------------------------------------------------------------- the mix --------------------------------------------

def mix(sc, voice_path: Path, out_path: Path) -> dict:
    """The voice with the small sounds and the music under it, written to `out_path`. Says what went in."""
    voice, rate = _read(voice_path)
    seconds = max(len(voice) / rate, float(getattr(sc, "end", 0.0)) + 3.2)
    n = int(seconds * rate)
    out = np.zeros(n, dtype=np.float32)
    out[: len(voice)] += voice
    sound = getattr(sc, "sound", None)
    sound = (os.environ.get("V3_SOUND", "1") != "0") if sound is None else sound
    mood = getattr(sc, "music", None) or os.environ.get("V3_MUSIC", "calm")
    told = {"sounds": 0, "music": mood if mood != "none" else None}
    if sound:
        for i, (t, name) in enumerate(events(sc)):
            s = SOUNDS[name](rate, seed=i)
            a = int(t * rate)
            b = min(n, a + len(s))
            if a < n:
                out[a:b] += 0.35 * s[: b - a]
                told["sounds"] += 1
    if mood != "none":
        bed = music(seconds, mood, rate)
        g = duck(np.concatenate([voice, np.zeros(n - len(voice), dtype=np.float32)]), rate)
        fade = np.minimum(1, np.arange(n) / (2.0 * rate)) * np.minimum(1, (n - np.arange(n)) / (2.5 * rate))
        out += 0.15 * bed * g * fade
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 0.98:
        out *= 0.98 / peak
    _write(out_path, out, rate)
    return told
