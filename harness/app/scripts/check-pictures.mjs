// A section is checked without its pictures (lib/lecture.ts withoutPictures), its pictures are made apart
// (makePictures, compile_lecture.py --pictures-only), and the lecture's compile then finds them made: the image
// models' minutes no longer hold a section's writing slot.
//   node --experimental-strip-types --import ./scripts/ts-resolve.mjs scripts/check-pictures.mjs
import assert from "node:assert/strict";
import { mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const cache = mkdtempSync(path.join(tmpdir(), "pics-"));
process.env.PANIM_IMAGE_FAKE = "1";
process.env.PANIM_IMAGE_CACHE = cache;
process.env.OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY || "test";
delete process.env.PANIM_IMAGES;
const { compileLecture, makePictures, picturesStatus } = await import("../lib/lecture.ts");

// The status line says what came back: never "made" for pictures that all failed.
const failedAll = picturesStatus({ pictures: 81, made: 0, failed: 81, error: "HTTP 403: not available in your region", seconds: 12, slowest: 3 }, 6);
assert.match(failedAll, /^Pictures: all 81 failed in 12 s .*region/);
assert.doesNotMatch(failedAll, /made/);
assert.match(picturesStatus({ pictures: 10, made: 7, failed: 3, error: "filtered", seconds: 40, slowest: 20 }, 6),
  /^Pictures: 7 of 10 made at once in 40 s .*; 3 failed \(filtered\)\.$/);
assert.equal(picturesStatus({ pictures: 5, made: 5, failed: 0, seconds: 30, slowest: 9 }, 6),
  "Pictures: 5 of 5 made at once in 30 s (the slowest 9 s; 6 at a time).");
assert.equal(picturesStatus({ pictures: 3, made: 3, seconds: 0.2 }, 6), null);   // all found made already

const script = { title: "T", style: "parchment", auto_visuals: false, place_figures: false, chapters: [
  { title: "A", map: false, section: 1, beats: [
    { say: "A ship sails for India.", do: [{ op: "picture", generate: "a Portuguese carrack" }] },
    { say: "Spices fill the market.", do: [{ op: "picture", generate: "a spice market" }] }] }] };
const made = () => readdirSync(cache).filter((f) => f.startsWith("gen-") && f.endsWith(".png")).length;

const checked = await compileLecture(script, { withoutPictures: true });
assert.ok(checked.source, checked.errors.join("; "));
assert.equal(made(), 0);                                         // the check asked the image models for nothing
const generated = [];
let imageSpans = 0;
let compileSpan = -1;
await makePictures(script, { onGenerated: (g) => generated.push(...g),
  onTime: (span, images) => { compileSpan = span[1] - span[0]; imageSpans = images.length; } });
assert.equal(made(), 2);
assert.equal(generated.length, 2);
assert.equal(compileSpan, 0);                                    // no compile time billed for a picture job
const full = await compileLecture(script, { onGenerated: (g) => assert.fail(`made again: ${g.length}`) });
assert.ok(full.source && (full.source.match(/gen-[0-9a-f]+\.png/g) ?? []).length >= 2);
console.log("ok: a section checked without its pictures; they are made apart, and the lecture's compile finds them made");
