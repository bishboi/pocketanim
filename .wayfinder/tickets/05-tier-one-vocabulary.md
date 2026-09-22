---
id: 5
title: How generation is kept from silently producing a wrong scene
labels: [wayfinder:answered]
parent: 1
blocked_by: []
assignee: null
state: answered
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

## Answer

**Fix the exporter.** Not chosen on argument — the option list above was written
before the evidence, and the evidence settled it.

All three examples in the question are fixed in this repo, and three more of the
same kind were found while fixing them:

| Silently wrong at tier 1 | Status |
|---|---|
| `Circle().shift(...)` drawn at the origin | fixed — `at=` is emitted |
| `play(Create(a), Create(b))` playing for the sum of its parts | fixed — `par` verb |
| `Write(Circle())` crashing the player | fixed — blocker, falls to tier 3 |
| `set_camera_orientation(zoom=0.9)` drawing every frame 11% too large | fixed — `zoom` is a camera field |
| `begin_ambient_camera_rotation(about="phi")` spinning the wrong axis | fixed — blocker |
| `play(..., rate_func=linear)` easing anyway | fixed — `rate=` is emitted |

**Why a harness-side pre-flight gate does not answer this ticket.** Every one of
the six is the exporter reading a value and dropping it. A gate that parses
generated source can only refuse constructs; it cannot make `zoom=0.9` arrive,
because the information is lost *after* the source is accepted. A gate would
have had to ban `set_camera_orientation(zoom=...)` outright — banning correct
Manim to work around a defect in the emitter.

**What the harness should take from this instead:**

1. **Trust `tier` and `blockers`, and nothing else.** A blocker is honest: the
   scene falls to tier 3 and still renders correctly. The danger was never
   tier 3; it was tier 1 with an empty blocker list.
2. **The vocabulary is not the risk.** Geometry never blocks
   ([research 03](../research/03-openrouter-model-capability.md)), and the
   animation set is wide. Constraining generation to a "safe subset" would have
   prevented none of the six, because all six are constructs the exporter
   accepts.
3. **The seam to audit is Manim's API against the emitter**, not the generated
   source. The check that found the last two: diff what each patched entry point
   *accepts* against what it *reads*. That is a standing job for this repo,
   not the harness.

Ticket 6 and ticket 7 are unblocked: neither needs a vocabulary constraint.

## The gap this answer named, then closed

The first audit covered the patched entry points' signatures and not `declare()`.
Looking there found three more, and they are the most ordinary constructs of the
nine:

| Silently wrong at tier 1 | Status |
|---|---|
| `Square(fill_opacity=1)` drawn as an empty outline | fixed — bakes as a geom asset |
| `Square(2).rotate(PI/4)` drawn axis-aligned at bounding-box size | fixed — bakes as a geom asset |
| `Circle(1).stretch(2, 0)` drawn as a circle | fixed — bakes as a geom asset |

A filled shape is not an exotic thing for a model to write; it is the first
thing most people write. This strengthens point 2 above rather than weakening
it — the danger is not an unusual vocabulary, it is an ordinary one the emitter
reads carelessly.

**Still not audited:** the animation branches of `patched_play` read specific
attributes off each animation (`anim.mobject`, `anim.point`, chain arguments for
`.animate`). The same class could live there. No instance is known; none has
been looked for.
