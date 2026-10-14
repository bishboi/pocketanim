/**
 * Where a model's request goes: OpenRouter, or OpenAI's own API for an OpenAI model when there is a key for it.
 *
 * Every AI step names its model the OpenRouter way ("openai/gpt-5.1", "google/gemini-2.5-flash"). A model named
 * openai/... is asked of OpenAI directly when OPENAI_API_KEY is set (PANIM_OPENAI_DIRECT=off keeps it on
 * OpenRouter): the prefix comes off and the request is put in OpenAI's form -- OpenRouter's own fields out (usage,
 * provider, plugins, transforms), its reasoning setting as OpenAI's reasoning_effort, max_tokens as
 * max_completion_tokens, no temperature for a reasoning model, the usage asked for when streaming. OpenAI does not
 * say what a request cost: it is priced from its tokens with PANIM_OPENAI_PRICES ({"gpt-5.1": [in, out]}, US
 * dollars per million tokens), else counted as 0. The Python steps do the same (harness/lecture/providers.py).
 *
 * OPENAI_BASE_URL points at another OpenAI-compatible endpoint (a test's mock, Azure's).
 */

const OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions";
const OPENAI_BASE = "https://api.openai.com/v1";
const OPENROUTER_ONLY = ["usage", "provider", "plugins", "transforms", "models", "route"];

type Body = Record<string, unknown>;

/** Whether this model is asked of OpenAI itself. */
export function openaiDirect(model: string | undefined): boolean {
  return !!model && model.startsWith("openai/") && !!process.env.OPENAI_API_KEY &&
    !["off", "0", "no"].includes((process.env.PANIM_OPENAI_DIRECT ?? "on").trim().toLowerCase());
}

/** OpenAI's reasoning models (o1..., gpt-5 and every gpt after it): they take reasoning_effort, refuse a
 * temperature, and spend part of their output on thinking. */
export function reasoningModel(id: string): boolean {
  const gpt = /^gpt-(\d+)/.exec(id);
  return /^o\d/.test(id) || (!!gpt && Number(gpt[1]) >= 5);
}

/** A reasoning model's output includes its thinking: a cap this small leaves it nothing to answer with. */
const THINKING_ROOM = 4000;

/** An OpenRouter chat request in OpenAI's form. */
export function openaiBody(body: Body): Body {
  const out: Body = Object.fromEntries(Object.entries(body).filter(([k]) => !OPENROUTER_ONLY.includes(k)));
  const id = String(out.model ?? "").replace(/^openai\//, "");
  out.model = id;
  const reasoning = out.reasoning as { effort?: string } | undefined;
  delete out.reasoning;
  if (reasoningModel(id)) {
    if (reasoning?.effort) out.reasoning_effort = reasoning.effort;
    delete out.temperature;
    delete out.top_p;
  }
  if ("max_tokens" in out) {
    const cap = Number(out.max_tokens);
    out.max_completion_tokens = reasoningModel(id) && cap < THINKING_ROOM ? THINKING_ROOM : cap;
    delete out.max_tokens;
  }
  if (out.stream) out.stream_options = { include_usage: true };
  return out;
}

/** The URL, headers and body of a chat completion for this body's model. */
export function chatRequest(body: Body, openrouterKey: string | undefined): { url: string; headers: Record<string, string>; body: Body } {
  const model = String(body.model ?? "");
  if (openaiDirect(model)) {
    return {
      url: `${(process.env.OPENAI_BASE_URL || OPENAI_BASE).replace(/\/$/, "")}/chat/completions`,
      headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
      body: openaiBody(body),
    };
  }
  return {
    url: process.env.OPENROUTER_URL || OPENROUTER_CHAT,
    headers: { Authorization: `Bearer ${openrouterKey ?? process.env.OPENROUTER_API_KEY ?? ""}`, "Content-Type": "application/json" },
    body,
  };
}

/**
 * A provider that refused the request's key (401, 403): the same request will be refused again, so the work stops
 * with what to fix instead of trying again.
 */
export class ProviderAuthError extends Error {}

/** The error for a refused request, with what to do about it when it is the key. */
export function providerError(model: string, status: number, detail: string): Error {
  const said = `${providerName(model)} ${status}: ${detail.slice(0, 300)}`;
  if (status !== 401 && status !== 403) return new Error(said);
  if (openaiDirect(model)) {
    return new ProviderAuthError(`${said}. OpenAI refused the key: check OPENAI_API_KEY in harness/app/.env.local ` +
      "(and that it may use this model), then restart the app.");
  }
  if (model.startsWith("openai/")) {
    return new ProviderAuthError(`${said}. ${model} went through OpenRouter because OPENAI_API_KEY is not set where ` +
      "the app runs: put OPENAI_API_KEY=<your OpenAI key> in harness/app/.env.local and restart the app to ask " +
      "OpenAI directly (or set a working OPENROUTER_API_KEY).");
  }
  return new ProviderAuthError(`${said}. OpenRouter refused the key: ${model} is asked through OpenRouter, so it ` +
    "needs a working OPENROUTER_API_KEY in harness/app/.env.local (restart the app after changing it); or choose " +
    "an openai/... model to use OPENAI_API_KEY.");
}

/** Where each named model's requests go, for the run's first status line. */
export function describeProviders(models: Record<string, string>): string {
  const seen = new Map<string, string[]>();
  for (const [role, model] of Object.entries(models)) {
    if (!model) continue;
    const key = `${model} via ${openaiDirect(model) ? "OpenAI (OPENAI_API_KEY)" : "OpenRouter"}`;
    seen.set(key, [...(seen.get(key) ?? []), role]);
  }
  const parts = [...seen].map(([where, roles]) => `${roles.join(" and ")}: ${where}`);
  const missed = Object.values(models).some((m) => m?.startsWith("openai/") && !openaiDirect(m));
  return `Models: ${parts.join("; ")}.` + (missed && !process.env.OPENAI_API_KEY
    ? " OPENAI_API_KEY is not set where the app runs, so openai/ models go through OpenRouter." : "");
}

/** Who answers for a model, for an error message. */
export function providerName(model: string | undefined): string {
  return openaiDirect(model) ? "OpenAI" : "OpenRouter";
}

/** What a reply cost: OpenRouter's own figure, else (an OpenAI reply) its tokens at PANIM_OPENAI_PRICES. */
export function replyCost(model: string | undefined, usage: { cost?: number; prompt_tokens?: number; completion_tokens?: number } | undefined): number {
  if (usage?.cost != null) return Number(usage.cost) || 0;
  let prices: Record<string, [number, number]> = {};
  try {
    prices = JSON.parse(process.env.PANIM_OPENAI_PRICES || "{}");
  } catch {
    prices = {};
  }
  const price = prices[String(model ?? "").replace(/^openai\//, "")];
  if (!price || !usage) return 0;
  return ((usage.prompt_tokens ?? 0) * price[0] + (usage.completion_tokens ?? 0) * price[1]) / 1e6;
}

/** The usage of a reply with its cost filled in (an OpenAI reply has none of its own). */
export function withCost<U extends { cost?: number; prompt_tokens?: number; completion_tokens?: number }>(model: string | undefined, usage: U | undefined): U | undefined {
  if (!usage || usage.cost != null) return usage;
  return { ...usage, cost: replyCost(model, usage) };
}

// ---- OpenAI's Responses API, for a request with tools -----------------------------------------------------------
//
// OpenAI refuses function tools together with a reasoning setting on chat completions for its newer models
// ("Function tools with reasoning_effort are not supported ... Please use /v1/responses instead"). A request with
// tools to an OpenAI model therefore goes to /v1/responses: its messages and tools are put in that API's form, and
// its stream is read back as the chat stream the caller already reads (responsesDelta).

type ChatTool = { type: "function"; function: { name: string; description?: string; parameters?: unknown } };
type ChatMsg = {
  role: string;
  content: unknown;
  tool_calls?: { id: string; function: { name: string; arguments: string } }[];
  tool_call_id?: string;
};

/** Whether a request is asked of OpenAI's Responses API rather than chat completions. */
export function usesResponses(body: Body): boolean {
  return openaiDirect(String(body.model ?? "")) && Array.isArray(body.tools) && body.tools.length > 0 &&
    !["off", "0", "no"].includes((process.env.PANIM_OPENAI_RESPONSES ?? "on").trim().toLowerCase());
}

function inputParts(content: unknown, role: string): unknown {
  if (typeof content === "string" || content == null) return content ?? "";
  if (!Array.isArray(content)) return String(content);
  return content.map((part: { type?: string; text?: string; image_url?: { url?: string } }) =>
    part.type === "image_url"
      ? { type: "input_image", image_url: part.image_url?.url ?? "" }
      : { type: role === "assistant" ? "output_text" : "input_text", text: part.text ?? "" });
}

/** A chat request with tools in the Responses API's form. */
export function responsesBody(body: Body): Body {
  const id = String(body.model ?? "").replace(/^openai\//, "");
  const input: unknown[] = [];
  for (const m of (body.messages as ChatMsg[] | undefined) ?? []) {
    if (m.role === "tool") {
      input.push({ type: "function_call_output", call_id: m.tool_call_id ?? "", output: String(m.content ?? "") });
      continue;
    }
    if (m.role === "assistant" && m.tool_calls?.length) {
      if (m.content) input.push({ role: "assistant", content: inputParts(m.content, "assistant") });
      for (const call of m.tool_calls) {
        input.push({ type: "function_call", call_id: call.id, name: call.function.name, arguments: call.function.arguments });
      }
      continue;
    }
    input.push({ role: m.role, content: inputParts(m.content, m.role) });
  }
  const out: Body = {
    model: id,
    input,
    store: false,
    tools: ((body.tools as ChatTool[]) ?? []).map((t) => ({ type: "function", name: t.function.name,
      description: t.function.description ?? "", parameters: t.function.parameters ?? { type: "object" } })),
  };
  if (body.tool_choice) out.tool_choice = body.tool_choice;
  if (body.stream) out.stream = true;
  const effort = (body.reasoning as { effort?: string } | undefined)?.effort;
  if (reasoningModel(id)) {
    if (effort) out.reasoning = { effort };
  } else if (body.temperature != null) {
    out.temperature = body.temperature;
  }
  const cap = body.max_tokens ?? body.max_completion_tokens;
  if (cap != null) out.max_output_tokens = reasoningModel(id) ? Math.max(Number(cap), THINKING_ROOM) : Number(cap);
  return out;
}

/** The URL, headers and body for this request: the Responses API when it has tools, else chat completions. */
export function modelRequest(body: Body, openrouterKey: string | undefined): { url: string; headers: Record<string, string>; body: Body; responses: boolean } {
  if (usesResponses(body)) {
    return {
      url: `${(process.env.OPENAI_BASE_URL || OPENAI_BASE).replace(/\/$/, "")}/responses`,
      headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
      body: responsesBody(body),
      responses: true,
    };
  }
  return { ...chatRequest(body, openrouterKey), responses: false };
}

type ChatDelta = {
  content?: string;
  reasoning?: string;
  tool_calls?: { index: number; id?: string; function: { name?: string; arguments?: string } }[];
};

/** A Responses API stream read as a chat stream: one event in, the chat delta (and the end) it amounts to. */
export class ResponsesStream {
  private calls = new Map<string, number>();
  usage?: { prompt_tokens: number; completion_tokens: number };
  finishReason = "";

  handle(event: Record<string, unknown>): { delta?: ChatDelta; error?: string } {
    const type = String(event.type ?? "");
    const item = event.item as { type?: string; id?: string; call_id?: string; name?: string; arguments?: string } | undefined;
    switch (type) {
      case "response.output_text.delta":
        return { delta: { content: String(event.delta ?? "") } };
      case "response.reasoning_summary_text.delta":
      case "response.reasoning_text.delta":
        return { delta: { reasoning: String(event.delta ?? "") } };
      case "response.output_item.added":
        if (item?.type === "function_call" && item.id) {
          const index = this.calls.size;
          this.calls.set(item.id, index);
          return { delta: { tool_calls: [{ index, id: item.call_id ?? item.id,
            function: { name: item.name ?? "", arguments: item.arguments ?? "" } }] } };
        }
        return {};
      case "response.function_call_arguments.delta": {
        const index = this.calls.get(String(event.item_id ?? ""));
        if (index === undefined) return {};
        return { delta: { tool_calls: [{ index, function: { arguments: String(event.delta ?? "") } }] } };
      }
      case "response.completed":
      case "response.incomplete": {
        const response = event.response as { usage?: { input_tokens?: number; output_tokens?: number };
          incomplete_details?: { reason?: string } } | undefined;
        this.usage = { prompt_tokens: response?.usage?.input_tokens ?? 0, completion_tokens: response?.usage?.output_tokens ?? 0 };
        this.finishReason = type === "response.incomplete"
          ? (response?.incomplete_details?.reason === "max_output_tokens" ? "length" : String(response?.incomplete_details?.reason ?? "incomplete"))
          : (this.calls.size ? "tool_calls" : "stop");
        return {};
      }
      case "response.failed": {
        const response = event.response as { error?: { message?: string } } | undefined;
        return { error: response?.error?.message ?? "OpenAI: the response failed" };
      }
      case "error":
        return { error: String((event as { message?: string }).message ?? (event.error as { message?: string })?.message ?? "OpenAI stream error") };
      default:
        return {};
    }
  }
}
