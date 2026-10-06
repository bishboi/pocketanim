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


def test_a_long_lecture_goes_to_the_browser_in_segments_that_draw_the_same(tmp_path):
    """Past PANIM_IR_SEGMENT_OVER bytes the geometry is cut into segments ("This film is too long to send as one
    picture" was a scrub-only preview with no voice): every frame drawn from its segment is the frame of the whole."""
    scene = tmp_path / "scene.py"
    scene.write_text(LECTURE.replace("{aside}", ""))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), "Slide",
                          str(tmp_path)], capture_output=True, text=True, timeout=600,
                         env={**__import__("os").environ, "PANIM_VOICE": "silent"})
    assert json.loads(out.stdout.strip().splitlines()[-1])["tier"] == 1
    script = str(REPO / "harness" / "scripts" / "scene_ir.py")
    subprocess.run([sys.executable, script, str(tmp_path), "Slide"], capture_output=True, text=True, timeout=600)
    whole = json.loads((tmp_path / "scene_ir.json").read_text())
    sys.path.insert(0, str(REPO / "harness" / "scripts"))
    import scene_ir

    parts = scene_ir.segments(whole, 7)
    assert len(parts) > 2 and sum(p["frames"] for p in parts) == whole["frames"]

    def drawn(scene, shapes, index):
        cursor = index
        for count, pieces in scene["runs"]:
            if cursor < count:
                return [(shapes[row[0]], row[1:]) for p in pieces for row in scene["pieces"][p]]
            cursor -= count
        return []

    for index in range(whole["frames"]):
        part = next(p for p in reversed(parts) if p["start"] <= index)
        assert drawn(part, part["shapes"], index - part["start"]) == drawn(whole, whole["shapes"], index)
    # And the script writes them, with an index the page loads first.
    small = subprocess.run([sys.executable, script, str(tmp_path), "Slide"], capture_output=True, text=True,
                           timeout=600, env={**__import__("os").environ, "PANIM_IR_SEGMENT_OVER": "1"})
    summary = json.loads(small.stdout.strip().splitlines()[-1])
    index = json.loads((tmp_path / "scene_ir.json").read_text())
    assert summary["segments"] == len(index["segments"]) >= 1 and index["pieces"] == []
    assert (tmp_path / "scene_ir_0.json").is_file()


def test_a_diagram_set_moving_moves_its_parts_in_the_program_and_brings_them_back(tmp_path):
    """The block slides down the wedge and back. Moved out of the drawing it was baked into, a part left its copy
    behind (two blocks), and a there-and-back move lost its rate (the block stayed at the bottom)."""
    sys.path.insert(0, str(REPO / "harness" / "lecture"))
    import compile_lecture as cl

    beats = [{"say": "A block rests on a smooth wedge.", "do": [{"op": "incline", "id": "ramp", "angle": 30,
                                                                  "forces": ["mg", "N"]}]},
             {"say": "Watch it slide down the slope.", "do": [{"op": "motion", "diagram": "ramp"}]},
             {"say": "And the pendulum swings.", "do": [{"op": "pendulum", "id": "pen", "angle": 25}]},
             {"say": "Watch it swing.", "do": [{"op": "motion", "diagram": "pen"}]}]
    script = {"title": "Motion", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
              "chapters": [{"title": "Motion", "narration": "Chapter one.", "beats": beats}]}
    scene = tmp_path / "scene.py"
    scene.write_text(cl.compile_script(json.loads(json.dumps(script))))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path)], capture_output=True, text=True, timeout=900,
                         env={**__import__("os").environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [], result
    program = result["program"]
    slides = [line for line in program.splitlines() if line.startswith("xform ")]
    swings = [line for line in program.splitlines() if line.startswith("rotate ")]
    assert slides and all("rate=there_and_back" in line for line in slides)       # block, mg and N, there and back
    assert len(swings) >= 2 and all("rate=there_and_back" in line for line in swings)
    assert "morph" not in program                                                    # no moved copy of a part


NESTED = '''
from manim import *


class Nested(Scene):
    def construct(self):
        a, b, c = Square().shift(LEFT * 3), Circle(), Triangle().shift(RIGHT * 3)
        # A group inside a Succession, and a group inside a group: both were "unsupported animation:
        # AnimationGroup" (tier 3); only a play's own groups were unwrapped.
        self.play(Succession(AnimationGroup(Create(a), FadeIn(b)), FadeOut(a)))
        self.play(AnimationGroup(AnimationGroup(Create(c), b.animate.shift(UP)), FadeIn(a)))
        self.wait(0.5)
'''


def test_nested_animation_groups_are_tier_one_and_both_interpreters_agree(tmp_path):
    import os

    scene = tmp_path / "scene.py"
    scene.write_text(NESTED)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), "Nested",
                          str(tmp_path)], capture_output=True, text=True, timeout=600)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1, result["blockers"]
    program = (tmp_path / "dsl" / "generated" / "Nested.panim").read_text()
    assert "ratio=0" in program
    (tmp_path / "player").symlink_to(REPO / "player")
    cross = subprocess.run([sys.executable, "-m", "tools.crosscheck_interpreter", "dsl/generated/Nested.panim"],
                           cwd=tmp_path, capture_output=True, text=True, timeout=900,
                           env={**os.environ, "PYTHONPATH": str(REPO)})
    assert "both interpreters agree" in cross.stdout, cross.stdout + cross.stderr
