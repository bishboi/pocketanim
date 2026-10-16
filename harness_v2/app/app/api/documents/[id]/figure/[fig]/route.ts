import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { documentBook } from "@/lib/store";

export const runtime = "nodejs";
const TYPES: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

/** A figure Datalab cut out of the book, by its block id (URL-encoded): shown with the call that described it. */
export async function GET(_: Request, { params }: { params: Promise<{ id: string; fig: string }> }) {
  const { id, fig } = await params;
  const { figures } = await documentBook(id).catch(() => ({ figures: {} as Record<string, string> }));
  const file = figures[decodeURIComponent(fig)];
  if (!file) return NextResponse.json({ error: "no such figure" }, { status: 404 });
  return new NextResponse(new Uint8Array(await readFile(file)), { headers: { "Content-Type": TYPES[path.extname(file).toLowerCase()] ?? "image/png" } });
}
