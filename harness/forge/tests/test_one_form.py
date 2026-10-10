"""One op for every picture, three diagram kinds, and faults the compiler mends by itself (compile_lecture
canonical_ops, mechanical_fixes): what needs no new words is fixed and said in a "fixed: " warning, never sent
back to the writer."""

from __future__ import annotations

import json

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402


def _script(*beats, **extra):
    return {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False, **extra,
            "chapters": [{"title": "A", "map": False, "beats": [{"say": f"Line {k}.", "do": list(do)}
                                                                  for k, do in enumerate(beats)]}]}


def test_the_picture_op_is_each_of_the_old_ones():
    script = _script([{"op": "picture", "subject": "Marie Curie", "caption": "Curie"}],
                     [{"op": "picture", "illustration": "water cycle"}],
                     [{"op": "picture", "figure": "fig1", "photo": True}],
                     [{"op": "picture", "draw": "A block on a smooth slope, its weight drawn down"}],
                     [{"op": "picture", "items": [{"subject": "Pierre Curie"}, {"subject": "Marie Curie"}]}],
                     figures={"fig1": {"file": "/tmp/x.png", "caption": "Figure 1"}})
    cl.canonical_ops(script)
    ops = [b["do"][0] for b in script["chapters"][0]["beats"]]
    assert ops[0] == {"op": "photo", "subject": "Marie Curie", "caption": "Curie"}
    assert ops[1] == {"op": "illustration", "query": "water cycle"}
    assert ops[2] == {"op": "figure", "id": "fig1", "photo": True}
    assert ops[3]["op"] == "draw" and ops[3]["parts"] == ["picture"] and ops[3]["id"] and "draw" not in ops[3]
    assert ops[4]["op"] == "gallery"


def test_three_diagram_kinds_and_the_old_ones_as_aliases():
    nodes = [{"id": i, "label": i.title()} for i in ("whole", "a", "b", "c")]
    tree = {"op": "diagram", "id": "d", "kind": "categories", "nodes": nodes}
    steps = {"op": "diagram", "id": "s", "kind": "steps", "nodes": nodes}
    chart = {"op": "diagram", "id": "f", "kind": "flowchart", "nodes": nodes}
    script = _script([tree], [steps], [chart])
    assert not cl.lint(script)[0]
    assert tree["kind"] == "flow" and tree["edges"] == [["whole", "a"], ["whole", "b"], ["whole", "c"]]
    assert steps["kind"] == "flow" and steps["steps"] is True and chart["kind"] == "flow"
    source = cl.compile_script(script)
    assert 'self.diagram("s", "flow"' in source and "numbered=True" in source
    assert cl.DIAGRAM_KINDS == {"flow", "cycle", "hub"}


def test_steps_that_point_at_nothing_are_left_out_with_a_warning():
    nodes = [{"id": i, "label": i.title()} for i in ("a", "b", "c")]
    script = _script([{"op": "diagram", "id": "d", "nodes": nodes, "show": ["a", "zz"], "edges": [["a", "b"], ["a", "q"]]}],
                     [{"op": "reveal", "diagram": "d", "nodes": ["b", "nope"]}, {"op": "focus", "diagram": "d", "node": "x"}],
                     [{"op": "reveal", "diagram": "ghost", "nodes": ["a"]}, {"op": "answer"}],
                     [{"op": "sparkle"}])
    errors, warnings = cl.lint(script)
    assert not errors, errors
    beats = script["chapters"][0]["beats"]
    assert beats[0]["do"][0]["show"] == ["a"] and beats[0]["do"][0]["edges"] == [["a", "b"]]
    assert beats[1]["do"] == [{"op": "reveal", "diagram": "d", "nodes": ["b", "c"]}]   # c: never shown, added
    assert beats[2]["do"] == [] and beats[3]["do"] == []
    fixed = [w for w in warnings if w.startswith("fixed: ")]
    assert any("no op" in w or "no such op" in w for w in fixed) and any("'ghost'" in w for w in fixed)
    assert any("parts never revealed (c) join its last reveal" in w for w in fixed)


def test_a_marker_on_no_place_is_left_out_and_the_rest_stays():
    script = {"title": "T", "style": "vox", "region": {"country": "India"}, "auto_visuals": False,
              "place_figures": False, "chapters": [{"title": "A", "beats": [
                  {"say": "Agra, and a town no map has.", "do": [{"op": "marker", "place": "Agra"},
                                                                {"op": "marker", "place": "Qwertyuiopville"}]},
                  {"say": "A march.", "do": [{"op": "journey", "stops": ["Agra", "Qwertyuiopville", "Delhi"],
                                              "labels": ["Agra", "Nowhere", "Delhi"]}]}]}]}
    errors, warnings = cl.lint(script)
    assert not errors, errors
    beats = script["chapters"][0]["beats"]
    assert beats[0]["do"] == [{"op": "marker", "place": "Agra"}]
    assert beats[1]["do"][0]["stops"] == ["Agra", "Delhi"] and beats[1]["do"][0]["labels"] == ["Agra", "Delhi"]
    assert sum("Qwertyuiopville" in w and w.startswith("fixed:") for w in warnings) == 2
    json.dumps(script)


def test_with_teaching_rules_off_only_drawing_is_checked():
    """The app's lectures: how to teach is the writer's, so no length, question, example or copying checks."""
    script = _script([{"op": "panel", "title": "A"}], [], [], teaching_rules=False,
                     source_text="A force is a push or a pull on a body that changes its motion in some way.")
    script["chapters"][0]["beats"][1]["say"] = "A force is a push or a pull on a body that changes its motion in some way."
    errors, _ = cl.lint(script, min_minutes=30, min_questions=5, min_examples=5, min_problems=2)
    assert errors == [], errors
    ruled = {k: v for k, v in script.items() if k != "teaching_rules"}
    assert cl.lint(ruled, min_minutes=30, min_questions=5)[0]          # the old checks still run for Forge
    script["chapters"][0]["beats"][0]["do"] = [{"op": "diagram", "id": "d", "nodes": [{"id": "a"}]}]
    assert cl.lint(script)[0]                                          # what cannot be drawn is still an error


def test_only_three_ways_to_a_picture():
    """A picture is made by the image model, drawn as an SVG, or built in Manim: a node's library drawing (entity)
    becomes a picture the image model makes; a define card's or a comparison's library drawing is gone; the
    picture op's "generate" asks the image model."""
    script = _script([{"op": "diagram", "id": "d", "nodes": [{"id": "a", "label": "Deer", "entity": "deer"},
                                                             {"id": "b", "label": "Grass"}]}],
                     [{"op": "define", "term": "Biome", "meaning": "a big living region", "entity": "tree"},
                      {"op": "compare", "columns": [{"title": "A", "entity": "x", "points": ["p"]},
                                                   {"title": "B", "points": ["q"]}]}],
                     [{"op": "picture", "generate": "a red deer in a meadow, side view", "caption": "Deer"}],
                     [{"op": "timeline", "events": [["1526", "Panipat", {"entity": "sword"}], ["1556", "Akbar"]]}])
    cl.canonical_ops(script)
    beats = script["chapters"][0]["beats"]
    node = beats[0]["do"][0]["nodes"][0]
    assert "entity" not in node and node["picture"] == {"generate": "deer"}
    assert "entity" not in beats[1]["do"][0] and "entity" not in beats[1]["do"][1]["columns"][0]
    assert beats[2]["do"][0] == {"op": "illustration", "query": "a red deer in a meadow, side view", "caption": "Deer"}
    assert beats[3]["do"][0]["events"][0][2] == {"generate": "sword"}
    assert cl._picture_fetch({"generate": "deer"}) == {"op": "illustration", "query": "deer", "optional": True}
