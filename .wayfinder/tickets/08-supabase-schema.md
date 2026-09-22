---
id: 8
title: What the Supabase schema is
labels: [wayfinder:grilling]
parent: 1
blocked_by: [5, 6]
assignee: null
state: open
---

## Question

Draw the schema. It cannot be drawn before
[What the pipeline produces between content and scene](06-pipeline-artifacts.md)
settles what exists, or before
[How generation is held inside the exporter's vocabulary](05-tier-one-vocabulary.md)
settles whether a failed export is a row or a retry.

What it has to hold, from the givens: scene **source** (Manim Python) and scene
**program** (`.panim` plus assets) as distinct things with a build relationship;
templates; whatever the pipeline ticket decides is stored.

The parts that will not draw themselves:

- **Versioning.** An edit produces a new source. Is that a new row, a new
  version, or a mutation with history beside it? The brief's edit loop means this
  is the table users spend their time in.
- **Assets.** Content-addressed blobs shared across scenes. Storage bucket keyed
  by digest, with a join table, or something simpler?
- **Build state.** A program is derived from a source and can be stale, missing,
  or failed. Where does that state live, and is a stale program still servable?
- **Tier.** A first-class column: it is the difference between 277 bytes and
  1.2 MB, and a user should be able to see it.

Related and deliberately left to fog for now: auth, RLS and multi-tenancy.
