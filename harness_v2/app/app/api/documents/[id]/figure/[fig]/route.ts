import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { documentBook } from "@/lib/store";
import { figureFile } from "@/lib/source/blocks";

export const runtime = "nodejs";
const TYPES: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

/** A figure Datalab cut out of the book, by its block id (URL-encoded; a group's is its picture's). */
export async function GET(_: Request, { params }: { params: Promise<{ id: string; fig: string }> }) {
  const { id, fig } = await params;
  const book = await documentBook(id).catch(() => null);
  const block = decodeURIComponent(fig);
  const file = book && (book.figures[block] ?? figureFile({ id: block } as never, book.json, book.figures));
  if (!file) return NextResponse.json({ error: "no such figure" }, { status: 404 });
  return new NextResponse(new Uint8Array(await readFile(file)), { headers: { "Content-Type": TYPES[path.extname(file).toLowerCase()] ?? "image/png" } });
}
