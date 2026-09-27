"""The model-worker path against a mock OpenRouter: tool calls, a reply that
fails its check and is retried, pattern beats, and a beat repair."""

from __future__ import annotations

import threading
from http.server import HTTPServer
from pathlib import Path

import pytest

import mock_openrouter
from forge import llm, machine
from forge.job import Job

HERE = Path(__file__).resolve().parents[1]


@pytest.fixture
def model(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), mock_openrouter.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mock_openrouter.LOG.clear()
    mock_openrouter.STATE["facts_tries"] = 0
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(llm, "URL", f"http://127.0.0.1:{server.server_port}/v1")
    yield mock_openrouter.LOG
    server.shutdown()


def test_model_workers_to_validated_script(model, tmp_path):
    job = Job.create("plassey", template="battle_explainer", style="campaign", title="Plassey",
                     content=(HERE / "examples" / "plassey.md").read_text(), region="bengal_lower",
                     root=tmp_path / "jobs")
    result = machine.run(job, until="script")
    assert result["state"] == "narrate", result
    assert "plan +tool" in model and "write +tool" in model      # tools before answers
    assert "facts (retry)" in model                               # the bad reply was checked and retried
    assert "repair" in model                                      # the unsupported number was repaired
    forces = next(c for c in job.read("outline.json")["chapters"] if c["slot"] == "forces")
    said = " ".join(b["say"] for b in job.script(forces["id"])["beats"])
    assert "99,999" not in said
    battle = next(c for c in job.read("outline.json")["chapters"] if c["slot"] == "battle")
    assert any(b.get("pattern") == "decisive_charge" for b in job.script(battle["id"])["beats"])
    state = job.state
    assert state["tokens"]["in"] > 0 and state["cost_usd"] > 0
    assert job.lexicon.get("Siraj ud-Daulah")
