# v2's lecture engine

The JSON a lecture is rendered from (the beat script), every operation and its arguments: [BEAT_SCRIPT.md](BEAT_SCRIPT.md).

A copy of v1's lecture engine (`harness/lecture/`, at commit b94dd84), so v2 renders with its own engine and never
reaches into v1's folders. v2 uses it to render maps (`compile_lecture.py` turns a map script into a scene on
`pocket_lecture.py`'s map engine; `app/lib/maps.ts`). Changes made here are v2's own; v1's copy is left as it is.

Its data is downloaded on first use into `data/` and `.cache/` here (historical borders, geocoding), and Natural
Earth by cartopy into its own shared folder, exactly as v1's engine does.

## v2's own changes

- `free_check.image(name, height, width, labels)`: in a Manim block, a picture the v2 Manim agent made, by its name,
  read from the JSON registry `PANIM_BLOCK_IMAGES` names (name to file); a labelled stand-in frame when it is missing.
- `tools/export_scene.py`, `tools/scene_ir.py`: copies of v1's `harness/scripts/` ones, with this
  engine on the path instead of v1's (the repo's `dsl/` and `exporter/` are used as they are): a compiled scene recorded
  into the program the phone plays, and expanded into the geometry v1's web player draws.
- `espeak_tts.py`: an offline voice (`PANIM_TTS=espeak`, espeak-ng), registered in `tts.py`: free and robotic, for
  trying the voice step without a key, and for the checks.
- `local_align`: Whisper `small` by default (v1: `tiny`, which timed Hinglish words loosely); `PANIM_ALIGN_WHISPER`
  picks another. A line's words already aligned stay as they were (`.words.json` beside its audio) until removed.
- `local_align.estimate`: when Whisper cannot be loaded, a line's words spread over its spoken stretches by length,
  each marked `"est"`; `pocket_lecture.line_words` uses an estimate but never keeps it, so Whisper times the line
  once it can.
- `tools/prespeak.py`, `tools/narration.py`: copies of v1's `harness/scripts/` ones on this engine (the exporter's
  narration mix needs `narration.py`). `tools/voice_scene.py`: a spoken scene's lines (audio, length, cost, word
  times and their source), the beats to time with `align_cues`'s prompt, and the timing model's answer checked and
  written into the scene as `cues=` (the app makes the timing call itself, so it is recorded).
- **A chapter spoken in one take** (`PANIM_TTS_WHOLE`, on by default): `tools/prespeak.py` gives a voice that can
  (`gemini_tts.speak_many`, `eleven_tts.speak_many`) all of a scene's lines at once, up to its `WHOLE_CHARS` (4,000,
  `PANIM_TTS_WHOLE_CHARS`) a take, so the chapter keeps one tone and pace. Gemini's take is cut back into lines at
  the pauses between them (`gemini_tts._cut`: the cuts placed in one go, else the take halved at its middle break and
  each half cut on its own); ElevenLabs' at the silences its own letter times give, with each line's word times. Each
  line keeps the pause the voice left after it (its cost file's `"gap"`), and `pocket_lecture.beat_pad` holds that
  long after it (the "natural" pace), so the chapter plays as it was spoken; a take that cannot be cut is spoken
  again `PANIM_TTS_BATCH` lines at a time. The animations are then timed against the whole chapter in one call
  (`align_cues.CHUNK`, 400 beats; the app's `V2_TIMING_CHUNK`).
- Hinglish word matching: `pocket_lecture._say_tokens` keeps a Devanagari word's vowel signs (only Latin letters
  lose their accents), and `compile_lecture._named_in` reads Indian scripts' letters as word letters, so a word that
  names a part is found in a line however it is written.
- **Measuring sync**: `tools/sync_probe.py scene.py --fake-voice` runs a compiled scene without drawing (a stand-in
  voice whose word times are exact) and reports, for each word a line says that something on the screen shows, how
  long before or after the word it came on. `examples/sync/` holds two full lectures to measure with (Hinglish on
  the motion engine, English on the board).
- A picture with words on it that no word was named for (a card, a chart, a timeline, a new diagram) comes on with
  the first of its own words the line says (`compile_lecture._shown_words`, passed as `said=[...]`;
  `Lecture._on_words` takes the first said). A picture is timed by its caption or title only: its labels have their
  own words.
- **Anchors in any spelling** (`compile_lecture.anchors`): an anchor the line says written another way (a matra
  dropped, "Japan" for जापान) is found by its consonants in one alphabet (`_skeleton`); one the line does not say at
  all is taken off with a note instead of refusing the beat (no call spent mending it); a part with no anchor whose
  name the line says another way is timed by the line's words for it. `Lecture._on_words` keeps the word each timed
  cue is on (`_word_cues`), which the motion engine lands its animations on (`motion.land_lead`).
- `picture_judge.py`: with `PANIM_PICTURE_JUDGE` set (a decision model: Jev), whether a picture asked for is one made
  before is the model's answer (show it again, draw a new one matching it, or draw fresh), from the earlier pictures'
  words and prompts, instead of `genimage._reusable` and `reference_for`; answers kept beside the pictures
  (`judge-<key>.json`) and reported in `genimage.report()["judged"]`. `genimage._words` and `_names` leave out colour
  codes, look words and titles.
- **The motion engine (beta)**: `compile_motion.py`, `motion.py`, `motion_kit.py`, `motion_timeline.py`,
  `motion_looks.py`, `tools/motion_strip.py`, documented in [MOTION_ENGINE.md](MOTION_ENGINE.md). Its own files: a
  script is drawn by it only when it says `"engine": "motion"`; compile_lecture and pocket_lecture are imported and
  extended in its process, not changed. `sfx.py` gains three sounds only it uses (`stamp`, `count`, `swish`).
- `MapFrame.xy` keeps every point a number: latitudes off the poles (±85°) and a place the projection cannot reach put
  far off the map. A conic projection sent the pole to NaN, and one NaN in the player's geometry
  (`tools/scene_ir.py`, which now also leaves out any shape or picture key placed by no number) made the whole video
  unplayable ("Unexpected token 'N'").
- A labelled picture's shade (and the boxes round its parts) is laid out where the picture is going this beat
  (`_where`): a stage moved aside for a card is an animation, so a shade built after it in the same beat lay where the
  picture had been, over the card's words.
- A book's figure is always shown whole (`figure` sets `_keep_whole`; a gallery of one figure goes through `figure`):
  with the screen to itself it was cut to the screen's shape, and a tall page lost its top and bottom.
- Every chapter is on the board; the map is up only for the runs of beats that point at it
  (`compile_lecture._map_runs`, `MapLecture.map_in` / `map_away`), each run fitted to its own places. A chapter was
  put on the map as a whole: its pictures sat over the map, a `manim` beat took the whole chapter off it and every map
  operation in it was left out.
- `mapguard.is_map` ignores what follows a negation ("no maps or outlines") and the style's name ("Atlas detailed
  shaded art"): an atlas is a map only as a book of maps ("an atlas", "the atlas of India", "an atlas page").
- `legible.py`, for the pieces a model writes and the motion engine's templates:
  - **Readable text.** Each piece of text a play brings on is read against what it sits on, and taken to the nearest
    shade that reads there. It runs on every play in the motion engine and on a manim block's plays in both engines.
  - **Clearing a figure.** A manim block drawing over an earlier block's part takes the old part away, out of the
    figure's group too.
  - **Pictures keep their shape.** `picture()` and `image()` keep their proportions when stretched.
- Motion `callout`: removed. A script that still has one compiles with it left out and a note.
- `picture_flow.py`, and a diagram's `"drawn": "picture"`: a flow or cycle drawn as ONE picture by the image model
  (`genimage` FLOW_FRAME: every picture and arrow apart, on white), revealed in that picture itself: the compiler
  finds where each step and arrow is in it (picture_flow.split), and the engine (`MapLecture.picture_flow`) draws
  each on in place (draw_on) on the words that name it, through _diagram_finish's stepping. A picture whose parts
  touch is shown whole, its steps lit as they are said (stage_image's labels); only one not made is built instead.
- Pictures are drawn in the style their writer describes: `genimage.prompt_for` adds only a picture's form (a cutout
  on white, a whole scene, a picture-diagram), its shape, what the lesson needs it for and no text. The lecture
  style's words (`LOOKS`, "like a plate in a good textbook") and the motion looks' (`PICTURE_WORDS`) are gone; the
  scene writer and the Manim agent are told the style of each picture is theirs. A "child" art keeps its crayon
  drawing (the board draws it on).
- **Manim plays as Manim on the phone (faithful export).** A free-form scene (one not drawn by `pocket_lecture`) is
  exported with `PANIM_FAITHFUL=1` (`dsl/export_dsl.py`): every play recorded as Manim draws it, frame by frame
  (a baked clip), never guessed at as verbs; the clock moved as Manim's render moves it (in whole frames, so a scene
  that reads `self.renderer.time` to wait for a word waits the same in both); each play's length written so the
  players count exactly Manim's frames; a clip's parts drawn in Manim's order (by `z_index`, stably), and what was
  above the lowest part that changed taken into the clip and put back in order after it. The scene file is never
  changed: the exporter prepares a copy beside it and removes it. A moved 2D camera (`self.camera.frame`) is named
  as a blocker: the program has no 2D camera. v1's label pass (`layout_guard.py`) is gone: it
  moved text a scene placed itself. Measured on a 140 s chapter written freely (`review/agent-trial/`): 128 plays,
  every one the same number of frames as Manim's video, and the phone's frames within antialiasing of the video's;
  the one difference left is a thing added or removed between two plays, which the phone shows a frame (33 ms)
  later.
- `tools/phone_check.py <build> <Scene> <video.mp4|-> <out> <t>...`: the phone's frames (the program played by
  `dsl/interpret.py`, drawn by `exporter/reference_render.py`, the oracle the Kotlin and Swift players are held to)
  beside the Manim video's at the same frames, with how far apart each pair is and whether it is within the limit.
- **The video step's tools** (the app's Video tab, `harness_v2/README.md`): `tools/chapter_voice.py <lines.json> <dir>`
  speaks a chapter from its transcript lines (a chapter's take where the voice can, through `narrate_many`), aligns
  every word (`line_words`) and lays the lines on one track (`chapter.wav`, each followed by `beat_pad`), writing
  `timing.json` (every line and word with its time on the track); `agent/narrated.py` is all the video agent's scene
  is given (`NarratedScene`: the voice as its sound, `word`, `phrase`, `wait_until`, `wait_until_end`);
  `tools/agent_tools.py` renders the agent's scene at 30 fps (`render`), cuts frames and sheets from it (`frames`,
  `sheet`) and exports it as the phone plays it, with the web player's geometry and the phone's frames compared with
  the render's (`phone`). `render` takes a section (`from`, `to` seconds: `PANIM_RENDER_FROM`/`PANIM_RENDER_TO`, read by
  `NarratedScene`, which skips the plays before it, splits a wait across its start, stops after it and writes where the
  video starts to `.render_window`) and returns a sheet of 320x180 frames with every render; `frames` and `sheet` take
  that offset, so times stay the chapter's.
- `agent/audit.py`: what a render of the video agent's scene measures about itself (still and empty stretches, words
  off the frame or on words, the animations used and the share of fades), written as `audit.json`;
  `agent/vox_example.py`: a chapter built in free Manim (`review/agent-trial/japan_ch4.py`), given to the agent to read.
- Faithful export: a picture (ImageMobject) sits just under the shapes at its own z (`z - 0.0005`): the players drew
  it over every shape at its z, so a paper backdrop with no z covered the whole stage on the phone, and a label written
  on a picture was hidden under it.
- `agent/style_frames.py`: the default look's reference sheet for the video agent (`agent/style-vox.jpg`), six stills
  drawn here in Manim in a Vox-like manner (a map with a highlighted country and callout, an archival photo collage, a
  data figure, a highlighted document, a timeline, a flow diagram); no frames from anyone's videos. Run it to remake
  the sheet.
- `agent/kit/`: the kit, optional building blocks for the video agent's scene (`from kit import *`), in a look (`vox`,
  `blueprint`): KitScene (NarratedScene, the look's stage, camera moves made by moving the stage as the phone has no 2D
  camera, clearing and wipes), text in the right font for its script, marks, cards, documents, books, scrolls, portrait cards,
  illustrated people, icons (the engine's Iconify sets, else v1's, read only), photos treated in the look and public
  domain pictures from Wikimedia Commons, maps from Natural Earth with places by name (`pocket_lecture.place`) and
  historical borders (`historical.empire`), timelines, charts and diagrams that lay themselves out. Plain Manim objects
  and animations throughout; nothing owns the frame or the clock. `agent/kit/KIT.md` is its catalog (copied into the
  agent's workspace); `tools/kit_preview.py` renders a snippet in a look (the agent's kit_preview tool);
  `agent/kit/gallery.py <dir>` previews every kind of piece in both looks side by side (`review/kit-gallery/`).
  Fonts are chosen for keeping their word spaces: Hind (Latin and Devanagari), Oswald, Playfair Display at normal
  weight, Kalam (handwriting with Devanagari), IBM Plex Mono, Architects Daughter.
- `agent/narrated.py`: a section render (`PANIM_RENDER_TO` set) is drawn silent and stops at its end, holds included
  (a `wait_until_end()` stops there too), so its video is the section's length.
- `agent/kit_example.py`: 70 seconds of a chapter (Japan, lines 0-13 of the Hindi narration it was made for) built with
  the kit, copied into the agent's workspace as `reference/kit_example.py`: an example of how such a chapter moves.
- `PACES["teacher"]` (`PANIM_PACE=teacher`, the Voice step's default): the voice 10% slower, its pitch kept (the
  voice modules' ffmpeg `atempo`; its lines cached apart from the 1.0 ones), the pauses the voice left between lines
  kept but never under 0.4 s, and 1.4 s between paragraphs. The other paces are as they were.
- The word being said, and music, copied from the motion engine (`Lecture.beat` wraps the line, now `_beat`): with a
  voice, the caption is laid out a line at a time with where each word sits measured (`_word_caption`), and the word
  being said is underlined as it is said, the underline moving as fades in the holds (`_kara_plan`, `_kara_moves`),
  which the exporter writes as verbs, so the phone and the web player show it (`PANIM_KARAOKE=0` turns it off); and a
  quiet music bed under each line (`music.py`, a calm mood: `MUSIC_MOOD`), from where its voice starts to the end of
  its pause, ducked under its words (`PANIM_MUSIC=off`, the Scenes tab's music box, turns it off). The underline's
  moves make no sound effect. The motion engine has its own of both: `WORD_CAPTION` and `MUSIC_BED` are off there.
- An anchor may be a word's number in its line (`"on": "w7"`, the line split at spaces, `w0` its first): the
  compiler makes it the line's own words from that word, as few as `pocket_lecture.said_at` hears there first
  (`compile_lecture._word_phrase`), then checks it as any other anchor. The Scenes tab's word timing call writes them
  on the current engine (voice first, README "Voice first on the current engine"). What the engine draws is unchanged.
- Strict chapters (the chapter's `"strict": true`, written for a chapter built as one piece; BEAT_SCRIPT.md §2):
  `Lecture.strict_beats` makes `_said` time a thing by its anchor only (`spoken_as`, which the compiler then fills
  with every anchor of the line), `_pointers` point at nothing, a labelled picture's parts get no light because they
  are named, and a label with no anchor comes on as its line begins; the compiler adds no `auto_visuals`, finds no
  paragraphs (`marked_paragraphs`), starts a map run on the beat that points at the map and accepts `unstage`. New
  operations, the script's own pointing: `point` (`Lecture.point`: a named thing on screen pulses once) and `shade`
  (`Lecture.shade_part`: a labelled picture's part lit, the rest shaded). The camera is off: `zoom` is left out with a
  note, and `spotlight` (`focus`) no longer moves the stage in on a big diagram (`PUSH_IN_FROM` gone).
- A diagram is held to what reads (`_fix_diagram`): at most 9 nodes (any kind; a flow and a hierarchy took 16 and 20,
  and a chapter's whole argument came out as one unreadable tree), and words cut where they would run over their
  boxes (a label past 6 words, a node's text past 10, an item past 5, an arrow's label past 4; items at most 4).
- A beat's `"screen": "join"` (`Lecture.screen_join`, `_join`): its new main picture joins the one up from an earlier
  line, which slides into its share (`_move_stage`) while the new one comes on in the other (`_pair_boxes`).
- Two pictures sharing the stage (joined, or two in one line) are marked `is_pair`: `_aside` puts nothing beside them
  (a card beside a picture used to take the second picture for an old card, fade it out and land over the first);
  the card takes the stage instead.
- The line-start clear of strays leaves what the line itself takes away by its parts (`_clear_strays`): a picture slid
  aside sits on the screen in the group its move made, and was cleared as the line began, its shade coming back for
  the line's own fade.
- Timelines build themselves (`big_timeline(enter=)`, `_timeline_in`, `_timeline_event`): `draw` draws the title
  and track in and pops each event on (its own words when it has an `on`), `travel` runs a marker to each; `whole`
  (and no `enter`, as the motion engine's styled timelines call it) is the old still one. Its events are named parts
  the engine never pulses by itself (`name_part(auto=False)`): only `point` does.
- A new stage picture waits at most `STAGE_WAIT` (1.2 s, or a quarter of the line) for its words, else comes on as
  the line begins (`_on_words`, `panim_stage`): a diagram whose only word said was the line's last left the screen
  empty for the whole line.
- Two main pictures of one line share the stage where each is seen best (`_pair_boxes`): side by side or one over
  the other, split where the smaller is drawn largest; the compiler moves a third to a later line
  (`MAIN_AT_ONCE`).
- At most two main pictures at once (`compile_lecture._one_on_the_stage`, BEAT_SCRIPT.md §2 `strict`): a third in
  one line moved to a later free line; in a strict chapter pointing at what is not up left out. A labelled
  picture's labels queued for a line are not drawn when another picture has taken the stage in that line
  (`_with_looks`: they were left on top of what replaced it). The board's heading (`stem.board_title`) is not drawn
  when it is the chapter's own name (the tag in the corner says it), and never over that tag (`_strip`).
- A picture's labels as the script says (current engine): `stage_image(hold=, notes=)` holds labels back
  (`_picture_view` queues none for them) and writes a short note under a label's name (`_label_tag`). A labelled
  picture never moves (`move` is for a picture without labels): a moving picture was marked `still`, which turned its
  lights off, and a full-screen scene did not even move.
  New operations: `label` (`Lecture.label`: a held label brought on), `unlabel` (`Lecture.unlabel`: a label faded, the
  picture kept), `unshade` (`Lecture.unshade`) and `unfocus` (`Lecture.unfocus`: a diagram's veils lifted); `shade`
  takes `hold` (`held_light`: `_looks_away` and `_lifts` leave the light on until an `unshade`).
- `compile_lecture.anchors` merges a beat's `_spoken_as` with what it had: the checks run twice, and the second run saw
  the parts' anchors already folded into their names and wrote the table without them.
- The music bed is continuous (both engines): `Lecture._bed_gap` fills from where the last line's piece ended to where
  the next begins (a map coming in, a picture changing, a chapter card) with the bed at its level between words,
  placed back in time (`add_sound` with a negative offset, which the exporter records too), and `tear_down` fills to
  the video's end (the outro, the credits). Before, the music stopped in every animation between lines.
