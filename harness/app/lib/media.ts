/**
 * Everything a lecture generation makes, kept in Supabase by default, so runs can be saved and compared
 * (harness/supabase/migrations/0003_generated_media.sql). PANIM_STORE_MEDIA=0 turns it off; without Supabase set up
 * (lib/store.ts storeProblem) nothing is kept and nothing is said.
 *
 *   - the generation: what it was asked, its models, its length and cost (generations);
 *   - each picture it made or used, once per distinct file in the private bucket `media`, media/<sha256>.<ext>,
 *     with what it shows (media.description) and where it came from (media.metadata), and each use of it with its
 *     context: the chapter, the line said over it, what it sits beside, what it cost (generation_media);
 *   - each video's Manim source (generation_scenes), and each .panim built from one, programs/<sha256>.panim
 *     (programs: every build, saved or not, linked to its generation by the source's digest).
 *
 * The uploads run in the background and never hold the lecture up; a failure is said once in the log.
 */

import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import type { CompiledPicture } from "./lecture";
import { describeError, storeClient } from "./store";

export const MEDIA_BUCKET = "media";

export type MediaKind = "drawing" | "figure" | "book-figure" | "book-photo" | "photo" | "illustration";

/** One picture to keep: its file, what it shows, where it came from, and where this generation used it. */
export type MediaItem = {
  file: string;
  kind: MediaKind;
  /** What the picture shows, in words: the drawing's description, the figure's caption, the subject. */
  description: string;
  /** Where the picture came from: parts, model, source, credit, licence, url, the query it was found by. */
  metadata?: Record<string, unknown>;
  /** How this generation used it, in a few words ("drawn for a beat", "book figure redrawn as SVG"). */
  role: string;
  /** Where: chapter, section, the line said over it, the diagram node or label it sits beside. */
  context?: Record<string, unknown>;
  usd?: number | null;
  reused?: boolean;
};

const TYPES: Record<string, string> = {
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
  ".gif": "image/gif", ".panim": "text/plain; charset=utf-8",
};

export function mediaEnabled(): boolean {
  return process.env.PANIM_STORE_MEDIA !== "0" && storeClient() !== null;
}

export function sha256(data: string | Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

/** Keep the meaningful part of a context: no empty values, long texts shortened. */
function tidy(value: Record<string, unknown> | undefined): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value ?? {})) {
    if (v === undefined || v === null || v === "") continue;
    out[k] = typeof v === "string" ? v.slice(0, 4000) : v;
  }
  return out;
}

/** A file into the bucket under its content's digest; one already there (the same bytes) is fine. */
async function upload(key: string, data: Buffer, contentType: string): Promise<void> {
  const supabase = storeClient();
  if (!supabase) return;
  const { error } = await supabase.storage.from(MEDIA_BUCKET).upload(key, data, { contentType, upsert: false });
  if (error && !/already exists|Duplicate|409/i.test(describeError(error))) throw error;
}

/**
 * The record of one generation. Created when the generation starts; every call queues its upload and returns at
 * once. `done()` waits for what is queued (the generation is finished then).
 */
export class MediaLog {
  private queue: Promise<void> = Promise.resolve();
  private started: Promise<boolean> | null = null;
  private warned = false;
  private seen = new Set<string>();

  constructor(readonly id: string, private onProblem: (text: string) => void = () => {}) {}

  get enabled(): boolean {
    return mediaEnabled();
  }

  private later(work: () => Promise<void>) {
    if (!this.enabled) return;
    this.queue = this.queue.then(work).catch((error) => {
      if (this.warned) return;
      this.warned = true;
      this.onProblem(`Keeping this lecture's pictures and programs in Supabase failed (${describeError(error).slice(0, 200)}); ` +
        "the lecture goes on. Is harness/supabase/migrations/0003_generated_media.sql applied?");
    });
  }

  /** The generation's row, written once before anything that refers to it. */
  private ensure(): Promise<boolean> {
    this.started ??= (async () => {
      const supabase = storeClient();
      if (!supabase) return false;
      const { error } = await supabase.from("generations").upsert({ id: this.id }, { onConflict: "id", ignoreDuplicates: true });
      if (error) throw error;
      return true;
    })();
    return this.started;
  }

  /** What the generation was asked and how: its title, models, options and the content (shortened). Called again
   * with what is learnt later (the lecture's own title). */
  describe(row: Record<string, unknown>) {
    this.later(async () => {
      await this.ensure();
      const { error } = await storeClient()!.from("generations").update(tidy(row)).eq("id", this.id);
      if (error) throw error;
    });
  }

  /** How it ended: the number of videos, the cost, its state. */
  finish(row: { state: "finished" | "failed" | "stopped"; videos?: number; cost_usd?: number; error?: string;
    minutes?: number }) {
    this.later(async () => {
      await this.ensure();
      const { error } = await storeClient()!.from("generations")
        .update(tidy({ ...row, finished_at: new Date().toISOString() })).eq("id", this.id);
      if (error) throw error;
    });
  }

  /** A picture the generation made or used, with its context. The same file used again is one more use. */
  picture(item: MediaItem) {
    const use = `${item.file}|${item.role}|${JSON.stringify(item.context ?? {})}`;
    if (this.seen.has(use)) return;
    this.seen.add(use);
    this.later(async () => {
      let data: Buffer;
      try {
        if (!(await stat(item.file)).isFile()) return;
        data = await readFile(item.file);
      } catch {
        return;                                   // a picture whose file is gone is left out of the record
      }
      await this.ensure();
      const supabase = storeClient()!;
      const digest = sha256(data);
      const ext = path.extname(item.file).toLowerCase() || ".bin";
      const key = `media/${digest}${ext}`;            // one copy of the bytes, whatever they are used as
      await upload(key, data, TYPES[ext] ?? "application/octet-stream");
      const { error } = await supabase.from("media").upsert({
        digest, kind: item.kind, content_type: TYPES[ext] ?? "application/octet-stream", byte_size: data.length,
        storage_path: key, description: item.description.slice(0, 4000) || path.basename(item.file),
        metadata: tidy(item.metadata),
      }, { onConflict: "digest", ignoreDuplicates: true });
      if (error) throw error;
      const { error: useError } = await supabase.from("generation_media").insert({
        generation_id: this.id, digest, role: item.role.slice(0, 200), context: tidy(item.context),
        usd: item.usd ?? null, reused: !!item.reused,
      });
      if (useError) throw useError;
    });
  }

  /** Each video's Manim source, as the generation wrote it (programs built from it find their generation by it). */
  scenes(parts: { part: number; title?: string; minutes?: number; source: string }[]) {
    this.later(async () => {
      await this.ensure();
      const rows = parts.map((p) => ({ generation_id: this.id, part: p.part, title: p.title ?? null,
        minutes: p.minutes ?? null, source_digest: sha256(p.source), source: p.source }));
      if (!rows.length) return;
      const { error } = await storeClient()!.from("generation_scenes").upsert(rows, { onConflict: "generation_id,source_digest" });
      if (error) throw error;
    });
  }

  /** The web and library pictures a compiled video shows (compile_lecture.pictures_used), each with its line. */
  compiled(pictures: CompiledPicture[] | undefined, video?: { index?: number; title?: string }) {
    for (const p of pictures ?? []) {
      this.picture({
        file: p.file, kind: p.kind, description: p.description, role: p.role,
        metadata: { found_by: p.found_by, ...(p.source ?? {}) },
        context: { ...(p.context ?? {}), video: video?.index, video_title: video?.title },
      });
    }
  }

  /** Wait for everything queued. */
  async done(): Promise<void> {
    await this.queue;
  }
}

/**
 * A .panim program a build made (app/api/export), kept by default with what it was built from: the scene source's
 * digest finds the generation that wrote it (generation_scenes), so a program is compared with the run it came
 * from. Returns where it went, or null (off, or no program).
 */
export async function keepProgram(program: string, info: { source: string; sceneClass: string; tier?: number;
  frames?: number; narrated?: boolean; buildSeconds?: number }): Promise<string | null> {
  const supabase = storeClient();
  if (!supabase || process.env.PANIM_STORE_MEDIA === "0") return null;
  const data = await readFile(program);
  const digest = sha256(data);
  const key = `programs/${digest}.panim`;
  await upload(key, data, TYPES[".panim"]);
  const sourceDigest = sha256(info.source);
  const { data: scene } = await supabase.from("generation_scenes").select("generation_id, title")
    .eq("source_digest", sourceDigest).order("created_at", { ascending: false }).limit(1).maybeSingle();
  const { error } = await supabase.from("programs").insert({
    digest, storage_path: key, byte_size: data.length, scene_class: info.sceneClass, source_digest: sourceDigest,
    generation_id: scene?.generation_id ?? null, title: scene?.title ?? null, tier: info.tier ?? null,
    frames: info.frames ?? null, narrated: !!info.narrated, build_seconds: info.buildSeconds ?? null,
  });
  if (error) throw error;
  return key;
}
