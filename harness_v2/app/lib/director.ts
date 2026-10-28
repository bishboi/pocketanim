/**
 * What a chapter's director and choreographer (lib/beat-director.ts) share: the limits a beat's operations are held to
 * (told to the director in prompts/beat-director.ts), an operation's parts (what can come on by itself on a word),
 * an operation's "on" set or taken out, and a line's words when it is not spoken yet.
 */

type Op = Record<string, unknown>;

export type PlanElement = { id: string; role?: string; op: Op };
export type PlanPart = { ref: string; element: string; place: (string | number)[]; name: string; parent?: string; node?: string };

/** What a look may not change: the element's own content (the director's). */
export const NOT_LOOK = new Set(["op", "id", "on", "nodes", "edges", "labels", "items", "events", "steps_of", "show", "hide", "text", "title"]);
/** A beat's line as the voice says it (or, unspoken, as it would be: `estimated`). */
export type BeatWords = { n: number; text: string; seconds: number; pause: number; words: { w: string; t: number }[]; estimated?: boolean };

/** A part's name (compile_lecture.NAMED_BY). */
const NAMED_BY = ["label", "text", "title", "name", "term", "date", "place"];
/** Lists of ids, places on the screen, colours: no thing of their own. */
const NOT_PARTS = new Set(["show", "hide", "ids", "order", "range", "colors", "colours", "keep", "path", "at", "from", "to", "size",
  "edges", "box", "values", "frames", "picture"]);
export const isObj = (x: unknown): x is Op => !!x && typeof x === "object" && !Array.isArray(x);
const nameOf = (o: Op) => NAMED_BY.map((k) => o[k]).find((v) => (typeof v === "string" || typeof v === "number") && String(v).trim());

export function slug(text: string): string {
  return String(text).toLowerCase().normalize("NFC").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 24) || "x";
}

// ---------------------------------------------------------------- limits --------------------------------------------

/** What the director is held to (told it in prompts/beat-director.ts LIMITS): small paragraphs, small pictures. */
export const LIMITS = { sceneBeats: 5, sceneElements: 3, nodes: 6, nodeWords: 4, items: 3, itemWords: 3, edgeWords: 2,
  events: 6, eventWords: 4, columns: 3, points: 3, pointWords: 6, labels: 5, labelWords: 3 };

const wordCount = (x: unknown) => String(x ?? "").trim().split(/\s+/).filter(Boolean).length;
const nameOfLabel = (x: unknown) => (isObj(x) ? String(x.name ?? "") : String(x ?? ""));

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

/** Every "on" taken out of an operation: the patch says when. */
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

/** A line's words, unspoken: each at about 0.4 s (143 words a minute, as the engine estimates). */
export function estimatedWords(n: number, text: string): BeatWords {
  const words = text.split(/\s+/).filter(Boolean).map((w, i) => ({ w, t: Math.round(i * 0.42 * 10) / 10 }));
  return { n, text, seconds: Math.round(words.length * 0.42 * 10) / 10, pause: 0.4, words, estimated: true };
}
