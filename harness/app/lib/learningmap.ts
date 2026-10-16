/**
 * The learning map: before any section of a book's lecture is written, what the book teaches, as goals a student
 * reaches, each tied to the book's own items that teach it. It is the lecture's coverage list.
 *
 *   sourceItems   what the book's text holds that the lecture must teach, found by code (no model): its headings,
 *                 its bold and italic terms, its asides ("Do you know?", "Activity") and its figures, per section.
 *   the map       one model call over the whole book (learningMapRequest, LEARNING_MAP_TOOL): goals in a
 *                 student's words, each naming the items it teaches, what it builds on, the usual wrong idea about
 *                 it, an everyday hook and how hard it is.
 *   readLearningMap  the reply checked against the items: every item sits under a goal. An item the reply left
 *                 out gets a goal of its own, made here, so nothing in the book is dropped by the map.
 *
 * A goal is taught in the section whose part of the book holds its items (the first of them), so the section's
 * writer has the text it teaches from. The book's questions are not goals: they are placed by the story plan
 * (storyplan.ts) and checked by the compiler (every one asked and explained).
 */

import { asidesOf, ideasOf } from "./coverage";
import type { Section } from "./transcript";

export type SourceItem = {
  /** "i1", "i2"...: the map and the goals name items by these. */
  id: string;
  kind: "heading" | "term" | "aside" | "figure";
  text: string;
  section: number;
};

export type Goal = {
  /** "g1", "g2"...: in order of the sections that teach them. */
  id: string;
  /** In a student's words: "Explain why surplus food let villages grow into cities". */
  goal: string;
  /** The items it teaches (SourceItem ids). */
  items: string[];
  /** The section that teaches it: the one whose part of the book holds its first item. */
  section: number;
  buildsOn: string[];
  misconception: string;
  hook: string;
  /** 1 (easy) to 3 (hard): how much time it is given. */
  difficulty: number;
  /** Made here for items the map left out, not by the model. */
  added?: boolean;
};

export type LearningMap = { items: SourceItem[]; goals: Goal[]; added: number };

const FIGURE = /\[FIGURE (\w+):\s*([^\]\n]{0,160})\]/g;

/** What each section's part of the book holds that the lecture must teach, in order. */
export function sourceItems(sections: Section[]): SourceItem[] {
  const out: SourceItem[] = [];
  const seen = new Set<string>();
  for (const section of sections) {
    // A section of only questions carries the part of the book before it, for context: its items are that part's.
    if (!section.book || section.questionsOnly) continue;
    const add = (kind: SourceItem["kind"], text: string) => {
      const key = `${kind}:${text.toLowerCase()}`;
      if (!text || seen.has(key)) return;
      seen.add(key);
      out.push({ id: `i${out.length + 1}`, kind, text, section: section.n });
    };
    // Every box beside the text is an item of its own, with or without a bold term in it.
    for (const idea of ideasOf(section.source)) if (idea.kind !== "aside") add(idea.kind, idea.text);
    for (const aside of asidesOf(section.source)) {
      const body = aside.text.startsWith(aside.title) ? aside.text.slice(aside.title.length).replace(/^[\s:.!?।-]+/, "")
        : aside.text;
      add("aside", `${aside.title}: ${body.slice(0, 100)}`.replace(/:\s*$/, ""));
    }
    for (const m of section.source.matchAll(FIGURE)) add("figure", `${m[1]}: ${m[2].trim()}`.replace(/:\s*$/, ""));
  }
  return out;
}

export const LEARNING_MAP_TOOL = {
  type: "function" as const,
  function: {
    name: "write_learning_map",
    description: "Save the lecture's learning goals, in teaching order, each with the book's items it teaches.",
    parameters: {
      type: "object",
      properties: {
        goals: {
          type: "array",
          items: {
            type: "object",
            properties: {
              goal: { type: "string", description: "What the student will be able to do, in their words, one sentence." },
              items: { type: "array", items: { type: "string" }, description: "The ids of the book's items it teaches (\"i3\")." },
              builds_on: { type: "array", items: { type: "integer" }, description: "The numbers (1-based, in this list) of earlier goals it needs." },
              misconception: { type: "string", description: "The wrong idea students usually hold about it, or \"\"." },
              hook: { type: "string", description: "Something from a student's everyday life that it can start from." },
              difficulty: { type: "integer", description: "1 easy, 2 medium, 3 hard." },
            },
            required: ["goal", "items", "misconception", "hook", "difficulty"],
            additionalProperties: false,
          },
        },
      },
      required: ["goals"],
      additionalProperties: false,
    },
  },
};

export const LEARNING_MAP_SYSTEM = [
  "You are an experienced teacher planning a video lecture from a book chapter. Before anyone writes a word of the",
  "lecture, you list what the student must come away able to do: its LEARNING GOALS. The goals are the lecture's",
  "checklist; every item of the book listed for you is taught under one of them.",
  "",
  "For each goal:",
  "  - goal: one sentence in a student's words, about understanding, not reciting (\"Explain why ...\", \"Tell ...",
  "    apart from ...\", \"Use ... to work out ...\").",
  "  - items: the ids of the book's items it teaches. EVERY item listed belongs to exactly one goal. A goal's items",
  "    come from one part of the book (one section), or from neighbouring parts when they are one idea.",
  "  - builds_on: earlier goals it needs.",
  "  - misconception: the wrong idea students usually hold (\"heavier things fall faster\"); \"\" when there is none.",
  "  - hook: something from a student's everyday life in India to start from (cricket, trains, the monsoon, the",
  "    kitchen, the market, a festival), true to the idea.",
  "  - difficulty: 1 to 3.",
  "Group small items into one goal when they are one idea (a heading and the terms under it); a big idea may need",
  "two goals. Keep the book's order. Facts come from the book only. Call write_learning_map once.",
].join("\n");

/** The request for the map: each section's items and its part of the book. */
export function learningMapRequest(sections: Section[], items: SourceItem[], subject?: string): string {
  const parts: string[] = [];
  let budget = 60000;
  for (const section of sections) {
    if (!section.book || section.questionsOnly) continue;
    const own = items.filter((i) => i.section === section.n);
    const text = section.source.slice(0, Math.max(1500, Math.min(6000, budget)));
    budget -= text.length;
    parts.push(
      `SECTION ${section.n}`,
      own.length ? own.map((i) => `  ${i.id} [${i.kind}] ${i.text}`).join("\n") : "  (no listed items: its text only)",
      "  Its part of the book:",
      text.split("\n").map((line) => `    ${line}`).join("\n"),
      "",
    );
  }
  return [
    ...(subject ? [`The subject is ${subject}.`, ""] : []),
    `The book's items to teach (${items.length}), section by section, with each section's text:`,
    "",
    ...parts,
    "List the learning goals now (write_learning_map), every item under exactly one goal.",
  ].join("\n");
}

type RawGoal = { goal?: unknown; items?: unknown; builds_on?: unknown; misconception?: unknown; hook?: unknown; difficulty?: unknown };

/** The model's reply as goals, checked against the items: unknown ids dropped, every item placed. */
export function readLearningMap(raw: unknown, items: SourceItem[], sections: Section[]): LearningMap {
  const byId = new Map(items.map((i) => [i.id, i]));
  const list: RawGoal[] = Array.isArray((raw as { goals?: unknown })?.goals) ? (raw as { goals: RawGoal[] }).goals : [];
  const placed = new Set<string>();
  const kept: { raw: RawGoal; ids: string[]; at: number }[] = [];
  list.forEach((g, at) => {
    const ids = (Array.isArray(g?.items) ? g.items : []).map((x) => String(x).trim())
      .filter((id) => byId.has(id) && !placed.has(id));
    const text = String(g?.goal ?? "").trim();
    if (!text || !ids.length) return;
    ids.forEach((id) => placed.add(id));
    kept.push({ raw: g, ids, at: at + 1 });
  });
  const goals: Goal[] = kept.map(({ raw: g, ids }) => ({
    id: "",
    goal: String(g.goal).trim().slice(0, 240),
    items: ids,
    section: Math.min(...ids.map((id) => byId.get(id)!.section)),
    buildsOn: [],
    misconception: String(g.misconception ?? "").trim().slice(0, 240),
    hook: String(g.hook ?? "").trim().slice(0, 240),
    difficulty: Math.max(1, Math.min(3, Math.round(Number(g.difficulty) || 2))),
  }));
  // A goal whose items lie in more than one section is taught in each of them, from that section's own text: its
  // items there go with a goal of the same words in that section (a section is written from its own part only).
  const split: Goal[] = [];
  goals.forEach((goal, i) => {
    const here = goal.items.filter((id) => byId.get(id)!.section === goal.section);
    const elsewhere = goal.items.filter((id) => byId.get(id)!.section !== goal.section);
    goal.items = here;
    for (const n of [...new Set(elsewhere.map((id) => byId.get(id)!.section))]) {
      split.push({ ...goal, items: elsewhere.filter((id) => byId.get(id)!.section === n), section: n,
        goal: `${goal.goal} (continued)`.slice(0, 240), buildsOn: [String(i)] });
    }
  });
  // What builds on what, by the model's numbering of its own list (only goals that were kept).
  const keptAt = new Map(kept.map((k, i) => [k.at, i]));
  kept.forEach(({ raw: g }, i) => {
    const refs = Array.isArray(g.builds_on) ? g.builds_on : [];
    goals[i].buildsOn = refs.map((r) => keptAt.get(Number(r))).filter((j): j is number => j !== undefined && j !== i)
      .map(String);
  });
  goals.push(...split);
  // Items the map left out: one goal per section for them, so the lecture still teaches them.
  let added = 0;
  const left = items.filter((i) => !placed.has(i.id));
  for (const section of sections) {
    const own = left.filter((i) => i.section === section.n);
    if (!own.length) continue;
    added += 1;
    // Named shortly (a box by its title, a figure by its id); the items themselves are listed with the goal.
    const name = (i: SourceItem) => i.kind === "aside" ? i.text.split(":")[0] : i.kind === "figure" ? `figure ${i.text.split(":")[0]}` : i.text;
    goals.push({ id: "", goal: `Also from the book: ${own.map(name).join("; ")}`.slice(0, 240),
      items: own.map((i) => i.id), section: section.n, buildsOn: [], misconception: "", hook: "", difficulty: 2, added: true });
  }
  // In teaching order (by section, the model's order within one); ids follow that order.
  const order = goals.map((g, i) => ({ g, i })).sort((a, b) => a.g.section - b.g.section || a.i - b.i);
  const newIndex = new Map(order.map(({ i }, k) => [String(i), k]));
  const out = order.map(({ g }, k) => ({ ...g, id: `g${k + 1}` }));
  for (const g of out) g.buildsOn = g.buildsOn.map((old) => newIndex.get(old)).filter((k): k is number => k !== undefined)
    .map((k) => `g${k + 1}`);
  return { items, goals: out, added };
}

/** A goal as the prompts show it: its words, the book's items it teaches, its wrong idea and its hook. */
export function goalLine(goal: Goal, items: SourceItem[]): string {
  const own = goal.items.map((id) => items.find((i) => i.id === id)).filter((i): i is SourceItem => !!i)
    .map((i) => `[${i.kind}] ${i.text}`);
  return `${goal.id}: ${goal.goal}` + (own.length ? `\n      teaches: ${own.join("; ")}` : "") +
    (goal.misconception ? `\n      the usual wrong idea: ${goal.misconception}` : "") +
    (goal.hook ? `\n      everyday hook: ${goal.hook}` : "");
}
