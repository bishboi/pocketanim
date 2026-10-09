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

  bill(task: CostTask, usd: number, more: { calls?: number; inputTokens?: number; outputTokens?: number; items?: number } = {}) {
    const line = (this.lines[task] ??= { usd: 0, calls: 0, inputTokens: 0, outputTokens: 0, items: 0 });
    line.usd += Number.isFinite(usd) ? usd : 0;
    line.calls += more.calls ?? 1;
    line.inputTokens += more.inputTokens ?? 0;
    line.outputTokens += more.outputTokens ?? 0;
    line.items += more.items ?? 0;
    return this.total;
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
