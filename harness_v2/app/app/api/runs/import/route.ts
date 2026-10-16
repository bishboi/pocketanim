import { NextRequest, NextResponse } from "next/server";
import { importTranscript } from "@/lib/export";

export const runtime = "nodejs";

/** POST a transcript exported as JSON (form field "file"): it becomes a run of its own, to continue from. */
export async function POST(request: NextRequest) {
  try {
    const file = (await request.formData()).get("file");
    if (!(file instanceof File)) throw new Error("no file");
    const run = await importTranscript(JSON.parse(await file.text()), file.name);
    return NextResponse.json({ id: run.id });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 400 });
  }
}
