"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { TEMPLATES } from "@/lib/templates";
import { TemplateCard } from "@/components/template-card";
import { Player } from "@/components/player";
import type { SceneIR } from "@/lib/pocketanim";

type ExportState = {
  tier: 1 | 3 | null;
  scene?: string;
  blockers?: string[];
  program?: string | null;
  source?: string;
  program_bytes?: number;
  assets?: string[];
  container?: string;
  container_error?: string;
  buildDir?: string;
  frames?: number;
  error?: string;
  stored?: { configured: boolean; reason?: string; error?: string };
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
};

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
  exported?: ExportState;
  ir?: SceneIR | null;
  sceneClass?: string;
};

type Status = {
  python: string;
  manim: string | null;
  latex: boolean;
  kokoro?: boolean;
  fixture: boolean;
  model: string;
  error?: string;
};

const SCENE = "GeneratedScene";

function sceneClassOf(source: string): string {
  if (/class\s+GeneratedScene\b/.test(source)) return SCENE;
  const found = source.match(/class\s+(\w+)\s*\(\s*(?:ThreeDScene|Scene)\s*\)/);
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
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frame, setFrame] = useState(0);
  const [status, setStatus] = useState<Status | null>(null);
  const [showProgram, setShowProgram] = useState(false);
  const [pasted, setPasted] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  const version = current >= 0 ? versions[current] : undefined;
  const exported = version?.exported;
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
    if (!response.ok) throw new Error(data.error ?? `${response.status}`);
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

  async function attachBuild(
    index: number,
    source: string,
    instruction: string | null,
    model: string,
  ) {
    const sceneClass = sceneClassOf(source);
    setBusy("Running Manim and building the program…");
    const exported: ExportState = await post("/api/export", {
      source,
      sceneClass,
      instruction,
      model,
    });
    const played = exported.scene || sceneClass;
    let ir: SceneIR | null | undefined;
    if (exported.buildDir && exported.program && !exported.error) {
      setBusy("Loading the preview…");
      ir = await loadPreview(exported.buildDir, played);
    } else if (exported.error) {
      setError(exported.error);
    }
    const fixed = exported.source ?? source;
    setVersions((all) =>
      all.map((v, i) => (i === index ? { ...v, exported, ir, sceneClass: played, source: fixed } : v)),
    );
    setFrame(0);
  }

  async function runGenerate(edit: boolean) {
    setError(null);
    setBusy(
      edit ? "Agent is rewriting the scene…" : "Agent is writing the scene…",
    );
    const index = versions.length;
    const styleId = templateId;
    const next: Version = {
      n: versions.length + 1,
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
      n: versions.length + 1,
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
      if (/^# voice:/m.test(source)) {
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

  const frames = exported?.frames ?? 0;
  const frameSrc =
    exported?.buildDir && frames > 0 && (exported.tier === 1 || exported.container)
      ? `/api/frame?build=${encodeURIComponent(exported.buildDir)}&scene=${version?.sceneClass ?? SCENE}&n=${frame}&w=640`
      : null;

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-6 py-8 text-neutral-200">
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
        <div className="flex flex-wrap gap-2">
          {status?.manim ? (
            <Badge tone="good">Manim {status.manim}</Badge>
          ) : (
            <Badge tone="bad">Manim missing</Badge>
          )}
          <Badge tone={status?.fixture === false ? "good" : "neutral"}>
            {status?.fixture === false ? status.model : "offline fixture"}
          </Badge>
          {status && !status.latex && <Badge tone="warn">no LaTeX</Badge>}
          {status && status.kokoro === false && (
            <Badge tone="warn">no Kokoro</Badge>
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
          LaTeX is not installed, so a scene that uses MathTex will fail until a
          TeX distribution is on PATH. Scenes written with Text still build.
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
              <Button
                onClick={() => runGenerate(false)}
                disabled={!content.trim() || !!busy}
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
                        key={v.n}
                        onClick={() => {
                          setCurrent(i);
                          setFrame(0);
                          setError(null);
                        }}
                        title={v.instruction ?? "first version"}
                        className={`rounded border px-2 py-1 text-xs ${
                          i === current
                            ? "border-neutral-400 text-neutral-100"
                            : "border-neutral-800 text-neutral-500"
                        }`}
                      >
                        v{v.n}
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
                  Some effects in this file are not in the preview, so those
                  parts are missing. The rest is playing.
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
                {exported.stored && !exported.stored.configured && (
                  <p className="text-xs text-neutral-500">
                    Not stored: {exported.stored.reason}
                  </p>
                )}
                {exported.stored?.error && (
                  <p className="text-xs text-amber-300">
                    Storage: {exported.stored.error}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </main>
  );
}
