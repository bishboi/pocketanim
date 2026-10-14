/**
 * The map agent (harness/lecture/map_agent.py): before a lecture is compiled, the places its map names that the
 * gazetteers do not know (a chain of shoals, a climate zone, a country's own name for its highlands) are found by a
 * model of their own, with web search, OpenStreetMap, Wikidata and the map country's provinces, and put in the
 * script's "places", which the compiler and the render read. Its model is PANIM_MAP_MODEL, else PANIM_MANIM_MODEL,
 * else OPENROUTER_MODEL; PANIM_MAP_AGENT=off turns it off. What it found is kept (harness/lecture/.cache), so a
 * rebuild asks nothing again, and each run's log is kept in harness/app/.logs/map-*.json.
 */

import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { REPO, run } from "./pocketanim";

export type MapReport = {
  ok: boolean;
  names: number;
  found_here: number;
  asked: string[];
  resolved: Record<string, { lonlat?: number[]; states?: string[]; outline?: number[][]; source?: string; from?: string }>;
  gave_up: Record<string, string>;
  usd: number;
  model: string | null;
  seconds?: number;
  errors: string[];
  summary?: string;
  error?: string;
  log?: string;
};

/** The names each script was last checked with: a part compiled again with the same map asks nothing. */
const checked = new Map<string, string>();

const MAP_OPS = new Set(["marker", "state", "relief", "journey", "arrow", "path", "icon"]);

/** The map's names in a script, as a key: unchanged, the agent need not run again. */
function mapKey(script: Record<string, unknown>): string | null {
  if (!script.region || typeof script.region !== "object") return null;
  const names: string[] = [];
  const chapters = Array.isArray(script.chapters) ? (script.chapters as Record<string, unknown>[]) : [];
  for (const chapter of chapters) {
    for (const beat of (Array.isArray(chapter?.beats) ? chapter.beats : []) as Record<string, unknown>[]) {
      for (const op of (Array.isArray(beat?.do) ? beat.do : []) as Record<string, unknown>[]) {
        if (op && MAP_OPS.has(String(op.op))) names.push(JSON.stringify([op.op, op.place, op.name, op.names, op.stops, op.points, op.places]));
      }
    }
  }
  return names.length ? JSON.stringify([script.region, names.sort()]) : null;
}

/** Finds the script's unfound map places and puts them in script.places (in place). Null when there was nothing
 * to do. Never throws: a failure is in the report, and the lecture goes on (the names it could not place are left
 * off the map, as before). */
export async function resolvePlaces(script: Record<string, unknown>): Promise<MapReport | null> {
  if (["off", "0", "no"].includes((process.env.PANIM_MAP_AGENT ?? "on").trim().toLowerCase())) return null;
  const key = mapKey(script);
  if (!key) return null;
  const id = String(script.title ?? "");
  if (checked.get(id) === key) return null;
  const dir = await mkdtemp(path.join(tmpdir(), "panim-map-"));
  try {
    const input = path.join(dir, "script.json");
    await writeFile(input, JSON.stringify(script), "utf8");
    const { stdout, stderr } = await run([path.join(REPO, "harness", "lecture", "map_agent.py"), input], { timeoutMs: 900_000 });
    const line = stdout.toString().trim().split("\n").pop() ?? "";
    let report: MapReport;
    try {
      report = JSON.parse(line) as MapReport;
    } catch {
      const tail = stderr.trim().split("\n").slice(-4).join("\n");
      console.warn("[map] failed:", tail);
      return { ok: false, names: 0, found_here: 0, asked: [], resolved: {}, gave_up: {}, usd: 0, model: null,
        errors: [tail.slice(-400) || "the map step failed"] };
    }
    if (!report.ok) {
      console.warn(`[map] not run: ${report.error ?? "unknown"}`);
      return { ...report, resolved: {}, gave_up: {}, asked: [], errors: [report.error ?? "not run"] };
    }
    const out = JSON.parse(await readFile(input, "utf8")) as Record<string, unknown>;
    if (out.places && typeof out.places === "object") script.places = out.places;
    checked.set(id, key);
    try {
      const logs = path.join(REPO, "harness", "app", ".logs");
      await mkdir(logs, { recursive: true });
      report.log = path.join(logs, `map-${new Date().toISOString().replace(/[:.]/g, "-")}.json`);
      await writeFile(report.log, await readFile(`${input}.map.json`, "utf8"));
    } catch {
      report.log = undefined;
    }
    if (report.names) console.log(`[map] ${report.summary ?? ""}${report.log ? ` (${report.log})` : ""}`);
    return report;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
