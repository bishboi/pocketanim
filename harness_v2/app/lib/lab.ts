/**
 * The Lab: beat scripts written by hand (or started from a preset, lib/lab-presets.ts, or from a lecture's chapter)
 * to try an animation with the voice, apart from the lectures. Each experiment is a chapter's beat script, spoken and
 * played as the Voice tab tries an edited chapter (lib/voice.ts speakChapter): compiled with the run's look and a
 * lecture's figures, spoken with the voice set on the Voice tab, its animations timed to the words, and played with
 * its narration. Kept in the run (run.lab); its files under .data/runs/<run>/scenes/lab/<id>/.
 */

import { rm } from "node:fs/promises";
import path from "node:path";
import { LAB_EXAMPLES } from "./lab-presets";
import { scenesDir } from "./scenes";
import { loadRun, saveRun } from "./store";
import type { ChapterScript, LabItem, LabState, Run } from "./types";
import { chapterScript, readChapterScript, speakChapter } from "./voice";

export type LabAction =
  | { action: "add"; preset?: string; lecture?: number; chapter?: number; name?: string; script?: unknown }
  | { action: "save"; id: string; name?: string; lecture?: number; script?: unknown }
  | { action: "try"; id: string; script?: unknown }
  | { action: "duplicate"; id: string }
  | { action: "remove"; id: string };

const busy = ((globalThis as { __v2labBusy?: Set<string> }).__v2labBusy ??= new Set<string>());

export function labOf(run: Run): LabState {
  return (run.lab ??= { items: [] });
}

function itemDir(run: Run, id: string): string {
  return path.join(scenesDir(run.id), "lab", id);
}

function newId(lab: LabState): string {
  let k = lab.items.length + 1;
  while (lab.items.some((i) => i.id === `x${k}`)) k++;
  return `x${k}`;
}

/** The lecture an experiment is compiled with (its figures, its title): the one asked for, else the run's first. */
function lectureFor(run: Run, n?: number): number {
  return n !== undefined && run.lectures.some((l) => l.n === n) ? n : run.lectures[0]?.n ?? 1;
}

function find(lab: LabState, id: string): LabItem {
  const item = lab.items.find((i) => i.id === id);
  if (!item) throw new Error(`the Lab has no experiment ${id}`);
  return item;
}

export async function labAction(id: string, a: LabAction): Promise<LabItem | null> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (run.legacy) throw new Error(run.legacy);
  settleLab(run);
  const lab = labOf(run);
  if (a.action === "add") {
    let script: ChapterScript;
    let name = a.name?.trim();
    let from: string | undefined;
    let lecture = a.lecture;
    if (a.preset) {
      const p = LAB_EXAMPLES.find((x) => x.id === a.preset);
      if (!p) throw new Error(`no preset "${a.preset}"`);
      script = readChapterScript(p.script);
      name ||= p.name;
      from = p.id;
    } else if (a.chapter !== undefined) {
      const n = lectureFor(run, a.lecture);
      script = await chapterScript(run, n, a.chapter);
      // Beat numbers belong to the lecture's scenes; an experiment's beats are its own.
      script.chapter.beats = script.chapter.beats.map(({ beat: _, ...b }) => b);
      name ||= `Lecture ${n}, chapter ${a.chapter}: ${script.chapter.title}`;
      from = `L${n}c${a.chapter}`;
      lecture = n;
    } else {
      script = readChapterScript(a.script ?? { engine: "beta", chapter: { title: "An experiment", beats: [{ say: "Write the words said here.",
        layout: "center", elements: [{ id: "t", text: "Your words here", style: "title", slot: "main" }], animate: [{ id: "t", in: "type", on: "words" }] }] } });
      name ||= "An experiment";
    }
    const item: LabItem = { id: newId(lab), name, from, lecture: lectureFor(run, lecture), script, at: Date.now() };
    lab.items.push(item);
    saveRun(run, true);
    return item;
  }
  const item = find(lab, a.id);
  if (a.action === "save") {
    if (a.script !== undefined) item.script = readChapterScript(a.script);
    if (a.name?.trim()) item.name = a.name.trim();
    if (a.lecture !== undefined) item.lecture = lectureFor(run, a.lecture);
    item.at = Date.now();
    saveRun(run, true);
    return item;
  }
  if (a.action === "duplicate") {
    const copy: LabItem = { ...structuredClone({ ...item, result: undefined }), id: newId(lab), name: `${item.name} (copy)`, at: Date.now() };
    lab.items.splice(lab.items.indexOf(item) + 1, 0, copy);
    saveRun(run, true);
    return copy;
  }
  const key = `${id}|${item.id}`;
  if (a.action === "remove") {
    if (busy.has(key)) throw new Error("it is being tried: wait for it to finish");
    lab.items.splice(lab.items.indexOf(item), 1);
    await rm(itemDir(run, item.id), { recursive: true, force: true });
    saveRun(run, true);
    return null;
  }
  // Try: the script as it is in the editor (saved first), spoken and played.
  if (busy.has(key)) throw new Error("it is being tried already");
  if (a.script !== undefined) item.script = readChapterScript(a.script);
  const target = item.result = { status: "running", phase: "waiting", edited: item.script, started: Date.now() };
  busy.add(key);
  saveRun(run, true);
  void (async () => {
    try {
      await speakChapter(run, lectureFor(run, item.lecture), 0, target, item.script, { dir: itemDir(run, item.id), name: item.name });
    } catch (error) {
      Object.assign(target, { status: "failed", phase: undefined, error: (error as Error).message, at: Date.now() });
    } finally {
      busy.delete(key);
      saveRun(run, true);
    }
  })();
  return item;
}

/** An experiment marked running that nothing is trying (the server restarted mid-way): failed, so it can be tried again. */
export function settleLab(run: Run): void {
  for (const item of run.lab?.items ?? []) {
    if (item.result?.status === "running" && !busy.has(`${run.id}|${item.id}`))
      Object.assign(item.result, { status: "failed", phase: undefined, error: "interrupted (the server restarted): try it again" });
  }
}
