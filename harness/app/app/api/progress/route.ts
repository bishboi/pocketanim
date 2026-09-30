import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import { progressFile } from "@/lib/pocketanim";

export const runtime = "nodejs";

/** How far a build has got: {phase: "voice" | "render", done, total}, or {} before it starts. */
export async function GET(request: NextRequest) {
  const file = progressFile(request.nextUrl.searchParams.get("id") ?? "");
  if (!file) return NextResponse.json({ error: "bad id" }, { status: 400 });
  try {
    return NextResponse.json(JSON.parse(await readFile(file, "utf8")));
  } catch {
    return NextResponse.json({});
  }
}
