/**
 * The scenes: what is on screen on each beat of a lecture's script, as the engine's operations (harness_v2/engine,
 * compile_lecture.py). The narration is fixed (the transcript's sentences, as the script grouped them into beats):
 * the model writes only each beat's "do", the visuals.
 *
 * The wording of every kind is v1's (harness/app/lib/lecture.ts lecturePrompt), cut into one part per kind, and only
 * the kinds switched on are told (lib/visual-kinds.ts): a kind not described is never used. Asked for the whole
 * lecture, for one chapter, or for one beat (the rest of its chapter given as it is, for context).
 */

import { part, type Part } from "./parts";

const ROLE = "You design the visuals of ONE narrated lecture video, beat by beat, as operations a compiler turns into a Manim " +
  "scene. The narration is fixed: each beat's sentences are said exactly as given. You write only what is on screen while " +
  "they are said (each beat's \"do\"): pictures, diagrams, maps and a few words, chosen and paced for the learning.";

const BEATS = [
  "A BEAT is its sentences (fixed) and its operations, \"do\": at most four, often one or none (a beat that builds on the",
  "last visual, or leaves it up, needs nothing new). Plan a PARAGRAPH at a time (3-5 beats on one idea): its first beat",
  "puts up the visual, the next ones build on it (reveal the next part, focus on a node, add a marker) or leave it up. A",
  "picture stays until the next one. EVERY CHAPTER OPENS WITH A VISUAL on its first beat: the board is empty until one is",
  "put up. The script's note of what is on screen (\"on screen:\") is the plan to follow; the figure named on a beat is",
  "shown on it.",
  "",
  "LITTLE TEXT ON SCREEN. A chapter without a map is taught on a BOARD: the whole frame is the picture, and the words on",
  "screen are only the topic heading and one key point over it. With a map, the map takes the left and a side panel",
  "holds at most 3 short points under its title. The narration carries the explanation; the screen shows pictures,",
  "diagrams, graphs and working, not paragraphs. Every number shown must be in the sentences or well established.",
  "",
  "PICTURES FOLLOW THE VOICE: a label, a node, a gallery item or a place comes on as its name is SAID, so name things",
  "on screen in the words the sentences use (they cannot be changed). Only teaching content is shown: never the book's",
  "furniture (QR codes, logos, page headers).",
  "",
  "Always there (the board's words):",
  '  {"op":"panel","title","sub"?}          the topic heading; start each topic with one',
  '  {"op":"fact","text","color"?}          ONE key point, a few words (under 60 characters); it replaces the last',
  '  {"op":"clear"}                         clear the heading and key point',
  "Colours are palette names (SAND RIVER GOLD ROSE TEAL GREEN VIOLET MUTED CREAM HI) or #RRGGBB; leave them out to use",
  "the style's own.",
].join("\n");

/** Each visual kind as v1's prompt describes it. */
const KIND_TEXT: Record<string, string[]> = {
  map: [
    "THE MAP (only in a chapter marked map; the region is the lecture's, below). WHERE something is: a place, a route, a",
    "spread across a region. It is drawn from Natural Earth's data, true to the coastline; never put a map, an outline,",
    "borders or a route in any other kind of picture. ALWAYS NAME PLACES (in English); never guess coordinates: the",
    "compiler looks names up. Give lonlat only for a spot with no name (a point at sea).",
    '  {"op":"marker","place":"Jaipur" | "lonlat":[lon,lat],"label"?,"color"?,"side"?:"left|right|up|down","picture"?}   a POINT:',
    "     a town, a battlefield, a temple, a port. picture: what is there, above the label (if pictures are on).",
    '  {"op":"river","name":"Ganges","color"?}   a Natural Earth river by its English name',
    '  {"op":"state","name":"Normandy","label"?,"color"?,"opacity"?}   SHADE AN AREA: a state, a country, a region, a',
    "     continent. A country or region is the land it covers, never a dot. A different colour for each area compared.",
    '  {"op":"arrow","points":["Delhi","Agra"],"color"?,"label"?}  a curved arrow: winds, migrations, routes; label: what moves',
    '  {"op":"empire","name":"Mughal Empire","year":1600,"label"?,"color"?}  a state as it stood in that year (2000 BC to 2010)',
    '  {"op":"relief","names"?:["Himalayas"],"label"?:false}  the mountains and plateaus in view, shaded and named',
    '  {"op":"path","points":["Haridwar","Prayagraj"],"color"?}  a hand-drawn line: a ridge, a canal',
    '  {"op":"journey","stops":["Ahmedabad","Surat",[72.8,20.89]],"labels"?,"color"?}  a traveller moving stop to stop',
    '  {"op":"graticule","lat":23.44 | "lon":82.5,"label"?}     {"op":"dim","opacity"?}  fade filled areas before highlighting one',
    "  A map shows only the last few places named: name a place when it matters, not every place at once.",
  ],
  figure: [
    "THE BOOK'S OWN FIGURES come first whenever one shows what the beat explains (the ones listed below, by id; the beat",
    'the script put one on shows it there): {"op":"picture","figure":"<id>","caption"?}. One figure a beat.',
  ],
  illustration: [
    "AI ILLUSTRATIONS, made by the image model in the lecture's style: a real PERSON, PLACE, LIVING THING OR OBJECT the",
    'class should see: {"op":"picture","generate":"<what it shows, in English, and how it is seen>","caption"?,"labels"?}',
    '  ("a steam locomotive, side view"). A CUTOUT with no background, like a sticker. No words in it; to name its parts give',
    '  "labels" (2-6 short names of parts really in it) and SAY each in the sentences. A SETTING, AN EVENT, A WAY OF LIFE ->',
    '  a whole scene: "scene": true (drawn edge to edge). A paragraph about several things -> ONE scene with all of them,',
    '  labelled. "move"?: "bob" | "sway" | "breathe" | "drift", only where moving is what the thing does. "points"?: ["2-4',
    '  short lines"] -> the picture large on the left, what to take away from it on the right (not with labels).',
    '  ONE PICTURE PER THING: the same person or thing asked for again in the very same "generate" words.',
    "  PICTURES BESIDE WORDS: a diagram's node, a timeline's event and a map marker may carry a picture,",
    '  "picture": {"generate":"Mahatma Gandhi, an illustrated portrait"}, where seeing the thing teaches it.',
  ],
  drawing: [
    "AI DETAILED DIAGRAMS, made by the image model that draws exact textbook diagrams: a real, complex STRUCTURE -- an",
    "organ, a cell and its organelles, a flower in section, a skeleton, lab apparatus, a machine's insides, a landform in",
    'section: {"op":"picture","draw":"<everything on it, in English, precisely: each part, each arrow>","labels":[up to 6',
    '  parts to name],"caption"?}. It is shown whole (no reveal of its parts); the board writes each label with a line to',
    "  its part as it is said. Never a graph or anything with exact values (those are built).",
  ],
  gallery: [
    "A GALLERY: several pictures of one kind of thing (kinds of rock, the wonders of the world, the people of a movement):",
    '  {"op":"picture","title"?,"layout"?:"spotlight"|"grid","items":[{<a picture: generate | draw | figure>,"caption":"...",',
    '  "say"?:"..."},...]} (2-6 items). Each slides in as its caption (or "say" words) is SAID, so name them in that order.',
  ],
  diagram: [
    "A DIAGRAM: boxes joined by arrows, built a node or two at a time across the paragraph's beats, as they are named:",
    '  {"op":"diagram","id":"chain","kind":"flow"|"cycle"|"hub"|"pyramid","steps"?:true,"title"?,',
    '   "nodes":[{"id":"sun","label":"Sun","items"?:["up to 5"],"kind"?:"person|place|event|idea","shape"?,"lane"?,"picture"?}],',
    '   "edges"?:[["sun","plants","light","gives|owes|power"]],"show"?:["sun"]}',
    "  flow takes its layout from its edges: a chain = in order; edges that only branch downwards = a hierarchy (drawn as a",
    '  textbook tree); branches, joins, loops, shapes ("start","end","process","decision","io","store","note") or lanes =',
    "  a flowchart. cycle = round; hub = the first node in the middle (a concept map); pyramid = ranks, top first, each with",
    "  items. 2-9 nodes (a flow up to 16, a hierarchy up to 20). Labels short; an edge's label says how they connect.",
    '  {"op":"reveal","diagram":"chain","nodes":["deer"]}   the next nodes, with their arrows',
    '  {"op":"focus","diagram":"chain","node":"plants"}     a ring round one node while it is talked about',
    '  {"op":"zoom","diagram":"chain","node":"x","scale"?:2}   move in on one part; {"op":"zoom","diagram":"chain"} back out',
  ],
  timeline: [
    'A TIMELINE: WHEN, several dated events: {"op":"timeline","events":[["1526","Panipat"],["1556","Akbar"]],"title"?}; an',
    '  event may carry a picture as a third item (PICTURES BESIDE WORDS, if pictures are on).',
  ],
  manim: [
    'FREE-FORM MANIM: a figure you design yourself, in any subject, whenever it teaches better than the other kinds',
    "(a graph, a free-body diagram, a ray diagram, a circuit, a wave, a Venn diagram, a Punnett square; a population",
    "pyramid changing, a supply and demand shift, a river's long profile, tribute flowing up the feudal ranks):",
    '  {"op":"manim","id":"f1","code":"...","area"?:"left"}   the ONLY op on its beat. code is the body of construct() for',
    "  this beat: build objects and self.play(...) them, about as long as the sentence. Beats with the same id share",
    "  their variables, in order: build the figure on one beat, point at its parts on the next (Indicate, GrowArrow,",
    "  TransformFromCopy, .animate). Rules: everything Manim exports and np; no imports, classes, while loops,",
    "  self.camera or self.clear: only self.play, self.wait, self.add, self.remove. The board is x -6.9..6.9, y",
    "  -3.05..2.85. Colours: INK, MUTED_INK, PALETTE[\"ROSE\"] (forces), PALETTE[\"GREEN\"], PALETTE[\"GOLD\"],",
    "  PALETTE[\"RIVER\"], PALETTE[\"TEAL\"], PALETTE[\"VIOLET\"]. Text font_size 24-32, MathTex for symbols, labels next_to",
    "  their part (buff 0.15-0.3), never on a line. True geometry, values and units. Never a map. FadeOut what the next",
    '  step no longer needs. area "left": the figure in the left half, a working ({"op":"work"}) beside it.',
  ],
  equation: ['{"op":"equation","tex":"6CO_2 + 6H_2O -> C_6H_{12}O_6 + 6O_2","label"?}   a law or a reaction, large'],
  molecule: [
    '{"op":"molecule","name":"glucose" | "H2O" | SMILES,"label"?}   a structural formula; ONLY where the sentences explain',
    "  that structure, once a chapter.",
  ],
  define: ['A HARD WORD -> {"op":"define","term":"Biodiversity","meaning":"<plain words>"}'],
  compare: ['TWO OR THREE KINDS OF SOMETHING -> {"op":"compare","title"?,"columns":[{"title":"Reserved","points":["up to 4 short lines"]},...]}'],
  question: [
    'A QUESTION FOR THE CLASS (only where the sentences ask one): {"op":"question","text":"...","choices"?:["A","B","C"],',
    '  "answer":"A" | "<the answer in words>","think"?:5}, then {"op":"answer"} on the beat that gives the answer.',
    '  {"op":"option","choice":"B"} marks one choice while it is talked about.',
  ],
  numbers: [
    '{"op":"stat","value":"2,525 km","label":"Ganga: longest river","color"?}   a key number with a label',
    '{"op":"bars","items":[["label",n],...],"unit"?,"color"?}   a bar chart, at most 8 bars',
  ],
  work: [
    'A WORKED SOLUTION: {"op":"work","id":"w","title"?,"lines":["N = mg\\\\cos\\\\theta"],"box"?:true}: the same id adds',
    "  lines under the last, one or two a beat, as they are said; TeX, or a sentence; box rings the answer. Beside a",
    '  picture on the stage. A LONG QUESTION: {"op":"problem","id":"p1","title":"Problem 1","text":"...","given":[...],',
    '  "find":"a","think"?:5}, solved by work ops with its id.',
  ],
  words: [
    '{"op":"quote","text":"...","who":"Akbar"}   a primary source, in its own words',
    '{"op":"process","steps":["Evaporation","Condensation","Rain"],"cycle"?:true,"title"?}   steps in boxes (rarely)',
  ],
};

export const SCENES_TOOL = {
  type: "function" as const,
  function: {
    name: "write_scenes",
    description: "Save the visuals: each beat's operations, by the beat's number; and the lecture's map region when a chapter is on a map.",
    parameters: {
      type: "object",
      properties: {
        region: {
          description: 'The map region, when a chapter is on a map: {"country":"India"} | {"state":"Rajasthan","country":"India"} | {"area":"World" | a continent | a world region}; null for none.',
          anyOf: [{ type: "object", properties: { country: { type: "string" }, state: { type: "string" }, area: { type: "string" } } }, { type: "null" }],
        },
        beats: {
          type: "array",
          items: {
            type: "object",
            properties: {
              beat: { type: "integer", description: "The beat's number, as given." },
              do: { type: "array", items: { type: "object", additionalProperties: true }, description: "Its operations (0-4)." },
            },
            required: ["beat", "do"],
          },
        },
      },
      required: ["beats"],
    },
  },
};

export type SceneBeatInput = {
  n: number;
  chapter: number;
  text: string;
  show: string;
  figure?: { id: string; way: string; caption: string; ready: boolean };
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
}): { system: Part[]; user: Part[] } {
  const on = x.kinds.filter((k) => KIND_TEXT[k]);
  const writing = (b: SceneBeatInput) => x.ask.what === "lecture" || (x.ask.what === "chapter" && b.chapter === x.ask.chapter)
    || (x.ask.what === "beat" && b.n === x.ask.beat) || (x.ask.what === "fix" && x.ask.beats.includes(b.n));
  const beatLine = (b: SceneBeatInput) => [
    `#${b.n} [ch ${b.chapter}] "${b.text}"`,
    `   on screen: ${b.show || "-"}`,
    ...(b.figure ? [`   figure: ${b.figure.id} (${b.figure.way}${b.figure.ready ? "" : ", not made yet: the book's picture is shown"}) - ${b.figure.caption || "(no caption)"}`] : []),
    ...(b.kinds ? [`   this beat may use only: ${b.kinds.map((k) => x.labels[k] ?? k).join(", ") || "the heading and key point"}`] : []),
    ...(!writing(b) && b.ops ? [`   do (as it is, not to be written): ${JSON.stringify(b.ops)}`] : []),
    ...(writing(b) && b.ops?.length && x.ask.what !== "lecture" ? [`   do now (to be written again): ${JSON.stringify(b.ops)}`] : []),
    ...(x.problems?.[b.n]?.length ? x.problems[b.n].map((p) => `   COMPILER: ${p}`) : []),
  ].join("\n");
  const target = x.ask.what === "lecture" ? `every beat, 1 to ${x.beats.at(-1)?.n ?? 0}`
    : x.ask.what === "chapter" ? `the beats of chapter ${x.ask.chapter} only (${x.beats.filter(writing).map((b) => `#${b.n}`).join(", ")})`
      : x.ask.what === "beat" ? `beat #${x.ask.beat} only (the beats around it are given as they are, so it follows on from them)`
        : `beats ${x.ask.beats.map((n) => `#${n}`).join(", ")} only, mending what the compiler says of each`;
  return {
    system: [
      part("role", "Role", "rules", ROLE),
      part("beats", "Beats, paragraphs and the board", "rules", BEATS),
      part("kinds", `The visuals you may use (${on.length})`, "choices", on.length
        ? [`Only these kinds; anything else is taken out:`, "", ...on.flatMap((k) => [...KIND_TEXT[k], ""])]
        : "No visuals are switched on: only the heading and key point (panel, fact, clear)."),
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
      part("ask", "Request", "ask", `Write the visuals (write_scenes) of ${target}. Give each beat its number and its do (0-4 operations).`),
    ],
  };
}
