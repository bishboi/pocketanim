/** The voices v2 can speak with (the engine's tts.py), for the server and the page alike. */

import type { Run, VoiceSettings } from "./types";

export const ENGINES: { id: VoiceSettings["engine"]; label: string; key: string; voices: string[] }[] = [
  { id: "gemini", label: "Gemini TTS", key: "GEMINI_API_KEY",
    voices: ["Achird", "Kore", "Charon", "Puck", "Aoede", "Orus", "Zephyr", "Fenrir", "Leda", "Sulafat", "Iapetus", "Algieba"] },
  { id: "chirp", label: "Google Chirp 3 HD", key: "GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_TTS_API_KEY",
    voices: ["Charon", "Kore", "Aoede", "Puck", "Orus", "Leda", "Fenrir"] },
  { id: "eleven", label: "ElevenLabs (times its own words)", key: "ELEVENLABS_API_KEY", voices: [] },
  { id: "espeak", label: "espeak-ng (offline, free, robotic)", key: "", voices: ["en-gb", "en-us", "en-in", "hi"] },
];

/** Whether any chapter of the run is being spoken now (the page follows the run while it is). */
export function voiceRunning(run: Run | null | undefined): boolean {
  return Object.values(run?.voice?.lectures ?? {}).some((l) => Object.values(l).some((c) => c.status === "running"));
}

/** What a chapter's scenes are (the look, each beat's words and visuals), as a short key: a voice made from other
 * scenes is behind them. A plain string hash (FNV-1a), so the page can tell too. */
export function scenesKey(run: Run, n: number, chapter: number): string {
  const c = run.script?.lectures[n]?.chapters.find((x) => x.n === chapter);
  const sl = run.scenes?.lectures[n];
  const text = JSON.stringify([run.scenes?.look, (c?.beats ?? []).map((b) => [b.lines, sl?.beats[b.n]?.ops ?? []])]);
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193) >>> 0;
  return h.toString(16);
}
