// The transcription flow end to end with no keys: a 4-page chapter PDF read by the offline reader into Datalab-shaped
// JSON, planned and written by the offline stand-in. Checks: blocks keep Datalab's ids and boxes; the planner sees no
// boxes; every block is placed in a lecture; every goal is taught or written in; lectures see the ones before them.
//   npm run check
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

delete process.env.OPENROUTER_API_KEY;
delete process.env.DATALAB_API_KEY;
const here = import.meta.dirname;
const pdf = readFileSync(path.join(here, "fixtures", "chapter.pdf"));
process.chdir(mkdtempSync(path.join(tmpdir(), "v2-check-")));
const { addDocument } = await import(path.resolve(here, "../lib/docs.ts"));
const { startRun } = await import(path.resolve(here, "../lib/run.ts"));
const { loadRun } = await import(path.resolve(here, "../lib/store.ts"));
const { render } = await import(path.resolve(here, "../lib/prompts/parts.ts"));

const doc = await addDocument("chapter.pdf", new Uint8Array(pdf));
assert.equal(doc.pages, 4);
assert.equal(doc.source, "offline");

// Two pictures put in the book as Datalab gives them (a Picture block, its image, a Caption), for the figure steps.
const dir = path.join(process.cwd(), ".data", "docs", doc.id);
const book = JSON.parse(readFileSync(path.join(dir, "book.json"), "utf8"));
const figures = JSON.parse(readFileSync(path.join(dir, "figures.json"), "utf8"));
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
[["Figure 1: A map of the rivers of India.", 0], ["Figure 2: A graph of speed against time.", 1]].forEach(([caption, p], k) => {
  const page = book.children[p];
  const [, , w, h] = page.bbox;
  const id = `/page/${p}/Picture/9${k}`;
  page.children.push({ id, block_type: "Picture", html: "", bbox: [w * 0.2, h * 0.7, w * 0.6, h * 0.85], children: null },
    { id: `/page/${p}/Caption/9${k}`, block_type: "Caption", html: `<p>${caption}</p>`, bbox: [w * 0.2, h * 0.86, w * 0.6, h * 0.88], children: null });
  writeFileSync(path.join(dir, "figures", `fig${k}.png`), png);
  figures[id] = path.join(dir, "figures", `fig${k}.png`);
});
writeFileSync(path.join(dir, "book.json"), JSON.stringify(book));
writeFileSync(path.join(dir, "figures.json"), JSON.stringify(figures));
const wait = async (id, busy) => {
  for (let i = 0; i < 400; i++) {
    const r = await loadRun(id);
    if (!busy(r)) return r;
    await new Promise((res) => setTimeout(res, 100));
  }
  throw new Error("timed out");
};
const started = await startRun(doc.id, { lectureMinutes: 4 });
let run;
for (let i = 0; i < 300; i++) {
  run = await loadRun(started.id);
  if (run.status !== "running") break;
  await new Promise((r) => setTimeout(r, 200));
}
assert.equal(run.status, "done", run.error);
assert.ok(run.steps.every((s) => s.status === "done"), JSON.stringify(run.steps));

// Datalab's shape: ids by page and type, boxes within the page.
assert.ok(run.blocks.length > 10);
for (const b of run.blocks) {
  assert.match(b.id, /^\/page\/\d+\/[A-Za-z]+\/\d+$/);
  assert.ok(b.box.every((v) => v >= -0.01 && v <= 1.01), `${b.id} box ${b.box}`);
}
assert.ok(run.blocks.some((b) => b.type === "SectionHeader"), "headers found");

// The planner reads Datalab's ids, types and HTML, never the boxes; it answers with ids.
const plan = run.calls.find((c) => c.step === "plan");
const sent = render(plan.prompt.user);
assert.ok(sent.includes('"block_type":"SectionHeader"') && sent.includes("/page/0/"), "planner sees the blocks");
assert.ok(!/bbox|polygon|"box"/.test(sent), "planner sees no boxes");

// Every block in exactly one lecture (or skipped); every goal taught or written in; the patch ran.
const placed = run.lectures.flatMap((l) => l.blocks);
assert.equal(new Set(placed).size, placed.length, "no block in two lectures");
assert.equal(placed.length + run.skipped.length, run.blocks.length, "every block placed or skipped");
assert.ok(run.lectures.length >= 2, `lectures by topic (${run.lectures.length})`);
assert.ok(run.lectures.every((l) => l.status === "written" && l.text), JSON.stringify(run.lectures.map((l) => [l.n, l.status, run.calls.filter((c) => c.lecture === l.n).map((c) => c.error)])));
assert.ok(Object.values(run.goalStatus).every((s) => s === "taught" || s === "patched"), JSON.stringify(run.goalStatus));
assert.ok(run.calls.some((c) => c.step === "patch"), "a patch call");

// A later lecture is given the earlier ones whole; no length ceiling anywhere in a writer's prompt.
const second = run.calls.find((c) => c.step === "lecture" && c.lecture === 2);
const previous = second.prompt.user.find((p) => p.key === "previous").text;
assert.ok(previous.includes(run.lectures[0].text.slice(0, 80)), "lecture 2 sees lecture 1's transcript");
assert.ok(!/at most about|words \(\d+ min\)/.test(render(second.prompt.system) + render(second.prompt.user)), "no length ceiling");
// Figures: both described, then triaged from the ways allowed.
const { triageAction } = await import(path.resolve(here, "../lib/triage.ts"));
const { checkExport, exportTranscript, exportWhole, importTranscript, transcriptMarkdown } = await import(path.resolve(here, "../lib/export.ts"));
const { continueRun } = await import(path.resolve(here, "../lib/run.ts"));
const pics = run.blocks.filter((b) => b.image);
assert.equal(pics.length, 2, "two pictures");
assert.ok(pics.every((b) => b.description), "pictures described");
await triageAction(run.id, { action: "run", kinds: ["manim", "map", "styled"] });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.equal(run.triage.status, "done", run.triage.error);
const kindOf = (k) => run.triage.figures[pics[k].id].kind;
assert.equal(kindOf(0), "map");
assert.equal(kindOf(1), "manim");
// By default a decision model decides: one Choice question over the ways ticked, the picture in the state.
const tcall = run.calls.find((c) => c.step === "triage");
assert.equal(tcall.api, "decisions");
assert.equal(tcall.model, "typesafe/jev-1.14");
assert.deepEqual(Object.keys(tcall.tool.way.options), ["manim", "map", "styled"], "only the ways ticked are offered");
assert.equal(tcall.tool.way.type, "choice");
assert.ok(tcall.request.state.some((s) => s.type === "image_url"), "the picture is in the state");
assert.ok(!JSON.stringify(tcall.request).includes("iVBORw0KGgo"), "the run's file keeps no image bytes");
const f0 = run.triage.figures[pics[0].id];
assert.ok(f0.confidence > 0.8 && !f0.unsure && Object.keys(f0.probabilities).length === 3, JSON.stringify(f0));
// The chat engine for one figure: its instruction and reason, the run's engine unchanged.
await triageAction(run.id, { action: "one", block: pics[1].id, engine: "chat" });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.equal(run.triage.engine, "decision");
assert.equal(run.triage.figures[pics[1].id].engine, "chat");
assert.ok(run.triage.figures[pics[1].id].how, "the chat model gives an instruction");
assert.ok(run.calls.at(-1).tool.function.parameters.properties.kind.enum.includes("map"));
// A high threshold makes the decisions unsure; the unsure ones go to the chat model.
await triageAction(run.id, { action: "reset", threshold: 0.95 });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.ok(Object.values(run.triage.figures).every((f) => f.unsure), "under the threshold: unsure");
await triageAction(run.id, { action: "unsure" });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.ok(Object.values(run.triage.figures).every((f) => f.engine === "chat" && !f.unsure && f.how), "the unsure ones answered by the chat model");
await triageAction(run.id, { action: "reset", kinds: ["manim", "map", "styled"], threshold: 0.6 });
run = await wait(run.id, (r) => r.triage.status === "running");
await assert.rejects(triageAction(run.id, { action: "run" }), /every figure is triaged/);
// Map not allowed: reset reruns all, and the map falls back to a way that is.
await triageAction(run.id, { action: "reset", kinds: ["manim", "styled"] });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.equal(run.triage.rounds, 6);
assert.equal(kindOf(0), "manim");
await triageAction(run.id, { action: "override", block: pics[0].id, kind: "exact" });
assert.equal(run.triage.figures[pics[0].id].override, "exact");
await triageAction(run.id, { action: "one", block: pics[1].id });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.equal(run.triage.figures[pics[1].id].calls.length, 7, "a figure's calls are kept across reruns");

// Export: numbered sentences, goals with their sentences, figures with their triage; imported again as a run.
const x = exportTranscript(run);
assert.equal(x.format, "pocketanim.v2.transcript");
assert.equal(x.lectures.length, run.lectures.length);
assert.ok(x.lectures.every((l) => l.lines.length && l.lines[0].n === 1));
const fig = x.blocks.find((b) => b.id === pics[0].id).figure;
assert.equal(fig.triage.kind, "exact");
assert.equal(fig.triage.chosenBy, "user");
assert.ok(transcriptMarkdown(run).includes("### Transcript"));
const back = await importTranscript(JSON.parse(JSON.stringify(x)), "x.json");
assert.equal(back.status, "done");
assert.equal(back.documentId, run.documentId, "the same book: found here, not made again");
assert.deepEqual(back.lectures.map((l) => l.text), run.lectures.map((l) => l.text));
assert.equal(back.triage.figures[pics[0].id].override, "exact");
assert.deepEqual(exportTranscript(back).lectures, x.lectures, "export, import, export: the same lectures");

// Continue: a lecture lost is written again, and only it.
const calls = run.calls.length;
const lost = run.lectures[1];
Object.assign(lost, { status: "waiting", text: undefined });
run.status = "failed";
run.steps.find((s) => s.key === "write").status = "failed";
await continueRun(run.id);
run = await wait(run.id, (r) => r.status === "running");
assert.equal(run.status, "done", run.error);
assert.equal(lost.status, "written");
const added = run.calls.slice(calls);
assert.ok(added.length >= 1 && added.every((c) => c.lecture === lost.n), `only lecture ${lost.n} written again: ${added.map((c) => c.label)}`);

// The whole file on another machine: the book is not there; the file carries it, and the next steps go on from it.
const whole = JSON.parse(JSON.stringify(await exportWhole(run)));
assert.equal(whole.version, 2);
assert.ok(whole.book.pdf && whole.book.datalab && Object.keys(whole.book.figures).length === 2, "the book is in the file");
const { rmSync } = await import("node:fs");
rmSync(path.join(process.cwd(), ".data"), { recursive: true, force: true });
assert.match(checkExport({ format: "x" }), /not an exported/);
assert.match(checkExport({ ...whole, version: 99 }), /newer/);
const there = await importTranscript(whole, "whole.json");
assert.notEqual(there.documentId, run.documentId, "the book made again");
assert.ok(there.log[0].text.includes("made again from the file"), there.log[0].text);
assert.deepEqual(exportTranscript(there).lectures, x.lectures);
await triageAction(there.id, { action: "one", block: pics[1].id, kinds: ["manim", "map"] });
const t2 = await wait(there.id, (r) => r.triage.status === "running");
assert.equal(t2.triage.figures[pics[1].id].kind, "manim", t2.triage.error);
Object.assign(t2.lectures[2], { status: "waiting", text: undefined });
t2.status = "stopped";
await continueRun(there.id);
const t3 = await wait(there.id, (r) => r.status === "running");
assert.equal(t3.status, "done", t3.error);
assert.equal(t3.lectures[2].status, "written");
assert.ok(t3.calls.find((c) => c.lecture === 3).prompt.user.find((p) => p.key === "previous").text.includes(run.lectures[0].text.slice(0, 60)),
  "a lecture written after import sees the imported ones");

console.log(`ok: ${run.blocks.length} blocks, ${run.lectures.length} lectures, ${Object.keys(run.goalStatus).length} goals, ${run.calls.length} calls, ${pics.length} figures triaged`);
process.exit(0);
