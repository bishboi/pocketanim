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
  blueprint, chalkboard, parchment, lab and cosmos: palette, fonts, panel treatment, caption box, map
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

A chapter draws the map only if one of its beats points at it: a marker, a river, a state or an arrow.
Otherwise the stage shows pictures. Lectures use **no icons**:

| Operation | What it shows |
|---|---|
| `{"op":"photo","image":"File:….jpg" \| "subject":"Chipko movement" \| "query":"…","caption"?,"where"?:"stage"\|"full"\|"panel"}` | A photo. `subject` is Wikipedia's picture of a person, movement, event, monument or place; `query` searches Commons. Only public-domain, CC0, CC BY and CC BY-SA files are used, and they are credited at the end. |
| `{"op":"illustration","image":"File:….svg" \| "query":"water cycle diagram","caption"?}` | An educational illustration or diagram that explains the idea: labelled drawings and diagrams from Wikimedia Commons (SVGs, rendered at 1600 px), then openly licensed illustrations from Openverse. Reusable licences only, and credited. Logos, flags and clip art are skipped. |
| `{"op":"figure","id":"fig2","where":"stage"}` | A diagram from the uploaded PDF. |

On a map chapter, a stage picture covers the map, and the next beat that points at the map clears it.

**People, movements and places get their picture.** A beat about a particular person, movement, event, monument
or place gets Wikipedia's picture of it, when the book has no figure of it:
- in English, from the proper names in its narration ("Sunderlal Bahuguna", "Battle of Plassey");
- in any language, from the beat's `"about": "Chipko movement"`.

A Hindi name is looked up on Hindi Wikipedia and followed to the English article's picture. The picture is used
only when it is on Commons under a reusable licence; non-free posters and logos are never used. Book figures are
placed first. At most six names are looked up per chapter, and misses are remembered.

A beat left without a picture gets an automatic illustration or diagram, searched in this order:
- its `"picture": "soil layers diagram"`, in English, which the model is asked to give each beat;
- else the key terms of its English narration, ranked by how often the chapter uses them;
- else, on a chapter's first beat, the chapter's title.

An automatic picture stays up for two beats, and the same diagram is never used twice in a lecture. Set
`"auto_visuals": false` in the script to turn this off.

Photos are downloaded when the script compiles, into `.cache/images`. To search from the shell:

```
.venv/bin/python harness/lecture/images.py "sugarcane field India"
```

Set `PANIM_IMAGES=0` to turn internet photos off.

## Subjects: the content decides the kind of lecture

`genre.py` reads the content and picks its subject: geography, history, biology, chemistry, physics,
mathematics, economics or general. It scores the vocabulary and also counts dates, chemical formulas and
maths signs. The subject sets:
- **the style:** vox for geography, parchment for history, lab for biology and chemistry, cosmos for
  physics, chalkboard for mathematics, atlas for economics;
- **the map:** often for geography; sometimes for history and economics; rarely for biology; never for
  chemistry, physics and mathematics;
- **the kit:** which stage pictures the model is told to use.

```
.venv/bin/python harness/lecture/genre.py < content.txt
```

In the app, the **Lecture · Auto** template (style `auto`) uses the subject's style. The subject is
reported in the log. The kit operations draw on the stage:

| Operation | What it shows |
|---|---|
| `{"op":"molecule","name":"glucose" \| "H2O" \| "<SMILES>","label"?}` | A 2-D structure in CPK colours, laid out by RDKit. Names not in the table are looked up on PubChem (`PANIM_MOLECULES_ONLINE=0` turns that off). |
| `{"op":"equation","tex":"CH_4 + 2O_2 \\rightarrow CO_2 + 2H_2O","label"?}` | MathTex when LaTeX is installed, else the same equation set in Unicode. |
| `{"op":"plot","exprs":["sin(x)"],"x_range":[-3,3],"x_label"?,"y_label"?}` | Graphs of functions of x (a safe subset of numpy). |
| `{"op":"process","steps":["…","…"],"cycle"?:true,"title"?}` | A chain of steps, or a cycle. |
| `{"op":"timeline","events":[["1526","Panipat"]],"where":"stage","title"?}` | A large timeline. |
| `{"op":"quote","text":"…","who":"…"}` | A primary-source quote. |

Automatic pictures follow the subject too. A science beat that names a molecule or writes an equation
gets a molecule or an equation, and a history chapter opens on a timeline of the years it mentions.

## Illustrations and diagrams (no icons)

Icons were too simple to teach with, so lectures no longer use them. An older script's icon operations still
compile:
- an icon illustration becomes an illustration search for the same thing;
- an icon at a place becomes a labelled marker;
- a panel icon becomes a fact line.

To search from the shell:

```
.venv/bin/python harness/lecture/images.py --illustrations "water cycle" "leaf cross section"
```

### Where the pictures come from

`illustrations.py` asks the sources that suit the lecture's subject, in order, and uses only reusable
pictures, crediting each:

| Subject | Sources, in order |
|---|---|
| biology, chemistry, maths, economics | local collections (OpenStax figures, your packs) → Wikimedia Commons → Openverse → AI |
| physics, geography | local → NASA → Commons → Openverse → AI |
| history | The Met → Smithsonian → local → Commons → Openverse → AI |
| anything else | local → Commons → Openverse → The Met → AI |

- **OpenStax textbook figures.** `fetch_openstax.py` indexes the figures in OpenStax's free textbooks (from
  their GitHub sources): captions and image links only, and each image is downloaded when a lecture first
  shows it. Figures credited to someone else are skipped. Most OpenStax books are **CC BY-NC-SA 4.0
  (non-commercial)**; only the high-school *Physics* book is CC BY 4.0. By default only the CC BY books are
  indexed. `--non-commercial` indexes the rest, and a lecture uses them only with `PANIM_ALLOW_NC=1`.
- **NASA** (not copyrighted; anything credited to someone else is skipped), **The Met** (public-domain
  objects, CC0) and the **Smithsonian** (media marked CC0; `SMITHSONIAN_API_KEY`, a free api.data.gov key, or
  the rate-limited `DEMO_KEY`).
- **Your own packs.** Put a folder in `harness/lecture/data/illustrations/<name>/` with the images and a
  `collection.json` such as `{"name": "NIH BioArt", "license": "Public domain", "credit": "NIH BioArt Source"}`.
  Images are found by their file names, or by an `index.json` of `[{"file", "title", "caption"}]`. This is
  how to add [NIH BioArt](https://bioart.niaid.nih.gov/) (public domain) or
  [Servier Medical Art](https://smart.servier.com/) (CC BY 4.0) downloads; neither offers a search API.
- **AI illustrations**, last and only when nothing else fits. They are drawn by an image model through
  OpenRouter (`OPENROUTER_API_KEY`; `PANIM_IMAGE_MODEL`, default `google/gemini-2.5-flash-image`), in the
  lecture's style, with no text and no real people. There are at most `PANIM_AI_MAX` (6) per lecture.
  `PANIM_AI_ILLUSTRATIONS=0` turns them off.

The endpoints can be overridden with `NASA_IMAGES_API`, `MET_API`, `SMITHSONIAN_API`, `COMMONS_API`,
`OPENVERSE_API` and `OPENROUTER_URL`. `PANIM_IMAGES=0` turns internet pictures off.

```
.venv/bin/python harness/lecture/illustrations.py "electric circuit" --genre physics
```

## Paragraph flow: one visual a paragraph, built as the narration goes

A lecture plans its stage a **paragraph** at a time: 3 to 5 beats that explain one idea. It never puts up a new
picture every sentence. A paragraph starts at a beat marked `"paragraph": true`, at a beat that puts up its own
visual, or after 5 beats. Its visual is one of these:
- a map sequence, for where things are;
- a diagram built on the stage and revealed across the paragraph's beats, for how things work;
- a definition or a comparison;
- the document's figures;
- a gallery of the people, communities and places it names.

Some paragraphs need no picture at all.

| Operation | What it builds |
|---|---|
| `{"op":"diagram","id":"chain","kind":"flow\|cycle\|tree\|hub","nodes":[{"id","label","entity"?}],"edges"?:[[from,to,label?]],"show"?:[ids],"title"?}` | A diagram of the things themselves. Each node is an SVG drawing of its `entity` (an English word: tree, deer, factory) with its label, and arrows join the nodes. `flow` runs in order, `cycle` goes round, `tree` runs down from the first node, and `hub` puts the first node in the middle. `show` draws some nodes first. |
| `{"op":"reveal","diagram":"chain","nodes":["deer"]}` | The next nodes of that diagram, with the arrows that now connect them. |
| `{"op":"focus","diagram":"chain","node":"plants"}` | A ring around one node while the narration talks about it. |
| `{"op":"define","term","meaning","entity"?}` | A hard word, big, with its meaning in plain words. |
| `{"op":"compare","columns":[{"title","entity"?,"points":[…]}],"title"?}` | Two or three kinds side by side. |
| `{"op":"gallery","items":[{"subject"\|"image"\|"figure"\|"illustration","caption"}],"title"?}` | 2 to 4 pictures together. |

Real pictures are only for people, communities, movements and historic places. Everything else is built: a
diagram, a map, a definition, a comparison, or the document's figures. The diagram drawings come from the SVG
library (`fetch_icons.py`, which the app fetches when needed). They appear only inside diagrams, definitions and
comparisons, never as a lecture's picture. Diagrams are vector, so they stay sharp and export at tier 1.

Where the script chose nothing, `auto_visuals` fills a paragraph's first beat, and only that beat:
- with an equation or molecule, or, in history, a timeline;
- else with pictures of the people and places it names, as a gallery when there are several;
- else with nothing, and the last paragraph's picture leaves the stage.

Fetched illustrations of a topic are off unless the script sets `"auto_illustrations": true`. The compiler
warns when more than 60% of beats put up a new picture.

## Teaching in depth: pace, pauses and questions for the class

A lecture teaches each topic slowly, the way a teacher does in class. It does not read the book out or
summarise it. The prompts (the app's `lecturePrompt` and Forge's `EXPLAIN_SIMPLY`) ask for this, for every
important statement of the content:
- say it in easy words;
- explain each hard term;
- give two or three examples from daily life;
- say why it is so;
- say the key idea again in other words;
- add the background the book leaves out.

A chapter is where the lecture starts, not its limit. Without a length in the request, a long source gets time
for this: about a minute for every 120 of its words, from 10 to 30 minutes (Forge plans 2.5 times the reading
time).

**Length and depth.** On the editor page and on the Forge page, **Video length** can be set to 5, 10, 15, 20,
30 or 40 minutes, or left automatic. The content decides the topics: about one every 350 words of a source, and
for a bare topic, one every 3 minutes. The length decides how deep each topic goes, through the teaching plan
(`teaching_plan` in `compile_lecture.py`, and `teachingPlan` in the app with the same formula).

| Minutes per topic | Examples per statement | Questions |
|---|---|---|
| under 1.5 | 1 | one every two topics |
| 1.5–3 | 2 | one per topic |
| 3–5 | 3 | two per topic below 4 minutes a topic, else one |
| 5 and over | 4 | two per topic, three from 7 minutes a topic |

So the same chapter at 30 minutes keeps its topics, and gets more examples and more questions than at 10. The
questions are capped at one every 2 minutes and the example beats at about one every 50 seconds, so a short
video of a long chapter is never asked for more than it has room for.

The prompt gives the model these numbers and asks for everything to be explained in detail: no term, fact, name
or number without what it means and why it matters. The compiler checks the finished script against the plan.
The app passes `--min-questions` and `--min-examples`, and a written lecture with fewer of either is sent back.
The agent's trace shows the plan, for example: "Length 20 min: about 7 topics, 2 examples for each statement,
at least 7 questions for the class".

**Pace.** `PANIM_PACE` sets it. `relaxed`, the default, has:
- the voice at 0.9 speed;
- 0.9 s of silence after every line;
- 1.8 s at the end of each paragraph.

`brisk` is the older, faster pace (1.0, 0.45 s and 0.9 s). A beat can ask for more silence after itself with
`"pause": 1-8` (seconds), for a line that needs a moment to sink in.

**Questions.** Between topics the lecture stops and asks the class something. The stage shows the question; a
bar under its heading fills during `think` seconds of silence; then the next beat shows the answer and
explains it.

| Operation | What it builds |
|---|---|
| `{"op":"question","text","choices"?:[2-4],"answer"?,"think"?:5,"title"?}` | The question card. `answer` is the right choice's letter (`"B"`), its number from 1, or its text. For an open question with no choices, it is the answer in words. The heading reads "Think about it", or "सोचिए" in Hindi. |
| `{"op":"answer"}` | On the next beat: the right choice ringed with a tick, or the answer in words under the question. |

A lecture written by a model (one with a target length) must ask the class at least one question and give
examples; the compiler returns an error otherwise. For an offline or hand-made script, these checks are only
warnings.

## Lecture PDFs and figures

`pdf_source.py` turns a PDF into Markdown plus its figures. Each figure is marked in the text as
`[FIGURE fig3: caption]`.
- With `DATALAB_API_KEY` set, it uses Datalab's conversion API: `POST /api/v1/convert`, then it polls the
  `request_check_url` it gets back.
- Without a key, it uses pypdf, offline.
- Conversions are cached by the PDF's content, so the same PDF is converted only once.

On the upload page, each figure has a **×** to leave it out of the lecture; **restore all** brings them back. A
removed figure is dropped from the figure list and from the text, so the model never sees it. It is recorded
in `excluded.json` beside the PDF, which Forge's reader honours too.

A script shows a figure with `{"op":"figure","id":"fig3","where":"panel"|"full"}`, or several at once in a
gallery. The app supplies the
`figures` table (id → image file); the model only names ids. A figure is a raster image, so the phone
export marks such a scene as blocked and plays sampled frames.

Figures the script does not show itself are placed automatically: each goes on the beat whose words best
match its caption, or in document order, at most one every two beats and never over a map beat. Set
`"place_figures": false` to turn this off.

## Voice

Lectures are voiced by Kokoro-82M (`harness/models/kokoro-v1.0.onnx`, run through kokoro-onnx). The app and
Forge download it before the first lecture build when it is missing. `PANIM_VOICE` picks the voice.
`auto` (the default) uses Kokoro-82M when it is downloaded, espeak-ng when that is installed (offline, say),
and silence with neither. Each style has its own Kokoro voice, and Hindi lines use a Hindi
voice. The other settings are `kokoro:<voice>`, `espeak` and `silent`. With `silent`, lengths are estimated
from the word count.

Lines are cached by the voice and the spoken text in `PANIM_AUDIO_DIR` (default `./build_audio`). `SAY`
respells names for the voice without touching the captions.

Get Kokoro-82M ahead of time (about 350 MB) with the **download** button next to *Voice* at the top of the app, or:

```
.venv/bin/python harness/scripts/fetch_voice.py
```

The app warns when a lecture comes back with no audio.

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
