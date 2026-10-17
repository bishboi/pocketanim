"use client";

/**
 * The voice: each chapter whose scenes are built, spoken, its animations timed to the words, and played with its
 * narration (lib/voice.ts).
 *
 *   - The voice: the engine (Gemini, Chirp, ElevenLabs, or espeak offline), the speaker, the pace, the timing model.
 *   - One lecture: its chapters, each with its scenes (built or not), its voice (spoken, behind its scenes, failed),
 *     its length, lines and cost; speak one, or every chapter with scenes not spoken yet.
 *   - One chapter: the player with the narration (the whole chapter, or a beat of it), every line spoken (its audio,
 *     its length, when each word is said and where those times came from) and each beat's animations as timed to
 *     the words (on the line's timeline), with the calls made.
 */

import { useEffect, useState } from "react";
import type { ChapterVoice, Run, VoiceCue, VoiceLine } from "@/lib/types";
import { ENGINES, scenesKey } from "@/lib/voice-engines";
import { money } from "./call-inspector";
import { IRPlayer } from "./player";

type Act = (body: Record<string, unknown>) => Promise<boolean>;
const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";
/** A length in seconds, as said (1 min 58 s, 9.0 s). */
const seconds = (s?: number) => s === undefined ? "" : s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${s.toFixed(1)} s`;
const TONE = { running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;

/** The chapters of a lecture with their scenes: how many beats have visuals. */
function chapterRows(run: Run, n: number) {
  const script = run.script?.lectures[n];
  const sl = run.scenes?.lectures[n];
  return (script?.chapters ?? []).map((c) => ({ c, built: c.beats.filter((b) => sl?.beats[b.n]?.ops?.length).length, total: c.beats.length }));
}

function length(v?: ChapterVoice): number | undefined {
  return v?.frames && v.fps ? v.frames / v.fps : undefined;
}

export function VoicePanel({ run, ready, timingModel, onCall, act }: {
  run: Run; ready?: Record<string, boolean>; timingModel: string; onCall: (id: string) => void; act: Act;
}) {
  const settings = run.voice?.settings ?? { engine: ready?.gemini ? "gemini" : "espeak", pace: "natural" };
  const withScenes = run.lectures.filter((l) => chapterRows(run, l.n).some((r) => r.built === r.total && r.total));
  const [lecture, setLecture] = useState<number | undefined>(withScenes[0]?.n);
  const [chapter, setChapter] = useState<number | undefined>();
  const [speaker, setSpeaker] = useState(settings.voice ?? "");
  const [timing, setTiming] = useState(settings.timingModel ?? "");
  useEffect(() => { setSpeaker(run.voice?.settings.voice ?? ""); setTiming(run.voice?.settings.timingModel ?? ""); }, [run.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (lecture === undefined && withScenes.length) setLecture(withScenes[0].n); }, [withScenes.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const engine = ENGINES.find((e) => e.id === settings.engine) ?? ENGINES[0];
  const cost = run.calls.filter((c) => c.step === "voice").reduce((k, c) => k + c.cost, 0);
  const spoken = Object.values(run.voice?.lectures ?? {}).reduce((k, l) => k + Object.values(l).filter((c) => c.status === "done").length, 0);

  if (!withScenes.length) return <p className="text-sm text-neutral-400">No chapter has its scenes built yet: build them on the Scenes tab first. The voice speaks the chapters whose every beat has its visuals.</p>;
  const rows = lecture !== undefined ? chapterRows(run, lecture) : [];
  const lv = lecture !== undefined ? run.voice?.lectures[lecture] ?? {} : {};
  const open = chapter !== undefined ? lv[chapter] : undefined;
  const behind = (c: number) => lv[c]?.status === "done" && lv[c]?.scenesKey !== scenesKey(run, lecture!, c);

  return (
    <div className="space-y-3" data-testid="voice">
      <section className="rounded border border-neutral-800 p-3 text-xs">
        <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-sm font-semibold text-neutral-100">Voice</h3>
          <span className="text-neutral-400">Each chapter with its scenes built is spoken, its animations timed to the words, and played with its narration.</span>
          <span className="ml-auto text-neutral-400">{spoken} chapter(s) spoken · {money(cost)}</span>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-neutral-400">Voice engine</span>
            <select data-testid="voice-engine" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={settings.engine}
              onChange={(e) => { setSpeaker(""); void act({ action: "settings", engine: e.target.value, voice: "" }); }}>
              {ENGINES.map((e) => <option key={e.id} value={e.id}>{e.label}{ready && !ready[e.id] ? " (no key)" : ""}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-neutral-400">Speaker</span>
            <input data-testid="voice-speaker" list="voice-speakers" className="w-36 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={speaker}
              placeholder="the engine's default" onChange={(e) => setSpeaker(e.target.value)}
              onBlur={() => speaker !== (settings.voice ?? "") && void act({ action: "settings", voice: speaker })} />
            <datalist id="voice-speakers">{engine.voices.map((v) => <option key={v} value={v} />)}</datalist>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-neutral-400">Pace</span>
            <select className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={settings.pace ?? "natural"}
              onChange={(e) => void act({ action: "settings", pace: e.target.value })}>
              <option value="natural">natural (lines run on)</option>
              <option value="relaxed">relaxed</option>
              <option value="slow">slow (long holds)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-neutral-400">Timing model (animations to words)</span>
            <input className="w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={timing} placeholder={timingModel}
              onChange={(e) => setTiming(e.target.value)} onBlur={() => timing !== (settings.timingModel ?? "") && void act({ action: "settings", timingModel: timing })} />
          </label>
        </div>
        {ready && !ready[settings.engine] && (
          <p className="mt-2 text-amber-300">{engine.label} has no key here ({engine.key}): speaking will fail. Pick espeak-ng to try the step offline, for free.</p>
        )}
        {settings.engine === "espeak" && <p className="mt-2 text-neutral-500">espeak-ng is a robotic offline voice: right for trying the timing, not for a lecture to watch.</p>}
        <p className="mt-2 text-neutral-500">
          The lines are kept by voice and words: a line said again (in another chapter, a rebuild, another run) is not spoken or paid for again.
          A changed speaker, pace or engine is a new voice: speak the chapters again.
        </p>
      </section>

      <div className="flex flex-wrap gap-1">
        {withScenes.map((l) => {
          const done = Object.values(run.voice?.lectures[l.n] ?? {}).filter((c) => c.status === "done").length;
          return (
            <button key={l.n} onClick={() => { setLecture(l.n); setChapter(undefined); }}
              className={`${btn} ${lecture === l.n ? "border-white/60 bg-neutral-800" : "border-neutral-700 hover:bg-neutral-800"}`}>
              Lecture {l.n} <span className="text-neutral-500">{done ? `· ${done} spoken` : ""}</span>
            </button>
          );
        })}
      </div>

      {lecture !== undefined && (
        <section className="rounded border border-neutral-800 p-3 text-xs">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h4 className="text-sm text-neutral-100">Lecture {lecture}: {run.lectures.find((l) => l.n === lecture)?.title}</h4>
            <button data-testid="voice-speak-all" className={`${btn} ml-auto border-emerald-700 text-emerald-200 hover:bg-emerald-950`}
              onClick={() => void act({ action: "speak", lecture })}>Speak the chapters with scenes not spoken yet</button>
            <button className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => { if (confirm(`Forget lecture ${lecture}'s voice?`)) void act({ action: "reset", lecture }); }}>Reset the lecture's voice</button>
          </div>
          <table className="w-full text-left">
            <thead className="text-neutral-500"><tr><th className="py-1">Chapter</th><th>Scenes</th><th>Voice</th><th>Length</th><th>Lines</th><th>Cost</th><th /></tr></thead>
            <tbody>
              {rows.map(({ c, built, total }) => {
                const v = lv[c.n];
                const ok = built === total && total > 0;
                const cost = v ? (v.cost?.spoken ?? 0) + (v.cost?.director ?? 0) + (v.cost?.timing ?? 0) : 0;
                return (
                  <tr key={c.n} data-testid={`voice-chapter-${c.n}`} className={`border-t border-neutral-800 ${chapter === c.n ? "bg-neutral-900" : ""}`}>
                    <td className="py-1"><button className="text-left hover:underline" onClick={() => setChapter(c.n)}>{c.n}. {c.title}</button></td>
                    <td className={ok ? "text-emerald-300" : "text-neutral-500"}>{built}/{total} beats{ok ? "" : " (build them first)"}</td>
                    <td className={v ? TONE[v.status] : "text-neutral-500"}>
                      {v ? (v.status === "running" ? v.phase ?? "running" : v.status === "failed" ? "failed" : `spoken (${v.mode})`) : "not spoken"}
                      {behind(c.n) && <span className="ml-1 text-amber-300" data-testid={`voice-behind-${c.n}`}>· its scenes changed since: speak it again</span>}
                    </td>
                    <td>{seconds(length(v))}</td>
                    <td>{v?.lines ? `${v.lines.length}${v.cost?.newLines !== undefined ? ` (${v.cost.newLines} new)` : ""}` : ""}</td>
                    <td>{v ? money(cost) : ""}</td>
                    <td className="space-x-1 text-right">
                      <button data-testid={`voice-speak-${c.n}`} disabled={!ok || v?.status === "running"} className={`${btn} border-neutral-700 hover:bg-neutral-800`}
                        onClick={() => { setChapter(c.n); void act({ action: "speak", lecture, chapter: c.n }); }}>{v ? "Speak again" : "Speak"}</button>
                      {v && v.status !== "running" && <button className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => void act({ action: "reset", lecture, chapter: c.n })}>Reset</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {lecture !== undefined && chapter !== undefined && <ChapterView run={run} n={lecture} chapter={chapter} v={open} onCall={onCall} act={act} />}
    </div>
  );
}

/** One chapter: its voice as made from its scenes, or its beat script edited by hand and tried. */
function ChapterView({ run, n, chapter, v, onCall, act }: { run: Run; n: number; chapter: number; v?: ChapterVoice; onCall: (id: string) => void; act: Act }) {
  const [tab, setTab] = useState<"voice" | "edit">("voice");
  const trial = run.voice?.trials?.[n]?.[chapter];
  return (
    <div className="space-y-2">
      <div className="flex gap-1">
        <button data-testid="voice-tab-voice" className={`${btn} ${tab === "voice" ? "border-white/60 bg-neutral-800" : "border-neutral-700"}`} onClick={() => setTab("voice")}>Its voice</button>
        <button data-testid="voice-tab-edit" className={`${btn} ${tab === "edit" ? "border-white/60 bg-neutral-800" : "border-neutral-700"}`} onClick={() => setTab("edit")}>
          Edit its beat script (JSON) and try it{trial?.edited ? " ·" : ""}{trial?.status === "running" ? " (trying…)" : ""}</button>
      </div>
      {tab === "voice"
        ? <VoiceResult run={run} n={n} chapter={chapter} v={v} onCall={onCall} />
        : <EditAndTry key={`${run.id}|${n}|${chapter}`} run={run} n={n} chapter={chapter} trial={trial} onCall={onCall} act={act} />}
    </div>
  );
}

/**
 * The chapter's beat script as JSON, the compiler's own (look, region, emblem, genre; the chapter, each beat with its
 * number, its words said and its operations), to change and try: spoken and played apart from the chapter's voice,
 * as often as wanted. Applying puts the visuals into the scenes (the words said stay the transcript's).
 */
function EditAndTry({ run, n, chapter, trial, onCall, act }: { run: Run; n: number; chapter: number; trial?: ChapterVoice; onCall: (id: string) => void; act: Act }) {
  const [text, setText] = useState<string>(trial?.edited ? JSON.stringify(trial.edited, null, 2) : "");
  const [loading, setLoading] = useState(!trial?.edited);
  const [loadError, setLoadError] = useState<string | null>(null);
  const load = async () => {
    setLoading(true);
    setLoadError(null);
    const res = await fetch(`/api/runs/${run.id}/voice?lecture=${n}&chapter=${chapter}`, { cache: "no-store" });
    const json = await res.json().catch(() => ({}));
    if (res.ok) setText(JSON.stringify(json.script, null, 2));
    else setLoadError(json.error ?? "the beat script could not be read");
    setLoading(false);
  };
  useEffect(() => { if (!trial?.edited) void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  let parsed: unknown;
  let parseError: string | null = null;
  try {
    parsed = text.trim() ? JSON.parse(text) : undefined;
  } catch (error) {
    parseError = (error as Error).message;
  }
  const beats = (parsed as { chapter?: { beats?: unknown[] } } | undefined)?.chapter?.beats;
  const running = trial?.status === "running";
  return (
    <section className="space-y-2 rounded border border-neutral-800 p-3 text-xs" data-testid="voice-edit">
      <p className="text-neutral-400">
        The chapter as the compiler is given it: change any beat&apos;s <code>do</code> (its operations), <code>paragraph</code>, <code>pause</code>,{" "}
        <code>about</code>, or its words (<code>say</code>), the <code>style</code> and <code>art</code>, the <code>region</code> or the <code>emblem</code>;
        add or take out beats. <b>Speak and play this</b> compiles it, speaks it with the voice above, times its animations to the words and plays it here,
        apart from the chapter&apos;s own voice. Lines already spoken are not paid for again.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button data-testid="voice-try" disabled={!!parseError || !parsed || running} className={`${btn} border-emerald-700 text-emerald-200 hover:bg-emerald-950`}
          onClick={() => void act({ action: "try", lecture: n, chapter, script: parsed })}>{running ? `${trial?.phase ?? "trying"}…` : "Speak and play this"}</button>
        <button disabled={!!parseError || !parsed} className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => setText(JSON.stringify(parsed, null, 2))}>Format</button>
        <button disabled={loading || running} className={`${btn} border-neutral-700 hover:bg-neutral-800`}
          onClick={() => { if (!trial?.edited || confirm("Replace what is here with the scenes' beat script as it is now?")) void load(); }}>Back to the scenes&apos; script</button>
        <button data-testid="voice-apply" disabled={!!parseError || !parsed || running} className={`${btn} border-amber-700 text-amber-200 hover:bg-amber-950`}
          onClick={() => { if (confirm("Put these visuals into the chapter's scenes (each beat by its number), and compile? The words said stay the transcript's.")) void act({ action: "apply", lecture: n, chapter, script: parsed }); }}>
          Apply to the scenes</button>
        {trial && !running && <button className={`${btn} border-neutral-700 hover:bg-neutral-800`} onClick={() => void act({ action: "resetTrial", lecture: n, chapter })}>Forget the trial</button>}
        <span className={`ml-auto ${parseError ? "text-red-300" : "text-neutral-500"}`} data-testid="voice-json-state">
          {loading ? "reading the beat script…" : parseError ? `not JSON: ${parseError}` : Array.isArray(beats) ? `${beats.length} beat(s)` : "no beats"}</span>
      </div>
      {loadError && <p className="text-red-300">{loadError}</p>}
      {trial?.applied && (
        <p className="text-amber-200">Applied {new Date(trial.applied.at).toLocaleTimeString()}: {trial.applied.beats} beat(s) put into the scenes (compiling on the Scenes tab)
          {trial.applied.notes.length ? <>; {trial.applied.notes.join("; ")}</> : null}. Speak the chapter again for its own voice.</p>
      )}
      <textarea data-testid="voice-json" spellCheck={false} value={text} onChange={(e) => setText(e.target.value)}
        className="mono h-[28rem] w-full resize-y rounded border border-neutral-700 bg-neutral-950 p-2 text-[11px] leading-snug text-neutral-100" />
      {trial && trial.status !== "running" && (
        <div className="space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-300">The edit, tried</p>
          <VoiceResult run={run} n={n} chapter={chapter} v={trial} onCall={onCall} tried />
        </div>
      )}
    </section>
  );
}

function VoiceResult({ run, n, chapter, v, onCall, tried }: { run: Run; n: number; chapter: number; v?: ChapterVoice; onCall: (id: string) => void; tried?: boolean }) {
  const [beat, setBeat] = useState<number | undefined>();
  const [view, setView] = useState<"lines" | "timing">("lines");
  const c = run.script?.lectures[n]?.chapters.find((x) => x.n === chapter);
  if (!v || !v.status || (!v.ir && v.status === "done" && v.applied)) return <p className="text-xs text-neutral-400">{tried ? "Not tried yet." : `Chapter ${chapter} is not spoken yet.`}</p>;
  if (v.status === "running") return <p className="text-xs text-sky-300" data-testid="voice-running">Chapter {chapter}: {v.phase ?? "running"}…</p>;
  if (v.status === "failed") return <p className="whitespace-pre-wrap text-xs text-red-300" data-testid="voice-error">Chapter {chapter} could not be {tried ? "tried" : "spoken"}: {v.error}</p>;
  const range = beat !== undefined ? v.beats?.find((b) => b.n === beat) : undefined;
  const estimated = (v.lines ?? []).some((l) => l.wordsFrom === "estimated");
  return (
    <section className="space-y-3 rounded border border-neutral-800 p-3 text-xs" data-testid={tried ? "voice-tried" : "voice-chapter"}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h4 className="text-sm text-neutral-100">Chapter {chapter}: {tried ? v.edited?.chapter.title ?? c?.title : c?.title}{tried ? " (edited)" : ""}</h4>
        <span className="text-neutral-400">{v.mode} · {v.style}/{v.art} · {seconds(length(v))} · made in {seconds(v.seconds)}</span>
        <span className="ml-auto text-neutral-400">voice {money(v.cost?.spoken ?? 0)}{v.cost?.director ? ` · delivery marking ${money(v.cost.director)}` : ""} · timing {money(v.cost?.timing ?? 0)}</span>
      </div>
      {v.ir && v.assets && (
        <div className="space-y-2">
          <IRPlayer src={v.ir} assets={v.assets} audio={v.audio} range={range ? [range.from, range.to] : undefined} />
          <div className="flex flex-wrap gap-1">
            <button className={`${btn} ${beat === undefined ? "border-white/60 bg-neutral-800" : "border-neutral-700"}`} onClick={() => setBeat(undefined)}>The whole chapter</button>
            {(v.beats ?? []).map((b) => (
              <button key={b.n} className={`${btn} ${beat === b.n ? "border-white/60 bg-neutral-800" : "border-neutral-700"}`} onClick={() => setBeat(b.n)}
                title={`${b.start.toFixed(1)}-${b.end.toFixed(1)} s`}>#{b.n} <span className="text-neutral-500">{(b.end - b.start).toFixed(1)}s</span></button>
            ))}
          </div>
          {v.audio && <a className="text-sky-300 hover:underline" href={v.audio} target="_blank" rel="noreferrer">the narration track (WAV)</a>}
          {v.blockers?.length ? <p className="text-amber-300">Left out of what plays: {v.blockers.join("; ")}</p> : null}
        </div>
      )}
      <p className={estimated ? "text-amber-300" : "text-neutral-500"}>
        Word times: {v.aligner}{estimated ? ". The words here are ESTIMATED (spread over the spoken parts of each line by their length), so the animations land only roughly on them; with Whisper available they are aligned to the audio." : "."}
      </p>
      <div className="flex gap-1">
        {(["lines", "timing"] as const).map((k) => (
          <button key={k} className={`${btn} ${view === k ? "border-white/60 bg-neutral-800" : "border-neutral-700"}`} onClick={() => setView(k)}>
            {k === "lines" ? `Lines spoken (${v.lines?.length ?? 0})` : `Animations timed (${(v.cues ?? []).filter((x) => x.cues).length} of ${v.cues?.length ?? 0} beats)`}
          </button>
        ))}
        {(v.calls ?? []).map((id) => <button key={id} className={`${btn} border-neutral-700 text-sky-300`} onClick={() => onCall(id)}>call {id}</button>)}
      </div>
      {view === "lines" ? <Lines lines={v.lines ?? []} beat={beat} /> : <Timing cues={v.cues ?? []} lines={v.lines ?? []} beat={beat} />}
    </section>
  );
}

function Words({ line }: { line: VoiceLine }) {
  if (!line.words?.length) return <span className="text-neutral-500">no word times ({line.wordsFrom ?? "none"})</span>;
  return (
    <span className="flex flex-wrap gap-x-1.5 gap-y-0.5">
      {line.words.map((w, i) => <span key={i}><span className="text-neutral-500">{w.start.toFixed(2)}</span> {w.w}</span>)}
    </span>
  );
}

function Lines({ lines, beat }: { lines: VoiceLine[]; beat?: number }) {
  const shown = beat !== undefined ? lines.filter((l) => l.beat === beat) : lines;
  return (
    <ol className="space-y-2" data-testid="voice-lines">
      {shown.map((l, i) => (
        <li key={i} className="rounded border border-neutral-800 p-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-neutral-500">{l.beat !== undefined ? `beat #${l.beat}` : "title card"}</span>
            <span className="text-neutral-400">{seconds(l.seconds)}</span>
            {l.usd !== undefined && l.usd !== null && <span className="text-neutral-500">{money(l.usd)}</span>}
            <span className={l.wordsFrom === "estimated" ? "text-amber-300" : l.wordsFrom === "voice" || l.wordsFrom === "aligned" ? "text-emerald-300" : "text-neutral-500"}>
              words: {l.wordsFrom ?? "none"}
            </span>
            {l.url && <audio controls preload="none" src={l.url} className="ml-auto h-7" />}
          </div>
          <p className="mt-1 text-neutral-100">{l.text}</p>
          {l.spoken && <p className="text-neutral-500">said as: {l.spoken}</p>}
          {l.delivery && <p className="text-neutral-500">marked for delivery: {l.delivery}</p>}
          <div className="mt-1 text-[11px] text-neutral-300"><Words line={l} /></div>
        </li>
      ))}
      {!shown.length && <li className="text-neutral-500">No line of this beat.</li>}
    </ol>
  );
}

/** Each beat's animations on its line's timeline, with the words' ticks under them. */
function Timing({ cues, lines, beat }: { cues: VoiceCue[]; lines: VoiceLine[]; beat?: number }) {
  const shown = beat !== undefined ? cues.filter((c) => c.beat === beat) : cues;
  return (
    <ol className="space-y-2" data-testid="voice-cues">
      {shown.map((c, i) => {
        const total = Math.max(0.5, c.seconds ?? 1);
        const line = lines.find((l) => l.text === c.text);
        const at = (t: number) => `${Math.min(100, (t / total) * 100)}%`;
        return (
          <li key={i} className="rounded border border-neutral-800 p-2">
            <div className="flex flex-wrap gap-2">
              <span className="text-neutral-500">{c.beat !== undefined ? `beat #${c.beat}` : "a beat"}</span>
              <span className="text-neutral-400">{c.kind === "free" ? "Manim block: its plays" : "animations"} · line {total.toFixed(2)} s</span>
              {c.why && <span className="text-amber-300">not timed: {c.why} (they play together as the line begins)</span>}
            </div>
            <p className="mt-1 text-neutral-300">{c.text}</p>
            <div className="relative mt-2 h-3 rounded bg-neutral-900">
              {(line?.words ?? []).map((w, k) => <span key={k} className="absolute top-0 h-3 w-px bg-neutral-600" style={{ left: at(w.start) }} title={`${w.start.toFixed(2)} ${w.w}`} />)}
            </div>
            <ul className="mt-1 space-y-1">
              {c.parts.map((p, k) => {
                const cue = c.cues?.[k];
                const start = cue === undefined ? undefined : Array.isArray(cue) ? cue[0] : cue;
                const run = Array.isArray(cue) ? cue[1] : 0.6;
                const word = start !== undefined ? line?.words?.find((w) => w.start >= start - 0.05) : undefined;
                return (
                  <li key={k}>
                    <div className="relative h-2 rounded bg-neutral-900">
                      {start !== undefined && <span className="absolute top-0 h-2 rounded bg-sky-500/70" style={{ left: at(start), width: `${Math.max(1, (run / total) * 100)}%` }} />}
                    </div>
                    <div className="flex gap-2 text-[11px]">
                      <span className="w-28 shrink-0 text-sky-300">{start !== undefined ? `${start.toFixed(2)} s${Array.isArray(cue) ? ` for ${cue[1].toFixed(2)} s` : ""}` : "at the start"}</span>
                      {word && <span className="shrink-0 text-neutral-500">on “{word.w}”</span>}
                      <code className="truncate text-neutral-400" title={p}>{p}</code>
                    </div>
                  </li>
                );
              })}
            </ul>
          </li>
        );
      })}
      {!shown.length && <li className="text-neutral-500">No animation of this beat to time.</li>}
    </ol>
  );
}
