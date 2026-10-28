/**
 * A chapter built as one piece (the Scenes tab's director and choreography): its plan, its cues, and how they become
 * the beat script the engines read.
 *
 *   - THE PLAN (the director's call, one a chapter): the chapter's elements (each an operation of the engine, with an
 *     id and a role) and its scenes (a run of beats, one idea: the elements it uses, its intent, its layout). It says
 *     what is on screen and why, never when.
 *   - THE CHOREOGRAPHY (the choreography's calls, one for a few scenes, at once): each element's timeline and look.
 *     Its timeline is its steps, each on a beat's word ("b12.w3"): it or one of its parts comes on (`enter`, `show`),
 *     is pulsed (`pulse`), lit with the rest shaded (`light`), ringed with the rest dimmed (`focus`), taken off
 *     (`hide` a part, `exit` the element), or a scene stamped (`stamps`); a light or a focus held `until` a later
 *     word; a picture's label given a short `note`. Its look is how it is drawn (a picture's move, a
 *     diagram's flow, a timeline's spans): merged into its operation. Kept and edited as
 *     {"elements": [{"id", "timeline": [...], "look"?}], "stamps"?: [...]}; read here as flat cues.
 *     The call is shown the manual of every artifact its scenes use (lib/manuals.ts).
 *   - LOWERING (here, in code): the plan and its cues made the beats' operations as the compilers read them: each
 *     element on the beat it comes on, its "on" the word ("w3"), its parts' words; a diagram's nodes said in a later
 *     line held back (`show`) and brought on by a `reveal` there; an emphasis on a diagram's node a `focus`, on a
 *     motion template an `emphasis` (`<id>.<part>`), on any other part of the current engine a `point`; a shade a
 *     `shade`; an exit an `unstage`; a stamp a `stamp`; on the current engine a labelled picture's label shown on a later line held
 *     back (`hold`) and brought on there by a `label`, hidden by an `unlabel`, a light held by `shade` with `hold` and
 *     lifted by an `unshade`, a focus held lifted by an `unfocus`. There is no camera: nothing zooms. What cannot be lowered is
 *     mended (a part to its element's line) or left out, with a note.
 */

import { MOTION_KIND, VISUAL_KINDS } from "./visual-kinds";

type Op = Record<string, unknown>;

export type PlanElement = { id: string; role?: string; op: Op };
export type PlanScene = { id: string; beats: number[]; intent?: string; layout?: string; uses: string[] };
/** A cue as it is kept and shown: its word as "b12.w3" (the choreography's own answer, mended). */
export type PlanCue = { at: string; ref: string; act: string; how?: string; text?: string; in_pause?: boolean };
/** A chapter's plan, as the director gave it (mended), with the cues it was lowered with: kept on the lecture's scenes
 * by chapter, seen and changed by hand on the Scenes tab. */
export type ChapterPlan = { elements: PlanElement[]; scenes: PlanScene[]; choreography?: Choreography; cues?: PlanCue[]; at?: number;
  notes?: string[] };
/** One step of an element's timeline, as the choreography gives it and the page shows it. */
export type Step = { at: string; do: string; part?: string; until?: string; how?: string; note?: string; in_pause?: boolean };
/** A stamp on a scene (the motion engine's). */
export type Stamp = { at: string; scene: string; text: string; in_pause?: boolean };
/** Every element's timeline and look, and the scenes' stamps: the choreographer's JSON. */
export type Choreography = { elements: { id: string; timeline: Step[]; look?: Op }[]; stamps?: Stamp[] };
export type PlanPart = { ref: string; element: string; place: (string | number)[]; name: string; parent?: string; node?: string };
export type CueAct = "enter" | "emphasis" | "shade" | "focus" | "hide" | "exit" | "stamp";
export type Cue = { beat: number; word: number; ref: string; act: CueAct; how?: string; text?: string; inPause?: boolean;
  until?: [number, number]; note?: string };
/** A step's `do` and the cue it is: `show` a part's enter, `light` a shade, `pulse` an emphasis. */
const ACT_OF: Record<string, CueAct> = { enter: "enter", show: "enter", hide: "hide", light: "shade", shade: "shade", pulse: "emphasis",
  emphasis: "emphasis", focus: "focus", exit: "exit", stamp: "stamp" };
/** A cue's act as a step's `do`. */
const DO_OF: Record<CueAct, string> = { enter: "enter", hide: "hide", shade: "light", emphasis: "pulse", focus: "focus", exit: "exit", stamp: "stamp" };
/** A cue's act as the choreographer writes it (`show` for a part's entry). */
export const doName = (act: CueAct, part: boolean) => (part && act === "enter" ? "show" : DO_OF[act]);
/** What a look may not change: the element's own content (the director's). */
export const NOT_LOOK = new Set(["op", "id", "on", "nodes", "edges", "labels", "items", "events", "steps_of", "show", "hide", "text", "title"]);
/** A beat's line as the voice says it (or, unspoken, as it would be: `estimated`). */
export type BeatWords = { n: number; text: string; seconds: number; pause: number; words: { w: string; t: number }[]; estimated?: boolean };
export type Engine = "current" | "motion";

/** A part's name (compile_lecture.NAMED_BY). */
const NAMED_BY = ["label", "text", "title", "name", "term", "date", "place"];
/** Lists of ids, places on the screen, colours: no thing of their own. */
const NOT_PARTS = new Set(["show", "hide", "ids", "order", "range", "colors", "colours", "keep", "path", "at", "from", "to", "size",
  "edges", "box", "values", "frames", "picture"]);
/** How an emphasis may point on the motion engine (MOTION_ENGINE.md, `emphasis`). */
export const EMPHASIS_HOW = ["pulse", "circle", "underline", "highlight", "box", "glow", "shake", "dim", "spotlight", "rack", "magnify",
  "wiggle", "bounce", "wash", "strike", "sweep"];
/** What takes the stage on the current engine (what was up before goes); two of them in one line are laid out together. */
const MAIN_AT_ONCE = 2;
const MAIN_OPS = new Set(["picture", "photo", "illustration", "figure", "gallery", "diagram", "timeline", "compare", "process", "quote", "draw",
  "problem", "molecule"]);
/** A stamp's words at most. */
const STAMP_LETTERS = 24;

export const isObj = (x: unknown): x is Op => !!x && typeof x === "object" && !Array.isArray(x);
const nameOf = (o: Op) => NAMED_BY.map((k) => o[k]).find((v) => (typeof v === "string" || typeof v === "number") && String(v).trim());

export function slug(text: string): string {
  return String(text).toLowerCase().normalize("NFC").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 24) || "x";
}

/** A motion template (not a classic operation): on the motion engine it takes an `id`, and its parts are `<id>.<name>`. */
export function isTemplate(op: Op, engine: Engine): boolean {
  return engine === "motion" && MOTION_KIND.ops.includes(String(op.op));
}

/** What can hold parts back for a later line's `reveal` with `of` (BEAT_SCRIPT.md §5.9): a template (on the current
 * engine those it draws, the "templates" kind; on the motion engine every one) and, on the motion engine, a timeline. */
export function holdsParts(op: Op, engine: Engine): boolean {
  const kind = String(op.op);
  return isTemplate(op, engine) || (engine === "motion" && kind === "timeline")
    || (VISUAL_KINDS.find((k) => k.id === "templates")?.ops.includes(kind) ?? false);
}

// ---------------------------------------------------------------- the plan ---------------------------------------

/**
 * The director's answer made a plan the chapter can be built from: every element with an id of its own and an
 * operation, every beat of the chapter in exactly one scene (scenes in order, each a run of beats; a beat no scene
 * has goes with the scene before it), each scene's elements known ones, every element in a scene. What was mended
 * is said.
 */
export function readPlan(reply: Op, beats: number[]): ChapterPlan & { notes: string[] } {
  const notes: string[] = [];
  const elements: PlanElement[] = [];
  const ids = new Set<string>();
  for (const [i, e] of (Array.isArray(reply.elements) ? reply.elements : []).entries()) {
    const op = isObj(e) && isObj(e.op) ? e.op : isObj(e) && typeof e.op === "string" ? { ...e } : undefined;
    if (!op || typeof op.op !== "string" || !op.op.trim()) {
      notes.push(`element ${i + 1}: no operation: left out`);
      continue;
    }
    if (isObj(e) && !isObj(e.op)) for (const k of ["id", "role"]) delete op[k];
    let id = slug(isObj(e) && typeof e.id === "string" && e.id.trim() ? e.id : `e${i + 1}`);
    while (ids.has(id)) id = `${id}-2`;
    ids.add(id);
    elements.push({ id, ...(isObj(e) && typeof e.role === "string" && e.role.trim() ? { role: e.role.trim().slice(0, 30) } : {}), op });
  }
  const raw = (Array.isArray(reply.scenes) ? reply.scenes : []).filter(isObj).map((s, i) => {
    const list = Array.isArray(s.beats) ? s.beats.map(Number).filter(Number.isFinite) : [];
    const first = list.length ? Math.min(...list) : Number.NaN;
    const uses = (Array.isArray(s.uses) ? s.uses : []).map((u) => slug(String(u))).filter((u) => {
      if (ids.has(u)) return true;
      notes.push(`scene ${i + 1}: uses ${JSON.stringify(u)}, no such element: left out`);
      return false;
    });
    return { id: typeof s.id === "string" && s.id.trim() ? s.id.trim().slice(0, 12) : `S${i + 1}`, first, uses: [...new Set(uses)],
      intent: typeof s.intent === "string" ? s.intent.trim().slice(0, 40) : undefined,
      layout: typeof s.layout === "string" ? s.layout.trim().slice(0, 30) : undefined };
  }).filter((s) => Number.isFinite(s.first)).sort((a, b) => a.first - b.first);
  const scenes: PlanScene[] = [];
  if (!raw.length) {
    notes.push("no scenes given: the chapter is one scene");
    raw.push({ id: "S1", first: beats[0] ?? 1, uses: elements.map((e) => e.id), intent: undefined, layout: undefined });
  }
  for (const b of beats) {
    const at = [...raw].reverse().find((s) => s.first <= b) ?? raw[0];
    let scene = scenes.find((s) => s.id === at.id);
    if (!scene) {
      scene = { id: at.id, beats: [], uses: at.uses, ...(at.intent ? { intent: at.intent } : {}), ...(at.layout ? { layout: at.layout } : {}) };
      scenes.push(scene);
    }
    scene.beats.push(b);
  }
  // Scene ids unique, in order.
  const seen = new Set<string>();
  for (const s of scenes) {
    while (seen.has(s.id)) s.id = `${s.id}b`;
    seen.add(s.id);
  }
  const used = new Set(scenes.flatMap((s) => s.uses));
  const kept = elements.filter((e) => {
    if (used.has(e.id)) return true;
    notes.push(`element ${e.id}: in no scene: left out`);
    return false;
  });
  return { elements: kept, scenes, notes };
}

// ---------------------------------------------------------------- limits --------------------------------------------

/** What a plan is held to (told to the director in prompts/director.ts LIMITS): small scenes, small elements. */
export const LIMITS = { sceneBeats: 5, sceneElements: 3, nodes: 6, nodeWords: 4, items: 3, itemWords: 3, edgeWords: 2,
  events: 6, eventWords: 4, columns: 3, points: 3, pointWords: 6, labels: 5, labelWords: 3 };

const wordCount = (x: unknown) => String(x ?? "").trim().split(/\s+/).filter(Boolean).length;
const nameOfLabel = (x: unknown) => (isObj(x) ? String(x.name ?? "") : String(x ?? ""));

/** Where a plan goes past LIMITS, each said so the director can fix it (none: it is within them). */
export function planProblems(plan: ChapterPlan): string[] {
  const out: string[] = [];
  const L = LIMITS;
  for (const sc of plan.scenes) {
    if (sc.beats.length > L.sceneBeats) out.push(`scene ${sc.id} has ${sc.beats.length} beats (at most ${L.sceneBeats}): cut it where the idea turns`);
    if (sc.uses.length > L.sceneElements) out.push(`scene ${sc.id} uses ${sc.uses.length} elements (at most ${L.sceneElements})`);
  }
  for (const el of plan.elements) out.push(...opProblems(el.id, el.op));
  return out;
}

/** Where one operation goes past LIMITS (its lists, its words), each said with `id` (an element's id, a beat's op). */
export function opProblems(id: string, op: Op): string[] {
  const out: string[] = [];
  const L = LIMITS;
  const say = (what: string) => out.push(`${id} (${String(op.op)}): ${what}`);
  if (op.op === "diagram" && Array.isArray(op.nodes)) {
    if (op.nodes.length > L.nodes) say(`${op.nodes.length} nodes (at most ${L.nodes}): split it into two diagrams for two scenes`);
    for (const n of op.nodes.filter(isObj)) {
      if (wordCount(n.label ?? n.id) > L.nodeWords) say(`node ${JSON.stringify(n.label ?? n.id)} is ${wordCount(n.label)} words (at most ${L.nodeWords})`);
      const items = Array.isArray(n.items) ? n.items : [];
      if (items.length > L.items) say(`node ${JSON.stringify(n.label ?? n.id)} has ${items.length} items (at most ${L.items})`);
      if (items.some((x) => wordCount(x) > L.itemWords)) say(`node ${JSON.stringify(n.label ?? n.id)} has an item longer than ${L.itemWords} words`);
      if (typeof n.text === "string" && wordCount(n.text) > L.nodeWords) say(`node ${JSON.stringify(n.label ?? n.id)} has a sentence in it: words on the screen are names`);
    }
    for (const e of Array.isArray(op.edges) ? op.edges : []) {
      if (Array.isArray(e) && e.length > 2 && wordCount(e[2]) > L.edgeWords) say(`the arrow label ${JSON.stringify(e[2])} is longer than ${L.edgeWords} words`);
    }
  }
  if (op.op === "timeline" && Array.isArray(op.events)) {
    if (op.events.length > L.events) say(`${op.events.length} events (at most ${L.events})`);
    for (const ev of op.events) {
      const label = Array.isArray(ev) ? ev[1] : isObj(ev) ? ev.label : "";
      if (wordCount(label) > L.eventWords) say(`the event ${JSON.stringify(label)} is longer than ${L.eventWords} words`);
    }
  }
  if (op.op === "compare" && Array.isArray(op.columns)) {
    if (op.columns.length > L.columns) say(`${op.columns.length} columns (at most ${L.columns})`);
    for (const c of op.columns.filter(isObj)) {
      const pts = Array.isArray(c.points) ? c.points : [];
      if (pts.length > L.points) say(`column ${JSON.stringify(c.title)} has ${pts.length} points (at most ${L.points})`);
      if (pts.some((x) => wordCount(x) > L.pointWords)) say(`column ${JSON.stringify(c.title)} has a point longer than ${L.pointWords} words`);
    }
  }
  if (op.op === "picture" && Array.isArray(op.labels)) {
    if (op.labels.length > L.labels) say(`${op.labels.length} labels (at most ${L.labels})`);
    if (op.labels.some((x) => wordCount(nameOfLabel(x)) > L.labelWords)) say(`a label longer than ${L.labelWords} words`);
  }
  return out;
}

/** Shortened to `most` words (a word list's end marked). */
const cut = (x: unknown, most: number) => {
  const words = String(x ?? "").trim().split(/\s+/).filter(Boolean);
  return words.length > most ? `${words.slice(0, most).join(" ")}…` : String(x ?? "");
};

/**
 * A plan brought within LIMITS by code, when the director's answer (asked again) still goes past them: a scene too
 * long cut into runs of at most LIMITS.sceneBeats beats (its elements listed in each, so they stay up); an element's
 * lists cut to their limits (nodes, items, events, columns, points, labels) and its words to theirs. What was cut is
 * said.
 */
export function fitPlan(plan: ChapterPlan): string[] {
  const notes: string[] = [];
  const L = LIMITS;
  const scenes: PlanScene[] = [];
  for (const sc of plan.scenes) {
    if (sc.beats.length <= L.sceneBeats) {
      scenes.push(sc);
      continue;
    }
    const parts = Math.ceil(sc.beats.length / L.sceneBeats);
    const size = Math.ceil(sc.beats.length / parts);
    for (let k = 0; k < parts; k++) {
      scenes.push({ ...sc, id: k ? `${sc.id}${String.fromCharCode(97 + k)}` : sc.id, beats: sc.beats.slice(k * size, (k + 1) * size) });
    }
    notes.push(`scene ${sc.id}: ${sc.beats.length} beats cut into ${parts} scenes`);
  }
  plan.scenes = scenes;
  for (const el of plan.elements) notes.push(...fitOp(el.id, el.op));
  return notes;
}

/** One operation's lists and words cut to LIMITS, in place; what was cut, each said with `id`. */
export function fitOp(id: string, op: Op): string[] {
  const notes: string[] = [];
  const L = LIMITS;
  const said = (what: string) => notes.push(`${id}: ${what}`);
  if (op.op === "diagram" && Array.isArray(op.nodes)) {
    if (op.nodes.length > L.nodes) {
      const kept = new Set(op.nodes.slice(0, L.nodes).filter(isObj).map((n) => String(n.id)));
      said(`${op.nodes.length - L.nodes} node(s) past ${L.nodes} left out`);
      op.nodes = op.nodes.slice(0, L.nodes);
      if (Array.isArray(op.edges)) op.edges = op.edges.filter((e) => Array.isArray(e) && kept.has(String(e[0])) && kept.has(String(e[1])));
      if (Array.isArray(op.show)) op.show = op.show.filter((x) => kept.has(String(x)));
    }
    for (const n of (op.nodes as unknown[]).filter(isObj)) {
      if (typeof n.label === "string" && wordCount(n.label) > L.nodeWords) n.label = cut(n.label, L.nodeWords);
      if (Array.isArray(n.items)) n.items = n.items.slice(0, L.items).map((x: unknown) => cut(x, L.itemWords));
      if (typeof n.text === "string" && wordCount(n.text) > L.nodeWords) delete n.text;
    }
    if (Array.isArray(op.edges)) op.edges = op.edges.map((e) => (Array.isArray(e) && e.length > 2 ? [e[0], e[1], cut(e[2], L.edgeWords), ...e.slice(3)] : e));
  }
  if (op.op === "timeline" && Array.isArray(op.events)) {
    if (op.events.length > L.events) said(`${op.events.length - L.events} event(s) past ${L.events} left out`);
    op.events = op.events.slice(0, L.events).map((ev) => (Array.isArray(ev) ? [ev[0], cut(ev[1], L.eventWords), ...ev.slice(2)]
      : isObj(ev) ? { ...ev, label: cut(ev.label, L.eventWords) } : ev));
  }
  if (op.op === "compare" && Array.isArray(op.columns)) {
    if (op.columns.length > L.columns) said(`${op.columns.length - L.columns} column(s) past ${L.columns} left out`);
    op.columns = op.columns.slice(0, L.columns).map((c) => (isObj(c) && Array.isArray(c.points)
      ? { ...c, points: c.points.slice(0, L.points).map((x) => cut(x, L.pointWords)) } : c));
  }
  if (op.op === "picture" && Array.isArray(op.labels)) {
    if (op.labels.length > L.labels) said(`${op.labels.length - L.labels} label(s) past ${L.labels} left out`);
    op.labels = op.labels.slice(0, L.labels).map((x) => (isObj(x) ? { ...x, name: cut(x.name, L.labelWords) } : cut(x, L.labelWords)));
  }
  return notes;
}

/** The scene an element first comes on in, and every beat of the scenes it is in (it stays up through them). */
function lifeOf(plan: ChapterPlan) {
  const first = new Map<string, PlanScene>();
  const span = new Map<string, Set<number>>();
  for (const s of plan.scenes) {
    for (const id of s.uses) {
      if (!first.has(id)) first.set(id, s);
      const set = span.get(id) ?? new Set<number>();
      s.beats.forEach((b) => set.add(b));
      span.set(id, set);
    }
  }
  return { first, span };
}

// ---------------------------------------------------------------- parts --------------------------------------------

/**
 * The parts of an element that can each come on with a word: a diagram's nodes (by their ids); in any other
 * operation, everything with a name in it (a label, an event, a step, a card, a stop) and a list's words, by their
 * names. Each has a ref (`<element>.<part>`) and the place it is in the operation.
 */
export function partsOf(el: PlanElement): PlanPart[] {
  const out: PlanPart[] = [];
  const refs = new Set<string>();
  const add = (p: Omit<PlanPart, "ref" | "element"> & { key: string }) => {
    let ref = `${el.id}.${slug(p.key)}`;
    while (refs.has(ref)) ref = `${ref}-2`;
    refs.add(ref);
    const { key: _key, ...rest } = p;
    out.push({ ref, element: el.id, ...rest });
    return ref;
  };
  const op = el.op;
  if (op.op === "diagram" && Array.isArray(op.nodes)) {
    op.nodes.forEach((n, i) => {
      if (isObj(n) && (typeof n.id === "string" || typeof n.id === "number")) {
        add({ key: String(n.id), place: ["nodes", i], name: String(nameOf(n) ?? n.id), node: String(n.id) });
      }
    });
    return out;
  }
  const inside = (value: unknown, place: (string | number)[], parent: string | undefined, depth: number) => {
    if (depth > 4 || !isObj(value)) return;
    for (const [key, inner] of Object.entries(value)) {
      if (key === "on" || NOT_PARTS.has(key)) continue;
      if (isObj(inner)) {
        const name = nameOf(inner);
        if (name !== undefined && depth > 0) {
          const ref = add({ key: String(name), place: [...place, key], name: String(name).trim(), ...(parent ? { parent } : {}) });
          inside(inner, [...place, key], ref, depth + 1);
        } else inside(inner, [...place, key], parent, depth + 1);
        continue;
      }
      if (!Array.isArray(inner)) continue;
      inner.forEach((item, i) => {
        if (typeof item === "string" && /\p{L}/u.test(item) && item.trim().length <= 80) {
          add({ key: item.trim(), place: [...place, key, i], name: item.trim(), ...(parent ? { parent } : {}) });
        } else if (isObj(item)) {
          const name = nameOf(item);
          if (name !== undefined) {
            const ref = add({ key: String(name), place: [...place, key, i], name: String(name).trim(), ...(parent ? { parent } : {}) });
            inside(item, [...place, key, i], ref, depth + 1);
          } else inside(item, [...place, key, i], parent, depth + 1);
        }
      });
    }
  };
  inside(op, [], undefined, 0);
  return out;
}

/** What is put on the board's strip or the map, not the stage: not taken off by an exit (the next picture, or the
 * map going, does). */
const NOT_STAGED = new Set(["panel", "fact", "stat", "bars", "clear", "icon", "marker", "river", "path", "arrow", "state", "dim",
  "graticule", "journey", "empire", "relief"]);

/** What the choreography may do with an element and with its parts, on this engine. */
export function actsFor(el: PlanElement, engine: Engine): { element: CueAct[]; parts: CueAct[]; laterParts: boolean } {
  const diagram = el.op.op === "diagram";
  const template = isTemplate(el.op, engine);
  const labelled = engine === "current" && el.op.op === "picture" && Array.isArray(el.op.labels) && el.op.labels.length > 0;
  const exits = engine === "current" && !NOT_STAGED.has(String(el.op.op));
  return {
    element: ["enter", ...(template ? ["emphasis" as const] : []), ...(exits ? ["exit" as const] : [])],
    parts: ["enter", "emphasis", ...(labelled ? ["shade" as const, "hide" as const] : []), ...(diagram ? ["focus" as const] : [])],
    // A diagram's nodes, a labelled picture's labels (both engines) and a template's parts may come on in a later
    // line of its scenes (held, then revealed there: lowerPlan).
    laterParts: diagram || (el.op.op === "picture" && Array.isArray(el.op.labels) && el.op.labels.length > 0) || holdsParts(el.op, engine),
  };
}

// ---------------------------------------------------------------- cues ---------------------------------------------

const AT = /^\s*b?(\d+)\s*(?:\.\s*(?:w(\d+)|start)|\s*w(\d+))?\s*$/i;

/**
 * The choreography's answer as cues: each `at` a word of a beat of its scenes ("b12.w3"; "b12" or "b12.start" its
 * first), each ref a known element or part (or, for a stamp, one of its scenes), each act one it may do. What is
 * not is left out, and said.
 */
export function readCues(reply: Op, o: { words: Map<number, BeatWords>; beats: Set<number>; acts: Map<string, CueAct[]>; scenes: Set<string> }):
  { cues: Cue[]; dropped: string[] } {
  const cues: Cue[] = [];
  const dropped: string[] = [];
  for (const c of Array.isArray(reply.cues) ? reply.cues : []) {
    if (!isObj(c)) continue;
    const m = AT.exec(String(c.at ?? ""));
    const ref = String(c.ref ?? c.id ?? "").trim();
    const act = ACT_OF[String(c.act ?? c.do ?? "enter").trim()] ?? (String(c.act ?? c.do).trim() as CueAct);
    const said = `${JSON.stringify(c).slice(0, 120)}`;
    if (!m || !o.beats.has(Number(m[1]))) {
      dropped.push(`${said}: not a word of this scene's lines`);
      continue;
    }
    const beat = Number(m[1]);
    const last = Math.max(0, (o.words.get(beat)?.words.length ?? 1) - 1);
    const word = Math.min(last, Number(m[2] ?? m[3] ?? 0));
    if (act === "stamp") {
      if (!o.scenes.has(ref) && ref !== "") {
        dropped.push(`${said}: a stamp is on a scene`);
        continue;
      }
      if (!o.acts.get("*")?.includes("stamp")) {
        dropped.push(`${said}: no stamps on this engine`);
        continue;
      }
      const text = String(c.text ?? "").trim();
      if (!text) {
        dropped.push(`${said}: a stamp with no words`);
        continue;
      }
      cues.push({ beat, word, ref, act, text: text.slice(0, STAMP_LETTERS), ...(c.in_pause === true ? { inPause: true } : {}) });
      continue;
    }
    const may = o.acts.get(ref);
    if (!may) {
      dropped.push(`${said}: no element or part ${JSON.stringify(ref)}`);
      continue;
    }
    if (!may.includes(act)) {
      dropped.push(`${said}: ${JSON.stringify(ref)} cannot ${act}`);
      continue;
    }
    const how = typeof c.how === "string" && EMPHASIS_HOW.includes(c.how) ? c.how : undefined;
    // Held until a later word (a light, a focus).
    let until: [number, number] | undefined;
    const u = c.until !== undefined && (act === "shade" || act === "focus") ? AT.exec(String(c.until)) : null;
    if (u && o.beats.has(Number(u[1]))) {
      const ub = Number(u[1]);
      const uw = Math.min(Math.max(0, (o.words.get(ub)?.words.length ?? 1) - 1), Number(u[2] ?? u[3] ?? 0));
      if (ub > beat || (ub === beat && uw > word)) until = [ub, uw];
      else dropped.push(`${said}: its "until" is not after it: not held`);
    } else if (c.until !== undefined && (act === "shade" || act === "focus")) dropped.push(`${said}: its "until" is not a word of these lines: not held`);
    const note = typeof c.note === "string" && c.note.trim() ? c.note.trim().slice(0, 60) : undefined;
    cues.push({ beat, word, ref, act, ...(how ? { how } : {}), ...(c.in_pause === true ? { inPause: true } : {}), ...(until ? { until } : {}),
      ...(note ? { note } : {}) });
  }
  return { cues, dropped };
}

/**
 * The choreographer's JSON ({"elements": [{"id", "timeline", "look"?}], "stamps"?}) as flat cues to read (readCues),
 * and each element's look. A step's `part` is its part's name or key (`soil`, `granary`) or its whole ref
 * (`img.soil`). Older plans' flat cues (`cues`: [{"at", "ref", "act"}]) are read as they are.
 */
export function flatSteps(raw: unknown, refs?: Set<string>): { cues: Op[]; looks: Map<string, Op>; dropped: string[] } {
  const cues: Op[] = [];
  const looks = new Map<string, Op>();
  const dropped: string[] = [];
  if (Array.isArray(raw)) return { cues: raw.filter(isObj), looks, dropped };
  if (!isObj(raw)) return { cues, looks, dropped };
  if (Array.isArray(raw.cues)) cues.push(...raw.cues.filter(isObj));
  for (const e of Array.isArray(raw.elements) ? raw.elements : []) {
    if (!isObj(e) || typeof e.id !== "string") continue;
    const id = e.id.trim();
    for (const step of Array.isArray(e.timeline) ? e.timeline : []) {
      if (!isObj(step)) continue;
      const part = typeof step.part === "string" && step.part.trim() ? step.part.trim() : "";
      const ref = !part ? id : refs?.has(part) ? part : `${id}.${slug(part)}`;
      const { part: _p, do: act, ...rest } = step;
      cues.push({ ...rest, ref, act: act ?? "enter" });
    }
    if (isObj(e.look)) {
      const look: Op = {};
      for (const [k, v] of Object.entries(e.look)) {
        if (NOT_LOOK.has(k)) dropped.push(`${id}: its look cannot change ${JSON.stringify(k)} (the director's): left out`);
        else look[k] = v;
      }
      if (Object.keys(look).length) looks.set(id, look);
    }
  }
  for (const s of Array.isArray(raw.stamps) ? raw.stamps : []) {
    if (isObj(s)) cues.push({ at: s.at, ref: String(s.scene ?? s.ref ?? ""), act: "stamp", text: s.text, ...(s.in_pause === true ? { in_pause: true } : {}) });
  }
  return { cues, looks, dropped };
}

/** Cues (and looks) as the choreographer's JSON: every element of the plan with its timeline, in order, and the stamps. */
export function choreographyOf(plan: Pick<ChapterPlan, "elements">, cues: Cue[], looks: Map<string, Op>): Choreography {
  const at = (b: number, w: number) => `b${b}.w${w}`;
  const sorted = [...cues].sort((a, b) => a.beat - b.beat || a.word - b.word);
  const elements = plan.elements.map((el) => {
    const parts = new Map(partsOf(el).map((p) => [p.ref, p]));
    const timeline: Step[] = sorted.filter((c) => c.act !== "stamp" && (c.ref === el.id || parts.has(c.ref))).map((c) => {
      const p = parts.get(c.ref);
      return { at: at(c.beat, c.word), do: doName(c.act, !!p), ...(p ? { part: c.ref.slice(el.id.length + 1) } : {}),
        ...(c.until ? { until: at(...c.until) } : {}), ...(c.how ? { how: c.how } : {}),
        ...(c.note ? { note: c.note } : {}), ...(c.inPause ? { in_pause: true } : {}) };
    });
    const look = looks.get(el.id);
    return { id: el.id, timeline, ...(look ? { look } : {}) };
  });
  const stamps: Stamp[] = sorted.filter((c) => c.act === "stamp").map((c) => ({ at: at(c.beat, c.word), scene: c.ref, text: c.text ?? "",
    ...(c.inPause ? { in_pause: true } : {}) }));
  return { elements, ...(stamps.length ? { stamps } : {}) };
}

/** A kept plan's choreography as flat cues and looks (an older plan's flat `cues` read as they are). */
export function keptSteps(plan: ChapterPlan, refs?: Set<string>) {
  return plan.choreography ? flatSteps(plan.choreography, refs) : flatSteps(plan.cues ?? [], refs);
}

// ---------------------------------------------------------------- lowering -----------------------------------------

const anchor = (word: number) => (word <= 0 ? "start" : `w${word}`);
const before = (a: [number, number], b: [number, number]) => a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]);

/** Every "on" taken out of an operation: the cues say when. */
export function withoutOn(x: unknown): unknown {
  if (Array.isArray(x)) return x.map(withoutOn);
  if (!isObj(x)) return x;
  const out: Op = {};
  for (const [k, v] of Object.entries(x)) if (k !== "on" && k !== "in_pause" && k !== "delay") out[k] = withoutOn(v);
  return out;
}

/** The part's place in the operation given its "on" (a string becomes {"name", "on"}). */
export function setOn(op: Op, place: (string | number)[], on: string): void {
  let holder: unknown = op;
  for (const step of place.slice(0, -1)) holder = (holder as Record<string | number, unknown>)?.[step];
  const key = place[place.length - 1];
  const at = (holder as Record<string | number, unknown>)?.[key];
  if (typeof at === "string") (holder as unknown[])[key as number] = { name: at, on };
  else if (isObj(at)) at.on = on;
}

/**
 * The chapter's beats' operations from its plan and cues. Each element goes on the beat its entry is cued on (else
 * its first scene's first beat, as the line begins) with "on" its word; each part with a cue gets its word, on its
 * element's beat (a diagram's node cued on a later beat of its scenes is held back and revealed there); a part is
 * never before its element or the part it is in. Emphases, shades, exits and stamps become operations of their
 * own on their beats (an exit only on a beat that puts up nothing new: a new picture takes the last one off itself). A `manim` beat keeps only its figure (the compiler's rule): what else came on it moves to the next beat of its
 * scene, else is left out. Returns each beat's operations, in the order they come on, and what was mended.
 */
export function lowerPlan(plan: ChapterPlan, cues: Cue[], words: Map<number, BeatWords>, engine: Engine, looks: Map<string, Op> = new Map()):
  { ops: Map<number, Op[]>; notes: string[] } {
  const notes: string[] = [];
  const ops = new Map<number, { op: Op; at: [number, number] }[]>();
  for (const s of plan.scenes) for (const b of s.beats) ops.set(b, []);
  const put = (beat: number, word: number, op: Op) => ops.get(beat)?.push({ op, at: [beat, word] });
  const { first, span } = lifeOf(plan);
  const exits: { beat: number; word: number; ref: string }[] = [];
  const byRef = new Map<string, Cue[]>();
  for (const c of [...cues].sort((a, b) => a.beat - b.beat || a.word - b.word)) byRef.set(c.ref, [...(byRef.get(c.ref) ?? []), c]);
  // At most MAIN_AT_ONCE main pictures on the stage at once (current engine; two are laid out together): elements
  // taken in the order they come on, and one more cued on a line that has them already comes on as a later line of
  // its scenes begins.
  const mainAt = new Map<number, string[]>();
  const entryOf = (el: PlanElement): [number, number] => {
    const e = byRef.get(el.id)?.find((c) => c.act === "enter");
    return e ? [e.beat, e.word] : [first.get(el.id)?.beats[0] ?? Number.MAX_SAFE_INTEGER, 0];
  };
  const order = [...plan.elements].sort((a, b) => { const x = entryOf(a), y = entryOf(b); return x[0] - y[0] || x[1] - y[1]; });
  for (const el of order) {
    const scene = first.get(el.id);
    const life = span.get(el.id);
    if (!scene || !life) continue;
    const op = withoutOn(el.op) as Op;
    // Its look (the choreographer's): how it is drawn, over what the director gave.
    for (const [k, v] of Object.entries(looks.get(el.id) ?? {})) if (!NOT_LOOK.has(k)) op[k] = withoutOn(v);
    const template = isTemplate(op, engine);
    if (template || op.op === "diagram") op.id ??= el.id;
    const enter = byRef.get(el.id)?.find((c) => c.act === "enter");
    let at: [number, number] = [scene.beats[0], 0];
    if (enter && life.has(enter.beat) && enter.beat <= scene.beats[scene.beats.length - 1]) at = [enter.beat, enter.word];
    else if (enter) notes.push(`${el.id}: its entry (b${enter.beat}.w${enter.word}) is outside its scene ${scene.id}: it comes on as the scene begins`);
    if (engine === "current" && MAIN_OPS.has(String(op.op))) {
      const other = mainAt.get(at[0]) ?? [];
      if (other.length >= MAIN_AT_ONCE) {
        const free = [...life].filter((b) => b > at[0] && !mainAt.has(b)).sort((a, b) => a - b);
        // The first line of those that a part of it is cued on, else the next free one.
        const cued = partsOf(el).map((p) => byRef.get(p.ref)?.find((x) => x.act === "enter")?.beat).filter((b): b is number => b !== undefined);
        const t = free.find((b) => cued.includes(b)) ?? free[0];
        if (t !== undefined) {
          notes.push(`${el.id}: more than ${MAIN_AT_ONCE} main pictures on b${at[0]} (with ${other.join(", ")}): comes on as b${t} begins`);
          at = [t, 0];
        }
      }
      mainAt.set(at[0], [...(mainAt.get(at[0]) ?? []), el.id]);
    }
    op.on = anchor(at[1]);
    if (enter?.inPause && engine === "motion") op.in_pause = true;
    // Its parts.
    const parts = partsOf(el);
    const entered = new Map<string, [number, number]>([[el.id, at]]);
    const reveals = new Map<string, { beat: number; word: number; nodes: string[] }>();
    const held = new Set<string>();
    // A labelled picture: its labels held back to a later line, each label's note (both engines).
    const labelled = op.op === "picture" && Array.isArray(op.labels);
    // A template (a timeline on the motion engine): its parts held back to a later line, revealed there.
    const holder = !labelled && op.op !== "diagram" && holdsParts(op, engine);
    const heldParts: string[] = [];
    const partReveals = new Map<string, { beat: number; word: number; parts: string[] }>();
    const holdLabels: string[] = [];
    if (labelled) {
      const notes2: Record<string, string> = isObj(op.notes) ? { ...(op.notes as Record<string, string>) } : {};
      for (const p of parts) {
        for (const c of byRef.get(p.ref) ?? []) {
          if (c.note) notes2[p.name] = c.note;
        }
      }
      if (Object.keys(notes2).length) op.notes = notes2;
    }
    for (const p of parts) {
      const c = byRef.get(p.ref)?.find((x) => x.act === "enter");
      if (!c) continue;
      let pat: [number, number] = [c.beat, c.word];
      const floor = entered.get(p.parent ?? el.id) ?? at;
      if (before(pat, floor)) {
        pat = floor;
        notes.push(`${p.ref}: cued before what it is in: comes on with it`);
      }
      if (pat[0] !== at[0]) {
        if (p.node && life.has(pat[0])) {
          const key = `${pat[0]}.${pat[1]}`;
          const r = reveals.get(key) ?? { beat: pat[0], word: pat[1], nodes: [] };
          r.nodes.push(p.node);
          reveals.set(key, r);
          held.add(p.node);
          entered.set(p.ref, pat);
          continue;
        }
        if (labelled && life.has(pat[0])) {
          holdLabels.push(p.name);
          put(pat[0], pat[1], { op: "label", part: p.name, on: anchor(pat[1]) });
          entered.set(p.ref, pat);
          continue;
        }
        if (holder && life.has(pat[0]) && !p.parent) {
          // Said on a later line of its scenes: held, and revealed on that line's word.
          const key = `${pat[0]}.${pat[1]}`;
          const r = partReveals.get(key) ?? { beat: pat[0], word: pat[1], parts: [] };
          r.parts.push(p.name);
          partReveals.set(key, r);
          heldParts.push(p.name);
          entered.set(p.ref, pat);
          continue;
        }
        notes.push(`${p.ref}: cued on another line (b${pat[0]}) than its ${String(op.op)} (b${at[0]}): comes on in its turn with it`);
        continue;
      }
      setOn(op, p.place, anchor(pat[1]));
      entered.set(p.ref, pat);
    }
    if (held.size && Array.isArray(op.nodes)) {
      const all = op.nodes.filter(isObj).map((n) => String(n.id));
      const shown = (Array.isArray(op.show) ? op.show.map(String) : all).filter((id) => !held.has(id));
      if (!shown.length && all.length) {
        shown.push(all[0]);
        held.delete(all[0]);
        for (const r of reveals.values()) r.nodes = r.nodes.filter((x) => x !== all[0]);
      }
      op.show = shown;
    }
    if (holdLabels.length) op.hold = holdLabels;
    if (heldParts.length) {
      op.id ??= el.id;
      op.hold = heldParts;
    }
    put(at[0], at[1], op);
    for (const r of partReveals.values()) put(r.beat, r.word, { op: "reveal", of: String(op.id), parts: r.parts, on: anchor(r.word) });
    for (const r of reveals.values()) if (r.nodes.length) put(r.beat, r.word, { op: "reveal", diagram: op.id, nodes: r.nodes, on: anchor(r.word) });
    // What is done with it while it is up.
    const partOf = new Map(parts.map((p) => [p.ref, p]));
    const later = (c: Cue) => c.until && life.has(c.until[0]) ? c.until : undefined;
    for (const c of cues.filter((x) => ["emphasis", "shade", "focus", "hide", "exit"].includes(x.act))) {
      const p = partOf.get(c.ref);
      if (c.ref !== el.id && !p) continue;
      // A part given no entry comes on with its element.
      const since = entered.get(c.ref) ?? (p ? entered.get(p.parent ?? el.id) ?? at : undefined);
      if (!life.has(c.beat) || !since || before([c.beat, c.word], since)) {
        notes.push(`${c.ref}: ${c.act} on b${c.beat}.w${c.word}, when it is not on the screen: left out`);
        continue;
      }
      if (c.act === "exit") {
        exits.push({ beat: c.beat, word: c.word, ref: c.ref });
      } else if (c.act === "shade") {
        if (!p) continue;
        const until = later(c);
        put(c.beat, c.word, { op: "shade", part: p.name, on: anchor(c.word), ...(until ? { hold: true } : {}) });
        if (until) put(until[0], until[1], { op: "unshade", on: anchor(until[1]) });
      } else if (c.act === "hide") {
        if (p && labelled) put(c.beat, c.word, { op: "unlabel", part: p.name, on: anchor(c.word) });
        else notes.push(`${c.ref}: hide on b${c.beat}: only a labelled picture's label can be hidden: left out`);
      } else if (op.op === "diagram" && p?.node && (c.act === "focus" || engine === "motion")) {
        put(c.beat, c.word, { op: "focus", diagram: op.id, node: p.node, on: anchor(c.word) });
        const until = c.act === "focus" && engine === "current" ? later(c) : undefined;
        if (until) put(until[0], until[1], { op: "unfocus", diagram: op.id, on: anchor(until[1]) });
      } else if (engine === "motion") {
        const target = template ? (p ? `${op.id}.${p.name}` : String(op.id)) : p?.name;
        if (target) put(c.beat, c.word, { op: "emphasis", target, how: c.how ?? "pulse", on: anchor(c.word) });
      } else if (p) {
        put(c.beat, c.word, { op: "point", target: p.name, on: anchor(c.word) });
      }
    }
  }
  // An exit takes the stage's picture off, on a beat that puts up nothing new (a new picture takes it off itself).
  for (const x of exits) {
    const fresh = (ops.get(x.beat) ?? []).some((o) => !["point", "shade", "focus", "reveal", "emphasis", "stamp", "label", "unlabel", "unshade", "unfocus"].includes(String(o.op.op)));
    if (fresh) notes.push(`${x.ref}: exit on b${x.beat}, where a new picture comes on and takes it off: left to it`);
    else put(x.beat, x.word, { op: "unstage", on: anchor(x.word) });
  }
  for (const c of cues.filter((x) => x.act === "stamp")) {
    put(c.beat, c.word, { op: "stamp", text: c.text, on: anchor(c.word), ...(c.inPause ? { in_pause: true } : {}) });
  }
  // A `manim` beat keeps only its figure.
  for (const s of plan.scenes) {
    s.beats.forEach((b, i) => {
      const list = ops.get(b) ?? [];
      if (!list.some((x) => x.op.op === "manim") || list.length < 2) return;
      const others = list.filter((x) => x.op.op !== "manim");
      ops.set(b, list.filter((x) => x.op.op === "manim"));
      const next = s.beats[i + 1];
      if (next !== undefined) {
        for (const x of others) ops.get(next)?.unshift({ op: { ...x.op, on: "start" }, at: [next, 0] });
        notes.push(`b${b}: a manim figure is alone on its beat: ${others.length} operation(s) moved to b${next}`);
      } else notes.push(`b${b}: a manim figure is alone on its beat: ${others.length} operation(s) left out`);
    });
  }
  const out = new Map<number, Op[]>();
  for (const [b, list] of ops) out.set(b, list.sort((x, y) => x.at[1] - y.at[1]).map((x) => x.op));
  return { ops: out, notes };
}

/** Seconds from a beat's start for each beat of the chapter, run on (the scenes' clock): for a scene's length. */
export function sceneSeconds(scene: PlanScene, words: Map<number, BeatWords>): number {
  return scene.beats.reduce((k, b) => k + (words.get(b)?.seconds ?? 0) + (words.get(b)?.pause ?? 0), 0);
}

/** A line's words, unspoken: each at about 0.4 s (143 words a minute, as the engine estimates). */
export function estimatedWords(n: number, text: string): BeatWords {
  const words = text.split(/\s+/).filter(Boolean).map((w, i) => ({ w, t: Math.round(i * 0.42 * 10) / 10 }));
  return { n, text, seconds: Math.round(words.length * 0.42 * 10) / 10, pause: 0.4, words, estimated: true };
}
