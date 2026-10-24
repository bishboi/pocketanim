/**
 * A chapter built as one piece on the current engine, in one JSON: the beat script itself.
 *
 *   - THE DIRECTOR (one call a chapter) writes the chapter's beats: each beat's operations (`do`), what it shows and
 *     on which line each part of it comes on (a diagram's `show` and later `reveal`s, a labelled picture's `hold` and
 *     later `label`s), where a paragraph (a scene) starts, a pause, and whether a line's main picture joins the one
 *     up (`"screen": "join"`). Nothing timed: no "on", and no pointing (that is the choreographer's).
 *   - THE CHOREOGRAPHER (one call for a few paragraphs, at once) answers a PATCH on those beats: each step on a word
 *     of its line -- when each operation (and each of its parts) comes on, and the pulses, lights, focuses, hides and
 *     exits -- and how an operation is drawn (its look). It cannot change what the director wrote: code applies the
 *     patch, and a step that names no operation or part of its beat is left out, with a note.
 *   - The beats the engine reads are the director's beats with the patch applied (applyPatch). Both are kept
 *     (`plans[chapter]`, kind "beats"), seen and changed by hand on the Scenes tab.
 */

import { fitOp, isObj, NOT_LOOK, opProblems, partsOf, LIMITS, setOn, withoutOn, type BeatWords } from "./director";
import { ENTRANCES, POINT_HOWS, SPEEDS } from "./primitives";

type Op = Record<string, unknown>;

/** One beat as the director writes it: what it shows, no timing. */
export type ContentBeat = { beat: number; do: Op[]; paragraph?: boolean; pause?: number; about?: string; screen?: "join" };
/** One step of the choreographer's patch, on a word of its beat's line. */
export type PatchStep = { at: string; do: string; op?: number; part?: string; target?: string; diagram?: string; node?: string;
  until?: string; how?: string; enter?: string; speed?: string };
/** The choreographer's patch for one beat: its steps, and how its operations are drawn. */
export type BeatPatch = { beat: number; steps: PatchStep[]; look?: ({ op: number } & Op)[] };
/** A chapter built as one piece, as kept: the director's beats and the choreographer's patch. */
export type BeatsPlan = { kind: "beats"; beats: ContentBeat[]; patch: BeatPatch[]; at?: number; notes?: string[] };

/** The steps a choreographer may write. */
export const STEPS = ["enter", "show", "pulse", "light", "focus", "hide", "exit"] as const;
/** What takes the stage on the current engine (two in one line share it; compile_lecture.STAGE_MAIN). */
export const MAIN = new Set(["picture", "photo", "illustration", "figure", "gallery", "diagram", "timeline", "compare", "process",
  "quote", "draw", "problem", "molecule"]);
/** The pointing the choreographer writes, never the director (left out of its beats with a note). */
const POINTING = new Set(["point", "shade", "unshade", "focus", "unfocus", "unlabel", "unstage", "emphasis", "zoom"]);

export const isPlanOfBeats = (x: unknown): x is BeatsPlan => isObj(x) && x.kind === "beats";

// ---------------------------------------------------------------- the director's beats ------------------------------

/**
 * The director's answer as the chapter's beats: one for each of its beats (`own`), in order, each with its
 * operations (every "on" taken out: the choreographer times them; pointing taken out: the choreographer points), its
 * paragraph (the first beat always starts one), pause, about and `screen`. A beat it did not write shows nothing new.
 */
export function readBeats(reply: Op, own: number[]): { beats: ContentBeat[]; notes: string[] } {
  const notes: string[] = [];
  const given = new Map<number, Op>();
  for (const b of Array.isArray(reply.beats) ? reply.beats : []) {
    if (isObj(b) && own.includes(Math.round(Number(b.beat)))) given.set(Math.round(Number(b.beat)), b);
  }
  const beats = own.map((n, i): ContentBeat => {
    const b = given.get(n);
    if (!b) {
      notes.push(`beat ${n}: not written: it shows nothing new`);
      return { beat: n, do: [], ...(i === 0 ? { paragraph: true } : {}) };
    }
    const ops: Op[] = [];
    for (const op of Array.isArray(b.do) ? b.do : []) {
      if (!isObj(op) || typeof op.op !== "string") continue;
      if (POINTING.has(op.op)) {
        notes.push(`beat ${n}: ${op.op} left out: pointing is the choreographer's`);
        continue;
      }
      ops.push(withoutOn(op) as Op);
    }
    const pause = Number(b.pause);
    return { beat: n, do: ops, ...(b.paragraph === true || i === 0 ? { paragraph: true } : {}),
      ...(Number.isFinite(pause) && pause > 0 ? { pause: Math.min(pause, 2) } : {}),
      ...(typeof b.about === "string" && b.about.trim() ? { about: b.about.trim().slice(0, 120) } : {}),
      ...(b.screen === "join" ? { screen: "join" as const } : {}) };
  });
  return { beats, notes };
}

/** The chapter's paragraphs (its scenes): runs of beat numbers, each from a beat that starts one. */
export function paragraphsOf(beats: ContentBeat[]): number[][] {
  const out: number[][] = [];
  for (const b of beats) {
    if (b.paragraph || !out.length) out.push([]);
    out[out.length - 1].push(b.beat);
  }
  return out;
}

/** Where the director's beats go past LIMITS, each said so it can fix them (none: within them). */
export function beatsProblems(beats: ContentBeat[]): string[] {
  const out: string[] = [];
  for (const run of paragraphsOf(beats)) {
    if (run.length > LIMITS.sceneBeats) out.push(`the paragraph from beat ${run[0]} has ${run.length} beats (at most ${LIMITS.sceneBeats}): start a new paragraph where the idea turns`);
  }
  for (const b of beats) {
    const mains = b.do.filter((op) => MAIN.has(String(op.op))).length;
    if (mains > 2) out.push(`beat ${b.beat} brings on ${mains} main pictures (at most 2, and only when they belong together)`);
    b.do.forEach((op, i) => out.push(...opProblems(`beat ${b.beat} op ${i}`, op)));
  }
  return out;
}

/** The director's beats brought within LIMITS by code: a long paragraph cut (a new one started), each operation's
 * lists and words cut. What was cut, each said. (A third main picture in a line is the compiler's to move.) */
export function fitBeats(beats: ContentBeat[]): string[] {
  const notes: string[] = [];
  for (const run of paragraphsOf(beats)) {
    if (run.length <= LIMITS.sceneBeats) continue;
    const parts = Math.ceil(run.length / LIMITS.sceneBeats);
    const size = Math.ceil(run.length / parts);
    for (let k = 1; k < parts; k++) {
      const b = beats.find((x) => x.beat === run[k * size]);
      if (b) b.paragraph = true;
    }
    notes.push(`the paragraph from beat ${run[0]}: ${run.length} beats cut into ${parts}`);
  }
  for (const b of beats) b.do.forEach((op, i) => notes.push(...fitOp(`beat ${b.beat} op ${i}`, op)));
  return notes;
}

// ---------------------------------------------------------------- what the choreographer is shown -----------------

/** What brings on a part of something already up (on its own word, by its `enter`): no parts of its own. */
const FOLLOW_UPS = new Set(["reveal", "label", "unshade", "unlabel", "unfocus", "unstage", "manim"]);

/** An operation's parts that can come on by themselves in its own line, by name: a diagram's nodes (those it
 * shows: the rest come by a later `reveal`), a picture's labels (but those it holds for a later `label`), a
 * timeline's events, a comparison's columns and points... (partsOf). */
export function opParts(op: Op) {
  if (FOLLOW_UPS.has(String(op.op))) return [];
  const shown = op.op === "diagram" && Array.isArray(op.show) ? new Set(op.show.map(String)) : undefined;
  // Held for a later line (a picture's label, a template's part): not its own line's.
  const held = Array.isArray(op.hold) ? new Set(op.hold.map((x) => norm(x))) : undefined;
  return partsOf({ id: "op", op }).filter((p) => (!shown || !p.node || shown.has(p.node)) && (!held || !held.has(norm(p.name))));
}

/** What is up as each beat begins (the main pictures of the last line that brought any, with the ones it joined):
 * their names, for the choreographer to point at. */
export function upBefore(beats: ContentBeat[]): Map<number, string[]> {
  const out = new Map<number, string[]>();
  let up: Op[] = [];
  for (const b of beats) {
    out.set(b.beat, up.map((op) => `${String(op.op)}${op.id ? ` ${String(op.id)}` : ""}: ${partsOf({ id: "op", op }).slice(0, 8)
      .map((p) => (p.node ? `${p.node} ${JSON.stringify(p.name)}` : JSON.stringify(p.name))).join(", ")}`));
    const mains = b.do.filter((op) => MAIN.has(String(op.op)));
    if (mains.length) up = b.screen === "join" ? [...up, ...mains] : mains;
  }
  return out;
}

/** The parts of a beat's operation the choreographer may `show` by name: its own (opParts); a `reveal`'s nodes (by
 * their labels in the diagram, or ids), each of which may come on on a word of its own; a `label`'s label. Each with
 * the key it is kept by (a node's id, else the name). */
export function stepParts(beats: ContentBeat[], op: Op): { name: string; key: string }[] {
  if (op.op === "reveal" && op.of !== undefined && Array.isArray(op.parts)) return op.parts.map((x) => ({ name: String(x), key: String(x) }));
  if (op.op === "reveal" && Array.isArray(op.nodes)) {
    const diagram = beats.flatMap((b) => b.do).find((o) => o.op === "diagram" && String(o.id) === String(op.diagram));
    const nodes = diagram && Array.isArray(diagram.nodes) ? diagram.nodes.filter(isObj) : [];
    return op.nodes.map((id) => {
      const n = nodes.find((x) => String(x.id) === String(id));
      return { name: String(n?.label ?? id), key: String(id) };
    });
  }
  if (op.op === "label" && typeof op.part === "string") return [{ name: op.part, key: op.part }];
  return opParts(op).map((p) => ({ name: p.name, key: p.name }));
}

// ---------------------------------------------------------------- the patch -----------------------------------------

const WORD = /^\s*w(\d+)\s*$/i;
const UNTIL = /^\s*b?(\d+)\s*\.\s*w(\d+)\s*$/i;
const norm = (x: unknown) => String(x ?? "").toLowerCase().normalize("NFC").replace(/[^\p{L}\p{N}]+/gu, " ").trim();

/**
 * The choreographer's answer as a patch on these beats (only those in `scope`): each step kept when it fits -- a word
 * of its own line, an operation of its beat by index, a part of that operation by name -- else left out and said.
 * An `until` is a later word ("b13.w2") of these beats.
 */
export function readPatch(reply: unknown, beats: ContentBeat[], words: Map<number, BeatWords>, scope?: Set<number>):
  { patch: BeatPatch[]; dropped: string[] } {
  const dropped: string[] = [];
  const patch: BeatPatch[] = [];
  const rows = Array.isArray(reply) ? reply : isObj(reply) && Array.isArray(reply.beats) ? reply.beats : [];
  const byBeat = new Map(beats.map((b) => [b.beat, b]));
  for (const row of rows) {
    if (!isObj(row)) continue;
    const n = Math.round(Number(row.beat));
    const beat = byBeat.get(n);
    if (!beat || (scope && !scope.has(n))) {
      dropped.push(`beat ${String(row.beat)}: not a beat of these lines`);
      continue;
    }
    const last = Math.max(0, (words.get(n)?.words.length ?? 1) - 1);
    const steps: PatchStep[] = [];
    for (const given of Array.isArray(row.steps) ? row.steps : []) {
      if (!isObj(given)) continue;
      // A field left empty (a model may send every field) is a field not given.
      const raw = Object.fromEntries(Object.entries(given).filter(([, v]) => v !== "" && v !== null));
      const said = `beat ${n}: ${JSON.stringify(raw).slice(0, 110)}`;
      const m = WORD.exec(String(raw.at ?? ""));
      if (!m) {
        dropped.push(`${said}: "at" is a word of its line ("w3")`);
        continue;
      }
      const at = `w${Math.min(last, Number(m[1]))}`;
      const what = String(raw.do ?? "");
      if (!(STEPS as readonly string[]).includes(what)) {
        dropped.push(`${said}: no step ${JSON.stringify(what)}`);
        continue;
      }
      const step: PatchStep = { at, do: what };
      if (what === "enter" || what === "show") {
        const k = Number(raw.op);
        const op = beat.do[k];
        if (!Number.isInteger(k) || !op) {
          dropped.push(`${said}: no operation ${String(raw.op)} on this beat`);
          continue;
        }
        step.op = k;
        if (what === "show") {
          const part = stepParts(beats, op).find((p) => norm(p.name) === norm(raw.part) || norm(p.key) === norm(raw.part));
          if (!part) {
            dropped.push(`${said}: its operation has no part ${JSON.stringify(raw.part)}`);
            continue;
          }
          step.part = part.key;
        }
      } else if (what === "pulse") {
        if (!String(raw.target ?? "").trim()) {
          dropped.push(`${said}: a pulse needs its "target"`);
          continue;
        }
        step.target = String(raw.target).trim();
      } else if (what === "light" || what === "hide") {
        if (!String(raw.part ?? "").trim()) {
          dropped.push(`${said}: a ${what} needs its "part" (a labelled picture's label)`);
          continue;
        }
        step.part = String(raw.part).trim();
      } else if (what === "focus") {
        if (!String(raw.diagram ?? "").trim() || !String(raw.node ?? "").trim()) {
          dropped.push(`${said}: a focus needs its "diagram" and "node"`);
          continue;
        }
        step.diagram = String(raw.diagram).trim();
        step.node = String(raw.node).trim();
      }
      if ((what === "light" || what === "focus") && raw.until !== undefined) {
        const u = UNTIL.exec(String(raw.until));
        const ub = u ? Number(u[1]) : NaN;
        if (!u || !byBeat.has(ub) || ub < n || (ub === n && Number(u[2]) <= Number(m[1]))) dropped.push(`${said}: its "until" is not a later word of these beats: not held`);
        else step.until = `b${ub}.w${Math.min(Math.max(0, (words.get(ub)?.words.length ?? 1) - 1), Number(u[2]))}`;
      }
      if (what === "pulse" && raw.how !== undefined) {
        if ((POINT_HOWS as readonly string[]).includes(String(raw.how))) step.how = String(raw.how);
        else dropped.push(`${said}: its "how" is one of ${POINT_HOWS.join(", ")}: a pulse`);
      }
      if (what === "enter") {
        // How the operation comes on and how fast (the shared choices).
        if (raw.enter !== undefined) {
          if ((ENTRANCES as readonly string[]).includes(String(raw.enter))) step.enter = String(raw.enter);
          else dropped.push(`${said}: its "enter" is one of ${ENTRANCES.join(", ")}: its own way`);
        }
        if (raw.speed !== undefined) {
          if ((SPEEDS as readonly string[]).includes(String(raw.speed))) step.speed = String(raw.speed);
          else dropped.push(`${said}: its "speed" is one of ${SPEEDS.join(", ")}: left out`);
        }
      }
      steps.push(step);
    }
    const look: ({ op: number } & Op)[] = [];
    for (const l of Array.isArray(row.look) ? row.look : []) {
      if (!isObj(l) || !beat.do[Number(l.op)]) continue;
      const kept: Op = {};
      for (const [k, v] of Object.entries(l)) {
        if (k === "op") continue;
        if (NOT_LOOK.has(k)) dropped.push(`beat ${n} op ${String(l.op)}: its look cannot change ${JSON.stringify(k)} (the director's)`);
        else kept[k] = v;
      }
      if (Object.keys(kept).length) look.push({ op: Number(l.op), ...kept });
    }
    patch.push({ beat: n, steps, ...(look.length ? { look } : {}) });
  }
  return { patch, dropped };
}

/**
 * The beats the engine reads: the director's beats with the patch applied. Each operation and part on its step's
 * word (an operation with none comes on as its line begins); a light a `shade` (held, with an `unshade` at its
 * `until`); a focus a `focus` (an `unfocus` at its `until`); a pulse a `point`; a hide an `unlabel`; an exit an
 * `unstage` (only on a line that brings no new main picture: a new one takes the last off itself). What does not fit
 * is left out, and said.
 */
export function applyPatch(beats: ContentBeat[], patch: BeatPatch[]): { ops: Map<number, Op[]>; notes: string[] } {
  const notes: string[] = [];
  const ops = new Map<number, Op[]>();
  const added = new Map<number, { op: Op; word: number }[]>();
  const wordOf = (on: unknown) => (on === "start" ? 0 : Number(String(on ?? "w0").slice(1)) || 0);
  const add = (beat: number, op: Op) => {
    const word = wordOf(op.on);
    added.set(beat, [...(added.get(beat) ?? []), { op, word }]);
  };
  const untilOf = (u: string) => {
    const m = UNTIL.exec(u)!;
    return { beat: Number(m[1]), on: Number(m[2]) ? `w${m[2]}` : "start" };
  };
  for (const b of beats) ops.set(b.beat, structuredClone(b.do));
  // A reveal's nodes each on the word of its own `show` (a reveal for each word): by beat, op, the node's word.
  const nodesOn = new Map<string, Map<string, string>>();
  for (const p of patch) {
    const own = ops.get(p.beat);
    const beat = beats.find((x) => x.beat === p.beat);
    if (!own || !beat) continue;
    for (const l of p.look ?? []) {
      const op = own[l.op];
      if (!op) continue;
      for (const [k, v] of Object.entries(l)) if (k !== "op" && !NOT_LOOK.has(k)) op[k] = withoutOn(v);
    }
    for (const s of p.steps) {
      const on = s.at === "w0" ? "start" : s.at;
      if (s.do === "enter" && s.op !== undefined && own[s.op]) {
        own[s.op].on = on;
        if (s.enter) own[s.op].enter = s.enter;
        if (s.speed) own[s.op].speed = s.speed;
      }
      else if (s.do === "show" && s.op !== undefined && own[s.op]) {
        const op = own[s.op];
        if (op.op === "reveal") {
          const k = `${p.beat}.${s.op}`;
          nodesOn.set(k, (nodesOn.get(k) ?? new Map()).set(String(s.part), on));
        } else if (op.op === "label") op.on = on;
        else {
          const part = opParts(op).find((x) => x.name === s.part);
          if (part) setOn(op, part.place, on);
        }
      } else if (s.do === "pulse") add(p.beat, { op: "point", target: s.target, on, ...(s.how && s.how !== "pulse" ? { how: s.how } : {}) });
      else if (s.do === "light") {
        add(p.beat, { op: "shade", part: s.part, on, ...(s.until ? { hold: true } : {}) });
        if (s.until) {
          const u = untilOf(s.until);
          add(u.beat, { op: "unshade", on: u.on });
        }
      } else if (s.do === "focus") {
        add(p.beat, { op: "focus", diagram: s.diagram, node: s.node, on });
        if (s.until) {
          const u = untilOf(s.until);
          add(u.beat, { op: "unfocus", diagram: s.diagram, on: u.on });
        }
      } else if (s.do === "hide") add(p.beat, { op: "unlabel", part: s.part, on });
      else if (s.do === "exit") {
        if (beat.do.some((op) => MAIN.has(String(op.op)))) notes.push(`beat ${p.beat}: exit left out: the line brings on a new picture, which takes the last off itself`);
        else add(p.beat, { op: "unstage", on });
      }
    }
  }
  for (const [k, on] of nodesOn) {
    const [beat, i] = k.split(".").map(Number);
    const op = ops.get(beat)?.[i];
    // A diagram's nodes, or a template's parts held back (`of`).
    const key = op?.of !== undefined ? "parts" : "nodes";
    if (!op || !Array.isArray(op[key])) continue;
    const words = new Map<string, string[]>();
    for (const id of (op[key] as unknown[]).map(String)) {
      const w = on.get(id) ?? String(op.on ?? "start");
      words.set(w, [...(words.get(w) ?? []), id]);
    }
    const [first, ...rest] = [...words].sort((a, b) => wordOf(a[0]) - wordOf(b[0]));
    op[key] = first[1];
    op.on = first[0];
    for (const [w, ids] of rest) add(beat, key === "parts" ? { op: "reveal", of: op.of, parts: ids, on: w } : { op: "reveal", diagram: op.diagram, nodes: ids, on: w });
  }
  for (const [beat, list] of added) ops.get(beat)?.push(...list.map((x) => x.op));
  // Each beat's operations in the order of their words; on one word what comes on before what points at it.
  const pointing = (op: Op) => (POINTING.has(String(op.op)) ? 1 : 0);
  for (const [beat, list] of ops) {
    ops.set(beat, list.map((op, i) => ({ op, i })).sort((a, b) => wordOf(a.op.on) - wordOf(b.op.on) || pointing(a.op) - pointing(b.op) || a.i - b.i)
      .map((x) => x.op));
  }
  return { ops, notes };
}

/** Of a patch, the steps that still fit beats changed by hand (an operation gone, a part renamed: left out). */
export function patchStillFits(patch: BeatPatch[], beats: ContentBeat[], words: Map<number, BeatWords>) {
  return readPatch(patch, beats, words);
}
