/**
 * The transcription flow, v1's structure, every step visible:
 *
 *   1. read    the book cut into sections by code; its questions and items found         (no model)
 *   2. map     the learning goals, every item of the book under one                      (1 call)
 *   3. plan    the videos decided from the sections; each video's story                  (1 call per video)
 *   4. write   each section's transcript, several at once; its goals checked, a missing
 *              goal written in by a small patch                                           (1 call per section, + patches)
 *   5. videos  each video's written length; one written past the top of the range cut
 *              between sections                                                          (no model)
 *
 * Each call is recorded whole (llm.ts) with what code found when it read the reply (its checks).
 */

import { bookMinutes, cleanSection, linesOf, bookSections, type Section, type WrittenSection } from "./source/book";
import { dropRepeats } from "./source/repeats";
import { LEARNING_MAP_TOOL, readLearningMap, sourceItems, goalLine, type LearningMap } from "./plan/learningmap";
import { STORY_PLAN_TOOL, readStoryPlan, type StoryPlan } from "./plan/storyplan";
import { OPEN_CLOSE_MINUTES, microMinutes, planTopics } from "./plan/videos";
import { PATCH_TOOL, SECTION_TOOL, learningMapPrompt, patchPrompt, sectionPrompt, sectionSystem, storyPlanPrompt } from "./prompts/build";
import { callTool } from "./llm";
import { documentInfo, documentMarkdown, newId, saveRun } from "./store";
import type { Call, Check, Options, Run, SectionState, Step, StepKey } from "./types";
import type { Prompt } from "./prompts/parts";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "read", label: "Read the book" },
  { key: "map", label: "Learning map" },
  { key: "plan", label: "Story plans" },
  { key: "write", label: "Write sections" },
  { key: "videos", label: "Videos" },
];

export async function startRun(documentId: string, asked: Partial<Options>): Promise<Run> {
  const info = await documentInfo(documentId);
  const markdown = await documentMarkdown(documentId);
  const options: Options = {
    minutes: asked.minutes && asked.minutes > 0 ? asked.minutes : bookMinutes(markdown),
    language: asked.language ?? "auto",
    subject: asked.subject ?? "",
    plannerModel: asked.plannerModel || process.env.V2_PLANNER_MODEL || "anthropic/claude-sonnet-4.5",
    writerModel: asked.writerModel || process.env.V2_WRITER_MODEL || "anthropic/claude-sonnet-4.5",
    effort: asked.effort ?? "medium",
    parallel: Math.max(1, Math.min(16, asked.parallel ?? 10)),
  };
  const run: Run = {
    id: newId(), documentId, documentName: info.name, created: Date.now(), status: "running", options,
    steps: STEPS.map((s): Step => ({ ...s, status: "waiting" })), sections: [], plans: [], videos: [], goalStatus: {},
    calls: [], log: [],
  };
  saveRun(run, true);
  void flow(run, markdown).catch((error) => {
    run.status = "failed";
    run.error = (error as Error).message;
    run.ended = Date.now();
    for (const s of run.steps) if (s.status === "running") s.status = "failed";
    log(run, `Failed: ${run.error}`);
    saveRun(run, true);
  });
  return run;
}

function log(run: Run, text: string) {
  run.log.push({ t: Date.now(), text });
  saveRun(run);
}

function step(run: Run, key: StepKey, status: Step["status"], summary?: string) {
  const s = run.steps.find((x) => x.key === key)!;
  if (status === "running") s.started = Date.now();
  if (status === "done" || status === "failed") s.ended = Date.now();
  s.status = status;
  if (summary !== undefined) s.summary = summary;
  saveRun(run);
}

function newCall(run: Run, o: { step: string; label: string; section?: number; model: string; prompt: Prompt }): Call {
  const call: Call = { id: `c${run.calls.length + 1}`, step: o.step, label: o.label, section: o.section, model: o.model,
    effort: run.options.effort, status: "running", started: Date.now(), attempts: [], prompt: o.prompt, cost: 0,
    provider: "openrouter", checks: [] };
  run.calls.push(call);
  if (o.section) run.sections.find((s) => s.n === o.section)?.calls.push(call.id);
  saveRun(run);
  return call;
}

const check = (call: Call, name: string, result: Check["result"], detail: string) => call.checks.push({ name, result, detail });

async function flow(run: Run, markdown: string) {
  const o = run.options;
  const subject = o.subject || undefined;

  // 1. Read ─────────────────────────────────────────────────────────────────────────────────────────────────────
  step(run, "read", "running");
  let sections = bookSections(markdown, o.minutes);
  const items = sourceItems(sections);
  run.sections = sections.map((s): SectionState => ({ n: s.n, minutes: s.minutes, words: s.words, source: s.source,
    questions: s.questions ?? [], questionsOnly: s.questionsOnly, status: "waiting", calls: [] }));
  const questions = sections.flatMap((s) => s.questions ?? []);
  step(run, "read", "done", `${sections.length} sections (about ${o.minutes} min), ${items.length} items ` +
    `(${["heading", "term", "aside", "figure"].map((k) => `${items.filter((i) => i.kind === k).length} ${k}s`).join(", ")}), ` +
    `${questions.length} book questions`);
  if (!items.length) {
    log(run, "The book's text has no headings, bold terms or boxes (read without DATALAB_API_KEY?): the learning map has " +
      "nothing to place, so the sections are written from their text alone.");
  }

  // 2. Learning map ─────────────────────────────────────────────────────────────────────────────────────────────
  step(run, "map", "running");
  const mapCall = newCall(run, { step: "map", label: "Learning map", model: o.plannerModel,
    prompt: learningMapPrompt(sections, items, subject) });
  const raw = await callTool({ call: mapCall, tool: LEARNING_MAP_TOOL, onChange: () => saveRun(run),
    fake: () => fakeMap(sections, items) });
  if (!raw) throw new Error(`The learning map could not be made: ${mapCall.error ?? "no reply"}`);
  const map = readLearningMap(raw, items, sections);
  run.map = map;
  checkMap(mapCall, raw, map);
  for (const g of map.goals) run.goalStatus[g.id] = "waiting";
  step(run, "map", "done", `${map.goals.length} goals${map.added ? ` (${map.added} added by code for items the map left out)` : ""}`);

  // 3. Videos and story plans ───────────────────────────────────────────────────────────────────────────────────
  step(run, "plan", "running");
  const groups = planTopics(sections);
  const videos = groups.map((t) => ({ index: t.index, of: groups.length,
    sections: t.sections.map((n) => sections.find((s) => s.n === n)!).filter(Boolean) }));
  run.videos = groups.map((t) => ({ index: t.index, sections: t.sections, minutes: t.minutes, title: t.title }));
  for (const v of videos) for (const s of v.sections) run.sections.find((x) => x.n === s.n)!.video = v.index;
  saveRun(run);
  const plans = await Promise.all(videos.map(async (video) => {
    const qs = video.sections.flatMap((s) => s.questions ?? []);
    const call = newCall(run, { step: "plan", label: `Story plan, video ${video.index} of ${video.of}`, model: o.plannerModel,
      prompt: storyPlanPrompt(video, map, qs, subject) });
    const reply = await callTool({ call, tool: STORY_PLAN_TOOL, onChange: () => saveRun(run), fake: () => fakePlan(video, qs) });
    const plan = reply ? readStoryPlan(reply, video, qs) : null;
    checkPlan(call, reply, plan, video, qs);
    return plan;
  }));
  run.plans = plans.filter((p): p is StoryPlan => !!p);
  // The book's questions go to the sections the plans ask them in; a section of only questions left with none goes.
  const byId = new Map(questions.map((q) => [q.id, q]));
  for (const plan of run.plans) {
    for (const own of plan.sections) {
      const qs = own.questions.map((id) => byId.get(id)).filter((q): q is NonNullable<typeof q> => !!q);
      sections = sections.map((s) => (s.n === own.section ? { ...s, questions: qs } : s));
      const state = run.sections.find((s) => s.n === own.section);
      if (state) state.questions = qs;
    }
  }
  const empty = sections.filter((s) => s.questionsOnly && !(s.questions ?? []).length).map((s) => s.n);
  if (empty.length) {
    sections = sections.filter((s) => !empty.includes(s.n));
    run.sections = run.sections.filter((s) => !empty.includes(s.n));
    run.videos = run.videos.map((v) => ({ ...v, sections: v.sections.filter((n) => !empty.includes(n)) }));
    log(run, `Sections ${empty.join(", ")} held only book questions the plan asks elsewhere: not written.`);
  }
  step(run, "plan", run.plans.length ? "done" : "failed",
    `${run.videos.length} video${run.videos.length > 1 ? "s" : ""}, ${run.plans.length} planned` +
    (run.plans.length < videos.length ? ` (${videos.length - run.plans.length} without a plan: written from their goals)` : ""));

  // 4. Write ────────────────────────────────────────────────────────────────────────────────────────────────────
  step(run, "write", "running");
  const system = sectionSystem(sections, o.language, subject);
  const done = new Map<number, WrittenSection>();
  let next = 0;
  const worker = async () => {
    while (next < sections.length) {
      const section = sections[next++];
      await writeSection(run, section, sections, system, done, map);
      step(run, "write", "running", `${done.size} of ${sections.length} written`);
    }
  };
  await Promise.all(Array.from({ length: Math.min(o.parallel, sections.length) }, worker));
  const failed = run.sections.filter((s) => s.status === "failed").length;
  const statuses = Object.values(run.goalStatus);
  const count = (s: string) => statuses.filter((x) => x === s).length;
  step(run, "write", failed === sections.length ? "failed" : "done",
    `${done.size} of ${sections.length} written; goals: ${count("taught")} taught, ${count("patched")} written in after, ` +
    `${count("missing")} missing`);

  // 5. Videos ───────────────────────────────────────────────────────────────────────────────────────────────────
  step(run, "videos", "running");
  const spoken = (n: number) => (done.get(n)?.text ?? "").split(/\s+/).filter(Boolean).length / 100;
  const max = microMinutes().max;
  const out: Run["videos"] = [];
  for (const v of run.videos) {
    const length = (ns: number[]) => ns.reduce((m, n) => m + spoken(n), 0) + (run.videos.length > 1 ? OPEN_CLOSE_MINUTES : 0);
    const parts = [v.sections];
    for (let long = parts.findIndex((p) => p.length > 1 && length(p) > max); long >= 0;
      long = parts.findIndex((p) => p.length > 1 && length(p) > max)) {
      const p = parts[long];
      let best = 1;
      for (let k = 2; k < p.length; k++) {
        if (Math.max(length(p.slice(0, k)), length(p.slice(k))) < Math.max(length(p.slice(0, best)), length(p.slice(best)))) best = k;
      }
      parts.splice(long, 1, p.slice(0, best), p.slice(best));
    }
    if (parts.length > 1) log(run, `Video ${v.index} was written to about ${Math.round(length(v.sections))} min: made as ${parts.length} videos.`);
    for (const p of parts) out.push({ index: out.length + 1, sections: p, minutes: v.minutes, title: v.title,
      written: Math.round(length(p) * 10) / 10 });
  }
  run.videos = out;
  step(run, "videos", "done", out.map((v) => `video ${v.index}: ${v.written} min`).join(", "));
  run.status = "done";
  run.ended = Date.now();
  saveRun(run, true);
}

async function writeSection(run: Run, section: Section, sections: Section[], system: Prompt["system"],
  done: Map<number, WrittenSection>, map: LearningMap) {
  const state = run.sections.find((s) => s.n === section.n)!;
  state.status = "writing";
  const plan = run.plans.find((p) => p.sections.some((s) => s.section === section.n));
  const own = map.goals.filter((g) => g.section === section.n);
  let note: string | undefined;
  for (let attempt = 1; attempt <= 2; attempt++) {
    const written = [...done.values()].filter((w) => w.n < section.n).sort((a, b) => a.n - b.n);
    const call = newCall(run, { step: "section", label: `Section ${section.n}${attempt > 1 ? `, try ${attempt}` : ""}`,
      section: section.n, model: run.options.writerModel,
      prompt: sectionPrompt({ section, all: sections, written, system, plan, map, note }) });
    const reply = await callTool({ call, tool: SECTION_TOOL, onChange: () => saveRun(run),
      fake: () => fakeSection(section, own.map((g) => g.id)) });
    const rawText = String(reply?.text ?? call.text ?? "").trim();
    if (!rawText) {
      check(call, "Has text", "fail", "The reply had no text: asked again.");
      note = "your reply had no text.";
      continue;
    }
    check(call, "Has text", "pass", `${rawText.split(/\s+/).length} words (asked for at most about ${section.words})`);
    if (rawText.split(/\s+/).length > section.words * 1.3) {
      check(call, "Length", "info", `Written past the ceiling: ${rawText.split(/\s+/).length} words for about ${section.words}.`);
    }
    // Not spoken: headings, bullets, [stage directions] -- taken out, not refused.
    let text = cleanSection(rawText);
    const removed = linesOf(rawText).length - linesOf(text).length;
    check(call, "Only spoken words", removed > 0 ? "fixed" : "pass",
      removed > 0 ? `${removed} heading or bracket line(s) taken out` : "no headings, bullets or stage directions");
    // A sentence another section (written so far) already said is taken out.
    const before = [...done.values()].filter((w) => w.n !== section.n).flatMap((w) => linesOf(w.text));
    const cleaned = dropRepeats(text, before);
    text = cleaned.text;
    state.dropped = cleaned.dropped;
    check(call, "No repeats", cleaned.dropped.length ? "fixed" : "pass", cleaned.dropped.length
      ? `${cleaned.dropped.length} sentence(s) said before taken out: ${cleaned.dropped.slice(0, 2).map((d) => `"${d.slice(0, 70)}"`).join("; ")}`
      : "no sentence said before");
    // Goals: kept when the section's own and naming sentences it has; their sentences found again in the final text.
    const rawLines = linesOf(rawText);
    const reported = Array.isArray(reply?.goals_taught) ? (reply!.goals_taught as { goal?: unknown; lines?: unknown }[]) : [];
    const goalLines: Record<string, number[]> = {};
    const finalLines = () => linesOf(text);
    for (const r of reported) {
      const id = String(r?.goal ?? "").trim();
      if (!own.some((g) => g.id === id)) {
        check(call, `Goal ${id || "?"}`, "info", "reported, but not this section's goal: ignored");
        continue;
      }
      const nums = (Array.isArray(r.lines) ? r.lines : []).map(Number).filter((n) => n >= 1 && n <= rawLines.length);
      const said = nums.map((n) => rawLines[n - 1]);
      const at = said.map((s) => finalLines().indexOf(s) + 1).filter((n) => n > 0);
      if (!nums.length) continue;
      goalLines[id] = at;
    }
    for (const g of own) {
      if (goalLines[g.id]) {
        run.goalStatus[g.id] = "taught";
        check(call, `Goal ${g.id}`, "pass", `taught in sentence${goalLines[g.id].length > 1 ? "s" : ""} ${goalLines[g.id].join(", ") || "(removed as a repeat)"}: ${g.goal}`);
      } else {
        check(call, `Goal ${g.id}`, "fail", `not reported: a patch is asked for. ${g.goal}`);
      }
    }
    state.patched = [];
    for (const g of own.filter((x) => !goalLines[x.id])) {
      const lines = linesOf(text);
      const pcall = newCall(run, { step: "patch", label: `Patch ${g.id}, section ${section.n}`, section: section.n,
        model: run.options.writerModel, prompt: patchPrompt(text, goalLine(g, map.items), section.source) });
      const patch = await callTool({ call: pcall, tool: PATCH_TOOL, onChange: () => saveRun(run),
        fake: () => ({ after_line: Math.min(2, lines.length), text: `Let us also see this: ${g.goal}.` }) });
      const words = cleanSection(String(patch?.text ?? ""));
      if (!words) {
        run.goalStatus[g.id] = "missing";
        check(pcall, "Has words", "fail", "no words: the goal stays missing");
        continue;
      }
      const after = Math.max(1, Math.min(lines.length, Number(patch?.after_line) || lines.length));
      const where = !patch?.after_line || Number(patch.after_line) > lines.length;
      text = insertAfter(text, lines[after - 1], words);
      const added = linesOf(words).length;
      // Earlier goals' sentence numbers after the insertion move down.
      for (const id of Object.keys(goalLines)) goalLines[id] = goalLines[id].map((n) => (n > after ? n + added : n));
      for (const p of state.patched) p.lines = p.lines.map((n) => (n > after ? n + added : n));
      const nums = Array.from({ length: added }, (_, k) => after + 1 + k);
      state.patched.push({ goal: g.id, lines: nums });
      goalLines[g.id] = nums;
      run.goalStatus[g.id] = "patched";
      check(pcall, "Placed", where ? "fixed" : "pass", where ? `asked line ${patch?.after_line} is past the end: put after sentence ${after}`
        : `${added} sentence(s) after sentence ${after}`);
    }
    state.text = text;
    state.title = String(reply?.title ?? "") || `Section ${section.n}`;
    state.goalLines = goalLines;
    state.status = "written";
    done.set(section.n, { n: section.n, title: state.title, text });
    saveRun(run);
    return;
  }
  state.status = "failed";
  for (const g of own) run.goalStatus[g.id] = "missing";
  saveRun(run);
}

function insertAfter(text: string, line: string | undefined, words: string): string {
  const at = line ? text.indexOf(line) : -1;
  if (at < 0) return `${text}\n\n${words}`;
  const end = at + line!.length;
  return `${text.slice(0, end)} ${words}${text.slice(end)}`;
}

// ─── Checks on the planners' replies ─────────────────────────────────────────────────────────────────────────────

function checkMap(call: Call, raw: Record<string, unknown>, map: LearningMap) {
  const known = new Set(map.items.map((i) => i.id));
  const listed = (Array.isArray(raw.goals) ? raw.goals : []).flatMap((g: { items?: unknown }) =>
    Array.isArray(g?.items) ? g.items.map(String) : []);
  const unknown = listed.filter((id) => !known.has(id));
  const twice = listed.filter((id, k) => known.has(id) && listed.indexOf(id) !== k);
  check(call, "Goals", "pass", `${(raw.goals as unknown[] | undefined)?.length ?? 0} goals in the reply`);
  check(call, "Item ids", unknown.length ? "fixed" : "pass", unknown.length ? `${unknown.length} unknown id(s) dropped: ${unknown.slice(0, 8).join(", ")}` : "every id is a book item");
  if (twice.length) check(call, "Items placed once", "fixed", `${twice.length} item(s) under two goals: kept under the first (${twice.slice(0, 8).join(", ")})`);
  const continued = map.goals.filter((g) => g.goal.endsWith("(continued)")).length;
  if (continued) check(call, "One section a goal", "fixed", `${continued} goal(s) spanning two sections split, one per section`);
  check(call, "Every item placed", map.added ? "fixed" : "pass", map.added
    ? `${map.added} goal(s) added by code for items the map left out` : `all ${map.items.length} items under a goal`);
}

function checkPlan(call: Call, raw: Record<string, unknown> | null, plan: StoryPlan | null,
  video: { sections: Section[] }, qs: { id: string }[]) {
  if (!plan) {
    check(call, "Big question", "fail", raw ? "the reply had no big question: no plan for this video" : "no reply");
    return;
  }
  check(call, "Big question", "pass", plan.bigQuestion);
  const rows = Array.isArray(raw?.sections) ? (raw!.sections as { section?: unknown; questions?: unknown }[]) : [];
  const missing = video.sections.filter((s) => !rows.some((r) => Number(r?.section) === s.n)).map((s) => s.n);
  check(call, "Every section planned", missing.length ? "fail" : "pass", missing.length
    ? `no plan for section(s) ${missing.join(", ")}: written from their goals` : `${video.sections.length} sections`);
  const placed = rows.flatMap((r) => (Array.isArray(r?.questions) ? r.questions.map(String) : []));
  const moved = qs.filter((q) => !placed.includes(q.id)).length;
  if (qs.length) check(call, "Book questions placed once", moved ? "fixed" : "pass", moved
    ? `${moved} question(s) the plan left out stay where the book prints them` : `all ${qs.length} placed`);
}

// ─── Offline stand-ins (no key): enough to drive the flow and the page ───────────────────────────────────────────

function fakeMap(sections: Section[], items: ReturnType<typeof sourceItems>) {
  const goals: { goal: string; items: string[]; misconception: string; hook: string; difficulty: number }[] = [];
  for (const s of sections) {
    let current: (typeof goals)[number] | null = null;
    for (const item of items.filter((i) => i.section === s.n)) {
      if (item.kind === "heading" || !current) {
        current = { goal: `Explain ${item.text.replace(/^[\d.\s]+/, "").slice(0, 60)}`, items: [], misconception: "",
          hook: "something from daily life", difficulty: 2 };
        goals.push(current);
      }
      current.items.push(item.id);
    }
  }
  return { goals };
}

function fakePlan(video: { index: number; sections: Section[] }, qs: { id: string }[]) {
  const heading = /^#{1,6}\s+(.+)$/m.exec(video.sections[0]?.source ?? "")?.[1]?.replace(/[*_`]/g, "") ?? "this topic";
  return {
    big_question: `What is ${heading} really about?`, running_example: "a student in a small town", arc: "hook, build-up, twist, answer",
    opening: "A scene, then the big question.", closing: "The answer, two quick checks, what comes next.",
    sections: video.sections.map((s, k) => ({ section: s.n, opens_from: k ? `the end of section ${video.sections[k - 1].n}` : "the opening",
      hands_on: `a question for section ${s.n + 1}`, guess_first: "What do you think happens next?",
      questions: (s.questions ?? []).map((q) => q.id).filter((id) => qs.some((q) => q.id === id)) })),
  };
}

function fakeSection(section: Section, goals: string[]) {
  const sentences = section.source.replace(/\[FIGURE[^\]]*\]/g, "").replace(/[#*_>`]/g, "").split(/(?<=[.?!])\s+/)
    .map((s) => s.replace(/\s+/g, " ").trim()).filter((s) => s.split(" ").length > 4).slice(0, 18);
  const text = ["Imagine you are sitting in class and this page is open in front of you.", ...sentences].join(" ")
    .replace(/(([^.?!]+[.?!]\s+){4})/g, "$1\n\n");
  const lines = linesOf(text).length;
  // A section with three goals or more leaves its last one out, so the patch step is seen working.
  const reported = goals.length >= 3 ? goals.slice(0, -1) : goals;
  return { section: section.n, title: `Section ${section.n}`, text,
    goals_taught: reported.map((g, k) => ({ goal: g, lines: [Math.min(lines, 2 + k)] })) };
}
