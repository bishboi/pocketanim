"""Labels that start on top of each other or on a shape end up apart."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manim import Circle, Square, Text, UP  # noqa: E402

from layout_guard import SAFE, TEXT_GAP, _box, _overlap, settle  # noqa: E402


class _Stage:
    def __init__(self, *mobs):
        self.mobjects = list(mobs)


def test_two_titles_separate():
    a = Text("Photosynthesis", font_size=36)
    b = Text("makes sugar", font_size=36)
    b.move_to(a)
    settle(_Stage(), [a, b])
    assert _overlap(_box(a), _box(b), TEXT_GAP) == 0
    for mob in (a, b):
        box = _box(mob)
        assert box[0] >= SAFE[0] - 1e-3 and box[2] <= SAFE[2] + 1e-3
        assert box[1] >= SAFE[1] - 1e-3 and box[3] <= SAFE[3] + 1e-3


def test_label_leaves_the_circle():
    dot = Circle(radius=0.9)
    label = Text("leaf", font_size=28)
    label.move_to(dot)
    settle(_Stage(), [dot, label])
    box = _box(label)
    shape = _box(dot)
    assert _overlap(box, shape, 0.1) == 0


def test_caption_on_a_card_stays_inside():
    card = Square(side_length=3).set_fill("#F2C14E", opacity=1)
    caption = Text("air", font_size=28)
    caption.move_to(card)
    before = caption.get_center().copy()
    settle(_Stage(), [card, caption])
    after = caption.get_center()
    assert abs(after[0] - before[0]) < 0.05
    assert abs(after[1] - before[1]) < 0.05


def test_stage_text_is_not_moved():
    title = Text("Sky", font_size=40)
    title.to_edge(UP)
    scene = _Stage(title)
    pinned = title.get_center().copy()
    body = Text("Sky", font_size=40)
    body.move_to(title)
    settle(scene, [body])
    assert abs(title.get_center()[1] - pinned[1]) < 1e-6
    assert _overlap(_box(title), _box(body), TEXT_GAP) == 0


if __name__ == "__main__":
    test_two_titles_separate()
    test_label_leaves_the_circle()
    test_caption_on_a_card_stays_inside()
    test_stage_text_is_not_moved()
    print("ok")
