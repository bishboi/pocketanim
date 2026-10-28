"use client";

/**
 * The Lab: try the current engine's primitives with the voice, apart from the lectures (lib/lab.ts). Each experiment
 * is a chapter's beat script (engine/BEAT_SCRIPT.md), started from a preset, from every primitive at once
 * (lib/primitives.ts), from a lecture's chapter, or blank; edited here in a form (each beat and its operations, the
 * fields of each primitive) or as JSON; checked (compiled only: what the compiler refuses or mends), or spoken and
 * played: compiled, spoken with the Voice tab's voice, its animations timed to the words, played with its narration.
 */

import { useEffect, useRef, useState } from "react";
import { LAB_MOTION_PRESETS, LAB_PRESETS } from "@/lib/lab-presets";
import { PRIMITIVES, PRIMITIVE_BY_OP, type Field } from "@/lib/primitives";
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
  const known = useRef<Set<string> | null>(null);
  // A new experiment (one not seen before: added, or a copy) is opened as it arrives.
  const ids = items.map((i) => i.id).join(",");
  useEffect(() => {
    const now = items.map((i) => i.id);
    const fresh = known.current ? now.filter((id) => !known.current!.has(id)) : [];
    if (fresh.length) setOpen(fresh[fresh.length - 1]);
    else if (!open || !now.includes(open)) setOpen(now[0]);
    known.current = new Set(now);
  }, [ids]); // eslint-disable-line react-hooks/exhaustive-deps
  const settings = run.voice?.settings ?? { engine: ready?.gemini ? "gemini" : "espeak", pace: "teacher" };
  const engine = ENGINES.find((e) => e.id === settings.engine) ?? ENGINES[0];
  const item = items.find((i) => i.id === open);
  const chapters = run.lectures.flatMap((l) => (run.script?.lectures[l.n]?.chapters ?? []).map((c) => ({ n: l.n, c })));

  return (
    <div className="space-y-3" data-testid="lab">
      <section className="rounded border border-neutral-800 p-3 text-xs">
        <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-sm font-semibold text-neutral-100">Lab</h3>
          <span className="text-neutral-400">
            Try the engine&apos;s primitives, templates and looks with the voice, apart from the lectures: start from a preset, every primitive, a lecture&apos;s
            chapter, or blank; change it in the form or as JSON; <b>Check</b> compiles it only; <b>Speak and play</b> compiles it, speaks it,
            times each animation to its words and plays it.
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
              {LAB_PRESETS.map((p) => <option key={p.id} value={p.id}>{p.name}: {p.note}</option>)}
              {[...new Set(LAB_MOTION_PRESETS.map((p) => p.group))].map((g) => (
                <optgroup key={g} label={g}>
                  {LAB_MOTION_PRESETS.filter((p) => p.group === g).map((p) => <option key={p.id} value={p.id}>{p.name}: {p.note}</option>)}
                </optgroup>))}
            </select>
          </label>
          {chapters.length > 0 && (
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">…or from a lecture&apos;s chapter</span>
              <select data-testid="lab-chapter" className="w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value=""
                onChange={(e) => { const [n, c] = e.target.value.split("|").map(Number);
                  if (e.target.value) void act({ action: "add", lecture: n, chapter: c }); }}>
                <option value="">pick one…</option>
                {chapters.map(({ n, c }) => <option key={`${n}|${c.n}`} value={`${n}|${c.n}`}>Lecture {n}, chapter {c.n}: {c.title}</option>)}
              </select>
            </label>
          )}
          <button data-testid="lab-every" className={`${btn} border-sky-700 text-sky-200 hover:bg-sky-950`} title={`One beat for each of the ${PRIMITIVES.length - 1} primitives (a Manim figure aside: the Manim agent writes it), on India's map`}
            onClick={() => void act({ action: "add", every: true })}>Every primitive</button>
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
      <Reference />
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
  const [mode, setMode] = useState<"form" | "json">("form");
  const addBeat = (op: string) => {
    const p = PRIMITIVE_BY_OP.get(op);
    if (!p || parseError || !parsed) return;
    const next = structuredClone(parsed) as { chapter: { beats: unknown[] } };
    next.chapter.beats.push({ say: p.say, do: [structuredClone(p.example)] });
    setText(JSON.stringify(next, null, 2));
  };
  const checked = item.checked;
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
        <button data-testid="lab-check" disabled={!!parseError || !parsed || running} className={`${btn} border-sky-700 text-sky-200 hover:bg-sky-950`}
          title="Compile it only (no voice, no render): what the compiler refuses or mends"
          onClick={() => void act({ action: "check", id: item.id, script: parsed })}>Check</button>
        <button data-testid="lab-save" disabled={!changed} className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => void act({ action: "save", id: item.id, script: parsed })}>Save</button>
        <button disabled={!!parseError || !parsed} className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => setText(JSON.stringify(parsed, null, 2))}>Format</button>
        <button className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => void act({ action: "duplicate", id: item.id })}>Duplicate (to try a variant)</button>
        <select data-testid="lab-snippet" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value="" disabled={!!parseError || !parsed}
          onChange={(e) => addBeat(e.target.value)}>
          <option value="">Add a beat with…</option>
          {PRIMITIVES.map((p) => <option key={p.op} value={p.op}>{p.op}: {p.what.slice(0, 60)}</option>)}
        </select>
        <span className="flex overflow-hidden rounded border border-neutral-700" data-testid="lab-mode">
          {(["form", "json"] as const).map((m) => (
            <button key={m} className={`px-2 py-1 ${mode === m ? "bg-neutral-700 text-white" : "text-neutral-300 hover:bg-neutral-800"}`} onClick={() => setMode(m)}>
              {m === "form" ? "Form" : "JSON"}</button>
          ))}
        </span>
        <button disabled={running} className={`${btn} ml-auto border-red-900 text-red-300 hover:bg-red-950`}
          onClick={() => { if (confirm(`Delete "${item.name}"?`)) void act({ action: "remove", id: item.id }); }}>Delete</button>
      </div>
      {checked && (
        <div className={`rounded border p-2 ${checked.ok ? "border-emerald-900 text-emerald-200" : "border-red-900 text-red-200"}`} data-testid="lab-checked">
          <p className="font-semibold">{checked.ok ? "Compiles" : "Refused"} · {new Date(checked.at).toLocaleTimeString()}
            {checked.warnings.length ? <span className="font-normal text-amber-300"> · {checked.warnings.length} note(s)</span> : null}</p>
          {checked.errors.map((e, k) => <p key={`e${k}`} className="text-red-300">✗ {e}</p>)}
          {checked.warnings.slice(0, 12).map((w, k) => <p key={`w${k}`} className="text-amber-200/90">• {w}</p>)}
        </div>
      )}
      {mode === "form" && parsed && !parseError
        ? <FormEditor value={parsed as LabScript} onChange={(v) => setText(JSON.stringify(v, null, 2))} />
        : (
          <>
            <p className="text-neutral-500">
              The JSON is a chapter: <code>chapter.beats</code>, each <code>{"{say, do: [operations], paragraph?, pause?}"}</code>; <code>style</code>/<code>art</code> change
              the look, <code>region</code> (with <code>chapter.map: true</code>) draws a map. The reference is under the editor.
            </p>
            <textarea data-testid="lab-json" spellCheck={false} value={text} onChange={(e) => setText(e.target.value)}
              className="mono h-[26rem] w-full resize-y rounded border border-neutral-700 bg-neutral-950 p-2 text-[11px] leading-snug text-neutral-100" />
          </>
        )}
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

/** engine/BEAT_SCRIPT.md, to read beside the editor. */
function Reference() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (!open || text !== null) return;
    void (async () => {
      const res = await fetch("/api/runs/_/lab", { cache: "no-store" });
      const j = await res.json().catch(() => ({}));
      setText(j.reference ?? j.error ?? "the reference could not be read");
    })();
  }, [open, text]);
  return (
    <details className="rounded border border-neutral-800 p-2 text-xs" data-testid="lab-reference" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-neutral-200">The beat script&apos;s reference: every operation and its arguments (engine/BEAT_SCRIPT.md)</summary>
      <pre className="mono mt-2 max-h-[32rem] overflow-auto whitespace-pre-wrap text-[11px] leading-snug text-neutral-300">{text ?? "reading…"}</pre>
    </details>
  );
}

type LabOp = Record<string, unknown>;
type LabBeat = { say: string; do: LabOp[]; paragraph?: boolean; pause?: number };
type LabScript = { chapter: { title: string; beats: LabBeat[] } & Record<string, unknown> } & Record<string, unknown>;
const input = "rounded border border-neutral-700 bg-neutral-950 px-1.5 py-0.5 text-[11px] text-neutral-100";
/** What is up by the time a beat plays, for the knobs' choices: the labelled pictures' labels, the diagrams and their
 * nodes, every name that can be pointed at. */
type Known = { labels: string[]; diagrams: Map<string, string[]>; names: string[] };

function knownBy(beats: LabBeat[], upTo: number): Known {
  const labels = new Set<string>();
  const diagrams = new Map<string, string[]>();
  const names = new Set<string>();
  for (const b of beats.slice(0, upTo + 1)) {
    for (const op of Array.isArray(b.do) ? b.do : []) {
      if (Array.isArray(op.labels)) for (const l of op.labels) {
        const name = typeof l === "string" ? l : l && typeof l === "object" ? String((l as LabOp).name ?? "") : "";
        if (name) { labels.add(name); names.add(name); }
      }
      if (op.op === "diagram" && Array.isArray(op.nodes)) {
        const nodes = op.nodes.filter((n): n is LabOp => !!n && typeof n === "object").map((n) => String(n.id));
        diagrams.set(String(op.id ?? ""), nodes);
        for (const n of op.nodes as LabOp[]) if (n && typeof n === "object") names.add(String(n.label ?? n.id));
      }
      for (const k of ["title", "label", "term", "name", "place"]) if (typeof op[k] === "string" && op[k]) names.add(String(op[k]));
    }
  }
  return { labels: [...labels], diagrams, names: [...names] };
}

/** The experiment as a form: its title, each beat (its words, paragraph, pause) and each of its operations, with the
 * fields of its primitive (lib/primitives.ts). Every change is written back to the JSON. */
function FormEditor({ value, onChange }: { value: LabScript; onChange: (v: LabScript) => void }) {
  const beats = Array.isArray(value.chapter?.beats) ? value.chapter.beats : [];
  const set = (f: (v: LabScript) => void) => {
    const next = structuredClone(value);
    next.chapter.beats ??= [];
    f(next);
    onChange(next);
  };
  const move = <T,>(list: T[], i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
  };
  return (
    <div className="space-y-2" data-testid="lab-form">
      <label className="flex items-center gap-2 text-neutral-400">Chapter title
        <input className={`${input} w-80`} value={String(value.chapter?.title ?? "")} onChange={(e) => set((v) => { v.chapter.title = e.target.value; })} />
      </label>
      {beats.map((b, i) => (
        <div key={i} className="space-y-1 rounded border border-neutral-800 bg-neutral-900/40 p-2" data-testid="lab-form-beat">
          <div className="flex items-center gap-2">
            <span className="text-neutral-500">#{i + 1}</span>
            <textarea className={`${input} h-10 flex-1`} value={b.say ?? ""} placeholder="the words said" onChange={(e) => set((v) => { v.chapter.beats[i].say = e.target.value; })} />
            <label className="flex items-center gap-1 text-neutral-400"><input type="checkbox" checked={!!b.paragraph}
              onChange={(e) => set((v) => { if (e.target.checked) v.chapter.beats[i].paragraph = true; else delete v.chapter.beats[i].paragraph; })} />paragraph</label>
            <label className="flex items-center gap-1 text-neutral-400" title="the quiet after the line, in seconds">pause
              <input type="range" step="0.25" min="0" max="2" className="w-20 accent-sky-500" value={b.pause ?? 0} data-testid="lab-knob-pause"
                onChange={(e) => set((v) => { if (Number(e.target.value)) v.chapter.beats[i].pause = Number(e.target.value); else delete v.chapter.beats[i].pause; })} />
              <span className="mono w-8 text-neutral-300">{(b.pause ?? 0).toFixed(2)}</span></label>
            <button className="text-neutral-400 hover:text-white" title="up" onClick={() => set((v) => move(v.chapter.beats, i, -1))}>↑</button>
            <button className="text-neutral-400 hover:text-white" title="down" onClick={() => set((v) => move(v.chapter.beats, i, 1))}>↓</button>
            <button className="text-red-300 hover:text-red-200" title="remove the beat" onClick={() => set((v) => { v.chapter.beats.splice(i, 1); })}>✕</button>
          </div>
          {(Array.isArray(b.do) ? b.do : []).map((op, k) => (
            <OpForm key={k} op={op} words={String(b.say ?? "").split(/\s+/).filter(Boolean)} known={knownBy(beats, i)}
              onChange={(o) => set((v) => { v.chapter.beats[i].do[k] = o; })}
              onMove={(d) => set((v) => move(v.chapter.beats[i].do, k, d))} onRemove={() => set((v) => { v.chapter.beats[i].do.splice(k, 1); })} />
          ))}
          <select className={input} value="" onChange={(e) => { const p = PRIMITIVE_BY_OP.get(e.target.value);
            if (p) set((v) => { (v.chapter.beats[i].do ??= []).push(structuredClone(p.example)); }); }}>
            <option value="">+ an operation…</option>
            {PRIMITIVES.map((p) => <option key={p.op} value={p.op}>{p.op}</option>)}
          </select>
        </div>
      ))}
      <button className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => set((v) => { v.chapter.beats.push({ say: "", do: [] }); })}>+ a beat</button>
    </div>
  );
}

/** One operation: its primitive (changed: started again from its example), each of its fields, and its anchor. */
function OpForm({ op, words, known, onChange, onMove, onRemove }: { op: LabOp; words: string[]; known: Known; onChange: (o: LabOp) => void;
  onMove: (d: number) => void; onRemove: () => void }) {
  const p = PRIMITIVE_BY_OP.get(String(op.op));
  // A labelled picture's labels are set in its own knobs (note, held back), not as raw fields.
  const labelled = Array.isArray(op.labels) && op.labels.length > 0;
  const knob = new Set(labelled ? ["hold", "notes"] : []);
  // A field that names what is up: a choice of what is up by this beat (or any words).
  const choices = (key: string): string[] | undefined => key === "part" ? known.labels : key === "diagram" ? [...known.diagrams.keys()]
    : key === "node" ? known.diagrams.get(String(op.diagram ?? "")) ?? [] : key === "target" ? known.names : undefined;
  const field = (f: Field) => {
    const v = op[f.key];
    const put = (x: unknown) => {
      const next = { ...op };
      if (x === undefined || x === "" || (Array.isArray(x) && !x.length)) delete next[f.key];
      else next[f.key] = x;
      onChange(next);
    };
    const label = <span className={`w-20 shrink-0 ${f.required ? "text-neutral-200" : "text-neutral-400"}`} title={f.hint}>{f.key}{f.required ? "*" : ""}</span>;
    if (f.kind === "bool") return <label key={f.key} className="flex items-center gap-1">{label}<input type="checkbox" checked={v === true} onChange={(e) => put(e.target.checked || undefined)} /></label>;
    if (f.kind === "select") return <label key={f.key} className="flex items-center gap-1">{label}
      <select className={input} value={String(v ?? "")} onChange={(e) => put(e.target.value || undefined)}>{(f.options ?? []).map((o) => <option key={o} value={o}>{o || "—"}</option>)}</select></label>;
    if (f.kind === "number") return <label key={f.key} className="flex items-center gap-1">{label}
      <input type="number" className={`${input} w-24`} value={v === undefined ? "" : String(v)} onChange={(e) => put(e.target.value === "" ? undefined : Number(e.target.value))} /></label>;
    if (f.kind === "texts") return <label key={f.key} className="flex items-start gap-1">{label}
      <textarea className={`${input} h-12 flex-1`} placeholder="one a line" value={Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join("\n") : ""}
        onChange={(e) => put(e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} /></label>;
    if (f.kind === "json") return <JsonField key={f.key} label={label} value={v} hint={f.hint} onChange={put} />;
    const pick = choices(f.key);
    if (pick && f.kind === "text") return <label key={f.key} className="flex items-center gap-1">{label}
      <input className={`${input} flex-1`} list={`lab-pick-${f.key}`} placeholder={pick.length ? "pick or type" : "nothing up by this beat"} value={v === undefined ? "" : String(v)}
        onChange={(e) => put(e.target.value)} data-testid={`lab-knob-${f.key}`} />
      <datalist id={`lab-pick-${f.key}`}>{pick.map((x) => <option key={x} value={x} />)}</datalist></label>;
    if (f.kind === "long") return <label key={f.key} className="flex items-start gap-1">{label}
      <textarea className={`${input} h-12 flex-1`} placeholder={f.hint} value={String(v ?? "")} onChange={(e) => put(e.target.value)} /></label>;
    return <label key={f.key} className="flex items-center gap-1">{label}
      <input className={`${input} flex-1`} placeholder={f.hint} value={v === undefined ? "" : String(v)} onChange={(e) => put(e.target.value)} /></label>;
  };
  const known2 = new Set(["op", "on", ...(p?.fields.map((f) => f.key) ?? [])]);
  const extra = Object.keys(op).filter((k) => !known2.has(k));
  return (
    <div className="ml-6 space-y-1 rounded border border-neutral-800 p-1.5" data-testid="lab-form-op">
      <div className="flex items-center gap-2">
        <select className={input} value={String(op.op ?? "")} onChange={(e) => { const q = PRIMITIVE_BY_OP.get(e.target.value); if (q) onChange(structuredClone(q.example)); }}>
          {!p && <option value={String(op.op ?? "")}>{String(op.op ?? "?")}</option>}
          {PRIMITIVES.map((x) => <option key={x.op} value={x.op}>{x.op}</option>)}
        </select>
        <span className="min-w-0 flex-1 truncate text-neutral-500" title={p?.what}>{p?.what ?? "not one of the primitives: its JSON below"}</span>
        <label className="flex items-center gap-1 text-neutral-400" title="the word of the line it lands on">on
          <select className={`${input} max-w-40`} value={String(op.on ?? "")} data-testid="lab-knob-on"
            onChange={(e) => { const next = { ...op }; if (e.target.value) next.on = e.target.value; else delete next.on; onChange(next); }}>
            <option value="">— (as the line begins)</option>
            <option value="start">start</option>
            {words.map((w, k) => <option key={k} value={`w${k}`}>w{k} · {w}</option>)}
            {typeof op.on === "string" && op.on && op.on !== "start" && !/^w\d+$/.test(op.on) && <option value={op.on}>{op.on}</option>}
          </select></label>
        <button className="text-neutral-400 hover:text-white" onClick={() => onMove(-1)}>↑</button>
        <button className="text-neutral-400 hover:text-white" onClick={() => onMove(1)}>↓</button>
        <button className="text-red-300 hover:text-red-200" onClick={onRemove}>✕</button>
      </div>
      <div className="grid gap-1 md:grid-cols-2">{p?.fields.filter((f) => !knob.has(f.key)).map(field)}</div>
      {labelled && <LabelKnobs op={op} onChange={onChange} />}
      {(extra.length > 0 || !p) && (
        <JsonField label={<span className="w-20 shrink-0 text-neutral-400">{p ? "more" : "the op"}</span>}
          value={Object.fromEntries((p ? extra : Object.keys(op).filter((k) => k !== "op")).map((k) => [k, op[k]]))}
          onChange={(x) => onChange({ op: op.op, ...(p ? Object.fromEntries([...known2].filter((k) => k !== "op" && op[k] !== undefined).map((k) => [k, op[k]])) : {}),
            ...(x && typeof x === "object" ? x as LabOp : {}) })} />
      )}
    </div>
  );
}

/** A labelled picture's labels, one row each: a short note under its name, and whether it is held back (brought on
 * later by a `label` operation). Written to the picture's `notes` and `hold`. */
function LabelKnobs({ op, onChange }: { op: LabOp; onChange: (o: LabOp) => void }) {
  const names = (op.labels as unknown[]).map((l) => (typeof l === "string" ? l : l && typeof l === "object" ? String((l as LabOp).name ?? "") : "")).filter(Boolean);
  const notes = (op.notes && typeof op.notes === "object" ? op.notes : {}) as Record<string, string>;
  const hold = Array.isArray(op.hold) ? op.hold.map(String) : [];
  const write = (key: "notes", name: string, value: string) => {
    const next = { ...op, [key]: { ...notes } } as LabOp;
    const map = next[key] as Record<string, string>;
    if (value) map[name] = value; else delete map[name];
    if (!Object.keys(map).length) delete next[key];
    onChange(next);
  };
  const held = (name: string, on: boolean) => {
    const list = on ? [...new Set([...hold, name])] : hold.filter((x) => x !== name);
    const next = { ...op, hold: list };
    if (!list.length) delete (next as LabOp).hold;
    onChange(next);
  };
  return (
    <table className="w-full text-[11px]" data-testid="lab-label-knobs">
      <thead><tr className="text-left text-neutral-500"><th className="font-normal">label</th><th className="font-normal">note</th>
        <th className="font-normal" title="held back: brought on later by a label operation">later</th></tr></thead>
      <tbody>
        {names.map((n) => (
          <tr key={n}>
            <td className="pr-2 text-neutral-200">{n}</td>
            <td className="pr-2"><input className={`${input} w-full`} maxLength={60} placeholder="a short line under it" value={notes[n] ?? ""}
              onChange={(e) => write("notes", n, e.target.value)} data-testid="lab-knob-note" /></td>
            <td><input type="checkbox" checked={hold.includes(n)} onChange={(e) => held(n, e.target.checked)} data-testid="lab-knob-hold" /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** A field written as JSON (a list of nodes, of events, of columns): applied when it parses. */
function JsonField({ label, value, hint, onChange }: { label: React.ReactNode; value: unknown; hint?: string; onChange: (v: unknown) => void }) {
  const [text, setText] = useState(value === undefined ? "" : JSON.stringify(value));
  const [bad, setBad] = useState(false);
  return (
    <label className="flex items-start gap-1 md:col-span-2">{label}
      <textarea className={`${input} mono h-14 flex-1 ${bad ? "border-red-700" : ""}`} placeholder={hint} value={text}
        onChange={(e) => { setText(e.target.value); try { onChange(e.target.value.trim() ? JSON.parse(e.target.value) : undefined); setBad(false); } catch { setBad(true); } }} />
    </label>
  );
}
