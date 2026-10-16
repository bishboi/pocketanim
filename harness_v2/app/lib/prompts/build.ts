/**
 * The four prompts of the transcription, as parts (parts.ts). Their words are v1's (prompts/texts.ts and v1's
 * transcript.ts, learningmap.ts, storyplan.ts, coverage.ts); what is new is that each piece is named.
 *
 *   learningMapPrompt   one call: the book's items, section by section, into learning goals
 *   storyPlanPrompt     one call per video: its story, and each section's part in it
 *   sectionPrompt       one call per section: its spoken transcript
 *   patchPrompt         one call per goal a section did not report: the sentences that teach it
 */

import { ideasOf, numbered, WORDS_PER_MINUTE, withoutExercises, type Section, type WrittenSection } from "../source/book";
import { questionLine, type BookQuestion } from "../source/questions";
import { goalLine, type LearningMap, type SourceItem } from "../plan/learningmap";
import type { StoryPlan } from "../plan/storyplan";
import { microMinutes } from "../plan/videos";
import {
  LEARNING_MAP_SYSTEM, NARRATION_EXAMPLES, STORY_PLAN_SYSTEM, STORYTELLING_PLANNED, classVoicePlanned, languagePrompt,
  type Language,
} from "./texts";
import { part, type Part, type Prompt } from "./parts";

// ─── Learning map ────────────────────────────────────────────────────────────────────────────────────────────────

export function learningMapPrompt(sections: Section[], items: SourceItem[], subject?: string): Prompt {
  const user: Part[] = [];
  if (subject) user.push(part("subject", "Subject", "context", `The subject is ${subject}.`));
  user.push(part("count", "What to place", "ask",
    `The book's items to teach (${items.length}), section by section, with each section's text:`));
  let budget = 60000;
  for (const section of sections) {
    if (section.questionsOnly) continue;
    const own = items.filter((i) => i.section === section.n);
    const text = section.source.slice(0, Math.max(1500, Math.min(6000, budget)));
    budget -= text.length;
    user.push(part(`items-${section.n}`, `Section ${section.n} items`, "items", [`SECTION ${section.n}`,
      own.length ? own.map((i) => `  ${i.id} [${i.kind}] ${i.text}`).join("\n") : "  (no listed items: its text only)"]));
    user.push(part(`book-${section.n}`, `Section ${section.n} book text`, "book",
      ["  Its part of the book:", text.split("\n").map((line) => `    ${line}`).join("\n")]));
  }
  user.push(part("ask", "Request", "ask", "List the learning goals now (write_learning_map), every item under exactly one goal."));
  return { system: [part("system", "Planner's rules", "rules", LEARNING_MAP_SYSTEM)], user };
}

// ─── Story plan ──────────────────────────────────────────────────────────────────────────────────────────────────

export function storyPlanPrompt(video: { index: number; of: number; sections: Section[] }, map: LearningMap,
  questions: BookQuestion[], subject?: string): Prompt {
  const numbers = new Set(video.sections.map((s) => s.n));
  const before = map.goals.filter((g) => g.section < Math.min(...numbers));
  const after = map.goals.filter((g) => g.section > Math.max(...numbers));
  const words = video.sections.reduce((n, s) => n + s.words, 0);
  const user: Part[] = [];
  if (subject) user.push(part("subject", "Subject", "context", `The subject is ${subject}.`));
  user.push(part("video", "Which video", "ask", `Plan video ${video.index} of ${video.of}.`));
  user.push(part("before", "Earlier videos", "context", before.length
    ? ["Earlier videos teach these (the student has seen them; recall in a sentence, never teach again):",
      ...before.map((g) => `  ${g.goal}`)]
    : "This is the first video of the lecture."));
  user.push(part("length", "Length", "context",
    `Its length: about ${Math.round(words / WORDS_PER_MINUTE)} minutes (${words} spoken words), so plan only what fits.`));
  user.push(part("goals", "Sections and goals", "goals", ["ITS SECTIONS, in order, with the goals each teaches:",
    ...video.sections.flatMap((s) => {
      const goals = map.goals.filter((g) => g.section === s.n);
      return [`  SECTION ${s.n}${s.questionsOnly ? " (the book's questions on the part before)" : ""}`,
        ...(goals.length ? goals.map((g) => `    ${goalLine(g, map.items)}`) : ["    (no goals of its own)"])];
    })]));
  if (questions.length) {
    user.push(part("questions", "Book questions", "questions",
      [`THE BOOK'S QUESTIONS IN THIS VIDEO (${questions.length}; place every one):`, ...questions.map(questionLine)]));
  }
  user.push(part("after", "Later videos", "context", after.length
    ? ["The videos after this one teach (do not teach or preview these):", ...after.map((g) => `  ${g.goal}`)]
    : "This is the last video of the lecture."));
  user.push(part("ask", "Request", "ask", "Call write_story_plan now."));
  return { system: [part("system", "Planner's rules", "rules", STORY_PLAN_SYSTEM)], user };
}

// ─── Section ─────────────────────────────────────────────────────────────────────────────────────────────────────

/** The section writer's system prompt: the same for every section (so the provider caches it). */
export function sectionSystem(sections: Section[], language: Language, subject?: string): Part[] {
  const range = microMinutes();
  return [
    part("role", "Role", "rules", [
      "You write the complete spoken TRANSCRIPT of a video lecture: every word the teacher says, in order. A later",
      "step turns it into the video sentence for sentence and adds the pictures, so everything the student hears is",
      "in these words.",
    ]),
    part("matters", "What matters", "rules", [
      "FOUR THINGS MATTER above all:",
      "  1. THE QUALITY OF THE LEARNING comes first: the student truly understands and remembers. The order of",
      "     explanation, the examples, how deep each idea goes and how a video opens and closes are yours to decide.",
      "     Nothing about your style or length is counted or checked.",
      "  2. TOLD AS A STORY. The student follows a story, never a list of facts read out (rule 4 below says how).",
      `  3. VIDEOS OF ${range.min}-${range.max} MINUTES. A long lecture is watched as several videos of about ${range.min}-${range.max}`,
      `     minutes (a minute is about ${WORDS_PER_MINUTE} spoken words). Where each starts and ends is decided from your`,
      "     written transcript, always between sections, and you are then asked for the words that close one video and",
      "     open the next. So write the sections as one continuous lecture, and spend the time where learning needs it.",
      "  4. COVER EVERYTHING IN THE SOURCE: the lecture's learning goals were planned from every heading, term, box and",
      "     figure of the book, and each section's request names its own. Teach every goal of yours and report it in",
      "     goals_taught; a goal left out is written in afterwards, where it fits less well. Ask each of the book's",
      "     questions your section is given (say which one it is, by its number).",
    ]),
    part("telling", "How to tell it", "rules", STORYTELLING_PLANNED),
    part("voice", "Voice", "rules", classVoicePlanned(language)),
    part("examples", "Narration examples", "rules", NARRATION_EXAMPLES),
    part("use", "How the transcript is used", "rules", [
      "HOW THE TRANSCRIPT IS USED (facts, not rules of style):",
      "  - A voice speaks it, so write only the words said: no headings, bullet lists, [brackets] or stage directions,",
      "    and say formulas and symbols the way they are spoken.",
      "  - Where the source marks [FIGURE figN: caption], the video shows that figure as it is spoken of there.",
      "  - Teach the subject only. The book's own furniture is not content: never mention or describe its QR codes,",
      "    \"scan for e-content\" boxes, logos, page numbers, page layout, reprint or copyright notes.",
      "  - Each request asks for one section, with the end of the one before when it is written: write that one",
      "    section, carrying on from there. Several sections are written at the same time, each by its own request:",
      "    the request names what the sections around it teach, which are theirs to teach.",
      "  - The student hears the lecture once, in order: what one section explains, the student already knows in the",
      "    next. A sentence said again, in this section or another, is taken out of the transcript.",
      ...(subject ? [`  - The subject is ${subject}.`] : []),
    ]),
    part("language", "Language", "language", languagePrompt(language)),
    part("outline", "The sections", "context", ["THE SECTIONS, in order (each request gives that section's own source):",
      ...sections.map((s) => `  SECTION ${s.n}` + (s.questionsOnly ? ": more of the source's questions from the section before"
        : `: ${headingOf(s.source) || "its part of the book"}`) +
        (s.questions?.length ? ` (${s.questions.length} of the source's questions)` : ""))]),
  ].filter((p) => p.text);       // "auto" language has no rules of its own
}

function headingOf(source: string): string {
  return (/^#{1,6}\s+(.+)$/m.exec(source ?? "")?.[1] ?? "").replace(/[*_`]/g, "").trim().slice(0, 80);
}

/** What the sections around this one teach, when they are not written yet: theirs, not this section's. */
function neighbours(section: Section, all: Section[], written: WrittenSection[]): string[] {
  const lines = all.filter((s) => Math.abs(s.n - section.n) <= 2 && s.n !== section.n && !written.some((w) => w.n === s.n))
    .map((s) => {
      const ideas = ideasOf(s.source).filter((idea) => idea.kind !== "aside").map((idea) => idea.text).slice(0, 12);
      const what = ideas.length ? ideas.join("; ") : `"${s.source.slice(0, 200).replace(/\s+/g, " ")}..."`;
      return `  Section ${s.n}${s.n < section.n ? " (before this one)" : " (after this one)"}: ${what}`;
    });
  return lines.length ? ["BEING WRITTEN AT THE SAME TIME, NOT YOURS TO TEACH (do not explain or preview these):", ...lines] : [];
}

export function sectionPrompt(o: {
  section: Section; all: Section[]; written: WrittenSection[]; system: Part[];
  plan?: StoryPlan; map: LearningMap; note?: string;
}): Prompt {
  const { section, all, written, plan, map } = o;
  const user: Part[] = [];
  const last = written.find((w) => w.n === section.n - 1);
  const context: string[] = [];
  if (written.length) context.push(`Written so far: ${written.map((w) => `section ${w.n} "${w.title}"`).join(", ")}.`);
  else if (section.n === 1) context.push("Nothing is written yet: this is the start of the lecture.");
  if (last) context.push(`Section ${last.n} ended like this:`, `  ...${last.text.slice(-1500)}`);
  else if (section.n > 1) context.push(`Section ${section.n - 1} is being written at the same time as this one (its topic is in the outline of sections).`);
  if (context.length) user.push(part("before", "Written before", "context", context));
  const around = neighbours(section, all, written);
  if (around.length) user.push(part("around", "Written at the same time", "context", around));
  user.push(part("ask", "Request", "ask", `Now write SECTION ${section.n} of ${all.length}` +
    (section.n === all.length ? " (the last: the lecture ends with it)" : "") +
    (section.questionsOnly ? ", which takes up more of the source's questions, listed below" : ", which teaches its part of the book, given below") +
    `. Call write_section once, with section: ${section.n} and the full text.`));
  const own = plan?.sections.find((s) => s.section === section.n);
  if (plan && own) {
    const first = plan.sections[0]?.section === section.n;
    const end = plan.sections[plan.sections.length - 1]?.section === section.n;
    user.push(part("story", "The video's story", "plan", [
      `THE STORY OF THIS VIDEO (video ${plan.video} of ${plan.of}), planned before any section was written. Every section of it is`,
      "being written from this plan at the same time, so follow it: it is what makes them one lesson.",
      `  Big question: ${plan.bigQuestion}`,
      ...(plan.runningExample ? [`  Running example: ${plan.runningExample}`] : []),
      `  Arc: ${plan.arc}`,
      "  Its sections:",
      ...plan.sections.map((s) => `    Section ${s.section}${s.section === section.n ? " (YOURS)" : ""}: picks up from "${s.opensFrom}"; ` +
        `ends on "${s.handsOn}"`),
    ]));
    user.push(part("yours", "This section's part", "plan", [
      `YOUR SECTION (${section.n}):`,
      first ? `  It OPENS the video: ${plan.opening}` : `  Pick up from: "${own.opensFrom}". Carry on from there, mid-thought: no greeting, ` +
        "no \"now let us talk about\", nothing the section before already said.",
      `  Guess first: ask "${own.guessFirst}", let the student think, then answer it.`,
      end ? `  It CLOSES the video: ${plan.closing}` : `  End on: "${own.handsOn}", left open for the next section to answer. ` +
        "Never end on a summary of what you just said.",
    ]));
  }
  const goals = map.goals.filter((g) => g.section === section.n);
  if (goals.length) {
    user.push(part("goals", "Goals to teach", "goals", ["The goals it teaches, every one (report each in goals_taught with the numbers of the",
      "sentences, counted from 1 in your text, that teach it):", ...goals.map((g) => `  ${goalLine(g, map.items)}`)]));
  }
  const qs = section.questions ?? [];
  user.push(part("questions", "Book questions", "questions", qs.length
    ? [`The book's questions you ask (${qs.map((q) => q.id).join(", ")}). Every other book question is asked in another ` +
      "section: do not solve it here.", ...qs.map(questionLine)]
    : "You ask none of the book's questions: they are asked in other sections."));
  user.push(part("length", "Length", "context", `Length: at most about ${section.words} words ` +
    `(${Math.round(section.words / WORDS_PER_MINUTE)} min). Shorter is fine once your goals are taught: never fill it out ` +
    "with extra exercises, recaps or talk about how to study."));
  const source = withoutExercises(section.source);
  user.push(part("book", section.questionsOnly ? "Book text these questions come from" : "Book text", "book",
    [section.questionsOnly ? "THE BOOK'S TEXT THESE QUESTIONS COME FROM:" : "THE PART OF THE BOOK THIS SECTION TEACHES:",
      source.slice(0, section.questionsOnly ? 6000 : 12000)]));
  if (o.note) user.push(part("retry", "Why the last try was sent back", "retry", `Your last try at section ${section.n} was sent back: ${o.note}`));
  return { system: o.system, user };
}

// ─── Patch ───────────────────────────────────────────────────────────────────────────────────────────────────────

export function patchPrompt(text: string, goal: string, source: string): Prompt {
  return {
    system: [part("system", "Patcher's rules", "rules", "You add a few sentences to a lecture's transcript, in its own voice.")],
    user: [
      part("section", "The section, numbered", "context", ["A section of a video lecture's transcript, its sentences numbered:", numbered(text)]),
      part("goal", "The goal it missed", "goals", `It was to teach this goal and did not: ${goal}`),
      part("book", "Book text", "book", ["Its part of the book:", source.slice(0, 6000)]),
      part("ask", "Request", "ask", "Write the few sentences that teach it, in the section's own voice and language, from the book's " +
        "facts only, and say after which sentence they go: where they fit the flow, not at the very end. Call write_patch once."),
    ],
  };
}

// ─── Tools ───────────────────────────────────────────────────────────────────────────────────────────────────────

export const SECTION_TOOL = {
  type: "function" as const,
  function: {
    name: "write_section",
    description: "Save one section of the lecture's spoken transcript. The text is only what the teacher says, in " +
      "paragraphs: no stage directions, no headings, no brackets, no markdown.",
    parameters: {
      type: "object",
      properties: {
        section: { type: "integer", description: "The section number, starting at 1." },
        title: { type: "string", description: "A short English title for what the section teaches." },
        text: { type: "string", description: "The section's full spoken transcript, paragraph by paragraph." },
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
          description: "Each of the section's goals, with the sentences that teach it.",
        },
      },
      required: ["section", "title", "text", "goals_taught"],
      additionalProperties: false,
    },
  },
};

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
