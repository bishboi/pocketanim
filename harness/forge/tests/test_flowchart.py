"""Flowcharts (harness/lecture/flowchart.py and pocket_lecture._flowchart): processes that branch, decide, join
and loop back, laid out in ranks; the compiler's rules for them; and the words in pictures written in the art
style's font."""

from __future__ import annotations

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import artstyle  # noqa: E402
import compile_lecture as cl  # noqa: E402
import flowchart as fc  # noqa: E402

from test_sims_more import REPO  # noqa: E402

LAW = ["intro", "debate", "pass", "rs", "rs_pass", "joint", "president", "law", "lapse"]
LAW_EDGES = [("intro", "debate"), ("debate", "pass"), ("pass", "rs"), ("pass", "lapse"), ("rs", "rs_pass"),
             ("rs_pass", "president"), ("rs_pass", "joint"), ("joint", "president"), ("president", "law"),
             ("president", "debate")]


def _sizes(ids, w=2.0, h=0.8):
    return {i: (w, h) for i in ids}


def test_ranks_follow_the_flow_and_loops_go_round():
    lay = fc.layout(LAW, LAW_EDGES, _sizes(LAW))
    rank = lay.rank_of
    backs = [(a, b) for a, b, _, back in lay.routes if back]
    assert backs == [("president", "debate")]
    for a, b in LAW_EDGES:
        if (a, b) not in backs:
            assert rank[b] > rank[a], (a, b)


def test_long_arrows_pass_through_gaps():
    ids = ["a", "b", "c", "d"]
    lay = fc.layout(ids, [("a", "b"), ("b", "c"), ("c", "d"), ("a", "d")], _sizes(ids))
    skip = [way for a, b, way, back in lay.routes if (a, b) == ("a", "d")][0]
    assert len(skip) == 2                                  # a waypoint in each rank it crosses
    for x, y in skip:
        for i in ("b", "c"):
            cx, cy = lay.centres[i]
            assert abs(x - cx) > 1.0 or abs(y - cy) > 0.5     # never through a box


def test_few_crossings():
    ids = ["s", "a", "b", "c", "d", "e"]
    edges = [("s", "a"), ("s", "b"), ("a", "d"), ("b", "c"), ("a", "e"), ("b", "e")]
    lay = fc.layout(ids, edges, _sizes(ids))
    assert fc.crossings(lay, edges) == 0


def test_lanes_are_bands_that_do_not_overlap():
    lanes = {"intro": "Lok Sabha", "debate": "Lok Sabha", "pass": "Lok Sabha", "lapse": "Lok Sabha",
             "rs": "Rajya Sabha", "rs_pass": "Rajya Sabha", "joint": "Rajya Sabha",
             "president": "President", "law": "President"}
    lay = fc.layout(LAW, LAW_EDGES, _sizes(LAW), lanes=lanes, direction="right")
    assert [name for name, _, _ in lay.lanes] == ["Lok Sabha", "Rajya Sabha", "President"]
    spans = sorted((lo, hi) for _, lo, hi in lay.lanes)
    for (lo1, hi1), (lo2, hi2) in zip(spans, spans[1:]):
        assert hi1 <= lo2 + 1e-9
    for name, lo, hi in lay.lanes:
        for i, lane in lanes.items():
            if lane == name:
                assert lo <= lay.centres[i][1] <= hi


def test_the_board_shape_picks_the_direction():
    chain = [f"n{k}" for k in range(4)]
    tall = fc.layout(chain, list(zip(chain, chain[1:])), _sizes(chain, 3.5, 0.6), board=(6.0, 12.0))
    wide = fc.layout(chain, list(zip(chain, chain[1:])), _sizes(chain, 1.5, 0.6), board=(12.6, 6.0))
    assert tall.direction == "down" and wide.direction == "right"


def _script(op):
    return {"title": "T", "style": "chalkboard", "chapters": [{"title": "A", "beats": [
        {"say": "Here is how the process goes, step by step, with every branch and loop.", "do": [op]}]}]}


def _flowchart(**extra):
    return {"op": "diagram", "id": "f", "kind": "flowchart",
            "nodes": [{"id": "s", "label": "Start", "shape": "start"}, {"id": "q", "label": "Hot?", "shape": "decision"},
                      {"id": "a", "label": "Heater off", "lane": "Room"}, {"id": "b", "label": "Heater on", "lane": "Room"}],
            "edges": [["s", "q"], ["q", "a", "Yes"], ["q", "b", "No", "dashed"], {"from": "b", "to": "q", "style": "bold"}],
            **extra}


def test_the_compiler_takes_a_flowchart():
    script = _script(_flowchart())
    assert not cl.lint(script)[0]
    source = cl.compile_script(_script(_flowchart()))
    assert "'shape': 'decision'" in source and "'lane': 'Room'" in source
    assert "['q', 'b', 'No', 'dashed']" in source and "['b', 'q', '', 'bold']" in source


def test_the_compiler_refuses_what_it_cannot_draw():
    bad_shape = _flowchart()
    bad_shape["nodes"][0]["shape"] = "hexagon"
    errors, warnings = cl.lint(_script(bad_shape))          # mended, not sent back: a plain box
    assert not errors and any("fixed:" in w and "no shape 'hexagon'" in w for w in warnings)
    assert "shape" not in bad_shape["nodes"][0]
    bad_style = _flowchart()
    bad_style["edges"][1] = ["q", "a", "Yes", "wiggly"]
    assert not cl.lint(_script(bad_style))[0] and bad_style["edges"][1][3] == "solid"
    many = _flowchart()
    many["nodes"] = [{"id": f"n{k}", "label": f"Step {k}"} for k in range(17)]
    many["edges"] = []
    assert any("2-16 nodes" in e for e in cl.lint(_script(many))[0])
    cycle = {**_flowchart(), "kind": "cycle"}
    cycle["nodes"] = [{"id": f"n{k}", "label": f"Step {k}"} for k in range(12)]
    cycle["edges"] = []
    assert any("2-9 nodes" in e for e in cl.lint(_script(cycle))[0])


def test_the_script_writer_is_told():
    prompt = (REPO / "harness/app/lib/lecture.ts").read_text()
    assert 'FLOWCHARTS' in prompt and '"kind":"flow"|"cycle"|"hub"' in prompt and '"decision"' in prompt and '"lane"' in prompt


@pytest.mark.parametrize("art", list(artstyle.ART_STYLES))
def test_picture_words_take_the_art_styles_font(art):
    import pocket_lecture as pl

    pl.use_style("chalkboard")
    artstyle.use(art)
    outside = pl.T("Panel words", 20)
    with artstyle.drawing():
        inside = pl.T("Heater on", 20)
    assert outside.font == pl.TH["sans"]
    want = artstyle.ART_FONTS[art]
    if want and want.lower() in artstyle._installed():
        assert inside.font == want
    else:
        assert inside.font == pl.TH["sans"]
    artstyle.use("auto", "chalkboard")
