"""The second set of sims (harness/lecture/sims_more.py) and the journey on a map: every kind builds and moves, the
compiler accepts them, and the script writer is told about each of them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import live  # noqa: E402
import sims_more  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
BOX = (0.0, -0.2, 12.6, 6.0)


def _points(mob):
    import numpy as np

    pts = [m.points for m in mob.family_members_with_points() if len(m.points)]
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def _looks(mob):
    """What a picture shows: every piece's points and how opaque it is (a part revealed by fading in moves nothing)."""
    import numpy as np

    alphas = [(float(m.get_fill_opacity()), float(m.get_stroke_opacity())) for m in mob.family_members_with_points()]
    return _points(mob), np.array(alphas)


@pytest.mark.parametrize("kind", sorted(sims_more.MORE))
def test_every_new_sim_builds_and_moves(kind):
    import numpy as np
    import pocket_lecture as pl

    pl.use_style("chalkboard")
    made = live.BUILDERS[kind]({}, BOX)
    assert made.mode in ("loop", "process")
    assert (kind in sims_more.LOOPING) == (made.mode == "loop")
    first_points, first_alpha = (a.copy() for a in _looks(made.body))
    for p in (0.0, 0.3, 0.6, 1.0):
        made.step(p * 6.3, p)
    last_points, last_alpha = _looks(made.body)
    # It changes as it plays (something moves, fills in or appears) and stays on the board.
    moved = first_points.shape != last_points.shape or not np.allclose(first_points, last_points)
    shown = first_alpha.shape != last_alpha.shape or not np.allclose(first_alpha, last_alpha)
    assert moved or shown
    assert np.abs(last_points[:, :2]).max() < 9


def test_balancing_counts_atoms():
    assert sims_more.atoms_in("Ca(OH)2") == {"Ca": 1, "O": 2, "H": 2}
    assert sims_more.atoms_in("Fe2(SO4)3") == {"Fe": 2, "S": 3, "O": 12}
    assert sims_more.formula("H2O") == "H₂O" and sims_more.formula("2H2") == "2H₂"


def test_new_sims_pass_the_compiler_and_a_wrong_kind_does_not():
    script = {"title": "S", "chapters": [{"title": "C", "beats": [
        {"say": "Watch it.", "do": [{"op": "sim", "id": f"s{k}", "kind": kind}]}
        for k, kind in enumerate(sorted(sims_more.MORE))]}]}
    errors, _ = cl.lint(json.loads(json.dumps(script)))
    assert not [e for e in errors if "sim" in e], errors
    script["chapters"][0]["beats"][0]["do"][0]["kind"] = "teleporter"
    assert any("sim kind must be one of" in e for e in cl.lint(script)[0])


def test_a_journey_is_checked_and_drawn():
    script = {"title": "Salt", "region": {"country": "India"}, "chapters": [{"title": "March", "beats": [
        {"say": "From Sabarmati to Dandi.", "do": [{"op": "journey", "stops": ["Ahmedabad", [72.80, 20.89]],
                                                    "labels": ["Sabarmati", "Dandi"]}]}]}]}
    assert cl.lint(json.loads(json.dumps(script)))[0] == []
    source = cl.compile_script(json.loads(json.dumps(script)))
    assert "self.journey([" in source and "(72.8, 20.89)" in source and "labels=['Sabarmati', 'Dandi']" in source
    short = json.loads(json.dumps(script))
    short["chapters"][0]["beats"][0]["do"][0]["stops"] = ["Ahmedabad"]
    assert any("'journey' needs stops" in e for e in cl.lint(short)[0])


def test_the_script_writer_is_told_about_every_new_sim():
    prompt = (REPO / "harness" / "app" / "lib" / "lecture.ts").read_text()
    missing = [kind for kind in sims_more.MORE if f"{kind}:" not in prompt]
    assert not missing, missing
    assert '"op":"journey"' in prompt


def test_moving_parts_stay_with_the_still_ones_once_fitted():
    """A sim's step places its moving parts from the box; fitted into the stage (or moved with it) they must still
    stand where the still parts are. The columns' bars stood below their axis on the board."""
    import pocket_lecture as pl
    import stem

    pl.use_style("chalkboard")
    made = live.BUILDERS["columns"]({}, BOX)
    step = stem._in_own_frame(made.body, made.step, BOX)
    stem._fit_into([made.body], (2.0, 1.0, 6.0, 3.0))
    made.body.shift([0.5, -0.3, 0])
    step(1.0, 1.0)
    axis, bar = made.body[0], made.body[2]
    assert abs(bar.get_bottom()[1] - axis.get_center()[1]) < 1e-6
    assert abs(axis.get_center()[0] - 2.5) < 0.3
