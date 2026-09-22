---
id: 7
title: How a generated scene reaches the phone
labels: [wayfinder:grilling]
parent: 1
blocked_by: []
assignee: null
state: open
---

## Question

The brief requires that everything the harness generates plays on the renderer in
this repo. That renderer does not read a database; it reads a **library**: a
manifest plus content-addressed files, built by `tools/build_library.py` and
opened through `Library.load(storage)`. Decide the contract between the two.

What has to be settled:

- Does the harness **serve a library over HTTP** that the player syncs, or does it
  export a bundle a user sideloads? Today the player reads its library from APK
  assets — it has never fetched one.
- What is the **unit of delivery**: one scene, a user's whole library, a
  published collection?
- Assets are **content-addressed** and shared across scenes — the glyph atlas is
  one file every text scene points at. Does the harness preserve that sharing,
  and who does the deduplication?
- Does the player need to **change** to support this? Fetching, caching and
  integrity-checking a remote library is work that lands in this repo, and
  `Library.checkIntegrity` already exists for exactly this.
- What happens to a scene that lands at **tier 3**? It still plays, it is just
  large. Does the harness deliver it anyway, or hold it back?

This is the integration boundary between two codebases, which is why it is on the
frontier rather than deferred — getting it wrong is the expensive kind of wrong.
