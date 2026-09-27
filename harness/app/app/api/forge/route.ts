import { NextRequest, NextResponse } from "next/server";
import { documentPdf } from "@/lib/document";
import { forge, libraries, startMake } from "@/lib/forge";

export const runtime = "nodejs";

/** GET: the jobs and the libraries. POST: `forge new` then `forge make` in the background. */
export async function GET() {
  const listed = await forge(["list"]);
  let jobs: unknown[] = [];
  try {
    jobs = JSON.parse(listed.out || "[]");
  } catch {}
  return NextResponse.json({ jobs, registry: await libraries() });
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const str = (v: unknown) => (typeof v === "string" ? v.trim() : "");
  const id = str(body.id).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);
  if (!id) return NextResponse.json({ error: "a job needs an id" }, { status: 400 });
  if (!str(body.template) || !str(body.style)) {
    return NextResponse.json({ error: "choose a template and a style" }, { status: 400 });
  }
  let pdf: string | null = null;
  if (str(body.documentId)) {
    try {
      pdf = documentPdf(str(body.documentId));
    } catch (error) {
      return NextResponse.json({ error: (error as Error).message }, { status: 400 });
    }
  }
  if (!str(body.brief) && !pdf) {
    return NextResponse.json({ error: "paste the content, or upload a lecture PDF" }, { status: 400 });
  }
  const args = ["new", id, "--template", str(body.template), "--style", str(body.style)];
  if (str(body.brief)) args.push("--brief", str(body.brief));
  if (pdf) args.push("--source", pdf);
  if (str(body.title)) args.push("--title", str(body.title));
  if (str(body.subtitle)) args.push("--subtitle", str(body.subtitle));
  if (str(body.region)) args.push("--region", str(body.region));
  if (Number(body.minutes) > 0) args.push("--minutes", String(Number(body.minutes)));
  if (/^[lmh]$/.test(str(body.quality))) args.push("--quality", str(body.quality));
  if (body.reviewOutline) args.push("--review-outline");
  if (body.reviewPreview) args.push("--review-preview");
  if (!body.phone) args.push("--no-phone");
  const made = await forge(args);
  if (made.code !== 0) {
    return NextResponse.json({ error: made.err.trim() || made.out.trim() || `forge new exited ${made.code}` }, { status: 400 });
  }
  startMake(id, { until: str(body.until) || undefined });
  return NextResponse.json({ id });
}
