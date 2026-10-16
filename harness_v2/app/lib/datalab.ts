/**
 * The book as Datalab reads it: its convert API with output_format=json, which gives every block of every page with
 * its own id ("/page/3/Text/7"), its type (SectionHeader, Text, Figure, Caption, ListGroup, Table...), its content as
 * HTML and its bounding box. That JSON is the book from here on: the planner names its block ids, the PDF view draws
 * its boxes. Nothing is rewritten into another form.
 *
 * Each PDF is converted once (cached by its content's hash in .data/datalab/). Without DATALAB_API_KEY, an offline
 * reader makes JSON of the same shape from the PDF's own text positions (pdf.js): lines grouped into paragraphs, a
 * larger font as a SectionHeader, and each picture a page paints as a Picture block (pdf-images.ts). It has no
 * captions or bold, and figures drawn as lines are missed; it is there so the harness runs with no key.
 */

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { DATA } from "./store";
import { pdfImages } from "./pdf-images";

const HOST = (process.env.DATALAB_HOST || "https://www.datalab.to").replace(/\/$/, "");

/** A block of Datalab's JSON (the fields v2 reads). */
export type RawBlock = {
  id: string;
  block_type: string;
  html?: string;
  bbox?: number[];
  polygon?: number[][];
  children?: RawBlock[] | null;
  images?: Record<string, string> | null;
  section_hierarchy?: Record<string, string> | null;
};

export type Converted = { source: "datalab" | "offline"; json: RawBlock; pages: number; figures: Record<string, string> };

/** The PDF converted, from the cache when it was before; figure images written to `dir/figures/<block>.<ext>`. */
export async function convertPdf(bytes: Uint8Array, dir: string): Promise<Converted> {
  const hash = createHash("sha256").update(bytes).digest("hex").slice(0, 20);
  const key = process.env.DATALAB_API_KEY?.trim();
  const cache = path.join(DATA, "datalab", `${hash}${key ? "" : ".offline"}.json`);
  let result: { json: RawBlock; images: Record<string, string>; page_count?: number };
  if (existsSync(cache)) {
    result = JSON.parse(await readFile(cache, "utf8"));
  } else {
    result = key ? await fromDatalab(bytes, key) : await offline(bytes);
    await mkdir(path.dirname(cache), { recursive: true });
    await writeFile(cache, JSON.stringify(result), "utf8");
  }
  const { figures, report } = await extractFigures(result, dir, bytes);
  await writeFile(path.join(dir, "figure-report.json"), JSON.stringify(report, null, 2), "utf8");
  const pages = (result.json.children ?? []).filter((c) => c.block_type === "Page").length || result.page_count || 0;
  return { source: key ? "datalab" : "offline", json: result.json, pages, figures };
}

/** What the figure search found in a Datalab result: shown on the page when a book has figure blocks but no pictures. */
export type FigureReport = { figureBlocks: number; matched: number; blockImages: number; topImages: number; imgTags: number;
  /** Figure blocks whose picture was cut out of the PDF itself (Datalab returned none for them). */
  cut: number; unmatched: string[]; note: string };

/**
 * The figure pictures of a Datalab result, each saved under the block it belongs to (dir/figures/<block>.<ext>).
 * A picture is looked for everywhere Datalab may put it, as its API's JSON has been seen to differ:
 *   - a block's own "images" ({key: base64}): the key a block id ("/page/0/Picture/1"), or any name (then the
 *     block itself);
 *   - a block's HTML: <img src="data:..."> (the picture itself) or <img src="name"> (a name in the result's images);
 *   - the result's "images" ({name: base64}, also under json.images): "_page_0_Picture_1.jpeg" names its block;
 *   - last, the PDF itself (pdf-images.ts): the picture the page paints inside the block's box, when Datalab
 *     returned none for it. A figure drawn as vector lines has none and stays without a picture.
 */
export async function extractFigures(result: { json: RawBlock; images?: Record<string, string> | null }, dir: string,
  pdf?: Uint8Array, known: Record<string, string> = {}): Promise<{ figures: Record<string, string>; report: FigureReport }> {
  const figures: Record<string, string> = { ...known };
  await mkdir(path.join(dir, "figures"), { recursive: true });
  const top: Record<string, string> = { ...((result.json as { images?: Record<string, string> }).images ?? {}), ...(result.images ?? {}) };
  const report: FigureReport = { figureBlocks: 0, matched: 0, blockImages: 0, topImages: Object.keys(top).length, imgTags: 0, cut: 0, unmatched: [], note: "" };
  const save = async (blockId: string, name: string, data: string) => {
    if (figures[blockId] || typeof data !== "string" || !data) return;
    const uri = /^data:image\/(\w+);base64,/.exec(data);
    const b64 = uri ? data.slice(uri[0].length) : data;
    const ext = ((uri?.[1] ?? /\.(png|jpe?g|webp|gif)$/i.exec(name)?.[1] ?? "jpeg").toLowerCase()).replace("jpg", "jpeg");
    const file = path.join(dir, "figures", `${blockId.replace(/[^\w]+/g, "_")}.${ext}`);
    await writeFile(file, Buffer.from(b64, "base64"));
    figures[blockId] = file;
  };
  const byName = (src: string) => top[src] ?? top[path.basename(src)] ?? Object.entries(top).find(([k]) => k.endsWith(path.basename(src)))?.[1];
  const walk = async (b: RawBlock) => {
    const isFigure = /Figure|Picture/.test(b.block_type);
    if (isFigure) report.figureBlocks += 1;
    for (const [key, data] of Object.entries(b.images ?? {})) {
      report.blockImages += 1;
      await save(key.startsWith("/page/") ? key : b.id, key, data as string);
    }
    for (const m of (b.html ?? "").matchAll(/<img[^>]*\ssrc=["']([^"']+)["']/gi)) {
      report.imgTags += 1;
      const src = m[1];
      if (src.startsWith("data:image/")) await save(b.id, src, src);
      else if (byName(src)) await save(b.id, src, byName(src)!);
    }
    for (const c of b.children ?? []) await walk(c);
    if (isFigure) {
      if (figures[b.id] || (b.children ?? []).some((c) => figures[c.id])) report.matched += 1;
    }
  };
  // The result's named pictures first by their names ("_page_0_Picture_1.jpeg" is /page/0/Picture/1), then the blocks.
  for (const [name, data] of Object.entries(top)) {
    const m = /_page_(\d+)_([A-Za-z]+)_(\d+)/.exec(name);
    if (m) await save(`/page/${m[1]}/${m[2]}/${m[3]}`, name, data);
  }
  await walk(result.json);
  if (pdf) await cutFromPdf(result.json, figures, dir, pdf, report);
  const unmatchedBlocks: string[] = [];
  const find = (b: RawBlock) => {
    if (/Figure|Picture/.test(b.block_type) && !figures[b.id] && !(b.children ?? []).some((c) => figures[c.id])) unmatchedBlocks.push(b.id);
    (b.children ?? []).forEach(find);
  };
  find(result.json);
  report.unmatched = unmatchedBlocks.slice(0, 20);
  report.note = !report.figureBlocks ? "no figure blocks"
    : !report.unmatched.length ? "every figure block has its picture"
      : `${report.unmatched.length} figure block(s) have no picture found for them; Datalab's result has ${report.blockImages} block image(s), ${report.topImages} named picture(s), ${report.imgTags} <img> tag(s)${!report.blockImages && !report.topImages && !report.imgTags ? " (it was converted without pictures)" : ""}${pdf ? "; the PDF paints no picture inside their boxes (drawn as lines?)" : ""}`;
  if (report.cut) report.note += ` (${report.cut} cut out of the PDF itself: Datalab returned no picture for them)`;
  return { figures, report };
}

/**
 * Figure blocks still without a picture take the raster image the PDF paints inside their box (the largest overlap),
 * cut out of the PDF itself. A group (a FigureGroup with its Figure) gets one picture, not two.
 */
async function cutFromPdf(json: RawBlock, figures: Record<string, string>, dir: string, pdf: Uint8Array, report: FigureReport) {
  const pages = (json.children ?? []).filter((c) => c.block_type === "Page");
  const wanting: { id: string; page: number; box: number[] }[] = [];
  // `covered`: inside a figure (group) that has its picture or is being given one; a page is never covered.
  const visit = (b: RawBlock, page: number, covered: boolean) => {
    const figure = /Figure|Picture/.test(b.block_type);
    const has = figure && (!!figures[b.id] || (b.children ?? []).some((c) => figures[c.id]));
    if (figure && !has && !covered && b.bbox) {
      const [px0, py0, px1, py1] = pages[page]?.bbox ?? [0, 0, 1, 1];
      const w = Math.max(1e-6, px1 - px0), h = Math.max(1e-6, py1 - py0);
      wanting.push({ id: b.id, page, box: [(b.bbox[0] - px0) / w, (b.bbox[1] - py0) / h, (b.bbox[2] - px0) / w, (b.bbox[3] - py0) / h] });
      covered = true;
    }
    for (const c of b.children ?? []) visit(c, page, covered || has);
  };
  pages.forEach((p, i) => visit(p, i, false));
  if (!wanting.length) return;
  let images: Awaited<ReturnType<typeof pdfImages>>;
  try {
    images = await pdfImages(pdf);
  } catch (error) {
    console.error(`the PDF's pictures could not be read: ${(error as Error).message}`);
    return;
  }
  const area = (b: number[]) => Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
  for (const f of wanting) {
    let best: (typeof images)[number] | undefined;
    let most = 0;
    for (const im of images.filter((x) => x.page === f.page)) {
      const inter = area([Math.max(f.box[0], im.box[0]), Math.max(f.box[1], im.box[1]), Math.min(f.box[2], im.box[2]), Math.min(f.box[3], im.box[3])]);
      // Most of the image inside the figure's box, or most of the box covered by the image.
      if (inter > most && (inter >= 0.5 * area(im.box) || inter >= 0.5 * area(f.box))) {
        best = im;
        most = inter;
      }
    }
    if (!best) continue;
    const file = path.join(dir, "figures", `${f.id.replace(/[^\w]+/g, "_")}.png`);
    await writeFile(file, best.png);
    figures[f.id] = file;
    report.cut += 1;
  }
}

/**
 * A book's figures found again from what was kept (Datalab's cached result, else its book.json): for a book
 * uploaded before the figure search knew a place Datalab puts pictures. Writes figures.json and figure-report.json.
 */
export async function refreshFigures(docDirPath: string): Promise<FigureReport | null> {
  try {
    const pdf = await readFile(path.join(docDirPath, "source.pdf"));
    const hash = createHash("sha256").update(pdf).digest("hex").slice(0, 20);
    const cache = path.join(DATA, "datalab", `${hash}.json`);
    const result = existsSync(cache) ? JSON.parse(await readFile(cache, "utf8"))
      : { json: JSON.parse(await readFile(path.join(docDirPath, "book.json"), "utf8")), images: {} };
    // Pictures already found (an imported book's, an earlier search's) are kept; the search only adds.
    const known: Record<string, string> = JSON.parse(await readFile(path.join(docDirPath, "figures.json"), "utf8").catch(() => "{}"));
    const kept = Object.fromEntries(Object.entries(known).filter(([, file]) => existsSync(file)));
    const { figures, report } = await extractFigures(result, docDirPath, pdf, kept);
    await writeFile(path.join(docDirPath, "figures.json"), JSON.stringify({ ...kept, ...figures }), "utf8");
    await writeFile(path.join(docDirPath, "figure-report.json"), JSON.stringify(report, null, 2), "utf8");
    if (report.unmatched.length) console.warn(`figures of ${docDirPath}: ${report.note}`);
    return report;
  } catch (error) {
    console.error(`figures could not be found again for ${docDirPath}: ${(error as Error).message}`);
    return null;
  }
}

async function fromDatalab(bytes: Uint8Array, key: string) {
  const form = new FormData();
  form.append("file", new Blob([new Uint8Array(bytes)], { type: "application/pdf" }), "book.pdf");
  form.append("output_format", "json");
  form.append("mode", process.env.DATALAB_MODE || "balanced");
  form.append("disable_image_extraction", "false");
  const started = await fetch(`${HOST}/api/v1/convert`, { method: "POST", headers: { "X-Api-Key": key }, body: form });
  const start = await started.json() as { success?: boolean; error?: string; request_check_url?: string };
  if (!started.ok || !start.request_check_url) throw new Error(`Datalab refused the PDF: ${start.error ?? started.status}`);
  const check = start.request_check_url.startsWith("http") ? start.request_check_url : `${HOST}/${start.request_check_url.replace(/^\//, "")}`;
  const deadline = Date.now() + 20 * 60_000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2500));
    let result = await (await fetch(check, { headers: { "X-Api-Key": key } })).json() as Record<string, unknown>;
    if (result.success === false || result.status === "failed") throw new Error(`Datalab could not convert the PDF: ${result.error ?? "failed"}`);
    if (result.status !== "complete") continue;
    if (typeof result.result_url === "string") {
      const download = await fetch(result.result_url);
      if (!download.ok) throw new Error(`Datalab's result could not be downloaded (${download.status})`);
      // The downloaded result wins; the status reply only fills what it lacks (an empty "images": {} there must not
      // hide the downloaded pictures).
      const full = (await download.json()) as Record<string, unknown>;
      const empty = (v: unknown) => v === null || v === undefined || (typeof v === "object" && !Array.isArray(v) && !Object.keys(v as object).length);
      for (const [k, v] of Object.entries(result)) if (empty(full[k]) && !empty(v)) full[k] = v;
      result = full;
    }
    let json = result.json as RawBlock | string | undefined;
    if (typeof json === "string") json = JSON.parse(json) as RawBlock;
    if (!json) throw new Error("Datalab's result had no JSON");
    return { json, images: (result.images ?? {}) as Record<string, string>, page_count: Number(result.page_count) || undefined };
  }
  throw new Error("Datalab did not finish converting the PDF in 20 minutes");
}

/** The PDF's own text, as Datalab-shaped JSON: a Page block per page, its lines grouped into Text and SectionHeader blocks. */
async function offline(bytes: Uint8Array) {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const doc = await pdfjs.getDocument({ data: new Uint8Array(bytes), useSystemFonts: true }).promise;
  const pages: RawBlock[] = [];
  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);
    const view = page.getViewport({ scale: 1 });
    const content = await page.getTextContent();
    type Line = { text: string; x0: number; x1: number; top: number; bottom: number; size: number };
    const lines: Line[] = [];
    for (const raw of content.items) {
      const it = raw as { str?: string; transform?: number[]; width?: number; height?: number };
      if (!it.str?.trim() || !it.transform) continue;
      const size = Math.hypot(it.transform[2], it.transform[3]);
      const top = view.height - it.transform[5] - size;
      const last = lines[lines.length - 1];
      if (last && Math.abs(last.top - top) < size * 0.5) {
        last.text += (it.str.startsWith(" ") || last.text.endsWith(" ") ? "" : " ") + it.str;
        last.x1 = Math.max(last.x1, it.transform[4] + (it.width ?? 0));
        last.x0 = Math.min(last.x0, it.transform[4]);
      } else {
        lines.push({ text: it.str, x0: it.transform[4], x1: it.transform[4] + (it.width ?? 0), top, bottom: top + size * 1.2, size });
      }
    }
    const sizes = lines.map((l) => l.size).sort((a, b) => a - b);
    const body = sizes[Math.floor(sizes.length / 2)] ?? 10;
    const children: RawBlock[] = [];
    let group: Line[] = [];
    const flush = () => {
      if (!group.length) return;
      const heading = group[0].size > body * 1.2;
      const type = heading ? "SectionHeader" : "Text";
      const text = group.map((l) => l.text.trim()).join(" ").replace(/\s+/g, " ");
      const html = heading ? `<h2>${escape(text)}</h2>` : `<p>${escape(text)}</p>`;
      const x0 = Math.min(...group.map((l) => l.x0)), x1 = Math.max(...group.map((l) => l.x1));
      const y0 = group[0].top, y1 = group[group.length - 1].bottom;
      children.push({ id: `/page/${p - 1}/${type}/${children.length}`, block_type: type, html, bbox: [x0, y0, x1, y1],
        polygon: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], children: null });
      group = [];
    };
    for (const line of lines) {
      const prev = group[group.length - 1];
      const gap = prev ? line.top - prev.bottom : 0;
      const sizeChange = prev && Math.abs(line.size - prev.size) > body * 0.15;
      if (prev && (gap > body * 0.6 || sizeChange)) flush();
      group.push(line);
    }
    flush();
    pages.push({ id: `/page/${p - 1}/Page/0`, block_type: "Page", html: "", bbox: [0, 0, view.width, view.height],
      polygon: [[0, 0], [view.width, 0], [view.width, view.height], [0, view.height]], children });
  }
  // The pictures the pages paint, as Picture blocks in reading order (by their top), named as Datalab names them.
  const images: Record<string, string> = {};
  const counts = new Map<number, number>();
  for (const im of await pdfImages(bytes).catch(() => [])) {
    const page = pages[im.page];
    if (!page?.bbox) continue;
    const [, , w, h] = page.bbox;
    const k = counts.get(im.page) ?? 0;
    counts.set(im.page, k + 1);
    const box = [im.box[0] * w, im.box[1] * h, im.box[2] * w, im.box[3] * h];
    page.children = [...(page.children ?? []), { id: `/page/${im.page}/Picture/${k}`, block_type: "Picture", html: "", bbox: box,
      polygon: [[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]], children: null }]
      .sort((x, y) => (x.bbox?.[1] ?? 0) - (y.bbox?.[1] ?? 0));
    images[`_page_${im.page}_Picture_${k}.png`] = im.png.toString("base64");
  }
  return { json: { id: "/document/0", block_type: "Document", children: pages } as RawBlock, images, page_count: doc.numPages };
}

function escape(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
