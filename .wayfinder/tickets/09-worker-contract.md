---
id: 9
title: What the export worker's contract and lifecycle are
labels: [wayfinder:grilling]
parent: 1
blocked_by: [4, 5]
assignee: opus-5
state: closed
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

## Resolution

Decided, as asked, against the measurement in
[What an export actually costs, per archetype](04-export-cost-per-archetype.md)
and the user's "immediate outputs, no orchestrator loop".

**Synchronous. One HTTP request per export, no queue.** A queue is the right
answer to a multi-minute job, and three of the four archetypes are not one.
Building it now would be paying for a molecule's 126 s in every text scene's
1.2 s.

- **Interface.** `POST /export` with `{source, scene_class, template}`; back
  comes `{tier, blockers[], program, assets[], frames, fps, duration_ms}` or an
  error. The tier and blockers come straight from the exporter's own
  `<Scene>.tier.json` rather than being re-derived.
- **Timeout 180 s**, which clears the worst measured archetype with margin. A
  timeout is a failed build with a reason, not a hang.
- **Warm worker.** A container with Manim, LaTeX, cairo and cartopy. One that
  stays up: import and TeX startup are per-process, not per-scene.
- **The UI promises per template, not globally.** A template knows roughly what
  it costs; the button should say so rather than implying every scene is
  instant.

**The part that is not comfortable, recorded rather than smoothed over:** this
executes model-written Python on a server, which is remote code execution by
design. For a throwaway single-user version the mitigation is a
network-isolated container, one process per request, and resource limits. That
is *adequate for one trusted user and not adequate for signups*, and the moment
this has a second user it needs revisiting. Noted as fog on the map rather than
pretended away.

**What this forecloses:** if a later version wants many templates like the
molecule, the answer is a queue, and this decision is meant to be reversed then
rather than defended.
