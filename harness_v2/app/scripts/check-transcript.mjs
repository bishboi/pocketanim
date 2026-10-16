// The transcription flow end to end with the offline stand-in (no key): a small book in, every step done, every
// item under a goal, every goal taught or written in, each call recorded with its prompt parts and checks.
//   npm run check
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

delete process.env.OPENROUTER_API_KEY;
const dir = mkdtempSync(path.join(tmpdir(), "v2-check-"));
process.chdir(dir);
const { startRun } = await import(path.resolve(import.meta.dirname, "../lib/run.ts"));
const { loadRun } = await import(path.resolve(import.meta.dirname, "../lib/store.ts"));
const { render } = await import(path.resolve(import.meta.dirname, "../lib/prompts/parts.ts"));

const book = [
  "# From Villages to Cities", "",
  "## The River Valleys", "", "The first farmers settled near the **Indus**. The floods left rich **silt** behind them every year. ".repeat(20), "",
  "[FIGURE fig1: The Indus valley]", "", "Do you know?", "The Nile flood came at the same time every year.", "",
  "## The First Cities", "", "Cities such as **Harappa** had drains and a **granary** for the grain of the whole town. ".repeat(22), "",
  "## Exercises", "", "1. Why did farmers settle near rivers?", "2. Which of these was found in Harappa?", "(a) Iron (b) Drains (c) Coins (d) Paper",
].join("\n");
const id = "check-0001";
mkdirSync(path.join(dir, ".data", "docs", id, "out"), { recursive: true });
writeFileSync(path.join(dir, ".data", "docs", id, "out", "document.md"), book);
writeFileSync(path.join(dir, ".data", "docs", id, "info.json"), JSON.stringify({ id, name: "check.pdf", pages: 2, words: 500, source: "test", created: 1 }));

const started = await startRun(id, { minutes: 10, parallel: 4 });
let run;
for (let i = 0; i < 200; i++) {
  run = await loadRun(started.id);
  if (run.status !== "running") break;
  await new Promise((r) => setTimeout(r, 200));
}
assert.equal(run.status, "done", run.error);
assert.ok(run.steps.every((s) => s.status === "done"), JSON.stringify(run.steps));
const placed = run.map.goals.flatMap((g) => g.items);
assert.equal(new Set(placed).size, run.map.items.length, "every item under one goal");
assert.ok(run.sections.every((s) => s.status === "written" && s.text), "every section written");
assert.ok(Object.values(run.goalStatus).every((s) => s === "taught" || s === "patched"), JSON.stringify(run.goalStatus));
assert.ok(Object.values(run.goalStatus).includes("patched"), "the patch step ran");
const kinds = new Set(run.calls.map((c) => c.step));
for (const k of ["map", "plan", "section", "patch"]) assert.ok(kinds.has(k), `a ${k} call`);
for (const c of run.calls) {
  assert.ok(c.prompt.system.length && c.prompt.user.length, `${c.label}: prompt parts`);
  assert.ok(render(c.prompt.user).length > 20, `${c.label}: user prompt`);
  assert.ok(c.checks.length || c.step === "plan", `${c.label}: checks`);
  assert.equal(c.provider, "fixture");
}
const section = run.calls.find((c) => c.step === "section");
for (const key of ["ask", "story", "yours", "goals", "questions", "length", "book"]) {
  assert.ok(section.prompt.user.some((p) => p.key === key), `section prompt has its ${key} part`);
}
console.log(`ok: ${run.sections.length} sections, ${run.map.goals.length} goals, ${run.calls.length} calls, ` +
  `${Object.values(run.goalStatus).filter((s) => s === "patched").length} patched`);
process.exit(0);
