import { NextRequest, NextResponse } from "next/server";
import { questionsAction, type QuestionsAction } from "@/lib/questions";

export const runtime = "nodejs";

/** POST {action: "generate" | "reset", lecture, chapter?, count?, model?}: the questions on the videos (lib/questions.ts). */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  try {
    await questionsAction((await params).id, body as QuestionsAction);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
