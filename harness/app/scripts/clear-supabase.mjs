// Clear the generation history kept in Supabase (harness/scripts/clear_all.sh --supabase): every generation's
// row, its pictures, scenes and programs (0003_generated_media.sql) and the files in the `media` bucket. With
// --saved, also the saved lectures the phone lists (projects, their scenes, versions and builds, the assets, and
// the `lectures` bucket). Uses the server's service-role key from the environment or .env.local.
//
//   node scripts/clear-supabase.mjs [--saved]

import { readFileSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";

function env(name) {
  if (process.env[name]) return process.env[name];
  try {
    const text = readFileSync(path.join(process.cwd(), ".env.local"), "utf8");
    const line = text.split(/\r?\n/).find((l) => l.trim().startsWith(`${name}=`));
    return line ? line.slice(line.indexOf("=") + 1).trim().replace(/^["']|["']$/g, "") : undefined;
  } catch {
    return undefined;
  }
}

const url = env("NEXT_PUBLIC_SUPABASE_URL");
const key = env("SUPABASE_SERVICE_ROLE_KEY");
if (!url || !key) {
  console.error("Supabase not cleared: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are needed " +
    "(in harness/app/.env.local).");
  process.exit(1);
}
const saved = process.argv.includes("--saved");
const db = createClient(url, key, { auth: { persistSession: false } });

/** Every file under a prefix of a bucket (folders are listed by name with no id). */
async function files(bucket, prefix = "") {
  const out = [];
  for (let offset = 0; ; offset += 1000) {
    const { data, error } = await db.storage.from(bucket).list(prefix, { limit: 1000, offset });
    if (error) throw new Error(`${bucket}/${prefix}: ${error.message}`);
    for (const item of data ?? []) {
      const full = prefix ? `${prefix}/${item.name}` : item.name;
      if (item.id) out.push(full);
      else out.push(...await files(bucket, full));
    }
    if (!data || data.length < 1000) return out;
  }
}

async function emptyBucket(bucket) {
  let all;
  try {
    all = await files(bucket);
  } catch (e) {
    console.log(`  bucket ${bucket}: ${e.message}`);
    return;
  }
  for (let i = 0; i < all.length; i += 100) {
    const { error } = await db.storage.from(bucket).remove(all.slice(i, i + 100));
    if (error) throw new Error(`${bucket}: ${error.message}`);
  }
  console.log(`  bucket ${bucket}: ${all.length} files removed`);
}

/** Delete every row of a table (a filter that every row passes: the API refuses a delete with none). */
async function emptyTable(table, column) {
  const { error, count } = await db.from(table).delete({ count: "exact" }).not(column, "is", null);
  if (error) {
    // A table a migration has not made yet is nothing to clear.
    if (/does not exist|schema cache/i.test(error.message)) return console.log(`  ${table}: not there`);
    throw new Error(`${table}: ${error.message}`);
  }
  console.log(`  ${table}: ${count ?? 0} rows removed`);
}

console.log("Clearing Supabase generation history");
for (const [table, column] of [["generation_media", "id"], ["programs", "id"], ["generation_scenes", "source_digest"],
  ["media", "digest"], ["generations", "id"]]) {
  await emptyTable(table, column);
}
await emptyBucket("media");

if (saved) {
  console.log("Clearing saved lectures");
  // Projects take their scenes, versions, builds and build assets with them (on delete cascade).
  await emptyTable("build_assets", "build_id");
  await emptyTable("projects", "id");
  await emptyTable("assets", "digest");
  await emptyBucket("lectures");
}
console.log("Supabase cleared.");
