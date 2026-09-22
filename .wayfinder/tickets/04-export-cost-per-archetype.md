---
id: 4
title: What an export actually costs, per archetype
labels: [wayfinder:task]
parent: 1
blocked_by: []
assignee: null
state: open
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
