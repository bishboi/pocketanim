import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { loadRun } from "@/lib/store";
import { chapterLines, phoneLibrary, settingsOf, timingOf, videoAction, videoBusy, type VideoAction } from "@/lib/video";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** POST {action: "settings" | "narrate" | "build" | "all" | "stop" | "reset", ...}: the video step (lib/video.ts). */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const body = await request.json().catch(() => ({}));
  try {
    await videoAction((await params).id, body as VideoAction);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}

/** GET ?style=1: the look's screenshot; ?lecture=&chapter=: the chapter's lines and its narration's timing; else what is
 * being worked on now. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const id = (await params).id;
  const run = await loadRun(id);
  if (!run) return NextResponse.json({ error: "no such run" }, { status: 404 });
  const q = new URL(request.url).searchParams;
  if (q.get("style")) {
    const file = settingsOf(run).style;
    const data = await readFile(file).catch(() => null);
    if (!data) return NextResponse.json({ error: "no look" }, { status: 404 });
    const type = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" }[path.extname(file).toLowerCase()] ?? "image/png";
    return new NextResponse(new Uint8Array(data), { headers: { "Content-Type": type, "Cache-Control": "no-store" } });
  }
  if (q.get("library")) {
    // The chapter as a phone library (zip): to import on the phone, or unzip and push to the app's files.
    try {
      const { zip, name } = await phoneLibrary(run, Number(q.get("lecture")), Number(q.get("chapter")));
      return new NextResponse(new Uint8Array(await readFile(zip)), { headers: { "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="${name}"`, "Cache-Control": "no-store" } });
    } catch (error) {
      return NextResponse.json({ error: (error as Error).message }, { status: 400 });
    }
  }
  if (q.get("lecture")) {
    const n = Number(q.get("lecture"));
    const c = Number(q.get("chapter"));
    try {
      return NextResponse.json({ lines: chapterLines(run, n, c), timing: await timingOf(id, n, c) });
    } catch (error) {
      return NextResponse.json({ error: (error as Error).message }, { status: 400 });
    }
  }
  const s = settingsOf(run);
  return NextResponse.json({ busy: videoBusy(id), settings: { model: s.model, imageModel: s.imageModel, turns: s.turns, styleNote: s.styleNote ?? "",
    customStyle: !!run.video?.settings.style } });
}
