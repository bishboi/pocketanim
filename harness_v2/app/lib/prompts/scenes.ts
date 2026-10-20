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

import { betaSystem } from "./scenes-beta";
import { part, render, type Part } from "./parts";
import { V1_FREE_DRAWINGS_HEAD, V1_LECTURE, V1_MANIM_PLAN, V1_MANIM_RULES } from "./v1-lecture";

const ROLE = [
  "You design the visuals of ONE narrated lecture video, beat by beat, as the beat script that a compiler turns into",
  "Manim for a phone renderer. The NARRATION IS FIXED: it is the lecture's transcript, already cut into chapters and",
  "beats, and each beat's sentences (its \"say\") are said exactly as given. Your work is everything else the beat",
  "script holds: each beat's operations (\"do\"), where a paragraph starts and where a line needs a pause, and the",
  "lecture's map region and emblem. The script's note of what is on screen (\"on screen:\") is its writer's plan for",
  "the beat, and a figure named on a beat is shown on it. Everything below is how the beat script is written.",
].join("\n");

/** What v2's engine adds to v1's timeline (pocket_lecture.big_timeline, timeline_dates.py). */
const PICTURE_FLOW = [
  "A FLOW DRAWN AS ONE PICTURE (v2): a diagram of kind \"flow\" or \"cycle\" with 2 to 6 nodes may take",
  "  \"drawn\": \"picture\": the image model draws the whole flow as ONE rich picture (each step its own picture, an arrow",
  "  between each pair), and that picture itself is revealed as the narration speaks of it: each step (the arrow into it",
  "  first) is drawn on where it is in the picture as its label is said, until the whole picture stands. Give each node",
  "  an \"entity\" (what its picture shows, and how it is drawn: \"a sheaf of golden wheat, a warm watercolour\") and a",
  "  short \"label\", and the diagram an \"about\" (\"how bread is made\"). Use it for a process of concrete things one",
  "  can see (wheat -> mill -> flour -> bread, the water cycle), not for ideas, branches or a flowchart. reveal and",
  "  focus work on it as on any diagram.",
  '  {"op": "diagram", "id": "bread", "kind": "flow", "drawn": "picture", "about": "how bread is made",',
  '   "nodes": [{"id": "wheat", "label": "Wheat", "entity": "a sheaf of golden wheat"}, {"id": "mill", "label": "Mill",',
  '   "entity": "a stone windmill"}, {"id": "bread", "label": "Bread", "entity": "a round loaf"}], "edges": [["wheat", "mill", "harvested"], ["mill", "bread"]]}',
];

const PICTURE_STYLE = [
  "PICTURES: THEIR STYLE IS YOURS (v2; this overrides what the instructions above say of pictures \"in the lecture's",
  "style\"). Every picture the image model makes -- an illustration, a scene, a drawing to label, a picture on a",
  "diagram's node, a timeline's event or a marker, a flow drawn as one picture -- is drawn from your words alone.",
  "Describe each one whole: what it shows and how it is seen, AND how it is drawn -- the medium and art style (a",
  "watercolour, an engraving, a flat vector illustration, a realistic painting, a photograph-like image), its colours",
  "and its mood -- as best suits the subject and that moment of the lesson. Nothing is added to your words but its",
  "form (a cutout on white, or a whole scene) and no text. Keep pictures that belong together alike (the same",
  "person drawn the same way each time). The board's look (below) is for the board, its diagrams and its words: do",
  "not copy its name or its colour codes into a picture's description.",
];

const TIMELINE_ADDITIONS = [
  "TIMELINES, what this engine adds to the timeline op above:",
  "  - IN PROPORTION: when every date reads as a year, each event sits at its date along the track, with a scale of",
  "    round years under it, so the gaps between events are the real gaps. Dates may be \"1526\", \"500 BC\", \"320 BCE\",",
  "    \"AD 78\", \"c. 1500\", \"1920s\", \"16th century\", \"early 18th century\", \"3rd millennium BC\", \"15 August 1947\",",
  "    \"10,000 years ago\". Events close together are spread apart along their side, each with a slanted stem to its date.",
  '  - "range": ["1500", "1900"]: the years the timeline covers (to zoom in on a period); events outside it are left out.',
  '  - "spans": [["1526", "1857", "Mughal Empire"], ["1556", "1605", "Akbar"]]: periods shaded along the track and named',
  "    in a strip under the scale (reigns, eras, wars, dynasties), up to 6; overlapping ones are stacked.",
  '  - "scale": "even": events evenly spaced, for steps with no real dates ("Stone Age", "Bronze Age"); a timeline whose',
  "    dates are not all years is spaced evenly by itself.",
  "  - Up to 10 events.",
  '  {"op":"timeline","title":"The Mughals","range":["1500","1870"],"events":[["1526","Panipat"],["1556","Akbar"],',
  '   ["1857","The revolt"]],"spans":[["1526","1857","Mughal Empire"]]}',
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
  "Chapter titles and their title cards are the script's. Every chapter is drawn on the board. The map is not a chapter's: it",
  "comes in on a beat that points at it (a map operation) and stays through the beats after it until one puts up a",
  "picture of its own (a photo, a diagram, a manim figure), when it goes; map operations need the lecture's region.",
].join("\n");

export const SCENES_TOOL = {
  type: "function" as const,
  function: {
    name: "write_scenes",
    description: "Save the beat script's visual parts: each beat's operations (and paragraph, pause, about), by the beat's number; the lecture's map region when a beat points at the map, and its emblem.",
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
              beat: { type: "integer", description: "The beat's number, as given." },
              do: { type: "array", items: { type: "object", additionalProperties: true }, description: "Its operations." },
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

/** How busy the visuals are: operations a beat (left out or 0: no limit, the default; v1 said four), and whether they
 * change a paragraph at a time (v1) or on every beat. */
export type ScenePace = { maxOps?: number; change?: "paragraph" | "beat" };

const opsWords = (p?: ScenePace) => (!p?.maxOps ? "as many operations as its line needs" : `0-${p.maxOps} operations`);

/**
 * v1's section on a beat, with its limit on operations as this run has it: none (the default: "at most four
 * operations" is taken out) or the number chosen. The rest of v1's words are as they are.
 */
function beatSection(p?: ScenePace): string[] {
  const limit = p?.maxOps ? `, at most ${p.maxOps === 1 ? "one operation" : `${p.maxOps} operations`}.` : ".";
  return V1_LECTURE.beat.map((line) => line.replace(", at most four operations.", limit));
}

/**
 * The pace chosen for this run, when it is not v1's: told after v1's instructions, and said to override them where
 * they differ ("a paragraph at a time"). The limit on operations is in v1's own beat section (beatSection); with no
 * limit, a line says so here too.
 */
function pacePart(p?: ScenePace): Part | undefined {
  const free = !p?.maxOps;
  const beat = p?.change === "beat";
  if (!free && !beat) return undefined;
  return part("pace", "This run's pace (overrides v1's where they differ)", "rules", [
    "THIS RUN'S PACE, overriding what the instructions above say where they differ:",
    ...(free ? ["  - OPERATIONS: no limit to the operations on a beat: give a beat as many as its line needs, each built on its words."] : []),
    ...(beat ? [
      "  - THE VISUALS MOVE ON EVERY BEAT, not a paragraph at a time: every beat brings something new on screen -- a new",
      "    picture, the next part of a diagram, a focus or a zoom, a label, a marker, a step of working -- so the screen",
      "    never stands still for a whole line. A paragraph may still share one picture, built and pointed at beat by",
      "    beat; an empty \"do\" is for a beat whose line truly needs nothing new.",
    ] : []),
  ]);
}

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
  /** How many operations a beat, how often the visuals change: v1's (4, a paragraph at a time) unless set. */
  pace?: ScenePace;
  /** Built on the motion engine (beta): its templates and moments are told after v1's instructions. */
  motion?: { look?: string; timeline?: string };
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
  if (x.motion) {
    // The motion engine (beta): the elements, how to use them and examples, and nothing that limits how (no subject
    // tuning, no pace, no rules for choosing a visual): prompts/scenes-beta.ts.
    return {
      system: betaSystem({ manimAgent: x.manimAgent, off, labels: x.labels, look: x.motion.look }),
      user: [
        part("look", "The look", "context", `The board is drawn in ${x.look}. The pictures the image model makes are drawn in the style you describe for each.`),
        part("lecture", "The lecture and its chapters", "plan", [`Lecture ${x.lecture.n}: ${x.lecture.title}`,
          ...x.chapters.map((c) => `Chapter ${c.n}: ${c.title} - title card: "${c.narration}"`),
          ...(x.region ? [`Map region (already chosen): ${JSON.stringify(x.region)}`] : [])]),
        part("figures", `The lecture's figures (${x.figures.length})`, "items", x.figures.length
          ? x.figures.map((f) => `${f.id}: ${f.way}${f.ready ? "" : " (not made yet)"} - ${f.caption || "(no caption)"}`) : "None."),
        part("script", `The beats (${x.beats.length})`, "book", x.beats.map(beatLine)),
        ...(x.note ? [part("note", "Your note for this", "context", x.note)] : []),
        ...(x.ask.what === "fix" ? [part("retry", "What the compiler refused", "retry",
          "The compiler could not draw these beats (COMPILER lines above). Write them again so they can be drawn.")] : []),
        part("ask", "Request", "ask", `Write the visuals (write_scenes) of ${target}: each beat by its number, with its do.`),
      ],
    };
  }
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
      part("v1-beat", x.pace?.maxOps ? `A beat (at most ${x.pace.maxOps} operations)` : "A beat (no limit to its operations)", "rules", beatSection(x.pace)),
      part("shape", "The answer's shape (v2)", "rules", SHAPE),
      v1("ops", "Operations, little text, choosing the visual"),
      v1("stage", "The stage: diagrams, pictures, side by side, other operations"),
      part("v2-picture-style", "Pictures: their style is yours (v2)", "rules", PICTURE_STYLE),
      part("v2-timeline", "Timelines (v2's additions)", "rules", TIMELINE_ADDITIONS),
      ...(x.kinds.includes("diagram") && x.kinds.includes("drawing") ? [part("v2-picture-flow", "A flow drawn as one picture (v2)", "rules", PICTURE_FLOW)] : []),
      part("v1-free", "Free-form drawings, worked solutions and problems", "rules", V1_FREE_DRAWINGS_HEAD),
      v1("concept", "Concept maps and chains"),
      v1("camera", "Camera"),
      part("v1-manim", x.manimAgent ? "Free-form Manim (planned; the Manim agent writes it)" : "Free-form Manim (written here)", "rules",
        x.manimAgent ? V1_MANIM_PLAN : V1_MANIM_RULES),
      v1("detailed", "Detailed diagrams"),
      v1("map", "Map operations"),
      ...(pacePart(x.pace) ? [pacePart(x.pace)!] : []),
      ...(off.length ? [part("off", `Switched off here (${off.length})`, "choices", [
        "SWITCHED OFF FOR THIS LECTURE: never use these kinds of visual; anything of them is taken out:",
        ...off.map((k) => `  - ${x.labels[k] ?? k}`)])] : []),
    ],
    user: [
      part("look", "The look", "context", `The board is drawn in ${x.look}: its diagrams, cards, words and drawn shapes. Do not choose colours outside it for them. The pictures the image model makes are drawn in the style you describe for each.`),
      part("lecture", "The lecture and its chapters", "plan", [`Lecture ${x.lecture.n}: ${x.lecture.title}`,
        ...x.chapters.map((c) => `Chapter ${c.n}: ${c.title} (${c.map ? "on the board, the map in for its beats on places" : "on the board"}) - title card: "${c.narration}"`),
        ...(x.region ? [`Map region (already chosen): ${JSON.stringify(x.region)}`] : [])]),
      part("figures", `The lecture's figures (${x.figures.length})`, "items", x.figures.length
        ? x.figures.map((f) => `${f.id}: ${f.way}${f.ready ? "" : " (not made yet)"} - ${f.caption || "(no caption)"}`) : "None."),
      part("script", `The beats (${x.beats.length})`, "book", x.beats.map(beatLine)),
      ...(x.note ? [part("note", "Your note for this", "context", x.note)] : []),
      ...(x.ask.what === "fix" ? [part("retry", "What the compiler refused", "retry",
        "The compiler refused these beats (COMPILER lines above). Write them again so they compile: keep what is right, change what it names.")] : []),
      part("ask", "Request", "ask", `Write the visuals (write_scenes) of ${target}. Give each beat its number and its do (${opsWords(x.pace)}), and ` +
        `"paragraph": true on the first beat of each paragraph.`),
    ],
  };
}

/** The role when the instructions are given to any chat model by hand (the Voice tab's editor). */
const HAND_ROLE = [
  "You design the visuals of ONE chapter of a narrated lecture video, beat by beat, as the beat script that a compiler",
  "turns into Manim for a phone renderer. You are given the chapter's beat script as JSON (below the instructions)",
  "and what to change; you return the whole chapter's beat script, changed. Each beat's sentences (\"say\") are the",
  "lecture's transcript: keep them as they are unless you are asked to change the words. Everything below is how the",
  "beat script is written.",
].join("\n");

/** How the answer is given when the instructions are used by hand: the whole chapter, in the editor's shape. */
const HAND_SHAPE = [
  "THE ANSWER: the whole chapter's beat script as ONE JSON object, in exactly this shape, and nothing else (no words",
  "before or after it):",
  '{"style": "<the look, as given>", "art": "<as given>",',
  ' "region": {"country": "India", "view": "ind"} | {"state": "Rajasthan", "country": "India"} |',
  '   {"area": "World" | a continent ("Asia", "Europe", "Africa") | a world region ("South Asia", "Middle East",',
  '   "Western Europe", "Southern Africa", "Indian subcontinent")} | null,  (an area\'s "state" op fills a country)',
  ' "emblem": "<one simple object that stands for the whole topic>" | null, "genre": "<as given>",',
  ' "chapter": {"title", "narration": "Chapter one. ...",',
  '   "beats": [{"beat": <its number, as given>, "say": "...", "paragraph"?: true, "pause"?: 2, "about"?: "<English name>",',
  '              "do": [ops]}]}}',
  "Keep every beat's \"beat\" number as given (a beat you add has none). Map operations need a region; the chapter",
  'is on the board and the map comes in for the beats that point at it. Free-form Manim is written as code ("code"), never as a plan: nothing writes it after you.',
].join("\n");

/**
 * The scene writer's instructions as one text to give any chat model by hand, with a chapter's beat script, to have
 * it change the chapter (the Voice tab's editor): v1's instructions as the scene writer gets them, its subject and
 * the kinds switched off, with the role and the answer's shape for a whole chapter, and Manim written as code.
 */
export function handInstructions(x: { look: string; kinds: string[]; labels: Record<string, string>; subject?: SceneSubject; pace?: ScenePace;
  motion?: { look?: string; timeline?: string } }): string {
  const system = scenesPrompt({ lecture: { n: 0, title: "" }, look: x.look, kinds: x.kinds, labels: x.labels, chapters: [], beats: [],
    figures: [], ask: { what: "lecture" }, manimAgent: false, subject: x.subject, pace: x.pace, motion: x.motion }).system
    .map((p) => (p.key === "role" ? { ...p, text: HAND_ROLE } : p.key === "shape" ? { ...p, text: HAND_SHAPE } : p));
  return [render(system), "", `THE LOOK: the board is drawn in ${x.look}: its diagrams, cards, words and drawn shapes. Do not choose colours outside it for them. The pictures the image model makes are drawn in the style you describe for each.`].join("\n");
}
