"use client";

import { COST_LABELS, COST_TASKS, busySeconds, duration, itemsText, usd, type Costs } from "@/lib/costs";

/** What a version holds about its cost: writing it (task by task), its voice and its builds. */
export type CostedVersion = {
  costUsd?: number;
  costs?: Costs;
  voiceUsd?: number;
  voiceLecture?: { usd: number; lines: number; unknown: number; engine?: string };
  build?: { seconds: number; voiceSeconds: number; count: number; aiImages: number; aiUsd: number };
  part?: { index: number; of: number; title: string; minutes: number };
  writeSeconds?: number;
  mp4Seconds?: number;
  saveSeconds?: number;
};

/** Everything the version cost: writing it, its voice (every line of it), and illustrations drawn while building. */
export function versionTotal(v: CostedVersion): number {
  const writing = v.costs ? Object.values(v.costs).reduce((t, line) => t + (line?.usd ?? 0), 0) : (v.costUsd ?? 0);
  return writing + (v.voiceLecture?.usd ?? v.voiceUsd ?? 0) + (v.build?.aiUsd ?? 0);
}


const ENGINES: Record<string, string> = { gemini: "Gemini TTS", chirp: "Google Chirp 3 HD", silent: "silent", kokoro: "Kokoro (local)" };

type Row = { task: string; what: string; cost: number; free?: boolean; pending?: boolean;
  /** Seconds of the clock it took; left out when it was not timed. */
  time?: number; stage?: "writing" | "after" };

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
    rows.push({ task: COST_LABELS[task], what: bits.join(" · "), cost: line.usd, time: line.seconds, stage: "writing" });
  }
  if (!version.costs && version.costUsd) rows.push({ task: "Writing the lecture", what: "model requests", cost: version.costUsd,
    stage: "writing" });
  // The writing's time no task above accounts for: choosing the subject and map, checking and compiling the script,
  // waiting between turns.
  const writing = version.writeSeconds;
  if (writing) {
    const other = writing - busySeconds(costs);
    if (other >= 1) {
      rows.push({ task: "Planning and checks", what: "the subject, the map, checking and compiling the script",
        cost: 0, free: true, time: other, stage: "writing" });
    }
  }

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
      time: parts.reduce((t, p) => t + (p.build?.voiceSeconds ?? 0), 0) || undefined,
      stage: "after",
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
    const runs = built.reduce((t, p) => t + (p.build?.count ?? 0), 0);
    rows.push({ task: "Building the video", what: ["rendering and baking the phone program, on this machine",
      runs > built.length ? `${runs} builds (the latest timed)` : "",
      parts.length > 1 ? `${built.length} of ${parts.length} parts` : ""].filter(Boolean).join(" · "), cost: 0, free: true,
      time: buildSeconds, stage: "after" });
  } else {
    rows.push({ task: "Building the video", what: "on this machine, when it is built", cost: 0, free: true, pending: true });
  }
  const mp4 = parts.reduce((t, p) => t + (p.mp4Seconds ?? 0), 0);
  if (mp4) rows.push({ task: "Rendering the MP4", what: "the downloaded video, on this machine", cost: 0, free: true, time: mp4,
    stage: "after" });
  const saved = parts.reduce((t, p) => t + (p.saveSeconds ?? 0), 0);
  if (saved) rows.push({ task: "Saving to the library", what: "packing the phone files and uploading them", cost: 0, free: true,
    time: saved, stage: "after" });

  const total = rows.reduce((t, r) => t + r.cost, 0);
  // The writing's tasks run at the same time (figures are drawn while the script is written), so its time is the
  // clock from Generate to done, not their sum; what comes after (voice, build, MP4, save) runs one after another.
  const writingTime = writing ?? (busySeconds(costs) || 0);
  const afterTime = rows.filter((r) => r.stage === "after").reduce((t, r) => t + (r.time ?? 0), 0);
  const totalTime = writingTime + afterTime;
  return (
    <details className="rounded border border-neutral-800 bg-neutral-950 text-xs" data-testid="cost-breakdown" open>
      <summary className="cursor-pointer select-none px-3 py-2 text-neutral-300">
        Cost <span className="font-mono text-neutral-100">{usd(total)}</span>
        {totalTime > 0 && <> · time <span className="font-mono text-neutral-100">{duration(totalTime)}</span></>}
        {parts.length > 1 ? <span className="text-neutral-500"> for all {parts.length} parts</span> : null}
        <span className="text-neutral-500"> · breakdown</span>
      </summary>
      <div className="overflow-x-auto px-3 pb-3">
        <table className="w-full border-collapse tabular-nums">
          <thead>
            <tr className="text-left text-neutral-500">
              <th className="py-1 pr-3 font-normal">Task</th>
              <th className="py-1 pr-3 font-normal">What</th>
              <th className="py-1 pr-3 text-right font-normal">Time</th>
              <th className="py-1 text-right font-normal">Cost</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.task} className="border-t border-neutral-900 align-top">
                <td className="py-1 pr-3 text-neutral-200">{row.task}</td>
                <td className="py-1 pr-3 text-neutral-400">{row.what}</td>
                <td className="whitespace-nowrap py-1 pr-3 text-right font-mono text-neutral-300">
                  {row.time ? duration(row.time) : "—"}
                </td>
                <td className="py-1 text-right font-mono text-neutral-200">
                  {row.pending ? "—" : row.free ? "free" : usd(row.cost)}
                </td>
              </tr>
            ))}
            {writingTime > 0 && (
              <tr className="border-t border-neutral-800 text-neutral-400">
                <td className="py-1 pr-3" colSpan={2}>Writing, start to finish (its tasks run side by side)</td>
                <td className="py-1 pr-3 text-right font-mono">{duration(writingTime)}</td>
                <td />
              </tr>
            )}
            <tr className="border-t border-neutral-700">
              <td className="py-1 pr-3 font-medium text-neutral-100" colSpan={2}>Total</td>
              <td className="whitespace-nowrap py-1 pr-3 text-right font-mono font-medium text-neutral-100">
                {totalTime > 0 ? duration(totalTime) : "—"}
              </td>
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
