"use client";

/**
 * The run's panels: the book as blocks, the lectures (their chapters and the content each teaches from), the
 * transcripts, every call, the costs, and the models. Selecting a lecture, a chapter or a block lights its source up
 * in the PDF beside them.
 */

import { useState } from "react";
import type { Call, Chapter, LectureState, Run } from "@/lib/types";
import { beatFigures, chaptersOf } from "@/lib/script-figures";
import { kindOf } from "@/lib/source/blocks";
import { linesOf } from "@/lib/source/book";
import { CHECK_STYLE, money, seconds } from "./call-inspector";

export type Selection = { kind: "lecture"; n: number } | { kind: "block"; id: string }
  | { kind: "blocks"; ids: string[]; label: string } | null;

export const LECTURE_COLORS = [
  "rgba(250, 204, 21, 0.32)", "rgba(56, 189, 248, 0.32)", "rgba(244, 114, 182, 0.32)", "rgba(74, 222, 128, 0.32)",
  "rgba(251, 146, 60, 0.32)", "rgba(167, 139, 250, 0.32)", "rgba(45, 212, 191, 0.32)", "rgba(248, 113, 113, 0.32)",
];
export const lectureColor = (n: number) => LECTURE_COLORS[(n - 1) % LECTURE_COLORS.length];
export const solid = (n: number) => lectureColor(n).replace(/[\d.]+\)$/, "1)");

const KIND_TONE: Record<ReturnType<typeof kindOf>, string> = {
  heading: "text-sky-300", text: "text-neutral-400", figure: "text-violet-300", table: "text-amber-300", caption: "text-pink-300",
  furniture: "text-neutral-600",
};
const shortId = (id: string) => id.replace(/^\/page\/(\d+)\//, (_, p) => `p${Number(p) + 1}/`);

function CallsLink({ run, ids, onCall }: { run: Run; ids: string[]; onCall: (id: string) => void }) {
  if (!ids.length) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((id) => {
        const c = run.calls.find((x) => x.id === id);
        if (!c) return null;
        return (
          <button key={id} onClick={(e) => { e.stopPropagation(); onCall(id); }}
            className="rounded border border-neutral-700 px-1.5 py-px text-[10px] text-neutral-300 hover:bg-neutral-800">
            {c.step} {id}{c.status === "running" ? " …" : c.status === "failed" ? " ✗" : ""}
          </button>
        );
      })}
    </span>
  );
}

function BlockChips({ ids, run, select, tone }: { ids: string[]; run: Run; select: (s: Selection) => void; tone?: (id: string) => string }) {
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((id) => {
        const b = run.blocks.find((x) => x.id === id);
        return (
          <button key={id} title={b ? `${b.id} · ${b.type}: ${b.text.slice(0, 200)}` : id}
            onClick={(e) => { e.stopPropagation(); select({ kind: "block", id }); }}
            className={`rounded bg-neutral-800 px-1.5 py-px text-[10px] hover:bg-neutral-700 ${tone?.(id) ?? "text-neutral-300"}`}>
            {shortId(id)}{b ? <span className={`ml-1 ${KIND_TONE[kindOf(b.type)]}`}>{kindOf(b.type) === "heading" ? b.text.slice(0, 40) : b.type}</span> : null}
          </button>
        );
      })}
    </span>
  );
}

// ─── Book ────────────────────────────────────────────────────────────────────────────────────────────────────────

export function BookPanel({ run, selection, select }: { run: Run; selection: Selection; select: (s: Selection) => void }) {
  const home = new Map(run.lectures.flatMap((l) => l.blocks.map((id) => [id, l.n] as const)));
  const skipped = new Map(run.skipped.map((s) => [s.block, s.reason]));
  const [raw, setRaw] = useState(false);
  return (
    <div className="space-y-1" data-testid="book">
      <p className="mb-2 text-xs text-neutral-400">The book as Datalab read it: {run.blocks.length} blocks, each with Datalab's id, type and HTML (what
        the models read; the boxes are only for the PDF). The colour is the lecture it was placed in. Click a block to see it in the PDF.
        <button className="ml-2 rounded border border-neutral-700 px-1.5" onClick={() => setRaw(!raw)}>{raw ? "show text" : "show HTML"}</button></p>
      {run.blocks.map((b) => {
        const n = home.get(b.id);
        const chosen = selection?.kind === "block" && selection.id === b.id;
        const kind = kindOf(b.type);
        return (
          <div key={b.id} onClick={() => select(chosen ? null : { kind: "block", id: b.id })} data-testid="book-block"
            className={`flex cursor-pointer gap-2 rounded px-2 py-1 text-xs ${chosen ? "bg-neutral-800 ring-1 ring-white/50" : "hover:bg-neutral-900"}`}>
            <span className="mono w-28 shrink-0 truncate text-neutral-500" title={b.id}>{b.id}</span>
            <span className="w-14 shrink-0" title={n ? `lecture ${n}` : skipped.has(b.id) ? `skipped: ${skipped.get(b.id)}` : "not placed yet"}>
              {n ? <span className="rounded px-1 text-[10px] text-black" style={{ background: solid(n) }}>L{n}</span>
                : skipped.has(b.id) ? <span className="text-[10px] text-neutral-500">skipped</span> : <span className="text-neutral-700">·</span>}
            </span>
            <span className={`w-24 shrink-0 truncate ${KIND_TONE[kind]}`} title={b.type}>{b.type}</span>
            <span className={kind === "heading" ? "font-semibold text-neutral-100" : "text-neutral-300"}>
              {raw ? <code className="mono text-[11px] text-neutral-400">{b.html}</code> : (b.text.length > 260 ? `${b.text.slice(0, 260)}…` : b.text || <i className="text-neutral-600">(picture)</i>)}
              {b.description && <span className="block text-violet-300/80">shows: {b.description}</span>}
              {skipped.has(b.id) && <span className="block text-neutral-500">skipped: {skipped.get(b.id)}</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Lectures (as the writer structured them) ────────────────────────────────────────────────────────────────────

/** The book's blocks no lecture teaches from (headings, furniture and the skipped aside). */
function notTaught(run: Run): string[] {
  const used = new Set(run.lectures.flatMap((l) => [...l.blocks, ...chaptersOf(run, l.n).flatMap((c) => [...(c.content ?? []), ...c.beats.flatMap(beatFigures)])]));
  const skipped = new Set(run.skipped.map((x) => x.block));
  return run.blocks.filter((b) => !used.has(b.id) && !skipped.has(b.id) && !["heading", "furniture"].includes(kindOf(b.type))).map((b) => b.id);
}

export function LecturesPanel({ run, selection, select, onCall }: { run: Run; selection: Selection; select: (s: Selection) => void;
  onCall: (id: string) => void }) {
  const writing = run.steps.find((s) => s.key === "write")?.status === "running";
  const left = run.lectures.length ? notTaught(run) : [];
  const chapters = run.lectures.reduce((k, l) => k + chaptersOf(run, l.n).length, 0);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-400">
        {run.lectures.length
          ? <span>{run.lectures.length} lecture{run.lectures.length > 1 ? "s" : ""}, {chapters} chapters, each lecture written as its script in one call
            (the writer decides where it ends){run.skipped.length ? `; ${run.skipped.length} blocks skipped as furniture` : ""}. Click a chapter to see the
            book&apos;s content it teaches from (chapters may share it).</span>
          : <span>{writing ? "The writer is writing the first lecture…" : "Not written yet."}</span>}
      </div>
      {left.length > 0 && !writing && (
        <p className="flex flex-wrap items-center gap-1 text-[11px] text-amber-300">{left.length} block(s) of the book no lecture teaches from:
          <BlockChips ids={left} run={run} select={select} tone={() => "text-amber-300"} /></p>
      )}
      {run.lectures.map((l) => {
        const active = selection?.kind === "lecture" && selection.n === l.n;
        const chs = chaptersOf(run, l.n);
        const words = l.text ? l.text.split(/\s+/).length : 0;
        return (
          <section key={l.n} onClick={() => select(active ? null : { kind: "lecture", n: l.n })} data-testid="plan-lecture"
            className={`cursor-pointer rounded border p-3 ${active ? "border-white/60 bg-neutral-800/60" : "border-neutral-800 bg-neutral-900/60 hover:border-neutral-600"}`}>
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: solid(l.n) }} />
              <h3 className="text-sm font-semibold text-neutral-100">Lecture {l.n}: {l.title}</h3>
              <span className="text-[11px] text-neutral-500">{chs.length} chapters · {chs.reduce((k, c) => k + c.beats.length, 0)} beats · {l.blocks.length} blocks
                {words ? ` · ${words} words (about ${Math.round(words / 130)} min)` : ""}</span>
              <StatusDot status={l.status} />
            </div>
            {l.why && <p className="mt-1 text-xs text-neutral-400">{l.why}</p>}
            <ol className="mt-2 space-y-1">
              {chs.map((c) => <ChapterRow key={c.n} run={run} lecture={l.n} chapter={c} selection={selection} select={select} />)}
            </ol>
            {!chs.length && <div className="mt-2"><BlockChips ids={l.blocks} run={run} select={select} /></div>}
            <div className="mt-2"><CallsLink run={run} ids={l.calls} onCall={onCall} /></div>
          </section>
        );
      })}
    </div>
  );
}

/** A chapter: its title card and stage, its beats and figures, and its content (clicked: lit up in the PDF). */
function ChapterRow({ run, lecture, chapter, selection, select }: { run: Run; lecture: number; chapter: Chapter; selection: Selection; select: (s: Selection) => void }) {
  const label = `lecture ${lecture}, chapter ${chapter.n}`;
  const chosen = selection?.kind === "blocks" && selection.label === label;
  const content = chapter.content ?? [];
  const figures = [...new Set(chapter.beats.flatMap(beatFigures))];
  const shared = content.filter((id) => run.lectures.some((l) => chaptersOf(run, l.n).some((c) => (l.n !== lecture || c.n !== chapter.n) && (c.content ?? []).includes(id))));
  return (
    <li onClick={(e) => { e.stopPropagation(); select(chosen ? null : { kind: "blocks", ids: content, label }); }} data-testid="lecture-chapter"
      className={`rounded px-1.5 py-1 ${chosen ? "bg-sky-950/70 ring-1 ring-sky-500" : "hover:bg-neutral-800"}`}>
      <div className="flex flex-wrap items-baseline gap-2 text-xs">
        <span className="text-neutral-100"><span className="text-neutral-500">{chapter.n}.</span> {chapter.title}</span>
        <span className={`rounded px-1 text-[10px] ${chapter.map ? "bg-emerald-950 text-emerald-300" : "bg-neutral-800 text-neutral-400"}`}>{chapter.map ? "map" : "board"}</span>
        <span className="text-[11px] text-neutral-500">{chapter.beats.length} beats · {content.length} block(s){shared.length ? ` (${shared.length} shared with other chapters)` : ""}
          {figures.length ? ` · ${figures.length} figure(s) on ${chapter.beats.filter((b) => beatFigures(b).length).length} beat(s)` : ""}</span>
      </div>
      {chosen && <div className="mt-1"><BlockChips ids={content} run={run} select={select} tone={(id) => (shared.includes(id) ? "text-sky-300" : "")} /></div>}
    </li>
  );
}

function StatusDot({ status }: { status: LectureState["status"] }) {
  const tone = { waiting: "bg-neutral-600", writing: "bg-sky-400 animate-pulse", written: "bg-emerald-400", failed: "bg-red-500" }[status];
  return <span className={`ml-auto h-2 w-2 shrink-0 rounded-full ${tone}`} title={status} />;
}

// ─── Transcript ──────────────────────────────────────────────────────────────────────────────────────────────────

/** The transcript: each lecture's words, chapter by chapter, beat by beat (a beat's sentences together, numbered). */
export function TranscriptPanel({ run, selection, select, onCall }: { run: Run; selection: Selection; select: (s: Selection) => void;
  onCall: (id: string) => void }) {
  const words = run.lectures.reduce((n, l) => n + (l.text ? l.text.split(/\s+/).length : 0), 0);
  return (
    <div className="space-y-3">
      <p className="text-xs text-neutral-400">{words.toLocaleString()} words written (about {Math.round(words / 130)} min). Each lecture is its
        chapters and beats: the beats&apos; words, in order, are the transcript. Click a chapter&apos;s title to light up its content in the PDF.</p>
      {run.lectures.map((l) => {
        const active = selection?.kind === "lecture" && selection.n === l.n;
        const lines = linesOf(l.text ?? "");
        const chs = chaptersOf(run, l.n);
        return (
          <section key={l.n} className={`rounded border p-3 ${active ? "border-white/60" : "border-neutral-800"} bg-neutral-900/60`} data-testid="transcript-lecture">
            <div className="flex cursor-pointer items-center gap-2" onClick={() => select(active ? null : { kind: "lecture", n: l.n })}>
              <span className="h-3 w-3 rounded-sm" style={{ background: solid(l.n) }} />
              <h3 className="text-sm font-semibold text-neutral-100">Lecture {l.n}: {l.title}</h3>
              <span className="text-[11px] text-neutral-500">{l.text ? `${l.text.split(/\s+/).length} words, about ${Math.round(l.text.split(/\s+/).length / 130)} min` : l.status}</span>
              <StatusDot status={l.status} />
            </div>
            {l.text && chs.length ? (
              <div className="mt-2 space-y-3 text-[13.5px] leading-relaxed text-neutral-200">
                {chs.map((c) => (
                  <div key={c.n}>
                    <button className="mb-1 text-left text-xs font-semibold text-sky-300 hover:underline"
                      onClick={() => select({ kind: "blocks", ids: c.content ?? [], label: `lecture ${l.n}, chapter ${c.n}` })}>
                      Chapter {c.n}: {c.title} <span className="font-normal italic text-neutral-500">“{c.narration}”</span></button>
                    <p>
                      {c.beats.map((b) => (
                        <span key={b.n} className="mr-1" title={`beat ${b.n}: ${b.show}`}>
                          {b.lines.map((k) => <span key={k}><sup className="mr-0.5 text-[9px] text-neutral-600">{k}</sup>{lines[k - 1]} </span>)}
                        </span>
                      ))}
                    </p>
                  </div>
                ))}
              </div>
            ) : l.text ? (
              <div className="mt-2 space-y-2 text-[13.5px] leading-relaxed text-neutral-200">
                {l.text.split(/\n\s*\n/).map((para, p) => <p key={p}>{para}</p>)}
              </div>
            ) : <p className="mt-2 text-xs text-neutral-500">{l.status === "writing" ? "Being written…" : l.status === "failed" ? "Could not be written." : "Not written yet."}</p>}
            <div className="mt-2"><CallsLink run={run} ids={l.calls} onCall={onCall} /></div>
          </section>
        );
      })}
    </div>
  );
}

// ─── Calls ───────────────────────────────────────────────────────────────────────────────────────────────────────

export function CallsPanel({ run, onCall, lecture }: { run: Run; onCall: (id: string) => void; lecture?: number }) {
  const [step, setStep] = useState("all");
  const steps = ["all", ...new Set(run.calls.map((c) => c.step))];
  const rows = run.calls.filter((c) => (step === "all" || c.step === step) && (!lecture || c.lecture === lecture || !c.lecture));
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1 text-xs">
        {steps.map((s) => (
          <button key={s} onClick={() => setStep(s)}
            className={`rounded border px-2 py-0.5 ${step === s ? "border-white/60 bg-neutral-800" : "border-neutral-700 hover:bg-neutral-800"}`}>{s}</button>
        ))}
        {lecture ? <span className="text-neutral-500">· lecture {lecture} and the book-wide calls</span> : null}
      </div>
      <table className="w-full text-left text-xs" data-testid="calls-table">
        <thead className="text-[10px] uppercase tracking-wide text-neutral-500">
          <tr><th className="py-1">#</th><th>Call</th><th>Model</th><th>Status</th><th className="text-right">Time</th>
            <th className="text-right">In / out</th><th className="text-right">Cost</th><th className="pl-3">Checks</th></tr>
        </thead>
        <tbody>{rows.map((c) => <CallRow key={c.id} call={c} onCall={onCall} />)}</tbody>
      </table>
      {!rows.length && <p className="text-sm text-neutral-500">No calls yet.</p>}
    </div>
  );
}

function CallRow({ call, onCall }: { call: Call; onCall: (id: string) => void }) {
  const count = (r: keyof typeof CHECK_STYLE) => call.checks.filter((c) => c.result === r).length;
  return (
    <tr onClick={() => onCall(call.id)} className="cursor-pointer border-t border-neutral-800 hover:bg-neutral-900" data-testid="call-row">
      <td className="py-1 text-neutral-500">{call.id}</td>
      <td className="text-neutral-100">{call.label}</td>
      <td className="max-w-[12rem] truncate text-neutral-400" title={call.model}>{call.provider === "fixture" ? "stand-in" : call.model}</td>
      <td className={call.status === "failed" ? "text-red-300" : call.status === "done" ? "text-emerald-300" : "text-sky-300"}>
        {call.status}{call.attempts.length > 1 ? ` (${call.attempts.length} tries)` : ""}</td>
      <td className="text-right text-neutral-300">{seconds(call.started, call.ended)}</td>
      <td className="text-right text-neutral-300">{call.usage ? `${(call.usage.input / 1000).toFixed(1)}k / ${(call.usage.output / 1000).toFixed(1)}k` : ""}</td>
      <td className="text-right text-neutral-100">{money(call.cost)}</td>
      <td className="pl-3">
        {(["pass", "fixed", "fail", "info"] as const).map((r) => count(r) ? (
          <span key={r} className={`mr-2 ${CHECK_STYLE[r].tone}`}>{CHECK_STYLE[r].icon}{count(r)}</span>) : null)}
      </td>
    </tr>
  );
}

// ─── Costs ───────────────────────────────────────────────────────────────────────────────────────────────────────

type CostRow = { calls: number; input: number; output: number; cost: number; time: number };

export function CostsPanel({ run }: { run: Run }) {
  const total = run.calls.reduce((n, c) => n + c.cost, 0);
  const group = (key: (c: Call) => string): [string, CostRow][] => {
    const out = new Map<string, CostRow>();
    for (const c of run.calls) {
      const k = key(c);
      const row = out.get(k) ?? { calls: 0, input: 0, output: 0, cost: 0, time: 0 };
      row.calls += 1;
      row.input += c.usage?.input ?? 0;
      row.output += c.usage?.output ?? 0;
      row.cost += c.cost;
      row.time += c.ended ? c.ended - c.started : 0;
      out.set(k, row);
    }
    return [...out.entries()];
  };
  const Table = ({ title, rows }: { title: string; rows: [string, CostRow][] }) => (
    <section className="mb-4">
      <h3 className="mb-1 text-sm font-semibold text-neutral-100">{title}</h3>
      <table className="w-full text-left text-xs">
        <thead className="text-[10px] uppercase tracking-wide text-neutral-500">
          <tr><th className="py-1"> </th><th className="text-right">Calls</th><th className="text-right">Tokens in</th><th className="text-right">Tokens out</th>
            <th className="text-right">Model time</th><th className="text-right">Cost</th><th className="text-right">Share</th></tr>
        </thead>
        <tbody>
          {rows.map(([k, r]) => (
            <tr key={k} className="border-t border-neutral-800">
              <td className="py-1 text-neutral-100">{k}</td><td className="text-right">{r.calls}</td>
              <td className="text-right">{r.input.toLocaleString()}</td><td className="text-right">{r.output.toLocaleString()}</td>
              <td className="text-right">{(r.time / 1000).toFixed(0)} s</td><td className="text-right text-neutral-100">{money(r.cost)}</td>
              <td className="text-right text-neutral-400">{total ? `${Math.round((r.cost / total) * 100)}%` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
  return (
    <div data-testid="costs">
      <p className="mb-3 text-sm text-neutral-300">Total {money(total)} for {run.calls.length} calls
        {run.calls.some((c) => c.provider === "fixture") ? " (offline stand-in calls cost nothing)" : ""}.
        {" "}Costs are OpenRouter's own figures for each call (usage.cost).</p>
      <Table title="By step" rows={group((c) => c.step)} />
      <Table title="By model" rows={group((c) => (c.provider === "fixture" ? `${c.model} (stand-in)` : c.model))} />
      <Table title="By lecture" rows={group((c) => (c.lecture ? `Lecture ${c.lecture}` : "Book-wide (figures, plan)"))} />
    </div>
  );
}

// ─── Models ──────────────────────────────────────────────────────────────────────────────────────────────────────

type ModelCheck = { model: string; ok: boolean; seconds: number; cost: number; reply?: string; error?: string;
  prices?: { input: number; output: number }; context?: number; fixture?: boolean; outputs?: string[] };

/** A role as the page knows it (lib/models.ts ResolvedModel): its model from the environment and where that came from. */
export type RoleModel = { role: string; label: string; what: string; kind: "text" | "vision" | "image" | "decision"; env: string[]; used: boolean;
  model: string; source: string };

const KIND_LABEL = { text: "writes text", vision: "reads images", image: "makes images", decision: "decides (typed answer)" } as const;

/**
 * Every model, by its role: the one in use (from .env unless changed here), where it came from, what it does, and a
 * check (a one-word call; for an image model, whether an image comes back). Changing one here changes it for the
 * runs started or continued from now on.
 */
export function ModelsPanel({ roles, values, change }: { roles: RoleModel[]; values: Record<string, string | undefined>;
  change?: (role: string, model: string) => void }) {
  const [results, setResults] = useState<Record<string, ModelCheck | "checking">>({});
  const check = async (role: string, model: string, kind: string) => {
    setResults((r) => ({ ...r, [role]: "checking" }));
    const res = await fetch("/api/models", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model, kind }) });
    const json = await res.json();
    setResults((r) => ({ ...r, [role]: json }));
  };
  return (
    <div className="space-y-2" data-testid="models">
      <p className="text-xs text-neutral-400">Every model, from <span className="mono">.env.local</span> (v2&apos;s, else v1&apos;s): the variable each
        came from is shown. Change one here for the runs you start or continue next; Check makes a tiny call (an image model must send an image back).</p>
      {roles.map((r) => {
        const value = values[r.role] ?? r.model;
        const changed = value !== r.model;
        const res = results[r.role];
        return (
          <div key={r.role} className="rounded border border-neutral-800 bg-neutral-900/60 p-2 text-sm" data-testid={`model-${r.role}`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-32 font-medium text-neutral-200">{r.label}</span>
              <span className={`rounded px-1.5 py-px text-[10px] ${r.kind === "image" ? "bg-pink-950 text-pink-300" : r.kind === "decision" ? "bg-emerald-950 text-emerald-300" : r.kind === "vision" ? "bg-sky-950 text-sky-300" : "bg-neutral-800 text-neutral-300"}`}>{KIND_LABEL[r.kind]}</span>
              {change ? (
                <input className="mono w-72 rounded border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-xs text-neutral-100" value={value}
                  onChange={(e) => change(r.role, e.target.value)} />
              ) : <span className="mono text-xs text-neutral-100">{value}</span>}
              <span className="text-[11px] text-neutral-500">{changed ? <>changed here · <button className="underline" onClick={() => change?.(r.role, r.model)}>back to {r.source === "default" ? "the default" : r.source}</button></>
                : r.source === "default" ? `default (set ${r.env[0]} in .env.local)` : `from ${r.source}`}</span>
              <button onClick={() => check(r.role, value, r.kind)} className="ml-auto rounded border border-neutral-700 px-2 py-0.5 text-xs hover:bg-neutral-800">Check</button>
            </div>
            <p className="mt-1 text-xs text-neutral-400">{r.what}{r.used ? "" : <span className="text-amber-300/80"> Not used yet: kept for its step.</span>}</p>
            {res === "checking" && <p className="mt-1 text-xs text-sky-300">Checking…</p>}
            {res && res !== "checking" && (
              <p className={`mt-1 text-xs ${res.ok ? "text-emerald-300" : "text-red-300"}`}>
                {res.ok ? "✓ works" : "✗ fails"}{res.fixture ? " (offline stand-in)" : ` in ${res.seconds.toFixed(1)} s, ${money(res.cost)}`}
                {res.reply ? ` · ${r.kind === "image" ? res.reply : `"${res.reply}"`}` : ""}{res.error ? ` · ${res.error}` : ""}
                {res.prices ? ` · $${res.prices.input.toFixed(2)} / $${res.prices.output.toFixed(2)} per million tokens in / out` : " · prices not found"}
                {res.context ? ` · ${Math.round(res.context / 1000)}k context` : ""}
                {res.outputs ? ` · outputs: ${res.outputs.join(", ")}` : ""}
                {r.kind === "image" && res.outputs && !res.outputs.includes("image") ? " · this model does not make images" : ""}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
