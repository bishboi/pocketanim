/**
 * The scenes step: each beat of a lecture's script given its visuals, as the engine's operations
 * (harness_v2/engine/compile_lecture.py), then compiled by the engine, mended, and rendered a beat or a chapter at a
 * time to be looked at.
 *
 *   - Each chapter stands alone: it is written, compiled and mended by itself, with its own map region, so a lecture's
 *     chapters are built side by side (V2_SCENES_CHAPTERS_PARALLEL at once). Its writer sees the other chapters' words,
 *     never their visuals, so what it is given does not depend on which chapter finished first.
 *   - BUILD: one call per chapter (prompts/scenes.ts); a whole lecture, one chapter, or one beat (the beats of its
 *     chapter given as they are). The narration is the script's: the model writes only each beat's "do". Code takes
 *     out what is switched off (visual-kinds.ts) and says so.
 *   - COMPILE: each chapter as the engine's beat script (the run's look, its figures as files), checked and compiled
 *     by the engine; its errors and notes are put on the beats they name; the lecture's compile is its chapters' put
 *     together. The image model makes the pictures asked for while it compiles (the engine's genimage.py; a stand-in
 *     picture when there is no key).
 *   - FIX: a chapter's beats the compiler refused are asked again with what it said, once by itself after a build,
 *     and whenever the page asks.
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
import { SCENES_TOOL, scenesPrompt, type BeatVoice, type SceneBeatInput, type ScenesAsk } from "./prompts/scenes";
import { WORD_TIMING_TOOL, wordTimingPrompt, type TimingBeat, type TimingSlot } from "./prompts/word-timing";
import { estimatedWords, type BeatWords } from "./director";
import { BEAT_CHOREOGRAPHY_TOOL, BEAT_DIRECTOR_TOOL, beatChoreographyPrompt, beatDirectorPrompt } from "./prompts/beat-director";
import { MAIN, applyPatch, beatsProblems, fitBeats, isPlanOfBeats, opParts, paragraphsOf, patchStillFits, readBeats, readPatch, upBefore,
  type BeatPatch, type BeatsPlan, type ContentBeat, type PatchStep } from "./beat-director";
import { manualFor } from "./manuals";
import { PRIMITIVES, primitiveText } from "./primitives";
import { check, clearStop, jobs, log, newCall, stopJob, stopRequested } from "./run";
import { runManimAgent } from "./manim-agent";
import { beatFigures, lectureFigures } from "./script-figures";
import { captionOf, figureFile } from "./source/blocks";
import { linesOf } from "./source/book";
import { DATA, loadRun, saveRun } from "./store";
import { DEFAULT_LOOK, cleanLook, lookWords, type Look } from "./styles";
import type { Beat, BeatPicture, ImageReport, MissingPicture, Run, SceneBeat, SceneChapterRender, SceneCompile, SceneLecture, SceneRender, ScenesState, SpokenLine } from "./types";
import { ALL_KINDS, VISUAL_KINDS, filterOps, kindOfOp } from "./visual-kinds";

const MAP_OPS = new Set(VISUAL_KINDS.find((k) => k.id === "map")?.ops ?? []);

/** Whether a lecture's beats point at the map anywhere (a marker, a shaded state, a journey...). */
function usesMap(sl: { beats: Record<number, { ops: { op?: unknown }[] } | undefined> }): boolean {
  return Object.values(sl.beats).some((b) => b?.ops.some((o) => MAP_OPS.has(String(o.op))));
}
import { MOTION_LOOKS } from "./prompts/scenes-motion";

const AT_ONCE = Math.max(1, Number(process.env.V2_SCENES_PARALLEL) || 3);
/** A lecture's chapters built at once (each written, compiled and mended by itself). */
const CHAPTERS_AT_ONCE = Math.max(1, Number(process.env.V2_SCENES_CHAPTERS_PARALLEL) || 4);
const RENDERS_AT_ONCE = Math.max(1, Number(process.env.V2_RENDER_PARALLEL) || 2);
const COMPILE_TIMEOUT = Math.max(60, Number(process.env.V2_COMPILE_TIMEOUT_SECONDS) || 900) * 1000;
const RENDER_TIMEOUT = Math.max(60, Number(process.env.V2_RENDER_TIMEOUT_SECONDS) || 900) * 1000;

type Scope = "rest" | "all" | "next" | "lecture" | "chapter" | "beat";
export type ScenesAction =
  | { action: "look"; style?: string; art?: string }
  | { action: "kinds"; kinds: string[] }
  | { action: "beatKinds"; lecture: number; beat: number; kinds: string[] | null }
  | { action: "chapterKinds"; lecture: number; chapter: number; kinds: string[] | null }
  | { action: "edit"; lecture: number; beat: number; ops: unknown; render?: boolean }
  | { action: "editChapter"; lecture: number; chapter: number; beats: { beat: number; ops: unknown; paragraph?: boolean; pause?: number; about?: string; screen?: string }[];
      emblem?: string | null; region?: Record<string, unknown> | null; render?: boolean }
  | { action: "editPlan"; lecture: number; chapter: number; plan: unknown; choreograph?: boolean; render?: boolean }
  | { action: "editCues"; lecture: number; chapter: number; cues: unknown; render?: boolean }
  | { action: "rebuildScene"; lecture: number; chapter: number; scene: string; note?: string; render?: boolean }
  | { action: "build"; scope: Scope; lecture?: number; chapter?: number; beat?: number; model?: string; oneAtATime?: boolean; note?: string }
  | { action: "fix"; lecture: number; model?: string }
  | { action: "compile"; lecture: number }
  | { action: "render"; lecture: number; chapter: number; beat?: number; style?: string; art?: string }
  | { action: "agent"; lecture: number; beat: number; instruction?: string; model?: string }
  | { action: "agentSettings"; on?: boolean; model?: string }
  | { action: "reuseSettings"; on?: boolean; model?: string }
  | { action: "pace"; maxOps?: number; change?: "paragraph" | "beat" }
  | { action: "motion"; look?: string; energy?: string; transition?: string; idle?: string; timeline?: string;
      voiceFirst?: boolean; music?: boolean; director?: boolean }
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
  // Runs made before the templates were one kind with the rest had them switched on under another name.
  if (!run.scenes.kinds.includes("templates") && ((run.scenes as { engine?: string }).engine === "motion" || run.scenes.kinds.includes("motion"))) {
    run.scenes.kinds = ALL_KINDS.filter((k) => k === "templates" || run.scenes!.kinds.includes(k));
  }
  delete (run.scenes as { engine?: string }).engine;
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
    settleScenes(run);
    return run;
  }
  settleScenes(run);
  if (run.legacy) throw new Error(run.legacy);
  const st = stateOf(run);
  if (a.action === "look") {
    st.look = cleanLook({ ...st.look, ...(a.style ? { style: a.style } : {}), ...(a.art ? { art: a.art } : {}) });
    saveRun(run, true);
    return run;
  }
  if (a.action === "pace") {
    if (a.maxOps !== undefined) {
      const k = Math.round(Number(a.maxOps));
      if (!(k >= 0 && k <= 20)) throw new Error("operations a beat: 0 (no limit) to 20");
      st.maxOps = k === 0 ? undefined : k;                  // left out: no limit (the default)
    }
    if (a.change) st.visualChange = a.change === "beat" ? "beat" : undefined;
    saveRun(run, true);
    return run;
  }
  if (a.action === "motion") {
    // How the lectures move (their look, energy, transition, idle motion, timeline style), and how they are built:
    // for the next builds, compiles and renders; the beats already built stay as they are.
    const m = { ...(st.motion ?? {}) };
    for (const k of ["look", "energy", "transition", "idle", "timeline"] as const) if (a[k] !== undefined) m[k] = a[k] || undefined;
    if (m.look && !(MOTION_LOOKS as readonly string[]).includes(m.look)) throw new Error(`the look is one of ${MOTION_LOOKS.join(", ")}`);
    st.motion = m;
    if (a.voiceFirst !== undefined) st.voiceFirst = a.voiceFirst ? undefined : false;
    if (a.director !== undefined) st.director = a.director ? undefined : false;
    if (a.music !== undefined) st.music = a.music ? undefined : false;
    log(run, `Scenes: ${st.motion.look ? `look ${st.motion.look}` : "the style's own look"}.`);
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
    const kept = filterOps(a.ops as Record<string, unknown>[], allowedFor(run, sl, a.beat));
    Object.assign(b, { ops: kept.ops, dropped: kept.dropped, edited: true, status: "done", errors: undefined, notes: undefined });
    const chapter = chapterOfBeat(run, a.lecture, a.beat)!;
    lock(run, [a.lecture], async () => {
      await compileChapter(run, a.lecture, chapter);
      // Saved and rendered again (the Scenes tab's "Save and re-render"): the beat, as it now is.
      if (a.render) startRender(run, a.lecture, chapter, a.beat);
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
      const kept = filterOps(e.ops as Record<string, unknown>[], allowedFor(run, sl, e.beat));
      Object.assign(b, { ops: kept.ops, dropped: kept.dropped, edited: true, status: "done", errors: undefined, notes: undefined,
        paragraph: e.paragraph || undefined, pause: e.pause || undefined, about: e.about || undefined,
        screen: e.screen === "join" ? "join" : undefined });
    }
    if (a.emblem !== undefined) sl.emblem = a.emblem || undefined;
    if (a.region !== undefined) (sl.regions ??= {})[a.chapter] = a.region;
    lock(run, [a.lecture], async () => {
      await compileChapter(run, a.lecture, a.chapter);
      if (a.render) startRender(run, a.lecture, a.chapter);
    });
    return run;
  }
  if (a.action === "rebuildScene") {
    // One scene of a chapter built as one piece built again (the director and the choreography, for its beats only);
    // the chapter's voice kept. Compiled, and rendered when asked.
    lectureOf(a.lecture);
    if (busy.has(busyKey(id, a.lecture))) throw new Error(`lecture ${a.lecture} is being built: wait, or stop it`);
    const had = lectureState(run, a.lecture).plans?.[a.chapter];
    if (had && !isPlanOfBeats(had)) throw new Error(LEGACY_PLAN);
    // A scene is a paragraph of the director's beats ("P2": the second).
    const paragraph = isPlanOfBeats(had) ? paragraphsOf(had.beats)[Number(/^P(\d+)$/i.exec(a.scene)?.[1]) - 1] : undefined;
    if (!paragraph) throw new Error(`chapter ${a.chapter} has no scene ${a.scene}`);
    log(run, `Lecture ${a.lecture}, chapter ${a.chapter}: paragraph ${a.scene} built again${a.note ? ` (${a.note})` : ""}; its voice kept.`);
    lock(run, [a.lecture], async () => {
      await redirectBeats(run, a.lecture, a.chapter, paragraph, { note: a.note, label: `paragraph ${a.scene} again` });
      await compileChapter(run, a.lecture, a.chapter);
      if (a.render) startRender(run, a.lecture, a.chapter);
    });
    return run;
  }
  if (a.action === "editPlan" || a.action === "editCues") {
    // A chapter built as one piece, changed by hand (the Scenes tab's beats and patch). Compiled, and rendered when
    // asked.
    const sl = lectureOf(a.lecture);
    if (busy.has(busyKey(id, a.lecture))) throw new Error(`lecture ${a.lecture} is being built: wait, or stop it`);
    if (!scriptOf(run, a.lecture)!.chapters.some((c) => c.n === a.chapter)) throw new Error(`lecture ${a.lecture} has no chapter ${a.chapter}`);
    const had = sl.plans?.[a.chapter];
    if (!had) throw new Error(`chapter ${a.chapter} was not built as one piece (with the director): build it first`);
    if (!isPlanOfBeats(had)) throw new Error(LEGACY_PLAN);
    await editBeats(run, a, had);
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
      await compileChapter(run, a.lecture, chapterOfBeat(run, a.lecture, a.beat)!);
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
      if (sl.regions) delete sl.regions[chapter.n];
      if (sl.compiles) delete sl.compiles[chapter.n];
      await rm(path.join(dir, `chapter-${chapter.n}`), { recursive: true, force: true });
      await rm(path.join(dir, "compile", `chapter-${chapter.n}`), { recursive: true, force: true });
      sl.compile = mergedCompile(sl);
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
    if (renderBusy.has(`${id}|${a.lecture}|${a.chapter}|${a.beat ?? "all"}`)) throw new Error("that is being rendered already");
    startRender(run, a.lecture, a.chapter, a.beat, a.style, a.art);
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
      const chapters = [...new Set(broken.map((k) => chapterOfBeat(run, a.lecture, k)).filter((c): c is number => c !== undefined))];
      await eachAtOnce(chapters, CHAPTERS_AT_ONCE, (c) => fixChapter(run, a.lecture, c));
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

/** A chapter (or one beat of it) rendered in the background, in the run's look (or `style`/`art`); its state kept on
 * the beat or the chapter. A second render of the same thing while one is going is not started. */
function startRender(run: Run, n: number, chapter: number, beat?: number, style?: string, art?: string) {
  const st = stateOf(run);
  const sl = lectureState(run, n);
  const key = `${run.id}|${n}|${chapter}|${beat ?? "all"}`;
  if (renderBusy.has(key)) return;
  const look = cleanLook({ ...st.look, ...(style ? { style } : {}), ...(art ? { art } : {}) });
  const target: SceneRender = { status: "running", style: look.style, art: look.art, started: Date.now() };
  if (beat !== undefined) beatState(sl, beat).render = target;
  else (sl.chapters ??= {})[chapter] = target as SceneChapterRender;
  renderBusy.add(key);
  st.renders = (st.renders ?? 0) + 1;
  saveRun(run, true);
  void (async () => {
    try {
      await renderPart(run, n, chapter, beat, look, target);
    } catch (error) {
      Object.assign(target, { status: "failed", error: (error as Error).message, at: Date.now() });
    } finally {
      renderBusy.delete(key);
      st.renders = Math.max(0, (st.renders ?? 1) - 1);
      saveRun(run, true);
    }
  })();
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

/**
 * A lecture shown as being built that no job of this server is building (a job that ended without setting it back, a
 * build cut off) set back: done when it has beats, else waiting; and the step itself when nothing is running. Else the
 * page keeps its buttons off for a build that is not there.
 */
function settleScenes(run: Run): void {
  const st = run.scenes;
  if (!st) return;
  let changed = false;
  for (const [k, sl] of Object.entries(st.lectures)) {
    if (busy.has(busyKey(run.id, Number(k)))) continue;
    if (sl.status === "running" || (sl.status === "waiting" && sl.doing)) {
      sl.status = Object.keys(sl.beats).length ? "done" : "waiting";
      sl.doing = undefined;
      for (const b of Object.values(sl.beats)) if (b.status === "running") b.status = b.ops.length ? "done" : "waiting";
      changed = true;
    }
  }
  if (st.status === "running" && !active.get(run.id)) {
    st.status = "stopped";
    st.ended = Date.now();
    changed = true;
  }
  if (changed) saveRun(run, true);
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
  // The chapter it writes in: the other chapters' beats are given as words only, never their visuals, so a chapter is
  // written the same whichever chapters were built before it; its own region is the one already chosen.
  const own = ask.what === "chapter" ? ask.chapter : ask.what === "lecture" ? undefined : chapterOfBeat(run, n, targets[0] ?? -1);
  if (own !== undefined) for (const b of beats) if (b.chapter !== own) delete b.ops;
  const chosen = own !== undefined ? (sl.regions?.[own] ?? sl.region ?? undefined) : sl.region;
  const call = newCall(run, { step: "scenes", label, lecture: n, model: st.model,
    prompt: scenesPrompt({ lecture: { n, title: lecture.title }, look: motionLookWords(st), kinds, labels,
      chapters: script.chapters.map((c) => ({ n: c.n, title: c.title, narration: c.narration, map: c.map })),
      beats, figures, region: chosen, ask, problems, note, manimAgent: st.manimAgent !== false, subject: await subjectOf(run, n),
      pace: { maxOps: st.maxOps, change: st.visualChange } }) });
  sl.calls.push(call.id);
  for (const t of targets) {
    const b = beatState(sl, t);
    b.status = "running";
    b.calls.push(call.id);
  }
  saveRun(run);
  const reply = await callTool({ call, tool: SCENES_TOOL, onChange: () => saveRun(run),
    fake: () => fakeScenes(run, n, beats.filter((b) => targets.includes(b.n)), kinds) });
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
    const kept = filterOps(ops as Record<string, unknown>[], allowedFor(run, sl, t));
    droppedAll += kept.dropped.length;
    Object.assign(b, { ops: kept.ops, dropped: kept.dropped, status: "done", edited: false, errors: undefined, notes: undefined,
      paragraph: undefined, pause: undefined, about: undefined, ...extras.get(t) });
  }
  const missing = targets.filter((t) => !answered.has(t));
  check(call, "Beats", missing.length ? "fail" : "pass", missing.length ? `${missing.length} of ${targets.length} beat(s) not answered: ${missing.slice(0, 12).map((t) => `#${t}`).join(", ")}`
    : `all ${targets.length} beat(s) answered`);
  if (droppedAll) check(call, "Switched off", "fixed", `${droppedAll} operation(s) or picture(s) of a kind switched off (or unknown) taken out`);
  const region = reply.region && typeof reply.region === "object" ? reply.region as Record<string, unknown> : undefined;
  // Every chapter is on the board; the map comes in for the beats that point at it, in any chapter.
  const needsMap = script.chapters.some((c) => c.map) || usesMap(sl);
  if (region && needsMap && own !== undefined && (ask.what === "chapter" || !sl.regions?.[own])) {
    (sl.regions ??= {})[own] = region;
    check(call, "Region", "pass", `chapter ${own}: ${JSON.stringify(region)}`);
  } else if (region && needsMap && own === undefined && (!sl.region || ask.what === "lecture")) {
    sl.region = region;
    check(call, "Region", "pass", JSON.stringify(region));
  } else if (needsMap && !chosen && !region && st.kinds.includes("map")) {
    check(call, "Region", "info", "beats point at the map but no region was given: their map operations are left out by the compiler");
  }
  sl.scriptAt = run.script?.lectures[n]?.at;
  // A chapter written again by this writer (not as one piece) is no longer its plan's, nor strict.
  if (ask.what === "lecture" || ask.what === "chapter") {
    for (const c of new Set(targets.map((t) => chapterOfBeat(run, n, t)))) if (c !== undefined && sl.plans?.[c]) delete sl.plans[c];
  }
  saveRun(run);
  if (voiceFirst(st)) {
    const written = targets.filter((t) => answered.has(t));
    for (const c of new Set(written.map((t) => chapterOfBeat(run, n, t)).filter((c): c is number => c !== undefined))) {
      await timeWords(run, n, c, written.filter((t) => chapterOfBeat(run, n, t) === c));
    }
  }
}

// ---------------------------------------------------------------- the word timing (current engine) --------------

/** Operations that act as their line begins (compile_lecture.UNSAID_OPS): not timed to a word. */
const UNSAID = new Set(["clear", "unstage", "manim", "answer", "emphasis", "zoom", "camera", "pause", "think", "map_in", "map_away", "recap"]);
/** A part's name (compile_lecture.NAMED_BY). */
const NAMED_BY = ["label", "text", "title", "name", "term", "date"];
/** Lists of ids, places on the screen, colours: no thing of their own. */
const NOT_PARTS = new Set(["show", "hide", "ids", "order", "range", "colors", "colours", "keep", "path", "at", "from", "to", "size"]);
const PART_DEPTH = 4;

type Place = (string | number)[];
type Slot = TimingSlot & { beat: number; place: Place };

/** What an operation shows, in a few words, for the timing call. */
function opWords(o: Record<string, unknown>): string {
  const said = ["title", "text", "label", "term", "name", "place", "caption", "generate", "question", "kind"]
    .map((k) => o[k]).filter((v) => typeof v === "string" && v.trim()).map((v) => String(v).trim().slice(0, 70));
  return `${String(o.op ?? "operation")}${said.length ? ` ${JSON.stringify(said.slice(0, 2).join(" — "))}` : ""}`;
}

/** The things a beat's operations put on the screen that can each come on with a word: the operations (not those that
 * act as the line begins) and the parts inside them (a node, a label, an event, a point...), with where each is. */
function timingSlots(beat: number, ops: Record<string, unknown>[], next: () => number): Slot[] {
  const out: Slot[] = [];
  const inside = (value: unknown, place: Place, parent: number, what: string, depth: number) => {
    if (depth > PART_DEPTH || !value || typeof value !== "object") return;
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      if (key === "on" || NOT_PARTS.has(key)) continue;
      if (!Array.isArray(inner)) {
        if (inner && typeof inner === "object") inside(inner, [...place, key], parent, what, depth + 1);
        continue;
      }
      inner.forEach((item, i) => {
        if (typeof item === "string" && /\p{L}/u.test(item) && item.trim().length <= 80) {
          const id = next();
          out.push({ id, beat, place: [...place, key, i], parent, what: `${key.replace(/s$/, "")} ${JSON.stringify(item.trim())}` });
        } else if (item && typeof item === "object" && !Array.isArray(item)) {
          const o = item as Record<string, unknown>;
          const name = NAMED_BY.map((k) => o[k]).find((v) => (typeof v === "string" || typeof v === "number") && String(v).trim());
          if (name !== undefined) {
            const id = next();
            out.push({ id, beat, place: [...place, key, i], parent, what: `${key.replace(/s$/, "")} ${JSON.stringify(String(name).trim().slice(0, 70))}`,
              ...(typeof o.on === "string" && o.on.trim() ? { writer: o.on.trim() } : {}) });
            inside(o, [...place, key, i], id, what, depth + 1);
          } else inside(o, [...place, key, i], parent, what, depth + 1);
        }
      });
    }
  };
  ops.forEach((o, i) => {
    if (!o || typeof o !== "object" || UNSAID.has(String(o.op))) return;
    const id = next();
    out.push({ id, beat, place: [i], what: opWords(o), ...(typeof o.on === "string" && o.on.trim() ? { writer: o.on.trim() } : {}) });
    inside(o, [i], id, opWords(o), 1);
  });
  return out;
}

const plain = (w: string) => w.toLowerCase().normalize("NFC").replace(/[^\p{L}\p{N}]+/gu, "");

/** The stand-in's words (no key): each thing on the first word of the line that is in its name (or its writer's
 * words), else on its picture's word. */
function fakeWords(beats: TimingBeat[], slots: Slot[]): { anchors: { slot: number; word: number }[] } {
  const anchors: { slot: number; word: number }[] = [];
  const got = new Map<number, number>();
  for (const s of slots) {
    const words = beats.find((b) => b.beat === s.beat)?.words ?? [];
    const named = `${s.what} ${s.writer ?? ""}`.toLowerCase();
    const k = words.findIndex((w) => plain(w.w).length > 3 && named.includes(plain(w.w)));
    const word = Math.max(k >= 0 ? k : 0, s.parent !== undefined ? got.get(s.parent) ?? 0 : 0);
    got.set(s.id, word);
    anchors.push({ slot: s.id, word });
  }
  return { anchors };
}

/**
 * The current engine's word timing (voice first): one call of its own (the timing role's model), after the scene
 * writer, for a voiced chapter's beats just written. It is shown each beat's line as the voice says it (its words by
 * number with their times) and every thing its operations put on the screen, and gives each the word it comes on
 * with; that is written as the thing's "on" ("w7", the line's words from word 7: compile_lecture.anchors), a string
 * part as {"name", "on"}. Checked: a word inside its line, a part never before its picture.
 */
async function timeWords(run: Run, n: number, c: number, targets: number[]): Promise<void> {
  const voiced = await voicedBeats(run, n, c);
  if (!voiced) return;
  const sl = lectureState(run, n);
  let count = 0;
  const slots: Slot[] = [];
  const beats: TimingBeat[] = [];
  for (const t of targets) {
    const v = voiced.get(t);
    const ops = (sl.beats[t]?.ops ?? []) as Record<string, unknown>[];
    if (!v?.words.length || !ops.length) continue;
    const own = timingSlots(t, ops, () => ++count);
    if (!own.length) continue;
    slots.push(...own);
    beats.push({ beat: t, seconds: v.seconds, pause: v.pause, words: v.words, slots: own });
  }
  if (!slots.length) return;
  const { voiceOf } = await import("./voice");
  const model = voiceOf(run).settings.timingModel || modelFor("timing");
  const title = scriptOf(run, n)?.chapters.find((x) => x.n === c)?.title;
  const call = newCall(run, { step: "scenes", label: `Time the pictures to the words: lecture ${n}, chapter ${c} (${slots.length} thing(s) in ${beats.length} beat(s))`,
    lecture: n, model, effort: "low", prompt: wordTimingPrompt({ lecture: n, chapter: c, title, beats }) });
  sl.calls.push(call.id);
  for (const b of beats) beatState(sl, b.beat).calls.push(call.id);
  saveRun(run);
  const reply = await callTool({ call, tool: WORD_TIMING_TOOL, onChange: () => saveRun(run), fake: () => fakeWords(beats, slots) });
  const answer = new Map<number, number>();
  for (const a of Array.isArray(reply?.anchors) ? reply!.anchors as { slot?: unknown; word?: unknown }[] : []) {
    const id = Math.round(Number(a?.slot));
    const word = Math.round(Number(a?.word));
    if (Number.isFinite(id) && Number.isFinite(word) && !answer.has(id)) answer.set(id, word);
  }
  const words = new Map<number, number>();
  let mended = 0;
  let missing = 0;
  for (const s of slots) {
    const last = (voiced.get(s.beat)?.words.length ?? 1) - 1;
    const asked = answer.get(s.id);
    if (asked === undefined) missing += 1;
    let word = asked ?? (s.parent !== undefined ? words.get(s.parent) : undefined);
    if (word === undefined) continue;                // left as the writer had it
    const floor = s.parent !== undefined ? words.get(s.parent) ?? 0 : 0;
    const kept = Math.min(last, Math.max(0, floor, word));
    if (asked !== undefined && kept !== word) mended += 1;
    word = kept;
    words.set(s.id, word);
    // Written where the thing is: an operation's or a part's "on"; a part given as a string becomes {"name", "on"}.
    const ops = sl.beats[s.beat].ops as unknown[];
    let holder: unknown = ops;
    for (const step of s.place.slice(0, -1)) holder = (holder as Record<string | number, unknown>)?.[step];
    const key = s.place[s.place.length - 1];
    const at = (holder as Record<string | number, unknown>)?.[key];
    const on = word === 0 ? "start" : `w${word}`;
    if (typeof at === "string") (holder as unknown[])[key as number] = { name: at, on };
    else if (at && typeof at === "object") (at as Record<string, unknown>).on = on;
  }
  check(call, "Words", !answer.size ? "fail" : missing ? "fixed" : "pass", !answer.size
    ? "no words given: the pictures keep the scene writer's words"
    : `${words.size} of ${slots.length} thing(s) on their words${missing ? `; ${missing} not answered (a part on its picture's word, else the writer's)` : ""}`);
  if (mended) check(call, "In order", "fixed", `${mended} word(s) moved inside the line, or to the word of the picture they are in`);
  saveRun(run);
}

// ---------------------------------------------------------------- a chapter as one piece (director) ----------------

/** Whether a chapter is built as one piece (lib/beat-director.ts): its beats by the director, their timing by the
 * choreographer. On unless the Scenes tab turned it off (or V2_SCENES_DIRECTOR=0). */
export function directed(st: ScenesState): boolean {
  return st.director !== false && process.env.V2_SCENES_DIRECTOR !== "0";
}

/** Said when a chapter's plan was made by the retired motion-engine director (a run made before). */
const LEGACY_PLAN = "this chapter was built by the old motion-engine director (retired): build it again to change it";

/** What the director of a chapter is told: the scene writer's prompt for the chapter (the scenes model's instructions,
 * its beats, the kinds it may use), and what goes with it. */
async function directorBase(run: Run, n: number, c: number, note?: string) {
  const st = stateOf(run);
  const sl = lectureState(run, n);
  const script = scriptOf(run, n)!;
  const lecture = run.lectures.find((l) => l.n === n)!;
  const own = chapterBeats(run, n, c);
  const beats = beatInputs(run, n);
  for (const b of beats) if (b.chapter !== c) delete b.ops;
  const kinds = own.length ? ALL_KINDS.filter((k) => own.some((t) => kindsFor(run, sl, t).includes(k))) : st.kinds;
  for (const b of beats) if (b.kinds && (!own.includes(b.n) || kinds.every((k) => b.kinds!.includes(k)))) delete b.kinds;
  const labels = Object.fromEntries(VISUAL_KINDS.map((k) => [k.id, k.label]));
  const figures = lectureFigures(run, n).map((f) => ({ id: f.id, way: f.way, caption: f.caption, ready: f.ready }));
  const chosen = sl.regions?.[c] ?? sl.region ?? undefined;
  const base = scenesPrompt({ lecture: { n, title: lecture.title }, look: motionLookWords(st), kinds, labels,
    chapters: script.chapters.map((x) => ({ n: x.n, title: x.title, narration: x.narration, map: x.map })),
    beats, figures, region: chosen, ask: { what: "chapter", chapter: c }, note, manimAgent: st.manimAgent !== false,
    subject: await subjectOf(run, n), pace: { maxOps: st.maxOps, change: st.visualChange } });
  return { st, sl, script, own, beats, kinds, base, mine: beats.filter((b) => own.includes(b.n)) };
}

/** Each beat of a chapter as its voice says it (spoken first), else as it would be (estimated); and the voice's own. */
async function chapterWords(run: Run, n: number, c: number): Promise<{ words: Map<number, BeatWords>; voiced?: Map<number, BeatVoice> }> {
  const voiced = await voicedBeats(run, n, c);
  const own = new Set(chapterBeats(run, n, c));
  const words = new Map<number, BeatWords>();
  for (const b of beatInputs(run, n).filter((x) => own.has(x.n))) {
    const v = voiced?.get(b.n);
    words.set(b.n, v ? { n: b.n, text: b.text, seconds: v.seconds, pause: v.pause, words: v.words } : estimatedWords(b.n, b.text));
  }
  return { words, voiced };
}

/** The primitives the director may use (lib/primitives.ts), those of the kinds switched on. */
function primitiveCatalog(kinds: string[]): string {
  const pictures = ["figure", "illustration", "drawing", "gallery"];
  return PRIMITIVES.filter((p) => {
    if (p.op === "picture") return pictures.some((k) => kinds.includes(k));
    const k = kindOfOp(p.example);
    return !k || k === "base" || kinds.includes(k);
  }).map(primitiveText).join("\n");
}

// ---------------------------------------------------------------- a chapter's beats (current engine) -------------

/**
 * A chapter built as beats, changed by hand (the Scenes tab's JSON): the director's beats (the patch kept, the steps
 * that still fit; or choreographed again), or the patch. Compiled, and rendered when asked.
 */
async function editBeats(run: Run, a: Extract<ScenesAction, { action: "editPlan" | "editCues" }>, had: BeatsPlan) {
  const own = chapterBeats(run, a.lecture, a.chapter);
  const { words } = await chapterWords(run, a.lecture, a.chapter);
  let beats = had.beats;
  let patch: BeatPatch[] | undefined;
  let notes: string[] = [];
  if (a.action === "editPlan") {
    const raw = Array.isArray(a.plan) ? { beats: a.plan } : a.plan;
    if (!raw || typeof raw !== "object") throw new Error('the beats must be a JSON object: {"beats": [{"beat": 12, "do": [...]}]}');
    const got = readBeats(raw as Record<string, unknown>, own);
    keepBeatKinds(run, a.lecture, got.beats);
    if (!got.beats.some((b) => b.do.length)) throw new Error(`the beats show nothing that can be drawn${got.notes.length ? `: ${got.notes.slice(0, 4).join("; ")}` : ""}`);
    beats = got.beats;
    notes = got.notes;
    if (!a.choreograph) patch = patchStillFits(had.patch, beats, words).patch;
  } else {
    const got = readPatch(a.cues, beats, words);
    if (got.dropped.length) throw new Error(`${got.dropped.length} step(s) cannot be used: ${got.dropped.slice(0, 6).join("; ")}`);
    patch = got.patch;
  }
  log(run, `Lecture ${a.lecture}, chapter ${a.chapter}: its ${a.action === "editPlan" ? "beats" : "patch"} changed by hand` +
    (a.action === "editPlan" && a.choreograph ? ", choreographed again." : "."));
  lock(run, [a.lecture], async () => {
    applyBeats(run, a.lecture, a.chapter, beats, patch ?? await choreographBeats(run, a.lecture, a.chapter, beats, words), notes);
    saveRun(run);
    await compileChapter(run, a.lecture, a.chapter);
    if (a.render) startRender(run, a.lecture, a.chapter);
  });
}

/**
 * A chapter built as one piece on the current engine, in one JSON (lib/beat-director.ts). (1) The director writes the
 * chapter's beats: each line's operations, which line each part comes on, the paragraphs, pauses and joins; nothing
 * timed. Past the LIMITS: asked again once with what was wrong, then cut to fit. (2) Each few paragraphs are
 * choreographed in a call of their own, at once, answered as a patch on those beats. (3) Code applies the patch: the
 * beats as the compiler reads them. Both kept by chapter (sl.plans, kind "beats").
 */
async function directBeats(run: Run, n: number, c: number, note?: string): Promise<void> {
  const { st, sl, script, own, kinds, base, mine } = await directorBase(run, n, c, note);
  const catalog = primitiveCatalog(kinds);
  const ask = (label: string, problems?: { beats: unknown; list: string[] }) => {
    const call = newCall(run, { step: "scenes", label: `Scenes: lecture ${n}, chapter ${c} (${label})`, lecture: n, model: st.model,
      prompt: beatDirectorPrompt(base, { chapter: c, beats: own, catalog, problems }) });
    sl.calls.push(call.id);
    for (const t of own) beatState(sl, t).calls.push(call.id);
    saveRun(run);
    return call;
  };
  for (const t of own) beatState(sl, t).status = "running";
  const call = ask("director");
  let reply = await callTool({ call, tool: BEAT_DIRECTOR_TOOL, onChange: () => saveRun(run), fake: () => fakeBeats(run, n, mine, kinds) });
  if (!reply) {
    for (const t of own) Object.assign(beatState(sl, t), { status: sl.beats[t].ops.length ? "done" : "failed" });
    throw new Error(`the call failed: ${call.error ?? "no reply"}`);
  }
  let read = readBeats(reply, own);
  let dropped = keepBeatKinds(run, n, read.beats);
  const problems = beatsProblems(read.beats);
  if (problems.length) {
    check(call, "Limits", "fixed", `${problems.length} past the limits: ${problems.slice(0, 6).join("; ")}; asked again`);
    const again = ask("director, again within the limits", { beats: read.beats, list: problems });
    const second = await callTool({ call: again, tool: BEAT_DIRECTOR_TOOL, onChange: () => saveRun(run), fake: () => fakeBeats(run, n, mine, kinds) });
    if (second) {
      const read2 = readBeats(second, own);
      const dropped2 = keepBeatKinds(run, n, read2.beats);
      const left = beatsProblems(read2.beats);
      check(again, "Limits", left.length ? "fixed" : "pass", left.length ? `${left.length} still past them (cut to fit): ${left.slice(0, 6).join("; ")}` : "within the limits");
      if (read2.beats.some((b) => b.do.length) && left.length < problems.length) {
        reply = second;
        read = read2;
        dropped = dropped2;
      }
    }
  }
  const { beats } = read;
  const fitted = fitBeats(beats);
  if (fitted.length) check(call, "Cut to fit", "fixed", fitted.slice(0, 8).join("; "));
  const shown = beats.reduce((k, b) => k + b.do.length, 0);
  check(call, "Beats", shown ? "pass" : "fail", `${shown} operation(s) on ${beats.length} beat(s) in ${paragraphsOf(beats).length} paragraph(s)`);
  if (read.notes.length) check(call, "Mended", "fixed", read.notes.slice(0, 10).join("; "));
  if (dropped) check(call, "Switched off", "fixed", `${dropped} operation(s) or picture(s) of a kind switched off (or unknown) taken out`);
  if (typeof reply.emblem === "string" && reply.emblem.trim() && !sl.emblem) sl.emblem = reply.emblem.trim().slice(0, 160);
  const region = reply.region && typeof reply.region === "object" ? reply.region as Record<string, unknown> : undefined;
  if (region && (script.chapters.some((x) => x.map) || beats.some((b) => b.do.some((o) => MAP_OPS.has(String(o.op)))))) {
    (sl.regions ??= {})[c] = region;
    check(call, "Region", "pass", `chapter ${c}: ${JSON.stringify(region)}`);
  }
  const { words } = await chapterWords(run, n, c);
  const patch = await choreographBeats(run, n, c, beats, words);
  const notes = applyBeats(run, n, c, beats, patch, [...read.notes, ...fitted]);
  if (notes.length) check(call, "Applied", "fixed", `${notes.length} step(s) left out: ${notes.slice(0, 8).join("; ")}`);
  saveRun(run);
}

/** The kinds switched off, as in any build: a beat's operations of a kind switched off (or of none) taken out. How
 * many. */
function keepBeatKinds(run: Run, n: number, beats: ContentBeat[]): number {
  const sl = lectureState(run, n);
  let dropped = 0;
  for (const b of beats) {
    const kept = filterOps(b.do, allowedFor(run, sl, b.beat));
    dropped += kept.dropped.length;
    b.do = kept.ops as Record<string, unknown>[];
  }
  return dropped;
}

/** The beats to choreograph: all of them, or with `only` the whole paragraphs that have one of those beats. */
function beatsInScope(beats: ContentBeat[], only?: Set<number>): Set<number> {
  return new Set(paragraphsOf(beats).filter((r) => !only || r.some((b) => only.has(b))).flat());
}

/** A beat's steps in words, for the next beat's call ("what the line before did"). */
function stepsSaid(p: BeatPatch | undefined, beat: ContentBeat | undefined): string {
  if (!p || !p.steps.length) return "nothing timed (all came on as it began)";
  return p.steps.map((x) => `${x.at} ${x.do}${x.op !== undefined ? ` op ${x.op}${beat?.do[x.op] ? ` (${String(beat.do[x.op].op)})` : ""}` : ""}` +
    `${x.part ? ` ${x.part}` : ""}${x.target ? ` ${x.target}` : ""}${x.node ? ` ${x.node}` : ""}${x.how ? ` (${x.how})` : ""}` +
    `${x.enter ? ` enter ${x.enter}` : ""}${x.speed ? ` ${x.speed}` : ""}`).join("; ");
}

/**
 * The patch on a chapter's beats (with `only`, on the paragraphs that have those beats): one call a beat, in order
 * (the Choreography role's model), each shown the chapter's lines, its own line's words, the lines round it, what is
 * up as it begins, what the line before did (this call's answer, or the patch `kept`), its operations with every
 * choice each has, and their manuals.
 */
async function choreographBeats(run: Run, n: number, c: number, beats: ContentBeat[], words: Map<number, BeatWords>,
  only?: Set<number>, kept: BeatPatch[] = []): Promise<BeatPatch[]> {
  const sl = lectureState(run, n);
  const look = motionLookWords(stateOf(run));
  const scope = beatsInScope(beats, only);
  const up = upBefore(beats);
  const model = modelFor("choreography");
  const lines = beats.map((b) => ({ n: b.beat, text: words.get(b.beat)?.text ?? "" }));
  const done = new Map(kept.map((p) => [p.beat, p]));
  const out: BeatPatch[] = [];
  for (const [i, b] of beats.entries()) {
    if (!scope.has(b.beat)) continue;
    if (stopRequested(`${run.id}:scenes`)) break;
    // A Manim figure times itself (the Manim agent writes it to the beat's word times): not choreographed.
    const shown = { ...b, do: b.do.filter((o) => o.op !== "manim") };
    const kinds = [...new Set([...shown.do.map((o) => String(o.op)), "point", "shade", "focus", "unlabel", "unstage"])];
    const manuals = kinds.map((op) => ({ op, text: manualFor(op) })).filter((m) => m.text);
    const prev = beats[i - 1];
    const next = beats[i + 1];
    const call = newCall(run, { step: "scenes", label: `Choreography: lecture ${n}, chapter ${c}, beat ${b.beat}`, lecture: n, model, effort: "low",
      prompt: beatChoreographyPrompt({ lecture: n, chapter: c, look, beat: shown, all: beats, words: words.get(b.beat), lines, up: up.get(b.beat) ?? [], manuals,
        before: prev ? `b${prev.beat} "${words.get(prev.beat)?.text.slice(0, 160) ?? ""}": it did ${stepsSaid(done.get(prev.beat), prev)}` : undefined,
        after: next ? `b${next.beat} "${words.get(next.beat)?.text.slice(0, 160) ?? ""}"` : undefined }) });
    sl.calls.push(call.id);
    beatState(sl, b.beat).calls.push(call.id);
    saveRun(run);
    const reply = await callTool({ call, tool: BEAT_CHOREOGRAPHY_TOOL, onChange: () => saveRun(run), fake: () => fakePatch([shown], words).beats[0] });
    const { patch, dropped } = readPatch({ beats: [{ ...(reply ?? {}), beat: b.beat }] }, beats, words, new Set([b.beat]));
    const steps = patch.reduce((k, p) => k + p.steps.length, 0);
    check(call, "Steps", !reply ? "fail" : dropped.length ? "fixed" : "pass", !reply ? `no answer: ${call.error ?? ""}`
      : `${steps} step(s) on beat ${b.beat}` + (dropped.length ? `; ${dropped.length} left out: ${dropped.slice(0, 5).join("; ")}` : ""));
    for (const p of patch) {
      done.set(p.beat, p);
      out.push(p);
    }
  }
  return out;
}

/**
 * A chapter's beats with its patch applied (applyPatch), each beat's operations, paragraph, pause, about and screen
 * written; both kept (sl.plans, kind "beats"), to be seen and changed. What was left out.
 */
function applyBeats(run: Run, n: number, c: number, beats: ContentBeat[], patch: BeatPatch[], notes: string[] = []): string[] {
  const sl = lectureState(run, n);
  const applied = applyPatch(beats, patch);
  for (const b of beats) {
    Object.assign(beatState(sl, b.beat), { ops: applied.ops.get(b.beat) ?? [], dropped: [], status: "done", edited: false, errors: undefined,
      notes: undefined, paragraph: b.paragraph || undefined, pause: b.pause, about: b.about, screen: b.screen });
  }
  (sl.plans ??= {})[c] = { kind: "beats", beats, patch, at: Date.now(), notes: [...notes, ...applied.notes].slice(0, 60) };
  sl.scriptAt = run.script?.lectures[n]?.at;
  return applied.notes;
}

/**
 * Some beats of a chapter built on the current engine written again by the director (shown the chapter's beats; the
 * others kept): a paragraph rebuilt by hand, or the beats the compiler refused (`refused`: what it said of each).
 * Only those beats' paragraphs choreographed again; the rest of the patch kept.
 */
async function redirectBeats(run: Run, n: number, c: number, targets: number[], o: { note?: string; refused?: Record<number, string[]>; label: string }) {
  const had = lectureState(run, n).plans?.[c];
  if (!isPlanOfBeats(had)) throw new Error(`chapter ${c} was not built as beats by the director`);
  const { st, sl, kinds, base, mine } = await directorBase(run, n, c, o.note);
  const refused = o.refused ? Object.entries(o.refused).flatMap(([b, errs]) => errs.map((e) => `beat ${b}: ${e}`)) : undefined;
  const call = newCall(run, { step: "scenes", label: `Scenes: lecture ${n}, chapter ${c}, ${o.label} (director)`, lecture: n, model: st.model,
    prompt: beatDirectorPrompt(base, { chapter: c, beats: targets, catalog: primitiveCatalog(kinds),
      only: { beats: targets, all: had.beats, note: o.note, why: refused ? "the compiler refused them" : undefined },
      ...(refused ? { problems: { beats: had.beats.filter((b) => targets.includes(b.beat)), list: refused, refused: true } } : {}) }) });
  sl.calls.push(call.id);
  for (const t of targets) beatState(sl, t).calls.push(call.id);
  saveRun(run);
  const reply = await callTool({ call, tool: BEAT_DIRECTOR_TOOL, onChange: () => saveRun(run),
    fake: () => fakeBeats(run, n, mine.filter((b) => targets.includes(b.n)), kinds) });
  if (!reply) throw new Error(`the call failed: ${call.error ?? "no reply"}`);
  const read = readBeats(reply, targets);
  const dropped = keepBeatKinds(run, n, read.beats);
  const fitted = fitBeats(read.beats);
  // A paragraph keeps its start (readBeats starts one at its first beat); a mended beat keeps the paragraph it had.
  for (const b of read.beats) {
    const was = had.beats.find((x) => x.beat === b.beat);
    if (o.refused) b.paragraph = was?.paragraph;
  }
  const beats = had.beats.map((b) => read.beats.find((x) => x.beat === b.beat) ?? b);
  check(call, "Beats", read.beats.some((b) => b.do.length) ? "pass" : "fail", `${read.beats.reduce((k, b) => k + b.do.length, 0)} operation(s) on beats ${targets.join(", ")}`);
  if ([...read.notes, ...fitted].length) check(call, "Mended", "fixed", [...read.notes, ...fitted].slice(0, 8).join("; "));
  if (dropped) check(call, "Switched off", "fixed", `${dropped} operation(s) or picture(s) of a kind switched off taken out`);
  const { words } = await chapterWords(run, n, c);
  const only = new Set(targets);
  const redone = beatsInScope(beats, only);
  const fresh = await choreographBeats(run, n, c, beats, words, only, had.patch.filter((p) => !redone.has(p.beat)));
  // The other beats' steps, those that still fit (a step whose `until` is now in a redone beat is checked again).
  const kept = patchStillFits(had.patch.filter((p) => !redone.has(p.beat)), beats, words).patch;
  const notes = applyBeats(run, n, c, beats, [...kept, ...fresh], [...(had.notes ?? []).slice(0, 20), ...read.notes]);
  if (notes.length) check(call, "Applied", "fixed", `${notes.length} step(s) left out: ${notes.slice(0, 6).join("; ")}`);
  saveRun(run);
}

/** The stand-in director's beats (no key): the stand-in's beats, a new paragraph at a main picture after two beats. */
function fakeBeats(run: Run, n: number, beats: SceneBeatInput[], kinds: string[]) {
  const base = fakeScenes(run, n, beats, kinds);
  let since = 0;
  return { region: base.region, beats: base.beats.map((b, i) => {
    const ops = (b.do as Record<string, unknown>[]).filter((o) => !["reveal", "focus", "zoom", "emphasis", "clear"].includes(String(o.op)));
    const starts = i === 0 || (ops.some((o) => MAIN.has(String(o.op))) && since >= 2) || since >= 4;
    since = starts ? 1 : since + 1;
    return { beat: b.beat, do: ops, ...(starts ? { paragraph: true } : {}) };
  }) };
}

/** The stand-in choreographer's patch (no key): each operation on the first word of its line that is in its words,
 * else as the line begins; each part on the first word that names it; a labelled picture's part lit as it is named. */
function fakePatch(beats: ContentBeat[], words: Map<number, BeatWords>) {
  const plainWord = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
  const find = (beat: number, text: string) => (words.get(beat)?.words ?? []).findIndex((w) => plainWord(w.w).length > 3 && text.toLowerCase().includes(plainWord(w.w)));
  return { beats: beats.map((b) => {
    const steps: PatchStep[] = [];
    b.do.forEach((op, i) => {
      const named = ["title", "text", "label", "term", "value", "name", "caption", "part"].map((k) => op[k]).filter((v) => typeof v === "string").join(" ");
      const at = Math.max(0, find(b.beat, named));
      // Now and then another way in, and a quick one (the shared choices exercised).
      steps.push({ at: `w${at}`, do: "enter", op: i, ...(b.beat % 3 === 1 ? { enter: "rise" } : b.beat % 3 === 2 ? { speed: "fast" } : {}) });
      for (const p of opParts(op)) {
        const hit = find(b.beat, p.name);
        if (hit < 0) continue;
        steps.push({ at: `w${Math.max(hit, at)}`, do: "show", op: i, part: p.name });
        if (op.op === "picture" && Array.isArray(op.labels)) steps.push({ at: `w${Math.max(hit, at) + 1}`, do: "light", part: p.name });
      }
    });
    return { beat: b.beat, steps };
  }) };
}

// ---------------------------------------------------------------- the voice first ---------------

/** The music bed's setting for the engine (engine/music.py): off when the Scenes tab turned it off. */
export function musicEnv(st: ScenesState): Record<string, string> {
  return { PANIM_MUSIC: st.music === false ? "off" : "on" };
}

/** Whether the chapters are spoken before their scenes are written (on either engine), unless switched off. */
export function voiceFirst(st: ScenesState): boolean {
  return st.voiceFirst !== false && process.env.V2_SCENES_VOICE_FIRST !== "0";
}

/**
 * Each beat of a chapter as its voice says it (the chapter spoken already, lib/video.ts narrate): how long its line
 * is, the quiet after it, and its words (as the line is written, split at spaces: w0 its first) with when each is
 * said, from the line's start. Undefined when the chapter is not spoken, or was spoken from other words.
 */
export async function voicedBeats(run: Run, n: number, c: number): Promise<Map<number, BeatVoice> | undefined> {
  const { chapterLines, timingOf } = await import("./video");
  const timing = await timingOf(run.id, n, c);
  const chapter = scriptOf(run, n)?.chapters.find((x) => x.n === c);
  if (!timing || !chapter) return undefined;
  const lines = chapterLines(run, n, c);
  if (timing.lines.length !== lines.length || timing.lines.some((l, i) => l.text.trim() !== lines[i])) return undefined;
  const all = linesOf(run.lectures.find((l) => l.n === n)?.text ?? "");
  const spoken = (b: Beat) => b.lines.map((k) => (all[k - 1] ?? "").trim()).filter(Boolean);
  let k = Math.max(0, lines.length - chapter.beats.reduce((sum, b) => sum + spoken(b).length, 0));   // the card's line first
  const out = new Map<number, BeatVoice>();
  for (const b of chapter.beats) {
    const own = timing.lines.slice(k, k + spoken(b).length);
    k += spoken(b).length;
    if (!own.length) continue;
    const start = own[0].start;
    const end = own[own.length - 1].end;
    const next = timing.lines[k]?.start ?? timing.seconds;
    const said = own.flatMap((l) => l.words);
    const tokens = own.map((l) => l.text).join(" ").split(/\s+/).filter(Boolean);
    // The aligner's words are the line's own (pocket_lecture.line_words); counted otherwise, each word placed by its
    // share of the line.
    const words = tokens.map((w, i) => {
      const at = said.length === tokens.length ? said[i].start : said[Math.min(said.length - 1, Math.floor((i * said.length) / tokens.length))]?.start ?? start;
      return { w, t: Math.round(Math.max(0, at - start) * 10) / 10 };
    });
    out.set(b.n, { seconds: Math.round((end - start) * 10) / 10, pause: Math.round(Math.max(0, next - end) * 10) / 10, words });
  }
  return out;
}

/** The chapter spoken and aligned before its scenes are written (once: again only when its words changed). */
async function speakFirst(run: Run, n: number, c: number): Promise<void> {
  if (await voicedBeats(run, n, c)) return;
  const sl = lectureState(run, n);
  const was = sl.doing;
  sl.doing = `speaking chapter ${c} first`;
  saveRun(run);
  const { chapterVideo, narrate } = await import("./video");
  await narrate(run, n, c);
  sl.doing = was;
  const told = chapterVideo(run, n, c).narration;
  log(run, told?.status === "done" ? `Lecture ${n}, chapter ${c}: spoken first (${told.seconds ?? "?"} s), its scenes written to the voice.`
    : `Lecture ${n}, chapter ${c}: could not be spoken first (${told?.error ?? "no voice"}): its scenes are written without the voice's times.`);
}

/** A whole lecture (chapter by chapter), one chapter, or one beat; compiled; the refused beats mended once. */
async function buildLecture(run: Run, n: number, what: { chapter?: number; beat?: number }, note?: string) {
  const sl = lectureState(run, n);
  const script = scriptOf(run, n)!;
  const key = `${run.id}:scenes`;
  Object.assign(sl, { status: "running", error: undefined });
  if (what.beat) {
    const bc = chapterOfBeat(run, n, what.beat);
    if (voiceFirst(stateOf(run)) && bc !== undefined) await speakFirst(run, n, bc);
    sl.doing = `beat ${what.beat}`;
    saveRun(run);
    await writeBeats(run, n, { what: "beat", beat: what.beat }, undefined, note);
    const c = chapterOfBeat(run, n, what.beat);
    if (c !== undefined && !stopRequested(key)) await finishChapter(run, n, c);
  } else {
    // Each chapter by itself, several at once: written, its Manim figures, compiled, its refused beats mended.
    const chapters = what.chapter ? [what.chapter] : script.chapters.map((c) => c.n);
    const going = new Set<number>();
    let done = 0;
    const doing = () => {
      sl.doing = chapters.length > 1 ? `chapters ${[...going].sort((a, b) => a - b).join(", ")} (${done} of ${chapters.length} done)` : `chapter ${chapters[0]}`;
      saveRun(run);
    };
    await eachAtOnce(chapters, CHAPTERS_AT_ONCE, async (c) => {
      if (stopRequested(key)) return;
      going.add(c);
      doing();
      try {
        if (voiceFirst(stateOf(run))) await speakFirst(run, n, c);
        if (stopRequested(key)) return;
        if (directed(stateOf(run))) await directBeats(run, n, c, note);
        else await writeBeats(run, n, { what: "chapter", chapter: c }, undefined, note);
        if (!stopRequested(key)) await finishChapter(run, n, c);
      } finally {
        going.delete(c);
        done += 1;
        doing();
      }
    });
  }
  if (stopRequested(key)) return;
  Object.assign(sl, { status: "done", at: Date.now(), doing: undefined });
  saveRun(run);
}

/** A chapter's beats written: its Manim figures, compiled, and its refused beats mended once. */
async function finishChapter(run: Run, n: number, c: number) {
  const key = `${run.id}:scenes`;
  const sl = lectureState(run, n);
  await agentsOn(run, n, (b) => !b.ops.some((o) => o.op === "manim" && o.code), c);
  if (stopRequested(key)) return;
  await compileChapter(run, n, c);
  if (chapterBeats(run, n, c).some((k) => sl.beats[k]?.errors?.length) && !stopRequested(key)) await fixChapter(run, n, c);
}

/** `work` for each item, `atOnce` at a time. */
async function eachAtOnce<T>(items: T[], atOnce: number, work: (item: T) => Promise<void>): Promise<void> {
  const queue = [...items];
  const worker = async () => {
    for (let x = queue.shift(); x !== undefined; x = queue.shift()) await work(x);
  };
  await Promise.all(Array.from({ length: Math.min(atOnce, queue.length) }, worker));
}

/** The chapter a beat is in. */
function chapterOfBeat(run: Run, n: number, beat: number): number | undefined {
  return scriptOf(run, n)?.chapters.find((c) => c.beats.some((b) => b.n === beat))?.n;
}

/** A chapter's beats, by number. */
function chapterBeats(run: Run, n: number, c: number): number[] {
  return scriptOf(run, n)?.chapters.find((x) => x.n === c)?.beats.map((b) => b.n) ?? [];
}

/** A chapter's refused beats asked again with what the compiler said, then the chapter compiled again. */
async function fixChapter(run: Run, n: number, c: number) {
  const sl = lectureState(run, n);
  const agent = stateOf(run).manimAgent !== false;
  // A refused Manim figure goes back to the Manim agent (told what the compiler said); the rest to the scene writer.
  const isFigure = (b: SceneBeat) => agent && b.ops.some((o) => o.op === "manim");
  const mine = chapterBeats(run, n, c).map((k) => sl.beats[k]).filter((b): b is SceneBeat => !!b);
  const broken = mine.filter((b) => b.errors?.length && !isFigure(b));
  const figures = mine.filter((b) => b.errors?.length && isFigure(b));
  if (!broken.length && !figures.length) return;
  saveRun(run);
  // A chapter the director wrote as beats: its refused beats (what the compiler could not mend itself) asked of the
  // director again, told what the compiler said, never of the per-beat writer; a beat still refused shows nothing new.
  if (broken.length && isPlanOfBeats(sl.plans?.[c])) {
    try {
      await redirectBeats(run, n, c, broken.map((b) => b.n), { refused: Object.fromEntries(broken.map((b) => [b.n, b.errors!])),
        label: `mend ${broken.length} beat(s)` });
    } catch (e) {
      log(run, `Lecture ${n}, chapter ${c}: the director could not mend its refused beats (${(e as Error).message}).`);
    }
    await agentsOn(run, n, (b) => broken.some((x) => x.n === b.n) && !b.ops.some((o) => o.op === "manim" && o.code), c);
    await compileChapter(run, n, c);
    const still = chapterBeats(run, n, c).map((k) => sl.beats[k]).filter((b): b is SceneBeat => !!b?.errors?.length && !isFigure(b));
    const plan = sl.plans?.[c];
    if (still.length && isPlanOfBeats(plan)) {
      for (const b of still) {
        const own = plan.beats.find((x) => x.beat === b.n);
        if (own) own.do = [];
        Object.assign(b, { ops: [], errors: undefined });
      }
      plan.notes = [...(plan.notes ?? []), ...still.map((b) => `beat ${b.n}: still refused after the director's mend: it shows nothing new`)].slice(0, 60);
      log(run, `Lecture ${n}, chapter ${c}: beat(s) ${still.map((b) => b.n).join(", ")} still refused: their operations left out.`);
      await compileChapter(run, n, c);
    }
    broken.length = 0;
    if (!figures.length) return;
  }
  if (broken.length) await writeBeats(run, n, { what: "fix", beats: broken.map((b) => b.n) }, Object.fromEntries(broken.map((b) => [b.n, b.errors!])));
  for (const b of figures) {
    if (stopRequested(`${run.id}:scenes`)) break;
    await runManimAgent(run, n, b.n, { instruction: b.errors?.length ? `The compiler refused this beat's figure: ${b.errors.join("; ")}. Mend it.` : undefined,
      stop: () => stopRequested(`${run.id}:scenes`) });
  }
  await agentsOn(run, n, (b) => broken.some((x) => x.n === b.n) && !b.ops.some((o) => o.op === "manim" && o.code), c);
  await compileChapter(run, n, c);
}

/**
 * Every Manim figure of the lecture (or of one chapter) planned but still without its code, written before it is
 * compiled: the Manim agent asked again (twice at most), or, with the agent switched off, the scene writer asked to
 * write the beat again. Never left out: a figure the agent did not finish (an error, a timeout, a stop) stopped the
 * whole chapter from compiling ("a manim op needs its code").
 */
export async function writeMissingFigures(run: Run, n: number, chapter?: number) {
  const sl = lectureState(run, n);
  const script = scriptOf(run, n);
  if (!script) return;
  const beats = script.chapters.filter((c) => chapter === undefined || c.n === chapter).flatMap((c) => c.beats.map((b) => b.n));
  const unwritten = (k: number) => !!sl.beats[k]?.ops.some((o) => o.op === "manim" && !String(o.code ?? "").trim());
  for (const k of beats.filter(unwritten)) {
    for (let attempt = 1; attempt <= 2 && unwritten(k); attempt++) {
      if (stopRequested(`${run.id}:scenes`)) return;
      sl.doing = `writing beat ${k}'s Manim figure (it had no code)${attempt > 1 ? ", again" : ""}`;
      saveRun(run);
      if (stateOf(run).manimAgent !== false) {
        await runManimAgent(run, n, k, { instruction: "This beat's figure was planned but its code was never written: write it.",
          stop: () => stopRequested(`${run.id}:scenes`) });
      } else {
        await writeBeats(run, n, { what: "fix", beats: [k] }, { [k]: ["a manim op needs its code: the Python that draws this beat"] });
      }
    }
  }
}

/** The Manim agent on each beat whose manim op `needs` it (the scene writer planned it), in beat order. */
async function agentsOn(run: Run, n: number, needs: (b: SceneBeat) => boolean, chapter?: number) {
  if (stateOf(run).manimAgent === false) return;
  const sl = lectureState(run, n);
  const order = scriptOf(run, n)!.chapters.filter((c) => chapter === undefined || c.n === chapter).flatMap((c) => c.beats.map((b) => b.n));
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
  // Every chapter is on the board; with a region, the map comes in for the beats that point at it, in any chapter
  // (compile_lecture._map_runs). A chapter is never put on the map, or kept off it, as a whole.
  const own = only ? (sl.regions?.[only.chapter] ?? sl.region) : sl.region;
  const region = (script.chapters.some((c) => c.map) || usesMap(sl)) && own ? own : null;
  // A chapter built as one piece on the current engine is strict: everything that comes on, and when, is its
  // script's (compile_lecture: the chapter's "strict"; README "A chapter as one piece").
  const st0 = stateOf(run);
  const strict = (c: number) => directed(st0) && isPlanOfBeats(sl.plans?.[c]);
  let chapters = script.chapters.map((c) => ({
    n: c.n, title: c.title, narration: c.narration, ...(strict(c.n) ? { strict: true } : {}),
    beats: c.beats.map((b) => {
      const sb = sl.beats[b.n];
      return { n: b.n, say: b.lines.map((k) => lines[k - 1] ?? "").join(" ").trim() || "…", do: sb?.ops ?? [],
        ...(sb?.paragraph ? { paragraph: true } : {}), ...(sb?.pause ? { pause: sb.pause } : {}), ...(sb?.about ? { about: sb.about } : {}),
        ...(sb?.screen === "join" ? { screen: "join" } : {}) };
    }),
  }));
  if (only) {
    chapters = chapters.filter((c) => c.n === only.chapter).map((c) => ({ ...c, beats: only.upTo === undefined ? c.beats
      : c.beats.slice(0, c.beats.findIndex((b) => b.n === only.upTo) + 1) }));
  }
  const st = stateOf(run);
  return {
    // How it moves: its look, energy, transition, idle motion and timeline style (engine/MOTION_ENGINE.md).
    ...Object.fromEntries(Object.entries(st.motion ?? {}).filter(([, v]) => v)),
    title: lecture.title, sub: "", style: look.style, art: look.art, region, place_figures: false,
    ...(sl.emblem ? { emblem: sl.emblem } : {}), ...(sl.subject?.genre ? { genre: sl.subject.genre } : {}),
    figures: await figureFiles(run, n),
    chapters: chapters.map((c) => ({ title: c.title, narration: c.narration, ...(c.strict ? { strict: true } : {}),
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

export type Compiled = { source?: string; errors: string[]; warnings: string[]; minutes?: number; generated?: { prompt?: string; model?: string; usd?: number }[];
  /** The engine's image model's report (genimage.report): asked, made, cached, and each picture it could not get. */
  images?: { model?: string; asked?: number; made?: number; cached?: number; failed?: { what?: string; model?: string; error?: string }[];
    /** The decision model's answers on reusing a picture made before (picture_judge.py). */
    judged?: Judged[] };
  /** The call each decision asked now was recorded as, by what was asked. */
  judgedCalls?: Record<string, string>;
  /** Every picture the scene shows (compile_lecture.pictures_used): its file, what it shows, where. */
  pictures?: { file?: string; description?: string; role?: string; context?: { chapter?: number; beat?: number; caption?: string };
    parts?: [string, number?, number?, number?, number?][] }[] };

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
  // The engine's compiler: the lecture compiler with its motion layer (engine/MOTION_ENGINE.md).
  const out = await runPython([path.join(engineDir(), "compile_motion.py"), "-", "--json"], dir, engineEnv(run, n), JSON.stringify(script), COMPILE_TIMEOUT);
  try {
    const json = JSON.parse(out.stdout.slice(out.stdout.indexOf("{"))) as Compiled & { source?: string | null };
    const judgedCalls = n !== undefined ? recordJudged(run, n, json.images?.judged ?? []) : {};
    return { ...json, source: json.source ?? undefined, errors: json.errors ?? [], warnings: json.warnings ?? [], judgedCalls };
  } catch {
    return { errors: [`the engine's compile failed: ${errorOf(out.out).slice(-800)}`], warnings: [] };
  }
}

/** Every chapter of the lecture compiled, each by itself, several at once. */
async function compileLecture(run: Run, n: number) {
  await eachAtOnce(scriptOf(run, n)!.chapters.map((c) => c.n), CHAPTERS_AT_ONCE, (c) => compileChapter(run, n, c));
}

/** The lecture's compile: its chapters' compiles put together (running while any is, failed when any did). */
function mergedCompile(sl: SceneLecture): SceneCompile | undefined {
  const all = Object.values(sl.compiles ?? {});
  if (!all.length) return undefined;
  const sum = (f: (c: SceneCompile) => number | undefined) => all.reduce((k, c) => k + (f(c) ?? 0), 0);
  const missing = all.flatMap((c) => c.missing ?? []);
  const reports = all.map((c) => c.images).filter((r): r is ImageReport => !!r);
  const pictures = all.flatMap((c) => c.pictures ?? []);
  return {
    status: all.some((c) => c.status === "running") ? "running" : all.some((c) => c.status === "failed") ? "failed" : "done",
    errors: all.flatMap((c) => c.errors), warnings: all.flatMap((c) => c.warnings),
    ...(pictures.length ? { pictures } : {}), ...(missing.length ? { missing } : {}),
    ...(reports.length ? { images: { model: reports[0].model, asked: reports.reduce((k, r) => k + r.asked, 0), made: reports.reduce((k, r) => k + r.made, 0),
      cached: reports.reduce((k, r) => k + r.cached, 0), failed: reports.reduce((k, r) => k + r.failed, 0) } } : {}),
    minutes: Math.round(sum((c) => c.minutes) * 10) / 10 || undefined,
    // Compiled side by side: the lecture took as long as its slowest chapter.
    seconds: Math.max(...all.map((c) => c.seconds ?? 0)) || undefined,
    at: Math.max(...all.map((c) => c.at ?? 0)) || undefined,
  };
}

/** One chapter checked and compiled by the engine by itself; its messages put on the beats they name. */
async function compileChapter(run: Run, n: number, chapter: number) {
  const st = stateOf(run);
  const sl = lectureState(run, n);
  const sc = scriptOf(run, n)!.chapters.find((c) => c.n === chapter);
  if (!sc) return;
  await writeMissingFigures(run, n, chapter);
  const began = Date.now();
  const mine: SceneCompile = { status: "running", errors: [], warnings: [], at: began };
  (sl.compiles ??= {})[chapter] = mine;
  sl.compile = mergedCompile(sl);
  saveRun(run);
  const dir = path.join(scenesDir(run.id), `L${n}`, "compile", `chapter-${chapter}`);
  const c = await compile(run, await engineScript(run, n, st.look, { chapter }), dir, n);
  // The script compiled is this chapter alone: the engine's "chapter 1" is this one.
  const named = (text: string) => {
    const m = /chapter \d+ beat (\d+)/i.exec(text);
    return m ? sc.beats[Number(m[1]) - 1]?.n : undefined;
  };
  for (const b of sc.beats) {
    const sb = sl.beats[b.n];
    if (sb) Object.assign(sb, { errors: undefined, notes: undefined, missing: undefined, pictures: undefined });
  }
  const lost = missingPictures(c, named);
  for (const m of lost.missing) if (m.beat !== undefined) (beatState(sl, m.beat).missing ??= []).push(m);
  for (const p of await picturesByBeat(run, n, c, (_, bi) => sc.beats[bi - 1]?.n, lost.missing)) {
    if (p.beat !== undefined) (beatState(sl, p.beat).pictures ??= []).push(p);
  }
  const errors: string[] = [];
  const warnings: string[] = [];
  for (const e of c.errors) {
    const at = named(e);
    if (at !== undefined) (beatState(sl, at).errors ??= []).push(e.replace(/^chapter \d+ beat \d+:\s*/i, ""));
    else errors.push(`chapter ${chapter}: ${e}`);
  }
  for (const w of c.warnings) {
    const at = named(w);
    if (at !== undefined) (beatState(sl, at).notes ??= []).push(w.replace(/chapter \d+ beat \d+:\s*/i, ""));
    else warnings.push(`chapter ${chapter}: ${w}`);
  }
  const pictures = (c.generated ?? []).map((g) => ({ prompt: String(g.prompt ?? ""), model: g.model, usd: Number(g.usd) || 0 }));
  sl.compiles[chapter] = { status: c.errors.length ? "failed" : "done", errors, warnings, pictures, minutes: c.minutes, seconds: (Date.now() - began) / 1000,
    at: Date.now(), ...(lost.missing.length ? { missing: lost.missing } : {}), ...(lost.report ? { images: lost.report } : {}) };
  sl.compile = mergedCompile(sl);
  const cost = pictures.reduce((k, p) => k + (p.usd ?? 0), 0);
  if (pictures.length) {
    // The pictures the image model made while compiling, as a call, so the Costs tab counts them.
    const call = newCall(run, { step: "scenes", label: `Pictures for lecture ${n}, chapter ${chapter} (${pictures.length}, made while compiling)`, lecture: n,
      model: pictures[0].model ?? "image model", effort: "off",
      prompt: { system: [], user: pictures.map((p, i) => part(`p${i + 1}`, `Picture ${i + 1}`, "items", p.prompt)) } });
    Object.assign(call, { api: "image", status: "done", ended: Date.now(), cost, provider: usingFixture(call.model) ? "fixture" : "openrouter",
      attempts: [{ started: began, ended: Date.now() }], output: { pictures: pictures.length } });
    sl.calls.push(call.id);
  }
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
  const rows = existsSync(beatLog) ? (await readFile(beatLog, "utf8")).split("\n").filter(Boolean).map((l) => JSON.parse(l) as { kind: string; start: number; text?: string; words?: { w: string; start: number; end: number; est?: boolean }[] }) : [];
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
/** Each line of a render where it starts in the video and its words' times (the engine's beat log). */
function spokenLines(said: { start: number; text?: string; words?: { w: string; start: number; end: number; est?: boolean }[] }[]): SpokenLine[] | undefined {
  const out = said.filter((r) => r.words?.length).map((r) => ({ start: r.start, text: r.text ?? "", est: r.words!.some((w) => w.est) || undefined,
    words: r.words!.map((w) => ({ w: w.w, start: w.start, end: w.end })) }));
  return out.length ? out : undefined;
}

async function renderPart(run: Run, n: number, chapter: number, beat: number | undefined, look: Look, target: SceneRender) {
  await writeMissingFigures(run, n, chapter);
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
    // With its voice when the chapter was spoken first (its lines and their word times are in the voice's cache, so
    // nothing is spoken again): heard as it plays, its animations on the words as they are said.
    let env: Record<string, string> = {};
    if (voiceFirst(stateOf(run)) && await voicedBeats(run, n, chapter)) {
      const { voiceEnv, voiceOf } = await import("./voice");
      env = { ...voiceEnv(voiceOf(run).settings), ...musicEnv(stateOf(run)) };
    }
    const p = await playable(run, n, dir, source, env);
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
      still: undefined, clip: undefined, video: undefined, seconds: (Date.now() - began) / 1000, at: Date.now(), error: undefined,
      audio: env.PANIM_TTS && p.narration && existsSync(p.narration) ? fileUrl(run.id, p.narration) : undefined,
      spoken: env.PANIM_TTS ? spokenLines(p.said) : undefined };
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
    } else if (on.has("templates") && /\b\d[\d,]*(?:\.\d+)?\b/.test(b.text)) {
      const number = b.text.match(/\b\d[\d,]*(?:\.\d+)?\b/)![0];
      ops.push({ op: "counter", value: number, label: (b.show || words.slice(0, 4).join(" ")).slice(0, 50) });
    } else if (on.has("templates") && b.n % 4 === 2 && words.length >= 3) {
      ops.push({ op: "list", id: `l${b.n}`, mark: "check", items: words.slice(0, 3).map((w) => ({ text: w })) });
    } else if (on.has("define") && b.n % 3 === 0 && words[0]) ops.push({ op: "define", term: words[0], meaning: b.text.slice(0, 60) });
    // No key point on the board: a define card of the line's own words instead.
    else if (words[0]) ops.push({ op: "define", term: words[0], meaning: (b.show || b.text).slice(0, 60) });
    return { beat: b.n, do: ops };
  });
  return { region: null, beats: out };
}

/** The kinds a beat may use. */
function allowedFor(run: Run, sl: SceneLecture, n: number): string[] {
  return kindsFor(run, sl, n);
}

/** The look as the scene writer is told it: the run's, and its motion look when one is set. */
function motionLookWords(st: ScenesState): string {
  const words = lookWords(st.look);
  return st.motion?.look ? `the ${st.motion.look} look (over ${words})` : words;
}

