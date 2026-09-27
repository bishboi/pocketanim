"""Subject kits: the content decides the lecture -- style, map policy, and the pictures (molecules, equations...)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from forge.util import LECTURE

import compile_lecture as cl  # noqa: E402 -- harness/lecture is on the path via forge.util
import genre  # noqa: E402

HERE = Path(__file__).resolve().parents[1]

SAMPLES = {
    "biology": "Plants make glucose by photosynthesis. Chlorophyll in the leaves captures light; the cell releases oxygen.",
    "chemistry": "Methane burns in oxygen: CH4 + 2O2 -> CO2 + 2H2O. The reaction releases energy as the bonds change.",
    "physics": "Newton's second law says force equals mass times acceleration, F = ma, for any moving body.",
    "history": "The Mughal Empire was founded by Babur in 1526 after the battle of Panipat. Akbar ruled from 1556.",
    "geography": "Rajasthan is the largest state of India. The Aravalli range and the Thar desert shape its rainfall.",
    "mathematics": "The derivative of x^2 is 2x. A function's graph has a slope equal to its derivative.",
    "economics": "Inflation rises when demand grows faster than supply, and the central bank raises interest rates.",
}


@pytest.mark.parametrize("expected", sorted(SAMPLES))
def test_classify(expected):
    result = genre.classify(SAMPLES[expected])
    assert result["genre"] == expected
    assert result["style"] in ("vox", "parchment", "lab", "cosmos", "chalkboard", "atlas")


def test_equations_and_timelines_from_narration():
    assert cl._equation_in("The equation is CH4 + 2O2 -> CO2 + 2H2O.") == "CH_4 + 2O_2 -> CO_2 + 2H_2O"
    assert cl._equation_in("Einstein showed that E = mc^2 links mass and energy.") == "E = mc^2"
    assert cl._equation_in("Prices rose sharply in 1991.") is None
    events = cl._timeline_of({"beats": [{"say": "Babur won at Panipat in 1526."}, {"say": "Akbar ruled from 1556."},
                                        {"say": "Aurangzeb died in 1707."}]})
    assert events == [["1526", "Babur Panipat"], ["1556", "Akbar"], ["1707", "Aurangzeb"]]


def test_science_beats_get_molecules_and_equations():
    pytest.importorskip("rdkit")
    fills = cl.auto_visuals({"beats": [{"say": "Plants turn carbon dioxide and water into glucose."},
                                       {"say": "The equation is 6CO2 + 6H2O -> C6H12O6 + 6O2."}]}, genre="biology")
    assert fills[0] == {"op": "molecule", "name": "carbon dioxide"}
    assert fills[1]["op"] == "equation" and "C_6H_{12}O_6" in fills[1]["tex"]


def test_kit_ops_lint():
    pytest.importorskip("rdkit")
    assert cl._kit_problem({"op": "molecule", "name": "glucose"}) is None
    assert "no molecule" in cl._kit_problem({"op": "molecule", "name": "unobtainium-xyz"})
    assert cl._kit_problem({"op": "plot", "expr": "x^2 - 3*x", "x": [0, 5]}) is None
    assert "unknown name" in cl._kit_problem({"op": "plot", "expr": "__import__('os')", "x": [0, 5]})
    assert cl._kit_problem({"op": "process", "steps": ["one"]})


def test_unused_figures_are_placed_where_the_narration_names_them():
    script = {"figures": {"fig1": {"file": "a.png", "caption": "Figure 1: Area under the main crops"},
                          "fig2": {"file": "b.png", "caption": "Figure 2: Monsoon rainfall"}},
              "chapters": [{"beats": [{"say": "The plain is flat.", "do": []},
                                      {"say": "The monsoon brings the rainfall.", "do": []},
                                      {"say": "It is hot.", "do": []},
                                      {"say": "The main crops cover the area.", "do": []}]}]}
    assert cl.place_figures(script) == 2
    placed = {op["id"]: i for i, b in enumerate(script["chapters"][0]["beats"]) for op in b["do"]}
    assert placed == {"fig2": 1, "fig1": 3}


def test_forge_auto_picks_template_and_style(tmp_path):
    from forge import machine
    from forge.job import Job

    job = Job.create("auto", template="auto", style="auto", title="Combustion",
                     content=(HERE / "examples" / "combustion.md").read_text(), root=tmp_path / "jobs")
    run = machine.Run(job)
    run.intake()
    run.resolve()
    spec = job.spec
    assert (spec["genre"], spec["template"], spec["style"]) == ("chemistry", "science_explainer", "lab")
    assert spec.get("region_id") is None
