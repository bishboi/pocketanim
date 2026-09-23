import { NextRequest, NextResponse } from "next/server";
import { exportScene, frameCount } from "@/lib/pocketanim";
import { saveVersion } from "@/lib/store";

export const runtime = "nodejs";
// An export runs Manim, which is slow the first time in a cold container.
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const source = String(body?.source ?? "");
    if (!source.trim()) {
      return NextResponse.json({ error: "no source to export" }, { status: 400 });
    }
    const sceneClass = String(body?.sceneClass ?? "GeneratedScene");

    const { result, buildDir } = await exportScene(source, sceneClass);
    const frames = result.tier === 1 ? await frameCount(buildDir, sceneClass) : 0;

    // Persisted only when a project is configured; the pipeline does not
    // depend on it, which is what lets the whole thing run with no database.
    const stored = await saveVersion({
      source,
      sceneClass,
      instruction: body?.instruction ? String(body.instruction) : null,
      model: body?.model ? String(body.model) : null,
      result,
    });

    return NextResponse.json({ ...result, buildDir, frames, stored });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 500 },
    );
  }
}
