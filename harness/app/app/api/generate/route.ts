import { NextRequest } from "next/server";
import { generate, usingFixture, type GenerateRequest } from "@/lib/model";
import type { AgentEvent } from "@/lib/agent";
import { SSE_HEADERS, createJob, finishJob, followStream, getJob, pushEvent, validJobId, type JobEvent } from "@/lib/jobs";
import { artStyle } from "@/lib/artstyles";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body?.content?.trim() && !body?.instruction?.trim() && !body?.referenceId) {
    return Response.json(
      { error: "nothing to generate from" },
      { status: 400 },
    );
  }
  const job: GenerateRequest = {
    content: String(body.content ?? ""),
    templateId: String(body.templateId ?? "manim"),
    previousSource: body.previousSource
      ? String(body.previousSource)
      : undefined,
    instruction: body.instruction ? String(body.instruction) : undefined,
    documentId: typeof body.documentId === "string" ? body.documentId : undefined,
    minutes:
      typeof body.minutes === "number" && Number.isFinite(body.minutes) && body.minutes >= 1 ? body.minutes : undefined,
    subject: typeof body.subject === "string" && body.subject !== "auto" ? body.subject : undefined,
    referenceId: typeof body.referenceId === "string" ? body.referenceId : undefined,
    language: typeof body.language === "string" && body.language !== "auto" ? body.language : undefined,
    // An OpenRouter model id ("anthropic/claude-opus-4.1"); anything else is ignored.
    transcriptModel: typeof body.transcriptModel === "string" && /^[\w.\-]+\/[\w.:\-]+$/.test(body.transcriptModel.trim())
      ? body.transcriptModel.trim() : undefined,
    art: artStyle(body.art),
    svgModel: typeof body.svgModel === "string" && /^[\w.\-]+\/[\w.:\-]+$/.test(body.svgModel.trim())
      ? body.svgModel.trim() : undefined,
  };

  // The lecture is written as a job of the server's (lib/jobs.ts): the page follows it, and a page that is
  // reloaded follows it again (GET ?job=). Closing the page no longer stops it; Stop (DELETE ?job=) does.
  const running = createJob("generate");
  void (async () => {
    try {
      pushEvent(running, { type: "message", role: "system", text: usingFixture() ? "Fixture agent" : "Model agent" });
      await generate({ ...job, generationId: running.id }, (event: AgentEvent) => pushEvent(running, event as JobEvent),
        () => running.stopped);
    } catch (error) {
      pushEvent(running, { type: "error", text: error instanceof Error ? error.message : String(error) });
    } finally {
      finishJob(running);
    }
  })();
  return new Response(followStream(running, 0, { type: "job", text: running.id }), { headers: SSE_HEADERS });
}

/** GET ?job=<id>&from=<n>: follow a lecture being written (or written already), from its n-th event. */
export async function GET(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("job") ?? "";
  const running = validJobId(id) ? getJob(id) : undefined;
  if (!running) return Response.json({ error: "no such lecture being written (the server may have restarted)" }, { status: 404 });
  const from = Math.max(0, Number(request.nextUrl.searchParams.get("from") ?? 0) || 0);
  return new Response(followStream(running, from, { type: "job", text: running.id }), { headers: SSE_HEADERS });
}

/** DELETE ?job=<id>: stop writing it. */
export async function DELETE(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("job") ?? "";
  const running = validJobId(id) ? getJob(id) : undefined;
  if (!running) return Response.json({ error: "no such job" }, { status: 404 });
  running.stopped = true;
  return Response.json({ stopped: true });
}
