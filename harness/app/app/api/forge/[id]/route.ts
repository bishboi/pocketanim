import { NextRequest, NextResponse } from "next/server";
import { checkJob, forge, jobView, running, startMake } from "@/lib/forge";

export const runtime = "nodejs";

type Params = { params: Promise<{ id: string }> };

/** GET: where the job stands. */
export async function GET(_request: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    return NextResponse.json(await jobView(id));
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 404 });
  }
}

/**
 * POST {action}: make (continue / approve a review), revise {note}, restyle {style}.
 * revise and restyle rewind the job, then make runs again from there.
 */
export async function POST(request: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    checkJob(id);
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message }, { status: 404 });
  }
  if (running(id)) return NextResponse.json({ error: "the job is running; wait for it to stop" }, { status: 409 });
  const body = await request.json().catch(() => ({}));
  const action = String(body.action ?? "make");
  let result: unknown = null;
  if (action === "revise" || action === "restyle") {
    const value = String(action === "revise" ? body.note ?? "" : body.style ?? "").trim();
    if (!value) return NextResponse.json({ error: `${action} needs ${action === "revise" ? "a note" : "a style"}` }, { status: 400 });
    const done = await forge([action, id, value]);
    if (done.code !== 0) return NextResponse.json({ error: done.err.trim() || done.out.trim() }, { status: 400 });
    try {
      result = JSON.parse(done.out);
    } catch {
      result = done.out;
    }
    if (body.run === false) return NextResponse.json({ id, result });
  } else if (action !== "make") {
    return NextResponse.json({ error: `unknown action ${action}` }, { status: 400 });
  }
  const started = startMake(id, {
    until: typeof body.until === "string" ? body.until : undefined,
    quality: typeof body.quality === "string" ? body.quality : undefined,
    accept: Boolean(body.accept),
  });
  return NextResponse.json({ id, result, started });
}
