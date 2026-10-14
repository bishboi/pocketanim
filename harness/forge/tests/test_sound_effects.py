"""Sound effects (harness/lecture/sfx.py): made here, one for each kind of animation, started with it, quiet under
the voice; none in a silent build."""

from __future__ import annotations

import wave

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import pocket_lecture as pl  # noqa: E402
import sfx  # noqa: E402


def test_every_sound_is_made_once_short_and_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("PANIM_AUDIO_DIR", str(tmp_path))
    for kind in sfx.GAIN:
        path = sfx.path(kind)
        with wave.open(path) as w:
            seconds = w.getnframes() / w.getframerate()
        assert 0.02 < seconds <= 2.0, kind
        assert sfx.gain(kind) <= -12                        # under the voice
    assert sfx.path("pop") == sfx.path("pop")


def test_each_animation_gets_the_sound_of_what_it_does():
    from manim import Circle, Create, FadeIn, FadeOut, ImageMobject, ScaleInPlace, Square, Write

    import numpy as np

    photo = ImageMobject(np.zeros((8, 8, 3), dtype=np.uint8))
    assert sfx.classify([FadeIn(Circle())])[0] == "pop"
    assert sfx.classify([FadeIn(photo)])[0] == "whoosh"
    assert sfx.classify([Create(Square())])[0] == "draw"
    assert sfx.classify([Write(pl.T("words", 20))])[0] == "type"
    assert sfx.classify([ScaleInPlace(Circle(), 1.1)])[0] == "tick"
    assert sfx.classify([FadeOut(photo)])[0] == "out"
    tagged = FadeIn(Circle())
    tagged.panim_sfx = "answer"
    assert sfx.classify([Create(Square()), tagged])[0] == "answer"


@pytest.mark.parametrize("voice, made", [("gemini:Achird", True), ("silent", False)])
def test_a_play_starts_its_sound_with_it_but_a_silent_build_stays_silent(tmp_path, monkeypatch, voice, made):
    from manim import Circle, FadeIn

    monkeypatch.setenv("PANIM_AUDIO_DIR", str(tmp_path))
    monkeypatch.delenv("PANIM_SFX", raising=False)
    monkeypatch.setattr(pl, "voice_mode", lambda: voice)

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    added = []
    scene.add_sound = lambda path, gain=None, **k: added.append((path, gain))
    scene.play(FadeIn(Circle()), run_time=0.05)
    assert bool(added) == made
    if made:
        assert added[0][0].endswith(f"pop-v{sfx.VERSION}.wav") and added[0][1] == sfx.gain("pop")
