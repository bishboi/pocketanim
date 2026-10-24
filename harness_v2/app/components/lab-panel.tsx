"use client";

/**
 * The Lab: try animations with the voice, apart from the lectures (lib/lab.ts). Each experiment is a chapter's beat
 * script (engine/BEAT_SCRIPT.md), started from a preset (one per kind of animation), from a lecture's chapter, or
 * blank; edited here, and spoken and played: compiled, spoken with the Voice tab's voice, its animations timed to the
 * words, and played with its narration, with every line's word times and each animation's start shown under it.
 */

import { useEffect, useState } from "react";
import { LAB_MOTION_PRESETS, LAB_MOTION_SNIPPETS, LAB_PRESETS, LAB_SNIPPETS } from "@/lib/lab-presets";
import { MOTION_LOOKS } from "@/lib/prompts/scenes-motion";
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
  const settings = run.voice?.settings ?? { engine: ready?.gemini ? "gemini" : "espeak", pace: "teacher" };
  const engine = ENGINES.find((e) => e.id === settings.engine) ?? ENGINES[0];
  const item = items.find((i) => i.id === open);
  const chapters = run.lectures.flatMap((l) => (run.script?.lectures[l.n]?.chapters ?? []).map((c) => ({ n: l.n, c })));
  // A lecture's chapter may be added as it is, or on the motion engine (beta) in one of its looks.
  const [motionLook, setMotionLook] = useState("");
  const groups = [...new Set(LAB_MOTION_PRESETS.map((p) => p.group))];

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
            <select className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={settings.pace ?? "teacher"}
              onChange={(e) => void voiceAct({ action: "settings", pace: e.target.value })}>
              <option value="teacher">teacher</option><option value="natural">natural</option><option value="relaxed">relaxed</option><option value="slow">slow</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-neutral-400">New experiment from a preset</span>
            <select data-testid="lab-preset" className="w-64 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value=""
              onChange={(e) => { if (e.target.value) void act({ action: "add", preset: e.target.value }); }}>
              <option value="">pick one…</option>
              <optgroup label="Current engine">
                {LAB_PRESETS.map((p) => <option key={p.id} value={p.id}>{p.name}: {p.note}</option>)}
              </optgroup>
              {groups.map((g) => (
                <optgroup key={g} label={`Motion engine (beta): ${g}`}>
                  {LAB_MOTION_PRESETS.filter((p) => p.group === g).map((p) => <option key={p.id} value={p.id}>{p.name}: {p.note}</option>)}
                </optgroup>
              ))}
            </select>
          </label>
          {chapters.length > 0 && (
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">…or from a lecture&apos;s chapter</span>
              <select data-testid="lab-chapter" className="w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value=""
                onChange={(e) => { const [n, c] = e.target.value.split("|").map(Number);
                  if (e.target.value) void act({ action: "add", lecture: n, chapter: c, ...(motionLook ? { motion: true, look: motionLook === "own" ? undefined : motionLook } : {}) }); }}>
                <option value="">pick one…</option>
                {chapters.map(({ n, c }) => <option key={`${n}|${c.n}`} value={`${n}|${c.n}`}>Lecture {n}, chapter {c.n}: {c.title}</option>)}
              </select>
            </label>
          )}
          {chapters.length > 0 && (
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">…drawn by</span>
              <select data-testid="lab-chapter-engine" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={motionLook}
                onChange={(e) => setMotionLook(e.target.value)}>
                <option value="">the current engine</option>
                <option value="own">the motion engine (beta), its own style</option>
                {MOTION_LOOKS.map((l) => <option key={l} value={l}>the motion engine (beta), look: {l}</option>)}
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
              {i.name}{i.result && <span className={`ml-1 ${TONE[i.result.status]}`}>· {i.result.status === "running" ? "trying" : i.result.status === "done" ? "played" : "failed"}</span>}
            </button>
          ))}
        </div>
      )}
      {!items.length && <p className="text-xs text-neutral-400">No experiment yet: pick a preset above.</p>}
      {item && <Experiment key={item.id} run={run} item={item} onCall={onCall} act={act} />}
      <Reference motion={(item?.script as { engine?: string } | undefined)?.engine === "motion"} />
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
  const running = item.result?.status === "running";
  const changed = !parseError && JSON.stringify(parsed) !== JSON.stringify(item.script);
  const motion = (parsed as { engine?: string } | undefined)?.engine === "motion";
  const snippets = motion ? [...LAB_MOTION_SNIPPETS, ...LAB_SNIPPETS] : LAB_SNIPPETS;
  const addBeat = (k: number) => {
    const s = snippets[k];
    if (!s || parseError || !parsed) return;
    const next = structuredClone(parsed) as { chapter: { beats: unknown[] } };
    next.chapter.beats.push({ say: s.say, do: [s.do] });
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
          {snippets.map((s, k) => <option key={k} value={k}>{s.op}</option>)}
        </select>
        <button disabled={running} className={`${btn} ml-auto border-red-900 text-red-300 hover:bg-red-950`}
          onClick={() => { if (confirm(`Delete "${item.name}"?`)) void act({ action: "remove", id: item.id }); }}>Delete</button>
      </div>
      {motion && (
        <p className="text-violet-300" data-testid="lab-motion-note">
          Motion engine (beta): <code>look</code>, <code>energy</code>, <code>transition</code> and <code>timeline</code> set how it looks and moves; its
          templates (<code>counter</code>, <code>chart</code>, <code>units</code>, <code>cards</code>, <code>stamp</code>…) take <code>on</code>, the words they land on.
        </p>
      )}
      <p className="text-neutral-500">
        The JSON is a chapter: <code>chapter.beats</code>, each <code>{"{say, do: [operations], paragraph?, pause?}"}</code>; <code>style</code>/<code>art</code> change
        the look, <code>region</code> (with <code>chapter.map: true</code>) draws a map. The reference is under the editor.
      </p>
      <textarea data-testid="lab-json" spellCheck={false} value={text} onChange={(e) => setText(e.target.value)}
        className="mono h-[26rem] w-full resize-y rounded border border-neutral-700 bg-neutral-950 p-2 text-[11px] leading-snug text-neutral-100" />
      {item.result && (
        <div className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-300">Spoken and played {item.result.at ? new Date(item.result.at).toLocaleTimeString() : ""}</p>
          <VoiceResult run={run} n={item.lecture ?? 1} chapter={0} v={item.result} onCall={onCall} tried />
        </div>
      )}
      {!!item.result?.pictures?.length && <MadePictures pictures={item.result.pictures} />}
    </section>
  );
}

type Made = NonNullable<NonNullable<LabItem["result"]>["pictures"]>[number];

/** The AI pictures the experiment's compile showed, as the image model made them: what each shows, how it is used, its
 * beat and the prompt it was sent; a flow drawn as one picture with a box round each step where it was found in it. */
function MadePictures({ pictures }: { pictures: Made[] }) {
  return (
    <div className="space-y-1" data-testid="lab-pictures">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-sky-300">Pictures the image model made ({pictures.length})</p>
      <div className="grid gap-3 md:grid-cols-2">
        {pictures.map((p) => <MadePicture key={p.url} p={p} />)}
      </div>
    </div>
  );
}

function MadePicture({ p }: { p: Made }) {
  const [size, setSize] = useState<[number, number] | null>(null);
  return (
    <figure className="space-y-1 rounded border border-neutral-800 p-2" data-testid="lab-picture">
      <div className="relative rounded" style={{ background: "repeating-conic-gradient(#2a2a2a 0% 25%, #1f1f1f 0% 50%) 50% / 16px 16px" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={p.url} alt={p.what} className="block w-full" onLoad={(e) => setSize([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])} />
        {size && p.parts?.map(([label, x0, y0, x1, y1], k) => x0 === undefined || y0 === undefined || x1 === undefined || y1 === undefined ? null : (
          <div key={k} className="absolute border-2 border-amber-400" title={label}
            style={{ left: `${(x0 / size[0]) * 100}%`, top: `${(y0 / size[1]) * 100}%`, width: `${((x1 - x0) / size[0]) * 100}%`, height: `${((y1 - y0) / size[1]) * 100}%` }}>
            <span className="absolute -top-4 left-0 rounded bg-amber-400 px-1 text-[10px] font-semibold text-black">{k + 1}. {label}</span>
          </div>
        ))}
      </div>
      <figcaption className="space-y-0.5">
        <p className="text-neutral-100">{p.what || "(no description)"}{p.beat ? <span className="text-neutral-500"> · beat {p.beat}</span> : null}</p>
        {p.role && <p className="text-neutral-400">{p.role}</p>}
        {p.prompt && (
          <details>
            <summary className="cursor-pointer text-neutral-400">The prompt it was sent{p.model ? ` (${p.model})` : ""}</summary>
            <p className="mono mt-1 whitespace-pre-wrap text-[11px] text-neutral-300">{p.prompt}</p>
          </details>
        )}
      </figcaption>
    </figure>
  );
}

/** engine/BEAT_SCRIPT.md (or, for a motion experiment, engine/MOTION_ENGINE.md), to read beside the editor. */
function Reference({ motion }: { motion: boolean }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  useEffect(() => setText(null), [motion]);
  useEffect(() => {
    if (!open || text !== null) return;
    void (async () => {
      const res = await fetch(`/api/runs/_/lab${motion ? "?engine=motion" : ""}`, { cache: "no-store" });
      const j = await res.json().catch(() => ({}));
      setText(j.reference ?? j.error ?? "the reference could not be read");
    })();
  }, [open, text, motion]);
  return (
    <details className="rounded border border-neutral-800 p-2 text-xs" data-testid="lab-reference" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-neutral-200">{motion
        ? "The motion engine's reference (beta): its templates, looks, moments, transitions and timeline styles (engine/MOTION_ENGINE.md)"
        : "The beat script's reference: every operation and its arguments (engine/BEAT_SCRIPT.md)"}</summary>
      <pre className="mono mt-2 max-h-[32rem] overflow-auto whitespace-pre-wrap text-[11px] leading-snug text-neutral-300">{text ?? "reading…"}</pre>
    </details>
  );
}
