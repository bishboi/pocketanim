import { NextRequest, NextResponse } from "next/server";
import { loadRun } from "@/lib/store";
import { chapterScript, voiceAction, type VoiceAction } from "@/lib/voice";

export const runtime = "nodejs";

/** POST {action: "settings" | "speak" | "reset", ...}: the voice (lib/voice.ts). */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  try {
    await voiceAction((await params).id, body as VoiceAction);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}

/** GET ?lecture=&chapter=: the chapter's beat script as the compiler is given it, to edit on the Voice tab. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const run = await loadRun((await params).id);
  if (!run) return NextResponse.json({ error: "no such run" }, { status: 404 });
  const q = new URL(request.url).searchParams;
  try {
    return NextResponse.json({ script: await chapterScript(run, Number(q.get("lecture")), Number(q.get("chapter"))) });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
