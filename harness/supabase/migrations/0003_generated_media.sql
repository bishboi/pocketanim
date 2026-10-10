-- Everything a lecture generation makes, kept by default (app/lib/media.ts), so runs can be saved and compared.
--
-- What changed since 0002: until now nothing was stored until the user pressed Save, and then only the phone
-- library. Now, as a lecture is made, the server keeps (PANIM_STORE_MEDIA=0 turns it off):
--
--   GENERATIONS        one row per lecture made: what it was asked, the models, its length and cost.
--   MEDIA              every picture it made or used, once per distinct file (content-addressed by its SHA-256):
--                      SVG drawings, book figures redrawn as SVG, AI illustrations, book photos and the web
--                      photos found like them, and the web and library pictures the compiler fetched. Each with
--                      what it shows (description) and where it came from (source, credit, licence, model).
--   GENERATION_MEDIA   where each picture was used in a generation: the chapter, the line said over it, the
--                      section, the diagram node or map label it sits beside, what it cost. A file used twice is
--                      two rows here and one in MEDIA.
--   GENERATION_SCENES  each video's Manim source, as the generation wrote it.
--   PROGRAMS           each .panim program built from a scene (every build, not only saved ones), with its frames
--                      and size, linked to its generation through the scene source's digest.
--
-- The files are in the private Storage bucket `media`:
--
--   media/<sha256>.<ext>              a picture (svg, png, jpg, webp); its kind and description are in MEDIA
--   programs/<sha256>.panim           a program
--
-- Written by the server's service role alone; nothing here is for the phone. Safe to re-run, like 0001 and 0002.

-- ---------------------------------------------------------------------------
-- Generations
-- ---------------------------------------------------------------------------

create table if not exists generations (
  id                text primary key,                    -- the generate job's id (lib/jobs.ts)
  created_at        timestamptz not null default now(),
  finished_at       timestamptz,
  title             text,
  template          text,
  model             text,
  transcript_model  text,
  svg_model         text,
  subject           text,
  language          text,
  art               text,
  minutes           numeric,                             -- asked for, or estimated from the source
  videos            integer check (videos is null or videos >= 1),
  cost_usd          numeric check (cost_usd is null or cost_usd >= 0),
  request           jsonb not null default '{}'::jsonb,  -- the content (shortened), the document, the options
  state             text not null default 'running' check (state in ('running', 'finished', 'failed', 'stopped')),
  error             text
);

create index if not exists generations_created_idx on generations (created_at desc);

-- ---------------------------------------------------------------------------
-- Media: each distinct picture once
-- ---------------------------------------------------------------------------

create table if not exists media (
  digest        text primary key check (digest ~ '^[0-9a-f]{64}$'),   -- SHA-256 of the file
  kind          text not null check (kind in (
                  'drawing',        -- a picture the lecture asked for, drawn as SVG (lib/drawings.ts)
                  'figure',         -- a book figure redrawn as SVG (lib/figures.ts)
                  'book-figure',    -- a book figure as the document has it (built in Manim instead)
                  'book-photo',     -- a book photograph, shown as it is
                  'photo',          -- a real photo: the web's like a book photo, or one the lecture asked for
                  'illustration'    -- an illustration: a library's, or one an image model drew
                )),
  content_type  text not null,
  byte_size     bigint not null check (byte_size >= 0),
  storage_path  text not null unique,                   -- in the `media` bucket
  description   text not null,                          -- what it shows
  metadata      jsonb not null default '{}'::jsonb,     -- parts, source, credit, licence, url, model
  created_at    timestamptz not null default now()
);

create index if not exists media_kind_idx on media (kind, created_at desc);

-- ---------------------------------------------------------------------------
-- Where each picture was used
-- ---------------------------------------------------------------------------

create table if not exists generation_media (
  id             bigint generated always as identity primary key,
  generation_id  text not null references generations (id) on delete cascade,
  digest         text not null references media (digest) on delete cascade,
  role           text not null,                         -- drawn, book figure, beside a label, a beat's photo...
  context        jsonb not null default '{}'::jsonb,    -- chapter, section, line said, diagram node, query
  usd            numeric check (usd is null or usd >= 0),
  reused         boolean not null default false,        -- found already made (a cache): nothing paid this run
  created_at     timestamptz not null default now()
);

create index if not exists generation_media_generation_idx on generation_media (generation_id);
create index if not exists generation_media_digest_idx on generation_media (digest);

-- ---------------------------------------------------------------------------
-- Scenes and programs
-- ---------------------------------------------------------------------------

create table if not exists generation_scenes (
  generation_id  text not null references generations (id) on delete cascade,
  part           integer not null check (part >= 1),    -- its place in the series (1 for a single video)
  title          text,
  minutes        numeric,
  source_digest  text not null check (source_digest ~ '^[0-9a-f]{64}$'),  -- SHA-256 of the Manim source
  source         text not null,
  created_at     timestamptz not null default now(),
  primary key (generation_id, source_digest)            -- a renumbered video is a source of its own
);

create index if not exists generation_scenes_source_idx on generation_scenes (source_digest);

create table if not exists programs (
  id             bigint generated always as identity primary key,
  digest         text not null check (digest ~ '^[0-9a-f]{64}$'),         -- SHA-256 of the .panim
  storage_path   text not null,                         -- in the `media` bucket
  byte_size      bigint not null check (byte_size >= 0),
  scene_class    text not null,
  source_digest  text not null check (source_digest ~ '^[0-9a-f]{64}$'),  -- the scene it was built from
  generation_id  text references generations (id) on delete set null,     -- when that scene came from one
  title          text,
  tier           integer,
  frames         integer check (frames is null or frames >= 0),
  narrated       boolean not null default false,
  build_seconds  integer,
  created_at     timestamptz not null default now()
);

create index if not exists programs_generation_idx on programs (generation_id, created_at desc);
create index if not exists programs_source_idx on programs (source_digest);

-- ---------------------------------------------------------------------------
-- Access: the server alone (its service role passes row-level security); no policy lets anyone else in.
-- ---------------------------------------------------------------------------

alter table generations       enable row level security;
alter table media             enable row level security;
alter table generation_media  enable row level security;
alter table generation_scenes enable row level security;
alter table programs          enable row level security;

-- The bucket: private (book figures and web photos keep their own licences; nothing here is published).
do $$ begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public)
    values ('media', 'media', false)
    on conflict (id) do nothing;
  end if;
end $$;
