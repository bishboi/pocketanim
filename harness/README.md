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
