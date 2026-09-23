import { NextRequest, NextResponse } from "next/server";
import { renderFrame } from "@/lib/pocketanim";

export const runtime = "nodejs";
export const maxDuration = 120;

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const buildDir = params.get("build");
  const sceneClass = params.get("scene") ?? "GeneratedScene";
  const frame = Number(params.get("n") ?? 0);
  const width = Number(params.get("w") ?? 640);

  if (!buildDir) {
    return NextResponse.json({ error: "build is required" }, { status: 400 });
  }
  const result = await renderFrame(buildDir, sceneClass, frame, width);
  if (!Buffer.isBuffer(result)) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  return new NextResponse(new Uint8Array(result), {
    headers: {
      "Content-Type": "image/png",
      // Frames are derived, never stored. Caching one is fine; keeping it is
      // not, which is the whole point of not having a video at rest.
      "Cache-Control": "private, max-age=60",
    },
  });
}
