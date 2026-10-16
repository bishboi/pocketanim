/**
 * The figure triage: how each of the book's figures is to be shown in the video, decided by a model that reads
 * images, one call per figure, from the ways the user allows (triage-kinds.ts). It runs apart from the transcript,
 * on any run whose book has been read, and every answer is saved in the run as it comes:
 *
 *   run       triage every figure not triaged yet (a first run, or the rest after a stop or a failure)
 *   reset     forget every decision (and the user's own choices) and triage them all again
 *   one       triage one figure again
 *
 * Code checks each answer: the way chosen must be one the user allows, with an instruction for whoever builds it.
 * A figure with no picture (Datalab cut none out) cannot be triaged and says so.
 */

import { documentBook, loadRun, saveRun } from "./store";
import { figureFile, kindOf, type Block } from "./source/blocks";
import { callTool } from "./llm";
import { modelFor } from "./models";
import { part } from "./prompts/parts";
import { DEFAULT_KINDS, TRIAGE_CHOICES, choiceOf, type TriageKind } from "./triage-kinds";
import { check, clearStop, imageData, jobs, log, newCall, stopJob, stopRequested } from "./run";
import type { FigureTriage, Run, Triage } from "./types";

const AT_ONCE = Math.max(1, Number(process.env.V2_TRIAGE_PARALLEL) || 4);

export type TriageAction =
  | { action: "run" | "reset"; kinds?: string[]; model?: string }
  | { action: "one"; block: string; kinds?: string[]; model?: string }
  | { action: "override"; block: string; kind: string | null }
  | { action: "stop" };

export function defaultTriageModel(run: Run): string {
  return run.options.triageModel || modelFor("triage");
}

/** The figures a run can triage: blocks with a picture Datalab cut out. */
export function triageable(run: Run): Block[] {
  return run.blocks.filter((b) => b.image);
}

export async function triageAction(id: string, a: TriageAction): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (a.action === "stop") {
    stopJob(id, "triage");
    return run;
  }
  if (a.action === "override") {
    const f = run.triage?.figures[a.block];
    if (!f) throw new Error("that figure has not been triaged");
    if (a.kind && !choiceOf(a.kind)) throw new Error(`no such way: ${a.kind}`);
    f.override = (a.kind || undefined) as TriageKind | undefined;
    log(run, a.kind ? `Figure ${a.block}: shown as ${choiceOf(a.kind)!.label} (chosen by hand).` : `Figure ${a.block}: back to the model's choice.`);
    saveRun(run, true);
    return run;
  }
  if (!run.blocks.length) throw new Error("the book has not been read in this run yet: build the transcript first (its first step reads it)");
  if (jobs.has(`${id}:triage`)) throw new Error("the triage is already running");
  const kinds = (a.kinds ?? run.triage?.kinds ?? DEFAULT_KINDS).filter((k): k is TriageKind => !!choiceOf(k));
  if (!kinds.length) throw new Error("choose at least one way a figure may be shown");
  const triage: Triage = run.triage ?? { status: "idle", kinds, model: "", rounds: 0, figures: {} };
  triage.kinds = kinds;
  triage.model = a.model || triage.model || defaultTriageModel(run);
  run.triage = triage;
  const figures = triageable(run);
  if (!figures.length) throw new Error("this book has no figure with a picture to triage");
  let todo: Block[];
  if (a.action === "reset") {
    // Decisions and hand choices go; each figure's past calls stay listed with it (their cost was real).
    triage.figures = Object.fromEntries(Object.entries(triage.figures).map(([id, f]) => [id, { block: id, status: "waiting", calls: f.calls }]));
    todo = figures;
    log(run, `Triage reset: every figure's decision cleared; all ${figures.length} triaged again.`);
  } else if (a.action === "one") {
    const b = figures.find((x) => x.id === a.block);
    if (!b) throw new Error("no such figure");
    todo = [b];
  } else {
    todo = figures.filter((b) => triage.figures[b.id]?.status !== "done");
    if (!todo.length) throw new Error("every figure is triaged: reset to triage them all again, or rerun one");
  }
  for (const b of todo) {
    const old = triage.figures[b.id];
    triage.figures[b.id] = { block: b.id, status: "waiting", calls: old?.calls ?? [], override: a.action === "one" ? old?.override : undefined };
  }
  triage.rounds += 1;
  launch(run, todo);
  return run;
}

function launch(run: Run, todo: Block[]) {
  const key = `${run.id}:triage`;
  const triage = run.triage!;
  jobs.add(key);
  clearStop(key);
  triage.status = "running";
  triage.error = undefined;
  triage.started = Date.now();
  triage.ended = undefined;
  saveRun(run, true);
  void (async () => {
    try {
      const book = await documentBook(run.documentId);
      const queue = [...todo];
      const worker = async () => {
        while (queue.length && !stopRequested(key)) await triageFigure(run, queue.shift()!, book);
      };
      await Promise.all(Array.from({ length: Math.min(AT_ONCE, queue.length) }, worker));
      const all = Object.values(triage.figures);
      const failed = all.filter((f) => f.status === "failed").length;
      if (stopRequested(key)) {
        triage.status = "stopped";
        log(run, "Triage stopped: what was decided is kept; Run triage does the rest.");
      } else {
        triage.status = failed && failed === all.length ? "failed" : "done";
        if (failed) triage.error = `${failed} figure(s) could not be triaged: see each one's error, and rerun them.`;
      }
    } catch (error) {
      triage.status = "failed";
      triage.error = (error as Error).message;
      log(run, `Triage failed: ${triage.error}`);
    } finally {
      for (const f of Object.values(triage.figures)) if (f.status === "running") f.status = "waiting";
      jobs.delete(key);
      clearStop(key);
      triage.ended = Date.now();
      saveRun(run, true);
    }
  })();
}

const tool = (kinds: TriageKind[]) => ({
  type: "function" as const,
  function: {
    name: "triage_figure",
    description: "Save how this figure is to be shown in the video lecture.",
    parameters: {
      type: "object",
      properties: {
        kind: { type: "string", enum: kinds, description: "The way it is shown: one of the ways offered." },
        how: { type: "string", description: "Your own short instruction (at most 40 words) for whoever builds or redraws it: what matters in it, what must stay exactly as it is, what may change." },
        reason: { type: "string", description: "One sentence: why this way and not another." },
        keep: { type: "array", items: { type: "string" }, description: "The labels, values, names and parts that must appear exactly as in the book (empty when none)." },
      },
      required: ["kind", "how", "reason", "keep"],
      additionalProperties: false,
    },
  },
});

async function triageFigure(run: Run, block: Block, book: Awaited<ReturnType<typeof documentBook>>) {
  const triage = run.triage!;
  const kinds = triage.kinds;
  const state = triage.figures[block.id];
  state.status = "running";
  state.error = undefined;
  const file = figureFile(block, book.json, book.figures);
  const image = file ? await imageData(file) : undefined;
  if (!image) {
    state.status = "failed";
    state.error = "its picture could not be read (Datalab cut none out, or the file is gone)";
    saveRun(run);
    return;
  }
  const i = run.blocks.indexOf(block);
  const caption = run.blocks.slice(i + 1, i + 3).concat(run.blocks.slice(Math.max(0, i - 2), i))
    .find((b) => b.page === block.page && kindOf(b.type) === "caption");
  const around = [...run.blocks.slice(Math.max(0, i - 3), i), ...run.blocks.slice(i + 1, i + 4)]
    .filter((b) => b.page === block.page || Math.abs(b.page - block.page) <= 1)
    .filter((b) => ["text", "heading", "caption"].includes(kindOf(b.type)));
  const lecture = run.lectures.find((l) => l.blocks.includes(block.id));
  const goals = lecture?.goals.filter((g) => g.blocks.includes(block.id)) ?? [];
  const subject = run.options.subject;
  const call = newCall(run, { step: "triage", label: `Triage ${block.id}`, block: block.id, model: triage.model, effort: "off", prompt: {
    system: [
      part("role", "Role", "rules", "You look at ONE figure from a textbook and decide how a video lecture should best show it. The " +
        "book's own picture is not put in the video as it is unless that is one of the ways offered and nothing else would do."),
      part("choices", `Ways offered (${kinds.length})`, "choices", ["Choose exactly one of these ways:",
        ...kinds.map((k) => `- ${choiceOf(k)!.prompt}`)]),
      part("rules", "How to choose", "rules", [
        "Choose by what the figure teaches and what must survive in the video: its exact values and labels, its look, or only its idea.",
        ...(kinds.includes("exact") && kinds.includes("styled") ? ["When in doubt between EXACT and STYLED, EXACT."] : []),
        "If no way offered fits well, choose the closest and say in the reason what would fit better.",
      ]),
    ],
    user: [
      ...(subject ? [part("subject", "Subject", "context", `The subject is ${subject}.`)] : []),
      part("block", "The figure's block", "book", JSON.stringify({ id: block.id, block_type: block.type, html: block.html })),
      ...(caption ? [part("caption", "Its caption", "book", caption.text)] : []),
      ...(block.description ? [part("shows", "What it shows (the figures step)", "items", block.description)] : []),
      ...(around.length ? [part("around", "The book's text around it", "book", around.map((b) => b.text).join("\n"))] : []),
      ...(lecture ? [part("lecture", "Where it is taught", "goals", [`Lecture ${lecture.n}: ${lecture.title}`,
        ...goals.map((g) => `${g.id}: ${g.goal}`)])] : []),
      part("image", "The figure (picture)", "book", `[the picture is attached: /api/documents/${run.documentId}/figure/${encodeURIComponent(block.id)}]`),
      part("ask", "Request", "ask", "Decide how it is shown (triage_figure)."),
    ],
  } });
  state.calls.push(call.id);
  const reply = await callTool({ call, tool: tool(kinds), images: [image], onChange: () => saveRun(run),
    fake: () => fakeTriage(kinds, `${caption?.text ?? ""} ${block.description ?? ""} ${block.text}`) });
  state.at = Date.now();
  if (!reply) {
    state.status = "failed";
    state.error = `the call failed: ${call.error ?? "no reply"}`;
    saveRun(run);
    return;
  }
  const kind = String(reply.kind ?? "").trim().toLowerCase();
  if (!kinds.includes(kind as TriageKind)) {
    check(call, "Way offered", "fail", `answered "${kind || "(nothing)"}", which is not one of ${kinds.join(", ")}`);
    state.status = "failed";
    state.error = `the model answered "${kind || "(nothing)"}", not one of the ways offered`;
    saveRun(run);
    return;
  }
  check(call, "Way offered", "pass", choiceOf(kind)!.label);
  const how = String(reply.how ?? "").replace(/\s+/g, " ").trim();
  check(call, "Instruction", how ? "pass" : "fail", how ? `${how.split(" ").length} words` : "no instruction for whoever builds it");
  const keep = (Array.isArray(reply.keep) ? reply.keep : []).map((x) => String(x).trim()).filter(Boolean).slice(0, 40);
  if (keep.length) check(call, "Must keep", "info", keep.join(", ").slice(0, 300));
  Object.assign(state, { status: "done", kind: kind as TriageKind, how: how.slice(0, 400),
    reason: String(reply.reason ?? "").replace(/\s+/g, " ").trim().slice(0, 300), keep } satisfies Partial<FigureTriage>);
  saveRun(run);
}

/** The offline stand-in's choice: by the words of the caption and description, among the ways offered. */
function fakeTriage(kinds: TriageKind[], words: string) {
  const w = words.toLowerCase();
  const wants: TriageKind[] = /\bmap\b|river|border|route/.test(w) ? ["map"]
    : /graph|chart|plot|table|circuit|axis|triangle|flow/.test(w) ? ["manim"]
      : /photo|photograph/.test(w) ? ["photo", "exact"]
        : /logo|qr code|icon/.test(w) ? ["skip"]
          : /cell|organ|anatomy|apparatus|specimen/.test(w) ? ["svg", "exact"] : ["styled", "exact"];
  const kind = wants.find((k) => kinds.includes(k)) ?? kinds[0];
  return { kind, how: `Show it as ${choiceOf(kind)!.label.toLowerCase()}, every label as in the book.`,
    reason: `The stand-in chose by the figure's words: ${words.trim().slice(0, 80)}`, keep: [] };
}

export { TRIAGE_CHOICES };
