"use client";

/**
 * The script: each lecture cut into chapters and beats. A chapter shows its title card (number, title, the line said
 * on it) and its stage (map or board); each beat its sentences (numbers and words, as the transcript has them), what
 * is on screen, and its figure. Clicking a beat lights up in the PDF what it teaches (its figure, else the blocks of
 * the goals its sentences teach). Build, rebuild, stop; lectures in parallel or one at a time; or one lecture: picked
 * (and shown alone), or the next one not scripted yet.
 */

import { useEffect, useState } from "react";
import type { Run } from "@/lib/types";
import { linesOf } from "@/lib/source/book";
import { choiceOf } from "@/lib/triage-kinds";
import { CHECK_STYLE, money } from "./call-inspector";
import { solidKind } from "./figures-panel";
import type { Selection } from "./panels";

const TONE = { waiting: "text-neutral-400", running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;

export function ScriptPanel({ run, defaultModel, select, onCall, act }: {
  run: Run; defaultModel: string; select: (s: Selection) => void; onCall: (id: string) => void;
  act: (body: Record<string, unknown>) => Promise<boolean>;
}) {
  const st = run.script;
  const [model, setModel] = useState(st?.model || defaultModel);
  const [inTurn, setInTurn] = useState(false);
  const [picked, setPicked] = useState<number | null>(null);
  useEffect(() => { setModel(run.script?.model || defaultModel); setPicked(null); }, [run.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const running = st?.status === "running";
  const written = run.lectures.filter((l) => l.status === "written" && l.text);
  const busy = (n: number) => running && (st?.lectures[n]?.status === "running" || st?.lectures[n]?.status === "waiting");
  const done = written.filter((l) => st?.lectures[l.n]?.status === "done").length;
  const chapters = Object.values(st?.lectures ?? {}).reduce((k, l) => k + l.chapters.length, 0);
  const beats = Object.values(st?.lectures ?? {}).reduce((k, l) => k + l.chapters.reduce((j, c) => j + c.beats.length, 0), 0);
  const cost = run.calls.filter((c) => c.step === "script").reduce((n, c) => n + c.cost, 0);
  const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";
  const next = written.find((l) => !busy(l.n) && st?.lectures[l.n]?.status !== "done");
  const one = written.find((l) => l.n === picked);
  const shown = one ? [one] : written;

  if (!written.length) return <p className="text-sm text-neutral-400">No lecture is written yet: build the transcript (or import one) first. The script cuts each lecture&apos;s transcript into chapters and beats.</p>;
  return (
    <div className="space-y-3" data-testid="script">
      <section className="rounded border border-neutral-800 bg-neutral-900/60 p-3">
        <h3 className="text-sm font-semibold text-neutral-100">Script: chapters and beats</h3>
        <p className="mb-2 text-xs text-neutral-400">Each lecture&apos;s transcript cut into <b>chapters</b> (a topic, with a title card and one stage: a map or a
          board) and <b>beats</b> (1-2 of its numbered sentences, and what is on screen while they are said). Every sentence is in exactly one beat, in
          order, so the narration is the transcript word for word; code checks it and mends what it can. The lecture&apos;s figures are placed on the
          beats that teach them. Script one lecture at a time (pick it, or take the next one not scripted), or build them all:
          in parallel, or one after the other.</p>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-neutral-400">Model</span>
          <input className="mono w-64 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={model}
            onChange={(e) => setModel(e.target.value)} data-testid="script-model" />
          <button className={`${btn} border-emerald-700 bg-emerald-700 text-white`} data-testid="script-run"
            disabled={written.every((l) => busy(l.n) || st?.lectures[l.n]?.status === "done")}
            onClick={() => act({ action: "run", model, oneAtATime: inTurn })}>{!done ? "Build the scripts" : done < written.length ? `Script the ${written.length - done} left` : "All scripted"}</button>
          <button className={`${btn} border-amber-700 text-amber-200 hover:bg-amber-950`} data-testid="script-reset" disabled={written.every((l) => busy(l.n))}
            onClick={() => confirm("Script every lecture again? The scripts there are now are replaced.") && act({ action: "reset", model, oneAtATime: inTurn })}>Rebuild all</button>
          <label className="flex items-center gap-1 text-neutral-300" title="Build them one lecture after the other, not in parallel">
            <input type="checkbox" checked={inTurn} onChange={(e) => setInTurn(e.target.checked)} data-testid="script-in-turn" /> one at a time</label>
          {running && <button className={`${btn} border-red-700 text-red-200`} onClick={() => act({ action: "stop" })}>Stop all</button>}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-neutral-800 pt-2 text-xs">
          <span className="text-neutral-400">One lecture</span>
          <select className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={picked ?? ""} data-testid="script-pick"
            onChange={(e) => setPicked(e.target.value ? Number(e.target.value) : null)}>
            <option value="">all lectures shown</option>
            {written.map((l) => <option key={l.n} value={l.n}>Lecture {l.n}: {l.title}{st?.lectures[l.n]?.status === "done" ? " ✓" : ""}</option>)}
          </select>
          {one && <button className={`${btn} border-sky-700 bg-sky-800 text-white`} disabled={busy(one.n)} data-testid="script-picked"
            onClick={() => act({ action: "one", lecture: one.n, model })}>
            {busy(one.n) ? `Scripting lecture ${one.n}…` : `${st?.lectures[one.n]?.status === "done" ? "Rescript" : "Script"} lecture ${one.n}`}</button>}
          <button className={`${btn} border-sky-700 text-sky-200 hover:bg-sky-950`} disabled={!next} data-testid="script-next"
            onClick={() => next && (setPicked(picked === null ? null : next.n), act({ action: "next", model }))}>
            {next ? `Script the next: lecture ${next.n}` : "No lecture left to script"}</button>
        </div>
      </section>
      <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-300" data-testid="script-summary">
        <span className={st?.status === "failed" ? "text-red-300" : running ? "text-sky-300" : st?.status === "done" ? "text-emerald-300" : "text-neutral-400"}>
          {st ? st.status : "not scripted yet"}</span>
        <span>{done} of {written.length} lectures scripted</span>
        <span>{chapters} chapters, {beats} beats</span>
        {st && <span>{st.model}</span>}
        <span className="font-semibold">{money(cost)}</span>
      </div>
      {st?.error && <p className="rounded border border-red-800 bg-red-950/40 p-2 text-xs text-red-200">{st.error}</p>}

      {shown.map((lecture) => {
        const ls = st?.lectures[lecture.n];
        const lines = linesOf(lecture.text ?? "");
        // What a beat teaches, in the book: its figure, else the blocks of the goals its sentences teach.
        const blocksOf = (ns: number[], figure?: string) => figure ? [figure]
          : [...new Set(lecture.goals.filter((g) => (lecture.goalLines?.[g.id] ?? []).some((k) => ns.includes(k))).flatMap((g) => g.blocks))];
        return (
          <section key={lecture.n} className="rounded border border-neutral-800 p-2" data-testid="script-lecture">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-sm font-semibold text-neutral-100">Lecture {lecture.n}: {lecture.title}</span>
              <span className="text-neutral-500">{lines.length} sentences</span>
              <span className={TONE[ls?.status ?? "waiting"]}>{ls ? (ls.status === "running" ? "scripting…" : ls.status === "waiting" && busy(lecture.n) ? "queued" : ls.status) : "not scripted"}</span>
              {ls?.lines !== undefined && ls.lines !== lines.length && <span className="text-amber-300">the transcript changed since: rescript it</span>}
              <span className="ml-auto flex items-center gap-1.5">
                <button className="rounded border border-neutral-700 px-1.5 py-px text-[11px] text-neutral-300 hover:bg-neutral-800 disabled:opacity-40" disabled={busy(lecture.n)}
                  data-testid="script-one" onClick={() => act({ action: "one", lecture: lecture.n, model })}>{ls?.status === "done" ? "Rescript" : "Script"}</button>
                {ls?.calls.map((id) => {
                  const c = run.calls.find((x) => x.id === id);
                  return c ? <button key={id} onClick={() => onCall(id)} className={`rounded border px-1.5 py-px text-[10px] hover:bg-neutral-800 ${c.status === "failed" ? "border-red-800 text-red-300" : "border-neutral-700 text-neutral-400"}`}>
                    call {id}{c.status === "running" ? " …" : c.status === "failed" ? " ✗" : ""} · {money(c.cost)}</button> : null;
                })}
              </span>
            </div>
            {ls?.error && <p className="mt-1 text-xs text-red-300">Error: {ls.error}</p>}
            {ls?.checks?.length ? (
              <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]">
                {ls.checks.map((c, k) => <li key={k}><span className={CHECK_STYLE[c.result].tone}>{CHECK_STYLE[c.result].icon}</span> <span className="text-neutral-300">{c.name}</span> <span className="text-neutral-500">{c.detail}</span></li>)}
              </ul>
            ) : null}
            <div className="mt-2 space-y-2">
              {ls?.chapters.map((ch) => (
                <div key={ch.n} className="rounded border border-neutral-800 bg-neutral-900/40" data-testid="script-chapter">
                  <div className="flex flex-wrap items-baseline gap-2 border-b border-neutral-800 px-2 py-1">
                    <span className="text-xs font-semibold text-neutral-100">Chapter {ch.n}: {ch.title}</span>
                    <span className={`rounded px-1.5 py-px text-[10px] ${ch.map ? "bg-emerald-950 text-emerald-300" : "bg-neutral-800 text-neutral-300"}`}>{ch.map ? "on a map" : "on a board"}</span>
                    <span className="text-[11px] italic text-neutral-400">title card: “{ch.narration}”</span>
                    <span className="ml-auto text-[10px] text-neutral-500">sentences {ch.beats[0]?.lines[0]}–{ch.beats.at(-1)?.lines.at(-1)} · {ch.beats.length} beats</span>
                  </div>
                  <ol>
                    {ch.beats.map((b) => {
                      const way = b.figure ? (run.triage?.figures[b.figure]?.override ?? run.triage?.figures[b.figure]?.kind) : undefined;
                      const made = b.figure ? run.generation?.figures[b.figure] : undefined;
                      return (
                        <li key={b.n} data-testid="script-beat" className="flex cursor-pointer gap-2 border-b border-neutral-900 px-2 py-1 text-xs last:border-0 hover:bg-neutral-800/50"
                          onClick={() => {
                            const ids = blocksOf(b.lines, b.figure);
                            select(ids.length === 1 ? { kind: "block", id: ids[0] } : { kind: "blocks", ids, label: `beat ${b.n}` });
                          }}>
                          <span className="w-10 shrink-0 text-neutral-500">#{b.n}</span>
                          <span className="mono w-14 shrink-0 text-sky-300" title="the transcript's sentence numbers">{b.lines.length > 1 ? `${b.lines[0]}–${b.lines.at(-1)}` : b.lines[0]}</span>
                          <span className="min-w-0 flex-1 text-neutral-200">{b.lines.map((k) => lines[k - 1]).join(" ")}
                            <span className="mt-0.5 block text-[11px] text-neutral-500">on screen: {b.show || "—"}</span></span>
                          {b.figure && (
                            <span className="flex w-40 shrink-0 flex-col items-end gap-0.5">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img alt={b.figure} className={`h-16 rounded object-contain ${made?.url && (way === "svg" || way === "manim" || way === "map") ? "bg-[#0D1117]" : "bg-white"}`}
                                src={made?.status === "done" && made.url ? made.url : `/api/documents/${run.documentId}/figure/${encodeURIComponent(b.figure)}`} />
                              <span className="text-[10px]" style={{ color: solidKind(way) }}>{choiceOf(way)?.label ?? "figure"}{made?.status === "done" ? "" : " · not made yet"}</span>
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ol>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
