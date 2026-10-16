/**
 * The book as Datalab reads it: its convert API with output_format=json, which gives every block of every page with
 * its own id ("/page/3/Text/7"), its type (SectionHeader, Text, Figure, Caption, ListGroup, Table...), its content as
 * HTML and its bounding box. That JSON is the book from here on: the planner names its block ids, the PDF view draws
 * its boxes. Nothing is rewritten into another form.
 *
 * Each PDF is converted once (cached by its content's hash in .data/datalab/). Without DATALAB_API_KEY, an offline
 * reader makes JSON of the same shape from the PDF's own text positions (pdf.js): lines grouped into paragraphs, a
 * larger font as a SectionHeader. It has no figures and no bold, and is there so the harness runs with no key.
 */

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { DATA } from "./store";

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
  // Figure images: in each picture block's "images" ({block id: base64}), or the result's ("_page_0_Picture_1.jpeg").
  const figures: Record<string, string> = {};
  await mkdir(path.join(dir, "figures"), { recursive: true });
  const save = async (blockId: string, name: string, b64: string) => {
    const ext = (/\.(png|jpe?g|webp)$/i.exec(name)?.[1] ?? "jpeg").toLowerCase().replace("jpg", "jpeg");
    const file = path.join(dir, "figures", `${blockId.replace(/[^\w]+/g, "_")}.${ext}`);
    await writeFile(file, Buffer.from(b64, "base64"));
    figures[blockId] = file;
  };
  const walk = async (b: RawBlock) => {
    for (const [id, data] of Object.entries(b.images ?? {})) if (typeof data === "string") await save(id, id, data);
    for (const c of b.children ?? []) await walk(c);
  };
  await walk(result.json);
  for (const [name, data] of Object.entries(result.images ?? {})) {
    // "_page_0_Picture_1.jpeg" names the block "/page/0/Picture/1".
    const m = /_page_(\d+)_([A-Za-z]+)_(\d+)/.exec(name);
    const id = m ? `/page/${m[1]}/${m[2]}/${m[3]}` : name;
    if (!figures[id]) await save(id, name, data);
  }
  const pages = (result.json.children ?? []).filter((c) => c.block_type === "Page").length || result.page_count || 0;
  return { source: key ? "datalab" : "offline", json: result.json, pages, figures };
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
      result = { ...(await download.json()), ...Object.fromEntries(Object.entries(result).filter(([, v]) => v !== null && v !== undefined)) };
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
  return { json: { id: "/document/0", block_type: "Document", children: pages } as RawBlock, images: {}, page_count: doc.numPages };
}

function escape(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
