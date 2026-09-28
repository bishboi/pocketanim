import { NextRequest, NextResponse } from "next/server";
import { spawn } from "node:child_process";
import path from "node:path";
import { REPO, python } from "@/lib/pocketanim";

export const runtime = "nodejs";
export const maxDuration = 900;

const SCRIPTS: Record<string, string> = {
  icons: "fetch_icons.py",
  gazetteer: "fetch_gazetteer.py",
  voice: "fetch_voice.py",
  openstax: "fetch_openstax.py",
};

/** POST {what: "icons" | "gazetteer" | "voice" | "openstax"}: run the download script, wait, report its output. */
export async function POST(request: NextRequest) {
  const { what } = await request.json().catch(() => ({ what: "" }));
  const script = SCRIPTS[String(what)];
  if (!script) return NextResponse.json({ error: "unknown download" }, { status: 400 });
  const result = await new Promise<{ code: number; out: string }>((resolve) => {
    const child = spawn(python(), [path.join(REPO, "harness", "scripts", script)], { cwd: REPO });
    let out = "";
    child.stdout.on("data", (c) => (out += c.toString()));
    child.stderr.on("data", (c) => (out += c.toString()));
    child.on("close", (code) => resolve({ code: code ?? -1, out }));
    child.on("error", (e) => resolve({ code: -1, out: String(e) }));
  });
  return NextResponse.json({ ok: result.code === 0, output: result.out.trim().split("\n").slice(-8).join("\n") },
    { status: result.code === 0 ? 200 : 500 });
}
