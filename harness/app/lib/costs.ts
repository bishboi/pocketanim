/**
 * What a lecture cost, task by task: the model calls that wrote it (transcript, video script, fixes), the
 * pictures made for it (the book's figures looked at and redrawn, AI illustrations and diagrams), its voice, and
 * its build. The server keeps one ledger per generation and streams it with every usage event; the page adds the
 * voice and the build, which happen when the lecture is built.
 */

export const COST_TASKS = ["planning", "transcript", "script", "fixes", "stalled", "manim", "figures", "waiting", "compile", "drawings", "images"] as const;
export type CostTask = (typeof COST_TASKS)[number];

export type CostLine = {
  usd: number;
  /** Model requests made for it. */
  calls: number;
  inputTokens: number;
  outputTokens: number;
  /** Things made: book figures redrawn, illustrations and diagrams generated. */
  items: number;
  /** A short word on what the items are, or what else happened ("3 built in Manim, 1 photograph"). */
  note?: string;
  /** How long the task ran, in seconds of the clock: the periods it was at work, overlaps counted once (sections
   * written at once take as long as the longest, not the sum). */
  seconds?: number;
  /** Those periods, [start, end] in ms since the epoch, merged. */
  spans?: [number, number][];
};

export type Costs = Partial<Record<CostTask, CostLine>>;

export const COST_LABELS: Record<CostTask, string> = {
  planning: "Reading the source, choosing the subject",
  transcript: "Transcribing the lecture",
  script: "Writing the video script",
  fixes: "Fixing the script",
  stalled: "Model tries that stalled or failed (asked again)",
  manim: "Writing the Manim figures",
  figures: "Book figures",
  waiting: "Waiting for the book's figures",
  compile: "Checking and compiling the script",
  drawings: "Detailed diagrams",
  images: "AI illustrations",
};

const ITEM_WORDS: Partial<Record<CostTask, [string, string]>> = {
  figures: ["redrawn", "redrawn"],
  stalled: ["try", "tries"],
  manim: ["request", "requests"],
  drawings: ["diagram", "diagrams"],
  images: ["image", "images"],
};

/** The ledger for one generation: bill() adds to a task and returns the new total. */
export class CostLedger {
  readonly lines: Costs = {};
  /** When the generation began: its whole time is from here to the last event. */
  readonly started = Date.now();

  /** Told of every timed step, with what it was for (the generation's timing log, lib/timing.ts). */
  onSpan?: (task: CostTask, start: number, end: number, detail?: Record<string, unknown>) => void;

  bill(task: CostTask, usd: number, more: { calls?: number; inputTokens?: number; outputTokens?: number; items?: number;
    span?: [number, number]; detail?: Record<string, unknown> } = {}) {
    const line = (this.lines[task] ??= { usd: 0, calls: 0, inputTokens: 0, outputTokens: 0, items: 0 });
    line.usd += Number.isFinite(usd) ? usd : 0;
    line.calls += more.calls ?? 1;
    line.inputTokens += more.inputTokens ?? 0;
    line.outputTokens += more.outputTokens ?? 0;
    line.items += more.items ?? 0;
    if (more.span) this.time(task, more.span[0], more.span[1], { ...more.detail, usd: Number(usd.toFixed(5)),
      in: more.inputTokens, out: more.outputTokens });
    return this.total;
  }

  /** The task was at work from `start` to `end` (ms since the epoch). */
  time(task: CostTask, start: number, end: number, detail?: Record<string, unknown>) {
    if (!(end > start)) return;
    this.onSpan?.(task, start, end, detail);
    const line = (this.lines[task] ??= { usd: 0, calls: 0, inputTokens: 0, outputTokens: 0, items: 0 });
    line.spans = mergeSpans([...(line.spans ?? []), [start, end]]);
    line.seconds = spanSeconds(line.spans);
  }

  /** Seconds since the generation began. */
  get elapsed(): number {
    return (Date.now() - this.started) / 1000;
  }

  /** Things made without a call of their own (a drawing counted when it passed its checks). */
  count(task: CostTask, items: number, note?: string) {
    const line = (this.lines[task] ??= { usd: 0, calls: 0, inputTokens: 0, outputTokens: 0, items: 0 });
    line.items += items;
    if (note !== undefined) line.note = note;
  }

  note(task: CostTask, note: string) {
    const line = (this.lines[task] ??= { usd: 0, calls: 0, inputTokens: 0, outputTokens: 0, items: 0 });
    line.note = note;
  }

  get total(): number {
    return Object.values(this.lines).reduce((sum, line) => sum + (line?.usd ?? 0), 0);
  }

  snapshot(): Costs {
    return JSON.parse(JSON.stringify(this.lines)) as Costs;
  }
}

/** Periods put in order with the ones that overlap or touch joined. */
export function mergeSpans(spans: [number, number][]): [number, number][] {
  const sorted = spans.filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]);
  const out: [number, number][] = [];
  for (const [a, b] of sorted) {
    const last = out[out.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b);
    else out.push([a, b]);
  }
  return out;
}

export function spanSeconds(spans: [number, number][]): number {
  return spans.reduce((t, [a, b]) => t + (b - a), 0) / 1000;
}

/** Seconds of the clock any task was at work: the generation's time not in "other" (planning, checks, waiting). */
export function busySeconds(costs: Costs): number {
  return spanSeconds(mergeSpans(Object.values(costs).flatMap((line) => line?.spans ?? [])));
}

/** "45 s", "3 min 20 s", "1 h 05 min". */
export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  return `${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")} min`;
}

/** "4 redrawn", "1 image", "" for a task without items. */
export function itemsText(task: CostTask, line: CostLine): string {
  const words = ITEM_WORDS[task];
  if (!words) return "";
  return `${line.items} ${line.items === 1 ? words[0] : words[1]}`;
}

export function usd(value: number): string {
  if (!value) return "$0";
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(value < 1 ? 3 : 2)}`;
}

/** A picture the AI made for a lecture: a book figure redrawn or made again, or an illustration or diagram an image
 * model made. `usd` is what it cost this lecture; one `reused` from an earlier run cost nothing now, and
 * `paid` says what it cost when it was made. */
export type AiPicture = {
  /** figure: a book figure redrawn by the diagram model; photo: a book photo (made again by the image model, or as
   * it is); rebuilt: a book figure built in Manim instead; drawing: a detailed diagram the diagram model made;
   * illustration: one the illustration model made. */
  kind: "figure" | "photo" | "rebuilt" | "drawing" | "illustration";
  /** Where it is on the server (/api/picture serves it). */
  file: string;
  title: string;
  usd: number;
  reused: boolean;
  paid?: number | null;
  /** Its labels, or the model that made it. */
  detail?: string;
  /** What became of a book figure, in a few words ("shown as a real photo like it", "built in Manim"). */
  status?: string;
  /** Where the lecture uses it (lib/media.ts keeps it with the picture): the chapter, the line said over it. */
  context?: Record<string, unknown>;
};

export const PICTURE_KINDS: Record<AiPicture["kind"], string> = {
  figure: "Book figure, redrawn",
  photo: "Book photo",
  rebuilt: "Book figure, built in Manim",
  drawing: "Detailed diagram",
  illustration: "AI illustration",
};
