"""Moving pictures on the phone: updaters baked into clips, the lecture's live ops (sim, counter, trace, sweep,
zoom, continuous motion) and their lint. Everything plays from shapes on the phone (clip and run verbs), never
from a video."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path
from forge.util import REPO

import compile_lecture as cl  # noqa: E402

UPDATERS = '''
from manim import *


class Ticking(Scene):
    def construct(self):
        t = ValueTracker(0)
        dot = always_redraw(lambda: Dot([t.get_value() - 2, np.sin(t.get_value()), 0], color=YELLOW))
        number = DecimalNumber(0).to_edge(UP)
        number.add_updater(lambda m: m.set_value(t.get_value()))
        arm = Line(ORIGIN, RIGHT * 1.5).shift(DOWN * 2)
        arm.add_updater(lambda m, dt: m.rotate(dt, about_point=m.get_start()))
        self.add(dot, number, arm)
        self.play(t.animate.set_value(4), run_time=2)
        number.clear_updaters()
        arm.clear_updaters()
        self.play(FadeOut(arm))
        self.wait(0.5)
'''


def _export(tmp_path, source: str, name: str, timeout: int = 900) -> dict:
    scene = tmp_path / "scene.py"
    scene.write_text(source)
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene), name,
                          str(tmp_path)], capture_output=True, text=True, timeout=timeout,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    return json.loads(out.stdout.strip().splitlines()[-1])


def _interpreters_agree(tmp_path, name: str) -> None:
    (tmp_path / "player").symlink_to(REPO / "player")
    cross = subprocess.run([sys.executable, "-m", "tools.crosscheck_interpreter", f"dsl/generated/{name}.panim"],
                           cwd=tmp_path, capture_output=True, text=True, timeout=1800,
                           env={**os.environ, "PYTHONPATH": str(REPO)})
    assert "both interpreters agree" in cross.stdout, cross.stdout[-3000:] + cross.stderr[-2000:]


def test_updaters_are_baked_into_a_clip_both_interpreters_play(tmp_path):
    result = _export(tmp_path, UPDATERS, "Ticking")
    assert result["tier"] == 1 and result["blockers"] == [], result
    program = (tmp_path / "dsl" / "generated" / "Ticking.panim").read_text()
    clips = [line for line in program.splitlines() if line.startswith("clip ")]
    runs = [line for line in program.splitlines() if line.startswith("run ")]
    assert clips and runs and "frames=60" in clips[0]           # 2 s at 30 fps, frame by frame
    _interpreters_agree(tmp_path, "Ticking")


def _lecture(beats):
    return {"title": "Motion", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
            "chapters": [{"title": "Motion", "narration": "Chapter one.", "map": False, "beats": beats}]}


def test_lint_checks_the_live_ops():
    graph = {"op": "graph", "id": "g", "x": [-3, 3], "y": [-1, 4],
             "items": [{"kind": "curve", "id": "f", "expr": "0.4*x^2"}]}
    ok = _lecture([
        {"say": "A curve.", "do": [graph]},
        {"say": "As the point moves, the slope changes.", "do": [{"op": "trace", "diagram": "g", "curve": "f",
                                                                  "from": -2, "to": 2, "tangent": True,
                                                                  "readout": "slope"}]},
        {"say": "Change a and the curve reshapes.", "do": [{"op": "sweep", "diagram": "g", "expr": "a*x^2",
                                                            "param": "a", "from": -1, "to": 1}]},
        {"say": "A wave travels along the string.", "do": [{"op": "sim", "id": "w", "kind": "wave",
                                                             "wave": "standing"}]},
        {"say": "The speed rises.", "do": [{"op": "counter", "id": "n", "from": 0, "to": 30, "style": "dial"}]},
        {"say": "A circuit.", "do": [{"op": "circuit", "id": "c", "kind": "series"}]},
        {"say": "Look closer at the first resistor.", "do": [{"op": "zoom", "diagram": "c", "node": "R1"}]},
    ])
    assert cl.lint(ok)[0] == []

    def errors(*beats):
        return cl.lint(_lecture(list(beats)))[0]

    assert any("sim" in e or "kind" in e for e in errors({"say": "A thing.", "do": [{"op": "sim", "id": "s",
                                                                                     "kind": "volcano"}]}))
    assert any("travelling, standing or superpose" in e
               for e in errors({"say": "A wave.", "do": [{"op": "sim", "id": "s", "kind": "wave", "wave": "square"}]}))
    assert any("counter needs from" in e for e in errors({"say": "Up.", "do": [{"op": "counter", "id": "n",
                                                                                "to": 5}]}))
    assert any("works on a graph" in e
               for e in errors({"say": "A ramp.", "do": [{"op": "incline", "id": "r"}]},
                               {"say": "Trace it.", "do": [{"op": "trace", "diagram": "r", "curve": "f"}]}))
    assert any("sweep expr" in e
               for e in errors({"say": "A curve.", "do": [graph]},
                               {"say": "Sweep.", "do": [{"op": "sweep", "diagram": "g", "expr": "b*x^2",
                                                         "param": "a"}]}))


def test_live_ops_export_as_shapes_and_zoom_draws_the_picture_once(tmp_path):
    """A sim, a counter, a trace, live motion on a sketch and a zoom, compiled from a lecture script: tier 1, played
    from clips, both interpreters frame for frame the same. The zoom moved parts nested in the stage card; exported
    as verbs it drew a moved copy over the unmoved picture, so the frames after it held twice the shapes."""
    sys.path.insert(0, str(REPO))
    from dsl.interpret import build, fold_steps, parse, step_frames

    beats = [
        {"say": "A curve.", "do": [{"op": "graph", "id": "g", "x": [-3, 3], "y": [-1, 4],
                                    "items": [{"kind": "curve", "id": "f", "expr": "0.4*x^2"}]}]},
        {"say": "As the point moves, its slope reads out.", "do": [{"op": "trace", "diagram": "g", "curve": "f",
                                                                    "from": -2, "to": 2, "tangent": True,
                                                                    "readout": "slope"}]},
        {"say": "A planet goes round its star.", "do": [
            {"op": "sketch", "id": "s", "items": [{"id": "sun", "type": "circle", "at": [5, 3], "r": 0.5},
                                                   {"id": "p", "type": "circle", "at": [7, 3], "r": 0.2}]},
            {"op": "motion", "diagram": "s", "kind": "orbit", "parts": ["p"], "about": [5, 3], "period": 2}]},
        {"say": "Two carts collide.", "do": [{"op": "sim", "id": "k", "kind": "collision"}]},
        {"say": "The battery runs down.", "do": [{"op": "counter", "id": "n", "from": 90, "to": 20, "unit": "%"}]},
        {"say": "Here is a circuit.", "do": [{"op": "circuit", "id": "c", "kind": "series"}]},
        {"say": "Let us move in on the first resistor.", "do": [{"op": "zoom", "diagram": "c", "node": "R1"}]},
        {"say": "And back out.", "do": [{"op": "zoom", "diagram": "c"}]},
    ]
    script = _lecture(beats)
    assert cl.lint(json.loads(json.dumps(script)))[0] == []
    result = _export(tmp_path, cl.compile_script(json.loads(json.dumps(script))), "GeneratedScene", timeout=1500)
    assert result["tier"] == 1 and result["blockers"] == [] and not result.get("skipped"), result
    path = tmp_path / "dsl" / "generated" / "GeneratedScene.panim"
    program = path.read_text()
    assert sum(line.startswith("run ") for line in program.splitlines()) >= 5     # trace, orbit, sim, counter, zoom x2

    # The zoom: the circuit just before it, and once it has moved in, is the same number of shapes.
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        scene = parse(program)
        ir = build(scene)
    finally:
        os.chdir(cwd)
    pos, runs = 1, []
    for node in fold_steps(scene["timeline"]):
        n = 0 if node[0] in ("show", "hide") else step_frames(node, scene["fps"])
        if node[0] == "run":
            runs.append((pos, n))
        pos += n
    glyphs = [sum(not c.isspace() for c in b["say"]) for b in beats[-3:]]     # each beat's caption, a shape a letter
    (zoom_at, zoom_n), (out_at, out_n) = runs[-2], runs[-1]
    before = len(ir.frame(zoom_at - 2))
    moving = {len(ir.frame(f)) for f in (zoom_at + 1, zoom_at + zoom_n // 2, zoom_at + zoom_n - 1, zoom_at + zoom_n + 2)}
    assert len(moving) == 1, moving                                  # the same shapes through the move and after it
    assert abs(moving.pop() - before - (glyphs[1] - glyphs[0])) <= 3   # only the caption changed: no second circuit
    back = {len(ir.frame(f)) for f in (out_at + 1, out_at + out_n + 2)}
    assert len(back) == 1 and abs(back.pop() - before - (glyphs[2] - glyphs[0])) <= 3
    _interpreters_agree(tmp_path, "GeneratedScene")
