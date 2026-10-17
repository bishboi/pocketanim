/**
 * The transcription flow:
 *
 *   1. read     the book's Markdown as blocks, each with an id (blocks.ts)                      (no model)
 *   2. figures  each figure of the book described from its picture, so the writer knows what
 *               it shows, not only its caption                                                 (1 call per figure)
 *   3. write    the lectures, in order, each written as its script in one call: its chapters
 *               (title card, stage, the book's blocks each teaches from: chapters may share
 *               them) and beats (the sentences said, what is on screen, the figures shown: a
 *               figure may be on several beats). Each call is given the whole book, each block
 *               marked taught or not, and every lecture before it whole, and writes the next
 *               lecture, ending where it judges; until the book is taught.                     (1 call per lecture)
 *
 * Runs made before (a planner, goals, a patch, then a script step) are read as they are: their lectures and scripts.
 *
 * Each call is recorded whole (llm.ts) with what code found when it read the reply.
 */

import { readFile } from "node:fs/promises";
import path from "node:path";
import { datalabBlocks, figureFile, kindOf, type Block } from "./source/blocks";
import type { RawBlock } from "./datalab";
import { cleanSection, linesOf } from "./source/book";
import { WRITE_TOOL, lectureSystem, writePrompt } from "./prompts/build";
import { part } from "./prompts/parts";
import { callTool } from "./llm";
import { modelFor } from "./models";
import { documentInfo, loadRun, newId, saveRun } from "./store";
import { bookOf, markPictures } from "./docs";
import type { Beat, Call, Chapter, Check, LectureState, Options, Run, Step, StepKey } from "./types";
import type { Prompt } from "./prompts/parts";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "read", label: "Read the book" },
  { key: "figures", label: "Describe figures" },
  { key: "write", label: "Write lectures (chapters, beats)" },
];
const ORDER: StepKey[] = STEPS.map((s) => s.key);

/** What runs on each run right now (a run's transcript and its triage are each one job at a time). */
const shared = globalThis as unknown as { __v2jobs?: Set<string>; __v2stop?: Set<string> };
export const jobs = (shared.__v2jobs ??= new Set<string>());
const stopping = (shared.__v2stop ??= new Set<string>());

/** Thrown between calls when the page asked a job to stop. */
export class Stopped extends Error {}
export function stopRequested(key: string): boolean {
  return stopping.has(key);
}
export function clearStop(key: string) {
  stopping.delete(key);
}

/**
 * A new run. `until` stops it after that step (the book read, or its figures described too), for the figure triage
 * without a transcript; Continue builds the rest later.
 */
export async function startRun(documentId: string, asked: Partial<Options>, until?: StepKey): Promise<Run> {
  const info = await documentInfo(documentId);
  const options: Options = {
    lectureMinutes: asked.lectureMinutes && asked.lectureMinutes >= 3 ? asked.lectureMinutes : 27,
    language: asked.language ?? "auto",
    subject: asked.subject ?? "",
    // Kept for runs made before (a planner, a script step); new runs use neither.
    plannerModel: asked.plannerModel || modelFor("planner"),
    writerModel: asked.writerModel || modelFor("writer"),
    figureModel: asked.figureModel || modelFor("figure"),
    triageModel: asked.triageModel || modelFor("triage"),
    triageChatModel: asked.triageChatModel || modelFor("triageChat"),
    scriptModel: asked.scriptModel || modelFor("script"),
    imageModel: asked.imageModel || modelFor("image"),
    svgModel: asked.svgModel || modelFor("svg"),
    manimModel: asked.manimModel || modelFor("manim"),
    mapModel: asked.mapModel || modelFor("map"),
    effort: asked.effort ?? "medium",
    writerEffort: asked.writerEffort ?? "high",
  };
  const run: Run = {
    id: newId(), documentId, documentName: info.name, created: Date.now(), status: "running", options,
    steps: STEPS.map((s): Step => ({ ...s, status: "waiting" })), blocks: [], skipped: [], lectures: [], goalStatus: {},
    calls: [], log: [],
  };
  saveRun(run, true);
  launch(run, until && ORDER.includes(until) ? until : undefined);
  return run;
}

/**
 * A run picked up where it stopped (failed, stopped, cut off by a server restart): every step's saved result is kept
 * and only what is not done yet is done: figures not described, the plan if there is none, lectures not written.
 * The models and effort may be changed for what is left.
 */
export async function continueRun(id: string, asked: Partial<Options> = {}): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (run.legacy) throw new Error(run.legacy);
  if (jobs.has(`${id}:transcript`)) throw new Error("this run's transcript is already being made");
  for (const k of ["writerEffort", "plannerModel", "writerModel", "figureModel", "triageModel", "triageChatModel", "imageModel", "svgModel", "manimModel", "mapModel", "effort", "language"] as const) {
    if (asked[k]) (run.options as Record<string, unknown>)[k] = asked[k];
  }
  log(run, "Continued: the steps done are kept; what is left is done now.");
  launch(run);
  return run;
}

/** A step made again: its saved result and every later step's are cleared, then the run continues from it. */
export async function redoFrom(id: string, key: StepKey, asked: Partial<Options> = {}): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (run.legacy) throw new Error(run.legacy);
  if (jobs.has(`${id}:transcript`)) throw new Error("stop the run before making a step again");
  const from = ORDER.indexOf(key);
  if (from < 0) throw new Error("no such step");
  for (const s of run.steps.slice(from)) Object.assign(s, { status: "waiting", started: undefined, ended: undefined, summary: undefined });
  if (from <= ORDER.indexOf("read")) run.blocks = [];
  if (from <= ORDER.indexOf("figures")) for (const b of run.blocks) delete b.description;
  if (from <= ORDER.indexOf("write")) {
    // The lectures are the writer's (and their scripts): written again from the first.
    run.lectures = [];
    run.skipped = [];
    run.goalStatus = {};
    run.script = undefined;
  }
  log(run, `Step "${run.steps[from].label}" and the ones after it cleared, to be made again.`);
  return continueRun(id, asked);
}

/** Ask a running job to stop after the call it is in. */
export function stopJob(id: string, job: "transcript" | "triage" | "generate" | "script" | "scenes") {
  if (jobs.has(`${id}:${job}`)) stopping.add(`${id}:${job}`);
}

function launch(run: Run, until?: StepKey) {
  const key = `${run.id}:transcript`;
  jobs.add(key);
  stopping.delete(key);
  run.status = "running";
  run.error = undefined;
  run.ended = undefined;
  saveRun(run, true);
  void (async () => {
    try {
      const book = await bookOf(run.documentId);
      if (run.blocks.length && markPictures(run.blocks, book)) log(run, "The book's figure pictures were found again: the figure blocks are marked anew.");
      await flow(run, book, until);
      run.status = until ? "stopped" : "done";
      if (until) log(run, `Stopped after "${run.steps.find((s) => s.key === until)?.label}", as asked: Continue builds the transcript.`);
    } catch (error) {
      const stopped = error instanceof Stopped;
      run.status = stopped ? "stopped" : "failed";
      run.error = stopped ? "Stopped from the page. Continue picks it up from here." : (error as Error).message;
      for (const s of run.steps) if (s.status === "running") s.status = stopped ? "waiting" : "failed";
      for (const l of run.lectures) if (l.status === "writing") l.status = "waiting";
      log(run, stopped ? "Stopped." : `Failed: ${run.error}`);
    } finally {
      jobs.delete(key);
      stopping.delete(key);
      run.ended = Date.now();
      saveRun(run, true);
    }
  })();
}

export function log(run: Run, text: string) {
  run.log.push({ t: Date.now(), text });
  saveRun(run);
}

function step(run: Run, key: StepKey, status: Step["status"], summary?: string) {
  const s = run.steps.find((x) => x.key === key)!;
  if (status === "running") s.started = Date.now();
  if (status === "done" || status === "failed") s.ended = Date.now();
  s.status = status;
  if (summary !== undefined) s.summary = summary;
  saveRun(run);
}

export function newCall(run: Run, o: { step: string; label: string; lecture?: number; block?: string; model: string; prompt: Prompt;
  effort?: string }): Call {
  const call: Call = { id: `c${run.calls.length + 1}`, step: o.step, label: o.label, lecture: o.lecture, block: o.block, model: o.model,
    effort: o.effort ?? run.options.effort, status: "running", started: Date.now(), attempts: [], prompt: o.prompt, cost: 0,
    provider: "openrouter", checks: [] };
  run.calls.push(call);
  if (o.lecture) run.lectures.find((l) => l.n === o.lecture)?.calls.push(call.id);
  saveRun(run);
  return call;
}

export const check = (call: Call, name: string, result: Check["result"], detail: string) => call.checks.push({ name, result, detail });

/** A figure's file as a data URL, for a model that reads images. */
export async function imageData(file: string): Promise<string | undefined> {
  try {
    const ext = path.extname(file).toLowerCase().replace(".", "").replace("jpg", "jpeg") || "png";
    return `data:image/${ext};base64,${(await readFile(file)).toString("base64")}`;
  } catch {
    return undefined;
  }
}

/** Each step skips what it already has, so a run continued after a stop or a failure does only what is left. */
async function flow(run: Run, book: { json: RawBlock; figures: Record<string, string> }, until?: StepKey) {
  const o = run.options;
  const subject = o.subject || undefined;
  const halt = () => {
    if (stopping.has(`${run.id}:transcript`)) throw new Stopped();
  };
  const done = (key: StepKey) => run.steps.find((s) => s.key === key)?.status === "done";

  // 1. Read: Datalab's JSON, its blocks in page order ─────────────────────────────────────────────────────────
  if (!done("read") || !run.blocks.length) {
    step(run, "read", "running");
    run.blocks = datalabBlocks(book.json, book.figures);
    const types = new Map<string, number>();
    for (const b of run.blocks) types.set(b.type, (types.get(b.type) ?? 0) + 1);
    step(run, "read", "done", `${run.blocks.length} blocks: ${[...types.entries()].sort((a, b) => b[1] - a[1]).map(([t, n]) => `${n} ${t}`).join(", ")}`);
    if (!run.blocks.some((b) => kindOf(b.type) === "heading")) log(run, "Datalab found no SectionHeader in the book: the writer divides it by its text alone.");
  }
  if (until === "read") return;

  // 2. Figures: each picture Datalab cut out, described for the writer (those not described yet) ─────────────
  if (!done("figures")) {
    step(run, "figures", "running");
    const pictures = run.blocks.map((b) => ({ block: b, file: b.image ? figureFile(b, book.json, book.figures) : undefined }))
      .filter((x): x is { block: Block; file: string } => !!x.file);
    const left = pictures.filter((p) => !p.block.description);
    if (left.length < pictures.length) log(run, `${pictures.length - left.length} figure(s) already described: kept.`);
    await Promise.all(left.map(async ({ block, file }) => {
      halt();
      await describeFigure(run, block, file, subject);
    }));
    halt();
    const figureBlocks = run.blocks.filter((b) => kindOf(b.type) === "figure").length;
    step(run, "figures", "done", pictures.length ? `${run.blocks.filter((b) => b.description).length} of ${pictures.length} figures described`
      : figureBlocks ? `${figureBlocks} figure blocks, no picture of them: their captions only` : "no figures");
  }
  if (until === "figures") return;

  // 3. Write, in order: each lecture as its script, given the book (each block taught or not) and every lecture
  // before it; the writer decides where each ends. Lectures written are kept (Continue writes the next ones).
  if (run.steps.some((s) => s.key === "plan")) {
    // A run made before: its lectures were planned; what is written stays, nothing is written the old way.
    if (run.lectures.some((l) => l.status !== "written")) throw new Error("This run was made by an earlier version (planned lectures, goals): build a new run to write the rest.");
    return;
  }
  step(run, "write", "running");
  const system = lectureSystem(o.language, subject);
  const kept = run.lectures.filter((l) => l.status === "written").length;
  if (kept) log(run, `${kept} lecture(s) already written: kept.`);
  // Each lecture is written from the ones before it: what is kept is the written ones up to the first that is not;
  // from there on (and their scripts) the lectures are written again.
  const cut = run.lectures.findIndex((l) => l.status !== "written");
  if (cut >= 0) {
    for (const l of run.lectures.slice(cut)) if (run.script) delete run.script.lectures[l.n];
    run.lectures = run.lectures.slice(0, cut);
  }
  for (let n = run.lectures.length + 1; n <= MAX_LECTURES; n++) {
    halt();
    const left = notTaught(run);
    if (!left.length) break;
    const out = await writeLecture(run, n, system);
    if (out === "failed") throw new Error(`Lecture ${n} could not be written: see its call.`);
    step(run, "write", "running", `${run.lectures.length} lecture(s) written; ${notTaught(run).length} block(s) not taught yet`);
    // The writer says the book is done, or this lecture taught nothing new: stop (what is left is said).
    if (out === "done" || notTaught(run).length === left.length) break;
  }
  const left = notTaught(run);
  const script = run.script!;
  const chapters = Object.values(script?.lectures ?? {}).reduce((k, l) => k + l.chapters.length, 0);
  const beats = Object.values(script?.lectures ?? {}).reduce((k, l) => k + l.chapters.reduce((j, c) => j + c.beats.length, 0), 0);
  if (left.length) log(run, `${left.length} block(s) of the book not taught by any lecture: ${left.slice(0, 20).map((b) => b.id).join(", ")}`);
  step(run, "write", run.lectures.length ? "done" : "failed",
    `${run.lectures.length} lecture(s), ${chapters} chapters, ${beats} beats${left.length ? `; ${left.length} block(s) not taught` : "; the whole book taught"}`);
}

/** At most this many lectures a run (a safety stop; the writer ends when the book is taught). */
const MAX_LECTURES = Math.max(1, Number(process.env.V2_MAX_LECTURES) || 40);

/** The book's blocks no lecture has taught yet (headings and furniture aside, the skipped too). */
function notTaught(run: Run): Run["blocks"] {
  const taught = new Set(Object.values(run.script?.lectures ?? {}).flatMap((l) => l.chapters.flatMap((c) => [...(c.content ?? []), ...c.beats.flatMap((b) => b.figures ?? [])])));
  const skipped = new Set(run.skipped.map((s) => s.block));
  return run.blocks.filter((b) => !taught.has(b.id) && !skipped.has(b.id) && kindOf(b.type) !== "furniture" && kindOf(b.type) !== "heading");
}

// ─── Figures ─────────────────────────────────────────────────────────────────────────────────────────────────────

const DESCRIBE_TOOL = {
  type: "function" as const,
  function: {
    name: "describe_figure",
    description: "Save what the figure shows, for a teacher who cannot see it.",
    parameters: {
      type: "object",
      properties: {
        description: { type: "string", description: "What the figure shows: its parts, labels, arrows, numbers and what it teaches, in 2-5 sentences." },
      },
      required: ["description"],
      additionalProperties: false,
    },
  },
};

async function describeFigure(run: Run, block: Block, file: string, subject?: string) {
  const caption = run.blocks.find((b) => b.page === block.page && kindOf(b.type) === "caption" && b.box[1] >= block.box[1] - 0.02)?.text;
  const call = newCall(run, { step: "figure", label: `Describe ${block.id}`, block: block.id, model: run.options.figureModel, prompt: {
    system: [part("role", "Role", "rules", "You describe a textbook's figure for a teacher planning lectures, who cannot see it. Say what it " +
      "shows: its parts, labels, arrows, numbers and what it teaches. Only what is in the figure.")],
    user: [
      ...(subject ? [part("subject", "Subject", "context", `The subject is ${subject}.`)] : []),
      part("block", "The figure's block", "book", `The figure ${block.id}${caption || block.text ? `, captioned: ${caption || block.text}` : ""}`),
      part("image", "The figure (picture)", "book", `[the picture is attached: /api/documents/${run.documentId}/figure/${encodeURIComponent(block.id)}]`),
      part("ask", "Request", "ask", "Describe it (describe_figure)."),
    ],
  } });
  const image = await imageData(file);
  const reply = await callTool({ call, tool: DESCRIBE_TOOL, images: image ? [image] : [], onChange: () => saveRun(run),
    fake: () => ({ description: `A figure of ${caption || block.text || block.id}, its parts labelled as in the book.` }) });
  const words = String(reply?.description ?? "").trim();
  if (words) {
    block.description = words.slice(0, 900);
    check(call, "Description", "pass", `${words.split(/\s+/).length} words`);
  } else {
    check(call, "Description", "fail", "no description: the plan has the caption only");
  }
  saveRun(run);
}

// ─── Lectures ────────────────────────────────────────────────────────────────────────────────────────────────────

type RawBeat = { say?: unknown; show?: unknown; figures?: unknown };
type RawChapter = { title?: unknown; narration?: unknown; map?: unknown; content?: unknown; beats?: unknown };

/**
 * One lecture written as its script by one call (prompts/build.ts), read against the book by code: a block id that
 * is not the book's is dropped, a figure that is not one of its figures is dropped, a figure shown is in its
 * chapter's content, a beat's words are only words (headings and bracket lines out), a sentence an earlier lecture
 * already said is taken out, an empty beat or chapter goes; the sentences are numbered through the lecture. Asked
 * again once when nothing usable comes back. "done" when the writer says the book is taught.
 */
async function writeLecture(run: Run, n: number, system: Prompt["system"]): Promise<"written" | "done" | "failed"> {
  const o = run.options;
  const byId = new Map(run.blocks.map((b) => [b.id, b]));
  const figureIds = new Set(run.blocks.filter((b) => b.image || kindOf(b.type) === "figure").map((b) => b.id));
  const taught = new Map<string, number[]>();
  for (const l of run.lectures) {
    for (const c of run.script?.lectures[l.n]?.chapters ?? []) {
      for (const id of [...(c.content ?? []), ...c.beats.flatMap((b) => b.figures ?? [])]) taught.set(id, [...new Set([...(taught.get(id) ?? []), l.n])]);
    }
  }
  const previous = run.lectures.map((l) => ({ n: l.n, title: l.title, chapters: (run.script?.lectures[l.n]?.chapters ?? []).map((c) => ({ title: c.title,
    says: c.beats.map((b) => b.lines.map((k) => linesOf(l.text ?? "")[k - 1] ?? "").join(" ")) })) }));
  const said = new Set(run.lectures.flatMap((l) => linesOf(l.text ?? "")).map(norm));
  const state: LectureState = { n, title: `Lecture ${n}`, why: "", blocks: [], goals: [], status: "writing", calls: [] };
  run.lectures.push(state);
  saveRun(run);
  let note: string | undefined;
  for (let attempt = 1; attempt <= 2; attempt++) {
    const call = newCall(run, { step: "lecture", label: `Lecture ${n}${attempt > 1 ? ` (try ${attempt})` : ""}`, lecture: n, model: o.writerModel,
      effort: o.writerEffort ?? "high",
      prompt: writePrompt({ n, blocks: run.blocks, taught, skipped: new Set(run.skipped.map((x) => x.block)), lectureMinutes: o.lectureMinutes, system, previous, note }) });
    const reply = await callTool({ call, tool: WRITE_TOOL, onChange: () => saveRun(run), fake: () => fakeWrite(run, taught) });
    const rawChapters = (Array.isArray(reply?.chapters) ? reply!.chapters : []) as RawChapter[];
    let unknownContent = 0, unknownFigures = 0, addedContent = 0, cleanedLines = 0, repeated = 0;
    const sentences: string[] = [];
    const chapters: Chapter[] = [];
    for (const rc of rawChapters) {
      const content = [...new Set((Array.isArray(rc.content) ? rc.content : []).map(String))].filter((id) => byId.has(id) || (unknownContent++, false));
      const beats: Beat[] = [];
      for (const rb of (Array.isArray(rc.beats) ? rc.beats : []) as RawBeat[]) {
        const raw = String(rb?.say ?? "").trim();
        const words = cleanSection(raw);
        if (linesOf(raw).length !== linesOf(words).length) cleanedLines += linesOf(raw).length - linesOf(words).length;
        const lines = linesOf(words).filter((x) => (said.has(norm(x)) ? (repeated++, false) : true));
        if (!lines.length) continue;
        const figures = [...new Set((Array.isArray(rb.figures) ? rb.figures : []).map(String))].filter((id) => figureIds.has(id) || (unknownFigures++, false));
        for (const f of figures) if (!content.includes(f)) { content.push(f); addedContent++; }
        const first = sentences.length + 1;
        for (const x of lines) { sentences.push(/[.?!।]$/.test(x) ? x : `${x}.`); said.add(norm(x)); }
        beats.push({ n: 0, lines: lines.map((_, i) => first + i), show: String(rb.show ?? "").trim().slice(0, 200), ...(figures.length ? { figures } : {}) });
      }
      if (!beats.length) continue;
      const map = rc.map === true || beats.some((b) => (b.figures ?? []).some((f) => wayOfFigure(run, f) === "map"));
      chapters.push({ n: chapters.length + 1, title: String(rc.title ?? "").trim().slice(0, 100) || `Chapter ${chapters.length + 1}`,
        narration: String(rc.narration ?? "").trim().slice(0, 200) || `Chapter ${chapters.length + 1}. ${String(rc.title ?? "").trim()}.`, map, content, beats });
    }
    if (!chapters.length) {
      check(call, "Chapters", "fail", "no chapter with a beat with words: asked again");
      note = "it had no chapter with beats that say something.";
      continue;
    }
    let bn = 0;
    for (const c of chapters) for (const b of c.beats) b.n = ++bn;
    const words = sentences.join(" ").split(/\s+/).length;
    check(call, "Script", "pass", `${chapters.length} chapter(s), ${bn} beats, ${sentences.length} sentences, ${words} words (about ${Math.round(words / 130)} min)`);
    if (cleanedLines) check(call, "Only spoken words", "fixed", `${cleanedLines} heading or bracket line(s) taken out of beats`);
    if (repeated) check(call, "Not said before", "fixed", `${repeated} sentence(s) already said (here or in an earlier lecture) taken out`);
    if (unknownContent) check(call, "Content", "fixed", `${unknownContent} id(s) that are not the book's blocks dropped`);
    if (unknownFigures) check(call, "Figures", "fixed", `${unknownFigures} id(s) that are not the book's figures dropped`);
    if (addedContent) check(call, "Content", "fixed", `${addedContent} figure(s) shown on a beat added to its chapter's content`);
    const content = [...new Set(chapters.flatMap((c) => c.content ?? []))];
    const shared = content.filter((id) => chapters.filter((c) => (c.content ?? []).includes(id)).length > 1).length;
    const again = content.filter((id) => taught.has(id)).length;
    check(call, "Content", "info", `${content.length} block(s) taught from${shared ? `, ${shared} shared by chapters` : ""}${again ? `, ${again} taught in an earlier lecture too` : ""}`);
    const multi = [...new Set(chapters.flatMap((c) => c.beats.flatMap((b) => b.figures ?? [])))]
      .filter((f) => chapters.flatMap((c) => c.beats).filter((b) => (b.figures ?? []).includes(f)).length > 1).length;
    if (multi) check(call, "Figures", "info", `${multi} figure(s) shown on several beats`);
    const skipped = (Array.isArray(reply?.skipped) ? reply!.skipped as { block?: unknown; reason?: unknown }[] : [])
      .map((x) => ({ block: String(x?.block ?? ""), reason: String(x?.reason ?? "furniture") })).filter((x) => byId.has(x.block) && !content.includes(x.block));
    for (const x of skipped) if (!run.skipped.some((y) => y.block === x.block)) run.skipped.push(x);
    Object.assign(state, { title: String(reply?.title ?? "").trim() || `Lecture ${n}`, why: String(reply?.about ?? "").trim(), blocks: content,
      text: chapters.map((c) => c.beats.map((b) => b.lines.map((k) => sentences[k - 1]).join(" ")).join("\n")).join("\n\n"), status: "written" });
    const lineCount = linesOf(state.text!).length;
    if (lineCount !== sentences.length) check(call, "Sentences", "fail", `the text reads as ${lineCount} sentences, the beats name ${sentences.length}`);
    run.script ??= { status: "done", model: o.writerModel, rounds: 0, lectures: {} };
    Object.assign(run.script, { status: "done", model: o.writerModel });
    run.script.lectures[n] = { lecture: n, status: "done", chapters, lines: sentences.length, checks: call.checks, calls: [call.id], at: Date.now() };
    saveRun(run);
    return reply?.done === true ? "done" : "written";
  }
  state.status = "failed";
  saveRun(run);
  return "failed";
}

const norm = (x: string) => x.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();

/** A figure's way (the triage's, or chosen by hand), when it has one. */
function wayOfFigure(run: Run, id: string): string | undefined {
  const f = run.triage?.figures[id];
  return f?.override ?? (f?.status === "done" ? f.kind : undefined);
}

// ─── Offline stand-ins (no key): enough to drive the flow and the page ───────────────────────────────────────────

/**
 * The stand-in writer (no key): the next lecture from the first block not taught, a lecture's worth of the book cut at
 * a section header; a chapter per header (its blocks its content, the next chapter sharing its last block), a beat
 * of two sentences, each figure shown on the beat that reaches it and pointed at again on the next.
 */
function fakeWrite(run: Run, taught: Map<string, number[]>) {
  const target = run.options.lectureMinutes * 100;
  const skipped = new Set(run.skipped.map((x) => x.block));
  const start = run.blocks.findIndex((b) => !taught.has(b.id) && !skipped.has(b.id) && kindOf(b.type) !== "furniture" && kindOf(b.type) !== "heading");
  const own: Block[] = [];
  let words = 0;
  for (const b of run.blocks.slice(Math.max(0, start - 1))) {
    if (kindOf(b.type) === "furniture") continue;
    if (own.length && kindOf(b.type) === "heading" && words >= target * 0.6) break;
    if (taught.has(b.id) && kindOf(b.type) !== "heading") continue;
    own.push(b);
    words += b.text.split(/\s+/).length;
  }
  const chapters: { title: string; narration: string; map: boolean; content: string[]; beats: { say: string; show: string; figures?: string[] }[] }[] = [];
  for (const b of own) {
    if (!chapters.length || kindOf(b.type) === "heading") {
      const last = chapters.at(-1)?.content.at(-1);
      chapters.push({ title: kindOf(b.type) === "heading" ? b.text.slice(0, 60) : "Introduction", narration: `Chapter ${chapters.length + 1}.`, map: false,
        content: last ? [last] : [], beats: [] });
    }
    const c = chapters.at(-1)!;
    if (!c.content.includes(b.id)) c.content.push(b.id);
    if (kindOf(b.type) === "heading") continue;
    if (b.image || kindOf(b.type) === "figure") {
      c.beats.push({ say: `Look at this figure: ${(b.description ?? b.text).replace(/[.?!]+$/, "")}.`, show: "the figure", figures: [b.id] });
      c.beats.push({ say: "Look again at its parts, one by one.", show: "the figure again, a part ringed", figures: [b.id] });
      continue;
    }
    const sentences = b.text.split(/(?<=[.?!])\s+/).filter((x) => /[\p{L}]/u.test(x)).slice(0, 4);
    for (let i = 0; i < sentences.length; i += 2) c.beats.push({ say: sentences.slice(i, i + 2).join(" "), show: "the key point on the board" });
  }
  if (chapters[0]) chapters[0].beats.unshift({ say: run.lectures.length ? "Let us pick up where we left off." : "Imagine you are sitting in class with this page open in front of you.", show: "the title" });
  const rest = run.blocks.filter((b) => !taught.has(b.id) && !skipped.has(b.id) && !own.includes(b) && kindOf(b.type) !== "furniture" && kindOf(b.type) !== "heading");
  return { title: chapters[0]?.title ?? "A lecture", about: "one topic, whole", chapters: chapters.filter((c) => c.beats.length),
    skipped: run.blocks.filter((b) => kindOf(b.type) === "furniture" && !skipped.has(b.id)).map((b) => ({ block: b.id, reason: "page furniture" })),
    done: !rest.length };
}
