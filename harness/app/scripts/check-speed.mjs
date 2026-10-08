// The speed-ups in the generate pipeline (lib/figures.ts, lib/pocketanim.ts), without a model:
//  - the script writer waits for the book's figures only so long, then goes on with the ones that are ready;
//  - a lecture spoken ahead in the background hands over to the build's own pass without speaking a line twice
//    at once.
//   npm run check:speed
import assert from "node:assert/strict";
import path from "node:path";
import { tmpdir } from "node:os";

process.env.PANIM_FIGURE_WAIT_SECONDS = "0.3";
const { figuresWithin } = await import("../lib/figures.ts");

// All drawn in time: the whole set.
const quick = Promise.resolve({ fig1: { svg: "/a.svg" }, fig2: { manim: true } });
assert.deepEqual(await figuresWithin(quick, {}, Date.now(), () => {}), { fig1: { svg: "/a.svg" }, fig2: { manim: true } });

// One still drawing at the deadline: only the settled ones, and a status that says so.
const ready = { fig1: { svg: "/a.svg" } };
const said = [];
let finish;
const slow = new Promise((resolve) => (finish = resolve));
const t0 = Date.now();
const got = await figuresWithin(slow, ready, t0, (text) => said.push(text));
assert.ok(Date.now() - t0 < 1500, "it did not wait for the slow figure");
assert.deepEqual(got, { fig1: { svg: "/a.svg" } });
ready.fig2 = { svg: "/b.svg" };                     // drawn later: not in what this run already took
assert.equal(got.fig2, undefined);
assert.match(said[0], /1 of the book's figures were ready/);
finish({});

// Nothing ready by the deadline: none (every figure is built in Manim this run).
assert.equal(await figuresWithin(new Promise(() => {}), {}, Date.now() - 1000, () => {}), undefined);

// Speaking ahead, then the build: the build waits for the pass under way and takes over what was queued.
process.env.PANIM_AUDIO_DIR = path.join(tmpdir(), "panim-speak-check");
const { speakAhead, prespeak } = await import("../lib/pocketanim.ts");
const scene = "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n        pass\n";
speakAhead(scene);
speakAhead(scene);                                  // queued behind the first: replaced, not added
const built = await prespeak(scene, null);
// Without a voice key here the build says so (built.error); either way the pass ahead has finished and nothing waits.
assert.ok(built.error === null || /voice|key|narration/i.test(built.error), String(built.error));
assert.equal(globalThis.__panimSpeakAhead.running, null);
assert.equal(globalThis.__panimSpeakAhead.next, null);
console.log("ok: figures waited for within the limit; speaking ahead hands over to the build");
