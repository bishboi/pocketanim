"use client";

/**
 * Generation: the figures triaged Exact or Styled redraw, each redrawn by the image model from the book's figure with
 * v1's redraw prompt. Every figure shows the book's figure, the prompt it was sent (its parts, each opening to its
 * words), the image made, its calls, cost and error.
 */

import { useEffect, useState } from "react";
import type { Run } from "@/lib/types";
import { choiceOf } from "@/lib/triage-kinds";
import { KIND_STYLE, money } from "./call-inspector";
import { solidKind } from "./figures-panel";
import type { Selection } from "./panels";

const TONE = { waiting: "text-neutral-400", running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;
const GENERATED = ["exact", "styled", "svg", "manim", "map"];

export function GenerationPanel({ run, defaultModel, defaultSvgModel, defaultManimModel, defaultMapModel, select, onCall, act }: {
  run: Run; defaultModel: string; defaultSvgModel: string; defaultManimModel: string; defaultMapModel: string; select: (s: Selection) => void; onCall: (id: string) => void;
  act: (body: Record<string, unknown>) => Promise<boolean>;
}) {
  const gen = run.generation;
  const [model, setModel] = useState(gen?.model || defaultModel);
  const [svgModel, setSvgModel] = useState(gen?.svgModel || defaultSvgModel);
  const [manimModel, setManimModel] = useState(gen?.manimModel || defaultManimModel);
  const [mapModel, setMapModel] = useState(gen?.mapModel || defaultMapModel);
  useEffect(() => {
    setModel(run.generation?.model || defaultModel);
    setSvgModel(run.generation?.svgModel || defaultSvgModel);
    setManimModel(run.generation?.manimModel || defaultManimModel);
    setMapModel(run.generation?.mapModel || defaultMapModel);
  }, [run.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const models = { model, svgModel, manimModel, mapModel };
  const wayOf = (id: string) => {
    const f = run.triage?.figures[id];
    return f?.override ?? (f?.status === "done" ? f.kind : undefined);
  };
  const figures = run.blocks.filter((b) => b.image && GENERATED.includes(wayOf(b.id) ?? ""));
  const others = run.blocks.filter((b) => b.image && wayOf(b.id) && !GENERATED.includes(wayOf(b.id)!));
  const running = gen?.status === "running";
  // A figure is busy while it is queued or being generated; the others stay free to start.
  const busyFig = (id: string) => running && (gen?.figures[id]?.status === "running" || gen?.figures[id]?.status === "waiting");
  const busyCount = figures.filter((b) => busyFig(b.id)).length;
  const states = Object.values(gen?.figures ?? {});
  const done = figures.filter((b) => gen?.figures[b.id]?.status === "done").length;
  const failed = states.filter((f) => f.status === "failed").length;
  const cost = run.calls.filter((c) => c.step === "generate").reduce((n, c) => n + c.cost, 0);
  const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";

  if (!run.triage) return <p className="text-sm text-neutral-400">Triage the figures first (Figures tab): this step redraws the figures triaged Exact or Styled redraw.</p>;
  return (
    <div className="space-y-3" data-testid="generation">
      <section className="rounded border border-neutral-800 bg-neutral-900/60 p-3">
        <h3 className="text-sm font-semibold text-neutral-100">Generation: redraws, SVG drawings, Manim and maps</h3>
        <p className="mb-2 text-xs text-neutral-400">Each figure triaged <b>Exact redraw</b> or <b>Styled redraw</b> is redrawn by the image model from the
          book&apos;s figure (sent as the reference image), with no text in it (labels are put on later), in gentle words that moderation lets through
          (gentler still, then without the reference, when it blocks one). Styled uses the same prompt for now: there are no lecture styles yet.
          Each figure triaged <b>SVG drawing</b> is drawn by the SVG model from the figure itself, in one call, with v1&apos;s SVG prompt; code checks it
          against v1&apos;s rules and sends what breaks them back once. It is shown on v1&apos;s default board. Each figure triaged <b>Manim</b> is
          written in Manim by the Manim model from the figure itself, in one call, with v1&apos;s Manim rules, and rendered here with the repo&apos;s Manim:
          its last frame and its video (a failed render goes back to the model once, with the error). Each figure triaged <b>Map</b> is written
          by the map model from the book&apos;s map, in one call, as a short map script (region and a few beats of map operations, v1&apos;s), drawn
          on real map data by v2&apos;s lecture engine and rendered the same way.
          The other ways are built by steps to come{others.length ? ` (${others.length} figure(s) here: ${[...new Set(others.map((b) => choiceOf(wayOf(b.id))?.label))].join(", ")})` : ""}.</p>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-neutral-400">Image model</span>
          <input className="mono w-64 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={model}
            onChange={(e) => setModel(e.target.value)} data-testid="image-model" />
          <span className="text-neutral-400">SVG model</span>
          <input className="mono w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={svgModel}
            title="Reads the figure and writes the SVG, in one call" onChange={(e) => setSvgModel(e.target.value)} data-testid="svg-model" />
          <span className="text-neutral-400">Manim model</span>
          <input className="mono w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={manimModel}
            title="Reads the figure and writes its Manim code, in one call" onChange={(e) => setManimModel(e.target.value)} data-testid="manim-model" />
          <span className="text-neutral-400">Map model</span>
          <input className="mono w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={mapModel}
            title="Reads the book's map and writes its map script, in one call" onChange={(e) => setMapModel(e.target.value)} data-testid="map-model" />
          <button className={`${btn} border-emerald-700 bg-emerald-700 text-white`} disabled={!figures.length || busyCount === figures.length} data-testid="generate-run"
            onClick={() => act({ action: "run", ...models })}>{done && done < figures.length ? `Generate the ${figures.length - done} left` : "Generate"}</button>
          <button className={`${btn} border-amber-700 text-amber-200 hover:bg-amber-950`} disabled={!figures.length || busyCount === figures.length} data-testid="generate-reset"
            onClick={() => confirm("Forget every generated image and generate them all again?") && act({ action: "reset", ...models })}>Reset and regenerate all</button>
          {running && <button className={`${btn} border-red-700 text-red-200`} onClick={() => act({ action: "stop" })}>Stop all</button>}
          {running && <span className="text-sky-300" data-testid="generating-count">{busyCount} generating; the others can be started now</span>}
        </div>
      </section>
      <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-300" data-testid="generation-summary">
        <span className={gen?.status === "failed" ? "text-red-300" : running ? "text-sky-300" : gen?.status === "done" ? "text-emerald-300" : "text-neutral-400"}>
          {gen ? gen.status : "not generated yet"}</span>
        <span>{done} of {figures.length} generated</span>
        {failed > 0 && <span className="text-red-300">{failed} failed</span>}
        {gen && <span>{gen.rounds} run{gen.rounds === 1 ? "" : "s"} · {gen.model}{gen.svgModel ? ` · ${gen.svgModel}` : ""}{gen.manimModel ? ` · ${gen.manimModel}` : ""}{gen.mapModel ? ` · ${gen.mapModel}` : ""}</span>}
        <span className="font-semibold">{money(cost)}</span>
      </div>
      {gen?.error && <p className="rounded border border-red-800 bg-red-950/40 p-2 text-xs text-red-200">{gen.error}</p>}
      {!figures.length && <p className="text-sm text-neutral-400">No figure is triaged Exact redraw, Styled redraw, SVG drawing, Manim or Map. Change a figure&apos;s way on the Figures tab, or triage again.</p>}

      <ul className="space-y-3">
        {figures.map((b) => {
          const f = gen?.figures[b.id];
          const kind = wayOf(b.id);
          const lastCall = f?.calls.length ? run.calls.find((c) => c.id === f.calls[f.calls.length - 1]) : undefined;
          return (
            <li key={b.id} className="rounded border border-neutral-800 p-2" style={{ borderLeft: `4px solid ${solidKind(kind)}` }} data-testid="generation-card">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <button className="font-mono text-neutral-200 hover:underline" onClick={() => select({ kind: "block", id: b.id })}>{b.id}</button>
                <span className="rounded px-1.5 py-px font-semibold text-neutral-950" style={{ background: solidKind(kind) }}>{choiceOf(kind)?.label}</span>
                <span className="text-neutral-500">page {b.page + 1}</span>
                <span className={TONE[f?.status ?? "waiting"]}>{f ? (f.status === "running" ? "generating…" : f.status === "waiting" && busyFig(b.id) ? "queued" : f.status) : "not generated"}</span>
                {f?.level && f.level !== "full" && <span className="text-amber-300" data-testid="generation-level">{f.level === "gentle"
                  ? "asked in gentler words (the full prompt was blocked by moderation)" : "drawn with no reference image (the picture was blocked by moderation)"}</span>}
                <span className="ml-auto flex items-center gap-1.5">
                  <button className="rounded border border-neutral-700 px-1.5 py-px text-[11px] text-neutral-300 hover:bg-neutral-800 disabled:opacity-40"
                    disabled={busyFig(b.id)} data-testid="generate-one" onClick={() => act({ action: "one", block: b.id, ...models })}>{f?.status === "done" ? "Regenerate" : "Generate"}</button>
                  {f?.calls.map((id) => {
                    const c = run.calls.find((x) => x.id === id);
                    return c ? <button key={id} onClick={() => onCall(id)} className={`rounded border px-1.5 py-px text-[10px] hover:bg-neutral-800 ${c.status === "failed" ? "border-red-800 text-red-300" : "border-neutral-700 text-neutral-400"}`}>
                      call {id}{c.status === "running" ? " …" : c.status === "failed" ? " ✗" : ""} · {money(c.cost)}</button> : null;
                  })}
                </span>
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <figure>
                  <figcaption className="mb-1 text-[11px] uppercase tracking-wide text-neutral-500">The book&apos;s figure (reference)</figcaption>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img alt={b.id} className="max-h-72 w-full rounded bg-white object-contain" src={`/api/documents/${run.documentId}/figure/${encodeURIComponent(b.id)}`} />
                </figure>
                <figure>
                  <figcaption className="mb-1 text-[11px] uppercase tracking-wide text-neutral-500">{kind === "svg" ? "SVG drawing (on v1's default board)" : kind === "manim" ? "Manim (its last frame; the video below)" : kind === "map" ? "Map (its last frame; the video below)" : "Generated"}
                    {lastCall?.provider === "fixture" ? (kind === "svg" || kind === "manim" || kind === "map" ? " (offline stand-in)" : " (offline stand-in: the book's figure back)") : ""}</figcaption>
                  {f?.url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img alt={`${b.id} generated`} className={`max-h-72 w-full rounded object-contain ${kind === "svg" || kind === "manim" || kind === "map" ? "bg-[#0D1117]" : "bg-white"}`} src={f.url}
                      data-testid={kind === "svg" ? "generated-svg" : kind === "manim" ? "generated-manim" : kind === "map" ? "generated-map" : "generated-image"} />
                  ) : (
                    <div className="flex h-40 items-center justify-center rounded border border-dashed border-neutral-700 text-xs text-neutral-500">
                      {f?.status === "running" ? "generating…" : f?.error ? "no image" : "not generated yet"}</div>
                  )}
                </figure>
              </div>
              {f?.error && <p className="mt-1 text-xs text-red-300" data-testid="generation-error">Error: {f.error}</p>}
              {kind === "svg" && f?.status === "done" && <SvgFacts run={run} block={b.id} parts={f.svgParts ?? []} problems={f.svgProblems} />}
              {kind === "manim" && <ManimFacts run={run} block={b.id} video={f?.status === "done" && !!f.video} code={f?.code} at={f?.at} />}
              {kind === "map" && <ManimFacts run={run} block={b.id} video={f?.status === "done" && !!f.video} what="map script"
                code={f?.mapScript ? JSON.stringify(f.mapScript, null, 2) : undefined} at={f?.at} />}
              {lastCall && <PromptParts parts={kind === "svg" || kind === "manim" || kind === "map" ? [...lastCall.prompt.system, ...lastCall.prompt.user] : lastCall.prompt.user} sent={f?.prompt} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** The prompt by its parts: click one to read it; the whole as sent below. */
function PromptParts({ parts, sent }: { parts: Run["calls"][number]["prompt"]["user"]; sent?: string }) {
  const [open, setOpen] = useState<string | null>(null);
  const [whole, setWhole] = useState(false);
  const p = parts.find((x) => x.key === open);
  return (
    <div className="mt-2 text-xs" data-testid="generation-prompt">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-neutral-500">Input prompt</p>
      <div className="flex flex-wrap gap-1">
        {parts.map((x) => (
          <button key={x.key} onClick={() => setOpen(open === x.key ? null : x.key)}
            className={`rounded border px-1.5 py-0.5 text-[11px] ${KIND_STYLE[x.kind]} ${open === x.key ? "ring-2 ring-white/60" : ""}`}>{x.label}</button>
        ))}
        {sent && <button onClick={() => setWhole(!whole)} className="rounded border border-neutral-600 px-1.5 py-0.5 text-[11px] text-neutral-200">{whole ? "Hide" : "Whole prompt as sent"}</button>}
      </div>
      {p && <pre className={`mono mt-1 whitespace-pre-wrap rounded border-l-4 bg-neutral-900 p-2 text-[11.5px] text-neutral-200 ${KIND_STYLE[p.kind]}`}>{p.text}</pre>}
      {whole && sent && <pre className="mono mt-1 whitespace-pre-wrap rounded bg-neutral-900 p-2 text-[11.5px] text-neutral-200">{sent}</pre>}
    </div>
  );
}

/** An SVG's parts, the rules it still breaks, and its code as written. */
function SvgFacts({ run, block, parts, problems }: { run: Run; block: string; parts: string[]; problems?: string[] }) {
  const [code, setCode] = useState<string | null>(null);
  return (
    <div className="mt-2 text-xs" data-testid="svg-facts">
      <p className="text-neutral-400">Parts ({parts.length}): {parts.length ? parts.map((p) => <span key={p} className="mono mr-1 rounded bg-neutral-800 px-1">{p}</span>) : "none"}</p>
      {problems?.length ? <p className="mt-0.5 text-amber-300">Still breaks v1&apos;s rules: {problems.join("; ")}</p> : <p className="mt-0.5 text-emerald-300">Keeps v1&apos;s rules.</p>}
      <button className="mt-1 rounded border border-neutral-700 px-1.5 py-0.5 text-[11px] text-neutral-300 hover:bg-neutral-800"
        onClick={async () => setCode(code ? null : await fetch(`/api/runs/${run.id}/generated/${encodeURIComponent(block)}?raw`).then((r) => r.text()))}>
        {code ? "Hide the SVG code" : "Show the SVG code"}</button>
      {code && <pre className="mono mt-1 max-h-80 overflow-auto whitespace-pre-wrap rounded bg-neutral-900 p-2 text-[11px] text-neutral-300">{code}</pre>}
    </div>
  );
}

/** A Manim figure's video (its whole build, as rendered) and its code. */
function ManimFacts({ run, block, video, code, at, what = "Manim code" }: { run: Run; block: string; video: boolean; code?: string; at?: number; what?: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="mt-2 text-xs" data-testid="manim-facts">
      {video && (
        <video className="max-h-80 w-full rounded bg-[#0D1117]" controls loop muted data-testid="manim-video"
          src={`/api/runs/${run.id}/generated/${encodeURIComponent(block)}?video&v=${at ?? 0}`} />
      )}
      {code && (
        <>
          <button className="mt-1 rounded border border-neutral-700 px-1.5 py-0.5 text-[11px] text-neutral-300 hover:bg-neutral-800" onClick={() => setShow(!show)}>
            {show ? `Hide the ${what}` : `Show the ${what}`}</button>
          {show && <pre className="mono mt-1 max-h-80 overflow-auto whitespace-pre-wrap rounded bg-neutral-900 p-2 text-[11px] text-neutral-300">{code}</pre>}
        </>
      )}
    </div>
  );
}
