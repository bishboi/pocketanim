/**
 * Narration is a list of `# voice:` lines in the scene. Kokoro speaks them,
 * and the wait that follows each line is rewritten to the real duration so
 * the picture holds while the sentence is said.
 */

import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { REPO, python } from "./pocketanim";
import { templateById } from "./templates";

export type VoiceResult = {
  ok: boolean;
  source: string;
  audioPath?: string;
  durations?: number[];
  error?: string;
};

export function voiceLines(source: string): string[] {
  return [...source.matchAll(/^# voice:\s*(.+)$/gm)].map((match) => match[1].trim()).filter(Boolean);
}

export function retime(source: string, durations: number[]): string {
  let index = 0;
  return source.replace(/# voice:.*\n([ \t]*)self\.wait\([^)]*\)/g, (match) => {
    const seconds = durations[index++];
    if (seconds == null) return match;
    return match.replace(/self\.wait\([^)]*\)/, `self.wait(${seconds.toFixed(2)})`);
  });
}

function runKokoro(payload: unknown): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(python(), [path.join(REPO, "harness", "scripts", "kokoro_speak.py")], { cwd: REPO });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk.toString()));
    child.stderr.on("data", (chunk) => (stderr += chunk.toString()));
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: code ?? -1, stdout, stderr }));
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

export async function kokoroReady(): Promise<boolean> {
  try {
    const { stdout } = await runKokoro({ check: true });
    const line = stdout.trim().split("\n").pop() || "";
    return JSON.parse(line).ok === true;
  } catch {
    return false;
  }
}

export async function speak(source: string, templateId: string): Promise<VoiceResult> {
  const lines = voiceLines(source);
  if (lines.length === 0) return { ok: false, source, error: "The scene has no # voice: lines." };
  const dir = path.join(REPO, "harness", "app", ".voice");
  mkdirSync(dir, { recursive: true });
  const audioPath = path.join(dir, `narration-${Date.now()}.wav`);
  const voice = templateById(templateId).voice;
  const { stdout, stderr } = await runKokoro({ voice, lines, out: audioPath });
  const line = stdout.trim().split("\n").pop() || "";
  let data: { ok?: boolean; durations?: number[]; out?: string; error?: string } = {};
  try {
    data = JSON.parse(line);
  } catch {
    return { ok: false, source, error: stderr.trim().slice(-400) || "Kokoro returned nothing." };
  }
  if (!data.ok || !data.durations) return { ok: false, source, error: data.error || "Kokoro did not speak." };
  return { ok: true, source: retime(source, data.durations), audioPath: data.out, durations: data.durations };
}
