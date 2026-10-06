"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { VersionBar } from "@/components/version-bar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { LENGTH_CHOICES, SUBJECT_CHOICES, TEMPLATES } from "@/lib/templates";
import { TemplateCard } from "@/components/template-card";
import { Player } from "@/components/player";
import type { SceneIR } from "@/lib/pocketanim";

type ExportState = {
  tier: 1 | 3 | null;
  scene?: string;
  blockers?: string[];
  /** Pictures left out because they could not be drawn (the lecture still built), with their beats. */
  skipped?: string[];
  program?: string | null;
  source?: string;
  program_bytes?: number;
  assets?: string[];
  container?: string;
  container_error?: string;
  buildDir?: string;
  frames?: number;
  error?: string;
  voiceWarning?: string | null;
  /** What the narration voice cost (scripts/prespeak.py): lines spoken for this build, and the whole lecture. */
  voiceCost?: { usd: number; lecture_usd: number; spoken: number; lines: number; unknown: number; engine: string };
  narrationUrl?: string | null;
};

type TraceEvent = {
  type: string;
  role?: string;
  name?: string;
  text?: string;
  args?: string;
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
  source?: string;
  model?: string;
  streaming?: boolean;
  /** A lecture made as several videos: each part's title, length and scene (lib/parts.ts). */
  parts?: { title: string; minutes: number; source: string }[];
  /** One micro-lecture, written before the rest: built at once, while the others are still being written. */
  part?: { index: number; of: number; title: string; minutes: number; source: string };
};

/** A build already under way: its progress id and the export it will finish with. */
type StartedBuild = { jobId: string; exported: Promise<ExportState> };

/** Builds at once, at most: a series of micro-lectures built one after the other took as long again as writing them. */
const BUILD_SLOTS = 3;
let buildsRunning = 0;
const buildWaiting: (() => void)[] = [];

async function inBuildSlot<T>(work: () => Promise<T>): Promise<T> {
  if (buildsRunning >= BUILD_SLOTS) await new Promise<void>((resolve) => buildWaiting.push(resolve));
  buildsRunning += 1;
  try {
    return await work();
  } finally {
    buildsRunning -= 1;
    buildWaiting.shift()?.();
  }
}

type Version = {
  n: number;
  templateId: string;
  instruction: string | null;
  source: string;
  voiceUrl?: string | null;
  model: string;
  trace: TraceEvent[];
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
  /** The voice's cost for this version, added up over its builds (each line is paid for once, when spoken). */
  voiceUsd?: number;
  /** The whole lecture's voice, at the latest build: what its lines cost when they were spoken. */
  voiceLecture?: { usd: number; lines: number; unknown: number };
  exported?: ExportState;
  ir?: SceneIR | null;
  sceneClass?: string;
  /** The lecture's spoken transcript, written in full before the video (lib/transcript.ts). */
  transcript?: string;
  /** One video of a lecture made as several micro-lectures (lib/topics.ts, lib/parts.ts): the versions of one n are its parts. */
  part?: { index: number; of: number; title: string; minutes: number };
};

type Status = {
  python: string;
  manim: string | null;
  latex: boolean;
  chirp?: boolean;
  fixture: boolean;
  model: string;
  /** The model that writes the lecture's transcript (OPENROUTER_TRANSCRIPT_MODEL, else the video's). */
  transcriptModel?: string;
  error?: string;
};

const SCENE = "GeneratedScene";

function sceneClassOf(source: string): string {
  if (/class\s+GeneratedScene\b/.test(source)) return SCENE;
  // A Manim scene, or a lecture (pocket_lecture's Lecture, MapLecture...).
  const found = source.match(/class\s+(\w+)\s*\(\s*(?:ThreeDScene|MovingCameraScene|Scene|\w*Lecture)\s*\)/);
  return found?.[1] ?? SCENE;
}

function Expandable({ text, limit }: { text: string; limit: number }) {
  const [open, setOpen] = useState(false);
  if (text.length <= limit) return <>{text}</>;
  return (
    <>
      {open ? text : `${text.slice(0, limit)}…`}
      <button
        type="button"
        className="ml-2 text-sky-300 underline-offset-2 hover:underline"
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "show less" : "show all"}
      </button>
    </>
  );
}

function TraceLine({ event }: { event: TraceEvent }) {
  if (event.type === "usage") {
    return <p className="text-neutral-500">{event.text}</p>;
  }
  if (event.type === "tool_call") {
    return (
      <p className="whitespace-pre-wrap text-sky-300">
        <span className="text-sky-500">tool call </span>
        {event.name} {event.args}
      </p>
    );
  }
  if (event.type === "tool_result") {
    return (
      <pre className="whitespace-pre-wrap text-emerald-200/90">
        <span className="text-emerald-500">{event.name} output: </span>
        <Expandable text={event.text ?? ""} limit={1800} />
      </pre>
    );
  }
  if (event.type === "done") {
    return <p className="text-neutral-300">scene written</p>;
  }
  if (event.type === "error") {
    return <p className="text-rose-300">{event.text}</p>;
  }
  if (event.type === "input") {
    return (
      <pre className="whitespace-pre-wrap border-l border-amber-700/80 pl-2 text-amber-100/90">
        <span className="text-amber-500">input · {event.role}: </span>
        <Expandable text={event.text ?? ""} limit={event.role === "system" ? 400 : 1600} />
      </pre>
    );
  }
  const label =
    event.role === "thinking" ? "thinking" : event.role === "status" ? "status" : (event.role ?? event.type);
  const tone =
    event.role === "thinking"
      ? "text-violet-200/90"
      : event.role === "status"
        ? "text-neutral-400"
        : "text-neutral-200";
  return (
    <p className={`whitespace-pre-wrap ${tone}`}>
      <span className="text-neutral-500">{label}: </span>
      {event.text}
      {event.streaming ? <span className="text-neutral-500"> ▍</span> : null}
    </p>
  );
}

function applyTrace(trace: TraceEvent[], event: TraceEvent): TraceEvent[] {
  // An early part's scene is built, not shown in the trace (the status line before it says so).
  if (event.type === "part") return trace;
  if (event.type === "delta") {
    const last = trace[trace.length - 1];
    if (last?.type === "message" && last.role === event.role && last.streaming) {
      return [...trace.slice(0, -1), { ...last, text: `${last.text ?? ""}${event.text ?? ""}` }];
    }
    return [...trace, { type: "message", role: event.role, text: event.text, streaming: true }];
  }
  const closed =
    trace.length > 0 && trace[trace.length - 1]?.streaming
      ? [...trace.slice(0, -1), { ...trace[trace.length - 1], streaming: false }]
      : trace;
  return [...closed, event];
}

function phaseFor(event: TraceEvent): string | null {
  if (event.type === "input") {
    return event.role === "system" ? "Sending the system prompt…" : "Sending the scene to the model…";
  }
  if (event.type === "delta") {
    return event.role === "thinking" ? "Model is thinking…" : "Model is writing the scene…";
  }
  if (event.type === "tool_call") return `Running ${event.name}…`;
  if (event.type === "tool_result") return `${event.name} returned`;
  if (event.type === "usage") return event.text ?? null;
  if (event.role === "status") return event.text ?? null;
  return null;
}

export default function Home() {
  const [content, setContent] = useState("");
  const [templateId, setTemplateId] = useState(TEMPLATES[0].id);
  const [versions, setVersions] = useState<Version[]>([]);
  const [current, setCurrent] = useState(-1);
  // The version on screen, for work that finishes later (a part built in the background).
  const currentRef = useRef(-1);
  useEffect(() => {
    currentRef.current = current;
  }, [current]);
  const [instruction, setInstruction] = useState("");
  /** The lecture's length in minutes; null lets the content's size decide. */
  const [minutes, setMinutes] = useState<number | null>(null);
  /** The subject the lecture is taught as; "auto" lets the content decide. */
  const [subject, setSubject] = useState("auto");
  /** The narration's language: "auto" follows the content; "hinglish" is Hindi with English terms. */
  const [language, setLanguage] = useState("auto");
  /** The transcript's model, typed on the page (kept in this browser); empty: the server's setting. */
  const [writer, setWriter] = useState("");
  useEffect(() => {
    try {
      setWriter(localStorage.getItem("panim.transcriptModel") ?? "");
    } catch {
      // no storage here: the server's setting
    }
  }, []);
  function chooseWriter(value: string) {
    setWriter(value);
    try {
      localStorage.setItem("panim.transcriptModel", value.trim());
    } catch {
      // not remembered, still used for this lecture
    }
  }
  /** A YouTube video the lecture follows: its link, or its transcript pasted in. */
  const [reference, setReference] = useState<{
    busy: boolean;
    error?: string;
    id?: string;
    title?: string;
    parts?: number;
    duration?: number;
    language?: string;
    note?: string | null;
    url: string;
    transcript: string;
    paste: boolean;
  }>({ busy: false, url: "", transcript: "", paste: false });
  const [busy, setBusyText] = useState<string | null>(null);
  const setBusy = setBusyText;
  const [error, setError] = useState<string | null>(null);
  const [frame, setFrame] = useState(0);
  const [status, setStatus] = useState<Status | null>(null);
  const [showProgram, setShowProgram] = useState(false);
  const [pasted, setPasted] = useState("");
  const [doc, setDoc] = useState<{
    busy: boolean;
    error?: string;
    id?: string;
    name?: string;
    source?: string;
    pages?: number;
    note?: string | null;
    figures?: { id: string; caption: string; url: string }[];
    /** Figures removed from the lecture: kept by the server, restorable. */
    excluded?: { id: string; caption: string; url: string }[];
  }>({ busy: false });
  const [saving, setSaving] = useState<{
    busy: boolean;
    ready?: boolean;
    problem?: string | null;
    error?: string;
    result?: { lectures: { lecture: number; title: string; bytes: number }[]; skipped: string[] };
    /** What is saved and what the phone's Saved list sees of it (/api/save?status=1). */
    status?: string;
    /** Builds already saved in this session: Save again (after rebuilding a failed video) saves only the rest. */
    savedDirs?: string[];
    /** What the save in progress is doing, and how far through it is (0-100). */
    progress?: string;
    percent?: number;
  }>({ busy: false });
  useEffect(() => {
    fetch("/api/save").then((r) => r.json()).then((d: { ready: boolean; problem: string | null }) =>
      setSaving((s) => ({ ...s, ready: d.ready, problem: d.problem }))).catch(() => {});
  }, []);
  const [video, setVideo] = useState<{ busy: boolean; error?: string; quality: string }>({
    busy: false,
    quality: "m",
  });
  const logRef = useRef<HTMLDivElement>(null);

  const version = current >= 0 ? versions[current] : undefined;
  const exported = version?.exported;

  /**
   * Save the lecture on screen: every micro-lecture of its series, or the one video, with its phone files
   * (/api/save, lib/store.ts). Each must be built at tier 1: the phone plays programs.
   */
  /** What the database holds and what the phone's Saved list can see, in one line (lib/store.ts storeStatus). */
  async function checkSaved() {
    setSaving((s) => ({ ...s, status: "Checking…" }));
    try {
      const d = await (await fetch("/api/save?status=1")).json() as { problem: string | null; status: null | { error: string } |
        { published: number; failed: { at: string; error: string }[]; phoneSees: number | null; phoneError: string | null } };
      const st = d.status;
      let line: string;
      if (!st) line = `Saving is not set up: ${d.problem}`;
      else if ("error" in st) line = `Could not read the database: ${st.error}`;
      else {
        line = `Saved in the database: ${st.published} video${st.published === 1 ? "" : "s"}. ` +
          (st.phoneSees !== null ? `The phone's Saved list sees ${st.phoneSees}.` : `The phone's view could not be read: ${st.phoneError}`);
        if (st.phoneSees !== null && st.phoneSees < st.published) {
          line += " The phone cannot see them all: run harness/supabase/setup.sql again in the SQL editor (it grants the phone's view).";
        }
        if (st.failed.length) line += ` Last failed save: ${st.failed[0].error}`;
      }
      setSaving((s) => ({ ...s, status: line }));
    } catch (e) {
      setSaving((s) => ({ ...s, status: `Could not check: ${e instanceof Error ? e.message : String(e)}` }));
    }
  }

  async function saveLecture() {
    if (!version) return;
    const all = version.part ? versions.filter((v) => v.n === version.n && v.part) : [version];
    // A series saves the micro-lectures that built for the phone; one that did not is named, with why, so it can be
    // rebuilt (pick it, Rebuild preview) and saved on its own afterwards. One failed video no longer held back the rest.
    const built = (v: Version) => v.exported?.tier === 1 && !!v.exported?.buildDir;
    const done = new Set(saving.savedDirs ?? []);
    const videos = all.filter((v) => built(v) && !done.has(v.exported!.buildDir!));
    const why = (v: Version) => !v.exported ? "still building, or its build stopped"
      : v.exported.error ? v.exported.error.split("\n")[0].slice(0, 160)
        : v.exported.tier === 3 ? `not playable on the phone (${(v.exported.blockers ?? []).slice(0, 2).join("; ") || "tier 3"})`
          : "no build";
    const left = all.filter((v) => !built(v)).map((v) => `${v.part?.title ?? "this video"}: ${why(v)}`);
    if (!videos.length) {
      setSaving((s) => ({ ...s, result: undefined, error: left.length
        ? `Nothing new is built for the phone: ${left.join("; ")}` : "Already saved: every video of this lecture is saved." }));
      return;
    }
    // The series' title: a micro-lecture's title card says "<series> · Lecture k of N"; a single video's is its own.
    const card = /self\.title_slide\(("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")/.exec(videos[0].source);
    const read = (text?: string) => {
      try {
        return text ? String(JSON.parse(text)) : "";
      } catch {
        return "";
      }
    };
    const series = version.part ? read(card?.[2]).split(" · ")[0] : read(card?.[1]);
    setSaving((s) => ({ ...s, busy: true, error: undefined, result: undefined, progress: "Starting…" }));
    // A save that sends nothing for this long has stalled (a dropped connection): stopped, so Save works again.
    const QUIET_MS = 5 * 60_000;
    const abort = new AbortController();
    let quiet: ReturnType<typeof setTimeout> | undefined;
    const heard = () => {
      if (quiet) clearTimeout(quiet);
      quiet = setTimeout(() => abort.abort(), QUIET_MS);
    };
    const savedNow: string[] = [];
    const mb = (n?: number) => `${((n ?? 0) / 1048576).toFixed(1)} MB`;
    try {
      heard();
      const response = await fetch("/api/save", {
        method: "POST",
        signal: abort.signal,
        headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
        body: JSON.stringify({
          title: series || videos[0].part?.title || "Untitled lecture",
          content,
          subject: subject === "auto" ? undefined : subject,
          language: language === "auto" ? undefined : language,
          parts: videos.map((v) => ({
            buildDir: v.exported!.buildDir,
            sceneClass: v.sceneClass ?? SCENE,
            source: v.source,
            title: v.part?.title ?? (read(card?.[1]) || "Lecture"),
            minutes: v.part?.minutes ?? (v.exported?.frames ? v.exported.frames / 30 / 60 : undefined),
            instruction: v.instruction,
            model: v.model,
            transcript: v.transcript,
            inputTokens: v.inputTokens,
            outputTokens: v.outputTokens,
            lecture: v.part?.index,
            of: v.part?.of,
          })),
        }),
      });
      // A refusal before the save started (not set up, not a build) comes back as one JSON object.
      if (!response.ok || !response.body || !(response.headers.get("content-type") ?? "").includes("ndjson")) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error ?? `HTTP ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let result: { saved: boolean; error?: string; lectures?: { lecture: number; title: string; bytes: number }[];
        skipped?: string[] } | null = null;
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        heard();
        buffer += decoder.decode(chunk.value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines.filter(Boolean)) {
          const event = JSON.parse(line);
          if (event.type === "result") {
            result = event;
            continue;
          }
          const which = event.videos > 1 ? `Video ${event.video} of ${event.videos} (${event.title})` : event.title;
          if (event.stage === "saved") savedNow.push(videos[event.video - 1].exported!.buildDir!);
          const text = event.stage === "packing" ? `${which}: packing the phone files…`
            : event.stage === "uploading" ? `${which}: uploading ${event.filesDone} of ${event.files} files ` +
              `(${mb(event.bytesDone)} of ${mb(event.bytes)})`
              : event.stage === "saved" ? `${which}: saved`
                : `${which}: not saved (${event.error})`;
          const share = event.stage === "uploading" && event.bytes ? event.bytesDone / event.bytes : event.stage === "saved" ? 1 : 0;
          setSaving((s) => ({ ...s, progress: text,
            percent: Math.round(((event.video - 1 + share) / event.videos) * 100) }));
        }
      }
      if (!result) throw new Error("the save stopped before it finished");
      if (!result.saved) throw new Error(result.error ?? "nothing was saved");
      const done = result;
      setSaving((s) => ({ ...s, result: { lectures: done.lectures ?? [],
        skipped: [...left.map((l) => `${l} (pick it and press Rebuild preview, then Save it)`), ...(done.skipped ?? [])] } }));
      void checkSaved();
    } catch (e) {
      const why = abort.signal.aborted ? `nothing came back for ${QUIET_MS / 60_000} minutes; press Save to try again`
        : e instanceof Error ? e.message : String(e);
      setSaving((s) => ({ ...s, error: savedNow.length ? `${why} (${savedNow.length} of ${videos.length} saved before it ` +
        "stopped; Save again sends only the rest)" : why }));
    } finally {
      // Whatever happened, Save can be pressed again, and the videos that did get saved are not sent twice.
      if (quiet) clearTimeout(quiet);
      setSaving((s) => ({ ...s, busy: false, progress: undefined, percent: undefined,
        savedDirs: [...(s.savedDirs ?? []), ...savedNow] }));
    }
  }
  const ir = version?.ir;
  const template = TEMPLATES.find((t) => t.id === templateId) ?? TEMPLATES[0];

  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    if (busy) el.scrollIntoView({ block: "nearest" });
  }, [version?.trace, busy]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/status")
      .then((response) => response.json())
      .then((data: Status) => {
        if (!cancelled) setStatus(data);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function post(path: string, body: unknown) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      // The body may still say what was paid for before the failure (the voice's lines).
      throw Object.assign(new Error(data.error ?? `${response.status}`), { data });
    }
    return data;
  }

  async function loadPreview(buildDir: string, sceneClass: string): Promise<SceneIR | null> {
    const response = await fetch(
      `/api/ir?build=${encodeURIComponent(buildDir)}&scene=${sceneClass}`,
    );
    const geometry = await response.json();
    if (!response.ok) {
      setError(geometry.error ?? "could not load the scene");
      return null;
    }
    return geometry as SceneIR;
  }

  /** A build started now (or as soon as a slot is free), for attachBuild to finish: early, for a part. */
  function startBuild(source: string, instruction: string | null, model: string): StartedBuild {
    const jobId = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
    const exported = inBuildSlot(() => post("/api/export", {
      source,
      sceneClass: sceneClassOf(source),
      instruction,
      model,
      jobId,
    }) as Promise<ExportState>);
    // Awaited by attachBuild; until then a failure is not an unhandled rejection.
    exported.catch(() => {});
    return { jobId, exported };
  }

  async function attachBuild(
    index: number,
    source: string,
    instruction: string | null,
    model: string,
    label = "",
    started?: StartedBuild,
  ) {
    // A lecture made as several videos builds them one after the other: each says which it is.
    const setBusy = (text: string | null) => setBusyText(text && label ? `${label}: ${text}` : text);
    const sceneClass = sceneClassOf(source);
    const lecture = /pocket_lecture/.test(source);
    setBusy(lecture
      ? "Speaking the lecture, running Manim and building the program…"
      : "Running Manim and building the program…");
    // The server writes how far it has got (lines spoken, beats drawn); the busy line shows it.
    const build = started ?? startBuild(source, instruction, model);
    const jobId = build.jobId;
    const startedAt = Date.now();
    const poll = lecture ? setInterval(async () => {
      try {
        const state = await (await fetch(`/api/progress?id=${jobId}`)).json() as
          { phase?: string; done?: number; total?: number };
        const elapsed = Math.round((Date.now() - startedAt) / 1000);
        const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
        if (state.phase === "voice" && state.total) {
          const share = Math.round((100 * (state.done ?? 0)) / state.total);
          setBusy(`Speaking the lecture: ${state.done} of ${state.total} lines (${share}%) · ${clock}`);
        } else if (state.phase === "render" && state.total) {
          const share = Math.round((100 * (state.done ?? 0)) / state.total);
          setBusy(`Drawing the lecture in Manim: beat ${state.done} of ${state.total} (${share}%) · ${clock}`);
        }
      } catch {
        // progress is a nicety: the build goes on without it
      }
    }, 1500) : null;
    let exported: ExportState;
    // The voice's bill for this build goes on the version, whether the build then succeeds or not.
    const billVoice = (cost?: ExportState["voiceCost"]) => {
      if (!cost) return;
      setVersions((all) => all.map((v, i) => i === index ? {
        ...v,
        voiceUsd: (v.voiceUsd ?? 0) + cost.usd,
        voiceLecture: { usd: cost.lecture_usd, lines: cost.lines, unknown: cost.unknown },
      } : v));
    };
    try {
      exported = await build.exported;
    } catch (error) {
      billVoice((error as { data?: ExportState }).data?.voiceCost);
      throw error;
    } finally {
      if (poll) clearInterval(poll);
    }
    billVoice(exported.voiceCost);
    if (lecture) setBusy("Building the program and the preview…");
    const played = exported.scene || sceneClass;
    let ir: SceneIR | null | undefined;
    if (exported.buildDir && exported.program && !exported.error) {
      setBusy("Loading the preview…");
      ir = await loadPreview(exported.buildDir, played);
    } else if (exported.error) {
      setError(exported.error);
    }
    if (exported.voiceWarning && !exported.error) setError(exported.voiceWarning);
    const fixed = exported.source ?? source;
    setVersions((all) =>
      all.map((v, i) =>
        i === index
          ? {
              ...v,
              exported,
              ir,
              sceneClass: played,
              source: fixed,
              // The scene's own narration, when it has one, is the track that
              // matches this build; a separate voiceover belongs to # voice: lines.
              voiceUrl: exported.narrationUrl ?? v.voiceUrl,
            }
          : v,
      ),
    );
    // Only the video on screen starts again: a later part built in the background leaves the one being watched.
    if (currentRef.current === index) setFrame(0);
  }

  async function runGenerate(edit: boolean) {
    setError(null);
    setBusy(
      edit ? "Agent is rewriting the scene…" : "Agent is writing the scene…",
    );
    const index = versions.length;
    const styleId = templateId;
    const next: Version = {
      n: (versions[versions.length - 1]?.n ?? 0) + 1,
      templateId: styleId,
      instruction: edit ? instruction : null,
      source: "",
      model: "",
      trace: [],
    };
    setVersions((all) => [...all, next]);
    setCurrent(index);
    setInstruction("");
    setFrame(0);
    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content,
          templateId: styleId,
          previousSource: edit ? version?.source : undefined,
          instruction: edit ? instruction : undefined,
          documentId: doc.id,
          minutes: template.kind === "lecture" && minutes ? minutes : undefined,
          subject: template.kind === "lecture" ? subject : undefined,
          language: template.kind === "lecture" ? language : undefined,
          transcriptModel: template.kind === "lecture" && writer.trim() ? writer.trim() : undefined,
          referenceId: template.kind === "lecture" ? reference.id : undefined,
        }),
      });
      if (!response.ok || !response.body) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error ?? `${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let source = "";
      let modelName = "";
      let videoParts: { title: string; minutes: number; source: string }[] = [];
      // Micro-lectures sent before the rest was written, already building, by their scene.
      const early = new Map<string, StartedBuild>();
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.split("\n").find((row) => row.startsWith("data: "));
          if (!line) continue;
          const event = JSON.parse(line.slice(6)) as TraceEvent;
          if (event.type === "error")
            throw new Error(event.text || "agent failed");
          if (event.type === "done") {
            source = event.source ?? source;
            modelName = event.model ?? modelName;
            videoParts = event.parts ?? [];
          }
          if (event.type === "part" && event.part && !early.has(event.part.source)) {
            early.set(event.part.source, startBuild(event.part.source, next.instruction, modelName));
          }
          const phase = phaseFor(event);
          if (phase) setBusy(phase);
          setVersions((all) =>
            all.map((item, i) =>
              i === index
                ? {
                    ...item,
                    trace: applyTrace(item.trace, event),
                    source:
                      event.type === "done"
                        ? (event.source ?? item.source)
                        : item.source,
                    model:
                      event.type === "done"
                        ? (event.model ?? item.model)
                        : item.model,
                    transcript: event.type === "transcript" ? event.text : item.transcript,
                    inputTokens: event.inputTokens ?? item.inputTokens,
                    outputTokens: event.outputTokens ?? item.outputTokens,
                    costUsd: event.costUsd ?? item.costUsd,
                  }
                : item,
            ),
          );
        }
      }
      if (!source.trim())
        throw new Error("The agent finished without a scene.");
      // Only a scene with # voice: lines is voiced here. A lecture speaks its
      // own beats during export, and asking for a voiceover of lines it does not have
      // put an error over every lecture.
      if (/^\s*# voice:/m.test(source)) {
        setBusy("Recording the voiceover…");
        const spoken = await post("/api/voice", { source, templateId: styleId });
        if (spoken.source) source = spoken.source;
        setVersions((all) =>
          all.map((item, i) =>
            i === index
              ? { ...item, source, voiceUrl: spoken.audioUrl ?? null }
              : item,
          ),
        );
        if (!spoken.ok && spoken.error) setError(spoken.error);
      }
      if (videoParts.length > 1) {
        // A series of micro-lectures: one video per topic, each a version of the same n, built in turn. The first is shown.
        const info = (k: number) => ({ index: k + 1, of: videoParts.length, title: videoParts[k].title, minutes: videoParts[k].minutes });
        setVersions((all) => [
          ...all.map((item, i) => (i === index ? { ...item, source: videoParts[0].source, part: info(0) } : item)),
          ...videoParts.slice(1).map((p, k) => ({
            ...next, source: p.source, model: modelName, trace: [], part: info(k + 1),
            transcript: undefined, inputTokens: undefined, outputTokens: undefined, costUsd: undefined,
          })),
        ]);
        // Up to three at once (inBuildSlot); a part built early, from the same scene, is that build.
        await Promise.all(videoParts.map(async (p, k) => {
          try {
            await attachBuild(index + k, p.source, next.instruction, modelName,
              `${p.title} (${k + 1} of ${videoParts.length})`, early.get(p.source));
          } catch (e) {
            setError(`${p.title}: ${e instanceof Error ? e.message : String(e)}`);
          }
        }));
        return;
      }
      await attachBuild(index, source, next.instruction, modelName);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function playPasted() {
    const raw = pasted.trim();
    if (!/from manim import/.test(raw)) {
      setError("Paste a Manim file. It needs a line that says from manim import.");
      return;
    }
    setError(null);
    const index = versions.length;
    const sceneClass = sceneClassOf(raw);
    const next: Version = {
      n: (versions[versions.length - 1]?.n ?? 0) + 1,
      templateId,
      instruction: null,
      source: raw,
      model: "pasted",
      trace: [],
      sceneClass,
    };
    setVersions((all) => [...all, next]);
    setCurrent(index);
    setFrame(0);
    try {
      let source = raw;
      if (/^\s*# voice:/m.test(source)) {
        setBusy("Recording the voiceover…");
        const spoken = await post("/api/voice", { source, templateId });
        if (spoken.source) source = spoken.source;
        setVersions((all) =>
          all.map((item, i) =>
            i === index ? { ...item, source, voiceUrl: spoken.audioUrl ?? null } : item,
          ),
        );
        if (!spoken.ok && spoken.error) setError(spoken.error);
      }
      await attachBuild(index, source, null, "pasted");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function runExport() {
    if (!version) return;
    setError(null);
    try {
      await attachBuild(
        current,
        version.source,
        version.instruction,
        version.model,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  /** Leave one of the PDF's figures out of the lecture (or, with null, bring them all back). */
  async function changeFigures(figure: string | null) {
    if (!doc.id) return;
    const response = figure
      ? await fetch(`/api/document?id=${doc.id}&figure=${encodeURIComponent(figure)}`, { method: "DELETE" })
      : await fetch(`/api/document?id=${doc.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ excluded: [] }) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setDoc((d) => ({ ...d, error: data.error ?? `HTTP ${response.status}` }));
      return;
    }
    setDoc((d) => ({ ...d, error: undefined, figures: data.figures, excluded: data.excluded }));
    // The content box holds the PDF's text: a removed figure's marker leaves it, a restored one comes back.
    if (figure) {
      const marker = new RegExp(`\\[FIGURE ${figure.replace(/[^a-z0-9_]/gi, "")}:[^\\]]*\\]\\n?`, "g");
      setContent((c) => c.replace(marker, ""));
    } else if (data.markdown) {
      setContent((c) => `${c.split("\n")[0]}\n${data.markdown}`);
    }
  }

  /** Read a reference video's transcript (from YouTube, or pasted): the lecture will follow its parts. */
  async function addReference() {
    setReference((r) => ({ ...r, busy: true, error: undefined }));
    try {
      const response = await fetch("/api/document", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reference.paste
          ? { transcript: reference.transcript, youtube: reference.url || undefined }
          : { youtube: reference.url }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
      setReference((r) => ({ ...r, busy: false, id: data.id, title: data.video?.title ?? data.name,
        parts: data.parts?.length ?? 0, duration: data.video?.duration, language: data.video?.language, note: data.note }));
      // With no content of its own, the lecture is named after the video.
      setContent((c) => c.trim() ? c : `${data.video?.title ?? "Lecture"}`);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      // YouTube refuses some networks: offer the paste box straight away.
      setReference((r) => ({ ...r, busy: false, error: message, paste: r.paste || /paste/i.test(message) }));
    }
  }

  /** Upload a lecture PDF: its text becomes the content, its figures become figure ops. */
  async function uploadDocument(file: File) {
    setDoc({ busy: true, name: file.name });
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/document", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
      setDoc({ busy: false, id: data.id, name: file.name, source: data.source, pages: data.pages, note: data.note,
        figures: data.figures, excluded: data.excluded });
      setContent(`${file.name.replace(/\.pdf$/i, "")}\n${data.markdown}`);
    } catch (e) {
      setDoc({ busy: false, name: file.name, error: e instanceof Error ? e.message : String(e) });
    }
  }

  /** Render the build with Manim and hand the MP4 to the browser as a download. */
  async function downloadVideo() {
    if (!exported?.buildDir) return;
    const scene = version?.sceneClass ?? SCENE;
    setVideo((v) => ({ ...v, busy: true, error: undefined }));
    try {
      const response = await fetch(
        `/api/video?build=${encodeURIComponent(exported.buildDir)}&scene=${scene}&quality=${video.quality}`,
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
        throw new Error(body.error ?? `HTTP ${response.status}`);
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `${scene}.mp4`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setVideo((v) => ({ ...v, busy: false }));
    } catch (e) {
      setVideo((v) => ({ ...v, busy: false, error: e instanceof Error ? e.message : String(e) }));
    }
  }

  const frames = exported?.frames ?? 0;
  const frameSrc =
    exported?.buildDir && frames > 0 && (exported.tier === 1 || exported.container)
      ? `/api/frame?build=${encodeURIComponent(exported.buildDir)}&scene=${version?.sceneClass ?? SCENE}&n=${frame}&w=640`
      : null;

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-6 py-8 text-neutral-200">
      <VersionBar />
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-neutral-100">
            pocketanim harness
          </h1>
          <p className="mt-1 max-w-xl text-sm text-neutral-400">
            Pick a visual style, then describe the scene. Diagrams, charts, and
            the rest are used only when they explain the idea, drawn in that
            style.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/forge" className="text-sm text-sky-300 underline-offset-2 hover:underline">
            Lecture Forge →
          </Link>
          {status?.manim ? (
            <Badge tone="good">Manim {status.manim}</Badge>
          ) : (
            <Badge tone="bad">Manim missing</Badge>
          )}
          <Badge tone={status?.fixture === false ? "good" : "neutral"}>
            {status?.fixture === false ? status.model : "offline fixture"}
          </Badge>
          {status && !status.latex && <Badge tone="warn">no LaTeX</Badge>}
          {status && status.chirp === false && (
            <Badge tone="bad">no voice: set GEMINI_API_KEY</Badge>
          )}
        </div>
      </header>

      {status && !status.manim && (
        <div className="mb-4 rounded-md border border-amber-900 bg-amber-950/40 p-3 text-sm text-amber-100">
          <p className="font-medium">
            Export cannot run until Manim is installed.
          </p>
          <p className="mt-1 text-amber-200/80">
            The page was calling the system Python, which has no{" "}
            <code>manim</code> module. From the repo root:
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-2 text-xs">
            harness/scripts/setup-python.sh
          </pre>
          {status.error && (
            <pre className="mt-2 whitespace-pre-wrap text-xs text-amber-200/70">
              {status.error}
            </pre>
          )}
        </div>
      )}

      {status && !status.latex && status.manim && (
        <p className="mb-4 text-xs text-neutral-500">
          LaTeX is not installed, so equations (MathTex, Tex, axis numbers) are
          drawn as plain text. Use the LaTeX download in the bar above to typeset them.
        </p>
      )}

      {error && (
        <div className="mb-4 whitespace-pre-wrap rounded-md border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <section className="mb-4">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-medium text-neutral-200">Template</h2>
          <p className="text-xs text-neutral-500">
            {template.name} — {template.summary}
          </p>
        </div>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {TEMPLATES.map((item) => (
            <TemplateCard
              key={item.id}
              template={item}
              selected={templateId === item.id}
              onSelect={() => setTemplateId(item.id)}
            />
          ))}
        </div>
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Content</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Textarea
                rows={6}
                placeholder={
                  "First line becomes the title.\nEach line after it becomes a beat."
                }
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
              <div className="flex flex-col gap-2 rounded border border-neutral-800 p-2 text-xs text-neutral-400">
                <label className="flex cursor-pointer items-center gap-2">
                  <span className="rounded bg-neutral-800 px-2 py-1 text-neutral-200 hover:bg-neutral-700">
                    {doc.busy ? "Reading the PDF…" : "Upload lecture PDF"}
                  </span>
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    className="hidden"
                    data-testid="pdf-upload"
                    disabled={doc.busy}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) uploadDocument(file);
                      e.target.value = "";
                    }}
                  />
                  <span>
                    {doc.id
                      ? `${doc.name}: ${doc.pages} pages, ${doc.figures?.length ?? 0} figures (${doc.source})`
                      : "Its text becomes the content; its diagrams are shown in the lecture."}
                  </span>
                  {doc.id && (
                    <button type="button" className="ml-auto underline-offset-2 hover:underline"
                      onClick={() => setDoc({ busy: false })}>
                      remove
                    </button>
                  )}
                </label>
                {doc.note && <span className="text-amber-300/80">{doc.note}</span>}
                {doc.error && <span className="text-rose-300">{doc.error}</span>}
                {!!doc.figures?.length && (
                  <>
                    <span className="text-neutral-400">Figures in the lecture — remove any you do not want:</span>
                    <div className="flex gap-2 overflow-x-auto pb-1" data-testid="pdf-figures">
                      {doc.figures.map((f) => (
                        <div key={f.id} className="relative shrink-0">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={f.url} alt={f.caption} title={`${f.id}: ${f.caption}`}
                            className="h-20 rounded border border-neutral-700 bg-white object-contain" />
                          <button type="button" aria-label={`remove ${f.id}`} title={`Leave ${f.id} out of the lecture`}
                            data-testid={`remove-${f.id}`}
                            onClick={() => changeFigures(f.id)}
                            className="absolute right-0.5 top-0.5 h-5 w-5 rounded-full bg-neutral-900/85 text-xs leading-5 text-white hover:bg-rose-600">
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  </>
                )}
                {!!doc.excluded?.length && (
                  <span className="text-neutral-500" data-testid="pdf-excluded">
                    {doc.excluded.length} figure{doc.excluded.length > 1 ? "s" : ""} left out ({doc.excluded.map((f) => f.id).join(", ")}).{" "}
                    <button type="button" className="underline underline-offset-2 hover:text-neutral-300"
                      onClick={() => changeFigures(null)}>
                      restore all
                    </button>
                  </span>
                )}
              </div>
              {template.kind === "lecture" && (
                <div className="flex flex-col gap-2 rounded border border-neutral-800 p-2 text-xs text-neutral-400"
                  data-testid="reference-video">
                  <span className="text-neutral-300">Reference video (YouTube)</span>
                  {reference.id ? (
                    <span className="flex items-center gap-2">
                      <span>
                        {reference.title}: {reference.parts} parts
                        {reference.duration ? `, ${Math.round(reference.duration / 60)} min` : ""}
                        {reference.language ? ` (${reference.language} captions)` : ""}. The lecture follows its
                        structure, its examples and its solved problems, with its own diagrams.
                      </span>
                      <button type="button" className="ml-auto underline-offset-2 hover:underline"
                        onClick={() => setReference({ busy: false, url: "", transcript: "", paste: false })}>
                        remove
                      </button>
                    </span>
                  ) : (
                    <>
                      <div className="flex gap-2">
                        <input type="url" placeholder="https://www.youtube.com/watch?v=…" value={reference.url}
                          data-testid="reference-url"
                          onChange={(e) => setReference((r) => ({ ...r, url: e.target.value }))}
                          className="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-neutral-200" />
                        <button type="button" disabled={reference.busy || (!reference.url.trim() && !reference.transcript.trim())}
                          onClick={addReference} data-testid="reference-add"
                          className="rounded bg-neutral-800 px-2 py-1 text-neutral-100 hover:bg-neutral-700 disabled:opacity-50">
                          {reference.busy ? "Reading…" : "Use as reference"}
                        </button>
                      </div>
                      <button type="button" className="self-start underline-offset-2 hover:underline"
                        onClick={() => setReference((r) => ({ ...r, paste: !r.paste }))}>
                        {reference.paste ? "hide the transcript box" : "or paste its transcript"}
                      </button>
                      {reference.paste && (
                        <Textarea rows={4} data-testid="reference-transcript"
                          placeholder={"On YouTube: … under the video > Show transcript, select it all, copy, paste here.\nTimestamps (2:15) are kept."}
                          value={reference.transcript}
                          onChange={(e) => setReference((r) => ({ ...r, transcript: e.target.value }))} />
                      )}
                      <span>
                        Its transcript sets the lecture&apos;s structure: the same topics in the same order, its examples
                        and solved problems, explained again with diagrams. The length follows the video unless you pick one.
                      </span>
                    </>
                  )}
                  {reference.note && <span className="text-amber-300/80">{reference.note}</span>}
                  {reference.error && <span className="text-rose-300">{reference.error}</span>}
                </div>
              )}
              <div className="flex items-center justify-end">
                <button
                  type="button"
                  className="shrink-0 text-xs text-neutral-300 underline-offset-2 hover:underline"
                  onClick={() => {
                    setContent(template.example);
                  }}
                >
                  Use {template.name.toLowerCase()} example
                </button>
              </div>
              {template.kind === "lecture" && (
                <div className="flex flex-col gap-1 text-xs text-neutral-400">
                  <label className="flex items-center gap-2">
                    <span className="text-neutral-300">Video length</span>
                    <select
                      aria-label="Video length"
                      data-testid="lecture-length"
                      className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-200"
                      value={minutes ?? ""}
                      disabled={!!busy}
                      onChange={(e) => setMinutes(e.target.value ? Number(e.target.value) : null)}
                    >
                      <option value="">Automatic (from the content)</option>
                      {LENGTH_CHOICES.map((m) => (
                        <option key={m} value={m}>
                          {m} minutes
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex items-center gap-2">
                    <span className="text-neutral-300">Subject</span>
                    <select
                      aria-label="Subject"
                      data-testid="lecture-subject"
                      className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-200"
                      value={subject}
                      disabled={!!busy}
                      onChange={(e) => setSubject(e.target.value)}
                    >
                      {SUBJECT_CHOICES.map(([id, name]) => (
                        <option key={id} value={id}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex items-center gap-2">
                    <span className="text-neutral-300">Language</span>
                    <select
                      aria-label="Language"
                      data-testid="lecture-language"
                      className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-200"
                      value={language}
                      disabled={!!busy}
                      onChange={(e) => setLanguage(e.target.value)}
                    >
                      <option value="auto">Automatic (the content&apos;s)</option>
                      <option value="english">English</option>
                      <option value="hindi">Hindi</option>
                      <option value="hinglish">Hinglish: English content, explained in easy Hindi</option>
                    </select>
                  </label>
                  <label className="flex items-center gap-2">
                    <span className="text-neutral-300">Transcript model</span>
                    <input
                      aria-label="Transcript model"
                      data-testid="transcript-model"
                      className="w-72 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 font-mono text-xs text-neutral-200"
                      placeholder={status?.transcriptModel ?? "OpenRouter model id"}
                      value={writer}
                      disabled={!!busy}
                      onChange={(e) => chooseWriter(e.target.value)}
                    />
                    <span className="text-neutral-500">
                      writes what the teacher says; the video (pictures, Manim) uses {status?.model ?? "OPENROUTER_MODEL"}
                    </span>
                  </label>
                  <span>
                    Mathematics, physics and chemistry are taught as theory, then long problems solved step by step on
                    labelled diagrams and graphs.
                  </span>
                  <span>
                    The topics come from your content. The length decides how deep each one goes: a longer video
                    gives more examples for each statement and asks the class more questions.
                  </span>
                </div>
              )}
              <Button
                onClick={() => runGenerate(false)}
                disabled={(!content.trim() && !reference.id) || !!busy}
              >
                {busy ?? `Generate in ${template.name}`}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Paste Manim</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Textarea
                rows={8}
                className="font-mono text-xs"
                placeholder={"from manim import *\n\nclass GeneratedScene(Scene):\n    def construct(self):\n        ..."}
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
              />
              <Button onClick={playPasted} disabled={!pasted.trim() || !!busy} variant="outline">
                {busy && pasted.trim() ? busy : "Play this code"}
              </Button>
            </CardContent>
          </Card>

          {version && (
            <Card>
              <CardHeader>
                <CardTitle>
                  Scene source — v{version.n}
                  <span className="ml-2 font-normal text-neutral-500">
                    {version.model}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {(version.trace.length > 0 || busy) && (
                  <div
                    id="agent-log"
                    ref={logRef}
                    className="max-h-96 space-y-2 overflow-auto rounded bg-neutral-900 p-2 text-xs"
                  >
                    <p className="sticky top-0 bg-neutral-900 pb-1 text-neutral-400">
                      Agent log · {version.inputTokens ?? 0} in ·{" "}
                      {version.outputTokens ?? 0} out · $
                      {(version.costUsd ?? 0).toFixed(4)}
                      {version.voiceUsd !== undefined && (
                        <span
                          data-testid="voice-cost"
                          title={version.voiceLecture
                            ? `The whole lecture's voice: $${version.voiceLecture.usd.toFixed(4)} for ${version.voiceLecture.lines} lines` +
                              (version.voiceLecture.unknown ? ` (${version.voiceLecture.unknown} spoken before costs were kept)` : "") +
                              ". A line is paid for once; a rebuild speaks only new or changed lines."
                            : undefined}
                        >
                          {" "}· voice ${version.voiceUsd.toFixed(4)} · total $
                          {((version.costUsd ?? 0) + version.voiceUsd).toFixed(4)}
                        </span>
                      )}
                      {busy ? ` · ${busy}` : ""}
                    </p>
                    {version.trace.length === 0 && (
                      <p className="text-neutral-500">Waiting for the agent…</p>
                    )}
                    {version.trace.map((event, i) => (
                      <TraceLine key={i} event={event} />
                    ))}
                  </div>
                )}
                {version.transcript && (
                  <details className="rounded border border-neutral-800 p-2 text-xs text-neutral-300" data-testid="transcript">
                    <summary className="cursor-pointer text-neutral-200">
                      Transcript · {version.transcript.split(/\s+/).length} words (about{" "}
                      {Math.round(version.transcript.split(/\s+/).length / 100)} min)
                      <button type="button" className="ml-3 text-neutral-400 underline-offset-2 hover:underline"
                        onClick={(e) => {
                          e.preventDefault();
                          const url = URL.createObjectURL(new Blob([version.transcript ?? ""], { type: "text/plain;charset=utf-8" }));
                          const link = document.createElement("a");
                          link.href = url;
                          link.download = `transcript-v${version.n}.txt`;
                          link.click();
                          URL.revokeObjectURL(url);
                        }}>
                        download
                      </button>
                    </summary>
                    <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap font-sans leading-relaxed">{version.transcript}</pre>
                  </details>
                )}
                <Textarea
                  rows={12}
                  className="font-mono text-xs"
                  value={version.source}
                  onChange={(e) =>
                    setVersions((all) =>
                      all.map((v, i) =>
                        i === current
                          ? {
                              ...v,
                              source: e.target.value,
                              exported: undefined,
                              ir: undefined,
                            }
                          : v,
                      ),
                    )
                  }
                />
                <Button variant="outline" onClick={runExport} disabled={!!busy}>
                  {busy && version ? busy : "Rebuild preview"}
                </Button>
              </CardContent>
            </Card>
          )}

          {version && (
            <Card>
              <CardHeader>
                <CardTitle>Change it</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <Textarea
                  rows={3}
                  placeholder="Make the title blue and hold it longer."
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                />
                <Button
                  variant="outline"
                  onClick={() => runGenerate(true)}
                  disabled={!instruction.trim() || !!busy}
                >
                  Apply and preview
                </Button>
                {versions.length > 1 && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {versions.map((v, i) => (
                      <button
                        key={`${v.n}-${v.part?.index ?? 0}`}
                        onClick={() => {
                          setCurrent(i);
                          setFrame(0);
                          setError(null);
                        }}
                        title={v.part ? v.part.title : v.instruction ?? "first version"}
                        className={`rounded border px-2 py-1 text-xs ${
                          i === current
                            ? "border-neutral-400 text-neutral-100"
                            : "border-neutral-800 text-neutral-500"
                        }`}
                      >
                        v{v.n}{v.part ? ` · part ${v.part.index}/${v.part.of}` : ""}
                      </button>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-4 lg:sticky lg:top-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Preview
                {exported?.tier === 1 && <Badge tone="good">tier 1</Badge>}
                {exported?.tier === 3 && <Badge tone="warn">tier 3</Badge>}
                {exported?.tier === null && <Badge tone="bad">failed</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {version?.part && (
                <div className="flex flex-col gap-1">
                  <p className="text-xs text-neutral-400">
                    This lecture runs about{" "}
                    {Math.round(versions.filter((v) => v.n === version.n && v.part).reduce((t, v) => t + (v.part?.minutes ?? 0), 0))}{" "}
                    min, made as {version.part.of} micro-lectures, one per topic, each with its own opening and
                    recap. Pick one to play:
                  </p>
                  <div role="tablist" aria-label="Videos of this lecture" className="flex flex-wrap gap-2">
                    {versions.map((v, i) => v.n === version.n && v.part ? (
                      <button
                        key={v.part.index}
                        role="tab"
                        aria-selected={i === current}
                        onClick={() => {
                          setCurrent(i);
                          setFrame(0);
                          setError(null);
                        }}
                        title={v.part.title}
                        className={`rounded border px-3 py-1.5 text-xs ${
                          i === current
                            ? "border-amber-400 text-neutral-100"
                            : "border-neutral-700 text-neutral-400 hover:border-neutral-500"
                        }`}
                      >
                        {v.part.title.startsWith("Lecture ") ? v.part.title : `Part ${v.part.index}`}
                        {" "}· {Math.round(v.part.minutes)} min
                        {!v.exported ? " · building…" : v.exported.error ? " · failed" : ""}
                      </button>
                    ) : null)}
                  </div>
                </div>
              )}
              {!version && (
                <p className="text-sm text-neutral-500">
                  The animation plays here for you. The agent that wrote the
                  scene is not shown this picture and does not revise from it.
                </p>
              )}
              {version && !exported && (
                <p className="text-sm text-neutral-500">
                  {busy ??
                    "Source changed. Rebuild the preview to play this version."}
                </p>
              )}
              {exported?.tier === 1 && ir === undefined && (
                <p className="text-sm text-neutral-500">
                  Expanding the program for playback…
                </p>
              )}
              {ir && "mode" in ir && ir.mode === "2d" && (
                  <Player
                    key={version?.n}
                    ir={ir}
                    autoPlay
                    audioSrc={version?.voiceUrl}
                    imageUrl={exported?.buildDir ? (asset) =>
                      `/api/image?build=${encodeURIComponent(exported.buildDir!)}&file=${asset}` : undefined}
                    segmentUrl={exported?.buildDir ? (k) =>
                      `/api/ir?build=${encodeURIComponent(exported.buildDir!)}&scene=${exported.scene ?? "GeneratedScene"}&segment=${k}` : undefined}
                  />
                )}
              {(exported?.tier === 1 || exported?.container) &&
                ir &&
                "mode" in ir &&
                (ir.mode === "3d" || ir.mode === "frames") &&
                frameSrc && (
                  <>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={frameSrc}
                      alt={`frame ${frame}`}
                      className="w-full rounded border border-neutral-800 bg-black"
                    />
                    <input
                      type="range"
                      min={0}
                      max={Math.max(0, frames - 1)}
                      value={frame}
                      onChange={(e) => setFrame(Number(e.target.value))}
                      className="w-full"
                    />
                    <p className="text-xs text-neutral-500">
                      {ir.mode === "frames"
                        ? "This film is too long to send as one picture. Frames are rendered as you scrub."
                        : "3D scene — frames rendered on the server, one at a time."}
                    </p>
                  </>
                )}
              {exported?.tier === 1 && ir === null && (
                <p className="text-sm text-neutral-500">
                  The program built, but its geometry could not be loaded.
                </p>
              )}
              {exported?.tier === 3 && ir && !exported.container && (
                <p className="text-sm text-neutral-400">
                  {(exported.blockers ?? []).every((b) => b.startsWith("raster image"))
                    ? "Photos and figures are drawn from the build's images. The phone app plays this scene as sampled frames."
                    : "Some effects in this file are not in the preview, so those parts are missing. The rest is playing."}
                </p>
              )}
              {exported?.container && ir && "mode" in ir && ir.mode === "2d" && (
                <p className="text-sm text-neutral-400">
                  Playing every sampled frame.
                </p>
              )}
              {exported && exported.tier !== 1 && !exported.error && !ir && (
                <p className="text-sm text-neutral-400">
                  This scene did not stay on a tier-1 program, so there is no
                  faithful preview.
                </p>
              )}
              {exported?.tier === 1 && (
                <p className="text-xs text-neutral-500">
                  {exported.program_bytes} bytes ·{" "}
                  {exported.assets?.length ?? 0} assets · {frames} frames
                </p>
              )}
            </CardContent>
          </Card>

          {exported && (
            <Card>
              <CardHeader>
                <CardTitle>Build</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                {!!exported.blockers?.length && (
                  <ul className="list-inside list-disc text-amber-300">
                    {exported.blockers.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                )}
                {!!exported.skipped?.length && (
                  <div className="text-xs text-amber-300">
                    {exported.skipped.length} picture{exported.skipped.length > 1 ? "s" : ""} could not be drawn and
                    {exported.skipped.length > 1 ? " were" : " was"} left out; the narration plays on:
                    <ul className="mt-1 list-inside list-disc text-amber-200/90">
                      {exported.skipped.slice(0, 8).map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {exported.container && exported.buildDir && (
                  <p className="text-xs text-neutral-300">
                    The phone renders every frame from {exported.buildDir}/
                    {exported.container}
                  </p>
                )}
                {exported.container_error && (
                  <p className="text-xs text-rose-300">
                    Render: {exported.container_error}
                  </p>
                )}
                {exported.error && (
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-neutral-900 p-2 text-xs text-rose-300">
                    {exported.error}
                  </pre>
                )}
                {exported.program && (
                  <>
                    <button
                      type="button"
                      className="self-start text-xs text-neutral-400 underline-offset-2 hover:underline"
                      onClick={() => setShowProgram((open) => !open)}
                    >
                      {showProgram ? "Hide program" : "Show program"}
                    </button>
                    {showProgram && (
                      <pre className="max-h-48 overflow-auto rounded bg-neutral-900 p-2 font-mono text-xs text-neutral-300">
                        {exported.program}
                      </pre>
                    )}
                  </>
                )}
                {exported.buildDir && (
                  <div className="flex flex-col gap-1 text-xs text-neutral-400">
                    <div className="flex flex-wrap items-center gap-2">
                      <Button size="sm" onClick={downloadVideo} disabled={video.busy} data-testid="download-video">
                        {video.busy ? "Rendering video…" : "Download video"}
                      </Button>
                      <select
                        aria-label="Video quality"
                        className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-200"
                        value={video.quality}
                        disabled={video.busy}
                        onChange={(e) => setVideo((v) => ({ ...v, quality: e.target.value }))}
                      >
                        <option value="l">480p</option>
                        <option value="m">720p</option>
                        <option value="h">1080p</option>
                      </select>
                    </div>
                    <span>
                      The finished MP4, rendered by Manim with its narration. The first render of a
                      build takes a while; after that it downloads at once.
                    </span>
                    {video.error && (
                      <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-neutral-900 p-2 text-rose-300">
                        {video.error}
                      </pre>
                    )}
                  </div>
                )}
                {exported.tier === 1 && exported.buildDir && (
                  <div className="text-xs text-neutral-400">
                    <a
                      className="text-sky-300 underline-offset-2 hover:underline"
                      href={`/api/bundle?build=${encodeURIComponent(exported.buildDir)}&scene=${version?.sceneClass ?? SCENE}`}
                    >
                      Download for the phone
                    </a>{" "}
                    — the lecture as a program the pocketanim app plays (no video file). Open this page on the
                    phone and tap the link, then open the download with pocketanim; or send the zip to the phone
                    and use <span className="text-neutral-300">Import</span> in the app.
                  </div>
                )}
                {((exported.tier === 1 && exported.buildDir) || (version?.part && versions.some((v) =>
                  v.n === version.n && v.part && v.exported?.tier === 1 && v.exported.buildDir))) && (
                  <div className="flex flex-col gap-1 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        onClick={saveLecture}
                        disabled={saving.busy || saving.ready === false}
                        title={saving.problem ?? "Save the lecture and its phone files to Supabase"}
                      >
                        {saving.busy ? "Saving…" : "Save"}
                      </Button>
                      <span>
                        {saving.ready === false
                          ? `Saving is not set up: ${saving.problem}`
                          : version?.part
                            ? `Saves the ${version.part.of} micro-lectures that are built (one that failed is named), each to the phone app's Saved list.`
                            : "Saves the lecture, and its .panim files for the phone app's Saved list."}
                      </span>
                    </div>
                    {saving.busy && saving.progress && (
                      <div className="flex flex-col gap-1">
                        <div className="h-1.5 w-full overflow-hidden rounded bg-neutral-800">
                          <div className="h-full bg-emerald-400 transition-all" style={{ width: `${saving.percent ?? 0}%` }} />
                        </div>
                        <span className="text-neutral-300">{saving.progress}</span>
                      </div>
                    )}
                    {saving.result && (
                      <p className="text-emerald-300">
                        Saved {saving.result.lectures.length} video{saving.result.lectures.length > 1 ? "s" : ""} (
                        {Math.round(saving.result.lectures.reduce((n, l) => n + l.bytes, 0) / 1024)} KB): open{" "}
                        <span className="text-neutral-200">Saved</span> in the phone app to play.
                        {saving.result.skipped.length > 0 && (
                          <span className="block text-amber-300">Not saved: {saving.result.skipped.join("; ")}</span>
                        )}
                      </p>
                    )}
                    {saving.error && (/^Already saved/.test(saving.error)
                      ? <p className="text-emerald-300">{saving.error}</p>
                      : <p className="text-amber-300">Not saved: {saving.error}</p>)}
                    {saving.ready && (
                      <p>
                        <button className="underline hover:text-neutral-200" onClick={checkSaved}>
                          Check the phone&apos;s Saved list
                        </button>
                        {saving.status && <span className="ml-2 text-neutral-300">{saving.status}</span>}
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </main>
  );
}
