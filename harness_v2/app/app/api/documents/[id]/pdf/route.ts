import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { docDir } from "@/lib/store";

export const runtime = "nodejs";

/** The uploaded PDF itself, for the page's viewer. */
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const bytes = await readFile(path.join(docDir((await params).id), "source.pdf"));
    return new NextResponse(new Uint8Array(bytes), { headers: { "Content-Type": "application/pdf" } });
  } catch {
    return NextResponse.json({ error: "no such document" }, { status: 404 });
  }
}
