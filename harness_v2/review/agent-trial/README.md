# Agent trial: a chapter in raw Manim

`japan_ch4.py` is chapter 4 of the latest run (East Asia course, script lines 117–138), written by hand in plain Manim in
a Vox-like style, with no primitives and no beat script. It tests whether a free-form scene can stream on the phone.

- Render: `manim -qm japan_ch4.py JapanChapter4` (writes to `media/`, which git ignores).
- Phone export: `python ../../engine/tools/export_scene.py` on a **copy** of the file. The exporter writes a
  layout_guard preamble into the file it exports, and a `from __future__` import then breaks the file.
- Result: tier 1 (vector program), no blockers, a 4.3 MB program against a 27 MB 720p MP4. `contact_sheet.jpg` shows
  one frame every 10 s.

What the phone IR got wrong:

1. Tag words land off their cards. layout_guard moves text that isn't on stage yet; a tag's text and its card are
   added separately, so only the text moves.
2. Objects stay on screen after FadeOut. The case is a play on a temporary `VGroup` that bakes a clip (Indicate, then
   Wiggle) followed by `FadeOut` of the group. The members declared again after the baked clip are never hidden.
