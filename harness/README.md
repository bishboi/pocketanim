# Harness (staged)

The generation harness the map in `.wayfinder/` is charting: content in,
pocketanim scenes out. It belongs in **its own repo** — different stack,
different lifecycle, different CI — and is staged here only until that repo
exists, because the constraint it is built against (the `.panim` format) is
defined in this one.

```
harness/
  supabase/migrations/                the schema (0001 init, 0002 saved lectures and the phone's catalog)
  supabase/setup.sql                  every migration in one file, for the dashboard's SQL editor
  scripts/apply-schema.sh             applies every migration, in order, to a project
  scripts/export_scene.py             Manim source -> .panim program, as JSON
  scripts/narration.py                a scene's add_sound calls -> one track
  lecture/                            the narrated map-lecture engine and its compiler
  app/                                the Next.js app
```

## Lectures

`lecture/` is the map-lecture engine (see `lecture/README.md`): beats, captions,
a fact panel, chapter cards and maps in six styles, all tier 1. The app has a
lecture template per style. Generating with one writes a *beat script* -- with a
model through a `write_lecture` tool, offline from the content and the place it
names -- which `lecture/compile_lecture.py` lints and turns into Manim you can
edit. A pasted lecture script written the guide's way (the India and Rajasthan
lectures) plays too.

Narration is part of the build. A scene that calls `add_sound` (every lecture
beat does) gets one mixed `narration.wav`, each line placed on the frame its
beat starts; a scene with `# voice:` lines is voiced by Google Chirp 3 HD, the
only narration voice, and gets the same treatment. The preview plays that track as
its clock, and **Download for the phone** zips the build as a player library,
narration included.

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

**Full local setup, including every downloadable library (place names, voice, maps, fonts) and
troubleshooting: [SETUP.md](SETUP.md).**

```sh
harness/scripts/setup-python.sh   # creates .venv and installs Manim 0.21
cd harness/app
npm install
cp .env.example .env.local     # optional: a key and a project
npm run dev                    # http://localhost:3000
```

`setup-python.sh` is required. Export executes the generated scene, so a
machine Python without Manim fails with `ModuleNotFoundError: No module named
'manim'`. The script picks Python 3.11+ (Homebrew `python@3.13` is the one
that has Manim's wheels), creates `.venv` at the repo root, and installs
`harness/requirements.txt`. The app uses that interpreter.

Nothing in `.env.local` is required. With no `OPENROUTER_API_KEY` the app uses
an offline fixture provider that returns real, exportable Manim, so export,
preview and the edit loop all work with no network and no account. With no
Supabase project, the pipeline runs; only Save is unavailable (see "Saving lectures" below).

The app needs the repo's Python environment, because export and preview are the
repo's own tools: `lib/pocketanim.ts` prefers `.venv/bin/python`, found by
walking up from the process directory. `/api/status` reports whether that
interpreter can import Manim. LaTeX is optional and only required for MathTex.

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
* **No Supabase project is configured**. The schema is checked against a local
  Postgres (`scripts/test-schema.sh`), and Save and the phone's download against a
  stand-in for Supabase (`forge/tests/test_saved_lectures.py`), not a live project.

Neither blocks the deterministic half — source in, program out — which is the
half the phone depends on.

## Applying it

Without psql: in the project's dashboard open **SQL Editor**, paste `harness/supabase/setup.sql` and **Run**
(regenerate it after changing a migration with `harness/scripts/apply-schema.sh --bundle`). The phone's
**Saved** answering "Could not find the table 'public.phone_lectures'" means this has not been done.

```sh
# against a hosted project
DATABASE_URL='postgresql://postgres:...@db.<ref>.supabase.co:5432/postgres' \
  harness/scripts/apply-schema.sh

# or against a local supabase start
harness/scripts/apply-schema.sh --local

# see what it would do first
harness/scripts/apply-schema.sh --dry-run
```

The script is idempotent: every migration is written so that re-applying it is a
no-op rather than an error, which is what makes it safe to run from CI or by
hand against a project someone has already touched. Migration 0002 also creates
the Storage bucket `lectures` (public for reading) when it runs against Supabase.

## Saving lectures, and playing them on the phone

**Save** (under the preview, once a build is tier 1) stores the lecture on screen
-- one video, or every micro-lecture of a series -- in the project (`lib/store.ts`):

* rows of record: a project for the series, a scene per video (its place in the
  series as `ordinal`), the version's Manim source, and a build;
* each video's phone library in Storage, bucket `lectures`: the `.panim` program,
  its `scenes/*.json`, the glyph atlas and the narration under
  `builds/<build id>/`, and each asset once at `assets/<digest>.panm`
  (content-addressed, indexed in `assets` and tied to builds in `build_assets`);
* the build marked published, which lists it in the view `phone_lectures`.

The app needs `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in
`.env.local` (writing the tables and the bucket is the server's alone). Saved
lectures belong to the user `PANIM_OWNER_EMAIL` (default
`harness@pocketanim.local`, created on first save) or to `PANIM_OWNER_ID`.

### Everything a generation makes, kept by default

With Supabase set up, every lecture generation is recorded as it runs, without
pressing Save (`lib/media.ts`, migration `0003_generated_media.sql`; set
`PANIM_STORE_MEDIA=0` to turn it off). In the private bucket `media`:

* each picture once, at `media/<sha256>.<ext>`: SVG drawings, book figures
  redrawn as SVG, AI illustrations, book photos and the web photos found like
  them, and the web and library pictures the compiler fetched. The `media` table
  holds its kind, **what it shows** (the drawing's description, the figure's
  caption, the subject) and **where it came from** (parts, model, source,
  credit, licence, url, the query it was found by);
* each `.panim` program built (every build, saved or not), at
  `programs/<sha256>.panim`, listed in `programs` with its frames and size.

And in the tables: `generations` (what was asked, the models, the length, the
cost, how it ended); `generation_media`, one row per use of a picture with its
**context** (the video, chapter and section, the line said over it, the diagram
node or map label it sits beside, what it cost, whether a cache had it);
`generation_scenes`, each video's Manim source. A program finds its generation
through its scene source's digest, so the pictures, sources and programs of two
runs can be compared side by side. Apply the migration once (`setup.sql` has it).

On the phone, **Saved** lists `phone_lectures` and downloads the one picked
(once; it then plays offline). The app asks once for the project's URL and anon
key (Supabase: Project Settings -> API; long-press Saved to change them), or
reads them from `player/app/src/main/assets/supabase.json`
(`{"url": "...", "anon_key": "..."}`) when an APK is built with one.
