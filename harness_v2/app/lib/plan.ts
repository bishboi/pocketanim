/**
 * The lecture plan: one model call reads the whole book (as blocks, blocks.ts) and divides it into lectures by what
 * is learned, not by word count, and maps each lecture's learning goals. It answers with block ids only, never the
 * book's text. Code then checks the reply against the book:
 *
 *   - an id that is not a block is dropped;
 *   - a block placed in two lectures stays in the first;
 *   - a block placed nowhere (and not skipped as the book's furniture) goes to the lecture that holds the block
 *     before it, so nothing in the book is left out;
 *   - a goal's blocks must be its lecture's: others are dropped; a lecture's block no goal names is reported.
 */

import { kindOf, type Block } from "./source/blocks";
import type { Check } from "./types";

export type Goal = { id: string; lecture: number; goal: string; blocks: string[]; misconception: string; hook: string };
export type Lecture = { n: number; title: string; why: string; blocks: string[]; goals: Goal[] };
export type Plan = { lectures: Lecture[]; skipped: { block: string; reason: string }[] };

export const PLAN_TOOL = {
  type: "function" as const,
  function: {
    name: "plan_lectures",
    description: "Save the lecture series: each lecture's blocks of the book (by id) and its learning goals, in teaching order.",
    parameters: {
      type: "object",
      properties: {
        lectures: {
          type: "array",
          description: "The lectures in the order they are taught.",
          items: {
            type: "object",
            properties: {
              title: { type: "string", description: "What the lecture teaches, as its title." },
              why: { type: "string", description: "One sentence: why this lecture is a unit, and what it builds on." },
              blocks: { type: "array", items: { type: "string" }, description: "The Datalab ids of the book's blocks this lecture teaches (\"/page/3/Text/7\"), every one." },
              goals: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    goal: { type: "string", description: "What the student will be able to do, in their words, one sentence." },
                    blocks: { type: "array", items: { type: "string" }, description: "The ids of the blocks that teach it (this lecture's)." },
                    misconception: { type: "string", description: "The wrong idea students usually hold about it, or \"\"." },
                    hook: { type: "string", description: "Something from a student's everyday life it can start from." },
                  },
                  required: ["goal", "blocks", "misconception", "hook"],
                  additionalProperties: false,
                },
              },
            },
            required: ["title", "why", "blocks", "goals"],
            additionalProperties: false,
          },
        },
        skipped: {
          type: "array",
          description: "Blocks that are not teaching (the book's furniture: QR codes, page headers, reprint notes), each with why.",
          items: {
            type: "object",
            properties: { block: { type: "string" }, reason: { type: "string" } },
            required: ["block", "reason"],
            additionalProperties: false,
          },
        },
      },
      required: ["lectures", "skipped"],
      additionalProperties: false,
    },
  },
};

type RawGoal = { goal?: unknown; blocks?: unknown; misconception?: unknown; hook?: unknown };
type RawLecture = { title?: unknown; why?: unknown; blocks?: unknown; goals?: unknown };

const ids = (v: unknown) => (Array.isArray(v) ? v.map((x) => String(x).trim()) : []);
const text = (v: unknown, most = 300) => String(v ?? "").replace(/\s+/g, " ").trim().slice(0, most);

/** The reply as a plan, made whole against the book, and what code found doing it. */
export function readPlan(raw: unknown, blocks: Block[]): { plan: Plan; checks: Check[] } {
  const checks: Check[] = [];
  const known = new Map(blocks.map((b, i) => [b.id, i]));
  const r = (raw ?? {}) as { lectures?: unknown; skipped?: unknown };
  const rawLectures: RawLecture[] = Array.isArray(r.lectures) ? r.lectures : [];
  const skipped = (Array.isArray(r.skipped) ? r.skipped : [])
    .map((s: { block?: unknown; reason?: unknown }) => ({ block: String(s?.block ?? ""), reason: text(s?.reason, 160) }))
    .filter((s) => known.has(s.block));
  const placed = new Map<string, number>();
  const unknown: string[] = [];
  const twice: string[] = [];
  const lectures: Lecture[] = [];
  for (const l of rawLectures) {
    const own: string[] = [];
    for (const id of ids(l.blocks)) {
      if (!known.has(id)) { unknown.push(id); continue; }
      if (placed.has(id)) { if (placed.get(id) !== lectures.length + 1) twice.push(id); continue; }
      placed.set(id, lectures.length + 1);
      own.push(id);
    }
    if (!own.length) continue;
    lectures.push({ n: lectures.length + 1, title: text(l.title, 120) || `Lecture ${lectures.length + 1}`, why: text(l.why),
      blocks: own, goals: [] });
    // Goals are read once every lecture has its blocks (a goal may only name its own lecture's blocks).
    (lectures[lectures.length - 1] as Lecture & { rawGoals?: RawGoal[] }).rawGoals = Array.isArray(l.goals) ? l.goals : [];
  }
  checks.push({ name: "Lectures", result: lectures.length ? "pass" : "fail", detail: `${lectures.length} lecture(s) in the reply` });
  if (unknown.length) checks.push({ name: "Block ids", result: "fixed", detail: `${unknown.length} id(s) that are not blocks dropped: ${unknown.slice(0, 10).join(", ")}` });
  if (twice.length) checks.push({ name: "One lecture a block", result: "fixed", detail: `${twice.length} block(s) placed in two lectures, kept in the first: ${twice.slice(0, 10).join(", ")}` });

  // Every block in a lecture or skipped: one placed nowhere goes with the block before it (or after, at the start).
  const skip = new Set(skipped.map((s) => s.block));
  const missing = blocks.filter((b) => !placed.has(b.id) && !skip.has(b.id));
  for (const b of missing) {
    const at = known.get(b.id)!;
    let home: number | undefined;
    for (let i = at - 1; i >= 0 && home === undefined; i--) home = placed.get(blocks[i].id);
    for (let i = at + 1; i < blocks.length && home === undefined; i++) home = placed.get(blocks[i].id);
    if (home === undefined) continue;
    placed.set(b.id, home);
    lectures[home - 1].blocks.push(b.id);
  }
  checks.push({ name: "Every block placed", result: missing.length ? "fixed" : "pass", detail: missing.length
    ? `${missing.length} block(s) the plan left out put with the block before them: ${missing.slice(0, 12).map((b) => b.id).join(", ")}`
    : `all ${blocks.length - skip.size} teaching blocks in a lecture` });
  if (skipped.length) checks.push({ name: "Skipped as furniture", result: "info", detail: skipped.map((s) => `${s.block} (${s.reason})`).join("; ").slice(0, 400) });

  // A lecture's blocks in the book's order (the writer reads them as the book has them).
  for (const l of lectures) l.blocks.sort((a, b) => known.get(a)! - known.get(b)!);
  const order = lectures.map((l) => known.get(l.blocks[0])!);
  if (order.some((x, i) => i && x < order[i - 1])) checks.push({ name: "Order", result: "info", detail: "lectures teach the book in another order than it is printed" });

  // Goals: each with its own lecture's blocks only; numbered in teaching order.
  let g = 0;
  let foreign = 0;
  for (const l of lectures) {
    const mine = new Set(l.blocks);
    for (const rg of (l as Lecture & { rawGoals?: RawGoal[] }).rawGoals ?? []) {
      const own = ids(rg.blocks).filter((id) => mine.has(id));
      foreign += ids(rg.blocks).length - own.length;
      const words = text(rg.goal, 240);
      if (!words) continue;
      l.goals.push({ id: `g${++g}`, lecture: l.n, goal: words, blocks: own, misconception: text(rg.misconception, 200), hook: text(rg.hook, 200) });
    }
    delete (l as Lecture & { rawGoals?: RawGoal[] }).rawGoals;
  }
  if (foreign) checks.push({ name: "Goal blocks", result: "fixed", detail: `${foreign} block id(s) a goal named outside its lecture dropped` });
  const named = new Set(lectures.flatMap((l) => l.goals.flatMap((x) => x.blocks)));
  const loose = lectures.flatMap((l) => l.blocks).filter((id) => !named.has(id) && kindOf(blocks[known.get(id)!].type) !== "heading");
  checks.push({ name: "Goals", result: g ? "pass" : "fail", detail: `${g} goals` });
  if (loose.length) checks.push({ name: "Blocks under a goal", result: "info", detail: `${loose.length} block(s) in a lecture that no goal names (taught all the same): ${loose.slice(0, 12).join(", ")}` });
  return { plan: { lectures, skipped }, checks };
}

/** A goal as the writer's prompt shows it. */
export function goalLine(goal: Goal): string {
  return `${goal.id}: ${goal.goal}` + (goal.blocks.length ? ` [blocks ${goal.blocks.join(", ")}]` : "") +
    (goal.misconception ? `\n      the usual wrong idea: ${goal.misconception}` : "") +
    (goal.hook ? `\n      everyday hook: ${goal.hook}` : "");
}
