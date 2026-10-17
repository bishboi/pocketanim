/**
 * The scenes: what is on screen on each beat of a lecture's script, as the engine's operations (harness_v2/engine,
 * compile_lecture.py). The narration is fixed (the transcript's sentences, as the script grouped them into beats):
 * the model writes only each beat's "do", the visuals.
 *
 * The instructions are v1's, word for word (harness/app/lib/lecture.ts lecturePrompt, as prompts/v1-lecture.ts holds
 * them), in v1's order, with its subject guidance (the engine's genre.py); only how the answer is given is v2's own,
 * since the narration is the script's (fixed). The kinds switched off are named (and code takes them out). Asked for
 * the whole lecture, for one chapter, or for one beat (the rest of its chapter given as it is, for context).
 */

import { part, type Part } from "./parts";
import { V1_FREE_DRAWINGS_HEAD, V1_LECTURE, V1_MANIM_PLAN, V1_MANIM_RULES } from "./v1-lecture";

const ROLE = [
  "You design the visuals of ONE narrated lecture video, beat by beat, as the beat script that a compiler turns into",
  "Manim for a phone renderer. The NARRATION IS FIXED: it is the lecture's transcript, already cut into chapters and",
  "beats, and each beat's sentences (its \"say\") are said exactly as given. Your work is everything else the beat",
  "script holds: each beat's operations (\"do\"), where a paragraph starts and where a line needs a pause, and the",
  "lecture's map region and emblem. The script's note of what is on screen (\"on screen:\") is its writer's plan for",
  "the beat, and a figure named on a beat is shown on it. Everything below is how the beat script is written.",
].join("\n");

/** How the answer is given: v1's script shape with the narration fixed (v2's own). */
const SHAPE = [
  "THE ANSWER (write_scenes): the beat script's parts that are yours, by the beats' numbers; the say of each beat",
  "is the one given and is not written again:",
  '{"region": {"country": "India", "view": "ind"} | {"state": "Rajasthan", "country": "India"} |',
  '   {"area": "World" | a continent ("Asia", "Europe", "Africa") | a world region ("South Asia", "Middle East",',
  '   "Western Europe", "Southern Africa", "Indian subcontinent")} | null,  (an area\'s "state" op fills a country)',
  ' "emblem"?: "<one simple object that stands for the whole topic>",',
  ' "beats": [{"beat": <its number>, "paragraph"?: true, "pause"?: 2, "about"?: "<English name>", "do": [ops]}]}',
  "Chapter titles and their title cards are the script's. A chapter taught on a map (marked so below) needs the region.",
].join("\n");

export const SCENES_TOOL = {
  type: "function" as const,
  function: {
    name: "write_scenes",
    description: "Save the beat script's visual parts: each beat's operations (and paragraph, pause, about), by the beat's number; the lecture's map region when a chapter is on a map, and its emblem.",
    parameters: {
      type: "object",
      properties: {
        region: {
          description: 'The map region, when a chapter is on a map: {"country":"India"} | {"state":"Rajasthan","country":"India"} | {"area":"World" | a continent | a world region}; null for none.',
          anyOf: [{ type: "object", properties: { country: { type: "string" }, state: { type: "string" }, area: { type: "string" } } }, { type: "null" }],
        },
        emblem: { type: "string", description: "One simple object that stands for the whole topic (the lecture's emblem)." },
        beats: {
          type: "array",
          items: {
            type: "object",
            properties: {
              beat: { type: "integer", description: "The beat's number, as given." },
              do: { type: "array", items: { type: "object", additionalProperties: true }, description: "Its operations (0-4)." },
              paragraph: { type: "boolean", description: "The first beat of a paragraph (it gives the paragraph's visual)." },
              pause: { type: "number", description: "Extra seconds after the line, 1-2, rarely." },
              about: { type: "string", description: "The person, movement or place the beat is about, its English name." },
            },
            required: ["beat", "do"],
          },
        },
      },
      required: ["beats"],
    },
  },
};

export type SceneSubject = { genre: string; label: string; guidance?: string; map?: string; kit?: string[] };

export type SceneBeatInput = {
  n: number;
  chapter: number;
  text: string;
  show: string;
  /** The book's figures the script shows on it (a figure may be on several beats). */
  figures?: { id: string; way: string; caption: string; ready: boolean }[];
  /** Its own kinds, when they differ from the lecture's. */
  kinds?: string[];
  /** Its operations now (a beat given for context, or the one being written again). */
  ops?: unknown[];
};

export type ScenesAsk =
  | { what: "lecture" }
  | { what: "chapter"; chapter: number }
  | { what: "beat"; beat: number }
  | { what: "fix"; beats: number[] };

export function scenesPrompt(x: {
  lecture: { n: number; title: string };
  look: string;
  kinds: string[];
  labels: Record<string, string>;
  chapters: { n: number; title: string; narration: string; map: boolean }[];
  beats: SceneBeatInput[];
  figures: { id: string; way: string; caption: string; ready: boolean }[];
  region?: unknown;
  ask: ScenesAsk;
  /** The compiler's errors (and notes) on the beats to fix, by beat. */
  problems?: Record<number, string[]>;
  note?: string;
  /** Manim figures are built by the Manim agent from a plan (else written here as code). */
  manimAgent?: boolean;
  /** The lecture's subject and its kit (the engine's genre.py), as v1 tells it. */
  subject?: SceneSubject;
}): { system: Part[]; user: Part[] } {
  const writing = (b: SceneBeatInput) => x.ask.what === "lecture" || (x.ask.what === "chapter" && b.chapter === x.ask.chapter)
    || (x.ask.what === "beat" && b.n === x.ask.beat) || (x.ask.what === "fix" && x.ask.beats.includes(b.n));
  const beatLine = (b: SceneBeatInput) => [
    `#${b.n} [ch ${b.chapter}] "${b.text}"`,
    `   on screen: ${b.show || "-"}`,
    ...(b.figures ?? []).map((f) => `   figure: ${f.id} (${f.way}${f.ready ? "" : ", not made yet: the book's picture is shown"}) - ${f.caption || "(no caption)"}`),
    ...(b.kinds ? [`   this beat may use only: ${b.kinds.map((k) => x.labels[k] ?? k).join(", ") || "the heading and key point"}`] : []),
    ...(!writing(b) && b.ops ? [`   do (as it is, not to be written): ${JSON.stringify(b.ops)}`] : []),
    ...(writing(b) && b.ops?.length && x.ask.what !== "lecture" ? [`   do now (to be written again): ${JSON.stringify(b.ops)}`] : []),
    ...(x.problems?.[b.n]?.length ? x.problems[b.n].map((p) => `   COMPILER: ${p}`) : []),
  ].join("\n");
  const target = x.ask.what === "lecture" ? `every beat, 1 to ${x.beats.at(-1)?.n ?? 0}`
    : x.ask.what === "chapter" ? `the beats of chapter ${x.ask.chapter} only (${x.beats.filter(writing).map((b) => `#${b.n}`).join(", ")})`
      : x.ask.what === "beat" ? `beat #${x.ask.beat} only (the beats around it are given as they are, so it follows on from them)`
        : `beats ${x.ask.beats.map((n) => `#${n}`).join(", ")} only, mending what the compiler says of each`;
  const off = Object.keys(x.labels).filter((k) => !x.kinds.includes(k));
  const v1 = (key: string, label: string, kind: Part["kind"] = "rules") => part(`v1-${key}`, label, kind, V1_LECTURE[key]);
  return {
    system: [
      part("role", "Role", "rules", ROLE),
      ...(x.subject?.guidance ? [part("subject", `Subject: ${x.subject.label}`, "rules", [
        `SUBJECT. This is a ${x.subject.label} lecture. ${x.subject.guidance}`,
        `The map is used ${x.subject.map} in ${x.subject.label.toLowerCase()} lectures. Often useful in them: ${(x.subject.kit ?? []).join(", ")} (any kind below may be used).`,
      ])] : []),
      v1("matters", "What matters"),
      v1("question", "A question for the class"),
      v1("pauses", "Pauses"),
      v1("pictures", "Every picture is made one of three ways"),
      v1("beat", "A beat"),
      part("shape", "The answer's shape (v2)", "rules", SHAPE),
      v1("ops", "Operations, little text, choosing the visual"),
      v1("stage", "The stage: diagrams, pictures, side by side, other operations"),
      part("v1-free", "Free-form drawings, worked solutions and problems", "rules", V1_FREE_DRAWINGS_HEAD),
      v1("concept", "Concept maps and chains"),
      v1("camera", "Camera"),
      part("v1-manim", x.manimAgent ? "Free-form Manim (planned; the Manim agent writes it)" : "Free-form Manim (written here)", "rules",
        x.manimAgent ? V1_MANIM_PLAN : V1_MANIM_RULES),
      v1("detailed", "Detailed diagrams"),
      v1("map", "Map operations"),
      ...(off.length ? [part("off", `Switched off here (${off.length})`, "choices", [
        "SWITCHED OFF FOR THIS LECTURE: never use these kinds of visual; anything of them is taken out:",
        ...off.map((k) => `  - ${x.labels[k] ?? k}`)])] : []),
    ],
    user: [
      part("look", "The look", "context", `The lecture is drawn in ${x.look}. Do not choose colours outside it.`),
      part("lecture", "The lecture and its chapters", "plan", [`Lecture ${x.lecture.n}: ${x.lecture.title}`,
        ...x.chapters.map((c) => `Chapter ${c.n}: ${c.title} (${c.map ? "on a map" : "on a board"}) - title card: "${c.narration}"`),
        ...(x.region ? [`Map region (already chosen): ${JSON.stringify(x.region)}`] : [])]),
      part("figures", `The lecture's figures (${x.figures.length})`, "items", x.figures.length
        ? x.figures.map((f) => `${f.id}: ${f.way}${f.ready ? "" : " (not made yet)"} - ${f.caption || "(no caption)"}`) : "None."),
      part("script", `The beats (${x.beats.length})`, "book", x.beats.map(beatLine)),
      ...(x.note ? [part("note", "Your note for this", "context", x.note)] : []),
      ...(x.ask.what === "fix" ? [part("retry", "What the compiler refused", "retry",
        "The compiler refused these beats (COMPILER lines above). Write them again so they compile: keep what is right, change what it names.")] : []),
      part("ask", "Request", "ask", `Write the visuals (write_scenes) of ${target}. Give each beat its number and its do (0-4 operations), and ` +
        `"paragraph": true on the first beat of each paragraph.`),
    ],
  };
}
