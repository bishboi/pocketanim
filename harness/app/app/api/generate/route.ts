import { NextRequest } from "next/server";
import { generate, usingFixture, type GenerateRequest } from "@/lib/model";
import type { AgentEvent } from "@/lib/agent";
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
      typeof body.minutes === "number" && body.minutes >= 1 && body.minutes <= 90 ? body.minutes : undefined,
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

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      let closed = false;
      const send = (event: AgentEvent) => {
        if (closed) return;
        try {
          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify(event)}\n\n`),
          );
        } catch {
          closed = true;
        }
      };
      const stop = () => {
        closed = true;
      };
      request.signal.addEventListener("abort", stop);
      try {
        send({
          type: "message",
          role: "system",
          text: usingFixture() ? "Fixture agent" : "Model agent",
        });
        await generate(job, send, () => closed);
      } catch (error) {
        send({
          type: "error",
          text: error instanceof Error ? error.message : String(error),
        });
      } finally {
        closed = true;
        try {
          controller.close();
        } catch {
          // The browser already went away.
        }
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
