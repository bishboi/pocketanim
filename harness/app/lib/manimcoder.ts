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
import { FREE_DRAWN_OPS, MANIM_RULES } from "./lecture";

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
  onCost?: (usd: number, span: [number, number], tokens: { in: number; out: number }, detail?: Record<string, unknown>) => void;
  onStatus?: (text: string) => void;
};

/** How long one figure's request may take before it is given up on and asked again (PANIM_MANIM_TIMEOUT_SECONDS):
 * a request the connection left hanging held its section, and the lecture, for ever. */
const TIMEOUT_MS = Math.max(1, Number(process.env.PANIM_MANIM_TIMEOUT_SECONDS) || 150) * 1000;
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
const memoKey = (id: string, slots: Slot[]) =>
  JSON.stringify([id, slots[0]?.op.area ?? "", slots.map((s) => [s.say, s.plan, s.figure ?? ""])]);

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

/**
 * How hard the Manim model thinks before it writes a figure: PANIM_MANIM_REASONING_EFFORT = minimal, low, medium,
 * high or xhigh. Empty (the default), "off" or anything else sends no setting: the model's own default.
 */
export function manimReasoning(): { reasoning?: { effort: string } } {
  const effort = (process.env.PANIM_MANIM_REASONING_EFFORT ?? "").trim().toLowerCase();
  return ["minimal", "low", "medium", "high", "xhigh"].includes(effort) ? { reasoning: { effort } } : {};
}

/** The blocks of one figure from the model: one code string a beat, or null when its reply will not do. */
async function ask(id: string, slots: Slot[], options: ManimCoderOptions, fix?: { errors: string[] }): Promise<string[] | null> {
  // "area": "left" (the figure's first beat decides): drawn in the left half, a working or a card beside it.
  const left = slots[0]?.op.area === "left";
  const lines = [
    `The lecture's style: ${options.style ?? "atlas"}. The figure's id: ${id}. Its ${slots.length} beat${slots.length > 1 ? "s" : ""}:`,
    ...(left ? ["Its area is the LEFT HALF of the board: keep everything within x from -6.9 to -0.4 (a working or a " +
      "card fills the right half, beside it, while later beats point at the figure)."] : []),
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
  const limit = AbortSignal.timeout(TIMEOUT_MS);
  const response = await fetch(process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    signal: options.signal ? AbortSignal.any([options.signal, limit]) : limit,
    headers: { Authorization: `Bearer ${options.key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: options.model, usage: { include: true }, response_format: { type: "json_object" },
      ...manimReasoning(),
      messages: [{ role: "system", content: SYSTEM }, { role: "user", content }] }),
  });
  if (!response.ok) throw new Error(`OpenRouter ${response.status}: ${(await response.text()).slice(0, 200)}`);
  const body = (await response.json()) as { choices?: { message?: { content?: string } }[];
    usage?: { cost?: number; prompt_tokens?: number; completion_tokens?: number } };
  options.onCost?.(body.usage?.cost ?? 0, [began, Date.now()],
    { in: body.usage?.prompt_tokens ?? 0, out: body.usage?.completion_tokens ?? 0 },
    { figure: id, beats: slots.length, repair: !!fix, model: options.model });
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
  const fresh = todo.filter(([id, slots]) => !written.has(memoKey(id, slots)));
  if (fresh.length) {
    options.onStatus?.(`Manim: ${options.model} is writing ${fresh.length} figure${fresh.length > 1 ? "s" : ""} ` +
      `(${fresh.map(([id]) => id).join(", ")}).`);
  }
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
        // Timed out, a dropped connection, an OpenRouter error: one more try, then the figure is left out.
        options.onStatus?.(`Manim: figure ${id}, try ${attempt + 1}: ${error instanceof Error && error.name === "TimeoutError"
          ? `no answer in ${TIMEOUT_MS / 1000} s` : String(error instanceof Error ? error.message : error).slice(0, 160)}` +
          `${attempt === 0 ? "; asking again." : "."}`);
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

/** Map operations: a chapter with one is drawn over its map, where a free-form block (the board's) cannot go. */
const MAP_OPS = new Set(["marker", "river", "path", "arrow", "state", "dim", "graticule", "journey", "empire", "relief", "icon"]);
/** Steps that point at a figure drawn earlier (by its id in "diagram"). */
const STEP_OPS = new Set(["reveal", "focus", "zoom", "motion", "trace", "sweep"]);
/** What may share a beat with a drawing turned free-form: said in its plan (words, an equation, a card). */
const FOLDED_OPS = new Set(["panel", "fact", "stat", "clear", "define", "equation", "work", "question", "answer", "option"]);

/**
 * The small built drawings the writer used although they are switched off (lecture.ts builtDrawings: presets,
 * sketch, graph, plot, motion, trace, sweep, sims, counter), turned into free-form Manim planned from what the op
 * said, for the Manim model to write: the first beat draws it, the later beats of the same id (a focus, a motion)
 * carry on with the same figure. A figure is left built where it cannot be free-form: in a chapter over a map, or
 * on a beat with a picture, a diagram or a timeline beside it. A problem's built figure is left out (its statement and
 * working stay). Returns how many figures were turned.
 */
export function freeDrawings(script: Record<string, unknown>): number {
  const drawn = new Set(FREE_DRAWN_OPS);
  const chapters = Array.isArray(script.chapters) ? (script.chapters as Record<string, unknown>[]) : [];
  let turned = 0;
  chapters.forEach((chapter, c) => {
    const beats = (Array.isArray(chapter?.beats) ? chapter.beats : []) as Record<string, unknown>[];
    const opsOf = (beat: Record<string, unknown>) => (Array.isArray(beat?.do) ? (beat.do as Op[]) : []);
    for (const beat of beats) {
      for (const op of opsOf(beat)) {
        const figure = op?.op === "problem" ? (op.figure as Op | undefined) : undefined;
        if (figure && drawn.has(String(figure.op))) delete op.figure;
      }
    }
    if (chapter.map === true || beats.some((b) => opsOf(b).some((op) => MAP_OPS.has(String(op?.op))))) return;
    // Each drawing's id (one is given where the op had none), and the beats that draw it or step on it.
    const ids = new Map<string, number[]>();
    beats.forEach((beat, b) => opsOf(beat).forEach((op, k) => {
      if (!op || typeof op !== "object") return;
      if (drawn.has(String(op.op)) && !STEP_OPS.has(String(op.op))) {
        const id = String(op.id ?? `draw${c + 1}_${b + 1}_${k + 1}`);
        op.id = id;
        ids.set(id, [...(ids.get(id) ?? []), b]);
      }
    }));
    beats.forEach((beat, b) => opsOf(beat).forEach((op) => {
      const id = String(op?.diagram ?? "");
      if (STEP_OPS.has(String(op?.op)) && ids.has(id)) ids.set(id, [...ids.get(id)!, b]);
    }));
    // A figure is free-form only if every beat it is on can be: nothing on them but it, its steps and words.
    const ok = [...ids].filter(([id, on]) => on.every((b) => opsOf(beats[b]).every((op) =>
      FOLDED_OPS.has(String(op?.op)) || (drawn.has(String(op?.op)) && !STEP_OPS.has(String(op?.op)) && String(op.id) === id)
      || (STEP_OPS.has(String(op?.op)) && String(op.diagram ?? "") === id))));
    for (const [id, on] of ok) {
      [...new Set(on)].sort((x, y) => x - y).forEach((b, n) => {
        const beat = beats[b];
        const parts = opsOf(beat).map((op) => {
          const { op: kind, ...rest } = op;
          const data = JSON.stringify(rest);
          if (drawn.has(String(kind)) && !STEP_OPS.has(String(kind))) {
            return `Draw this ${kind} (described as data: ${data}) on the board, labelled, in full detail` +
              (kind === "sim" || kind === "counter" ? ", moving over the line as it describes" : "") + ".";
          }
          if (STEP_OPS.has(String(kind))) return `Then on the same figure: ${kind} ${data}.`;
          return `Also show on the board: ${kind} ${data}.`;
        });
        const from = opsOf(beat).find((op) => typeof op.from_figure === "string")?.from_figure;
        beat.do = [{ op: "manim", id, plan: (n === 0 ? "" : "Carry on with the figure drawn on earlier beats. ") +
          parts.join(" "), ...(from ? { from_figure: from } : {}) }];
      });
      turned += 1;
    }
    if (ok.length) chapter.map = false;
  });
  return turned;
}
