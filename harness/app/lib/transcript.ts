/**
 * The transcript stage of a lecture: before any beat or picture, the model writes the whole lecture as a teacher
 * would speak it, section by section, at full length. Only then is the video built, and its narration is that
 * transcript, sentence for sentence (checked here), so the detail written in stage one cannot be squeezed out.
 *
 * With a reference video, the sections follow its parts (about five minutes of it each): the same order, its
 * examples, its questions and its solved problems, explained in more detail than the video does. Without one,
 * the content is taught in order in sections of about five minutes.
 */

import { linesOf, numberedSection } from "./lines";
import { microMinutes } from "./topics";
import type { DocumentManifest } from "./document";
import type { Language } from "./lecture";
import { bookQuestions, questionLine, questionWords, unexplainedQuestions, type BookQuestion } from "./questions";
import { asidesOf, ideasOf, uncovered } from "./coverage";

/** Narration words in a minute of finished lecture, at the slow teaching pace with its pauses, questions and cards. */
export const WORDS_PER_MINUTE = 100;
const SECTION_MINUTES = 5;

export type Section = {
  n: number;
  /** The reference video's parts this section remakes (1-based), when there is a reference. */
  parts: number[];
  minutes: number;
  words: number;
  /** What the reference video says in those parts, or the part of the book this section teaches. */
  source: string;
  /** The source is a book's (a PDF's) text, to be taught with examples and questions the book does not have. */
  book?: boolean;
  /** The book's own questions in this part (its exercises, MCQs): each is explained in full, every choice. */
  questions?: BookQuestion[];
  /** Only more of the part's questions: its teaching was in the section before. */
  questionsOnly?: boolean;
};

export type WrittenSection = { n: number; title: string; text: string };

/** The sections to write, and how many words each needs for the lecture to run `minutes`. */
export function transcriptSections(reference: DocumentManifest | null, minutes: number, book = ""): Section[] {
  const parts = reference?.parts ?? [];
  if (!parts.length && book.split(/\s+/).filter(Boolean).length >= BOOK_MIN_WORDS) return bookSections(book, minutes);
  if (parts.length) {
    const total = Math.max(1, parts[parts.length - 1].end - parts[0].start);
    const groups: (typeof parts)[] = [];
    let current: typeof parts = [];
    for (const part of parts) {
      current.push(part);
      const span = current[current.length - 1].end - current[0].start;
      if (span >= SECTION_MINUTES * 60 * 0.8) {
        groups.push(current);
        current = [];
      }
    }
    if (current.length) {
      if (groups.length && current[current.length - 1].end - current[0].start < SECTION_MINUTES * 60 * 0.35) {
        groups[groups.length - 1].push(...current);
      } else {
        groups.push(current);
      }
    }
    return groups.map((group, i) => {
      const share = (group[group.length - 1].end - group[0].start) / total;
      const sectionMinutes = minutes * share;
      return {
        n: i + 1,
        parts: group.map((p) => p.part),
        minutes: Math.round(sectionMinutes * 10) / 10,
        words: Math.round(sectionMinutes * WORDS_PER_MINUTE),
        source: group.map((p) => p.text).join(" "),
      };
    });
  }
  const count = Math.max(1, Math.round(minutes / SECTION_MINUTES));
  return Array.from({ length: count }, (_, i) => ({
    n: i + 1,
    parts: [],
    minutes: Math.round((minutes / count) * 10) / 10,
    words: Math.round((minutes / count) * WORDS_PER_MINUTE),
    source: "",
  }));
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
        parts: [],
        minutes: Math.round((words / WORDS_PER_MINUTE) * 10) / 10,
        words,
        // A section of only questions carries its part of the book, for the questions' context.
        source: group.join("\n\n"),
        book: true,
        ...(chunk.length ? { questions: chunk } : {}),
        ...(c > 0 ? { questionsOnly: true } : {}),
      });
    });
  });
  return out;
}

export const SECTION_TOOL = {
  type: "function" as const,
  function: {
    name: "write_section",
    description:
      "Save one section of the lecture's spoken transcript, in order (section 1, then 2, ...). The text is only " +
      "what the teacher says, in paragraphs: no stage directions, no headings, no brackets, no markdown.",
    parameters: {
      type: "object",
      properties: {
        section: { type: "integer", description: "The section number, starting at 1." },
        title: { type: "string", description: "A short English title for what the section teaches." },
        text: { type: "string", description: "The section's full spoken transcript, paragraph by paragraph." },
      },
      required: ["section", "title", "text"],
      additionalProperties: false,
    },
  },
};

export function transcriptPrompt(options: {
  sections: Section[];
  minutes: number;
  language: Language;
  languageRules: string;
  subject?: string;
  hasReference: boolean;
  content: string;
}): string {
  const { sections, hasReference } = options;
  const range = microMinutes();
  return [
    "You write the complete spoken TRANSCRIPT of a video lecture: every word the teacher says, in order. A later",
    "step turns it into the video sentence for sentence and adds the pictures, so everything the student hears is",
    "in these words.",
    "",
    "THREE THINGS MATTER, and nothing else is asked of you:",
    "  1. THE QUALITY OF THE LEARNING comes first. How to teach is yours to decide: the order of explanation, the",
    "     examples, analogies and stories, questions for the class, worked problems, how deep each idea goes, how a",
    "     video opens and closes. Do whatever makes the student truly understand and remember. Nothing about your",
    "     style or length is counted or checked.",
    `  2. VIDEOS OF ${range.min}-${range.max} MINUTES. A long lecture is watched as several videos of about ${range.min}-${range.max}`,
    `     minutes (a minute is about ${WORDS_PER_MINUTE} spoken words). Where each starts and ends is decided from your`,
    "     written transcript, always between sections, and you are then asked for the words that close one video and",
    "     open the next. So write the sections as one continuous lecture, and spend the time where learning needs it.",
    "  3. COVER EVERYTHING IN THE SOURCE: every idea, definition, law, fact, figure, table, example, box or aside,",
    "     and question in it. This is the one thing checked: a section that leaves part of its text out, or one of",
    "     the source's own questions, is sent back.",
    "",
    "HOW THE TRANSCRIPT IS USED (facts, not rules of style):",
    "  - A voice speaks it, so write only the words said: no headings, bullet lists, [brackets] or stage directions,",
    "    and say formulas and symbols the way they are spoken.",
    ...(sections.some((s) => s.book) ? [
      "  - Where the source marks [FIGURE figN: caption], the video shows that figure as it is spoken of there.",
    ] : []),
    ...(hasReference ? [
      "  - The source is a reference video's automatic captions (given for each section): many words are misheard",
      "    and numbers garbled; work out what the teacher meant. Its channel talk (subscribe, the next video) is not",
      "    content.",
    ] : []),
    "  - Each request asks for one section, with the end of the one before when it is written: write that one",
    "    section, carrying on from there.",
    ...(options.subject ? [`  - The subject is ${options.subject}.`] : []),
    "",
    options.languageRules.trim(),
    "",
    "THE SECTIONS, in order (each request gives that section's own source):",
    ...sections.map((s) => `  SECTION ${s.n}` +
      (s.parts.length ? `: part${s.parts.length > 1 ? "s" : ""} ${s.parts.join(", ")} of the reference`
        : s.questionsOnly ? ": more of the source's questions from the section before"
        : s.book ? `: ${headingIn(s.source) || "its part of the book"}` : "") +
      (s.questions?.length ? ` (${s.questions.length} of the source's questions)` : "")),
    "",
    ...(options.content.trim() ? ["THE CONTENT (notes, a chapter) to teach from:", options.content.slice(0, 60000)] : []),
  ].join("\n");
}


/**
 * Why a written section is sent back, or null when it is accepted. Coverage is the only check: every idea, aside
 * and figure of its part of the book, and each of the source's own questions taken up. How it teaches, and how
 * long it takes, are the writer's.
 */
export function sectionProblem(text: string, section: Section, language: Language): string | null {
  if (!text.trim()) return `Section ${section.n} came back empty.`;
  const skipped = unexplainedQuestions(text, section.questions ?? []);
  if (skipped.length) {
    return `Section ${section.n} leaves out the source's ${skipped.map((s) => s.what).join("; ")}. Take up every ` +
      "question of the section (say which one it is, by its number).";
  }
  if (section.book && !section.questionsOnly) {
    // The whole of its part of the book: every heading, every aside, and the terms it sets in bold (one may be
    // missed: a bold word in a caption, say).
    const missing = uncovered(text, section.source, language);
    const heavy = missing.filter((idea) => idea.kind !== "term");
    const terms = missing.filter((idea) => idea.kind === "term");
    if (heavy.length || terms.length > 1) {
      const named = [...heavy, ...terms].slice(0, 8).map((idea) => `${idea.kind === "aside" ? "the aside " : ""}"${idea.text}"`);
      return `Section ${section.n} leaves out parts of its source: ${named.join(", ")}${missing.length > 8 ? ", ..." : ""}. ` +
        "Teach each of them, where it fits.";
    }
  }
  return null;
}

/**
 * A section's text without what a teacher does not say, removed rather than refused: markdown headings, bullet
 * marks, and [stage directions]. A section refused for one heading line was written again, at full length.
 */
export function cleanSection(text: string): string {
  return text
    .split("\n")
    .filter((line) => !/^\s*#{1,6}\s/.test(line))
    .map((line) => line.replace(/^\s*(?:[-*•]|\d+[.)])\s+(?=\S)/, "").replace(/\[[^\]\n]{0,200}\]/g, "").replace(/ {2,}/g, " ").trimEnd())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Whether a refusal can be mended by adding to the end of the section rather than writing it again: all of them
 * can (something of the source is missing). */
export function repairable(problem: string): boolean {
  return /leaves out/.test(problem);
}

/** The request that mends a refused section by adding to it (repairable): only the new paragraphs, at its end. */
export function repairRequest(section: Section, count: number, text: string, problem: string): string {
  return [
    `SECTION ${section.n} of ${count} is written, and it ends like this:`,
    `  ...${text.slice(-1500)}`,
    "",
    `It was sent back: ${problem}`,
    "",
    "Do NOT write the section again. Write ONLY the new paragraphs that teach what is missing, to be added at its " +
      "end, carrying on naturally from where it stops, in the same voice and language.",
    ...(sectionSource(section) ? ["", sectionSource(section)] : []),
    "",
    `Call write_section with section: ${section.n} and, as its text, only the new paragraphs.`,
  ].join("\n");
}

/** Whether a reply to repairRequest wrote the whole section again instead of only what to add. */
export function rewroteWhole(addition: string, before: string): boolean {
  const start = norm(before.slice(0, 160));
  return addition.length > before.length * 0.7 && start.length > 20 && norm(addition.slice(0, 400)).includes(start.slice(0, 40));
}

/**
 * The request for one section. Each section is asked for on its own, with the sections before it summed up and the
 * end of the last one quoted: a growing conversation of saved and refused sections confused models into rewriting
 * an old section over and over ("Write section 7 next." twenty times).
 */
/** The first heading of a section's book text, or "". */
function headingIn(source: string): string {
  return (/^#{1,6}\s+(.+)$/m.exec(source ?? "")?.[1] ?? "").replace(/[*_`]/g, "").trim().slice(0, 80);
}

/** What one section is to say: its slice of the reference or the book, and the book's questions in it. */
export function sectionSource(section: Section): string {
  const questions = section.questions?.length
    ? `\nTHE SOURCE'S QUESTIONS IN THIS SECTION (${section.questions.length}; every one taken up):\n` +
      section.questions.map(questionLine).join("\n")
    : "";
  if (section.parts.length) {
    return `WHAT THE REFERENCE SAYS IN PART${section.parts.length > 1 ? "S" : ""} ${section.parts.join(", ")}:\n` +
      section.source.slice(0, 12000);
  }
  if (section.questionsOnly) return `THE BOOK'S TEXT THESE QUESTIONS COME FROM:\n${section.source.slice(0, 6000)}${questions}`;
  if (section.book) return `THE PART OF THE BOOK THIS SECTION TEACHES:\n${section.source.slice(0, 12000)}${coverList(section.source)}${questions}`;
  return "";
}

/** What a part of the book covers: its ideas and its asides, all of which the section teaches. */
function coverList(source: string): string {
  const thread = ideasOf(source).filter((idea) => idea.kind !== "aside").map((idea) => idea.text);
  const asides = asidesOf(source);
  return (thread.length ? `\nWHAT THIS PART COVERS (every one is taught): ${thread.join("; ")}` : "") +
    (asides.length ? `\nASIDES IN THIS PART (boxes beside the main text; each is taught too):\n` +
      asides.map((a) => `  - ${a.title}: ${a.text.slice(0, 200)}`).join("\n") : "");
}

export function sectionRequest(section: Section, count: number, written: WrittenSection[], note?: string): string {
  // Sections are written a few at a time: the one just before this may still be on its way.
  const last = written.find((w) => w.n === section.n - 1);
  const tail = last ? last.text.slice(-1500) : "";
  const opening = section.n === 1;
  return [
    written.length
      ? `Written so far: ${written.map((w) => `section ${w.n} "${w.title}"`).join(", ")}.`
      : opening ? "Nothing is written yet: this is the start of the lecture." : "",
    ...(last ? [`Section ${last.n} ended like this:`, `  ...${tail}`, ""]
      : opening ? [] : [`Section ${section.n - 1} is being written at the same time as this one (its topic is in the ` +
        "outline of sections).", ""]),
    `Now write SECTION ${section.n} of ${count}` + (section.n === count ? " (the last: the lecture ends with it)" : "") +
      (section.parts.length ? `, which remakes part${section.parts.length > 1 ? "s" : ""} ${section.parts.join(", ")} of the reference`
        : section.questionsOnly ? ", which takes up more of the source's questions, listed below"
        : section.book ? ", which teaches its part of the book, given below" : "") +
      `. Call write_section once, with section: ${section.n} and the full text.`,
    ...(sectionSource(section) ? ["", sectionSource(section)] : []),
    ...(note ? ["", `Your last try at section ${section.n} was sent back: ${note}`] : []),
  ].join("\n");
}

/** The tool for the words between two videos (transitionRequest). */
export const TRANSITION_TOOL = {
  type: "function" as const,
  function: {
    name: "write_transition",
    description: "Save the words that close one video of the lecture and the words that open the next.",
    parameters: {
      type: "object",
      properties: {
        closing: { type: "string", description: "Said at the end of the video that ends here, after its last line." },
        opening: { type: "string", description: "Said at the start of the next video, before its first line." },
      },
      required: ["closing", "opening"],
      additionalProperties: false,
    },
  },
};

/**
 * The request for the words between two videos, once the written transcript has decided where one ends
 * (topics.nextVideos): the close of the one and the opening of the next, each watched on its own.
 */
export function transitionRequest(ending: { index: number; minutes: number; titles: string[]; tail: string },
  next: { title: string; head: string }): string {
  return [
    `The lecture is watched as separate videos, each on its own, perhaps on another day. Video ${ending.index} ` +
      `(about ${Math.round(ending.minutes)} minutes; ${ending.titles.join(", ")}) ends here, and video ${ending.index + 1} ` +
      `starts with "${next.title}".`,
    "",
    `Video ${ending.index} ends like this:`,
    `  ...${ending.tail.slice(-1500)}`,
    "",
    `Video ${ending.index + 1} starts like this:`,
    `  ${next.head.slice(0, 1500)}...`,
    "",
    `Write the words that CLOSE video ${ending.index} (said after its last line) and the words that OPEN video ` +
      `${ending.index + 1} (said before its first line), as you judge best for the learning. Do not teach again ` +
      "what the videos teach, and do not say how many videos there are. Call write_transition once.",
  ].join("\n");
}

/** The source's own questions in the transcript, for the video's writer (shown on the stage as it judges best). */
function questionRules(questions: BookQuestion[]): string[] {
  if (!questions.length) return [];
  return [
    "",
    `THE SOURCE'S QUESTIONS (${questions.length}), as the book prints them, for when you put one on the stage (a`,
    'question op; "from_book" with its id):',
    ...questions.map(questionLine),
  ];
}

/** How the video's beats say the transcript: by its numbered lines (lines.ts), never copied out again. */
export const LINES_RULES = [
  "THE TRANSCRIPT IS WRITTEN, and its sentences are NUMBERED (\"12| ...\"). The lecture's narration is exactly",
  "this transcript, in order: each beat says one or two consecutive sentences, and names them by number instead of",
  "writing them out: {\"lines\": [12, 13], \"do\": [...]} (no \"say\": the words are filled in from the transcript).",
  "Use every line of the section once, in order. Give each chapter \"section\": the number of the section it",
  "speaks (a section may take several chapters). Your work is the picture: for each beat the operations that show",
  "what is being said (a sketch or preset built and revealed step by step, a graph, a define card, a question on",
  "the stage when the transcript asks the class one, then the answer; work lines for each step of a problem as it",
  "is said; the problem op when a problem is read out), as you judge best for the learning.",
];

/** The beat script's rules when a transcript has been written: its narration is the transcript, by line number. */
export function fromTranscriptPrompt(written: WrittenSection[], questions: BookQuestion[] = []): string {
  return [
    ...questionRules(questions),
    "",
    ...LINES_RULES,
    "",
    ...written.map((s) => `SECTION ${s.n} (${s.title}):\n${numberedSection(s)}`),
    "",
  ].join("\n");
}

/**
 * One section as its own video request carries it (model.ts, the chapters of each section written at the same
 * time): its numbered transcript, and only its own questions -- not the whole lecture again in every request.
 */
export function sectionForVideo(section: WrittenSection, questions: BookQuestion[] = []): string {
  return [
    ...questionRules(questions),
    "",
    ...LINES_RULES,
    "",
    `SECTION ${section.n} (${section.title}):`,
    numberedSection(section),
  ].join("\n");
}

function norm(sentence: string): string {
  return sentence.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

export function sentencesOf(text: string): string[] {
  return text.split(/(?<=[.?!।])\s+|\n+/).map((s) => s.trim()).filter((s) => norm(s).length > 3);
}

/**
 * Which of the given sections' sentences no beat says (compared letters and digits only). A part of a long
 * lecture is checked against the sections its chapters name.
 */
export function unsaidSentences(script: unknown, written: WrittenSection[], only?: number[]): { n: number; missing: string[]; total: number }[] {
  const chapters = ((script as { chapters?: { section?: unknown; beats?: { say?: unknown }[] }[] })?.chapters ?? []);
  const said = norm(chapters.flatMap((c) => (c.beats ?? []).map((b) => String(b?.say ?? ""))).join(" "));
  const wanted = only ?? written.map((s) => s.n);
  return written
    .filter((s) => wanted.includes(s.n))
    .map((s) => {
      const sentences = sentencesOf(s.text);
      return { n: s.n, total: sentences.length, missing: sentences.filter((line) => !said.includes(norm(line))) };
    });
}

/** The sections a part of the script names ("section" on its chapters). */
export function sectionsOf(script: unknown): number[] {
  const chapters = ((script as { chapters?: { section?: unknown }[] })?.chapters ?? []);
  return [...new Set(chapters.map((c) => Number(c?.section)).filter((n) => Number.isFinite(n) && n > 0))];
}

/** An error for a script whose narration leaves out more than a tenth of its sections' transcript, or null. */
export function transcriptProblem(script: unknown, written: WrittenSection[], only?: number[]): string | null {
  if (!written.length) return null;
  const sections = only ?? written.map((s) => s.n);
  if (only && !sections.length) {
    return "Give each chapter \"section\": the number of the transcript section it speaks.";
  }
  const gaps = unsaidSentences(script, written, sections).filter((g) => g.missing.length > g.total * 0.1);
  if (!gaps.length) return null;
  return gaps.map((g) => {
    const own = linesOf(written.find((w) => w.n === g.n)?.text ?? "");
    const numbers = g.missing.map((m) => own.indexOf(m) + 1).filter((k) => k > 0);
    return `Section ${g.n}: ${g.missing.length} of ${g.total} transcript sentences are not said` +
      (numbers.length ? ` (lines ${numbers.slice(0, 12).join(", ")}${numbers.length > 12 ? ", ..." : ""})` : "") + ", e.g. " +
      g.missing.slice(0, 2).map((m) => `"${m.slice(0, 90)}"`).join("; ") +
      ". Every line of the transcript is said, in order, one or two a beat ({\"lines\": [n]}).";
  }).join("\n");
}
