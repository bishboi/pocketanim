import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { scenesDir } from "@/lib/scenes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const TYPES: Record<string, string> = { ".png": "image/png", ".mp4": "video/mp4", ".py": "text/plain; charset=utf-8", ".json": "application/json" };

/** A file the scenes made (a render's frame, clip or video), by its path under the run's scenes folder (?p=). */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const root = scenesDir(id);
  const file = path.resolve(root, new URL(request.url).searchParams.get("p") ?? "");
  if (!file.startsWith(root + path.sep) || !TYPES[path.extname(file)]) return NextResponse.json({ error: "no such file" }, { status: 404 });
  try {
    return new NextResponse(new Uint8Array(await readFile(file)), { headers: { "Content-Type": TYPES[path.extname(file)], "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "no such file" }, { status: 404 });
  }
}
