/**
 * The current engine's primitives, one entry each: what it is for, its fields (the Lab's form editor builds an
 * operation from them), its parts (what can come on by itself on a word), what the choreography may do with it
 * (lib/director.ts), and an example that compiles (engine/BEAT_SCRIPT.md has the full reference; `npm run check`
 * compiles every example). Read by the director's catalog (prompts/director.ts), the choreography's manuals
 * (lib/manuals.ts) and the Lab (components/lab-panel.tsx).
 */

export type FieldKind = "text" | "long" | "number" | "bool" | "select" | "texts" | "json";
export type Field = { key: string; kind: FieldKind; required?: boolean; options?: string[]; hint?: string };
export type Primitive = {
  op: string;
  group: "board" | "pictures" | "diagrams" | "cards" | "templates" | "questions" | "working" | "map" | "pointing" | "free";
  /** One line: what it shows and when to use it. */
  what: string;
  fields: Field[];
  /** Its parts, each able to come on with its own word (or none). */
  parts?: string;
  /** What the choreography can do with it, beyond bringing it on. */
  moves: string[];
  say: string;
  example: Record<string, unknown>;
};

/** Every op's shared choices (engine/BEAT_SCRIPT.md §3: `enter`, `speed`; §5.3 `point`'s `how`). */
export const ENTRANCES = ["fade", "rise", "pop", "drop", "slide", "zoom", "flip", "draw", "type", "unfold", "iris"] as const;
export const SPEEDS = ["fast", "base", "slow"] as const;
export const POINT_HOWS = ["pulse", "lift", "circle", "underline"] as const;

const COLOR: Field = { key: "color", kind: "select", options: ["", "GOLD", "ROSE", "RIVER", "GREEN", "TEAL", "TERRA", "VIOLET", "SAND", "MUTED"],
  hint: "a palette name (or #RRGGBB); left out, the look's own" };

export const PRIMITIVES: Primitive[] = [
  // ---------------- the board's words ----------------
  { op: "panel", group: "board", what: "The topic heading at the top of the board: start each topic with one.",
    fields: [{ key: "title", kind: "text", required: true }, { key: "sub", kind: "text", hint: "a line under it" }],
    moves: ["comes on as the line begins or on the word that names the topic", "stays until the next panel replaces it"],
    say: "Rivers shaped where people lived.", example: { op: "panel", title: "Rivers and settlement" } },
  { op: "stat", group: "board", what: "One key number, large, with what it is: a figure the narration wants remembered.",
    fields: [{ key: "value", kind: "text", required: true, hint: "\"2,525 km\"" }, { key: "label", kind: "text", required: true }, COLOR],
    moves: ["comes on as the number is said", "pulse: it pulses once (point)"],
    say: "The Ganga runs for 2,525 kilometres.", example: { op: "stat", value: "2,525 km", label: "Ganga: longest river", color: "RIVER" } },
  { op: "bars", group: "board", what: "A small bar chart of up to 8 values: a comparison of amounts.",
    fields: [{ key: "items", kind: "json", required: true, hint: "[[\"Ganga\", 2525], [\"Godavari\", 1465]]" }, { key: "unit", kind: "text" }, COLOR],
    parts: "each bar, by its label", moves: ["comes on when the comparison begins", "pulse on a bar's label: it pulses as that one is named"],
    say: "The Ganga is far longer than the Godavari.", example: { op: "bars", items: [["Ganga", 2525], ["Godavari", 1465]], unit: "km" } },
  // ---------------- pictures ----------------
  { op: "picture", group: "pictures", what: "A picture on the stage: a real thing made by the illustration model (generate), a labelled textbook drawing (draw), one of the book's figures (figure) or a gallery (items). Labels name its parts on the picture.",
    fields: [{ key: "generate", kind: "long", hint: "a real person, place or thing, and how it is drawn" }, { key: "draw", kind: "long", hint: "or: a detailed labelled textbook diagram" },
      { key: "figure", kind: "text", hint: "or: a book figure's id" }, { key: "labels", kind: "texts", hint: "its parts, named on it" },
      { key: "caption", kind: "text" }, { key: "move", kind: "select", options: ["", "bob", "sway", "breathe", "drift"], hint: "the picture keeps moving gently" },
      { key: "hold", kind: "texts", hint: "labels held back, each brought on later by a label op" },
      { key: "notes", kind: "json", hint: "{\"water\": \"the flood\"}: a short line under a label's name" }],
    parts: "each label (a part of the picture, boxed and named on it)",
    moves: ["comes on with the word that brings in what it shows; each label shown on the word that names its part, in its line or a later line of its scenes (held back, then a label op)",
      "a short note under a label's name",
      "light: the rest of the picture darkened round one labelled part while it is explained (until the next line; with until, held to that word)",
      "pulse on a label: it pulses once (point)", "hide: a label taken off (unlabel), the picture stays",
      "exit: taken off when its idea is done and nothing new replaces it"],
    say: "When the water goes back, it leaves rich soil behind.",
    example: { op: "picture", generate: "a river bank after a flood, dark wet silt, early fields, warm painted illustration", labels: ["water", "soil"] } },
  // ---------------- diagrams ----------------
  { op: "diagram", group: "diagrams", what: "Boxes joined by arrows, built as the narration names its parts: a chain of causes, a cycle, a hub of ideas, a hierarchy, a pyramid. The richest primitive to build over a scene.",
    fields: [{ key: "id", kind: "text", required: true }, { key: "kind", kind: "select", options: ["flow", "cycle", "hub", "pyramid"] }, { key: "title", kind: "text" },
      { key: "nodes", kind: "json", required: true, hint: "[{\"id\": \"fields\", \"label\": \"Fields\"}, ...] (2-9; picture?, items?, kind?, shape?)" },
      { key: "edges", kind: "json", hint: "[[\"fields\", \"granary\", \"grain\"], ...]" }, { key: "steps", kind: "bool", hint: "numbered steps" }, { key: "flow", kind: "bool", hint: "dots run along the arrows" }],
    parts: "each node, by its id (with the arrows into it)",
    moves: ["comes on with its first node; every other node on the word that names it, in ANY line of its scene (the arrows into it with it)",
      "focus on a node: ringed, the rest of the diagram dimmed while it is explained (with until, lifted on that word: unfocus)", "pulse on a node: it pulses once (point)",
      "the best primitive for a scene of several lines: put it up, then build it node by node and focus the one being explained",
      "exit: taken off when its idea is done"],
    say: "The fields gave grain, and the grain went into the granary.",
    example: { op: "diagram", id: "chain", kind: "flow", title: "Where the grain went", nodes: [{ id: "fields", label: "Fields" }, { id: "granary", label: "Granary" }], edges: [["fields", "granary", "grain"]], show: ["fields"] } },
  { op: "timeline", group: "diagrams", what: "Dated events across the stage in proportion, with periods shaded: a sequence in history.",
    fields: [{ key: "title", kind: "text" },
      { key: "events", kind: "json", required: true, hint: "[[\"1526\", \"Panipat\"], ...] or [{\"date\": \"1526\", \"label\": \"Panipat\", \"on\": \"w4\"}, ...] (2-10)" },
      { key: "enter", kind: "select", options: ["", "draw", "travel", "whole"], hint: "draw (default): the track draws in, the events pop on one by one; travel: a marker runs to each; whole: all at once" },
      { key: "spans", kind: "json", hint: "[[\"1526\", \"1857\", \"Mughal Empire\"]]" }, { key: "range", kind: "json", hint: "[\"1500\", \"1870\"]" },
      { key: "scale", kind: "select", options: ["", "even"], hint: "even: events evenly spaced (steps with no real dates)" }],
    parts: "each event, by its label; each span by its name",
    moves: ["the track draws in as the period is introduced, then each event pops on (on its own word when it has one: {date, label, on})",
      "enter travel: a marker runs along the track to each event as it comes", "pulse on an event: it pulses as it is talked about again (the engine never pulses one by itself)",
      "exit: taken off when the story moves on"],
    say: "From the battle of Panipat to the revolt of 1857.", example: { op: "timeline", title: "The Mughals", events: [["1526", "Panipat"], ["1857", "The revolt"]] } },
  { op: "process", group: "diagrams", what: "Steps in boxes, in order (a diagram is usually better).",
    fields: [{ key: "steps", kind: "texts", required: true, hint: "2-8 steps" }, { key: "cycle", kind: "bool" }, { key: "title", kind: "text" }],
    parts: "each step", moves: ["each step on the word that names it, in its line", "pulse on a step: it pulses"],
    say: "Water evaporates, condenses and falls as rain.", example: { op: "process", steps: ["Evaporation", "Condensation", "Rain"], cycle: true } },
  // ---------------- templates (the motion engine's, drawn in this style: engine/templates.py) ----------------
  { op: "list", group: "templates", what: "Points that come in one at a time as they are said: reasons, features, steps of an argument.",
    fields: [{ key: "items", kind: "texts", required: true, hint: "up to 7 points (5 reads best), each 1-6 words" }, { key: "title", kind: "text" },
      { key: "mark", kind: "select", options: ["", "bullet", "number", "check"] }, { key: "layout", kind: "select", options: ["", "column", "grid", "pills", "steps"] }],
    parts: "each point", moves: ["the first point comes on with the list; each other on the word that names it", "hold a point for a later line (hold, then reveal with of)",
      "point at a point: pulse, lift, circle, underline"],
    say: "Japan changed for three reasons: a strong state, new schools and railways.",
    example: { op: "list", title: "Why so fast", mark: "number", items: ["A strong state", "New schools", "Railways"] } },
  // ---------------- cards ----------------
  { op: "define", group: "cards", what: "A hard word and its meaning on a card, beside the picture up (never in place of it).",
    fields: [{ key: "term", kind: "text", required: true }, { key: "meaning", kind: "text", required: true }],
    moves: ["comes on as the term is said (often at the end of its sentence: the line's last words)", "pulse: the term pulses (point)"],
    say: "That extra grain is called a surplus.", example: { op: "define", term: "Surplus", meaning: "more than a family needs to eat" } },
  { op: "compare", group: "cards", what: "Two or three kinds side by side, a few points each: a contrast.",
    fields: [{ key: "title", kind: "text" }, { key: "columns", kind: "json", required: true, hint: "[{\"title\": \"Himalayan\", \"points\": [\"Snow-fed\"]}, ...] (2-3)" }],
    parts: "each column, by its title; each point", moves: ["each column on the word that names its kind", "pulse on a column: it pulses as it is talked about", "exit"],
    say: "Himalayan rivers are snow-fed; peninsular rivers are rain-fed.",
    example: { op: "compare", columns: [{ title: "Himalayan", points: ["Snow-fed"] }, { title: "Peninsular", points: ["Rain-fed"] }] } },
  { op: "quote", group: "cards", what: "A primary source in its own words, with who said it.",
    fields: [{ key: "text", kind: "long", required: true }, { key: "who", kind: "text" }],
    moves: ["comes on as the quotation begins", "exit"], say: "Akbar wrote to his son.", example: { op: "quote", text: "Be just to all.", who: "Akbar" } },
  { op: "equation", group: "cards", what: "A law or a reaction, large, in TeX.",
    fields: [{ key: "tex", kind: "text", required: true }, { key: "label", kind: "text" }],
    moves: ["comes on as the law is named", "exit"], say: "Photosynthesis makes glucose from carbon dioxide and water.",
    example: { op: "equation", tex: "6CO_2 + 6H_2O \\to C_6H_{12}O_6 + 6O_2", label: "Photosynthesis" } },
  { op: "molecule", group: "cards", what: "A structural formula in CPK colours, only where the line explains the structure.",
    fields: [{ key: "name", kind: "text", required: true, hint: "a name, a formula or SMILES" }, { key: "label", kind: "text" }],
    moves: ["comes on as the structure is explained", "exit"], say: "Look at the ring of carbon atoms in glucose: its structure.", example: { op: "molecule", name: "glucose", label: "Glucose" } },
  // ---------------- questions ----------------
  { op: "question", group: "questions", what: "A question for the class, with choices and a timer: makes the viewer think.",
    fields: [{ key: "text", kind: "text", required: true }, { key: "choices", kind: "texts", hint: "2-5 short answers" }, { key: "answer", kind: "text", hint: "\"B\", 1-5, or its text" },
      { key: "think", kind: "number", hint: "seconds of silence (default 7)" }, { key: "title", kind: "text" }],
    parts: "each choice", moves: ["comes on as the question is asked", "each choice on its words", "the class thinks in the silence after"],
    say: "Which of these is a force?", example: { op: "question", text: "Which of these is a force?", choices: ["Kicking a ball", "Sleeping"], answer: "A" } },
  { op: "answer", group: "questions", what: "Shows the answer of the question up (a later beat).", fields: [],
    moves: ["on the word that gives the answer"], say: "The answer is kicking a ball.", example: { op: "answer" } },
  { op: "option", group: "questions", what: "Marks one choice right (ringed) or wrong (crossed) while it is talked about.",
    fields: [{ key: "choice", kind: "text", required: true }, { key: "right", kind: "bool" }],
    moves: ["on the word that judges the choice"], say: "Sleeping is not a force.", example: { op: "option", choice: "B", right: false } },
  // ---------------- working ----------------
  { op: "work", group: "working", what: "Working built line by line beside the figure: a derivation or a calculation.",
    fields: [{ key: "id", kind: "text", required: true }, { key: "title", kind: "text" }, { key: "lines", kind: "texts", required: true, hint: "TeX, one or two a beat" }, { key: "box", kind: "bool", hint: "rings the answer" }],
    parts: "each line", moves: ["each line as it is said; the same id on later beats adds lines under the last"],
    say: "The normal force is m g cos theta.", example: { op: "work", id: "w", title: "Along the slope", lines: ["N = mg\\cos\\theta"] } },
  { op: "problem", group: "working", what: "A long question across the top, its solution worked beside it (work with the same id).",
    fields: [{ key: "id", kind: "text", required: true }, { key: "title", kind: "text" }, { key: "text", kind: "long", required: true }, { key: "given", kind: "texts" }, { key: "find", kind: "text" }, { key: "think", kind: "number" }],
    moves: ["comes on as the problem is read", "the class tries it in the silence after (think)"],
    say: "Here is a problem: a block rests on an incline.", example: { op: "problem", id: "p1", title: "Problem 1", text: "A 5 kg block rests on a 30° incline. Find its acceleration.", given: ["m = 5 kg"], find: "a" } },
  // ---------------- the map ----------------
  { op: "marker", group: "map", what: "A point on the map: a town, a battlefield, a temple, with a label (and a picture).",
    fields: [{ key: "place", kind: "text", required: true }, { key: "label", kind: "text" }, { key: "side", kind: "select", options: ["", "left", "right", "up", "down"] }, COLOR],
    moves: ["comes on as the place is named", "pulse: the place is pointed at (point)"], say: "The city of Jaipur.", example: { op: "marker", place: "Jaipur", label: "Jaipur" } },
  { op: "state", group: "map", what: "An area shaded with its name: a state, a country, a region.",
    fields: [{ key: "name", kind: "text", required: true }, { key: "label", kind: "text" }, COLOR, { key: "opacity", kind: "number" }],
    moves: ["comes on as the area is named", "pulse: pointed at as it is named again"], say: "Rajasthan, in the west of India.", example: { op: "state", name: "Rajasthan", label: "Rajasthan" } },
  { op: "river", group: "map", what: "A river drawn on the map by its English name.", fields: [{ key: "name", kind: "text", required: true }, COLOR],
    moves: ["drawn as it is named"], say: "The Ganga flows east.", example: { op: "river", name: "Ganges" } },
  { op: "arrow", group: "map", what: "A curved arrow between places: a wind, a migration, a route; its label rides it.",
    fields: [{ key: "points", kind: "texts", required: true, hint: "places, in order" }, { key: "label", kind: "text" }, COLOR],
    moves: ["drawn as the movement is said"], say: "Trade ran from Delhi to Agra.", example: { op: "arrow", points: ["Delhi", "Agra"], label: "trade" } },
  { op: "path", group: "map", what: "A hand-drawn line on the land: a ridge, a canal.", fields: [{ key: "points", kind: "texts", required: true }, COLOR],
    moves: ["drawn as it is named"], say: "A canal joined the two cities.", example: { op: "path", points: ["Delhi", "Agra"] } },
  { op: "journey", group: "map", what: "A traveller moving stop to stop, each stop named as it is reached.",
    fields: [{ key: "stops", kind: "texts", required: true, hint: "2 or more places" }, { key: "labels", kind: "texts" }, COLOR],
    moves: ["the traveller sets out as the journey begins; each stop as it is named"], say: "He walked from Ahmedabad to Surat.", example: { op: "journey", stops: ["Ahmedabad", "Surat"] } },
  { op: "empire", group: "map", what: "A state as it stood in a year, with its historical border.",
    fields: [{ key: "name", kind: "text", required: true }, { key: "year", kind: "number", required: true }, { key: "label", kind: "text" }, COLOR],
    moves: ["filled as it is named"], say: "The Mughal Empire in 1600.", example: { op: "empire", name: "Mughal Empire", year: 1600, label: "Mughals, 1600" } },
  { op: "relief", group: "map", what: "Mountains and plateaus shaded and named.", fields: [{ key: "names", kind: "texts" }, { key: "label", kind: "bool" }],
    moves: ["shaded as the mountains are named"], say: "The Himalayas rise in the north.", example: { op: "relief", names: ["Himalayas"] } },
  { op: "graticule", group: "map", what: "A line of latitude or longitude.", fields: [{ key: "lat", kind: "number" }, { key: "lon", kind: "number" }, { key: "label", kind: "text" }, COLOR],
    moves: ["drawn as it is named"], say: "The Tropic of Cancer crosses India.", example: { op: "graticule", lat: 23.44, label: "Tropic of Cancer" } },
  { op: "dim", group: "map", what: "Fades what is filled on the map, before one area is highlighted.", fields: [{ key: "opacity", kind: "number" }],
    moves: ["as the line turns to one area"], say: "Now look only at the east.", example: { op: "dim", opacity: 0.15 } },
  { op: "icon", group: "map", what: "A small icon on places of the map (or in the side panel).",
    fields: [{ key: "name", kind: "text", required: true }, { key: "places", kind: "texts" }, { key: "label", kind: "text" }],
    moves: ["comes on as what it shows is named"], say: "Wheat grows in Punjab.", example: { op: "icon", name: "wheat", places: ["Punjab"], label: "Wheat" } },
  // ---------------- pointing (the script's own) ----------------
  { op: "reveal", group: "pointing", what: "Brings on more nodes of a diagram already up (the choreography writes it from a node's entry in a later line).",
    fields: [{ key: "diagram", kind: "text", required: true }, { key: "nodes", kind: "texts", required: true }], moves: ["on the word that names the node"],
    say: "And the grain fed the craftsmen.", example: { op: "reveal", diagram: "chain", nodes: ["granary"] } },
  { op: "focus", group: "pointing", what: "Rings one node of a diagram up, the rest dimmed, while it is talked about.",
    fields: [{ key: "diagram", kind: "text", required: true }, { key: "node", kind: "text", required: true }], moves: ["on the word that turns to it"],
    say: "So the granary was the heart of the town.", example: { op: "focus", diagram: "chain", node: "granary" } },
  { op: "point", group: "pointing", what: "Points at whatever is on the screen by that name (a node, a label, a card, a place, a template's part): a pulse, a lift, a ring drawn round it or a line drawn under it.",
    fields: [{ key: "target", kind: "text", required: true }, { key: "how", kind: "select", options: ["", ...POINT_HOWS], hint: "pulse (default), lift, circle, underline" }],
    moves: ["on the word that names it again", "how: pulse (swells once), lift (rises and settles), circle (a ring drawn round it, kept until the next), underline (a line drawn under it)"],
    say: "Look again at the fields.", example: { op: "point", target: "Fields" } },
  { op: "shade", group: "pointing", what: "Lights one labelled part of the picture up, the rest shaded, until the next line (held: until an unshade).",
    fields: [{ key: "part", kind: "text", required: true }, { key: "hold", kind: "bool", hint: "held over the next lines, until an unshade" }],
    moves: ["on the word that turns to the part"], say: "That soil is why the fields are rich.", example: { op: "shade", part: "soil" } },
  { op: "unshade", group: "pointing", what: "Lifts the light from the labelled picture: the whole picture clear again (after a held shade).",
    fields: [], moves: ["on the word that moves on from the part"], say: "Now look at the whole bank again.", example: { op: "unshade" } },
  { op: "label", group: "pointing", what: "Brings on a labelled picture's label held back (the picture's hold): its box, line and name.",
    fields: [{ key: "part", kind: "text", required: true }], moves: ["on the word that names the part"], say: "And there is the soil.", example: { op: "label", part: "soil" } },
  { op: "unlabel", group: "pointing", what: "Takes a label off the labelled picture: its box, line and name fade; the picture stays.",
    fields: [{ key: "part", kind: "text", required: true }], moves: ["when the picture moves on to its other parts"], say: "Leave the water aside.", example: { op: "unlabel", part: "water" } },
  { op: "unfocus", group: "pointing", what: "Lifts a diagram's focus: the veils over its other parts gone, the whole diagram clear.",
    fields: [{ key: "diagram", kind: "text", required: true }], moves: ["on the word that turns back to the whole"], say: "Now see the whole chain.", example: { op: "unfocus", diagram: "chain" } },
  { op: "clear", group: "pointing", what: "Clears the heading.", fields: [], moves: ["as a new topic begins"], say: "Now a new idea.", example: { op: "clear" } },
  // ---------------- free-form ----------------
  { op: "manim", group: "free", what: "A figure written as Manim code (graphs, geometry, apparatus, anything that moves): the Manim agent writes it, timed to its beat's words. Alone on its beat; a scene of its own.",
    fields: [{ key: "id", kind: "text", hint: "the figure's id (beats with the same id build on it)" }, { key: "plan", kind: "long", hint: "what the figure shows, step by step (the agent writes the code)" }],
    moves: ["times itself: its code waits for each word (the choreography does not cue it)"], say: "Watch the ball fall faster and faster.",
    example: { op: "manim", id: "fall", plan: "a ball dropped from rest, its speed arrow growing" } },
];

export const PRIMITIVE_BY_OP = new Map(PRIMITIVES.map((p) => [p.op, p]));

/** One primitive for a prompt: what it is, its parts, what can be done with it. */
export function primitiveText(p: Primitive): string {
  return [`${p.op} — ${p.what}`, ...(p.parts ? [`  parts: ${p.parts}`] : []), `  choreography: ${p.moves.join("; ")}`,
    `  e.g. ${JSON.stringify(p.example)}`].join("\n");
}

/** One beat for each primitive, in an order where each finds what it points at (a reveal after its diagram, an answer
 * after its question), on India's map: the Lab's "every primitive" experiment. A Manim figure is left out (the Manim
 * agent writes its code). */
export function everyPrimitive(): { region: Record<string, unknown>; chapter: { title: string; map: boolean; beats: { say: string; do: Record<string, unknown>[] }[] } } {
  return { region: { country: "India" }, chapter: { title: "Every primitive", map: true,
    // The picture first: a chapter's first beats must put something on the stage.
    beats: [...PRIMITIVES.filter((p) => p.op === "picture"), ...PRIMITIVES.filter((p) => p.op !== "manim" && p.op !== "picture")]
      .map((p) => ({ say: p.say, do: [structuredClone(p.example)] })) } };
}
