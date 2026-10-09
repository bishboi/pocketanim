import { NextRequest, NextResponse } from "next/server";
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { REPO, exportScene, frameCount, prespeak, progressFile, type VoiceCost } from "@/lib/pocketanim";
import { rm, writeFile } from "node:fs/promises";
import { exposeMapProject, sanitizeScene } from "@/lib/model";
import { voiceEngine, voiceName, voiceProblem } from "@/lib/version";
import { once, resultOf, validJobId } from "@/lib/jobs";

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
    const source = exposeMapProject(sanitizeScene(String(body?.source ?? "")));
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
    }
    const building = Date.now();
    const { result, buildDir } = await exportScene(source, sceneClass, progress);
    if (progress) await rm(progress, { force: true });
    // The video render (/api/video) counts its progress against this.
    if (beats) await writeFile(path.join(buildDir, "beats.json"), JSON.stringify({ beats }));
    const frames =
      result.tier === 1 ? await frameCount(buildDir, result.scene) : (result.frames ?? 0);
    const timing = { voiceSeconds: Math.round(voiceSeconds), buildSeconds: Math.round((Date.now() - building) / 1000) };

    // Nothing is stored here: a lecture is saved when the user presses Save (/api/save, lib/store.ts).

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
    if (!narrationUrl && !result.error && /pocket_lecture/.test(source) && (engine === "gemini" || engine === "chirp")) {
      voiceWarning = `This lecture has no audio: ${voiceName()} did not speak its lines (check the key; the dev ` +
        "server log has Google's message).";
    }

    return reply({ ...result, buildDir, frames, source, narrationUrl, voiceWarning, voiceCost, timing });
  } catch (error) {
    return reply(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 500 },
    );
  }
}
