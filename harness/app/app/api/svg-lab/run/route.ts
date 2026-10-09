import { NextRequest, NextResponse } from "next/server";
import { cleanParts, getRun, startRun, stopRun, validModel } from "@/lib/svglab";

export const runtime = "nodejs";

/** POST {models, diagrams: [{id, what, parts, moves?}], atOnce}: start a run in the server (it goes on whatever the
 * page does); the page polls GET ?id= for it. */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const models = [...new Set((Array.isArray(body?.models) ? body.models : []).map((m: unknown) => String(m).trim()))]
    .filter((m): m is string => validModel(m)).slice(0, 20);
  const diagrams = (Array.isArray(body?.diagrams) ? body.diagrams : [])
    .map((d: { id?: unknown; what?: unknown; parts?: unknown; moves?: unknown }) => ({
      id: String(d.id ?? "").replace(/[^\w-]/g, "").slice(0, 40), what: String(d.what ?? "").slice(0, 2000),
      parts: cleanParts(d.parts), moves: typeof d.moves === "string" ? d.moves.slice(0, 500) : undefined,
    }))
    .filter((d: { id: string; what: string; parts: string[] }) => d.id && d.what.trim() && d.parts.length)
    .slice(0, 20);
  if (!models.length || !diagrams.length) {
    return NextResponse.json({ error: "give at least one model id and one diagram with its parts" }, { status: 400 });
  }
  if (!process.env.OPENROUTER_API_KEY) return NextResponse.json({ error: "OPENROUTER_API_KEY is not set on the server" }, { status: 400 });
  const atOnce = Math.max(1, Math.min(12, Number(body?.atOnce) || 4));
  return NextResponse.json({ run: startRun(models, diagrams, atOnce) });
}

/** GET ?id=: a run as it stands. */
export async function GET(request: NextRequest) {
  const run = await getRun(request.nextUrl.searchParams.get("id") ?? "");
  if (!run) return NextResponse.json({ error: "no such run" }, { status: 404 });
  return NextResponse.json({ run });
}

/** DELETE ?id=: stop a run (drawings under way finish their current request; the rest are not started). */
export async function DELETE(request: NextRequest) {
  return NextResponse.json({ stopped: stopRun(request.nextUrl.searchParams.get("id") ?? "") });
}
