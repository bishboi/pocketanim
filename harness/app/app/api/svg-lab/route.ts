import { NextRequest, NextResponse } from "next/server";
import { drawForLab, labModels, validModel } from "@/lib/svglab";

export const runtime = "nodejs";
// A drawing is a conversation: drawn, checked, repaired, looked at and fixed. A slow model takes minutes.
export const maxDuration = 900;

let models: { at: number; list: Awaited<ReturnType<typeof labModels>> } | null = null;

/** GET: OpenRouter's models and their prices, for the lab's picker (kept for an hour). */
export async function GET() {
  try {
    if (!models || Date.now() - models.at > 3600_000) models = { at: Date.now(), list: await labModels() };
    return NextResponse.json({ models: models.list, key: !!process.env.OPENROUTER_API_KEY });
  } catch (error) {
    return NextResponse.json({ models: [], key: !!process.env.OPENROUTER_API_KEY,
      error: error instanceof Error ? error.message : String(error) });
  }
}

/** POST {model, what, parts, moves?, run}: one diagram drawn by one model, with its cost, time and requests. */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body || !validModel(body.model)) return NextResponse.json({ error: "give an OpenRouter model id, like anthropic/claude-sonnet-4.5" }, { status: 400 });
  if (typeof body.what !== "string" || !body.what.trim()) return NextResponse.json({ error: "say what to draw" }, { status: 400 });
  const result = await drawForLab(body.model.trim(), { what: body.what.slice(0, 2000), parts: body.parts,
    moves: typeof body.moves === "string" ? body.moves.slice(0, 500) : undefined }, String(body.run ?? "run"), request.signal);
  return NextResponse.json(result);
}
