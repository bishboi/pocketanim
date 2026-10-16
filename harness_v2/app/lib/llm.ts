/**
 * One model call, recorded whole: the prompt as its parts, the tool, every attempt, the reply, the tokens and what
 * it cost (OpenRouter's own figure, usage.cost). The flow (run.ts) adds what its checks found.
 *
 * Without OPENROUTER_API_KEY, or for a model named "fixture", the call is answered by the step's own stand-in
 * (`fake`), so the whole flow and the page can be tried with no key and no network; its cost is 0.
 */

import { render, type Prompt } from "./prompts/parts";
import type { Call } from "./types";

const URL_ = process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions";
const TRIES = 3;
const TIMEOUT_MS = Math.max(60, Number(process.env.V2_CALL_TIMEOUT_SECONDS) || 480) * 1000;

type Tool = { type: "function"; function: { name: string; description: string; parameters: unknown } };

export function usingFixture(model: string): boolean {
  return !process.env.OPENROUTER_API_KEY || model.startsWith("fixture");
}

/** The request body exactly as it is sent (also shown on the page). */
export function requestBody(model: string, prompt: Prompt, tool: Tool, effort?: string, images: string[] = []): Record<string, unknown> {
  const user = images.length
    ? [{ type: "text", text: render(prompt.user) }, ...images.map((url) => ({ type: "image_url", image_url: { url } }))]
    : render(prompt.user);
  return {
    model,
    messages: [{ role: "system", content: render(prompt.system) }, { role: "user", content: user }],
    tools: [tool],
    tool_choice: { type: "function", function: { name: tool.function.name } },
    usage: { include: true },
    ...(effort && effort !== "off" ? { reasoning: { effort } } : {}),
  };
}

export async function callTool(o: {
  call: Call;
  tool: Tool;
  fake: () => Record<string, unknown>;
  onChange: () => void;
  /** Pictures sent with the user message (data URLs). */
  images?: string[];
}): Promise<Record<string, unknown> | null> {
  const { call, tool } = o;
  call.tool = tool;
  call.provider = usingFixture(call.model) ? "fixture" : "openrouter";
  for (let attempt = 1; attempt <= TRIES; attempt++) {
    const began = Date.now();
    try {
      const args = call.provider === "fixture" ? await fixture(o.fake) : await real(call, tool, o.images);
      call.attempts.push({ started: began, ended: Date.now() });
      call.output = args ?? undefined;
      call.status = "done";
      call.ended = Date.now();
      if (call.provider === "fixture") {
        // Tokens counted as a provider would, roughly (4 characters a token), so the page's numbers mean something.
        const input = Math.round((render(call.prompt.system).length + render(call.prompt.user).length) / 4);
        call.usage = { input, output: Math.round(JSON.stringify(args ?? {}).length / 4) };
      }
      o.onChange();
      return args;
    } catch (error) {
      call.attempts.push({ started: began, ended: Date.now(), error: (error as Error).message.slice(0, 400) });
      o.onChange();
      if (/\b(401|403)\b/.test((error as Error).message)) break;     // a refused key is refused again
    }
  }
  call.status = "failed";
  call.ended = Date.now();
  call.error = call.attempts[call.attempts.length - 1]?.error;
  o.onChange();
  return null;
}

async function fixture(fake: () => Record<string, unknown>): Promise<Record<string, unknown>> {
  await new Promise((r) => setTimeout(r, 300 + Math.random() * 900));
  return fake();
}

async function real(call: Call, tool: Tool, images: string[] = []): Promise<Record<string, unknown> | null> {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(URL_, {
      method: "POST",
      signal: abort.signal,
      headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json",
        "X-Title": "pocketanim harness v2" },
      body: JSON.stringify(requestBody(call.model, call.prompt, tool, call.effort, images)),
    });
    const body = await response.text();
    if (!response.ok) throw new Error(`${response.status} ${body.slice(0, 300)}`);
    const json = JSON.parse(body) as {
      choices?: { message?: { content?: string | null; tool_calls?: { function?: { name?: string; arguments?: string } }[] } }[];
      usage?: { prompt_tokens?: number; completion_tokens?: number; cost?: number;
        prompt_tokens_details?: { cached_tokens?: number }; completion_tokens_details?: { reasoning_tokens?: number } };
      error?: { message?: string };
    };
    if (json.error) throw new Error(json.error.message ?? "provider error");
    const u = json.usage ?? {};
    call.usage = { input: u.prompt_tokens ?? 0, output: u.completion_tokens ?? 0,
      cached: u.prompt_tokens_details?.cached_tokens, reasoning: u.completion_tokens_details?.reasoning_tokens };
    call.cost += Number(u.cost ?? 0);
    const message = json.choices?.[0]?.message;
    call.text = message?.content ?? undefined;
    // The longest call of the tool asked for (a model may call it twice).
    let best: Record<string, unknown> | null = null;
    let size = -1;
    for (const c of message?.tool_calls ?? []) {
      if (c.function?.name !== tool.function.name) continue;
      try {
        const args = JSON.parse(c.function.arguments || "{}");
        if ((c.function.arguments ?? "").length > size) {
          best = args;
          size = (c.function.arguments ?? "").length;
        }
      } catch {}
    }
    if (!best && !message?.content) throw new Error("the reply was empty");
    return best;
  } finally {
    clearTimeout(timer);
  }
}

/** A model's prices (US dollars per million tokens) from OpenRouter's public list, and whether a tiny call works. */
export async function checkModel(model: string, kind: "text" | "vision" | "image" = "text"): Promise<{ ok: boolean; seconds: number;
  cost: number; reply?: string; error?: string; prices?: { input: number; output: number }; context?: number; fixture?: boolean;
  outputs?: string[] }> {
  const began = Date.now();
  let prices: { input: number; output: number } | undefined;
  let context: number | undefined;
  let outputs: string[] | undefined;
  try {
    const list = await fetch("https://openrouter.ai/api/v1/models", { signal: AbortSignal.timeout(15000) });
    const data = (await list.json()) as { data?: { id: string; context_length?: number; pricing?: { prompt?: string; completion?: string } }[] };
    const found = (data.data as { id: string; context_length?: number; pricing?: { prompt?: string; completion?: string };
      architecture?: { output_modalities?: string[] } }[] | undefined)?.find((m) => m.id === model);
    outputs = found?.architecture?.output_modalities;
    if (found?.pricing) prices = { input: Number(found.pricing.prompt) * 1e6, output: Number(found.pricing.completion) * 1e6 };
    context = found?.context_length;
  } catch {}
  if (usingFixture(model)) {
    return { ok: true, seconds: 0, cost: 0, fixture: true, prices, context, outputs,
      reply: process.env.OPENROUTER_API_KEY ? "fixture model: answered by the offline stand-in" : "no OPENROUTER_API_KEY: calls use the offline stand-in" };
  }
  try {
    const response = await fetch(URL_, {
      method: "POST",
      signal: AbortSignal.timeout(60000),
      headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json" },
      // An image model is asked for a picture (and passes only if one comes back); the others for one word.
      body: JSON.stringify(kind === "image"
        ? { model, messages: [{ role: "user", content: "Draw a small red circle on a white background." }], modalities: ["image", "text"],
          usage: { include: true } }
        : { model, messages: [{ role: "user", content: "Reply with the one word: ready" }], max_tokens: 400, usage: { include: true } }),
    });
    const body = await response.text();
    if (!response.ok) return { ok: false, seconds: (Date.now() - began) / 1000, cost: 0, error: `${response.status} ${body.slice(0, 200)}`, prices, context, outputs };
    const json = JSON.parse(body);
    const seconds = (Date.now() - began) / 1000;
    const cost = Number(json.usage?.cost ?? 0);
    if (kind === "image") {
      const images = (json.choices?.[0]?.message?.images ?? []) as { image_url?: { url?: string } }[];
      const url = images.find((i) => i.image_url?.url)?.image_url?.url;
      return url ? { ok: true, seconds, cost, prices, context, outputs, reply: `an image came back (${Math.round(url.length * 0.75 / 1024)} kB)` }
        : { ok: false, seconds, cost, prices, context, outputs, error: "no image came back: not a model that makes images" };
    }
    return { ok: true, seconds, cost, prices, context, outputs, reply: String(json.choices?.[0]?.message?.content ?? "").slice(0, 80) };
  } catch (error) {
    return { ok: false, seconds: (Date.now() - began) / 1000, cost: 0, error: (error as Error).message, prices, context, outputs };
  }
}
