/**
 * The SVG drawing of a figure triaged SVG: one model that reads images is shown the book's figure and writes the SVG
 * from it, in the same call (no other model describes it first). The prompt is v1's (harness/app/lib/figures.ts
 * SVG_PROMPT and SVG_RULES, as they were before v1 dropped SVG drawing in 506360a), in named parts, without its two
 * ways out (PHOTO, MANIM: the triage has decided) and without its review round.
 *
 * Colours are v1's names (INK, MUTED, ROSE...), so a drawing suits any board; the page shows it on v1's default board
 * (atlas), with the names put in as that board's colours. Code checks the SVG against v1's rules and asks once
 * more with what broke them.
 */

import { part, type Part } from "./parts";

/** v1's atlas board: its palette, and the names the SVG rules add (pocket_lecture.py, 506360a~1). */
const ATLAS = { SAND: "#E3B25A", DUNE: "#C9793A", TERRA: "#B5523B", RUST: "#8E3B2E", TEAL: "#3FB8AF", RIVER: "#5AB4F0",
  GREEN: "#86B86A", OLIVE: "#6E8B3D", CREAM: "#F4E9D8", MUTED: "#8A93A6", ROSE: "#E06C75", GOLD: "#F2C14E", VIOLET: "#A78BFA",
  HI: "#FFFFFF", MOUNT: "#C9D3E0" };
export const BOARD_BG = "#0D1117";
export const PALETTE: Record<string, string> = { ...ATLAS, INK: ATLAS.CREAM, BOARD: BOARD_BG, SHINE: "#FFFFFF", SHADE: "#000000" };

const RULES = [
  "RULES (a checker reads it the way the board draws it, and sends back what breaks them):",
  '- <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 H">, width 800, H to suit the figure (300-600).',
  "- Elements: g, path, rect, circle, ellipse, line, polyline, polygon, text, tspan, and for animation animate and",
  "  animateTransform. NOT image, style, filter, mask, clipPath, pattern, gradients, foreignObject or script.",
  "- Colours by NAME, not hex, so the drawing suits a dark or a light board: INK (lines and words), MUTED (faint",
  "  guides, axes, dashed construction lines), ROSE (forces), GREEN (velocities, normals), GOLD (angles, highlights),",
  "  RIVER (water, blue things), TERRA, TEAL, VIOLET, SAND, DUNE, RUST, OLIVE, MOUNT (fills: fill-opacity 0.3-0.8),",
  "  SHINE (highlights) and SHADE (shadows), both at fill-opacity 0.15-0.35, BOARD (the board itself: to blank out",
  "  a wire behind a symbol drawn over it).",
  '  fill="none" for open outlines. Main lines 3-5 wide, detail lines 1-2.',
  "- Labels: <text> at font-size 24-34 with text-anchor, plain Unicode for symbols (θ, μ, ₁, ², →, Ω, °), never",
  "  LaTeX; beside what they name, never on top of a line. No title or caption text: the lecture shows the caption.",
  '- PARTS: wrap each thing the teacher will point at in <g id="...">: a short id in letters, digits and _ (block,',
  "  mg, normal, theta, battery, r1, nucleus, xylem), each label inside the group of the thing it names. Every",
  "  visible thing belongs to a part. Ids are unique.",
  "- ANIMATION ONLY IF IT TEACHES: only when the figure shows a process or motion (current flowing round a",
  "  circuit, blood through the heart, a wave travelling, a planet in orbit, a piston pushing, particles moving,",
  "  water evaporating). A structure, an apparatus at rest, a graph or a labelled organ stays still: no animation.",
  '  When it moves, put SMIL inside the moving part: <animateTransform attributeName="transform" type="translate"',
  '  (or rotate, scale) values="0 0; 40 0; 0 0" dur="2s" repeatCount="indefinite" additive="sum"/>, <animate',
  '  attributeName="opacity" .../>, or a dashed path (stroke-dasharray) with <animate attributeName="stroke-dashoffset"',
  '  values="0; -40" .../> for something flowing along a line. dur 0.5s, 1s, 2s or 4s; repeatCount="indefinite".',
  "  Animate transforms and opacity only (not d, width or points).",
  "- Under 70 KB, no comments.",
].join("\n");

const QUALITY = [
  "QUALITY (it is shown full screen to a class, on a phone, and judged against a good textbook figure):",
  "- Plan the layout before writing: where each thing goes on a grid, its size, where each label sits. Then write",
  "  coordinates that follow the plan. Use the whole viewBox with a margin of 30 or more on every side; the main",
  "  subject large and central; nothing crammed into a corner, nothing touching the edge.",
  "- Correct geometry and science: angles drawn at the angle they are (30° looks like 30°), forces from the point",
  "  they act on and in their true direction, perpendiculars perpendicular, parallel lines parallel, rays obeying",
  "  the laws of reflection and refraction, circuits closed, proportions believable.",
  "- Arrows: a line plus a filled triangle head (a polygon about 18 long and 14 wide) at the exact end, pointing",
  "  along the line; never <marker>. Force arrows long enough to read (80+).",
  "- Labels: every label clear of every line, arrow and other label (leave 8+ units of space); a leader line",
  "  (MUTED, thin) from a label to a small part when it cannot sit right beside it; the same size for labels of the",
  "  same kind; never upside down or rotated.",
  "- Consistent style: the same line width for the same kind of thing, a few colours with a meaning each (forces",
  "  one colour, motion another), fills light (fill-opacity 0.3-0.6) so lines and labels stay readable on top.",
  "- Smooth shapes: real curves (arcs, cubic Béziers) for round things, not jagged polylines.",
].join("\n");

const DETAIL = [
  "DETAIL (it is judged against a fine textbook illustration, not a sketch; aim for 60-200 shapes):",
  "- Depth without gradients: build each solid thing in layers: its base fill (fill-opacity 0.5-0.8), a shadow",
  "  shape along its lower or far side in the next darker colour of its family (SAND→DUNE→TERRA→RUST,",
  "  GREEN→OLIVE, RIVER→TEAL, or SHADE at fill-opacity 0.15-0.3), and a highlight shape on its lit side (SHINE at",
  "  fill-opacity 0.2-0.35). Light comes from the top left for every part.",
  "- Texture and structure: the real surface of a thing in fine lines (1-2 wide, MUTED or a darker shade): a leaf's",
  "  veins, muscle fibres, bark, brick courses, rock strata, a membrane's double line, cell walls, a wire's",
  "  insulation, screw threads, water ripples, fur, scales. A cross-section shows its layers, each a distinct fill.",
  "- The small features that make it recognisable and true: organelles inside a cell (ribosomes as dots, cristae",
  "  inside mitochondria), stomata on a leaf, valves in the heart, terminals and a filament in a bulb, rivets,",
  "  teeth on a gear, the meniscus in a tube, graduations on a scale. Several of each where the real thing has many.",
  "- Outlines: a firm outline (3-5 wide) round each main thing, thinner lines (1-2) for detail inside it.",
  "- Still clear: detail sits inside and on things, never across labels or arrows; the thing being taught stays",
  "  the strongest shape in the picture, and every label still has room.",
].join("\n");

const EDUCATIONAL = [
  "EDUCATIONAL (it teaches; it is not decoration):",
  "- Label every part the lesson names with the exact term students must learn (the textbook's word), and the key",
  "  values with their units (2 kg, 30°, 5 Ω, 10 m/s).",
  "- Make the idea being taught stand out: the part the lesson is about drawn largest or in the highlight colour,",
  "  the rest quieter (MUTED or thin) so the eye goes where the teacher points.",
  "- Show cause, direction and flow with arrows (what pushes what, which way blood, current, light, energy goes).",
  "- True to a good textbook: correct relative sizes and positions (the nucleus inside the cell, the left ventricle's",
  "  wall thicker than the right's), nothing scientifically wrong even if simplified.",
  "- One clear idea per picture: detail that makes the subject real and true, but no unrelated background scenery,",
  "  no faces, no parts the lesson never uses.",
].join("\n");

export const SVG_TOOL = {
  type: "function" as const,
  function: {
    name: "draw_svg",
    description: "Save the SVG drawing of the figure.",
    parameters: {
      type: "object",
      properties: {
        svg: { type: "string", description: "The whole SVG, <svg ...> to </svg>." },
        parts: { type: "array", items: { type: "string" }, description: "The ids of its parts (<g id>), in the order a teacher would point at them." },
      },
      required: ["svg", "parts"],
      additionalProperties: false,
    },
  },
};

export function svgPrompt(x: { documentId: string; blockId: string; page: number; caption?: string; context?: string; how?: string; retry?: string[] }):
  { system: Part[]; user: Part[] } {
  return {
    system: [
      part("role", "Role", "rules", "You redraw ONE figure from a textbook as a detailed, clean SVG illustration for a teacher's board in a " +
        "video lecture. You see the figure itself (attached): draw it from what you see."),
      part("what", "What to draw", "rules", "WHAT TO DRAW: what the figure shows and teaches: the same parts, labels, arrows, numbers and layout, " +
        "cleaner, as a good teacher draws on a board."),
      part("rules", "Rules (SVG, colours, parts, animation)", "rules", RULES),
      part("quality", "Quality", "rules", QUALITY),
      part("detail", "Detail", "rules", DETAIL),
      part("educational", "Educational", "rules", EDUCATIONAL),
    ],
    user: [
      part("figure", "The figure", "book", `Figure ${x.blockId} (page ${x.page + 1}): ${x.caption || "(no caption)"}`),
      ...(x.context?.trim() ? [part("context", "The book around it", "book", `The book around it:\n${x.context.trim().slice(0, 1200)}`)] : []),
      ...(x.how?.trim() ? [part("how", "Note on this figure (triage)", "items", `Note on this figure: ${x.how.trim().slice(0, 300)}`)] : []),
      part("image", "The figure (picture)", "book", `[the picture is attached: /api/documents/${x.documentId}/figure/${encodeURIComponent(x.blockId)}]`),
      ...(x.retry?.length ? [part("retry", "What broke the rules last time", "retry", ["Your last SVG broke these rules; draw it again with them fixed:",
        ...x.retry.map((r) => `- ${r}`)])] : []),
      part("ask", "Request", "ask", "Draw it as the SVG (draw_svg)."),
    ],
  };
}

const FORBIDDEN = new Set(["image", "style", "filter", "mask", "clipPath", "pattern", "linearGradient", "radialGradient", "foreignObject", "script", "marker"]);
const ALLOWED = new Set(["svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "animate", "animateTransform", "title", "desc"]);
const COLOUR_ATTR = /\b(fill|stroke|stop-color|color)\s*=\s*"([^"]+)"/g;

/** What breaks v1's rules in an SVG; the svg cleaned of anything that would run (scripts, handlers, links). */
export function checkSvg(raw: string): { svg: string; problems: string[]; parts: string[]; shapes: number; animated: boolean } {
  const problems: string[] = [];
  const at = raw.indexOf("<svg");
  const end = raw.lastIndexOf("</svg>");
  let svg = at >= 0 && end > at ? raw.slice(at, end + 6) : raw;
  if (at < 0 || end < 0) problems.push("no <svg>…</svg> in the answer");
  svg = svg.replace(/<!--[\s\S]*?-->/g, "").replace(/\son\w+\s*=\s*"[^"]*"/gi, "").replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/(xlink:)?href\s*=\s*"(?!#)[^"]*"/gi, "");
  if (!/viewBox\s*=\s*"0 0 800 \d+(\.\d+)?"/.test(svg)) problems.push('the viewBox is not "0 0 800 H"');
  const tags = [...new Set([...svg.matchAll(/<\s*([a-zA-Z][\w:-]*)/g)].map((m) => m[1]))];
  const bad = tags.filter((t) => FORBIDDEN.has(t));
  if (bad.length) problems.push(`elements not allowed: ${bad.join(", ")}`);
  const unknown = tags.filter((t) => !ALLOWED.has(t) && !FORBIDDEN.has(t));
  if (unknown.length) problems.push(`elements not in the rules: ${unknown.join(", ")}`);
  const hex = [...new Set([...svg.matchAll(COLOUR_ATTR)].map((m) => m[2]).filter((c) => /^#|^rgb/i.test(c)))];
  if (hex.length) problems.push(`colours by hex, not by name: ${hex.slice(0, 6).join(", ")}`);
  const names = [...new Set([...svg.matchAll(COLOUR_ATTR)].map((m) => m[2]).filter((c) => /^[A-Z]+$/.test(c) && !PALETTE[c]))];
  if (names.length) problems.push(`colour names not in the palette: ${names.join(", ")}`);
  const ids = [...svg.matchAll(/<g\b[^>]*\sid\s*=\s*"([^"]+)"/g)].map((m) => m[1]);
  if (!ids.length) problems.push('no parts: wrap each thing in <g id="...">');
  const twice = ids.filter((id, i) => ids.indexOf(id) !== i);
  if (twice.length) problems.push(`part ids used twice: ${[...new Set(twice)].join(", ")}`);
  if (svg.length > 70_000) problems.push(`${Math.round(svg.length / 1024)} KB: over 70 KB`);
  const shapes = (svg.match(/<(path|rect|circle|ellipse|line|polyline|polygon)\b/g) ?? []).length;
  return { svg, problems, parts: ids, shapes, animated: /<animate/i.test(svg) };
}

/** The SVG as v1's default board shows it: colour names put in as its colours, on its board colour. */
export function onBoard(svg: string): string {
  const coloured = svg.replace(COLOUR_ATTR, (all, attr, value) => (PALETTE[value] ? `${attr}="${PALETTE[value]}"` : all))
    .replace(/(fill|stroke)\s*:\s*([A-Z]+)/g, (all, attr, value) => (PALETTE[value] ? `${attr}:${PALETTE[value]}` : all));
  // The board behind it, as the first thing drawn.
  return coloured.replace(/<svg\b([^>]*)>/, `<svg$1><rect x="-2000" y="-2000" width="6000" height="6000" fill="${BOARD_BG}"/>`);
}

/** An offline stand-in's drawing: a framed sketch of the figure with one labelled part. */
export function standInSvg(caption: string): string {
  const label = (caption || "figure").replace(/[<&>"]/g, "").slice(0, 40);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400"><g id="subject"><rect x="200" y="80" width="400" height="220" rx="24" fill="RIVER" fill-opacity="0.4" stroke="INK" stroke-width="4"/>` +
    `<circle cx="400" cy="190" r="60" fill="GOLD" fill-opacity="0.6" stroke="INK" stroke-width="3"/></g>` +
    `<g id="label"><text x="400" y="350" font-size="28" text-anchor="middle" fill="INK">${label}</text></g></svg>`;
}
