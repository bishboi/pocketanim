"""What keeps the screen clean and the voice even: strays (what no layout holds) are cleared as a line begins and
when the stage changes; a line's own silence at either end is cut to a breath; the backdrop drifts, in the video
and, from one `drift` line, on the phone."""

from __future__ import annotations

import json
import wave

import numpy as np

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import pocket_lecture as pl  # noqa: E402


def _scene(monkeypatch):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 2.0))

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    real = scene.play
    scene.play = lambda *a, run_time=1.0, **k: real(*a, run_time=0.05, **k)
    scene.wait = lambda *a, **k: None
    return scene


def _on(scene, mob) -> bool:
    return any(mob is m for top in scene.mobjects for m in top.get_family())


def test_a_stray_is_cleared_as_the_next_line_begins(monkeypatch):
    scene = _scene(monkeypatch)
    stray = pl.T("left behind", 28).move_to([0, 1, 0])
    scene.add(stray)                                   # on the screen, held by no layout
    held = scene.quote("Nature is pleased with simplicity.", "Newton")
    scene.beat("A quote.", held)
    assert not _on(scene, stray) and scene.stage_body is not None and not scene.strays()
    assert pl.sync_counts().get("cleared", 0) >= 1


def test_the_stage_and_strip_are_not_strays(monkeypatch):
    scene = _scene(monkeypatch)
    scene.beat("A title.", scene.panel_title("Forces"))
    scene.beat("A card.", scene.define("Force", "A push or a pull."))
    assert scene.strays() == []


def _write(path, rate, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((samples * 20000).astype("<i2").tobytes())


def test_a_lines_silence_is_cut_and_its_words_moved_to_match(tmp_path, monkeypatch):
    rate = 16000
    t = np.arange(rate) / rate
    line = np.concatenate([np.zeros(rate // 2), np.sin(2 * np.pi * 220 * t), np.zeros(int(rate * 0.6))])
    wav = tmp_path / "line.wav"
    _write(wav, rate, line)
    path, lead, seconds = pl._tight(wav)
    assert abs(lead - (0.5 - pl.LEAD_KEPT)) < 0.01 and abs(seconds - (1.0 + pl.LEAD_KEPT + pl.TAIL_KEPT)) < 0.02
    assert pl._tight(wav)[0] == path                                    # made once, then read back
    monkeypatch.setattr(pl, "voice_mode", lambda: "gemini:Achird")
    monkeypatch.setattr(pl, "audio_file", lambda mode, spoken: wav)
    pl.words_file(wav).write_text(json.dumps([{"w": "Hello", "start": 0.6, "end": 0.9}]))
    words = pl.line_words("Hello")
    assert abs(words[0]["start"] - (0.6 - lead)) < 1e-3


def test_the_backdrop_drifts_and_the_phone_is_told_how(tmp_path):
    parts, still = pl.backdrop()
    if not len(parts):
        return
    before = parts.get_center().copy()
    for _ in range(90):
        for u in parts.updaters:
            u(parts, 1 / 30)
    assert np.linalg.norm(parts.get_center() - before) > 0.01           # it moved, slowly
    assert all(getattr(m, "_panim_drift", None) for m in parts.get_family())
    assert not any(getattr(m, "_panim_drift", None) for m in still.get_family())


def test_the_reference_player_moves_a_drifting_backdrop_by_the_clock():
    from dsl.interpret import drift_at

    a, b = drift_at(0.0, **pl.DRIFT), drift_at(6.5, **pl.DRIFT)
    assert a != b and drift_at(6.5, **pl.DRIFT) == pl.drift_at(6.5, **pl.DRIFT)
