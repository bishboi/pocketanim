"use client";

import { PICTURE_KINDS, usd, type AiPicture } from "@/lib/costs";

/**
 * The pictures the AI made for a lecture, each as the board shows it, with what it cost: the book's figures and the
 * script's pictures drawn as SVG (painted in the lecture's colours, moving if they move), and illustrations an
 * image model drew. A picture reused from an earlier lecture cost nothing now; what it cost then is said.
 */
export function AiPictures({ pictures, style }: { pictures: AiPicture[]; style?: string }) {
  if (!pictures.length) return null;
  const svgs = pictures.filter((p) => p.kind !== "illustration");
  const images = pictures.filter((p) => p.kind === "illustration");
  const spent = (list: AiPicture[]) => list.reduce((t, p) => t + p.usd, 0);
  const made = (list: AiPicture[]) => list.filter((p) => !p.reused).length;
  const sum = (list: AiPicture[], word: string) =>
    list.length ? `${list.length} ${word}${list.length > 1 ? "s" : ""} (${made(list)} new) ${usd(spent(list))}` : "";
  return (
    <details className="rounded border border-neutral-800 bg-neutral-950 text-xs" data-testid="ai-pictures">
      <summary className="cursor-pointer select-none px-3 py-2 text-neutral-300">
        Pictures the AI made <span className="font-mono text-neutral-100">{usd(spent(pictures))}</span>
        <span className="text-neutral-500"> · {[sum(svgs, "SVG"), sum(images, "illustration")].filter(Boolean).join(" · ")}</span>
      </summary>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3 px-3 pb-3">
        {pictures.map((p) => (
          <figure key={p.file} className="flex min-w-0 flex-col overflow-hidden rounded border border-neutral-800 bg-neutral-900">
            <a href={src(p, style)} target="_blank" rel="noreferrer" title="Open full size">
              {/* An <img> keeps an SVG's own animation running and its scripts off. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={src(p, style)} alt={p.title} loading="lazy"
                className="aspect-video w-full bg-neutral-950 object-contain" />
            </a>
            <figcaption className="flex flex-col gap-1 p-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[10px] uppercase tracking-wide text-neutral-500">{PICTURE_KINDS[p.kind]}</span>
                <span className="font-mono text-neutral-100">
                  {p.reused ? "reused" : usd(p.usd)}
                </span>
              </div>
              <p className="line-clamp-3 text-neutral-300" title={p.title}>{p.title}</p>
              {p.reused && (
                <p className="text-neutral-500">
                  Made for an earlier lecture{p.paid ? ` for ${usd(p.paid)}` : ""}; free this time.
                </p>
              )}
              {p.detail && <p className="truncate text-neutral-500" title={p.detail}>{p.kind === "illustration" ? `by ${p.detail}` : `parts: ${p.detail}`}</p>}
            </figcaption>
          </figure>
        ))}
      </div>
    </details>
  );
}

function src(p: AiPicture, style?: string): string {
  return `/api/picture?file=${encodeURIComponent(p.file)}${style ? `&style=${encodeURIComponent(style)}` : ""}`;
}
