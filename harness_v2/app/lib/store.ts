/**
 * Where v2 keeps its files: harness_v2/app/.data/docs/<id>/ (the PDF, Datalab's JSON of it, its figures) and harness_v2/app/.data/runs/<id>.json (a run, written as it goes, so a page reloaded mid-run sees it).
 */

import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import type { DocumentInfo, Run } from "./types";
import type { RawBlock } from "./datalab";

export const DATA = path.join(process.cwd(), ".data");
export const REPO = path.resolve(process.cwd(), "..", "..");
const ID = /^[a-z0-9-]{6,40}$/;

export function newId(): string {
  return `${Date.now().toString(36)}-${randomBytes(4).toString("hex")}`;
}

export function docDir(id: string): string {
  if (!ID.test(id)) throw new Error("not a document id");
  return path.join(DATA, "docs", id);
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  const root = path.join(DATA, "docs");
  if (!existsSync(root)) return [];
  const out: DocumentInfo[] = [];
  for (const id of await readdir(root)) {
    try {
      out.push(JSON.parse(await readFile(path.join(root, id, "info.json"), "utf8")));
    } catch {}
  }
  return out.sort((a, b) => b.created - a.created);
}

/** The book as Datalab's JSON, and its figures' image files by block id. */
export async function documentBook(id: string): Promise<{ json: RawBlock; figures: Record<string, string> }> {
  const json = JSON.parse(await readFile(path.join(docDir(id), "book.json"), "utf8")) as RawBlock;
  let figures: Record<string, string> = {};
  try {
    figures = JSON.parse(await readFile(path.join(docDir(id), "figures.json"), "utf8"));
  } catch {}
  return { json, figures };
}

export async function documentInfo(id: string): Promise<DocumentInfo> {
  return JSON.parse(await readFile(path.join(docDir(id), "info.json"), "utf8"));
}

// ─── Runs ────────────────────────────────────────────────────────────────────────────────────────────────────────

// Kept on globalThis: Next can load this module more than once (a copy per route), and every copy must see the same
// live runs, or a run being written would look like one the server lost.
const shared = globalThis as unknown as { __v2runs?: Map<string, Run>; __v2pending?: Map<string, ReturnType<typeof setTimeout>> };
const runs = (shared.__v2runs ??= new Map<string, Run>());
const pending = (shared.__v2pending ??= new Map<string, ReturnType<typeof setTimeout>>());

function runFile(id: string): string {
  if (!ID.test(id)) throw new Error("not a run id");
  return path.join(DATA, "runs", `${id}.json`);
}

const writing = ((globalThis as unknown as { __v2writing?: Map<string, Promise<void>> }).__v2writing ??= new Map());

/** One write of a run at a time, each to its own temporary file then renamed over the run's, so two saves close
 * together never meet; a write that fails is logged, never thrown (a run in memory is still whole). */
function writeRun(run: Run): Promise<void> {
  const next = (writing.get(run.id) ?? Promise.resolve()).then(async () => {
    try {
      await mkdir(path.join(DATA, "runs"), { recursive: true });
      const file = runFile(run.id);
      const tmp = `${file}.${randomBytes(3).toString("hex")}.tmp`;
      await writeFile(tmp, JSON.stringify(run), "utf8");
      await rename(tmp, file);
    } catch (error) {
      console.error(`run ${run.id} could not be saved: ${(error as Error).message}`);
    }
  });
  writing.set(run.id, next);
  return next;
}

/** Keep a run in memory, and write it to disk at most twice a second. */
export function saveRun(run: Run, now = false): void {
  runs.set(run.id, run);
  if (pending.has(run.id) && !now) return;
  clearTimeout(pending.get(run.id));
  pending.set(run.id, setTimeout(() => {
    pending.delete(run.id);
    void writeRun(run);
  }, now ? 0 : 500));
}

/**
 * A run: the live one while this server has it, else as last written. One written as running that this server does
 * not have was cut off (the server stopped): it is marked interrupted, what was running set back to waiting, so it
 * can be continued from there.
 */
export async function loadRun(id: string): Promise<Run | null> {
  const live = runs.get(id);
  if (live) return normalize(live as unknown as Record<string, unknown>);
  let run: Run;
  try {
    run = normalize(JSON.parse(await readFile(runFile(id), "utf8")));
  } catch {
    return null;
  }
  let cut = false;
  if (run.status === "running") {
    cut = true;
    run.status = "interrupted";
    run.error = "The server stopped while this ran. Continue picks it up from where it was.";
    for (const s of run.steps) if (s.status === "running") s.status = "waiting";
    for (const l of run.lectures) if (l.status === "writing") l.status = "waiting";
  }
  if (run.script?.status === "running") {
    cut = true;
    run.script.status = "interrupted";
    for (const l of Object.values(run.script.lectures)) if (l.status === "running" || l.status === "waiting") l.status = l.chapters.length ? "done" : "waiting";
  }
  if (run.generation?.status === "running") {
    cut = true;
    run.generation.status = "interrupted";
    for (const f of Object.values(run.generation.figures)) if (f.status === "running") f.status = "waiting";
  }
  if (run.triage?.status === "running") {
    cut = true;
    run.triage.status = "interrupted";
    for (const f of Object.values(run.triage.figures)) if (f.status === "running") f.status = "waiting";
  }
  for (const c of run.calls) {
    if (c.status === "running") {
      c.status = "failed";
      c.error = "cut off: the server stopped during the call";
    }
  }
  runs.set(run.id, run);
  if (cut) saveRun(run, true);
  return run;
}

/**
 * A run file as this version reads it. One written by an earlier v2 (sections, a learning map and story plans,
 * before lectures were planned from Datalab's blocks) has none of the fields this one fills: they are made empty,
 * and it is marked as from an earlier version (it can be opened, not continued).
 */
function normalize(raw: Record<string, unknown>): Run {
  const run = raw as unknown as Run & { sections?: unknown };
  const legacy = !Array.isArray(raw.lectures) && (Array.isArray(run.sections) || !Array.isArray(raw.blocks));
  run.steps = Array.isArray(run.steps) ? run.steps : [];
  run.blocks = Array.isArray(run.blocks) ? run.blocks : [];
  run.skipped = Array.isArray(run.skipped) ? run.skipped : [];
  run.lectures = Array.isArray(run.lectures) ? run.lectures : [];
  run.goalStatus = run.goalStatus && typeof run.goalStatus === "object" ? run.goalStatus : {};
  run.calls = Array.isArray(run.calls) ? run.calls : [];
  run.log = Array.isArray(run.log) ? run.log : [];
  run.options = run.options ?? ({} as Run["options"]);
  run.documentName = run.documentName ?? "(unknown book)";
  run.created = Number(run.created) || 0;
  if (legacy) {
    run.legacy = "Made by an earlier version of v2 (sections and story plans): its calls can be looked at, but it cannot be continued. Build the transcript again for this book.";
    if (run.status === "running") run.status = "interrupted";
  }
  return run;
}

export type RunSummary = { id: string; documentName: string; created: number; status: string; cost: number; lectures: string;
  triage?: string };

export async function listRuns(): Promise<RunSummary[]> {
  const root = path.join(DATA, "runs");
  if (!existsSync(root)) return [];
  const out = [];
  for (const name of await readdir(root)) {
    if (!name.endsWith(".json")) continue;
    // A run already in memory may have been read by an earlier version of this code: normalized here too.
    let run: Run | null;
    try {
      const live = runs.get(name.slice(0, -5));
      run = live ? normalize(live as unknown as Record<string, unknown>) : await loadRun(name.slice(0, -5));
    } catch (error) {
      console.error(`run file ${name} could not be read: ${(error as Error).message}`);
      continue;
    }
    if (!run) continue;
    if (run.legacy) {
      out.push({ id: run.id, documentName: run.documentName, created: run.created, status: `${run.status} (earlier version)`,
        cost: run.calls.reduce((n, c) => n + (Number(c.cost) || 0), 0), lectures: "no lectures" });
      continue;
    }
    const figures = Object.values(run.triage?.figures ?? {});
    out.push({ id: run.id, documentName: run.documentName, created: run.created, status: run.status,
      cost: run.calls.reduce((n, c) => n + c.cost, 0),
      lectures: `${run.lectures.filter((l) => l.status === "written").length}/${run.lectures.length} lectures`,
      triage: figures.length ? `${figures.filter((f) => f.status === "done").length}/${figures.length} figures triaged` : undefined });
  }
  return out.sort((a, b) => b.created - a.created);
}
