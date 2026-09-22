---
id: 2
title: What the reference project does for web rendering
labels: [wayfinder:research]
parent: 1
blocked_by: []
assignee: null
state: open
---

## Question

`https://github.com/yu314-coder/manim_app/` was cited as a reference for the
**web renderer**, explicitly not for the harness. Establish what it actually
does, so the preview decision is made against a real approach rather than an
assumed one.

Answer these:

- How does it get Manim output into a browser? Server-rendered video, streamed
  frames, a WASM build, a re-implementation, something else?
- Where does Manim run in its architecture, and what does it need installed?
- What does it do about the wait? A Manim render is seconds-to-minutes; a web UI
  is not. Job queue, progress, streaming, or does it simply block?
- Is any of it reusable for a preview that must not persist an MP4?
- What is its licence?

The decision this unblocks is how our preview reaches the browser. The map has
already settled that the preview is server-rendered frames for now rather than a
faithful TS renderer — this ticket is about *how*, and about whether the
reference's approach beats whatever we would have invented.
