import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { bundleLibrary } from "@/lib/pocketanim";

export const runtime = "nodejs";
export const maxDuration = 300;

/** The build as a phone library, zipped. See bundleLibrary. */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const buildDir = params.get("build");
  const sceneClass = params.get("scene") ?? "GeneratedScene";
  if (!buildDir) return NextResponse.json({ error: "build is required" }, { status: 400 });
  const result = await bundleLibrary(buildDir, sceneClass);
  if ("error" in result) return NextResponse.json({ error: result.error }, { status: 400 });
  const bytes = await readFile(result.zip);
  return new NextResponse(new Uint8Array(bytes), {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="${path.basename(result.zip)}"`,
      "Content-Length": String(bytes.length),
    },
  });
}
