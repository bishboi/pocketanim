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
  summary: string;
  palette: string[];
  background: string;
  /** Colour for titles, sentences, and labels. */
  ink: string;
  /** Kokoro voice id for the narration. */
  voice: string;
  direction: string;
  example: string;
  /** Miniature of the frame, in a 320×180 viewBox. */
  preview: PreviewMark[];
};

export const TEMPLATES: Template[] = [
  {
    id: "manim",
    name: "Manim",
    summary: "Black field, precise strokes, constructions that draw themselves.",
    palette: ["#58C4DD", "#FFFF00", "#83C167"],
    background: "#000000",
    ink: "#FFFFFF",
    voice: "af_sarah",
    direction: [
      "Classic Manim. Black background. Thin precise strokes, almost no solid fills.",
      "Blue for the main object, yellow for the thing to notice, green for a result.",
      "Introduce geometry with Create and text with Write. Transform one form into the next instead of cutting.",
      "Equations use MathTex and TransformMatchingTex when the idea is mathematical.",
      "Leave a lot of black around the drawing. Nothing decorative that does not teach.",
    ].join(" "),
    example: ["Why the sky is blue", "Sunlight is many colours", "Air scatters blue light", "Sunset is what remains"].join("\n"),
    preview: [
      { t: "circle", cx: 118, cy: 96, r: 36, stroke: "#58C4DD", sw: 2 },
      { t: "line", x1: 118, y1: 96, x2: 200, y2: 64, stroke: "#FFFF00", sw: 2 },
      { t: "circle", cx: 200, cy: 64, r: 4, fill: "#FFFF00" },
      { t: "text", x: 28, y: 36, text: "Why the sky is blue", size: 14, fill: "#FFFFFF", weight: 500 },
      { t: "text", x: 214, y: 70, text: "blue", size: 11, fill: "#83C167" },
    ],
  },
  {
    id: "vox",
    name: "Vox",
    summary: "Flat colour blocks, bold type, motion-graphics pacing.",
    palette: ["#F2C14E", "#E07A5F", "#3D7A6A"],
    background: "#F6F1E7",
    ink: "#1C1915",
    voice: "af_bella",
    direction: [
      "A Vox-style explainer. Warm paper background, flat filled shapes, no thin technical strokes.",
      "Big type. Short phrases, not paragraphs. One strong colour block per idea: a filled Rectangle or circle in the accent, with the label beside it, never on top of it.",
      "Cuts are quick. Fade the previous idea before the next block arrives.",
      "When you chart or diagram, use solid fills and thick simple forms, the way a motion-graphics piece would, not a textbook figure.",
    ].join(" "),
    example: ["Why the sky is blue", "Sunlight is many colours", "Air scatters blue light", "Sunset is what remains"].join("\n"),
    preview: [
      { t: "rect", x: 24, y: 28, w: 150, h: 22, fill: "#1C1915", rx: 2 },
      { t: "rect", x: 36, y: 72, w: 88, h: 72, fill: "#F2C14E", rx: 6 },
      { t: "rect", x: 140, y: 96, w: 64, h: 48, fill: "#E07A5F", rx: 6 },
      { t: "rect", x: 218, y: 78, w: 72, h: 66, fill: "#3D7A6A", rx: 6 },
      { t: "text", x: 32, y: 44, text: "WHY THE SKY", size: 11, fill: "#F6F1E7", weight: 700 },
    ],
  },
  {
    id: "whiteboard",
    name: "Whiteboard",
    summary: "Marker on a white board. Drawn live, labelled by hand.",
    palette: ["#1A1A1A", "#2F6FED", "#E23D3D"],
    background: "#F7F5F0",
    ink: "#1A1A1A",
    voice: "am_adam",
    direction: [
      "A whiteboard lesson. Off-white background, black marker for structure, blue for the main idea, red for the one thing to circle.",
      "Everything is drawn, not revealed as a slide: Create for lines and shapes, Write for words.",
      "Stroke widths are marker-thick (6 to 8). Fills stay empty or nearly empty.",
      "Labels sit next to the sketch with a short leader line, the way a person would write beside a drawing.",
      "Circle the key term in red at the end. Do not use a dark theme.",
    ].join(" "),
    example: ["Why the sky is blue", "Sunlight is many colours", "Air scatters blue light", "Sunset is what remains"].join("\n"),
    preview: [
      { t: "text", x: 28, y: 40, text: "why the sky is blue", size: 16, fill: "#1A1A1A", weight: 500 },
      { t: "line", x1: 28, y1: 48, x2: 168, y2: 52, stroke: "#1A1A1A", sw: 2 },
      { t: "circle", cx: 90, cy: 110, r: 28, stroke: "#2F6FED", sw: 3 },
      { t: "line", x1: 118, y1: 110, x2: 190, y2: 88, stroke: "#1A1A1A", sw: 2 },
      { t: "text", x: 198, y: 92, text: "air", size: 13, fill: "#1A1A1A" },
      { t: "circle", cx: 214, cy: 86, r: 22, stroke: "#E23D3D", sw: 2 },
    ],
  },
  {
    id: "chalkboard",
    name: "Chalkboard",
    summary: "Chalk on a green board. Soft strokes, dusty highlights.",
    palette: ["#F4F0E4", "#F2E27A", "#9FD4E0"],
    background: "#1B3A2F",
    ink: "#F4F0E4",
    voice: "am_michael",
    direction: [
      "A chalkboard. Deep green background. Chalk white for words, pale yellow for emphasis, light blue for a second sketch.",
      "Strokes are soft and a little thick, like chalk, not vector-sharp. No solid neon fills.",
      "Write titles as if they were chalked at the top of the board, with a chalk underline.",
      "Diagrams, numbers, and equations are chalked in and can be wiped (FadeOut) before the next drawing.",
    ].join(" "),
    example: ["Why the sky is blue", "Sunlight is many colours", "Air scatters blue light", "Sunset is what remains"].join("\n"),
    preview: [
      { t: "text", x: 28, y: 42, text: "why the sky is blue", size: 15, fill: "#F4F0E4", weight: 500 },
      { t: "line", x1: 28, y1: 52, x2: 150, y2: 54, stroke: "#F2E27A", sw: 3 },
      { t: "circle", cx: 100, cy: 112, r: 26, stroke: "#F4F0E4", sw: 3 },
      { t: "line", x1: 126, y1: 112, x2: 200, y2: 90, stroke: "#9FD4E0", sw: 2 },
      { t: "text", x: 208, y: 96, text: "scatters", size: 12, fill: "#F2E27A" },
    ],
  },
];

/** The user message repeats this so a picked style cannot be dropped. */
export function filmBrief(template: Template): string {
  return [
    `STYLE LOCK. This film is ${template.name}, and no other style.`,
    `The file must set config.background_color = "${template.background}" and config.frame_rate = 15.`,
    `Titles and labels use ${template.ink}. Accents, in order: ${template.palette.join(", ")}.`,
    template.direction,
    "Make it immersive: the idea is acted, not listed. Open on the thing itself, already moving. While a sentence is spoken, the picture draws, shifts, or points, and it stays up until that sentence is finished.",
    "Each beat is a new slide. Before the next beat, FadeOut everything from the previous beat, including its title, labels, and picture. Nothing from an earlier slide remains. Text from two beats is never on screen together.",
    "Before every self.wait that covers speech, the immediately previous line is a comment of the form: # voice: the sentence",
    "That wait lasts about 0.45 seconds per word, and at least 1.6 seconds.",
    "Length follows the idea. A short idea stays under a minute. A lesson may run many beats, up to 30 minutes of speech. Do not pad a short idea, and do not crush a long one into three cards.",
    "Use a diagram, chart, timeline, equation, map, or molecule only when it explains more than the sentence, and draw it in this style.",
  ].join(" ");
}

export function templateById(id: string): Template {
  const found = TEMPLATES.find((t) => t.id === id);
  if (!found) throw new Error(`unknown template: ${id}`);
  return found;
}

/** What to draw is decided by the content. The template only decides the look. */
export function explainWith(): string {
  return [
    "Choose the picture the idea needs. The template is only the look.",
    "A relationship or a process becomes a diagram: a few nodes and arrows, labels beside the shapes.",
    "A comparison of amounts becomes a chart: bars or a simple plot, values above the marks, names below, none of them touching.",
    "A sequence in time becomes a timeline, captions alternating above and below the line.",
    "A mathematical step becomes one equation, replaced by the next, with a short caption clear of it.",
    "A place becomes a map from find_map. A molecule becomes the structure from molecule_guide.",
    "Use one of these when it explains more than a sentence would. Do not use one just to decorate.",
    "Whatever you pick, draw it in the template's colours, stroke, and background. A chart on a whiteboard is marker and white board, not a dashboard.",
  ].join(" ");
}

/** Shared layout contract. Appended to every template prompt. */
export function layoutContract(): string {
  return [
    "LAYOUT. Text that overlaps is a failed scene. So is text that clips the frame. So is a new beat drawn on top of the previous one.",
    "One slide at a time. Group everything a beat adds — title, sentences, shapes, labels — and FadeOut that group before the next beat's first object appears. Do not leave an old title up as a header for the rest of the lecture.",
    "The frame is 14.22 wide and 8 tall. Keep every object inside x -6.2 to 6.2 and y -3.3 to 3.3.",
    "Leave at least 0.35 units between any two Text or MathTex objects. Place with next_to(..., buff=0.35), arrange(..., buff=0.3), or to_edge(..., buff=0.4). Do not invent coordinates that share a point.",
    "Never shift a title by UP * 3. That clips it. A title is to_edge(UP, buff=0.4) and stays there.",
    "Body copy uses font_size 28 to 36. Titles use 40 to 52. Labels on shapes use 22 to 26 and at most four words.",
    "A line longer than 42 characters is split into two Text objects and arranged DOWN. Do not rely on a single wide string.",
    "The next beat always starts on an empty frame. FadeOut the previous group first, even when the new content would fit beside it.",
    "Use three bands that do not cross. Title in the top 1.2 units, the picture in the middle, the caption in the bottom 1.2 units.",
    "A label sits just outside the shape it names, with a visible gap. It never covers the shape, another label, or the caption.",
    "Use the template palette and its ink colour. config.background_color is the template background.",
  ].join(" ");
}
