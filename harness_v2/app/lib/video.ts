/**
 * The video step, v2's default flow once the transcript is written: a chapter at a time,
 *
 *   1. NARRATION: the chapter's lines, as the transcript has them, spoken with the chosen voice (the Voice settings:
 *      Gemini or ElevenLabs say the chapter whole, in one take) and every word aligned to the audio (the voice's own
 *      times, else Whisper here, else an estimate), laid on one track (engine/tools/chapter_voice.py). No scenes are
 *      needed: the voice comes first and the video is built to it.
 *   2. THE VIDEO AGENT (lib/video-agent.ts) builds the chapter's video in free Manim from the narration and its word
 *      times and a screenshot of the look wanted, working as a coding agent does: it writes and edits its scene,
 *      renders it, looks at frames, makes pictures, and plays it as the phone does, until it is right.
 *   3. THE PROGRAM: the scene exported as the phone plays it (faithful: every play as Manim draws it), with the
 *      narration mixed in, and its geometry for v1's web player; compared with the Manim video frame for frame.
 *
 * Everything is kept in the run (run.video) and under .data/runs/<run>/scenes/video/L<n>/C<c>/ (the agent's
 * workspace: lines.json, timing.json, chapter.wav, its scene, its pictures, renders and the export).
 */

import { existsSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { engineDir } from "./maps";
import { errorOf, runPython } from "./manim";
import { modelFor } from "./models";
import { fileUrl, scenesDir, scriptOf } from "./scenes";
import { linesOf } from "./source/book";
import { DATA, loadRun, saveRun } from "./store";
import type { ChapterVideo, Run, VideoSettings, VideoState } from "./types";
import { voiceEnv, voiceOf } from "./voice";

const SPEAK_TIMEOUT = Math.max(60, Number(process.env.V2_VOICE_TIMEOUT_SECONDS) || 1800) * 1000;
const TOOLS = () => path.join(engineDir(), "tools");

/** The look built in when none is chosen: a screenshot of a Vox-like chapter built in free Manim. */
export const DEFAULT_STYLE = () => path.join(engineDir(), "agent", "style-vox.jpg");

const busy = ((globalThis as { __v2videoBusy?: Map<string, { stop: boolean }> }).__v2videoBusy ??= new Map());

export function videoOf(run: Run): VideoState {
  return (run.video ??= { settings: {}, chapters: {} });
}

export const chapterKey = (n: number, c: number) => `${n}-${c}`;

export function chapterVideo(run: Run, n: number, c: number): ChapterVideo {
  const vs = videoOf(run);
  return (vs.chapters[chapterKey(n, c)] ??= { lecture: n, chapter: c });
}

/** The chapter's workspace: everything the voice and the agent make for it. */
export function workspaceOf(runId: string, n: number, c: number): string {
  return path.join(scenesDir(runId), "video", `L${n}`, `C${c}`);
}

/** The lines a chapter says, in order, as the transcript has them: its title card's line, then each beat's sentences. */
export function chapterLines(run: Run, n: number, c: number): string[] {
  const script = scriptOf(run, n);
  const chapter = script?.chapters.find((x) => x.n === c);
  if (!chapter) throw new Error(`lecture ${n} has no chapter ${c} in its script`);
  const all = linesOf(run.lectures.find((l) => l.n === n)?.text ?? "");
  const lines = chapter.beats.flatMap((b) => b.lines.map((k) => all[k - 1] ?? "")).map((x) => x.trim()).filter(Boolean);
  const card = chapter.narration?.trim();
  return card && !lines.includes(card) ? [card, ...lines] : lines;
}

/** The settings the agent runs with, filled from the run's options and the environment. */
export function settingsOf(run: Run): Required<Pick<VideoSettings, "model" | "imageModel" | "turns" | "style" | "effort">> & VideoSettings {
  const s = videoOf(run).settings;
  // Its own reasoning, not the run's (a run is often started with effort off, for the transcript's sake).
  const effort = s.effort || ((process.env.V2_VIDEO_AGENT_EFFORT || process.env.PANIM_MANIM_REASONING_EFFORT)?.trim().toLowerCase() as VideoSettings["effort"]) || "high";
  return { ...s, effort, model: s.model || run.options.videoModel || modelFor("video"), imageModel: s.imageModel || run.options.imageModel || modelFor("image"),
    turns: s.turns || Math.max(4, Number(process.env.V2_VIDEO_AGENT_TURNS) || 60), style: s.style && existsSync(s.style) ? s.style : DEFAULT_STYLE() };
}

/** 1. The chapter spoken from its lines and every word aligned: timing.json and chapter.wav in its workspace. */
export async function narrate(run: Run, n: number, c: number): Promise<void> {
  const cv = chapterVideo(run, n, c);
  const dir = workspaceOf(run.id, n, c);
  await mkdir(dir, { recursive: true });
  const lines = chapterLines(run, n, c);
  await writeFile(path.join(dir, "lines.json"), JSON.stringify({ lines }, null, 1), "utf8");
  const settings = voiceOf(run).settings;
  cv.narration = { status: "running", at: Date.now(), engine: settings.engine, lines: lines.length, progress: { phase: "voice", done: 0, total: lines.length } };
  saveRun(run, true);
  const progress = path.join(dir, "voice-progress.json");
  const timer = setInterval(async () => {
    try {
      const p = JSON.parse(await readFile(progress, "utf8")) as { phase: string; done: number; total: number };
      if (cv.narration?.status === "running") {
        cv.narration.progress = p;
        saveRun(run);
      }
    } catch { /* not yet */ }
  }, 1500);
  try {
    const out = await runPython([path.join(TOOLS(), "chapter_voice.py"), path.join(dir, "lines.json"), dir, progress], dir,
      voiceEnv(settings), undefined, SPEAK_TIMEOUT);
    const last = out.stdout.trim().split("\n").pop() ?? "";
    let result: { ok?: boolean; error?: string; seconds?: number; source?: string; track?: string; voice?: { usd?: number; spoken?: number; engine?: string } } = {};
    try {
      result = JSON.parse(last);
    } catch {
      throw new Error(`the voice failed: ${errorOf(out.out)}`);
    }
    if (!result.ok) throw new Error(result.error || "the voice failed");
    cv.narration = { status: "done", at: cv.narration.at, ended: Date.now(), engine: result.voice?.engine ?? settings.engine, seconds: result.seconds,
      source: result.source, lines: lines.length, spoken: result.voice?.spoken, cost: result.voice?.usd ?? 0,
      track: fileUrl(run.id, path.join(dir, result.track || "chapter.wav")) };
    // A new narration: what was built to the old one is out of time with it.
    if (cv.build) cv.build = { ...cv.build, blockers: [...cv.build.blockers.filter((b) => !b.startsWith("narration")), "narration spoken again since: build again"] };
  } catch (error) {
    cv.narration = { ...cv.narration, status: "failed", ended: Date.now(), error: (error as Error).message.slice(0, 1200) };
  } finally {
    clearInterval(timer);
    saveRun(run, true);
  }
}

/** The narration's timing as the agent and the page read it. */
export type Timing = { seconds: number; source?: string; lines: { n: number; text: string; start: number; end: number; words: { w: string; start: number; end: number; est?: boolean }[] }[] };

export async function timingOf(runId: string, n: number, c: number): Promise<Timing | null> {
  try {
    const t = JSON.parse(await readFile(path.join(workspaceOf(runId, n, c), "timing.json"), "utf8")) as Timing & { ok?: boolean };
    return t.ok === false ? null : t;
  } catch {
    return null;
  }
}

export type VideoAction =
  | { action: "settings"; model?: string; imageModel?: string; turns?: number; effort?: VideoSettings["effort"]; styleNote?: string; style?: string | null }
  | { action: "narrate"; lecture: number; chapter: number }
  | { action: "build"; lecture: number; chapter: number; note?: string }
  | { action: "all"; lecture: number; note?: string }
  | { action: "stop"; lecture: number; chapter?: number }
  | { action: "reset"; lecture: number; chapter: number };

/** A screenshot of the look wanted, sent as a data URL: kept for the run. */
async function saveStyle(runId: string, dataUrl: string): Promise<string> {
  const m = /^data:image\/(png|jpe?g|webp);base64,(.+)$/.exec(dataUrl);
  if (!m) throw new Error("the look must be a PNG, JPEG or WebP picture");
  const file = path.join(DATA, "runs", runId, "video-style." + (m[1] === "jpeg" ? "jpg" : m[1]));
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, Buffer.from(m[2], "base64"));
  return file;
}

/** One chapter: its narration (unless spoken already), then the agent. */
async function chapterThrough(run: Run, n: number, c: number, note: string | undefined, flag: { stop: boolean }) {
  const cv = chapterVideo(run, n, c);
  if (cv.narration?.status !== "done" || !(await timingOf(run.id, n, c))) await narrate(run, n, c);
  if (flag.stop || cv.narration?.status !== "done") return;
  const { runVideoAgent } = await import("./video-agent");
  await runVideoAgent(run, n, c, { note, stop: () => flag.stop });
}

export async function videoAction(id: string, a: VideoAction): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (run.legacy) throw new Error(run.legacy);
  const vs = videoOf(run);
  if (a.action === "settings") {
    if (a.model !== undefined) vs.settings.model = a.model.trim() || undefined;
    if (a.imageModel !== undefined) vs.settings.imageModel = a.imageModel.trim() || undefined;
    if (a.turns !== undefined) vs.settings.turns = Math.max(4, Math.min(300, Math.round(a.turns))) || undefined;
    if (a.styleNote !== undefined) vs.settings.styleNote = a.styleNote.trim() || undefined;
    if (a.effort) vs.settings.effort = a.effort;
    if (a.style === null) vs.settings.style = undefined;
    else if (a.style) vs.settings.style = await saveStyle(id, a.style);
    saveRun(run, true);
    return run;
  }
  if (a.action === "stop") {
    for (const [key, flag] of busy) if (key.startsWith(`${id}|${a.lecture}|`) && (a.chapter === undefined || key === `${id}|${a.lecture}|${a.chapter}`)) flag.stop = true;
    for (const [key, flag] of busy) if (key === `${id}|${a.lecture}|all`) flag.stop = true;
    return run;
  }
  if (a.action === "reset") {
    if (busy.has(`${id}|${a.lecture}|${a.chapter}`)) throw new Error(`chapter ${a.chapter} is being built`);
    delete vs.chapters[chapterKey(a.lecture, a.chapter)];
    await rm(workspaceOf(id, a.lecture, a.chapter), { recursive: true, force: true });
    saveRun(run, true);
    return run;
  }
  if (!scriptOf(run, a.lecture)) throw new Error(`lecture ${a.lecture} has no script yet: write the transcript first`);
  const chapters = a.action === "all" ? scriptOf(run, a.lecture)!.chapters.map((c) => c.n) : [a.chapter];
  const key = `${id}|${a.lecture}|${a.action === "all" ? "all" : a.chapter}`;
  for (const c of chapters) if (busy.has(`${id}|${a.lecture}|${c}`)) throw new Error(`chapter ${c} is being built`);
  if (busy.has(`${id}|${a.lecture}|all`)) throw new Error("this lecture's chapters are being built");
  const flag = { stop: false };
  busy.set(key, flag);
  void (async () => {
    try {
      for (const c of chapters) {
        if (flag.stop) break;
        const own = `${id}|${a.lecture}|${c}`;
        if (a.action === "all") busy.set(own, flag);
        try {
          if (a.action === "narrate") await narrate(run, a.lecture, c);
          else if (a.action === "all") {
            // Built already and in time with its narration: left as it is.
            const cv = chapterVideo(run, a.lecture, c);
            if (cv.build && !cv.build.blockers.length && cv.agent?.status === "done") continue;
            await chapterThrough(run, a.lecture, c, a.note, flag);
          } else await chapterThrough(run, a.lecture, c, a.note, flag);
        } finally {
          if (a.action === "all") busy.delete(own);
        }
      }
    } catch (error) {
      run.log.push({ t: Date.now(), text: `video: ${(error as Error).message.slice(0, 300)}` });
    } finally {
      busy.delete(key);
      saveRun(run, true);
    }
  })();
  return run;
}

/** Whether a chapter is being worked on now (the page shows Stop). */
export function videoBusy(id: string): string[] {
  return [...busy.keys()].filter((k) => k.startsWith(`${id}|`)).map((k) => k.slice(id.length + 1));
}

/**
 * A built chapter as a phone library (tools/build_library.py: the program, its clips, pictures, glyphs and its
 * narration as Opus), opened by the phone's own code first when the player is built (player/build.sh), and zipped
 * with `library/` at its top, as the phone's import and the APK's own library are laid out.
 */
export async function phoneLibrary(run: Run, n: number, c: number): Promise<{ zip: string; name: string }> {
  const cv = run.video?.chapters[chapterKey(n, c)];
  if (!cv?.build) throw new Error(`chapter ${c} is not built yet`);
  const ws = workspaceOf(run.id, n, c);
  const generated = path.join(ws, "export", "dsl", "generated");
  const out = path.join(ws, "library", "library");
  await rm(path.join(ws, "library"), { recursive: true, force: true });
  const repo = path.resolve(engineDir(), "..", "..");
  const packed = await runPython(["-m", "tools.build_library", "--source", generated, "--out", out], repo, {}, undefined, 600_000);
  if (packed.code !== 0) throw new Error(`the library could not be packed: ${errorOf(packed.out)}`);
  const classes = path.join(repo, "player", "build", "classes");
  if (existsSync(path.join(classes, "core"))) {
    const { spawnSync } = await import("node:child_process");
    const cp = ["core", "desktop", "kotlin-stdlib.jar"].map((p) => path.join(classes, p)).join(":");
    const checked = spawnSync("java", ["-cp", cp, "com.pocketanim.desktop.VerifyKt", out, "library"], { timeout: 180_000, encoding: "utf8" });
    if (!checked.error && checked.status !== 0) {
      const said = `${checked.stdout}\n${checked.stderr}`.split("\n").filter((l) => /FAIL|missing|expected|Exception/.test(l));
      throw new Error(`the phone player could not open it: ${said.slice(0, 4).join("; ") || `exit ${checked.status}`}`);
    }
  }
  const title = run.script?.lectures[n]?.chapters.find((x) => x.n === c)?.title ?? `chapter ${c}`;
  const slug = `L${n}-C${c}-${title.normalize("NFKD").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 50)}`;
  const zipped = await runPython(["-c", "import shutil, sys; print(shutil.make_archive(sys.argv[1], 'zip', sys.argv[2], 'library'))",
    path.join(ws, "library", slug), path.join(ws, "library")], ws);
  const zip = zipped.stdout.trim().split("\n").pop() ?? "";
  if (zipped.code !== 0 || !zip) throw new Error(`could not zip the library: ${errorOf(zipped.out)}`);
  return { zip, name: `${slug}.zip` };
}
