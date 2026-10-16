/**
 * The transcription flow:
 *
 *   1. read     the book's Markdown as blocks, each with an id (blocks.ts)                      (no model)
 *   2. figures  each figure of the book described from its picture, so the plan knows what
 *               it shows, not only its caption                                                 (1 call per figure)
 *   3. plan     the whole book (blocks, figure descriptions) divided into lectures by what is
 *               learned, and each lecture's goals mapped: block ids only, checked by code      (1 call)
 *   4. write    each lecture's transcript, in order, from its blocks and goals, with every
 *               lecture before it given whole; what it left out written in by one patch       (1-2 calls per lecture)
 *
 * Each call is recorded whole (llm.ts) with what code found when it read the reply.
 */

import { readFile } from "node:fs/promises";
import path from "node:path";
import { datalabBlocks, figureFile, kindOf, type Block } from "./source/blocks";
import type { RawBlock } from "./datalab";
import { cleanSection, linesOf } from "./source/book";
import { dropRepeats } from "./source/repeats";
import { PLAN_TOOL, goalLine, readPlan, type Lecture } from "./plan";
import { LECTURE_TOOL, PATCH_TOOL, lecturePrompt, lectureSystem, patchPrompt, planPrompt } from "./prompts/build";
import { part } from "./prompts/parts";
import { callTool } from "./llm";
import { modelFor } from "./models";
import { documentBook, documentInfo, loadRun, newId, saveRun } from "./store";
import type { Call, Check, LectureState, Options, Run, Step, StepKey } from "./types";
import type { Prompt } from "./prompts/parts";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "read", label: "Read the book" },
  { key: "figures", label: "Describe figures" },
  { key: "plan", label: "Plan lectures and goals" },
  { key: "write", label: "Write lectures" },
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

export async function startRun(documentId: string, asked: Partial<Options>): Promise<Run> {
  const info = await documentInfo(documentId);
  const options: Options = {
    lectureMinutes: asked.lectureMinutes && asked.lectureMinutes >= 3 ? asked.lectureMinutes : 27,
    language: asked.language ?? "auto",
    subject: asked.subject ?? "",
    plannerModel: asked.plannerModel || modelFor("planner"),
    writerModel: asked.writerModel || modelFor("writer"),
    figureModel: asked.figureModel || modelFor("figure"),
    triageModel: asked.triageModel || modelFor("triage"),
    imageModel: asked.imageModel || modelFor("image"),
    svgModel: asked.svgModel || modelFor("svg"),
    manimModel: asked.manimModel || modelFor("manim"),
    mapModel: asked.mapModel || modelFor("map"),
    effort: asked.effort ?? "medium",
  };
  const run: Run = {
    id: newId(), documentId, documentName: info.name, created: Date.now(), status: "running", options,
    steps: STEPS.map((s): Step => ({ ...s, status: "waiting" })), blocks: [], skipped: [], lectures: [], goalStatus: {},
    calls: [], log: [],
  };
  saveRun(run, true);
  launch(run);
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
  if (jobs.has(`${id}:transcript`)) throw new Error("this run's transcript is already being made");
  for (const k of ["plannerModel", "writerModel", "figureModel", "triageModel", "imageModel", "svgModel", "manimModel", "mapModel", "effort", "language"] as const) {
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
  if (jobs.has(`${id}:transcript`)) throw new Error("stop the run before making a step again");
  const from = ORDER.indexOf(key);
  if (from < 0) throw new Error("no such step");
  for (const s of run.steps.slice(from)) Object.assign(s, { status: "waiting", started: undefined, ended: undefined, summary: undefined });
  if (from <= ORDER.indexOf("read")) run.blocks = [];
  if (from <= ORDER.indexOf("figures")) for (const b of run.blocks) delete b.description;
  if (from <= ORDER.indexOf("plan")) {
    run.lectures = [];
    run.skipped = [];
    run.goalStatus = {};
  }
  if (from <= ORDER.indexOf("write")) {
    for (const l of run.lectures) {
      Object.assign(l, { status: "waiting", text: undefined, goalLines: undefined, blocksTaught: undefined, patched: undefined, dropped: undefined });
    }
    for (const g of Object.keys(run.goalStatus)) run.goalStatus[g] = "waiting";
  }
  log(run, `Step "${run.steps[from].label}" and the ones after it cleared, to be made again.`);
  return continueRun(id, asked);
}

/** Ask a running job to stop after the call it is in. */
export function stopJob(id: string, job: "transcript" | "triage") {
  if (jobs.has(`${id}:${job}`)) stopping.add(`${id}:${job}`);
}

function launch(run: Run) {
  const key = `${run.id}:transcript`;
  jobs.add(key);
  stopping.delete(key);
  run.status = "running";
  run.error = undefined;
  run.ended = undefined;
  saveRun(run, true);
  void (async () => {
    try {
      const book = await documentBook(run.documentId);
      await flow(run, book);
      run.status = "done";
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
async function flow(run: Run, book: { json: RawBlock; figures: Record<string, string> }) {
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
    if (!run.blocks.some((b) => kindOf(b.type) === "heading")) log(run, "Datalab found no SectionHeader in the book: the planner divides it by its text alone.");
  }

  // 2. Figures: each picture Datalab cut out, described for the planner (those not described yet) ─────────────
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

  // 3. Plan ─────────────────────────────────────────────────────────────────────────────────────────────────────
  if (!done("plan") || !run.lectures.length) {
    halt();
    step(run, "plan", "running");
    const planCall = newCall(run, { step: "plan", label: "Plan the lectures and their goals", model: o.plannerModel,
      prompt: planPrompt(run.blocks, o.lectureMinutes, subject) });
    const raw = await callTool({ call: planCall, tool: PLAN_TOOL, onChange: () => saveRun(run),
      fake: () => fakePlan(run.blocks, o.lectureMinutes) });
    if (!raw) throw new Error(`The lectures could not be planned: ${planCall.error ?? "no reply"}`);
    const { plan, checks } = readPlan(raw, run.blocks);
    planCall.checks.push(...checks);
    if (!plan.lectures.length) throw new Error("The plan had no lectures.");
    run.skipped = plan.skipped;
    run.lectures = plan.lectures.map((l): LectureState => ({ ...l, status: "waiting", calls: [] }));
    run.goalStatus = {};
    for (const g of plan.lectures.flatMap((l) => l.goals)) run.goalStatus[g.id] = "waiting";
    step(run, "plan", "done", `${plan.lectures.length} lecture${plan.lectures.length > 1 ? "s" : ""}, ` +
      `${plan.lectures.reduce((n, l) => n + l.goals.length, 0)} goals${plan.skipped.length ? `, ${plan.skipped.length} blocks skipped as furniture` : ""}`);
  }

  // 4. Write, in order: each lecture is given every lecture before it (those written are kept) ──────────────────
  step(run, "write", "running");
  const system = lectureSystem(o.language, subject);
  const kept = run.lectures.filter((l) => l.status === "written").length;
  if (kept) log(run, `${kept} lecture(s) already written: kept.`);
  for (const lecture of run.lectures) {
    if (lecture.status === "written") continue;
    halt();
    await writeLecture(run, lecture, run.lectures, system);
    step(run, "write", "running", `${run.lectures.filter((l) => l.status === "written").length} of ${run.lectures.length} written`);
  }
  const statuses = Object.values(run.goalStatus);
  const n = (s: string) => statuses.filter((x) => x === s).length;
  const missingBlocks = run.lectures.reduce((k, l) => k + l.blocks.filter((b) => !(l.blocksTaught ?? []).includes(b)).length, 0);
  step(run, "write", run.lectures.every((l) => l.status === "failed") ? "failed" : "done",
    `${run.lectures.filter((l) => l.status === "written").length} of ${run.lectures.length} written; goals: ${n("taught")} taught, ` +
    `${n("patched")} written in after, ${n("missing")} missing; ${missingBlocks} block(s) not reported taught`);
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

async function writeLecture(run: Run, lecture: Lecture, lectures: Lecture[], system: Prompt["system"]) {
  const state = run.lectures.find((l) => l.n === lecture.n)!;
  state.status = "writing";
  saveRun(run);
  const byId = new Map(run.blocks.map((b) => [b.id, b]));
  const previous = run.lectures.filter((l) => l.n < lecture.n && l.text).map((l) => ({ n: l.n, title: l.title, text: l.text! }));
  let note: string | undefined;
  for (let attempt = 1; attempt <= 2; attempt++) {
    const call = newCall(run, { step: "lecture", label: `Lecture ${lecture.n}: ${lecture.title}${attempt > 1 ? ` (try ${attempt})` : ""}`,
      lecture: lecture.n, model: run.options.writerModel,
      prompt: lecturePrompt({ lecture, lectures, blocks: run.blocks, system, previous, note }) });
    const reply = await callTool({ call, tool: LECTURE_TOOL, onChange: () => saveRun(run),
      fake: () => fakeLecture(lecture, run.blocks) });
    const rawText = String(reply?.text ?? call.text ?? "").trim();
    if (!rawText) {
      check(call, "Has text", "fail", "the reply had no text: asked again");
      note = "your reply had no text.";
      continue;
    }
    check(call, "Has text", "pass", `${rawText.split(/\s+/).length} words, about ${Math.round(rawText.split(/\s+/).length / 100)} min`);
    let text = cleanSection(rawText);
    const removed = linesOf(rawText).length - linesOf(text).length;
    check(call, "Only spoken words", removed > 0 ? "fixed" : "pass", removed > 0 ? `${removed} heading or bracket line(s) taken out`
      : "no headings, bullets or stage directions");
    const cleaned = dropRepeats(text, previous.flatMap((p) => linesOf(p.text)));
    text = cleaned.text;
    state.dropped = cleaned.dropped;
    check(call, "Not said before", cleaned.dropped.length ? "fixed" : "pass", cleaned.dropped.length
      ? `${cleaned.dropped.length} sentence(s) already said (here or in an earlier lecture) taken out` : "no sentence said before");

    // Goals: the lecture's own, naming sentences it has; found again in the final text by their words.
    const rawLines = linesOf(rawText);
    const goalLines: Record<string, number[]> = {};
    for (const r of Array.isArray(reply?.goals_taught) ? (reply!.goals_taught as { goal?: unknown; lines?: unknown }[]) : []) {
      const id = String(r?.goal ?? "").trim();
      if (!lecture.goals.some((g) => g.id === id)) continue;
      const nums = (Array.isArray(r.lines) ? r.lines : []).map(Number).filter((k) => k >= 1 && k <= rawLines.length);
      if (!nums.length) continue;
      const final = linesOf(text);
      goalLines[id] = nums.map((k) => final.indexOf(rawLines[k - 1]) + 1).filter((k) => k > 0);
    }
    for (const g of lecture.goals) {
      if (goalLines[g.id]) run.goalStatus[g.id] = "taught";
      check(call, `Goal ${g.id}`, goalLines[g.id] ? "pass" : "fail", goalLines[g.id]
        ? `sentence${goalLines[g.id].length > 1 ? "s" : ""} ${goalLines[g.id].join(", ") || "(said before, taken out)"}: ${g.goal}`
        : `not reported taught: ${g.goal}`);
    }
    // Blocks: the lecture's own the writer says it taught.
    const said = new Set((Array.isArray(reply?.blocks_taught) ? reply!.blocks_taught : []).map(String));
    const taught = lecture.blocks.filter((id) => said.has(id));
    const untaught = lecture.blocks.filter((id) => !said.has(id) && kindOf(byId.get(id)?.type ?? "") !== "heading");
    check(call, "Blocks taught", untaught.length ? "fail" : "pass", untaught.length
      ? `${untaught.length} of the lecture's blocks not reported taught: ${untaught.slice(0, 15).join(", ")}`
      : `all ${lecture.blocks.length} blocks`);

    // What it left out, written in by one patch call, where each part fits.
    const missingGoals = lecture.goals.filter((g) => !goalLines[g.id]);
    state.patched = [];
    if (missingGoals.length || untaught.length) {
      const lines = linesOf(text);
      const pcall = newCall(run, { step: "patch", label: `Patch lecture ${lecture.n}`, lecture: lecture.n, model: run.options.writerModel,
        prompt: patchPrompt(text, { goals: missingGoals.map(goalLine), blocks: untaught.map((id) => byId.get(id)!).filter(Boolean) }) });
      const reply2 = await callTool({ call: pcall, tool: PATCH_TOOL, onChange: () => saveRun(run),
        fake: () => ({ patches: [...missingGoals.map((g) => ({ after_line: Math.min(3, lines.length), text: `Let us also see this: ${g.goal}.`, covers: [g.id, ...g.blocks] })),
          ...(untaught.length ? [{ after_line: lines.length, text: "And one more thing the book tells us here.", covers: untaught }] : [])] }) });
      const patches = (Array.isArray(reply2?.patches) ? reply2!.patches : []) as { after_line?: unknown; text?: unknown; covers?: unknown }[];
      // From the last place to the first, so earlier sentence numbers stay right while inserting.
      const sorted = patches.map((p) => ({ after: Math.max(1, Math.min(lines.length, Number(p.after_line) || lines.length)),
        words: cleanSection(String(p.text ?? "")), covers: (Array.isArray(p.covers) ? p.covers : []).map(String) }))
        .filter((p) => p.words).sort((a, b) => b.after - a.after);
      for (const p of sorted) {
        const added = linesOf(p.words).length;
        text = insertAfter(text, lines[p.after - 1], p.words);
        for (const id of Object.keys(goalLines)) goalLines[id] = goalLines[id].map((k) => (k > p.after ? k + added : k));
        for (const q of state.patched) q.lines = q.lines.map((k) => (k > p.after ? k + added : k));
        const nums = Array.from({ length: added }, (_, k) => p.after + 1 + k);
        state.patched.push({ covers: p.covers, lines: nums });
        for (const id of p.covers) {
          if (missingGoals.some((g) => g.id === id)) {
            run.goalStatus[id] = "patched";
            goalLines[id] = nums;
          }
          if (untaught.includes(id)) taught.push(id);
        }
        check(pcall, "Placed", "pass", `${added} sentence(s) after sentence ${p.after}: ${p.covers.join(", ") || "(covers nothing named)"}`);
      }
      for (const g of missingGoals) {
        if (run.goalStatus[g.id] !== "patched") {
          run.goalStatus[g.id] = "missing";
          check(pcall, `Goal ${g.id}`, "fail", "no patch covers it: it stays missing");
        }
      }
      const still = untaught.filter((id) => !taught.includes(id));
      check(pcall, "Blocks", still.length ? "fail" : "pass", still.length ? `${still.length} block(s) still not covered: ${still.join(", ")}`
        : `all ${untaught.length} left-out block(s) covered`);
    }
    state.text = text;
    state.title = String(reply?.title ?? "") || lecture.title;
    state.goalLines = goalLines;
    state.blocksTaught = [...new Set(taught)];
    state.status = "written";
    saveRun(run);
    return;
  }
  state.status = "failed";
  for (const g of lecture.goals) run.goalStatus[g.id] = "missing";
  saveRun(run);
}

function insertAfter(text: string, line: string | undefined, words: string): string {
  const at = line ? text.indexOf(line) : -1;
  if (at < 0) return `${text}\n\n${words}`;
  const end = at + line!.length;
  return `${text.slice(0, end)} ${words}${text.slice(end)}`;
}

// ─── Offline stand-ins (no key): enough to drive the flow and the page ───────────────────────────────────────────

function fakePlan(blocks: Block[], minutes: number) {
  // Lectures cut at section headers once they hold about a lecture's worth of the book; a goal per header.
  const target = minutes * 100;
  const lectures: { title: string; why: string; blocks: string[]; goals: { goal: string; blocks: string[]; misconception: string; hook: string }[] }[] = [];
  const skipped: { block: string; reason: string }[] = [];
  let words = 0;
  for (const b of blocks) {
    if (kindOf(b.type) === "furniture") { skipped.push({ block: b.id, reason: "page furniture" }); continue; }
    const header = kindOf(b.type) === "heading";
    if (!lectures.length || (header && words >= target * 0.6)) {
      lectures.push({ title: header ? b.text : "Introduction", why: "one topic, whole", blocks: [], goals: [] });
      words = 0;
    }
    const l = lectures[lectures.length - 1];
    l.blocks.push(b.id);
    words += b.text.split(/\s+/).length;
    if (header || !l.goals.length) l.goals.push({ goal: `Explain ${b.text.slice(0, 60)}`, blocks: [b.id], misconception: "", hook: "daily life" });
    else l.goals[l.goals.length - 1].blocks.push(b.id);
  }
  return { lectures, skipped };
}

function fakeLecture(lecture: Lecture, blocks: Block[]) {
  const own = blocks.filter((b) => lecture.blocks.includes(b.id) && kindOf(b.type) !== "heading");
  const sentences = own.flatMap((b) => (kindOf(b.type) === "figure" ? [`Look at this figure: ${b.description ?? b.text}.`] : b.text.split(/(?<=[.?!])\s+/).slice(0, 3)));
  const text = ["Imagine you are sitting in class with this page open in front of you.", ...sentences].join(" ")
    .replace(/(([^.?!]+[.?!]\s+){4})/g, "$1\n\n");
  const lines = linesOf(text).length;
  // The last goal is left out when there are three or more, and the last block, so the patch step is seen working.
  const goals = lecture.goals.length >= 3 ? lecture.goals.slice(0, -1) : lecture.goals;
  return { title: lecture.title, text, goals_taught: goals.map((g, k) => ({ goal: g.id, lines: [Math.min(lines, 2 + k)] })),
    blocks_taught: lecture.blocks.slice(0, -1) };
}
