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
import { topicLabel, type Topic } from "./topics";
import type { DocumentManifest } from "./document";
import type { Language } from "./lecture";
import { SOLVING_STEPS } from "./solving";
import { bookQuestions, questionLine, questionWords, unexplainedQuestions, type BookQuestion } from "./questions";

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
function bookBlocks(markdown: string): string[] {
  return markdown
    .replace(/^#+\s*page \d+\s*$/gim, "")
    .split(/\n\s*\n|\n(?=#)/)
    .map((b) => b.trim())
    .filter((b) => b && !/^#+\s*$/.test(b));
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
  /** The lecture as a series of micro-lectures (topics.ts); one topic, or none, is one lecture as before. */
  topics?: Topic[];
}): string {
  const { sections, minutes, hasReference } = options;
  const total = sections.reduce((n, s) => n + s.words, 0);
  const series = (options.topics?.length ?? 0) > 1 ? options.topics! : [];
  return [
    "You write the complete spoken TRANSCRIPT of a video lecture: every word the teacher says, in order. It is",
    "written first, in full, before any picture: a later step turns it into the video, sentence for sentence. So",
    "everything the student needs must be in these words.",
    "",
    `The lecture runs about ${minutes} minutes: about ${total} words in ${sections.length} sections. Each request asks`,
    "for ONE section, and gives the end of the section before it: write that one section, in one write_section",
    "call, picking up where the last one stopped. Each section must reach its length (the tool refuses a short",
    "one): reach it by explaining more, never by padding.",
    "",
    ...(series.length ? [
      `A SERIES OF ${series.length} MICRO-LECTURES. The lecture is made as ${series.length} separate videos of 20-30 minutes, ` +
        "one per topic, each watched on its own, perhaps on another day:",
      ...series.map((t) => `  Lecture ${t.index}: sections ${t.sections[0]}-${t.sections[t.sections.length - 1]}` +
        `${t.title ? ` ("${t.title}")` : ""}, about ${Math.round(t.minutes)} min.`),
      "Each micro-lecture is complete and STRUCTURED: it OPENS (in its first section) with what it covers, a short",
      "recall of what the lecture before taught, why this topic matters, and what the student will be able to do by",
      "its end; then it TEACHES, as deeply and slowly as always (every idea, examples, questions for the class, worked",
      "problems from the very basics); and it CLOSES (in its last section) with the key points, a few quick",
      "questions for the student to check themselves (each answered after a pause), and one sentence on what the",
      "next lecture covers. Within a lecture, sections flow on from each other as one class.",
      "",
    ] : []),
    hasReference
      ? [
          "MIMIC THE REFERENCE LECTURE (a YouTube video; its words for each section are given below). Keep its order,",
          "its flow and its way of teaching: the same topics, the same examples and analogies, the same solved",
          "problems with the same numbers, and the SAME QUESTIONS it asks the students (ask them the same way,",
          "then give the time to think, then the answer and why). Where it goes fast, you go slowly: say everything",
          "it says, and explain each step it skips. Keep its teacher's way of talking, its tricks and its repeated",
          "rules; say them clearly and completely, in more detail.",
          "Its words are YouTube's automatic captions of a live class: many are misheard (\"पुलिस\" is pulley,",
          "\"Bigg Boss\" or \"एक्सेस\" may be forces or axes, numbers come out garbled). Work out what the teacher meant",
          "from the physics and use the right words and numbers. Leave out channel talk (subscribe, like, the next",
          "video) and anything about the recording.",
        ].join("\n")
      : sections.some((s) => s.book)
        ? [
            "TEACH THE BOOK (its text for each section is given below). A book only states things; the teacher makes",
            "them understood. So you WRITE what a good teacher adds, the way the best YouTube teachers do:",
            "  - Cover every idea of the section's text, in its order: every definition, law, fact, figure, table,",
            "    solved example and in-text question. Leave nothing out, and add nothing off the syllabus.",
            "  - Explain each idea slowly in easy words: what it means, each term in it, why it is so, and the idea",
            "    again in other words. Never read the book's sentences out word for word: say them your own way.",
            "  - EXAMPLES the book does not give: for each important statement, two or three everyday examples",
            "    (\"मान लो...\", \"जैसे...\": a bus braking, a ball on a table, the ceiling fan, cricket, the kitchen).",
            "  - QUESTIONS for the class, several in every section: ask, give time (\"सोचो...\"), then the answer and",
            "    why, and why a common wrong answer is wrong.",
            "  - THE BOOK'S OWN QUESTIONS (listed under each section: its in-text questions, exercises, MCQs): explain",
            "    EVERY ONE, in the book's order, none skipped, none merged. For each: first say its number (\"प्रश्न",
            "    4.1\", \"Question 4.1\"), then read the question out as the book has it; say what it is really asking and which idea of the chapter it tests; then, for a",
            "    multiple-choice question, take EVERY option in turn, A, B, C, D (\"Option A, ... यह गलत है क्योंकि",
            "    ...\"; \"Option B, ... यही सही है, क्योंकि ...\"): what the option says and exactly why it is right or",
            "    wrong (the trap in it, the mistake that leads a student to pick it); then say the answer again with",
            "    its reason. For a question to answer: think it through out loud and give the full answer the way",
            "    an exam wants it; a numerical is solved from the very basics (below). Then a one-line tip to",
            "    remember it.",
            "  - PROBLEMS: in a maths or science chapter, solve numericals from the very basics (below). Use the",
            "    book's solved examples, and make up one or two more with easy numbers where the book has none.",
            "  - Where the text shows [FIGURE figN: caption], talk the class through that figure (\"इस figure में",
            "    देखो...\"): the video draws it there, built in Manim from the figure. Build every diagram out loud, piece by piece.",
            "  - Tie each new idea to the one before, and end each section with a short recap.",
          ].join("\n")
        : "TEACH THE CONTENT in order, section by section, from its first idea to its last, explaining each idea " +
          "in detail with everyday examples, questions for the class and worked problems.",
    "",
    "TEACH EXACTLY LIKE A REAL TEACHER TALKING TO A CLASS, NOT LIKE A BOOK OR AN ARTICLE. Write it the way it",
    "would be spoken in front of students, in easy everyday language:",
    "  - Talk to the students all the time: \"बच्चों\", \"देखो\", \"ध्यान से सुनो\", \"मेरी बात समझो\", \"अब यहां देखो\".",
    "  - Check in after every idea: \"ठीक है?\", \"समझ में आया?\", \"क्लियर है?\", \"अच्छा ठीक है, आगे बढ़ते हैं\".",
    "  - REPEAT. Say every important rule two or three times, in slightly different words, and once more when it is",
    "    used: \"Tension हमेशा point से दूर जाती है। Away from the point. फिर से बोलता हूं, tension हमेशा away from",
    "    the point बनाओ।\" Repeating is how a class remembers; it is never padding here.",
    "  - Go in small steps, one small idea per sentence. Short sentences. Never two new things in one sentence.",
    "  - Give memory tricks and everyday pictures: \"जहां tension बनानी है, वहां बैठ जाओ और हाथ खोल दो; जिधर हाथ",
    "    खुलेगा, उधर tension\"; \"मान लो यहां एक 5 kg का block रखा है...\"; a bus braking, a ball on a table.",
    "  - Build every diagram out loud, piece by piece, as if drawing on the board: \"यहां एक block है। इस पर नीचे की",
    "    तरफ क्या लगेगा? Weight, m g। अब surface इसे ऊपर push करेगा, normal reaction, N। और कोई force? नहीं।\"",
    "  - Ask the class often and wait: \"बताओ, इस पर कौन-कौन सी forces लगेंगी? सोचो।\" Then answer, and say why",
    "    (and why a common wrong answer is wrong: \"यह मत कहना कि ऊपर वाला block इसे mg से दबा रहा है...\").",
    "  - Solve numericals slowly and completely, the way SOLVING below says, every step out loud. Then \"समझ में",
    "    आया? अब एक और question देखते हैं\".",
    "  - Say every formula and symbol in words (\"F equals m a\", \"m g sin theta\"), since it is heard, not read.",
    ...SOLVING_STEPS.map((line) => `  ${line}`),
    "  - Close each section with a short recap (\"तो आज हमने क्या देखा...\"), and open the next by linking back.",
    "",
    "EXAMPLE of the voice (the style only; not the content to use):",
    "  \"अच्छा बच्चों, अब बात करते हैं normal reaction की। Normal का मतलब होता है perpendicular, यानी surface के",
    "  बिल्कुल सीधा, ninety degree पर। ठीक है? मान लो table पर एक book रखी है। Book table को नीचे दबा रही है।",
    "  तो table क्या करेगी? Table book को ऊपर की तरफ push करेगी। यही push normal reaction है। फिर से सुनो, normal",
    "  reaction हमेशा surface के perpendicular होता है। Surface सीधी है तो ऊपर, surface झुकी हुई है तो उसके",
    "  perpendicular, तिरछा। समझ में आया? चलो, अब एक inclined plane पर देखते हैं।\"",
    "",
    options.languageRules.trim(),
    "",
    "Only speech: no [brackets], no stage directions (\"(draws a diagram)\"), no headings, no bullet lists, no",
    "markdown. When a picture helps, just say what to look at (\"इस diagram में देखो...\"); the pictures are added later.",
    "",
    // An outline only: each section's own text and questions come with the request for it (sectionSource), so
    // these instructions are the same for every section -- one prefix the provider can cache -- and a request does
    // not carry the whole book.
    "THE SECTIONS, in order (each request gives that section's own text):",
    ...sections.map((s) => `  SECTION ${s.n}: about ${s.words} words (${s.minutes} min)` +
      (s.parts.length ? `, remaking part${s.parts.length > 1 ? "s" : ""} ${s.parts.join(", ")} of the reference`
        : s.questionsOnly ? ", more of the book's questions from the section before"
        : s.book ? `, teaching ${headingIn(s.source) || "its part of the book"}` : "") +
      (s.questions?.length ? ` (${s.questions.length} of the book's questions)` : "")),
    "",
    ...(options.content.trim() ? ["THE CONTENT (notes, a chapter) to teach from:", options.content.slice(0, 60000)] : []),
  ].join("\n");
}

const DEVANAGARI = /[ऀ-ॿ]/;
const EXAMPLE_CUES = /मान लो|मान लीजिए|जैसे|उदाहरण|example|suppose|imagine|let us say|say you|think of/i;
const ROMAN_HINDI = /\b(hai|hain|hota|hoti|matlab|yaani|kya|nahi|aur|toh|lekin|isliye|dekho|samjho|chalo)\b/gi;

/** Why a written section is refused, or null when it is accepted. */
/**
 * A sentence that reads out one of the book's questions or one of its options ("Option B, newton."): said as the
 * book prints it, on purpose, so the checks for copying and for too much English leave it alone.
 */
function readsQuestion(line: string, questions: BookQuestion[]): boolean {
  const said = norm(line);
  if (!said || !questions.length) return false;
  return questions.some((q) => {
    const asked = norm(q.text);
    return (asked.length > 10 && (asked.includes(said) || said.includes(asked.slice(0, 60)))) ||
      q.choices.some((c) => norm(c).length >= 3 && said.includes(norm(c)));
  });
}

export function sectionProblem(text: string, section: Section, language: Language): string | null {
  const words = text.split(/\s+/).filter(Boolean).length;
  const questions = section.questions ?? [];
  if (words < section.words * 0.9) {
    return `Section ${section.n} has ${words} words; it needs about ${section.words} (at least ${Math.round(section.words * 0.9)}). ` +
      "Write it again at full length: explain each statement more (the meaning of each term, an example or two, " +
      "why it is so, the idea again in other words), ask the class a question, and work every step of each problem.";
  }
  if (!section.parts.length) {
    // Taught, not read out: a section of a book (or of typed notes) must ask the class and give examples.
    const asked = (text.match(/[?？]/g) ?? []).length;
    if (asked < 2) {
      return `Section ${section.n} asks the class ${asked} question${asked === 1 ? "" : "s"}: ask at least two (\"बताओ...?\", ` +
        "\"सोचो, ...?\"), give a moment to think, then answer and say why.";
    }
    if (section.book) {
      // The video stage refuses narration that reads the book word for word: caught here, while it is cheap.
      const book = norm(section.source);
      const copied = sentencesOf(text).filter((line) => norm(line).length > 40 && book.includes(norm(line)) &&
        !readsQuestion(line, questions));
      if (copied.length > 1) {
        return `Section ${section.n} reads ${copied.length} sentences of the book word for word (e.g. "${copied[0].slice(0, 90)}"): ` +
          "say each idea in your own words, the way you would explain it to the class.";
      }
    }
    const skipped = unexplainedQuestions(text, section.questions ?? []);
    if (skipped.length) {
      return `Section ${section.n} does not explain the book's ${skipped.map((s) => s.what).join("; ")}. Explain every ` +
        "question of the section: say its number first (\"प्रश्न 4.1\"), read it, what it asks, then every option in " +
        "turn (\"Option A, ...\") and why it is right or wrong, then the answer and why.";
    }
    // A section that is mostly the book's exercises explains questions; it need not bring examples of its own.
    const askedWords = questions.reduce((n, q) => n + questionWords(q), 0);
    if (!EXAMPLE_CUES.test(text) && askedWords < section.words * 0.5) {
      return `Section ${section.n} gives no example: explain its ideas with everyday examples (\"मान लो...\", ` +
        "\"जैसे...\", \"for example...\").";
    }
  }
  if (/\[[^\]]*\]|^#|^\s*[-*•]\s/m.test(text)) {
    return `Section ${section.n} has brackets, headings or bullet points: write only what the teacher says, in paragraphs.`;
  }
  if (language === "hinglish") {
    const sentences = text.split(/(?<=[.?!।])\s+/).filter((s) => s.trim());
    const english = sentences.filter((s) => !DEVANAGARI.test(s) && !readsQuestion(s, questions)).length;
    if (english > sentences.length * 0.25) {
      return `Section ${section.n} is mostly English (${english} of ${sentences.length} sentences). It is Hinglish: ` +
        "simple Hindi in Devanagari with the subject's terms in English.";
    }
    const roman = text.match(ROMAN_HINDI) ?? [];
    if (roman.length >= 3) {
      return `Section ${section.n} writes Hindi in Latin letters (${[...new Set(roman.map((r) => r.toLowerCase()))].slice(0, 5).join(", ")}): ` +
        "write the Hindi words in Devanagari; the voice reads Latin letters as English.";
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

/**
 * Whether a refusal can be mended by adding to the end of the section rather than writing it again: too short, too
 * few questions for the class, no example, or some of the book's questions not explained. Copying the book, or the
 * wrong language, needs the section written again.
 */
export function repairable(problem: string): boolean {
  return /has \d+ words; it needs|asks the class \d+ question|gives no example|does not explain the book's/.test(problem);
}

/** The request that mends a refused section by adding to it (repairable): only the new paragraphs, at its end. */
export function repairRequest(section: Section, count: number, text: string, problem: string): string {
  const words = text.split(/\s+/).filter(Boolean).length;
  const more = Math.max(0, Math.round(section.words * 0.95) - words);
  return [
    `SECTION ${section.n} of ${count} is written, and it ends like this:`,
    `  ...${text.slice(-1500)}`,
    "",
    `It was refused: ${problem}`,
    "",
    "Do NOT write the section again. Write ONLY the new paragraphs that mend this, to be added at its end, " +
      "carrying on naturally from where it stops, in the same voice and language, without repeating anything it " +
      "already says" + (more > 0 ? `: about ${more} more words (it has ${words}, it needs about ${section.words}),` : ",") +
      " teaching more of the section's ideas in depth: more examples, a question for the class, a worked step.",
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
    ? `\nQUESTIONS IN THIS SECTION (explain all ${section.questions.length}, every option):\n` +
      section.questions.map(questionLine).join("\n")
    : "";
  if (section.parts.length) {
    return `WHAT THE REFERENCE SAYS IN PART${section.parts.length > 1 ? "S" : ""} ${section.parts.join(", ")}:\n` +
      section.source.slice(0, 12000);
  }
  if (section.questionsOnly) return `THE BOOK'S TEXT THESE QUESTIONS COME FROM:\n${section.source.slice(0, 6000)}${questions}`;
  if (section.book) return `THE PART OF THE BOOK THIS SECTION TEACHES:\n${section.source.slice(0, 12000)}${questions}`;
  return "";
}

export function sectionRequest(section: Section, count: number, written: WrittenSection[], note?: string,
  topic?: Topic): string {
  // Sections are written a few at a time: the one just before this may still be on its way.
  const last = written.find((w) => w.n === section.n - 1);
  const tail = last ? last.text.slice(-1500) : "";
  const opening = section.n === 1;
  return [
    written.length
      ? `Written so far: ${written.map((w) => `section ${w.n} "${w.title}"`).join(", ")}.`
      : opening ? "Nothing is written yet: this is the opening of the lecture." : "",
    ...(last ? [`Section ${last.n} ended like this:`, `  ...${tail}`, ""]
      : opening ? [] : [`Section ${section.n - 1} is being written at the same time as this one. Open with one short ` +
        "sentence that links back to the topic before (named in the outline of sections), without " +
        "repeating it, and without a greeting or an introduction to the lecture.", ""]),
    `Now write SECTION ${section.n} of ${count} (about ${section.words} words, at least ` +
      `${Math.round(section.words * 0.9)}${section.parts.length ? `; it remakes part${section.parts.length > 1 ? "s" : ""} ` +
      `${section.parts.join(", ")} of the reference` : section.questionsOnly ? `; it explains the next ` +
      `${section.questions?.length ?? 0} of the book's questions, listed below, ` +
      "each in full, every option in turn, carrying on from the questions before" : section.book ? "; it teaches its part of the book, given below, with your own examples, questions for the class " +
      "and worked problems" +
      (section.questions?.length ? `, and every one of the book's ${section.questions.length} question` +
        `${section.questions.length > 1 ? "s" : ""} listed below explained in full, each option in turn` : "") : ""}).` + (last ? ` Carry on from where section ${last.n} stopped: do not ` +
      "repeat what it said." : "") + ` Call write_section once, with section: ${section.n} and the full text.`,
    ...topicDuties(section, topic),
    ...(sectionSource(section) ? ["", sectionSource(section)] : []),
    ...(note ? ["", `Your last try at section ${section.n} was refused: ${note}`] : []),
  ].join("\n");
}

/** What a section adds when it opens or closes one micro-lecture of a series (topics.ts). */
function topicDuties(section: Section, topic?: Topic): string[] {
  if (!topic || topic.of < 2) return [];
  const first = topic.sections[0] === section.n;
  const last = topic.sections[topic.sections.length - 1] === section.n;
  const out: string[] = [];
  if (first) {
    out.push("", `This section OPENS ${topicLabel(topic)}, a video of its own. Begin it as a lecture begins: say ` +
      `it is lecture ${topic.index} of ${topic.of}${topic.title ? ` and what it is about` : ""}; ` +
      (topic.index > 1 ? "recall in two or three sentences what the lecture before taught that this one builds on; "
        : "") +
      "say why this topic matters, with an everyday example; then the three to five things the student will be able " +
      "to do by its end, one short sentence each (\"इस lecture के बाद आप ... कर पाएंगे\"). Then teach. This opening " +
      "comes before the section's own teaching and does not replace any of it.");
  }
  if (last) {
    out.push("", `This section CLOSES ${topicLabel(topic)}. After its teaching, end the lecture: the key points of ` +
      "the whole lecture in four to six short sentences; then three quick questions for the student to check " +
      "themselves, each followed by a moment to think and its answer with the reason; " +
      (topic.index < topic.of ? "then one sentence on what the next lecture covers." : "then a closing line: this is " +
        "the last lecture of the series."));
  }
  return out;
}

/** The book's questions, as the video's writer is told to put them on the stage. */
function questionRules(questions: BookQuestion[]): string[] {
  if (!questions.length) return [];
  return [
    "",
    `THE BOOK'S QUESTIONS (${questions.length}). The transcript explains each; put each one on the stage where it is`,
    "read out, marked with its id, with ALL its choices in the book's order (in English on the screen):",
    '  {"op":"question","from_book":"q3","text":"...","choices":["...","...","...","..."],"answer":"B"}',
    "then, on the beats that explain the options, ONE BEAT PER OPTION, in order, each marking the option it talks",
    'about: {"op":"option","choice":"A"} (a wrong one is crossed out, the right one ringed), and the answer\'s beat',
    '{"op":"answer"}. A question to answer (no choices) is a question op with "from_book" and its answer in words;',
    "a numerical one is worked with problem and work ops. The compiler checks every id is asked and every option",
    "marked.",
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
  "is said; the problem op when a problem is read out). The length, the examples and the questions are already in",
  "the transcript; the checks on them follow from it.",
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
