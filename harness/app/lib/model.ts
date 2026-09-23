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

import { Template, templateById } from "./templates";

export type Generated = {
  source: string;
  sceneClass: string;
  model: string;
  inputTokens?: number;
  outputTokens?: number;
};

export type GenerateRequest = {
  content: string;
  templateId: string;
  /** An edit: the version being changed, and what to change about it. */
  previousSource?: string;
  instruction?: string;
};

const SCENE_CLASS = "GeneratedScene";

/**
 * What the model is told it may write.
 *
 * This lowers how often a scene falls to tier 3; it does not make a scene
 * *correct*. Correctness is the exporter's job, and docs/SPEC.md §11 is the
 * record of why: thirteen constructs exported at tier 1 and drew the wrong
 * thing, none of which any prompt would have prevented. The program's own
 * `blockers` are the authority, not this list.
 */
function systemPrompt(template: Template): string {
  return [
    "You write Manim Community scenes that a separate exporter turns into a",
    "small program for a phone renderer. Reply with Python only -- no prose, no",
    "code fences.",
    "",
    `The scene class must be named ${SCENE_CLASS}.`,
    "",
    "Stay inside this vocabulary, which the exporter expresses exactly:",
    "  shapes     Circle, Square, Rectangle, Text, MathTex, Tex, VGroup",
    "  animations Create, Write, FadeIn, FadeOut, Transform,",
    "             TransformMatchingTex, GrowFromCenter in a LaggedStart,",
    "             and .animate with only .scale() and .shift()",
    "  timing     self.play(..., run_time=...) and self.wait(...)",
    "",
    "Avoid, because they force a much larger fallback artifact:",
    "  ValueTracker and always_redraw; Uncreate and Unwrite; FadeIn(shift=...)",
    "  or scale=...; Transform(path_arc=...); rate_func other than smooth or",
    "  linear; rotating or non-uniformly stretching a Circle/Square/Rectangle.",
    "",
    `Template: ${template.name}. ${template.direction}`,
    `Use these colours: ${template.palette.join(", ")}.`,
    ...(template.extraImports?.length
      ? ["You may also use: " + template.extraImports.join("; ")]
      : []),
  ].join("\n");
}

function userPrompt(request: GenerateRequest): string {
  if (request.instruction && request.previousSource) {
    return [
      "Here is the current scene:",
      "",
      request.previousSource,
      "",
      "Change it as follows, and reply with the complete updated file:",
      request.instruction,
    ].join("\n");
  }
  return [
    "Write a scene that explains the following content:",
    "",
    request.content,
  ].join("\n");
}

/** Strip a fenced block if the model wrapped its answer in one anyway. */
function unfence(text: string): string {
  const fence = text.match(/```(?:python)?\s*\n([\s\S]*?)```/);
  return (fence ? fence[1] : text).trim() + "\n";
}

async function viaOpenRouter(request: GenerateRequest): Promise<Generated> {
  const key = process.env.OPENROUTER_API_KEY!;
  const model = process.env.OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4.5";
  const template = templateById(request.templateId);

  const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: systemPrompt(template) },
        { role: "user", content: userPrompt(request) },
      ],
    }),
  });

  if (!response.ok) {
    throw new Error(
      `OpenRouter ${response.status}: ${(await response.text()).slice(0, 400)}`,
    );
  }
  const body = await response.json();
  const text: string = body.choices?.[0]?.message?.content ?? "";
  if (!text.trim()) throw new Error("OpenRouter returned an empty message");

  return {
    source: unfence(text),
    sceneClass: SCENE_CLASS,
    model,
    inputTokens: body.usage?.prompt_tokens,
    outputTokens: body.usage?.completion_tokens,
  };
}

/**
 * The offline provider. It does not pretend to understand the content -- it
 * builds a scene *from* it, so the output is real Manim that exports and plays,
 * and an instruction visibly changes the result. Enough to exercise every step
 * after generation without a key.
 */
function viaFixture(request: GenerateRequest): Generated {
  const template = templateById(request.templateId);
  const title = (request.content.trim().split("\n")[0] || "Untitled").slice(0, 40);
  const beats = request.content
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(1, 4);

  const escape = (s: string) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const [accent, second, third] = template.palette;

  const body = beats.length
    ? beats
        .map((beat, index) => {
          const colour = [accent, second, third][index % 3];
          return [
            `        beat${index} = Text("${escape(beat.slice(0, 48))}", font_size=28, color="${colour}")`,
            `        beat${index}.shift(DOWN * ${index - 0.5})`,
            `        self.play(FadeIn(beat${index}), run_time=0.8)`,
            `        self.wait(0.4)`,
          ].join("\n");
        })
        .join("\n")
    : [
        `        shape = Circle(radius=1.2, color="${accent}")`,
        `        self.play(Create(shape), run_time=1.2)`,
        `        self.wait(0.5)`,
      ].join("\n");

  const note = request.instruction
    ? `\n        # edit: ${request.instruction.replace(/\n/g, " ").slice(0, 70)}\n`
    : "\n";

  return {
    source:
      `from manim import *\n\n\n` +
      `class ${SCENE_CLASS}(Scene):\n` +
      `    def construct(self):${note}` +
      `        title = Text("${escape(title)}", font_size=44, color="${template.palette[template.palette.length - 1]}")\n` +
      `        self.play(Write(title), run_time=1.2)\n` +
      `        self.play(title.animate.scale(0.5).shift(UP * 3), run_time=0.8)\n` +
      `${body}\n` +
      `        self.wait(1)\n`,
    sceneClass: SCENE_CLASS,
    model: "fixture (no OPENROUTER_API_KEY set)",
  };
}

export function usingFixture(): boolean {
  return !process.env.OPENROUTER_API_KEY;
}

export async function generate(request: GenerateRequest): Promise<Generated> {
  return usingFixture() ? viaFixture(request) : viaOpenRouter(request);
}
