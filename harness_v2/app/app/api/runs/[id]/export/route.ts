import { NextRequest, NextResponse } from "next/server";
import { loadRun } from "@/lib/store";
import { exportWhole, transcriptMarkdown } from "@/lib/export";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET ?format=json|md: the run's transcript as a file: JSON with the book inside, to import for the next steps; Markdown to read. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const run = await loadRun((await params).id).catch(() => null);
  if (!run) return NextResponse.json({ error: "no such run" }, { status: 404 });
  const md = request.nextUrl.searchParams.get("format") === "md";
  const name = `${run.documentName.replace(/\.pdf$/i, "").replace(/[^\w.-]+/g, "_")}-${run.id}.${md ? "transcript.md" : "panim-transcript.json"}`;
  return new NextResponse(md ? transcriptMarkdown(run) : JSON.stringify(await exportWhole(run)), {
    headers: { "Content-Type": md ? "text/markdown; charset=utf-8" : "application/json", "Content-Disposition": `attachment; filename="${name}"` },
  });
}
