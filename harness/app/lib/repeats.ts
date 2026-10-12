/**
 * Sentences said twice. A lecture's sections are written several at once, and a beat may name a line another beat
 * already said: the same sentence came out two or three times. A sentence that says again, word for word or nearly,
 * what was already said is taken out (a short one, "Let's see.", may come back: it is not a repeat of content).
 */

/** A sentence's words, lower case, letters and digits of any script. */
export function wordsOf(sentence: string): string[] {
  return (sentence.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []);
}

/** The fewest words a sentence has before its saying again counts as a repeat. */
const MIN_WORDS = 5;

/** Whether `b` says `a` again: the same words, or nearly (nine in ten words shared, both ways). */
export function sameSentence(a: string[], b: string[]): boolean {
  if (a.length < MIN_WORDS || b.length < MIN_WORDS) return false;
  if (a.join(" ") === b.join(" ")) return true;
  // "fact number 3" and "fact number 4" are two facts: the numbers must be the same.
  const numbers = (w: string[]) => w.filter((x) => /^\p{N}+$/u.test(x)).join(" ");
  if (numbers(a) !== numbers(b)) return false;
  const A = new Set(a);
  const B = new Set(b);
  let shared = 0;
  for (const w of A) if (B.has(w)) shared += 1;
  return shared / Math.max(A.size, B.size) >= 0.85;
}

/** Sentences of a text, each with the paragraph it is in. */
function sentencesOf(text: string): { paragraph: number; sentence: string }[] {
  return text.split(/\n\s*\n/).flatMap((paragraph, p) =>
    paragraph.split(/(?<=[.?!।])\s+|\n+/).map((s) => s.trim()).filter((s) => /[\p{L}\p{N}]/u.test(s))
      .map((sentence) => ({ paragraph: p, sentence })));
}

/**
 * `text` without the sentences that say again what `earlier` (sentences already said) or the text itself said
 * before them; paragraphs kept. Returns the text and the sentences taken out.
 */
export function dropRepeats(text: string, earlier: string[] = []): { text: string; dropped: string[] } {
  const seen = earlier.map(wordsOf).filter((w) => w.length >= MIN_WORDS);
  const exact = new Set(seen.map((w) => w.join(" ")));
  const kept: { paragraph: number; sentence: string }[] = [];
  const dropped: string[] = [];
  for (const item of sentencesOf(text)) {
    const words = wordsOf(item.sentence);
    if (words.length >= MIN_WORDS && (exact.has(words.join(" ")) || seen.some((s) => sameSentence(s, words)))) {
      dropped.push(item.sentence);
      continue;
    }
    kept.push(item);
    if (words.length >= MIN_WORDS) {
      seen.push(words);
      exact.add(words.join(" "));
    }
  }
  if (!dropped.length) return { text, dropped };
  const paragraphs = new Map<number, string[]>();
  for (const k of kept) paragraphs.set(k.paragraph, [...(paragraphs.get(k.paragraph) ?? []), k.sentence]);
  return { text: [...paragraphs.values()].map((s) => s.join(" ")).join("\n\n"), dropped };
}
