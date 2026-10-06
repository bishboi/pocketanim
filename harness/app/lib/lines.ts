/**
 * The video's narration by reference to the transcript's sentences, not copied out again.
 *
 * Once the transcript is written, the video's beat script said every sentence of it again, word for word, in
 * its "say" fields: about half of what the slowest stage wrote was a copy of text that already existed, and a
 * copy that slipped (a word changed, a sentence merged) was refused and the whole section written again. Now each
 * section's sentences are numbered (numberedSection), a beat names the ones it says ({"lines": [12, 13]}), and the
 * words are filled in here (fillLines), before anything checks or compiles the script. A sentence no beat names is
 * not a refusal either: it is said on a beat of its own, without a picture, where it belongs in the order.
 */

import type { WrittenSection } from "./transcript";

/** A section's sentences in order, as they are numbered for the video (1-based in the prompt). */
export function linesOf(text: string): string[] {
  return text
    .split(/(?<=[.?!।])\s+|\n+/)
    .map((s) => s.trim())
    .filter((s) => /[\p{L}\p{N}]/u.test(s));
}

/** A section's transcript as the video's writer sees it: one numbered sentence a line ("12| ..."). */
export function numberedSection(section: WrittenSection): string {
  return linesOf(section.text).map((line, i) => `${i + 1}| ${line}`).join("\n");
}

type Beat = { say?: unknown; lines?: unknown; do?: unknown[] } & Record<string, unknown>;
type Chapter = { section?: unknown; beats?: Beat[]; title?: unknown } & Record<string, unknown>;

/** A beat's "lines" as numbers: 12, [12, 13], "12-13", "12, 13". */
function numbersOf(value: unknown): number[] {
  const out: number[] = [];
  const add = (v: unknown) => {
    if (typeof v === "number" && Number.isFinite(v)) out.push(Math.round(v));
    else if (typeof v === "string") {
      for (const part of v.split(/[,\s]+/).filter(Boolean)) {
        const range = /^(\d+)\s*[-–]\s*(\d+)$/.exec(part);
        if (range) {
          const [a, b] = [Number(range[1]), Number(range[2])];
          for (let n = a; n <= b && n - a < 6; n++) out.push(n);
        } else if (/^\d+$/.test(part)) out.push(Number(part));
      }
    }
  };
  if (Array.isArray(value)) value.forEach(add);
  else add(value);
  return out;
}

export type FillReport = {
  /** Beats that named lines their section does not have. */
  problems: string[];
  /** Sentences no beat named, said on beats of their own. */
  added: number;
  /** Chapters with too few beats, merged into the chapter before (or after) them. */
  merged: number;
};

/**
 * The script with every beat's "lines" turned into its "say", in place. For the sections in `complete` (the ones
 * this script is meant to say in full), a sentence no beat names is added on a beat of its own after the beat
 * before it, and a chapter of fewer than `minBeats` beats is merged into its neighbour of the same section.
 */
export function fillLines(
  script: unknown,
  written: WrittenSection[],
  options: { complete?: number[]; minBeats?: number } = {},
): FillReport {
  const report: FillReport = { problems: [], added: 0, merged: 0 };
  const chapters = ((script as { chapters?: unknown })?.chapters ?? []) as Chapter[];
  if (!Array.isArray(chapters)) return report;
  const lines = new Map(written.map((w) => [w.n, linesOf(w.text)]));
  // Which line each beat says, by section, for the sentences left out.
  const said = new Map<number, Set<number>>();
  chapters.forEach((chapter, ci) => {
    const n = Number(chapter?.section);
    const own = lines.get(n);
    for (const [bi, beat] of (Array.isArray(chapter?.beats) ? chapter.beats : []).entries()) {
      if (!beat || typeof beat !== "object" || beat.lines === undefined) continue;
      const numbers = numbersOf(beat.lines);
      delete beat.lines;
      if (!own) {
        report.problems.push(`chapter ${ci + 1} beat ${bi + 1}: "lines" needs its chapter's "section" (a transcript section number)`);
        continue;
      }
      const bad = numbers.filter((k) => k < 1 || k > own.length);
      if (bad.length || !numbers.length) {
        report.problems.push(`chapter ${ci + 1} beat ${bi + 1}: line${bad.length > 1 ? "s" : ""} ${bad.join(", ") || "(none)"} ` +
          `not in section ${n}, which has lines 1-${own.length}`);
      }
      const good = numbers.filter((k) => k >= 1 && k <= own.length);
      if (good.length) {
        beat.say = good.map((k) => own[k - 1]).join(" ");
        const set = said.get(n) ?? new Set<number>();
        good.forEach((k) => set.add(k));
        said.set(n, set);
      }
    }
  });
  for (const n of options.complete ?? []) {
    const own = lines.get(n);
    if (!own) continue;
    const mine = chapters.filter((c) => Number(c?.section) === n && Array.isArray(c.beats));
    if (!mine.length) continue;
    // Beats that say text (by lines or written out) in this section, each with the last line number it says.
    const indexOf = (text: string) => {
      const at = own.findIndex((line) => text.includes(line));
      return at < 0 ? -1 : at + 1;
    };
    const missing = own.map((_, i) => i + 1).filter((k) => {
      if (said.get(n)?.has(k)) return false;
      // A beat that wrote the sentence out instead of naming it still says it.
      return !mine.some((c) => c.beats!.some((b) => typeof b.say === "string" && b.say.includes(own[k - 1])));
    });
    for (let i = 0; i < missing.length; ) {
      // One or two consecutive missing sentences a beat, as the script would have it.
      const group = [missing[i]];
      if (missing[i + 1] === missing[i] + 1 && (own[missing[i] - 1].length + own[missing[i]].length) < 170) {
        group.push(missing[i + 1]);
      }
      i += group.length;
      const before = group[0] - 1;
      // After the beat that says the nearest line before it; else at the start of the section's first chapter.
      let placed = false;
      for (let ci = mine.length - 1; ci >= 0 && !placed; ci--) {
        const beats = mine[ci].beats!;
        for (let bi = beats.length - 1; bi >= 0; bi--) {
          const last = typeof beats[bi].say === "string" ? lastLine(String(beats[bi].say), own, indexOf) : -1;
          if (last >= 1 && last <= before) {
            beats.splice(bi + 1, 0, { say: group.map((k) => own[k - 1]).join(" "), do: [] });
            placed = true;
            break;
          }
        }
      }
      if (!placed) mine[0].beats!.unshift({ say: group.map((k) => own[k - 1]).join(" "), do: [] });
      report.added += group.length;
    }
  }
  if (options.minBeats) report.merged = mergeThin(chapters, options.minBeats, options.complete ?? []);
  return report;
}

/** The highest line of `own` a beat's text says, or -1. */
function lastLine(text: string, own: string[], indexOf: (t: string) => number): number {
  let best = -1;
  own.forEach((line, i) => {
    if (text.includes(line)) best = Math.max(best, i + 1);
  });
  return best >= 0 ? best : indexOf(text);
}

/**
 * Chapters of fewer than `minBeats` beats in the given sections, merged into the chapter before them of the same
 * section (or the one after, for a section's first): a chapter of one beat was a title card for a sentence, and
 * the section was refused and written again for it. Returns how many were merged.
 */
function mergeThin(chapters: Chapter[], minBeats: number, sections: number[]): number {
  let merged = 0;
  for (let i = 0; i < chapters.length; i++) {
    const c = chapters[i];
    const n = Number(c?.section);
    if (!sections.includes(n) || !Array.isArray(c.beats) || c.beats.length >= minBeats) continue;
    const prev = i > 0 && Number(chapters[i - 1]?.section) === n ? chapters[i - 1] : null;
    const next = i + 1 < chapters.length && Number(chapters[i + 1]?.section) === n ? chapters[i + 1] : null;
    if (prev && Array.isArray(prev.beats)) {
      prev.beats.push(...c.beats);
    } else if (next && Array.isArray(next.beats)) {
      next.beats.unshift(...c.beats);
    } else {
      continue;      // the section's only chapter: it stays, short as it is
    }
    chapters.splice(i, 1);
    i--;
    merged++;
  }
  return merged;
}
