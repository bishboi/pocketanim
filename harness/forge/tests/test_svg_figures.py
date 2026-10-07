"""A book's figures redrawn as SVG by the model (harness/app/lib/figures.ts) and shown on the board: the checker
the drawer's output goes through, the compiler's handling of a drawn figure (shown, its parts revealed and pointed
at), and the lecture exported for the phone with both interpreters agreeing."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path
from forge.util import REPO

import compile_lecture as cl  # noqa: E402

HERE = REPO / "harness" / "forge" / "tests" / "fixtures" / "figures"
FIGURES = {
    "fig1": {"file": str(HERE / "incline.svg"), "svg": str(HERE / "incline.svg"), "caption": "A block on a slope",
             "parts": ["ground", "wedge", "theta", "block", "mg", "N"]},
    "fig2": {"file": str(HERE / "circuit.svg"), "svg": str(HERE / "circuit.svg"), "caption": "A simple circuit",
             "parts": ["wire", "battery", "bulb", "switch", "current"]},
}


def _check(paths: dict) -> dict:
    out = subprocess.run([sys.executable, str(REPO / "harness" / "lecture" / "svgcheck.py")], capture_output=True,
                         text=True, timeout=300,
                         input=json.dumps({"figures": [{"id": k, "svg": v} for k, v in paths.items()]}))
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_checker_passes_a_good_figure_and_says_what_is_wrong_with_a_bad_one(tmp_path):
    bad = tmp_path / "bad.svg"
    bad.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="x.png"/><style>.a{}</style>'
                   '<path d="M0 0 L9 9"/><rect x="1" y="1" width="2" height="2"/><circle cx="5" cy="5" r="2"/>'
                   '<line x1="0" y1="0" x2="3" y2="3"/></svg>')
    morph = tmp_path / "morph.svg"
    morph.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g id="a"><path d="M0 0 L50 50">'
                     '<animate attributeName="d" values="M0 0 L50 50; M0 0 L60 40" dur="1s" repeatCount="indefinite"/>'
                     '</path></g><g id="b"><circle cx="70" cy="70" r="5"/></g></svg>')
    result = _check({"good": FIGURES["fig2"]["svg"], "bad": str(bad), "morph": str(morph), "none": str(tmp_path / "x")})
    assert result["good"]["ok"] and result["good"]["parts"] == FIGURES["fig2"]["parts"] and result["good"]["animated"]
    assert result["good"]["labels"]["bulb"] == "bulb"
    errors = " ".join(result["bad"]["errors"])
    assert not result["bad"]["ok"] and "viewBox" in errors and "<image>" in errors and "<style>" in errors
    assert "<g id" in errors                                     # four shapes and no parts
    assert any("animates d" in e for e in result["morph"]["errors"])
    assert result["none"]["errors"] == ["no SVG was written"]


def _lecture():
    return {
        "title": "Figures", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
        "rebuild_figures": True, "figures": json.loads(json.dumps(FIGURES)),
        "chapters": [{"title": "Slopes and circuits", "map": False, "narration": "One.", "beats": [
            {"say": "Here is the book's figure: a block on a slope.",
             "do": [{"op": "figure", "id": "fig1", "show": ["ground", "wedge", "block"]}]},
            {"say": "Its weight pulls straight down.", "do": [{"op": "reveal", "diagram": "fig1", "nodes": ["mg"]}]},
            {"say": "And the angle of the slope is theta.", "do": [{"op": "focus", "diagram": "fig1", "node": "theta"}]},
            {"say": "Now a circuit: a cell, a bulb and a switch.",
             "do": [{"op": "figure", "id": "fig2", "show": ["wire", "battery", "bulb", "switch"]}]},
            {"say": "Close the switch and the current flows round, through the bulb and back to the cell.",
             "do": [{"op": "reveal", "diagram": "fig2", "nodes": ["current"]}]},
        ]}],
    }


def test_a_drawn_figure_is_shown_and_its_parts_revealed():
    script = _lecture()
    assert cl.lint(script)[0] == []
    source = cl.compile_script(json.loads(json.dumps(script)))
    assert source.count("self.svg_figure(") == 2 and "show=['ground', 'wedge', 'block']" in source
    wrong = _lecture()
    wrong["chapters"][0]["beats"][1]["do"][0]["nodes"] = ["weight"]
    assert any("reveal: nodes must be ids of diagram 'fig1'" in e for e in cl.lint(wrong)[0])
    unknown = _lecture()
    unknown["chapters"][0]["beats"][0]["do"][0]["show"] = ["slope"]
    assert any("no part 'slope'" in e for e in cl.lint(unknown)[0])
    # Without its SVG, the book's picture may not be shown as it is: it is built, or it is a photograph.
    undrawn = _lecture()
    undrawn["figures"]["fig1"].pop("svg")
    assert any("shown as it is. Build it in" in e for e in cl.lint(undrawn)[0])


def test_drawn_figures_play_on_the_phone_as_shapes(tmp_path):
    scene = tmp_path / "scene.py"
    scene.write_text(cl.compile_script(_lecture()))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path)], capture_output=True, text=True, timeout=1500,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [] and not result.get("skipped"), result
    program = (tmp_path / "dsl" / "generated" / "GeneratedScene.panim").read_text()
    assert any(line.startswith("clip ") and "loop=" in line for line in program.splitlines())   # the current flows
    (tmp_path / "player").symlink_to(REPO / "player")
    cross = subprocess.run([sys.executable, "-m", "tools.crosscheck_interpreter", "dsl/generated/GeneratedScene.panim"],
                           cwd=tmp_path, capture_output=True, text=True, timeout=1800,
                           env={**os.environ, "PYTHONPATH": str(REPO)})
    assert "both interpreters agree" in cross.stdout, cross.stdout[-3000:] + cross.stderr[-2000:]


def _drawn_lecture(with_svg: bool = True):
    """A lecture whose pictures are draw ops (described by the script writer, drawn as SVG before compiling)."""
    ramp = {"op": "draw", "id": "ramp", "what": "A block on a smooth slope with its weight and the normal force",
            "parts": ["ground", "wedge", "theta", "block", "mg", "N"], "show": ["ground", "wedge", "block"]}
    loop = {"op": "draw", "id": "loop", "what": "A cell, a bulb and a switch in a closed loop; current flowing",
            "parts": ["wire", "battery", "bulb", "switch", "current"], "moves": "current flows round the wire"}
    figure = {"op": "draw", "what": "A block on a smooth slope with its weight and the normal force",
              "parts": ["ground", "wedge", "theta", "block", "mg", "N"], "show": ["wedge", "block"]}
    if with_svg:
        ramp["svg"] = figure["svg"] = str(HERE / "incline.svg")
        loop["svg"] = str(HERE / "circuit.svg")
    return {
        "title": "Drawn", "style": "chalkboard", "auto_visuals": False, "place_figures": False, "drawn": with_svg,
        "chapters": [{"title": "Pictures", "map": False, "narration": "One.", "beats": [
            {"say": "A block rests on a smooth slope.", "do": [ramp]},
            {"say": "Its weight pulls straight down.", "do": [{"op": "reveal", "diagram": "ramp", "nodes": ["mg"]}]},
            {"say": "Now a circuit, with the current flowing round it.", "do": [loop]},
            {"say": "A problem on the slope.", "do": [{"op": "problem", "id": "p1", "text": "Find the acceleration.",
                                                       "given": ["θ = 30°"], "find": "a", "figure": figure}]},
            {"say": "The normal force acts at right angles to the slope.",
             "do": [{"op": "reveal", "diagram": "p1_figure", "nodes": ["N"]}]},
            {"say": "Along the slope, the weight's component is m g sine theta.",
             "do": [{"op": "work", "id": "p1", "lines": ["a = g\\sin\\theta"]}]},
        ]}],
    }


def test_a_described_picture_is_linted_compiled_and_falls_back_to_its_parts():
    script = _drawn_lecture()
    assert cl.lint(script)[0] == []
    source = cl.compile_script(json.loads(json.dumps(script)))
    assert source.count("self.svg_figure(") == 2 and "'op': 'draw'" in source and "incline.svg" in source
    # Not drawn (no drawing pass): its parts as labelled boxes, so the reveals still land.
    plain = cl.compile_script(_drawn_lecture(with_svg=False))
    assert "self.svg_figure(" not in plain and "self.sketch(\"ramp\"" in plain
    # The pass ran and could not draw one: the compiler sends back why.
    failed = _drawn_lecture()
    failed["chapters"][0]["beats"][0]["do"][0].pop("svg")
    failed["chapters"][0]["beats"][0]["do"][0]["_draw_error"] = "it has no part mg"
    assert any("could not be drawn: it has no part mg" in e for e in cl.lint(failed)[0])
    bad = _drawn_lecture()
    bad["chapters"][0]["beats"][0]["do"][0]["parts"] = ["a part"]
    assert any("a part id is a short name" in e for e in cl.lint(bad)[0])


def test_described_pictures_play_on_the_phone(tmp_path):
    scene = tmp_path / "scene.py"
    scene.write_text(cl.compile_script(_drawn_lecture()))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(tmp_path)], capture_output=True, text=True, timeout=1500,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["blockers"] == [] and not result.get("skipped"), result
    (tmp_path / "player").symlink_to(REPO / "player")
    cross = subprocess.run([sys.executable, "-m", "tools.crosscheck_interpreter", "dsl/generated/GeneratedScene.panim"],
                           cwd=tmp_path, capture_output=True, text=True, timeout=1800,
                           env={**os.environ, "PYTHONPATH": str(REPO)})
    assert "both interpreters agree" in cross.stdout, cross.stdout[-3000:] + cross.stderr[-2000:]
