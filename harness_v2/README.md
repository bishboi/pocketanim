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

v1 (`harness/`) is left as it is; v2 calls v1's PDF reader (`harness/lecture/pdf_source.py`) and nothing else.

## The transcript step

The same structure as v1's planned book lecture:

| Step | What | Calls |
| --- | --- | --- |
| 1. Read the book | The book cut into sections of about 5 minutes; its questions; its items (headings, bold terms, boxes, figures) | none |
| 2. Learning map | Goals, every item under one; code drops unknown ids, splits goals over two sections, adds goals for items left out | 1 |
| 3. Story plans | Videos of 25-30 minutes decided from the sections; each video's big question, running example, arc, hand-offs; book questions placed | 1 per video |
| 4. Write sections | Each section's transcript, several at once, from its plan and goals; headings and repeats taken out; each goal it did not report written in by a small patch | 1 per section, 1 per missing goal |
| 5. Videos | Each video's written length; one written past 30 minutes cut between sections | none |

The prompts' words are v1's (`app/lib/prompts/texts.ts`); `app/lib/prompts/build.ts` builds each as named parts.

## The page

- **Left:** the PDF. With nothing selected, every section's text in its own colour. A section: its text and its
  items. A goal: its items, in green. The bar says how many of the parts were found in the PDF's text.
- **Plan:** each video's story; each section's part in it, its book questions and its goals with their items and
  status (taught, written in after, missing).
- **Transcript:** each section's text, sentences numbered; a goal's sentences in green, patched ones in amber.
- **Calls:** every call; open one to see its prompt part by part (click a part to open it), output, checks,
  attempts, tool schema and the request exactly as sent.
- **Costs:** by step, by model, by section (OpenRouter's own `usage.cost`).
- **Models:** check a model: whether it answers, how fast, its prices and context.

## Running it

```sh
cd harness_v2/app
npm install
OPENROUTER_API_KEY=... DATALAB_API_KEY=... npm run dev     # http://localhost:3100
npm run check                                                # type check and the offline flow check
```

Without `OPENROUTER_API_KEY`, every call is answered by an offline stand-in (cost 0), so the flow and the page can
be tried with no key. Without `DATALAB_API_KEY`, the PDF is read by pypdf: no headings or bold come through, so the
learning map has few items to place. `V2_PLANNER_MODEL` and `V2_WRITER_MODEL` set the default models.

Uploaded books and runs are kept in `app/.data/` (not versioned).
