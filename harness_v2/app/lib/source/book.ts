/**
 * The book, read by code: its sections (about five minutes of teaching each, cut at block ends), the book's own
 * questions in each, the items its text holds (headings, bold and italic terms, boxes beside the text, figures), and
 * the clean-up of a written section. Copied from harness v1 (transcript.ts, coverage.ts), unchanged in behaviour.
 */

import { bookQuestions, questionWords, type BookQuestion } from "./questions";

/** Narration words in a minute of finished lecture, at the slow teaching pace with its pauses, questions and cards. */
export const WORDS_PER_MINUTE = 100;
const SECTION_MINUTES = 5;

export type Section = {
  n: number;
  minutes: number;
  words: number;
  /** The part of the book this section teaches. */
  source: string;
  /** The book's own questions in this part (its exercises, MCQs). */
  questions?: BookQuestion[];
  /** Only more of the part's questions: its teaching was in the section before. */
  questionsOnly?: boolean;
};

export type WrittenSection = { n: number; title: string; text: string };

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


const BOOK_MIN_WORDS = 150;
/** The most narration a section asks for its book questions: about what a model writes well in one reply. */
const QUESTION_WORDS = 1500;

/** A book's text as blocks in order: a heading with what follows it, a paragraph, a figure line. */
/** The longest block a section is cut from, in words: a book read without paragraph breaks (pypdf, no blank lines)
 * came as one block of the whole chapter, a single section, and a single video of two hours. */
const BLOCK_WORDS = 250;

function bookBlocks(markdown: string): string[] {
  const blocks = markdown
    .replace(/^#+\s*page \d+\s*$/gim, "")
    .split(/\n\s*\n|\n(?=#)/)
    .map((b) => b.trim())
    .filter((b) => b && !/^#+\s*$/.test(b));
  return blocks.flatMap((block) => cutBlock(block, BLOCK_WORDS));
}

/** A long block in pieces of about `most` words: at its line breaks, else between sentences. */
function cutBlock(block: string, most: number): string[] {
  const size = (t: string) => t.split(/\s+/).filter(Boolean).length;
  if (size(block) <= most * 1.5) return [block];
  const lines = block.split(/\n+/);
  const units = lines.length > 1 ? lines : block.split(/(?<=[.?!।])\s+/);
  const out: string[] = [];
  let current: string[] = [];
  for (const unit of units) {
    if (current.length && size(current.join(" ")) + size(unit) > most) {
      out.push(current.join(lines.length > 1 ? "\n" : " "));
      current = [];
    }
    current.push(unit);
  }
  if (current.length) out.push(current.join(lines.length > 1 ? "\n" : " "));
  // A line longer than the limit (a page without line breaks) is cut again, by sentences.
  return out.flatMap((piece) => (lines.length > 1 && size(piece) > most * 1.5 ? cutBlock(piece.replace(/\n+/g, " "), most) : [piece]));
}

/**
 * The book in order, cut into sections of about SECTION_MINUTES each at block ends, each teaching its own slice.
 * A section's length follows its share of the book, so a long topic gets more time than a short one.
 */
export function bookSections(markdown: string, minutes: number): Section[] {
  const blocks = bookBlocks(markdown);
  const count = (b: string) => b.split(/\s+/).filter(Boolean).length;
  const total = Math.max(1, blocks.reduce((n, b) => n + count(b), 0));
  const wanted = Math.max(1, Math.min(blocks.length, Math.round(minutes / SECTION_MINUTES)));
  const groups: string[][] = [];
  let current: string[] = [];
  let taken = 0;
  for (const block of blocks) {
    current.push(block);
    taken += count(block);
    // Cut when this group has its share; a heading starts the next group rather than ending this one.
    if (taken >= (total * (groups.length + 1)) / wanted && groups.length < wanted - 1) {
      groups.push(current);
      current = [];
    }
  }
  if (current.length) groups.push(current);
  // The book's questions, found in the whole text (an exercise heading may sit in an earlier part), each in the
  // part where it is printed.
  const questions = bookQuestions(markdown);
  const flat = (text: string) => text.replace(/[*_`#>\s]+/g, " ").toLowerCase();
  const sources = groups.map((group) => flat(group.join("\n\n")));
  const home = questions.map((q) => {
    const at = sources.findIndex((src) => src.includes(flat(q.text).trim().slice(0, 40)));
    return at < 0 ? groups.length - 1 : at;
  });
  const out: Section[] = [];
  groups.forEach((group, i) => {
    const share = group.reduce((n, b) => n + count(b), 0) / total;
    const own = questions.filter((_, k) => home[k] === i);
    const base = Math.round(Math.max(1, minutes * share) * WORDS_PER_MINUTE);
    // The part's teaching, with as many of its questions as fit one reply; the rest of its questions follow in
    // sections of their own (a model writes about QUESTION_WORDS words at a time at full length, not 6,000).
    const chunks: BookQuestion[][] = [[]];
    let room = Math.max(0, QUESTION_WORDS - Math.round(base * 0.5));
    for (const q of own) {
      if (chunks[chunks.length - 1].length && questionWords(q) > room) {
        chunks.push([]);
        room = QUESTION_WORDS;
      }
      chunks[chunks.length - 1].push(q);
      room -= questionWords(q);
    }
    chunks.forEach((chunk, c) => {
      const asked = chunk.reduce((n, q) => n + questionWords(q), 0);
      const words = c === 0 ? Math.max(base, Math.round(asked + base * 0.5)) : Math.max(300, asked);
      out.push({
        n: out.length + 1,
        minutes: Math.round((words / WORDS_PER_MINUTE) * 10) / 10,
        words,
        // A section of only questions carries its part of the book, for the questions' context.
        source: group.join("\n\n"),
        ...(chunk.length ? { questions: chunk } : {}),
        ...(c > 0 ? { questionsOnly: true } : {}),
      });
    });
  });
  return out;
}

/** A part of the book without its exercise blocks (an exercise heading up to the next other heading). */
export function withoutExercises(source: string): string {
  const out: string[] = [];
  let skipping = false;
  for (const line of String(source ?? "").split("\n")) {
    const heading = /^#{1,6}\s+(.+)$/.exec(line)?.[1];
    if (heading !== undefined) skipping = /\b(?:exercises?|questions?|mcqs?|अभ्यास|प्रश्न(?:ावली)?)\b/i.test(heading);
    if (!skipping) out.push(line);
  }
  return out.join("\n").trim();
}


export function cleanSection(text: string): string {
  return text
    .split("\n")
    .filter((line) => !/^\s*#{1,6}\s/.test(line))
    .map((line) => line.replace(/^\s*(?:[-*•]|\d+[.)])\s+(?=\S)/, "").replace(/\[[^\]\n]{0,200}\]/g, "").replace(/ {2,}/g, " ").trimEnd())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** A text's sentences in order, as they are numbered for the coverage check (1-based in the prompts). */
export function linesOf(text: string): string[] {
  return text
    .split(/(?<=[.?!।])\s+|\n+/)
    .map((s) => s.trim())
    .filter((s) => /[\p{L}\p{N}]/u.test(s));
}

/** A section's text as numbered sentences ("12| ..."). */
export function numbered(text: string): string {
  return linesOf(text).map((line, i) => `${i + 1}| ${line}`).join("\n");
}

/** The first heading of a section's book text, or "". */
export function headingIn(source: string): string {
  return (/^#{1,6}\s+(.+)$/m.exec(source ?? "")?.[1] ?? "").replace(/[*_`]/g, "").trim().slice(0, 80);
}

/** How long the lecture runs when nobody says: about a minute for every 100 words of the book, 5 to 90. */
export function bookMinutes(markdown: string): number {
  const words = markdown.split(/\s+/).filter(Boolean).length;
  return Math.max(5, Math.min(90, Math.round(words / WORDS_PER_MINUTE)));
}
