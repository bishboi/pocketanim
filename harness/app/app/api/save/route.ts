import { NextRequest, NextResponse } from "next/server";
import { checkBuild } from "@/lib/pocketanim";
import { saveLecture, storeProblem, storeStatus, type SavePart } from "@/lib/store";

export const runtime = "nodejs";
// An hour of lectures is a few hundred files and tens of MB to upload.
export const maxDuration = 1800;

/**
 * Whether Save is set up, for the button to say so before it is pressed; with ?status=1, what is saved and what
 * the phone's Saved list can see of it (lib/store.ts storeStatus).
 */
export async function GET(request: NextRequest) {
  const problem = storeProblem();
  if (request.nextUrl.searchParams.get("status")) {
    return NextResponse.json({ ready: !problem, problem, status: problem ? null : await storeStatus() });
  }
  return NextResponse.json({ ready: !problem, problem });
}

/**
 * Save the lecture on screen -- one video, or each micro-lecture of a series -- to the database and its phone
 * libraries to Supabase Storage, for the phone app to list (lib/store.ts).
 */
export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => null)) as {
    title?: unknown; content?: unknown; subject?: unknown; language?: unknown; parts?: unknown[];
  } | null;
  const parts: SavePart[] = [];
  for (const raw of Array.isArray(body?.parts) ? body!.parts : []) {
    const p = raw as Record<string, unknown>;
    try {
      checkBuild(String(p.buildDir ?? ""), String(p.sceneClass ?? ""));
    } catch (error) {
      return NextResponse.json({ saved: false, error: `not a build to save: ${(error as Error).message}` }, { status: 400 });
    }
    parts.push({
      buildDir: String(p.buildDir),
      sceneClass: String(p.sceneClass),
      source: String(p.source ?? ""),
      title: String(p.title ?? "Untitled"),
      minutes: Number.isFinite(Number(p.minutes)) ? Number(p.minutes) : undefined,
      instruction: p.instruction ? String(p.instruction) : null,
      model: p.model ? String(p.model) : null,
      transcript: p.transcript ? String(p.transcript) : undefined,
      inputTokens: Number.isFinite(Number(p.inputTokens)) ? Number(p.inputTokens) : undefined,
      outputTokens: Number.isFinite(Number(p.outputTokens)) ? Number(p.outputTokens) : undefined,
      lecture: Number.isInteger(Number(p.lecture)) && Number(p.lecture) >= 1 ? Number(p.lecture) : undefined,
      of: Number.isInteger(Number(p.of)) && Number(p.of) >= 1 ? Number(p.of) : undefined,
    });
  }
  if (!parts.length) return NextResponse.json({ saved: false, error: "nothing to save" }, { status: 400 });
  const save = {
    title: String(body?.title ?? parts[0].title),
    content: body?.content ? String(body.content) : undefined,
    subject: body?.subject ? String(body.subject) : undefined,
    language: body?.language ? String(body.language) : undefined,
    parts,
  };
  if (!(request.headers.get("accept") ?? "").includes("application/x-ndjson")) {
    const result = await saveLecture(save);
    return NextResponse.json(result, { status: result.saved ? 200 : 500 });
  }
  // The page's Save: one JSON line per step (packing, each file uploaded, each video saved or failed), then the
  // result, so it can show how far it has got and which videos are already in, whatever happens after.
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (line: unknown) => {
        try {
          controller.enqueue(encoder.encode(`${JSON.stringify(line)}\n`));
        } catch {
          // the page went away; the save carries on and its rows say what was saved
        }
      };
      try {
        const result = await saveLecture(save, (progress) => send({ type: "progress", ...progress }));
        send({ type: "result", ...result });
      } catch (error) {
        send({ type: "result", saved: false, error: error instanceof Error ? error.message : String(error) });
      } finally {
        try {
          controller.close();
        } catch {}
      }
    },
  });
  return new Response(stream, { headers: { "Content-Type": "application/x-ndjson", "Cache-Control": "no-store" } });
}
