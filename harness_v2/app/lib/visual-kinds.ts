/**
 * The kinds of visual a scene may use, each switched on or off: for the whole run, or for one beat. The scene writer
 * is told only of the kinds that are on (prompts/scenes.ts), and code takes out what it used anyway (filterOps), so
 * "AI illustrations off" means no picture the image model makes, anywhere: not on the stage, not on a diagram's
 * node, a timeline's event or a map's marker.
 *
 * The heading and key point (panel, fact, clear) are always there: they are the board's words, not a visual.
 */

export type VisualKind = {
  id: string;
  label: string;
  /** What it draws, and how it is made. */
  about: string;
  /** The engine's operations that are this kind (a picture op is told apart by its keys: pictureKind). */
  ops: string[];
  /** Made by a model at compile time (the image model), so it costs. */
  paid?: boolean;
};

export const VISUAL_KINDS: VisualKind[] = [
  { id: "map", label: "Map", about: "Natural Earth through Cartopy: markers, rivers, shaded areas, routes, empires, relief (map chapters).",
    ops: ["marker", "river", "path", "arrow", "state", "dim", "graticule", "journey", "empire", "relief"] },
  { id: "figure", label: "Book figures", about: "The book's own figures (as redrawn or drawn in Generate, else the book's picture).", ops: ["figure"] },
  { id: "illustration", label: "AI illustrations", about: "Pictures of people, places, things and scenes made by the image model, as cutouts or whole scenes; also on diagram nodes, timeline events and map markers.",
    ops: ["illustration", "photo"], paid: true },
  { id: "drawing", label: "AI detailed diagrams", about: "Labelled textbook drawings (a cell, an organ, a machine) made by the image model, labels placed by the board.",
    ops: ["draw"], paid: true },
  { id: "gallery", label: "Gallery", about: "Several pictures of one kind of thing, one in the spotlight or in a grid, each brought up as it is named.", ops: ["gallery"] },
  { id: "diagram", label: "Diagrams", about: "Boxes and arrows built as they are named: flow, cycle, hub, pyramid, hierarchy, flowchart; reveal, focus, zoom.",
    ops: ["diagram", "reveal", "focus", "zoom"] },
  { id: "timeline", label: "Timeline", about: "Dated events across the stage, in proportion to their dates with a scale of years; a range of years, periods shaded along it.", ops: ["timeline"] },
  { id: "manim", label: "Manim (free-form)", about: "A figure written as Manim code: graphs, geometry, apparatus, anything that moves.", ops: ["manim"] },
  { id: "equation", label: "Equations", about: "A law or a reaction, large, in TeX.", ops: ["equation"] },
  { id: "molecule", label: "Molecules", about: "A structural formula in CPK colours.", ops: ["molecule"] },
  { id: "define", label: "Definitions", about: "A term and its meaning on a card.", ops: ["define"] },
  { id: "compare", label: "Comparisons", about: "Two or three kinds side by side, a few points each.", ops: ["compare"] },
  { id: "question", label: "Questions", about: "A question for the class, a timer, then the answer.", ops: ["question", "answer", "option"] },
  { id: "numbers", label: "Stats and bars", about: "A key number large, or a small bar chart.", ops: ["stat", "bars"] },
  { id: "work", label: "Worked solutions", about: "Working built line by line beside a figure; a long problem.", ops: ["work", "problem"] },
  { id: "words", label: "Quotes and step boxes", about: "A primary source in its own words; steps in boxes.", ops: ["quote", "process"] },
];

export const ALL_KINDS = VISUAL_KINDS.map((k) => k.id);

/** Always allowed: the board's words. */
export const BASE_OPS = ["panel", "fact", "clear", "unstage"];

export function kindById(id: string): VisualKind | undefined {
  return VISUAL_KINDS.find((k) => k.id === id);
}

/** The kind of a picture spec ({generate} | {draw} | {figure} | {items}), or of a picture-ish op. */
export function pictureKind(spec: Record<string, unknown>): string | undefined {
  if (Array.isArray(spec.items)) return "gallery";
  if (spec.figure !== undefined) return "figure";
  if (spec.draw !== undefined || spec.diagram === true) return "drawing";
  if (spec.generate !== undefined || spec.illustration !== undefined || spec.query !== undefined || spec.subject !== undefined) return "illustration";
  return undefined;
}

/** The kind an op is ("base" for the board's words), or undefined for an op the engine does not know. */
export function kindOfOp(op: Record<string, unknown>): string | undefined {
  const name = String(op.op ?? "");
  if (BASE_OPS.includes(name)) return "base";
  if (name === "picture") return pictureKind(op) ?? "illustration";
  if (name === "illustration" && op.diagram === true) return "drawing";
  return VISUAL_KINDS.find((k) => k.ops.includes(name))?.id;
}

type Op = Record<string, unknown>;

/**
 * An op with what it may not use taken out: the op itself when its kind is off, else the pictures on it whose kind
 * is off (a node keeps its words, a timeline its dates, a gallery its other items). What was taken out, in words.
 */
export function filterOps(ops: Op[], allowed: string[]): { ops: Op[]; dropped: string[] } {
  const on = new Set(allowed);
  const dropped: string[] = [];
  const keep = (spec: unknown, where: string): boolean => {
    if (!spec || typeof spec !== "object") return true;
    const k = pictureKind(spec as Op);
    if (!k || on.has(k)) return true;
    dropped.push(`${where}: a ${kindById(k)?.label ?? k} picture (switched off)`);
    return false;
  };
  const out: Op[] = [];
  for (const raw of ops) {
    if (!raw || typeof raw !== "object") continue;
    const op: Op = JSON.parse(JSON.stringify(raw));
    const name = String(op.op ?? "");
    if (name === "beta") {
      out.push(filterBeta(op, on, dropped));
      continue;
    }
    const kind = kindOfOp(op);
    if (!kind) {
      dropped.push(`"${name || "(no op)"}": not an operation the engine knows`);
      continue;
    }
    if (kind !== "base" && !on.has(kind)) {
      dropped.push(`${name}: ${kindById(kind)?.label ?? kind} is switched off`);
      continue;
    }
    if (name === "manim" && !on.has("illustration") && /\bpicture\s*\(/.test(String(op.code ?? ""))) {
      dropped.push("manim: its code asks for an AI illustration (picture(...)), switched off");
      continue;
    }
    if (Array.isArray(op.nodes)) {
      for (const node of op.nodes as Op[]) if (node && node.picture && !keep(node.picture, `diagram node "${node.label ?? node.id}"`)) delete node.picture;
    }
    if (Array.isArray(op.events)) {
      op.events = (op.events as unknown[]).map((e) => (Array.isArray(e) && e.length > 2 && !keep(e[2], `timeline event "${e[1]}"`) ? e.slice(0, 2) : e));
    }
    if (op.picture && name !== "picture" && !keep(op.picture, `${name} "${op.label ?? op.place ?? ""}"`)) delete op.picture;
    if (Array.isArray(op.pictures)) op.pictures = (op.pictures as unknown[]).map((p, i) => (p && !keep(p, `${name} stop ${i + 1}`) ? null : p));
    if (Array.isArray(op.items) && (name === "picture" || name === "gallery")) {
      op.items = (op.items as Op[]).filter((it, i) => keep(it, `gallery item ${i + 1}`));
      if (!(op.items as Op[]).length) {
        dropped.push(`${name}: every picture in it was switched off`);
        continue;
      }
    }
    out.push(op);
  }
  return { ops: out, dropped };
}

/** The kind a beta element is (engine/BETA_ENGINE.md), or "base" for what is always allowed (text, lists, shapes, icons, arrows). */
export function betaKind(el: Op): string {
  const image = (el.image && typeof el.image === "object" ? el.image : el.kind === "image" ? el : undefined) as Op | undefined;
  if (image) return image.figure !== undefined ? "figure" : image.generate !== undefined ? "illustration" : "base";
  if (el.timeline !== undefined || el.kind === "timeline") return "timeline";
  if (el.equation !== undefined || el.formula !== undefined || el.kind === "equation") return "equation";
  if (el.number !== undefined || el.bars !== undefined || el.stat !== undefined || el.chart !== undefined || ["number", "bars"].includes(String(el.kind))) return "numbers";
  return "base";
}

/** A beta beat (one {"op": "beta", layout, elements, animate, clear}) with its elements of a kind switched off taken
 * out, and the steps (and arrows) that name them. */
function filterBeta(op: Op, on: Set<string>, dropped: string[]): Op {
  const gone = new Set<string>();
  const elements = (Array.isArray(op.elements) ? op.elements as Op[] : []).filter((el) => {
    if (!el || typeof el !== "object") return false;
    const k = betaKind(el);
    if (k === "base" || on.has(k)) return true;
    gone.add(String(el.id));
    dropped.push(`element "${el.id}": ${kindById(k)?.label ?? k} is switched off`);
    return false;
  }).filter((el) => {
    const arrow = (el.arrow && typeof el.arrow === "object" ? el.arrow : el.kind === "arrow" ? el : undefined) as Op | undefined;
    if (arrow && (gone.has(String(arrow.from)) || gone.has(String(arrow.to)))) {
      gone.add(String(el.id));
      return false;
    }
    return true;
  });
  const animate = (Array.isArray(op.animate) ? op.animate as Op[] : []).filter((st) => st && typeof st === "object" && !gone.has(String(st.id ?? "").split(".")[0]));
  return { ...op, elements, animate };
}

/** Whether a beat's visuals are written for `engine`: one {"op": "beta"} on the beta, operations on the current one. */
export function builtFor(ops: Record<string, unknown>[] | undefined, engine?: "beta"): boolean {
  const beta = !!ops?.length && ops.every((o) => o?.op === "beta");
  return engine === "beta" ? beta : !!ops?.length && !beta;
}
