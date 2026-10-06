"""Save, end to end: the web app's saveLecture (app/lib/store.ts) puts a series of micro-lectures in Supabase --
rows of record and each video's phone library in Storage -- and the phone's own code (player/core SavedLectures)
lists them, downloads them and opens them. Against a stand-in for Supabase (fixtures/mock_supabase.cjs); the rows
it was sent are then replayed into the real schema (harness/supabase/migrations) when a Postgres is at hand
(PANIM_TEST_DATABASE_URL), so its constraints and the phone's view judge them too."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

from forge.util import REPO

APP = REPO / "harness" / "app"
PHONE = REPO / "player" / "build" / "classes"
MOCK = Path(__file__).with_name("fixtures") / "mock_supabase.cjs"

sys.path.insert(0, str(REPO / "harness" / "lecture"))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def supabase():
    if not shutil.which("node"):
        pytest.skip("no Node")
    port = _free_port()
    mock = subprocess.Popen(["node", str(MOCK)], env={**os.environ, "PORT": str(port)},
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{url}/__dump", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield url
    mock.terminate()


def _build(tmp_path: Path) -> Path:
    """A small lecture, compiled and exported as the web app would, in a build folder it accepts."""
    import compile_lecture as cl

    script = {"title": "Forces", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
              "chapters": [{"title": "Push and pull", "beats": [
                  {"say": "A force is a push or a pull.", "do": [{"op": "fact", "text": "Force: a push or a pull"}]},
                  {"say": "It can change how a thing moves.", "do": [{"op": "define", "term": "Force",
                                                                      "meaning": "a push or a pull"}]}]}]}
    scene = tmp_path / "lecture.py"
    scene.write_text(cl.compile_script(script))
    build = Path(tempfile.mkdtemp(prefix="panim-build-", dir=tempfile.gettempdir()))
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(build)], capture_output=True, text=True, timeout=600,
                         env={**os.environ, "PANIM_VOICE": "silent"})
    assert json.loads(out.stdout.strip().splitlines()[-1])["tier"] == 1, out.stderr[-2000:]
    (build / "source.py").write_text(scene.read_text())
    return build


def test_a_saved_series_is_listed_downloaded_and_played_by_the_phone(tmp_path, supabase):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not (PHONE / "core").is_dir() or not shutil.which("java"):
        pytest.skip("needs the app's TypeScript compiler and the built player (player/build.sh)")
    js = tmp_path / "js"
    built = subprocess.run([str(tsc), "lib/store.ts", "--outDir", str(js), "--module", "commonjs", "--target",
                            "es2022", "--skipLibCheck", "--esModuleInterop", "--moduleResolution", "node",
                            "--resolveJsonModule", "--rootDir", "."], cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    build = _build(tmp_path)
    try:
        parts = [{"buildDir": str(build), "sceneClass": "GeneratedScene", "source": "from manim import *",
                  "title": f"Lecture {k}: {name}", "minutes": m, "model": "test"}
                 for k, (name, m) in enumerate([("Newton", 24), ("Friction", 26)], 1)]
        script = (f"require({json.dumps(str(js / 'lib' / 'store.js'))}).saveLecture("
                  f"{json.dumps({'title': 'Forces', 'subject': 'physics', 'parts': parts})})"
                  ".then((r) => console.log(JSON.stringify(r)));")
        env = {**os.environ, "NODE_PATH": str(APP / "node_modules"), "NEXT_PUBLIC_SUPABASE_URL": supabase,
               "SUPABASE_SERVICE_ROLE_KEY": "service-test"}
        done = subprocess.run(["node", "-e", script], cwd=APP, capture_output=True, text=True, timeout=600, env=env)
        saved = json.loads(done.stdout.strip().splitlines()[-1])
        assert saved["saved"], saved
        assert [s["lecture"] for s in saved["lectures"]] == [1, 2] and not saved["skipped"]

        # A video saved on its own later (a series' failed build, rebuilt) keeps its place: lecture 3 of 4.
        late = {**parts[0], "title": "Lecture 3: Energy", "lecture": 3, "of": 4}
        again = subprocess.run(["node", "-e", f"require({json.dumps(str(js / 'lib' / 'store.js'))}).saveLecture("
                                f"{json.dumps({'title': 'Forces', 'parts': [late]})})"
                                ".then((r) => console.log(JSON.stringify(r)));"], cwd=APP, capture_output=True,
                               text=True, timeout=600, env=env)
        assert [s["lecture"] for s in json.loads(again.stdout.strip().splitlines()[-1])["lectures"]] == [3], again.stderr
        scene = json.loads(urllib.request.urlopen(f"{supabase}/__dump").read())["tables"]["scenes"][-1]
        assert (scene["ordinal"], scene["part_of"], scene["title"]) == (3, 4, "Energy")
        published = 3

        # What the page's "Check the phone's Saved list" reports: both videos saved, both visible to the phone.
        status = subprocess.run(["node", "-e", f"require({json.dumps(str(js / 'lib' / 'store.js'))}).storeStatus()"
                                 ".then((r) => console.log(JSON.stringify(r)));"], cwd=APP, capture_output=True,
                                text=True, timeout=120, env={**env, "NEXT_PUBLIC_SUPABASE_ANON_KEY": "sb_publishable_test"})
        assert json.loads(status.stdout.strip().splitlines()[-1]) == {"published": published, "failed": [], "phoneSees": published,
                                                                      "phoneError": None}, status.stderr

        dump = json.loads(urllib.request.urlopen(f"{supabase}/__dump").read())
        builds = dump["tables"]["builds"]
        assert all(b["published"] and b["state"] == "succeeded" and b["library_path"].startswith("builds/")
                   for b in builds)
        assert [s["title"] for s in dump["tables"]["scenes"]][:2] == ["Newton", "Friction"]   # no "Lecture k: " in it
        assets = [o for o in dump["objects"] if o.startswith("lectures/assets/")]
        assert assets and len(assets) == len(dump["tables"]["assets"])                     # each asset stored once

        classpath = ":".join(str(PHONE / p) for p in ("core", "desktop", "kotlin-stdlib.jar"))
        phone = subprocess.run(["java", "-Dhttp.nonProxyHosts=127.0.0.1|localhost", "-cp", classpath,
                                "com.pocketanim.desktop.VerifyKt", supabase, "saved", "anon-test",
                                str(tmp_path / "phone")], capture_output=True, text=True, timeout=600)
        assert phone.returncode == 0, phone.stdout + phone.stderr
        assert "catalog: 3 saved video(s)" in phone.stdout
        assert "Lecture 2 of 2: Friction (26 min)" in phone.stdout
        assert phone.stdout.count("GeneratedScene             1") == 3

        database = os.environ.get("PANIM_TEST_DATABASE_URL")
        if database and shutil.which("psql"):
            _replay_into_schema(database, dump)
    finally:
        shutil.rmtree(build, ignore_errors=True)


def _replay_into_schema(admin: str, dump: dict) -> None:
    """The rows Save sent, into a scratch database with the real migrations: accepted, and the phone's view lists
    them to the anon role."""
    from urllib.parse import urlsplit, urlunsplit

    name = f"saved_test_{os.getpid()}"
    db = urlunsplit(urlsplit(admin)._replace(path="/" + name))
    psql = lambda url, sql: subprocess.run(["psql", url, "-v", "ON_ERROR_STOP=1", "-qAt", "-c", sql],  # noqa: E731
                                           capture_output=True, text=True)
    psql(admin, f"drop database if exists {name}")
    assert psql(admin, f"create database {name}").returncode == 0
    try:
        stub = ("create schema auth; create table auth.users (id uuid primary key, email text);"
                "create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;"
                "do $$ begin create role authenticated; exception when duplicate_object then null; end $$;"
                "do $$ begin create role anon; exception when duplicate_object then null; end $$;")
        assert psql(db, stub).returncode == 0
        applied = subprocess.run([str(REPO / "harness" / "scripts" / "apply-schema.sh")], capture_output=True,
                                 text=True, env={**os.environ, "DATABASE_URL": db})
        assert applied.returncode == 0, applied.stderr

        def lit(v):
            if v is None:
                return "null"
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, (int, float)):
                return repr(v)
            return "'" + str(v).replace("'", "''") + "'"

        rows = [f"insert into auth.users (id, email) values ({lit(u['id'])}, {lit(u['email'])})" for u in dump["users"]]
        for table in ("projects", "scenes", "scene_versions", "builds", "assets", "build_assets"):
            for row in dump["tables"][table]:
                cols = [c for c in row if c != "created_at"]
                rows.append(f"insert into {table} ({', '.join(cols)}) values ({', '.join(lit(row[c]) for c in cols)})")
        replay = psql(db, ";\n".join(rows))
        assert replay.returncode == 0, replay.stderr
        listed = psql(db, "set role anon; select lecture || ' ' || title from phone_lectures order by lecture")
        assert listed.stdout.split("\n")[:2] == ["1 Newton", "2 Friction"], listed.stdout + listed.stderr
    finally:
        psql(admin, f"drop database if exists {name}")
