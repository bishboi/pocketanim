# harness_v2

- The beat script (the JSON a lecture video is rendered from) is documented in `engine/BEAT_SCRIPT.md`. Any change to
  what the compiler (`engine/compile_lecture.py`) or the engine (`engine/pocket_lecture.py`) accepts -- an operation,
  an argument, a limit, a default, what is mended or refused -- updates that file in the same commit, with an example
  that compiles. `npm run check` (in `app/`) fails when an operation or a script, chapter or beat field the compiler
  reads is missing from it.
- The scene writer's instructions are v1's word for word (`app/lib/prompts/v1-lecture.ts`, from
  `scripts/sync-v1-lecture.py`); v2's additions go in their own parts in `app/lib/prompts/scenes.ts`.
- v1 (`harness/`) is not modified; v2's engine is its own copy (`engine/ENGINE.md` lists v2's changes).
- The motion engine (beta) is documented in `engine/MOTION_ENGINE.md`; any change to what `engine/compile_motion.py` or
  `engine/motion*.py` accepts updates that file in the same commit (`npm run check` fails when a template, an argument
  or a script field it reads is missing). It never changes the current engine's files or what they make: a script is
  drawn by it only with `"engine": "motion"`: in the Lab, or for a run whose Scenes tab's engine is set to motion.
- The default flow is the Scenes tab on the motion engine (beta, `engine/MOTION_ENGINE.md`), then Voice: a lecture's
  scenes start on it unless `V2_SCENES_ENGINE=current`. On it each chapter is spoken and aligned first and its scenes
  written to the voice's times ("voice first", MOTION_ENGINE.md §1). The current engine is voice first too. On both, a
  chapter is built as one piece: a director call plans its elements and scenes, then each few scenes are choreographed
  in a call of their own with their artifacts' manuals, and code lowers both into the beats (README "A chapter as one
  piece", `app/lib/director.ts`). The Video tab (README "The video step": the video agent in free
  Manim, `app/lib/video-agent.ts`, checked against the phone by `engine/tools/agent_tools.py phone`) is set aside behind
  "Video agent…", not removed.
- The kit (`engine/agent/kit/`) is the video agent's optional library. A change to what it offers (a piece, an
  argument, a look) updates `engine/agent/kit/KIT.md` in the same commit (the agent reads only that), and
  `engine/agent/kit/gallery.py` still renders every snippet in both looks.
