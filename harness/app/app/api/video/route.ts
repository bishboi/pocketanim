import { NextRequest, NextResponse } from "next/server";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { Readable } from "node:stream";
import { renderVideo } from "@/lib/pocketanim";

export const runtime = "nodejs";
export const maxDuration = 1800;

/**
 * The build as a finished MP4, rendered by Manim with its narration.
 * ?build=<dir>&scene=<Class>&quality=l|m|h. Rendered on first request, cached after.
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const buildDir = params.get("build");
  const sceneClass = params.get("scene") ?? "GeneratedScene";
  const quality = params.get("quality") ?? "m";
  if (!buildDir) return NextResponse.json({ error: "build is required" }, { status: 400 });
  const result = await renderVideo(buildDir, sceneClass, quality);
  if ("error" in result) return NextResponse.json({ error: result.error }, { status: 400 });
  const info = await stat(result.file);
  const stream = createReadStream(result.file);
  return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
    headers: {
      "Content-Type": "video/mp4",
      "Content-Disposition": `attachment; filename="${sceneClass}.mp4"`,
      "Content-Length": String(info.size),
    },
  });
}
