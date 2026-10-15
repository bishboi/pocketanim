"""A picture alone on a line fills the screen, made in the screen's shape; a part named is lit with the rest of the
picture shaded; small pictures are children's drawings drawn on outline first; a map shows only its last few
place names."""

from __future__ import annotations

import numpy as np
import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import pocket_lecture as pl  # noqa: E402


def _probe(cls=pl.MapLecture):
    class Probe(cls):
        REGION = dict(area="Europe")

        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    return scene


def test_the_image_model_is_asked_for_the_shape(monkeypatch):
    import genimage

    sent = []

    def post(url, body, proxied=True, who=None):
        sent.append(body)
        return {"choices": [{"message": {"images": [{"image_url": {"url": "data:image/png;base64,AAAA"}}]}}]}

    monkeypatch.setattr(genimage, "_post", post)
    monkeypatch.setattr(genimage, "_image_bytes", lambda ref: b"png")
    genimage._LOCAL.aspect = "16:9"
    try:
        genimage._ask_chat("a village")
    finally:
        genimage._LOCAL.aspect = None
    assert sent[0]["image_config"] == {"aspect_ratio": "16:9"}
    assert "16:9" in genimage.prompt_for("a village", scene=True, aspect="16:9")
    child = genimage.prompt_for("a cow", look="child", aspect="1:1")
    assert "wax-crayon drawing" in child and "CUTOUT" in child


def test_a_picture_alone_fills_the_screen_and_its_labels_sit_on_it(tmp_path):
    from PIL import Image

    path = tmp_path / "scene.png"
    Image.new("RGB", (1200, 900), (90, 140, 190)).save(path)             # 4:3: cut to the screen's shape
    scene = _probe()
    scene.board()
    scene.stage_image(str(path), "x", labels=[("sun", 0.3, 0.3, 0.2, 0.2, 0.4, 0.4)])
    view = scene._views[-1]
    image = view["image"]
    assert image.width >= pl.config.frame_width and image.height >= pl.config.frame_height
    tag = view["parts"]["sun"]["tag"]
    assert abs(tag.get_center()[0]) < pl.config.frame_width / 2                # on the picture, not beside it


def test_a_childs_drawing_is_drawn_on(tmp_path):
    from PIL import Image, ImageDraw

    path = tmp_path / "gen-child-ball.png"
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([40, 40, 260, 260], fill=(220, 60, 60, 255), outline=(20, 20, 20, 255), width=10)
    img.save(path)
    mob = pl.cutout_mob(str(path), 2, 2)
    assert mob._panim_child
    assert len(pl.sketch_lines(mob)) >= 1
    anim = pl.write_in(mob)
    assert type(anim).__name__ == "AnimationGroup" and type(anim.animations[0]).__name__ == "Create"


def test_a_map_shows_only_its_last_few_place_names():
    scene = _probe()
    scene.show_map()
    for city in ("Paris", "London", "Rome", "Madrid", "Vienna", "Berlin"):
        scene.marker(city, city)
    assert len(scene._map_names) == scene.MAP_NAMES
    assert len(scene._map_tidy) == 2                                        # Paris's and London's names go


def test_a_pictures_labels_move_and_shrink_with_it(tmp_path, monkeypatch):
    # A labelled picture beside its names, then the stage shrinks it (a card set beside it): every label not yet
    # shown keeps its place on the part, and the picture is held to its share of the stage, not the whole of it.
    from PIL import Image

    monkeypatch.setenv("PANIM_FULL_SCREEN", "0")
    path = tmp_path / "square.png"
    Image.new("RGB", (800, 800), (200, 120, 90)).save(path)
    scene = _probe()
    scene.board()
    scene.stage_image(str(path), "x", labels=[("tower", 0.25, 0.4, 0.2, 0.1, 0.3, 0.7)])
    view = scene._views[-1]
    image, piece = view["image"], view["parts"]["tower"]
    cx, cy, w, h = scene.STAGE
    assert image.width <= w * 0.58 + 1e-6

    def on_part():
        x0, y0, x1, y1 = scene._part_rect(view, piece["box"])
        return np.allclose(piece["frame"].get_center()[:2], [(x0 + x1) / 2, (y0 + y1) / 2], atol=1e-3)

    assert on_part()
    whole = pl.Group(scene.stage_body, *scene.stage_extra, *scene.stage_pending)
    scene._move_stage(0.5, whole.get_center(), (-3.4, 0.0, 6.5, 5.0))
    assert on_part()
    assert piece["tag"].get_right()[0] < image.get_left()[0]                  # still beside the picture's edge
