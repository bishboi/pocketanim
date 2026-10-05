/**
 * Saving a lecture: the database rows of record and the phone library in Supabase Storage.
 *
 * Nothing is saved until the user presses Save: generating and building need no database, which is what lets the
 * harness run with none. Save takes the version on screen -- one video, or every micro-lecture of a series
 * (topics.ts) -- and for each video:
 *
 *   - a project (the series), a scene (ordinal = its place in the series), the version's Manim source, and a build;
 *   - its phone library (packLibrary: the .panim program, its assets, the glyph atlas, the narration) uploaded to
 *     the `lectures` bucket: builds/<build id>/... and each asset once, content-addressed, at assets/<digest>.panm,
 *     indexed in the assets table and tied to the build in build_assets;
 *   - the build marked succeeded and published, so the phone's catalog (the view phone_lectures) lists it.
 *
 * The schema is harness/supabase/migrations. What is never stored, per the brief and the schema's own
 * `assets_no_video` constraint: rendered video. Writing needs the service role key: the tables and the bucket are
 * written by the server alone.
 */

import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { packLibrary } from "./pocketanim";

export const BUCKET = "lectures";

let cached: SupabaseClient | null = null;

function client(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return null;
  cached ??= createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
  return cached;
}

function describeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (error && typeof error === "object") {
    const record = error as { message?: unknown; details?: unknown; hint?: unknown; code?: unknown };
    const parts = [record.message, record.details, record.hint, record.code].filter(
      (part): part is string => typeof part === "string" && part.length > 0,
    );
    if (parts.length) return parts.join(" — ");
    try {
      return JSON.stringify(error);
    } catch {
      return "storage request failed";
    }
  }
  return String(error);
}

/** Why Save is unavailable, or null when it can run. */
export function storeProblem(): string | null {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL) return "NEXT_PUBLIC_SUPABASE_URL is not set";
  if (!process.env.SUPABASE_SERVICE_ROLE_KEY) {
    return "SUPABASE_SERVICE_ROLE_KEY is not set (saving writes the tables and the lectures bucket, which only the " +
      "service role may)";
  }
  return null;
}

export function storeConfigured(): boolean {
  return client() !== null;
}

/**
 * Whose the saved lectures are: PANIM_OWNER_ID, or the user PANIM_OWNER_EMAIL (harness@pocketanim.local by
 * default), created on first use. The harness has no sign-in; every project needs an owner (projects.owner_id).
 */
async function ownerId(supabase: SupabaseClient): Promise<string> {
  const set = process.env.PANIM_OWNER_ID?.trim();
  if (set) return set;
  const email = (process.env.PANIM_OWNER_EMAIL?.trim() || "harness@pocketanim.local").toLowerCase();
  for (let page = 1; page <= 20; page++) {
    const { data, error } = await supabase.auth.admin.listUsers({ page, perPage: 200 });
    if (error) throw error;
    const users = data.users as { id: string; email?: string }[];
    const found = users.find((u) => u.email?.toLowerCase() === email);
    if (found) return found.id;
    if (users.length < 200) break;
  }
  const { data, error } = await supabase.auth.admin.createUser({ email, email_confirm: true });
  if (error) throw error;
  return data.user.id;
}

export type SavePart = {
  buildDir: string;
  sceneClass: string;
  source: string;
  title: string;
  minutes?: number;
  instruction?: string | null;
  model?: string | null;
  transcript?: string;
  inputTokens?: number;
  outputTokens?: number;
};

export type SaveRequest = {
  /** The series' title (a single video's own title when there is one). */
  title: string;
  content?: string;
  subject?: string;
  language?: string;
  parts: SavePart[];
};

export type SavedLecture = { lecture: number; title: string; buildId: string; libraryPath: string; bytes: number };

export type SaveResult =
  | { saved: true; projectId: string; lectures: SavedLecture[]; skipped: string[] }
  | { saved: false; error: string };

const CONTENT_TYPES: Record<string, string> = {
  ".json": "application/json",
  ".panim": "text/plain; charset=utf-8",
  ".wav": "audio/wav",
};

async function filesUnder(dir: string, prefix = ""): Promise<string[]> {
  const out: string[] = [];
  for (const entry of await readdir(path.join(dir, prefix), { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) out.push(...(await filesUnder(dir, rel)));
    else out.push(rel);
  }
  return out;
}

/** An upload that already exists is fine for a content-addressed asset: the same digest is the same bytes. */
function alreadyThere(error: unknown): boolean {
  const said = describeError(error);
  return /already exists|Duplicate|409/i.test(said);
}

async function uploadLibrary(supabase: SupabaseClient, dir: string, buildId: string) {
  const files = await filesUnder(dir);
  let bytes = 0;
  const assets: { digest: string; size: number }[] = [];
  for (const rel of files) {
    const data = await readFile(path.join(dir, rel));
    bytes += data.length;
    const asset = /^assets\/([0-9a-f]{10,64})\.panm$/.exec(rel);
    const key = asset ? rel : `builds/${buildId}/${rel}`;
    const contentType = CONTENT_TYPES[path.extname(rel)] ?? "application/octet-stream";
    const { error } = await supabase.storage.from(BUCKET).upload(key, data, { contentType, upsert: !asset });
    if (error && !(asset && alreadyThere(error))) throw new Error(`uploading ${rel}: ${describeError(error)}`);
    if (asset) assets.push({ digest: asset[1], size: data.length });
  }
  return { files, bytes, assets };
}

/** Save a lecture, every video of it. Each video that cannot be saved is reported; the rest are kept. */
export async function saveLecture(request: SaveRequest): Promise<SaveResult> {
  const problem = storeProblem();
  const supabase = client();
  if (problem || !supabase) return { saved: false, error: `Saving is not set up: ${problem}` };
  if (!request.parts.length) return { saved: false, error: "nothing to save" };
  try {
    const owner = await ownerId(supabase);
    const minutes = request.parts.reduce((n, p) => n + (p.minutes ?? 0), 0);
    const { data: project, error: projectError } = await supabase
      .from("projects")
      .insert({
        owner_id: owner,
        title: request.title.slice(0, 300) || "Untitled",
        content: (request.content ?? "").slice(0, 200_000),
        subject: request.subject ?? null,
        language: request.language ?? null,
        minutes: minutes || null,
      })
      .select("id")
      .single();
    if (projectError) throw projectError;

    const lectures: SavedLecture[] = [];
    const skipped: string[] = [];
    for (const [k, part] of request.parts.entries()) {
      const label = request.parts.length > 1 ? `lecture ${k + 1} (${part.title})` : part.title;
      const { data: scene, error: sceneError } = await supabase
        .from("scenes")
        .insert({
          project_id: project.id,
          ordinal: k + 1,
          class_name: part.sceneClass,
          // The topic's own name: "Lecture 2 of 3" is its ordinal and part_of, not part of its title.
          title: part.title.replace(/^Lecture \d+:\s*/, "").slice(0, 300),
          transcript: (part.transcript ?? "").slice(0, 500_000),
          minutes: part.minutes ?? null,
          part_of: request.parts.length,
        })
        .select("id")
        .single();
      if (sceneError) throw sceneError;
      const { data: version, error: versionError } = await supabase
        .from("scene_versions")
        .insert({
          scene_id: scene.id,
          version: 1,
          source: part.source,
          instruction: part.instruction ?? null,
          model: part.model ?? null,
          input_tokens: part.inputTokens ?? null,
          output_tokens: part.outputTokens ?? null,
        })
        .select("id")
        .single();
      if (versionError) throw versionError;
      const started = new Date();
      const { data: build, error: buildError } = await supabase
        .from("builds")
        .insert({ scene_version_id: version.id, state: "running", started_at: started.toISOString() })
        .select("id")
        .single();
      if (buildError) throw buildError;

      const fail = async (why: string) => {
        skipped.push(`${label}: ${why}`);
        await supabase.from("builds").update({ state: "failed", error: why.slice(0, 2000),
          finished_at: new Date().toISOString() }).eq("id", build.id);
      };
      const packed = await packLibrary(part.buildDir, part.sceneClass);
      if ("error" in packed) {
        await fail(packed.error);
        continue;
      }
      let uploaded;
      try {
        uploaded = await uploadLibrary(supabase, packed.dir, build.id);
      } catch (error) {
        await fail(describeError(error));
        continue;
      }
      const manifest = JSON.parse(await readFile(path.join(packed.dir, "library.json"), "utf8")) as {
        scenes?: { name: string; tier?: number; program?: string; frames?: number; audio?: string }[];
      };
      const entry = manifest.scenes?.find((s) => s.name === packed.sceneClass) ?? manifest.scenes?.[0];
      if (!entry?.program || entry.tier !== 1) {
        await fail("the build has no program the phone can play (not tier 1)");
        continue;
      }
      if (uploaded.assets.length) {
        const { error: assetError } = await supabase.from("assets").upsert(
          uploaded.assets.map((a) => ({ digest: a.digest, byte_size: a.size, content_type: "application/octet-stream" })),
          { onConflict: "digest", ignoreDuplicates: true });
        if (assetError) throw assetError;
        const { error: linkError } = await supabase.from("build_assets").insert(
          [...new Set(uploaded.assets.map((a) => a.digest))].map((digest) => ({ build_id: build.id, digest })));
        if (linkError) throw linkError;
      }
      const program = await stat(path.join(packed.dir, entry.program));
      const finished = new Date();
      const libraryPath = `builds/${build.id}`;
      const { error: doneError } = await supabase
        .from("builds")
        .update({
          state: "succeeded",
          tier: "tier1",
          program_path: `${libraryPath}/${entry.program}`,
          program_bytes: program.size,
          frame_count: entry.frames ?? null,
          fps: 30,
          library_path: libraryPath,
          library_bytes: uploaded.bytes,
          audio_path: entry.audio ? `${libraryPath}/${entry.audio}` : null,
          published: true,
          finished_at: finished.toISOString(),
          duration_ms: finished.getTime() - started.getTime(),
        })
        .eq("id", build.id);
      if (doneError) throw doneError;
      lectures.push({ lecture: k + 1, title: part.title, buildId: build.id, libraryPath, bytes: uploaded.bytes });
    }
    if (!lectures.length) return { saved: false, error: `Nothing could be saved: ${skipped.join("; ")}` };
    return { saved: true, projectId: project.id, lectures, skipped };
  } catch (error) {
    return { saved: false, error: describeError(error) };
  }
}
