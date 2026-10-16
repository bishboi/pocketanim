/**
 * The lecture's look, as v1 has it (harness/app/lib/templates.ts, artstyles.ts): a STYLE is the whole film's frame
 * (background, fonts, panel, captions: one of the engine's styles, pocket_lecture.py) and an ART STYLE is the hand
 * that draws the pictures, diagrams, charts and maps on it (artstyle.py); "auto" draws with the style's own.
 *
 * The scenes are compiled and rendered in it (compile_lecture.py's "style" and "art"), and the Styled redraws of
 * the figures are drawn in it (prompts/redraw.ts). No server code here: the page shows the pickers from it.
 */

export type PreviewMark =
  | { t: "rect"; x: number; y: number; w: number; h: number; fill?: string; rx?: number; opacity?: number }
  | { t: "circle"; cx: number; cy: number; r: number; fill?: string; stroke?: string; sw?: number }
  | { t: "line"; x1: number; y1: number; x2: number; y2: number; stroke: string; sw?: number }
  | { t: "text"; x: number; y: number; text: string; size: number; fill: string; anchor?: "start" | "middle" | "end"; weight?: number };

export type LectureStyle = {
  /** The engine's style. */
  id: string;
  name: string;
  summary: string;
  /** Its colours, for a redraw in it: the main ones, the board and the ink. */
  palette: string[];
  background: string;
  ink: string;
  /** A miniature of its frame (320×180). */
  preview: PreviewMark[];
};

/** A frame in miniature: the stage on the left, the panel on the right, the caption below. */
function preview(land: string, edge: string, panel: string, title: string, ink: string, accent: string, caption: string, captionInk: string): PreviewMark[] {
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

export const STYLES: LectureStyle[] = [
  { id: "atlas", name: "Atlas", summary: "Dark cartographic: navy board, sand outlines, serif titles.", palette: ["#E3B25A", "#5AB4F0", "#F2C14E"],
    background: "#0D1117", ink: "#F4E9D8", preview: preview("#1A2230", "#E3B25A", "#141A23", "#E3B25A", "#F4E9D8", "#5AB4F0", "#05070A", "#F4E9D8") },
  { id: "parchment", name: "Parchment", summary: "History: an old page, brown ink, Roman capitals, timelines and quotes.", palette: ["#6B2E1A", "#8C5A2B", "#2F5D7C"],
    background: "#EFE3C6", ink: "#3B2A1A", preview: preview("#F6ECD4", "#6B2E1A", "#E9DBB8", "#6B2E1A", "#3B2A1A", "#2F5D7C", "#3B2A1A", "#F6EEDC") },
  { id: "lab", name: "Lab", summary: "Biology and chemistry: clean white, teal, molecules and reactions drawn out.", palette: ["#0F8B8D", "#D1495B", "#2E86AB"],
    background: "#F4F8F8", ink: "#12303A", preview: preview("#FFFFFF", "#0F8B8D", "#F4F8F8", "#0F8B8D", "#12303A", "#D1495B", "#12303A", "#FFFFFF") },
  { id: "cosmos", name: "Cosmos", summary: "Physics and space: night sky, cyan light, equations and graphs.", palette: ["#7DD3FC", "#F472B6", "#FDE68A"],
    background: "#0A0E1F", ink: "#E6ECFF", preview: preview("#121836", "#7DD3FC", "#0F1530", "#7DD3FC", "#E6ECFF", "#F472B6", "#05070F", "#E6ECFF") },
  { id: "vox", name: "Vox", summary: "Editorial explainer: warm paper, black type, yellow highlighter.", palette: ["#111111", "#FFD02F", "#1F6FB2"],
    background: "#EFE8DA", ink: "#161616", preview: preview("#FBF8F1", "#111111", "#EFE8DA", "#111111", "#161616", "#1F6FB2", "#111111", "#FFFFFF") },
  { id: "cardboard", name: "Cardboard", summary: "Craft look: kraft paper, cut-out shapes with a shadow, taped notes.", palette: ["#2B1D10", "#B8741F", "#1F6FB2"],
    background: "#B98A57", ink: "#2B1D10", preview: preview("#EAD6AA", "#86613A", "#F3E6C8", "#2B1D10", "#2B1D10", "#1F6FB2", "#F3E6C8", "#2B1D10") },
  { id: "whiteboard", name: "Whiteboard", summary: "Marker on a board: wobbly lines, blue underlined titles that write on.", palette: ["#1B1B1B", "#1565C0", "#D9730D"],
    background: "#F7F7F3", ink: "#1B1B1B", preview: preview("#F7F7F3", "#1B1B1B", "#F7F7F3", "#1565C0", "#1B1B1B", "#1565C0", "#FFFFFF", "#1B1B1B") },
  { id: "blueprint", name: "Blueprint", summary: "Technical drawing: blue grid, white linework, monospace type.", palette: ["#FFFFFF", "#8ECAFF", "#FFD166"],
    background: "#0E3A66", ink: "#EAF2FF", preview: preview("#1A5288", "#FFFFFF", "#0E3A66", "#FFFFFF", "#EAF2FF", "#8ECAFF", "#0A2C4E", "#EAF2FF") },
  { id: "chalkboard", name: "Chalkboard", summary: "Chalk on green: pale yellow titles, soft dusty strokes.", palette: ["#F4F0E4", "#F2E27A", "#9FD4E0"],
    background: "#1B3A2F", ink: "#F4F0E4", preview: preview("#224536", "#F4F0E4", "#1B3A2F", "#F2E27A", "#F4F0E4", "#9FD4E0", "#12291F", "#F4F0E4") },
];

export type ArtStyle = { id: string; name: string; summary: string };

export const ART_STYLES: ArtStyle[] = [
  { id: "auto", name: "Style's own", summary: "The art the style draws with." },
  { id: "clean", name: "Clean", summary: "Flat colours and crisp lines." },
  { id: "detailed", name: "Detailed", summary: "Shaded shapes with highlights and rims; a relief map." },
  { id: "blueprint", name: "Blueprint", summary: "Fine technical line drawings, faint fills, construction marks." },
  { id: "chalk", name: "Chalk", summary: "Soft pastel chalk lines with a hand-drawn wobble and dust." },
  { id: "sketch", name: "Sketch", summary: "Pencil outlines with cross-hatched shading." },
  { id: "neon", name: "Neon", summary: "Glowing lines of light over dark, translucent shapes." },
  { id: "watercolour", name: "Watercolour", summary: "Layered translucent washes and thin ink lines." },
];

/** The art each style draws with when it is left to it (artstyle.TEMPLATE_ART). */
export const STYLE_ART: Record<string, string> = {
  atlas: "detailed", vox: "clean", cardboard: "watercolour", whiteboard: "sketch", blueprint: "blueprint",
  chalkboard: "chalk", parchment: "sketch", lab: "detailed", cosmos: "neon",
};

export type Look = { style: string; art: string };
export const DEFAULT_LOOK: Look = { style: "atlas", art: "auto" };

export function styleOf(id?: string): LectureStyle {
  return STYLES.find((s) => s.id === id) ?? STYLES[0];
}

export function artOf(id?: string): ArtStyle {
  return ART_STYLES.find((a) => a.id === id) ?? ART_STYLES[0];
}

/** A look made of known ids. */
export function cleanLook(x: Partial<Look> | undefined): Look {
  return { style: styleOf(x?.style).id, art: artOf(x?.art).id };
}

/** The art the look draws with ("auto" made the style's own). */
export function artUsed(look: Look): ArtStyle {
  return artOf(look.art === "auto" ? STYLE_ART[look.style] : look.art);
}

/** The look in words, for a prompt (a Styled redraw, the scene writer). */
export function lookWords(look: Look): string {
  const s = styleOf(look.style);
  const a = artUsed(look);
  return `the "${s.name}" style (${s.summary}) drawn as "${a.name}" art (${a.summary}); its colours ${s.palette.join(", ")} with ink ${s.ink}, on a ${s.background} board`;
}

/** A miniature of each art style (a circle and a bar drawn that way, 64×36), as SVG elements. */
export function artPreview(id: string, ink: string, accent: string): string {
  const shapes: Record<string, string> = {
    clean: `<circle cx="20" cy="18" r="10" fill="${accent}"/><rect x="38" y="10" width="14" height="18" fill="${ink}" opacity=".8"/>`,
    detailed:
      `<circle cx="20" cy="18" r="10" fill="${accent}" stroke="#000" stroke-opacity=".45" stroke-width="1.2"/>` +
      `<circle cx="22" cy="20" r="8" fill="#000" opacity=".18"/><circle cx="16.5" cy="14.5" r="4" fill="#fff" opacity=".45"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="${ink}" opacity=".8" stroke="#000" stroke-opacity=".45"/>` +
      `<rect x="40" y="11" width="3" height="16" fill="#fff" opacity=".35"/>`,
    blueprint:
      `<circle cx="20" cy="18" r="10" fill="${accent}" fill-opacity=".12" stroke="${accent}" stroke-width="1"/>` +
      `<path d="M8 18H32M20 6V30" stroke="${ink}" stroke-width=".5" opacity=".6"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="none" stroke="${ink}" stroke-width="1"/>`,
    chalk:
      `<circle cx="20" cy="18" r="10" fill="${accent}" fill-opacity=".5" stroke="${accent}" stroke-width="1.6"/>` +
      `<path d="M13 23L25 11M16 26L28 14M11 19L21 9" stroke="#fff" stroke-width=".7" opacity=".35"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="${ink}" fill-opacity=".45" stroke="${ink}" stroke-width="1.5"/>`,
    sketch:
      `<circle cx="20" cy="18" r="10" fill="${accent}" fill-opacity=".3" stroke="${ink}" stroke-width="1.2"/>` +
      `<path d="M12 22L24 10M14 26L28 12M18 27L29 16" stroke="${ink}" stroke-width=".6" opacity=".6"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="none" stroke="${ink}" stroke-width="1.2"/>` +
      `<path d="M38 18L46 10M38 26L52 12M44 28L52 20" stroke="${ink}" stroke-width=".6" opacity=".6"/>`,
    neon:
      `<circle cx="20" cy="18" r="10" fill="${accent}" fill-opacity=".2" stroke="${accent}" stroke-width="5" stroke-opacity=".18"/>` +
      `<circle cx="20" cy="18" r="10" fill="none" stroke="${accent}" stroke-width="1.6"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="none" stroke="${ink}" stroke-width="5" stroke-opacity=".18"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="none" stroke="${ink}" stroke-width="1.4"/>`,
    watercolour:
      `<circle cx="20" cy="18" r="10" fill="${accent}" opacity=".45"/><circle cx="21" cy="17" r="11" fill="${accent}" opacity=".18"/>` +
      `<circle cx="19" cy="19" r="9" fill="${accent}" opacity=".18"/>` +
      `<rect x="38" y="10" width="14" height="18" fill="${ink}" opacity=".45"/><rect x="37" y="11" width="15" height="18" fill="${ink}" opacity=".15"/>`,
  };
  return shapes[id] ?? shapes.clean;
}
