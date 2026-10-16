"use client";

/**
 * The uploaded PDF, drawn page by page (pdf.js), with the parts of the book a step works from highlighted on it.
 *
 * The book reached the model as Markdown (Datalab or pypdf), so its words are found again in the PDF's own text:
 * a range (a section's slice of the book) by a run of five words near its start and near its end, a term (a
 * heading, a bold term, a box, a figure's caption) by its first words inside that range. What cannot be found (a
 * scanned page, a word the reader changed) is counted and said, never guessed.
 */

import { useEffect, useMemo, useRef, useState } from "react";

export type Mark = { text: string; color: string; label?: string };
export type Marks = { ranges: Mark[]; terms: Mark[] };

type Item = { page: number; left: number; top: number; width: number; height: number };
type Word = { w: string; item: number };
type PageInfo = { width: number; height: number; canvas: HTMLCanvasElement };

const GRAM = 5;

function tokens(text: string): string[] {
  return (text
    .replace(/\[FIGURE[^\]:]*:/g, " ")
    .replace(/[*_`#>\[\]]/g, " ")
    .toLowerCase()
    .match(/[\p{L}\p{M}\p{N}]+/gu) ?? []);
}

export function PdfView({ url, marks, focusKey }: { url: string; marks: Marks; focusKey: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<PageInfo[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [words, setWords] = useState<Word[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Load and draw every page once, at the column's width; keep each text item's box and its words.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPages([]);
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const doc = await pdfjs.getDocument(url).promise;
        const width = Math.max(320, (box.current?.clientWidth ?? 640) - 24);
        const outPages: PageInfo[] = [];
        const outItems: Item[] = [];
        const outWords: Word[] = [];
        for (let p = 1; p <= doc.numPages; p++) {
          if (cancelled) return;
          const page = await doc.getPage(p);
          const scale = width / page.getViewport({ scale: 1 }).width;
          const viewport = page.getViewport({ scale });
          const canvas = document.createElement("canvas");
          const ratio = window.devicePixelRatio || 1;
          canvas.width = Math.floor(viewport.width * ratio);
          canvas.height = Math.floor(viewport.height * ratio);
          canvas.style.width = `${viewport.width}px`;
          canvas.style.height = `${viewport.height}px`;
          const ctx = canvas.getContext("2d")!;
          ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
          await page.render({ canvasContext: ctx, viewport }).promise;
          const content = await page.getTextContent();
          for (const raw of content.items) {
            const it = raw as { str?: string; transform?: number[]; width?: number };
            if (!it.str || !it.transform) continue;
            const tx = pdfjs.Util.transform(viewport.transform, it.transform);
            const h = Math.hypot(tx[2], tx[3]);
            const index = outItems.length;
            outItems.push({ page: p - 1, left: tx[4], top: tx[5] - h, width: (it.width ?? 0) * scale, height: h * 1.2 });
            for (const w of tokens(it.str)) outWords.push({ w, item: index });
          }
          outPages.push({ width: viewport.width, height: viewport.height, canvas });
          if (!cancelled && (p === 1 || p % 4 === 0 || p === doc.numPages)) {
            setPages([...outPages]);
            setItems([...outItems]);
            setWords([...outWords]);
          }
        }
        if (!cancelled) setLoading(false);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url]);

  // Five-word runs of the PDF's text, to find the book's words again.
  const grams = useMemo(() => {
    const index = new Map<string, number[]>();
    for (let i = 0; i + GRAM <= words.length; i++) {
      const key = words.slice(i, i + GRAM).map((x) => x.w).join(" ");
      const list = index.get(key);
      if (list) list.push(i);
      else index.set(key, [i]);
    }
    return index;
  }, [words]);

  const found = useMemo(() => {
    const hits = new Map<number, { color: string; strong: boolean; label?: string }>();
    let missing = 0;
    const ranges: [number, number][] = [];
    const locate = (ws: string[], from = 0): [number, number] | null => {
      if (ws.length < GRAM) return null;
      let start = -1;
      for (let k = 0; k + GRAM <= Math.min(ws.length, 80); k++) {
        const at = (grams.get(ws.slice(k, k + GRAM).join(" ")) ?? []).find((x) => x >= from);
        if (at !== undefined) { start = Math.max(0, at - k); break; }
      }
      if (start < 0) return null;
      let end = -1;
      for (let k = 0; k + GRAM <= Math.min(ws.length, 80); k++) {
        const s = ws.length - GRAM - k;
        if (s < 0) break;
        const at = (grams.get(ws.slice(s, s + GRAM).join(" ")) ?? []).filter((x) => x >= start).pop();
        if (at !== undefined) { end = Math.min(words.length - 1, at + GRAM - 1 + k); break; }
      }
      return [start, end >= start ? end : Math.min(words.length - 1, start + ws.length)];
    };
    for (const r of marks.ranges) {
      const span = locate(tokens(r.text));
      if (!span) { missing += 1; continue; }
      ranges.push(span);
      for (let i = span[0]; i <= span[1]; i++) if (!hits.has(words[i].item)) hits.set(words[i].item, { color: r.color, strong: false });
    }
    for (const t of marks.terms) {
      const ws = tokens(t.text).slice(0, 6);
      if (!ws.length) { missing += 1; continue; }
      const within = ranges.length ? ranges : [[0, words.length - 1] as [number, number]];
      let at = -1;
      for (const [a, b] of within) {
        for (let i = a; i + ws.length - 1 <= b && at < 0; i++) {
          if (ws.every((w, k) => words[i + k]?.w === w)) at = i;
        }
        if (at >= 0) break;
      }
      if (at < 0) { missing += 1; continue; }
      for (let k = 0; k < ws.length; k++) hits.set(words[at + k].item, { color: t.color, strong: true, label: t.label });
    }
    return { hits, missing, total: marks.ranges.length + marks.terms.length };
  }, [marks, grams, words]);

  // Bring the first highlight into view when what is selected changes.
  useEffect(() => {
    const first = box.current?.querySelector("[data-hl-strong]") ?? box.current?.querySelector("[data-hl]");
    first?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focusKey, found]);

  return (
    <div ref={box} className="relative h-full overflow-y-auto bg-neutral-800 p-3" data-testid="pdf-view">
      <div className="sticky top-0 z-10 mb-2 flex items-center justify-between rounded bg-neutral-900/90 px-2 py-1 text-[11px] text-neutral-400 backdrop-blur">
        <span>{loading ? `Drawing the PDF… ${pages.length} page${pages.length === 1 ? "" : "s"}` : `${pages.length} pages`}</span>
        {found.total > 0 && (
          <span className={found.missing ? "text-amber-300" : "text-emerald-300"}>
            {found.total - found.missing} of {found.total} parts found in the PDF's text
          </span>
        )}
      </div>
      {error && <p className="text-sm text-red-300">The PDF could not be shown: {error}</p>}
      {pages.map((page, p) => (
        <div key={p} className="relative mx-auto mb-3 bg-white shadow" style={{ width: page.width, height: page.height }}>
          <CanvasHost canvas={page.canvas} />
          {items.map((it, k) => {
            if (it.page !== p) return null;
            const hit = found.hits.get(k);
            if (!hit) return null;
            return (
              <div key={k} className="hl" data-hl="" {...(hit.strong ? { "data-hl-strong": "" } : {})}
                title={hit.label}
                style={{ left: it.left - 1, top: it.top - 1, width: it.width + 2, height: it.height + 2,
                  background: hit.color, outline: hit.strong ? `2px solid ${hit.color.replace(/[\d.]+\)$/, "1)")}` : undefined }} />
            );
          })}
          <span className="absolute right-1 bottom-1 rounded bg-black/50 px-1 text-[10px] text-white">{p + 1}</span>
        </div>
      ))}
    </div>
  );
}

function CanvasHost({ canvas }: { canvas: HTMLCanvasElement }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    host.innerHTML = "";
    host.appendChild(canvas);
  }, [canvas]);
  return <div ref={ref} className="absolute inset-0" />;
}
