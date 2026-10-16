/**
 * The script step: each lecture's transcript cut into chapters and beats by one call (prompts/script.ts), every
 * sentence assigned to one beat, the lecture's figures placed. Code reads the answer against the transcript and
 * mends what it can, saying so:
 *
 *   - a sentence number not in the transcript is dropped; one used twice stays in its first beat;
 *   - a sentence left out goes into the beat before it (or the first beat);
 *   - beats and chapters are put in sentence order;
 *   - a figure not of the lecture is dropped, one shown twice stays on its first beat, a Map figure makes its
 *     chapter a map chapter; a lecture figure not shown is noted.
 *
 * When the sentences still do not run 1 to the last once each, the lecture is asked again with what broke. Lectures
 * are scripted in parallel (each on its own, as figures are generated), or one at a time: one lecture picked, the next
 * one not scripted yet, or a whole build in turn. Everything is saved in the run.
 */

import { linesOf } from "./source/book";
import { callTool } from "./llm";
import { modelFor } from "./models";
import { SCRIPT_TOOL, scriptPrompt, type FigureForScript } from "./prompts/script";
import { lectureFigures } from "./script-figures";
import { clearStop, jobs, log, newCall, stopJob, stopRequested } from "./run";
import { loadRun, saveRun } from "./store";
import type { Beat, Chapter, Check, LectureScript, Run, ScriptState } from "./types";

export { lectureFigures };

const AT_ONCE = Math.max(1, Number(process.env.V2_SCRIPT_PARALLEL) || 3);

/** run/reset: every lecture (not scripted yet / all again), in parallel or, with oneAtATime, in turn. one: that lecture.
 * next: the first lecture not scripted yet. */
export type ScriptAction = { action: "run" | "reset"; model?: string; oneAtATime?: boolean } | { action: "one"; lecture: number; model?: string }
  | { action: "next"; model?: string } | { action: "stop" };

const shared = globalThis as unknown as { __v2scriptBusy?: Set<string>; __v2scriptActive?: Map<string, number> };
const busy = (shared.__v2scriptBusy ??= new Set<string>());
const active = (shared.__v2scriptActive ??= new Map<string, number>());
const busyKey = (run: string, n: number) => `${run}|${n}`;

export async function scriptAction(id: string, a: ScriptAction): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (a.action === "stop") {
    stopJob(id, "script");
    return run;
  }
  if (run.legacy) throw new Error(run.legacy);
  const written = run.lectures.filter((l) => l.status === "written" && l.text);
  if (!written.length) throw new Error("no lecture is written yet: build the transcript first");
  const st: ScriptState = run.script ?? { status: "idle", model: "", rounds: 0, lectures: {} };
  st.model = a.model || st.model || run.options.scriptModel || modelFor("script");
  run.script = st;
  const free = (n: number) => !busy.has(busyKey(id, n));
  let todo: number[];
  if (a.action === "one") {
    if (!written.some((l) => l.n === a.lecture)) throw new Error(`lecture ${a.lecture} is not written`);
    if (!free(a.lecture)) throw new Error(`lecture ${a.lecture} is being scripted already`);
    todo = [a.lecture];
  } else if (a.action === "next") {
    const next = written.find((l) => free(l.n) && st.lectures[l.n]?.status !== "done");
    if (!next) throw new Error("every written lecture is scripted or being scripted: rescript one, or rebuild all");
    todo = [next.n];
  } else if (a.action === "reset") {
    todo = written.map((l) => l.n).filter(free);
    log(run, `Scripts reset: ${todo.length} lecture(s) scripted again.`);
  } else {
    todo = written.map((l) => l.n).filter((n) => free(n) && st.lectures[n]?.status !== "done");
    if (!todo.length) throw new Error("every written lecture is scripted or being scripted: reset to script them all again, or rescript one");
  }
  if (!todo.length) throw new Error("every lecture is being scripted already");
  for (const n of todo) {
    busy.add(busyKey(id, n));
    st.lectures[n] = { lecture: n, status: "waiting", chapters: st.lectures[n]?.chapters ?? [], calls: st.lectures[n]?.calls ?? [] };
  }
  st.rounds += 1;
  launch(run, todo, (a.action === "run" || a.action === "reset") && a.oneAtATime ? 1 : AT_ONCE);
  return run;
}

function launch(run: Run, todo: number[], atOnce: number) {
  const key = `${run.id}:script`;
  const st = run.script!;
  const first = !active.get(run.id);
  active.set(run.id, (active.get(run.id) ?? 0) + 1);
  jobs.add(key);
  if (first) {
    clearStop(key);
    Object.assign(st, { status: "running", error: undefined, started: Date.now(), ended: undefined });
  }
  saveRun(run, true);
  void (async () => {
    const queue = [...todo];
    const worker = async () => {
      for (let n = queue.shift(); n !== undefined; n = queue.shift()) {
        try {
          if (!stopRequested(key)) await scriptLecture(run, n);
        } catch (error) {
          Object.assign(st.lectures[n], { status: "failed", error: (error as Error).message });
        } finally {
          busy.delete(busyKey(run.id, n));
          if (st.lectures[n]?.status === "running") st.lectures[n].status = "waiting";
          saveRun(run);
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(atOnce, queue.length) }, worker));
    const left = (active.get(run.id) ?? 1) - 1;
    if (left > 0) active.set(run.id, left);
    else {
      active.delete(run.id);
      const all = Object.values(st.lectures);
      const failed = all.filter((l) => l.status === "failed").length;
      if (stopRequested(key)) {
        st.status = "stopped";
        log(run, "Scripts stopped: what was scripted is kept.");
      } else {
        st.status = failed && failed === all.length ? "failed" : "done";
        st.error = failed ? `${failed} lecture(s) could not be scripted: see each one's error, and rescript them.` : undefined;
      }
      jobs.delete(key);
      clearStop(key);
      st.ended = Date.now();
    }
    saveRun(run, true);
  })();
}

/** Whether lectures of a run are being scripted now. */
export function scripting(runId: string): number[] {
  return [...busy].filter((k) => k.startsWith(`${runId}|`)).map((k) => Number(k.slice(runId.length + 1)));
}

async function scriptLecture(run: Run, n: number) {
  const st = run.script!;
  const state = st.lectures[n];
  const lecture = run.lectures.find((l) => l.n === n)!;
  const lines = linesOf(lecture.text ?? "");
  const figures = lectureFigures(run, n);
  const goals = lecture.goals.map((g) => ({ id: g.id, goal: g.goal, lines: lecture.goalLines?.[g.id] ?? [] }));
  Object.assign(state, { status: "running", error: undefined, lines: lines.length });
  saveRun(run);
  let retry: string[] | undefined;
  for (let attempt = 1; attempt <= 2; attempt++) {
    const call = newCall(run, { step: "script", label: `Script lecture ${n}${attempt > 1 ? " (again, with what broke)" : ""}`, lecture: n,
      model: st.model, prompt: scriptPrompt({ lecture, lines, goals, figures, retry }) });
    state.calls.push(call.id);
    const reply = await callTool({ call, tool: SCRIPT_TOOL, onChange: () => saveRun(run), fake: () => fakeScript(lines.length, figures) });
    if (!reply) {
      Object.assign(state, { status: "failed", error: `the call failed: ${call.error ?? "no reply"}`, at: Date.now() });
      saveRun(run);
      return;
    }
    const read = readScript(reply, lines.length, figures);
    call.checks.push(...read.checks);
    if (read.problems.length && attempt === 1) {
      retry = read.problems;
      continue;
    }
    Object.assign(state, { status: read.chapters.length ? "done" : "failed", chapters: read.chapters, checks: read.checks, at: Date.now(),
      error: read.problems.length ? `still broken after a second try: ${read.problems.join("; ")}` : read.chapters.length ? undefined : "no chapters" });
    saveRun(run);
    return;
  }
}

/** The answer made whole against the transcript (see the top of this file), what code did, and what it could not mend. */
export function readScript(raw: unknown, total: number, figures: FigureForScript[]): { chapters: Chapter[]; checks: Check[]; problems: string[] } {
  const checks: Check[] = [];
  const r = (raw ?? {}) as { chapters?: unknown };
  const rawChapters = (Array.isArray(r.chapters) ? r.chapters : []) as { title?: unknown; narration?: unknown; map?: unknown; beats?: unknown }[];
  const seen = new Set<number>();
  let outside = 0, twice = 0;
  const known = new Map(figures.map((f) => [f.id, f]));
  const shown = new Set<string>();
  let unknownFig = 0, figTwice = 0;
  let chapters: Chapter[] = rawChapters.map((c, ci) => {
    const beats: Beat[] = (Array.isArray(c.beats) ? c.beats : []).map((b: { lines?: unknown; show?: unknown; figure?: unknown }) => {
      const own: number[] = [];
      for (const v of Array.isArray(b?.lines) ? b.lines : []) {
        const k = Math.round(Number(v));
        if (!(k >= 1 && k <= total)) { outside++; continue; }
        if (seen.has(k)) { twice++; continue; }
        seen.add(k);
        own.push(k);
      }
      let figure = typeof b?.figure === "string" && b.figure.trim() ? b.figure.trim() : undefined;
      if (figure && !known.has(figure)) { unknownFig++; figure = undefined; }
      if (figure && shown.has(figure)) { figTwice++; figure = undefined; }
      if (figure) shown.add(figure);
      return { n: 0, lines: own.sort((x, y) => x - y), show: String(b?.show ?? "").trim().slice(0, 200), ...(figure ? { figure } : {}) };
    }).filter((b) => b.lines.length);
    return { n: ci + 1, title: String(c.title ?? "").trim().slice(0, 100) || `Chapter ${ci + 1}`,
      narration: String(c.narration ?? "").trim().slice(0, 200), map: c.map === true, beats };
  }).filter((c) => c.beats.length);
  checks.push({ name: "Chapters", result: chapters.length ? "pass" : "fail", detail: `${chapters.length} chapter(s), ${chapters.reduce((k, c) => k + c.beats.length, 0)} beats` });
  if (outside) checks.push({ name: "Sentence numbers", result: "fixed", detail: `${outside} number(s) not in the transcript dropped` });
  if (twice) checks.push({ name: "Each sentence once", result: "fixed", detail: `${twice} sentence(s) used twice kept in their first beat` });

  // In sentence order: chapters by their first sentence, beats inside each by theirs.
  const first = (c: Chapter) => c.beats[0].lines[0];
  let reordered = false;
  for (const c of chapters) {
    const before = c.beats.map((b) => b.lines[0]).join();
    c.beats.sort((x, y) => x.lines[0] - y.lines[0]);
    if (c.beats.map((b) => b.lines[0]).join() !== before) reordered = true;
  }
  const order = chapters.map(first).join();
  chapters.sort((x, y) => first(x) - first(y));
  if (chapters.map(first).join() !== order) reordered = true;
  if (reordered) checks.push({ name: "Order", result: "fixed", detail: "beats or chapters put in sentence order" });

  // Sentences left out: into the beat holding the sentence before (or the first beat).
  const missing = Array.from({ length: total }, (_, i) => i + 1).filter((k) => !seen.has(k));
  if (missing.length && chapters.length) {
    const beats = chapters.flatMap((c) => c.beats);
    for (const k of missing) {
      const home = [...beats].reverse().find((b) => b.lines[0] < k) ?? beats[0];
      home.lines.push(k);
      home.lines.sort((x, y) => x - y);
    }
    checks.push({ name: "Every sentence", result: "fixed", detail: `${missing.length} sentence(s) left out put in the beat before them: ${missing.slice(0, 15).join(", ")}` });
  } else if (chapters.length) {
    checks.push({ name: "Every sentence", result: "pass", detail: `all ${total} sentences in a beat` });
  }

  // What could not be mended: the sentences must run 1..total once each, in order, beat after beat.
  const problems: string[] = [];
  if (!chapters.length) problems.push("no chapter with a beat with sentences");
  const flat = chapters.flatMap((c) => c.beats.flatMap((b) => b.lines));
  const interleaved = flat.some((k, i) => i && k < flat[i - 1]);
  if (chapters.length && interleaved) problems.push("the beats' sentences interleave (a beat takes sentences from between another beat's): each beat takes a run of consecutive sentences");

  // Figures: each once; a Map figure makes its chapter a map chapter; the lecture's figures not shown, noted.
  if (unknownFig) checks.push({ name: "Figures", result: "fixed", detail: `${unknownFig} figure id(s) not of this lecture dropped` });
  if (figTwice) checks.push({ name: "Figures", result: "fixed", detail: `${figTwice} figure(s) shown twice kept on their first beat` });
  for (const c of chapters) {
    if (!c.map && c.beats.some((b) => b.figure && known.get(b.figure)?.way === "Map")) {
      c.map = true;
      checks.push({ name: "Map chapter", result: "fixed", detail: `chapter "${c.title}" shows a Map figure: made a map chapter` });
    }
  }
  const notShown = figures.filter((f) => !shown.has(f.id));
  checks.push({ name: "Figures shown", result: notShown.length ? "info" : "pass", detail: notShown.length
    ? `${notShown.length} of the lecture's ${figures.length} figure(s) not shown: ${notShown.map((f) => f.id).join(", ")}` : `all ${figures.length} shown` });
  const long = chapters.flatMap((c) => c.beats).filter((b) => b.lines.length > 3).length;
  if (long) checks.push({ name: "Beat length", result: "info", detail: `${long} beat(s) of more than 3 sentences` });

  // Numbered: chapters 1.., beats 1.. through the lecture.
  let bn = 0;
  chapters = chapters.map((c, i) => ({ ...c, n: i + 1, narration: c.narration || `Chapter ${i + 1}. ${c.title}.`, beats: c.beats.map((b) => ({ ...b, n: ++bn })) }));
  return { chapters, checks, problems };
}

/** The offline stand-in: two sentences a beat, a chapter every six beats, each figure on the beat of its first sentence. */
function fakeScript(total: number, figures: FigureForScript[]) {
  const beats: { lines: number[]; show: string; figure?: string }[] = [];
  for (let k = 1; k <= total; k += 2) beats.push({ lines: k + 1 <= total ? [k, k + 1] : [k], show: "the key point on the board" });
  for (const f of figures) {
    const at = beats.find((b) => b.lines.includes(f.lines[0] ?? -1) && !b.figure) ?? beats.find((b) => !b.figure);
    if (at) {
      at.figure = f.id;
      at.show = `the figure: ${f.caption.slice(0, 60)}`;
    }
  }
  const chapters = [];
  for (let i = 0; i < beats.length; i += 6) {
    const own = beats.slice(i, i + 6);
    chapters.push({ title: `Part ${chapters.length + 1}`, narration: `Chapter ${chapters.length + 1}.`,
      map: own.some((b) => b.figure && figures.find((f) => f.id === b.figure)?.way === "Map"), beats: own });
  }
  return { chapters };
}
