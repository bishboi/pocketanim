import { NextRequest, NextResponse } from "next/server";
import { startRun } from "@/lib/run";
import { listRuns } from "@/lib/store";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ runs: await listRuns() });
}

/** POST {documentId, options}: start a transcription; it runs on the server, the page follows it by its id. */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  try {
    const run = await startRun(String(body?.documentId ?? ""), body?.options ?? {});
    return NextResponse.json({ id: run.id });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
