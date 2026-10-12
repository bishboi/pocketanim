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
