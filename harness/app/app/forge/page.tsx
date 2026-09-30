"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { VersionBar } from "@/components/version-bar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { LENGTH_CHOICES } from "@/lib/templates";

type Registry = {
  engine?: string;
  styles?: Record<string, { label?: string; status?: string; extends?: string | null }>;
  templates?: Record<string, { label?: string }>;
  regions?: Record<string, { name?: string; battlefield?: boolean }>;
};

type JobRow = { id: string; title?: string; template?: string; style?: string; state?: string };

type Beat = { id: string; say: string; do: { op: string }[] };

type JobView = {
  id: string;
  running: boolean;
  state: {
    state: string;
    history: { state: string; at: number; note: string }[];
    open_questions?: string[];
    human_review?: unknown[];
    waived?: unknown[];
    errors?: { state: string; error: string }[];
    tokens?: { in: number; out: number };
    cost_usd?: number;
  } | null;
  outline: { target_minutes?: number; chapters: { id: string; title: string; slot: string; beats: Beat[] }[] } | null;
  report: {
    output?: Record<string, number | boolean | null>;
    voice?: string;
  } | null;
  log: string;
  files: string[];
  error?: string;
};

const STATES = [
  "intake", "resolve", "plan", "outline_review", "ground", "script", "validate", "narrate",
  "compile", "preview", "preview_review", "final_render", "deliver", "done",
];

const input =
  "rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-sm text-neutral-200 outline-none focus:border-neutral-500";

export default function ForgePage() {
  const [registry, setRegistry] = useState<Registry>({});
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<JobView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    id: "", title: "", subtitle: "", template: "auto", style: "auto", region: "",
    minutes: "", quality: "m", brief: "", reviewOutline: false, reviewPreview: false, phone: false,
  });
  const [note, setNote] = useState("");
  const [doc, setDoc] = useState<{ busy: boolean; id?: string; name?: string; summary?: string; error?: string }>({
    busy: false,
  });

  async function upload(file: File) {
    setDoc({ busy: true, name: file.name });
    const upload = new FormData();
    upload.append("file", file);
    try {
      const response = await fetch("/api/document", { method: "POST", body: upload });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
      setDoc({ busy: false, id: data.id, name: file.name,
        summary: `${data.pages} pages, ${data.figures.length} figures (${data.source})${data.note ? ` -- ${data.note}` : ""}` });
      setForm((f) => ({ ...f, title: f.title || file.name.replace(/\.pdf$/i, "") }));
    } catch (e) {
      setDoc({ busy: false, name: file.name, error: e instanceof Error ? e.message : String(e) });
    }
  }
  const [restyleTo, setRestyleTo] = useState("");
  /** A YouTube video the lecture follows: its link, or its transcript pasted when YouTube refuses the network. */
  const [video, setVideo] = useState<{ busy: boolean; id?: string; summary?: string; error?: string; url: string;
    transcript: string; paste: boolean }>({ busy: false, url: "", transcript: "", paste: false });

  async function addVideo() {
    setVideo((v) => ({ ...v, busy: true, error: undefined }));
    try {
      const response = await fetch("/api/document", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(video.paste ? { transcript: video.transcript, youtube: video.url || undefined } : { youtube: video.url }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
      const minutes = data.video?.duration ? Math.round(data.video.duration / 60) : 0;
      setVideo((v) => ({ ...v, busy: false, id: data.id,
        summary: `${data.video?.title ?? "Transcript"}: ${data.parts?.length ?? 0} parts${minutes ? `, ${minutes} min` : ""}` }));
      setForm((f) => ({ ...f, title: f.title || data.video?.title || "", minutes: f.minutes || (minutes ? String(Math.min(40, Math.max(3, minutes))) : "") }));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setVideo((v) => ({ ...v, busy: false, error: message, paste: v.paste || /paste/i.test(message) }));
    }
  }

  const loadJobs = useCallback(async () => {
    const response = await fetch("/api/forge");
    const body = await response.json();
    setRegistry(body.registry ?? {});
    setJobs(body.jobs ?? []);
  }, []);

  const loadView = useCallback(async (id: string) => {
    const response = await fetch(`/api/forge/${id}`);
    const body = (await response.json()) as JobView;
    if (body.error) setError(body.error);
    else setView(body);
  }, []);

  useEffect(() => {
    loadJobs().catch((e) => setError(String(e)));
  }, [loadJobs]);

  // Poll while a job runs; its state.json is the progress report.
  useEffect(() => {
    if (!selected) return;
    loadView(selected);
    const timer = setInterval(() => {
      loadView(selected);
    }, 2500);
    return () => clearInterval(timer);
  }, [selected, loadView]);

  useEffect(() => {
    if (view && !view.running) loadJobs();
  }, [view?.running, view?.state?.state, loadJobs]); // eslint-disable-line react-hooks/exhaustive-deps

  async function send(url: string, body: unknown) {
    setError(null);
    setBusy(true);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    const data = await send("/api/forge", { ...form, id: form.id || form.title, documentId: doc.id, referenceId: video.id });
    if (data?.id) {
      setSelected(data.id);
      loadJobs();
    }
  }

  const file = (name: string, download = false) =>
    `/api/forge/${view?.id}/file?name=${encodeURIComponent(name)}${download ? "&download=1" : ""}`;
  const has = (name: string) => view?.files.includes(name);
  const state = view?.state?.state ?? "";
  const stateIndex = STATES.indexOf(state);
  const waitingForReview = !view?.running && (state === "outline_review" || state === "preview_review");
  const stopped = !view?.running && state !== "done" && view?.state?.history?.length;

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-6 py-8 text-neutral-200">
      <VersionBar />
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-neutral-100">Lecture Forge</h1>
          <p className="mt-1 max-w-2xl text-sm text-neutral-400">
            Content, a video template and a style pack in; a narrated, animated MP4 out. The template decides what
            happens, the style how it looks and sounds, the content what it is about.
          </p>
        </div>
        <Link href="/" className="text-sm text-sky-300 underline-offset-2 hover:underline">
          ← Manim editor
        </Link>
      </header>

      {error && (
        <div className="mb-4 whitespace-pre-wrap rounded-md border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>New video</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              <input className={input} placeholder="Title" value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <input className={input} placeholder="Subtitle (optional)" value={form.subtitle}
                onChange={(e) => setForm({ ...form, subtitle: e.target.value })} />
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1 text-xs text-neutral-400">
                  Template
                  <select className={input} value={form.template} aria-label="Template"
                    onChange={(e) => setForm({ ...form, template: e.target.value })}>
                    <option value="auto">Auto (from the content)</option>
                    {Object.entries(registry.templates ?? {}).map(([id, t]) => (
                      <option key={id} value={id}>{t.label ?? id}</option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs text-neutral-400">
                  Style
                  <select className={input} value={form.style} aria-label="Style"
                    onChange={(e) => setForm({ ...form, style: e.target.value })}>
                    <option value="auto">Auto (the subject&apos;s style)</option>
                    {Object.entries(registry.styles ?? {}).map(([id, s]) => (
                      <option key={id} value={id}>{(s.label ?? id) + (s.status === "draft" ? " (draft)" : "")}</option>
                    ))}
                  </select>
                </label>
              </div>
              <input className={input} placeholder="Region: a pack id or a place (e.g. rajasthan, Kenya)"
                value={form.region} list="forge-regions" onChange={(e) => setForm({ ...form, region: e.target.value })} />
              <datalist id="forge-regions">
                {Object.entries(registry.regions ?? {}).map(([id, r]) => (
                  <option key={id} value={id}>{r.name}</option>
                ))}
              </datalist>
              <div className="grid grid-cols-2 gap-2">
                <select className={input} value={form.minutes} aria-label="Video length"
                  title="The length decides how deep each topic goes: examples per statement and questions for the class"
                  onChange={(e) => setForm({ ...form, minutes: e.target.value })}>
                  <option value="">Length: automatic</option>
                  {LENGTH_CHOICES.map((m) => (
                    <option key={m} value={String(m)}>{m} minutes</option>
                  ))}
                </select>
                <select className={input} value={form.quality} aria-label="Quality"
                  onChange={(e) => setForm({ ...form, quality: e.target.value })}>
                  <option value="l">480p (fast)</option>
                  <option value="m">720p</option>
                  <option value="h">1080p</option>
                </select>
              </div>
              <label className="flex cursor-pointer flex-wrap items-center gap-2 text-xs text-neutral-400">
                <span className="rounded bg-neutral-800 px-2 py-1 text-neutral-200 hover:bg-neutral-700">
                  {doc.busy ? "Reading the PDF…" : "Upload lecture PDF"}
                </span>
                <input type="file" accept="application/pdf,.pdf" className="hidden" data-testid="forge-pdf"
                  disabled={doc.busy}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) upload(file);
                    e.target.value = "";
                  }} />
                <span className={doc.error ? "text-rose-300" : ""}>
                  {doc.error ?? (doc.id ? `${doc.name}: ${doc.summary}` : "text and figures become the lecture's source")}
                </span>
              </label>
              <div className="flex flex-col gap-1.5 text-xs text-neutral-400" data-testid="forge-video">
                {video.id ? (
                  <span className="flex items-center gap-2">
                    <span className="rounded bg-neutral-800 px-2 py-1 text-neutral-200">YouTube reference</span>
                    <span>{video.summary}. The lecture follows its structure.</span>
                    <button type="button" className="ml-auto underline-offset-2 hover:underline"
                      onClick={() => setVideo({ busy: false, url: "", transcript: "", paste: false })}>remove</button>
                  </span>
                ) : (
                  <>
                    <div className="flex gap-2">
                      <input type="url" className={`${input} min-w-0 flex-1 text-xs`} placeholder="YouTube link: https://www.youtube.com/watch?v=…"
                        value={video.url} data-testid="forge-video-url"
                        onChange={(e) => setVideo((v) => ({ ...v, url: e.target.value }))} />
                      <button type="button" disabled={video.busy || (!video.url.trim() && !video.transcript.trim())}
                        onClick={addVideo}
                        className="rounded bg-neutral-800 px-2 py-1 text-neutral-100 hover:bg-neutral-700 disabled:opacity-50">
                        {video.busy ? "Reading…" : "Use as reference"}
                      </button>
                    </div>
                    <button type="button" className="self-start underline-offset-2 hover:underline"
                      onClick={() => setVideo((v) => ({ ...v, paste: !v.paste }))}>
                      {video.paste ? "hide the transcript box" : "or paste its transcript"}
                    </button>
                    {video.paste && (
                      <Textarea rows={4} placeholder={"On YouTube: … under the video > Show transcript, select it all, copy, paste here."}
                        value={video.transcript} onChange={(e) => setVideo((v) => ({ ...v, transcript: e.target.value }))} />
                    )}
                  </>
                )}
                {video.error && <span className="text-rose-300">{video.error}</span>}
              </div>
              <Textarea rows={9} placeholder="The content: notes, an article, a chapter. Every number in the video will come from here."
                value={form.brief} onChange={(e) => setForm({ ...form, brief: e.target.value })} />
              <div className="flex flex-col gap-1 text-xs text-neutral-400">
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={form.reviewOutline}
                    onChange={(e) => setForm({ ...form, reviewOutline: e.target.checked })} />
                  Stop for me to review the outline
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={form.reviewPreview}
                    onChange={(e) => setForm({ ...form, reviewPreview: e.target.checked })} />
                  Stop for me to review the 480p preview
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.checked })} />
                  Also export the chapters for the phone player
                </label>
              </div>
              <Button onClick={create} disabled={busy || (!form.brief.trim() && !doc.id && !video.id) || !(form.id || form.title)}>
                Make the video
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Jobs</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-1 text-sm">
              {!jobs.length && <p className="text-xs text-neutral-500">No jobs yet.</p>}
              {jobs.map((job) => (
                <button key={job.id} type="button" onClick={() => setSelected(job.id)}
                  className={`flex items-center justify-between gap-2 rounded px-2 py-1.5 text-left hover:bg-neutral-800 ${
                    selected === job.id ? "bg-neutral-800" : ""}`}>
                  <span className="truncate">
                    {job.title ?? job.id}
                    <span className="ml-2 text-xs text-neutral-500">{job.template} · {job.style}</span>
                  </span>
                  <Badge tone={job.state === "done" ? "good" : "neutral"}>{job.state}</Badge>
                </button>
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          {!view && (
            <Card>
              <CardContent className="py-10 text-center text-sm text-neutral-500">
                Start a video, or pick a job to see where it stands.
              </CardContent>
            </Card>
          )}

          {view && (
            <Card>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  {view.id}
                  <Badge tone={state === "done" ? "good" : view.running ? "neutral" : "warn"} data-testid="job-state">{state}</Badge>
                  {view.running && <span className="text-xs font-normal text-sky-300">running…</span>}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                <ol className="flex flex-wrap gap-1 text-[11px]">
                  {STATES.filter((s) => s !== "done").map((s, i) => (
                    <li key={s} className={`rounded px-1.5 py-0.5 ${
                      i < stateIndex || state === "done" ? "bg-emerald-900/60 text-emerald-200"
                        : i === stateIndex ? "bg-sky-900/70 text-sky-100" : "bg-neutral-800 text-neutral-500"}`}>
                      {s.replace("_", " ")}
                    </li>
                  ))}
                </ol>

                {has("out/video.mp4") && (
                  <video key={view.state?.history?.length} controls className="w-full rounded bg-black"
                    src={file("out/video.mp4")} poster={has("out/thumbnail.png") ? file("out/thumbnail.png") : undefined}>
                    {has("out/video.srt") && <track kind="subtitles" src={file("out/video.srt")} default />}
                  </video>
                )}
                {has("out/video.mp4") && (
                  <div className="flex flex-wrap gap-3 text-xs">
                    <a className="text-sky-300 hover:underline" href={file("out/video.mp4", true)} data-testid="forge-download">
                      Download video
                    </a>
                    {has("out/video.srt") && <a className="text-sky-300 hover:underline" href={file("out/video.srt", true)}>Subtitles (.srt)</a>}
                    {has("out/chapters.txt") && <a className="text-sky-300 hover:underline" href={file("out/chapters.txt", true)}>Chapters</a>}
                    {has("out/thumbnail.png") && <a className="text-sky-300 hover:underline" href={file("out/thumbnail.png", true)}>Thumbnail</a>}
                    {has("qa/report.json") && <a className="text-sky-300 hover:underline" href={file("qa/report.json")}>QA report</a>}
                    {has(`out/${view.id}-phone.zip`) && (
                      <a className="text-sky-300 hover:underline" href={file(`out/${view.id}-phone.zip`, true)}>
                        Phone library (.zip)
                      </a>
                    )}
                  </div>
                )}
                {view.report?.output && (
                  <div className="flex flex-wrap gap-2 text-xs">
                    {(["loudness_ok", "music_ok", "length_ok"] as const).map((k) =>
                      view.report?.output?.[k] === undefined ? null : (
                        <Badge key={k} tone={view.report.output[k] ? "good" : "warn"}>
                          {k.replace("_ok", "")}: {view.report.output[k] ? "pass" : "check"}
                        </Badge>
                      ))}
                    <span className="text-neutral-400">
                      {view.report.output.seconds}s · {view.report.output.loudness_lufs} LUFS · {view.report.output.music_under_speech_db == null
                        ? "no music"
                        : `music ${view.report.output.music_under_speech_db} dB under speech`} · voice {view.report.voice}
                    </span>
                  </div>
                )}

                {(waitingForReview || stopped) && !view.running && state !== "done" && (
                  <div className="rounded border border-amber-800 bg-amber-950/30 p-2 text-xs text-amber-200">
                    {view.state?.history?.at(-1)?.note}
                    <div className="mt-2">
                      <Button size="sm" disabled={busy}
                        onClick={() => send(`/api/forge/${view.id}`, { action: "make" }).then(() => loadView(view.id))}>
                        {waitingForReview ? "Approve and continue" : "Continue"}
                      </Button>
                      {state === "validate" && (
                        <Button size="sm" variant="outline" className="ml-2" disabled={busy}
                          onClick={() => send(`/api/forge/${view.id}`, { action: "make", accept: true }).then(() => loadView(view.id))}>
                          Accept the findings and continue
                        </Button>
                      )}
                    </div>
                  </div>
                )}

                {!!view.state?.open_questions?.length && (
                  <div className="text-xs text-neutral-400">
                    <div className="mb-1 text-neutral-300">Open questions</div>
                    <ul className="list-inside list-disc">
                      {view.state.open_questions.map((q) => <li key={q}>{q}</li>)}
                    </ul>
                  </div>
                )}

                {(has("out/contact_sheet.png") || has("qa/preview_sheet.png")) && (
                  <details open={state === "preview_review"}>
                    <summary className="cursor-pointer text-xs text-neutral-400">
                      Contact sheet: one frame per beat, labelled with the id revise takes
                    </summary>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img alt="contact sheet" className="mt-2 w-full rounded"
                      src={file(has("out/contact_sheet.png") ? "out/contact_sheet.png" : "qa/preview_sheet.png")
                        + `&v=${view.state?.history?.length}`} />
                  </details>
                )}

                {view.outline && (
                  <details open={state === "outline_review"}>
                    <summary className="cursor-pointer text-xs text-neutral-400">
                      Outline and script ({view.outline.chapters.length} chapters, {view.outline.target_minutes} min target)
                    </summary>
                    <div className="mt-2 flex max-h-96 flex-col gap-2 overflow-auto">
                      {view.outline.chapters.map((c) => (
                        <div key={c.id}>
                          <div className="text-xs font-medium text-neutral-200">{c.id} · {c.title}
                            <span className="ml-2 text-neutral-500">{c.slot}</span></div>
                          <ol className="ml-4 text-xs text-neutral-400">
                            {c.beats.map((b) => (
                              <li key={b.id}>
                                <button type="button" className="text-left hover:text-neutral-200"
                                  onClick={() => setNote(`${c.id}.${b.id}: say: ${b.say}`)}>
                                  <span className="text-neutral-500">{b.id}</span> {b.say}
                                  <span className="text-neutral-600"> [{b.do.map((o) => o.op).join(", ")}]</span>
                                </button>
                              </li>
                            ))}
                          </ol>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                <div className="flex flex-col gap-2 border-t border-neutral-800 pt-3">
                  <div className="text-xs text-neutral-400">
                    Revise: <code>c6.b07: say: a better line</code>, <code>c6.b07: drop</code>,{" "}
                    <code>c6: more on the cavalry</code> or <code>outline: …</code>. Only what the note touches is
                    spoken and rendered again.
                  </div>
                  <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="c3.b02: say: …" />
                  <div className="flex flex-wrap items-center gap-2">
                    <Button size="sm" disabled={busy || view.running || !note.trim()}
                      onClick={() => send(`/api/forge/${view.id}`, { action: "revise", note }).then((d) => {
                        if (d) setNote("");
                        loadView(view.id);
                      })}>
                      Revise
                    </Button>
                    <select className={input} value={restyleTo} aria-label="Restyle"
                      onChange={(e) => setRestyleTo(e.target.value)}>
                      <option value="">Restyle to…</option>
                      {Object.entries(registry.styles ?? {}).map(([id, s]) => (
                        <option key={id} value={id}>{s.label ?? id}</option>
                      ))}
                    </select>
                    <Button size="sm" variant="outline" disabled={busy || view.running || !restyleTo}
                      onClick={() => send(`/api/forge/${view.id}`, { action: "restyle", style: restyleTo }).then(() => loadView(view.id))}>
                      Restyle
                    </Button>
                  </div>
                </div>

                <details>
                  <summary className="cursor-pointer text-xs text-neutral-400">
                    Log{view.state?.tokens ? ` · ${view.state.tokens.in + view.state.tokens.out} tokens, $${view.state.cost_usd ?? 0}` : ""}
                  </summary>
                  <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-neutral-900 p-2 font-mono text-[11px] text-neutral-400">
                    {view.log}
                  </pre>
                  {!!view.state?.errors?.length && (
                    <pre className="mt-2 whitespace-pre-wrap rounded bg-neutral-900 p-2 text-[11px] text-rose-300">
                      {view.state.errors.at(-1)?.state}: {view.state.errors.at(-1)?.error}
                    </pre>
                  )}
                </details>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </main>
  );
}
