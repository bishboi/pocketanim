# How the engine moves

There is one engine, and this is its motion layer: it draws every lecture the way a modern explainer channel does: everything on screen is **designed in a
look** (colours, fonts, a textured board, cards with soft shadows, pictures dressed as stickers, prints or newsprint)
and **animated with intent** (each template brings its parts on in a choreography, each part landing on the words
that name it, one picture giving way to the next with a transition, nothing ever frozen).

Every beat script is drawn this way: `compile_motion.py` is the lecture compiler (`compile_lecture.py`) with the motion
layer installed (running `compile_lecture.py` installs it too), so everything of BEAT_SCRIPT.md -- its checks and
mends, strict chapters, joins, two pictures at once, hold and reveal, `enter`, `speed`, `point` -- holds, and is drawn
by `motion.MotionLecture` (over `pocket_lecture.MapLecture`) in a look, with every template here. There was once a
separate "motion engine (beta)" beside a "current engine" that drew without looks, transitions, idle motion or sound;
the two are one now, and a script's old `"engine": "motion"` is read and dropped.

How to teach is the writer's: `compile_motion.py` sets `teaching_rules: false` unless the script says otherwise, so
only what is needed to draw the video is checked (known operations and their fields, real places, Manim blocks that
run), never the lecture compiler's teaching rules (empty stretches, plain language, text-heavy beats, the panel's
points). The app's director and scene writer are told every template, how each is used and how to move with intent
(`app/lib/prompts/scenes-templates.ts`, when the "templates" kind is on).

```
beat script (JSON)                     ─▶ compile_motion.py ─▶ Manim scene on motion.MotionLecture ─▶ export_scene.py ─▶ .panim ─▶ phone / web player
                                           = compile_lecture.py          (pocket_lecture's MapLecture,        (unchanged: every motion is a verb
                                             extended in-process           every template in motion)            the players have, or a baked clip)
```

| File | What it is |
|---|---|
| `compile_motion.py` | The compiler: `compile_lecture.py` imported and extended in its own process (the templates, `on`, looks), so every check, mend and picture of the beat script works as it does there. |
| `motion.py` | `MotionLecture`: the engine every scene is drawn on. Extends `pocket_lecture.MapLecture`; redraws the classic operations in motion and adds the templates (`m_*`). |
| `motion_kit.py` | The primitives: words, cards, chips, stamps, marks, and the motions (entrances, emphasis, exits, a counter, a spring, a shake). |
| `motion_timeline.py` | The timeline in five styles. |
| `motion_more.py` | The templates for the shape of a history, a society or an argument: hierarchy, exchange, plan, lineage, lifespan, analogy, myth, ritual, share, calendar, converge, table, ask. |
| `motion_forms.py` | What overlaps, sits between, narrows, measures, weighs, hides, changes or ranks: venn, quadrant, funnel, gauge, scale, iceberg, before_after, ranking. |
| `motion_story.py` | History and storytelling: cause_web, portrait_card, source_vs_reality, population_pyramid, migration_flow, quote_reveal, newspaper, letter, countdown. |
| `motion_explain.py` | Numbers and explanations: race_bars, waterfall, stacked_area, slope, dot_compare, split_number, zoom_in, layers, cycle_wheel, checklist, pros_cons, mind_map. |
| `motion_looks.py` | The fourteen looks: design, motion tokens, textures, picture dressing. |
| `music.py` | The music bed under the voice: soft chords in the look's mood, made by formula, ducked under each line's words (§2). |
| `tools/motion_strip.py` | A contact sheet of a rendered video, every N seconds: how a motion plays, at a glance. |

Contents: [the script](#1-the-script) · [how a beat plays](#2-how-a-beat-plays-in-motion) ·
[templates](#3-the-templates) · [classic operations](#4-the-classic-operations-in-motion) ·
[timelines](#5-the-timeline-in-five-styles) · [looks](#6-looks) · [motion tokens](#7-motion-tokens) ·
[checks and mends](#8-what-the-compiler-checks-and-mends) · [phones](#9-what-the-phones-play) ·
[running and testing](#10-running-it-and-testing-it) · [known gaps](#11-known-gaps)

---

## 1. The script

A script is a beat script ([BEAT_SCRIPT.md](BEAT_SCRIPT.md)): its `chapters`, their beats and their operations, with
these additions. Everything in BEAT_SCRIPT.md holds: the same chapters, beats, operations, pictures, maps and checks.

```json
{
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
| `engine` | `"motion"` | Old scripts only: read and dropped (there is one engine). |
| `look`? | `paper` \| `newsroom` \| `chalk` \| `data` \| `studio` \| `sketch` \| `archive` \| `neon` \| `brush` \| `collage` \| `textbook` \| `chalkcolour` \| `isometric` \| `drafting` | The design and the way of moving (§6). Left out: the script's classic `style` keeps its colours and fonts and moves as its nearest look does (vox, parchment, cardboard → paper; atlas, cosmos, blueprint → data; lab, friendly, water → studio; whiteboard, ink → sketch; chalkboard → chalk). |
| `energy`? | `calm` \| `lively` \| `punchy` | How fast everything moves (§7). Default: the look's own. |
| `transition`? | `slide` \| `push` \| `wipe` \| `dissolve` \| `zoom` \| `page` \| `cut` \| `whip` \| `stack` \| `flash` \| `turn` \| `match` | How one picture gives way to the next (§6, Transitions). Default: the look's own. |
| `idle`? | `float` \| `drift` \| `boil` \| `breathe` \| `sway` \| `parallax` \| `flicker` \| `none` | How what is up keeps moving while the voice goes on (§6, Idle). Default: the look's own. |
| `timeline`? | `track` \| `ribbon` \| `cards` \| `road` \| `vertical` | The default style of a `timeline` (§5). |
| `style`? | a classic style | With a `look`, the pictures are still asked of the image model in this style (so pictures made for a lecture before are found again, not made anew). Left out with a look: the classic style the look rests on (paper → vox, newsroom → atlas, chalk → chalkboard, data → cosmos, studio → lab, sketch → whiteboard). |

**`on`: the words an operation lands on.** Any operation (a template or a classic one) may carry `"on": "<words of
its line>"`: it starts as those words are said (the voice's word times), not as the line begins; `"start"`: as the line
begins. Inside a template, items carry their own `on` (a chart's column, a group of units, a chain's step, a card's
mark); without one, an item lands on its own name when the line says it, or in its turn. Every anchor is checked
against its line, mended or refused (BEAT_SCRIPT.md §4, Anchors); a template without one
lands on the first of its own words the line says.

**Word numbers, `delay` and `in_pause`: timing to a voice recorded first.** An `on` (an operation's or a part's) may
name a word by its number in its line, `"w7"` (w0 its first word, as the line is written, split at spaces): it is made
the words of the line from it, as few as are said there first (`compile_motion._word_ids`), so it is exact where a word
comes twice; a number past the line's end is left out, with a note. Any operation may carry `"delay": 0.4` (seconds
after its words, 0 to 3; `MotionLecture._m_when`, `_cue_plan`), and a `stamp` or an `emphasis` `"in_pause": true`: it
plays in the quiet after its line, which lasts as long as it did unless it needs more (`MotionLecture.beat`); on any
other operation it is left out, with a note (a template played after its line would have its parts' moments before it).

In the app (the Scenes tab, "voice first": on unless switched off, or `V2_SCENES_VOICE_FIRST=0`) each chapter is
**spoken and aligned before its scenes are written** (lib/video.ts `narrate`, engine/tools/chapter_voice.py: the
voice's cache is the one the Voice step reads, so nothing is spoken twice); the director writes its beats and the
choreographer puts each thing and each part on its word number (`app/lib/beat-director.ts`). The Scenes tab's renders
of a chapter spoken first are made with its voice (from the cache: nothing is spoken again) and play it as their clock.

---

## 2. How a beat plays, in motion

**Scenes, not slides.** The scene writer is told to show each idea of the narration (usually a paragraph, 20 to 40 s)
as one scene: one main picture, held while the idea is explained and built on by every later line (a part revealed
or labelled as it is named, an emphasis, a zoom, a stamp in the pause), with a new main picture only where the idea
changes (`"paragraph": true`). With the Scenes tab's director on (the default), a chapter's paragraphs are the
director's own (README "A chapter as beats"): it cuts the chapter into paragraphs, each with one main picture built
up over its lines, and the choreographer puts each thing on its word.

**The pace.** Every line is followed by at least `LINE_PAD` (0.4 s) of quiet, the pause the voice left there when it
is longer, and an idea's last line by `PARAGRAPH_PAD` (1.4 s): the next idea begins after a breath. The voice's own
pace is the Voice step's (`teacher`, the default: 10% slower, pitch kept). Words a picture's layout shrank under
`CHECK_MIN_TEXT` (13 pt) are grown to it in place before the picture comes on (`MotionLecture._m_legible`).

1. **The voice starts.** If the look wipes, a sheet of the accent covers the board just before the voice and
   uncovers it under the line's first words: the cut lands as the line starts. The cover's time is taken from the
   line's own pause after it, so the chapter is as long as before.
2. **The picture's choreography.** A template comes on as it was designed to: its title typed, then its body (a
   chart's baseline drawn, the columns rising one after another, the values popping over them). Parts overlap: each
   starts before the last has landed. The old picture leaves the look's way (slid out, pushed up, zoomed past), and
   the new one starts coming on as the old is mostly gone (`MotionLecture.CROSS`: 0.6 of its exit), not after it.
   The exit is unhurried (the look's base time, an even ease), never a rush: a sudden cut read as a slide changing,
   and an overlap of half the exit piled the old picture, its card and the new one on each other.
3. **Moments on words.** Parts held back come on as the line says them: a chain's next step and the arrow to it, a
   group of units coloured, a card's tick, a phrase highlighted, a timeline's event. A part not said comes on in its
   turn after the template is in. Each is **read** on its words: it starts early by as much of its run as it takes
   for its key words to read (`MotionLecture._readable_share`: a picture's largest words, a term, a question, a
   counter's figure, else its largest image, read once what brings them on is `READ_AT` = 60% through), wherever in
   its entrance they come; what brings no words on starts early by `motion.land_lead` (0.12 s and a third of its
   run). A lead of a third of the run had a long entrance's words still arriving after their word. A part never comes on before its template: one whose words the line says
   before the template's own is held until the template has begun (its start plus half its run, 0.6 s at most), so
   the last picture has left and the new one is coming in when it lands. A new picture set on words that come late
   in its line (past 1.2 s and past a third of it: a term defined at the end of its sentence) comes on as the line
   begins instead (`MotionLecture.LATE_PICTURE`): the old picture stayed up while the line had moved on, and the
   change came as it ended. Its parts still come on their own words. The sync probe does not count it an anchor.
4. **Pointing.** A part of a template on screen whose name a later line says is pointed at the look's way (a
   column pulses and its value grows, a card lifts). On a large template (over half the stage), the first part a
   line names is **pushed in on** instead, as a camera would: the template scaled 1.12 about the part and drawn a
   third of the way to the middle (the part kept whole on the screen), held, and eased back before the line ends
   (`MotionLecture._push_on`; moves the players apply). `emphasis` points on purpose (§3). A line that brings a new
   picture points at nothing of the old one, which is leaving; and any pulse, push or pointer whose picture has left
   by the time it plays is dropped (`MotionLecture._unstale`): played, it put the old picture back under every one
   after it (a migration's discs over a timeline).
5. **Match cuts** (off unless `PANIM_CARRY=1`: the carried copies were left over the next picture in the players).
   When the next picture shows a word or a figure (three words at most, on one line: never a
   question or a sentence) the one leaving shows too, in a like size (a
   counter's "60%" in the next card, a term defined and then a headline), a copy of it flies to its place in the new
   picture, taking its size, and dissolves into it as the new picture's own word comes on (`_carry_from`,
   `_carry_into`; two at most a change).
6. **Room made when it is needed.** A template with a definition card (or another card of words) beside it keeps
   the whole stage until the card is said, then slides to its half as the card comes on (`MotionLecture._beside`);
   its parts still to come on are moved with it as the card comes on (`_room_moves`), so they arrive in its half.
   A part not on the screen yet is never pointed at (no bracket round an empty space).
7. **Idle.** What is up keeps moving gently (the look's or the script's `idle`: a float, a slow drift, a breath, a
   sway, a slow parallax, a film's flicker; played by the players themselves), so nothing is frozen while the voice
   goes on.
8. **The pause after a line** is the voice's own (the gap it left there when the chapter was spoken in one take,
   else the pace's 0.3 s); the longer paragraph hold (0.8 s) only after a beat whose next is marked `"paragraph": true`,
   and a beat's `pause` adds to it (`compile_motion._patched_paragraphs`). Read as the lecture compiler reads them,
   almost every beat here put up a picture of its own and closed a paragraph: 0.8 s of quiet after every sentence.
9. **Sound.** Each motion has its sound, under the voice: pops, swishes, a stamp's thud, a counter's ticks, a pen's
   scratch (sfx.py), tuned to the look (`MotionLecture._sound_for`): a calm look's softer (a swish for a whoosh,
   pops 4 dB down, a punchy look's 1.5 dB up); the same sound again within 2 s is 6 dB quieter and a third is left
   out; one that lands within 80 ms of a stressed word is 6 dB quieter; a hold the caption's underline moves in makes
   none. Under it all, a **music bed** (`music.py`): soft chords in the look's mood (calm: a pad; lively: plucked
   notes of the chord in eighths too; punchy: and a soft low pulse on the beat), made by formula on the lecture's own
   clock, so the pieces each line adds join into one bed; −24 dB while a word is said and −16 dB in a pause of 0.6 s
   or more, with 150 ms ramps. It is a sound of the line's like the voice, so the video and the players' narration
   track both carry it. It never stops for an animation: what plays between two lines' pieces (a map moving in, a
   picture changing, a chapter's card, the credits) gets the bed too, at its level between words, from where the last
   piece ended (`Lecture._bed_gap`, placed back in time; and to the video's end in `tear_down`).
   `PANIM_MUSIC=off` (the Scenes tab's "music" box) leaves it out; `PANIM_MUSIC_GAIN` adds dB.
10. **Kept alive** (`MotionLecture._lively`). A word the voice **stresses** (said 1.2 standard deviations louder than
   its line's words, from the line's own audio: `_word_stress`) pulses what it names on the screen, two a line at
   most. A stretch of a line with nothing moving for 2 s or more gets one quiet beat on a word said in it (two in a
   stretch of 6 s): what that word names pulses (a part, never the whole picture: swelled as one, the players lost
   it). Neither makes a sound.
   `PANIM_LIVELY=0` turns both off. The sync probe's `still` counts what is left: stretches of 2.5 s or more of a
   spoken line with nothing moving.
11. **Weight.** How a look's things land is its `energy`: calm ones glide in and stop; lively ones overshoot a little
   (a rise, a slide, a zoom eased with an overshoot, an easing the players have) and settle (`motion_kit._feel`). A
   photo alone is never sprung. (A squash on landing and a pull back before leaving moved the whole picture with a
   transform, and the players lost it: taken out.)

Each animation asks for its own length (from the look's tokens, §7), and the beat gives it that length. When the
next moment comes sooner, the animation is shortened to fit.

---

## 3. The templates

Each is an operation (`"op": "<name>"`) and a method of the engine (`MotionLecture.m_<name>`). All take `id` (to point
at their parts later: `"<id>.<part>"`) and `on`. Sizes fit the board (or the stage beside a panel or a map) by
themselves.

**Layouts and entrances: the same template in different forms.** Several templates take `layout`, which arranges
the same content another way (the first is the default):

| Template | `layout` |
|---|---|
| `counter` | `big` (the figure alone), `ring` (inside a ring swept round to value/`max`), `bar` (over a bar filled to value/`max`), `badge` (on a round seal, the label beside it) |
| `list` | `column` (lines sliding in), `grid` (tiles in two columns, dealt in), `pills` (coloured chips flowing in rows, popping in), `steps` (a staircase, numbered) |
| `chain` | `row` (left to right), `column` (top to bottom, wide cards), `zigzag` (along one row, back along a second) |
| `cards` | `row`, `grid` (two rows, larger), `fan` (overlapping, spread like a hand of cards) |
| `versus` | `cards` (two cards side by side), `split` (the stage cut in two coloured halves, a line down the middle), `stack` (one card over the other) |
| `kpi` | `row`, `grid` (two by two), `column` (wide strips, the figure at the right) |

Every template (not `stamp` or `emphasis`) also takes `enter`: how its parts come on, as it is built and as each is
said later -- `pop` (grows from small with an overshoot), `rise` (comes up as it fades in), `drop` (falls in from
above), `slide` (sweeps in from a side), `zoom` (comes from large), `fade`, `flip` (turned in like a card), `write`
(drawn or written), `unfold` (opened out from a fold, as a paper is), `typewrite` (its frame faded in, its words
typed letter by letter), `ink` (bleeding in slowly, as ink into paper), `stamp` (slammed down from large), `spin`
(turning in from small, twice round), `iris` (opening from a point at its middle). Left out, each part comes on its own way (a card dealt, a line slid in, a step popped). An
unknown `layout` or `enter` is left out, with a note. Vary them across a video: the same content need not look the
same twice.

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
| `value` | required | The figure as it ends ("204%", "2,525 km", "$14.06B", "+50%"). Its number counts up from `start` (default 0) easing out, its prefix and suffix kept, its commas and decimals kept. Words with no number, and a rank ("3rd", "21st"), pop in. |
| `label`?, `kicker`?, `sub`? | | Under it, typed over it, under the label. |
| `delta`?, `trend`? | | A change beside it with an arrow: green ▲ up, red ▼ down (`trend`, else from a leading minus). |
| `color`? | | The figure's colour (a palette name or #hex); default the look's accent. |
| `layout`?, `max`? | | `big`, `ring`, `bar` or `badge` (above); a ring or a bar is filled to value/`max` (full without `max`). |

A year as the value ("1949") is not counted up from nothing: it rolls up from forty years before, landing as it is
said.

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
a part. `layout`: `row`, `grid`, `fan`.

### `stamp`: a stamp slammed onto what is up
```json
{"op": "stamp", "text": "Cleared", "on": "cleared", "color": "ROSE", "angle": -10, "at": "center"}
```
A rubber stamp (double-ruled box, capitals, turned by `angle` degrees, default -10) lands from large with a thud (an
earlier stamp still up is lifted off as it lands, and a stamp alone on the board is replaced, never stamped over), onto the picture on the stage
(`at`: center, top, bottom, left, right) and the picture shakes; with nothing up, on the board. At `center` on a
template of words (a timeline, cards), it lands on its lower edge, or its upper, where the stage has room, not over
the words nor over a stamp the template has of its own (a `myth`'s label); a picture takes it in its middle. Put over what is up:
it plays after the beat's pictures.

### `kpi`: data cards
```json
{"op": "kpi", "kicker": "Last quarter", "cards": [{"label": "Sales", "value": "+50%", "delta": "$3.27B", "note": "in sales"},
                                               {"label": "Backlog", "value": "$14.06B", "delta": "+73%", "trend": "up"}]}
```
Two to four cards: a mono label, a big figure that counts up as its card lands, a change with its arrow, a note.
Dealt in one after another. `layout`: `row`, `grid`, `column`.

### `chain`: steps joined by arrows
```json
{"op": "chain", "title": "How a dollar of backlog moves", "loop": true,
 "steps": ["Signed", {"label": "Built", "on": "built"}, {"label": "Billed", "picture": {"generate": "an invoice"}}, "Paid"]}
```
`steps`: two to seven, each a word or `{label, on?, picture?}`, in a row, numbered (or with their pictures). The first pops in with the template; each next step
pops in and the arrow to it is drawn as the line says it (or in its turn); `loop` draws an arrow from the last back to
the first. Each step is a part. `layout`: `row`, `column`, `zigzag` (the loop's arrow goes round the side).

### `list`: points coming in as they are said
```json
{"op": "list", "title": "What to watch", "mark": "check", "items": ["Margins", {"text": "Hiring", "on": "hiring"}, "The next report"]}
```
Up to 7 points; each slides in from the left with its mark (`bullet`, `number`, or `check`: a tick drawn) as it is
said. Each point is a part. `layout`: `column`, `grid`, `pills`, `steps`.

### `versus`: two sides
```json
{"op": "versus", "title": "Two kinds of river",
 "left": {"title": "Himalayan", "points": ["Snow-fed", "Flow all year"]},
 "right": {"title": "Peninsular", "points": ["Rain-fed"], "value": "40%", "picture": {"generate": "a dry river bed"}}}
```
The left card sweeps in from its edge, its points sliding in one after another (on its own `on`, under a title, when
it has one); the right card waits for its own
words (its `on`, else its title said), then sweeps in from the other edge, the VS badge slams down between them and
its points slide in. Each side (`left`, `right`, a title alone or an object): `title`, `points` (up to 4, a point
plain words or `{text, on}` to come on as said), `value` (a big figure), `picture`, `on`. Each side is a part.
`layout`: `cards`, `split`, `stack`.

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

Every play reads each piece of text against what it actually sits on (a card, a chip, the caption bar, else the
board; `legible.py`). A colour that does not read there is taken to the nearest shade of it that does: 4.5:1 for
small words, 3.2:1 for large ones, as the accent's yellow on a cream board. Text over a picture is left as drawn.

There is no `callout` any more: one in a script is left out, with a note.

Each print's caption is set under it, one size for every print, a long one on two lines.

### `emphasis`: pointing on purpose
```json
{"op": "emphasis", "target": "Japan", "how": "circle", "on": "Japan"}
{"op": "emphasis", "target": "chart1.Italy", "how": "box"}
```
At a part of a template on screen (its name, or `<id>.<name>`), or at a whole template on screen by its `id`: `pulse` (default), `circle` (a ring drawn round it by
hand), `underline`, `highlight` (the highlighter behind it), `box` (the house frame), `glow`, `shake`, `dim` (the
rest of its template faded back), `spotlight` (the other named parts of its template faded far back, the part
left lit), `rack` (as a camera's focus racks: the others faded and shrunk a little, the part kept sharp),
`magnify` (a lens with a handle drawn over it), `wiggle` (a quick wiggle), `bounce` (it hops up and lands),
`wash` (its colour washed to the accent), `strike` (a line struck through it: wrong, gone, refused), `sweep` (a
bar swept in under it, left to right). A name not on screen is left out with a note, and so is a part of a template the
same line has already replaced. A mark made on a template the line is moving (aside for a card) moves with it.

### The shapes of a history, a society or an argument (`motion_more.py`)

#### `hierarchy`: tiers of a pyramid
```json
{"op": "hierarchy", "title": "The three orders", "build": "up",
 "tiers": [{"label": "Clergy", "role": "those who pray", "on": "clergy"}, {"label": "Nobility", "role": "those who fight"},
           {"label": "Peasantry", "role": "those who work", "picture": {"generate": "a peasant with a plough"}}],
 "badge": {"tier": "Nobility", "text": "controls the land", "on": "land"}}
```
Two to six `tiers`, the first at the top, each a word or `{label, role?, picture?, on?}`: stacked as a pyramid, the
role beside each on a leader line, its picture to the left. Built from the bottom (`build`: `up`, default) or the top
(`down`), each tier rising in as it is named. A `badge` (`{tier, text, on}`) is slammed beside its tier. Each tier is
a part.

#### `exchange`: what two parties give each other
```json
{"op": "exchange", "title": "A mutual promise", "left": "Lord", "right": {"title": "Vassal", "picture": {"generate": "a kneeling knight"}},
 "flows": [{"from": "left", "text": "protection", "on": "protection"}, {"from": "right", "text": "loyalty", "on": "loyalty"}]}
```
The two parties (`left`, `right`: a title or `{title, sub?, picture?}`) sweep in from the sides; each of up to four
`flows` (`{from: left | right, text, on?}`) is drawn across as an arrow from the one who gives it, its words on a chip,
as the line says it. Each party and each flow is a part.

#### `plan`: a site's plan, zone by zone
```json
{"op": "plan", "title": "A manorial estate",
 "zones": [{"label": "Manor-house", "kind": "building", "at": "center"}, {"label": "Fields", "kind": "field", "at": "w", "on": "strips"},
           {"label": "Woodland", "kind": "wood", "at": "ne"}, {"label": "Common pasture", "kind": "pasture", "at": "s"}]}
{"op": "plan", "picture": {"figure": "fig7"}, "zones": [{"label": "Mill", "box": [0.42, 0.55, 0.52, 0.66]}]}
```
Up to twelve `zones`, each `{label, kind?, at?, box?, on?}`, drawn on a board as the line names them. `kind`: `field`
(strips), `wood` (trees), `water`, `pasture`, `building`, `church`, `marsh`, `road`. `at` places a zone on a 3 x 3 grid:
`nw`, `n`, `ne`, `w`, `center`, `e`, `sw`, `s`, `se` (zones sharing a place share it side by side; without one, the
free places in turn). With a `picture` (a book's plan), each zone's `box` `[x0, y0, x1, y1]` (0 to 1 across and down
the picture) is tinted on it instead. Each zone is a part.

#### `lineage`: a family or a dynasty
```json
{"op": "lineage", "title": "A dynasty",
 "people": [{"name": "Charles Martel", "dates": "714", "role": "mayor of the palace"},
            {"name": "Pepin", "dates": "751", "role": "king", "via": "son"},
            {"name": "Charlemagne", "dates": "768", "via": "son", "picture": {"generate": "Charlemagne crowned"}}]}
```
Two to eight `people`, each `{name, dates?, role?, picture?, parent?, via?, on?}`, a card joined to its `parent` (a
name given before; by default the one before) by a line named `via` ("son", "succeeds"). A single line of descent
runs left to right; a family branches down. Each person joins as the line names them, and is a part.

#### `lifespan`: lives on one scale of years
```json
{"op": "lifespan", "title": "Lives", "range": ["700", "2000"],
 "people": [{"name": "Charlemagne", "from": 742, "to": 814}, {"name": "Marc Bloch", "from": 1886, "to": 1944, "on": "Bloch"}],
 "marks": [{"at": 1066, "label": "Norman Conquest", "on": "conquest"}]}
```
Up to seven `people` (`{name, from, to, note?, on?}`, dates as BEAT_SCRIPT.md reads them), each a bar swept from
birth to death on a shared scale as the line names them (overlaps show who lived at the same time); `range` widens
the scale; `marks` (`{at, label, on}`) are dashed lines down at a year. A life without both years (or ending before
it begins) is left out with a note. Each life is a part.

#### `analogy`: matched pairs
```json
{"op": "analogy", "title": "Hildegard's comparison", "left": "In the stable", "right": "In society",
 "pairs": [["Cows", "Clergy"], ["Donkeys", "Nobles"], {"a": "Sheep", "b": "Peasants", "on": "sheep"}],
 "stamp": {"text": "Separate ranks", "on": "ranks"}}
```
Up to six `pairs` (`[a, b]` or `{a, b, on?}`) under two headings (`left`, `right`), each pair sliding in and joined by
an arrow as the line says it; a `stamp` across them at the end. Each pair is a part (by its `a`).

#### `myth`: the wrong idea, then the right one
```json
{"op": "myth", "wrong": "Three separate worlds", "right": "Three groups connected by the same land", "label": "Not quite", "on": "three groups"}
```
The `wrong` idea on a card; as the line gives the `right` one (`on`, else its first three words) the wrong one is
struck through and stamped (`label`, default "Not quite") and the right one slides in under it with a tick.

#### `ritual`: a ceremony, step by step
```json
{"op": "ritual", "title": "Homage and fealty",
 "steps": [{"text": "Kneel before the lord", "on": "kneel"}, {"text": "Swear on the Bible", "on": "Bible"}],
 "objects": [{"name": "Charter"}, {"name": "Staff"}, {"name": "Clod of earth", "on": "clod", "picture": {"generate": "a clod of earth"}}],
 "seal": {"text": "Bound", "on": "binding"}}
```
A parchment headed with the `title`; up to six `steps` (`{text, on?}`) written in, numbered, as they are said; up to
four `objects` (`{name, picture?, on?}`) laid out beside it as they are named; a `seal` pressed at the end. Each step
and object is a part.

#### `share`: one part of a whole
```json
{"op": "share", "label": "The tithe", "total": 10, "part": 1, "unit": "sack",
 "part_label": "to the Church", "rest_label": "kept by the family", "on": "one went"}
```
`total` equal pieces (`unit`: `sack`, `coin`, `box`; at most 20, a larger whole scaled) in a row; as the line names
the share (`on`, else the `part_label`), `part` of them are coloured and lifted out, named (`part_label`), and
"1 in 10" set beside them. `rest_label` names the rest.

#### `calendar`: a year as a ring
```json
{"op": "calendar", "title": "The village year",
 "seasons": [{"from": "March", "to": "May", "label": "Sowing", "on": "sowing"}, {"from": "August", "to": "September", "label": "Harvest"}],
 "days": [{"at": "December 25", "label": "Christmas"}, {"moves": ["March 22", "April 25"], "label": "Easter", "on": "Easter"}]}
```
A ring of months, January at the top, clockwise. Up to six `seasons` (`{from, to, label, on?}`) swept round inside it,
and up to six `days` (`{at, label, on?}`, or `moves: [from, to]` for a day whose date moves: its range dashed on the
ring, "(moves)" on its tag) pinned on it, each tag beside the ring at its height. Dates are a month, with or without
its day. Each season and day is a part.

#### `converge`: many to one
```json
{"op": "converge", "title": "Pilgrimage", "to": {"label": "Canterbury", "picture": {"generate": "Canterbury Cathedral"}},
 "sources": ["Kent", "Essex", {"label": "London", "on": "London"}], "direction": "in"}
```
`to` (a label or `{label, picture?}`) in the middle; up to eight `sources` (`{label, on?}`) round it, each popping in
with its arrow drawn to the middle (`direction`: `in`, default, or `out`: from the middle) as the line names it. Each
is a part.

#### `table`: a few columns, row by row
```json
{"op": "table", "title": "Hierarchies compared", "columns": ["France", "Mesopotamia", "Rome"], "highlight": "France",
 "rows": [{"label": "What justified rank", "cells": ["Three orders", "Temple and palace", "Law and citizenship"], "on": "justified"},
          {"label": "Resources", "cells": ["Land", "Temple estates", "Wealth and slaves"]}]}
```
Two to four `columns` (their headings pop in with the template) and up to five `rows` (`{label, cells, on?}`), each
filled in as the line says it; the `highlight` column in the stamp colour. Each row is a part.

#### `ask`: a question, then its answer
```json
{"op": "ask", "text": "Why did power belong not just to kings?", "kicker": "Our question",
 "answer": "Land, protection and religion made several centres of power", "on": "land, protection"}
```
The question set large beside a question mark (its `kicker` typed over it); when the line gives the `answer` (`on`,
else its first three words) the answer is typed in under it with a tick and the question steps back. Without an
`answer`, `on` is when the question comes on. Set the question at a chapter's start, and ask it again with its answer
where the lecture answers it: given the same `id` while that question is still up, the answer comes in under it
(room made for it) instead of the question coming on a second time; an `ask` with an `answer` and no `id` answers
the question up with the same words the same way. A part still to come on (an answer) that is up
when the next picture replaces its template in the same line leaves with it.

---

### What overlaps, sits between, narrows, measures, weighs, hides, changes or ranks (`motion_forms.py`)

#### `venn`: sets and what they share
```json
{"op": "venn", "title": "Two forces", "sets": [{"label": "Trade", "items": ["markets", "ports"], "on": "trade"},
 {"label": "Faith", "items": ["temples"], "on": "faith"}], "overlap": {"text": "Cities", "on": "cities"}}
```
Two or three `sets` (`{label, items?, on}`; up to 3 items each) as translucent circles, each drawn in and named on
its words, its items written inside; `overlap` (a text, or `{text, on}`) is slammed where they all meet.

#### `quadrant`: two qualities, four fields
```json
{"op": "quadrant", "title": "Cost against return", "x": ["Low cost", "High cost"], "y": ["Low return", "High return"],
 "cells": {"tr": "Big bets", "bl": "Small steps"},
 "items": [{"text": "Railways", "x": 0.85, "y": 0.85, "on": "railways"}, {"text": "Canals", "x": 0.2, "y": 0.25}]}
```
The axes drawn (`x`, `y`: `[low end, high end]`, or `{label, low, high}`), the four fields tinted and named
(`cells`: `tl`, `tr`, `bl`, `br`); each of up to 8 `items` (`{text, x, y, on}`, x and y from 0 to 1, or a
percentage) dropped at its place with its tag as it is said.

#### `funnel`: stages narrowing
```json
{"op": "funnel", "title": "The exam", "stages": [{"label": "Applied", "value": "1,000"}, {"label": "Sat", "value": "300", "on": "three hundred"},
 {"label": "Passed", "value": "40", "on": "forty"}]}
```
Two to six `stages` (`{label, value?, on}`) as bands narrowing down, the first widest; each slides in on its words,
its figure counting up.

#### `gauge`: a dial
```json
{"op": "gauge", "value": 72, "min": 0, "max": 100, "text": "72%", "label": "literacy", "low": "none", "high": "all"}
```
A half dial from `min` to `max` (default 0 and 100; its ends named `low` and `high`), coloured from bad to good
(`invert`: good to bad); the needle swings from the low end to `value` as the figure (`text`, else the value)
counts up; `label` and `sub` under it.

#### `scale`: a balance
```json
{"op": "scale", "title": "What weighed more", "tips": "left",
 "left": {"title": "Exports", "items": [{"text": "Silver", "on": "silver"}, "Silk"]}, "right": {"title": "Imports", "items": ["Rice"]}}
```
A balance; each side (`left`, `right`: `{title, items, weight?}`) a pan; each of its items (up to 4) dropped onto
its pan as it is said; once the last is down the beam tips to the heavier side (`tips`: `left`, `right` or `even`;
else by `weight`, else by how many items).

#### `iceberg`: what is seen, and what lies beneath
```json
{"op": "iceberg", "waterline": "what we see", "above": [{"text": "Castles", "on": "castles"}],
 "below": [{"text": "Taxes", "on": "taxes"}, "Roads", "Rice"]}
```
The waterline (named by `waterline`) and the tip with what is seen (`above`, up to 3); the much larger mass under the water rises into
view as the first thing `below` (up to 5) is said, each written on the ice on its words.

#### `before_after`: a change
```json
{"op": "before_after", "change": "the reform", "before": {"title": "Village rule", "points": ["Local elders"]},
 "after": {"title": "Capital rule", "points": ["Governors"], "on": "after it"}}
```
`before` set on the stage; on `after`'s words (its `on`, else its title) a bar wipes across, the old state steps back
and the new one comes in beside it; `change` is slammed on the divide. Each side: `title`, `points` (up to 4),
`value`, `picture`, `label` (the kicker over it; default BEFORE / AFTER).

#### `ranking`: a leaderboard
```json
{"op": "ranking", "title": "Largest cities", "unit": "k", "order": "up",
 "items": [{"label": "Edo", "value": 1000, "on": "Edo"}, {"label": "Kyoto", "value": 400}, {"label": "Osaka", "value": 350}]}
```
Two to seven places, the first given is first place: each a row with its big place number, a bar to scale (given
values; `unit` after the figure) or its `note`. They come in from the last place up (`order`: `up`, a countdown) or
from the first down (`down`), each on its words; the first place (or `highlight`) is crowned.

### History and storytelling (`motion_story.py`)

#### `map_story`: a journey told on the map
```json
{"op": "map_story", "stops": [{"place": "Kagoshima", "date": "1867"}, {"place": "Kyoto", "date": "1868"},
 {"place": "Tokyo", "label": "Edo", "date": "1868"}]}
```
Written as the map's `journey` (BEAT_SCRIPT.md): the route drawn behind a traveller, each stop (`{place, date?,
label?, picture?}`; two or more, `place` a real place) named "label · date" as it is reached. `color` and `on` pass
through.

#### `cause_web`: many causes, one event
```json
{"op": "cause_web", "effect": {"text": "The revolt"}, "causes": [{"text": "Debt", "weight": 3, "on": "Debt"},
 {"text": "Drought", "weight": 2, "on": "drought"}, {"text": "A weak king", "weight": 1, "on": "weak king"}]}
```
The `effect` (a text, or `{text, on, picture?}`) on the right; up to 6 `causes` (`{text, weight 1-3, on}`) slide in
on the left, each joined to it by an arrow as thick as its weight; the effect pulses as the last lands.

#### `portrait_card`: a person, as a trading card
```json
{"op": "portrait_card", "name": "Tokugawa Ieyasu", "dates": "1543 - 1616", "role": "First shogun",
 "picture": {"generate": "portrait of a samurai lord"}, "facts": [{"text": "Founded the shogunate", "on": "founded"}]}
```
The card turned in: the picture, a banner with the `name`, `dates` and `role`; up to 3 `facts` (`{text, on}`) dealt
beside it as they are said.

#### `source_vs_reality`: what a source says, and what was so
```json
{"op": "source_vs_reality", "source": {"text": "The city burned for a month", "by": "A court chronicle"},
 "reality": {"text": "Records show three days", "on": "in fact"}, "verdict": "Exaggerated"}
```
The `source` (`{text, by?}`) as a quoted page on the left; the `reality` (`{text, on}`) slides in on the right on its
words; `verdict` is stamped at the foot of the source's page (never over the claim it judges).

#### `population_pyramid`: a people by age
```json
{"op": "population_pyramid", "unit": "% of people", "left_label": "Men", "right_label": "Women",
 "groups": [{"label": "60+", "left": 3, "right": 4}, {"label": "20-59", "left": 20, "right": 21}, {"label": "0-19", "left": 24, "right": 23}]}
```
Up to 10 `groups` (`{label, left, right}`, the oldest first) as bars both ways from a spine (`left_label`,
`right_label` over them), growing out row by row from the youngest up.

#### `migration_flow`: who moved where
```json
{"op": "migration_flow", "regions": ["Villages", "Edo", "Osaka"],
 "flows": [{"from": "Villages", "to": "Edo", "value": 5000, "on": "Edo"}, {"from": "Edo", "to": "Osaka", "value": 1200, "on": "Osaka"}]}
```
Two to six `regions` (names, or `{name, on}`) as discs; each of up to 8 `flows` (`{from, to, value, label?, on}`)
an arc as wide as the number who moved, its figure on it, drawn as it is said. Not a map: for real places on a map,
`map_story` or the map's own arrows.

#### `quote_reveal`: a famous line, word by word
```json
{"op": "quote_reveal", "text": "The strong do what they can, and the weak suffer what they must.", "who": "Thucydides",
 "highlight": ["strong", "weak"], "picture": {"generate": "bust of a Greek historian"}}
```
The line set large in a serif, its words coming on one by one as it is spoken, the `highlight` words in the accent;
the speaker's picture and name (`who`) fading in beside it.

#### `newspaper`: news breaking
```json
{"op": "newspaper", "paper": "The Edo Herald", "date": "8 July 1853", "headline": "Black ships in the bay",
 "sub": "American warships anchor off Uraga", "picture": {"generate": "black steamships"}}
```
A front page spun onto the board: masthead (`paper`), `date` line, the `headline` slammed on, `sub`, columns of
print and the picture.

#### `letter`: a letter, written on
```json
{"op": "letter", "to": "Mother", "date": "1853", "text": "The ships are here. Nobody knows what they want.", "sign": "Kenji"}
```
A sheet laid on the board: the `date` and greeting (`to`), the `text` written on in a hand as the line reads it,
signed (`sign`) at the end.

#### `countdown`: the years running down to an event
```json
{"op": "countdown", "steps": [{"text": "1850", "on": "Eighteen fifty"}, {"text": "1852", "on": "fifty two"}],
 "event": {"text": "The ships arrive", "on": "ships arrived"}}
```
A big flip display: each of up to 6 `steps` (`{text, note?, on}`) flips in over the last as it is said; then the
`event` (a text or `{text, on}`) lands with a thud.

### Numbers and explanations (`motion_explain.py`)

#### `race_bars`: a race over time
```json
{"op": "race_bars", "unit": "k", "frames": [{"at": "1700", "values": {"Edo": 300, "Kyoto": 350}},
 {"at": "1750", "values": {"Edo": 800, "Kyoto": 380}, "on": "1750"}]}
```
Up to 8 `frames` (`{at, values: {name: number}, on}`); the first is drawn, then at each next one's words the bars
stretch to their new lengths and re-sort, largest on top, the `at` label rolling over in the corner.

#### `waterfall`: from a start, through gains and losses, to a total
```json
{"op": "waterfall", "start": {"label": "Start", "value": 100}, "total": "End",
 "steps": [{"label": "Taxes", "value": 40, "on": "taxes"}, {"label": "Wars", "value": -60, "on": "wars"}]}
```
`start` (`{label, value}`, or a number), then up to 8 `steps` (`{label, value: +n or -n, on}`) stepping up in green or
down in red from where the last left off; the `total` bar (its label) at the end.

#### `stacked_area`: shares of a whole over time
```json
{"op": "stacked_area", "years": [1700, 1750, 1800], "series": [{"label": "Farming", "values": [70, 62, 55]},
 {"label": "Trade", "values": [30, 38, 45], "on": "trade"}]}
```
Up to 6 `series` (`{label, values, on}`, one value a year) stacked over `years` (two or more), each layer swept in
from the left as it is named.

#### `slope`: then and now
```json
{"op": "slope", "left_label": "1700", "right_label": "1800",
 "items": [{"label": "Rice", "from": 40, "to": 90, "on": "Rice"}, {"label": "Silk", "from": 80, "to": 50, "on": "silk"}]}
```
Up to 7 `items` (`{label, from, to, on}`), each a line from one post to the other, green rising or red falling.

#### `dot_compare`: "one in four" against "one in twenty"
```json
{"op": "dot_compare", "groups": [{"label": "Towns", "part": 25, "total": 100, "text": "1 in 4", "on": "towns"},
 {"label": "Villages", "part": 5, "total": 100, "text": "1 in 20", "on": "villages"}]}
```
Two to four grids of dots (`{label, part, total: 100 or less, text?, on}`), each grid's part filling in as it is said.

#### `split_number`: a total broken into its parts
```json
{"op": "split_number", "value": "3,000,000", "label": "koku of revenue",
 "parts": [{"label": "Rice", "value": 2000000, "on": "rice"}, {"label": "Silk", "value": 1000000, "on": "silk"}]}
```
The big total over a bar; the bar breaks into up to 6 `parts` (`{label, value, on}`), each block sized to its share.

#### `zoom_in`: look closer at one part of a picture
```json
{"op": "zoom_in", "picture": {"generate": "a castle with a gate"}, "box": [0.6, 0.5, 0.9, 0.85], "label": "The gate",
 "note": "Where the guards stood", "on": "gate"}
```
The picture; on `on` a box is drawn round `box` (`[x0, y0, x1, y1]` from 0 to 1, across and down; else its middle)
and the view pushes in on it, its `label` and `note` beside it.

#### `layers`: a stack, lifted apart
```json
{"op": "layers", "layers": [{"label": "Shogun", "on": "shogun"}, {"label": "Daimyo", "on": "daimyo"}, {"label": "Farmers", "on": "farmers"}]}
```
Two to six `layers` (`{label, note?, on}`, the top first) as slabs seen at an angle, each lifted apart and named as
it is said.

#### `cycle_wheel`: a cycle that goes round
```json
{"op": "cycle_wheel", "center": "The rice year", "steps": [{"label": "Plant", "on": "Plant"}, {"label": "Grow", "on": "grow"},
 {"label": "Harvest", "on": "harvest"}]}
```
Three to eight `steps` (`{label, on}`) round a ring with arrows, `center` in the middle; a pointer travels round to
each step as it is said, lighting it.

#### `checklist`: a claim tested point by point
```json
{"op": "checklist", "claim": "The Meiji Restoration was a revolution", "verdict": "Partly",
 "criteria": [{"text": "New rulers", "met": true, "on": "rulers"}, {"text": "Land redistributed", "met": false, "on": "land"}]}
```
The `claim` at the top; up to 6 `criteria` (`{text, met, on}`) ticked or crossed as they are said; the `verdict`
stamped at the end.

#### `pros_cons`: for and against
```json
{"op": "pros_cons", "pros": [{"text": "Trade", "on": "trade"}, {"text": "New ideas", "on": "ideas"}],
 "cons": [{"text": "Unequal treaties", "on": "unequal"}], "lean": "even", "verdict": "Mixed blessing"}
```
Two columns; each point (up to 5 a side) dropped into its column as it is said; a bar under them leans to the
stronger side (`lean`: `pros`, `cons` or `even`; else the longer column), the `verdict` on it.

#### `mind_map`: an idea and what grows from it
```json
{"op": "mind_map", "center": "Modernisation", "branches": [{"label": "Schools", "on": "schools", "children": ["universal"]},
 {"label": "Railways", "on": "railways"}, {"label": "Army", "on": "army"}]}
```
`center` in the middle; up to 8 `branches` (`{label, on, children?: [text]}`) growing out on curved stems, each in
a coloured pill, its children budding off it.

### Built over several lines: `hold`, then `reveal` with `of`

Any template, and a timeline in a `style`, may hold parts back for a later line: `"hold": [<part names>]` (with an
`id`), then on that line `{"op": "reveal", "of": "<id>", "parts": [<names>], "on": "<words>"}` brings them on there
(`MotionLecture.holding`, `reveal_held`; BEAT_SCRIPT.md §5.9). A part's name is
the one its template times it by: a card's title, a list's point, a criterion's text, a side's title, an event's
label. A labelled picture holds labels the same way (`hold`, then `label`).

```json
{"op": "cards", "id": "sch", "title": "Who wrote", "hold": ["Ricci"], "items": [{"title": "Xavier", "big": "1549"}, {"title": "Ricci", "big": "1582"}]}
```
```json
{"op": "reveal", "of": "sch", "parts": ["Ricci"], "on": "Ricci"}
```

---

## 4. The classic operations, in motion

Every operation of BEAT_SCRIPT.md works. On the board, these are redrawn:

| Operation | In motion |
|---|---|
| `stat` | A `counter` (the value counts up, the label under it). In the side panel it stays the panel's line. |
| `bars` | A `chart`: columns (8 or fewer, short labels), else bars. |
| `fact` | Left out: the board has no key point (BEAT_SCRIPT.md, `fact`). |
| `compare` | Two columns: a `versus`. More: `cards`. |
| `define` | The term set large, the highlighter swept under it, the meaning typed in under it. With a picture already up, it goes beside it (the picture moves into the left half, its labels with it) instead of hiding it. |
| `quote` | A card: big quote marks drop in, the words typed on, the speaker slides in. Beside a picture already up, as `define`. |
| `process` | A `chain` (`cycle`: its loop). |
| `equation` | Written on as before; a box drawn round it when it has the board to itself. |
| `timeline` | The timeline in motion, in its `style` (§5). |
| `picture` (a photo, a figure, a made picture) | Dressed the look's way (a cutout as a sticker with a white edge and a shadow; a photo as a card, a polaroid, newsprint or a rounded frame), its labels moved onto the dressed picture, brought on the look's way, floating while up. A picture with the screen to itself stays full-bleed; a book's figure never does (shown whole, dressed). Its labels are chips of the look's accent with boxes and lines in the accent; the light on a part being talked about is a shade cut from the picture's own shape (its card edge, its shadow, a cutout's clear corners are never greyed), feathered round the part, and it follows the picture when the picture moves aside. It moves to each part on its word and lifts once every part has been named, as in BEAT_SCRIPT.md. Moved into half the board, the labels keep three quarters of their size. |
| `picture`'s `move` | Besides the lecture engine's moves, three cameras: `kenburns` (a slow push in and drift, as a documentary films a still), `pan` (carried slowly across it), `pullback` (opens close in and pulls back to the whole). A picture's camera, not a template's. |
| chapter card, title slide | The number springs in, the kicker is typed, the title's words rise, the accent bar is drawn; the card sweeps up and away. |

Diagrams, maps, worked solutions, questions and free-form Manim are drawn as pocket_lecture draws them, in the
look's colours and fonts, with the look's entrances and transitions where they bring none of their own. A map's
`arrow` through three places or more draws each leg as its own gentle arc, joined (never one curve smoothed through
them all, which swung past the middle place and hooked back); one that turns back on itself (more than 110° at a
stop: France, then England, then Italy) is a spread, not a journey, and is drawn as an arrow from the first place to
each of the others in turn, the label on the first (`MotionLecture.flow`). A map of an area (`"region": {"area":
"Western Europe"}`) is fitted to every place its arrows, paths, journeys and markers reach, with room round them
(more under them, for the caption), not to the area's own countries: an arrow into Spain or Italy on a map of
Western Europe ran off the screen (`compile_motion._patched_chapter_frame`).

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

A timeline that cannot be drawn in its style falls back to the still one, with a note. A timeline given an `enter` of its own (`draw`, `travel`, `whole`: BEAT_SCRIPT.md, timeline) and no `style`, in a
script with no `timeline`, comes on that way instead (`MotionLecture.big_timeline`).

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
| `archive` | Sepia paper with foxing; EB Garamond; oxblood accent; photos taped on, as in a box of old papers. | Calm; things bleed in like ink; pictures dissolve; a film's flicker. |
| `neon` | A night board with glowing pink and cyan; Quicksand; rounded dark cards. | Punchy; things open from a point (iris); a white flash between pictures; a breath while up. |
| `brush` | Rice paper with fibres; Playfair Display heads; vermilion seals; ink-wash art. | Calm; ink bleeding in; pictures dissolve; a slow drift. |
| `collage` | Kraft paper; Oswald and Libre Franklin; cut-paper cards; halftone photos. | Punchy; pieces drop in; pictures stack onto the last; a sway. |
| `textbook` | A white page with a fine grid; Source Sans; blue and violet; rounded figures. | Calm; things rise in; pictures push up; no idle. |
| `chalkcolour` | A green board with coloured chalk; Caveat and Patrick Hand; polaroids. | Lively; written on; pictures dissolve; a slow drift. |
| `isometric` | A pale grid of isometric lines; Poppins; teal and coral blocks. | Lively; things rise in; pictures push; a float. |
| `drafting` | A blueprint sheet; Oswald and Plex Mono; pale yellow lines. | Lively; drawn on; pictures turn like a page; still. |

**Transitions** (`transition`): `slide` (the old picture slides out, the new one in), `push` (pushed up and away),
`wipe` (a sheet of the accent covers and uncovers), `dissolve`, `zoom` (zoomed past), `page` (as a page turns),
`cut` (at once), `whip` (a whip pan: the old one flung off sideways, the new one sweeping in fast), `stack` (the new
picture laid over the old, which sinks back), `flash` (a quick white flash), `turn` (turned over like a card),
`match` (the old one zooms past as the new opens from a point at its middle; with the match cuts of §2 it carries a
shared word or figure across).

**Idle** (`idle`): `float` (a gentle bob), `drift` (a slow drift), `boil` (as float, for hand-drawn looks),
`breathe` (swelling and settling in place), `sway` (rocking a little), `parallax` (carried slowly across, as a
camera passing), `flicker` (a quick unsteady tremble, as old film), `none` (still).

A look is registered as a style of the lecture engine, so everything pocket_lecture draws (captions, maps,
diagrams, the panel) is in its colours and fonts. Each rests on a classic style (paper → vox, newsroom → atlas, chalk
→ chalkboard, data → cosmos, studio → lab, sketch → whiteboard): the voice tools read that, and the look speaks with
its voice. Textures and dressed pictures are made here (numpy, Pillow) into `.cache/motion/`, once each.

---

## 7. Motion tokens

Seconds, scaled by the energy (calm × 1.3, lively × 1, punchy × 0.8):

| Token | Lively | For |
|---|---|---|
| `fast` | 0.25 | a chip, a tick, a label, an exit |
| `base` | 0.4 | a card, a picture, a heading |
| `slow` | 0.7 | a chart's columns, a line drawn, a counter, a road |
| `stagger` | 0.1 | between the items of a row or list (as a share of each one's time) |
| `hold` | 0.15 | a breath between moments |

A template's whole entrance takes at most 2.5 s (`motion_looks.TEMPLATE_MOST`); each animation is sped up to finish
before the next one in its line begins.

Eases (all ones the players have): arrivals `ease_out_cubic` / `ease_out_expo`, pops and drops `ease_out_back` (the
overshoot), exits `rush_into`, slams `ease_in_cubic`, drawing `rush_from`. Motions the players have no verb for are
**baked** into small clips by the exporter: a counter counting, a dot riding a line, a marker along a road, a shake
(`motion_kit.baked`). A spring is a scale-in with the overshoot ease (baked, a sign's words came apart in the players).

---

## 8. What the compiler checks and mends

Everything compile_lecture checks and mends, and for the templates (a note starting `fixed:`, the beat plays on):

- A template missing what it shows is left out: `counter` without `value`, `chart` without numeric items (a line
  needs two), `cards`/`list`/`polaroids` without items, `kpi` without values, `chain` with fewer than two steps,
  `versus` without both titles, `donut` without a number, `document`/`title`/`stamp` without text,
  `emphasis` without `target`. A print without a picture is left out. `venn` with fewer than two sets, `funnel` or
  `ranking` with fewer than two, `gauge` without a number, `scale`/`before_after` without both titles, `iceberg`
  without `below`, `quadrant` without both axes. `cause_web` without causes, `source_vs_reality` without both
  texts, `population_pyramid` with fewer than two `{label, left, right}` groups, `migration_flow` without two regions
  and a flow, `countdown` without steps and an event, `race_bars` without frames, `waterfall` without a start and
  steps, `stacked_area` without two years and a series, `slope`/`dot_compare`/`split_number` without their items,
  `zoom_in` without a picture, `layers` with fewer than two, `cycle_wheel` with fewer than three, `checklist`
  without criteria, `pros_cons` with neither side, `mind_map` without branches; `map_story` with fewer than two
  stops.
- Counts cut to fit: chart 12 (line 60), cards 6, chain 7, list 7, kpi 4, polaroids 5, units 1-400 (groups cut to
  the total).
- A `waterfall`'s start and a `race_bars` first frame are drawn with the template (`"on": "start"`), never timed by
  a word of the line their label looks like.
- Cut to fit: cause_web 6 causes, portrait_card 3 facts, population_pyramid 10, migration_flow 6 regions and 8
  flows, countdown 6, race_bars 8 frames, waterfall 8, stacked_area 6, slope 7, dot_compare 4, split_number 6, layers
  6, cycle_wheel 8, checklist 6, pros_cons 5 a side, mind_map 8. A `zoom_in` box that is not four numbers is left out
  (its middle is used); an unknown `lean` is left out. Lists of words are read as their objects (`"Edo"` as
  `{"text": "Edo"}` or `{"label": "Edo"}`).
- An unknown `layout` or `enter` is left out (the default is used), with a note; so is a ranking `order` (up).
- Unknown values set to the default, with a note: chart `kind` (column), list `mark` (bullet), emphasis `how`
  (pulse), timeline `style` (track), the script's `energy` (lively), `transition`, `idle` and `timeline` (the look's own),
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

A picture whose parts come on one by one (a versus card's points faded in after its card) and of which one part is
then pulsed (the card's title, said again) is drawn by the players as its parts while it is on (`dsl/export_dsl.py`,
`split_for`), in the video's order: the card's face, redrawn as parts, is put back under the points it holds, which
it had covered. When the picture leaves whole it is one picture again (`merge_for`), and every part the program drew
on its own goes with it; before, the points stayed, hidden under the card while it was on and then over every later
picture and the closing credits (a lord's points under a timeline). Checked with `tools/phone_check.py` against the
Manim render of a ten-beat chapter (ask, define, migration, chain, versus, hierarchy, timeline, portrait, chain,
stamp, credits): every frame within the limit, nothing left over at the end.

---

## 10. Running it and testing it

```sh
.venv/bin/python harness_v2/engine/compile_motion.py script.json -o scene.py --embed-path   # the scene
.venv/bin/python harness_v2/engine/compile_motion.py - --json < script.json                 # as the app calls it
PANIM_TTS=espeak .venv/bin/python -m manim -ql scene.py GeneratedScene                       # a quick render, with a free voice
.venv/bin/python harness_v2/engine/tools/motion_strip.py video.mp4 sheet.png --every 0.5     # how it moves, at a glance
.venv/bin/python harness_v2/engine/tools/export_scene.py scene.py GeneratedScene out         # the program the phones play
```

- **The word being said, in the caption**: with a voice, the caption underlines each word as it is said (any
  script: the caption is set a line at a time and each word's place measured, as Hindi's joined letters give no
  glyph per letter). The underline moves as fades the exporter writes as verbs (a `lag` of them in place of a hold),
  so the phone and the web player show it too; only in holds (beside a play's own animations, the players hid a
  picture that play moved), so a word said during a play is underlined as the play ends. `PANIM_KARAOKE=0` turns it off.
- **Spoken words under the player**: a render with its voice logs each line's words with their times (the beat log's
  `words`, from `pocket_lecture.line_words`: as aligned, or `est` when only estimated); the Scenes tab's player shows
  the line being spoken under the picture with the word being said lit, so the word times the animations are set to
  can be checked by ear (the caption in the picture comes on with its whole line, so it cannot show them).
- **In the app**: the **Lab** tab has the presets in a look (each template, each timeline style, each classic
  operation, each look, each transition and energy, and whole scenes) beside the beat script's, "Add a beat with" its
  templates, and "from a lecture's chapter" in the run's look. **Speak and play** compiles, speaks, times and plays it
  as for any experiment.
- **In the Scenes tab**: the **Motion** row sets the look, energy, transition, idle motion and timeline style for the
  run (and voice first, the director, the music bed); each lecture's beat script carries them, and every compile,
  render and the Voice tab's speak-and-play draw in them. The beats already built stay as they are until built again;
  the lectures and videos made before are never touched. The "templates" kind (on by default) tells the director and
  the scene writer every template (`app/lib/prompts/scenes-templates.ts`).
- **`npm run check`** (harness_v2/app) builds a lecture in a look from the Scenes tab (stand-in director), checks its
  templates, compiles and renders a beat of it on `MotionLecture`; and compiles the presets in a look and every
  template snippet with nothing left out.
- `PANIM_IMAGES=1 PANIM_IMAGE_FAKE=1` builds with stand-in pictures, offline.

### The QA loop: build chapters, judge them, fix, again

```sh
# test chapters made as the app makes them (lecture written, voice first, motion scenes), from source PDFs; needs
# the environment's model and voice keys; run from a scratch folder (its runs go in ./.data)
node --experimental-strip-types --import harness_v2/app/scripts/ts-resolve.mjs harness_v2/app/scripts/qa-build.mjs \
    harness_v2/engine/examples/qa/sources/feudal.pdf [--minutes 4] [--language hinglish] [--look paper]
# one chapter built and judged / the whole test set (engine/examples/qa/*.json), a table of what failed
.venv/bin/python harness_v2/engine/tools/chapter_qa.py harness_v2/engine/examples/qa/<name>.json out/<name>
.venv/bin/python harness_v2/engine/tools/qa_suite.py --out qa-out [--jobs 3] [--voice fake|real]
```

`chapter_qa.py` builds a chapter as the Scenes tab does (no title slide or closing fade; the credits over the last
picture), spoken in the stand-in voice (`--voice fake`, exact word times, free) or the real one (`--voice real`),
rendered with Manim and exported for the players, and fails it on: a compile error; a picture the engine left out;
a **leftover** (anything of a picture that has left the stage still drawn after a line or under the credits:
`MotionLecture._m_leftovers`, written to the beat log as `leftover`); an export below tier 1; a frame where **the
players differ from the video** (drawn from the program by the reference renderer, `tools/phone_check.py`, the two
clocks lined up by where each line's voice starts on each: the beat log's `voice` rows and the export's `clips`).
Timing (the sync probe: anchors on their words, still seconds a minute) and the engine's visual check are warnings.
Each chapter's `report.json` says why, and `sheet.png` shows each differing frame, the players' beside Manim's.

The program's clock runs a little short of the video's (about 0.07 s a line: verbs run whole frames); the players
place each line's voice on the program's clock, so on a phone voice and picture keep together, and the check lines
the clocks up rather than comparing the same second (the video is rendered at the program's 30 frames a second,
`--fps`, so each play rounds to the same frames; a frame that differs is judged against the program's three either
side, `phone_check.py --slack`; one that is gone half a second either side, a move played a few frames apart, is
a warning, and one still there fails). A test chapter is a beat script as `engineScript` writes it,
with a `qa` field saying where it came from (the compiler ignores it). Every bug fixed adds its chapter to the set.

What the loop has found and fixed so far:
- **The players** (`dsl/export_dsl.py`): a group's members are written at the length Manim plays them (stretched
  onto the group's run time; a crossfade's old picture left early); `.animate(rate_func=...)` keeps its rate (a
  wipe eased out ran at an even speed); a picture's idle drift starts on the first play it is in the scene for,
  shown yet or not, as Manim's does (a picture held back for its word floated two seconds out of step); a group
  drawn whole again hides its parts drawn on their own only when it is itself drawn (`Recorder.absorb`), and a
  picture moved as one (a timeline making room for a card) is put on stage before the move (it vanished); the
  pieces of a baked play (a counter's ring counting up) are declared again in the order Manim draws them, as baked
  shapes (a stage card declared after the number covered it, a ring's track its arc, for the whole line).
- a drifting picture moved aside for a card (its drift's pivot moved with it, `pl.follow_drift`) is declared again
  with the new pivot from that play on, the same start kept (`note_drifts`; the image track starts a new entry), as
  the program declares a drift once: it kept the old pivot, and a Ken Burns photo zoomed about the wrong point.
- **Layout**: a wide picture (wider than `STACK_WIDE`, 2x its height: a timeline, a chain) and a card in the same
  line are stacked, the picture across the top and the card under it (`MotionLecture._halves`), not put side by
  side, where a timeline stood at a third of its size; the closing credits come on a cleared stage (a chapter
  rendered alone has no closing fade, and the credit lines ran across its last picture's words).

---

## 11. Known gaps

- **No masks.** A true wipe-reveal of a picture (a mask moving across it) is not a verb the players have; wipes are
  sheets moved across instead, and the highlighter is a stroke drawn on.
- **Blur and glow** are faked: soft shadows are layered copies; a glow is widening faint strokes.
- **The `track` timeline's lit line** runs on to events in the order they are said; said out of order, it jumps.
- **Pictures for the new templates** (cards, prints, a document's portrait) are made by the image model like any
  picture: with no key they are left out (the template plays without them).
- **Timing in the players** of a long lagged group can differ slightly from Manim's render (§9).
- **A run has one look**: the Scenes tab's Motion row applies to all its lectures (changing it does not rebuild them).

---

## Keeping this document current

This file is the reference for how the engine moves and is checked: `npm run check` fails when compile_motion.py
accepts a template, or reads a script field, that is not named here (in backticks). Any change to what compile_motion.py
or motion*.py accepts updates this file in the same change.
