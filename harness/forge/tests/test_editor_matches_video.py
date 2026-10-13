"""What the editor and the phone play (the exported program) against what the video shows, for the faults the
beat-by-beat comparison (tools/check_editor_matches_video.py) found: each a case where the two disagreed."""

from __future__ import annotations

import json
import subprocess
import sys

from forge.util import REPO

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "harness" / "lecture"))

import free_check  # noqa: E402


def test_a_scale_about_another_point_moves_the_part_too():
    # The stage shrinks its parts together beside a card: scale(f, about_point=centre). Written as a scale about
    # each part's own centre, every part shrank where it stood and the picture came apart beside the card.
    import numpy as np
    from manim import Square

    from dsl.export_dsl import animate_verbs

    square = Square(1).move_to([2, 1, 0])
    builder = square.animate.scale(0.5, about_point=np.array([0.0, 0.0, 0.0]))
    verbs = animate_verbs(builder.methods, "S", 1.0, square)
    assert verbs and "by=0.5" in verbs[0] and "by_xy=-1,-0.5" in verbs[0], verbs


def _played(tmp_path, body: str):
    """The last frame of a one-line Manim scene's exported program, as the players draw it."""
    (tmp_path / "scene.py").write_text("from manim import *\n\nclass One(Scene):\n    def construct(self):\n"
                                       "        line = Line(LEFT * 3, RIGHT * 3, color=GREY, stroke_width=4)\n"
                                       "        self.add(line)\n" + "".join(f"        {b}\n" for b in body.splitlines())
                                       + "        self.wait(0.5)\n")
    out = subprocess.run([sys.executable, str(REPO / "dsl" / "export_dsl.py"), str(tmp_path / "scene.py"), "One",
                          "--write"], cwd=tmp_path, capture_output=True, text=True, timeout=600,
                         env={**__import__("os").environ, "PYTHONPATH": str(REPO)})
    assert out.returncode == 0 and "TIER 1" in out.stdout, (out.stdout[-800:], out.stderr[-1500:])
    probe = (f"import sys, os\nsys.path.insert(0, {str(REPO)!r})\nos.chdir({str(tmp_path)!r})\n"
             "import numpy as np\nfrom dsl.interpret import load_program\n"
             "from exporter.reference_render import render_frame\n"
             "ir = load_program('dsl/generated/One.panim')\n"
             "np.save('last.npy', render_frame(ir, len(ir.records) - 1, 320, 180))")
    run = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr[-1500:]
    import numpy as np

    return np.load(tmp_path / "last.npy")


def test_a_colour_and_a_width_set_together_both_show(tmp_path):
    # set_color(...).set_stroke(width=8) is a `stroke` and a `fill` in one `par`. Each wrote the object back from
    # its own start every frame, so the stroke's change was undone: a shortest path's edges never turned gold.
    frame = _played(tmp_path, "self.play(line.animate.set_color(RED).set_stroke(width=12))")
    red = (frame[..., 0] > 180) & (frame[..., 1] < 100)
    assert red.sum() > 150, red.sum()


def test_a_turned_part_stays_turned(tmp_path):
    # Rotate leaves its object turned; the players put a baked part back where it started when the turn ended.
    import numpy as np

    frame = _played(tmp_path, "self.play(Rotate(line, PI / 2))")
    background = np.median(frame.reshape(-1, frame.shape[2]), axis=0)
    rows, cols = np.nonzero(np.abs(frame.astype(int) - background).max(axis=2) > 40)
    assert len(rows), "nothing drawn"
    assert np.ptp(rows) > np.ptp(cols), (np.ptp(rows), np.ptp(cols))        # upright, not lying along the x axis


def test_a_live_readout_can_fade_in_while_it_changes():
    # A trace's slope readout writes its next number every frame; fading in, its glyphs no longer paired with the
    # fade's start and end, and Manim's strict pairing stopped the whole render.
    import live as lv
    import pocket_lecture  # noqa: F401 -- the engine relaxes Transform's pairing
    from manim import Dot, FadeIn, VGroup

    read, put = lv._readout("1", 22)
    anim = FadeIn(VGroup(Dot(), read))
    anim.begin()
    put("slope -12.75")
    anim.interpolate(0.5)
    put("0")
    anim.interpolate(0.9)


def test_words_inside_a_cell_or_a_node_need_no_patch():
    # The patch of board behind a block's words (backed_text) showed as a dark box in a coloured table cell or a
    # highlighted node; words inside a closed shape drop it, words in the open keep it.
    import backed_text
    from manim import Circle, Square

    names = free_check.namespace(None)

    class Board:
        mobjects: list = []

    cell = Square(1.5).set_fill("#88AA88", 0.5)
    inside = names["MathTex"]("Tt").move_to(cell)
    node = Circle(radius=0.42)
    number = names["MathTex"]("50").move_to(node)
    loose = names["MathTex"]("x").shift([4, 0, 0])
    backed_text.settle(Board(), [cell, inside, node, number, loose])
    patched = [any(getattr(s, "is_backing", False) for s in t.submobjects) for t in (inside, number, loose)]
    assert patched == [False, False, True], patched


def _export(tmp_path, script):
    import compile_lecture as cl

    scene = tmp_path / "s.py"
    scene.write_text(cl.compile_script(script))
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PANIM_BUILD_WORKERS": "1"}
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path / "build")], capture_output=True, text=True, timeout=900,
                         env=env)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result.get("tier") == 1, (result.get("error"), out.stderr[-1500:])
    return tmp_path / "build"


def test_a_part_of_a_group_highlighted_on_its_own_shows_in_the_program(tmp_path, monkeypatch):
    # nodes[v][0].animate.set_fill(GOLD): the node is drawn as one picture, the fill went to its circle as an
    # object the program never showed, and the highlight never appeared in the editor.
    monkeypatch.setattr(free_check, "CACHE", tmp_path / "cache")
    first = ("node = VGroup(Circle(radius=0.6, color=INK, fill_color=BACKGROUND, fill_opacity=1), "
             "MathTex('50', color=INK)).move_to([2.9, 0, 0])\nself.play(FadeIn(node))")
    then = "self.play(node[0].animate.set_fill('#FF2020', 0.9))"
    script = {"title": "T", "style": "blueprint", "teaching_rules": False, "auto_visuals": False,
              "place_figures": False, "chapters": [
                  {"title": "Nodes", "map": False, "beats": [
                      {"say": "A node.", "do": [{"op": "manim", "id": "n", "code": first}]},
                      {"say": "It lights up.", "do": [{"op": "manim", "id": "n", "code": then}]},
                      {"say": "That is it.", "do": [{"op": "manim", "id": "n", "code": "self.wait(0.5)"}]}]},
                  {"title": "Next", "map": False, "beats": [{"say": "And on.", "do": []}]}]}
    build = _export(tmp_path, script)
    probe = (f"import sys, os\nsys.path.insert(0, {str(REPO)!r})\nos.chdir({str(build)!r})\n"
             "from dsl.interpret import load_program\nfrom exporter.reference_render import render_frame\n"
             "ir = load_program('dsl/generated/GeneratedScene.panim')\nn = len(ir.records)\n"
             "f = render_frame(ir, int(n * 0.48), 640, 360)[150:210, 420:480]\n"
             "print(int(((f[..., 0] > 180) & (f[..., 1] < 90)).sum()))")
    run = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr[-1500:]
    assert int(run.stdout.strip().splitlines()[-1]) > 300, run.stdout
