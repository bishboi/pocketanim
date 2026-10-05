-- What the schema promises, as statements that must be refused.
--
-- A constraint nobody has seen reject anything is a comment. Run by
-- `harness/scripts/test-schema.sh`, which applies the migration to a scratch
-- database and checks that every statement below fails.
--
\set ON_ERROR_STOP off
\set QUIET on
-- A user and the happy path: template -> project -> scene -> version -> build.
insert into auth.users (id, email) values ('11111111-1111-1111-1111-111111111111','a@b.c');
insert into templates (slug, name, is_builtin, requires, palette)
  values ('map-walkthrough','Map walkthrough', true, '{cartopy}', '{"bg":"#000"}');
insert into projects (id, owner_id, title, content, template_id)
  values ('22222222-2222-2222-2222-222222222222','11111111-1111-1111-1111-111111111111',
          'Coastlines','some content', (select id from templates where slug='map-walkthrough'));
insert into scenes (id, project_id, ordinal, class_name, transcript)
  values ('33333333-3333-3333-3333-333333333333','22222222-2222-2222-2222-222222222222',
          0,'CoastlineIntro','Here is the coast.');
insert into scene_versions (id, scene_id, version, source)
  values ('44444444-4444-4444-4444-444444444444','33333333-3333-3333-3333-333333333333',1,'from manim import *');
insert into assets (digest, byte_size, content_type) values ('d43c418bf3', 811764, 'application/octet-stream');
insert into builds (id, scene_version_id, state, tier, program_path, program_bytes)
  values ('55555555-5555-5555-5555-555555555555','44444444-4444-4444-4444-444444444444',
          'succeeded','tier1','programs/abc.panim',277);
insert into build_assets values ('55555555-5555-5555-5555-555555555555','d43c418bf3');
-- A saved series (0002): two videos of one lecture, both GeneratedScene, told apart by ordinal; one published.
insert into scenes (id, project_id, ordinal, class_name, title, minutes, part_of)
  values ('66666666-6666-6666-6666-666666666666','22222222-2222-2222-2222-222222222222',1,'GeneratedScene','Newton',24,2),
         ('77777777-7777-7777-7777-777777777777','22222222-2222-2222-2222-222222222222',2,'GeneratedScene','Friction',26,2);
insert into scene_versions (id, scene_id, version, source)
  values ('88888888-8888-8888-8888-888888888888','66666666-6666-6666-6666-666666666666',1,'from manim import *');
insert into builds (id, scene_version_id, state, tier, program_path, library_path, library_bytes, published)
  values ('99999999-9999-9999-9999-999999999999','88888888-8888-8888-8888-888888888888',
          'succeeded','tier1','builds/9999/scenes/GeneratedScene.panim','builds/9999',150000,true);
\echo '--- happy path inserted'
select series, lecture, lectures, title, library_path from phone_lectures;

\echo '--- each of these MUST fail:'
\echo '1. storing a video asset'
insert into assets (digest, byte_size, content_type) values ('aaaaaaaaaa', 1, 'video/mp4');
\echo '2. a build that succeeded with no program'
insert into builds (scene_version_id, state, tier) values ('44444444-4444-4444-4444-444444444444','succeeded','tier1');
\echo '3. a build that failed without saying why'
insert into builds (scene_version_id, state) values ('44444444-4444-4444-4444-444444444444','failed');
\echo '4. a built-in template with an owner'
insert into templates (slug,name,is_builtin,owner_id) values ('x','X',true,'11111111-1111-1111-1111-111111111111');
\echo '5. a scene whose class_name is not a Python class name'
insert into scenes (project_id,ordinal,class_name) values ('22222222-2222-2222-2222-222222222222',9,'not a class');
\echo '6. two scenes at the same ordinal'
insert into scenes (project_id,ordinal,class_name) values ('22222222-2222-2222-2222-222222222222',0,'Other');
\echo '7. deleting an asset a build still needs'
delete from assets where digest = 'd43c418bf3';
\echo '8. publishing a build for the phone with no library to download'
insert into builds (scene_version_id, state, tier, program_path, published)
  values ('44444444-4444-4444-4444-444444444444','succeeded','tier1','programs/x.panim',true);
