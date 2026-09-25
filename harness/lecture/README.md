# Lecture engine

Narrated, captioned, map-animated lectures that play on the phone, in the web
editor, and render in Manim — from one source file. This is the engine from the
map-lecture guide (Rajasthan, India and its five styled variants), rebuilt so
that everything it draws exports as a **tier-1 program** rather than video.

```
pocket_lecture.py    the engine: styles, beats, captions, panel, cards, maps
compile_lecture.py   beat script (JSON) -> Manim on the engine, with a linter
resolve_region.py    the country or state a piece of content is about
examples/india.json  the reference India lecture, condensed
```

## What is the same as the guide

* **Audio drives timing.** `beat(text, *animations)` speaks the line first,
  measures it, runs the animations over 55% of it (1.2–3.2 s), and holds for
  the rest plus 0.45 s.
* **One projection for everything.** `MapFrame` takes a Cartopy projection
  (Lambert Conformal fitted to the region by default, standard parallels at
  1/6 and 5/6 of its latitude span) and one linear map to scene units; every
  outline, river, marker and graticule goes through it.
* **Engine, data and script are separate.** A lecture is a `MapLecture`
  subclass with a `REGION` and a `construct` of beats — or a JSON script the
  compiler turns into one.
* **Styles are one table.** `THEMES` holds atlas, vox, cardboard, whiteboard,
  blueprint and chalkboard: palette, fonts, panel treatment, caption box, map
  colours, text entrance. `LECTURE_STYLE` (or `use_style`) picks one.
* The screen layout and z-order of the guide: map left of x = 1.05, panel to
  the right, captions at y = −3.45 on z 60, chapter cards on z 40.

## What is different, and why

The phone plays a *program*, not pixels, so the engine avoids what a program
cannot carry:

| Guide | Here | Why |
| --- | --- | --- |
| Background textures as `ImageMobject` | Vector shapes (grid, fibres, board frame, soft discs), one baked asset | No image verb |
| Rainfall raster from Matplotlib | Filled regions (`region_fill`, `fill_state`) | No image verb |
| Globe intro as PNG frames | Omitted | No image verb |
| Blueprint text types letter by letter | Writes on | No per-letter verb |
| `set_z_index` on everything | Same — the program now carries z | Added `z=` |
| `add_sound` per beat | Same — the exporter records where each starts | Mixed into one track |

Scenes written the guide's own way — like the pasted India script — also
export: image backgrounds are dropped (the scene's background colour is kept),
and everything vector plays.

## Writing a lecture

```python
import os
os.environ.setdefault("LECTURE_STYLE", "vox")
from pocket_lecture import *

class GeneratedScene(MapLecture):
    REGION = dict(country="India", view="ind")     # or dict(state="Rajasthan", country="India")
    SECTIONS = ["Introduction", "Rivers"]

    def construct(self):
        self.chapter(1, "Rivers", "Two families", "Chapter one. The rivers of India.")
        self.show_map()
        self.beat("The Ganga is India's longest river.",
                  self.panel_title("Rivers"),
                  self.river("Ganges"),
                  self.big_stat("2,525 km", "Ganga: longest river of India", P.RIVER))
        self.beat("Delhi is the capital.", self.mark("New Delhi", "Delhi", P.GOLD))
        self.outro_fade()
```

Colours are read from `P` at call time (`P.RIVER`, `P.GOLD`, ...) so a style
switch never leaves stale defaults. Helpers return animations to pass into
`beat`: `panel_title`, `fact`, `big_stat`, `bar_chart`, `clear_panel`, `mark`,
`river`, `path`, `flow` (curved arrow), `fill_state`, `graticule`, `dim`.
Whole-beat helpers: `chapter`, `title_slide`, `recap`, `credits`,
`outro_fade`. A beat that changes the panel title plays the change before the
new facts arrive.

Or write a beat script and compile it:

```sh
python harness/lecture/compile_lecture.py harness/lecture/examples/india.json -o scene.py
python harness/lecture/compile_lecture.py script.json --check     # lint only
```

The linter rejects unknown operations, map operations without a region, and
missing fields, and warns about captions past two lines and a panel that runs
into the caption.

## Voice

`PANIM_VOICE` picks it: `auto` (espeak-ng when installed, else silent), `espeak`,
`silent` (lengths estimated from word count), or `kokoro:<voice>`. Lines are
cached by their spoken text in `PANIM_AUDIO_DIR` (default `./build_audio`), and
`SAY` respells names for the voice without touching the captions.

## Building

```sh
# the harness path: program, assets, narration.wav, tier verdict
python harness/scripts/export_scene.py scene.py GeneratedScene build/

# pack a build for the phone
python -m tools.build_library --source build/dsl/generated --out library
adb push library /sdcard/Android/data/com.pocketanim.player/files/

# or render the same file to video with Manim
PYTHONPATH=harness/lecture manim -qm scene.py GeneratedScene
```

Map data is Natural Earth through Cartopy's downloader (`admin_0_countries`,
`admin_0_countries_ind` for India's view of its borders, `admin_1_states_provinces`,
`rivers_lake_centerlines`, `populated_places`), fetched once and cached.

`corpus/scenes/14_lecture_engine.py` is a network-free lecture on the engine.
Against Manim's own frames it is 0.04% of pixels off, worst frame 2.7% of its
ink, and it is in the nightly fidelity job.
