import { NextResponse } from "next/server";
import { loadRun } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** A run as it stands: its steps, sections, plan, every call. */
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const run = await loadRun((await params).id).catch(() => null);
  return run ? NextResponse.json(run) : NextResponse.json({ error: "no such run" }, { status: 404 });
}
