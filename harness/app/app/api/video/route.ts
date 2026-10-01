import { NextRequest, NextResponse } from "next/server";
import { createReadStream } from "node:fs";
import { rm, stat } from "node:fs/promises";
import { Readable } from "node:stream";
import { progressFile, renderVideo } from "@/lib/pocketanim";

export const runtime = "nodejs";
export const maxDuration = 10800;

/**
 * The build as a finished MP4, rendered by Manim with its narration: the same file whether it is played on the
 * page or downloaded. ?build=<dir>&scene=<Class>&quality=l|m|h. Rendered on first request, cached after.
 *   &prepare=1&job=<id>  render it (progress at /api/progress?id=<id>) and answer {ready: true} when done
 *   &download=1          as a file to save; otherwise inline, with byte ranges, so the player can seek
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const buildDir = params.get("build");
  const sceneClass = params.get("scene") ?? "GeneratedScene";
  const quality = params.get("quality") ?? "m";
  if (!buildDir) return NextResponse.json({ error: "build is required" }, { status: 400 });
  const progress = progressFile(params.get("job") ?? "");
  const result = await renderVideo(buildDir, sceneClass, quality, progress);
  if (progress) await rm(progress, { force: true });
  if ("error" in result) return NextResponse.json({ error: result.error }, { status: 400 });
  if (params.get("prepare")) return NextResponse.json({ ready: true });

  const size = (await stat(result.file)).size;
  const disposition = params.get("download")
    ? `attachment; filename="${sceneClass}.mp4"`
    : `inline; filename="${sceneClass}.mp4"`;
  const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.get("range") ?? "");
  if (range && (range[1] || range[2])) {
    // A seek: the player asks for the part of the file it needs.
    let start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2]));
    let end = range[1] && range[2] ? Number(range[2]) : size - 1;
    end = Math.min(end, size - 1);
    start = Math.min(start, end);
    const stream = createReadStream(result.file, { start, end });
    return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
      status: 206,
      headers: {
        "Content-Type": "video/mp4",
        "Content-Disposition": disposition,
        "Accept-Ranges": "bytes",
        "Content-Range": `bytes ${start}-${end}/${size}`,
        "Content-Length": String(end - start + 1),
      },
    });
  }
  const stream = createReadStream(result.file);
  return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
    headers: {
      "Content-Type": "video/mp4",
      "Content-Disposition": disposition,
      "Accept-Ranges": "bytes",
      "Content-Length": String(size),
    },
  });
}
