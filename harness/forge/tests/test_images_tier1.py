"""Raster pictures play on the phone at tier 1: the program carries an `image` line for each (its PNG beside the
program, in the library's images/ folder), and both players draw it in its place in the z order, fading and moving
as it did in the video."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from forge.util import REPO

SCENE = '''from manim import *

class PhotoScene(Scene):
    def construct(self):
        under = Square(6, color=BLUE, fill_opacity=1).set_z_index(-1)
        self.add(under)
        image = ImageMobject({photo!r}).scale_to_fit_width(4).shift(LEFT * 2)
        caption = Text("A forest").scale(0.5).next_to(image, DOWN)
        cover = Rectangle(width=1, height=1, color=YELLOW, fill_opacity=1).move_to(LEFT * 3.5).set_z_index(5)
        self.play(FadeIn(Group(image, caption)), run_time=1)
        self.play(FadeIn(cover), run_time=0.5)
        t = ValueTracker(0)
        image.add_updater(lambda m: m.move_to(LEFT * 2 + UP * t.get_value()))
        self.play(t.animate.set_value(1), run_time=1, rate_func=there_and_back)
        image.clear_updaters()
        self.wait(1)
        self.play(FadeOut(Group(image, caption)), run_time=1)
'''


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from PIL import Image

    root = tmp_path_factory.mktemp("pictures")
    photo = Image.new("RGB", (80, 50), (40, 160, 60))
    photo.paste((200, 40, 40), (0, 0, 40, 50))                       # left half red, right half green
    photo.save(root / "photo.png")
    (root / "photo_scene.py").write_text(SCENE.format(photo=str(root / "photo.png")))
    out = root / "build"
    run = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"),
                          str(root / "photo_scene.py"), "PhotoScene", str(out)], capture_output=True, text=True,
                         cwd=REPO, timeout=600)
    result = json.loads(run.stdout.strip().splitlines()[-1])
    return root, out, result


def _pixel(frame: np.ndarray, x: float, y: float) -> tuple:
    width, height = frame.shape[1], frame.shape[0]
    return tuple(int(v) for v in frame[int(height / 2 - y * height / 8), int(width / 2 + x * width / 14.2222)])


def test_a_picture_keeps_the_scene_tier_1(built):
    _, out, result = built
    assert result["tier"] == 1 and result["blockers"] == [], result
    lines = [line for line in result["program"].splitlines() if line.startswith("image ")]
    assert len(lines) == 1 and "src=" in lines[0] and "px=80,50" in lines[0]
    src = lines[0].split("src=")[1].split()[0]
    assert (out / "dsl" / "generated" / "images" / src).is_file()


def test_the_picture_is_keyed_through_its_fades_and_its_motion(built):
    from dsl.interpret import parse

    _, _, result = built
    image = parse(result["program"])["images"][0]
    keys = image["keys"]
    assert keys[0][1] == 0 and keys[-1][1] == 0 and max(k[1] for k in keys) == 1    # fades in, then out
    lifted = max(k[3] for k in keys)
    assert 2.0 < lifted < 2.3                                       # rose by (nearly) a unit, as the updater moved it
    assert len(keys) < 40                                           # still stretches kept as two keys, not one a frame
    assert all(b[0] >= a[0] for a, b in zip(keys, keys[1:]))


def test_the_reference_player_draws_it_in_its_z_place(built):
    from dsl.interpret import images_in_frame, load_program
    from exporter.reference_render import render_frame

    _, out, _ = built
    cwd = os.getcwd()
    os.chdir(out)
    try:
        ir = load_program("dsl/generated/PhotoScene.panim")
        frame = render_frame(ir, 40)
        placed = images_in_frame(ir, 40)
    finally:
        os.chdir(cwd)
    assert len(placed) == 1 and placed[0][2] == 1.0
    assert _pixel(frame, -2.5, 0) == (200, 40, 40)                  # the picture's red half, over the z=-1 square
    assert _pixel(frame, -1.0, 0) == (40, 160, 60)                  # its green half
    yellow = _pixel(frame, -3.6, 0)
    assert yellow[0] > 200 and yellow[1] > 150 and yellow[2] < 150  # the z=5 box stays over it
    blue = _pixel(frame, 2.0, 0)
    assert blue[2] > 150 and blue[0] < 150                          # the square, where there is no picture


def test_the_library_ships_the_picture(built):
    root, out, _ = built
    lib = root / "lib"
    subprocess.run([sys.executable, "-m", "tools.build_library", "--source", str(out / "dsl" / "generated"),
                    "--out", str(lib)], check=True, cwd=REPO, capture_output=True, timeout=300)
    entry = json.loads((lib / "scenes" / "PhotoScene.json").read_text())
    pictures = [a for a in entry["assets"] if a.startswith("images/")]
    assert len(pictures) == 1 and (lib / pictures[0]).is_file()
    manifest = json.loads((lib / "library.json").read_text())
    assert pictures[0] in {a["path"] for a in manifest["assets"]}


def test_the_phone_player_agrees(built):
    classes = REPO / "player" / "build" / "classes"
    if not (classes / "core").exists():
        pytest.skip("player not built (player/build.sh)")
    _, out, _ = built
    program = out / "dsl" / "generated" / "PhotoScene.panim"
    import tools.crosscheck_interpreter as crosscheck

    cwd = os.getcwd()
    os.chdir(out)                                                   # the interpreter finds assets from here
    try:
        crosscheck.CLASSES = classes
        assert crosscheck.check(program)                            # instances and pictures, line for line
    finally:
        crosscheck.CLASSES = Path("player/build/classes")
        os.chdir(cwd)
    from PIL import Image

    rendered = out / "kt.png"
    subprocess.run(["java", "-cp", f"{classes / 'core'}:{classes / 'desktop'}:{classes / 'kotlin-stdlib.jar'}",
                    "com.pocketanim.desktop.VerifyKt", str(program), "render", "40", str(rendered)],
                   check=True, capture_output=True, timeout=300)
    frame = np.asarray(Image.open(rendered).convert("RGB"))
    assert _pixel(frame, -2.5, 0) == (200, 40, 40) and _pixel(frame, -1.0, 0) == (40, 160, 60)


def test_a_lecture_built_in_windows_ends_each_windows_pictures(tmp_path):
    """A lecture built in two windows: each window's pictures are in the joined program, moved to where it starts,
    and a picture still up when its window ends stops there (the next window keys it again from its own start) --
    left held, it stayed over every chapter after."""
    from PIL import Image

    from dsl.interpret import parse

    Image.new("RGB", (40, 30), (200, 80, 60)).save(tmp_path / "a.png")
    Image.new("RGB", (40, 30), (60, 80, 200)).save(tmp_path / "b.png")
    lecture = REPO / "harness" / "lecture"
    (tmp_path / "lec.py").write_text(f'''import sys
sys.path.insert(0, {str(lecture)!r})
from manim import *
from pocket_lecture import *

class S(MapLecture):
    def construct(self):
        self.board()
        self.chapter(1, "One", "first", "One.")
        self.beat("Newton.", self.stage_image({str(tmp_path / "a.png")!r}, "Newton"))
        self.beat("More.", self.work("w", ["F = ma"], title="Law"))
        self.chapter(2, "Two", "second", "Two.")
        self.beat("Leibniz.", self.stage_image({str(tmp_path / "b.png")!r}, "Leibniz"))
        self.beat("Fin.", self.work("w", ["a = F/m"], box=True))
''')
    run = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(tmp_path / "lec.py"),
                          "S", str(tmp_path / "build")], capture_output=True, text=True, timeout=900,
                         env={**os.environ, "PANIM_VOICE": "silent", "PANIM_BUILD_WORKERS": "2"})
    result = json.loads(run.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1 and result["windows"] == 2, result
    scene = parse(result["program"])
    second = min(k[0] for k in scene["images"][-1]["keys"])
    assert second > 300                                             # chapter 2's picture, after chapter 1's frames
    for image in scene["images"][:-1]:
        assert image["keys"][-1][1] == 0 and image["keys"][-1][0] < second, image["keys"]
