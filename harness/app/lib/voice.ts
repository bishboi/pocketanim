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
  return [...source.matchAll(/^[ \t]*# voice:[ \t]*(.+)$/gm)].map((match) => match[1].trim()).filter(Boolean);
}

/**
 * Set each voiced wait to its line's real length, and start the line there.
 *
 * With `files`, an `self.add_sound(...)` goes before each wait. The exporter
 * records where every sound starts and mixes one track from them, so a line
 * plays on the frame its beat does. The single concatenated file played from
 * t=0 ran ahead of the picture by every animation between the waits.
 */
export function retime(source: string, durations: number[], files: string[] = []): string {
  let index = 0;
  return source.replace(
    /(# voice:.*\n)(?:[ \t]*self\.add_sound\([^)]*\)\n)?([ \t]*)self\.wait\([^)]*\)/g,
    (match, comment: string, indent: string) => {
      const at = index++;
      const seconds = durations[at];
      if (seconds == null) return match;
      const sound = files[at] ? `${indent}self.add_sound(${JSON.stringify(files[at])})\n` : "";
      return `${comment}${sound}${indent}self.wait(${seconds.toFixed(2)})`;
    },
  );
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
  let data: { ok?: boolean; durations?: number[]; files?: string[]; out?: string; error?: string } = {};
  try {
    data = JSON.parse(line);
  } catch {
    return { ok: false, source, error: stderr.trim().slice(-400) || "Kokoro returned nothing." };
  }
  if (!data.ok || !data.durations) return { ok: false, source, error: data.error || "Kokoro did not speak." };
  return {
    ok: true,
    source: retime(source, data.durations, data.files ?? []),
    audioPath: data.out,
    durations: data.durations,
  };
}
