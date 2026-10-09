"""A lecture's chapters built side by side (harness/scripts/export_scene.py, export_dsl's record window): the
chapters are split into windows of about equal weight, the windows' programs are joined with every object under
a name of its own, and the joined lecture plays the same frames, for as long, as the lecture built whole."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

from test_sims_more import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "harness" / "scripts"))
sys.path.insert(0, str(REPO))

import export_scene as es  # noqa: E402
from dsl.export_dsl import Recorder  # noqa: E402


def _scene(chapters: int, beats: int = 2) -> str:
    lines = ["class GeneratedScene(MapLecture):", "    def construct(self):"]
    for c in range(1, chapters + 1):
        lines.append(f"        self.chapter({c}, 'C{c}', '', 'Chapter {c}.')")
        lines += ["        self.beat('A line.')"] * beats
    return "\n".join(lines) + "\n"


def test_chapters_split_into_windows_of_equal_weight():
    assert es._windows(_scene(8), 4) == [(1, 2), (3, 4), (5, 6), (7, 8)]
    assert es._windows(_scene(8), 1) == []
    assert es._windows(_scene(1), 4) == []
    assert es._windows(_scene(3), 8) == [(1, 1), (2, 2), (3, 3)]
    # A long chapter gets a window of its own.
    heavy = _scene(4).replace("self.chapter(1, 'C1', '', 'Chapter 1.')",
                              "self.chapter(1, 'C1', '', 'Chapter 1.')" + "\n        self.beat('More.')" * 20)
    windows = es._windows(heavy, 2)
    assert windows[0] == (1, 1) and windows[-1][1] == 4


def test_joined_names_are_the_recorders_own():
    rec = Recorder()
    names = [rec.name_for(object()) for _ in range(60)]
    assert names == [es._name(k) for k in range(60)]


def test_a_lecture_built_in_windows_plays_the_same(tmp_path):
    script = {"title": "Windows", "style": "chalkboard", "art": "detailed", "chapters": [
        {"title": f"Part {k}", "beats": [
            {"say": f"Part {k} begins with a picture that moves for as long as the line is said.",
             "do": [{"op": "sim", "id": f"s{k}", "kind": kind}]},
            {"say": f"And part {k} ends with a diagram of three steps in a flow.",
             "do": [{"op": "diagram", "id": f"d{k}", "kind": "flow",
                     "nodes": [{"id": "a", "label": "First"}, {"id": "b", "label": "Second"},
                               {"id": "c", "label": "Third"}]}]}]}
        for k, kind in ((1, "columns"), (2, "pendulum_period"), (3, "fractions"))]}
    source = tmp_path / "script.json"
    source.write_text(json.dumps(script))
    builds = {}
    for name, workers in (("whole", "1"), ("windows", "3")):
        out = tmp_path / name
        out.mkdir()
        subprocess.run([sys.executable, str(REPO / "harness/lecture/compile_lecture.py"), str(source), "-o",
                        str(out / "scene.py")], check=True, capture_output=True)
        env = {**os.environ, "PANIM_VOICE": "silent", "PANIM_BUILD_WORKERS": workers}
        done = subprocess.run([sys.executable, str(REPO / "harness/scripts/export_scene.py"), str(out / "scene.py"),
                               "GeneratedScene", str(out)], capture_output=True, text=True, env=env, timeout=900)
        result = json.loads(done.stdout.strip().splitlines()[-1])
        assert result["tier"] == 1 and not result["blockers"], result
        builds[name] = (out, result)
    assert builds["windows"][1].get("windows") == 3
    sys.path.insert(0, str(REPO / "dsl"))
    from interpret import load_program

    frames = {}
    for name, (out, _) in builds.items():
        here = Path.cwd()
        os.chdir(out)
        try:
            frames[name] = len(load_program("dsl/generated/GeneratedScene.panim").records)
        finally:
            os.chdir(here)
    assert frames["whole"] == frames["windows"]
    names = [line.split(" ")[1] for line in builds["windows"][1]["program"].splitlines()[1:]
             if line.split(" ")[0] in ("geom", "text", "clip", "rect", "circle", "line", "dot", "arrow")]
    assert len(names) == len(set(names))


def test_join_moves_sounds_and_pictures_to_their_window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    parts = []
    for k in range(2):
        out = tmp_path / f"w{k}"
        (out / "dsl" / "generated" / "assets").mkdir(parents=True)
        (out / "dsl" / "generated" / "assets" / f"a{k}.panm").write_bytes(b"x")
        result = {
            "program": "scene 2d fps=30 bg=#112233\ngeom A asset=a0\ngeom B asset=b0\nshow A\nwait t=2\nshow B\nwait t=1\n",
            "declarations": [f"geom A asset=a{k}", f"geom B asset=b{k}"],
            "timeline": ["show A", "wait t=2", "show B", "wait t=1", "hide A", "hide B"],
            "sounds": [(0.5, f"/voice/{k}.wav", 0.0)],
            "images_track": [{"asset": f"p{k}.png", "width": 4, "height": 3, "z": 0.0, "keys": [[0, 1.0, 0, 0, 1, 0, 0, 1]]}],
            "skipped": ["a picture"], "blockers": [], "ai_images": {"count": 1, "usd": 0.04, "items": []},
        }
        parts.append((out, result))
    joined = es._join(parts, "GeneratedScene")
    lines = joined["program"].splitlines()
    assert lines[0] == "scene 2d fps=30 bg=#112233"
    assert lines[1:5] == ["geom A asset=a0", "geom B asset=b0", "geom C asset=a1", "geom D asset=b1"]
    assert "show C" in lines and lines.index("show C") > lines.index("hide B")
    from dsl.interpret import parse, timeline_frames

    # The second window starts where the player has the first one end, counted as the player counts frames.
    first = timeline_frames(parse("\n".join(parts[0][1]["timeline"]))["timeline"], 30)
    assert first >= 90
    assert joined["sounds"] == [(0.5, "/voice/0.wav", 0.0), (0.5 + first / 30, "/voice/1.wav", 0.0)]
    assert [image["keys"][0][0] for image in joined["images_track"]] == [0, first]
    assert joined["skipped"] == ["a picture"] and joined["ai_images"]["count"] == 2
    assert sorted(p.name for p in (tmp_path / "dsl" / "generated" / "assets").iterdir()) == ["a0.panm", "a1.panm"]
