"use client";

/**
 * The figure triage: which ways a figure may be shown (the user's choice), the model that decides, and every figure
 * with its picture, what it shows, the way chosen and the instruction for whoever builds it, its errors and calls.
 * Run does the figures not triaged yet; Reset and rerun all forgets every decision and does them all again.
 */

import { useEffect, useState } from "react";
import type { Run, TriageEngine } from "@/lib/types";
import { DEFAULT_KINDS, TRIAGE_CHOICES, choiceOf, type TriageKind } from "@/lib/triage-kinds";
import { money } from "./call-inspector";
import type { Selection } from "./panels";

const TONE = { waiting: "text-neutral-400", running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;
export const solidKind = (k?: string) => (choiceOf(k)?.color ?? "rgba(148,163,184,0.45)").replace(/[\d.]+\)$/, "1)");

export function FiguresPanel({ run, defaultModel, defaultChatModel, selection, select, onCall, act }: {
  run: Run; defaultModel: string; defaultChatModel: string; selection: Selection; select: (s: Selection) => void; onCall: (id: string) => void;
  act: (body: Record<string, unknown>) => Promise<boolean>;
}) {
  const triage = run.triage;
  const [kinds, setKinds] = useState<TriageKind[]>(triage?.kinds ?? DEFAULT_KINDS);
  const [engine, setEngine] = useState<TriageEngine>(triage?.engine ?? "decision");
  // A run triaged before decision models kept a chat model as its model.
  const legacy = !!triage && !triage.engine;
  const [model, setModel] = useState((!legacy && triage?.model) || defaultModel);
  const [chatModel, setChatModel] = useState(triage?.chatModel || (legacy ? triage?.model : "") || defaultChatModel);
  const [threshold, setThreshold] = useState(Math.round((triage?.threshold ?? 0.6) * 100));
  // A run picked from the list brings its own choices.
  useEffect(() => {
    setKinds(run.triage?.kinds ?? DEFAULT_KINDS);
    setEngine(run.triage?.engine ?? "decision");
    const old = !!run.triage && !run.triage.engine;
    setModel((!old && run.triage?.model) || defaultModel);
    setChatModel(run.triage?.chatModel || (old ? run.triage?.model : "") || defaultChatModel);
    setThreshold(Math.round((run.triage?.threshold ?? 0.6) * 100));
  }, [run.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const settings = { kinds, engine, model, chatModel, threshold: threshold / 100 };

  const figures = run.blocks.filter((b) => b.image);
  const noPicture = run.blocks.filter((b) => !b.image && /Figure|Picture/.test(b.type));
  const running = triage?.status === "running";
  const states = Object.values(triage?.figures ?? {});
  const done = states.filter((f) => f.status === "done").length;
  const failed = states.filter((f) => f.status === "failed").length;
  const unsure = states.filter((f) => f.status === "done" && f.unsure).length;
  const cost = run.calls.filter((c) => c.step === "triage").reduce((n, c) => n + c.cost, 0);
  const counts = new Map<string, number>();
  for (const f of states) {
    const k = f.override ?? (f.status === "done" ? f.kind : undefined);
    if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";

  if (!run.blocks.length) {
    return <p className="text-sm text-neutral-400">The book has not been read in this run yet{run.status === "running" ? ": it is being read now." : ". Continue the run, or start one for the figures only."}</p>;
  }
  return (
    <div className="space-y-3" data-testid="figures">
      <section className="rounded border border-neutral-800 bg-neutral-900/60 p-3">
        <h3 className="text-sm font-semibold text-neutral-100">Figure triage</h3>
        <p className="mb-2 text-xs text-neutral-400">Each figure is classified into one of the ways ticked here. A <b>decision model</b> (Jev) answers
          with the way, a probability for each and its confidence, no words; under the threshold a figure is marked unsure. A <b>chat model</b> that reads
          images answers with an instruction and a reason too. Every decision is saved with the run.</p>
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
          <span className="text-neutral-400">Decided by</span>
          <select className="rounded border border-neutral-700 bg-neutral-900 px-1 py-1 text-neutral-100" value={engine} disabled={running}
            data-testid="triage-engine" onChange={(e) => setEngine(e.target.value as TriageEngine)}>
            <option value="decision">a decision model</option>
            <option value="chat">a chat model (reads images)</option>
          </select>
          {engine === "decision" ? (
            <>
              <input className="mono w-48 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={model} title="The decision model (Decisions API)"
                onChange={(e) => setModel(e.target.value)} disabled={running} />
              <span className="text-neutral-400" title="A choice with less confidence than this is marked unsure">unsure under</span>
              <input className="w-14 rounded border border-neutral-700 bg-neutral-900 px-1 py-1 text-neutral-100" type="number" min={0} max={100}
                value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} disabled={running} data-testid="triage-threshold" />
              <span className="text-neutral-400">%</span>
            </>
          ) : null}
          <span className="text-neutral-400">{engine === "decision" ? "Chat model (for unsure)" : "Chat model"}</span>
          <input className="mono w-48 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={chatModel}
            onChange={(e) => setChatModel(e.target.value)} disabled={running} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <button className={`${btn} border-emerald-700 bg-emerald-700 text-white`} disabled={running || !kinds.length || !figures.length}
            data-testid="triage-run" onClick={() => act({ action: "run", ...settings })}>
            {done && done < figures.length ? `Triage the ${figures.length - done} left` : "Triage figures"}
          </button>
          <button className={`${btn} border-amber-700 text-amber-200 hover:bg-amber-950`} disabled={running || !kinds.length || !figures.length}
            data-testid="triage-reset"
            onClick={() => confirm("Forget every figure's triage (and the ways chosen by hand) and triage them all again?") && act({ action: "reset", ...settings })}>
            Reset and rerun all
          </button>
          {unsure > 0 && (
            <button className={`${btn} border-sky-700 text-sky-200 hover:bg-sky-950`} disabled={running} data-testid="triage-unsure"
              onClick={() => act({ action: "unsure", ...settings })}>Ask the chat model about the {unsure} unsure</button>
          )}
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
        {unsure > 0 && <span className="text-amber-300">{unsure} unsure</span>}
        {[...counts].map(([k, n]) => <span key={k} style={{ color: solidKind(k) }}>{n} {choiceOf(k)?.label}</span>)}
        {triage && <span>{triage.rounds} run{triage.rounds === 1 ? "" : "s"} · {triage.engine === "chat" ? triage.chatModel : triage.model}</span>}
        <span className="font-semibold">{money(cost)}</span>
      </div>
      {triage?.error && <p className="rounded border border-red-800 bg-red-950/40 p-2 text-xs text-red-200" data-testid="triage-error">{triage.error}</p>}
      <FigureSearch run={run} figures={figures.length} noPicture={noPicture.length} running={running} act={act} />

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
                    {f?.confidence !== undefined && !f.override && (
                      <span className={`ml-1 ${f.unsure ? "text-amber-300" : "text-neutral-400"}`}>{(f.confidence * 100).toFixed(0)}% sure{f.unsure ? " · unsure" : ""}</span>
                    )}
                    {f?.engine && <span className="ml-1 text-neutral-500">· {f.engine === "decision" ? "decision model" : "chat model"}</span>}
                  </p>
                )}
                {f?.probabilities && Object.keys(f.probabilities).length > 0 && (
                  <div className="mt-1 space-y-px" data-testid="probabilities">
                    {Object.entries(f.probabilities).sort((a, b) => b[1] - a[1]).map(([k, p]) => (
                      <div key={k} className="flex items-center gap-1.5 text-[10px] text-neutral-400">
                        <span className="w-20 truncate">{choiceOf(k)?.label ?? k}</span>
                        <span className="h-1.5 flex-1 rounded bg-neutral-800"><span className="block h-1.5 rounded" style={{ width: `${Math.round(p * 100)}%`, background: solidKind(k) }} /></span>
                        <span className="w-8 text-right">{(p * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                )}
                {f?.how && <p className="mt-1 text-neutral-200">{f.override && f.kind && f.override !== f.kind ? <span className="text-neutral-500">Model&apos;s note (for {choiceOf(f.kind)?.label}): </span> : null}{f.how}</p>}
                {f?.reason && <p className="mt-0.5 text-neutral-400">Why: {f.reason}</p>}
                {f?.keep?.length ? <p className="mt-0.5 text-neutral-400">Keep exactly: {f.keep.join(", ")}</p> : null}
                {b.description && <p className="mt-1 line-clamp-3 text-neutral-500" title={b.description}>Shows: {b.description}</p>}
                {f?.error && <p className="mt-1 text-red-300" data-testid="figure-error">Error: {f.error}</p>}
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                  <button className="rounded border border-neutral-700 px-1.5 py-px text-[11px] text-neutral-300 hover:bg-neutral-800 disabled:opacity-40"
                    disabled={running || !kinds.length} onClick={() => act({ action: "one", block: b.id, ...settings })}>Rerun</button>
                  {engine === "decision" && (
                    <button className="rounded border border-neutral-700 px-1.5 py-px text-[11px] text-neutral-300 hover:bg-neutral-800 disabled:opacity-40"
                      title="Ask the chat model instead, for its instruction and reason" disabled={running || !kinds.length}
                      onClick={() => act({ action: "one", block: b.id, ...settings, engine: "chat" })}>Ask chat model</button>
                  )}
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

type Report = { figureBlocks: number; matched: number; blockImages: number; topImages: number; imgTags: number; cut?: number; unmatched: string[]; note: string };

/** What the search for the book's figure pictures found, and a button to search again (no Datalab call). */
function FigureSearch({ run, figures, noPicture, running, act }: { run: Run; figures: number; noPicture: number; running: boolean;
  act: (body: Record<string, unknown>) => Promise<boolean> }) {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    fetch(`/api/documents/${run.documentId}/figures`).then((r) => r.json()).then((j) => setReport(j.report)).catch(() => {});
  }, [run.documentId, figures]);
  if (!noPicture && report && !report.unmatched.length) return null;
  return (
    <div className={`rounded border p-2 text-xs ${figures ? "border-neutral-800 text-neutral-400" : "border-amber-800 bg-amber-950/30 text-amber-100"}`} data-testid="figure-search">
      <p>
        {figures ? `${figures} figure(s) have a picture` : "No figure has a picture yet"}{noPicture ? `; ${noPicture} figure block(s) have none` : ""}.
        {report ? ` Search: ${report.note}.` : ""}
      </p>
      {report && (
        <p className="mt-0.5 text-neutral-400">Datalab found {report.figureBlocks} figure block(s); its result had {report.blockImages} block image(s),
          {" "}{report.topImages} named picture(s) and {report.imgTags} &lt;img&gt; tag(s){report.cut !== undefined ? `; ${report.cut} cut out of the PDF itself` : ""}.
          {report.unmatched.length ? ` Still without: ${report.unmatched.slice(0, 6).join(", ")}${report.unmatched.length > 6 ? "…" : ""}` : ""}</p>
      )}
      <button className="mt-1 rounded border border-neutral-600 px-2 py-0.5 text-neutral-200 hover:bg-neutral-800 disabled:opacity-40" disabled={busy || running}
        data-testid="figure-rescan" onClick={async () => {
          setBusy(true);
          await act({ action: "rescan" });
          const j = await fetch(`/api/documents/${run.documentId}/figures`).then((r) => r.json()).catch(() => ({}));
          setReport(j.report ?? null);
          setBusy(false);
        }}>{busy ? "Searching…" : "Search the pictures again"}</button>
      <span className="ml-2 text-neutral-500">Datalab&apos;s cached result, then the PDF itself: no new conversion, no cost.</span>
    </div>
  );
}
