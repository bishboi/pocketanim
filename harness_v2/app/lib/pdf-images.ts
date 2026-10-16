/**
 * The pictures a PDF carries, cut out of it directly (pdf.js, no canvas): every raster image each page paints, with
 * where it lands on the page (fractions of the page, top-left origin) and its pixels as a PNG. A figure block whose
 * picture Datalab did not return takes the picture painted inside its box (datalab.ts). A figure drawn as vector
 * lines has no raster image and is not found here.
 */

import { deflateSync } from "node:zlib";

export type PdfImage = { page: number; box: [number, number, number, number]; width: number; height: number; png: Buffer };

/** Images smaller than this (either side, in pixels) are icons and rules, not figures. */
const MIN_SIDE = 24;

export async function pdfImages(bytes: Uint8Array): Promise<PdfImage[]> {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const { OPS, Util } = pdfjs;
  const doc = await pdfjs.getDocument({ data: new Uint8Array(bytes), isOffscreenCanvasSupported: false, useSystemFonts: true }).promise;
  const out: PdfImage[] = [];
  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);
    const view = page.getViewport({ scale: 1 });
    const ops = await page.getOperatorList();
    let ctm = [1, 0, 0, 1, 0, 0];
    const stack: number[][] = [];
    for (let i = 0; i < ops.fnArray.length; i++) {
      const fn = ops.fnArray[i];
      const args = ops.argsArray[i] as unknown[];
      if (fn === OPS.save) stack.push(ctm);
      else if (fn === OPS.restore) ctm = stack.pop() ?? [1, 0, 0, 1, 0, 0];
      else if (fn === OPS.transform) ctm = Util.transform(ctm, args as number[]);
      else if (fn === OPS.paintFormXObjectBegin) {
        stack.push(ctm);
        if (Array.isArray(args[0]) && args[0].length === 6) ctm = Util.transform(ctm, args[0] as number[]);
      } else if (fn === OPS.paintFormXObjectEnd) ctm = stack.pop() ?? [1, 0, 0, 1, 0, 0];
      else if (fn === OPS.paintImageXObject || fn === OPS.paintInlineImageXObject) {
        const image = fn === OPS.paintInlineImageXObject ? args[0] : await objectOf(page, String(args[0]));
        const png = image ? toPng(image as RawImage) : null;
        if (!png) continue;
        // The image fills the unit square under the current matrix; its corners on the page, top-left origin.
        const m = Util.transform(view.transform, ctm);
        const xs: number[] = [], ys: number[] = [];
        for (const [x, y] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
          xs.push(m[0] * x + m[2] * y + m[4]);
          ys.push(m[1] * x + m[3] * y + m[5]);
        }
        out.push({ page: p - 1, width: png.width, height: png.height, png: png.data,
          box: [Math.min(...xs) / view.width, Math.min(...ys) / view.height, Math.max(...xs) / view.width, Math.max(...ys) / view.height] });
      }
    }
    page.cleanup();
  }
  await doc.destroy();
  return out;
}

type RawImage = { width: number; height: number; kind?: number; data?: Uint8Array | Uint8ClampedArray };

function objectOf(page: { objs: { get: (id: string, cb: (v: unknown) => void) => void }; commonObjs: { get: (id: string, cb: (v: unknown) => void) => void } },
  id: string): Promise<unknown> {
  const store = id.startsWith("g_") ? page.commonObjs : page.objs;
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), 5000);
    try {
      store.get(id, (v) => {
        clearTimeout(timer);
        resolve(v);
      });
    } catch {
      clearTimeout(timer);
      resolve(null);
    }
  });
}

/** pdf.js's decoded pixels (1-bit grey, RGB or RGBA) as a PNG. */
function toPng(img: RawImage): { data: Buffer; width: number; height: number } | null {
  const { width: w, height: h, data } = img;
  if (!data || !w || !h || w < MIN_SIDE || h < MIN_SIDE) return null;
  const rgba = Buffer.alloc(w * h * 4);
  if (img.kind === 3 && data.length >= w * h * 4) {
    rgba.set(data.subarray(0, w * h * 4));
  } else if (img.kind === 2 && data.length >= w * h * 3) {
    for (let i = 0, j = 0; i < w * h; i++, j += 3) rgba.set([data[j], data[j + 1], data[j + 2], 255], i * 4);
  } else if (img.kind === 1) {
    const row = (w + 7) >> 3;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const v = (data[y * row + (x >> 3)] >> (7 - (x & 7))) & 1 ? 255 : 0;
      rgba.set([v, v, v, 255], (y * w + x) * 4);
    }
  } else return null;
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) rgba.copy(raw, y * (w * 4 + 1) + 1, y * w * 4, (y + 1) * w * 4);
  const chunk = (type: string, body: Buffer) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(body.length);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(Buffer.concat([Buffer.from(type), body])));
    return Buffer.concat([len, Buffer.from(type), body, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(w, 0);
  header.writeUInt32BE(h, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return { width: w, height: h, data: Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]) };
}

let table: Uint32Array | undefined;
function crc32(buf: Buffer): number {
  if (!table) {
    table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
  }
  let c = 0xffffffff;
  for (const b of buf) c = table[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
