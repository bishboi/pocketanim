/**
 * An image model's call, recorded like the others (llm.ts): the prompt as its parts, every attempt, the image it
 * made, tokens and cost, and the request as sent (images cut to a placeholder). Asked as v1 asks
 * (genimage.py _ask): chat completions with image output, the reference image before the words; when OpenRouter
 * says the model is not served that way, its Images API (input_references), and the way that works is remembered.
 */

import { render, type Prompt } from "./prompts/parts";
import { usingFixture } from "./llm";
import type { Call } from "./types";

const CHAT = process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions";
const IMAGES = process.env.OPENROUTER_IMAGES_URL || "https://openrouter.ai/api/v1/images";
const TRIES = 2;
const TIMEOUT_MS = 300_000;
/** The way each model answered (chat or images), as v1 remembers it per run of genimage. */
const routes = ((globalThis as unknown as { __v2routes?: Map<string, "chat" | "images"> }).__v2routes ??= new Map());

export type ImageResult = { bytes: Buffer; mime: string };

const placeholder = (url: string) => `${url.split(",")[0]},… (${Math.round(url.length * 0.75 / 1024)} kB)`;

export async function callImage(o: { call: Call; text: string; reference?: string; fake: () => ImageResult; onChange: () => void }):
  Promise<ImageResult | null> {
  const { call } = o;
  call.api = "image";
  call.provider = usingFixture(call.model) ? "fixture" : "openrouter";
  for (let attempt = 1; attempt <= TRIES; attempt++) {
    const began = Date.now();
    try {
      const out = call.provider === "fixture" ? await fixture(o.fake) : await real(call, o.text, o.reference);
      call.attempts.push({ started: began, ended: Date.now() });
      call.status = "done";
      call.ended = Date.now();
      if (call.provider === "fixture") call.usage = { input: Math.round(o.text.length / 4), output: 0 };
      o.onChange();
      return out;
    } catch (error) {
      call.attempts.push({ started: began, ended: Date.now(), error: (error as Error).message.slice(0, 400) });
      o.onChange();
      if (/\b(400|401|403|404|422)\b/.test((error as Error).message)) break;
    }
  }
  call.status = "failed";
  call.ended = Date.now();
  call.error = call.attempts[call.attempts.length - 1]?.error;
  o.onChange();
  return null;
}

async function fixture(fake: () => ImageResult) {
  await new Promise((r) => setTimeout(r, 200 + Math.random() * 500));
  return fake();
}

async function real(call: Call, text: string, reference?: string): Promise<ImageResult> {
  const known = routes.get(call.model);
  const order: ("chat" | "images")[] = known ? [known, known === "chat" ? "images" : "chat"] : ["chat", "images"];
  let last: Error | undefined;
  for (const route of order) {
    try {
      const out = route === "chat" ? await viaChat(call, text, reference) : await viaImages(call, text, reference);
      routes.set(call.model, route);
      return out;
    } catch (error) {
      last = error as Error;
      // Only a "not served this way" answer tries the other way; anything else is this model's answer.
      if (!/output modalit|images endpoint|\/api\/v1\/images|not support.*image|No endpoints found/i.test(last.message)) throw last;
    }
  }
  throw last ?? new Error("no way to ask this model for an image");
}

async function post(url: string, body: unknown): Promise<Record<string, unknown>> {
  const response = await fetch(url, {
    method: "POST", signal: AbortSignal.timeout(TIMEOUT_MS),
    headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json", "X-Title": "pocketanim harness v2" },
    body: JSON.stringify(body),
  });
  const raw = await response.text();
  if (!response.ok) throw new Error(`${response.status} ${raw.slice(0, 400)}`);
  const json = JSON.parse(raw) as Record<string, unknown> & { error?: { message?: string } };
  if (json.error) throw new Error(json.error.message ?? "provider error");
  return json;
}

async function viaChat(call: Call, text: string, reference?: string): Promise<ImageResult> {
  const content = (url?: string) => [...(url ? [{ type: "image_url", image_url: { url } }] : []), { type: "text", text }];
  const body = { model: call.model, modalities: ["image", "text"], usage: { include: true }, messages: [{ role: "user", content: content(reference) }] };
  call.request = { ...body, messages: [{ role: "user", content: content(reference && placeholder(reference)) }] };
  const json = await post(CHAT, body);
  const message = ((json.choices as { message?: { content?: string; images?: { image_url?: { url?: string } }[] } }[] | undefined)?.[0]?.message) ?? {};
  bill(call, json);
  const url = (message.images ?? []).map((i) => i.image_url?.url).find(Boolean);
  call.text = message.content ?? undefined;
  if (!url) throw new Error(`${call.model} returned no image (is it an image model?)${message.content ? `; it said: ${String(message.content).slice(0, 200)}` : ""}`);
  return await bytesOf(url);
}

async function viaImages(call: Call, text: string, reference?: string): Promise<ImageResult> {
  const refs = (url?: string) => (url ? { input_references: [{ type: "image_url", image_url: { url } }] } : {});
  const body = { model: call.model, prompt: text, ...refs(reference) };
  call.request = { ...body, ...refs(reference && placeholder(reference)) };
  const json = await post(IMAGES, body);
  bill(call, json);
  const items = (json.data ?? json.images ?? []) as Record<string, unknown>[];
  const first = items[0] ?? {};
  const ref = String(first.b64_json ?? first.url ?? (first.image_url as { url?: string } | undefined)?.url ?? "");
  if (!ref) throw new Error(`${call.model} returned no image from the Images API`);
  return await bytesOf(ref.startsWith("data:") || ref.startsWith("http") ? ref : `data:image/png;base64,${ref}`);
}

function bill(call: Call, json: Record<string, unknown>) {
  const u = (json.usage ?? {}) as Record<string, number>;
  call.usage = { input: u.prompt_tokens ?? u.input_tokens ?? 0, output: u.completion_tokens ?? u.output_tokens ?? 0 };
  call.cost += Number(u.cost ?? 0);
}

async function bytesOf(url: string): Promise<ImageResult> {
  const m = /^data:(image\/[\w+.-]+);base64,([\s\S]*)$/.exec(url);
  if (m) return { bytes: Buffer.from(m[2], "base64"), mime: m[1] };
  const response = await fetch(url, { signal: AbortSignal.timeout(60_000) });
  if (!response.ok) throw new Error(`the image could not be downloaded (${response.status})`);
  return { bytes: Buffer.from(await response.arrayBuffer()), mime: response.headers.get("content-type") ?? "image/png" };
}

/** The prompt as the page shows it (its parts); what is sent is `text`. */
export function promptOf(parts: Prompt["user"]): Prompt {
  return { system: [], user: parts };
}

export { render };
