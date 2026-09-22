---
id: 9
title: What the export worker's contract and lifecycle are
labels: [wayfinder:grilling]
parent: 1
blocked_by: [4, 5]
assignee: null
state: open
---

## Question

Export runs as a server-side Python job. Decide its interface and its lifecycle.
Waits on [What an export actually costs, per archetype](04-export-cost-per-archetype.md),
because a ten-second job and a five-minute job are different products, and on
[How generation is held inside the exporter's vocabulary](05-tier-one-vocabulary.md),
because a validate-and-repair loop means the worker runs several times per scene.

What has to be settled:

- **Synchronous or queued.** A request that blocks for minutes is not a request.
  If queued: what queue, and how does the browser learn it finished?
- **What crosses the boundary.** Source in, and out comes… a program, assets, a
  tier verdict, a blocker list, a render for preview? The exporter already emits
  the verdict and blockers as `<Scene>.tier.json`.
- **Where it runs.** A container with Manim, LaTeX, cairo and cartopy installed
  is a heavy image. Fly, Railway, Modal, a self-hosted box?
- **Arbitrary Python from a language model, executed on a server.** This is
  remote code execution by design. Sandbox, network policy, resource limits.
- **Concurrency and cost.** One warm worker or many cold ones, given whatever
  ticket 4 finds about cold-start.

Note the overlap with preview: if the worker also renders frames, that is one
service; if not, it is two.
