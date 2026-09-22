-- Harness schema.
--
-- Shape of the thing: a user brings CONTENT and picks a TEMPLATE. That
-- produces SCENES, each of which has a transcript and a chain of SCENE
-- VERSIONS -- Manim source, one version per instruction the user gives.
-- Exporting a version produces a BUILD: a .panim program, its ASSETS, and a
-- tier verdict. Source and program are separate on purpose; one is what a
-- human edits and the other is what a phone plays.
--
-- Safe to re-run. Every statement is guarded, because this is applied by hand
-- against projects someone has already touched.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

do $$ begin
  create type build_state as enum ('pending', 'running', 'succeeded', 'failed');
exception when duplicate_object then null; end $$;

-- Which tier the exporter reached. 1 is a program of a few hundred bytes; 3 is
-- sampled frames, which on the corpus measured about a thousand times larger
-- for the same scene. It is a first-class column because a user should be able
-- to see that difference, and because a silent fall to 3 is the main way
-- generation goes wrong without anything appearing to break.
do $$ begin
  create type scene_tier as enum ('tier1', 'tier3');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- Templates: the kinds of video that can be made
-- ---------------------------------------------------------------------------

create table if not exists templates (
  id           uuid primary key default gen_random_uuid(),
  slug         text not null unique,
  name         text not null,
  description  text,

  -- Look. Separated from the prompt so a palette can be swapped without
  -- rewriting the instructions that shape the animation.
  palette      jsonb not null default '{}'::jsonb,
  typography   jsonb not null default '{}'::jsonb,
  pacing       jsonb not null default '{}'::jsonb,

  -- What the model is told, and what it is given to start from. The preamble
  -- is real Python prepended to generated source -- imports and helpers a
  -- template guarantees are present, so the model never has to guess whether
  -- cartopy is available.
  prompt       text not null default '',
  preamble     text not null default '',

  -- Python the worker must have installed for this template to export at all.
  -- A map template needs cartopy; a molecule template does not.
  requires     text[] not null default '{}',

  is_builtin   boolean not null default false,
  owner_id     uuid references auth.users (id) on delete cascade,
  created_at   timestamptz not null default now(),

  -- A built-in belongs to everyone, so it has no owner. Anything else must.
  constraint templates_ownership check (is_builtin = (owner_id is null))
);

-- ---------------------------------------------------------------------------
-- Projects: the content a user brought, and what to make of it
-- ---------------------------------------------------------------------------

create table if not exists projects (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null references auth.users (id) on delete cascade,
  title        text not null default 'Untitled',
  content      text not null default '',
  template_id  uuid references templates (id) on delete restrict,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists projects_owner_idx on projects (owner_id, updated_at desc);

-- ---------------------------------------------------------------------------
-- Scenes: one Manim Scene each, ordered within a project
-- ---------------------------------------------------------------------------

create table if not exists scenes (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects (id) on delete cascade,
  ordinal       integer not null,

  -- The name the exporter will know it by: a Python class name, so it has to
  -- be one. Checked here rather than discovered when export fails.
  class_name    text not null check (class_name ~ '^[A-Z][A-Za-z0-9_]*$'),
  title         text not null default '',

  -- What the scene says, as opposed to what it draws. The natural place for a
  -- human to steer meaning rather than visuals.
  transcript    text not null default '',

  created_at    timestamptz not null default now(),
  unique (project_id, ordinal),
  unique (project_id, class_name)
);

-- ---------------------------------------------------------------------------
-- Scene versions: the edit history, one version per instruction
-- ---------------------------------------------------------------------------

create table if not exists scene_versions (
  id           uuid primary key default gen_random_uuid(),
  scene_id     uuid not null references scenes (id) on delete cascade,
  version      integer not null,

  -- The Manim Python. The artifact of record on the source side.
  source       text not null,

  -- What the user asked for to get here. Null on the first version, which
  -- nothing asked for. This is the edit loop: a human gives an instruction, a
  -- version comes back, and the chain is the history of that conversation.
  instruction  text,
  parent_id    uuid references scene_versions (id) on delete set null,

  -- Provenance. Which model wrote it, and what it cost.
  model        text,
  input_tokens  integer,
  output_tokens integer,

  created_at   timestamptz not null default now(),
  unique (scene_id, version)
);

create index if not exists scene_versions_scene_idx
  on scene_versions (scene_id, version desc);

-- ---------------------------------------------------------------------------
-- Assets: content-addressed, shared across everything
-- ---------------------------------------------------------------------------

-- The glyph atlas is one file every text scene points at, so assets are keyed
-- by digest and shared rather than copied per build. Bytes live in Supabase
-- Storage under the digest; this table is the index.
create table if not exists assets (
  digest       text primary key check (digest ~ '^[0-9a-f]{10,64}$'),
  byte_size    bigint not null check (byte_size >= 0),
  content_type text not null default 'application/octet-stream',
  created_at   timestamptz not null default now(),

  -- The brief's one hard prohibition, made an invariant rather than a
  -- convention: no rendered video is ever stored. A schema that cannot hold it
  -- is a stronger guarantee than a rule someone has to remember.
  constraint assets_no_video check (content_type not like 'video/%')
);

-- ---------------------------------------------------------------------------
-- Builds: exporting a version, and what came back
-- ---------------------------------------------------------------------------

create table if not exists builds (
  id                uuid primary key default gen_random_uuid(),
  scene_version_id  uuid not null references scene_versions (id) on delete cascade,
  state             build_state not null default 'pending',

  tier              scene_tier,

  -- The exporter's own verdict, carried through rather than re-derived: it
  -- writes a blockers array naming each thing it could not express. That list
  -- is what tells a user why their scene is large, and it is the only honest
  -- source for it.
  blockers          jsonb not null default '[]'::jsonb,

  -- The .panim program, in Storage under this key. Small enough to inline,
  -- but kept beside the assets so one mechanism serves both.
  program_path      text,
  program_bytes     integer,
  frame_count       integer,
  fps               integer,

  started_at        timestamptz,
  finished_at       timestamptz,
  duration_ms       integer,
  error             text,
  created_at        timestamptz not null default now(),

  -- A build that succeeded has a tier and a program; one that failed has
  -- neither and should say why. Enforced because "succeeded with no output" is
  -- the state that wastes the most time to debug.
  constraint builds_succeeded_is_complete check (
    state <> 'succeeded' or (tier is not null and program_path is not null)
  ),
  constraint builds_failed_explains_itself check (
    state <> 'failed' or error is not null
  )
);

create index if not exists builds_version_idx
  on builds (scene_version_id, created_at desc);

-- Which assets a build needs. Many-to-many because assets are shared: two
-- scenes with text point at the same atlas.
create table if not exists build_assets (
  build_id  uuid not null references builds (id) on delete cascade,
  digest    text not null references assets (digest) on delete restrict,
  primary key (build_id, digest)
);

-- ---------------------------------------------------------------------------
-- Row-level security: everything is owned, nothing is shared by default
-- ---------------------------------------------------------------------------

alter table templates      enable row level security;
alter table projects       enable row level security;
alter table scenes         enable row level security;
alter table scene_versions enable row level security;
alter table builds         enable row level security;
alter table assets         enable row level security;
alter table build_assets   enable row level security;

-- Built-in templates are readable by anyone signed in; a user's own are theirs.
drop policy if exists templates_read on templates;
create policy templates_read on templates for select
  to authenticated using (is_builtin or owner_id = auth.uid());

drop policy if exists templates_write on templates;
create policy templates_write on templates for all
  to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists projects_own on projects;
create policy projects_own on projects for all
  to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- Everything below a project inherits its ownership. Written as an exists
-- against the chain rather than a denormalised owner column, so there is one
-- place ownership is defined and no way for the copies to disagree.
drop policy if exists scenes_own on scenes;
create policy scenes_own on scenes for all to authenticated
  using (exists (select 1 from projects p
                 where p.id = scenes.project_id and p.owner_id = auth.uid()))
  with check (exists (select 1 from projects p
                      where p.id = scenes.project_id and p.owner_id = auth.uid()));

drop policy if exists scene_versions_own on scene_versions;
create policy scene_versions_own on scene_versions for all to authenticated
  using (exists (select 1 from scenes s join projects p on p.id = s.project_id
                 where s.id = scene_versions.scene_id and p.owner_id = auth.uid()))
  with check (exists (select 1 from scenes s join projects p on p.id = s.project_id
                      where s.id = scene_versions.scene_id and p.owner_id = auth.uid()));

drop policy if exists builds_own on builds;
create policy builds_own on builds for all to authenticated
  using (exists (select 1 from scene_versions v
                 join scenes s on s.id = v.scene_id
                 join projects p on p.id = s.project_id
                 where v.id = builds.scene_version_id and p.owner_id = auth.uid()))
  with check (exists (select 1 from scene_versions v
                      join scenes s on s.id = v.scene_id
                      join projects p on p.id = s.project_id
                      where v.id = builds.scene_version_id and p.owner_id = auth.uid()));

-- Assets are content-addressed and therefore not secret: the digest is the
-- capability. Readable by anyone signed in, writable only by the service role,
-- which is the worker. A client that could insert asset rows could lie about
-- what a build contains.
drop policy if exists assets_read on assets;
create policy assets_read on assets for select to authenticated using (true);

drop policy if exists build_assets_read on build_assets;
create policy build_assets_read on build_assets for select to authenticated
  using (exists (select 1 from builds b
                 join scene_versions v on v.id = b.scene_version_id
                 join scenes s on s.id = v.scene_id
                 join projects p on p.id = s.project_id
                 where b.id = build_assets.build_id and p.owner_id = auth.uid()));

-- ---------------------------------------------------------------------------
-- Housekeeping
-- ---------------------------------------------------------------------------

create or replace function touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists projects_touch on projects;
create trigger projects_touch before update on projects
  for each row execute function touch_updated_at();
