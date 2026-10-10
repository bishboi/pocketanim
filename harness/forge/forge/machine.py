"""The orchestrator: one job through the control loop, resumable at every state.

    intake -> resolve -> plan -> (outline review) -> ground -> script -> validate
      -> narrate -> compile -> preview -> (preview review) -> final render -> deliver

Plain code owns the loop; model workers are called for one job each and never
see the loop. The three ways back are all at beat level where they can be:

    repair   a gate fails a beat: its deterministic fix, then a targeted model
             repair of that beat (REPAIRS_PER_BEAT), then a chapter retry
             (RETRIES_PER_CHAPTER), then a person.
    QA fail  a render fails: that chapter only is compiled and rendered again.
    revise   a person's note on c6.b07 edits that beat; c6 rewrites the chapter;
             outline re-plans. Every later stage is cached by content, so only
             what the note changed is spoken and rendered again.

state.json is written after every state, so `forge make` resumes where a job
stopped: a review point, a budget run out, a crash.
"""

from __future__ import annotations

import copy
from pathlib import Path
import json
import re
import time
import traceback

from forge import gates, llm, region, registry, workers
from forge.engine import assemble, compile as compile_, ingest, narrate, qa, render
from forge.job import REPAIRS_PER_BEAT, RETRIES_PER_CHAPTER, STATES, Job
from forge.util import digest, write_json

UNTIL = {"outline": "plan", "script": "validate", "preview": "preview"}
# The workers' own code is an input of their output: a better writer rewrites cached scripts.
WORKERS = digest(Path(workers.__file__))


class Stop(Exception):
    """A state that cannot go on without a person: a review point or a blocker."""

    def __init__(self, state: str, reason: str):
        super().__init__(reason)
        self.state = state
        self.reason = reason


class Run:
    def __init__(self, job: Job, quality: str | None = None, accept: bool = False):
        self.job = job
        self.quality = quality
        self.accept = accept

    # ---------------- shared ----------------
    @property
    def spec(self) -> dict:
        return self.job.spec

    def template(self) -> dict:
        return registry.load_template(self.spec["template"])

    def style(self) -> dict:
        return registry.resolve_style(self.spec["style"], self.spec["template"], self.spec.get("overrides") or {})

    def notes(self) -> dict:
        return self.job.read("revisions.json", {}) or {}

    # ---------------- states ----------------
    def intake(self):
        bundle = ingest.intake(self.job)
        for problem in bundle["problems"]:
            self.job.note("open_questions", f"source unreadable: {problem}")
        if not bundle["passages"]:
            raise Stop("intake", "there is no readable content: give a brief or a source file")
        self.job.log(f"intake: {len(bundle['passages'])} passages, {bundle['words']} words")
        return "resolve"

    def resolve(self):
        self._auto()
        spec = self.spec
        template = self.template()
        style = self.style()
        problems = registry.check_compat(template, style, spec.get("lang", "en"))
        if problems:
            nearest = registry.nearest_compatible(template, style["id"], spec.get("lang", "en"))
            hint = f"; `forge restyle {self.job.id} {nearest}` would fit" if nearest else ""
            self.job.note("human_review", {"state": "resolve", "problems": problems, "suggest": nearest})
            raise Stop("resolve", "; ".join(problems) + hint)
        region_id = None
        wants_map = any(registry.ops().get(op, {}).get("map") for op in template.get("requires_ops", []))
        for query in [spec.get("region")] + ([spec.get("title"), spec.get("brief", "")[:300]] if wants_map else []):
            if query:
                hits = region.find(query)
                if hits:
                    region_id = hits[0]["id"]
                    break
        if wants_map and not region_id:
            raise Stop("resolve", f"template {template['id']} draws maps; name the place with --region")
        versions = {"engine": self.job.state.get("engine"), "template": [template["id"], template.get("version")],
                    "style": [style["id"], style.get("version")], "style_chain": style.get("chain"),
                    "model": llm.model_name() if llm.available() else "offline"}
        if region_id:
            versions["region"] = [region_id, region.load(region_id).get("version", "auto")]
        self.job.update_spec(region_id=region_id)
        state = self.job.state
        state["versions"] = versions
        self.job.save_state(state)
        self.job.log(f"resolve: {template['id']} x {style['id']} (via {' < '.join(style['chain'])}), "
                     f"region {region_id or 'none'}")
        return "plan"

    # The subject decides the template and style when the job leaves them to it.
    GENRE_TEMPLATE = {"geography": "geography_lecture", "history": "history_lecture", "biology": "science_explainer",
                      "chemistry": "science_explainer", "physics": "science_explainer",
                      "mathematics": "science_explainer", "economics": "explainer", "general": "explainer"}

    def _auto(self):
        from genre import classify   # harness/lecture

        spec = self.spec
        bundle = self.job.read("bundle.json") or {}
        text = " ".join(p["text"] for p in bundle.get("passages", []))[:40000] or spec.get("brief", "")
        subject = classify(text)
        changes = {"genre": subject["genre"]}
        if spec.get("template") == "auto":
            changes["template"] = self.GENRE_TEMPLATE[subject["genre"]]
        if spec.get("style") == "auto":
            changes["style"] = subject["style"] if subject["style"] in registry.styles() else "vox"
        self.job.update_spec(**changes)
        self.job.log(f"subject: {subject['label']} ({', '.join(subject['why']) or 'vocabulary'}) -> "
                     f"{changes.get('template', spec['template'])}, {changes.get('style', spec['style'])}")

    def plan(self):
        notes = self.notes().get("outline", "")
        key = digest("plan", WORKERS, self.job.read("bundle.json"), self.template().get("version"), self.spec.get("region_id"),
                     self.spec.get("target_minutes"), notes, llm.available())
        outline = self.job.read("outline.json")
        if not outline or outline.get("key") != key:
            outline = workers.plan(self.job, self.template(), self.style(), self.job.read("bundle.json"), notes)
            outline["key"] = key
            self.job.write("outline.json", outline)
        for question in outline.get("open_questions", []):
            self.job.note("open_questions", question)
        self.job.log(f"plan: {len(outline['chapters'])} chapters, {outline['target_minutes']:.1f} min: "
                     + ", ".join(c["title"] for c in outline["chapters"]))
        if (self.spec.get("review") or {}).get("outline"):
            raise Stop("outline_review", "the outline waits for review: `forge review` then `forge make`")
        return "ground"

    def outline_review(self):
        return "ground"      # reached only on resume: running `make` again is the approval

    def ground(self):
        outline = self.job.read("outline.json")
        facts = workers.ground(self.job, self.job.read("bundle.json"), outline)
        self.job.write("facts.json", facts)
        self.job.log(f"ground: {len(facts['facts'])} facts, {len(facts['numbers'])} numbers")
        return "script"

    def script(self):
        template, style = self.template(), self.style()
        outline, bundle, facts = self.job.read("outline.json"), self.job.read("bundle.json"), self.job.read("facts.json")
        notes = self.notes()
        for chapter in outline["chapters"]:
            if chapter["slot"] == "recap":
                continue          # written last: it sums up the chapters before it
            self._write(template, style, chapter, bundle, facts, outline, notes.get(chapter["id"], ""))
        for chapter in outline["chapters"]:
            if chapter["slot"] == "recap":
                self._write(template, style, chapter, bundle, facts, outline, notes.get(chapter["id"], ""), force=True)
        return "validate"

    def _write(self, template, style, chapter, bundle, facts, outline, note, force=False):
        raw_name = f"script/{chapter['id']}.raw.json"
        key = digest("script", WORKERS, chapter, facts, template.get("version"), note, llm.available())
        raw = self.job.read(raw_name)
        if raw and raw.get("key") == key and not force:
            return raw
        started = time.time()
        script = workers.write_chapter(self.job, template, style, chapter, bundle, facts, outline, note)
        script["key"] = key
        self.job.write(raw_name, script)
        # validate reads the chapter scripts for the recap; give it the draft until then
        if not self.job.path(f"script/{chapter['id']}.json").exists():
            self.job.write_script(chapter["id"], script)
        self.job.log(f"script {chapter['id']}: {len(script['beats'])} beats ({time.time() - started:.1f}s)")
        return script

    def validate(self):
        template, style = self.template(), self.style()
        outline, bundle, facts = self.job.read("outline.json"), self.job.read("bundle.json"), self.job.read("facts.json")
        report, blocking = {}, []
        state = self.job.state
        waived = [w for w in state.get("waived", []) if not isinstance(w, dict) or w.get("state") != "validate"]
        for chapter in outline["chapters"]:
            script = copy.deepcopy(self.job.read(f"script/{chapter['id']}.raw.json"))
            script, errors = gates.run_all(self.job, template, style, chapter, script, facts)
            script, errors = self._repair(template, style, chapter, bundle, facts, outline, script, errors)
            self.job.write_script(chapter["id"], script)
            report[chapter["id"]] = {"beats": len(script["beats"]), "errors": errors}
            for error in errors:
                if error["repairable"] and not self.accept:
                    blocking.append(error)
                else:
                    waived.append({"state": "validate", **error})
        state = self.job.state
        state["waived"] = waived
        self.job.save_state(state)
        write_json(self.job.path("qa", "gates.json"), report)
        total = sum(len(r["errors"]) for r in report.values())
        self.job.log(f"validate: {sum(r['beats'] for r in report.values())} beats, {total} open finding(s), "
                     f"{len(blocking)} blocking")
        if blocking:
            self.job.note("human_review", {"state": "validate", "errors": blocking})
            raise Stop("validate", f"{len(blocking)} beat(s) failed their gates after the repair budget: see "
                                   "qa/gates.json; `forge revise` them or `forge make --accept`")
        return "narrate"

    def _repair(self, template, style, chapter, bundle, facts, outline, script, errors):
        """Targeted repairs, then a chapter retry, within budget."""
        for _ in range(REPAIRS_PER_BEAT):
            broken = [e for e in errors if e["repairable"] and e.get("beat")]
            if not broken or not llm.available():
                break
            by_beat = {}
            for e in broken:
                by_beat.setdefault(e["beat"], []).append(e["message"])
            changed = False
            for bid, messages in by_beat.items():
                index = next((i for i, b in enumerate(script["beats"]) if b["id"] == bid), None)
                if index is None or not self.job.budget("repairs", f"{chapter['id']}.{bid}", REPAIRS_PER_BEAT):
                    continue
                try:
                    fixed = workers.repair_beat(self.job, template, chapter, script, index, messages)
                except Exception as error:  # noqa: BLE001 -- a failed repair leaves the beat for the next rung
                    self.job.log(f"repair {chapter['id']}.{bid}: {error}")
                    continue
                if fixed:
                    script["beats"][index] = {**script["beats"][index], **fixed}
                    changed = True
            if not changed:
                break
            script, errors = gates.run_all(self.job, template, style, chapter, script, facts)
        if any(e["repairable"] for e in errors) and llm.available() \
                and self.job.budget("retries", chapter["id"], RETRIES_PER_CHAPTER):
            note = "Fix: " + "; ".join(sorted({e["message"] for e in errors if e["repairable"]}))[:1500]
            self.job.log(f"retry {chapter['id']}: {note[:120]}")
            try:
                fresh = workers.write_chapter(self.job, template, style, chapter, bundle, facts, outline, note)
                fresh, fresh_errors = gates.run_all(self.job, template, style, chapter, fresh, facts)
                if len(fresh_errors) < len(errors):
                    script, errors = fresh, fresh_errors
            except Exception as error:  # noqa: BLE001
                self.job.log(f"retry {chapter['id']} failed: {error}")
        return script, errors

    def narrate(self):
        style = self.style()
        timeline = narrate.narrate_job(self.job, self.template(), style)
        audit = narrate.audit(self.job)
        for warning in timeline["warnings"]:
            self.job.log(f"timing: {warning}")
        self.job.log(f"narrate: {timeline['voice']}, about {timeline['total_seconds'] / 60:.1f} min "
                     f"(target {timeline['target_seconds'] / 60:.1f}); "
                     f"{len(audit['unknown_names'])} name(s) without a respelling")
        return "compile"

    def compile(self):
        manifest = compile_.compile_job(self.job, self.template(), self.style())
        self.job.log(f"compile: {len(manifest)} scene files")
        return "preview"

    def _voice(self) -> str:
        return (self.job.read("timeline.json") or {}).get("voice") or narrate.voice_mode(self.style())

    def _render(self, quality: str) -> dict:
        results = render.render(self.job, quality, self._voice())
        failed = {cid: r for cid, r in results.items() if r.get("error")}
        if failed:
            # QA fail, chapter level: the likeliest cause is one operation the
            # engine rejects. Drop the beat's operations the error names, keep
            # its narration, and render that chapter again, within budget.
            for cid, r in failed.items():
                if self.job.budget("retries", f"render.{cid}", RETRIES_PER_CHAPTER):
                    self.job.log(f"render {cid}: {r['error']}; retrying without the failing operations")
                    self._strip_failing(cid, r)
            compile_.compile_job(self.job, self.template(), self.style())
            again = render.render(self.job, quality, self._voice(), only=list(failed))
            results.update(again)
            failed = {cid: r for cid, r in results.items() if r.get("error")}
        write_json(self.job.path("build", f"renders-{quality}.json"), results)
        if failed:
            self.job.note("human_review", {"state": "render", "chapters": {c: r["error"] for c, r in failed.items()}})
            raise Stop("preview" if quality == "l" else "final_render",
                       "chapter(s) " + ", ".join(failed) + " failed to render: see build/renders/*.err")
        return results

    def _strip_failing(self, chapter_id: str, result: dict):
        """Find the beat whose line the traceback names; drop that beat's operations."""
        text = open(result["stderr"], encoding="utf-8").read() if result.get("stderr") else ""
        script = self.job.script(chapter_id)
        lineno = None
        for m in re.finditer(rf"{chapter_id}\.py\", line (\d+)", text):
            lineno = int(m.group(1))
        if lineno is None:
            return
        source = self.job.path("build", f"{chapter_id}.py").read_text(encoding="utf-8").splitlines()
        bid = None
        for line in reversed(source[:lineno]):
            m = re.match(r"\s+# (b\d+)$", line)
            if m:
                bid = m.group(1)
                break
        for beat in script.get("beats", []):
            if beat["id"] == bid:
                self.job.log(f"{chapter_id}.{bid}: dropped {[o['op'] for o in beat['do']]} after a render failure")
                self.job.note("waived", {"state": "render", "chapter": chapter_id, "beat": bid,
                                         "message": "operations dropped after a render failure"})
                beat["do"] = []
        self.job.write_script(chapter_id, script)

    def preview(self):
        results = self._render("l")
        labels = {c["id"]: compile_.line_ids(c, self.job.script(c["id"])) for c in self.job.read("outline.json")["chapters"]}
        sheet = qa.contact_sheet(self.job, results, labels, self.job.path("qa", "preview_sheet.png"))
        self.job.log(f"preview: {len(results)} chapters; contact sheet {sheet.get('file')}")
        if (self.spec.get("review") or {}).get("preview"):
            raise Stop("preview_review", "the preview waits for review: qa/preview_sheet.png, then `forge make`")
        return "final_render"

    def preview_review(self):
        return "final_render"

    def final_render(self):
        quality = self.quality or self.spec.get("quality", "m")
        self._render(quality)
        return "deliver"

    def deliver(self):
        quality = self.quality or self.spec.get("quality", "m")
        results = self.job.read(f"build/renders-{quality}.json") or self._render(quality)
        report = assemble.deliver(self.job, self.template(), self.style(), results,
                                  gate_report=self.job.read("qa/gates.json"), phone=bool(self.spec.get("phone")))
        out = report["output"]
        self.job.log(f"deliver: {report['delivered']['video']} ({out['seconds']:.0f}s, "
                     f"{out['loudness_lufs']} LUFS, music {out['music_under_speech_db']} dB under)")
        for key in ("loudness_ok", "music_ok", "length_ok"):
            if out.get(key) is False:
                self.job.log(f"output gate: {key.replace('_ok', '')} outside its bound (see qa/report.json)")
        return "done"


def run(job: Job, until: str | None = None, quality: str | None = None, accept: bool = False) -> dict:
    """Drive a job from its current state; stop at `until`, a review point, a blocker or done."""
    runner = Run(job, quality, accept)
    stop_after = UNTIL.get(until or "", None)
    if quality:
        job.update_spec(quality=quality)
    while True:
        name = job.state["state"]
        if name == "done":
            return {"state": "done", "report": job.read("qa/report.json")}
        started = time.time()
        try:
            following = getattr(runner, name)()
        except Stop as stop:
            job.set_state(stop.state, stop.reason)
            job.log(f"stopped at {stop.state}: {stop.reason}")
            return {"state": stop.state, "stopped": stop.reason}
        except Exception as error:  # noqa: BLE001 -- recorded; the job resumes from this state
            state = job.state
            state["errors"].append({"state": name, "at": round(time.time(), 1), "error": f"{type(error).__name__}: {error}",
                                    "trace": traceback.format_exc()[-3000:]})
            job.save_state(state)
            job.log(f"error in {name}: {type(error).__name__}: {error}")
            return {"state": name, "error": f"{type(error).__name__}: {error}"}
        state = job.state
        state.setdefault("timings", {})[name] = round(time.time() - started, 1)
        job.save_state(state)
        job.set_state(following, f"{name} done")
        if stop_after and name == stop_after:
            return {"state": following, "stopped": f"--until {until}"}


# ════════════════════════════════════════════════════════════════════════
#  Revisions: the third loop back
# ════════════════════════════════════════════════════════════════════════

def revise(job: Job, note: str) -> dict:
    """Apply "c6.b07: note", "c6: note" or "outline: note" and rewind the job to the state it touches.

    A beat note is applied at once when it is mechanical ("say: new line",
    "drop", "ops: []") or by the repair worker when there is a model. A
    chapter note rewrites that chapter; an outline note re-plans.
    """
    m = re.match(r"\s*(outline|c\d+)(?:\.(b\d+))?\s*:\s*(.+)$", note, re.S)
    if not m:
        raise ValueError('a revision is "c6.b07: note", "c6: note" or "outline: note"')
    target, beat_id, text = m.group(1), m.group(2), m.group(3).strip()
    notes = job.read("revisions.json", {}) or {}
    history = notes.setdefault("history", [])
    history.append({"at": round(time.time(), 1), "target": f"{target}{'.' + beat_id if beat_id else ''}", "note": text})
    if target == "outline":
        notes["outline"] = (notes.get("outline", "") + "\n" + text).strip()
        job.write("revisions.json", notes)
        job.set_state("plan", f"revise outline: {text[:80]}")
        return {"rewind": "plan"}
    if target not in job.chapter_ids():
        raise ValueError(f"no chapter {target}; have {', '.join(job.chapter_ids())}")
    if not beat_id:
        if not job.budget("retries", target, RETRIES_PER_CHAPTER):
            raise ValueError(f"{target} has used its {RETRIES_PER_CHAPTER} retries; edit its beats directly")
        notes[target] = (notes.get(target, "") + "\n" + text).strip()
        job.write("revisions.json", notes)
        job.set_state("script", f"revise {target}: {text[:80]}")
        return {"rewind": "script", "chapter": target}

    script = job.script(target)
    index = next((i for i, b in enumerate(script.get("beats", [])) if b["id"] == beat_id), None)
    if index is None:
        raise ValueError(f"no beat {beat_id} in {target}")
    beat = script["beats"][index]
    how = "model"
    if text.lower() in ("drop", "delete", "remove"):
        script["beats"].pop(index)
        how = "dropped"
    elif text.lower().startswith("say:"):
        beat["say"] = text[4:].strip()
        beat.pop("say_caption", None)
        how = "narration replaced"
    elif text.lower().startswith("ops:") or text.lower().startswith("do:"):
        beat["do"] = json.loads(text.split(":", 1)[1])
        how = "operations replaced"
    else:
        template = registry.load_template(job.spec["template"])
        chapter = next(c for c in job.read("outline.json")["chapters"] if c["id"] == target)
        fixed = workers.repair_beat(job, template, chapter, script, index, [f"Reviewer's note: {text}"])
        if fixed is None:
            job.note("human_review", {"state": "revise", "beat": f"{target}.{beat_id}", "note": text,
                                      "why": "no model to apply a free-text note; use 'say:', 'ops:' or 'drop'"})
            job.write("revisions.json", notes)
            return {"rewind": None, "applied": False,
                    "why": "offline: a free-text note needs a model. Use 'say: ...', 'ops: [...]' or 'drop'."}
        script["beats"][index] = {**beat, **fixed}
    for i, b in enumerate(script["beats"], 1):
        b["id"] = f"b{i:02d}"
    raw = job.read(f"script/{target}.raw.json") or {}
    script["key"] = raw.get("key")
    job.write(f"script/{target}.raw.json", script)
    job.write_script(target, script)
    job.write("revisions.json", notes)
    job.set_state("validate", f"revise {target}.{beat_id}: {how}")
    return {"rewind": "validate", "applied": True, "how": how}


def restyle(job: Job, style_id: str) -> dict:
    """Keep the words; change the look and the voice. Rewinds to validate (glyphs, layout)."""
    template = registry.load_template(job.spec["template"])
    style = registry.resolve_style(style_id, template["id"], job.spec.get("overrides") or {})
    problems = registry.check_compat(template, style, job.spec.get("lang", "en"))
    if problems:
        raise ValueError("; ".join(problems))
    job.update_spec(style=style_id)
    current = job.state["state"]
    # Scripts stand; the gates that depend on the style (glyphs, layout) run again.
    rewind = "validate" if STATES.index(current) > STATES.index("validate") else current
    if current == "resolve":
        rewind = "resolve"
    job.set_state(rewind, f"restyle to {style_id}")
    return {"rewind": rewind, "style": style_id}
