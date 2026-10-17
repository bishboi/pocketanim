import { NextRequest, NextResponse } from "next/server";
import { voiceAction, type VoiceAction } from "@/lib/voice";

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
