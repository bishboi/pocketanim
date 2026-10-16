"use client";

/**
 * The run's panels: the plan (videos, sections, goals and their book items), the transcript, every call, the costs,
 * and the models. Selecting a section or a goal highlights its source in the PDF beside them.
 */

import { useState } from "react";
import type { Call, Run, SectionState } from "@/lib/types";
import { linesOf } from "@/lib/source/book";
import { CHECK_STYLE, money, seconds } from "./call-inspector";

export type Selection = { kind: "section"; n: number } | { kind: "goal"; id: string } | null;

export const SECTION_COLORS = [
  "rgba(250, 204, 21, 0.30)", "rgba(56, 189, 248, 0.30)", "rgba(244, 114, 182, 0.30)", "rgba(74, 222, 128, 0.30)",
  "rgba(251, 146, 60, 0.30)", "rgba(167, 139, 250, 0.30)", "rgba(45, 212, 191, 0.30)", "rgba(248, 113, 113, 0.30)",
];
export const sectionColor = (n: number) => SECTION_COLORS[(n - 1) % SECTION_COLORS.length];
const swatch = (n: number) => sectionColor(n).replace(/[\d.]+\)$/, "1)");

const GOAL_TONE = {
  waiting: "border-neutral-700 text-neutral-400",
  taught: "border-emerald-700 bg-emerald-950/60 text-emerald-300",
  patched: "border-amber-700 bg-amber-950/60 text-amber-300",
  missing: "border-red-700 bg-red-950/60 text-red-300",
} as const;
const GOAL_LABEL = { waiting: "not written yet", taught: "taught", patched: "written in after", missing: "missing" } as const;
const ITEM_TONE: Record<string, string> = {
  heading: "text-sky-300", term: "text-amber-300", aside: "text-pink-300", figure: "text-violet-300",
};

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
            {c.step === "patch" ? "patch" : "call"} {id}{c.status === "running" ? " …" : c.status === "failed" ? " ✗" : ""}
          </button>
        );
      })}
    </span>
  );
}

// ─── Plan ────────────────────────────────────────────────────────────────────────────────────────────────────────

export function PlanPanel({ run, selection, select, onCall }: { run: Run; selection: Selection; select: (s: Selection) => void;
  onCall: (id: string) => void }) {
  const map = run.map;
  const mapCall = run.calls.find((c) => c.step === "map");
  const groups = run.videos.length ? run.videos : [{ index: 1, sections: run.sections.map((s) => s.n), minutes: 0, title: "" }];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-400">
        {map ? <span>{map.goals.length} learning goals from {map.items.length} book items{map.added ? ` (${map.added} added by code)` : ""}</span>
          : <span>The learning map is not made yet: the sections as code cut the book.</span>}
        {mapCall && <CallsLink run={run} ids={[mapCall.id]} onCall={onCall} />}
      </div>
      {groups.map((v) => {
        const plan = run.plans.find((p) => p.sections.some((s) => v.sections.includes(s.section)));
        const planCall = run.calls.find((c) => c.step === "plan" && c.label.includes(`video ${v.index} `));
        return (
          <section key={v.index} className="rounded border border-neutral-800 bg-neutral-900/60 p-3" data-testid="plan-video">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[11px] uppercase tracking-wide text-neutral-500">Video {v.index}{run.videos.length ? ` of ${run.videos.length}` : ""}
                {v.written ? ` · written ${v.written} min` : v.minutes ? ` · planned ${Math.round(v.minutes)} min` : ""}</p>
              {planCall && <CallsLink run={run} ids={[planCall.id]} onCall={onCall} />}
            </div>
            {plan ? (
              <div className="mt-1 space-y-1 text-sm">
                <p className="font-semibold text-neutral-100">{plan.bigQuestion}</p>
                <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-0.5 text-xs text-neutral-300">
                  {plan.runningExample && <><dt className="text-neutral-500">Running example</dt><dd>{plan.runningExample}</dd></>}
                  <dt className="text-neutral-500">Arc</dt><dd>{plan.arc}</dd>
                  <dt className="text-neutral-500">Opens with</dt><dd>{plan.opening}</dd>
                  <dt className="text-neutral-500">Closes with</dt><dd>{plan.closing}</dd>
                </dl>
              </div>
            ) : <p className="mt-1 text-xs text-neutral-500">{run.steps.find((s) => s.key === "plan")?.status === "done" ? "No story plan for this video." : "Story plan not made yet."}</p>}
            <ol className="mt-2 space-y-2">
              {v.sections.map((n) => {
                const s = run.sections.find((x) => x.n === n);
                if (!s) return null;
                const own = plan?.sections.find((x) => x.section === n);
                const goals = map?.goals.filter((g) => g.section === n) ?? [];
                const active = selection?.kind === "section" && selection.n === n;
                return (
                  <li key={n} onClick={() => select(active ? null : { kind: "section", n })}
                    className={`cursor-pointer rounded border p-2 ${active ? "border-white/60 bg-neutral-800" : "border-neutral-800 bg-neutral-950 hover:border-neutral-600"}`}>
                    <div className="flex items-center gap-2">
                      <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: swatch(n) }} />
                      <span className="text-sm font-semibold text-neutral-100">Section {n}{s.title ? `: ${s.title}` : ""}</span>
                      <span className="text-[11px] text-neutral-500">~{s.words} words{s.questionsOnly ? " · book questions only" : ""}</span>
                      <StatusDot status={s.status} />
                    </div>
                    {own && (
                      <div className="mt-1 space-y-0.5 text-xs text-neutral-400">
                        <p><span className="text-neutral-500">Picks up from:</span> {own.opensFrom}</p>
                        <p className="text-sky-300"><span className="text-neutral-500">Guess first:</span> {own.guessFirst}</p>
                        <p><span className="text-neutral-500">Ends on:</span> {own.handsOn}</p>
                      </div>
                    )}
                    {s.questions.length > 0 && (
                      <div className="mt-1 text-xs text-violet-300">
                        <span className="text-neutral-500">Book questions asked here:</span>
                        <ul className="ml-4 list-disc">{s.questions.map((q) => <li key={q.id}>{q.id} ({q.number}). {q.text}</li>)}</ul>
                      </div>
                    )}
                    {goals.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {goals.map((g) => {
                          const status = run.goalStatus[g.id] ?? "waiting";
                          const chosen = selection?.kind === "goal" && selection.id === g.id;
                          return (
                            <li key={g.id} onClick={(e) => { e.stopPropagation(); select(chosen ? null : { kind: "goal", id: g.id }); }}
                              className={`rounded px-1.5 py-1 ${chosen ? "bg-emerald-950/70 ring-1 ring-emerald-500" : "hover:bg-neutral-800"}`} data-testid="plan-goal">
                              <div className="flex items-start gap-2 text-xs">
                                <span className={`shrink-0 rounded border px-1 text-[10px] ${GOAL_TONE[status]}`}>{GOAL_LABEL[status]}</span>
                                <span className="text-neutral-100"><span className="text-neutral-500">{g.id}</span> {g.goal}
                                  {g.added && <span className="text-neutral-500"> (added by code for items the map left out)</span>}</span>
                              </div>
                              <div className="mt-0.5 ml-1 flex flex-wrap gap-1">
                                {g.items.map((id) => map!.items.find((i) => i.id === id)).filter(Boolean).map((i) => (
                                  <span key={i!.id} className="rounded bg-neutral-800 px-1.5 py-px text-[10px] text-neutral-300">
                                    <span className={ITEM_TONE[i!.kind]}>{i!.kind}</span> {i!.text.slice(0, 70)}
                                  </span>
                                ))}
                              </div>
                              {(g.misconception || g.hook) && (
                                <p className="mt-0.5 ml-1 text-[11px] text-neutral-500">
                                  {g.misconception && <>Wrong idea: <span className="text-neutral-400">{g.misconception}</span></>}
                                  {g.misconception && g.hook ? " · " : ""}{g.hook && <>Hook: <span className="text-neutral-400">{g.hook}</span></>}
                                </p>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                    <div className="mt-1"><CallsLink run={run} ids={s.calls} onCall={onCall} /></div>
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}
    </div>
  );
}

function StatusDot({ status }: { status: SectionState["status"] }) {
  const tone = { waiting: "bg-neutral-600", writing: "bg-sky-400 animate-pulse", written: "bg-emerald-400", failed: "bg-red-500" }[status];
  return <span className={`ml-auto h-2 w-2 shrink-0 rounded-full ${tone}`} title={status} />;
}

// ─── Transcript ──────────────────────────────────────────────────────────────────────────────────────────────────

export function TranscriptPanel({ run, selection, select, onCall }: { run: Run; selection: Selection; select: (s: Selection) => void;
  onCall: (id: string) => void }) {
  const goal = selection?.kind === "goal" ? selection.id : null;
  const words = run.sections.reduce((n, s) => n + (s.text ? s.text.split(/\s+/).length : 0), 0);
  return (
    <div className="space-y-3">
      <p className="text-xs text-neutral-400">{words.toLocaleString()} words written (about {Math.round(words / 100)} min).
        {" "}Green: the sentences that teach the selected goal. Amber: sentences written in by a patch.</p>
      {run.sections.map((s) => {
        const active = selection?.kind === "section" && selection.n === s.n;
        const goals = run.map?.goals.filter((g) => g.section === s.n) ?? [];
        const patched = new Set((s.patched ?? []).flatMap((p) => p.lines));
        const lit = new Set(goal ? s.goalLines?.[goal] ?? [] : []);
        const lines = s.text ? linesOf(s.text) : [];
        // Paragraphs kept: each sentence numbered as linesOf numbers them.
        let k = 0;
        return (
          <section key={s.n} className={`rounded border p-3 ${active ? "border-white/60" : "border-neutral-800"} bg-neutral-900/60`} data-testid="transcript-section">
            <div className="flex cursor-pointer items-center gap-2" onClick={() => select(active ? null : { kind: "section", n: s.n })}>
              <span className="h-3 w-3 rounded-sm" style={{ background: swatch(s.n) }} />
              <h3 className="text-sm font-semibold text-neutral-100">Section {s.n}{s.title ? `: ${s.title}` : ""}</h3>
              <span className="text-[11px] text-neutral-500">{s.text ? `${s.text.split(/\s+/).length} words of about ${s.words}` : s.status}</span>
              <StatusDot status={s.status} />
            </div>
            {goals.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {goals.map((g) => {
                  const status = run.goalStatus[g.id] ?? "waiting";
                  return (
                    <button key={g.id} onClick={() => select(goal === g.id ? null : { kind: "goal", id: g.id })} title={g.goal}
                      className={`rounded border px-1.5 py-px text-[10px] ${GOAL_TONE[status]} ${goal === g.id ? "ring-1 ring-white" : ""}`}>
                      {g.id} {GOAL_LABEL[status]}{s.goalLines?.[g.id]?.length ? ` · sentence ${s.goalLines[g.id].join(", ")}` : ""}
                    </button>
                  );
                })}
              </div>
            )}
            {s.text ? (
              <div className="mt-2 space-y-2 text-[13.5px] leading-relaxed text-neutral-200">
                {s.text.split(/\n\s*\n/).map((para, p) => (
                  <p key={p}>
                    {linesOf(para).map((line) => {
                      k += 1;
                      const n = k;
                      return (
                        <span key={n} title={`sentence ${n}`}
                          className={lit.has(n) ? "rounded bg-emerald-800/70 text-white" : patched.has(n) ? "rounded bg-amber-900/60" : ""}>
                          <sup className="mr-0.5 text-[9px] text-neutral-600">{n}</sup>{line}{" "}
                        </span>
                      );
                    })}
                  </p>
                ))}
                {lines.length !== k && <p className="text-[11px] text-neutral-600">({lines.length} sentences)</p>}
              </div>
            ) : <p className="mt-2 text-xs text-neutral-500">{s.status === "writing" ? "Being written…" : s.status === "failed" ? "Could not be written." : "Not written yet."}</p>}
            {(s.dropped?.length ?? 0) > 0 && (
              <details className="mt-2 text-xs text-neutral-400">
                <summary className="cursor-pointer">{s.dropped!.length} sentence{s.dropped!.length > 1 ? "s" : ""} taken out as said before</summary>
                <ul className="ml-4 list-disc">{s.dropped!.map((d, i) => <li key={i}>{d}</li>)}</ul>
              </details>
            )}
            <div className="mt-2"><CallsLink run={run} ids={s.calls} onCall={onCall} /></div>
          </section>
        );
      })}
    </div>
  );
}

// ─── Calls ───────────────────────────────────────────────────────────────────────────────────────────────────────

export function CallsPanel({ run, onCall, section }: { run: Run; onCall: (id: string) => void; section?: number }) {
  const [step, setStep] = useState("all");
  const steps = ["all", ...new Set(run.calls.map((c) => c.step))];
  const rows = run.calls.filter((c) => (step === "all" || c.step === step) && (!section || c.section === section || !c.section));
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1 text-xs">
        {steps.map((s) => (
          <button key={s} onClick={() => setStep(s)}
            className={`rounded border px-2 py-0.5 ${step === s ? "border-white/60 bg-neutral-800" : "border-neutral-700 hover:bg-neutral-800"}`}>{s}</button>
        ))}
        {section ? <span className="text-neutral-500">· section {section} and the lecture-wide calls</span> : null}
      </div>
      <table className="w-full text-left text-xs" data-testid="calls-table">
        <thead className="text-[10px] uppercase tracking-wide text-neutral-500">
          <tr><th className="py-1">#</th><th>Call</th><th>Model</th><th>Status</th><th className="text-right">Time</th>
            <th className="text-right">In / out</th><th className="text-right">Cost</th><th className="pl-3">Checks</th></tr>
        </thead>
        <tbody>
          {rows.map((c) => <CallRow key={c.id} call={c} onCall={onCall} />)}
        </tbody>
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

export function CostsPanel({ run }: { run: Run }) {
  const total = run.calls.reduce((n, c) => n + c.cost, 0);
  const group = (key: (c: Call) => string) => {
    const out = new Map<string, { calls: number; input: number; output: number; cost: number; time: number }>();
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
  const Table = ({ title, rows }: { title: string; rows: [string, { calls: number; input: number; output: number; cost: number; time: number }][] }) => (
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
      <Table title="By section" rows={group((c) => (c.section ? `Section ${c.section}` : "Lecture-wide (map, plans)"))} />
    </div>
  );
}

// ─── Models ──────────────────────────────────────────────────────────────────────────────────────────────────────

type ModelCheck = { model: string; ok: boolean; seconds: number; cost: number; reply?: string; error?: string;
  prices?: { input: number; output: number }; context?: number; fixture?: boolean };

export function ModelsPanel({ models }: { models: { role: string; model: string }[] }) {
  const [results, setResults] = useState<Record<string, ModelCheck | "checking">>({});
  const check = async (model: string) => {
    setResults((r) => ({ ...r, [model]: "checking" }));
    const res = await fetch("/api/models", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model }) });
    const json = await res.json();
    setResults((r) => ({ ...r, [model]: json }));
  };
  return (
    <div className="space-y-2" data-testid="models">
      <p className="text-xs text-neutral-400">Each model the run uses, checked with a one-word call: whether it answers, how fast, and its
        prices from OpenRouter's list.</p>
      {models.map(({ role, model }) => {
        const r = results[`${model}`];
        return (
          <div key={role} className="rounded border border-neutral-800 bg-neutral-900/60 p-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="w-28 text-neutral-500">{role}</span>
              <span className="mono text-neutral-100">{model}</span>
              <button onClick={() => check(model)} className="ml-auto rounded border border-neutral-700 px-2 py-0.5 text-xs hover:bg-neutral-800">Check</button>
            </div>
            {r === "checking" && <p className="mt-1 text-xs text-sky-300">Checking…</p>}
            {r && r !== "checking" && (
              <p className={`mt-1 text-xs ${r.ok ? "text-emerald-300" : "text-red-300"}`}>
                {r.ok ? "✓ answers" : "✗ fails"}{r.fixture ? " (offline stand-in)" : ` in ${r.seconds.toFixed(1)} s, ${money(r.cost)}`}
                {r.reply ? ` · "${r.reply}"` : ""}{r.error ? ` · ${r.error}` : ""}
                {r.prices ? ` · $${r.prices.input.toFixed(2)} / $${r.prices.output.toFixed(2)} per million tokens in / out` : " · prices not found"}
                {r.context ? ` · ${Math.round(r.context / 1000)}k context` : ""}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
