import { NextRequest, NextResponse } from "next/server";
import { generate, usingFixture } from "@/lib/model";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    if (!body?.content?.trim() && !body?.instruction?.trim()) {
      return NextResponse.json({ error: "nothing to generate from" }, { status: 400 });
    }
    const result = await generate({
      content: String(body.content ?? ""),
      templateId: String(body.templateId ?? "explainer"),
      previousSource: body.previousSource ? String(body.previousSource) : undefined,
      instruction: body.instruction ? String(body.instruction) : undefined,
    });
    return NextResponse.json({ ...result, fixture: usingFixture() });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 500 },
    );
  }
}
