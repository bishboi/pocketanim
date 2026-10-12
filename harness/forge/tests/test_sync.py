"""Pictures in step with the words (Lecture.on_words, spoken_at, compile_lecture.spoken_anchor): an op tied to words of
its line plays as they are spoken, and a part lit for them lets go when the voice moves on."""

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import pocket_lecture as pl  # noqa: E402


LINE = "The lord gave the knight a fief, and the knight paid a fee. Then the peasants worked the land."


def test_a_phrase_is_timed_by_where_it_falls_in_the_line():
    fief = pl.Lecture.spoken_at(LINE, "fief", 10.0)
    fee = pl.Lecture.spoken_at(LINE, "paid a fee", 10.0)
    land = pl.Lecture.spoken_at(LINE, "peasants", 10.0)
    assert 0 < fief[0] < fee[0] < land[0] < 10
    assert fief[1] == fee[1] < land[1] <= 10.0                        # the end of its own sentence
    assert pl.Lecture.spoken_at(LINE, "castle", 10.0) is None
    assert pl.Lecture.spoken_at("दोस्तों, अब किसान की बात करते हैं।", "किसान", 4.0)[0] > 0
    # Punctuation and case in the phrase do not matter.
    assert pl.Lecture.spoken_at(LINE, "The Knight, paid", 10.0) is not None


def _scene():
    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    log, clock = [], [0.0]
    real_play = scene.play

    def play(*anims, run_time=1.0, **kw):
        log.append(("play", round(clock[0], 2), anims))
        clock[0] += run_time
        real_play(*anims, run_time=0.05, **kw)

    def wait(t=1.0, **kw):
        clock[0] += t

    scene.play, scene.wait = play, wait
    return scene, log, clock


def test_a_focus_lands_on_its_word_and_lets_go_when_its_sentence_ends(monkeypatch):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 10.0))
    scene, log, clock = _scene()
    nodes = [{"id": k, "label": k} for k in ("lord", "knight", "fief")]
    scene.beat("Here is how it worked.", scene.diagram("d", "flow", nodes, [["lord", "knight"], ["knight", "fief"]]))
    log.clear()
    clock[0] = 0.0
    lit = scene.on_words("fief", scene.spotlight("d", "fief"))
    scene.beat(LINE, lit)
    start, end = pl.Lecture.spoken_at(LINE, "fief", 10.0)
    plays = [t for kind, t, _ in log if kind == "play"]
    assert abs(plays[0] - (start - scene.ANCHOR_LEAD)) < 0.05           # lit as "fief" is said, not at 0
    assert abs(plays[1] - end) < 0.05                                   # and let go when its sentence is over
    d = scene.diagrams["d"]
    assert d["focus"] is None and d["veils"] == []
    assert clock[0] >= 10.0                                              # the line is never cut short


def test_without_at_everything_plays_as_the_line_begins(monkeypatch):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 10.0))
    scene, log, clock = _scene()
    nodes = [{"id": k, "label": k} for k in ("lord", "knight", "fief")]
    scene.beat("Here is how it worked.", scene.diagram("d", "flow", nodes, [["lord", "knight"], ["knight", "fief"]]))
    log.clear()
    clock[0] = 0.0
    scene.beat(LINE, scene.spotlight("d", "fief"))
    assert [t for kind, t, _ in log if kind == "play"] == [0.0]
    assert scene.diagrams["d"]["focus"] is not None                      # stays lit, as before


def test_the_compiler_ties_an_op_to_its_words_only_when_the_line_says_them():
    assert cl.spoken_anchor({"op": "focus", "at": "fief"}, LINE) == "fief"
    assert cl.spoken_anchor({"op": "focus", "at": "castle"}, LINE) is None
    assert cl.spoken_anchor({"op": "dot", "at": [1, 2]}, LINE) is None        # a place, not words
    script = {"title": "T", "style": "chalkboard", "chapters": [{"title": "A", "beats": [
        {"say": "Here is how it worked.", "do": [{"op": "diagram", "id": "d", "kind": "flow",
                                                  "nodes": [{"id": "l", "label": "Lord"}, {"id": "k", "label": "Knight"},
                                                            {"id": "f", "label": "Fief"}],
                                                  "edges": [["l", "k"], ["k", "f"]]}]},
        {"say": LINE, "do": [{"op": "focus", "diagram": "d", "node": "f", "at": "fief"}]},
        {"say": "Nothing of it here.", "do": [{"op": "focus", "diagram": "d", "node": "k", "at": "castle"}]}]}]}
    code = cl.compile_script(script)
    assert code.count('self.on_words("fief"') == 1 and "castle" not in code


def test_a_lecture_with_words_tied_to_its_pictures_plays_on_the_phone(tmp_path):
    """Tied to words, a beat plays in several steps (the line's start, each set of words, the letting go): the phone
    gets them as it gets any beat, tier 1."""
    import json
    import os
    import subprocess
    import sys

    from forge.util import REPO

    script = {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "A", "map": False, "beats": [
            {"say": "Here is how it worked.", "do": [{"op": "diagram", "id": "d", "kind": "flow",
                                                      "nodes": [{"id": "l", "label": "Lord"}, {"id": "k", "label": "Knight"},
                                                                {"id": "f", "label": "Fief"}],
                                                      "edges": [["l", "k"], ["k", "f"]]}]},
            {"say": LINE, "do": [{"op": "focus", "diagram": "d", "node": "f", "at": "fief"}]}]}]}
    source = cl.compile_script(script)
    assert "self.on_words(" in source
    scene = tmp_path / "scene.py"
    scene.write_text(source)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path)], capture_output=True, text=True, timeout=900,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [] and not result.get("skipped"), result
