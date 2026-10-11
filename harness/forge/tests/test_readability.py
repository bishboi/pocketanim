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
