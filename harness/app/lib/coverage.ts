/**
 * What a section of the book holds that its transcript must say, and what the transcript left out.
 *
 * A book's part has its MAIN THREAD -- its headings and the terms it sets in bold or italics, which the lesson
 * tells as one story -- and its ASIDES: boxes such as "Do you know?", "Interesting fact" or "Activity" that sit
 * beside the thread. Every one of both is taught (the source is covered whole); an aside is said as an aside, so
 * the story is not broken by it.
 */

import type { Language } from "./lecture";

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

const LATIN = /[A-Za-z]/;
const DEVANAGARI = /[ऀ-ॿ]/;

function words(text: string): string[] {
  return text.toLowerCase().normalize("NFKC").split(/[^\p{L}\p{M}\p{N}]+/u).filter(Boolean);
}

/** Whether the transcript says an idea: a short term as it is, a longer heading by most of its words. */
export function says(transcript: string, idea: string): boolean {
  const said = ` ${words(transcript).join(" ")} `;
  const wanted = words(idea);
  if (!wanted.length) return true;
  if (wanted.length <= 2) return said.includes(` ${wanted.join(" ")} `) || wanted.every((w) => said.includes(` ${w}`));
  const content = wanted.filter((w) => w.length >= (DEVANAGARI.test(w) ? 2 : 4));
  const found = content.filter((w) => said.includes(` ${w}`)).length;
  return found >= Math.ceil(content.length * 0.6);
}

/** The ideas of a part of the book the transcript leaves out. An idea in a script the lecture is not written in
 * (an English book taught in Hindi) cannot be matched word for word, and is left to the prompt. */
export function uncovered(transcript: string, source: string, language: Language): Idea[] {
  const latinLecture = language === "english" || language === "hinglish" ||
    (language === "auto" && LATIN.test(transcript) && !DEVANAGARI.test(transcript.slice(0, 2000)));
  const devanagariLecture = language === "hindi" || language === "hinglish" ||
    (language === "auto" && DEVANAGARI.test(transcript));
  return ideasOf(source).filter((idea) => {
    const latin = LATIN.test(idea.text) && !DEVANAGARI.test(idea.text);
    if (latin ? !latinLecture : !devanagariLecture) return false;
    return !says(transcript, idea.text);
  });
}
