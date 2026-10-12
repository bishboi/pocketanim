"""The catalogue of diagrams free Manim builds (manim_catalog.py): every kind's blocks pass the sandbox and run in the
probe scene the `manim` op is checked in (on the board, phone-playable, not far longer than their lines), and the
example lecture is the catalogue as it stands."""

from __future__ import annotations

import json

from forge.util import LECTURE

import free_check  # noqa: E402
import manim_catalog as mc  # noqa: E402


def test_the_catalogue_has_each_kind_once_with_a_use():
    ids = [e["id"] for e in mc.CATALOG]
    assert len(ids) == len(set(ids)) and len(ids) >= 35
    assert all(e["use"] and e["beats"] and e["subject"] for e in mc.CATALOG)
    assert {e["subject"] for e in mc.CATALOG} >= {"mathematics", "physics", "chemistry", "biology", "computing"}


def test_every_block_passes_the_sandbox_and_the_probe():
    script = mc.script()
    for group in free_check.blocks_of(script):
        for block in group["blocks"]:
            assert free_check.check_code(block["code"]) == [], (group["key"], block["where"])
    assert free_check.verify(script) == []


def test_the_example_lecture_is_the_catalogue():
    kept = json.loads((LECTURE / "examples" / "manim-diagrams.json").read_text())
    assert kept == json.loads(json.dumps(mc.script(), ensure_ascii=False))


def test_a_block_that_does_not_read_cleanly_is_sent_back():
    """Words too small for a phone, two labels on top of each other, a line through a label: each is a fault the
    writer is told to fix. A label inside its box, or beside a line, is fine."""
    from manim import LEFT, RIGHT, DOWN, Line, Rectangle, Text

    small = Text("tiny words", font_size=12)
    assert any("font size 12" in f for f in free_check.layout_faults([small]))
    a = Text("Mitochondria", font_size=30)
    b = Text("Nucleus here", font_size=30).move_to(a.get_center() + RIGHT * 0.3)
    assert any("'Mitochondria' and 'Nucleus here' overlap" in f for f in free_check.layout_faults([a, b]))
    word = Text("Force", font_size=34)
    assert any("a line runs through the text 'Force'" in f
               for f in free_check.layout_faults([Line(LEFT * 3, RIGHT * 3), word]))
    assert free_check.layout_faults([Line(LEFT * 3, RIGHT * 3).shift(DOWN), word]) == []
    box = Rectangle(width=3, height=1.2)
    assert free_check.layout_faults([box, Text("Nucleus", font_size=30).move_to(box)]) == []
