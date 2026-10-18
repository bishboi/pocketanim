/**
 * The scene writer's instructions on the beta engine (engine/BETA_ENGINE.md): each beat's visuals as slides of boxes,
 * each thing animated on the words that bring it. The narration is fixed (the transcript's sentences, as the script
 * grouped them into beats); the model writes each beat's layout (a new slide), the elements it brings, and how and
 * on which words each animates. Asked for a whole lecture, a chapter, one beat, or the beats the compiler refused,
 * with the same context as the current engine's writer (prompts/scenes.ts): the lecture, its chapters, its figures,
 * every beat with the script's note of what is on screen, the look, the subject and the kinds switched off.
 */

import { part, render, type Part } from "./parts";
import type { ScenesAsk, SceneBeatInput, ScenePace, SceneSubject } from "./scenes";

const ROLE = [
  "You design the visuals of ONE narrated lecture video, beat by beat, as SLIDES OF BOXES whose every element is",
  "animated on the words that bring it (the beta engine: a compiler turns your answer into Manim for a phone).",
  "The NARRATION IS FIXED: it is the lecture's transcript, already cut into chapters and beats, and each beat's",
  "sentences (its \"say\") are said exactly as given. Your work is what the viewer sees while each line is said: the",
  "slides, what is on them, and the moment each thing comes on, is pointed at or leaves. The script's note of what is",
  "on screen (\"on screen:\") is its writer's plan for the beat, and a figure named on a beat is shown on it.",
].join("\n");

const FORMAT = [
  "HOW A BEAT IS WRITTEN. A beat is {\"beat\": <its number>, \"layout\"?, \"elements\"?, \"animate\"?, \"clear\"?,",
  "\"paragraph\"?, \"pause\"?}:",
  "  - \"layout\": STARTS A NEW SLIDE (what was up leaves as the line begins). A beat without one adds to the slide",
  "    that is up. The first beat of every chapter starts one.",
  "  - \"elements\": what this beat brings onto the slide, each with an \"id\" (unique on its slide) and a slot.",
  "  - \"animate\": the steps, in the order they happen, each naming an element (or a part of one) by id.",
  "  - \"clear\": true: everything on the slide leaves as the line begins.",
  "  - \"paragraph\": true on the first beat of each paragraph; \"pause\": 1-2 extra seconds after a line that needs to sink in.",
  "",
  "LAYOUTS AND THEIR SLOTS (the board below the chapter's heading, above the caption):",
  "  full: main | center: main (the middle 70%) | left-right: left, right | wide-left: left (62%), right |",
  "  wide-right: left, right (62%) | top-bottom: top (46%), bottom | title-body: title (a band), body |",
  "  title-left-right: title, left, right | three-col: left, middle, right | grid-2x2: tl, tr, bl, br |",
  "  focus-side: main (70%), side",
  "  An element goes in a \"slot\" of its slide's layout. Several elements in one slot are STACKED down it, in order.",
  "  \"box\": [x, y, w, h] (shares of the board, 0-1, y down from the top) puts one in its own box instead, over the",
  "  slots (a callout in a corner). Every element of a slide is laid out when the slide starts, so nothing moves or",
  "  overlaps later: give a slide no more than its slots can hold (about 2 elements a slot, 6 on a slide).",
  "",
  "ELEMENTS (the key that holds the content says the kind):",
  '  {"id": "t", "text": "The steam engine", "style": "title"}   styles: title, heading, body, callout (in a box),',
  "      caption, quote, label",
  '  {"id": "pts", "list": ["Coal burns", "Water boils"], "numbered"?: true}   up to 8 items; parts pts.0, pts.1, ...',
  '  {"id": "pic", "image": {"generate": "a steam locomotive, side view", "labels": ["boiler", "chimney"]}}',
  "      made by the image model as a cutout with no words in it (describe it in English: what it shows, how it is",
  "      seen); \"labels\": up to 6 parts really in the picture, each written beside it with a line to its part; parts",
  "      pic.boiler, pic.left-ventricle (lower case, spaces as -). \"scene\": true for a whole scene edge to edge.",
  '  {"id": "f", "image": {"figure": "<a figure id below>"}}   one of the book\'s figures',
  '  {"id": "i", "icon": "seed", "label"?: "a seed"}   a small drawing of a thing',
  '  {"id": "n", "number": {"value": "2,525 km", "label": "length of the Ganga"}}',
  '  {"id": "s", "shape": "box" | "circle" | "pill", "text": "Coal"}',
  '  {"id": "e", "equation": "F = ma", "label"?: "force = mass x acceleration"}   TeX',
  '  {"id": "b", "bars": {"items": [["Rice", 130], ["Wheat", 110]], "title"?: "Harvest (million t)"}}   parts b.0, b.1',
  '  {"id": "ab", "arrow": {"from": "a", "to": "b", "label"?: "heat"}}   joins two elements of the slide; no slot',
  '  {"id": "tl", "timeline": {"events": [["1526", "Panipat"], ["1857", "Revolt"]], "title"?, "range"?: ["1500", "1900"],',
  '      "spans"?: [["1526", "1857", "Mughal Empire"]]}}   2-10 events, placed in proportion to their dates',
  "",
  "ANIMATE: each step names one element or part (\"id\") and ONE of:",
  "  \"in\": fade | slide (+ \"from\": left, right, up, down) | rise | drop | pop | grow | type (a sentence typed) |",
  "        write (titles, equations) | draw (shapes, arrows) | stagger (a list's or a chart's items one by one) | appear",
  "  \"emphasis\": highlight (a box round it; round a picture's part, the part's own box) | circle | underline | pulse |",
  "        flash | color (+ \"color\": GOLD, ROSE, RIVER, GREEN, SAND) | dim-others | focus (dims the rest, boxes it) | enlarge",
  "  \"out\": fade | slide (+ \"to\") | shrink | unwrite",
  "  \"move\": a slot's name: the element moves into it",
  "WHEN: \"on\": a word or short phrase THE BEAT'S OWN LINE SAYS, copied exactly: the step starts as it is said. Or",
  "  \"with\": <an id> (at the same moment), \"after\": <an id> (when it ends), plus \"delay\" (seconds). A step with none",
  "  follows the one before. An element this beat brings that no step names fades in, in its turn. Marks (highlight,",
  "  circle, underline, focus) and dimming last until the next line.",
].join("\n");

const DESIGN = [
  "HOW TO DESIGN THE SLIDES:",
  "  - ONE IDEA A SLIDE. A new layout when the lesson moves to a new idea (often a paragraph); the beats of that idea",
  "    build the slide up, each bringing its part on its words, and pointing at what is already there when the line",
  "    returns to it. Do not start a new slide on every beat, and do not keep one slide for a whole chapter.",
  "  - EVERYTHING ON ITS WORDS. Give every step an \"on\" with words from its beat's line (a name, a number, a key",
  "    word), so the picture follows the voice; things that belong together use \"with\" or \"after\".",
  "  - FEW WORDS ON SCREEN. Never write the narration on the slide. Titles and headings of 2-6 words, list items of",
  "    1-6 words, at most 5 items, a callout of one short line. The words on screen are the key terms, names, numbers",
  "    and steps the line says.",
  "  - THE RIGHT ELEMENT FOR THE IDEA: a person, place, thing or scene -> an image (labelled when the line names its",
  "    parts, each part highlighted on its name); a number -> a number; amounts to compare -> bars; dates -> a timeline;",
  "    a sequence or a cause -> shapes joined by arrows, or a numbered list; two kinds -> two columns (left-right or",
  "    title-left-right) with a label and a list each; a law -> an equation; a new term -> its word as a title and its",
  "    meaning as a callout; a key sentence or a source's words -> a quote.",
  "  - A FIGURE NAMED ON A BEAT is shown on it ({\"image\": {\"figure\": \"<id>\"}}), usually large (wide-left, focus-side or",
  "    full), its points beside it.",
  "  - POINT AT WHAT THE LINE STRESSES: highlight or circle the item named; focus or dim-others for \"the key one\";",
  "    underline a key phrase; color for a change of state. Not on every beat.",
  "  - VARY the layouts and entrances from slide to slide; pictures large, text beside them; a slide should look full",
  "    but never crowded.",
  "  - IDs are short (a, b, pic, pts) and unique on their slide; a part is <id>.<part> as above. Name only what is on",
  "    the slide that is up.",
  "  - MAPS are not drawn by this engine: a chapter marked \"on a map\" is drawn on the board here (places as a list,",
  "    a picture, or a timeline of where things happened).",
].join("\n");

const SHAPE = [
  "THE ANSWER (write_slides): the beats asked for, by their numbers (the say of each is the one given and is not",
  "written again), and the lecture's emblem:",
  '{"emblem"?: "<one simple object that stands for the whole topic>",',
  ' "beats": [{"beat": 4, "layout": "wide-left", "paragraph": true,',
  '            "elements": [{"id": "pic", "image": {"generate": "...", "labels": ["boiler"]}, "slot": "left"},',
  '                         {"id": "t", "text": "The steam engine", "style": "heading", "slot": "right"},',
  '                         {"id": "pts", "list": ["Coal burns", "Water boils"], "slot": "right"}],',
  '            "animate": [{"id": "pic", "in": "grow", "on": "locomotive"}, {"id": "t", "in": "write", "with": "pic"},',
  '                        {"id": "pts.0", "in": "slide", "from": "right", "on": "coal"},',
  '                        {"id": "pic.boiler", "emphasis": "highlight", "on": "boiler"}]},',
  '           {"beat": 5, "animate": [{"id": "pts.1", "in": "slide", "from": "right", "on": "boils"}]}]}',
].join("\n");

export const BETA_SCENES_TOOL = {
  type: "function" as const,
  function: {
    name: "write_slides",
    description: "Save each beat's slide work (layout, elements, animate, clear, paragraph, pause) by the beat's number, and the lecture's emblem.",
    parameters: {
      type: "object",
      properties: {
        emblem: { type: "string", description: "One simple object that stands for the whole topic (the lecture's emblem)." },
        beats: {
          type: "array",
          items: {
            type: "object",
            properties: {
              beat: { type: "integer", description: "The beat's number, as given." },
              layout: { type: "string", description: "Starts a new slide with this layout." },
              elements: { type: "array", items: { type: "object", additionalProperties: true }, description: "What this beat brings onto the slide." },
              animate: { type: "array", items: { type: "object", additionalProperties: true }, description: "The steps, each on its words." },
              clear: { type: "boolean", description: "Everything on the slide leaves as the line begins." },
              paragraph: { type: "boolean", description: "The first beat of a paragraph." },
              pause: { type: "number", description: "Extra seconds after the line, 1-2, rarely." },
            },
            required: ["beat"],
          },
        },
      },
      required: ["beats"],
    },
  },
};

/** What a beat holds on the beta engine, as the scene writer gives it. */
export type BetaBeat = { layout?: string; elements?: Record<string, unknown>[]; animate?: Record<string, unknown>[]; clear?: boolean };

export function betaScenesPrompt(x: {
  lecture: { n: number; title: string };
  look: string;
  kinds: string[];
  labels: Record<string, string>;
  chapters: { n: number; title: string; narration: string; map: boolean }[];
  beats: SceneBeatInput[];
  figures: { id: string; way: string; caption: string; ready: boolean }[];
  ask: ScenesAsk;
  problems?: Record<number, string[]>;
  note?: string;
  subject?: SceneSubject;
  pace?: ScenePace;
}): { system: Part[]; user: Part[] } {
  const writing = (b: SceneBeatInput) => x.ask.what === "lecture" || (x.ask.what === "chapter" && b.chapter === x.ask.chapter)
    || (x.ask.what === "beat" && b.n === x.ask.beat) || (x.ask.what === "fix" && x.ask.beats.includes(b.n));
  const slide = (ops?: unknown[]) => {
    const op = (ops ?? []).find((o) => (o as { op?: string })?.op === "beta") as Record<string, unknown> | undefined;
    if (!op) return undefined;
    const { op: _, ...rest } = op;
    return JSON.stringify(rest);
  };
  const beatLine = (b: SceneBeatInput) => [
    `#${b.n} [ch ${b.chapter}] "${b.text}"`,
    `   on screen: ${b.show || "-"}`,
    ...(b.figures ?? []).map((f) => `   figure: ${f.id} (${f.way}${f.ready ? "" : ", not made yet: the book's picture is shown"}) - ${f.caption || "(no caption)"}`),
    ...(b.kinds ? [`   this beat may use only: ${b.kinds.map((k) => x.labels[k] ?? k).join(", ") || "text, lists, shapes, icons and arrows"}`] : []),
    ...(!writing(b) && slide(b.ops) ? [`   as it is (not to be written): ${slide(b.ops)}`] : []),
    ...(writing(b) && slide(b.ops) && x.ask.what !== "lecture" ? [`   now (to be written again): ${slide(b.ops)}`] : []),
    ...(x.problems?.[b.n]?.length ? x.problems[b.n].map((p) => `   COMPILER: ${p}`) : []),
  ].join("\n");
  const target = x.ask.what === "lecture" ? `every beat, 1 to ${x.beats.at(-1)?.n ?? 0}`
    : x.ask.what === "chapter" ? `the beats of chapter ${x.ask.chapter} only (${x.beats.filter(writing).map((b) => `#${b.n}`).join(", ")})`
      : x.ask.what === "beat" ? `beat #${x.ask.beat} only (the beats around it are given as they are; it adds to the slide up before it unless it starts one)`
        : `beats ${x.ask.beats.map((n) => `#${n}`).join(", ")} only, mending what the compiler says of each`;
  const off = Object.keys(x.labels).filter((k) => !x.kinds.includes(k));
  return {
    system: [
      part("role", "Role", "rules", ROLE),
      ...(x.subject?.guidance ? [part("subject", `Subject: ${x.subject.label}`, "rules", [
        `SUBJECT. This is a ${x.subject.label} lecture. ${x.subject.guidance}`,
        `Often useful in ${x.subject.label.toLowerCase()} lectures: ${(x.subject.kit ?? []).join(", ")} (shown here with the elements below).`,
      ])] : []),
      part("format", "How a beat is written (the beta engine)", "rules", FORMAT),
      part("design", "How to design the slides", "rules", DESIGN),
      ...(x.pace?.change === "beat" ? [part("pace", "This run's pace", "rules",
        "THIS RUN'S PACE: every beat brings something new or points at something on the slide; no beat's line passes with the slide standing still.")] : []),
      part("shape", "The answer's shape", "rules", SHAPE),
      ...(off.length ? [part("off", `Switched off here (${off.length})`, "choices", [
        "SWITCHED OFF FOR THIS LECTURE: never use these; anything of them is taken out:",
        ...off.map((k) => `  - ${x.labels[k] ?? k}`),
        "(AI illustrations: no image with \"generate\"; Book figures: no image with \"figure\"; Timeline: no timeline;",
        "Equations: no equation; Stats and bars: no number or bars.)"])] : []),
    ],
    user: [
      part("look", "The look", "context", `The lecture is drawn in ${x.look}. Colours are the look's: name them only as GOLD, ROSE, RIVER, GREEN or SAND.`),
      part("lecture", "The lecture and its chapters", "plan", [`Lecture ${x.lecture.n}: ${x.lecture.title}`,
        ...x.chapters.map((c) => `Chapter ${c.n}: ${c.title}${c.map ? " (on a map in the script: drawn on the board here)" : ""} - title card: "${c.narration}"`)]),
      part("figures", `The lecture's figures (${x.figures.length})`, "items", x.figures.length
        ? x.figures.map((f) => `${f.id}: ${f.way}${f.ready ? "" : " (not made yet)"} - ${f.caption || "(no caption)"}`) : "None."),
      part("script", `The beats (${x.beats.length})`, "book", x.beats.map(beatLine)),
      ...(x.note ? [part("note", "Your note for this", "context", x.note)] : []),
      ...(x.ask.what === "fix" ? [part("retry", "What the compiler said", "retry",
        "The compiler mended or left out parts of these beats (COMPILER lines above). Write them again so nothing is left out: keep what is right, change what it names.")] : []),
      part("ask", "Request", "ask", `Write the slides (write_slides) of ${target}: each beat by its number, a "layout" where a new slide starts, ` +
        `its elements, and an "animate" step for each, "on" the words of its own line.`),
    ],
  };
}

/** The role when the instructions are given to any chat model by hand (the Voice tab's editor). */
const HAND_ROLE = [
  "You design the visuals of ONE chapter of a narrated lecture video as SLIDES OF BOXES, every element animated on",
  "the words that bring it (the beta engine). You are given the chapter's script as JSON (below the instructions) and",
  "what to change; you return the whole chapter's script, changed. Each beat's sentences (\"say\") are the lecture's",
  "transcript: keep them as they are unless you are asked to change the words.",
].join("\n");

const HAND_SHAPE = [
  "THE ANSWER: the whole chapter's script as ONE JSON object, in exactly this shape, and nothing else:",
  '{"engine": "beta", "style": "<as given>", "art": "<as given>", "region": null, "emblem": "<as given>" | null,',
  ' "chapter": {"title", "narration", "map": false,',
  '   "beats": [{"beat": <its number, as given>, "say": "...", "layout"?, "elements"?, "animate"?, "clear"?, "paragraph"?, "pause"?}]}}',
  "Keep every beat's \"beat\" number as given (a beat you add has none).",
].join("\n");

/** The beta scene writer's instructions as one text to give any chat model by hand, with a chapter's script. */
export function betaHandInstructions(x: { look: string; kinds: string[]; labels: Record<string, string>; subject?: SceneSubject; pace?: ScenePace }): string {
  const system = betaScenesPrompt({ lecture: { n: 0, title: "" }, look: x.look, kinds: x.kinds, labels: x.labels, chapters: [], beats: [],
    figures: [], ask: { what: "lecture" }, subject: x.subject, pace: x.pace }).system
    .map((p) => (p.key === "role" ? { ...p, text: HAND_ROLE } : p.key === "shape" ? { ...p, text: HAND_SHAPE } : p));
  return [render(system), "", `THE LOOK: the lecture is drawn in ${x.look}. Name colours only as GOLD, ROSE, RIVER, GREEN or SAND.`].join("\n");
}
