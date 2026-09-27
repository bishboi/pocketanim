"""Fast offline checks: planning, scripting, gates and compiling a job, no render.

    cd harness/forge && ../../.venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

import ast
import os
import tempfile
from pathlib import Path

import pytest

os.environ.pop("OPENROUTER_API_KEY", None)          # the offline workers, always

from forge import gates, machine, patterns, registry  # noqa: E402
from forge.engine import compile as compile_  # noqa: E402
from forge.job import Job  # noqa: E402

HERE = Path(__file__).resolve().parents[1]


@pytest.fixture
def plassey(tmp_path):
    root = tmp_path / "jobs"
    job = Job.create("plassey", template="battle_explainer", style="campaign", title="The Battle of Plassey",
                     content=(HERE / "examples" / "plassey.md").read_text(), region="bengal_lower", root=root)
    run = machine.Run(job)
    state = "intake"
    while state != "narrate":
        state = getattr(run, state)()
    return job


def test_every_library_resolves():
    for sid in registry.styles():
        style = registry.resolve_style(sid)
        assert style["chain"][0] == sid
    for tid in registry.templates():
        template = registry.load_template(tid)
        assert template["arc"], tid
        assert not registry.check_compat(template, registry.resolve_style("atlas", tid)), tid


def test_incompatible_script_is_flagged():
    template = registry.load_template("geography_lecture")
    problems = registry.check_compat(template, registry.resolve_style("atlas"), "hi-IN")
    assert any("Deva" in p for p in problems)


def test_pattern_expansion():
    pats = registry.load_template("battle_explainer")["patterns"]
    beats = patterns.expand({"pattern": "decisive_charge", "slots": {"attacker": "mir_madan", "target": "company",
                                                                    "outcome": "repulsed"},
                             "lines": {"setup": "a", "charge": "b", "result": "c"}}, pats)
    assert [b["say"] for b in beats] == ["a", "b", "c"]
    assert beats[2]["do"][1] == {"op": "rout", "unit": "mir_madan", "to": "company"}


def test_plassey_plan_and_gates(plassey):
    outline = plassey.read("outline.json")
    slots = [c["slot"] for c in outline["chapters"]]
    assert slots[0] == "prologue" and "battle" in slots and "road_to_war" in slots
    report = plassey.read("qa/gates.json")
    assert all(not r["errors"] for r in report.values()), report
    battle = next(c for c in outline["chapters"] if c["slot"] == "battle")
    ops = [o["op"] for b in plassey.script(battle["id"])["beats"] for o in b["do"]]
    for needed in ("unit", "volley", "clock", "charge", "rout"):
        assert needed in ops
    facts = plassey.read("facts.json")
    assert "08:00" in facts["times"] and "50000" in facts["numbers"]
    shown = gates.numbers_shown(plassey.script(battle["id"]))
    assert shown <= set(facts["numbers"]) | {str(n) for n in range(1, 11)}


def test_compiled_scenes_parse(plassey):
    template = registry.load_template("battle_explainer")
    style = registry.resolve_style("campaign", "battle_explainer")
    manifest = compile_.compile_job(plassey, template, style)
    for entry in manifest.values():
        source = Path(entry["file"]).read_text()
        ast.parse(source)
        assert f"class {entry['class']}(" in source


def test_revise_beat_rewinds_to_validate(plassey):
    before = plassey.script("c2")["beats"][0]["say"]
    result = machine.revise(plassey, "c2.b01: say: Bengal was the richest province of Mughal India.")
    assert result["rewind"] == "validate" and plassey.state["state"] == "validate"
    assert plassey.script("c2")["beats"][0]["say"] != before
    with pytest.raises(ValueError):
        machine.revise(plassey, "c99: nothing")
