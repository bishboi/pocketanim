/**
 * The HTTP face of Lecture Forge: every route runs the same `forge` CLI a
 * person runs, so the web page and the terminal can never disagree.
 *
 * `make` runs detached: a lecture takes minutes, and the job's state.json is
 * the progress report the page polls. A pid file marks a job as running.
 */

import { spawn } from "node:child_process";
import { existsSync, openSync, readFileSync, writeFileSync } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { REPO, python } from "@/lib/pocketanim";

export const FORGE = path.join(REPO, "harness", "forge");
export const JOBS = process.env.FORGE_JOBS ?? path.join(FORGE, "jobs");

const JOB_ID = /^[a-z0-9][a-z0-9-]{0,47}$/;

export function checkJob(id: string): string {
  if (!JOB_ID.test(id)) throw new Error("not a job id");
  const dir = path.join(JOBS, id);
  if (!existsSync(dir)) throw new Error(`no job ${id}`);
  return dir;
}

/** Run the CLI and wait: for the quick commands (new, status, revise, restyle). */
export function forge(args: string[], timeoutMs = 120_000): Promise<{ code: number; out: string; err: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(python(), ["-m", "forge", ...args], { cwd: FORGE, env: { ...process.env, FORGE_JOBS: JOBS } });
    let out = "";
    let err = "";
    child.stdout.on("data", (c) => (out += c.toString()));
    child.stderr.on("data", (c) => (err += c.toString()));
    const timer = setTimeout(() => child.kill("SIGKILL"), timeoutMs);
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code: code ?? -1, out, err });
    });
  });
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function running(id: string): boolean {
  const file = path.join(JOBS, id, "run.pid");
  if (!existsSync(file)) return false;
  const pid = parseInt(readFileSync(file, "utf8"), 10);
  return Number.isFinite(pid) && alive(pid);
}

/** Start `forge make` for a job in the background; its output goes to run.log. */
export function startMake(id: string, options: { until?: string; quality?: string; accept?: boolean } = {}): boolean {
  const dir = checkJob(id);
  if (running(id)) return false;
  const args = ["-m", "forge", "make", id];
  if (options.until && ["outline", "script", "preview"].includes(options.until)) args.push("--until", options.until);
  if (options.quality && /^[lmhk]$/.test(options.quality)) args.push("--quality", options.quality);
  if (options.accept) args.push("--accept");
  const log = openSync(path.join(dir, "run.log"), "a");
  const child = spawn(python(), args, {
    cwd: FORGE,
    env: { ...process.env, FORGE_JOBS: JOBS },
    detached: true,
    stdio: ["ignore", log, log],
  });
  writeFileSync(path.join(dir, "run.pid"), String(child.pid));
  child.unref();
  return true;
}

async function json(file: string): Promise<unknown> {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch {
    return null;
  }
}

/** Everything the page shows about a job, read straight from its folder. */
export async function jobView(id: string) {
  const dir = checkJob(id);
  const state = (await json(path.join(dir, "state.json"))) as Record<string, unknown> | null;
  const outline = (await json(path.join(dir, "outline.json"))) as { chapters?: unknown[] } | null;
  let log = "";
  try {
    log = (await readFile(path.join(dir, "forge.log"), "utf8")).split("\n").slice(-60).join("\n");
  } catch {}
  const files: string[] = [];
  for (const sub of ["out", "qa"]) {
    try {
      for (const name of await readdir(path.join(dir, sub))) {
        const info = await stat(path.join(dir, sub, name));
        if (info.isFile()) files.push(`${sub}/${name}`);
      }
    } catch {}
  }
  const spec = await readFile(path.join(dir, "job.yaml"), "utf8").catch(() => "");
  const chapters = [] as { id: string; beats: unknown[] }[];
  for (const c of (outline?.chapters ?? []) as { id: string }[]) {
    const script = (await json(path.join(dir, "script", `${c.id}.json`))) as { beats?: unknown[] } | null;
    chapters.push({ ...c, beats: script?.beats ?? [] });
  }
  return {
    id,
    running: running(id),
    state,
    spec,
    outline: outline ? { ...outline, chapters } : null,
    report: await json(path.join(dir, "qa", "report.json")),
    gates: await json(path.join(dir, "qa", "gates.json")),
    log,
    files,
  };
}

const TYPES: Record<string, string> = {
  ".mp4": "video/mp4",
  ".srt": "text/plain; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".json": "application/json",
  ".png": "image/png",
  ".zip": "application/zip",
};

/** A deliverable of a job: only out/ and qa/, only the types above. */
export function jobFile(id: string, name: string): { file: string; type: string } {
  const dir = checkJob(id);
  const file = path.resolve(dir, name);
  const rel = path.relative(dir, file);
  if (rel.startsWith("..") || !/^(out|qa)\//.test(rel)) throw new Error("not a deliverable");
  const type = TYPES[path.extname(file).toLowerCase()];
  if (!type || !existsSync(file)) throw new Error("no such file");
  return { file, type };
}

/** The libraries a job can be made from: registry.json, which `forge registry` writes. */
export async function libraries() {
  let registry = (await json(path.join(FORGE, "registry.json"))) as Record<string, unknown> | null;
  if (!registry) {
    const built = await forge(["registry"]);
    registry = JSON.parse(built.out || "{}");
  }
  return registry;
}
