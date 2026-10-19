/**
 * A map drawn and rendered by v2's lecture engine (harness_v2/engine, a copy of v1's): the map model's answer made
 * into a one-chapter beat script, checked and compiled by the engine's compile_lecture.py (its lint names what is
 * wrong: an unknown place, an op it cannot draw), the scene's title slide and closing fade taken out (a figure is the
 * map itself), and rendered silent (no voice) with Manim: its last frame and its video.
 *
 * Map operations are data, not code: nothing the model writes is run.
 */

import { existsSync } from "node:fs";
import path from "node:path";
import { renderScene, runPython, type Rendered } from "./manim";
import { REPO } from "./store";

/** The ops a map figure may use (the engine's map operations; pictures on markers are left out). */
const MAP_OPS = new Set(["marker", "river", "path", "arrow", "state", "dim", "graticule", "journey", "empire", "relief"]);

/** v2's engine: V2_ENGINE, else harness_v2/engine beside the app. */
export function engineDir(): string {
  if (process.env.V2_ENGINE) return process.env.V2_ENGINE;
  for (const dir of [path.resolve(process.cwd(), "..", "engine"), path.join(REPO, "harness_v2", "engine")]) {
    if (existsSync(path.join(dir, "compile_lecture.py"))) return dir;
  }
  return path.join(REPO, "harness_v2", "engine");
}

const ENV = () => ({ PYTHONPATH: engineDir(), PANIM_VOICE: "silent", LECTURE_STYLE: "atlas" });

export type MapAnswer = { region?: unknown; title?: unknown; beats?: unknown };

/** The model's answer as the engine's beat script, and what code took out of it. */
export function mapScript(a: MapAnswer): { script: Record<string, unknown>; dropped: string[] } {
  const dropped: string[] = [];
  const beats = (Array.isArray(a.beats) ? a.beats : []).map((b, k) => {
    const beat = (b ?? {}) as { say?: unknown; do?: unknown };
    const ops = (Array.isArray(beat.do) ? beat.do : []).filter((op): op is Record<string, unknown> => {
      const kind = String((op as { op?: unknown })?.op ?? "");
      if (MAP_OPS.has(kind)) return true;
      dropped.push(`beat ${k + 1}: "${kind || "(no op)"}" is not a map operation`);
      return false;
    }).map((op) => {
      const { picture, pictures, ...rest } = op;
      if (picture !== undefined || pictures !== undefined) dropped.push(`beat ${k + 1}: a picture on a ${String(op.op)} (no pictures here)`);
      return rest;
    });
    return { say: String(beat.say ?? "").trim() || "Here it is on the map.", do: ops };
  }).filter((b) => b.do.length);
  const title = String(a.title ?? "").trim().slice(0, 80) || "The map";
  const region = a.region && typeof a.region === "object" ? a.region : { area: "World" };
  return { script: { title, style: "atlas", art: "auto", region, chapters: [{ title, narration: title, map: true, beats }] }, dropped };
}

/** The engine's check and compile of a script: its errors and warnings, and the scene's source when it has none. */
export async function compileMap(script: Record<string, unknown>, dir: string): Promise<{ source?: string; errors: string[]; warnings: string[] }> {
  const out = await runPython([path.join(engineDir(), "compile_lecture.py"), "-", "--json"], dir, ENV(), JSON.stringify(script), 180_000);
  try {
    const json = JSON.parse(out.stdout.slice(out.stdout.indexOf("{"))) as { source?: string | null; errors?: string[]; warnings?: string[] };
    return { source: json.source ?? undefined, errors: json.errors ?? [], warnings: json.warnings ?? [] };
  } catch {
    const tail = out.out.split("\n").filter(Boolean).slice(-6).join("\n");
    return { errors: [/No module named/.test(out.out) ? `the engine could not run: ${tail}` : `the engine's compile failed: ${tail}`], warnings: [] };
  }
}

/**
 * What makes a compiled map unusable: the engine's errors, and a scene with no map in it (the engine mends a script by
 * leaving out what it cannot draw, so a map whose operations all failed compiles to a bare board), with the engine's
 * notes on what it left out.
 */
export function mapProblems(compiled: { source?: string; errors: string[]; warnings: string[] }): string[] {
  if (compiled.errors.length) return compiled.errors;
  if (!compiled.source) return ["the engine made no scene of it"];
  if (!/self\.(?:show_map|map_in)\(/.test(compiled.source)) {
    return ["nothing was drawn on a map", ...compiled.warnings.filter((w) => /left out|unknown|not found|no place/i.test(w))];
  }
  return [];
}

/** The compiled scene as a figure: no title slide, no closing fade (its last frame is the whole map). */
export function asFigure(source: string): string {
  return source.split("\n").filter((l) => !/self\.(title_slide|outro_fade)\(/.test(l)).join("\n");
}

export async function renderMap(source: string, dir: string): Promise<Rendered> {
  return renderScene(asFigure(source), "GeneratedScene", dir, ENV());
}
