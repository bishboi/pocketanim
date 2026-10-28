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
sudo apt-get install -y libcairo2-dev libpango1.0-dev pkg-config ffmpeg   # once
./setup.sh                                                                 # once
export OPENROUTER_API_KEY=...        # for script, storyboard, score and critic; optional V3_MODEL=provider/model
export DATALAB_API_KEY=...           # to read PDFs (optional DATALAB_MODE=balanced|accurate|fast)
../.venv3/bin/python engine/server.py --port 8300                          # then open http://localhost:8300
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

Not yet: the phone players (the demo is a video), more lands than Japan, and the
critic run on a real model (it needs a key).
