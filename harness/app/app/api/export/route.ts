import { NextRequest, NextResponse } from "next/server";
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { REPO, exportScene, frameCount } from "@/lib/pocketanim";
import { exposeMapProject, sanitizeScene } from "@/lib/model";
import { saveVersion } from "@/lib/store";

export const runtime = "nodejs";
// An export runs Manim, which is slow the first time in a cold container.
export const maxDuration = 600;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const source = exposeMapProject(sanitizeScene(String(body?.source ?? "")));
    if (!source.trim()) {
      return NextResponse.json({ error: "no source to export" }, { status: 400 });
    }
    const sceneClass = String(body?.sceneClass ?? "GeneratedScene");

    const { result, buildDir } = await exportScene(source, sceneClass);
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
    // Kokoro voiceover so the player plays it against its own frames.
    let narrationUrl: string | null = null;
    if (result.narration?.file) {
      const voiceDir = path.join(REPO, "harness", "app", ".voice");
      await mkdir(voiceDir, { recursive: true });
      const name = `narration-${Date.now()}.wav`;
      await copyFile(path.join(buildDir, result.narration.file), path.join(voiceDir, name));
      narrationUrl = `/api/audio?file=${encodeURIComponent(name)}`;
    }

    return NextResponse.json({ ...result, buildDir, frames, stored, source, narrationUrl });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 500 },
    );
  }
}
