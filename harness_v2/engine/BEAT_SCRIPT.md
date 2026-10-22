# The beat script: the JSON a lecture video is rendered from

A lecture video is described by one JSON object, the **beat script**. The compiler (`compile_lecture.py`) checks it,
mends what it can, makes the pictures it asks for, and writes a Manim scene on the engine's drawing library
(`pocket_lecture.py`). The exporter (`tools/export_scene.py`) then records that scene as the program the phones
play, and `tools/scene_ir.py` expands it for the browser player.

```
beat script (JSON) ─▶ compile_lecture.py ─▶ Manim scene (Python) ─▶ export_scene.py ─▶ program (.panim) ─▶ phone / web player
                         checks, mends,          pocket_lecture.py          (with the voice: one narration track)
                         makes the pictures
```

Everything here is read from the compiler and the engine as they are (v1's, copied into `harness_v2/engine`). Where
a field is optional it is marked `?`.

To try any of it with the voice, use the app's **Lab** tab: a chapter's beat script (from a preset for each kind of
animation, a lecture's chapter, or blank) is compiled, spoken, its animations timed to the words, and played. Its
presets and "add a beat with" snippets are `app/lib/lab-presets.ts`, and `npm run check` compiles every one of them.

Contents: [the whole script](#1-the-whole-script) · [a chapter](#2-a-chapter) · [a beat](#3-a-beat) ·
[how a beat plays](#4-how-a-beat-plays) · [operations](#5-operations): [board words](#51-the-boards-words) ·
[pictures](#52-pictures) · [diagrams](#53-diagrams) · [kits](#54-cards-kits-and-questions) ·
[worked solutions](#55-worked-solutions-and-problems) · [free-form Manim](#56-free-form-manim) · [map](#57-the-map) ·
[what the compiler checks and mends](#6-what-the-compiler-checks-and-mends) · [colours and looks](#7-colours-styles-and-art-styles) ·
[running it](#8-running-the-compiler) · [known gaps](#9-known-gaps)

---

## 1. The whole script

```json
{
  "title": "India",
  "sub": "The geography of a subcontinent",
  "style": "atlas",
  "art": "auto",
  "region": {"country": "India", "view": "ind"},
  "intro": "Welcome to this lecture on India.",
  "emblem": "a map pin over a river",
  "genre": "geography",
  "figures": {"fig1": {"file": "/abs/path/fig1.png", "caption": "Figure 1: The Ganga basin"}},
  "chapters": [ ... ],
  "recap": [["Rivers", "Snow-fed and rain-fed"]],
  "credits": "Map data: Natural Earth · Animation: Manim"
}
```

| Field | Type | What it does |
|---|---|---|
| `title` | text | The lecture's title: the title slide, and the name of the scene's introduction. |
| `sub`? | text | A line under the title on the title slide. |
| `engine`? | `"motion"` | Drawn by the motion engine (beta, [MOTION_ENGINE.md](MOTION_ENGINE.md)); left out, this engine. The compiler keeps the parts' own anchors (`on`) for its templates. |
| `intro`? | text | What is said over the title slide. Default: `"<title>. <sub>"`. |
| `style`? | name | The **look** (the film's frame, board colour, fonts): `atlas` (default), `parchment`, `lab`, `cosmos`, `vox`, `cardboard`, `whiteboard`, `blueprint`, `chalkboard`, also `friendly`, `ink`, `water`. See §7. |
| `art`? | name | How pictures are drawn: `auto` (the look's own), `clean`, `detailed`, `blueprint`, `chalk`, `sketch`, `neon`, `watercolour`. |
| `region`? | object \| null | The map's region. Without one, a script whose beats use map operations gets the world map (`fixed: the beats use the map but the script has no region`), each beat's map zoomed to the places it names; a script with no map operations has no map. One of: `{"country": "India", "view"?: "ind"}`, `{"state": "Rajasthan", "country": "India"}`, `{"area": "World" \| a continent ("Asia") \| a world region ("South Asia", "Middle East", "Western Europe", "Southern Africa", "Indian subcontinent")}`. With an area, a `state` operation fills a whole country. |
| `emblem`? | text | One simple object that stands for the topic ("a golden crown"). Made once as a small picture and shown on the title, every chapter card and beside the chapter's name. If it cannot be made, there is no emblem. |
| `genre`? | name | The subject: `mathematics`, `physics`, `chemistry`, `biology`, `history`, `geography`, `economics`, `general`. Mathematics, physics and chemistry chapters are taught on a board by default (no side panel), and some checks depend on it (see "wrong maker" in §6). |
| `figures`? | object | The book's figures a beat can show, by id: `{"<id>": {"file": "<path to the picture>", "caption"?, "credit"?, "parts"?: [...]}}`. A `figure` operation (or a `picture` with `"figure"`) names one by its id. |
| `recap`? | list | A recap at the end: `[["Heading", "short body"], ...]`, said and shown point by point. |
| `credits`? | text | The credits line at the end. Pictures made by the image model are credited after it by themselves. |
| `places`? | object | The lecture's own places (a map agent's lookups), used before the gazetteers for every place, area and range. |
| `chapters` | list | The chapters (§2). |

Options read by the checks rather than by the drawing (the v2 app sets `teaching_rules: false`):

| Field | What it does |
|---|---|
| `teaching_rules`? | `false`: how to teach is the writer's. Only what the video needs to be drawn is checked, and the free Manim blocks are test-run. |
| `place_figures`? | `true` (default): the compiler places the book's figures on beats that talk about them when the script did not. `false`: only where the script shows them. |
| `auto_visuals`? | `true` (default): a paragraph that opens with no picture of its own gets one (a molecule or equation its beats contain, a timeline of the chapter's years, pictures of the people and places it names). `false`: none. |
| `auto_illustrations`? | `true`: as a last resort, an illustration of the paragraph's topic. Default off. |
| `rebuild_figures`? | `true`: a book figure is always shown as its redrawn picture, never the book's own image. |
| `layout`? | `"panel"`: chapters keep the side panel instead of the board. |
| `language`?, `subject`?, `source_text`?, `book_questions`? | Inputs for the teaching checks: the narration language, the subject's words, the source (to catch lines read out word for word), and the book's own questions (each must be asked and explained). |

---

## 2. A chapter

```json
{
  "title": "Rivers",
  "sub": "Two great families",
  "narration": "Chapter one. The rivers of India.",
  "beats": [ ... ]
}
```

| Field | Type | What it does |
|---|---|---|
| `title` | text | The chapter's card and its name in the player's chapter list. |
| `sub`? | text | A line under the title on the chapter card. |
| `narration`? | text | What is said over the chapter card. Default: the title. |
| `map`? | false | `false` keeps the map out of the chapter (its map operations are left out with a note). Left out (or `true`), the chapter's beats that point at the map show it in their turn (below). A chapter is never put on the map as a whole. |
| `beats` | list | The beats (§3), in order. |
| `section`? | text | Which part of the source the chapter comes from. Not drawn; carried into the compile's report of the pictures used (their context). |

Where it is taught: every chapter is on the board, or with the side panel when the script says `layout: "panel"`.

- **On a board**: the whole frame is the picture. The words on screen are only the topic heading and one key point.
- **With the side panel** (`layout: "panel"`): the stage on the left, the panel on the right.
- **The map, beat by beat**: with the script's `region`, the map comes in on a beat that points at it (a map
  operation, or an icon placed on places) and stays through the beats after it until one puts up a picture of its
  own with nothing on the map (a photo, a diagram, a template, a `manim` figure): then the map, its marks and its
  panel go and the chapter is back on the board. The beats just before such a run that show nothing of their own (a
  panel title, a fact) are on the map too. Each run is fitted to the places it marks; it is across the whole frame,
  or beside a side panel when its beats put facts, stats or bars in one. A beat that points at the map and shows a
  picture too keeps the map, the picture over it; the next map beat takes the picture away.

---

## 3. A beat

A beat is one narration line and what goes with it on screen.

```json
{"say": "The Ganga is India's longest river.",
 "do": [{"op": "panel", "title": "Rivers"},
        {"op": "river", "name": "Ganges"},
        {"op": "stat", "value": "2,525 km", "label": "Ganga: longest river", "color": "RIVER"}],
 "paragraph": true,
 "pause": 1}
```

| Field | Type | What it does |
|---|---|---|
| `say` | text | The words said, and the caption under the picture. Required. Over about 184 characters, the compiler warns that the caption runs past two lines. |
| `do`? | list | The beat's **operations** (§5), what comes on screen as the line is said. Empty or left out: what is up stays up. |
| `paragraph`? | true | This beat starts a paragraph (an idea over a few beats). The beat before it ends the last paragraph, so it gets the longer hold. Where the script marks none, the compiler finds paragraphs itself. |
| `pause`? | number | Extra seconds of silence after the line (at most 2), for a line that needs to sink in. |
| `about`? | text \| list | Whom or what the beat is about, its English name(s) ("Sunderlal Bahuguna"). Used to find pictures for a paragraph left without a visual (`auto_visuals`). Without it, proper names in the line are used. |
| `picture`? | text | What to picture for this beat if the paragraph is left without a visual (`auto_illustrations`), in English. |
| `rt`? | number | The time (seconds) the beat's animations take, instead of the engine's own. |
| `cues`? | list | Written by the voice step, not by hand: the start (and length) of each animation, timed to the words. |
| (`do` items) `on`? | text | On any operation or part: the words of `say` it lands on, or `"start"` (§4, Anchors). |

---

## 4. How a beat plays

1. **The line is spoken**, with the chosen voice, or silent with an estimate of about 143 words a minute. Its length
   times the beat.
2. **Order**: what goes up (pictures, diagrams, cards, map layers), then what adds to
   them (`work`, `reveal`, `focus`, `zoom`, `answer`, `option`). Otherwise the order is as written.
3. **Timing** (the first that applies, for each animation; each starts 0.2 s before its words):
   - **Its anchor**: the words its `on` names (below).
   - Its part's name when the line says it: a picture's labels, a gallery's next picture, a diagram's next node, a
     place, a term defined.
   - The words it shows, the first the line says: a card, a chart, a timeline, a new diagram (its title or the
     nodes it starts with), a picture (its caption or title).
   - With cues (the voice step, `align_cues.py`), where the timing model puts it.
   - Otherwise, as the line begins, the animations together, quickly (a fifth of the line, 0.6 to 1.2 s).

   The base animations are quick (`PrimitiveRun`): a thing shown 0.6 s, the last picture cleared 0.5 s, none longer than
   2.5 s; each is sped up to finish before the next one in its line begins. A panel's points are their words
   alone, with no bullet; the board has no key point.
4. **Pointing**: something already on screen whose name the line says (a diagram node, a picture's part, a place) is
   pointed at on those words. A labelled picture is shaded round each part as it is named, however quickly the next
   follows; once every labelled part has been talked about, the shade lifts (about a second and a half after the
   last) and the whole picture is clear again, its labels and boxes kept. At most 4 things are pointed at in one
   line.
5. **Holds**: a short hold after the line, and a longer one at a paragraph's end (by the pace: `natural`, `relaxed`,
   `slow`), plus the beat's `pause`.
6. **Staying up**: a picture stays until the next one replaces it, or until a map beat takes the stage away. A question leaves its seconds of silence after its beat.
7. **Safety**: each operation is drawn through a guard. One the engine cannot draw is left out with its reason, and
   the lecture goes on.

### Anchors: `on`

Every operation, and every part inside one, may carry `"on"`: the words of its beat's `say` it lands on, copied as
they are written there (one to four words), or `"start"` (up as the line begins). A part is anything with a name in
an operation: a diagram's node, a timeline's event, a chart's item, a list's point, a column, a card; a picture's
label is written `{"name": "<label>", "on": "<words>"}`.

```json
{"say": "The fields gave more grain than a family could eat, and the extra went into the granary.",
 "do": [{"op": "diagram", "id": "chain", "kind": "flow", "on": "The fields", "show": ["fields", "granary"],
         "nodes": [{"id": "fields", "label": "Fields"}, {"id": "granary", "label": "Granary", "on": "granary"},
                   {"id": "crafts", "label": "Craftsmen"}]}]}
{"say": "The citadel had the Great Bath, a big tank lined with bricks.",
 "do": [{"op": "picture", "generate": "the Great Bath of Mohenjo-daro, a brick-lined tank with steps", "on": "Great Bath",
         "labels": [{"name": "tank", "on": "big tank"}, {"name": "bricks", "on": "bricks"}]}]}
```

The compiler checks each anchor against the line as the voice will say it (`compile_lecture.anchors`): kept when the
line says it, mended to the line's own words when a word is a little off (`fixed: ... "on": "Granaries" is
"granary" in its line`) or written another way: a matra dropped, or the other script ("Japan" for जापान), compared by
the word's consonants in one alphabet (`compile_lecture._skeleton`); and when the line does not say it in any
spelling, taken off with a note (`fixed: ... is not in its line: it comes on in its turn`), the beat playing on. A
part with no anchor of its own whose name the line says in another spelling is timed by the line's words for it
(`fixed: ... 'Kyushu' is timed by 'क्यूशू' in its line`). An anchor of one word of two letters or fewer
(है, थे, "Wu"), too short to be found on its own, is mended to the two words it is said with ("ऊपर थी"). A part's anchor is kept by its name for the line
(`self.spoken_as({...})` before the beat), and the engine times the part by it (`Lecture.spoken_as`, `_said`).

How many operations a beat may carry: the compiler sets **no limit**. Above 5 it warns ("the eye cannot follow more
than about four"); nothing is refused. v1's instructions asked for at most four; v2's scene writer is told no limit by
default (the Scenes tab's pace can set one). One rule is hard: **a `manim` beat carries only its `manim` operation**.

---

## 5. Operations

Every operation is an object with `"op"`. Colours (`color`) are palette names or `#RRGGBB` (§7); left out, the look's
own colour is used.

### 5.1 The board's words

These are always there, on a board or in the side panel.

#### `panel`: the topic heading
```json
{"op": "panel", "title": "Rivers", "sub": "Two great families"}
```
| Arg | | |
|---|---|---|
| `title` | required | The heading. Clears the panel and heads it. |
| `sub`? | | A line under it. |

Start each topic with one. In the side panel, the panel holds a title and a few points; when they would overflow,
the compiler warns to start a new panel.

#### `fact`: one key point
```json
{"op": "fact", "text": "Snow-fed rivers flow all year", "color": "RIVER"}
```
| Arg | | |
|---|---|---|
| `text` | required | A few words (under about 60 characters). In the side panel (`"layout": "panel"`) it is the next line. **The board has no key point**: on a board chapter a `fact` is left out (`fixed: ... the board has no key point`), and the engine draws none. |
| `color`? | | |

#### `stat`: a key number
```json
{"op": "stat", "value": "2,525 km", "label": "Ganga: longest river", "color": "RIVER"}
```
| Arg | | |
|---|---|---|
| `value` | required | The number, large. |
| `label` | required | What it is. |
| `color`? | | |

#### `bars`: a small bar chart
```json
{"op": "bars", "items": [["Ganga", 2525], ["Godavari", 1465]], "unit": "km", "color": "TEAL"}
```
| Arg | | |
|---|---|---|
| `items` | required | `[[label, number], ...]`, at most 8 bars. |
| `unit`? | | Written with the values. |
| `color`? | | |

For many values or change over time, use a `manim` chart instead.

#### `clear`: clear the heading and key point
```json
{"op": "clear"}
```

#### `unstage`: not accepted from a script
`{"op": "unstage"}` exists in the engine (it takes the picture off the stage, back to the map or an empty board, and
would run first on its beat), but the compiler does not accept it from a script: it is left out as "no such op". The
stage is cleared by itself when a map beat follows a picture, and a new picture replaces the last. See §9.

#### `icon`: a small icon on the map or in the panel
```json
{"op": "icon", "name": "wheat", "places": ["Punjab", "Haryana"], "label": "Wheat", "color": "GOLD", "size": 0.6}
```
| Arg | | |
|---|---|---|
| `name` | required | What the icon shows ("wheat", "factory"). Made as a small picture by the image model. |
| `place` \| `places` \| `lonlat`? | | Where on the map. Left out, it goes in the side panel with its `label`. |
| `label`?, `color`?, `size`? | | |

### 5.2 Pictures

One operation for every picture on the stage: `picture`. Its keys decide what it is:

| Key | It is | Made by |
|---|---|---|
| `generate` | a picture of a real thing (a cutout, or a whole scene) | the illustration model, drawn in the style its words describe |
| `draw` | a detailed, labelled textbook diagram (a cell, an organ, a machine) | the diagram model (exact drawings) |
| `figure` | one of the book's figures, by its id in `figures` | the book (or its redrawn copy) |
| `items` | a gallery of several pictures | each item one of the three above |

The older operation names still work: `illustration` (= `generate`), `photo` (`subject` / `query` / `image`),
`figure` (`id`), `draw` (`what`, `parts`), `gallery` (`items`, `title`, `layout`: the same as a `picture` with
`items`).

#### `picture` with `generate`: a real person, place, thing or scene
```json
{"op": "picture", "generate": "a steam locomotive, side view",
 "labels": ["boiler", "chimney", "driving wheels"], "caption": "A steam locomotive", "move": "drift"}
```
| Arg | | |
|---|---|---|
| `generate` | required | What it shows, how it is seen and how it is drawn (the medium, art style, colours and mood are the writer's to choose: nothing sets them), in English. The image model makes it once (kept by its words) as a **cutout** with no background and **no words in it**: only that form is added to the words. |
| `labels`? | 2-6 | Names of parts really in the picture. A vision model finds where each part is, and the board writes each name beside the picture with a line and a box to its part, coming on as the line says the name (§4). |
| `scene`? | true | A whole scene drawn edge to edge (a market, a battle, a way of life) instead of a cutout. A picture that is its line's only visual becomes a full-screen scene by itself. |
| `caption`? | text | Under the picture. |
| `move`? | `bob` \| `sway` \| `breathe` \| `drift` | The picture moves gently once drawn (a boat bobs, a flag sways, a heart breathes, a ship drifts on). Another word is left out with a note. |
| `points`? | 2-4 short lines | The split layout: the picture large on the left, these lines on the right. Not with `labels`. |
| `aspect`? | `16:9` \| `4:3` \| `1:1` | The shape it is made in. Default: the screen's shape when it is the line's only picture. |
| `diagram`? | true | Made by the diagram model (as `draw`). |

Reuse: the same thing asked for again (in the same or other words) is the picture already made, and a named person
is drawn to match their earlier picture. In v2, a decision model (Jev) can decide this instead (`picture_judge.py`).
A picture that cannot be made (no key, refused, taken for a map) is left out with a note, and the line plays without
it. A picture is never a map: the compiler refuses one that asks for a map, an outline, borders or a route.

#### `picture` with `draw`: a detailed labelled diagram
```json
{"op": "picture",
 "draw": "A human heart in front section: right and left atria above the right and left ventricles; the aorta out of the left ventricle; the vena cava into the right atrium",
 "labels": ["right atrium", "left atrium", "right ventricle", "left ventricle", "aorta"],
 "caption": "The heart"}
```
| Arg | | |
|---|---|---|
| `draw` | required | Everything on it, in English, precisely: each part, each arrow and where it points, numbers and units. |
| `labels` | up to 6 | Parts to name (written by the board beside the picture, as above). |
| `caption`? | | |

It is shown whole: its parts are named, not revealed one at a time. The compiler refuses one for a graph or anything
with exact values (those are built in Manim).

The older form `{"op": "draw", "id", "what", "parts": [...]}` is read as this.

#### `picture` with `figure`: one of the book's figures
```json
{"op": "picture", "figure": "fig2", "caption": "Figure 2: The monsoon winds"}
```
| Arg | | |
|---|---|---|
| `figure` | required | Its id in the script's `figures`. An unknown id is left out with a note. |
| `caption`? | | Default: the figure's own caption. |
| `where`? | `stage` \| `panel` | In the older `figure` form: on the stage, or in the side panel (default). |
| `show`? | | The figure's named parts to show, when it has `parts`. |

A book's figure is always shown whole, in its own shape (a tall page, a wide chart): never cut to fill the screen, even
when it is its line's only visual (a gallery of one figure too).

#### `picture` with `items`: a gallery
```json
{"op": "picture", "title": "Kinds of rock", "layout": "spotlight",
 "items": [{"generate": "a piece of granite", "caption": "Granite"},
           {"generate": "a piece of basalt", "caption": "Basalt", "say": "basalt"},
           {"figure": "fig3", "caption": "Marble"}]}
```
| Arg | | |
|---|---|---|
| `items` | required, 2-6 | Each `{generate \| draw \| figure, caption, say?}`. A `draw` in a gallery is made as a picture. |
| `layout`? | `spotlight` (default) \| `grid` | Spotlight: one picture large with the others as thumbnails beneath. Grid: side by side (best for 2-4). |
| `title`? | | |

The first is shown at once. Each other one slides into the spotlight (or pops into the grid) as its caption, or its
`say` words, is said, so name them in the line in that order. Naming one again later brings it back. Items that
cannot be made are left out; with one left it is a single picture, with none the gallery is left out.

#### Pictures beside words

A diagram's node, a timeline's event and a map marker (or a journey's stop) can carry a small picture of the thing:
`"picture": {"generate": "..."}`, `{"draw": "..."}` or `{"figure": "<id>"}`. These are made as small square pictures
and laid out so no picture or word covers another.

### 5.3 Diagrams

#### `diagram`: boxes joined by arrows, built over the beats
```json
{"op": "diagram", "id": "chain", "kind": "flow", "title": "Where the surplus went", "steps": false,
 "nodes": [
   {"id": "fields",  "label": "Fields",  "picture": {"generate": "ploughed fields"}},
   {"id": "granary", "label": "Granary", "kind": "place", "items": ["grain", "seed"]},
   {"id": "crafts",  "label": "Craftsmen", "shape": "process", "anim": "bob"}
 ],
 "edges": [["fields", "granary", "grain"], ["granary", "crafts", "food", "bold"]],
 "show": ["fields", "granary"],
 "flow": true}
```
| Arg | | |
|---|---|---|
| `id` | required | The diagram's name. `reveal`, `focus` and `zoom` refer to it. |
| `kind`? | `flow` (default) \| `cycle` \| `hub` \| `pyramid` | See below. The older kinds still read: `flowchart`, `tree`, `hierarchy`, `categories` (= `flow`), `steps` (= a numbered flow). Unknown: drawn as a flow, with a note. |
| `nodes` | required | 2-9 nodes (a flow up to 16, a hierarchy up to 20). Each node takes the fields in the next table. |
| `edges`? | | `[from, to, label?, style?]` (or `{from, to, label, style}`). `label` says how they connect ("leads to", "light"). `style` is `solid` (default), `dashed` or `bold`. Edges to no node are left out. A flow or cycle with no edges joins its nodes in order. |
| `show`? | | The node ids drawn now. The rest come with `reveal`. Default: all. |
| `title`? | | Over the diagram. |
| `steps`? | true | Numbers a chain's cards (steps in order). |
| `flow`? | true/false | Dots run along the arrows, the way the process goes. On by default for a flow or cycle; `false` turns them off, `true` adds them to a tree or hub. |
| `animate`? | true/false | Whether nodes' pictures move (default on). |
| `drawn`? | `picture` | v2: a `flow` or `cycle` of 2-6 nodes drawn as ONE picture by the image model, then cut into its steps and arrows and built as it is spoken of (below). |
| `about`? | | With `drawn`: what the flow is about, told to the image model ("how bread is made"). |

Each node:

| Field | | |
|---|---|---|
| `id` | required | Unique within the diagram. |
| `label` | required | Short words, in the lecture's language. |
| `picture`? | | A picture of the thing (pictures beside words). A concrete thing gets one; an idea gets none. A flow whose every step is a thing to see becomes **pictures instead of words**: each node is the picture, its name on a chip at its foot. |
| `items`? | up to 5 | Short lines listed in the node (a category's members, what a rank does). |
| `kind`? | `person` \| `place` \| `event` \| `idea` | Drawn as a portrait card, a pin, a dated tag or a soft card. |
| `shape`? | flowcharts | `start`, `end` (pills), `process` (box, default), `decision` (diamond: a yes/no question, its edges labelled "Yes"/"No"), `io` (what goes in or out), `store` (a drum: a tank, a database), `note`. Unknown: a plain box. |
| `lane`? | flowcharts | Who or where does it ("Lok Sabha", "Liver"). Lanes become bands. |
| `anim`? | | The node's picture moves while the diagram is up: `bob`, `hop`, `sway`, `shake`, `flicker`, `spin`, `pulse`, `breathe`, `drift`, `none`, `auto`. |
| `tone`? | | The node's colour role. |

What each kind draws:

- **`flow`**: its layout comes from its edges.
  - No edges, or a chain: in order, left to right, wrapping.
  - Edges that only branch downward from one top: a **hierarchy**, drawn as a textbook tree. The whole is on top,
    its kinds in a row under it, each over its own kinds, joined by right-angled connectors with an open triangle
    ("is a kind of"); long lists of leaves are stacked in columns.
  - Branches, joins, loops, `shape`s or `lane`s: a **flowchart**, laid out in ranks with few crossings and loops
    drawn round the outside.
- **`cycle`**: round, each node to the next.
- **`"drawn": "picture"`** (a `flow` or `cycle` of 2-6 nodes): the picture the image model draws is the diagram,
  revealed in that picture itself as it is spoken of.
  - **One picture.** The image model draws the whole flow at once: each node's `entity` (else its `label`) as a
    picture of its own, well apart, in a row (two rows past four, a circle for a cycle), and one thick arrow for each
    edge (or each pair in order), a gap at both ends, on white, no words. Its style is the one the words describe.
  - **Drawn on where it is.** The compiler finds where each step and each arrow is in the picture (its patches once
    the white is cut away: a step's under the label finder's point for it, else where the layout puts it; an arrow's
    along the line between the steps it joins). Each is drawn on exactly there (its outline traced, then its
    colour), a label under each step: nothing is moved or laid out again, and when every step is said the screen
    shows the picture the model drew. The first step comes on with it, each other one on the words that name it,
    the arrow into it first; `show`, `reveal` and `focus` work as on any diagram. An arrow drawn too dark for the
    board is drawn in the board's ink.
  - **Shown whole when its parts touch.** A picture whose steps cannot be drawn on one by one (they touch, or it is a
    whole scene) is shown whole, each step boxed, named and lit in it as it is said (a labelled picture). Only a
    picture that could not be made is built as a diagram instead (each node's `entity` its own picture), with a
    note.

  ```json
  {"op": "diagram", "id": "bread", "kind": "flow", "drawn": "picture", "about": "how bread is made", "title": "From wheat to bread",
   "nodes": [{"id": "wheat", "label": "Wheat", "entity": "a sheaf of golden wheat"},
             {"id": "mill", "label": "Mill", "entity": "a stone windmill"},
             {"id": "bread", "label": "Bread", "entity": "a round loaf of bread"}],
   "edges": [["wheat", "mill", "harvested"], ["mill", "bread", "ground and baked"]]}
  ```
- **`hub`**: the first node in the middle, the rest around it (a concept map).
- **`pyramid`**: ranks, top first, each with its `items`.

Diagrams are drawn as a teacher draws on a board, outlines first and then their colours, and built as the lines name
their parts.

#### `reveal`: bring in the next nodes
```json
{"op": "reveal", "diagram": "chain", "nodes": ["crafts"]}
```
The named nodes come on, with their arrows. The diagram must be drawn earlier in the chapter. Unknown node ids are
left out, and the reveal too if none is left.

#### `focus`: ring one node while it is talked about
```json
{"op": "focus", "diagram": "chain", "node": "granary"}
```
A ring round the node; the rest dims while it is talked about.

#### `zoom`: move the camera in on one part
```json
{"op": "zoom", "diagram": "chain", "node": "granary", "scale": 2}
{"op": "zoom", "diagram": "chain"}
```
| Arg | | |
|---|---|---|
| `diagram` | required | A diagram (or another picture with named parts) drawn earlier in the chapter. |
| `node`? | | The part to move in on. Left out: back out to the whole. |
| `scale`? | 1.1-3 | How much closer (default 1.8). |

### 5.4 Cards, kits and questions

#### `define`: a hard word and its meaning
```json
{"op": "define", "term": "Surplus", "meaning": "more than a family needs to eat"}
```
`term` and `meaning` are required. Shown as a card on the stage.

#### `compare`: two or three kinds side by side
```json
{"op": "compare", "title": "Two kinds of river",
 "columns": [{"title": "Himalayan", "points": ["Snow-fed", "Flow all year"]},
             {"title": "Peninsular", "points": ["Rain-fed", "Seasonal"]}]}
```
| Arg | | |
|---|---|---|
| `columns` | 2-3 | Each `{title, points: [up to 4 short lines]}`. More than 3 are cut to 3. With 1 column it becomes a card. |
| `title`? | | |

#### `timeline`: dated events across the stage
```json
{"op": "timeline", "title": "The Mughals", "range": ["1500", "1870"],
 "events": [["1526", "Panipat"], ["1556", "Akbar crowned", {"generate": "Akbar, an illustrated portrait"}],
            ["1707", "Aurangzeb dies"], ["1857", "The revolt"]],
 "spans": [["1526", "1857", "Mughal Empire"], ["1556", "1605", "Akbar"], ["1757", "1857", "Company rule"]]}
```
| Arg | | |
|---|---|---|
| `events` | 2-10 | `[date, label, picture?]` (or `{date, label, picture}`). With one event it becomes a card. Past ten, the first ten are kept. |
| `title`? | | Over the timeline. |
| `range`? | `[from, to]` | v2: the years the track covers, to zoom in on a period. Events outside it are left out (with a note). |
| `spans`? | up to 6 | v2: periods `[from, to, label]` (a reign, an era, a war, a dynasty), shaded on the track and drawn as labelled bars in a strip under the scale. Overlapping periods (or their names) are stacked in lanes. A span whose dates are not years is left out. |
| `scale`? | `"even"` | v2: events evenly spaced, for steps with no real dates. |

How it is drawn (v2's engine, `pocket_lecture.big_timeline`, `timeline_dates.py`):

- **In proportion**: when every date reads as a year, each event sits at its date and a scale of round years
  (decades, centuries or millennia, as fits) runs under the track. Without a `range`, the track covers the events and
  spans with a little margin. Dates are read in these forms: `"1526"`, `"500 BC"`, `"320 BCE"`, `"AD 78"`,
  `"c. 1500"`, `"1920s"`, `"1500s"`, `"16th century"`, `"early 18th century"` (early/mid/late), `"3rd millennium BC"`,
  `"15 August 1947"`, `"1947-48"` (its first year), `"10,000 years ago"`.
- **Not every date is a year** ("Stone Age", "Step 2"): evenly spaced, as before; its `range` and `spans` are left
  out with a note.
- **Events and their words**: the events alternate above and below the track, each with its date in a pill and its
  words beyond (and its picture beyond them). Events too close for their words are spread apart along their side,
  each with a slanted stem back to its true date; when a side is too full everything is made a little smaller.
- **Pointing**: the dates, labels and period names are pointed at as they are said. The timeline appears whole and
  holds still.

#### `equation`: a law or a reaction, large
```json
{"op": "equation", "tex": "6CO_2 + 6H_2O \\to C_6H_{12}O_6 + 6O_2", "label": "Photosynthesis"}
```
`tex` (TeX) is required. Without LaTeX on the machine, it is drawn from text.

#### `molecule`: a structural formula
```json
{"op": "molecule", "name": "glucose", "label": "Glucose"}
```
`name` is a common name, a formula (`H2O`) or SMILES, drawn with atoms in CPK colours (needs RDKit). It is used only
where the line explains the structure, once a chapter. The compiler leaves out a molecule on a beat that explains no
structure, and one already drawn in the chapter.

#### `process`: steps in boxes
```json
{"op": "process", "steps": ["Evaporation", "Condensation", "Rain"], "cycle": true, "title": "The water cycle"}
```
2-8 `steps`. `cycle` joins the last back to the first. Use it rarely: a `diagram` is usually better.

#### `quote`: a primary source, in its own words
```json
{"op": "quote", "text": "...", "who": "Akbar"}
```

#### `question`: a question for the class
```json
{"op": "question", "text": "Which of these is a force?",
 "choices": ["Kicking a ball", "Sleeping", "Thinking"], "answer": "A", "think": 5, "title": "Check"}
```
| Arg | | |
|---|---|---|
| `text` | required | The question, in the lecture's language. |
| `choices`? | 2-5 | Short answers. Left out: an open question. |
| `answer`? | | The right choice's letter ("B"), its number (1-5) or its text; or, for an open question, the answer in words. |
| `think`? | seconds | Silence with a timer after the beat, for the class to think (default 7). |
| `title`? | | |

#### `answer`: show the answer
```json
{"op": "answer"}
```
On a later beat: reveals the answer of the question up. It needs a question earlier in the chapter.

#### `option`: mark one choice while it is talked about
```json
{"op": "option", "choice": "B", "right": false}
```
`choice` is a letter, number or text of the question's choices. The choice is crossed out (wrong) or ringed (right);
`right` says which, when given.

### 5.5 Worked solutions and problems

#### `work`: working built line by line
```json
{"op": "work", "id": "w", "title": "Along the slope", "lines": ["N = mg\\cos\\theta", "f = \\mu N"], "box": true}
```
| Arg | | |
|---|---|---|
| `id` | required | The same id on later beats adds lines under the last ones. |
| `lines` | required | TeX for maths (`\frac{a}{b}`, `v^2`, `\text{m/s}`); a line with two words in a row (`"Geography → human history"`) is shown as a sentence, in the lecture's font. One or two a beat, as they are said. |
| `title`? | | |
| `box`? | true | Rings the answer. |

Beside any picture on the stage (a figure, a diagram, a timeline): the picture moves into the left half and the
working takes the right. A wide picture (a timeline, a long chain: more than 2.4 times as wide as tall) moves to the
top at the size it was drawn (smaller only when wider than the board, or when the column would have no room for its
title and this beat's lines) and the working goes below. With a `manim` figure, give the
figure `"area": "left"` so both stay put.

#### `problem`: a long question and its solution
```json
{"op": "problem", "id": "p1", "title": "Problem 1", "text": "A 5 kg block rests on a 30° incline...",
 "given": ["m = 5 kg", "\\theta = 30°"], "find": "a", "think": 5,
 "figure": {"op": "draw", "what": "a block on a 30° smooth incline; its weight mg straight down; the normal force N", "parts": ["block", "mg", "N"]}}
```
| Arg | | |
|---|---|---|
| `id`, `text` | required | The statement goes across the top. Its solution is `work` with the same `id`, beside it. |
| `given`?, `find`? | | Listed with it. |
| `figure`? | | A `draw` (made by the diagram model, its `parts` named), or left out and drawn with `manim` on the beats before. |
| `think`? | seconds | Silence to try it first. |

### 5.6 Free-form Manim

#### `manim`: a figure written as Manim code
```json
{"op": "manim", "id": "ranks",
 "code": "tiers = VGroup(*[Rectangle(width=w, height=1) for w in (6, 4, 2)]).arrange(UP, buff=0)\nself.play(Create(tiers))",
 "area": "left"}
```
| Arg | | |
|---|---|---|
| `id` | required | Beats with the same id share their variables, in order. Build the figure on one beat, then point at, label or move its parts on the next ones. |
| `code` | required | The body of `construct()` for this beat: build objects and `self.play(...)` them, about as long as the line. |
| `area`? | `left` \| `full` | `left`: the figure stays in the board's left half (x -6.9 to -0.4) so a `work`, question or card can sit beside it. The first beat of the id decides. |
| `plan`? | | v2 only: what to draw, in words, for the Manim agent, which writes the `code`. A `manim` op still without code is refused by the compiler; the app asks the agent again (twice at most) for any such figure before it compiles or renders a lecture or chapter. |

Rules (the compiler test-runs each block in a probe scene and refuses one that breaks them, with the reason):

- **The only op on its beat.**
- **Names**:
  - everything Manim exports, and `np`;
  - no imports, classes, `while` loops, dunder names, files or `exec`;
  - of the scene, only `self.play`, `self.wait`, `self.add`, `self.remove`.
- **The board**: x -6.9..6.9, y -3.05..2.85. Nothing outside it.
- **Readable**: no text under font size 20, no two labels overlapping, no line through a label.
- **Animations the phone plays**:
  - `Create`, `Write`, `FadeIn`/`FadeOut`, `GrowArrow`, `DrawBorderThenFill`, `Indicate`;
  - `Transform`, `TransformFromCopy`, `ReplacementTransform`, `TransformMatchingShapes`, `LaggedStart`;
  - `.animate` moves;
  - updaters (`always_redraw`, `ValueTracker`) and `MoveAlongPath`.
- **Colours**: `INK`, `MUTED_INK`, and `PALETTE["ROSE"]`, `["GREEN"]`, `["GOLD"]`, `["RIVER"]`, `["TERRA"]`, `["TEAL"]`, `["VIOLET"]`.
- **Never a map.**

When it plays (`legible.py`):

- **Colours that do not read are fixed.** A colour that does not read on what it sits on (`PALETTE["GOLD"]` words on a
  cream board, cream words on a white card) is taken to the nearest shade that does.
- **Old parts are cleared.** A block drawing over what an earlier block of its figure drew takes the old part away
  as the new one comes: a new picture or filled shape over an old part, new words over old words. A label put on an
  old picture leaves the picture alone.
- **Pictures keep their shape.** A picture from `picture()` or `image()` only scales as a whole: stretched to a width
  or a height, it keeps its proportions, and its labels stay on what they name.

Helpers available in the code:

- `picture("a steam locomotive, side view", height=2, width=?, labels=[...])`: a cutout made by the illustration
  model, with each label written on the picture where that part really is. Bring it in with `FadeIn`. A stand-in
  frame appears if it cannot be made.
- `image("farmer", height=2.5, labels=[...])`: v2 only, a picture the Manim agent made, by its name.

### 5.7 The map

Map operations need the script's `region` (and a chapter not set to `"map": false`). Otherwise they are left out with
a note. The map is up for the beats that point at it (§2, "The map, beat by beat"), in any chapter.
**Name places**; never guess coordinates. The compiler looks names up in real gazetteers (towns and historic sites).
A place it cannot find, or one off the region's map, is left out with a note (an arrow, path or journey keeps its
other points, and is left out when fewer than two are left). A `lonlat` given with a label that names a known place
far from it is moved to where that place really is. A place is its English name; put the lecture's own language in `label`. Give
`lonlat` only for a spot with no name (a point at sea).

#### `marker`: a point
```json
{"op": "marker", "place": "Jaipur", "label": "Jaipur", "color": "ROSE", "side": "right",
 "picture": {"generate": "the Hawa Mahal, illustrated"}}
```
| Arg | | |
|---|---|---|
| `place` \| `lonlat` | one required | A town, a battlefield, a temple, a port; or `[lon, lat]`. |
| `label`? | | |
| `color`? | | |
| `side`? | `left` \| `right` \| `up` \| `down` | Where the label sits. |
| `picture`? | | What is there, above the label. |

Labels never cover one another; the map shows only the last few places named.

#### `river`: a river
```json
{"op": "river", "name": "Ganges", "color": "RIVER"}
```
A Natural Earth river by its English name.

#### `state`: shade an area
```json
{"op": "state", "name": "Normandy", "label": "Normandy", "color": "GOLD", "opacity": 0.6}
```
A state or province, a country, a region or a continent, filled with its name written on it (`opacity` default
0.6). A country or region is the land it covers, never a dot. Use a different colour for each area compared.

#### `arrow`: a curved arrow
```json
{"op": "arrow", "points": ["Delhi", "Agra"], "label": "trade", "color": "GOLD"}
```
Winds, migrations, routes. `points` are places (or `[lon, lat]`). The `label` (what moves) rides the arrow as it is
drawn.

#### `path`: a hand-drawn line
```json
{"op": "path", "points": ["Delhi", "Agra"], "color": "SAND"}
```
A ridge, a canal, a line on the land.

#### `journey`: a traveller moving stop to stop
```json
{"op": "journey", "stops": ["Ahmedabad", "Surat", [72.8, 20.89]],
 "labels": ["Sabarmati", "Surat", "Dandi"], "color": "ROSE",
 "pictures": [null, null, {"draw": "Gandhi picking up salt"}]}
```
At least two `stops` (places or `[lon, lat]`). The route is drawn behind the traveller and each stop is named as it
is reached. `labels` name stops the map may not know; `pictures` are a stop's picture or `null`. For a short route,
narrow the region to its state, or its stops crowd into a dot.

#### `empire`: a state as it stood in a year
```json
{"op": "empire", "name": "Mughal Empire", "year": 1600, "label": "Mughals, 1600", "color": "GOLD"}
```
Filled with its historical border (2000 BC to 2010): kingdoms and empires, never today's borders for the past. Use
its usual English name. A name not on the historical map of that year is left out with a note.

#### `relief`: mountains and plateaus
```json
{"op": "relief", "names": ["Himalayas", "Western Ghats"], "label": true}
```
The mountains and plateaus in view, shaded with hill marks and named. With `names`, only those. `label: false`
leaves out their names.

#### `graticule`: a line of latitude or longitude
```json
{"op": "graticule", "lat": 23.44, "label": "Tropic of Cancer", "color": "MUTED"}
```
One of `lat` or `lon`.

#### `dim`: fade the filled areas
```json
{"op": "dim", "opacity": 0.15}
```
Fades what is filled before highlighting one area.

---

## 6. What the compiler checks and mends

The compiler reads the script in three passes.

**Mends by itself** (a note starting `fixed:`, nothing asked of the writer):

- A `picture` is turned into the operation it amounts to.
- Old diagram kinds are read as new ones.
- An unknown diagram kind becomes a flow; an unknown node shape becomes a box; an unknown motion becomes none.
- More than 5 items in a node are cut to 5; edges to no node are left out.
- A `compare` of one column, or a `timeline` of one event, becomes a card.
- More than 3 compare columns are cut to 3.
- A gallery's unknown layout, or a picture's unknown `move`, is left out.
- A `reveal`, `focus` or `zoom` of no picture drawn earlier in the chapter is left out.
- `answer` or `option` with no question before it is left out.
- A picture beside words that cannot be made is left out; its words stand alone.
- A map place it cannot find, or off the map, is left out; a guessed `lonlat` labelled with a known place is moved to
  where it is.
- A `manim` figure moves its chapter onto the board.

**Leaves out** (with a note, the beat plays without it):

- an unknown operation;
- a retired one (`incline`, `pulley`, `piston`, `spring`, `pendulum`, `projectile`, `circuit`, `lever`, `lens`,
  `sketch`, `graph`, `plot`, `motion`, `trace`, `sweep`, `sim`, `counter`: use `manim`);
- a map operation with no map;
- an operation missing what it draws (`panel` without `title`, `marker` without `place`...);
- an unknown book figure;
- a kit that cannot be drawn (an unknown molecule, a `process` of 1 or 9+ steps);
- a picture the image model could not make.

**Refuses** (an error on the beat; the v2 app sends refused beats back to the scene writer):

- a beat with no `say`;
- a picture, drawing or Manim block that draws a map;
- the **wrong maker**: a graph or exact values asked of the diagram model, or a biology structure drawn in Manim;
- a `manim` beat with other operations;
- a Manim block that breaks the sandbox, raises, draws off the board, or is unreadable;
- a diagram with the wrong number of nodes, or nodes without `id`/`label`;
- a `question` with 1 or more than 5 choices, or an answer that is none of them;
- a `zoom` scale outside 1.1-3;
- a `work` without `id` or `lines`, or a `problem` without `text`.

**Warns**: more than 5 operations on a beat; a caption over two lines; a side panel that overflows.

---

## 7. Colours, styles and art styles

- **Palette names** (for `color`): `SAND`, `DUNE`, `TERRA`, `RUST`, `TEAL`, `RIVER`, `GREEN`, `OLIVE`, `CREAM`,
  `MUTED`, `ROSE`, `GOLD`, `VIOLET`, `HI`, `MOUNT`, or `#RRGGBB`. Each look has its own colour for each name, so a
  script reads well in any look.
- **Looks** (`style`): `atlas` (dark cartographic), `parchment`, `lab`, `cosmos`, `vox`, `cardboard`, `whiteboard`,
  `blueprint`, `chalkboard`, `friendly`, `ink`, `water`.
- **Art styles** (`art`): `clean`, `detailed`, `blueprint`, `chalk`, `sketch`, `neon`, `watercolour`, or `auto` (the
  look's own: atlas → detailed, vox → clean, cardboard → watercolour, whiteboard → sketch...). Pictures, maps and
  diagrams are painted in it; it also sets the fonts of the words on pictures.

---

## 8. Running the compiler

```sh
.venv/bin/python harness_v2/engine/compile_lecture.py script.json -o scene.py   # the Manim scene
.venv/bin/python harness_v2/engine/compile_lecture.py script.json --check       # errors and warnings only, as JSON
.venv/bin/python harness_v2/engine/compile_lecture.py - --json < script.json    # {source, errors, warnings, images, pictures...}
.venv/bin/python harness_v2/engine/tools/export_scene.py scene.py GeneratedScene out   # the program the phones play
```

- **Environment**: `PANIM_VOICE=silent` builds without a voice. `PANIM_IMAGE_MODEL` / `PANIM_DIAGRAM_MODEL` with
  `OPENROUTER_API_KEY` make the pictures; `PANIM_IMAGES=0` turns them off; `PANIM_IMAGE_FAKE=1` uses stand-ins.
- **In the v2 app**: the Scenes tab writes each beat's `do` (and `paragraph`, `pause`, `about`, and the lecture's
  `emblem` and `region`). The Voice tab's **Edit its beat script (JSON) and try it** shows a chapter's script exactly
  as the compiler is given it, to change and play.

---

## 9. Known gaps

- **Arrow meanings are lost.** The drawing engine supports meaning words as an edge's 4th item: `gives`/`provides`
  plain, `owes`/`promises`/`duty`/`loyalty`/`serves` dashed, `power`/`rules`/`controls`/`commands`/`authority`
  bold, with a key under the diagram (`pocket_lecture.EDGE_LOOKS`). The compiler's mend, however, rewrites any style
  other than `solid`/`dashed`/`bold` to `solid` before it gets there. Until that is fixed, use the look words
  (`dashed`, `bold`); the meanings v1's instructions describe arrive as plain arrows.
- **`unstage` is refused from a script** (left out as "no such op") although the engine has it: the compiler's list
  of operations it accepts leaves it out.
- **v2's `plan` on a `manim` op** is not compiled until the Manim agent has written its `code`. A script edited by
  hand needs `code`.

---

## Keeping this document current

This file is the reference for the beat script, and it is checked: `npm run check` (harness_v2/app) fails when the
compiler accepts an operation, or reads a field of the script, a chapter or a beat, that is not written here (each
name in backticks). Any change to what the compiler or the engine accepts (a new operation, a new argument, a changed
limit or default, something mended or refused differently) updates this file in the same change, with an example
that compiles.
