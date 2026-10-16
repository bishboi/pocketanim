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

There is no length ceiling anywhere. The wanted length of a lecture (minutes) is only stated as context in the plan
call; the topics decide where lectures end.

The prompts' words are v1's where they apply (`app/lib/prompts/texts.ts`); `app/lib/prompts/build.ts` builds each
prompt as named parts.

## The page

- **Left:** the PDF with Datalab's block boxes drawn over it, each lecture in its own colour. Select a lecture, a
  goal or a block to highlight its boxes; click a box to select its block.
- **Lectures:** each lecture's why, its blocks and its goals with their status (taught, written in after, missing).
- **Book:** every Datalab block: type, lecture, skipped reason, its HTML.
- **Transcript:** each lecture's text; a goal's sentences in green, patched ones in amber, untaught blocks listed.
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
`V2_PLANNER_MODEL`, `V2_WRITER_MODEL` and `V2_FIGURE_MODEL` set the default models. Each PDF is converted once and
cached in `app/.data/datalab/`.

Uploaded books and runs are kept in `app/.data/` (not versioned).
