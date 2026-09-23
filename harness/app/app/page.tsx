"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { TEMPLATES } from "@/lib/templates";

type ExportState = {
  tier: 1 | 3 | null;
  blockers?: string[];
  program?: string | null;
  program_bytes?: number;
  assets?: string[];
  buildDir?: string;
  frames?: number;
  error?: string;
  stored?: { configured: boolean; reason?: string; error?: string };
};

type Version = {
  n: number;
  instruction: string | null;
  source: string;
  model: string;
  exported?: ExportState;
};

const SCENE = "GeneratedScene";

export default function Home() {
  const [content, setContent] = useState("");
  const [templateId, setTemplateId] = useState(TEMPLATES[0].id);
  const [versions, setVersions] = useState<Version[]>([]);
  const [current, setCurrent] = useState(-1);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frame, setFrame] = useState(0);

  const version = current >= 0 ? versions[current] : undefined;
  const exported = version?.exported;

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

  async function runGenerate(edit: boolean) {
    setError(null);
    setBusy(edit ? "Rewriting…" : "Generating…");
    try {
      const data = await post("/api/generate", {
        content,
        templateId,
        previousSource: edit ? version?.source : undefined,
        instruction: edit ? instruction : undefined,
      });
      const next: Version = {
        n: versions.length + 1,
        instruction: edit ? instruction : null,
        source: data.source,
        model: data.model,
      };
      setVersions((all) => [...all, next]);
      setCurrent(versions.length);
      setInstruction("");
      setFrame(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function runExport() {
    if (!version) return;
    setError(null);
    setBusy("Exporting — this runs Manim, so it takes a moment…");
    try {
      const data: ExportState = await post("/api/export", {
        source: version.source,
        sceneClass: SCENE,
        instruction: version.instruction,
        model: version.model,
      });
      setVersions((all) =>
        all.map((v, i) => (i === current ? { ...v, exported: data } : v)),
      );
      setFrame(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const frames = exported?.frames ?? 0;
  const frameSrc =
    exported?.tier === 1 && exported.buildDir && frames > 0
      ? `/api/frame?build=${encodeURIComponent(exported.buildDir)}&scene=${SCENE}&n=${frame}&w=640`
      : null;

  return (
    <main className="mx-auto min-h-screen max-w-6xl bg-neutral-950 px-6 py-8 text-neutral-200">
      <header className="mb-6">
        <h1 className="text-lg font-semibold text-neutral-100">pocketanim harness</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Content in, a program the phone plays out. No video is ever stored — the
          preview is rendered from the program on demand.
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-md border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>1 · Content</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Textarea
                rows={6}
                placeholder={"First line becomes the title.\nEach line after it becomes a beat."}
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
              <div className="flex flex-wrap gap-2">
                {TEMPLATES.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTemplateId(t.id)}
                    title={t.summary}
                    className={`rounded-md border px-3 py-1.5 text-xs transition-colors ${
                      templateId === t.id
                        ? "border-neutral-400 bg-neutral-800 text-neutral-100"
                        : "border-neutral-800 text-neutral-400 hover:border-neutral-700"
                    }`}
                  >
                    {t.name}
                  </button>
                ))}
              </div>
              <p className="text-xs text-neutral-500">
                {TEMPLATES.find((t) => t.id === templateId)?.summary}
              </p>
              <Button onClick={() => runGenerate(false)} disabled={!content.trim() || !!busy}>
                {busy ?? "Generate scene"}
              </Button>
            </CardContent>
          </Card>

          {version && (
            <Card>
              <CardHeader>
                <CardTitle>
                  2 · Scene source — v{version.n}
                  <span className="ml-2 font-normal text-neutral-500">{version.model}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <Textarea
                  rows={14}
                  className="font-mono text-xs"
                  value={version.source}
                  onChange={(e) =>
                    setVersions((all) =>
                      all.map((v, i) =>
                        i === current ? { ...v, source: e.target.value, exported: undefined } : v,
                      ),
                    )
                  }
                />
                <Button onClick={runExport} disabled={!!busy}>
                  Export to a program
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-4">
          {exported && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  3 · Build
                  {exported.tier === 1 && <Badge tone="good">tier 1 · plays as a program</Badge>}
                  {exported.tier === 3 && <Badge tone="warn">tier 3 · falls back to sampled IR</Badge>}
                  {exported.tier === null && <Badge tone="bad">did not export</Badge>}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                {exported.tier === 1 && (
                  <p className="text-neutral-400">
                    {exported.program_bytes} bytes · {exported.assets?.length ?? 0} asset
                    {(exported.assets?.length ?? 0) === 1 ? "" : "s"} · {frames} frames
                  </p>
                )}
                {!!exported.blockers?.length && (
                  <ul className="list-inside list-disc text-amber-300">
                    {exported.blockers.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                )}
                {exported.error && (
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-neutral-900 p-2 text-xs text-rose-300">
                    {exported.error}
                  </pre>
                )}
                {exported.program && (
                  <pre className="max-h-48 overflow-auto rounded bg-neutral-900 p-2 font-mono text-xs text-neutral-300">
                    {exported.program}
                  </pre>
                )}
                {exported.stored && !exported.stored.configured && (
                  <p className="text-xs text-neutral-500">
                    Not stored: {exported.stored.reason}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {frameSrc && (
            <Card>
              <CardHeader>
                <CardTitle>4 · Preview</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
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
                  frame {frame} of {frames - 1} — rendered on demand, never stored
                </p>
              </CardContent>
            </Card>
          )}

          {version && (
            <Card>
              <CardHeader>
                <CardTitle>5 · Change it</CardTitle>
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
                  Apply as a new version
                </Button>
                {versions.length > 1 && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {versions.map((v, i) => (
                      <button
                        key={v.n}
                        onClick={() => {
                          setCurrent(i);
                          setFrame(0);
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
      </div>
    </main>
  );
}
