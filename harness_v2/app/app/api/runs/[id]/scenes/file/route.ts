import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { rangeOf } from "@/lib/ranges";
import { scenesDir } from "@/lib/scenes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const TYPES: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".mp4": "video/mp4", ".py": "text/plain; charset=utf-8", ".json": "application/json", ".wav": "audio/wav" };

/** A file the scenes made (a render's frame, clip or video), by its path under the run's scenes folder (?p=). */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const root = scenesDir(id);
  const file = path.resolve(root, new URL(request.url).searchParams.get("p") ?? "");
  if (!file.startsWith(root + path.sep) || !TYPES[path.extname(file)]) return NextResponse.json({ error: "no such file" }, { status: 404 });
  try {
    const data = await readFile(file);
    // A range (the player seeks the narration): the browser seeks only in audio served in ranges.
    const range = rangeOf(request.headers.get("range"), data.length);
    if (range === "bad") return new NextResponse(null, { status: 416, headers: { "Content-Range": `bytes */${data.length}` } });
    if (range) {
      const [start, end] = range;
      return new NextResponse(new Uint8Array(data.subarray(start, end + 1)), { status: 206, headers: { "Content-Type": TYPES[path.extname(file)],
        "Content-Range": `bytes ${start}-${end}/${data.length}`, "Accept-Ranges": "bytes", "Content-Length": String(end - start + 1), "Cache-Control": "no-store" } });
    }
    return new NextResponse(new Uint8Array(data), { headers: { "Content-Type": TYPES[path.extname(file)], "Accept-Ranges": "bytes", "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "no such file" }, { status: 404 });
  }
}
