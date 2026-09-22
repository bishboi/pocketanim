---
id: 3
title: Which models write Manim the exporter accepts
labels: [wayfinder:research]
parent: 1
blocked_by: []
assignee: opus-5
state: closed
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

## Resolution

Answered, and **it inverts the question ticket 5 was asking**. Findings:
[03-openrouter-model-capability.md](../research/03-openrouter-model-capability.md)
(34 single-construct probe scenes run against the real exporter).

**The danger is not tier 3. It is tier 1 with wrong output.** Three of the
findings were re-verified independently before being recorded here:

- **Geometry never blocks.** `declare`'s catch-all at `export_dsl.py:206` bakes
  any drawable mobject as a tier-2 asset, and the `unsupported mobject:` blocker
  at `:217` is **provably unreachable** — `:120` returns early on exactly the
  negation of `:206`'s condition. The vocabulary constraint is about
  *animations*, not classes. `Arrow`, `Triangle` and `Axes` all reach tier 1.
- **A positioned circle silently draws at the origin.** The `circle` and
  `square` emitters carry radius, colour and width and **no position**; only
  `rect` emits `at=`. Verified: a circle shifted to (4.0, 2.0) exports at tier 1
  and the program draws it at (0.00, 0.00).
- **`Write(Circle())` exports at tier 1 and then crashes the player.** Verified:
  `KeyError "write target 'A' was never declared"`. `write` assumes a text
  asset; nothing checks.

Five more silent failures are catalogued in the findings, the worst being that
`self.play(Create(a), Create(b), run_time=2)` — the most ordinary thing a model
writes — emits two sequential verbs and plays for 4.03 s against Manim's 2 s.

On the models themselves the ticket is **not** answered: `openrouter.ai` is
blocked by this environment's egress proxy and there is no key, so no tier-1
rates were measured and none are reported. The pricing table in the findings is
second-hand and marked as such. A precise experiment is specified — 20 briefs,
5 models, and a four-grade rubric whose point is that **grade A (it exports) is
exactly the metric every silent failure passes**.

The prediction worth testing, flagged there as inference: failures cluster in
idiomatic Manim that no prompt makes feel wrong, in which case the answer is a
static gate and a post-generation transform rather than a better model.
