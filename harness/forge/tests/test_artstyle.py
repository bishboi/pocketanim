"""Art styles (harness/lecture/artstyle.py): how a lecture's pictures are drawn, chosen apart from the template.
Each style paints every shape without feeding on its own output, keeps a moving shape's extras on it, leaves text
alone, and is chosen by the script's "art" (or by its template when "auto")."""

from __future__ import annotations

from pathlib import Path
import json
import re

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import artstyle  # noqa: E402
import compile_lecture as cl  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

STYLES = list(artstyle.ART_STYLES)


@pytest.fixture(autouse=True)
def _board():
    import pocket_lecture as pl

    pl.use_style("chalkboard")
    yield
    artstyle.use("auto", "chalkboard")


@pytest.mark.parametrize("art", STYLES)
def test_painting_again_never_compounds(art):
    """A sim that fades a dot every frame used to have its width multiplied every frame, until the dot was drawn
    with a stroke a thousand wide."""
    from manim import Dot, Line

    artstyle.use(art)
    dot, line = Dot(radius=0.2), Line([0, 0, 0], [1, 0, 0], stroke_width=3)
    widths = set()
    for k in range(40):
        dot.set_fill(opacity=0.3 + 0.6 * (k % 2))
        line.set_stroke(opacity=0.5 + 0.5 * (k % 2))
        artstyle.paint(dot)
        artstyle.paint(line)
        widths.add((round(dot.get_stroke_width(), 3), round(line.get_stroke_width(), 3)))
    assert len(widths) == 1, widths
    assert max(widths.pop()) < 6


@pytest.mark.parametrize("art", ["detailed", "neon", "chalk", "watercolour"])
def test_extras_follow_a_moving_shape(art):
    from manim import Circle

    artstyle.use(art)
    ball = Circle(radius=0.6, fill_opacity=0.8, stroke_width=3)
    artstyle.mark_live(ball)
    artstyle.dress(ball)
    assert ball._art_decos
    ball.shift([2.0, 1.0, 0])
    artstyle.live_paint(ball)
    for child in ball._art_decos:
        assert abs(child.get_center()[0] - ball.get_center()[0]) < 0.25
        assert abs(child.get_center()[1] - ball.get_center()[1]) < 0.25


@pytest.mark.parametrize("art", STYLES)
def test_text_belongs_to_the_template(art):
    import pocket_lecture as pl

    artstyle.use(art)
    words = pl.T("Pressure", 24, "#F2E27A")
    before = [(m.get_fill_color().to_hex(), m.get_stroke_width(), len(m.submobjects)) for m in words.get_family()]
    artstyle.dress(words)
    after = [(m.get_fill_color().to_hex(), m.get_stroke_width(), len(m.submobjects)) for m in words.get_family()]
    assert before == after


def test_auto_takes_the_templates_art():
    assert artstyle.use("auto", "blueprint") == "blueprint"
    assert artstyle.use("auto", "chalkboard") == "chalk"
    assert artstyle.use("auto", "cosmos") == "neon"
    assert artstyle.use("watercolor", "vox") == "watercolour"
    assert artstyle.use("auto", "no-such-template") == "clean"
    with pytest.raises(KeyError):
        artstyle.use("crayon")


def test_the_script_chooses_the_art():
    script = {"title": "T", "style": "chalkboard", "art": "blueprint",
              "chapters": [{"title": "A", "beats": [{"say": "Blood goes round twice through the heart.",
                                                       "do": [{"op": "sim", "id": "h", "kind": "double_circulation"}]}]}]}
    assert not cl.lint(script)[0]
    assert 'os.environ.setdefault("LECTURE_ART", "blueprint")' in cl.compile_script(script)
    assert any("art must be one of" in e for e in cl.lint({**script, "art": "crayon"})[0])
    assert 'LECTURE_ART", "auto"' in cl.compile_script({k: v for k, v in script.items() if k != "art"})


def test_the_page_offers_the_same_styles():
    text = (REPO / "harness/app/lib/artstyles.ts").read_text()
    ids = re.findall(r'\{ id: "(\w+)", name:', text)
    assert ids == ["auto", *STYLES]
    pairs = dict(re.findall(r"(\w+): \"(\w+)\"", text[text.index("TEMPLATE_ART"):text.index("};", text.index("TEMPLATE_ART"))]))
    assert pairs == artstyle.TEMPLATE_ART
    assert json.dumps(sorted(cl.ARTS)) == json.dumps(sorted(["auto", *STYLES]))
