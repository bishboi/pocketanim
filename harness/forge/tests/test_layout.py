"""Lecture layout: typeset maths, labels clear of lines, two pictures in one beat, and nothing on top of
anything else at the end of a beat (harness/scripts/lecture_audit.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import nolatex  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def test_unicode_in_maths_becomes_tex_but_words_in_text_stay():
    assert nolatex.to_tex("μ_s = 0.1, θ = 30°") == r"\mu _s = 0.1, \theta  = 30^{\circ}"
    assert nolatex.to_tex(r"v² ≤ μRg \text{फिसलन होगी}") == r"v^{2} \le  \mu Rg \text{फिसलन होगी}"


def test_a_formula_that_will_not_compile_is_drawn_not_raised(monkeypatch, tmp_path):
    from manim import config

    monkeypatch.setitem(config, "tex_dir", str(tmp_path))
    monkeypatch.setattr(nolatex, "latex_available", lambda: True)

    def broken(*_args, **_kw):
        raise ValueError("LaTeX compilation error")

    monkeypatch.setattr(nolatex, "_original", broken)
    path = nolatex.typeset(r"\frac{a}{b}", "align*")
    assert Path(path).name.startswith("nolatex_") and Path(path).exists()


def test_hindi_in_maths_needs_xelatex_or_is_drawn(monkeypatch, tmp_path):
    from manim import config

    monkeypatch.setitem(config, "tex_dir", str(tmp_path))
    monkeypatch.setattr(nolatex, "latex_available", lambda: True)
    monkeypatch.setattr(nolatex, "xelatex_available", lambda: False)
    monkeypatch.setattr(nolatex, "_original", lambda *a, **k: (_ for _ in ()).throw(AssertionError("pdflatex")))
    path = nolatex.typeset(r"25 > 2.94 \Rightarrow \text{फिसलन होगी}", "align*")
    assert Path(path).name.startswith("nolatex_")


def test_unicode_math_reads_font_and_spacing_commands():
    import pocket_lecture as pl

    assert pl.unicode_math(r"\sum\mathbf F_{\rm ext}=0\ \Rightarrow\ \mathbf a=0") == "ΣFₑₓₜ=0 ⇒ a=0"
    assert pl.unicode_math(r"s=\tfrac12\times6") == "s=1/2×6"
    assert pl.unicode_math("H_2O") == "H₂O"
    assert pl.unicode_math(r"F_{AB}") == "F_(AB)"


def test_maths_with_unit_names_is_not_prose():
    from stem import BoardMixin

    assert not BoardMixin._is_prose(r"\Delta\mathbf P_{\rm total}=0\quad(\mathbf J_{\rm ext}=0)")
    assert not BoardMixin._is_prose(r"25>2.94\quad\Rightarrow\quad\text{फिसलन होगी}")
    assert BoardMixin._is_prose("मान लो a = 2")
    assert BoardMixin._is_prose("first find the net force")


def test_a_rope_comes_with_its_pulley_parts():
    from stem import _with_companions

    ids = ["table", "leg", "pulley", "rope", "rope2", "m1", "m2", "T1"]
    shown = _with_companions(["table", "pulley", "rope", "m1", "m2"], ids)
    assert "rope2" in shown and "leg" in shown and "T1" not in shown


def test_ops_in_a_beat_clear_then_draw_then_add():
    from compile_lecture import beat_order

    ops = [{"op": "work", "key": "w"}, {"op": "figure", "id": "f"}, {"op": "unstage"}, {"op": "reveal"}]
    assert [o["op"] for o in beat_order(ops)] == ["unstage", "figure", "work", "reveal"]


def _board_scene():
    import pocket_lecture as pl

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    return scene


def test_label_moves_off_a_line_it_sat_on():
    scene = _board_scene()
    items = [{"id": "bat", "type": "rect", "at": [2, 0], "w": 0.4, "h": 3},
             {"id": "u", "type": "arrow", "from": [-3, 1], "to": [0, 1], "label": "comes in: 12 m/s"}]
    scene._build_sketch("k", items, (-3.4, -1, 6.45, 3.5))
    bat = scene.diagrams["k"]["nodes"]["bat"][0]
    label = scene.diagrams["k"]["nodes"]["u"][-1]
    left, right = label.get_left()[0], label.get_right()[0]
    assert right < bat.get_left()[0] or left > bat.get_right()[0] or label.get_bottom()[1] > bat.get_top()[1]


def test_a_sketch_and_its_labels_fit_its_box():
    scene = _board_scene()
    items = [{"id": "a", "type": "arrow", "from": [0, 0], "to": [9, 0], "label": "a very long label at the tip"}]
    box = (0.0, 0.0, 4.0, 3.0)
    body = scene._build_sketch("k", items, box)
    assert body.get_left()[0] >= -2.0 - 1e-6 and body.get_right()[0] <= 2.0 + 1e-6


def test_two_pictures_in_one_beat_sit_side_by_side():
    scene = _board_scene()
    scene.sketch("s", [{"id": "b", "type": "rect", "at": [0, 0], "w": 2, "h": 1, "label": "m"}])
    scene.equation(r"F = ma")
    picture, card = scene.stage_body, scene.stage_extra[-1]
    assert picture.get_right()[0] < card.get_left()[0]          # the drawing left, the equation right


def test_a_definition_goes_beside_the_drawing_it_explains():
    scene = _board_scene()
    scene.sketch("s", [{"id": "b", "type": "rect", "at": [0, 0], "w": 2, "h": 1}])
    scene._beat_new = []                                         # the drawing's beat has played
    scene.define("velocity", "speed and direction")
    assert scene.stage_body is not None and scene.stage_body.get_right()[0] < scene.stage_extra[-1].get_left()[0]


def test_equation_during_a_problem_joins_its_working():
    scene = _board_scene()
    scene.problem("p", "A 2 kg block is pulled.", given=["m = 2 kg"], find="a",
                  figure={"op": "sketch", "items": [{"id": "b", "type": "rect", "at": [0, 0], "w": 2, "h": 1}]})
    scene._beat_new = []
    scene.equation(r"a = F/m")
    assert scene._problem is not None and scene.works      # the problem stays; the equation is a working line


SCENE = '''
from manim import *
from pocket_lecture import *


class AuditProbe(MapLecture):
    def construct(self):
        self.board()
        self.beat("A block and its law.",
                  self.sketch("s", [{"id": "b", "type": "rect", "at": [0, 0], "w": 2, "h": 1, "label": "m"},
                                    {"id": "F", "type": "arrow", "from": [1, 0], "to": [3, 0], "label": "F"}]),
                  self.equation(r"F = ma"))
        self.beat("What it means.", self.define("force", "a push or a pull"))
        self.beat("Which force pushes the block up?", self.question("Which force pushes the block up?",
                                                                    answer="The normal reaction"))
        self.think(1.0)
        self.beat("The normal reaction.", self.answer())
        self.beat("Solve it.", self.work("w", ["a = F/m", "a = 2\\\\,\\\\mathrm{m/s^2}"], box=True))
'''


def test_audit_finds_nothing_on_top_of_anything(tmp_path):
    scene = tmp_path / "probe.py"
    scene.write_text(SCENE)
    run = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "lecture_audit.py"), str(scene),
                          "AuditProbe", str(tmp_path / "audit"), "--quiet"], capture_output=True, text=True,
                         timeout=300)
    assert run.returncode == 0, run.stdout + run.stderr
    assert '"serious": 0' in run.stdout


@pytest.mark.parametrize("line", ["F = ma", r"\frac{mv^2}{R}"])
def test_work_line_is_typeset(line, monkeypatch, tmp_path):
    from manim import MathTex, config

    monkeypatch.setitem(config, "tex_dir", str(tmp_path))
    nolatex.install()
    scene = _board_scene()
    assert isinstance(scene._work_line(line, 6.0), MathTex)


def test_an_equation_goes_beside_the_drawing_whose_parts_it_reveals():
    scene = _board_scene()
    scene.sketch("s", [{"id": "b", "type": "rect", "at": [0, 0], "w": 2, "h": 1},
                       {"id": "F", "type": "arrow", "from": [1, 0], "to": [3, 0], "label": "F"}], show=["b"])
    scene._beat_new = []
    scene.equation(r"F = ma")
    assert scene.reveal_nodes("s", ["F"]) is not None
    eq = [m for m in scene.stage_extra if getattr(m, "is_aside", False)][0]
    arrow = scene.diagrams["s"]["nodes"]["F"]
    assert arrow.get_right()[0] < eq.get_left()[0]


def test_parts_of_a_diagram_that_left_the_stage_are_not_drawn():
    scene = _board_scene()
    scene.sketch("s", [{"id": "b", "type": "rect", "at": [0, 0], "w": 2, "h": 1},
                       {"id": "F", "type": "arrow", "from": [1, 0], "to": [3, 0]}], show=["b"])
    scene._beat_new = []
    scene.sketch("t", [{"id": "c", "type": "circle", "at": [0, 0], "r": 1}])
    scene._beat_new = []
    assert scene.reveal_nodes("s", ["F"]) is None


def test_a_question_about_the_drawing_keeps_it_on_the_board():
    scene = _board_scene()
    scene.sketch("s", [{"id": "b", "type": "rect", "at": [0, 0], "w": 2, "h": 1},
                       {"id": "F", "type": "arrow", "from": [1, 0], "to": [3, 0], "label": "F"}])
    scene._beat_new = []                                         # the drawing's beat has played
    drawing = scene.stage_body
    scene.question("इस diagram में सोचो, कौन सा force लग रहा है?", answer="Normal reaction, N")
    card = [m for m in scene.stage_extra if getattr(m, "is_aside", False)][0]
    assert scene.stage_body is drawing                           # still up, now in the left half
    assert card.get_left()[0] > 0 and card.get_right()[0] < 7.2   # the card in the right half (the drawing slides left)
    said = scene.answer()
    assert said is not None and scene._question["answer"] is None


def test_a_figure_does_not_take_a_problem_off_the_board(tmp_path):
    from PIL import Image

    Image.new("RGB", (64, 40), "white").save(tmp_path / "f.png")
    scene = _board_scene()
    scene.problem("p", "A 2 kg block is pulled.", given=["m = 2 kg"], find="a",
                  figure={"op": "sketch", "items": [{"id": "b", "type": "rect", "at": [0, 0], "w": 2, "h": 1}]})
    scene._beat_new = []
    assert scene.figure(str(tmp_path / "f.png"), "a figure", where="stage") is None
    assert scene._problem is not None


def test_a_definition_during_a_problem_goes_in_the_strip():
    scene = _board_scene()
    scene.problem("p", "A 2 kg block is pulled.", given=["m = 2 kg"], find="a")
    scene._beat_new = []
    scene.define("System", "the object chosen")
    assert scene._problem is not None and scene.strip["point"] is not None


def test_a_clear_after_this_beats_working_keeps_it():
    scene = _board_scene()
    scene.work("w", ["a = F/m"])
    assert scene.clear_stage() is None and scene.works


def test_answer_ring_scrolls_with_its_line():
    scene = _board_scene()
    for k in range(14):
        scene.work("w", [f"x_{k} = {k}"], box=(k == 2))
        scene._beat_new, scene._beat_added = [], []
    ring = next(iter(scene.works["w"]["rings"].values()), None)
    # The boxed line scrolled off with its ring, or both are still on screen together.
    assert ring is None or ring in scene.stage_extra


def test_figures_are_not_placed_inside_a_problem():
    from compile_lecture import place_figures

    script = {"figures": {"f1": {"caption": "a block on a table"}},
              "chapters": [{"beats": [{"say": "a block on a table", "do": [{"op": "problem", "id": "p", "text": "x"}]},
                                      {"say": "a block on a table", "do": [{"op": "work", "id": "p", "lines": ["x"]}]},
                                      {"say": "a block on a table again"}]}]}
    place_figures(script)
    beats = script["chapters"][0]["beats"]
    assert not any(op.get("op") == "figure" for b in beats[:2] for op in b.get("do", []))


def test_diagram_drawings_are_whiteboard_drawings_in_the_board_ink():
    import icons
    import pocket_lecture as pl

    assert icons.sketch("tree") == "openmoji:deciduous-tree"           # outlined and flat-filled, not an emoji
    assert icons.sketch("river") != "openmoji:screwdriver"             # whole words, not letters inside one
    assert "#000" not in pl._ink_svg('<path stroke="#000" fill="#fcea2b"/>', "#F4E9D8")
    assert 'fill="#fcea2b"' in pl._ink_svg('<path stroke="#000" fill="#fcea2b"/>', "#F4E9D8")


def test_categories_and_steps_are_cards_of_words_written_in():
    scene = _board_scene()
    anim = scene.diagram("f", "categories", [{"id": "all", "label": "Forces"},
                                              {"id": "c", "label": "Contact", "items": ["Friction", "Tension"]},
                                              {"id": "n", "label": "Non-contact", "items": ["Gravity"]}])
    nodes = scene.diagrams["f"]["nodes"]
    assert nodes["all"].get_bottom()[1] > nodes["c"].get_top()[1]   # the whole above its kinds
    assert len(scene.diagrams["f"]["edges"]) == 2                    # joined to each kind
    assert "Write" in repr([type(a).__name__ for a in anim.animations[-1].animations])
    scene.diagram("s", "steps", [{"id": "a", "label": "Pick the body"}, {"id": "b", "label": "Draw the forces"}])
    assert len(scene.diagrams["s"]["edges"]) == 1
