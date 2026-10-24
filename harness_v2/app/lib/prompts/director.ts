/**
 * The two calls of a chapter built as one piece (lib/director.ts):
 *
 *   - THE DIRECTOR: the scene writer's own instructions (v1's on the current engine, the motion engine's on it) and
 *     the chapter's beats, answered as the chapter's plan: its elements and its scenes, with no timing.
 *   - THE CHOREOGRAPHY: a few scenes at a time, each beat's line as the voice says it (its words by number with their
 *     times), the elements the scenes use with their parts, what may be done with each, and each artifact's manual;
 *     answered as each element's timeline and look: what comes on, or is done, on which word, and how it is drawn.
 */

import { part, type Part, type Prompt } from "./parts";
import { doName, type BeatWords, type CueAct, type PlanElement, type PlanPart, type PlanScene } from "../director";

// ---------------------------------------------------------------- the director -----------------------------------

const DIRECTOR = `You are the DIRECTOR of one chapter of a narrated lecture video. You get the chapter's lines (its BEATS,
each one spoken line, by number) and the PRIMITIVES the engine can draw. You answer with THE CHAPTER'S PLAN
(write_plan): what is on the screen and why, scene by scene. You do not time anything: a choreographer puts each
thing on the word that names it afterwards. Write no "on", "delay" or "in_pause".

HOW TO PLAN
1. Cut the chapter into SCENES where the narration turns to a new idea: 2 to 5 beats each (about 15-40 seconds).
   A chapter of 9 beats has 2-4 scenes, never one.
2. Give each scene ONE MAIN ELEMENT that shows its idea: the primitive that can build up over its lines (a diagram
   whose nodes come one by one, a labelled picture whose parts are lit in turn, a timeline whose events are named,
   a comparison whose columns come in turn, a map whose places come on).
3. Add at most two small things the lines need: a word defined, a key number, a question. At most two main
   elements are on the screen together, and only when they belong together (a picture and its dates).
4. Keep every element small enough to read on a phone (the limits below). An element shows ONE idea of ONE scene:
   the next idea is the next scene's element. Never put the whole chapter into one diagram or one comparison.
5. Vary the scenes (a picture, then a diagram, then a map), and prefer pictures of real people, places and things
   where seeing them teaches; drawn primitives where the idea is a structure.

LIMITS (the engine shrinks or cuts what goes past them)
- A scene: 2-5 beats; 1-3 elements.
- A diagram: 3-6 nodes; each node's label 1-4 words; "items" at most 3, each 1-3 words; an arrow's label 1-2 words.
- A timeline: 2-6 events; each label 1-4 words.
- A comparison: 2-3 columns; 2-3 points each, each point at most 6 words.
- A labelled picture: 2-5 labels, each 1-3 words, of parts that are really in the picture.
- Words on the screen are names and short phrases, never sentences: the narration says the sentences.

THE ANSWER
- elements: everything the chapter shows, once each: {"id": "<short name>", "role": "<subject | part | key_term |
  number | question | contrast | place | person>", "op": {<one operation, all its parts>}}. A diagram's own "id" is
  its element's id. Give a diagram every node, a picture every label, a timeline every event: the choreographer can
  only bring on and point at what you gave.
- scenes: in order, every beat in exactly one: {"id": "S1", "beats": [<a run of beat numbers>], "intent": "<hook |
  explain | build_chain | compare | name_it | story | question | recap>", "uses": [<element ids, the main one
  first>]}. An element may stay up into the next scene (list it in both).
- A manim figure is a scene of its own and its only element.
- beats (optional): {"beat": <n>, "pause"?: 1-2, "about"?: "<what it is about, in English>"}.`;

export const DIRECTOR_TOOL = {
  type: "function" as const,
  function: {
    name: "write_plan",
    description: "Save the chapter's plan: its elements (each an operation with an id and a role) and its scenes (runs of beats, each the elements it uses), the map region when an element points at the map, and the lecture's emblem.",
    parameters: {
      type: "object",
      properties: {
        region: {
          description: 'The map region, when an element points at the map: {"country":"India"} | {"state":"Rajasthan","country":"India"} | {"area":"World" | a continent | a world region}; null for none.',
          anyOf: [{ type: "object", properties: { country: { type: "string" }, state: { type: "string" }, area: { type: "string" } } }, { type: "null" }],
        },
        emblem: { type: "string", description: "One simple object that stands for the whole topic (the lecture's emblem)." },
        elements: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              role: { type: "string" },
              op: { type: "object", additionalProperties: true, description: "One operation, with all its parts; no \"on\"." },
            },
            required: ["id", "op"],
          },
        },
        scenes: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              beats: { type: "array", items: { type: "integer" } },
              intent: { type: "string" },
              layout: { type: "string" },
              uses: { type: "array", items: { type: "string" } },
            },
            required: ["beats", "uses"],
          },
        },
        beats: {
          type: "array",
          items: {
            type: "object",
            properties: { beat: { type: "integer" }, paragraph: { type: "boolean" }, pause: { type: "number" }, about: { type: "string" } },
            required: ["beat"],
          },
        },
      },
      required: ["elements", "scenes"],
    },
  },
};

/** The parts of the scene writer's prompt the director keeps: the facts it needs (the subject, the kinds switched
 * off, how pictures are written, the map, the motion engine's templates), none of the per-beat writer's rules. */
const DIRECTOR_KEEPS = new Set(["off", "subject", "v1-matters", "v2-picture-style", "pictures", "templates", "map"]);

/** The director's prompt: its own instructions, the primitives (or the motion engine's templates), the facts kept
 * from the scene writer's prompt, the chapter's lines; with `only` one scene asked again, with `problems` the plan
 * asked again with what was wrong with it. */
export function directorPrompt(scenes: Prompt, o: { chapter: number; beats: number[]; catalog?: string;
  only?: { scene: string; beats: number[]; plan: { elements: PlanElement[]; scenes: PlanScene[] }; note?: string };
  problems?: { plan: unknown; list: string[] } }): Prompt {
  const system: Part[] = [part("director", "THE CHAPTER'S PLAN: how to direct a chapter", "rules", DIRECTOR)];
  if (o.catalog) system.push(part("primitives", "The primitives: what each shows and what can be done with it", "rules",
    `THE PRIMITIVES (the current engine's operations, each with its parts and what the choreographer can do with it):\n${o.catalog}`));
  system.push(...scenes.system.filter((p) => DIRECTOR_KEEPS.has(p.key)));
  const ask = o.only
    ? `Write scene ${o.only.scene} again (write_plan): beats ${o.only.beats.map((b) => `#${b}`).join(", ")} only. The chapter's plan as it ` +
      `is (below): the other scenes stay as they are. Answer with this scene's elements (new ids, or the ids of elements it ` +
      `keeps from the scenes around it) and ONE scene (or a few) covering exactly those beats.`
    : `Write chapter ${o.chapter}'s plan (write_plan): its elements and its scenes, every one of its beats (` +
      `${o.beats.map((b) => `#${b}`).join(", ")}) in exactly one scene, in order, within the LIMITS.`;
  const user = scenes.user.filter((p) => p.key !== "ask");
  if (o.only) {
    user.push(part("plan", "The chapter's plan as it is", "plan", JSON.stringify(o.only.plan)),
      ...(o.only.note ? [part("scene-note", `What to change in scene ${o.only.scene}`, "context", o.only.note)] : []));
  }
  if (o.problems) {
    user.push(part("problems", "Your plan broke the limits", "context", [
      "Your plan (below) broke these rules. Write the whole plan again, keeping what was good, with every one fixed:",
      ...o.problems.list.map((x) => `- ${x}`), "", JSON.stringify(o.problems.plan)].join("\n")));
  }
  user.push(part("ask", "Request", "ask", ask));
  return { system, user };
}

// ---------------------------------------------------------------- the choreography -------------------------------

const CHOREOGRAPHY = `You choreograph a narrated lecture video: when each thing on the screen comes on, and what is done with
it as the narration goes on. The narration is already spoken. You are given a few SCENES of one chapter: each beat's
line as the voice says it, every word numbered (w0 the first) with the second it is said from the line's start; the
ELEMENTS the scenes use (each an operation of the engine, with its parts and what you may do with each); and each
artifact's MANUAL (what the engine draws and how it moves). Answer with each element's TIMELINE and LOOK
(choreograph): every element and every part an entry, and the moments that make the scene alive.

AN ELEMENT: {"id": "<element id>", "timeline": [<steps, in order>], "look"?: {...}}
A STEP: {"at": "b<beat>.w<word>", "do": "<one it may do>", "part"?: "<part, as given after the element's id>", ...}
  - "enter" (the element, no "part"): it comes on as that word is said. "in_pause": true: in the quiet after its
    line instead (a card that sums the line up).
  - "show" (a part): the part comes on as that word is said. On a labelled picture: "note" (a few words) is written small under its name (a date, a number, what it does). A labelled picture's
    label may be shown on a later line of the picture's scenes than the picture, as a diagram's node may.
  - "pulse" (where allowed): it is pointed at once on that word ("how", on the motion engine: one of the manual's
    ways). For what the line stresses: a contrast ("but", "only", "never"), a number, the answer, the word the idea
    turns on.
  - "light" (a labelled picture's part, where allowed): the rest of the picture shaded round the part while it is
    explained: until the next line, or a light on another part; with "until": "b<beat>.w<word>", held over the lines
    between and lifted on that word.
  - "focus" (a diagram's node, where allowed): it is ringed and the rest of the diagram dimmed while it is talked
    about; with "until", lifted on that word.
  - "hide" (a labelled picture's label, where allowed): the label taken off on that word (the picture stays), when
    the picture moves on to its other parts.
  - "exit" (an element, where allowed): it is taken off the screen on that word, when the idea it showed is done and
    nothing new replaces it (a new picture takes the last one off by itself: no exit then).
A LOOK: how the element is drawn, from its manual's own fields: a picture's "move" ("drift", "push", "pan"), a
diagram's "flow" or "steps", a timeline's "spans" or "range", a card's "style". Never its content (its nodes, labels,
words): those are the director's. Leave it out when the director's is right.
A STAMP (where allowed; in "stamps", not in a timeline): {"at", "scene": "<scene id>", "text": "<1-3 words>",
"in_pause"?: true}: a stamp slammed onto what is up: a verdict, a name, a number to remember. One a scene at most,
often none; best in the quiet after its line.

WHEN
- A thing comes on as the voice NAMES it: the first word that names it (the noun, the name, the number, the date),
  never a small word before it ("the", "a", "of", "and", "है", "का", "की", "के", "में"). A name may be said in another
  spelling or script: the word where the line says it.
- A scene's main element comes on with the scene's first line, near its start, on the word that brings in its idea
  (the cut lands as the idea changes). What a later line adds to it comes on that line's words.
- A part never before the element it is in. A diagram's nodes (and only they) may come on in any line of the
  element's scenes: each on the line, and the word, that names it. Every other part comes on in its element's own
  line: give it a word of that line.
- AT MOST TWO MAIN PICTURES AT ONCE: a picture, a diagram, a timeline, a comparison or a gallery takes the stage,
  and what was up before goes. Two brought on in ONE line are laid out together (side by side, or one over the
  other); a third in that line waits for a later one. A main picture brought on in a later line replaces both:
  from then on point only at what is on it (a light on the picture before it, a pulse at its labels, is lost).
  Hold each for its lines: a main picture shown for a second and replaced is never seen.
- Each moment must be seen: keep them about 0.6 s apart or more (the times tell you); parts said in one breath may
  share a word. Not everything on w0. At most about three moments in a second.
- Make every line do something: in a line that adds nothing new, point at what it speaks of (a pulse, a light, a
  focus). There is no camera: nothing zooms or pans.
- Nothing happens that you do not write: a part with no step comes on as its line begins, and nothing is pointed at
  because the line says its name.
- Use only the elements, parts and steps given. Do not invent elements. Every element of these scenes once in
  "elements", even with no steps (one already on the screen).

BE RICH: the video is alive only when something moves on every line, on its words. Use each primitive's manual
("HOW TO CHOREOGRAPH"): bring every part on by itself on the word that names it, never all at once; on a diagram,
focus the node being explained and bring the next nodes on in the lines that name them; on a labelled picture, show
each label on the line that explains it, light each part as it is explained (held with "until" while a few lines
explain it), hide a label when the picture moves on; pulse what a line names again; take a picture off (exit) when
its idea is done and nothing replaces it. A scene of four lines should have ten or more
moments, each on its word, about a second or more apart.`

const STEP = {
  type: "object",
  properties: {
    at: { type: "string", description: "b<beat>.w<word>, e.g. b12.w3." },
    do: { type: "string", enum: ["enter", "show", "pulse", "light", "focus", "hide", "exit"] },
    part: { type: "string", description: "The part (its name after the element's id), for show, pulse, light, focus, hide." },
    until: { type: "string", description: "b<beat>.w<word>: a light or a focus held until this word." },
    how: { type: "string" },
    note: { type: "string" },
    in_pause: { type: "boolean" },
  },
  required: ["at", "do"],
  additionalProperties: false,
};

export const CHOREOGRAPHY_TOOL = {
  type: "function" as const,
  function: {
    name: "choreograph",
    description: "Each element's timeline (its entry, its parts' entries, the pulses, lights, focuses, hides and exits, each on a word) and look, and the scenes' stamps.",
    parameters: {
      type: "object",
      properties: {
        elements: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              timeline: { type: "array", items: STEP },
              look: { type: "object", description: "How it is drawn (its manual's fields: move, flow, steps, spans, range, style). Not its content." },
            },
            required: ["id", "timeline"],
            additionalProperties: false,
          },
        },
        stamps: {
          type: "array",
          items: {
            type: "object",
            properties: { at: { type: "string" }, scene: { type: "string" }, text: { type: "string" }, in_pause: { type: "boolean" } },
            required: ["at", "scene", "text"],
            additionalProperties: false,
          },
        },
      },
      required: ["elements"],
      additionalProperties: false,
    },
  },
};

export type ChoreographyElement = { el: PlanElement; parts: PlanPart[]; acts: { element: CueAct[]; parts: CueAct[]; laterParts: boolean };
  scene: string; already: boolean };

/** One call's prompt: its scenes' lines and words, their elements and what may be done with each, the manuals. */
export function choreographyPrompt(o: { lecture: number; chapter: number; engine: "current" | "motion"; look: string;
  scenes: PlanScene[]; words: Map<number, BeatWords>; elements: ChoreographyElement[]; manuals: { op: string; text: string }[];
  before?: string; after?: string; stamps: boolean }): Prompt {
  const lines = o.scenes.map((s) => [
    `SCENE ${s.id} (beats ${s.beats[0]}-${s.beats[s.beats.length - 1]}${s.intent ? `, ${s.intent}` : ""}${s.layout ? `, ${s.layout}` : ""}): uses ${s.uses.join(", ")}`,
    ...s.beats.map((b) => {
      const w = o.words.get(b);
      if (!w) return `  b${b}: (no words)`;
      return `  b${b} (${w.seconds} s, then ${w.pause} s quiet${w.estimated ? "; times estimated" : ""}): "${w.text}"\n` +
        `     ${w.words.map((x, i) => `w${i} ${x.w} ${x.t.toFixed(1)}`).join(" | ")}`;
    }),
  ].join("\n"));
  const elements = o.elements.map((e) => [
    `ELEMENT ${e.el.id} (${String(e.el.op.op)}${e.el.role ? `, ${e.el.role}` : ""}) in scene ${e.scene}${e.already ? " -- ALREADY ON THE SCREEN (came on before): do not enter it again" : ""}`,
    `  it may: ${e.acts.element.map((a) => doName(a, false)).join(", ")}${e.parts.length ? `; each part may: ${e.acts.parts.map((a) => doName(a, true)).join(", ")}${e.acts.laterParts ? " (and be shown in a later line of its scenes)" : " (shown in its element's line)"}` : ""}`,
    `  op: ${JSON.stringify(e.el.op)}`,
    ...(e.parts.length ? [`  parts: ${e.parts.map((p) => `${p.ref.slice(e.el.id.length + 1)} ${JSON.stringify(p.name)}${p.parent ? ` (in ${p.parent})` : ""}`).join(" · ")}`] : []),
  ].join("\n"));
  return {
    system: [
      part("choreography", "How to choreograph the scenes", "rules", CHOREOGRAPHY),
      ...(o.stamps ? [] : [part("no-stamps", "Not on this engine", "rules", "This engine has no stamps. The engine points at nothing by itself: what is pulsed, lit, focused, hidden or taken off is only what you write.")]),
      part("manuals", `The manuals of this call's artifacts (${o.manuals.length})`, "rules",
        o.manuals.map((m) => `=== ${m.op} ===\n${m.text}`).join("\n\n")),
    ],
    user: [
      part("frame", "Where these scenes are", "context", [
        `Lecture ${o.lecture}, chapter ${o.chapter}, drawn ${o.engine === "motion" ? "on the motion engine" : "on the current engine"} in ${o.look}.`,
        ...(o.before ? [`Just before: ${o.before}`] : ["These scenes open the chapter (after its title card)."]),
        ...(o.after ? [`Just after: ${o.after}`] : ["These scenes end the chapter."]),
      ]),
      part("scenes", "The scenes, their lines and words", "book", lines),
      part("elements", "Their elements, parts and what may be done with them", "items", elements),
      part("ask", "Request", "ask", "Choreograph these scenes (choreograph): every element not already on the screen and every part an entry, then the moments that keep each line alive."),
    ],
  };
}
