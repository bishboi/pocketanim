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

v1 (`harness/`) is left as it is; v2 shares nothing with it at run time but the prompt texts it copied.

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
| Image (redraw) | makes images | `V2_IMAGE_MODEL`, `PANIM_DIAGRAM_MODEL`, `PANIM_IMAGE_MODEL` | redraws (Exact, Styled): to come |
| SVG | writes text | `V2_SVG_MODEL`, `OPENROUTER_MODEL` | SVG drawings: to come |
| Manim | writes text | `V2_MANIM_MODEL`, `PANIM_MANIM_MODEL`, `OPENROUTER_MODEL` | Manim figures: to come |
| Map | writes text | `V2_MAP_MODEL`, `PANIM_MAP_MODEL`, `PANIM_MANIM_MODEL`, `OPENROUTER_MODEL` | maps: to come |

The **Models** tab shows each role's model and the variable it came from, can change one for the runs started or
continued next, and checks it (an image model passes only if an image comes back). A run keeps the models it was
started with. `V2_TRIAGE_PARALLEL` (4) sets how many figures are triaged at once, `V2_TRIAGE_CONFIDENCE` (0.6) the default
threshold. The Decisions API and its image input are marked alpha/early by OpenRouter: the answer is read loosely
(the option, the probabilities and the confidence wherever they are) and kept raw on the call, so a change in its
shape shows on the page. Each PDF is converted once and
cached in `app/.data/datalab/`.

Uploaded books and runs are kept in `app/.data/` (not versioned).
