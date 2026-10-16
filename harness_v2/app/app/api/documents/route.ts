import { NextRequest, NextResponse } from "next/server";
import { addDocument } from "@/lib/docs";
import { listDocuments } from "@/lib/store";

export const runtime = "nodejs";
export const maxDuration = 1200;

/** The books uploaded so far. */
export async function GET() {
  return NextResponse.json({ documents: await listDocuments() });
}

/** POST a PDF (multipart field "file"): kept, and read into Markdown. */
export async function POST(request: NextRequest) {
  const form = await request.formData().catch(() => null);
  const file = form?.get("file");
  if (!file || typeof file === "string") return NextResponse.json({ error: "upload a PDF as 'file'" }, { status: 400 });
  try {
    return NextResponse.json(await addDocument(file.name, new Uint8Array(await file.arrayBuffer())));
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
