/**
 * The Manim agent: one beat's Manim figure, built the way a person would build it. It reads the beat (what is said
 * on it, what the scene writer planned, the earlier beats of the same figure, the book's figure when there is one),
 * then works in turns with three tools:
 *
 *   - make_image: has the image model draw a picture it wants in the figure (a cutout of a thing or a person, or a
 *     whole scene behind), drawn in the style it describes (only the form and no text are added); it is shown the picture made, and uses it in
 *     its code by name: image("farmer", height=2.5) (the engine's free_check.image, v2's own);
 *   - check: its code checked in the beat's place (the earlier beats of the same figure first) by v2's engine's
 *     compile: the sandbox's rules, and a run of the blocks in a probe scene; nothing is rendered, no frame or video
 *     goes back to it (a render each turn was too slow): only the errors, or that it runs;
 *   - finish: the code it settles on (and whether the figure keeps the left half for a working beside it).
 *
 * So it decides itself whether pictures help, makes them, looks at them (the pictures it makes are shown to it),
 * places them by numbers, and gets its code to run before it is done; the beat is rendered on the page when asked. Every turn is a call; every picture is a call of the image model; every step is kept on the
 * beat (SceneBeat.agent) for the page.
 */

import { isPlanOfBeats, paragraphsOf } from "./beat-director";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";
import { bookOf } from "./docs";
import { callImage } from "./images";
import { usingFixture } from "./llm";
import { modelFor } from "./models";
import { part, render, type Part } from "./prompts/parts";
import { imageData, newCall } from "./run";
import { agentRegistry, compile, engineScript, fileUrl, lectureState, scenesDir, scriptOf, stateOf, voicedBeats } from "./scenes";
import { beatFigures, lectureFigures } from "./script-figures";
import { figureFile } from "./source/blocks";
import { linesOf } from "./source/book";
import { saveRun } from "./store";
import { lookWords } from "./styles";
import type { AgentImage, AgentStep, Call, ManimAgentState, Run, SceneBeat } from "./types";

const URL_ = process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions";
const MAX_TURNS = Math.max(2, Number(process.env.V2_MANIM_AGENT_TURNS) || 10);
const MAX_IMAGES = Math.max(0, Number(process.env.V2_MANIM_AGENT_IMAGES) || 4);
const TIMEOUT_MS = 480_000;

const TOOLS = [
  { type: "function", function: { name: "make_image", description: "Have the image model draw a picture for the figure. You are shown it; use it in code as image(\"<name>\", height=..., width=..., labels=[...]).",
    parameters: { type: "object", properties: {
      name: { type: "string", description: "A short name for it, letters and _ (\"farmer\", \"indus_city\"). The same name again replaces it." },
      what: { type: "string", description: "The whole picture, in English, as the image model is to draw it: what it shows, how it is seen, and how it is drawn -- the medium and art style, the colours, the mood (\"a farmer ploughing with two oxen, side view, a warm watercolour with soft ink lines\"). Nothing is added to your words but its form (a cutout on white, or a whole scene) and no text, so the style is yours to choose for this moment. No words in it." },
      kind: { type: "string", enum: ["cutout", "scene"], description: "cutout: one thing or person, cut out with no background, a sticker on the board; scene: a whole picture edge to edge (a place, an event), to put behind or beside." },
    }, required: ["name", "what", "kind"] } } },
  { type: "function", function: { name: "check", description: "Check the code in the beat's place (after the earlier beats of the same figure): the compiler reads it and runs it in a probe, nothing is rendered. Returns its errors, or that it runs.",
    parameters: { type: "object", properties: {
      code: { type: "string", description: "The body of construct() for this beat." },
      area: { type: "string", enum: ["full", "left"], description: "left: the figure keeps the board's left half (x -6.9..-0.4) for a working beside it." },
    }, required: ["code"] } } },
  { type: "function", function: { name: "finish", description: "Settle on the code for this beat (it is checked again if it is not the code last checked).",
    parameters: { type: "object", properties: {
      code: { type: "string" }, area: { type: "string", enum: ["full", "left"] },
      summary: { type: "string", description: "One line: what the figure shows on this beat, and the pictures in it." },
    }, required: ["code", "summary"] } } },
];

const ROLE = "You are the Manim agent of a narrated lecture video. You build ONE beat's Manim figure: the animation on screen " +
  "while the beat's sentences are said. You work in turns with tools: make the pictures the figure needs (make_image), " +
  "check your code (check: the compiler reads it and runs it, nothing is rendered), mend what it says, and finish (finish) with the code you settle on.";

const TIMING = [
  "TIMING: YOU TIME THE FIGURE. Nothing else moves it: your code starts as the line starts (t = 0) and runs as written,",
  "so the figure follows the voice only if you time it. Use the beat's word times (given): before each step, self.wait()",
  "for the gap until its word, and give its self.play a run_time that ends before the next step's word -- a part comes on",
  "as the narration names it (0.2 s before the word), a highlight as the word that turns the idea is said. Add up your",
  "waits and run_times as you go: the total must stay within the line's seconds (the quiet after it is a hold: one last",
  "settle, never a new step). Many small steps on their words read better than one long play at the start.",
].join("\n");

const RULES = [
  "THE CODE is the body of construct() for this beat: build objects and self.play(...) them. Beats with the same figure id",
  "share their variables, in order: the earlier beats' code (given) has run before yours; build on it (Indicate a part,",
  "add the next piece, move an equation), do not rebuild it. Its animations happen while the beat is said: about as long",
  "as the sentences (given in seconds), so only what they describe; the next step belongs to the next beat.",
  "- Names: everything Manim exports (Polygon, Line, Arrow, Circle, Rectangle, Arc, Dot, DashedLine, MathTex, Text, VGroup,",
  "  Group, SurroundingRectangle, Create, Write, FadeIn, FadeOut, GrowArrow, Indicate, TransformFromCopy,",
  "  ReplacementTransform, LaggedStart, UP, DOWN, LEFT, RIGHT, PI...) and np. No imports, classes, while loops, try, with,",
  "  self.camera or self.clear: only self.play, self.wait, self.add, self.remove.",
  "- The board: x from -6.9 to 6.9, y from -3.05 to 2.85 (a title strip above, the caption below); nothing outside it.",
  "- Colours: INK for lines and words, MUTED_INK for faint parts, PALETTE[\"ROSE\"] (forces), PALETTE[\"GREEN\"] (motion),",
  "  PALETTE[\"GOLD\"] (highlights, answers), PALETTE[\"RIVER\"], PALETTE[\"TERRA\"], PALETTE[\"TEAL\"], PALETTE[\"VIOLET\"].",
  "- Words: Text(..., font_size=24-32), MathTex for symbols; each label next_to its part (buff 0.15-0.3), never on a line,",
  "  never two overlapping. True geometry, values and units. Never a map (no outlines of places).",
  "",
  "PICTURES. Where seeing a real thing teaches it (a farmer, a granary, a river valley, a cell under a microscope), make it",
  "with make_image and put it in the figure: image(\"farmer\", height=2.5) is a Mobject you place, scale, move and FadeIn",
  "(not Create or Write: it is a picture); labels=[\"plough\", \"oxen\"] writes those names on it where the parts really",
  "are, so never put your own Text on a picture by guessed coordinates. A cutout is one thing on the board; a scene is a",
  "whole picture (put it behind with a lower z: scene.set_z_index(-1), or beside). Pictures have no words in them. Make",
  `only the pictures the figure needs (at most ${MAX_IMAGES}); reuse one already made (listed) by its name. A diagram of`,
  "exact things (axes, forces, geometry) is drawn in Manim, not as a picture. Leave pictures out when they do not help.",
  "",
  "WORK LIKE THIS: plan the layout first, in numbers (what goes where, its size, the gaps), since you will not see it: keep",
  "everything inside the board, words clear of lines and pictures, nothing overlapping. Make the pictures, write the code,",
  "check it, mend what the compiler says, check again, then finish. Finish only code that checked without errors.",
].join("\n");

type Msg = { role: "system" | "user" | "assistant" | "tool"; content: unknown; tool_calls?: unknown[]; tool_call_id?: string };
type ToolCall = { id: string; function: { name: string; arguments: string } };

/** A placeholder for an image in what is kept of a request. */
const short = (url: string) => (url.startsWith("data:") ? `${url.split(",")[0]},… (${Math.round(url.length * 0.75 / 1024)} kB)` : url);

/** One turn of the model: the conversation so far, the tools; what it said and the tools it called. */
async function turn(call: Call, messages: Msg[], fake: () => { text?: string; calls: { name: string; args: Record<string, unknown> }[] }):
  Promise<{ text?: string; calls: ToolCall[] } | null> {
  call.tool = TOOLS;
  call.provider = usingFixture(call.model) ? "fixture" : "openrouter";
  const body = { model: call.model, messages, tools: TOOLS, tool_choice: "required", usage: { include: true },
    ...(call.effort && call.effort !== "off" ? { reasoning: { effort: call.effort } } : {}) };
  call.request = { ...body, messages: messages.map((m) => Array.isArray(m.content)
    ? { ...m, content: (m.content as { type: string; image_url?: { url: string } }[]).map((c) => (c.image_url ? { ...c, image_url: { url: short(c.image_url.url) } } : c)) } : m) };
  for (let attempt = 1; attempt <= 3; attempt++) {
    const began = Date.now();
    try {
      let out: { text?: string; calls: ToolCall[] };
      if (call.provider === "fixture") {
        await new Promise((r) => setTimeout(r, 200 + Math.random() * 400));
        const f = fake();
        out = { text: f.text, calls: f.calls.map((c, i) => ({ id: `fake_${Date.now()}_${i}`, function: { name: c.name, arguments: JSON.stringify(c.args) } })) };
        call.usage = { input: Math.round(JSON.stringify(call.request).length / 4), output: Math.round(JSON.stringify(f).length / 4) };
      } else {
        const response = await fetch(URL_, { method: "POST", signal: AbortSignal.timeout(TIMEOUT_MS),
          headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json", "X-Title": "pocketanim harness v2" },
          body: JSON.stringify(body) });
        const raw = await response.text();
        if (!response.ok) throw new Error(`${response.status} ${raw.slice(0, 300)}`);
        const json = JSON.parse(raw) as { choices?: { message?: { content?: string | null; tool_calls?: ToolCall[] } }[];
          usage?: { prompt_tokens?: number; completion_tokens?: number; cost?: number }; error?: { message?: string } };
        if (json.error) throw new Error(json.error.message ?? "provider error");
        call.usage = { input: json.usage?.prompt_tokens ?? 0, output: json.usage?.completion_tokens ?? 0 };
        call.cost += Number(json.usage?.cost ?? 0);
        const m = json.choices?.[0]?.message;
        out = { text: m?.content ?? undefined, calls: (m?.tool_calls ?? []).filter((c) => c?.function?.name) };
      }
      call.attempts.push({ started: began, ended: Date.now() });
      call.text = out.text;
      call.output = { said: out.text, tools: out.calls.map((c) => ({ name: c.function.name, args: safeJson(c.function.arguments) })) };
      call.status = "done";
      call.ended = Date.now();
      return out;
    } catch (error) {
      call.attempts.push({ started: began, ended: Date.now(), error: (error as Error).message.slice(0, 400) });
      if (/\b(400|401|403|404)\b/.test((error as Error).message)) break;
    }
  }
  call.status = "failed";
  call.ended = Date.now();
  call.error = call.attempts.at(-1)?.error;
  return null;
}

function safeJson(text: string): Record<string, unknown> {
  try {
    const v = JSON.parse(text || "{}");
    return v && typeof v === "object" ? v as Record<string, unknown> : {};
  } catch {
    return { _unreadable: text.slice(0, 400) };
  }
}

/** The images of a lecture the agent made, kept with the scenes. */
function imagesOf(run: Run, n: number): Record<string, AgentImage> {
  const st = stateOf(run);
  st.agentImages ??= {};
  st.agentImages[n] ??= {};
  return st.agentImages[n];
}

async function writeRegistry(run: Run, n: number) {
  const file = agentRegistry(run.id, n);
  await mkdir(path.dirname(file), { recursive: true });
  const ok = Object.fromEntries(Object.values(imagesOf(run, n)).filter((i) => i.status === "done" && i.file).map((i) => [i.name, i.file]));
  await writeFile(file, JSON.stringify(ok, null, 1), "utf8");
}

/** A stand-in picture (no key): a soft shape with the name's first letter, on white. */
async function standIn(name: string, kind: "cutout" | "scene"): Promise<Buffer> {
  const hue = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  const svg = kind === "scene"
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="hsl(${hue},45%,72%)"/><rect y="360" width="960" height="180" fill="hsl(${(hue + 60) % 360},40%,45%)"/><circle cx="760" cy="120" r="60" fill="#fff6c8"/></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect width="512" height="512" fill="#ffffff"/><circle cx="256" cy="256" r="170" fill="hsl(${hue},60%,55%)"/><text x="256" y="300" font-size="140" text-anchor="middle" fill="#fff" font-family="sans-serif">${name[0]?.toUpperCase() ?? "?"}</text></svg>`;
  return sharp(Buffer.from(svg)).png().toBuffer();
}

/** White round a cutout made clear, so it sits on the board like a sticker (the engine trims the clear edge). */
async function cutout(bytes: Buffer): Promise<Buffer> {
  const { data, info } = await sharp(bytes).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  for (let i = 0; i < data.length; i += 4) {
    const [r, g, b] = [data[i], data[i + 1], data[i + 2]];
    const light = Math.min(r, g, b);
    if (light > 238) data[i + 3] = 0;
    else if (light > 222) data[i + 3] = Math.round(255 * (238 - light) / 16);
  }
  return sharp(data, { raw: { width: info.width, height: info.height, channels: 4 } }).png().toBuffer();
}

async function makeImage(run: Run, n: number, beat: number, state: ManimAgentState, args: Record<string, unknown>, _look: string): Promise<AgentImage> {
  // The picture's style is the agent's own, in its words (make_image's "what"): only its form and no text are added.
  const name = String(args.name ?? "").trim().replace(/[^\w]+/g, "_").slice(0, 40) || `image_${Object.keys(imagesOf(run, n)).length + 1}`;
  const kind = args.kind === "scene" ? "scene" : "cutout";
  const what = String(args.what ?? "").trim().slice(0, 600) || name.replace(/_/g, " ");
  const text = kind === "cutout"
    ? `${what}. One subject alone, isolated on a plain pure white background, no shadow, no border, no frame. NO TEXT at all: no words, letters, numbers or labels.`
    : `${what}. A whole scene filling the image edge to edge, wide (16:9). NO TEXT at all: no words, letters, numbers or labels.`;
  const call = newCall(run, { step: "manim-agent", label: `Manim agent image "${name}" (lecture ${n}, beat ${beat})`, lecture: n, model: state.imageModel, effort: "off",
    prompt: { system: [], user: [part("what", "What it shows", "ask", what), part("rules", "Its form and look", "rules", text.slice(what.length + 2))] } });
  lectureState(run, n).calls.push(call.id);
  const out = await callImage({ call, text, fake: () => ({ bytes: Buffer.alloc(0), mime: "image/png" }), onChange: () => saveRun(run) });
  const row: AgentImage = { name, what, kind, beat, call: call.id, status: "failed", cost: call.cost, at: Date.now() };
  if (!out) {
    row.error = call.error ?? "no image";
  } else {
    const raw = out.bytes.length ? out.bytes : await standIn(name, kind);
    const bytes = kind === "cutout" ? await cutout(raw) : await sharp(raw).png().toBuffer();
    // "gen-" in the name: the engine shows it as a made picture (no frame round it).
    const file = path.join(scenesDir(run.id), `L${n}`, "agent-images", `gen-agent-${name}.png`);
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, bytes);
    Object.assign(row, { status: "done", file, url: fileUrl(run.id, file) });
    call.output = { image: row.url, kind };
  }
  imagesOf(run, n)[name] = row;
  if (!state.images.includes(name)) state.images.push(name);
  await writeRegistry(run, n);
  return row;
}

/**
 * The code checked in the beat's place, nothing rendered: the earlier beats of the figure, then it, through the
 * engine's compile, which reads each block against the sandbox's rules and runs the figure's blocks in a probe scene
 * (free_check.verify: no frames are drawn, no video is made). Its errors, or none.
 */
async function checkCode(run: Run, n: number, beat: number, id: string, code: string, area: string | undefined, tag: string):
  Promise<{ errors: string[]; notes: string[]; seconds: number }> {
  const began = Date.now();
  const script = scriptOf(run, n)!;
  const chapter = script.chapters.find((c) => c.beats.some((b) => b.n === beat))!;
  const sl = lectureState(run, n);
  const st = stateOf(run);
  const full = await engineScript(run, n, st.look, { chapter: chapter.n, upTo: beat });
  const ch = (full.chapters as { beats: { say: string; do: unknown[] }[] }[])[0];
  // Only this figure: its earlier beats' blocks, then this one.
  ch.beats = chapter.beats.slice(0, chapter.beats.findIndex((b) => b.n === beat) + 1).map((b, i, all) => {
    const say = ch.beats[i].say;
    if (i === all.length - 1) return { say, do: [{ op: "manim", id, code, ...(area === "left" ? { area: "left" } : {}) }] };
    const own = (sl.beats[b.n]?.ops ?? []).filter((o) => o.op === "manim" && String(o.id) === id && o.code);
    return { say, do: own };
  }).filter((b, i, all) => i === all.length - 1 || b.do.length);
  const dir = path.join(scenesDir(run.id), `L${n}`, "agent", `beat-${beat}`, tag);
  await rm(dir, { recursive: true, force: true });
  const compiled = await compile(run, full, dir, n);
  const strip = (e: string) => e.replace(/^(fixed:\s*)?chapter \d+ beat \d+:\s*/i, "");
  const errors = compiled.errors.map(strip);
  if (!errors.length && !compiled.source) errors.push("the engine made no scene of it");
  // A block the engine left out (rather than refused) is as good as broken for the agent.
  const dropped = compiled.warnings.filter((w) => /manim/i.test(w) && /left out|dropped|removed/i.test(w)).map(strip);
  return { errors: [...errors, ...dropped], notes: compiled.warnings.filter((w) => /manim/i.test(w) && !dropped.includes(strip(w))).map(strip).slice(0, 6),
    seconds: (Date.now() - began) / 1000 };
}

/** The beat's figure id: its manim op's, else a new one. */
export function figureIdOf(b: SceneBeat | undefined, beat: number): string {
  const op = b?.ops.find((o) => o.op === "manim");
  return op?.id ? String(op.id) : `m${beat}`;
}

/** The agent run on one beat (its lecture locked by the caller). The beat's ops become its manim op when it finishes. */
export async function runManimAgent(run: Run, n: number, beat: number, o: { instruction?: string; model?: string; stop?: () => boolean } = {}) {
  const st = stateOf(run);
  const sl = lectureState(run, n);
  const script = scriptOf(run, n)!;
  const lecture = run.lectures.find((l) => l.n === n)!;
  const lines = linesOf(lecture.text ?? "");
  const chapter = script.chapters.find((c) => c.beats.some((b) => b.n === beat))!;
  const sbeat = chapter.beats.find((b) => b.n === beat)!;
  const b = (sl.beats[beat] ??= { n: beat, status: "waiting", ops: [], calls: [] });
  const existing = b.ops.find((op) => op.op === "manim");
  const id = figureIdOf(b, beat);
  const plan = existing ? String(existing.plan ?? "") : "";
  const said = sbeat.lines.map((k) => lines[k - 1] ?? "").join(" ").trim();
  // The beat as its voice says it (the chapter spoken first), so the figure is timed to its words; else estimated.
  const voiced = await voicedBeats(run, n, chapter.n).catch(() => undefined);
  const voice = voiced?.get(beat);
  const secs = voice?.seconds ?? Math.max(2, said.split(/\s+/).length / 2.6);
  // The scene it is in (a chapter built as one piece): its beats, so the figure is built across them.
  const built = sl.plans?.[chapter.n];
  const scene: { id: string; beats: number[]; intent?: string } | undefined = isPlanOfBeats(built)
    ? paragraphsOf(built.beats).map((beats, k) => ({ id: `P${k + 1}`, beats })).find((x) => x.beats.includes(beat))
    : built?.scenes.find((x) => x.beats.includes(beat));
  const look = lookWords(st.look);
  const state: ManimAgentState = { status: "running", model: o.model || st.manimModel || run.options.manimModel || modelFor("manim"),
    imageModel: run.options.imageModel || modelFor("image"), id, plan: plan || undefined, instruction: o.instruction, steps: [], images: [], turns: 0, cost: 0, started: Date.now() };
  b.agent = state;
  b.status = "running";
  saveRun(run);
  const step = (s: Omit<AgentStep, "at">) => { state.steps.push({ ...s, at: Date.now() }); saveRun(run); };

  // What it is told: the beat, the figure's earlier beats, what follows, the images there are, the book's figure.
  const before = chapter.beats.filter((x) => x.n < beat).map((x) => ({ x, op: sl.beats[x.n]?.ops.find((op) => op.op === "manim" && String(op.id) === id) }))
    .filter((r) => r.op?.code);
  const after = chapter.beats.filter((x) => x.n > beat).slice(0, 3);
  const made = Object.values(imagesOf(run, n)).filter((i) => i.status === "done");
  // The book's figures the script shows on this beat (a figure may be on several beats), their pictures attached.
  const known = lectureFigures(run, n);
  const figures = beatFigures(sbeat).map((id) => known.find((f) => f.id === id)).filter((f): f is NonNullable<typeof f> => !!f).slice(0, 3);
  const book = figures.length ? await bookOf(run.documentId).catch(() => null) : null;
  const figureData: string[] = [];
  for (const figure of figures) {
    const gen = run.generation?.figures[figure.id];
    const block = run.blocks.find((x) => x.id === figure.id);
    const file = gen?.status === "done" && gen.file && !gen.file.endsWith(".svg") ? gen.file : book && block ? figureFile(block, book.json, book.figures) : undefined;
    const data = file ? await imageData(file) : undefined;
    if (data) figureData.push(data);
  }
  const userParts: Part[] = [
    part("lecture", "The lecture and chapter", "context", `Lecture ${n}: ${lecture.title}. Chapter ${chapter.n}: ${chapter.title} (on the board).`),
    part("look", "The look", "context", `The board is drawn in ${look}: its colours are INK, MUTED_INK and PALETTE. The pictures you make (make_image) are drawn in the style you describe for each: choose it.`),
    part("beat", `Beat #${beat}: what is said (${voice ? `${secs} s, then ${voice.pause} s quiet` : `about ${secs.toFixed(0)} s`})`, "book", `"${said}"\nThe script's note of what is on screen: ${sbeat.show || "-"}`),
    part("timing", voice ? "The beat's words and when each is said (its own timing: you time the figure)" : "The beat's timing (estimated: the voice is not made yet)", "context", [
      voice ? `Words (seconds from the line's start): ${voice.words.map((w, i) => `w${i} ${w.w} ${w.t.toFixed(1)}`).join(" | ")}`
        : `About ${secs.toFixed(1)} s; its words are said evenly through it.`,
      ...(scene ? [`It is in scene ${scene.id} (beats ${scene.beats.join(", ")}${scene.intent ? `, ${scene.intent}` : ""}): the beats after it in that scene build on this figure.`] : []),
    ]),
    ...(plan ? [part("plan", "The scene writer's plan for this figure", "plan", plan)] : []),
    ...(o.instruction ? [part("instruction", "What you are asked (by the person building the video)", "ask", o.instruction)] : []),
    part("figure", `The figure: id "${id}"`, "context", before.length
      ? [`Its earlier beats (their code has run before yours, its variables are yours to use):`, ...before.map((r) => `--- beat #${r.x.n}: "${r.x.lines.map((k) => lines[k - 1]).join(" ")}"\n${r.op!.code}`)]
      : "It starts on this beat: nothing of it is on the board yet."),
    ...(after.length ? [part("after", "What comes next (not yours: leave it for those beats)", "context", after.map((x) => `#${x.n}: ${x.lines.map((k) => lines[k - 1]).join(" ")}`))] : []),
    part("images", `Pictures already made for this lecture (${made.length})`, "items", made.length ? made.map((i) => `${i.name} (${i.kind}): ${i.what}`) : "None yet."),
    ...(figures.length ? [part("bookfigure", `The book's figure${figures.length > 1 ? "s" : ""} on this beat (attached)`, "items",
      figures.map((f) => `${f.id}: ${f.caption || "(no caption)"} - ${f.way}${f.beats.length > 1 ? ` (also shown on beats ${f.beats.filter((x) => x !== beat).join(", ")})` : ""}`))] : []),
    part("ask", "Request", "ask", "Build this beat's figure: make the pictures it needs, write the code, check it, mend it, finish."),
  ];
  const system: Part[] = [part("role", "Role", "rules", ROLE), part("rules", "Code, pictures, how to work", "rules", RULES),
    part("timing-rules", "Timing the figure to the voice", "rules", TIMING)];
  const messages: Msg[] = [
    { role: "system", content: render(system) },
    { role: "user", content: figureData.length ? [{ type: "text", text: render(userParts) }, ...figureData.map((url) => ({ type: "image_url", image_url: { url } }))] : render(userParts) },
  ];

  let lastGood: { code: string; area?: string } | undefined;
  let finished: { code: string; area?: string; summary?: string } | undefined;
  let checks = 0;
  try {
    for (let t = 1; t <= MAX_TURNS && !finished; t++) {
      if (o.stop?.()) {
        state.status = "stopped";
        break;
      }
      state.turns = t;
      const history = state.steps.filter((s) => s.kind !== "think" || s.text).map((s) => `turn ${s.turn}: ${s.kind}${s.args?.name ? ` "${s.args.name}"` : ""}${s.errors?.length ? ` -> errors: ${s.errors.join("; ")}` : s.kind === "check" ? " -> it runs" : ""}`);
      const call = newCall(run, { step: "manim-agent", label: `Manim agent: lecture ${n}, beat ${beat}, turn ${t}`, lecture: n, model: state.model,
        prompt: { system, user: t === 1 ? userParts : [...userParts, part("sofar", `So far (${history.length} steps)`, "context", history), part("next", "This turn", "ask", "Go on: the next tool.")] } });
      sl.calls.push(call.id);
      b.calls.push(call.id);
      saveRun(run);
      const reply = await turn(call, messages, () => fakeTurn(t, state, said, made.map((i) => i.name)));
      state.cost += call.cost;
      if (!reply) throw new Error(`turn ${t}: the call failed: ${call.error ?? "no reply"}`);
      if (reply.text?.trim()) step({ turn: t, kind: "think", call: call.id, text: reply.text.trim().slice(0, 1500) });
      if (!reply.calls.length) {
        messages.push({ role: "assistant", content: reply.text ?? "" });
        messages.push({ role: "user", content: "Use a tool: make_image, check or finish." });
        continue;
      }
      messages.push({ role: "assistant", content: reply.text ?? null, tool_calls: reply.calls.map((c) => ({ id: c.id, type: "function", function: c.function })) });
      const seen: { url: string; what: string }[] = [];
      for (const c of reply.calls) {
        const args = safeJson(c.function.arguments);
        if (c.function.name === "make_image") {
          if (state.images.length >= MAX_IMAGES && !imagesOf(run, n)[String(args.name)]) {
            messages.push({ role: "tool", tool_call_id: c.id, content: `No more pictures: at most ${MAX_IMAGES} for a figure. Use the ones made.` });
            step({ turn: t, kind: "error", call: call.id, args, errors: ["too many pictures"] });
            continue;
          }
          const img = await makeImage(run, n, beat, state, args, look);
          state.cost += img.cost;
          step({ turn: t, kind: "image", call: img.call, args: { name: img.name, what: img.what, kind: img.kind }, image: img.url, errors: img.error ? [img.error] : undefined });
          messages.push({ role: "tool", tool_call_id: c.id, content: img.status === "done"
            ? `Made "${img.name}" (${img.kind}). Use it as image("${img.name}", height=...). It is shown to you below.` : `It could not be made: ${img.error}. Do without it, or ask again in other words.` });
          if (img.file && img.status === "done") seen.push({ url: (await imageData(img.file))!, what: `The picture "${img.name}" you made:` });
        } else if (c.function.name === "check" || c.function.name === "preview" || c.function.name === "finish") {
          const code = String(args.code ?? "");
          const area = args.area === "left" ? "left" : undefined;
          const finishing = c.function.name === "finish";
          if (finishing && lastGood?.code === code) {
            finished = { code, area, summary: String(args.summary ?? "") };
            step({ turn: t, kind: "finish", call: call.id, args: { code, area, summary: args.summary } });
            messages.push({ role: "tool", tool_call_id: c.id, content: "Done." });
            continue;
          }
          checks += 1;
          const k = await checkCode(run, n, beat, state.id, code, area, `c${checks}`);
          step({ turn: t, kind: finishing ? "finish" : "check", call: call.id, args: { code, area, ...(args.summary ? { summary: args.summary } : {}) },
            errors: k.errors.length ? k.errors : undefined, text: k.notes.length ? k.notes.join("\n") : undefined, seconds: k.seconds });
          if (!k.errors.length) lastGood = { code, area };
          if (finishing && !k.errors.length) {
            finished = { code, area, summary: String(args.summary ?? "") };
            messages.push({ role: "tool", tool_call_id: c.id, content: "Done." });
          } else {
            messages.push({ role: "tool", tool_call_id: c.id, content: k.errors.length
              ? `It does not run. The compiler says:\n${k.errors.join("\n")}\nMend it and check again.`
              : `It runs (checked in ${k.seconds.toFixed(0)} s)${k.notes.length ? `; the compiler notes: ${k.notes.join("; ")}` : ""}. Finish, or improve it and check again.` });
          }
        } else {
          messages.push({ role: "tool", tool_call_id: c.id, content: `No tool "${c.function.name}": make_image, check or finish.` });
        }
      }
      if (seen.length) messages.push({ role: "user", content: seen.flatMap((s) => [{ type: "text", text: s.what }, { type: "image_url", image_url: { url: s.url } }]) });
      saveRun(run);
    }
    const kept = finished ?? lastGood;
    if (!kept) throw new Error(state.status === "stopped" ? "stopped before any code ran" : `no code checked without errors in ${MAX_TURNS} turns`);
    const op: Record<string, unknown> = { op: "manim", id, code: kept.code, ...(kept.area === "left" ? { area: "left" } : {}), ...(plan ? { plan } : {}) };
    // The figure is the beat's visual: its heading stays, the rest makes way for it (a manim block is the only visual on its beat).
    b.ops = [...b.ops.filter((x) => x.op === "panel"), op];
    Object.assign(state, { status: state.status === "stopped" ? "stopped" : "done", code: kept.code, area: kept.area, summary: finished?.summary ?? "(the last code that checked: it did not finish)",
      ended: Date.now() });
    Object.assign(b, { status: "done", errors: undefined, edited: false });
  } catch (error) {
    Object.assign(state, { status: "failed", error: (error as Error).message, ended: Date.now() });
    b.status = b.ops.length ? "done" : "failed";
    step({ turn: state.turns, kind: "error", errors: [(error as Error).message] });
  }
  saveRun(run);
}

/** The stand-in's turns (no key): a picture, a check of the code using it, then finish. */
function fakeTurn(t: number, state: ManimAgentState, said: string, made: string[]) {
  const name = made[0] ?? "subject";
  const words = said.replace(/[^\p{L}\s]/gu, "").split(/\s+/).filter((w) => w.length > 4).slice(0, 2).join(" ") || "the idea";
  const code = [
    `pic = image("${name}", height=2.6)`,
    "pic.move_to(LEFT * 3.2)",
    `title = Text(${JSON.stringify(words.slice(0, 24))}, font_size=30, color=INK).move_to(RIGHT * 2.8 + UP * 1.2)`,
    "arrow = Arrow(pic.get_right(), title.get_left() + DOWN * 0.1, color=PALETTE[\"GOLD\"], buff=0.2)",
    "self.play(FadeIn(pic), run_time=1)",
    "self.play(Write(title), GrowArrow(arrow), run_time=1.5)",
  ].join("\n");
  if (t === 1 && !made.length) return { text: "A picture of the subject will help: I make it first.", calls: [{ name: "make_image", args: { name, what: `an illustration of ${words}`, kind: "cutout" } }] };
  if (!state.steps.some((s) => s.kind === "check" && !s.errors?.length)) return { text: "Placing the picture on the left and the words on the right.", calls: [{ name: "check", args: { code } }] };
  return { text: "It runs.", calls: [{ name: "finish", args: { code, summary: `the picture "${name}" with its idea beside it` } }] };
}
