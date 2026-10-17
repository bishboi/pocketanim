/**
 * The learning goals of runs made before the lectures were written as scripts: a planner divided the book into
 * lectures and mapped each lecture's goals. New runs have none; old run files keep theirs and are read as they are.
 */

export type Goal = { id: string; lecture: number; goal: string; blocks: string[]; misconception: string; hook: string };
