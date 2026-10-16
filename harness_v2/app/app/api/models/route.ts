import { NextRequest, NextResponse } from "next/server";
import { checkModel } from "@/lib/llm";

export const runtime = "nodejs";

/** POST {model}: its prices and context, and whether a one-word call to it works now. */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const model = String(body?.model ?? "").trim();
  if (!model) return NextResponse.json({ error: "no model" }, { status: 400 });
  return NextResponse.json({ model, ...(await checkModel(model)) });
}
