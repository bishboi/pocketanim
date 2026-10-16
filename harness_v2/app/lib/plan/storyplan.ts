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

import type { LearningMap } from "./learningmap";
import type { BookQuestion } from "../source/questions";
import type { Section } from "../source/book";

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
