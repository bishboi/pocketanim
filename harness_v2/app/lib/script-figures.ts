/**
 * A lecture's figures as the script step sees them (and the page shows them): no server code here, so the Script
 * tab can show what the script was told.
 */

import type { FigureForScript } from "./prompts/script";
import { captionOf } from "./source/blocks";
import { choiceOf } from "./triage-kinds";
import type { Run } from "./types";

/** A figure's way as it stands (chosen by hand, else the triage's). */
export function wayOf(run: Run, block: string): string | undefined {
  const f = run.triage?.figures[block];
  return f?.override ?? (f?.status === "done" ? f.kind : undefined);
}

/** A lecture's figures, as the script is told of them: way, caption, made yet, and the sentences that teach them. */
export function lectureFigures(run: Run, n: number): FigureForScript[] {
  const lecture = run.lectures.find((l) => l.n === n);
  if (!lecture) return [];
  return run.blocks.filter((b) => b.image && lecture.blocks.includes(b.id) && wayOf(run, b.id) !== "skip").map((b) => {
    const lines = [...new Set(lecture.goals.filter((g) => g.blocks.includes(b.id)).flatMap((g) => lecture.goalLines?.[g.id] ?? []))].sort((x, y) => x - y);
    const way = wayOf(run, b.id);
    return { id: b.id, way: way ? choiceOf(way)?.label ?? way : "not triaged", caption: captionOf(run.blocks, b) ?? b.description ?? "",
      ready: run.generation?.figures[b.id]?.status === "done", lines };
  });
}

