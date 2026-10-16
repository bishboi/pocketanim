import { NextResponse } from "next/server";

export const runtime = "nodejs";

/** What the page needs to know before a run: whether calls are real, and the default models. */
export async function GET() {
  return NextResponse.json({
    hasKey: !!process.env.OPENROUTER_API_KEY,
    datalab: !!process.env.DATALAB_API_KEY,
    plannerModel: process.env.V2_PLANNER_MODEL || "anthropic/claude-sonnet-4.5",
    writerModel: process.env.V2_WRITER_MODEL || "anthropic/claude-sonnet-4.5",
    figureModel: process.env.V2_FIGURE_MODEL || "google/gemini-2.5-flash",
    triageModel: process.env.V2_TRIAGE_MODEL || process.env.V2_FIGURE_MODEL || "google/gemini-2.5-flash",
  });
}
