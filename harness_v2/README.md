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
| Figure triage | A model that reads images decides, per figure, how the video shows it, choosing only from the ways ticked on the page: Manim (rebuilt exactly), Map, Exact redraw, Styled redraw, SVG drawing, Photo search, Book's picture, Leave out (`app/lib/triage-kinds.ts`). It gets the figure's picture, block, caption, description, the text around it and the lecture and goals it is in. Code checks the way is one offered and there is an instruction for whoever builds it. **Triage figures** does those not done yet; **Reset and rerun all** forgets every decision; each figure can be rerun alone or set by hand. | 1 per figure |

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
paragraphs and larger-font headings, no figures. `DATALAB_MODE` (default `balanced`) sets Datalab's mode;
`V2_PLANNER_MODEL`, `V2_WRITER_MODEL`, `V2_FIGURE_MODEL` and `V2_TRIAGE_MODEL` set the default models;
`V2_TRIAGE_PARALLEL` (4) how many figures are triaged at once. Each PDF is converted once and
cached in `app/.data/datalab/`.

Uploaded books and runs are kept in `app/.data/` (not versioned).
