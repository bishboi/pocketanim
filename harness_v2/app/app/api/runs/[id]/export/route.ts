import { NextRequest, NextResponse } from "next/server";
import { loadRun } from "@/lib/store";
import { exportTranscript, transcriptMarkdown } from "@/lib/export";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET ?format=json|md: the run's transcript as a file (JSON for the steps to come, Markdown to read). */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const run = await loadRun((await params).id).catch(() => null);
  if (!run) return NextResponse.json({ error: "no such run" }, { status: 404 });
  const md = request.nextUrl.searchParams.get("format") === "md";
  const name = `${run.documentName.replace(/\.pdf$/i, "").replace(/[^\w.-]+/g, "_")}-${run.id}.transcript.${md ? "md" : "json"}`;
  return new NextResponse(md ? transcriptMarkdown(run) : JSON.stringify(exportTranscript(run), null, 2), {
    headers: { "Content-Type": md ? "text/markdown; charset=utf-8" : "application/json", "Content-Disposition": `attachment; filename="${name}"` },
  });
}
