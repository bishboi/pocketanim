import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { loadRun } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const TYPES: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

/** A figure's generated image, by its block id (URL-encoded). */
export async function GET(_: Request, { params }: { params: Promise<{ id: string; fig: string }> }) {
  const { id, fig } = await params;
  const run = await loadRun(id).catch(() => null);
  const file = run?.generation?.figures[decodeURIComponent(fig)]?.file;
  if (!file) return NextResponse.json({ error: "no generated image" }, { status: 404 });
  return new NextResponse(new Uint8Array(await readFile(file)), { headers: { "Content-Type": TYPES[path.extname(file).toLowerCase()] ?? "image/png", "Cache-Control": "no-store" } });
}
