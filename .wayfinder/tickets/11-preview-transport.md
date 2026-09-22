---
id: 11
title: How a preview reaches the browser with no video at rest
labels: [wayfinder:grilling]
parent: 1
blocked_by: [9]
assignee: null
state: open
---

## Question

Graduated from fog by
[What the reference project does for web rendering](02-reference-web-renderer.md),
which established that the cited reference offers nothing to copy here: it
writes an MP4 to disk and plays it in a `<video>` tag, which is the inverse of
this brief's constraint. A frames-based preview is something this effort
**invents**.

Decide how a preview gets from the worker to the browser, given that no video
may exist at rest.

- **What crosses the wire.** Individual frames (PNG/WebP over websocket, drawn to
  a canvas)? A short-lived stream that is never written down? Something else?
- **Does "never store the MP4" forbid a transient one?** A stream that exists
  only in memory for the length of a request is arguably not storage. The brief
  says never store; it does not obviously say never encode. This needs a ruling,
  because encoding is by far the cheaper path.
- **At what fidelity and rate.** The reference settles for 480p/15fps *locally*.
  A preview that is not what the phone will show is already approximate — how
  approximate is acceptable?
- **Who renders it.** The export worker, or a second service? This is why the
  ticket waits on
  [What the export worker's contract and lifecycle are](09-worker-contract.md).

The honest tension to hold: the map already accepts that the preview is not what
ships, and the last month of this repo was spent catching exactly that class of
divergence. Whatever is decided here should say what the user is expected to
trust the preview *for*.
