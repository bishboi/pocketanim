# harness_v2

- The beat script (the JSON a lecture video is rendered from) is documented in `engine/BEAT_SCRIPT.md`. Any change to
  what the compiler (`engine/compile_lecture.py`) or the engine (`engine/pocket_lecture.py`) accepts -- an operation,
  an argument, a limit, a default, what is mended or refused -- updates that file in the same commit, with an example
  that compiles. `npm run check` (in `app/`) fails when an operation or a script, chapter or beat field the compiler
  reads is missing from it.
- The scene writer's instructions are v1's word for word (`app/lib/prompts/v1-lecture.ts`, from
  `scripts/sync-v1-lecture.py`); v2's additions go in their own parts in `app/lib/prompts/scenes.ts`.
- v1 (`harness/`) is not modified; v2's engine is its own copy (`engine/ENGINE.md` lists v2's changes).
- The beta engine (`engine/beta_engine.py`, `engine/compile_beta.py`: slides of boxes, animations on their words) is
  documented in `engine/BETA_ENGINE.md`; a change to its layouts, elements, presets or checks updates that file in
  the same commit, and the Lab's examples (`app/lib/lab-presets.ts`, all on the beta engine) must compile with no warnings and cover every entrance, emphasis, exit, layout and kind of element (`npm run check`).
