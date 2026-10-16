import { NextRequest, NextResponse } from "next/server";
import { triageAction, type TriageAction } from "@/lib/triage";

export const runtime = "nodejs";

/** POST {action: "run" | "reset" | "one" | "override" | "stop", kinds?, model?, block?, kind?}: the figure triage. */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  try {
    await triageAction((await params).id, body as TriageAction);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
