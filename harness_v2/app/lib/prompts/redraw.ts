/**
 * The redraw prompt, in named parts so the page can show each; sent as one paragraph (the parts joined by a
 * space), with the book's figure attached as the reference image. It began as v1's (harness/lecture/genimage.py
 * redraw_prompt, its `faithful` form) and differs in two ways:
 *
 *   - NO TEXT in the image: every label, word and number is left out and its place left clear, so labels can be
 *     put on it later (as the lecture engine does, synced to the words);
 *   - gentler words: image models' moderation (Azure's, for one) blocks requests that read as copying a picture
 *     ("exact copy", "looks just like it", "textbook"), so it asks for an original illustration based on a sketch.
 *
 * When a model's moderation still blocks it, it is asked again in gentler words (`gentle`: no book text, a simple
 * school illustration), then with no reference image at all (`blind`: drawn from what the figure shows, in words).
 *
 * Styled redraws use the same prompt for now: the styled form needs a lecture's template look (its art style, ink
 * and palette), and v2 has no templates yet.
 */

import { part, type Part } from "./parts";

export type RedrawLevel = "full" | "gentle" | "blind";
export const REDRAW_LEVELS: RedrawLevel[] = ["full", "gentle", "blind"];

export type RedrawInput = {
  /** What the figure shows: its caption, else what the figures step saw in it. */
  caption: string;
  /** What the figures step saw in it (for the blind try, which has no picture to go by). */
  description?: string;
  /** What it is for in the lecture (its lecture and goals, the book's words around it). */
  context?: string;
  /** The triage's note on how to redraw it (the chat model's; a decision model gives none). */
  how?: string;
  /** The colour it stands on when it has no background of its own (v1: the template's board, #0D1117 by default). */
  background?: string;
  level?: RedrawLevel;
};

const NO_TEXT = "NO TEXT AT ALL in the picture: no labels, words, letters, numbers, captions, titles or marks. Where the sketch " +
  "has a label, leave that spot clear and plain, so a label can be placed on it later.";

export function redrawParts(x: RedrawInput): Part[] {
  const what = (x.caption.trim() || "a school diagram").slice(0, 160);
  // v1's board colour when a lecture has no style of its own (its default template, atlas); V2_REDRAW_BACKGROUND
  // changes it.
  const bg = x.background || process.env.V2_REDRAW_BACKGROUND || "#0D1117";
  if (x.level === "blind") {
    const shows = (x.description?.trim() || what).slice(0, 600);
    return [
      part("task", "Request (no reference: the picture was blocked)", "ask", "Draw a simple, friendly educational illustration for a school lesson."),
      part("what", "What it shows (the figure, in words)", "items", `It shows: ${shows}`),
      part("notext", "No text", "rules", NO_TEXT),
      part("background", "Background", "rules", `A plain, flat ${bg} background; only the illustration, no frame.`),
    ];
  }
  if (x.level === "gentle") {
    return [
      part("task", "Request (gentle: the full one was blocked)", "ask", "Draw a simple, friendly educational illustration for a school lesson, " +
        "using the attached sketch as a guide for its layout and parts."),
      part("what", "What it shows (caption)", "book", `It shows: ${what}.`),
      part("notext", "No text", "rules", NO_TEXT),
      part("background", "Background", "rules", `A plain, flat ${bg} background; only the illustration, no frame.`),
    ];
  }
  return [
    part("task", "Request", "ask", "Create an original, clean educational illustration for a school video lesson, based on the attached " +
      "sketch."),
    part("what", "What it shows (caption)", "book", `It shows: ${what}.`),
    ...(x.context?.trim() ? [part("context", "What it is for (lecture, goals, book text)", "context", `It is used to teach: ${x.context.trim().slice(0, 500)}`)] : []),
    ...(x.how?.trim() ? [part("how", "Note on this figure (triage)", "items", `Note on this figure: ${x.how.trim().slice(0, 300)}`)] : []),
    part("keep", "Keep its layout and look", "rules", "Follow the sketch closely: the same layout, the same parts in the same places and " +
      "proportions, every arrow, line and connection, and its drawing style, colours and level of detail. Nothing added, " +
      "nothing left out, nothing rearranged."),
    part("notext", "No text", "rules", NO_TEXT),
    part("clean", "Clean and clear", "rules", "Make it sharp and clear, readable on a phone, without blur, grain, stains or uneven light. " +
      "Show only the illustration itself: no page, border, frame or anything around it."),
    part("background", "Background and frame", "rules", `If it has no background of its own, it stands on a single plain, flat colour ${bg} ` +
      "filling the rest of the image edge to edge, with no card or shadow; if it has one (a scene, a microscope field), keep it. " +
      "Fill the frame with the illustration."),
  ];
}

/** The prompt as sent: one paragraph. */
export function redrawText(parts: Part[]): string {
  return parts.map((p) => p.text).join(" ");
}

/** An image model's refusal by its moderation or content filter (asked again in gentler words). */
export const BLOCKED = /moderat|content (filter|policy)|safety|blocked|flagged|not allowed|violat|refus/i;
