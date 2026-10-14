"""Moving pictures on the phone: updaters baked into clips, and the camera's zoom on a diagram. Everything plays from
shapes on the phone (clip and run verbs), never from a video."""

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


def test_a_zoom_draws_the_picture_once(tmp_path):
    """A zoom on a diagram, compiled from a lecture script: tier 1, played from clips, both interpreters frame for
    frame the same. The zoom moved parts nested in the stage card; exported as verbs it drew a moved copy over the
    unmoved picture, so the frames after it held twice the shapes."""
    sys.path.insert(0, str(REPO))
    from dsl.interpret import build, fold_steps, parse, step_frames

    nodes = [{"id": k, "label": k.title()} for k in ("battery", "switch", "lamp")]
    beats = [
        {"say": "Here is a circuit.", "do": [{"op": "diagram", "id": "c", "kind": "flow", "nodes": nodes,
                                               "edges": [["battery", "switch"], ["switch", "lamp"]],
                                               "animate": False, "flow": False}]},
        {"say": "Let us move in on the switch.", "do": [{"op": "zoom", "diagram": "c", "node": "switch"}]},
        {"say": "And back out.", "do": [{"op": "zoom", "diagram": "c"}]},
    ]
    script = _lecture(beats)
    assert cl.lint(json.loads(json.dumps(script)))[0] == []
    result = _export(tmp_path, cl.compile_script(json.loads(json.dumps(script))), "GeneratedScene", timeout=1500)
    assert result["tier"] == 1 and result["blockers"] == [] and not result.get("skipped"), result
    # The diagram drawn once.
    program = (tmp_path / "dsl" / "generated" / "GeneratedScene.panim").read_text()
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        scene = parse(program)
        ir = build(scene)
    finally:
        os.chdir(cwd)
    total = sum(0 if node[0] in ("show", "hide") else step_frames(node, scene["fps"])
                for node in fold_steps(scene["timeline"]))
    # What is held on screen: a count kept 15 frames or more (a fade from one picture to the next has both, briefly).
    seen = [len(ir.frame(f)) for f in range(1, total + 1)]
    runs = [(seen[0], 0)]
    for n in seen:
        runs[-1] = (n, runs[-1][1] + 1) if n == runs[-1][0] else runs[-1]
        if n != runs[-1][0]:
            runs.append((n, 1))
    counts = {n for n, length in runs if length >= 15}
    # Each beat holds the diagram and its caption (a shape a letter): zoomed in and back out, the count changes by the
    # caption's letters only. A moved copy drawn over the picture would add the whole diagram again.
    g0, g1, g2 = (sum(not c.isspace() for c in b["say"]) for b in beats)
    held = [x for x in counts if x + g1 - g0 in counts and x + g2 - g0 in counts]
    assert held, sorted(counts)
    assert max(counts) == max(held) + max(0, g1 - g0, g2 - g0), sorted(counts)
    _interpreters_agree(tmp_path, "GeneratedScene")
