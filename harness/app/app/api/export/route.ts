import { readVisualCheck } from "@/lib/visualcheck";
import { TimingLog } from "@/lib/timing";
import { NextRequest, NextResponse } from "next/server";
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { REPO, alignBeats, exportScene, frameCount, prespeak, progressFile, type VoiceCost } from "@/lib/pocketanim";
import { rm, writeFile } from "node:fs/promises";
import { exposeMapProject, sanitizeScene } from "@/lib/model";
import { voiceEngine, voiceName, voiceProblem } from "@/lib/version";
import { once, resultOf, validJobId } from "@/lib/jobs";
import { keepProgram } from "@/lib/media";
import { buildRepairs, failedFigures, repairBuiltManim } from "@/lib/manimcoder";
import { manimModel } from "@/lib/lecture";
import { openaiDirect } from "@/lib/providers";

export const runtime = "nodejs";
// An export speaks the lecture and runs Manim: a long lecture takes a while.
export const maxDuration = 10800;

type Reply = { status: number; body: Record<string, unknown> };

const reply = (body: Record<string, unknown>, init?: { status?: number }): Reply => ({ status: init?.status ?? 200, body });

/**
 * POST {source, sceneClass, jobId}: speak and build a scene. Run once per jobId (lib/jobs.ts once): a page reloaded
 * while it built asks again with the same id and gets the same build, still running or finished, instead of a
 * second one.
 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const jobId = String(body?.jobId ?? "");
  const work = () => build(body);
  const done = validJobId(jobId) ? await once(`export-${jobId}`, work) : await work();
  return NextResponse.json(done.body, { status: done.status });
}

/** GET ?job=<jobId>: a build's result once it has finished; {state: "running"} while it runs. */
export async function GET(request: NextRequest) {
  const jobId = request.nextUrl.searchParams.get("job") ?? "";
  if (!validJobId(jobId)) return NextResponse.json({ error: "no job" }, { status: 400 });
  const found = await resultOf(`export-${jobId}`);
  if (found.state === "done") {
    const done = found.result as Reply;
    return NextResponse.json(done.body, { status: done.status });
  }
  return NextResponse.json({ state: found.state }, { status: found.state === "running" ? 202 : 404 });
}

async function build(body: Record<string, unknown> | null): Promise<Reply> {
  try {
    let source = exposeMapProject(sanitizeScene(String(body?.source ?? "")));
    if (!source.trim()) {
      return reply({ error: "no source to export" }, { status: 400 });
    }
    const sceneClass = String(body?.sceneClass ?? "GeneratedScene");

    // A lecture is voiced by its narration voice (Gemini 3.8 Flash-Lite TTS) and nothing else: without it, say so first.
    const noVoice = /pocket_lecture/.test(source) ? voiceProblem() : null;
    if (noVoice) return reply({ error: noVoice }, { status: 400 });
    // The lines are spoken first, several at once, with progress the page polls (/api/progress); Manim then finds
    // each line ready instead of waiting for them one by one.
    const progress = progressFile(String(body?.jobId ?? ""));
    // How long the voice and the build took, for the page's cost breakdown (the build itself runs here, free).
    const started = Date.now();
    // Every timed step of this build (lib/timing.ts), in harness/app/.logs; its summary goes to the server's log.
    const log = new TimingLog(`build-${String(body?.jobId ?? sceneClass)}`);
    let voiceSeconds = 0;
    let beats = 0;
    let voiceCost: VoiceCost | undefined;
    if (/pocket_lecture/.test(source)) {
      const spoken = await prespeak(source, progress);
      if (spoken.error) {
        if (progress) await rm(progress, { force: true });
        // Lines spoken before the refusal were paid for: the page still adds them to the bill.
        return reply({ error: spoken.error, voiceCost: spoken.voice }, { status: 500 });
      }
      beats = spoken.beats;
      voiceCost = spoken.voice;
      voiceSeconds = (Date.now() - started) / 1000;
      logVoice(log, started, spoken.waitedAhead, spoken.voice);
      // The voice is made: the animations are timed to its words (as ElevenLabs timed them, or as a small local
      // model aligns them to any other voice's audio), filling the scene's timing slots before Manim draws it.
      if (voiceEngine() !== "silent") {
        const aligning = Date.now();
        if (progress) await writeFile(progress, JSON.stringify({ phase: "align", done: 0, total: beats })).catch(() => {});
        const aligned = await alignBeats(source);
        source = aligned.source;
        if (aligned.report && voiceCost) {
          voiceCost = { ...voiceCost, usd: voiceCost.usd + aligned.report.usd, align: aligned.report };
        }
        log.span("align", aligning, Date.now(), { what: "the animations timed to the spoken words",
          ...(aligned.report ?? { failed: true }) });
      }
    }
    const building = Date.now();
    let { result, buildDir } = await exportScene(source, sceneClass, progress);
    log.span("build", building, Date.now(), { what: "Manim draws the lecture and the phone program is baked", tier: result.tier });
    // Figures whose blocks failed while the video was drawn: mended by the Manim model after the build, and the
    // lecture built again with them (lib/manimcoder.ts repairBuiltManim).
    const repaired = await repairAfterBuild(source, sceneClass, progress, body, log, { result, buildDir });
    ({ result, buildDir } = repaired);
    const built = repaired.source;
    console.log(`[timing] build ${log.file}\n${log.summary().join("\n")}`);
    if (progress) await rm(progress, { force: true });
    // The video render (/api/video) counts its progress against this.
    if (beats) await writeFile(path.join(buildDir, "beats.json"), JSON.stringify({ beats }));
    const frames =
      result.tier === 1 ? await frameCount(buildDir, result.scene) : (result.frames ?? 0);
    const timing = { voiceSeconds: Math.round(voiceSeconds), buildSeconds: Math.round((Date.now() - building) / 1000) };

    // The program is kept by default (lib/media.ts keepProgram), linked to the generation that wrote its scene, so
    // builds can be compared; in the background, never holding the reply. The phone library is saved only when
    // the user presses Save (/api/save, lib/store.ts).
    const program = path.join(buildDir, "dsl", "generated", `${result.scene || sceneClass}.panim`);
    if (result.tier === 1) {
      void keepProgram(program, { source: built, sceneClass, tier: result.tier ?? undefined, frames,
        narrated: !!result.narration?.file, buildSeconds: timing.buildSeconds })
        .catch((error) => console.warn(`Keeping the program in Supabase failed: ${error instanceof Error ? error.message : error}`));
    }

    // A scene that narrates itself (a lecture's beats call add_sound) comes
    // back with one mixed track beside the program. It is served like the
    // voiceover so the player plays it against its own frames.
    let narrationUrl: string | null = null;
    if (result.narration?.file) {
      const voiceDir = path.join(REPO, "harness", "app", ".voice");
      await mkdir(voiceDir, { recursive: true });
      // Parts of a series are built at once: the name must not collide within a millisecond.
      const name = `narration-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.wav`;
      await copyFile(path.join(buildDir, result.narration.file), path.join(voiceDir, name));
      narrationUrl = `/api/audio?file=${encodeURIComponent(name)}`;
    }

    // A lecture with no narration means no voice could speak here: say so,
    // rather than hand back a video that is silent for no visible reason.
    let voiceWarning: string | null = null;
    // When the build failed, its error already says why (Google's own message for the voice): no warning over it.
    const engine = voiceEngine();
    if (!narrationUrl && !result.error && /pocket_lecture/.test(built) && (engine === "gemini" || engine === "chirp" || engine === "eleven")) {
      voiceWarning = `This lecture has no audio: ${voiceName()} did not speak its lines (check the key; the dev ` +
        "server log has Google's message).";
    }

    // What the visual check found at each beat, and what a model that reads images says of the frames it flagged.
    const checks = result.error ? null : await readVisualCheck(buildDir);

    if (result.synced) {
      console.log(`[sync] inside the beats: ${result.synced.on_words} pictures on their words, ${result.synced.pointed} ` +
        `things pointed at as named, ${result.synced.looked ?? 0} camera moves, over ${result.synced.beats} beats with word times; ` +
        `layout: ${result.synced.moved ?? 0} moved, ${result.synced.cleared ?? 0} cleared, ${result.synced.clashes ?? 0} overlaps left` +
        (result.synced.clashes ? " (PANIM_LAYOUT_LOG names them)" : ""));
    }
    return reply({ ...result, buildDir, frames, source: built, narrationUrl, voiceWarning, voiceCost, timing, checks,
      ...(repaired.tried.length ? { manimRepair: { tried: repaired.tried, fixed: repaired.fixed, usd: repaired.usd } } : {}) });
  } catch (error) {
    return reply(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 500 },
    );
  }
}

type Built = Awaited<ReturnType<typeof exportScene>>;

/**
 * The figures a build left out because their Manim failed in the real run, sent back to the Manim model with the
 * build's reasons and the lecture built again, up to PANIM_MANIM_BUILD_REPAIRS times. A rebuild is kept only when
 * it leaves out fewer pictures than the build before it; otherwise the earlier build stands.
 */
async function repairAfterBuild(source: string, sceneClass: string, progress: string | null,
  body: Record<string, unknown> | null, log: TimingLog, first: Built):
  Promise<Built & { source: string; tried: string[]; fixed: string[]; usd: number }> {
  let best = first;
  let current = source;
  const tried = new Set<string>();
  let usd = 0;
  const key = process.env.OPENROUTER_API_KEY;
  // The Manim model, or the model that wrote the lecture when the Manim was the writer's own.
  const fallback = String(body?.model ?? "");
  const model = manimModel() ?? (/^[\w.-]+\/[\w.:-]+$/.test(fallback) ? fallback : "");
  const style = /LECTURE_STYLE", "([^"]+)"/.exec(source)?.[1];
  const leftOut = (built: Built) => built.result.skipped?.length ?? 0;
  for (let round = 0; round < buildRepairs() && (key || openaiDirect(model)) && model; round++) {
    if (best.result.tier !== 1 || best.result.error) break;
    const failed = (best.result.skipped ?? []).filter((s) => /^manim block '/.test(s));
    if (!failed.length || !/pocket_lecture/.test(current)) break;
    const asked = Date.now();
    if (progress) {
      await writeFile(progress, JSON.stringify({ phase: "repair", done: 0, total: failedFigures(failed).size }))
        .catch(() => {});
    }
    const mended = await repairBuiltManim(current, failed, { key: key ?? "", model, style,
      onCost: (cost) => { usd += cost; },
      onStatus: (text) => console.warn(`[manim repair] ${text}`) });
    log.span("manim-repair", asked, Date.now(), { what: "the Manim model mends the figures the build left out",
      figures: failedFigures(failed).size, rewritten: mended.fixed.length });
    if (!mended.fixed.length) break;
    mended.fixed.forEach((id) => tried.add(id));
    const rebuilding = Date.now();
    const again = await exportScene(mended.source, sceneClass, progress);
    log.span("rebuild", rebuilding, Date.now(), { what: "the lecture built again with the mended figures",
      tier: again.result.tier, left_out: again.result.skipped?.length ?? 0 });
    const better = again.result.tier === 1 && !again.result.error && leftOut(again) < leftOut(best);
    await rm(better ? best.buildDir : again.buildDir, { recursive: true, force: true }).catch(() => {});
    if (!better) break;
    best = again;
    current = mended.source;
  }
  const still = new Set(failedFigures(best.result.skipped ?? []).keys());
  return { ...best, source: current, tried: [...tried], fixed: [...tried].filter((id) => !still.has(id)), usd };
}

/** The narration's steps in the build's timing log: the wait for speaking ahead, each batch, each request to the
 * voice (its tries, its refusals, the seconds spent waiting them out), and a line that sums the requests up. */
function logVoice(log: TimingLog, started: number, waitedAhead: number, voice?: VoiceCost) {
  if (waitedAhead > 0.5) {
    log.span("wait", started, started + waitedAhead * 1000, { what: "the build waited for speaking ahead to finish" });
  }
  const timing = voice?.timing;
  if (!timing) return;
  for (const b of timing.batches) log.span("tts-batch", b.start, b.end, { lines: b.lines, chars: b.chars, outcome: b.outcome });
  for (const c of timing.calls) {
    log.span("tts-request", c.start, c.end ?? c.start, { chars: c.chars, tries: c.tries, waited: c.waited,
      ...(c.codes.length ? { refused: c.codes } : {}), ok: !!c.ok });
  }
  const calls = timing.calls;
  const limited = calls.filter((c) => c.codes.includes(429)).length;
  const waited = calls.reduce((t, c) => t + c.waited, 0);
  const average = calls.length ? calls.reduce((t, c) => t + ((c.end ?? c.start) - c.start), 0) / calls.length / 1000 : 0;
  log.note("tts-summary", { engine: voice?.engine, requests: calls.length, threads: timing.threads,
    batch_lines: timing.batch_lines, rate_limited: limited, seconds_waiting_out_limits: Math.round(waited),
    average_request_seconds: Math.round(average * 10) / 10, batches: voice?.batches });
}
