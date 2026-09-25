"""Mix the sounds a scene started into one narration track.

A narrated lecture calls ``add_sound`` once per beat. The program has no audio
verb -- audio is fetched beside a scene, not inside it (§5.3) -- so the
exporter records where each sound starts and this lays them on one timeline:
one WAV the browser preview plays against its frames and the phone's
AudioClock follows.

Plain numpy and the ``wave`` module, so it needs nothing Manim does not
already install. 16-bit PCM in, any rate and channel count; 44.1 kHz mono out.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 44100


def _read(path: str) -> np.ndarray:
    with wave.open(path) as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width != 2:
        raise ValueError(f"{path}: {8 * width}-bit audio; expected 16-bit PCM")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != RATE and len(data):
        # Linear resampling. Narration is speech band-limited well under the
        # new Nyquist either way, so nothing audible is lost.
        target = int(round(len(data) * RATE / rate))
        data = np.interp(np.linspace(0, len(data) - 1, target), np.arange(len(data)), data)
    return data.astype(np.float32)


def mix(sounds: list[tuple[float, str, float]], seconds: float, out: Path) -> dict:
    """Place each (start, path, gain_db) and write one track of `seconds`."""
    track = np.zeros(int(round(max(seconds, 0.0) * RATE)) + 1, dtype=np.float32)
    placed = 0
    for start, path, gain in sounds:
        try:
            clip = _read(path)
        except (OSError, ValueError, wave.Error):
            continue
        if gain:
            clip = clip * (10 ** (gain / 20))
        at = int(round(start * RATE))
        if at >= len(track):
            continue
        end = min(len(track), at + len(clip))
        track[at:end] += clip[: end - at]
        placed += 1
    peak = float(np.abs(track).max()) if len(track) else 0.0
    if peak > 0.98:
        track *= 0.98 / peak
    pcm = (np.clip(track, -1, 1) * 32767).astype("<i2")
    with wave.open(str(out), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())
    return {"file": out.name, "clips": placed, "seconds": round(len(pcm) / RATE, 3)}
