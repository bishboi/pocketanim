// The transcription flow end to end with no keys: a 4-page chapter PDF read by the offline reader into Datalab-shaped
// JSON, written by the offline stand-in, each lecture as its script in one call. Checks: blocks keep Datalab's ids and
// boxes; the writer sees no boxes; the writer decides the lectures; chapters name their content (and may share it);
// a figure may be on several beats; the beats are the transcript; lectures see the ones before them.
//   npm run check
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

delete process.env.OPENROUTER_API_KEY;
delete process.env.DATALAB_API_KEY;
const here = import.meta.dirname;
// The slow parts (real renders of what a faster part already compiles, every Lab preset compiled, the Voice tab's
// trial, the sync probes) only with V2_CHECK_FULL=1; by default a sample of the Lab, and the rest skipped.
const FULL = process.env.V2_CHECK_FULL === "1";
const began = Date.now();
/** `items` through `work`, `n` at a time. */
const atOnce = async (items, n, work) => {
  const queue = [...items];
  await Promise.all(Array.from({ length: Math.min(n, queue.length) }, async () => {
    for (let x = queue.shift(); x !== undefined; x = queue.shift()) await work(x);
  }));
};
// Manim renders with the repo's .venv (the check runs from a temporary folder).
process.env.V2_PYTHON ??= path.resolve(here, "../../../.venv/bin/python");
// Maps are drawn by v2's own engine (a copy of v1's).
process.env.V2_ENGINE ??= path.resolve(here, "../../engine");
// The pictures the engine makes go to the check's own folder: never among a real run's pictures made before.
process.env.PANIM_IMAGE_CACHE = path.join(mkdtempSync(path.join(tmpdir(), "v2-check-images-")));
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
  for (let i = 0; i < 1200; i++) {   // two minutes: a map figure renders a video
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

// No planner: the steps are read, figures, write; each lecture is written as its script in one call, at high effort.
assert.deepEqual(run.steps.map((s) => s.key), ["read", "figures", "write"]);
const first = run.calls.find((c) => c.step === "lecture");
assert.equal(first.effort, "high", "the writer thinks longer");
const sent = render(first.prompt.user);
assert.ok(sent.includes('"block_type":"SectionHeader"') && sent.includes("/page/0/") && sent.includes("NOT TAUGHT"), "the writer sees the blocks, each taught or not");
assert.ok(!/bbox|polygon|"box"/.test(sent), "the writer sees no boxes");
assert.equal(first.tool.function.name, "write_lecture");

// The writer decided the lectures; each is its chapters and beats, the beats' sentences the whole text, in order.
const { linesOf: linesOfText } = await import(path.resolve(here, "../lib/source/book.ts"));
assert.ok(run.lectures.length >= 2, `lectures by topic (${run.lectures.length})`);
assert.ok(run.lectures.every((l) => l.status === "written" && l.text && !l.goals.length), "written, no goals");
const ids = new Set(run.blocks.map((b) => b.id));
for (const l of run.lectures) {
  const ls = run.script.lectures[l.n];
  assert.equal(ls.status, "done");
  assert.ok(ls.chapters.length && ls.chapters.every((c) => c.title && c.narration && c.beats.length && c.content.length && c.content.every((id) => ids.has(id))));
  const said = ls.chapters.flatMap((c) => c.beats.flatMap((b) => b.lines));
  assert.deepEqual(said, Array.from({ length: linesOfText(l.text).length }, (_, i) => i + 1), `lecture ${l.n}: the beats are the text, in order`);
  assert.deepEqual(l.blocks, [...new Set(ls.chapters.flatMap((c) => c.content))], "a lecture's blocks are its chapters' content");
}
const allChapters = run.lectures.flatMap((l) => run.script.lectures[l.n].chapters);
const usedBy = (id) => allChapters.filter((c) => c.content.includes(id)).length;
assert.ok(run.blocks.some((b) => usedBy(b.id) > 1), "chapters may share content");
const allBeats = allChapters.flatMap((c) => c.beats);
const figIds = [...new Set(allBeats.flatMap((b) => b.figures ?? []))];
assert.ok(figIds.length && figIds.some((f) => allBeats.filter((b) => (b.figures ?? []).includes(f)).length > 1), "a figure on several beats");
const taughtIds = new Set(allChapters.flatMap((c) => c.content));
const skippedIds = new Set(run.skipped.map((x) => x.block));
assert.ok(run.blocks.every((b) => taughtIds.has(b.id) || skippedIds.has(b.id) || ["SectionHeader", "PageHeader", "PageFooter"].includes(b.type)),
  "the whole book taught (or skipped as furniture)");
assert.ok(first.checks.some((c) => c.name === "Script" && c.result === "pass"), "code reads the script");

// A later lecture is given the earlier ones whole and the book marked with what they taught; no length ceiling.
const second = run.calls.find((c) => c.step === "lecture" && c.lecture === 2);
const previous = second.prompt.user.find((p) => p.key === "previous").text;
assert.ok(previous.includes(linesOfText(run.lectures[0].text)[0]), "lecture 2 sees lecture 1's transcript");
assert.ok(second.prompt.user.find((p) => p.key === "book").text.includes('"taught":"in lecture 1"'), "lecture 2 sees what lecture 1 taught");
assert.ok(!/at most about|words \(\d+ min\)/.test(render(second.prompt.system) + render(second.prompt.user)), "no length ceiling");
assert.ok(second.prompt.system.some((p) => p.key === "speech" && p.text.includes("INDIAN CLASSROOM") &&
  (run.options.language === "english" || p.text.includes("HOW THE BEST HINDI EXPLAINER CHANNELS TELL IT"))) && second.prompt.system.some((p) => p.key === "examples" && p.text.includes("WHAT IT SOUNDS LIKE")), "the script is told how a teacher in India talks");
// Figures: both described, then triaged from the ways allowed.
const { triageAction } = await import(path.resolve(here, "../lib/triage.ts"));
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
// The beat script's reference (engine/BEAT_SCRIPT.md) keeps up with the compiler: every operation it accepts and every
// field of the script, a chapter and a beat it reads is written there.
{
  const { runPython: rp } = await import(path.resolve(here, "../lib/manim.ts"));
  const engine = process.env.V2_ENGINE;
  const code = [
    "import json, re, compile_lecture as c",
    "ops = {'panel','fact','stat','bars','clear','icon','figure','photo','illustration','picture','draw','unstage'} | c.KIT_OPS | c.MAP_OPS | c.BUILD_OPS | c.STEP_OPS | c.WORK_OPS | c.FREE_OPS",
    "src = open('compile_lecture.py').read()",
    "fields = {w: sorted(set(k for k in re.findall(w + r'\\.get\\(\"([a-z_]+)\"', src) if not k.startswith('_'))) for w in ('script', 'chapter', 'beat')}",
    "print(json.dumps({'ops': sorted(ops), **fields}))",
  ].join("\n");
  const listed = await rp(["-c", code], engine, { PYTHONPATH: engine });
  const known = JSON.parse(listed.stdout.trim().split("\n").pop());
  const doc = readFileSync(path.join(engine, "BEAT_SCRIPT.md"), "utf8");
  const missing = Object.entries(known).flatMap(([kind, names]) => names.filter((k) => !doc.includes(`\`${k}\``)).map((k) => `${kind}: ${k}`));
  assert.deepEqual(missing, [], `engine/BEAT_SCRIPT.md does not document: ${missing.join(", ")}`);
  assert.ok(known.ops.length > 30 && known.script.length > 10 && known.beat.length > 4, "the compiler's names were read");
  // The motion engine's reference (engine/MOTION_ENGINE.md, beta) likewise: its templates, their arguments, the
  // script fields it reads and the values it accepts.
  const motionCode = [
    "import json, re, compile_motion as m, motion_looks as l",
    "src = open('compile_motion.py').read()",
    "args = sorted({a for o in m.MOTION_OPS.values() for a in o['args'] if a not in ('file',)})",
    "fields = sorted(set(k for k in re.findall(r'script\\.get\\(\"([a-z_]+)\"', src) if not k.startswith('_')))",
    "values = sorted(set(m.CHART_KINDS) | set(m.LIST_MARKS) | set(m.EMPHASES) | set(m.TIMELINE_STYLES) | set(m.ENERGIES) | set(l.TRANSITIONS) | set(l.LOOKS) | {w for ws in m.LAYOUTS.values() for w in ws} | set(m.ENTRANCES) | set(m.RANK_ORDERS) | set(m.IDLES) | set(m.CAMERA_MOVES))",
    "print(json.dumps({'templates': sorted(set(m.MOTION_OPS) | set(m.SUGAR_OPS)), 'args': args, 'script': fields, 'values': values}))",
  ].join("\n");
  const mlisted = await rp(["-c", motionCode], engine, { PYTHONPATH: engine });
  const mknown = JSON.parse(mlisted.stdout.trim().split("\n").pop());
  const mdoc = readFileSync(path.join(engine, "MOTION_ENGINE.md"), "utf8");
  const mmissing = Object.entries(mknown).flatMap(([kind, names]) => names.filter((k) => !mdoc.includes(`\`${k}\``)).map((k) => `${kind}: ${k}`));
  assert.deepEqual(mmissing, [], `engine/MOTION_ENGINE.md does not document: ${mmissing.join(", ")}`);
  assert.ok(mknown.templates.length >= 15 && mknown.script.length >= 4, "the motion compiler's names were read");
}

// Timelines in proportion (v2's engine): dates read as years; a range, periods (spans); drawn by a real render.
{
  const { runPython: rp } = await import(path.resolve(here, "../lib/manim.ts"));
  const engine = process.env.V2_ENGINE;
  const env = { PYTHONPATH: engine, PANIM_VOICE: "silent", PANIM_IMAGES: "0" };
  const dates = await rp(["-c", "import json,timeline_dates as t; print(json.dumps([t.year(x) for x in ['1526','500 BC','AD 78','1920s','16th century','early 18th century','15 August 1947','Stone Age','Step 2']]))"], engine, env);
  assert.deepEqual(JSON.parse(dates.stdout.trim().split("\n").pop()).map((y) => (y === null ? null : Math.round(y))), [1526, -500, 78, 1925, 1550, 1720, 1948, null, null], "dates read as years");
  const tlScript = (op) => ({ title: "T", style: "atlas", teaching_rules: false, place_figures: false, auto_visuals: false,
    chapters: [{ title: "A", narration: "Chapter one.", map: false, beats: [{ say: "From 1905 to 1947.", do: [op] }] }] });
  const compileTl = async (op) => {
    const r = await rp([path.join(engine, "compile_lecture.py"), "-", "--json"], engine, env, JSON.stringify(tlScript(op)), 300000);
    return JSON.parse(r.stdout.slice(r.stdout.indexOf("{")));
  };
  const tl = await compileTl({ op: "timeline", title: "India", range: ["1900", "1950"], events: [["1885", "Congress"], ["1905", "Bengal"], ["1930", "Dandi March"], ["1947", "Independence"]],
    spans: [["1914", "1918", "World War I"], ["x", "y", "bad"]] });
  assert.deepEqual(tl.errors, []);
  assert.ok(/range=\("1900", "1950"\)/.test(tl.source) && /spans=\[\("1914", "1918", "World War I"\)\]/.test(tl.source), "range and spans passed to the engine");
  assert.ok(tl.warnings.some((w) => /outside its range/.test(w)) && tl.warnings.some((w) => /span is \[from, to, label\]/.test(w)), tl.warnings.join("; "));
  const even = await compileTl({ op: "timeline", events: [["Stone Age", "Stone tools"], ["Bronze Age", "Bronze"]], spans: [["1", "2", "x"]] });
  assert.ok(even.warnings.some((w) => /spaced evenly/.test(w)), "undated: spaced evenly");
  // Drawn: the timeline's beat rendered (its last frame), nothing skipped by the engine's guard (V2_CHECK_FULL).
  if (FULL) {
  const dir = mkdtempSync(path.join(tmpdir(), "v2-timeline-"));
  writeFileSync(path.join(dir, "scene.py"), tl.source.split("\n").filter((l) => !/self\.(outro_fade|title_slide|credits)\(/.test(l)).join("\n"));
  const drawn = await rp(["-m", "manim", "-ql", "-s", "--disable_caching", "-o", "tl", "scene.py", "GeneratedScene"], dir, env, undefined, 600000);
  assert.ok(!/picture skipped|Traceback/.test(drawn.out), `the timeline is drawn: ${drawn.out.slice(-600)}`);
  assert.ok(readFileSync(path.join(dir, "media", "images", "scene", "tl.png")).length > 1000, "its frame");
  }
}

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

// The script as the later steps read it: a lecture's figures with the beats they are on; the chapters using a block.
const { lectureFigures, chaptersUsing } = await import(path.resolve(here, "../lib/script-figures.ts"));
const withFigure = run.lectures.find((l) => lectureFigures(run, l.n).some((f) => f.beats.length > 1));
assert.ok(withFigure, "a lecture's figure on several beats");
const shared = run.blocks.find((b) => usedBy(b.id) > 1);
assert.ok(chaptersUsing(run, shared.id).length > 1, "every chapter using a block");

// Scenes: each beat's visuals as the engine's operations, compiled, a kind switched off, one beat rendered.
const { scenesAction } = await import(path.resolve(here, "../lib/scenes.ts"));
const { filterOps } = await import(path.resolve(here, "../lib/visual-kinds.ts"));
const slow = async (id, busy, tries = 1800) => {
  for (let i = 0; i < tries; i++) {
    const r = await loadRun(id);
    if (!busy(r)) return r;
    await new Promise((res) => setTimeout(res, 100));
  }
  throw new Error("timed out");
};
const offOps = filterOps([{ op: "picture", generate: "a farmer" }, { op: "diagram", id: "d", nodes: [{ id: "a", label: "A", picture: { generate: "x" } }] },
  { op: "timeline", events: [["1526", "Panipat", { generate: "a battle" }]] }, { op: "fact", text: "ok" }, { op: "teleport" }], ["diagram", "timeline"]);
assert.equal(offOps.ops.length, 3, "the illustration and the unknown op taken out");
assert.ok(!offOps.ops[0].nodes[0].picture && offOps.ops[1].events[0].length === 2, "pictures on nodes and events taken out when illustrations are off");
assert.equal(offOps.dropped.length, 4);
// This part is the current engine's (a lecture's scenes start on the motion engine, which is checked further on).
await scenesAction(run.id, { action: "engine", engine: "current" });
await scenesAction(run.id, { action: "look", style: "chalkboard", art: "sketch" });
await scenesAction(run.id, { action: "kinds", kinds: ["figure", "diagram", "define", "timeline"] });
await scenesAction(run.id, { action: "build", scope: "lecture", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running");
const sl1 = run.scenes.lectures[1];
assert.equal(sl1.status, "done", sl1.error);
assert.equal(run.scenes.look.style, "chalkboard");
const sceneBeats = run.script.lectures[1].chapters.flatMap((c) => c.beats);
assert.ok(sceneBeats.every((b) => sl1.beats[b.n]?.status === "done"), "every beat has its visuals");
assert.equal(sl1.compile.status, "done", JSON.stringify(sl1.compile));
assert.ok(Object.values(sl1.beats).every((b) => !b.errors?.length), "nothing refused by the compiler");
assert.ok(Object.values(sl1.beats).every((b) => b.ops.every((o) => ["panel", "fact", "picture", "diagram", "reveal", "focus", "point", "shade", "unshade", "label", "unlabel", "unfocus", "unstage", "define", "clear"].includes(o.op))),
  "only the kinds switched on");
// A chapter as one piece (the default), on the current engine in one JSON: the director writes the beats (each line's
// operations, no timing, no pointing), then each few paragraphs choreographed (the stand-in here) with their
// artifacts' manuals, answered as a patch on those beats that code applies.
const directorCalls = run.calls.filter((c) => c.step === "scenes" && /\(director\)$/.test(c.label));
assert.equal(directorCalls.length, run.script.lectures[1].chapters.length, "one director call a chapter");
// The director's prompt is its own: its instructions, the primitives, the facts it needs; none of the per-beat writer's.
assert.ok(directorCalls.every((c) => !c.prompt.system.some((p) => /^v1-/.test(p.key) && p.key !== "v1-matters") && c.prompt.system.some((p) => p.key === "primitives")
  && c.prompt.system.reduce((k, p) => k + p.text.length, 0) < 25000), "the director told only what it needs");
// Its limits: a plan past them is said (planProblems) and cut to fit (fitPlan): a scene too long split, a diagram too
// big cut to its nodes and its words.
{
  const d = await import(path.resolve(here, "../lib/director.ts"));
  const big = { elements: [{ id: "tree", op: { op: "diagram", id: "tree", nodes: Array.from({ length: 9 }, (_, k) => ({ id: `n${k}`,
    label: k ? `Node ${k}` : "A very long label of a great many words", items: ["one two three four", "a", "b", "c"] })), edges: [["n0", "n8", "one two three"]] } }],
    scenes: [{ id: "S1", beats: [1, 2, 3, 4, 5, 6, 7, 8, 9], uses: ["tree"] }] };
  const problems = d.planProblems(big);
  assert.ok(problems.some((x) => /9 beats/.test(x)) && problems.some((x) => /9 nodes/.test(x)) && problems.some((x) => /items/.test(x)), JSON.stringify(problems));
  const notes = d.fitPlan(big);
  assert.deepEqual(big.scenes.map((x) => x.beats.length), [5, 4], JSON.stringify(big.scenes));
  assert.ok(big.scenes.every((x) => x.uses.includes("tree")) && big.elements[0].op.nodes.length === 6 && big.elements[0].op.edges.length === 0, JSON.stringify(big.elements[0].op));
  assert.equal(d.planProblems(big).length, 0, JSON.stringify(d.planProblems(big)));
  assert.ok(notes.length >= 2, JSON.stringify(notes));
}
// The director's beats and the choreographer's patch (lib/beat-director.ts): limits said and cut to fit, timing and
// pointing taken out of the director's beats, a patch read against them (a word of its line, an operation by number,
// a part by name, a look that cannot change content) and applied.
{
  const b = await import(path.resolve(here, "../lib/beat-director.ts"));
  const long = Array.from({ length: 7 }, (_, k) => ({ beat: k + 1, do: [] }));
  long[0].do = [{ op: "diagram", id: "d", nodes: Array.from({ length: 8 }, (_, k) => ({ id: `n${k}`, label: `Node ${k}` })), edges: [], on: "w2" },
    { op: "point", target: "Node 1" }];
  const read = b.readBeats({ beats: long }, long.map((x) => x.beat));
  assert.ok(read.beats[0].paragraph && read.beats[0].do.length === 1 && read.beats[0].do[0].on === undefined && read.notes.some((x) => /point left out/.test(x)), JSON.stringify(read));
  const problems = b.beatsProblems(read.beats);
  assert.ok(problems.some((x) => /7 beats/.test(x)) && problems.some((x) => /8 nodes/.test(x)), JSON.stringify(problems));
  b.fitBeats(read.beats);
  assert.deepEqual([b.paragraphsOf(read.beats).map((r) => r.length), read.beats[0].do[0].nodes.length, b.beatsProblems(read.beats).length], [[4, 3], 6, 0]);
  const beats = [
    { beat: 1, paragraph: true, do: [{ op: "picture", generate: "a river bank", labels: ["water", "soil"], hold: ["soil"] }] },
    { beat: 2, do: [{ op: "label", part: "soil" }] },
    { beat: 3, do: [] },
    { beat: 4, paragraph: true, do: [{ op: "diagram", id: "chain", nodes: [{ id: "food", label: "Food" }, { id: "towns", label: "Towns" }], edges: [["food", "towns"]], show: ["food"] }] },
    { beat: 5, do: [{ op: "reveal", diagram: "chain", nodes: ["towns"] }] }];
  const d = await import(path.resolve(here, "../lib/director.ts"));
  const words = new Map([1, 2, 3, 4, 5].map((n) => [n, d.estimatedWords(n, "one two three four five six seven eight")]));
  assert.deepEqual([b.opParts(beats[0].do[0]).map((p) => p.name), b.opParts(beats[3].do[0]).map((p) => p.name), b.opParts(beats[1].do[0])], [["water"], ["Food"], []],
    "a part held for a later line is not this line's");
  const patch = b.readPatch({ beats: [
    { beat: 1, steps: [{ at: "w1", do: "enter", op: 0 }, { at: "w2", do: "show", op: 0, part: "water" }, { at: "w9", do: "light", part: "water", until: "b3.w5" },
      { at: "w2", do: "show", op: 0, part: "nope" }], look: [{ op: 0, move: "drift", labels: ["x"] }] },
    { beat: 2, steps: [{ at: "w3", do: "enter", op: 0 }] },
    { beat: 3, steps: [{ at: "w2", do: "hide", part: "water" }, { at: "w4", do: "exit" }] },
    { beat: 5, steps: [{ at: "w1", do: "enter", op: 0 }, { at: "w2", do: "focus", diagram: "chain", node: "towns", until: "b5.w6" }, { at: "w3", do: "pulse", target: "Food" }] },
    { beat: 99, steps: [] }] }, beats, words);
  assert.equal(patch.dropped.length, 3, JSON.stringify(patch.dropped));
  assert.ok(patch.dropped.some((x) => /no part "nope"/.test(x)) && patch.dropped.some((x) => /cannot change "labels"/.test(x)) && patch.dropped.some((x) => /beat 99/.test(x)));
  const { ops, notes } = b.applyPatch(beats, patch.patch);
  assert.deepEqual(ops.get(1).map((o) => [o.op, o.on, o.hold, o.move]), [["picture", "w1", ["soil"], "drift"], ["shade", "w7", true, undefined]], JSON.stringify(ops.get(1)));
  assert.equal(ops.get(1)[0].labels[0].on, "w2", "a part on its word");
  assert.deepEqual(ops.get(2).map((o) => [o.op, o.on]), [["label", "w3"]]);
  assert.deepEqual(ops.get(3).map((o) => [o.op, o.on]), [["unlabel", "w2"], ["unstage", "w4"], ["unshade", "w5"]], JSON.stringify(ops.get(3)));
  assert.deepEqual(ops.get(5).map((o) => [o.op, o.on]), [["reveal", "w1"], ["focus", "w2"], ["point", "w3"], ["unfocus", "w6"]], JSON.stringify(ops.get(5)));
  assert.equal(notes.length, 0, JSON.stringify(notes));
  assert.deepEqual(b.upBefore(beats).get(3).length, 1, "what is up as a line begins");
  // A reveal's nodes each on the word of its own show (a reveal for each word); a field sent empty is not given.
  const two = structuredClone(beats);
  two[3].do[0].nodes.push({ id: "trade", label: "Trade" });
  two[4].do[0].nodes = ["towns", "trade"];
  const split = b.readPatch({ beats: [{ beat: 5, steps: [{ at: "w2", do: "show", op: 0, part: "Towns", until: "", target: "" },
    { at: "w5", do: "show", op: 0, part: "trade", until: "" }, { at: "w6", do: "light", part: "water", until: "" }] }] }, two, words);
  assert.deepEqual(split.dropped, [], JSON.stringify(split.dropped));
  assert.deepEqual(b.applyPatch(two, split.patch).ops.get(5).map((o) => [o.op, o.nodes, o.on]),
    [["reveal", ["towns"], "w2"], ["reveal", ["trade"], "w5"], ["shade", undefined, "w6"]]);
}
assert.ok(directorCalls.every((c) => c.prompt.system.some((p) => p.key === "director" && /THE CHAPTER'S BEATS/.test(p.text))
  && !c.prompt.system.some((p) => p.key === "v2-anchors") && c.checks.some((k) => k.name === "Beats" && k.result === "pass")), "the director writes the beats, and times nothing");
const choreoCalls = run.calls.filter((c) => c.step === "scenes" && /^Choreography: lecture 1/.test(c.label));
assert.ok(choreoCalls.length >= run.script.lectures[1].chapters.length && choreoCalls.every((c) => c.status === "done"
  && c.prompt.system.some((p) => p.key === "manuals" && /=== \w+ ===/.test(p.text)) && c.checks.some((k) => k.name === "Steps" && k.result !== "fail")),
  "every chapter's paragraphs choreographed with their manuals");
const plans = Object.values(sl1.plans ?? {});
assert.equal(plans.length, run.script.lectures[1].chapters.length, "each chapter's beats kept");
assert.ok(plans.every((pl, i) => pl.kind === "beats" && pl.beats.length === run.script.lectures[1].chapters[i].beats.length && pl.beats[0].paragraph
  && pl.patch.length), "every chapter's beats and patch kept");
const lowered = Object.values(sl1.beats).flatMap((b) => b.ops).filter((o) => typeof o.on === "string");
assert.ok(lowered.length && lowered.every((o) => /^(w\d+|start)$/.test(o.on)), `the elements lowered on their words: ${JSON.stringify(lowered.slice(0, 3))}`);
// Strict on the current engine: every chapter's script says so, its compile keeps it, and the engine is told.
const strictLib = await import(path.resolve(here, "../lib/scenes.ts"));
const strictScript = await strictLib.engineScript(run, 1, run.scenes.look);
assert.ok(strictScript.chapters.every((c) => c.strict === true), "the director's chapters are strict on the current engine");
const strictCompiled = await strictLib.compile(run, strictScript, path.join(strictLib.scenesDir(run.id), "strict-check"), 1);
assert.ok(strictCompiled.source?.includes("self.strict_beats(True)") && !strictCompiled.errors.length, strictCompiled.errors.join("; "));
// The beats and the patch, seen and changed by hand (the Scenes tab's "Director beats and choreography"): a patch
// that does not fit is refused with why; a patch and beats saved are applied, compiled; beats can be choreographed again.
const pc = run.script.lectures[1].chapters[0].n;
const kept = sl1.plans[pc];
const stepsOf = (pl) => pl.patch.flatMap((p) => p.steps);
assert.ok(stepsOf(kept).length && stepsOf(kept).every((q) => /^w\d+$/.test(q.at)), "the patch kept with the beats, each step on a word of its line");
await assert.rejects(scenesAction(run.id, { action: "editCues", lecture: 1, chapter: pc, cues: { beats: [{ beat: 999, steps: [{ at: "w0", do: "enter", op: 0 }] }] } }), /cannot be used/);
const firstOp = kept.beats.find((x) => x.do.length);
await assert.rejects(scenesAction(run.id, { action: "editCues", lecture: 1, chapter: pc, cues: { beats: [{ beat: firstOp.beat, steps: [], look: [{ op: 0, nodes: [] }] }] } }), /cannot change "nodes"/);
const entersOnly = { beats: kept.patch.map((p) => ({ beat: p.beat, steps: p.steps.filter((q) => q.do === "enter" || q.do === "show") })) };
const enters = entersOnly.beats.flatMap((p) => p.steps);
await scenesAction(run.id, { action: "editCues", lecture: 1, chapter: pc, cues: entersOnly });
run = await slow(run.id, (r) => r.scenes.status === "running" || r.scenes.lectures[1].status === "running");
assert.equal(stepsOf(run.scenes.lectures[1].plans[pc]).length, enters.length, "the patch saved");
assert.equal(run.scenes.lectures[1].compiles[pc].status, "done", JSON.stringify(run.scenes.lectures[1].compiles[pc]));
const edited = structuredClone({ beats: run.scenes.lectures[1].plans[pc].beats });
edited.beats[0].about = "edited by hand";
await scenesAction(run.id, { action: "editPlan", lecture: 1, chapter: pc, plan: edited });
run = await slow(run.id, (r) => r.scenes.status === "running" || r.scenes.lectures[1].status === "running");
assert.equal(run.scenes.lectures[1].plans[pc].beats[0].about, "edited by hand", "the beats saved");
assert.equal(run.scenes.lectures[1].beats[edited.beats[0].beat].about, "edited by hand", "and applied");
assert.equal(stepsOf(run.scenes.lectures[1].plans[pc]).length, enters.length, "with the patch's steps that still fit them");
// The lowering of every step (lib/director.ts), on the current engine: a label shown on a later line held back and
// brought on by a `label`, its note, a light held until a word (shade with hold, then unshade), a hide (an
// unlabel), a focus held (focus, then unfocus), a pulse on a node (point), a look merged and content refused.
{
  const d = await import(path.resolve(here, "../lib/director.ts"));
  const plan = { elements: [{ id: "bank", op: { op: "picture", generate: "a river bank", labels: ["water", "soil"] } },
    { id: "chain", op: { op: "diagram", id: "chain", nodes: [{ id: "food", label: "Food" }, { id: "towns", label: "Towns" }], edges: [["food", "towns"]] } }],
    scenes: [{ id: "S1", beats: [1, 2, 3], uses: ["bank"] }, { id: "S2", beats: [4, 5], uses: ["chain"] }] };
  const words = new Map([1, 2, 3, 4, 5].map((n) => [n, d.estimatedWords(n, "one two three four five six seven eight")]));
  const acts = new Map();
  for (const el of plan.elements) {
    const may = d.actsFor(el, "current");
    acts.set(el.id, may.element);
    for (const p of d.partsOf(el)) acts.set(p.ref, may.parts);
  }
  const choreo = { elements: [
    { id: "bank", look: { move: "drift" }, timeline: [{ at: "b1.w1", do: "enter" }, { at: "b1.w2", do: "show", part: "water", note: "the flood" },
      { at: "b2.w3", do: "show", part: "soil" }, { at: "b2.w4", do: "light", part: "soil", until: "b3.w5" }, { at: "b3.w2", do: "hide", part: "water" }] },
    { id: "chain", look: { flow: true }, timeline: [{ at: "b4.w0", do: "enter" }, { at: "b4.w3", do: "show", part: "towns" },
      { at: "b5.w1", do: "focus", part: "towns", until: "b5.w6" }, { at: "b5.w3", do: "pulse", part: "food" }] }] };
  const steps = d.flatSteps(choreo, new Set(acts.keys()));
  const read = d.readCues({ cues: steps.cues }, { words, beats: new Set([1, 2, 3, 4, 5]), acts, scenes: new Set(["S1", "S2"]) });
  assert.deepEqual([...steps.dropped, ...read.dropped], [], "every step read");
  const { ops } = d.lowerPlan(plan, read.cues, words, "current", steps.looks);
  const pic = ops.get(1).find((o) => o.op === "picture");
  assert.deepEqual([pic.hold, pic.sides, pic.notes, pic.move], [["soil"], undefined, { water: "the flood" }, "drift"], JSON.stringify(pic));
  assert.deepEqual(ops.get(2).map((o) => [o.op, o.part, o.hold, o.on]), [["label", "soil", undefined, "w3"], ["shade", "soil", true, "w4"]], JSON.stringify(ops.get(2)));
  assert.deepEqual(ops.get(3).map((o) => [o.op, o.on]), [["unlabel", "w2"], ["unshade", "w5"]], JSON.stringify(ops.get(3)));
  assert.equal(ops.get(4).find((o) => o.op === "diagram").flow, true, "a diagram's look merged");
  assert.deepEqual(ops.get(5).map((o) => [o.op, o.on]), [["focus", "w1"], ["point", "w3"], ["unfocus", "w6"]], JSON.stringify(ops.get(5)));
  // The choreographer's JSON round-trips through the cues.
  const back = d.choreographyOf(plan, read.cues, steps.looks);
  assert.deepEqual(back.elements.map((e) => e.timeline.map((q) => q.do).join(",")), ["enter,show,show,light,hide", "enter,show,focus,pulse"], JSON.stringify(back));
  assert.equal(back.elements[0].timeline[3].until, "b3.w5", "a light's until kept");
  assert.ok(d.flatSteps({ elements: [{ id: "bank", timeline: [], look: { labels: ["x"] } }] }).dropped.length === 1, "a look cannot change content");
  // At most two main pictures at once: a picture and a timeline cued on one line stay together; a third comes on as
  // the next line begins.
  const three = { elements: [plan.elements[0], { id: "dates", op: { op: "timeline", events: [["1500", "A"], ["1600", "B"]] } },
    { id: "two", op: { op: "compare", columns: [{ title: "A", points: ["x"] }, { title: "B", points: ["y"] }] } }],
    scenes: [{ id: "S1", beats: [1, 2, 3], uses: ["bank", "dates", "two"] }] };
  const threeCues = d.readCues({ cues: [{ at: "b1.w1", ref: "bank", act: "enter" }, { at: "b1.w4", ref: "dates", act: "enter" },
    { at: "b1.w6", ref: "two", act: "enter" }] },
    { words, beats: new Set([1, 2, 3]), acts: new Map([["bank", ["enter"]], ["dates", ["enter"]], ["two", ["enter"]]]), scenes: new Set(["S1"]) }).cues;
  const lowered2 = d.lowerPlan(three, threeCues, words, "current");
  assert.deepEqual([lowered2.ops.get(1).map((o) => o.op), lowered2.ops.get(2).map((o) => [o.op, o.on])], [["picture", "timeline"], [["compare", "start"]]],
    JSON.stringify([...lowered2.ops]));
  // The compiler mends a chapter the same way, whatever wrote it: a third main picture of a line moved (to the line
  // that points into it), and in a strict chapter pointing at what is not up left out.
  const { runPython: rp2 } = await import(path.resolve(here, "../lib/manim.ts"));
  const crowd = { title: "T", chapters: [{ title: "C", strict: true, beats: [
    { say: "one two three four five six", do: [{ op: "illustration", query: "a court", labels: ["China", "Japan"], on: "w1" },
      { op: "timeline", events: [["1894", "War"], ["1905", "Russia"]], on: "w2" },
      { op: "compare", columns: [{ title: "China", points: ["Civil war"] }, { title: "Japan", points: ["Occupation"] }], on: "w3" },
      { op: "shade", part: "China", on: "w4" }] },
    { say: "one two three four five six", do: [{ op: "point", target: "Japan", on: "w2" }] },
    { say: "one two three four five six", do: [{ op: "point", target: "Civil war", on: "w2" }] },
    { say: "one two three four five six", do: [{ op: "point", target: "Occupation", on: "w2" }, { op: "shade", part: "China", on: "w3" }] }] }] };
  const mended = await rp2(["-c", "import json,sys,compile_lecture as c; s=json.load(sys.stdin); n=c._one_on_the_stage(s); print(json.dumps({'notes': n, 'ops': [[o['op'] for o in b['do']] for b in s['chapters'][0]['beats']]}))"],
    process.env.V2_ENGINE, { PYTHONPATH: process.env.V2_ENGINE }, JSON.stringify(crowd));
  const got = JSON.parse(mended.stdout.trim().split("\n").pop());
  assert.deepEqual(got.ops, [["illustration", "timeline", "shade"], ["point"], ["compare", "point"], ["point"]], JSON.stringify(got));
  assert.ok(got.notes.length === 2 && got.notes.every((x) => x.startsWith("fixed: ")), JSON.stringify(got.notes));
}
const choreoBefore = run.calls.filter((c) => /^Choreography:/.test(c.label)).length;
await scenesAction(run.id, { action: "editPlan", lecture: 1, chapter: pc, plan: edited, choreograph: true });
run = await slow(run.id, (r) => r.scenes.status === "running" || r.scenes.lectures[1].status === "running");
assert.ok(run.calls.filter((c) => /^Choreography:/.test(c.label)).length > choreoBefore, "a plan choreographed again");
assert.equal(run.scenes.lectures[1].compiles[pc].status, "done", JSON.stringify(run.scenes.lectures[1].compiles[pc]));
await assert.rejects(scenesAction(run.id, { action: "editPlan", lecture: 1, chapter: pc, plan: { beats: [] } }), /show nothing/);
// One paragraph built again (the director for its beats only, then its choreography); the other beats and the voice kept.
{
  const b = await import(path.resolve(here, "../lib/beat-director.ts"));
  const before = run.scenes.lectures[1].plans[pc];
  const first = b.paragraphsOf(before.beats)[0];
  const others = before.beats.filter((x) => !first.includes(x.beat)).map((x) => JSON.stringify(x));
  await scenesAction(run.id, { action: "rebuildScene", lecture: 1, chapter: pc, scene: "P1", note: "a different picture" });
  run = await slow(run.id, (r) => r.scenes.status === "running" || r.scenes.lectures[1].status === "running");
  const rebuilt = run.scenes.lectures[1].plans[pc];
  assert.ok(run.calls.some((c) => /paragraph P1 again \(director\)/.test(c.label)), "the director asked for that paragraph only");
  assert.ok(others.every((x) => rebuilt.beats.some((y) => JSON.stringify(y) === x)), "the other beats as they were");
  assert.deepEqual(rebuilt.beats.map((x) => x.beat), run.script.lectures[1].chapters[0].beats.map((x) => x.n), "every beat still there");
  assert.equal(run.scenes.lectures[1].compiles[pc].status, "done", JSON.stringify(run.scenes.lectures[1].compiles[pc]));
  await assert.rejects(scenesAction(run.id, { action: "rebuildScene", lecture: 1, chapter: pc, scene: "P99" }), /no scene P99/);
  // A beat the compiler refuses in a directed chapter is mended by the director (told what the compiler said), not
  // by the per-beat writer.
  const bad = structuredClone({ beats: rebuilt.beats });
  const target = bad.beats[1] ?? bad.beats[0];
  target.do = [{ op: "define" }];
  await scenesAction(run.id, { action: "editPlan", lecture: 1, chapter: pc, plan: bad });
  run = await slow(run.id, (r) => r.scenes.status === "running" || r.scenes.lectures[1].status === "running");
  assert.ok(run.scenes.lectures[1].beats[target.beat].errors?.length, "the beat refused");
  const writerBefore = run.calls.filter((c) => /mend \d+ beat\(s\)$/.test(c.label)).length;
  await scenesAction(run.id, { action: "fix", lecture: 1 });
  run = await slow(run.id, (r) => r.scenes.status === "running" || r.scenes.lectures[1].status === "running");
  const mend = run.calls.find((c) => /mend 1 beat\(s\) \(director\)/.test(c.label));
  assert.ok(mend && mend.prompt.user.some((p) => p.key === "problems" && /define/.test(p.text)), "the director told what the compiler refused");
  assert.equal(run.calls.filter((c) => /mend \d+ beat\(s\)$/.test(c.label)).length, writerBefore, "never the per-beat writer in a directed chapter");
  assert.ok(!run.scenes.lectures[1].beats[target.beat].errors?.length, "the beat mended");
  assert.equal(run.scenes.lectures[1].compiles[pc].status, "done", JSON.stringify(run.scenes.lectures[1].compiles[pc]));
}
// The scene writer of before (director off): one call a chapter writing each beat's do, then the word timing call.
await scenesAction(run.id, { action: "engine", engine: "current", director: false });
await scenesAction(run.id, { action: "build", scope: "lecture", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.equal(run.scenes.lectures[1].status, "done", run.scenes.lectures[1].error);
const scenesCall = run.calls.find((c) => c.step === "scenes" && /^Scenes: lecture 1, chapter \d+$/.test(c.label));
const offAll = scenesCall.prompt.system.find((p) => p.key === "off");
assert.ok(scenesCall.prompt.system.some((p) => p.key === "v2-anchors" && /EVERY VISUAL LANDS ON ITS WORDS/.test(p.text)), "the scene writer is told to anchor every visual");
// Voice first on the current engine: each chapter spoken first, then a timing call of its own (the stand-in here)
// puts every picture and part on its word ("w7", or "start"), and the compiler takes them.
const timingCalls = run.calls.filter((c) => c.step === "scenes" && /^Time the pictures to the words/.test(c.label));
assert.equal(timingCalls.length, run.script.lectures[1].chapters.length, "one word timing call a chapter");
assert.ok(timingCalls.every((c) => c.status === "done" && c.prompt.system.some((p) => p.key === "word-timing")
  && c.checks.some((k) => k.name === "Words" && k.result !== "fail")), "each timed, its words checked");
assert.ok(!scenesCall.prompt.user.some((p) => /w0 /.test(p.text)), "the current scene writer is not shown word numbers");
const anchored = Object.values(run.scenes.lectures[1].beats).flatMap((b) => b.ops).filter((o) => typeof o.on === "string");
assert.ok(anchored.length && anchored.every((o) => /^(w\d+|start)$/.test(o.on)), `the pictures on their words: ${JSON.stringify(anchored.slice(0, 3))}`);
assert.ok(offAll && /AI illustrations/.test(offAll.text) && !/Diagrams/.test(offAll.text), "the kinds switched off are named as such");
await scenesAction(run.id, { action: "engine", engine: "current", director: true });
// A beat's kinds of its own, its operations by hand, one beat built again.
const firstBeat = sceneBeats[0].n;
await scenesAction(run.id, { action: "beatKinds", lecture: 1, beat: firstBeat, kinds: ["define"] });
await scenesAction(run.id, { action: "build", scope: "beat", lecture: 1, beat: firstBeat });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.ok(run.scenes.lectures[1].beats[firstBeat].ops.every((o) => ["panel", "fact", "define", "clear"].includes(o.op)), "a beat's own kinds kept");
await scenesAction(run.id, { action: "edit", lecture: 1, beat: firstBeat, ops: [{ op: "panel", title: "By hand" }, { op: "define", term: "Surplus", meaning: "More food than is needed" }] });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.ok(run.scenes.lectures[1].beats[firstBeat].edited);
await assert.rejects(scenesAction(run.id, { action: "edit", lecture: 1, beat: firstBeat, ops: "nope" }), /JSON list/);
// The Manim agent on a beat: it makes a picture, previews its code (rendered), looks, finishes; the beat is its figure.
await assert.rejects(scenesAction(run.id, { action: "agent", lecture: 1, beat: firstBeat }), /switched off/);
await scenesAction(run.id, { action: "beatKinds", lecture: 1, beat: firstBeat, kinds: ["manim"] });
await scenesAction(run.id, { action: "agent", lecture: 1, beat: firstBeat, instruction: "show the first farmers by a river" });
run = await slow(run.id, (r) => r.scenes.status === "running", 3000);
const agentBeat = run.scenes.lectures[1].beats[firstBeat];
assert.equal(agentBeat.agent.status, "done", agentBeat.agent.error);
assert.deepEqual(agentBeat.agent.steps.map((x) => x.kind).filter((k) => k !== "think"), ["image", "check", "finish"]);
const checked = agentBeat.agent.steps.find((x) => x.kind === "check");
assert.ok(!checked.errors && !checked.still && !checked.video && !checked.ir, "the code checked, nothing rendered in the agent's loop");
const turnCalls = run.calls.filter((c) => c.step === "manim-agent" && c.api !== "image");
assert.ok(turnCalls.every((c) => !JSON.stringify(c.request ?? {}).includes("last frame")), "no frame goes back to the agent");
const madeImage = Object.values(run.scenes.agentImages[1])[0];
assert.equal(madeImage.status, "done");
assert.ok(agentBeat.ops.some((o) => o.op === "manim" && /image\("/.test(o.code)), "the beat is its figure, using the picture by name");
assert.ok(run.calls.filter((c) => c.step === "manim-agent").length >= 4, "every turn and the picture are calls");
assert.equal(run.scenes.lectures[1].compile.status, "done", JSON.stringify(run.scenes.lectures[1].compile));
assert.ok(!agentBeat.errors?.length, `the compiler takes the figure: ${agentBeat.errors}`);
await scenesAction(run.id, { action: "beatKinds", lecture: 1, beat: firstBeat, kinds: null });
// One beat rendered in its chapter, in another look: its frame and clip.
const ch1 = run.script.lectures[1].chapters[0];
const renderBeat = ch1.beats[1]?.n ?? firstBeat;
const { scenesDir } = await import(path.resolve(here, "../lib/scenes.ts"));
const irOf = (url) => JSON.parse(readFileSync(path.join(scenesDir(run.id), new URL(`http://x${url}`).searchParams.get("p"), "scene_ir.json"), "utf8"));
if (FULL) {
  await scenesAction(run.id, { action: "render", lecture: 1, chapter: ch1.n, beat: renderBeat, style: "blueprint" });
  run = await slow(run.id, (r) => r.scenes.renders > 0, 3000);
  const rendered = run.scenes.lectures[1].beats[renderBeat].render;
  assert.equal(rendered.status, "done", rendered.error);
  assert.equal(rendered.style, "blueprint");
  assert.ok(rendered.ir && rendered.assets && rendered.range && rendered.frames > rendered.range[0], "playable in v1's web player: its geometry, and the beat's frames");
  assert.equal(irOf(rendered.ir).frames, rendered.frames, "the geometry is there, every frame");
}
await scenesAction(run.id, { action: "render", lecture: 1, chapter: ch1.n });
run = await slow(run.id, (r) => r.scenes.renders > 0, 3000);
const chRender = run.scenes.lectures[1].chapters[ch1.n];
assert.equal(chRender.status, "done", chRender.error);
assert.equal(chRender.beats.length, ch1.beats.length);
assert.ok(chRender.beats.every((b, i, all) => b.to >= b.from && (i === 0 || b.from > all[i - 1].from)), "each beat's frames, in order");

// The voice: a chapter with its scenes spoken (espeak-ng, offline), its words timed, its animations timed to them
// (the timing model's call, a stand-in here), and played with its narration track.
const { voiceAction, voiceOf } = await import(path.resolve(here, "../lib/voice.ts"));
const { voiceRunning, scenesKey } = await import(path.resolve(here, "../lib/voice-engines.ts"));
await voiceAction(run.id, { action: "settings", engine: "espeak", pace: "natural" });
await voiceAction(run.id, { action: "speak", lecture: 1, chapter: ch1.n });
run = await slow(run.id, (r) => voiceRunning(r), 3000);
let cv = run.voice.lectures[1][ch1.n];
assert.equal(cv.status, "done", cv.error);
assert.equal(cv.mode, "espeak:en-gb");
assert.ok(cv.lines.length >= ch1.beats.length && cv.lines.every((l) => l.url && l.seconds > 0), "every line spoken, with its audio and length");
assert.ok(cv.lines.filter((l) => l.beat !== undefined).length >= ch1.beats.length, "each beat's line found under its beat");
assert.ok(cv.lines.every((l) => l.words?.length && l.wordsFrom), "when each word is said (estimated here: no Whisper download)");
assert.ok(cv.cues.length && cv.cues.some((c) => c.cues?.length), "animations timed to the words");
const timingCall = run.calls.find((c) => c.id === cv.calls.find((id) => run.calls.find((x) => x.id === id)?.tool));
assert.ok(timingCall && timingCall.step === "voice" && /time the animations/i.test(timingCall.prompt.system[0].text), "the timing call, with align_cues's prompt");
assert.ok(run.calls.some((c) => c.step === "voice" && c.api === "voice"), "the voice as a call, for the costs");
assert.ok(cv.audio && cv.ir && cv.frames > 0 && cv.beats.length === ch1.beats.length, "played with its narration");
assert.ok(cv.beats.every((b, i, all) => b.to >= b.from && (i === 0 || b.start > all[i - 1].start)), "each beat where its line is said");
const fileOf = (url) => path.join(scenesDir(run.id), new URL(`http://x${url}`).searchParams.get("p"));
const { duration: lengthOf } = await import(path.resolve(here, "../lib/scenes.ts"));
const track = await lengthOf(fileOf(cv.audio));
assert.ok(Math.abs(track - cv.frames / cv.fps) < 1.5, `the narration as long as the scene (${track} s, ${cv.frames / cv.fps} s)`);
assert.ok(readFileSync(path.join(fileOf(cv.ir), "..", "aligned.py"), "utf8").includes("cues="), "the times written into the scene");
const { rangeOf } = await import(path.resolve(here, "../lib/ranges.ts"));
assert.deepEqual(rangeOf("bytes=100-199", 1000), [100, 199], "the narration served in ranges (the player seeks it)");
assert.deepEqual(rangeOf("bytes=900-", 1000), [900, 999]);
assert.deepEqual(rangeOf("bytes=-300", 1000), [700, 999]);
assert.equal(rangeOf("bytes=2000-", 1000), "bad");
assert.equal(rangeOf(null, 1000), undefined);
assert.equal(cv.scenesKey, scenesKey(run, 1, ch1.n), "made from the scenes as they are");
// Spoken again: every line found spoken (nothing paid twice).
await voiceAction(run.id, { action: "speak", lecture: 1, chapter: ch1.n });
run = await slow(run.id, (r) => voiceRunning(r), 3000);
cv = run.voice.lectures[1][ch1.n];
assert.equal(cv.status, "done", cv.error);
assert.equal(cv.cost.newLines, 0, "the lines found spoken already");
assert.equal(voiceOf(run).settings.engine, "espeak");

// Questions on the video (the Questions tab): written for the voiced chapter (stand-in model), each with four options
// in English and Hindi, a right answer, its beats, and where in the narrated video they play.
const { questionsAction, readQuestions, chapterSource } = await import(path.resolve(here, "../lib/questions.ts"));
const qRunning = (r) => Object.values(r.questions?.lectures ?? {}).some((l) => Object.values(l).some((c) => c.status === "running"));
await questionsAction(run.id, { action: "generate", lecture: 1, chapter: ch1.n, count: 4 });
run = await slow(run.id, qRunning, 1000);
const cq = run.questions.lectures[1][ch1.n];
assert.equal(cq.status, "done", cq.error);
assert.equal(cq.source, "voice", "times from the narrated chapter");
assert.ok(cq.questions.length >= 2 && cq.questions.every((q) => q.en.options.length === 4 && q.hi.options.length === 4
  && q.answer >= 0 && q.answer < 4 && q.beats.length && q.en.question && /[\u0900-\u097F]/.test(q.hi.question)), "four options, both languages, a right answer, its beats");
assert.ok(cq.questions.every((q) => q.at && q.at.start >= 0 && q.at.end <= cv.frames / cv.fps + 0.5 && q.at.end >= q.at.start), "where it is taught, in the video");
assert.ok(run.calls.some((c) => c.id === cq.calls[0] && c.step === "questions" && /judgment/i.test(c.prompt.system[0].text)), "the question writer's call");
const qSrc = chapterSource(run, 1, ch1.n);
const qBad = readQuestions({ questions: [
  { skill: "apply", beats: [qSrc.beats[0].n], answer: 1, en: { question: "Q?", options: ["a", "b", "c", "d"], explanation: "" }, hi: { question: "प्र?", options: ["क", "ख", "ग", "घ"], explanation: "" } },
  { skill: "apply", beats: [qSrc.beats[0].n], answer: 0, en: { question: "Q?", options: ["a", "a", "c", "d"], explanation: "" }, hi: { question: "प्र?", options: ["क", "ख", "ग", "घ"], explanation: "" } },
  { skill: "apply", beats: [999], answer: 0, en: { question: "Q?", options: ["a", "b", "c", "d"], explanation: "" }, hi: { question: "प्र?", options: ["क", "ख", "ग", "घ"], explanation: "" } },
  { skill: "apply", beats: [qSrc.beats[0].n], answer: 7, en: { question: "Q?", options: ["a", "b", "c", "d"], explanation: "" }, hi: { question: "प्र?", options: ["क", "ख", "ग", "घ"], explanation: "" } },
] }, qSrc, "t");
assert.equal(qBad.questions.length, 1, "repeated options, a beat not in the chapter and no right answer are left out");
assert.equal(qBad.dropped.length, 3);
const qSame = readQuestions({ questions: Array.from({ length: 4 }, () => ({ skill: "infer", beats: [qSrc.beats[0].n], answer: 2,
  en: { question: "Q?", options: ["a", "b", "c", "d"], explanation: "" }, hi: { question: "प्र?", options: ["क", "ख", "ग", "घ"], explanation: "" } })) }, qSrc, "s");
assert.deepEqual(qSame.questions.map((q) => q.answer).sort(), [0, 1, 2, 3], "the right answers spread over the four positions");
assert.ok(qSame.questions.every((q) => q.en.options[q.answer] === "c" && q.hi.options[q.answer] === "ग"), "the options turned round together, in both languages");
await questionsAction(run.id, { action: "reset", lecture: 1, chapter: ch1.n });
console.log(`questions: chapter ${ch1.n}, ${cq.questions.length} written, each with its time in the video`);

await voiceAction(run.id, { action: "reset", lecture: 1, chapter: ch1.n });
assert.ok(!(await loadRun(run.id)).voice.lectures[1][ch1.n], "the chapter's voice forgotten");
await assert.rejects(voiceAction(run.id, { action: "speak", lecture: 99 }), /no chapter with its scenes/);
console.log(`voice: chapter ${ch1.n}, ${cv.lines.length} lines, ${cv.cues.filter((c) => c.cues).length} beats timed, ${(cv.frames / cv.fps).toFixed(1)} s`);

// The chapter's beat script edited by hand on the Voice tab and tried (spoken and played apart), then applied.
const { chapterScript } = await import(path.resolve(here, "../lib/voice.ts"));
const base = await chapterScript(run, 1, ch1.n);
// The scene writer's instructions to give a chat model by hand: v1's, word for word, the whole chapter's shape, Manim as code.
const { editInstructions } = await import(path.resolve(here, "../lib/voice.ts"));
const { V1_LECTURE: V1L, V1_MANIM_RULES } = await import(path.resolve(here, "../lib/prompts/v1-lecture.ts"));
const hand = await editInstructions(run, 1);
for (const key of Object.keys(V1L).filter((k) => k !== "beat")) assert.ok(hand.includes(V1L[key].join("\n").trim()), `the copy has v1's ${key} section`);
assert.ok(!/at most four operations/.test(hand), "the copy has no limit to a beat's operations either");
assert.ok(hand.includes(V1_MANIM_RULES.join("\n").trim()) && !/write_scenes/.test(hand), "Manim written as code; no tool named");
assert.ok(/THE ANSWER: the whole chapter's beat script as ONE JSON object/.test(hand) && /"beat": <its number, as given>/.test(hand));
// With it, what the scene writer is told of the lecture: its chapters, the region, its figures by id, each beat's plan.
const { editContext } = await import(path.resolve(here, "../lib/voice.ts"));
const { lectureFigures: lf } = await import(path.resolve(here, "../lib/script-figures.ts"));
const ctx = editContext(run, 1, ch1.n);
assert.ok(lf(run, 1).every((f) => ctx.includes(`  ${f.id}: `)), "every figure of the lecture, by id");
assert.ok(ch1.beats.every((b) => ctx.includes(`  #${b.n} "`)) && /on screen: /.test(ctx) && /<- the chapter to write/.test(ctx), "each beat as the script planned it");
assert.equal(base.chapter.beats.length, ch1.beats.length);
assert.deepEqual(base.chapter.beats.map((b) => b.beat), ch1.beats.map((b) => b.n), "each beat with its number");
assert.ok(base.chapter.beats.every((b) => typeof b.say === "string" && Array.isArray(b.do)) && base.style, "the compiler's own script");
const edit = JSON.parse(JSON.stringify(base));
edit.chapter.beats[0].do = [{ op: "panel", title: "Tried by hand" }, { op: "fact", text: "An edit, tried" }];
edit.chapter.beats[0].pause = 1;
edit.chapter.beats[1].say = "These are new words, said only in the trial.";
await assert.rejects(voiceAction(run.id, { action: "try", lecture: 1, chapter: ch1.n, script: { beats: [] } }), /needs "chapter"/);
await assert.rejects(voiceAction(run.id, { action: "try", lecture: 1, chapter: ch1.n, script: { chapter: { title: "x", beats: [{ say: "s", do: [{ title: "no op" }] }] } } }), /each with "op"/);
if (FULL) {
await voiceAction(run.id, { action: "speak", lecture: 1, chapter: ch1.n });
run = await slow(run.id, (r) => voiceRunning(r), 3000);
const realBefore = run.voice.lectures[1][ch1.n].ir;
await voiceAction(run.id, { action: "try", lecture: 1, chapter: ch1.n, script: edit });
run = await slow(run.id, (r) => voiceRunning(r), 3000);
const tv = run.voice.trials[1][ch1.n];
assert.equal(tv.status, "done", tv.error);
assert.ok(tv.ir && tv.audio && tv.frames > 0 && tv.beats.length === edit.chapter.beats.length, "played with its narration");
assert.ok(tv.lines.some((l) => l.text === "These are new words, said only in the trial." && l.beat === ch1.beats[1].n), "the edited words spoken, under their beat");
assert.ok(readFileSync(path.join(fileOf(tv.ir), "..", "scene.py"), "utf8").includes("Tried by hand"), "the edited visuals compiled");
assert.equal(run.voice.lectures[1][ch1.n].ir, realBefore, "the chapter's own voice untouched");
assert.deepEqual(tv.edited.chapter.beats[0].do[0], { op: "panel", title: "Tried by hand" });
// Applied: the visuals into the scenes (compiled there); the edited words are the transcript's, so not applied.
await voiceAction(run.id, { action: "apply", lecture: 1, chapter: ch1.n, script: edit });
run = await slow(run.id, (r) => r.scenes.status === "running" || voiceRunning(r), 3000);
const appliedBeat = run.scenes.lectures[1].beats[ch1.beats[0].n];
assert.deepEqual(appliedBeat.ops.map((o) => o.op), ["panel", "fact"]);
assert.ok(appliedBeat.edited && appliedBeat.pause === 1, "edited by hand, with its pause");
assert.ok(run.voice.trials[1][ch1.n].applied.notes.some((x) => /transcript/.test(x)), "says the words were not applied");
assert.notEqual(run.voice.lectures[1][ch1.n].scenesKey, scenesKey(run, 1, ch1.n), "the chapter's voice is now behind its scenes");
await voiceAction(run.id, { action: "resetTrial", lecture: 1, chapter: ch1.n });
assert.ok(!(await loadRun(run.id)).voice.trials[1][ch1.n], "the trial forgotten");
}
await voiceAction(run.id, { action: "reset", lecture: 1, chapter: ch1.n });

// The Lab: every preset and every snippet compiles; an experiment from a preset is spoken, timed and played; one from a
// lecture's chapter; duplicated, renamed, removed.
{
  const { LAB_PRESETS, LAB_SNIPPETS } = await import(path.resolve(here, "../lib/lab-presets.ts"));
  const { labAction } = await import(path.resolve(here, "../lib/lab.ts"));
  const { compile: compileScript } = await import(path.resolve(here, "../lib/scenes.ts"));
  const { readChapterScript, engineScriptOf } = await import(path.resolve(here, "../lib/voice.ts"));
  const all = { region: null, chapter: { title: "Snippets", beats: LAB_SNIPPETS.map((x) => ({ say: x.say, do: [x.do] })) } };
  const presets = [...LAB_PRESETS.map((p) => [p.id, p.script]), ["snippets", all]];
  await atOnce(FULL ? presets : [...presets.slice(0, 2), presets.at(-1)], 4, async ([name, script]) => {
    const c = await compileScript(run, await engineScriptOf(run, 1, readChapterScript(script)), path.join(scenesDir(run.id), "lab-check", name));
    assert.ok(c.source && !c.errors.length, `the Lab's ${name} compiles: ${c.errors.join("; ")}`);
    assert.deepEqual(c.warnings.filter((w) => /left out|unknown/i.test(w)), [], `the Lab's ${name}: nothing left out`);
  });
  // The motion engine (beta): every motion preset and snippet compiles on it, with nothing left out.
  const { LAB_MOTION_PRESETS, LAB_MOTION_SNIPPETS } = await import(path.resolve(here, "../lib/lab-presets.ts"));
  const motionAll = { engine: "motion", look: "paper", region: null, chapter: { title: "Motion snippets",
    beats: [{ say: "Japan, Italy and Germany.", do: [{ op: "chart", items: [["Japan", 204], ["Italy", 138], ["Germany", 65]] }] },
      ...LAB_MOTION_SNIPPETS.map((x) => ({ say: x.say, do: [x.do] }))] } };
  const motionPresets = [...LAB_MOTION_PRESETS.map((p) => [p.id, p.script]), ["motion-snippets", motionAll]];
  // By default every eighth preset and the snippets (each template is in the snippets).
  await atOnce(FULL ? motionPresets : [...motionPresets.filter((_, i) => i % 8 === 0), motionPresets.at(-1)], 4, async ([name, script]) => {
    const c = await compileScript(run, await engineScriptOf(run, 1, readChapterScript(script)), path.join(scenesDir(run.id), "lab-check", name));
    assert.ok(c.source && !c.errors.length, `the Lab's ${name} compiles on the motion engine: ${c.errors.join("; ")}`);
    assert.ok(c.source.includes("(MotionLecture)") && c.source.includes("from motion import *"), `the Lab's ${name} is a motion scene`);
    assert.deepEqual(c.warnings.filter((w) => /left out|unknown|is not one of/i.test(w) && !/no reusable illustration|picture/i.test(w)), [],
      `the Lab's ${name}: nothing left out`);
  });
  await assert.rejects(Promise.resolve().then(() => readChapterScript({ engine: "beta", chapter: { title: "x", beats: [{ say: "x" }] } })), /"engine" is "motion"/);
  const added = await labAction(run.id, { action: "add", preset: "diagram-build" });
  assert.equal(added.name, "Diagram built over beats");
  let lv;
  if (FULL) {
  await labAction(run.id, { action: "try", id: added.id });
  run = await slow(run.id, (r) => voiceRunning(r), 3000);
  lv = run.lab.items.find((i) => i.id === added.id).result;
  assert.equal(lv.status, "done", lv.error);
  assert.ok(lv.ir && lv.audio && lv.frames > 0 && lv.beats.length === 4, "the experiment played with its narration, its four beats placed");
  assert.ok(lv.cues.some((c) => c.cues?.length), "its animations timed to the words");
  assert.ok(lv.lines.filter((l) => l.beat !== undefined).length === 4, "each line under its beat");
  assert.ok(fileOf(lv.ir).includes(`${path.sep}lab${path.sep}${added.id}`), "its files the Lab's own");
  assert.ok(run.calls.some((c) => /the Lab's "Diagram built over beats"/.test(c.label)), "its calls named for it");
  }
  const fromChapter = await labAction(run.id, { action: "add", lecture: 1, chapter: ch1.n });
  assert.ok(fromChapter.script.chapter.beats.length === ch1.beats.length && fromChapter.script.chapter.beats.every((b) => b.beat === undefined), "a lecture's chapter, its beats the experiment's own");
  // A motion experiment: spoken, timed and played on the motion engine; a lecture's chapter added in a motion look.
  // The Lab is the current engine's: a motion preset is not one of its presets; a lecture's chapter comes on it as it is.
  await assert.rejects(labAction(run.id, { action: "add", preset: "m-columns" }), /no preset/);
  const inMotion = await labAction(run.id, { action: "add", lecture: 1, chapter: ch1.n });
  assert.ok(!inMotion.script.engine, "a lecture's chapter, on the current engine");
  // Every primitive at once (lib/primitives.ts), checked by compiling it only: nothing refused.
  const every = await labAction(run.id, { action: "add", every: true });
  assert.ok(every.script.chapter.beats.length >= 30, "a beat for each primitive");
  const checkedLab = await labAction(run.id, { action: "check", id: every.id });
  assert.ok(checkedLab.checked.ok, `every primitive compiles: ${checkedLab.checked.errors.join("; ")}`);
  assert.deepEqual(checkedLab.checked.warnings.filter((w) => /left out|no such op/i.test(w)), [], "nothing left out");
  for (const i of [inMotion, every]) await labAction(run.id, { action: "remove", id: i.id });
  const copy = await labAction(run.id, { action: "duplicate", id: added.id });
  assert.ok(!copy.result && copy.name.endsWith("(copy)"));
  await labAction(run.id, { action: "save", id: copy.id, name: "Variant", script: { chapter: { title: "V", beats: [{ say: "One beat.", do: [{ op: "fact", text: "a variant" }] }] } } });
  run = await loadRun(run.id);
  assert.equal(run.lab.items.find((i) => i.id === copy.id).name, "Variant");
  await assert.rejects(labAction(run.id, { action: "save", id: copy.id, script: { beats: [] } }), /needs "chapter"/);
  for (const i of [copy, fromChapter, added]) await labAction(run.id, { action: "remove", id: i.id });
  assert.equal((await loadRun(run.id)).lab.items.length, 0, "removed");
  console.log(`lab: ${FULL ? LAB_PRESETS.length : 2} presets and ${LAB_SNIPPETS.length} snippets compile` +
    (lv ? `; an experiment played in ${(lv.frames / lv.fps).toFixed(1)} s` : ""));
  console.log(`motion presets: ${FULL ? LAB_MOTION_PRESETS.length : Math.ceil(LAB_MOTION_PRESETS.length / 8)} and ${LAB_MOTION_SNIPPETS.length} snippets compile on the motion engine`);
}

// A chapter's own kinds: its beats built with only those (a beat's own still wins).
const kc = run.script.lectures[1].chapters[0];
await scenesAction(run.id, { action: "chapterKinds", lecture: 1, chapter: kc.n, kinds: ["define"] });
await scenesAction(run.id, { action: "build", scope: "chapter", lecture: 1, chapter: kc.n });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.ok(kc.beats.every((b) => run.scenes.lectures[1].beats[b.n].ops.every((o) => ["panel", "fact", "define", "clear"].includes(o.op))), "only the chapter's kinds");
const kcCall = run.calls.filter((c) => c.step === "scenes" && /^Scenes: .*chapter/.test(c.label)).at(-1);
const offPart = kcCall.prompt.system.find((p) => p.key === "off");
assert.ok(offPart && /Diagrams/.test(offPart.text) && !/Definitions/.test(offPart.text), "the kinds the chapter may not use are named as switched off");
// The scene writer's instructions (the per-beat writer, director off) are v1's, word for word, in v1's order; the
// subject's guidance as v1 tells it. (The director's prompt is its own: checked above.)
const { V1_LECTURE, V1_MANIM_PLAN } = await import(path.resolve(here, "../lib/prompts/v1-lecture.ts"));
const writerCall = run.calls.filter((c) => c.step === "scenes" && /^Scenes: lecture \d+, chapter \d+$/.test(c.label)).at(-1);
assert.ok(writerCall, "a call of the per-beat scene writer");
const sysText = render(writerCall.prompt.system);
for (const key of Object.keys(V1_LECTURE).filter((k) => k !== "beat")) assert.ok(sysText.includes(V1_LECTURE[key].join("\n").trim()), `v1's ${key} section, verbatim`);
// No limit to a beat's operations by default: v1's "at most four operations" is taken out, the rest of its words kept.
assert.ok(!/at most four operations/.test(sysText) && sysText.includes(V1_LECTURE.beat.join("\n").replace(", at most four operations.", ".").trim()), "no limit to a beat's operations");
assert.ok(writerCall.prompt.system.some((p) => p.key === "pace" && /no limit to the operations on a beat/.test(p.text)));
const { scenesPrompt: sp } = await import(path.resolve(here, "../lib/prompts/scenes.ts"));
const limited = render(sp({ lecture: { n: 1, title: "" }, look: "", kinds: [], labels: {}, chapters: [], beats: [], figures: [], ask: { what: "lecture" },
  pace: { maxOps: 6 } }).system);
assert.ok(/at most 6 operations\./.test(limited) && !/at most four operations/.test(limited), "a limit chosen is put in its place");
assert.ok(sysText.includes(V1_MANIM_PLAN.join("\n").trim()), "v1's Manim plan rules (the agent builds the figures)");
assert.ok(kcCall.prompt.system.some((p) => p.key === "subject" && /^SUBJECT\. This is a /.test(p.text)), "the subject, as v1 tells it");
await scenesAction(run.id, { action: "chapterKinds", lecture: 1, chapter: kc.n, kinds: null });
assert.ok(!(await loadRun(run.id)).scenes.lectures[1].chapterKinds?.[kc.n]);

// A gallery whose AI pictures cannot be made: the engine leaves it out, and the beat, the compile and a render say
// which pictures and why (here: the image model is off).
const galleryBeat = run.script.lectures[1].chapters[0].beats[0].n;
const gallery = [{ op: "picture", title: "Rocks", items: [{ generate: "a piece of granite", caption: "granite" }, { generate: "a piece of basalt", caption: "basalt" }] }];
await scenesAction(run.id, { action: "beatKinds", lecture: 1, beat: galleryBeat, kinds: ["gallery", "illustration"] });
process.env.PANIM_IMAGES = "0";
await scenesAction(run.id, { action: "edit", lecture: 1, beat: galleryBeat, ops: gallery });
run = await slow(run.id, (r) => r.scenes.status === "running", 3000);
let gb = run.scenes.lectures[1].beats[galleryBeat];
assert.deepEqual(gb.missing?.map((m) => m.what).sort(), ["a piece of basalt", "a piece of granite"], JSON.stringify(run.scenes.lectures[1].compile));
assert.ok(gb.missing.every((m) => /pictures are off/.test(m.error)), "why: the image model is off");
assert.ok(gb.pictures.length === 2 && gb.pictures.every((x) => x.status === "failed" && x.error), "each picture shown as not made, with why");
assert.equal(run.scenes.lectures[1].compile.missing.length, 2);
if (FULL) {
  await scenesAction(run.id, { action: "render", lecture: 1, chapter: run.script.lectures[1].chapters[0].n, beat: galleryBeat });
  run = await slow(run.id, (r) => r.scenes.renders > 0, 3000);
  assert.equal(run.scenes.lectures[1].beats[galleryBeat].render.missing?.length, 2, "the render says what it left out");
}
delete process.env.PANIM_IMAGES;
await scenesAction(run.id, { action: "compile", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running", 3000);
gb = run.scenes.lectures[1].beats[galleryBeat];
assert.ok(!gb.missing?.length, "made once the image model is on");
assert.deepEqual(gb.pictures.map((x) => x.role), ["in a gallery", "in a gallery"]);
assert.ok(gb.pictures.every((x) => ["made", "cached"].includes(x.status) && x.url && x.prompt), "each picture: its file to show, the prompt it was made from");
assert.ok(run.scenes.lectures[1].compile.images.asked >= 2);
await scenesAction(run.id, { action: "beatKinds", lecture: 1, beat: galleryBeat, kinds: null });

// Pictures made before: the decision model (Jev; a stand-in here) is asked whether one is the picture asked for now.
// A new person is drawn fresh; the same person in another moment is drawn anew to match the first (its reference).
const who = `Zorvan${Date.now().toString(36)}`;
const [pb1, pb2] = run.script.lectures[1].chapters[0].beats.slice(0, 2).map((b) => b.n);
for (const b of [pb1, pb2]) await scenesAction(run.id, { action: "beatKinds", lecture: 1, beat: b, kinds: ["illustration"] });
await scenesAction(run.id, { action: "edit", lecture: 1, beat: pb1, ops: [{ op: "picture", generate: `King ${who} of the river cities, seated on a stone throne` }] });
run = await slow(run.id, (r) => r.scenes.status === "running", 3000);
await scenesAction(run.id, { action: "edit", lecture: 1, beat: pb2, ops: [{ op: "picture", generate: `King ${who} of the river cities, riding a bullock cart to the market` }] });
run = await slow(run.id, (r) => r.scenes.status === "running", 3000);
const matched = run.scenes.lectures[1].beats[pb2].pictures?.find((x) => x.what.includes("bullock"));
assert.ok(matched?.decision, JSON.stringify(run.scenes.lectures[1].beats[pb2].pictures));
assert.equal(matched.decision.action, "match", JSON.stringify(matched.decision));
assert.ok(matched.decision.candidates.some((c) => c.what.includes("throne")) && matched.decision.pickedUrl, "asked about the throne picture, and chose it");
const judgeCall = run.calls.find((c) => c.id === matched.decision.call);
assert.ok(judgeCall && judgeCall.api === "decisions" && judgeCall.step === "scenes" && /throne/.test(render(judgeCall.prompt.user)), "the decision, as a call, with the pictures it was shown");
assert.ok(Object.keys(judgeCall.tool.use.criteria).includes("fresh"));
// Compiled again: the answer is kept, nothing asked again.
const decisionsBefore = run.calls.filter((c) => c.api === "decisions" && c.step === "scenes").length;
await scenesAction(run.id, { action: "compile", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running", 3000);
assert.equal(run.calls.filter((c) => c.api === "decisions" && c.step === "scenes").length, decisionsBefore, "kept, not asked again");
assert.equal(run.scenes.lectures[1].beats[pb2].pictures.find((x) => x.what.includes("bullock")).decision.askedNow, false);
for (const b of [pb1, pb2]) await scenesAction(run.id, { action: "beatKinds", lecture: 1, beat: b, kinds: null });

// Reset: a chapter's scenes, then the lecture's.
const resetCh = run.script.lectures[1].chapters[0];
await scenesAction(run.id, { action: "reset", lecture: 1, chapter: resetCh.n });
run = await loadRun(run.id);
assert.ok(resetCh.beats.every((b) => !run.scenes.lectures[1].beats[b.n]?.ops.length), "the chapter's beats have no visuals");
assert.ok(!run.scenes.lectures[1].chapters?.[resetCh.n] && !run.scenes.lectures[1].compile, "its render and the compile are gone");
await scenesAction(run.id, { action: "reset", lecture: 1 });
run = await loadRun(run.id);
assert.equal(run.scenes.lectures[1].status, "waiting");
assert.ok(!run.scenes.agentImages?.[1], "the agent's pictures are gone with the lecture");
await assert.rejects(scenesAction(run.id, { action: "reset", lecture: 1, chapter: 99 }), /no chapter 99/);
await scenesAction(run.id, { action: "build", scope: "lecture", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running");

// The motion engine (beta) in the Scenes tab: a lecture built with its templates, compiled and rendered on it, its
// chapters tried on it in the Voice tab; then back to the current engine (which leaves the templates out).
const { engineScript, compile: compileMotion } = await import(path.resolve(here, "../lib/scenes.ts"));
await assert.rejects(scenesAction(run.id, { action: "engine", engine: "motion", look: "pastel-dream" }), /motion look is one of/);
await scenesAction(run.id, { action: "engine", engine: "motion", look: "newsroom", timeline: "ribbon" });
run = await loadRun(run.id);
assert.ok(run.scenes.engine === "motion" && run.scenes.motion.look === "newsroom", "the engine set for the run");
await scenesAction(run.id, { action: "engine", engine: "motion", director: false });
const callsBefore = run.calls.length;
await scenesAction(run.id, { action: "build", scope: "lecture", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.equal(run.scenes.lectures[1].status, "done", run.scenes.lectures[1].error);
const motionCall = run.calls.slice(callsBefore).find((c) => c.step === "scenes");
assert.ok(/motion engine/.test(motionCall.label) && motionCall.prompt.system.some((p) => p.key === "templates" && /MOTION TEMPLATES/.test(p.text)), "the scene writer told of the motion templates");
// On the beta the scene writer is told the elements, how to use them and examples: nothing that limits its choices.
assert.ok(!motionCall.prompt.system.some((p) => ["subject", "pace", "matters"].includes(p.key) || p.key.startsWith("v1-")),
  `no subject tuning, pace or v1 rules on the beta: ${motionCall.prompt.system.map((p) => p.key).join(", ")}`);
assert.ok(["pictures", "diagrams", "timelines", "map", "manim", "examples"].every((k) => motionCall.prompt.system.some((p) => p.key === k)), "every element told");
// The voice first: each chapter spoken and aligned before its scenes, the writer given each beat's seconds, the quiet
// after it and its words by number with their times, and told to anchor by word number and pace by the clock.
assert.ok(motionCall.prompt.system.some((p) => p.key === "anchors" && /THE VOICE IS RECORDED ALREADY/.test(p.text) && /"on": "w4"/.test(p.text)),
  "the beta writer is told to anchor by word number and pace by the clock");
const voicedPart = motionCall.prompt.user.find((p) => p.key === "script");
assert.ok(/ s, then [\d.]+ s quiet: "/.test(voicedPart.text) && /words: w0 \S+ 0\.0 · w1 /.test(voicedPart.text), "each beat with its seconds, its quiet and its words by number");
const { chapterVideo } = await import(path.resolve(here, "../lib/video.ts"));
assert.ok(run.script.lectures[1].chapters.every((c) => chapterVideo(run, 1, c.n).narration?.status === "done"), "every chapter spoken first");
const mch1 = run.script.lectures[1].chapters[0];   // its beats numbered again (one sentence each)
const { pacingProblems, voicedBeats } = await import(path.resolve(here, "../lib/scenes.ts"));
const voiced1 = await voicedBeats(run, 1, mch1.n);
assert.ok(voiced1 && voiced1.size === mch1.beats.length, "every beat of the chapter has its voice");
const crowded = { beats: { [mch1.beats[0].n]: { ops: [{ op: "counter", value: "1", on: "w0" }, { op: "chart", items: [["a", 1]], on: "w0" },
  { op: "title", text: "x", on: "w0" }, { op: "venn", sets: ["a", "b"], on: "w0" }] } } };
const tight = new Map([[mch1.beats[0].n, { seconds: 2, pause: 0.5, words: [{ w: "a", t: 0 }] }]]);
assert.match((pacingProblems(crowded, tight, [mch1.beats[0].n])[mch1.beats[0].n] ?? []).join(" "), /4 new pictures in a 2 s line/, "a beat that asks too much is sent back");
assert.deepEqual(pacingProblems({ beats: { [mch1.beats[0].n]: { ops: [{ op: "counter", value: "1", on: "w0" }, { op: "stamp", text: "x", in_pause: true }] } } },
  tight, [mch1.beats[0].n]), {}, "one picture and a stamp in the quiet fit a 2 s line");
assert.ok(motionCall.prompt.system.some((p) => p.key === "shape" && /HOW TO BUILD THE JSON/.test(p.text)) &&
  motionCall.prompt.system.some((p) => p.key === "choose" && /WHICH PRIMITIVE FOR WHAT/.test(p.text)), "the beta writer is told how to build the JSON and which primitive suits what");
const motionBeats = Object.values(run.scenes.lectures[1].beats);
assert.ok(run.script.lectures[1].chapters.every((c) => c.beats.every((b) => b.lines.length === 1)), "one sentence a beat on the motion engine");
const templateBeats = motionBeats.filter((b) => b.ops.some((o) => ["title", "counter", "list", "stamp"].includes(o.op))).length;
assert.ok(templateBeats > 0, "motion templates in the beats");
assert.ok(motionBeats.every((b) => !b.errors?.length), `nothing refused on the motion engine: ${motionBeats.flatMap((b) => b.errors ?? []).join("; ")}`);
assert.equal(run.scenes.lectures[1].compile.status, "done", JSON.stringify(run.scenes.lectures[1].compile));
// The motion engine with the director: its plan, then its scenes choreographed (templates pointed at by "<id>.<part>",
// stamps), compiled with nothing refused.
await scenesAction(run.id, { action: "engine", engine: "motion", director: true });
const directedFrom = run.calls.length;
await scenesAction(run.id, { action: "build", scope: "lecture", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.equal(run.scenes.lectures[1].status, "done", run.scenes.lectures[1].error);
const motionDirector = run.calls.slice(directedFrom).find((c) => /\(director, motion engine\)$/.test(c.label));
assert.ok(motionDirector && motionDirector.prompt.system.some((p) => p.key === "templates") && !motionDirector.prompt.system.some((p) => p.key === "anchors"),
  "the motion director told of the templates, not of timing");
assert.ok(run.calls.slice(directedFrom).some((c) => /^Choreography:/.test(c.label) && !c.prompt.system.some((p) => p.key === "no-stamps")), "choreographed, stamps allowed");
assert.ok(Object.values(run.scenes.lectures[1].beats).every((b) => !b.errors?.length), "nothing refused from the director's plan on the motion engine");
assert.equal(run.scenes.lectures[1].compile.status, "done", JSON.stringify(run.scenes.lectures[1].compile));
const motionScript = await engineScript(run, 1, run.scenes.look);
assert.ok(motionScript.engine === "motion" && motionScript.look === "newsroom" && motionScript.timeline === "ribbon", "its beat script on the motion engine");
const motionCompiled = await compileMotion(run, motionScript, path.join(scenesDir(run.id), "motion-check"), 1);
assert.ok(motionCompiled.source?.includes("(MotionLecture)") && !motionCompiled.errors.length, motionCompiled.errors.join("; "));
await scenesAction(run.id, { action: "render", lecture: 1, chapter: ch1.n, beat: firstBeat });
run = await slow(run.id, (r) => r.scenes.renders > 0, 3000);
const motionRender = run.scenes.lectures[1].beats[firstBeat].render;
assert.equal(motionRender.status, "done", motionRender.error);
assert.ok(motionRender.audio && existsSync(fileOf(motionRender.audio)), "the Scenes tab's render plays with the chapter's voice (spoken first)");
assert.ok(readFileSync(path.join(fileOf(motionRender.ir), "..", "scene.py"), "utf8").includes("MotionLecture"), "rendered by the motion engine");
// The Scenes tab's chapter JSON: edited (a stamp added on its first beat), saved and the chapter rendered again.
const asBuilt = await chapterScript(run, 1, mch1.n);
asBuilt.chapter.beats[0].do = [...asBuilt.chapter.beats[0].do, { op: "stamp", text: "Edited", in_pause: true }];
await scenesAction(run.id, { action: "editChapter", lecture: 1, chapter: mch1.n, render: true, emblem: asBuilt.emblem, region: asBuilt.region,
  beats: asBuilt.chapter.beats.map((b) => ({ beat: b.beat, ops: b.do, paragraph: b.paragraph, pause: b.pause, about: b.about })) });
run = await slow(run.id, (r) => !["done", "failed"].includes(r.scenes.lectures[1].chapters?.[mch1.n]?.status), 3000);
const rerendered = run.scenes.lectures[1].chapters[mch1.n];
assert.equal(rerendered.status, "done", rerendered.error);
assert.ok(run.scenes.lectures[1].beats[mch1.beats[0].n].edited && run.scenes.lectures[1].beats[mch1.beats[0].n].ops.some((o) => o.text === "Edited"),
  "the edited chapter saved into the scenes");
assert.ok(readFileSync(path.join(fileOf(rerendered.ir), "..", "scene.py"), "utf8").includes("'Edited'"), "and rendered again with the edit");
const motionChapter = await chapterScript(run, 1, ch1.n);
assert.ok(motionChapter.engine === "motion" && motionChapter.look === "newsroom", "the Voice tab's chapter carries the engine");
assert.ok((await editInstructions(run, 1)).includes("MOTION TEMPLATES"), "the hand instructions tell of the templates");
await scenesAction(run.id, { action: "engine", engine: "current" });
run = await loadRun(run.id);
assert.ok(!run.scenes.engine && !(await engineScript(run, 1, run.scenes.look)).engine, "back on the current engine");
await scenesAction(run.id, { action: "build", scope: "lecture", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.equal(run.scenes.lectures[1].status, "done", run.scenes.lectures[1].error);
// A strict chapter (built as one piece) spoken in the Voice tab: its animations are its script's, the timing model
// is not asked.
await voiceAction(run.id, { action: "speak", lecture: 1, chapter: ch1.n });
run = await slow(run.id, (r) => voiceRunning(r), 3000);
const strictVoice = run.voice.lectures[1][ch1.n];
assert.equal(strictVoice.status, "done", strictVoice.error);
assert.ok(!strictVoice.cues?.length && !strictVoice.calls.some((id) => /^Time the animations/.test(run.calls.find((x) => x.id === id)?.label ?? "")),
  "a strict chapter is not timed again by the timing model");
console.log(`scenes (motion beta): lecture 1 built with ${templateBeats} template beats, compiled and a beat rendered`);

// Export: numbered sentences, goals with their sentences, figures with their triage; imported again as a run.
const x = exportTranscript(run);
assert.equal(x.format, "pocketanim.v2.transcript");
assert.equal(x.lectures.length, run.lectures.length);
assert.ok(x.lectures.every((l) => l.lines.length && l.lines[0].n === 1));
const fig = x.blocks.find((b) => b.id === pics[0].id).figure;
assert.equal(fig.triage.kind, "exact");
assert.equal(fig.triage.chosenBy, "user");
assert.ok(fig.generated?.prompt?.includes("NO TEXT AT ALL"), "the export carries the redraw's prompt");
assert.ok(transcriptMarkdown(run).includes("### Script") && transcriptMarkdown(run).includes("Content: `"), "the markdown is the script");
const back = await importTranscript(JSON.parse(JSON.stringify(x)), "x.json");
assert.equal(back.status, "done");
assert.deepEqual(back.script.lectures[1].chapters, run.script.lectures[1].chapters, "the scripts travel with the export");
assert.deepEqual(back.scenes.lectures[1].beats[firstBeat].ops, run.scenes.lectures[1].beats[firstBeat].ops, "the scenes travel with the export");
assert.equal(back.scenes.look.style, "chalkboard");
assert.equal(back.documentId, run.documentId, "the same book: found here, not made again");
assert.deepEqual(back.lectures.map((l) => l.text), run.lectures.map((l) => l.text));
assert.equal(back.triage.figures[pics[0].id].override, "exact");
assert.deepEqual(exportTranscript(back).lectures, x.lectures, "export, import, export: the same lectures");

// Continue: the last lecture lost is written again, and only it.
const calls = run.calls.length;
const lost = run.lectures.at(-1);
Object.assign(lost, { status: "waiting", text: undefined });
run.status = "failed";
run.steps.find((s) => s.key === "write").status = "failed";
await continueRun(run.id);
run = await wait(run.id, (r) => r.status === "running");
assert.equal(run.status, "done", run.error);
assert.equal(run.lectures.at(-1).status, "written");
assert.equal(run.lectures.length, x.lectures.length, "the same number of lectures");
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
const lastT2 = t2.lectures.at(-1).n;
Object.assign(t2.lectures.at(-1), { status: "waiting", text: undefined });
t2.status = "stopped";
await continueRun(there.id);
const t3 = await wait(there.id, (r) => r.status === "running");
assert.equal(t3.status, "done", t3.error);
assert.equal(t3.lectures.at(-1).status, "written");
assert.ok(t3.calls.find((c) => c.lecture === lastT2).prompt.user.find((p) => p.key === "previous").text.includes(linesOfText(run.lectures[0].text)[0]),
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
assert.equal(r1.steps.find((x) => x.key === "write").status, "waiting", "no transcript built");
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

// Sync: the two anchored example lectures (engine/examples/sync, Hinglish on the motion engine and English on the
// board) compiled and run without drawing, in a voice whose word times are exact (tools/sync_probe.py): every
// animation tied to words begins on them (from 0.6 s before to 0.35 s after). V2_CHECK_FULL only (minutes of renders).
if (FULL) {
  const { runPython: rp } = await import(path.resolve(here, "../lib/manim.ts"));
  const engine = process.env.V2_ENGINE;
  const probes = await Promise.all(["motion-hinglish", "board-english"].map(async (name) => {
    const dir = mkdtempSync(path.join(tmpdir(), `v2-sync-${name}-`));
    const env = { PYTHONPATH: engine, PANIM_IMAGE_FAKE: "1", PANIM_IMAGE_MODEL: "stand-in", PANIM_DIAGRAM_MODEL: "stand-in", PANIM_VOICE: "silent" };
    const compiler = name.startsWith("motion") ? "compile_motion.py" : "compile_lecture.py";
    const made = await rp([path.join(engine, compiler), "-", "--json"], dir, env, readFileSync(path.join(engine, "examples", "sync", `${name}.json`), "utf8"), 600_000);
    const compiled = JSON.parse(made.stdout.trim().split("\n").pop());
    assert.ok(compiled.source && !compiled.errors.length, `${name} compiles: ${compiled.errors?.join("; ")}`);
    writeFileSync(path.join(dir, "scene.py"), compiled.source);
    const probed = await rp([path.join(engine, "tools", "sync_probe.py"), "scene.py", "--fake-voice", "--json"], dir, { ...env, PANIM_VOICE: "" }, undefined, 900_000);
    return [name, JSON.parse(probed.stdout.trim().split("\n").pop())];
  }));
  for (const [name, sum] of probes) {
    const a = sum.anchors;
    // A new picture set late in its line comes on as the line begins and is not an anchor (MOTION_ENGINE.md §2).
    assert.ok(a.count >= 12, `${name}: its anchored animations measured (${a.count})`);
    assert.equal(a.on_time, a.count, `${name}: every anchored animation on its words: ${JSON.stringify(a.worst)}`);
    // Read on time: each anchored picture's key words readable no later than 0.35 s after their word, except where
    // the word comes sooner into its line than the picture takes to read (counted apart: sync_probe.py).
    // Kept alive: little of a spoken line left with nothing moving (MOTION_ENGINE.md §2, "Kept alive").
    const still = sum.still;
    if (still && name.startsWith("motion")) assert.ok(still.per_minute <= 8, `${name}: still stretches: ${JSON.stringify(still)}`);
    const r = sum.readable;
    if (r) assert.equal(r.late, 0, `${name}: every anchored picture read on its words: ${JSON.stringify(r.worst)}`);
    console.log(`sync (${name}): ${a.on_time} of ${a.count} anchored animations on their words` +
      (r ? `; ${r.on_time} read on time, ${r.unreachable} said before they could be read` : "") +
      (still ? `; ${still.per_minute} s a minute still` : ""));
  }
}

console.log(`${FULL ? "full" : "fast (V2_CHECK_FULL=1 for the renders, every Lab preset and the sync probes)"}: ${Math.round((Date.now() - began) / 1000)} s`);
console.log(`ok: ${run.blocks.length} blocks, ${run.lectures.length} lectures, ${allChapters.length} chapters, ${allBeats.length} beats, ${run.calls.length} calls, ${pics.length} figures triaged`);
process.exit(0);
