# Harness (staged)

The generation harness the map in `.wayfinder/` is charting: content in,
pocketanim scenes out. It belongs in **its own repo** — different stack,
different lifecycle, different CI — and is staged here only until that repo
exists, because the constraint it is built against (the `.panim` format) is
defined in this one.

```
harness/
  supabase/migrations/0001_init.sql   the schema
  scripts/apply-schema.sh             applies it to a project
  scripts/export_scene.py             Manim source -> .panim program, as JSON
  app/                                the Next.js app
```

## What the harness actually produces

Not a video. The same artifact the phone already plays: a `.panim` program and
its baked assets. So the harness needs no renderer of its own — it needs the
exporter in this repo, addressed as a tool. `scripts/export_scene.py` is that
address, and it differs from `python -m dsl.export_dsl` in two ways that matter
here:

* **It builds into a directory you name.** The exporter writes assets and the
  glyph atlas by relative path, so the script sets the working directory to the
  build's own. A generated scene therefore cannot land in `dsl/generated`, which
  is the corpus.
* **It returns JSON.** `tier`, `blockers`, `program`, `assets`. The blockers are
  the point: tier 1 with an empty blocker list is the only combination that
  means the program is faithful, and §11 of `docs/SPEC.md` is the record of how
  much work it took to make that true.

A scene that does not import is an ordinary outcome, not a crash — it comes back
as `{"tier": null, "error": ...}`, because that is the first thing the edit loop
has to show a human.

## Running it

```sh
cd harness/app
npm install
cp .env.example .env.local     # optional: a key and a project
npm run dev                    # http://localhost:3000
```

Nothing in `.env.local` is required. With no `OPENROUTER_API_KEY` the app uses
an offline fixture provider that returns real, exportable Manim, so export,
preview and the edit loop all work with no network and no account. With no
Supabase project, the pipeline runs and simply writes nothing down.

The app needs the repo's Python environment, because export and preview are the
repo's own tools: `lib/pocketanim.ts` prefers `../../.venv/bin/python`.

The five steps on the page are the brief's pipeline: content and a template in,
a scene source you can edit by hand, an export that reports its tier and its
blockers, a preview, and an instruction box that produces the next version.

**The preview plays in the browser.** `/api/ir` expands a built program into
its geometry once -- the shape atlas, and per frame the instances that
reference it -- and `lib/draw.ts` rasterises that onto a canvas. About 730 kB
of numbers, 25 kB on the wire, one request per build and no server round-trip
per frame. There is no video anywhere: the durable artifacts are the program
and its assets, and a frame is recomputed from them like any other.

Manim's animation semantics stay in Python, where a corpus and a fidelity
harness have been spent proving them; only the rasterising crosses over. That
split is the `PathSink` seam the renderer already defines -- whoever draws
needs paths and colours and nothing more.

`lib/draw.ts` is a fourth implementation of this format's rasterising, after
Cairo, Java2D and Skia, so it is checked like the others:

```sh
npm run check:draw -- <ir.json> <build_dir> <SceneClass>
```

It renders frames headlessly and compares them with
`exporter/reference_render.py`. Measured on a generated scene: **0.00% of
pixels differing at every frame**. Node's canvas is Cairo and so is the oracle,
so that is a statement about the drawing logic -- subpath splitting, when a
subpath closes, fill and stroke order, the scene-to-pixel transform -- and not
about how a real browser rasterises, exactly as `tools/verify_player.py` can
say nothing about Skia.

**3D scenes still preview on the server**, one PNG per frame via `/api/frame`.
Projection, depth sorting and shading would all have to be reimplemented in the
browser to draw them faithfully, and a wrong preview is worse than an honest
fallback. Three of the four templates are 2D.

## Known gaps in this environment

* **OpenRouter is unreachable** from the dev container (the egress proxy refuses
  it) and no API key is set, so generation cannot be run here end to end.
* **No Supabase project is configured**, so the schema can be applied by the
  script but not exercised against live data here.

Neither blocks the deterministic half — source in, program out — which is the
half the phone depends on.

## Applying it

```sh
# against a hosted project
DATABASE_URL='postgresql://postgres:...@db.<ref>.supabase.co:5432/postgres' \
  harness/scripts/apply-schema.sh

# or against a local supabase start
harness/scripts/apply-schema.sh --local

# see what it would do first
harness/scripts/apply-schema.sh --dry-run
```

The script is idempotent: the migration is written so that re-applying it is a
no-op rather than an error, which is what makes it safe to run from CI or by
hand against a project someone has already touched.
