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

import { ProviderAuthError, ResponsesStream, describeProviders, ensurePrices, modelRequest, providerError, providerName, withCost } from "./providers";
import { sanitizeScene } from "./scenefix";
export { sanitizeScene };
import { spawn } from "node:child_process";
import { Agent, fetch as undiciFetch } from "undici";
import { CostLedger, type AiPicture } from "./costs";
import { Template, templateById } from "./templates";
import { shownSoFar, taughtNotes } from "./continuity";
import { picturesStatus, type Compiled, type Prefetch, type GeneratedPicture, type ImageReport } from "./lecture";
import { ADD_CHAPTERS_TOOL, LANGUAGES, LECTURE_TOOL, PARTS_OVER_MINUTES, classifySubject, compileLecture, fixtureScript, makePictures, manimModel, languagePrompt, lecturePrompt, referencePrompt, resolveRegion, targetMinutes, type Language, type Subject } from "./lecture";
import { figureCaptions, figurePictures, figurePrompt, loadDocument, scriptFigures, teachingFigures, type DocumentManifest } from "./document";
import { drawFigures, figuresWithin, type Drawn } from "./figures";
import { TimingLog } from "./timing";
import { dropRepeats, sameParagraph } from "./repeats";
import { fillManim, freeDrawings, hasManim, needsManim, repairManim, type ManimCoderOptions } from "./manimcoder";
import { resolvePlaces } from "./mapagent";
import type { BookQuestion } from "./questions";
import { joinParts, maxVideoMinutes, splitByTopics, splitLecture, topicPart, type LecturePart } from "./parts";
import { nextVideos, planTopics, type Topic } from "./topics";
import { MediaLog, type MediaItem } from "./media";
import { PREVIEW_MINUTES, SECTION_TOOL, SECTION_TOOL_PLANNED, TRANSITION_TOOL, storyPlanOn, WORDS_PER_MINUTE, cleanSection, fromTranscriptPrompt, previewSections, sectionForVideo, sectionProblem, sectionRequest, sectionsOf, transcriptPrompt, transitionRequest, transcriptSections, type Section, type WrittenSection } from "./transcript";
import { fillLines, linesOf, numberedSection } from "./lines";
import { LEARNING_MAP_SYSTEM, LEARNING_MAP_TOOL, goalLine, learningMapRequest, readLearningMap, sourceItems, type LearningMap } from "./learningmap";
import { STORY_PLAN_SYSTEM, STORY_PLAN_TOOL, planView, readStoryPlan, sectionPlanText, storyPlanRequest, type GoalStatus, type StoryPlan } from "./storyplan";
import { PATCH_TOOL, goalsTaught, insertAfterLine, patchRequest } from "./coverage";
import { REPO, python, speakAhead } from "./pocketanim";
import { AgentEvent, TOOLS, applySceneTool, runTool } from "./agent";

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
  /** The model that looks at the book's figures (figures.ts: it reads images); without it, OPENROUTER_FIGURE_MODEL. */
  svgModel?: string;
  /** How the pictures are drawn (lib/artstyles.ts): "auto" or left out, the template's own art. */
  art?: string;
  /** The generate job's id (app/api/generate): the generation's record in Supabase is kept under it (lib/media.ts). */
  generationId?: string;
  /** A preview of 2-3 minutes: the lecture's opening sections only, with a map and a diagram if it has any, to judge
   * the look and the voice before the whole series is made. */
  preview?: boolean;
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
 * The model that looks at the book's figures and says how each is shown (a photograph, built in Manim, or a diagram
 * the diagram model redraws): the page's choice, else OPENROUTER_FIGURE_MODEL (OPENROUTER_SVG_MODEL, its older
 * name), else the video's model. It must read images.
 */
export function svgModel(chosen?: string): string {
  return chosen?.trim() || process.env.OPENROUTER_FIGURE_MODEL || process.env.OPENROUTER_SVG_MODEL || videoModel();
}

const SCENE_CLASS = "GeneratedScene";
/** How long a turn may pass with nothing from the model before it is stopped (PANIM_MODEL_WAIT_MINUTES). */
const FIRST_REPLY_MINUTES = Math.max(1, Number(process.env.PANIM_MODEL_WAIT_MINUTES) || 5);
// A reply that streams nothing for this long after it started writing has stalled: asked again.
const STALL_MS = Math.max(30, Number(process.env.PANIM_STALL_SECONDS) || 90) * 1000;
/** m:ss, for the progress lines. */
const clock = (ms: number) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

/**
 * How hard the model thinks before it writes: PANIM_REASONING_EFFORT = low (the default), minimal, medium or
 * high; "off" sends no setting (the model's own default). Low keeps a lecture quick and cheap to write.
 */
export function reasoningOption(chosen?: string): { reasoning?: { effort: string } } {
  const effort = (chosen || process.env.PANIM_REASONING_EFFORT || "low").trim().toLowerCase();
  if (effort === "off" || effort === "none" || effort === "default") return {};
  return { reasoning: { effort: ["minimal", "low", "medium", "high"].includes(effort) ? effort : "low" } };
}

/**
 * How hard the model thinks when it writes the video's chapters (the pictures, diagrams, labels and when to zoom):
 * PANIM_VIDEO_REASONING_EFFORT, medium by default. The visual choices are where thinking pays most; the transcript
 * keeps PANIM_REASONING_EFFORT.
 */
export function videoEffort(): string {
  return (process.env.PANIM_VIDEO_REASONING_EFFORT || "medium").trim().toLowerCase();
}

/**
 * How long a video-step request may send nothing at all before it is asked again (PANIM_VIDEO_WAIT_MINUTES, 6).
 * At medium effort some models think in silence for minutes; one that has not begun after this long has usually
 * hung, and holding its slot for FIRST_REPLY_MINUTES (15) held its whole lecture back.
 */
const VIDEO_WAIT_MS = Math.max(2, Number(process.env.PANIM_VIDEO_WAIT_MINUTES) || 3) * 60_000;

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

type ToolSpec = (typeof TOOLS)[number] | typeof LECTURE_TOOL | typeof ADD_CHAPTERS_TOOL | typeof SECTION_TOOL | typeof TRANSITION_TOOL;

async function streamCompletion(
  key: string,
  model: string,
  messages: OutMessage[],
  onDelta: (kind: "thinking" | "assistant", text: string) => void,
  tools: ToolSpec[] = TOOLS,
  signal?: AbortSignal,
  toolChoice: "auto" | "required" = "auto",
  withReasoning: boolean | string = true,
): Promise<{ message: ChatMessage; usage?: Usage; finishReason: string }> {
  // An openai/... model goes to OpenAI itself when OPENAI_API_KEY is set (lib/providers.ts).
  const request = modelRequest({
    model,
    messages: withCachedSystem(messages, model),
    tools,
    tool_choice: toolChoice,
    stream: true,
    usage: { include: true },
    ...(withReasoning ? reasoningOption(typeof withReasoning === "string" ? withReasoning : undefined) : {}),
  }, key);
  const response = await undiciFetch(request.url, {
    method: "POST",
    signal,
    dispatcher: OPENROUTER_AGENT,
    headers: request.headers,
    body: JSON.stringify(request.body),
  });
  if (!response.ok) throw providerError(model, response.status, await response.text());
  // A request with tools to an OpenAI model went to its Responses API: its events are read as chat deltas.
  const responses = request.responses ? new ResponsesStream() : null;
  if (!response.body) throw new Error(`${providerName(model)} returned no stream`);

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
        if (tool === "edit_scene" || tool === "write_lecture" || tool === "write_section" ||
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
    if (responses) {
      const got = responses.handle(parsed as Record<string, unknown>);
      if (got.error) throw new Error(`OpenAI: ${got.error}`);
      if (got.delta) takeDelta(got.delta);
      if (responses.usage) usage = responses.usage;
      if (responses.finishReason) finishReason = responses.finishReason;
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
    return { ...parsed, usage: withCost(model, parsed.usage), finishReason: "" };
  }

  const tool_calls = toolCallsFrom(calls);
  return {
    message: {
      role: "assistant",
      content: content || null,
      tool_calls: tool_calls.length ? tool_calls : undefined,
    },
    usage: withCost(model, usage),
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
  effort?: string,
): Promise<{ message: ChatMessage; usage?: Usage; finishReason?: string; span: [number, number] }> {
  // When the request began and its answer came: the task's time (lib/costs.ts), retries included.
  const began = Date.now();
  let empties = 0;
  let cut = false;
  for (let attempt = 1; attempt <= EMPTY_RETRIES; attempt++) {
    // After an empty reply, ask more loosely: some providers answer nothing when a tool call is "required",
    // and a reasoning model can spend its whole output on thinking. The prompts still ask for the tool.
    const choice = empties > 0 ? "auto" : toolChoice;
    const reasoning: boolean | string = empties < 2 && !cut ? (effort || true) : false;
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
  /** The generation's record in Supabase (lib/media.ts): its pictures, scenes and programs. */
  media?: MediaLog;
  /** Every timed step of the generation (lib/timing.ts). */
  timing?: TimingLog;
};

async function viaOpenRouter(
  request: GenerateRequest,
  emit: (event: AgentEvent) => void,
  stopped: () => boolean = () => false,
  kept: Kept = {},
): Promise<Generated> {
  const key = process.env.OPENROUTER_API_KEY ?? "";
  // How long each stage took, from the start of the run, in the status stream.
  const startedAt = Date.now();
  // Reading the source (the document, a reference video) and choosing the subject: the "planning" row.
  const planningBegan = startedAt;
  const mark = (stage: string) =>
    emit({ type: "message", role: "status", text: `[time] ${stage}: ${Math.round((Date.now() - startedAt) / 1000)} s` });
  // The transcript runs in the background of the video's chapters: when they fail, it stops too.
  let abandoned = false;
  const pageClosed = stopped;
  stopped = () => abandoned || pageClosed();
  const model = videoModel();
  const template = templateById(request.templateId);
  const doc = await documentOf(request);
  const reference = await documentOf({ ...request, documentId: request.referenceId });
  const language = LANGUAGES.includes(request.language as Language) ? (request.language as Language) : "auto";
  const referenceText = reference?.parts?.map((p) => p.text).join("\n") ?? "";
  // Without a chosen length, a remake runs as long as the video it follows.
  const referenceMinutes = reference?.video?.duration ? Math.min(90, Math.max(3, Math.round(reference.video.duration / 60))) : 0;
  // As long as the content needs; a long one is as many micro-lectures of 25-30 min as that makes (topics.ts).
  const minutes = request.minutes ?? (referenceMinutes ||
    targetMinutes(`${request.content}\n${request.instruction ?? ""}`, doc?.markdown ?? ""));
  const subject = await subjectOf({ ...request,
    content: `${request.content}\n${referenceText.slice(0, 15000)}\n${(doc?.markdown ?? "").slice(0, 15000)}` }, emit);
  const planningEnded = Date.now();
  const style = effectiveStyle(template, subject);
  if (reference?.parts?.length) {
    emit({ type: "message", role: "status", text: `Reference video: ${reference.video?.title ?? "transcript"}, ` +
      `${reference.parts.length} parts; the lecture follows them in order (about ${minutes} min).` });
  }
  // The book's figures, looked at (figures.ts) while the transcript is written: graphs and the like rebuilt in Manim,
  // the rest redrawn by the diagram model as exact copies in the lecture's style; the script writer is told about
  // them once they are done (stage 2). The book's own pictures are never shown. PANIM_SVG_FIGURES=0 builds them all
  // in Manim.
  // What the lecture cost, task by task (lib/costs.ts); costUsd is its total. Both stages and the figures run at
  // once, so every bill goes through the ledger and is sent with a usage event straight away.
  const ledger = new CostLedger();
  kept.ledger = ledger;
  // Every timed step, with what it was for, in harness/app/.logs (lib/timing.ts); its summary ends the run.
  const timing = new TimingLog(`gen-${String(request.content ?? "lecture").slice(0, 40)}`);
  kept.timing = timing;
  ledger.onSpan = (task, start, end, detail) => {
    if (!detail?.quiet) timing.span(task, start, end, detail ?? {});
  };
  emit({ type: "message", role: "status", text: `Timing log: ${timing.file}` });
  // A model try that stalled, went silent or failed, and was asked again: its time is lost, and shown as such.
  const lostTry = (began: number, detail: Record<string, unknown> = {}) => {
    ledger.time("stalled", began, Date.now(), detail);
    ledger.count("stalled", 1);
  };
  ledger.time("planning", planningBegan, planningEnded, { what: "reading the source, choosing the subject" });
  let inputTokens = 0;
  let outputTokens = 0;
  let costUsd = 0;
  const sendCosts = (text: string) =>
    emit({ type: "usage", text, inputTokens, outputTokens, costUsd, costs: ledger.snapshot(), seconds: ledger.elapsed });
  const figureTally = { diagram: 0, manim: 0, kept: 0, failed: 0 };
  // Each picture the AI made for the lecture goes to the page as it is made (once), with what it cost.
  const shownPictures = new Set<string>();
  const showPicture = (picture: AiPicture) => {
    if (shownPictures.has(picture.file)) return;
    shownPictures.add(picture.file);
    emit({ type: "picture", picture });
  };
  // Pictures the image model made while a script compiled (genimage.py): billed, and shown once each.
  const billGenerated = (made: GeneratedPicture[] | undefined) => {
    const fresh = (made ?? []).filter((m) => m.made && !shownPictures.has(m.path));
    if (!fresh.length) return;
    const usd = fresh.reduce((t, m) => t + (m.usd ?? 0), 0);
    costUsd = ledger.bill("images", usd, { items: fresh.length });
    sendCosts(`${fresh.length} picture${fresh.length > 1 ? "s" : ""} made by the image model: $${usd.toFixed(4)}`);
    for (const m of fresh) {
      showPicture({ kind: "illustration", file: m.path, title: m.what, usd: m.usd ?? 0, reused: false, paid: m.usd ?? null,
        detail: m.model });
    }
  };
  // Figures settled so far: stage 2 waits for them only so long (PANIM_FIGURE_WAIT_SECONDS), then goes on with
  // these; a figure drawn later is kept on disk for the next run, and this one rebuilds it in Manim.
  const figuresReady: Record<string, Drawn> = {};
  const drawingStarted = Date.now();
  const drawing = doc && process.env.PANIM_SVG_FIGURES !== "0" && teachingFigures(doc).length
    ? drawFigures(teachingFigures(doc), {
      key: process.env.OPENROUTER_API_KEY,
      model: svgModel(request.svgModel),
      markdown: doc.markdown,
      repo: REPO,
      python: python(),
      onStatus: (text) => emit({ type: "message", role: "status", text }),
      style,
      art: request.art,
      onTime: (start, end, detail) => ledger.time("figures", start, end, detail),
      onCost: (usd) => {
        costUsd = ledger.bill("figures", usd);
        sendCosts(`book figure redrawn: $${usd.toFixed(4)}`);
      },
      onDrawn: (id, made, kept) => {
        figuresReady[id] = made;
        // Every book figure is listed with what it cost: redrawn by the diagram model, or left out (never the
        // book's own picture) and rebuilt in Manim.
        const figure = teachingFigures(doc).find((f) => f.id === id);
        const title = `${id}: ${figure?.caption ?? ""}`.trim();
        const paid = { usd: kept ? 0 : made.usd ?? 0, reused: kept, paid: made.usd ?? null };
        if (made.manim && figure?.file) {
          showPicture({ kind: "rebuilt", file: figure.file, title, ...paid, status: "a graph or the like: rebuilt in Manim" });
        } else if (made.map && figure?.file) {
          showPicture({ kind: "rebuilt", file: figure.file, title, ...paid, status: "a map: built on the lecture's map" });
        } else if (made.generated?.file) {
          const how = made.faithful ? "close to the book's own look" : "in the lecture's style";
          showPicture({ kind: "figure", file: made.generated.file, title, ...paid, detail: made.generated.credit,
            status: made.checked ? `redrawn by the diagram model ${how}, every label checked`
              : `redrawn by the diagram model ${how} (closest try: ${made.issues || "not every label matched"})` });
        } else if (figure?.file) {
          showPicture({ kind: "rebuilt", file: figure.file, title, ...paid,
            status: `not redrawn (${made.diagramError ?? "no picture"}): left out, rebuilt in Manim` });
        }
        if (kept) figureTally.kept += 1;
        else if (made.manim || made.map) figureTally.manim += 1;
        else if (made.generated) figureTally.diagram += 1;
        else figureTally.failed += 1;
        ledger.count("figures", made.generated && !kept ? 1 : 0, [
          figureTally.diagram ? `${figureTally.diagram} redrawn by the diagram model` : "",
          figureTally.manim ? `${figureTally.manim} rebuilt on the board (Manim or the map)` : "",
          figureTally.kept ? `${figureTally.kept} decided by an earlier run (free)` : "",
          figureTally.failed ? `${figureTally.failed} not redrawn (rebuilt in Manim)` : "",
        ].filter(Boolean).join(", "));
        sendCosts(`book figure ${id}: ${made.manim ? "rebuilt in Manim" : made.map ? "built on the map"
          : made.generated ? "redrawn by the diagram model" : "not redrawn"}`);
      },
    }).catch((error) => {
      emit({ type: "message", role: "status", text: `The figures were not redrawn (${String(error).slice(0, 160)}); ` +
        "they are built on the board instead." });
      return undefined;
    })
    : Promise.resolve(undefined);
  const systemBase = lecturePrompt({ ...template, style }, minutes, subject ?? undefined);
  const systemTail = languagePrompt(language) + (reference ? referencePrompt(reference) : "");
  const user = lectureUserPrompt(request);
  const EDIT_TOOL = TOOLS.find((tool) => tool.function.name === "edit_scene")!;
  const tools: ToolSpec[] = [LECTURE_TOOL, ...(minutes > PARTS_OVER_MINUTES ? [ADD_CHAPTERS_TOOL] : []), EDIT_TOOL];
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
  // A planned lecture's moments for the picture (storyplan.ts): per section, what its scenes show on the stage.
  const storyCues = new Map<number, string[]>();
  // A long lecture as a series of videos of 25-30 min (topics.ts). Where each starts and ends is decided from the
  // written transcript as its sections come in (their real length), always between sections, and the writer then
  // writes the words that close one video and open the next: no video is ever cut after it is made.
  const topics: Topic[] = [];
  // Whether the lecture is made as a series: when its estimated length is more than one video holds.
  let series = false;
  if (!(request.instruction && request.previousSource)) {
    // A book (a PDF) is taught section by section, each with its own slice of the text; a reference video is
    // remade part by part.
    let sections = transcriptSections(reference, minutes, reference?.parts?.length ? "" : doc?.markdown ?? "");
    if (request.preview) {
      // A preview: the opening of the lecture only, about PREVIEW_MINUTES of teaching, as one short video.
      sections = previewSections(sections);
      emit({ type: "message", role: "status", text: `Preview: the first ${sections.length} section` +
        `${sections.length > 1 ? "s" : ""} only (about ${PREVIEW_MINUTES} min), to check the look and the voice. ` +
        "Untick Preview to make the whole lecture." });
    }
    series = !request.preview && planTopics(sections).length > 1;
    if (series) {
      emit({ type: "message", role: "status", text: `About ${Math.round(sections.reduce((n, x) => n + x.minutes, 0))} min ` +
        "estimated: made as videos of 25-30 min, each ending where the written transcript reaches that length, between " +
        "sections." });
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
    // A book's lecture is planned before it is written (learningmap.ts, storyplan.ts): its goals, then each video's
    // story, then its sections from that plan, and each section's goals checked as it comes in.
    const planOn = storyPlanOn() && fromBook && !reference?.parts?.length;
    const transcriptPromptFor = (planned: boolean) => transcriptPrompt({
      sections, minutes, language, languageRules: languagePrompt(language), subject: subject?.label,
      hasReference: !!reference?.parts?.length, planned,
      // The book's text is already in its sections; only what was typed goes in beside it.
      content: fromBook ? request.content : `${request.content}\n${doc?.markdown ?? ""}`,
    });
    let prompt = transcriptPromptFor(planOn);
    emit({ type: "input", role: "system", text: prompt });
    const writer = transcriptModel(request.transcriptModel);
    // How hard the writer thinks (PANIM_TRANSCRIPT_EFFORT): medium for a planned lecture, the default otherwise.
    const transcriptEffort = process.env.PANIM_TRANSCRIPT_EFFORT || (planOn ? "medium" : undefined);
    let map: LearningMap | null = null;
    const plans = new Map<number, StoryPlan>();                 // each section's video plan, by section number
    // The videos a planned lecture is made as, decided before writing (each video's story is planned whole):
    // the sections of each, by number.
    let videoGroups: number[][] = planOn
      ? (series ? planTopics(sections).map((t) => t.sections) : [sections.map((x) => x.n)]) : [];
    const coverage = { planned: 0, taught: 0, patched: 0, missing: [] as string[] };
    // Each goal's standing, and the plan as the page shows it (sent again whenever it changes).
    const goalStatus = new Map<string, GoalStatus>();
    const sendPlan = () => {
      if (!map) return;
      const videoPlans = [...new Set(plans.values())].sort((a, b) => a.video - b.video);
      emit({ type: "plan", plan: planView(map, videoPlans, goalStatus, sections.map((x) => x.n), bookQs) });
    };
    /** One call that answers with a tool (the map, a video's plan, a patch): its arguments, or null. */
    const askTool = async (system: string, content: string, tool: unknown, what: string): Promise<Record<string, unknown> | null> => {
      try {
        const result = await completionWithRetry(key, writer, [{ role: "system", content: system }, { role: "user", content }],
          emit, () => {}, [tool as ToolSpec], undefined, "required", transcriptEffort);
        const addedIn = result.usage?.prompt_tokens ?? 0;
        const addedOut = result.usage?.completion_tokens ?? 0;
        inputTokens += addedIn;
        outputTokens += addedOut;
        costUsd = ledger.bill("transcript", Number(result.usage?.cost ?? 0), { inputTokens: addedIn, outputTokens: addedOut,
          span: result.span, detail: { step: what, model: writer } });
        for (const call of result.message.tool_calls ?? []) {
          try {
            return JSON.parse(call.function.arguments || "{}") as Record<string, unknown>;
          } catch {}
        }
        return null;
      } catch (error) {
        if (error instanceof ProviderAuthError) throw error;     // a refused key is refused again: stop
        emit({ type: "message", role: "status", text: `Transcript: the ${what} could not be made ` +
          `(${error instanceof Error ? error.message.slice(0, 140) : String(error)}).` });
        return null;
      }
    };
    /** Before any section is written: the learning map, then every video's story plan at once. */
    const planLecture = async () => {
      if (!planOn) return;
      const items = sourceItems(sections);
      emit({ type: "message", role: "status", text: `Planning: the learning goals of the ${items.length} headings, terms, ` +
        "boxes and figures of the book, before anything is written." });
      const raw = await askTool(LEARNING_MAP_SYSTEM, learningMapRequest(sections, items, subject?.label), LEARNING_MAP_TOOL,
        "learning map");
      if (!raw) {
        // No map: written as before, from the book's parts.
        prompt = transcriptPromptFor(false);
        videoGroups = [];
        return;
      }
      map = readLearningMap(raw, items, sections);
      emit({ type: "message", role: "status", text: `Learning map: ${map.goals.length} goals from the book's ${items.length} ` +
        `items${map.added ? ` (${map.added} added for items the map left out)` : ""}.` });
      emit({ type: "tool_result", name: "write_learning_map", text: map.goals.map((g) => goalLine(g, map!.items)).join("\n") });
      sendPlan();
      const videos = videoGroups.map((ns, k) => ({ index: k + 1, of: videoGroups.length,
        sections: ns.map((n) => sections.find((x) => x.n === n)).filter((x): x is Section => !!x) }));
      const replies = await Promise.all(videos.map((video) => {
        const qs = video.sections.flatMap((x) => x.questions ?? []);
        return askTool(STORY_PLAN_SYSTEM, storyPlanRequest(video, map!, qs, subject?.label), STORY_PLAN_TOOL,
          `story plan of video ${video.index}`).then((reply) => reply ? readStoryPlan(reply, video, qs) : null);
      }));
      const byId = new Map(bookQs.map((q) => [q.id, q]));
      replies.forEach((plan, k) => {
        if (!plan) return;
        for (const own of plan.sections) {
          plans.set(own.section, plan);
          storyCues.set(own.section, [
            "THE STORY'S MOMENTS IN THIS SECTION (from the lecture's plan), for the stage:",
            ...(plan.sections[0]?.section === own.section ? [`  The video's big question, asked near its start: put it on ` +
              `the stage as a question when it is asked ("${plan.bigQuestion}").`] : []),
            ...(own.guessFirst ? [`  The student is asked to guess ("${own.guessFirst}"): show it as a question on the stage ` +
              "when it is asked, and the answer when the transcript gives it."] : []),
            ...(plan.runningExample ? [`  The running example (${plan.runningExample}): when the transcript comes back to it, ` +
              "show the same picture of it as before, not a new one."] : []),
          ]);
          // The book's questions go to the section the plan asks them in.
          const at = sections.findIndex((x) => x.n === own.section);
          if (at >= 0) sections[at] = { ...sections[at], questions: own.questions.map((id) => byId.get(id)).filter((q): q is BookQuestion => !!q) };
        }
        emit({ type: "message", role: "status", text: `Story plan, video ${k + 1}: "${plan.bigQuestion}"` +
          (plan.runningExample ? `; running example: ${plan.runningExample}` : "") + "." });
      });
      // A section of only the book's questions whose questions the plan asked elsewhere is not written.
      const empty = sections.filter((x) => x.questionsOnly && !(x.questions ?? []).length).map((x) => x.n);
      if (empty.length) {
        for (const n of empty) sections.splice(sections.findIndex((x) => x.n === n), 1);
        videoGroups = videoGroups.map((ns) => ns.filter((n) => !empty.includes(n))).filter((ns) => ns.length);
      }
      sendPlan();
    };
    /** A section's part in its video's plan, for its request ([] without a plan). */
    const planFor = (n: number): string[] => {
      if (!map) return [];
      const plan = plans.get(n);
      if (plan) return sectionPlanText(plan, n, map.goals, map);
      const own = map.goals.filter((g) => g.section === n);
      return own.length ? ["THE GOALS THIS SECTION TEACHES, every one (report each in goals_taught with the numbers of the",
        "sentences, counted from 1 in your text, that teach it):", ...own.map((g) => `  ${goalLine(g, map!.items)}`)] : [];
    };
    /** A written section's goals checked: each one it did not report is written in where it fits (one small call
     * each), and counted. */
    const coverSection = async (section: Section, text: string, reported: unknown): Promise<string> => {
      if (!map) return text;
      const own = map.goals.filter((g) => g.section === section.n);
      if (!own.length) return text;
      const taught = goalsTaught(reported, own.map((g) => g.id), linesOf(text).length);
      coverage.planned += own.length;
      coverage.taught += taught.length;
      for (const id of taught) goalStatus.set(id, "taught");
      for (const goal of own.filter((g) => !taught.includes(g.id))) {
        const lines = linesOf(text);
        const patch = await askTool("You add a few sentences to a lecture's transcript, in its own voice.",
          patchRequest(numberedSection({ n: section.n, title: "", text }), goalLine(goal, map.items), section.source),
          PATCH_TOOL, `patch for ${goal.id} in section ${section.n}`);
        const words = cleanSection(String(patch?.text ?? ""));
        if (!words) {
          coverage.missing.push(goal.id);
          goalStatus.set(goal.id, "missing");
          continue;
        }
        goalStatus.set(goal.id, "patched");
        text = insertAfterLine(text, lines, Number(patch?.after_line) || lines.length, words);
        coverage.patched += 1;
        emit({ type: "message", role: "status", text: `Coverage: section ${section.n} left out ${goal.id} ` +
          `("${goal.goal.slice(0, 80)}"); written in after its sentence ${Number(patch?.after_line) || lines.length}.` });
      }
      sendPlan();
      return text;
    };
    emit({ type: "message", role: "status",
      text: `Transcript by ${writer}; the video (pictures and Manim) by ${model}. ` +
        describeProviders({ transcript: writer, video: model, ...(manimModel() ? { Manim: manimModel()! } : {}) }) });
    const TRIES = 4;
    // A few sections at once (each its own request): one after another, a book chapter took most of an hour.
    const PARALLEL = Math.max(1, Math.min(16, Number(process.env.PANIM_TRANSCRIPT_PARALLEL) || 10));
    const done = new Map<number, WrittenSection>();
    const failed: number[] = [];
    // What each section in flight is doing, for the progress line: when it started, words so far, its try.
    const live = new Map<number, { started: number; words: number; attempt: number; thinking: boolean }>();
    let halted: unknown = null;
    const progress = setInterval(() => {
      if (!live.size) return;
      const now = Date.now();
      const parts = [...live.entries()].sort((x, y) => x[0] - y[0]).map(([n, p]) =>
        `${n} (${clock(now - p.started)}, ${p.words ? `about ${p.words} words` : p.thinking ? "thinking" : "waiting"}` +
        `${p.attempt > 1 ? `, try ${p.attempt}` : ""})`);
      emit({ type: "message", role: "status",
        text: `Transcript: ${done.size} of ${sections.length} sections written; writing ${parts.join(", ")}` });
    }, 10_000);

    /** One section, tried up to TRIES times (a stalled or failed reply, an empty one); null when none gave text. */
    const writeOne = async (section: (typeof sections)[number]): Promise<WrittenSection | null> => {
      let note: string | undefined;
      for (let attempt = 1; attempt <= TRIES; attempt++) {
        if (stopped() || halted) return null;
        const state = { started: Date.now(), words: 0, attempt, thinking: false };
        live.set(section.n, state);
        emit({ type: "message", role: "status",
          text: `Transcript: writing section ${section.n} of ${sections.length}${attempt > 1 ? `, try ${attempt} of ${TRIES}` : ""}` });
        const prior = [...done.values()].filter((w) => w.n < section.n).sort((x, y) => x.n - y.n);
        // A fresh request per section: the same system prompt (cached by the provider) and one short ask.
        const talk: OutMessage[] = [
          cachedSystem(prompt, writer),
          { role: "user", content: sectionRequest(section, sections.length, prior, note, sections, planFor(section.n)) },
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
          }, [map ? SECTION_TOOL_PLANNED : SECTION_TOOL], abort.signal, "required", transcriptEffort);
        } catch (error) {
          if (error instanceof ProviderAuthError) throw error;     // a refused key is refused again: stop
          if (stopped()) return null;
          lostTry(state.started, { step: "transcript", section: section.n, why: why ?? String(error).slice(0, 120) });
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
        costUsd = ledger.bill("transcript", addedCost, { inputTokens: addedIn, outputTokens: addedOut, span: result.span,
          detail: { section: section.n, try: attempt, model: writer } });
        sendCosts(`transcript section ${section.n}: ${addedIn} in, ${addedOut} out, $${addedCost.toFixed(4)}`);
        // The section is whatever the reply wrote: the longest write_section text, whatever number it gave, or,
        // from a provider that answered in plain text instead of calling the tool, the reply itself.
        let title = "";
        let text = "";
        let taught: string[] = [];
        let goals: unknown = [];
        for (const call of result.message.tool_calls ?? []) {
          try {
            const args = JSON.parse(call.function.arguments || "{}") as { title?: string; text?: string; taught?: unknown;
              goals_taught?: unknown };
            if (String(args.text ?? "").trim().length > text.length) {
              text = String(args.text).trim();
              title = String(args.title ?? "");
              taught = taughtNotes(args.taught);
              goals = args.goals_taught;
            }
          } catch {}
        }
        if (!text) text = (result.message.content ?? "").trim();
        // Headings, bullet marks and [stage directions] are taken out, not refused.
        text = cleanSection(text);
        // Only an empty reply is refused: what it covers and how it teaches are the writer's (its prompt says so).
        const problem = sectionProblem(text, section);
        emit({ type: "tool_result", name: "write_section",
          text: problem ? problem : `Section ${section.n}: ${title}\n\n${text}` });
        if (!problem) {
          // A sentence this section, or one written before it, already said is taken out: sections are written
          // several at once, and the same sentence came out two or three times.
          const before = [...done.values()].filter((w) => w.n !== section.n).flatMap((w) => linesOf(w.text));
          const cleaned = dropRepeats(text, before);
          if (cleaned.dropped.length) {
            emit({ type: "message", role: "status", text: `Transcript: section ${section.n}: ${cleaned.dropped.length} ` +
              `sentence${cleaned.dropped.length > 1 ? "s" : ""} said before taken out (${cleaned.dropped.slice(0, 2)
                .map((d) => `"${d.slice(0, 60)}"`).join(", ")}${cleaned.dropped.length > 2 ? ", ..." : ""}).` });
          }
          // A planned section's goals: each one it left out is written in now, before its scenes are made.
          const covered = await coverSection(section, cleaned.text, goals);
          return { n: section.n, title: title || `Section ${section.n}`, text: covered, taught };
        }
        note = problem;
      }
      return null;
    };

    // A series' videos, decided from the transcript as its sections come in (topics.nextVideos): the real length
    // of what is written, the cut only between sections, the words between two videos written by the writer.
    let cursor = 0;                                    // the first section not yet in a video
    let planning: Promise<void> = Promise.resolve();
    const spokenMinutes = (text: string) => text.split(/\s+/).filter(Boolean).length / WORDS_PER_MINUTE;
    const release = (group: Section[]) => {
      const titled = group.map((x) => done.get(x.n)).find((w): w is WrittenSection => !!w);
      const topic: Topic = { index: topics.length + 1, of: 0, sections: group.map((x) => x.n),
        minutes: Math.round(group.reduce((n, x) => n + x.minutes, 0) * 10) / 10,
        // The writer's title of the video's first section ("The Three Orders"), before the book's heading there (a
        // chapter's first heading may be a label: "THEME").
        title: done.get(group[0].n)?.title?.replace(/^Section \d+$/, "") ||
          (/^#{1,6}\s+(.+)$/m.exec(group[0].source ?? "")?.[1] ?? "").replace(/[*_`]/g, "").trim().slice(0, 80) ||
          titled?.title || "" };
      topics.push(topic);
      // Its chapters are written now, while the rest of the transcript is (stage 2).
      for (const x of group) {
        const w = done.get(x.n);
        if (!w) continue;
        ready.set(w.n, w);
        writtenQueue.push(w);
      }
      emit({ type: "message", role: "status", text: `Video ${topic.index}${topic.title ? ` ("${topic.title}")` : ""}: ` +
        `sections ${group[0].n}-${group[group.length - 1].n}, about ${Math.round(topic.minutes)} min of transcript; its ` +
        "scenes are being made" + (cursor + group.length < sections.length ? " while the rest is written." : ".") });
    };
    /** The words that close one video and open the next: for the end of its last section and the start of the
     * next one (added by the caller, one after another, so two never write over each other). */
    const transition = async (index: number, group: Section[], next: Section) => {
      const last = [...group].reverse().map((x) => done.get(x.n)).find((w): w is WrittenSection => !!w);
      const first = done.get(next.n);
      if (!last || !first) return null;
      try {
        const result = await completionWithRetry(key, writer, [cachedSystem(prompt, writer), { role: "user", content:
          transitionRequest({ index, minutes: group.reduce((n, x) => n + x.minutes, 0),
            titles: group.map((x) => done.get(x.n)?.title).filter((t): t is string => !!t), tail: last.text },
          { title: first.title, head: first.text }) }], emit, () => {}, [TRANSITION_TOOL], undefined, "required");
        const addedCost = Number(result.usage?.cost ?? 0);
        inputTokens += result.usage?.prompt_tokens ?? 0;
        outputTokens += result.usage?.completion_tokens ?? 0;
        costUsd = ledger.bill("transcript", addedCost, { inputTokens: result.usage?.prompt_tokens ?? 0,
          outputTokens: result.usage?.completion_tokens ?? 0, span: result.span });
        let words = { closing: "", opening: "" };
        for (const call of result.message.tool_calls ?? []) {
          try {
            const args = JSON.parse(call.function.arguments || "{}") as { closing?: string; opening?: string };
            words = { closing: cleanSection(String(args.closing ?? "")), opening: cleanSection(String(args.opening ?? "")) };
          } catch {}
        }
        return { last: last.n, closing: words.closing, first: first.n, opening: words.opening };
      } catch (error) {
        if (error instanceof ProviderAuthError) throw error;     // a refused key is refused again: stop
        if (stopped()) return null;
        emit({ type: "message", role: "status", text: `The words between videos ${index} and ${index + 1} could not be ` +
          `written (${error instanceof Error ? error.message.slice(0, 120) : String(error)}); they meet as the sections do.` });
        return null;
      }
    };
    const addWords = (n: number, words: string, where: "start" | "end") => {
      const w = done.get(n);
      if (!w || !words) return;
      // What the section already says is not said again: an opening that copied the section's first paragraph
      // made it heard twice.
      const fresh = dropRepeats(words, linesOf(w.text)).text.trim();
      if (!fresh || sameParagraph(fresh, where === "start" ? w.text.split(/\n\s*\n/)[0] : w.text.split(/\n\s*\n/).pop() ?? "")) return;
      done.set(n, { ...w, text: where === "end" ? `${w.text}\n\n${fresh}` : `${fresh}\n\n${w.text}` });
    };
    /** A planned lecture's videos (decided before writing), each released once all its sections are in. */
    let nextGroup = 0;
    const releasePlanned = () => {
      while (series && nextGroup < videoGroups.length) {
        const group = videoGroups[nextGroup].map((n) => sections.find((x) => x.n === n)).filter((x): x is Section => !!x);
        if (!group.every((x) => done.has(x.n) || failed.includes(x.n))) return;
        release(group);
        cursor += group.length;
        nextGroup += 1;
      }
    };
    /** Every video the sections written so far decide, in order (one call at a time). */
    const planVideos = () => (planning = planning.then(async () => {
      try {
        if (videoGroups.length) releasePlanned();
        else await decideVideos();
      } catch (error) {
        halted = halted ?? error;
      }
    }));
    const decideVideos = async () => {
      while (series && cursor < sections.length && !halted && !stopped()) {
        const known: Section[] = [];
        for (let i = cursor; i < sections.length; i++) {
          const w = done.get(sections[i].n);
          if (!w && !failed.includes(sections[i].n)) break;
          known.push({ ...sections[i], minutes: w ? spokenMinutes(w.text) : 0 });
        }
        const sizes = nextVideos(known, cursor + known.length < sections.length);
        if (!sizes.length) return;
        const groups: Section[][] = [];
        let at = 0;
        for (const k of sizes) {
          groups.push(known.slice(at, at + k));
          at += k;
        }
        let end = 0;
        const between = await Promise.all(groups.map((group, i) => {
          end += group.length;
          const next = known[end];
          return next ? transition(topics.length + i + 1, group, next) : null;
        }));
        for (const words of between) {
          if (!words) continue;
          addWords(words.last, words.closing, "end");
          addWords(words.first, words.opening, "start");
        }
        for (const group of groups) {
          release(group);
          cursor += group.length;
        }
      }
    };

    let next = 0;
    const worker = async () => {
      while (next < sections.length && !halted && !stopped()) {
        const section = sections[next++];
        try {
          const wrote = await writeOne(section);
          if (wrote) {
            done.set(section.n, wrote);
            if (!series) {
              // One video: its chapters are written now, while the rest of the transcript is (stage 2).
              ready.set(wrote.n, wrote);
              writtenQueue.push(wrote);
            }
          } else {
            failed.push(section.n);
          }
          // (Not waited for: the other sections go on being written while a video's end is decided.)
          if (series) void planVideos();
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
        await planLecture();
        await Promise.all(Array.from({ length: Math.min(PARALLEL, sections.length) }, worker));
      } finally {
        clearInterval(progress);
      }
      if (halted) throw halted;
      if (stopped()) throw new Error("The page closed while the transcript was being written.");
      // The last videos, planned from the whole of what is left.
      await planVideos();
      if (halted) throw halted;
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
      // A section that could not be written leaves its goals untaught.
      const learned = map as LearningMap | null;          // set inside planLecture, which TypeScript does not follow
      if (learned) {
        for (const goal of learned.goals) {
          if (!goalStatus.has(goal.id) && failed.includes(goal.section)) goalStatus.set(goal.id, "missing");
        }
        sendPlan();
      }
      if (map && coverage.planned) {
        emit({ type: "message", role: "status", text: `Coverage: ${coverage.planned - coverage.missing.length} of ` +
          `${coverage.planned} learning goals taught (${coverage.taught} as written` +
          (coverage.patched ? `, ${coverage.patched} written in afterwards` : "") + ")" +
          (coverage.missing.length ? `; not taught: ${coverage.missing.join(", ")}.` : ".") });
      }
      for (const topic of topics) {
        if (!topic.title) topic.title = written.find((w) => w.n === topic.sections[0])?.title ?? "";
      }
    })();
    transcriptDone.then(() => writtenQueue.close(), (error) => writtenQueue.fail(error));
    planned = sections;
  }
  // STAGE 2: the video, whose narration is the transcript sentence for sentence.
  // The book's figures as pictures, for the model to rebuild each one in Manim (it is not shown as it is).
  const waitBegan = Date.now();
  const drawn = await figuresWithin(drawing, figuresReady, drawingStarted, (text) =>
    emit({ type: "message", role: "status", text }));
  ledger.time("waiting", waitBegan, Date.now(), { what: "the script writer waited for the book's figures" });
  mark("figures ready");
  const system = systemBase + (doc ? figurePrompt(doc, drawn) : "") + systemTail;
  // Figures shown as their picture need no look; only those to rebuild in Manim go to the model as pictures.
  const pictures = doc ? await figurePictures(doc, new Set(Object.keys(drawn ?? {}).filter(
    (id) => drawn?.[id]?.photo))) : [];
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
  {
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
          if (["edit_scene", "write_lecture"].includes(call.function.name)) {
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
  // What each compile asked of the image model, in the log once: a failing model is told apart from a script that
  // chose to build its pictures in Manim.
  const imageNotes = new Set<string>();
  const noteImages = (report: ImageReport) => {
    const notes: string[] = [];
    if (!report.asked) {
      notes.push(`Pictures: the script asked the image model (${report.model}) for none here; its pictures are ` +
        "built in Manim.");
    } else {
      notes.push(`Pictures: ${report.asked} asked of the image model (${report.model}` +
        `${report.proxy ? `, through the test proxy ${report.proxy}` : ""}): ${report.made} made now, ` +
        `${report.cached} made before${report.failed.length ? `, ${report.failed.length} FAILED` : ""}.`);
    }
    for (const error of new Set(report.failed.map((f) => f.error))) {
      const what = report.failed.filter((f) => f.error === error).map((f) => f.what).slice(0, 3).join("; ");
      notes.push(`Image model failed (${what}): ${error}`);
    }
    for (const text of notes) {
      if (imageNotes.has(text)) continue;
      imageNotes.add(text);
      emit({ type: "message", role: "status", text });
    }
  };
  const lectureOptions = () => ({
    onGenerated: billGenerated,
    onImages: noteImages,
    onTime: (span: [number, number], images: [number, number][], prefetch?: Prefetch, more?: { phases?: Record<string, number>; calls?: { for: string; who: string; model: string;
      route: string; start: number; end: number; error?: string }[]; source?: string | null; errors?: string[] }) => {
      ledger.time("compile", span[0], span[1], { phases: more?.phases, ok: more?.source !== null,
        errors: more?.errors?.length || undefined });
      for (const [start, end] of images) ledger.time("images", start, end, { quiet: true });
      for (const call of more?.calls ?? []) {
        timing.span(call.who === "image" ? "picture-request" : "picture-check", call.start, call.end,
          { for: call.for, model: call.model, ...(call.error ? { error: call.error } : {}) });
      }
      const status = picturesStatus(prefetch);
      if (status) emit({ type: "message", role: "status", text: status });
    },
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
    if (compiled.source) kept.media?.compiled(compiled.pictures);
    mark(`whole lecture compiled${compiled.source ? "" : " (with faults)"}`);
    return compiled;
  };
  // The compile is the whole check: the video can be drawn (its ops, its Manim, its pictures). What the lecture
  // covers is the transcript's, and every transcript line is put on a beat by fillLines, not refused.
  const compileWholeChecked = (script: unknown) => compileChecked(script, lectureOptions());
  // One part of a long lecture is checked on its own: its ops, captions and copying, not the whole lecture's
  // length or counts.
  // The free-form Manim blocks, by their own model when PANIM_MANIM_MODEL is set (lib/manimcoder.ts): the writer
  // plans each block, the Manim model writes its code (every figure at once) before the compiler runs, and a block
  // the compiler's run refuses goes back to it with the reason, not to the section.
  const coder = manimModel();
  const coderOptions = (): ManimCoderOptions => ({
    key, model: coder!, style, signal: undefined,
    figureFile: (id) => (doc ? teachingFigures(doc).find((f) => f.id === id)?.file : undefined),
    onStatus: (text) => emit({ type: "message", role: "status", text }),
    onCost: (usd, span, tokens, detail) => {
      inputTokens += tokens.in;
      outputTokens += tokens.out;
      costUsd = ledger.bill("manim", usd, { inputTokens: tokens.in, outputTokens: tokens.out, span, items: 1, detail });
      sendCosts(`a Manim figure written by ${coder}: $${usd.toFixed(4)}`);
    },
  });
  // Each section's pictures, made in the background once its chapters pass (makePictures): a compile that shows
  // pictures waits for those of its own sections first, so nothing is asked of the image models twice.
  const pictureJobs = new Map<number, Promise<void>>();
  // Sections' picture jobs at once (PANIM_PICTURE_JOBS, 3; each makes PANIM_IMAGE_PARALLEL pictures at once).
  const JOBS = Math.max(1, Number(process.env.PANIM_PICTURE_JOBS) || 3);
  let jobsRunning = 0;
  const jobQueue: (() => void)[] = [];
  const inTurn = async <T,>(run: () => Promise<T>): Promise<T> => {
    if (jobsRunning >= JOBS) await new Promise<void>((resolve) => jobQueue.push(resolve));
    jobsRunning += 1;
    try {
      return await run();
    } finally {
      jobsRunning -= 1;
      jobQueue.shift()?.();
    }
  };
  const picturesOf = async (script: unknown) => {
    const chapters = script && typeof script === "object" && Array.isArray((script as { chapters?: unknown }).chapters)
      ? (script as { chapters: { section?: unknown }[] }).chapters : [];
    const sections = new Set(chapters.map((c) => Number(c?.section)).filter((n) => Number.isFinite(n)));
    const waiting = [...pictureJobs].filter(([n]) => !sections.size || sections.has(n)).map(([, job]) => job);
    if (waiting.length) await Promise.all(waiting);
  };
  const compileChecked = async (script: unknown, options: Parameters<typeof compileLecture>[1],
    phase: (what: string) => void = () => {}) => {
    // Each compile says when it waits for its turn and when it runs (the status of a section being checked).
    const compile = (scriptNow: unknown) => {
      phase("waiting for a compile slot");
      return compileLecture(scriptNow, { ...options, onStart: () => phase("compiling") });
    };
    if (!options?.withoutPictures) await picturesOf(script);
    // The small built drawings (presets, sketch, graph, sims...) are gone: any the writer still used is
    // drawn as free-form Manim instead, by the Manim model (lecture.ts FREE_DRAWN_OPS).
    if (coder && script && typeof script === "object") {
      const turned = freeDrawings(script as Record<string, unknown>);
      if (turned) {
        emit({ type: "message", role: "status", text: `Manim: ${turned} built drawing${turned > 1 ? "s" : ""} ` +
          "turned into free-form Manim (the built ones are gone)." });
      }
    }
    // The map's places the gazetteers do not know, found by the map agent (lib/mapagent.ts) before the compile
    // checks them: a strait's shoals, a climate zone, a country's own name for its highlands.
    if (script && typeof script === "object") {
      phase("finding the map's places");
      const started = Date.now();
      const map = await resolvePlaces(script as Record<string, unknown>);
      if (map && (map.asked.length || map.errors.length)) {
        if (map.usd) {
          costUsd = ledger.bill("map", map.usd, { items: Object.keys(map.resolved).length, span: [started, Date.now()],
            detail: { model: map.model, asked: map.asked } });
          sendCosts(`the map's places found by ${map.model}: $${map.usd.toFixed(4)}`);
        }
        emit({ type: "message", role: "status", text: `Map: ${map.summary ?? map.errors.join(" | ")}` });
      }
    }
    if (!coder || !script || typeof script !== "object" || !needsManim(script) && !hasManim(script)) {
      return compile(script);
    }
    const own = script as Record<string, unknown>;
    if (needsManim(own)) {
      phase("the Manim model writing its figures");
      await fillManim(own, coderOptions());
    }
    let compiled = await compile(own);
    for (let round = 0; round < 2 && !compiled.source; round++) {
      phase("the Manim model repairing figures the compile refused");
      if (!(await repairManim(own, compiled.errors, coderOptions()))) break;
      compiled = await compile(own);
    }
    return compiled;
  };
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
  const size = (chars: number) => (chars >= 1024 ? `about ${Math.round(chars / 1024)} KB` : `${chars} characters`);

  /** A section's chapters as a script of their own, checked as a part is: null when they pass, else what is wrong. */
  /**
   * Where a section's chapters stand in their video, in a series (its videos decided from the transcript,
   * topics.ts): the video's recap goes with its last section. Without a series, the last section has the recap.
   */
  const seriesDuties = (n: number, lastOfAll: boolean): string[] => {
    const topic = series ? topics.find((t) => t.sections.includes(n)) : undefined;
    if (!topic) return [lastOfAll ? "This is the last section: end the script with the recap." : "No recap: the last section has it."];
    const out: string[] = [];
    if (topic.sections[0] === n) {
      out.push(`This section OPENS video ${topic.index}${topic.title ? ` ("${topic.title}")` : ""}, watched on its own: ` +
        "its transcript begins with that video's opening words.");
    }
    if (topic.sections[topic.sections.length - 1] === n) {
      out.push(`This section CLOSES video ${topic.index}: its transcript ends with the video's closing words. End the ` +
        "script with \"recap\": [[head, body], ...], the key points of THIS video only.");
    } else {
      out.push("No recap: the last section of this video has it.");
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
  const checkSection = async (script: Record<string, unknown>, n: number, dropFailing = false,
    phase: (what: string) => void = () => {}) => {
    const chapters = (Array.isArray(script.chapters) ? script.chapters : [])
      .filter((c) => c && typeof c === "object")
      .map((c) => ({ ...(c as Record<string, unknown>), section: n }));
    if (!chapters.length) return { script, errors: ["The script has no chapters."], compiles: false, dropped: 0 };
    const own: Record<string, unknown> = { ...script, title: script.title || `Section ${n}`, chapters };
    const section = ready.get(n) ?? written.find((w) => w.n === n);
    const filled = section ? fillLines(own, [section], { complete: [n], minBeats: partBeats }) : { problems: [], added: 0, merged: 0 };
    // Checked without its pictures: the image models' minutes no longer hold this section's writing slot.
    let compiled = await compileChecked(own, { ...partOptions(), withoutPictures: true }, phase);
    let dropped = 0;
    if (!compiled.source && dropFailing) {
      dropped = dropOps(own, compiled.errors);
      if (dropped) compiled = await compileChecked(own, { ...partOptions(), withoutPictures: true }, phase);
    }
    const errors = [...filled.problems, ...(compiled.source ? [] : compiled.errors)];
    const repeated = "repeated" in filled ? filled.repeated ?? 0 : 0;
    if (!errors.length && (filled.added || filled.merged || dropped || repeated)) {
      emit({ type: "message", role: "status", text: `Video: section ${n}: ` + [
        repeated ? `${repeated} transcript line${repeated > 1 ? "s" : ""} named by a second beat, said once` : "",
        filled.added ? `${filled.added} transcript line${filled.added > 1 ? "s" : ""} no beat named, said on beats of their own` : "",
        filled.merged ? `${filled.merged} thin chapter${filled.merged > 1 ? "s" : ""} merged into a neighbouring one` : "",
        dropped ? `the ops of ${dropped} beat${dropped > 1 ? "s" : ""} that would not compile left out` : "",
      ].filter(Boolean).join("; ") + "." });
    }
    // Its lines are final unless it is sent back: speak them now, while the other sections are written; and its
    // pictures are made in the background, for the compiles of the lecture and its parts to find made.
    if (!errors.length && compiled.source && !usingFixture()) {
      speakAhead(compiled.source);
      const copy = JSON.parse(JSON.stringify(own));
      pictureJobs.set(n, inTurn(() => makePictures(copy, partOptions())));
    }
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
    const PARALLEL = Math.max(1, Math.min(16, Number(process.env.PANIM_CHAPTERS_PARALLEL) ||
      Number(process.env.PANIM_TRANSCRIPT_PARALLEL) || 10));
    const TRIES = 4;          // refused or failed replies before a section is given up
    const TURNS = 8;          // replies in all, the picture searches among them
    const done = new Map<number, Record<string, unknown>>();
    const missing: number[] = [];
    const live = new Map<number, { started: number; chars: number; attempt: number; thinking: boolean;
      checking?: number; phase?: string }>();
    // A section's tries, their checks among them, end after this long (PANIM_SECTION_MINUTES): the best one that
    // compiled is kept, else the section is left out with a note, instead of the lecture waiting on it for hours.
    const SECTION_MS = Math.max(5, Number(process.env.PANIM_SECTION_MINUTES) || 25) * 60_000;
    const sectionTools: ToolSpec[] = [LECTURE_TOOL];
    emit({ type: "message", role: "status", text: notes.size
      ? `Video: writing again the chapters of section${notes.size > 1 ? "s" : ""} ${[...notes.keys()].join(", ")}, ` +
        "with what the whole lecture's check found."
      : `Video: writing the chapters of the ${total} sections, ${Math.min(PARALLEL, total)} at a time, each as soon as ` +
        "its transcript is written." });
    const progress = setInterval(() => {
      if (!live.size) return;
      const now = Date.now();
      const parts = [...live.entries()].sort((x, y) => x[0] - y[0]).map(([n, p]) =>
        `${n} (${clock(now - p.started)}, ${p.checking ? `checking for ${clock(now - p.checking)}: ${p.phase ?? "starting"}`
          : p.chars ? size(p.chars) : p.thinking ? "thinking" : "waiting"}` +
        `${p.attempt > 1 ? `, try ${p.attempt}` : ""})`);
      emit({ type: "message", role: "status",
        text: `Video: ${done.size} of ${total} sections' chapters written; writing ${parts.join(", ")}` });
    }, 10_000);

    // One try's check (its Manim figures written, then compiled) ends after this long (PANIM_CHECK_MINUTES), or at
    // the section's own deadline: whatever it waits on, the section goes on (asked again, or kept as it stands).
    const CHECK_MS = Math.max(2, Number(process.env.PANIM_CHECK_MINUTES) || 12) * 60_000;
    /** A try's check, shown as checking rather than as the size it sent, and never longer than CHECK_MS. */
    const checking = async (state: { checking?: number; phase?: string }, until: number, script: Record<string, unknown>, n: number,
      dropFailing: boolean) => {
      state.checking = Date.now();
      const limit = Math.max(30_000, Math.min(CHECK_MS, until - Date.now()));
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        return await Promise.race([
          checkSection(script, n, dropFailing, (what) => {
            if (state.checking) state.phase = what;
          }),
          new Promise<Awaited<ReturnType<typeof checkSection>> & { timedOut: true }>((resolve) => {
            timer = setTimeout(() => resolve({ script, compiles: false, dropped: 0, timedOut: true, errors: [
              `Checking these chapters (their Manim figures, then the compile) took over ${clock(limit)}. Write them ` +
              "again more simply: fewer and smaller manim figures."] }), limit);
          }),
        ]);
      } finally {
        clearTimeout(timer);
        state.checking = undefined;
        state.phase = undefined;
      }
    };

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
        ...(storyCues.has(section.n) ? ["", ...storyCues.get(section.n)!, ""] : []),
        ...(request.preview ? ["PREVIEW: this short lecture shows how the whole one will look. Include, where the " +
          "content allows, one chapter on the map and one with a diagram, besides the pictures, so each kind can be " +
          "judged."] : []),
        ...(() => {
          // What the other sections' chapters (written so far) already put on screen: build on it, do not redraw it.
          const shown = shownSoFar(done, section.n);
          return shown.length ? ["", ...shown, ""] : [];
        })(),
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
      // Tries that sent nothing at all: the next is asked at low effort, the silent thinking being what hangs.
      let silent = 0;
      // Refused once for ops that would not compile: the next try's failing ops are left out instead.
      let opsRefused = false;
      // The longest try that compiles, kept when every try is refused, so one stubborn section does not lose the
      // lecture: the whole lecture's check names what it lacks, and that is fixed afterwards.
      let fallback: Record<string, unknown> | null = null;
      const began = Date.now();
      const until = began + SECTION_MS;
      for (let turn = 0; turn < TURNS && refused < TRIES; turn++) {
        if (stopped()) return null;
        if (turn > 0 && Date.now() > until) {
          emit({ type: "message", role: "status", text: `Video: section ${section.n} has taken over ` +
            `${Math.round(SECTION_MS / 60_000)} minutes (${refused} tries); ` +
            (fallback ? "its best try that compiles is kept." : "it is left out, and the lecture goes on.") });
          break;
        }
        const state: { started: number; chars: number; attempt: number; thinking: boolean; checking?: number;
          phase?: string } =
          { started: Date.now(), chars: 0, attempt: refused + 1, thinking: false };
        live.set(section.n, state);
        const abort = new AbortController();
        let why: "silent" | "stalled" | "deadline" | null = null;
        let lastDelta = 0;
        const watch = setInterval(() => {
          const now = Date.now();
          if (now > until) why = "deadline";
          else if (!lastDelta && now - state.started > VIDEO_WAIT_MS) why = "silent";
          else if (lastDelta && now - lastDelta > STALL_MS) why = "stalled";
          if (why) abort.abort();
        }, 5000);
        let result;
        try {
          result = await completionWithRetry(key, model, talk, emit, (kind, text) => {
            lastDelta = Date.now();
            if (kind === "thinking") state.thinking = true;
            else state.chars += text.length;
          }, sectionTools, abort.signal, "required", silent ? "low" : videoEffort());
        } catch (error) {
          if (error instanceof ProviderAuthError) throw error;     // a refused key is refused again: stop
          if (stopped()) return null;
          lostTry(state.started, { step: "chapters", section: section.n, why: why ?? String(error).slice(0, 120) });
          refused += 1;
          if (why === "silent") silent += 1;
          const note = why === "silent" ? `sent nothing for ${Math.round(VIDEO_WAIT_MS / 60_000)} minutes` +
              ` (asked again at low effort)`
            : why === "stalled" ? `stopped streaming partway (nothing for ${Math.round(STALL_MS / 1000)} s)`
              : why === "deadline" ? `was cut off: the section's ${Math.round(SECTION_MS / 60_000)} minutes are up`
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
        costUsd = ledger.bill("script", addedCost, { inputTokens: addedIn, outputTokens: addedOut, span: result.span,
          detail: { section: section.n, try: refused + 1, model } });
        sendCosts(`video section ${section.n}: ${addedIn} in, ${addedOut} out, $${addedCost.toFixed(4)}`);
        const calls = result.message.tool_calls ?? [];
        if (!calls.length) {
          // A script put in the reply text instead of the tool call is taken as if it had been sent with the tool.
          const typed = scriptFromText(result.message.content ?? "");
          if (typed) {
            const checked = await checking(state, until, typed, section.n, opsRefused);
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
              const checked = await checking(state, until, args.script as Record<string, unknown>, section.n, opsRefused);
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
          } else {
            output = "Only write_lecture is available here: pictures are asked for in the script (generate, draw) " +
              "or built in Manim.";
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
    const compiled = logFixed(await compileChecked(part, partOptions()));
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
    return { compiled, errors };
  };

  const finishTopic = async (k: number, bySection: Map<number, Record<string, unknown>>, missing: number[]) => {
    const topic = topics[k];
    const label = `Lecture ${k + 1}`;
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
      if (dropOps(part.script, compiled.errors)) compiled = await compileChecked(part.script, partOptions());
    }
    if (!compiled.source) {
      emit({ type: "message", role: "status", text: `${label} ("${topic.title}") could not be made: ${compiled.errors.slice(0, 2).join("; ")}` });
      return;
    }
    const left = [...checked.errors.values()].flat();
    const done = { index: k + 1, of: topics.length, title: part.title, minutes: compiled.minutes ?? 0, source: sanitizeScene(compiled.source) };
    finished.set(k, done);
    kept.media?.compiled(compiled.pictures, { index: k + 1, title: part.title });
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

  if (series && !scene) {
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
      source: parts.length === topics.length ? p.source : p.source.replace(/· Lecture \d+/, `· Lecture ${i + 1}`) }));
    emit({ type: "message", role: "status", text: `The series is written: ${series.length} micro-lectures ` +
      `(${series.map((p) => `${p.title}, ${Math.round(p.minutes)} min`).join("; ")}).` });
    return { source: series[0].source, parts: series, sceneClass: SCENE_CLASS, model, inputTokens, outputTokens, costUsd };
  }
  if (planned.length >= 2 && !scene) {
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
      const partsOk = (await compileChecked(script, partOptions())).source;
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
    slimHistory();
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
      if (error instanceof ProviderAuthError) throw error;     // a refused key is refused again: stop
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
        const partial = draft ? await compileChecked(draft, partOptions()) : null;
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
          "That reply timed out before the file was saved. Nothing was written. Call write_lecture again with a shorter script.",
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
    costUsd = ledger.bill("fixes", addedCost, { inputTokens: addedIn, outputTokens: addedOut,
      span: result.span });
    sendCosts(`turn ${turn + 1}: ${addedIn} in, ${addedOut} out, $${addedCost.toFixed(4)}`);

    const text = result.message.content?.trim() ?? "";
    const calls = result.message.tool_calls ?? [];
    if (calls.length === 0 && !/from manim import/.test(scene)) {
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
      const partial = await compileChecked(draft, partOptions());
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
        const compiled = chapterCount(first) === 0
          ? { source: null, errors: ["Part 1 has no chapters. Send it again with its chapters."], minutes: 0, warnings: [] }
          : await compileChecked(first, partOptions());
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
          const compiled = args.done ? await compileWhole(next) : logFixed(await compileChecked(next, partOptions()));
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
            const partsOk = (await compileChecked(next, partOptions())).source;
            if (partsOk) draft = next;
            if (partsOk) wholeRefused += 1;
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
      } else {
        const edited = applySceneTool(scene, call.function.name, args);
        output = edited ? edited.message : await runTool(call.function.name);
        if (edited) scene = edited.source;
      }
      emit({ type: "tool_result", name: call.function.name, text: output });
      messages.push({ role: "tool", tool_call_id: call.id, content: output });
    }
    if (draft && wholeRefused >= WHOLE_TRIES && !/from manim import/.test(scene)) {
      // A complete lecture whose whole-lecture checks still fail after several rounds of fixing: its chapters all
      // compile, so it is built (the checks named in the log), rather than turning for another hour.
      const built = await compileChecked(draft, partOptions());
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
    const partial = await compileChecked(draft, partOptions());
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
  return lectureFixture(request, templateById(request.templateId), emit, kept);
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
  return !process.env.OPENROUTER_API_KEY && !process.env.OPENAI_API_KEY;
}

/**
 * Generate a scene or a lecture. Each run is kept in Supabase by default (lib/media.ts): what it was asked, every
 * picture it made or used with its context, each video's source, and how it ended.
 */
export async function generate(
  request: GenerateRequest,
  emit: (event: AgentEvent) => void = () => {},
  stopped: () => boolean = () => false,
): Promise<Generated> {
  await ensurePrices();             // OpenAI's prices, so its requests are costed (providers.ts)
  const media = new MediaLog(request.generationId ?? `run-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
    (text) => emit({ type: "message", role: "status", text }));
  media.describe({
    title: request.content.trim().split("\n")[0]?.slice(0, 200) || undefined,
    template: request.templateId, model: videoModel(), transcript_model: transcriptModel(request.transcriptModel),
    svg_model: svgModel(request.svgModel), subject: request.subject, language: request.language, art: request.art,
    minutes: request.minutes,
    request: { content: request.content.slice(0, 20_000), documentId: request.documentId, referenceId: request.referenceId,
      instruction: request.instruction, edit: !!request.previousSource },
  });
  const watched = (event: AgentEvent) => {
    if (event.type === "picture" && event.picture) media.picture(mediaItem(event.picture));
    if (event.type === "part" && event.part) {
      media.scenes([{ part: event.part.index, title: event.part.title, minutes: event.part.minutes, source: event.part.source }]);
    }
    emit(event);
  };
  try {
    const result = await generateOnce(request, watched, stopped, media);
    const videos = result.parts?.length ? result.parts : [{ title: "", minutes: undefined, source: result.source }];
    media.scenes(videos.map((v, k) => ({ part: k + 1, title: v.title || undefined, minutes: v.minutes, source: v.source })));
    media.finish({ state: "finished", videos: videos.length, cost_usd: result.costUsd,
      minutes: result.parts?.reduce((n, p) => n + (p.minutes ?? 0), 0) || undefined });
    return result;
  } catch (error) {
    media.finish({ state: stopped() ? "stopped" : "failed", error: error instanceof Error ? error.message : String(error) });
    throw error;
  }
}

/** A picture the page is shown (AiPicture) as what is kept of it: what it is, what it shows, how it was used. */
function mediaItem(p: AiPicture): MediaItem {
  const base = { file: p.file, description: p.title, usd: p.usd, reused: p.reused, context: p.context };
  if (p.kind === "drawing") {
    return { ...base, kind: "drawing", role: "a detailed diagram made by the diagram model", metadata: { parts: p.detail } };
  }
  if (p.kind === "figure") {
    return { ...base, kind: "figure", role: "book figure redrawn by the diagram model", metadata: { status: p.status } };
  }
  if (p.kind === "photo") {
    const remade = /image model, like it/.test(p.status ?? "");
    return { ...base, kind: remade ? "photo" : "book-photo",
      role: remade ? "a book photograph made again by the image model" : "book photograph shown as it is",
      metadata: { found_by: p.detail, status: p.status } };
  }
  if (p.kind === "rebuilt") {
    return { ...base, kind: "book-figure", role: "book figure, built in Manim instead", metadata: { status: p.status } };
  }
  return { ...base, kind: "illustration", role: "drawn by an image model", metadata: { model: p.detail } };
}

async function generateOnce(
  request: GenerateRequest,
  emit: (event: AgentEvent) => void,
  stopped: () => boolean,
  media: MediaLog,
): Promise<Generated> {
  const kept: Kept = { media };
  const startedAt = Date.now();
  let result: Generated;
  try {
    result = usingFixture() ? await viaFixture(request, emit, kept) : await viaOpenRouter(request, emit, stopped, kept);
  } finally {
    // Where the time went, from the timing log (lib/timing.ts): each kind of step, then the slowest steps.
    if (kept.timing?.events.length) {
      const lines = kept.timing.summary(12);
      emit({ type: "message", role: "status", text: `Timing (${kept.timing.file}):\n${lines.join("\n")}` });
      console.log(`[timing] ${kept.timing.file}\n${lines.join("\n")}`);
    }
  }
  // A long lecture as videos of 25-30 min: cut where its videos meet when it was written as a series (their ends
  // decided from the transcript, topics.ts). A lecture written from a transcript is never cut otherwise; one
  // without (an edit by hand) is cut between chapters once it runs past PANIM_MAX_VIDEO_MINUTES (lib/parts.ts).
  if (kept.script && kept.options && kept.source === result.source && kept.minutes) {
    const script = kept.script as Record<string, unknown>;
    const byTopic = splitByTopics(script, kept.minutes);
    const fromTranscript = sectionsOf(script).length > 0;
    let parts: LecturePart[] = byTopic.length ? byTopic : fromTranscript ? [] : splitLecture(script, kept.minutes);
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
  // A lecture's look belongs to the engine: its style sets the background on import.
  result.source = sanitizeScene(result.source);
  if (!usingFixture()) {
    // The compiler wrote it: a file that does not parse is the compiler's fault, said as it is.
    const broken = await syntaxError(result.source);
    if (broken) throw new Error(`the compiled lecture is not valid Python: ${broken}`);
  }
  const named = (kept.script as { title?: unknown } | undefined)?.title;
  if (named) media.describe({ title: String(named).slice(0, 300) });
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
