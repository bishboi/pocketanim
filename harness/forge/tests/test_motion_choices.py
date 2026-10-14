"""How things come on (motion.py): a script chooses an entrance, a text motion and a time per op; the engine picks
quick modern ones otherwise; a gallery brings each picture forward as it is said; a diagram is built as its parts
are named; the phone's players ease a fade as the video does."""

from __future__ import annotations

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import motion  # noqa: E402
import pocket_lecture as pl  # noqa: E402


def test_the_compiler_knows_the_engines_motions():
    assert cl.MOTION_ENTER == motion.ENTER and cl.MOTION_TEXT == motion.TEXT


def test_a_chosen_motion_is_compiled_and_a_wrong_one_left_out():
    call = cl._styled({"op": "fact", "text": "x", "enter": "pop", "text_in": "type", "time": 0.5}, "self.fact('x')")
    assert call == """self.styled(lambda: self.fact('x'), enter="pop", text="type", time=0.5)"""
    assert cl._styled({"op": "fact", "text": "x"}, "self.fact('x')") == "self.fact('x')"
    script = {"title": "T", "chapters": [{"title": "C", "map": False, "narration": "x", "beats": [
        {"say": "One point here.", "do": [{"op": "fact", "text": "x", "enter": "spin", "time": 9}]}]}]}
    notes = cl.mechanical_fixes(script, False)
    op = script["chapters"][0]["beats"][0]["do"][0]
    assert "enter" not in op and op["time"] == 2.5 and any("enter is one of" in n for n in notes)


def test_entrances_are_quick_eased_fades_the_phone_has():
    from manim import Square, Text

    for how in motion.ENTER:
        anim = motion.enter(pl.VGroup(Square(), Square()), how)
        assert anim.run_time <= 1.0 and anim.panim_run == anim.run_time
    words = Text("the heart pumps blood")
    typed = motion.write_text(words, "type")
    assert len(typed.animations) == len(words.submobjects)
    assert len(motion.write_text(words, "words").animations) == 4
    from dsl.export_dsl import RATES

    assert {"ease_out_cubic", "ease_out_back", "ease_out_expo"} <= set(RATES)


def test_styled_sets_the_choice_for_one_op_only():
    seen = []

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.styled(lambda: seen.append(dict(motion.CHOSEN)), enter="zoom", time=0.4)
    assert seen == [{"enter": "zoom", "time": 0.4}] and motion.CHOSEN == {}


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
