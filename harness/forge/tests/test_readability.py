"""What a lesson shows is readable and about the lesson: no book furniture (QR codes, scan boxes), maps zoomed to
the places they show and drawn wide when the panel would be empty, labels big enough to read, pictures as large as
their space allows."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import pdf_source as ps  # noqa: E402


def _qr(path):
    rng = np.random.default_rng(1)
    g = (rng.random((29, 29)) > 0.5).astype(np.uint8)
    for r, c in ((0, 0), (0, 22), (22, 0)):
        g[r:r + 7, c:c + 7] = 1
        g[r + 1:r + 6, c + 1:c + 6] = 0
        g[r + 2:r + 5, c + 2:c + 5] = 1
    Image.fromarray(((1 - g) * 255).astype(np.uint8)).resize((290, 290), Image.NEAREST).save(path)


def test_qr_codes_and_scan_lines_are_taken_out_of_the_book(tmp_path):
    qr, picture = tmp_path / "fig1.png", tmp_path / "fig2.png"
    _qr(qr)
    yy, xx = np.mgrid[0:200, 0:300]
    Image.fromarray((120 + 60 * np.sin(xx / 20) * np.cos(yy / 30)).astype(np.uint8)).convert("RGB").save(picture)
    md = tmp_path / "document.md"
    md.write_text("# The Three Orders\n[FIGURE fig1: ]\nScan the QR code to access e-content on DIKSHA.\n"
                  "Reprint 2024-25\nA QR code stores data in a grid.\n[FIGURE fig2: Fig. 2 A manor]\nThe manor.\n")
    manifest = {"figures": [{"id": "fig1", "file": str(qr), "caption": ""},
                            {"id": "fig2", "file": str(picture), "caption": "Fig. 2 A manor"}],
                "markdown": str(md)}
    out = ps.drop_furniture(manifest)
    assert [f["id"] for f in out["figures"]] == ["fig2"] and out["furniture"] == ["fig1"]
    text = md.read_text()
    assert "fig1" not in text and "DIKSHA" not in text and "Reprint" not in text
    assert "A QR code stores data in a grid." in text and "[FIGURE fig2" in text      # teaching stays
    assert ps.drop_furniture(out) is out                                              # nothing more to take


def _map_script(*beats, region=None):
    return {"title": "T", "style": "parchment", "auto_visuals": False, "place_figures": False,
            "region": region or {"area": "Europe"},
            "chapters": [{"title": "Feudal Europe", "beats": [{"say": f"Line {k}.", "do": list(do)}
                                                               for k, do in enumerate(beats)]}]}


def test_a_map_chapter_is_zoomed_to_its_places_and_wide_without_a_panel():
    script = _map_script([{"op": "panel", "title": "Remember the terms"},
                          {"op": "marker", "place": "Paris", "label": "France"}],
                         [{"op": "marker", "place": "London"}, {"op": "marker", "place": "Naples"}])
    assert not cl.lint(script)[0]
    source = cl.compile_script(script)
    frame = next(line for line in source.splitlines() if "use_frame" in line)
    import re

    lon0, lat0, lon1, lat1 = (float(x) for x in re.findall(r"-?\d+\.?\d*", frame.split("use_frame(")[1]))
    assert -10 < lon0 < 0 and 15 < lon1 < 25 and 33 < lat0 < 40 and 52 < lat1 < 60   # Western Europe, not Russia
    assert "self.show_map(wide=True)" in source                                        # no empty panel

    with_fact = _map_script([{"op": "marker", "place": "Paris"}, {"op": "fact", "text": "Feudalism began here."}])
    assert not cl.lint(with_fact)[0]
    assert "self.show_map()" in cl.compile_script(with_fact)                          # the panel has words

    spread = _map_script([{"op": "marker", "place": "Lisbon"}, {"op": "marker", "place": "Moscow"},
                          {"op": "marker", "place": "Oslo"}, {"op": "marker", "place": "Athens"}])
    assert not cl.lint(spread)[0]
    assert "self.use_frame(None)" in cl.compile_script(spread)                         # all over: the whole map


def test_the_gallery_picks_the_grid_that_makes_pictures_largest():
    import pocket_lecture as pl

    grid = pl.MapLecture._gallery_grid
    assert grid([0.45, 0.45, 0.45], 13.5, 5.65) == (1, 3)          # three tall figures side by side
    assert grid([1.6] * 4, 6.5, 6.1) == (2, 2)
    assert grid([1.5] * 3, 6.5, 6.1) == (2, 2)


def test_a_big_diagram_keeps_its_arrow_words_readable():
    import pocket_lecture as pl

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    scene.STAGE = (-3.05, 0.3, 6.5, 6.1)                    # the narrow stage beside a panel
    ids = [f"n{k}" for k in range(9)]
    nodes = [{"id": i, "label": f"Step number {k}"} for k, i in enumerate(ids)]
    edges = [[a, b, "then this follows"] for a, b in zip(ids, ids[1:])]
    scene.diagram("d", "flowchart", nodes, edges)
    labels = [m for _, _, e in scene.diagrams["d"]["edges"] for m in e.get_family() if getattr(m, "is_label", False)]
    # Squeezed onto the narrow stage, its words are still at least the readable size.
    assert labels and min(label.font_size for label in labels) >= pl.READABLE_LABEL * 0.98
    nodes = [m for n in scene.diagrams["d"]["nodes"].values() for m in n.get_family() if hasattr(m, "font_size")]
    assert nodes


def test_the_chapter_tag_is_large():
    import pocket_lecture as pl

    class Probe(pl.MapLecture):
        SECTIONS = ["", "A changing Europe"]

        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.section(1)
    tag = scene.chrome[-1]
    assert tag.height >= pl.T("A", 23).height * 0.9


def test_each_beat_is_checked_and_what_can_be_mended_is(tmp_path, monkeypatch):
    """The visual check after each beat: text off the frame brought in, unreadable text grown, words over words moved
    apart; a beat with nothing wrong writes nothing."""
    import pocket_lecture as pl
    from manim import FadeIn, FadeOut, tempconfig

    log, frames = tmp_path / "checks.jsonl", tmp_path / "frames"
    monkeypatch.setenv("PANIM_CHECK_LOG", str(log))
    monkeypatch.setenv("PANIM_CHECK_FRAMES", str(frames))
    monkeypatch.setenv("PANIM_VOICE", "silent")
    seen = {}

    class Probe(pl.MapLecture):
        def construct(self):
            self.board()
            a = pl.T("tiny words here", 9, fine=True).move_to([0, 1, 0])
            b = pl.T("running off the edge of the frame", 30).move_to([7.5, 0, 0])
            c = pl.T("first label", 24).move_to([-3, -1, 0])
            d = pl.T("second label", 24).move_to([-2.8, -1.05, 0])
            self.beat("A beat with problems.", FadeIn(a), FadeIn(b), FadeIn(c), FadeIn(d))
            seen.update(edge=b.get_right()[0], size=a.font_size, apart=pl._overlap(pl._bbox(c), pl._bbox(d)))
            self.beat("A clean beat.", FadeOut(a), FadeOut(b), FadeOut(c), FadeOut(d))

    with tempconfig({"dry_run": True, "media_dir": str(tmp_path), "disable_caching": True}):
        Probe().render()
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["say"] == "A beat with problems."
    fixed = " ".join(rows[0]["fixed"])
    assert "off the frame" in fixed and "grown to 13pt" in fixed and "moved apart" in fixed
    assert seen["edge"] <= pl.config.frame_width / 2 and seen["size"] >= 12.9 and seen["apart"] == 0


def test_a_diagram_is_built_as_its_parts_are_spoken_of():
    script = {"title": "T", "style": "chalkboard", "auto_visuals": False, "place_figures": False, "chapters": [
        {"title": "A", "map": False, "beats": [
            {"say": "Society had three orders, starting with the clergy.", "do": [
                {"op": "diagram", "id": "d", "kind": "hub", "nodes": [
                    {"id": "s", "label": "Society"}, {"id": "c", "label": "Clergy"},
                    {"id": "n", "label": "Nobility"}, {"id": "p", "label": "Peasants"}]}]},
            {"say": "Then came the nobility, who fought.", "do": []},
            {"say": "And the peasants worked the land.", "do": []}]}]}
    errors, warnings = cl.lint(script)
    assert not errors
    beats = script["chapters"][0]["beats"]
    assert beats[0]["do"][0]["show"] == ["s", "c"]
    assert beats[1]["do"] == [{"op": "reveal", "diagram": "d", "nodes": ["n"]}]
    assert beats[2]["do"] == [{"op": "reveal", "diagram": "d", "nodes": ["p"]}]
    assert any("built as it is spoken of" in w for w in warnings)


def test_a_spotlight_quiets_the_rest_and_moves_in_on_a_big_diagram():
    import pocket_lecture as pl

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    ids = [f"n{k}" for k in range(8)]
    scene.diagram("d", "flow", [{"id": i, "label": i} for i in ids], [[a, b] for a, b in zip(ids, ids[1:])])
    scene.add(*scene.stage_items, *scene.stage_extra)
    assert scene.spotlight("d", "n4") is not None
    d = scene.diagrams["d"]
    assert len(d["veils"]) == 7 and d.get("pushed")                 # every other part veiled; moved in on it
    small = [f"m{k}" for k in range(4)]
    scene.diagram("e", "flow", [{"id": i, "label": i} for i in small], [[a, b] for a, b in zip(small, small[1:])])
    scene.spotlight("e", "m1")
    assert len(scene.diagrams["e"]["veils"]) == 3 and not scene.diagrams["e"].get("pushed")
    scene.reveal_nodes("e", [])
    assert scene.diagrams["e"]["veils"] == []                       # the focus moved on: the veils lift


def test_diagrams_carry_meaning():
    """Nodes look like what they are (a person, a place, an event), arrows like what they mean (gives, owes, rules)
    with a key under the diagram, and ranks stand as a pyramid."""
    import pocket_lecture as pl

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    nodes = [{"id": "l", "label": "Lord", "kind": "person"}, {"id": "v", "label": "Vassal", "kind": "person"},
             {"id": "o", "label": "Oath", "kind": "event"}, {"id": "m", "label": "Manor", "kind": "place"}]
    edges = [["l", "v", "grants land", "gives"], ["v", "o", "swears", "owes"], ["o", "m", "binds", "rules"]]
    scene.diagram("d", "flow", nodes, edges)
    built = scene.diagrams["d"]
    assert built["nodes"]["o"][1].__class__.__name__ == "Rectangle"          # the event's bar
    assert pl.edge_look("owes") == "dashed" and pl.edge_look("rules") == "bold" and pl.edge_look("") == "solid"
    legend = pl.edge_legend(["gives", "owes", "rules", "dashed"])
    assert legend is not None and len(legend) == 3
    scene.diagram("p", "pyramid", [{"id": k, "label": k.title(), "items": ["x"]} for k in ("king", "nobles", "peasants")])
    bands = [scene.diagrams["p"]["nodes"][k][0] for k in ("king", "nobles", "peasants")]
    assert bands[0].width < bands[1].width < bands[2].width                     # narrow at the top


def test_no_words_are_set_below_the_type_scale_but_credits():
    import pocket_lecture as pl

    assert pl.T("a label", 11).font_size == pytest.approx(pl.MIN_TEXT, abs=0.5)
    assert pl.T("Photo: Wikimedia", 10, fine=True).font_size == pytest.approx(10, abs=0.5)


def test_every_style_marks_things_in_colours_that_read_on_its_background():
    import pocket_lecture as pl

    try:
        for name in pl.THEMES:
            pl.use_style(name)
            for key in pl.CONTRAST_ROLES:
                assert pl.contrast(getattr(pl.P, f"role_{key}"), pl.P.BG) >= 3.0, (name, key)
        pl.use_style("cardboard")
        assert any(f.startswith("highlight") for f in pl.CONTRAST_FIXED)   # gold on kraft paper is shaded darker
    finally:
        pl.use_style("atlas")


def test_the_caption_colours_the_words_that_are_on_screen():
    import pocket_lecture as pl
    from manim import FadeIn

    class Probe(pl.MapLecture):
        def construct(self):
            pass

    scene = Probe()
    scene.setup()
    scene.board()
    scene.add(pl.T("Mughal Empire", 24).move_to([2, 1, 0]))
    scene._coming = (FadeIn(pl.T("Akbar", 24)),)
    cap = scene.caption("Akbar ruled the Mughal Empire for almost fifty years, and his court was the richest.")
    text = cap[-1]
    assert sorted(text._panim_terms) == ["Akbar", "Mughal Empire"]
    ink = [g.get_fill_color().to_hex().upper() for g in text.submobjects]
    assert ink[0] != ink[6] and ink[0] == ink[16]                   # "Akbar" and "Mughal" coloured, "ruled" not
    plain = scene.caption("Nothing on screen is said here at all.")[-1]
    assert not getattr(plain, "_panim_terms", None)
