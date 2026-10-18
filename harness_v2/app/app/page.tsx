"use client";

/**
 * Harness v2. A book PDF in, read by Datalab into its JSON of blocks; the lectures are written in order, each in one
 * call as its script (chapters with the book's blocks they teach from, beats with the words said, what is on screen
 * and the figures shown), with the whole book and every lecture before it; then the figures, the scenes. Every step,
 * every call (its prompt part by part, output, checks, cost) and every block's place in the PDF is in view.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { DocumentInfo, Options, Run } from "@/lib/types";
import { PdfView, type Mark } from "@/components/pdf-view";
import { CallInspector, money } from "@/components/call-inspector";
import { BookPanel, CallsPanel, CostsPanel, LecturesPanel, ModelsPanel, TranscriptPanel, lectureColor, type RoleModel, type Selection } from "@/components/panels";
import { FiguresPanel } from "@/components/figures-panel";
import { GenerationPanel } from "@/components/generation-panel";
import { ScriptPanel } from "@/components/script-panel";
import { ScenesPanel } from "@/components/scenes-panel";
import { VoicePanel } from "@/components/voice-panel";
import { LabPanel } from "@/components/lab-panel";
import { voiceRunning } from "@/lib/voice-engines";
import { choiceOf } from "@/lib/triage-kinds";

type Config = { hasKey: boolean; datalab: boolean; voices?: Record<string, boolean>; models: Record<string, RoleModel>; triageModel: string };
/** A role's key in a run's options ("planner" -> plannerModel). */
const optionKey = (role: string) => `${role}Model` as keyof Options;
type RunRow = { id: string; documentName: string; created: number; status: string; cost: number; lectures: string; triage?: string };
const TABS = ["Lectures", "Book", "Transcript", "Figures", "Generate", "Script", "Scenes", "Voice", "Lab", "Calls", "Costs", "Models"] as const;

export default function Page() {
  const [config, setConfig] = useState<Config | null>(null);
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [poke, setPoke] = useState(0);
  const [docId, setDocId] = useState("");
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [options, setOptions] = useState<Partial<Options>>({ lectureMinutes: 27, language: "auto", subject: "", effort: "medium" });
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Lectures");
  const [selection, setSelection] = useState<Selection>(null);
  const [callId, setCallId] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  // The PDF's share of the width (%), dragged on the divider; 0 hides it. Kept in this browser.
  const [pdfWidth, setPdfWidth] = useState(44);
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem("v2.pdfWidth"));
      if (saved >= 0 && saved <= 80 && localStorage.getItem("v2.pdfWidth") !== null) setPdfWidth(saved);
    } catch { /* no storage: the default */ }
  }, []);
  const widen = (w: number) => {
    const next = w < 12 ? 0 : Math.min(75, w);
    setPdfWidth(next);
    try { localStorage.setItem("v2.pdfWidth", String(next)); } catch { /* not kept */ }
  };
  useEffect(() => {
    if (!dragging) return;
    const move = (e: PointerEvent) => widen((e.clientX / window.innerWidth) * 100);
    const up = () => setDragging(false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, [dragging]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = useCallback(async () => {
    const [d, r] = await Promise.all([fetch("/api/documents").then((x) => x.json()), fetch("/api/runs").then((x) => x.json())]);
    setDocs(d.documents ?? []);
    setRuns(r.runs ?? []);
  }, []);

  useEffect(() => {
    fetch("/api/config").then((r) => r.json()).then((c: Config) => {
      setConfig(c);
      // Every model from the environment (.env.local): nothing to type.
      setOptions((o) => ({ ...Object.fromEntries(Object.values(c.models).map((m) => [optionKey(m.role), m.model])), ...o }));
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
      setDocId(next.documentId);
      if (next.status === "running" || next.triage?.status === "running" || next.generation?.status === "running" || next.script?.status === "running"
        || next.scenes?.status === "running" || (next.scenes?.renders ?? 0) > 0 || voiceRunning(next)) setTimeout(tick, 1000);
      else void refresh();
    };
    void tick();
    history.replaceState(null, "", `?run=${runId}`);
    return () => {
      stop = true;
    };
  }, [runId, refresh, poke]);

  // A run picked from the list brings its options back, so continuing it shows what it was made with.
  useEffect(() => {
    if (run) setOptions(run.options);
  }, [run?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const busy = run?.status === "running" || run?.triage?.status === "running" || run?.generation?.status === "running" || run?.script?.status === "running" || run?.scenes?.status === "running" || (run?.scenes?.renders ?? 0) > 0 || voiceRunning(run);
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [busy]);

  /** An action on the run (continue, stop, redo a step, the triage's): then follow it again. */
  const act = async (path: string, body: Record<string, unknown>) => {
    setError(null);
    const res = await fetch(`/api/runs/${runId}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError(json.error ?? "that did not work");
      return false;
    }
    setPoke((n) => n + 1);
    return true;
  };

  const importFile = async (file: File) => {
    setError(null);
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/runs/import", { method: "POST", body: form });
    const json = await res.json();
    if (!res.ok) return setError(json.error ?? "the import failed");
    await refresh();
    setSelection(null);
    setRunId(json.id);
  };

  const upload = async (file: File) => {
    setUploading(`Reading ${file.name} with ${config?.datalab ? "Datalab" : "the offline reader (no DATALAB_API_KEY)"}…`);
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

  /** A new run: the whole transcript, or only so far (`until` "read" or "figures") for the figure triage. */
  const start = async (until?: "read" | "figures", then: (typeof TABS)[number] = "Lectures") => {
    setError(null);
    const res = await fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documentId: docId, options, until }) });
    const json = await res.json();
    if (!res.ok) return setError(json.error ?? "the run could not start");
    setSelection(null);
    setRun(null);
    setRunId(json.id);
    setTab(then);
  };

  // What the PDF lights up, by Datalab's boxes: every block in its lecture's colour; a lecture's blocks; a chapter's
  // content (or any set of blocks); one block.
  const marks: Mark[] = useMemo(() => {
    if (!run) return [];
    if (tab === "Figures" && selection?.kind !== "block") {
      // The figures, each in the colour of the way it is shown (grey: not triaged yet).
      return run.blocks.filter((b) => b.image).map((b) => {
        const f = run.triage?.figures[b.id];
        const kind = f?.override ?? (f?.status === "done" ? f.kind : undefined);
        return { id: b.id, page: b.page, box: b.box, color: choiceOf(kind)?.color ?? "rgba(148,163,184,0.35)",
          label: `${b.id} · ${kind ? choiceOf(kind)!.label : f?.status ?? "not triaged"}` };
      });
    }
    const home = new Map(run.lectures.flatMap((l) => l.blocks.map((id) => [id, l.n] as const)));
    const mark = (id: string, color: string, strong = false): Mark | null => {
      const b = run.blocks.find((x) => x.id === id);
      return b ? { id, page: b.page, box: b.box, color, strong, label: `${b.id} · ${b.type}${home.get(id) ? ` · lecture ${home.get(id)}` : ""}` } : null;
    };
    const ok = (m: Mark | null): m is Mark => !!m;
    if (selection?.kind === "block") return [mark(selection.id, lectureColor(home.get(selection.id) ?? 1), true)].filter(ok);
    if (selection?.kind === "blocks") return selection.ids.map((id) => mark(id, lectureColor(home.get(id) ?? 1), true)).filter(ok);
    if (selection?.kind === "lecture") {
      const lecture = run.lectures.find((l) => l.n === selection.n);
      return (lecture?.blocks ?? []).map((id) => mark(id, lectureColor(selection.n), true)).filter(ok);
    }
    return run.blocks.map((b) => mark(b.id, home.has(b.id) ? lectureColor(home.get(b.id)!) : "rgba(148,163,184,0.15)")).filter(ok);
  }, [run, selection, tab]);

  const call = run?.calls.find((c) => c.id === callId) ?? null;
  const total = run?.calls.reduce((n, c) => n + c.cost, 0) ?? 0;
  const tokens = run?.calls.reduce((n, c) => n + (c.usage?.input ?? 0) + (c.usage?.output ?? 0), 0) ?? 0;
  const elapsed = run ? ((run.ended ?? now) - run.created) / 1000 : 0;
  const input = "rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-100";
  const doc = docs.find((d) => d.id === docId);

  return (
    <div className="flex h-screen flex-col">
      <header className="border-b border-neutral-800 px-4 py-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-sm font-semibold text-neutral-100">Harness v2 <span className="text-neutral-500">· Transcript, figures, script, scenes</span></h1>
          <select className={input} value={docId} onChange={(e) => { setDocId(e.target.value); setRun(null); setRunId(""); setSelection(null); }} data-testid="doc-select">
            <option value="">Choose a book…</option>
            {docs.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.pages} pages, {d.words.toLocaleString()} words, {d.source})</option>)}
          </select>
          <label className="cursor-pointer rounded border border-neutral-600 px-2 py-1 text-xs text-neutral-200 hover:bg-neutral-800">
            Upload PDF
            <input type="file" accept="application/pdf" className="hidden" data-testid="upload"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
          {uploading && <span className="text-xs text-sky-300">{uploading}</span>}
          <select className={input} value={runId} onChange={(e) => { setSelection(null); setRunId(e.target.value); }}>
            <option value="">Past runs…</option>
            {runs.map((r) => <option key={r.id} value={r.id}>{new Date(r.created).toLocaleString()} · {r.documentName} · {r.status} · {r.lectures}{r.triage ? ` · ${r.triage}` : ""} · {money(r.cost)}</option>)}
          </select>
          <label className="cursor-pointer rounded border border-neutral-600 px-2 py-1 text-xs text-neutral-200 hover:bg-neutral-800" title="An exported transcript (.panim-transcript.json): it becomes a run with its book, to go on from">
            Import transcript
            <input type="file" accept="application/json,.json,.panim-transcript.json" className="hidden" data-testid="import"
              onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
          </label>
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
          <span title="Told to the planner as context: how long one lecture (one video) is meant to be">Lecture length (min)</span>
          <input className={`${input} w-14`} type="number" min={3} value={options.lectureMinutes ?? 27}
            onChange={(e) => setOptions({ ...options, lectureMinutes: Number(e.target.value) })} />
          <span>Language</span>
          <select className={input} value={options.language} onChange={(e) => setOptions({ ...options, language: e.target.value as Options["language"] })}>
            {["auto", "english", "hindi", "hinglish"].map((l) => <option key={l}>{l}</option>)}
          </select>
          <span>Subject</span>
          <input className={`${input} w-28`} placeholder="(optional)" value={options.subject ?? ""} onChange={(e) => setOptions({ ...options, subject: e.target.value })} />
          <span title="From .env.local; change them in the Models tab">Models</span>
          <button className="mono max-w-[30rem] truncate rounded border border-neutral-800 px-2 py-1 text-left text-[11px] text-neutral-300 hover:bg-neutral-800"
            onClick={() => setTab("Models")} data-testid="models-summary" title="Change in the Models tab">
            {options.writerModel} · {options.figureModel}
          </button>
          <span title="The writer's reasoning: it writes each lecture as its script (chapters, beats) in one call">Writer effort</span>
          <select className={input} value={options.writerEffort ?? "high"} onChange={(e) => setOptions({ ...options, writerEffort: e.target.value as Options["effort"] })}
            data-testid="writer-effort">
            {["low", "medium", "high", "off"].map((l) => <option key={l}>{l}</option>)}
          </select>
          <span title="Every other call's reasoning (figures, triage, scenes...)">Effort</span>
          <select className={input} value={options.effort} onChange={(e) => setOptions({ ...options, effort: e.target.value as Options["effort"] })}>
            {["low", "medium", "high", "off"].map((l) => <option key={l}>{l}</option>)}
          </select>
          <button disabled={!docId || run?.status === "running"} onClick={() => start()} data-testid="start"
            className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white disabled:opacity-40">Build the transcript</button>
          {config && !config.hasKey && <span className="text-amber-300">No OPENROUTER_API_KEY: calls are answered by the offline stand-in.</span>}
          {config && !config.datalab && <span className="text-amber-300">No DATALAB_API_KEY: PDFs are read offline (pictures cut from the PDF; no captions, no bold).</span>}
          {error && <span className="text-red-300" data-testid="error">{error}</span>}
        </div>
        {run && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs" data-testid="run-actions">
            <span className="text-neutral-500">This run:</span>
            {run.status === "running"
              ? <button className="rounded border border-red-700 px-2 py-0.5 text-red-200 hover:bg-red-950" onClick={() => act("", { action: "stop" })}>Stop</button>
              : run.status !== "done" && !run.legacy && <button className="rounded border border-emerald-700 px-2 py-0.5 text-emerald-200 hover:bg-emerald-950" data-testid="continue"
                  title="Keep every step done so far and do only what is left, with the models above" onClick={() => act("", { action: "continue", options })}>Continue from where it stopped</button>}
            <a className="rounded border border-neutral-700 px-2 py-0.5 text-neutral-200 hover:bg-neutral-800" href={`/api/runs/${run.id}/export?format=json`} data-testid="export-json"
              title="One file with everything: the lectures' numbered sentences, goals, blocks, figure triage, and the book itself (PDF, Datalab JSON, figures). Import it here or on another machine to go on with the next steps.">Export transcript (to import later)</a>
            <a className="rounded border border-neutral-700 px-2 py-0.5 text-neutral-200 hover:bg-neutral-800" href={`/api/runs/${run.id}/export?format=md`}
              title="To read; it cannot be imported">Markdown (to read)</a>
            {run.imported && <span className="text-neutral-500">imported from {run.imported.file}</span>}
            <span className="text-neutral-500">Saved as it goes: pick it again from Past runs at any time.</span>
          </div>
        )}
        {run && (
          <ol className="mt-2 flex flex-wrap gap-2 text-xs" data-testid="steps">
            {run.steps.map((s, k) => (
              <li key={s.key} className={`rounded border px-2 py-1 ${s.status === "done" ? "border-emerald-800 bg-emerald-950/40" :
                s.status === "running" ? "border-sky-700 bg-sky-950/40" : s.status === "failed" ? "border-red-800 bg-red-950/40" : "border-neutral-800"}`}>
                <span className="text-neutral-500">{k + 1}.</span> <span className="text-neutral-100">{s.label}</span>
                {s.started && <span className="text-neutral-500"> · {Math.round(((s.ended ?? now) - s.started) / 1000)} s</span>}
                {run.status !== "running" && (s.status === "done" || s.status === "failed") && (
                  <button className="ml-1 text-neutral-500 hover:text-neutral-200" title={`Make "${s.label}" again, and the steps after it (the others are kept)`}
                    onClick={() => confirm(`Make "${s.label}" and every step after it again? Their saved results are cleared.`) && act("", { action: "redo", step: s.key, options })}>↻ redo</button>
                )}
                {s.summary && <span className="block max-w-[34rem] text-[11px] text-neutral-400">{s.summary}</span>}
              </li>
            ))}
          </ol>
        )}
        {run?.legacy && <p className="mt-1 text-xs text-amber-300" data-testid="legacy">{run.legacy}</p>}
        {run?.error && <p className="mt-1 text-xs text-red-300">{run.error}</p>}
      </header>

      <main className={`flex min-h-0 flex-1 ${dragging ? "cursor-col-resize select-none" : ""}`}>
        {pdfWidth > 0 && (
          <div className="min-w-[220px] shrink-0" style={{ width: `${pdfWidth}%` }} data-testid="pdf-pane">
            {docId ? <PdfView url={`/api/documents/${docId}/pdf`} marks={marks} focusKey={JSON.stringify(selection)}
              onPick={(id) => setSelection({ kind: "block", id })} />
              : <div className="p-6 text-sm text-neutral-400">Upload a book's PDF, or choose one, to begin.</div>}
          </div>
        )}
        <div onPointerDown={(e) => { e.preventDefault(); setDragging(true); }} onDoubleClick={() => widen(pdfWidth ? 0 : 44)} data-testid="divider"
          title="Drag to make the panels wider or narrower; double-click to hide or show the PDF"
          className={`group relative w-1.5 shrink-0 cursor-col-resize border-x border-neutral-800 ${dragging ? "bg-sky-600" : "bg-neutral-900 hover:bg-sky-800"}`}>
          <span className="absolute left-1/2 top-1/2 h-8 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded bg-neutral-600 group-hover:bg-sky-300" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <nav className="flex flex-wrap items-center gap-1 border-b border-neutral-800 px-3 pt-2">
            {TABS.map((t) => (
              <button key={t} onClick={() => setTab(t)} data-testid={`tab-${t}`}
                className={`rounded-t px-3 py-1.5 text-sm ${tab === t ? "bg-neutral-800 text-white" : "text-neutral-400 hover:text-neutral-200"}`}>{t}
                {t === "Calls" && run ? <span className="ml-1 text-[10px] text-neutral-500">{run.calls.length}</span> : null}
              </button>
            ))}
            <span className="ml-auto flex items-center gap-1 pb-1 text-[11px] text-neutral-400" data-testid="layout">
              <span className="text-neutral-500">PDF</span>
              {([["hide", 0], ["narrow", 25], ["half", 44], ["wide", 60]] as const).map(([label, w]) => (
                <button key={label} onClick={() => widen(w)} className={`rounded border px-1.5 ${Math.round(pdfWidth) === w ? "border-sky-600 text-sky-200" : "border-neutral-700 hover:bg-neutral-800"}`}>{label}</button>
              ))}
            </span>
            {selection && (
              <span className="flex items-center gap-2 pb-1 text-xs text-neutral-400" data-testid="selection">
                Showing {selection.kind === "lecture" ? `lecture ${selection.n}`
                  : selection.kind === "blocks" ? `${selection.label} (${selection.ids.length} blocks)` : `block ${selection.id}`} in the PDF
                <button className="rounded border border-neutral-700 px-1.5" onClick={() => setSelection(null)}>clear</button>
              </span>
            )}
          </nav>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {!run && tab !== "Models" && tab !== "Figures" && <p className="text-sm text-neutral-400">{doc ? `${doc.name}: ${doc.pages} pages read by ${doc.source}. Press Build the transcript to start.` : "No book chosen yet."}</p>}
            {run && tab === "Lectures" && <LecturesPanel run={run} selection={selection} select={setSelection} onCall={setCallId} />}
            {run && tab === "Book" && <BookPanel run={run} selection={selection} select={setSelection} />}
            {run && tab === "Transcript" && <TranscriptPanel run={run} selection={selection} select={setSelection} onCall={setCallId} />}
            {!run && tab === "Figures" && docId && (
              <div className="space-y-2 text-sm text-neutral-300" data-testid="figures-start">
                <p>Triage this book&apos;s figures without building the transcript: a run that only reads the book (and, if you like, describes its
                  figures), saved like any other. Continue builds the transcript from it later.</p>
                <div className="flex gap-2">
                  <button className="rounded bg-emerald-700 px-3 py-1 text-xs font-semibold text-white" data-testid="read-only"
                    onClick={() => start("read", "Figures")}>Read the book</button>
                  <button className="rounded border border-emerald-700 px-3 py-1 text-xs text-emerald-200"
                    title="Also describe each figure with the Figures model: the chat triage reads the description"
                    onClick={() => start("figures", "Figures")}>Read and describe the figures</button>
                </div>
              </div>
            )}
            {run && tab === "Figures" && <FiguresPanel run={run} defaultModel={(run.options.triageChatModel && run.options.triageModel) || config?.models.triage?.model || ""}
              defaultChatModel={run.options.triageChatModel || options.triageChatModel || config?.models.triageChat?.model || ""} selection={selection}
              select={setSelection} onCall={setCallId} act={(body) => act("/triage", body)} next={() => setTab("Generate")} />}
            {run && tab === "Generate" && <GenerationPanel run={run} defaultModel={run.options.imageModel || options.imageModel || config?.models.image?.model || ""}
              defaultSvgModel={run.options.svgModel || options.svgModel || config?.models.svg?.model || ""}
              defaultManimModel={run.options.manimModel || options.manimModel || config?.models.manim?.model || ""}
              defaultMapModel={run.options.mapModel || options.mapModel || config?.models.map?.model || ""}
              select={setSelection} onCall={setCallId} act={(body) => act("/generate", body)}
              setWay={(block, kind) => act("/triage", { action: "override", block, kind })} />}
            {run && tab === "Script" && <ScriptPanel run={run} select={setSelection} onCall={setCallId} />}
            {run && tab === "Scenes" && <ScenesPanel run={run} defaultModel={run.options.scenesModel || options.scenesModel || config?.models.scenes?.model || ""}
              manimModel={run.options.manimModel || options.manimModel || config?.models.manim?.model || ""}
              reuseModel={config?.models.reuse?.model || ""}
              select={setSelection} onCall={setCallId} act={(body) => act("/scenes", body)} />}
            {run && tab === "Voice" && <VoicePanel run={run} ready={config?.voices} timingModel={config?.models.timing?.model || ""}
              onCall={setCallId} act={(body) => act("/voice", body)} />}
            {run && tab === "Lab" && <LabPanel run={run} ready={config?.voices} onCall={setCallId}
              act={(body) => act("/lab", body)} voiceAct={(body) => act("/voice", body)} />}
            {run && tab === "Calls" && <CallsPanel run={run} onCall={setCallId} lecture={selection?.kind === "lecture" ? selection.n : undefined} />}
            {run && tab === "Costs" && <CostsPanel run={run} />}
            {tab === "Models" && config && <ModelsPanel roles={Object.values(config.models)}
              values={Object.fromEntries(Object.values(config.models).map((m) => [m.role, options[optionKey(m.role)] as string | undefined]))}
              change={(role, model) => setOptions((o) => ({ ...o, [optionKey(role)]: model }))} />}
            {run && run.log.length > 0 && tab === "Lectures" && (
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
