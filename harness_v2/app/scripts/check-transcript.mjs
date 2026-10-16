// The transcription flow end to end with no keys: a 4-page chapter PDF read by the offline reader into Datalab-shaped
// JSON, planned and written by the offline stand-in. Checks: blocks keep Datalab's ids and boxes; the planner sees no
// boxes; every block is placed in a lecture; every goal is taught or written in; lectures see the ones before them.
//   npm run check
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

delete process.env.OPENROUTER_API_KEY;
delete process.env.DATALAB_API_KEY;
const here = import.meta.dirname;
// Manim renders with the repo's .venv (the check runs from a temporary folder).
process.env.V2_PYTHON ??= path.resolve(here, "../../../.venv/bin/python");
// Maps are drawn by v2's own engine (a copy of v1's).
process.env.V2_ENGINE ??= path.resolve(here, "../../engine");
const pdf = readFileSync(path.join(here, "fixtures", "chapter.pdf"));
process.chdir(mkdtempSync(path.join(tmpdir(), "v2-check-")));
const { addDocument } = await import(path.resolve(here, "../lib/docs.ts"));
const { startRun } = await import(path.resolve(here, "../lib/run.ts"));
const { loadRun, saveRun } = await import(path.resolve(here, "../lib/store.ts"));
const { render } = await import(path.resolve(here, "../lib/prompts/parts.ts"));

const doc = await addDocument("chapter.pdf", new Uint8Array(pdf));
assert.equal(doc.pages, 4);
assert.equal(doc.source, "offline");

// Two pictures put in the book as Datalab gives them (a Picture block, its image, a Caption), for the figure steps.
const dir = path.join(process.cwd(), ".data", "docs", doc.id);
const book = JSON.parse(readFileSync(path.join(dir, "book.json"), "utf8"));
const figures = JSON.parse(readFileSync(path.join(dir, "figures.json"), "utf8"));
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
[["Figure 1: A map of the rivers of India.", 0], ["Figure 2: A graph of speed against time.", 1]].forEach(([caption, p], k) => {
  const page = book.children[p];
  const [, , w, h] = page.bbox;
  const id = `/page/${p}/Picture/9${k}`;
  page.children.push({ id, block_type: "Picture", html: "", bbox: [w * 0.2, h * 0.7, w * 0.6, h * 0.85], children: null },
    { id: `/page/${p}/Caption/9${k}`, block_type: "Caption", html: `<p>${caption}</p>`, bbox: [w * 0.2, h * 0.86, w * 0.6, h * 0.88], children: null });
  writeFileSync(path.join(dir, "figures", `fig${k}.png`), png);
  figures[id] = path.join(dir, "figures", `fig${k}.png`);
});
writeFileSync(path.join(dir, "book.json"), JSON.stringify(book));
writeFileSync(path.join(dir, "figures.json"), JSON.stringify(figures));
const wait = async (id, busy) => {
  for (let i = 0; i < 400; i++) {
    const r = await loadRun(id);
    if (!busy(r)) return r;
    await new Promise((res) => setTimeout(res, 100));
  }
  throw new Error("timed out");
};
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
// Figures: both described, then triaged from the ways allowed.
const { triageAction } = await import(path.resolve(here, "../lib/triage.ts"));
const { linesOf: linesOfText } = await import(path.resolve(here, "../lib/source/book.ts"));
const { checkExport, exportTranscript, exportWhole, importTranscript, transcriptMarkdown } = await import(path.resolve(here, "../lib/export.ts"));
const { continueRun } = await import(path.resolve(here, "../lib/run.ts"));
const pics = run.blocks.filter((b) => b.image);
assert.equal(pics.length, 2, "two pictures");
assert.ok(pics.every((b) => b.description), "pictures described");
await triageAction(run.id, { action: "run", kinds: ["manim", "map", "styled"] });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.equal(run.triage.status, "done", run.triage.error);
const kindOf = (k) => run.triage.figures[pics[k].id].kind;
assert.equal(kindOf(0), "map");
assert.equal(kindOf(1), "manim");
// Pictures fitted for the decision model: none too small, too large or too long a strip.
const { fitImage } = await import(path.resolve(here, "../lib/imagefit.ts"));
const sharpLib = (await import("sharp")).default;
for (const [w, h, ok] of [[20, 15, (f) => Math.min(f.width, f.height) >= 64], [3000, 200, (f) => f.width <= 1568 && f.width / f.height <= 4],
  [400, 300, (f) => f.width === 400 && !f.changed.length], [5000, 5000, (f) => f.width === 1568], [30, 900, (f) => f.height / f.width <= 4 && Math.min(f.width, f.height) >= 64]]) {
  const png = await sharpLib({ create: { width: w, height: h, channels: 4, background: { r: 0, g: 0, b: 255, alpha: 0.5 } } }).png().toBuffer();
  const f = await fitImage(`data:image/png;base64,${png.toString("base64")}`);
  const real = await sharpLib(Buffer.from(f.url.split(",")[1], "base64")).metadata();
  assert.ok(ok(f) && real.width === f.width && real.height === f.height && !real.hasAlpha, `${w}x${h} -> ${f.width}x${f.height} (${f.changed.join("; ")})`);
}

// By default a decision model decides: one Choice question over the ways ticked, the picture in the state.
const tcall = run.calls.find((c) => c.step === "triage");
assert.equal(tcall.api, "decisions");
assert.equal(tcall.model, "typesafe/jev-1.14");
assert.deepEqual(Object.keys(tcall.tool.way.criteria), ["manim", "map", "styled"], "only the ways ticked are offered");
assert.equal(tcall.tool.way.options, undefined, "a Choice's options go in criteria");
assert.equal(tcall.tool.way.type, "choice");
assert.ok(tcall.tool.way.instructions.startsWith("You look at ONE figure from a textbook"), "v1's triage instructions");
assert.ok(tcall.tool.way.instructions.includes("- MAP: a map of a real place") && !tcall.tool.way.instructions.includes("PHOTO:"), "the ways offered, in v1's words");
assert.ok(tcall.request.state.some((s) => s.type === "image_url"), "the picture is in the state");
assert.ok(!JSON.stringify(tcall.request).includes("iVBORw0KGgo"), "the run's file keeps no image bytes");
const f0 = run.triage.figures[pics[0].id];
assert.ok(f0.confidence > 0.8 && !f0.unsure && Object.keys(f0.probabilities).length === 3, JSON.stringify(f0));
// A picture the decision model refuses ("Invalid image dimensions"): that figure is decided by the chat model.
await triageAction(run.id, { action: "one", block: pics[0].id, model: "fixture-refuses-images" });
run = await wait(run.id, (r) => r.triage.status === "running");
const refused = run.triage.figures[pics[0].id];
assert.equal(refused.status, "done", refused.error);
assert.equal(refused.engine, "chat");
assert.match(refused.rule, /refused its picture/);
assert.ok(run.calls.some((c) => c.checks.some((k) => k.name === "Picture size")), "the picture's size is checked and said");
await triageAction(run.id, { action: "one", block: pics[0].id, model: "typesafe/jev-1.14" });
run = await wait(run.id, (r) => r.triage.status === "running");

// The chat engine for one figure: its instruction and reason, the run's engine unchanged.
await triageAction(run.id, { action: "one", block: pics[1].id, engine: "chat" });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.equal(run.triage.engine, "decision");
assert.equal(run.triage.figures[pics[1].id].engine, "chat");
assert.ok(run.triage.figures[pics[1].id].how, "the chat model gives an instruction");
assert.ok(run.calls.at(-1).tool.function.parameters.properties.kind.enum.includes("map"));
// A high threshold makes the decisions unsure; the unsure ones go to the chat model.
await triageAction(run.id, { action: "reset", threshold: 0.95 });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.ok(Object.values(run.triage.figures).every((f) => f.unsure), "under the threshold: unsure");
await triageAction(run.id, { action: "unsure" });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.ok(Object.values(run.triage.figures).every((f) => f.engine === "chat" && !f.unsure && f.how), "the unsure ones answered by the chat model");
await triageAction(run.id, { action: "reset", kinds: ["manim", "map", "styled"], threshold: 0.6 });
run = await wait(run.id, (r) => r.triage.status === "running");
await assert.rejects(triageAction(run.id, { action: "run" }), /every figure is triaged/);
// Map not allowed: reset reruns all, and the map falls back to a way that is.
await triageAction(run.id, { action: "reset", kinds: ["manim", "styled"] });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.equal(run.triage.rounds, 8);
assert.equal(kindOf(0), "manim");
await triageAction(run.id, { action: "override", block: pics[0].id, kind: "exact" });
assert.equal(run.triage.figures[pics[0].id].override, "exact");
await triageAction(run.id, { action: "one", block: pics[1].id });
run = await wait(run.id, (r) => r.triage.status === "running");
assert.equal(run.triage.figures[pics[1].id].calls.length, 7, "a figure's calls are kept across reruns");

// A Map choice under 20 points from a redraw is redrawn instead; 20 or more apart, it stays a map.
const { mapOrRedraw } = await import(path.resolve(here, "../lib/triage.ts"));
const near = { choice: "map", probabilities: { map: 0.45, exact: 0.30, styled: 0.20 }, confidence: 0.45 };
assert.match(mapOrRedraw(near, ["map", "exact", "styled"]), /under 20 points/);
assert.equal(near.choice, "exact");
const far = { choice: "map", probabilities: { map: 0.7, exact: 0.2, styled: 0.1 }, confidence: 0.7 };
assert.equal(mapOrRedraw(far, ["map", "exact", "styled"]), undefined);
assert.equal(far.choice, "map");
const noRedraw = { choice: "map", probabilities: { map: 0.5, manim: 0.45 } };
assert.equal(mapOrRedraw(noRedraw, ["map", "manim"]), undefined, "no redraw offered: stays a map");

// Generation: the figures set to a redraw are redrawn with v1's prompt; the image is kept and shown.
const { generateAction } = await import(path.resolve(here, "../lib/generate.ts"));
await generateAction(run.id, { action: "run" });
run = await wait(run.id, (r) => r.generation.status === "running");
assert.equal(run.generation.status, "done", run.generation.error);
const g0 = run.generation.figures[pics[0].id];
assert.equal(g0.status, "done");
assert.equal(g0.kind, "exact");
assert.ok(g0.prompt.startsWith("Create an original, clean educational illustration for a school video lesson, based on the attached sketch."), g0.prompt);
assert.ok(g0.prompt.includes("It shows: Figure 1: A map of the rivers of India."), "the caption in the prompt");
assert.ok(g0.prompt.includes("NO TEXT AT ALL in the picture"), "no text in the image");
assert.ok(!/LOOKS JUST LIKE|exact copy|textbook|EVERY LABEL/i.test(g0.prompt), "no words moderation reads as copying");
assert.equal(g0.level, "full");
assert.ok(readFileSync(g0.file).subarray(1, 4).toString() === "PNG", "the image kept");
assert.equal(run.generation.figures[pics[1].id]?.kind, "manim", "the graph, triaged Manim, is drawn in Manim");
assert.equal(run.generation.figures[pics[1].id]?.status, "done", run.generation.figures[pics[1].id]?.error);
const gcall = run.calls.find((c) => c.id === g0.calls[0]);
assert.equal(gcall.api, "image");
assert.ok(gcall.prompt.user.some((p) => p.key === "keep") && gcall.prompt.user.some((p) => p.key === "reference"), "the prompt by its parts");
assert.equal(gcall.output.image.split("?")[0], `/api/runs/${run.id}/generated/${encodeURIComponent(pics[0].id)}`);
await assert.rejects(generateAction(run.id, { action: "run" }), /every figure is generated/);
await generateAction(run.id, { action: "one", block: pics[0].id });
run = await wait(run.id, (r) => r.generation.status === "running");
assert.equal(run.generation.figures[pics[0].id].calls.length, 2);
// A model whose moderation blocks: asked in gentler words, then with no reference image, and that is kept.
await generateAction(run.id, { action: "one", block: pics[0].id, model: "fixture-moderated" });
run = await wait(run.id, (r) => r.generation.status === "running");
const gm = run.generation.figures[pics[0].id];
assert.equal(gm.status, "done", gm.error);
assert.equal(gm.level, "blind");
const [cFull, cGentle, cBlind] = gm.calls.slice(-3).map((id) => run.calls.find((c) => c.id === id));
assert.ok(cFull.status === "failed" && /moderation/.test(cFull.error) && cFull.checks.some((c) => c.name === "Moderation"));
assert.ok(cGentle.prompt.user[0].label.includes("gentle") && !cGentle.prompt.user.some((p) => p.key === "context"), "gentle: no book text");
assert.ok(!JSON.stringify(cBlind.request ?? {}).includes("image_url") && !cBlind.prompt.user.some((p) => p.key === "reference"), "blind: no reference image");

// SVG: a figure set to SVG is drawn by the SVG model from the figure itself, in one call, and checked against v1's rules.
const { checkSvg, onBoard } = await import(path.resolve(here, "../lib/prompts/svg.ts"));
const bad = checkSvg('<svg viewBox="0 0 800 400"><script>alert(1)</script><g id="a" onclick="x()"><rect fill="#ff0000"/></g><image href="http://x/y.png"/></svg>');
assert.ok(!/script|onclick|http:/.test(bad.svg), "nothing that runs or loads is kept");
assert.ok(bad.problems.some((p) => /hex/.test(p)) && bad.problems.some((p) => /not allowed: image/.test(p)), bad.problems.join("; "));
assert.ok(onBoard('<svg viewBox="0 0 800 400"><g id="a"><rect fill="RIVER" stroke="INK"/></g></svg>').includes('fill="#5AB4F0" stroke="#F4E9D8"'), "names as the board's colours");
await triageAction(run.id, { action: "override", block: pics[1].id, kind: "svg" });
await generateAction(run.id, { action: "run" });
run = await wait(run.id, (r) => r.generation.status === "running");
const gs = run.generation.figures[pics[1].id];
assert.equal(gs.status, "done", gs.error);
assert.equal(gs.kind, "svg");
assert.ok(readFileSync(gs.file, "utf8").startsWith("<svg") && gs.svgParts.includes("subject"), "the SVG kept, with its parts");
const svgCalls = run.calls.filter((c) => gs.calls.includes(c.id) && c.label.startsWith("SVG"));
const scall = svgCalls[0];
assert.equal(scall.model, "anthropic/claude-sonnet-4.5", "the SVG model");
assert.equal(svgCalls.length, 1, "one call: the same model reads the figure and draws it");
assert.ok(scall.prompt.system.some((p) => p.key === "rules" && p.text.includes("Colours by NAME")), "v1's SVG rules");
assert.ok(scall.prompt.user.some((p) => p.key === "image"), "the figure goes with the request");
assert.ok(scall.checks.some((c) => c.name === "SVG rules" && c.result === "pass"), JSON.stringify(scall.checks));
// Manim: drawn by the Manim model from the figure, in one call, checked, and rendered with the repo's Manim.
const { checkManim, renderManim } = await import(path.resolve(here, "../lib/manim.ts"));
assert.ok(checkManim("import os\nself.play(Create(Circle()))").some((p) => /imports/.test(p)));
assert.ok(checkManim("open('x').read()\nself.add(Circle())").some((p) => /open/.test(p)));
assert.ok(checkManim("x = Circle().__class__\nself.add(x)").some((p) => /dunder/.test(p)));
assert.deepEqual(checkManim('c = Circle(color=INK)\nself.play(Create(c))'), []);
const broken = await renderManim("self.play(Create(NoSuchThing()))", path.join(process.cwd(), "manim-broken"));
assert.ok(!broken.png && /NameError|NoSuchThing/.test(broken.error ?? ""), `the error goes back to the model: ${broken.error}`);
await triageAction(run.id, { action: "override", block: pics[1].id, kind: "manim" });
await generateAction(run.id, { action: "one", block: pics[1].id });
run = await wait(run.id, (r) => r.generation.status === "running");
const gmn = run.generation.figures[pics[1].id];
assert.equal(gmn.status, "done", gmn.error);
assert.equal(readFileSync(gmn.file).subarray(1, 4).toString(), "PNG", "its last frame");
assert.ok(gmn.video && readFileSync(gmn.video).subarray(4, 8).toString() === "ftyp", "its video");
assert.ok(gmn.code.includes("self.play"));
const mcall = run.calls.find((c) => c.id === gmn.calls.at(-1));
assert.ok(mcall.prompt.system.some((p) => p.key === "rules" && p.text.includes("PALETTE")) && mcall.prompt.user.some((p) => p.text.includes("to rebuild exactly")), "v1's Manim rules");
assert.ok(mcall.checks.some((c) => c.name === "Render" && c.result === "pass"), JSON.stringify(mcall.checks));
// Maps: written by the map model from the book's map, in one call, compiled and rendered by v2's engine.
const { mapScript, compileMap, mapProblems, engineDir } = await import(path.resolve(here, "../lib/maps.ts"));
assert.ok(engineDir().endsWith(path.join("harness_v2", "engine")), `v2's own engine: ${engineDir()}`);
const ms = mapScript({ region: { country: "India" }, title: "T", beats: [{ say: "s", do: [{ op: "river", name: "Ganges" }, { op: "panel", title: "x" },
  { op: "marker", place: "Delhi", picture: { draw: "a fort" } }] }] });
assert.ok(ms.dropped.some((d) => /panel/.test(d)) && ms.dropped.some((d) => /picture/.test(d)), ms.dropped.join("; "));
assert.equal(ms.script.chapters[0].beats[0].do.length, 2);
const { mkdirSync } = await import("node:fs");
mkdirSync(path.join(process.cwd(), "map-check"), { recursive: true });
const refusedMap = await compileMap(mapScript({ region: { country: "India" }, title: "T", beats: [{ say: "s", do: [{ op: "marker", label: "nowhere" }] }] }).script,
  path.join(process.cwd(), "map-check"));
const why = mapProblems(refusedMap);
assert.ok(why[0] === "nothing was drawn on a map" && why.some((w) => /no place/.test(w)), `a map whose ops were all left out is refused: ${why}`);
await triageAction(run.id, { action: "override", block: pics[0].id, kind: "map" });
await generateAction(run.id, { action: "one", block: pics[0].id });
run = await wait(run.id, (r) => r.generation.status === "running");
const gmap = run.generation.figures[pics[0].id];
assert.equal(gmap.status, "done", gmap.error);
assert.equal(gmap.kind, "map");
assert.equal(readFileSync(gmap.file).subarray(1, 4).toString(), "PNG", "the map's last frame");
assert.ok(gmap.video && readFileSync(gmap.video).subarray(4, 8).toString() === "ftyp", "the map's video");
assert.equal(gmap.mapScript.region.country, "India");
const mapCall = run.calls.find((c) => c.id === gmap.calls.at(-1));
assert.ok(mapCall.checks.some((c) => c.name === "Engine check" && c.result === "pass") && mapCall.prompt.system.some((p) => p.key === "ops" && p.text.includes('"op":"empire"')), "v1's map ops");
await triageAction(run.id, { action: "override", block: pics[0].id, kind: "exact" });

// In parallel: one figure started while another is being generated; the busy one is not started twice.
const { generating } = await import(path.resolve(here, "../lib/generate.ts"));
await generateAction(run.id, { action: "one", block: pics[1].id });
await generateAction(run.id, { action: "one", block: pics[0].id });
assert.deepEqual(generating(run.id).sort(), [pics[0].id, pics[1].id].sort(), "both at once");
await assert.rejects(generateAction(run.id, { action: "one", block: pics[1].id }), /being generated already/);
run = await wait(run.id, (r) => r.generation.status === "running");
assert.equal(run.generation.status, "done", run.generation.error);
assert.ok([pics[0].id, pics[1].id].every((id) => run.generation.figures[id].status === "done"));
assert.deepEqual(generating(run.id), []);
await triageAction(run.id, { action: "override", block: pics[1].id, kind: null });

// Script: chapters and beats, every sentence once and in order; code mends what it can and says so.
const { readScript, scriptAction, lectureFigures } = await import(path.resolve(here, "../lib/script.ts"));
const figs = [{ id: "f1", way: "Map", caption: "a map", ready: true, lines: [3] }];
const mended = readScript({ chapters: [
  { title: "B", narration: "", map: false, beats: [{ lines: [5, 6], show: "x" }, { lines: [3, 4, 99], show: "the map", figure: "f1" }] },
  { title: "A", narration: "Chapter one.", map: false, beats: [{ lines: [1, 2, 2], show: "y", figure: "nope" }] },
] }, 7, figs);
assert.deepEqual(mended.problems, [], mended.problems.join("; "));
assert.deepEqual(mended.chapters.flatMap((c) => c.beats.flatMap((b) => b.lines)), [1, 2, 3, 4, 5, 6, 7], "every sentence once, in order");
assert.equal(mended.chapters[0].title, "A", "chapters in sentence order");
assert.ok(mended.chapters[1].map, "a chapter showing a Map figure is a map chapter");
const fixedNames = mended.checks.filter((c) => c.result === "fixed").map((c) => c.name);
for (const name of ["Sentence numbers", "Each sentence once", "Order", "Every sentence", "Figures", "Map chapter"]) assert.ok(fixedNames.includes(name), `${name}: ${fixedNames}`);
assert.equal(mended.chapters[1].narration, "Chapter 2. B.", "a title card line when none was given");
const tangled = readScript({ chapters: [{ title: "A", narration: "", map: false, beats: [{ lines: [1, 3], show: "" }, { lines: [2, 4], show: "" }] }] }, 4, []);
assert.ok(tangled.problems.some((p) => /interleave/.test(p)), "interleaved beats go back to the model");

await scriptAction(run.id, { action: "run" });
run = await wait(run.id, (r) => r.script.status === "running");
assert.equal(run.script.status, "done", run.script.error);
for (const l of run.lectures) {
  const ls = run.script.lectures[l.n];
  assert.equal(ls.status, "done", ls.error);
  const said = ls.chapters.flatMap((c) => c.beats.flatMap((b) => b.lines));
  assert.deepEqual(said, Array.from({ length: linesOfText(l.text).length }, (_, i) => i + 1), `lecture ${l.n}: every sentence once, in order`);
  assert.ok(ls.chapters.every((c) => c.title && c.narration && c.beats.length));
}
const scriptCall = run.calls.find((c) => c.step === "script");
assert.ok(scriptCall.prompt.user.some((p) => p.key === "transcript" && p.text.startsWith("1| ")), "the transcript numbered");
const withFigure = run.lectures.find((l) => lectureFigures(run, l.n).length);
if (withFigure) assert.ok(run.script.lectures[withFigure.n].chapters.some((c) => c.beats.some((b) => b.figure)), "the lecture's figure placed on a beat");
await assert.rejects(scriptAction(run.id, { action: "run" }), /every written lecture is scripted/);
await assert.rejects(scriptAction(run.id, { action: "next" }), /every written lecture is scripted/);
// One at a time: a whole build in turn, and the next lecture not scripted yet.
await scriptAction(run.id, { action: "reset", oneAtATime: true });
run = await wait(run.id, (r) => r.script.status === "running");
assert.equal(run.script.status, "done", run.script.error);
assert.ok(run.lectures.every((l) => run.script.lectures[l.n].status === "done"), "a build in turn scripts every lecture");
{
  const r = await loadRun(run.id);
  r.script.lectures[2].status = "failed";
  await saveRun(r, true);
  await scriptAction(run.id, { action: "next" });
  run = await wait(run.id, (x) => x.script.status === "running");
  assert.equal(run.script.lectures[2].status, "done", "next scripts the first lecture not scripted");
}

// Export: numbered sentences, goals with their sentences, figures with their triage; imported again as a run.
const x = exportTranscript(run);
assert.equal(x.format, "pocketanim.v2.transcript");
assert.equal(x.lectures.length, run.lectures.length);
assert.ok(x.lectures.every((l) => l.lines.length && l.lines[0].n === 1));
const fig = x.blocks.find((b) => b.id === pics[0].id).figure;
assert.equal(fig.triage.kind, "exact");
assert.equal(fig.triage.chosenBy, "user");
assert.ok(fig.generated?.prompt?.includes("NO TEXT AT ALL"), "the export carries the redraw's prompt");
assert.ok(transcriptMarkdown(run).includes("### Transcript"));
const back = await importTranscript(JSON.parse(JSON.stringify(x)), "x.json");
assert.equal(back.status, "done");
assert.deepEqual(back.script.lectures[1].chapters, run.script.lectures[1].chapters, "the scripts travel with the export");
assert.equal(back.documentId, run.documentId, "the same book: found here, not made again");
assert.deepEqual(back.lectures.map((l) => l.text), run.lectures.map((l) => l.text));
assert.equal(back.triage.figures[pics[0].id].override, "exact");
assert.deepEqual(exportTranscript(back).lectures, x.lectures, "export, import, export: the same lectures");

// Continue: a lecture lost is written again, and only it.
const calls = run.calls.length;
const lost = run.lectures[1];
Object.assign(lost, { status: "waiting", text: undefined });
run.status = "failed";
run.steps.find((s) => s.key === "write").status = "failed";
await continueRun(run.id);
run = await wait(run.id, (r) => r.status === "running");
assert.equal(run.status, "done", run.error);
assert.equal(lost.status, "written");
const added = run.calls.slice(calls);
assert.ok(added.length >= 1 && added.every((c) => c.lecture === lost.n), `only lecture ${lost.n} written again: ${added.map((c) => c.label)}`);

// The whole file on another machine: the book is not there; the file carries it, and the next steps go on from it.
const whole = JSON.parse(JSON.stringify(await exportWhole(run)));
assert.equal(whole.version, 2);
assert.ok(whole.book.pdf && whole.book.datalab && Object.keys(whole.book.figures).length === 2, "the book is in the file");
rmSync(path.join(process.cwd(), ".data"), { recursive: true, force: true });
assert.match(checkExport({ format: "x" }), /not an exported/);
assert.match(checkExport({ ...whole, version: 99 }), /newer/);
const there = await importTranscript(whole, "whole.json");
assert.notEqual(there.documentId, run.documentId, "the book made again");
assert.ok(there.log[0].text.includes("made again from the file"), there.log[0].text);
assert.deepEqual(exportTranscript(there).lectures, x.lectures);
await triageAction(there.id, { action: "one", block: pics[1].id, kinds: ["manim", "map"] });
const t2 = await wait(there.id, (r) => r.triage.status === "running");
assert.equal(t2.triage.figures[pics[1].id].kind, "manim", t2.triage.error);
Object.assign(t2.lectures[2], { status: "waiting", text: undefined });
t2.status = "stopped";
await continueRun(there.id);
const t3 = await wait(there.id, (r) => r.status === "running");
assert.equal(t3.status, "done", t3.error);
assert.equal(t3.lectures[2].status, "written");
assert.ok(t3.calls.find((c) => c.lecture === 3).prompt.user.find((p) => p.key === "previous").text.includes(run.lectures[0].text.slice(0, 60)),
  "a lecture written after import sees the imported ones");

// A figure Datalab returned no picture for: cut out of the PDF itself, and triaged with no transcript built.
const figDoc = await addDocument("figure.pdf", new Uint8Array(readFileSync(path.join(here, "fixtures", "figure.pdf"))));
const fdir = path.join(process.cwd(), ".data", "docs", figDoc.id);
const fbook = JSON.parse(readFileSync(path.join(fdir, "book.json"), "utf8"));
const [, , fw, fh] = fbook.children[0].bbox;
// The offline reader found the picture itself (/page/0/Picture/0). A second figure block where Datalab would put it
// (the picture is at about x 0.07-0.64, y 0.19-0.48), with no picture: the search cuts it out of the PDF.
fbook.children[0].children.push({ id: "/page/0/Picture/5", block_type: "Picture", html: "", bbox: [fw * 0.06, fh * 0.18, fw * 0.66, fh * 0.49], children: null });
writeFileSync(path.join(fdir, "book.json"), JSON.stringify(fbook));
rmSync(path.join(fdir, "figure-report.json"), { force: true });
const readOnly = await startRun(figDoc.id, {}, "read");
let r1 = await wait(readOnly.id, (r) => r.status === "running");
assert.equal(r1.status, "stopped", r1.error);
assert.equal(r1.steps.find((x) => x.key === "read").status, "done");
assert.equal(r1.steps.find((x) => x.key === "plan").status, "waiting", "no transcript built");
assert.equal(r1.calls.length, 0);
await triageAction(readOnly.id, { action: "run" });
r1 = await wait(readOnly.id, (r) => r.triage.status === "running");
assert.equal(r1.triage.status, "done", r1.triage.error);
assert.ok(r1.blocks.find((b) => b.id === "/page/0/Picture/5").image, "the picture was cut out of the PDF");
const freport = JSON.parse(readFileSync(path.join(fdir, "figure-report.json"), "utf8"));
assert.equal(freport.cut, 1, JSON.stringify(freport));
assert.ok(r1.blocks.find((b) => b.id === "/page/0/Picture/0")?.image, "the offline reader makes a Picture block of the PDF's picture");
const cutPng = readFileSync(JSON.parse(readFileSync(path.join(fdir, "figures.json"), "utf8"))["/page/0/Picture/5"]);
assert.equal(cutPng.subarray(1, 4).toString(), "PNG");
assert.equal(cutPng.readUInt32BE(16), 420, "the picture at its own size");
assert.equal(r1.triage.figures["/page/0/Picture/5"].status, "done");

// A way chosen by hand on a run with no triage: the figure gets it, and is generated that way.
const bare = await startRun(figDoc.id, {}, "read");
let r2 = await wait(bare.id, (r) => r.status === "running");
assert.ok(!r2.triage, "no triage yet");
await triageAction(bare.id, { action: "override", block: "/page/0/Picture/0", kind: "exact" });
await generateAction(bare.id, { action: "one", block: "/page/0/Picture/0" });
r2 = await wait(bare.id, (r) => r.generation.status === "running");
assert.equal(r2.generation.figures["/page/0/Picture/0"].status, "done", r2.generation.figures["/page/0/Picture/0"].error);
await assert.rejects(triageAction(bare.id, { action: "override", block: "/page/9/Nothing/1", kind: "map" }), /no such figure/);

console.log(`ok: ${run.blocks.length} blocks, ${run.lectures.length} lectures, ${Object.keys(run.goalStatus).length} goals, ${run.calls.length} calls, ${pics.length} figures triaged`);
process.exit(0);
