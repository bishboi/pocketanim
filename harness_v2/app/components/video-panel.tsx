"use client";

/**
 * The video step (lib/video.ts), v2's default flow after the transcript: each chapter spoken from its lines and its
 * words aligned, then built by the video agent in free Manim, and played here as the phone plays it.
 *
 *   - Settings: the voice (engine, speaker, pace), the agent's model, its image model, its turns, and the look (a
 *     screenshot of how the visuals look, and words about it).
 *   - One lecture: its chapters, each with its narration (spoken, how long, where its word times came from, cost) and
 *     its video (the agent's turns and cost, the program's length and size, whether the phone plays what Manim drew).
 *   - One chapter: the player (the program the phone plays, with its narration), the Manim render it was checked
 *     against, the narration's lines and words with their times, and every step the agent took.
 */

import { useEffect, useRef, useState } from "react";
import type { ChapterVideo, Run } from "@/lib/types";
import { ENGINES } from "@/lib/voice-engines";
import { money } from "./call-inspector";
import { AgentLog } from "./agent-log";
import { IRPlayer } from "./player";

type Act = (body: Record<string, unknown>) => Promise<boolean>;
type Timing = { seconds: number; source?: string; lines: { n: number; text: string; start: number; end: number; words: { w: string; start: number; end: number; est?: boolean }[] }[] };
const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";
const seconds = (s?: number) => s === undefined || !Number.isFinite(s) ? "" : s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${s.toFixed(1)} s`;
const TONE: Record<string, string> = { running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300", stopped: "text-amber-300" };
const key = (n: number, c: number) => `${n}-${c}`;

function videoState(cv?: ChapterVideo): { label: string; tone: string } {
  if (!cv?.agent) return { label: cv?.build ? "built" : "not built", tone: "text-neutral-500" };
  if (cv.agent.status === "running") return { label: `building · turn ${cv.agent.turns}`, tone: TONE.running };
  if (cv.agent.status === "done" && cv.build) {
    const stale = cv.build.blockers.length > 0;
    return { label: stale ? "built (out of date)" : "built", tone: stale ? "text-amber-300" : TONE.done };
  }
  return { label: cv.agent.status === "stopped" ? "stopped" : `failed${cv.agent.error ? `: ${cv.agent.error.slice(0, 60)}` : ""}`, tone: TONE[cv.agent.status] };
}

export function VideoPanel({ run, ready, defaults, onCall, act, voiceAct }: {
  run: Run; ready?: Record<string, boolean>; defaults: { model: string; imageModel: string }; onCall: (id: string) => void; act: Act; voiceAct: Act;
}) {
  const scripted = run.lectures.filter((l) => run.script?.lectures[l.n]?.status === "done" && run.script.lectures[l.n].chapters.length);
  const [lecture, setLecture] = useState<number | undefined>(scripted[0]?.n);
  const [chapter, setChapter] = useState<number | undefined>();
  const [note, setNote] = useState("");
  const [timing, setTiming] = useState<Timing | null>(null);
  const vset = run.video?.settings ?? {};
  const voice = run.voice?.settings ?? { engine: ready?.gemini ? "gemini" : "espeak", pace: "natural" };
  const [model, setModel] = useState(vset.model ?? "");
  const [imageModel, setImageModel] = useState(vset.imageModel ?? "");
  const [turns, setTurns] = useState(String(vset.turns ?? ""));
  const [styleNote, setStyleNote] = useState(vset.styleNote ?? "");
  const [speaker, setSpeaker] = useState(voice.voice ?? "");
  const [styleV, setStyleV] = useState(0);
  // Where the agent will run and how hard it will reason, as the server resolves it (model, keys, settings).
  const [agentEngine, setAgentEngine] = useState<{ model: string; provider: string; effort: string; openaiKey: boolean } | null>(null);
  useEffect(() => {
    fetch(`/api/runs/${run.id}/video`).then((r) => r.json()).then((j) => setAgentEngine(j.settings ?? null)).catch(() => {});
  }, [run.id, run.video?.settings.model, run.video?.settings.effort]);
  const upload = useRef<HTMLInputElement>(null);
  useEffect(() => { if (lecture === undefined && scripted.length) setLecture(scripted[0].n); }, [scripted.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const cv = lecture !== undefined && chapter !== undefined ? run.video?.chapters[key(lecture, chapter)] : undefined;
  const narrationAt = cv?.narration?.ended ?? 0;
  useEffect(() => {
    setTiming(null);
    if (lecture === undefined || chapter === undefined) return;
    fetch(`/api/runs/${run.id}/video?lecture=${lecture}&chapter=${chapter}`).then((r) => r.json()).then((j) => setTiming(j.timing ?? null)).catch(() => {});
  }, [run.id, lecture, chapter, narrationAt]);

  if (!scripted.length) return <p className="text-sm text-neutral-400">No lecture has its script yet: write the transcript first. Each chapter is then spoken, its words aligned, and its video built by the agent.</p>;
  const chapters = lecture !== undefined ? run.script?.lectures[lecture]?.chapters ?? [] : [];
  const engine = ENGINES.find((e) => e.id === voice.engine) ?? ENGINES[0];
  const all = Object.values(run.video?.chapters ?? {});
  const cost = run.calls.filter((c) => c.step === "video-agent").reduce((k, c) => k + c.cost, 0) + all.reduce((k, c) => k + (c.narration?.cost ?? 0), 0);
  const busy = (c: number) => run.video?.chapters[key(lecture!, c)]?.agent?.status === "running" || run.video?.chapters[key(lecture!, c)]?.narration?.status === "running";

  const pickStyle = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => void act({ action: "settings", style: String(reader.result) }).then(() => setStyleV((v) => v + 1));
    reader.readAsDataURL(file);
  };

  return (
    <div className="space-y-3 text-xs" data-testid="video">
      <section className="rounded border border-neutral-800 p-3">
        <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-sm font-semibold text-neutral-100">Video</h3>
          <span className="text-neutral-400">Each chapter is spoken from its transcript and its words aligned; then the video agent builds it in free Manim, timed to the words, and it plays here as on the phone.</span>
          <span className="ml-auto text-neutral-400">{all.filter((c) => c.build).length} chapter(s) built · {money(cost)}</span>
        </div>
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">Voice</span>
              <select data-testid="video-voice" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={voice.engine}
                onChange={(e) => { setSpeaker(""); void voiceAct({ action: "settings", engine: e.target.value, voice: "" }); }}>
                {ENGINES.map((e) => <option key={e.id} value={e.id}>{e.label}{ready && !ready[e.id] ? " (no key)" : ""}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">Speaker</span>
              <input list="video-speakers" className="w-32 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={speaker} placeholder="default"
                onChange={(e) => setSpeaker(e.target.value)} onBlur={() => speaker !== (voice.voice ?? "") && void voiceAct({ action: "settings", voice: speaker })} />
              <datalist id="video-speakers">{engine.voices.map((v) => <option key={v} value={v} />)}</datalist>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">Pace</span>
              <select className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={voice.pace ?? "natural"}
                onChange={(e) => void voiceAct({ action: "settings", pace: e.target.value })}>
                {["natural", "relaxed", "slow"].map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">Agent model</span>
              <input data-testid="video-model" className="w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={model} placeholder={defaults.model}
                onChange={(e) => setModel(e.target.value)} onBlur={() => model !== (vset.model ?? "") && void act({ action: "settings", model })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">Image model</span>
              <input className="w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={imageModel} placeholder={defaults.imageModel}
                onChange={(e) => setImageModel(e.target.value)} onBlur={() => imageModel !== (vset.imageModel ?? "") && void act({ action: "settings", imageModel })} />
            </label>
            <label className="flex flex-col gap-1" title="lean: it only writes its scene (each write rendered and checked on the phone) and looks at frames; far fewer turns. agent: every tool (files, shell, section renders, kit previews, pictures).">
              <span className="text-neutral-400">Agent tools</span>
              <select data-testid="video-mode" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={vset.mode ?? "lean"}
                onChange={(e) => void act({ action: "settings", mode: e.target.value })}>
                <option value="lean">lean: scene + look</option>
                <option value="agent">agent: every tool</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">Agent reasoning</span>
              <select data-testid="video-effort" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={vset.effort ?? "high"}
                onChange={(e) => void act({ action: "settings", effort: e.target.value })}>
                {["max", "xhigh", "high", "medium", "low", "off"].map((x) => <option key={x}>{x}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-neutral-400">Turns at most</span>
              <input className="w-20 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={turns} placeholder={(vset.mode ?? "lean") === "lean" ? "20" : "60"}
                onChange={(e) => setTurns(e.target.value)} onBlur={() => turns !== String(vset.turns ?? "") && void act({ action: "settings", turns: Number(turns) || 0 })} />
            </label>
          </div>
          {agentEngine && (
            <p className="w-full text-neutral-400" data-testid="video-engine">
              The agent will run on <span className="text-neutral-200">{agentEngine.model}</span> via{" "}
              <span className="text-neutral-200">{agentEngine.provider === "openai" ? "OpenAI's API" : agentEngine.provider === "fixture" ? "the stand-in (no key)" : "OpenRouter"}</span>
              {" "}with reasoning <span className={agentEngine.effort === "off" ? "text-amber-300" : "text-violet-300"}>{agentEngine.effort}</span>
              {agentEngine.model.startsWith("openai/") && !agentEngine.openaiKey ? " (set OPENAI_API_KEY to run OpenAI models on OpenAI's own API, with their reasoning kept between turns)" : ""}
              {agentEngine.effort === "max" || agentEngine.effort === "xhigh" ? `; a model that does not take ${agentEngine.effort} runs at high` : ""}.
            </p>
          )}
          <div className="flex items-start gap-2" data-testid="video-style">
            <img src={`/api/runs/${run.id}/video?style=1&v=${styleV}`} alt="The look" className="h-24 rounded border border-neutral-700" />
            <div className="flex flex-col gap-1">
              <span className="text-neutral-400">The look: a screenshot of how the visuals look{vset.style ? "" : " (the default: Vox-like)"}</span>
              <div className="flex gap-1">
                <button className={`${btn} border-neutral-600`} onClick={() => upload.current?.click()}>Choose a screenshot…</button>
                {vset.style && <button className={`${btn} border-neutral-700`} onClick={() => void act({ action: "settings", style: null }).then(() => setStyleV((v) => v + 1))}>Use the default</button>}
                <input ref={upload} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && pickStyle(e.target.files[0])} />
              </div>
              <textarea className="h-12 w-72 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={styleNote} placeholder="Words about the look (optional)"
                onChange={(e) => setStyleNote(e.target.value)} onBlur={() => styleNote !== (vset.styleNote ?? "") && void act({ action: "settings", styleNote })} />
            </div>
          </div>
        </div>
      </section>

      <section className="rounded border border-neutral-800 p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-neutral-400">Lecture</span>
          <select data-testid="video-lecture" className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={lecture}
            onChange={(e) => { setLecture(Number(e.target.value)); setChapter(undefined); }}>
            {scripted.map((l) => <option key={l.n} value={l.n}>{l.n}. {l.title}</option>)}
          </select>
          <button data-testid="video-all" className={`${btn} border-emerald-700 text-emerald-200`} disabled={chapters.some((c) => busy(c.n))}
            onClick={() => void act({ action: "all", lecture, note: note || undefined })}>Speak and build every chapter</button>
          {chapters.some((c) => busy(c.n)) && <button className={`${btn} border-amber-700 text-amber-200`} onClick={() => void act({ action: "stop", lecture })}>Stop</button>}
        </div>
        <table className="w-full text-left">
          <thead className="text-neutral-500"><tr><th className="py-1">Chapter</th><th>Narration</th><th>Video</th><th>Phone</th><th>Cost</th><th /></tr></thead>
          <tbody>
            {chapters.map((c) => {
              const v = run.video?.chapters[key(lecture!, c.n)];
              const n = v?.narration;
              const st = videoState(v);
              const chapterCost = (v?.narration?.cost ?? 0) + (v?.agent?.cost ?? 0);
              return (
                <tr key={c.n} data-testid={`video-row-${c.n}`} className={`border-t border-neutral-800 ${chapter === c.n ? "bg-neutral-800/60" : ""}`}>
                  <td className="py-1"><button className="text-left text-neutral-100 underline-offset-2 hover:underline" onClick={() => setChapter(c.n)}>{c.n}. {c.title}</button></td>
                  <td className={n ? TONE[n.status] : "text-neutral-500"}>
                    {!n ? "not spoken" : n.status === "running" ? `${n.progress?.phase ?? "speaking"} ${n.progress ? `${n.progress.done}/${n.progress.total}` : ""}`
                      : n.status === "done" ? `${seconds(n.seconds)} · ${n.source}` : `failed: ${n.error?.slice(0, 80)}`}
                  </td>
                  <td className={st.tone}>{st.label}</td>
                  <td>{v?.build ? `${seconds(v.build.seconds)} · ${(v.build.bytes / 1e6).toFixed(1)} MB · ${v.build.check?.ok === false ? "differs" : "matches Manim"}` : ""}</td>
                  <td className="text-neutral-400">{chapterCost ? money(chapterCost) : ""}</td>
                  <td className="space-x-1 whitespace-nowrap text-right">
                    <button className={`${btn} border-neutral-600`} disabled={busy(c.n)} onClick={() => void act({ action: "narrate", lecture, chapter: c.n })}>{n?.status === "done" ? "Speak again" : "Speak"}</button>
                    <button data-testid={`video-build-${c.n}`} className={`${btn} border-emerald-700 text-emerald-200`} disabled={busy(c.n)}
                      onClick={() => { setChapter(c.n); void act({ action: "build", lecture, chapter: c.n, note: note || undefined }); }}>{v?.build ? "Build again" : "Build"}</button>
                    {busy(c.n) && <button className={`${btn} border-amber-700 text-amber-200`} onClick={() => void act({ action: "stop", lecture, chapter: c.n })}>Stop</button>}
                    {(v?.agent || v?.build) && !busy(c.n) && <button className={`${btn} border-rose-800 text-rose-200`} title="Throw away this chapter's video and everything the agent wrote (the voice is kept), then build it from scratch"
                      onClick={() => { if (!confirm(`Reset chapter ${c.n}'s video and build it again from scratch? The voice is kept.`)) return; setChapter(c.n); void act({ action: "rebuild", lecture, chapter: c.n, note: note || undefined }); }}>Reset and rebuild</button>}
                    {v && !busy(c.n) && <button className={`${btn} border-neutral-700 text-neutral-400`} title="Throw away this chapter's video and its voice" onClick={() => void act({ action: "reset", lecture, chapter: c.n })}>Reset</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <label className="mt-2 flex items-center gap-2">
          <span className="text-neutral-400">A note for the agent (optional)</span>
          <input className="flex-1 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. more maps; slower cuts; a darker look" />
        </label>
      </section>

      {lecture !== undefined && chapter !== undefined && (
        <section className="space-y-3 rounded border border-neutral-800 p-3" data-testid="video-chapter">
          <h4 className="text-sm font-semibold text-neutral-100">Chapter {chapter}: {chapters.find((c) => c.n === chapter)?.title}</h4>
          {cv?.build ? (
            <div className="space-y-1">
              <div className="text-neutral-400">As the phone plays it: {seconds(cv.build.seconds)}, {(cv.build.bytes / 1e6).toFixed(1)} MB, tier {cv.build.tier}
                {cv.build.check ? ` · ${cv.build.check.frames} frames compared with Manim's, ${cv.build.check.differ.length} differ` : ""}
                {cv.build.blockers.length ? ` · ${cv.build.blockers.join("; ")}` : ""}
                {cv.build.video && <> · <a className="text-sky-300 underline" href={cv.build.video} target="_blank" rel="noreferrer">the Manim render</a></>}
                {" · "}<a data-testid="video-library" className="text-sky-300 underline" href={`/api/runs/${run.id}/video?library=1&lecture=${lecture}&chapter=${chapter}`}
                  title="The chapter packed for the phone (program, clips, pictures, narration), checked by the phone's own code: import it on the phone">Phone library (zip)</a>
              </div>
              <IRPlayer key={cv.build.ir} src={cv.build.ir} assets={cv.build.assets} audio={cv.build.audio} />
            </div>
          ) : <p className="text-neutral-400">Not built yet{cv?.agent?.status === "running" ? ": the agent is at work (its steps are below)" : ""}.</p>}

          {cv?.narration?.track && (
            <details open={!cv.build}>
              <summary className="cursor-pointer text-neutral-300">The narration: {seconds(cv.narration.seconds)}, {cv.narration.lines} lines, word times from {cv.narration.source}, {cv.narration.engine}{cv.narration.cost ? `, ${money(cv.narration.cost)}` : ""}</summary>
              <audio controls src={cv.narration.track} className="mt-1 w-full" />
              {timing && (
                <ol className="mt-1 space-y-1">
                  {timing.lines.map((l) => (
                    <li key={l.n} className="rounded border border-neutral-800 p-1.5">
                      <span className="text-neutral-500">[{l.n}] {l.start.toFixed(1)}–{l.end.toFixed(1)} s</span> <span className="text-neutral-200">{l.text}</span>
                      <div className="mt-0.5 flex flex-wrap gap-x-2 text-[11px] text-neutral-500">{l.words.map((w, i) => <span key={i} className={w.est ? "italic" : ""}>{w.w}<sub>{w.start.toFixed(1)}</sub></span>)}</div>
                    </li>
                  ))}
                </ol>
              )}
            </details>
          )}

          {cv?.agent && <AgentLog key={`${lecture}-${chapter}-${cv.agent.started}`} run={run} n={lecture} c={chapter} agent={cv.agent} built={cv.build} onCall={onCall} />}
        </section>
      )}
    </div>
  );
}
