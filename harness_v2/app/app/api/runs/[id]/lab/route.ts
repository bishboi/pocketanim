import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";
import { labAction, type LabAction } from "@/lib/lab";
import { engineDir } from "@/lib/maps";

export const runtime = "nodejs";

/** POST {action: "add" | "save" | "try" | "duplicate" | "remove", ...}: the Lab's experiments (lib/lab.ts). */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  try {
    const item = await labAction((await params).id, body as LabAction);
    return NextResponse.json({ ok: true, id: item?.id });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}

/** GET: the beat script's reference (engine/BEAT_SCRIPT.md), to read beside the editor. */
export async function GET() {
  try {
    return NextResponse.json({ reference: await readFile(path.join(engineDir(), "BEAT_SCRIPT.md"), "utf8") });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
