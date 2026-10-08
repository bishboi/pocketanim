"use client";

import { COST_LABELS, COST_TASKS, itemsText, usd, type Costs } from "@/lib/costs";

/** What a version holds about its cost: writing it (task by task), its voice and its builds. */
export type CostedVersion = {
  costUsd?: number;
  costs?: Costs;
  voiceUsd?: number;
  voiceLecture?: { usd: number; lines: number; unknown: number; engine?: string };
  build?: { seconds: number; voiceSeconds: number; count: number; aiImages: number; aiUsd: number };
  part?: { index: number; of: number; title: string; minutes: number };
};

/** Everything the version cost: writing it, its voice (every line of it), and illustrations drawn while building. */
export function versionTotal(v: CostedVersion): number {
  const writing = v.costs ? Object.values(v.costs).reduce((t, line) => t + (line?.usd ?? 0), 0) : (v.costUsd ?? 0);
  return writing + (v.voiceLecture?.usd ?? v.voiceUsd ?? 0) + (v.build?.aiUsd ?? 0);
}

function seconds(s: number): string {
  if (s < 60) return `${Math.round(s)} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

const ENGINES: Record<string, string> = { gemini: "Gemini TTS", chirp: "Google Chirp 3 HD", silent: "silent", kokoro: "Kokoro (local)" };

type Row = { task: string; what: string; cost: number; free?: boolean; pending?: boolean };

/**
 * The cost of one lecture, task by task: transcribing it, writing the video script and fixing it, the SVGs drawn
 * (book figures and pictures, how many), AI illustrations, the narration voice (how many lines), and building the
 * video (on this machine: no charge, its time shown). `series` are all the parts of a lecture made as several
 * videos: their voices and builds are added up under the first part, which carries the writing.
 */
export function CostBreakdown({ version, series = [] }: { version: CostedVersion; series?: CostedVersion[] }) {
  const parts = series.length > 1 ? series : [version];
  const rows: Row[] = [];
  const costs = version.costs ?? {};
  for (const task of COST_TASKS) {
    const line = costs[task];
    if (!line || (!line.usd && !line.calls && !line.items && !line.note)) continue;
    const bits = [
      itemsText(task, line),
      line.calls ? `${line.calls} request${line.calls > 1 ? "s" : ""}` : "",
      line.inputTokens || line.outputTokens ? `${line.inputTokens.toLocaleString()} in / ${line.outputTokens.toLocaleString()} out` : "",
      line.note ?? "",
    ].filter(Boolean);
    rows.push({ task: COST_LABELS[task], what: bits.join(" · "), cost: line.usd });
  }
  if (!version.costs && version.costUsd) rows.push({ task: "Writing the lecture", what: "model requests", cost: version.costUsd });

  const voiced = parts.filter((p) => p.voiceLecture);
  if (voiced.length) {
    const lines = voiced.reduce((t, p) => t + (p.voiceLecture?.lines ?? 0), 0);
    const unknown = voiced.reduce((t, p) => t + (p.voiceLecture?.unknown ?? 0), 0);
    const engine = voiced[0].voiceLecture?.engine;
    rows.push({
      task: "Audio generation (narration)",
      what: [`${lines.toLocaleString()} lines`, engine ? ENGINES[engine] ?? engine : "",
        unknown ? `${unknown} spoken before costs were kept (not in the sum)` : "",
        voiced.length < parts.length ? `${parts.length - voiced.length} part${parts.length - voiced.length > 1 ? "s" : ""} not built yet` : ""]
        .filter(Boolean).join(" · "),
      cost: voiced.reduce((t, p) => t + (p.voiceLecture?.usd ?? 0), 0),
    });
  } else {
    rows.push({ task: "Audio generation (narration)", what: "spoken when the video is built", cost: 0, pending: true });
  }

  const built = parts.filter((p) => p.build);
  const aiImages = built.reduce((t, p) => t + (p.build?.aiImages ?? 0), 0);
  if (aiImages) {
    rows.push({ task: "AI illustrations (while building)", what: `${aiImages} image${aiImages > 1 ? "s" : ""}`,
      cost: built.reduce((t, p) => t + (p.build?.aiUsd ?? 0), 0) });
  }
  if (built.length) {
    const buildSeconds = built.reduce((t, p) => t + (p.build?.seconds ?? 0), 0);
    const voiceSeconds = built.reduce((t, p) => t + (p.build?.voiceSeconds ?? 0), 0);
    const runs = built.reduce((t, p) => t + (p.build?.count ?? 0), 0);
    rows.push({ task: "Building the video", what: [`on this machine, ${seconds(buildSeconds)}`,
      voiceSeconds ? `voice ${seconds(voiceSeconds)}` : "", runs > built.length ? `${runs} builds` : "",
      parts.length > 1 ? `${built.length} of ${parts.length} parts` : ""].filter(Boolean).join(" · "), cost: 0, free: true });
  } else {
    rows.push({ task: "Building the video", what: "on this machine, when it is built", cost: 0, free: true, pending: true });
  }

  const total = rows.reduce((t, r) => t + r.cost, 0);
  return (
    <details className="rounded border border-neutral-800 bg-neutral-950 text-xs" data-testid="cost-breakdown" open>
      <summary className="cursor-pointer select-none px-3 py-2 text-neutral-300">
        Cost <span className="font-mono text-neutral-100">{usd(total)}</span>
        {parts.length > 1 ? <span className="text-neutral-500"> for all {parts.length} parts</span> : null}
        <span className="text-neutral-500"> · breakdown</span>
      </summary>
      <div className="overflow-x-auto px-3 pb-3">
        <table className="w-full border-collapse tabular-nums">
          <thead>
            <tr className="text-left text-neutral-500">
              <th className="py-1 pr-3 font-normal">Task</th>
              <th className="py-1 pr-3 font-normal">What</th>
              <th className="py-1 text-right font-normal">Cost</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.task} className="border-t border-neutral-900 align-top">
                <td className="py-1 pr-3 text-neutral-200">{row.task}</td>
                <td className="py-1 pr-3 text-neutral-400">{row.what}</td>
                <td className="py-1 text-right font-mono text-neutral-200">
                  {row.pending ? "—" : row.free ? "free" : usd(row.cost)}
                </td>
              </tr>
            ))}
            <tr className="border-t border-neutral-700">
              <td className="py-1 pr-3 font-medium text-neutral-100" colSpan={2}>Total</td>
              <td className="py-1 text-right font-mono font-medium text-neutral-100">{usd(total)}</td>
            </tr>
          </tbody>
        </table>
        {total > 0 && (
          <p className="mt-1 text-neutral-500">
            {rows.filter((r) => r.cost > 0).sort((a, b) => b.cost - a.cost).slice(0, 3)
              .map((r) => `${r.task.split(" (")[0]} ${Math.round((r.cost / total) * 100)}%`).join(" · ")}
          </p>
        )}
      </div>
    </details>
  );
}
