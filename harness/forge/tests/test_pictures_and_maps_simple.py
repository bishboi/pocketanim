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


def test_a_question_about_a_picture_goes_in_the_panel(tmp_path, monkeypatch):
    # With a panel up, a question set with a picture is written in the panel under its points; the picture keeps
    # the stage whole (no two narrow columns beside the panel), and the answer is written in the panel too.
    from PIL import Image

    monkeypatch.setenv("PANIM_FULL_SCREEN", "0")
    path = tmp_path / "wide.png"
    Image.new("RGB", (1600, 900), (90, 140, 190)).save(path)
    scene = _probe()
    scene.panel = scene.panel_bg()
    scene.add(scene.panel)
    scene.panel_title("What changed?")
    scene.fact("1442: trade begins")
    scene.stage_image(str(path), "x", labels=[("ships", 0.7, 0.5, 0.6, 0.3, 0.8, 0.7)])
    image = scene._views[-1]["image"]
    before = image.get_center().copy()
    scene.question("What changed with these contacts?", answer="Trade in people began")
    card = scene.panel_items[-1]
    assert getattr(card, "is_in_panel", False)
    assert card.get_left()[0] >= scene.TEXT_LEFT - 1e-3 and card.width <= pl.TEXT_W + 1e-3
    assert np.allclose(image.get_center(), before)                            # the picture did not move aside
    assert scene._question["in_panel"]
    scene.answer()
    assert scene.panel_items[-1].get_left()[0] >= pl.PANEL_X


def test_a_world_map_turned_from_greenwich_has_no_lines_across_it():
    # Robinson centred on the Atlantic: a coast running across the map's back meridian is cut there, not joined by a
    # line straight across the map.
    from shapely.geometry import LineString, Polygon, box

    frame = pl.MapFrame(box(-100, -10, 30, 70), center=(0, 0), height=7.5, width=13.5, clip=False)
    assert frame.seam is not None
    land = frame.project_geom(Polygon([(30, 50), (179, 50), (179, 70), (30, 70)]))
    assert land.geom_type == "MultiPolygon"
    assert max(p.bounds[2] - p.bounds[0] for p in land.geoms) < 12
    coast = frame.project_geom(LineString([(100, 60), (179, 62)]))
    assert coast.geom_type == "MultiLineString"


def test_a_map_frame_is_made_for_any_focus():
    # One place, a line, a box padded past a pole or the date line: the map is still made (it divided by zero, or
    # asked the projection for a parallel past 90 degrees).
    from shapely.geometry import LineString, Point

    for focus in (Point(10, 50), LineString([(0, 20), (40, 20)]), pl._box((5, 20, 5, 20)),
                  pl._box((-20, 70, 40, 100)), pl._box((170, -20, 195, 10)), pl._box((0, -10, 360, 60))):
        frame = pl.MapFrame(focus)
        assert np.isfinite(frame.s) and frame.s > 0
