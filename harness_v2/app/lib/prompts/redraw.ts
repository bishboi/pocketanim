/**
 * The redraw prompt: v1's (harness/lecture/genimage.py redraw_prompt, its `faithful` form), word for word, cut into
 * the named parts it is made of so the page can show each. It is sent as v1 sent it: the parts joined by a space,
 * one paragraph, with the book's figure attached as the reference image.
 *
 * Styled redraws use it too for now: the styled prompt needs a lecture's template look (its art style, ink and
 * palette), and v2 has no templates yet.
 *
 * Its words are v1's on purpose: "exact copy", "textbook", "watermark" or "logo" make image models' content filters
 * block the request as copying, so the figure is asked for as a clean new version of a reference image.
 */

import { part, type Part } from "./parts";

export type RedrawInput = {
  /** What the figure shows: its caption, else what the figures step saw in it. */
  caption: string;
  /** What it is for in the lecture (its lecture and goals, the book's words around it). */
  context?: string;
  /** The triage's note on how to redraw it (the chat model's; a decision model gives none). */
  how?: string;
  /** The colour it stands on when it has no background of its own (v1: the template's board, #0D1117 by default). */
  background?: string;
  /** Asked again in the plainest words, when an image model's filter blocked the full prompt (v1's `plain`). */
  plain?: boolean;
};

export function redrawParts(x: RedrawInput): Part[] {
  const what = (x.caption.trim() || "a figure").slice(0, 160);
  if (x.plain) {
    return [part("task", "Request (plain: the full one was blocked)", "ask",
      `An educational figure for a school lesson: ${what}. Make a clean, sharp version of the attached reference image that ` +
      "looks just like it: the same drawing, colours, parts and labels. Only the figure itself.")];
  }
  // v1's board colour when a lecture has no style of its own (its default template, atlas); V2_REDRAW_BACKGROUND
  // changes it.
  const bg = x.background || process.env.V2_REDRAW_BACKGROUND || "#0D1117";
  return [
    part("task", "Request", "ask", "Make a clean, sharp version of the attached REFERENCE IMAGE for a video lesson that LOOKS JUST LIKE IT: " +
      "what it shows is taught by how it looks."),
    part("what", "What it shows (caption)", "book", `What it shows: ${what}.`),
    ...(x.context?.trim() ? [part("context", "What it is for (lecture, goals, book text)", "context", `WHAT IT IS FOR: ${x.context.trim().slice(0, 500)}`)] : []),
    ...(x.how?.trim() ? [part("how", "Note on this figure (triage)", "items", `NOTE ON THIS FIGURE: ${x.how.trim().slice(0, 300)}`)] : []),
    part("keep", "Keep its own look", "rules", "KEEP ITS OWN LOOK: the same drawing style, colours, shading, textures, proportions and fine detail, " +
      "the same layout, every part in its place, every arrow and line, every number and unit, and EVERY LABEL " +
      "with the same words and spelling beside the same part. Do NOT restyle it, simplify it, recolour it or " +
      "add anything. If it is a photograph, keep it photographic and true."),
    part("clean", "Only clean it", "rules", "ONLY CLEAN IT: sharp and clear, labels crisp and readable on a phone, without blur, grain, stains, " +
      "yellowed paper or uneven light, and show only the figure itself: leave out everything around it that is not " +
      "part of it (any page, border, caption, figure number, title, page number, stamp, mark or stray text)."),
    part("background", "Background and frame", "rules", `If the figure has no background of its own, it stands on a single plain, flat colour ${bg} ` +
      "filling the rest of the image edge to edge, no frame, card or shadow; if it has one (a photograph, a " +
      "scene, a microscope field), keep it. Fill the frame with the figure."),
  ];
}

/** The prompt as sent: v1's one paragraph. */
export function redrawText(parts: Part[]): string {
  return parts.map((p) => p.text).join(" ");
}
