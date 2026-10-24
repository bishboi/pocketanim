"use client";

/**
 * The scenes: each beat's visuals as the lecture engine's operations, compiled, and rendered to be looked at.
 *
 *   - The look: the style (the film's frame) and the art style (how its pictures are drawn), each with a miniature;
 *     what is rendered and the Styled redraws use it.
 *   - The visuals switched on: every kind (map, book figures, AI illustrations, AI detailed diagrams, gallery,
 *     diagrams, timeline, Manim...) on or off for the run; a beat can have its own.
 *   - Build: the next lecture, one lecture, all (in parallel or one at a time); a chapter or a beat again.
 *   - One lecture: its chapters and beats in an outline (what each beat uses, what the compiler refused, what is
 *     rendered); a chapter shows its render (the video, a frame for each beat); a beat shows its sentences, its
 *     operations (as cards, or as JSON to change by hand), the compiler's words on it, its kinds, and its render
 *     (its clip and last frame), in the run's look or another.
 */

import { useEffect, useMemo, useState } from "react";
import type { BeatPicture, Call, MissingPicture, Run, SceneBeat, SceneLecture, SceneRender } from "@/lib/types";
import { linesOf } from "@/lib/source/book";
import { ART_STYLES, STYLES, STYLE_ART, artOf, artPreview, styleOf, type PreviewMark } from "@/lib/styles";
import { MOTION_KIND, VISUAL_KINDS, kindById, kindOfOp } from "@/lib/visual-kinds";
import { MOTION_IDLES, MOTION_LOOKS, MOTION_TRANSITIONS } from "@/lib/prompts/scenes-motion";
import { beatFigures, lectureFigures } from "@/lib/script-figures";
import { money, seconds } from "./call-inspector";
import { FrameStill, IRPlayer } from "./player";
import { PromptView } from "./script-panel";
import type { Selection } from "./panels";

type Act = (body: Record<string, unknown>) => Promise<boolean>;
type Lecture = Run["lectures"][number];
type Pick = { kind: "chapter"; c: number } | { kind: "beat"; n: number };

const TONE = { waiting: "text-neutral-400", running: "text-sky-300", done: "text-emerald-300", failed: "text-red-300" } as const;
const DOT = { waiting: "bg-neutral-500", running: "bg-sky-400 animate-pulse", done: "bg-emerald-400", failed: "bg-red-400" } as const;
/** A colour per visual kind, for its badges. */
const KIND_COLOR: Record<string, string> = {
  base: "#a3a3a3", map: "#34d399", figure: "#fbbf24", illustration: "#f472b6", drawing: "#fb7185", gallery: "#e879f9", diagram: "#38bdf8",
  timeline: "#a78bfa", manim: "#22d3ee", equation: "#facc15", molecule: "#4ade80", define: "#93c5fd", compare: "#c4b5fd", question: "#fdba74",
  numbers: "#fca5a5", work: "#5eead4", words: "#d6d3d1", motion: "#e879f9",
};
const btn = "rounded border px-2.5 py-1 text-xs disabled:opacity-40";

export function ScenesPanel({ run, defaultModel, manimModel, reuseModel = "", select, onCall, act }: {
  run: Run; defaultModel: string; manimModel: string; reuseModel?: string; select: (s: Selection) => void; onCall: (id: string) => void; act: Act;
}) {
  const st = run.scenes;
  const [model, setModel] = useState(st?.model || defaultModel);
  const [inTurn, setInTurn] = useState(false);
  const [open, setOpen] = useState<number | "all">("all");
  const [showLook, setShowLook] = useState(!Object.keys(run.scenes?.lectures ?? {}).length);
  useEffect(() => { setModel(run.scenes?.model || defaultModel); setOpen("all"); }, [run.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const scripted = run.lectures.filter((l) => run.script?.lectures[l.n]?.status === "done");
  const running = st?.status === "running";
  const busy = (n: number) => running && (st?.lectures[n]?.status === "running" || (st?.lectures[n]?.status === "waiting" && !!st?.lectures[n]?.doing));
  const done = scripted.filter((l) => st?.lectures[l.n]?.status === "done").length;
  const next = scripted.find((l) => !busy(l.n) && st?.lectures[l.n]?.status !== "done");
  const look = st?.look ?? { style: "atlas", art: "auto" };
  const kinds = st?.kinds ?? VISUAL_KINDS.map((k) => k.id);
  const cost = run.calls.filter((c) => c.step === "scenes").reduce((k, c) => k + c.cost, 0);
  const beatsBuilt = Object.values(st?.lectures ?? {}).reduce((k, l) => k + Object.values(l.beats).filter((b) => b.ops.length).length, 0);
  const refused = Object.values(st?.lectures ?? {}).reduce((k, l) => k + Object.values(l.beats).filter((b) => b.errors?.length).length, 0);
  const lecture = open === "all" ? undefined : scripted.find((l) => l.n === open);
  const buildOne = (n: number) => { setOpen(n); return act({ action: "build", scope: "lecture", lecture: n, model }); };

  if (!scripted.length) return <p className="text-sm text-neutral-400">No lecture is scripted yet: build the scripts first (Script tab). The scenes give each beat of a script its visuals.</p>;
  return (
    <div className="space-y-3" data-testid="scenes">
      <section className="rounded border border-neutral-800 bg-neutral-900/60 p-3">
        <div className="flex items-baseline gap-2">
          <h3 className="text-sm font-semibold text-neutral-100">Scenes: what is on screen on each beat</h3>
          <button className="ml-auto text-[11px] text-sky-300 hover:underline" onClick={() => setShowLook(!showLook)}>{showLook ? "hide the look and visuals" : "show the look and visuals"}</button>
        </div>
        <p className="mb-2 text-xs text-neutral-400">Each beat of the script gets its visuals as the lecture engine&apos;s operations (the narration stays the
          transcript): one call a chapter, told only the kinds of visual switched on. The engine compiles the lecture (making its AI pictures), the beats it
          refuses are sent back with what it said, and any beat or chapter can be rendered (silent) to see it, in this look or another.</p>
        {showLook && <LookPicker look={look} act={act} />}
        {showLook && <KindToggles kinds={kinds} onChange={(k) => act({ action: "kinds", kinds: k })} />}
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-neutral-800 pt-2 text-xs">
          <span className="text-neutral-400">Model</span>
          <input className="mono w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" value={model}
            onChange={(e) => setModel(e.target.value)} data-testid="scenes-model" />
          <button className={`${btn} border-sky-700 bg-sky-800 text-white`} disabled={!next} data-testid="scenes-next"
            onClick={() => next && buildOne(next.n)}>{next ? `Build the next: lecture ${next.n}` : "No lecture left to build"}</button>
          <span className="mx-1 h-4 w-px bg-neutral-700" />
          <button className={`${btn} border-emerald-700 bg-emerald-700 text-white`} data-testid="scenes-run"
            disabled={scripted.every((l) => busy(l.n) || st?.lectures[l.n]?.status === "done")}
            onClick={() => act({ action: "build", scope: "rest", model, oneAtATime: inTurn })}>{!done ? "Build all" : done < scripted.length ? `Build the ${scripted.length - done} left` : "All built"}</button>
          <button className={`${btn} border-amber-700 text-amber-200 hover:bg-amber-950`} disabled={scripted.every((l) => busy(l.n))}
            onClick={() => confirm("Build every lecture's scenes again? What is there now (and any beat changed by hand) is replaced.") && act({ action: "build", scope: "all", model, oneAtATime: inTurn })}>Rebuild all</button>
          <label className="flex items-center gap-1 text-neutral-300" title="One lecture after the other, not in parallel">
            <input type="checkbox" checked={inTurn} onChange={(e) => setInTurn(e.target.checked)} /> one at a time</label>
          {running && <button className={`${btn} border-red-700 text-red-200`} onClick={() => act({ action: "stop" })}>Stop</button>}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-cyan-300">Manim figures</span>
          <label className="flex items-center gap-1 text-neutral-300" title="The scene writer plans a Manim figure; the Manim agent builds it: makes the pictures it needs, writes the code, checks it with the compiler (no render) and mends it">
            <input type="radio" checked={st?.manimAgent !== false} onChange={() => act({ action: "agentSettings", on: true })} data-testid="scenes-agent-on" /> built by the Manim agent (pictures, code checks)</label>
          <label className="flex items-center gap-1 text-neutral-300" title="The scene writer writes the Manim code itself, in its answer">
            <input type="radio" checked={st?.manimAgent === false} onChange={() => act({ action: "agentSettings", on: false })} /> written by the scene writer</label>
          <span className="text-neutral-500">agent model</span>
          <input className="mono w-56 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" defaultValue={st?.manimModel ?? manimModel} key={st?.manimModel ?? manimModel}
            onBlur={(e) => e.target.value !== (st?.manimModel ?? manimModel) && act({ action: "agentSettings", model: e.target.value })} title="the Manim role's model (V2_MANIM_MODEL); changed here for this run" />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-pink-300">AI pictures made before</span>
          <label className="flex items-center gap-1 text-neutral-300" title="For each AI picture a scene asks for, the decision model is shown the pictures made before that could be it (their words and the prompts they were drawn from) and chooses: show one again, draw a new one that matches one (the same person or place, sent as its reference), or draw fresh">
            <input type="radio" checked={st?.reuseJudge !== false} onChange={() => act({ action: "reuseSettings", on: true })} data-testid="scenes-reuse-judge" /> a decision model decides: show again, match, or draw fresh</label>
          <label className="flex items-center gap-1 text-neutral-300" title="The engine's own rule: the same words shown again, the same proper name matched">
            <input type="radio" checked={st?.reuseJudge === false} onChange={() => act({ action: "reuseSettings", on: false })} /> matched by their words</label>
          <span className="text-neutral-500">model</span>
          <input className="mono w-48 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-100" defaultValue={st?.reuseModel ?? reuseModel} key={st?.reuseModel ?? reuseModel}
            disabled={st?.reuseJudge === false}
            onBlur={(e) => e.target.value !== (st?.reuseModel ?? reuseModel) && act({ action: "reuseSettings", model: e.target.value })} title="the Picture reuse role's model (V2_REUSE_MODEL, else the triage's: Jev); changed here for this run" />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs" data-testid="scenes-pace">
          <span className="text-amber-300">Pace</span>
          <label className="flex items-center gap-1 text-neutral-300" title="No limit by default: v1's &quot;at most four operations&quot; is taken out of the instructions; a number puts that limit in its place">
            operations a beat
            <select className="rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5" value={String(st?.maxOps ?? 0)} data-testid="scenes-max-ops"
              onChange={(e) => act({ action: "pace", maxOps: Number(e.target.value) })}>
              <option value="0">no limit</option><option value="4">up to 4 (v1)</option><option value="6">up to 6</option><option value="8">up to 8</option>
            </select></label>
          <label className="flex items-center gap-1 text-neutral-300" title="v1 plans a visual a paragraph at a time (3-5 beats on one picture); every beat brings something new on screen">
            visuals change
            <select className="rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5" value={st?.visualChange ?? "paragraph"} data-testid="scenes-visual-change"
              onChange={(e) => act({ action: "pace", change: e.target.value })}>
              <option value="paragraph">a paragraph at a time (v1)</option><option value="beat">on every beat</option>
            </select></label>
          <span className="text-neutral-500">used for the next builds (and the Voice tab&apos;s instructions); build again to see it</span>
        </div>
        <EngineRow st={st} act={act} />
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-neutral-300" data-testid="scenes-summary">
          <span className={st?.status === "failed" ? "text-red-300" : running ? "text-sky-300" : st?.status === "done" ? "text-emerald-300" : "text-neutral-400"}>{st ? st.status : "not built yet"}</span>
          <span>{done} of {scripted.length} lectures built</span>
          <span>{beatsBuilt} beats with visuals</span>
          {refused > 0 && <span className="text-red-300">{refused} refused by the compiler</span>}
          {(st?.renders ?? 0) > 0 && <span className="text-sky-300">{st!.renders} rendering…</span>}
          <span className="text-neutral-500">{styleOf(look.style).name} · {artOf(look.art).name} art</span>
          {st?.engine === "motion" && <span className="text-fuchsia-300" data-testid="scenes-engine-badge">motion engine (beta){st.motion?.look ? ` · ${st.motion.look}` : ""}</span>}
          <span className="font-semibold">{money(cost)}</span>
        </div>
        {st?.error && <p className="mt-2 rounded border border-red-800 bg-red-950/40 p-2 text-xs text-red-200">{st.error}</p>}
      </section>

      <nav className="flex flex-wrap gap-1 border-b border-neutral-800">
        <Tab on={open === "all"} onClick={() => setOpen("all")}>All lectures</Tab>
        {scripted.map((l) => {
          const s = st?.lectures[l.n]?.status ?? "waiting";
          return <Tab key={l.n} on={open === l.n} onClick={() => setOpen(l.n)} title={l.title}>
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${st?.lectures[l.n] ? DOT[s] : "bg-neutral-700"}`} /> Lecture {l.n}</Tab>;
        })}
      </nav>
      {!lecture ? <Overview run={run} lectures={scripted} busy={busy} openLecture={setOpen} build={buildOne} />
        : <LectureView key={lecture.n} run={run} lecture={lecture} busy={busy(lecture.n)} model={model} act={act} select={select} onCall={onCall} />}
    </div>
  );
}

function Tab({ on, onClick, title, children }: { on: boolean; onClick: () => void; title?: string; children: React.ReactNode }) {
  return <button onClick={onClick} title={title} data-testid="scenes-tab"
    className={`flex items-center gap-1.5 rounded-t px-2.5 py-1 text-xs ${on ? "bg-neutral-800 text-white" : "text-neutral-400 hover:text-neutral-200"}`}>{children}</button>;
}

function Mini({ marks, background }: { marks: PreviewMark[]; background: string }) {
  return (
    <svg viewBox="0 0 320 180" className="w-full rounded" style={{ background }}>
      {marks.map((m, i) => m.t === "rect" ? <rect key={i} x={m.x} y={m.y} width={m.w} height={m.h} fill={m.fill} rx={m.rx} opacity={m.opacity} />
        : m.t === "circle" ? <circle key={i} cx={m.cx} cy={m.cy} r={m.r} fill={m.fill} stroke={m.stroke} strokeWidth={m.sw} />
          : m.t === "line" ? <line key={i} x1={m.x1} y1={m.y1} x2={m.x2} y2={m.y2} stroke={m.stroke} strokeWidth={m.sw} />
            : <text key={i} x={m.x} y={m.y} fontSize={m.size} fill={m.fill} textAnchor={m.anchor} fontWeight={m.weight}>{m.text}</text>)}
    </svg>
  );
}

/** The style (frame) and art style (pictures) pickers, each with its miniature. */
function LookPicker({ look, act }: { look: { style: string; art: string }; act: Act }) {
  const s = styleOf(look.style);
  return (
    <div className="space-y-2" data-testid="scenes-look">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-400">Style <span className="font-normal normal-case text-neutral-500">· the film&apos;s frame: board, fonts, panel, captions</span></p>
      <div className="grid grid-cols-3 gap-2 lg:grid-cols-5 xl:grid-cols-9">
        {STYLES.map((x) => (
          <button key={x.id} onClick={() => act({ action: "look", style: x.id })} title={x.summary} data-testid="scenes-style"
            className={`rounded border p-1 text-left ${look.style === x.id ? "border-sky-400 ring-1 ring-sky-400" : "border-neutral-800 hover:border-neutral-600"}`}>
            <Mini marks={x.preview} background={x.background} />
            <span className="mt-0.5 block text-[11px] text-neutral-200">{x.name}</span>
          </button>
        ))}
      </div>
      <p className="text-[11px] text-neutral-500">{s.name}: {s.summary}</p>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-400">Art style <span className="font-normal normal-case text-neutral-500">· how its pictures, diagrams and maps are drawn</span></p>
      <div className="flex flex-wrap gap-1.5">
        {ART_STYLES.map((a) => (
          <button key={a.id} onClick={() => act({ action: "look", art: a.id })} title={a.summary} data-testid="scenes-art"
            className={`flex items-center gap-1.5 rounded border px-1.5 py-1 text-[11px] ${look.art === a.id ? "border-sky-400 bg-sky-950 text-sky-100" : "border-neutral-800 text-neutral-300 hover:border-neutral-600"}`}>
            <svg viewBox="0 0 64 36" className="h-5 w-9 rounded" style={{ background: s.background }}
              dangerouslySetInnerHTML={{ __html: artPreview(a.id === "auto" ? STYLE_ART[s.id] ?? "clean" : a.id, s.ink, s.palette[0]) }} />
            {a.name}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Every visual kind as a switch, with what it draws. */
function KindToggles({ kinds, onChange, compact }: { kinds: string[]; onChange: (k: string[]) => void; compact?: boolean }) {
  const on = new Set(kinds);
  const flip = (id: string) => onChange(on.has(id) ? kinds.filter((k) => k !== id) : [...kinds, id]);
  return (
    <div className={compact ? "" : "mt-3"} data-testid="scenes-kinds">
      {!compact && (
        <div className="mb-1 flex items-center gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-400">Visuals the scenes may use <span className="font-normal normal-case text-neutral-500">· {kinds.length} of {VISUAL_KINDS.length} on</span></p>
          <button className="ml-auto text-[11px] text-sky-300 hover:underline" onClick={() => onChange(VISUAL_KINDS.map((k) => k.id))}>all on</button>
          <button className="text-[11px] text-sky-300 hover:underline" onClick={() => onChange([])}>all off</button>
          <button className="text-[11px] text-sky-300 hover:underline" onClick={() => onChange(kinds.filter((k) => !kindById(k)?.paid))}>no paid pictures</button>
        </div>
      )}
      <div className={`grid gap-1.5 ${compact ? "grid-cols-2 lg:grid-cols-3" : "grid-cols-2 lg:grid-cols-4"}`}>
        {VISUAL_KINDS.map((k) => (
          <label key={k.id} title={k.about} data-testid="scenes-kind"
            className={`flex cursor-pointer items-start gap-1.5 rounded border px-1.5 py-1 text-[11px] ${on.has(k.id) ? "border-neutral-600 bg-neutral-800/60" : "border-neutral-800 opacity-60"}`}>
            <input type="checkbox" className="mt-0.5" checked={on.has(k.id)} onChange={() => flip(k.id)} />
            <span className="min-w-0">
              <span className="font-medium" style={{ color: KIND_COLOR[k.id] }}>{k.label}</span>{k.paid ? <span className="ml-1 rounded bg-amber-950 px-1 text-[9px] text-amber-300">image model</span> : null}
              {!compact && <span className="block text-neutral-500">{k.about}</span>}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}

function Overview({ run, lectures, busy, openLecture, build }: {
  run: Run; lectures: Lecture[]; busy: (n: number) => boolean; openLecture: (n: number) => void; build: (n: number) => void;
}) {
  return (
    <table className="w-full text-xs" data-testid="scenes-overview">
      <thead className="text-left text-[10px] uppercase tracking-wide text-neutral-500">
        <tr><th className="py-1">Lecture</th><th>State</th><th>Beats with visuals</th><th>Refused</th><th>Compiled</th><th>Rendered</th><th>Cost</th><th /></tr>
      </thead>
      <tbody>
        {lectures.map((l) => {
          const sl = run.scenes?.lectures[l.n];
          const all = run.script!.lectures[l.n].chapters.flatMap((c) => c.beats);
          const withOps = all.filter((b) => sl?.beats[b.n]?.ops.length).length;
          const refused = all.filter((b) => sl?.beats[b.n]?.errors?.length).length;
          const rendered = all.filter((b) => sl?.beats[b.n]?.render?.status === "done").length + Object.values(sl?.chapters ?? {}).filter((c) => c.status === "done").length;
          const cost = run.calls.filter((c) => c.step === "scenes" && c.lecture === l.n).reduce((k, c) => k + c.cost, 0);
          return (
            <tr key={l.n} className="cursor-pointer border-t border-neutral-800 hover:bg-neutral-900" onClick={() => openLecture(l.n)} data-testid="scenes-lecture">
              <td className="py-1.5 pr-2 text-neutral-100"><b>{l.n}</b>. {l.title}</td>
              <td className={TONE[sl?.status ?? "waiting"]}>{sl?.doing ?? sl?.status ?? "not built"}</td>
              <td>{withOps} of {all.length}</td>
              <td className={refused ? "text-red-300" : "text-neutral-500"}>{refused || "—"}</td>
              <td className={sl?.compile?.status === "failed" ? "text-red-300" : ""}>{sl?.compile ? sl.compile.status : "—"}</td>
              <td>{rendered || "—"}</td>
              <td>{money(cost)}</td>
              <td className="text-right"><button className="rounded border border-neutral-700 px-1.5 py-px text-[11px] text-neutral-300 hover:bg-neutral-800 disabled:opacity-40"
                disabled={busy(l.n)} onClick={(e) => { e.stopPropagation(); build(l.n); }}>{sl?.status === "done" ? "Rebuild" : "Build"}</button></td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function LectureView({ run, lecture, busy, model, act, select, onCall }: {
  run: Run; lecture: Lecture; busy: boolean; model: string; act: Act; select: (s: Selection) => void; onCall: (id: string) => void;
}) {
  const sl = run.scenes?.lectures[lecture.n];
  const script = run.script!.lectures[lecture.n];
  const lines = useMemo(() => linesOf(lecture.text ?? ""), [lecture.text]);
  const [pick, setPick] = useState<Pick>({ kind: "chapter", c: script.chapters[0]?.n ?? 1 });
  const [view, setView] = useState<"Beats" | "Compiler" | "Pictures" | "Calls">("Beats");
  const calls = (sl?.calls ?? []).map((id) => run.calls.find((c) => c.id === id)).filter((c): c is Call => !!c);
  const beats = script.chapters.flatMap((c) => c.beats.map((b) => ({ ...b, chapter: c.n })));
  const refused = beats.filter((b) => sl?.beats[b.n]?.errors?.length).length;
  const stale = sl?.scriptAt !== undefined && script.at !== undefined && sl.scriptAt < script.at;
  const pictures = sl?.compile?.pictures ?? [];
  return (
    <section className="space-y-2" data-testid="scenes-lecture-view">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-sm font-semibold text-neutral-100">Lecture {lecture.n}: {lecture.title}</span>
        <span className={TONE[sl?.status ?? "waiting"]}>{sl?.doing ?? sl?.status ?? "not built"}</span>
        {sl?.compile && <span className={sl.compile.status === "failed" ? "text-red-300" : sl.compile.status === "running" ? "text-sky-300" : "text-neutral-400"}>
          compile: {sl.compile.status}{sl.compile.seconds ? ` in ${sl.compile.seconds.toFixed(0)} s` : ""}{sl.compile.minutes ? ` · about ${sl.compile.minutes} min of video` : ""}</span>}
        {pictures.length > 0 && <span className="text-neutral-400">{pictures.length} AI picture(s) · {money(pictures.reduce((k, p) => k + (p.usd ?? 0), 0))}</span>}
        {sl?.compile?.missing?.length ? <button className="text-red-300 hover:underline" onClick={() => setView("Compiler")} data-testid="scenes-missing-count">
          ✗ {sl.compile.missing.length} AI picture(s) not made</button> : null}
        {sl?.regions && Object.keys(sl.regions).length ? Object.entries(sl.regions).filter(([, r]) => r).map(([c, r]) => (
          <span key={c} className="mono text-emerald-300" title={`chapter ${c}'s map region`}>ch {c}: {JSON.stringify(r)}</span>))
          : sl?.region && <span className="mono text-emerald-300" title="the map region">{JSON.stringify(sl.region)}</span>}
        <span className="ml-auto flex gap-1.5">
          <button className={`${btn} border-sky-700 bg-sky-800 text-white`} disabled={busy} data-testid="scenes-build-lecture"
            onClick={() => act({ action: "build", scope: "lecture", lecture: lecture.n, model })}>{sl?.status === "done" ? "Rebuild this lecture" : "Build this lecture"}</button>
          <button className={`${btn} border-neutral-700 text-neutral-200`} disabled={busy || !sl} onClick={() => act({ action: "compile", lecture: lecture.n })}>Compile</button>
          <button className={`${btn} border-red-800 text-red-200`} disabled={busy || !refused} data-testid="scenes-fix"
            onClick={() => act({ action: "fix", lecture: lecture.n, model })}>Mend {refused || ""} refused</button>
          <button className={`${btn} border-red-900 text-red-300 hover:bg-red-950`} disabled={busy || !sl || (!Object.keys(sl.beats).length && !sl.compile)} data-testid="scenes-reset-lecture"
            onClick={() => confirm(`Reset lecture ${lecture.n}'s scenes? Every beat's visuals, the Manim agent's work and pictures, the compile and the renders are deleted (a beat's own visual kinds are kept).`)
              && act({ action: "reset", lecture: lecture.n })}>Reset</button>
        </span>
      </div>
      {stale && <p className="text-xs text-amber-300">The script was rebuilt after these scenes: rebuild them so their beats match.</p>}
      {sl?.error && <p className="rounded border border-red-800 bg-red-950/40 p-2 text-xs text-red-200">Error: {sl.error}</p>}
      <nav className="flex gap-1 text-xs">
        {(["Beats", "Compiler", "Pictures", "Calls"] as const).map((v) => (
          <button key={v} onClick={() => setView(v)} className={`rounded-full border px-2.5 py-0.5 ${view === v ? "border-sky-600 bg-sky-950 text-sky-100" : "border-neutral-700 text-neutral-400 hover:text-neutral-200"}`}>
            {v}{v === "Compiler" && sl?.compile ? ` (${(sl.compile.errors.length + sl.compile.warnings.length + refused)})` : ""}{v === "Calls" && calls.length ? ` (${calls.length})` : ""}{v === "Pictures" ? ` (${Object.keys(run.scenes?.agentImages?.[lecture.n] ?? {}).length})` : ""}</button>
        ))}
      </nav>
      {view === "Beats" && (
        <div className="flex gap-3">
          <Outline run={run} lecture={lecture} lines={lines} pick={pick} setPick={setPick} />
          <div className="min-w-0 flex-1">
            {pick.kind === "chapter"
              ? <ChapterDetail key={`c${pick.c}`} run={run} lecture={lecture} c={pick.c} busy={busy} model={model} act={act} setPick={setPick} />
              : <BeatDetail key={`b${pick.n}`} run={run} lecture={lecture} n={pick.n} lines={lines} busy={busy} model={model} act={act} setPick={setPick} select={select} onCall={onCall} />}
          </div>
        </div>
      )}
      {view === "Compiler" && <CompilerView sl={sl} beats={beats} setPick={(p) => { setPick(p); setView("Beats"); }} />}
      {view === "Pictures" && <PicturesView run={run} lecture={lecture} onCall={onCall} setPick={(p) => { setPick(p); setView("Beats"); }} />}
      {view === "Calls" && <PromptView calls={calls} onCall={onCall} />}
    </section>
  );
}

/** The kinds a beat's operations are, as coloured dots. */
function KindDots({ ops }: { ops: Record<string, unknown>[] }) {
  const ks = [...new Set(ops.map((o) => kindOfOp(o) ?? "base").filter((k) => k !== "base"))];
  return <span className="flex gap-0.5">{ks.map((k) => <span key={k} title={kindById(k)?.label} className="inline-block h-2 w-2 rounded-full" style={{ background: KIND_COLOR[k] }} />)}</span>;
}

function Outline({ run, lecture, lines, pick, setPick }: { run: Run; lecture: Lecture; lines: string[]; pick: Pick; setPick: (p: Pick) => void }) {
  const sl = run.scenes?.lectures[lecture.n];
  const script = run.script!.lectures[lecture.n];
  return (
    <aside className="sticky top-0 w-60 shrink-0 self-start overflow-y-auto" style={{ maxHeight: "75vh" }} data-testid="scenes-outline">
      {script.chapters.map((ch) => {
        const cr = sl?.chapters?.[ch.n];
        return (
          <div key={ch.n} className="mb-1.5">
            <button onClick={() => setPick({ kind: "chapter", c: ch.n })} data-testid="scenes-chapter"
              className={`flex w-full items-baseline gap-1 rounded px-1.5 py-1 text-left text-xs ${pick.kind === "chapter" && pick.c === ch.n ? "bg-sky-950 text-sky-100" : "text-neutral-100 hover:bg-neutral-800"}`}>
              <span className="text-neutral-500">{ch.n}.</span><span className="min-w-0 flex-1 truncate font-semibold">{ch.title}</span>
              <span className={`text-[9px] ${ch.map ? "text-emerald-400" : "text-neutral-500"}`} title="Every chapter is on the board; the map comes in for its beats that point at places">{ch.map ? "board · map" : "board"}</span>
              {cr && <span className={`text-[9px] ${TONE[cr.status]}`} title="chapter render">▶</span>}
            </button>
            <ol className="ml-3 border-l border-neutral-800">
              {ch.beats.map((b) => {
                const sb = sl?.beats[b.n];
                const on = pick.kind === "beat" && pick.n === b.n;
                return (
                  <li key={b.n}>
                    <button onClick={() => setPick({ kind: "beat", n: b.n })} data-testid="scenes-beat"
                      className={`flex w-full items-center gap-1.5 px-1.5 py-0.5 text-left text-[11px] ${on ? "bg-sky-950 text-sky-100" : "text-neutral-300 hover:bg-neutral-800"}`}>
                      <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${sb ? DOT[sb.status] : "bg-neutral-700"}`} />
                      <span className="w-6 shrink-0 text-neutral-500">#{b.n}</span>
                      <span className="min-w-0 flex-1 truncate">{lines[b.lines[0] - 1]}</span>
                      {sb?.errors?.length ? <span className="text-red-400" title={sb.errors.join("\n")}>✗</span> : null}
                      {sb?.missing?.length ? <span className="text-red-400" title={`AI picture(s) not made: ${sb.missing.map((m) => m.what).join(", ")}`}>⊘</span> : null}
                      {sb?.kinds ? <span className="text-amber-300" title="its own visual kinds">◐</span> : null}
                      {sb?.edited ? <span className="text-violet-300" title="changed by hand">✎</span> : null}
                      {sb?.agent ? <span className={sb.agent.status === "running" ? "animate-pulse text-sky-300" : sb.agent.status === "failed" ? "text-red-400" : "text-cyan-300"} title={`the Manim agent: ${sb.agent.status}`}>◆</span> : null}
                      {sb?.render?.status === "done" ? <span className="text-emerald-400" title="rendered">▣</span> : sb?.render?.status === "running" ? <span className="animate-pulse text-sky-300">▣</span> : null}
                      <KindDots ops={sb?.ops ?? []} />
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        );
      })}
    </aside>
  );
}

/** The run's look, or another, for a render. */
function LookSelect({ style, art, setStyle, setArt }: { style: string; art: string; setStyle: (s: string) => void; setArt: (a: string) => void }) {
  return (
    <>
      <select className="rounded border border-neutral-700 bg-neutral-900 px-1.5 py-1 text-xs text-neutral-100" value={style} onChange={(e) => setStyle(e.target.value)} data-testid="render-style">
        {STYLES.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <select className="rounded border border-neutral-700 bg-neutral-900 px-1.5 py-1 text-xs text-neutral-100" value={art} onChange={(e) => setArt(e.target.value)}>
        {ART_STYLES.map((a) => <option key={a.id} value={a.id}>{a.name} art</option>)}
      </select>
    </>
  );
}

function RenderState({ r, what }: { r?: SceneRender; what: string }) {
  if (!r) return <p className="text-xs text-neutral-500">Not rendered yet: render {what} to see it (silent, low quality, a few seconds a beat).</p>;
  return (
    <div>
      <p className="text-[11px] text-neutral-400">
        <span className={TONE[r.status]}>{r.status === "running" ? "rendering…" : r.status}</span> · {styleOf(r.style).name}, {artOf(r.art).name} art
        {r.seconds ? ` · ${r.seconds.toFixed(0)} s` : r.started && r.status === "running" ? ` · ${seconds(r.started, Date.now())}` : ""}
        {r.images && r.images.asked > 0 ? ` · AI pictures: ${r.images.made} made, ${r.images.cached} already made${r.images.failed ? `, ${r.images.failed} failed` : ""}` : ""}
        {r.error && <span className="block whitespace-pre-wrap text-red-300">{r.error}</span>}
      </p>
      {r.status === "done" && (r.pictures?.length ? <PictureStrip pictures={r.pictures} /> : <MissingPictures missing={r.missing} note="left out of this render" />)}
    </div>
  );
}

const ROLE_ORDER = (role?: string) => (role?.includes("gallery") ? 0 : role?.includes("stage") ? 1 : 2);

/** The AI pictures of a beat, as the last compile got them, like the Manim agent's: each picture (enlarged on a click),
 * what it shows, its caption and place (a gallery's first), made now (and its cost), made before, or not made and the
 * image model's error; the prompt the image model was sent and its model. */
/** What the decision model said about a picture: shown again, drawn to match one made before, or drawn fresh. */
function Decision({ d, onBig, onCall }: { d: NonNullable<BeatPicture["decision"]>; onBig: (url: string) => void; onCall?: (id: string) => void }) {
  const tone = d.action === "reuse" ? "text-sky-300" : d.action === "match" ? "text-violet-300" : "text-neutral-300";
  const top = Object.entries(d.probabilities ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 3);
  return (
    <div className="mt-1 rounded border border-neutral-800 bg-neutral-950/60 p-1" data-testid="picture-decision">
      <p className={tone}>
        {d.action === "reuse" ? "shown again: a picture made before" : d.action === "match" ? "drawn anew to match a picture made before" : "drawn fresh"}
        {d.confidence != null ? ` · ${Math.round(d.confidence * 100)}%` : ""}{d.unsure ? " (unsure: not taken as it said)" : ""}
      </p>
      <p className="text-neutral-500">{d.model}{d.askedNow ? "" : " · answer kept from before"} · asked about {d.candidates.length} picture(s)
        {d.call && onCall ? <> · <button className="text-sky-300 hover:underline" onClick={() => onCall(d.call!)}>its call</button></> : null}</p>
      {d.error && <p className="text-red-300">{d.error}</p>}
      {d.pickedUrl && (
        // eslint-disable-next-line @next/next/no-img-element
        <img alt="the picture it chose" src={d.pickedUrl} onClick={() => onBig(d.pickedUrl!)} className="mt-0.5 h-12 cursor-zoom-in rounded bg-neutral-900 object-contain" title={d.candidates.find((c) => c.key === d.picked)?.what} />
      )}
      <details>
        <summary className="cursor-pointer text-neutral-500">what it was asked</summary>
        <ol className="mt-0.5 space-y-0.5 text-neutral-400">
          {d.candidates.map((c, i) => (
            <li key={c.key} className={c.key === d.picked ? "text-neutral-100" : ""}>{i}. {c.what}{c.reusable ? "" : " (only to match)"}</li>
          ))}
        </ol>
        {top.length > 0 && <p className="mt-0.5 text-neutral-500">{top.map(([k, v]) => `${k} ${Math.round(v * 100)}%`).join(" · ")}</p>}
      </details>
    </div>
  );
}

function BeatPictures({ pictures, onRetry, busy, onCall }: { pictures: BeatPicture[]; onRetry: () => void; busy: boolean; onCall?: (id: string) => void }) {
  const [big, setBig] = useState<string | null>(null);
  const sorted = [...pictures].sort((a, b) => ROLE_ORDER(a.role) - ROLE_ORDER(b.role));
  const groups = [...new Set(sorted.map((p) => (p.status === "failed" ? "not made" : p.role ?? "on the beat")))];
  const failed = pictures.filter((p) => p.status === "failed").length;
  const made = pictures.filter((p) => p.status === "made");
  return (
    <section className="rounded border border-pink-900/60 bg-pink-950/10 p-2" data-testid="scenes-beat-pictures">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-pink-300">AI pictures</span>
        <span className="text-neutral-400">{pictures.length - failed} on the beat{made.length ? ` · ${made.length} made now (${money(made.reduce((k, p) => k + (p.usd ?? 0), 0))})` : ""}
          {pictures.length - failed - made.length ? ` · ${pictures.length - failed - made.length} made before` : ""}</span>
        {failed > 0 && <span className="text-red-300">✗ {failed} not made: left out of the scene (a gallery with none made is left out whole)</span>}
        {failed > 0 && <button className={`${btn} ml-auto border-pink-800 text-pink-200`} disabled={busy} onClick={onRetry}>Ask the image model again (compile)</button>}
      </div>
      {groups.map((g) => (
        <div key={g} className="mt-2">
          <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">{g === "in a gallery" ? `the gallery (${sorted.filter((p) => p.role === g && p.status !== "failed").length})` : g}</p>
          <div className="flex flex-wrap gap-2">
            {sorted.filter((p) => (p.status === "failed" ? "not made" : p.role ?? "on the beat") === g).map((p, i) => (
              <div key={i} className={`w-44 rounded border p-1 text-[10px] ${p.status === "failed" ? "border-red-900 bg-red-950/30" : "border-neutral-800"}`} data-testid="scenes-beat-picture">
                {p.url
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img alt={p.what} src={p.url} onClick={() => setBig(p.url!)} className="h-28 w-full cursor-zoom-in rounded bg-[repeating-conic-gradient(#262626_0_25%,#171717_0_50%)] bg-[length:16px_16px] object-contain" />
                  : <div className="flex h-28 items-center justify-center rounded bg-red-950/40 text-center text-red-300">✗ not made</div>}
                <p className="mt-0.5 line-clamp-2 font-medium text-neutral-200" title={p.what}>{p.what}</p>
                {p.caption && <p className="text-neutral-400">caption: “{p.caption}”</p>}
                <p className={p.status === "failed" ? "text-red-300" : p.status === "made" ? "text-emerald-300" : "text-neutral-400"}>
                  {p.status === "failed" ? "not made" : p.status === "made" ? `made now${p.usd ? ` · ${money(p.usd)}` : ""}` : "made before (reused)"}{p.model ? ` · ${p.model}` : ""}</p>
                {p.error && <p className="whitespace-pre-wrap text-red-200">{p.error}</p>}
                {p.decision && <Decision d={p.decision} onBig={setBig} onCall={onCall} />}
                {p.prompt && <details><summary className="cursor-pointer text-neutral-500">the prompt</summary><p className="mt-0.5 max-h-40 overflow-auto whitespace-pre-wrap text-neutral-300">{p.prompt}</p></details>}
              </div>
            ))}
          </div>
        </div>
      ))}
      {big && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6" onClick={() => setBig(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img alt="enlarged" src={big} className="max-h-full max-w-full rounded bg-[repeating-conic-gradient(#262626_0_25%,#171717_0_50%)] bg-[length:16px_16px]" />
        </div>
      )}
    </section>
  );
}

/** A render's AI pictures in a row: each one's thumbnail, or not made and why. */
function PictureStrip({ pictures }: { pictures: BeatPicture[] }) {
  const failed = pictures.filter((p) => p.status === "failed");
  return (
    <div className="mt-1" data-testid="scenes-render-pictures">
      <div className="flex flex-wrap gap-1">
        {pictures.filter((p) => p.url).map((p, i) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={i} alt={p.what} title={`${p.what}${p.role ? ` (${p.role})` : ""}: ${p.status === "made" ? "made now" : "made before"}`} src={p.url}
            className={`h-10 w-14 rounded border object-contain ${p.status === "made" ? "border-emerald-700" : "border-neutral-800"} bg-[repeating-conic-gradient(#262626_0_25%,#171717_0_50%)] bg-[length:8px_8px]`} />
        ))}
      </div>
      {failed.length > 0 && <MissingPictures compact missing={failed.map((p) => ({ what: p.what, error: p.error, beat: p.beat }))} note="left out of this render" />}
    </div>
  );
}

/** AI pictures the image model could not make, so the engine left them out of the scene (a gallery none of whose
 * pictures were made is left out whole), each with the image model's error. */
function MissingPictures({ missing, note, compact }: { missing?: MissingPicture[]; note: string; compact?: boolean }) {
  if (!missing?.length) return null;
  return (
    <div className="mt-1 rounded border border-red-900 bg-red-950/30 p-1.5 text-[11px] text-red-200" data-testid="scenes-missing">
      <p className="font-semibold">{missing.length} AI picture(s) not made: {note}{compact ? "" : " (a gallery with none of its pictures is left out whole)"}</p>
      <ul className="mt-0.5 space-y-0.5">
        {missing.map((m, i) => (
          <li key={i}>✗ “{m.what}”{m.beat !== undefined ? <span className="text-red-300/70"> (beat #{m.beat})</span> : null}: <span className="text-red-100">{m.error ?? "the image model gave no picture (no reason given)"}</span></li>
        ))}
      </ul>
      {!compact && <p className="mt-0.5 text-red-300/80">Compile (or render) again to ask the image model again; check the image model in the Models tab if it keeps failing.</p>}
    </div>
  );
}

function Issues({ issues, fixed }: { issues?: string[]; fixed?: string[] }) {
  if (!issues?.length && !fixed?.length) return null;
  return (
    <ul className="mt-1 space-y-0.5 text-[11px]">
      {(issues ?? []).map((x, i) => <li key={`i${i}`} className="text-amber-300">⚠ on screen: {x}</li>)}
      {(fixed ?? []).map((x, i) => <li key={`f${i}`} className="text-neutral-400">✎ mended on screen: {x}</li>)}
    </ul>
  );
}

function ChapterDetail({ run, lecture, c, busy, model, act, setPick }: {
  run: Run; lecture: Lecture; c: number; busy: boolean; model: string; act: Act; setPick: (p: Pick) => void;
}) {
  const st = run.scenes;
  const sl = st?.lectures[lecture.n];
  const ch = run.script!.lectures[lecture.n].chapters.find((x) => x.n === c)!;
  const r = sl?.chapters?.[c];
  const [style, setStyle] = useState(st?.look.style ?? "atlas");
  const [art, setArt] = useState(st?.look.art ?? "auto");
  const built = ch.beats.filter((b) => sl?.beats[b.n]?.ops.length).length;
  const ownKinds = sl?.chapterKinds?.[c];
  const [only, setOnly] = useState<NonNullable<NonNullable<typeof r>["beats"]>[number] | null>(null);
  return (
    <div className="space-y-2" data-testid="scenes-chapter-detail">
      <div className="rounded border border-neutral-800 bg-neutral-900/40 p-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-sm font-semibold text-neutral-100">Chapter {ch.n}: {ch.title}</span>
          <span className={`rounded px-1.5 py-px text-[10px] ${ch.map ? "bg-emerald-950 text-emerald-300" : "bg-neutral-800 text-neutral-300"}`}>{ch.map ? "on a map" : "on a board"}</span>
          <span className="text-[11px] text-neutral-500">{ch.beats.length} beats · {built} with visuals</span>
        </div>
        <p className="text-[11px] italic text-neutral-400">title card: “{ch.narration}”</p>
        <div className="mt-2 rounded border border-neutral-800 p-2" data-testid="scenes-chapter-kinds">
          <div className="mb-1 flex items-center gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-400">Visuals this chapter may use</p>
            <span className="text-[11px] text-neutral-500">{ownKinds ? `its own (${ownKinds.length})` : `the run's (${st?.kinds.length ?? 0})`} · a beat&apos;s own choice wins</span>
            {ownKinds && <button className="ml-auto text-[11px] text-sky-300 hover:underline" onClick={() => act({ action: "chapterKinds", lecture: lecture.n, chapter: c, kinds: null })}>same as the run</button>}
          </div>
          <KindToggles compact kinds={ownKinds ?? st?.kinds ?? []} onChange={(k) => act({ action: "chapterKinds", lecture: lecture.n, chapter: c, kinds: k })} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          <button className={`${btn} border-sky-700 text-sky-200 hover:bg-sky-950`} disabled={busy} data-testid="scenes-build-chapter"
            onClick={() => act({ action: "build", scope: "chapter", lecture: lecture.n, chapter: c, model })}>{built ? "Build this chapter again" : "Build this chapter"}</button>
          <button className={`${btn} border-red-900 text-red-300 hover:bg-red-950`} disabled={busy || (!built && !r) || r?.status === "running"} data-testid="scenes-reset-chapter"
            onClick={() => confirm(`Reset chapter ${c}'s scenes? Its beats' visuals, the Manim agent's work on them and its renders are deleted (pictures stay for the lecture; a beat's own visual kinds are kept).`)
              && act({ action: "reset", lecture: lecture.n, chapter: c })}>Reset this chapter</button>
          <span className="mx-1 h-4 w-px bg-neutral-700" />
          <LookSelect style={style} art={art} setStyle={setStyle} setArt={setArt} />
          <button className={`${btn} border-emerald-700 bg-emerald-800 text-white`} disabled={!built || r?.status === "running"} data-testid="scenes-render-chapter"
            onClick={() => act({ action: "render", lecture: lecture.n, chapter: c, style, art })}>{r?.status === "running" ? "Rendering…" : r ? "Render the chapter again" : "Render the chapter"}</button>
        </div>
      </div>
      <ChapterJson run={run} lecture={lecture.n} c={c} act={act} disabled={busy || !built} />
      <RenderState r={r} what="the chapter" />
      {r?.status === "done" && r.audio && <p className="text-[11px] text-emerald-300" data-testid="scenes-render-voiced">With its voice (spoken first): heard as it plays.</p>}
      {r?.status === "done" && r.ir && r.assets && (
        <div className="max-w-3xl" data-testid="scenes-chapter-player">
          {only && <p className="mb-1 text-[11px] text-sky-300">Playing beat #{only.n} only · <button className="underline" onClick={() => setOnly(null)}>the whole chapter</button></p>}
          <IRPlayer src={r.ir} assets={r.assets} audio={r.audio} spoken={r.spoken} range={only ? [only.from ?? 0, only.to ?? (r.frames ?? 1) - 1] : undefined} />
        </div>
      )}
      {r?.status === "done" && !r.ir && r.video && <video key={r.video} src={r.video} controls className="w-full max-w-3xl rounded border border-neutral-800 bg-black" data-testid="scenes-chapter-video" />}
      {r?.beats?.length ? (
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-3" data-testid="scenes-filmstrip">
          {r.beats.map((b) => (
            <div key={b.n} className={`rounded border p-1 text-left ${only?.n === b.n ? "border-sky-500" : "border-neutral-800 hover:border-sky-600"}`}>
              <button className="block w-full" title="play this beat in the player above" onClick={() => setOnly(b)}>
                {r.ir && r.assets && b.to !== undefined ? <FrameStill src={r.ir} assets={r.assets} frame={b.to} />
                  // eslint-disable-next-line @next/next/no-img-element
                  : b.still ? <img alt={`beat ${b.n}`} src={b.still} className="w-full rounded" /> : <div className="aspect-video rounded bg-neutral-900" />}
              </button>
              <span className="flex items-center gap-1 text-[10px] text-neutral-400">▶ #{b.n} · {b.start.toFixed(1)}–{b.end.toFixed(1)} s{b.issues?.length ? <span className="text-amber-300"> · ⚠ {b.issues.length}</span> : null}
                <button className="ml-auto text-sky-300 hover:underline" onClick={() => setPick({ kind: "beat", n: b.n })}>open</button></span>
            </div>
          ))}
        </div>
      ) : null}
      <ul className="space-y-1">
        {ch.beats.map((b) => {
          const sb = sl?.beats[b.n];
          return (
            <li key={b.n} className="flex cursor-pointer gap-2 rounded border border-neutral-900 px-2 py-1 text-xs hover:bg-neutral-900" onClick={() => setPick({ kind: "beat", n: b.n })}>
              <span className="w-8 text-neutral-500">#{b.n}</span>
              <span className="min-w-0 flex-1 text-neutral-300">{b.show || "—"}</span>
              <span className="flex flex-wrap justify-end gap-1">{(sb?.ops ?? []).map((o, i) => <OpChip key={i} op={o} />)}{sb?.errors?.length ? <span className="text-red-300">✗ refused</span> : null}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function OpChip({ op }: { op: Record<string, unknown> }) {
  const k = kindOfOp(op) ?? "base";
  return <span className="rounded border px-1 text-[10px]" style={{ borderColor: KIND_COLOR[k], color: KIND_COLOR[k] }}>{String(op.op)}{op.op === "picture" ? `:${pictureWord(op)}` : ""}</span>;
}

const pictureWord = (op: Record<string, unknown>) => Array.isArray(op.items) ? "gallery" : op.figure ? "figure" : op.draw ? "drawing" : "illustration";

/** An operation in words: what it puts on screen. */
function opWords(op: Record<string, unknown>): string {
  const s = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));
  switch (op.op) {
    case "panel": return `heading “${s(op.title)}”${op.sub ? ` · ${s(op.sub)}` : ""}`;
    case "fact": return `key point “${s(op.text)}”`;
    case "picture": return Array.isArray(op.items) ? `gallery of ${op.items.length}: ${(op.items as Record<string, unknown>[]).map((i) => i.caption ?? i.generate ?? i.figure).join(", ")}`
      : op.figure ? `book figure ${s(op.figure)}${op.caption ? ` — ${s(op.caption)}` : ""}` : op.draw ? `AI diagram: ${s(op.draw)}${Array.isArray(op.labels) ? ` [${(op.labels as string[]).join(", ")}]` : ""}`
        : `AI illustration: ${s(op.generate)}${op.scene ? " (scene)" : ""}${Array.isArray(op.labels) ? ` [${(op.labels as string[]).join(", ")}]` : ""}`;
    case "diagram": return `${s(op.kind ?? "flow")} diagram “${s(op.id)}”: ${(Array.isArray(op.nodes) ? op.nodes as Record<string, unknown>[] : []).map((n) => n.label).join(" → ")}`;
    case "reveal": return `reveal ${(op.nodes as string[] | undefined)?.join(", ")} in “${s(op.diagram)}”`;
    case "focus": return `focus ${s(op.node)} in “${s(op.diagram)}”`;
    case "zoom": return op.node ? `zoom on ${s(op.node)} in “${s(op.diagram)}”` : `zoom back out of “${s(op.diagram)}”`;
    case "timeline": return `timeline: ${(Array.isArray(op.events) ? op.events as unknown[][] : []).map((e) => `${e[0]} ${e[1]}`).join(" · ")}`;
    case "define": return `define “${s(op.term)}”: ${s(op.meaning)}`;
    case "compare": return `compare: ${(Array.isArray(op.columns) ? op.columns as Record<string, unknown>[] : []).map((c) => c.title).join(" vs ")}`;
    case "equation": return `equation ${s(op.tex)}`;
    case "molecule": return `molecule ${s(op.name)}`;
    case "manim": return `Manim figure “${s(op.id)}” (${String(op.code ?? "").split("\n").length} lines of code)`;
    case "question": return `question: ${s(op.text)}`;
    case "stat": return `stat ${s(op.value)} — ${s(op.label)}`;
    case "bars": return `bar chart of ${(op.items as unknown[] | undefined)?.length ?? 0}`;
    case "marker": return `marker ${s(op.place ?? op.lonlat)}${op.label ? ` “${s(op.label)}”` : ""}`;
    case "state": return `shade ${s(op.name)}`;
    case "river": return `river ${s(op.name)}`;
    case "arrow": case "path": case "journey": return `${s(op.op)} ${s(op.points ?? op.stops)}`;
    case "empire": return `${s(op.name)} in ${s(op.year)}`;
    case "work": return `working “${s(op.id)}”: ${(op.lines as string[] | undefined)?.join(" · ")}`;
    case "quote": return `quote “${s(op.text)}” — ${s(op.who)}`;
    default: return JSON.stringify(Object.fromEntries(Object.entries(op).filter(([k]) => k !== "op"))).slice(0, 140);
  }
}

function BeatDetail({ run, lecture, n, lines, busy, model, act, setPick, select, onCall }: {
  run: Run; lecture: Lecture; n: number; lines: string[]; busy: boolean; model: string; act: Act; setPick: (p: Pick) => void; select: (s: Selection) => void; onCall: (id: string) => void;
}) {
  const st = run.scenes;
  const sl: SceneLecture | undefined = st?.lectures[lecture.n];
  const script = run.script!.lectures[lecture.n];
  const all = script.chapters.flatMap((c) => c.beats.map((b) => ({ ...b, chapter: c })));
  const at = all.findIndex((b) => b.n === n);
  const b = all[at];
  const sb: SceneBeat | undefined = sl?.beats[n];
  const [style, setStyle] = useState(st?.look.style ?? "atlas");
  const [art, setArt] = useState(st?.look.art ?? "auto");
  const [editing, setEditing] = useState(false);
  const [json, setJson] = useState("");
  const [note, setNote] = useState("");
  const [bad, setBad] = useState<string | null>(null);
  const chapterRender = b ? sl?.chapters?.[b.chapter.n] : undefined;
  const fromChapter = chapterRender?.status === "done" ? chapterRender.beats?.find((x) => x.n === n) : undefined;
  const r = sb?.render;
  const known = b ? lectureFigures(run, lecture.n) : [];
  const figures = b ? beatFigures(b).map((id) => known.find((f) => f.id === id)).filter((f): f is NonNullable<typeof f> => !!f) : [];
  const ownKinds = sb?.kinds;
  const chapterKinds = b ? sl?.chapterKinds?.[b.chapter.n] : undefined;
  const inherited = chapterKinds ?? st?.kinds ?? [];
  if (!b) return null;
  return (
    <div className="space-y-2.5" data-testid="scenes-beat-detail">
      <div className="flex items-center gap-2 text-xs">
        <button className="rounded border border-neutral-700 px-1.5 text-neutral-300 disabled:opacity-30" disabled={at <= 0} onClick={() => setPick({ kind: "beat", n: all[at - 1].n })}>‹ prev</button>
        <span className="font-semibold text-neutral-100">Beat #{n}</span>
        <button className="text-sky-300 hover:underline" onClick={() => setPick({ kind: "chapter", c: b.chapter.n })}>chapter {b.chapter.n}: {b.chapter.title}</button>
        <span className="text-neutral-500">sentences {b.lines.join(", ")}</span>
        <span className={sb ? TONE[sb.status] : "text-neutral-500"}>{sb?.status ?? "not built"}</span>
        <button className="ml-auto rounded border border-neutral-700 px-1.5 text-neutral-300 disabled:opacity-30" disabled={at >= all.length - 1} onClick={() => setPick({ kind: "beat", n: all[at + 1].n })}>next ›</button>
      </div>
      <div className="rounded border border-neutral-800 bg-neutral-900/40 p-2 text-xs">
        <p className="text-sm text-neutral-100">{b.lines.map((k) => lines[k - 1]).join(" ")}</p>
        <p className="mt-1 text-neutral-400"><span className="text-neutral-500">the script&apos;s plan:</span> {b.show || "—"}</p>
        {figures.map((figure) => (
          <button key={figure.id} className="mt-1 flex items-center gap-2 text-left" onClick={() => select({ kind: "block", id: figure.id })}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img alt={figure.id} className="h-12 rounded bg-white object-contain" src={run.generation?.figures[figure.id]?.status === "done" && run.generation.figures[figure.id].url ? run.generation.figures[figure.id].url : `/api/documents/${run.documentId}/figure/${encodeURIComponent(figure.id)}`} />
            <span className="text-neutral-300">figure {figure.id} · {figure.way}{figure.ready ? "" : " · not made yet (the book's picture is used)"}
              {figure.beats.length > 1 ? <span className="text-neutral-500"> · also on beat{figure.beats.length > 2 ? "s" : ""} {figure.beats.filter((x) => x !== n).map((x) => `#${x}`).join(", ")}</span> : null}</span>
          </button>
        ))}
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-400">On screen ({sb?.ops.length ?? 0} operations)</p>
            {sb?.edited && <span className="text-[10px] text-violet-300">✎ changed by hand</span>}
            <button className="ml-auto text-[11px] text-sky-300 hover:underline" onClick={() => { setJson(JSON.stringify(sb?.ops ?? [], null, 2)); setBad(null); setEditing(!editing); }}>
              {editing ? "cancel" : "edit as JSON"}</button>
          </div>
          {editing ? (
            <div className="space-y-1">
              <textarea className="mono h-64 w-full rounded border border-neutral-700 bg-neutral-950 p-2 text-[11px] text-neutral-100" value={json} onChange={(e) => setJson(e.target.value)} data-testid="scenes-json" />
              {bad && <p className="text-[11px] text-red-300">{bad}</p>}
              <div className="flex flex-wrap gap-1.5">
                {[false, true].map((render) => (
                  <button key={String(render)} className={`${btn} border-violet-700 ${render ? "bg-emerald-800" : "bg-violet-800"} text-white`} disabled={busy}
                    data-testid={render ? "scenes-json-rerender" : "scenes-json-save"} onClick={async () => {
                      let ops: unknown;
                      try { ops = JSON.parse(json); } catch (e) { setBad(`not JSON: ${(e as Error).message}`); return; }
                      if (await act({ action: "edit", lecture: lecture.n, beat: n, ops, render })) setEditing(false);
                    }}>{render ? "Save and re-render this beat" : "Save and compile"}</button>
                ))}
              </div>
            </div>
          ) : sb?.ops.length ? (
            <ol className="space-y-1" data-testid="scenes-ops">
              {sb.ops.map((o, i) => {
                const k = kindOfOp(o) ?? "base";
                return (
                  <li key={i} className="rounded border-l-2 bg-neutral-900 px-2 py-1 text-xs" style={{ borderColor: KIND_COLOR[k] }}>
                    <span className="mr-1.5 rounded px-1 text-[10px]" style={{ background: `${KIND_COLOR[k]}22`, color: KIND_COLOR[k] }}>{k === "base" ? "words" : kindById(k)?.label}</span>
                    <span className="text-neutral-200">{opWords(o)}</span>
                  </li>
                );
              })}
            </ol>
          ) : <p className="text-xs text-neutral-500">{sb?.status === "running" ? "Being written…" : sb ? "Nothing new on screen: the last visual stays up." : "Not built yet."}</p>}
          {sb?.dropped?.length ? <ul className="text-[11px] text-amber-300">{sb.dropped.map((d, i) => <li key={i}>✂ taken out: {d}</li>)}</ul> : null}
          {!sb?.pictures?.length && <MissingPictures missing={sb?.missing} note="left out of the scene" />}
          {sb?.errors?.length ? <ul className="rounded border border-red-900 bg-red-950/30 p-1.5 text-[11px] text-red-200" data-testid="scenes-errors">{sb.errors.map((e, i) => <li key={i}>✗ {e}</li>)}</ul> : null}
          {sb?.notes?.length ? <ul className="text-[11px] text-neutral-400">{sb.notes.map((e, i) => <li key={i}>{/^fixed/i.test(e) ? "✎" : "i"} {e.replace(/^fixed:\s*/i, "")}</li>)}</ul> : null}

          <div className="rounded border border-neutral-800 p-2">
            <div className="mb-1 flex items-center gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-400">Visuals this beat may use</p>
              {ownKinds ? <button className="ml-auto text-[11px] text-sky-300 hover:underline" onClick={() => act({ action: "beatKinds", lecture: lecture.n, beat: n, kinds: null })}>same as the {chapterKinds ? "chapter" : "run"}</button>
                : <span className="ml-auto text-[11px] text-neutral-500">{chapterKinds ? `the chapter's (${chapterKinds.length})` : `the run's (${st?.kinds.length ?? 0})`}</span>}
            </div>
            <KindToggles compact kinds={ownKinds ?? inherited} onChange={(k) => act({ action: "beatKinds", lecture: lecture.n, beat: n, kinds: k })} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <input className="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-100" placeholder="a note for the model (optional): “a timeline instead”, “show the granary”"
              value={note} onChange={(e) => setNote(e.target.value)} />
            <button className={`${btn} border-sky-700 bg-sky-800 text-white`} disabled={busy} data-testid="scenes-build-beat"
              onClick={() => act({ action: "build", scope: "beat", lecture: lecture.n, beat: n, model, note: note || undefined })}>{sb?.ops.length ? "Build this beat again" : "Build this beat"}</button>
          </div>
          {sb?.calls.length ? <p className="flex flex-wrap gap-1 text-[10px]">{sb.calls.map((id) => <button key={id} className="rounded border border-neutral-700 px-1 text-neutral-400 hover:bg-neutral-800" onClick={() => onCall(id)}>call {id}</button>)}</p> : null}
        </div>

        <div className="space-y-2" data-testid="scenes-beat-render">
          <div className="flex flex-wrap items-center gap-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-400">Render</p>
            <LookSelect style={style} art={art} setStyle={setStyle} setArt={setArt} />
            <button className={`${btn} border-emerald-700 bg-emerald-800 text-white`} disabled={!sb?.ops.length && !b.chapter.beats.some((x) => sl?.beats[x.n]?.ops.length) || r?.status === "running"}
              data-testid="scenes-render-beat" onClick={() => act({ action: "render", lecture: lecture.n, chapter: b.chapter.n, beat: n, style, art })}>
              {r?.status === "running" ? "Rendering…" : r ? "Render again" : "Render this beat"}</button>
          </div>
          <p className="text-[10px] text-neutral-500">The chapter is recorded up to this beat (so what is on the board before it is there) and played from this beat, in v1&apos;s web player.</p>
          <RenderState r={r} what="this beat" />
          {r?.status === "done" && (
            <>
              {r.ir && r.assets ? (
                <div data-testid="scenes-beat-player">
                  <IRPlayer src={r.ir} assets={r.assets} audio={r.audio} spoken={r.spoken} range={r.range} compact />
                  {r.range && r.range[0] > 0 && <details className="mt-1"><summary className="cursor-pointer text-[11px] text-sky-300">the chapter up to here</summary>
                    <IRPlayer src={r.ir} assets={r.assets} audio={r.audio} spoken={r.spoken} compact /></details>}
                </div>
              ) : (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {r.still && <img alt={`beat ${n}, last frame`} src={r.still} className="w-full rounded border border-neutral-800" data-testid="scenes-still" />}
                  {r.clip && <video key={r.clip} src={r.clip} controls loop className="w-full rounded border border-neutral-800 bg-black" />}
                </>
              )}
              {r.blockers?.length ? <p className="text-[11px] text-amber-300">The program leaves out: {r.blockers.join("; ")}</p> : null}
              <Issues issues={r.issues} fixed={r.fixed} />
            </>
          )}
          {(!r || r.status !== "done") && fromChapter && (chapterRender?.ir || fromChapter.still) && (
            <div>
              <p className="text-[11px] text-neutral-500">From the chapter&apos;s render:</p>
              {chapterRender?.ir && chapterRender.assets && fromChapter.from !== undefined
                ? <IRPlayer src={chapterRender.ir} assets={chapterRender.assets} audio={chapterRender.audio} spoken={chapterRender.spoken} range={[fromChapter.from, fromChapter.to ?? fromChapter.from]} compact />
                // eslint-disable-next-line @next/next/no-img-element
                : <img alt={`beat ${n} in the chapter`} src={fromChapter.still} className="w-full rounded border border-neutral-800" />}
              <Issues issues={fromChapter.issues} fixed={fromChapter.fixed} />
            </div>
          )}
        </div>
      </div>
      {sb?.pictures?.length ? <BeatPictures pictures={sb.pictures} onRetry={() => act({ action: "compile", lecture: lecture.n })} busy={busy} onCall={onCall} /> : null}
      <AgentSection run={run} lecture={lecture} n={n} sb={sb} busy={busy} act={act} onCall={onCall}
        manimOn={(ownKinds ?? inherited).includes("manim")} />
    </div>
  );
}

const STEP_LOOK = { think: { icon: "💭", tone: "text-neutral-300" }, image: { icon: "🖼", tone: "text-pink-300" }, check: { icon: "⚙", tone: "text-sky-300" }, preview: { icon: "▶", tone: "text-sky-300" },
  finish: { icon: "✓", tone: "text-emerald-300" }, error: { icon: "✗", tone: "text-red-300" } } as const;

/** The Manim agent on this beat: ask it (with words of your own), and every step it took: its words, the pictures it
 * made, each check of its code (the compiler's errors or "it runs", the code; nothing is rendered in its loop), the code
 * it settled on. Render the beat (above) to see the figure. */
function AgentSection({ run, lecture, n, sb, busy, act, onCall, manimOn }: {
  run: Run; lecture: Lecture; n: number; sb?: SceneBeat; busy: boolean; act: Act; onCall: (id: string) => void; manimOn: boolean;
}) {
  const a = sb?.agent;
  const [ask, setAsk] = useState("");
  const [big, setBig] = useState<string | null>(null);
  const plan = sb?.ops.find((o) => o.op === "manim")?.plan as string | undefined;
  const images = run.scenes?.agentImages?.[lecture.n] ?? {};
  const turns = [...new Set((a?.steps ?? []).map((x) => x.turn))];
  return (
    <section className="rounded border border-cyan-900/70 bg-cyan-950/10 p-2" data-testid="scenes-agent">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-cyan-300">Manim agent</span>
        {a ? (
          <>
            <span className={a.status === "failed" ? "text-red-300" : a.status === "running" ? "animate-pulse text-sky-300" : a.status === "done" ? "text-emerald-300" : "text-amber-300"}>{a.status === "running" ? "working…" : a.status}</span>
            <span className="text-neutral-400">figure “{a.id}” · {a.turns} turn(s) · {a.images.length} picture(s) · {a.steps.filter((x) => x.kind === "check" || x.kind === "preview" || (x.kind === "finish" && x.args?.code !== undefined && x.seconds !== undefined)).length} code check(s)</span>
            <span className="mono text-neutral-500">{a.model} · images {a.imageModel}</span>
            <span className="text-neutral-400">{seconds(a.started, a.ended ?? Date.now())} · {money(a.cost)}</span>
          </>
        ) : <span className="text-neutral-500">{manimOn ? "Builds this beat as a Manim figure: decides which pictures it needs and has them made, writes the code, has the compiler check it (nothing is rendered in its loop), mends it, finishes. Render the beat to see it." : "Manim is switched off for this beat."}</span>}
      </div>
      {(plan || a?.instruction) && (
        <div className="mt-1 space-y-0.5 text-[11px]">
          {plan && <p className="text-neutral-400"><span className="text-neutral-500">the scene writer&apos;s plan:</span> {plan}</p>}
          {a?.instruction && <p className="text-neutral-400"><span className="text-neutral-500">asked:</span> {a.instruction}</p>}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <input className="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-100" value={ask} onChange={(e) => setAsk(e.target.value)}
          placeholder="what you want (optional): “a farmer ploughing beside the river, the silt shown in layers”" data-testid="scenes-agent-ask" />
        <button className={`${btn} border-cyan-700 bg-cyan-800 text-white`} disabled={busy || !manimOn} data-testid="scenes-agent-run"
          onClick={() => act({ action: "agent", lecture: lecture.n, beat: n, instruction: ask || undefined })}>{a ? "Run the Manim agent again" : "Build with the Manim agent"}</button>
      </div>
      {a?.error && <p className="mt-1 text-[11px] text-red-300">{a.error}</p>}
      {a && (
        <ol className="mt-2 space-y-1.5" data-testid="scenes-agent-steps">
          {turns.map((t) => (
            <li key={t} className="rounded border border-neutral-800 bg-neutral-950/60 p-1.5">
              <div className="mb-1 flex items-center gap-2 text-[10px] text-neutral-500">
                <span className="rounded bg-neutral-800 px-1.5 text-neutral-300">turn {t}</span>
                {[...new Set(a.steps.filter((x) => x.turn === t && x.call).map((x) => x.call!))].map((id) => (
                  <button key={id} className="rounded border border-neutral-700 px-1 hover:bg-neutral-800" onClick={() => onCall(id)}>
                    call {id}{(() => { const c = run.calls.find((x) => x.id === id); return c ? ` · ${c.api === "image" ? "image model" : "agent"} · ${money(c.cost)}` : ""; })()}</button>
                ))}
              </div>
              <div className="space-y-1">
                {a.steps.filter((x) => x.turn === t).map((x, i) => (
                  <div key={i} className="text-xs">
                    <span className={STEP_LOOK[x.kind].tone}>{STEP_LOOK[x.kind].icon} {x.kind === "think" ? "" : x.kind === "image" ? `made the picture “${x.args?.name}” (${x.args?.kind})` : x.kind === "check" ? `checked the code${x.seconds ? ` (${x.seconds.toFixed(0)} s)` : ""}: ${x.errors?.length ? "it does not run" : "it runs"}`
                      : x.kind === "preview" ? `previewed${x.seconds ? ` (${x.seconds.toFixed(0)} s)` : ""}` : x.kind === "finish" ? `finished${x.seconds !== undefined ? ` (checked in ${x.seconds.toFixed(0)} s${x.errors?.length ? ": it does not run" : ""})` : ""}` : "error"}</span>
                    {x.kind === "think" && <span className="whitespace-pre-wrap text-neutral-300">{x.text}</span>}
                    {x.kind === "image" && (
                      <div className="mt-1 flex items-start gap-2">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        {x.image && <img alt={String(x.args?.name)} src={x.image} onClick={() => setBig(x.image!)} className="h-28 cursor-zoom-in rounded border border-neutral-800 bg-[repeating-conic-gradient(#262626_0_25%,#171717_0_50%)] bg-[length:16px_16px] object-contain" />}
                        <span className="text-[11px] text-neutral-400">{String(x.args?.what ?? "")}</span>
                      </div>
                    )}
                    {(x.kind === "check" || x.kind === "preview" || x.kind === "finish") && (
                      <div className="mt-1 grid gap-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                        <div>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          {x.ir && x.assets ? <IRPlayer src={x.ir} assets={x.assets} range={x.range} compact />
                            : x.video ? <video src={x.video} controls loop className="w-full rounded border border-neutral-800 bg-black" /> : null}
                          {x.still && <button className="mt-1 text-[10px] text-neutral-400 hover:underline" onClick={() => setBig(x.still!)}>the frame the agent looked at</button>}
                          {x.args?.summary ? <p className="mt-1 text-[11px] text-emerald-200">{String(x.args.summary)}</p> : null}
                          {x.kind !== "preview" && x.text ? <p className="mt-1 whitespace-pre-wrap text-[11px] text-neutral-400">compiler notes: {x.text}</p> : null}
                          {x.kind === "check" && !x.errors?.length && !x.text ? <p className="text-[11px] text-emerald-300">✓ the compiler ran it in a probe: no errors</p> : null}
                        </div>
                        <details open={!!x.errors?.length}>
                          <summary className="cursor-pointer text-[11px] text-neutral-400">the code ({String(x.args?.code ?? "").split("\n").length} lines){x.args?.area === "left" ? " · left half" : ""}</summary>
                          <pre className="mono mt-1 max-h-72 overflow-auto rounded bg-neutral-900 p-1.5 text-[10.5px] text-neutral-200">{String(x.args?.code ?? "")}</pre>
                        </details>
                      </div>
                    )}
                    {x.errors?.length ? <ul className="mt-1 rounded border border-red-900 bg-red-950/30 p-1 text-[11px] text-red-200">{x.errors.map((e, k) => <li key={k} className="whitespace-pre-wrap">✗ {e}</li>)}</ul> : null}
                  </div>
                ))}
              </div>
            </li>
          ))}
        </ol>
      )}
      {a?.images.length ? (
        <div className="mt-2">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">Pictures it made for this figure</p>
          <div className="flex flex-wrap gap-2">{a.images.map((name) => images[name]).filter(Boolean).map((img) => <AgentImageCard key={img.name} img={img} onCall={onCall} open={setBig} />)}</div>
        </div>
      ) : null}
      {a?.code && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] text-neutral-400">the code it settled on</summary>
          <pre className="mono mt-1 max-h-80 overflow-auto rounded bg-neutral-900 p-1.5 text-[10.5px] text-neutral-200">{a.code}</pre>
        </details>
      )}
      {big && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6" onClick={() => setBig(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img alt="enlarged" src={big} className="max-h-full max-w-full rounded bg-[repeating-conic-gradient(#262626_0_25%,#171717_0_50%)] bg-[length:16px_16px]" />
        </div>
      )}
    </section>
  );
}

function AgentImageCard({ img, onCall, open }: { img: import("@/lib/types").AgentImage; onCall: (id: string) => void; open: (url: string) => void }) {
  return (
    <div className="w-40 rounded border border-neutral-800 p-1 text-[10px]" data-testid="scenes-agent-image">
      {img.url
        // eslint-disable-next-line @next/next/no-img-element
        ? <img alt={img.name} src={img.url} onClick={() => open(img.url!)} className="h-24 w-full cursor-zoom-in rounded bg-[repeating-conic-gradient(#262626_0_25%,#171717_0_50%)] bg-[length:16px_16px] object-contain" />
        : <div className="flex h-24 items-center justify-center rounded bg-red-950/30 text-red-300">not made</div>}
      <p className="mt-0.5 font-medium text-neutral-200">“{img.name}” <span className="text-neutral-500">{img.kind} · beat #{img.beat}</span></p>
      <p className="line-clamp-2 text-neutral-400" title={img.what}>{img.what}</p>
      {img.error && <p className="text-red-300">{img.error}</p>}
      <p className="text-neutral-500">{money(img.cost)}{img.call && <button className="ml-1 text-sky-300 hover:underline" onClick={() => onCall(img.call!)}>call {img.call}</button>}</p>
    </div>
  );
}

/** Every picture the Manim agent made for the lecture, with the beat it was made for. */
function PicturesView({ run, lecture, onCall, setPick }: { run: Run; lecture: Lecture; onCall: (id: string) => void; setPick: (p: Pick) => void }) {
  const images = Object.values(run.scenes?.agentImages?.[lecture.n] ?? {});
  const [big, setBig] = useState<string | null>(null);
  const agents = Object.values(run.scenes?.lectures[lecture.n]?.beats ?? {}).filter((b) => b.agent);
  return (
    <div className="space-y-3 text-xs" data-testid="scenes-pictures">
      <p className="text-neutral-400">The Manim agent ran on {agents.length} beat(s) and made {images.length} picture(s) for this lecture
        ({money(images.reduce((k, i) => k + i.cost, 0))}). A picture is used in a figure&apos;s code by its name, image(&quot;name&quot;); any later figure of the lecture may use it again.</p>
      <div className="flex flex-wrap gap-2">{images.map((img) => <AgentImageCard key={img.name} img={img} onCall={onCall} open={setBig} />)}</div>
      {agents.length > 0 && (
        <table className="w-full">
          <thead className="text-left text-[10px] uppercase text-neutral-500"><tr><th className="py-1">Beat</th><th>Figure</th><th>State</th><th>Turns</th><th>Pictures</th><th>Cost</th><th>What it shows</th></tr></thead>
          <tbody>{agents.map((b) => (
            <tr key={b.n} className="cursor-pointer border-t border-neutral-800 hover:bg-neutral-900" onClick={() => setPick({ kind: "beat", n: b.n })}>
              <td className="py-1">#{b.n}</td><td className="mono">{b.agent!.id}</td>
              <td className={b.agent!.status === "failed" ? "text-red-300" : b.agent!.status === "done" ? "text-emerald-300" : "text-sky-300"}>{b.agent!.status}</td>
              <td>{b.agent!.turns}</td><td>{b.agent!.images.join(", ") || "—"}</td><td>{money(b.agent!.cost)}</td>
              <td className="text-neutral-400">{b.agent!.summary ?? b.agent!.error ?? ""}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {big && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6" onClick={() => setBig(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img alt="enlarged" src={big} className="max-h-full max-w-full rounded" />
        </div>
      )}
    </div>
  );
}

function CompilerView({ sl, beats, setPick }: { sl?: SceneLecture; beats: { n: number }[]; setPick: (p: Pick) => void }) {
  if (!sl?.compile) return <p className="text-xs text-neutral-500">Not compiled yet: it is compiled after each build.</p>;
  const c = sl.compile;
  const refused = beats.filter((b) => sl.beats[b.n]?.errors?.length);
  const noted = beats.filter((b) => sl.beats[b.n]?.notes?.length);
  return (
    <div className="space-y-3 text-xs" data-testid="scenes-compiler">
      <p className="text-neutral-400">The engine checked and compiled the whole lecture: <span className={c.status === "failed" ? "text-red-300" : "text-emerald-300"}>{c.status}</span>
        {c.seconds ? ` in ${c.seconds.toFixed(0)} s` : ""}{c.minutes ? `, about ${c.minutes} minutes of video` : ""}.</p>
      {[...c.errors].length > 0 && <ul className="text-red-300">{c.errors.map((e, i) => <li key={i}>✗ {e}</li>)}</ul>}
      <div>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">Refused beats ({refused.length})</p>
        {refused.length ? <ul className="space-y-1">{refused.map((b) => (
          <li key={b.n}><button className="text-left text-red-200 hover:underline" onClick={() => setPick({ kind: "beat", n: b.n })}>#{b.n}: {sl.beats[b.n].errors!.join("; ")}</button></li>
        ))}</ul> : <p className="text-neutral-500">None.</p>}
      </div>
      <div>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">What it mended or noted, by beat ({noted.length})</p>
        <ul className="space-y-0.5">{noted.map((b) => (
          <li key={b.n}><button className="text-left text-neutral-300 hover:underline" onClick={() => setPick({ kind: "beat", n: b.n })}>#{b.n}: {sl.beats[b.n].notes!.map((x) => x.replace(/^fixed:\s*/i, "")).join("; ")}</button></li>
        ))}</ul>
      </div>
      {c.warnings.length > 0 && (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">On the whole lecture</p>
          <ul className="space-y-0.5 text-neutral-400">{c.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </div>
      )}
      <MissingPictures missing={c.missing} note="left out of the scene" />
      {c.images && c.images.asked > 0 && <p className="text-neutral-400">The image model ({c.images.model}): {c.images.asked} picture request(s), {c.images.made} made now, {c.images.cached} made already{c.images.failed ? `, ${c.images.failed} could not be made` : ""}.</p>}
      {c.pictures?.length ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-400">AI pictures made ({c.pictures.length})</p>
          <ul className="space-y-0.5 text-neutral-400">{c.pictures.map((p, i) => <li key={i}>{p.prompt} <span className="text-neutral-500">· {p.model} · {money(p.usd ?? 0)}</span></li>)}</ul>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The chapter's beat script as built (each beat's operations, its paragraph, pause and about; the lecture's emblem
 * and the chapter's region), edited by hand as JSON, saved into the scenes and the chapter rendered again. The words
 * said are the transcript's: an edited "say" is not applied.
 */
function ChapterJson({ run, lecture, c, act, disabled }: { run: Run; lecture: number; c: number; act: Act; disabled: boolean }) {
  const [open, setOpen] = useState(false);
  const [json, setJson] = useState("");
  const [bad, setBad] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    setBad(null);
    try {
      const res = await fetch(`/api/runs/${run.id}/voice?lecture=${lecture}&chapter=${c}`, { cache: "no-store" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? res.statusText);
      setJson(JSON.stringify(body.script, null, 2));
      setOpen(true);
    } catch (e) {
      setBad((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  const save = async () => {
    let script: { chapter?: { beats?: { beat?: number; do?: unknown; paragraph?: boolean; pause?: number; about?: string }[] }; emblem?: string | null;
      region?: Record<string, unknown> | null };
    try { script = JSON.parse(json); } catch (e) { setBad(`not JSON: ${(e as Error).message}`); return; }
    const beats = script.chapter?.beats;
    if (!Array.isArray(beats)) { setBad("its chapter.beats must be a list of beats"); return; }
    const kept = beats.filter((b) => typeof b?.beat === "number");
    if (!kept.length) { setBad("no beat has its \"beat\" number: nothing to save"); return; }
    if (await act({ action: "editChapter", lecture, chapter: c, render: true, emblem: script.emblem ?? null, region: script.region ?? null,
      beats: kept.map((b) => ({ beat: b.beat, ops: Array.isArray(b.do) ? b.do : [], paragraph: b.paragraph, pause: b.pause, about: b.about })) })) {
      setOpen(false);
    }
  };
  return (
    <div className="rounded border border-neutral-800 p-2" data-testid="scenes-chapter-json">
      <div className="flex items-center gap-2 text-xs">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-400">The chapter as JSON</p>
        <span className="text-[11px] text-neutral-500">every beat&apos;s operations as built: change them, save, and the chapter is rendered again</span>
        <button className="ml-auto text-[11px] text-sky-300 hover:underline disabled:opacity-40" disabled={disabled || loading}
          onClick={() => (open ? setOpen(false) : void load())} data-testid="scenes-chapter-json-edit">{open ? "close" : loading ? "loading…" : "edit as JSON"}</button>
      </div>
      {bad && <p className="mt-1 text-[11px] text-red-300">{bad}</p>}
      {open && (
        <div className="mt-1 space-y-1">
          <textarea className="mono h-96 w-full rounded border border-neutral-700 bg-neutral-950 p-2 text-[11px] text-neutral-100" value={json}
            onChange={(e) => setJson(e.target.value)} data-testid="scenes-chapter-json-text" />
          <p className="text-[10px] text-neutral-500">Each beat keeps its &quot;beat&quot; number. The words said (&quot;say&quot;) are the transcript&apos;s: an edited say is not applied (edit the transcript for that). The look is the run&apos;s.</p>
          <button className={`${btn} border-emerald-700 bg-emerald-800 text-white`} disabled={disabled} onClick={() => void save()}
            data-testid="scenes-chapter-json-rerender">Save and re-render the chapter</button>
        </div>
      )}
    </div>
  );
}

/**
 * Which engine draws the lecture: the current one, or the motion engine (beta: engine/MOTION_ENGINE.md), which draws
 * every current operation in motion and adds its templates (the scene writer is told of them); its look, energy,
 * transition and timeline style. Used for the next builds, compiles, renders and the Voice tab.
 */
function EngineRow({ st, act }: { st: Run["scenes"]; act: Act }) {
  const motion = st?.engine === "motion";
  const m = st?.motion ?? {};
  const set = (k: string, v: string) => act({ action: "engine", engine: "motion", [k]: v });
  const sel = "rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 disabled:opacity-40";
  const templated = Object.values(st?.lectures ?? {}).reduce((k, l) => k + Object.values(l.beats).filter((b) => b.ops.some((o) => MOTION_KIND.ops.includes(String(o.op)))).length, 0);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs" data-testid="scenes-engine">
      <span className="text-fuchsia-300">Engine</span>
      <label className="flex items-center gap-1 text-neutral-300" title="pocket_lecture: what every lecture has been built with">
        <input type="radio" checked={!motion} onChange={() => act({ action: "engine", engine: "current" })} data-testid="scenes-engine-current" /> current</label>
      <label className="flex items-center gap-1 text-neutral-300" title="The motion engine (beta): every operation drawn in motion, each part landing on its words, plus templates (counters, charts, cards, stamps...) the scene writer is told of">
        <input type="radio" checked={motion} onChange={() => act({ action: "engine", engine: "motion" })} data-testid="scenes-engine-motion" /> motion (beta)</label>
      <label className="flex items-center gap-1 text-neutral-300">look
        <select className={sel} disabled={!motion} value={m.look ?? ""} onChange={(e) => set("look", e.target.value)} data-testid="scenes-motion-look">
          <option value="">the style&apos;s own</option>{MOTION_LOOKS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select></label>
      <label className="flex items-center gap-1 text-neutral-300">energy
        <select className={sel} disabled={!motion} value={m.energy ?? ""} onChange={(e) => set("energy", e.target.value)}>
          <option value="">the look&apos;s own</option>{["calm", "lively", "punchy"].map((l) => <option key={l} value={l}>{l}</option>)}
        </select></label>
      <label className="flex items-center gap-1 text-neutral-300">transition
        <select className={sel} disabled={!motion} value={m.transition ?? ""} onChange={(e) => set("transition", e.target.value)}>
          <option value="">the look&apos;s own</option>{MOTION_TRANSITIONS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select></label>
      <label className="flex items-center gap-1 text-neutral-300">idle
        <select className={sel} disabled={!motion} value={m.idle ?? ""} onChange={(e) => set("idle", e.target.value)}>
          <option value="">the look&apos;s own</option>{MOTION_IDLES.map((l) => <option key={l} value={l}>{l}</option>)}
        </select></label>
      <label className="flex items-center gap-1 text-neutral-300">timeline
        <select className={sel} disabled={!motion} value={m.timeline ?? ""} onChange={(e) => set("timeline", e.target.value)}>
          <option value="">track</option>{["ribbon", "cards", "road", "vertical"].map((l) => <option key={l} value={l}>{l}</option>)}
        </select></label>
      <label className="flex items-center gap-1 text-neutral-300" title={motion
        ? "Each chapter is spoken and its words aligned before its scenes are written: the scene writer sees how long every line is, the quiet after it and its words by number with their times, and anchors to them"
        : "Each chapter is spoken and its words aligned before its scenes are written; then a timing call of its own puts every picture and every part of one on the exact word it comes on with"}>
        <input type="checkbox" checked={st?.voiceFirst !== false}
          onChange={(e) => act({ action: "engine", engine: motion ? "motion" : "current", voiceFirst: e.target.checked })} data-testid="scenes-voice-first" /> voice first</label>
      <label className="flex items-center gap-1 text-neutral-300" title="A quiet music bed under the voice (on either engine: the motion look's mood, a calm one on the current engine), dipping under its words and up a little in its pauses">
        <input type="checkbox" checked={st?.music !== false}
          onChange={(e) => act({ action: "engine", engine: motion ? "motion" : "current", music: e.target.checked })} data-testid="scenes-music" /> music</label>
      <span className="text-neutral-500">{motion
        ? "the scene writer is told of the motion templates; builds, renders and the Voice tab use the motion engine"
        : "the lectures built so far stay as they are either way"}</span>
      {!motion && templated > 0 && <span className="text-amber-300">{templated} beats use motion templates: the current engine leaves those out</span>}
    </div>
  );
}
