import { NextResponse } from "next/server";
import { toolchain } from "@/lib/pocketanim";
import { usingFixture } from "@/lib/model";
import { kokoroReady } from "@/lib/voice";

export const runtime = "nodejs";

export async function GET() {
  const tools = await toolchain();
  const kokoro = await kokoroReady();
  return NextResponse.json({
    ...tools,
    kokoro,
    fixture: usingFixture(),
    model: usingFixture()
      ? "fixture"
      : (process.env.OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4.5"),
  });
}
