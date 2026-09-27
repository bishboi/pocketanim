import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { addDocument, figureFile } from "@/lib/document";

export const runtime = "nodejs";
export const maxDuration = 1200;

const TYPES: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

/** POST a PDF (multipart field "file"): its text and figures. */
export async function POST(request: NextRequest) {
  const form = await request.formData().catch(() => null);
  const file = form?.get("file");
  if (!file || typeof file === "string") return NextResponse.json({ error: "upload a PDF as 'file'" }, { status: 400 });
  if (file.size > 60 * 1024 * 1024) return NextResponse.json({ error: "the PDF is over 60 MB" }, { status: 413 });
  try {
    const doc = await addDocument(new Uint8Array(await file.arrayBuffer()));
    return NextResponse.json({
      ...doc,
      name: file.name,
      figures: doc.figures.map((f) => ({ id: f.id, caption: f.caption, page: f.page,
        url: `/api/document?id=${doc.id}&figure=${f.id}` })),
    });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}

/** GET ?id=&figure=: a figure's image. */
export async function GET(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("id") ?? "";
  const figure = request.nextUrl.searchParams.get("figure") ?? "";
  try {
    const file = await figureFile(id, figure);
    return new NextResponse(new Uint8Array(await readFile(file)), {
      headers: { "Content-Type": TYPES[path.extname(file).toLowerCase()] ?? "application/octet-stream" },
    });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 404 });
  }
}
