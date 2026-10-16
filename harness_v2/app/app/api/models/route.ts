import { NextRequest, NextResponse } from "next/server";
import { checkModel } from "@/lib/llm";

export const runtime = "nodejs";

/** POST {model, kind}: its prices and context, and whether a call works now (an image model: whether an image comes back). */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const model = String(body?.model ?? "").trim();
  if (!model) return NextResponse.json({ error: "no model" }, { status: 400 });
  const kind = ["text", "vision", "image", "decision"].includes(body?.kind) ? body.kind : "text";
  return NextResponse.json({ model, ...(await checkModel(model, kind)) });
}
