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
    // Kokoro-82M is ready: the package is installed and its weights are downloaded.
    kokoro: found.find((r) => r.id === "voice")?.ready ?? false,
    version: versionInfo(),
    resources: found,
    fixture: usingFixture(),
    model: usingFixture()
      ? "fixture"
      : (process.env.OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4.5"),
  });
}
