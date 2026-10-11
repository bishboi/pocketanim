// The book's figures (lib/figures.ts) against a stand-in for OpenRouter and the offline image model: a photograph is
// made again by the illustration model, a graph goes back to Manim, a labelled diagram is redrawn by the diagram
// model (never drawn as an SVG, and an SVG an older version drew beside it is removed); a second run asks nothing.
//   node --experimental-strip-types scripts/check-figures.mjs
import http from "node:http";
import { mkdtempSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import assert from "node:assert/strict";

const requests = [];
const server = http.createServer((req, res) => {
  let body = "";
  req.on("data", (d) => (body += d));
  req.on("end", () => {
    const ask = JSON.parse(body);
    requests.push(ask);
    const first = JSON.stringify(ask.messages[1].content);
    const text = first.includes("figP") ? "PHOTO: a coal power station, wide view\nSUBJECT: -"
      : first.includes("figG") ? "MANIM" : "DIAGRAM";
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ choices: [{ message: { content: text } }], usage: { cost: 0.001 } }));
  });
});
await new Promise((r) => server.listen(0, r));
process.env.OPENROUTER_URL = `http://127.0.0.1:${server.address().port}/v1/chat/completions`;
const dir = mkdtempSync(path.join(tmpdir(), "figs-"));
// The image models offline: a stand-in picture for each (genimage.py), kept in a cache of this run's own.
process.env.PANIM_IMAGE_FAKE = "1";
process.env.PANIM_IMAGE_CACHE = path.join(dir, "images");
const { drawFigures, drawnLine } = await import("../lib/figures.ts");

// A 1x1 PNG for each figure.
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
for (const id of ["figC", "figP", "figG"]) writeFileSync(path.join(dir, `${id}.png`), png);
// An SVG an older version drew for figC: never shown again.
writeFileSync(path.join(dir, "figC.drawn.svg"), "<svg/>");
const figures = [
  { id: "figC", file: path.join(dir, "figC.png"), caption: "Parts of a plant cell" },
  { id: "figP", file: path.join(dir, "figP.png"), caption: "A photograph of a power station" },
  { id: "figG", file: path.join(dir, "figG.png"), caption: "Velocity against time" },
];
const repo = path.resolve(process.cwd(), "..", "..");
const options = { key: "test", model: "test/model", markdown: "Cells. [FIGURE figC: Parts of a plant cell] Walls.",
  repo, python: path.join(repo, ".venv", "bin", "python"), onStatus: (t) => console.log("  ", t) };
const drawn = await drawFigures(figures, options);
assert.equal(drawn.figP.photo, true);
assert.ok(drawn.figP.generated && existsSync(drawn.figP.generated.file), "figP made again");
assert.equal(drawn.figG.manim, true);                   // a graph: rebuilt in Manim
assert.match(drawnLine(figures[2], drawn.figG), /build it on the board in full detail/);
assert.equal(drawn.figC.diagram, true);                 // a diagram: redrawn by the diagram model
assert.ok(drawn.figC.generated && /\.png$/.test(drawn.figC.generated.file) && existsSync(drawn.figC.generated.file));
assert.match(drawnLine(figures[0], drawn.figC), /"photo":true,"where":"stage"/);
assert.ok(!existsSync(path.join(dir, "figC.drawn.svg")), "the old SVG is gone");
assert.ok(Object.values(drawn).every((d) => !("svg" in d)));
assert.equal(requests.length, 3);                       // each figure looked at once
assert.ok(requests.every((r) => r.messages[1].content.some((p) => p.type === "image_url")));   // it saw the figure
const again = await drawFigures(figures, options);
assert.equal(requests.length, 3);                       // decided already: nothing asked
assert.equal(again.figG.manim, true);
assert.equal(again.figC.generated.file, drawn.figC.generated.file);
server.close();
console.log("ok: figures made again, redrawn or built in Manim; none drawn as SVG");
