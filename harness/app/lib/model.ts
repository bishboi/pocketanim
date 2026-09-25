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
import { Template, explainWith, filmBrief, isLecture, layoutContract, templateById } from "./templates";
import { LECTURE_TOOL, compileLecture, fixtureScript, lecturePrompt, resolveRegion } from "./lecture";
import { python } from "./pocketanim";
import { AgentEvent, TOOLS, applySceneTool, findMap, moleculeGuide, runTool } from "./agent";

export type Generated = {
  source: string;
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
};

const SCENE_CLASS = "GeneratedScene";

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
    "A map from find_map may use the cartopy scene that tool returns.",
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
  return ["Write a narrated lecture on the following content with write_lecture.", "", request.content].join("\n");
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

/** Seconds of narration already written, from the waits that follow # voice: lines. */
function voiceSeconds(source: string): number {
  const waits = source.matchAll(/# voice:.*\n[ \t]*self\.wait\(([0-9.]+)\)/g);
  let total = 0;
  for (const wait of waits) total += Number(wait[1]) || 0;
  return total;
}

type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
  tool_calls?: { id: string; type: "function"; function: { name: string; arguments: string } }[];
  tool_call_id?: string;
};

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

function isEmptyReply(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.includes("empty message") || message.includes("returned no message");
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

type ToolSpec = (typeof TOOLS)[number] | typeof LECTURE_TOOL;

async function streamCompletion(
  key: string,
  model: string,
  messages: ChatMessage[],
  onDelta: (kind: "thinking" | "assistant", text: string) => void,
  tools: ToolSpec[] = TOOLS,
): Promise<{ message: ChatMessage; usage?: Usage; finishReason: string }> {
  const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      messages,
      tools,
      tool_choice: "auto",
      stream: true,
      usage: { include: true },
      reasoning: { effort: "low" },
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
        if (tool === "write_scene" || tool === "edit_scene" || tool === "write_lecture") deltas.push("assistant", args);
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

const EMPTY_RETRIES = 3;

async function completionWithRetry(
  key: string,
  model: string,
  messages: ChatMessage[],
  emit: (event: AgentEvent) => void,
  onDelta: (kind: "thinking" | "assistant", text: string) => void,
  tools: ToolSpec[] = TOOLS,
): Promise<{ message: ChatMessage; usage?: Usage }> {
  for (let attempt = 1; attempt <= EMPTY_RETRIES; attempt++) {
    try {
      const result = await streamCompletion(key, model, messages, onDelta, tools);
      const text = result.message.content?.trim() ?? "";
      const calls = result.message.tool_calls ?? [];
      if (!text && calls.length === 0) {
        const why = result.finishReason ? ` (${result.finishReason})` : "";
        throw new Error(`OpenRouter returned an empty message${why}`);
      }
      return result;
    } catch (error) {
      if (!isEmptyReply(error) || attempt === EMPTY_RETRIES) throw error;
      emit({
        type: "message",
        role: "status",
        text: `OpenRouter returned an empty message. Retrying (${attempt + 1} of ${EMPTY_RETRIES})…`,
      });
      await new Promise((resolve) => setTimeout(resolve, 800 * attempt));
    }
  }
  throw new Error("OpenRouter returned an empty message");
}

async function viaOpenRouter(
  request: GenerateRequest,
  emit: (event: AgentEvent) => void,
  stopped: () => boolean = () => false,
): Promise<Generated> {
  const key = process.env.OPENROUTER_API_KEY!;
  const model = process.env.OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4.5";
  const template = templateById(request.templateId);
  const lecture = isLecture(template);
  const system = lecture ? lecturePrompt(template) : systemPrompt(template);
  const user = lecture ? lectureUserPrompt(request) : userPrompt(request);
  const EDIT_TOOL = TOOLS.find((tool) => tool.function.name === "edit_scene")!;
  const tools: ToolSpec[] = lecture ? [LECTURE_TOOL, EDIT_TOOL] : TOOLS;
  const messages: ChatMessage[] = [
    { role: "system", content: system },
    { role: "user", content: user },
  ];
  emit({ type: "input", role: "system", text: system });
  emit({ type: "input", role: "user", text: user });
  let scene = request.previousSource ?? "";
  let inputTokens = 0;

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
      if (messages[i].role === "user" && messages[i].content?.startsWith("CURRENT SCENE")) messages.splice(i, 1);
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
  let outputTokens = 0;
  let costUsd = 0;

  for (let turn = 0; turn < 40; turn++) {
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
    emit({
      type: "message",
      role: "status",
      text: `Turn ${turn + 1}: waiting for ${model}`,
    });
    let sawDelta = false;
    let lastDelta = Date.now();
    const waiting = setInterval(() => {
      const quiet = Date.now() - lastDelta;
      if (!sawDelta) {
        emit({
          type: "message",
          role: "status",
          text: `Turn ${turn + 1}: still waiting for ${model}`,
        });
      } else if (quiet > 12000) {
        emit({
          type: "message",
          role: "status",
          text: `Turn ${turn + 1}: still writing the next beat`,
        });
      }
    }, 8000);
    let result: { message: ChatMessage; usage?: Usage };
    try {
      result = await completionWithRetry(key, model, messages, emit, (kind, text) => {
        sawDelta = true;
        lastDelta = Date.now();
        emit({ type: "delta", role: kind === "thinking" ? "thinking" : "assistant", text });
      }, tools);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
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
    }
    const addedIn = result.usage?.prompt_tokens ?? 0;
    const addedOut = result.usage?.completion_tokens ?? 0;
    const addedCost = Number(result.usage?.cost ?? 0);
    inputTokens += addedIn;
    outputTokens += addedOut;
    costUsd += addedCost;
    emit({
      type: "usage",
      text: `turn ${turn + 1}: ${addedIn} in, ${addedOut} out, $${addedCost.toFixed(4)}`,
      inputTokens,
      outputTokens,
      costUsd,
    });

    const text = result.message.content?.trim() ?? "";
    const calls = result.message.tool_calls ?? [];
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
      } = {};
      try {
        args = JSON.parse(call.function.arguments || "{}");
      } catch {
        args = {};
      }
      emit({ type: "tool_call", name: call.function.name, args: call.function.arguments });
      let output: string;
      if (call.function.name === "write_lecture") {
        const compiled = await compileLecture(args.script ?? {});
        if (compiled.source) {
          scene = compiled.source;
          output = [
            `Compiled the lecture (${compiled.source.split("\n").length} lines of Manim).`,
            ...compiled.warnings.map((w) => `warning: ${w}`),
            compiled.warnings.length ? "Fix the warnings with another write_lecture if they matter; otherwise stop." : "Stop calling tools and reply in one sentence.",
          ].join("\n");
        } else {
          output = ["The script did not compile. Fix these and call write_lecture again:", ...compiled.errors].join("\n");
        }
      } else {
        const edited = applySceneTool(scene, call.function.name, args);
        output = edited ? edited.message : await runTool(call.function.name, args);
        if (edited) scene = edited.source;
      }
      emit({ type: "tool_result", name: call.function.name, text: output });
      messages.push({ role: "tool", tool_call_id: call.id, content: output });
    }
  }
  const done = savedScene();
  if (done) return done;
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
): Promise<Generated> {
  const template = templateById(request.templateId);
  if (isLecture(template)) return lectureFixture(request, template, emit);
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
): Promise<Generated> {
  emit({ type: "input", role: "user", text: lectureUserPrompt(request) });
  emit({ type: "message", role: "assistant", text: "Offline agent. No model tokens." });
  const region = await resolveRegion(request.content);
  emit({ type: "message", role: "status", text: region ? `Map: ${region.state ?? region.country}` : "No place named; a lecture without a map." });
  const script = fixtureScript(request.content, template, region, request.instruction);
  const args = JSON.stringify({ script });
  emit({ type: "tool_call", name: "write_lecture", args: args.length > 1600 ? `${args.slice(0, 1600)}…` : args });
  const compiled = await compileLecture(script);
  if (!compiled.source) throw new Error(`The beat script did not compile:\n${compiled.errors.join("\n")}`);
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
  const result = usingFixture() ? await viaFixture(request, emit) : await viaOpenRouter(request, emit, stopped);
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
      const model = process.env.OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4.5";
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
      const text = repaired.message.content?.trim() ?? "";
      if (!text) throw new Error(broken);
      result.source = exposeMapProject(sanitizeScene(enforceStyle(extractScene(text), template)));
      const still = await syntaxError(result.source);
      if (still) throw new Error(still);
    }
  }
  emit({
    type: "done",
    source: result.source,
    model: result.model,
    inputTokens: result.inputTokens,
    outputTokens: result.outputTokens,
    costUsd: result.costUsd,
  });
  return result;
}
