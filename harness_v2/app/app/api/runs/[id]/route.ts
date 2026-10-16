import { NextRequest, NextResponse } from "next/server";
import { loadRun } from "@/lib/store";
import { continueRun, redoFrom, stopJob } from "@/lib/run";
import type { StepKey } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** A run as it stands: its steps, sections, plan, every call. */
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const run = await loadRun((await params).id).catch(() => null);
  return run ? NextResponse.json(run) : NextResponse.json({ error: "no such run" }, { status: 404 });
}

/** POST {action: "continue" | "stop" | "redo", step?, options?}: pick the transcript up, stop it, or make a step again. */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const id = (await params).id;
  const body = await request.json().catch(() => ({}));
  try {
    if (body?.action === "stop") stopJob(id, "transcript");
    else if (body?.action === "continue") await continueRun(id, body?.options ?? {});
    else if (body?.action === "redo") await redoFrom(id, String(body?.step) as StepKey, body?.options ?? {});
    else throw new Error("unknown action");
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
