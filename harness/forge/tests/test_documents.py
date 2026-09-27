"""Lecture PDFs: Datalab's protocol (against a mock), the offline reader, and figures in a compiled lecture."""

from __future__ import annotations

import importlib
import json
import tempfile
import sys
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest

from forge.util import LECTURE

sys.path.insert(0, str(LECTURE / "tests"))
import mock_datalab  # noqa: E402


def _pdf(path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.1, 0.9, "Uttar Pradesh grows more sugarcane than any other state.", size=10)
        ax = fig.add_axes([0.2, 0.4, 0.6, 0.4])
        ax.imshow(np.random.default_rng(0).integers(0, 255, (300, 480, 3)).astype("uint8"))
        ax.axis("off")
        fig.text(0.2, 0.35, "Figure 1: Sugarcane districts", size=10)
        pdf.savefig(fig)
    return path


@pytest.fixture
def datalab(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), mock_datalab.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    mock_datalab.SEEN.update(posts=[], polls=0)
    monkeypatch.setenv("DATALAB_API_KEY", "test-key")
    monkeypatch.setenv("DATALAB_HOST", f"http://127.0.0.1:{server.server_port}")
    import pdf_source

    importlib.reload(pdf_source)
    monkeypatch.setattr(pdf_source, "CACHE", Path(tempfile.mkdtemp()))
    yield pdf_source
    server.shutdown()
    monkeypatch.delenv("DATALAB_HOST")
    importlib.reload(pdf_source)


def test_datalab_protocol(datalab, tmp_path):
    manifest = datalab.convert(_pdf(tmp_path / "a.pdf"), tmp_path / "out")
    post = mock_datalab.SEEN["posts"][0]
    assert post == {"key": "test-key", "path": "/api/v1/convert", "has_file": True, "format": True}
    assert mock_datalab.SEEN["polls"] == 2                      # one "processing", then complete
    assert manifest["source"] == "datalab" and manifest["pages"] == 2
    [figure] = manifest["figures"]
    assert figure["caption"] == "Figure 1: The sugarcane belt of western Uttar Pradesh" and figure["page"] == 1
    assert Path(figure["file"]).is_file()
    text = Path(manifest["markdown"]).read_text()
    assert "[FIGURE fig1: Figure 1: The sugarcane belt" in text and "![" not in text


def test_offline_reader(tmp_path, monkeypatch):
    monkeypatch.delenv("DATALAB_API_KEY", raising=False)
    import pdf_source

    monkeypatch.setattr(pdf_source, "CACHE", tmp_path / "cache")
    manifest = pdf_source.convert(_pdf(tmp_path / "b.pdf"), tmp_path / "out")
    assert manifest["source"] == "pypdf" and manifest["note"]
    assert [f["caption"] for f in manifest["figures"]] == ["Figure 1: Sugarcane districts"]
    assert "sugarcane" in Path(manifest["markdown"]).read_text()


def test_figure_and_icon_ops_compile(tmp_path):
    import subprocess

    import icons

    if not icons.available():
        pytest.skip("icon sets not downloaded (harness/scripts/fetch_icons.py)")

    image = tmp_path / "f.png"
    from PIL import Image

    Image.new("RGB", (300, 200), "white").save(image)
    script = {"title": "T", "style": "vox", "region": {"state": "Uttar Pradesh", "country": "India"},
              "figures": {"fig1": {"file": str(image), "caption": "Figure 1"}},
              "chapters": [{"title": "A", "narration": "x", "beats": [
                  {"say": "one two three four five six seven eight", "do": [
                      {"op": "figure", "id": "fig1"}, {"op": "icon", "name": "sugarcane", "places": ["Meerut"]},
                      {"op": "icon", "name": "wheat", "label": "Rabi"}]},
                  {"say": "one two three four five six seven eight", "do": [{"op": "figure", "id": "fig9"}]}]}]}
    out = subprocess.run([sys.executable, str(LECTURE / "compile_lecture.py"), "-", "--json"],
                         input=json.dumps(script), capture_output=True, text=True)
    errors = json.loads(out.stdout.strip().splitlines()[-1])["errors"]
    assert errors == ["chapter 1 beat 2: no figure 'fig9'; the figures are: fig1"]
    del script["chapters"][0]["beats"][1]
    out = subprocess.run([sys.executable, str(LECTURE / "compile_lecture.py"), "-", "--json"],
                         input=json.dumps(script), capture_output=True, text=True)
    source = json.loads(out.stdout.strip().splitlines()[-1])["source"]
    assert "self.figure(" in source and 'self.icon("sugarcane", ["Meerut"]' in source
    assert 'self.panel_icon("wheat", label="Rabi")' in source and "self.credits(" in source
