/**
 * Questions on the videos: for each chapter, hard multiple-choice questions (four options) that test the student's
 * judgment, in English and in Hindi, each with where in the chapter's video the answer is taught.
 *
 * The chapter is given to the question writer as its narration, beat by beat, each beat with where it plays in the
 * video: the Voice tab's narrated chapter when there is one, else the Scenes tab's chapter render (its times are the
 * video's own), else the transcript alone (no times). The writer cites the beats that teach each answer; the times are
 * worked out here from those beats, never taken from the model. What comes back is checked (four different options,
 * a right answer, both languages, beats that exist) and the right answers spread over the four positions.
 */

import { callTool } from "./llm";
import { modelFor } from "./models";
import { part } from "./prompts/parts";
import { QUESTION_RULES } from "./prompts/questions";
import { check, log, newCall } from "./run";
import { scriptOf, stateOf as scenesOf } from "./scenes";
import { linesOf } from "./source/book";
import { loadRun, saveRun } from "./store";
import type { ChapterQuestions, Question, QuestionText, QuestionsState, Run } from "./types";
import { voiceOf } from "./voice";

export type QuestionsAction =
  | { action: "generate"; lecture: number; chapter?: number; count?: number; model?: string }
  | { action: "reset"; lecture: number; chapter?: number };

const COUNT = 8;
const AT_ONCE = 3;
const busy = ((globalThis as { __v2questionsBusy?: Set<string> }).__v2questionsBusy ??= new Set<string>());

export function questionsOf(run: Run): QuestionsState {
  return (run.questions ??= { lectures: {} });
}

type BeatTime = { start: number; end: number; from?: number; to?: number };
type Source = { beats: { n: number; text: string; time?: BeatTime }[]; source: ChapterQuestions["source"];
  video?: ChapterQuestions["video"]; title: string };

/** A chapter's narration beat by beat, with where each beat plays in its video. */
export function chapterSource(run: Run, n: number, c: number): Source {
  const ls = scriptOf(run, n);
  const chapter = ls?.chapters.find((ch) => ch.n === c);
  if (!chapter) throw new Error(`lecture ${n} has no chapter ${c} scripted yet`);
  const lines = linesOf(run.lectures.find((l) => l.n === n)?.text ?? "");
  const voiced = voiceOf(run).lectures[n]?.[c];
  const rendered = scenesOf(run).lectures[n]?.chapters?.[c];
  let source: Source["source"] = "none";
  let times: { n: number; start: number; end: number; from?: number; to?: number }[] = [];
  let video: Source["video"];
  if (voiced?.status === "done" && voiced.beats?.length) {
    source = "voice";
    times = voiced.beats;
    if (voiced.ir && voiced.assets) video = { ir: voiced.ir, assets: voiced.assets, audio: voiced.audio, fps: voiced.fps };
  } else if (rendered?.status === "done" && rendered.beats?.length) {
    source = "scenes";
    times = rendered.beats;
    if (rendered.ir && rendered.assets) video = { ir: rendered.ir, assets: rendered.assets, audio: rendered.audio, fps: rendered.fps };
  }
  const at = new Map(times.map((t) => [t.n, t]));
  const beats = chapter.beats.map((b) => {
    const t = at.get(b.n);
    return { n: b.n, text: b.lines.map((k) => lines[k - 1] ?? "").join(" ").trim(), time: t ? { start: t.start, end: t.end, from: t.from, to: t.to } : undefined };
  }).filter((b) => b.text);
  return { beats, source, video, title: chapter.title };
}

function clock(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

const TEXT = {
  type: "object",
  properties: {
    question: { type: "string" },
    options: { type: "array", items: { type: "string" }, minItems: 4, maxItems: 4 },
    explanation: { type: "string", description: "Why the right option is right (from the chapter), then a line on why each other option is wrong." },
  },
  required: ["question", "options", "explanation"],
  additionalProperties: false,
};

const QUESTION_TOOL = {
  type: "function" as const,
  function: {
    name: "write_questions",
    description: "The chapter's questions: each in English and Hindi, four options in the same order in both, the right one's index, its skill, and the beats that teach it.",
    parameters: {
      type: "object",
      properties: {
        questions: {
          type: "array",
          items: {
            type: "object",
            properties: {
              skill: { type: "string", enum: ["apply", "analyse", "evaluate", "infer"] },
              beats: { type: "array", items: { type: "integer" }, minItems: 1, maxItems: 4 },
              answer: { type: "integer", minimum: 0, maximum: 3 },
              en: TEXT,
              hi: TEXT,
            },
            required: ["skill", "beats", "answer", "en", "hi"],
            additionalProperties: false,
          },
        },
      },
      required: ["questions"],
      additionalProperties: false,
    },
  },
};

function readText(raw: unknown): QuestionText | undefined {
  const r = raw as Partial<QuestionText> | undefined;
  if (!r || typeof r.question !== "string" || !r.question.trim() || !Array.isArray(r.options)) return undefined;
  const options = r.options.map((o) => String(o ?? "").trim());
  if (options.length !== 4 || options.some((o) => !o)) return undefined;
  if (new Set(options.map((o) => o.toLowerCase())).size !== 4) return undefined;
  return { question: r.question.trim(), options, explanation: String(r.explanation ?? "").trim() };
}

/** The questions a reply gives, checked; and what was wrong with the ones left out. */
export function readQuestions(reply: unknown, src: Source, prefix: string): { questions: Question[]; dropped: string[] } {
  const got = Array.isArray((reply as { questions?: unknown })?.questions) ? (reply as { questions: unknown[] }).questions : [];
  const known = new Set(src.beats.map((b) => b.n));
  const out: Question[] = [];
  const dropped: string[] = [];
  got.forEach((raw, i) => {
    const q = raw as Record<string, unknown>;
    const en = readText(q.en);
    const hi = readText(q.hi);
    const answer = Number(q.answer);
    const beats = (Array.isArray(q.beats) ? q.beats : []).map(Number).filter((b) => known.has(b));
    if (!en || !hi) return void dropped.push(`question ${i + 1}: not four different options with a question in both English and Hindi`);
    if (!Number.isInteger(answer) || answer < 0 || answer > 3) return void dropped.push(`question ${i + 1}: no right answer among the four`);
    if (!beats.length) return void dropped.push(`question ${i + 1}: cites no beat of this chapter`);
    const times = beats.map((b) => src.beats.find((x) => x.n === b)?.time).filter((t): t is BeatTime => !!t);
    const at = times.length ? { start: Math.min(...times.map((t) => t.start)), end: Math.max(...times.map((t) => t.end)),
      from: times.every((t) => t.from !== undefined) ? Math.min(...times.map((t) => t.from!)) : undefined,
      to: times.every((t) => t.to !== undefined) ? Math.max(...times.map((t) => t.to!)) : undefined } : undefined;
    out.push({ id: `${prefix}q${out.length + 1}`, en, hi, answer, skill: String(q.skill ?? "apply"), beats: [...new Set(beats)].sort((a, b) => a - b), at });
  });
  return { questions: spread(out), dropped };
}

/** The right answers spread over the four positions (a model leans to one): a question whose position is already
 * taken more than its share has its options turned round, the same way in both languages. */
function spread(qs: Question[]): Question[] {
  const counts = [0, 0, 0, 0];
  const share = Math.ceil(qs.length / 4);
  return qs.map((q, i) => {
    let target = q.answer;
    if (counts[target] >= share) target = [0, 1, 2, 3].map((k) => (k + i) % 4).sort((a, b) => counts[a] - counts[b])[0];
    counts[target]++;
    if (target === q.answer) return q;
    const turn = (o: string[]) => o.map((_, k) => o[(k - target + q.answer + 4) % 4]);
    return { ...q, answer: target, en: { ...q.en, options: turn(q.en.options) }, hi: { ...q.hi, options: turn(q.hi.options) } };
  });
}

function fakeQuestions(src: Source, count: number) {
  // A stand-in (no key): questions that keep the shape, so the tab and the checks can be tried.
  return {
    questions: src.beats.slice(0, Math.max(1, Math.min(count, src.beats.length))).map((b, i) => ({
      skill: ["apply", "analyse", "evaluate", "infer"][i % 4], beats: [b.n], answer: i % 4,
      en: { question: `Stand-in question ${i + 1}: which idea does beat ${b.n} rest on?`,
        options: ["The first idea", "The second idea", "The third idea", "The fourth idea"], explanation: "A stand-in: no model was asked." },
      hi: { question: `नमूना प्रश्न ${i + 1}: बीट ${b.n} किस विचार पर टिकी है?`,
        options: ["पहला विचार", "दूसरा विचार", "तीसरा विचार", "चौथा विचार"], explanation: "नमूना: कोई मॉडल नहीं पूछा गया।" },
    })),
  };
}

async function generateChapter(run: Run, n: number, c: number, count: number, model: string): Promise<void> {
  const qs = questionsOf(run);
  const target: ChapterQuestions = ((qs.lectures[n] ??= {})[c] = { status: "running", questions: [], source: "none", calls: [], started: Date.now(), model });
  saveRun(run);
  try {
    const src = chapterSource(run, n, c);
    target.source = src.source;
    target.video = src.video;
    if (!src.beats.length) throw new Error("the chapter has no narration");
    const lectureTitle = run.lectures.find((l) => l.n === n)?.title ?? `Lecture ${n}`;
    const narration = src.beats.map((b) => `B${b.n}${b.time ? ` [${clock(b.time.start)}-${clock(b.time.end)}]` : ""}: ${b.text}`).join("\n");
    const call = newCall(run, { step: "questions", label: `Questions: lecture ${n}, chapter ${c}`, lecture: n, model, effort: "medium",
      prompt: { system: [part("rules", "How to write the questions", "rules", QUESTION_RULES)],
        user: [part("chapter", `Lecture ${n} (${lectureTitle}), chapter ${c}: ${src.title}`, "book", narration),
          part("ask", "Request", "ask", `Write ${count} questions on this chapter (write_questions).`)] } });
    target.calls.push(call.id);
    const reply = await callTool({ call, tool: QUESTION_TOOL, onChange: () => saveRun(run), fake: () => fakeQuestions(src, count) });
    if (!reply) throw new Error(call.error ?? "the model gave no questions");
    const { questions, dropped } = readQuestions(reply, src, `L${n}C${c}`);
    check(call, "Questions", questions.length >= Math.min(count, src.beats.length) ? "pass" : questions.length ? "fixed" : "fail",
      `${questions.length} question(s) kept${dropped.length ? `; left out: ${dropped.join("; ")}` : ""}`);
    if (!questions.length) throw new Error(`no question was usable: ${dropped.join("; ") || "none came back"}`);
    Object.assign(target, { status: "done", questions, notes: dropped.length ? dropped : undefined, at: Date.now() });
    if (src.source === "none") (target.notes ??= []).push("No rendered video of this chapter yet: render it (Voice or Scenes tab) and generate again to get the times.");
  } catch (error) {
    Object.assign(target, { status: "failed", error: (error as Error).message, at: Date.now() });
  }
  saveRun(run, true);
}

export async function questionsAction(id: string, a: QuestionsAction): Promise<Run> {
  const run = await loadRun(id);
  if (!run) throw new Error("no such run");
  if (run.legacy) throw new Error(run.legacy);
  const qs = questionsOf(run);
  const ls = scriptOf(run, a.lecture);
  if (!ls) throw new Error(`lecture ${a.lecture} is not scripted yet`);
  const chapters = a.chapter !== undefined ? [a.chapter] : ls.chapters.map((ch) => ch.n);
  if (a.action === "reset") {
    for (const c of chapters) if (!busy.has(`${id}|${a.lecture}|${c}`)) delete qs.lectures[a.lecture]?.[c];
    saveRun(run, true);
    return run;
  }
  const count = Math.max(2, Math.min(15, Math.round(a.count ?? qs.count ?? COUNT)));
  qs.count = count;
  if (a.model !== undefined) qs.model = a.model.trim() || undefined;
  const model = qs.model || modelFor("questions");
  const todo = chapters.filter((c) => !busy.has(`${id}|${a.lecture}|${c}`));
  for (const c of todo) busy.add(`${id}|${a.lecture}|${c}`);
  log(run, `Questions: lecture ${a.lecture}, ${todo.length === 1 ? `chapter ${todo[0]}` : `${todo.length} chapters`}, ${count} each.`);
  void (async () => {
    const queue = [...todo];
    await Promise.all(Array.from({ length: Math.min(AT_ONCE, queue.length) }, async () => {
      for (let c = queue.shift(); c !== undefined; c = queue.shift()) {
        try {
          await generateChapter(run, a.lecture, c, count, model);
        } finally {
          busy.delete(`${id}|${a.lecture}|${c}`);
        }
      }
    }));
  })();
  return run;
}
