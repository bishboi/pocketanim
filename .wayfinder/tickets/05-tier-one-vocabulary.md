---
id: 5
title: How generation is kept from silently producing a wrong scene
labels: [wayfinder:grilling]
parent: 1
blocked_by: []
assignee: null
state: open
---

## Question

**Rewritten after [Which models write Manim the exporter accepts](03-openrouter-model-capability.md).**
This ticket originally asked how to keep generation inside a vocabulary so
scenes would not fall to tier 3. That premise was wrong in a way worth stating:
geometry never blocks, the tier-3 cliff is far narrower than assumed, and the
real failure is **a scene that exports at tier 1 and is wrong**.

Three verified examples, all of which a model would write without hesitation:

- A circle shifted to (4, 2) exports at tier 1 and draws at the origin — the
  `circle` emitter carries no position at all.
- `self.play(Create(a), Create(b), run_time=2)` plays for 4.03 s instead of 2 s,
  because concurrent animations become sequential verbs.
- `Write(Circle())` exports at tier 1 and crashes the player with a `KeyError`.

Decide the response. The options are no longer about prompting:

- **Fix the exporter.** These are defects in *this* repo — the position is
  simply not emitted. Lands in pocketanim rather than the harness, and is the
  only option that helps every consumer of the format. Recorded in `docs/SPEC.md`.
- **A static pre-flight gate in the harness.** Parse generated source, refuse
  the constructs known to mislead, ask the model again with the specific
  violation. Roughly 60 lines of AST work. Catches what the exporter cannot,
  because the exporter has already lost the information by then.
- **Post-generation transform.** Rewrite `play(A(), B())` into a form that
  survives, rather than rejecting it.
- **Constrain by template**, so a template's preamble only exposes constructs
  known to be safe.

The user has ruled out an **orchestrator loop** — no agent that builds then
fixes in a cycle. That does not rule out a single deterministic gate before the
human ever sees the output, and the distinction is worth being explicit about
when this is decided.
