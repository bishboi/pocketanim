import { NextResponse } from "next/server";
import { resolveModels } from "@/lib/models";
import { voicesReady } from "@/lib/voice";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** What the page needs to know before a run: whether calls are real, and every role's model from the environment. */
export async function GET() {
  const models = resolveModels();
  return NextResponse.json({
    hasKey: !!process.env.OPENROUTER_API_KEY,
    datalab: !!process.env.DATALAB_API_KEY,
    models,
    voices: voicesReady(),
    plannerModel: models.planner.model,
    writerModel: models.writer.model,
    figureModel: models.figure.model,
    triageModel: models.triage.model,
  });
}
