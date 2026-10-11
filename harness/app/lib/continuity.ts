/**
 * What one section's writer is told of the others, so a lecture written several sections at a time still reads and
 * looks like one lecture:
 *
 *   taughtSoFar   for the transcript: what each section already written taught (the terms it defined, the examples
 *                 and stories it used, the questions it asked the class), as the writer noted it with write_section.
 *                 A later section points back to these instead of explaining them again or reusing an example.
 *   shownSoFar    for the video: what each other section's chapters already put on screen (the book's figures, the
 *                 pictures made or drawn, the diagrams, timelines, comparisons and maps). A section builds on these
 *                 instead of drawing the same picture again.
 *
 * Both are short lists (a few hundred tokens), not the other sections' full text.
 */

import type { WrittenSection } from "./transcript";

/** At most this many notes from one section, each at most NOTE_CHARS long. */
const NOTES_PER_SECTION = 14;
const NOTE_CHARS = 90;

function clip(text: unknown, most = NOTE_CHARS): string {
  const flat = String(text ?? "").replace(/\s+/g, " ").trim();
  return flat.length > most ? `${flat.slice(0, most - 1)}…` : flat;
}

/** The writer's notes of what a section taught (write_section "taught"), cleaned: short, distinct, at most 14. */
export function taughtNotes(raw: unknown): string[] {
  const list = Array.isArray(raw) ? raw : typeof raw === "string" ? raw.split(/\n|;\s*/) : [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of list) {
    const note = clip(item).replace(/^[-*•\d.)\s]+/, "");
    const key = note.toLowerCase();
    if (note.length < 3 || seen.has(key)) continue;
    seen.add(key);
    out.push(note);
    if (out.length >= NOTES_PER_SECTION) break;
  }
  return out;
}

/** For the transcript writer: what the sections written before this one taught, section by section. */
export function taughtSoFar(prior: WrittenSection[]): string[] {
  const noted = prior.filter((w) => w.taught?.length).sort((a, b) => a.n - b.n);
  if (!noted.length) return [];
  return [
    "ALREADY TAUGHT in the sections written before this one (what each defined, the examples and stories it used, " +
      "the questions it asked). Do not explain these again or reuse their examples: when this section needs one, " +
      "point back to it in a few words (\"as we saw with ...\") and build on it.",
    ...noted.map((w) => `  Section ${w.n} "${w.title}": ${(w.taught ?? []).join("; ")}`),
  ];
}

type Op = Record<string, unknown>;

/** What one op puts on screen, in a few words (null for words-only ops: panels, facts, questions). */
function shownBy(op: Op): string | null {
  const kind = String(op.op ?? "");
  const said = (key: string) => clip(op[key], 70);
  if (kind === "figure" || (kind === "picture" && op.figure)) {
    const id = String(op.id ?? op.figure ?? "");
    return `the book's figure ${id}${op.caption ? ` ("${said("caption")}")` : ""}` +
      (Array.isArray(op.show) && op.show.length ? `, parts ${op.show.slice(0, 6).join(", ")}` : "");
  }
  if (kind === "picture" && Array.isArray(op.items)) {
    return `pictures of ${op.items.map((i) => clip((i as Op).generate ?? (i as Op).subject ?? (i as Op).figure ??
      (i as Op).caption, 50)).filter(Boolean).join(", ")}`;
  }
  if (kind === "picture" || kind === "illustration" || kind === "photo") {
    const what = op.generate ?? op.illustration ?? op.subject ?? op.query ?? op.draw;
    if (!what) return null;
    if (!op.draw && (op.generate || op.illustration)) {
      return `a picture made of "${clip(what, 120)}"` +
        (Array.isArray(op.labels) && op.labels.length ? ` (labelled ${op.labels.slice(0, 6).join(", ")})` : "");
    }
    return `${op.draw ? "a drawing" : "a picture"} of ${clip(what, 80)}` +
      (Array.isArray(op.labels) && op.labels.length ? ` (labelled ${op.labels.slice(0, 6).join(", ")})` : "");
  }
  if (kind === "draw") return `a drawing of ${clip(op.what ?? op.description, 80)}`;
  if (kind === "gallery" && Array.isArray(op.items)) {
    return `pictures of ${op.items.map((i) => clip((i as Op).generate ?? (i as Op).subject ?? (i as Op).query ??
      (i as Op).figure, 50)).filter(Boolean).join(", ")}`;
  }
  if (kind === "diagram") {
    const nodes = Array.isArray(op.nodes) ? op.nodes.map((n) => clip((n as Op).label ?? (n as Op).id, 30)) : [];
    return `diagram "${String(op.id ?? "")}"${op.title ? ` ("${said("title")}")` : ""}${op.kind ? ` (${String(op.kind)})` : ""}` +
      (nodes.length ? `: ${nodes.slice(0, 7).join(", ")}${nodes.length > 7 ? ", ..." : ""}` : "");
  }
  if (kind === "timeline") {
    const events = Array.isArray(op.events) ? op.events.map((e) => Array.isArray(e) ? `${e[0]} ${clip(e[1], 30)}`
      : clip((e as Op).date ?? (e as Op).label, 30)) : [];
    return `a timeline${op.title ? ` "${said("title")}"` : ""}: ${events.slice(0, 6).join(", ")}`;
  }
  if (kind === "compare" && Array.isArray(op.columns)) {
    return `a comparison of ${op.columns.map((c) => clip((c as Op).title, 30)).join(" / ")}`;
  }
  if (kind === "journey" && Array.isArray(op.stops)) {
    return `a journey on the map: ${op.stops.map((s) => (typeof s === "string" ? s : "a point")).slice(0, 6).join(" → ")}`;
  }
  if (kind === "marker" && op.place) return `the place ${clip(op.place, 40)} marked on the map`;
  if (kind === "state" && op.name) return `${clip(op.name, 40)} filled on the map`;
  if (["sketch", "graph", "plot", "process", "molecule", "equation", "preset", "sim"].includes(kind)) {
    const what = op.title ?? op.label ?? op.name ?? op.preset ?? op.id ?? op.tex ?? op.expr;
    return what ? `a ${kind} of ${clip(what, 60)}` : null;
  }
  return null;
}

/** What one section's chapters showed, distinct, in order. */
export function visualsOf(script: unknown): string[] {
  const chapters = ((script as { chapters?: { beats?: { do?: unknown[] }[] }[] })?.chapters ?? []);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const chapter of chapters) {
    for (const beat of chapter.beats ?? []) {
      for (const op of beat.do ?? []) {
        if (!op || typeof op !== "object") continue;
        const what = shownBy(op as Op);
        if (!what || seen.has(what)) continue;
        seen.add(what);
        out.push(what);
      }
    }
  }
  return out;
}

/** For the video writer: what the other sections' chapters (those written so far) already put on screen. */
export function shownSoFar(done: Map<number, unknown>, except: number, most = 18): string[] {
  const rows = [...done.entries()].filter(([n]) => n !== except).sort((a, b) => a[0] - b[0])
    .map(([n, script]) => [n, visualsOf(script).slice(0, most)] as const)
    .filter(([, shown]) => shown.length);
  if (!rows.length) return [];
  return [
    "ALREADY ON SCREEN in the other sections' videos (written so far). Do not draw these again: a picture or diagram " +
      "the class has seen is pointed back to in words, or shown again only to explain something new in it (then " +
      "reveal only the parts this section explains). A book figure already shown elsewhere is shown here only if " +
      "this section's text is about it. Choose new pictures for what is new here. To show a person, place or thing " +
      "already pictured, give the very same \"generate\" words as before: the picture already made is used again.",
    ...rows.map(([n, shown]) => `  Section ${n}: ${shown.join("; ")}`),
  ];
}
