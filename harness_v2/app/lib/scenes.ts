/**
 * The scenes step: each beat of a lecture's script given its visuals, as the engine's operations
 * (harness_v2/engine/compile_lecture.py), then compiled by the engine, mended, and rendered a beat or a chapter at a
 * time to be looked at.
 *
 *   - BUILD: one call per chapter (prompts/scenes.ts), in order, so a lecture's region and diagrams carry on; a whole
 *     lecture, one chapter, or one beat (the beats around it given as they are). The narration is the script's: the
 *     model writes only each beat's "do". Code takes out what is switched off (visual-kinds.ts) and says so.
 *   - COMPILE: the lecture as the engine's beat script (the run's look, its figures as files), checked and compiled
 *     by the engine; its errors and notes are put on the beats they name. The image model makes the pictures asked
 *     for while it compiles (the engine's genimage.py; a stand-in picture when there is no key).
 *   - FIX: the beats the compiler refused are asked again with what it said, once by itself after a build, and
 *     whenever the page asks.
 *   - RENDER: one beat in its chapter (the chapter rendered up to it, silent, and the beat cut out: its clip and its
 *     last frame), or a chapter (its video, and each beat's frame and clip), in the run's look or another.
 *
 * Everything is saved in the run; renders under .data/runs/<run>/scenes/.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";
import { bookOf } from "./docs";
import { callTool, usingFixture } from "./llm";
import { engineDir } from "./maps";
import { errorOf, runPython } from "./manim";
import { modelFor } from "./models";
import { part } from "./prompts/parts";
import { SCENES_TOOL, scenesPrompt, type SceneBeatInput, type ScenesAsk } from "./prompts/scenes";
import { check, clearStop, jobs, log, newCall, stopJob, stopRequested } from "./run";
import { runManimAgent } from "./manim-agent";
import { beatFigures, lectureFigures } from "./script-figures";
import { captionOf, figureFile } from "./source/blocks";
import { linesOf } from "./source/book";
import { DATA, loadRun, saveRun } from "./store";
import { DEFAULT_LOOK, cleanLook, lookWords, type Look } from "./styles";
import type { BeatPicture, ImageReport, MissingPicture, Run, SceneBeat, SceneChapterRender, SceneLecture, SceneRender, ScenesState } from "./types";
import { ALL_KINDS, VISUAL_KINDS, filterOps } from "./visual-kinds";

const AT_ONCE = Math.max(1, Number(process.env.V2_SCENES_PARALLEL) || 3);
const RENDERS_AT_ONCE = Math.max(1, Number(process.env.V2_RENDER_PARALLEL) || 2);
const COMPILE_TIMEOUT = Math.max(60, Number(process.env.V2_COMPILE_TIMEOUT_SECONDS) || 900) * 1000;
const RENDER_TIMEOUT = Math.max(60, Number(process.env.V2_RENDER_TIMEOUT_SECONDS) || 900) * 1000;

type Scope = "rest" | "all" | "next" | "lecture" | "chapter" | "beat";
export type ScenesAction =
  | { action: "look"; style?: string; art?: string }
  | { action: "kinds"; kinds: string[] }
  | { action: "beatKinds"; lecture: number; beat: number; kinds: string[] | null }
  | { action: "chapterKinds"; lecture: number; chapter: number; kinds: string[] | null }
  | { action: "edit"; lecture: number; beat: number; ops: unknown }
  | { action: "editChapter"; lecture: number; chapter: number; beats: { beat: number; ops: unknown; paragraph?: boolean; pause?: number; about?: string }[];
      emblem?: string | null; region?: Record<string, unknown> | null }
  | { action: "build"; scope: Scope; lecture?: number; chapter?: number; beat?: number; model?: string; oneAtATime?: boolean; note?: string }
  | { action: "fix"; lecture: number; model?: string }
  | { action: "compile"; lecture: number }
  | { action: "render"; lecture: number; chapter: number; beat?: number; style?: string; art?: string }
  | { action: "agent"; lecture: number; beat: number; instruction?: string; model?: string }
  | { action: "agentSettings"; on?: boolean; model?: string }
  | { action: "reuseSettings"; on?: boolean; model?: string }
  | { action: "reset"; lecture: number; chapter?: number }
  | { action: "stop" };

const shared = globalThis as unknown as { __v2scenesBusy?: Set<string>; __v2scenesActive?: Map<string, number>; __v2renderBusy?: Set<string>;
  __v2renderQueue?: (() => void)[]; __v2renderOn?: { n: number } };
const busy = (shared.__v2scenesBusy ??= new Set<string>());
const active = (shared.__v2scenesActive ??= new Map<string, number>());
const renderBusy = (shared.__v2renderBusy ??= new Set<string>());
const renderQueue = (shared.__v2renderQueue ??= []);
const renderOn = (shared.__v2renderOn ??= { n: 0 });
const busyKey = (run: string, n: number) => `${run}|${n}`;

export function scenesDir(runId: string): string {
  return path.join(DATA, "runs", runId, "scenes");
}

/** A file under the run's scenes folder as a URL the page can load. */
export function fileUrl(runId: string, file: string): string {
  return `/api/runs/${runId}/scenes/file?p=${encodeURIComponent(path.relative(scenesDir(runId), file))}&v=${Date.now()}`;
}

export function stateOf(run: Run): ScenesState {
  run.scenes ??= { status: "idle", model: "", look: { ...DEFAULT_LOOK }, kinds: [...ALL_KINDS], rounds: 0, lectures: {} };
  return run.scenes;
}

export function lectureState(run: Run, n: number): SceneLecture {
  const st = stateOf(run);
  st.lectures[n] ??= { lecture: n, status: "waiting", beats: {}, calls: [] };
  return st.lectures[n];
}

/** The lecture's script, when it is scripted. */
export function scriptOf(run: Run, n: number) {
  const ls = run.script?.lectures[n];
  return ls?.status === "done" && ls.chapters.length ? ls : undefined;
}

export function beatState(sl: SceneLecture, n: number): SceneBeat {
  sl.beats[n] ??= { n, status: "waiting", ops: [], calls: [] };
  return sl.beats[n];
}

/** The chapter a beat is in (its number), from the script. */
function chapterOf(run: Run, sl: SceneLecture, beat: number): number | undefined {
  return scriptOf(run, sl.lecture)?.chapters.find((c) => c.beats.some((b) => b.n === beat))?.n;
}

/** The kinds a beat may use: its own, else its chapter's, else the run's. */
export const kindsFor = (run: Run, sl: SceneLecture, beat: number) => {
  const c = chapterOf(run, sl, beat);
  return sl.beats[beat]?.kinds ?? (c !== undefined ? sl.chapterKinds?.[c] : undefined) ?? stateOf(run).kinds;
};

export async function scenesAction(id: string, a: ScenesAction): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (a.action === "stop") {
    stopJob(id, "scenes");
    return run;
  }
  if (run.legacy) throw new Error(run.legacy);
  const st = stateOf(run);
  if (a.action === "look") {
    st.look = cleanLook({ ...st.look, ...(a.style ? { style: a.style } : {}), ...(a.art ? { art: a.art } : {}) });
    saveRun(run, true);
    return run;
  }
  if (a.action === "reuseSettings") {
    if (a.on !== undefined) st.reuseJudge = a.on;
    if (a.model !== undefined) st.reuseModel = a.model.trim() || undefined;
    saveRun(run, true);
    return run;
  }
  if (a.action === "agentSettings") {
    if (a.on !== undefined) st.manimAgent = a.on;
    if (a.model !== undefined) st.manimModel = a.model.trim() || undefined;
    saveRun(run, true);
    return run;
  }
  if (a.action === "kinds") {
    st.kinds = ALL_KINDS.filter((k) => a.kinds.includes(k));
    saveRun(run, true);
    return run;
  }
  const lectureOf = (n?: number) => {
    if (!n || !scriptOf(run, n)) throw new Error(`lecture ${n ?? "?"} is not scripted yet: script it first`);
    return lectureState(run, n);
  };
  if (a.action === "beatKinds") {
    const sl = lectureOf(a.lecture);
    const b = beatState(sl, a.beat);
    if (a.kinds === null) delete b.kinds;
    else b.kinds = ALL_KINDS.filter((k) => a.kinds!.includes(k));
    saveRun(run, true);
    return run;
  }
  if (a.action === "chapterKinds") {
    const sl = lectureOf(a.lecture);
    if (!scriptOf(run, a.lecture)!.chapters.some((c) => c.n === a.chapter)) throw new Error(`lecture ${a.lecture} has no chapter ${a.chapter}`);
    sl.chapterKinds ??= {};
    if (a.kinds === null) delete sl.chapterKinds[a.chapter];
    else sl.chapterKinds[a.chapter] = ALL_KINDS.filter((k) => a.kinds!.includes(k));
    saveRun(run, true);
    return run;
  }
  if (a.action === "edit") {
    const sl = lectureOf(a.lecture);
    if (busy.has(busyKey(id, a.lecture))) throw new Error(`lecture ${a.lecture} is being built: wait, or stop it`);
    if (!Array.isArray(a.ops)) throw new Error("the operations must be a JSON list of objects");
    const b = beatState(sl, a.beat);
    const kept = filterOps(a.ops as Record<string, unknown>[], kindsFor(run, sl, a.beat));
    Object.assign(b, { ops: kept.ops, dropped: kept.dropped, edited: true, status: "done", errors: undefined, notes: undefined });
    lock(run, [a.lecture], async () => {
      await compileLecture(run, a.lecture);
    });
    return run;
  }
  if (a.action === "editChapter") {
    // A chapter's beats set by hand at once (the Voice tab's edited beat script): each beat's operations (only the
    // kinds switched on for it), paragraph, pause and about; the lecture's emblem and region when given. Compiled.
    const sl = lectureOf(a.lecture);
    if (busy.has(busyKey(id, a.lecture))) throw new Error(`lecture ${a.lecture} is being built: wait, or stop it`);
    const chapter = scriptOf(run, a.lecture)!.chapters.find((c) => c.n === a.chapter);
    if (!chapter) throw new Error(`lecture ${a.lecture} has no chapter ${a.chapter}`);
    for (const e of a.beats) {
      if (!chapter.beats.some((b) => b.n === e.beat)) throw new Error(`beat ${e.beat} is not in chapter ${a.chapter}`);
      if (!Array.isArray(e.ops)) throw new Error(`beat ${e.beat}: its do must be a JSON list of operations`);
      const b = beatState(sl, e.beat);
      const kept = filterOps(e.ops as Record<string, unknown>[], kindsFor(run, sl, e.beat));
      Object.assign(b, { ops: kept.ops, dropped: kept.dropped, edited: true, status: "done", errors: undefined, notes: undefined,
        paragraph: e.paragraph || undefined, pause: e.pause || undefined, about: e.about || undefined });
    }
    if (a.emblem !== undefined) sl.emblem = a.emblem || undefined;
    if (a.region !== undefined) sl.region = a.region;
    lock(run, [a.lecture], async () => {
      await compileLecture(run, a.lecture);
    });
    return run;
  }
  if (a.action === "agent") {
    const sl = lectureOf(a.lecture);
    if (!scriptOf(run, a.lecture)!.chapters.some((c) => c.beats.some((b) => b.n === a.beat))) throw new Error(`lecture ${a.lecture} has no beat ${a.beat}`);
    if (busy.has(busyKey(id, a.lecture))) throw new Error(`lecture ${a.lecture} is being built: wait, or stop it`);
    if (!kindsFor(run, sl, a.beat).includes("manim")) throw new Error("Manim is switched off for this beat: switch it on (for the run or the beat) first");
    sl.doing = `the Manim agent on beat ${a.beat}`;
    lock(run, [a.lecture], async () => {
      await runManimAgent(run, a.lecture, a.beat, { instruction: a.instruction, model: a.model, stop: () => stopRequested(`${id}:scenes`) });
      await compileLecture(run, a.lecture);
    });
    return run;
  }
  if (a.action === "reset") {
    const sl = lectureOf(a.lecture);
    if (busy.has(busyKey(id, a.lecture))) throw new Error(`lecture ${a.lecture} is being built: stop it first`);
    const script = scriptOf(run, a.lecture)!;
    const chapter = a.chapter === undefined ? undefined : script.chapters.find((c) => c.n === a.chapter);
    if (a.chapter !== undefined && !chapter) throw new Error(`lecture ${a.lecture} has no chapter ${a.chapter}`);
    const keys = `${id}|${a.lecture}|`;
    if ([...renderBusy].some((k) => k.startsWith(keys) && (!chapter || k.startsWith(`${keys}${chapter.n}|`)))) throw new Error("a render of it is going: wait for it to end");
    const dir = path.join(scenesDir(id), `L${a.lecture}`);
    if (!chapter) {
      // The whole lecture back to not built: its beats (their kinds of their own are kept), region, compile, renders,
      // the Manim agent's work and pictures, and their files.
      const kinds = Object.fromEntries(Object.values(sl.beats).filter((b) => b.kinds).map((b) => [b.n, b.kinds!]));
      st.lectures[a.lecture] = { lecture: a.lecture, status: "waiting", beats: Object.fromEntries(Object.entries(kinds)
        .map(([n, k]) => [n, { n: Number(n), status: "waiting", ops: [], kinds: k, calls: [] } as SceneBeat])), calls: [],
        ...(sl.chapterKinds ? { chapterKinds: sl.chapterKinds } : {}) };
      if (st.agentImages) delete st.agentImages[a.lecture];
      await rm(dir, { recursive: true, force: true });
      log(run, `Scenes of lecture ${a.lecture} reset.`);
    } else {
      // One chapter: its beats' visuals, agent work and renders; the lecture's compile is then out of date.
      for (const b of chapter.beats) {
        const kinds = sl.beats[b.n]?.kinds;
        if (kinds) sl.beats[b.n] = { n: b.n, status: "waiting", ops: [], kinds, calls: [] };
        else delete sl.beats[b.n];
        await rm(path.join(dir, `beat-${b.n}`), { recursive: true, force: true });
        await rm(path.join(dir, "agent", `beat-${b.n}`), { recursive: true, force: true });
      }
      if (sl.chapters) delete sl.chapters[chapter.n];
      await rm(path.join(dir, `chapter-${chapter.n}`), { recursive: true, force: true });
      sl.compile = undefined;
      if (!Object.values(sl.beats).some((b) => b.ops.length)) sl.status = "waiting";
      log(run, `Scenes of lecture ${a.lecture}, chapter ${chapter.n} reset.`);
    }
    saveRun(run, true);
    return run;
  }
  if (a.action === "compile") {
    lectureOf(a.lecture);
    if (busy.has(busyKey(id, a.lecture))) throw new Error(`lecture ${a.lecture} is being built already`);
    lock(run, [a.lecture], async () => {
      await compileLecture(run, a.lecture);
    });
    return run;
  }
  if (a.action === "render") {
    const sl = lectureOf(a.lecture);
    const script = scriptOf(run, a.lecture)!;
    const chapter = script.chapters.find((c) => c.n === a.chapter);
    if (!chapter) throw new Error(`lecture ${a.lecture} has no chapter ${a.chapter}`);
    if (a.beat !== undefined && !chapter.beats.some((b) => b.n === a.beat)) throw new Error(`beat ${a.beat} is not in chapter ${a.chapter}`);
    if (!chapter.beats.some((b) => sl.beats[b.n]?.ops.length)) throw new Error(`chapter ${a.chapter} has no visuals yet: build its scenes first`);
    const key = `${id}|${a.lecture}|${a.chapter}|${a.beat ?? "all"}`;
    if (renderBusy.has(key)) throw new Error("that is being rendered already");
    const look = cleanLook({ ...st.look, ...(a.style ? { style: a.style } : {}), ...(a.art ? { art: a.art } : {}) });
    const target: SceneRender = { status: "running", style: look.style, art: look.art, started: Date.now() };
    if (a.beat !== undefined) beatState(sl, a.beat).render = target;
    else (sl.chapters ??= {})[a.chapter] = target as SceneChapterRender;
    renderBusy.add(key);
    st.renders = (st.renders ?? 0) + 1;
    saveRun(run, true);
    void (async () => {
      try {
        await renderPart(run, a.lecture, a.chapter, a.beat, look, target);
      } catch (error) {
        Object.assign(target, { status: "failed", error: (error as Error).message, at: Date.now() });
      } finally {
        renderBusy.delete(key);
        st.renders = Math.max(0, (st.renders ?? 1) - 1);
        saveRun(run, true);
      }
    })();
    return run;
  }

  // Builds and fixes.
  const scripted = run.lectures.filter((l) => scriptOf(run, l.n)).map((l) => l.n);
  if (!scripted.length) throw new Error("no lecture is scripted yet: build the scripts first (Script tab)");
  st.model = a.model || st.model || run.options.scenesModel || modelFor("scenes");
  const free = (n: number) => !busy.has(busyKey(id, n));
  if (a.action === "fix") {
    const sl = lectureOf(a.lecture);
    const broken = Object.values(sl.beats).filter((b) => b.errors?.length).map((b) => b.n);
    if (!broken.length) throw new Error(`lecture ${a.lecture} has no beat the compiler refused`);
    if (!free(a.lecture)) throw new Error(`lecture ${a.lecture} is being built already`);
    st.rounds += 1;
    lock(run, [a.lecture], async () => {
      await fixLecture(run, a.lecture);
    });
    return run;
  }
  let todo: number[];
  if (a.scope === "lecture" || a.scope === "chapter" || a.scope === "beat") {
    const sl = lectureOf(a.lecture);
    if (!free(a.lecture!)) throw new Error(`lecture ${a.lecture} is being built already`);
    const script = scriptOf(run, a.lecture!)!;
    if (a.scope === "chapter" && !script.chapters.some((c) => c.n === a.chapter)) throw new Error(`lecture ${a.lecture} has no chapter ${a.chapter}`);
    if (a.scope === "beat" && !script.chapters.some((c) => c.beats.some((b) => b.n === a.beat))) throw new Error(`lecture ${a.lecture} has no beat ${a.beat}`);
    void sl;
    todo = [a.lecture!];
  } else if (a.scope === "next") {
    const next = scripted.find((n) => free(n) && st.lectures[n]?.status !== "done");
    if (next === undefined) throw new Error("every scripted lecture has its scenes, or is being built: rebuild one, or all");
    todo = [next];
  } else if (a.scope === "all") {
    todo = scripted.filter(free);
  } else {
    todo = scripted.filter((n) => free(n) && st.lectures[n]?.status !== "done");
    if (!todo.length) throw new Error("every scripted lecture has its scenes, or is being built: rebuild one, or all");
  }
  if (!todo.length) throw new Error("every lecture is being built already");
  st.rounds += 1;
  for (const n of todo) {
    const sl = lectureState(run, n);
    Object.assign(sl, { status: "waiting", error: undefined, doing: "queued" });
  }
  if (a.scope === "all") log(run, `Scenes rebuilt: ${todo.length} lecture(s).`);
  const what = a.scope === "chapter" ? { chapter: a.chapter! } : a.scope === "beat" ? { beat: a.beat! } : {};
  lock(run, todo, (n) => buildLecture(run, n, what, a.note), (a.scope === "all" || a.scope === "rest") && a.oneAtATime ? 1 : AT_ONCE);
  return run;
}

/** Run `work` for each lecture, `atOnce` at a time, each lecture locked while it runs; the step's status kept. */
function lock(run: Run, lectures: number[], work: (n: number) => Promise<void>, atOnce = AT_ONCE) {
  const st = stateOf(run);
  const key = `${run.id}:scenes`;
  for (const n of lectures) busy.add(busyKey(run.id, n));
  const first = !active.get(run.id);
  active.set(run.id, (active.get(run.id) ?? 0) + 1);
  jobs.add(key);
  if (first) {
    clearStop(key);
    Object.assign(st, { status: "running", error: undefined, started: Date.now(), ended: undefined });
  }
  saveRun(run, true);
  void (async () => {
    const queue = [...lectures];
    const worker = async () => {
      for (let n = queue.shift(); n !== undefined; n = queue.shift()) {
        const sl = lectureState(run, n);
        try {
          if (!stopRequested(key)) await work(n);
        } catch (error) {
          Object.assign(sl, { status: "failed", error: (error as Error).message });
        } finally {
          busy.delete(busyKey(run.id, n));
          if (sl.status === "running" || sl.status === "waiting") sl.status = Object.keys(sl.beats).length ? "done" : "waiting";
          for (const b of Object.values(sl.beats)) if (b.status === "running") b.status = b.ops.length ? "done" : "waiting";
          sl.doing = undefined;
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
        log(run, "Scenes stopped: what was built is kept.");
      } else {
        st.status = failed && failed === all.length ? "failed" : "done";
        st.error = failed ? `${failed} lecture(s) failed: see each one's error.` : undefined;
      }
      jobs.delete(key);
      clearStop(key);
      st.ended = Date.now();
    }
    saveRun(run, true);
  })();
}

/** Lectures being built now, by number. */
export function buildingScenes(runId: string): number[] {
  return [...busy].filter((k) => k.startsWith(`${runId}|`)).map((k) => Number(k.slice(runId.length + 1)));
}

/** The lecture's beats as the prompt gives them. */
export function beatInputs(run: Run, n: number): SceneBeatInput[] {
  const script = scriptOf(run, n)!;
  const lecture = run.lectures.find((l) => l.n === n)!;
  const lines = linesOf(lecture.text ?? "");
  const figures = new Map(lectureFigures(run, n).map((f) => [f.id, f]));
  const sl = lectureState(run, n);
  return script.chapters.flatMap((c) => c.beats.map((b) => {
    const shown = beatFigures(b).map((id) => figures.get(id)).filter((f): f is NonNullable<typeof f> => !!f);
    return { n: b.n, chapter: c.n, text: b.lines.map((k) => lines[k - 1] ?? "").join(" ").trim(), show: b.show,
      ...(shown.length ? { figures: shown.map((f) => ({ id: f.id, way: f.way, caption: f.caption, ready: f.ready })) } : {}),
      kinds: kindsFor(run, sl, b.n),
      ...(sl.beats[b.n]?.ops.length ? { ops: sl.beats[b.n].ops } : {}) };
  }));
}

/** One call: the visuals of the beats `ask` names, written into the lecture's state. */
async function writeBeats(run: Run, n: number, ask: ScenesAsk, problems?: Record<number, string[]>, note?: string): Promise<void> {
  const st = stateOf(run);
  const sl = lectureState(run, n);
  const script = scriptOf(run, n)!;
  const lecture = run.lectures.find((l) => l.n === n)!;
  const beats = beatInputs(run, n);
  const targets = beats.filter((b) => ask.what === "lecture" || (ask.what === "chapter" && b.chapter === ask.chapter)
    || (ask.what === "beat" && b.n === ask.beat) || (ask.what === "fix" && ask.beats.includes(b.n))).map((b) => b.n);
  const labels = Object.fromEntries(VISUAL_KINDS.map((k) => [k.id, k.label]));
  // The kinds told: the run's, and any a target beat has of its own (its line says which it may use).
  const kinds = targets.length ? ALL_KINDS.filter((k) => targets.some((t) => kindsFor(run, sl, t).includes(k))) : st.kinds;
  // A beat's line says what it may use only when that is less than what the prompt tells.
  for (const b of beats) if (b.kinds && (!targets.includes(b.n) || kinds.every((k) => b.kinds!.includes(k)))) delete b.kinds;
  const figures = lectureFigures(run, n).map((f) => ({ id: f.id, way: f.way, caption: f.caption, ready: f.ready }));
  const label = ask.what === "chapter" ? `Scenes: lecture ${n}, chapter ${ask.chapter}` : ask.what === "beat" ? `Scenes: lecture ${n}, beat ${ask.beat}`
    : ask.what === "fix" ? `Scenes: lecture ${n}, mend ${targets.length} beat(s)` : `Scenes: lecture ${n}`;
  const call = newCall(run, { step: "scenes", label, lecture: n, model: st.model,
    prompt: scenesPrompt({ lecture: { n, title: lecture.title }, look: lookWords(st.look), kinds, labels,
      chapters: script.chapters.map((c) => ({ n: c.n, title: c.title, narration: c.narration, map: c.map })),
      beats, figures, region: sl.region, ask, problems, note, manimAgent: st.manimAgent !== false, subject: await subjectOf(run, n) }) });
  sl.calls.push(call.id);
  for (const t of targets) {
    const b = beatState(sl, t);
    b.status = "running";
    b.calls.push(call.id);
  }
  saveRun(run);
  const reply = await callTool({ call, tool: SCENES_TOOL, onChange: () => saveRun(run), fake: () => fakeScenes(run, n, beats.filter((b) => targets.includes(b.n)), kinds) });
  if (!reply) {
    for (const t of targets) Object.assign(beatState(sl, t), { status: sl.beats[t].ops.length ? "done" : "failed" });
    throw new Error(`the call failed: ${call.error ?? "no reply"}`);
  }
  const answered = new Map<number, unknown[]>();
  const extras = new Map<number, Pick<SceneBeat, "paragraph" | "pause" | "about">>();
  for (const b of Array.isArray(reply.beats) ? reply.beats as { beat?: unknown; do?: unknown; paragraph?: unknown; pause?: unknown; about?: unknown }[] : []) {
    const k = Math.round(Number(b?.beat));
    if (!targets.includes(k) || answered.has(k)) continue;
    answered.set(k, Array.isArray(b.do) ? b.do : []);
    const pause = Number(b.pause);
    extras.set(k, { paragraph: b.paragraph === true || undefined, pause: Number.isFinite(pause) && pause > 0 ? Math.min(pause, 4) : undefined,
      about: typeof b.about === "string" && b.about.trim() ? b.about.trim().slice(0, 120) : undefined });
  }
  if (typeof reply.emblem === "string" && reply.emblem.trim() && (!sl.emblem || ask.what === "lecture")) sl.emblem = reply.emblem.trim().slice(0, 160);
  let droppedAll = 0;
  for (const t of targets) {
    const b = beatState(sl, t);
    const ops = answered.get(t);
    if (!ops) {
      b.status = b.ops.length ? "done" : "failed";
      continue;
    }
    const kept = filterOps(ops as Record<string, unknown>[], kindsFor(run, sl, t));
    droppedAll += kept.dropped.length;
    Object.assign(b, { ops: kept.ops, dropped: kept.dropped, status: "done", edited: false, errors: undefined, notes: undefined,
      paragraph: undefined, pause: undefined, about: undefined, ...extras.get(t) });
  }
  const missing = targets.filter((t) => !answered.has(t));
  check(call, "Beats", missing.length ? "fail" : "pass", missing.length ? `${missing.length} of ${targets.length} beat(s) not answered: ${missing.slice(0, 12).map((t) => `#${t}`).join(", ")}`
    : `all ${targets.length} beat(s) answered`);
  if (droppedAll) check(call, "Switched off", "fixed", `${droppedAll} operation(s) or picture(s) of a kind switched off (or unknown) taken out`);
  const region = reply.region && typeof reply.region === "object" ? reply.region as Record<string, unknown> : undefined;
  const needsMap = script.chapters.some((c) => c.map);
  if (region && needsMap && (!sl.region || ask.what === "lecture")) {
    sl.region = region;
    check(call, "Region", "pass", JSON.stringify(region));
  } else if (needsMap && !sl.region && st.kinds.includes("map")) {
    check(call, "Region", "info", "a chapter is on a map but no region was given: its map operations are left out by the compiler");
  }
  sl.scriptAt = run.script?.lectures[n]?.at;
  saveRun(run);
}

/** A whole lecture (chapter by chapter), one chapter, or one beat; compiled; the refused beats mended once. */
async function buildLecture(run: Run, n: number, what: { chapter?: number; beat?: number }, note?: string) {
  const sl = lectureState(run, n);
  const script = scriptOf(run, n)!;
  const key = `${run.id}:scenes`;
  Object.assign(sl, { status: "running", error: undefined });
  const chapters = what.chapter ? [what.chapter] : what.beat ? [] : script.chapters.map((c) => c.n);
  if (what.beat) {
    sl.doing = `beat ${what.beat}`;
    saveRun(run);
    await writeBeats(run, n, { what: "beat", beat: what.beat }, undefined, note);
  }
  for (const [i, c] of chapters.entries()) {
    if (stopRequested(key)) return;
    sl.doing = chapters.length > 1 ? `chapter ${c} (${i + 1} of ${chapters.length})` : `chapter ${c}`;
    saveRun(run);
    await writeBeats(run, n, { what: "chapter", chapter: c }, undefined, note);
  }
  if (stopRequested(key)) return;
  await agentsOn(run, n, (b) => !b.ops.some((o) => o.op === "manim" && o.code));
  if (stopRequested(key)) return;
  await compileLecture(run, n);
  if (Object.values(sl.beats).some((b) => b.errors?.length) && !stopRequested(key)) await fixLecture(run, n);
  Object.assign(sl, { status: "done", at: Date.now(), doing: undefined });
  saveRun(run);
}

/** The refused beats asked again with what the compiler said, then the lecture compiled again. */
async function fixLecture(run: Run, n: number) {
  const sl = lectureState(run, n);
  const agent = stateOf(run).manimAgent !== false;
  // A refused Manim figure goes back to the Manim agent (told what the compiler said); the rest to the scene writer.
  const isFigure = (b: SceneBeat) => agent && b.ops.some((o) => o.op === "manim");
  const broken = Object.values(sl.beats).filter((b) => b.errors?.length && !isFigure(b));
  const figures = Object.values(sl.beats).filter((b) => b.errors?.length && isFigure(b));
  if (!broken.length && !figures.length) return;
  sl.doing = `mending ${broken.length + figures.length} beat(s)`;
  saveRun(run);
  if (broken.length) await writeBeats(run, n, { what: "fix", beats: broken.map((b) => b.n) }, Object.fromEntries(broken.map((b) => [b.n, b.errors!])));
  for (const b of figures) {
    if (stopRequested(`${run.id}:scenes`)) break;
    await runManimAgent(run, n, b.n, { instruction: `The compiler refused this beat's figure: ${b.errors!.join("; ")}. Mend it.`, stop: () => stopRequested(`${run.id}:scenes`) });
  }
  await agentsOn(run, n, (b) => broken.some((x) => x.n === b.n) && !b.ops.some((o) => o.op === "manim" && o.code));
  await compileLecture(run, n);
  Object.assign(sl, { status: "done", at: Date.now() });
}

/** The Manim agent on each beat whose manim op `needs` it (the scene writer planned it), in beat order. */
async function agentsOn(run: Run, n: number, needs: (b: SceneBeat) => boolean) {
  if (stateOf(run).manimAgent === false) return;
  const sl = lectureState(run, n);
  const order = scriptOf(run, n)!.chapters.flatMap((c) => c.beats.map((b) => b.n));
  const todo = order.filter((k) => sl.beats[k]?.ops.some((o) => o.op === "manim") && needs(sl.beats[k]));
  for (const [i, k] of todo.entries()) {
    if (stopRequested(`${run.id}:scenes`)) return;
    sl.doing = `the Manim agent: beat ${k} (${i + 1} of ${todo.length})`;
    saveRun(run);
    await runManimAgent(run, n, k, { stop: () => stopRequested(`${run.id}:scenes`) });
  }
}

// ---------------- the engine's script ----------------

/** The lecture's figures as files the engine shows (a generated one when it is made, else the book's), by id. */
export async function figureFiles(run: Run, n: number): Promise<Record<string, { file: string; caption: string }>> {
  const out: Record<string, { file: string; caption: string }> = {};
  const figures = lectureFigures(run, n);
  if (!figures.length) return out;
  const book = await bookOf(run.documentId).catch(() => null);
  for (const f of figures) {
    const block = run.blocks.find((b) => b.id === f.id);
    if (!block) continue;
    const made = run.generation?.figures[f.id];
    let file = made?.status === "done" && made.file && existsSync(made.file) ? made.file : undefined;
    if (file?.endsWith(".svg")) {
      // The engine shows pictures: the SVG drawn as a PNG.
      const png = path.join(scenesDir(run.id), "figures", `${f.id.replace(/[^\w]+/g, "_")}.png`);
      try {
        await mkdir(path.dirname(png), { recursive: true });
        await sharp(await readFile(file), { density: 200 }).png().toFile(png);
        file = png;
      } catch {
        file = undefined;
      }
    }
    file ??= book ? figureFile(block, book.json, book.figures) : undefined;
    if (file) out[f.id] = { file, caption: captionOf(run.blocks, block) ?? f.caption ?? "" };
  }
  return out;
}

/** The lecture as the engine's beat script, in `look`; `only` keeps one chapter, up to one beat. */
export async function engineScript(run: Run, n: number, look: Look, only?: { chapter: number; upTo?: number }): Promise<Record<string, unknown>> {
  const script = scriptOf(run, n)!;
  const lecture = run.lectures.find((l) => l.n === n)!;
  const lines = linesOf(lecture.text ?? "");
  const sl = lectureState(run, n);
  const region = script.chapters.some((c) => c.map) && sl.region ? sl.region : null;
  let chapters = script.chapters.map((c) => ({
    n: c.n, title: c.title, narration: c.narration, map: c.map && !!region,
    beats: c.beats.map((b) => {
      const sb = sl.beats[b.n];
      return { n: b.n, say: b.lines.map((k) => lines[k - 1] ?? "").join(" ").trim() || "…", do: sb?.ops ?? [],
        ...(sb?.paragraph ? { paragraph: true } : {}), ...(sb?.pause ? { pause: sb.pause } : {}), ...(sb?.about ? { about: sb.about } : {}) };
    }),
  }));
  if (only) {
    chapters = chapters.filter((c) => c.n === only.chapter).map((c) => ({ ...c, beats: only.upTo === undefined ? c.beats
      : c.beats.slice(0, c.beats.findIndex((b) => b.n === only.upTo) + 1) }));
  }
  return {
    title: lecture.title, sub: "", style: look.style, art: look.art, region, place_figures: false,
    ...(sl.emblem ? { emblem: sl.emblem } : {}), ...(sl.subject?.genre ? { genre: sl.subject.genre } : {}),
    figures: await figureFiles(run, n),
    chapters: chapters.map((c) => ({ title: c.title, narration: c.narration, map: c.map,
      beats: c.beats.map(({ n: _, ...b }) => b) })),
  };
}

/** The engine's subjects (genre.py), as v1's page offers them; another subject is decided from the lecture's words. */
const GENRES = ["mathematics", "physics", "chemistry", "biology", "history", "geography", "economics", "general"];

/**
 * A lecture's subject and its kit, as v1 tells its writer (the engine's genre.py): the run's subject when it names
 * one of the engine's, else decided from the lecture's words. Kept on the lecture.
 */
export async function subjectOf(run: Run, n: number): Promise<NonNullable<SceneLecture["subject"]> | undefined> {
  const sl = lectureState(run, n);
  if (sl.subject) return sl.subject;
  const chosen = String(run.options.subject ?? "").trim().toLowerCase();
  const text = run.lectures.find((l) => l.n === n)?.text ?? "";
  const out = GENRES.includes(chosen)
    ? await runPython([path.join(engineDir(), "genre.py"), "--genre", chosen], engineDir(), {}, undefined, 60_000)
    : await runPython([path.join(engineDir(), "genre.py")], engineDir(), {}, text.slice(0, 20000), 60_000);
  try {
    const j = JSON.parse(out.stdout.slice(out.stdout.indexOf("{"))) as NonNullable<SceneLecture["subject"]>;
    if (!j.genre) return undefined;
    sl.subject = { genre: j.genre, label: j.label ?? j.genre, guidance: j.guidance, map: j.map, kit: j.kit };
    return sl.subject;
  } catch {
    return undefined;
  }
}

/** The images the Manim agent made for a lecture, by name (the engine's image("name") reads it). */
export function agentRegistry(runId: string, n: number): string {
  return path.join(scenesDir(runId), `L${n}`, "agent-images.json");
}

/** The model that decides whether a picture made before is used again (picture_judge.py), when that is on. */
export function reuseModel(run: Run): string | undefined {
  const st = run.scenes;
  return st?.reuseJudge === false ? undefined : st?.reuseModel || modelFor("reuse");
}

export function engineEnv(run: Run, n?: number): Record<string, string> {
  const image = run.options.imageModel || modelFor("image");
  const judge = reuseModel(run);
  return { PYTHONPATH: engineDir(), PANIM_VOICE: "silent", PANIM_IMAGE_MODEL: image, PANIM_DIAGRAM_MODEL: image,
    ...(usingFixture(image) ? { PANIM_IMAGE_FAKE: "1" } : {}),
    ...(judge ? { PANIM_PICTURE_JUDGE: judge, ...(usingFixture(judge) ? { PANIM_PICTURE_JUDGE_FAKE: "1" } : {}) } : { PANIM_PICTURE_JUDGE: "" }),
    ...(n !== undefined && existsSync(agentRegistry(run.id, n)) ? { PANIM_BLOCK_IMAGES: agentRegistry(run.id, n) } : {}) };
}

type Judged = { what: string; model?: string; candidates?: { key: string; what: string; prompt?: string; reusable?: boolean }[];
  state?: string[]; criteria?: Record<string, string>; asked_now?: boolean; usd?: number; fake?: boolean; choice?: string | null;
  probabilities?: Record<string, number>; confidence?: number | null; seconds?: number; action?: "reuse" | "match" | "fresh";
  picked?: string | null; unsure?: boolean; error?: string };

type Compiled = { source?: string; errors: string[]; warnings: string[]; minutes?: number; generated?: { prompt?: string; model?: string; usd?: number }[];
  /** The engine's image model's report (genimage.report): asked, made, cached, and each picture it could not get. */
  images?: { model?: string; asked?: number; made?: number; cached?: number; failed?: { what?: string; model?: string; error?: string }[];
    /** The decision model's answers on reusing a picture made before (picture_judge.py). */
    judged?: Judged[] };
  /** The call each decision asked now was recorded as, by what was asked. */
  judgedCalls?: Record<string, string>;
  /** Every picture the scene shows (compile_lecture.pictures_used): its file, what it shows, where. */
  pictures?: { file?: string; description?: string; role?: string; context?: { chapter?: number; beat?: number; caption?: string } }[] };

/**
 * A compile's AI pictures, by beat: each picture the scene shows (copied beside the run's scenes so the page can
 * show it), made now or found made before, with the prompt the image model was sent (the engine keeps it beside each
 * picture), its model and cost; and each one the image model could not make, with its error.
 */
async function picturesByBeat(run: Run, n: number, c: Compiled, beatAt: (chapter: number, beat: number) => number | undefined,
  missing: MissingPicture[]): Promise<BeatPicture[]> {
  const out: BeatPicture[] = [];
  const now = new Set((c.generated ?? []).map((g) => String((g as { path?: string }).path ?? "")));
  const dir = path.join(scenesDir(run.id), `L${n}`, "pictures");
  for (const p of c.pictures ?? []) {
    if (!p.file || !/\/gen-[^/]*\.png$/.test(p.file) || !existsSync(p.file)) continue;
    const beat = p.context?.chapter && p.context.beat ? beatAt(p.context.chapter, p.context.beat) : undefined;
    let side: { prompt?: string; model?: string; usd?: number } = {};
    try {
      side = JSON.parse(await readFile(p.file.replace(/\.png$/, ".json"), "utf8"));
    } catch {}
    const copy = path.join(dir, path.basename(p.file));
    if (!existsSync(copy)) {
      await mkdir(dir, { recursive: true });
      await writeFile(copy, await readFile(p.file));
    }
    const what = String(p.description ?? "");
    out.push({ what, caption: p.context?.caption, role: p.role, status: now.has(p.file) ? "made" : "cached",
      url: fileUrl(run.id, copy), prompt: side.prompt, model: side.model, usd: Number(side.usd) || undefined, beat,
      decision: await decisionFor(run, c, what, dir) });
  }
  for (const m of missing) out.push({ what: m.what, status: "failed", error: m.error, beat: m.beat });
  return out;
}

/** The decision model's answer on a picture (by what it shows), with the picture it chose copied to be shown. */
async function decisionFor(run: Run, c: Compiled, what: string, dir: string): Promise<BeatPicture["decision"]> {
  const same = (x?: string) => String(x ?? "").replace(/\s+/g, " ").trim().toLowerCase();
  const j = (c.images?.judged ?? []).find((x) => same(x.what) === same(what));
  if (!j?.action) return undefined;
  let pickedUrl: string | undefined;
  if (j.picked) {
    const from = path.join(imageCache(), `${j.picked}.png`);
    const to = path.join(dir, `${j.picked}.png`);
    if (existsSync(from)) {
      if (!existsSync(to)) {
        await mkdir(dir, { recursive: true });
        await writeFile(to, await readFile(from));
      }
      pickedUrl = fileUrl(run.id, to);
    }
  }
  return { action: j.action, choice: j.choice, confidence: j.confidence, probabilities: j.probabilities, unsure: j.unsure,
    candidates: j.candidates ?? [], picked: j.picked, pickedUrl, model: j.model, call: c.judgedCalls?.[j.what], askedNow: !!j.asked_now, error: j.error };
}

/** Where the engine keeps the pictures it made (genimage.CACHE). */
function imageCache(): string {
  return process.env.PANIM_IMAGE_CACHE || path.join(engineDir(), ".cache", "images");
}

/** The engine's words for a picture it could not get (compile_lecture: "no reusable illustration for '...'; it is left out"). */
const LEFT_OUT = /no reusable illustration for (['"])(.*?)\1;? it is left out/i;

/**
 * The AI pictures a compile could not get, each with the image model's error and its beat (from the engine's
 * warning). With no request made at all, why: the image model is off here.
 */
function missingPictures(c: Compiled, beatOf: (warning: string) => number | undefined): { missing: MissingPicture[]; report?: ImageReport } {
  const failed = c.images?.failed ?? [];
  const asked = c.images?.asked ?? 0;
  const missing: MissingPicture[] = [];
  for (const w of c.warnings) {
    const m = LEFT_OUT.exec(w);
    if (!m) continue;
    const what = m[2];
    const same = (x?: string) => String(x ?? "").replace(/\s+/g, " ").trim().toLowerCase();
    const why = failed.find((f) => same(f.what) === same(what))?.error
      ?? (asked === 0 ? "the image model was not asked: pictures are off here (no OPENROUTER_API_KEY, or PANIM_IMAGES=0)" : undefined);
    if (!missing.some((x) => x.what === what && x.beat === beatOf(w))) missing.push({ what, error: why, beat: beatOf(w) });
  }
  const report = c.images ? { model: c.images.model, asked, made: c.images.made ?? 0, cached: c.images.cached ?? 0,
    failed: new Set(failed.map((f) => f.what)).size } : undefined;
  return { missing, report };
}

/**
 * Each decision on reusing a picture asked now, as a call (a decision model's: the state, the question's options,
 * the answer), so the Calls and Costs tabs have it; an answer kept from a compile before is no call.
 */
function recordJudged(run: Run, n: number, judged: Judged[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const j of judged) {
    if (!j.asked_now) continue;
    const call = newCall(run, { step: "scenes", label: `Reuse a picture made before? "${j.what.slice(0, 70)}${j.what.length > 70 ? "…" : ""}"`, lecture: n,
      model: j.model ?? "decision model", effort: "off",
      prompt: { system: [], user: (j.state ?? []).map((t, i) => part(i ? `picture${i - 1}` : "needed", i ? `Picture ${i - 1} made before` : "The picture needed now", i ? "context" : "ask", t)) } });
    Object.assign(call, { api: "decisions", tool: { use: { type: "choice", criteria: j.criteria ?? {} } }, status: j.error ? "failed" : "done",
      ended: call.started + Math.round((j.seconds ?? 0) * 1000), cost: j.usd ?? 0, provider: j.fake ? "fixture" : "openrouter",
      attempts: [{ started: call.started, ended: call.started + Math.round((j.seconds ?? 0) * 1000), ...(j.error ? { error: j.error } : {}) }],
      output: { choice: j.choice, probabilities: j.probabilities, confidence: j.confidence }, ...(j.error ? { error: j.error } : {}) });
    check(call, "Decision", j.error ? "fail" : "info", j.error ? `no answer (${j.error}): drawn fresh`
      : `${j.action === "reuse" ? `shown again: ${j.picked}` : j.action === "match" ? `drawn anew to match ${j.picked}` : "drawn fresh"}` +
        `${j.confidence != null ? ` (${Math.round(j.confidence * 100)}%)` : ""}${j.unsure ? "; it was unsure, so not taken as it said" : ""}`);
    lectureState(run, n).calls.push(call.id);
    out[j.what] = call.id;
  }
  return out;
}

export async function compile(run: Run, script: Record<string, unknown>, dir: string, n?: number): Promise<Compiled> {
  await mkdir(dir, { recursive: true });
  const out = await runPython([path.join(engineDir(), "compile_lecture.py"), "-", "--json"], dir, engineEnv(run, n), JSON.stringify(script), COMPILE_TIMEOUT);
  try {
    const json = JSON.parse(out.stdout.slice(out.stdout.indexOf("{"))) as Compiled & { source?: string | null };
    const judgedCalls = n !== undefined ? recordJudged(run, n, json.images?.judged ?? []) : {};
    return { ...json, source: json.source ?? undefined, errors: json.errors ?? [], warnings: json.warnings ?? [], judgedCalls };
  } catch {
    return { errors: [`the engine's compile failed: ${errorOf(out.out).slice(-800)}`], warnings: [] };
  }
}

/** Which beat (the script's number) a compiler message names ("chapter 2 beat 3: ..."), within `only`'s chapters. */
function beatNamed(run: Run, n: number, text: string, chapters?: number[]): number | undefined {
  const m = /chapter (\d+) beat (\d+)/i.exec(text);
  if (!m) return undefined;
  const script = scriptOf(run, n)!;
  const list = chapters ? script.chapters.filter((c) => chapters.includes(c.n)) : script.chapters;
  return list[Number(m[1]) - 1]?.beats[Number(m[2]) - 1]?.n;
}

/** The whole lecture checked and compiled by the engine; its messages put on the beats they name. */
async function compileLecture(run: Run, n: number) {
  const st = stateOf(run);
  const sl = lectureState(run, n);
  sl.doing = "compiling (and making its pictures)";
  const began = Date.now();
  sl.compile = { status: "running", errors: [], warnings: [], at: began };
  saveRun(run);
  const c = await compile(run, await engineScript(run, n, st.look), path.join(scenesDir(run.id), `L${n}`, "compile"), n);
  for (const b of Object.values(sl.beats)) Object.assign(b, { errors: undefined, notes: undefined, missing: undefined });
  const lost = missingPictures(c, (w) => beatNamed(run, n, w));
  for (const m of lost.missing) if (m.beat !== undefined) (beatState(sl, m.beat).missing ??= []).push(m);
  for (const b of Object.values(sl.beats)) b.pictures = undefined;
  const script = scriptOf(run, n)!;
  for (const p of await picturesByBeat(run, n, c, (ci, bi) => script.chapters[ci - 1]?.beats[bi - 1]?.n, lost.missing)) {
    if (p.beat !== undefined) (beatState(sl, p.beat).pictures ??= []).push(p);
  }
  const errors: string[] = [];
  const warnings: string[] = [];
  for (const e of c.errors) {
    const at = beatNamed(run, n, e);
    if (at !== undefined) (beatState(sl, at).errors ??= []).push(e.replace(/^chapter \d+ beat \d+:\s*/i, ""));
    else errors.push(e);
  }
  for (const w of c.warnings) {
    const at = beatNamed(run, n, w);
    if (at !== undefined) (beatState(sl, at).notes ??= []).push(w.replace(/chapter \d+ beat \d+:\s*/i, ""));
    else warnings.push(w);
  }
  const pictures = (c.generated ?? []).map((g) => ({ prompt: String(g.prompt ?? ""), model: g.model, usd: Number(g.usd) || 0 }));
  sl.compile = { status: c.errors.length ? "failed" : "done", errors, warnings, pictures, minutes: c.minutes, seconds: (Date.now() - began) / 1000, at: Date.now(),
    ...(lost.missing.length ? { missing: lost.missing } : {}), ...(lost.report ? { images: lost.report } : {}) };
  const cost = pictures.reduce((k, p) => k + (p.usd ?? 0), 0);
  if (pictures.length) {
    // The pictures the image model made while compiling, as a call, so the Costs tab counts them.
    const call = newCall(run, { step: "scenes", label: `Pictures for lecture ${n} (${pictures.length}, made while compiling)`, lecture: n,
      model: pictures[0].model ?? "image model", effort: "off",
      prompt: { system: [], user: pictures.map((p, i) => part(`p${i + 1}`, `Picture ${i + 1}`, "items", p.prompt)) } });
    Object.assign(call, { api: "image", status: "done", ended: Date.now(), cost, provider: usingFixture(call.model) ? "fixture" : "openrouter",
      attempts: [{ started: began, ended: Date.now() }], output: { pictures: pictures.length } });
    sl.calls.push(call.id);
  }
  sl.doing = undefined;
  saveRun(run);
}

// ---------------- renders ----------------

export async function renderSlot(): Promise<() => void> {
  if (renderOn.n >= RENDERS_AT_ONCE) await new Promise<void>((resolve) => renderQueue.push(resolve));
  renderOn.n += 1;
  return () => {
    renderOn.n -= 1;
    renderQueue.shift()?.();
  };
}

export function ffmpeg(args: string[]): Promise<{ code: number | null; out: string }> {
  return new Promise((resolve) => {
    const child = spawn(process.env.V2_FFMPEG || "ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...args]);
    let out = "";
    child.stderr.on("data", (d) => (out += d));
    child.on("close", (code) => resolve({ code, out }));
    child.on("error", (e) => resolve({ code: -1, out: String(e) }));
  });
}

export async function duration(file: string): Promise<number> {
  return new Promise((resolve) => {
    const child = spawn(process.env.V2_FFPROBE || "ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file]);
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.on("close", () => resolve(Number(out.trim()) || 0));
    child.on("error", () => resolve(0));
  });
}

/** Where a scene's playable program is, as the page's player loads it: its geometry and its pictures. */
export type Playable = { ir: string; assets: string; fps: number; frames: number; blockers: string[];
  /** The narration track the exporter mixed (a scene spoken with a voice), as a file. */
  narration?: string;
  /** Each line said, in order: where it starts (seconds), its words (the chapter's title card first). */
  said: { start: number; text?: string }[];
  checks: { say: string; issues: string[]; fixed: string[] }[] };

/**
 * A compiled scene made playable as v1's web player plays it: recorded by the exporter into the program the phone
 * plays (engine/tools/export_scene.py, v2's copy of v1's, on v2's engine), then expanded into the geometry the
 * browser draws (engine/tools/scene_ir.py). Silent; the engine's beat log says where each line starts.
 */
export async function playable(run: Run, n: number, dir: string, source: string, env: Record<string, string> = {}): Promise<Playable> {
  const scene = path.join(dir, "scene.py");
  await writeFile(scene, source, "utf8");
  const out = path.join(dir, "out");
  const beatLog = path.join(dir, "beats.jsonl");
  const checkLog = path.join(dir, "checks.jsonl");
  await rm(beatLog, { force: true });
  await rm(checkLog, { force: true });
  const tools = path.join(engineDir(), "tools");
  const exported = await runPython([path.join(tools, "export_scene.py"), scene, "GeneratedScene", out], dir,
    { ...engineEnv(run, n), PANIM_BEAT_LOG: beatLog, PANIM_CHECK_LOG: checkLog, ...env }, undefined, RENDER_TIMEOUT);
  let summary: { blockers?: string[]; error?: string; narration?: { file?: string } } = {};
  try {
    summary = JSON.parse(exported.stdout.slice(exported.stdout.indexOf("{")));
  } catch {
    throw new Error(/No module named ['"]?manim/.test(exported.out) ? "Manim is not installed for this Python: run harness/scripts/setup-python.sh"
      : `the export failed: ${errorOf(exported.out)}`);
  }
  if (summary.error) throw new Error(`the export failed: ${summary.error}`);
  const expanded = await runPython([path.join(tools, "scene_ir.py"), out, "GeneratedScene"], dir, {}, undefined, RENDER_TIMEOUT);
  let ir: { fps?: number; frames?: number; error?: string } = {};
  try {
    ir = JSON.parse(expanded.stdout.trim().split("\n").pop() ?? "{}");
  } catch {
    throw new Error(`the player's geometry could not be made: ${errorOf(expanded.out)}`);
  }
  if (ir.error) throw new Error(`the player's geometry could not be made: ${ir.error}`);
  const rows = existsSync(beatLog) ? (await readFile(beatLog, "utf8")).split("\n").filter(Boolean).map((l) => JSON.parse(l) as { kind: string; start: number; text?: string }) : [];
  const checks = existsSync(checkLog) ? (await readFile(checkLog, "utf8")).split("\n").filter(Boolean).map((l) => JSON.parse(l) as Playable["checks"][number]) : [];
  const rel = (f: string) => encodeURIComponent(path.relative(scenesDir(run.id), f));
  return { ir: `/api/runs/${run.id}/scenes/ir?p=${rel(out)}&v=${Date.now()}`, assets: `/api/runs/${run.id}/scenes/file?p=${rel(path.join(out, "dsl", "generated", "images"))}${encodeURIComponent("/")}`,
    fps: ir.fps ?? 30, frames: ir.frames ?? 0, blockers: summary.blockers ?? [], said: rows.filter((r) => r.kind === "beat"), checks,
    ...(summary.narration?.file ? { narration: path.join(out, summary.narration.file) } : {}) };
}

/**
 * A chapter made playable (up to `beat`, when one is asked for), in `look`, for v1's web player: each beat found in
 * the engine's beat log, as the frames it plays. A beat's render plays the beat (the chapter before it is there,
 * recorded); a chapter's plays it all, with each beat's frames for its strip.
 */
async function renderPart(run: Run, n: number, chapter: number, beat: number | undefined, look: Look, target: SceneRender) {
  const release = await renderSlot();
  const began = Date.now();
  try {
    const dir = path.join(scenesDir(run.id), `L${n}`, beat !== undefined ? `beat-${beat}` : `chapter-${chapter}`);
    await rm(dir, { recursive: true, force: true });
    await mkdir(dir, { recursive: true });
    const script = await engineScript(run, n, look, { chapter, upTo: beat });
    const compiled = await compile(run, script, dir, n);
    if (!compiled.source) throw new Error(compiled.errors.length ? `it does not compile: ${compiled.errors.slice(0, 4).join("; ")}` : "the engine made no scene of it");
    const source = compiled.source.split("\n").filter((l) => !/self\.(title_slide|outro_fade)\(/.test(l)).join("\n");
    const p = await playable(run, n, dir, source);
    const sc = scriptOf(run, n)!.chapters.find((c) => c.n === chapter)!;
    // The script rendered is one chapter: the engine's "chapter 1" is this one.
    const lost = missingPictures(compiled, (w) => {
      const m = /chapter \d+ beat (\d+)/i.exec(w);
      return m ? sc.beats[Number(m[1]) - 1]?.n : undefined;
    });
    const wanted = beat !== undefined ? sc.beats.slice(0, sc.beats.findIndex((b) => b.n === beat) + 1) : sc.beats;
    const offset = p.said.length > wanted.length ? p.said.length - wanted.length : 0;
    const lines = linesOf(run.lectures.find((l) => l.n === n)!.text ?? "");
    const last = Math.max(0, p.frames - 1);
    const at = (i: number) => {
      const b = wanted[i];
      const start = p.said[offset + i]?.start ?? 0;
      const end = p.said[offset + i + 1]?.start ?? last / p.fps;
      const text = b.lines.map((k) => lines[k - 1] ?? "").join(" ").trim().slice(0, 200);
      const found = p.checks.filter((c) => c.say && text.startsWith(c.say.slice(0, 60)));
      return { n: b.n, start, end, from: Math.min(last, Math.round(start * p.fps)), to: Math.min(last, Math.max(0, Math.round(end * p.fps) - 1)),
        issues: found.flatMap((c) => c.issues ?? []), fixed: found.flatMap((c) => c.fixed ?? []) };
    };
    const shown = await picturesByBeat(run, n, compiled, (_, bi) => sc.beats[bi - 1]?.n, lost.missing);
    const pictures = beat !== undefined ? shown.filter((x) => x.beat === beat) : shown;
    const common = { status: "done", ir: p.ir, assets: p.assets, fps: p.fps, frames: p.frames, blockers: p.blockers.length ? p.blockers : undefined,
      pictures: pictures.length ? pictures : undefined,
      missing: lost.missing.length ? lost.missing : undefined, images: lost.report,
      still: undefined, clip: undefined, video: undefined, seconds: (Date.now() - began) / 1000, at: Date.now(), error: undefined };
    if (beat !== undefined) {
      const me = at(wanted.length - 1);
      Object.assign(target, { ...common, range: [me.from, last], issues: me.issues, fixed: me.fixed });
    } else {
      const beats = wanted.map((_, i) => at(i));
      Object.assign(target, { ...common, beats, issues: beats.flatMap((b) => b.issues), fixed: beats.flatMap((b) => b.fixed) });
    }
  } finally {
    release();
  }
}

// ---------------- offline stand-in ----------------

/** The stand-in's visuals (no key): a heading on each chapter's first beat, the beat's figure, a diagram, a definition. */
function fakeScenes(run: Run, n: number, beats: SceneBeatInput[], kinds: string[]) {
  const on = new Set(kinds);
  const script = scriptOf(run, n)!;
  const first = new Set(script.chapters.map((c) => c.beats[0]?.n));
  const out = beats.map((b) => {
    const ops: Record<string, unknown>[] = [];
    const chapter = script.chapters.find((c) => c.n === b.chapter)!;
    if (first.has(b.n)) ops.push({ op: "panel", title: chapter.title.slice(0, 40) });
    const words = b.text.replace(/[^\p{L}\p{N}\s]/gu, "").split(/\s+/).filter((w) => w.length > 3);
    if (b.figures?.length && on.has("figure")) ops.push({ op: "picture", figure: b.figures[0].id, caption: b.figures[0].caption.slice(0, 60) });
    else if (first.has(b.n) && on.has("diagram") && words.length >= 3) {
      const nodes = words.slice(0, 3).map((w, i) => ({ id: `n${i + 1}`, label: w }));
      ops.push({ op: "diagram", id: `d${b.n}`, kind: "flow", nodes, edges: [["n1", "n2"], ["n2", "n3"]] });
    } else if (on.has("define") && b.n % 3 === 0 && words[0]) ops.push({ op: "define", term: words[0], meaning: b.text.slice(0, 60) });
    else ops.push({ op: "fact", text: (b.show || b.text).slice(0, 50) });
    return { beat: b.n, do: ops };
  });
  return { region: null, beats: out };
}
