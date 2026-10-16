"use client";

/**
 * The figure triage: which ways a figure may be shown (the user's choice), the model that decides, and every figure
 * with its picture, what it shows, the way chosen and the instruction for whoever builds it, its errors and calls.
 * Run does the figures not triaged yet; Reset and rerun all forgets every decision and does them all again.
 */

import { useEffect, useState } from "react";
import type { Run } from "@/lib/types";
import { DEFAULT_KINDS, TRIAGE_CHOICES, choiceOf, type TriageKind } from "@/lib/triage-kinds";
import { money } from "./call-inspector";
import type { Selection } from "./panels";

const TONE = { waiting: "text-neutral-400", running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;
export const solidKind = (k?: string) => (choiceOf(k)?.color ?? "rgba(148,163,184,0.45)").replace(/[\d.]+\)$/, "1)");

export function FiguresPanel({ run, defaultModel, selection, select, onCall, act }: {
  run: Run; defaultModel: string; selection: Selection; select: (s: Selection) => void; onCall: (id: string) => void;
  act: (body: Record<string, unknown>) => Promise<boolean>;
}) {
  const triage = run.triage;
  const [kinds, setKinds] = useState<TriageKind[]>(triage?.kinds ?? DEFAULT_KINDS);
  const [model, setModel] = useState(triage?.model || defaultModel);
  // A run picked from the list brings its own choices.
  useEffect(() => {
    setKinds(run.triage?.kinds ?? DEFAULT_KINDS);
    setModel(run.triage?.model || defaultModel);
  }, [run.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const figures = run.blocks.filter((b) => b.image);
  const noPicture = run.blocks.filter((b) => !b.image && /Figure|Picture/.test(b.type));
  const running = triage?.status === "running";
  const states = Object.values(triage?.figures ?? {});
  const done = states.filter((f) => f.status === "done").length;
  const failed = states.filter((f) => f.status === "failed").length;
  const cost = run.calls.filter((c) => c.step === "triage").reduce((n, c) => n + c.cost, 0);
  const counts = new Map<string, number>();
  for (const f of states) {
    const k = f.override ?? (f.status === "done" ? f.kind : undefined);
    if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";

  if (!run.blocks.length) {
    return <p className="text-sm text-neutral-400">The book has not been read in this run yet. Build the transcript (its first step reads the book), then triage its figures.</p>;
  }
  return (
    <div className="space-y-3" data-testid="figures">
      <section className="rounded border border-neutral-800 bg-neutral-900/60 p-3">
        <h3 className="text-sm font-semibold text-neutral-100">Figure triage</h3>
        <p className="mb-2 text-xs text-neutral-400">A model that reads images looks at each figure and decides how the video shows it, choosing only
          from the ways ticked here. Every decision is saved with the run.</p>
        <div className="grid gap-1.5 sm:grid-cols-2">
          {TRIAGE_CHOICES.map((c) => (
            <label key={c.key} className="flex cursor-pointer gap-2 rounded border border-neutral-800 p-1.5 text-xs hover:bg-neutral-800/60" data-testid={`kind-${c.key}`}>
              <input type="checkbox" checked={kinds.includes(c.key)} disabled={running}
                onChange={(e) => setKinds(e.target.checked ? [...kinds, c.key] : kinds.filter((k) => k !== c.key))} />
              <span>
                <span className="font-semibold" style={{ color: solidKind(c.key) }}>{c.label}</span>
                <span className="block text-neutral-400">{c.short}</span>
              </span>
            </label>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-neutral-400">Model</span>
          <input className="w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={model}
            onChange={(e) => setModel(e.target.value)} disabled={running} />
          <button className={`${btn} border-emerald-700 bg-emerald-700 text-white`} disabled={running || !kinds.length || !figures.length}
            data-testid="triage-run" onClick={() => act({ action: "run", kinds, model })}>
            {done && done < figures.length ? `Triage the ${figures.length - done} left` : "Triage figures"}
          </button>
          <button className={`${btn} border-amber-700 text-amber-200 hover:bg-amber-950`} disabled={running || !kinds.length || !figures.length}
            data-testid="triage-reset"
            onClick={() => confirm("Forget every figure's triage (and the ways chosen by hand) and triage them all again?") && act({ action: "reset", kinds, model })}>
            Reset and rerun all
          </button>
          {running && <button className={`${btn} border-red-700 text-red-200`} onClick={() => act({ action: "stop" })}>Stop</button>}
          {!kinds.length && <span className="text-red-300">Tick at least one way.</span>}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-300" data-testid="triage-summary">
        <span className={triage?.status === "failed" ? "text-red-300" : triage?.status === "running" ? "text-sky-300" : triage?.status === "done" ? "text-emerald-300" : "text-neutral-400"}>
          {triage ? triage.status : "not triaged yet"}
        </span>
        <span>{done} of {figures.length} figures triaged</span>
        {failed > 0 && <span className="text-red-300">{failed} failed</span>}
        {[...counts].map(([k, n]) => <span key={k} style={{ color: solidKind(k) }}>{n} {choiceOf(k)?.label}</span>)}
        {triage && <span>{triage.rounds} run{triage.rounds === 1 ? "" : "s"} · {triage.model}</span>}
        <span className="font-semibold">{money(cost)}</span>
      </div>
      {triage?.error && <p className="rounded border border-red-800 bg-red-950/40 p-2 text-xs text-red-200" data-testid="triage-error">{triage.error}</p>}
      {!figures.length && <p className="text-sm text-neutral-400">This book has no figure with a picture: Datalab cut none out
        {noPicture.length ? ` (${noPicture.length} figure block(s) without one)` : ""}.</p>}

      <ul className="grid gap-2 xl:grid-cols-2">
        {figures.map((b) => {
          const f = triage?.figures[b.id];
          const kind = f?.override ?? (f?.status === "done" ? f.kind : undefined);
          const lecture = run.lectures.find((l) => l.blocks.includes(b.id));
          const picked = selection?.kind === "block" && selection.id === b.id;
          return (
            <li key={b.id} data-testid="figure-card" onClick={() => select({ kind: "block", id: b.id })}
              className={`flex cursor-pointer gap-3 rounded border p-2 ${picked ? "border-white/60 bg-neutral-800/60" : "border-neutral-800 hover:bg-neutral-900"}`}
              style={kind ? { borderLeft: `4px solid ${solidKind(kind)}` } : undefined}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img alt={b.id} className="h-28 w-28 shrink-0 rounded bg-white object-contain"
                src={`/api/documents/${run.documentId}/figure/${encodeURIComponent(b.id)}`} />
              <div className="min-w-0 flex-1 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-neutral-300">{b.id}</span>
                  <span className="text-neutral-500">page {b.page + 1}{lecture ? ` · lecture ${lecture.n}` : ""}</span>
                  <span className={TONE[f?.status ?? "waiting"]}>{f ? (f.status === "running" ? "triaging…" : f.status) : "not triaged"}</span>
                </div>
                {kind && (
                  <p className="mt-1">
                    <span className="rounded px-1.5 py-px font-semibold text-neutral-950" style={{ background: solidKind(kind) }}>{choiceOf(kind)?.label}</span>
                    {f?.override && <span className="ml-1 text-amber-300">chosen by hand{f.kind ? ` (model: ${choiceOf(f.kind)?.label})` : ""}</span>}
                  </p>
                )}
                {f?.how && <p className="mt-1 text-neutral-200">{f.override && f.kind && f.override !== f.kind ? <span className="text-neutral-500">Model&apos;s note (for {choiceOf(f.kind)?.label}): </span> : null}{f.how}</p>}
                {f?.reason && <p className="mt-0.5 text-neutral-400">Why: {f.reason}</p>}
                {f?.keep?.length ? <p className="mt-0.5 text-neutral-400">Keep exactly: {f.keep.join(", ")}</p> : null}
                {b.description && <p className="mt-1 line-clamp-3 text-neutral-500" title={b.description}>Shows: {b.description}</p>}
                {f?.error && <p className="mt-1 text-red-300" data-testid="figure-error">Error: {f.error}</p>}
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                  <button className="rounded border border-neutral-700 px-1.5 py-px text-[11px] text-neutral-300 hover:bg-neutral-800 disabled:opacity-40"
                    disabled={running || !kinds.length} onClick={() => act({ action: "one", block: b.id, kinds, model })}>Rerun</button>
                  {f && (
                    <select className="rounded border border-neutral-700 bg-neutral-900 px-1 py-px text-[11px] text-neutral-300" value={f.override ?? ""}
                      title="Show it another way than the model chose" onChange={(e) => act({ action: "override", block: b.id, kind: e.target.value || null })}>
                      <option value="">{f.kind ? `model's choice (${choiceOf(f.kind)?.label})` : "model's choice"}</option>
                      {TRIAGE_CHOICES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                    </select>
                  )}
                  {f?.calls.map((id) => {
                    const c = run.calls.find((x) => x.id === id);
                    return c ? (
                      <button key={id} onClick={() => onCall(id)} className={`rounded border px-1.5 py-px text-[10px] hover:bg-neutral-800 ${c.status === "failed" ? "border-red-800 text-red-300" : "border-neutral-700 text-neutral-400"}`}>
                        call {id}{c.status === "running" ? " …" : c.status === "failed" ? " ✗" : ""} · {money(c.cost)}
                      </button>
                    ) : null;
                  })}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
