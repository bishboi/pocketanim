"use client";

/**
 * The Lab: try animations with the voice, apart from the lectures (lib/lab.ts). Each experiment is a chapter's beat
 * script (engine/BEAT_SCRIPT.md), started from a preset (one per kind of animation), from a lecture's chapter, or
 * blank; edited here, and spoken and played: compiled, spoken with the Voice tab's voice, its animations timed to the
 * words, and played with its narration, with every line's word times and each animation's start shown under it.
 */

import { useEffect, useState } from "react";
import { LAB_BETA_PRESETS, LAB_BETA_SNIPPETS, LAB_PRESETS, LAB_SNIPPETS } from "@/lib/lab-presets";
import type { LabItem, Run } from "@/lib/types";
import { ENGINES } from "@/lib/voice-engines";
import { unfence, VoiceResult } from "./voice-panel";

type Act = (body: Record<string, unknown>) => Promise<boolean>;
const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";
const TONE = { running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;

export function LabPanel({ run, ready, onCall, act, voiceAct }: {
  run: Run; ready?: Record<string, boolean>; onCall: (id: string) => void; act: Act; voiceAct: Act;
}) {
  const items = run.lab?.items ?? [];
  const [open, setOpen] = useState<string | undefined>(items[0]?.id);
  const [count, setCount] = useState(items.length);
  // A new experiment is opened as it arrives.
  useEffect(() => {
    if (items.length > count) setOpen(items[items.length - 1].id);
    setCount(items.length);
  }, [items.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const settings = run.voice?.settings ?? { engine: ready?.gemini ? "gemini" : "espeak", pace: "natural" };
  const engine = ENGINES.find((e) => e.id === settings.engine) ?? ENGINES[0];
  const item = items.find((i) => i.id === open);
  const chapters = run.lectures.flatMap((l) => (run.script?.lectures[l.n]?.chapters ?? []).map((c) => ({ n: l.n, c })));

  return (
    <div className="space-y-3" data-testid="lab">
      <section className="rounded border border-neutral-800 p-3 text-xs">
        <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-sm font-semibold text-neutral-100">Lab</h3>
          <span className="text-neutral-400">
            Try animations with the voice, apart from the lectures: start from a preset (one for each kind of animation), a lecture&apos;s chapter,
            or blank; change its beat-script JSON; <b>Speak and play</b> compiles it, speaks it, times each animation to its words and plays it.
          </span>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-neutral-400">Voice (the Voice tab&apos;s)</span>
            <select data-testid="lab-engine" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={settings.engine}
              onChange={(e) => void voiceAct({ action: "settings", engine: e.target.value, voice: "" })}>
              {ENGINES.map((e) => <option key={e.id} value={e.id}>{e.label}{ready && !ready[e.id] ? " (no key)" : ""}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-neutral-400">Pace</span>
            <select className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={settings.pace ?? "natural"}
              onChange={(e) => void voiceAct({ action: "settings", pace: e.target.value })}>
              <option value="natural">natural</option><option value="relaxed">relaxed</option><option value="slow">slow</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-neutral-400">New experiment from a preset</span>
            <select data-testid="lab-preset" className="w-64 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value=""
              onChange={(e) => { if (e.target.value) void act({ action: "add", preset: e.target.value }); }}>
              <option value="">pick one…</option>
              <optgroup label="The current engine">
                {LAB_PRESETS.map((p) => <option key={p.id} value={p.id}>{p.name}: {p.note}</option>)}
              </optgroup>
              <optgroup label="The beta engine: slides of boxes, animations on their words">
                {LAB_BETA_PRESETS.map((p) => <option key={p.id} value={p.id}>{p.name}: {p.note}</option>)}
              </optgroup>
            </select>
          </label>
          {chapters.length > 0 && (
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">…or from a lecture&apos;s chapter</span>
              <select data-testid="lab-chapter" className="w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value=""
                onChange={(e) => { const [n, c] = e.target.value.split("|").map(Number); if (e.target.value) void act({ action: "add", lecture: n, chapter: c }); }}>
                <option value="">pick one…</option>
                {chapters.map(({ n, c }) => <option key={`${n}|${c.n}`} value={`${n}|${c.n}`}>Lecture {n}, chapter {c.n}: {c.title}</option>)}
              </select>
            </label>
          )}
          <button data-testid="lab-blank" className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => void act({ action: "add" })}>Blank</button>
        </div>
        {ready && !ready[settings.engine] && <p className="mt-2 text-amber-300">{engine.label} has no key here ({engine.key}): pick espeak-ng to try offline, for free.</p>}
      </section>

      {items.length > 0 && (
        <div className="flex flex-wrap gap-1" data-testid="lab-items">
          {items.map((i) => (
            <button key={i.id} data-testid={`lab-item-${i.id}`} onClick={() => setOpen(i.id)}
              className={`${btn} ${open === i.id ? "border-white/60 bg-neutral-800" : "border-neutral-700 hover:bg-neutral-800"}`}>
              {i.script.engine === "beta" && <span className="mr-1 rounded bg-violet-900/70 px-1 text-[10px] text-violet-100">beta</span>}
              {i.name}{i.result && <span className={`ml-1 ${TONE[i.result.status]}`}>· {i.result.status === "running" ? "trying" : i.result.status === "done" ? "played" : "failed"}</span>}
            </button>
          ))}
        </div>
      )}
      {!items.length && <p className="text-xs text-neutral-400">No experiment yet: pick a preset above.</p>}
      {item && <Experiment key={item.id} run={run} item={item} onCall={onCall} act={act} />}
      <Reference beta={item?.script.engine === "beta"} />
    </div>
  );
}

function Experiment({ run, item, onCall, act }: { run: Run; item: LabItem; onCall: (id: string) => void; act: Act }) {
  const [text, setText] = useState(JSON.stringify(item.script, null, 2));
  const [name, setName] = useState(item.name);
  let parsed: unknown;
  let parseError: string | null = null;
  try {
    parsed = text.trim() ? JSON.parse(unfence(text)) : undefined;
  } catch (error) {
    parseError = (error as Error).message;
  }
  const beats = (parsed as { chapter?: { beats?: unknown[] } } | undefined)?.chapter?.beats;
  const beta = (parsed as { engine?: string } | undefined)?.engine === "beta";
  const running = item.result?.status === "running";
  const changed = !parseError && JSON.stringify(parsed) !== JSON.stringify(item.script);
  const addBeat = (k: number) => {
    if (parseError || !parsed) return;
    const next = structuredClone(parsed) as { chapter: { beats: unknown[] } };
    if (beta) {
      const s = LAB_BETA_SNIPPETS[k];
      if (!s) return;
      next.chapter.beats.push(structuredClone(s.beat));
    } else {
      const s = LAB_SNIPPETS[k];
      if (!s) return;
      next.chapter.beats.push({ say: s.say, do: [s.do] });
    }
    setText(JSON.stringify(next, null, 2));
  };
  return (
    <section className="space-y-2 rounded border border-neutral-800 p-3 text-xs" data-testid="lab-experiment">
      <div className="flex flex-wrap items-center gap-2">
        <input data-testid="lab-name" className="w-72 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm" value={name} onChange={(e) => setName(e.target.value)}
          onBlur={() => name.trim() && name !== item.name && void act({ action: "save", id: item.id, name })} />
        {run.lectures.length > 1 && (
          <label className="flex items-center gap-1 text-neutral-400">figures of
            <select className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5" value={item.lecture ?? ""}
              onChange={(e) => void act({ action: "save", id: item.id, lecture: Number(e.target.value) })}>
              {run.lectures.map((l) => <option key={l.n} value={l.n}>lecture {l.n}</option>)}
            </select>
          </label>
        )}
        <span className={`ml-auto ${parseError ? "text-red-300" : "text-neutral-500"}`} data-testid="lab-json-state">
          {parseError ? `not JSON: ${parseError}` : Array.isArray(beats) ? `${beats.length} beat(s)${changed ? " · not saved" : ""}` : "no beats"}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button data-testid="lab-try" disabled={!!parseError || !parsed || running} className={`${btn} border-emerald-700 text-emerald-200 hover:bg-emerald-950`}
          onClick={() => { if (text.trim().startsWith("```")) setText(JSON.stringify(parsed, null, 2)); void act({ action: "try", id: item.id, script: parsed }); }}>
          {running ? `${item.result?.phase ?? "trying"}…` : "Speak and play"}</button>
        <button data-testid="lab-save" disabled={!changed} className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => void act({ action: "save", id: item.id, script: parsed })}>Save</button>
        <button disabled={!!parseError || !parsed} className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => setText(JSON.stringify(parsed, null, 2))}>Format</button>
        <button className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => void act({ action: "duplicate", id: item.id })}>Duplicate (to try a variant)</button>
        <select data-testid="lab-snippet" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value="" disabled={!!parseError || !parsed}
          onChange={(e) => addBeat(Number(e.target.value))}>
          <option value="">Add a beat with…</option>
          {(beta ? LAB_BETA_SNIPPETS : LAB_SNIPPETS).map((s, k) => <option key={k} value={k}>{s.op}</option>)}
        </select>
        <button disabled={running} className={`${btn} ml-auto border-red-900 text-red-300 hover:bg-red-950`}
          onClick={() => { if (confirm(`Delete "${item.name}"?`)) void act({ action: "remove", id: item.id }); }}>Delete</button>
      </div>
      {beta ? (
        <p className="text-violet-200/80" data-testid="lab-beta-note">
          <b>Beta engine</b> (<code>&quot;engine&quot;: &quot;beta&quot;</code>): each beat is <code>{"{say, layout?, elements?, animate?, clear?}"}</code>. A <code>layout</code> starts a
          slide (full, center, left-right, wide-left, wide-right, top-bottom, title-body, title-left-right, three-col, grid-2x2, focus-side); each element goes in
          a <code>slot</code> or its own <code>box</code> [x, y, w, h]; each <code>animate</code> step brings one in (<code>in</code>), points at it (<code>emphasis</code>),
          takes it away (<code>out</code>) or moves it, <code>on</code> the words that bring it. Its reference (engine/BETA_ENGINE.md) is under the editor.
        </p>
      ) : (
        <p className="text-neutral-500">
          The JSON is a chapter: <code>chapter.beats</code>, each <code>{"{say, do: [operations], paragraph?, pause?}"}</code>; <code>style</code>/<code>art</code> change
          the look, <code>region</code> (with <code>chapter.map: true</code>) draws a map. The reference is under the editor.
        </p>
      )}
      <textarea data-testid="lab-json" spellCheck={false} value={text} onChange={(e) => setText(e.target.value)}
        className="mono h-[26rem] w-full resize-y rounded border border-neutral-700 bg-neutral-950 p-2 text-[11px] leading-snug text-neutral-100" />
      {item.result && (
        <div className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-300">Spoken and played {item.result.at ? new Date(item.result.at).toLocaleTimeString() : ""}</p>
          <VoiceResult run={run} n={item.lecture ?? 1} chapter={0} v={item.result} onCall={onCall} tried />
        </div>
      )}
    </section>
  );
}

/** engine/BEAT_SCRIPT.md, every operation and its arguments, to read beside the editor. */
function Reference({ beta }: { beta: boolean }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState<Record<string, string>>({});
  const which = beta ? "beta" : "current";
  useEffect(() => {
    if (!open || text[which] !== undefined) return;
    void (async () => {
      const res = await fetch(`/api/runs/_/lab${beta ? "?engine=beta" : ""}`, { cache: "no-store" });
      const j = await res.json().catch(() => ({}));
      setText((t) => ({ ...t, [which]: j.reference ?? j.error ?? "the reference could not be read" }));
    })();
  }, [open, text, which, beta]);
  return (
    <details className="rounded border border-neutral-800 p-2 text-xs" data-testid="lab-reference" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-neutral-200">{beta ? "The beta engine's reference: layouts, elements, animations (engine/BETA_ENGINE.md)"
        : "The beat script's reference: every operation and its arguments (engine/BEAT_SCRIPT.md)"}</summary>
      <pre className="mono mt-2 max-h-[32rem] overflow-auto whitespace-pre-wrap text-[11px] leading-snug text-neutral-300">{text[which] ?? "reading…"}</pre>
    </details>
  );
}
