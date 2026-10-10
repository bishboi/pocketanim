"""STEM boards: presets, sketches, graphs, worked solutions and problems -- lint, compile and the engine's build."""

from __future__ import annotations

import json
import os

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import stem  # noqa: E402


def _lecture(beats, **extra):
    return {"title": "Forces", "style": "blueprint", "auto_visuals": False, "place_figures": False, **extra,
            "chapters": [{"title": "Slopes", "narration": "Chapter one.", "beats": beats}]}


@pytest.mark.parametrize("kind", stem.PRESETS)
def test_every_preset_names_its_parts(kind):
    elements = stem.preset_elements(kind, {})
    ids = stem.element_ids(elements)
    assert ids and len(ids) == len(set(ids))
    assert all(e["type"] in stem.PRIMITIVES | {"group"} for e in elements)


def test_lint_checks_parts_and_reveals():
    ok = _lecture([{"say": "A block on a ramp.", "do": [{"op": "incline", "id": "r", "show": ["wedge", "block"]}]},
                   {"say": "Its weight.", "do": [{"op": "reveal", "diagram": "r", "nodes": ["mg"]}]},
                   {"say": "Write it down.", "do": [{"op": "work", "id": "w", "lines": ["F = ma"]}]}])
    assert cl.lint(ok)[0] == []
    bad = _lecture([{"say": "A block.", "do": [{"op": "incline", "id": "r", "show": ["wedgie"]}]}])
    assert any("fixed:" in w and "no part 'wedgie'" in w for w in cl.lint(bad)[1])
    wrong = _lecture([{"say": "A block.", "do": [{"op": "incline", "id": "r"}]},
                      {"say": "Its weight.", "do": [{"op": "reveal", "diagram": "r", "nodes": ["weight"]}]}])
    errors, warnings = cl.lint(wrong)                   # a reveal of nothing it has is left out
    assert not errors and any("left out 'reveal'" in w for w in warnings) and wrong["chapters"][0]["beats"][1]["do"] == []
    graph = _lecture([{"say": "A graph.", "do": [{"op": "graph", "id": "g", "items": [{"kind": "curve", "expr": "y+"}]}]}])
    assert cl.lint(graph)[0]
    problem = _lecture([{"say": "A problem.", "do": [{"op": "problem", "id": "p", "text": "Find a.",
                                                     "figure": {"op": "pulley", "show": ["pulley"]}}]},
                        {"say": "Forces.", "do": [{"op": "reveal", "diagram": "p_figure", "nodes": ["T1"]}]},
                        {"say": "Solve.", "do": [{"op": "work", "id": "p", "lines": ["a = 2"], "box": True}]}])
    assert cl.lint(problem)[0] == []


def test_every_chapter_without_a_map_is_a_board_and_steps_stay_in_their_paragraph():
    beats = [{"say": "A ramp.", "paragraph": True, "do": [{"op": "incline", "id": "r"}]}] + \
            [{"say": f"Step {n}.", "do": [{"op": "work", "id": "w", "lines": [f"x = {n}"]}]} for n in range(8)]
    source = cl.compile_script(json.loads(json.dumps(_lecture(beats))))
    assert "self.board()" in source and "self.add_panel()" not in source
    assert "self.clear_stage()" not in source          # a long build is never cut into paragraphs
    assert "self.preset(" in source and source.count("self.work(") == 8
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
    for kind in stem.PRESETS:
        assert scene.preset(kind, kind, {}) is not None
    scene.graph("g", {"x": [0, 4], "items": [{"id": "c", "kind": "curve", "expr": "x^2"},
                                             {"id": "p", "kind": "point", "at": [2, 4]},
                                             {"id": "a", "kind": "area", "expr": "x^2", "x": [0, 2]},
                                             {"id": "t", "kind": "tangent", "expr": "x^2", "at": 1}], "show": ["c"]})
    assert scene.reveal_nodes("g", ["p", "a"]) is not None
    assert scene.work("w", ["v = u + at", "Put in the numbers"], title="Solution") is not None   # moves the graph aside
    assert scene.work("w", ["v = 12"], box=True) is not None
    assert scene.problem("p", "A ball is thrown at 20 m/s at 30 degrees. Find its range.", given=["u = 20 m/s"],
                         find="R", figure={"op": "projectile", "angle": 30, "show": ["ground", "path"]}) is not None
    assert scene.reveal_nodes("p_figure", ["u", "R"]) is not None
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
    assert result["tier"] == 3 and all(b.startswith("raster image") for b in result["blockers"]), result
    preview = subprocess.run([sys.executable, str(REPO / "harness/scripts/scene_ir.py"), str(out), "S"],
                             capture_output=True, text=True, env=env, timeout=600)
    assert '"mode": "2d"' in preview.stdout and "error" not in preview.stdout, preview.stdout + preview.stderr
