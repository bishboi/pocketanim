import { NextRequest, NextResponse } from "next/server";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { refreshFigures } from "@/lib/datalab";
import { docDir } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET: what the figure search found for this book (figure-report.json). */
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const file = path.join(docDir((await params).id), "figure-report.json");
  return NextResponse.json({ report: existsSync(file) ? JSON.parse(await readFile(file, "utf8")) : null });
}

/** POST: search the book's figure pictures again (Datalab's cached result, then the PDF itself); no Datalab call. */
export async function POST(_: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const report = await refreshFigures(docDir((await params).id));
  return report ? NextResponse.json({ report }) : NextResponse.json({ error: "the figures could not be searched again" }, { status: 500 });
}
