import { NextRequest, NextResponse } from "next/server";
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { REPO, exportScene, frameCount, prespeak, progressFile, type DrawCost, type VoiceCost } from "@/lib/pocketanim";
import { rm, writeFile } from "node:fs/promises";
import { exposeMapProject, sanitizeScene } from "@/lib/model";
import { saveVersion } from "@/lib/store";
import { voiceEngine, voiceName, voiceProblem } from "@/lib/version";

export const runtime = "nodejs";
// An export speaks the lecture and runs Manim: a long lecture takes a while.
export const maxDuration = 10800;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const source = exposeMapProject(sanitizeScene(String(body?.source ?? "")));
    if (!source.trim()) {
      return NextResponse.json({ error: "no source to export" }, { status: 400 });
    }
    const sceneClass = String(body?.sceneClass ?? "GeneratedScene");

    // A lecture is voiced by its narration voice (Gemini 3.8 Flash-Lite TTS) and nothing else: without it, say so first.
    const noVoice = /pocket_lecture/.test(source) ? voiceProblem() : null;
    if (noVoice) return NextResponse.json({ error: noVoice }, { status: 400 });
    // The lines are spoken first, several at once, with progress the page polls (/api/progress); Manim then finds
    // each line ready instead of waiting for them one by one.
    const progress = progressFile(String(body?.jobId ?? ""));
    let beats = 0;
    let voiceCost: VoiceCost | undefined;
    let drawCost: DrawCost | undefined;
    if (/pocket_lecture/.test(source)) {
      const spoken = await prespeak(source, progress);
      if (spoken.error) {
        if (progress) await rm(progress, { force: true });
        // Lines spoken before the refusal were paid for: the page still adds them to the bill.
        return NextResponse.json({ error: spoken.error, voiceCost: spoken.voice, drawCost: spoken.drawings }, { status: 500 });
      }
      beats = spoken.beats;
      voiceCost = spoken.voice;
      drawCost = spoken.drawings;
    }
    const { result, buildDir } = await exportScene(source, sceneClass, progress);
    if (progress) await rm(progress, { force: true });
    // The video render (/api/video) counts its progress against this.
    if (beats) await writeFile(path.join(buildDir, "beats.json"), JSON.stringify({ beats }));
    const frames =
      result.tier === 1 ? await frameCount(buildDir, result.scene) : (result.frames ?? 0);

    // Persisted only when a project is configured; the pipeline does not
    // depend on it, which is what lets the whole thing run with no database.
    const stored = await saveVersion({
      source,
      sceneClass,
      instruction: body?.instruction ? String(body.instruction) : null,
      model: body?.model ? String(body.model) : null,
      result,
    });

    // A scene that narrates itself (a lecture's beats call add_sound) comes
    // back with one mixed track beside the program. It is served like the
    // voiceover so the player plays it against its own frames.
    let narrationUrl: string | null = null;
    if (result.narration?.file) {
      const voiceDir = path.join(REPO, "harness", "app", ".voice");
      await mkdir(voiceDir, { recursive: true });
      const name = `narration-${Date.now()}.wav`;
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

    return NextResponse.json({ ...result, buildDir, frames, stored, source, narrationUrl, voiceWarning, voiceCost, drawCost });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 500 },
    );
  }
}
