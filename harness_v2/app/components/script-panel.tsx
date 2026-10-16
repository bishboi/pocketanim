"use client";

/**
 * The script: each lecture cut into chapters and beats, and how it was made. An overview of every lecture, then one
 * lecture at a time, in four views:
 *
 *   - Chapters and beats: an outline of the chapters beside them, each chapter's title card and stage (map or board),
 *     and its beats: sentences (numbers and words, as the transcript has them), the goals they teach, what is on
 *     screen, and the figure;
 *   - Planning it used: the lecture, its goals (with their sentences, and the chapters that teach them now), its
 *     figures (way, made yet, the sentences that teach them, and the beat each is on), the numbered transcript;
 *   - Prompt and answer: each call made for it, its prompt as the parts it was built from, the answer and the checks;
 *   - Checks: what code found and mended.
 *
 * Clicking a beat, a goal or a figure lights up in the PDF what it teaches.
 */

import { useEffect, useMemo, useState } from "react";
import type { Call, Chapter, Run } from "@/lib/types";
import { linesOf } from "@/lib/source/book";
import { lectureFigures } from "@/lib/script-figures";
import { choiceOf } from "@/lib/triage-kinds";
import { CHECK_STYLE, Json, PromptParts, money, seconds } from "./call-inspector";
import { solidKind } from "./figures-panel";
import type { Selection } from "./panels";

const TONE = { waiting: "text-neutral-400", running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;
const DOT = { waiting: "bg-neutral-500", running: "bg-sky-400 animate-pulse", done: "bg-emerald-400", failed: "bg-red-400" } as const;
const VIEWS = ["Chapters and beats", "Planning it used", "Prompt and answer", "Checks"] as const;
type View = (typeof VIEWS)[number];

type Lecture = Run["lectures"][number];

export function ScriptPanel({ run, defaultModel, select, onCall, act }: {
  run: Run; defaultModel: string; select: (s: Selection) => void; onCall: (id: string) => void;
  act: (body: Record<string, unknown>) => Promise<boolean>;
}) {
  const st = run.script;
  const [model, setModel] = useState(st?.model || defaultModel);
  const [inTurn, setInTurn] = useState(false);
  const [open, setOpen] = useState<number | "all">("all");
  const [view, setView] = useState<View>("Chapters and beats");
  useEffect(() => { setModel(run.script?.model || defaultModel); setOpen("all"); }, [run.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const running = st?.status === "running";
  const written = run.lectures.filter((l) => l.status === "written" && l.text);
  const busy = (n: number) => running && (st?.lectures[n]?.status === "running" || st?.lectures[n]?.status === "waiting");
  const done = written.filter((l) => st?.lectures[l.n]?.status === "done").length;
  const chapters = Object.values(st?.lectures ?? {}).reduce((k, l) => k + l.chapters.length, 0);
  const beats = Object.values(st?.lectures ?? {}).reduce((k, l) => k + l.chapters.reduce((j, c) => j + c.beats.length, 0), 0);
  const cost = run.calls.filter((c) => c.step === "script").reduce((n, c) => n + c.cost, 0);
  const next = written.find((l) => !busy(l.n) && st?.lectures[l.n]?.status !== "done");
  const lecture = open === "all" ? undefined : written.find((l) => l.n === open);
  const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";
  const scriptOne = (n: number) => { setOpen(n); return act({ action: "one", lecture: n, model }); };

  if (!written.length) return <p className="text-sm text-neutral-400">No lecture is written yet: build the transcript (or import one) first. The script cuts each lecture&apos;s transcript into chapters and beats.</p>;
  return (
    <div className="space-y-3" data-testid="script">
      <section className="rounded border border-neutral-800 bg-neutral-900/60 p-3">
        <h3 className="text-sm font-semibold text-neutral-100">Script: chapters and beats</h3>
        <p className="mb-2 text-xs text-neutral-400">Each lecture&apos;s transcript cut into <b>chapters</b> (a topic, with a title card and one stage: a map or a
          board) and <b>beats</b> (1-2 of its numbered sentences, and what is on screen while they are said). Every sentence is in exactly one beat, in
          order, so the narration is the transcript word for word; code checks it and mends what it can. One call a lecture, told the lecture&apos;s
          goals, its figures and its numbered transcript.</p>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-neutral-400">Model</span>
          <input className="mono w-60 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={model}
            onChange={(e) => setModel(e.target.value)} data-testid="script-model" />
          <button className={`${btn} border-sky-700 bg-sky-800 text-white`} disabled={!next} data-testid="script-next"
            onClick={() => next && scriptOne(next.n)}>{next ? `Script the next: lecture ${next.n}` : "No lecture left to script"}</button>
          <span className="mx-1 h-4 w-px bg-neutral-700" />
          <button className={`${btn} border-emerald-700 bg-emerald-700 text-white`} data-testid="script-run"
            disabled={written.every((l) => busy(l.n) || st?.lectures[l.n]?.status === "done")}
            onClick={() => act({ action: "run", model, oneAtATime: inTurn })}>{!done ? "Build all" : done < written.length ? `Script the ${written.length - done} left` : "All scripted"}</button>
          <button className={`${btn} border-amber-700 text-amber-200 hover:bg-amber-950`} data-testid="script-reset" disabled={written.every((l) => busy(l.n))}
            onClick={() => confirm("Script every lecture again? The scripts there are now are replaced.") && act({ action: "reset", model, oneAtATime: inTurn })}>Rebuild all</button>
          <label className="flex items-center gap-1 text-neutral-300" title="Build them one lecture after the other, not in parallel">
            <input type="checkbox" checked={inTurn} onChange={(e) => setInTurn(e.target.checked)} data-testid="script-in-turn" /> one at a time</label>
          {running && <button className={`${btn} border-red-700 text-red-200`} onClick={() => act({ action: "stop" })}>Stop all</button>}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-neutral-800 pt-2 text-xs text-neutral-300" data-testid="script-summary">
          <span className={st?.status === "failed" ? "text-red-300" : running ? "text-sky-300" : st?.status === "done" ? "text-emerald-300" : "text-neutral-400"}>
            {st ? st.status : "not scripted yet"}</span>
          <span>{done} of {written.length} lectures scripted</span>
          <span>{chapters} chapters, {beats} beats</span>
          {st && <span className="mono text-neutral-500">{st.model}</span>}
          <span className="font-semibold">{money(cost)}</span>
        </div>
        {st?.error && <p className="mt-2 rounded border border-red-800 bg-red-950/40 p-2 text-xs text-red-200">{st.error}</p>}
      </section>

      <nav className="flex flex-wrap gap-1 border-b border-neutral-800" data-testid="script-lectures">
        <Tab on={open === "all"} onClick={() => setOpen("all")}>All lectures</Tab>
        {written.map((l) => {
          const s = st?.lectures[l.n]?.status ?? "waiting";
          return (
            <Tab key={l.n} on={open === l.n} onClick={() => setOpen(l.n)} title={l.title}>
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${st?.lectures[l.n] ? DOT[s] : "bg-neutral-700"}`} /> Lecture {l.n}
            </Tab>
          );
        })}
      </nav>

      {!lecture ? <Overview run={run} written={written} busy={busy} openLecture={(n) => setOpen(n)} scriptOne={scriptOne} />
        : <LectureView key={lecture.n} run={run} lecture={lecture} busy={busy(lecture.n)} view={view} setView={setView}
          select={select} onCall={onCall} scriptIt={() => scriptOne(lecture.n)} />}
    </div>
  );
}

function Tab({ on, onClick, title, children }: { on: boolean; onClick: () => void; title?: string; children: React.ReactNode }) {
  return (
    <button onClick={onClick} title={title} data-testid="script-tab"
      className={`flex items-center gap-1.5 rounded-t px-2.5 py-1 text-xs ${on ? "bg-neutral-800 text-white" : "text-neutral-400 hover:text-neutral-200"}`}>{children}</button>
  );
}

/** Every lecture in a row: its state, size, figures placed, cost; a row opens the lecture. */
function Overview({ run, written, busy, openLecture, scriptOne }: {
  run: Run; written: Lecture[]; busy: (n: number) => boolean; openLecture: (n: number) => void; scriptOne: (n: number) => void;
}) {
  const st = run.script;
  return (
    <table className="w-full text-xs" data-testid="script-overview">
      <thead className="text-left text-[10px] uppercase tracking-wide text-neutral-500">
        <tr><th className="py-1">Lecture</th><th>Sentences</th><th>State</th><th>Chapters</th><th>Beats</th><th>Figures shown</th><th>Cost</th><th /></tr>
      </thead>
      <tbody>
        {written.map((l) => {
          const ls = st?.lectures[l.n];
          const figs = lectureFigures(run, l.n);
          const placed = new Set(ls?.chapters.flatMap((c) => c.beats.flatMap((b) => (b.figure ? [b.figure] : []))));
          const lineCount = linesOf(l.text ?? "").length;
          const cost = run.calls.filter((c) => ls?.calls.includes(c.id)).reduce((k, c) => k + c.cost, 0);
          return (
            <tr key={l.n} className="cursor-pointer border-t border-neutral-800 hover:bg-neutral-900" onClick={() => openLecture(l.n)} data-testid="script-lecture">
              <td className="py-1.5 pr-2 text-neutral-100"><b>{l.n}</b>. {l.title}</td>
              <td className="text-neutral-400">{lineCount}</td>
              <td className={TONE[ls?.status ?? "waiting"]}>{ls ? (ls.status === "running" ? "scripting…" : ls.status === "waiting" && busy(l.n) ? "queued" : ls.status) : "not scripted"}
                {ls?.lines !== undefined && ls.lines !== lineCount && <span className="ml-1 text-amber-300">(transcript changed)</span>}</td>
              <td>{ls?.chapters.length ?? "—"}</td>
              <td>{ls ? ls.chapters.reduce((k, c) => k + c.beats.length, 0) : "—"}</td>
              <td className={figs.length && placed.size < figs.length && ls?.status === "done" ? "text-amber-300" : ""}>{figs.length ? `${placed.size} of ${figs.length}` : "none"}</td>
              <td>{money(cost)}</td>
              <td className="text-right">
                <button className="rounded border border-neutral-700 px-1.5 py-px text-[11px] text-neutral-300 hover:bg-neutral-800 disabled:opacity-40" disabled={busy(l.n)}
                  onClick={(e) => { e.stopPropagation(); scriptOne(l.n); }}>{ls?.status === "done" ? "Rescript" : "Script"}</button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function LectureView({ run, lecture, busy, view, setView, select, onCall, scriptIt }: {
  run: Run; lecture: Lecture; busy: boolean; view: View; setView: (v: View) => void; select: (s: Selection) => void;
  onCall: (id: string) => void; scriptIt: () => void;
}) {
  const ls = run.script?.lectures[lecture.n];
  const lines = useMemo(() => linesOf(lecture.text ?? ""), [lecture.text]);
  const calls = (ls?.calls ?? []).map((id) => run.calls.find((c) => c.id === id)).filter((c): c is Call => !!c);
  const cost = calls.reduce((k, c) => k + c.cost, 0);
  const last = calls.at(-1);
  const checks = ls?.checks ?? [];
  const fixes = checks.filter((c) => c.result === "fixed" || c.result === "fail").length;
  return (
    <section className="space-y-2" data-testid="script-lecture-view">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-sm font-semibold text-neutral-100">Lecture {lecture.n}: {lecture.title}</span>
        <span className={TONE[ls?.status ?? "waiting"]}>{ls ? (ls.status === "running" ? "scripting…" : ls.status === "waiting" && busy ? "queued" : ls.status) : "not scripted"}</span>
        {ls?.lines !== undefined && ls.lines !== lines.length && <span className="text-amber-300">the transcript changed since: rescript it</span>}
        <span className="text-neutral-500">{lines.length} sentences · {ls?.chapters.length ?? 0} chapters · {ls?.chapters.reduce((k, c) => k + c.beats.length, 0) ?? 0} beats
          {last ? ` · ${last.model} · ${seconds(calls[0].started, last.ended)}` : ""} · {money(cost)}</span>
        <button className="ml-auto rounded border border-sky-700 bg-sky-800 px-2.5 py-1 text-xs text-white disabled:opacity-40" disabled={busy}
          data-testid="script-one" onClick={scriptIt}>{busy ? "Scripting…" : ls?.status === "done" ? "Rescript this lecture" : "Script this lecture"}</button>
      </div>
      {ls?.error && <p className="rounded border border-red-800 bg-red-950/40 p-2 text-xs text-red-200">Error: {ls.error}</p>}
      <nav className="flex gap-1 text-xs">
        {VIEWS.map((v) => (
          <button key={v} onClick={() => setView(v)} data-testid="script-view"
            className={`rounded-full border px-2.5 py-0.5 ${view === v ? "border-sky-600 bg-sky-950 text-sky-100" : "border-neutral-700 text-neutral-400 hover:text-neutral-200"}`}>
            {v}{v === "Prompt and answer" && calls.length ? ` (${calls.length})` : ""}{v === "Checks" && checks.length ? ` (${fixes ? `${fixes} mended` : "all passed"})` : ""}
          </button>
        ))}
      </nav>
      {view === "Chapters and beats" && <ChaptersView run={run} lecture={lecture} lines={lines} select={select} />}
      {view === "Planning it used" && <PlanningView run={run} lecture={lecture} lines={lines} select={select} />}
      {view === "Prompt and answer" && <PromptView calls={calls} onCall={onCall} />}
      {view === "Checks" && (checks.length ? <CheckList checks={checks} /> : <p className="text-xs text-neutral-500">Not scripted yet.</p>)}
    </section>
  );
}

/** The goals a run of sentences teaches. */
function goalsOf(lecture: Lecture, ns: number[]) {
  return lecture.goals.filter((g) => (lecture.goalLines?.[g.id] ?? []).some((k) => ns.includes(k)));
}

function ChaptersView({ run, lecture, lines, select }: { run: Run; lecture: Lecture; lines: string[]; select: (s: Selection) => void }) {
  const ls = run.script?.lectures[lecture.n];
  const [shut, setShut] = useState<Set<number>>(new Set());
  if (!ls?.chapters.length) return <p className="text-xs text-neutral-500">{ls?.status === "running" ? "Scripting…" : "Not scripted yet: script this lecture to see its chapters and beats."}</p>;
  const toggle = (n: number) => setShut((s) => { const x = new Set(s); if (x.has(n)) x.delete(n); else x.add(n); return x; });
  const anchor = (n: number) => `script-${lecture.n}-chapter-${n}`;
  return (
    <div className="flex gap-3">
      <aside className="sticky top-0 hidden w-48 shrink-0 self-start md:block" data-testid="script-outline">
        <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Chapters</p>
        <ol className="space-y-0.5 text-xs">
          {ls.chapters.map((ch) => (
            <li key={ch.n}>
              <button className="w-full rounded px-1.5 py-1 text-left hover:bg-neutral-800"
                onClick={() => { setShut((s) => { const x = new Set(s); x.delete(ch.n); return x; }); document.getElementById(anchor(ch.n))?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
                <span className="text-neutral-500">{ch.n}.</span> <span className="text-neutral-100">{ch.title}</span>
                <span className="block text-[10px] text-neutral-500">
                  <span className={ch.map ? "text-emerald-400" : ""}>{ch.map ? "map" : "board"}</span> · {ch.beats.length} beats · {span(ch)}
                  {ch.beats.some((b) => b.figure) ? ` · ${ch.beats.filter((b) => b.figure).length} fig.` : ""}</span>
              </button>
            </li>
          ))}
        </ol>
        <div className="mt-2 flex gap-1 text-[10px]">
          <button className="rounded border border-neutral-700 px-1.5 text-neutral-400 hover:bg-neutral-800" onClick={() => setShut(new Set())}>open all</button>
          <button className="rounded border border-neutral-700 px-1.5 text-neutral-400 hover:bg-neutral-800" onClick={() => setShut(new Set(ls.chapters.map((c) => c.n)))}>close all</button>
        </div>
      </aside>
      <div className="min-w-0 flex-1 space-y-2">
        {ls.chapters.map((ch) => (
          <div key={ch.n} id={anchor(ch.n)} className="scroll-mt-2 rounded border border-neutral-800 bg-neutral-900/40" data-testid="script-chapter">
            <button className="flex w-full flex-wrap items-baseline gap-2 border-b border-neutral-800 px-2 py-1.5 text-left" onClick={() => toggle(ch.n)}>
              <span className="text-neutral-500">{shut.has(ch.n) ? "▸" : "▾"}</span>
              <span className="text-xs font-semibold text-neutral-100">Chapter {ch.n}: {ch.title}</span>
              <span className={`rounded px-1.5 py-px text-[10px] ${ch.map ? "bg-emerald-950 text-emerald-300" : "bg-neutral-800 text-neutral-300"}`}>{ch.map ? "on a map" : "on a board"}</span>
              <span className="ml-auto text-[10px] text-neutral-500">sentences {span(ch)} · {ch.beats.length} beats</span>
              <span className="basis-full pl-5 text-[11px] italic text-neutral-400">title card: “{ch.narration}”</span>
            </button>
            {!shut.has(ch.n) && (
              <ol>
                {ch.beats.map((b) => {
                  const way = b.figure ? (run.triage?.figures[b.figure]?.override ?? run.triage?.figures[b.figure]?.kind) : undefined;
                  const made = b.figure ? run.generation?.figures[b.figure] : undefined;
                  const goals = goalsOf(lecture, b.lines);
                  return (
                    <li key={b.n} data-testid="script-beat" className="flex cursor-pointer gap-2 border-b border-neutral-900 px-2 py-1.5 text-xs last:border-0 hover:bg-neutral-800/50"
                      onClick={() => {
                        const ids = b.figure ? [b.figure] : [...new Set(goals.flatMap((g) => g.blocks))];
                        if (ids.length) select(ids.length === 1 ? { kind: "block", id: ids[0] } : { kind: "blocks", ids, label: `beat ${b.n}` });
                      }}>
                      <span className="w-8 shrink-0 text-neutral-500">#{b.n}</span>
                      <span className="mono w-12 shrink-0 text-sky-300" title="the transcript's sentence numbers">{b.lines.length > 1 ? `${b.lines[0]}–${b.lines.at(-1)}` : b.lines[0]}</span>
                      <span className="min-w-0 flex-1">
                        <span className="text-neutral-200">{b.lines.map((k) => lines[k - 1]).join(" ")}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-1 text-[11px]">
                          <span className="rounded bg-neutral-800 px-1.5 py-px text-neutral-300" title="what is on screen">▣ {b.show || "—"}</span>
                          {goals.map((g) => <span key={g.id} className="rounded border border-emerald-900 px-1.5 py-px text-emerald-300" title={g.goal}>{g.id}</span>)}
                        </span>
                      </span>
                      {b.figure && (
                        <span className="flex w-36 shrink-0 flex-col items-end gap-0.5">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img alt={b.figure} className={`h-16 rounded object-contain ${made?.url && (way === "svg" || way === "manim" || way === "map") ? "bg-[#0D1117]" : "bg-white"}`}
                            src={made?.status === "done" && made.url ? made.url : `/api/documents/${run.documentId}/figure/${encodeURIComponent(b.figure)}`} />
                          <span className="text-[10px]" style={{ color: solidKind(way) }}>{b.figure} · {choiceOf(way)?.label ?? "figure"}{made?.status === "done" ? "" : " · not made yet"}</span>
                        </span>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const span = (ch: Chapter) => `${ch.beats[0]?.lines[0]}–${ch.beats.at(-1)?.lines.at(-1)}`;

/** What the script was told, from the plan and the steps before: the lecture, goals, figures, numbered transcript. */
function PlanningView({ run, lecture, lines, select }: { run: Run; lecture: Lecture; lines: string[]; select: (s: Selection) => void }) {
  const ls = run.script?.lectures[lecture.n];
  const figures = lectureFigures(run, lecture.n);
  const beats = ls?.chapters.flatMap((c) => c.beats.map((b) => ({ ...b, chapter: c }))) ?? [];
  const beatOf = (k: number) => beats.find((b) => b.lines.includes(k));
  const [allLines, setAllLines] = useState(false);
  const h = "mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400";
  return (
    <div className="space-y-3 text-xs" data-testid="script-planning">
      <div>
        <p className={h}>The lecture (from the plan)</p>
        <p className="text-neutral-100">Lecture {lecture.n}: {lecture.title}</p>
        {lecture.why && <p className="text-neutral-400">{lecture.why}</p>}
        <p className="text-neutral-500">{lecture.blocks.length} blocks of the book · {lecture.goals.length} goals · {figures.length} figures · {lines.length} sentences</p>
      </div>

      <div>
        <p className={h}>Goals, the sentences that teach them, and where they are now</p>
        <table className="w-full">
          <thead className="text-left text-[10px] uppercase text-neutral-500"><tr><th className="w-14">Goal</th><th>What the lecture teaches</th><th className="w-32">Sentences</th><th className="w-28">Chapters</th></tr></thead>
          <tbody>
            {lecture.goals.map((g) => {
              const ns = lecture.goalLines?.[g.id] ?? [];
              const chs = [...new Set(ns.map((k) => beatOf(k)?.chapter.n).filter((x): x is number => x !== undefined))];
              return (
                <tr key={g.id} className="cursor-pointer border-t border-neutral-800 align-top hover:bg-neutral-900"
                  onClick={() => select(g.blocks.length === 1 ? { kind: "block", id: g.blocks[0] } : { kind: "blocks", ids: g.blocks, label: `goal ${g.id}` })}>
                  <td className="py-1 text-emerald-300">{g.id}</td>
                  <td className="py-1 pr-2 text-neutral-200">{g.goal}</td>
                  <td className="mono py-1 text-sky-300">{ns.length ? ranges(ns) : <span className="text-amber-300">none</span>}</td>
                  <td className="py-1 text-neutral-300">{ls?.chapters.length ? (chs.length ? chs.map((n) => `ch. ${n}`).join(", ") : "—") : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div>
        <p className={h}>Figures it was given, and the beat each is on</p>
        {figures.length ? (
          <ul className="space-y-1.5">
            {figures.map((f) => {
              const at = beats.find((b) => b.figure === f.id);
              const way = run.triage?.figures[f.id]?.override ?? run.triage?.figures[f.id]?.kind;
              return (
                <li key={f.id} className="flex cursor-pointer gap-2 rounded border border-neutral-800 p-1.5 hover:bg-neutral-900" onClick={() => select({ kind: "block", id: f.id })}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img alt={f.id} className="h-14 w-20 shrink-0 rounded bg-white object-contain" src={`/api/documents/${run.documentId}/figure/${encodeURIComponent(f.id)}`} />
                  <span className="min-w-0 flex-1">
                    <span className="text-neutral-100">{f.id}</span> <span style={{ color: solidKind(way) }}>{f.way}</span>
                    <span className={f.ready ? "text-emerald-400" : "text-neutral-500"}> · {f.ready ? "made" : "not made yet"}</span>
                    <span className="block truncate text-neutral-400" title={f.caption}>{f.caption || "(no caption)"}</span>
                    <span className="text-[11px] text-neutral-500">taught in sentences <span className="mono text-sky-300">{f.lines.length ? ranges(f.lines) : "— (no goal names it)"}</span></span>
                  </span>
                  <span className={`w-36 shrink-0 text-right text-[11px] ${at ? "text-neutral-200" : ls?.status === "done" ? "text-amber-300" : "text-neutral-500"}`}>
                    {at ? <>on beat #{at.n}<br /><span className="text-neutral-500">chapter {at.chapter.n}, sentences {ranges(at.lines)}</span></> : ls?.status === "done" ? "not shown" : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : <p className="text-neutral-500">This lecture has no figures (or all were triaged Skip).</p>}
      </div>

      <div>
        <p className={h}>The transcript, numbered, with the beat each sentence is in</p>
        <ol className="space-y-0.5">
          {(allLines ? lines : lines.slice(0, 12)).map((t, i) => {
            const b = beatOf(i + 1);
            return (
              <li key={i} className="flex gap-2">
                <span className="mono w-8 shrink-0 text-right text-sky-300">{i + 1}</span>
                <span className="min-w-0 flex-1 text-neutral-300">{t}</span>
                <span className="w-20 shrink-0 text-right text-[10px] text-neutral-500">{b ? `ch. ${b.chapter.n} · #${b.n}` : ""}</span>
              </li>
            );
          })}
        </ol>
        {lines.length > 12 && <button className="mt-1 text-[11px] text-sky-300 hover:underline" onClick={() => setAllLines(!allLines)}>
          {allLines ? "show fewer" : `show all ${lines.length} sentences`}</button>}
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

/** Each call made for the lecture (the first try, and the one sent back when it broke): prompt parts, answer, checks. */
function PromptView({ calls, onCall }: { calls: Call[]; onCall: (id: string) => void }) {
  const [picked, setPicked] = useState<string | null>(null);
  const call = calls.find((c) => c.id === picked) ?? calls.at(-1);
  if (!call) return <p className="text-xs text-neutral-500">No call made yet: script this lecture.</p>;
  return (
    <div className="space-y-3 text-xs" data-testid="script-prompt">
      <div className="flex flex-wrap items-center gap-1.5">
        {calls.map((c, i) => (
          <button key={c.id} onClick={() => setPicked(c.id)}
            className={`rounded border px-2 py-1 ${c.id === call.id ? "border-sky-600 bg-sky-950 text-sky-100" : "border-neutral-700 text-neutral-400 hover:bg-neutral-800"}`}>
            {c.label} · call {c.id}{c.status === "running" ? " …" : c.status === "failed" ? " ✗" : ""}</button>
        ))}
        <button className="ml-auto rounded border border-neutral-700 px-2 py-1 text-neutral-300 hover:bg-neutral-800" onClick={() => onCall(call.id)}>Open the whole call</button>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-neutral-400">
        <span><span className="text-neutral-500">model</span> <span className="mono text-neutral-200">{call.model}</span></span>
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

/** The answer as the model gave it: a short outline, and the JSON. */
function Answer({ output }: { output: unknown }) {
  const chapters = (output as { chapters?: { title?: string; map?: boolean; beats?: { lines?: number[]; figure?: string }[] }[] })?.chapters;
  return (
    <div className="space-y-1.5">
      {Array.isArray(chapters) && (
        <ol className="space-y-0.5 text-neutral-300">
          {chapters.map((c, i) => (
            <li key={i}><span className="text-neutral-500">{i + 1}.</span> {c.title ?? "(no title)"} <span className="text-neutral-500">
              · {c.map ? "map" : "board"} · {c.beats?.length ?? 0} beats · sentences {c.beats?.length ? ranges(c.beats.flatMap((b) => b.lines ?? [])) : "—"}
              {c.beats?.some((b) => b.figure) ? ` · figures ${c.beats.filter((b) => b.figure).map((b) => b.figure).join(", ")}` : ""}</span></li>
          ))}
        </ol>
      )}
      <details><summary className="cursor-pointer text-neutral-400">the answer as JSON</summary><Json value={output} /></details>
    </div>
  );
}

function CheckList({ checks }: { checks: { name: string; result: keyof typeof CHECK_STYLE; detail: string }[] }) {
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
