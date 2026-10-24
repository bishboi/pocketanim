/**
 * The two calls of a chapter built as one piece on the current engine (lib/beat-director.ts):
 *
 *   - THE DIRECTOR: the chapter's lines and the primitives, answered as the chapter's beats themselves: each beat's
 *     operations, which line each part comes on, the paragraphs, pauses and joins. Nothing timed, nothing pointed at.
 *   - THE CHOREOGRAPHER: a few paragraphs at a time, each line as the voice says it (its words by number with their
 *     times), each beat's operations by number with their parts, what is up as it begins, and each artifact's manual;
 *     answered as a patch: steps on words, and looks.
 */

import { part, type Part, type Prompt } from "./parts";
import { LIMITS, type BeatWords } from "../director";
import { stepParts, type ContentBeat } from "../beat-director";

// ---------------------------------------------------------------- the director -----------------------------------

const BEAT_DIRECTOR = `You are the DIRECTOR of one chapter of a narrated lecture video. You get the chapter's lines (its BEATS,
each one spoken line, by number) and the PRIMITIVES the engine can draw. You answer with THE CHAPTER'S BEATS
(write_beats): for every line, what it brings on the screen. You do not time anything: a choreographer puts each
thing on the word that names it afterwards, and points at what is up. Write no "on", "delay" or "in_pause", and no
pointing (no point, shade, unshade, focus, unfocus, unlabel, unstage).

HOW TO DIRECT
1. Cut the chapter into PARAGRAPHS where the narration turns to a new idea: "paragraph": true on each one's first
   beat. 2 to ${LIMITS.sceneBeats} beats each (about 15-40 seconds). A chapter of 9 beats has 2-4 paragraphs, never one.
2. Give each paragraph ONE MAIN PICTURE that shows its idea, brought on in its first line, that BUILDS UP over its
   lines -- you decide on which line each part comes on:
   - a diagram: on its first line with "show": [the ids of the nodes that line names]; each later line that names
     more of it: {"op": "reveal", "diagram": "<its id>", "nodes": [<ids>]}.
   - a labelled picture: on its first line with "hold": [the labels said in later lines]; each later line that
     explains one: {"op": "label", "part": "<the label>"}.
   - a timeline, a comparison, a process: all its parts on its own line (the choreographer brings each on its word).
3. Add at most two small things a line needs: a word defined, a key number, a question.
4. A main picture on a later line REPLACES what was up. With "screen": "join" on that beat, it JOINS the one up
   instead: the two share the screen (a picture and its dates, a before and an after). Two main pictures in one
   line share it too. Never more than two at once, and only when they belong together.
5. A line that adds nothing new has an empty "do": the choreographer points at what it speaks of.
6. Keep every picture small enough to read on a phone (the limits below). It shows ONE idea of ONE paragraph: the
   next idea is the next paragraph's. Never put the whole chapter into one diagram or one comparison.
7. Vary the paragraphs (a picture, then a diagram, then a map), and prefer pictures of real people, places and
   things where seeing them teaches; drawn primitives where the idea is a structure.

LIMITS (the engine shrinks or cuts what goes past them)
- A paragraph: 2-${LIMITS.sceneBeats} beats; a line brings on at most ${LIMITS.sceneElements} things.
- A diagram: 3-${LIMITS.nodes} nodes; each node's label 1-${LIMITS.nodeWords} words; "items" at most ${LIMITS.items}, each 1-${LIMITS.itemWords} words; an arrow's label 1-${LIMITS.edgeWords} words.
- A timeline: 2-${LIMITS.events} events; each label 1-${LIMITS.eventWords} words.
- A comparison: 2-${LIMITS.columns} columns; 2-${LIMITS.points} points each, each point at most ${LIMITS.pointWords} words.
- A labelled picture: 2-${LIMITS.labels} labels, each 1-${LIMITS.labelWords} words, of parts that are really in the picture.
- Words on the screen are names and short phrases, never sentences: the narration says the sentences.

THE ANSWER
- beats: every beat of the chapter, in order: {"beat": <n>, "do": [<operations>], "paragraph"?: true,
  "pause"?: 1-2 (seconds of quiet after the line, for an idea to land), "about"?: "<what it is about, in English>",
  "screen"?: "join"}.
- A diagram's "id" is short and its own; a "reveal" names it. A "label" names a label its picture holds.
- A manim figure is alone on its beat.`;

export const BEAT_DIRECTOR_TOOL = {
  type: "function" as const,
  function: {
    name: "write_beats",
    description: "Save the chapter's beats: each beat's operations (what it brings on, no timing, no pointing), the paragraphs, pauses and joins; the map region when a beat points at the map, and the lecture's emblem.",
    parameters: {
      type: "object",
      properties: {
        region: {
          description: 'The map region, when a beat points at the map: {"country":"India"} | {"state":"Rajasthan","country":"India"} | {"area":"World" | a continent | a world region}; null for none.',
          anyOf: [{ type: "object", properties: { country: { type: "string" }, state: { type: "string" }, area: { type: "string" } } }, { type: "null" }],
        },
        emblem: { type: "string", description: "One simple object that stands for the whole topic (the lecture's emblem)." },
        beats: {
          type: "array",
          items: {
            type: "object",
            properties: {
              beat: { type: "integer" },
              do: { type: "array", items: { type: "object", additionalProperties: true }, description: "The operations this line brings on; no \"on\"." },
              paragraph: { type: "boolean" },
              pause: { type: "number" },
              about: { type: "string" },
              screen: { type: "string", enum: ["join"] },
            },
            required: ["beat", "do"],
          },
        },
      },
      required: ["beats"],
    },
  },
};

/** The parts of the scene writer's prompt the director keeps: the facts it needs (the subject, the kinds switched
 * off, how pictures are written, the map), none of the per-beat writer's rules. */
const DIRECTOR_KEEPS = new Set(["off", "subject", "v1-matters", "v2-picture-style", "pictures", "map"]);

/** The director's prompt: its own instructions, the primitives, the facts kept from the scene writer's prompt, the
 * chapter's lines; with `only` some beats asked again (the chapter's beats shown, the others kept), with `problems`
 * the beats asked again with what was wrong with them (the limits broken, or what the compiler refused). */
export function beatDirectorPrompt(scenes: Prompt, o: { chapter: number; beats: number[]; catalog: string;
  only?: { beats: number[]; all: ContentBeat[]; note?: string; why?: string }; problems?: { beats: unknown; list: string[]; refused?: boolean } }): Prompt {
  const system: Part[] = [part("director", "THE CHAPTER'S BEATS: how to direct a chapter", "rules", BEAT_DIRECTOR),
    part("primitives", "The primitives: what each shows and what can be done with it", "rules",
      `THE PRIMITIVES (the current engine's operations, each with its parts and what the choreographer can do with it):\n${o.catalog}`),
    ...scenes.system.filter((p) => DIRECTOR_KEEPS.has(p.key))];
  const list = (b: number[]) => b.map((x) => `#${x}`).join(", ");
  const ask = o.only
    ? `Write beats ${list(o.only.beats)} again (write_beats), those only${o.only.why ? ` (${o.only.why})` : ""}. The chapter's beats as they are ` +
      `(below): the others stay as they are, so what is up as these begin is what the beats before them put up.`
    : `Write chapter ${o.chapter}'s beats (write_beats): every one of them (${list(o.beats)}), in order, in paragraphs, within the LIMITS.`;
  const user = scenes.user.filter((p) => p.key !== "ask");
  if (o.only) {
    user.push(part("beats-now", "The chapter's beats as they are", "plan", JSON.stringify(o.only.all.map(({ beat, do: ops, paragraph, screen }) =>
      ({ beat, do: ops, ...(paragraph ? { paragraph } : {}), ...(screen ? { screen } : {}) })))),
    ...(o.only.note ? [part("beats-note", "What to change", "context", o.only.note)] : []));
  }
  if (o.problems) {
    user.push(part("problems", o.problems.refused ? "The compiler refused these beats" : "Your beats broke the limits", "context", [
      o.problems.refused
        ? "The compiler could not draw these beats (below), even after mending what it could. Write them again, keeping the idea, with every error fixed:"
        : "Your beats (below) broke these rules. Write them all again, keeping what was good, with every one fixed:",
      ...o.problems.list.map((x) => `- ${x}`), "", JSON.stringify(o.problems.beats)].join("\n")));
  }
  user.push(part("ask", "Request", "ask", ask));
  return { system, user };
}

// ---------------------------------------------------------------- the choreographer ------------------------------

const BEAT_CHOREOGRAPHY = `You choreograph a narrated lecture video: when each thing on the screen comes on, and what is pointed at
as the narration goes on. The narration is already spoken, and the DIRECTOR has written what each line brings on.
You are given a few PARAGRAPHS of one chapter: each beat's line as the voice says it, every word numbered (w0 the
first) with the second it is said from the line's start; each beat's OPERATIONS by number (op 0, op 1...) with
their parts; what is UP as the beat begins; and each artifact's MANUAL. Answer with a PATCH (choreograph_beats):
for each beat its STEPS, each on a word of its own line, and the LOOK of its operations. You cannot change what is
shown: only when, and what is pointed at.

A STEP: {"at": "w<word>", "do": "<step>", ...}
  - "enter" {"op": <n>}: the beat's operation n comes on as that word is said (a "reveal" or a "label" too: its
    nodes or its label come on then).
  - "show" {"op": <n>, "part": "<a part of op n, by its name>"}: that part comes on as that word is said (a
    reveal's nodes each on the word that names it).
  - "pulse" {"target": "<a name on the screen>"}: it is pointed at once (a label, a node, an event, a word).
    For what the line stresses: a contrast ("but", "only", "never"), a number, the answer, the word the idea
    turns on.
  - "light" {"part": "<a label of the labelled picture up>", "until"?: "b<beat>.w<word>"}: the rest of the picture
    shaded round the part while it is explained: until the next light, or held until that later word.
  - "focus" {"diagram": "<its id>", "node": "<node id>", "until"?: "b<beat>.w<word>"}: the node ringed and the rest
    dimmed while it is talked about; with "until", lifted on that word.
  - "hide" {"part": "<a label of the picture up>"}: the label taken off (the picture stays), when it moves on.
  - "exit": what is up taken off, when its idea is done and the line brings nothing new (a new picture takes the
    last one off by itself: no exit then).
A LOOK: {"op": <n>, ...} how the beat's operation n is drawn, from its manual's own fields: a picture's "move"
("drift", "push", "pan"), a diagram's "flow" or "steps", a timeline's "enter", "spans" or "range", a card's "style".
Never its content (its nodes, labels, words): those are the director's. Leave it out when the director's is right.

WHEN
- A thing comes on as the voice NAMES it: the first word that names it (the noun, the name, the number, the date),
  never a small word before it ("the", "a", "of", "and", "है", "का", "की", "के", "में"). A name may be said in another
  spelling or script: the word where the line says it.
- A line's main picture comes on near the line's start, on the word that brings in its idea (the cut lands as the
  idea changes). Its parts each on the word that names them, never all at once.
- Point only at what is up: what the beat brings on, or what is up as it begins. A picture that a new one has
  replaced is gone.
- Each moment must be seen: keep them about 0.6 s apart or more (the times tell you); parts said in one breath may
  share a word. Not everything on w0. At most about three moments in a second.
- Make every line do something: in a line that brings nothing new, point at what it speaks of (a pulse, a light, a
  focus). There is no camera: nothing zooms or pans.
- Nothing happens that you do not write: an operation or part with no step comes on as its line begins, and
  nothing is pointed at because the line says its name.

BE RICH: the video is alive only when something moves on every line, on its words. Use each primitive's manual
("HOW TO CHOREOGRAPH"): bring every part on by itself on the word that names it; on a diagram, focus the node being
explained; on a labelled picture, light each part as it is explained (held with "until" while a few lines explain
it), hide a label when the picture moves on; pulse what a line names again. A paragraph of four lines should have
ten or more moments, each on its word, about a second or more apart.`;

const PATCH_STEP = {
  type: "object",
  properties: {
    at: { type: "string", description: "w<word> of this beat's line, e.g. w3." },
    do: { type: "string", enum: ["enter", "show", "pulse", "light", "focus", "hide", "exit"] },
    op: { type: "integer", description: "enter, show: the beat's operation, by its number." },
    part: { type: "string", description: "show: the part of the operation; light, hide: the picture's label." },
    target: { type: "string", description: "pulse: the name on the screen pointed at." },
    diagram: { type: "string", description: "focus: the diagram's id." },
    node: { type: "string", description: "focus: the node's id." },
    until: { type: "string", description: "light, focus: b<beat>.w<word>, held until this later word." },
  },
  required: ["at", "do"],
  additionalProperties: false,
};

export const BEAT_CHOREOGRAPHY_TOOL = {
  type: "function" as const,
  function: {
    name: "choreograph_beats",
    description: "The patch on these beats: each beat's steps (its operations' and parts' entries, the pulses, lights, focuses, hides and exits, each on a word of its line) and its operations' looks.",
    parameters: {
      type: "object",
      properties: {
        beats: {
          type: "array",
          items: {
            type: "object",
            properties: {
              beat: { type: "integer" },
              steps: { type: "array", items: PATCH_STEP },
              look: { type: "array", items: { type: "object", properties: { op: { type: "integer" } }, required: ["op"], additionalProperties: true },
                description: "How an operation is drawn (its manual's fields: move, flow, steps, enter, spans, range, style). Not its content." },
            },
            required: ["beat", "steps"],
            additionalProperties: false,
          },
        },
      },
      required: ["beats"],
      additionalProperties: false,
    },
  },
};

/** One call's prompt: its paragraphs' lines and words, each beat's operations and parts, what is up as each
 * begins, the manuals. */
export function beatChoreographyPrompt(o: { lecture: number; chapter: number; look: string; paragraphs: ContentBeat[][];
  words: Map<number, BeatWords>; up: Map<number, string[]>; manuals: { op: string; text: string }[]; before?: string; after?: string }): Prompt {
  const lines = o.paragraphs.map((run, k) => [
    `PARAGRAPH ${k + 1} (beats ${run[0].beat}-${run[run.length - 1].beat})`,
    ...run.map((b) => {
      const w = o.words.get(b.beat);
      const said = !w ? `  b${b.beat}: (no words)` : `  b${b.beat} (${w.seconds} s, then ${w.pause} s quiet${w.estimated ? "; times estimated" : ""}): "${w.text}"\n` +
        `     ${w.words.map((x, i) => `w${i} ${x.w} ${x.t.toFixed(1)}`).join(" | ")}`;
      const up = o.up.get(b.beat) ?? [];
      const all = o.paragraphs.flat();
      const ops = b.do.map((op, i) => {
        const parts = stepParts(all, op).map((p) => JSON.stringify(p.name));
        return `     op ${i}: ${JSON.stringify(op)}${parts.length ? `\n        parts: ${parts.join(" · ")}` : ""}`;
      });
      return [said, `     up as it begins: ${up.length ? up.join(" ; ") : "nothing"}${b.screen === "join" ? " (its main picture JOINS it)" : ""}`,
        ...(ops.length ? ops : ["     (brings nothing new: point at what is up)"])].join("\n");
    }),
  ].join("\n"));
  return {
    system: [
      part("choreography", "How to choreograph the beats", "rules", BEAT_CHOREOGRAPHY),
      part("manuals", `The manuals of this call's artifacts (${o.manuals.length})`, "rules",
        o.manuals.map((m) => `=== ${m.op} ===\n${m.text}`).join("\n\n")),
    ],
    user: [
      part("frame", "Where these beats are", "context", [
        `Lecture ${o.lecture}, chapter ${o.chapter}, drawn on the current engine in ${o.look}.`,
        ...(o.before ? [`Just before: ${o.before}`] : ["These beats open the chapter (after its title card)."]),
        ...(o.after ? [`Just after: ${o.after}`] : ["These beats end the chapter."]),
      ]),
      part("beats", "The beats: their lines, words and operations", "book", lines),
      part("ask", "Request", "ask", "Choreograph these beats (choreograph_beats): every operation and every part an entry on its word, then the moments that keep each line alive."),
    ],
  };
}
