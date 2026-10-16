/**
 * The prompts of the transcription, as named parts (parts.ts):
 *
 *   planPrompt     one call: the whole book as blocks -> lectures (block ids) and their learning goals
 *   lecturePrompt  one call per lecture, in order: its transcript, from its blocks and goals, with every lecture
 *                  before it given whole (what the student has already been taught)
 *   patchPrompt    one call per lecture that left a goal or a block out: the sentences that teach them, and where
 *
 * There is no length ceiling anywhere: the planner is told how long a lecture is meant to be, as context; a writer
 * is told to teach everything it is given, and to stop when it has.
 */

import { blocksJson, bookWords, kindOf, type Block } from "../source/blocks";
import { numbered } from "../source/book";
import { goalLine, type Lecture } from "../plan";
import { NARRATION_EXAMPLES, classVoicePlanned, languagePrompt, type Language } from "./texts";
import { part, type Part, type Prompt } from "./parts";

// ─── Plan ────────────────────────────────────────────────────────────────────────────────────────────────────────

export function planPrompt(blocks: Block[], lectureMinutes: number, subject?: string): Prompt {
  const words = bookWords(blocks);
  const figures = blocks.filter((b) => kindOf(b.type) === "figure").length;
  return {
    system: [
      part("role", "Role", "rules", [
        "You are an experienced teacher planning a book chapter as a series of video lectures, before any of them is",
        "written. You divide the chapter into LECTURES by what is learned, and you list each lecture's LEARNING GOALS.",
      ]),
      part("segment", "How to divide it", "rules", [
        "HOW TO DIVIDE THE BOOK INTO LECTURES:",
        "  - A lecture is a unit a student sits down to learn: one topic and everything it needs, with a beginning, a",
        "    middle and an end. Never cut an idea, an explanation, a worked example or a figure away from the text that",
        "    explains it. Cut where one topic is complete and the next begins.",
        "  - Every block of the book is taught in exactly one lecture, except the book's furniture (QR codes, \"scan",
        "    for e-content\", page headers, reprint and copyright notes), which you list in skipped.",
        "  - A box beside the text (\"Do you know?\", \"Activity\"), a figure and its caption go in the lecture whose topic they serve.",
        "  - The book's questions (exercises, in-text questions, multiple-choice questions) go in the lecture that teaches the idea each tests, so it",
        "    is asked right after that idea is taught.",
        "  - Teach in the book's order unless another order is clearly better for learning.",
      ]),
      part("map", "How to map the goals", "rules", [
        "HOW TO MAP EACH LECTURE'S LEARNING GOALS:",
        "  - goal: what the student will be able to do, one sentence in a student's words, about understanding, not",
        "    reciting (\"Explain why ...\", \"Tell ... apart from ...\", \"Use ... to work out ...\").",
        "  - blocks: the ids of this lecture's blocks that teach it. Together the goals cover all of the lecture's",
        "    teaching blocks: every heading's idea, every bold term, every box and every figure.",
        "  - misconception: the wrong idea students usually hold (\"heavier things fall faster\"); \"\" when there is none.",
        "  - hook: something from a student's everyday life in India to start from (cricket, trains, the monsoon, the",
        "    kitchen, the market, a festival), true to the idea.",
      ]),
      part("output", "How to answer", "rules", [
        "Answer with Datalab's block ids only (\"/page/3/Text/7\"), never the book's text: the text is taken from the book by its id.",
        "Facts come from the book only. Call plan_lectures once.",
      ]),
    ],
    user: [
      ...(subject ? [part("subject", "Subject", "context", `The subject is ${subject}.`)] : []),
      part("length", "How long a lecture is", "context", [
        `HOW LONG A LECTURE IS: each lecture is one video of about ${lectureMinutes} minutes, watched on its own. A book`,
        `is taught at roughly its own length, about 100 words of the book a minute, so a lecture usually takes about`,
        `${lectureMinutes * 100} words of the book; let the topics decide, not the count. This chapter has ${words} words`,
        `in ${blocks.length} blocks (${figures} figures): about ${Math.max(1, Math.round(words / (lectureMinutes * 100)))} lecture(s).`,
      ]),
      part("book", "The book as JSON", "book", [
        "THE BOOK as Datalab read it: every block in page order, one JSON object a line (Datalab's id, block_type and",
        "html; a figure has figure_shows, what it shows):",
        blocksJson(blocks),
      ]),
      part("ask", "Request", "ask", "Divide it into lectures and map their goals now (plan_lectures): every block in one lecture or in skipped."),
    ],
  };
}

// ─── Lecture ─────────────────────────────────────────────────────────────────────────────────────────────────────

/** How a great teacher tells it: v1's rules, with the plan's story and the length ceiling taken out. */
const TELLING = [
  "HOW A GREAT TEACHER TELLS IT:",
  "  - The lecture is ONE story with ONE question the student wants answered, asked near the start and answered by",
  "    the end. Every part moves it forward.",
  "  - Make them guess before you tell: ask, let them think, then answer. In fresh words each time, never a stock",
  "    pause phrase.",
  "  - Concrete before abstract: a scene, an object, a number made tangible (\"as heavy as 40 school bags\"), then the",
  "    term. Everyday life in India is the best source: trains, cricket, the monsoon, the kitchen, the market.",
  "  - Name the wrong idea students usually hold (the goal says it), let them hold it for a moment, then show why it",
  "    fails.",
  "  - Vary the rhythm: a short line after a long explanation. Not every sentence is a fact. Never read out a list.",
  "  - A figure, a map or a table is shown at its moment: say what it shows and why it matters there, and point at the",
  "    one or two things to look at. The book's questions are asked right after the idea they test, as a check-in,",
  "    then answered in full, every choice of a multiple-choice question explained.",
  "  - The story never changes the facts: no invented events, people, quotes, numbers or dates presented as history or",
  "    science. A scene you imagine is said as imagined (\"imagine...\", \"सोचो...\").",
  "  - When everything is taught, stop: no padding, no extra self-checks or study tips, no summary of what was just said",
  "    except the short close of the lecture.",
];

export function lectureSystem(language: Language, subject?: string): Part[] {
  return [
    part("role", "Role", "rules", [
      "You write the complete spoken TRANSCRIPT of one video lecture of a series: every word the teacher says, in order.",
      "A later step turns it into the video sentence for sentence and adds the pictures, so everything the student hears",
      "is in these words.",
    ]),
    part("matters", "What matters", "rules", [
      "WHAT MATTERS above all:",
      "  1. LEAVE NOTHING OUT. Everything in the blocks of the book you are given is taught: every heading's idea, every",
      "     definition and bold term, every fact, number and example, every box, every figure, every book question. Take",
      "     the time each needs; nothing about the length is counted. Report each goal you taught in goals_taught and",
      "     each block in blocks_taught: what is missing is written in afterwards, where it fits less well.",
      "  2. THE QUALITY OF THE LEARNING: the student truly understands and remembers.",
      "  3. TOLD AS A STORY, never a list of facts read out.",
      "  4. ONE SERIES. The lectures before this one are given to you whole: the student has watched them. Never teach",
      "     again what they taught; recall it in a sentence when this lecture needs it, and build on it. Open by",
      "     picking up from where the last lecture ended (a short look back), and end with a short close of this",
      "     lecture and what comes next.",
    ]),
    part("telling", "How to tell it", "rules", TELLING),
    part("voice", "Voice", "rules", classVoicePlanned(language)),
    part("examples", "Narration examples", "rules", NARRATION_EXAMPLES),
    part("use", "How the transcript is used", "rules", [
      "HOW THE TRANSCRIPT IS USED (facts, not rules of style):",
      "  - A voice speaks it, so write only the words said: no headings, bullet lists, [brackets] or stage directions,",
      "    and say formulas and symbols the way they are spoken.",
      "  - Teach the subject only. The book's furniture is not content: never mention its QR codes, logos, page",
      "    numbers, page layout, reprint or copyright notes.",
      ...(subject ? [`  - The subject is ${subject}.`] : []),
    ]),
    part("language", "Language", "language", languagePrompt(language)),
  ].filter((p) => p.text);
}

export function lecturePrompt(o: {
  lecture: Lecture; lectures: Lecture[]; blocks: Block[]; system: Part[];
  previous: { n: number; title: string; text: string }[]; note?: string;
}): Prompt {
  const { lecture, lectures } = o;
  const byId = new Map(o.blocks.map((b) => [b.id, b]));
  const own = lecture.blocks.map((id) => byId.get(id)).filter((b): b is Block => !!b);
  const user: Part[] = [
    part("series", "The series", "context", [`THE SERIES (${lectures.length} lecture${lectures.length > 1 ? "s" : ""}); you write lecture ${lecture.n}:`,
      ...lectures.map((l) => `  Lecture ${l.n}${l.n === lecture.n ? " (THIS ONE)" : ""}: ${l.title}`)]),
    part("previous", "Lectures already given", "context", o.previous.length
      ? ["THE LECTURES ALREADY GIVEN, whole (the student has watched them: never teach their content again; recall it in",
        "a sentence where this lecture needs it):",
        ...o.previous.map((p) => `\n=== LECTURE ${p.n}: ${p.title} ===\n${p.text}`)]
      : "This is the first lecture of the series: nothing has been taught yet."),
    part("later", "Later lectures", "context", lectures.filter((l) => l.n > lecture.n).length
      ? ["THE LECTURES AFTER THIS ONE teach these (not yours: do not teach or preview them):",
        ...lectures.filter((l) => l.n > lecture.n).flatMap((l) => [`  Lecture ${l.n}: ${l.title}`,
          ...l.goals.map((g) => `    - ${g.goal}`)])]
      : "This is the last lecture of the series."),
    part("goals", "This lecture's goals", "goals", [`THIS LECTURE: ${lecture.title}${lecture.why ? ` (${lecture.why})` : ""}`,
      "Its learning goals, every one (report each in goals_taught with the numbers of the sentences, counted from 1 in",
      "your text, that teach it):", ...lecture.goals.map((g) => `  ${goalLine(g)}`)]),
    part("book", "This lecture's book blocks", "book", [
      `THE BOOK'S BLOCKS THIS LECTURE TEACHES (${own.length}), as Datalab read them, in order. Teach every one; report them in blocks_taught:`,
      blocksJson(own),
    ]),
    part("ask", "Request", "ask", `Write lecture ${lecture.n} now: its complete transcript, leaving nothing in its blocks out. ` +
      "Call write_lecture_transcript once."),
  ];
  if (o.note) user.push(part("retry", "Why the last try was sent back", "retry", `Your last try was sent back: ${o.note}`));
  return { system: o.system, user };
}

// ─── Patch ───────────────────────────────────────────────────────────────────────────────────────────────────────

export function patchPrompt(text: string, missing: { goals: string[]; blocks: Block[] }): Prompt {
  return {
    system: [part("system", "Patcher's rules", "rules", "You add sentences to a lecture's transcript, in its own voice and language, " +
      "so that it teaches what it left out.")],
    user: [
      part("lecture", "The lecture, numbered", "context", ["A lecture's transcript, its sentences numbered:", numbered(text)]),
      ...(missing.goals.length ? [part("goals", "Goals it did not teach", "goals", ["It did not teach these goals:", ...missing.goals.map((g) => `  ${g}`)])] : []),
      ...(missing.blocks.length ? [part("book", "Blocks it did not teach", "book", ["It did not teach these blocks of the book:", blocksJson(missing.blocks)])] : []),
      part("ask", "Request", "ask", "For each, write the sentences that teach it, from the book's facts only, and say after which " +
        "sentence they go: where they fit the flow, not all at the end. Call write_patches once."),
    ],
  };
}

// ─── Tools ───────────────────────────────────────────────────────────────────────────────────────────────────────

export const LECTURE_TOOL = {
  type: "function" as const,
  function: {
    name: "write_lecture_transcript",
    description: "Save one lecture's spoken transcript. The text is only what the teacher says, in paragraphs: no stage " +
      "directions, no headings, no brackets, no markdown.",
    parameters: {
      type: "object",
      properties: {
        title: { type: "string", description: "The lecture's title." },
        text: { type: "string", description: "The lecture's full spoken transcript, paragraph by paragraph." },
        goals_taught: {
          type: "array",
          items: {
            type: "object",
            properties: {
              goal: { type: "string", description: "The goal's id (\"g4\")." },
              lines: { type: "array", items: { type: "integer" }, description: "The numbers of the sentences that teach it, counted from 1 in your text." },
            },
            required: ["goal", "lines"],
            additionalProperties: false,
          },
        },
        blocks_taught: { type: "array", items: { type: "string" }, description: "The Datalab ids of the book's blocks you taught (\"/page/3/Text/7\")." },
      },
      required: ["title", "text", "goals_taught", "blocks_taught"],
      additionalProperties: false,
    },
  },
};

export const PATCH_TOOL = {
  type: "function" as const,
  function: {
    name: "write_patches",
    description: "Save the sentences that teach what the lecture left out, each with the sentence it follows.",
    parameters: {
      type: "object",
      properties: {
        patches: {
          type: "array",
          items: {
            type: "object",
            properties: {
              after_line: { type: "integer", description: "The number of the sentence the words follow." },
              text: { type: "string", description: "The words to add: only what the teacher says." },
              covers: { type: "array", items: { type: "string" }, description: "The goal and block ids these words teach (\"g4\", \"/page/3/Text/7\")." },
            },
            required: ["after_line", "text", "covers"],
            additionalProperties: false,
          },
        },
      },
      required: ["patches"],
      additionalProperties: false,
    },
  },
};
