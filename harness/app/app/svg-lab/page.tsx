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
  status: "queued" | "drawing" | "done" | "failed" | "stopped" | "interrupted";
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
/** The page's inputs and its latest run, kept in this browser: a reload comes back to them. */
const KEPT = "svg-lab-page";

type Run = { id: string; running: boolean; models: string[]; diagrams: Diagram[]; cells: Record<string, Cell> };

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
  const [runId, setRunId] = useState<string | null>(null);
  const [runShape, setRunShape] = useState<{ models: string[]; diagrams: Diagram[] } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const run = useRef("lab");

  // The page as it was left: its inputs and its run (which goes on in the server while the page is away).
  useEffect(() => {
    try {
      const kept = JSON.parse(localStorage.getItem(KEPT) ?? "null") as {
        modelsText?: string; chosen?: string[]; custom?: Diagram; style?: string; atOnce?: number; runId?: string | null;
      } | null;
      if (kept) {
        if (typeof kept.modelsText === "string") setModelsText(kept.modelsText);
        if (Array.isArray(kept.chosen)) setChosen(new Set(kept.chosen));
        if (kept.custom) setCustom(kept.custom);
        if (kept.style) setStyle(kept.style);
        if (kept.atOnce) setAtOnce(kept.atOnce);
        if (kept.runId) setRunId(kept.runId);
      }
    } catch {
      // nothing kept
    }
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (!loaded) return;
    try {
      localStorage.setItem(KEPT, JSON.stringify({ modelsText, chosen: [...chosen], custom, style, atOnce, runId }));
    } catch {
      // not kept
    }
  }, [loaded, modelsText, chosen, custom, style, atOnce, runId]);

  // Follow the run: poll the server while it draws, once when it is over.
  useEffect(() => {
    if (!runId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const response = await fetch(`/api/svg-lab/run?id=${encodeURIComponent(runId)}`);
        const data = await response.json() as { run?: Run; error?: string };
        if (!alive) return;
        if (!data.run) {
          setProblem(data.error ?? "the run could not be found");
          setRunning(false);
          return;
        }
        run.current = data.run.id;
        setCells(data.run.cells);
        setRunShape({ models: data.run.models, diagrams: data.run.diagrams.map((d) => ({ ...d,
          parts: Array.isArray(d.parts) ? (d.parts as unknown as string[]).join(", ") : String(d.parts) })) });
        setRunning(data.run.running);
        if (data.run.running) timer = setTimeout(poll, 2000);
      } catch {
        if (alive) timer = setTimeout(poll, 4000);
      }
    };
    void poll();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

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
    setProblem(null);
    const response = await fetch("/api/svg-lab/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ models, diagrams, atOnce }),
    });
    const data = await response.json() as { run?: Run; error?: string };
    if (!response.ok || !data.run) {
      setProblem(data.error ?? `HTTP ${response.status}`);
      return;
    }
    // The server draws them; the page follows the run (and follows it again after a reload).
    setCells(data.run.cells);
    setRunning(true);
    setRunId(data.run.id);
  }

  async function stop() {
    if (runId) await fetch(`/api/svg-lab/run?id=${encodeURIComponent(runId)}`, { method: "DELETE" }).catch(() => undefined);
  }

  // A run shows the models and diagrams it was started with, whatever the inputs say now.
  const shownModels = runShape?.models ?? models;
  const shownDiagrams = runShape?.diagrams ?? diagrams;
  // Each model's totals over the diagrams it drew in this run.
  const totals = shownModels.map((model) => {
    const mine = shownDiagrams.map((d) => ({ d, cell: cells[key(model, d.id)] })).filter((x) => x.cell);
    const finished = mine.filter((x) => x.cell.status === "done" || x.cell.status === "failed" || x.cell.status === "stopped");
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
    const rows = shownDiagrams.flatMap((d) => shownModels.map((m) => ({ model: m, diagram: d.id, ...cells[key(m, d.id)],
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
      {problem && (
        <div className="mb-4 rounded border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-200">{problem}</div>
      )}
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
        <Review
          models={shownModels} diagrams={shownDiagrams} cells={cells} scores={scores} score={score}
          picture={picture} now={now} runId={run.current}
        />
      )}
    </main>
  );
}

/** The small grid of every drawing: the overview. */
function OverviewGrid(props: { models: string[]; diagrams: Diagram[]; cells: Record<string, Cell>; scores: Record<string, number>;
  score: (m: string, d: string, n: number) => void; picture: (file: string) => string; now: number; label: (m: string) => string;
  open: (m: string, d: string) => void }) {
  const { models: shownModels, diagrams: shownDiagrams, cells, scores, score, picture, now, label, open } = props;
  return (
        <div className="overflow-x-auto">
          <table className="border-separate border-spacing-2 text-xs" data-testid="lab-grid">
            <thead>
              <tr>
                <th />
                {shownModels.map((m) => <th key={m} className="min-w-[260px] text-left font-mono font-normal text-neutral-300">{label(m)}</th>)}
              </tr>
            </thead>
            <tbody>
              {shownDiagrams.map((d) => (
                <tr key={d.id} className="align-top">
                  <th className="w-28 pt-2 text-left font-normal text-neutral-300">{d.id}</th>
                  {shownModels.map((m) => {
                    const cell = cells[key(m, d.id)];
                    const given = scores[key(m, d.id)];
                    return (
                      <td key={m} className="w-[260px] rounded border border-neutral-800 bg-neutral-950 p-2">
                        {!cell || cell.status === "queued" ? <p className="text-neutral-500">Waiting</p>
                          : cell.status === "interrupted" ? <p className="text-amber-300">Interrupted (the server restarted)</p>
                          : cell.status === "stopped" && !cell.file ? <p className="text-neutral-500">Stopped</p>
                          : cell.status === "drawing" ? (
                            <p className="text-amber-300">Drawing… {duration((now - (cell.started ?? now)) / 1000)}</p>
                          ) : (
                            <div className="flex flex-col gap-1">
                              {cell.file ? (
                                <button type="button" onClick={() => open(m, d.id)} className="block w-full" title="Review it large">
                                  {/* An <img> keeps the drawing's own animation running and its scripts off. */}
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img src={picture(cell.file)} alt={`${d.id} by ${label(m)}`} className="aspect-video w-full rounded bg-neutral-900 object-contain" />
                                </button>
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
  );
}

/** A deterministic shuffle (a run's own order), so blind labels do not follow the order the models were typed in. */
function shuffled<T>(items: T[], seed: string): T[] {
  let h = 2166136261;
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    const j = Math.abs(h) % (i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

type ReviewProps = {
  models: string[];
  diagrams: Diagram[];
  cells: Record<string, Cell>;
  scores: Record<string, number>;
  score: (model: string, diagram: string, value: number) => void;
  picture: (file: string) => string;
  now: number;
  runId: string;
};

/**
 * Reviewing a run: one diagram at a time with every model's drawing large beside the others (Compare), any one of
 * them full screen (keys 1-5 score it and go on to the next), or every drawing small (Overview). Blind hides which
 * model drew what until you reveal it.
 */
function Review({ models, diagrams, cells, scores, score, picture, now, runId }: ReviewProps) {
  const [view, setView] = useState<"compare" | "overview">("compare");
  const [columns, setColumns] = useState(2);
  const [blind, setBlind] = useState(false);
  const [at, setAt] = useState(0);                       // the diagram on show
  const [focus, setFocus] = useState(0);                 // the drawing the keys act on
  const [full, setFull] = useState<{ model: string; diagram: string } | null>(null);
  const loaded = useRef(false);

  useEffect(() => {
    try {
      const kept = JSON.parse(localStorage.getItem("svg-lab-review") ?? "null") as { columns?: number; blind?: boolean; view?: "compare" | "overview" } | null;
      if (kept?.columns) setColumns(kept.columns);
      if (typeof kept?.blind === "boolean") setBlind(kept.blind);
      if (kept?.view) setView(kept.view);
    } catch {
      // defaults
    }
  }, []);
  useEffect(() => {
    // Not on the first render: that still has the defaults, and would write them over what was kept.
    if (!loaded.current) {
      loaded.current = true;
      return;
    }
    try {
      localStorage.setItem("svg-lab-review", JSON.stringify({ columns, blind, view }));
    } catch {
      // not kept
    }
  }, [columns, blind, view]);

  const order = useMemo(() => (blind ? shuffled(models, runId) : models), [blind, models, runId]);
  const label = (model: string) => (blind ? `Model ${String.fromCharCode(65 + shuffled(models, runId).indexOf(model))}` : model);
  const diagram = diagrams[Math.min(at, diagrams.length - 1)];
  const scoredIn = (d: Diagram) => models.filter((m) => scores[key(m, d.id)] !== undefined).length;
  const drawnIn = (d: Diagram) => models.filter((m) => cells[key(m, d.id)]?.ok).length;

  /** The next drawing that passed and has no score yet, after the one in focus. */
  const nextUnscored = () => {
    const flat = diagrams.flatMap((d, di) => order.map((m, mi) => ({ d, di, m, mi })));
    const here = flat.findIndex((x) => x.di === at && x.mi === focus);
    for (let k = 1; k <= flat.length; k++) {
      const x = flat[(here + k) % flat.length];
      if (cells[key(x.m, x.d.id)]?.ok && scores[key(x.m, x.d.id)] === undefined) return x;
    }
    return null;
  };
  const goNextUnscored = () => {
    const x = nextUnscored();
    if (!x) return;
    setAt(x.di);
    setFocus(x.mi);
    if (full) setFull({ model: x.m, diagram: x.d.id });
  };

  // Keys: arrows move, 1-5 score, Enter opens full screen, Escape closes it, N goes to the next unscored.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) return;
      if (view !== "compare" && !full) return;
      const fullAt = full ? order.indexOf(full.model) : focus;
      const di = full ? diagrams.findIndex((d) => d.id === full.diagram) : at;
      const move = (mi: number, dIndex: number) => {
        const m = (mi + order.length) % order.length;
        const d = (dIndex + diagrams.length) % diagrams.length;
        setFocus(m);
        setAt(d);
        if (full) setFull({ model: order[m], diagram: diagrams[d].id });
      };
      if (e.key === "ArrowRight") move(fullAt + 1, di);
      else if (e.key === "ArrowLeft") move(fullAt - 1, di);
      else if (e.key === "ArrowDown") move(fullAt, di + 1);
      else if (e.key === "ArrowUp") move(fullAt, di - 1);
      else if (e.key === "Escape") setFull(null);
      else if (e.key === "Enter" && !full) setFull({ model: order[focus], diagram: diagrams[at].id });
      else if (e.key.toLowerCase() === "n") goNextUnscored();
      else if (/^[1-5]$/.test(e.key)) {
        const m = order[fullAt];
        const d = diagrams[di];
        if (!m || !d || !cells[key(m, d.id)]?.ok) return;
        score(m, d.id, Number(e.key));
        // Scored full screen: on to the next model's drawing of the same diagram.
        if (full && fullAt + 1 < order.length) move(fullAt + 1, di);
      } else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!diagram) return null;
  const stars = (m: string, d: string, big = false) => {
    const given = scores[key(m, d)];
    return (
      <div className="flex items-center gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" onClick={() => score(m, d, n)} aria-label={`Score ${n}`}
            className={`${big ? "h-9 w-9 text-base" : "h-7 w-7 text-sm"} rounded font-medium ${given !== undefined && n <= given
              ? "bg-amber-400 text-neutral-900" : "bg-neutral-800 text-neutral-400 hover:bg-neutral-700"}`}>
            {n}
          </button>
        ))}
      </div>
    );
  };
  const stats = (cell: Cell) => (
    <span className="flex flex-wrap gap-x-3 text-xs text-neutral-400">
      <span className="font-mono text-neutral-100">{usd(cell.usd ?? 0)}</span>
      <span>{duration(cell.seconds ?? 0)}</span>
      <span>{cell.requests ?? 0} request{cell.requests === 1 ? "" : "s"}</span>
      {cell.bytes ? <span>{Math.round(cell.bytes / 1000)} KB</span> : null}
      {cell.warnings?.length ? <span className="text-amber-300/80" title={cell.warnings.join("\n")}>{cell.warnings.length} warning{cell.warnings.length > 1 ? "s" : ""}</span> : null}
    </span>
  );
  const status = (cell?: Cell) => (
    <div className="flex aspect-video w-full items-center justify-center rounded bg-neutral-900 p-4 text-center text-sm">
      {!cell || cell.status === "queued" ? <span className="text-neutral-500">Waiting</span>
        : cell.status === "drawing" ? <span className="text-amber-300">Drawing… {duration((now - (cell.started ?? now)) / 1000)}</span>
        : cell.status === "interrupted" ? <span className="text-amber-300">Interrupted (the server restarted)</span>
        : cell.status === "stopped" ? <span className="text-neutral-500">Stopped</span>
        : <span className="line-clamp-6 text-rose-300">Failed: {cell.error}</span>}
    </div>
  );
  const fullCell = full ? cells[key(full.model, full.diagram)] : undefined;
  const fullDiagram = full ? diagrams.find((d) => d.id === full.diagram) : undefined;
  const unscoredLeft = diagrams.reduce((t, d) => t + models.filter((m) => cells[key(m, d.id)]?.ok && scores[key(m, d.id)] === undefined).length, 0);

  return (
    <section className="mb-8" data-testid="lab-review">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        <h2 className="mr-2 text-base font-semibold text-neutral-100">Review</h2>
        <div className="flex overflow-hidden rounded border border-neutral-700 text-xs">
          {(["compare", "overview"] as const).map((v) => (
            <button key={v} type="button" onClick={() => setView(v)}
              className={`px-3 py-1 capitalize ${view === v ? "bg-neutral-200 text-neutral-900" : "text-neutral-300 hover:bg-neutral-800"}`}>
              {v}
            </button>
          ))}
        </div>
        {view === "compare" && (
          <label className="flex items-center gap-2 text-xs text-neutral-400">
            Per row
            <select value={columns} onChange={(e) => setColumns(Number(e.target.value))}
              className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5">
              {[1, 2, 3].map((n) => <option key={n}>{n}</option>)}
            </select>
          </label>
        )}
        <label className="flex cursor-pointer items-center gap-2 text-xs text-neutral-400" title="Hide which model drew what while you score">
          <input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} data-testid="lab-blind" />
          Blind
        </label>
        <button type="button" onClick={goNextUnscored} disabled={!unscoredLeft}
          className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40">
          Next unscored ({unscoredLeft})
        </button>
        <span className="text-xs text-neutral-500">Keys: ← → drawing · ↑ ↓ diagram · 1–5 score · Enter full screen · N next unscored</span>
      </div>

      {view === "overview" ? (
        <OverviewGrid models={order} diagrams={diagrams} cells={cells} scores={scores} score={score} picture={picture} now={now}
          label={label} open={(m, d) => setFull({ model: m, diagram: d })} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2" data-testid="lab-diagram-tabs">
            {diagrams.map((d, i) => (
              <button key={d.id} type="button" onClick={() => { setAt(i); setFocus(0); }}
                className={`rounded border px-3 py-1 text-xs ${i === at ? "border-amber-400 bg-amber-400/10 text-amber-200"
                  : "border-neutral-800 text-neutral-300 hover:border-neutral-600"}`}>
                {d.id} <span className="text-neutral-500">{scoredIn(d)}/{drawnIn(d)} scored</span>
              </button>
            ))}
          </div>
          <div className="mb-3 rounded border border-neutral-800 bg-neutral-950 p-3 text-sm">
            <p className="text-neutral-200">{diagram.what}</p>
            <p className="mt-1 text-xs text-neutral-500">Parts: {diagram.parts}{diagram.moves ? ` · moves: ${diagram.moves}` : ""}</p>
          </div>
          <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }} data-testid="lab-compare">
            {order.map((m, mi) => {
              const cell = cells[key(m, diagram.id)];
              return (
                <div key={m} onClick={() => setFocus(mi)}
                  className={`flex flex-col gap-2 rounded-lg border bg-neutral-950 p-3 ${mi === focus ? "border-amber-400/70" : "border-neutral-800"}`}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate font-mono text-sm text-neutral-100">{label(m)}</span>
                    {cell?.file && (
                      <button type="button" onClick={() => setFull({ model: m, diagram: diagram.id })}
                        className="shrink-0 text-xs text-sky-300 hover:underline">Full screen</button>
                    )}
                  </div>
                  {cell?.file ? (
                    <button type="button" onClick={() => setFull({ model: m, diagram: diagram.id })} className="block w-full" title="Full screen">
                      {/* An <img> keeps the drawing's own animation running and its scripts off. */}
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={picture(cell.file)} alt={`${diagram.id} by ${label(m)}`}
                        className="aspect-video w-full rounded bg-neutral-900 object-contain" />
                    </button>
                  ) : status(cell)}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    {cell && (cell.status === "done" || cell.status === "failed") ? stats(cell) : <span />}
                    {cell?.ok && stars(m, diagram.id)}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {full && fullDiagram && (
        <div className="fixed inset-0 z-50 flex flex-col bg-neutral-950 p-4" role="dialog" aria-modal="true" data-testid="lab-full"
          onClick={(e) => { if (e.target === e.currentTarget) setFull(null); }}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-sm">
            <div className="min-w-0">
              <p className="font-mono text-neutral-100">{label(full.model)} · <span className="text-neutral-400">{fullDiagram.id}</span></p>
              <p className="truncate text-xs text-neutral-500">{fullDiagram.what}</p>
            </div>
            <div className="flex items-center gap-3">
              {fullCell && stats(fullCell)}
              <button type="button" onClick={() => setFull(null)} className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-200">
                Close (Esc)
              </button>
            </div>
          </div>
          <div className="flex min-h-0 flex-1 items-center justify-center">
            {fullCell?.file ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={picture(fullCell.file)} alt={`${fullDiagram.id} by ${label(full.model)}`}
                className="h-full w-full rounded object-contain" />
            ) : <div className="w-full max-w-3xl">{status(fullCell)}</div>}
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-400">
            <span>← → other models · ↑ ↓ other diagrams · 1–5 score and go to the next model · N next unscored</span>
            {fullCell?.ok && stars(full.model, full.diagram, true)}
          </div>
        </div>
      )}
    </section>
  );
}
