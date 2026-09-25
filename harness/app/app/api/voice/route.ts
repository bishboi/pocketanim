import { NextRequest, NextResponse } from "next/server";
import path from "node:path";
import { speak } from "@/lib/voice";
import { REPO } from "@/lib/pocketanim";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body?.source) return NextResponse.json({ error: "source is required" }, { status: 400 });
  const result = await speak(String(body.source), String(body.templateId ?? "manim"));
  const audioUrl =
    result.ok && result.audioPath
      ? `/api/audio?file=${encodeURIComponent(path.relative(path.join(REPO, "harness", "app", ".voice"), result.audioPath))}`
      : null;
  return NextResponse.json({
    ok: result.ok,
    source: result.source,
    audioUrl,
    durations: result.durations ?? [],
    error: result.error,
  });
}
