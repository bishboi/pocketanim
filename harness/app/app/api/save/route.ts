import { NextRequest, NextResponse } from "next/server";
import { checkBuild } from "@/lib/pocketanim";
import { saveLecture, storeProblem, type SavePart } from "@/lib/store";

export const runtime = "nodejs";
export const maxDuration = 600;

/** Whether Save is set up, for the button to say so before it is pressed. */
export async function GET() {
  const problem = storeProblem();
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
    });
  }
  if (!parts.length) return NextResponse.json({ saved: false, error: "nothing to save" }, { status: 400 });
  const result = await saveLecture({
    title: String(body?.title ?? parts[0].title),
    content: body?.content ? String(body.content) : undefined,
    subject: body?.subject ? String(body.subject) : undefined,
    language: body?.language ? String(body.language) : undefined,
    parts,
  });
  return NextResponse.json(result, { status: result.saved ? 200 : 500 });
}
