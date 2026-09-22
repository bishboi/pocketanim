---
id: 4
title: What an export actually costs, per archetype
labels: [wayfinder:task]
parent: 1
blocked_by: []
assignee: opus-5
state: closed
---

## Question

Export is a server job whose duration shapes the whole UX — whether the harness
needs a queue, what progress it can show, whether a user waits or comes back.
Right now that duration is folklore. Measure it.

For each scene in `corpus/scenes/` plus `samples/hello_pocketanim.py`, record
wall-clock, peak memory and output size for
`python -m dsl.export_dsl <file> <Scene> --write`, and group the results by the
archetype the scene represents: text/explainer, plot, 3D camera, map, molecule.

Impressions from the session that produced the corpus, to be confirmed or
corrected: simple text scenes exported in well under a minute; CartopyMap and
MolecularStructure took minutes each; LaTeX scenes pay for a TeX run. If a map
really is a five-minute job, that is a product constraint, not a detail.

Also worth capturing while the harness is running these:

- Cold versus warm cost. How much is Manim import and TeX startup, paid once per
  worker rather than once per scene?
- Does anything need the network at export time (cartopy's Natural Earth
  downloader, TeX packages)? A worker that phones home mid-export is a different
  operational animal.

The answer belongs in the ticket as a table. Two decisions wait on it: the worker
contract, and whether generation is interactive at all.

## Resolution

Measured. **The ticket's own premise was wrong, and so was mine.**

| Archetype | Scene | Export |
|---|---|---|
| simple / text | HelloPocketanim | **1.2 s** |
| LaTeX | LatexDerivation | **2.2 s** |
| map | CartopyMap | **20.9 s** |
| molecule | MolecularStructure | **126.5 s** |

The ticket said "CartopyMap and MolecularStructure took minutes each" from
impressions formed during the player work. Text scenes are a second and a half.
What took minutes back then was **fidelity verification** — `dsl/verify_dsl.py`
renders Manim's own frames to compare against. Export sets
`write_to_movie: False` and encodes nothing. Export and render are different
jobs, and conflating them would have bought a job queue nobody needed.

Two things follow:

- **"Immediate" is a per-template promise, not a global one.** True for text,
  marginal for maps, false for molecules.
- **A template chooses its own export cost.** MolecularStructure is 15 spheres
  at resolution (12,12) — 2,160 faces walked across 271 frames. Halving the
  sphere resolution quarters the faces. That belongs in
  [What a template is, concretely, and the first catalogue](10-what-a-template-is.md).

Not established: cold versus warm cost (these were warm — Manim was already
imported in a previous run in the same environment), peak memory, and whether
cartopy's Natural Earth downloader touches the network on a cold machine. The
last one matters operationally and is now fog on the map.
