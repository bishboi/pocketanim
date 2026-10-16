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
import { MANIM_TOOL, manimPrompt, standInManim } from "./prompts/manim";
import { checkManim, renderManim } from "./manim";
import { MAP_TOOL, mapPrompt, standInMap } from "./prompts/map";
import { compileMap, mapProblems, mapScript, renderMap } from "./maps";
import { copyFile } from "node:fs/promises";
import { callTool } from "./llm";
import { check, clearStop, imageData, jobs, log, newCall, stopJob, stopRequested } from "./run";
import { captionOf, figureFile, kindOf, type Block } from "./source/blocks";
import { cleanLook, lookWords, styleOf } from "./styles";
import { DATA, loadRun, saveRun } from "./store";
import type { TriageKind } from "./triage-kinds";
import type { FigureGeneration, Generation, Run } from "./types";

const AT_ONCE = Math.max(1, Number(process.env.V2_GENERATE_PARALLEL) || 3);
/** The ways this step generates. */
export const GENERATED: TriageKind[] = ["exact", "styled", "svg", "manim", "map"];

export type GenerateAction =
  | { action: "run" | "reset"; model?: string; svgModel?: string; manimModel?: string; mapModel?: string }
  | { action: "one"; block: string; model?: string; svgModel?: string; manimModel?: string; mapModel?: string }
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

/**
 * What is being generated now: each figure on its own (a figure is generated once at a time; any number of figures
 * at once), and how many batches each run has going. Kept on globalThis, as the runs are (store.ts).
 */
const shared = globalThis as unknown as { __v2genBusy?: Set<string>; __v2genActive?: Map<string, number> };
const busy = (shared.__v2genBusy ??= new Set<string>());
const active = (shared.__v2genActive ??= new Map<string, number>());
const busyKey = (run: string, block: string) => `${run}|${block}`;

export async function generateAction(id: string, a: GenerateAction): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (a.action === "stop") {
    stopJob(id, "generate");
    return run;
  }
  if (run.legacy) throw new Error(run.legacy);
  if (!run.triage) throw new Error("no figure has a way yet: triage the figures, or choose a way under Generate as");
  const gen: Generation = run.generation ?? { status: "idle", model: "", rounds: 0, figures: {} };
  gen.model = a.model || gen.model || run.options.imageModel || modelFor("image");
  gen.svgModel = a.svgModel || gen.svgModel || run.options.svgModel || modelFor("svg");
  gen.manimModel = a.manimModel || gen.manimModel || run.options.manimModel || modelFor("manim");
  gen.mapModel = a.mapModel || gen.mapModel || run.options.mapModel || modelFor("map");
  run.generation = gen;
  const figures = toGenerate(run);
  if (!figures.length) throw new Error("no figure is triaged Exact redraw, Styled redraw, SVG drawing, Manim or Map");
  // Figures being generated now go on; the others are free to start, alone or together.
  const free = (b: Block) => !busy.has(busyKey(id, b.id));
  let todo: Block[];
  if (a.action === "reset") {
    todo = figures.filter(free);
    for (const b of todo) gen.figures[b.id] = { block: b.id, status: "waiting", calls: gen.figures[b.id]?.calls ?? [] };
    log(run, `Generation reset: ${todo.length} figure(s) cleared and generated again${todo.length < figures.length ? ` (${figures.length - todo.length} being generated already go on)` : ""}.`);
  } else if (a.action === "one") {
    const b = figures.find((x) => x.id === a.block);
    if (!b) throw new Error("that figure is not triaged Exact or Styled redraw, SVG drawing or Manim");
    if (!free(b)) throw new Error("that figure is being generated already");
    todo = [b];
  } else {
    todo = figures.filter((b) => free(b) && (gen.figures[b.id]?.status !== "done" || gen.figures[b.id]?.kind !== wayOf(run, b.id)));
    if (!todo.length) throw new Error("every figure is generated or being generated: reset to generate them all again, or regenerate one");
  }
  if (!todo.length) throw new Error("every figure is being generated already");
  for (const b of todo) {
    busy.add(busyKey(id, b.id));
    gen.figures[b.id] = { ...(gen.figures[b.id] ?? { calls: [] }), block: b.id, status: "waiting", calls: gen.figures[b.id]?.calls ?? [] };
  }
  gen.rounds += 1;
  launch(run, todo);
  return run;
}

/** One batch (one figure, or several): runs beside any other batch of the run; the run's generation is running while any is. */
function launch(run: Run, todo: Block[]) {
  const key = `${run.id}:generate`;
  const gen = run.generation!;
  const first = !active.get(run.id);
  active.set(run.id, (active.get(run.id) ?? 0) + 1);
  jobs.add(key);
  if (first) {
    clearStop(key);
    Object.assign(gen, { status: "running", error: undefined, started: Date.now(), ended: undefined });
  }
  saveRun(run, true);
  void (async () => {
    try {
      const book = await bookOf(run.documentId);
      const queue = [...todo];
      const worker = async () => {
        for (let b = queue.shift(); b; b = queue.shift()) {
          if (stopRequested(key)) {
            busy.delete(busyKey(run.id, b.id));
            continue;
          }
          try {
            await generateFigure(run, b, book);
          } finally {
            busy.delete(busyKey(run.id, b.id));
            const f = gen.figures[b.id];
            if (f?.status === "running") f.status = "waiting";
            saveRun(run);
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(AT_ONCE, queue.length) }, worker));
    } catch (error) {
      gen.error = (error as Error).message;
      log(run, `Generation failed: ${gen.error}`);
      for (const b of todo) busy.delete(busyKey(run.id, b.id));
    } finally {
      const left = (active.get(run.id) ?? 1) - 1;
      if (left > 0) active.set(run.id, left);
      else {
        // The last batch of the run: the generation's status says how it all went.
        active.delete(run.id);
        const all = Object.values(gen.figures);
        const failed = all.filter((f) => f.status === "failed").length;
        if (stopRequested(key)) {
          gen.status = "stopped";
          log(run, "Generation stopped: what was made is kept; Generate does the rest.");
        } else if (gen.error && !all.some((f) => f.status === "done")) {
          gen.status = "failed";
        } else {
          gen.status = failed && failed === all.length ? "failed" : "done";
          gen.error = failed ? `${failed} figure(s) could not be generated: see each one's error, and regenerate them.` : undefined;
        }
        jobs.delete(key);
        clearStop(key);
        gen.ended = Date.now();
      }
      saveRun(run, true);
    }
  })();
}

/** Whether a figure of a run is being generated now (for the page). */
export function generating(runId: string): string[] {
  return [...busy].filter((k) => k.startsWith(`${runId}|`)).map((k) => k.slice(runId.length + 1));
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
  if (kind === "manim") return drawManim(run, block, state, reference, { caption, context, how: t?.how });
  if (kind === "map") return drawMap(run, block, state, reference, { caption, context, how: t?.how });
  // Asked in full; when the model's moderation blocks it, in gentler words; then with no reference image at all.
  for (const level of REDRAW_LEVELS) {
    const blind = level === "blind";
    const look = cleanLook(run.scenes?.look);
    const parts = redrawParts({ caption: caption || block.description || block.text, description: block.description, context, how: t?.how, level,
      background: run.scenes ? styleOf(look.style).background : undefined, look: kind === "styled" ? lookWords(look) : undefined });
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

/**
 * A figure triaged Manim: the Manim model is shown the book's figure and writes its Manim code in the same call,
 * with v1's Manim rules; the code is checked and rendered with the repo's Manim (manim.ts): the last frame and a
 * short video. A refused or failed render goes back to the same model once, with the error, as v1's coder did.
 */
async function drawManim(run: Run, block: Block, state: FigureGeneration, reference: string,
  x: { caption?: string; context?: string; how?: string }) {
  const gen = run.generation!;
  let retry: { code: string; error: string } | undefined;
  const work = path.join(path.dirname(generatedFile(run.id, block.id)), `${block.id.replace(/[^\w]+/g, "_")}.manim`);
  for (let attempt = 1; attempt <= 2; attempt++) {
    const prompt = manimPrompt({ documentId: run.documentId, blockId: block.id, page: block.page, caption: x.caption, context: x.context, how: x.how, retry });
    const call = newCall(run, { step: "generate", label: `Manim ${block.id}${attempt > 1 ? " (again, with the error)" : ""}`,
      block: block.id, model: gen.manimModel!, effort: "off", prompt });
    state.calls.push(call.id);
    const reply = await callTool({ call, tool: MANIM_TOOL, images: [reference], onChange: () => saveRun(run),
      fake: () => ({ code: standInManim(x.caption ?? block.text) }) });
    const code = String(reply?.code ?? "").replace(/^```(?:python)?\n?|```\s*$/g, "").trim();
    if (!code) {
      check(call, "Code", "fail", call.error ? `the call failed: ${call.error}` : "the answer had no code");
      if (call.error) break;
      retry = { code: "(none)", error: "your answer had no code: give the body of construct() in write_manim" };
      continue;
    }
    state.code = code;
    const problems = checkManim(code);
    if (problems.length) {
      check(call, "Rules", "fail", problems.join("; "));
      retry = { code, error: problems.join("\n") };
      state.error = `refused before running: ${problems.join("; ")}`;
      continue;
    }
    check(call, "Rules", "pass", `${code.split("\n").length} lines`);
    state.status = "running";
    saveRun(run);
    const out = await renderManim(code, work);
    if (!out.png) {
      check(call, "Render", "fail", out.error ?? "no frame");
      retry = { code, error: out.error ?? "the render failed" };
      state.error = `the render failed: ${(out.error ?? "").split("\n").slice(-2).join(" ")}`;
      if (/not installed/.test(out.error ?? "")) break;
      continue;
    }
    const png = generatedFile(run.id, block.id, "png");
    await mkdir(path.dirname(png), { recursive: true });
    await copyFile(out.png, png);
    let video: string | undefined;
    if (out.mp4) {
      video = generatedFile(run.id, block.id, "mp4");
      await copyFile(out.mp4, video);
    }
    check(call, "Render", out.mp4 ? "pass" : "info", `rendered in ${out.seconds.toFixed(1)} s${out.mp4 ? ": its last frame and its video" : `: the last frame only (${out.error})`}`);
    const url = `/api/runs/${run.id}/generated/${encodeURIComponent(block.id)}?v=${Date.now()}`;
    call.output = { ...(call.output as object), image: url };
    Object.assign(state, { status: "done", file: png, video, url, at: Date.now(), error: undefined, level: undefined, prompt: undefined });
    saveRun(run);
    return;
  }
  Object.assign(state, { status: "failed", error: state.error ?? "no Manim code was written", at: Date.now() });
  saveRun(run);
}

/**
 * A figure triaged Map: the map model is shown the book's map and writes it as a short map script in the same call
 * (region, title, a few beats of map operations); v2's engine checks and compiles it (what it refuses goes back to the
 * same model once) and renders it silent: the last frame and the video, as for Manim.
 */
async function drawMap(run: Run, block: Block, state: FigureGeneration, reference: string,
  x: { caption?: string; context?: string; how?: string }) {
  const gen = run.generation!;
  let retry: { script: string; errors: string[] } | undefined;
  const work = path.join(path.dirname(generatedFile(run.id, block.id)), `${block.id.replace(/[^\w]+/g, "_")}.map`);
  await mkdir(work, { recursive: true });
  for (let attempt = 1; attempt <= 2; attempt++) {
    const prompt = mapPrompt({ documentId: run.documentId, blockId: block.id, page: block.page, caption: x.caption, context: x.context, how: x.how, retry });
    const call = newCall(run, { step: "generate", label: `Map ${block.id}${attempt > 1 ? " (again, with what the engine refused)" : ""}`,
      block: block.id, model: gen.mapModel!, effort: "off", prompt });
    state.calls.push(call.id);
    const reply = await callTool({ call, tool: MAP_TOOL, images: [reference], onChange: () => saveRun(run),
      fake: () => standInMap(x.caption ?? block.text) });
    if (!reply) {
      check(call, "Map", "fail", `the call failed: ${call.error ?? "no reply"}`);
      state.error = `the call failed: ${call.error ?? "no reply"}`;
      break;
    }
    const { script, dropped } = mapScript(reply);
    state.mapScript = script;
    if (dropped.length) check(call, "Map operations", "fixed", `taken out: ${dropped.join("; ")}`);
    const beats = ((script.chapters as { beats: unknown[] }[])[0]?.beats ?? []).length;
    if (!beats) {
      check(call, "Map operations", "fail", "no beat has a map operation");
      retry = { script: JSON.stringify(reply), errors: ["no beat has a map operation: give each beat 1 to 4 map operations"] };
      state.error = "the map had no map operations";
      continue;
    }
    const compiled = await compileMap(script, work);
    if (compiled.warnings.length) check(call, "Engine warnings", "info", compiled.warnings.slice(0, 6).join("; "));
    const problems = mapProblems(compiled);
    if (problems.length || !compiled.source) {
      check(call, "Engine check", "fail", problems.slice(0, 8).join("; "));
      retry = { script: JSON.stringify(script), errors: problems };
      state.error = `the engine refused it: ${problems.slice(0, 3).join("; ")}`;
      if (problems.some((e) => /could not run/.test(e))) break;
      continue;
    }
    check(call, "Engine check", "pass", `${beats} beat(s) compiled`);
    state.status = "running";
    saveRun(run);
    const out = await renderMap(compiled.source, path.join(work, "render"));
    if (!out.png) {
      check(call, "Render", "fail", out.error ?? "no frame");
      retry = { script: JSON.stringify(script), errors: [out.error ?? "the render failed"] };
      state.error = `the render failed: ${(out.error ?? "").split("\n").slice(-2).join(" ")}`;
      if (/not installed/.test(out.error ?? "")) break;
      continue;
    }
    const png = generatedFile(run.id, block.id, "png");
    await copyFile(out.png, png);
    let video: string | undefined;
    if (out.mp4) {
      video = generatedFile(run.id, block.id, "mp4");
      await copyFile(out.mp4, video);
    }
    check(call, "Render", out.mp4 ? "pass" : "info", `rendered in ${out.seconds.toFixed(1)} s${out.mp4 ? ": its last frame and its video" : `: the last frame only (${out.error})`}`);
    const url = `/api/runs/${run.id}/generated/${encodeURIComponent(block.id)}?v=${Date.now()}`;
    call.output = { ...(call.output as object), image: url };
    Object.assign(state, { status: "done", file: png, video, url, at: Date.now(), error: undefined, level: undefined, prompt: undefined, code: undefined });
    saveRun(run);
    return;
  }
  Object.assign(state, { status: "failed", error: state.error ?? "no map was made", at: Date.now() });
  saveRun(run);
}
