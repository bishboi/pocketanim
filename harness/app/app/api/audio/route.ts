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
    const stream = createReadStream(file);
    return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
      headers: {
        "Content-Type": "audio/wav",
        "Content-Length": String(info.size),
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json({ error: "missing audio" }, { status: 404 });
  }
}
