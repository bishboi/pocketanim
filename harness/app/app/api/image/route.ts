import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { checkBuild } from "@/lib/pocketanim";

export const runtime = "nodejs";

/**
 * GET ?build=<build dir>&file=<asset>.png: a photo or figure a scene showed.
 * The program cannot carry pixels, so the preview draws these from the
 * exporter's image track (scene_ir.py `images`).
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const file = params.get("file") ?? "";
  if (!/^[0-9a-f]{16}\.png$/.test(file)) return NextResponse.json({ error: "bad file" }, { status: 400 });
  let buildDir: string;
  try {
    ({ buildDir } = checkBuild(params.get("build") ?? "", "GeneratedScene"));
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
  try {
    const data = await readFile(path.join(buildDir, "dsl", "generated", "images", file));
    return new NextResponse(new Uint8Array(data), {
      headers: { "Content-Type": "image/png", "Cache-Control": "private, max-age=3600" },
    });
  } catch {
    return NextResponse.json({ error: "missing image" }, { status: 404 });
  }
}
