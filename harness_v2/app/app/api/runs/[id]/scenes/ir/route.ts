import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { scenesDir } from "@/lib/scenes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** A playable scene's geometry for v1's web player (scene_ir.json in the build ?p= names; ?segment=k: a long one's part). */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const root = scenesDir(id);
  const q = new URL(request.url).searchParams;
  const dir = path.resolve(root, q.get("p") ?? "");
  if (!dir.startsWith(root + path.sep)) return NextResponse.json({ error: "no such scene" }, { status: 404 });
  const segment = q.get("segment");
  if (segment !== null && !/^\d+$/.test(segment)) return NextResponse.json({ error: "no such segment" }, { status: 404 });
  try {
    const text = await readFile(path.join(dir, segment === null ? "scene_ir.json" : `scene_ir_${segment}.json`), "utf8");
    return new NextResponse(text, { headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "this scene has no geometry: render it again" }, { status: 404 });
  }
}
