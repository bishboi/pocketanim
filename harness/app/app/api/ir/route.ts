import { NextRequest, NextResponse } from "next/server";
import { sceneIR } from "@/lib/pocketanim";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const buildDir = params.get("build");
  const sceneClass = params.get("scene") ?? "GeneratedScene";
  if (!buildDir) {
    return NextResponse.json({ error: "build is required" }, { status: 400 });
  }
  const result = await sceneIR(buildDir, sceneClass);
  if ("error" in result && result.error) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  // Big and perfectly compressible: ~730 kB of numbers, ~25 kB on the wire.
  return NextResponse.json(result);
}
