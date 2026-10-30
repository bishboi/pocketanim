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
| `engine/assets.py` | Pictures a score asks for (`pic`, `photo`; sized by what shows, not the clear margin round a cut-out: a cut-out 3.0 across and a print 4.6 unless `size` or `w`/`h` say, never smaller than 1.4 and 2.4; a cut-out loses its background, any flat panel drawn behind it and any stray from the next cell of its sheet), made by an image model through OpenRouter's Image API (`V3_IMAGE_MODEL`), cut out or framed with a soft shadow, kept by their words; flags (`flag jp`) from flag-icons, exact. |
| `engine/kit.py` | The bigger pieces (after v2's kit): timeline / event / span, chart (line, bars, donut), flow (a flow diagram laid out in layers), pyramid, cycle, quote, doc, title, and labels on a picture. Each is one `ent`, placed freely; its parts are what the actions bring on (`in fl[1]`), its places are `NAME.KEY` (`tl.1347`, `fl.town`). `demo/gallery.score` shows every one. |
| `engine/kit2.py` | More pieces: science and maths (numberline, plot, triangle, molecule, equation, circuit), data and civics (race, parliament, market, climate, scatter and area charts), storytelling (quiz, lens, split, clock, odometer, clipping), maps (shade, march, inset, globe, layers). `who` and `polaroids` are drawn in look.py (they hold pictures). |
| `engine/sound.py` | The soundtrack: the voice with small sounds where things happen (a pop, a paper slap, a flick as one is peeled off, footsteps, a scratch, a thud, a chime, a buzz, a whoosh, a page's rustle; all made from numbers) and a quiet music bed ducked under the voice (`music calm|warm|tense|none` in a score, or `V3_MUSIC`; `sound off`, or `V3_SOUND=0`). The timeline, the player, the export and the render all play it. |
| `engine/feel.py` | How things feel (render.py uses it): the paper world's motion (a cut-out slapped down like a sticker, peeled off and flicked away when the score says no way; moves that overshoot a little and settle, tilting as they slide; neighbours nudged when a thing lands), the hand-drawn texture (outlines that boil a few times a second, arrows and paths drawn by a pen with a slight wobble, marks drawn as a hand would: a ring looped round once and a bit, a swooshed underline, a box of four overshooting strokes, a rough highlighter band, a wavy strike, each with the pen's nib at its head, paper grain and a soft vignette over the frame) and parallax (as the camera travels between shots, backdrops and maps slide slower, cut-outs and words faster; never while the camera is in a shot, a zoom to a place on its map included, so each shot's layout is exact while it is looked at). A score turns them off with `texture off`, `parallax off`, `motion plain` (or `V3_TEXTURE=0`, `V3_PARALLAX=0`, `V3_MOTION=plain`). The player draws the same boil from the timeline's `boil` entry. |
| `engine/people.py` | Little drawn people (`ent ann person wear coat hat top tool book at X,Y`, its feet there): a round head with a doodle face that changes: eyes with pupils that look about and lids that droop, tilt and blink, other eyes it can take (× ×, > <, ^ ^, sunglasses), brows that rise and knit, a mouth that smiles, frowns, smirks, wobbles, opens or grins with its tongue out, and sweat, an anger bolt, blush and tears. Faces: happy, calm, joy, laugh, excited, playful, proud, smug, cool, sad, crying, angry, furious, annoyed, suspicious, surprised, shocked, scared, worried, nervous, embarrassed, confused, think, dazed, pained, sleepy, disgusted (`mood FACE` to begin with, `emote P FACE` to ease into another as it plays: every part is a number the pose blends); `stubble`, hair (`hair long-blonde`, `beard`, `longbeard`, `mustache`), a skin tone, clothes (`wear` shirt, tunic, robe, habit, dress, gown, coat, suit, armor, apron, toga, uniform, lab, overalls, vest; `color`), a hat (top, bowler, cap, beret, straw, cowboy, crown, helmet, tricorn, mitre, turban, hood, veil, chef, hardhat, wreath, headscarf), something held (`tool` book, scroll, quill, coin, bag, sword, shield, staff, spear, flag, sign, hammer, pickaxe, torch, lantern, basket, cane, pointer, briefcase), `seat`, `old`, `kid`; what is not said is picked from the name. Posed over time: `walk`, `run`, `point P at T`, `wave`, `talk P "WORDS"`, `carry P THING`, `sit`, `stand`, `turn`, `cheer`, `shrug`, `think`, `bow`, `jump` (a crouch first), `nod`, `dance`, `clap`, `facepalm`, `laugh`, `cry`, `shiver`, `kick`, `look P at T`, `faint` (falls flat; `stand` gets it up), `hug P OTHER`, `emote`; every figure breathes and blinks while it is up. They stand 2.8 tall unless `size` says. `ent de nation Germany [year 1900] [color C] [mood FACE] [named]` is a country as a character: its real shape for a body (never turned over), stick legs and arms, the same face and every verb. Each verb poses only its part (a person can talk while walking). |
| `engine/acts.py` | More of what the score can say. **Cast**: `cast monk person wear habit hat hood mood calm` once at the top (the storyboard writes one for each character seen in two shots or more), then `ent monk at X,Y` (or `ent m2 monk mood sad at X,Y`) in any shot: it looks the same every time. **Things come alive**: `pic "a padlock" alive [mood FACE]`: the picture is the body, with stick legs and arms and the doodle face, and every person's verb works. **Reactions**: `react T idea\|question\|exclaim\|shock\|love\|zzz\|anger\|sweat\|sparkle`, a doodle that pops over a head (or a thing), lives a moment and goes. **Borders that move**: `annex A B`, where B takes A's colour and its border flares (B comes on in A's colour if not yet up); a front line is two paths and a `morph`. **Vehicles**: `travel T PATH`, which follows a route, turns to face its way, tilts with the slope, bobs, and draws the route behind it as dashes (`face left` for a picture drawn facing left; `trail off`). **Two at once**: `give A B THING`, `throw A B THING` (an arc, caught), `shake A B` (a handshake), `push A B`, `tug A B [THING]` (a rope between them), `argue A B "WORDS" ...` (turn by turn, bubbles), `whisper A B "WORDS"`; A walks up to B first. **Picture rows**: `isotype N "WHAT" [per K] [shape person\|coin\|book\|house\|box\|drop\|tree\|bread] [cols C] [lit L] [img "..."]`, N/K figures in rows, the first L lit, with a key "= K WHAT"; its parts are the figures. **Margin notes**: `note "WORDS / second line" [to T]`, in handwriting (Caveat, fetched by setup.sh), a little askew, written on with a curved hand-drawn arrow to T. |
| Map frames | A `map` comes in an atlas frame: a cream mat with a soft shadow, a double rule with the alternating band of a degree scale (a round number of degrees a stretch), the degrees named in the margin, black corners; the map and its frame fill the `w`/`h` asked for. `frame plain` for a bare one; `full` fills the shot's screen edge to edge (no frame). Whatever is drawn on a map (regions, shades, pins, rivers, things put `at MAP.place`, arrows and paths between its places) goes where the map goes when it is moved, scaled or slid. |
| `engine/geo.py` | Real maps' data: countries, coasts, seas, rivers and towns from Natural Earth; the states of a year from historical-basemaps (A. Ourednik, GPL-3.0; fetched when first asked for); places by name (towns, old names such as Constantinople, sites of the past, seas, else OpenStreetMap, cached). In `.cache/geo`. |
| `engine/layout.py` | The layout check (the `layout` step, after the pictures): the score's things built with their real sizes, and what covers what without meaning to (a thing set wholly on a much bigger one, or on a card, box or map, is meant: letters in their tray, a coin in a hand, tools on a map; nothing over words is; a cut-out is measured by what shows of it), runs off its screen or a map, or is empty said by shot, with every thing's size. Shots with problems go back to the score's model once (`V3_LAYOUT_FIX`), then are checked again; a score given by hand is only checked. |
| Words with the voice | `phrase "KEY WORDS"` with `wA-wB in P speak`: each word comes on as it is said. A `num` brought `in` as the voice says it counts up to itself over the word (unless the score counts it; years and small numbers stay). `captions on` (or `V3_CAPTIONS=1`): the narration along the bottom, a few words at a time, the one being said lit. |
| Carried over | `bring T to SHOT [X,Y]` at a camera move: T rides on the screen into the next shot and stays there. `cam SHOT via dive into MAP.place`: into a pin or a picture until it fills the screen, opening on the next shot. `chapter "TITLE"` lines put a chapter bar along the bottom (the video's progress, a tick at each chapter, the chapter's name); `progress on|off`. |
| `engine/parts.py` | Long videos in parts: the cut at pauses (`parts_of`), each part's own score, words and voice slice (`split`, `write`), its place in the whole for the chapter bar (`env`), and `player/parts.json` (`manifest`). |
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

## Long videos (up to 20 minutes and more)

A narration of any length is made the same way: **New run** with the whole narration (one sentence a line), or from
a book with **Seconds each** set up to 1200. Nothing else changes for you; under the hood a long video is made in
**parts** (`engine/parts.py`):

- **Voice, once.** The whole narration is spoken and timed in one take (one voice for all of it). It is then cut
  into parts of about `V3_PART_SECONDS` (150 s) at the pauses between sentences, on frame boundaries
  (`runs/<id>/parts.json`). A narration under about 4 minutes is one part and is made exactly as before.
- **Cast, once.** One call reads the whole narration and writes the recurring characters as `cast` lines, so a
  person, a country or a thing come alive looks the same in minute 2 and minute 19.
- **Storyboard, a call a part, all at once.** Each part's call sees only its words (numbered as in the whole), the
  last words before it, and the cast. A part that opens a new topic starts with `chapter: TITLE`, so the chapter
  bar along the bottom names 5-10 chapters over the whole video.
- **Score**: a call a shot, as always (`V3_SCORE_JOBS` at once; a 20-minute video is about 150-200 shots).
- **Layout, timeline and render, a part at a time, `V3_PART_JOBS` (3) at once.** Each part gets its own score
  (`parts/pK/video.score`: the head of the score, its shots, and the `ent` lines of anything it uses from an
  earlier part), its words timed from its own start, and its slice of the voice. Its timeline goes to
  `player/pK/`; `player/parts.json` lists the parts in order. The chapter bar runs over the whole video, and only
  the last part holds the closing seconds.
- **One soundtrack.** The voice, the small sounds and the music are mixed once for the whole video and played
  under all the parts, so no seam can be heard.
- **Player and export.** The player loads a part as playback reaches it (the next one ahead of time) and seeks
  across the whole video. **Export MP4 from the player** draws all of it. The Manim render (optional, slow)
  renders each part, joins them and lays the soundtrack under them.

**Writing a 20-minute narration.** About 2,700-3,200 words, one sentence a line, told as a documentary in
chapters. From a book: set **Videos** to 1 and **Seconds each** to 1200; the script call is then told to write
chapters, recurring characters and recaps. By hand:

- Open with a hook in the first 20 seconds: a scene, a puzzle or a surprising number, and the big question.
- 5-10 chapters of 2-4 minutes, each starting with a line that names where we are going ("Now, the money.").
- A few recurring characters, always named the same way: the cast call turns them into the same drawing every time.
- Every 3-4 minutes, one sentence summing up, then a turn ("But that raised a new problem.").
- Vary the pace: story, then a number made tangible, then a comparison. Never more than four abstract sentences in a row.
- End on the answer to the opening question.

**What it takes**, roughly, for 20 minutes:
- Calls: about 200 (cast, about 8 storyboard parts, about 180 shots, plus layout fixes); the score model is most
  of the cost.
- Pictures: about 100-200.
- Baking: about 1-1.5 hours with 3 parts at once (more cores: raise `V3_PART_JOBS`).
- Timelines: about 15-40 MB a part.

Settings:

| Setting | Default | What it does |
|---|---|---|
| `V3_PART_SECONDS` | 150 | Part length; shorter parts bake faster and load sooner. |
| `V3_PART_JOBS` | 3 | Parts laid out or baked at once; each takes a core and 1-2 GB. |
| `V3_SCORE_JOBS` | 6 | Model calls at once. |
| `V3_LAYOUT_SHOTS` | 40 | The most shots sent back for layout fixes per round; raise it for long videos. |

A score given by hand that is long is cut into parts in the same way.

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
and actions stay free.

Maps are real and accurate (as v1 and v2's were): `ent eu map europe year 1300 names rivers` draws Europe with the
states of 1300 (no year: today's borders); `ent hre region "Holy Roman Empire" map eu` shades a state, a country or a
sea where it really is; `ent paris pin Paris map eu` marks a town; `ent rhine river Rhine map eu`; any place on a map
is `eu.paris` (`path eu.venice eu.genoa eu.bruges` is a trade route, `cam eu.paris zoom 2` flies there). A region is a
name (europe, british isles, mediterranean, middle east, india...), a country, or `"LON0,LAT0,LON1,LAT1"`; the map
fills the `w`/`h` it is given (12 x 6.6 by default).

Small pictures (`pic`, and what were icons: `icon NAME` is drawn as a small picture of the thing unless
`V3_ICONS=1`) are hand-drawn, like sketchbook doodles with people as simple stick-like figures (`V3_SMALL_STYLE`), and
each is cut out on a paper edge, as a sticker. Photos stay prints. A place beyond a map's region is drawn at the
map's edge, and the layout check says so.

Three image models, each set in `.env.local` (or per run in the app): `V3_IMAGE_MODEL` for pictures (photos,
backdrops, portraits), `V3_IMAGE_MODEL_SMALL` for small cut-out things and icons (`pic`, six to a sheet: a smaller,
cheaper model does), `V3_IMAGE_MODEL_LABELED` for a picture whose parts a `labels` entity names (its parts must show
clearly: a stronger model); a blank one is the image model. A picture is kept by its words, look and kind, with the
model that made it beside it (NAME.model.txt); pictures kept before under a model's own key are moved over, not made
again. Searching Wikimedia Commons for real pictures is off unless `V3_IMAGE_SEARCH=1`; when off, a picture asked for
from the archive is made from the same words.

Pictures are asked for well and cheaply: before any is made, one call to the score's model rewrites each picture's
few words into an exact prompt from the narration and its shot (what, of when and where, materials, pose; kept
beside the picture as NAME.prompt.txt; `V3_IMAGE_REFINE=0` turns it off), and small cut-out objects (`pic`) are asked
for six at a time on one sheet (a 3 x 2 grid on plain grey) and cut apart (`V3_IMAGE_SHEET`). A cell where the model
did not keep to the grid (its object running to the cell's edge, or nothing in it) is made again on its own. Photos
are made one by one.

The bigger pieces (`engine/kit.py`; every one in `demo/gallery.score`), still placed freely and brought on by the
actions, part by part as the voice names them:

```
ent tl     timeline 1000 1400 w 12            # years; tl.1347 is a place on it (`move marker to tl.1347`)
ent bd     event 1347 "black death" on tl     # a card on a stem, kept clear of the others
ent fam    span 1315 1317 "famine" on tl
ent pop    chart line 1000:42 1300:73 1400:45 suffix " m"     # also: chart bars K:V..., chart donut K:V...
ent fl     flow "farm>market:sells grain>town*" "market>lord:rent"   # a flow diagram, laid out in layers
ent soc    pyramid "clergy" "nobles" "peasants"
ent rot    cycle "wheat" "beans" "fallow" label "3 fields"
ent q      quote "Town air makes free." who "people said"
ent ch     doc "Charter of the town" sub "anno 1188" seal
ent t      title "the three orders" sub "part two"
ent parts  labels "spire" "rose window" "portal" on cath     # a picture's parts named
w10        in fl[1] fade          # a piece's parts: the second node with its arrows in
w12        ring fl.town           # a named part
```

Labels on a picture: after the pictures are made, the assets step shows each labelled picture to the vision model
(the critic's, else the run's model) once, which says where each part is; that is kept beside the picture
(`NAME.spots.json`) and the labels point there. `"spire@0.5,0.1"` places one by hand.

More pieces (also `engine/kit.py`, all in the gallery): `compare "manor" "town" "labour:wages"` (two sides, a row
each), `table "crop|season" "wheat|autumn"`, `list "squares" "churches" numbered`, `steps "plough" "sow" "harvest"`,
`stat 20 "of Europe died" suffix "%"` (counts), `calendar 366` (`count cal 366` fills the days), `meter 8 "heat"`
(a thermometer; `grow`), `balance "people" "food"` (`tip bal left`), `venn "nobles" "merchants" label "wealth"`,
`tree "king>lords>knights"`, `chart stack ...` and `chart waffle died:20 lived:80`, `formula "6CO_2 + 6H_2O ->
C_6H_12O_6"`, `backdrop "a snowy forest"` (a softened photo behind a shot), `weather snow|rain` (falls only while up
and in view), `portrait "Edward III" sub "1312 to 1377" img "commons:..."`, `bubble "words" on PERSON`, and a map's
`compass` and `scale` bar. Verbs: `pan PHOTO` (a slow push into a still), `type T`, `fill SHAPE 60`, `connect A B
"words"`, `follow T` (the camera keeps a moving thing in view), `tip`.

More pieces (`engine/kit2.py`; all in the gallery): `numberline -5 5` (`nl.3` a place), `plot "x^2 - 2" -3 3` (`pl.2`
the curve at x = 2), `triangle A:0,0 B:3,0 C:1,2 sides angles`, `molecule H2O`, `equation "2x + 3 = 7" "2x = 4"
"x = 2"`, `circuit "battery>bulb>switch"`, `race "1900|1950|2000" UK:12|8|5 USA:8|14|20` (`count rc 2000`),
`parliament A:303 B:52`, `market` (`grow mk 1` moves demand), `climate J:14:20 ...`, `chart scatter` / `chart area`,
`quiz "Which came first?" "A" "B" answer 1`, `lens "@0.6,0.4" on PIC`, `split "before" "after"`, `clock 9`
(`count clk 17`), `odometer 0` (`count od 1455`), `clipping "HEADLINE"`, `who "NAME" sub "years" where "place"`,
`polaroids "a" "b" "c"`, `shade "WHAT" on MAP France:30 ...`, `march MAP.a MAP.b`, `inset on MAP`, `globe 10,50`,
`layers "crust" "mantle" ... round`. Verbs: `era MAP 1500` (borders change to that year's), `glow T`,
`cam SHOT via page|tear|whip`.

Placing a thing against another: `below X`, `above X`, `left X`, `right X` (X a thing or a part of a piece:
`below fl.economic`; `gap G`): it is put against X's edge with its real size, whatever that turns out to be. A
picture, icon or words put `at` a piece's part (a flow's node, a pyramid's level) goes beside it on the first side
clear of the piece (`side up|down|left|right` says which first), not over it; `at` a map's place or a year still
means exactly there. Marks follow what they mark: a ring round a thing that then moves goes with it.

Marks (verbs; they stay until the thing goes): `ring`, `underline`, `highlight`, `strike`, `box`, `tick`, `cross`,
`stamp T "FREE"`, `callout T "words" up`, `bracket A,B,C "words"`, `spotlight T` (everything else veiled; `lift`
brings one back). `dots 100 shape user` draws people instead of dots.

The score's card stays short: the storyboard names each shot's pieces (`| kit: map, flow`), and a shot's call is told
only those pieces' lines. The assets step makes the pictures between score and render (`V3_IMAGE_JOBS` at once), each
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
