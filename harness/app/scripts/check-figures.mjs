// The book's figures (lib/figures.ts) with the offline image model: every figure -- a diagram, a graph, a
// photograph -- is redrawn by the diagram model (never shown as the book's), an SVG an older version drew is removed,
// the figures table holds only the redraws, and a second run asks nothing.
//   node --experimental-strip-types scripts/check-figures.mjs
import { mkdtempSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import assert from "node:assert/strict";

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
const options = { markdown: "Cells. [FIGURE figC: Parts of a plant cell] Walls.", repo,
  python: path.join(repo, ".venv", "bin", "python"), onStatus: (t) => { statuses.push(t); console.log("  ", t); } };
const drawn = await drawFigures(figures, options);
for (const f of figures) {
  const d = drawn[f.id];
  assert.ok(d.generated && /gen-diagram-.*\.png$/.test(d.generated.file) && existsSync(d.generated.file), `${f.id} redrawn`);
  assert.ok(d.photo && d.diagram && d.checked, f.id);
  assert.notEqual(d.generated.file, f.file);                               // never the book's own picture
  assert.match(drawnLine(f, d), /"photo":true,"where":"stage"/);
}
assert.ok(!existsSync(path.join(dir, "figC.drawn.svg")), "the old SVG is gone");
const table = scriptFigures({ figures }, drawn);
assert.deepEqual(Object.keys(table).sort(), ["figC", "figG", "figP"]);
assert.ok(Object.values(table).every((t) => /gen-diagram-/.test(t.file)));
// A figure with no redraw is not in the table at all, and the writer rebuilds it.
assert.deepEqual(Object.keys(scriptFigures({ figures }, { figC: drawn.figC })), ["figC"]);
assert.match(drawnLine(figures[2], undefined), /not available as a picture: build it on the board/);
statuses = [];
const again = await drawFigures(figures, options);
assert.equal(statuses.length, 0);                                           // redrawn already: nothing asked
assert.equal(again.figC.generated.file, drawn.figC.generated.file);
console.log("ok: every figure redrawn by the diagram model; the book's own pictures never in the table");
