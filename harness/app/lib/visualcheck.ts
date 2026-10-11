/**
 * The visual check of a built lecture: what the engine found on screen at each beat (pocket_lecture.py
 * _check_beat: words too small, off the frame, over other words, a stage left nearly empty), what it mended by
 * itself, and, for the beats it could not mend, what a model that reads images says when shown the frame:
 * "Is anything unreadable, overlapping, or off-topic?". Read after each build (app/api/export) and shown under
 * the video, so a problem is seen before the video is watched.
 */

import { readFile } from "node:fs/promises";
import path from "node:path";

export type BeatCheck = { beat: number; say: string; issues: string[]; fixed: string[]; frame?: string; review?: string };
export type VisualCheck = { beats: BeatCheck[]; fixed: number; flagged: number; reviewed: number; model?: string };

/** Where the engine writes its check (the build passes these to export_scene.py). */
export function checkPaths(buildDir: string): { log: string; frames: string } {
  return { log: path.join(buildDir, "checks.jsonl"), frames: path.join(buildDir, "checks") };
}

/** The model shown flagged frames: one that reads images (PANIM_LABEL_MODEL, else the figures' model). */
export function reviewModel(): string {
  return process.env.PANIM_CHECK_MODEL || process.env.PANIM_LABEL_MODEL || process.env.OPENROUTER_FIGURE_MODEL || process.env.OPENROUTER_SVG_MODEL ||
    process.env.OPENROUTER_MODEL || "google/gemini-2.5-flash";
}

const QUESTION =
  "This is one frame of an educational lecture video, at the moment the teacher says the line below. Is anything " +
  "unreadable (too small, too faint, cut off), overlapping (words over words or over pictures), or off-topic (not " +
  "about what is being said, or a book's QR code, logo or page furniture)? Answer in one or two short sentences. " +
  "If nothing is wrong, answer exactly: OK.";

async function review(frame: string, say: string, key: string, model: string): Promise<string | null> {
  try {
    const image = `data:image/png;base64,${(await readFile(frame)).toString("base64")}`;
    const response = await fetch(process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      signal: AbortSignal.timeout(60_000),
      body: JSON.stringify({
        model, temperature: 0, max_tokens: 160,
        messages: [{ role: "user", content: [
          { type: "image_url", image_url: { url: image } },
          { type: "text", text: `${QUESTION}\nThe line: "${say}"` },
        ] }],
      }),
    });
    if (!response.ok) return null;
    const data = await response.json() as { choices?: { message?: { content?: string } }[] };
    return (data.choices?.[0]?.message?.content ?? "").trim().slice(0, 400) || null;
  } catch {
    return null;
  }
}

/**
 * The build's check: every beat the engine flagged or mended, and, for up to `most` flagged frames (the vision
 * model is asked several at once), its answer. Without a key, or with PANIM_CHECK_REVIEW=0, the engine's own
 * findings alone.
 */
export async function readVisualCheck(buildDir: string, most = Number(process.env.PANIM_CHECK_REVIEWS) || 6):
  Promise<VisualCheck | null> {
  let text = "";
  try {
    text = await readFile(checkPaths(buildDir).log, "utf8");
  } catch {
    return null;
  }
  const beats: BeatCheck[] = text.split("\n").filter(Boolean).flatMap((line) => {
    try {
      return [JSON.parse(line) as BeatCheck];
    } catch {
      return [];
    }
  });
  if (!beats.length) return null;
  const key = process.env.OPENROUTER_API_KEY;
  const flagged = beats.filter((b) => b.issues.length && b.frame);
  let reviewed = 0;
  const model = reviewModel();
  if (key && process.env.PANIM_CHECK_REVIEW !== "0") {
    await Promise.all(flagged.slice(0, most).map(async (b) => {
      const said = await review(b.frame!, b.say, key, model);
      if (said) {
        b.review = /^ok\.?$/i.test(said) ? "OK" : said;
        reviewed += 1;
      }
    }));
  }
  return {
    beats,
    fixed: beats.reduce((n, b) => n + b.fixed.length, 0),
    flagged: beats.filter((b) => b.issues.length).length,
    reviewed,
    model: reviewed ? model : undefined,
  };
}
