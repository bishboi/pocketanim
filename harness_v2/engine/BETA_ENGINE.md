# The beta engine: slides of boxes, animated on their words

A second way to describe a lecture's visuals, beside the beat script ([BEAT_SCRIPT.md](BEAT_SCRIPT.md)). Instead of
one operation that decides what is drawn, where it goes and how it moves (`timeline`, `diagram`, `compare`), the
beta splits them into three layers, the way slide decks (PowerPoint, Keynote) and JSON video tools (Creatomate,
Shotstack) do:

| Layer | Says | In the script |
|---|---|---|
| **Where** | which slots the screen has, and which box each thing goes in | `layout`, an element's `slot` or `box` |
| **What** | the things on screen, each with an `id`, their parts named `id.part` | `elements` |
| **How** | how each comes on, is pointed at, leaves or moves, and **on which words** | `animate` |

```
beta script (JSON) ─▶ compile_beta.py ─▶ Manim scene on beta_engine.BetaLecture ─▶ export_scene.py ─▶ program ─▶ phones / web
                        checks, mends,        lays out each slide once,                (the same exporter and players:
                        makes the pictures    plays each step on its words              every beta animation is one they play)
```

Try it on the app's **Lab** tab: pick a "Beta:" preset, change its JSON, **Speak and play**. It is a beta: it is
tried on the Lab, not applied to a lecture's scenes (those are the current engine's).

---

## 1. The script

A chapter, as the Lab edits it (the Lab adds the lecture's title and figures):

```json
{
  "engine": "beta",
  "style": "chalkboard",
  "chapter": {
    "title": "From coal to motion",
    "beats": [
      {"say": "Coal heats water into steam, and the steam makes motion.",
       "layout": "three-col",
       "elements": [
         {"id": "a", "shape": "box", "text": "Coal", "slot": "left"},
         {"id": "b", "shape": "circle", "text": "Steam", "slot": "middle"},
         {"id": "c", "shape": "pill", "text": "Motion", "slot": "right"},
         {"id": "ab", "arrow": {"from": "a", "to": "b", "label": "heat"}},
         {"id": "bc", "arrow": {"from": "b", "to": "c"}}
       ],
       "animate": [
         {"id": "a", "in": "pop", "on": "coal"},
         {"id": "ab", "in": "draw", "on": "heats"},
         {"id": "b", "in": "pop", "on": "steam"},
         {"id": "bc", "in": "draw", "on": "makes"},
         {"id": "c", "in": "slide", "from": "right", "on": "motion"}
       ]},
      {"say": "Steam is the key to all of it.",
       "animate": [{"id": "b", "emphasis": "focus", "on": "steam"}]}
    ]
  }
}
```

`style` and `art` are the look, as in the beat script (§7 there). The compiler reads a whole lecture too:
`{"engine": "beta", "title", "style", "chapters": [{"title", "narration", "beats"}]}`.

### A beat

| Field | | |
|---|---|---|
| `say` | required | The words said (and the caption). |
| `layout`? | a layout's name | Starts a **new slide**: what was on the slide before leaves as this line begins. The first beat of a chapter starts one (`full` when it names none). |
| `elements`? | list | What this beat brings onto the slide (§3). Every element of a slide is laid out when the slide starts, so nothing moves or shrinks to make room for a later one. |
| `animate`? | list | The steps (§4). An element this beat brings that no step names fades in, in its turn. |
| `clear`? | true | Everything on the slide leaves as the line begins. |
| `pause`? | seconds | Silence after the line (at most 2). |

---

## 2. Where: layouts, slots and boxes

The board is the frame below the chapter's heading and above the caption. A layout divides it into slots:

| Layout | Slots |
|---|---|
| `full` | `main` |
| `center` | `main` (the middle 70%) |
| `left-right` | `left`, `right` (halves) |
| `wide-left` | `left` (62%), `right` |
| `wide-right` | `left`, `right` (62%) |
| `top-bottom` | `top` (46%), `bottom` |
| `title-body` | `title` (a band, 20%), `body` |
| `title-left-right` | `title`, `left`, `right` |
| `three-col` | `left`, `middle`, `right` |
| `grid-2x2` | `tl`, `tr`, `bl`, `br` |
| `focus-side` | `main` (70%), `side` |

- An element goes in a `slot` of its slide's layout. One with no slot (or a slot the layout lacks) goes in the
  first slot, with a note.
- **Several elements in one slot are stacked down it** in the order given, each as wide as the slot, the stack
  centred; a stack too tall for its slot is made smaller as a whole.
- `"box": [x, y, w, h]` puts an element in its own box instead: shares of the board, `x` from the left, `y` down
  from the top (`[0.6, 0.75, 0.38, 0.2]` is a strip at the bottom right). A box is not checked against the slots:
  it may sit over them (a callout over a picture).

---

## 3. What: elements

Every element has an `id` (letters, digits, `-`, `_`; unique on its slide) and either `kind` or the key that holds
its content: `{"id": "t", "text": "..."}` is a text, `{"id": "l", "list": [...]}` a list.

| Kind | Its content | Parts (`id.part`) | Options |
|---|---|---|---|
| `text` | `"text": "words"` | | `style`: `title`, `heading`, `body` (default), `callout` (in a box), `caption`, `quote`, `label`; `color` |
| `list` | `"list": ["...", ...]` (up to 8) | each item by number: `pts.0`, `pts.1` | `numbered`: true; `style` of its words |
| `image` | `"image": {"generate": "what it shows, in English"}`, or `{"figure": "<the book's figure id>"}`, or `{"file": "<path>"}` | each label by name, lower case, spaces as `-`: `pic.boiler`, `pic.left-ventricle` | `labels`: up to 6 parts really in the picture (a vision model finds each; the name is written beside the picture with a line to it, on the side its part is on; the picture takes the rest of its box); `scene`: true for a whole scene edge to edge |
| `icon` | `"icon": "seed"` | | `label` under it |
| `number` | `"number": {"value": "2,525 km", "label": "length of the Ganga"}` | | `color` |
| `shape` | `"shape": "box"` \| `"circle"` \| `"pill"` | | `text` inside it, `color` |
| `equation` | `"equation": "F = ma"` (TeX) | | `label` under it |
| `bars` | `"bars": {"items": [["Ganga", 2525], ...], "title": "Length (km)"}` (up to 8) | each bar by number: `b.0` | `color` |
| `arrow` | `"arrow": {"from": "<id>", "to": "<id>", "label": "heat"}` | | joins two elements of the slide, edge to edge; needs no slot |
| `timeline` | `"timeline": {"events": [["1526", "Panipat"], ...], "title", "range", "spans", "scale"}` | | the engine's own timeline (BEAT_SCRIPT.md §5.4), drawn for its box |

Aliases: `bullets`/`points` = `list`, `picture`/`photo` = `image`, `chart` = `bars`, `formula` = `equation`,
`stat` = `number`.

Pictures are made when the script is compiled, as the beat script's are: the same image model, cache, reuse
decision and map guard.

---

## 4. How: animation steps

A step names one element or part (`id`) and one of `in`, `emphasis`, `out` or `move`:

```json
{"id": "pts.1", "in": "slide", "from": "left", "on": "boils"}
{"id": "pic.boiler", "emphasis": "highlight", "on": "boiler", "color": "GOLD"}
{"id": "i", "out": "slide", "to": "right"}
{"id": "e", "move": "title", "on": "moves"}
```

| Kind | Values | What it does |
|---|---|---|
| `in` | `fade` (default) | fades in |
| | `slide` + `from`: `left` \| `right` \| `up` \| `down` | comes in from that side |
| | `rise`, `drop` | comes up from below, down from above |
| | `pop` | grows from 60% with a little overshoot |
| | `grow` | grows from small |
| | `type` | a text's letters one after another (typewriter) |
| | `write` | written in as by hand (text, equation, shapes) |
| | `draw` | outlines drawn, then filled (shapes, arrows) |
| | `stagger` | a list's or a chart's items one after another |
| | `appear` | at once |
| `emphasis` | `highlight` | a box round it (round a picture's part: the part's own box) |
| | `circle`, `underline` | a ring round it, a line under it |
| | `pulse`, `flash`, `enlarge` | a quick grow and colour, a burst of lines, a swell and back |
| | `color` + `color` | turns that colour |
| | `dim-others`, `focus` | everything else on the slide dims (`focus` also boxes it) |
| `out` | `fade`, `slide` + `to`, `shrink`, `unwrite` | leaves |
| `move` | a slot's name, or `[x, y, w, h]` | moves (and resizes) into that slot or box |

Marks (`highlight`, `circle`, `underline`, `focus`) and dimming last until the next line begins.

### When: on the words

| Key | |
|---|---|
| `on` | A word or phrase **the line says**: the step starts 0.2 s before it. The time comes from the voice's word times (aligned to the audio) when the chapter is spoken, else from where the phrase stands in the line. A phrase the line does not say is dropped with a note (the step follows the one before). |
| `with` | Another step's `id`: starts with it. |
| `after` | Another step's `id`: starts when it ends. |
| `delay` | Seconds added to the start. |
| `dur` | Seconds it takes (default per preset: a fade 0.8, a slide 0.9, write 1.3, draw 1.6, a highlight 0.6). |

A step with none of these follows the one before it. Steps are played in time order, each kept inside its line;
one that would run into the next is shortened.

The beta is **timed by its words, not by the timing model**: the voice step's timing call (align_cues) does not see
beta beats, so nothing is guessed and nothing is paid for timing.

---

## 5. What the compiler checks and mends

`compile_beta.py` never refuses a script that has words to say. It mends, with a note in the warnings:

- an unknown layout → `full`; a slot the layout lacks → its first slot; a bad box → a slot;
- an element with no id, no kind, no content, or an id already on the slide → left out;
- an arrow joining an element not on the slide → left out;
- a step naming nothing on the slide, or a part the element does not have (its parts are listed) → left out;
- an unknown `in`/`out` → `fade`; an unknown `emphasis` → `pulse`;
- an `on` the line does not say → the step follows the one before;
- a picture the image model could not make, or a label it could not find on the picture → left out.

Refused (errors): no chapters, a chapter with no beats, a beat with no `say`.

```
python compile_beta.py script.json -o scene.py
python compile_beta.py - --json < script.json     # {"source", "errors", "warnings", "minutes", "generated", "images"}
```

---

## 6. For the phones

Every animation the beta plays is one the exporter writes for the phones and the web player: `FadeIn` (with its
shift, scale and rate), `FadeOut`, `Write`, `Create`, `Indicate`, `Flash`, `.animate` colour, move and scale, grouped
and lagged. `npm run check` exports a beta scene and requires tier 1 with nothing blocked.

## 7. Not yet in the beta

- Diagrams with nodes and edges, maps, galleries, worked solutions and free-form Manim are the current engine's;
  the beta has shapes and arrows, and the timeline. More of the current engine's pieces will become elements.
- The camera does not move (`move` resizes an element instead).
- The scene writer still writes beat scripts; beta scripts are written by hand (or by a chat model given this file)
  and tried on the Lab.

## 8. Files

| File | |
|---|---|
| `engine/beta_engine.py` | The runtime: layouts, elements, presets, a beat's plan on its words (`BetaLecture`). |
| `engine/compile_beta.py` | The compiler: checks and mends, makes the pictures, writes the scene. |
| `app/lib/lab-presets.ts` | The Lab's beta presets and "add a beat with" snippets (`LAB_BETA_PRESETS`, `LAB_BETA_SNIPPETS`), each compiled by `npm run check`. |
