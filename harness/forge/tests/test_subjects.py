"""Subject kits: the content decides the lecture -- style, map policy, and the pictures (molecules, equations...)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from forge.util import LECTURE

import compile_lecture as cl  # noqa: E402 -- harness/lecture is on the path via forge.util
import genre  # noqa: E402

HERE = Path(__file__).resolve().parents[1]

SAMPLES = {
    "biology": "Plants make glucose by photosynthesis. Chlorophyll in the leaves captures light; the cell releases oxygen.",
    "chemistry": "Methane burns in oxygen: CH4 + 2O2 -> CO2 + 2H2O. The reaction releases energy as the bonds change.",
    "physics": "Newton's second law says force equals mass times acceleration, F = ma, for any moving body.",
    "history": "The Mughal Empire was founded by Babur in 1526 after the battle of Panipat. Akbar ruled from 1556.",
    "geography": "Rajasthan is the largest state of India. The Aravalli range and the Thar desert shape its rainfall.",
    "mathematics": "The derivative of x^2 is 2x. A function's graph has a slope equal to its derivative.",
    "economics": "Inflation rises when demand grows faster than supply, and the central bank raises interest rates.",
}


@pytest.mark.parametrize("expected", sorted(SAMPLES))
def test_classify(expected):
    result = genre.classify(SAMPLES[expected])
    assert result["genre"] == expected
    assert result["style"] in ("vox", "parchment", "lab", "cosmos", "chalkboard", "atlas", "blueprint")


def test_equations_and_timelines_from_narration():
    assert cl._equation_in("The equation is CH4 + 2O2 -> CO2 + 2H2O.") == "CH_4 + 2O_2 -> CO_2 + 2H_2O"
    assert cl._equation_in("Einstein showed that E = mc^2 links mass and energy.") == "E = mc^2"
    assert cl._equation_in("Prices rose sharply in 1991.") is None
    events = cl._timeline_of({"beats": [{"say": "Babur won at Panipat in 1526."}, {"say": "Akbar ruled from 1556."},
                                        {"say": "Aurangzeb died in 1707."}]})
    assert events == [["1526", "Babur Panipat"], ["1556", "Akbar"], ["1707", "Aurangzeb"]]


def test_science_beats_get_molecules_and_equations():
    pytest.importorskip("rdkit")
    # One visual a paragraph: the paragraph's equation, on its first beat; the next beat keeps it.
    fills = cl.auto_visuals({"beats": [{"say": "Plants turn carbon dioxide and water into glucose."},
                                       {"say": "The equation is 6CO2 + 6H2O -> C6H12O6 + 6O2."}]}, genre="biology")
    assert fills[0]["op"] == "equation" and "C_6H_{12}O_6" in fills[0]["tex"] and fills[1] is None
    # A paragraph that only names substances gets no structural formula: it is said, not drawn.
    fills = cl.auto_visuals({"beats": [{"say": "The equation is 6CO2 + 6H2O -> C6H12O6 + 6O2."},
                                       {"say": "Plants turn carbon dioxide and water into glucose.", "paragraph": True}]},
                            genre="chemistry")
    assert fills[1] is None or fills[1].get("op") != "molecule"
    # One that explains a structure gets it, once a chapter, never again for the same molecule.
    fills = cl.auto_visuals({"beats": [
        {"say": "Carbon dioxide is a linear molecule: two double bonds join the carbon to the oxygen atoms."},
        {"say": "Now think about the weather today.", "paragraph": True},
        {"say": "Glucose has six carbon atoms, five of them in a ring.", "paragraph": True}]}, genre="chemistry")
    assert fills[0] == {"op": "molecule", "name": "carbon dioxide"}
    assert all(f is None or f.get("op") != "molecule" for f in fills[1:])


def test_a_molecule_the_model_draws_stays_only_where_its_structure_is_explained():
    beat = lambda say, name: {"say": say, "do": [{"op": "molecule", "name": name}]}  # noqa: E731
    script = {"genre": "chemistry", "chapters": [{"title": "c", "beats": [
        beat("Water is everywhere in the body.", "water"),
        beat("Glucose gives us energy.", "glucose"),
        beat("Glucose has six carbon atoms in a ring with hydroxyl groups.", "glucose"),
        beat("पानी के अणु की संरचना मुड़ी हुई है।", "water")]}]}
    notes = cl._unneeded_molecules(script, drop=True)
    kept = [[op["name"] for op in b["do"]] for b in script["chapters"][0]["beats"]]
    # Named in passing: left out; its structure explained on the next beat: kept, and not drawn twice; a Hindi
    # beat about water's structure: kept.
    assert kept == [[], ["glucose"], [], ["water"]], (kept, notes)


def test_a_biology_paragraph_without_a_picture_gets_an_illustration_of_its_topic(monkeypatch):
    import images

    asked = []
    monkeypatch.setattr(cl, "script_photos", {})            # the compiler's picture table: this test's own
    monkeypatch.setattr(cl, "USED_PICTURES", set())
    monkeypatch.setattr(images, "enabled", lambda: True)
    monkeypatch.setattr(images, "fetch", lambda **kw: asked.append(kw) or (
        {"id": "x1", "title": kw.get("illustration"), "credit": "test"} if kw.get("illustration") else None))
    fills = cl.auto_visuals({"title": "The leaf", "beats": [
        {"say": "The leaf makes food for the plant in its green cells."}]}, genre="biology")
    assert fills[0] and fills[0]["op"] == "illustration"
    assert any(kw.get("illustration") for kw in asked)


def test_kit_ops_lint():
    pytest.importorskip("rdkit")
    assert cl._kit_problem({"op": "molecule", "name": "glucose"}) is None
    assert "no molecule" in cl._kit_problem({"op": "molecule", "name": "unobtainium-xyz"})
    assert cl._kit_problem({"op": "plot", "expr": "x^2 - 3*x", "x": [0, 5]}) is None
    assert "unknown name" in cl._kit_problem({"op": "plot", "expr": "__import__('os')", "x": [0, 5]})
    assert cl._kit_problem({"op": "process", "steps": ["one"]})


def test_unused_figures_are_placed_where_the_narration_names_them():
    script = {"figures": {"fig1": {"file": "a.png", "caption": "Figure 1: Area under the main crops"},
                          "fig2": {"file": "b.png", "caption": "Figure 2: Monsoon rainfall"}},
              "chapters": [{"beats": [{"say": "The plain is flat.", "do": []},
                                      {"say": "The monsoon brings the rainfall.", "do": []},
                                      {"say": "It is hot.", "do": []},
                                      {"say": "The main crops cover the area.", "do": []}]}]}
    assert cl.place_figures(script) == 2
    placed = {op["id"]: i for i, b in enumerate(script["chapters"][0]["beats"]) for op in b["do"]}
    assert placed == {"fig2": 1, "fig1": 3}


def test_forge_auto_picks_template_and_style(tmp_path):
    from forge import machine
    from forge.job import Job

    job = Job.create("auto", template="auto", style="auto", title="Combustion",
                     content=(HERE / "examples" / "combustion.md").read_text(), root=tmp_path / "jobs")
    run = machine.Run(job)
    run.intake()
    run.resolve()
    spec = job.spec
    assert (spec["genre"], spec["template"], spec["style"]) == ("chemistry", "science_explainer", "lab")
    assert spec.get("region_id") is None


def test_kit_visuals_without_icon_library(monkeypatch):
    """No icon library means no illustrations, but molecules and equations still come."""
    import icons
    from compile_lecture import auto_visuals

    monkeypatch.setattr(icons, "available", lambda: [])
    chapter = {"title": "Burning", "beats": [
        {"say": "Methane burns: CH4 + 2O2 -> CO2 + 2H2O releases heat.", "do": []},
        {"say": "Sugarcane and wheat grow on the plains.", "do": []}]}
    fills = auto_visuals(chapter, genre="chemistry")
    assert fills[0] and fills[0]["op"] in ("equation", "molecule")
    assert fills[1] is None


def test_hindi_chapter_is_classified_by_its_words():
    from genre import classify

    text = ("# वन एवं वन्य जीव संसाधन\nभारत में वन और वन्य जीव संसाधन। 1972 में वन्यजीव अधिनियम लागू हुआ। 1973 में "
            "प्रोजेक्ट टाइगर। राष्ट्रीय उद्यान और अभयारण्य बनाए गए। मध्य प्रदेश राज्य में स्थायी वन क्षेत्र सबसे अधिक है। "
            "राजस्थान के अलवर जिले में वन भूमि का संरक्षण। हिमालय क्षेत्र में चिपको आंदोलन। 1988 में ओडिशा।")
    assert classify(text)["genre"] == "geography"


def test_reading_the_book_aloud_is_an_error():
    from compile_lecture import lint

    book = ("यह पूरा आवासीय स्थल जिस पर हम रहते हैं, अत्यधिक जैव-विविधताओं से भरा हुआ है। वन पारिस्थितिकी तंत्र "
            "में महत्वपूर्ण भूमिका निभाते हैं क्योंकि ये प्राथमिक उत्पादक हैं जिन पर दूसरे सभी जीव निर्भर करते हैं।")
    copied = {"say": "वन पारिस्थितिकी तंत्र में महत्वपूर्ण भूमिका निभाते हैं क्योंकि ये प्राथमिक उत्पादक हैं।", "do": []}
    simple = {"say": "जंगल एक बड़े साझा घर जैसा है। पेड़ खाना बनाते हैं, और बाकी सब जीव उसी पर जीते हैं।", "do": []}
    script = {"title": "वन", "source_text": book,
              "chapters": [{"title": "वन", "narration": "अध्याय एक।", "beats": [copied] * 4 + [simple] * 4}]}
    errors, _ = lint(script)
    assert any("word for word" in e for e in errors)
    script["chapters"][0]["beats"] = [simple] * 8
    errors, _ = lint(script)
    assert not any("word for word" in e for e in errors)


def test_boxes_of_words_are_an_error_and_qr_codes_are_not_figures():
    from compile_lecture import lint, place_figures

    box = {"say": "Plants make food, animals eat plants, and bigger animals eat them.",
           "do": [{"op": "process", "steps": ["Plants", "Deer", "Tiger"]}]}
    script = {"title": "Forests", "chapters": [{"title": "Food", "narration": "Chapter one.", "beats": [box] * 8}]}
    errors, _ = lint(script)
    assert any("boxes of words" in e for e in errors)

    script = {"figures": {"fig1": {"file": "q.png", "caption": "QR code linking to the content"},
                          "fig2": {"file": "t.png", "caption": "A tiger in the forest"}},
              "chapters": [{"title": "t", "beats": [{"say": "The tiger lives in the forest.", "do": []},
                                                    {"say": "It hunts deer at night.", "do": []},
                                                    {"say": "Forests give it cover.", "do": []},
                                                    {"say": "Its numbers fell.", "do": []}]}]}
    place_figures(script)
    shown = [op["id"] for c in script["chapters"] for b in c["beats"] for op in b["do"] if op["op"] == "figure"]
    assert shown == ["fig2"]


def test_icon_search_falls_back_to_simpler_words():
    import icons

    if not icons.available():
        return
    assert icons.search("farmers") and icons.search("villagers")


def test_paragraphs_hold_one_visual():
    beats = [{"say": "a", "do": [{"op": "diagram", "id": "d", "nodes": [{"id": "x", "label": "X"}, {"id": "y", "label": "Y"}]}]},
             {"say": "b", "do": [{"op": "reveal", "diagram": "d", "nodes": ["y"]}]},
             {"say": "c"}, {"say": "d", "paragraph": True}, {"say": "e"}, {"say": "f"}, {"say": "g"}, {"say": "h"},
             {"say": "i"}]
    assert cl.paragraphs(beats) == [[0, 1, 2], [3, 4, 5, 6, 7], [8]]


def test_diagram_gallery_define_compare_checks():
    diagrams: dict = {}
    good = {"op": "diagram", "id": "chain", "kind": "flow",
            "nodes": [{"id": "sun", "label": "Sun", "entity": "sun"}, {"id": "tree", "label": "Tree"}],
            "edges": [["sun", "tree", "light"]], "show": ["sun"]}
    assert cl._build_problem(good, diagrams, {}) is None and diagrams == {"chain": ["sun", "tree"]}
    assert cl._build_problem({"op": "reveal", "diagram": "chain", "nodes": ["tree"]}, diagrams, {}) is None
    assert "nodes must be ids" in cl._build_problem({"op": "reveal", "diagram": "chain", "nodes": ["moon"]}, diagrams, {})
    assert "drawn earlier" in cl._build_problem({"op": "focus", "diagram": "other", "node": "x"}, diagrams, {})
    assert "edge" in cl._build_problem({**good, "edges": [["sun", "moon"]]}, {}, {})
    assert "kind" in cl._build_problem({**good, "kind": "spiral"}, {}, {})
    assert cl._build_problem({"op": "gallery", "items": [{"figure": "fig1"}, {"subject": "Akbar"}]}, {}, {"fig1": {}}) is None
    assert "no figure" in cl._build_problem({"op": "gallery", "items": [{"figure": "fig9"}]}, {}, {"fig1": {}})
    assert cl._build_problem({"op": "define", "term": "Biodiversity"}, {}, {})
    assert cl._build_problem({"op": "compare", "columns": [{"title": "A"}]}, {}, {})


def test_new_ops_compile_and_a_picture_a_sentence_is_flagged(tmp_path):
    from PIL import Image

    Image.new("RGB", (400, 300), "white").save(tmp_path / "f.png")
    node = lambda i: {"id": i, "label": i.title(), "entity": i}  # noqa: E731
    script = {"title": "T", "style": "lab", "figures": {"fig1": {"file": str(tmp_path / "f.png"), "caption": "F"}},
              "place_figures": False, "chapters": [{"title": "C", "narration": "One.", "beats": [
                  {"say": "one two three four five six seven eight", "do": [
                      {"op": "diagram", "id": "d", "kind": "cycle", "nodes": [node("sun"), node("rain"), node("river")],
                       "show": ["sun"]}]},
                  {"say": "one two three four five six seven eight", "do": [{"op": "reveal", "diagram": "d", "nodes": ["rain", "river"]}]},
                  {"say": "one two three four five six seven eight", "do": [{"op": "focus", "diagram": "d", "node": "rain"}]},
                  {"say": "one two three four five six seven eight", "do": [
                      {"op": "define", "term": "Evaporation", "meaning": "Water turning into vapour"}]},
                  {"say": "one two three four five six seven eight", "do": [
                      {"op": "compare", "columns": [{"title": "A", "points": ["x"]}, {"title": "B", "points": ["y"]}]}]},
                  {"say": "one two three four five six seven eight", "do": [
                      {"op": "gallery", "items": [{"figure": "fig1", "caption": "one"}, {"figure": "fig1", "caption": "two"}]}]},
                  {"say": "one two three four five six seven eight", "do": [
                      {"op": "define", "term": "Rain", "meaning": "Water falling"}]},
                  {"say": "one two three four five six seven eight", "do": [
                      {"op": "define", "term": "River", "meaning": "Water flowing"}]}]}]}
    errors, warnings = cl.lint(script)
    assert errors == [], errors
    assert any("a picture a sentence" in w for w in warnings)
    source = cl.compile_script(json.loads(json.dumps(script)))
    for call in ("self.diagram(", "self.reveal_nodes(", "self.spotlight(", "self.define(", "self.compare_cards(",
                 "self.gallery("):
        assert call in source, call


def test_forge_leaves_out_figures_removed_on_the_upload_page(monkeypatch, tmp_path):
    import pdf_source

    from forge.engine import ingest

    (tmp_path / "doc").mkdir()
    pdf = tmp_path / "doc" / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    (tmp_path / "doc" / "excluded.json").write_text('["fig2"]')
    markdown = tmp_path / "doc.md"
    markdown.write_text("Text.\n[FIGURE fig1: One]\nMore.\n[FIGURE fig2: Two]\nEnd.")
    monkeypatch.setattr(pdf_source, "convert", lambda path, out: {"markdown": str(markdown), "figures": [
        {"id": "fig1", "file": "a.png", "caption": "One"}, {"id": "fig2", "file": "b.png", "caption": "Two"}]})
    _name, text, figures, _manifest = ingest.read_pdf(str(pdf), tmp_path, "s1", tmp_path / "out")
    assert [f["id"] for f in figures] == ["s1_fig1"]
    assert "[FIGURE s1_fig1: One]" in text and "fig2" not in text


def test_an_ai_illustration_says_what_it_cost(monkeypatch, tmp_path):
    """The image model's bill (OpenRouter's usage) comes back on the row and is added up for the build."""
    import base64
    import io
    import json as _json
    import urllib.request

    import illustrations

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(illustrations, "CACHE", tmp_path)
    illustrations.reset()
    asked = []
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 32).decode()

    def fake(request, timeout=0):
        asked.append(_json.loads(request.data))
        reply = {"choices": [{"message": {"images": [{"image_url": {"url": f"data:image/png;base64,{png}"}}]}}],
                 "usage": {"cost": 0.039}}
        return io.BytesIO(_json.dumps(reply).encode())

    class Opened(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=0: Opened(fake(request).read()))
    rows = illustrations.ai("a leaf in cross section")
    assert rows and rows[0]["usd"] == 0.039 and rows[0]["made"]
    assert asked[0]["usage"] == {"include": True}
    assert illustrations.AI_MADE["count"] == 1 and illustrations.AI_MADE["usd"] == 0.039
    assert illustrations.AI_MADE["items"][0]["query"] == "a leaf in cross section"
    again = illustrations.ai("a leaf in cross section")        # drawn already: from the cache, free
    assert again and "usd" not in again[0] and again[0]["paid"] == 0.039 and illustrations.AI_MADE["count"] == 1
    illustrations.reset()
    assert illustrations.AI_MADE == {"count": 0, "usd": 0.0, "items": []}
