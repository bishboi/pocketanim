---
id: 1
title: Generation harness for pocketanim scenes
labels: [wayfinder:map]
state: open
---

## Destination

**A decided architecture for a browser harness that turns content into
pocketanim scenes.** The hard choices locked and written down; implementation
left to a build session afterwards. The map is done when someone could sit down
and build the thing without another architectural argument.

Not a spec, not a working app. The expensive mistakes here are structural, and
the brief already says the first version is throwaway.

## Notes

### The brief, as given

Content in, scene out: describe the scene / generate a transcript, generate the
video, show it on screen, then let the user steer it with further instructions.
No visual feedback loop — a human gives the feedback. OpenRouter for the model.
Never store an MP4; store the code and assets. Next.js + Supabase + shadcn.
Whatever it produces has to play on the phone renderer in this repo, users pick
a **template**, and maps (cartopy) and molecular structures have to be possible.

### Settled while charting

These were decided in the opening round and are givens for every ticket below,
not steps on the route.

| | Decision |
|---|---|
| Destination | A decided architecture, not a spec and not a build |
| Where Manim runs | A server-side Python worker. The harness is a browser app; export is a server job |
| Artifact of record | **Both**: Manim Python as editable source, `.panim` + assets as build output |
| Preview fidelity | Server-rendered frames for now. A TS/WASM renderer is named as the eventual answer and is **not** this effort |
| Template | **Corrected by the user after charting**: a *type of video* — animation style, colour scheme, and so on. Charting had recommended "archetype, not visual style"; the user's definition puts the look at the centre and the archetype alongside it. The schema holds both |
| Where it lives | A new repo. This map stays here, because the constraint that binds it — the `.panim` format — is defined here |

### The constraint everything bends around

`dsl/export_dsl.py` produces a program by **executing** the scene: it intercepts
`Scene.play` and `Scene.add` under a real Manim 0.21 with cairo, LaTeX and
cartopy. There is no source-to-program path that avoids running Python, and the
DSL has no vocabulary for a coastline or a molecule — those exist only as baked
tier-2 assets that Manim produced. That is why "all in the browser" holds for
the harness and not for export.

Also load-bearing: **anything the exporter cannot express falls to tier 3**
(sampled IR), which measured 1.2 MB against a 277-byte program on the sample
scene. Generation that drifts outside the supported vocabulary does not fail
loudly; it silently ships something 1000x larger.

### Glossary in progress

Terms sharpened here, to graduate into the new repo's `CONTEXT.md` once it
exists. Kept on the map until then rather than written into this repo's
context, which describes the format and the player.

- **Harness** — the browser app. Authoring, editing, preview, storage. Not the renderer and not the exporter.
- **Template** — a scene archetype. Shapes what the model generates and which Manim vocabulary is in play. Not a visual theme, though it carries one.
- **Scene source** — the Manim Python. What the model writes and a human reads.
- **Scene program** — the `.panim` plus its assets. What a phone plays. Built from the source by the worker.
- **Export** — running the source through `dsl/export_dsl.py` to get a program. A server job, minutes not milliseconds.

### This effort carries execution

Wayfinder plans by default. This one was overridden: the user asked for the
Supabase schema to be built rather than specified, so decided things get
implemented here as they settle. The map still drives the order.

### Settled after charting

Given directly by the user, and so given rather than derived:

- **A template is a type of video** — animation style, colour scheme, and what kind of thing it is. Not primarily a vocabulary constraint.
- **No orchestrator agent.** The first version does not loop build-then-fix. A human looks at the output and says what to change. The exporter's blocker list is therefore something to *show a person*, not something to feed back into a model.
- **Immediate outputs.** The first version answers rather than queues. See the export timings below for where that promise breaks.

### What an export actually costs

Measured, because the decision above depends on it and my own impression was
wrong. `python -m dsl.export_dsl` on this machine:

| Archetype | Scene | Export |
|---|---|---|
| simple / text | HelloPocketanim | **1.2 s** |
| LaTeX | LatexDerivation | **2.2 s** |
| map | CartopyMap | **20.9 s** |
| molecule | MolecularStructure | **126.5 s** |

I had assumed minutes across the board, from watching exports during the player
work. That was wrong: what took minutes there was *fidelity verification*, which
renders Manim's own frames. Export sets `write_to_movie: False` and encodes
nothing, which is why text is a second and a half.

So "immediate" is true for most of the corpus, marginal for maps, and false for
molecules. That is a **template-level** fact, not a global one — and it is
partly a template's own doing: MolecularStructure is 15 spheres at resolution
(12,12), so 2,160 faces walked across 271 frames. A molecule template picks that
number.

### Skills every session should consult

`grilling` and `domain-modeling` by default; `research` for the research
tickets. The glossary above is live — sharpen it as terms settle.

## Decisions so far

<!-- one line per closed ticket, then zoom the link for the detail -->

- [What the reference project does for web rendering](tickets/02-reference-web-renderer.md): it is a Windows desktop app that plays an MP4 off disk, not a web renderer — no transport to copy, and it does not support the frames-based preview position. Its value is the latency calibration: even with no network hop it settles for fire-and-forget and 480p.

## Not yet specified

In scope, not yet sharp enough to ticket. Graduates as the frontier advances.

- **Edit-loop semantics.** "Edit using further instructions" — does an instruction regenerate the scene or patch it? Does history branch, or is it linear? Waits on the pipeline's artifacts being settled.
- **Template asset provenance.** Natural Earth data for cartopy, coordinates for molecules: bundled with the worker, fetched at generation, or supplied by the user. Waits on what a template turns out to be.
- **Preview latency budget.** What the harness promises a user between "generate" and something on screen, and whether `render_farm.py`'s parallel-fragment trick is worth stealing. Waits on the real export timings.
- **Failure surface.** What a user sees when export fails, or when a scene silently lands at tier 3 instead of tier 1.
- **Auth and multi-tenancy.** Supabase auth and RLS, or single-user for the throwaway version.
- **Cost control.** Rate limiting and budget on OpenRouter, once the model and token cost per scene are known.

## Out of scope

Ruled beyond the destination. Does not graduate.

- **Building the TS/WASM renderer.** Named as the eventual answer to preview fidelity, and a project the size of this one. A separate effort.
- **A visual feedback loop.** Explicitly excluded by the brief: the human judges the output.
- **Storing rendered video.** Excluded by the brief, and the whole point of the format.
