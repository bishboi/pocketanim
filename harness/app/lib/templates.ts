/**
 * A template is a visual style — how the film looks — not a subject.
 * Diagrams, charts, maps, and equations are ways to explain, used when the
 * content needs them, and drawn in whichever style was picked.
 */

export type PreviewMark =
  | { t: "rect"; x: number; y: number; w: number; h: number; fill?: string; rx?: number; opacity?: number }
  | { t: "circle"; cx: number; cy: number; r: number; fill?: string; stroke?: string; sw?: number }
  | { t: "line"; x1: number; y1: number; x2: number; y2: number; stroke: string; sw?: number }
  | { t: "text"; x: number; y: number; text: string; size: number; fill: string; anchor?: "start" | "middle" | "end"; weight?: number };

export type Template = {
  id: string;
  name: string;
  /** Always "lecture": the agent writes a beat script that harness/lecture/compile_lecture.py turns into a narrated
   * lecture on the pocket_lecture engine, in `style`. */
  kind?: "lecture";
  /** The pocket_lecture style a lecture template compiles to. */
  style?: string;
  summary: string;
  palette: string[];
  background: string;
  /** Colour for titles, sentences, and labels. */
  ink: string;
  /** The speaker with Chirp 3 HD (PANIM_TTS=chirp). Gemini TTS speaks every template with Achird. */
  voice: string;
  direction: string;
  example: string;
  /** Miniature of the frame, in a 320×180 viewBox. */
  preview: PreviewMark[];
};

/** A lecture frame in miniature: map on the left, fact panel on the right. */
function lecturePreview(
  land: string,
  edge: string,
  panel: string,
  title: string,
  ink: string,
  accent: string,
  caption: string,
  captionInk: string,
): PreviewMark[] {
  return [
    { t: "circle", cx: 92, cy: 84, r: 48, fill: land, stroke: edge, sw: 2 },
    { t: "circle", cx: 80, cy: 72, r: 4, fill: accent },
    { t: "line", x1: 52, y1: 104, x2: 134, y2: 62, stroke: accent, sw: 3 },
    { t: "rect", x: 178, y: 18, w: 128, h: 124, fill: panel, rx: 3 },
    { t: "text", x: 188, y: 40, text: "Rivers", size: 15, fill: title, weight: 700 },
    { t: "text", x: 188, y: 70, text: "2,525 km", size: 17, fill: accent, weight: 700 },
    { t: "text", x: 188, y: 88, text: "• perennial", size: 10, fill: ink },
    { t: "rect", x: 70, y: 150, w: 180, h: 18, fill: caption, rx: 3 },
    { t: "text", x: 160, y: 163, text: "The Ganga is India's longest river.", size: 8, fill: captionInk, anchor: "middle" },
  ];
}

const LECTURE_EXAMPLE = [
  "The geography of India",
  "India lies entirely in the Northern Hemisphere, at the heart of South Asia.",
  "It covers 3.287 million km², the seventh largest country in the world.",
  "The Ganga is India's longest river, flowing 2,525 km to the Bay of Bengal.",
  "The monsoon brings about 75% of the year's rain between June and September.",
].join("\n");

/** Lecture templates: one per pocket_lecture style, and Auto, which picks the style from the subject. */
const LECTURES: Template[] = [
  {
    id: "lecture-auto", kind: "lecture", style: "auto", name: "Auto lecture",
    summary: "Reads the content, picks the subject kit: maps for geography, timelines for history, molecules, equations and graphs for science.",
    palette: ["#0F8B8D", "#8C5A2B", "#7DD3FC"], background: "#F4F8F8", ink: "#12303A", voice: "Kore",
    direction: "A narrated lecture whose style and pictures follow its subject.",
    example: [
      "Photosynthesis",
      "Plants make their own food from light, water and carbon dioxide.",
      "In the chloroplasts, chlorophyll captures sunlight.",
      "The overall reaction: 6CO2 + 6H2O -> C6H12O6 + 6O2.",
      "The glucose made is stored as starch or burned for energy in respiration.",
    ].join("\n"),
    preview: lecturePreview("#FFFFFF", "#0F8B8D", "#F4F8F8", "#0F8B8D", "#12303A", "#2E86AB", "#12303A", "#FFFFFF"),
  },
  {
    id: "lecture-parchment", kind: "lecture", style: "parchment", name: "Parchment lecture",
    summary: "History: an old page, brown ink, Roman capitals, timelines and quotes.",
    palette: ["#6B2E1A", "#8C5A2B", "#2F5D7C"], background: "#EFE3C6", ink: "#3B2A1A", voice: "Iapetus",
    direction: "A narrated history lecture in the parchment style.",
    example: [
      "The Mughal Empire",
      "Babur founded the Mughal Empire after winning the battle of Panipat in 1526.",
      "Akbar, who ruled from 1556 to 1605, built an empire across northern India.",
      "Shah Jahan built the Taj Mahal in Agra in memory of Mumtaz Mahal.",
      "After Aurangzeb died in 1707 the empire slowly broke apart.",
    ].join("\n"),
    preview: lecturePreview("#F6ECD4", "#6B2E1A", "#E9DBB8", "#6B2E1A", "#3B2A1A", "#2F5D7C", "#3B2A1A", "#F6EEDC"),
  },
  {
    id: "lecture-lab", kind: "lecture", style: "lab", name: "Lab lecture",
    summary: "Biology and chemistry: clean white, teal, molecules and reactions drawn out.",
    palette: ["#0F8B8D", "#D1495B", "#2E86AB"], background: "#F4F8F8", ink: "#12303A", voice: "Kore",
    direction: "A narrated science lecture in the lab style.",
    example: [
      "Combustion",
      "When methane burns it reacts with oxygen from the air.",
      "The equation is CH4 + 2O2 -> CO2 + 2H2O.",
      "Carbon dioxide and water are the products, and heat is released.",
    ].join("\n"),
    preview: lecturePreview("#FFFFFF", "#0F8B8D", "#F4F8F8", "#0F8B8D", "#12303A", "#D1495B", "#12303A", "#FFFFFF"),
  },
  {
    id: "lecture-cosmos", kind: "lecture", style: "cosmos", name: "Cosmos lecture",
    summary: "Physics and space: night sky, cyan light, equations and graphs.",
    palette: ["#7DD3FC", "#F472B6", "#FDE68A"], background: "#0A0E1F", ink: "#E6ECFF", voice: "Charon",
    direction: "A narrated physics lecture in the cosmos style.",
    example: [
      "Gravity",
      "Every mass attracts every other mass.",
      "Newton wrote it as F = G m1 m2 / r^2.",
      "Near the Earth a falling object gains about 9.8 metres per second every second.",
    ].join("\n"),
    preview: lecturePreview("#121836", "#7DD3FC", "#0F1530", "#7DD3FC", "#E6ECFF", "#F472B6", "#05070F", "#E6ECFF"),
  },
  {
    id: "lecture-atlas", kind: "lecture", style: "atlas", name: "Atlas lecture",
    summary: "Dark cartographic lecture: map, fact panel, captions, narration.",
    palette: ["#E3B25A", "#5AB4F0", "#F2C14E"], background: "#0D1117", ink: "#F4E9D8", voice: "Kore",
    direction: "A narrated map lecture in the atlas style: dark navy, sand outlines, serif titles.",
    example: LECTURE_EXAMPLE,
    preview: lecturePreview("#1A2230", "#E3B25A", "#141A23", "#E3B25A", "#F4E9D8", "#5AB4F0", "#05070A", "#F4E9D8"),
  },
  {
    id: "lecture-vox", kind: "lecture", style: "vox", name: "Vox lecture",
    summary: "Editorial explainer: warm paper, black type, yellow highlighter.",
    palette: ["#111111", "#FFD02F", "#1F6FB2"], background: "#EFE8DA", ink: "#161616", voice: "Aoede",
    direction: "A narrated map lecture in the Vox style: paper, uppercase condensed titles, highlighter bars.",
    example: LECTURE_EXAMPLE,
    preview: lecturePreview("#FBF8F1", "#111111", "#EFE8DA", "#111111", "#161616", "#1F6FB2", "#111111", "#FFFFFF"),
  },
  {
    id: "lecture-cardboard", kind: "lecture", style: "cardboard", name: "Cardboard lecture",
    summary: "Craft look: kraft paper, cut-out map with a shadow, taped notes.",
    palette: ["#2B1D10", "#B8741F", "#1F6FB2"], background: "#B98A57", ink: "#2B1D10", voice: "Puck",
    direction: "A narrated map lecture in the cardboard style: kraft paper and paper cut-outs.",
    example: LECTURE_EXAMPLE,
    preview: lecturePreview("#EAD6AA", "#86613A", "#F3E6C8", "#2B1D10", "#2B1D10", "#1F6FB2", "#F3E6C8", "#2B1D10"),
  },
  {
    id: "lecture-whiteboard", kind: "lecture", style: "whiteboard", name: "Whiteboard lecture",
    summary: "Marker on a board: wobbly lines, blue underlined titles that write on.",
    palette: ["#1B1B1B", "#1565C0", "#D9730D"], background: "#F7F7F3", ink: "#1B1B1B", voice: "Charon",
    direction: "A narrated map lecture in the whiteboard style: marker lines, text that writes itself on.",
    example: LECTURE_EXAMPLE,
    preview: lecturePreview("#F7F7F3", "#1B1B1B", "#F7F7F3", "#1565C0", "#1B1B1B", "#1565C0", "#FFFFFF", "#1B1B1B"),
  },
  {
    id: "lecture-blueprint", kind: "lecture", style: "blueprint", name: "Blueprint lecture",
    summary: "Technical drawing: blue grid, white linework, monospace type.",
    palette: ["#FFFFFF", "#8ECAFF", "#FFD166"], background: "#0E3A66", ink: "#EAF2FF", voice: "Orus",
    direction: "A narrated map lecture in the blueprint style: grid, white lines, dashed frames.",
    example: LECTURE_EXAMPLE,
    preview: lecturePreview("#1A5288", "#FFFFFF", "#0E3A66", "#FFFFFF", "#EAF2FF", "#8ECAFF", "#0A2C4E", "#EAF2FF"),
  },
  {
    id: "lecture-chalkboard", kind: "lecture", style: "chalkboard", name: "Chalkboard lecture",
    summary: "Chalk on green: pale yellow titles, soft dusty strokes.",
    palette: ["#F4F0E4", "#F2E27A", "#9FD4E0"], background: "#1B3A2F", ink: "#F4F0E4", voice: "Puck",
    direction: "A narrated map lecture in the chalkboard style.",
    example: LECTURE_EXAMPLE,
    preview: lecturePreview("#224536", "#F4F0E4", "#1B3A2F", "#F2E27A", "#F4F0E4", "#9FD4E0", "#12291F", "#F4F0E4"),
  },
];

/** The templates: lectures only, Auto first (it reads the content and picks the subject's kit and style). The older
 * templates, where the model wrote a whole film's Manim itself (Manim, Vox, Whiteboard, Chalkboard), are gone. */
export const TEMPLATES: Template[] = LECTURES;

/** A template by id. An id from before the older templates were removed ("manim", "vox", ...) opens as Auto. */
export function templateById(id: string): Template {
  return TEMPLATES.find((t) => t.id === id) ?? TEMPLATES[0];
}

/** The lecture lengths the page offers, in minutes, when a length is chosen rather than left to the source
 * (a long one is made as several videos of 25-30 min). */
// Past 30 minutes a lecture is a series of micro-lectures of 25-30 min (topics.ts), as many as it needs.
export const LENGTH_CHOICES = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 375];

/** The subjects a lecture can be taught as (the page's Subject menu); "auto" lets the content decide. Mathematics,
 * physics and chemistry are taught as theory, then long problems solved step by step, on diagrams and graphs. */
export const SUBJECT_CHOICES: [string, string][] = [
  ["auto", "Automatic (from the content)"], ["mathematics", "Mathematics"], ["physics", "Physics"],
  ["chemistry", "Chemistry"], ["biology", "Biology"], ["history", "History"], ["geography", "Geography"],
  ["economics", "Economics"], ["general", "General"],
];
