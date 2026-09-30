import { NextResponse } from "next/server";
import { toolchain } from "@/lib/pocketanim";
import { transcriptModel, usingFixture, videoModel } from "@/lib/model";
import { latexStatus, resources, versionInfo } from "@/lib/version";

export const runtime = "nodejs";

export async function GET() {
  const tools = await toolchain();
  const found = resources();
  return NextResponse.json({
    ...tools,
    // Read now, and where TinyTeX and MacTeX install as well as on PATH (the toolchain's own check looked at PATH
    // only, once, and said "no LaTeX" beside a status bar that found TinyTeX).
    latex: latexStatus().latex,
    // The narration voice (Gemini 3.8 Flash TTS) is set up.
    chirp: found.find((r) => r.id === "voice")?.ready ?? false,
    version: versionInfo(),
    resources: found,
    fixture: usingFixture(),
    model: usingFixture() ? "fixture" : videoModel(),
    transcriptModel: usingFixture() ? "fixture" : transcriptModel(),
  });
}
