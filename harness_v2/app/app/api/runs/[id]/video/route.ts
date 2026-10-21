import { NextRequest, NextResponse } from "next/server";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { loadRun } from "@/lib/store";
import { LOG_FILE } from "@/lib/video-agent";
import { useOpenAI } from "@/lib/openai-responses";
import { usingFixture } from "@/lib/llm";
import { chapterLines, phoneLibrary, settingsOf, timingOf, videoAction, videoBusy, workspaceOf, type VideoAction } from "@/lib/video";

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
  if (q.get("lecture") && (q.get("files") || q.get("read") !== null || q.get("log"))) {
    // The agent's workspace: its files (?files=1), one file's text (?read=<path>), its conversation (?log=1).
    const ws = workspaceOf(id, Number(q.get("lecture")), Number(q.get("chapter")));
    try {
      if (q.get("files")) return NextResponse.json({ files: await listFiles(ws) });
      if (q.get("log")) {
        const text = await readFile(path.join(ws, LOG_FILE), "utf8").catch(() => "");
        return NextResponse.json({ entries: text.split("\n").filter(Boolean).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean) });
      }
      const file = path.resolve(ws, q.get("read") ?? "");
      if (!file.startsWith(ws + path.sep) || !TEXT.has(path.extname(file).toLowerCase())) return NextResponse.json({ error: "not a text file of the workspace" }, { status: 400 });
      if ((await stat(file)).size > 3_000_000) return NextResponse.json({ error: "too large to show" }, { status: 400 });
      return NextResponse.json({ path: path.relative(ws, file), text: await readFile(file, "utf8") });
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
  return NextResponse.json({ busy: videoBusy(id), settings: { model: s.model, imageModel: s.imageModel, turns: s.turns, effort: s.effort,
    provider: useOpenAI(s.model) ? "openai" : usingFixture(s.model) ? "fixture" : "openrouter", openaiKey: !!process.env.OPENAI_API_KEY?.trim(), styleNote: s.styleNote ?? "",
    customStyle: !!run.video?.settings.style } });
}

const TEXT = new Set([".py", ".md", ".txt", ".json", ".jsonl", ".log", ".csv", ".svg", ".panim"]);
/** Folders the agent's tools fill (renders' frames, the export, Manim's media): left out of the list but for videos. */
const SKIP = /^(export|media|library|history|__pycache__)(\/|$)|\/__pycache__\/|^renders\/(draft|final|look)\/|^renders\/sheet-.*_tiles\//;

async function listFiles(ws: string): Promise<{ path: string; size: number; at: number }[]> {
  const out: { path: string; size: number; at: number }[] = [];
  for (const e of await readdir(ws, { withFileTypes: true, recursive: true }).catch(() => [])) {
    if (!e.isFile()) continue;
    const full = path.join(e.parentPath ?? ws, e.name);
    const rel = path.relative(ws, full).split(path.sep).join("/");
    if (SKIP.test(rel) || rel.startsWith("_panim_export_")) continue;
    const s = await stat(full);
    out.push({ path: rel, size: s.size, at: s.mtimeMs });
  }
  return out.sort((a, b) => a.path.localeCompare(b.path));
}
