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
- `phone/<chapter>/`: `.panim` programs, when the job asks for them.

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
../../.venv/bin/python -m pytest tests -q     # offline: plan, script, gates, compile, revise
```
