import { NextResponse } from "next/server";
import { spawn } from "node:child_process";
import path from "node:path";
import { REPO, python } from "@/lib/pocketanim";

export const runtime = "nodejs";
export const maxDuration = 300;

/**
 * POST: a real call to the image model (genimage.py --check), never from the cache, made the way a lecture makes
 * its pictures (the same environment, key and model). Reports whether it works and why not, which model, how long
 * and what it cost, and the picture as the model made it.
 */
export async function POST() {
  const result = await new Promise<{ code: number; out: string; err: string }>((resolve) => {
    const child = spawn(python(), [path.join(REPO, "harness", "lecture", "genimage.py"), "--check"], { cwd: REPO });
    let out = "";
    let err = "";
    child.stdout.on("data", (c) => (out += c.toString()));
    child.stderr.on("data", (c) => (err += c.toString()));
    child.on("close", (code) => resolve({ code: code ?? -1, out, err }));
    child.on("error", (e) => resolve({ code: -1, out: "", err: String(e) }));
  });
  try {
    return NextResponse.json(JSON.parse(result.out.trim().split("\n").pop() || ""));
  } catch {
    return NextResponse.json({ ok: false, model: process.env.PANIM_IMAGE_MODEL || "google/gemini-2.5-flash-image",
      error: `the check did not run: ${result.err.trim().split("\n").slice(-3).join(" ") || `exit ${result.code}`}` });
  }
}
