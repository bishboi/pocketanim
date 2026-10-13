"""The phone player's side of a saved lecture: chapter times from the export into the library the phone reads, and a
lecture streamed as the phone streams it (its library without the narration, then the narration from its own URL),
checked with the phone's own code against a stand-in for the Supabase project (tools/mock_saved_lectures.py)."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time

from forge.util import REPO

sys.path.insert(0, str(REPO / "harness" / "lecture"))

import compile_lecture as cl  # noqa: E402

PHONE = REPO / "player" / "build" / "classes"
FIXTURE = REPO / "player" / "fixtures" / "streamed-lecture"


def test_chapter_times_reach_the_phones_library(tmp_path):
    # The player lists a lecture's chapters and marks them on its seek bar: the export records where each begins,
    # and the library the phone downloads carries them.
    script = {"title": "T", "style": "blueprint", "teaching_rules": False, "auto_visuals": False,
              "place_figures": False, "chapters": [
                  {"title": "First idea", "map": False, "beats": [{"say": "One.", "do": []}]},
                  {"title": "Second idea", "map": False, "beats": [{"say": "Two.", "do": []}]}]}
    scene = tmp_path / "lecture.py"
    scene.write_text(cl.compile_script(script))
    build = tmp_path / "build"
    env = {**__import__("os").environ, "PANIM_VOICE": "silent", "PANIM_BUILD_WORKERS": "2"}
    out = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                          "GeneratedScene", str(build)], capture_output=True, text=True, timeout=900, env=env)
    assert json.loads(out.stdout.strip().splitlines()[-1])["tier"] == 1, out.stderr[-1500:]
    chapters = json.loads((build / "dsl" / "generated" / "GeneratedScene.chapters.json").read_text())
    assert [c["title"] for c in chapters] == ["First idea", "Second idea"], chapters
    assert 0 < chapters[0]["frame"] < chapters[1]["frame"], chapters
    subprocess.run([sys.executable, "-m", "tools.build_library", "--source", str(build / "dsl" / "generated"),
                    "--out", str(tmp_path / "library")], cwd=REPO, check=True, capture_output=True, timeout=300)
    manifest = json.loads((tmp_path / "library" / "library.json").read_text())
    assert manifest["scenes"][0]["chapters"] == chapters


def test_a_saved_lecture_streams_as_the_phone_plays_it(tmp_path):
    # Save uploads the library without its narration and the narration beside it; the phone downloads the small
    # part, plays, and streams the narration (range reads, as its decoder seeks), keeping it for offline.
    import pytest

    if not (PHONE / "core").is_dir() or not shutil.which("java"):
        pytest.skip("the phone player is not built (player/build.sh)")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "tools.mock_saved_lectures", str(FIXTURE), "--port", str(port),
                               "--host", "127.0.0.1"], cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        server.stdout.readline()                                   # "serving ..." once it listens
        time.sleep(0.3)
        classpath = ":".join(str(PHONE / p) for p in ("core", "desktop", "kotlin-stdlib.jar"))
        run = subprocess.run(["java", "-cp", classpath, "com.pocketanim.desktop.VerifyKt", f"http://127.0.0.1:{port}",
                              "stream", "test", str(tmp_path / "phone")], capture_output=True, text=True, timeout=300)
    finally:
        server.terminate()
    assert run.returncode == 0 and run.stdout.strip().endswith("OK"), run.stdout + run.stderr
    assert "on the phone: false" in run.stdout          # it played before the narration was down
    assert "2 chapter(s)" in run.stdout and "HTTP 206" in run.stdout
