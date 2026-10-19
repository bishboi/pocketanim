/**
 * A run's transcript as one file that later steps start from: every lecture's text with its sentences numbered (the
 * numbers the scene script will name), its goals with the sentences that teach them, the book's blocks each lecture
 * teaches (Datalab's id, type, HTML, page and box), each figure's description and triage, and the book itself (the
 * PDF, Datalab's JSON and the figure pictures, base64). With the book inside, the file is whole: imported on any
 * machine (importTranscript) it becomes a run with every step done, the book read again from it, so the next steps
 * (triage, scene script...) and Continue work as on the run it came from. Markdown is the same to read only.
 */

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { linesOf } from "./source/book";
import { choiceOf, type TriageKind } from "./triage-kinds";
import { docDir, documentInfo, listDocuments, newId, saveRun } from "./store";
import type { RawBlock } from "./datalab";
import type { Chapter, DocumentInfo, GoalStatus, LectureState, Run, Step } from "./types";
import type { Block } from "./source/blocks";
import { ALL_KINDS } from "./visual-kinds";

export const EXPORT_FORMAT = "pocketanim.v2.transcript";
/** 2: the book inside (`book`); 1 (no book) is still read. */
export const EXPORT_VERSION = 2;

/** The book as the file carries it: enough to read it again with no Datalab call. */
export type ExportedBook = {
  info: DocumentInfo;
  /** sha256 of the PDF: an import finds the book already here by it. */
  sha256: string;
  pdf: string;
  /** Datalab's JSON of it, as converted. */
  datalab: RawBlock;
  /** Each figure's picture by block id: its file's name and its bytes. */
  figures: Record<string, { name: string; base64: string }>;
};

export type ExportedLine = { n: number; text: string; goals: string[]; patch?: string[] };
export type ExportedLecture = {
  n: number; title: string; why: string; status: LectureState["status"]; words: number; minutes: number;
  blocks: string[];
  goals: { id: string; goal: string; misconception: string; hook: string; blocks: string[]; status: GoalStatus; lines: number[] }[];
  lines: ExportedLine[];
  /** The text as written (paragraphs kept); `lines` is it sentence by sentence. */
  text: string;
  blocksTaught: string[];
  /** Its script, when it has one: chapters, and beats naming the `lines` above by number. */
  script?: { chapters: Chapter[] };
  /** Its scenes, when it has them: the map region, and each beat's operations (and kinds of its own) by beat number. */
  scenes?: { region?: Record<string, unknown> | null; beats: Record<string, { ops: Record<string, unknown>[]; kinds?: string[]; edited?: boolean }>;
    chapterKinds?: Record<string, string[]> };
};
export type ExportedBlock = Pick<Block, "id" | "type" | "html" | "text" | "page" | "box"> & {
  lecture?: number;
  skipped?: string;
  figure?: { image: string; description?: string; triage?: { kind: TriageKind; label: string; chosenBy: "model" | "user"; how?: string; reason?: string; keep?: string[];
    engine?: "decision" | "chat"; probabilities?: Record<string, number>; confidence?: number; unsure?: boolean; rule?: string };
    /** The redraw generated for it: the image model, the prompt as sent, and the image (on the server that made it). */
    generated?: { kind?: string; model: string; prompt?: string; image?: string } };
};
export type ExportedTranscript = {
  format: typeof EXPORT_FORMAT;
  version: number;
  exported: string;
  run: { id: string; created: string; status: Run["status"]; options: Run["options"] };
  document: { id: string; name: string; pdf: string };
  lectures: ExportedLecture[];
  blocks: ExportedBlock[];
  triage?: { kinds: TriageKind[]; model: string; status: string; engine?: string; chatModel?: string; threshold?: number };
  /** The scenes' look and the visual kinds switched on. */
  scenes?: { model: string; look: { style: string; art: string }; kinds: string[] };
  /** What the transcript cost, by step (USD). */
  costs?: Record<string, number>;
  book?: ExportedBook;
};

/** The whole file: the transcript and the book inside it. */
export async function exportWhole(run: Run): Promise<ExportedTranscript> {
  return { ...exportTranscript(run), book: await bookOf(run.documentId) };
}

async function bookOf(id: string): Promise<ExportedBook | undefined> {
  const dir = docDir(id);
  if (!existsSync(path.join(dir, "source.pdf"))) return undefined;
  const pdf = await readFile(path.join(dir, "source.pdf"));
  const files: Record<string, string> = JSON.parse(await readFile(path.join(dir, "figures.json"), "utf8").catch(() => "{}"));
  const figures: ExportedBook["figures"] = {};
  for (const [block, file] of Object.entries(files)) {
    const bytes = await readFile(file).catch(() => null);
    if (bytes) figures[block] = { name: path.basename(file), base64: bytes.toString("base64") };
  }
  return { info: await documentInfo(id), sha256: createHash("sha256").update(pdf).digest("hex"), pdf: pdf.toString("base64"),
    datalab: JSON.parse(await readFile(path.join(dir, "book.json"), "utf8")), figures };
}

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
      ...(run.script?.lectures[l.n]?.status === "done" ? { script: { chapters: run.script.lectures[l.n].chapters } } : {}),
      ...(run.scenes?.lectures[l.n] && Object.keys(run.scenes.lectures[l.n].beats).length ? { scenes: { region: run.scenes.lectures[l.n].region,
        beats: Object.fromEntries(Object.values(run.scenes.lectures[l.n].beats).map((b) => [b.n, { ops: b.ops,
          ...(b.kinds ? { kinds: b.kinds } : {}), ...(b.edited ? { edited: true } : {}) }])),
        ...(run.scenes.lectures[l.n].chapterKinds ? { chapterKinds: run.scenes.lectures[l.n].chapterKinds } : {}) } } : {}),
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
          how: t?.how, reason: t?.reason, keep: t?.keep, engine: t?.engine, probabilities: t?.probabilities, confidence: t?.confidence,
          unsure: t?.unsure, rule: t?.rule } } : {}),
        ...(run.generation?.figures[b.id]?.status === "done" ? { generated: { kind: run.generation.figures[b.id].kind,
          model: run.generation.model, prompt: run.generation.figures[b.id].prompt, image: `/api/runs/${run.id}/generated/${encodeURIComponent(b.id)}` } } : {}),
      } } : {}),
    };
  });
  return {
    format: EXPORT_FORMAT, version: EXPORT_VERSION, exported: new Date().toISOString(),
    run: { id: run.id, created: new Date(run.created).toISOString(), status: run.status, options: run.options },
    document: { id: run.documentId, name: run.documentName, pdf: `/api/documents/${run.documentId}/pdf` },
    lectures, blocks,
    ...(run.triage ? { triage: { kinds: run.triage.kinds, model: run.triage.model, status: run.triage.status, engine: run.triage.engine,
      chatModel: run.triage.chatModel, threshold: run.triage.threshold } } : {}),
    ...(run.scenes ? { scenes: { model: run.scenes.model, look: run.scenes.look, kinds: run.scenes.kinds } } : {}),
    costs: run.calls.reduce<Record<string, number>>((m, c) => ({ ...m, [c.step]: (m[c.step] ?? 0) + c.cost }), {}),
  };
}

export function transcriptMarkdown(run: Run): string {
  const x = exportTranscript(run);
  const out = [`# ${x.document.name}: transcript`, "",
    `Run ${x.run.id}, ${x.run.created}. ${x.lectures.length} lecture(s), about ${Math.round(x.lectures.reduce((n, l) => n + l.minutes, 0))} min in all.`, ""];
  const byId = new Map(x.blocks.map((b) => [b.id, b]));
  for (const l of x.lectures) {
    out.push(`## Lecture ${l.n}: ${l.title}`, "", `_${l.why}_`, "", `${l.words} words, about ${l.minutes} min. ${l.status === "written" ? "" : `(${l.status})`}`.trim(), "");
    if (l.goals.length) {
      out.push("### Goals", "");
      for (const g of l.goals) out.push(`- **${g.id}** (${g.status}${g.lines.length ? `, sentences ${g.lines.join(", ")}` : ""}): ${g.goal}`);
    }
    const figures = l.blocks.map((id) => byId.get(id)).filter((b) => b?.figure);
    if (figures.length) {
      out.push("", "### Figures", "");
      for (const b of figures) {
        const t = b!.figure!.triage;
        out.push(`- \`${b!.id}\`${t ? ` — **${t.label}**${t.chosenBy === "user" ? " (chosen by hand)" : ""}: ${t.how ?? ""}` : ""}` +
          (b!.figure!.description ? `\n  ${b!.figure!.description}` : ""));
      }
    }
    if (l.script?.chapters.length) {
      // The lecture as its script: each chapter (its stage and the book's blocks it teaches from), each beat's words.
      out.push("", "### Script", "");
      for (const c of l.script.chapters) {
        out.push(`#### Chapter ${c.n}: ${c.title} (${c.map ? "on the board, the map in for its beats on places" : "on the board"})`, "", `_Title card: ${c.narration}_`, "",
          `Content: ${(c.content ?? []).map((id) => `\`${id}\``).join(", ") || "none named"}`, "");
        for (const b of c.beats) {
          const figures = b.figures ?? (b.figure ? [b.figure] : []);
          out.push(`${b.n}. ${b.lines.map((k) => l.lines[k - 1]?.text ?? "").join(" ")}  _[on screen: ${b.show || "-"}${figures.length ? `; figures ${figures.join(", ")}` : ""}]_`);
        }
        out.push("");
      }
    } else {
      out.push("", "### Transcript", "");
      for (const line of l.lines) out.push(`${line.n}. ${line.text}${line.goals.length ? `  _[${line.goals.join(", ")}]_` : ""}${line.patch ? "  _(written in after)_" : ""}`);
      out.push("");
    }
  }
  return out.join("\n");
}

/**
 * The book of an imported file, here: the same PDF already uploaded (by its sha256), else the one the file names if
 * it is here, else made again from the file (the PDF, Datalab's JSON and figures it carries; Datalab is not called).
 */
async function placeBook(x: ExportedTranscript): Promise<{ id: string; how: string }> {
  if (x.book?.sha256) {
    for (const d of await listDocuments()) {
      const pdf = await readFile(path.join(docDir(d.id), "source.pdf")).catch(() => null);
      if (pdf && createHash("sha256").update(pdf).digest("hex") === x.book.sha256) return { id: d.id, how: `the book already here (${d.name})` };
    }
  }
  if (!x.book) {
    if (existsSync(path.join(docDir(x.document.id), "source.pdf"))) return { id: x.document.id, how: "the book already here" };
    return { id: x.document.id, how: "no book: the file carries none and it is not here (the PDF and figures will be missing)" };
  }
  const id = newId();
  const dir = docDir(id);
  await mkdir(path.join(dir, "figures"), { recursive: true });
  await writeFile(path.join(dir, "source.pdf"), Buffer.from(x.book.pdf, "base64"));
  await writeFile(path.join(dir, "book.json"), JSON.stringify(x.book.datalab), "utf8");
  const figures: Record<string, string> = {};
  for (const [block, f] of Object.entries(x.book.figures ?? {})) {
    const file = path.join(dir, "figures", path.basename(f.name));
    await writeFile(file, Buffer.from(f.base64, "base64"));
    figures[block] = file;
  }
  await writeFile(path.join(dir, "figures.json"), JSON.stringify(figures), "utf8");
  await writeFile(path.join(dir, "info.json"), JSON.stringify({ ...x.book.info, id, created: Date.now() }), "utf8");
  return { id, how: `the book made again from the file (${x.book.info.name}, ${Object.keys(figures).length} figure pictures)` };
}

/** Whether a parsed file is an exported transcript this version reads; the reason when it is not. */
export function checkExport(data: unknown): string | null {
  const x = data as ExportedTranscript;
  if (x?.format !== EXPORT_FORMAT) return "not an exported v2 transcript (its format is not pocketanim.v2.transcript)";
  if (typeof x.version !== "number" || x.version > EXPORT_VERSION) return `made by a newer harness (version ${x.version}; this one reads up to ${EXPORT_VERSION})`;
  if (!Array.isArray(x.lectures) || !Array.isArray(x.blocks)) return "the file has no lectures or blocks";
  if (!x.document?.id || !x.run?.options) return "the file has no document or run options";
  for (const l of x.lectures) {
    if (!Array.isArray(l.lines) || !Array.isArray(l.blocks)) return `lecture ${l.n} is missing its lines or blocks`;
    l.goals ??= [];
  }
  return null;
}

/** An exported transcript (JSON) as a run of its own: the transcript's steps done, nothing called again. */
export async function importTranscript(data: unknown, file: string): Promise<Run> {
  const problem = checkExport(data);
  if (problem) throw new Error(problem);
  const x = data as ExportedTranscript;
  const book = await placeBook(x);
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
    id: newId(), documentId: book.id, documentName: x.document.name, created: Date.now(), ended: Date.now(),
    status: written === lectures.length ? "done" : "stopped", options: x.run.options,
    steps: [
      done("read", "Read the book", `${blocks.length} blocks (imported)`),
      done("figures", "Describe figures", `${blocks.filter((b) => b.description).length} described (imported)`),
      // A run made before the lectures were written as scripts had a planner step.
      ...(lectures.some((l) => l.goals.length) ? [done("plan", "Plan lectures and goals", `${lectures.length} lectures (imported)`)] : []),
      { key: "write", label: "Write lectures (chapters, beats)", status: written === lectures.length ? "done" : "waiting", summary: `${written} of ${lectures.length} written (imported)` },
    ],
    blocks, skipped: x.blocks.filter((b) => b.skipped).map((b) => ({ block: b.id, reason: b.skipped! })), lectures, goalStatus,
    calls: [], log: [{ t: Date.now(), text: `Imported from ${file} (run ${x.run.id}, exported ${x.exported}); ${book.how}.` }],
    imported: { file, at: Date.now() },
  };
  const scripted = x.lectures.filter((l) => l.script?.chapters?.length);
  if (scripted.length) {
    run.script = { status: "done", model: x.run.options.scriptModel ?? "", rounds: 0, lectures: Object.fromEntries(scripted.map((l) =>
      [l.n, { lecture: l.n, status: "done", chapters: l.script!.chapters, lines: l.lines.length, calls: [] }])) };
  }
  const withScenes = x.lectures.filter((l) => l.scenes && Object.keys(l.scenes.beats).length);
  if (x.scenes || withScenes.length) {
    run.scenes = { status: "done", model: x.scenes?.model ?? "", look: x.scenes?.look ?? { style: "atlas", art: "auto" }, kinds: x.scenes?.kinds ?? ALL_KINDS,
      rounds: 0, lectures: Object.fromEntries(withScenes.map((l) => [l.n, { lecture: l.n, status: "done", region: l.scenes!.region, calls: [],
        ...(l.scenes!.chapterKinds ? { chapterKinds: l.scenes!.chapterKinds } : {}),
        beats: Object.fromEntries(Object.entries(l.scenes!.beats).map(([n, b]) => [n, { n: Number(n), status: "done", ops: b.ops, kinds: b.kinds,
          edited: b.edited, calls: [] }])) }])) };
  }
  const triaged = x.blocks.filter((b) => b.figure?.triage);
  if (x.triage) {
    run.triage = { status: "done", kinds: x.triage.kinds, model: x.triage.model, rounds: 0,
      engine: x.triage.engine === "chat" ? "chat" : "decision", chatModel: x.triage.chatModel, threshold: x.triage.threshold,
      figures: Object.fromEntries(triaged.map((b) => {
      const t = b.figure!.triage!;
      return [b.id, { block: b.id, status: "done", kind: t.kind, how: t.how, reason: t.reason, keep: t.keep, calls: [],
        engine: t.engine, probabilities: t.probabilities, confidence: t.confidence, unsure: t.unsure,
        ...(t.chosenBy === "user" ? { override: t.kind } : {}) }];
    })) };
  }
  saveRun(run, true);
  return run;
}
