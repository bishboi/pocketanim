/**
 * What a lecture cost, task by task: the model calls that wrote it (transcript, video script, fixes), the
 * pictures drawn for it (the book's figures and the script's drawings as SVG, AI illustrations), its voice, and
 * its build. The server keeps one ledger per generation and streams it with every usage event; the page adds the
 * voice and the build, which happen when the lecture is built.
 */

export const COST_TASKS = ["transcript", "script", "fixes", "figures", "drawings", "images"] as const;
export type CostTask = (typeof COST_TASKS)[number];

export type CostLine = {
  usd: number;
  /** Model requests made for it. */
  calls: number;
  inputTokens: number;
  outputTokens: number;
  /** Things made: figures or drawings drawn as SVG, illustrations generated. */
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
  transcript: "Transcribing the lecture",
  script: "Writing the video script",
  fixes: "Fixing the script",
  figures: "Book figures drawn as SVG",
  drawings: "Pictures drawn as SVG",
  images: "AI illustrations",
};

const ITEM_WORDS: Partial<Record<CostTask, [string, string]>> = {
  figures: ["SVG", "SVGs"],
  drawings: ["SVG", "SVGs"],
  images: ["image", "images"],
};

/** The ledger for one generation: bill() adds to a task and returns the new total. */
export class CostLedger {
  readonly lines: Costs = {};
  /** When the generation began: its whole time is from here to the last event. */
  readonly started = Date.now();

  bill(task: CostTask, usd: number, more: { calls?: number; inputTokens?: number; outputTokens?: number; items?: number;
    span?: [number, number] } = {}) {
    const line = (this.lines[task] ??= { usd: 0, calls: 0, inputTokens: 0, outputTokens: 0, items: 0 });
    line.usd += Number.isFinite(usd) ? usd : 0;
    line.calls += more.calls ?? 1;
    line.inputTokens += more.inputTokens ?? 0;
    line.outputTokens += more.outputTokens ?? 0;
    line.items += more.items ?? 0;
    if (more.span) this.time(task, more.span[0], more.span[1]);
    return this.total;
  }

  /** The task was at work from `start` to `end` (ms since the epoch). */
  time(task: CostTask, start: number, end: number) {
    if (!(end > start)) return;
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

/** "4 SVGs", "1 image", "" for a task without items. */
export function itemsText(task: CostTask, line: CostLine): string {
  const words = ITEM_WORDS[task];
  if (!words) return "";
  return `${line.items} ${line.items === 1 ? words[0] : words[1]}`;
}

export function usd(value: number): string {
  if (!value) return "$0";
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(value < 1 ? 3 : 2)}`;
}

/** A picture the AI made for a lecture: an SVG drawn for a book figure or for the script, or an illustration an
 * image model drew. `usd` is what it cost this lecture; one `reused` from an earlier run cost nothing now, and
 * `paid` says what it cost when it was made. */
export type AiPicture = {
  kind: "figure" | "drawing" | "illustration";
  /** Where it is on the server (/api/picture serves it). */
  file: string;
  title: string;
  usd: number;
  reused: boolean;
  paid?: number | null;
  /** Its parts (an SVG), or the model that drew it (an illustration). */
  detail?: string;
};

export const PICTURE_KINDS: Record<AiPicture["kind"], string> = {
  figure: "Book figure, drawn as SVG",
  drawing: "Picture drawn as SVG",
  illustration: "AI illustration",
};
