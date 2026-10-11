/**
 * The book's figures, as a video lecture shows them. Each is looked at once by a model that reads images and
 * sorted three ways:
 *   - a photograph: made again by the illustration model as a cutout (genimage.py --realistic);
 *   - a figure the board's own shapes build exactly (a graph, an incline, a circuit, a flowchart): rebuilt in Manim
 *     by the script writer, in full detail;
 *   - any other drawing (a labelled diagram, a cell, a cross-section, an apparatus): redrawn by the diagram model
 *     from the figure itself, in the lecture's style, every label kept and checked (genimage.py --redraw).
 * Nothing is drawn as an SVG.
 *
 * What each figure became is kept next to it (fig3.png -> fig3.drawn.json), so a second lecture from the same book
 * does not ask again. A decision made under an older version (DRAWING_VERSION) is made again.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

/** Bumped when the prompt or the routes change: older decisions are made again (6: no SVG drawings). */
export const DRAWING_VERSION = 6;
/** Figures looked at at once. */
const AT_ONCE = Number(process.env.PANIM_FIGURE_DRAWERS ?? 4);

export type FigureInfo = { id: string; file: string; caption: string; page?: number | null };

export type Drawn = {
  /** Shown as a picture: a photograph (made again by the image model) or a diagram (redrawn by the diagram model). */
  photo?: boolean;
  /** What the photograph shows, in words, and the named thing in it (a person, a monument), if any. */
  query?: string;
  subject?: string;
  /** The picture the image model made of it (genimage.py), shown instead of the scan. */
  generated?: { file: string; title?: string; credit?: string; license?: string };
  /** A diagram, redrawn by the diagram model in the lecture's style from the figure itself (genimage.redraw), its
   * labels checked against the book's; with no `generated`, no redraw was true to it and the scan is shown. */
  diagram?: boolean;
  /** Why the diagram could not be redrawn (the scan is shown, and it is tried again on the next run). */
  diagramError?: string;
  /** The image model was asked for one (whether or not it made one), so a later run does not ask again. */
  looked?: boolean;
  /** The board's own shapes build it exactly (a graph, a preset, a sketch, a flowchart): it is rebuilt in Manim. */
  manim?: boolean;
  /** Why it could not be looked at (it is then built in Manim). */
  failed?: string;
  /** What deciding and redrawing it cost (US dollars), kept with it so a later run can say so. */
  usd?: number;
};

export const CLASSIFY_PROMPT = [
  "You look at ONE figure from a textbook and say how a video lecture should show it. Reply with exactly one of:",
  "- PHOTO: <in English, what it shows and how it is seen, most telling first, for an image model to make it again>",
  "  and, when it shows one named thing (a person, a monument, a place, a species), a second line SUBJECT: <its name>.",
  "  For a PHOTOGRAPH or a painting of a real person, place, building, specimen, animal, plant or object.",
  "- MANIM: for a figure the board's own shapes build EXACTLY and in full detail, every value and label in place: a",
  "  graph or plot, a block on an incline, a pulley, a spring, a pendulum, a projectile's path, a circuit, a lever,",
  "  a lens or mirror with its rays, a geometric construction, a vector diagram, a flowchart, a cycle or tree of",
  "  labelled boxes, a table, a bar chart. It is rebuilt there, exact and moving.",
  "- DIAGRAM: for every other drawing: a labelled diagram, a cell or an organ, a cross-section, an organism, an",
  "  apparatus or machine, a detailed structure, a historical map, a timeline chart, an annotated illustration. It",
  "  is redrawn by an image model from the figure itself in the lecture's style, every label kept.",
  "Reply with the one word (and for PHOTO its lines), nothing else.",
].join("\n");

/** Where what became of a figure is kept, and the SVG an older version drew beside it (removed when met). */
function drawnPaths(figure: FigureInfo): { meta: string; oldSvg: string } {
  const base = figure.file.replace(/\.[a-z0-9]+$/i, "");
  return { meta: `${base}.drawn.json`, oldSvg: `${base}.drawn.svg` };
}

/** The words of the book around a figure's marker, for the model to know what it is for. */
export function figureContext(markdown: string, id: string, around = 900): string {
  const at = markdown.search(new RegExp(`\\[FIGURE ${id}:`));
  if (at < 0) return "";
  return markdown.slice(Math.max(0, at - around), at + around).replace(/\s+/g, " ").trim();
}

/** A PHOTO reply's search words and subject: "PHOTO: Taj Mahal front view\nSUBJECT: Taj Mahal". */
export function photoWords(reply: string): { query?: string; subject?: string } {
  const text = reply.replace(/```/g, "").trim();
  const query = /^PHOTO\b[:\s-]*(.*)$/im.exec(text)?.[1]?.trim();
  const subject = /^SUBJECT\b[:\s-]*(.+)$/im.exec(text)?.[1]?.trim();
  return { ...(query ? { query: query.slice(0, 120) } : {}), ...(subject && subject !== "-" ? { subject: subject.slice(0, 80) } : {}) };
}

export type Part = { type: "text"; text: string } | { type: "image_url"; image_url: { url: string } };
export type Message = { role: "system" | "user" | "assistant"; content: string | Part[] };

/** One chat completion (not streamed): the reply's text, and what it cost. */
export async function ask(key: string, model: string, messages: Message[], signal?: AbortSignal):
  Promise<{ text: string; cost: number }> {
  let last: unknown = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        signal,
        headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model, messages, max_tokens: 24000, usage: { include: true } }),
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

export type SettleOptions = {
  key: string;
  model: string;
  repo: string;
  python: string;
  signal?: AbortSignal;
  onCost?: (usd: number) => void;
};

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

function runPython(python: string, repo: string, args: string[], signal?: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(python, args, { cwd: repo, signal });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", reject);
    child.on("close", (code) => (code === 0 ? resolve(out) : reject(new Error(`${args[0]} failed (${code}): ${err.slice(-300)}`))));
  });
}

/**
 * A book's photograph made again by the image model, as a cutout without a border (genimage.py), from what the
 * figure model said it shows. PANIM_PHOTO_REMAKE=0 keeps the book's own photos. Nothing is searched for on the web.
 */
export async function remakePhoto(figure: FigureInfo, query: string | undefined, subject: string | undefined,
  options: SettleOptions): Promise<Drawn["generated"] | undefined> {
  const what = [subject, query || figure.caption].filter(Boolean).join(": ");
  if (process.env.PANIM_PHOTO_REMAKE === "0" || !what.trim()) return undefined;
  const script = path.join(options.repo, "harness", "lecture", "genimage.py");
  try {
    const row = JSON.parse((await runPython(options.python, options.repo, [script, "--realistic", what], options.signal))
      .trim().split("\n").pop() || "null") as { file?: string; title?: string; credit?: string; license?: string;
      usd?: number } | null;
    if (row?.usd) options.onCost?.(row.usd);
    return row?.file ? { file: row.file, title: row.title, credit: row.credit, license: row.license } : undefined;
  } catch (error) {
    if (options.signal?.aborted) throw error;
    return undefined;                       // no key, refused, offline: the book's photo is shown
  }
}

/**
 * A book's diagram redrawn by the diagram model (genimage.py --redraw): from the figure itself, in the lecture's
 * style, every label kept, checked against the book's and redrawn with what was wrong. Undefined generated (and
 * the reason) when no redraw was true to the book: the scan is shown.
 */
export async function redrawDiagram(figure: FigureInfo, context: string, options: SettleOptions & { style?: string }):
  Promise<{ generated?: Drawn["generated"]; error?: string; usd: number }> {
  const script = path.join(options.repo, "harness", "lecture", "genimage.py");
  const args = [script, "--redraw", figure.file, "--caption", figure.caption || "", "--context", context.slice(0, 600),
    ...(options.style ? ["--style", options.style] : [])];
  try {
    const row = JSON.parse((await runPython(options.python, options.repo, args, options.signal))
      .trim().split("\n").pop() || "null") as { file?: string; title?: string; credit?: string; usd?: number;
      error?: string } | null;
    const usd = Number(row?.usd ?? 0);
    if (usd) options.onCost?.(usd);
    if (row?.file) return { generated: { file: row.file, title: row.title || figure.caption, credit: row.credit }, usd };
    return { error: row?.error || "the diagram model made nothing", usd };
  } catch (error) {
    if (options.signal?.aborted) throw error;
    return { error: String(error instanceof Error ? error.message : error).slice(0, 200), usd: 0 };
  }
}

/**
 * Look at each figure (or find it decided already) and make what it becomes: a photograph made again, a diagram
 * redrawn, or a note that it is rebuilt in Manim. Returns what became of each, by id.
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
    /** Each figure as soon as it is settled (found decided, decided now, or not), for a caller that will not wait
     * for all; `kept` when an earlier run decided it (and it cost nothing now). */
    onDrawn?: (id: string, drawn: Drawn, kept: boolean) => void;
    /** How long a figure looked at now took (ms since the epoch), whatever came of it. */
    onTime?: (start: number, end: number) => void;
    /** The lecture's style: a diagram is redrawn in it. */
    style?: string;
  },
): Promise<Record<string, Drawn>> {
  const out: Record<string, Drawn> = {};
  const todo: FigureInfo[] = [];
  for (const figure of figures) {
    const { meta, oldSvg } = drawnPaths(figure);
    // An SVG an older version drew beside the figure is never shown again.
    if (existsSync(oldSvg)) await rm(oldSvg, { force: true });
    try {
      const kept = JSON.parse(await readFile(meta, "utf8"));
      // A photograph decided before the image model was asked for one like it is looked at again.
      const photoDone = kept.photo && kept.looked && (!kept.generated || existsSync(kept.generated.file));
      if (kept.version === DRAWING_VERSION && (photoDone || kept.manim)) {
        out[figure.id] = kept;
        options.onDrawn?.(figure.id, kept, true);
        continue;
      }
    } catch {
      // not decided yet
    }
    todo.push(figure);
  }
  if (!todo.length) return out;
  options.onStatus?.(`Looking at the book's ${todo.length} figure${todo.length > 1 ? "s" : ""}: built in Manim where ` +
    "the board's shapes build it exactly; photographs made again by the illustration model; diagrams redrawn by " +
    "the diagram model in the lecture's style, their labels checked against the book's.");
  let done = 0;

  const drawOne = async (figure: FigureInfo): Promise<Drawn> => {
    const image = await picture(figure.file);
    const context = figureContext(options.markdown, figure.id);
    let usd = 0;
    const bill = (cost: number) => {
      usd += cost;
      options.onCost?.(cost);
    };
    const content: Part[] = [{ type: "text", text: `Figure ${figure.id}: ${figure.caption || "(no caption)"}` +
      (context ? `\n\nThe book around it:\n${context}` : "") }];
    if (image) content.push({ type: "image_url", image_url: { url: image } });
    const said = await ask(options.key, options.model,
      [{ role: "system", content: CLASSIFY_PROMPT }, { role: "user", content }], options.signal);
    bill(said.cost);
    const verdict = said.text.trim();
    if (/^PHOTO\b/i.test(verdict)) {
      const { query, subject } = photoWords(verdict);
      const found = await remakePhoto(figure, query, subject, { ...options, onCost: bill });
      return { photo: true, query, subject, looked: true, ...(found ? { generated: found } : {}), usd };
    }
    if (/^MANIM\b/i.test(verdict)) return { manim: true, usd };
    const redrawn = await redrawDiagram(figure, context, { ...options, onCost: bill });
    return { photo: true, diagram: true, looked: true, ...(redrawn.generated ? { generated: redrawn.generated }
      : { diagramError: redrawn.error }), usd };
  };

  const queue = [...todo];
  const workers = Array.from({ length: Math.max(1, Math.min(AT_ONCE, queue.length)) }, async () => {
    for (let figure = queue.shift(); figure; figure = queue.shift()) {
      let drawn: Drawn;
      const began = Date.now();
      try {
        drawn = await drawOne(figure);
      } catch (error) {
        if (options.signal?.aborted) throw error;
        drawn = { failed: String(error instanceof Error ? error.message : error).slice(0, 200) };
      }
      options.onTime?.(began, Date.now());
      out[figure.id] = drawn;
      options.onDrawn?.(figure.id, drawn, false);
      if (!drawn.failed && !drawn.diagramError) {
        await writeFile(drawnPaths(figure).meta, JSON.stringify({ ...drawn, version: DRAWING_VERSION }), "utf8");
      }
      done++;
      options.onStatus?.(`Figure ${figure.id} ${drawn.diagram ? (drawn.generated ? "is a diagram; redrawn by the diagram " +
          "model in the lecture's style, its labels checked against the book's" : `is a diagram; shown as the book's ` +
          `(not redrawn: ${drawn.diagramError ?? "no redraw kept its labels"})`) : drawn.photo ? (drawn.generated ? `is a photograph; made again by the image ` +
        `model as a cutout ("${drawn.generated.title ?? figure.caption}")` : "is a photograph (shown as it is: the image model made none)")
        : drawn.manim ? "is built in Manim" : `could not be looked at (${drawn.failed}); built on the board instead`} — ${done} of ${todo.length}.`);
    }
  });
  await Promise.all(workers);
  return out;
}

/** A figure's line in the script writer's prompt: how to show it. */
export function drawnLine(figure: FigureInfo, drawn?: Drawn): string {
  const head = `  ${figure.id}: ${figure.caption}${figure.page ? ` (page ${figure.page})` : ""}`;
  if (drawn?.diagram) return `${head} — a diagram, shown whole as a picture with its labels: ` +
    `{"op":"figure","id":"${figure.id}","photo":true,"where":"stage"} (no parts to reveal)`;
  if (drawn?.photo) return `${head} — a photograph: {"op":"figure","id":"${figure.id}","photo":true}`;
  return `${head} — build it on the board in full detail, every value and label of the book's figure (sketch, ` +
    `preset, graph, diagram, or a manim op), marked "from_figure":"${figure.id}"`;
}

/** How long stage 2 waits for the book's figures, from when their drawing began (PANIM_FIGURE_WAIT_SECONDS). */
const FIGURE_WAIT_MS = Math.max(0, Number(process.env.PANIM_FIGURE_WAIT_SECONDS ?? 120)) * 1000;

/**
 * The book's figures once all are settled, or, if that takes longer than FIGURE_WAIT_MS, the ones settled by then
 * (the rest are rebuilt in Manim on this run; their drawings are kept for the next).
 */
export async function figuresWithin(drawing: Promise<Record<string, Drawn> | undefined>, ready: Record<string, Drawn>,
  started: number, onStatus: (text: string) => void): Promise<Record<string, Drawn> | undefined> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), Math.max(0, FIGURE_WAIT_MS - (Date.now() - started)));
  });
  const done = await Promise.race([drawing.then((all) => ({ all })), late]);
  clearTimeout(timer);
  if (done) return done.all;
  const settled = { ...ready };
  onStatus(`${Object.keys(settled).length} of the book's figures were ready in ${Math.round(FIGURE_WAIT_MS / 1000)} s; ` +
    "the script goes on without waiting, and the rest are built in Manim this time (their drawings are kept for the next run).");
  return Object.keys(settled).length ? settled : undefined;
}
