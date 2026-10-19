# The motion engine (beta)

The motion engine draws a lecture the way a modern explainer channel does: everything on screen is **designed in a
look** (colours, fonts, a textured board, cards with soft shadows, pictures dressed as stickers, prints or newsprint)
and **animated with intent** (each template brings its parts on in a choreography, each part landing on the words
that name it, one picture giving way to the next with a transition, nothing ever frozen).

It is a beta beside the current engine, not a replacement. Nothing of the current engine, its compiler or what it has
made changes: the motion engine is its own files, and a script is drawn by it only when it says `"engine": "motion"`.

```
beat script (JSON, "engine": "motion") ─▶ compile_motion.py ─▶ Manim scene on motion.MotionLecture ─▶ export_scene.py ─▶ .panim ─▶ phone / web player
                                           = compile_lecture.py          (pocket_lecture's MapLecture,        (unchanged: every motion is a verb
                                             extended in-process           every template in motion)            the players have, or a baked clip)
```

| File | What it is |
|---|---|
| `compile_motion.py` | The compiler: `compile_lecture.py` imported and extended in its own process (new operations, `on`, looks), so every check, mend and picture of the beat script works as it does there. |
| `motion.py` | `MotionLecture`: the engine. Extends `pocket_lecture.MapLecture`; redraws the classic operations in motion and adds the templates (`m_*`). |
| `motion_kit.py` | The primitives: words, cards, chips, stamps, marks, and the motions (entrances, emphasis, exits, a counter, a spring, a shake). |
| `motion_timeline.py` | The timeline in five styles. |
| `motion_looks.py` | The six looks: design, motion tokens, textures, picture dressing. |
| `tools/motion_strip.py` | A contact sheet of a rendered video, every N seconds: how a motion plays, at a glance. |

Contents: [the script](#1-the-script) · [how a beat plays](#2-how-a-beat-plays-in-motion) ·
[templates](#3-the-templates) · [classic operations](#4-the-classic-operations-in-motion) ·
[timelines](#5-the-timeline-in-five-styles) · [looks](#6-looks) · [motion tokens](#7-motion-tokens) ·
[checks and mends](#8-what-the-compiler-checks-and-mends) · [phones](#9-what-the-phones-play) ·
[running and testing](#10-running-it-and-testing-it) · [known gaps](#11-known-gaps)

---

## 1. The script

A motion script is a beat script ([BEAT_SCRIPT.md](BEAT_SCRIPT.md)): its `chapters`, their beats and their
operations, with these additions. Everything in BEAT_SCRIPT.md
still holds: the same chapters, beats, operations, pictures, maps and checks.

```json
{
  "engine": "motion",
  "look": "paper",
  "energy": "lively",
  "transition": "slide",
  "timeline": "track",
  "chapters": [{"title": "Japan's debt", "beats": [
    {"say": "Japan owes more than twice the size of its whole economy.",
     "do": [{"op": "counter", "value": "204%", "label": "debt, as a share of the economy", "kicker": "Debt · % of GDP", "delta": "+12%"}]},
    {"say": "Compare it with Italy, the United States and Germany.",
     "do": [{"op": "chart", "items": [["Japan", 204], ["Italy", 138], ["USA", 126], ["Germany", 65]],
             "unit": "%", "highlight": "Japan", "reference": {"value": 100, "label": "The economy"}}]},
    {"say": "Yet every auction cleared.", "do": [{"op": "stamp", "text": "Cleared", "on": "cleared"}]}
  ]}]
}
```

| Field | | What it does |
|---|---|---|
| `engine` | `"motion"` | Drawn by the motion engine. Left out: the current engine. |
| `look`? | `paper` \| `newsroom` \| `chalk` \| `data` \| `studio` \| `sketch` | The design and the way of moving (§6). Left out: the script's classic `style` keeps its colours and fonts and moves as its nearest look does (vox, parchment, cardboard → paper; atlas, cosmos, blueprint → data; lab, friendly, water → studio; whiteboard, ink → sketch; chalkboard → chalk). |
| `energy`? | `calm` \| `lively` \| `punchy` | How fast everything moves (§7). Default: the look's own. |
| `transition`? | `slide` \| `push` \| `wipe` \| `dissolve` \| `zoom` \| `page` \| `cut` | How one picture gives way to the next. Default: the look's own. |
| `timeline`? | `track` \| `ribbon` \| `cards` \| `road` \| `vertical` | The default style of a `timeline` (§5). |
| `style`? | a classic style | With a `look`, the pictures are still asked of the image model in this style (so pictures made for a lecture before are found again, not made anew). Left out with a look: the classic style the look rests on (paper → vox, newsroom → atlas, chalk → chalkboard, data → cosmos, studio → lab, sketch → whiteboard). |

**`on`: the words an operation lands on.** Any operation (a template or a classic one) may carry `"on": "<words of
its line>"`: it starts as those words are said (the voice's word times), not as the line begins. Inside a template,
items carry their own `on` (a chart's column, a group of units, a chain's step, a card's mark); without one, an item
lands on its own name when the line says it, or in its turn.

---

## 2. How a beat plays, in motion

1. **The voice starts.** If the look wipes, a sheet of the accent sweeps across the board first, taking the last
   picture away under it (about 0.6 s of the line).
2. **The picture's choreography.** A template comes on as it was designed to: its title typed, then its body (a
   chart's baseline drawn, the columns rising one after another, the values popping over them). Parts overlap: each
   starts before the last has landed. The old picture leaves the look's way (slid out, pushed up, zoomed past).
3. **Moments on words.** Parts held back come on as the line says them: a chain's next step and the arrow to it, a
   group of units coloured, a card's tick, a phrase highlighted, a timeline's event. A part not said comes on in its
   turn after the template is in.
4. **Pointing.** A part of a template on screen whose name a later line says is pointed at the look's way (a
   column pulses and its value grows, a card lifts). `emphasis` points on purpose (§3).
5. **Idle.** What is up keeps moving gently (a float or a slow drift, played by the players themselves), so
   nothing is frozen while the voice goes on.
6. **Sound.** Each motion has its sound, under the voice: pops, swishes, a stamp's thud, a counter's ticks, a pen's
   scratch (sfx.py).

Each animation asks for its own length (from the look's tokens, §7), and the beat gives it that length. When the
next moment comes sooner, the animation is shortened to fit.

---

## 3. The templates

Each is an operation (`"op": "<name>"`) and a method of the engine (`MotionLecture.m_<name>`). All take `id` (to point
at their parts later: `"<id>.<part>"`) and `on`. Sizes fit the board (or the stage beside a panel or a map) by
themselves.

### `title`: a headline
```json
{"op": "title", "kicker": "A true story", "text": "The man who read the hands of kings", "highlight": "kings", "sub": "1866-1936"}
```
Big words rise in one after another (wrapped onto lines), the `highlight` word gets the highlighter drawn behind it
(its letters turned to read on it), the kicker is typed over it, an underline is drawn under it when nothing is
highlighted, and `sub` fades in under it. Each word is a part.

### `counter`: a figure counting up
```json
{"op": "counter", "value": "$14.06B", "label": "work already signed", "kicker": "Backlog", "delta": "+73%", "trend": "up", "start": 0}
```
| Arg | | |
|---|---|---|
| `value` | required | The figure as it ends ("204%", "2,525 km", "$14.06B", "+50%"). Its number counts up from `start` (default 0) easing out, its prefix and suffix kept, its commas and decimals kept. Words with no number pop in. |
| `label`?, `kicker`?, `sub`? | | Under it, typed over it, under the label. |
| `delta`?, `trend`? | | A change beside it with an arrow: green ▲ up, red ▼ down (`trend`, else from a leading minus). |
| `color`? | | The figure's colour (a palette name or #hex); default the look's accent. |

### `chart`: columns, bars or a line
```json
{"op": "chart", "kind": "column", "kicker": "Debt · % of the economy", "unit": "%", "highlight": "Japan",
 "reference": {"value": 100, "label": "The economy"},
 "items": [["Japan", 204], ["Italy", 138], {"label": "Germany", "value": 65, "on": "Germany", "color": "TEAL"}],
 "source": "IMF World Economic Outlook"}
```
| Arg | | |
|---|---|---|
| `items` | required | `[label, number]` or `{label, value, on?, color?, text?}` (`text`: the value as written). Up to 12 (a line: 60). |
| `kind`? | `column` (default) \| `bar` \| `line` | |
| `highlight`? | a label or labels | In the accent, the rest muted. Without one: the largest. |
| `reference`? | `{value, label}` | Column: a dashed line across at that value, drawn, its label popping at its end. |
| `marks`? | `[{at, label}]` | Line: dashed lines down at those x values (when the labels are numbers, e.g. years), each labelled. |
| `unit`?, `title`?, `kicker`?, `source`? | | A unit after each value; a heading; the mono line over it; a source line under it. |

- **column**: the baseline drawn; the columns grow from it one after another; each value pops over its column; the
  labels rise under them; the reference line is drawn across and its label pops.
- **bar**: each row's label rises, its track fades in, its bar sweeps out along it, its value pops at the end.
- **line**: the axes drawn and the grid faded in; a dot pops at the start and rides the end of the line as it is
  drawn left to right (a baked clip); the last value pops beside the end; the marks are drawn down and labelled.

Each item is a part: a later line naming it pulses its column and its value. An item with `on` turns to the accent
and pulses as it is said.

### `units`: a grid of units
```json
{"op": "units", "total": 100, "kicker": "Japan's government bonds", "unit": "IOU", "cols": 10,
 "groups": [{"n": 46, "label": "Bank of Japan", "on": "Bank of Japan", "color": "GOLD"}],
 "fly": {"n": 8, "label": "8% abroad", "on": "abroad"}}
```
| Arg | | |
|---|---|---|
| `total`? | 1-400 | How many units (default 100). |
| `cols`? | | Units in a row (default 10, or 20 past 120). |
| `unit`? | | The word written in each unit (when there are 60 or fewer). |
| `groups`? | `[{n, label, on?, color?}]` | Runs of units from the first, each coloured and labelled as it is said. |
| `fly`? | `{n, label, on?}` | The last `n` units fly off into a pile, labelled. |
| `title`?, `kicker`? | | |

`total` units pop in a wave from the corner. Each
group, in order from the first unit, is coloured as it is said, its label slammed in as a chip under the grid.
`fly` sends the last `n` units flying off to the side into a loose pile, labelled. Each group is a part.

### `cards`: cards dealt in a row
```json
{"op": "cards", "title": "His predictions", "stamp": {"text": "Debunked", "on": "tested"},
 "items": [{"title": "Prediction one", "big": "1912", "mark": "check", "on": "three"},
           {"title": "Lord Kitchener", "picture": {"generate": "Lord Kitchener, a portrait photograph"}, "mark": "cross"},
           {"title": "Prediction four", "big": "1920", "mark": "untested"}]}
```
Up to 6 cards, dealt in from below one after another, each turned a little. A card shows its `picture` (or a `big`
word) over its `title` and `sub`. Its `mark` lands as the line says it (its `on`, else its title): `check` (a tick
drawn), `cross` (a cross drawn), or any other words (stamped on it). `stamp` slams across the whole row. Each card is
a part.

### `stamp`: a stamp slammed onto what is up
```json
{"op": "stamp", "text": "Cleared", "on": "cleared", "color": "ROSE", "angle": -10, "at": "center"}
```
A rubber stamp (double-ruled box, capitals, turned by `angle` degrees, default -10) lands from large with a thud, onto the picture on the stage
(`at`: center, top, bottom, left, right) and the picture shakes; with nothing up, on the board. Put over what is up:
it plays after the beat's pictures.

### `kpi`: data cards
```json
{"op": "kpi", "kicker": "Last quarter", "cards": [{"label": "Sales", "value": "+50%", "delta": "$3.27B", "note": "in sales"},
                                               {"label": "Backlog", "value": "$14.06B", "delta": "+73%", "trend": "up"}]}
```
Two to four cards: a mono label, a big figure that counts up as its card lands, a change with its arrow, a note.
Dealt in one after another.

### `chain`: steps joined by arrows
```json
{"op": "chain", "title": "How a dollar of backlog moves", "loop": true,
 "steps": ["Signed", {"label": "Built", "on": "built"}, {"label": "Billed", "picture": {"generate": "an invoice"}}, "Paid"]}
```
`steps`: two to seven, each a word or `{label, on?, picture?}`, in a row, numbered (or with their pictures). The first pops in with the template; each next step
pops in and the arrow to it is drawn as the line says it (or in its turn); `loop` draws an arrow from the last back to
the first. Each step is a part.

### `list`: points coming in as they are said
```json
{"op": "list", "title": "What to watch", "mark": "check", "items": ["Margins", {"text": "Hiring", "on": "hiring"}, "The next report"]}
```
Up to 7 points; each slides in from the left with its mark (`bullet`, `number`, or `check`: a tick drawn) as it is
said. Each point is a part.

### `versus`: two sides
```json
{"op": "versus", "title": "Two kinds of river",
 "left": {"title": "Himalayan", "points": ["Snow-fed", "Flow all year"]},
 "right": {"title": "Peninsular", "points": ["Rain-fed"], "value": "40%", "picture": {"generate": "a dry river bed"}}}
```
Two cards sweep in from the two edges, a VS badge slams between them. Each side (`left`, `right`, a title alone or
an object): `title`, `points` (up to 4),
`value` (a big figure), `picture`. Each side is a part.

### `donut`: a part of a whole
```json
{"op": "donut", "value": 62, "total": 100, "label": "of the backlog is data centres", "sub": "Q2 filing", "text": "62%"}
```
The ring's track drawn, the share swept round it from the top, the figure counting up in the middle (`text`, else
`value%` of 100).

### `document`: a page, its phrases highlighted
```json
{"op": "document", "title": "Cheiro's memoirs", "source": "Cheiro, 1931",
 "text": "While there I came in contact with a certain sect of Brahmins ... a science called Samudrika.",
 "highlight": ["a certain sect of Brahmins", "Samudrika"], "picture": {"generate": "a Victorian gentleman, sepia portrait"}}
```
A page drops onto the board (its picture, dressed as a print, slides in beside it), its title and words fade on;
each `highlight` phrase (words of the text, as written) is swept with the highlighter as the line says it, line by
line. Each phrase is a part.

### `polaroids`: prints dealt onto the board
```json
{"op": "polaroids", "items": [{"generate": "Mark Twain, a portrait photograph", "caption": "Mark Twain"}, {"figure": "fig2", "caption": "Oscar Wilde"}]}
```
Up to 5 photos, dressed as prints (polaroid, or the look's newsprint), dealt in turned a little and overlapping, each
captioned in its frame. Each print is a part (its caption).

### `callout`: a line on a block of the accent
```json
{"op": "callout", "text": "8% abroad", "at": "right", "on": "abroad"}
```
Popped onto what is up (`at`: right, left, top, bottom, center), or alone on the board.

### `emphasis`: pointing on purpose
```json
{"op": "emphasis", "target": "Japan", "how": "circle", "on": "Japan"}
{"op": "emphasis", "target": "chart1.Italy", "how": "box"}
```
At a part of a template on screen (its name, or `<id>.<name>`): `pulse` (default), `circle` (a ring drawn round it by
hand), `underline`, `highlight` (the highlighter behind it), `box` (the house frame), `glow`, `shake`, `dim` (the
rest of its template faded back). A name not on screen is left out with a note.

---

## 4. The classic operations, in motion

Every operation of BEAT_SCRIPT.md works. On the board, these are redrawn:

| Operation | In motion |
|---|---|
| `stat` | A `counter` (the value counts up, the label under it). In the side panel it stays the panel's line. |
| `bars` | A `chart`: columns (8 or fewer, short labels), else bars. |
| `fact` | The board's key point, swept in from the left. |
| `compare` | Two columns: a `versus`. More: `cards`. |
| `define` | The term set large, the highlighter swept under it, the meaning typed in under it. With a picture already up, it goes beside it (the picture moves into the left half, its labels with it) instead of hiding it. |
| `quote` | A card: big quote marks drop in, the words typed on, the speaker slides in. Beside a picture already up, as `define`. |
| `process` | A `chain` (`cycle`: its loop). |
| `equation` | Written on as before; a box drawn round it when it has the board to itself. |
| `timeline` | The timeline in motion, in its `style` (§5). |
| `picture` (a photo, a figure, a made picture) | Dressed the look's way (a cutout as a sticker with a white edge and a shadow; a photo as a card, a polaroid, newsprint or a rounded frame), its labels moved onto the dressed picture, brought on the look's way, floating while up. A picture with the screen to itself stays full-bleed; a book's figure never does (shown whole, dressed). Its labels are chips of the look's accent with boxes and lines in the accent; the light on a part being talked about is a shade cut from the picture's own shape (its card edge, its shadow, a cutout's clear corners are never greyed), feathered round the part, and it follows the picture when the picture moves aside. Moved into half the board, the labels keep three quarters of their size. |
| chapter card, title slide | The number springs in, the kicker is typed, the title's words rise, the accent bar is drawn; the card sweeps up and away. |

Diagrams, maps, worked solutions, questions and free-form Manim are drawn as the current engine draws them, in the
look's colours and fonts, with the look's entrances and transitions where they bring none of their own.

---

## 5. The timeline in five styles

```json
{"op": "timeline", "style": "road", "title": "Babur's road", "events": [["1504", "Kabul"], ["1526", "Panipat"], ["1527", "Agra"]],
 "spans": [["1526", "1857", "Mughal Empire"]], "range": ["1500", "1870"]}
```
`style` (or the script's `timeline`, else `track`) picks one. In every style each event comes on as the line says its
words or its date (whichever it says first), or one after another when it says neither, and is a part to point at.
Dates are read as in BEAT_SCRIPT.md (`"1526"`, `"500 BC"`, `"16th century"`...).

| Style | How it looks and moves |
|---|---|
| `track` | The classic layout (in proportion, its scale of years, its periods in lanes, events above and below with their pictures): the track drawn from the left, the periods faded in; then each event: the lit line runs on to it, its ring pops, its stem is drawn, its date and words drop in. |
| `ribbon` | A thick band of eras (the `spans`, named inside; without them, the unnamed stretches between the events), each block sweeping in from the left, on a thin axis that runs on past them; each event a flag on a pole, above the band or below it, placed so that no flag touches another, no pole runs through a flag and none leaves the board (a date outside every era stands on the axis). |
| `cards` | A line across the middle; each event a card (its date on a chip, its words, its picture) hung above or below it on a string, a pin popping, the card swinging in. |
| `road` | A winding road drawn across the board; a marker travels along it to each stop as it is said (a baked clip), the stop's pin pops and its sign springs up (scaled in with an overshoot). |
| `vertical` | A line down the side; a dot slides down to each event, its date (large) and words sweeping in from both sides. |

A timeline that cannot be drawn in its style falls back to the still one, with a note.

---

## 6. Looks

| Look | Design | Motion |
|---|---|---|
| `paper` | A cream page with fibre and a warm light; Oswald heads, IBM Plex Mono kickers, Libre Franklin words; white cards with soft shadows; a yellow highlight, red stamps; cutouts as stickers, photos on white card. | Lively; things pop with an overshoot; pictures slide in and out; a float while up. |
| `newsroom` | A dark, grainy board with a halftone corner; cream words; red accent; cutouts as stickers, photos as warm newsprint duotones. | Punchy; things drop in; a red wipe between pictures. |
| `chalk` | A charcoal board with chalk smudges and dust; Poppins; sky-blue and chalk-yellow; photos as polaroids. | Calm; things rise in; pictures dissolve; a slow drift. |
| `data` | A dark studio with orange and blue glows; Poppins and Plex Mono; rounded dark cards; orange, green, blue figures. | Lively; things rise in; pictures zoom past. |
| `studio` | A pale grey studio with a soft light; Poppins; white rounded cards; orange and blue. | Lively; things rise in; pictures push up and away. |
| `sketch` | A sketchbook page with a dotted grid; Patrick Hand and Permanent Marker; red and blue pencil; photos taped on. | Lines and words written on; pages turn. |

A look is registered as a style of the lecture engine, so everything the current engine draws (captions, maps,
diagrams, the panel) is in its colours and fonts. Each rests on a classic style (paper → vox, newsroom → atlas, chalk
→ chalkboard, data → cosmos, studio → lab, sketch → whiteboard): the voice tools read that, and the look speaks with
its voice. Textures and dressed pictures are made here (numpy, Pillow) into `.cache/motion/`, once each.

---

## 7. Motion tokens

Seconds, scaled by the energy (calm × 1.3, lively × 1, punchy × 0.8):

| Token | Lively | For |
|---|---|---|
| `fast` | 0.35 | a chip, a tick, a label, an exit |
| `base` | 0.6 | a card, a picture, a heading |
| `slow` | 1.0 | a chart's columns, a line drawn, a counter, a road |
| `stagger` | 0.12 | between the items of a row or list (as a share of each one's time) |
| `hold` | 0.25 | a breath between moments |

Eases (all ones the players have): arrivals `ease_out_cubic` / `ease_out_expo`, pops and drops `ease_out_back` (the
overshoot), exits `rush_into`, slams `ease_in_cubic`, drawing `rush_from`. Motions the players have no verb for are
**baked** into small clips by the exporter: a counter counting, a dot riding a line, a marker along a road, a shake
(`motion_kit.baked`). A spring is a scale-in with the overshoot ease (baked, a sign's words came apart in the players).

---

## 8. What the compiler checks and mends

Everything compile_lecture checks and mends, and for the templates (a note starting `fixed:`, the beat plays on):

- A template missing what it shows is left out: `counter` without `value`, `chart` without numeric items (a line
  needs two), `cards`/`list`/`polaroids` without items, `kpi` without values, `chain` with fewer than two steps,
  `versus` without both titles, `donut` without a number, `document`/`title`/`stamp`/`callout` without text,
  `emphasis` without `target`. A print without a picture is left out.
- Counts cut to fit: chart 12 (line 60), cards 6, chain 7, list 7, kpi 4, polaroids 5, units 1-400 (groups cut to
  the total).
- Unknown values set to the default, with a note: chart `kind` (column), list `mark` (bullet), emphasis `how`
  (pulse), timeline `style` (track), the script's `energy` (lively), `transition` and `timeline` (the look's own),
  `look` (the style's own motion).
- A chart `reference` given as a number is read as `{value}`; one with no value is left out. A highlight phrase not
  in the document's text is left out.
- A picture written as an item's own key (`{"generate": ...}`) is moved into its `picture`.
- `on` is read on any operation: its start, on those words.

---

## 9. What the phones play

Nothing new. Every motion is a verb the exporter writes for the players (fades with shift, scale and rate, create,
write, grow, `.animate` moves, scales and colours, lagged groups), or a play baked into a clip (§7); idle motion is
the players' own drift; textures and dressed pictures are images. A motion scene says `# panim: fixed-layout`, so the
exporter's label pass (for placements a model guessed) leaves the engine's own layout alone. Checked: the paper chart scene exports at **tier 1
with no blockers** (`tools/export_scene.py`), and `dsl.verify_dsl` draws the program frame by frame against Manim's
(mean 1% of pixels off; a lagged group's parts can run a little later in the players than in Manim's render).

---

## 10. Running it and testing it

```sh
.venv/bin/python harness_v2/engine/compile_motion.py script.json -o scene.py --embed-path   # the scene
.venv/bin/python harness_v2/engine/compile_motion.py - --json < script.json                 # as the app calls it
PANIM_TTS=espeak .venv/bin/python -m manim -ql scene.py GeneratedScene                       # a quick render, with a free voice
.venv/bin/python harness_v2/engine/tools/motion_strip.py video.mp4 sheet.png --every 0.5     # how it moves, at a glance
.venv/bin/python harness_v2/engine/tools/export_scene.py scene.py GeneratedScene out         # the program the phones play
```

- **In the app**: the **Lab** tab has the motion presets (each template, each timeline style, each classic operation,
  each look, each transition and energy, and whole scenes), "Add a beat with" its templates, this reference beside
  the editor, and "from a lecture's chapter … drawn by the motion engine" in any look, to see a lecture's own chapter
  in motion. **Speak and play** compiles, speaks, times and plays it as for any experiment.
- **In the Scenes tab**: the **Engine** row (current / motion (beta), with the look, energy, transition and timeline
  style) sets the engine for the run. On motion, the scene writer is also told of the templates (its own instructions
  part, `motion`, after v1's), each lecture's beat script carries `"engine": "motion"` and its settings, and the
  compile, the beat and chapter renders and the Voice tab's speak-and-play are all on the motion engine; an edited
  motion script can be applied there. The beats already built stay as they are when the engine is switched: the motion
  engine draws every current operation, and the current engine leaves the templates out (with a note) until they are
  built again. The lectures and videos made before are never touched.
- **`npm run check`** also builds a lecture on the motion engine from the Scenes tab (stand-in scene writer), checks
  its templates, compiles and renders a beat of it, and switches back.
- **`npm run check`** (harness_v2/app) compiles every motion preset and snippet on the motion engine with nothing
  left out, plays one with the voice, and compiles a lecture's chapter in a motion look.
- `PANIM_IMAGES=1 PANIM_IMAGE_FAKE=1` builds with stand-in pictures, offline.

---

## 11. Known gaps

- **No masks.** A true wipe-reveal of a picture (a mask moving across it) is not a verb the players have; wipes are
  sheets moved across instead, and the highlighter is a stroke drawn on.
- **Blur and glow** are faked: soft shadows are layered copies; a glow is widening faint strokes.
- **The `track` timeline's lit line** runs on to events in the order they are said; said out of order, it jumps.
- **Pictures for the new templates** (cards, prints, a document's portrait) are made by the image model like any
  picture: with no key they are left out (the template plays without them).
- **Timing in the players** of a long lagged group can differ slightly from Manim's render (§9).
- **A run has one engine**: the Scenes tab's setting applies to all its lectures (switching it does not rebuild them).

---

## Keeping this document current

This file is the reference for the motion engine and is checked: `npm run check` fails when compile_motion.py accepts
a template, or reads a script field, that is not named here (in backticks). Any change to what the motion compiler or
engine accepts updates this file in the same change.
