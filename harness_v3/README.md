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
| `engine/pipeline.py` | Narration to video, end to end (`--score` to render a given score; the calls need `OPENROUTER_API_KEY`). |
| `demo/` | The 40-second demo: its narration and its score. |

```
./setup.sh
../.venv3/bin/python engine/pipeline.py demo/japan.txt out/japan --score demo/japan.score --quality h
```

Not yet: the phone players (the demo is a video), the app (this is a command line), more lands than Japan, and the
critic run on a real model (it needs a key).
