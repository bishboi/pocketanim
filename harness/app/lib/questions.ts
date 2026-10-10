/**
 * The questions a book (an uploaded PDF) asks: its exercises, in-text questions and multiple-choice questions. A
 * lecture from the book explains every one of them, each choice in turn (transcript.ts, the compiler's
 * _book_questions). Found in the PDF's markdown:
 *
 *   a numbered line ("3.", "Q3.", "Q.3", "प्रश्न 3.") with 2-5 choices after it ("(a) ... (b) ...", "A. ...",
 *   "(1) ...", "(क) ...", one to a line or several on one line) is a multiple-choice question;
 *   a numbered line under an exercise heading ("Exercises", "Questions", "MCQ", "अभ्यास", "प्रश्न"), or one that
 *   ends with a question mark, is a question to answer.
 */

export type BookQuestion = {
  /** The lecture's id for it ("q7"): books number each exercise from 1 again, so the book's number is not unique. */
  id: string;
  /** The number the book gives it. */
  number: string;
  text: string;
  /** Its choices, in the book's order; empty for a question to answer. */
  choices: string[];
  /** The answer the book prints, when it does ("Ans. (b)"). */
  answer?: string;
};

const QUESTION_HEADING = /(exercise|questions?\b|question bank|mcq|multiple[- ]choice|objective|test yourself|check your|self[- ]assessment|review|practice|assignment|worksheet|अभ्यास|प्रश्न)/i;
// "3." "Q3." "प्रश्न 3." and the chapter-numbered "4.1 Give the magnitude..." of an NCERT exercise: read as 4,
// every exercise came out as question 4 with its text starting "1 Give...".
const QUESTION_START =
  /^(?:Q(?:uestion)?\s*\.?\s*|प्रश्न\s*|Exercise\s*)?(?:(\d{1,2}\.\d{1,3})\s*[.):]?\s+|(\d{1,3})\s*[.):]\s*)(.+)$/i;
// A choice's mark: (a) a) a. A. (1) 1) (i) (क) क)
const CHOICE_MARK = /(?:^|\s)(?:\(([a-eA-E]|[1-5]|i{1,3}|iv|v|[कखगघङ])\)|([a-eA-E]|[कखगघङ])[.)](?=\s))\s*/g;
const ANSWER_LINE = /^(?:ans(?:wer)?|उत्तर|correct answer)\s*[:.\-–]?\s*(.+)$/i;

function clean(line: string): string {
  return line
    .replace(/\*\*|__|`/g, "")
    .replace(/^\s*(?:[-*•]\s+|>\s*)/, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The choices on a line that starts with a choice mark, or null when it does not start with one. */
function choicesOn(line: string): string[] | null {
  const marks = [...line.matchAll(CHOICE_MARK)];
  if (!marks.length || marks[0].index !== 0) return null;
  const out: string[] = [];
  marks.forEach((mark, i) => {
    const start = (mark.index ?? 0) + mark[0].length;
    const end = i + 1 < marks.length ? marks[i + 1].index ?? line.length : line.length;
    const text = line.slice(start, end).trim();
    if (text) out.push(text);
  });
  return out;
}

/**
 * The questions in a book's markdown, in order. `start` numbers the ids on from an earlier part of the same book
 * (ids are q<start+1>, q<start+2>...).
 */
export function bookQuestions(markdown: string, start = 0): BookQuestion[] {
  const found: BookQuestion[] = [];
  let inQuestions = false;
  let current: (BookQuestion & { counted: boolean; open: boolean }) | null = null;
  const finish = () => {
    if (!current) return;
    const { counted, open: _open, ...question } = current;
    void _open;
    // Long "choices" are a question's parts ("Explain why (a) a horse cannot pull a cart... (b) ..."), each to be
    // answered, not options to mark right or wrong: they stay in its text.
    const long = question.choices.length &&
      question.choices.reduce((n, c) => n + c.length, 0) / question.choices.length > 45;
    if (long || question.choices.length > 5) {
      const parts = question.choices.map((c, i) => `(${"abcdefghij"[i] ?? i + 1}) ${c}`).join(" ");
      found.push({ ...question, text: `${question.text} ${parts}`.slice(0, 600), choices: [] });
    } else if (question.choices.length >= 2) {
      found.push(question);
    } else if (counted) {
      found.push({ ...question, choices: [] });
    }
    current = null;
  };
  for (const raw of markdown.split("\n")) {
    if (/^\s*#/.test(raw)) {
      finish();
      inQuestions = QUESTION_HEADING.test(raw);
      continue;
    }
    const line = clean(raw);
    if (!line) continue;
    if (!current && QUESTION_HEADING.test(line) && line.length < 60 && !QUESTION_START.test(line)) {
      inQuestions = true;              // a heading written as a bold line ("**Exercises**")
      continue;
    }
    const answer = ANSWER_LINE.exec(line);
    if (answer && current) {
      current.answer = answer[1].trim().slice(0, 200);
      current.open = false;
      continue;
    }
    const choices = current?.open ? choicesOn(line) : null;
    if (choices && current) {
      current.choices.push(...choices);
      continue;
    }
    const start_ = QUESTION_START.exec(line);
    if (start_) {
      finish();
      let text = start_[3].trim();
      // Choices on the question's own line: "3. Which is a force? (a) push (b) sleep (c) ..."
      const inline = [...text.matchAll(CHOICE_MARK)];
      let choicesHere: string[] = [];
      if (inline.length >= 2) {
        const at = inline[0].index ?? 0;
        choicesHere = choicesOn(text.slice(at).trim()) ?? [];
        text = text.slice(0, at).trim();
      }
      current = {
        id: "",
        number: start_[1] ?? start_[2],
        text: text.slice(0, 400),
        choices: choicesHere,
        counted: inQuestions || /[?？]\s*$/.test(text),
        open: true,
      };
      continue;
    }
    if (current?.open && !current.choices.length && current.text.length < 400) {
      current.text = `${current.text} ${line}`.slice(0, 400);    // the question runs on to the next line
    } else {
      finish();
    }
  }
  finish();
  return found.map((q, i) => ({ ...q, id: `q${start + i + 1}` }));
}

/** Words of narration a question needs: read it, the right answer and why, each wrong choice in a line on why not.
 * (80 + 45 a choice made every multiple-choice question a long speech.) */
export function questionWords(question: BookQuestion): number {
  return question.choices.length ? 60 + 25 * question.choices.length : 110;
}

/** A question as the prompts list it: its id, the book's number, the question and its choices. */
export function questionLine(question: BookQuestion): string {
  const choices = question.choices.map((c, i) => `(${"ABCDE"[i]}) ${c}`).join("  ");
  return `  ${question.id} (the book's ${question.number}): ${question.text}${choices ? `\n      ${choices}` : ""}` +
    (question.answer ? `\n      the book's answer: ${question.answer}` : "");
}

function fold(text: string): string {
  return text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

/** The book questions a section's text does not take up (how it explains them is the writer's). */
export function unexplainedQuestions(text: string, questions: BookQuestion[]): { id: string; what: string }[] {
  const said = fold(text);
  const out: { id: string; what: string }[] = [];
  for (const q of questions) {
    // Explained in another language than the book's (an English exercise taught in Hindi), its words are not in
    // the narration: then its number said out ("प्रश्न 4.1"), or most of its numbers, show it is the one taught.
    const number = q.number.replace(".", "\\.");
    const called = new RegExp(
      q.number.includes(".") ? `(^|[^\\d.])${number}(?![\\d])`
        : `(question|प्रश्न|सवाल|exercise|अभ्यास|Q\\.?)\\s*(नंबर|संख्या|number|no\\.?)?\\s*${number}(?![\\d])`,
      "i").test(text);
    const values = q.text.match(/\d+(?:\.\d+)?/g) ?? [];
    const valuesHeard = values.filter((v) => text.includes(v)).length;
    const words = q.text.split(/[^\p{L}\p{N}]+/u).filter((w) => w.length >= 4);
    const heard = words.filter((w) => said.includes(fold(w))).length;
    const covered = called || (values.length >= 2 && valuesHeard >= Math.ceil(values.length * 0.6)) ||
      !words.length || heard >= Math.ceil(words.length * 0.5);
    if (!covered) {
      out.push({ id: q.id, what: `question ${q.number} ("${q.text.slice(0, 60)}")` });
      continue;
    }
  }
  return out;
}
