/**
 * The voice step: a chapter whose scenes are built is spoken, its animations timed to the words, and played with its
 * narration in v1's web player. A chapter at a time (or every chapter of a lecture that has scenes), in order:
 *
 *   1. COMPILE the chapter as the scenes step renders it (the run's look, its figures and pictures).
 *   2. SPEAK every line it says with the chosen voice (engine/tools/prespeak.py, v2's copy of v1's): Gemini and
 *      ElevenLabs speak the whole chapter in one take (one tone and pace, each line running on into the next), cut
 *      back into its lines, each keeping the pause the voice left after it as its beat's hold; into one cache,
 *      .data/voice, shared by every run, so a line said again is not paid for again. For Gemini and ElevenLabs the
 *      voice director marks the lines for delivery first, as in v1.
 *   3. WORDS: when each word is said (engine/tools/voice_scene.py lines): from the voice (ElevenLabs), from the
 *      aligner here (Whisper through faster-whisper, local_align.py), or, when it cannot be had, an estimate.
 *   4. TIME the animations to the words: one call for the whole chapter (the timing role's model) with align_cues's own prompt, each beat's
 *      line, words with their times and the animations that go with it; the answer is checked (in order, inside the
 *      line) and written into the scene as cues= (voice_scene.py cues).
 *   5. RENDER the timed scene with the voice: the exporter places each line where its beat starts and mixes one
 *      narration track (tools/narration.py); the player plays it as its clock.
 *
 * Everything is saved in the run (run.voice); the files under .data/runs/<run>/scenes/L<n>/voice-<chapter>/.
 */

import { existsSync } from "node:fs";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { callTool, usingFixture } from "./llm";
import { engineDir } from "./maps";
import { errorOf, runPython } from "./manim";
import { modelFor } from "./models";
import { part } from "./prompts/parts";
import { handInstructions } from "./prompts/scenes";
import { check, newCall } from "./run";
import { compile, type Compiled, engineScript, musicEnv, writeMissingFigures, figureFiles, fileUrl, playable, renderSlot, scenesAction, scenesDir, scriptOf, stateOf as scenesOf, subjectOf, beatInputs } from "./scenes";
import { lectureFigures } from "./script-figures";
import { linesOf } from "./source/book";
import { DATA, loadRun, saveRun } from "./store";
import { cleanLook, lookWords } from "./styles";
import type { ChapterScript, ChapterVoice, Run, VoiceCue, VoiceLine, VoiceSettings, VoiceState } from "./types";
import { ENGINES, scenesKey } from "./voice-engines";
import { VISUAL_KINDS } from "./visual-kinds";

export { ENGINES, scenesKey };

const SPEAK_TIMEOUT = Math.max(60, Number(process.env.V2_VOICE_TIMEOUT_SECONDS) || 1800) * 1000;
/** Beats a timing call (align_cues.CHUNK): the whole chapter in one, so its animations are timed against its whole
 * voice (V2_TIMING_CHUNK for fewer a call). */
const CHUNK = Math.max(1, Number(process.env.V2_TIMING_CHUNK) || 400);

/** Which voices can speak here: each engine's key set (espeak needs none). */
export function voicesReady(): Record<VoiceSettings["engine"], boolean> {
  const has = (k: string) => !!process.env[k]?.trim();
  return { gemini: has("GEMINI_API_KEY") || has("GOOGLE_API_KEY"), chirp: has("GOOGLE_APPLICATION_CREDENTIALS") || has("GOOGLE_TTS_API_KEY"),
    eleven: has("ELEVENLABS_API_KEY"), espeak: true };
}

export function voiceOf(run: Run): VoiceState {
  const ready = voicesReady();
  return (run.voice ??= { settings: { engine: ready.gemini ? "gemini" : "espeak", pace: "teacher" }, lectures: {} });
}

/** Where every line spoken is kept (by voice and words): shared by the runs. */
export function voiceCache(): string {
  return process.env.V2_AUDIO_DIR || path.join(DATA, "voice");
}

export function voiceEnv(s: VoiceSettings): Record<string, string> {
  const director = s.engine === "gemini" || s.engine === "eleven";
  return { PANIM_TTS: s.engine, PANIM_VOICE: s.voice?.trim() ? `${s.engine}:${s.voice.trim()}` : "auto", PANIM_AUDIO_DIR: voiceCache(),
    PANIM_PACE: s.pace ?? "teacher", PANIM_ALIGN: "off",
    // The voice director is a chat model (OpenRouter): off with no key, as every other call is then a stand-in.
    ...(director && usingFixture(modelFor("scenes")) ? { PANIM_VOICE_DIRECTOR: "off" } : {}) };
}

const busy = ((globalThis as { __v2voiceBusy?: Set<string> }).__v2voiceBusy ??= new Set<string>());

export type VoiceAction =
  | { action: "settings"; engine?: VoiceSettings["engine"]; voice?: string; pace?: VoiceSettings["pace"]; timingModel?: string }
  | { action: "speak"; lecture: number; chapter?: number }
  | { action: "reset"; lecture: number; chapter?: number }
  | { action: "try"; lecture: number; chapter: number; script: unknown }
  | { action: "apply"; lecture: number; chapter: number; script: unknown }
  | { action: "resetTrial"; lecture: number; chapter: number };

/** A chapter's beat script as the compiler is given it (its figures aside), each beat with its number: to edit. */
export async function chapterScript(run: Run, n: number, chapter: number): Promise<ChapterScript> {
  const sc = scriptOf(run, n)?.chapters.find((c) => c.n === chapter);
  if (!sc) throw new Error(`lecture ${n} has no chapter ${chapter}`);
  const full = await engineScript(run, n, cleanLook(scenesOf(run).look), { chapter });
  const ch = (full.chapters as ChapterScript["chapter"][])[0];
  // On the motion engine (beta: the Scenes tab's setting), the chapter carries it and its settings, to be tried on it.
  const motion = full.engine === "motion" ? { engine: "motion" as const, ...Object.fromEntries((["look", "energy", "transition", "idle", "timeline"] as const)
    .filter((k) => typeof full[k] === "string").map((k) => [k, full[k] as string])) } : {};
  return { ...motion, style: full.style as string, art: full.art as string, region: (full.region as ChapterScript["region"]) ?? null,
    emblem: (full.emblem as string) ?? null, genre: (full.genre as string) ?? null,
    chapter: { title: ch.title, narration: ch.narration, map: ch.map, ...(ch.strict ? { strict: true } : {}),
      beats: ch.beats.map((b, i) => ({ beat: sc.beats[i]?.n, ...b })) } };
}

/** The scene writer's instructions, to give any chat model with this chapter's beat script (the editor's copy). */
export async function editInstructions(run: Run, n: number): Promise<string> {
  const st = scenesOf(run);
  const motion = st.engine === "motion" ? { look: st.motion?.look, timeline: st.motion?.timeline } : undefined;
  return handInstructions({ look: lookWords(st.look), kinds: st.kinds, subject: await subjectOf(run, n), pace: { maxOps: st.maxOps, change: st.visualChange }, motion,
    labels: Object.fromEntries(VISUAL_KINDS.map((k) => [k.id, k.label])) });
}

/**
 * What the scene writer is told with the instructions, for one chapter, as text to give a chat model by hand: the
 * lecture and its chapters, the map region chosen, the lecture's figures (by id, to show with {"op":"picture","figure"}),
 * and each beat of the chapter as the script planned it (what is on screen, its figures, the kinds it may use).
 */
export function editContext(run: Run, n: number, chapter: number): string {
  const script = scriptOf(run, n);
  if (!script) throw new Error(`lecture ${n} has no script`);
  const st = scenesOf(run);
  const sl = run.scenes?.lectures[n];
  const labels = Object.fromEntries(VISUAL_KINDS.map((k) => [k.id, k.label]));
  const figures = lectureFigures(run, n);
  const beats = beatInputs(run, n).filter((b) => b.chapter === chapter);
  return [
    `THE LECTURE: lecture ${n}, "${run.lectures.find((l) => l.n === n)?.title ?? ""}". Its chapters:`,
    ...script.chapters.map((c) => `  Chapter ${c.n}: ${c.title} (${c.map ? "on the board, the map in for its beats on places" : "on the board"})${c.n === chapter ? "  <- the chapter to write" : ""}`),
    `This chapter's map region (chosen already): ${(sl?.regions?.[chapter] ?? sl?.region) ? JSON.stringify(sl?.regions?.[chapter] ?? sl?.region) : "none"}.`,
    "",
    `THE LECTURE'S FIGURES (${figures.length}), the book's own, shown by id: {"op":"picture","figure":"<id>"}:`,
    ...(figures.length ? figures.map((f) => `  ${f.id}: ${f.caption || "(no caption)"} (${f.way}${f.ready ? "" : "; not made yet: the book's picture is shown"})`) : ["  none"]),
    "",
    "THIS CHAPTER'S BEATS AS THE SCRIPT PLANNED THEM (its writer's note of what is on screen; a figure named on a beat is shown on it):",
    ...beats.map((b) => [`  #${b.n} "${b.text}"`, `     on screen: ${b.show || "-"}`,
      ...(b.figures ?? []).map((f) => `     figure: ${f.id} - ${f.caption || "(no caption)"}`),
      ...(b.kinds && b.kinds.length !== st.kinds.length ? [`     this beat may use only: ${b.kinds.map((k) => labels[k] ?? k).join(", ") || "the heading and key point"}`] : []),
    ].join("\n")),
  ].join("\n");
}

/** An edited beat script read as one: what is wrong with it said plainly, so the page can show it. */
export function readChapterScript(x: unknown): ChapterScript {
  const fail = (why: string): never => { throw new Error(`the beat script: ${why}`); };
  if (!x || typeof x !== "object" || Array.isArray(x)) fail("it must be a JSON object");
  const o = x as Record<string, unknown>;
  const ch = o.chapter as Record<string, unknown> | undefined;
  if (!ch || typeof ch !== "object" || Array.isArray(ch)) fail('it needs "chapter": {"title", "narration", "map", "beats": [...]}');
  if (typeof ch!.title !== "string" || !ch!.title.trim()) fail('"chapter.title" must be a text');
  if (!Array.isArray(ch!.beats) || !(ch!.beats as unknown[]).length) fail('"chapter.beats" must be a list of at least one beat');
  const beats = (ch!.beats as unknown[]).map((raw, i) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) fail(`beat ${i + 1} must be an object`);
    const b = raw as Record<string, unknown>;
    if (typeof b.say !== "string" || !b.say.trim()) fail(`beat ${i + 1}: "say" must be the words said`);
    const ops = b.do ?? [];
    if (!Array.isArray(ops) || ops.some((op) => !op || typeof op !== "object" || Array.isArray(op) || typeof (op as Record<string, unknown>).op !== "string"))
      fail(`beat ${i + 1}: "do" must be a list of operations, each with "op"`);
    if (b.pause !== undefined && !(Number(b.pause) >= 0)) fail(`beat ${i + 1}: "pause" must be a number of seconds`);
    if (b.beat !== undefined && !Number.isInteger(b.beat)) fail(`beat ${i + 1}: "beat" must be the beat's number`);
    return { ...(b.beat !== undefined ? { beat: b.beat as number } : {}), say: (b.say as string).trim(), do: ops as Record<string, unknown>[],
      ...(b.paragraph === true ? { paragraph: true } : {}), ...(b.pause ? { pause: Number(b.pause) } : {}),
      ...(typeof b.about === "string" && b.about.trim() ? { about: b.about.trim() } : {}) };
  });
  const text = (k: string) => (typeof o[k] === "string" && (o[k] as string).trim() ? (o[k] as string).trim() : undefined);
  if (o.region !== undefined && o.region !== null && (typeof o.region !== "object" || Array.isArray(o.region))) fail('"region" must be an object or null');
  if (o.engine !== undefined && o.engine !== "motion") fail('"engine" is "motion" (the motion engine, beta) or left out');
  // The motion engine's own settings (engine/MOTION_ENGINE.md); its compiler checks their values.
  const motion = o.engine === "motion" ? { engine: "motion" as const, ...Object.fromEntries((["look", "energy", "transition", "idle", "timeline"] as const)
    .filter((k) => text(k)).map((k) => [k, text(k)])) } : {};
  return { ...motion, style: text("style"), art: text("art"), region: (o.region as ChapterScript["region"]) ?? null, emblem: text("emblem") ?? null,
    genre: text("genre") ?? null,
    chapter: { title: (ch!.title as string).trim(), narration: typeof ch!.narration === "string" ? ch!.narration : "",
      // On the board, the map in for its beats that point at it; "map": false keeps the map out of the chapter.
      ...(ch!.map === false ? { map: false } : {}), ...(ch!.strict === true ? { strict: true } : {}), beats } };
}

/** The engine's script for an edited chapter: the lecture's title and its figures, the chapter as edited. */
export async function engineScriptOf(run: Run, n: number, s: ChapterScript): Promise<Record<string, unknown>> {
  const look = cleanLook({ ...scenesOf(run).look, ...(s.style ? { style: s.style } : {}), ...(s.art ? { art: s.art } : {}) });
  const region = s.region && Object.keys(s.region).length ? s.region : null;
  const motion = s.engine === "motion" ? { engine: "motion", ...Object.fromEntries((["look", "energy", "transition", "idle", "timeline"] as const)
    .filter((k) => s[k]).map((k) => [k, s[k]])) } : {};
  return { ...motion, title: run.lectures.find((l) => l.n === n)?.title ?? "", sub: "", style: look.style, art: look.art, region, place_figures: false,
    ...(s.emblem ? { emblem: s.emblem } : {}), ...(s.genre ? { genre: s.genre } : {}), figures: await figureFiles(run, n),
    chapters: [{ title: s.chapter.title, narration: s.chapter.narration ?? "", ...(s.chapter.map === false ? { map: false } : {}),
      ...(s.chapter.strict ? { strict: true } : {}),
      beats: s.chapter.beats.map(({ beat: _, ...b }) => b) }] };
}

/** The chapters of a lecture whose scenes are built (every beat written, some with visuals), in order. */
export function chaptersWithScenes(run: Run, n: number): number[] {
  const script = scriptOf(run, n);
  const sl = run.scenes?.lectures[n];
  if (!script || !sl) return [];
  // A beat is built when it was written (a beat of a scene built as one piece may add nothing: what is up stays).
  return script.chapters.filter((c) => c.beats.length && c.beats.every((b) => sl.beats[b.n]?.status === "done" || sl.beats[b.n]?.ops?.length)
    && c.beats.some((b) => sl.beats[b.n]?.ops?.length)).map((c) => c.n);
}

export async function voiceAction(id: string, a: VoiceAction): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (run.legacy) throw new Error(run.legacy);
  const vs = voiceOf(run);
  if (a.action === "settings") {
    if (a.engine) vs.settings.engine = a.engine;
    if (a.voice !== undefined) vs.settings.voice = a.voice.trim() || undefined;
    if (a.pace) vs.settings.pace = a.pace;
    if (a.timingModel !== undefined) vs.settings.timingModel = a.timingModel.trim() || undefined;
    saveRun(run, true);
    return run;
  }
  if (a.action === "reset") {
    const lv = vs.lectures[a.lecture] ?? {};
    for (const c of a.chapter !== undefined ? [a.chapter] : Object.keys(lv).map(Number)) {
      if (busy.has(`${id}|${a.lecture}|${c}`)) throw new Error(`chapter ${c} is being spoken`);
      delete lv[c];
      await rm(path.join(scenesDir(id), `L${a.lecture}`, `voice-${c}`), { recursive: true, force: true });
    }
    saveRun(run, true);
    return run;
  }
  if (a.action === "try") {
    const edited = readChapterScript(a.script);
    if (!scriptOf(run, a.lecture)?.chapters.some((c) => c.n === a.chapter)) throw new Error(`lecture ${a.lecture} has no chapter ${a.chapter}`);
    const key = `${id}|${a.lecture}|${a.chapter}|try`;
    if (busy.has(key)) throw new Error("this chapter's edit is being tried already");
    const trials = ((vs.trials ??= {})[a.lecture] ??= {});
    const target: ChapterVoice = trials[a.chapter] = { status: "running", phase: "waiting", edited, started: Date.now() };
    busy.add(key);
    saveRun(run, true);
    void (async () => {
      try {
        await speakChapter(run, a.lecture, a.chapter, target, edited);
      } catch (error) {
        Object.assign(target, { status: "failed", phase: undefined, error: (error as Error).message, at: Date.now() });
      } finally {
        busy.delete(key);
        saveRun(run, true);
      }
    })();
    return run;
  }
  if (a.action === "apply") {
    // The edited visuals put into the scenes (the Scenes tab's beats), and compiled: each beat named by its number in
    // this chapter. The words said are the transcript's: an edited say is tried, never applied.
    const edited = readChapterScript(a.script);
    if (edited.engine === "motion" && scenesOf(run).engine !== "motion") throw new Error("a motion-engine script (beta) is tried, not applied: the lecture's scenes are the current engine's (switch the Scenes tab's engine to motion to apply it)");
    const chapter = scriptOf(run, a.lecture)?.chapters.find((c) => c.n === a.chapter);
    if (!chapter) throw new Error(`lecture ${a.lecture} has no chapter ${a.chapter}`);
    const notes: string[] = [];
    const known = new Set(chapter.beats.map((b) => b.n));
    const beats = edited.chapter.beats.filter((b) => {
      if (b.beat !== undefined && known.has(b.beat)) return true;
      notes.push(`"${b.say.slice(0, 50)}…": ${b.beat === undefined ? "no beat number" : `beat ${b.beat} is not in this chapter`}, so not applied`);
      return false;
    });
    if (!beats.length) throw new Error("no beat of this chapter in it (each beat needs its \"beat\" number) : nothing to apply");
    const fresh = await chapterScript(run, a.lecture, a.chapter);
    for (const b of beats) {
      const was = fresh.chapter.beats.find((x) => x.beat === b.beat);
      if (was && was.say !== b.say) notes.push(`beat ${b.beat}: its words are the transcript's, so the edited say was not applied`);
    }
    if (edited.style && edited.style !== fresh.style || edited.art && edited.art !== fresh.art) notes.push("the look is the run's (Scenes tab), so the edited style and art were not applied");
    await scenesAction(id, { action: "editChapter", lecture: a.lecture, chapter: a.chapter,
      beats: beats.map((b) => ({ beat: b.beat!, ops: b.do, paragraph: b.paragraph, pause: b.pause, about: b.about })),
      emblem: edited.emblem ?? null, region: edited.region ?? null });
    const after = await loadRun(id);
    if (!after) return run;
    const trials = ((voiceOf(after).trials ??= {})[a.lecture] ??= {});
    trials[a.chapter] = { ...(trials[a.chapter] ?? { status: "done" }), applied: { at: Date.now(), beats: beats.length, notes } };
    saveRun(after, true);
    return after;
  }
  if (a.action === "resetTrial") {
    if (busy.has(`${id}|${a.lecture}|${a.chapter}|try`)) throw new Error("this chapter's edit is being tried");
    delete vs.trials?.[a.lecture]?.[a.chapter];
    await rm(path.join(scenesDir(id), `L${a.lecture}`, `voice-${a.chapter}-try`), { recursive: true, force: true });
    saveRun(run, true);
    return run;
  }
  // Speak: one chapter, or every chapter with scenes not spoken yet (or behind its scenes), one after another.
  const ready = chaptersWithScenes(run, a.lecture);
  if (!ready.length) throw new Error(`lecture ${a.lecture} has no chapter with its scenes built yet: build them on the Scenes tab first`);
  const lv = (vs.lectures[a.lecture] ??= {});
  let todo: number[];
  if (a.chapter !== undefined) {
    if (!ready.includes(a.chapter)) throw new Error(`chapter ${a.chapter} has beats without visuals: build its scenes first`);
    todo = [a.chapter];
  } else {
    todo = ready.filter((c) => lv[c]?.status !== "done" || lv[c]?.scenesKey !== scenesKey(run, a.lecture, c));
    if (!todo.length) throw new Error(`every chapter of lecture ${a.lecture} with scenes is spoken already (speak one again from its row)`);
  }
  todo = todo.filter((c) => !busy.has(`${id}|${a.lecture}|${c}`));
  if (!todo.length) throw new Error("that is being spoken already");
  for (const c of todo) {
    busy.add(`${id}|${a.lecture}|${c}`);
    lv[c] = { status: "running", phase: "waiting", started: Date.now() };
  }
  saveRun(run, true);
  void (async () => {
    for (const c of todo) {
      const target = lv[c];
      try {
        await speakChapter(run, a.lecture, c, target);
      } catch (error) {
        Object.assign(target, { status: "failed", phase: undefined, error: (error as Error).message, at: Date.now() });
      } finally {
        busy.delete(`${id}|${a.lecture}|${c}`);
        saveRun(run, true);
      }
    }
  })();
  return run;
}

export function speaking(runId: string): string[] {
  return [...busy].filter((k) => k.startsWith(`${runId}|`));
}

type Tool = { stdout: string; out: string };
function lastJson<T>(r: Tool, what: string): T {
  const line = r.stdout.trim().split("\n").pop() ?? "";
  try {
    return JSON.parse(line) as T;
  } catch {
    throw new Error(`${what} failed: ${errorOf(r.out).slice(-600)}`);
  }
}

/** A Lab experiment (lib/lab.ts): where its files go and what its calls are named; spoken as a trial is. */
export type LabWhere = { dir: string; name: string };

/** The AI pictures a compile showed, copied beside the result so the page can show them as the image model made
 * them, with the prompt it was sent (the engine keeps it beside each picture). */
async function madePictures(run: Run, compiled: Compiled, dir: string): Promise<ChapterVoice["pictures"]> {
  const out: NonNullable<ChapterVoice["pictures"]> = [];
  const into = path.join(dir, "pictures");
  for (const p of compiled.pictures ?? []) {
    if (!p.file || !/\/gen-[^/]*\.png$/.test(p.file) || !existsSync(p.file) || out.some((o) => o.url.endsWith(path.basename(p.file!)))) continue;
    let side: { prompt?: string; model?: string } = {};
    try {
      side = JSON.parse(await readFile(p.file.replace(/\.png$/, ".json"), "utf8"));
    } catch {}
    await mkdir(into, { recursive: true });
    const copy = path.join(into, path.basename(p.file));
    await copyFile(p.file, copy);
    out.push({ url: fileUrl(run.id, copy), what: String(p.description ?? ""), role: p.role, beat: p.context?.beat, prompt: side.prompt,
      model: side.model, ...(p.parts?.length ? { parts: p.parts } : {}) });
  }
  return out;
}

export async function speakChapter(run: Run, n: number, chapter: number, target: ChapterVoice, edited?: ChapterScript, lab?: LabWhere) {
  const began = Date.now();
  const settings = { ...voiceOf(run).settings };
  const env = { ...voiceEnv(settings), ...musicEnv(scenesOf(run)) };
  const look = cleanLook({ ...scenesOf(run).look, ...(edited?.style ? { style: edited.style } : {}), ...(edited?.art ? { art: edited.art } : {}) });
  const dir = lab?.dir ?? path.join(scenesDir(run.id), `L${n}`, edited ? `voice-${chapter}-try` : `voice-${chapter}`);
  const what = lab ? `the Lab's "${lab.name}"` : `lecture ${n}, chapter ${chapter}`;
  const tools = path.join(engineDir(), "tools");
  const phase = (p: string) => {
    target.phase = p;
    saveRun(run);
  };
  Object.assign(target, { status: "running", engine: settings.engine, style: look.style, art: look.art, error: undefined,
    ...(edited ? {} : { scenesKey: scenesKey(run, n, chapter) }), started: began });
  // Each line to its beat: by the edited script's words (a trial), else by the transcript's.
  const beatOf = edited ? editedBeats(edited) : beatsByText(run, n, chapter);
  // A Manim figure planned but never written is written now (the agent asked again), not left to stop the compile.
  if (!edited) {
    phase("writing the chapter's unwritten Manim figures");
    await writeMissingFigures(run, n, chapter);
  }
  const release = await renderSlot();
  try {
    await rm(dir, { recursive: true, force: true });
    await mkdir(path.join(dir, "lines"), { recursive: true });
    await mkdir(voiceCache(), { recursive: true });

    phase("compiling the chapter");
    const script = edited ? await engineScriptOf(run, n, edited) : await engineScript(run, n, look, { chapter });
    // A strict chapter's animations are timed by its script alone: the timing model is not asked (step 4).
    const strict = (script.chapters as { strict?: boolean }[] | undefined)?.some((c) => c.strict) ?? false;
    const compiled = await compile(run, script, dir, n);
    if (!compiled.source) throw new Error(compiled.errors.length ? `it does not compile: ${compiled.errors.slice(0, 4).join("; ")}` : "the engine made no scene of it");
    target.pictures = await madePictures(run, compiled, dir);
    const source = compiled.source.split("\n").filter((l) => !/self\.(title_slide|outro_fade)\(/.test(l)).join("\n");
    const scene = path.join(dir, "scene.py");
    await writeFile(scene, source, "utf8");
    const pyEnv = { PYTHONPATH: engineDir(), ...env };

    phase(`speaking (${ENGINES.find((e) => e.id === settings.engine)?.label ?? settings.engine})`);
    type Spoken = { ok: boolean; error?: string; lines?: number; spoken?: number;
      voice?: { usd?: number; lecture_usd?: number; spoken?: number; lines?: number; engine?: string; director?: { lines?: number; usd?: number } } };
    const spoke = lastJson<Spoken>(await runPython([path.join(tools, "prespeak.py"), scene], dir, pyEnv, undefined, SPEAK_TIMEOUT), "speaking");
    if (!spoke.ok) throw new Error(spoke.error ?? "the voice did not speak");

    phase("timing the words");
    type Lines = { ok: boolean; error?: string; mode?: string; aligner?: string;
      lines?: { text: string; spoken: string; seconds: number | null; file: string | null; usd: number | null; delivery?: string | null;
        words?: VoiceLine["words"]; words_from?: string }[] };
    const said = lastJson<Lines>(await runPython([path.join(tools, "voice_scene.py"), "lines", scene], dir, pyEnv, undefined, SPEAK_TIMEOUT), "the word times");
    if (!said.ok) throw new Error(said.error ?? "the lines could not be read");
    const lines: VoiceLine[] = [];
    for (const [i, l] of (said.lines ?? []).entries()) {
      let url: string | undefined;
      if (l.file && existsSync(l.file)) {
        const copy = path.join(dir, "lines", `${String(i + 1).padStart(3, "0")}.wav`);
        await copyFile(l.file, copy);
        url = fileUrl(run.id, copy);
      }
      lines.push({ beat: beatOf(l.text), text: l.text, spoken: l.spoken !== l.text ? l.spoken : undefined, delivery: l.delivery ?? undefined,
        seconds: l.seconds ?? undefined, url, usd: l.usd, words: l.words ?? undefined, wordsFrom: l.words_from });
    }
    const voiceUsd = Number(spoke.voice?.usd ?? 0) - Number(spoke.voice?.director?.usd ?? 0);
    target.mode = said.mode;
    target.aligner = said.aligner;
    target.lines = lines;
    target.cost = { spoken: Math.max(0, voiceUsd), voice: Number(spoke.voice?.lecture_usd ?? 0), director: Number(spoke.voice?.director?.usd ?? 0),
      timing: 0, lines: spoke.lines ?? lines.length, newLines: spoke.spoken ?? 0 };
    target.calls = [];
    if ((spoke.spoken ?? 0) > 0) {
      // The lines spoken now (and the director's marking of them), as a call, so the Costs tab counts the voice.
      const call = newCall(run, { step: "voice", label: `Voice for ${what}${edited && !lab ? " (edited, tried)" : ""} (${spoke.spoken} line(s) spoken)`, lecture: n,
        model: said.mode ?? settings.engine, effort: "off",
        prompt: { system: [], user: lines.map((l, i) => part(`l${i + 1}`, `Line ${i + 1}`, "items", l.delivery ?? l.spoken ?? l.text)) } });
      Object.assign(call, { api: "voice", status: "done", ended: Date.now(), cost: Number(spoke.voice?.usd ?? 0),
        provider: settings.engine === "espeak" ? "fixture" : "openrouter", attempts: [{ started: began, ended: Date.now() }],
        output: { lines: spoke.spoken, director: spoke.voice?.director } });
      target.calls.push(call.id);
    }

    phase(strict ? "the animations on the script's own words" : "timing the animations to the words");
    const { cues, aligned } = strict ? { cues: [] as VoiceCue[], aligned: source }
      : await timeAnimations(run, n, what, scene, dir, pyEnv, settings, target, beatOf);
    target.cues = cues;

    phase("rendering with the voice");
    const p = await playable(run, n, dir, aligned, env);
    if (!p.narration || !existsSync(p.narration)) throw new Error("the render has no narration track: the voice was not heard in it");
    const list = edited ? edited.chapter.beats.map((b, i) => ({ n: b.beat ?? i + 1 })) : scriptOf(run, n)!.chapters.find((c) => c.n === chapter)!.beats;
    const offset = p.said.length > list.length ? p.said.length - list.length : 0;
    const last = Math.max(0, p.frames - 1);
    const beats = list.map((b, i) => {
      const start = p.said[offset + i]?.start ?? 0;
      const end = p.said[offset + i + 1]?.start ?? last / p.fps;
      return { n: b.n, start, end, from: Math.min(last, Math.round(start * p.fps)), to: Math.min(last, Math.max(0, Math.round(end * p.fps) - 1)) };
    });
    Object.assign(target, { status: "done", phase: undefined, ir: p.ir, assets: p.assets, fps: p.fps, frames: p.frames,
      audio: fileUrl(run.id, p.narration), beats, blockers: p.blockers.length ? p.blockers : undefined,
      seconds: (Date.now() - began) / 1000, at: Date.now() });
  } finally {
    release();
  }
}

/** A line of an edited chapter to its beat (by the edited words): its number, else its place in the list. */
function editedBeats(s: ChapterScript): (text: string) => number | undefined {
  const norm = (t: string) => t.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const said = s.chapter.beats.map((b, i) => ({ n: b.beat ?? i + 1, text: norm(b.say) }));
  // The chapter card's line (its narration, else its title) is no beat's, though a beat's words may start with it.
  const card = norm(s.chapter.narration || s.chapter.title);
  return (text) => {
    const t = norm(text);
    if (t === card && !said.some((b) => b.text === t)) return undefined;
    return t ? said.find((b) => b.text === t)?.n ?? said.find((b) => b.text.startsWith(t.slice(0, 40)) || t.startsWith(b.text.slice(0, 40)))?.n : undefined;
  };
}

/** A line of the chapter to its beat (by its words), so the page shows each line under its beat. */
function beatsByText(run: Run, n: number, chapter: number): (text: string) => number | undefined {
  const sc = scriptOf(run, n)?.chapters.find((c) => c.n === chapter);
  const all = linesOf(run.lectures.find((l) => l.n === n)?.text ?? "");
  const norm = (t: string) => t.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const said = (sc?.beats ?? []).map((b) => ({ n: b.n, text: norm(b.lines.map((k) => all[k - 1] ?? "").join(" ")) }));
  return (text) => {
    const t = norm(text);
    if (!t) return undefined;
    return said.find((b) => b.text === t)?.n ?? said.find((b) => b.text.startsWith(t.slice(0, 40)) || t.startsWith(b.text.slice(0, 40)))?.n;
  };
}

type Items = { ok: boolean; error?: string; system: string; beats: { id: number; kind: "beat" | "free"; text: string; parts: string[]; seconds: number | null;
  item?: string; words?: { w: string; start: number }[]; why?: string }[] };

const TIME_TOOL = {
  type: "function" as const,
  function: {
    name: "time_beats",
    description: "Give each beat's animations their start (and duration) in seconds from the beat's line start, so the picture follows the voice.",
    parameters: {
      type: "object",
      properties: {
        beats: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "integer" },
              cues: { type: "array", items: { type: "array", items: { type: "number" } }, description: "An ordinary beat: [start, duration] for each animation, in order." },
              starts: { type: "array", items: { type: "number" }, description: "A FREE block: the start of each of its plays, in order." },
            },
            required: ["id"],
            additionalProperties: false,
          },
        },
      },
      required: ["beats"],
      additionalProperties: false,
    },
  },
};

/**
 * The chapter's animations timed to its words: align_cues's prompt, one call for the whole chapter (a CHUNK of beats
 * a call), the answer checked and
 * written into the scene. The scene as it was when no beat has its words timed (it then plays each beat's
 * animations together as its line begins).
 */
async function timeAnimations(run: Run, n: number, what: string, scene: string, dir: string, env: Record<string, string>,
  settings: VoiceSettings, target: ChapterVoice, beatOf: (text: string) => number | undefined): Promise<{ cues: VoiceCue[]; aligned: string }> {
  const tools = path.join(engineDir(), "tools");
  const items = lastJson<Items>(await runPython([path.join(tools, "voice_scene.py"), "items", scene], dir, env, undefined, SPEAK_TIMEOUT), "reading the beats");
  if (!items.ok) throw new Error(items.error ?? "the beats could not be read");
  const cues: VoiceCue[] = items.beats.map((b) => ({ beat: beatOf(b.text), kind: b.kind, text: b.text, parts: b.parts, seconds: b.seconds ?? undefined,
    ...(b.why ? { why: b.why } : {}) }));
  const todo = items.beats.filter((b) => b.item);
  const source = await readFile(scene, "utf8");
  if (!todo.length) return { cues, aligned: source };
  const model = settings.timingModel || modelFor("timing");
  const answers: { id: number; cues?: unknown; starts?: unknown }[] = [];
  for (let i = 0; i < todo.length; i += CHUNK) {
    const chunk = todo.slice(i, i + CHUNK);
    const call = newCall(run, { step: "voice", label: `Time the animations to the words: ${what}` +
      (todo.length > CHUNK ? ` (beats ${i + 1}-${i + chunk.length})` : ""), lecture: n, model, effort: "low",
      prompt: { system: [part("timing", "How to time the animations (align_cues.py)", "rules", items.system)],
        user: [part("beats", "Each beat: its line, its words with their times, its animations", "items", chunk.map((b) => b.item!).join("\n\n")),
          part("ask", "Request", "ask", "Time every beat above (time_beats): the ids as given.")] } });
    target.calls!.push(call.id);
    const reply = await callTool({ call, tool: TIME_TOOL, onChange: () => saveRun(run), fake: () => ({ beats: chunk.map(fakeCues) }) });
    const got = Array.isArray(reply?.beats) ? (reply!.beats as typeof answers) : [];
    check(call, "Beats timed", got.length >= chunk.length ? "pass" : got.length ? "fixed" : "fail",
      `${got.length} of ${chunk.length} beat(s) given times${got.length < chunk.length ? "; the rest play their animations as their line begins" : ""}`);
    answers.push(...got);
    target.cost!.timing += call.cost;
  }
  const answer = path.join(dir, "cues.json");
  await writeFile(answer, JSON.stringify({ beats: answers }), "utf8");
  const out = path.join(dir, "aligned.py");
  type Written = { ok: boolean; error?: string; aligned: number; beats: { id: number; cues?: VoiceCue["cues"]; why?: string }[] };
  const written = lastJson<Written>(await runPython([path.join(tools, "voice_scene.py"), "cues", scene, answer, out], dir, env, undefined, SPEAK_TIMEOUT), "writing the times");
  if (!written.ok) throw new Error(written.error ?? "the times could not be written");
  for (const w of written.beats) {
    const c = cues[w.id];
    if (!c) continue;
    if (w.cues) Object.assign(c, { cues: w.cues, why: undefined });
    else c.why ??= w.why;
  }
  const call = run.calls.find((x) => x.id === target.calls![target.calls!.length - 1]);
  if (call) check(call, "Times fit", written.aligned === todo.length ? "pass" : "fixed",
    `${written.aligned} of ${todo.length} beat(s) timed: the times kept in order and inside each line`);
  return { cues, aligned: await readFile(out, "utf8") };
}

/** The stand-in's times (no key): each animation starts on the word that names it, else spread along the line. */
function fakeCues(b: Items["beats"][number]): { id: number; cues?: number[][]; starts?: number[] } {
  const words = b.words ?? [];
  const seconds = b.seconds ?? 1;
  const starts = b.parts.map((p, i) => {
    const named = words.find((w) => w.w.length > 4 && p.toLowerCase().includes(w.w.toLowerCase()));
    return Math.round(Math.max(0, Math.min(seconds - 0.3, named ? named.start - 0.2 : (i * seconds) / (b.parts.length + 1))) * 100) / 100;
  });
  for (let i = 1; i < starts.length; i++) starts[i] = Math.max(starts[i], starts[i - 1]);
  return b.kind === "free" ? { id: b.id, starts } : { id: b.id, cues: starts.map((s) => [s, 0.8]) };
}
