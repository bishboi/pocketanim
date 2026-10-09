/**
 * The SVG lab: one educational diagram drawn by one model, exactly as a lecture's pictures are drawn
 * (drawings.ts: the same prompt, the board's checks and repairs, the look-and-fix round), but never from the
 * cache, so every model really draws it. What it cost, how long it took and how many requests it needed come back
 * with it, so models can be compared on the same diagrams.
 */
import { createHash } from "node:crypto";
import { mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { DRAW_PROMPT } from "./drawings";
import { settle, type Message } from "./figures";
import { REPO, python } from "./pocketanim";

export type LabDiagram = {
  /** What to draw, as a lecture's draw op says it. */
  what: string;
  /** The part ids it must have (each a <g id>). */
  parts: string[];
  /** What moves, if anything. */
  moves?: string;
};

export type LabResult = {
  ok: boolean;
  model: string;
  /** The drawing, where /api/picture serves it. */
  file?: string;
  usd: number;
  seconds: number;
  /** Model requests it took: the first drawing, repairs after the board's checks, and the look-and-fix round. */
  requests: number;
  bytes?: number;
  parts?: string[];
  warnings?: string[];
  animated?: boolean;
  error?: string;
};

/** An OpenRouter model id: "provider/model", optionally ":variant". */
export function validModel(model: unknown): model is string {
  return typeof model === "string" && /^[\w.\-]+\/[\w.:\-]+$/.test(model.trim());
}

/** Part ids as the board wants them: short, letters, digits and _. */
export function cleanParts(parts: unknown): string[] {
  const list = Array.isArray(parts) ? parts : String(parts ?? "").split(/[,\s]+/);
  const out = list.map((p) => String(p).trim().toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/^_+|_+$/g, ""))
    .filter((p) => p && /^[a-z]/.test(p));
  return [...new Set(out)].slice(0, 16);
}

export async function drawForLab(model: string, diagram: LabDiagram, run: string, signal?: AbortSignal):
  Promise<LabResult> {
  const key = process.env.OPENROUTER_API_KEY;
  const began = Date.now();
  const empty = { model, usd: 0, seconds: 0, requests: 0 };
  if (!key) return { ...empty, ok: false, error: "OPENROUTER_API_KEY is not set on the server" };
  const parts = cleanParts(diagram.parts);
  if (!diagram.what.trim() || !parts.length) return { ...empty, ok: false, error: "a diagram needs what to draw and its parts" };
  const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
  const digest = createHash("sha1").update(`${model}|${diagram.what}|${parts.join(",")}|${diagram.moves ?? ""}`)
    .digest("hex").slice(0, 8);
  const dir = path.join(REPO, "harness", "lecture", ".cache", "svglab", run.replace(/[^\w-]/g, "").slice(0, 40) || "run");
  await mkdir(dir, { recursive: true });
  const file = path.join(dir, `${slug(model)}--${slug(diagram.what)}-${digest}.svg`);
  const ask0 = [
    `THE PICTURE: ${diagram.what.trim()}`,
    `PARTS (each a <g id>, exactly these ids): ${parts.join(", ")}`,
    diagram.moves?.trim() ? `MOVES: ${diagram.moves.trim()}` : "MOVES: nothing (a still picture: no animation)",
    "",
    "It goes with a lesson on this topic, for a class of school students.",
  ].join("\n");
  const messages: Message[] = [{ role: "system", content: DRAW_PROMPT }, { role: "user", content: ask0 }];
  let usd = 0;
  let requests = 0;
  try {
    const made = await settle(messages, file, parts, {
      key, model, repo: REPO, python: python(), signal,
      onCost: (cost) => {
        usd += Number.isFinite(cost) ? cost : 0;
        requests += 1;
      },
    });
    const seconds = (Date.now() - began) / 1000;
    if (!made.svg || !made.check) return { ok: false, model, usd, seconds, requests, error: made.error ?? "no drawing passed the checks" };
    return {
      ok: true, model, file: made.svg, usd, seconds, requests, bytes: (await stat(made.svg)).size,
      parts: made.check.parts, warnings: made.check.warnings ?? [], animated: !!made.check.animated,
    };
  } catch (error) {
    return { ok: false, model, usd, seconds: (Date.now() - began) / 1000, requests,
      error: error instanceof Error ? error.message.slice(0, 400) : String(error).slice(0, 400) };
  }
}

/** OpenRouter's models with their prices (USD per million tokens), for the page's model picker. */
export async function labModels(): Promise<{ id: string; name: string; input: number; output: number; images: boolean }[]> {
  const response = await fetch("https://openrouter.ai/api/v1/models", { signal: AbortSignal.timeout(15_000) });
  if (!response.ok) throw new Error(`OpenRouter ${response.status}`);
  const body = (await response.json()) as { data?: { id: string; name?: string; pricing?: { prompt?: string; completion?: string };
    architecture?: { input_modalities?: string[]; output_modalities?: string[] } }[] };
  return (body.data ?? [])
    .filter((m) => (m.architecture?.output_modalities ?? ["text"]).includes("text"))
    .map((m) => ({
      id: m.id, name: m.name ?? m.id,
      input: Number(m.pricing?.prompt ?? 0) * 1e6, output: Number(m.pricing?.completion ?? 0) * 1e6,
      images: (m.architecture?.input_modalities ?? []).includes("image"),
    }))
    .sort((a, b) => a.id.localeCompare(b.id));
}
