# v2's lecture engine

A copy of v1's lecture engine (`harness/lecture/`, at commit b94dd84), so v2 renders with its own engine and never
reaches into v1's folders. v2 uses it to render maps (`compile_lecture.py` turns a map script into a scene on
`pocket_lecture.py`'s map engine; `app/lib/maps.ts`). Changes made here are v2's own; v1's copy is left as it is.

Its data is downloaded on first use into `data/` and `.cache/` here (historical borders, geocoding), and Natural
Earth by cartopy into its own shared folder, exactly as v1's engine does.

## v2's own changes

- `free_check.image(name, height, width, labels)`: in a Manim block, a picture the v2 Manim agent made, by its name,
  read from the JSON registry `PANIM_BLOCK_IMAGES` names (name to file); a labelled stand-in frame when it is missing.
