"""Free-form Manim in a lecture (the manim op, harness/lecture/free_check.py): the sandbox's rules, the check that
runs each block before a render, the compiled beat, and the exporter on what such blocks write."""

from __future__ import annotations

import json
import subprocess
import sys

from forge.util import REPO

sys.path.insert(0, str(REPO / "harness" / "lecture"))

import compile_lecture as cl  # noqa: E402
import free_check  # noqa: E402

BUILD = "box = Square(side_length=1.2, color=INK)\nself.play(Create(box))"
MOVE = "copy = Square(side_length=0.8, color=PALETTE['ROSE']).next_to(box, RIGHT)\nself.play(TransformFromCopy(box, copy))"


def _script(*blocks, say="We draw a box on the board and watch it."):
    beats = [{"say": say, "do": [{"op": "manim", "id": "fig", "code": code}]} for code in blocks]
    return {"title": "Free", "style": "chalkboard", "chapters": [{"title": "One", "beats": beats}]}


def test_the_sandbox_refuses_what_a_block_must_not_do():
    assert free_check.check_code(BUILD) == []
    assert free_check.check_code("def arrow(a, b):\n    return Arrow(a, b)\nself.play(GrowArrow(arrow(LEFT, RIGHT)))") == []
    for code, said in [("import os", "no imports"), ("x = ().__class__", "private"), ("open('f')", "open"),
                       ("self.camera.background_color = BLACK", "self.camera"), ("while True:\n    pass", "while"),
                       ("class A:\n    pass", "no classes"), ("eval('1')", "eval"), ("self.play(", "syntax"),
                       ("FadeOut(Group(*self.mobjects))", "self.mobjects")]:
        problems = free_check.check_code(code)
        assert problems and any(said in p for p in problems), (code, problems)


def test_a_manim_beat_compiles_to_a_free_beat_and_shares_its_names(monkeypatch):
    monkeypatch.setenv("PANIM_MANIM_CHECK", "off")
    script = _script(BUILD, MOVE)
    errors, _ = cl.lint(script)
    assert errors == []
    source = cl.compile_script(script)
    assert source.count('self.free("fig", ') == 2 and "self.board()" in source
    # Only op on its beat; code required.
    crowded = _script(BUILD)
    crowded["chapters"][0]["beats"][0]["do"].append({"op": "fact", "text": "a box"})
    assert any("only its manim op" in e for e in cl.lint(crowded)[0])
    empty = _script("  ")
    assert any("needs its code" in e for e in cl.lint(empty)[0])
    assert any("not allowed" in e for e in cl.lint(_script("import os"))[0])


def test_each_block_is_run_before_it_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(free_check, "CACHE", tmp_path)
    assert free_check.verify(_script(BUILD, MOVE)) == []
    errors = free_check.verify(_script(BUILD, "self.play(Create(Circle().move_to([9, 0, 0])))",
                                       "self.play(FadeIn(Square()), run_time=40)", "y = nothing + 1"))
    assert any("beat 2" in e and "off the board" in e for e in errors)
    assert any("beat 3" in e and "run 40.0 s" in e for e in errors)
    assert any("beat 4" in e and "NameError" in e for e in errors)
    assert len(list(tmp_path.glob("*.json"))) == 2          # each id's verdict, cached by its code


TRANSFORMS = '''
from manim import *


class Copies(Scene):
    def construct(self):
        a = Rectangle(width=0.6, height=0.8, color=ORANGE, fill_opacity=0.8).shift(LEFT * 3)
        self.play(FadeIn(a))
        b = Rectangle(width=0.8, height=1.0, color=ORANGE, fill_opacity=0.8).shift(RIGHT * 3)
        self.play(TransformFromCopy(a, b))
        eq = MathTex("T = m g").shift(UP * 2)
        self.play(Write(eq))
        self.play(eq.animate.next_to(b, DOWN, buff=0.4))
        self.wait(0.5)
'''


def test_a_copy_arrives_beside_its_original_and_next_to_is_a_move(tmp_path):
    scene = tmp_path / "scene.py"
    scene.write_text(TRANSFORMS)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), "Copies",
                          str(tmp_path)], capture_output=True, text=True, timeout=600)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1, result["blockers"]
    program = (tmp_path / "dsl" / "generated" / "Copies.panim").read_text()
    sys.path.insert(0, str(REPO))
    from dsl.interpret import parse

    declared = {line.split()[1]: line for line in program.splitlines() if line.startswith("geom ")}
    morph = next(line for line in program.splitlines() if line.startswith("morph "))
    _, ghost, arriving = morph.split()[:3]
    # A copy of the original morphs into the new block: the original is not the one that moves.
    assert ghost not in ("A",) and arriving != ghost and ghost in declared and arriving in declared
    # eq.animate.next_to(b, DOWN): eq moves down onto b's column, as one shift.
    xform = next(line for line in program.splitlines() if line.startswith("xform "))
    dx, dy = (float(v) for v in xform.split("by_xy=")[1].split()[0].split(","))
    assert abs(dx - 3) < 0.05 and dy < -2
    assert parse(program)["timeline"]


PHONE = REPO / "player" / "build" / "classes"


def test_a_lecture_with_free_manim_plays_on_the_phone(tmp_path, monkeypatch):
    """The whole road to the phone: a lecture with manim beats is compiled and exported, the phone's interpreter
    (player/core, the Kotlin that ships) agrees with the reference on its frames, and the zip the web app's
    "Download for the phone" makes is imported by the phone's own code (LibraryImport) and opens."""
    import shutil

    import pytest

    if not (PHONE / "core").is_dir() or not shutil.which("java"):
        pytest.skip("the phone player is not built (player/build.sh)")
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    script = _script(BUILD, MOVE, "self.play(Indicate(copy), box.animate.next_to(copy, LEFT, buff=1))")
    errors, _ = cl.lint(script)
    assert errors == []
    scene = tmp_path / "lecture.py"
    scene.write_text(cl.compile_script(script))
    build = tmp_path / "build"
    env = {**__import__("os").environ, "PANIM_VOICE": "silent"}
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(build)], capture_output=True, text=True, timeout=900, env=env)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1, result["blockers"]
    (build / "player").symlink_to(REPO / "player")
    cross = subprocess.run([sys.executable, "-m", "tools.crosscheck_interpreter", "dsl/generated/GeneratedScene.panim"],
                           cwd=build, capture_output=True, text=True, timeout=900,
                           env={**env, "PYTHONPATH": str(REPO)})
    assert "both interpreters agree" in cross.stdout, cross.stdout + cross.stderr
    subprocess.run([sys.executable, "-m", "tools.build_library", "--source", str(build / "dsl" / "generated"),
                    "--out", str(build / "library")], cwd=REPO, check=True, capture_output=True, timeout=300)
    zipped = shutil.make_archive(str(tmp_path / "Free-abc123"), "zip", str(build), "library")
    classpath = ":".join(str(PHONE / p) for p in ("core", "desktop", "kotlin-stdlib.jar"))
    phone = subprocess.run(["java", "-cp", classpath, "com.pocketanim.desktop.VerifyKt", zipped, "import",
                            str(tmp_path / "phone" / "Free-abc123")], capture_output=True, text=True, timeout=300)
    assert phone.returncode == 0, phone.stdout + phone.stderr
    assert "GeneratedScene" in phone.stdout and " ok" in phone.stdout
    # Every frame, through the phone's renderer: the cross-check compares a few frames, and a verb the phone
    # cannot run crashes only on the frame that reaches it.
    played = subprocess.run(["java", "-cp", classpath, "com.pocketanim.desktop.VerifyKt",
                             str(tmp_path / "phone" / "Free-abc123"), "devicebench"],
                            capture_output=True, text=True, timeout=600)
    assert "GeneratedScene" in played.stdout and "PASS" in played.stdout, played.stdout + played.stderr
