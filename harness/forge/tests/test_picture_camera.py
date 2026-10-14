"""A labelled picture follows the narration: each label comes on as its part is said, with a box round the part,
and where the narration stays on a part the camera moves in on it (a sharp crop of the part grows out of its box to
fill the picture's frame), moves on to the next part named, and draws back out when the narration moves on."""

from __future__ import annotations

import numpy as np
import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import pocket_lecture as pl  # noqa: E402


def _timed(text: str, per_word: float = 0.4) -> list[dict]:
    return [{"w": w, "start": round(i * per_word, 3), "end": round(i * per_word + 0.35, 3)}
            for i, w in enumerate(text.split())]


def _probe():
    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    log, clock = [], [0.0]
    real_play = scene.play

    def play(*anims, run_time=1.0, **kw):
        log.append((round(clock[0], 2), round(run_time, 2), anims))
        clock[0] += run_time
        real_play(*anims, run_time=0.05, **kw)

    def wait(t=1.0, **kw):
        clock[0] += t

    scene.play, scene.wait = play, wait
    return scene, log, clock


@pytest.fixture
def photo(tmp_path):
    from PIL import Image

    path = tmp_path / "heart.png"
    pixels = np.zeros((400, 600, 3), dtype=np.uint8)
    pixels[:, :300] = (200, 40, 40)
    pixels[:, 300:] = (40, 40, 200)
    Image.fromarray(pixels).save(path)
    return str(path)


LABELS = [("left atrium", 0.25, 0.25, 0.15, 0.15, 0.35, 0.35), ("aorta", 0.75, 0.2, 0.65, 0.1, 0.85, 0.3),
          ("right ventricle", 0.3, 0.75, 0.2, 0.65, 0.4, 0.85)]


def _baked(anim) -> bool:
    todo = [anim]
    while todo:
        a = todo.pop()
        if getattr(a, "_panim_bake", False):
            return True
        todo.extend(getattr(a, "animations", None) or [])
    return False


def _on(scene, mob) -> bool:
    return any(mob is m for top in scene.mobjects for m in top.get_family())


def test_labels_come_on_their_words_and_the_camera_moves_in(monkeypatch, photo):
    monkeypatch.setattr(pl, "voice_mode", lambda: "gemini:Achird")
    monkeypatch.setattr(pl, "line_words", lambda text: _timed(text))
    line = "Blood comes into the left atrium first, and much later it leaves through the great aorta at the top."
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 0.4 * len(text.split()) + 0.4))
    scene, log, clock = _probe()
    scene.beat(line, scene.stage_image(photo, "The heart", labels=LABELS))
    starts = [t for t, _, _ in log]
    # The picture as the line begins; "left atrium" (word 5, 1.6 s) and "aorta" (word 15, 6.0 s) on their words,
    # each with the camera moving in (a baked clip on the phone); the unsaid "right ventricle" after the picture.
    assert starts[0] == 0.0
    timed = {round(t, 1) for t, _, anims in log if any(_baked(a) for a in anims)}
    assert 1.4 in timed and 5.8 in timed, log
    view = scene._views[-1]
    assert view["zoom"] == "aorta" and view["revealed"] == {"left atrium", "aorta", "right ventricle"}
    lens = view["lens"]
    # The camera's view fills the picture's frame, and only the part it is on is named by a line to it.
    image = view["image"]
    assert lens.width == pytest.approx(image.width, rel=0.02) and lens.height == pytest.approx(image.height, rel=0.02)
    assert not any(_on(scene, m) for n in view["parts"] for m in scene._pointer_pieces(view["parts"][n]))
    assert pl.sync_counts([0]).get("looked", 0) >= 2 or scene._views


def test_the_camera_draws_out_when_the_narration_moves_on_and_back_in_when_a_part_is_named(monkeypatch, photo):
    monkeypatch.setattr(pl, "voice_mode", lambda: "gemini:Achird")
    monkeypatch.setattr(pl, "line_words", lambda text: _timed(text))
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 0.4 * len(text.split()) + 0.4))
    scene, log, clock = _probe()
    scene.beat("This is the left atrium, a small chamber at the top of the heart.",
               scene.stage_image(photo, "The heart", labels=LABELS))
    view = scene._views[-1]
    assert view["zoom"] == "left atrium"
    scene.beat("The heart beats about seventy times every single minute of the day.")
    assert view["zoom"] is None and view["lens"] is None
    frame = view["parts"]["left atrium"]["frame"]
    assert _on(scene, frame)                                 # every label's box and line back on the whole picture
    log.clear()
    began = clock[0]
    scene.beat("Now look closely at the strong right ventricle below it.")
    assert view["zoom"] == "right ventricle"
    camera = [t - began for t, _, anims in log if any(getattr(a, "panim_camera", False) for a in anims)]
    assert camera and camera[0] == pytest.approx(0.4 * 6 - pl.SYNC_LEAD, abs=0.05)


def test_without_word_times_the_labels_follow_the_picture(monkeypatch, photo):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 5.0))
    scene, log, clock = _probe()
    scene.beat("The heart has four chambers.", scene.stage_image(photo, "The heart", labels=LABELS))
    starts = [t for t, _, _ in log]
    assert starts[0] == 0.0 and len(starts) == 4 and all(b > a for a, b in zip(starts, starts[1:]))
    assert scene._views[-1]["zoom"] is None                  # the camera moves only with the words


def test_a_moving_picture_keeps_its_labels_still(monkeypatch, photo):
    monkeypatch.setattr(pl, "voice_mode", lambda: "gemini:Achird")
    monkeypatch.setattr(pl, "line_words", lambda text: _timed(text))
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 8.0))
    scene, log, clock = _probe()
    scene.beat("This is the left atrium, a small chamber at the very top.",
               scene.stage_image(photo, "The heart", labels=LABELS, move="bob"))
    assert scene._views[-1]["zoom"] is None


def test_the_compiler_asks_for_each_label_to_be_said_while_its_picture_is_up():
    import json

    import compile_lecture as cl

    script = {"title": "Heart", "style": "lab", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "The heart", "map": False, "beats": [
            {"say": "Here is the heart, with its left atrium at the top.",
             "do": [{"op": "draw", "id": "h", "what": "a human heart in section",
                     "labels": ["left atrium", "aorta", "right ventricles"]}]},
            {"say": "The right ventricle pumps blood to the lungs."}]}]}
    errors, warnings = cl.lint(json.loads(json.dumps(script)))
    said = [w for w in warnings if "never said" in w]
    assert len(said) == 1 and "'aorta'" in said[0] and "left atrium" not in said[0] and "ventricle" not in said[0]
