/**
 * The story plan: each video of a book's lecture planned as one story before its sections are written, so the
 * sections, written several at once, still read as one lesson.
 *
 * One model call per video (all at once), from the learning map (learningmap.ts): the video's big question (asked
 * in its first half minute, answered at its end), a running example or character, its arc, how it opens (a look
 * back at the video before, then the hook) and how it closes (the answer, a short self-check, what comes next),
 * and for each section the line it picks up from, the line it hands on, a moment where the student guesses before
 * being told, and the book's questions it asks right after the idea they test.
 *
 * The goals stay in the sections the map put them in (the section has the book's text for them); the plan decides
 * how the video tells them. A section writer gets the whole plan of its video (sectionPlanText).
 */

import { goalLine, type Goal, type LearningMap } from "./learningmap";
import { questionLine, type BookQuestion } from "./questions";
import type { Section } from "./transcript";

export type SectionPlan = {
  section: number;
  /** The words it picks the story up from (the end of the section before, as planned). */
  opensFrom: string;
  /** What it ends on, open, for the next section to answer. */
  handsOn: string;
  /** The question the student is asked to guess at before being told. */
  guessFirst: string;
  /** The book's questions it asks (ids, "q3"), each right after the idea it tests. */
  questions: string[];
};

export type StoryPlan = {
  video: number;
  of: number;
  bigQuestion: string;
  runningExample: string;
  arc: string;
  /** How the video opens: the look back at the video before (when there is one), the hook, the big question. */
  opening: string;
  /** How it ends: the big question answered, a short self-check, what comes next. */
  closing: string;
  sections: SectionPlan[];
};

export const STORY_PLAN_TOOL = {
  type: "function" as const,
  function: {
    name: "write_story_plan",
    description: "Save the plan of one video of the lecture: its story, and what each of its sections does in it.",
    parameters: {
      type: "object",
      properties: {
        big_question: { type: "string", description: "The one question the video answers: asked in its first half minute, answered at its end." },
        running_example: { type: "string", description: "A person, place or object that comes back through the video's sections, or \"\" when the content has none." },
        arc: { type: "string", description: "The story in two or three sentences: hook, build-up, the twist or wrong idea, the resolution." },
        opening: { type: "string", description: "How the video opens: a one-minute look back at the video before (when there is one), then the hook and the big question." },
        closing: { type: "string", description: "How it ends: the big question answered, two or three quick self-check questions, what the next video takes up." },
        sections: {
          type: "array",
          items: {
            type: "object",
            properties: {
              section: { type: "integer" },
              opens_from: { type: "string", description: "The thought it picks up from, as the section before ends it (for the video's first section: the opening)." },
              hands_on: { type: "string", description: "What it ends on: something open that the next section answers (for the last: the closing)." },
              guess_first: { type: "string", description: "A question the student is asked to guess at before the section tells it." },
              questions: { type: "array", items: { type: "string" }, description: "Ids of the book's questions this section asks, right after the idea each tests." },
            },
            required: ["section", "opens_from", "hands_on", "guess_first", "questions"],
            additionalProperties: false,
          },
        },
      },
      required: ["big_question", "running_example", "arc", "opening", "closing", "sections"],
      additionalProperties: false,
    },
  },
};

export const STORY_PLAN_SYSTEM = [
  "You plan one video of a lecture as a story, before its sections are written. The sections are written at the same",
  "time by different writers from your plan, so it is what makes them one lesson: each picks up exactly where the one",
  "before it ends and hands on to the next.",
  "",
  "  - The big question: a real puzzle the student wants answered, asked in the first half minute, answered at the end.",
  "  - The running example: someone or something the sections keep coming back to (a farmer's family on the Indus, a",
  "    cricket ball for the laws of motion). \"\" when the content has none (a list of definitions).",
  "  - The arc: hook, build-up, the wrong idea students hold and why it fails, the resolution.",
  "  - Each section: the thought it picks up from, what it ends on (open, for the next to answer, never a summary),",
  "    and one question the student guesses at before being told.",
  "  - The book's questions: each asked in the section that teaches its idea, right after that idea, as a check-in.",
  "    Only questions on the video's last idea go to its closing self-check. Every question listed is placed once.",
  "  - The opening of a video after the first starts with a one-minute look back: a question or two asking the",
  "    student to recall the video before, then its answer.",
  "Facts come from the goals and the book only. Call write_story_plan once.",
].join("\n");

/** The request for one video's plan: its sections and their goals, its questions, and the videos around it. */
export function storyPlanRequest(video: { index: number; of: number; sections: Section[] }, map: LearningMap,
  questions: BookQuestion[], subject?: string): string {
  const numbers = new Set(video.sections.map((s) => s.n));
  const before = map.goals.filter((g) => g.section < Math.min(...numbers));
  const after = map.goals.filter((g) => g.section > Math.max(...numbers));
  return [
    ...(subject ? [`The subject is ${subject}.`, ""] : []),
    `Plan video ${video.index} of ${video.of}.`,
    "",
    ...(before.length ? ["Earlier videos taught (the student has seen these):",
      ...before.slice(-8).map((g) => `  ${g.goal}`), ""] : ["This is the first video of the lecture.", ""]),
    "ITS SECTIONS, in order, with the goals each teaches:",
    ...video.sections.flatMap((s) => {
      const goals = map.goals.filter((g) => g.section === s.n);
      return [`  SECTION ${s.n}${s.questionsOnly ? " (the book's questions on the part before)" : ""}`,
        ...(goals.length ? goals.map((g) => `    ${goalLine(g, map.items)}`) : ["    (no goals of its own)"])];
    }),
    "",
    ...(questions.length ? [`THE BOOK'S QUESTIONS IN THIS VIDEO (${questions.length}; place every one):`,
      ...questions.map(questionLine), ""] : []),
    ...(after.length ? ["The videos after this one teach (do not teach these):", ...after.slice(0, 6).map((g) => `  ${g.goal}`), ""]
      : ["This is the last video of the lecture.", ""]),
    "Call write_story_plan now.",
  ].join("\n");
}

type RawSection = { section?: unknown; opens_from?: unknown; hands_on?: unknown; guess_first?: unknown; questions?: unknown };

/** The reply as a plan for the video's sections; null when it holds no story. Every listed question is placed:
 * one the reply left out stays in the section the book prints it in. */
export function readStoryPlan(raw: unknown, video: { index: number; of: number; sections: Section[] },
  questions: BookQuestion[]): StoryPlan | null {
  const r = (raw ?? {}) as Record<string, unknown>;
  const text = (v: unknown, most = 400) => String(v ?? "").replace(/\s+/g, " ").trim().slice(0, most);
  const bigQuestion = text(r.big_question);
  if (!bigQuestion) return null;
  const rows: RawSection[] = Array.isArray(r.sections) ? (r.sections as RawSection[]) : [];
  const known = new Set(questions.map((q) => q.id));
  const placed = new Set<string>();
  const sections: SectionPlan[] = video.sections.map((s) => {
    const row = rows.find((x) => Number(x?.section) === s.n) ?? {};
    const ids: string[] = [];
    for (const q of Array.isArray(row.questions) ? row.questions : []) {
      const id = String(q).trim();
      if (!known.has(id) || placed.has(id)) continue;
      placed.add(id);
      ids.push(id);
    }
    return { section: s.n, opensFrom: text(row.opens_from), handsOn: text(row.hands_on), guessFirst: text(row.guess_first),
      questions: ids };
  });
  // A question the plan did not place: where the book prints it.
  for (const s of video.sections) {
    for (const q of s.questions ?? []) {
      if (placed.has(q.id)) continue;
      placed.add(q.id);
      sections.find((x) => x.section === s.n)!.questions.push(q.id);
    }
  }
  return { video: video.index, of: video.of, bigQuestion, runningExample: text(r.running_example), arc: text(r.arc, 600),
    opening: text(r.opening, 600), closing: text(r.closing, 600), sections };
}

/** What one section's writer is told of its video's plan: the whole story, and its own part in it. */
export function sectionPlanText(plan: StoryPlan, n: number, goals: Goal[], map: LearningMap): string[] {
  const own = plan.sections.find((s) => s.section === n);
  if (!own) return [];
  const first = plan.sections[0]?.section === n;
  const last = plan.sections[plan.sections.length - 1]?.section === n;
  const mine = goals.filter((g) => g.section === n);
  return [
    `THE STORY OF THIS VIDEO (video ${plan.video} of ${plan.of}), planned before any section was written. Every section of it is`,
    "being written from this plan at the same time, so follow it: it is what makes them one lesson.",
    `  Big question: ${plan.bigQuestion}`,
    ...(plan.runningExample ? [`  Running example: ${plan.runningExample}`] : []),
    `  Arc: ${plan.arc}`,
    "  Its sections:",
    ...plan.sections.map((s) => `    Section ${s.section}${s.section === n ? " (YOURS)" : ""}: picks up from "${s.opensFrom}"; ` +
      `ends on "${s.handsOn}"`),
    "",
    `YOUR SECTION (${n}):`,
    first ? `  It OPENS the video: ${plan.opening}` : `  Pick up from: "${own.opensFrom}". Carry on from there, mid-thought: no greeting, ` +
      "no \"now let us talk about\", nothing the section before already said.",
    `  Guess first: ask "${own.guessFirst}", give the student a moment, then answer it.`,
    ...(mine.length ? ["  The goals it teaches, every one (report each in goals_taught with the numbers of the sentences, counted",
      "  from 1 in your text, that teach it):", ...mine.map((g) => `    ${goalLine(g, map.items)}`)] : []),
    last ? `  It CLOSES the video: ${plan.closing}` : `  End on: "${own.handsOn}", left open for the next section to answer. ` +
      "Never end on a summary of what you just said.",
  ];
}

/** Where a goal stands while the lecture is written: not written yet, taught as written, written in afterwards,
 * or still missing. */
export type GoalStatus = "waiting" | "taught" | "patched" | "missing";

/** The lecture's plan as the page shows it (the "plan" event): the learning map, each video's story, coverage. */
export type PlanView = {
  goals: {
    id: string; goal: string; section: number; items: { kind: string; text: string }[];
    misconception: string; hook: string; difficulty: number; added?: boolean; status: GoalStatus;
  }[];
  videos: {
    index: number; of: number; bigQuestion: string; runningExample: string; arc: string; opening: string; closing: string;
    sections: { section: number; opensFrom: string; handsOn: string; guessFirst: string; questions: string[] }[];
  }[];
  /** Every section of the lecture, in order. */
  sections: number[];
  coverage: { planned: number; taught: number; patched: number; missing: number };
};

/** The plan for the page, from the map, the videos' plans and each goal's status so far. */
export function planView(map: LearningMap, plans: StoryPlan[], status: Map<string, GoalStatus>, sections: number[],
  questions: BookQuestion[]): PlanView {
  const byId = new Map(map.items.map((i) => [i.id, i]));
  const asked = (id: string) => {
    const q = questions.find((x) => x.id === id);
    return q ? `${q.number}. ${q.text}${q.choices.length ? ` (${q.choices.join(" / ")})` : ""}` : id;
  };
  const goals = map.goals.map((g) => ({
    id: g.id, goal: g.goal, section: g.section,
    items: g.items.map((id) => byId.get(id)).filter((i): i is NonNullable<typeof i> => !!i).map((i) => ({ kind: i.kind, text: i.text })),
    misconception: g.misconception, hook: g.hook, difficulty: g.difficulty, ...(g.added ? { added: true } : {}),
    status: status.get(g.id) ?? "waiting" as GoalStatus,
  }));
  const count = (s: GoalStatus) => goals.filter((g) => g.status === s).length;
  return {
    goals,
    videos: plans.map((p) => ({ index: p.video, of: p.of, bigQuestion: p.bigQuestion, runningExample: p.runningExample, arc: p.arc,
      opening: p.opening, closing: p.closing,
      sections: p.sections.map((s) => ({ ...s, questions: s.questions.map(asked) })) })),
    sections,
    coverage: { planned: goals.length, taught: count("taught"), patched: count("patched"), missing: count("missing") },
  };
}
