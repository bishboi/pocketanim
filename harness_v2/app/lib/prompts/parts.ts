/**
 * A prompt as named parts. Every call v2 makes is built this way, so the page can show the final prompt as the
 * pieces it was made of (the rules, the book's text, the plan, the goals...) and open each one, and so a change to
 * one piece is a change in one place.
 *
 * The text sent is exactly the parts joined with a blank line between them, system and user apart.
 */

export type PartKind =
  | "rules"      // how to do the job: role, rules, style
  | "book"       // the book's own text
  | "items"      // what code found in the book: headings, terms, boxes, figures
  | "goals"      // learning goals from the map
  | "plan"       // the video's story plan
  | "questions"  // the book's questions
  | "context"    // what other sections are doing, what was written before
  | "language"   // the narration language's rules
  | "choices"    // the options a model chooses from
  | "ask"        // the request itself
  | "retry";     // why the last try was sent back

export type Part = { key: string; label: string; kind: PartKind; text: string };

export type Prompt = { system: Part[]; user: Part[] };

export function part(key: string, label: string, kind: PartKind, text: string | string[]): Part {
  return { key, label, kind, text: (Array.isArray(text) ? text.join("\n") : text).trim() };
}

/** The parts joined as they are sent; empty parts are left out. */
export function render(parts: Part[]): string {
  return parts.filter((p) => p.text).map((p) => p.text).join("\n\n");
}
