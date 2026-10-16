/**
 * What a run is, as the server keeps it and the page shows it. Plain data (no Node imports): the page reads it.
 */

import type { Part } from "./prompts/parts";
import type { Block } from "./source/blocks";
import type { Goal } from "./plan";

/** What code found when it read a model's reply: passed, mended by code, failed, or only noted. */
export type Check = { name: string; result: "pass" | "fixed" | "fail" | "info"; detail: string };

export type Call = {
  id: string;
  /** Which step of the flow made it: "plan", "lecture", "patch". */
  step: string;
  label: string;
  lecture?: number;
  model: string;
  effort?: string;
  status: "running" | "done" | "failed";
  started: number;
  ended?: number;
  attempts: { started: number; ended: number; error?: string }[];
  prompt: { system: Part[]; user: Part[] };
  tool?: unknown;
  /** The tool's arguments the reply gave (parsed), or the reply's text when it gave none. */
  output?: unknown;
  text?: string;
  usage?: { input: number; output: number; cached?: number; reasoning?: number };
  cost: number;
  /** "openrouter" for a real call, "fixture" for the offline stand-in (no key). */
  provider: "openrouter" | "fixture";
  error?: string;
  checks: Check[];
  /** Pictures sent with the prompt (a figure to describe), as URLs the page can show. */
  images?: string[];
};

export type StepKey = "read" | "figures" | "plan" | "write";

export type Step = { key: StepKey; label: string; status: "waiting" | "running" | "done" | "failed"; started?: number;
  ended?: number; summary?: string };

/** A lecture of the series: its part of the book (block ids) and goals from the plan, and its transcript. */
export type LectureState = {
  n: number;
  title: string;
  why: string;
  blocks: string[];
  goals: Goal[];
  status: "waiting" | "writing" | "written" | "failed";
  /** The final text (cleaned, repeats out, patches in). */
  text?: string;
  /** Each goal taught, with the sentence numbers in the final text that teach it. */
  goalLines?: Record<string, number[]>;
  /** The blocks the writer (or a patch) says it taught; the rest of the lecture's blocks are missing. */
  blocksTaught?: string[];
  /** Sentences written in by a patch, with what they cover. */
  patched?: { covers: string[]; lines: number[] }[];
  dropped?: string[];
  calls: string[];
};

export type Options = {
  /** How long a lecture is meant to be: told to the planner, as context. */
  lectureMinutes: number;
  language: "auto" | "english" | "hindi" | "hinglish";
  subject: string;
  plannerModel: string;
  writerModel: string;
  /** Reads the book's figures (a model that reads images). */
  figureModel: string;
  effort: "low" | "medium" | "high" | "off";
};

export type Run = {
  id: string;
  documentId: string;
  documentName: string;
  created: number;
  ended?: number;
  status: "running" | "done" | "failed";
  error?: string;
  options: Options;
  steps: Step[];
  /** The book as blocks (blocks.ts): what the plan and the lectures name. */
  blocks: Block[];
  skipped: { block: string; reason: string }[];
  lectures: LectureState[];
  goalStatus: Record<string, GoalStatus>;
  calls: Call[];
  log: { t: number; text: string }[];
};

export type GoalStatus = "waiting" | "taught" | "patched" | "missing";

export type DocumentInfo = {
  id: string;
  name: string;
  pages: number;
  words: number;
  source: string;
  created: number;
};
