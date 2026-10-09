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
import { readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

/** Bumped when the prompt or the rules change: older drawings are made again. */
export const DRAWING_VERSION = 4;
/** Figures drawn at once. */
const AT_ONCE = Number(process.env.PANIM_FIGURE_DRAWERS ?? 4);
/** Rounds of "here is what is wrong, fix it". */
const REPAIRS = 2;

export type FigureInfo = { id: string; file: string; caption: string; page?: number | null };

export type Drawn = {
  /** The figure is a photograph: shown as it is, not drawn. */
  photo?: boolean;
  /** The board's own shapes build it well (a graph, a preset, a sketch, a diagram): it is rebuilt in Manim. */
  manim?: boolean;
  /** The SVG file, when it was drawn and passed the check. */
  svg?: string;
  /** Its parts, in drawing order, and the words in each (for the script writer to point at). */
  parts?: string[];
  labels?: Record<string, string>;
  /** It has SMIL animation. */
  animated?: boolean;
  /** Why it could not be drawn (it is then built in Manim, as before). */
  failed?: string;
  /** What deciding and drawing it cost (US dollars), kept with the drawing so a later run can say so. */
  usd?: number;
};

export const SVG_RULES = [
  "RULES (a checker reads it the way the board draws it, and sends back what breaks them):",
  '- <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 H">, width 800, H to suit the figure (300-600).',
  "- Elements: g, path, rect, circle, ellipse, line, polyline, polygon, text, tspan, and for animation animate and",
  "  animateTransform. NOT image, style, filter, mask, clipPath, pattern, gradients, foreignObject or script.",
  "- Colours by NAME, not hex, so the drawing suits a dark or a light board: INK (lines and words), MUTED (faint",
  "  guides, axes, dashed construction lines), ROSE (forces), GREEN (velocities, normals), GOLD (angles, highlights),",
  "  RIVER (water, blue things), TERRA, TEAL, VIOLET, SAND, DUNE, RUST, OLIVE, MOUNT (fills: fill-opacity 0.3-0.8),",
  "  SHINE (highlights) and SHADE (shadows), both at fill-opacity 0.15-0.35, BOARD (the board itself: to blank out",
  "  a wire behind a symbol drawn over it).",
  '  fill="none" for open outlines. Main lines 3-5 wide, detail lines 1-2.',
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
  "- Under 70 KB, no comments.",
  "",
  "QUALITY (it is shown full screen to a class, on a phone, and judged against a good textbook figure):",
  "- Plan the layout before writing: where each thing goes on a grid, its size, where each label sits. Then write",
  "  coordinates that follow the plan. Use the whole viewBox with a margin of 30 or more on every side; the main",
  "  subject large and central; nothing crammed into a corner, nothing touching the edge.",
  "- Correct geometry and science: angles drawn at the angle they are (30° looks like 30°), forces from the point",
  "  they act on and in their true direction, perpendiculars perpendicular, parallel lines parallel, rays obeying",
  "  the laws of reflection and refraction, circuits closed, proportions believable.",
  "- Arrows: a line plus a filled triangle head (a polygon about 18 long and 14 wide) at the exact end, pointing",
  "  along the line; never <marker>. Force arrows long enough to read (80+).",
  "- Labels: every label clear of every line, arrow and other label (leave 8+ units of space); a leader line",
  "  (MUTED, thin) from a label to a small part when it cannot sit right beside it; the same size for labels of the",
  "  same kind; never upside down or rotated.",
  "- Consistent style: the same line width for the same kind of thing, a few colours with a meaning each (forces",
  "  one colour, motion another), fills light (fill-opacity 0.3-0.6) so lines and labels stay readable on top.",
  "- Smooth shapes: real curves (arcs, cubic Béziers) for round things, not jagged polylines.",
  "",
  "DETAIL (it is judged against a fine textbook illustration, not a sketch; aim for 60-200 shapes):",
  "- Depth without gradients: build each solid thing in layers: its base fill (fill-opacity 0.5-0.8), a shadow",
  "  shape along its lower or far side in the next darker colour of its family (SAND→DUNE→TERRA→RUST,",
  "  GREEN→OLIVE, RIVER→TEAL, or SHADE at fill-opacity 0.15-0.3), and a highlight shape on its lit side (SHINE at",
  "  fill-opacity 0.2-0.35). Light comes from the top left for every part.",
  "- Texture and structure: the real surface of a thing in fine lines (1-2 wide, MUTED or a darker shade): a leaf's",
  "  veins, muscle fibres, bark, brick courses, rock strata, a membrane's double line, cell walls, a wire's",
  "  insulation, screw threads, water ripples, fur, scales. A cross-section shows its layers, each a distinct fill.",
  "- The small features that make it recognisable and true: organelles inside a cell (ribosomes as dots, cristae",
  "  inside mitochondria), stomata on a leaf, valves in the heart, terminals and a filament in a bulb, rivets,",
  "  teeth on a gear, the meniscus in a tube, graduations on a scale. Several of each where the real thing has many.",
  "- Outlines: a firm outline (3-5 wide) round each main thing, thinner lines (1-2) for detail inside it.",
  "- Still clear: detail sits inside and on things, never across labels or arrows; the thing being taught stays",
  "  the strongest shape in the picture, and every label still has room.",
  "",
  "EDUCATIONAL (it teaches; it is not decoration):",
  "- Label every part the lesson names with the exact term students must learn (the textbook's word), and the key",
  "  values with their units (2 kg, 30°, 5 Ω, 10 m/s).",
  "- Make the idea being taught stand out: the part the lesson is about drawn largest or in the highlight colour,",
  "  the rest quieter (MUTED or thin) so the eye goes where the teacher points.",
  "- Show cause, direction and flow with arrows (what pushes what, which way blood, current, light, energy goes).",
  "- True to a good textbook: correct relative sizes and positions (the nucleus inside the cell, the left ventricle's",
  "  wall thicker than the right's), nothing scientifically wrong even if simplified.",
  "- One clear idea per picture: detail that makes the subject real and true, but no unrelated background scenery,",
  "  no faces, no parts the lesson never uses.",
].join("\n");

/** Rounds of looking at the drawing as the board shows it and fixing it (PANIM_SVG_REVIEWS; 0 turns it off). */
export const REVIEWS = Math.max(0, Number(process.env.PANIM_SVG_REVIEWS ?? 1));

export const REVIEW_PROMPT = [
  "Here is your SVG as the lecture's board shows it (the colour names become the board's colours; labels are set in",
  "the lecture's own font, so they may be a little wider than you planned). Look at it hard, as the teacher who will",
  "use it in front of a class:",
  "- Is everything asked for there, correct and in the right place (the science, the angles, the directions)?",
  "- Does it teach: every key part labelled with its proper term, the idea being taught standing out, arrows",
  "  showing what flows or acts and which way? Would a student learn the right thing from it alone?",
  "- Is any label on top of a line, an arrow, a shape or another label, cut off, or hard to read?",
  "- Is the layout clear and balanced: the subject large, nothing cramped, nothing stranded, arrows meeting what",
  "  they point at, shapes joined where they should be?",
  "- Is it as rich as a fine textbook illustration: solid things shaded (a shadow side, a highlight), real texture",
  "  and the small features that make each thing recognisable? A flat, bare outline is not finished: add the detail.",
  "If it is right and clear, reply with exactly LOOKS GOOD. Otherwise reply with the whole corrected SVG in a ```svg",
  "block (same part ids, same rules).",
].join("\n");

export const SVG_PROMPT = [
  "You redraw ONE figure from a textbook as a detailed, clean SVG illustration for a teacher's board in a video lecture.",
  "Reply with the SVG alone in a ```svg block. If the figure is a PHOTOGRAPH (real people, a place, a specimen, an",
  "object as photographed) that no drawing can replace, reply with the single word PHOTO instead.",
  "If the board builds it well from its own shapes -- a graph or plot, a block on an incline, a pulley, a spring,",
  "a pendulum, a projectile's path, a simple circuit, a lever, a lens or mirror with its rays, a geometric figure,",
  "a flowchart, a cycle or tree of labelled boxes, a table -- reply with the single word MANIM instead: it is",
  "rebuilt there. Draw an SVG only for what those shapes cannot show well: a cell or an organ, a cross-section,",
  "an organism, a real apparatus or machine, a detailed structure.",
  "",
  "WHAT TO DRAW: what the figure shows and teaches: the same parts, labels, arrows, numbers and layout, cleaner.",
  "Flat shapes and clear lines, as a good teacher draws on a board: no shading, textures or tiny details.",
  "",
  SVG_RULES,
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

/** The SVG in a reply (a ```svg block, or a bare <svg>...</svg>), "PHOTO", "MANIM", or null. */
export function svgOf(reply: string): string | "PHOTO" | "MANIM" | null {
  const text = reply.trim();
  if (/^PHOTO\b/i.test(text) || /^```\s*PHOTO\s*```$/i.test(text)) return "PHOTO";
  if (/^MANIM\b/i.test(text) || /^```\s*MANIM\s*```$/i.test(text)) return "MANIM";
  const fenced = /```(?:svg|xml)?\s*([\s\S]*?<svg[\s\S]*?<\/svg>)\s*```/i.exec(text);
  if (fenced) return fenced[1].trim();
  const bare = /<svg[\s\S]*<\/svg>/i.exec(text);
  return bare ? bare[0] : null;
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

export type Check = { ok: boolean; errors: string[]; warnings?: string[]; parts: string[]; labels?: Record<string, string>;
  animated?: boolean; preview?: string };

/** svgcheck.py on these SVG files: what the board makes of each (and, given `previews`, a PNG of it on the board). */
export function checkSvgs(repo: string, python: string, files: Record<string, string>,
  parts: Record<string, string[]> = {}, previews: Record<string, string> = {}): Promise<Record<string, Check>> {
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
    child.stdin.end(JSON.stringify({ figures: Object.entries(files).map(([id, svg]) =>
      ({ id, svg, parts: parts[id], ...(previews[id] ? { preview: previews[id] } : {}) })) }));
  });
}

export type SettleOptions = {
  key: string;
  model: string;
  repo: string;
  python: string;
  signal?: AbortSignal;
  onCost?: (usd: number) => void;
};

/**
 * The conversation that makes one drawing: ask, check what comes back the way the board draws it (svgcheck.py),
 * send faults back (REPAIRS rounds), then show the model its passing drawing as the board renders it and let it fix
 * what it sees (REVIEWS rounds). A fix that breaks the rules is dropped and the last good drawing kept. Writes the
 * final SVG to `file`.
 */
export async function settle(messages: Message[], file: string, parts: string[] | undefined, options: SettleOptions,
  asFigure = false): Promise<{ svg?: string; check?: Check; photo?: boolean; manim?: boolean; error?: string }> {
  const made: string[] = [];
  const scratch = (n: string) => {
    const name = `${file}.${process.pid}.${n}`;
    made.push(name);
    return name;
  };
  try {
    return await converse();
  } finally {
    await Promise.all(made.map((name) => rm(name, { force: true })));
  }

  async function converse(): Promise<{ svg?: string; check?: Check; photo?: boolean; manim?: boolean; error?: string }> {
  const checkOne = async (svg: string, n: string, look: boolean) => {
    await writeFile(scratch(`${n}.svg`), svg, "utf8");
    const result = await checkSvgs(options.repo, options.python, { pic: scratch(`${n}.svg`) },
      parts ? { pic: parts } : {}, look ? { pic: scratch(`${n}.png`) } : {});
    return result.pic;
  };
  let good: { svg: string; check: Check } | null = null;
  let last = "the SVG did not pass the board's checks";
  for (let round = 0; round <= REPAIRS && !good; round++) {
    const reply = await ask(options.key, options.model, messages, options.signal);
    options.onCost?.(reply.cost);
    const svg = svgOf(reply.text);
    // A book figure may be a photograph (shown as it is) or one the board builds itself (rebuilt in Manim).
    if (svg === "PHOTO" && asFigure) return { photo: true };
    if (svg === "MANIM" && asFigure) return { manim: true };
    messages.push({ role: "assistant", content: reply.text });
    if (!svg || svg === "PHOTO" || svg === "MANIM") {
      messages.push({ role: "user", content: "No SVG came back. Reply with the SVG in a ```svg block." });
      last = "no SVG came back";
      continue;
    }
    const check = await checkOne(svg, `r${round}`, REVIEWS > 0);
    if (check?.ok) {
      good = { svg, check };
      break;
    }
    last = (check?.errors ?? ["it could not be read"]).join("; ");
    messages.push({ role: "user", content: `The board cannot use it yet:\n- ${(check?.errors ?? ["it could not be read"])
      .join("\n- ")}\nSend the corrected SVG, whole, in a \`\`\`svg block.` });
  }
  if (!good) return { error: last.slice(0, 300) };
  for (let look = 0; look < REVIEWS && good.check.preview && existsSync(good.check.preview); look++) {
    let reply;
    try {
      const png = (await readFile(good.check.preview)).toString("base64");
      // What the board had to work around (a label it could only set over a line) is said, not just shown.
      const noted = good.check.warnings?.length ? `\n\nThe board also found:\n- ${good.check.warnings.join("\n- ")}` : "";
      messages.push({ role: "user", content: [{ type: "text", text: REVIEW_PROMPT + noted },
        { type: "image_url", image_url: { url: `data:image/png;base64,${png}` } }] });
      reply = await ask(options.key, options.model, messages, options.signal);
    } catch (error) {
      if (options.signal?.aborted) throw error;
      break;                                      // a model that cannot read images: the drawing stands as it is
    }
    options.onCost?.(reply.cost);
    messages.push({ role: "assistant", content: reply.text });
    const svg = svgOf(reply.text);
    if (/LOOKS GOOD/i.test(reply.text) && !svg) break;
    if (!svg || svg === "PHOTO" || svg === "MANIM") break;
    const check = await checkOne(svg, `v${look}`, look + 1 < REVIEWS);
    if (!check?.ok) break;                        // the fix broke a rule: keep the drawing that passed
    good = { svg, check };
  }
  await writeFile(file, good.svg, "utf8");
  return { svg: file, check: good.check };
  }
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
    /** Each figure as soon as it is settled (found drawn, drawn, or not), for a caller that will not wait for all;
     * `kept` when it was drawn by an earlier run (and cost nothing now). */
    onDrawn?: (id: string, drawn: Drawn, kept: boolean) => void;
  },
): Promise<Record<string, Drawn>> {
  const out: Record<string, Drawn> = {};
  const todo: FigureInfo[] = [];
  for (const figure of figures) {
    const { meta } = drawnPaths(figure);
    try {
      const kept = JSON.parse(await readFile(meta, "utf8"));
      if (kept.version === DRAWING_VERSION && (kept.photo || kept.manim || (kept.svg && existsSync(kept.svg)))) {
        out[figure.id] = kept;
        options.onDrawn?.(figure.id, kept, true);
        continue;
      }
    } catch {
      // not drawn yet
    }
    todo.push(figure);
  }
  if (!todo.length) return out;
  options.onStatus?.(`Looking at the book's ${todo.length} figure${todo.length > 1 ? "s" : ""}: built in Manim where ` +
    "the board's shapes can, drawn as SVG where they cannot.");
  let done = 0;

  const drawOne = async (figure: FigureInfo): Promise<Drawn> => {
    const image = await picture(figure.file);
    const context = figureContext(options.markdown, figure.id);
    const ask0: Part[] = [{
      type: "text",
      text: `Figure ${figure.id}${figure.page ? ` (page ${figure.page})` : ""}: ${figure.caption || "(no caption)"}` +
        (context ? `\n\nThe book around it:\n${context}` : "") + "\n\nRedraw it as the SVG (or reply MANIM or PHOTO).",
    }];
    if (image) ask0.push({ type: "image_url", image_url: { url: image } });
    const messages: Message[] = [{ role: "system", content: SVG_PROMPT }, { role: "user", content: ask0 }];
    const { svg: file } = drawnPaths(figure);
    // Its own bill as well as the lecture's: each picture says what it cost.
    let usd = 0;
    const made = await settle(messages, file, undefined, { ...options, onCost: (cost) => {
      usd += cost;
      options.onCost?.(cost);
    } }, true);
    if (made.photo) return { photo: true, usd };
    if (made.manim) return { manim: true, usd };
    if (!made.svg || !made.check) return { failed: made.error ?? "the SVG did not pass the board's checks", usd };
    return { svg: made.svg, parts: made.check.parts, labels: made.check.labels ?? {}, animated: !!made.check.animated,
      usd };
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
      options.onDrawn?.(figure.id, drawn, false);
      if (!drawn.failed) {
        await writeFile(drawnPaths(figure).meta, JSON.stringify({ ...drawn, version: DRAWING_VERSION }), "utf8");
      }
      done++;
      options.onStatus?.(`Figure ${figure.id} ${drawn.photo ? "is a photograph (shown as it is)"
        : drawn.manim ? "is built in Manim" : drawn.svg
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
