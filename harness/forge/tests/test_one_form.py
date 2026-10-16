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
    # A drawing in words is a detailed diagram the diagram model makes: never drawn as an SVG.
    assert ops[3] == {"op": "illustration", "query": "A block on a smooth slope, its weight drawn down",
                      "diagram": True, "_drawn": ops[3]["_drawn"]} and ops[3]["_drawn"]
    # Several pictures are a gallery: each brought forward as it is said.
    assert ops[4]["op"] == "gallery" and len(ops[4]["items"]) == 2


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
    assert cl.DIAGRAM_KINDS == {"flow", "cycle", "hub", "pyramid"}


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
    assert cl._picture_fetch({"generate": "deer"}) == {"op": "illustration", "query": "deer", "optional": True,
                                                       "aspect": "1:1", "look": "child"}


def test_a_timeline_of_one_event_is_a_card_and_of_none_is_left_out():
    """A timeline with fewer than two dates was sent back to the writer; now the compiler mends it itself."""
    script = _script([{"op": "timeline", "events": [["1066", "Norman Conquest"]]}],
                     [{"op": "timeline", "events": []}])
    errors, warnings = cl.lint(script)
    assert not errors, errors
    first, second = (b["do"] for b in script["chapters"][0]["beats"])
    assert first == [{"op": "fact", "text": "1066: Norman Conquest"}] and second == []
    assert any("timeline of one event shown as a card" in w for w in warnings)
    assert any("left out 'timeline'" in w for w in warnings)
    assert cl.compile_script(script, "GeneratedScene")


def test_a_compare_of_one_column_is_a_card_and_too_many_are_cut():
    script = _script([{"op": "compare", "columns": [{"title": "Monks", "points": ["pray", "copy books"]}]}],
                     [{"op": "compare", "columns": [{"title": t, "points": ["x"]} for t in "ABCD"]}])
    errors, warnings = cl.lint(script)
    assert not errors, errors
    first, second = (b["do"] for b in script["chapters"][0]["beats"])
    assert first == [{"op": "fact", "text": "Monks: pray; copy books"}]
    assert [c["title"] for c in second[0]["columns"]] == ["A", "B", "C"]


def test_a_region_the_map_does_not_know_is_mended():
    """England is part of the United Kingdom in Natural Earth; a region nothing knows leaves the lecture mapless
    (its map ops left out) instead of sending the section back."""
    script = _script([{"op": "marker", "place": "London"}], region={"country": "England"})
    errors, warnings = cl.lint(script)
    assert not errors, errors
    assert script["region"] == {"country": "United Kingdom"}
    assert any("region 'England' drawn as 'United Kingdom'" in w for w in warnings)
    script = _script([{"op": "marker", "place": "Camelot"}], region={"country": "Lyonesse"})
    errors, warnings = cl.lint(script)
    assert not errors, errors
    assert script["region"] is None and script["chapters"][0]["beats"][0]["do"] == []


def test_a_detailed_drawing_is_made_by_the_diagram_model_never_as_an_svg(tmp_path, monkeypatch):
    """A draw op (and a picture beside a label described as a drawing) is a picture the diagram model makes, its
    labels written by the board; its parts are not revealed one by one, so reveals and focuses of it are dropped."""
    import genimage

    monkeypatch.setenv("PANIM_IMAGE_FAKE", "1")
    monkeypatch.setattr(genimage, "CACHE", tmp_path)
    monkeypatch.setenv("PANIM_DIAGRAM_MODEL", "test/diagram-model")
    asked = []
    real = genimage._generate
    monkeypatch.setattr(genimage, "_generate", lambda *a, **k: asked.append(genimage.model()) or real(*a, **k))
    script = _script([{"op": "draw", "id": "leaf", "what": "A cross-section of a green leaf, its cells and a stoma",
                       "parts": ["upper_epidermis", "palisade", "stoma"]}],
                     [{"op": "focus", "diagram": "leaf", "node": "palisade"}],
                     [{"op": "diagram", "id": "d", "nodes": [{"id": "a", "label": "Cow", "entity": "coco:7-cow"},
                                                             {"id": "b", "label": "Barn",
                                                              "picture": {"draw": "a red barn"}}]}])
    errors, warnings = cl.lint(script)
    assert not errors, errors
    assert any("shown whole as a picture" in w for w in warnings)
    beats = script["chapters"][0]["beats"]
    assert beats[1]["do"] == []                                               # the focus went
    leaf = beats[0]["do"][0]
    assert leaf["op"] == "illustration" and leaf["diagram"] is True
    assert leaf["labels"] == ["upper epidermis", "palisade", "stoma"]
    nodes = beats[2]["do"][0]["nodes"]
    assert nodes[0]["picture"] == {"generate": "cow"} and nodes[1]["picture"] == {"generate": "a red barn"}
    assert asked[0] == "test/diagram-model"                                   # the drawing: the diagram model
    source = cl.compile_script(script)
    assert "svg" not in source.lower() and "self.stage_image(" in source and "labels=[('upper epidermis'" in source


def test_a_manim_figure_sharing_its_beat_is_given_a_beat_of_its_own():
    code = "class Fig(Scene):\n    def construct(self):\n        self.add(Circle())\n"
    script = {"chapters": [{"title": "C", "beats": [
        {"say": "Here is the field. Watch it bend the beam.", "do": [
            {"op": "panel", "title": "Fields"}, {"op": "manim", "code": code}]},
        {"say": "One line only.", "do": [{"op": "manim", "code": code}, {"op": "fact", "text": "E = F/q"}]},
        {"say": "Next.", "do": []},
    ]}]}
    notes = cl.mechanical_fixes(script, has_map=False)
    beats = script["chapters"][0]["beats"]
    # Two sentences: shared, in the order the ops were written (the panel first).
    assert [b["say"] for b in beats[:2]] == ["Here is the field.", "Watch it bend the beam."]
    assert [op["op"] for op in beats[0]["do"]] == ["panel"]
    assert [op["op"] for op in beats[1]["do"]] == ["manim"]
    # One sentence: the figure keeps the beat, its other op moves to the next beat that is not a figure.
    assert [op["op"] for op in beats[2]["do"]] == ["manim"]
    assert [op["op"] for op in beats[3]["do"]] == ["fact"]
    assert sum("manim figure" in n for n in notes) == 2 and all(n.startswith(cl.FIXED) for n in notes if "manim" in n)
    for beat in beats:
        ops = beat["do"]
        assert not (any(op["op"] == "manim" for op in ops) and len(ops) > 1)
