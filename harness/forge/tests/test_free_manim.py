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


def test_a_figure_that_goes_on_after_a_question_card_does_not_draw_over_it(tmp_path, monkeypatch):
    # A figure built over beats, a question card between, then more of the figure: the later blocks drew over the
    # card ("Think about it" under "At rest" and the figure's boxes). The card goes; the figure's parts come back.
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    script = _script(BUILD)
    beats = script["chapters"][0]["beats"]
    beats.append({"say": "Must a body stop?", "do": [{"op": "question", "text": "Must a body stop?",
                                                         "answer": "No: it keeps its state."}]})
    beats.append({"say": "No, it need not.", "do": [{"op": "answer"}]})
    beats.append({"say": "We draw a box on the board and watch it.", "do": [{"op": "manim", "id": "fig", "code": MOVE}]})
    scene = tmp_path / "lecture.py"
    seen = tmp_path / "seen.json"
    scene.write_text(cl.compile_script(script) + f'''

class Seen(GeneratedScene):
    def free(self, *a, **kw):
        out = super().free(*a, **kw)
        import json as _json
        texts = [m.text for m in self.get_mobject_family_members() if hasattr(m, "text")]
        boxes = [m for m in self.mobjects for x in m.get_family() if type(x).__name__ == "Square"]
        with open({str(seen)!r}, "a") as f:
            f.write(_json.dumps({{"texts": texts, "squares": len(boxes)}}) + "\\n")
        return out
''')
    env = {**__import__("os").environ, "PANIM_VOICE": "silent",
           "PYTHONPATH": str(REPO / "harness" / "lecture")}
    run = subprocess.run([sys.executable, "-m", "manim", "-ql", "--dry_run", str(scene), "Seen"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=600, env=env)
    assert run.returncode == 0, run.stderr[-2000:]
    first, last = [json.loads(line) for line in seen.read_text().splitlines()]
    assert first["squares"] == 1
    assert not any("Mustabodystop" in t or "keepsitsstate" in t for t in last["texts"]), last["texts"]  # no spaces
    assert last["squares"] == 2                       # the first box came back beside its copy


def test_a_working_goes_beside_a_free_figure_not_over_it(tmp_path, monkeypatch):
    # A ray diagram drawn in free-form Manim, then the working about it: the working was written over the figure.
    # The figure is the stage's drawing now: it moves into the left half, the working takes the right.
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    script = _script("axis = Line(LEFT * 5, RIGHT * 5, color=INK)\nself.play(Create(axis))")
    beats = script["chapters"][0]["beats"]
    beats.append({"say": "Look at two right triangles.",
                  "do": [{"op": "work", "id": "w", "title": "Two right triangles", "lines": ["a = b"]}]})
    scene = tmp_path / "lecture.py"
    seen = tmp_path / "seen.json"
    scene.write_text(cl.compile_script(script) + f'''

class Seen(GeneratedScene):
    def beat(self, *a, **kw):
        out = super().beat(*a, **kw)
        import json as _json
        fig = getattr(self, "_free_group", None)
        line = [m for m in self.get_mobject_family_members() if type(m).__name__ == "MathTex"]
        if fig is None or not line:
            return out
        with open({str(seen)!r}, "w") as f:
            f.write(_json.dumps({{"fig_right": float(fig.get_right()[0]), "fig_bottom": float(fig.get_bottom()[1]),
                                 "work_left": min(float(m.get_left()[0]) for m in line),
                                 "work_top": max(float(m.get_top()[1]) for m in line)}}))
        return out
''')
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PYTHONPATH": str(REPO / "harness" / "lecture")}
    run = subprocess.run([sys.executable, "-m", "manim", "-ql", "--dry_run", str(scene), "Seen"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=600, env=env)
    assert run.returncode == 0, run.stderr[-2000:]
    found = json.loads(seen.read_text())
    # Beside it, or under it when the figure is wide and flat (this one is a single line): never over it.
    assert found["fig_right"] < found["work_left"] or found["fig_bottom"] > found["work_top"], found


def test_a_figure_that_redraws_itself_is_moved_aside_and_exported(tmp_path, monkeypatch):
    # A traced path redraws itself every frame: moved aside for a working, its shape changed during the move, the
    # exporter could not write that, and the whole build stopped. It is frozen before it moves.
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    script = _script("d = Dot(LEFT * 2)\ntr = TracedPath(d.get_center)\nself.add(tr, d)\nself.play(d.animate.shift(RIGHT * 3))")
    script["chapters"][0]["beats"].append(
        {"say": "Now the working.", "do": [{"op": "work", "id": "w", "title": "Working", "lines": ["x = 1"]}]})
    scene = tmp_path / "lecture.py"
    scene.write_text(cl.compile_script(script))
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PANIM_BUILD_WORKERS": "1"}
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path / "build")], capture_output=True, text=True, timeout=900,
                         env=env)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result.get("tier") == 1, (result.get("error"), out.stderr[-1500:])


def test_a_part_swapped_in_a_moved_figure_moves_with_it(tmp_path, monkeypatch):
    # A ray turned into the next one (ReplacementTransform) after the figure had been moved aside and back: the new
    # ray took the old one's place inside the figure's group, was not counted as the figure's, and the next working
    # left it at full size across the shrunk figure and the equations beside it.
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    first = ("water = Rectangle(width=9, height=2.5, fill_opacity=0.3, stroke_width=0).shift(LEFT + DOWN * 1.25)\n"
             "src = Dot(LEFT * 4.5 + DOWN * 2.2)\nr = Arrow(src.get_center(), LEFT * 3 + UP * 1.5, buff=0)\n"
             "self.play(FadeIn(water), FadeIn(src), GrowArrow(r))")
    then = ("r2 = Arrow(src.get_center(), RIGHT * 1.5 + UP * 1.0, buff=0, color=PALETTE['ROSE'])\n"
            "self.play(ReplacementTransform(r, r2))")
    script = _script(first, then)
    beats = script["chapters"][0]["beats"]
    beats.insert(1, {"say": "The critical angle follows.", "do": [{"op": "work", "id": "w", "lines": ["x = 1"]}]})
    beats.append({"say": "In terms of relative index.", "do": [{"op": "work", "id": "w2", "lines": ["y = 2"]}]})
    scene = tmp_path / "lecture.py"
    seen = tmp_path / "seen.json"
    scene.write_text(cl.compile_script(script) + f'''

class Seen(GeneratedScene):
    def beat(self, *a, **kw):
        out = super().beat(*a, **kw)
        import json as _json
        fig = getattr(self, "_free_group", None)
        arrows = [m for m in self.get_mobject_family_members() if type(m).__name__ == "Arrow"]
        if fig is None or not arrows:
            return out
        with open({str(seen)!r}, "w") as f:
            f.write(_json.dumps({{"fig": [float(fig.get_left()[0]), float(fig.get_right()[0]),
                                          float(fig.get_bottom()[1]), float(fig.get_top()[1])],
                                 "arrows": [[float(m.get_left()[0]), float(m.get_right()[0]),
                                             float(m.get_bottom()[1]), float(m.get_top()[1])] for m in arrows]}}))
        return out
''')
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PYTHONPATH": str(REPO / "harness" / "lecture")}
    run = subprocess.run([sys.executable, "-m", "manim", "-ql", "--dry_run", str(scene), "Seen"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=600, env=env)
    assert run.returncode == 0, run.stderr[-2000:]
    found = json.loads(seen.read_text())
    left, right, bottom, top = found["fig"]
    for a in found["arrows"]:
        assert left - 0.05 <= a[0] and a[1] <= right + 0.05 and bottom - 0.05 <= a[2] and a[3] <= top + 0.05, found


def test_a_left_half_figure_is_explained_while_its_working_stays_beside_it(tmp_path, monkeypatch):
    # "area": "left": the figure is drawn in the left half, the working takes the right, and neither moves, so the
    # figure's later blocks point at it (an angle, a ray) while the derivation beside it goes on, line after line.
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    script = _script("axis = Line(LEFT * 6, LEFT * 1, color=INK)\nself.play(Create(axis))",
                     "mark = Dot(LEFT * 3)\nself.play(FadeIn(mark))")
    beats = script["chapters"][0]["beats"]
    beats[0]["do"][0]["area"] = "left"
    beats.insert(1, {"say": "Write the first line.", "do": [{"op": "work", "id": "w", "lines": ["a = b"]}]})
    beats.append({"say": "And the second line.", "do": [{"op": "work", "id": "w", "lines": ["c = d"]}]})
    assert cl.lint(script)[0] == []
    source = cl.compile_script(script)
    assert 'area="left"' in source
    scene = tmp_path / "lecture.py"
    seen = tmp_path / "seen.jsonl"
    scene.write_text(source + f'''

class Seen(GeneratedScene):
    def _seen(self):
        import json as _json
        fig = getattr(self, "_free_group", None)
        lines = [m for m in self.get_mobject_family_members() if type(m).__name__ == "MathTex"]
        with open({str(seen)!r}, "a") as f:
            f.write(_json.dumps({{"fig": [float(fig.get_left()[0]), float(fig.get_right()[0])] if fig else None,
                                 "lines": len(lines)}}) + "\\n")

    def free(self, *a, **kw):
        out = super().free(*a, **kw)
        self._seen()
        return out

    def beat(self, *a, **kw):
        out = super().beat(*a, **kw)
        self._seen()
        return out
''')
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PYTHONPATH": str(REPO / "harness" / "lecture")}
    run = subprocess.run([sys.executable, "-m", "manim", "-ql", "--dry_run", str(scene), "Seen"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=600, env=env)
    assert run.returncode == 0, run.stderr[-2000:]
    rows = [json.loads(line) for line in seen.read_text().splitlines() if '"fig": null' not in line]
    first, *rest = rows
    assert all(r["fig"] == first["fig"] for r in rest)     # never moved
    assert first["fig"][1] < 0                              # in the left half
    assert [r["lines"] for r in rest][-2:] == [1, 2]       # the working stayed through the figure's next block


def test_a_figure_area_is_left_or_full():
    script = _script(BUILD)
    script["chapters"][0]["beats"][0]["do"][0]["area"] = "right"
    assert any("area" in e for e in cl.lint(script)[0])


def test_notes_go_under_a_wide_picture_and_beside_a_tall_one(tmp_path):
    # A working (here notes in words) beside a timeline halved it, and its labels could not be read: a wide picture
    # keeps the board's width along the top, the column under it.
    script = {"title": "T", "style": "lab", "chapters": [{"title": "Era", "map": False, "beats": [
        {"say": "The medieval era.", "do": [{"op": "timeline", "title": "The medieval era",
                                             "events": [["476", "Rome falls"], ["1453", "Constantinople falls"]]}]},
        {"say": "Why these dates.", "do": [{"op": "work", "id": "n", "lines": ["476: the last emperor is removed."]}]},
    ]}]}
    scene = tmp_path / "lecture.py"
    seen = tmp_path / "seen.json"
    scene.write_text(cl.compile_script(script) + f'''

class Seen(GeneratedScene):
    def beat(self, *a, **kw):
        out = super().beat(*a, **kw)
        import json as _json
        if self.works:
            w = next(iter(self.works.values()))
            body = self.stage_body
            with open({str(seen)!r}, "w") as f:
                f.write(_json.dumps({{"body_bottom": float(body.get_bottom()[1]), "body_width": float(body.width),
                                     "line_top": float(w["lines"][0].get_top()[1])}}))
        return out
''')
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PYTHONPATH": str(REPO / "harness" / "lecture")}
    run = subprocess.run([sys.executable, "-m", "manim", "-ql", "--dry_run", str(scene), "Seen"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=600, env=env)
    assert run.returncode == 0, run.stderr[-2000:]
    found = json.loads(seen.read_text())
    assert found["line_top"] < found["body_bottom"], found      # the notes under the timeline
    assert found["body_width"] > 8, found                        # which keeps most of the board's width


def test_a_figure_dropped_from_the_stage_list_still_goes_when_the_stage_clears(tmp_path, monkeypatch):
    # Parts of a free-form figure that something had dropped from the stage's list stayed on screen for the rest of
    # the chapter, and the problem, the working and every later figure were drawn over them. A clear of the stage
    # now takes every part a block drew, wherever it is.
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    script = _script(BUILD)
    script["chapters"][0]["beats"].append({"say": "Now a problem.", "do": [{"op": "problem", "id": "p1",
                                           "text": "Find v.", "given": ["R = 15 cm"], "find": "v"}]})
    scene = tmp_path / "lecture.py"
    seen = tmp_path / "seen.json"
    scene.write_text(cl.compile_script(script) + f'''

class Seen(GeneratedScene):
    def free(self, *a, **kw):
        out = super().free(*a, **kw)
        self.stage_extra = []                  # some path loses the figure from the stage's list
        return out

    def beat(self, *a, **kw):
        out = super().beat(*a, **kw)
        import json as _json
        if self._problem is not None:
            squares = [x for m in self.mobjects for x in m.get_family() if type(x).__name__ == "Square"]
            with open({str(seen)!r}, "w") as f:
                f.write(_json.dumps({{"squares": len(squares)}}))
        return out
''')
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PYTHONPATH": str(REPO / "harness" / "lecture")}
    run = subprocess.run([sys.executable, "-m", "manim", "-ql", "--dry_run", str(scene), "Seen"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=600, env=env)
    assert run.returncode == 0, run.stderr[-2000:]
    assert json.loads(seen.read_text())["squares"] == 0


def _swap_lecture(swaps):
    first = ("a = MathTex('FD', '=', '\\\\frac{CD}{2}').shift(RIGHT * 3)\n"
             "box = SurroundingRectangle(a, color=PALETTE['GOLD'])\nself.play(Write(a), Create(box))")
    then = "b = MathTex('f', '=', '\\\\frac{R}{2}').move_to(a)\n"
    return {"title": "T", "style": "blueprint", "teaching_rules": False, "auto_visuals": False,
            "place_figures": False, "chapters": [
                {"title": f"Swap {k}", "map": False, "beats": [
                    {"say": "Here FD is CD over two.", "do": [{"op": "manim", "id": f"s{k}", "code": first}]},
                    {"say": "So f is R over two.", "do": [{"op": "manim", "id": f"s{k}", "code": then + swap}]},
                    {"say": "That is the result.", "do": [{"op": "manim", "id": f"s{k}", "code": "self.wait(0.5)"}]}]}
                for k, swap in enumerate(swaps)]}


def _chapter_end_ink(tmp_path, name, script, chapters):
    """Ink in the equation's place at the end of each chapter, in the program the editor and the phone play."""
    import numpy as np

    scene = tmp_path / f"{name}.py"
    scene.write_text(cl.compile_script(script))
    build = tmp_path / name
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PANIM_BUILD_WORKERS": "1"}
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(build)], capture_output=True, text=True, timeout=900, env=env)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result.get("tier") == 1, (result.get("error"), out.stderr[-1500:])
    probe = (f"import sys, os, json\nsys.path.insert(0, {str(REPO)!r})\nos.chdir({str(build)!r})\n"
             "from dsl.interpret import load_program\nfrom exporter.reference_render import render_frame\n"
             "ir = load_program('dsl/generated/GeneratedScene.panim')\nn = len(ir.records)\n"
             f"ink = [int((render_frame(ir, int(n * (k + 0.97) / {chapters}), 640, 360)[150:212, 405:510] > 150).sum())"
             f" for k in range({chapters})]\nprint(json.dumps(ink))")
    run = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr[-1500:]
    return np.array(json.loads(run.stdout.strip().splitlines()[-1]))


def test_an_equation_swapped_any_way_leaves_nothing_behind_in_the_program(tmp_path, monkeypatch):
    # The editor and the phone play the exported program, not the video: an equation turned into the next one piece
    # by piece, through a copy, or by FadeTransform left the old one drawn under it (or, for FadeTransform, neither),
    # and those leftovers stayed for the rest of the lecture under every later figure.
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    swaps = ["self.play(ReplacementTransform(a[0], b[0]), ReplacementTransform(a[1], b[1]), "
             "ReplacementTransform(a[2], b[2]))",
             "self.play(ReplacementTransform(a.copy(), b), FadeOut(a))",
             "self.play(FadeTransform(a, b))"]
    plain = "self.play(FadeOut(a), FadeIn(b))"
    swapped = _chapter_end_ink(tmp_path, "swapped", _swap_lecture(swaps), len(swaps))
    reference = _chapter_end_ink(tmp_path, "plain", _swap_lecture([plain] * len(swaps)), len(swaps))
    assert (abs(swapped - reference) <= reference * 0.15 + 20).all(), (swapped.tolist(), reference.tolist())
