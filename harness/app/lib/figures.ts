/**
 * The book's figures redrawn as SVG by the model, for the lecture board.
 *
 * A textbook diagram shown as it is (a scan) looks poor on the board, and rebuilding it out of the engine's own
 * shapes loses most of it. Instead the model looks at each figure and writes it as a clean SVG: the same parts,
 * labels and arrows, each part in a <g id> the lecture can reveal and point at, colours named so they follow the
 * board's style, and SMIL animation only where the figure shows something moving (current in a wire, a wave, an
 * orbit). harness/lecture/svgcheck.py reads each one the way the engine will draw it; what fails goes back to the
 * model with the reason, twice at most. The lecture shows a drawn figure with {"op":"figure","id":...}; the engine
 * draws it (pocket_lecture.svg_figure, animsvg.py) and the exporter turns it into shapes for the phone.
 *
 * Drawings are kept next to the figure (fig3.png -> fig3.drawn.svg, fig3.drawn.json), so a second lecture from the
 * same book reuses them.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

/** Bumped when the prompt or the rules change: older drawings are made again. */
export const DRAWING_VERSION = 1;
/** Figures drawn at once. */
const AT_ONCE = Number(process.env.PANIM_FIGURE_DRAWERS ?? 4);
/** Rounds of "here is what is wrong, fix it". */
const REPAIRS = 2;

export type FigureInfo = { id: string; file: string; caption: string; page?: number | null };

export type Drawn = {
  /** The figure is a photograph: shown as it is, not drawn. */
  photo?: boolean;
  /** The SVG file, when it was drawn and passed the check. */
  svg?: string;
  /** Its parts, in drawing order, and the words in each (for the script writer to point at). */
  parts?: string[];
  labels?: Record<string, string>;
  /** It has SMIL animation. */
  animated?: boolean;
  /** Why it could not be drawn (it is then built in Manim, as before). */
  failed?: string;
};

export const SVG_PROMPT = [
  "You redraw ONE figure from a textbook as a clean SVG diagram for a teacher's board in a video lecture.",
  "Reply with the SVG alone in a ```svg block. If the figure is a PHOTOGRAPH (real people, a place, a specimen, an",
  "object as photographed) that no drawing can replace, reply with the single word PHOTO instead.",
  "",
  "WHAT TO DRAW: what the figure shows and teaches: the same parts, labels, arrows, numbers and layout, cleaner.",
  "Flat shapes and clear lines, as a good teacher draws on a board: no shading, textures or tiny details.",
  "",
  "RULES (a checker reads it the way the board draws it, and sends back what breaks them):",
  '- <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 H">, width 800, H to suit the figure (300-600).',
  "- Elements: g, path, rect, circle, ellipse, line, polyline, polygon, text, tspan, and for animation animate and",
  "  animateTransform. NOT image, style, filter, mask, clipPath, pattern, gradients, foreignObject or script.",
  "- Colours by NAME, not hex, so the drawing suits a dark or a light board: INK (lines and words), MUTED (faint",
  "  guides, axes, dashed construction lines), ROSE (forces), GREEN (velocities, normals), GOLD (angles, highlights),",
  "  RIVER (water, blue things), TERRA, TEAL, VIOLET, SAND, DUNE (fills: use fill-opacity 0.3-0.6 for large areas),",
  "  BOARD (the board itself: to blank out a wire behind a symbol drawn over it).",
  '  fill="none" for open outlines. Lines 3-6 wide.',
  "- Labels: <text> at font-size 24-34 with text-anchor, plain Unicode for symbols (θ, μ, ₁, ², →, Ω, °), never",
  "  LaTeX; beside what they name, never on top of a line. No title or caption text: the lecture shows the caption.",
  '- PARTS: wrap each thing the teacher will point at in <g id="...">: a short id in letters, digits and _ (block,',
  "  mg, normal, theta, battery, r1, nucleus, xylem), each label inside the group of the thing it names. Every",
  "  visible thing belongs to a part. Ids are unique.",
  "- ANIMATION ONLY IF IT TEACHES: only when the figure shows a process or motion (current flowing round a",
  "  circuit, blood through the heart, a wave travelling, a planet in orbit, a piston pushing, particles moving,",
  "  water evaporating). A structure, an apparatus at rest, a graph or a labelled organ stays still: no animation.",
  '  When it moves, put SMIL inside the moving part: <animateTransform attributeName="transform" type="translate"',
  '  (or rotate, scale) values="0 0; 40 0; 0 0" dur="2s" repeatCount="indefinite" additive="sum"/>, <animate',
  '  attributeName="opacity" .../>, or a dashed path (stroke-dasharray) with <animate attributeName="stroke-dashoffset"',
  '  values="0; -40" .../> for something flowing along a line. dur 0.5s, 1s, 2s or 4s; repeatCount="indefinite".',
  "  Animate transforms and opacity only (not d, width or points).",
  "- Under 30 KB, no comments.",
].join("\n");

function drawnPaths(figure: FigureInfo): { svg: string; meta: string } {
  const base = figure.file.replace(/\.[a-z0-9]+$/i, "");
  return { svg: `${base}.drawn.svg`, meta: `${base}.drawn.json` };
}

/** The words of the book around a figure's marker, for the drawer to know what it is for. */
export function figureContext(markdown: string, id: string, around = 900): string {
  const at = markdown.search(new RegExp(`\\[FIGURE ${id}:`));
  if (at < 0) return "";
  return markdown.slice(Math.max(0, at - around), at + around).replace(/\s+/g, " ").trim();
}

/** The SVG in a reply (a ```svg block, or a bare <svg>...</svg>), "PHOTO", or null. */
export function svgOf(reply: string): string | "PHOTO" | null {
  const text = reply.trim();
  if (/^PHOTO\b/i.test(text) || /^```\s*PHOTO\s*```$/i.test(text)) return "PHOTO";
  const fenced = /```(?:svg|xml)?\s*([\s\S]*?<svg[\s\S]*?<\/svg>)\s*```/i.exec(text);
  if (fenced) return fenced[1].trim();
  const bare = /<svg[\s\S]*<\/svg>/i.exec(text);
  return bare ? bare[0] : null;
}

type Part = { type: "text"; text: string } | { type: "image_url"; image_url: { url: string } };
type Message = { role: "system" | "user" | "assistant"; content: string | Part[] };

/** One chat completion (not streamed): the reply's text, and what it cost. */
async function ask(key: string, model: string, messages: Message[], signal?: AbortSignal):
  Promise<{ text: string; cost: number }> {
  let last: unknown = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        signal,
        headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model, messages, max_tokens: 12000, usage: { include: true } }),
      });
      if (!response.ok) throw new Error(`OpenRouter ${response.status}: ${(await response.text()).slice(0, 300)}`);
      const body = (await response.json()) as {
        choices?: { message?: { content?: string | { text?: string }[] } }[]; usage?: { cost?: number };
      };
      const content = body.choices?.[0]?.message?.content;
      const text = typeof content === "string" ? content : (content ?? []).map((c) => c.text ?? "").join("");
      if (!text.trim()) throw new Error("an empty reply");
      return { text, cost: body.usage?.cost ?? 0 };
    } catch (error) {
      if (signal?.aborted) throw error;
      last = error;
      await new Promise((r) => setTimeout(r, 1500 * attempt));
    }
  }
  throw last instanceof Error ? last : new Error(String(last));
}

type Check = { ok: boolean; errors: string[]; warnings?: string[]; parts: string[]; labels?: Record<string, string>;
  animated?: boolean };

/** svgcheck.py on these SVG files: what the board makes of each. */
export function checkSvgs(repo: string, python: string, files: Record<string, string>): Promise<Record<string, Check>> {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [path.join(repo, "harness", "lecture", "svgcheck.py")], { cwd: repo });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", reject);
    child.on("close", (code) => {
      try {
        resolve(JSON.parse(out.trim().split("\n").pop() || "{}"));
      } catch {
        reject(new Error(`svgcheck failed (${code}): ${err.slice(-400)}`));
      }
    });
    child.stdin.end(JSON.stringify({ figures: Object.entries(files).map(([id, svg]) => ({ id, svg })) }));
  });
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
 * Draw each figure as an SVG (or find it drawn already). Returns what became of each, by id. Figures that cannot
 * be drawn come back with `failed` and the lecture builds them in Manim as before.
 */
export async function drawFigures(
  figures: FigureInfo[],
  options: {
    key: string;
    model: string;
    markdown: string;
    repo: string;
    python: string;
    signal?: AbortSignal;
    onStatus?: (text: string) => void;
    onCost?: (usd: number) => void;
  },
): Promise<Record<string, Drawn>> {
  const out: Record<string, Drawn> = {};
  const todo: FigureInfo[] = [];
  for (const figure of figures) {
    const { meta } = drawnPaths(figure);
    try {
      const kept = JSON.parse(await readFile(meta, "utf8"));
      if (kept.version === DRAWING_VERSION && (kept.photo || (kept.svg && existsSync(kept.svg)))) {
        out[figure.id] = kept;
        continue;
      }
    } catch {
      // not drawn yet
    }
    todo.push(figure);
  }
  if (!todo.length) return out;
  options.onStatus?.(`Drawing the book's ${todo.length} figure${todo.length > 1 ? "s" : ""} as SVG for the board.`);
  let done = 0;

  const drawOne = async (figure: FigureInfo): Promise<Drawn> => {
    const image = await picture(figure.file);
    const context = figureContext(options.markdown, figure.id);
    const ask0: Part[] = [{
      type: "text",
      text: `Figure ${figure.id}${figure.page ? ` (page ${figure.page})` : ""}: ${figure.caption || "(no caption)"}` +
        (context ? `\n\nThe book around it:\n${context}` : "") + "\n\nRedraw it as the SVG (or reply PHOTO).",
    }];
    if (image) ask0.push({ type: "image_url", image_url: { url: image } });
    const messages: Message[] = [{ role: "system", content: SVG_PROMPT }, { role: "user", content: ask0 }];
    const { svg: file } = drawnPaths(figure);
    for (let round = 0; round <= REPAIRS; round++) {
      const reply = await ask(options.key, options.model, messages, options.signal);
      options.onCost?.(reply.cost);
      const svg = svgOf(reply.text);
      if (svg === "PHOTO") return { photo: true };
      messages.push({ role: "assistant", content: reply.text });
      if (!svg) {
        messages.push({ role: "user", content: "No SVG came back. Reply with the SVG in a ```svg block, or PHOTO." });
        continue;
      }
      await writeFile(file, svg, "utf8");
      const check = (await checkSvgs(options.repo, options.python, { [figure.id]: file }))[figure.id];
      if (check?.ok) {
        return { svg: file, parts: check.parts, labels: check.labels ?? {}, animated: !!check.animated };
      }
      messages.push({
        role: "user",
        content: `The board cannot use it yet:\n- ${(check?.errors ?? ["it could not be read"]).join("\n- ")}\n` +
          "Send the corrected SVG, whole, in a ```svg block.",
      });
    }
    return { failed: "the SVG did not pass the board's checks" };
  };

  const queue = [...todo];
  const workers = Array.from({ length: Math.max(1, Math.min(AT_ONCE, queue.length)) }, async () => {
    for (let figure = queue.shift(); figure; figure = queue.shift()) {
      let drawn: Drawn;
      try {
        drawn = await drawOne(figure);
      } catch (error) {
        if (options.signal?.aborted) throw error;
        drawn = { failed: String(error instanceof Error ? error.message : error).slice(0, 200) };
      }
      out[figure.id] = drawn;
      if (!drawn.failed) {
        await writeFile(drawnPaths(figure).meta, JSON.stringify({ ...drawn, version: DRAWING_VERSION }), "utf8");
      }
      done++;
      options.onStatus?.(`Figure ${figure.id} ${drawn.photo ? "is a photograph (shown as it is)" : drawn.svg
        ? `drawn as SVG${drawn.animated ? ", moving" : ""} (${(drawn.parts ?? []).length} parts)`
        : `not drawn (${drawn.failed}); built on the board instead`} — ${done} of ${todo.length}.`);
    }
  });
  await Promise.all(workers);
  return out;
}

/** A figure's line in the script writer's prompt: how to show it, and its parts to reveal. */
export function drawnLine(figure: FigureInfo, drawn?: Drawn): string {
  const head = `  ${figure.id}: ${figure.caption}${figure.page ? ` (page ${figure.page})` : ""}`;
  if (drawn?.photo) return `${head} — a photograph: {"op":"figure","id":"${figure.id}","photo":true}`;
  if (drawn?.svg) {
    const parts = (drawn.parts ?? []).map((p) => (drawn.labels?.[p] ? `${p} (${drawn.labels[p]})` : p)).join(", ");
    return `${head} — drawn as SVG${drawn.animated ? ", it moves by itself" : ""}; parts: ${parts}`;
  }
  return `${head} — build it on the board (sketch, preset, graph, diagram) marked "from_figure":"${figure.id}"`;
}
