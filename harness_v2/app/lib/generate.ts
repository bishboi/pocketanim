/**
 * Generation, the step after the triage: every figure triaged Exact or Styled redraw (or set so by hand) is redrawn
 * by the image model from the book's figure, with the redraw prompt (prompts/redraw.ts: v1's, with no text in the image
 * and gentler words; asked gentler still, then without the reference image, when a model's moderation blocks it). Each figure keeps the
 * prompt it was sent, as its parts, the image made, and its calls; everything is saved in the run as it comes.
 *
 *   run     generate every redraw figure not generated yet
 *   reset   forget every generated image and generate them all again
 *   one     generate one figure again
 *
 * Only the redraws for now; the other ways (Manim, map, SVG, photo) are built by steps to come. v1 then checked a
 * redraw's labels against the book's and drew it again with what was wrong; that check is not here yet.
 */

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { bookOf } from "./docs";
import { callImage } from "./images";
import { modelFor } from "./models";
import { BLOCKED, REDRAW_LEVELS, redrawParts, redrawText } from "./prompts/redraw";
import { SVG_TOOL, checkSvg, standInSvg, svgPrompt } from "./prompts/svg";
import { callTool } from "./llm";
import { check, clearStop, imageData, jobs, log, newCall, stopJob, stopRequested } from "./run";
import { captionOf, figureFile, kindOf, type Block } from "./source/blocks";
import { DATA, loadRun, saveRun } from "./store";
import type { TriageKind } from "./triage-kinds";
import type { FigureGeneration, Generation, Run } from "./types";

const AT_ONCE = Math.max(1, Number(process.env.V2_GENERATE_PARALLEL) || 3);
/** The ways this step generates. */
export const GENERATED: TriageKind[] = ["exact", "styled", "svg"];

export type GenerateAction =
  | { action: "run" | "reset"; model?: string; svgModel?: string }
  | { action: "one"; block: string; model?: string; svgModel?: string }
  | { action: "stop" };

/** A figure's way as it stands: chosen by hand, else the triage's. */
export function wayOf(run: Run, block: string): TriageKind | undefined {
  const f = run.triage?.figures[block];
  return f?.override ?? (f?.status === "done" ? f.kind : undefined);
}

/** The figures this step redraws. */
export function toGenerate(run: Run): Block[] {
  return run.blocks.filter((b) => b.image && GENERATED.includes(wayOf(run, b.id) as TriageKind));
}

export function generatedFile(runId: string, block: string, ext = "png"): string {
  return path.join(DATA, "runs", runId, "generated", `${block.replace(/[^\w]+/g, "_")}.${ext}`);
}

export async function generateAction(id: string, a: GenerateAction): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (a.action === "stop") {
    stopJob(id, "generate");
    return run;
  }
  if (run.legacy) throw new Error(run.legacy);
  if (!run.triage) throw new Error("triage the figures first: generation redraws the figures triaged Exact or Styled redraw");
  if (jobs.has(`${id}:generate`)) throw new Error("the generation is already running");
  const gen: Generation = run.generation ?? { status: "idle", model: "", rounds: 0, figures: {} };
  gen.model = a.model || gen.model || run.options.imageModel || modelFor("image");
  gen.svgModel = a.svgModel || gen.svgModel || run.options.svgModel || modelFor("svg");
  run.generation = gen;
  const figures = toGenerate(run);
  if (!figures.length) throw new Error("no figure is triaged Exact redraw, Styled redraw or SVG drawing");
  let todo: Block[];
  if (a.action === "reset") {
    gen.figures = Object.fromEntries(Object.entries(gen.figures).map(([b, f]) => [b, { block: b, status: "waiting", calls: f.calls } as FigureGeneration]));
    todo = figures;
    log(run, `Generation reset: every generated image cleared; all ${figures.length} redrawn again.`);
  } else if (a.action === "one") {
    const b = figures.find((x) => x.id === a.block);
    if (!b) throw new Error("that figure is not triaged as a redraw");
    todo = [b];
  } else {
    todo = figures.filter((b) => gen.figures[b.id]?.status !== "done" || gen.figures[b.id]?.kind !== wayOf(run, b.id));
    if (!todo.length) throw new Error("every redraw is generated: reset to generate them all again, or regenerate one");
  }
  for (const b of todo) gen.figures[b.id] = { block: b.id, status: "waiting", calls: gen.figures[b.id]?.calls ?? [] };
  gen.rounds += 1;
  launch(run, todo);
  return run;
}

function launch(run: Run, todo: Block[]) {
  const key = `${run.id}:generate`;
  const gen = run.generation!;
  jobs.add(key);
  clearStop(key);
  Object.assign(gen, { status: "running", error: undefined, started: Date.now(), ended: undefined });
  saveRun(run, true);
  void (async () => {
    try {
      const book = await bookOf(run.documentId);
      const queue = [...todo];
      const worker = async () => {
        while (queue.length && !stopRequested(key)) await generateFigure(run, queue.shift()!, book);
      };
      await Promise.all(Array.from({ length: Math.min(AT_ONCE, queue.length) }, worker));
      const all = Object.values(gen.figures);
      const failed = all.filter((f) => f.status === "failed").length;
      if (stopRequested(key)) {
        gen.status = "stopped";
        log(run, "Generation stopped: the images made are kept; Generate does the rest.");
      } else {
        gen.status = failed && failed === all.length ? "failed" : "done";
        if (failed) gen.error = `${failed} figure(s) could not be generated: see each one's error, and regenerate them.`;
      }
    } catch (error) {
      gen.status = "failed";
      gen.error = (error as Error).message;
      log(run, `Generation failed: ${gen.error}`);
    } finally {
      for (const f of Object.values(gen.figures)) if (f.status === "running") f.status = "waiting";
      jobs.delete(key);
      clearStop(key);
      gen.ended = Date.now();
      saveRun(run, true);
    }
  })();
}

async function generateFigure(run: Run, block: Block, book: Awaited<ReturnType<typeof bookOf>>) {
  const gen = run.generation!;
  const state = gen.figures[block.id];
  const kind = wayOf(run, block.id)!;
  Object.assign(state, { status: "running", error: undefined, kind });
  const file = figureFile(block, book.json, book.figures);
  const reference = file ? await imageData(file) : undefined;
  if (!reference) {
    Object.assign(state, { status: "failed", error: "the book's figure could not be read" });
    saveRun(run);
    return;
  }
  // What the prompt says of the figure: its caption, else what the figures step saw; what it is for: its lecture,
  // the goals it is under, the book's words around it; the triage's note when a chat model gave one.
  const i = run.blocks.indexOf(block);
  // The prompt puts its own full stop after the caption.
  const caption = captionOf(run.blocks, block)?.replace(/[.\s]+$/, "");
  const lecture = run.lectures.find((l) => l.blocks.includes(block.id));
  const goals = lecture?.goals.filter((g) => g.blocks.includes(block.id)).map((g) => g.goal) ?? [];
  const around = [...run.blocks.slice(Math.max(0, i - 2), i), ...run.blocks.slice(i + 1, i + 3)]
    .filter((b) => b.page === block.page && kindOf(b.type) === "text" && !(caption && b.text.startsWith(caption))).map((b) => b.text).join(" ");
  const context = [lecture ? `Lecture "${lecture.title}"${goals.length ? `, to teach: ${goals.join("; ")}` : ""}.` : "", around].filter(Boolean).join(" ");
  const t = run.triage?.figures[block.id];
  if (kind === "svg") return drawSvg(run, block, state, reference, { caption, context, how: t?.how });
  // Asked in full; when the model's moderation blocks it, in gentler words; then with no reference image at all.
  for (const level of REDRAW_LEVELS) {
    const blind = level === "blind";
    const parts = redrawParts({ caption: caption || block.description || block.text, description: block.description, context, how: t?.how, level });
    const text = redrawText(parts);
    const call = newCall(run, { step: "generate", label: `Redraw ${block.id} (${kind === "exact" ? "Exact" : "Styled"}${level === "full" ? "" : `, ${level}`})`,
      block: block.id, model: gen.model, effort: "off", prompt: { system: [], user: [...parts, ...(blind ? [] : [
        { key: "reference", label: "The book's figure (reference image)", kind: "book" as const, text: `[attached before the words: /api/documents/${run.documentId}/figure/${encodeURIComponent(block.id)}]` }])] } });
    state.calls.push(call.id);
    state.prompt = text;
    const out = await callImage({ call, text, reference: blind ? undefined : reference, onChange: () => saveRun(run),
      fake: () => {
        // The stand-in answers as a moderating model would when its name says so ("fixture-moderated"), to try the
        // gentler asks offline; else it gives the book's figure back.
        if (gen.model.includes("moderated") && !blind) throw new Error('400 {"error":{"message":"Azure MAI blocked this request through content moderation.","code":400}}');
        return { bytes: Buffer.from(reference.split(",")[1], "base64"), mime: reference.slice(5, reference.indexOf(";")) };
      } });
    if (!out) {
      const next = REDRAW_LEVELS[REDRAW_LEVELS.indexOf(level) + 1];
      if (next && BLOCKED.test(call.error ?? "")) {
        check(call, "Moderation", "fixed", `blocked by the model's moderation: asked again ${next === "gentle" ? "in gentler words" : "with no reference image, from what the figure shows"}`);
        continue;
      }
      Object.assign(state, { status: "failed", error: `the call failed: ${call.error ?? "no image"}`, at: Date.now(), level });
      saveRun(run);
      return;
    }
    const ext = out.mime.includes("jpeg") ? "jpg" : out.mime.includes("webp") ? "webp" : "png";
    const target = generatedFile(run.id, block.id, ext);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, out.bytes);
    const url = `/api/runs/${run.id}/generated/${encodeURIComponent(block.id)}?v=${Date.now()}`;
    call.output = { image: url, bytes: out.bytes.length, mime: out.mime };
    check(call, "Image", "pass", `${Math.round(out.bytes.length / 1024)} kB ${out.mime}${call.provider === "fixture" ? " (the stand-in returns the book's figure)" : ""}`);
    Object.assign(state, { status: "done", file: target, url, at: Date.now(), level });
    saveRun(run);
    return;
  }
}

/**
 * A figure triaged SVG: the SVG model is shown the book's figure and writes the SVG from it, in one call (no other
 * model describes it first), with v1's SVG prompt. Code checks it against v1's rules; what breaks them goes back to
 * the same model once, and the better of the two is kept.
 */
async function drawSvg(run: Run, block: Block, state: FigureGeneration, reference: string,
  x: { caption?: string; context?: string; how?: string }) {
  const gen = run.generation!;
  let retry: string[] | undefined;
  let best: { svg: string; problems: string[]; parts: string[]; shapes: number; animated: boolean } | undefined;
  for (let attempt = 1; attempt <= 2; attempt++) {
    const prompt = svgPrompt({ documentId: run.documentId, blockId: block.id, page: block.page, caption: x.caption, context: x.context, how: x.how, retry });
    const call = newCall(run, { step: "generate", label: `SVG ${block.id}${attempt > 1 ? " (again, with what broke the rules)" : ""}`,
      block: block.id, model: gen.svgModel!, effort: "off", prompt });
    state.calls.push(call.id);
    const reply = await callTool({ call, tool: SVG_TOOL, images: [reference], onChange: () => saveRun(run),
      fake: () => ({ svg: standInSvg(x.caption ?? block.text), parts: ["subject", "label"] }) });
    const raw = String(reply?.svg ?? call.text ?? "");
    if (!raw.includes("<svg")) {
      check(call, "SVG", "fail", call.error ? `the call failed: ${call.error}` : "the answer had no SVG");
      if (call.error) break;
      retry = ["your answer had no <svg>…</svg>: give the whole SVG in draw_svg"];
      continue;
    }
    const got = checkSvg(raw);
    check(call, "SVG rules", got.problems.length ? "fail" : "pass", got.problems.length ? got.problems.join("; ")
      : `${got.shapes} shapes, ${got.parts.length} parts${got.animated ? ", animated" : ""}, ${Math.round(got.svg.length / 1024)} KB`);
    if (!best || got.problems.length < best.problems.length) best = got;
    if (!got.problems.length) break;
    retry = got.problems;
  }
  if (!best) {
    const last = run.calls.find((c) => c.id === state.calls[state.calls.length - 1]);
    Object.assign(state, { status: "failed", error: last?.error ? `the call failed: ${last.error}` : "no SVG was drawn", at: Date.now() });
    saveRun(run);
    return;
  }
  const target = generatedFile(run.id, block.id, "svg");
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, best.svg, "utf8");
  const url = `/api/runs/${run.id}/generated/${encodeURIComponent(block.id)}?v=${Date.now()}`;
  const last = run.calls.find((c) => c.id === state.calls[state.calls.length - 1]);
  if (last) last.output = { ...(last.output as object), image: url };
  Object.assign(state, { status: "done", file: target, url, at: Date.now(), level: undefined, svgParts: best.parts,
    svgProblems: best.problems.length ? best.problems : undefined, prompt: undefined });
  saveRun(run);
}
