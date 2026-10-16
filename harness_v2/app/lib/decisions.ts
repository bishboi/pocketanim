/**
 * Decision models (Jev and the others on OpenRouter's Decisions API): application state and typed questions in, a
 * typed answer with probabilities out, no text. One call is recorded like a chat call (llm.ts): its parts, every
 * attempt, the answer, tokens and cost (usage.cost; a decision model bills input tokens only), and the request as sent.
 *
 *   POST https://openrouter.ai/api/alpha/decisions  {model, state, questions}
 *
 * The Decisions API is marked alpha and image input as early; the answer is read loosely (the selected option, the
 * probabilities and the confidence wherever they are), and the raw answer is kept on the call, so a change in its
 * shape shows on the page instead of breaking the step.
 */

import type { Call } from "./types";
import { usingFixture } from "./llm";

const URL_ = process.env.OPENROUTER_DECISIONS_URL || "https://openrouter.ai/api/alpha/decisions";
const TRIES = 3;
const TIMEOUT_MS = 180_000;

/** Part of the state: a line of text, or an image (a data URL). */
export type StateItem = string | { type: "image_url"; image_url: { url: string } };

export type ChoiceQuestion = { type: "choice"; instructions: string; options: Record<string, string> };
export type NoulQuestion = { type: "noul"; instructions: string };
export type Question = ChoiceQuestion | NoulQuestion;

export type ChoiceAnswer = { choice?: string; probabilities: Record<string, number>; confidence?: number };

/** The request as it is sent; `shown` is the same with every image cut to a placeholder (for the run's file). */
export function decisionBody(model: string, state: StateItem[], questions: Record<string, Question>) {
  const body = { model, state, questions };
  const shown = { ...body, state: state.map((s) => (typeof s === "string" ? s : { type: "image_url", image_url: { url: `${s.image_url.url.split(",")[0]},… (${Math.round(s.image_url.url.length * 0.75 / 1024)} kB)` } })) };
  return { body, shown };
}

export async function callDecision(o: {
  call: Call;
  state: StateItem[];
  questions: Record<string, Question>;
  fake: () => Record<string, unknown>;
  onChange: () => void;
}): Promise<Record<string, unknown> | null> {
  const { call } = o;
  const { body, shown } = decisionBody(call.model, o.state, o.questions);
  call.api = "decisions";
  call.tool = o.questions;
  call.request = shown;
  call.provider = usingFixture(call.model) ? "fixture" : "openrouter";
  for (let attempt = 1; attempt <= TRIES; attempt++) {
    const began = Date.now();
    try {
      const answer = call.provider === "fixture" ? await fixture(o.fake) : await real(call, body);
      call.attempts.push({ started: began, ended: Date.now() });
      call.output = answer;
      call.status = "done";
      call.ended = Date.now();
      if (call.provider === "fixture") call.usage = { input: Math.round(JSON.stringify(shown).length / 4), output: 0 };
      o.onChange();
      return answer;
    } catch (error) {
      call.attempts.push({ started: began, ended: Date.now(), error: (error as Error).message.slice(0, 400) });
      o.onChange();
      // A refused key, or a request the API refuses as malformed, is refused again.
      if (/\b(400|401|403|404|422)\b/.test((error as Error).message)) break;
    }
  }
  call.status = "failed";
  call.ended = Date.now();
  call.error = call.attempts[call.attempts.length - 1]?.error;
  o.onChange();
  return null;
}

async function fixture(fake: () => Record<string, unknown>) {
  await new Promise((r) => setTimeout(r, 150 + Math.random() * 400));
  return fake();
}

async function real(call: Call, body: unknown): Promise<Record<string, unknown>> {
  const response = await fetch(URL_, {
    method: "POST",
    signal: AbortSignal.timeout(TIMEOUT_MS),
    headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json", "X-Title": "pocketanim harness v2" },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${response.status} ${text.slice(0, 400)}`);
  const json = JSON.parse(text) as Record<string, unknown> & { usage?: Record<string, number>; error?: { message?: string } };
  if (json.error) throw new Error(json.error.message ?? "provider error");
  const u = json.usage ?? {};
  call.usage = { input: u.prompt_tokens ?? u.input_tokens ?? 0, output: u.completion_tokens ?? u.output_tokens ?? 0 };
  call.cost += Number(u.cost ?? 0);
  return json;
}

/** The answer to one question, wherever the reply puts it: at the top, or under answers / decisions / results. */
export function answerTo(reply: Record<string, unknown> | null, key: string): Record<string, unknown> | undefined {
  if (!reply) return undefined;
  for (const place of [reply, reply.answers, reply.decisions, reply.results, reply.data]) {
    const a = (place as Record<string, unknown> | undefined)?.[key];
    if (a && typeof a === "object") return a as Record<string, unknown>;
  }
  return undefined;
}

/** A Choice answer read loosely: the option chosen, a probability for each, and the confidence. */
export function readChoice(a: Record<string, unknown> | undefined, options: string[]): ChoiceAnswer {
  if (!a) return { probabilities: {} };
  const probabilities: Record<string, number> = {};
  const raw = a.probabilities ?? a.probs ?? a.distribution ?? a.options ?? a.scores;
  if (Array.isArray(raw)) {
    for (const p of raw as Record<string, unknown>[]) {
      const k = String(p?.option ?? p?.key ?? p?.label ?? p?.value ?? "");
      const v = Number(p?.probability ?? p?.p ?? p?.score);
      if (k && Number.isFinite(v)) probabilities[k] = v;
    }
  } else if (raw && typeof raw === "object") {
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) if (Number.isFinite(Number(v))) probabilities[k] = Number(v);
  }
  let choice = [a.choice, a.selected, a.answer, a.option, a.value].map((x) => (x == null ? "" : String(x))).find((x) => options.includes(x));
  if (!choice && Object.keys(probabilities).length) choice = Object.entries(probabilities).sort((x, y) => y[1] - x[1])[0][0];
  const confidence = Number.isFinite(Number(a.confidence)) ? Number(a.confidence) : choice ? probabilities[choice] : undefined;
  return { choice: choice && options.includes(choice) ? choice : undefined, probabilities, confidence };
}
