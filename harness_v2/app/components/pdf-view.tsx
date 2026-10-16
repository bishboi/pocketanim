"use client";

/**
 * The uploaded PDF, drawn page by page (pdf.js), with blocks of the book lit up on it: each by the bounding box
 * Datalab gave it, so what is highlighted is exactly the block a step works from. Clicking a box selects its block.
 */

import { useEffect, useRef, useState } from "react";

/** A block to light up: its page (0-based) and box (fractions of the page), in a colour; strong ones are outlined. */
export type Mark = { id: string; page: number; box: [number, number, number, number]; color: string; label?: string; strong?: boolean };

type PageInfo = { width: number; height: number; canvas: HTMLCanvasElement };

export function PdfView({ url, marks, focusKey, onPick }: { url: string; marks: Mark[]; focusKey: string; onPick?: (id: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<PageInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
        const out: PageInfo[] = [];
        for (let p = 1; p <= doc.numPages; p++) {
          if (cancelled) return;
          const page = await doc.getPage(p);
          const viewport = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width });
          const canvas = document.createElement("canvas");
          const ratio = window.devicePixelRatio || 1;
          canvas.width = Math.floor(viewport.width * ratio);
          canvas.height = Math.floor(viewport.height * ratio);
          canvas.style.width = `${viewport.width}px`;
          canvas.style.height = `${viewport.height}px`;
          const ctx = canvas.getContext("2d")!;
          ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
          await page.render({ canvasContext: ctx, viewport }).promise;
          out.push({ width: viewport.width, height: viewport.height, canvas });
          if (!cancelled && (p === 1 || p % 4 === 0 || p === doc.numPages)) setPages([...out]);
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

  // Bring the first selected block into view when the selection changes.
  useEffect(() => {
    const first = box.current?.querySelector("[data-hl-strong]") ?? (focusKey === "null" ? null : box.current?.querySelector("[data-hl]"));
    first?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focusKey, pages.length]);

  return (
    <div ref={box} className="relative h-full overflow-y-auto bg-neutral-800 p-3" data-testid="pdf-view">
      <div className="sticky top-0 z-10 mb-2 flex items-center justify-between rounded bg-neutral-900/90 px-2 py-1 text-[11px] text-neutral-400 backdrop-blur">
        <span>{loading ? `Drawing the PDF… ${pages.length} page${pages.length === 1 ? "" : "s"}` : `${pages.length} pages`}</span>
        <span>{marks.length ? `${marks.length} block${marks.length > 1 ? "s" : ""} shown` : ""}</span>
      </div>
      {error && <p className="text-sm text-red-300">The PDF could not be shown: {error}</p>}
      {pages.map((page, p) => (
        <div key={p} className="relative mx-auto mb-3 bg-white shadow" style={{ width: page.width, height: page.height }}>
          <CanvasHost canvas={page.canvas} />
          {marks.filter((m) => m.page === p).map((m) => (
            <div key={m.id} data-hl="" {...(m.strong ? { "data-hl-strong": "" } : {})} title={m.label}
              onClick={() => onPick?.(m.id)}
              className="absolute cursor-pointer rounded-sm"
              style={{ left: m.box[0] * page.width - 2, top: m.box[1] * page.height - 2, width: (m.box[2] - m.box[0]) * page.width + 4,
                height: (m.box[3] - m.box[1]) * page.height + 4, background: m.color, mixBlendMode: "multiply",
                outline: m.strong ? `2px solid ${m.color.replace(/[\d.]+\)$/, "1)")}` : undefined }} />
          ))}
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
