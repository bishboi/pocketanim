/**
 * A lecture's script as the later steps read it: the figures a beat shows (any figure may be on several beats), a
 * lecture's figures with the sentences they are shown on, and the chapters that teach from a block of the book
 * (chapters may share their content). No server code here: the page reads it too.
 */

import { captionOf } from "./source/blocks";
import { choiceOf } from "./triage-kinds";
import type { Beat, Chapter, Run } from "./types";

/** A figure as the steps after the script are told of it: its way, caption, made yet, and where it is shown. */
export type FigureForScript = { id: string; way: string; caption: string; ready: boolean; lines: number[]; beats: number[] };

/** The figures a beat shows: its list, or the one figure older scripts had. */
export function beatFigures(b: Pick<Beat, "figures" | "figure">): string[] {
  return b.figures?.length ? b.figures : b.figure ? [b.figure] : [];
}

/** A figure's way as it stands (chosen by hand, else the triage's). */
export function wayOf(run: Run, block: string): string | undefined {
  const f = run.triage?.figures[block];
  return f?.override ?? (f?.status === "done" ? f.kind : undefined);
}

/** A lecture's chapters (its script), when it has one. */
export function chaptersOf(run: Run, n: number): Chapter[] {
  return run.script?.lectures[n]?.chapters ?? [];
}

/**
 * A lecture's figures: those its beats show, and those in its chapters' content (or, before it has a script, in its
 * blocks), each with the beats and sentences it is shown on. A figure triaged Skip is left out.
 */
export function lectureFigures(run: Run, n: number): FigureForScript[] {
  const lecture = run.lectures.find((l) => l.n === n);
  if (!lecture) return [];
  const chapters = chaptersOf(run, n);
  const beats = chapters.flatMap((c) => c.beats);
  const ids = new Set([...beats.flatMap(beatFigures), ...chapters.flatMap((c) => c.content ?? []), ...(chapters.length ? [] : lecture.blocks)]);
  return run.blocks.filter((b) => b.image && ids.has(b.id) && wayOf(run, b.id) !== "skip").map((b) => {
    const on = beats.filter((x) => beatFigures(x).includes(b.id));
    const way = wayOf(run, b.id);
    return { id: b.id, way: way ? choiceOf(way)?.label ?? way : "not triaged", caption: captionOf(run.blocks, b) ?? b.description ?? "",
      ready: run.generation?.figures[b.id]?.status === "done", lines: [...new Set(on.flatMap((x) => x.lines))].sort((x, y) => x - y),
      beats: on.map((x) => x.n) };
  });
}

/** The chapters that teach from a block of the book (any number: chapters may share content), with their lecture. */
export function chaptersUsing(run: Run, block: string): { lecture: number; title: string; chapter: Chapter }[] {
  return run.lectures.flatMap((l) => chaptersOf(run, l.n)
    .filter((c) => (c.content ?? []).includes(block) || c.beats.some((b) => beatFigures(b).includes(block)))
    .map((chapter) => ({ lecture: l.n, title: l.title, chapter })));
}
