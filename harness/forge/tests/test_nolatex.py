"""Scenes with MathTex, Tex and axis numbers render without LaTeX installed (harness/lecture/nolatex.py)."""

from __future__ import annotations

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import nolatex  # noqa: E402


@pytest.fixture
def no_latex(monkeypatch, tmp_path):
    """Manim as it is on a machine without LaTeX: the fallback in place, a fresh tex folder."""
    import manim.mobject.text.tex_mobject as tex_mobject
    from manim import config

    monkeypatch.setattr(tex_mobject, "tex_to_svg_file", nolatex.tex_to_svg_file)
    monkeypatch.setitem(config, "tex_dir", str(tmp_path))


def test_mathtex_keeps_its_parts_and_size(no_latex):
    from manim import MathTex, Text

    law = MathTex("F", "=", "m", "a")
    assert len(law) == 4                      # law[0].set_color(...) still reaches the F
    x = MathTex("x^2 + y", font_size=48)
    assert x.height == pytest.approx(Text("x² + y", font="Serif", font_size=48).height, rel=0.05)


def test_axis_numbers_labels_and_tex_render(no_latex):
    from manim import Axes, DecimalNumber, Tex

    axes = Axes(x_range=[0, 5, 1], y_range=[0, 5, 1], axis_config={"include_numbers": True})
    assert len(axes.x_axis.numbers) == 4
    assert axes.get_axis_labels(x_label="t", y_label="v")
    assert Tex("Hello world").width > 0
    assert DecimalNumber(3.14).width > 0


def test_tex_reads_as_unicode_maths():
    assert nolatex._plain(r"\frac{F}{m}") == "F/m"
    assert nolatex._plain(r"\frac{a + b}{2}") == "(a + b)/2"
    assert nolatex._plain(r"v^2 = u^2 + 2as") == "v² = u² + 2as"
    assert nolatex._plain(r"\text{speed} = \alpha") == "speed = α"
