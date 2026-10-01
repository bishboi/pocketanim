"""The exporter on scenes a model writes: a Transform between a shape and text.

morph matches instances by glyph id; a primitive has none. The exporter used to
emit it anyway, claim tier 1, and ship a program both interpreters crashed on
(KeyError 'glyph_ids'). It is a blocker now, and the partial program still plays.
"""

from __future__ import annotations

import json
import subprocess
import sys

from forge.util import REPO

SCENE = '''
from manim import *


class Mixed(Scene):
    def construct(self):
        t = Text("Rice")
        self.play(Write(t))
        c = Circle(color=GREEN)
        self.play(Transform(t, c))
        self.play(ReplacementTransform(c.copy(), Text("Wheat")))
        self.wait(0.5)
'''


def test_shape_text_transform_is_a_blocker_and_the_program_plays(tmp_path):
    scene = tmp_path / "scene.py"
    scene.write_text(SCENE)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), "Mixed",
                          str(tmp_path)], capture_output=True, text=True, timeout=600)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 3
    assert "Transform between a shape and text or a baked asset" in result["blockers"]
    assert "morph" not in (tmp_path / "dsl" / "generated" / "Mixed.panim").read_text()
    ir = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "scene_ir.py"), str(tmp_path), "Mixed"],
                        capture_output=True, text=True, timeout=600)
    summary = json.loads(ir.stdout.strip().splitlines()[-1])
    assert summary.get("error") is None and summary["frames"] > 0


LECTURE = '''
from manim import *
from pocket_lecture import *


class Slide(MapLecture):
    def construct(self):
        self.board()
        self.beat("First a box.", self.sketch("a", [{"id": "b", "type": "rect", "at": [0, 0], "w": 3, "h": 2,
                                                     "label": "FIRST"}]))
        {aside}
        self.beat("Now a circle replaces it.", self.sketch("c", [{"id": "o", "type": "circle", "at": [0, 0],
                                                                  "r": 1.5, "label": "SECOND"}]))
        self.beat("Hold.")
'''


def _last_frame_instances(tmp_path, source: str) -> tuple[int, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    scene = tmp_path / "scene.py"
    scene.write_text(source)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), "Slide",
                          str(tmp_path)], capture_output=True, text=True, timeout=600,
                         env={**__import__("os").environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1, result
    ir = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "scene_ir.py"), str(tmp_path), "Slide"],
                        capture_output=True, text=True, timeout=600)
    assert json.loads(ir.stdout.strip().splitlines()[-1]).get("error") is None
    data = json.loads((tmp_path / "scene_ir.json").read_text())
    return sum(len(data["pieces"][i]) for i in data["runs"][-1][1]), result["program"]


def test_a_drawing_slid_aside_leaves_with_the_stage(tmp_path):
    """A definition beside a drawing slides the drawing left with .animate, which Manim plays as a Transform
    that keeps the drawing on stage. The program morphed it into its moved copy and hid the original, so the
    stage change that followed faded out the hidden original: the copy stayed on screen for the rest of the
    lecture, under every later picture. The last frame must hold what it holds without the slide."""
    plain, _ = _last_frame_instances(tmp_path / "plain", LECTURE.replace("{aside}", ""))
    slid, program = _last_frame_instances(
        tmp_path / "slid", LECTURE.replace("{aside}", 'self.beat("Beside it.", self.define("Isolated", "no force"))'))
    assert "keep=1" in program
    assert slid == plain
