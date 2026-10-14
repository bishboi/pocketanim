"""STEM boards: worked solutions and problems -- lint, compile and the engine's build; the retired built drawings
left out."""

from __future__ import annotations

import json
import os

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402


def _lecture(beats, **extra):
    return {"title": "Forces", "style": "blueprint", "auto_visuals": False, "place_figures": False, **extra,
            "chapters": [{"title": "Slopes", "narration": "Chapter one.", "beats": beats}]}


NODES = [{"id": k, "label": k} for k in ("wedge", "block", "mg")]


def test_lint_checks_parts_and_reveals():
    ok = _lecture([{"say": "A block on a ramp.", "do": [{"op": "diagram", "id": "r", "nodes": NODES,
                                                         "edges": [["wedge", "block"]], "show": ["wedge", "block"]}]},
                   {"say": "Its weight.", "do": [{"op": "reveal", "diagram": "r", "nodes": ["mg"]}]},
                   {"say": "Write it down.", "do": [{"op": "work", "id": "w", "lines": ["F = ma"]}]}])
    assert cl.lint(ok)[0] == []
    wrong = _lecture([{"say": "A block.", "do": [{"op": "diagram", "id": "r", "nodes": NODES, "edges": []}]},
                      {"say": "Its weight.", "do": [{"op": "reveal", "diagram": "r", "nodes": ["weight"]}]}])
    errors, warnings = cl.lint(wrong)                   # a reveal of nothing it has is left out
    assert not errors and any("left out 'reveal'" in w for w in warnings) and wrong["chapters"][0]["beats"][1]["do"] == []
    problem = _lecture([{"say": "A problem.", "do": [{"op": "problem", "id": "p", "text": "Find a."}]},
                        {"say": "Solve.", "do": [{"op": "work", "id": "p", "lines": ["a = 2"], "box": True}]}])
    assert cl.lint(problem)[0] == []


@pytest.mark.parametrize("kind", ["incline", "sketch", "graph", "plot", "sim", "counter", "motion", "trace"])
def test_a_retired_built_drawing_is_left_out_with_a_note(kind):
    script = _lecture([{"say": "A drawing.", "do": [{"op": kind, "id": "x", "diagram": "x"}]},
                       {"say": "Solve.", "do": [{"op": "work", "id": "w", "lines": ["a = 2"]}]}])
    errors, warnings = cl.lint(script)
    assert not errors
    assert any(f"left out {kind!r}" in w and "manim op" in w for w in warnings)
    assert script["chapters"][0]["beats"][0]["do"] == []


def test_a_problem_with_a_retired_figure_keeps_its_question():
    script = _lecture([{"say": "A problem.", "do": [{"op": "problem", "id": "p", "text": "Find a.",
                                                     "figure": {"op": "pulley"}}]}])
    errors, warnings = cl.lint(script)
    assert not errors and any("figure" in w and "no longer built" in w for w in warnings)
    assert "figure" not in script["chapters"][0]["beats"][0]["do"][0]


def test_every_chapter_without_a_map_is_a_board_and_steps_stay_in_their_paragraph():
    beats = [{"say": "A ramp.", "paragraph": True, "do": [{"op": "diagram", "id": "r", "nodes": NODES,
                                                          "edges": [["wedge", "block"]]}]}] + \
            [{"say": f"Step {n}.", "do": [{"op": "work", "id": "w", "lines": [f"x = {n}"]}]} for n in range(8)]
    source = cl.compile_script(json.loads(json.dumps(_lecture(beats))))
    assert "self.board()" in source and "self.add_panel()" not in source
    assert "self.clear_stage()" not in source          # a long build is never cut into paragraphs
    assert "self.diagram(" in source and source.count("self.work(") == 8
    panel = cl.compile_script(json.loads(json.dumps(_lecture(
        [{"say": "Hello.", "do": [{"op": "fact", "text": "a point"}]}], layout="panel"))))
    assert "self.add_panel()" in panel


def test_problems_are_counted_for_a_written_stem_lecture():
    beats = [{"say": f"For example, force fact {n}.", "do": []} for n in range(12)]
    beats[3] = {"say": "Try this.", "do": [{"op": "problem", "id": "p", "text": "Find a."}]}
    errors, _ = cl.lint(_lecture(beats), min_minutes=0.5, min_problems=3)
    assert any("long problem" in e for e in errors)
    assert cl.teaching_plan(20, 2500)["min_problems"] >= 2


def test_a_map_panel_holds_three_short_points():
    beats = [{"say": "Rivers.", "do": [{"op": "river", "name": "Ganges"}, {"op": "panel", "title": "Rivers"}] +
              [{"op": "fact", "text": f"point {n}"} for n in range(4)]}]
    script = _lecture(beats, region={"country": "India", "view": "ind"})
    errors, _ = cl.lint(script, min_minutes=0.1)
    assert any("more than 3 points" in e for e in errors)


def test_the_engine_builds_boards(tmp_path, monkeypatch):
    monkeypatch.setenv("PANIM_VOICE", "silent")
    import pocket_lecture as pl

    class Board(pl.MapLecture):
        def construct(self):
            pass

    scene = Board()
    scene.setup()
    scene.board()
    scene.diagram("g", "flow", NODES, [["wedge", "block"]], show=["wedge"])
    assert scene.reveal_nodes("g", ["block", "mg"]) is not None
    assert scene.work("w", ["v = u + at", "Put in the numbers"], title="Solution") is not None   # moves the diagram aside
    assert scene.work("w", ["v = 12"], box=True) is not None
    assert scene.problem("p", "A ball is thrown at 20 m/s at 30 degrees. Find its range.", given=["u = 20 m/s"],
                         find="R") is not None
    assert scene.work("p", ["R = \\frac{u^2 \\sin 2\\theta}{g}"]) is not None


def test_a_photo_moved_aside_by_working_still_previews(tmp_path, monkeypatch):
    """A photo makes a scene tier 3 (sampled frames), but its preview must still build: the working that moves
    the photo aside once left a step the preview could not play (KeyError on an object name)."""
    import subprocess
    import sys

    from PIL import Image

    from forge.util import REPO

    Image.new("RGB", (40, 30), (200, 80, 60)).save(tmp_path / "photo.png")
    scene = tmp_path / "scene.py"
    scene.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, {str(LECTURE)!r})\n"
        "from manim import *\nfrom pocket_lecture import *\n\n"
        "class S(MapLecture):\n"
        "    def construct(self):\n"
        "        self.board()\n"
        f"        self.beat('Newton.', self.stage_image({str(tmp_path / 'photo.png')!r}, 'Newton'))\n"
        "        self.beat('His law.', self.work('w', ['F = ma'], title='Second law'))\n"
        "        self.beat('So.', self.work('w', ['a = F/m'], box=True))\n")
    env = {**os.environ, "PANIM_VOICE": "silent", "PANIM_AUDIO_DIR": str(tmp_path / "audio")}
    out = tmp_path / "build"
    exported = subprocess.run([sys.executable, str(REPO / "harness/scripts/export_scene.py"), str(scene), "S", str(out)],
                              capture_output=True, text=True, env=env, timeout=600)
    result = json.loads(exported.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [], result
    preview = subprocess.run([sys.executable, str(REPO / "harness/scripts/scene_ir.py"), str(out), "S"],
                             capture_output=True, text=True, env=env, timeout=600)
    assert '"mode": "2d"' in preview.stdout and "error" not in preview.stdout, preview.stdout + preview.stderr
