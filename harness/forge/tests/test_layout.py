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
    # The card in the right half; the drawing slides into the left one (an animation, not played here).
    assert scene.stage_body is not None and scene.stage_extra[-1].get_left()[0] >= 0


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

    assert icons.sketch("tree") == "fluent-emoji-flat:deciduous-tree"  # a flat drawing, drawn with ink outlines
    assert len(icons.drawings("tree")) >= 5                             # choices for the model (find_drawing)
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


def test_each_option_is_marked_while_it_is_explained():
    scene = _board_scene()
    scene.question("The SI unit of force is", ["joule", "newton", "watt", "pascal"], answer=1)
    ring = scene._question["answer"]
    crossed = scene.option(0)
    assert crossed is not None and scene._question["answer"] is ring          # a wrong one: the answer still to come
    right = scene.option(1)
    assert right is not None and scene._question["answer"] is None           # the right one is the answer, shown now
    assert scene.answer() is None
    assert scene.option(7) is None


def test_an_option_of_a_question_without_its_answer_says_itself():
    scene = _board_scene()
    scene.question("Which is a force?", ["push", "sleep"])
    assert scene.option(0, right=True) is not None and scene.option(1, right=False) is not None


def test_an_empty_animation_group_does_not_stop_the_render(tmp_path):
    """A step that finds nothing to show hands the beat an empty group; Manim refuses one, whole or nested."""
    import pocket_lecture as pl
    from manim import AnimationGroup, FadeIn, LaggedStart, Square, tempconfig

    class Probe(pl.MapLecture):
        def construct(self):
            self.board()
            self.beat("Nothing new on this beat.", AnimationGroup(), LaggedStart(*[]))
            self.beat("Some of it is new.", AnimationGroup(AnimationGroup(), FadeIn(Square())))
            self.play(AnimationGroup())

    with tempconfig({"dry_run": True, "media_dir": str(tmp_path), "disable_caching": True}):
        Probe().render()
    assert pl._playable(AnimationGroup(AnimationGroup())) is None
    kept = pl._playable(AnimationGroup(AnimationGroup(), FadeIn(Square()), lag_ratio=0.5))
    assert len(kept.animations) == 1 and kept.lag_ratio == 0.5


def _crosses(label, mobs) -> bool:
    """Whether a line or shape outline of `mobs` runs through the label's box (its own backing patch aside)."""
    import stem

    left, bottom = label.get_corner([-1, -1, 0])[:2]
    right, top = label.get_corner([1, 1, 0])[:2]
    own = {id(m) for m in label.get_family()}
    for mob in mobs:
        for part in mob.family_members_with_points():
            if id(part) in own or len(part.points) < 2:
                continue
            if part.get_stroke_opacity() == 0 and part.get_fill_opacity() == 0:
                continue                              # an invisible anchor, not a line on the board
            pts = stem.curve_samples(part.points, 24)
            if ((pts[:, 0] > left) & (pts[:, 0] < right) & (pts[:, 1] > bottom) & (pts[:, 1] < top)).any():
                return True
    return False


SVG_LABELS_ON_LINES = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400">
<g id="wire"><line x1="50" y1="200" x2="750" y2="200" stroke="INK" stroke-width="5"/>
<text x="400" y="208" font-size="28" fill="INK" text-anchor="middle">wire</text></g>
<g id="box"><rect x="300" y="60" width="200" height="80" fill="none" stroke="ROSE" stroke-width="4"/>
<text x="300" y="70" font-size="26" fill="ROSE" text-anchor="middle">block</text>
<animateTransform attributeName="transform" type="translate" values="0 0; 60 0; 0 0" dur="2s"
 repeatCount="indefinite" additive="sum"/></g>
<g id="a"><text x="400" y="300" font-size="28" fill="GOLD" text-anchor="middle">overlap one</text></g>
<g id="b"><text x="410" y="305" font-size="28" fill="GREEN" text-anchor="middle">overlap two</text></g>
</svg>"""


def test_an_svgs_labels_are_set_clear_of_its_lines_and_of_each_other(tmp_path):
    import pocket_lecture as pl

    _board_scene()
    path = tmp_path / "bad.svg"
    path.write_text(SVG_LABELS_ON_LINES)
    drawing = pl.board_svg(str(path), 8.0, 5.0)
    labels = [mob for _, mob, *_ in drawing.labels]
    shapes = [m for m in drawing.family_members_with_points() if not any(m in lab.get_family() for lab in labels)]
    for lab in labels:
        assert getattr(lab, "backed", False) or not _crosses(lab, shapes), lab
    one, two = labels[2], labels[3]
    apart_x = one.get_right()[0] <= two.get_left()[0] or two.get_right()[0] <= one.get_left()[0]
    apart_y = one.get_top()[1] <= two.get_bottom()[1] or two.get_top()[1] <= one.get_bottom()[1]
    assert apart_x or apart_y
    # The moving part's label keeps its new place through the motion's loop.
    where = [lab.get_center().copy() for lab in labels]
    drawing.show(0.5)
    drawing.show(0.0)
    assert all(abs(lab.get_center() - w).max() < 1e-6 for lab, w in zip(labels, where))


def test_a_label_with_nowhere_clear_gets_a_patch_of_board_behind_it():
    import pocket_lecture as pl
    import stem
    from manim import Line, VGroup

    _board_scene()
    # Lines every 0.15 across a field far wider than a label moves: it cannot get clear, so the lines stop short
    # of its words (a patch of the board behind them) instead of running through them.
    grid = VGroup(*[Line([-4, y, 0], [4, y, 0]) for y in [k * 0.15 for k in range(-20, 21)]])
    label = pl.T("trapped", 26, pl.P.CREAM).move_to([0, 0.07, 0])
    label.is_label = True
    crossing = stem._settle_labels([grid, label], (0.0, 0.0, 8.0, 6.0), backing=pl.P.BG)
    assert crossing == [label] and getattr(label, "backed", False)
    patch = label.submobjects[0]
    assert getattr(patch, "is_backing", False) and patch.get_fill_color().to_hex().lower() == str(pl.P.BG).lower()
    assert patch.width > label.submobjects[1].width     # behind the whole word


def test_a_diagrams_arrow_words_sit_clear_of_the_other_arrows():
    scene = _board_scene()
    nodes = [{"id": i, "label": i} for i in ("Sun", "Plant", "Deer", "Tiger")]
    edges = [["Sun", "Plant", "light energy"], ["Plant", "Deer", "eaten by"], ["Deer", "Tiger", "eaten by"],
             ["Sun", "Deer", "warmth"]]
    scene.diagram("chain", "flow", nodes, edges)
    d = scene.diagrams["chain"]
    words = [part for _, _, edge in d["edges"] for part in edge.submobjects if getattr(part, "is_label", False)]
    assert words
    for word in words:
        others = [*d["nodes"].values(), *[e[0] for _, _, e in d["edges"]]]
        assert getattr(word, "backed", False) or not _crosses(word, others)


def test_a_name_with_no_drawing_is_not_reported_and_a_report_is_made_once():
    import pocket_lecture as pl

    scene = _board_scene()
    pl.SKIPPED.clear()
    for _ in range(3):
        scene._entity("zzqx thing", 1.0, motion="auto")
    assert pl.SKIPPED == []                     # no drawing at all: the node's name carries it, nothing to report
    for _ in range(3):
        pl.skipped("a drawing of 'x' holds still: ValueError: bad")
    assert pl.SKIPPED == ["a drawing of 'x' holds still: ValueError: bad"]
    pl.SKIPPED.clear()
    # The thing named last is drawn: a rice plant is a plant.
    assert "plant" in pl.drawing_source("rice plant")[1]


def test_a_ring_of_big_drawings_leaves_room_for_every_arrow():
    scene = _board_scene()
    nodes = [{"id": "s", "label": "Sun heats the sea", "entity": "sun"}, {"id": "c", "label": "Vapour forms clouds",
             "entity": "cloud"}, {"id": "r", "label": "Rain falls", "entity": "rain"},
             {"id": "v", "label": "Rivers run back", "entity": "boat"}]
    scene.diagram("w", "cycle", nodes)
    lengths = [edge[0].get_length() for _, _, edge in scene.diagrams["w"]["edges"]]
    assert len(lengths) == 4 and min(lengths) > 0.5, lengths     # rain -> rivers was 0.05 long: never seen


def _box_hit(mob, arrow) -> bool:
    """Whether the arrow's line runs through the box of `mob`."""
    lo, hi = mob.get_corner([-1, -1, 0]), mob.get_corner([1, 1, 0])
    for k in range(41):
        p = arrow.point_from_proportion(k / 40)
        if lo[0] + 0.02 < p[0] < hi[0] - 0.02 and lo[1] + 0.02 < p[1] < hi[1] - 0.02:
            return True
    return False


@pytest.mark.parametrize("kind", ["flow", "hub"])
def test_an_arrow_goes_round_the_cards_it_would_cross(kind):
    """An arrow from the first card to the third of a row (or across a hub) bows round the card between them."""
    scene = _board_scene()
    nodes = [{"id": i, "label": label} for i, label in
             [("pope", "Pope"), ("east", "Eastern Church head"), ("emp", "Byzantine emperor"), ("king", "King"),
              ("bishop", "Bishop")]]
    edges = [["pope", "east"], ["east", "emp"], ["pope", "emp", "crowns"], ["king", "east"]] if kind == "flow" else \
        [["pope", "east"], ["pope", "emp"], ["east", "king"], ["emp", "king"]]
    scene.diagram("d", kind, nodes, edges)
    d = scene.diagrams["d"]
    for a, b, edge in d["edges"]:
        for other, mob in d["nodes"].items():
            if other not in (a, b):
                assert not _box_hit(mob, edge[0]), (a, b, other)


def test_a_ring_is_not_drawn_on_a_picture_that_has_left():
    scene = _board_scene()
    scene.diagram("d", "flow", [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}])
    scene._stage_leaving()
    assert scene.spotlight("d", "a") is None


def test_a_second_picture_moves_the_firsts_revealed_parts_with_it():
    """The beat's first picture shrinks to the left half beside the second; what it revealed and its ring go
    with it, instead of staying over the second picture."""
    scene = _board_scene()
    scene._beat_new = []
    scene.diagram("d", "flow", [{"id": "a", "label": "Manor"}, {"id": "b", "label": "Church"}], show=["a"])
    scene.reveal_nodes("d", ["b"])
    scene.spotlight("d", "b")
    ring = scene.diagrams["d"]["focus"]
    church = scene.diagrams["d"]["nodes"]["b"]
    from manim import Square

    scene._to_stage(pl_group(Square(1.0), Square(0.5)))
    left, right = scene._halves()
    edge = left[0] + left[2] / 2 + 0.05
    assert church.get_right()[0] <= edge and ring.get_right()[0] <= edge + 0.2


def pl_group(*mobs):
    from manim import Group

    return Group(*mobs)
