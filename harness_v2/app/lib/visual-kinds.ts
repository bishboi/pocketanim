/**
 * The kinds of visual a scene may use, each switched on or off: for the whole run, or for one beat. The scene writer
 * is told only of the kinds that are on (prompts/scenes.ts), and code takes out what it used anyway (filterOps), so
 * "AI illustrations off" means no picture the image model makes, anywhere: not on the stage, not on a diagram's
 * node, a timeline's event or a map's marker.
 *
 * The heading (panel, clear) is always there: the board's words, not a visual. ("fact" is a side panel's point; the board has no key point.)
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
  { id: "map", label: "Map", about: "Natural Earth through Cartopy: markers, rivers, shaded areas, routes, empires, relief (the map comes in on the beats that point at it).",
    ops: ["marker", "river", "path", "arrow", "state", "dim", "graticule", "journey", "empire", "relief"] },
  { id: "figure", label: "Book figures", about: "The book's own figures (as redrawn or drawn in Generate, else the book's picture).", ops: ["figure"] },
  { id: "illustration", label: "AI illustrations", about: "Pictures of people, places, things and scenes made by the image model, as cutouts or whole scenes; also on diagram nodes, timeline events and map markers.",
    ops: ["illustration", "photo"], paid: true },
  { id: "drawing", label: "AI detailed diagrams", about: "Labelled textbook drawings (a cell, an organ, a machine) made by the image model, labels placed by the board; and flows drawn as one picture (a diagram's \"drawn\": \"picture\"), each step and arrow drawn on in that picture as it is said.",
    ops: ["draw"], paid: true },
  { id: "gallery", label: "Gallery", about: "Several pictures of one kind of thing, one in the spotlight or in a grid, each brought up as it is named.", ops: ["gallery"] },
  { id: "diagram", label: "Diagrams", about: "Boxes and arrows built as they are named: flow, cycle, hub, pyramid, hierarchy, flowchart; reveal, focus, zoom. With AI detailed diagrams on, a flow or cycle may be drawn as one picture.",
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

/** The motion engine's templates (engine/MOTION_ENGINE.md, beta): allowed only when the Scenes tab builds on it. */
export const MOTION_KIND: VisualKind = {
  id: "motion", label: "Motion templates (beta)",
  about: "The motion engine's animated templates: counters, charts, grids of units, cards, stamps, data cards, chains, lists, versus, donuts, highlighted documents, polaroids, headlines, pointing; hierarchies, exchanges, site plans, lineages, lifespans, analogies, myths corrected, rituals, shares, calendars, convergence, tables, questions.",
  ops: ["title", "counter", "chart", "units", "cards", "stamp", "kpi", "chain", "list", "versus", "donut", "document", "polaroids", "emphasis",
    "hierarchy", "exchange", "plan", "lineage", "lifespan", "analogy", "myth", "ritual", "share", "calendar", "converge", "table", "ask"],
};

/** Always allowed: the board's words. */
export const BASE_OPS = ["panel", "fact", "clear", "unstage"];

export function kindById(id: string): VisualKind | undefined {
  return VISUAL_KINDS.find((k) => k.id === id) ?? (id === MOTION_KIND.id ? MOTION_KIND : undefined);
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
  if (MOTION_KIND.ops.includes(name)) return MOTION_KIND.id;
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
    if (name === "diagram" && op.drawn === "picture" && !on.has("drawing")) {
      // Drawn as one picture by the image model: with AI detailed diagrams off, built as a diagram instead.
      delete op.drawn;
      dropped.push(`diagram "${op.id ?? ""}": drawn as one picture needs AI detailed diagrams (switched off): built instead`);
    }
    if (Array.isArray(op.nodes)) {
      for (const node of op.nodes as Op[]) if (node && node.picture && !keep(node.picture, `diagram node "${node.label ?? node.id}"`)) delete node.picture;
    }
    if (Array.isArray(op.events)) {
      op.events = (op.events as unknown[]).map((e) => (Array.isArray(e) && e.length > 2 && !keep(e[2], `timeline event "${e[1]}"`) ? e.slice(0, 2) : e));
    }
    if (op.picture && name !== "picture" && !keep(op.picture, `${name} "${op.label ?? op.place ?? ""}"`)) delete op.picture;
    // The motion templates' pictures: a card's, a print's, a step's, a side's (a print without one is left out).
    if (kind === MOTION_KIND.id) {
      const inner = (x: unknown, where: string) => {
        const it = x as Op;
        if (!it || typeof it !== "object") return true;
        const spec = (it.picture as Op | undefined) ?? (pictureKind(it) ? it : undefined);
        if (!spec || keep(spec, where)) return true;
        if (it.picture) delete it.picture;
        else for (const k of ["generate", "figure", "draw"]) delete it[k];
        return name !== "polaroids";
      };
      for (const key of ["items", "steps", "tiers", "people", "objects"]) if (Array.isArray(op[key])) op[key] = (op[key] as unknown[]).filter((x, i) => inner(x, `${name} ${key} ${i + 1}`));
      for (const side of ["left", "right", "to"]) if (op[side]) inner(op[side], `${name} ${side}`);
    }
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
