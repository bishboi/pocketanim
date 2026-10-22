// The transcription flow end to end with no keys: a 4-page chapter PDF read by the offline reader into Datalab-shaped
// JSON, written by the offline stand-in, each lecture as its script in one call. Checks: blocks keep Datalab's ids and
// boxes; the writer sees no boxes; the writer decides the lectures; chapters name their content (and may share it);
// a figure may be on several beats; the beats are the transcript; lectures see the ones before them.
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
  // Drawn: the timeline's beat rendered (its last frame), nothing skipped by the engine's guard.
  const dir = mkdtempSync(path.join(tmpdir(), "v2-timeline-"));
  writeFileSync(path.join(dir, "scene.py"), tl.source.split("\n").filter((l) => !/self\.(outro_fade|title_slide|credits)\(/.test(l)).join("\n"));
  const drawn = await rp(["-m", "manim", "-ql", "-s", "--disable_caching", "-o", "tl", "scene.py", "GeneratedScene"], dir, env, undefined, 600000);
  assert.ok(!/picture skipped|Traceback/.test(drawn.out), `the timeline is drawn: ${drawn.out.slice(-600)}`);
  assert.ok(readFileSync(path.join(dir, "media", "images", "scene", "tl.png")).length > 1000, "its frame");
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
assert.ok(Object.values(sl1.beats).every((b) => b.ops.every((o) => ["panel", "fact", "picture", "diagram", "define", "clear"].includes(o.op))), "only the kinds switched on");
const scenesCall = run.calls.find((c) => c.step === "scenes");
const offAll = scenesCall.prompt.system.find((p) => p.key === "off");
assert.ok(scenesCall.prompt.system.some((p) => p.key === "v2-anchors" && /EVERY VISUAL LANDS ON ITS WORDS/.test(p.text)), "the scene writer is told to anchor every visual");
assert.ok(offAll && /AI illustrations/.test(offAll.text) && !/Diagrams/.test(offAll.text), "the kinds switched off are named as such");
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
await scenesAction(run.id, { action: "render", lecture: 1, chapter: ch1.n, beat: renderBeat, style: "blueprint" });
run = await slow(run.id, (r) => r.scenes.renders > 0, 3000);
const rendered = run.scenes.lectures[1].beats[renderBeat].render;
assert.equal(rendered.status, "done", rendered.error);
assert.equal(rendered.style, "blueprint");
assert.ok(rendered.ir && rendered.assets && rendered.range && rendered.frames > rendered.range[0], "playable in v1's web player: its geometry, and the beat's frames");
const { scenesDir } = await import(path.resolve(here, "../lib/scenes.ts"));
const irOf = (url) => JSON.parse(readFileSync(path.join(scenesDir(run.id), new URL(`http://x${url}`).searchParams.get("p"), "scene_ir.json"), "utf8"));
assert.equal(irOf(rendered.ir).frames, rendered.frames, "the geometry is there, every frame");
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
await voiceAction(run.id, { action: "reset", lecture: 1, chapter: ch1.n });

// The Lab: every preset and every snippet compiles; an experiment from a preset is spoken, timed and played; one from a
// lecture's chapter; duplicated, renamed, removed.
{
  const { LAB_PRESETS, LAB_SNIPPETS } = await import(path.resolve(here, "../lib/lab-presets.ts"));
  const { labAction } = await import(path.resolve(here, "../lib/lab.ts"));
  const { compile: compileScript } = await import(path.resolve(here, "../lib/scenes.ts"));
  const { readChapterScript, engineScriptOf } = await import(path.resolve(here, "../lib/voice.ts"));
  const all = { region: null, chapter: { title: "Snippets", beats: LAB_SNIPPETS.map((x) => ({ say: x.say, do: [x.do] })) } };
  for (const [name, script] of [...LAB_PRESETS.map((p) => [p.id, p.script]), ["snippets", all]]) {
    const c = await compileScript(run, await engineScriptOf(run, 1, readChapterScript(script)), path.join(scenesDir(run.id), "lab-check", name));
    assert.ok(c.source && !c.errors.length, `the Lab's ${name} compiles: ${c.errors.join("; ")}`);
    assert.deepEqual(c.warnings.filter((w) => /left out|unknown/i.test(w)), [], `the Lab's ${name}: nothing left out`);
  }
  // The motion engine (beta): every motion preset and snippet compiles on it, with nothing left out.
  const { LAB_MOTION_PRESETS, LAB_MOTION_SNIPPETS } = await import(path.resolve(here, "../lib/lab-presets.ts"));
  const motionAll = { engine: "motion", look: "paper", region: null, chapter: { title: "Motion snippets",
    beats: [{ say: "Japan, Italy and Germany.", do: [{ op: "chart", items: [["Japan", 204], ["Italy", 138], ["Germany", 65]] }] },
      ...LAB_MOTION_SNIPPETS.map((x) => ({ say: x.say, do: [x.do] }))] } };
  for (const [name, script] of [...LAB_MOTION_PRESETS.map((p) => [p.id, p.script]), ["motion-snippets", motionAll]]) {
    const c = await compileScript(run, await engineScriptOf(run, 1, readChapterScript(script)), path.join(scenesDir(run.id), "lab-check", name));
    assert.ok(c.source && !c.errors.length, `the Lab's ${name} compiles on the motion engine: ${c.errors.join("; ")}`);
    assert.ok(c.source.includes("(MotionLecture)") && c.source.includes("from motion import *"), `the Lab's ${name} is a motion scene`);
    assert.deepEqual(c.warnings.filter((w) => /left out|unknown|is not one of/i.test(w) && !/no reusable illustration|picture/i.test(w)), [],
      `the Lab's ${name}: nothing left out`);
  }
  await assert.rejects(Promise.resolve().then(() => readChapterScript({ engine: "beta", chapter: { title: "x", beats: [{ say: "x" }] } })), /"engine" is "motion"/);
  const added = await labAction(run.id, { action: "add", preset: "diagram-build" });
  assert.equal(added.name, "Diagram built over beats");
  await labAction(run.id, { action: "try", id: added.id });
  run = await slow(run.id, (r) => voiceRunning(r), 3000);
  const lv = run.lab.items.find((i) => i.id === added.id).result;
  assert.equal(lv.status, "done", lv.error);
  assert.ok(lv.ir && lv.audio && lv.frames > 0 && lv.beats.length === 4, "the experiment played with its narration, its four beats placed");
  assert.ok(lv.cues.some((c) => c.cues?.length), "its animations timed to the words");
  assert.ok(lv.lines.filter((l) => l.beat !== undefined).length === 4, "each line under its beat");
  assert.ok(fileOf(lv.ir).includes(`${path.sep}lab${path.sep}${added.id}`), "its files the Lab's own");
  assert.ok(run.calls.some((c) => /the Lab's "Diagram built over beats"/.test(c.label)), "its calls named for it");
  const fromChapter = await labAction(run.id, { action: "add", lecture: 1, chapter: ch1.n });
  assert.ok(fromChapter.script.chapter.beats.length === ch1.beats.length && fromChapter.script.chapter.beats.every((b) => b.beat === undefined), "a lecture's chapter, its beats the experiment's own");
  // A motion experiment: spoken, timed and played on the motion engine; a lecture's chapter added in a motion look.
  const moving = await labAction(run.id, { action: "add", preset: "m-columns" });
  await labAction(run.id, { action: "try", id: moving.id });
  run = await slow(run.id, (r) => voiceRunning(r), 3000);
  const mv = run.lab.items.find((i) => i.id === moving.id).result;
  assert.equal(mv.status, "done", mv.error);
  assert.ok(mv.ir && mv.audio && mv.frames > 0 && mv.beats.length === 2, "the motion experiment played with its narration");
  assert.ok(readFileSync(path.join(fileOf(mv.ir), "..", "scene.py"), "utf8").includes("MotionLecture"), "drawn by the motion engine");
  const inMotion = await labAction(run.id, { action: "add", lecture: 1, chapter: ch1.n, motion: true, look: "newsroom" });
  assert.ok(inMotion.script.engine === "motion" && inMotion.script.look === "newsroom" && / \(motion: newsroom\)$/.test(inMotion.name), "a chapter in a motion look");
  const c2 = await compileScript(run, await engineScriptOf(run, 1, inMotion.script), path.join(scenesDir(run.id), "lab-check", "chapter-in-motion"));
  assert.ok(c2.source && !c2.errors.length && c2.source.includes("(MotionLecture)"), `a lecture's chapter compiles on the motion engine: ${c2.errors.join("; ")}`);
  for (const i of [moving, inMotion]) await labAction(run.id, { action: "remove", id: i.id });
  const copy = await labAction(run.id, { action: "duplicate", id: added.id });
  assert.ok(!copy.result && copy.name.endsWith("(copy)"));
  await labAction(run.id, { action: "save", id: copy.id, name: "Variant", script: { chapter: { title: "V", beats: [{ say: "One beat.", do: [{ op: "fact", text: "a variant" }] }] } } });
  run = await loadRun(run.id);
  assert.equal(run.lab.items.find((i) => i.id === copy.id).name, "Variant");
  await assert.rejects(labAction(run.id, { action: "save", id: copy.id, script: { beats: [] } }), /needs "chapter"/);
  for (const i of [copy, fromChapter, added]) await labAction(run.id, { action: "remove", id: i.id });
  assert.equal((await loadRun(run.id)).lab.items.length, 0, "removed");
  console.log(`lab: ${LAB_PRESETS.length} presets and ${LAB_SNIPPETS.length} snippets compile; an experiment played in ${(lv.frames / lv.fps).toFixed(1)} s`);
  console.log(`lab (motion beta): ${LAB_MOTION_PRESETS.length} presets and ${LAB_MOTION_SNIPPETS.length} snippets compile; one played in ${(mv.frames / mv.fps).toFixed(1)} s`);
}

// A chapter's own kinds: its beats built with only those (a beat's own still wins).
const kc = run.script.lectures[1].chapters[0];
await scenesAction(run.id, { action: "chapterKinds", lecture: 1, chapter: kc.n, kinds: ["define"] });
await scenesAction(run.id, { action: "build", scope: "chapter", lecture: 1, chapter: kc.n });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.ok(kc.beats.every((b) => run.scenes.lectures[1].beats[b.n].ops.every((o) => ["panel", "fact", "define", "clear"].includes(o.op))), "only the chapter's kinds");
const kcCall = run.calls.filter((c) => c.step === "scenes" && /chapter/.test(c.label)).at(-1);
const offPart = kcCall.prompt.system.find((p) => p.key === "off");
assert.ok(offPart && /Diagrams/.test(offPart.text) && !/Definitions/.test(offPart.text), "the kinds the chapter may not use are named as switched off");
// The instructions are v1's, word for word, in v1's order; the subject's guidance as v1 tells it.
const { V1_LECTURE, V1_MANIM_PLAN } = await import(path.resolve(here, "../lib/prompts/v1-lecture.ts"));
const sysText = render(kcCall.prompt.system);
for (const key of Object.keys(V1_LECTURE).filter((k) => k !== "beat")) assert.ok(sysText.includes(V1_LECTURE[key].join("\n").trim()), `v1's ${key} section, verbatim`);
// No limit to a beat's operations by default: v1's "at most four operations" is taken out, the rest of its words kept.
assert.ok(!/at most four operations/.test(sysText) && sysText.includes(V1_LECTURE.beat.join("\n").replace(", at most four operations.", ".").trim()), "no limit to a beat's operations");
assert.ok(kcCall.prompt.system.some((p) => p.key === "pace" && /no limit to the operations on a beat/.test(p.text)));
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
await scenesAction(run.id, { action: "render", lecture: 1, chapter: run.script.lectures[1].chapters[0].n, beat: galleryBeat });
run = await slow(run.id, (r) => r.scenes.renders > 0, 3000);
assert.equal(run.scenes.lectures[1].beats[galleryBeat].render.missing?.length, 2, "the render says what it left out");
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
await assert.rejects(scenesAction(run.id, { action: "engine", engine: "motion", look: "neon" }), /motion look is one of/);
await scenesAction(run.id, { action: "engine", engine: "motion", look: "newsroom", timeline: "ribbon" });
run = await loadRun(run.id);
assert.ok(run.scenes.engine === "motion" && run.scenes.motion.look === "newsroom", "the engine set for the run");
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
assert.ok(motionCall.prompt.system.some((p) => p.key === "anchors" && /EVERY VISUAL LANDS ON ITS WORDS/.test(p.text)), "the beta writer is told to anchor every visual");
assert.ok(motionCall.prompt.system.some((p) => p.key === "shape" && /HOW TO BUILD THE JSON/.test(p.text)) &&
  motionCall.prompt.system.some((p) => p.key === "choose" && /WHICH PRIMITIVE FOR WHAT/.test(p.text)), "the beta writer is told how to build the JSON and which primitive suits what");
const motionBeats = Object.values(run.scenes.lectures[1].beats);
assert.ok(run.script.lectures[1].chapters.every((c) => c.beats.every((b) => b.lines.length === 1)), "one sentence a beat on the motion engine");
const templateBeats = motionBeats.filter((b) => b.ops.some((o) => ["title", "counter", "list", "stamp"].includes(o.op))).length;
assert.ok(templateBeats > 0, "motion templates in the beats");
assert.ok(motionBeats.every((b) => !b.errors?.length), `nothing refused on the motion engine: ${motionBeats.flatMap((b) => b.errors ?? []).join("; ")}`);
assert.equal(run.scenes.lectures[1].compile.status, "done", JSON.stringify(run.scenes.lectures[1].compile));
const motionScript = await engineScript(run, 1, run.scenes.look);
assert.ok(motionScript.engine === "motion" && motionScript.look === "newsroom" && motionScript.timeline === "ribbon", "its beat script on the motion engine");
const motionCompiled = await compileMotion(run, motionScript, path.join(scenesDir(run.id), "motion-check"), 1);
assert.ok(motionCompiled.source?.includes("(MotionLecture)") && !motionCompiled.errors.length, motionCompiled.errors.join("; "));
await scenesAction(run.id, { action: "render", lecture: 1, chapter: ch1.n, beat: firstBeat });
run = await slow(run.id, (r) => r.scenes.renders > 0, 3000);
const motionRender = run.scenes.lectures[1].beats[firstBeat].render;
assert.equal(motionRender.status, "done", motionRender.error);
assert.ok(readFileSync(path.join(fileOf(motionRender.ir), "..", "scene.py"), "utf8").includes("MotionLecture"), "rendered by the motion engine");
const motionChapter = await chapterScript(run, 1, ch1.n);
assert.ok(motionChapter.engine === "motion" && motionChapter.look === "newsroom", "the Voice tab's chapter carries the engine");
assert.ok((await editInstructions(run, 1)).includes("MOTION TEMPLATES"), "the hand instructions tell of the templates");
await scenesAction(run.id, { action: "engine", engine: "current" });
run = await loadRun(run.id);
assert.ok(!run.scenes.engine && !(await engineScript(run, 1, run.scenes.look)).engine, "back on the current engine");
await scenesAction(run.id, { action: "build", scope: "lecture", lecture: 1 });
run = await slow(run.id, (r) => r.scenes.status === "running");
assert.equal(run.scenes.lectures[1].status, "done", run.scenes.lectures[1].error);
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
// animation tied to words begins on them (from 0.6 s before to 0.35 s after).
{
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
    assert.ok(a.count >= 15, `${name}: its anchored animations measured (${a.count})`);
    assert.equal(a.on_time, a.count, `${name}: every anchored animation on its words: ${JSON.stringify(a.worst)}`);
    console.log(`sync (${name}): ${a.on_time} of ${a.count} anchored animations on their words`);
  }
}

console.log(`ok: ${run.blocks.length} blocks, ${run.lectures.length} lectures, ${allChapters.length} chapters, ${allBeats.length} beats, ${run.calls.length} calls, ${pics.length} figures triaged`);
process.exit(0);
