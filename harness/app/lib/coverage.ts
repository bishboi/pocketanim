/**
 * What a section of the book holds that its transcript must say (listed in its request; the writer covers it).
 *
 * A book's part has its MAIN THREAD -- its headings and the terms it sets in bold or italics, which the lesson
 * tells as one story -- and its ASIDES: boxes such as "Do you know?", "Interesting fact" or "Activity" that sit
 * beside the thread. Every one of both is taught (the source is covered whole); an aside is said as an aside, so
 * the story is not broken by it.
 */

/** A box beside the thread: by its heading or its opening words, or set as a quotation. */
const ASIDE = /^(?:do you know|did you know|interesting (?:fact|facts)|fun fact|amazing fact|fact ?file|know more|think about it|think it over|activity|box|note|extra|for your information|more to know|क्या आप जानते हैं|क्या तुम जानते हो|रोचक तथ्य|रोचक जानकारी|मज़ेदार तथ्य|मजेदार तथ्य|जानकारी|क्रियाकलाप|गतिविधि|सोचिए|याद रखें|ध्यान दें)\b/i;
/** Headings of the book's exercises: their questions are explained by the question checks, not here. */
const EXERCISES = /\b(?:exercises?|questions?|mcqs?|intext|in-text|अभ्यास|प्रश्न|प्रश्नावली)\b/i;

export type Aside = { title: string; text: string };

function plain(text: string): string {
  return text.replace(/[*_`#>]+/g, " ").replace(/\s+/g, " ").trim();
}

/** The asides of a part of the book, in order. */
export function asidesOf(source: string): Aside[] {
  const out: Aside[] = [];
  const blocks = String(source ?? "").split(/\n\s*\n/);
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i].trim();
    const heading = /^#{1,6}\s+(.+)$/.exec(block.split("\n")[0])?.[1];
    const opening = plain(block.split("\n")[0]).replace(/^[\d.\s]+/, "");
    const quoted = block.split("\n").every((line) => /^\s*>/.test(line));
    if (!(ASIDE.test(opening) || quoted)) continue;
    // A heading on its own: its box is the paragraph after it.
    let body = heading && block.split("\n").length === 1 ? (blocks[i + 1] ?? "") : block;
    if (heading && block.split("\n").length === 1) i += 1;
    body = plain(body);
    out.push({ title: plain(heading ?? opening.split(/[:.!?।]/)[0]).slice(0, 80), text: body.slice(0, 400) });
  }
  return out;
}

export type Idea = { kind: "heading" | "term" | "aside"; text: string };

/** The ideas a part of the book holds that its transcript must say: its headings, its bold and italic terms, and
 * its asides (by their content's own terms). */
export function ideasOf(source: string): Idea[] {
  const text = String(source ?? "");
  const out: Idea[] = [];
  const seen = new Set<string>();
  const add = (kind: Idea["kind"], value: string) => {
    const clean = plain(value).replace(/^[\d.()\s]+/, "").replace(/[:.,;]+$/, "").trim();
    const key = clean.toLowerCase();
    if (clean.length < 3 || clean.split(/\s+/).length > 8 || seen.has(key)) return;
    seen.add(key);
    out.push({ kind, text: clean });
  };
  for (const m of text.matchAll(/^#{1,6}\s+(.+)$/gm)) {
    const heading = plain(m[1]);
    if (!EXERCISES.test(heading) && !ASIDE.test(heading.replace(/^[\d.\s]+/, ""))) add("heading", heading);
  }
  // Asides before the terms: a bold word inside an aside is the aside's, and is checked as one.
  const blocks = text.split(/\n\s*\n/);
  for (const aside of asidesOf(text)) {
    // An aside is covered when its content is: the first of its own bold terms, else its title.
    const raw = blocks.find((b) => plain(b).includes(aside.text.slice(0, 40))) ?? "";
    const term = /\*\*([^*\n]{2,80})\*\*/.exec(raw)?.[1];
    if (term || !ASIDE.test(aside.title)) add("aside", term ?? aside.title);
  }
  for (const m of text.matchAll(/\*\*([^*\n]{2,80})\*\*|__([^_\n]{2,80})__/g)) add("term", m[1] ?? m[2]);
  return out;
}

/**
 * The coverage check of a planned lecture (learningmap.ts, storyplan.ts), done by code: each section reports the
 * goals it taught (write_section "goals_taught", by sentence number); a goal of the section's it did not report is
 * written in by a small patch (PATCH_TOOL, patchRequest) where it fits, and the lecture's count is shown.
 */

/** The goal ids a section reports as taught, kept only when they are its own and name a sentence it has. */
export function goalsTaught(raw: unknown, own: string[], sentences: number): string[] {
  const list = Array.isArray(raw) ? raw : [];
  const out = new Set<string>();
  for (const item of list) {
    const goal = String((item as { goal?: unknown })?.goal ?? item ?? "").trim();
    const lines = (item as { lines?: unknown })?.lines;
    const named = Array.isArray(lines) ? lines.map(Number).filter((n) => n >= 1 && n <= sentences) : [];
    if (own.includes(goal) && (named.length || !Array.isArray(lines))) out.add(goal);
  }
  return [...out];
}

export const PATCH_TOOL = {
  type: "function" as const,
  function: {
    name: "write_patch",
    description: "Save the words that teach a goal the section left out, and the sentence they follow.",
    parameters: {
      type: "object",
      properties: {
        after_line: { type: "integer", description: "The number of the sentence the words follow." },
        text: { type: "string", description: "The words to add: only what the teacher says, a few sentences." },
      },
      required: ["after_line", "text"],
      additionalProperties: false,
    },
  },
};

/** The request for a patch: the section's numbered sentences, the goal it missed, and its part of the book. */
export function patchRequest(numbered: string, goal: string, source: string): string {
  return [
    "A section of a video lecture's transcript, its sentences numbered:",
    numbered,
    "",
    `It was to teach this goal and did not: ${goal}`,
    "",
    "Its part of the book:",
    source.slice(0, 6000),
    "",
    "Write the few sentences that teach it, in the section's own voice and language, from the book's facts only, and",
    "say after which sentence they go: where they fit the flow, not at the very end. Call write_patch once.",
  ].join("\n");
}

/** The section's text with `addition` after its sentence number `after` (1-based, as linesOf numbers them); after
 * the last paragraph's first sentence when the number is not found, so the section still ends on its hand-off. */
export function insertAfterLine(text: string, lines: string[], after: number, addition: string): string {
  const words = addition.trim();
  if (!words) return text;
  const line = lines[Math.max(0, Math.min(lines.length, after) - 1)];
  const at = line ? text.indexOf(line) : -1;
  if (at >= 0) {
    const end = at + line.length;
    return `${text.slice(0, end)} ${words}${text.slice(end)}`;
  }
  const paragraphs = text.split(/\n\s*\n/);
  paragraphs.splice(Math.max(0, paragraphs.length - 1), 0, words);
  return paragraphs.join("\n\n");
}
