"""Lecture Forge: content + a video template + a style pack -> a narrated, animated MP4.

The template decides what happens, the style decides how it looks and sounds,
and the content decides what it is about. Model workers only ever write
content into a template's structure; they never write styling or code.

    forge/machine.py     the orchestrator: job state machine, loops, budgets
    forge/tools.py       the tool router: read-only lookups and engine tools
    forge/workers.py     planner, fact extractor, script writer, repairer
    forge/gates.py       the quality gates, with their deterministic fixes
    forge/engine/        ingest, narrate, compile, render, assemble, learn
    forge/registry.py    styles, templates and region packs, resolved
"""

ENGINE_VERSION = "0.6.0"
