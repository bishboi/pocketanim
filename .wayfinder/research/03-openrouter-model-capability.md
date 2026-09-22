---
ticket: 3
title: Which models write Manim the exporter accepts
labels: [wayfinder:research]
state: answered
---

# Which models write Manim the exporter accepts

## Headline

**The repo half of this ticket is settled and the ticket's prose summary of the
vocabulary is wrong in the direction that matters. The OpenRouter half could not
be measured: there is no API key in this environment, and `openrouter.ai` is
blocked by the egress proxy, so not even the free model catalogue could be
read.**

Three things came out of the source that change what ticket 5 has to decide:

1. **Geometry never blocks.** Any mobject at all — `Axes`, `Arrow`, `Triangle`,
   `Sphere`, a cartopy coastline — is baked as a tier-2 asset and exports at
   tier 1. The `unsupported mobject` blocker is unreachable dead code. The
   vocabulary constraint is **entirely about animations**, not shapes.
2. **The real danger is not tier 3.** It is the set of constructs that export at
   **tier 1 and render the wrong thing**, with no blocker recorded. Eight of
   these are catalogued below, measured by running the exporter. One of them —
   two animations in a single `self.play()` — is the single most natural thing a
   model writes, and it silently doubles the scene's duration. Another —
   `Write()` on a `Circle` — produces a tier-1 program that **crashes the
   runtime**.
3. **`Circle` and `Square` declarations carry no position.** `circle A r=1.3` has
   no `at=` field; only `rect` does. Any circle or square not at the origin is
   drawn at the origin. Tier 1, no blocker.

So the generation constraint ticket 5 writes cannot be "stay inside this list of
classes". It has to be a list of *statement shapes*, plus a post-export
verification step, because the exporter's own verdict is not sufficient evidence
that a scene is right.

**Confidence.** Part 1 is **high** — read from source at the current working
tree and confirmed by running `dsl/export_dsl.py` on 34 probe scenes under the
repo's own Manim 0.21.0. Part 2 is **low** and explicitly second-hand; every
number in it is marked. Part 3 is a design, not a result.

**Provenance.** `dsl/export_dsl.py` (713 lines) and `dsl/interpret.py` (751
lines) as they stand in the working tree; line numbers are that tree's. Probes
were run from a scratch directory so that the asset writes the exporter performs
as a side effect landed outside the repo — the working tree is unchanged by this
research.

---

# Part 1 — The vocabulary, from the source

## How the exporter decides

`record_scene` (`dsl/export_dsl.py:303-578`) monkey-patches `Scene.play`,
`Scene.add`, and four `ThreeDScene` camera methods, then **renders the scene for
real** under `tempconfig({"quality": "low_quality", "write_to_movie": False})`.
Everything it knows, it learns from live Manim objects at the moment `play()` is
called — before the original `play()` runs.

Two consequences that matter for generation:

- The exporter never reads the source. It cannot be fooled by, and cannot
  benefit from, how the Python is written — only by what objects reach `play()`.
- Anything applied to an animation *inside* `Scene.play` is invisible to it. A
  `rate_func=` passed as a `play()` keyword is one such thing (see the silent
  list below).

`main()` (`:661`) prints `TIER 1` iff the deduplicated blocker list is empty, and
with `--write` records `{"scene", "tier", "blockers", "program_bytes"}` plus an
optional `"simplified"` block to `dsl/generated/<Class>.tier.json`. That is the
verdict shape the harness would read. `tier` is `3` if there are any blockers,
`1` otherwise — there is no tier-2 verdict; tier 2 is the *asset* mechanism
inside a tier-1 program.

## Declarations — what `declare()` can emit

`Recorder.declare` (`:107-218`) is tried on every mobject that reaches `play()`
or `add()`. In branch order:

| Emitted | Matched by | Test | Fields kept |
|---|---|---|---|
| `circle N r= stroke= w=` | `isinstance(mob, Circle)` | `:127` | radius (`width/2`), stroke colour, stroke width |
| `square N s= stroke= w=` | `isinstance(mob, Square)` | `:135` | side, stroke colour, stroke width |
| `rect N wh= at= stroke= w=` | `type(mob).__name__ in ("Rectangle", "SurroundingRectangle")` | `:142` | size, **centre**, stroke colour, stroke width |
| `surface N fn= u= v= res= fill= alpha= stroke=` | `isinstance(mob, Surface)` **and** its lambda source matches `np.array([u, v, <expr>])` | `:151-169` | the z expression, ranges, resolution, checkerboard colours |
| `geom N asset=<sha1[:10]>` | `type(mob).__name__ in ("VGroup", "Group")` with submobjects | `:171-185` | baked geometry, content-addressed |
| `text N asset=<sha1[:10]>` | `isinstance(mob, (Text, SingleStringMathTex))` or `type(mob).__name__ in ("MathTex", "Tex", "Code", "MarkupText")` | `:187-201` | baked glyph instances against a shared atlas |
| `geom N asset=<sha1[:10]>` | **catch-all**: anything drawable (`len(points) >= 4`) or with submobjects | `:206-215` | baked geometry |
| `camera phi= theta=` | `ThreeDScene.set_camera_orientation` | `:516-523` | degrees |

**The catch-all is the important row.** Because `:120` already returns early for
a mobject that is neither drawable nor has submobjects, the condition at `:206`
(`if drawable or mob.submobjects`) is always true, and **the
`unsupported mobject:` blocker at `:217` can never fire**. Measured: `Arrow`,
`Triangle`, `Axes` each export at tier 1 as `geom A asset=…`.

Two isinstance traps confirmed by probe, both from Manim 0.21's real hierarchy
(`Dot <- Circle`, `Ellipse <- Circle`, `Annulus <- Circle`;
`Square <- Rectangle`; `Sphere/Line3D/Cylinder/Cone/Torus <- Surface`):

- `Ellipse(width=3, height=1)` → `circle A r=1.5`. **Drawn as a circle.**
- `Dot()` → `circle A r=0.08 stroke=#FFFFFF w=0`. Stroke width 0; **invisible**,
  and its fill is discarded because `hex_of` reads `get_stroke_color()`.
- `Sphere`, `Line3D` etc. are `Surface` subclasses but have no parseable lambda,
  so they fall to the catch-all and bake correctly. No problem there.

`surface_expression` (`:257-279`) scrapes `inspect.getsource(mob._func)` for the
literal pattern `np.array([ u , v , <expr> ])`, strips `np.` and all spaces, and
rejects anything outside `[0-9a-zA-Z_+\-*/(),. ]`. `lambda u, v: axes.c2p(...)`
does not match — measured, and it falls to a baked `geom` asset at tier 1, which
is what corpus scene 03 does.

## Timeline verbs — what `patched_play` can emit

`patched_play` (`:337-501`) iterates the animations of one `play()` call and
tests each with `isinstance`, in this order. `duration` is the `play()`
`run_time=` keyword if present, else the animation's own `run_time`, else 1.0.

| Verb | Triggered by | Line | Notes |
|---|---|---|---|
| `wait t=` / `spin rate= t=` | `Wait` (i.e. `self.wait(...)`) | `:351-356` | becomes `spin` while ambient rotation is on |
| `morph S T t=` | `TransformMatchingAbstractBase` — `TransformMatchingTex`, `TransformMatchingShapes` | `:364-375` | operands captured by a patched `__init__` at `:317-324` |
| `laggedgrow N lag= groups= t=` | `LaggedStart` **whose every sub-animation is a `GrowFromPoint` with `point == mobject.get_center()`** | `:376-413` | i.e. `GrowFromCenter` only |
| `write N t=` | `Write` | `:414-421` | |
| `fadeout N t=` | `FadeOut` | `:422-427` | |
| `fade N t=` | `FadeIn` | `:428-435` | tested after `FadeOut`; both subclass `Transform` |
| `create N t= [rate=]` | `Create` | `:436-441` | |
| `transform S T t= [rate=]` | `Transform`, when neither operand is a baked asset | `:442-454` | |
| `morph S T t= [rate=]` | `Transform`, when either operand **is** a baked asset | `:455-463` | glyph-level match by atlas id |
| `xform N [by=] [by_xy=] t=` | `_AnimationBuilder` (`.animate`) whose chain is only `scale(x)` / `shift(v)` with positional args | `:470-478`, `affine_verb` `:282-300` | the whole chain collapses to one verb |
| `show N` | `Scene.add` | `:503-514` | also fires when an introducer animation adds its mobject on cleanup |
| `move phi= theta= t=` | `ThreeDScene.move_camera` | `:525-538` | |

`dsl/interpret.py`'s `parse()` (`:119-214`) recognises exactly this set and
nothing more: `scene`, `circle`, `square`, `rect`, `text`, `geom`, `surface`,
`camera`, `create`, `transform`, `morph`, `write`, `fade`, `fadeout`, `xform`,
`laggedgrow`, `show`, `move`, `spin`, `wait`. **Exporter and interpreter agree
exactly on the verb set** — there is no verb one can produce that the other does
not know.

Scene mode is `3d` iff any declaration starts with `surface` or `camera`
(`:666`); otherwise `2d`.

## Blockers — the complete list

Every string that can reach `rec.blockers`, deduplicated by `dict.fromkeys` at
`:668`:

| Blocker string | Line | Fires when |
|---|---|---|
| `unsupported mobject: {T}` | `:217` | **never — unreachable** (see above) |
| `non-default rate_func: {name}` | `:361` | animation's own `rate_func` is not `smooth` or `linear` |
| `TransformMatchingTex operands could not be declared` | `:374` | |
| `LaggedStart over {kinds}` | `:408` | `LaggedStart` of anything but grows |
| `LaggedStart grows from a point off centre` | `:411` | `GrowFromEdge`, `GrowArrow`, explicit `GrowFromPoint` |
| `LaggedStart group could not be partitioned` | `:413` | `instance_partition` disagreed with the baker |
| `Write target could not be declared` | `:421` | |
| `FadeOut target could not be declared` | `:427` | |
| `FadeIn target could not be declared` | `:435` | |
| `Create target could not be declared` | `:441` | |
| `{AnimClass} operands could not be declared` | `:468` | any `Transform` subclass whose source or target is undeclarable |
| `unsupported .animate method: {names}` | `:478` | `.animate` chain contains anything but `scale`/`shift` |
| `ValueTracker drives always_redraw (arbitrary per-frame Python)` | `:484` | |
| `.animate on undeclarable {T}` | `:490` | |
| `unsupported animation: {T}` | `:493` | the catch-all for animations |
| `play() produced no verb ({kinds})` | `:500` | structural guard; always accompanies one of the above |

The committed corpus is 11 scenes, of which exactly one is tier 3
(`dsl/generated/PlotGeometry.tier.json`: `ValueTracker drives always_redraw` +
`play() produced no verb (_AnimationBuilder)`). Program sizes range from 110
bytes (`TextReuse`) to 2005 bytes (`LongLesson`, a three-minute scene).

## Corrections to the ticket

The ticket says the exporter supports *"`Circle`, `Square`, `Rectangle`,
`Text`/`Tex`/`MathTex`, `Surface`, baked groups, and the animations `Write`,
`Create`, `FadeIn`/`FadeOut`, `Transform`, `TransformMatchingTex`,
`LaggedStart`+`GrowFromCenter`, `.animate.scale().shift()`, camera moves and
ambient rotation. Anything else is recorded as a blocker."*

Corrections:

- **"Anything else is recorded as a blocker" is false for mobjects.** Every
  mobject is declarable. The list of supported *classes* is not the constraint.
- `Code` and `MarkupText` are also baked as text; `SurroundingRectangle` is a
  first-class `rect`.
- `LaggedStart` + `GrowFromCenter` is right, but `GrowFromCenter` **on its own**,
  outside a `LaggedStart`, is a **blocker** (`GrowFromCenter operands could not
  be declared` — measured). The ticket's phrasing suggests the opposite.
- `Surface` is only *program* when written as `lambda u, v: np.array([u, v, …])`
  with a space-free, arithmetic-only expression. Every other `Surface` is a baked
  asset — still tier 1.
- `TransformMatchingShapes` also works (same base class), which the ticket omits.
- Missing entirely from the ticket: `show` (bare `self.add`), `wait`, and the
  fact that `Transform` between two *text* assets becomes `morph` rather than
  `transform`.

## The silent failures — tier 1, wrong output

This is the material ticket 5 actually needs, and none of it is in the ticket.
All eight were produced by running `dsl/export_dsl.py` on a probe scene; the
emitted program is quoted.

**1. Two animations in one `self.play()` are serialised.** The loop at `:338`
emits one verb per animation into a flat timeline, and `interpret.build_2d`
(`:387-…`) walks that timeline strictly one step at a time, emitting
`duration * fps` frames each. No blocker.

```python
self.play(Create(a), Create(b), run_time=2)
```
```
create A t=2
create B t=2
```
Measured: the resulting program replays as **121 frames = 4.03 s**, against
Manim's 2 s. This is the most common shape in real Manim and the most damaging.

**2. `Circle` and `Square` lose their position.** The `circle`/`square`
declarations have no `at=` field, and `interpret.geometry_for` (`:217-228`)
defaults `at` to `[0, 0]`. Only `rect` carries a centre.

```python
b = Square().shift(RIGHT * 3)          # → square B s=2 stroke=#FFFFFF w=4
```
Drawn at the origin. `Text` and `geom` assets keep their position (it is baked
into the instance transforms), so a scene mixing a labelled title with a shifted
circle comes out half-right.

**3. `Write()` on a program shape produces a program that crashes.** Exporter
says `TIER 1 (67 bytes)`; `dsl/interpret.py` raises
`KeyError: "write target 'A' was never declared"` at `interpret.py:466`, because
`write`/`revealseq` are only implemented for assets. Reproduced end to end.

**4. `Uncreate` is recorded as `create`.** `Uncreate <- Create`, and the
`isinstance` at `:436` catches it. The object is re-drawn instead of erased.

**5. `Unwrite` is recorded as `write`.** `Unwrite <- Write`, caught at `:414`.

**6. `rate_func` passed as a `play()` keyword is not seen.** The guard at `:358`
reads `anim.rate_func`, and `patched_play` runs *before* the real `Scene.play`
applies its keywords. `self.play(Create(c), rate_func=there_and_back)` exports
clean at tier 1 and plays with `smooth`. (`Indicate`, which sets
`rate_func=there_and_back` on the animation itself, *is* caught.)

**7. `FadeIn(mob, shift=UP)` loses the shift.** `fade A t=1`; the object appears
in place.

**8. `TransformMatchingTex` leaves ghost objects on stage.** The cleanup adds the
operands' families back through `Scene.add`, producing extra `show` lines for
re-baked duplicates of the same geometry:

```
write A t=1 / show A / morph A B t=1 / show C / show D / show B
```
`C` has the same asset digest as `A`. Corpus scene 01 has the same shape, so it
is tolerated today, but it is not obviously correct.

For completeness, the constructs that **do** block cleanly, measured:
`Rotate`, `GrowFromCenter` alone, `Restore`, `Indicate`, `AnimationGroup`,
`Succession`, `LaggedStart` over non-grows, `.animate.move_to`,
`.animate.set_color`, `.animate.rotate`, and `ValueTracker` + `always_redraw`.

### Probe method

34 single-construct scenes were exported with
`python dsl/export_dsl.py <probe>.py <Class>` from a scratch working directory
(the exporter resolves `dsl/generated/assets` relative to cwd, so the repo's
versioned assets and `library.atlas` were untouched — `git status` confirms the
working tree is unchanged). Class hierarchies were read out of the repo's own
`.venv` running Manim **0.21.0**.

---

# Part 2 — Models and pricing on OpenRouter

## What could not be done, and why

**There is no OpenRouter API key in this environment, and `openrouter.ai` is
blocked outright by the egress proxy** — `curl`, `WebFetch` and every third-party
pricing aggregator I tried (`costgoat.com`, `tokentab.dev`) return
`EGRESS_BLOCKED` or a 403 CONNECT. `arxiv.org`, `docs.manim.community` and
Wikipedia are blocked too. The only working channel was `WebSearch`, which
returns a *summary* of pages rather than the pages themselves.

So:

- **No tier-1 success rates are reported here, for any model.** Not estimated,
  not inferred from reputation. Part 3 specifies the measurement instead.
- **The pricing table below is second-hand and should be treated as a shopping
  list, not a fact.** Re-derive it in one unauthenticated call — the model
  catalogue needs no key:

  ```
  curl -s https://openrouter.ai/api/v1/models \
    | jq -r '.data[] | [.id, (.pricing.prompt|tonumber*1e6), (.pricing.completion|tonumber*1e6)] | @tsv'
  ```

  (`pricing.prompt` / `pricing.completion` are per-token strings; multiply by
  1e6. This is from memory of the API shape — the docs were unreachable.)

## Model families worth testing

Reasoning, not measurement. The ticket asks which models are *worth testing*; the
shortlist below is chosen to span the price range by roughly a decade at each
step, because the interesting question is where tier-1 reliability falls off, not
which model is best.

The **Claude rows are first-party Anthropic rates**, from the bundled
`claude-api` skill's model table (cached 2026-06-24) — higher confidence than the
rest, and OpenRouter states it passes provider pricing through without per-token
markup. Every other row is a WebSearch summary of a third-party aggregator,
**unverified**, and the naming was inconsistent between searches (one result set
said "Gemini 3 Pro", another "Gemini 3.8 Flash"; one said "DeepSeek Pro", another
"DeepSeek V4.1 Flash"). Treat the ids as approximate.

| Model | $/M in | $/M out | Source | Why on the list |
|---|---|---|---|---|
| Claude Opus 5 | 5.00 | 25.00 | `claude-api` skill table | Ceiling: if this cannot hold the vocabulary, prompt-only constraint fails |
| Claude Sonnet 5 | 2.00 | 10.00 | `claude-api` skill table (corroborated by search) | The likely default |
| Claude Haiku 4.5 | 1.00 | 5.00 | `claude-api` skill table | Cheap-tier probe from a strong family |
| GPT-5.6 "terra" | 2.00 | 12.00 | WebSearch, unverified | Cross-family control at Sonnet's price |
| GPT-5.6 "luna" | 0.20 | 1.20 | WebSearch, unverified | Cheap tier |
| Gemini 3 Pro | 2.00 | 12.00 (≤200K) | WebSearch, unverified | Cross-family control |
| DeepSeek (Pro) | 0.62 | 2.88 | WebSearch, unverified | Open-weight, strong coding reputation |
| GLM-5.3 | 0.44 | 1.32 | WebSearch, unverified | Open-weight, ~10x cheaper than Sonnet |
| Qwen3.6 Flash | 0.30 | 1.80 | WebSearch, unverified | Open-weight cheap tier |
| Kimi K3 | 3.00 | 15.00 | WebSearch, unverified | Long-context coding |

Two structural facts about OpenRouter that survive the sourcing problem, both
repeated consistently across searches and both relevant to ticket "Cost control"
on the map: **no per-token markup over the provider's own rate**, and **a ~5.5%
fee on credit purchases**. There is also a free tier (rate-limited, roughly 20
req/min, 200 req/day) which is enough to run the experiment in Part 3 once, for
nothing, if budget is the blocker.

## The one external prior worth knowing

**TheoremExplainAgent / TheoremExplainBench** (ACL 2025, arXiv 2502.19400) is the
closest published measurement: 240 theorems, an agent that plans then writes
Manim, scored partly on whether the script runs. Its best configuration (o3-mini)
reports a **93.8% success rate** — where "success" means *the Manim script
executes and produces a video*, after an agentic repair loop.

That number is a ceiling that does not transfer. Our bar is strictly harder in
three independent ways: the script must run **and** export at tier 1 **and** do
so **without repair**. A script full of `ValueTracker`, `Axes.plot` and
`AnimationGroup` scores 100% on their metric and 0% on ours. The right way to
read 93.8% is: *syntactic* Manim competence is close to solved for a 2025-era
model, so whatever our rate turns out to be, the gap is about vocabulary
discipline, not about writing valid Python. Related benchmarks named in the
literature — ManimBench, ManiBench, Code2Video — are measuring the same
"does it render" bar.

## Token cost per scene — estimate only

No tokenizer is installed in this environment (`tiktoken` and `transformers` are
both absent), so these are the chars ÷ 4 heuristic over real files, not measured
counts.

- **Output.** The repo's scenes are 547–2756 bytes; `samples/hello_pocketanim.py`
  is 1189 bytes. So **≈150–700 output tokens** for the scene itself, call it
  ~300 for a typical one. With a reasoning model, thinking tokens are billed as
  output and can dwarf this — budget 2–5x.
- **Input.** A vocabulary spec strict enough to be worth having (the tables in
  Part 1, written as rules) is ~1,500–2,500 tokens; two worked examples
  (`hello_pocketanim.py` + one 3D scene) ~600; the content brief 100–500. So
  **≈2,500–4,000 input tokens per scene**, stable across a session and therefore
  a good prompt-caching candidate.

At Sonnet-5 rates that is roughly **$0.008–0.015 per scene** before thinking
tokens; at GLM/Qwen rates, well under a tenth of a cent. **Model price is not
the cost driver for this harness.** Retries and the export job are.

---

# Part 3 — The experiment, specified to be runnable in an hour

Everything below is designed so that someone with an OpenRouter key and this repo
can run it without making further decisions.

## Setup

Requirements: this repo, its `.venv` (Manim 0.21 + cairo + LaTeX), and
`OPENROUTER_API_KEY`. Work in a scratch directory, not the repo — the exporter
writes `dsl/generated/assets/*.panm` and `dsl/generated/library.atlas` relative
to the current working directory, and those are versioned.

```
mkdir -p /tmp/tier1-eval/dsl/generated/assets && cd /tmp/tier1-eval
```

## The prompt

One system message, held constant across models. It encodes the **corrected**
vocabulary from Part 1, including the silent-failure rules — which are the part
no model can infer from Manim knowledge.

```
You write Manim Community v0.21 scenes for a renderer that supports only a
narrow subset of Manim. Output ONE Python file and nothing else: no prose, no
markdown fences, no comments outside the file.

Structure:
  from manim import *
  class <Name>(Scene):        # or ThreeDScene for 3D
      def construct(self):
          ...

HARD RULES — a scene that breaks any of these is rejected:

1. Exactly ONE animation per self.play() call. Never
   self.play(Create(a), Create(b)). Write two separate play() calls.
2. Never pass rate_func= to play() or to an animation.
3. Circle and Square must stay at the origin. To place one elsewhere, create it
   at the origin and move it with .animate.shift(). To draw a positioned
   rectangle, use Rectangle (its position is preserved).
4. Never call Write() on a shape. Write() is for Text, Tex, MathTex and Code
   only. Use Create() for shapes.

ALLOWED ANIMATIONS — nothing else:
  Create(mob)                         shapes and baked geometry
  Write(text)                         Text / Tex / MathTex / Code only
  FadeIn(mob) / FadeOut(mob)          no shift= or scale= arguments
  Transform(a, b)
  TransformMatchingTex(a, b)          MathTex / Tex only
  LaggedStart(*[GrowFromCenter(m) for m in group], lag_ratio=r)
  mob.animate.scale(x)                positional argument only
  mob.animate.shift(vec)              positional argument only
  mob.animate.scale(x).shift(vec)     the two may be chained
  self.wait(t)
  self.add(mob)
  ThreeDScene only: self.set_camera_orientation(phi=, theta=),
    self.move_camera(phi=, theta=, run_time=),
    self.begin_ambient_camera_rotation(rate=),
    self.stop_ambient_camera_rotation()

ALLOWED MOBJECTS: any Manim mobject may be constructed — Axes, Arrow, Polygon,
Sphere, VGroup and so on are all fine. Only the animation list above is
restricted. Prefer Circle, Square, Rectangle, Text, Tex, MathTex, Code, VGroup.
A 3D Surface is cheapest when written exactly as
  Surface(lambda u, v: np.array([u, v, <expression in u and v>]), ...)

FORBIDDEN, no exceptions: ValueTracker, always_redraw, updaters, Rotate,
Uncreate, Unwrite, Restore, Indicate, Circumscribe, Flash, AnimationGroup,
Succession, GrowFromCenter outside a LaggedStart, MoveAlongPath, ApplyMethod,
.animate.move_to, .animate.rotate, .animate.set_color, .animate.to_edge,
.animate.next_to.

Always pass an explicit run_time= to every play(). Give the scene a class name
in CamelCase matching the topic.
```

The user message is the brief, e.g. *"A 20-second scene explaining why a circle's
area is πr². Title, the formula, one shape, one transform."*

Run it **once per sample, no repair loop, no multi-turn**. The whole point is to
measure the unrepaired rate; ticket 5 decides what the repair loop looks like.

## The briefs

20 briefs, held constant. Cover the three archetypes the map names, so the result
is per-archetype rather than one number:

- 8 **explainer** briefs (title + text + 2–3 shapes + a transform),
- 6 **formula** briefs (`MathTex` + `TransformMatchingTex` chains),
- 3 **3D** briefs (surface or grouped solids + camera move + ambient rotation),
- 3 **group** briefs (`VGroup` + `LaggedStart` of `GrowFromCenter`).

3 samples per brief per model at `temperature=0.7` (or the model's default if
temperature is rejected) → 60 generations per model. Five models → 300 calls,
~1.2M input and ~0.2M output tokens all-in: a few dollars at Sonnet rates, free
on the rate-limited tier if you are patient.

## Grading — four graded outcomes, not a boolean

Run each generated file through the exporter and then the interpreter:

```
python /path/to/pocketanim/dsl/export_dsl.py scene.py <Class> --write
python /path/to/pocketanim/dsl/interpret.py dsl/generated/<Class>.panim
```

| Grade | Test | Why it is separate |
|---|---|---|
| **A — exports** | `tier.json` has `tier == 1`, `blockers == []` | The ticket's stated bar |
| **B — plays** | `interpret.py` exits 0 | Part 1 §3: a tier-1 program can crash the runtime |
| **C — faithful** | no `self.play()` in the source has more than one animation argument; no `rate_func=` anywhere; no `Circle(`/`Square(` followed by `.shift`/`.move_to`/`.next_to`/`.to_edge` on the same expression; no `Uncreate`/`Unwrite`/`FadeIn(..., shift=`/`Write(` on a non-text name | the eight silent failures; all are detectable by static check on the source, which is why they belong in the harness and not only in the prompt |
| **D — right** | a human watches the rendered `manim -pql` output against the `.panim` replay | the only check that catches a scene that is legal, plays, and is ugly |

**Report A ∧ B ∧ C as "tier-1 clean".** Reporting A alone will overstate every
model, because A is exactly the metric the eight silent failures pass.

Grade C's checks are cheap AST work — a `ast.NodeVisitor` over the generated
source is about 60 lines and is reusable as the harness's pre-flight gate, which
is probably its real home.

## What to record per generation

`model`, `brief_id`, `sample`, `usage.prompt_tokens`, `usage.completion_tokens`,
`usage.cost` if OpenRouter returns it (request it with `"usage": {"include":
true}` in the body — from memory; verify against the docs), wall-clock latency,
grades A–C, and **the verbatim `blockers` array**.

The blockers array is the deliverable the ticket actually asks for. The ticket
is right that failure *modes* matter more than the rate: a model that reaches for
`ValueTracker` needs a different fix (an explicit ban, which is already in the
prompt above) from one that writes `self.play(Create(a), Create(b))` (which needs
a post-processing pass that splits the call, and is mechanically repairable). Tally
the blocker strings and the grade-C violations into a frequency table; that table,
not the headline rate, is what ticket 5 should be handed.

## Prediction, to be falsified

Stated so the run has something to disagree with, and marked as **inference, not
a finding**: the frequent failures will be *grade C*, not grade A —
multi-animation `play()` calls and positioned `Circle`/`Square` — because they are
idiomatic Manim that no amount of "stay in the vocabulary" phrasing makes feel
wrong, whereas `ValueTracker` and `Rotate` are nameable and therefore bannable. If
that holds, the answer to ticket 5 is a post-generation transform plus a static
gate, not a better prompt, and model choice matters much less than it looks.

---

## What I could not establish

- **Any tier-1 rate, for any model.** No key, and `openrouter.ai` is blocked.
- **The real OpenRouter catalogue and prices.** Blocked; the table in Part 2 is
  from search summaries, unverified, with inconsistent model naming between
  sources. The Claude rows are the only ones with a first-party source.
- **Measured token counts.** No tokenizer available; Part 2's figures are chars ÷ 4.
- **Whether the ghost `show` lines after `TransformMatchingTex` are harmless.**
  The corpus tolerates them, but I did not compare a replay against Manim's own
  frames.
- **Whether `write` on a `geom` (non-text) asset works.** I proved it crashes for
  a program shape; the asset path was not probed.
