// The transcription flow end to end with no keys: a 4-page chapter PDF read by the offline reader into Datalab-shaped
// JSON, planned and written by the offline stand-in. Checks: blocks keep Datalab's ids and boxes; the planner sees no
// boxes; every block is placed in a lecture; every goal is taught or written in; lectures see the ones before them.
//   npm run check
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
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
console.log(`ok: ${run.blocks.length} blocks, ${run.lectures.length} lectures, ${Object.keys(run.goalStatus).length} goals, ${run.calls.length} calls`);
process.exit(0);
