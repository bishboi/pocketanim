import { NextRequest, NextResponse } from "next/server";
import { readFile, realpath } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { REPO } from "@/lib/pocketanim";

export const runtime = "nodejs";

/** Where the pictures the AI made are kept: the lecture engine's caches (illustrations and diagrams the image models
 * made) and the uploaded documents' folders (the book's figures, lib/document.ts). Nothing else is served. */
async function allowed(file: string): Promise<boolean> {
  const inside = (root: string, test: (first: string) => boolean = () => true) => {
    const rel = path.relative(root, file);
    return !!rel && !rel.startsWith("..") && !path.isAbsolute(rel) && test(rel.split(path.sep)[0]);
  };
  const cache = await realpath(path.join(REPO, "harness", "lecture", ".cache")).catch(() => null);
  const tmp = await realpath(tmpdir()).catch(() => tmpdir());
  return (!!cache && inside(cache)) || inside(tmp, (first) => first.startsWith("panim-doc-"));
}

/**
 * GET ?file=<path>: a picture the AI made for a lecture (lib/costs.ts AiPicture): an illustration or a diagram an
 * image model made, or a book's figure (PNG, JPEG, WebP), as it is.
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const asked = params.get("file") ?? "";
  if (!/\.(png|jpe?g|webp)$/i.test(asked)) return NextResponse.json({ error: "not a picture" }, { status: 400 });
  let file: string;
  try {
    file = await realpath(asked);
  } catch {
    return NextResponse.json({ error: "missing picture" }, { status: 404 });
  }
  if (!(await allowed(file))) return NextResponse.json({ error: "not a picture the AI made" }, { status: 403 });
  try {
    const raster = /\.(png|jpe?g|webp)$/i.exec(file)?.[1]?.toLowerCase();
    const type = raster === "png" ? "image/png" : raster === "webp" ? "image/webp" : "image/jpeg";
    return new NextResponse(new Uint8Array(await readFile(file)), {
      headers: { "Content-Type": type, "Cache-Control": "private, max-age=3600" },
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
