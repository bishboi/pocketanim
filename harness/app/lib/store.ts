/**
 * Persistence, and what happens without it.
 *
 * The schema in harness/supabase is the shape of record. But a harness that
 * cannot run without a configured project is a harness nobody can try, so
 * every function here is a no-op when the environment is not set, and the
 * pipeline does not read anything back that it needs. Storage is a record of
 * what happened, not a step in making it happen.
 *
 * What is never stored, per the brief and enforced by the schema's own
 * `assets_no_video` constraint: rendered video. The durable artifacts are the
 * Manim source, the exported program and its assets.
 */

import { createClient, SupabaseClient } from "@supabase/supabase-js";
import type { ExportResult } from "./pocketanim";

export type StoreStatus =
  | { configured: false; reason: string }
  | { configured: true; sceneVersionId: string; buildId: string }
  | { configured: true; error: string };

let cached: SupabaseClient | null = null;

function client(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  cached ??= createClient(url, key, { auth: { persistSession: false } });
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

export function storeConfigured(): boolean {
  return client() !== null;
}

export async function saveVersion(input: {
  source: string;
  sceneClass: string;
  instruction: string | null;
  model: string | null;
  result: ExportResult;
}): Promise<StoreStatus> {
  const supabase = client();
  if (!supabase) {
    return {
      configured: false,
      reason: "NEXT_PUBLIC_SUPABASE_URL and a key are not set",
    };
  }

  try {
    const { data: scene, error: sceneError } = await supabase
      .from("scenes")
      .insert({ title: input.sceneClass })
      .select("id")
      .single();
    if (sceneError) throw sceneError;

    const { data: version, error: versionError } = await supabase
      .from("scene_versions")
      .insert({
        scene_id: scene.id,
        version: 1,
        source: input.source,
        instruction: input.instruction,
        model: input.model,
      })
      .select("id")
      .single();
    if (versionError) throw versionError;

    // The build row carries the verdict, and the schema refuses a succeeded
    // build that cannot show its work -- tier and program both present.
    const succeeded = input.result.tier === 1;
    const { data: build, error: buildError } = await supabase
      .from("builds")
      .insert({
        scene_version_id: version.id,
        state: succeeded ? "succeeded" : "failed",
        tier: input.result.tier === 1 ? "tier1" : input.result.tier === 3 ? "tier3" : null,
        program_path: succeeded ? `${input.sceneClass}.panim` : null,
        error: succeeded
          ? null
          : (input.result.error ?? input.result.blockers?.join("; ") ?? "unknown"),
      })
      .select("id")
      .single();
    if (buildError) throw buildError;

    return { configured: true, sceneVersionId: version.id, buildId: build.id };
  } catch (error) {
    // A storage failure must not lose the user's generated scene, which is
    // still on screen and still exportable.
    return {
      configured: true,
      error: describeError(error),
    };
  }
}
