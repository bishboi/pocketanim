// The cost tracker (lib/costs.ts) and its breakdown on the page (components/cost-breakdown.tsx), without a model:
// bills land on their tasks and add up; the breakdown shows each task, the SVGs and lines counted, the voice of
// every part of a series, the build as free, and a total that is the sum of its rows.
//   npm run check:costs
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const { CostLedger, usd, duration, mergeSpans } = await import("../lib/costs.ts");

const ledger = new CostLedger();
const t0 = 1_700_000_000_000;
// Two transcript sections written at once (0-40 s and 10-50 s) took 50 s of the clock, not 80.
ledger.bill("transcript", 0.12, { inputTokens: 1000, outputTokens: 4000, span: [t0, t0 + 40_000] });
ledger.bill("transcript", 0.08, { inputTokens: 800, outputTokens: 3000, span: [t0 + 10_000, t0 + 50_000] });
ledger.bill("script", 0.5, { inputTokens: 20000, outputTokens: 9000, span: [t0 + 50_000, t0 + 120_000] });
ledger.time("drawings", t0 + 60_000, t0 + 90_000);
assert.equal(ledger.lines.transcript.seconds, 50);
assert.equal(ledger.lines.script.seconds, 70);
assert.deepEqual(mergeSpans([[5, 9], [1, 3], [2, 4]]), [[1, 4], [5, 9]]);
assert.equal(duration(42), "42 s");
assert.equal(duration(185), "3 min 05 s");
assert.equal(duration(3900), "1 h 05 min");
ledger.bill("figures", 0.03);
ledger.bill("figures", 0.02);
ledger.count("figures", 1, "1 built in Manim");
ledger.count("figures", 1, "1 built in Manim, 1 photograph");
ledger.bill("drawings", 0.04);
ledger.count("drawings", 1);
ledger.bill("images", 0.039, { items: 1 });
assert.equal(Math.round(ledger.total * 1000) / 1000, 0.829);
assert.deepEqual([ledger.lines.transcript.calls, ledger.lines.transcript.outputTokens], [2, 7000]);
assert.deepEqual([ledger.lines.figures.items, ledger.lines.figures.calls, ledger.lines.figures.note], [2, 2, "1 built in Manim, 1 photograph"]);
const snap = ledger.snapshot();
ledger.bill("script", 1);
assert.equal(snap.script.usd, 0.5, "a snapshot does not change with the ledger");
assert.equal(usd(0), "$0");
assert.equal(usd(0.0042), "$0.0042");
assert.equal(usd(0.829), "$0.829");
assert.equal(usd(12.5), "$12.50");

// The breakdown, rendered as the page renders it (TypeScript's own transpiler for the TSX).
const out = mkdtempSync(path.join(tmpdir(), "costs-"));
mkdirSync(path.join(out, "lib"));
mkdirSync(path.join(out, "components"));
const compile = (from, to, rewrite = (s) => s) => writeFileSync(path.join(out, to), rewrite(ts.transpileModule(
  readFileSync(new URL(from, import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } },
).outputText));
compile("../lib/costs.ts", "lib/costs.mjs");
compile("../components/cost-breakdown.tsx", "components/cost-breakdown.mjs",
  (s) => s.replace('"@/lib/costs"', '"../lib/costs.mjs"').replace('"react/jsx-runtime"',
    `"${new URL("../node_modules/react/jsx-runtime.js", import.meta.url).href}"`));
const { CostBreakdown, versionTotal } = await import(path.join(out, "components", "cost-breakdown.mjs"));
const { createElement } = await import("react");
const { renderToStaticMarkup } = await import("react-dom/server");
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/\s+/g, " ");

const first = { costs: snap, costUsd: 0.829, part: { index: 1, of: 2, title: "A", minutes: 20 }, writeSeconds: 150,
  mp4Seconds: 60, saveSeconds: 20,
  voiceLecture: { usd: 0.3, lines: 200, unknown: 0, engine: "gemini" },
  build: { seconds: 95, voiceSeconds: 40, count: 1, aiImages: 0, aiUsd: 0 } };
const second = { part: { index: 2, of: 2, title: "B", minutes: 20 },
  voiceLecture: { usd: 0.25, lines: 180, unknown: 0, engine: "gemini" },
  build: { seconds: 80, voiceSeconds: 30, count: 1, aiImages: 1, aiUsd: 0.04 } };
const page = text(renderToStaticMarkup(createElement(CostBreakdown, { version: first, series: [first, second] })));
for (const shown of ["Transcribing the lecture", "2 requests", "Writing the video script", "Book figures drawn as SVG",
  "2 SVGs", "1 built in Manim, 1 photograph", "Pictures drawn as SVG", "1 SVG", "AI illustrations", "1 image",
  "Audio generation (narration)", "380 lines", "Gemini TTS", "AI illustrations (while building)",
  "Building the video", "rendering and baking the phone program", "free", "for all 2 parts",
  // Times: each task's, the writing start to finish, the steps after it, and the whole.
  "Transcribing the lecture", "50 s", "1 min 10 s", "Pictures drawn as SVG", "30 s",
  "Planning and checks", "Writing, start to finish (its tasks run side by side) 2 min 30 s",
  "Building the video", "2 min 55 s", "Rendering the MP4", "1 min 00 s", "Saving to the library", "20 s"]) {
  assert.ok(page.includes(shown), `the breakdown shows "${shown}": ${page}`);
}
// The total is the sum of the rows: writing 0.829 + voice 0.55 + illustrations while building 0.04.
assert.ok(page.includes("Total $1.42") || /Total [^$]*\$1\.42/.test(page), page);
// Writing 150 s, then voice 70 s, build 175 s, MP4 60 s and save 20 s, one after another: 475 s.
assert.ok(page.includes("Total 7 min 55 s $1.42"), page);
assert.ok(page.includes("time 7 min 55 s"), page);
// "Planning and checks" is the writing's time no task accounts for: 150 s less the 120 s the tasks were at work.
assert.match(page, /Planning and checks [^$]*? 30 s free/);
assert.equal(Math.round(versionTotal(first) * 1000) / 1000, 1.129);

// Before a build: the voice and the build are still to come, not $0 that looks final.
const unbuilt = text(renderToStaticMarkup(createElement(CostBreakdown, { version: { costs: snap } })));
assert.match(unbuilt, /Audio generation \(narration\) spoken when the video is built —/);
assert.match(unbuilt, /Building the video on this machine, when it is built —/);
console.log("ok: costs billed by task, broken down, and added up");
