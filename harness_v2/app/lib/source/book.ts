/**
 * A written lecture's text, as code reads it: what a teacher does not say taken out, and its sentences numbered (the
 * writer reports which sentences teach each block and goal by these numbers).
 */

/** Spoken words in a minute of finished lecture, at the slow teaching pace with its pauses, questions and cards. */
export const WORDS_PER_MINUTE = 100;

/** A text without what a teacher does not say: markdown headings, bullet marks and [stage directions]. */
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

