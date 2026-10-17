# v2's lecture engine

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
