import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { loadRun } from "@/lib/store";
import { onBoard } from "@/lib/prompts/svg";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const TYPES: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

/** A figure's generated image, by its block id (URL-encoded). */
export async function GET(request: Request, { params }: { params: Promise<{ id: string; fig: string }> }) {
  const { id, fig } = await params;
  const run = await loadRun(id).catch(() => null);
  const file = run?.generation?.figures[decodeURIComponent(fig)]?.file;
  if (!file) return NextResponse.json({ error: "no generated image" }, { status: 404 });
  if (file.endsWith(".svg")) {
    // An SVG as v1's default board shows it (its colour names as the board's colours, on the board), or as written
    // (?raw). Served so nothing in it can run, even opened on its own.
    const svg = await readFile(file, "utf8");
    return new NextResponse(new URL(request.url).searchParams.has("raw") ? svg : onBoard(svg), { headers: { "Content-Type": "image/svg+xml",
      "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox" } });
  }
  return new NextResponse(new Uint8Array(await readFile(file)), { headers: { "Content-Type": TYPES[path.extname(file).toLowerCase()] ?? "image/png", "Cache-Control": "no-store" } });
}
