import { NextRequest, NextResponse } from "next/server";
import { scenesAction, type ScenesAction } from "@/lib/scenes";

export const runtime = "nodejs";

/** POST {action: "look" | "kinds" | "beatKinds" | "edit" | "build" | "fix" | "compile" | "render" | "stop", ...}: the scenes. */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  try {
    await scenesAction((await params).id, body as ScenesAction);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
