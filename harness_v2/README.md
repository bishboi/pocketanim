# Harness v2

A new harness, built one step at a time. It shares the deterministic engines with v1 (the PDF reader, the lecture
engine, maps, the compiler, the exporter, the Manim player and editor) and changes only how the harness works:

- **One step at a time.** Each step is added only when the one before it is right. Today there is one step: the
  **transcript**.
- **Everything visible.** Every model call is recorded whole: the prompt as the named parts it was built from (the
  rules, the book's text, the goals, the plan...), the tool it had to call, its output, what code checked in it,
  its tokens, time and cost. Every part of the book a step works from is highlighted on the PDF.
- **Code checks, models write.** What code can check or mend, it does, and says so (a check: passed, mended,
  failed, noted); a model is asked again only when there is nothing usable to mend.

v1 (`harness/`) is left as it is; v2 shares nothing with it at run time. v2 has its own copy of the lecture engine in
`harness_v2/engine/` (from v1's `harness/lecture/`, see `engine/ENGINE.md`), which draws its maps; changes to it are
v2's own.

## The transcript step

| Step | What | Calls |
| --- | --- | --- |
| 1. Read the book | Datalab's convert API with `output_format=json`: every block of every page with its id (`/page/3/Text/7`), type, HTML and bounding box. That JSON is the book from here on; nothing is rewritten into markdown. | none |
| 2. Figures | Each picture block described from its image, so the planner and writer know what it shows | 1 per figure |
| 3. Plan | One call reads the whole book as Datalab's JSON (id, block_type, html, figure description; no boxes) and divides it into lectures by what is learned, mapping each lecture's goals. It answers with block ids only. Code drops unknown ids, keeps a block placed twice in its first lecture, puts a block placed nowhere with the block before it, and keeps each goal's blocks inside its lecture. | 1 |
| 4. Write | Each lecture written in order from its blocks and goals, with every earlier lecture's full transcript in the prompt and the instruction to leave nothing out. The writer reports which goals and blocks it taught; one patch call writes in any it did not. | 1 per lecture, 1 patch call when needed |

Then, apart from the transcript and at any time once the book is read:

| Step | What | Calls |
| --- | --- | --- |
| Figure triage | A classification, so a **decision model** decides it by default: Jev (`typesafe/jev-1.14`) on OpenRouter's Decisions API (`app/lib/decisions.ts`), one Choice question per figure over the ways ticked on the page (Manim, Map, Exact redraw, Styled redraw, SVG drawing, Photo search, Book's picture, Leave out: `app/lib/triage-kinds.ts`), with the figure's picture, block, caption, description, the text around it and its lecture as state. It answers with the way, a probability for each and its confidence, and no words; under the threshold (60% by default) a figure is marked **unsure**. When Jev picks **Map** but the surer redraw (Exact or Styled) is under 20 points behind it (`V2_MAP_REDRAW_MARGIN`, 0.2), the figure is redrawn instead, and its check says so. A **chat model** that reads images can decide instead (a whole round, one figure, or **Ask the chat model about the unsure**), with an instruction for whoever builds the figure and its reason. Code checks the way is one offered. **Triage figures** does those not done yet; **Reset and rerun all** forgets every decision; each figure can be rerun alone or set by hand. | 1 per figure |
| Generation (redraws) | **Next: generate the redraws →** opens the Generate tab: every figure triaged **Exact** or **Styled redraw** (or set so by hand) is redrawn by the image model (`V2_IMAGE_MODEL`, default `google/gemini-2.5-flash-image`) from the book's figure, sent as the reference image (`app/lib/prompts/redraw.ts`). The prompt began as v1's (`genimage.py` `redraw_prompt`) and differs in two ways: **no text in the image** (every label, word and number left out, its spot left clear for labels put on later), and **gentle words** (an original illustration based on a sketch, never "an exact copy" or "looks just like it", which moderation such as Azure's blocks). When a model's moderation still blocks it, it is asked again in gentler words with no book text, then with no reference image, from what the figure shows; the card says which. Styled uses the same prompt for now (there are no lecture styles yet). Asked by chat completions with image output, else OpenRouter's Images API. Each figure shows the book's figure, the image made, and the prompt by its parts (and whole, as sent). **Generate**, **Reset and regenerate all**, **Regenerate** one, **Stop**. | 1 per figure (up to 3 when blocked) |
| Generation (SVG drawings) | On the same Generate tab, every figure triaged **SVG drawing** (or set so by hand) is drawn by the **SVG model** (`V2_SVG_MODEL`, a model that reads images; default `anthropic/claude-sonnet-4.5`): it is shown the book's figure and writes the SVG from it **in the same call**, no other model describing it first. The prompt is v1's SVG prompt and rules (`figures.ts` `SVG_PROMPT`/`SVG_RULES` before 506360a, `app/lib/prompts/svg.ts`) without its PHOTO/MANIM ways out: colours by name (INK, ROSE, RIVER…), parts as `<g id>`, labels as `<text>`, animation only when it teaches. Code checks it against those rules (viewBox, elements, colour names, parts, size) and sends what breaks them back to the same model once. The page shows it on v1's default board (atlas colours), with its parts, any rule it still breaks, its code, and the prompt by its parts. Nothing in an SVG can run: scripts, handlers and outside links are stripped, and it is served under a sandboxing CSP. | 1 per figure (2 when it breaks the rules) |
| Generation (Manim) | On the same Generate tab, every figure triaged **Manim** (or set so by hand) is written in Manim by the **Manim model** (`V2_MANIM_MODEL`, a model that reads images; default `anthropic/claude-sonnet-4.5`): it is shown the book's figure and writes the body of `construct()` **in the same call**, with v1's Manim rules (`lecture.ts` `MANIM_RULES`, `manimcoder.ts`: "the book's figure, to rebuild exactly"; `app/lib/prompts/manim.ts`) for one figure in one scene. Code checks it first (no imports, file/OS/process access, exec/eval, dunder names, while loops, classes, camera surgery), then renders it with the repo's Manim (`.venv` from `harness/scripts/setup-python.sh`, or `V2_PYTHON`) on v1's default board, in its own process and folder with a time limit (`V2_MANIM_TIMEOUT_SECONDS`, 120): its last frame (PNG) and its video (MP4, 480p). A refused or failed render goes back to the same model once, with the error. The card shows the frame, the video, the code and the prompt by its parts. | 1 per figure (2 when it fails) |
| Generation (maps) | Every figure triaged **Map** (or set so by hand) is written by the **map model** (`V2_MAP_MODEL`, a model that reads images; default `anthropic/claude-sonnet-4.5`): it is shown the book's map and writes it **in the same call** as a short map script: its region and 2-6 beats, each a line said and 1-4 of v1's map operations (marker, river, state, arrow, empire, relief, path, journey, graticule, dim; `app/lib/prompts/map.ts`). **v2's own lecture engine** (`harness_v2/engine`) checks and compiles it, looking every place up by name on real map data, and it is rendered silent like a Manim figure: its last frame and its video. A map the engine cannot draw (every operation left out) goes back to the same model once, with the engine's notes. Map operations are data: nothing the model writes is run. | 1 per figure (2 when refused) |
| Script (chapters and beats) | The **Script** tab cuts each written lecture's transcript into **chapters** (a topic, a few minutes: a title card with one line said on it, and one stage, a map or a board) and **beats** (1-2 of the transcript's numbered sentences, and what is on screen while they are said), one call per lecture (`V2_SCRIPT_MODEL`; `app/lib/prompts/script.ts`, `app/lib/script.ts`). The beats name sentences by number, never copy them, so the narration is the transcript word for word. The lecture's figures (with their way, caption, whether made yet, and the sentences that teach them) are placed on the beats that teach them. Code reads the answer against the transcript: numbers not in it dropped, a sentence used twice kept in its first beat, one left out put in the beat before it, beats and chapters put in sentence order, a figure not of the lecture dropped or shown twice kept once, a Map figure's chapter made a map chapter; beats that interleave go back to the model once. Each beat's "show" is a short note of what is on screen, to be built into the engine's operations by the step to come. One lecture at a time: pick it (it is then shown alone) and script it, or script the next one not scripted yet; or build them all, in parallel (`V2_SCRIPT_PARALLEL`, 3) or one after the other ("one at a time"). Scripts are saved in the run and the export. The tab shows all lectures in a table, then one lecture at a time in four views: **Chapters and beats** (a chapter outline beside the chapters; each beat with its sentences, the goals they teach, what is on screen and its figure), **Planning it used** (the lecture from the plan, its goals with their sentences and the chapters teaching them now, its figures with the beat each is on, the numbered transcript with each sentence's beat), **Prompt and answer** (each call: its prompt as parts, the answer before code mended it, the checks) and **Checks**. Clicking a beat, goal or figure lights up in the PDF what it teaches. | 1 per lecture (2 when broken) |
| Scenes (visuals per beat), look and render | The **Scenes** tab gives each beat of a script its visuals as the lecture engine's operations (`V2_SCENES_MODEL`; `app/lib/prompts/scenes.ts`, `app/lib/scenes.ts`): one call a chapter, in order, told the beats' sentences (fixed: the narration stays the transcript), the script's note of what is on screen, the beat's figure, the look, and only the **visual kinds switched on** (`app/lib/visual-kinds.ts`: map, book figures, AI illustrations, AI detailed diagrams, gallery, diagrams, timeline, Manim, equations, molecules, definitions, comparisons, questions, stats and bars, worked solutions, quotes and step boxes; v1's wording for each). Code takes out any op or picture of a kind switched off (also pictures on diagram nodes, timeline events, markers) and says so. A beat can have its own kinds. The **look** (`app/lib/styles.ts`, v1's templates and art styles: Atlas, Parchment, Lab, Cosmos, Vox, Cardboard, Whiteboard, Blueprint, Chalkboard; Clean, Detailed, Blueprint, Chalk, Sketch, Neon, Watercolour art) is picked with miniatures; scenes compile and render in it, and the Generate tab's **Styled** redraws are drawn in it (both redraws stand on its board colour). After a build the engine (`engine/compile_lecture.py`) checks and compiles the lecture, making its AI pictures (the run's image model; a stand-in picture with no key; their cost is a call in Costs); its errors and notes land on the beats they name, and the refused beats go back to the model once with what it said ("Mend refused" asks again). Build the next lecture, one, all (in parallel, `V2_SCENES_PARALLEL` 3, or one at a time), a chapter or a beat again (with a note for the model); change a beat's operations by hand as JSON. **Render** (silent, 480p, `V2_RENDER_PARALLEL` 2): a beat (its chapter rendered up to it, the beat cut out: clip and last frame, with what the engine's on-screen check found) or a chapter (its video and a frame per beat), in the run's look or any other. Renders are under `.data/runs/<run>/scenes/`. Scenes, look and kinds travel in the export. | 1 per chapter (+1 when beats are refused) |

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
  what is left (figures not described, the plan if none, lectures not written), with the models now chosen. A run
  the server lost mid-way (a restart) shows as interrupted and continues the same way. **↻ redo** on a step clears
  it and the steps after it, and makes them again.
- **Export transcript (to import later)** (`/api/runs/<id>/export`): one file, `<book>-<run>.panim-transcript.json`,
  format `pocketanim.v2.transcript` version 2 (`app/lib/export.ts` is its contract). It holds:
  - `lectures`: each lecture's sentences numbered (`lines`: the numbers the scene script will name), its text, its
    goals with their sentences and status, patched sentences marked, its blocks and those it taught;
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
  goal or a block to highlight its boxes; click a box to select its block.
- **Lectures:** each lecture's why, its blocks and its goals with their status (taught, written in after, missing).
- **Book:** every Datalab block: type, lecture, skipped reason, its HTML.
- **Transcript:** each lecture's text; a goal's sentences in green, patched ones in amber, untaught blocks listed.
- **Figures:** the triage: the ways a figure may be shown, the model, run / reset and rerun all / stop; every figure
  with its picture, the way chosen, the instruction, its error and its calls. The PDF colours each figure by its way.
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
| Planner | writes text | `V2_PLANNER_MODEL`, `OPENROUTER_MODEL` | transcript: plan |
| Writer | writes text | `V2_WRITER_MODEL`, `OPENROUTER_TRANSCRIPT_MODEL`, `OPENROUTER_MODEL` | transcript: lectures |
| Figures | reads images | `V2_FIGURE_MODEL`, `OPENROUTER_FIGURE_MODEL`, `OPENROUTER_SVG_MODEL` | transcript: figure descriptions |
| Triage | decides (Decisions API) | `V2_TRIAGE_MODEL` (default `typesafe/jev-1.14`) | figure triage |
| Triage (chat) | reads images | `V2_TRIAGE_CHAT_MODEL`, `V2_FIGURE_MODEL`, `OPENROUTER_FIGURE_MODEL` | figure triage: unsure figures, or a chat round |
| Image (redraw) | makes images | `V2_IMAGE_MODEL`, `PANIM_DIAGRAM_MODEL`, `PANIM_IMAGE_MODEL` | generation: redraws (Exact, Styled) |
| SVG | reads images, writes SVG | `V2_SVG_MODEL`, `OPENROUTER_MODEL` | generation: SVG drawings |
| Manim | reads images, writes Manim | `V2_MANIM_MODEL`, `PANIM_MANIM_MODEL`, `OPENROUTER_MODEL` | generation: Manim figures, rendered |
| Map | reads images, writes a map script | `V2_MAP_MODEL`, `PANIM_MAP_MODEL`, `PANIM_MANIM_MODEL`, `OPENROUTER_MODEL` | generation: maps, rendered by v2's engine |

The **Models** tab shows each role's model and the variable it came from, can change one for the runs started or
continued next, and checks it (an image model passes only if an image comes back). A run keeps the models it was
started with. `V2_TRIAGE_PARALLEL` (4) sets how many figures are triaged at once, `V2_TRIAGE_CONFIDENCE` (0.6) the default
threshold. The Decisions API and its image input are marked alpha/early by OpenRouter: the answer is read loosely
(the option, the probabilities and the confidence wherever they are) and kept raw on the call, so a change in its
shape shows on the page. Each PDF is converted once and
cached in `app/.data/datalab/`.

Uploaded books and runs are kept in `app/.data/` (not versioned).
