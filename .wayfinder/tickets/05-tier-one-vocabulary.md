---
id: 5
title: How generation is held inside the exporter's vocabulary
labels: [wayfinder:grilling]
parent: 1
blocked_by: []
assignee: null
state: open
---

## Question

A model writing free-form Manim will regularly write Manim this exporter cannot
express. The failure is quiet: the scene still exports, as **tier 3 sampled
IR**, which measured 1.2 MB against a 277-byte program on the sample scene.
Silently shipping something a thousand times larger is worse than refusing.

Decide how generation is constrained. Candidates, not exclusive:

- **Prompt-only.** Hand the model the supported vocabulary and trust it.
- **Validate and repair.** Export, read the exporter's own blocker list, feed the
  blockers back and regenerate. The exporter already emits exactly this — it
  writes `<Scene>.tier.json` with a `blockers` array naming what it could not
  express.
- **Constrain by template.** A template fixes which vocabulary is in play, and
  the model fills a much smaller hole.
- **Extend the DSL** so more Manim is expressible. Moves cost into this repo and
  is the only option that changes the format.
- **Refuse tier 3.** Treat a tier-3 verdict as a generation failure rather than a
  fallback, and retry.

The decision is really about where the loop closes and how many attempts a user
pays for. [Which models write Manim the exporter accepts](03-openrouter-model-capability.md)
supplies the failure rates; this decides the response to them.

Three tickets wait on this: the schema, the worker contract, and what a template
turns out to be.
