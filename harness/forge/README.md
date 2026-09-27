# Lecture Forge

Content + a video template + a style pack → a narrated, animated MP4.

The template decides what happens (the chapter arc, beat patterns, required
elements), the style decides how it looks and sounds (roles, fonts, motion,
voice, music), and the content decides what it is about. Model workers only
ever write content into a template's structure. They never write styling or
code. The scenes are compiled from the scripts onto `harness/lecture/pocket_lecture.py`.

```
cd harness/forge
../../.venv/bin/python -m forge new plassey --template battle_explainer --style campaign \
    --title "The Battle of Plassey" --brief-file examples/plassey.md --region bengal_lower
../../.venv/bin/python -m forge make plassey                 # or --until outline|script|preview, --quality l|m|h
../../.venv/bin/python -m forge revise plassey "c7.b04: say: A better line."
../../.venv/bin/python -m forge make plassey                 # redoes only what the note changed
../../.venv/bin/python -m forge restyle plassey blueprint && ../../.venv/bin/python -m forge make plassey
```

`--template` and `--style` default to `auto`. The resolve state reads the sources, classifies the subject
(`harness/lecture/genre.py`) and picks the template and style: `history_lecture` + parchment for history,
`science_explainer` + lab, cosmos or chalkboard for the sciences and maths, `geography_lecture` + vox for
geography, and `explainer` for economics and anything else. A subject that
never uses a map gets no region. `examples/combustion.md` is a chemistry example:

```
../../.venv/bin/python -m forge new combustion --brief-file examples/combustion.md   # science_explainer, lab
```

The same commands are available over HTTP in the harness app at `/forge`
(`/api/forge`, `/api/forge/<id>`, `/api/forge/<id>/file`).

## The control loop

```
intake → resolve → plan → (outline review) → ground → script → validate
       → narrate → compile → preview → (preview review) → final render → deliver
```

`forge/machine.py` owns the loop, and `state.json` is written after every
state, so `make` resumes wherever a job stopped. There are three loops back,
all at beat level where possible:

| Loop | Trigger | Steps |
|---|---|---|
| repair | a gate fails a beat | The gate's deterministic fix first. Then a model repair of that one beat (2 per beat), then a chapter retry (3 per chapter), then a person (`qa/gates.json`; `make --accept` waives). |
| QA fail | a chapter fails to render | The failing beat's operations are dropped, and that chapter alone is compiled and rendered again. |
| revise | a person's note | `c6.b07: say: …` / `ops: [...]` / `drop` edits one beat. `c6: note` rewrites a chapter. `outline: note` re-plans. |

Every stage is cached by the content hash of its inputs. That covers the
script per chapter, speech per line, and renders per chapter, keyed by scene
source, engine version, quality and voice. A revision therefore re-speaks and
re-renders only what it touched.

## Workers and tools

`forge/workers.py` holds the planner, fact grounder, script writer and
repairer. With `OPENROUTER_API_KEY` set (model: `FORGE_MODEL`), each is a
stateless model call with a cached prefix. The prefix carries the template,
the style vocabulary and the op schemas. The workers may call only the
read-only tools in `forge/tools.py`: `template.describe`, `style.vocabulary`,
`ops.schema`, `region.find`, `region.index`, `gazetteer.lookup`,
`facts.query`, `sources.search` and `lexicon.suggest`.

Without a key, deterministic offline workers write the same JSON from the
sources alone. Every line they narrate is a source sentence, and every number
on screen is one of that sentence's numbers. So the whole pipeline runs, and
is tested, with no network.

## Voice

Narration is spoken by Kokoro-82M in the style's voice. The narrate stage downloads it when it is missing
(`FORGE_FETCH_VOICE=0` turns that off; `FORGE_VOICE=espeak` forces espeak-ng).

## Gates (`forge/gates.py`, `forge/engine/qa.py`)

Before render, the gates check:
- **schema:** 8–40 words a beat, known operations, and places that resolve.
- **facts:** every number or clock time said or shown is in `facts.json`.
- **template fit:** required elements and battle phases are present.
- **glyphs:** each character is in the style's fonts, with substitutes where it isn't.
- **layout:** captions stay within two lines and panels don't overflow.
- **motion:** one animation per object per beat.

After render, the output gate measures loudness (−17 LUFS ±1), music at least
`duck_db` under speech, and length within ±10% of target. The results go to
`qa/report.json`.

## Output (`jobs/<id>/out/`)

- `video.mp4`
- `video.srt`
- `chapters.txt`
- `thumbnail.png`
- `contact_sheet.png`: one frame per beat, labelled with the id `revise` takes.
- `report.json`
- `phone/library/` and `<id>-phone.zip`: every chapter as a `.panim` program in one library the phone player opens (unzip, `adb push library …`), with the job's own narration. Only when the job asks for phone output (`forge new` without `--no-phone`).

## PDFs, figures and icons

A `--source` ending in `.pdf` is read by `harness/lecture/pdf_source.py`: Datalab when `DATALAB_API_KEY`
is set, pypdf otherwise. Its figures join `bundle.json` as `s1_fig3` and so on. A script shows one with
`{"op":"figure","id":"s1_fig3"}`, and the offline writer puts each figure where its marker sits in the text.

`{"op":"icon","name":"sugarcane","places":[...]}` draws icons from the library that
`harness/scripts/fetch_icons.py` downloads. The offline writer adds one when a beat names a crop,
mineral, industry or animal, at the place named in the same sentence.

The web page's **Upload lecture PDF** button makes the PDF the job's source.

## The stage

A chapter draws its map only if its beats point at the map. Everything else plays on the stage:
- `photo`: a Wikimedia Commons photo with a reusable licence;
- `illustration`: a composition of icons;
- `figure`: a diagram from a source PDF.

Science and history kits add `molecule`, `equation`, `plot`, `process`, `quote`, and `timeline` with
`"where":"stage"` (see `harness/lecture/README.md`). PDF figures the script leaves out are placed on the
best-matching beats automatically.

The offline writer does map work only in slots about the map. Each map-free chapter opens on a photo of
its subject when one can be found.

Beats without a picture are illustrated from their own words, as in the editor. Photo and icon credits
go at the end of the video and in `out/credits.txt`.

## Libraries

- `styles/<id>/`: `style.yaml` (with `extends:`, roles, theme, voice, music, fonts, `per_template`), `tokens.yaml`, `writing.md`.
- `templates/<id>/`: `template.yaml`, `arc.yaml` (slots with share, required elements, keywords), `patterns/*.yaml`, `prompts/*.md`.
- `regions/<id>/region.yaml`: focus, anchors, features and a battlefield with its units. Any other place gets an automatic pack from Natural Earth.

Precedence, highest first: the job's overrides, then the style's
`per_template` block, the style, its parents, and finally the harness defaults.

`forge registry` rebuilds `registry.json`. `forge learn-style <video|image> --name x`
drafts a style pack from an example's palette. `forge learn-template <outline.md> --name x`
drafts a template from an example outline. Drafts are marked `status: draft`.

## Tests

```
../../.venv/bin/python -m pytest tests -q
```

`test_forge.py` runs the offline workers (plan, script, gates, compile, revise).
`test_llm_path.py` runs the model workers against `tests/mock_openrouter.py`, which
checks tool calls, a reply retried after failing its check, pattern beats and a beat repair.
Set `OPENROUTER_URL` to point the workers at any OpenRouter-compatible endpoint.
