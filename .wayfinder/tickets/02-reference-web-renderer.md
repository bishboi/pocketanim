---
id: 2
title: What the reference project does for web rendering
labels: [wayfinder:research]
parent: 1
blocked_by: []
assignee: opus-5
state: closed
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

## Resolution

**The premise was wrong: it is not a web renderer, and there is no web in it.**
Read in full at commit `ca73becc`. Findings:
[02-reference-web-renderer.md](../research/02-reference-web-renderer.md).

It is a Windows desktop app — a PyWebView native window pointed at a local
`index.html` — that shells out to the `manim` CLI and plays the resulting MP4
off the filesystem. No HTTP server, no browser, no client/server split, no
queue. Its one transport trick, copying the MP4 into a web root so the page can
`<video src>` it, exists only because a webview's CSP blocks `file:///`. There
is no analogue in a Next.js app talking to a remote worker.

Three things that matter to the map:

- **It does not support the server-rendered-frames position.** It never renders
  frames; its only frame handling is `canvas.drawImage()` screenshotting an
  already-rendered `<video>`. A frames-based preview is something this effort
  would be **inventing, not borrowing**.
- **Its transport is the inverse of our constraint.** One preview writes the MP4
  to disk four times, and the copy the player reads has no cleanup path.
- **The latency calibration is the real prize.** A purpose-built desktop Manim
  IDE with no network hop still settles for fire-and-forget, a log tail, no
  percentage progress, and "render at 480p/15fps". A remote worker promising
  better needs an argument.

Also noted for later: `render_farm.py` AST-splits `construct()` at `self.wait()`
boundaries and renders fragments in parallel, carrying an explicit bail-out list
(ValueTracker, cross-fragment references, narration, GPU). That list is the
expensive part to rediscover if preview latency becomes the problem.

Licence is MIT with a blank copyright holder — the grant is intact, the notice
is malformed. Worth knowing before lifting anything.
