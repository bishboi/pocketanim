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
- `tools/export_scene.py`, `tools/scene_ir.py`, `tools/layout_guard.py`: copies of v1's `harness/scripts/` ones, with this
  engine on the path instead of v1's (the repo's `dsl/` and `exporter/` are used as they are): a compiled scene recorded
  into the program the phone plays, and expanded into the geometry v1's web player draws.
- `espeak_tts.py`: an offline voice (`PANIM_TTS=espeak`, espeak-ng), registered in `tts.py`: free and robotic, for
  trying the voice step without a key, and for the checks.
- `local_align.estimate`: when Whisper cannot be loaded, a line's words spread over its spoken stretches by length,
  each marked `"est"`; `pocket_lecture.line_words` uses an estimate but never keeps it, so Whisper times the line
  once it can.
- `tools/prespeak.py`, `tools/narration.py`: copies of v1's `harness/scripts/` ones on this engine (the exporter's
  narration mix needs `narration.py`). `tools/voice_scene.py`: a spoken scene's lines (audio, length, cost, word
  times and their source), the beats to time with `align_cues`'s prompt, and the timing model's answer checked and
  written into the scene as `cues=` (the app makes the timing call itself, so it is recorded).
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
- Motion `callout`: smaller (22 pt, two lines), no wider than the room beside the picture, placed where it covers
  least, and replacing the last callout.
