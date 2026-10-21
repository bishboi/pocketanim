"use client";

/**
 * What the video agent did on a chapter (lib/video-agent.ts), in five views:
 *
 *   - What it did: the outcome and its summary, and the counts: time, turns, cost, tokens, files written, renders,
 *     looks, pictures, commands, phone checks.
 *   - Steps: the turn being written now, live (its reasoning, its words, the tools it is calling, or the tool running),
 *     then every turn: what the model took, said and thought, and each tool it called with its answer.
 *   - Commands: everything it ran, in order: shell commands with their exit codes and output, renders, looks, pictures,
 *     phone checks, with how long each took.
 *   - Files: its workspace, each file readable, and every version of every file it wrote, with what changed.
 *   - Conversation: the whole conversation as sent and answered (agent-log.jsonl in its workspace).
 */

import { useEffect, useMemo, useState } from "react";
import type { ChapterAgent, Run, VideoStep } from "@/lib/types";
import { money } from "./call-inspector";

const VIEWS = ["What it did", "Steps", "Commands", "Files", "Conversation"] as const;
const btn = "rounded border px-2 py-0.5 text-[11px] disabled:opacity-40";
const pre = "max-h-96 overflow-auto whitespace-pre-wrap rounded bg-neutral-950 p-2 text-[11px] text-neutral-300";

export const took = (n?: number) => n === undefined ? "" : n < 1000 ? `${n} ms` : n < 60_000 ? `${(n / 1000).toFixed(1)} s`
  : `${Math.floor(n / 60_000)} min ${Math.round((n % 60_000) / 1000)} s`;

type Entry = Record<string, unknown> & { t: number; kind: string };
type FileRow = { path: string; size: number; at: number };

/** A file of the workspace as a URL the page can load (pictures, videos). */
const wsUrl = (runId: string, n: number, c: number, rel: string) =>
  `/api/runs/${runId}/scenes/file?p=${encodeURIComponent(`video/L${n}/C${c}/${rel}`)}`;
const isImage = (p: string) => /\.(png|jpe?g|webp)$/i.test(p);
const isVideo = (p: string) => /\.mp4$/i.test(p);

/** Lines added and removed between two texts (the longest common subsequence of their lines). */
function diffLines(before: string, after: string): { k: " " | "-" | "+"; line: string }[] {
  const a = before.split("\n");
  const b = after.split("\n");
  if (a.length * b.length > 4_000_000) return [...a.map((line) => ({ k: "-" as const, line })), ...b.map((line) => ({ k: "+" as const, line }))];
  const w = b.length + 1;
  const dp = new Uint32Array((a.length + 1) * w);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i * w + j] = a[i] === b[j] ? dp[(i + 1) * w + j + 1] + 1 : Math.max(dp[(i + 1) * w + j], dp[i * w + j + 1]);
    }
  }
  const out: { k: " " | "-" | "+"; line: string }[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { out.push({ k: " ", line: a[i] }); i++; j++; }
    else if (dp[(i + 1) * w + j] >= dp[i * w + j + 1]) out.push({ k: "-", line: a[i++] });
    else out.push({ k: "+", line: b[j++] });
  }
  while (i < a.length) out.push({ k: "-", line: a[i++] });
  while (j < b.length) out.push({ k: "+", line: b[j++] });
  return out;
}

/** The changed lines with three lines of context round each change. */
function Diff({ before, after }: { before: string; after: string }) {
  const rows = useMemo(() => diffLines(before, after), [before, after]);
  const near = new Set<number>();
  rows.forEach((r, i) => { if (r.k !== " ") for (let k = i - 3; k <= i + 3; k++) near.add(k); });
  if (!near.size) return <p className="text-neutral-500">No change.</p>;
  const added = rows.filter((r) => r.k === "+").length;
  const removed = rows.filter((r) => r.k === "-").length;
  return (
    <div>
      <p className="mb-1 text-neutral-400"><span className="text-emerald-300">+{added}</span> <span className="text-red-300">-{removed}</span> lines</p>
      <pre className={`${pre} max-h-[32rem]`} data-testid="agent-diff">
        {rows.map((r, i) => near.has(i) ? (
          <div key={i} className={r.k === "+" ? "bg-emerald-950 text-emerald-200" : r.k === "-" ? "bg-red-950 text-red-200" : ""}>{r.k} {r.line}</div>
        ) : near.has(i - 1) ? <div key={i} className="text-neutral-600">…</div> : null)}
      </pre>
    </div>
  );
}

/** What a tool call was about, in a few words. */
function headOf(s: VideoStep): string {
  const a = s.args ?? {};
  switch (s.tool) {
    case "write_file": case "edit_file": case "read_file": return String(a.path ?? "") + (s.version ? ` → v${s.version}` : "");
    case "list_files": return String(a.path ?? ".");
    case "shell": return String(a.command ?? "");
    case "render": return String(a.quality ?? "draft");
    case "look": return Array.isArray(a.times) && a.times.length ? `frames at ${(a.times as number[]).join(", ")} s` : `a sheet${a.sheet_every ? ` every ${a.sheet_every} s` : ""}`;
    case "make_image": return `${a.name} (${a.kind}): ${String(a.what ?? "")}`;
    case "phone_check": return `${a.samples ?? 12} frames`;
    case "finish": return String(a.summary ?? "").split("\n")[0];
    default: return "";
  }
}

function ToolRow({ s, onCall }: { s: VideoStep; onCall: (id: string) => void }) {
  const a = s.args ?? {};
  return (
    <li className="rounded border border-neutral-800 p-2" data-testid="video-step">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className={`font-semibold ${s.ok === false ? "text-red-300" : s.kind === "finish" ? "text-emerald-300" : "text-sky-300"}`}>{s.tool}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-neutral-400" title={headOf(s)}>{headOf(s)}</span>
        {s.exit !== undefined && <span className={s.exit === 0 ? "text-neutral-500" : "text-red-300"}>exit {String(s.exit)}</span>}
        <span className="text-neutral-500">{took(s.ms)}</span>
        {s.call && <button className="text-neutral-500 underline" onClick={() => onCall(s.call!)}>call</button>}
      </div>
      {s.result && (
        <details className="mt-1">
          <summary className="cursor-pointer text-neutral-400">{s.result.split("\n")[0].slice(0, 200)}</summary>
          <pre className={`mt-1 ${pre}`}>{s.result}</pre>
          {s.tool === "write_file" && <pre className={`mt-1 ${pre} text-neutral-400`}>{String(a.content ?? "")}</pre>}
          {s.tool === "edit_file" && <Diff before={String(a.old ?? "")} after={String(a.new ?? "")} />}
        </details>
      )}
      {s.images?.length ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {s.images.map((u) => <a key={u} href={u} target="_blank" rel="noreferrer"><img src={u} alt="" className="max-h-40 rounded border border-neutral-800" /></a>)}
        </div>
      ) : null}
      {s.video && <a className="mt-1 inline-block text-sky-300 underline" href={s.video} target="_blank" rel="noreferrer">the render ({s.seconds?.toFixed(1)} s)</a>}
    </li>
  );
}

function Live({ agent, now }: { agent: ChapterAgent; now: number }) {
  const live = agent.live;
  if (agent.status !== "running") return null;
  return (
    <div className="rounded border border-sky-800 bg-sky-950/30 p-2" data-testid="agent-live">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="animate-pulse text-sky-300">●</span>
        <span className="font-semibold text-sky-200">turn {live?.turn ?? agent.turns}</span>
        <span className="text-neutral-300">{live ? (live.tools[0]?.startsWith("running ") ? live.tools[0] : live.tools.length ? `calling ${live.tools.join(", ")}` : "the model is writing") : "between turns"}</span>
        {live && <span className="text-neutral-500">{took(now - live.started)}</span>}
      </div>
      {live?.reasoning && (
        <details open className="mt-1"><summary className="cursor-pointer text-neutral-400">Reasoning (as it streams)</summary>
          <pre className={`mt-1 ${pre} max-h-48 text-neutral-400`}>{live.reasoning}</pre></details>
      )}
      {live?.text && <p className="mt-1 whitespace-pre-wrap text-neutral-200">{live.text}</p>}
    </div>
  );
}

function Steps({ agent, onCall, now }: { agent: ChapterAgent; onCall: (id: string) => void; now: number }) {
  const turns = useMemo(() => {
    const by = new Map<number, VideoStep[]>();
    for (const s of agent.steps) by.set(s.turn, [...(by.get(s.turn) ?? []), s]);
    return [...by.entries()].sort((a, b) => b[0] - a[0]);
  }, [agent.steps]);
  return (
    <div className="space-y-2">
      <Live agent={agent} now={now} />
      <p className="text-neutral-500">Newest turn first.</p>
      {turns.map(([k, steps]) => {
        const think = steps.find((s) => s.kind === "think" || s.kind === "error");
        const tools = steps.filter((s) => s.kind === "tool" || s.kind === "finish");
        return (
          <section key={k} className="rounded border border-neutral-800 p-2" data-testid="agent-turn">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-semibold text-neutral-100">turn {k}</span>
              {think?.ms !== undefined && <span className="text-neutral-500">model {took(think.ms)}</span>}
              {think?.tokens && <span className="text-neutral-500">{think.tokens.input.toLocaleString()} in · {think.tokens.output.toLocaleString()} out{think.tokens.reasoning ? ` (${think.tokens.reasoning.toLocaleString()} reasoning)` : ""}</span>}
              {think?.cost ? <span className="text-neutral-500">{money(think.cost)}</span> : null}
              <span className="text-neutral-500">{tools.map((t) => t.tool).join(", ")}</span>
              {think?.call && <button className="ml-auto text-neutral-500 underline" onClick={() => onCall(think.call!)}>call</button>}
            </div>
            {think?.kind === "error" && <p className="mt-1 text-red-300">{think.text}</p>}
            {think?.reasoning && <details className="mt-1"><summary className="cursor-pointer text-neutral-400">Reasoning</summary><pre className={`mt-1 ${pre} text-neutral-400`}>{think.reasoning}</pre></details>}
            {think?.kind === "think" && think.text && <p className="mt-1 whitespace-pre-wrap text-neutral-200">{think.text}</p>}
            <ol className="mt-1 space-y-1">{tools.map((s, i) => <ToolRow key={i} s={s} onCall={onCall} />)}</ol>
          </section>
        );
      })}
    </div>
  );
}

const KINDS = { all: "Everything", shell: "Shell commands", render: "Renders and looks", phone_check: "Phone checks", make_image: "Pictures", files: "File writes" } as const;

function Commands({ agent, onCall }: { agent: ChapterAgent; onCall: (id: string) => void }) {
  const [kind, setKind] = useState<keyof typeof KINDS>("all");
  const rows = agent.steps.filter((s) => s.kind === "tool" || s.kind === "finish").filter((s) => kind === "all" || (kind === "render" ? s.tool === "render" || s.tool === "look"
    : kind === "files" ? s.tool === "write_file" || s.tool === "edit_file" : s.tool === kind));
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {(Object.keys(KINDS) as (keyof typeof KINDS)[]).map((k) => (
          <button key={k} className={`${btn} ${kind === k ? "border-sky-600 text-sky-200" : "border-neutral-700 text-neutral-400"}`} onClick={() => setKind(k)}>{KINDS[k]}</button>
        ))}
      </div>
      <table className="w-full table-fixed text-left" data-testid="agent-commands">
        <thead className="text-neutral-500"><tr><th className="w-12">Turn</th><th className="w-24">Tool</th><th>What</th><th className="w-20">Result</th><th className="w-20">Took</th></tr></thead>
        <tbody>
          {rows.map((s, i) => (
            <tr key={i} className="border-t border-neutral-800 align-top">
              <td className="py-1 text-neutral-500">{s.turn}</td>
              <td className="text-sky-300">{s.tool}</td>
              <td className="min-w-0">
                <details>
                  <summary className="cursor-pointer truncate font-mono text-neutral-300">{headOf(s) || "—"}</summary>
                  {s.tool === "shell" && <pre className={`mt-1 ${pre} text-neutral-400`}>$ {String(s.args?.command ?? "")}</pre>}
                  {s.result && <pre className={`mt-1 ${pre}`}>{s.result}</pre>}
                  {s.call && <button className="text-neutral-500 underline" onClick={() => onCall(s.call!)}>call</button>}
                </details>
              </td>
              <td className={s.ok === false ? "text-red-300" : "text-emerald-300"}>{s.exit !== undefined ? `exit ${String(s.exit)}` : s.ok === false ? "failed" : "ok"}</td>
              <td className="text-neutral-500">{took(s.ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="text-neutral-500">Nothing of this kind yet.</p>}
    </div>
  );
}

function Files({ run, n, c, agent }: { run: Run; n: number; c: number; agent: ChapterAgent }) {
  const [files, setFiles] = useState<FileRow[]>([]);
  const [open, setOpen] = useState<string | null>("scene.py");
  const [version, setVersion] = useState<number | null>(null);
  const [text, setText] = useState<{ now?: string; before?: string; error?: string }>({});
  const [showDiff, setShowDiff] = useState(true);
  const running = agent.status === "running";
  const base = `/api/runs/${run.id}/video?lecture=${n}&chapter=${c}`;
  useEffect(() => {
    let live = true;
    const load = () => fetch(`${base}&files=1`).then((r) => r.json()).then((j) => live && setFiles(j.files ?? [])).catch(() => {});
    void load();
    const t = running ? setInterval(load, 5000) : undefined;
    return () => { live = false; if (t) clearInterval(t); };
  }, [base, running, agent.versions?.length]);
  const versions = (agent.versions ?? []).filter((v) => v.path === open);
  const shown = version !== null ? versions.find((v) => v.v === version) : undefined;
  const before = shown ? versions[versions.indexOf(shown) - 1] : versions.at(-2);
  useEffect(() => {
    setText({});
    if (!open || isImage(open) || isVideo(open)) return;
    const read = (rel: string) => fetch(`${base}&read=${encodeURIComponent(rel)}`).then((r) => r.json()).then((j) => j.error ? Promise.reject(new Error(j.error)) : j.text as string);
    const now = shown ? read(shown.file) : read(open);
    const prev = before ? read(before.file) : Promise.resolve(undefined);
    Promise.all([now, prev]).then(([a, b]) => setText({ now: a, before: b })).catch((e: Error) => setText({ error: e.message }));
  }, [base, open, shown?.v, before?.v, agent.versions?.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const written = new Set((agent.versions ?? []).map((v) => v.path));
  return (
    <div className="flex gap-3" data-testid="agent-files">
      <ul className="w-64 shrink-0 space-y-0.5">
        {files.map((f) => (
          <li key={f.path}>
            <button className={`w-full truncate text-left ${open === f.path ? "text-sky-200" : written.has(f.path) ? "text-neutral-200" : "text-neutral-400"}`}
              title={`${f.path} · ${(f.size / 1024).toFixed(1)} kB`} onClick={() => { setOpen(f.path); setVersion(null); }}>
              {f.path} <span className="text-neutral-600">{f.size > 1e6 ? `${(f.size / 1e6).toFixed(1)} MB` : `${(f.size / 1024).toFixed(1)} kB`}</span>
              {written.has(f.path) && <span className="text-neutral-500"> · {(agent.versions ?? []).filter((v) => v.path === f.path).length} version(s)</span>}
            </button>
          </li>
        ))}
        {!files.length && <li className="text-neutral-500">Nothing yet.</li>}
      </ul>
      <div className="min-w-0 flex-1">
        {open && (
          <>
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="font-mono text-neutral-200">{open}</span>
              {versions.length > 0 && (
                <select className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5" value={version ?? ""} onChange={(e) => setVersion(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">as it is now</option>
                  {versions.map((v) => <option key={v.v} value={v.v}>v{v.v} · turn {v.turn} · {v.lines} lines</option>)}
                </select>
              )}
              {versions.length > 0 && <label className="flex items-center gap-1 text-neutral-400"><input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />what changed{before ? ` since v${before.v}` : ""}</label>}
              <a className="ml-auto text-sky-300 underline" href={wsUrl(run.id, n, c, shown?.file ?? open)} target="_blank" rel="noreferrer">open</a>
            </div>
            {isImage(open) ? <img src={wsUrl(run.id, n, c, open)} alt="" className="max-h-[32rem] rounded border border-neutral-800" />
              : isVideo(open) ? <video controls src={wsUrl(run.id, n, c, open)} className="max-h-[32rem] w-full" />
              : text.error ? <p className="text-red-300">{text.error}</p>
              : text.now === undefined ? <p className="text-neutral-500">Loading…</p>
              : showDiff && versions.length > 0 ? (before && text.before !== undefined ? <Diff before={text.before} after={text.now} /> : <><p className="mb-1 text-neutral-500">The first version.</p><pre className={`${pre} max-h-[32rem]`}>{text.now}</pre></>)
              : <pre className={`${pre} max-h-[32rem]`}>{text.now.split("\n").map((l, i) => <div key={i}><span className="mr-2 inline-block w-8 select-none text-right text-neutral-600">{i + 1}</span>{l}</div>)}</pre>}
          </>
        )}
      </div>
    </div>
  );
}

function Conversation({ run, n, c, agent, onCall }: { run: Run; n: number; c: number; agent: ChapterAgent; onCall: (id: string) => void }) {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const running = agent.status === "running";
  const base = `/api/runs/${run.id}/video?lecture=${n}&chapter=${c}`;
  useEffect(() => {
    let live = true;
    const load = () => fetch(`${base}&log=1`).then((r) => r.json()).then((j) => live && setEntries(j.entries ?? [])).catch(() => {});
    void load();
    const t = running ? setInterval(load, 4000) : undefined;
    return () => { live = false; if (t) clearInterval(t); };
  }, [base, running, agent.steps.length]);
  if (!entries) return <p className="text-neutral-500">Loading…</p>;
  if (!entries.length) return <p className="text-neutral-500">No conversation kept for this build (builds before the log was kept have only their steps).</p>;
  const turnCall = (turn: unknown) => agent.steps.find((s) => s.turn === turn && s.call)?.call;
  return (
    <ol className="space-y-1" data-testid="agent-conversation">
      {entries.map((e, i) => {
        const time = new Date(e.t).toLocaleTimeString();
        const tag = (label: string, tone: string) => <span className={`font-semibold ${tone}`}>{label}</span>;
        if (e.kind === "build") return <li key={i} className="text-neutral-400">{time} · build started: {String(e.model)}{e.note ? ` · note: ${String(e.note)}` : ""} · at most {String(e.turns)} turns</li>;
        if (e.kind === "system") return <li key={i}><details><summary className="cursor-pointer">{tag("system", "text-violet-300")} the agent&apos;s instructions</summary><pre className={`mt-1 ${pre}`}>{String(e.text)}</pre></details></li>;
        if (e.kind === "user") return (
          <li key={i}><details><summary className="cursor-pointer">{tag("user", "text-amber-300")} the chapter and its narration{(e.images as string[])?.length ? " (with the look's screenshot)" : ""}</summary>
            <pre className={`mt-1 ${pre}`}>{String(e.text)}</pre>
            {(e.images as string[] ?? []).map((f) => <img key={f} src={wsUrl(run.id, n, c, f)} alt="" className="mt-1 max-h-40 rounded" />)}</details></li>
        );
        if (e.kind === "assistant") {
          const tools = (e.tools as { id: string; name: string; args: Record<string, unknown> }[]) ?? [];
          const usage = e.usage as { input?: number; output?: number } | undefined;
          const call = turnCall(e.turn);
          return (
            <li key={i} className="rounded border border-neutral-800 p-2">
              <div className="flex flex-wrap items-baseline gap-2">{tag(`assistant · turn ${String(e.turn)}`, "text-sky-300")}
                <span className="text-neutral-500">{time} · {took(Number(e.ms))}{usage ? ` · ${usage.input ?? 0} in, ${usage.output ?? 0} out` : ""}{e.cost ? ` · ${money(Number(e.cost))}` : ""}</span>
                {call && <button className="ml-auto text-neutral-500 underline" onClick={() => onCall(call)}>call</button>}</div>
              {e.reasoning ? <details className="mt-1"><summary className="cursor-pointer text-neutral-400">Reasoning</summary><pre className={`mt-1 ${pre} text-neutral-400`}>{String(e.reasoning)}</pre></details> : null}
              {e.text ? <p className="mt-1 whitespace-pre-wrap text-neutral-200">{String(e.text)}</p> : null}
              {tools.map((t) => (
                <details key={t.id} className="mt-1"><summary className="cursor-pointer font-mono text-neutral-300">→ {t.name}({Object.keys(t.args ?? {}).join(", ")})</summary>
                  {Object.entries(t.args ?? {}).map(([k, v]) => (
                    <div key={k} className="mt-1"><span className="text-neutral-500">{k}</span>
                      <pre className={pre}>{typeof v === "string" ? v : JSON.stringify(v, null, 1)}</pre></div>
                  ))}</details>
              ))}
            </li>
          );
        }
        if (e.kind === "tool") return (
          <li key={i} className="ml-4"><details><summary className="cursor-pointer">{tag(`← ${String(e.name)}`, e.ok === false ? "text-red-300" : "text-emerald-300")}
            <span className="text-neutral-500"> · {took(Number(e.ms))}{e.exit !== undefined ? ` · exit ${String(e.exit)}` : ""}{e.version ? ` · v${String(e.version)}` : ""} · </span>
            <span className="text-neutral-400">{String(e.result ?? "").split("\n")[0].slice(0, 160)}</span></summary>
            <pre className={`mt-1 ${pre}`}>{String(e.result ?? "")}</pre></details></li>
        );
        if (e.kind === "images") return (
          <li key={i} className="ml-4"><span className="text-neutral-400">{String(e.label)}</span>
            <div className="mt-1 flex flex-wrap gap-1">{(e.files as string[] ?? []).map((f) => <a key={f} href={wsUrl(run.id, n, c, f)} target="_blank" rel="noreferrer"><img src={wsUrl(run.id, n, c, f)} alt="" className="max-h-32 rounded border border-neutral-800" /></a>)}</div></li>
        );
        if (e.kind === "end") return <li key={i} className="text-neutral-400">{time} · ended: <span className={e.status === "done" ? "text-emerald-300" : "text-red-300"}>{String(e.status)}</span>{e.error ? ` · ${String(e.error)}` : ""} · {String(e.turns)} turns · {money(Number(e.cost ?? 0))}</li>;
        if (e.kind === "error") return <li key={i} className="text-red-300">turn {String(e.turn)}: {String(e.text)}</li>;
        return null;
      })}
    </ol>
  );
}

function Outcome({ agent, built }: { agent: ChapterAgent; built?: { seconds: number; bytes: number; check?: { frames: number; differ: unknown[] } } }) {
  const tools = agent.steps.filter((s) => s.kind === "tool" || s.kind === "finish");
  const thinks = agent.steps.filter((s) => s.kind === "think");
  const count = (t: string) => tools.filter((s) => s.tool === t).length;
  const failed = (t: string) => tools.filter((s) => s.tool === t && s.ok === false).length;
  const sum = (xs: (number | undefined)[]) => xs.reduce<number>((k, x) => k + (x ?? 0), 0);
  const tokensIn = sum(thinks.map((s) => s.tokens?.input));
  const tokensOut = sum(thinks.map((s) => s.tokens?.output));
  const files = [...new Set((agent.versions ?? []).map((v) => v.path))];
  const checks = tools.filter((s) => s.tool === "phone_check");
  const renders = tools.filter((s) => s.tool === "render" && s.ok);
  const pictures = tools.filter((s) => s.tool === "make_image" && s.ok);
  const stats: [string, string][] = [
    ["Time", took((agent.ended ?? Date.now()) - agent.started)],
    ["Turns", String(agent.turns)],
    ["Model time", took(sum(thinks.map((s) => s.ms)))],
    ["Tool time", took(sum(tools.map((s) => s.ms)))],
    ["Cost", money(agent.cost)],
    ["Tokens", `${tokensIn.toLocaleString()} in · ${tokensOut.toLocaleString()} out`],
    ["Files written", `${files.length} (${(agent.versions ?? []).length} versions)`],
    ["Shell commands", `${count("shell")}${failed("shell") ? ` (${failed("shell")} failed)` : ""}`],
    ["Renders", `${count("render")}${failed("render") ? ` (${failed("render")} failed)` : ""}`],
    ["Looks", String(count("look"))],
    ["Pictures made", String(pictures.length)],
    ["Phone checks", `${checks.length}${checks.length ? ` (last: ${checks.at(-1)!.ok ? "passed" : "failed"})` : ""}`],
  ];
  return (
    <div className="space-y-2" data-testid="agent-outcome">
      <p className={agent.status === "done" ? "text-emerald-300" : agent.status === "running" ? "text-sky-300" : "text-red-300"}>
        {agent.status === "done" ? "Finished" : agent.status === "running" ? "Still building" : agent.status === "stopped" ? "Stopped" : "Did not finish"}
        {agent.error ? `: ${agent.error}` : ""}
        {built ? ` · the chapter plays on the phone: ${built.seconds.toFixed(1)} s, ${(built.bytes / 1e6).toFixed(1)} MB${built.check ? `, ${built.check.frames} frames compared with Manim's, ${built.check.differ.length} differ` : ""}` : ""}
      </p>
      {agent.summary && <div><div className="text-neutral-400">In its own words</div><p className="whitespace-pre-wrap text-neutral-200">{agent.summary}</p></div>}
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 sm:grid-cols-3 lg:grid-cols-4">
        {stats.map(([k, v]) => <div key={k}><span className="text-neutral-500">{k}</span> <span className="text-neutral-200">{v}</span></div>)}
      </div>
      {files.length > 0 && <div><span className="text-neutral-500">Files: </span><span className="font-mono text-neutral-300">{files.join(", ")}</span></div>}
      {pictures.length > 0 && (
        <div className="flex flex-wrap gap-1">{pictures.flatMap((s) => s.images ?? []).map((u) => <img key={u} src={u} alt="" title="a picture it made" className="max-h-24 rounded border border-neutral-800" />)}</div>
      )}
      {renders.at(-1)?.video && <a className="text-sky-300 underline" href={renders.at(-1)!.video} target="_blank" rel="noreferrer">its last render ({renders.at(-1)!.seconds?.toFixed(1)} s)</a>}
    </div>
  );
}

export function AgentLog({ run, n, c, agent, built, onCall }: { run: Run; n: number; c: number; agent: ChapterAgent;
  built?: { seconds: number; bytes: number; check?: { frames: number; differ: unknown[] } }; onCall: (id: string) => void }) {
  const [view, setView] = useState<(typeof VIEWS)[number]>(agent.status === "running" ? "Steps" : "What it did");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (agent.status !== "running") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [agent.status]);
  return (
    <div className="space-y-2" data-testid="agent-log">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="font-semibold text-neutral-200">The agent</span>
        <span className="text-neutral-400">{agent.model}{agent.effort ? ` · reasoning ${agent.effort}` : ""} · {agent.turns} turn(s) · {money(agent.cost)}{agent.note ? ` · note: ${agent.note}` : ""}</span>
        <span className="ml-auto flex gap-1">
          {VIEWS.map((v) => (
            <button key={v} data-testid={`agent-view-${v}`} className={`${btn} ${view === v ? "border-sky-600 text-sky-200" : "border-neutral-700 text-neutral-400"}`} onClick={() => setView(v)}>{v}</button>
          ))}
        </span>
      </div>
      {agent.status === "running" && view !== "Steps" && <Live agent={agent} now={now} />}
      {view === "What it did" && <Outcome agent={agent} built={built} />}
      {view === "Steps" && <Steps agent={agent} onCall={onCall} now={now} />}
      {view === "Commands" && <Commands agent={agent} onCall={onCall} />}
      {view === "Files" && <Files run={run} n={n} c={c} agent={agent} />}
      {view === "Conversation" && <Conversation run={run} n={n} c={c} agent={agent} onCall={onCall} />}
    </div>
  );
}
