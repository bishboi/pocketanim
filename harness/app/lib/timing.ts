/**
 * The timing log of one generation or build: every timed step (a model request, a compile and its parts, a
 * picture, a Manim figure, a book figure, a narration request, a wait) as one JSON line, with what it was for and how
 * it ended, in harness/app/.logs (PANIM_TIMING_DIR). `node scripts/timing-report.mjs <file>` sums one up; the end of
 * a generation also says its slowest steps in the status log.
 */

import { appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";

export type TimingEvent = {
  /** What kind of step: "transcript", "script", "compile", "picture", "manim", "figure", "tts", "wait"... */
  kind: string;
  /** When it began and ended (ms since the epoch); seconds it took. */
  start: number;
  end: number;
  seconds: number;
  /** What it was for: a section, a figure, a picture's subject, a model, an outcome. */
  [detail: string]: unknown;
};

const DIR = process.env.PANIM_TIMING_DIR || path.join(process.cwd(), ".logs");

export class TimingLog {
  readonly file: string;
  readonly events: TimingEvent[] = [];

  constructor(name: string) {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "run";
    this.file = path.join(DIR, `${stamp}-${slug}.jsonl`);
    try {
      mkdirSync(DIR, { recursive: true });
    } catch {
      // no log, the run goes on
    }
  }

  /** A step that ran from `start` to `end` (ms since the epoch). */
  span(kind: string, start: number, end: number, detail: Record<string, unknown> = {}) {
    if (!(end >= start)) return;
    const event: TimingEvent = { kind, start, end, seconds: Math.round((end - start) / 100) / 10, ...detail };
    this.events.push(event);
    try {
      appendFileSync(this.file, `${JSON.stringify(event)}\n`);
    } catch {
      // the log is a help, never a failure
    }
  }

  /** A moment worth knowing (a stall, a fallback, a wait begun). */
  note(kind: string, detail: Record<string, unknown> = {}) {
    const now = Date.now();
    this.span(kind, now, now, detail);
  }

  /** Each kind's count, its time (overlaps counted once) and its longest step; then the slowest steps. */
  summary(top = 10): string[] {
    const kinds = new Map<string, TimingEvent[]>();
    for (const e of this.events) kinds.set(e.kind, [...(kinds.get(e.kind) ?? []), e]);
    const rows = [...kinds].map(([kind, list]) => ({ kind, count: list.length, wall: wallSeconds(list),
      longest: Math.max(...list.map((e) => e.seconds)) })).filter((r) => r.wall > 0).sort((a, b) => b.wall - a.wall);
    const slowest = [...this.events].filter((e) => e.seconds > 0).sort((a, b) => b.seconds - a.seconds).slice(0, top);
    return [
      ...rows.map((r) => `${r.kind}: ${r.count} step${r.count > 1 ? "s" : ""}, ${clock(r.wall)} on the clock, the longest ${clock(r.longest)}`),
      "slowest steps:",
      ...slowest.map((e) => `  ${clock(e.seconds)}  ${e.kind}  ${describe(e)}`),
    ];
  }
}

/** Seconds of the clock a list of steps covered, overlaps counted once. */
export function wallSeconds(events: { start: number; end: number }[]): number {
  const spans = events.map((e) => [e.start, e.end] as [number, number]).sort((a, b) => a[0] - b[0]);
  let total = 0;
  let [from, to] = [0, 0];
  for (const [a, b] of spans) {
    if (a > to) {
      total += to - from;
      [from, to] = [a, b];
    } else to = Math.max(to, b);
  }
  return (total + to - from) / 1000;
}

export function clock(seconds: number): string {
  const s = Math.round(seconds);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
}

function describe(e: TimingEvent): string {
  return Object.entries(e).filter(([k]) => !["kind", "start", "end", "seconds"].includes(k))
    .map(([k, v]) => `${k}=${typeof v === "string" ? JSON.stringify(v.slice(0, 80)) : JSON.stringify(v)}`).join(" ");
}
