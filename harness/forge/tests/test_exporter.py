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
