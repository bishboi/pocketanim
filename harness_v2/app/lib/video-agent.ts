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
import { appendFile, copyFile, mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import sharp from "sharp";
import { callImage } from "./images";
import { usingFixture } from "./llm";
import { respond, useOpenAI } from "./openai-responses";
import { engineDir } from "./maps";
import { pythonPath, runPython } from "./manim";
import { detachedForAbort, killOnAbort, killTree, stopped, timeoutOrAbort } from "./abort";
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
/** Room for a whole scene in one reply: without it a provider's default cut a long file off mid-write. */
const MAX_TOKENS = Math.max(4000, Number(process.env.V2_VIDEO_AGENT_MAX_TOKENS) || 32000);
/** Past this many input tokens a turn, the conversation is condensed into a summary (the files stay as they are). */
const COMPACT_TOKENS = Math.max(4000, Number(process.env.V2_VIDEO_AGENT_COMPACT_TOKENS) || 150000);
/** Reasoning chosen turn by turn: the level set for thinking turns, low for the mechanical ones (V2_VIDEO_AGENT_ADAPTIVE_EFFORT=off: always the level set). */
const ADAPTIVE = (process.env.V2_VIDEO_AGENT_ADAPTIVE_EFFORT ?? "on").toLowerCase() !== "off";
/** A whole draft render and phone check made in the background while the model thinks (V2_VIDEO_AGENT_AHEAD=off: none). */
const AHEAD = (process.env.V2_VIDEO_AGENT_AHEAD ?? "on").toLowerCase() !== "off";
/** Frames shown to the model are this wide (enough to judge a layout, a third of the tokens of a full frame). */
/** Tools whose success needs no fresh thinking after it. */
const EASY = new Set(["read_file", "list_files"]);
const FRAME_WIDTH = Math.max(320, Number(process.env.V2_VIDEO_AGENT_FRAME_WIDTH) || 640);
const SCENE_FILE = "scene.py";
const SCENE_CLASS = "Chapter";
/** The conversation's log in the workspace. */
export const LOG_FILE = "agent-log.jsonl";

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
  ...(SHELL ? [fn("shell", "Run a shell command in your workspace (bash; `python` is the Python that has Manim, numpy, shapely, cartopy, PIL). For what files cannot do: list fonts (fc-list), test a snippet, compute geometry, read map data. Long output keeps its first and last 4000 characters (the middle is cut): read files with read_file, not cat.", {
    command: { type: "string" }, timeout: { type: "integer", description: "Seconds, at most 600 (default 120)." } }, ["command"])] : []),
  fn("render", `Render ${SCENE_FILE} (class ${SCENE_CLASS}) with Manim at 30 fps: draft 854x480 (fast, for looking), final 1280x720. You are shown a sheet of about 12 frames of it at once (stamped with their times); look: [times] also shows you frames at those times, in the same turn. from/to render only that stretch of the chapter (seconds on its clock; the plays before it run undrawn), much faster while you work on one moment. A whole render also runs phone_check (check: false skips it). A whole draft of your latest files is often already rendered and checked in the background by the time you ask.`, {
    quality: { type: "string", enum: ["draft", "final"] }, from: { type: "number" }, to: { type: "number" },
    check: { type: "boolean", description: "Whole renders only; default true." },
    look: { type: "array", items: { type: "number" }, description: "Times (seconds on the chapter's clock, up to 8) to see closer, as look does." } }),
  fn("look", "See the last render closer: frames at the times you give (seconds on the chapter's clock; up to 8), or a sheet of frames every N seconds. You are shown them once; look again if you need them later.", {
    times: { type: "array", items: { type: "number" } }, sheet_every: { type: "number", description: "Seconds between the sheet's frames." },
    detail: { type: "string", enum: ["high", "low"], description: "low: a cheap glance (layout only); high (default): to read text and details." } }),
  fn("kit_preview", "Render a snippet of Manim code small and see it before you use it: the code is the body of a KitScene's construct() (self is the scene; `from kit import *` is done; your workspace's assets/ are there), in a kit look. You are shown its last frame, and a sheet of frames when it animates. For trying a kit piece (KIT.md), a layout, a font or any idea; it does not touch scene.py.", {
    code: { type: "string", description: "Python statements, e.g. m = Map(\"east asia\"); self.add(m); self.play(m.shade(\"Japan\"))" },
    look: { type: "string", description: "vox (default) or blueprint, or another look name." } }, ["code"]),
  fn("make_image", `Have the image model draw a picture into assets/<name>.png (you are shown it). At most ${MAX_IMAGES} a chapter. Use it in Manim with ImageMobject.`, {
    name: { type: "string", description: "Letters, digits and _ only." },
    what: { type: "string", description: "The whole picture, in English, as it is to be drawn: subject, view, medium and style, colours, mood. No text will be in it." },
    kind: { type: "string", enum: ["cutout", "scene"], description: "cutout: one subject on a clear background (white made transparent); scene: a full-bleed picture." } },
    ["name", "what", "kind"]),
  fn("phone_check", "Export the scene as the phone plays it and compare the phone's frames with the last render's at evenly spread times. Returns whether they match, the program's size and length, and shows you the worst pair (phone left, Manim right). Render the whole chapter first (not a from/to section): it compares against the last render.", {
    samples: { type: "integer", description: "How many times to compare (default 12, at most 40)." } }),
  fn("finish", "The chapter is done. Allowed only when the last phone_check passed on the scene as it is now. First look at the video as a viewer would and list honestly what is still wrong with it (open_issues); while turns remain, finishing with open issues sends you back to fix them.", {
    summary: { type: "string", description: "A few lines: what the video shows, line by line in broad strokes, and the pictures and maps in it." },
    open_issues: { type: "array", items: { type: "string" }, description: "What you still see wrong (overlaps, cut or missing labels, words out of time, empty or static stretches, anything unlike the look). Empty when nothing is." } },
    ["summary", "open_issues"]),
];

/** NarratedScene's clock, as both modes are told it. */
const NARRATED_API = [
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
];

/** What the phone can play, as both modes are told it. */
const PHONE_RULES = [
  "THE ONE HARD RULE: THE PHONE",
  "The video is not shipped as an MP4. The phone (and the web player) play the scene as a program recorded from Manim, and",
  "it must look exactly as Manim drew it. Every play is recorded as Manim draws it, frame by frame, so almost anything",
  "Manim does plays, with these limits:",
  "- 2D: anything goes, except moving the camera: the phone has no 2D camera, so a moved self.camera.frame",
  "  (MovingCameraScene) is a blocker in the phone check. Zoom and pan by moving the stage instead (KitScene's cam_to,",
  "  cam_push, cam_pan, cam_reset do, as a camera would look), or move and scale the mobjects yourself.",
  "- 3D (ThreeDScene) is only partly supported on the phone: see-through solids lose faces and the web player cannot",
  "  preview it; prefer 2D.",
  "- Pictures (PNG, JPG) as ImageMobject are fine. Load files by absolute path: Path(__file__).resolve().parent / \"assets\" / ...",
  "- Size: every frame of motion costs bytes; a still hold costs nothing. Keep the program under about 20 MB for the",
  "  chapter (phone_check says its size): no endless idle motion, no updaters ticking through long holds, no needless",
  "  points (simplify map outlines).",
  "- phone_check must pass before you finish: it exports the scene and compares the phone's frames with the render's.",
];

/**
 * The lean mode's tools: the agent only writes its scene and looks at what it makes. Writing or editing renders the
 * whole chapter and checks it on the phone in the same turn; there is no shell, no other file, no image model.
 */
const LEAN_TOOLS = [
  fn("write_scene", `Write ${SCENE_FILE} whole. It is then rendered (the whole chapter, draft) and checked on the phone in the same turn: you are shown a sheet of frames, what the render measured and whether the phone plays it as Manim drew it, or the error.`, {
    content: { type: "string", description: "The whole file." } }, ["content"]),
  fn("edit_scene", `Change parts of ${SCENE_FILE}: each edit replaces \`old\` (which must occur exactly once, or set all) with \`new\`, in order; then it is rendered and checked as write_scene is. Put every change you want into one call: each call renders the whole chapter.`, {
    edits: { type: "array", items: { type: "object", properties: { old: { type: "string" }, new: { type: "string" }, all: { type: "boolean" } }, required: ["old", "new"] } } },
    ["edits"]),
  fn("look", "See the last render closer: frames at the times you give (seconds on the chapter's clock, up to 8), as one picture. Shown to you once.", {
    times: { type: "array", items: { type: "number" } },
    detail: { type: "string", enum: ["high", "low"], description: "low: a cheap glance (layout only); high (default): to read text." } }, ["times"]),
  fn("finish", "The chapter is done. Allowed only when the last render passed the phone check. First look at the video as a viewer would and list honestly what is still wrong with it (open_issues); while turns remain, finishing with open issues sends you back to fix them.", {
    summary: { type: "string", description: "A few lines: what the video shows, line by line in broad strokes." },
    open_issues: { type: "array", items: { type: "string" }, description: "What you still see wrong. Empty when nothing is." } },
    ["summary", "open_issues"]),
];

function leanRoleText(style: { note?: string; custom: boolean }, turns: number, kit: string): string {
  return [
    "You are the video agent of an explainer channel. You build ONE chapter of a narrated lesson as a finished video, in",
    "Manim Community (Python): you decide what is on screen, how it moves and how it looks, as a motion designer who codes.",
    "",
    "WHAT YOU HAVE",
    "- The narration: the chapter is already spoken; every line and every word with its time (seconds on the chapter's",
    "  track) is below. The video lasts as long as the narration, and each thing appears or changes on the words that name it.",
    ...NARRATED_API,
    `- A screenshot of the look wanted (attached${style.custom ? ", chosen for this lesson" : ": six frames of a Vox-like explainer"}). Match its feel: its palette, type,`,
    "  textures, how labels and highlights look, how busy a frame is. It is a look, not a layout: compose each moment yourself.",
    ...(style.note ? [`  About the look: ${style.note}`] : []),
    "- The kit: `from kit import *` gives all of Manim plus building blocks drawn in a look; `class Chapter(KitScene)` is",
    "  NarratedScene with the look's stage and camera moves. Its whole catalog is at the end of these instructions (the",
    "  kit_preview tool and the python commands it mentions are not available here). Plain Manim beside it is fine.",
    "",
    "HOW IT WORKS",
    `- You have one file, ${SCENE_FILE}, and three tools. write_scene writes it whole; edit_scene changes parts of it. Each`,
    "  renders the whole chapter (a draft, about a minute) and checks it on the phone in the same turn: you are shown a",
    "  sheet of frames stamped with their times, what the render measured (long still or empty stretches, words off the",
    "  frame or on top of words) and whether the phone plays it as Manim drew it; or the error if it failed.",
    "- look shows frames of the last render at the times you give, as one picture.",
    "- finish when it is right. There is no shell and no other file: everything the chapter needs is in the scene.",
    "",
    ...PHONE_RULES,
    "",
    "HOW TO WORK",
    "1. Read the narration and plan the chapter's moments in your head: one clear idea on screen at a time; something",
    "   meaningful changes every few seconds, landing on the words that name it.",
    "2. Write the whole scene in one write_scene: complete, every line of the narration covered, ending with",
    "   self.wait_until_end(). The frame is x -7.1..7.1, y -4..4: keep everything inside with a margin; text at least",
    "   font_size 24; Devanagari in a font that has it (the kit's text() picks one).",
    "3. Read what comes back: an error first; then the sheet and the measurements. Look closer only where it matters",
    "   (where things land, where text could overlap or leave the frame).",
    "4. Fix with edit_scene, every change in one call. Each render costs a minute and each turn costs money: aim to be",
    "   done in a handful of turns, not dozens.",
    "5. Finish when the phone check has passed and it looks right; list in open_issues what is still wrong.",
    `You have at most ${turns} turns. Every reply calls one tool. Say briefly what you are doing as you go.`,
    "",
    "THE KIT (KIT.md)",
    kit,
  ].join("\n");
}

function roleText(style: { note?: string; custom: boolean }, turns: number): string {
  return [
    "You are the video agent of an explainer channel. You build ONE chapter of a narrated lesson as a finished video, in",
    "Manim Community (Python), by yourself, end to end: you decide what is on screen, how it moves and how it looks, as a",
    "motion designer who codes. Nothing is laid out for you; a kit of building blocks is there if you want it.",
    "",
    "WHAT YOU HAVE",
    "- The narration: the chapter is already spoken. timing.json in your workspace has every line with its start and end,",
    "  and every word with its own, in seconds on the chapter's track (chapter.wav); they are also below. The video is built",
    "  to the voice: it lasts as long as the narration, and each thing appears or changes on the words that name it.",
    ...NARRATED_API,
    `- A screenshot of the look wanted (attached${style.custom ? ", chosen for this lesson" : ": six frames of a Vox-like explainer, a map, an archival collage, a data figure, a document, a timeline and a flow"}). Match its feel: its palette, type,`,
    "  textures, how labels and highlights look, how busy a frame is. It is a look, not a layout: compose each moment yourself.",
    ...(style.note ? [`  About the look: ${style.note}`] : []),
    "- The kit (optional; use any of it, none of it, or take pieces apart; plain Manim beside it is always fine).",
    "  `from kit import *` gives all of Manim plus building blocks drawn in a look (vox: paper, collage, marker, cutout",
    "  photos; blueprint: drafting grid, outlines, mono type). Each piece is a plain Manim mobject with .appear(),",
    "  .disappear(), .emphasize() in its look, and named parts. The main things:",
    "    class Chapter(KitScene): look = \"vox\"      NarratedScene + camera moves + the look's stage",
    "    self.at(n, \"word\") / self.until(t, lead)   the narration's clock",
    "    self.cam_to(mob_or_point, width=), cam_push(k), cam_pan(v), cam_reset(), camera_drift(speed)   camera moves (they move the stage)",
    "    self.wipe(then=next_scene), self.clear_stage(how)                                            scene changes",
    "    enter(m, how) / leave(m, how) / emph(m, how) / stagger(items) / later(anim, delay)          motion",
    "      entrances: rise drop slide pop grow grow_left draw write type unfold zoom spin stamp spring",
    "    headline, kicker, text (right font for Hindi/Chinese/Latin), label, quote, caption, number + count",
    "    marks: highlight circle underline strike box arrow callout bracket stamp tick cross dimension spotlight",
    "    card chip tag sticky document clipping book shelf scroll portrait stat checklist; person crowd icon photo",
    "    Map(\"east asia\" or bounds, year=) .shade .pin .route .empire .view .point; Timeline .event .span .lifespan",
    "    bars donut units line_chart versus; Flow Tree Cycle Hub Chain Network Pyramid (.reveal .focus .pulse)",
    "  KIT.md in your workspace is the full catalog (read it with read_file); kit_preview shows a snippet before you",
    "  use it. reference/kit_example.py is 70 seconds of a chapter built with it: read it to see how such a chapter",
    "  moves (camera pans and pushes, wipes, things landing on their words, counters, marks drawn on, a diagram built",
    "  as the voice names its parts), not to copy it.",
    "- Tools to write and edit files, render, look at frames, preview kit pieces, make pictures, run commands, and check",
    "  the phone.",
    "",
    ...PHONE_RULES,
    "",
    "- reference/vox_example.py (plain Manim) and reference/kit_example.py (with the kit) are chapters built in this setup.",
    "",
    "HOW TO WORK (as a careful engineer works)",
    "1. Read the narration. Write plan.md: the chapter's moments, each with its lines and times, what is on screen and",
    "   which words drive what. One clear idea on screen at a time; something meaningful changes every few seconds.",
    "2. Build scene.py in pieces you can check: render a draft early, look at a sheet of frames, then frames at the",
    "   moments that matter (where things land on words, where text could overlap or leave the frame). Fix what you see.",
    "   Look before you believe: a frame shows overlaps, cut-off text, unreadable sizes and empty screens that code hides.",
    "3. The frame is x -7.1..7.1, y -4..4 (16:9). Keep everything inside with a margin; text at least font_size 24.",
    "   Fonts: use what is installed (listed in the first message); the narration may be in Hindi or Hinglish:",
    "   Devanagari needs a font that has it (Noto Sans Devanagari, Hind). Subtitles are your choice.",
    "   Work on one moment at a time with render(from=..., to=...): a section renders in seconds. Every render shows you a",
    "   sheet of its frames; give it look: [times] for a closer view in the same turn. Pictures are shown to you once, in",
    "   the turn after they are made.",
    "   A long build is condensed into a summary now and then; your files stay as they are, so read them when you need.",
    "4. A render also says what it measured (the animations used, long still or empty stretches, words off the frame",
    "   or on top of words): information for you, not rules.",
    "5. When it is right, render final (a whole render runs the phone check too), then look at it as a viewer would:",
    "   list in finish what is still wrong (open_issues). If anything is, fix it first: a passing phone check is not the",
    "   bar, the video is. If the phone differs, find why and change the scene.",
    `You have at most ${turns} turns: plan, then build steadily; do not stop at a first draft that you have not looked at.`,
    "Every reply is a turn, and a turn may hold several tool calls: they run in order, so edits and then a render go in",
    "one turn. Every reply calls at least one tool. Say briefly what you are doing and why as you go.",
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

type Msg = { role: "system" | "user" | "assistant" | "tool"; content: unknown; tool_calls?: unknown[]; tool_call_id?: string; _openai?: unknown[] };
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

type Live = { text: string; reasoning: string; tools: string[] };
/** `output`: an OpenAI answer's own items (its encrypted reasoning with them), sent back with the next turn. */
type Answer = { text?: string; reasoning?: string; calls: ToolCall[]; output?: unknown[] };

/**
 * OpenRouter sends a model's requests to whichever provider is free, and each provider has its own prompt cache: a
 * turn sent elsewhere pays for the whole conversation again. These pin a build to one (V2_VIDEO_AGENT_PROVIDER: a
 * comma list of OpenRouter provider names; by default the model's own maker, for OpenAI's and Anthropic's models).
 */
function providerPin(model: string): Record<string, unknown> {
  const set = (process.env.V2_VIDEO_AGENT_PROVIDER ?? "").split(",").map((x) => x.trim()).filter(Boolean);
  const own = model.startsWith("openai/") ? ["openai"] : model.startsWith("anthropic/") ? ["anthropic"] : [];
  const order = set.length ? set : own;
  return order.length ? { provider: { order, allow_fallbacks: true } } : {};
}

/** A request refused for something the next attempt changes (a setting the model does not take): always tried again. */
class Retry extends Error {}

/**
 * Models that refuse a forced tool call (tool_choice "required", which Anthropic's models take as "any", is refused
 * while they think): asked with "auto" from then on. A turn may then answer without a tool, which the loop asks again.
 */
const NO_FORCED = new Set<string>();
const forcedRefused = (model: string, effort?: string) =>
  NO_FORCED.has(model) || (model.startsWith("anthropic/") && !!effort && effort !== "off");

/** Models that refused cache marks: sent without them from then on. */
const NO_MARKS = new Set<string>();

/**
 * Anthropic's models cache only up to marks put in the request: one on the instructions and one on the latest message,
 * so each turn reads the conversation so far from the cache and writes the rest. Other models cache by themselves.
 */
function cacheMarks(model: string, messages: Record<string, unknown>[]): Record<string, unknown>[] {
  if (!model.startsWith("anthropic/") || NO_MARKS.has(model)) return messages;
  const mark = (m: Record<string, unknown>) => {
    const parts = typeof m.content === "string" ? (m.content ? [{ type: "text", text: m.content }] : [])
      : Array.isArray(m.content) ? [...(m.content as Record<string, unknown>[])] : [];
    const at = parts.map((p) => p.type).lastIndexOf("text");
    if (at < 0) return m;
    parts[at] = { ...parts[at], cache_control: { type: "ephemeral" } };
    return { ...m, content: parts };
  };
  const last = messages.length - 1;
  return messages.map((m, i) => (i === 0 && m.role === "system") || (i === last && m.role !== "assistant") ? mark(m) : m);
}

/**
 * One turn of the model: the conversation, the tools; what it said, its reasoning, and the tools it called. Streamed,
 * so the page sees the turn as it is written (`onLive`, called as the words, the reasoning and the tool calls come).
 */
async function turn(call: Call, messages: Msg[], fake: () => Fake, onLive: (live: Live) => void, cacheKey: string, tools: typeof TOOLS): Promise<Answer | null> {
  // OpenAI's models on OpenAI's own API when there is a key for it (openai-responses.ts); everything else on OpenRouter.
  call.provider = useOpenAI(call.model) ? "openai" : usingFixture(call.model) ? "fixture" : "openrouter";
  const plain = messages.map(({ _openai, ...m }) => (void _openai, m as Record<string, unknown>));
  const body: Record<string, unknown> = { model: call.model, messages: cacheMarks(call.model, plain), tools,
    tool_choice: forcedRefused(call.model, call.effort) ? "auto" : "required", stream: true, usage: { include: true }, max_tokens: MAX_TOKENS,
    ...providerPin(call.model),
    // Off is asked for: with no reasoning setting, a reasoning model thinks at its own default level.
    // ("default": a model whose reasoning cannot be turned off, at its own level).
    ...(call.effort === "default" ? {} : { reasoning: call.effort && call.effort !== "off" ? { effort: call.effort } : { enabled: false } }) };
  // What is kept of the request on the call: its size; the conversation itself is the workspace's agent-log.jsonl.
  call.request = { model: call.model, messages: messages.length, tools: tools.map((t) => t.function.name), chars: JSON.stringify(messages).length };
  for (let attempt = 1; attempt <= 3; attempt++) {
    const began = Date.now();
    try {
      let out: Answer;
      if (call.provider === "openai") {
        const r = await respond({ model: call.model, messages, tools: tools as never, effort: call.effort, maxTokens: MAX_TOKENS, timeoutMs: TIMEOUT_MS, onLive, cacheKey });
        call.usage = r.usage;
        if (r.effort) call.effort = r.effort;
        out = { text: r.text, reasoning: r.reasoning, calls: r.calls, output: r.output };
      } else if (call.provider === "fixture") {
        const f = fake();
        // As a real turn streams: its words a few at a time.
        const words = (f.text ?? "").split(/(?<=\s)/);
        for (let i = 1; i <= words.length; i++) {
          onLive({ text: words.slice(0, i).join(""), reasoning: "", tools: [] });
          await new Promise((r) => setTimeout(r, 60));
        }
        out = { text: f.text, calls: f.calls.map((c, i) => ({ id: `fake_${Date.now()}_${i}`, function: { name: c.name, arguments: JSON.stringify(c.args) } })) };
        onLive({ text: f.text ?? "", reasoning: "", tools: f.calls.map((c) => c.name) });
        // Estimated as a provider counts: a picture as a picture (~800 tokens), not as its data URL's characters.
        const sent = JSON.stringify(messages);
        call.usage = { input: Math.round(sent.replace(/data:image\/[^"]+/g, "").length / 4 + 800 * (sent.match(/data:image\//g)?.length ?? 0)), output: Math.round(JSON.stringify(f).length / 4) };
      } else {
        const response = await fetch(URL_, { method: "POST", signal: timeoutOrAbort(TIMEOUT_MS),
          headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json", "X-Title": "pocketanim harness v2" },
          body: JSON.stringify(body) });
        if (!response.ok || !response.body) {
          const said = await response.text();
          // A reasoning level this model does not take: the rest of the build at high.
          // A forced tool call refused (a model that thinks): the same turn with the tool left to it.
          if (response.status === 400 && /tool_choice/i.test(said) && body.tool_choice !== "auto") {
            NO_FORCED.add(call.model);
            body.tool_choice = "auto";
            throw new Retry(`a forced tool call is not taken by this model, asking again with tool_choice auto: ${said.slice(0, 200)}`);
          }
          // Cache marks refused (a provider without them): the same turn without, and the build from then on.
          if (response.status === 400 && /cache_control/i.test(said) && !NO_MARKS.has(call.model)) {
            NO_MARKS.add(call.model);
            body.messages = plain;
            throw new Retry(`cache marks not taken, asking again without: ${said.slice(0, 200)}`);
          }
          // A model whose reasoning cannot be turned off: asked again with no setting (its own default level).
          if (response.status === 400 && /reason/i.test(said) && (body.reasoning as { enabled?: boolean } | undefined)?.enabled === false) {
            delete body.reasoning;
            call.effort = "default";
            throw new Retry(`reasoning cannot be turned off for this model, asking again at its default: ${said.slice(0, 200)}`);
          }
          if (response.status === 400 && /effort/i.test(said) && call.effort && call.effort !== "high" && call.effort !== "off") {
            call.effort = "high";
            body.reasoning = { effort: "high" };
            throw new Retry(`reasoning level not taken by this model, asking again at high: ${said.slice(0, 200)}`);
          }
          throw new Error(`${response.status} ${said.slice(0, 300)}`);
        }
        let text = "";
        let reasoning = "";
        const tools: { id: string; name: string; args: string }[] = [];
        let usage: { prompt_tokens?: number; completion_tokens?: number; cost?: number; completion_tokens_details?: { reasoning_tokens?: number };
          prompt_tokens_details?: { cached_tokens?: number } } | undefined;
        const decoder = new TextDecoder();
        let buffer = "";
        let shown = 0;
        const reader = response.body.getReader();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let cut: number;
          while ((cut = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, cut).trim();
            buffer = buffer.slice(cut + 1);
            if (!line.startsWith("data:")) continue;
            const data = line.slice(5).trim();
            if (data === "[DONE]") continue;
            let chunk: { error?: { message?: string }; usage?: typeof usage; choices?: { delta?: { content?: string | null; reasoning?: string | null;
              tool_calls?: { index?: number; id?: string; function?: { name?: string; arguments?: string } }[] } }[] };
            try {
              chunk = JSON.parse(data);
            } catch {
              continue;
            }
            if (chunk.error) throw new Error(chunk.error.message ?? "provider error");
            if (chunk.usage) usage = chunk.usage;
            const delta = chunk.choices?.[0]?.delta;
            if (!delta) continue;
            if (delta.content) text += delta.content;
            if (delta.reasoning) reasoning += delta.reasoning;
            for (const t of delta.tool_calls ?? []) {
              const k = t.index ?? tools.length;
              tools[k] ??= { id: t.id ?? `call_${k}`, name: "", args: "" };
              if (t.id) tools[k].id = t.id;
              if (t.function?.name) tools[k].name += t.function.name;
              if (t.function?.arguments) tools[k].args += t.function.arguments;
            }
            // The page is told every few hundred characters, not every token.
            const size = text.length + reasoning.length + tools.reduce((n, t) => n + t.args.length, 0);
            if (size - shown > 300) {
              shown = size;
              onLive({ text, reasoning, tools: tools.filter(Boolean).map((t) => t.name) });
            }
          }
        }
        onLive({ text, reasoning, tools: tools.filter(Boolean).map((t) => t.name) });
        call.usage = { input: usage?.prompt_tokens ?? 0, output: usage?.completion_tokens ?? 0,
          ...(usage?.completion_tokens_details?.reasoning_tokens ? { reasoning: usage.completion_tokens_details.reasoning_tokens } : {}),
          ...(usage?.prompt_tokens_details?.cached_tokens ? { cached: usage.prompt_tokens_details.cached_tokens } : {}) };
        call.cost += Number(usage?.cost ?? 0);
        out = { text: text || undefined, reasoning: reasoning || undefined,
          calls: tools.filter((t) => t?.name).map((t) => ({ id: t.id, function: { name: t.name, arguments: t.args } })) };
      }
      call.attempts.push({ started: began, ended: Date.now() });
      call.text = out.text;
      call.output = { said: out.text, reasoning: out.reasoning?.slice(0, 20000), tools: out.calls.map((c) => ({ name: c.function.name, args: brief(safeJson(c.function.arguments)) })) };
      call.status = "done";
      call.ended = Date.now();
      return out;
    } catch (error) {
      call.attempts.push({ started: began, ended: Date.now(), error: stopped() ? "stopped" : (error as Error).message.slice(0, 400) });
      if (stopped() || (!(error instanceof Retry) && /\b(400|401|403|404)\b/.test((error as Error).message))) break;
    }
  }
  call.status = "failed";
  call.ended = Date.now();
  call.error = call.attempts.at(-1)?.error;
  return null;
}

/** What a render measured about itself (engine/agent/audit.py). */
type Audit = { plays: number; seconds: number; kinds: Record<string, number>; fade_share: number; dead: number[][]; empty: number[][];
  off_frame: [number, string][]; overlaps: [number, string, string][] };

/** Most of the animations may be fades, no more: past this the chapter plays as a slideshow. */
const FADE_SHARE = Math.min(1, Math.max(0, Number(process.env.V2_VIDEO_AGENT_FADE_SHARE) || 0.6));

/** The audit's faults, in words: what stops the chapter from finishing. */
function auditFaults(a: Audit | undefined): string[] {
  if (!a) return [];
  const span = (r: number[]) => `${r[0]}-${r[1]} s`;
  return [
    ...(a.dead.length ? [`nothing moves for more than 8 s at ${a.dead.map(span).join(", ")}: something should change on screen as the voice goes on`] : []),
    ...(a.empty.length ? [`the screen is empty at ${a.empty.map(span).join(", ")}`] : []),
    ...(a.off_frame.length ? [`words outside the frame: ${a.off_frame.slice(0, 8).map(([t, s]) => `"${s}" at ${t} s`).join("; ")}`] : []),
    ...(a.overlaps.length ? [`words on top of words: ${a.overlaps.slice(0, 8).map(([t, x, y]) => `"${x}" and "${y}" at ${t} s`).join("; ")}`] : []),
    ...(a.fade_share > FADE_SHARE ? [`${Math.round(a.fade_share * 100)}% of the animations are FadeIn/FadeOut`] : []),
  ];
}

function auditText(a: Audit | undefined): string {
  if (!a) return "";
  const kinds = Object.entries(a.kinds).slice(0, 12).map(([k, v]) => `${k} ${v}`).join(", ");
  const faults = auditFaults(a);
  return `\nmeasured: ${a.plays} animated plays; animations: ${kinds || "none"}` +
    (faults.length ? `\nnoticed (yours to judge):\n- ${faults.join("\n- ")}` : "");
}

/** Arguments as kept on a step: a long text (a whole file) cut, its length said. */
function brief(args: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(args).map(([k, v]) => [k, typeof v === "string" && v.length > 4000 ? `${v.slice(0, 4000)}\n… (${v.length} characters)` : v]));
}

/** A tool call's arguments in a line: long text left out. */
function shortArgs(args: Record<string, unknown>): string {
  return Object.entries(args).map(([k, v]) => {
    const text = typeof v === "string" ? v : JSON.stringify(v);
    return `${k}=${text.length > 80 ? `(${text.length} characters)` : text}`;
  }).join(" ");
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

/** A long output as its start and its end, the middle cut (a file read whole shows its top; an error its end). */
function headTail(out: string, keep = 4000): string {
  if (out.length <= keep * 2 + 200) return out;
  return `${out.slice(0, keep)}\n… (${out.length - keep * 2} characters cut here) …\n${out.slice(-keep)}`;
}

function sh(command: string, cwd: string, timeout: number): Promise<{ code: number | null; out: string }> {
  return new Promise((resolve) => {
    const bin = path.dirname(pythonPath());
    const child = spawn("bash", ["-c", command], { cwd, env: { ...withoutSecrets(), PATH: `${bin}:${process.env.PATH ?? ""}`,
      PANIM_NARRATION_DIR: cwd, PYTHONPATH: [cwd, path.join(engineDir(), "agent")].join(":") }, detached: detachedForAbort() });
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    const timer = setTimeout(() => { child.kill("SIGKILL"); out += `\nstopped: over ${timeout / 1000} s`; }, timeout);
    const unwatch = killOnAbort(child, () => (out += "\nstopped"));
    child.on("close", (code) => { clearTimeout(timer); unwatch(); resolve({ code, out }); });
    child.on("error", (e) => { clearTimeout(timer); unwatch(); resolve({ code: -1, out: String(e) }); });
  });
}

async function tool(kind: string, args: string[], ws: string, o: { env?: Record<string, string>; onChild?: (child: ChildProcess) => void } = {}):
  Promise<Record<string, unknown>> {
  const out = await runPython([path.join(engineDir(), "tools", "agent_tools.py"), kind, ...args], ws, o.env ?? {}, undefined, 1_800_000, o.onChild);
  try {
    return JSON.parse(out.stdout.trim().split("\n").pop() ?? "");
  } catch {
    return { ok: false, error: out.out.slice(-1500) || "the tool said nothing" };
  }
}

const hashOf = async (file: string) => createHash("sha1").update(await readFile(file).catch(() => Buffer.alloc(0))).digest("hex");

/** What is installed (fonts, Python, map data), looked up once a server: told in the first message, not found by turns. */
let factsOnce: Promise<string> | undefined;
function environmentFacts(ws: string): Promise<string> {
  factsOnce ??= tool("facts", [], ws).then((f) => {
    if (!f.ok) return "";
    const ne = f.natural_earth as { dir: string; files: string[] } | undefined;
    return [
      "What is installed (no need to look it up):",
      `- Python with Manim Community ${f.manim ?? ""}, numpy, shapely, cartopy, PIL; the kit is importable (from kit import *).`,
      ne?.files.length ? `- Natural Earth map data, offline, in ${ne.dir}: ${ne.files.join(", ")} (the kit's Map reads it for you).` : "",
      `- Fonts (fc-list families): ${(f.fonts as string[]).join(", ")}.`,
    ].filter(Boolean).join("\n");
  }).catch(() => "");
  return factsOnce;
}

/** The workspace as a render sees it: its Python files and its assets (not notes, renders or references). */
async function workspaceKey(ws: string): Promise<string> {
  const h = createHash("sha1");
  const entries = await readdir(ws, { withFileTypes: true, recursive: true }).catch(() => []);
  const rows: string[] = [];
  for (const e of entries) {
    if (!e.isFile()) continue;
    const rel = path.relative(ws, path.join(e.parentPath ?? ws, e.name));
    if (/^(renders|export|media|history|reference|library|\.kit_preview)\b/.test(rel) || rel.includes("__pycache__")) continue;
    if (rel.endsWith(".py")) rows.push(`${rel}:${await hashOf(path.join(ws, rel))}`);
    else if (rel.startsWith("assets")) {
      const st = await stat(path.join(ws, rel)).catch(() => undefined);
      rows.push(`${rel}:${st?.size}:${st?.mtimeMs}`);
    }
  }
  for (const r of rows.sort()) h.update(r + "\n");
  return h.digest("hex");
}

/** Frames as one picture: 1 across, 2 across up to 4, else 4 across; each stamped with its time in its corner. */
async function frameSheet(frames: { t: number; file: string }[], out: string): Promise<void> {
  const cols = frames.length <= 1 ? 1 : frames.length <= 4 ? 2 : 4;
  const w = cols === 1 ? FRAME_WIDTH : cols === 2 ? 640 : 480;
  const h = Math.round(w * 9 / 16);
  const rows = Math.ceil(frames.length / cols);
  const tiles = await Promise.all(frames.map(async (f, i) => {
    const stamp = Buffer.from(`<svg width="${w}" height="${h}"><rect width="78" height="26" fill="black"/>` +
      `<text x="7" y="19" font-family="DejaVu Sans Mono" font-size="16" fill="white">${f.t.toFixed(1)}s</text></svg>`);
    const tile = await sharp(f.file).resize(w, h, { fit: "contain", background: "#000" }).composite([{ input: stamp, left: 0, top: 0 }]).png().toBuffer();
    return { input: tile, left: (i % cols) * w, top: Math.floor(i / cols) * h };
  }));
  await mkdir(path.dirname(out), { recursive: true });
  await sharp({ create: { width: cols * w, height: rows * h, channels: 3, background: "#141414" } }).composite(tiles).png().toFile(out);
}

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

/** The stand-in agent in the lean mode: the scene written (rendered and checked), an edit, a look, finished. */
function leanScriptedAgent(t: Timing): () => Fake {
  const scene = [
    "from kit import *",
    "",
    "class Chapter(KitScene):",
    "    look = \"vox\"",
    "    def construct(self):",
    "        for n, line in enumerate(self.lines):",
    "            self.until(line[\"start\"], lead=0.2)",
    "            h = headline(\" \".join(w[\"w\"] for w in line[\"words\"][:3]), size=44)",
    "            self.play(h.appear())",
    "            self.until(line[\"end\"], lead=0.3)",
    "            self.play(h.disappear())",
    "        self.wait_until_end()",
    "",
  ].join("\n");
  const steps: Fake[] = [
    { text: "Writing the whole scene.", calls: [{ name: "write_scene", args: { content: scene } }] },
    { text: "Larger headlines.", calls: [{ name: "edit_scene", args: { edits: [{ old: "size=44", new: "size=48" }] } }] },
    { text: "Looking closer.", calls: [{ name: "look", args: { times: [Math.min(3, t.seconds / 3), t.seconds / 2, t.seconds * 0.8], detail: "low" } }] },
    { text: "Done.", calls: [{ name: "finish", args: { summary: "Each line's first words as a headline (the stand-in agent: no model key).", open_issues: [] } }] },
  ];
  let k = 0;
  return () => steps[Math.min(k++, steps.length - 1)];
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
    "            self.play(Write(head), GrowFromEdge(bar, LEFT), run_time=0.5)",
    "            self.wait_until(line[\"end\"], lead=0.3)",
    "            self.play(Unwrite(head), ShrinkToCenter(bar), run_time=0.3)",
    "        self.wait_until_end()",
    "",
  ].join("\n");
  const plan = ["# Plan", "", ...t.lines.map((l) => `- [${l.n}] ${l.start.toFixed(1)}-${l.end.toFixed(1)}: the line's first words, underlined in red`)].join("\n");
  const steps: Fake[] = [
    { text: "Planning the chapter.", calls: [{ name: "write_file", args: { path: "plan.md", content: plan } }] },
    { text: "Which fonts are there?", calls: [{ name: "shell", args: { command: "fc-list : family | sort -u | head -20" } }] },
    { text: "Trying a kit headline.", calls: [{ name: "kit_preview", args: { code: "h = headline(\"Japan\"); self.play(h.appear())", look: "vox" } }] },
    { text: "Writing the scene.", calls: [{ name: "write_file", args: { path: "scene.py", content: scene } }] },
    { text: "Larger words.", calls: [{ name: "edit_file", args: { path: "scene.py", old: "font_size=44", new: "font_size=48" } }] },
    { text: "Rendering a draft, checked on the phone.", calls: [{ name: "render", args: { quality: "draft", check: true } }] },
    { text: "Rendering the opening again.", calls: [{ name: "render", args: { quality: "draft", from: Math.min(2, t.seconds / 4), to: Math.min(6, t.seconds / 2) } }] },
    { text: "Looking closer.", calls: [{ name: "look", args: { times: [Math.min(3, t.seconds / 3)], detail: "low" } }] },
    { text: "The whole chapter again, for the phone.", calls: [{ name: "render", args: { quality: "draft" } }] },
    { text: "Checking the phone.", calls: [{ name: "phone_check", args: { samples: 6 } }] },
    { text: "Done, though one label is tight.", calls: [{ name: "finish", args: { summary: "A first pass.", open_issues: ["the last line's words sit close to the frame's edge"] } }] },
    { text: "Checked again: it is fine.", calls: [{ name: "finish", args: { summary: "Each line's first words, underlined in red, on paper (the stand-in agent: no model key).", open_issues: [] } }] },
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
  await copyFile(path.join(engineDir(), "agent", "kit", "KIT.md"), path.join(ws, "KIT.md"));
  await mkdir(path.join(ws, "reference"), { recursive: true });
  await copyFile(path.join(engineDir(), "agent", "vox_example.py"), path.join(ws, "reference", "vox_example.py"));
  await copyFile(path.join(engineDir(), "agent", "kit_example.py"), path.join(ws, "reference", "kit_example.py"));
  const styleFile = path.join(ws, "style" + path.extname(settings.style));
  await copyFile(settings.style, styleFile);
  const agent: ChapterAgent = { status: "running", model: settings.model, effort: settings.effort, imageModel: settings.imageModel, note: o.note, started: Date.now(),
    turns: 0, cost: 0, steps: [], versions: [], log: LOG_FILE };
  agent.provider = useOpenAI(settings.model) ? "openai" : usingFixture(settings.model) ? "fixture" : "openrouter";
  agent.effortUsed = settings.effort;
  cv.agent = agent;
  saveRun(run, true);
  const step = (s: Omit<VideoStep, "at">) => { agent.steps.push({ ...s, at: Date.now() }); saveRun(run); };
  // The whole conversation, as sent and answered, a line a message: what the Conversation view reads. A build
  // starts a new log (the one before is kept beside it).
  const logFile = path.join(ws, LOG_FILE);
  if (existsSync(logFile)) await copyFile(logFile, path.join(ws, `agent-log-${(await stat(logFile)).mtimeMs.toFixed(0)}.jsonl`));
  await writeFile(logFile, "", "utf8");
  const log = (entry: Record<string, unknown>) => appendFile(logFile, JSON.stringify({ t: Date.now(), ...entry }) + "\n", "utf8").catch(() => {});
  let currentTurn = 0;
  // Every version of every file it writes, under history/: the Files view shows each and what changed.
  await mkdir(path.join(ws, "history"), { recursive: true });
  const keepVersion = async (file: string): Promise<number> => {
    const rel = path.relative(ws, file);
    const v = agent.versions!.length + 1;
    const kept = path.join("history", `v${String(v).padStart(3, "0")}-${rel.replace(/[\\/]/g, "__")}`);
    await copyFile(file, path.join(ws, kept));
    const lines = (await readFile(file, "utf8").catch(() => "")).split("\n").length;
    agent.versions!.push({ v, path: rel, turn: currentTurn, file: kept, lines, at: Date.now() });
    return v;
  };

  const custom = path.resolve(settings.style) !== path.resolve(path.join(engineDir(), "agent", "style-vox.jpg"));
  const lean = settings.mode === "lean";
  const system = lean
    ? leanRoleText({ note: settings.styleNote, custom }, settings.turns, await readFile(path.join(engineDir(), "agent", "kit", "KIT.md"), "utf8"))
    : roleText({ note: settings.styleNote, custom }, settings.turns);
  const existing = existsSync(path.join(ws, SCENE_FILE));
  const ask = [
    `Lecture ${n}, chapter ${c}: "${run.script?.lectures[n]?.chapters.find((x) => x.n === c)?.title ?? ""}". Build its video.`,
    `Lesson: ${run.lectures.find((l) => l.n === n)?.title ?? ""}; book: ${run.documentName}.`,
    existing && lean ? `There is already a ${SCENE_FILE} from an earlier build: improve it (edit_scene) rather than starting over unless it is wrong. It is:\n\`\`\`python\n${await readFile(path.join(ws, SCENE_FILE), "utf8")}\n\`\`\`` : "",
    existing && !lean ? `Your workspace already has a ${SCENE_FILE} from an earlier build: read it, and improve it rather than starting over unless it is wrong.` : "",
    o.note ? `A note from the person you build for: ${o.note}` : "",
    await environmentFacts(ws),
    "",
    narrationText(timing),
  ].filter((x) => x !== "").join("\n");
  const styleData = await imageData(styleFile);
  const messages: Msg[] = [
    { role: "system", content: system },
    { role: "user", content: [{ type: "text", text: ask }, ...(styleData ? [{ type: "image_url", image_url: { url: styleData } }] : [])] },
  ];
  await log({ kind: "build", model: settings.model, effort: settings.effort, imageModel: settings.imageModel, note: o.note ?? null, turns: settings.turns });
  await log({ kind: "system", text: system });
  await log({ kind: "user", text: ask, images: styleData ? [path.basename(styleFile)] : [] });
  const fake = lean ? leanScriptedAgent(timing) : scriptedAgent(timing);
  // One prompt cache for the chapter's whole build.
  const cacheKey = createHash("sha1").update(`video-agent:${run.id}:${n}:${c}`).digest("hex").slice(0, 32);
  let lastRender: { video?: string; hash?: string; seconds?: number; audit?: Audit; offset?: number; section?: boolean; quality?: string } = {};
  let lastCheck: { ok: boolean; hash?: string; key?: string; result?: Record<string, unknown> } = { ok: false };
  let images = 0;
  let firstPrompt = true;

  /** Pictures for the model: a user message after the tool results; older pictures are dropped from the conversation. */
  /**
   * Pictures to show the model: sent once, with the next request, then left out. The conversation itself is only
   * ever added to (never edited), so the provider's prompt cache keeps it: the turn's pictures ride on one message at
   * its end, which the next request carries as a note instead.
   */
  let shownNow: { label: string; urls: string[]; detail: string }[] = [];
  const transient: { at?: { index: number; parts: unknown[] } } = {};
  const show = async (label: string, files: string[], detail = "high") => {
    const data = (await Promise.all(files.map((f) => imageData(f)))).filter((d): d is string => !!d);
    if (!data.length) return;
    void log({ kind: "images", turn: currentTurn, label, files: files.map((f) => path.relative(ws, f)) });
    shownNow.push({ label, urls: data, detail });
  };
  /** The request: the conversation, with this turn's pictures on the message that carries them. */
  const request = (): Msg[] => {
    const t = transient.at;
    return t ? messages.map((m, i) => (i === t.index ? { ...m, content: t.parts } : m)) : messages;
  };
  /** The turn's pictures: one user message after the tool results, its pictures sent with the next request only. */
  const attachShown = () => {
    transient.at = undefined;
    if (!shownNow.length) return;
    const text = shownNow.map((s) => s.label).join("\n");
    messages.push({ role: "user", content: `${text}\n(shown to you once; look again if you need it)` });
    transient.at = { index: messages.length - 1, parts: [{ type: "text", text },
      ...shownNow.flatMap((s) => s.urls.map((url) => ({ type: "image_url", image_url: { url, detail: s.detail } })))] };
    shownNow = [];
  };
  /**
   * The conversation condensed, once a request has grown past COMPACT_TOKENS: the instructions, the chapter, and a
   * summary built here (no model call) of what was done, what the files are and where the build stands.
   */
  const compact = async (k: number) => {
    const files = (await run1("list_files", {}).catch(() => ({ text: "" }))).text.split("\n").filter(Boolean);
    const said = messages.filter((m) => m.role === "assistant" && typeof m.content === "string" && m.content.trim())
      .slice(-4).map((m) => String(m.content).trim().slice(0, 1500));
    const done = agent.steps.filter((s) => s.kind === "tool" || s.kind === "finish")
      .map((s) => `turn ${s.turn}: ${s.tool}${s.args ? ` ${shortArgs(s.args)}` : ""} -> ${s.ok ? "ok" : "failed"}${s.result ? `: ${s.result.split("\n")[0].slice(0, 160)}` : ""}`);
    let summary = [
      `The conversation so far was condensed at turn ${k} to save room. Your files are as you left them: read any you need.`,
      "",
      "What you did:",
      ...done.slice(-60),
      "",
      said.length ? `What you last said:\n${said.join("\n---\n")}` : "",
      files.length ? `Your files:\n${files.slice(0, 80).join("\n")}` : "",
      lastRender.video ? `Last render: ${path.relative(ws, lastRender.video)}, ${lastRender.seconds ?? "?"} s${lastRender.section ? ` (a section from ${lastRender.offset} s)` : ""}` : "No render yet.",
      lastCheck.result ? `Last phone check: ${lastCheck.ok ? "passed" : "did not pass"}` : "No phone check yet.",
      "Carry on from here.",
    ].filter((x) => x !== "").join("\n");
    const now = await hashOf(path.join(ws, SCENE_FILE)).catch(() => undefined);
    if (lastCheck.result && lastCheck.hash !== now) summary = summary.replace(/Last phone check: \w+/, (m) => `${m} (on an earlier version of ${SCENE_FILE})`);
    const t = transient.at;
    messages.splice(2, messages.length - 2, { role: "user", content: summary });
    transient.at = t ? { index: 2, parts: [{ type: "text", text: summary }, ...t.parts.slice(1)] } : undefined;
    await log({ kind: "compact", turn: k, text: summary });
  };

  /**
   * Work done ahead, while the model thinks: once a turn has changed what a render sees, the whole chapter is rendered
   * (draft) and checked on the phone in the background, so the render and the phone check asked for next are often
   * ready. Only while the agent works on the whole chapter (its last render a whole draft, or none yet); keyed by the
   * workspace's state; anything else run first stops it.
   */
  type Ahead = { key: string; hash: string; name: string; render?: Promise<Record<string, unknown>>; check?: Promise<Record<string, unknown> | undefined>;
    children: Set<ChildProcess>; stopped: boolean; adopted: boolean };
  let ahead: Ahead | undefined;
  let renderedKey = "";
  let askedWhole = true;
  const stopAhead = async () => {
    const a = ahead;
    ahead = undefined;
    if (!a) return;
    a.stopped = true;
    for (const ch of a.children) killTree(ch);
    await Promise.allSettled([a.render, a.check]);
  };
  const startAhead = async () => {
    if (!AHEAD || lean || !askedWhole || !existsSync(path.join(ws, SCENE_FILE))) return;
    const key = await workspaceKey(ws);
    if (key === renderedKey || ahead?.key === key) return;
    await stopAhead();
    // Never over the render in use: the look tool reads it.
    const name = lastRender.video && path.basename(lastRender.video) === "ahead-a.mp4" ? "ahead-b" : "ahead-a";
    const a: Ahead = { key, hash: await hashOf(path.join(ws, SCENE_FILE)), name, children: new Set(), stopped: false, adopted: false };
    const onChild = (ch: ChildProcess) => a.children.add(ch);
    a.render = tool("render", [ws, SCENE_FILE, SCENE_CLASS, "draft"], ws, { env: { PANIM_RENDER_NAME: name }, onChild });
    a.check = a.render.then((r) => (r.ok && !a.stopped && !r.section
      ? tool("phone", [ws, SCENE_FILE, SCENE_CLASS, path.join(ws, "export"), String(r.video), "12"], ws, { onChild }) : undefined));
    ahead = a;
    await log({ kind: "ahead", turn: currentTurn, name });
  };

  /** The scene played as the phone plays it, compared with the last whole render. */
  const phoneCheck = async (samples: number): Promise<{ ok: boolean; text: string }> => {
        const hash = await hashOf(path.join(ws, SCENE_FILE));
        if (!lastRender.video || lastRender.hash !== hash) return { ok: false, text: "render the scene as it is now first: the check compares the phone with the last render" };
        if (lastRender.section) return { ok: false, text: "render the whole chapter first (no from/to): the check compares the whole program with the whole render" };
        const key = await workspaceKey(ws);
        // The check made ahead, on the render made ahead that is in use, when nothing has changed since.
        let r = ahead?.adopted && ahead.key === key && samples === 12 ? await ahead.check : undefined;
        if (r) ahead = undefined;
        else {
          await stopAhead();
          r = await tool("phone", [ws, SCENE_FILE, SCENE_CLASS, path.join(ws, "export"), lastRender.video, String(samples)], ws);
        }
        if (r.ok === false && r.error) return { ok: false, text: `the export failed:\n${r.error}` };
        const check = r.check as { ok: boolean | null; frames: number; differ: { t: number; mean: number; differ: number }[] };
        const ok = !!r.ok;
        lastCheck = { ok, hash, key, result: r };
        const worst = r.worst as { t: number; phone: string; manim: string } | undefined;
        if (!ok && worst?.phone && worst.manim) {
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
  };

  const run1 = async (name: string, args: Record<string, unknown>): Promise<{ text: string; ok: boolean; images?: string[]; video?: string; seconds?: number;
    done?: boolean; exit?: number | null; version?: number }> => {
    switch (name) {
      case "write_file": {
        const file = inside(ws, args.path);
        await mkdir(path.dirname(file), { recursive: true });
        await writeFile(file, String(args.content ?? ""), "utf8");
        const version = await keepVersion(file);
        return { ok: true, version, text: `wrote ${path.relative(ws, file)} (${String(args.content ?? "").split("\n").length} lines)` };
      }
      case "edit_file": {
        const file = inside(ws, args.path);
        const text = await readFile(file, "utf8");
        const old = String(args.old ?? "");
        const count = old ? text.split(old).length - 1 : 0;
        if (!count) return { ok: false, text: `${args.path}: the old text is not in the file (read it again)` };
        if (count > 1 && !args.all) return { ok: false, text: `${args.path}: the old text occurs ${count} times; give more of it, or set all` };
        await writeFile(file, args.all ? text.split(old).join(String(args.new ?? "")) : text.replace(old, () => String(args.new ?? "")), "utf8");
        const version = await keepVersion(file);
        return { ok: true, version, text: `edited ${args.path} (${args.all ? count : 1} place${count > 1 && args.all ? "s" : ""})` };
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
          if (!e.isFile() || /^(renders|export|media|history|library|__pycache__|\.kit_preview)\b/.test(rel) || rel.includes("__pycache__") || /^agent-log/.test(rel)) continue;
          rows.push(`${rel}  ${(await stat(full)).size} B`);
        }
        return { ok: true, text: rows.sort().join("\n") || "(empty)" };
      }
      case "shell": {
        if (!SHELL) return { ok: false, text: "the shell is off here" };
        const r = await sh(String(args.command ?? ""), ws, Math.min(600, Math.max(5, Number(args.timeout) || 120)) * 1000);
        return { ok: r.code === 0, exit: r.code, text: `exit ${r.code}\n${headTail(r.out)}` };
      }
      case "render": {
        if (!existsSync(path.join(ws, SCENE_FILE))) return { ok: false, text: `write ${SCENE_FILE} first` };
        const quality = args.quality === "final" ? "final" : "draft";
        const from = Math.max(0, Number(args.from) || 0);
        const to = Math.max(0, Number(args.to) || 0);
        const section = from > 0 || (to > 0 && to < timing.seconds);
        askedWhole = !section && quality === "draft";
        const key = await workspaceKey(ws);
        // The render made ahead when it is this one (a whole draft of the workspace as it is).
        let r = askedWhole && ahead?.key === key && ahead.render ? await ahead.render : undefined;
        if (r && ahead) ahead.adopted = true;
        else {
          await stopAhead();
          r = await tool("render", [ws, SCENE_FILE, SCENE_CLASS, quality, ...(section ? [String(from), String(to)] : [])], ws);
        }
        renderedKey = key;
        if (!r.ok) return { ok: false, text: `the render failed:\n${r.error}` };
        const audit = (r.audit ?? undefined) as Audit | undefined;
        const offset = Number(r.offset) || 0;
        lastRender = { video: String(r.video), hash: await hashOf(path.join(ws, SCENE_FILE)), seconds: Number(r.seconds), audit, offset, section, quality };
        const times = (r.sheet_times as number[] | undefined) ?? [];
        if (r.sheet) await show(`The render's sheet: frames at ${times.join(", ")} s`, [String(r.sheet)]);
        const off = Number(r.seconds) - timing.seconds;
        let text = section
          ? `rendered ${offset.toFixed(1)}-${(offset + Number(r.seconds)).toFixed(1)} s of the chapter (${quality})`
          : `rendered (${quality}): ${Number(r.seconds).toFixed(2)} s; the narration is ${timing.seconds.toFixed(2)} s` +
            (Math.abs(off) > 0.5 ? ` (${off > 0 ? "longer" : "shorter"} by ${Math.abs(off).toFixed(1)} s: end with self.wait_until_end(), and do not run past the voice)` : "") +
            auditText(audit);
        text += r.warnings ? `\nwarnings:\n${r.warnings}` : "";
        const images = r.sheet ? [fileUrl(run.id, String(r.sheet))] : [];
        if (Array.isArray(args.look) && args.look.length) {
          const seen = await run1("look", { times: args.look });
          text += `\n${seen.text}`;
          images.push(...(seen.images ?? []));
        }
        if (args.check !== false && !section) {
          const checked = await phoneCheck(12);
          return { ok: checked.ok, video: fileUrl(run.id, String(r.video)), seconds: Number(r.seconds), images, text: `${text}\n\nphone_check:\n${checked.text}` };
        }
        return { ok: true, video: fileUrl(run.id, String(r.video)), seconds: Number(r.seconds), images, text };
      }
      case "look": {
        if (!lastRender.video) return { ok: false, text: "render first" };
        const stale = lastRender.hash !== await hashOf(path.join(ws, SCENE_FILE)) ? " (the scene changed since this render)" : "";
        const detail = args.detail === "low" ? "low" : "high";
        const offset = lastRender.offset ?? 0;
        const times = Array.isArray(args.times) ? (args.times as unknown[]).map(Number).filter((x) => Number.isFinite(x) && x >= offset).slice(0, 8) : [];
        if (times.length) {
          const r = await tool("frames", [lastRender.video, path.join(ws, "renders", "look"), String(offset), String(FRAME_WIDTH), ...times.map(String)], ws);
          const frames = (r.frames as { t: number; file: string }[]) ?? [];
          if (!frames.length) return { ok: false, text: `no frames at those times${stale}` };
          // One picture of them all, each stamped with its time: one image for the model instead of several.
          const out = path.join(ws, "renders", "look", `look-${Date.now()}.png`);
          await frameSheet(frames, out);
          await show(`Frames at ${frames.map((f) => f.t).join(", ")} s (one picture, each stamped with its time)${stale}:`, [out], detail);
          return { ok: true, text: `${frames.length} frame(s) shown as one picture${stale}`, images: [fileUrl(run.id, out)] };
        }
        const out = path.join(ws, "renders", `sheet-${Date.now()}.png`);
        const r = await tool("sheet", [lastRender.video, out, String(Number(args.sheet_every) > 0 ? Number(args.sheet_every) : Math.max(0.5, (lastRender.seconds ?? 16) / 16)), String(lastRender.offset ?? 0)], ws);
        if (!r.ok) return { ok: false, text: String(r.error) };
        await show(`A sheet of the render: frames at ${(r.times as number[]).join(", ")} s${stale}:`, [out], detail);
        return { ok: true, text: `sheet shown (${(r.times as number[]).length} frames${stale})`, images: [fileUrl(run.id, out)] };
      }
      case "write_scene":
      case "edit_scene": {
        const file = path.join(ws, SCENE_FILE);
        let wrote: string;
        if (name === "write_scene") {
          await writeFile(file, String(args.content ?? ""), "utf8");
          wrote = `wrote ${SCENE_FILE} (${String(args.content ?? "").split("\n").length} lines)`;
        } else {
          // Every edit applied in memory first: one that does not fit changes nothing.
          let text = await readFile(file, "utf8").catch(() => "");
          const edits = Array.isArray(args.edits) ? args.edits as { old?: string; new?: string; all?: boolean }[] : [];
          if (!edits.length) return { ok: false, text: "give the edits" };
          for (const [i, e] of edits.entries()) {
            const old = String(e.old ?? "");
            const count = old ? text.split(old).length - 1 : 0;
            if (!count) return { ok: false, text: `edit ${i + 1}: its old text is not in ${SCENE_FILE} (nothing was changed)` };
            if (count > 1 && !e.all) return { ok: false, text: `edit ${i + 1}: its old text occurs ${count} times; give more of it, or set all (nothing was changed)` };
            text = e.all ? text.split(old).join(String(e.new ?? "")) : text.replace(old, () => String(e.new ?? ""));
          }
          await writeFile(file, text, "utf8");
          wrote = `${edits.length} edit${edits.length > 1 ? "s" : ""} made to ${SCENE_FILE}`;
        }
        const version = await keepVersion(file);
        const r = await run1("render", { quality: "draft" });
        return { ...r, version, text: `${wrote}\n\n${r.text}` };
      }
      case "kit_preview": {
        const code = String(args.code ?? "");
        if (!code.trim()) return { ok: false, text: "give the code to preview" };
        const dir = path.join(ws, ".kit_preview");
        await mkdir(dir, { recursive: true });
        const file = path.join(dir, `snippet-${Date.now()}.py`);
        await writeFile(file, code, "utf8");
        const out = await runPython([path.join(engineDir(), "tools", "kit_preview.py"), ws, file, dir, String(args.look ?? "vox")], ws, {}, undefined, 300_000);
        let r: Record<string, unknown>;
        try {
          r = JSON.parse(out.stdout.trim().split("\n").pop() ?? "");
        } catch {
          r = { ok: false, error: out.out.slice(-1500) || "the preview said nothing" };
        }
        if (!r.ok) return { ok: false, text: `the preview failed:\n${String(r.error ?? "").slice(-2500)}` };
        const files = [String(r.still), ...(r.sheet ? [String(r.sheet)] : [])];
        await show(r.sheet ? `kit_preview: its last frame, then a sheet of frames over its ${r.seconds} s:` : "kit_preview: the frame:", files, "low");
        return { ok: true, text: `previewed (${r.seconds} s of animation)`, images: files.map((f) => fileUrl(run.id, f)) };
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
        const r = await phoneCheck(Math.min(40, Math.max(3, Number(args.samples) || 12)));
        return { ok: r.ok, text: r.text };
      }
      case "finish": {
        const hash = await hashOf(path.join(ws, SCENE_FILE));
        if (!lastCheck.ok || lastCheck.hash !== hash || lastCheck.key !== await workspaceKey(ws)) {
          return { ok: false, text: "not yet: render the scene as it is now (your files changed since the last check) and run phone_check; finish when it passes" };
        }
        await stopAhead();
        const issues = (Array.isArray(args.open_issues) ? args.open_issues : []).map(String).filter((x) => x.trim());
        const left = settings.turns - currentTurn;
        if (issues.length && left >= 3) {
          return { ok: false, text: `not finished: you listed what is still wrong:\n${issues.map((x) => `- ${x}`).join("\n")}\nYou have ${left} turns left: fix these, render, check the phone, and finish again.` };
        }
        if (issues.length) agent.summary = `${String(args.summary ?? "")}\n\nStill open: ${issues.join("; ")}`.slice(0, 3000);
        if (!issues.length) agent.summary = String(args.summary ?? "").slice(0, 3000);
        // The lean mode renders drafts only: the finished video is rendered once more at its full size.
        if (lean && lastRender.quality !== "final") {
          const final = await run1("render", { quality: "final", check: false });
          if (!final.ok) return { ok: false, text: `the final render failed:\n${final.text}` };
        }
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

  let mechanical = false;
  try {
    for (let k = 1; k <= settings.turns; k++) {
      if (o.stop?.()) {
        agent.status = "stopped";
        break;
      }
      agent.turns = k;
      currentTurn = k;
      const effort = k === 1 || !ADAPTIVE || settings.effort === "off" || !mechanical ? settings.effort : "low";
      const call = newCall(run, { step: "video-agent", label: `Video agent, turn ${k} (lecture ${n}, chapter ${c})`, lecture: n, model: settings.model, effort,
        prompt: firstPrompt
          ? { system: [part("role", "The video agent's instructions", "rules", system)], user: [part("chapter", "The chapter and its narration", "ask", ask)] }
          : { system: [], user: [part("turn", "The turn", "context", `turn ${k}: the conversation so far (${messages.length} messages)`)] } });
      firstPrompt = false;
      const asked = Date.now();
      agent.live = { turn: k, started: asked, text: "", reasoning: "", tools: [] };
      saveRun(run);
      const answer = await turn(call, request(), fake, (live) => {
        agent.live = { turn: k, started: asked, text: live.text.slice(-6000), reasoning: live.reasoning.slice(-6000), tools: live.tools };
        saveRun(run);
      }, cacheKey, lean ? LEAN_TOOLS : TOOLS);
      agent.live = undefined;
      agent.cost += call.cost;
      agent.provider = call.provider;
      // The level the build thinks at (a low turn chosen for mechanical work is shown on the turn itself).
      if (effort === settings.effort) agent.effortUsed = call.effort ?? "off";
      if (call.effort && call.effort !== effort && effort === settings.effort) {
        // The level asked for was not taken by this model: the rest of the build at the one that was.
        settings.effort = call.effort as typeof settings.effort;
      }
      if (o.stop?.()) {
        agent.status = "stopped";
        break;
      }
      if (!answer) {
        step({ turn: k, kind: "error", call: call.id, text: call.error ?? "the model did not answer", ms: Date.now() - asked });
        await log({ kind: "error", turn: k, text: call.error ?? "the model did not answer" });
        agent.status = "failed";
        agent.error = call.error ?? "the model did not answer";
        break;
      }
      await log({ kind: "assistant", turn: k, text: answer.text ?? "", reasoning: answer.reasoning ?? "", ms: Date.now() - asked,
        usage: call.usage, cost: call.cost, tools: answer.calls.map((t) => ({ id: t.id, name: t.function.name, args: safeJson(t.function.arguments) })) });
      // The turn itself: what it said and thought, what the model call took.
      step({ turn: k, kind: "think", call: call.id, text: answer.text?.trim().slice(0, 4000), reasoning: answer.reasoning?.trim().slice(0, 8000),
        ms: Date.now() - asked, cost: call.cost, provider: call.provider, effort: call.effort ?? "off",
        tokens: call.usage ? { input: call.usage.input, output: call.usage.output, reasoning: call.usage.reasoning, cached: call.usage.cached } : undefined });
      messages.push({ role: "assistant", content: answer.text ?? "", tool_calls: answer.calls.map((t) => ({ id: t.id, type: "function", function: t.function })),
        ...(answer.output ? { _openai: answer.output } : {}) });
      if (!answer.calls.length) {
        transient.at = undefined;
        mechanical = false;
        messages.push({ role: "user", content: "Use a tool: carry on building, or finish once phone_check has passed." });
        continue;
      }
      // Tool results go back in order, then any pictures they showed (user messages may follow tool messages only).
      let finished = false;
      const results: { name: string; ok: boolean }[] = [];
      for (const t of answer.calls) {
        if (o.stop?.()) break;
        const args = safeJson(t.function.arguments);
        let r: Awaited<ReturnType<typeof run1>>;
        const began = Date.now();
        agent.live = { turn: k, started: began, text: "", reasoning: "", tools: [`running ${t.function.name}`] };
        saveRun(run);
        try {
          r = await run1(t.function.name, args);
        } catch (error) {
          r = { ok: false, text: (error as Error).message.slice(0, 1500) };
        }
        agent.live = undefined;
        const ms = Date.now() - began;
        messages.push({ role: "tool", tool_call_id: t.id, content: r.text });
        results.push({ name: t.function.name, ok: r.ok });
        await log({ kind: "tool", turn: k, id: t.id, name: t.function.name, ok: r.ok, ms, result: r.text, ...(r.exit !== undefined ? { exit: r.exit } : {}),
          ...(r.version ? { version: r.version } : {}) });
        step({ turn: k, kind: r.done ? "finish" : "tool", tool: t.function.name, call: call.id, args: brief(args), result: r.text.slice(0, 6000), ok: r.ok,
          images: r.images, video: r.video, seconds: r.seconds, ms, exit: r.exit, version: r.version });
        if (r.done) finished = true;
      }
      attachShown();
      if (!finished && !o.stop?.()) await startAhead().catch(() => {});
      if (o.stop?.()) {
        agent.status = "stopped";
        break;
      }
      // The next turn thinks at the level set unless this one only did mechanical work that went through.
      mechanical = results.every((x) => x.ok && EASY.has(x.name));
      if (finished) {
        agent.status = "done";
        break;
      }
      // Condensed only once there is something to condense (more than the last turn since the summary).
      if ((call.usage?.input ?? 0) > COMPACT_TOKENS && messages.length > 8) await compact(k);
      if (k === settings.turns) {
        agent.status = "failed";
        agent.error = `out of turns (${settings.turns}) before it finished`;
      }
    }
  } catch (error) {
    agent.status = o.stop?.() ? "stopped" : "failed";
    if (agent.status === "failed") agent.error = (error as Error).message.slice(0, 1200);
  } finally {
    await stopAhead().catch(() => {});
    if (agent.status === "running") agent.status = o.stop?.() ? "stopped" : "failed";
    agent.live = undefined;
    agent.ended = Date.now();
    await log({ kind: "end", status: agent.status, error: agent.error ?? null, summary: agent.summary ?? null, turns: agent.turns, cost: agent.cost });
    saveRun(run, true);
  }
}
