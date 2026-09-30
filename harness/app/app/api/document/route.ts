import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { addDocument, addReference, figureFile, loadDocument, setExcluded, type DocumentManifest } from "@/lib/document";

export const runtime = "nodejs";
export const maxDuration = 1200;

const TYPES: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

/**
 * POST a PDF (multipart field "file"): its text and figures. Or POST JSON {youtube: link} or {transcript, title?,
 * youtube?}: a reference video's transcript, in parts.
 */
export async function POST(request: NextRequest) {
  if ((request.headers.get("content-type") ?? "").includes("application/json")) {
    const body = await request.json().catch(() => ({}));
    try {
      const doc = await addReference({ url: body?.youtube, transcript: body?.transcript, title: body?.title });
      return NextResponse.json({ ...shape(doc), name: doc.video?.title ?? "Reference video" });
    } catch (error) {
      return NextResponse.json({ error: (error as Error).message }, { status: 400 });
    }
  }
  const form = await request.formData().catch(() => null);
  const file = form?.get("file");
  if (!file || typeof file === "string") return NextResponse.json({ error: "upload a PDF as 'file'" }, { status: 400 });
  if (file.size > 60 * 1024 * 1024) return NextResponse.json({ error: "the PDF is over 60 MB" }, { status: 413 });
  try {
    const doc = await addDocument(new Uint8Array(await file.arrayBuffer()));
    return NextResponse.json({ ...shape(doc), name: file.name });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}

/** What the page shows: the kept figures and the removed ones, each with its thumbnail URL. */
function shape(doc: DocumentManifest) {
  const withUrl = (f: DocumentManifest["figures"][number]) => ({ id: f.id, caption: f.caption, page: f.page,
    url: `/api/document?id=${doc.id}&figure=${f.id}` });
  return { ...doc, figures: doc.figures.map(withUrl), excluded: doc.excluded.map(withUrl) };
}

/** DELETE ?id=&figure=: leave that figure out of the lecture (it stays on disk, restorable). */
export async function DELETE(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("id") ?? "";
  const figure = request.nextUrl.searchParams.get("figure") ?? "";
  try {
    const doc = await loadDocument(id);
    const removed = [...doc.excluded.map((f) => f.id), figure];
    return NextResponse.json(shape(await setExcluded(id, removed)));
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}

/** PATCH ?id= {excluded: [...]}: set the removed figures ([] restores them all). */
export async function PATCH(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("id") ?? "";
  const body = await request.json().catch(() => ({}));
  try {
    return NextResponse.json(shape(await setExcluded(id, Array.isArray(body?.excluded) ? body.excluded.map(String) : [])));
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}

/** GET ?id=&figure=: a figure's image (removed ones too, for restoring). */
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
