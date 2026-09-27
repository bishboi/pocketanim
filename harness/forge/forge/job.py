"""A job: one request, one folder, one state.json.

    jobs/<id>/
      job.yaml  lexicon.yaml  sources/  bundle.json  facts.json  outline.json
      script/c1.json ...  timeline.json  audio/  build/  qa/  out/
      state.json      current state, pinned versions, budgets, tokens, timings
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from forge import ENGINE_VERSION
from forge.util import JOBS, read_json, read_yaml, write_json, write_yaml

STATES = [
    "intake", "resolve", "plan", "outline_review", "ground", "script", "validate", "narrate",
    "compile", "preview", "preview_review", "final_render", "deliver", "done",
]

# Budgets stop runaway loops (see the spec's control loop).
REPAIRS_PER_BEAT = 2
RETRIES_PER_CHAPTER = 3


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "job"


class Job:
    def __init__(self, job_id: str, root: Path | None = None):
        self.id = job_id
        self.dir = (root or JOBS) / job_id
        if not self.dir.is_dir():
            raise FileNotFoundError(f"no job {job_id!r} in {self.dir.parent}")

    # ---------------- creation ----------------
    @classmethod
    def create(cls, job_id: str, *, template: str, style: str, content: str = "", sources=(), title: str = "",
               lang: str = "en-GB", region: str | None = None, target_minutes: float | None = None,
               review: dict | None = None, overrides: dict | None = None, root: Path | None = None) -> "Job":
        folder = (root or JOBS) / job_id
        folder.mkdir(parents=True, exist_ok=True)
        spec = {
            "id": job_id, "title": title or job_id.replace("-", " ").title(), "template": template,
            "style": style, "lang": lang, "brief": content, "sources": list(sources),
            "region": region, "target_minutes": target_minutes,
            "review": review or {"outline": False, "preview": False},
            "overrides": overrides or {},   # voice:, music:, motion: -- the top of the precedence stack
            "quality": "m", "phone": True,
        }
        write_yaml(folder / "job.yaml", spec)
        if not (folder / "lexicon.yaml").exists():
            write_yaml(folder / "lexicon.yaml", {})
        job = cls(job_id, root)
        job.save_state({"state": "intake", "history": [], "created": time.time(), "engine": ENGINE_VERSION,
                        "versions": {}, "budgets": {"repairs": {}, "retries": {}}, "tokens": {"in": 0, "out": 0},
                        "cost_usd": 0.0, "timings": {}, "waived": [], "open_questions": [], "human_review": [],
                        "errors": []})
        return job

    # ---------------- files ----------------
    @property
    def spec(self) -> dict:
        return read_yaml(self.dir / "job.yaml")

    def update_spec(self, **changes) -> None:
        spec = self.spec
        spec.update(changes)
        write_yaml(self.dir / "job.yaml", spec)

    @property
    def lexicon(self) -> dict:
        return read_yaml(self.dir / "lexicon.yaml") or {}

    def path(self, *parts) -> Path:
        return self.dir.joinpath(*parts)

    def read(self, name: str, default=None):
        return read_json(self.path(name), default)

    def write(self, name: str, data) -> None:
        write_json(self.path(name), data)

    def chapter_ids(self) -> list[str]:
        outline = self.read("outline.json", {}) or {}
        return [c["id"] for c in outline.get("chapters", [])]

    def script(self, chapter_id: str) -> dict:
        return self.read(f"script/{chapter_id}.json", {}) or {}

    def write_script(self, chapter_id: str, script: dict) -> None:
        self.write(f"script/{chapter_id}.json", script)

    # ---------------- state ----------------
    @property
    def state(self) -> dict:
        return read_json(self.path("state.json"), {}) or {}

    def save_state(self, state: dict) -> None:
        write_json(self.path("state.json"), state)

    def set_state(self, name: str, note: str = "", **extra) -> None:
        state = self.state
        state["state"] = name
        state["history"].append({"state": name, "at": round(time.time(), 1), "note": note})
        state.update(extra)
        self.save_state(state)

    def note(self, key: str, value) -> None:
        state = self.state
        if isinstance(state.get(key), list):
            if value not in state[key]:
                state[key].append(value)
        else:
            state[key] = value
        self.save_state(state)

    def log(self, message: str) -> None:
        with open(self.path("forge.log"), "a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')}  {message}\n")
        print(f"[{self.id}] {message}", flush=True)

    def spend(self, tokens_in: int = 0, tokens_out: int = 0, cost: float = 0.0) -> None:
        state = self.state
        state["tokens"]["in"] += tokens_in
        state["tokens"]["out"] += tokens_out
        state["cost_usd"] = round(state.get("cost_usd", 0.0) + cost, 5)
        self.save_state(state)

    def budget(self, kind: str, key: str, limit: int) -> bool:
        """Spend one unit of a budget. False once it is used up."""
        state = self.state
        used = state["budgets"].setdefault(kind, {})
        if used.get(key, 0) >= limit:
            return False
        used[key] = used.get(key, 0) + 1
        self.save_state(state)
        return True


def list_jobs(root: Path | None = None) -> list[dict]:
    folder = root or JOBS
    out = []
    if folder.is_dir():
        for child in sorted(folder.iterdir()):
            state = read_json(child / "state.json", None)
            spec = read_yaml(child / "job.yaml")
            if state and spec:
                out.append({"id": child.name, "title": spec.get("title"), "template": spec.get("template"),
                            "style": spec.get("style"), "state": state.get("state"),
                            "updated": state["history"][-1]["at"] if state.get("history") else state.get("created")})
    return out
