/**
 * The book's figures, as a video lecture shows them: never the book's own picture. Every figure -- a labelled
 * diagram, a graph, an apparatus, a photograph -- is redrawn by the diagram model from the figure itself as an exact
 * copy: the same layout, parts, arrows, numbers and labels letter for letter, in the lecture's style, with the
 * watermarks, logos, QR codes, figure numbers, captions and scan marks left out; checked label by label against the
 * book's and redrawn with what was wrong (genimage.py --redraw). A figure that cannot be redrawn at all (no image
 * model, refused) is left out of the lecture's figures, and the script writer rebuilds it in Manim instead.
 *
 * What each figure became is kept next to it (fig3.png -> fig3.drawn.json), so a second lecture from the same book
 * does not ask again. A figure decided under an older version (DRAWING_VERSION) is made again.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

/** Bumped when the prompt or the routes change: older decisions are made again (7: every figure redrawn). */
export const DRAWING_VERSION = 7;
/** Figures redrawn at once. */
const AT_ONCE = Number(process.env.PANIM_FIGURE_DRAWERS ?? 4);

export type FigureInfo = { id: string; file: string; caption: string; page?: number | null };

export type Drawn = {
  /** Shown as a picture (always, once redrawn): the figure op takes "photo": true. */
  photo?: boolean;
  /** Redrawn by the diagram model from the figure itself, in the lecture's style (genimage.redraw). */
  diagram?: boolean;
  /** The redrawn picture, shown in place of the book's. With none, the figure is not shown at all. */
  generated?: { file: string; title?: string; credit?: string; license?: string };
  /** Whether every label was found right in the redraw (false: the closest try is kept; `issues` says what). */
  checked?: boolean;
  issues?: string;
  /** Why it could not be redrawn (it is left out, rebuilt in Manim by the writer, and tried again next run). */
  diagramError?: string;
  /** What redrawing it cost (US dollars), kept with it so a later run can say so. */
  usd?: number;
};

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

export type SettleOptions = {
  repo: string;
  python: string;
  signal?: AbortSignal;
  onCost?: (usd: number) => void;
};

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
 * A book's diagram redrawn by the diagram model (genimage.py --redraw): from the figure itself, in the lecture's
 * style, every label kept, checked against the book's and redrawn with what was wrong; the closest try is kept when
 * none passes. Undefined generated (and the reason) only when the model made nothing: the figure is then left out.
 */
export async function redrawDiagram(figure: FigureInfo, context: string, options: SettleOptions & { style?: string }):
  Promise<{ generated?: Drawn["generated"]; checked?: boolean; issues?: string; error?: string; usd: number }> {
  const script = path.join(options.repo, "harness", "lecture", "genimage.py");
  const args = [script, "--redraw", figure.file, "--caption", figure.caption || "", "--context", context.slice(0, 600),
    ...(options.style ? ["--style", options.style] : [])];
  try {
    const row = JSON.parse((await runPython(options.python, options.repo, args, options.signal))
      .trim().split("\n").pop() || "null") as { file?: string; title?: string; credit?: string; usd?: number;
      error?: string; ok?: boolean | null; check?: { missing?: string[]; wrong?: string[]; notes?: string } } | null;
    const usd = Number(row?.usd ?? 0);
    if (usd) options.onCost?.(usd);
    if (row?.file) {
      const issues = [...(row.check?.missing ?? []).map((l) => `missing ${l}`), ...(row.check?.wrong ?? []).map((l) => `wrong ${l}`)]
        .join(", ") || (row.ok === false ? row.check?.notes ?? "" : "");
      return { generated: { file: row.file, title: row.title || figure.caption, credit: row.credit },
        checked: row.ok !== false, ...(issues ? { issues: issues.slice(0, 200) } : {}), usd };
    }
    return { error: row?.error || "the diagram model made nothing", usd };
  } catch (error) {
    if (options.signal?.aborted) throw error;
    return { error: String(error instanceof Error ? error.message : error).slice(0, 200), usd: 0 };
  }
}

/**
 * Redraw each figure (or find it redrawn already). Returns what became of each, by id.
 */
export async function drawFigures(
  figures: FigureInfo[],
  options: {
    markdown: string;
    repo: string;
    python: string;
    signal?: AbortSignal;
    onStatus?: (text: string) => void;
    onCost?: (usd: number) => void;
    /** Each figure as soon as it is settled (found redrawn, redrawn now, or not), for a caller that will not wait
     * for all; `kept` when an earlier run redrew it (and it cost nothing now). */
    onDrawn?: (id: string, drawn: Drawn, kept: boolean) => void;
    /** How long a figure redrawn now took (ms since the epoch), whatever came of it. */
    onTime?: (start: number, end: number) => void;
    /** The lecture's style: every figure is redrawn in it. */
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
      if (kept.version === DRAWING_VERSION && kept.generated && existsSync(kept.generated.file)) {
        out[figure.id] = kept;
        options.onDrawn?.(figure.id, kept, true);
        continue;
      }
    } catch {
      // not redrawn yet
    }
    todo.push(figure);
  }
  if (!todo.length) return out;
  options.onStatus?.(`Redrawing the book's ${todo.length} figure${todo.length > 1 ? "s" : ""} with the diagram model: ` +
    "each an exact copy in the lecture's style, watermarks and page marks left out, its labels checked against the " +
    "book's. The book's own pictures are never shown.");
  let done = 0;

  const drawOne = async (figure: FigureInfo): Promise<Drawn> => {
    let usd = 0;
    const redrawn = await redrawDiagram(figure, figureContext(options.markdown, figure.id), { ...options,
      onCost: (cost) => {
        usd += cost;
        options.onCost?.(cost);
      } });
    if (!redrawn.generated) return { diagramError: redrawn.error, usd };
    return { photo: true, diagram: true, generated: redrawn.generated, checked: redrawn.checked,
      ...(redrawn.issues ? { issues: redrawn.issues } : {}), usd };
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
        drawn = { diagramError: String(error instanceof Error ? error.message : error).slice(0, 200) };
      }
      options.onTime?.(began, Date.now());
      out[figure.id] = drawn;
      options.onDrawn?.(figure.id, drawn, false);
      if (drawn.generated) {
        await writeFile(drawnPaths(figure).meta, JSON.stringify({ ...drawn, version: DRAWING_VERSION }), "utf8");
      }
      done++;
      options.onStatus?.(`Figure ${figure.id} ${drawn.generated
        ? `redrawn by the diagram model in the lecture's style${drawn.checked ? ", every label checked"
          : ` (the closest try kept: ${drawn.issues || "not every label matched"})`}`
        : `could not be redrawn (${drawn.diagramError ?? "no picture"}): left out, rebuilt on the board instead`}` +
        ` — ${done} of ${todo.length}.`);
    }
  });
  await Promise.all(workers);
  return out;
}

/** A figure's line in the script writer's prompt: how to show it. */
export function drawnLine(figure: FigureInfo, drawn?: Drawn): string {
  const head = `  ${figure.id}: ${figure.caption}${figure.page ? ` (page ${figure.page})` : ""}`;
  if (drawn?.generated) return `${head} — redrawn as a picture with its labels: ` +
    `{"op":"figure","id":"${figure.id}","photo":true,"where":"stage"} (no parts to reveal)`;
  return `${head} — not available as a picture: build it on the board in full detail, every value and label of ` +
    `the book's figure (sketch, preset, graph, diagram, or a manim op), marked "from_figure":"${figure.id}"`;
}

/** How long stage 2 waits for the book's figures, from when their drawing began (PANIM_FIGURE_WAIT_SECONDS). */
const FIGURE_WAIT_MS = Math.max(0, Number(process.env.PANIM_FIGURE_WAIT_SECONDS ?? 420)) * 1000;

/**
 * The book's figures once all are settled, or, if that takes longer than FIGURE_WAIT_MS, the ones settled by then
 * (the rest are rebuilt in Manim on this run; their redraws are kept for the next). Never the book's own picture.
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
    "the script goes on without waiting, and the rest are built in Manim this time (their redraws are kept for the next run).");
  return Object.keys(settled).length ? settled : undefined;
}
