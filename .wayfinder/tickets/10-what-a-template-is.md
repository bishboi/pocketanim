---
id: 10
title: What a template is, concretely, and the first catalogue
labels: [wayfinder:grilling]
parent: 1
blocked_by: [5]
assignee: null
state: open
---

## Question

**The user has since defined the term**: a template is a *type of video* —
animation style, colour scheme, and what kind of thing it is. Charting had
recommended the opposite ("archetype, not visual style"); the user's definition
puts the look at the centre. The schema in `harness/supabase/migrations/` holds
both — `palette`/`typography`/`pacing` beside `prompt`/`preamble`/`requires` —
so nothing is foreclosed.

What remains is the catalogue and the mechanics. Waits on
[How generation is held inside the exporter's vocabulary](05-tier-one-vocabulary.md),
because if templates are how generation is constrained then they carry far more
weight than if they are only a starting point.

What has to be settled:

- **What a template is made of.** A prompt fragment? A Python skeleton the model
  fills? A declared vocabulary the model may use? A worked example? Some
  combination, and if so, which part does the constraining?
- **The v1 catalogue.** The brief names maps and molecular structures
  specifically. The corpus already demonstrates: LaTeX derivation, plotted
  geometry, 3D camera move, cartopy map, molecular structure, code walkthrough,
  surface orbit, text-heavy lesson. Which become templates, and is the corpus
  scene the template's worked example?
- **Who can author one.** Built-in only, or user-authored? That decides whether a
  template is a database row or a file in the repo.
- **What a template costs to export.** Measured: a molecule takes 126.5 s and a
  text scene 1.2 s, and the difference is largely the template's own choice —
  MolecularStructure is 15 spheres at resolution (12,12), so 2,160 faces walked
  across 271 frames. A template picks that number, which makes export time a
  design parameter rather than a fact of the archetype.
- **What a template declares about its needs.** A map template needs cartopy and
  Natural Earth data; a molecule template needs `Sphere` and `Line3D` and a set
  of coordinates. Is that declared, or implied by the prompt?

Template **asset provenance** — where Natural Earth data and molecule
coordinates actually come from — is deliberately left in the map's fog until
this settles what a template is responsible for.
