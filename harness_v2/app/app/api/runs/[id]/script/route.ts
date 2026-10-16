import { NextRequest, NextResponse } from "next/server";
import { scriptAction, type ScriptAction } from "@/lib/script";

export const runtime = "nodejs";

/** POST {action: "run" | "reset" | "one" | "next" | "stop", lecture?, model?, oneAtATime?}: the lectures' scripts (chapters and beats). */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  try {
    await scriptAction((await params).id, body as ScriptAction);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
