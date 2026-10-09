/**
 * Work that outlives the page that started it. Writing a lecture, building it and drawing an SVG lab's pictures
 * take minutes; they ran inside the request that started them, so reloading the page stopped them (or, for a
 * build, threw its result away). Here each runs as a job in the server process: its events are kept, and a page
 * that comes back (reloaded, or another tab) follows it again from any point, replayed from the start.
 *
 * Jobs live in memory for the life of the server process (kept on globalThis so a dev reload of this module does
 * not lose them); a finished build's result is also written to disk, so a page reloaded after a restart still
 * finds it.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

export type JobEvent = { type: string; role?: string; text?: string; [key: string]: unknown };

export type Job = {
  id: string;
  kind: string;
  events: JobEvent[];
  done: boolean;
  stopped: boolean;
  started: number;
  updated: number;
  listeners: Set<(event: JobEvent | null) => void>;
};

type Store = { jobs: Map<string, Job>; results: Map<string, Promise<unknown>> };
const store: Store = ((globalThis as { __panimJobs?: Store }).__panimJobs ??= { jobs: new Map(), results: new Map() });

/** Finished jobs are forgotten after a day. */
const KEEP_MS = 24 * 3600_000;

function sweep() {
  const now = Date.now();
  for (const [id, job] of store.jobs) {
    if (job.done && now - job.updated > KEEP_MS) store.jobs.delete(id);
  }
}

export function validJobId(id: unknown): id is string {
  return typeof id === "string" && /^[\w-]{6,80}$/.test(id);
}

export function newJobId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

export function getJob(id: string): Job | undefined {
  return store.jobs.get(id);
}

export function createJob(kind: string, id = newJobId(kind)): Job {
  sweep();
  const job: Job = { id, kind, events: [], done: false, stopped: false, started: Date.now(), updated: Date.now(),
    listeners: new Set() };
  store.jobs.set(id, job);
  return job;
}

/** An event of the job, kept and sent to everyone following it. Streamed text arrives in thousands of small
 * deltas: consecutive ones of the same kind are kept as one, so a replay is short. */
export function pushEvent(job: Job, event: JobEvent): void {
  // When it happened, so a page that replays a finished job still knows how long each part took.
  event = { ...event, at: Date.now() };
  const last = job.events[job.events.length - 1];
  if (event.type === "delta" && last?.type === "delta" && last.role === event.role && job.listeners.size === 0) {
    job.events[job.events.length - 1] = { ...last, text: `${last.text ?? ""}${event.text ?? ""}` };
  } else {
    job.events.push(event);
  }
  job.updated = Date.now();
  for (const listener of job.listeners) listener(event);
}

export function finishJob(job: Job): void {
  job.done = true;
  job.updated = Date.now();
  for (const listener of job.listeners) listener(null);
  job.listeners.clear();
}

/** Server-sent events following a job: everything from event `from` on, then each new one, until it ends. */
export function followStream(job: Job, from = 0, first?: JobEvent): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let listener: ((event: JobEvent | null) => void) | null = null;
  return new ReadableStream({
    start(controller) {
      const send = (event: JobEvent) => {
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
        } catch {
          // the page went away; the job goes on
        }
      };
      const close = () => {
        if (listener) job.listeners.delete(listener);
        try {
          controller.close();
        } catch {
          // already closed
        }
      };
      if (first) send(first);
      for (const event of job.events.slice(Math.max(0, from))) send(event);
      if (job.done) return close();
      listener = (event) => (event ? send(event) : close());
      job.listeners.add(listener);
    },
    cancel() {
      if (listener) job.listeners.delete(listener);
    },
  });
}

export const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  "X-Accel-Buffering": "no",
};

// ---------------------------------------------------------------- results asked for again by the same id

const RESULTS = path.join(process.cwd(), ".jobs");

/** Run `work` once per id: asked again with the same id (the page reloaded while it ran), the same run is waited
 * for, or its result, written to disk when it finished, is read back. */
export async function once<T>(id: string, work: () => Promise<T>): Promise<T> {
  const running = store.results.get(id) as Promise<T> | undefined;
  if (running) return running;
  const file = path.join(RESULTS, `${id}.json`);
  try {
    return JSON.parse(await readFile(file, "utf8")) as T;
  } catch {
    // not run before
  }
  const promise = (async () => {
    const result = await work();
    try {
      await mkdir(RESULTS, { recursive: true });
      await writeFile(file, JSON.stringify(result), "utf8");
    } catch {
      // kept in memory only
    }
    return result;
  })();
  store.results.set(id, promise);
  promise.catch(() => store.results.delete(id));
  return promise;
}

/** A result run by `once` with this id: finished (from memory or disk), still running, or unknown. */
export async function resultOf(id: string): Promise<{ state: "running" | "done" | "unknown"; result?: unknown }> {
  const running = store.results.get(id);
  const file = path.join(RESULTS, `${id}.json`);
  try {
    return { state: "done", result: JSON.parse(await readFile(file, "utf8")) };
  } catch {
    // not finished on disk
  }
  return running ? { state: "running" } : { state: "unknown" };
}
