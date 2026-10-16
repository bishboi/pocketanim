/**
 * A run's transcript as a file to keep: every lecture's text with its sentences numbered (the numbers the scene
 * script will name), its goals with the sentences that teach them, the book's blocks each lecture teaches (Datalab's
 * id, type, HTML, page and box) and each figure's description and triage. JSON for the steps to come, Markdown to
 * read. An exported JSON can be imported again as a run (importTranscript), so later steps can start from it.
 */

import { linesOf } from "./source/book";
import { choiceOf, type TriageKind } from "./triage-kinds";
import { newId, saveRun } from "./store";
import type { GoalStatus, LectureState, Run, Step } from "./types";
import type { Block } from "./source/blocks";

export const EXPORT_FORMAT = "pocketanim.v2.transcript";
export const EXPORT_VERSION = 1;

export type ExportedLine = { n: number; text: string; goals: string[]; patch?: string[] };
export type ExportedLecture = {
  n: number; title: string; why: string; status: LectureState["status"]; words: number; minutes: number;
  blocks: string[];
  goals: { id: string; goal: string; misconception: string; hook: string; blocks: string[]; status: GoalStatus; lines: number[] }[];
  lines: ExportedLine[];
  /** The text as written (paragraphs kept); `lines` is it sentence by sentence. */
  text: string;
  blocksTaught: string[];
};
export type ExportedBlock = Pick<Block, "id" | "type" | "html" | "text" | "page" | "box"> & {
  lecture?: number;
  skipped?: string;
  figure?: { image: string; description?: string; triage?: { kind: TriageKind; label: string; chosenBy: "model" | "user"; how?: string; reason?: string; keep?: string[] } };
};
export type ExportedTranscript = {
  format: typeof EXPORT_FORMAT;
  version: number;
  exported: string;
  run: { id: string; created: string; status: Run["status"]; options: Run["options"] };
  document: { id: string; name: string; pdf: string };
  lectures: ExportedLecture[];
  blocks: ExportedBlock[];
  triage?: { kinds: TriageKind[]; model: string; status: string };
};

export function exportTranscript(run: Run): ExportedTranscript {
  const home = new Map(run.lectures.flatMap((l) => l.blocks.map((id) => [id, l.n] as const)));
  const skipped = new Map(run.skipped.map((s) => [s.block, s.reason]));
  const lectures: ExportedLecture[] = run.lectures.map((l) => {
    const lines = linesOf(l.text ?? "");
    const words = (l.text ?? "").split(/\s+/).filter(Boolean).length;
    return {
      n: l.n, title: l.title, why: l.why, status: l.status, words, minutes: Math.round(words / 10) / 10,
      blocks: l.blocks,
      goals: l.goals.map((g) => ({ id: g.id, goal: g.goal, misconception: g.misconception, hook: g.hook, blocks: g.blocks,
        status: run.goalStatus[g.id] ?? "waiting", lines: l.goalLines?.[g.id] ?? [] })),
      lines: lines.map((text, k) => {
        const n = k + 1;
        const patch = l.patched?.find((p) => p.lines.includes(n));
        return { n, text, goals: Object.entries(l.goalLines ?? {}).filter(([, ns]) => ns.includes(n)).map(([id]) => id),
          ...(patch ? { patch: patch.covers } : {}) };
      }),
      text: l.text ?? "",
      blocksTaught: l.blocksTaught ?? [],
    };
  });
  const blocks: ExportedBlock[] = run.blocks.map((b) => {
    const t = run.triage?.figures[b.id];
    const kind = t?.override ?? (t?.status === "done" ? t.kind : undefined);
    return {
      id: b.id, type: b.type, html: b.html, text: b.text, page: b.page, box: b.box,
      ...(home.has(b.id) ? { lecture: home.get(b.id) } : {}),
      ...(skipped.has(b.id) ? { skipped: skipped.get(b.id) } : {}),
      ...(b.image || b.description ? { figure: {
        image: `/api/documents/${run.documentId}/figure/${encodeURIComponent(b.id)}`,
        ...(b.description ? { description: b.description } : {}),
        ...(kind ? { triage: { kind, label: choiceOf(kind)!.label, chosenBy: t?.override ? "user" as const : "model" as const,
          how: t?.how, reason: t?.reason, keep: t?.keep } } : {}),
      } } : {}),
    };
  });
  return {
    format: EXPORT_FORMAT, version: EXPORT_VERSION, exported: new Date().toISOString(),
    run: { id: run.id, created: new Date(run.created).toISOString(), status: run.status, options: run.options },
    document: { id: run.documentId, name: run.documentName, pdf: `/api/documents/${run.documentId}/pdf` },
    lectures, blocks,
    ...(run.triage ? { triage: { kinds: run.triage.kinds, model: run.triage.model, status: run.triage.status } } : {}),
  };
}

export function transcriptMarkdown(run: Run): string {
  const x = exportTranscript(run);
  const out = [`# ${x.document.name}: transcript`, "",
    `Run ${x.run.id}, ${x.run.created}. ${x.lectures.length} lecture(s), about ${Math.round(x.lectures.reduce((n, l) => n + l.minutes, 0))} min in all.`, ""];
  const byId = new Map(x.blocks.map((b) => [b.id, b]));
  for (const l of x.lectures) {
    out.push(`## Lecture ${l.n}: ${l.title}`, "", `_${l.why}_`, "", `${l.words} words, about ${l.minutes} min. ${l.status === "written" ? "" : `(${l.status})`}`.trim(), "");
    out.push("### Goals", "");
    for (const g of l.goals) out.push(`- **${g.id}** (${g.status}${g.lines.length ? `, sentences ${g.lines.join(", ")}` : ""}): ${g.goal}`);
    const figures = l.blocks.map((id) => byId.get(id)).filter((b) => b?.figure);
    if (figures.length) {
      out.push("", "### Figures", "");
      for (const b of figures) {
        const t = b!.figure!.triage;
        out.push(`- \`${b!.id}\`${t ? ` — **${t.label}**${t.chosenBy === "user" ? " (chosen by hand)" : ""}: ${t.how ?? ""}` : ""}` +
          (b!.figure!.description ? `\n  ${b!.figure!.description}` : ""));
      }
    }
    out.push("", "### Transcript", "");
    for (const line of l.lines) out.push(`${line.n}. ${line.text}${line.goals.length ? `  _[${line.goals.join(", ")}]_` : ""}${line.patch ? "  _(written in after)_" : ""}`);
    out.push("");
  }
  return out.join("\n");
}

/** An exported transcript (JSON) as a run of its own: the transcript's steps done, nothing called again. */
export function importTranscript(data: unknown, file: string): Run {
  const x = data as ExportedTranscript;
  if (x?.format !== EXPORT_FORMAT) throw new Error("not an exported v2 transcript (its format is not pocketanim.v2.transcript)");
  if (!Array.isArray(x.lectures) || !Array.isArray(x.blocks)) throw new Error("the file has no lectures or blocks");
  const goalStatus: Record<string, GoalStatus> = {};
  const lectures: LectureState[] = x.lectures.map((l) => {
    for (const g of l.goals) goalStatus[g.id] = g.status;
    const patched = new Map<string, { covers: string[]; lines: number[] }>();
    for (const line of l.lines) if (line.patch) {
      const k = line.patch.join(",");
      if (!patched.has(k)) patched.set(k, { covers: line.patch, lines: [] });
      patched.get(k)!.lines.push(line.n);
    }
    return { n: l.n, title: l.title, why: l.why, blocks: l.blocks, status: l.status === "written" ? "written" : "waiting",
      goals: l.goals.map((g) => ({ id: g.id, lecture: l.n, goal: g.goal, blocks: g.blocks, misconception: g.misconception, hook: g.hook })),
      text: l.text || undefined, goalLines: Object.fromEntries(l.goals.filter((g) => g.lines.length).map((g) => [g.id, g.lines])),
      blocksTaught: l.blocksTaught, patched: [...patched.values()], calls: [] };
  });
  const blocks: Block[] = x.blocks.map((b) => ({ id: b.id, type: b.type, html: b.html, text: b.text, page: b.page, box: b.box,
    ...(b.figure?.image ? { image: true } : {}), ...(b.figure?.description ? { description: b.figure.description } : {}) }));
  const done = (key: Step["key"], label: string, summary: string): Step => ({ key, label, status: "done", summary });
  const written = lectures.filter((l) => l.status === "written").length;
  const run: Run = {
    id: newId(), documentId: x.document.id, documentName: x.document.name, created: Date.now(), ended: Date.now(),
    status: written === lectures.length ? "done" : "stopped", options: x.run.options,
    steps: [
      done("read", "Read the book", `${blocks.length} blocks (imported)`),
      done("figures", "Describe figures", `${blocks.filter((b) => b.description).length} described (imported)`),
      done("plan", "Plan lectures and goals", `${lectures.length} lectures (imported)`),
      { key: "write", label: "Write lectures", status: written === lectures.length ? "done" : "waiting", summary: `${written} of ${lectures.length} written (imported)` },
    ],
    blocks, skipped: x.blocks.filter((b) => b.skipped).map((b) => ({ block: b.id, reason: b.skipped! })), lectures, goalStatus,
    calls: [], log: [{ t: Date.now(), text: `Imported from ${file} (run ${x.run.id}, exported ${x.exported}).` }],
    imported: { file, at: Date.now() },
  };
  const triaged = x.blocks.filter((b) => b.figure?.triage);
  if (x.triage) {
    run.triage = { status: "done", kinds: x.triage.kinds, model: x.triage.model, rounds: 0, figures: Object.fromEntries(triaged.map((b) => {
      const t = b.figure!.triage!;
      return [b.id, { block: b.id, status: "done", kind: t.kind, how: t.how, reason: t.reason, keep: t.keep, calls: [],
        ...(t.chosenBy === "user" ? { override: t.kind } : {}) }];
    })) };
  }
  saveRun(run, true);
  return run;
}
