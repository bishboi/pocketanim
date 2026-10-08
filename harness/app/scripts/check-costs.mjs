// The cost tracker (lib/costs.ts) and its breakdown on the page (components/cost-breakdown.tsx), without a model:
// bills land on their tasks and add up; the breakdown shows each task, the SVGs and lines counted, the voice of
// every part of a series, the build as free, and a total that is the sum of its rows.
//   npm run check:costs
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const { CostLedger, usd } = await import("../lib/costs.ts");

const ledger = new CostLedger();
ledger.bill("transcript", 0.12, { inputTokens: 1000, outputTokens: 4000 });
ledger.bill("transcript", 0.08, { inputTokens: 800, outputTokens: 3000 });
ledger.bill("script", 0.5, { inputTokens: 20000, outputTokens: 9000 });
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

const first = { costs: snap, costUsd: 0.829, part: { index: 1, of: 2, title: "A", minutes: 20 },
  voiceLecture: { usd: 0.3, lines: 200, unknown: 0, engine: "gemini" },
  build: { seconds: 95, voiceSeconds: 40, count: 1, aiImages: 0, aiUsd: 0 } };
const second = { part: { index: 2, of: 2, title: "B", minutes: 20 },
  voiceLecture: { usd: 0.25, lines: 180, unknown: 0, engine: "gemini" },
  build: { seconds: 80, voiceSeconds: 30, count: 1, aiImages: 1, aiUsd: 0.04 } };
const page = text(renderToStaticMarkup(createElement(CostBreakdown, { version: first, series: [first, second] })));
for (const shown of ["Transcribing the lecture", "2 requests", "Writing the video script", "Book figures drawn as SVG",
  "2 SVGs", "1 built in Manim, 1 photograph", "Pictures drawn as SVG", "1 SVG", "AI illustrations", "1 image",
  "Audio generation (narration)", "380 lines", "Gemini TTS", "AI illustrations (while building)",
  "Building the video", "on this machine, 2 min 55 s", "free", "for all 2 parts"]) {
  assert.ok(page.includes(shown), `the breakdown shows "${shown}": ${page}`);
}
// The total is the sum of the rows: writing 0.829 + voice 0.55 + illustrations while building 0.04.
assert.ok(page.includes("Total $1.42"), page);
assert.equal(Math.round(versionTotal(first) * 1000) / 1000, 1.129);

// Before a build: the voice and the build are still to come, not $0 that looks final.
const unbuilt = text(renderToStaticMarkup(createElement(CostBreakdown, { version: { costs: snap } })));
assert.match(unbuilt, /Audio generation \(narration\) spoken when the video is built —/);
assert.match(unbuilt, /Building the video on this machine, when it is built —/);
console.log("ok: costs billed by task, broken down, and added up");
