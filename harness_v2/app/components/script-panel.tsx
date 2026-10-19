"use client";

/**
 * The script: each lecture as the writer wrote it, in the same call as its transcript (run.ts): its chapters (a title
 * card, a stage, and the book's blocks each teaches from: chapters may share them) and its beats (the sentences said,
 * what is on screen, the figures shown: a figure may be on several beats). An overview of every lecture, then one
 * lecture at a time, in four views:
 *
 *   - Chapters and beats: an outline beside the chapters; clicking a chapter shows (and lights up in the PDF) the
 *     content it teaches from; a beat shows its sentences, what is on screen, and its figures;
 *   - Content: every block the lecture teaches from, with the chapters that use it (shared ones marked), and every
 *     figure with the beats it is shown on;
 *   - Prompt and answer: the writer's call (and its try again), its prompt as parts, its answer, its checks;
 *   - Checks: what code found and mended.
 */

import { useEffect, useMemo, useState } from "react";
import type { Call, Chapter, Run } from "@/lib/types";
import { linesOf } from "@/lib/source/book";
import { kindOf } from "@/lib/source/blocks";
import { beatFigures, chaptersOf, lectureFigures } from "@/lib/script-figures";
import { choiceOf } from "@/lib/triage-kinds";
import { CHECK_STYLE, Json, PromptParts, money, seconds } from "./call-inspector";
import { solidKind } from "./figures-panel";
import type { Selection } from "./panels";

const TONE = { waiting: "text-neutral-400", running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;
const VIEWS = ["Chapters and beats", "Content", "Prompt and answer", "Checks"] as const;
type View = (typeof VIEWS)[number];

type Lecture = Run["lectures"][number];

export function ScriptPanel({ run, select, onCall }: { run: Run; select: (s: Selection) => void; onCall: (id: string) => void }) {
  const [open, setOpen] = useState<number | "all">("all");
  const [view, setView] = useState<View>("Chapters and beats");
  useEffect(() => { setOpen("all"); }, [run.id]);
  const written = run.lectures.filter((l) => l.status === "written" && l.text);
  const chapters = written.reduce((k, l) => k + chaptersOf(run, l.n).length, 0);
  const beats = written.reduce((k, l) => k + chaptersOf(run, l.n).reduce((j, c) => j + c.beats.length, 0), 0);
  const lecture = open === "all" ? undefined : written.find((l) => l.n === open);

  if (!written.length) return <p className="text-sm text-neutral-400">No lecture is written yet: build the transcript. Each lecture is written as its script (chapters and beats) in the same call.</p>;
  return (
    <div className="space-y-3" data-testid="script">
      <section className="rounded border border-neutral-800 bg-neutral-900/60 p-3">
        <h3 className="text-sm font-semibold text-neutral-100">Script: chapters and beats</h3>
        <p className="text-xs text-neutral-400">Each lecture was written as its script in the same call as its transcript: <b>chapters</b> (a topic, with a
          title card, a stage, a map or a board, and the book&apos;s blocks it teaches from: chapters may share them) and <b>beats</b> (1-2 sentences said,
          what is on screen, the figures shown: a figure may be on several beats). The beats&apos; words, in order, are the transcript.</p>
        <p className="mt-2 text-xs text-neutral-300" data-testid="script-summary">{written.length} lectures · {chapters} chapters · {beats} beats</p>
      </section>
      <nav className="flex flex-wrap gap-1 border-b border-neutral-800">
        <Tab on={open === "all"} onClick={() => setOpen("all")}>All lectures</Tab>
        {written.map((l) => (
          <Tab key={l.n} on={open === l.n} onClick={() => setOpen(l.n)} title={l.title}>
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${chaptersOf(run, l.n).length ? "bg-emerald-400" : "bg-neutral-700"}`} /> Lecture {l.n}
          </Tab>
        ))}
      </nav>
      {!lecture ? <Overview run={run} written={written} openLecture={setOpen} />
        : <LectureView key={lecture.n} run={run} lecture={lecture} view={view} setView={setView} select={select} onCall={onCall} />}
    </div>
  );
}

function Tab({ on, onClick, title, children }: { on: boolean; onClick: () => void; title?: string; children: React.ReactNode }) {
  return (
    <button onClick={onClick} title={title} data-testid="script-tab"
      className={`flex items-center gap-1.5 rounded-t px-2.5 py-1 text-xs ${on ? "bg-neutral-800 text-white" : "text-neutral-400 hover:text-neutral-200"}`}>{children}</button>
  );
}

function Overview({ run, written, openLecture }: { run: Run; written: Lecture[]; openLecture: (n: number) => void }) {
  return (
    <table className="w-full text-xs" data-testid="script-overview">
      <thead className="text-left text-[10px] uppercase tracking-wide text-neutral-500">
        <tr><th className="py-1">Lecture</th><th>Sentences</th><th>Chapters</th><th>Beats</th><th>Content</th><th>Figures</th><th>Cost</th></tr>
      </thead>
      <tbody>
        {written.map((l) => {
          const chs = chaptersOf(run, l.n);
          const figs = lectureFigures(run, l.n);
          const cost = run.calls.filter((c) => l.calls.includes(c.id)).reduce((k, c) => k + c.cost, 0);
          return (
            <tr key={l.n} className="cursor-pointer border-t border-neutral-800 hover:bg-neutral-900" onClick={() => openLecture(l.n)} data-testid="script-lecture">
              <td className="py-1.5 pr-2 text-neutral-100"><b>{l.n}</b>. {l.title}</td>
              <td className="text-neutral-400">{linesOf(l.text ?? "").length}</td>
              <td>{chs.length || "—"}</td>
              <td>{chs.reduce((k, c) => k + c.beats.length, 0) || "—"}</td>
              <td>{new Set(chs.flatMap((c) => c.content ?? [])).size} blocks</td>
              <td>{figs.length ? `${figs.filter((f) => f.beats.length).length} of ${figs.length} shown` : "none"}</td>
              <td>{money(cost)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function LectureView({ run, lecture, view, setView, select, onCall }: {
  run: Run; lecture: Lecture; view: View; setView: (v: View) => void; select: (s: Selection) => void; onCall: (id: string) => void;
}) {
  const ls = run.script?.lectures[lecture.n];
  const lines = useMemo(() => linesOf(lecture.text ?? ""), [lecture.text]);
  const calls = lecture.calls.map((id) => run.calls.find((c) => c.id === id)).filter((c): c is Call => !!c && (c.step === "lecture" || c.step === "script"));
  const cost = calls.reduce((k, c) => k + c.cost, 0);
  const checks = ls?.checks ?? [];
  const fixes = checks.filter((c) => c.result === "fixed" || c.result === "fail").length;
  return (
    <section className="space-y-2" data-testid="script-lecture-view">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-sm font-semibold text-neutral-100">Lecture {lecture.n}: {lecture.title}</span>
        <span className="text-neutral-500">{lines.length} sentences · {ls?.chapters.length ?? 0} chapters · {ls?.chapters.reduce((k, c) => k + c.beats.length, 0) ?? 0} beats
          {calls.at(-1) ? ` · ${calls.at(-1)!.model} · ${seconds(calls[0].started, calls.at(-1)!.ended)}` : ""} · {money(cost)}</span>
      </div>
      {lecture.why && <p className="text-xs text-neutral-400">{lecture.why}</p>}
      <nav className="flex gap-1 text-xs">
        {VIEWS.map((v) => (
          <button key={v} onClick={() => setView(v)} data-testid="script-view"
            className={`rounded-full border px-2.5 py-0.5 ${view === v ? "border-sky-600 bg-sky-950 text-sky-100" : "border-neutral-700 text-neutral-400 hover:text-neutral-200"}`}>
            {v}{v === "Prompt and answer" && calls.length ? ` (${calls.length})` : ""}{v === "Checks" && checks.length ? ` (${fixes ? `${fixes} mended` : "all passed"})` : ""}
          </button>
        ))}
      </nav>
      {view === "Chapters and beats" && <ChaptersView run={run} lecture={lecture} lines={lines} select={select} />}
      {view === "Content" && <ContentView run={run} lecture={lecture} select={select} />}
      {view === "Prompt and answer" && <PromptView calls={calls} onCall={onCall} />}
      {view === "Checks" && (checks.length ? <CheckList checks={checks} /> : <p className="text-xs text-neutral-500">No checks.</p>)}
    </section>
  );
}

/** A figure as a small picture: its generated form when made, else the book's. */
function FigureThumb({ run, id, height = "h-16" }: { run: Run; id: string; height?: string }) {
  const way = run.triage?.figures[id]?.override ?? run.triage?.figures[id]?.kind;
  const made = run.generation?.figures[id];
  return (
    <span className="flex flex-col items-end gap-0.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img alt={id} className={`${height} rounded object-contain ${made?.url && (way === "svg" || way === "manim" || way === "map") ? "bg-[#0D1117]" : "bg-white"}`}
        src={made?.status === "done" && made.url ? made.url : `/api/documents/${run.documentId}/figure/${encodeURIComponent(id)}`} />
      <span className="text-[10px]" style={{ color: solidKind(way) }}>{choiceOf(way)?.label ?? "figure"}{made?.status === "done" ? "" : " · not made yet"}</span>
    </span>
  );
}

/** Which chapters (of any lecture) teach from a block, other than this one. */
function othersUsing(run: Run, block: string, lecture: number, chapter: number) {
  return run.lectures.flatMap((l) => chaptersOf(run, l.n).filter((c) => (l.n !== lecture || c.n !== chapter) && (c.content ?? []).includes(block))
    .map((c) => `${l.n === lecture ? "" : `L${l.n} `}ch. ${c.n}`));
}

/** A chapter's content: each of the book's blocks it teaches from, the text (a figure's picture), shared ones marked. */
function ContentList({ run, lecture, chapter, select }: { run: Run; lecture: number; chapter: Chapter; select: (s: Selection) => void }) {
  const content = chapter.content ?? [];
  if (!content.length) return <p className="text-[11px] text-neutral-500">No content named.</p>;
  return (
    <ul className="space-y-1" data-testid="script-chapter-content">
      {content.map((id) => {
        const b = run.blocks.find((x) => x.id === id);
        const also = othersUsing(run, id, lecture, chapter.n);
        return (
          <li key={id} className="flex cursor-pointer gap-2 rounded border border-neutral-800 p-1 text-[11px] hover:bg-neutral-900" onClick={(e) => { e.stopPropagation(); select({ kind: "block", id }); }}>
            <span className="mono w-28 shrink-0 text-neutral-500" title={id}>{id.replace(/^\/page\/(\d+)\//, (_, p) => `p${Number(p) + 1}/`)}</span>
            {b?.image ? <FigureThumb run={run} id={id} height="h-12" /> : null}
            <span className="min-w-0 flex-1 text-neutral-300"><span className="text-neutral-500">{b ? kindOf(b.type) : "?"}</span> {(b?.description ?? b?.text ?? "").slice(0, 220)}</span>
            {also.length ? <span className="shrink-0 text-sky-300" title="other chapters teaching from it">also {also.join(", ")}</span> : null}
          </li>
        );
      })}
    </ul>
  );
}

function ChaptersView({ run, lecture, lines, select }: { run: Run; lecture: Lecture; lines: string[]; select: (s: Selection) => void }) {
  const ls = run.script?.lectures[lecture.n];
  const [openCh, setOpenCh] = useState<number | null>(null);
  if (!ls?.chapters.length) return <p className="text-xs text-neutral-500">This lecture has no script.</p>;
  const anchor = (n: number) => `script-${lecture.n}-chapter-${n}`;
  const pickChapter = (c: Chapter) => {
    const on = openCh === c.n;
    setOpenCh(on ? null : c.n);
    if (!on) select({ kind: "blocks", ids: c.content ?? [], label: `lecture ${lecture.n}, chapter ${c.n}` });
  };
  return (
    <div className="flex gap-3">
      <aside className="sticky top-0 hidden w-48 shrink-0 self-start md:block" data-testid="script-outline">
        <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Chapters</p>
        <ol className="space-y-0.5 text-xs">
          {ls.chapters.map((ch) => (
            <li key={ch.n}>
              <button className="w-full rounded px-1.5 py-1 text-left hover:bg-neutral-800"
                onClick={() => { pickChapter(ch); document.getElementById(anchor(ch.n))?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
                <span className="text-neutral-500">{ch.n}.</span> <span className="text-neutral-100">{ch.title}</span>
                <span className="block text-[10px] text-neutral-500">
                  <span className={ch.map ? "text-emerald-400" : ""}>{ch.map ? "board · map beats" : "board"}</span> · {ch.beats.length} beats · {(ch.content ?? []).length} blocks</span>
              </button>
            </li>
          ))}
        </ol>
      </aside>
      <div className="min-w-0 flex-1 space-y-2">
        {ls.chapters.map((ch) => (
          <div key={ch.n} id={anchor(ch.n)} className="scroll-mt-2 rounded border border-neutral-800 bg-neutral-900/40" data-testid="script-chapter">
            <button className={`flex w-full flex-wrap items-baseline gap-2 border-b border-neutral-800 px-2 py-1.5 text-left ${openCh === ch.n ? "bg-sky-950/40" : "hover:bg-neutral-900"}`}
              onClick={() => pickChapter(ch)} title="Show the content it teaches from (and light it up in the PDF)" data-testid="script-chapter-head">
              <span className="text-neutral-500">{openCh === ch.n ? "▾" : "▸"}</span>
              <span className="text-xs font-semibold text-neutral-100">Chapter {ch.n}: {ch.title}</span>
              <span className={`rounded px-1.5 py-px text-[10px] ${ch.map ? "bg-emerald-950 text-emerald-300" : "bg-neutral-800 text-neutral-300"}`}>{ch.map ? "on a map" : "on a board"}</span>
              <span className="text-[10px] text-sky-300">{(ch.content ?? []).length} block(s) of content</span>
              <span className="ml-auto text-[10px] text-neutral-500">sentences {ch.beats[0]?.lines[0]}–{ch.beats.at(-1)?.lines.at(-1)} · {ch.beats.length} beats</span>
              <span className="basis-full pl-5 text-[11px] italic text-neutral-400">title card: “{ch.narration}”</span>
            </button>
            {openCh === ch.n && <div className="border-b border-neutral-800 bg-neutral-950/50 p-2"><ContentList run={run} lecture={lecture.n} chapter={ch} select={select} /></div>}
            <ol>
              {ch.beats.map((b) => {
                const figs = beatFigures(b);
                return (
                  <li key={b.n} data-testid="script-beat" className={`flex gap-2 border-b border-neutral-900 px-2 py-1.5 text-xs last:border-0 ${figs.length ? "cursor-pointer hover:bg-neutral-800/50" : ""}`}
                    onClick={() => figs.length && select(figs.length === 1 ? { kind: "block", id: figs[0] } : { kind: "blocks", ids: figs, label: `beat ${b.n}'s figures` })}>
                    <span className="w-8 shrink-0 text-neutral-500">#{b.n}</span>
                    <span className="mono w-12 shrink-0 text-sky-300" title="the transcript's sentence numbers">{b.lines.length > 1 ? `${b.lines[0]}–${b.lines.at(-1)}` : b.lines[0]}</span>
                    <span className="min-w-0 flex-1">
                      <span className="text-neutral-200">{b.lines.map((k) => lines[k - 1]).join(" ")}</span>
                      <span className="mt-1 block text-[11px]"><span className="rounded bg-neutral-800 px-1.5 py-px text-neutral-300" title="what is on screen">▣ {b.show || "—"}</span></span>
                    </span>
                    {figs.length > 0 && <span className="flex shrink-0 gap-1.5">{figs.map((id) => <FigureThumb key={id} run={run} id={id} />)}</span>}
                  </li>
                );
              })}
            </ol>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Every block the lecture teaches from, with its chapters; every figure, with the beats it is on. */
function ContentView({ run, lecture, select }: { run: Run; lecture: Lecture; select: (s: Selection) => void }) {
  const chs = chaptersOf(run, lecture.n);
  const blocks = [...new Set(chs.flatMap((c) => c.content ?? []))];
  const figures = lectureFigures(run, lecture.n);
  const h = "mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400";
  return (
    <div className="space-y-3 text-xs" data-testid="script-content">
      <div>
        <p className={h}>The book&apos;s blocks it teaches from ({blocks.length}), and the chapters that use each</p>
        <table className="w-full">
          <thead className="text-left text-[10px] uppercase text-neutral-500"><tr><th className="w-28">Block</th><th>What it is</th><th className="w-40">Chapters</th></tr></thead>
          <tbody>
            {blocks.map((id) => {
              const b = run.blocks.find((x) => x.id === id);
              const using = chs.filter((c) => (c.content ?? []).includes(id)).map((c) => c.n);
              const elsewhere = run.lectures.filter((l) => l.n !== lecture.n && chaptersOf(run, l.n).some((c) => (c.content ?? []).includes(id))).map((l) => l.n);
              return (
                <tr key={id} className="cursor-pointer border-t border-neutral-800 align-top hover:bg-neutral-900" onClick={() => select({ kind: "block", id })}>
                  <td className="mono py-1 text-neutral-500">{id.replace(/^\/page\/(\d+)\//, (_, p) => `p${Number(p) + 1}/`)}</td>
                  <td className="py-1 pr-2 text-neutral-300"><span className="text-neutral-500">{b ? kindOf(b.type) : "?"}</span> {(b?.description ?? b?.text ?? "").slice(0, 160)}</td>
                  <td className={`py-1 ${using.length > 1 || elsewhere.length ? "text-sky-300" : "text-neutral-300"}`}>{using.map((n) => `ch. ${n}`).join(", ")}
                    {elsewhere.length ? ` · also lecture ${elsewhere.join(", ")}` : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div>
        <p className={h}>Its figures, and the beats each is shown on</p>
        {figures.length ? (
          <ul className="space-y-1.5">
            {figures.map((f) => (
              <li key={f.id} className="flex cursor-pointer gap-2 rounded border border-neutral-800 p-1.5 hover:bg-neutral-900" onClick={() => select({ kind: "block", id: f.id })}>
                <FigureThumb run={run} id={f.id} height="h-14" />
                <span className="min-w-0 flex-1">
                  <span className="text-neutral-100">{f.id}</span> <span className="text-neutral-400">{f.way}</span>
                  <span className="block truncate text-neutral-400" title={f.caption}>{f.caption || "(no caption)"}</span>
                </span>
                <span className={`w-40 shrink-0 text-right text-[11px] ${f.beats.length ? "text-neutral-200" : "text-amber-300"}`}>
                  {f.beats.length ? <>on beat{f.beats.length > 1 ? "s" : ""} {f.beats.map((n) => `#${n}`).join(", ")}<br /><span className="text-neutral-500">sentences {ranges(f.lines)}</span></> : "in the content, on no beat"}
                </span>
              </li>
            ))}
          </ul>
        ) : <p className="text-neutral-500">This lecture has no figures (or all were triaged Skip).</p>}
      </div>
    </div>
  );
}

/** "3–5, 9, 12–13" */
function ranges(ns: number[]) {
  const s = [...new Set(ns)].sort((a, b) => a - b);
  const out: string[] = [];
  for (let i = 0; i < s.length; i++) {
    let j = i;
    while (j + 1 < s.length && s[j + 1] === s[j] + 1) j++;
    out.push(j > i ? `${s[i]}–${s[j]}` : `${s[i]}`);
    i = j;
  }
  return out.join(", ");
}

/** Each call made (the first try, and the one sent back when it broke): prompt parts, answer, checks. */
export function PromptView({ calls, onCall }: { calls: Call[]; onCall: (id: string) => void }) {
  const [picked, setPicked] = useState<string | null>(null);
  const call = calls.find((c) => c.id === picked) ?? calls.at(-1);
  if (!call) return <p className="text-xs text-neutral-500">No call made yet.</p>;
  return (
    <div className="space-y-3 text-xs" data-testid="script-prompt">
      <div className="flex flex-wrap items-center gap-1.5">
        {calls.map((c) => (
          <button key={c.id} onClick={() => setPicked(c.id)}
            className={`rounded border px-2 py-1 ${c.id === call.id ? "border-sky-600 bg-sky-950 text-sky-100" : "border-neutral-700 text-neutral-400 hover:bg-neutral-800"}`}>
            {c.label} · call {c.id}{c.status === "running" ? " …" : c.status === "failed" ? " ✗" : ""}</button>
        ))}
        <button className="ml-auto rounded border border-neutral-700 px-2 py-1 text-neutral-300 hover:bg-neutral-800" onClick={() => onCall(call.id)}>Open the whole call</button>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-neutral-400">
        <span><span className="text-neutral-500">model</span> <span className="mono text-neutral-200">{call.model}</span></span>
        {call.effort && <span><span className="text-neutral-500">effort</span> {call.effort}</span>}
        <span><span className="text-neutral-500">provider</span> {call.provider === "fixture" ? "offline stand-in" : "OpenRouter"}</span>
        <span className={call.status === "failed" ? "text-red-300" : call.status === "done" ? "text-emerald-300" : "text-sky-300"}>{call.status}</span>
        <span>{seconds(call.started, call.ended)}</span>
        {call.usage && <span>{call.usage.input.toLocaleString()} in / {call.usage.output.toLocaleString()} out tokens</span>}
        <span className="font-semibold text-neutral-200">{money(call.cost)}</span>
      </div>
      {call.error && <p className="text-red-300">{call.error}</p>}
      <div>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">The prompt, as the parts it was built from</p>
        <PromptParts key={call.id} prompt={call.prompt} compact />
      </div>
      <div>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">What it answered (before code mended it)</p>
        {call.status === "running" ? <p className="text-sky-300">Waiting for the reply…</p>
          : call.output ? <Answer output={call.output} /> : <p className="text-neutral-500">{call.text || "No answer."}</p>}
      </div>
      {call.checks.length ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">What code found in it</p>
          <CheckList checks={call.checks} />
        </div>
      ) : null}
    </div>
  );
}

/** The answer as the model gave it: a short outline (a lecture's chapters, when it is one), and the JSON. */
function Answer({ output }: { output: unknown }) {
  const o = output as { title?: string; done?: boolean; chapters?: { title?: string; map?: boolean; content?: string[]; beats?: { lines?: number[]; say?: string; figures?: string[]; figure?: string }[] }[] };
  const chapters = o?.chapters;
  return (
    <div className="space-y-1.5">
      {o?.title && <p className="text-neutral-200">“{o.title}”{o.done !== undefined ? <span className="text-neutral-500"> · done: {String(o.done)}</span> : null}</p>}
      {Array.isArray(chapters) && (
        <ol className="space-y-0.5 text-neutral-300">
          {chapters.map((c, i) => {
            const figs = [...new Set((c.beats ?? []).flatMap((b) => b.figures ?? (b.figure ? [b.figure] : [])))];
            return (
              <li key={i}><span className="text-neutral-500">{i + 1}.</span> {c.title ?? "(no title)"} <span className="text-neutral-500">
                · {c.map ? "board · map beats" : "board"} · {c.beats?.length ?? 0} beats{c.content ? ` · ${c.content.length} blocks of content` : ""}
                {figs.length ? ` · figures ${figs.join(", ")}` : ""}</span></li>
            );
          })}
        </ol>
      )}
      <details><summary className="cursor-pointer text-neutral-400">the answer as JSON</summary><Json value={output} /></details>
    </div>
  );
}

export function CheckList({ checks }: { checks: { name: string; result: keyof typeof CHECK_STYLE; detail: string }[] }) {
  return (
    <ul className="space-y-1 text-xs">
      {checks.map((c, k) => (
        <li key={k} className="flex gap-2">
          <span className={`w-4 shrink-0 text-center ${CHECK_STYLE[c.result].tone}`}>{CHECK_STYLE[c.result].icon}</span>
          <span className="shrink-0 font-medium text-neutral-200">{c.name}</span>
          <span className="text-neutral-400">{c.detail}</span>
        </li>
      ))}
    </ul>
  );
}
