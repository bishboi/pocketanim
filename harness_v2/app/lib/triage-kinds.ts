/**
 * The ways a book's figure can be shown in a video lecture: what the figure triage chooses from. Plain data (the page
 * reads it too): the user picks which of these a run may use, and only those are offered to the model.
 *
 * The first four are v1's (harness/app/lib/figures.ts CLASSIFY_PROMPT); svg, photo, book and skip are the routes v1
 * had elsewhere (detailed SVG drawings, a photograph found again by image search, page furniture left out), offered
 * here as choices of their own.
 */

export type TriageKind = "manim" | "map" | "exact" | "styled" | "svg" | "photo" | "book" | "skip";

export type TriageChoice = {
  key: TriageKind;
  /** Its name on the page. */
  label: string;
  /** One line for the page. */
  short: string;
  /** What the model is told it means: when to choose it, and what then happens to the figure. */
  prompt: string;
  /** Offered unless the user turns it off. */
  on: boolean;
  /** Its colour on the page (the PDF's boxes and the badges). */
  color: string;
};

export const TRIAGE_CHOICES: TriageChoice[] = [
  {
    key: "manim", label: "Manim", on: true, color: "rgba(56, 189, 248, 0.45)",
    short: "Rebuilt exactly with the board's own shapes: graphs, charts, constructions, circuits, flowcharts, tables.",
    prompt: "MANIM: the board's own shapes can build it EXACTLY, every value, label and line in place: a graph or plot of a " +
      "function or of data, a bar, line or pie chart, a number line, a coordinate or geometric construction (triangles, " +
      "circles, angles), a vector or force diagram, a ray diagram, a circuit schematic, a block on an incline, a pulley, " +
      "a spring, a pendulum, a flowchart, a cycle or tree of labelled boxes, a table, a Venn diagram, a Punnett square. " +
      "It is rebuilt there, exact and drawn part by part.",
  },
  {
    key: "map", label: "Map", on: true, color: "rgba(74, 222, 128, 0.45)",
    short: "A map of a real place: built with the lecture's map engine (places, borders, rivers, routes).",
    prompt: "MAP: a map of a real place (countries, states, rivers, routes, trade or migration, an empire, places marked). " +
      "It is built with the lecture's own map, every place, border, route and label of the book's.",
  },
  {
    key: "exact", label: "Exact redraw", on: true, color: "rgba(250, 204, 21, 0.45)",
    short: "Redrawn close to the book's own look: anatomy, specimens, apparatus, artworks, sources.",
    prompt: "EXACT: it must look as it does in the book, because its look is what is taught: an anatomy or specimen " +
      "drawing, a microscope view, a real apparatus or set-up, a rock, mineral or organism, an artwork, a coin, " +
      "inscription or historical source. Redrawn by an image model close to the book's own drawing, colours and detail, " +
      "only cleaned up, not restyled.",
  },
  {
    key: "styled", label: "Styled redraw", on: true, color: "rgba(244, 114, 182, 0.45)",
    short: "Redrawn in the lecture's art style, same parts and labels: schematic illustrations, cartoons, scenes.",
    prompt: "STYLED: any other picture: a schematic illustration, a labelled diagram whose look is not the point, a cartoon " +
      "or scene. Redrawn by an image model in the lecture's own art style, the same parts and labels.",
  },
  {
    key: "svg", label: "SVG drawing", on: false, color: "rgba(167, 139, 250, 0.45)",
    short: "Drawn as a detailed vector drawing whose parts can be revealed and labelled one by one.",
    prompt: "SVG: a labelled diagram of parts (a cell, an organ, a machine, a layered structure, a cross-section) that is " +
      "best drawn as a detailed vector drawing, each part its own shape so it can be revealed, highlighted and labelled " +
      "one at a time while the teacher speaks of it.",
  },
  {
    key: "photo", label: "Photo search", on: false, color: "rgba(251, 146, 60, 0.45)",
    short: "A real photograph: the same subject found again by image search (with its licence), not redrawn.",
    prompt: "PHOTO: a real photograph of a real thing, person, place or event, whose being real is the point. The same " +
      "subject is found again by image search, with its licence, and shown as a photograph.",
  },
  {
    key: "book", label: "Book's picture", on: false, color: "rgba(45, 212, 191, 0.45)",
    short: "Shown as the book's own picture, cropped, unchanged.",
    prompt: "BOOK: shown as the book's own picture, cropped from the page and unchanged, because nothing else would do " +
      "(choose this only when it cannot be rebuilt or redrawn without losing what it teaches).",
  },
  {
    key: "skip", label: "Leave out", on: true, color: "rgba(148, 163, 184, 0.45)",
    short: "Not teaching: a logo, QR code, decoration, page furniture. Left out of the lecture.",
    prompt: "SKIP: not part of the teaching: a publisher's logo, a QR code, an icon, a decoration, a page ornament, an " +
      "advertisement. It is left out of the lecture.",
  },
];

export const DEFAULT_KINDS: TriageKind[] = TRIAGE_CHOICES.filter((c) => c.on).map((c) => c.key);
export const choiceOf = (k?: string) => TRIAGE_CHOICES.find((c) => c.key === k);

/**
 * The decision model's instructions for the triage, in v1's words (harness/app/lib/figures.ts CLASSIFY_PROMPT): its
 * framing, the ways offered each as v1 describes it, and its rule between EXACT and STYLED. v1's reply format
 * ("KIND | HOW") is left out: a decision model only chooses (each way is also its criterion).
 */
export function triageInstructions(kinds: TriageKind[]): string {
  return [
    "You look at ONE figure from a textbook (the picture in the state) and decide how a video lecture should best show it: " +
      "by what matters in it, what must stay exactly as it is, and what may change.",
    "Choose exactly one of these ways:",
    ...kinds.map((k) => `- ${choiceOf(k)!.prompt}`),
    ...(kinds.includes("exact") && kinds.includes("styled") ? ["When in doubt between EXACT and STYLED, EXACT."] : []),
    ...(kinds.includes("book") ? [] : ["The book's own picture is never shown as it is: choose how it is rebuilt or redrawn."]),
    "If no way fits well, choose the closest.",
  ].join("\n");
}
