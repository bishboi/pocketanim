# Harness v2

A new harness, built one step at a time. It shares the deterministic engines with v1 (the PDF reader, the lecture
engine, maps, the compiler, the exporter, the Manim player and editor) and changes only how the harness works:

- **One step at a time.** Each step is added only when the one before it is right. Today there is one step: the
  **transcript**.
- **Everything visible.** Every model call is recorded whole: the prompt as the named parts it was built from (the
  rules, the book's text, the lectures before...), the tool it had to call, its output, what code checked in it,
  its tokens, time and cost. Every part of the book a step works from is highlighted on the PDF.
- **Code checks, models write.** What code can check or mend, it does, and says so (a check: passed, mended,
  failed, noted); a model is asked again only when there is nothing usable to mend.

v1 (`harness/`) is left as it is; v2 shares nothing with it at run time. v2 has its own copy of the lecture engine in
`harness_v2/engine/` (from v1's `harness/lecture/`, see `engine/ENGINE.md`), which draws its maps; changes to it are
v2's own.

The JSON each lecture's video is rendered from (the beat script: chapters, beats, every operation with its arguments and what it does, what the compiler mends or refuses) is documented in [engine/BEAT_SCRIPT.md](engine/BEAT_SCRIPT.md).

## The video step (the default)

Once the transcript is written, each chapter becomes a video in three steps, on the **Video** tab (`app/lib/video.ts`,
`app/lib/video-agent.ts`, `app/components/video-panel.tsx`):

| Step | What | Calls |
| --- | --- | --- |
| 1. Voice | The chapter's lines, exactly as the transcript has them (its title card's line, then each beat's sentences), are spoken with the chosen voice (Gemini or ElevenLabs say the chapter whole, in one take; Chirp and espeak line by line), into the shared line cache (`engine/tools/chapter_voice.py`). No scenes are needed: the voice comes first. | the voice, per line spoken |
| 2. Alignment | Every word's time: the voice's own (ElevenLabs), else Whisper here, else an estimate (said so). The lines are laid on one track (`chapter.wav`), each with the pause the voice left after it, and every line and word gets its time on that track (`timing.json`). | none |
| 3. The video agent | The **video agent** (the Video agent role, `V2_VIDEO_MODEL`) builds the chapter's whole video in free Manim, as a coding agent builds a program: nothing is given to it but the narration (every line and word with its time, and the voice), a **screenshot of the look** wanted (the default is a Vox-like chapter, `engine/agent/style-vox.jpg`; choose another on the tab, with words about it), and a workspace. No primitives, templates or layouts. It works in turns with tools: write, edit, read and list its files; a shell in its workspace (`V2_VIDEO_AGENT_SHELL=off` turns it off); **render** (Manim at 30 fps); **look** (frames of the render at chosen times, or a sheet of them, shown to it); **make_image** (the image model draws into `assets/`, at most `V2_VIDEO_AGENT_IMAGES`, 12); **phone_check**; and **finish**. Its scene subclasses `NarratedScene` (`engine/agent/narrated.py`), which only adds the voice and tells it the time (`self.word(n, "Japan")`, `self.wait_until(t)`). At most `V2_VIDEO_AGENT_TURNS` (60) turns, or the tab's own number. | 1 per turn (+1 per picture) |

**The kit** (optional): `from kit import *` (`engine/agent/kit/`, catalog `KIT.md` in the workspace) gives the agent
building blocks drawn in a look, **vox** (paper, collage, marker, cutout photos) or **blueprint** (a drafting grid,
outlines, mono type, duotone photos): `KitScene` (the narration's clock, a moving camera, the look's stage, camera moves,
clearing the stage and wipes), headlines, labels and quotes in the right font for Hindi, Chinese or Latin, marks
(highlight, circle, underline, arrow, callout, stamp, spotlight, dimensions), cards, documents with seals, newspaper
clippings, books, scrolls that unroll, portrait cards, illustrated people, icons, photos treated in the look and
public-domain pictures from Wikimedia Commons, maps from real data (places by name, routes, states in a given year),
timelines with events and lifespans, charts (bars, donut, units, line, versus) and diagrams that lay themselves out
(flow, tree, cycle, hub, chain, network, pyramid), each with its own entrance, exit and emphasis in the look. Every
piece is a plain Manim mobject and every helper a plain animation: the agent may use any of it, none of it, or take
it apart. Its **kit_preview** tool renders a snippet in a look and shows the agent the frame (and a sheet of frames
when it moves) before it commits to it. `engine/agent/kit/gallery.py` renders every kind of piece in both looks
(`review/kit-gallery/`).

**Every render also says what it measured** (`engine/agent/audit.py`, installed before the scene runs): the
animations used, stretches with nothing moving or nothing on screen, words outside the frame or on other words. It is
information for the agent, not a rule. Its workspace has a chapter built in this setup to look at if it wants
(`reference/vox_example.py`). It reasons at its own effort (**Agent reasoning** on the tab: max, xhigh, high, medium,
low or off; else `V2_VIDEO_AGENT_EFFORT` or `PANIM_MANIM_REASONING_EFFORT`; high by default, not the run's effort; a
level the model does not take is asked again at high, and the rest of the build runs at high), with room for a whole scene in one reply (`V2_VIDEO_AGENT_MAX_TOKENS`, 32,000). Its model is
`V2_VIDEO_MODEL` (else `V2_MANIM_MODEL`, else `OPENROUTER_MODEL`). An OpenAI model (`openai/...`) is called on
**OpenAI's own Responses API** when `OPENAI_API_KEY` is set (`app/lib/openai-responses.ts`), not through OpenRouter:
its reasoning comes back encrypted and is sent back with every turn (nothing is stored at OpenAI), so it keeps its
thread of thought through the whole build, and summaries of it stream to the page; the call says `openai` as its
provider. Any other model, or no key, goes through OpenRouter as before.

**Two modes** (the Video tab's "Agent tools", `V2_VIDEO_AGENT_MODE`). **lean** (the default): the agent only writes
its scene. Its tools are `write_scene` (the whole `scene.py`), `edit_scene` (several replacements in one call), `look`
(frames at given times, as one picture) and `finish`; every write or edit renders the whole chapter (draft) and checks it
on the phone in the same turn, so it sees the sheet, the measurements and the phone's verdict (or the error) without a
turn of its own. No shell, no other files, no image model; the kit's whole catalog (`KIT.md`) is in its instructions
(fixed, so cached); a scene from an earlier build is put in its first message; finishing renders the video once more at
full size. At most 20 turns unless set. **agent**: every tool below, at most 60 turns.

**Cost and speed.** The conversation is only ever added to, never edited, so the provider's prompt cache keeps
everything before the last turn. Every turn of a build goes to the same cache: on OpenAI's API one `prompt_cache_key`
for the chapter; on OpenRouter the build is pinned to one provider (each provider has its own cache, and a turn sent to
another pays for the whole conversation again): `V2_VIDEO_AGENT_PROVIDER`, a comma list of OpenRouter provider names,
by default the model's maker for OpenAI's and Anthropic's models; Anthropic's models get cache marks (on the
instructions and the latest message), which they need to cache at all. The first message says what is installed (the
fonts, the Python, the Natural Earth files, from `agent_tools.py facts`), so no turns go on looking. Pictures are sent once: a turn's pictures ride on one message with the next request
and are a one-line note in every request after (it looks again if it needs to); frames are 640 px wide
(`V2_VIDEO_AGENT_FRAME_WIDTH`), and `look` takes `detail: "low"` for a cheap glance. Frames `look` asks for come as one picture, each stamped with its time. Once a request passes
`V2_VIDEO_AGENT_COMPACT_TOKENS` (150,000; with the cache a long build is still cheap, and condensing early costs turns of
re-reading) the conversation is condensed, with no model call, to the instructions, the
chapter and a summary of what was done (every tool call and its outcome, what it last said, its files, the last render
and phone check); its files are as they were. Every **render** shows its sheet of frames (and, with `look: [times]`,
frames at those times in the same turn); a whole render also runs the phone check (`check: false` skips it). **Work
ahead**: once a turn has changed what a render sees (its Python files, its assets), a whole draft is rendered
(`renders/ahead-a.mp4` or `-b`, never over the render in use) and checked on the phone in the background while the model
thinks, so the render and check it asks for next are often ready; only while it works on the whole chapter (its last
render a whole draft, or none yet), stopped by anything else run first (`V2_VIDEO_AGENT_AHEAD=off`: none). `finish`
needs the workspace unchanged since the passing check. The agent is told a turn may hold several tool calls (run in
order: edits, then a render). `render` with `from`/`to` (seconds) draws only that stretch (the plays before it run
without drawing a frame; `NarratedScene` stops after it), for a quick look at one part; the phone check needs a whole
render. The reasoning level is chosen turn by turn: the level set, but low after a turn that only read or listed files
(a turn after writing or editing often writes the next big piece, so it thinks at the level set;
`V2_VIDEO_AGENT_ADAPTIVE_EFFORT=off`: always the level set). A shell command's long output keeps its first and last
4,000 characters (the middle is cut, so a file read with `cat` shows its top); the agent is told to read files with
`read_file`. The system prompt carries a short summary of the kit (KitScene, camera moves, entrances, the pieces), and
`reference/kit_example.py` (`engine/agent/kit_example.py`: 70 seconds of a chapter built with the kit, camera pans and
pushes, wipes, word-timed pins, counters, marks drawn on, a diagram built as it is named) shows how a chapter moves. The log has a `compact` line each time it condenses.

**The one hard rule is the phone.** The chapter is shipped as the program the phone plays, not as an MP4, and it must
play exactly as Manim drew it: `phone_check` exports the scene (faithfully: every play recorded as Manim draws it,
`engine/ENGINE.md`), draws the phone's frames with the reference renderer the Kotlin and Swift players are held to, and
compares them with the render's; **finish** is refused until it passes on the scene as it is. **finish** also asks the
agent to look at the video as a viewer would and list what is still wrong (`open_issues`); while three or more turns
remain, a list that is not empty sends it back to fix them (its own judgement, not a check of ours), and what it
leaves open on its last turns is kept in its summary. The page then plays the
chapter as the phone does (v1's web player, with the narration as its clock), beside the Manim render it was checked
against, every line and word of the narration with its time, and what the agent did, in five views
(`app/components/agent-log.tsx`): **What it did** (the outcome, its summary in its own words, and the counts: time,
turns, model and tool time, cost, tokens, files and versions, shell commands, renders, looks, pictures, phone checks);
**Steps** (the turn being written now, live as it streams: its reasoning, its words, the tool it is calling or running;
then each turn with what the model took, said and reasoned, and each tool call with its answer and how long it took);
**Commands** (everything it ran, filterable: shell commands with exit codes and output, renders and looks, phone
checks, pictures, file writes); **Files** (its workspace, each file readable, every version of every file it wrote
under `history/`, and what changed between versions); **Conversation** (the whole conversation as sent and answered,
from `agent-log.jsonl` in its workspace: the instructions, the chapter, every reply with its reasoning and tool calls
in full, every tool answer, every picture shown; a build starts a new log and keeps the one before). **Phone library (zip)** packs the chapter for the
phone (`tools/build_library.py`: the program, its clips, pictures and glyphs, and the narration as Opus), opened by the
phone's own code first when the player is built. **Speak and build every chapter** does a lecture's chapters in order;
a note for the agent goes with a build. **Build again** lets the agent improve the scene it wrote before; **Reset and
rebuild** throws the chapter's video away (everything the agent wrote, its renders, export, log and result) and builds it
from scratch, keeping the voice (`lines.json`, `chapter.wav`, `timing.json`); **Reset** throws away the voice too.
**Stop** stops at once: the model's answer being written is cut off, and a render, export, voice or command running
is killed with everything it started (`app/lib/abort.ts`: a build runs in an abort scope that its model calls and
processes listen to); the chapter is marked stopped and can be built again. A chapter left marked as running by a
server restart is marked stopped by Stop too.
Everything is under `.data/runs/<run>/scenes/video/L<n>/C<c>/`.

**The video agent is set aside**: the default flow is the **Scenes** tab on the **motion engine (beta)** (a lecture's
scenes start on it unless `V2_SCENES_ENGINE=current`; the tab switches engines), then **Voice**, with the **Lab** beside
them. The **Video** tab (this section) is hidden until **Video agent…** is pressed, and works as before.

The **motion engine (beta)** draws the same beat scripts the way a modern explainer does: six looks (paper, newsroom, chalk, data, studio, sketch), templates that animate themselves part by part on the words that name them (counters, charts, grids of units, cards, stamps, data cards, chains, lists, versus, donuts, highlighted documents, polaroids, headlines), the timeline in five styles, transitions, idle motion and sound. It is tried in the **Lab** (its own presets, and any lecture's chapter in any look), and a run can be built on it from the **Scenes** tab (its Engine row: the scene writer is told of the templates, and compiles, renders and the Voice tab use it), and documented in [engine/MOTION_ENGINE.md](engine/MOTION_ENGINE.md); `scripts/motion-rerun.mjs` compiles the lectures already built on it, beside what they made.

## The transcript step

| Step | What | Calls |
| --- | --- | --- |
| 1. Read the book | Datalab's convert API with `output_format=json`: every block of every page with its id (`/page/3/Text/7`), type, HTML and bounding box. That JSON is the book from here on; nothing is rewritten into markdown. | none |
| 2. Figures | Each picture block described from its image, so the writer knows what it shows | 1 per figure |
| 3. Write lectures (chapters, beats) | Each lecture is written **as its script, in one call**, in order (`write_lecture`; `app/lib/prompts/build.ts`). There is no planner: the writer is given the whole book as Datalab's JSON (id, block_type, html, figure description; no boxes) with each block marked taught (in which lecture), skipped or NOT TAUGHT, every earlier lecture whole, and the lecture length, and writes the next lecture from where the book is not taught yet, ending where a topic is complete. It answers with the lecture's title, its **chapters** (title, the line said on its title card, map or board, and its **content**: the ids of the blocks it teaches from; chapters, of this lecture or another, may share content) and each chapter's **beats** (1-2 sentences said, 3 at most; what is on screen; the **figures** shown: a figure may be on several beats, a beat may show two), and done when the book is all taught. The transcript is the beats' words. Code drops unknown ids, adds a beat's figures to its chapter's content, removes a sentence said before, drops empty beats and chapters, and makes a chapter showing a Map figure a map chapter. The lectures go on until every block is taught or skipped (at most `V2_MAX_LECTURES`, 40). The writer reasons long (**Writer effort**, high by default). | 1 per lecture |

Then, apart from the transcript and at any time once the book is read:

| Step | What | Calls |
| --- | --- | --- |
| Figure triage | A classification, so a **decision model** decides it by default: Jev (`typesafe/jev-1.14`) on OpenRouter's Decisions API (`app/lib/decisions.ts`), one Choice question per figure over the ways ticked on the page (Manim, Map, Exact redraw, Styled redraw, SVG drawing, Photo search, Book's picture, Leave out: `app/lib/triage-kinds.ts`), with the figure's picture, block, caption, description, the text around it and its lecture as state. It answers with the way, a probability for each and its confidence, and no words; under the threshold (60% by default) a figure is marked **unsure**. When Jev picks **Map** but the surer redraw (Exact or Styled) is under 20 points behind it (`V2_MAP_REDRAW_MARGIN`, 0.2), the figure is redrawn instead, and its check says so. A **chat model** that reads images can decide instead (a whole round, one figure, or **Ask the chat model about the unsure**), with an instruction for whoever builds the figure and its reason. Code checks the way is one offered. **Triage figures** does those not done yet; **Reset and rerun all** forgets every decision; each figure can be rerun alone or set by hand. | 1 per figure |
| Generation (redraws) | **Next: generate the redraws →** opens the Generate tab: every figure triaged **Exact** or **Styled redraw** (or set so by hand) is redrawn by the image model (`V2_IMAGE_MODEL`, default `google/gemini-2.5-flash-image`) from the book's figure, sent as the reference image (`app/lib/prompts/redraw.ts`). The prompt began as v1's (`genimage.py` `redraw_prompt`) and differs in two ways: **no text in the image** (every label, word and number left out, its spot left clear for labels put on later), and **gentle words** (an original illustration based on a sketch, never "an exact copy" or "looks just like it", which moderation such as Azure's blocks). When a model's moderation still blocks it, it is asked again in gentler words with no book text, then with no reference image, from what the figure shows; the card says which. Styled uses the same prompt for now (there are no lecture styles yet). Asked by chat completions with image output, else OpenRouter's Images API. Each figure shows the book's figure, the image made, and the prompt by its parts (and whole, as sent). **Generate**, **Reset and regenerate all**, **Regenerate** one, **Stop**. | 1 per figure (up to 3 when blocked) |
| Generation (SVG drawings) | On the same Generate tab, every figure triaged **SVG drawing** (or set so by hand) is drawn by the **SVG model** (`V2_SVG_MODEL`, a model that reads images; default `anthropic/claude-sonnet-4.5`): it is shown the book's figure and writes the SVG from it **in the same call**, no other model describing it first. The prompt is v1's SVG prompt and rules (`figures.ts` `SVG_PROMPT`/`SVG_RULES` before 506360a, `app/lib/prompts/svg.ts`) without its PHOTO/MANIM ways out: colours by name (INK, ROSE, RIVER…), parts as `<g id>`, labels as `<text>`, animation only when it teaches. Code checks it against those rules (viewBox, elements, colour names, parts, size) and sends what breaks them back to the same model once. The page shows it on v1's default board (atlas colours), with its parts, any rule it still breaks, its code, and the prompt by its parts. Nothing in an SVG can run: scripts, handlers and outside links are stripped, and it is served under a sandboxing CSP. | 1 per figure (2 when it breaks the rules) |
| Generation (Manim) | On the same Generate tab, every figure triaged **Manim** (or set so by hand) is written in Manim by the **Manim model** (`V2_MANIM_MODEL`, a model that reads images; default `anthropic/claude-sonnet-4.5`): it is shown the book's figure and writes the body of `construct()` **in the same call**, with v1's Manim rules (`lecture.ts` `MANIM_RULES`, `manimcoder.ts`: "the book's figure, to rebuild exactly"; `app/lib/prompts/manim.ts`) for one figure in one scene. Code checks it first (no imports, file/OS/process access, exec/eval, dunder names, while loops, classes, camera surgery), then renders it with the repo's Manim (`.venv` from `harness/scripts/setup-python.sh`, or `V2_PYTHON`) on v1's default board, in its own process and folder with a time limit (`V2_MANIM_TIMEOUT_SECONDS`, 120): its last frame (PNG) and its video (MP4, 480p). A refused or failed render goes back to the same model once, with the error. The card shows the frame, the video, the code and the prompt by its parts. | 1 per figure (2 when it fails) |
| Generation (maps) | Every figure triaged **Map** (or set so by hand) is written by the **map model** (`V2_MAP_MODEL`, a model that reads images; default `anthropic/claude-sonnet-4.5`): it is shown the book's map and writes it **in the same call** as a short map script: its region and 2-6 beats, each a line said and 1-4 of v1's map operations (marker, river, state, arrow, empire, relief, path, journey, graticule, dim; `app/lib/prompts/map.ts`). **v2's own lecture engine** (`harness_v2/engine`) checks and compiles it, looking every place up by name on real map data, and it is rendered silent like a Manim figure: its last frame and its video. A map the engine cannot draw (every operation left out) goes back to the same model once, with the engine's notes. Map operations are data: nothing the model writes is run. | 1 per figure (2 when refused) |
| Script (chapters and beats) | The **Script** tab shows what the writer wrote, nothing is built there: all lectures in a table, then one lecture at a time in four views: **Chapters and beats** (an outline beside the chapters; click a chapter's head to see the content it teaches from, blocks and figures, with the other chapters sharing each, lit up in the PDF; each beat with its numbered sentences, what is on screen and its figures, each with the other beats it is on), **Content** (every block the lecture teaches with the chapters using it, every figure with its beats), **Prompt and answer** (the call: its prompt as parts, the answer before code mended it) and **Checks**. Old runs' scripts (made by the former Script step) are still read. | none |
| Scenes (visuals per beat), look and render | The **Scenes** tab gives each beat of a script its visuals as the lecture engine's operations (`V2_SCENES_MODEL`; `app/lib/prompts/scenes.ts`, `app/lib/scenes.ts`): one call a chapter, **each chapter standing alone** (written, compiled and mended by itself, with its own map region, `V2_SCENES_CHAPTERS_PARALLEL` 4 chapters of a lecture at once; its writer is given the other chapters' words but never their visuals, so what it is told does not depend on which chapter finished first), told the beats' sentences (fixed: the narration stays the transcript), the script's note of what is on screen, the beat's figure and the look. The instructions are **v1's, word for word** (`harness/app/lib/lecture.ts` lecturePrompt with its free-form drawing and Manim rules; copied into `app/lib/prompts/v1-lecture.ts` by `scripts/sync-v1-lecture.py`, and `npm run check` fails when the copy is not v1's text), in v1's order, with v1's subject guidance (the engine's `genre.py`, the run's subject or the lecture's words); only how the answer is given is v2's own, since the narration is fixed: each beat's `do`, and as in v1's beat script its `paragraph`, `pause` and `about`, and the chapter's region and the lecture's `emblem`, all passed to the compiler. The **visual kinds switched off** (`app/lib/visual-kinds.ts`: map, book figures, AI illustrations, AI detailed diagrams, gallery, diagrams, timeline, Manim, equations, molecules, definitions, comparisons, questions, stats and bars, worked solutions, quotes and step boxes) are named as such. Code takes out any op or picture of a kind switched off (also pictures on diagram nodes, timeline events, markers) and says so. A beat can have its own kinds. The **look** (`app/lib/styles.ts`, v1's templates and art styles: Atlas, Parchment, Lab, Cosmos, Vox, Cardboard, Whiteboard, Blueprint, Chalkboard; Clean, Detailed, Blueprint, Chalk, Sketch, Neon, Watercolour art) is picked with miniatures; scenes compile and render in it, and the Generate tab's **Styled** redraws are drawn in it (both redraws stand on its board colour). After each chapter is written the engine (`engine/compile_lecture.py`, or `compile_motion.py` on the motion engine) checks and compiles that chapter by itself (the lecture's compile is its chapters' put together), making its AI pictures (the run's image model; a stand-in picture with no key; their cost is a call in Costs); its errors and notes land on the beats they name, and the chapter's refused beats go back to the model once with what it said ("Mend refused" asks again). Build the next lecture, one, all (in parallel, `V2_SCENES_PARALLEL` 3, or one at a time), a chapter or a beat again (with a note for the model); change a beat's operations by hand as JSON. **Render** (silent, `V2_RENDER_PARALLEL` 2) and play **as v1's web player plays**: not a video but the program the phone plays, recorded by the exporter (`engine/tools/export_scene.py`, v2's copy of v1's, on v2's engine; the repo's `dsl/` and `exporter/` read as they are) and expanded into the geometry the browser draws on a canvas (`engine/tools/scene_ir.py`, `app/components/player.tsx` and `app/lib/draw.ts`, v1's player: play, scrub, speed, full screen). A beat (its chapter recorded up to it, played from the beat, with what the engine's on-screen check found) or a chapter (the whole of it, and a frame for each beat that plays that beat), in the run's look or any other; the Manim agent's previews play the same way. **Reset** a lecture's scenes or one chapter's (visuals, agent work and pictures, compile, renders; a beat's own kinds are kept). Renders are under `.data/runs/<run>/scenes/`. Scenes, look and kinds travel in the export. | 1 per chapter (+1 when beats are refused) |
| Voice first on the current engine | (With the director off; with it on, the choreography times the chapter: the next row.) On the current engine too, each chapter is **spoken and its words aligned before its scenes are written** (the Scenes tab's **voice first** box, on by default; `V2_SCENES_VOICE_FIRST=0` turns it off on both engines). The scene writer is not changed: it writes each beat's `do` as before. Then **a call of its own times every picture to the words** (`app/lib/prompts/word-timing.ts`, `timeWords` in `app/lib/scenes.ts`; the Timing role's model, `V2_TIMING_MODEL`, or the Voice tab's timing model): it is shown each beat's line as the voice says it (every word by number with the second it is said, the beat's length and the quiet after it) and every thing the beat puts on the screen: each operation (not those that act as the line begins: clear, emphasis, zoom...) and each part inside one (a node, a label, an event, a point, a step), with the writer's own words for it as a hint. It answers each thing's word: the first word that names it, never a small word before it. Code checks the answer (a word inside its line; a part never before the picture it is in; a part not answered on its picture's word) and writes it as the thing's `"on": "w<k>"` (`"start"` for the first word; a part given as a string becomes `{"name", "on"}`), which the compiler makes the line's own words from that word, as few as are heard there first ([engine/BEAT_SCRIPT.md](engine/BEAT_SCRIPT.md) "Anchors"), so the engine brings each thing on as its word is said. A chapter's render in the Scenes tab plays with its voice. The Voice tab's timing call still gives each animation its length, starting it on these words. Each chapter's beats written (built, or mended) are timed again. | 1 timing call per chapter written (+ the voice, per line spoken) |
| A chapter as one piece (director and choreography) | The default on both engines (the Scenes tab's **director** box; `V2_SCENES_DIRECTOR=0` turns it off): a chapter is built as one video, in two kinds of call (`app/lib/director.ts`, `app/lib/prompts/director.ts`). (1) **The director** (the Scenes model, with the scene writer's own instructions: v1's on the current engine, the templates on the motion engine; only the parts on anchors and timing taken out) writes the **chapter's plan** (`write_plan`): its **elements**, everything the chapter shows once each (an id, a role, and one operation of the engine with all its parts: a diagram's every node, a picture's every label), and its **scenes**, the chapter cut into ideas (a run of beats each, every beat in one; an intent, a layout, the elements it uses; an element may go on into the next scene). It times nothing. Code mends the plan (scenes in order, a beat no scene has joins the one before it, unknown ids and elements in no scene left out, kinds switched off taken out) and keeps it (`plans`, by chapter). (2) **The choreography** (the Choreography role's model, `V2_CHOREOGRAPHY_MODEL`, else the Scenes model): the scenes a few at a time (about 30 s of narration a call, `V2_CHOREOGRAPHY_SECONDS`; at most 4 scenes), `V2_CHOREOGRAPHY_PARALLEL` 4 calls at once. Each is shown its scenes' lines as the voice says them (each word by number with its time; estimated, and said so, when the chapter is not spoken), what is just before and after, the elements its scenes use (their operation, their parts by ref `<element>.<part>`, what may be done with each, and whether it is already on the screen) and **each artifact's manual**: its section of `engine/BEAT_SCRIPT.md` (on the motion engine its template's of `engine/MOTION_ENGINE.md`, or a classic operation's with its row of §4), cut out by `app/lib/manuals.ts`. It answers **cues** (`choreograph`): `{"at": "b12.w3", "ref", "act"}`, an act being `enter` (with `in_pause` on the motion engine), `emphasis` (any part; on the motion engine any template too, with its `how`), `shade` (a labelled picture's part, current engine), `exit` (an element off the stage, current engine) or `stamp` (motion: a scene's, a few words). There is no camera: nothing zooms. (3) **Code lowers** plan and cues into the beats' operations (`lowerPlan`): each element on the beat and word of its entry (else as its scene begins), its parts on theirs (a string part becomes `{"name", "on"}`), never before what they are in; a diagram's node cued on a later line of its scenes held out of `show` and brought on there by a `reveal`; an emphasis on a node a `focus`, on a motion template an `emphasis` at `<id>.<part>` (the template given its element's id), on any other part of the current engine a `point`; a shade a `shade`; an exit an `unstage` (only on a beat that puts up nothing new); a stamp a `stamp`; a `manim` figure kept alone on its beat. What cannot be lowered is mended or left out, and each call's checks say so. On the current engine such a chapter is **strict** (`"strict": true`, engine/BEAT_SCRIPT.md §2): every animation is the JSON's own, nothing the engine adds or times by itself (no auto pictures, no pointing or lighting a part because a line names it, no inferred paragraphs, no Voice-tab re-timing). The beats are then compiled and mended as any others (a beat built again by itself, or mended, uses the per-beat writer). | 1 director call per chapter + 1 choreography call per ~30 s of narration |
| Manim agent (a beat's Manim figure) | With "built by the Manim agent" on (the default), the scene writer only plans a Manim figure (`{"op":"manim","id","plan"}`) and the **Manim agent** (`app/lib/manim-agent.ts`, the Manim role's model, `V2_MANIM_MODEL`) builds it, in turns with three tools: **make_image** (the image model draws a picture it wants: a cutout of a thing or person, white made clear, or a whole scene; in the lecture's look, no words; it is shown the picture), **check** (its code checked in the beat's place, after the earlier beats of the same figure, by v2's engine's compile: the sandbox's rules and a run of the blocks in a probe scene; nothing is rendered and no frame or video goes back to it, only the errors or "it runs") and **finish** (checked again if it is not the code last checked). Render the beat on the page to see the figure. Its code uses its pictures by name, `image("farmer", height=2.5, labels=[...])`, a helper added to v2's engine (`engine/free_check.py`, the registry `PANIM_BLOCK_IMAGES`). It runs on every planned figure after a build (in beat order), on a refused figure when mending (told what the compiler said), and on any beat from the page with your own words ("Build with the Manim agent"). The beat's page shows every turn: its words, its calls (agent and image model), each picture, each code check (the compiler's errors or "it runs", the code), and the code it settled on; the lecture's **Pictures** view shows every picture made and every agent run. At most `V2_MANIM_AGENT_TURNS` (10) turns and `V2_MANIM_AGENT_IMAGES` (4) pictures a figure. | turns (each a call) + 1 per picture |
| Pictures made before (reuse) | Every AI picture a scene asks for (on the stage, in a gallery, on a diagram) may be one made before: the same person, building or thing in another beat, chapter or lecture. With **a decision model decides** on (the default; the Scenes tab), the **Picture reuse** model (`V2_REUSE_MODEL`, else the triage's: Jev, on OpenRouter's Decisions API) is shown the picture needed (its words, how it is drawn, what it is for) and the pictures made before that could be it (each one's words and the prompt it was drawn from; code's shortlist: the same style, look and model, sharing a content word, up to 8), and chooses one option: **show picture k again** (only when it has the same shape and labels), **draw a new one that matches picture k** (the same person or place in another view, pose or moment: picture k is sent to the image model as its reference), or **draw fresh** (`engine/picture_judge.py`). Below 60% sure, a reuse is drawn anew to match instead and a match is drawn fresh. Each answer is kept, so a compile done again asks nothing; each question asked is a call (its state, its options, the answer). Each picture on the page says what was decided, how sure, the picture chosen and every picture it was asked about. With it off, the engine's own rule: the same words shown again, the same proper name matched. Colour codes, look names and titles are no longer taken for content or names. | 1 decision per new picture with a picture made before to compare |
| Voice (narration timed to the scenes) | The **Voice** tab speaks each chapter whose scenes are built (every beat has its visuals) and plays it with its narration (`app/lib/voice.ts`): a chapter, or every chapter with scenes not spoken yet, one after another. (1) The chapter is compiled as the Scenes step renders it. (2) Every line it says is spoken with the chosen voice (`engine/tools/prespeak.py`, v2's copy of v1's: several lines at once): **Gemini TTS** (`GEMINI_API_KEY`), **Google Chirp 3 HD**, **ElevenLabs** (times its own words) or **espeak-ng** (v2's offline voice, free and robotic, for trying the step; `engine/espeak_tts.py`), with a speaker and a pace (teacher, the default: the voice 10% slower with its pitch kept and real pauses between lines and ideas; natural, relaxed, slow); for Gemini and ElevenLabs v1's voice director marks the lines for delivery first. The lines are kept in one cache by voice and words (`.data/voice`, `V2_AUDIO_DIR`), so a line said again is not spoken or paid for again. (3) When each word is said: from the voice (ElevenLabs), or aligned to the audio here by Whisper through faster-whisper (`local_align.py`); when Whisper cannot be had, v2 **estimates** them (the words spread over the line's spoken stretches by length), says so on the page, and never keeps the estimate. (4) The **timing model** (`V2_TIMING_MODEL`, the Timing role) times each beat's animations to its words, in calls of 25 beats with v1's prompt (`align_cues.py`): a highlight on the word that names the part, a new picture at the line's start; code keeps the times in order and inside the line and writes them into the scene as `cues=` (`engine/tools/voice_scene.py`). (5) The timed scene is rendered with the voice: the exporter places each line where its beat starts and mixes one narration track (`engine/tools/narration.py`), and v1's web player plays it with the narration as its clock (the track served in byte ranges, so it seeks). The page shows each chapter (its scenes built, its voice, length, lines new and kept, cost, and when its scenes changed since it was spoken), and for one chapter: the player (the whole chapter or one beat), every line (its audio, length, cost, what the voice was given, the delivery marking, when each word is said and where those times came from) and every beat's animations on its line's timeline over the words' ticks, with the calls. **Reset** a chapter's voice or a lecture's. **Edit its beat script (JSON) and try it**: a chapter's beat script exactly as the compiler is given it (style, art, region, emblem, genre; the chapter, each beat with its number, its words said, its operations, paragraph, pause, about) in an editor; **Speak and play this** compiles the edit, speaks it, times its animations and plays it beside the chapter's own voice, untouched (`voice-<chapter>-try`), as often as wanted; what is wrong with the JSON is said as it is typed and when it is sent; **Apply to the scenes** puts each beat's visuals (by its number) into the Scenes tab and compiles them, the words said staying the transcript's (said so). **Instructions for an LLM**, in the same tab: everything the scene writer is told: its instructions (v1's, its subject, the kinds switched off; free-form Manim written as code, since nothing builds it after a model used by hand) with the answer's shape for a whole chapter, and the lecture's context (its chapters, the map region, its figures by id, each beat as the script planned it); say what to change, copy the prompt (instructions, this chapter's JSON, the change) into any chat model, and paste its answer into the editor (a ```json block is fine). | 1 timing call per 25 beats (+ the voice, per line spoken) |

**Parallel generation:** each figure is generated on its own, so any number can be generated at once: start one,
then another, or a batch while singles run (a batch skips the figures already being generated; a figure is never
generated twice at once). **Stop all** stops every batch after the figure each is on. `V2_GENERATE_PARALLEL` (3) is
how many figures one batch does at once.

**Pictures for the decision model** are made to fit first (`app/lib/imagefit.ts`, with sharp): no side over 1568 px
or under 64 px, no longer than 4:1 (padded with white), transparency flattened, PNG. Jev refused some book figures
outright ("Invalid image dimensions"); a picture it still refuses is decided by the chat model instead, and the
figure says so. `V2_IMAGE_MAX_SIDE`, `V2_IMAGE_MIN_SIDE`, `V2_IMAGE_MAX_RATIO` change the limits.

There is no length ceiling anywhere.

## Saved, continued, exported

- Every run is written to `app/.data/runs/<id>.json` as it goes: every step's result, every call, the triage. Pick
  it from **Past runs** at any time.
- **Stop** stops after the call in progress. **Continue from where it stopped** keeps every step done and does only
  what is left (figures not described, lectures not written), with the models now chosen. A run
  the server lost mid-way (a restart) shows as interrupted and continues the same way. **↻ redo** on a step clears
  it and the steps after it, and makes them again.
- **Export transcript (to import later)** (`/api/runs/<id>/export`): one file, `<book>-<run>.panim-transcript.json`,
  format `pocketanim.v2.transcript` version 2 (`app/lib/export.ts` is its contract). It holds:
  - `lectures`: each lecture's sentences numbered (`lines`), its text, its blocks and those it taught, and its
    script (chapters with their content, beats with their sentences and figures);
  - `blocks`: every block with Datalab's id, type, HTML, page and box, its lecture, and for a figure its
    description and triage (the way, who chose it, the instruction, what must stay exact);
  - `run`: the options it was made with; `triage`: the ways allowed and the model; `costs` by step;
  - `book`: the book itself, so the file is whole: the PDF, Datalab's JSON and each figure's picture (base64).

  **Import transcript** reads it (here or on another machine) as a run with every step done. Its book is the same
  PDF if it is already here (found by its sha256), else made again from the file, with no Datalab call. From an
  imported run everything goes on as from the run it came from: the PDF and its highlights, the figure triage,
  Continue, and the steps to come. **Markdown (to read)** is the same transcript to read; it is not imported.

## The page

- **Left:** the PDF with Datalab's block boxes drawn over it, each lecture in its own colour. Select a lecture, a
  chapter or a block to highlight its boxes; click a box to select its block.
- **Lectures:** each lecture and its chapters; click a chapter to see the blocks it teaches from (shared ones marked)
  and light them in the PDF; blocks not taught yet are listed.
- **Book:** every Datalab block: type, lecture, skipped reason, its HTML.
- **Transcript:** each lecture's chapters, then its beats with their numbered sentences.
- **Figures:** the triage: the ways a figure may be shown, the model, run / reset and rerun all / stop; every figure
  with its picture, the way chosen, the instruction, its error and its calls. The PDF colours each figure by its way.
- **Questions:** hard multiple-choice questions on each chapter's video (four options; apply, analyse, evaluate, infer),
  written by the questions model (`V2_QUESTIONS_MODEL`) from the chapter's narration beat by beat, in English and
  Hindi side by side (or one of them). Each names the beats that teach its answer, and shows where they play in the
  video (the Voice tab's narrated chapter, else the Scenes tab's chapter render); press the time to play that moment.
  Checked as they come back (four different options, a right answer, both languages, beats of the chapter), the right
  answers spread over A to D; per chapter or the whole lecture, answers shown or hidden, downloadable as JSON
  (`lib/questions.ts`).
- **Calls:** every call; open one to see its prompt part by part (click a part to open it), output, checks,
  attempts, tool schema and the request exactly as sent.
- **Costs:** by step, by model, by lecture (OpenRouter's own `usage.cost`).
- **Models:** check a model: whether it answers, how fast, its prices and context.

## Running it

```sh
cd harness_v2/app
npm install
OPENROUTER_API_KEY=... DATALAB_API_KEY=... npm run dev     # http://localhost:3100
npm run check                                                # type check and the offline flow check
```

Without `OPENROUTER_API_KEY`, every call is answered by an offline stand-in (cost 0), so the flow and the page can
be tried with no key. Without `DATALAB_API_KEY`, an offline reader builds JSON of the same shape from the PDF's text positions (pdf.js):
paragraphs, larger-font headings, and a Picture block for each picture a page paints (no captions, no bold).

**Figure pictures** are looked for wherever Datalab may put them (a block's `images`, its HTML's `<img>`, the
result's named images), and a figure block still without one takes the picture the PDF paints inside its box, cut
out of the PDF itself (`app/lib/pdf-images.ts`; a figure drawn as vector lines has none). What was found is in the
book's `figure-report.json` and on the Figures tab, with **Search the pictures again** (no Datalab call). A book
uploaded before this is searched again once, by itself.

**Triage without a transcript:** on the Figures tab with no run, **Read the book** (or **Read and describe the
figures**) starts a run that stops there; triage it, and Continue builds the transcript later. `DATALAB_MODE` (default `balanced`) sets Datalab's mode;
**Models come from `.env.local`** (`app/.env.example` lists them all), so nothing has to be typed. What v2's own
`app/.env.local` does not set is taken from v1's `harness/app/.env.local`, and v1's variable names work too. Each role
reads the first variable that is set (`app/lib/models.ts`):

| Role | Kind | Variables, in order | Used by |
| --- | --- | --- | --- |
| Writer | writes text | `V2_WRITER_MODEL`, `OPENROUTER_TRANSCRIPT_MODEL`, `OPENROUTER_MODEL` | transcript: each lecture as chapters and beats (reasons long) |
| Figures | reads images | `V2_FIGURE_MODEL`, `OPENROUTER_FIGURE_MODEL`, `OPENROUTER_SVG_MODEL` | transcript: figure descriptions |
| Triage | decides (Decisions API) | `V2_TRIAGE_MODEL` (default `typesafe/jev-1.14`) | figure triage |
| Triage (chat) | reads images | `V2_TRIAGE_CHAT_MODEL`, `V2_FIGURE_MODEL`, `OPENROUTER_FIGURE_MODEL` | figure triage: unsure figures, or a chat round |
| Image (redraw) | makes images | `V2_IMAGE_MODEL`, `PANIM_DIAGRAM_MODEL`, `PANIM_IMAGE_MODEL` | generation: redraws (Exact, Styled) |
| SVG | reads images, writes SVG | `V2_SVG_MODEL`, `OPENROUTER_MODEL` | generation: SVG drawings |
| Manim | reads images, writes Manim | `V2_MANIM_MODEL`, `PANIM_MANIM_MODEL`, `OPENROUTER_MODEL` | generation: Manim figures, rendered |
| Picture reuse | decides (Decisions API) | `V2_REUSE_MODEL`, `V2_TRIAGE_MODEL` (default `typesafe/jev-1.14`) | scenes: whether a picture made before is shown again, matched, or none |
| Timing | writes text | `V2_TIMING_MODEL`, `PANIM_ALIGN_MODEL`, `OPENROUTER_MODEL` | voice: the animations timed to the words |
| Map | reads images, writes a map script | `V2_MAP_MODEL`, `PANIM_MAP_MODEL`, `PANIM_MANIM_MODEL`, `OPENROUTER_MODEL` | generation: maps, rendered by v2's engine |

The **Models** tab shows each role's model and the variable it came from, can change one for the runs started or
continued next, and checks it (an image model passes only if an image comes back). A run keeps the models it was
started with. `V2_TRIAGE_PARALLEL` (4) sets how many figures are triaged at once, `V2_TRIAGE_CONFIDENCE` (0.6) the default
threshold. The Decisions API and its image input are marked alpha/early by OpenRouter: the answer is read loosely
(the option, the probabilities and the confidence wherever they are) and kept raw on the call, so a change in its
shape shows on the page. Each PDF is converted once and
cached in `app/.data/datalab/`.

Uploaded books and runs are kept in `app/.data/` (not versioned).
