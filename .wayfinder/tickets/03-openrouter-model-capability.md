---
id: 3
title: Which models write Manim the exporter accepts
labels: [wayfinder:research]
parent: 1
blocked_by: []
assignee: null
state: open
---

## Question

The harness is only as good as the Manim the model writes. Establish, with
evidence rather than reputation, which OpenRouter-hosted models can write Manim
0.21 that this repo's exporter turns into a **tier-1 program**.

The bar is specific and unusually strict. `dsl/export_dsl.py` supports a narrow
vocabulary — `Circle`, `Square`, `Rectangle`, `Text`/`Tex`/`MathTex`, `Surface`,
baked groups, and the animations `Write`, `Create`, `FadeIn`/`FadeOut`,
`Transform`, `TransformMatchingTex`, `LaggedStart`+`GrowFromCenter`,
`.animate.scale().shift()`, camera moves and ambient rotation. Anything else is
recorded as a blocker and the scene falls to tier 3, which is roughly a
thousand times larger.

Answer these:

- Which models are worth testing, at what cost per million tokens on OpenRouter?
- For a few candidates, what fraction of generated scenes export at tier 1
  without repair? Use the vocabulary above as the prompt's constraint.
- What do they get wrong most often? The failure *modes* matter more than the
  rate: a model that reaches for `ValueTracker` needs a different fix from one
  that miscounts `run_time`.
- Roughly how many tokens does one scene cost, input and output?

Do not decide how to constrain generation here — that is
[How generation is held inside the exporter's vocabulary](05-tier-one-vocabulary.md).
This ticket supplies the facts that decision needs.
