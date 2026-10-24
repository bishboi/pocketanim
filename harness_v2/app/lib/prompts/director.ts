/**
 * The two calls of a chapter built as one piece (lib/director.ts):
 *
 *   - THE DIRECTOR: the scene writer's own instructions (v1's on the current engine, the motion engine's on it) and
 *     the chapter's beats, answered as the chapter's plan: its elements and its scenes, with no timing.
 *   - THE CHOREOGRAPHY: a few scenes at a time, each beat's line as the voice says it (its words by number with their
 *     times), the elements the scenes use with their parts, what may be done with each, and each artifact's manual;
 *     answered as cues: what comes on, or is done, on which word.
 */

import { part, type Part, type Prompt } from "./parts";
import type { BeatWords, CueAct, PlanElement, PlanPart, PlanScene } from "../director";

// ---------------------------------------------------------------- the director -----------------------------------

const DIRECTOR = `THIS CALL'S ANSWER: THE CHAPTER'S PLAN (write_plan). It replaces the per-beat answer described above: the
operations are written exactly as above, but each is an ELEMENT of the chapter, and the chapter is cut into SCENES.
You say WHAT is on the screen and WHY; a second call, shown the voice's word times, says WHEN each element and each
of its parts comes on, and points, zooms and stamps as the lines go on. So write no "on", "delay" or "in_pause":
they are taken out.

ELEMENTS: everything the chapter shows, once each:
  {"id": "<short name: chain, river, surplus>", "role": "<subject | part | key_term | number | question | contrast |
   place | person | annotation>", "op": {<one operation, as above, with all its parts>}}
  - Give an element ALL the parts it will show over its scene: a diagram's every node (they are brought on as they
    are said, in a later line too), a picture's every label, a timeline's every event, a chain's every step. Never
    split one picture into several elements to bring its parts on later.
  - A diagram's "id" is its element's id.

SCENES: the chapter cut into scenes, in order, every beat in exactly one:
  {"id": "S1", "beats": [<its beats' numbers, a run in order>], "intent": "<hook | explain | reveal_parts |
   build_chain | compare | count_up | zoom_detail | name_it | story | recap>", "layout"?: "<full | main+side>",
   "uses": [<the ids of the elements on screen in it>]}
  - A scene is ONE IDEA of the narration (usually 2-6 beats, 15-40 s): one main element (a picture, a diagram, a
    template, a map run) held while the idea is explained, and what is added to it as the lines go on (a definition
    beside it, a number, its parts). A new scene only where the idea changes: its main element replaces the last.
  - An element may go on into the next scene when it stays up (list it in both): it comes on in the first.
  - A manim figure is a scene of its own, its only element.

Also, by beat when it matters: "beats": [{"beat": <n>, "paragraph"?: true, "pause"?: 1-2, "about"?: "<English name>"}].
The first beat of each scene starts a paragraph by itself.`;

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

/** The scene writer's prompt made the director's: its instructions on how operations are written kept, the parts on
 * anchors and timing (the choreography's) taken out, the plan's answer told, and the request asked again. */
export function directorPrompt(scenes: Prompt, o: { chapter: number; beats: number[] }): Prompt {
  const timing = new Set(["v2-anchors", "anchors", "timing"]);
  const system: Part[] = [];
  for (const p of scenes.system) {
    if (timing.has(p.key)) continue;
    system.push(p);
    if (p.key === "shape") system.push(part("director", "The answer: the chapter's plan (elements and scenes)", "rules", DIRECTOR));
  }
  if (!system.some((p) => p.key === "director")) system.push(part("director", "The answer: the chapter's plan (elements and scenes)", "rules", DIRECTOR));
  const user = scenes.user.map((p) => (p.key !== "ask" ? p : part("ask", "Request", "ask",
    `Write chapter ${o.chapter}'s plan (write_plan): its elements and its scenes, every one of its beats (` +
    `${o.beats.map((b) => `#${b}`).join(", ")}) in one scene, in order.`)));
  return { system, user };
}

// ---------------------------------------------------------------- the choreography -------------------------------

const CHOREOGRAPHY = `You choreograph a narrated lecture video: when each thing on the screen comes on, and what is done with
it as the narration goes on. The narration is already spoken. You are given a few SCENES of one chapter: each beat's
line as the voice says it, every word numbered (w0 the first) with the second it is said from the line's start; the
ELEMENTS the scenes use (each an operation of the engine, with its parts and what you may do with each); and each
artifact's MANUAL (what the engine draws and how it moves). Answer with cues (choreograph): every element and every
part their entry, and the moments that make the scene alive.

A CUE: {"at": "b<beat>.w<word>", "ref": "<element or part, as given>", "act": "<one it may do>", ...}
  - "enter": it comes on as that word is said.
  - "emphasis" (where allowed): it is pointed at on that word ("how", on the motion engine: one of the manual's ways;
    a diagram's node is ringed, the rest dimmed). For what the line stresses: a contrast ("but", "only", "never"),
    a number, the answer, the word the idea turns on.
  - "zoom" (a diagram, or one of its nodes): the camera moves in on it ("scale" 1.1-3); on the whole diagram, back out.
  - "stamp" (where allowed): {"at", "ref": "<scene id>", "act": "stamp", "text": "<1-3 words>", "in_pause"?: true}: a
    stamp slammed onto what is up: a verdict, a name, a number to remember. One a scene at most, often none; best in
    the quiet after its line ("in_pause": true).
  - "in_pause": true on an "enter": it comes on in the quiet after its line instead (a card that sums the line up).

WHEN
- A thing comes on as the voice NAMES it: the first word that names it (the noun, the name, the number, the date),
  never a small word before it ("the", "a", "of", "and", "है", "का", "की", "के", "में"). A name may be said in another
  spelling or script: the word where the line says it.
- A scene's main element comes on with the scene's first line, near its start, on the word that brings in its idea
  (the cut lands as the idea changes). What a later line adds to it comes on that line's words.
- A part never before the element it is in. A diagram's nodes (and only they) may come on in any line of the
  element's scenes: each on the line, and the word, that names it. Every other part comes on in its element's own
  line: give it a word of that line.
- Each moment must be seen: keep them about 0.6 s apart or more (the times tell you); parts said in one breath may
  share a word. Not everything on w0. At most about three moments in a second.
- Make every line do something: in a line that adds nothing new, point at what it speaks of (an emphasis, a zoom).
  But never more than two emphases in a line.
- Use only the refs and acts given. Do not invent elements.`;

export const CHOREOGRAPHY_TOOL = {
  type: "function" as const,
  function: {
    name: "choreograph",
    description: "The scenes' cues: each element's and part's entry, and the emphases, zooms and stamps, each on a word.",
    parameters: {
      type: "object",
      properties: {
        cues: {
          type: "array",
          items: {
            type: "object",
            properties: {
              at: { type: "string", description: "b<beat>.w<word>, e.g. b12.w3." },
              ref: { type: "string", description: "An element's or a part's ref (or a scene's id, for a stamp)." },
              act: { type: "string", enum: ["enter", "emphasis", "zoom", "stamp"] },
              how: { type: "string" },
              scale: { type: "number" },
              text: { type: "string" },
              in_pause: { type: "boolean" },
            },
            required: ["at", "ref", "act"],
            additionalProperties: false,
          },
        },
      },
      required: ["cues"],
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
    `  it may: ${e.acts.element.join(", ")}${e.parts.length ? `; each part may: ${e.acts.parts.join(", ")}${e.acts.laterParts ? " (and come on in a later line of its scenes)" : " (in its element's line)"}` : ""}`,
    `  op: ${JSON.stringify(e.el.op)}`,
    ...(e.parts.length ? [`  parts: ${e.parts.map((p) => `${p.ref} ${JSON.stringify(p.name)}${p.parent ? ` (in ${p.parent})` : ""}`).join(" · ")}`] : []),
  ].join("\n"));
  return {
    system: [
      part("choreography", "How to choreograph the scenes", "rules", CHOREOGRAPHY),
      ...(o.stamps ? [] : [part("no-stamps", "Not on this engine", "rules", "This engine has no stamps and no emphasis of its own on a picture: a picture's labelled parts are pointed at by the engine as they are said. Use emphasis only where an element's line says it may.")]),
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
