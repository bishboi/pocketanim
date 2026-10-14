/**
 * The scene tool the lecture agent may call besides write_lecture: edit_scene, a search-and-replace on the
 * compiled lecture.
 */

import type { AiPicture, Costs } from "./costs";

export type AgentEvent = {
  type: "message" | "input" | "delta" | "tool_call" | "tool_result" | "usage" | "done" | "error" | "transcript" | "part" | "job"
    | "picture";
  role?: string;
  name?: string;
  text?: string;
  args?: string;
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
  /** The cost so far, task by task (lib/costs.ts), with each usage event. */
  costs?: Costs;
  /** Seconds since the generation began, with each usage event: its whole time once it is done. */
  seconds?: number;
  /** When the server sent it (ms since the epoch; lib/jobs.ts stamps every event). */
  at?: number;
  /** A picture the AI made for the lecture (type "picture"), with what it cost. */
  picture?: AiPicture;
  source?: string;
  model?: string;
  /** A lecture made as more than one video (lib/parts.ts): each part's title, length and scene. */
  parts?: { title: string; minutes: number; source: string }[];
  /** One micro-lecture of a series, compiled as soon as its sections' chapters are written, for an early build. */
  part?: { index: number; of: number; title: string; minutes: number; source: string };
};

export const TOOLS = [
  {
    type: "function" as const,
    function: {
      name: "edit_scene",
      description:
        "Replace one exact span of the current Manim file, the way a code editor applies a search-and-replace. old_string must appear exactly once, including indentation and blank lines. new_string is what replaces it. For a lecture, new_string should add several beats, about two minutes of speech, not a single line. Each new beat FadeOuts the previous beat first, so titles and sentences never share the frame. If the result says the span was missing or matched more than once, copy a longer or shorter span from the file and call again. Do not reprint the file in your reply.",
      parameters: {
        type: "object",
        properties: {
          old_string: { type: "string", description: "The exact text to replace. Copy it from the current file." },
          new_string: { type: "string", description: "The text to put in its place. May be empty to delete the span." },
        },
        required: ["old_string", "new_string"],
        additionalProperties: false,
      },
    },
  },
];

function preview(text: string): string {
  const lines = text.split("\n");
  if (lines.length <= 14) return text;
  return `${lines.slice(0, 14).join("\n")}\n… (${lines.length} lines)`;
}

/** Apply edit_scene. Other tool names return null. */
export function applySceneTool(
  source: string,
  name: string,
  args: { source?: string; old_string?: string; new_string?: string },
): { source: string; message: string } | null {
  if (name !== "edit_scene") return null;
  const oldString = String(args.old_string ?? "");
  const newString = String(args.new_string ?? "");
  if (!source.trim()) return { source, message: "No scene yet. Call write_lecture first." };
  if (!oldString) return { source, message: "old_string is empty. Pass the exact lines to replace." };
  if (oldString === newString) return { source, message: "old_string and new_string are the same. Nothing changed." };
  const count = source.split(oldString).length - 1;
  if (count === 0) {
    return { source, message: "old_string was not found. Copy it exactly from the current scene, including indentation." };
  }
  if (count > 1) {
    return { source, message: `old_string matched ${count} times. Include more surrounding lines so it matches once.` };
  }
  const replaced = source.replace(oldString, newString);
  const file = replaced.endsWith("\n") ? replaced : `${replaced}\n`;
  return {
    source: file,
    message: `Edited the scene.\n\nold:\n${preview(oldString)}\n\nnew:\n${preview(newString)}`,
  };
}

export async function runTool(name: string): Promise<string> {
  return `Unknown tool ${name}.`;
}
