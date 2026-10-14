"""A lecture that builds even when one of its pictures cannot be drawn, and an error that says where it happened.

A model's point list of the wrong shape ("points": [1, 2, 3, 4]) reached numpy mid-render and stopped an hour-long
lecture with "IndexError: too many indices for array" and nothing else."""

from __future__ import annotations

import json
import os
import subprocess
import sys


from forge.util import REPO

sys.path.insert(0, str(REPO / "harness" / "lecture"))

import compile_lecture as cl  # noqa: E402
import pocket_lecture as pl  # noqa: E402


def test_point_lists_are_put_in_the_shape_the_engine_draws_from():
    op = {"op": "graph", "items": [{"kind": "data", "points": [1, 2, 3, 4]}],
          "figure": {"items": [{"type": "polygon", "points": [[0, 0, 0], [2, 0, 1], [1, 1, 0]], "at": [1, 2, 0]}]}}
    cl._normalise_points(op)
    assert op["items"][0]["points"] == [[1, 2], [3, 4]]
    assert op["figure"]["items"][0]["points"] == [[0, 0], [2, 0], [1, 1]]
    assert op["figure"]["items"][0]["at"] == [1, 2]


def test_a_picture_that_cannot_be_drawn_is_left_out_and_reported(tmp_path):
    script = {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
              "chapters": [{"title": "c", "beats": [
                  {"say": "Look.", "do": [{"op": "diagram", "id": "s", "kind": "flow",
                                           "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                                           "edges": [["a", "b"]]}]},
                  {"say": "And on.", "do": [{"op": "fact", "text": "still here"}]}]}]}
    source = cl.compile_script(script).replace("[['a', 'b']]", "[['a', 'b'], 7]")   # past the checks, as if unforeseen
    scene = tmp_path / "lecture.py"
    scene.write_text(source)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path / "build")], capture_output=True, text=True, timeout=600,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and not result.get("error")
    assert len(result["skipped"]) == 1 and result["skipped"][0].startswith("chapter 1 beat 1 diagram:")


def test_an_export_error_names_where_it_happened(tmp_path):
    scene = tmp_path / "bad.py"
    scene.write_text("from manim import *\nimport numpy as np\n\n\nclass B(Scene):\n    def construct(self):\n"
                     "        self.play(Create(Circle()))\n        np.array([1, 2])[:, 0]\n")
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), "B",
                          str(tmp_path / "build")], capture_output=True, text=True, timeout=600)
    error = json.loads(out.stdout.strip().splitlines()[-1])["error"]
    assert error.startswith("IndexError") and "(at bad.py:" in error and "in construct" in error


def test_a_title_with_a_line_break_stays_in_its_comment():
    # A chapter title with a break in it carried the rest of the title out of the "# 01  title" comment, and the
    # build stopped at "SyntaxError: invalid syntax (scene.py, line 54)".
    script = {"title": "T", "chapters": [{"title": "Uniform motion\nF = ma \\ net force", "map": False,
                                          "beats": [{"say": "A body keeps moving.", "do": []}]}]}
    source = cl.compile_script(script)
    compile(source, "scene.py", "exec")
    assert "# 01  Uniform motion F = ma \\ net force" in source


def test_a_half_written_narration_is_spoken_again(tmp_path):
    # Prespeak and the build share the narration cache: a wav read while it was being written stopped the build
    # with "EOFError" in wave.py. It is written whole or not at all now, and one that cannot be read is redone.
    import wave

    whole = tmp_path / "whole.wav"
    with wave.open(str(whole), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)
    assert abs(pl._cached_seconds(whole) - 1.0) < 1e-6
    cut = tmp_path / "cut.wav"
    cut.write_bytes(whole.read_bytes()[:30] + b"\x00" * 30)
    assert pl._cached_seconds(cut) is None and not cut.exists()
    assert pl._cached_seconds(tmp_path / "missing.wav") is None


def test_a_lecture_compiled_after_another_does_not_carry_its_pictures():
    # The pictures found for a script were kept for the process: the next lecture compiled in it got the last one's
    # photo credits (an end card it should not have).
    script = {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
              "chapters": [{"title": "c", "map": False, "beats": [{"say": "Hello.", "do": [{"op": "fact", "text": "x"}]}]}]}
    cl.script_photos["photo|left over"] = {"file": "/nowhere.png", "credit": "Someone, CC BY"}
    assert "self.credits(" not in cl.compile_script(json.loads(json.dumps(script)))
