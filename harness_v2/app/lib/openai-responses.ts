/**
 * OpenAI's own API for OpenAI's models (Responses API), for the agents: what OpenRouter cannot carry for them.
 *
 *   - Reasoning across tool calls: each answer's reasoning comes back encrypted (`include:
 *     ["reasoning.encrypted_content"]`, nothing stored at OpenAI) and is sent back with the next turn, so the model keeps
 *     its own thread of thought through a long build instead of starting cold every turn.
 *   - Its reasoning as words: summaries of it (`reasoning.summary`), streamed, for the page.
 *
 * Used when a model is named `openai/<model>` and OPENAI_API_KEY is set (OPENAI_BASE_URL for another endpoint); the
 * conversation stays in chat form for the rest of v2 and is turned into the Responses API's items here.
 */

import { timeoutOrAbort } from "./abort";

export type ChatMsg = { role: "system" | "user" | "assistant" | "tool"; content: unknown; tool_calls?: unknown[]; tool_call_id?: string;
  /** The Responses API's own output for this assistant turn (its reasoning, words and calls), sent back as it came. */
  _openai?: unknown[] };
export type ChatTool = { type: "function"; function: { name: string; description: string; parameters: unknown } };
export type Live = { text: string; reasoning: string; tools: string[] };
export type Answer = { text?: string; reasoning?: string; calls: { id: string; function: { name: string; arguments: string } }[];
  usage: { input: number; output: number; reasoning?: number; cached?: number }; output: unknown[];
  /** The reasoning level it ran at (high when the one asked was not taken). */
  effort?: string };

export function useOpenAI(model: string): boolean {
  return model.startsWith("openai/") && !!process.env.OPENAI_API_KEY?.trim();
}

const BASE = () => (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");

/** The chat conversation as the Responses API's input items (and its instructions). */
export function toInput(messages: ChatMsg[]): { instructions: string; input: unknown[] } {
  const instructions = messages.filter((m) => m.role === "system").map((m) => String(m.content)).join("\n\n");
  const input: unknown[] = [];
  for (const m of messages) {
    if (m.role === "system") continue;
    if (m.role === "user") {
      const parts = Array.isArray(m.content) ? m.content as { type: string; text?: string; image_url?: { url: string; detail?: string } }[] : [{ type: "text", text: String(m.content) }];
      input.push({ role: "user", content: parts.map((p) => p.type === "image_url"
        ? { type: "input_image", image_url: p.image_url!.url, detail: p.image_url!.detail ?? "auto" }
        : { type: "input_text", text: p.text ?? "" }) });
    } else if (m.role === "assistant") {
      if (m._openai?.length) {
        input.push(...m._openai);
        continue;
      }
      if (m.content) input.push({ role: "assistant", content: [{ type: "output_text", text: String(m.content) }] });
      for (const c of (m.tool_calls ?? []) as { id: string; function: { name: string; arguments: string } }[]) {
        input.push({ type: "function_call", call_id: c.id, name: c.function.name, arguments: c.function.arguments });
      }
    } else if (m.role === "tool") {
      input.push({ type: "function_call_output", call_id: m.tool_call_id, output: String(m.content) });
    }
  }
  return { instructions, input };
}

/** One turn on OpenAI's Responses API, streamed. */
export async function respond(o: { model: string; messages: ChatMsg[]; tools: ChatTool[]; effort?: string; maxTokens: number; timeoutMs: number;
  onLive: (live: Live) => void;
  /** The same for every turn of one conversation: its requests go to the same prompt cache. */
  cacheKey?: string }): Promise<Answer> {
  const { instructions, input } = toInput(o.messages);
  // Off is asked for as "none": with no reasoning setting at all, a reasoning model thinks at its own default level.
  let reasoning: { effort: string; summary?: string } = !o.effort || o.effort === "off" ? { effort: "none" } : { effort: o.effort, summary: "auto" };
  const body = (withSummary: boolean) => JSON.stringify({
    model: o.model.replace(/^openai\//, ""), instructions, input, stream: true, store: false, max_output_tokens: o.maxTokens,
    tools: o.tools.map((t) => ({ type: "function", name: t.function.name, description: t.function.description, parameters: t.function.parameters })),
    tool_choice: "required", parallel_tool_calls: true, ...(o.cacheKey ? { prompt_cache_key: o.cacheKey } : {}),
    reasoning: withSummary ? reasoning : { effort: reasoning.effort }, include: ["reasoning.encrypted_content"],
  });
  let response = await fetch(`${BASE()}/responses`, { method: "POST", signal: timeoutOrAbort(o.timeoutMs),
    headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" }, body: body(true) });
  if (!response.ok && reasoning.effort !== "high" && response.status === 400) {
    // A reasoning level this model does not take: off as "minimal" (models before "none"); max, xhigh on an older
    // one as high.
    const said = await response.clone().text();
    if (/effort/i.test(said)) {
      reasoning = reasoning.effort === "none" ? { effort: "minimal" } : { ...reasoning, effort: "high" };
      response = await fetch(`${BASE()}/responses`, { method: "POST", signal: timeoutOrAbort(o.timeoutMs),
        headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" }, body: body(true) });
    }
  }
  if (!response.ok) {
    const said = await response.text();
    // An organisation not verified for reasoning summaries: the same turn, its reasoning kept but not shown.
    if (reasoning.summary && response.status === 400 && /summar/i.test(said)) {
      response = await fetch(`${BASE()}/responses`, { method: "POST", signal: timeoutOrAbort(o.timeoutMs),
        headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" }, body: body(false) });
      if (!response.ok) throw new Error(`${response.status} ${(await response.text()).slice(0, 300)}`);
    } else {
      throw new Error(`${response.status} ${said.slice(0, 300)}`);
    }
  }
  if (!response.body) throw new Error("no answer");
  let text = "";
  let thought = "";
  const tools = new Map<string, { name: string; args: string }>();
  let final: { output?: unknown[]; usage?: { input_tokens?: number; output_tokens?: number;
    output_tokens_details?: { reasoning_tokens?: number }; input_tokens_details?: { cached_tokens?: number } }; status?: string;
    incomplete_details?: { reason?: string }; error?: { message?: string } } | undefined;
  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";
  let shown = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, cut).trim();
      buffer = buffer.slice(cut + 1);
      if (!line.startsWith("data:")) continue;
      let e: { type?: string; delta?: string; item?: { type?: string; id?: string; call_id?: string; name?: string }; item_id?: string;
        response?: typeof final; message?: string };
      try {
        e = JSON.parse(line.slice(5).trim());
      } catch {
        continue;
      }
      switch (e.type) {
        case "response.output_text.delta": text += e.delta ?? ""; break;
        case "response.reasoning_summary_text.delta": thought += e.delta ?? ""; break;
        case "response.reasoning_summary_part.done": thought += "\n\n"; break;
        case "response.output_item.added":
          if (e.item?.type === "function_call") tools.set(e.item.id ?? String(tools.size), { name: e.item.name ?? "", args: "" });
          break;
        case "response.function_call_arguments.delta": {
          const t = tools.get(e.item_id ?? "");
          if (t) t.args += e.delta ?? "";
          break;
        }
        case "response.completed": case "response.incomplete": final = e.response; break;
        case "response.failed": throw new Error(e.response?.error?.message ?? "the response failed");
        case "error": throw new Error(e.message ?? "provider error");
      }
      const size = text.length + thought.length + [...tools.values()].reduce((n, t) => n + t.args.length, 0);
      if (size - shown > 300) {
        shown = size;
        o.onLive({ text, reasoning: thought, tools: [...tools.values()].map((t) => t.name) });
      }
    }
  }
  if (!final) throw new Error("the answer ended before it was complete");
  if (final.status === "incomplete") throw new Error(`the answer was cut off (${final.incomplete_details?.reason ?? "incomplete"})`);
  const output = (final.output ?? []) as { type: string; call_id?: string; name?: string; arguments?: string;
    content?: { type: string; text?: string }[]; summary?: { text?: string }[] }[];
  const calls = output.filter((x) => x.type === "function_call").map((x) => ({ id: x.call_id ?? "", function: { name: x.name ?? "", arguments: x.arguments ?? "{}" } }));
  const said = output.filter((x) => x.type === "message").flatMap((x) => (x.content ?? []).filter((c) => c.type === "output_text").map((c) => c.text ?? "")).join("") || text;
  const summary = output.filter((x) => x.type === "reasoning").flatMap((x) => (x.summary ?? []).map((s) => s.text ?? "")).join("\n\n") || thought.trim();
  o.onLive({ text: said, reasoning: summary, tools: calls.map((c) => c.function.name) });
  return { text: said || undefined, reasoning: summary || undefined, calls, output,
    effort: reasoning.effort === "none" ? "off" : reasoning.effort,
    usage: { input: final.usage?.input_tokens ?? 0, output: final.usage?.output_tokens ?? 0,
      ...(final.usage?.output_tokens_details?.reasoning_tokens ? { reasoning: final.usage.output_tokens_details.reasoning_tokens } : {}),
      ...(final.usage?.input_tokens_details?.cached_tokens ? { cached: final.usage.input_tokens_details.cached_tokens } : {}) } };
}
