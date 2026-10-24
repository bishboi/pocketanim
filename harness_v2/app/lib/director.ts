/**
 * A chapter built as one piece (the Scenes tab's director and choreography): its plan, its cues, and how they become
 * the beat script the engines read.
 *
 *   - THE PLAN (the director's call, one a chapter): the chapter's elements (each an operation of the engine, with an
 *     id and a role) and its scenes (a run of beats, one idea: the elements it uses, its intent, its layout). It says
 *     what is on screen and why, never when.
 *   - THE CUES (the choreography's calls, one for a few scenes, at once): when each element and each of its parts
 *     comes on (a beat's word: "b12.w3"), and what is done with it as the line goes on (an emphasis, a zoom, a stamp).
 *     The call is shown the manual of every artifact its scenes use (lib/manuals.ts).
 *   - LOWERING (here, in code): the plan and its cues made the beats' operations as the compilers read them: each
 *     element on the beat it comes on, its "on" the word ("w3"), its parts' words; a diagram's nodes said in a later
 *     line held back (`show`) and brought on by a `reveal` there; an emphasis on a diagram's node a `focus`, on a
 *     motion template an `emphasis` (`<id>.<part>`); a zoom a `zoom`; a stamp a `stamp`. What cannot be lowered is
 *     mended (a part to its element's line) or left out, with a note.
 */

import { MOTION_KIND } from "./visual-kinds";

type Op = Record<string, unknown>;

export type PlanElement = { id: string; role?: string; op: Op };
export type PlanScene = { id: string; beats: number[]; intent?: string; layout?: string; uses: string[] };
/** A chapter's plan, as the director gave it (mended): kept on the lecture's scenes by chapter. */
export type ChapterPlan = { elements: PlanElement[]; scenes: PlanScene[]; at?: number; notes?: string[] };
export type PlanPart = { ref: string; element: string; place: (string | number)[]; name: string; parent?: string; node?: string };
export type CueAct = "enter" | "emphasis" | "zoom" | "stamp";
export type Cue = { beat: number; word: number; ref: string; act: CueAct; how?: string; text?: string; scale?: number; inPause?: boolean };
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
/** A stamp's words at most. */
const STAMP_LETTERS = 24;

const isObj = (x: unknown): x is Op => !!x && typeof x === "object" && !Array.isArray(x);
const nameOf = (o: Op) => NAMED_BY.map((k) => o[k]).find((v) => (typeof v === "string" || typeof v === "number") && String(v).trim());

export function slug(text: string): string {
  return String(text).toLowerCase().normalize("NFC").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 24) || "x";
}

/** A motion template (not a classic operation): on the motion engine it takes an `id`, and its parts are `<id>.<name>`. */
export function isTemplate(op: Op, engine: Engine): boolean {
  return engine === "motion" && MOTION_KIND.ops.includes(String(op.op));
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

/** What the choreography may do with an element and with its parts, on this engine. */
export function actsFor(el: PlanElement, engine: Engine): { element: CueAct[]; parts: CueAct[]; laterParts: boolean } {
  const diagram = el.op.op === "diagram";
  const template = isTemplate(el.op, engine);
  return {
    element: ["enter", ...(diagram ? ["zoom" as const] : []), ...(template ? ["emphasis" as const] : [])],
    parts: ["enter", ...(diagram || engine === "motion" ? ["emphasis" as const] : []), ...(diagram ? ["zoom" as const] : [])],
    laterParts: diagram,
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
    const act = String(c.act ?? "enter").trim() as CueAct;
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
    const scale = Number(c.scale);
    cues.push({ beat, word, ref, act, ...(how ? { how } : {}), ...(Number.isFinite(scale) ? { scale: Math.min(3, Math.max(1.1, scale)) } : {}),
      ...(c.in_pause === true ? { inPause: true } : {}) });
  }
  return { cues, dropped };
}

// ---------------------------------------------------------------- lowering -----------------------------------------

const anchor = (word: number) => (word <= 0 ? "start" : `w${word}`);
const before = (a: [number, number], b: [number, number]) => a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]);

/** Every "on" taken out of an operation: the cues say when. */
function withoutOn(x: unknown): unknown {
  if (Array.isArray(x)) return x.map(withoutOn);
  if (!isObj(x)) return x;
  const out: Op = {};
  for (const [k, v] of Object.entries(x)) if (k !== "on" && k !== "in_pause" && k !== "delay") out[k] = withoutOn(v);
  return out;
}

/** The part's place in the operation given its "on" (a string becomes {"name", "on"}). */
function setOn(op: Op, place: (string | number)[], on: string): void {
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
 * never before its element or the part it is in. Emphases, zooms and stamps become operations of their own on their
 * beats. A `manim` beat keeps only its figure (the compiler's rule): what else came on it moves to the next beat of its
 * scene, else is left out. Returns each beat's operations, in the order they come on, and what was mended.
 */
export function lowerPlan(plan: ChapterPlan, cues: Cue[], words: Map<number, BeatWords>, engine: Engine): { ops: Map<number, Op[]>; notes: string[] } {
  const notes: string[] = [];
  const ops = new Map<number, { op: Op; at: [number, number] }[]>();
  for (const s of plan.scenes) for (const b of s.beats) ops.set(b, []);
  const put = (beat: number, word: number, op: Op) => ops.get(beat)?.push({ op, at: [beat, word] });
  const { first, span } = lifeOf(plan);
  const byRef = new Map<string, Cue[]>();
  for (const c of [...cues].sort((a, b) => a.beat - b.beat || a.word - b.word)) byRef.set(c.ref, [...(byRef.get(c.ref) ?? []), c]);
  for (const el of plan.elements) {
    const scene = first.get(el.id);
    const life = span.get(el.id);
    if (!scene || !life) continue;
    const op = withoutOn(el.op) as Op;
    const template = isTemplate(op, engine);
    if (template || op.op === "diagram") op.id ??= el.id;
    const enter = byRef.get(el.id)?.find((c) => c.act === "enter");
    let at: [number, number] = [scene.beats[0], 0];
    if (enter && life.has(enter.beat) && enter.beat <= scene.beats[scene.beats.length - 1]) at = [enter.beat, enter.word];
    else if (enter) notes.push(`${el.id}: its entry (b${enter.beat}.w${enter.word}) is outside its scene ${scene.id}: it comes on as the scene begins`);
    op.on = anchor(at[1]);
    if (enter?.inPause && engine === "motion") op.in_pause = true;
    // Its parts.
    const parts = partsOf(el);
    const entered = new Map<string, [number, number]>([[el.id, at]]);
    const reveals = new Map<string, { beat: number; word: number; nodes: string[] }>();
    const held = new Set<string>();
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
    put(at[0], at[1], op);
    for (const r of reveals.values()) if (r.nodes.length) put(r.beat, r.word, { op: "reveal", diagram: op.id, nodes: r.nodes, on: anchor(r.word) });
    // What is done with it while it is up.
    const partOf = new Map(parts.map((p) => [p.ref, p]));
    for (const c of cues.filter((x) => x.act === "emphasis" || x.act === "zoom")) {
      const p = partOf.get(c.ref);
      if (c.ref !== el.id && !p) continue;
      const since = entered.get(c.ref);
      if (!life.has(c.beat) || !since || before([c.beat, c.word], since)) {
        notes.push(`${c.ref}: ${c.act} on b${c.beat}.w${c.word}, when it is not on the screen: left out`);
        continue;
      }
      if (c.act === "zoom") {
        put(c.beat, c.word, { op: "zoom", diagram: op.id, ...(p?.node ? { node: p.node } : {}), ...(c.scale ? { scale: c.scale } : {}), on: anchor(c.word) });
      } else if (op.op === "diagram" && p?.node) {
        put(c.beat, c.word, { op: "focus", diagram: op.id, node: p.node, on: anchor(c.word) });
      } else if (engine === "motion") {
        const target = template ? (p ? `${op.id}.${p.name}` : String(op.id)) : p?.name;
        if (target) put(c.beat, c.word, { op: "emphasis", target, how: c.how ?? "pulse", on: anchor(c.word) });
      } else {
        notes.push(`${c.ref}: an emphasis this engine draws by itself (a named part is pointed at as it is said): left out`);
      }
    }
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
