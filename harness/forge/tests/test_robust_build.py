"""A lecture that builds even when one of its pictures cannot be drawn, and an error that says where it happened.

A model's point list of the wrong shape ("points": [1, 2, 3, 4]) reached numpy mid-render and stopped an hour-long
lecture with "IndexError: too many indices for array" and nothing else."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np

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
    assert cl._point_problems({"op": "sketch", "items": [{"id": "c", "type": "curve", "points": [[1, 1]]}]})
    assert not cl._point_problems({"op": "sketch", "items": [{"type": "curve", "points": [[1, 1], [2, 2]]}]})


def test_a_constant_expression_has_a_value_for_every_x():
    f = pl.safe_function("4")
    xs = np.linspace(0, 1, 5)
    assert f(xs).shape == xs.shape and float(f(2.0)) == 4.0


def test_a_picture_that_cannot_be_drawn_is_left_out_and_reported(tmp_path):
    script = {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
              "chapters": [{"title": "c", "beats": [
                  {"say": "Look.", "do": [{"op": "sketch", "id": "s",
                                           "items": [{"id": "c", "type": "curve", "points": [[0, 0], [1, 1]]}]}]},
                  {"say": "And on.", "do": [{"op": "fact", "text": "still here"}]}]}]}
    source = cl.compile_script(script).replace("[[0, 0], [1, 1]]", "[]")     # past the checks, as if unforeseen
    scene = tmp_path / "lecture.py"
    scene.write_text(source)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path / "build")], capture_output=True, text=True, timeout=600,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and not result.get("error")
    assert len(result["skipped"]) == 1 and result["skipped"][0].startswith("chapter 1 beat 1 sketch:")


def test_an_export_error_names_where_it_happened(tmp_path):
    scene = tmp_path / "bad.py"
    scene.write_text("from manim import *\nimport numpy as np\n\n\nclass B(Scene):\n    def construct(self):\n"
                     "        self.play(Create(Circle()))\n        np.array([1, 2])[:, 0]\n")
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), "B",
                          str(tmp_path / "build")], capture_output=True, text=True, timeout=600)
    error = json.loads(out.stdout.strip().splitlines()[-1])["error"]
    assert error.startswith("IndexError") and "(at bad.py:" in error and "in construct" in error
