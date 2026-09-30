import { NextResponse } from "next/server";
import { toolchain } from "@/lib/pocketanim";
import { usingFixture } from "@/lib/model";
import { resources, versionInfo } from "@/lib/version";

export const runtime = "nodejs";

export async function GET() {
  const tools = await toolchain();
  const found = resources();
  return NextResponse.json({
    ...tools,
    // Google Chirp 3 HD, the narration voice, is set up.
    chirp: found.find((r) => r.id === "voice")?.ready ?? false,
    version: versionInfo(),
    resources: found,
    fixture: usingFixture(),
    model: usingFixture()
      ? "fixture"
      : (process.env.OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4.5"),
  });
}
