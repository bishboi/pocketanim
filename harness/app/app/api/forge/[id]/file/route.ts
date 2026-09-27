import { NextRequest, NextResponse } from "next/server";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import { jobFile } from "@/lib/forge";

export const runtime = "nodejs";

/** A job's deliverable: ?name=out/video.mp4 (out/ and qa/ only). ?download=1 to save it. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const name = request.nextUrl.searchParams.get("name") ?? "";
  let found;
  try {
    found = jobFile(id, name);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 404 });
  }
  const info = await stat(found.file);
  const size = info.size;
  const headers: Record<string, string> = { "Content-Type": found.type, "Accept-Ranges": "bytes", "Cache-Control": "no-store" };
  if (request.nextUrl.searchParams.get("download")) {
    headers["Content-Disposition"] = `attachment; filename="${id}-${path.basename(found.file)}"`;
  }
  // Ranges, so the <video> element can seek.
  const range = request.headers.get("range")?.match(/bytes=(\d*)-(\d*)/);
  if (range && (range[1] || range[2])) {
    const start = range[1] ? parseInt(range[1], 10) : Math.max(0, size - parseInt(range[2], 10));
    const end = range[1] && range[2] ? Math.min(parseInt(range[2], 10), size - 1) : size - 1;
    if (start >= size || start > end) {
      return new NextResponse(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    }
    const stream = createReadStream(found.file, { start, end });
    return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
      status: 206,
      headers: { ...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": String(end - start + 1) },
    });
  }
  const stream = createReadStream(found.file);
  return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
    headers: { ...headers, "Content-Length": String(size) },
  });
}
