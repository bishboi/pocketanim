"""Animated SVG drawings (harness/lecture/animsvg.py) and the looping clips they export as: SMIL read and played
on Manim's shapes, motions written into still drawings, a moving diagram stored once per period and replayed by
both interpreters."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path
from forge.util import REPO

import animsvg  # noqa: E402
import compile_lecture as cl  # noqa: E402

SPIN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<rect x="40" y="10" width="20" height="40" fill="#f00">
  <animateTransform attributeName="transform" type="rotate" values="0 50 50; 360 50 50" dur="4s"
                    repeatCount="indefinite"/>
</rect>
<circle cx="50" cy="80" r="5" fill="#00f" opacity="0">
  <animate attributeName="opacity" values="0; 1; 0" dur="1s" begin="0s; x1.end+1s"/>
</circle>
</svg>"""

USE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
<defs><symbol id="s" viewBox="0 0 10 10"><circle cx="5" cy="5" r="5" fill="#0f0"/></symbol></defs>
<use href="#s" width="20" height="20" transform="translate(10 10)"/>
<use href="#s" x="100" width="40" height="40"/>
</svg>"""


def test_smil_timing_values_and_periods():
    doc = animsvg.Doc(SPIN)
    spin, blink = doc.anims
    assert spin.period == 4.0 and blink.period == 2.0          # once every 1 s + 1 s of rest after it ends
    assert spin.matrix(0.25) @ np.array([50, 10, 1]) == pytest.approx([90, 50, 1])    # a quarter turn about (50, 50)
    assert blink.progress(0.5) == pytest.approx(0.5) and blink.value(0.5) == [1.0]
    assert blink.progress(1.5) is None                          # resting: back to its own opacity="0"
    assert doc.opacity(doc.leaves[1], doc.state(0.5)) == pytest.approx(1.0)
    assert doc.opacity(doc.leaves[1], doc.state(1.5)) == 0.0
    assert doc.period() == 120                                  # 4 s at 30 fps, every motion within it
    # Periods are snapped to whole frames that divide LOOP: 0.67 s + 0.33 s of rest -> 1 s, 6 s -> 4 s.
    assert animsvg._snap(30.0) == 30 and animsvg._snap(180) in (120, 240) and animsvg._snap(20.1) == 20


def test_uses_are_written_out_with_their_symbols_fitted():
    doc = animsvg.Doc(USE)
    assert len(doc.leaves) == 2
    centres = [doc.static_ctm(leaf) @ np.array([5, 5, 1]) for leaf in doc.leaves]
    assert centres[0][:2] == pytest.approx([20, 20]) and centres[1][:2] == pytest.approx([120, 20])


def test_the_drawing_moves_and_stays_where_it_is_put():
    from manim import RIGHT

    drawing = animsvg.make(SPIN, height=2.0)
    assert drawing.quick and drawing.period == 120
    bar, dot = drawing.leaves
    drawing.shift(RIGHT * 3)
    drawing.show(0.0)
    top = bar.get_top()[1]
    assert dot.get_fill_opacity() == 0.0                        # opacity="0" read, not Manim's default 1
    drawing.show(1.0)                                           # a quarter turn: the bar lies on its side
    assert bar.width > bar.height and bar.get_center()[0] > 3
    drawing.show(0.5)
    assert dot.get_fill_opacity() == pytest.approx(1.0)
    drawing.show(4.0)
    assert bar.get_top()[1] == pytest.approx(top, abs=1e-6)     # round again: period over


def test_a_motion_is_written_into_a_still_drawing_as_smil():
    still = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <path d="M20 20 H80 V80 H20 Z" fill="#888"/></svg>"""
    text = animsvg.add_motion(still, "spin", (20, 20, 60, 60))
    assert "<animateTransform" in text and 'type="rotate"' in text
    drawing = animsvg.make(text, height=1.0)
    square = drawing.leaves[0]
    corner = square.points[0].copy()
    drawing.show(0.5)                                           # 1/8 turn about the centre
    centre = np.array(drawing.get_center())
    moved = square.points[0] - centre
    before = corner - centre
    assert math.isclose(np.linalg.norm(moved), np.linalg.norm(before), rel_tol=1e-4)
    assert abs(math.degrees(math.atan2(moved[1], moved[0]) - math.atan2(before[1], before[0])) % 360 - 315) < 1


def test_words_find_their_motion_and_weather_its_animated_drawing():
    assert animsvg.motion_for("gear") == "spin" and animsvg.motion_for("deciduous tree") == "sway"
    assert animsvg.motion_for("cow") is None
    if animsvg._meteocons():
        assert animsvg.weather_icon("rain").startswith("rain")
        assert animsvg.weather_icon("thunderstorm") and animsvg.weather_icon("a sunny day")
        drawing = animsvg.make(animsvg.weather_svg(animsvg.weather_icon("rain")), height=1.0, strokes=True)
        shown = set()
        for frame in range(0, 30, 3):
            drawing.show(frame / 30)
            shown.add(round(sum(leaf.get_fill_opacity() for leaf in drawing.leaves), 2))
        assert drawing.period > 1 and len(shown) > 2              # drops fade in and out as they fall


def test_lint_checks_a_nodes_motion():
    ok = {"title": "W", "style": "chalkboard", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "Water", "map": False, "beats": [{"say": "Water goes round.", "do": [
            {"op": "diagram", "id": "w", "kind": "cycle", "flow": True, "nodes": [
                {"id": "s", "label": "Sun", "entity": "sun"}, {"id": "r", "label": "Rain", "entity": "rain"},
                {"id": "g", "label": "Gear", "entity": "gear", "anim": "spin"}]}]}]}]}
    assert cl.lint(ok)[0] == []
    assert "flow=True" in cl.compile_script(ok)
    ok["chapters"][0]["beats"][0]["do"][0]["nodes"][2]["anim"] = "twirl"
    assert any("anim is one of" in e for e in cl.lint(ok)[0])


def test_a_moving_diagram_loops_one_period_shared_by_its_lines(tmp_path):
    """Three lines over one moving diagram: each line's hold is a clip of one period (loop=phase), all three the
    same asset, and both interpreters play them frame for frame alike."""
    beats = [{"say": "The water goes round, from the sea to the sky and back again, all the time.", "do": [
        {"op": "diagram", "id": "w", "kind": "cycle", "nodes": [
            {"id": "s", "label": "Sun", "entity": "sun", "anim": "spin"},
            {"id": "c", "label": "Gear", "entity": "gear"},
            {"id": "r", "label": "Heart", "entity": "heart"}]}]},
        {"say": "The sun warms the sea and the water rises up into the air as an invisible vapour."},
        {"say": "Up high it cools, gathers into clouds, and comes back down to the ground as rain."}]
    script = {"title": "Loop", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
              "chapters": [{"title": "Loop", "map": False, "narration": "One.", "beats": beats}]}
    scene = tmp_path / "scene.py"
    scene.write_text(cl.compile_script(json.loads(json.dumps(script))))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path)], capture_output=True, text=True, timeout=1500,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [] and not result.get("skipped"), result
    program = (tmp_path / "dsl" / "generated" / "GeneratedScene.panim").read_text()
    loops = [line for line in program.splitlines() if line.startswith("clip ") and " loop=" in line]
    assert len(loops) >= 2, program[:3000]
    assets = {line.split("asset=")[1].split()[0] for line in loops}
    assert len(assets) < len(loops)                             # the same period, stored once
    (tmp_path / "player").symlink_to(REPO / "player")
    cross = subprocess.run([sys.executable, "-m", "tools.crosscheck_interpreter", "dsl/generated/GeneratedScene.panim"],
                           cwd=tmp_path, capture_output=True, text=True, timeout=1800,
                           env={**os.environ, "PYTHONPATH": str(REPO)})
    assert "both interpreters agree" in cross.stdout, cross.stdout[-3000:] + cross.stderr[-2000:]
