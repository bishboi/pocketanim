"""Every picture a lecture uses is kept with its context (app/lib/media.ts, supabase/migrations/0003): the compiler
reports the web and library pictures it showed, each with what it shows, where it came from and the line said
over it (compile_lecture.pictures_used, in the --json output)."""

from __future__ import annotations

import json
import subprocess
import sys

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402

from test_sims_more import REPO  # noqa: E402


def test_the_compiler_reports_each_picture_with_its_context(tmp_path, monkeypatch):
    import images

    monkeypatch.setattr(images, "enabled", lambda: False)
    photo = tmp_path / "gandhi.jpg"
    photo.write_bytes(b"\xff\xd8\xff" + b"0" * 64)
    leaf = tmp_path / "leaf.png"
    leaf.write_bytes(b"\x89PNG" + b"0" * 64)
    cl.script_photos[cl._photo_key({"op": "photo", "subject": "Mahatma Gandhi"})] = {
        "file": str(photo), "title": "File:Gandhi.jpg", "credit": "X, CC BY 4.0, via Wikimedia Commons",
        "license": "CC BY 4.0", "url": "https://commons.wikimedia.org/x"}
    cl.script_photos[cl._photo_key({"op": "illustration", "query": "leaf cross section"})] = {
        "file": str(leaf), "title": "Leaf cross section", "source": "OpenStax", "license": "CC BY 4.0",
        "credit": "OpenStax, CC BY 4.0"}
    script = {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "The march", "section": 3, "map": False, "beats": [
            {"say": "Gandhi walked to Dandi.", "do": [{"op": "picture", "subject": "Mahatma Gandhi", "caption": "Gandhi"}]},
            {"say": "A leaf, cut open.", "do": [{"op": "diagram", "id": "d", "nodes": [
                {"id": "a", "label": "Leaf", "picture": {"illustration": "leaf cross section"}},
                {"id": "b", "label": "Root"}]}]}]}]}
    cl.lint(script)
    cl.compile_script(script)
    used = cl.pictures_used(script)
    assert [(u["kind"], u["description"], u["role"]) for u in used] == [
        ("photo", "Mahatma Gandhi", "shown on the stage"),
        ("illustration", "Leaf cross section", "beside a diagram label")]
    first, second = used
    assert first["context"] == {"chapter": 1, "chapter_title": "The march", "section": 3, "beat": 1,
                                "line": "Gandhi walked to Dandi.", "caption": "Gandhi"}
    assert first["source"]["license"] == "CC BY 4.0" and first["found_by"] == {"subject": "Mahatma Gandhi"}
    assert second["context"]["beside"] == "node 'a'" and second["context"]["line"] == "A leaf, cut open."


def test_the_json_output_carries_the_pictures():
    script = {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False,
              "chapters": [{"title": "A", "map": False, "beats": [{"say": "Hello.", "do": []}]}]}
    out = subprocess.run([sys.executable, str(LECTURE / "compile_lecture.py"), "-", "--json"],
                         input=json.dumps(script), capture_output=True, text=True)
    assert json.loads(out.stdout.strip().splitlines()[-1])["pictures"] == []


def test_the_schema_keeps_generations_pictures_and_programs():
    sql = (REPO / "harness" / "supabase" / "migrations" / "0003_generated_media.sql").read_text()
    for table in ("generations", "media", "generation_media", "generation_scenes", "programs"):
        assert f"create table if not exists {table} (" in sql
    assert "values ('media', 'media', false)" in sql                     # a private bucket
    assert "0003_generated_media.sql" in (REPO / "harness" / "supabase" / "setup.sql").read_text()
