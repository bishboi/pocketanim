/**
 * Every picture a lecture builds, drawn as an SVG by the model.
 *
 * The script writer does not draw: it says what a picture shows and names the parts it will point at,
 *   {"op":"draw","id":"ramp","what":"a 2 kg block on a smooth 30° incline; its weight mg straight down; ...",
 *    "parts":["wedge","block","theta","mg","N"],"show"?:["wedge","block"],"moves"?:"the block slides down"}
 * and reveals and focuses on those parts on the beats that follow. Before each compile, this pass asks the model
 * for each such picture as an SVG (the same rules as the book's figures, figures.ts), with exactly those part ids
 * as <g> groups and animation only for what "moves" says. svgcheck.py reads each one the way the board draws it;
 * what fails goes back with the reason. The SVG's path goes on a copy of the op for the compiler
 * (pocket_lecture.svg_figure); a picture that could not be drawn carries why, and the compiler sends that back.
 *
 * Drawings are cached by what they show (harness/lecture/.cache/drawings), so a script compiled again, or two
 * lectures with the same picture, draw it once. Pictures are drawn several at once.
 */

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { SVG_RULES, settle, type Message } from "./figures";

/** Bumped when the prompt or the rules change: older drawings are made again. */
export const DRAW_VERSION = 3;
const AT_ONCE = Number(process.env.PANIM_DRAWERS ?? 4);

export const DRAW_PROMPT = [
  "You draw ONE picture for a teacher's board in a video lecture, as an SVG, from the teacher's description of it.",
  "Reply with the SVG alone in a ```svg block.",
  "",
  "WHAT TO DRAW: exactly what the description says: every thing, label, arrow, angle and number in it, laid out",
  "clearly, as a good teacher draws on a board: flat shapes, clean lines, no shading or tiny details. Correct for",
  "the subject (forces from the body they act on, rays obeying the laws of reflection, a cell's organelles inside",
  "it, a circuit closed). Big enough to read from the back of a class.",
  "",
  "PARTS: you are given the part ids. Each is one <g id=\"...\"> with EXACTLY that id, holding that thing and its",
  "label; every visible thing belongs to one of them. The lecture reveals and points at these ids, often one at a",
  "time, so each part must make sense drawn alone on top of the parts before it.",
  "MOTION: animate ONLY what MOVES says, and only that part. With no MOVES, nothing moves: no animation at all.",
  "",
  SVG_RULES,
].join("\n");

type DrawOp = { op: "draw"; id?: string; what: string; parts: string[]; moves?: string; show?: string[];
  svg?: string; _draw_error?: string };

export type DrawOptions = {
  key: string;
  model: string;
  repo: string;
  python: string;
  signal?: AbortSignal;
  onStatus?: (text: string) => void;
  onCost?: (usd: number) => void;
  /** A picture newly drawn as SVG (one from the cache is not counted). */
  onDrawn?: () => void;
};

/** Where a picture's drawing is kept: named by what it shows. */
function cachePaths(repo: string, op: DrawOp): { svg: string; meta: string } {
  const digest = createHash("sha1")
    .update(JSON.stringify({ v: DRAW_VERSION, what: op.what.trim(), parts: op.parts, moves: op.moves?.trim() ?? "" }))
    .digest("hex").slice(0, 16);
  const dir = path.join(repo, "harness", "lecture", ".cache", "drawings");
  return { svg: path.join(dir, `${digest}.svg`), meta: path.join(dir, `${digest}.json`) };
}

/** Each draw op in a script (a problem's figure too), with the line it is said on and its chapter. */
function drawOps(script: unknown): { op: DrawOp; say: string; chapter: string }[] {
  const out: { op: DrawOp; say: string; chapter: string }[] = [];
  const chapters = (script as { chapters?: { title?: string; beats?: { say?: string; do?: Record<string, unknown>[] }[] }[] })
    ?.chapters ?? [];
  for (const chapter of chapters) {
    for (const beat of chapter.beats ?? []) {
      for (const op of beat.do ?? []) {
        const figure = op?.op === "problem" ? (op.figure as Record<string, unknown> | undefined) : undefined;
        for (const candidate of [op, figure]) {
          if (candidate?.op === "draw" && typeof candidate.what === "string" && Array.isArray(candidate.parts)) {
            out.push({ op: candidate as unknown as DrawOp, say: String(beat.say ?? ""), chapter: String(chapter.title ?? "") });
          }
        }
      }
    }
  }
  return out;
}

/** Draw one picture (or find it drawn): the SVG's path, or why it could not be drawn. */
async function drawOne(op: DrawOp, say: string, chapter: string, options: DrawOptions):
  Promise<{ svg?: string; error?: string }> {
  const { svg: file, meta } = cachePaths(options.repo, op);
  if (existsSync(file) && existsSync(meta)) return { svg: file };
  await mkdir(path.dirname(file), { recursive: true });
  const ask0 = [
    `THE PICTURE: ${op.what.trim()}`,
    `PARTS (each a <g id>, exactly these ids): ${op.parts.join(", ")}`,
    op.moves?.trim() ? `MOVES: ${op.moves.trim()}` : "MOVES: nothing (a still picture: no animation)",
    "",
    `It goes with this line of the lecture${chapter ? ` (chapter "${chapter}")` : ""}: "${say}"`,
  ].join("\n");
  const messages: Message[] = [{ role: "system", content: DRAW_PROMPT }, { role: "user", content: ask0 }];
  // Drawn, checked, repaired, then looked at as the board shows it and fixed (figures.ts settle).
  const made = await settle(messages, file, op.parts, options);
  if (!made.svg || !made.check) return { error: made.error ?? "the SVG did not pass the board's checks" };
  await writeFile(meta, JSON.stringify({ version: DRAW_VERSION, what: op.what, parts: made.check.parts,
    animated: !!made.check.animated }), "utf8");
  options.onDrawn?.();
  return { svg: file };
}

/**
 * A copy of the script with every draw op drawn: `svg` on each op that was, `_draw_error` on each that was not,
 * and `drawn: true` so the compiler knows the pass ran.
 */
export async function drawScript(script: unknown, options: DrawOptions): Promise<unknown> {
  if (!script || typeof script !== "object") return script;
  const copy = JSON.parse(JSON.stringify(script)) as Record<string, unknown>;
  const ops = drawOps(copy);
  if (!ops.length) return copy;
  const pending = new Map<string, Promise<{ svg?: string; error?: string }>>();
  const fresh = ops.filter(({ op }) => {
    const { svg, meta } = cachePaths(options.repo, op);
    return !(existsSync(svg) && existsSync(meta));
  }).length;
  if (fresh) options.onStatus?.(`Drawing ${fresh} picture${fresh > 1 ? "s" : ""} as SVG for the board.`);
  const queue = [...ops];
  let done = 0;
  const workers = Array.from({ length: Math.max(1, Math.min(AT_ONCE, queue.length)) }, async () => {
    for (let item = queue.shift(); item; item = queue.shift()) {
      const key = cachePaths(options.repo, item.op).svg;
      if (!pending.has(key)) {
        pending.set(key, drawOne(item.op, item.say, item.chapter, options).catch((error) => {
          if (options.signal?.aborted) throw error;
          return { error: String(error instanceof Error ? error.message : error).slice(0, 200) };
        }));
      }
      const result = await pending.get(key)!;
      if (result.svg) item.op.svg = result.svg;
      else item.op._draw_error = result.error;
      done++;
    }
  });
  await Promise.all(workers);
  if (fresh) {
    const failed = ops.filter(({ op }) => !op.svg).length;
    options.onStatus?.(`Pictures drawn: ${done - failed} of ${done}${failed ? ` (${failed} sent back to describe again)` : ""}.`);
  }
  copy.drawn = true;
  return copy;
}

/** The picture a draw op points at, for a caller that wants the file (a preview). */
export async function drawnSvg(repo: string, op: DrawOp): Promise<string | null> {
  const { svg } = cachePaths(repo, op);
  return existsSync(svg) ? readFile(svg, "utf8") : null;
}
