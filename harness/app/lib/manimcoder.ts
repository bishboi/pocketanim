/**
 * The free-form Manim blocks of a lecture, written by their own model (PANIM_MANIM_MODEL). The script writer plans
 * each block ({"op":"manim","id":"pulley1","plan":"..."}, lib/lecture.ts MANIM_PLAN); this model writes the code of
 * every figure at once (one request a figure, all its beats together, so later beats can use what earlier ones
 * built), with the book's figure attached when it rebuilds one. A block the compiler's run refuses goes back to it
 * with the reason (repairManim), not to the whole section. A figure it cannot write is left out of its beats (the
 * lines are still said).
 */

import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { MANIM_RULES } from "./lecture";

type Op = Record<string, unknown>;
type Slot = { op: Op; beat: Record<string, unknown>; where: string; say: string; plan: string; figure?: string };

export type ManimCoderOptions = {
  key: string;
  model: string;
  /** The lecture's engine style (its board colours). */
  style?: string;
  /** A book figure's picture file by id, for a block marked "from_figure". */
  figureFile?: (id: string) => string | undefined;
  signal?: AbortSignal;
  /** What each request cost, when it ran, and its tokens. */
  onCost?: (usd: number, span: [number, number], tokens: { in: number; out: number }) => void;
  onStatus?: (text: string) => void;
};

/** Figures written at once (PANIM_MANIM_PARALLEL). */
const PARALLEL = Math.max(1, Number(process.env.PANIM_MANIM_PARALLEL) || 6);
/** Code already written for a figure (its beats' lines and plans): a script checked again asks nothing. */
const written = new Map<string, string[]>();
/** Each written block's plan (the plan leaves the op once its code is in): a repair is told the plan again. */
const planOf = new Map<string, string>();

const SYSTEM = [
  "You write the Manim code for ONE figure of a narrated video lecture. The figure is built over a few beats; each",
  "beat has the line the teacher says and the script writer's plan of what to draw on it. Write each beat's block.",
  "",
  ...MANIM_RULES,
  "",
  'Reply with JSON only: {"blocks": ["code for beat 1", "code for beat 2", ...]}: exactly one string per beat, in',
  "order, each the body of construct() for that beat (later beats use the names the earlier ones made). No",
  "markdown, no comments outside the code.",
].join("\n");

function slotsOf(script: Record<string, unknown>): Map<string, Slot[]> {
  const out = new Map<string, Slot[]>();
  const chapters = Array.isArray(script.chapters) ? script.chapters : [];
  chapters.forEach((chapter, c) => {
    const beats = Array.isArray((chapter as { beats?: unknown }).beats) ? (chapter as { beats: unknown[] }).beats : [];
    beats.forEach((beat, b) => {
      const ops = Array.isArray((beat as { do?: unknown }).do) ? (beat as { do: unknown[] }).do : [];
      for (const op of ops) {
        if (!op || typeof op !== "object" || (op as Op).op !== "manim") continue;
        const id = String((op as Op).id ?? `manim${c + 1}`);
        const list = out.get(id) ?? [];
        list.push({ op: op as Op, beat: beat as Record<string, unknown>, where: `chapter ${c + 1} beat ${b + 1}`,
          say: String((beat as { say?: unknown }).say ?? ""), plan: String((op as Op).plan ?? ""),
          figure: typeof (op as Op).from_figure === "string" ? String((op as Op).from_figure) : undefined });
        out.set(id, list);
      }
    });
  });
  return out;
}

const hasCode = (slot: Slot) => typeof slot.op.code === "string" && slot.op.code.trim() !== "";
const memoKey = (id: string, slots: Slot[]) => JSON.stringify([id, slots.map((s) => [s.say, s.plan, s.figure ?? ""])]);

/** Whether the script has any free-form Manim block. */
export function hasManim(script: unknown): boolean {
  return !!script && typeof script === "object" && slotsOf(script as Record<string, unknown>).size > 0;
}

/** Whether the script has a Manim block still to be written. */
export function needsManim(script: unknown): boolean {
  if (!script || typeof script !== "object") return false;
  return [...slotsOf(script as Record<string, unknown>).values()].some((slots) => slots.some((s) => !hasCode(s)));
}

async function picture(file: string): Promise<string | null> {
  try {
    const sharp = (await import("sharp")).default;
    const jpeg = await sharp(file).flatten({ background: "#ffffff" })
      .resize({ width: 1024, height: 1024, fit: "inside", withoutEnlargement: true }).jpeg({ quality: 80 }).toBuffer();
    return `data:image/jpeg;base64,${jpeg.toString("base64")}`;
  } catch {
    if (!existsSync(file)) return null;
    const ext = path.extname(file).slice(1).toLowerCase().replace("jpg", "jpeg") || "png";
    return `data:image/${ext};base64,${(await readFile(file)).toString("base64")}`;
  }
}

/** The blocks of one figure from the model: one code string a beat, or null when its reply will not do. */
async function ask(id: string, slots: Slot[], options: ManimCoderOptions, fix?: { errors: string[] }): Promise<string[] | null> {
  const lines = [
    `The lecture's style: ${options.style ?? "atlas"}. The figure's id: ${id}. Its ${slots.length} beat${slots.length > 1 ? "s" : ""}:`,
    ...slots.map((s, k) => `Beat ${k + 1} says: "${s.say}"\n  Plan: ${s.plan || "(no plan: draw what the line says)"}`),
  ];
  if (fix) {
    lines.push("", "YOUR LAST CODE for these beats was refused by the compiler's run:",
      ...slots.map((s, k) => `Beat ${k + 1}:\n${String(s.op.code ?? "")}`), "", "What was wrong:", ...fix.errors,
      "", "Fix exactly that and keep everything else.");
  }
  const content: unknown[] = [{ type: "text", text: lines.join("\n") }];
  const figure = slots.find((s) => s.figure)?.figure;
  const file = figure ? options.figureFile?.(figure) : undefined;
  const image = file ? await picture(file) : null;
  if (image) {
    content.push({ type: "text", text: `The book's figure ${figure}, to rebuild exactly (every value, label and line):` },
      { type: "image_url", image_url: { url: image } });
  }
  const began = Date.now();
  const response = await fetch(process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    signal: options.signal,
    headers: { Authorization: `Bearer ${options.key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: options.model, usage: { include: true }, response_format: { type: "json_object" },
      messages: [{ role: "system", content: SYSTEM }, { role: "user", content }] }),
  });
  if (!response.ok) throw new Error(`OpenRouter ${response.status}: ${(await response.text()).slice(0, 200)}`);
  const body = (await response.json()) as { choices?: { message?: { content?: string } }[];
    usage?: { cost?: number; prompt_tokens?: number; completion_tokens?: number } };
  options.onCost?.(body.usage?.cost ?? 0, [began, Date.now()],
    { in: body.usage?.prompt_tokens ?? 0, out: body.usage?.completion_tokens ?? 0 });
  const text = String(body.choices?.[0]?.message?.content ?? "");
  try {
    const parsed = JSON.parse(text.slice(text.indexOf("{"), text.lastIndexOf("}") + 1)) as { blocks?: unknown };
    const blocks = Array.isArray(parsed.blocks) ? parsed.blocks.map((b) => String(b ?? "")) : [];
    return blocks.length === slots.length && blocks.every((b) => b.trim()) ? blocks : null;
  } catch {
    return null;
  }
}

function put(slots: Slot[], blocks: string[]) {
  slots.forEach((slot, k) => {
    if (slot.plan) planOf.set(blocks[k], slot.plan);
    slot.op.code = blocks[k];
    delete slot.op.plan;
  });
}

function drop(slots: Slot[]) {
  for (const slot of slots) {
    const ops = slot.beat.do as unknown[];
    slot.beat.do = ops.filter((op) => op !== slot.op);
  }
}

async function eachAtOnce<T>(items: T[], run: (item: T) => Promise<void>) {
  const queue = [...items];
  await Promise.all(Array.from({ length: Math.min(PARALLEL, queue.length) }, async () => {
    for (let item = queue.shift(); item !== undefined; item = queue.shift()) await run(item);
  }));
}

/**
 * Every planned block of the script written (in place): each figure by one request, all at once; a figure asked
 * before is filled from what was written then. A figure the model cannot write (twice) is left out of its beats.
 */
export async function fillManim(script: Record<string, unknown>, options: ManimCoderOptions): Promise<{ written: string[]; dropped: string[] }> {
  const todo = [...slotsOf(script)].filter(([, slots]) => slots.some((s) => !hasCode(s)));
  const out = { written: [] as string[], dropped: [] as string[] };
  await eachAtOnce(todo, async ([id, slots]) => {
    const kept = written.get(memoKey(id, slots));
    if (kept) return put(slots, kept);
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const blocks = await ask(id, slots, options);
        if (blocks) {
          written.set(memoKey(id, slots), blocks);
          put(slots, blocks);
          out.written.push(id);
          return;
        }
      } catch (error) {
        if (options.signal?.aborted) throw error;
      }
    }
    drop(slots);
    out.dropped.push(id);
  });
  if (out.dropped.length) {
    options.onStatus?.(`Manim: ${out.dropped.join(", ")} could not be written by ${options.model}; left out (the lines are still said).`);
  }
  return out;
}

/**
 * The figures the compiler's errors name (by "chapter C beat B"), sent back to the Manim model with what was wrong;
 * how many were rewritten. The section is not asked again for them.
 */
export async function repairManim(script: Record<string, unknown>, errors: string[], options: ManimCoderOptions): Promise<number> {
  const slots = slotsOf(script);
  const byWhere = new Map<string, string>();
  for (const [id, list] of slots) for (const s of list) byWhere.set(s.where, id);
  const named = new Map<string, string[]>();
  for (const error of errors) {
    const at = /chapter (\d+) beat (\d+)/.exec(error);
    const id = at ? byWhere.get(`chapter ${at[1]} beat ${at[2]}`) : undefined;
    if (id && /manim|block/i.test(error)) named.set(id, [...(named.get(id) ?? []), error]);
  }
  let fixed = 0;
  await eachAtOnce([...named], async ([id, why]) => {
    const list = slots.get(id)!;
    for (const s of list) s.plan = s.plan || planOf.get(String(s.op.code ?? "")) || "";
    try {
      const blocks = await ask(id, list, options, { errors: why });
      if (blocks) {
        written.set(memoKey(id, list), blocks);
        put(list, blocks);
        fixed += 1;
      }
    } catch (error) {
      if (options.signal?.aborted) throw error;
    }
  });
  return fixed;
}
