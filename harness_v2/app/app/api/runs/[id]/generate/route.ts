import { NextRequest, NextResponse } from "next/server";
import { generateAction, type GenerateAction } from "@/lib/generate";

export const runtime = "nodejs";

/** POST {action: "run" | "reset" | "one" | "stop", model?, block?}: the redraws' generation. */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  try {
    await generateAction((await params).id, body as GenerateAction);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
