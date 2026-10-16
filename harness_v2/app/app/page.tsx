"use client";

/**
 * Harness v2, step one: the transcript. A book PDF in; the transcript out, built as v1 builds it (sections, learning
 * map, story plans, sections written several at once, goals checked and patched, videos), with every step, every
 * call (its prompt part by part, its output, its checks, its cost) and every part's source in the PDF in view.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { DocumentInfo, Options, Run } from "@/lib/types";
import { sourceItems, type SourceItem } from "@/lib/plan/learningmap";
import type { Section } from "@/lib/source/book";
import { PdfView, type Marks } from "@/components/pdf-view";
import { CallInspector, money } from "@/components/call-inspector";
import { CallsPanel, CostsPanel, ModelsPanel, PlanPanel, TranscriptPanel, sectionColor, type Selection } from "@/components/panels";

type Config = { hasKey: boolean; datalab: boolean; plannerModel: string; writerModel: string };
const TABS = ["Plan", "Transcript", "Calls", "Costs", "Models"] as const;

/** The words of an item to find in the PDF: a box's body, a figure's caption, a heading or term as it is. */
function itemText(item: SourceItem): string {
  if (item.kind === "aside" || item.kind === "figure") return item.text.includes(": ") ? item.text.split(": ").slice(1).join(": ") : item.text;
  return item.text;
}

export default function Page() {
  const [config, setConfig] = useState<Config | null>(null);
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [runs, setRuns] = useState<{ id: string; documentName: string; created: number; status: string; cost: number }[]>([]);
  const [docId, setDocId] = useState("");
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [options, setOptions] = useState<Partial<Options>>({ minutes: 0, language: "auto", subject: "", effort: "medium", parallel: 10 });
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Plan");
  const [selection, setSelection] = useState<Selection>(null);
  const [callId, setCallId] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  const refresh = useCallback(async () => {
    const [d, r] = await Promise.all([fetch("/api/documents").then((x) => x.json()), fetch("/api/runs").then((x) => x.json())]);
    setDocs(d.documents ?? []);
    setRuns(r.runs ?? []);
  }, []);

  useEffect(() => {
    fetch("/api/config").then((r) => r.json()).then((c: Config) => {
      setConfig(c);
      setOptions((o) => ({ ...o, plannerModel: o.plannerModel || c.plannerModel, writerModel: o.writerModel || c.writerModel }));
    });
    void refresh();
    const saved = new URLSearchParams(location.search).get("run");
    if (saved) setRunId(saved);
  }, [refresh]);

  // Follow the run: every second while it runs.
  useEffect(() => {
    if (!runId) return;
    let stop = false;
    const tick = async () => {
      const res = await fetch(`/api/runs/${runId}`, { cache: "no-store" });
      if (!res.ok || stop) return;
      const next = (await res.json()) as Run;
      setRun(next);
      setDocId((d) => d || next.documentId);
      if (next.status === "running") setTimeout(tick, 1000);
      else void refresh();
    };
    void tick();
    history.replaceState(null, "", `?run=${runId}`);
    return () => {
      stop = true;
    };
  }, [runId, refresh]);

  useEffect(() => {
    if (run?.status !== "running") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [run?.status]);

  const upload = async (file: File) => {
    setUploading(`Reading ${file.name}…`);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/documents", { method: "POST", body: form });
    const json = await res.json();
    setUploading(null);
    if (!res.ok) return setError(json.error ?? "the upload failed");
    await refresh();
    setDocId(json.id);
    setRun(null);
    setRunId("");
  };

  const start = async () => {
    setError(null);
    const res = await fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documentId: docId, options }) });
    const json = await res.json();
    if (!res.ok) return setError(json.error ?? "the run could not start");
    setSelection(null);
    setRun(null);
    setRunId(json.id);
    setTab("Plan");
  };

  // What the PDF highlights: every section's text in its colour; a section's items; a goal's items.
  const marks: Marks = useMemo(() => {
    if (!run) return { ranges: [], terms: [] };
    const items = run.map?.items ?? sourceItems(run.sections as unknown as Section[]);
    const termColor: Record<string, string> = { heading: "rgba(56,189,248,0.45)", term: "rgba(250,204,21,0.55)",
      aside: "rgba(244,114,182,0.45)", figure: "rgba(167,139,250,0.45)" };
    if (selection?.kind === "goal") {
      const goal = run.map?.goals.find((g) => g.id === selection.id);
      const section = run.sections.find((s) => s.n === goal?.section);
      return {
        ranges: section ? [{ text: section.source, color: "rgba(148,163,184,0.18)" }] : [],
        terms: (goal?.items ?? []).map((id) => items.find((i) => i.id === id)).filter((i): i is SourceItem => !!i)
          .map((i) => ({ text: itemText(i), color: "rgba(16,185,129,0.55)", label: `${goal?.id} · ${i.kind}: ${i.text}` })),
      };
    }
    if (selection?.kind === "section") {
      const section = run.sections.find((s) => s.n === selection.n);
      return {
        ranges: section && !section.questionsOnly ? [{ text: section.source, color: sectionColor(section.n) }] : [],
        terms: items.filter((i) => i.section === selection.n).map((i) => ({ text: itemText(i), color: termColor[i.kind], label: `${i.kind}: ${i.text}` })),
      };
    }
    return { ranges: run.sections.filter((s) => !s.questionsOnly).map((s) => ({ text: s.source, color: sectionColor(s.n), label: `Section ${s.n}` })), terms: [] };
  }, [run, selection]);

  const call = run?.calls.find((c) => c.id === callId) ?? null;
  const total = run?.calls.reduce((n, c) => n + c.cost, 0) ?? 0;
  const tokens = run?.calls.reduce((n, c) => n + (c.usage?.input ?? 0) + (c.usage?.output ?? 0), 0) ?? 0;
  const elapsed = run ? ((run.ended ?? now) - run.created) / 1000 : 0;
  const doc = docs.find((d) => d.id === docId);
  const input = "rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-100";

  return (
    <div className="flex h-screen flex-col">
      <header className="border-b border-neutral-800 px-4 py-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-sm font-semibold text-neutral-100">Harness v2 <span className="text-neutral-500">· Transcript</span></h1>
          <select className={input} value={docId} onChange={(e) => { setDocId(e.target.value); setRun(null); setRunId(""); setSelection(null); }} data-testid="doc-select">
            <option value="">Choose a book…</option>
            {docs.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.pages} pages, {d.words.toLocaleString()} words)</option>)}
          </select>
          <label className="cursor-pointer rounded border border-neutral-600 px-2 py-1 text-xs text-neutral-200 hover:bg-neutral-800">
            Upload PDF
            <input type="file" accept="application/pdf" className="hidden" data-testid="upload"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
          {uploading && <span className="text-xs text-sky-300">{uploading}</span>}
          <select className={input} value={runId} onChange={(e) => { setSelection(null); setRunId(e.target.value); }}>
            <option value="">Past runs…</option>
            {runs.map((r) => <option key={r.id} value={r.id}>{new Date(r.created).toLocaleString()} · {r.documentName} · {r.status} · {money(r.cost)}</option>)}
          </select>
          <div className="ml-auto flex items-center gap-3 text-xs text-neutral-300" data-testid="totals">
            {run && <>
              <span className={run.status === "failed" ? "text-red-300" : run.status === "done" ? "text-emerald-300" : "text-sky-300"}>{run.status}</span>
              <span>{Math.round(elapsed)} s</span>
              <span>{run.calls.length} calls</span>
              <span>{tokens.toLocaleString()} tokens</span>
              <span className="font-semibold text-neutral-100">{money(total)}</span>
            </>}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-neutral-400">
          <span>Minutes</span>
          <input className={`${input} w-16`} type="number" min={0} value={options.minutes ?? 0} title="0: from the book's length"
            onChange={(e) => setOptions({ ...options, minutes: Number(e.target.value) })} />
          <span>Language</span>
          <select className={input} value={options.language} onChange={(e) => setOptions({ ...options, language: e.target.value as Options["language"] })}>
            {["auto", "english", "hindi", "hinglish"].map((l) => <option key={l}>{l}</option>)}
          </select>
          <span>Subject</span>
          <input className={`${input} w-28`} placeholder="(optional)" value={options.subject ?? ""} onChange={(e) => setOptions({ ...options, subject: e.target.value })} />
          <span>Planner</span>
          <input className={`${input} w-52`} value={options.plannerModel ?? ""} onChange={(e) => setOptions({ ...options, plannerModel: e.target.value })} />
          <span>Writer</span>
          <input className={`${input} w-52`} value={options.writerModel ?? ""} onChange={(e) => setOptions({ ...options, writerModel: e.target.value })} />
          <span>Effort</span>
          <select className={input} value={options.effort} onChange={(e) => setOptions({ ...options, effort: e.target.value as Options["effort"] })}>
            {["low", "medium", "high", "off"].map((l) => <option key={l}>{l}</option>)}
          </select>
          <span>At once</span>
          <input className={`${input} w-12`} type="number" min={1} max={16} value={options.parallel ?? 10}
            onChange={(e) => setOptions({ ...options, parallel: Number(e.target.value) })} />
          <button disabled={!docId || run?.status === "running"} onClick={start} data-testid="start"
            className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white disabled:opacity-40">Build the transcript</button>
          {config && !config.hasKey && <span className="text-amber-300">No OPENROUTER_API_KEY: calls are answered by the offline stand-in.</span>}
          {error && <span className="text-red-300">{error}</span>}
        </div>
        {run && (
          <ol className="mt-2 flex flex-wrap gap-2 text-xs" data-testid="steps">
            {run.steps.map((s, k) => (
              <li key={s.key} className={`rounded border px-2 py-1 ${s.status === "done" ? "border-emerald-800 bg-emerald-950/40" :
                s.status === "running" ? "border-sky-700 bg-sky-950/40" : s.status === "failed" ? "border-red-800 bg-red-950/40" : "border-neutral-800"}`}>
                <span className="text-neutral-500">{k + 1}.</span> <span className="text-neutral-100">{s.label}</span>
                {s.started && <span className="text-neutral-500"> · {Math.round(((s.ended ?? now) - s.started) / 1000)} s</span>}
                {s.summary && <span className="block text-[11px] text-neutral-400">{s.summary}</span>}
              </li>
            ))}
          </ol>
        )}
        {run?.error && <p className="mt-1 text-xs text-red-300">{run.error}</p>}
      </header>

      <main className="flex min-h-0 flex-1">
        <div className="w-[44%] min-w-[360px] border-r border-neutral-800">
          {docId ? <PdfView url={`/api/documents/${docId}/pdf`} marks={marks} focusKey={JSON.stringify(selection)} />
            : <div className="p-6 text-sm text-neutral-400">Upload a book's PDF, or choose one, to begin.{doc ? "" : ""}</div>}
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <nav className="flex items-center gap-1 border-b border-neutral-800 px-3 pt-2">
            {TABS.map((t) => (
              <button key={t} onClick={() => setTab(t)} data-testid={`tab-${t}`}
                className={`rounded-t px-3 py-1.5 text-sm ${tab === t ? "bg-neutral-800 text-white" : "text-neutral-400 hover:text-neutral-200"}`}>{t}
                {t === "Calls" && run ? <span className="ml-1 text-[10px] text-neutral-500">{run.calls.length}</span> : null}
              </button>
            ))}
            {selection && (
              <span className="ml-auto flex items-center gap-2 pb-1 text-xs text-neutral-400">
                Showing {selection.kind === "section" ? `section ${selection.n}` : `goal ${selection.id}`} in the PDF
                <button className="rounded border border-neutral-700 px-1.5" onClick={() => setSelection(null)}>clear</button>
              </span>
            )}
          </nav>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {!run && tab !== "Models" && <p className="text-sm text-neutral-400">{docId ? "Press Build the transcript to start." : "No book chosen yet."}</p>}
            {run && tab === "Plan" && <PlanPanel run={run} selection={selection} select={setSelection} onCall={setCallId} />}
            {run && tab === "Transcript" && <TranscriptPanel run={run} selection={selection} select={setSelection} onCall={setCallId} />}
            {run && tab === "Calls" && <CallsPanel run={run} onCall={setCallId} section={selection?.kind === "section" ? selection.n : undefined} />}
            {run && tab === "Costs" && <CostsPanel run={run} />}
            {tab === "Models" && <ModelsPanel models={[{ role: "Planner", model: options.plannerModel ?? "" }, { role: "Writer", model: options.writerModel ?? "" }]} />}
            {run && run.log.length > 0 && tab === "Plan" && (
              <details className="mt-4 text-xs text-neutral-400"><summary className="cursor-pointer">Run log ({run.log.length})</summary>
                <ul className="mt-1 space-y-0.5">{run.log.map((l, k) => <li key={k}>{new Date(l.t).toLocaleTimeString()} · {l.text}</li>)}</ul>
              </details>
            )}
          </div>
        </div>
      </main>
      {call && <CallInspector call={call} onClose={() => setCallId(null)} />}
    </div>
  );
}
