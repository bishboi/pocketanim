/**
 * What a run is, as the server keeps it and the page shows it. Plain data (no Node imports): the page reads it.
 */

import type { Part } from "./prompts/parts";
import type { Block } from "./source/blocks";
import type { Goal } from "./plan";
import type { TriageKind } from "./triage-kinds";

/** What code found when it read a model's reply: passed, mended by code, failed, or only noted. */
export type Check = { name: string; result: "pass" | "fixed" | "fail" | "info"; detail: string };

export type Call = {
  id: string;
  /** Which step of the flow made it: "plan", "lecture", "patch". */
  step: string;
  label: string;
  lecture?: number;
  /** The book's block the call is about (a figure described or triaged). */
  block?: string;
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
  /** "interrupted": the server stopped while it ran (it can be continued); "stopped": stopped from the page. */
  status: "running" | "done" | "failed" | "stopped" | "interrupted";
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
  /** The figure triage (triage.ts): how each of the book's figures is to be shown. Runs apart from the transcript. */
  triage?: Triage;
  /** Where it was imported from, when it came from an exported transcript. */
  imported?: { file: string; at: number };
};

/** How one figure is to be shown, as the triage decided it (and the user, when they chose another). */
export type FigureTriage = {
  block: string;
  status: "waiting" | "running" | "done" | "failed";
  kind?: TriageKind;
  /** The model's instruction for whoever builds or redraws it. */
  how?: string;
  /** Why this way. */
  reason?: string;
  /** Labels, values and parts that must stay exactly as in the book. */
  keep?: string[];
  /** The way the user chose instead of the model's. */
  override?: TriageKind;
  error?: string;
  calls: string[];
  at?: number;
};

export type Triage = {
  status: "idle" | "running" | "done" | "failed" | "stopped" | "interrupted";
  /** The ways the model may choose from (the user's choice). */
  kinds: TriageKind[];
  model: string;
  started?: number;
  ended?: number;
  /** How many times it was run (reset or not). */
  rounds: number;
  figures: Record<string, FigureTriage>;
  error?: string;
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
