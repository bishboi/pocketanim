/**
 * The model seam.
 *
 * Two implementations behind one function, chosen by whether a key exists.
 * That is not a convenience: OpenRouter is unreachable from the development
 * container, so without an offline provider nothing downstream of generation
 * could be exercised at all. The fixture returns real, exportable Manim, so
 * the whole pipeline -- generate, export, preview, edit -- runs and can be
 * tested with no network and no key.
 */

import { spawn } from "node:child_process";
import { Agent, fetch as undiciFetch } from "undici";
import { CostLedger, type AiPicture } from "./costs";
import { Template, explainWith, filmBrief, isLecture, layoutContract, templateById } from "./templates";
import { unbuiltFigures, type Compiled } from "./lecture";
import { ADD_CHAPTERS_TOOL, DRAWING_TOOL, ILLUSTRATION_TOOL, findDrawings, IMAGE_TOOL, LANGUAGES, LECTURE_TOOL, PARTS_OVER_MINUTES, classifySubject, compileLecture, findIllustration, findImage, fixtureScript, languagePrompt, lecturePrompt, referencePrompt, resolveRegion, targetMinutes, uncoveredParts, type Language, type Subject } from "./lecture";
import { figurePictures, figurePrompt, loadDocument, scriptFigures, teachingFigures, type DocumentManifest } from "./document";
import { drawFigures, figuresWithin, type Drawn } from "./figures";
import type { BookQuestion } from "./questions";
import { boundParts, joinParts, maxVideoMinutes, splitByTopics, splitLecture, topicPart, type LecturePart } from "./parts";
import { planTopics, topicOf, topicLabel, type Topic } from "./topics";
import { SECTION_TOOL, cleanSection, fromTranscriptPrompt, repairable, repairRequest, rewroteWhole, sectionForVideo, sectionProblem, sectionRequest, sectionsOf, transcriptPrompt, transcriptProblem, transcriptSections, type Section, type WrittenSection } from "./transcript";
import { fillLines } from "./lines";
import { REPO, python, speakAhead } from "./pocketanim";
import { ensureSymbols, symbolsReady } from "./version";
import { AgentEvent, TOOLS, applySceneTool, findMap, moleculeGuide, runTool } from "./agent";

export type Generated = {
  source: string;
  /** A lecture over PANIM_MAX_VIDEO_MINUTES, as more than one video (lib/parts.ts); `source` is the first. */
  parts?: { title: string; minutes: number; source: string }[];
  sceneClass: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
};

export type GenerateRequest = {
  content: string;
  templateId: string;
  previousSource?: string;
  instruction?: string;
  /** An uploaded lecture PDF (lib/document.ts): its figures are offered to the model. */
  documentId?: string;
  /** The lecture's length, chosen on the page; without it, the request's words or the content's size decide. */
  minutes?: number;
  /** The subject, chosen on the page (lib/lecture.ts SUBJECTS); without it, the content decides. */
  subject?: string;
  /** A reference video's transcript (lib/document.ts addReference): the lecture follows its structure. */
  referenceId?: string;
  /** The narration's language (lib/lecture.ts LANGUAGES): "hinglish" is Hindi with English terms, English on screen. */
  language?: string;
  /** The model that writes the lecture's transcript (stage 1); without it, OPENROUTER_TRANSCRIPT_MODEL. */
  transcriptModel?: string;
  /** The model that draws the lecture's pictures as SVG (figures.ts, drawings.ts); without it, OPENROUTER_SVG_MODEL. */
  svgModel?: string;
  /** How the pictures are drawn (lib/artstyles.ts): "auto" or left out, the template's own art. */
  art?: string;
};

const DEFAULT_MODEL = "anthropic/claude-sonnet-4.5";

/** The model that writes the video (the beat script and its Manim scene): OPENROUTER_MODEL. */
export function videoModel(): string {
  return process.env.OPENROUTER_MODEL || DEFAULT_MODEL;
}

/**
 * The model that writes the lecture's spoken transcript, before any picture: the page's choice, else
 * OPENROUTER_TRANSCRIPT_MODEL, else the video's model. Writing a long, natural teacher's talk and building
 * pictures step by step are different jobs, so each can have the model that does it best.
 */
export function transcriptModel(chosen?: string): string {
  return chosen?.trim() || process.env.OPENROUTER_TRANSCRIPT_MODEL || videoModel();
}

/**
 * The model that draws the lecture's pictures as SVG (the book's figures and every draw op): the page's choice, else
 * OPENROUTER_SVG_MODEL, else the video's model. Drawing well is its own skill (and a model that reads images can
 * check its own drawing), so it can have the model that does it best.
 */
export function svgModel(chosen?: string): string {
  return chosen?.trim() || process.env.OPENROUTER_SVG_MODEL || videoModel();
}

const SCENE_CLASS = "GeneratedScene";
/** How long a turn may pass with nothing from the model before it is stopped (PANIM_MODEL_WAIT_MINUTES). */
const FIRST_REPLY_MINUTES = Math.max(1, Number(process.env.PANIM_MODEL_WAIT_MINUTES) || 15);
// A reply that streams nothing for this long after it started writing has stalled: asked again.
const STALL_MS = Math.max(30, Number(process.env.PANIM_STALL_SECONDS) || 180) * 1000;
/** m:ss, for the progress lines. */
const clock = (ms: number) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

/**
 * How hard the model thinks before it writes: PANIM_REASONING_EFFORT = low (the default), minimal, medium or
 * high; "off" sends no setting (the model's own default). Low keeps a lecture quick and cheap to write.
 */
export function reasoningOption(): { reasoning?: { effort: string } } {
  const effort = (process.env.PANIM_REASONING_EFFORT || "low").trim().toLowerCase();
  if (effort === "off" || effort === "none" || effort === "default") return {};
  return { reasoning: { effort: ["minimal", "low", "medium", "high"].includes(effort) ? effort : "low" } };
}

function systemPrompt(template: Template): string {
  return [
    "You are an agent that writes one Manim Community scene for a phone renderer.",
    "Use tools when they help. A short idea stays under a minute. A lesson may run up to 30 minutes of speech.",
    "Call find_map for a map, with the place the scene is about. The drawing must",
    "be that place: Rajasthan is the outline of Rajasthan, not the world. If the",
    "tool does not return an exact match, call it again with a name from its list.",
    "Call locate_on_map for every city, river, desert, or range you mark, with",
    "the region and the feature. Plot only the lon/lat it returns, through",
    "project(lon, lat). build_region() returns (group, project); unpack both.",
    "If locate_on_map says the feature was not found, do not mark it.",
    "Call molecule_guide for a chemical structure, again if you need another molecule.",
    "Put the Manim file in tools, not in the reply. Call write_scene first with only",
    "the opening beat: the title, the first picture, and one or two voice lines.",
    "Add later material with edit_scene. Each call adds several beats, about two minutes of speech, not one line.",
    "Never send a whole 30 minute lecture in one write_scene. Build it in those two-minute stretches.",
    "Do not print the tool arguments in your reply. Call the tool and leave the message empty.",
    "If edit_scene says the span is missing or matches more than once, call it again",
    "with a better span. When the scene is ready, stop calling tools and reply with",
    "one short sentence.",
    "Every line must be valid Python. Never leave a placeholder, an ellipsis argument,",
    "or a discarded alternative written as `if False else`.",
    "",
    "You are not shown the rendered video. Do not ask for frames or revise from",
    "how the picture looks. A person does that, in words.",
    "",
    `The scene class must be named ${SCENE_CLASS}.`,
    "",
    "For ordinary scenes stay with Circle, Square, Rectangle, RoundedRectangle,",
    "Line, Arrow, Dot, Text, MathTex, Tex, VGroup, Create, Write, FadeIn,",
    "FadeOut, Transform, TransformMatchingTex, GrowFromCenter, and",
    ".animate.scale() / .shift(). Do not pass lag_ratio. Do not use LaggedStart.",
    "Rotate a vector with rotate_vector(vector, angle). There is no rotate() function.",
    "Index a vector, never a number. Write (UP * t)[1], not UP * (t)[1].",
    "A map is ONLY the cartopy scene find_map returns, with places from locate_on_map. Never draw a map yourself:",
    "no Polygon or points for a country, coast, border or continent, no SVGs or pictures of maps. A guessed shape is wrong.",
    "A molecule may use Sphere, Line3D, and ThreeDScene as molecule_guide shows.",
    "",
    explainWith(),
    "",
    layoutContract(),
    "",
    filmBrief(template),
    "",
    "LENGTH. Add up the self.wait calls that follow # voice: lines. That sum is the spoken length.",
    "Stop at 30 minutes, which is 1800 seconds. Do not pad a short idea to fill that time.",
    "When the content asks for a long lecture, keep adding two-minute stretches until the spoken length is near 30 minutes, then close.",
  ].join("\n");
}

function userPrompt(request: GenerateRequest): string {
  if (request.instruction && request.previousSource) {
    return [
      "Here is the current scene:",
      "",
      request.previousSource,
      "",
      `Keep this visual style: ${templateById(request.templateId).name}. ${filmBrief(templateById(request.templateId))}`,
      "",
      "The file above is already loaded. Change it with edit_scene. Do not call write_scene",
      "and do not reply with the file. Change it as follows:",
      request.instruction,
    ].join("\n");
  }
  const template = templateById(request.templateId);
  return [
    filmBrief(template),
    "",
    "Write a scene that explains the following content in that style only.",
    "Open with write_scene, one beat only. Then each edit_scene adds about two minutes of speech.",
    "A long lecture may run up to 30 minutes. Do not send that whole lecture in one call:",
    "",
    request.content,
  ].join("\n");
}

function lectureUserPrompt(request: GenerateRequest): string {
  if (request.instruction && request.previousSource) {
    return [
      "Here is the current lecture scene, compiled from a beat script:",
      "",
      request.previousSource,
      "",
      "Change it as follows. Small changes: edit_scene on this file. Large ones: write_lecture with a new script.",
      request.instruction,
    ].join("\n");
  }
  if (request.referenceId && !request.content.trim()) {
    return "Write a narrated lecture that remakes the reference video (its transcript is in your instructions), with write_lecture.";
  }
  return [
    `Write a narrated lecture on the following content with write_lecture${request.referenceId ?
      ", following the reference video's structure (its transcript is in your instructions)" : ""}.`,
    "",
    request.content,
  ].join("\n");
}

/**
 * A lecture script the model put in its reply text instead of calling write_lecture: the bare script, a
 * {"script": …} object, or a tool call written out as text, with or without a code fence. Null when the text
 * holds no such JSON (or it was cut off before it closed).
 */
export function scriptFromText(text: string): Record<string, unknown> | null {
  const fenced = text.match(/```(?:json)?\s*\n([\s\S]*?)```/);
  const body = fenced ? fenced[1] : text;
  const start = body.indexOf("{");
  const end = body.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(body.slice(start, end + 1));
  } catch {
    return null;
  }
  const dig = (value: unknown, depth = 0): Record<string, unknown> | null => {
    if (!value || typeof value !== "object" || depth > 3) return null;
    const obj = value as Record<string, unknown>;
    if (Array.isArray(obj.chapters)) return obj;
    for (const key of ["script", "arguments", "parameters", "input"]) {
      const inner = typeof obj[key] === "string" ? (() => { try { return JSON.parse(obj[key] as string); } catch { return null; } })() : obj[key];
      const found = dig(inner, depth + 1);
      if (found) return found;
    }
    return null;
  };
  return dig(parsed);
}

/**
 * The model often writes a sentence before the file ("I cannot write a
 * file…"). Export then fails on line 1. Keep from the first Manim import.
 */
function extractScene(text: string): string {
  const fence = text.match(/```(?:python)?\s*\n([\s\S]*?)```/);
  const body = (fence ? fence[1] : text).replace(/\n```[\s\S]*$/, "\n");
  const at = body.search(/^from manim import\b/m);
  if (at < 0) {
    const said = body.trim().slice(0, 180);
    throw new Error(said ? `The model did not return a scene. It said: ${said}` : "The model returned an empty scene.");
  }
  return body.slice(at).trim() + "\n";
}

/**
 * The compiler's errors that name a beat ("chapter 3 beat 7: ..."), mended by leaving that beat's ops out: the
 * beat is said over the picture before it. A chapter "missing title" is given one. Returns how many beats lost
 * their ops (or chapters got titles); the script is changed in place.
 */
export function dropOps(script: Record<string, unknown>, errors: string[]): number {
  const chapters = (Array.isArray(script.chapters) ? script.chapters : []) as { title?: unknown; beats?: { do?: unknown }[] }[];
  let mended = 0;
  const seen = new Set<string>();
  for (const error of errors) {
    const beat = /^chapter (\d+) beat (\d+)\b/.exec(error);
    if (beat) {
      const target = chapters[Number(beat[1]) - 1]?.beats?.[Number(beat[2]) - 1];
      if (target && !seen.has(beat[0]) && Array.isArray(target.do) && target.do.length) {
        target.do = [];
        seen.add(beat[0]);
        mended += 1;
      }
      continue;
    }
    const untitled = /^chapter (\d+): missing title/.exec(error);
    const chapter = untitled ? chapters[Number(untitled[1]) - 1] : null;
    if (chapter && !chapter.title) {
      const said = String((chapter.beats?.[0] as { say?: unknown } | undefined)?.say ?? "").split(/[.?!]/)[0];
      chapter.title = said.split(/\s+/).slice(0, 6).join(" ") || "Chapter";
      mended += 1;
    }
  }
  return mended;
}

/** Seconds of narration already written, from the waits that follow # voice: lines. */
function voiceSeconds(source: string): number {
  const waits = source.matchAll(/# voice:.*\n[ \t]*self\.wait\(([0-9.]+)\)/g);
  let total = 0;
  for (const wait of waits) total += Number(wait[1]) || 0;
  return total;
}

/** A user message may carry pictures (the book's figures) for a model that reads images. */
type ContentPart = { type: "text"; text: string; cache_control?: { type: "ephemeral" } } | { type: "image_url"; image_url: { url: string } };

type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
  tool_calls?: { id: string; type: "function"; function: { name: string; arguments: string } }[];
  tool_call_id?: string;
};

/** What is sent: a ChatMessage, or a user message with pictures in it (or a system prompt marked for caching). */
type OutMessage = ChatMessage | (Omit<ChatMessage, "content"> & { role: "user" | "system"; content: ContentPart[] });

/**
 * A system prompt the provider keeps between requests: every section's request starts with the same one, so after
 * the first it is read from the provider's cache (cheaper, and the reply starts sooner). Anthropic and Google models
 * on OpenRouter need it marked (cache_control); the others cache a repeated prefix on their own.
 */
function cachedSystem(content: string, model: string): OutMessage {
  if (/^(anthropic|google)\//.test(model)) {
    return { role: "system", content: [{ type: "text", text: content, cache_control: { type: "ephemeral" } }] };
  }
  return { role: "system", content };
}

/** The messages as sent: a plain system prompt at the front marked for caching (the fix-up turns resend it each turn). */
function withCachedSystem(messages: OutMessage[], model: string): OutMessage[] {
  const first = messages[0];
  if (first?.role !== "system" || typeof first.content !== "string") return messages;
  return [cachedSystem(first.content, model), ...messages.slice(1)];
}

/** Items handed from one stage to the next as they are made: next() waits for one, null once it is closed. */
class Queue<T> {
  private items: T[] = [];
  private waiting: { resolve: (item: T | null) => void; reject: (error: unknown) => void }[] = [];
  private closed = false;
  private error: unknown = null;
  private failed = false;

  static of<T>(items: T[]): Queue<T> {
    const queue = new Queue<T>();
    items.forEach((item) => queue.push(item));
    queue.close();
    return queue;
  }

  push(item: T) {
    const waiter = this.waiting.shift();
    if (waiter) waiter.resolve(item);
    else this.items.push(item);
  }

  close() {
    this.closed = true;
    for (const waiter of this.waiting.splice(0)) waiter.resolve(null);
  }

  fail(error: unknown) {
    this.failed = true;
    this.error = error;
    for (const waiter of this.waiting.splice(0)) waiter.reject(error);
  }

  next(): Promise<T | null> {
    if (this.items.length) return Promise.resolve(this.items.shift()!);
    if (this.failed) return Promise.reject(this.error);
    if (this.closed) return Promise.resolve(null);
    return new Promise((resolve, reject) => this.waiting.push({ resolve, reject }));
  }
}

type Usage = { prompt_tokens?: number; completion_tokens?: number; cost?: number };

type ToolCall = NonNullable<ChatMessage["tool_calls"]>[number];

function toolCallsFrom(raw: { id?: string; name?: string; arguments?: string }[]): ToolCall[] {
  return raw
    .filter((call) => call.name)
    .map((call) => ({
      id: call.id || `call_${call.name}`,
      type: "function" as const,
      function: {
        name: call.name ?? "",
        arguments: call.arguments || "{}",
      },
    }));
}

function textOf(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return "";
  return value
    .map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object" && "text" in part) return String((part as { text?: unknown }).text ?? "");
      return "";
    })
    .join("");
}

function messageFromBody(body: {
  choices?: { message?: ChatMessage }[];
  usage?: Usage;
}): { message: ChatMessage; usage?: Usage } {
  const message = body.choices?.[0]?.message;
  if (!message) throw new Error("OpenRouter returned no message");
  const content = textOf(message.content);
  return { message: { ...message, content: content || null }, usage: body.usage };
}

/**
 * The connection to OpenRouter. Node's own fetch drops a request that sends nothing for 5 minutes (headers or
 * body) with a bare "fetch failed"; a reasoning model can think silently for longer, and the agent has its own
 * watchdog (FIRST_REPLY_MINUTES), so those timeouts are off here.
 */
const OPENROUTER_AGENT = new Agent({ headersTimeout: 0, bodyTimeout: 0, connect: { timeout: 30_000 } });

/** A network failure (not an answer from OpenRouter): worth sending the same request again. */
function isNetworkError(error: unknown): boolean {
  const text = `${error instanceof Error ? error.message : String(error)} ${causeCode(error)}`;
  return /fetch failed|terminated|socket|ECONNRESET|ETIMEDOUT|EPIPE|EAI_AGAIN|UND_ERR/i.test(text);
}

function causeCode(error: unknown): string {
  const cause = (error as { cause?: { code?: string; message?: string } })?.cause;
  return cause ? String(cause.code ?? cause.message ?? "") : "";
}

/** "fetch failed" with what actually went wrong, and what to do about it. */
export function explainNetworkError(error: unknown): string {
  const code = causeCode(error);
  const detail = (error as { cause?: { message?: string } })?.cause?.message ?? "";
  const why = /ENOTFOUND|EAI_AGAIN/.test(code) ? "the name openrouter.ai could not be looked up: is this machine online?"
    : /ECONNREFUSED/.test(code) ? "the connection was refused (a proxy or firewall?)"
    : /CERT|SELF_SIGNED|UNABLE_TO_VERIFY/.test(code + detail) ? "the TLS certificate was not trusted (a VPN or proxy inspecting traffic?)"
    : /CONNECT_TIMEOUT|ETIMEDOUT/.test(code) ? "connecting timed out (a slow or blocked network)"
    : /ECONNRESET|SOCKET|EPIPE|terminated/i.test(code + detail) ? "the connection dropped mid-reply (Wi-Fi, a VPN, or the Mac sleeping)"
    : code || detail || "no reason given";
  return `Could not reach OpenRouter: ${why}${code ? ` [${code}]` : ""}. Tried 3 times.`;
}

function isEmptyReply(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  // "Provider returned an empty response" comes from OpenRouter in the stream; a 5xx or an overloaded provider
  // is the same kind of passing failure, and the next attempt usually goes to another provider.
  return (
    isCutStream(error) ||
    /empty (message|response)|returned no message|OpenRouter (429|50[0234])|overloaded|provider returned error/i.test(message)
  );
}

/** The provider's own stream stopped mid-reply ("Stream ended before a terminal response event"): usually a long
 * reasoning reply that ran past the provider's time limit. Retried, and without reasoning, which is the slow part. */
function isCutStream(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /stream ended|terminal response|premature|incomplete (response|stream)|upstream (error|timeout)|timed? ?out/i.test(message);
}

/** Batch token deltas so the page updates live without a render per token. */
function batchDeltas(onDelta: (kind: "thinking" | "assistant", text: string) => void) {
  let kind: "thinking" | "assistant" | null = null;
  let pending = "";
  let timer: ReturnType<typeof setTimeout> | null = null;
  const flush = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (!pending || !kind) return;
    onDelta(kind, pending);
    pending = "";
    kind = null;
  };
  return {
    push(next: "thinking" | "assistant", text: string) {
      if (!text) return;
      if (kind && kind !== next) flush();
      kind = next;
      pending += text;
      if (pending.length >= 48) flush();
      else if (!timer) timer = setTimeout(flush, 80);
    },
    flush,
  };
}

type ToolSpec = (typeof TOOLS)[number] | typeof LECTURE_TOOL | typeof ADD_CHAPTERS_TOOL | typeof ILLUSTRATION_TOOL | typeof DRAWING_TOOL | typeof IMAGE_TOOL | typeof SECTION_TOOL;

async function streamCompletion(
  key: string,
  model: string,
  messages: OutMessage[],
  onDelta: (kind: "thinking" | "assistant", text: string) => void,
  tools: ToolSpec[] = TOOLS,
  signal?: AbortSignal,
  toolChoice: "auto" | "required" = "auto",
  withReasoning = true,
): Promise<{ message: ChatMessage; usage?: Usage; finishReason: string }> {
  const response = await undiciFetch(process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    signal,
    dispatcher: OPENROUTER_AGENT,
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      messages: withCachedSystem(messages, model),
      tools,
      tool_choice: toolChoice,
      stream: true,
      usage: { include: true },
      ...(withReasoning ? reasoningOption() : {}),
    }),
  });
  if (!response.ok) {
    throw new Error(`OpenRouter ${response.status}: ${(await response.text()).slice(0, 400)}`);
  }
  if (!response.body) throw new Error("OpenRouter returned no stream");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const deltas = batchDeltas(onDelta);
  let buffer = "";
  let raw = "";
  let content = "";
  let reasoning = "";
  let sawStream = false;
  let finishReason = "";
  const calls: { id: string; name: string; arguments: string }[] = [];
  let usage: Usage | undefined;

  const takeDelta = (delta: {
    content?: unknown;
    reasoning?: string | null;
    reasoning_content?: string | null;
    tool_calls?: {
      index?: number;
      id?: string;
      name?: string;
      arguments?: string;
      function?: { name?: string; arguments?: string };
    }[];
  }) => {
    const thought = delta.reasoning || delta.reasoning_content || "";
    if (thought) {
      reasoning += thought;
      deltas.push("thinking", thought);
    }
    const piece = textOf(delta.content);
    if (piece) {
      content += piece;
      deltas.push("assistant", piece);
    }
    for (const part of delta.tool_calls ?? []) {
      const index = part.index ?? 0;
      if (!calls[index]) calls[index] = { id: "", name: "", arguments: "" };
      if (part.id) calls[index].id = part.id;
      const name = part.function?.name || part.name || "";
      const args = part.function?.arguments || part.arguments || "";
      if (name) calls[index].name += name;
      if (args) {
        calls[index].arguments += args;
        const tool = calls[index].name || "tool";
        if (tool === "write_scene" || tool === "edit_scene" || tool === "write_lecture" || tool === "write_section" ||
            tool === "add_chapters") {
          deltas.push("assistant", args);
        }
      }
    }
  };

  const takeLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) return;
    const data = trimmed.slice(5).trim();
    if (!data || data === "[DONE]") return;
    sawStream = true;
    let parsed: {
      error?: { message?: string };
      usage?: Usage;
      choices?: {
        finish_reason?: string | null;
        delta?: Parameters<typeof takeDelta>[0];
        message?: ChatMessage & { tool_calls?: ToolCall[] };
      }[];
    };
    try {
      parsed = JSON.parse(data);
    } catch {
      return;
    }
    if (parsed.error?.message) throw new Error(parsed.error.message);
    if (parsed.usage) usage = parsed.usage;
    const choice = parsed.choices?.[0];
    if (choice?.finish_reason) finishReason = choice.finish_reason;
    if (choice?.delta) takeDelta(choice.delta);
    const messageText = textOf(choice?.message?.content);
    if (messageText && !content) {
      content = messageText;
      deltas.push("assistant", messageText);
    }
    for (const call of choice?.message?.tool_calls ?? []) {
      if (!calls.some((existing) => existing.id === call.id && existing.name === call.function.name)) {
        calls.push({ id: call.id, name: call.function.name, arguments: call.function.arguments });
      }
    }
  };

  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    const piece = decoder.decode(chunk.value, { stream: true });
    raw += piece;
    buffer += piece;
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) takeLine(line);
  }
  if (buffer.trim()) takeLine(buffer);
  deltas.flush();
  if (!content.trim() && /from manim import/.test(reasoning)) content = reasoning;

  if (!sawStream) {
    const body = JSON.parse(raw);
    const parsed = messageFromBody(body);
    const text = parsed.message.content?.trim() ?? "";
    if (text) onDelta("assistant", text);
    return { ...parsed, finishReason: "" };
  }

  const tool_calls = toolCallsFrom(calls);
  return {
    message: {
      role: "assistant",
      content: content || null,
      tool_calls: tool_calls.length ? tool_calls : undefined,
    },
    usage,
    finishReason,
  };
}

const EMPTY_RETRIES = 4;

async function completionWithRetry(
  key: string,
  model: string,
  messages: OutMessage[],
  emit: (event: AgentEvent) => void,
  onDelta: (kind: "thinking" | "assistant", text: string) => void,
  tools: ToolSpec[] = TOOLS,
  signal?: AbortSignal,
  toolChoice: "auto" | "required" = "auto",
): Promise<{ message: ChatMessage; usage?: Usage; finishReason?: string; span: [number, number] }> {
  // When the request began and its answer came: the task's time (lib/costs.ts), retries included.
  const began = Date.now();
  let empties = 0;
  let cut = false;
  for (let attempt = 1; attempt <= EMPTY_RETRIES; attempt++) {
    // After an empty reply, ask more loosely: some providers answer nothing when a tool call is "required",
    // and a reasoning model can spend its whole output on thinking. The prompts still ask for the tool.
    const choice = empties > 0 ? "auto" : toolChoice;
    const reasoning = empties < 2 && !cut;
    try {
      let result;
      try {
        result = await streamCompletion(key, model, messages, onDelta, tools, signal, choice, reasoning);
      } catch (error) {
        // A provider that refuses "required" gets the same request with "auto".
        if (choice === "auto" || !/tool_choice|required/i.test(String(error))) throw error;
        result = await streamCompletion(key, model, messages, onDelta, tools, signal, "auto", reasoning);
      }
      const text = result.message.content?.trim() ?? "";
      const calls = result.message.tool_calls ?? [];
      if (!text && calls.length === 0) {
        const why = result.finishReason ? ` (${result.finishReason})` : "";
        throw new Error(`OpenRouter returned an empty message${why}`);
      }
      return { ...result, span: [began, Date.now()] };
    } catch (error) {
      if (!signal?.aborted && isNetworkError(error)) {
        // A dropped connection: the same request again, after a pause, before giving up with the real reason.
        if (attempt === EMPTY_RETRIES) throw new Error(explainNetworkError(error));
        emit({
          type: "message",
          role: "status",
          text: `The connection to OpenRouter failed (${causeCode(error) || "network"}). Retrying (${attempt + 1} of ${EMPTY_RETRIES})…`,
        });
        await new Promise((resolve) => setTimeout(resolve, 3000 * attempt));
        continue;
      }
      if (signal?.aborted || !isEmptyReply(error)) throw error;
      const reason = error instanceof Error ? error.message : String(error);
      if (attempt === EMPTY_RETRIES) {
        throw new Error(
          `${reason} — ${EMPTY_RETRIES} times in a row. The model's provider on OpenRouter is not answering this ` +
            "request; try again in a minute, or pick another model (a non-reasoning one, or a larger context window, " +
            "helps with a long transcript).",
        );
      }
      empties += 1;
      cut = cut || isCutStream(error);
      emit({
        type: "message",
        role: "status",
        text: `OpenRouter: ${reason}. Retrying (${attempt + 1} of ${EMPTY_RETRIES})…`,
      });
      await new Promise((resolve) => setTimeout(resolve, 2000 * attempt));
    }
  }
  throw new Error("OpenRouter returned an empty message");
}

/** The lecture script behind the source a generation returns, so it can be cut into parts (lib/parts.ts). */
type Kept = {
  script?: unknown;
  source?: string;
  minutes?: number;
  options?: () => Parameters<typeof compileLecture>[1];
  /** The generation's cost ledger, for the repair after it and the done event. */
  ledger?: CostLedger;
};

async function viaOpenRouter(
  request: GenerateRequest,
  emit: (event: AgentEvent) => void,
  stopped: () => boolean = () => false,
  kept: Kept = {},
): Promise<Generated> {
  const key = process.env.OPENROUTER_API_KEY!;
  // How long each stage took, from the start of the run, in the status stream.
  const startedAt = Date.now();
  const mark = (stage: string) =>
    emit({ type: "message", role: "status", text: `[time] ${stage}: ${Math.round((Date.now() - startedAt) / 1000)} s` });
  // The transcript runs in the background of the video's chapters: when they fail, it stops too.
  let abandoned = false;
  const pageClosed = stopped;
  stopped = () => abandoned || pageClosed();
  const model = videoModel();
  const template = templateById(request.templateId);
  const lecture = isLecture(template);
  const doc = await documentOf(request);
  const reference = lecture ? await documentOf({ ...request, documentId: request.referenceId }) : null;
  const language = LANGUAGES.includes(request.language as Language) ? (request.language as Language) : "auto";
  const referenceText = reference?.parts?.map((p) => p.text).join("\n") ?? "";
  // Without a chosen length, a remake runs as long as the video it follows.
  const referenceMinutes = reference?.video?.duration ? Math.min(90, Math.max(3, Math.round(reference.video.duration / 60))) : 0;
  // As long as the content needs; a long one is as many micro-lectures of 25-30 min as that makes (topics.ts).
  const minutes = request.minutes ?? (referenceMinutes ||
    targetMinutes(`${request.content}\n${request.instruction ?? ""}`, doc?.markdown ?? ""));
  const subject = lecture
    ? await subjectOf({ ...request, content: `${request.content}\n${referenceText.slice(0, 15000)}\n${(doc?.markdown ?? "").slice(0, 15000)}` }, emit)
    : null;
  const style = lecture ? effectiveStyle(template, subject) : template.style;
  if (reference?.parts?.length) {
    emit({ type: "message", role: "status", text: `Reference video: ${reference.video?.title ?? "transcript"}, ` +
      `${reference.parts.length} parts; the lecture follows them in order (about ${minutes} min).` });
  }
  // The book's figures, redrawn as SVG by the model (figures.ts) while the transcript is written; the script
  // writer is told about them once they are done (stage 2). PANIM_SVG_FIGURES=0 builds them in Manim as before.
  // What the lecture cost, task by task (lib/costs.ts); costUsd is its total. Both stages and the figures run at
  // once, so every bill goes through the ledger and is sent with a usage event straight away.
  const ledger = new CostLedger();
  kept.ledger = ledger;
  let inputTokens = 0;
  let outputTokens = 0;
  let costUsd = 0;
  const sendCosts = (text: string) =>
    emit({ type: "usage", text, inputTokens, outputTokens, costUsd, costs: ledger.snapshot(), seconds: ledger.elapsed });
  const figureTally = { svg: 0, kept: 0, manim: 0, photo: 0, failed: 0 };
  // Each picture the AI made for the lecture goes to the page as it is made (once), with what it cost.
  const shownPictures = new Set<string>();
  const showPicture = (picture: AiPicture) => {
    if (shownPictures.has(picture.file)) return;
    shownPictures.add(picture.file);
    emit({ type: "picture", picture });
  };
  const billImages = (images: { path: string; title: string; usd: number; made: boolean; paid: number | null }[]) => {
    const made = images.filter((i) => i.made);
    if (made.length) {
      const usd = made.reduce((t, i) => t + i.usd, 0);
      costUsd = ledger.bill("images", usd, { items: made.length });
      sendCosts(`${made.length} illustration${made.length > 1 ? "s" : ""} generated: $${usd.toFixed(4)}`);
    }
    for (const i of images) {
      showPicture({ kind: "illustration", file: i.path, title: i.title, usd: i.usd, reused: !i.made, paid: i.paid,
        detail: process.env.PANIM_IMAGE_MODEL || "google/gemini-2.5-flash-image" });
    }
  };
  // Figures settled so far: stage 2 waits for them only so long (PANIM_FIGURE_WAIT_SECONDS), then goes on with
  // these; a figure drawn later is kept on disk for the next run, and this one rebuilds it in Manim.
  const figuresReady: Record<string, Drawn> = {};
  const drawingStarted = Date.now();
  const drawing = lecture && doc && process.env.PANIM_SVG_FIGURES !== "0" && teachingFigures(doc).length
    ? drawFigures(teachingFigures(doc), {
      key: process.env.OPENROUTER_API_KEY ?? "",
      model: svgModel(request.svgModel),
      markdown: doc.markdown,
      repo: REPO,
      python: python(),
      onStatus: (text) => emit({ type: "message", role: "status", text }),
      onTime: (start, end) => ledger.time("figures", start, end),
      onCost: (usd) => {
        costUsd = ledger.bill("figures", usd);
        sendCosts(`book figure drawn: $${usd.toFixed(4)}`);
      },
      onDrawn: (id, made, kept) => {
        figuresReady[id] = made;
        // Every book figure is listed with what it cost, whatever became of it: drawn as SVG, a photo (shown as the
        // web's photo most like it, or as it is), or built in Manim.
        const figure = teachingFigures(doc).find((f) => f.id === id);
        const title = `${id}: ${figure?.caption ?? ""}`.trim();
        const paid = { usd: kept ? 0 : made.usd ?? 0, reused: kept, paid: made.usd ?? null };
        if (made.svg) {
          showPicture({ kind: "figure", file: made.svg, title, ...paid, detail: (made.parts ?? []).join(", "),
            status: made.animated ? "drawn as SVG, moving" : "drawn as SVG" });
        } else if (made.photo && (made.web?.file || figure?.file)) {
          showPicture({ kind: "photo", file: made.web?.file ?? figure!.file, title, ...paid,
            detail: made.web?.credit ?? made.query,
            status: made.web ? "shown as a real photo like it" : "shown as it is (no photo like it found)" });
        } else if (figure?.file) {
          showPicture({ kind: "rebuilt", file: figure.file, title, ...paid,
            status: made.manim ? "simple shapes: built in Manim" : `not drawn (${made.failed ?? "no SVG"}): built in Manim` });
        }
        if (made.svg) figureTally[kept ? "kept" : "svg"] += 1;
        else if (made.manim) figureTally.manim += 1;
        else if (made.photo) figureTally.photo += 1;
        else figureTally.failed += 1;
        ledger.count("figures", made.svg && !kept ? 1 : 0, [
          figureTally.kept ? `${figureTally.kept} drawn by an earlier run (free)` : "",
          figureTally.manim ? `${figureTally.manim} built in Manim` : "",
          figureTally.photo ? `${figureTally.photo} photograph${figureTally.photo > 1 ? "s" : ""}` : "",
          figureTally.failed ? `${figureTally.failed} not drawn` : "",
        ].filter(Boolean).join(", "));
        sendCosts(`book figure ${id}: ${made.svg ? (kept ? "drawn earlier" : "drawn as SVG") : made.manim ? "built in Manim" : made.photo ? (made.web ? "a photograph, shown as a real photo like it" : "a photograph") : "not drawn"}`);
      },
    }).catch((error) => {
      emit({ type: "message", role: "status", text: `The figures were not drawn (${String(error).slice(0, 160)}); ` +
        "they are built on the board instead." });
      return undefined;
    })
    : Promise.resolve(undefined);
  const systemBase = lecture
    ? lecturePrompt({ ...template, style }, minutes, subject ?? undefined)
    : systemPrompt(template);
  const systemTail = lecture ? languagePrompt(language) + (reference ? referencePrompt(reference) : "") : "";
  const user = lecture ? lectureUserPrompt(request) : userPrompt(request);
  const EDIT_TOOL = TOOLS.find((tool) => tool.function.name === "edit_scene")!;
  const tools: ToolSpec[] = lecture
    ? [LECTURE_TOOL, ...(minutes > PARTS_OVER_MINUTES ? [ADD_CHAPTERS_TOOL] : []), ILLUSTRATION_TOOL, DRAWING_TOOL, IMAGE_TOOL, EDIT_TOOL]
    : TOOLS;
  // STAGE 1: the whole lecture as a teacher speaks it, section by section, at full length, before any picture.
  const written: WrittenSection[] = [];
  // Each section as it is written, for its video chapters to start on (stage 2), and the end of the transcript.
  const writtenQueue = new Queue<WrittenSection>();
  // The sections written so far, by number, while the rest are still being written.
  const ready = new Map<number, WrittenSection>();
  let transcriptDone: Promise<void> = Promise.resolve();
  // The sections the transcript was planned in (transcript.ts), when there is one.
  let planned: Section[] = [];
  // The book's own questions (exercises, MCQs): every one explained, each option marked (questions.ts).
  let bookQs: BookQuestion[] = [];
  // A long lecture as a series of micro-lectures, one per topic (topics.ts): planned from the sections before a
  // word is written, so each is written as a lecture of its own and cut there.
  let topics: Topic[] = [];
  if (lecture && !(request.instruction && request.previousSource)) {
    // A book (a PDF) is taught section by section, each with its own slice of the text; a reference video is
    // remade part by part.
    const sections = transcriptSections(reference, minutes, reference?.parts?.length ? "" : doc?.markdown ?? "");
    topics = planTopics(sections);
    if (topics.length > 1) {
      emit({ type: "message", role: "status", text: `About ${Math.round(sections.reduce((n, x) => n + x.minutes, 0))} min: ` +
        `made as ${topics.length} videos of 25-30 min (` +
        topics.map((t) => `${t.index}${t.title ? ` "${t.title}"` : ""}: sections ${t.sections[0]}-${t.sections[t.sections.length - 1]}, ` +
          `${Math.round(t.minutes)} min`).join("; ") + ")." });
    }
    const fromBook = sections.some((s) => s.book);
    bookQs = sections.flatMap((s) => s.questions ?? []);
    if (fromBook) {
      const total = Math.round(sections.reduce((n, s) => n + s.minutes, 0));
      const mcqs = bookQs.filter((q) => q.choices.length).length;
      emit({ type: "message", role: "status", text: `Book: ${doc?.pages ?? "?"} pages, about ${doc?.words ?? "?"} words, ` +
        `taught in ${sections.length} sections (about ${Math.max(minutes, total)} min, as the writer judges)` +
        (bookQs.length ? `; its ${bookQs.length} question${bookQs.length > 1 ? "s" : ""}${mcqs ? ` (${mcqs} multiple-choice)` : ""} ` +
          "covered too." : ".") });
    }
    const prompt = transcriptPrompt({
      sections, minutes, language, languageRules: languagePrompt(language), subject: subject?.label,
      hasReference: !!reference?.parts?.length,
      // The book's text is already in its sections; only what was typed goes in beside it.
      content: fromBook ? request.content : `${request.content}\n${doc?.markdown ?? ""}`,
      topics,
    });
    emit({ type: "input", role: "system", text: prompt });
    const writer = transcriptModel(request.transcriptModel);
    emit({ type: "message", role: "status",
      text: `Transcript by ${writer}; the video (pictures and Manim) by ${model}.` });
    const TRIES = 4;
    // A few sections at once (each its own request): one after another, a book chapter took most of an hour.
    const PARALLEL = Math.max(1, Math.min(8, Number(process.env.PANIM_TRANSCRIPT_PARALLEL) || 6));
    const done = new Map<number, WrittenSection>();
    const failed: number[] = [];
    // What each section in flight is doing, for the progress line: when it started, words so far, its try.
    const live = new Map<number, { started: number; words: number; attempt: number; thinking: boolean; mending: boolean }>();
    let halted: unknown = null;
    const progress = setInterval(() => {
      if (!live.size) return;
      const now = Date.now();
      const parts = [...live.entries()].sort((x, y) => x[0] - y[0]).map(([n, p]) =>
        `${n} (${clock(now - p.started)}, ${p.words ? `about ${p.words} words` : p.thinking ? "thinking" : "waiting"}` +
        `${p.mending ? ", mending" : p.attempt > 1 ? `, try ${p.attempt}` : ""})`);
      emit({ type: "message", role: "status",
        text: `Transcript: ${done.size} of ${sections.length} sections written; writing ${parts.join(", ")}` });
    }, 10_000);

    /**
     * One section, tried up to TRIES times; null when no try gave anything usable. A section that leaves part of
     * its source out is asked only for what to add at its end (repairRequest): the section is kept and grows.
     */
    const writeOne = async (section: (typeof sections)[number]): Promise<WrittenSection | null> => {
      let note: string | undefined;
      // The longest refused try: kept when every try is refused, so one stubborn section does not lose the lecture.
      let fallback: { title: string; text: string; problem: string } | null = null;
      // The last try's section and why it was refused, for mending it instead of starting again.
      let current: { title: string; text: string; problem: string } | null = null;
      for (let attempt = 1; attempt <= TRIES; attempt++) {
        if (stopped() || halted) return null;
        const mending = !!current && repairable(current.problem);
        const state = { started: Date.now(), words: 0, attempt, thinking: false, mending };
        live.set(section.n, state);
        emit({ type: "message", role: "status",
          text: `Transcript: ${mending ? "adding what is missing to" : "writing"} section ${section.n} of ${sections.length}` +
            `${attempt > 1 && !mending ? `, try ${attempt} of ${TRIES}` : ""}` });
        const prior = [...done.values()].filter((w) => w.n < section.n).sort((x, y) => x.n - y.n);
        // A fresh request per section: the same system prompt (cached by the provider) and one short ask.
        const talk: OutMessage[] = [
          cachedSystem(prompt, writer),
          { role: "user", content: mending
            ? repairRequest(section, sections.length, current!.text, current!.problem)
            : sectionRequest(section, sections.length, prior, note, topicOf(topics, section.n)) },
        ];
        const abort = new AbortController();
        let why: "silent" | "stalled" | null = null;
        let lastDelta = 0;
        const watch = setInterval(() => {
          const now = Date.now();
          if (!lastDelta && now - state.started > FIRST_REPLY_MINUTES * 60_000) why = "silent";
          else if (lastDelta && now - lastDelta > STALL_MS) why = "stalled";
          if (why) abort.abort();
        }, 5000);
        let result;
        try {
          result = await completionWithRetry(key, writer, talk, emit, (kind, text) => {
            lastDelta = Date.now();
            if (kind === "thinking") state.thinking = true;
            else state.words += (text.match(/\s+/g) ?? []).length;
          }, [SECTION_TOOL], abort.signal, "required");
        } catch (error) {
          if (stopped()) return null;
          // A reply that stalled, or failed after its own retries, is one failed try, not the end of the lecture.
          note = why === "silent"
            ? `Your last try sent nothing for ${FIRST_REPLY_MINUTES} minutes. Write the section straight away, without long planning.`
            : why === "stalled"
              ? `Your last try stopped streaming partway (nothing for ${STALL_MS >= 120_000 ? `${Math.round(STALL_MS / 60000)} minutes` : `${Math.round(STALL_MS / 1000)} seconds`}). Write the whole section again, straight away.`
              : `Your last try failed (${error instanceof Error ? error.message.slice(0, 160) : String(error)}). Write the section again.`;
          emit({ type: "message", role: "status", text: `Transcript: section ${section.n}, try ${attempt}: ${note}` });
          continue;
        } finally {
          clearInterval(watch);
        }
        const addedIn = result.usage?.prompt_tokens ?? 0;
        const addedOut = result.usage?.completion_tokens ?? 0;
        const addedCost = Number(result.usage?.cost ?? 0);
        inputTokens += addedIn;
        outputTokens += addedOut;
        costUsd = ledger.bill("transcript", addedCost, { inputTokens: addedIn, outputTokens: addedOut, span: result.span });
        sendCosts(`transcript section ${section.n}: ${addedIn} in, ${addedOut} out, $${addedCost.toFixed(4)}`);
        // The section is whatever the reply wrote: the longest write_section text, whatever number it gave, or,
        // from a provider that answered in plain text instead of calling the tool, the reply itself.
        let title = "";
        let text = "";
        for (const call of result.message.tool_calls ?? []) {
          try {
            const args = JSON.parse(call.function.arguments || "{}") as { title?: string; text?: string };
            if (String(args.text ?? "").trim().length > text.length) {
              text = String(args.text).trim();
              title = String(args.title ?? "");
            }
          } catch {}
        }
        if (!text) text = (result.message.content ?? "").trim();
        if (mending && text) {
          // What to add, at the end; a reply that wrote the whole section again replaces it instead.
          if (!rewroteWhole(text, current!.text)) text = `${current!.text}\n\n${text}`;
          title = current!.title;
        }
        // Headings, bullet marks and [stage directions] are taken out, not refused.
        text = cleanSection(text);
        // Only coverage is checked: how it teaches, and at what length, are the writer's.
        const problem = sectionProblem(text, section, language);
        emit({ type: "tool_result", name: "write_section",
          text: problem ? problem : `Section ${section.n}: ${title}\n\n${text}` });
        if (!problem) return { n: section.n, title: title || `Section ${section.n}`, text };
        note = problem;
        if (text) current = { title, text, problem };
        if (text && text.length > (fallback?.text.length ?? 0)) fallback = { title, text, problem };
      }
      if (fallback) {
        emit({ type: "message", role: "status",
          text: `Transcript: section ${section.n} kept after ${TRIES} tries, though not every check passed: ${fallback.problem}` });
        return { n: section.n, title: fallback.title || `Section ${section.n}`, text: fallback.text };
      }
      return null;
    };

    let next = 0;
    const worker = async () => {
      while (next < sections.length && !halted && !stopped()) {
        const section = sections[next++];
        try {
          const wrote = await writeOne(section);
          if (wrote) {
            done.set(section.n, wrote);
            // A topic the book gave no heading is called by its first section's title.
            const topic = topics.find((t) => t.sections[0] === wrote.n);
            if (topic && !topic.title) topic.title = wrote.title;
            // Its chapters are written now, while the rest of the transcript is (stage 2).
            ready.set(wrote.n, wrote);
            writtenQueue.push(wrote);
            const whole = topics.find((t) => t.sections.includes(wrote.n) && t.sections.every((n) => done.has(n)));
            if (whole && topics.length > 1) {
              emit({ type: "message", role: "status", text: `Transcript of Lecture ${whole.index} of ${topics.length} ` +
                `("${whole.title}") written: its scenes are being made${whole.index < topics.length ? " while the next is written" : ""}.` });
            }
          } else {
            failed.push(section.n);
          }
        } catch (error) {
          halted = error;
        } finally {
          live.delete(section.n);
        }
      }
    };
    // The transcript is written in the background: the video's chapters for each section start as soon as it is
    // there (writtenQueue), not when the last section is. Its end, or its failure, is transcriptDone.
    transcriptDone = (async () => {
      try {
        await Promise.all(Array.from({ length: Math.min(PARALLEL, sections.length) }, worker));
      } finally {
        clearInterval(progress);
      }
      if (halted) throw halted;
      if (stopped()) throw new Error("The page closed while the transcript was being written.");
      written.push(...[...done.values()].sort((x, y) => x.n - y.n));
      if (failed.length) {
        failed.sort((x, y) => x - y);
        // A section or two missing still makes a lecture; most of it missing does not.
        if (failed.length > Math.max(1, Math.floor(sections.length / 7))) {
          throw new Error(`The transcript could not be written: ${writer} gave nothing usable for section` +
            `${failed.length > 1 ? "s" : ""} ${failed.join(", ")} of ${sections.length}, after ${TRIES} tries each. ` +
            "Generate again, or pick another model for the transcript.");
        }
        emit({ type: "message", role: "status",
          text: `Transcript: section${failed.length > 1 ? "s" : ""} ${failed.join(", ")} could not be written after ${TRIES} ` +
            "tries each; the lecture goes on without " + (failed.length > 1 ? "them." : "it.") });
      }
      const words = written.reduce((n, w) => n + w.text.split(/\s+/).length, 0);
      emit({ type: "transcript", text: written.map((w) => `SECTION ${w.n}: ${w.title}\n\n${w.text}`).join("\n\n") });
      emit({ type: "message", role: "status",
        text: `Transcript written: ${written.length} sections, ${words} words (about ${Math.round(words / 100)} min).` });
      mark("transcript written");
      for (const topic of topics) {
        if (!topic.title) topic.title = written.find((w) => w.n === topic.sections[0])?.title ?? "";
      }
    })();
    transcriptDone.then(() => writtenQueue.close(), (error) => writtenQueue.fail(error));
    planned = sections;
  }
  // STAGE 2: the video, whose narration is the transcript sentence for sentence.
  // The book's figures as pictures, for the model to rebuild each one in Manim (it is not shown as it is).
  const drawn = await figuresWithin(drawing, figuresReady, drawingStarted, (text) =>
    emit({ type: "message", role: "status", text }));
  mark("figures ready");
  const system = systemBase + (lecture && doc ? figurePrompt(doc, drawn) : "") + systemTail;
  // Figures drawn as SVG are described by their parts; only the others go to the model as pictures.
  const pictures = lecture && doc ? await figurePictures(doc, new Set(Object.keys(drawn ?? {}).filter(
    (id) => drawn?.[id]?.svg || drawn?.[id]?.photo))) : [];
  // The whole transcript joins the system prompt once it is all written (settled, below); each section's chapters
  // are asked for with that section's lines only, as soon as it is written.
  const messages: OutMessage[] = [
    { role: "system", content: system },
    pictures.length ? { role: "user", content: [{ type: "text", text: user }, ...pictures] } : { role: "user", content: user },
  ];
  // The book's figures a section's text marks ("[FIGURE fig3: ...]"), for that section's request alone.
  const picturesFor = (text: string) => {
    const ids = new Set([...text.matchAll(/\[FIGURE (\w+):/g)].map((m) => m[1]));
    const out: ContentPart[] = [];
    for (let i = 0; i + 1 < pictures.length; i += 2) {
      const label = pictures[i];
      if (label.type === "text" && ids.has(/^Figure (\w+):/.exec(label.text)?.[1] ?? "")) out.push(pictures[i], pictures[i + 1]);
    }
    return out;
  };
  // Once the transcript is all written: its lines join the system prompt, for the turns that check and fix the
  // whole lecture.
  let settled = false;
  const settle = async () => {
    if (settled) return;
    await transcriptDone;
    settled = true;
    if (written.length) messages[0] = { role: "system", content: `${system}${fromTranscriptPrompt(written, bookQs)}` };
  };
  if (pictures.length) {
    emit({ type: "message", role: "status",
      text: `The book's ${pictures.length / 2} figure${pictures.length > 2 ? "s are" : " is"} sent to ${model} to rebuild in Manim.` });
  }
  emit({ type: "input", role: "system", text: system });
  emit({ type: "input", role: "user", text: user });
  if (lecture) {
    emit({
      type: "message",
      role: "status",
      text: `About ${minutes} min${request.minutes ? "" : " (estimated from the source)"}: the writer decides how to teach it; ` +
        "everything in the source is covered, in videos of 25-30 min.",
    });
  }
  let scene = request.previousSource ?? "";

  const shrinkHistory = () => {
    if (!scene.includes("from manim import")) return;
    if (!messages.some((message) => message.role === "tool")) return;
    for (const message of messages) {
      if (message.role === "assistant" && message.tool_calls) {
        for (const call of message.tool_calls) {
          if (["write_scene", "edit_scene", "find_map", "write_lecture"].includes(call.function.name)) {
            call.function.arguments = "{}";
          }
        }
        if (message.content && /old_string|"source"/.test(message.content)) message.content = null;
      }
      if (message.role === "tool" && message.content?.includes("def build_region")) {
        message.content = "Map geometry was returned and is already in the scene file.";
      }
    }
    for (let i = messages.length - 1; i >= 0; i--) {
      const said = messages[i].content;
      if (messages[i].role === "user" && typeof said === "string" && said.startsWith("CURRENT SCENE")) messages.splice(i, 1);
    }
    const spoken = voiceSeconds(scene);
    const next =
      spoken >= 1800
        ? "Spoken length is already 30 minutes. Do not call tools. Reply that the scene is ready."
        : `Spoken so far: ${spoken.toFixed(0)} seconds of at most 1800. If this is a long lecture and it is still short of 30 minutes, add the next stretch with one edit_scene: several beats, about two minutes of speech. Each beat is a new slide: FadeOut the previous beat before the next one appears, so text never overlaps. If the idea is already fully told and it was not a long lecture, stop.`;
    messages.push({
      role: "user",
      content: `CURRENT SCENE\n${next}\n\n${scene}`,
    });
  };

  const savedScene = () => {
    if (!/from manim import/.test(scene)) return null;
    return {
      source: scene.endsWith("\n") ? scene : `${scene}\n`,
      sceneClass: SCENE_CLASS,
      model,
      inputTokens,
      outputTokens,
      costUsd,
    };
  };

  // How every lecture script is compiled, whether it came by the tool or in the reply text.
  // The few pictures the script asks to draw (draw ops) become SVGs before each compile (drawings.ts).
  const drawOptions = process.env.OPENROUTER_API_KEY ? {
    key: process.env.OPENROUTER_API_KEY,
    model: svgModel(request.svgModel),
    repo: REPO,
    python: python(),
    onStatus: (text: string) => emit({ type: "message", role: "status", text }),
    onCost: (usd: number) => {
      costUsd = ledger.bill("drawings", usd);
      sendCosts(`picture drawn: $${usd.toFixed(4)}`);
    },
    onDrawn: () => ledger.count("drawings", 1),
    onTime: (start: number, end: number) => ledger.time("drawings", start, end),
    onPicture: (p: { file: string; what: string; parts: string[]; usd: number; kept: boolean }) =>
      showPicture({ kind: "drawing", file: p.file, title: p.what, usd: p.kept ? 0 : p.usd, reused: p.kept, paid: p.usd,
        detail: p.parts.join(", ") }),
  } : undefined;
  const lectureOptions = () => ({
    draw: drawOptions,
    style,
    art: request.art,
    genre: subject?.genre,
    // Every book figure is shown (coverage); how the lecture teaches is the writer's, so no teaching checks.
    figures: doc ? scriptFigures(doc, drawn) : undefined,
    language: language === "auto" ? undefined : language,
  });
  // The whole lecture: the compiler's checks, and, for a remake, every part of the reference video taught.
  // What the compiler mended by itself (a marker on no place, pictures past the web budget, reveals filled in) goes
  // to the log, never back to the model: its repairs are for content.
  const logFixed = (compiled: Compiled) => {
    if (compiled.fixed?.length) {
      emit({ type: "message", role: "status", text: `The compiler mended ${compiled.fixed.length} thing(s) by itself:\n` +
        compiled.fixed.map((f) => f.replace(/^fixed: /, "• ")).join("\n") });
    }
    return compiled;
  };
  const compileWhole = async (script: unknown) => {
    const compiled = logFixed(await compileWholeChecked(script));
    if (compiled.source) Object.assign(kept, { script, source: compiled.source, minutes: compiled.minutes });
    mark(`whole lecture compiled${compiled.source ? "" : " (with faults)"}`);
    return compiled;
  };
  const compileWholeChecked = async (script: unknown) => {
    const compiled = await compileLecture(script, lectureOptions());
    const unsaid = compiled.source ? transcriptProblem(script, written) : null;
    if (unsaid) return { ...compiled, source: null, errors: [unsaid] };
    const unbuilt = compiled.source && doc ? unbuiltFigures(script, scriptFigures(doc, drawn)) : [];
    if (unbuilt.length) {
      return { ...compiled, source: null, errors: [
        `The book's figure${unbuilt.length > 1 ? "s" : ""} ${unbuilt.join(", ")} ${unbuilt.length > 1 ? "are" : "is"} not in the ` +
        "lecture. Show each drawn one where the narration explains it ({\"op\":\"figure\",\"id\":...}, then reveal and " +
        "focus on its parts); build the others in Manim (sketch, preset, graph, diagram), marked with \"from_figure\"; " +
        "show a photograph as it is with {\"op\":\"figure\",\"photo\":true}."] };
    }
    const parts = reference?.parts?.length ?? 0;
    if (!compiled.source || !parts || written.length) return compiled;
    const missing = uncoveredParts(script, parts);
    if (!missing.length) return compiled;
    return {
      ...compiled,
      source: null,
      errors: [`No chapter teaches part${missing.length > 1 ? "s" : ""} ${missing.join(", ")} of the reference video. ` +
        "Every part is taught, in order, and each chapter says which part it teaches with \"from_part\"."],
    };
  };
  // One part of a long lecture is checked on its own: its ops, captions and copying, not the whole lecture's
  // length or counts.
  const partOptions = lectureOptions;
  kept.options = partOptions;
  let draft: Record<string, unknown> | null = null;      // a long lecture's parts so far
  const chapterCount = (script: Record<string, unknown>) => (Array.isArray(script.chapters) ? script.chapters.length : 0);
  let nudges = 0;
  // Chapters a fix-up call sends at most: a long add_chapters call ran into the reply's length limit.
  const FIX_CHAPTERS = 3;
  // done: true refused this many times, with every chapter compiling: the lecture is built as it is.
  const WHOLE_TRIES = 4;
  let wholeRefused = 0;
  // The scripts sent in earlier turns are saved (or were refused, with the reasons): only the last stays in the
  // conversation in full, so each turn does not resend the whole lecture so far (2.5 million tokens in a long one).
  const slimHistory = () => {
    const last = messages.length - 1 - [...messages].reverse().findIndex((m) => m.role === "assistant");
    messages.forEach((message, i) => {
      if (i === last || message.role !== "assistant" || !message.tool_calls) return;
      for (const call of message.tool_calls) {
        if (!["write_lecture", "add_chapters"].includes(call.function.name) || call.function.arguments.length < 400) continue;
        let args: { chapters?: unknown[]; script?: { chapters?: unknown[] }; replace_from?: unknown; replace_to?: unknown; done?: unknown } = {};
        try {
          args = JSON.parse(call.function.arguments);
        } catch {}
        const count = (args.chapters ?? args.script?.chapters ?? []).length;
        call.function.arguments = JSON.stringify({
          sent_earlier: `${count} chapter(s); see the result that follows`,
          ...(args.replace_from ? { replace_from: args.replace_from } : {}),
          ...(args.replace_to ? { replace_to: args.replace_to } : {}),
          ...(args.done ? { done: true } : {}),
        });
      }
    });
  };
  let quietTries = 0;           // turns in a row that went silent or stalled
  const QUIET_TRIES = 2;
  let requireTool = false;     // after a reminder, the next reply must be a tool call, not more prose
  // A part of a long lecture is whole chapters: a first part of one chapter with one beat became a 20-second video.
  const partBeats = minutes >= 5 ? 6 : 3;
  const thinChapters = (chapters: unknown) =>
    (Array.isArray(chapters) ? chapters : []).filter((c) => {
      const beats = (c as { beats?: unknown[] })?.beats;
      return !Array.isArray(beats) || beats.length < partBeats;
    }).length;
  const size = (chars: number) => (chars >= 1024 ? `about ${Math.round(chars / 1024)} KB` : `${chars} characters`);

  /** A section's chapters as a script of their own, checked as a part is: null when they pass, else what is wrong. */
  /**
   * What a section's chapters add when it opens or closes one micro-lecture of a series (topics.ts): the
   * lecture's opening on the board, and its own recap and self-check questions at its end. Without a series, the
   * last section has the lecture's recap.
   */
  const seriesDuties = (n: number, lastOfAll: boolean): string[] => {
    const topic = topicOf(topics, n);
    if (!topic) return [lastOfAll ? "This is the last section: end the script with the recap." : "No recap: the last section has it."];
    const out: string[] = [];
    if (topic.sections[0] === n) {
      out.push(`This section OPENS ${topicLabel(topic)}, a video of its own. Its first chapter is that lecture's ` +
        `opening (title: "Lecture ${topic.index}: ${topic.title || "..."}"): as the transcript says them, put on the board ` +
        "what the lecture covers and the things the student will be able to do (a steps diagram of them revealed " +
        "one by one, or one fact each), and a picture of why the topic matters. Then its teaching, as always.");
    }
    if (topic.sections[topic.sections.length - 1] === n) {
      out.push(`This section CLOSES ${topicLabel(topic)}. Its last chapter is that lecture's close: its key ` +
        "points on the board as they are said, each self-check question on the stage with a question op " +
        "(then the answer op when it is answered), and the next lecture named. End the script with \"recap\": " +
        "[[head, body], ...], the key points of THIS lecture only.");
    } else {
      out.push("No recap: the last section of this lecture has it.");
    }
    return out;
  };

  /**
   * A section's chapters, made whole and checked as a part is. Their beats name the transcript's lines (lines.ts):
   * the words are filled in here, a sentence no beat names is said on a beat of its own, and a chapter too thin to
   * stand is merged into its neighbour, instead of the section being refused and written again for it. With
   * `dropFailing` (a section already refused once for its ops), the ops of the beats the compiler names are left
   * out -- those beats are said over the picture before them -- and the rest kept, when that compiles.
   */
  const checkSection = async (script: Record<string, unknown>, n: number, dropFailing = false) => {
    const chapters = (Array.isArray(script.chapters) ? script.chapters : [])
      .filter((c) => c && typeof c === "object")
      .map((c) => ({ ...(c as Record<string, unknown>), section: n }));
    if (!chapters.length) return { script, errors: ["The script has no chapters."], compiles: false, dropped: 0 };
    const own: Record<string, unknown> = { ...script, title: script.title || `Section ${n}`, chapters };
    const section = ready.get(n) ?? written.find((w) => w.n === n);
    const filled = section ? fillLines(own, [section], { complete: [n], minBeats: partBeats }) : { problems: [], added: 0, merged: 0 };
    let compiled = await compileLecture(own, partOptions());
    let dropped = 0;
    if (!compiled.source && dropFailing) {
      dropped = dropOps(own, compiled.errors);
      if (dropped) compiled = await compileLecture(own, partOptions());
    }
    const errors = [
      ...filled.problems,
      ...[section ? transcriptProblem(own, [section], [n]) : null].filter((e): e is string => !!e),
      ...(compiled.source ? [] : compiled.errors),
    ];
    if (!errors.length && (filled.added || filled.merged || dropped)) {
      emit({ type: "message", role: "status", text: `Video: section ${n}: ` + [
        filled.added ? `${filled.added} transcript line${filled.added > 1 ? "s" : ""} no beat named, said on beats of their own` : "",
        filled.merged ? `${filled.merged} thin chapter${filled.merged > 1 ? "s" : ""} merged into a neighbouring one` : "",
        dropped ? `the ops of ${dropped} beat${dropped > 1 ? "s" : ""} that would not compile left out` : "",
      ].filter(Boolean).join("; ") + "." });
    }
    // Its lines are final unless it is sent back: speak them now, while the other sections are written.
    if (!errors.length && compiled.source && !usingFixture()) speakAhead(compiled.source);
    return { script: own, errors, compiles: !!compiled.source, dropped };
  };

  /**
   * The chapters of the transcript sections `source` hands over, written at the same time (PANIM_CHAPTERS_PARALLEL
   * requests at once), each as soon as its section is written, and asked again when it goes silent or stalls.
   * `total` is how many sections are coming. `notes` are what was wrong with a section's last chapters. `missing`
   * are the sections that gave nothing usable. `onSection` hears of each section's chapters as they are saved.
   */
  const chaptersInParallel = async (source: Queue<WrittenSection>, total: number, notes = new Map<number, string>(),
    onSection?: (done: Map<number, Record<string, unknown>>, missing: number[]) => Promise<void> | void) => {
    const PARALLEL = Math.max(1, Math.min(8, Number(process.env.PANIM_CHAPTERS_PARALLEL) ||
      Number(process.env.PANIM_TRANSCRIPT_PARALLEL) || 6));
    const TRIES = 4;          // refused or failed replies before a section is given up
    const TURNS = 8;          // replies in all, the picture searches among them
    const done = new Map<number, Record<string, unknown>>();
    const missing: number[] = [];
    const live = new Map<number, { started: number; chars: number; attempt: number; thinking: boolean }>();
    const sectionTools: ToolSpec[] = [LECTURE_TOOL, ILLUSTRATION_TOOL, DRAWING_TOOL, IMAGE_TOOL];
    emit({ type: "message", role: "status", text: notes.size
      ? `Video: writing again the chapters of section${notes.size > 1 ? "s" : ""} ${[...notes.keys()].join(", ")}, ` +
        "with what the whole lecture's check found."
      : `Video: writing the chapters of the ${total} sections, ${Math.min(PARALLEL, total)} at a time, each as soon as ` +
        "its transcript is written." });
    const progress = setInterval(() => {
      if (!live.size) return;
      const now = Date.now();
      const parts = [...live.entries()].sort((x, y) => x[0] - y[0]).map(([n, p]) =>
        `${n} (${clock(now - p.started)}, ${p.chars ? size(p.chars) : p.thinking ? "thinking" : "waiting"}` +
        `${p.attempt > 1 ? `, try ${p.attempt}` : ""})`);
      emit({ type: "message", role: "status",
        text: `Video: ${done.size} of ${total} sections' chapters written; writing ${parts.join(", ")}` });
    }, 10_000);

    const one = async (section: WrittenSection, note?: string): Promise<Record<string, unknown> | null> => {
      const first = section.n === planned[0].n;
      const last = section.n === planned[planned.length - 1].n;
      const plannedSection = planned.find((p) => p.n === section.n);
      const ask = [
        `Write the video's chapters for SECTION ${section.n} of ${planned.length} ("${section.title}") ONLY. The other ` +
          "sections are being written at the same time by others: do not write them.",
        "Its narration is that section's transcript, above: every numbered line of it, in order, one or two lines a " +
          "beat, named by number ({\"lines\": [n], \"do\": [...]}). Split it into chapters where its topics change, " +
          `each chapter with "section": ${section.n}, a title and a one-line "narration" for its title card.`,
        "Show the book's figures it speaks of (each is shown somewhere in the lecture); the rest of the pictures are " +
          "yours to choose, for the learning.",
        first ? "This is the first section: the script also has the lecture's title, sub and intro."
          : "Give the script a title (only the first section's is used) and no intro.",
        ...seriesDuties(section.n, last),
        "Call write_lecture once with this script ({title, sub, intro, chapters, recap}); use the find tools first if " +
          "you need pictures. Write it straight away.",
        ...(note ? ["", "You wrote this section's chapters before, and the check of the whole lecture refused them:", note,
          "Write all of this section's chapters again, with these fixed."] : []),
      ].join("\n");
      // The same system prompt for every section (cached by the provider), then only this section: its numbered
      // lines, its own book questions and the book's figures its text marks, not the whole lecture again.
      const own = `${sectionForVideo(section, plannedSection?.questions ?? [])}\n\n${ask}`;
      const figures = picturesFor(plannedSection?.source ?? "");
      const talk: OutMessage[] = [
        cachedSystem(system, model),
        figures.length ? { role: "user", content: [{ type: "text", text: own }, ...figures] } : { role: "user", content: own },
      ];
      let refused = 0;
      // Refused once for ops that would not compile: the next try's failing ops are left out instead.
      let opsRefused = false;
      // The longest try that compiles, kept when every try is refused, so one stubborn section does not lose the
      // lecture: the whole lecture's check names what it lacks, and that is fixed afterwards.
      let fallback: Record<string, unknown> | null = null;
      for (let turn = 0; turn < TURNS && refused < TRIES; turn++) {
        if (stopped()) return null;
        const state = { started: Date.now(), chars: 0, attempt: refused + 1, thinking: false };
        live.set(section.n, state);
        const abort = new AbortController();
        let why: "silent" | "stalled" | null = null;
        let lastDelta = 0;
        const watch = setInterval(() => {
          const now = Date.now();
          if (!lastDelta && now - state.started > FIRST_REPLY_MINUTES * 60_000) why = "silent";
          else if (lastDelta && now - lastDelta > STALL_MS) why = "stalled";
          if (why) abort.abort();
        }, 5000);
        let result;
        try {
          result = await completionWithRetry(key, model, talk, emit, (kind, text) => {
            lastDelta = Date.now();
            if (kind === "thinking") state.thinking = true;
            else state.chars += text.length;
          }, sectionTools, abort.signal, "required");
        } catch (error) {
          if (stopped()) return null;
          refused += 1;
          const note = why === "silent" ? `sent nothing for ${FIRST_REPLY_MINUTES} minutes`
            : why === "stalled" ? `stopped streaming partway (nothing for ${Math.round(STALL_MS / 1000)} s)`
              : `failed (${error instanceof Error ? error.message.slice(0, 160) : String(error)})`;
          emit({ type: "message", role: "status",
            text: `Video: section ${section.n}, try ${refused}: the reply ${note}.${refused < TRIES ? " Asking again." : ""}` });
          continue;
        } finally {
          clearInterval(watch);
        }
        const addedIn = result.usage?.prompt_tokens ?? 0;
        const addedOut = result.usage?.completion_tokens ?? 0;
        const addedCost = Number(result.usage?.cost ?? 0);
        inputTokens += addedIn;
        outputTokens += addedOut;
        costUsd = ledger.bill("script", addedCost, { inputTokens: addedIn, outputTokens: addedOut, span: result.span });
        sendCosts(`video section ${section.n}: ${addedIn} in, ${addedOut} out, $${addedCost.toFixed(4)}`);
        const calls = result.message.tool_calls ?? [];
        if (!calls.length) {
          // A script put in the reply text instead of the tool call is taken as if it had been sent with the tool.
          const typed = scriptFromText(result.message.content ?? "");
          if (typed) {
            const checked = await checkSection(typed, section.n, opsRefused);
            if (!checked.errors.length) return checked.script;
            if (checked.compiles) fallback = checked.script;
          }
          refused += 1;
          talk.push({ role: "assistant", content: result.message.content ?? "" });
          talk.push({ role: "user", content: "Call the write_lecture tool with the script of this section's chapters." });
          continue;
        }
        talk.push({ role: "assistant", content: result.message.content ?? null, tool_calls: calls });
        let saved: Record<string, unknown> | null = null;
        for (const call of calls) {
          let args: { script?: unknown; queries?: unknown } = {};
          try {
            args = JSON.parse(call.function.arguments || "{}");
          } catch {}
          let output: string;
          if (call.function.name === "write_lecture") {
            if (!args.script || typeof args.script !== "object") {
              refused += 1;
              output = "write_lecture needs the script: {title, chapters: [...]}.";
            } else {
              const checked = await checkSection(args.script as Record<string, unknown>, section.n, opsRefused);
              if (!checked.errors.length) {
                saved = checked.script;
                output = `Saved section ${section.n}'s ${chapterCount(checked.script)} chapter(s). Stop calling tools.`;
              } else {
                refused += 1;
                if (!checked.compiles) opsRefused = true;
                if (checked.compiles && JSON.stringify(checked.script).length > JSON.stringify(fallback ?? {}).length) {
                  fallback = checked.script;
                }
                output = [`Section ${section.n}'s chapters were refused. Fix these and call write_lecture again:`,
                  ...checked.errors].join("\n");
              }
            }
          } else if (call.function.name === "find_image") {
            output = await findImage(args.queries);
          } else if (call.function.name === "find_drawing") {
            output = await findDrawings(args.queries);
          } else if (call.function.name === "find_illustration") {
            const looked = Date.now();
            output = await findIllustration(args.queries, subject?.genre, billImages);
            ledger.time("images", looked, Date.now());
          } else {
            output = "Only write_lecture and the find tools are available here.";
          }
          emit({ type: "tool_result", name: call.function.name, text: `Section ${section.n}: ${output}` });
          talk.push({ role: "tool", tool_call_id: call.id, content: output });
        }
        if (saved) return saved;
      }
      if (fallback) {
        emit({ type: "message", role: "status",
          text: `Video: section ${section.n}'s chapters kept after ${refused} tries, though not every check passed.` });
      }
      return fallback;
    };

    let halted: unknown = null;
    const worker = async () => {
      while (!halted && !stopped()) {
        let section: WrittenSection | null = null;
        try {
          section = await source.next();
          if (!section) break;
          const script = await one(section, notes.get(section.n));
          if (script) done.set(section.n, script);
          else missing.push(section.n);
          await onSection?.(done, missing);
        } catch (error) {
          halted = error;
        } finally {
          if (section) live.delete(section.n);
        }
      }
    };
    try {
      await Promise.all(Array.from({ length: Math.max(1, Math.min(PARALLEL, total)) }, worker));
    } finally {
      clearInterval(progress);
    }
    if (halted) throw halted;
    if (stopped()) throw new Error("The page closed while the video was being written.");
    return { done, missing };
  };

  /** The sections' chapters as one lecture, in order: the first section's title and opening, the last's recap. */
  const assemble = (bySection: Map<number, Record<string, unknown>>) => {
    const order = planned.length ? planned.map((s) => s.n) : written.map((s) => s.n);
    const scripts = order.filter((n) => bySection.has(n)).map((n) => bySection.get(n)!);
    const head = bySection.get(order[0]) ?? scripts[0];
    const recap = [...scripts].reverse().find((s) => s.recap)?.recap;
    const script: Record<string, unknown> = {
      ...head,
      chapters: scripts.flatMap((s) => (Array.isArray(s.chapters) ? s.chapters : [])),
      ...(recap ? { recap } : {}),
    };
    if (!recap) delete script.recap;
    if (topics.length > 1) {
      // Each micro-lecture's recap, from its last section, for the cut into videos (parts.ts splitByTopics).
      script.topics = topics.map((t) => ({
        index: t.index, title: t.title, sections: t.sections,
        recap: bySection.get(t.sections[t.sections.length - 1])?.recap ?? null,
      }));
    }
    return script;
  };

  /**
   * The whole lecture's errors that belong to one section ("Section 9: ...", or "chapter 37 ..." of a chapter
   * of section 9, renumbered within the section), and the rest.
   */
  const errorsBySection = (errors: string[], script: Record<string, unknown>) => {
    const chapters = (Array.isArray(script.chapters) ? script.chapters : []) as { section?: unknown }[];
    const firstOf = new Map<number, number>();
    chapters.forEach((c, i) => {
      const n = Number(c?.section);
      if (!firstOf.has(n)) firstOf.set(n, i);
    });
    const bySection = new Map<number, string[]>();
    const rest: string[] = [];
    for (const error of errors) {
      const named = /^Section (\d+):/.exec(error);
      const chapter = /^chapter (\d+)\b/.exec(error);
      const n = named ? Number(named[1]) : chapter ? Number(chapters[Number(chapter[1]) - 1]?.section) : NaN;
      if (!Number.isFinite(n) || !written.some((s) => s.n === n)) {
        rest.push(error);
        continue;
      }
      const local = chapter ? error.replace(/^chapter \d+/, `your chapter ${Number(chapter[1]) - (firstOf.get(n) ?? 0)}`) : error;
      bySection.set(n, [...(bySection.get(n) ?? []), local]);
    }
    return { bySection, rest };
  };

  // A long lecture with a written transcript: each section's chapters are written at the same time, each by its
  // own request, as the transcript was. One after another (write_lecture, then add_chapters turn by turn) a two-hour
  // lecture took a slow model an hour of turns, each a longer conversation than the last, and looked stuck.
  /**
   * A series of micro-lectures (topics.ts) is finished one micro-lecture at a time, never as one long lecture: as
   * soon as every section of a topic has its chapters, that topic is put together as a lecture of its own, checked
   * on its own (its sections' transcript said, its ops compiling, its book questions asked, its figures built), its
   * faulty sections written again in parallel, and it is sent to the page to build ("part") while the other topics
   * are still being written. Checking and fixing the whole two-hour lecture at once, then cutting it, was the slow
   * part: every fix-up turn carried the whole lecture.
   */
  const finished = new Map<number, { index: number; of: number; title: string; minutes: number; source: string }>();
  const finishing: Promise<void>[] = [];
  const started = new Set<number>();
  // The series' title and opening come from the first section's chapters.
  let headReady: (head: Record<string, unknown>) => void = () => {};
  const head = new Promise<Record<string, unknown>>((resolve) => (headReady = resolve));
  const sectionOf = (n: number) => planned.find((p) => p.n === n);

  /** One micro-lecture's errors, each with the section it belongs to (or 0: the lecture's own). */
  const topicErrors = async (part: Record<string, unknown>, sections: number[]) => {
    const chapters = (Array.isArray(part.chapters) ? part.chapters : []) as { section?: unknown; beats?: { do?: Record<string, unknown>[] }[] }[];
    const compiled = logFixed(await compileLecture(part, partOptions()));
    const errors = new Map<number, string[]>();
    const add = (n: number, error: string) => errors.set(n, [...(errors.get(n) ?? []), error]);
    for (const error of compiled.source ? [] : compiled.errors) {
      const chapter = /^chapter (\d+)\b/.exec(error);
      const n = chapter ? Number(chapters[Number(chapter[1]) - 1]?.section) : NaN;
      if (Number.isFinite(n) && sections.includes(n)) {
        const first = chapters.findIndex((c) => Number(c?.section) === n);
        add(n, error.replace(/^chapter \d+/, `your chapter ${Number(chapter![1]) - first}`));
      } else {
        add(0, error);
      }
    }
    for (const n of sections) {
      const ws = ready.get(n);
      const gap = ws && chapters.some((c) => Number(c?.section) === n) ? transcriptProblem(part, [ws], [n]) : null;
      if (gap) add(n, gap);
      // Each of the book's figures in this section, shown (the transcript already covers its questions).
      if (doc) {
        const marked = new Set([...(sectionOf(n)?.source ?? "").matchAll(/\[FIGURE (\w+):/g)].map((m) => m[1]));
        const figures = Object.fromEntries(Object.entries(scriptFigures(doc, drawn)).filter(([id]) => marked.has(id)));
        const unbuilt = unbuiltFigures(part, figures);
        if (unbuilt.length) {
          add(n, `The book's figure${unbuilt.length > 1 ? "s" : ""} ${unbuilt.join(", ")} ${unbuilt.length > 1 ? "are" : "is"} not ` +
            "shown. Show each drawn one where the narration explains it ({\"op\":\"figure\",\"id\":...}, then reveal " +
            "its parts); build the others in Manim marked with \"from_figure\", or show a photograph as it is with " +
            "{\"op\":\"figure\",\"photo\":true}.");
        }
      }
    }
    return { compiled, errors };
  };

  const finishTopic = async (k: number, bySection: Map<number, Record<string, unknown>>, missing: number[]) => {
    const topic = topics[k];
    const label = `Lecture ${k + 1} of ${topics.length}`;
    const own = new Map(topic.sections.filter((n) => bySection.has(n)).map((n) => [n, bySection.get(n)!]));
    const build = (series: Record<string, unknown>) => {
      const chapters = topic.sections.flatMap((n) => {
        const c = own.get(n)?.chapters;
        return Array.isArray(c) ? c : [];
      });
      return topicPart({ ...series, chapters }, { title: topic.title, recap: own.get(topic.sections[topic.sections.length - 1])?.recap },
        k, topics.length, String(series.title ?? "Lecture"), null);
    };
    const series = await head;
    let part = build(series);
    let checked = await topicErrors(part.script, topic.sections);
    // Its faulty sections, and those that gave nothing, written again at the same time, told what was wrong.
    const notes = new Map<number, string>();
    for (const [n, errors] of checked.errors) if (n) notes.set(n, errors.join("\n"));
    for (const n of topic.sections) if (missing.includes(n) && ready.has(n)) notes.set(n, "Nothing usable came back for this section last time.");
    if (notes.size) {
      emit({ type: "message", role: "status", text: `${label}: section${notes.size > 1 ? "s" : ""} ` +
        `${[...notes.keys()].join(", ")} written again, with what its check found.` });
      const again = await chaptersInParallel(Queue.of([...notes.keys()].map((n) => ready.get(n)!)), notes.size, notes);
      for (const [n, chapters] of again.done) own.set(n, chapters);
      part = build(series);
      checked = await topicErrors(part.script, topic.sections);
    }
    let compiled = checked.compiled;
    if (!compiled.source) {
      // What still will not compile is left out (those beats' ops), rather than holding the lecture back.
      if (dropOps(part.script, compiled.errors)) compiled = await compileLecture(part.script, partOptions());
    }
    if (!compiled.source) {
      emit({ type: "message", role: "status", text: `${label} ("${topic.title}") could not be made: ${compiled.errors.slice(0, 2).join("; ")}` });
      return;
    }
    const left = [...checked.errors.values()].flat();
    const done = { index: k + 1, of: topics.length, title: part.title, minutes: compiled.minutes ?? 0, source: sanitizeScene(compiled.source) };
    finished.set(k, done);
    emit({ type: "part", part: done });
    emit({ type: "message", role: "status", text: `${part.title} is ready (about ${Math.round(done.minutes)} min): ` +
      `building it now${finished.size < topics.length ? ", while the others are written" : ""}.` +
      (left.length ? ` Not every check passed: ${left[0].slice(0, 200)}` : "") });
  };

  /** Each micro-lecture is finished as soon as all its sections are in (or given up). */
  const startTopics = (done: Map<number, Record<string, unknown>>, missing: number[], all = false) => {
    const first = done.get(planned[0]?.n);
    if (first) headReady(first);
    else if (all) headReady(done.values().next().value ?? { title: topics[0]?.title || "Lecture" });
    topics.forEach((topic, k) => {
      if (started.has(k)) return;
      const settledSections = topic.sections.every((n) => done.has(n) || missing.includes(n));
      if (!(settledSections || all) || !topic.sections.some((n) => done.has(n) || (all && ready.has(n)))) return;
      started.add(k);
      finishing.push(finishTopic(k, done, missing).catch((error) => {
        emit({ type: "message", role: "status", text: `Lecture ${k + 1} failed: ${error instanceof Error ? error.message : String(error)}` });
      }));
    });
  };

  if (lecture && topics.length > 1 && !scene) {
    let first;
    try {
      first = await chaptersInParallel(writtenQueue, planned.length, new Map(), (done, missing) => startTopics(done, missing));
      mark("chapters written");
      await settle();
      // Topics with a section the transcript could not write are finished with what they have.
      startTopics(first.done, first.missing, true);
      await Promise.all(finishing);
    } catch (error) {
      abandoned = true;
      throw error;
    }
    const parts = topics.map((_, k) => finished.get(k)).filter((p): p is NonNullable<typeof p> => !!p);
    if (!parts.length) throw new Error("None of the micro-lectures could be made; see the messages above.");
    // Numbered as they stand: a micro-lecture that could not be made is left out of the series.
    const series = parts.map((p, i) => ({ title: p.title.replace(/^Lecture \d+:/, `Lecture ${i + 1}:`), minutes: p.minutes,
      source: parts.length === topics.length ? p.source : p.source.replace(/Lecture \d+ of \d+/, `Lecture ${i + 1} of ${parts.length}`) }));
    emit({ type: "message", role: "status", text: `The series is written: ${series.length} micro-lectures ` +
      `(${series.map((p) => `${p.title}, ${Math.round(p.minutes)} min`).join("; ")}).` });
    return { source: series[0].source, parts: series, sceneClass: SCENE_CLASS, model, inputTokens, outputTokens, costUsd };
  }
  if (lecture && planned.length >= 2 && !scene) {
    let first;
    try {
      first = await chaptersInParallel(writtenQueue, planned.length);
      mark("chapters written");
      await settle();
    } catch (error) {
      abandoned = true;
      throw error;
    }
    const bySection = first.done;
    let missing = first.missing;
    let script = assemble(bySection);
    let compiled = bySection.size ? await compileWhole(script) : null;
    if (compiled && !compiled.source) {
      // What the whole lecture's check finds in a section (its transcript not all said, a chapter that does not
      // compile, no chapters at all) is that section's to fix: those sections are written again, at the same time,
      // told what was wrong. Only what belongs to no section is left to the turns below.
      const { bySection: notes } = errorsBySection(compiled.errors, script);
      // The transcript check runs only once the compiler passes, so each section's is run here as well.
      for (const s of written) {
        const gap = bySection.has(s.n) ? transcriptProblem(script, written, [s.n]) : null;
        if (gap) notes.set(s.n, [...(notes.get(s.n) ?? []), gap]);
      }
      const notesFor = new Map([...notes].map(([n, errs]) => [n, errs.join("\n")]));
      for (const n of missing) notesFor.set(n, "Nothing usable came back for this section last time.");
      if (notesFor.size) {
        const again = await chaptersInParallel(Queue.of(written.filter((s) => notesFor.has(s.n))), notesFor.size, notesFor);
        for (const [n, chapters] of again.done) bySection.set(n, chapters);
        missing = missing.filter((n) => !again.done.has(n));
        script = assemble(bySection);
        compiled = await compileWhole(script);
      }
    }
    if (compiled) {
      missing.sort((x, y) => x - y);
      emit({ type: "message", role: "status", text: `Video: chapters written for ${bySection.size} of ${written.length} sections` +
        (missing.length ? ` (section${missing.length > 1 ? "s" : ""} ${missing.join(", ")} still to write)` : "") + "." });
      if (!tools.includes(ADD_CHAPTERS_TOOL)) tools.splice(1, 0, ADD_CHAPTERS_TOOL);
      emit({ type: "tool_call", name: "write_lecture", args: JSON.stringify({ script }).slice(0, 1600) });
      if (compiled.source) {
        emit({ type: "tool_result", name: "write_lecture", text: [
          `Compiled the lecture: ${chapterCount(script)} chapters, ${compiled.source.split("\n").length} lines of Manim, ` +
            `about ${compiled.minutes ?? "?"} min.`,
          ...compiled.warnings.map((w) => `warning: ${w}`)].join("\n") });
        scene = compiled.source;
        return savedScene()!;
      }
      // The sections are written but the whole still falls short (a question or figure left out, the length, the
      // count of problems): the chapters are kept and the model fixes only what is wrong, with add_chapters.
      const partsOk = (await compileLecture(script, partOptions())).source;
      draft = script;
      const list = (Array.isArray(script.chapters) ? script.chapters : []).map((c, i) => {
        const chapter = c as { title?: unknown; section?: unknown };
        return `  chapter ${i + 1}: section ${chapter.section ?? "?"}, ${String(chapter.title ?? "")}`;
      });
      const problem = [
        partsOk ? `The chapters of every section were written and are saved (${chapterCount(script)} chapters):` :
          "The chapters of the sections were written, but they do not compile together:",
        ...list,
        ...missing.map((n) => `  section ${n}: NO CHAPTERS YET; write them and put them in their place`),
        "",
        "The whole lecture does not pass yet:",
        ...compiled.errors,
        "",
        "Fix only what is wrong, with add_chapters: replace_from n and replace_to m replace chapters n to m with the " +
          "chapters you send (replace_to n - 1 inserts them before chapter n); done: true when it is complete. Send at " +
          `most ${FIX_CHAPTERS} chapters a call: a longer call is cut off by the reply's length limit.`,
      ].join("\n");
      emit({ type: "tool_result", name: "write_lecture", text: problem });
      messages.push({ role: "user", content: problem });
      requireTool = true;
    }
  }
  await settle();
  // Every section said in full, once the whole lecture is in: what no beat names is added on beats of its own.
  const allSections = () => ({ complete: written.map((w) => w.n), minBeats: partBeats });
  for (let turn = 0; turn < (written.length ? 30 + written.length * 5 : 40); turn++) {
    if (stopped()) {
      const done = savedScene();
      if (done) return done;
      throw new Error("The page closed before a scene was written.");
    }
    if (voiceSeconds(scene) >= 1800) {
      const done = savedScene();
      if (done) return done;
    }
    shrinkHistory();
    if (lecture) slimHistory();
    emit({
      type: "message",
      role: "status",
      text: `Turn ${turn + 1}: waiting for ${model}`,
    });
    let sawDelta = false;
    let lastDelta = Date.now();
    let streamed = 0;
    const started = Date.now();
    const abort = new AbortController();
    let gaveUp: "silent" | "stalled" | null = null;
    const waiting = setInterval(() => {
      const quiet = Date.now() - lastDelta;
      const minutes = (Date.now() - started) / 60000;
      if (!sawDelta && minutes >= FIRST_REPLY_MINUTES) gaveUp = "silent";
      else if (sawDelta && quiet > STALL_MS) gaveUp = "stalled";
      if (gaveUp) {
        abort.abort();
        return;
      }
      if (!sawDelta) {
        // A reasoning model thinks before it writes and sends nothing meanwhile; a "pro" one for many minutes.
        const hint = minutes >= 2 ? ` (${Math.floor(minutes)} min; it has sent nothing yet: a reasoning model thinks ` +
          `silently first, and a "pro" model can take many minutes. Asked again at ${FIRST_REPLY_MINUTES} min)` : "";
        emit({
          type: "message",
          role: "status",
          text: `Turn ${turn + 1}: still waiting for ${model}${hint}`,
        });
      } else if (quiet > 12000) {
        emit({
          type: "message",
          role: "status",
          text: `Turn ${turn + 1}: ${model} is writing (${clock(Date.now() - started)}, ${streamed ? size(streamed) : "thinking"}` +
            `; nothing new for ${Math.round(quiet / 1000)} s, asked again at ${Math.round(STALL_MS / 1000)} s)`,
        });
      }
    }, 8000);
    let result: { message: ChatMessage; usage?: Usage; finishReason?: string; span?: [number, number] };
    try {
      result = await completionWithRetry(key, model, messages, emit, (kind, text) => {
        sawDelta = true;
        lastDelta = Date.now();
        if (kind !== "thinking") streamed += text.length;
        emit({ type: "delta", role: kind === "thinking" ? "thinking" : "assistant", text });
      }, tools, abort.signal, requireTool ? "required" : "auto");
      quietTries = 0;
    } catch (error) {
      if (gaveUp && !stopped()) {
        // A turn that went silent or stalled is asked again, not the end of the lecture.
        quietTries += 1;
        const what = gaveUp === "silent" ? `sent nothing for ${FIRST_REPLY_MINUTES} minute${FIRST_REPLY_MINUTES === 1 ? "" : "s"}`
          : `stopped streaming partway (nothing for ${Math.round(STALL_MS / 1000)} s)`;
        if (quietTries <= QUIET_TRIES) {
          emit({ type: "message", role: "status",
            text: `Turn ${turn + 1}: ${model} ${what}. Asking again (try ${quietTries + 1} of ${QUIET_TRIES + 1}).` });
          continue;
        }
        const partial = draft ? await compileLecture(draft, partOptions()) : null;
        if (partial?.source) {
          Object.assign(kept, { script: draft, source: partial.source, minutes: partial.minutes });
          emit({ type: "message", role: "status",
            text: `${model} ${what}, ${QUIET_TRIES + 1} times in a row; building the lecture from the ${chapterCount(draft!)} ` +
              `chapter(s) written (about ${partial.minutes ?? "?"} of ${minutes} min).` });
          return { source: partial.source, sceneClass: SCENE_CLASS, model, inputTokens, outputTokens, costUsd };
        }
        throw new Error(`${model} ${what}, ${QUIET_TRIES + 1} times in a row, so the request was stopped. ` +
          "Reasoning models (a \"pro\" model above all) think silently before writing, and a long lecture is a lot " +
          "to plan. Try a faster model in OPENROUTER_MODEL (a non-pro one), a shorter video length, or raise " +
          "PANIM_MODEL_WAIT_MINUTES.");
      }
      const message = error instanceof Error ? error.message : String(error);
      if (pictures.length && Array.isArray(messages[1].content) && /image|vision|modalit|multimodal/i.test(message)) {
        // A model that reads no images: the figures go as their captions alone, and the turn is asked again.
        messages[1] = { role: "user", content: user };
        emit({ type: "message", role: "status",
          text: `${model} takes no images: it rebuilds the book's figures from their captions alone.` });
        continue;
      }
      if (!/idle timeout|upstream/i.test(message)) throw error;
      const done = savedScene();
      if (done) {
        emit({
          type: "message",
          role: "status",
          text: "The model timed out. Keeping the scene already written.",
        });
        return done;
      }
      emit({
        type: "message",
        role: "status",
        text: "The model timed out while writing the file. Asking for one short beat instead.",
      });
      messages.push({
        role: "user",
        content:
          "That reply timed out before the file was saved. Nothing was written. Call write_scene with only the opening beat.",
      });
      continue;
    } finally {
      clearInterval(waiting);
      requireTool = false;
    }
    const addedIn = result.usage?.prompt_tokens ?? 0;
    const addedOut = result.usage?.completion_tokens ?? 0;
    const addedCost = Number(result.usage?.cost ?? 0);
    inputTokens += addedIn;
    outputTokens += addedOut;
    // The whole-lecture turns after the sections were written: checking and fixing the script (for a plain scene,
    // which has no sections, these turns write it).
    costUsd = ledger.bill(lecture ? "fixes" : "script", addedCost, { inputTokens: addedIn, outputTokens: addedOut,
      span: result.span });
    sendCosts(`turn ${turn + 1}: ${addedIn} in, ${addedOut} out, $${addedCost.toFixed(4)}`);

    const text = result.message.content?.trim() ?? "";
    const calls = result.message.tool_calls ?? [];
    if (calls.length === 0 && lecture && !/from manim import/.test(scene)) {
      // The model wrote the lecture into its reply instead of calling write_lecture (or stopped short). The
      // script is compiled as if it had called the tool; otherwise it is asked, twice at most, to call it.
      const typed = scriptFromText(text);
      if (typed && written.length) fillLines(typed, written, allSections());
      let nudge: string | null = null;
      if (typed) {
        emit({ type: "message", role: "status", text: "The model sent the script as text; compiling it as write_lecture." });
        const compiled = await compileWhole(typed);
        if (compiled.source) {
          emit({ type: "tool_result", name: "write_lecture", text: [
            `Compiled the lecture (${compiled.source.split("\n").length} lines of Manim, about ${compiled.minutes ?? "?"} min).`,
            ...compiled.warnings.map((w) => `warning: ${w}`)].join("\n") });
          return { source: compiled.source, sceneClass: SCENE_CLASS, model, inputTokens, outputTokens, costUsd };
        }
        nudge = ["You put the script in your reply. Call the write_lecture tool with it instead, after fixing these:",
          ...compiled.errors].join("\n");
      } else if (result.finishReason === "length") {
        nudge = "Your reply was cut off before it finished. Call the write_lecture tool with the whole script (the tool call " +
          "carries it; do not write it in the reply). Keep each chapter to 8-12 beats.";
      } else if (draft) {
        nudge = `The lecture is not finished: ${chapterCount(draft)} chapter(s) are saved. Continue with add_chapters ` +
          "(the next chapters), and done: true with the last part and the recap.";
      } else {
        nudge = "Call the write_lecture tool with the whole beat script. Do not put the script in your reply text.";
      }
      // A long lecture with only its first parts saved is asked again, more times, before anything is built.
      if (nudges < (draft ? 6 : 2)) {
        nudges += 1;
        emit({ type: "message", role: "status", text: draft ? "Asking the model to continue with add_chapters." :
          "Asking the model to call write_lecture." });
        messages.push({ role: "assistant", content: result.message.content ?? "" });
        messages.push({ role: "user", content: nudge });
        requireTool = true;
        continue;
      }
    }
    if (calls.length === 0 && draft && !/from manim import/.test(scene)) {
      // The model stopped before finishing a long lecture: the parts it wrote make a shorter video, not an error.
      const partial = await compileLecture(draft, partOptions());
      if (partial.source) Object.assign(kept, { script: draft, source: partial.source, minutes: partial.minutes });
      if (partial.source && (partial.minutes ?? 0) < minutes * 0.4) {
        // A fragment is not the lecture that was asked for: say so, rather than render 20 seconds of it.
        throw new Error(`${model} stopped after ${chapterCount(draft)} chapter(s), about ${partial.minutes ?? "?"} of ` +
          `${minutes} minutes, and did not continue after ${nudges} reminders. Generate again, or pick another model ` +
          "(OPENROUTER_MODEL): one that keeps calling tools finishes long lectures.");
      }
      if (partial.source) {
        emit({
          type: "message",
          role: "status",
          text: `The model stopped after ${chapterCount(draft)} chapter(s); building the lecture from them (about ` +
            `${partial.minutes ?? "?"} of ${minutes} min).`,
        });
        return { source: partial.source, sceneClass: SCENE_CLASS, model, inputTokens, outputTokens, costUsd };
      }
    }
    if (calls.length === 0) {
      const source = /from manim import/.test(scene) ? (scene.endsWith("\n") ? scene : `${scene}\n`) : extractScene(text);
      return { source, sceneClass: SCENE_CLASS, model, inputTokens, outputTokens, costUsd };
    }

    messages.push({
      role: "assistant",
      content: result.message.content ?? null,
      tool_calls: calls,
    });
    for (const call of calls) {
      let args: {
        place?: string;
        subject?: string;
        region?: string;
        feature?: string;
        source?: string;
        old_string?: string;
        new_string?: string;
        script?: unknown;
        more?: boolean;
        chapters?: unknown[];
        recap?: unknown;
        replace_from?: number;
        replace_to?: number;
        done?: boolean;
      } = {};
      let cut = false;
      try {
        args = JSON.parse(call.function.arguments || "{}");
      } catch {
        args = {};
        cut = true;
      }
      emit({ type: "tool_call", name: call.function.name, args: call.function.arguments });
      // Beats that name the transcript's lines get their words here, before anything checks them (lines.ts).
      let lineProblems: string[] = [];
      if (!cut && written.length && ["write_lecture", "add_chapters"].includes(call.function.name)) {
        const target = args.script ?? (Array.isArray(args.chapters) ? { chapters: args.chapters } : null);
        const whole = call.function.name === "write_lecture" && !args.more;
        if (target) lineProblems = fillLines(target, written, whole ? allSections() : {}).problems;
      }
      let output: string;
      if (lineProblems.length) {
        output = ["Some beats name lines their section does not have. Fix these and send the call again:",
          ...lineProblems.slice(0, 12)].join("\n");
      } else if (cut && ["write_lecture", "add_chapters"].includes(call.function.name)) {
        // A call cut off by the reply's length limit is not complete JSON. Read as empty, it was "saved" with
        // nothing in it, and the model went on as if its chapters were in.
        output = `Your ${call.function.name} call was cut off before it ended (the reply's length limit), so nothing ` +
          `was saved. Send it again in smaller pieces: at most ${FIX_CHAPTERS} chapters a call.`;
      } else if (call.function.name === "write_lecture" && args.more && args.script && typeof args.script === "object") {
        const first = args.script as Record<string, unknown>;
        const thin = thinChapters(first.chapters);
        const unsaid = written.length ? transcriptProblem(first, written, sectionsOf(first)) : null;
        const compiled = unsaid
          ? { source: null, errors: [unsaid], minutes: 0, warnings: [] }
          : thin || chapterCount(first) === 0
          ? { source: null, errors: [`Each chapter needs at least ${partBeats} beats (8-12 is right); ${thin || "no"} chapter(s) ` +
              `here have fewer. Send part 1 again with whole chapters, each teaching its topic fully.`], minutes: 0, warnings: [] }
          : await compileLecture(first, partOptions());
        if (compiled.source) {
          draft = first;
          output = `Saved part 1: ${chapterCount(first)} chapter(s), about ${compiled.minutes ?? "?"} of ${minutes} min. ` +
            "Now call add_chapters with the next chapters (done: false), and done: true with the last part and the recap.";
        } else {
          output = ["This part did not compile. Fix these and send it again with write_lecture (more: true):", ...compiled.errors].join("\n");
        }
      } else if (call.function.name === "add_chapters") {
        if (!draft) {
          output = "Start with write_lecture: the title, intro and first chapters, with more: true.";
        } else {
          const had = Array.isArray(draft.chapters) ? (draft.chapters as unknown[]) : [];
          const from = args.replace_from && args.replace_from >= 1 ? Math.min(args.replace_from - 1, had.length) : had.length;
          // replace_to n keeps the chapters after n (replace_to = replace_from - 1 inserts); without it, every
          // chapter from replace_from on is replaced.
          const to = args.replace_from && Number.isInteger(args.replace_to)
            ? Math.max(from, Math.min(Number(args.replace_to), had.length)) : had.length;
          const next: Record<string, unknown> = {
            ...draft, chapters: [...had.slice(0, from), ...(args.chapters ?? []), ...had.slice(to)],
            ...(args.recap ? { recap: args.recap } : {}),
          };
          if (args.done && written.length) fillLines(next, written, allSections());
          const thin = thinChapters(args.chapters);
          const part = { chapters: args.chapters ?? [] };
          // The sections these chapters speak are checked in the lecture they make, so a few chapters can replace
          // part of a section; checked alone, every section touched had to be sent whole again.
          const unsaid = written.length && !args.done ? transcriptProblem(next, written, sectionsOf(part)) : null;
          const compiled = unsaid
            ? { source: null, errors: [unsaid], minutes: 0, warnings: [] }
            : thin
            ? { source: null, errors: [`Each chapter needs at least ${partBeats} beats (8-12 is right); ${thin} of these have ` +
                "fewer. Send them again as whole chapters."], minutes: 0, warnings: [] }
            : args.done ? await compileWhole(next) : logFixed(await compileLecture(next, partOptions()));
          if (compiled.source && args.done) {
            draft = next;
            scene = compiled.source;
            output = [
              `Compiled the whole lecture: ${chapterCount(next)} chapters, ${compiled.source.split("\n").length} lines of Manim, about ${compiled.minutes ?? "?"} min.`,
              ...compiled.warnings.map((w) => `warning: ${w}`),
              "Stop calling tools and reply in one sentence.",
            ].join("\n");
          } else if (compiled.source) {
            draft = next;
            output = `Saved: ${chapterCount(next)} chapter(s), about ${compiled.minutes ?? "?"} of ${minutes} min. ` +
              "Continue with add_chapters; done: true with the last part and the recap.";
          } else if (args.done) {
            // The parts are fine but the whole falls short (length, questions, problems): keep them, ask for more.
            const partsOk = (await compileLecture(next, partOptions())).source;
            if (partsOk && !thin) draft = next;
            if (partsOk && !thin) wholeRefused += 1;
            output = [
              partsOk ? "Saved these chapters, but the whole lecture is not finished yet:" : "This part did not compile:",
              ...compiled.errors,
              "Add chapters (or rewrite some with replace_from) with add_chapters, and done: true again when it is complete.",
            ].join("\n");
          } else {
            output = ["This part did not compile and was not added. Fix these and send it again:", ...compiled.errors].join("\n");
          }
        }
      } else if (call.function.name === "write_lecture") {
        const compiled = await compileWhole(args.script ?? {});
        if (compiled.source) {
          scene = compiled.source;
          output = [
            `Compiled the lecture (${compiled.source.split("\n").length} lines of Manim, about ${compiled.minutes ?? "?"} min).`,
            ...compiled.warnings.map((w) => `warning: ${w}`),
            "Stop calling tools and reply in one sentence.",
          ].join("\n");
        } else {
          output = ["The script did not compile. Fix these and call write_lecture again:", ...compiled.errors].join("\n");
        }
      } else if (call.function.name === "find_image") {
        output = await findImage((args as { queries?: unknown }).queries);
      } else if (call.function.name === "find_drawing") {
        output = await findDrawings((args as { queries?: unknown }).queries);
      } else if (call.function.name === "find_illustration") {
        const looked = Date.now();
        output = await findIllustration((args as { queries?: unknown }).queries, subject?.genre, billImages);
        ledger.time("images", looked, Date.now());
      } else {
        const edited = applySceneTool(scene, call.function.name, args);
        output = edited ? edited.message : await runTool(call.function.name, args);
        if (edited) scene = edited.source;
      }
      emit({ type: "tool_result", name: call.function.name, text: output });
      messages.push({ role: "tool", tool_call_id: call.id, content: output });
    }
    if (draft && wholeRefused >= WHOLE_TRIES && !/from manim import/.test(scene)) {
      // A complete lecture whose whole-lecture checks still fail after several rounds of fixing: its chapters all
      // compile, so it is built (the checks named in the log), rather than turning for another hour.
      const built = await compileLecture(draft, partOptions());
      if (built.source) {
        Object.assign(kept, { script: draft, source: built.source, minutes: built.minutes });
        emit({ type: "message", role: "status", text: `The whole lecture was refused ${wholeRefused} times; building its ` +
          `${chapterCount(draft)} chapters (about ${built.minutes ?? "?"} min), though not every check passed.` });
        return { source: built.source, sceneClass: SCENE_CLASS, model, inputTokens, outputTokens, costUsd };
      }
    }
  }
  const done = savedScene();
  if (done) return done;
  if (draft) {
    // Out of turns with a long lecture's chapters saved: they are the video, not an error.
    const partial = await compileLecture(draft, partOptions());
    if (partial.source) {
      Object.assign(kept, { script: draft, source: partial.source, minutes: partial.minutes });
      emit({ type: "message", role: "status", text: `Out of turns; building the lecture from the ${chapterCount(draft)} ` +
        `chapter(s) written (about ${partial.minutes ?? "?"} of ${minutes} min), though not every check passed.` });
      return { source: partial.source, sceneClass: SCENE_CLASS, model, inputTokens, outputTokens, costUsd };
    }
  }
  throw new Error("The agent kept calling tools without writing a scene.");
}

/**
 * The offline provider. It does not pretend to understand the content -- it
 * builds a scene *from* it, so the output is real Manim that exports and plays,
 * and an instruction visibly changes the result. Enough to exercise every step
 * after generation without a key.
 */
async function viaFixture(
  request: GenerateRequest,
  emit: (event: AgentEvent) => void,
  kept: Kept = {},
): Promise<Generated> {
  const template = templateById(request.templateId);
  if (isLecture(template)) return lectureFixture(request, template, emit, kept);
  const brief = [request.content, request.instruction].filter(Boolean).join("\n");
  const place = (request.content.trim().split("\n")[0] || brief).slice(0, 80);
  emit({ type: "input", role: "user", text: userPrompt(request) });
  emit({ type: "message", role: "assistant", text: "Offline agent. No model tokens." });

  if (/\b(map|coast|country|continent|ocean|sea|geography|cartopy|border|state|province)\b/i.test(brief)) {
    emit({ type: "tool_call", name: "find_map", args: JSON.stringify({ place }) });
    const output = await findMap(place);
    emit({ type: "tool_result", name: "find_map", text: output });
    const scene = output.includes("class GeneratedScene") ? output.slice(output.indexOf("from manim import *")) : cartopyFallback(request, template);
    emit({ type: "message", role: "assistant", text: "Writing the map scene." });
    return { source: scene.endsWith("\n") ? scene : scene + "\n", sceneClass: SCENE_CLASS, model: "fixture agent", inputTokens: 0, outputTokens: 0, costUsd: 0 };
  }
  if (/\b(molecule|molecular|atom|bond|h2o|water|methane|ch4|co2|chemistry|chemical)\b/i.test(brief)) {
    emit({ type: "tool_call", name: "molecule_guide", args: JSON.stringify({ subject: place }) });
    const output = moleculeGuide(brief);
    emit({ type: "tool_result", name: "molecule_guide", text: output });
    return { source: `from manim import *\n\n${output}\n`, sceneClass: SCENE_CLASS, model: "fixture agent", inputTokens: 0, outputTokens: 0, costUsd: 0 };
  }

  emit({ type: "message", role: "assistant", text: `Writing a ${template.name.toLowerCase()} scene.` });
  return { source: sceneFixture(request, template), sceneClass: SCENE_CLASS, model: "fixture agent", inputTokens: 0, outputTokens: 0, costUsd: 0 };
}
/** The offline lecture: a beat script built from the content, compiled. */
async function lectureFixture(
  request: GenerateRequest,
  template: Template,
  emit: (event: AgentEvent) => void,
  kept: Kept = {},
): Promise<Generated> {
  emit({ type: "input", role: "user", text: lectureUserPrompt(request) });
  emit({ type: "message", role: "assistant", text: "Offline agent. No model tokens." });
  const subject = await subjectOf(request, emit);
  const style = effectiveStyle(template, subject);
  // Subjects that rarely need a map (chemistry, physics, maths, biology) do without one.
  const region = subject.map === "never" || subject.map === "rarely" ? null : await resolveRegion(request.content);
  emit({ type: "message", role: "status", text: region ? `Map: ${region.state ?? region.country}` : "No map for this lecture." });
  const script = fixtureScript(request.content, { ...template, style }, region, request.instruction);
  const doc = await documentOf(request);
  const args = JSON.stringify({ script });
  emit({ type: "tool_call", name: "write_lecture", args: args.length > 1600 ? `${args.slice(0, 1600)}…` : args });
  const options = { style, art: request.art, genre: subject.genre, figures: doc ? scriptFigures(doc) : undefined };
  const compiled = await compileLecture(script, options);
  if (!compiled.source) throw new Error(`The beat script did not compile:\n${compiled.errors.join("\n")}`);
  Object.assign(kept, { script, source: compiled.source, minutes: compiled.minutes, options: () => options });
  emit({
    type: "tool_result",
    name: "write_lecture",
    text: [`Compiled ${script.chapters.length} chapter(s).`, ...compiled.warnings.map((w) => `warning: ${w}`)].join("\n"),
  });
  return { source: compiled.source, sceneClass: SCENE_CLASS, model: "fixture agent", inputTokens: 0, outputTokens: 0, costUsd: 0 };
}

function sceneFixture(request: GenerateRequest, template: Template): string {
  const lines = request.content
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const title = (lines[0] || "Untitled").slice(0, 42);
  const beats = (lines.slice(1, 4).length ? lines.slice(1, 4) : ["One idea", "The next", "Then the last"]).map((line) =>
    line.slice(0, 42),
  );
  const escape = (s: string) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const q = (s: string) => `"${escape(s)}"`;
  const [accent, second] = [...template.palette, template.palette[0]];
  const paper = template.ink;
  const note = request.instruction
    ? `\n        # edit: ${request.instruction.replace(/\n/g, " ").slice(0, 70)}`
    : "";

  const header =
    `from manim import *\n\n` +
    `config.background_color = "${template.background}"\n\n\n` +
    `class ${SCENE_CLASS}(Scene):\n` +
    `    def construct(self):${note}\n`;

  const stroke = template.id === "whiteboard" || template.id === "chalkboard" ? 8 : 3;
  const fill = template.id === "vox" ? `, fill_color="${second}", fill_opacity=1` : "";
  const sentences = beats.map((beat) => {
    if (beat.length <= 36) return [beat];
    const cut = beat.lastIndexOf(" ", 36);
    const at = cut > 12 ? cut : 36;
    return [beat.slice(0, at).trim(), beat.slice(at).trim()].filter(Boolean);
  });
  return (
    header +
    `        title = Text(${q(title)}, font_size=48, color="${paper}")\n` +
    `        rule = Line(LEFT * 1.3, RIGHT * 1.3, color="${accent}", stroke_width=${stroke})\n` +
    `        heading = VGroup(title, rule).arrange(DOWN, buff=0.22)\n` +
    `        heading.to_edge(UP, buff=0.7)\n` +
    `        self.play(Write(title), run_time=0.7)\n` +
    `        self.play(Create(rule), run_time=0.35)\n` +
    sentences
      .map((parts, i) => {
        const built = parts
          .map((part, j) => `        line${i}_${j} = Text(${q(part)}, font_size=32, color="${paper}")`)
          .join("\n");
        const group = parts.map((_, j) => `line${i}_${j}`).join(", ");
        return (
          `${built}\n` +
          `        beat${i} = VGroup(${group}).arrange(DOWN, buff=0.22)\n` +
          `        mark${i} = Circle(radius=0.28, color="${second}", stroke_width=${stroke}${fill})\n` +
          `        row${i} = VGroup(mark${i}, beat${i}).arrange(RIGHT, buff=0.4)\n` +
          `        row${i}.move_to(DOWN * 0.6)\n` +
          `        self.play(Create(mark${i}), FadeIn(beat${i}), run_time=0.55)\n` +
          `        # voice: ${parts.join(" ")}\n` +
          `        self.wait(${Math.max(1.6, parts.join(" ").split(/\s+/).length * 0.45).toFixed(2)})\n` +
          (i < sentences.length - 1 ? `        self.play(FadeOut(row${i}), run_time=0.3)` : `        self.wait(0.4)`)
        );
      })
      .join("\n") +
    `\n`
  );
}

function cartopyFallback(request: GenerateRequest, template: Template): string {
  const escape = (s: string) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const title = (request.content.trim().split("\n")[0] || "Coastline").slice(0, 40);
  const note = (request.content.split("\n")[1] || "").trim().slice(0, 48);
  const label = note
    ? `        label = Text("${escape(note)}", font_size=24, color="${template.palette[1]}")\n        label.to_edge(DOWN)\n        self.play(FadeIn(label), run_time=0.6)\n`
    : "";
  return `from manim import *
import cartopy.io.shapereader as shpreader

config.background_color = "${template.background}"

LON_SCALE = 6.0 / 180.0
LAT_SCALE = 3.2 / 90.0


def line_coords(geom):
    if hasattr(geom, "geoms"):
        for part in geom.geoms:
            yield np.asarray(part.coords)
    else:
        yield np.asarray(geom.coords)


def build_coastline():
    fn = shpreader.natural_earth(resolution="50m", category="physical", name="coastline")
    group = VGroup()
    for geom in shpreader.Reader(fn).geometries():
        for coords in line_coords(geom):
            if len(coords) < 2:
                continue
            pts = [np.array([lon * LON_SCALE, lat * LAT_SCALE, 0.0]) for lon, lat in coords[:, :2]]
            line = VMobject(stroke_width=1.2, stroke_color="${template.palette[0]}")
            line.set_points_as_corners(pts)
            group.add(line)
    return group


class ${SCENE_CLASS}(Scene):
    def construct(self):
        title = Text("${escape(title)}", font_size=28, color="${template.palette[template.palette.length - 1]}")
        title.to_edge(UP)
        coast = build_coastline()
        self.add(title)
        self.play(FadeIn(coast), run_time=1.2)
${label}        self.wait(0.8)
`;
}

/** The picked style wins even when the model forgets the background. */
export function enforceStyle(source: string, template: Template): string {
  let text = source;
  const background = `config.background_color = "${template.background}"`;
  if (/config\.background_color\s*=/.test(text)) {
    text = text.replace(/config\.background_color\s*=\s*(?:["'][^"']*["']|\w+)/, background);
  } else if (text.includes("from manim import *")) {
    text = text.replace("from manim import *", `from manim import *\n\n${background}`);
  } else {
    text = `from manim import *\n\n${background}\n\n${text}`;
  }
  if (!/config\.frame_rate\s*=/.test(text)) {
    text = text.replace(background, `${background}\nconfig.frame_rate = 15`);
  }
  return text.endsWith("\n") ? text : text + "\n";
}

/**
 * find_map nests project() inside build_region and the model then calls it
 * from construct. Return the function and unpack it so that name exists.
 */
export function exposeMapProject(source: string): string {
  if (!/def project\s*\(/.test(source)) return source;
  let text = source.replace(/^([ \t]+)return group\s*$/m, "$1return group, project");
  text = text.replace(/^([ \t]*)(\w+) = build_region\(\)\s*$/gm, "$1$2, project = build_region()");
  return text;
}

/** Drop the broken half of a line the model rewrote in place. */
export function sanitizeScene(source: string): string {
  return source
    .split("\n")
    .map((line) => {
      const dead = line.match(/^(\s*).*\bif False else\b\s+(.*)$/);
      // Manim has rotate_vector, not a free function named rotate. Method
      // calls such as square.rotate(PI/4) are left alone.
      const fixed = (dead ? `${dead[1]}${dead[2]}` : line)
        .replace(/(?<!\.)\brotate\(/g, "rotate_vector(")
        // `UP * (t / 50)[1]` indexes the number, not the vector.
        .replace(
          /(\b(?:UP|DOWN|LEFT|RIGHT|OUT|IN|ORIGIN)\s*\*\s*)\(([^()\n]+)\)(\[\d+\])/g,
          "($1($2))$3",
        );
      return fixed;
    })
    .join("\n");
}

function syntaxError(source: string): Promise<string | null> {
  return new Promise((resolve) => {
    const child = spawn(python(), ["-c", "import ast,sys; ast.parse(sys.stdin.read())"]);
    let err = "";
    child.stderr.on("data", (chunk) => (err += chunk.toString()));
    child.on("error", () => resolve("could not run Python"));
    child.on("close", (code) => resolve(code === 0 ? null : err.trim().split("\n").slice(-6).join("\n")));
    child.stdin.write(source);
    child.stdin.end();
  });
}

export function usingFixture(): boolean {
  return !process.env.OPENROUTER_API_KEY;
}

export async function generate(
  request: GenerateRequest,
  emit: (event: AgentEvent) => void = () => {},
  stopped: () => boolean = () => false,
): Promise<Generated> {
  const template = templateById(request.templateId);
  const kept: Kept = {};
  const startedAt = Date.now();
  const result = usingFixture() ? await viaFixture(request, emit, kept) : await viaOpenRouter(request, emit, stopped, kept);
  // A long lecture as micro-lectures of 25-30 min: cut where its topics meet when it was written as a series
  // (topics.ts), else between chapters once it runs past PANIM_MAX_VIDEO_MINUTES (lib/parts.ts).
  if (isLecture(template) && kept.script && kept.options && kept.source === result.source && kept.minutes) {
    const script = kept.script as Record<string, unknown>;
    const byTopic = splitByTopics(script, kept.minutes);
    // Each video kept to a micro-lecture's length: a topic that came out long is cut again (as many videos as
    // that makes).
    let parts: LecturePart[] = boundParts(byTopic.length ? byTopic : splitLecture(script, kept.minutes));
    if (parts.length) {
      emit({ type: "message", role: "status", text: `The lecture runs about ${Math.round(kept.minutes)} min: making it ` +
        (byTopic.length ? `${parts.length} micro-lectures, one per topic` : `${parts.length} videos of up to ${maxVideoMinutes()} min`) +
        ` (${parts.map((p) => `${p.title}, ${Math.round(p.minutes)} min`).join("; ")}).` });
      const built: { title: string; minutes: number; source: string }[] = [];
      // The parts compile at once (each is its own process). One that will not compile on its own (it points back
      // at a picture of the part before) is joined to a neighbour and compiled again: the lecture stays a series,
      // never one video of hours.
      const options = kept.options();
      let compiledParts = await Promise.all(parts.map((part) => compileLecture(part.script, options)));
      for (let round = 0; round < 6 && parts.length > 1; round++) {
        const bad = compiledParts.findIndex((c) => !c.source);
        if (bad < 0) break;
        const other = bad > 0 ? bad - 1 : bad + 1;
        const [a, b] = bad > 0 ? [other, bad] : [bad, other];
        emit({ type: "message", role: "status", text: `${parts[bad].title} did not compile on its own ` +
          `(${compiledParts[bad].errors[0] ?? "no reason given"}); joining it to ${parts[other].title}.` });
        const joined = joinParts(parts[a], parts[b]);
        parts = [...parts.slice(0, a), joined, ...parts.slice(b + 1)].map((p, k, all) => ({ ...p, index: k + 1, of: all.length }));
        compiledParts = [...compiledParts.slice(0, a), await compileLecture(joined.script, options), ...compiledParts.slice(b + 1)];
      }
      for (const [i, part] of parts.entries()) {
        const compiled = compiledParts[i];
        if (!compiled.source) {
          emit({ type: "message", role: "status", text: `${part.title} did not compile ` +
            `(${compiled.errors[0] ?? "no reason given"}); keeping the lecture as one video.` });
          built.length = 0;
          break;
        }
        built.push({ title: part.title, minutes: compiled.minutes ?? part.minutes, source: sanitizeScene(compiled.source) });
      }
      if (built.length) {
        result.parts = built;
        result.source = built[0].source;
      }
    }
  }
  // A lecture's look belongs to the engine: its style sets the background on
  // import, and a config line pasted above it would only be overridden.
  result.source = isLecture(template)
    ? sanitizeScene(result.source)
    : exposeMapProject(sanitizeScene(enforceStyle(result.source, template)));
  if (!usingFixture()) {
    const broken = await syntaxError(result.source);
    if (broken) {
      emit({ type: "message", role: "status", text: "The scene did not parse. Asking the model to fix it." });
      const key = process.env.OPENROUTER_API_KEY!;
      const model = videoModel();
      const repair = [
        "This file is not valid Python. Reply with the corrected file only, starting with `from manim import *`.",
        "",
        broken,
        "",
        result.source,
      ].join("\n");
      emit({ type: "input", role: "user", text: repair });
      const repaired = await completionWithRetry(
        key,
        model,
        [
          { role: "system", content: systemPrompt(template) },
          { role: "user", content: repair },
        ],
        emit,
        (kind, text) => {
          emit({ type: "delta", role: kind === "thinking" ? "thinking" : "assistant", text });
        },
      );
      const repairCost = Number(repaired.usage?.cost ?? 0);
      result.costUsd = kept.ledger ? kept.ledger.bill("fixes", repairCost, {
        inputTokens: repaired.usage?.prompt_tokens ?? 0, outputTokens: repaired.usage?.completion_tokens ?? 0,
        span: repaired.span,
      }) : result.costUsd + repairCost;
      const text = repaired.message.content?.trim() ?? "";
      if (!text) throw new Error(broken);
      result.source = exposeMapProject(sanitizeScene(enforceStyle(extractScene(text), template)));
      const still = await syntaxError(result.source);
      if (still) throw new Error(still);
    }
  }
  emit({ type: "message", role: "status", text: `[time] script ready: ${Math.round((Date.now() - startedAt) / 1000)} s` });
  emit({
    type: "done",
    source: result.source,
    parts: result.parts,
    model: result.model,
    inputTokens: result.inputTokens,
    outputTokens: result.outputTokens,
    costUsd: kept.ledger ? kept.ledger.total : result.costUsd,
    costs: kept.ledger?.snapshot(),
  });
  return result;
}

/** The request's uploaded document, if it names one that still exists. */
async function documentOf(request: GenerateRequest): Promise<DocumentManifest | null> {
  if (!request.documentId) return null;
  try {
    return await loadDocument(request.documentId);
  } catch {
    return null;
  }
}

/** The content's subject, announced in the trace so the choice is visible. */
async function subjectOf(request: GenerateRequest, emit: (event: AgentEvent) => void): Promise<Subject> {
  // Diagrams draw their nodes from the SVG drawing library: fetch it before the lecture is written.
  if (!symbolsReady()) {
    emit({ type: "message", role: "status", text: "Downloading the SVG drawings diagrams are built from (once)…" });
    await ensureSymbols();
  }
  const subject = await classifySubject(`${request.content}\n${request.instruction ?? ""}`, request.subject);
  emit({
    type: "message",
    role: "status",
    text: `Subject: ${subject.label} (map ${subject.map}; ${subject.style} style${subject.why.length ? `; ${subject.why.join(", ")}` : ""})`,
  });
  return subject;
}

/** The engine style: the template's, or the subject's when the template is Auto. */
function effectiveStyle(template: Template, subject: Subject | null): string | undefined {
  return template.style === "auto" ? subject?.style ?? "vox" : template.style;
}
