/**
 * The figure triage: how each of the book's figures is to be shown in the video, one call per figure, from the ways
 * the user allows (triage-kinds.ts). It is a classification, so by default a decision model decides it (Jev on
 * OpenRouter's Decisions API, decisions.ts): one Choice question over the ways offered, with the figure's picture
 * and words as state; it answers with the way, a probability for each way and its confidence, and no words. A
 * choice under the confidence threshold is marked unsure. The chat engine (a model that reads images) answers the
 * same with an instruction for whoever builds the figure and its reason; it can be used for a whole round, or for
 * the unsure figures only.
 *
 *   run       triage every figure not triaged yet (a first run, or the rest after a stop or a failure)
 *   reset     forget every decision (and the user's own choices) and triage them all again
 *   one       triage one figure again
 *   unsure    ask the chat model about the figures the decision model was unsure of
 *
 * It runs apart from the transcript, on any run whose book has been read, and every answer is saved as it comes.
 * Code checks each answer: the way chosen must be one offered. A figure with no picture cannot be triaged.
 */

import { docDir, loadRun, saveRun, type documentBook } from "./store";
import { refreshFigures } from "./datalab";
import { bookOf, markPictures } from "./docs";
import { captionOf, figureFile, kindOf, type Block } from "./source/blocks";
import { callTool } from "./llm";
import { answerTo, callDecision, readChoice, type StateItem } from "./decisions";
import { fitImage, type Fitted } from "./imagefit";
import { modelFor } from "./models";
import { part } from "./prompts/parts";
import { DEFAULT_KINDS, TRIAGE_CHOICES, choiceOf, triageInstructions, type TriageKind } from "./triage-kinds";
import { check, clearStop, imageData, jobs, log, newCall, stopJob, stopRequested } from "./run";
import type { FigureTriage, Run, Triage, TriageEngine } from "./types";

const AT_ONCE = Math.max(1, Number(process.env.V2_TRIAGE_PARALLEL) || 4);

type Settings = { kinds?: string[]; engine?: TriageEngine; model?: string; chatModel?: string; threshold?: number };
export type TriageAction =
  | ({ action: "run" | "reset" | "unsure" } & Settings)
  | ({ action: "one"; block: string } & Settings)
  | { action: "override"; block: string; kind: string | null }
  | { action: "stop" }
  | { action: "rescan" };

export function defaultTriageModel(run: Run): string {
  // A run started before decision models (no triageChatModel) kept a chat model as its triageModel.
  return (run.options.triageChatModel && run.options.triageModel) || modelFor("triage");
}
const DEFAULT_THRESHOLD = Number(process.env.V2_TRIAGE_CONFIDENCE) || 0.6;
/** A decision model's Map choice closer than this to its best redraw (Exact, Styled) becomes that redraw. */
const MAP_MARGIN = Number(process.env.V2_MAP_REDRAW_MARGIN) || 0.2;

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
  if (a.action === "rescan") {
    // The book's pictures searched again (Datalab's cached result, then the PDF itself), the run's blocks marked anew.
    const report = await refreshFigures(docDir(run.documentId));
    const book = await bookOf(run.documentId);
    const changed = markPictures(run.blocks, book);
    log(run, `Figure pictures searched again: ${report?.note ?? "the search failed"}${changed ? `; ${changed} block(s) marked anew` : ""}.`);
    saveRun(run, true);
    return run;
  }
  if (a.action === "override") {
    // A way chosen by hand needs no triage: a figure not triaged (or a run with no triage yet) gets one here.
    if (!run.blocks.some((b) => b.id === a.block && b.image)) throw new Error("no such figure with a picture");
    run.triage ??= { status: "idle", kinds: DEFAULT_KINDS, model: defaultTriageModel(run), rounds: 0, figures: {} };
    const f = (run.triage.figures[a.block] ??= { block: a.block, status: "waiting", calls: [] });
    if (a.kind && !choiceOf(a.kind)) throw new Error(`no such way: ${a.kind}`);
    f.override = (a.kind || undefined) as TriageKind | undefined;
    log(run, a.kind ? `Figure ${a.block}: shown as ${choiceOf(a.kind)!.label} (chosen by hand).` : `Figure ${a.block}: back to the model's choice.`);
    saveRun(run, true);
    return run;
  }
  if (run.legacy) throw new Error(run.legacy);
  if (!run.blocks.length) throw new Error("the book has not been read in this run yet: build the transcript first (its first step reads it)");
  if (jobs.has(`${id}:triage`)) throw new Error("the triage is already running");
  const kinds = (a.kinds ?? run.triage?.kinds ?? DEFAULT_KINDS).filter((k): k is TriageKind => !!choiceOf(k));
  if (!kinds.length) throw new Error("choose at least one way a figure may be shown");
  const triage: Triage = run.triage ?? { status: "idle", kinds, model: "", rounds: 0, figures: {} };
  if (run.triage && !run.triage.engine) {
    // A run triaged before decision models: its model was a chat model.
    triage.chatModel ??= triage.model;
    triage.model = "";
  }
  triage.kinds = kinds;
  // A round of all the figures sets the run's engine; one figure or the unsure ones may be asked of another.
  if (a.action === "run" || a.action === "reset") triage.engine = a.engine ?? triage.engine ?? "decision";
  triage.engine ??= "decision";
  triage.model = a.model || triage.model || defaultTriageModel(run);
  triage.chatModel = a.chatModel || triage.chatModel || run.options.triageChatModel || modelFor("triageChat");
  if (a.threshold !== undefined && Number.isFinite(Number(a.threshold))) triage.threshold = Math.min(1, Math.max(0, Number(a.threshold)));
  triage.threshold ??= DEFAULT_THRESHOLD;
  // The engine of this round: the unsure ones always go to the chat model.
  const engine: TriageEngine = a.action === "unsure" ? "chat" : a.action === "one" ? a.engine ?? triage.engine : triage.engine;
  run.triage = triage;
  // The book's pictures as found now (a book uploaded before the search found them all is searched again, once).
  const book = await bookOf(run.documentId);
  if (markPictures(run.blocks, book)) log(run, "The book's figure pictures were found again: the figure blocks are marked anew.");
  saveRun(run);
  const figures = triageable(run);
  if (!figures.length) {
    const r = book.report;
    throw new Error(`this book has no figure with a picture to triage${r ? `: ${r.note}` : ""}`);
  }
  let todo: Block[];
  if (a.action === "reset") {
    // Decisions and hand choices go; each figure's past calls stay listed with it (their cost was real).
    triage.figures = Object.fromEntries(Object.entries(triage.figures).map(([id, f]) => [id, { block: id, status: "waiting", calls: f.calls }]));
    todo = figures;
    log(run, `Triage reset: every figure's decision cleared; all ${figures.length} triaged again.`);
  } else if (a.action === "unsure") {
    todo = figures.filter((b) => triage.figures[b.id]?.unsure);
    if (!todo.length) throw new Error("no figure is marked unsure");
    log(run, `The ${todo.length} unsure figure(s) asked of the chat model (${triage.chatModel}).`);
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
    triage.figures[b.id] = { block: b.id, status: "waiting", calls: old?.calls ?? [],
      override: a.action === "one" || a.action === "unsure" ? old?.override : undefined };
  }
  triage.rounds += 1;
  launch(run, todo, engine);
  return run;
}

function launch(run: Run, todo: Block[], engine: TriageEngine) {
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
      const book = await bookOf(run.documentId);
      const queue = [...todo];
      const worker = async () => {
        while (queue.length && !stopRequested(key)) await triageFigure(run, queue.shift()!, book, engine);
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

async function triageFigure(run: Run, block: Block, book: Awaited<ReturnType<typeof documentBook>>, engine: TriageEngine) {
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
  const captionText = captionOf(run.blocks, block);
  const caption = captionText ? { text: captionText } : undefined;
  const around = [...run.blocks.slice(Math.max(0, i - 3), i), ...run.blocks.slice(i + 1, i + 4)]
    .filter((b) => b.page === block.page || Math.abs(b.page - block.page) <= 1)
    .filter((b) => ["text", "heading", "caption"].includes(kindOf(b.type)));
  const lecture = run.lectures.find((l) => l.blocks.includes(block.id));
  const goals = lecture?.goals.filter((g) => g.blocks.includes(block.id)) ?? [];
  const subject = run.options.subject;
  state.engine = engine;
  state.rule = undefined;
  if (engine === "decision") {
    const outcome = await decide(run, block, state, image, { caption: caption?.text, around: around.map((b) => b.text), lecture, goals, subject });
    if (outcome !== "picture-refused") return;
    state.engine = "chat";
    state.rule = "the decision model refused its picture: decided by the chat model";
  }
  const call = newCall(run, { step: "triage", label: `Triage ${block.id} (chat)`, block: block.id, model: triage.chatModel!, effort: "off", prompt: {
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
  Object.assign(state, { status: "done", kind: kind as TriageKind, how: how.slice(0, 400), unsure: false, probabilities: undefined, confidence: undefined,
    rule: state.rule?.startsWith("the decision model refused") ? state.rule : undefined,
    reason: String(reply.reason ?? "").replace(/\s+/g, " ").trim().slice(0, 300), keep } satisfies Partial<FigureTriage>);
  saveRun(run);
}

/**
 * The decision model's triage: one Choice question over the ways offered (each with what it means), the figure's
 * picture and words as state. Its answer is the way, a probability for each, and a confidence; no words, so the
 * figure keeps no instruction (the step that builds it reads the figure itself). Under the threshold it is unsure.
 */
async function decide(run: Run, block: Block, state: FigureTriage, image: string,
  c: { caption?: string; around: string[]; lecture?: Run["lectures"][number]; goals: { id: string; goal: string }[]; subject?: string }) {
  const triage = run.triage!;
  const kinds = triage.kinds;
  // v1's triage instructions (triage-kinds.ts); each way also goes as its criterion.
  const instructions = triageInstructions(kinds);
  const criteria = Object.fromEntries(kinds.map((k) => [k, choiceOf(k)!.prompt]));
  const words: string[] = [
    ...(c.subject ? [`Subject: ${c.subject}.`] : []),
    `The figure's block in the book: ${JSON.stringify({ id: block.id, block_type: block.type, html: block.html })}`,
    ...(c.caption ? [`Its caption: ${c.caption}`] : []),
    ...(block.description ? [`What it shows: ${block.description}`] : []),
    ...(c.around.length ? [`The book's text around it: ${c.around.join(" ")}`] : []),
    ...(c.lecture ? [`It is taught in lecture ${c.lecture.n}, "${c.lecture.title}"${c.goals.length ? `, for: ${c.goals.map((g) => g.goal).join("; ")}` : ""}.`] : []),
    "The figure:",
  ];
  // Made to fit what a decision model takes (it refuses some sizes outright: "Invalid image dimensions").
  let fitted: Fitted | undefined;
  try {
    fitted = await fitImage(image);
  } catch {}
  const stateItems: StateItem[] = [...words, { type: "image_url", image_url: { url: fitted?.url ?? image } }];
  const call = newCall(run, { step: "triage", label: `Triage ${block.id}`, block: block.id, model: triage.model, effort: "off", prompt: {
    system: [
      part("question", "Instructions (v1's triage, as the question's instructions)", "rules", instructions),
      part("choices", `Criteria: the ways offered (${kinds.length})`, "choices", kinds.map((k) => `${k}: ${choiceOf(k)!.prompt}`)),
    ],
    user: [
      part("state", "State: the figure's words", "book", words.slice(0, -1)),
      part("image", "State: the figure (picture)", "book", `[the picture is in the state: /api/documents/${run.documentId}/figure/${encodeURIComponent(block.id)}]`),
    ],
  } });
  state.calls.push(call.id);
  if (fitted) check(call, "Picture size", fitted.changed.length ? "fixed" : "pass", `${fitted.from.width}×${fitted.from.height}` +
    (fitted.changed.length ? `: ${fitted.changed.join(", ")}` : ", sent as it is"));
  const reply = await callDecision({ call, state: stateItems, questions: { way: { type: "choice", instructions, criteria } },
    onChange: () => saveRun(run), fake: () => {
      // The stand-in refuses the picture as Jev did ("Invalid image dimensions") when its name says so, to try the
      // fallback offline.
      if (triage.model.includes("refuses-images")) throw new Error('400 {"error":{"message":"HTTP 400: {\\"detail\\":{\\"message\\":\\"Invalid image dimensions.\\"}}"}}');
      return fakeDecision(kinds, `${c.caption ?? ""} ${block.description ?? ""} ${block.text}`);
    } });
  state.at = Date.now();
  if (!reply) {
    // A picture the decision model will not take at all: the chat model decides this one instead.
    if (/image|dimension/i.test(call.error ?? "") && /\b400\b/.test(call.error ?? "")) {
      check(call, "Picture refused", "fixed", "the decision model refused the picture: the chat model decides this figure");
      return "picture-refused" as const;
    }
    state.status = "failed";
    state.error = `the call failed: ${call.error ?? "no reply"}`;
    saveRun(run);
    return;
  }
  const answer = readChoice(answerTo(reply, "way"), kinds);
  if (!answer.choice) {
    check(call, "Way offered", "fail", `no way offered found in the answer: ${JSON.stringify(reply).slice(0, 200)}`);
    state.status = "failed";
    state.error = "the answer named no way offered (see the call's output)";
    saveRun(run);
    return;
  }
  const threshold = triage.threshold ?? DEFAULT_THRESHOLD;
  const rule = mapOrRedraw(answer, kinds);
  const unsure = answer.confidence !== undefined && answer.confidence < threshold;
  const ranked = Object.entries(answer.probabilities).sort((x, y) => y[1] - x[1]).map(([k, p]) => `${k} ${(p * 100).toFixed(0)}%`).join(", ");
  check(call, "Way offered", "pass", `${choiceOf(answer.choice)!.label}${ranked ? ` (${ranked})` : ""}`);
  if (rule) check(call, "Map or redraw", "fixed", rule);
  check(call, "Confidence", unsure ? "fail" : answer.confidence === undefined ? "info" : "pass", answer.confidence === undefined
    ? "the answer gave no confidence" : `${(answer.confidence * 100).toFixed(0)}% (threshold ${(threshold * 100).toFixed(0)}%)${unsure ? ": unsure" : ""}`);
  Object.assign(state, { status: "done", kind: answer.choice as TriageKind, probabilities: answer.probabilities, confidence: answer.confidence,
    unsure, rule, how: undefined, reason: undefined, keep: undefined } satisfies Partial<FigureTriage>);
  saveRun(run);
}

/**
 * A Map choice only a little surer than a redraw (Exact or Styled, whichever is surer; under MAP_MARGIN apart) is
 * redrawn instead: a redraw keeps the book's picture, a map built wrong does not. Changes the answer; says why.
 */
export function mapOrRedraw(answer: { choice?: string; probabilities: Record<string, number>; confidence?: number },
  kinds: TriageKind[], margin = MAP_MARGIN): string | undefined {
  const p = answer.probabilities;
  if (answer.choice !== "map" || p.map === undefined) return undefined;
  const redraw = (["exact", "styled"] as const).filter((k) => kinds.includes(k) && p[k] !== undefined).sort((x, y) => p[y] - p[x])[0];
  if (!redraw || p.map - p[redraw] >= margin) return undefined;
  const rule = `Map ${(p.map * 100).toFixed(0)}% and ${choiceOf(redraw)!.label} ${(p[redraw] * 100).toFixed(0)}% are under ` +
    `${Math.round(margin * 100)} points apart: redrawn instead`;
  answer.choice = redraw;
  answer.confidence = p[redraw];
  return rule;
}

/** The offline stand-in of a decision model: a choice by the figure's words, with probabilities. */
function fakeDecision(kinds: TriageKind[], words: string) {
  const { kind } = fakeTriage(kinds, words);
  const sure = /map|graph|chart/i.test(words) ? 0.86 : 0.48;
  const rest = (1 - sure) / Math.max(1, kinds.length - 1);
  return { way: { type: "choice", choice: kind, probabilities: Object.fromEntries(kinds.map((k) => [k, k === kind ? sure : rest])), confidence: sure },
    usage: { prompt_tokens: 0, cost: 0 } };
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
