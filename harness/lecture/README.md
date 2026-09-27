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

## Place names

A marker's `place` is looked up in this order:

1. Natural Earth's populated places. This is about 7,300 towns worldwide, the same data the maps are drawn from.
2. The same lookup under a renamed city's other name, e.g. Prayagraj ⇄ Allahabad or Bengaluru ⇄ Bangalore (`PLACE_ALIASES`).
3. `data/places_extra.csv`, a short hand-kept list of district towns and parks.
4. The GeoNames gazetteer: about 150,000 towns, with old, new and non-Latin names. Download it once:

   ```
   .venv/bin/python harness/scripts/fetch_gazetteer.py
   ```

   `setup-python.sh` does this for you.
5. OpenStreetMap's Nominatim, when online. Each answer is cached in `.cache/geocode.json`. Set `PANIM_GEOCODE=0` to turn this off.

`compile_lecture.py --check` reports a place none of these can find as an error. The fix is to give `lonlat` for that marker instead.

A Devanagari line is spoken by a Hindi voice whatever the style's voice, and Devanagari text is laid out large and scaled down, so small captions keep their shaping.

## The stage: the map only when it is needed

The left half of the frame is the stage, and the fact panel is on the right.

A chapter draws the map only if one of its beats points at it: a marker, a river, a state, an arrow, or an
icon placed at a town. Otherwise the stage shows pictures:

| Operation | What it shows |
|---|---|
| `{"op":"photo","image":"File:….jpg" \| "query":"…","caption"?,"where"?:"stage"\|"full"\|"panel"}` | A Wikimedia Commons photo. Only public-domain, CC0, CC BY and CC BY-SA files are used, and they are credited at the end. |
| `{"op":"illustration","icon":"sugar-cane","items"?:[["wheat","Rabi"]],"title"?}` | One large icon with up to four small ones. |
| `{"op":"figure","id":"fig2","where":"stage"}` | A diagram from the uploaded PDF. |

On a map chapter, a stage picture covers the map, and the next beat that points at the map clears it.

A beat left without a picture gets an automatic illustration drawn from its own words: sugarcane, tigers,
tractors. A beat whose opening line has nothing to picture gets an illustration of the chapter's topic
instead (Climate, Population, …). Set `"auto_visuals": false` in the script to turn this off.

Photos are downloaded when the script compiles, into `.cache/images`. To search from the shell:

```
.venv/bin/python harness/lecture/images.py "sugarcane field India"
```

Set `PANIM_IMAGES=0` to turn internet photos off.

## Icons

`{"op":"icon","name":"sugarcane","places":["Meerut","Saharanpur"]}` puts an icon on the map at each place.
Without a place, it goes in the fact panel beside its `label`. Names are searched in about 25,000 openly
licensed icons:
- Single-colour silhouettes: game-icons, Material Design Icons, Health Icons. These are filled with the
  style's colour, or with `color`.
- Flat colour emoji: Fluent Emoji Flat, OpenMoji, Noto. These keep their own colours.

Download the icons once (about 53 MB):

```
.venv/bin/python harness/scripts/fetch_icons.py
.venv/bin/python harness/lecture/icons.py sugarcane coal tiger     # search from the shell
```

A lecture that uses icons credits their sets in its closing line.

## Lecture PDFs and figures

`pdf_source.py` turns a PDF into Markdown plus its figures. Each figure is marked in the text as
`[FIGURE fig3: caption]`.
- With `DATALAB_API_KEY` set, it uses Datalab's conversion API: `POST /api/v1/convert`, then it polls the
  `request_check_url` it gets back.
- Without a key, it uses pypdf, offline.
- Conversions are cached by the PDF's content, so the same PDF is converted only once.

A script shows a figure with `{"op":"figure","id":"fig3","where":"panel"|"full"}`. The app supplies the
`figures` table (id → image file); the model only names ids. A figure is a raster image, so the phone
export marks such a scene as blocked and plays sampled frames.

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
