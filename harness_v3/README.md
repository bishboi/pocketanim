# harness_v3: animated explainers from a score

A new engine, written from scratch after the scripting step (nothing of v1's or v2's engine, compiler or beats).
A video is a **canvas larger than the screen**, cut into **shots** (one idea each). Things on it are **entities**
built from a handful of plain primitives (words, line icons, dots, shapes, a number, a bar, a path, a land's
coastline), and **actions** pinned to the narration's words make them come in, move, morph, count, grow and be
pointed at while the **camera** travels between them. Every action is a tween on one clock, so any number overlap
and add up; nothing waits, nothing is a slide.

The model writes a **score**: a few short lines a small model can write (`engine/prompts.py` GRAMMAR, ~600 tokens).
The 40-second demo's whole score is ~1,150 tokens (`demo/japan.score`).

```
shot bay at 0,0
ent japan   land japan size 1.05 at -3.2,0.2
ent ships   icon ship x4 gap 0.3 badge navy size 0.8 at 4.4,-1.15
t0-w2       in japan draw stagger .15
w2-w4       in ships slide-left stagger .22
w5-w8       move ships by -2.7,0.15
w9-w13      cam bay -2.6,0 zoom 1.06
w58-w62     morph fields works stagger .14
```

| File | |
|---|---|
| `engine/voice.py` | The narration spoken (Piper, offline; one take, a pause between lines) and every written word timed (Whisper, matched to the script's words). |
| `engine/score.py` | The score's grammar and its parser (times: `w12`, `w12-w19`, `w12+0.4`, `t3.5`, `end`). |
| `engine/look.py` | The look (palette, fonts) and the primitives. |
| `engine/render.py` | The runtime: entities on the canvas, every action a tween on one clock, the camera, the narration under it. |
| `engine/prompts.py` | The small-model calls: storyboard (one a video), score (one a shot), critic (frames judged). |
| `engine/assets.py` | Pictures a score asks for (`pic`, `photo`), made by an image model through OpenRouter's Image API (`V3_IMAGE_MODEL`), cut out or framed with a soft shadow, kept by their words; flags (`flag jp`) from flag-icons, exact. |
| `engine/timeline.py` | The video as a timeline a player draws (no MP4): the renderer's own scene played without drawing, each drawn piece recorded (its shape once, then its transform, colours and width; a picture by its corners), keys only where something changes (`player/timeline.json`). |
| `engine/player.html` | The player: draws a timeline at any time t in a canvas, in step with the voice (the Player tab; `/play/<run>`). |
| `engine/export.py` | An MP4 made from the player in headless Chromium (chunks at once, the voice laid under), and a frame-by-frame comparison with the render's MP4: mean PSNR, the share of frames that differ, the moments that differ most side by side (the Compare tab). |
| `engine/runs.py` | A run: its settings, its steps (voice, storyboard, score, render, critic) with status, time and cost, every model call with its prompt, answer, tokens and cost (`runs/<id>/run.json`). |
| `engine/datalab.py` | A PDF read by Datalab's convert API (JSON blocks, as v2 reads it; `DATALAB_API_KEY`), cached by the PDF's hash: each page's text and the headings. |
| `engine/books.py` | A book: a PDF uploaded and read by Datalab (its pages' text, and sections from its headings), scripts of chosen pages (one call each, written as short videos), and each video built as a run; the script calls' cost and its videos' runs added up (`books/<id>/book.json`). |
| `engine/server.py`, `engine/ui.html` | The web app over runs (standard library only). |
| `engine/pipeline.py` | Narration to video, end to end (`--score` to render a given score; the calls need `OPENROUTER_API_KEY`). |
| `demo/` | The 40-second demo: its narration and its score. |

```
./setup.sh
../.venv3/bin/python engine/pipeline.py demo/japan.txt out/japan --score demo/japan.score --quality h
```

## The app

```
cp .env.example .env.local    # once: fill in OPENROUTER_API_KEY (script, storyboard, score, critic) and DATALAB_API_KEY
                              # (PDFs); v2's app/.env.local is read too, and exported variables win over both
./start.sh                    # sets up what is missing (./setup.sh: cairo, pango, ffmpeg, node and Python 3.12 from
                              # Homebrew on macOS, apt on Linux; ../.venv3; icons; voices), then serves
                              # http://localhost:8300
```

From a book: **Upload PDF**, Datalab reads it (in the background: a minute or a few; a PDF read before comes from the cache, at no cost),
then pick a section (from its headings) or a page range, and **Write the script**:
one call writes those pages as a few short videos (how many and how long, and notes for the writer, are yours to
set). Each video's title and narration can be edited; **Build this video** (or **Build all not built**) makes each
one a run, one at a time (`V3_PARALLEL=2` for more). The book shows read, script and videos with their time and
cost (Datalab's own cost for the read, when its result gives one), the script calls with their prompts, tokens and cost, and each video's run status, cost and player. The book's
figures are not used yet (its blocks are kept in `books/<id>/datalab.json`; the full result, pictures included, in `.cache/datalab/`).

A run by hand: **New run** takes a title, the narration (one sentence a line), the model, the voice, quality, speed and pause, the critic on
or off, and (optional) a score written by hand, which skips the storyboard and score calls (no key needed). A run
shows its five steps with status, time and cost (each can run again from there; a single shot can be scored again),
the video with its score (edit it and render again), the narration's timed words, the storyboard, and every call with
its prompt, answer, tokens and cost. The sidebar lists runs with their cost and the total.

The kit (`look editorial`, the default): cream paper, near-black ink, one yellow accent; Oswald headlines,
IBM Plex Mono labels; and the pieces Video1-style explainers are made of: `card "JAPAN" flag jp` (a paper card),
`tag "204%"` (a key number on the accent), `label "debt · % of the economy"` (small spaced capitals), `pic "a stack
of yen banknotes"` (a made cut-out object), `photo "a mountain valley at dawn"` (a made print), `flag us`. Coordinates
and actions stay free. The assets step makes the pictures between score and render (`V3_IMAGE_JOBS` at once), each
call with its cost; a model can be set per step (`V3_MODEL_SCRIPT`, `_STORYBOARD`, `_SCORE`, `_VISION`).

The player: every run gets a timeline step (before the render, which is now optional: `V3_RENDER_MP4=1`, the new
run's checkbox, or its render step run by hand); the Player tab plays the video from it with no MP4
(a few hundred KB to a few MB, gzipped). **Export MP4 from the player** (Compare tab) makes `player.mp4` from the
player and compares it with the render frame by frame, so any difference between the two is shown and can be
fixed; on the demo they agree to 42 dB on average (encoding noise), every frame above 35 dB.

Speed: a video's shots are scored at once (`V3_SCORE_JOBS`, 6), and a video longer than 20 s is rendered in
chunks at once (`V3_RENDER_JOBS`, half the cores), each chunk playing the timeline up to its start unseen so the
chunks join frame for frame; the voice is laid under the joined video.

Not yet: the phone players (the demo is a video), more lands than Japan, and the
critic run on a real model (it needs a key).
