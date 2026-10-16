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

const runs = new Map<string, Run>();
const pending = new Map<string, ReturnType<typeof setTimeout>>();

function runFile(id: string): string {
  if (!ID.test(id)) throw new Error("not a run id");
  return path.join(DATA, "runs", `${id}.json`);
}

async function writeRun(run: Run): Promise<void> {
  await mkdir(path.join(DATA, "runs"), { recursive: true });
  const file = runFile(run.id);
  await writeFile(`${file}.tmp`, JSON.stringify(run), "utf8");
  await rename(`${file}.tmp`, file);
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

export async function loadRun(id: string): Promise<Run | null> {
  const live = runs.get(id);
  if (live) return live;
  try {
    return JSON.parse(await readFile(runFile(id), "utf8"));
  } catch {
    return null;
  }
}

export async function listRuns(): Promise<{ id: string; documentName: string; created: number; status: string; cost: number }[]> {
  const root = path.join(DATA, "runs");
  if (!existsSync(root)) return [];
  const out = [];
  for (const name of await readdir(root)) {
    if (!name.endsWith(".json")) continue;
    const run = runs.get(name.slice(0, -5)) ?? await loadRun(name.slice(0, -5));
    if (run) out.push({ id: run.id, documentName: run.documentName, created: run.created, status: run.status,
      cost: run.calls.reduce((n, c) => n + c.cost, 0) });
  }
  return out.sort((a, b) => b.created - a.created);
}
