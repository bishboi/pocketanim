/**
 * The Manim drawing of a figure triaged Manim: one model that reads images is shown the book's figure and writes the
 * Manim code from it, in the same call. The prompt is v1's (harness/app/lib/lecture.ts MANIM_RULES and
 * manimcoder.ts SYSTEM, "The book's figure, to rebuild exactly (every value, label and line)"), in named parts,
 * for one figure built in one scene: v1's beats, left area and picture() (the illustration model) are left out.
 */

import { part, type Part } from "./parts";

const ROLE = "You write the Manim code for ONE figure of a narrated video lecture: the book's figure (attached), rebuilt exactly " +
  "(every value, label and line), built up on the board as a teacher builds it: the frame first, then each part, then what it shows.";

const RULES = [
  "code is the body of Manim's construct(): build objects and self.play(...) them. Rules (the code is run before it is",
  "accepted, and refused with the reason when it breaks them):",
  "- Names: everything Manim exports (Polygon, Line, Arrow, Circle, Square, Rectangle, Arc, Dot, DashedLine,",
  "  MathTex, Text, VGroup, SurroundingRectangle, Create, Write, FadeIn, FadeOut, GrowArrow, Indicate,",
  "  TransformFromCopy, ReplacementTransform, TransformMatchingShapes, LaggedStart, UP, DOWN, LEFT, RIGHT, PI...)",
  "  and np. No imports, no classes, no while loops, no self.camera / self.mobjects / self.clear: only",
  "  self.play, self.wait, self.add and self.remove.",
  "- The board: x from -6.9 to 6.9, y from -3.05 to 2.85 (a title strip above, the caption below); nothing",
  "  outside it. Lay it out yourself, text never on a line.",
  "- Colours: INK for lines and text (the style's ink: it shows on dark and light boards), MUTED_INK for faint",
  '  parts, and PALETTE["ROSE"] (forces), PALETTE["GREEN"] (velocity, normal), PALETTE["GOLD"] (angles,',
  '  answers), PALETTE["RIVER"], PALETTE["TERRA"], PALETTE["TEAL"], PALETTE["VIOLET"] for bodies and highlights.',
  "  Text(..., font_size=24-32) for words; MathTex for every symbol and equation.",
  "- Animations the phone plays: Create, Write, FadeIn/FadeOut (shift= is fine), GrowArrow, DrawBorderThenFill,",
  "  Indicate, Transform, TransformFromCopy, ReplacementTransform, TransformMatchingShapes, LaggedStart,",
  "  .animate with shift, move_to, next_to, to_edge, scale, rotate, set_color, set_opacity; default rate_func.",
  "  Continuous motion works too: add_updater (always_redraw, a ValueTracker driving a DecimalNumber or a",
  "  curve) and MoveAlongPath; the phone gets it as frames of moving shapes. Remove updaters when done.",
  "- Never a map in it (no outline of a place, no lon/lat): maps are the map operations'.",
].join("\n");

const QUALITY = [
  "QUALITY: every manim picture is judged against a fine textbook diagram, and one that does not read cleanly is sent",
  "back (words under font size 20, two labels overlapping, a line running through a label):",
  "- Plan it before writing: what goes where on the board, the main subject large (use most of the 13.8 x 5.9",
  "  board), its labels beside what they name with room to spare, nothing crammed into a corner.",
  "- True geometry and science: angles at the angle they are, forces from the point they act on, rays obeying",
  "  the laws, values and units on everything the lesson names; proportions believable.",
  "- Words: Text font_size 24-32, MathTex for symbols and equations, each label next_to its part with buff",
  "  0.15-0.3, never on a line; the same size for labels of the same kind.",
  "- Colour with meaning: INK for lines and words, one PALETTE colour per kind of thing (forces ROSE, motion",
  "  GREEN, highlights GOLD), fills at fill_opacity 0.2-0.6 so lines and words stay readable.",
  "- Built as it is said: the frame first, then each part, then what it shows. The whole figure is on the board at",
  "  the end (its last frame is the figure).",
].join("\n");

export const MANIM_TOOL = {
  type: "function" as const,
  function: {
    name: "write_manim",
    description: "Save the Manim code of the figure.",
    parameters: {
      type: "object",
      properties: { code: { type: "string", description: "The body of construct(): build the figure and self.play it, part by part." } },
      required: ["code"],
      additionalProperties: false,
    },
  },
};

export function manimPrompt(x: { documentId: string; blockId: string; page: number; caption?: string; context?: string; how?: string;
  retry?: { code: string; error: string } }): { system: Part[]; user: Part[] } {
  return {
    system: [
      part("role", "Role", "rules", ROLE),
      part("rules", "Rules (names, board, colours, animations)", "rules", RULES),
      part("quality", "Quality", "rules", QUALITY),
    ],
    user: [
      part("figure", "The figure", "book", `Figure ${x.blockId} (page ${x.page + 1}): ${x.caption || "(no caption)"}`),
      ...(x.context?.trim() ? [part("context", "The book around it", "book", `The book around it:\n${x.context.trim().slice(0, 1200)}`)] : []),
      ...(x.how?.trim() ? [part("how", "Note on this figure (triage)", "items", `Note on this figure: ${x.how.trim().slice(0, 300)}`)] : []),
      part("image", "The book's figure (picture)", "book", `The book's figure, to rebuild exactly (every value, label and line): ` +
        `[attached: /api/documents/${x.documentId}/figure/${encodeURIComponent(x.blockId)}]`),
      ...(x.retry ? [part("retry", "Your last code, and why it was refused", "retry", ["YOUR LAST CODE was refused when it was run:",
        x.retry.code, "", "What was wrong:", x.retry.error, "", "Fix exactly that and keep everything else."])] : []),
      part("ask", "Request", "ask", "Write the figure's code (write_manim)."),
    ],
  };
}

/** The offline stand-in's code: the caption on a framed board, drawn as Manim would. */
export function standInManim(caption: string): string {
  const words = (caption || "figure").replace(/["\\\n]/g, " ").slice(0, 40);
  return [
    "frame = RoundedRectangle(width=8, height=4, corner_radius=0.3, color=INK)",
    'dot = Circle(radius=1, color=PALETTE["GOLD"], fill_opacity=0.4)',
    `label = Text("${words}", font_size=28, color=INK).next_to(frame, DOWN, buff=0.2)`,
    "self.play(Create(frame))",
    "self.play(DrawBorderThenFill(dot))",
    "self.play(Write(label))",
  ].join("\n");
}
