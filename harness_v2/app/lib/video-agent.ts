/**
 * The video agent: one chapter's whole video, built in free Manim the way a coding agent builds a program. Nothing
 * is given to it but the chapter's narration (every line and word with its time, the voice itself), a screenshot of
 * the look wanted, and a workspace; no primitives, templates or layouts. It works in turns with tools:
 *
 *   write_file, edit_file, read_file, list_files  its workspace (its scene, notes, helpers)
 *   shell                                          a command in the workspace (fonts, data, a quick test), unless
 *                                                  V2_VIDEO_AGENT_SHELL=off
 *   render                                         Manim renders the scene (30 fps, the phone's rate)
 *   look                                           frames of the last render at given times, or a sheet of them
 *   make_image                                     the image model draws a picture into assets/
 *   phone_check                                    the scene played as the phone plays it, frames compared with Manim's
 *   finish                                         done: allowed only once the phone plays what Manim drew
 *
 * The one hard rule is the phone: the chapter must play on the phone (and the web player) exactly as Manim drew it,
 * which phone_check measures (engine/tools/agent_tools.py). Every turn is a call; every step is kept on the chapter
 * (run.video.chapters[...].agent) for the page.
 */

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { copyFile, mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import sharp from "sharp";
import { callImage } from "./images";
import { usingFixture } from "./llm";
import { engineDir } from "./maps";
import { pythonPath, runPython } from "./manim";
import { part } from "./prompts/parts";
import { imageData, newCall } from "./run";
import { fileUrl, scenesDir } from "./scenes";
import { saveRun } from "./store";
import type { Call, ChapterAgent, Run, VideoStep } from "./types";
import { chapterVideo, settingsOf, timingOf, workspaceOf, type Timing } from "./video";

const URL_ = process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions";
const TIMEOUT_MS = 600_000;
const SHELL = (process.env.V2_VIDEO_AGENT_SHELL ?? "on").toLowerCase() !== "off";
const MAX_IMAGES = Math.max(0, Number(process.env.V2_VIDEO_AGENT_IMAGES) || 12);
/** Pictures kept in the conversation: older ones are replaced by a note, so a long build stays affordable. */
const KEEP_IMAGES = 3;
const SCENE_FILE = "scene.py";
const SCENE_CLASS = "Chapter";

const fn = (name: string, description: string, properties: Record<string, unknown>, required: string[] = []) =>
  ({ type: "function", function: { name, description, parameters: { type: "object", properties, required } } });

const TOOLS = [
  fn("write_file", "Write a file in your workspace (whole), creating folders as needed.", {
    path: { type: "string", description: "A path inside the workspace, e.g. scene.py, plan.md, helpers/maps.py." },
    content: { type: "string" } }, ["path", "content"]),
  fn("edit_file", "Replace text in a file of your workspace: `old` must occur exactly once (or set all).", {
    path: { type: "string" }, old: { type: "string" }, new: { type: "string" }, all: { type: "boolean" } }, ["path", "old", "new"]),
  fn("read_file", "Read a file of your workspace, with line numbers (a range of lines if long).", {
    path: { type: "string" }, from: { type: "integer" }, to: { type: "integer" } }, ["path"]),
  fn("list_files", "List the files of your workspace (or of a folder in it), with sizes.", { path: { type: "string" } }),
  ...(SHELL ? [fn("shell", "Run a shell command in your workspace (bash; `python` is the Python that has Manim, numpy, shapely, cartopy, PIL). For what files cannot do: list fonts (fc-list), test a snippet, compute geometry, read map data. Output is cut to its last 6000 characters.", {
    command: { type: "string" }, timeout: { type: "integer", description: "Seconds, at most 600 (default 120)." } }, ["command"])] : []),
  fn("render", `Render ${SCENE_FILE} (class ${SCENE_CLASS}) with Manim at 30 fps: draft 854x480 (fast, for looking), final 1280x720. Returns its length against the narration's, or the error.`, {
    quality: { type: "string", enum: ["draft", "final"] } }),
  fn("look", "See the last render: frames at the times you give (seconds; up to 8), or a sheet of frames every N seconds over the whole video (each stamped with its time). You are shown the pictures.", {
    times: { type: "array", items: { type: "number" } }, sheet_every: { type: "number", description: "Seconds between the sheet's frames (default: about 16 frames over the video)." } }),
  fn("make_image", `Have the image model draw a picture into assets/<name>.png (you are shown it). At most ${MAX_IMAGES} a chapter. Use it in Manim with ImageMobject.`, {
    name: { type: "string", description: "Letters, digits and _ only." },
    what: { type: "string", description: "The whole picture, in English, as it is to be drawn: subject, view, medium and style, colours, mood. No text will be in it." },
    kind: { type: "string", enum: ["cutout", "scene"], description: "cutout: one subject on a clear background (white made transparent); scene: a full-bleed picture." } },
    ["name", "what", "kind"]),
  fn("phone_check", "Export the scene as the phone plays it and compare the phone's frames with the last render's at evenly spread times. Returns whether they match, the program's size and length, and shows you the worst pair (phone left, Manim right). Render first: it compares against the last render.", {
    samples: { type: "integer", description: "How many times to compare (default 12, at most 40)." } }),
  fn("finish", "The chapter is done. Allowed only when the last phone_check passed on the scene as it is now.", {
    summary: { type: "string", description: "A few lines: what the video shows, line by line in broad strokes, and the pictures and maps in it." } }, ["summary"]),
];

function roleText(style: { note?: string; custom: boolean }, turns: number): string {
  return [
    "You are the video agent of an explainer channel. You build ONE chapter of a narrated lesson as a finished video, in",
    "Manim Community (Python), by yourself, end to end: you decide what is on screen, how it moves and how it looks. There",
    "are no templates, primitives or layouts to use: you write the scene from nothing, as a motion designer who codes.",
    "",
    "WHAT YOU HAVE",
    "- The narration: the chapter is already spoken. timing.json in your workspace has every line with its start and end,",
    "  and every word with its own, in seconds on the chapter's track (chapter.wav); they are also below. The video is built",
    "  to the voice: it lasts as long as the narration, and each thing appears or changes on the words that name it.",
    "- narrated.py (in your workspace): `from narrated import NarratedScene`. Subclass it as `class Chapter(NarratedScene)`",
    "  in scene.py. It adds the voice to the scene and tells you the time; nothing else:",
    "    self.now                          seconds into the chapter so far",
    "    self.line(n)                      line n (0-based): {text, start, end, words: [{w, start, end}]}",
    "    self.word(n, \"Japan\", occurrence=0) when that word is said in line n (matched by its start, case aside)",
    "    self.phrase(n, \"string of islands\") when that run of words begins in line n",
    "    self.wait_until(t, lead=0.0)       hold until lead seconds before t (nothing if passed)",
    "    self.wait_until_end()              hold to the end of the narration; call it last",
    "  Plays take their run_time; between them, wait_until the next word. Start an animation a little before its word",
    "  (lead 0.1-0.3) so it lands as the word is said.",
    `- A screenshot of the look wanted (attached${style.custom ? ", chosen for this lesson" : ": a Vox-like explainer"}). Match its feel: its palette, type,`,
    "  textures, how labels and highlights look, how busy a frame is. It is a look, not a layout: compose each moment yourself.",
    ...(style.note ? [`  About the look: ${style.note}`] : []),
    "- Tools to write and edit files, render, look at frames, make pictures, run commands, and check the phone.",
    "",
    "THE ONE HARD RULE: THE PHONE",
    "The video is not shipped as an MP4. The phone (and the web player) play the scene as a program recorded from Manim, and",
    "it must look exactly as Manim drew it. Every play is recorded as Manim draws it, frame by frame, so almost anything",
    "Manim does plays, with these limits:",
    "- A 2D Scene (NarratedScene). No ThreeDScene, no MovingCameraScene or camera frame moves: to zoom or pan, scale and",
    "  move the groups themselves (a map zooming in is the map's VGroup scaled about a point).",
    "- Pictures (PNG, JPG) as ImageMobject are fine. Load files by absolute path: Path(__file__).resolve().parent / \"assets\" / ...",
    "- Size: every frame of motion costs bytes; a still hold costs nothing. Keep the program under about 20 MB for the",
    "  chapter (phone_check says its size): no endless idle motion, no updaters ticking through long holds, no needless",
    "  points (simplify map outlines).",
    "- phone_check must pass before you finish: it exports the scene and compares the phone's frames with the render's.",
    "",
    "HOW TO WORK (as a careful engineer works)",
    "1. Read the narration. Write plan.md: the chapter's moments, each with its lines and times, what is on screen and",
    "   which words drive what. One clear idea on screen at a time; something meaningful changes every few seconds.",
    "2. Build scene.py in pieces you can check: render a draft early, look at a sheet of frames, then frames at the",
    "   moments that matter (where things land on words, where text could overlap or leave the frame). Fix what you see.",
    "   Look before you believe: a frame shows overlaps, cut-off text, unreadable sizes and empty screens that code hides.",
    "3. The frame is x -7.1..7.1, y -4..4 (16:9). Keep everything inside with a margin; text at least font_size 24.",
    "   Fonts: use what is installed (shell: fc-list); the narration may be in Hindi or Hinglish: Devanagari needs a font",
    "   that has it (Noto Sans Devanagari, Hind). Subtitles are your choice.",
    "4. When it is right, render final, run phone_check, and finish. If the phone differs, find why (an unsupported",
    "   feature, a camera move) and change the scene.",
    `You have at most ${turns} turns: plan, then build steadily; do not stop at a first draft that you have not looked at.`,
    "Every tool call is a turn. Say briefly what you are doing and why as you go.",
  ].join("\n");
}

function narrationText(t: Timing): string {
  const rows = [`The narration: ${t.seconds.toFixed(1)} s, ${t.lines.length} lines (word times from ${t.source ?? "the voice"}).`];
  for (const l of t.lines) {
    rows.push(`[${l.n}] ${l.start.toFixed(2)}-${l.end.toFixed(2)}  ${l.text}`);
    rows.push(`    ${l.words.map((w) => `${w.w}@${w.start.toFixed(2)}`).join(" ")}`);
  }
  return rows.join("\n");
}

type Msg = { role: "system" | "user" | "assistant" | "tool"; content: unknown; tool_calls?: unknown[]; tool_call_id?: string };
type ToolCall = { id: string; function: { name: string; arguments: string } };
type Fake = { text?: string; calls: { name: string; args: Record<string, unknown> }[] };

function safeJson(text: string): Record<string, unknown> {
  try {
    const v = JSON.parse(text || "{}");
    return v && typeof v === "object" ? v as Record<string, unknown> : {};
  } catch {
    return { _unreadable: text.slice(0, 400) };
  }
}

/** One turn of the model: the conversation, the tools; what it said and the tools it called. */
async function turn(call: Call, messages: Msg[], fake: () => Fake): Promise<{ text?: string; calls: ToolCall[] } | null> {
  call.provider = usingFixture(call.model) ? "fixture" : "openrouter";
  const body = { model: call.model, messages, tools: TOOLS, tool_choice: "required", usage: { include: true },
    ...(call.effort && call.effort !== "off" ? { reasoning: { effort: call.effort } } : {}) };
  // What is kept of the request: its size, not the whole conversation again each turn.
  call.request = { model: call.model, messages: messages.length, tools: TOOLS.map((t) => t.function.name), chars: JSON.stringify(messages).length };
  for (let attempt = 1; attempt <= 3; attempt++) {
    const began = Date.now();
    try {
      let out: { text?: string; calls: ToolCall[] };
      if (call.provider === "fixture") {
        const f = fake();
        out = { text: f.text, calls: f.calls.map((c, i) => ({ id: `fake_${Date.now()}_${i}`, function: { name: c.name, arguments: JSON.stringify(c.args) } })) };
        call.usage = { input: Math.round(JSON.stringify(messages).length / 4), output: Math.round(JSON.stringify(f).length / 4) };
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
      call.output = { said: out.text, tools: out.calls.map((c) => ({ name: c.function.name, args: brief(safeJson(c.function.arguments)) })) };
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

/** Arguments as kept on a step: a long text (a whole file) cut, its length said. */
function brief(args: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(args).map(([k, v]) => [k, typeof v === "string" && v.length > 4000 ? `${v.slice(0, 4000)}\n… (${v.length} characters)` : v]));
}

/** A path inside the workspace, or an error. */
function inside(ws: string, p: unknown): string {
  const file = path.resolve(ws, String(p ?? "").trim() || ".");
  if (file !== ws && !file.startsWith(ws + path.sep)) throw new Error(`${p}: outside your workspace`);
  return file;
}

/** The environment without its keys and secrets: what the agent runs reaches the model, so no key goes near it. */
function withoutSecrets(): NodeJS.ProcessEnv {
  return Object.fromEntries(Object.entries(process.env).filter(([k, v]) => v !== undefined && !/KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH/i.test(k))) as NodeJS.ProcessEnv;
}

function sh(command: string, cwd: string, timeout: number): Promise<{ code: number | null; out: string }> {
  return new Promise((resolve) => {
    const bin = path.dirname(pythonPath());
    const child = spawn("bash", ["-c", command], { cwd, env: { ...withoutSecrets(), PATH: `${bin}:${process.env.PATH ?? ""}`,
      PANIM_NARRATION_DIR: cwd, PYTHONPATH: [cwd, path.join(engineDir(), "agent")].join(":") } });
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    const timer = setTimeout(() => { child.kill("SIGKILL"); out += `\nstopped: over ${timeout / 1000} s`; }, timeout);
    child.on("close", (code) => { clearTimeout(timer); resolve({ code, out }); });
    child.on("error", (e) => { clearTimeout(timer); resolve({ code: -1, out: String(e) }); });
  });
}

async function tool(kind: string, args: string[], ws: string, timeout = 1_800_000): Promise<Record<string, unknown>> {
  const out = await runPython([path.join(engineDir(), "tools", "agent_tools.py"), kind, ...args], ws, {}, undefined, timeout);
  try {
    return JSON.parse(out.stdout.trim().split("\n").pop() ?? "");
  } catch {
    return { ok: false, error: out.out.slice(-1500) || "the tool said nothing" };
  }
}

const hashOf = async (file: string) => createHash("sha1").update(await readFile(file).catch(() => Buffer.alloc(0))).digest("hex");

/** White round a cutout made clear. */
async function clearWhite(bytes: Buffer): Promise<Buffer> {
  const { data, info } = await sharp(bytes).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  for (let i = 0; i < data.length; i += 4) {
    const light = Math.min(data[i], data[i + 1], data[i + 2]);
    if (light > 238) data[i + 3] = 0;
    else if (light > 222) data[i + 3] = Math.round(255 * (238 - light) / 16);
  }
  return sharp(data, { raw: { width: info.width, height: info.height, channels: 4 } }).png().toBuffer();
}

/** The stand-in agent (no key): a plain scene, rendered, looked at, checked on the phone, finished. */
function scriptedAgent(t: Timing): () => Fake {
  const scene = [
    "from pathlib import Path",
    "from manim import *",
    "from narrated import NarratedScene",
    "",
    "PAPER, INK, RED = \"#F1E9DA\", \"#1D1D1B\", \"#E5383B\"",
    "",
    "",
    "class Chapter(NarratedScene):",
    "    def construct(self):",
    "        self.camera.background_color = PAPER",
    "        for n, line in enumerate(self.lines):",
    "            self.wait_until(line[\"start\"], lead=0.2)",
    "            words = [w[\"w\"] for w in line[\"words\"]][:4]",
    "            head = Text(\" \".join(words), font_size=44, color=INK)",
    "            if head.width > 12:",
    "                head.scale_to_fit_width(12)",
    "            bar = Rectangle(width=head.width + 0.4, height=0.18, fill_color=RED, fill_opacity=1, stroke_width=0)",
    "            bar.next_to(head, DOWN, buff=0.15)",
    "            self.play(FadeIn(head, shift=UP * 0.2), GrowFromEdge(bar, LEFT), run_time=0.5)",
    "            self.wait_until(line[\"end\"], lead=0.3)",
    "            self.play(FadeOut(head), FadeOut(bar), run_time=0.3)",
    "        self.wait_until_end()",
    "",
  ].join("\n");
  const plan = ["# Plan", "", ...t.lines.map((l) => `- [${l.n}] ${l.start.toFixed(1)}-${l.end.toFixed(1)}: the line's first words, underlined in red`)].join("\n");
  const steps: Fake[] = [
    { text: "Planning the chapter.", calls: [{ name: "write_file", args: { path: "plan.md", content: plan } }] },
    { text: "Writing the scene.", calls: [{ name: "write_file", args: { path: "scene.py", content: scene } }] },
    { text: "Rendering a draft.", calls: [{ name: "render", args: { quality: "draft" } }] },
    { text: "Looking at it.", calls: [{ name: "look", args: {} }] },
    { text: "Checking the phone.", calls: [{ name: "phone_check", args: { samples: 6 } }] },
    { text: "Done.", calls: [{ name: "finish", args: { summary: "Each line's first words, underlined in red, on paper (the stand-in agent: no model key)." } }] },
  ];
  let k = 0;
  return () => steps[Math.min(k++, steps.length - 1)];
}

/** The agent on one chapter (its narration spoken). */
export async function runVideoAgent(run: Run, n: number, c: number, o: { note?: string; stop?: () => boolean } = {}): Promise<void> {
  const cv = chapterVideo(run, n, c);
  const settings = settingsOf(run);
  const ws = workspaceOf(run.id, n, c);
  await mkdir(path.join(ws, "assets"), { recursive: true });
  const timing = await timingOf(run.id, n, c);
  if (!timing) throw new Error(`chapter ${c} has no narration: speak it first`);
  await copyFile(path.join(engineDir(), "agent", "narrated.py"), path.join(ws, "narrated.py"));
  const styleFile = path.join(ws, "style" + path.extname(settings.style));
  await copyFile(settings.style, styleFile);
  const agent: ChapterAgent = { status: "running", model: settings.model, imageModel: settings.imageModel, note: o.note, started: Date.now(),
    turns: 0, cost: 0, steps: [] };
  cv.agent = agent;
  saveRun(run, true);
  const step = (s: Omit<VideoStep, "at">) => { agent.steps.push({ ...s, at: Date.now() }); saveRun(run); };

  const custom = path.resolve(settings.style) !== path.resolve(path.join(engineDir(), "agent", "style-vox.jpg"));
  const system = roleText({ note: settings.styleNote, custom }, settings.turns);
  const existing = existsSync(path.join(ws, SCENE_FILE));
  const ask = [
    `Lecture ${n}, chapter ${c}: "${run.script?.lectures[n]?.chapters.find((x) => x.n === c)?.title ?? ""}". Build its video.`,
    `Lesson: ${run.lectures.find((l) => l.n === n)?.title ?? ""}; book: ${run.documentName}.`,
    existing ? `Your workspace already has a ${SCENE_FILE} from an earlier build: read it, and improve it rather than starting over unless it is wrong.` : "",
    o.note ? `A note from the person you build for: ${o.note}` : "",
    "",
    narrationText(timing),
  ].filter((x) => x !== "").join("\n");
  const styleData = await imageData(styleFile);
  const messages: Msg[] = [
    { role: "system", content: system },
    { role: "user", content: [{ type: "text", text: ask }, ...(styleData ? [{ type: "image_url", image_url: { url: styleData } }] : [])] },
  ];
  const fake = scriptedAgent(timing);
  let lastRender: { video?: string; hash?: string; seconds?: number } = {};
  let lastCheck: { ok: boolean; hash?: string; result?: Record<string, unknown> } = { ok: false };
  let images = 0;
  let firstPrompt = true;

  /** Pictures for the model: a user message after the tool results; older pictures are dropped from the conversation. */
  const show = async (label: string, files: string[]) => {
    const data = (await Promise.all(files.map((f) => imageData(f)))).filter((d): d is string => !!d);
    if (!data.length) return;
    messages.push({ role: "user", content: [{ type: "text", text: label }, ...data.map((url) => ({ type: "image_url", image_url: { url } }))] });
    const withImages = messages.map((m, i) => ({ m, i })).filter(({ m, i }) => i > 1 && Array.isArray(m.content)
      && (m.content as { type: string }[]).some((x) => x.type === "image_url"));
    for (const { m } of withImages.slice(0, -KEEP_IMAGES)) {
      m.content = (m.content as { type: string; text?: string }[]).filter((x) => x.type === "text")
        .map((x) => ({ ...x, text: `${x.text} (pictures no longer shown)` }));
    }
  };

  const run1 = async (name: string, args: Record<string, unknown>): Promise<{ text: string; ok: boolean; images?: string[]; video?: string; seconds?: number; done?: boolean }> => {
    switch (name) {
      case "write_file": {
        const file = inside(ws, args.path);
        await mkdir(path.dirname(file), { recursive: true });
        await writeFile(file, String(args.content ?? ""), "utf8");
        return { ok: true, text: `wrote ${path.relative(ws, file)} (${String(args.content ?? "").split("\n").length} lines)` };
      }
      case "edit_file": {
        const file = inside(ws, args.path);
        const text = await readFile(file, "utf8");
        const old = String(args.old ?? "");
        const count = old ? text.split(old).length - 1 : 0;
        if (!count) return { ok: false, text: `${args.path}: the old text is not in the file (read it again)` };
        if (count > 1 && !args.all) return { ok: false, text: `${args.path}: the old text occurs ${count} times; give more of it, or set all` };
        await writeFile(file, args.all ? text.split(old).join(String(args.new ?? "")) : text.replace(old, () => String(args.new ?? "")), "utf8");
        return { ok: true, text: `edited ${args.path} (${args.all ? count : 1} place${count > 1 && args.all ? "s" : ""})` };
      }
      case "read_file": {
        const file = inside(ws, args.path);
        const lines = (await readFile(file, "utf8")).split("\n");
        const from = Math.max(1, Number(args.from) || 1);
        const to = Math.min(lines.length, Number(args.to) || from + 399);
        return { ok: true, text: lines.slice(from - 1, to).map((l, i) => `${from + i}\t${l}`).join("\n") + (to < lines.length ? `\n… (${lines.length} lines)` : "") };
      }
      case "list_files": {
        const dir = inside(ws, args.path ?? ".");
        const rows: string[] = [];
        for (const e of await readdir(dir, { withFileTypes: true, recursive: true })) {
          const full = path.join(e.parentPath ?? dir, e.name);
          const rel = path.relative(ws, full);
          if (!e.isFile() || /^(renders|export|media|__pycache__)\b/.test(rel) || rel.includes("__pycache__")) continue;
          rows.push(`${rel}  ${(await stat(full)).size} B`);
        }
        return { ok: true, text: rows.sort().join("\n") || "(empty)" };
      }
      case "shell": {
        if (!SHELL) return { ok: false, text: "the shell is off here" };
        const r = await sh(String(args.command ?? ""), ws, Math.min(600, Math.max(5, Number(args.timeout) || 120)) * 1000);
        return { ok: r.code === 0, text: `exit ${r.code}\n${r.out.slice(-6000)}` };
      }
      case "render": {
        if (!existsSync(path.join(ws, SCENE_FILE))) return { ok: false, text: `write ${SCENE_FILE} first` };
        const quality = args.quality === "final" ? "final" : "draft";
        const r = await tool("render", [ws, SCENE_FILE, SCENE_CLASS, quality], ws);
        if (!r.ok) return { ok: false, text: `the render failed:\n${r.error}` };
        lastRender = { video: String(r.video), hash: await hashOf(path.join(ws, SCENE_FILE)), seconds: Number(r.seconds) };
        const off = Number(r.seconds) - timing.seconds;
        return { ok: true, video: fileUrl(run.id, String(r.video)), seconds: Number(r.seconds),
          text: `rendered (${quality}): ${Number(r.seconds).toFixed(2)} s; the narration is ${timing.seconds.toFixed(2)} s` +
            (Math.abs(off) > 0.5 ? ` (${off > 0 ? "longer" : "shorter"} by ${Math.abs(off).toFixed(1)} s: end with self.wait_until_end(), and do not run past the voice)` : "") +
            (r.warnings ? `\nwarnings:\n${r.warnings}` : "") };
      }
      case "look": {
        if (!lastRender.video) return { ok: false, text: "render first" };
        const stale = lastRender.hash !== await hashOf(path.join(ws, SCENE_FILE)) ? " (the scene changed since this render)" : "";
        const times = Array.isArray(args.times) ? (args.times as unknown[]).map(Number).filter((x) => Number.isFinite(x) && x >= 0).slice(0, 8) : [];
        if (times.length) {
          const r = await tool("frames", [lastRender.video, path.join(ws, "renders", "look"), ...times.map(String)], ws);
          const files = ((r.frames as { t: number; file: string }[]) ?? []).map((f) => f.file);
          await show(`Frames at ${times.join(", ")} s${stale}:`, files);
          return { ok: files.length > 0, text: `${files.length} frame(s) shown${stale}`, images: files.map((f) => fileUrl(run.id, f)) };
        }
        const out = path.join(ws, "renders", `sheet-${Date.now()}.png`);
        const r = await tool("sheet", [lastRender.video, out, ...(Number(args.sheet_every) > 0 ? [String(args.sheet_every)] : [])], ws);
        if (!r.ok) return { ok: false, text: String(r.error) };
        await show(`A sheet of the render: frames at ${(r.times as number[]).join(", ")} s${stale}:`, [out]);
        return { ok: true, text: `sheet shown (${(r.times as number[]).length} frames${stale})`, images: [fileUrl(run.id, out)] };
      }
      case "make_image": {
        if (images >= MAX_IMAGES) return { ok: false, text: `at most ${MAX_IMAGES} pictures a chapter` };
        const name = String(args.name ?? "").replace(/[^\w]+/g, "_").slice(0, 40) || `picture_${images + 1}`;
        const kind = args.kind === "scene" ? "scene" : "cutout";
        const what = String(args.what ?? "").slice(0, 900);
        const text = kind === "cutout"
          ? `${what}. One subject alone, isolated on a plain pure white background, no shadow, no border. NO TEXT at all: no words, letters, numbers or labels.`
          : `${what}. A whole scene filling the image edge to edge, wide (16:9). NO TEXT at all: no words, letters, numbers or labels.`;
        const call = newCall(run, { step: "video-agent", label: `Video agent picture "${name}" (lecture ${n}, chapter ${c})`, lecture: n, model: settings.imageModel, effort: "off",
          prompt: { system: [], user: [part("what", "What it shows", "ask", text)] } });
        const out = await callImage({ call, text, fake: () => ({ bytes: Buffer.alloc(0), mime: "image/png" }), onChange: () => saveRun(run) });
        agent.cost += call.cost;
        if (!out) return { ok: false, text: `the image model failed: ${call.error ?? "no image"}` };
        const raw = out.bytes.length ? out.bytes : await sharp({ create: { width: 640, height: kind === "scene" ? 360 : 640, channels: 3, background: "#c9b38f" } }).png().toBuffer();
        const file = path.join(ws, "assets", `${name}.png`);
        await writeFile(file, kind === "cutout" ? await clearWhite(raw) : await sharp(raw).png().toBuffer());
        images += 1;
        const meta = await sharp(file).metadata();
        await show(`The picture assets/${name}.png (${meta.width}x${meta.height}):`, [file]);
        return { ok: true, text: `made assets/${name}.png (${meta.width}x${meta.height}, ${kind})`, images: [fileUrl(run.id, file)] };
      }
      case "phone_check": {
        const hash = await hashOf(path.join(ws, SCENE_FILE));
        if (!lastRender.video || lastRender.hash !== hash) return { ok: false, text: "render the scene as it is now first: the check compares the phone with the last render" };
        const samples = Math.min(40, Math.max(3, Number(args.samples) || 12));
        const r = await tool("phone", [ws, SCENE_FILE, SCENE_CLASS, path.join(ws, "export"), lastRender.video, String(samples)], ws);
        if (r.ok === false && r.error) return { ok: false, text: `the export failed:\n${r.error}` };
        const check = r.check as { ok: boolean | null; frames: number; differ: { t: number; mean: number; differ: number }[] };
        const ok = !!r.ok;
        lastCheck = { ok, hash, result: r };
        const worst = r.worst as { t: number; phone: string; manim: string } | undefined;
        if (worst?.phone && worst.manim) {
          const pair = path.join(ws, "export", "worst.png");
          await sharp({ create: { width: 1920, height: 540, channels: 3, background: "#000" } })
            .composite([{ input: worst.phone, left: 0, top: 0 }, { input: worst.manim, left: 960, top: 0 }]).png().toFile(pair);
          await show(`phone_check: the pair that differs most, at ${worst.t} s (phone left, Manim right):`, [pair]);
        }
        const mb = (Number(r.bytes) / 1e6).toFixed(1);
        return { ok, text: [
          ok ? "the phone plays it as Manim drew it" : "the phone does NOT play it as Manim drew it",
          `program: ${r.seconds} s, ${mb} MB, tier ${r.tier}${(r.blockers as string[])?.length ? `, blocked by: ${(r.blockers as string[]).join("; ")}` : ""}`,
          `frames compared: ${check?.frames ?? 0}; differing: ${check?.differ?.length ? check.differ.map((d) => `${d.t}s (mean ${d.mean}, ${Math.round(d.differ * 100)}% of pixels)`).join(", ") : "none"}`,
          Number(r.bytes) > 20e6 ? "the program is large: cut needless motion and points" : "",
          r.geometry === false ? `the web player's geometry was not made: ${r.geometry_error ?? "too large"}` : "",
        ].filter(Boolean).join("\n") };
      }
      case "finish": {
        const hash = await hashOf(path.join(ws, SCENE_FILE));
        if (!lastCheck.ok || lastCheck.hash !== hash) return { ok: false, text: "not yet: render the scene as it is now and run phone_check; finish when it passes" };
        agent.summary = String(args.summary ?? "").slice(0, 3000);
        const r = lastCheck.result!;
        const out = path.join(ws, "export");
        const rel = (f: string) => encodeURIComponent(path.relative(scenesDir(run.id), f));
        cv.build = { at: Date.now(), ir: `/api/runs/${run.id}/scenes/ir?p=${rel(out)}&v=${Date.now()}`,
          assets: `/api/runs/${run.id}/scenes/file?p=${rel(path.join(out, "dsl", "generated", "images"))}${encodeURIComponent("/")}`,
          audio: r.narration ? fileUrl(run.id, path.join(out, String(r.narration))) : undefined,
          video: lastRender.video ? fileUrl(run.id, lastRender.video) : undefined,
          seconds: Number(r.seconds), bytes: Number(r.bytes), tier: Number(r.tier), blockers: (r.blockers as string[]) ?? [],
          check: r.check as never };
        return { ok: true, done: true, text: "finished" };
      }
      default:
        return { ok: false, text: `no tool ${name}` };
    }
  };

  try {
    for (let k = 1; k <= settings.turns; k++) {
      if (o.stop?.()) {
        agent.status = "stopped";
        break;
      }
      agent.turns = k;
      const call = newCall(run, { step: "video-agent", label: `Video agent, turn ${k} (lecture ${n}, chapter ${c})`, lecture: n, model: settings.model,
        prompt: firstPrompt
          ? { system: [part("role", "The video agent's instructions", "rules", system)], user: [part("chapter", "The chapter and its narration", "ask", ask)] }
          : { system: [], user: [part("turn", "The turn", "context", `turn ${k}: the conversation so far (${messages.length} messages)`)] } });
      firstPrompt = false;
      const answer = await turn(call, messages, fake);
      agent.cost += call.cost;
      if (!answer) {
        step({ turn: k, kind: "error", call: call.id, text: call.error ?? "the model did not answer" });
        agent.status = "failed";
        agent.error = call.error ?? "the model did not answer";
        break;
      }
      if (answer.text?.trim()) step({ turn: k, kind: "think", call: call.id, text: answer.text.trim().slice(0, 4000) });
      messages.push({ role: "assistant", content: answer.text ?? "", tool_calls: answer.calls.map((t) => ({ id: t.id, type: "function", function: t.function })) });
      if (!answer.calls.length) {
        messages.push({ role: "user", content: "Use a tool: carry on building, or finish once phone_check has passed." });
        continue;
      }
      // Tool results go back in order, then any pictures they showed (user messages may follow tool messages only).
      const pending: Msg[] = [];
      const held = messages.length;
      let finished = false;
      for (const t of answer.calls) {
        const args = safeJson(t.function.arguments);
        let r: Awaited<ReturnType<typeof run1>>;
        try {
          r = await run1(t.function.name, args);
        } catch (error) {
          r = { ok: false, text: (error as Error).message.slice(0, 1500) };
        }
        pending.push({ role: "tool", tool_call_id: t.id, content: r.text });
        step({ turn: k, kind: r.done ? "finish" : "tool", tool: t.function.name, call: call.id, args: brief(args), result: r.text.slice(0, 6000), ok: r.ok,
          images: r.images, video: r.video, seconds: r.seconds });
        if (r.done) finished = true;
      }
      // The pictures `show` added while the tools ran belong after the tool results.
      const shown = messages.splice(held);
      messages.push(...pending, ...shown);
      if (finished) {
        agent.status = "done";
        break;
      }
      if (k === settings.turns) {
        agent.status = "failed";
        agent.error = `out of turns (${settings.turns}) before it finished`;
      }
    }
  } catch (error) {
    agent.status = "failed";
    agent.error = (error as Error).message.slice(0, 1200);
  } finally {
    agent.ended = Date.now();
    saveRun(run, true);
  }
}
