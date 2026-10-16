"use client";

/**
 * One model call, whole: the prompt as the parts it was built from (each opens to its text), the tool it had to
 * call, what it answered, what code found when it read the answer, its attempts, tokens, time and cost, and the
 * request exactly as sent.
 */

import { useState } from "react";
import type { Call } from "@/lib/types";
import { render, type Part, type PartKind } from "@/lib/prompts/parts";

export const KIND_STYLE: Record<PartKind, string> = {
  rules: "border-slate-500 bg-slate-800 text-slate-200",
  book: "border-amber-500 bg-amber-950 text-amber-200",
  items: "border-orange-500 bg-orange-950 text-orange-200",
  goals: "border-emerald-500 bg-emerald-950 text-emerald-200",
  plan: "border-sky-500 bg-sky-950 text-sky-200",
  questions: "border-violet-500 bg-violet-950 text-violet-200",
  context: "border-neutral-500 bg-neutral-800 text-neutral-200",
  language: "border-pink-500 bg-pink-950 text-pink-200",
  choices: "border-cyan-500 bg-cyan-950 text-cyan-200",
  ask: "border-white bg-neutral-700 text-white",
  retry: "border-red-500 bg-red-950 text-red-200",
};

const KIND_NAME: Record<PartKind, string> = {
  rules: "instructions", book: "book content", items: "book items", goals: "goals", plan: "story plan",
  questions: "book questions", context: "context", language: "language", choices: "choices", ask: "request", retry: "retry note",
};

export const CHECK_STYLE = {
  pass: { icon: "✓", tone: "text-emerald-300" },
  fixed: { icon: "✎", tone: "text-amber-300" },
  fail: { icon: "✗", tone: "text-red-300" },
  info: { icon: "i", tone: "text-sky-300" },
};

export const money = (usd: number) => (usd >= 0.01 ? `$${usd.toFixed(3)}` : usd > 0 ? `$${usd.toFixed(5)}` : "$0");
const size = (text: string) => (text.length >= 1000 ? `${(text.length / 1000).toFixed(1)}k` : `${text.length}`);
export const seconds = (a?: number, b?: number) => (a && b ? `${((b - a) / 1000).toFixed(1)} s` : a ? "…" : "");

export function CallInspector({ call, onClose }: { call: Call; onClose: () => void }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const all = [...call.prompt.system.map((p) => ({ ...p, where: "system" })), ...call.prompt.user.map((p) => ({ ...p, where: "user" }))];
  const id = (p: Part & { where: string }) => `${p.where}:${p.key}`;
  const toggle = (k: string) => setOpen((s) => {
    const n = new Set(s);
    if (n.has(k)) n.delete(k);
    else n.add(k);
    return n;
  });
  const body = call.request ?? {
    model: call.model,
    messages: [{ role: "system", content: render(call.prompt.system) }, { role: "user", content: render(call.prompt.user) }],
    tools: call.tool ? [call.tool] : undefined,
    usage: { include: true },
    ...(call.effort && call.effort !== "off" ? { reasoning: { effort: call.effort } } : {}),
  };
  const output = call.output as Record<string, unknown> | undefined;
  const text = typeof output?.text === "string" ? output.text : null;
  const rest = output ? Object.fromEntries(Object.entries(output).filter(([k]) => k !== "text")) : null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose} data-testid="call-inspector">
      <div className="h-full w-full max-w-[min(1100px,92vw)] overflow-y-auto border-l border-neutral-700 bg-neutral-950 p-5"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-neutral-500">{call.step} call · {call.id}</p>
            <h2 className="text-lg font-semibold text-neutral-100">{call.label}</h2>
          </div>
          <button className="rounded border border-neutral-700 px-2 py-1 text-sm text-neutral-300 hover:bg-neutral-800" onClick={onClose}>Close</button>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4 lg:grid-cols-8">
          <Stat label="Model" value={call.model} wide />
          <Stat label="Provider" value={call.provider === "fixture" ? "offline stand-in" : call.api === "decisions" ? "OpenRouter Decisions" : "OpenRouter"} />
          <Stat label="Effort" value={call.effort ?? "default"} />
          <Stat label="Status" value={call.status} tone={call.status === "failed" ? "text-red-300" : call.status === "done" ? "text-emerald-300" : "text-sky-300"} />
          <Stat label="Time" value={seconds(call.started, call.ended)} />
          <Stat label="Tokens in / out" value={call.usage ? `${call.usage.input.toLocaleString()} / ${call.usage.output.toLocaleString()}` : "…"} />
          <Stat label="Cost" value={money(call.cost)} />
        </div>
        {call.usage && (call.usage.cached || call.usage.reasoning) ? (
          <p className="mt-1 text-[11px] text-neutral-500">
            {call.usage.cached ? `${call.usage.cached.toLocaleString()} input tokens from the cache` : ""}
            {call.usage.cached && call.usage.reasoning ? " · " : ""}
            {call.usage.reasoning ? `${call.usage.reasoning.toLocaleString()} output tokens of thinking` : ""}
          </p>
        ) : null}

        <Section title="Prompt" note="The final prompt as the parts it was built from. Click a part to see what is inside it.">
          <div className="flex items-center gap-2 text-xs">
            <button className="rounded border border-neutral-700 px-2 py-0.5 hover:bg-neutral-800" onClick={() => setOpen(new Set(all.map(id)))}>Open all</button>
            <button className="rounded border border-neutral-700 px-2 py-0.5 hover:bg-neutral-800" onClick={() => setOpen(new Set())}>Close all</button>
            <button className="rounded border border-neutral-700 px-2 py-0.5 hover:bg-neutral-800"
              onClick={() => navigator.clipboard?.writeText(`${render(call.prompt.system)}\n\n---\n\n${render(call.prompt.user)}`)}>Copy full prompt</button>
            <span className="text-neutral-500">{size(render(call.prompt.system) + render(call.prompt.user))} characters in all</span>
          </div>
          {(["system", "user"] as const).map((where) => (
            <div key={where} className="mt-3">
              <p className="mb-1 text-[11px] uppercase tracking-wide text-neutral-500">{where === "system" ? "System message" : "User message"}</p>
              <div className="flex flex-wrap gap-1.5">
                {call.prompt[where].map((p) => {
                  const k = `${where}:${p.key}`;
                  return (
                    <button key={k} onClick={() => toggle(k)} data-testid="prompt-part"
                      className={`rounded border px-2 py-1 text-xs ${KIND_STYLE[p.kind]} ${open.has(k) ? "ring-2 ring-white/60" : "opacity-90 hover:opacity-100"}`}>
                      {p.label} <span className="opacity-60">· {KIND_NAME[p.kind]} · {size(p.text)}</span>
                    </button>
                  );
                })}
              </div>
              {call.prompt[where].filter((p) => open.has(`${where}:${p.key}`)).map((p) => (
                <div key={p.key} className={`mt-2 rounded border-l-4 ${KIND_STYLE[p.kind]} bg-neutral-900 p-2`}>
                  <p className="mb-1 text-[11px] font-semibold">{p.label}</p>
                  <pre className="mono max-h-[50vh] overflow-auto whitespace-pre-wrap text-[11.5px] leading-snug text-neutral-200">{p.text}</pre>
                  {/\/api\/documents\/[^\s\]]+\/figure\/[^\s\]]+/.test(p.text) && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img alt="the figure sent with this call" className="mt-2 max-h-80 rounded bg-white"
                      src={/\/api\/documents\/[^\s\]]+\/figure\/[^\s\]]+/.exec(p.text)![0]} />
                  )}
                </div>
              ))}
            </div>
          ))}
        </Section>

        <Section title="Output" note={call.api === "decisions" ? "The decision model's typed answer: the option chosen, a probability for each, and its confidence."
          : call.tool ? `What the model passed to ${(call.tool as { function?: { name?: string } }).function?.name}.` : undefined}>
          {call.status === "running" && <p className="text-sm text-sky-300">Waiting for the reply…</p>}
          {call.error && <p className="text-sm text-red-300">{call.error}</p>}
          {text !== null && (
            <div className="mb-2 rounded border border-neutral-800 bg-neutral-900 p-3">
              <p className="mb-1 text-[11px] uppercase tracking-wide text-neutral-500">text</p>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-neutral-100">{text}</p>
            </div>
          )}
          {rest && <Json value={rest} />}
          {call.text && !output && <p className="whitespace-pre-wrap text-sm">{call.text}</p>}
        </Section>

        <Section title="Checks" note="What code found when it read the reply: passed, mended by code, failed, or only noted.">
          {call.checks.length ? (
            <ul className="space-y-1 text-sm">
              {call.checks.map((c, k) => (
                <li key={k} className="flex gap-2">
                  <span className={`w-4 shrink-0 text-center ${CHECK_STYLE[c.result].tone}`}>{CHECK_STYLE[c.result].icon}</span>
                  <span className="shrink-0 font-medium text-neutral-200">{c.name}</span>
                  <span className="text-neutral-400">{c.detail}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-neutral-500">None yet.</p>}
        </Section>

        <Section title="Attempts">
          <ul className="space-y-1 text-xs text-neutral-300">
            {call.attempts.map((a, k) => (
              <li key={k}>Try {k + 1}: {seconds(a.started, a.ended)}{a.error ? <span className="text-red-300"> · {a.error}</span> : " · answered"}</li>
            ))}
            {!call.attempts.length && <li className="text-neutral-500">Running…</li>}
          </ul>
        </Section>

        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-neutral-300">{call.api === "decisions" ? "Questions" : "Tool schema"}</summary>
          <Json value={call.tool} />
        </details>
        <details className="mt-2">
          <summary className="cursor-pointer text-sm text-neutral-300">Request as sent</summary>
          <Json value={body} />
        </details>
      </div>
    </div>
  );
}

function Stat({ label, value, tone, wide }: { label: string; value: string; tone?: string; wide?: boolean }) {
  return (
    <div className={`rounded border border-neutral-800 bg-neutral-900 px-2 py-1 ${wide ? "col-span-2" : ""}`}>
      <p className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</p>
      <p className={`truncate ${tone ?? "text-neutral-100"}`} title={value}>{value}</p>
    </div>
  );
}

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="text-sm font-semibold text-neutral-100">{title}</h3>
      {note && <p className="mb-2 text-xs text-neutral-500">{note}</p>}
      {children}
    </section>
  );
}

export function Json({ value }: { value: unknown }) {
  return <pre className="mono max-h-[60vh] overflow-auto rounded bg-neutral-900 p-2 text-[11.5px] text-neutral-300">{JSON.stringify(value, null, 2)}</pre>;
}
