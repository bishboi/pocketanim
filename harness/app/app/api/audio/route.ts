import { NextRequest, NextResponse } from "next/server";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import { REPO } from "@/lib/pocketanim";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const name = request.nextUrl.searchParams.get("file") ?? "";
  if (!name || name.includes("..") || path.isAbsolute(name)) {
    return NextResponse.json({ error: "bad file" }, { status: 400 });
  }
  const file = path.join(REPO, "harness", "app", ".voice", name);
  try {
    const info = await stat(file);
    const size = info.size;
    // Byte ranges, so the player can seek: without them the browser cannot jump into the narration, it
    // started again from 0, and the picture, which follows the voice, jumped back to the start with it.
    const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.get("range") ?? "");
    if (range && (range[1] || range[2])) {
      let start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2]));
      let end = range[1] && range[2] ? Number(range[2]) : size - 1;
      end = Math.min(end, size - 1);
      start = Math.min(start, end);
      return new NextResponse(Readable.toWeb(createReadStream(file, { start, end })) as ReadableStream, {
        status: 206,
        headers: {
          "Content-Type": "audio/wav",
          "Accept-Ranges": "bytes",
          "Content-Range": `bytes ${start}-${end}/${size}`,
          "Content-Length": String(end - start + 1),
          "Cache-Control": "no-store",
        },
      });
    }
    return new NextResponse(Readable.toWeb(createReadStream(file)) as ReadableStream, {
      headers: {
        "Content-Type": "audio/wav",
        "Accept-Ranges": "bytes",
        "Content-Length": String(size),
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json({ error: "missing audio" }, { status: 404 });
  }
}
