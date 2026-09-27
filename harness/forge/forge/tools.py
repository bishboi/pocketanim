"""The tool router.

Two kinds of tool. Read-only lookups are what a model worker may call; they
answer from the libraries and the job's own files and change nothing. Every
tool that writes files, synthesises speech or renders is called by the
orchestrator alone. Both kinds are keyed by a hash of their inputs where they
compute, so a retried or resumed job reuses what already finished.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from forge import region, registry


@dataclass
class Tool:
    name: str
    fn: Callable
    read_only: bool
    doc: str
    params: dict


TOOLS: dict[str, Tool] = {}


def tool(name: str, doc: str, params: dict | None = None, read_only: bool = True):
    def wrap(fn):
        TOOLS[name] = Tool(name, fn, read_only, doc, params or {})
        return fn
    return wrap


# ---------------- read-only: what model workers may call ----------------

@tool("template.describe", "Arc, beat patterns, required and allowed operations, word budgets.",
      {"template": "string"})
def template_describe(template: str, **_):
    t = registry.load_template(template)
    return {
        "id": t["id"], "label": t.get("label"), "words_per_minute": t.get("words_per_minute", 143),
        "beat_words": t.get("beat_words", {"min": 8, "max": 40}), "layouts": t.get("layouts", {}),
        "requires_ops": t.get("requires_ops", []),
        "arc": [{k: s.get(k) for k in ("id", "title", "purpose", "share", "required", "min_phases")} for s in t["arc"]],
        "patterns": {pid: {"description": p.get("description"), "slots": p.get("slots"),
                           "lines": sorted(set(re.findall(r"\{(\w+)\}", " ".join(b.get("say", "") for b in p.get("beats", [])))))}
                     for pid, p in t["patterns"].items()},
    }


@tool("style.vocabulary", "Roles, unit kinds, text entrance and the writing tone rules of a style.",
      {"style": "string"})
def style_vocabulary(style: str, template: str | None = None, **_):
    s = registry.resolve_style(style, template)
    return {"id": s["id"], "label": s.get("label"), "roles": sorted(s.get("roles") or {}),
            "unit_kinds": ["infantry", "cavalry", "artillery", "navy"],
            "entrance": (s.get("motion") or {}).get("entrance"), "writing": s.get("writing", "")}


@tool("ops.schema", "The JSON schema of each named operation (all when none named).", {"names": "array"})
def ops_schema(names=None, **_):
    every = registry.ops()
    return {n: every[n] for n in (names or every) if n in every}


@tool("region.find", "Region packs for a place name.", {"name": "string"})
def region_find(name: str, **_):
    return region.find(name)


@tool("region.index", "Anchors, features, units, places and rivers a script may name in a region.",
      {"region": "string"})
def region_index(region_id: str = "", region_: str = "", **kw):
    return region.index(region_id or kw.get("region") or region_)


@tool("gazetteer.lookup", "A place's canonical id and lon/lat, inside a region when given.",
      {"place": "string", "region": "string"})
def gazetteer_lookup(place: str, region_id: str | None = None, **kw):
    return region.lookup(place, region_id or kw.get("region")) or {"found": False, "place": place}


@tool("facts.query", "Fact rows for a chapter id or a keyword.", {"chapter": "string", "keyword": "string"})
def facts_query(job=None, chapter: str | None = None, keyword: str | None = None, **_):
    facts = (job.read("facts.json", {}) or {}).get("facts", []) if job else []
    if chapter:
        outline = job.read("outline.json", {}) or {}
        wanted = next((c.get("facts", []) for c in outline.get("chapters", []) if c["id"] == chapter), [])
        passages = next((c.get("passages", []) for c in outline.get("chapters", []) if c["id"] == chapter), [])
        facts = [f for f in facts if f["id"] in wanted or f["source"] in passages]
    if keyword:
        k = keyword.lower()
        facts = [f for f in facts if k in f["claim"].lower()]
    return facts


@tool("sources.search", "Passages matching a query, best first.", {"query": "string"})
def sources_search(job=None, query: str = "", limit: int = 6, **_):
    bundle = job.read("bundle.json", {}) or {} if job else {}
    terms = {t for t in re.findall(r"\w+", query.lower()) if len(t) > 2}
    scored = []
    for p in bundle.get("passages", []):
        text = p["text"].lower()
        score = sum(text.count(t) for t in terms)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda row: -row[0])
    return [p for _, p in scored[:limit]]


@tool("lexicon.suggest", "Respellings for proper nouns the voice may say wrongly.", {"nouns": "array"})
def lexicon_suggest(nouns=None, job=None, **_):
    """Known respellings: the job's lexicon first, then the engine's SAY table.

    Nouns with no entry come back unchanged, listed so the planner can add
    them to lexicon.yaml; the phoneme audit catches what still goes wrong.
    """
    import pocket_lecture as pl

    lexicon = job.lexicon if job else {}
    out, unknown = {}, []
    for noun in nouns or []:
        if noun in lexicon:
            out[noun] = lexicon[noun]
        elif noun in pl.SAY:
            out[noun] = pl.SAY[noun]
        else:
            unknown.append(noun)
    return {"respellings": out, "unknown": unknown}


def read_only_tools() -> list[Tool]:
    return [t for t in TOOLS.values() if t.read_only]


def call(name: str, job=None, **args):
    """Run a tool by name. The orchestrator's single entry point."""
    if name not in TOOLS:
        raise KeyError(f"no tool {name!r}")
    return TOOLS[name].fn(job=job, **args)


def register_engine_tools() -> None:
    """The write-and-compute tools, bound to the engine stages.

    Imported lazily: the engine pulls in Manim and Cartopy, which a model
    worker's lookups do not need.
    """
    from forge.engine import assemble, ingest, learn, narrate, qa, render
    from forge import gates
    from forge.engine import compile as compile_

    engine = {
        "ingest.file": (ingest.intake, "Clean sources into passages."),
        "registry.resolve": (registry.resolve_style, "Resolve a style with its parents and overrides."),
        "registry.check_compat": (registry.check_compat, "Can this style draw this template?"),
        "region.build": (region.build, "Build and cache an automatic region pack."),
        "validate.schema": (gates.schema_gate, "Schema gate."),
        "validate.facts": (gates.facts_gate, "Facts gate."),
        "validate.template_fit": (gates.template_gate, "Template-fit gate."),
        "validate.glyphs": (gates.glyph_gate, "Glyph gate."),
        "validate.layout": (gates.layout_gate, "Layout gate."),
        "validate.motion": (gates.motion_gate, "Motion gate."),
        "tts.synth": (narrate.narrate_job, "Speak every beat, cached by text and voice."),
        "tts.audit": (narrate.audit, "Phoneme audit of the synthesised lines."),
        "compile.chapter": (compile_.compile_job, "Scene code per chapter."),
        "render.preview": (render.preview, "480p15 chapter renders."),
        "render.chapter": (render.final, "Final chapter renders."),
        "qa.contact_sheet": (qa.contact_sheet, "One frame per beat, tiled."),
        "qa.audio": (qa.audio_check, "Loudness and music level."),
        "assemble.video": (assemble.deliver, "Join, mix, subtitles, chapters."),
        "extract.palette": (learn.extract_palette, "Palette of an example video or image."),
    }
    for name, (fn, doc) in engine.items():
        if name not in TOOLS:
            TOOLS[name] = Tool(name, fn, False, doc, {})
