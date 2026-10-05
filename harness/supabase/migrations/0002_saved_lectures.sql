-- Saved lectures, and the phone's catalog of them.
--
-- What changed since 0001: a lecture is now made as a series of micro-lectures (app/lib/topics.ts), one video
-- per topic, and a user saves it with Save. A saved lecture is a PROJECT (the series); each of its videos is a
-- SCENE (ordinal = its place in the series), with the version that was saved and the BUILD exported from it.
-- The build's phone library -- the .panim program, its assets, the glyph atlas and the narration, the same
-- folder the player opens (tools/build_library.py) -- is in Supabase Storage, in the bucket `lectures`:
--
--   builds/<build id>/library.json, scenes/<Scene>.panim, scenes/<Scene>.json, library.atlas, audio/<Scene>.wav
--   assets/<digest>.panm              content-addressed, shared by every build that uses it (the assets table)
--
-- The library's own "assets/<digest>.panm" paths are read from the shared folder at the bucket's root.
--
-- The phone lists what has been saved from the view `phone_lectures` and downloads a lecture's folder. Safe to
-- re-run, like 0001.

-- ---------------------------------------------------------------------------
-- Projects: what a saved lecture is about
-- ---------------------------------------------------------------------------

alter table projects add column if not exists subject  text;
alter table projects add column if not exists language text;
alter table projects add column if not exists minutes  numeric;

-- ---------------------------------------------------------------------------
-- Scenes: one per video of a series
-- ---------------------------------------------------------------------------

-- Every lecture video's Python class is GeneratedScene: the parts of a series share it, and the ordinal is what
-- tells them apart (unique (project_id, ordinal) stays).
alter table scenes drop constraint if exists scenes_project_id_class_name_key;

alter table scenes add column if not exists minutes numeric;
-- The series it belongs to: "Lecture 2 of 3".
alter table scenes add column if not exists part_of integer check (part_of is null or part_of >= 1);

-- ---------------------------------------------------------------------------
-- Builds: where the phone library is, and whether the phone may list it
-- ---------------------------------------------------------------------------

-- The library folder in the `lectures` bucket (builds/<build id>), its size, and the narration in it.
alter table builds add column if not exists library_path  text;
alter table builds add column if not exists library_bytes bigint check (library_bytes is null or library_bytes >= 0);
alter table builds add column if not exists audio_path    text;
-- Saved for the phone. Only a succeeded tier-1 build with its library uploaded may be: the phone plays programs,
-- and a row it cannot download is a dead entry in its list.
alter table builds add column if not exists published     boolean not null default false;

do $$ begin
  alter table builds add constraint builds_published_is_playable check (
    not published or (state = 'succeeded' and tier = 'tier1' and library_path is not null)
  );
exception when duplicate_object then null; end $$;

create index if not exists builds_published_idx on builds (finished_at desc) where published;

-- ---------------------------------------------------------------------------
-- The phone's catalog
-- ---------------------------------------------------------------------------

-- What the player app lists: every published lecture video, newest series first, its videos in order. A view so
-- the phone (signed in or not, with the project's anon key) reads exactly these columns of exactly these rows;
-- the tables' own policies still keep everything else to its owner. It runs with its owner's rights, which is
-- what lets the anon role read the published rows and nothing more.
create or replace view phone_lectures as
select
  b.id               as build_id,
  p.id               as project_id,
  p.title            as series,
  p.subject          as subject,
  p.language         as language,
  s.ordinal          as lecture,
  coalesce(s.part_of, 1) as lectures,
  coalesce(nullif(s.title, ''), p.title) as title,
  s.minutes          as minutes,
  b.library_path     as library_path,
  b.library_bytes    as library_bytes,
  b.program_bytes    as program_bytes,
  b.frame_count      as frame_count,
  b.fps              as fps,
  (b.audio_path is not null) as narrated,
  b.finished_at      as saved_at
from builds b
join scene_versions v on v.id = b.scene_version_id
join scenes s on s.id = v.scene_id
join projects p on p.id = s.project_id
where b.published;

do $$ begin
  grant select on phone_lectures to anon;
exception when undefined_object then null; end $$;
do $$ begin
  grant select on phone_lectures to authenticated;
exception when undefined_object then null; end $$;

-- ---------------------------------------------------------------------------
-- Storage: the bucket the libraries are in
-- ---------------------------------------------------------------------------

-- Public for reading: a library's path holds its build's random id, and the phone downloads it without signing
-- in. Writing is the service role's alone (the web app's Save), as for the assets table. Skipped where there is
-- no Supabase Storage (a bare Postgres in harness/scripts/test-schema.sh).
do $$ begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public)
    values ('lectures', 'lectures', true)
    on conflict (id) do update set public = true;
  end if;
end $$;
