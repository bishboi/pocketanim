import { NextRequest, NextResponse } from "next/server";
import { spawn } from "node:child_process";
import { readFile, realpath, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { REPO, python } from "@/lib/pocketanim";

export const runtime = "nodejs";

/** Where the pictures the AI made are kept: the lecture engine's caches (drawings, illustrations) and the uploaded
 * documents' folders (book figures redrawn as SVG beside them, lib/document.ts). Nothing else is served. */
async function allowed(file: string): Promise<boolean> {
  const inside = (root: string, test: (first: string) => boolean = () => true) => {
    const rel = path.relative(root, file);
    return !!rel && !rel.startsWith("..") && !path.isAbsolute(rel) && test(rel.split(path.sep)[0]);
  };
  const cache = await realpath(path.join(REPO, "harness", "lecture", ".cache")).catch(() => null);
  const tmp = await realpath(tmpdir()).catch(() => tmpdir());
  return (!!cache && inside(cache)) || inside(tmp, (first) => first.startsWith("panim-doc-"));
}

const painted = new Map<string, string>();

/** An SVG painted as the board shows it (scripts/board_svg.py), kept per file, change and style. */
function paint(file: string, style: string, stamp: number): Promise<string> {
  const key = `${file}|${stamp}|${style}`;
  const kept = painted.get(key);
  if (kept) return Promise.resolve(kept);
  return new Promise((resolve, reject) => {
    const child = spawn(python(), [path.join(REPO, "harness", "scripts", "board_svg.py"), style, file], { cwd: REPO });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0 || !out.includes("<svg")) return reject(new Error(err.slice(-300) || "could not paint the drawing"));
      if (painted.size > 200) painted.clear();
      painted.set(key, out);
      resolve(out);
    });
  });
}

/**
 * GET ?file=<path>&style=<style>: a picture the AI made for a lecture (lib/costs.ts AiPicture): an SVG it drew,
 * painted in the lecture's colours on its board, or an illustration an image model drew (PNG).
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const asked = params.get("file") ?? "";
  const style = (params.get("style") ?? "chalkboard").replace(/[^a-z_-]/gi, "") || "chalkboard";
  if (!/\.(svg|png)$/i.test(asked)) return NextResponse.json({ error: "not a picture" }, { status: 400 });
  let file: string;
  try {
    file = await realpath(asked);
  } catch {
    return NextResponse.json({ error: "missing picture" }, { status: 404 });
  }
  if (!(await allowed(file))) return NextResponse.json({ error: "not a picture the AI made" }, { status: 403 });
  try {
    if (file.toLowerCase().endsWith(".png")) {
      return new NextResponse(new Uint8Array(await readFile(file)), {
        headers: { "Content-Type": "image/png", "Cache-Control": "private, max-age=3600" },
      });
    }
    const svg = await paint(file, style, (await stat(file)).mtimeMs);
    return new NextResponse(svg, {
      headers: { "Content-Type": "image/svg+xml", "Cache-Control": "private, max-age=3600",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'" },
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
