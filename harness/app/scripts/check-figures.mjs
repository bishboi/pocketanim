// The figure drawer (lib/figures.ts) against a stand-in for OpenRouter: a broken SVG goes back with the board's
// reasons and comes back fixed; a photograph is left as one; a second run reuses the drawings.
//   node --experimental-strip-types scripts/check-figures.mjs
import http from "node:http";
import { mkdtempSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import assert from "node:assert/strict";

const GOOD = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400">
<g id="battery"><line x1="100" y1="150" x2="100" y2="250" stroke="INK" stroke-width="5"/>
<text x="70" y="210" font-size="24" fill="INK" text-anchor="end">V</text></g>
<g id="wire"><path d="M100 150 V60 H700 V340 H100 V250" fill="none" stroke="INK" stroke-width="4"/></g>
<g id="current"><path d="M100 150 V60 H700 V340 H100 V250" fill="none" stroke="GOLD" stroke-width="6" stroke-dasharray="10 30">
<animate attributeName="stroke-dashoffset" values="0; -40" dur="1s" repeatCount="indefinite"/></path>
<text x="400" y="45" font-size="24" fill="GOLD" text-anchor="middle">I</text></g>
</svg>`;
const BROKEN = GOOD.replace(' viewBox="0 0 800 400"', "");
const requests = [];
const server = http.createServer((req, res) => {
  let body = "";
  req.on("data", (d) => (body += d));
  req.on("end", () => {
    const ask = JSON.parse(body);
    requests.push(ask);
    const first = JSON.stringify(ask.messages[1].content);
    let text;
    const latest = ask.messages.at(-1).content;
    if (Array.isArray(latest) && latest.some((p) => p.type === "image_url") && ask.messages.length > 2) {
      // The review: it looked at its drawing on the board and renamed the battery's label.
      text = "The battery wants its name.\n```svg\n" + GOOD.replace(">V<", ">cell<") + "\n```";
    } else if (first.includes("figP")) text = "PHOTO";
    else if (ask.messages.length === 2) text = "```svg\n" + BROKEN + "\n```";
    else text = "Fixed.\n```svg\n" + GOOD + "\n```";
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ choices: [{ message: { content: text } }], usage: { cost: 0.001 } }));
  });
});
await new Promise((r) => server.listen(0, r));
process.env.OPENROUTER_URL = `http://127.0.0.1:${server.address().port}/v1/chat/completions`;
const { drawFigures, drawnLine } = await import("../lib/figures.ts");

const dir = mkdtempSync(path.join(tmpdir(), "figs-"));
// A 1x1 PNG for each figure.
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
for (const id of ["figC", "figP"]) writeFileSync(path.join(dir, `${id}.png`), png);
const figures = [
  { id: "figC", file: path.join(dir, "figC.png"), caption: "Current in a simple circuit" },
  { id: "figP", file: path.join(dir, "figP.png"), caption: "A photograph of a power station" },
];
const repo = path.resolve(process.cwd(), "..", "..");
const options = { key: "test", model: "test/model", markdown: "Current flows. [FIGURE figC: Current in a simple circuit] It goes round.",
  repo, python: path.join(repo, ".venv", "bin", "python"), onStatus: (t) => console.log("  ", t) };
const drawn = await drawFigures(figures, options);
assert.equal(drawn.figP.photo, true);
assert.ok(drawn.figC.svg && existsSync(drawn.figC.svg), "figC drawn");
assert.deepEqual(drawn.figC.parts, ["battery", "wire", "current"]);
assert.equal(drawn.figC.animated, true);
assert.equal(requests.length, 4);                       // figC: broken, fixed, reviewed; figP: one PHOTO
assert.match(JSON.stringify(requests.find((r) => r.messages.length > 2).messages.at(-1)), /viewBox/);   // the reason went back
assert.ok(requests.every((r) => r.messages[1].content.some((p) => p.type === "image_url")));   // it saw the figure
assert.match(readFileSync(drawn.figC.svg, "utf8"), />cell</);   // what it fixed on looking is what is kept
assert.equal(drawn.figC.labels.battery, "cell");
console.log("  ", drawnLine(figures[0], drawn.figC));
const again = await drawFigures(figures, options);
assert.equal(requests.length, 4);                       // drawn already: nothing asked
assert.equal(again.figC.svg, drawn.figC.svg);
server.close();
console.log("ok: figures drawn, repaired, cached");
