"""A gallery brings each picture forward as it is said; a diagram is built as its parts are named; the phone's
players ease a fade as the video does; Gemini's voice is marked with a teacher's vocal events."""

from __future__ import annotations

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import pocket_lecture as pl  # noqa: E402


def _probe():
    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    return scene


def test_a_gallery_steps_to_each_picture_as_it_is_said(tmp_path):
    from PIL import Image

    paths = []
    for k, colour in enumerate(((200, 40, 40), (40, 40, 200), (40, 160, 40))):
        path = tmp_path / f"p{k}.png"
        Image.new("RGB", (300, 200), colour).save(path)
        paths.append(str(path))
    scene = _probe()
    scene.gallery([(paths[0], "Red Fort"), (paths[1], "Blue Lake"), (paths[2], "Green Valley")])
    g = scene._gallery
    queue = scene._word_queue
    assert [h.panim_said for h in queue] == ["Blue Lake", "Green Valley"]
    assert queue[0].panim_build(False) is None                       # not said: it waits in the strip
    assert queue[0].panim_build(True) is not None and g["at"] == 1    # said: it comes forward
    assert scene._gallery_step(g, 1) is None                         # already there
    assert scene._gallery_step(g, 0) is not None and g["at"] == 0


def test_a_diagram_is_built_as_its_parts_are_named(monkeypatch):
    monkeypatch.setenv("PANIM_DIAGRAM_STEPS", "1")
    scene = _probe()
    nodes = [{"id": k, "label": k.title()} for k in ("seed", "sapling", "tree")]
    scene.diagram("g", "flow", nodes)
    d = scene.diagrams["g"]
    assert d["shown"] == {"seed"}
    assert [h.panim_said for h in scene._word_queue] == ["Sapling", "Tree"]
    assert scene._word_queue[0].panim_build(True) is not None and "sapling" in d["shown"]


def test_the_players_ease_a_fade_as_the_video_does():
    from dsl.interpret import RATE_FUNCS, parse
    from manim.utils.rate_functions import ease_out_back, ease_out_cubic, ease_out_expo

    for name, fn in (("ease_out_cubic", ease_out_cubic), ("ease_out_back", ease_out_back),
                     ("ease_out_expo", ease_out_expo)):
        assert all(abs(RATE_FUNCS[name](t / 10) - fn(t / 10)) < 1e-9 for t in range(11))
    scene = parse("scene 2d fps=30\nfade A t=0.5 rate=ease_out_back\n")
    assert scene["timeline"][0][-1] == "ease_out_back"


def test_gemini_lines_are_marked_with_a_teachers_vocal_events():
    import voice_director as vd

    line = "Scientists finally understood the shape of DNA."
    assert vd.enabled("gemini") or vd._env("PANIM_VOICE_DIRECTOR") == "off"
    assert vd.acceptable(line, "<breath> Scientists finally understood... the shape of DNA!", "gemini")
    assert not vd.acceptable(line, "<long pause> Scientists finally understood the shape of DNA.", "gemini")
    assert not vd.acceptable(line, "<scream> Scientists finally understood the shape of DNA.", "gemini")
    assert not vd.acceptable(line, "<chuckle> Scientists understood the shape of DNA.", "gemini")    # a word gone
    assert not vd.acceptable(line, "[warm] Scientists finally understood the shape of DNA.", "gemini")
    assert "<chuckle>" in vd.GEMINI_SYSTEM and "<long pause>" not in vd.GEMINI_SYSTEM


def test_a_thing_this_line_takes_away_is_not_pointed_at():
    """A timeline's date said again in the line that replaces it with a comparison: a pulse on it put it back over
    the comparison (a leftover cleared only at the next line)."""
    scene = _probe()
    scene.big_timeline([("1869", "DNA identified"), ("1950s", "Double helix understood")])
    scene.add(*scene.stage_items, *scene.stage_extra)
    scene._sync_beat, scene._beat_new = 5, []                      # the next line
    scene.compare_cards([{"title": "Already known", "points": ["DNA"]},
                         {"title": "1950s breakthrough", "points": ["Its structure"]}])
    words = [{"w": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate("the 1950s changed it all".split())]
    assert scene._pointers(words, 4.0, set()) == []
