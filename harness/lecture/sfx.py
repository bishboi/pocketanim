"""Sound effects for a lecture's animations: made here, in numpy, so nothing is downloaded or licensed.

Short, clean interface sounds in the modern explainer manner, kept well under the voice: a soft pop when a thing
comes on, a tick when something is pointed at, an airy whoosh when a picture arrives or leaves, a rising zoom when
the camera moves in, a pen's swish when a line is drawn, light keys when words are written, a two-note chime for a
question and a brighter one for its answer, a deep sweep between chapters. Each is made once (the same every time,
from a fixed seed) and kept as a WAV in the audio cache; the engine adds it at the moment its animation starts
(Lecture.play), and the exporter mixes it into the phone's track as it does the voice.

    PANIM_SFX=0           no sound effects (a silent build, PANIM_VOICE=silent, has none either; PANIM_SFX=1 adds them)
    PANIM_SFX_GAIN=-3     every effect this many dB louder or quieter (default 0)
"""

from __future__ import annotations

import os
import wave
from pathlib import Path

import numpy as np

RATE = 44100
VERSION = 1            # bump to remake every sound

# How loud each sits under the voice (dB, before PANIM_SFX_GAIN): the voice is near full scale.
GAIN = {"pop": -19, "tick": -21, "ping": -17, "whoosh": -18, "out": -22, "zoom": -16, "draw": -24, "type": -25,
        "question": -15, "answer": -14, "chapter": -13, "intro": -12}


def enabled() -> bool:
    return os.environ.get("PANIM_SFX", "1") != "0"


def gain(kind: str) -> float:
    try:
        extra = float(os.environ.get("PANIM_SFX_GAIN", "0") or 0)
    except ValueError:
        extra = 0.0
    return GAIN.get(kind, -20) + extra


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(RATE * seconds)) / RATE


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    """A quick rise and an exponential fall over n samples."""
    t = np.arange(n) / RATE
    rise = np.clip(t / max(attack, 1e-4), 0, 1)
    return rise * np.exp(-t / max(decay, 1e-4))


def _sweep(f0: float, f1: float, seconds: float) -> np.ndarray:
    """A sine gliding from f0 to f1 (exponentially), phase-continuous."""
    t = _t(seconds)
    freq = f0 * (f1 / f0) ** (t / seconds)
    return np.sin(2 * np.pi * np.cumsum(freq) / RATE)


def _lowpass(x: np.ndarray, cutoff) -> np.ndarray:
    """A one-pole low-pass whose cutoff may change sample by sample (a whoosh's opening and closing)."""
    cutoff = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * cutoff / RATE)
    out = np.empty_like(x)
    y = 0.0
    for i in range(len(x)):
        y += a[i] * (x[i] - y)
        out[i] = y
    return out


def _noise(seconds: float, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(int(RATE * seconds))


def _bell(freq: float, seconds: float, decay: float) -> np.ndarray:
    t = _t(seconds)
    tone = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2.01 * t)
            + 0.12 * np.sin(2 * np.pi * freq * 3.02 * t))
    return tone * _env(len(t), 0.003, decay)


def _whoosh(seconds: float, lo: float, hi: float, rising: bool, seed: int) -> np.ndarray:
    n = int(RATE * seconds)
    p = np.linspace(0, 1, n)
    shape = np.sin(np.pi * p) ** 1.6
    cut = lo + (hi - lo) * (p if rising else 1 - p) ** 1.2
    air = _lowpass(_noise(seconds, seed), cut)
    air -= _lowpass(air, 180.0)                           # no rumble
    return air * shape


def make(kind: str) -> np.ndarray:
    """The sound, as samples in -1..1."""
    if kind == "pop":
        body = _sweep(780, 340, 0.09) * _env(int(RATE * 0.09), 0.002, 0.03)
        click = _lowpass(_noise(0.01, 1), 6000) * _env(int(RATE * 0.01), 0.0005, 0.003)
        out = np.zeros(int(RATE * 0.1))
        out[: len(body)] += body
        out[: len(click)] += 0.4 * click
        return out
    if kind == "tick":
        return np.sin(2 * np.pi * 2600 * _t(0.04)) * _env(int(RATE * 0.04), 0.0005, 0.008)
    if kind == "ping":
        return _bell(1568, 0.5, 0.12) + 0.5 * _bell(2349, 0.5, 0.08)
    if kind == "whoosh":
        return _whoosh(0.45, 400, 5200, True, 2)
    if kind == "out":
        return _whoosh(0.35, 300, 3500, False, 3)
    if kind == "zoom":
        air = _whoosh(0.7, 300, 7000, True, 4)
        sub = _sweep(90, 170, 0.7) * np.sin(np.pi * np.linspace(0, 1, int(RATE * 0.7))) ** 2
        return air + 0.35 * sub
    if kind == "draw":
        n = int(RATE * 0.32)
        scratch = _lowpass(_noise(0.32, 5), 4200) - _lowpass(_noise(0.32, 5), 1400)
        wobble = 0.6 + 0.4 * np.sin(2 * np.pi * 14 * np.arange(n) / RATE)
        return scratch * wobble * np.sin(np.pi * np.linspace(0, 1, n)) ** 0.8
    if kind == "type":
        out = np.zeros(int(RATE * 0.36))
        rng = np.random.default_rng(6)
        for k in range(5):
            at = int(RATE * (0.07 * k + rng.uniform(0, 0.015)))
            key = np.sin(2 * np.pi * rng.uniform(1700, 2300) * _t(0.025)) * _env(int(RATE * 0.025), 0.0005, 0.005)
            out[at:at + len(key)] += key * rng.uniform(0.6, 1.0)
        return out
    if kind == "question":
        a = _bell(880, 0.7, 0.18)
        b = _bell(1318.5, 0.6, 0.2)
        out = np.zeros(int(RATE * 0.85))
        out[: len(a)] += a
        out[int(RATE * 0.13):int(RATE * 0.13) + len(b)] += b
        return out
    if kind == "answer":
        out = np.zeros(int(RATE * 1.0))
        for k, f in enumerate((1046.5, 1318.5, 1568.0)):
            note = _bell(f, 0.8, 0.25)
            at = int(RATE * 0.09 * k)
            out[at:at + len(note)] += note
        return out
    if kind == "chapter":
        air = _whoosh(1.1, 200, 6000, True, 7)
        boom = _sweep(70, 45, 1.1) * _env(int(RATE * 1.1), 0.02, 0.35)
        return air + 0.8 * boom
    if kind == "intro":
        n = int(RATE * 1.8)
        p = np.linspace(0, 1, n)
        riser = _whoosh(1.8, 150, 8000, True, 8) * p
        shimmer = sum(_bell(f, 1.8, 0.5) for f in (1046.5, 1568.0, 2093.0)) * np.clip((p - 0.55) * 3, 0, 1)
        return riser + 0.4 * shimmer
    raise KeyError(kind)


def _cache() -> Path:
    import pocket_lecture as pl

    folder = Path(pl.audio_dir()) / "sfx"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def path(kind: str) -> str | None:
    """The WAV of a sound effect, made the first time it is asked for; None when effects are off."""
    if not enabled() or kind not in GAIN:
        return None
    target = _cache() / f"{kind}-v{VERSION}.wav"
    if not target.exists():
        samples = make(kind)
        peak = float(np.abs(samples).max()) or 1.0
        data = np.clip(samples / peak * 0.89, -1, 1)          # -1 dBFS peak; GAIN sets the level in the mix
        # Each fades in and out over a millisecond or two: no click at either end.
        edge = min(len(data) // 4, int(RATE * 0.002))
        if edge:
            ramp = np.linspace(0, 1, edge)
            data[:edge] *= ramp
            data[-edge:] *= ramp[::-1]
        part = target.with_suffix(f".{os.getpid()}.part")
        with wave.open(str(part), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes((data * 32767).astype("<i2").tobytes())
        os.replace(part, target)
    return str(target)


def classify(animations) -> tuple[str | None, float]:
    """The one sound a play makes, and how far into the play (0 to 1) it starts: the most telling of its animations
    (the camera moving in over a word appearing; a picture arriving over a line being drawn). None for a play that
    should be quiet (a hold, a live loop, an object nudged into place)."""
    from manim import (Create, FadeIn, FadeOut, GrowFromCenter, Indicate, ScaleInPlace, UpdateFromAlphaFunc,
                       Write)
    from manim import ImageMobject

    leaves = []

    def walk(anim):
        subs = getattr(anim, "animations", None)
        leaves.append(anim)
        if subs:
            for sub in subs:
                walk(sub)

    for anim in animations:
        walk(anim)
    kinds = set()
    for anim in leaves:
        tag = getattr(anim, "panim_sfx", None)
        if tag:
            kinds.add(tag)
        if getattr(anim, "panim_camera", False) or isinstance(anim, UpdateFromAlphaFunc) and \
                getattr(anim, "_panim_bake", False):
            kinds.add("zoom")
        if getattr(anim, "panim_xform", False):
            kinds.add("zoom")
        mob = getattr(anim, "mobject", None)
        pictured = mob is not None and any(isinstance(m, ImageMobject) for m in mob.get_family())
        if isinstance(anim, (ScaleInPlace, Indicate)):
            kinds.add("tick")
        elif isinstance(anim, FadeOut):
            kinds.add("out" if pictured or (mob is not None and mob.width > 3) else "")
        elif isinstance(anim, Write):
            kinds.add("type")
        elif isinstance(anim, (FadeIn, GrowFromCenter)):
            kinds.add("whoosh" if pictured else "pop")
        elif isinstance(anim, Create):
            kinds.add("draw")
    for kind in ("intro", "chapter", "answer", "question", "zoom", "whoosh", "ping", "pop", "tick", "draw", "type",
                 "out"):
        if kind in kinds:
            return kind, 0.0
    return None, 0.0
