"""The stage: photos (Wikimedia Commons, reusable licences only), illustrations, and the map only when needed."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import threading
from http.server import HTTPServer

import pytest

from forge.util import LECTURE

sys.path.insert(0, str(LECTURE / "tests"))
import mock_commons  # noqa: E402


@pytest.fixture
def commons(monkeypatch, tmp_path):
    server = HTTPServer(("127.0.0.1", 0), mock_commons.Handler)
    mock_commons.PORT["value"] = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("COMMONS_API", f"http://127.0.0.1:{server.server_port}/w/api.php")
    monkeypatch.setenv("PANIM_IMAGE_CACHE", str(tmp_path / "images"))
    import images

    importlib.reload(images)
    yield images
    server.shutdown()


def test_only_reusable_photos_and_their_credits(commons):
    rows = commons.search("sugarcane")
    assert [r["id"] for r in rows] == ["File:Sugarcane field in Uttar Pradesh.jpg"]     # "All rights reserved" skipped
    assert rows[0]["credit"] == "A. Farmer, CC BY-SA 4.0, via Wikimedia Commons"
    got = commons.fetch(query="wheat")
    assert got and got["license"] == "CC0" and __import__("pathlib").Path(got["file"]).stat().st_size > 1000
    assert "Wheat harvest India (B. Grower, CC0" in commons.credit([got])


def _compile(script, env):
    out = subprocess.run([sys.executable, str(LECTURE / "compile_lecture.py"), "-", "--json"], input=json.dumps(script),
                         capture_output=True, text=True, env=env)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_map_only_when_a_beat_points_at_it(commons):
    import icons
    import os

    if not icons.available():
        pytest.skip("icon sets not downloaded")
    beat = lambda say, *ops: {"say": say, "do": list(ops)}  # noqa: E731
    script = {"title": "T", "style": "vox", "region": {"state": "Uttar Pradesh", "country": "India"}, "chapters": [
        {"title": "Crops", "narration": "One.", "beats": [
            beat("Sugarcane feeds the sugar mills of the west.", {"op": "photo", "query": "sugarcane"}),
            beat("In winter the farmers sow wheat across the plain."),
            beat("Tigers and elephants live in the Terai forests.")]},
        {"title": "Where", "narration": "Two.", "beats": [
            beat("The wheat harvest comes every April.", {"op": "photo", "query": "wheat"}),
            beat("The sugarcane belt lies around Meerut.", {"op": "marker", "place": "Meerut"}),
            beat("Tractors changed farming after the green revolution.")]}]}
    result = _compile(script, dict(os.environ))
    assert result["errors"] == []
    source = result["source"]
    first, second = source.split("# 02")
    assert "show_map" not in first and "add_panel" in first            # no map where no beat needs one
    assert "stage_image" in first and "self.illustration(" in first     # a photo, then pictures from the words
    assert "show_map" in second
    assert second.index("clear_stage") < second.index("self.mark(")    # the photo leaves when the map is needed
    assert second.count("self.illustration(") == 1                      # the tractor beat covers the map again
    assert "Photos: " in source.split("self.credits(")[1]
