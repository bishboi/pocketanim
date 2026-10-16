/**
 * What a run is, as the server keeps it and the page shows it. Plain data (no Node imports): the page reads it.
 */

import type { Part } from "./prompts/parts";
import type { LearningMap } from "./plan/learningmap";
import type { GoalStatus, StoryPlan } from "./plan/storyplan";
import type { BookQuestion } from "./source/questions";

/** What code found when it read a model's reply: passed, mended by code, failed, or only noted. */
export type Check = { name: string; result: "pass" | "fixed" | "fail" | "info"; detail: string };

export type Call = {
  id: string;
  /** Which step of the flow made it: "map", "plan", "section", "patch", "check". */
  step: string;
  label: string;
  section?: number;
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
};

export type StepKey = "read" | "map" | "plan" | "write" | "videos";

export type Step = { key: StepKey; label: string; status: "waiting" | "running" | "done" | "failed"; started?: number;
  ended?: number; summary?: string };

export type SectionState = {
  n: number;
  minutes: number;
  words: number;
  source: string;
  questions: BookQuestion[];
  questionsOnly?: boolean;
  video?: number;
  status: "waiting" | "writing" | "written" | "failed";
  title?: string;
  /** The final text (cleaned, repeats out, patches in). */
  text?: string;
  /** Each goal the section reported, with the sentence numbers in the final text that teach it. */
  goalLines?: Record<string, number[]>;
  /** Sentences written in by a patch: their numbers in the final text. */
  patched?: { goal: string; lines: number[] }[];
  dropped?: string[];
  calls: string[];
};

export type Options = {
  minutes: number;
  language: "auto" | "english" | "hindi" | "hinglish";
  subject: string;
  plannerModel: string;
  writerModel: string;
  effort: "low" | "medium" | "high" | "off";
  parallel: number;
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
  sections: SectionState[];
  map?: LearningMap;
  plans: StoryPlan[];
  videos: { index: number; sections: number[]; minutes: number; title: string; written?: number }[];
  goalStatus: Record<string, GoalStatus>;
  calls: Call[];
  log: { t: number; text: string }[];
};

export type DocumentInfo = {
  id: string;
  name: string;
  pages: number;
  words: number;
  source: string;
  created: number;
};
