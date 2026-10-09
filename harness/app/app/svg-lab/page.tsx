"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { VersionBar } from "@/components/version-bar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { duration, usd } from "@/lib/costs";

/**
 * The SVG lab: the same educational diagrams drawn by several models, each exactly as a lecture draws its pictures
 * (the prompt, the board's checks and repairs, the look-and-fix round), with what each drawing cost, how long it took
 * and how many requests it needed, a score you give it, and each model's totals. For choosing the drawing model.
 */

type Diagram = { id: string; what: string; parts: string; moves?: string };

const PRESETS: Diagram[] = [
  { id: "cell", what: "A plant cell in cross-section, with its organelles in their true places and proportions",
    parts: "cell_wall, membrane, nucleus, chloroplast, vacuole, mitochondrion, cytoplasm" },
  { id: "heart", what: "The human heart in a front cross-section: four chambers, valves, the great vessels, oxygen-rich blood red and oxygen-poor blood blue, arrows for the flow",
    parts: "right_atrium, right_ventricle, left_atrium, left_ventricle, aorta, pulmonary_artery, vena_cava, valves" },
  { id: "circuit", what: "A simple circuit: a cell, a switch and a bulb in series, with the current's direction shown",
    parts: "cell, switch, bulb, wires, current" },
  { id: "refraction", what: "A light ray passing through a rectangular glass block: incident, refracted and emergent rays, normals, angles i and r marked",
    parts: "block, incident, refracted, emergent, normal_1, normal_2, angle_i, angle_r" },
  { id: "water-cycle", what: "The water cycle over land and sea: evaporation, condensation into clouds, precipitation, runoff and groundwater back to the sea",
    parts: "sea, sun, evaporation, cloud, precipitation, mountain, runoff, groundwater" },
  { id: "volcano", what: "A volcano in cross-section: magma chamber, main vent, crater, layers of ash and lava, an eruption cloud",
    parts: "magma_chamber, vent, crater, layers, lava, ash_cloud" },
  { id: "leaf", what: "A leaf in cross-section: cuticle, upper epidermis, palisade layer, spongy layer, a stoma with guard cells, a vein",
    parts: "cuticle, upper_epidermis, palisade, spongy, stoma, guard_cells, vein, lower_epidermis" },
  { id: "eye", what: "The human eye in side section: cornea, iris, pupil, lens, retina, optic nerve, and rays focusing on the retina",
    parts: "cornea, iris, pupil, lens, retina, optic_nerve, rays" },
];

const DEFAULT_MODELS = [
  "anthropic/claude-sonnet-4.5",
  "openai/gpt-5",
  "google/gemini-2.5-pro",
  "google/gemini-2.5-flash",
  "x-ai/grok-4",
  "deepseek/deepseek-chat-v3.1",
].join("\n");

const STYLES = ["chalkboard", "atlas", "vox", "whiteboard", "blueprint", "parchment", "lab", "cosmos", "cardboard"];

type Cell = {
  status: "queued" | "drawing" | "done" | "failed";
  started?: number;
  ok?: boolean;
  file?: string;
  usd?: number;
  seconds?: number;
  requests?: number;
  bytes?: number;
  warnings?: string[];
  error?: string;
};

type ModelInfo = { id: string; name: string; input: number; output: number; images: boolean };

const key = (model: string, diagram: string) => `${model}||${diagram}`;
const SCORES = "svg-lab-scores";

function loadScores(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(SCORES) ?? "{}") as Record<string, number>;
  } catch {
    return {};
  }
}

export default function SvgLab() {
  const [modelsText, setModelsText] = useState(DEFAULT_MODELS);
  const [chosen, setChosen] = useState<Set<string>>(new Set(["cell", "heart", "circuit"]));
  const [custom, setCustom] = useState<Diagram>({ id: "custom", what: "", parts: "" });
  const [style, setStyle] = useState("chalkboard");
  const [atOnce, setAtOnce] = useState(4);
  const [cells, setCells] = useState<Record<string, Cell>>({});
  const [running, setRunning] = useState(false);
  const [catalogue, setCatalogue] = useState<ModelInfo[]>([]);
  const [keySet, setKeySet] = useState<boolean | null>(null);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [now, setNow] = useState(() => Date.now());
  const abort = useRef<AbortController | null>(null);
  const run = useRef(`lab-${Date.now()}`);

  useEffect(() => {
    setScores(loadScores());
    fetch("/api/svg-lab").then((r) => r.json())
      .then((d: { models?: ModelInfo[]; key?: boolean }) => {
        setCatalogue(d.models ?? []);
        setKeySet(!!d.key);
      })
      .catch(() => setKeySet(null));
  }, []);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);

  const models = useMemo(() => [...new Set(modelsText.split(/[\n,]+/).map((m) => m.trim()).filter(Boolean))], [modelsText]);
  const diagrams = useMemo(() => [
    ...PRESETS.filter((p) => chosen.has(p.id)),
    ...(custom.what.trim() && custom.parts.trim() ? [custom] : []),
  ], [chosen, custom]);
  const price = (id: string) => catalogue.find((m) => m.id === id);
  const badModels = models.filter((m) => !/^[\w.\-]+\/[\w.:\-]+$/.test(m));

  const score = (model: string, diagram: string, value: number) => {
    const next = { ...scores, [key(model, diagram)]: value };
    setScores(next);
    try {
      localStorage.setItem(SCORES, JSON.stringify(next));
    } catch {
      // scores stay for this visit only
    }
  };

  async function start() {
    if (!models.length || !diagrams.length || badModels.length) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    run.current = `lab-${Date.now()}`;
    const jobs = diagrams.flatMap((d) => models.map((m) => ({ model: m, diagram: d })));
    setCells(Object.fromEntries(jobs.map((j) => [key(j.model, j.diagram.id), { status: "queued" as const }])));
    setRunning(true);
    const queue = [...jobs];
    const worker = async () => {
      for (let job = queue.shift(); job && !controller.signal.aborted; job = queue.shift()) {
        const id = key(job.model, job.diagram.id);
        setCells((c) => ({ ...c, [id]: { status: "drawing", started: Date.now() } }));
        try {
          const response = await fetch("/api/svg-lab", {
            method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: job.model, what: job.diagram.what, parts: job.diagram.parts,
              moves: job.diagram.moves, run: run.current }),
          });
          const result = await response.json();
          if (!response.ok) throw new Error(result.error ?? `HTTP ${response.status}`);
          setCells((c) => ({ ...c, [id]: { ...result, status: result.ok ? "done" : "failed" } }));
        } catch (error) {
          setCells((c) => ({ ...c, [id]: { status: "failed", error: error instanceof Error ? error.message : String(error) } }));
        }
      }
    };
    await Promise.all(Array.from({ length: Math.max(1, Math.min(atOnce, jobs.length)) }, worker));
    setRunning(false);
  }

  function stop() {
    abort.current?.abort();
    setRunning(false);
  }

  // Each model's totals over the diagrams it drew in this run.
  const totals = models.map((model) => {
    const mine = diagrams.map((d) => ({ d, cell: cells[key(model, d.id)] })).filter((x) => x.cell);
    const finished = mine.filter((x) => x.cell.status === "done" || x.cell.status === "failed");
    const passed = finished.filter((x) => x.cell.ok);
    const spent = finished.reduce((t, x) => t + (x.cell.usd ?? 0), 0);
    const time = finished.reduce((t, x) => t + (x.cell.seconds ?? 0), 0);
    const requests = finished.reduce((t, x) => t + (x.cell.requests ?? 0), 0);
    const scored = mine.map((x) => scores[key(model, x.d.id)]).filter((v): v is number => typeof v === "number");
    return {
      model, drawn: finished.length, passed: passed.length, spent, time, requests,
      perSvg: passed.length ? spent / passed.length : null,
      avgTime: finished.length ? time / finished.length : null,
      score: scored.length ? scored.reduce((a, b) => a + b, 0) / scored.length : null,
    };
  });
  const grand = totals.reduce((t, m) => t + m.spent, 0);

  function download(kind: "csv" | "json") {
    const rows = diagrams.flatMap((d) => models.map((m) => ({ model: m, diagram: d.id, ...cells[key(m, d.id)],
      score: scores[key(m, d.id)] ?? null })));
    const text = kind === "json" ? JSON.stringify({ run: run.current, totals, rows }, null, 2)
      : ["model,diagram,status,usd,seconds,requests,bytes,score,error",
        ...rows.map((r) => [r.model, r.diagram, r.status ?? "", r.usd ?? "", r.seconds?.toFixed(1) ?? "", r.requests ?? "",
          r.bytes ?? "", r.score ?? "", JSON.stringify(r.error ?? "")].join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: kind === "json" ? "application/json" : "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${run.current}.${kind}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }

  const picture = (file: string) => `/api/picture?file=${encodeURIComponent(file)}&style=${style}`;

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-6 py-8 text-neutral-200">
      <VersionBar />
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-neutral-100">SVG lab</h1>
          <p className="mt-1 max-w-2xl text-sm text-neutral-400">
            The same educational diagrams drawn by several models, each exactly as a lecture draws its pictures:
            drawn, checked against the board&apos;s rules and repaired, then looked at and fixed. Compare what each
            drawing cost, how long it took, and how good it is.
          </p>
        </div>
        <Link href="/" className="text-sm text-sky-300 underline-offset-2 hover:underline">← Lectures</Link>
      </header>
      {keySet === false && (
        <div className="mb-4 rounded border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-200">
          OPENROUTER_API_KEY is not set on the server: nothing can be drawn.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr]">
        <Card>
          <CardHeader><CardTitle>Models</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-2 text-xs">
            <p className="text-neutral-400">OpenRouter model ids, one per line.</p>
            <Textarea rows={7} value={modelsText} onChange={(e) => setModelsText(e.target.value)}
              className="font-mono text-xs" data-testid="lab-models" />
            {badModels.length > 0 && <p className="text-rose-300">Not a model id: {badModels.join(", ")}</p>}
            <div className="flex flex-wrap gap-2">
              <input list="lab-catalogue" placeholder="Add a model…" className="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
                onKeyDown={(e) => {
                  const value = (e.target as HTMLInputElement).value.trim();
                  if (e.key === "Enter" && value) {
                    setModelsText((t) => `${t.trim()}\n${value}`);
                    (e.target as HTMLInputElement).value = "";
                  }
                }} />
              <datalist id="lab-catalogue">
                {catalogue.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </datalist>
            </div>
            <ul className="flex flex-col gap-0.5 text-neutral-500">
              {models.map((m) => {
                const p = price(m);
                return (
                  <li key={m} className="flex justify-between gap-2">
                    <span className="truncate font-mono text-neutral-300">{m}</span>
                    <span className="shrink-0">
                      {p ? `$${p.input.toFixed(2)} in · $${p.output.toFixed(2)} out per M tokens${p.images ? "" : " · no image input (skips the look-and-fix round)"}`
                        : catalogue.length ? "not in OpenRouter's list" : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Diagrams</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-2 text-xs">
            <div className="grid gap-1 sm:grid-cols-2">
              {PRESETS.map((p) => (
                <label key={p.id} className="flex cursor-pointer items-start gap-2 rounded border border-neutral-800 p-2 hover:border-neutral-600">
                  <input type="checkbox" checked={chosen.has(p.id)} onChange={() => setChosen((s) => {
                    const next = new Set(s);
                    if (next.has(p.id)) next.delete(p.id);
                    else next.add(p.id);
                    return next;
                  })} />
                  <span><span className="text-neutral-200">{p.id}</span>
                    <span className="block text-neutral-500">{p.what}</span></span>
                </label>
              ))}
            </div>
            <p className="mt-2 text-neutral-400">Your own diagram (what to draw, and its parts, comma-separated):</p>
            <Textarea rows={2} placeholder="A bicycle's gear system: chainring, chain, rear sprocket…" value={custom.what}
              onChange={(e) => setCustom({ ...custom, what: e.target.value })} />
            <input placeholder="chainring, chain, sprocket, pedal" value={custom.parts}
              onChange={(e) => setCustom({ ...custom, parts: e.target.value })}
              className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" />
            <input placeholder="What moves (optional): the chain turns the sprocket" value={custom.moves ?? ""}
              onChange={(e) => setCustom({ ...custom, moves: e.target.value })}
              className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1" />
          </CardContent>
        </Card>
      </div>

      <div className="my-4 flex flex-wrap items-center gap-3 text-sm">
        <Button onClick={start} disabled={running || !models.length || !diagrams.length || badModels.length > 0}
          data-testid="lab-run">
          {running ? "Drawing…" : `Draw ${diagrams.length * models.length} SVG${diagrams.length * models.length === 1 ? "" : "s"}`}
        </Button>
        {running && <Button variant="outline" onClick={stop}>Stop</Button>}
        <label className="flex items-center gap-2 text-xs text-neutral-400">
          At once
          <select value={atOnce} onChange={(e) => setAtOnce(Number(e.target.value))}
            className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5">
            {[1, 2, 4, 6, 8, 12].map((n) => <option key={n}>{n}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-neutral-400">
          Shown on
          <select value={style} onChange={(e) => setStyle(e.target.value)}
            className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5">
            {STYLES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        {grand > 0 && <span className="text-xs text-neutral-400">Spent this run: <span className="font-mono text-neutral-100">{usd(grand)}</span></span>}
        {Object.keys(cells).length > 0 && (
          <span className="flex gap-2 text-xs">
            <button className="text-sky-300 hover:underline" onClick={() => download("csv")}>Download CSV</button>
            <button className="text-sky-300 hover:underline" onClick={() => download("json")}>JSON</button>
          </span>
        )}
      </div>

      {Object.keys(cells).length > 0 && (
        <Card className="mb-4">
          <CardHeader><CardTitle>By model</CardTitle></CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full border-collapse text-xs tabular-nums" data-testid="lab-totals">
              <thead>
                <tr className="text-left text-neutral-500">
                  <th className="py-1 pr-3 font-normal">Model</th>
                  <th className="py-1 pr-3 text-right font-normal">Passed</th>
                  <th className="py-1 pr-3 text-right font-normal">Total cost</th>
                  <th className="py-1 pr-3 text-right font-normal">Per SVG</th>
                  <th className="py-1 pr-3 text-right font-normal">Avg time</th>
                  <th className="py-1 pr-3 text-right font-normal">Requests</th>
                  <th className="py-1 text-right font-normal">Your score</th>
                </tr>
              </thead>
              <tbody>
                {[...totals].sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || (a.perSvg ?? 1e9) - (b.perSvg ?? 1e9)).map((t) => (
                  <tr key={t.model} className="border-t border-neutral-900">
                    <td className="py-1 pr-3 font-mono text-neutral-200">{t.model}</td>
                    <td className="py-1 pr-3 text-right">{t.passed} / {t.drawn}</td>
                    <td className="py-1 pr-3 text-right font-mono">{usd(t.spent)}</td>
                    <td className="py-1 pr-3 text-right font-mono">{t.perSvg === null ? "—" : usd(t.perSvg)}</td>
                    <td className="py-1 pr-3 text-right">{t.avgTime === null ? "—" : duration(t.avgTime)}</td>
                    <td className="py-1 pr-3 text-right">{t.requests}</td>
                    <td className="py-1 text-right">{t.score === null ? "—" : `${t.score.toFixed(1)} / 5`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-neutral-500">
              Per SVG is the total cost over the drawings that passed the board&apos;s checks. Score the drawings below
              (kept in this browser) to rank the models by quality.
            </p>
          </CardContent>
        </Card>
      )}

      {Object.keys(cells).length > 0 && (
        <div className="overflow-x-auto">
          <table className="border-separate border-spacing-2 text-xs" data-testid="lab-grid">
            <thead>
              <tr>
                <th />
                {models.map((m) => <th key={m} className="min-w-[260px] text-left font-mono font-normal text-neutral-300">{m}</th>)}
              </tr>
            </thead>
            <tbody>
              {diagrams.map((d) => (
                <tr key={d.id} className="align-top">
                  <th className="w-28 pt-2 text-left font-normal text-neutral-300">{d.id}</th>
                  {models.map((m) => {
                    const cell = cells[key(m, d.id)];
                    const given = scores[key(m, d.id)];
                    return (
                      <td key={m} className="w-[260px] rounded border border-neutral-800 bg-neutral-950 p-2">
                        {!cell || cell.status === "queued" ? <p className="text-neutral-500">Waiting</p>
                          : cell.status === "drawing" ? (
                            <p className="text-amber-300">Drawing… {duration((now - (cell.started ?? now)) / 1000)}</p>
                          ) : (
                            <div className="flex flex-col gap-1">
                              {cell.file ? (
                                <a href={picture(cell.file)} target="_blank" rel="noreferrer">
                                  {/* An <img> keeps the drawing's own animation running and its scripts off. */}
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img src={picture(cell.file)} alt={`${d.id} by ${m}`} className="aspect-video w-full rounded bg-neutral-900 object-contain" />
                                </a>
                              ) : (
                                <p className="line-clamp-4 text-rose-300" title={cell.error}>Failed: {cell.error}</p>
                              )}
                              <p className="flex flex-wrap gap-x-2 text-neutral-400">
                                <span className="font-mono text-neutral-100">{usd(cell.usd ?? 0)}</span>
                                <span>{duration(cell.seconds ?? 0)}</span>
                                <span>{cell.requests ?? 0} request{cell.requests === 1 ? "" : "s"}</span>
                                {cell.bytes ? <span>{Math.round(cell.bytes / 1000)} KB</span> : null}
                              </p>
                              {cell.warnings?.length ? (
                                <p className="text-amber-300/80" title={cell.warnings.join("\n")}>{cell.warnings.length} warning{cell.warnings.length > 1 ? "s" : ""}</p>
                              ) : null}
                              {cell.ok && (
                                <div className="flex items-center gap-1 text-neutral-500">
                                  Score
                                  {[1, 2, 3, 4, 5].map((n) => (
                                    <button key={n} onClick={() => score(m, d.id, n)}
                                      className={`h-5 w-5 rounded ${given !== undefined && n <= given ? "bg-amber-400 text-neutral-900" : "bg-neutral-800 text-neutral-400"}`}>
                                      {n}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
