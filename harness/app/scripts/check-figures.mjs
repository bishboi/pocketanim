// The book's figures (lib/figures.ts) against a stand-in for the figure model and the offline image model: a graph
// is rebuilt in Manim, every other figure -- a diagram, a photograph -- is redrawn by the diagram model (never shown
// as the book's), an SVG an older version drew is removed, the figures table holds only the redraws, and a second
// run asks nothing.
//   node --experimental-strip-types scripts/check-figures.mjs
import http from "node:http";
import { mkdtempSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import assert from "node:assert/strict";

// The figure model: a graph is built in Manim, anything else redrawn.
const asked = [];
const server = http.createServer((req, res) => {
  let body = "";
  req.on("data", (d) => (body += d));
  req.on("end", () => {
    const text = JSON.stringify(JSON.parse(body).messages[1].content);
    asked.push(text);
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ choices: [{ message: { content: text.includes("figG") ? "MANIM" : "REDRAW" } }], usage: { cost: 0.001 } }));
  });
});
await new Promise((r) => server.listen(0, r));
process.env.OPENROUTER_URL = `http://127.0.0.1:${server.address().port}/v1/chat/completions`;
const dir = mkdtempSync(path.join(tmpdir(), "figs-"));
// The image models offline: a stand-in picture for each (genimage.py), kept in a cache of this run's own.
process.env.PANIM_IMAGE_FAKE = "1";
process.env.PANIM_IMAGE_CACHE = path.join(dir, "images");
const { drawFigures, drawnLine } = await import("../lib/figures.ts");
const { scriptFigures } = await import("../lib/document.ts");

// A small PNG for each figure (each different, so each is its own redraw).
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
for (const [k, id] of ["figC", "figP", "figG"].entries()) writeFileSync(path.join(dir, `${id}.png`), Buffer.concat([png, Buffer.from([k])]));
// An SVG an older version drew for figC: never shown again.
writeFileSync(path.join(dir, "figC.drawn.svg"), "<svg/>");
const figures = [
  { id: "figC", file: path.join(dir, "figC.png"), caption: "Parts of a plant cell" },
  { id: "figP", file: path.join(dir, "figP.png"), caption: "A photograph of a power station" },
  { id: "figG", file: path.join(dir, "figG.png"), caption: "Velocity against time" },
];
const repo = path.resolve(process.cwd(), "..", "..");
let statuses = [];
const options = { key: "test", model: "test/model", markdown: "Cells. [FIGURE figC: Parts of a plant cell] Walls.", repo,
  python: path.join(repo, ".venv", "bin", "python"), onStatus: (t) => { statuses.push(t); console.log("  ", t); } };
const drawn = await drawFigures(figures, options);
for (const f of figures.slice(0, 2)) {
  const d = drawn[f.id];
  assert.ok(d.generated && /gen-diagram-.*\.png$/.test(d.generated.file) && existsSync(d.generated.file), `${f.id} redrawn`);
  assert.ok(d.photo && d.diagram && d.checked, f.id);
  assert.notEqual(d.generated.file, f.file);                               // never the book's own picture
  assert.match(drawnLine(f, d), /"photo":true,"where":"stage"/);
}
// The graph: rebuilt in Manim, never redrawn and never shown as the book's.
assert.ok(drawn.figG.manim && !drawn.figG.generated);
assert.match(drawnLine(figures[2], drawn.figG), /BUILD IT IN MANIM/);
assert.equal(asked.length, 3);
assert.ok(asked.every((a) => a.includes("image_url")));                   // the figure model saw each figure
assert.ok(!existsSync(path.join(dir, "figC.drawn.svg")), "the old SVG is gone");
const table = scriptFigures({ figures }, drawn);
assert.deepEqual(Object.keys(table).sort(), ["figC", "figP"]);            // the Manim one is not a picture
assert.ok(Object.values(table).every((t) => /gen-diagram-/.test(t.file)));
// A figure with no redraw is not in the table at all, and the writer rebuilds it.
assert.deepEqual(Object.keys(scriptFigures({ figures }, { figC: drawn.figC })), ["figC"]);
assert.match(drawnLine(figures[2], undefined), /not available as a picture: build it on the board/);
statuses = [];
const again = await drawFigures(figures, options);
assert.equal(statuses.length, 0);                                           // redrawn already: nothing asked
assert.equal(again.figC.generated.file, drawn.figC.generated.file);
assert.ok(again.figG.manim && asked.length === 3);
server.close();
console.log("ok: graphs rebuilt in Manim, the rest redrawn by the diagram model; the book's own pictures never shown");
