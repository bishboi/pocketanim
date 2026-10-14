"""The layout pass (harness/lecture/layout.py): before a line plays, what it brings on is checked against what is on
the screen; a leftover of an earlier line under a new thing goes as the line begins, a new thing of its own that
lands on another is moved clear, and nothing is pushed off the frame."""

from __future__ import annotations

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import layout  # noqa: E402
import pocket_lecture as pl  # noqa: E402


def _scene(monkeypatch):
    monkeypatch.setattr(pl, "narrate", lambda text: (None, 3.0))

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    real = scene.play
    scene.play = lambda *a, run_time=1.0, **k: real(*a, run_time=0.05, **k)
    scene.wait = lambda *a, **k: None
    return scene


def _on(scene, mob) -> bool:
    return any(mob is m for top in scene.mobjects for m in top.get_family())


def test_a_leftover_under_a_new_thing_goes_as_the_line_begins(monkeypatch):
    from manim import FadeIn

    scene = _scene(monkeypatch)
    old = pl.T("an old card's words", 28).move_to([0, 1, 0])
    scene.beat("One.", FadeIn(old))
    new = pl.T("the new card's words", 28).move_to([0.1, 1.05, 0])
    scene.beat("Two.", FadeIn(new))
    assert _on(scene, new) and not _on(scene, old)
    assert pl.sync_counts().get("cleared", 0) >= 1


def test_two_new_things_on_each_other_are_moved_apart_inside_the_frame(monkeypatch):
    from manim import FadeIn

    scene = _scene(monkeypatch)
    a = pl.T("first label", 26).move_to([-3, -1, 0])
    b = pl.T("second label", 26).move_to([-2.9, -1.02, 0])
    c = pl.T("words running off the right of the frame", 26).move_to([7.4, 2, 0])
    scene.beat("Three.", FadeIn(a), FadeIn(b), FadeIn(c))
    assert layout._shared(layout._box(a), layout._box(b)) == 0
    assert c.get_right()[0] <= pl.config.frame_width / 2
    assert pl.sync_counts().get("moved", 0) >= 1


def test_a_layouts_own_parts_are_left_to_it(monkeypatch):
    """A diagram's nodes are the stage's: the pass does not move them about, whatever they are near."""
    scene = _scene(monkeypatch)
    nodes = [{"id": k, "label": k} for k in ("roots", "stem", "leaves")]
    scene.beat("A plant.", scene.diagram("p", "flow", nodes, [["roots", "stem"], ["stem", "leaves"]]))
    where = {k: tuple(m.get_center().round(3)) for k, m in scene.diagrams["p"]["nodes"].items()}
    scene.beat("Again.", scene.reveal_nodes("p", ["stem", "leaves"]))
    assert {k: tuple(m.get_center().round(3)) for k, m in scene.diagrams["p"]["nodes"].items()} == where
