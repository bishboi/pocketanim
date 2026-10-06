"""Builds at once, one Manim cache (scripts/export_scene.py manim_cache): text and formulas drawn by several
processes into the same folder at the same moment. Before nolatex made these writes safe, most of the processes
failed: "error while writing to output stream" (two text2svg into one file), FileNotFoundError (Manim's scratch
copy "<name>_.svg" deleted by another build) and "no element found" (Text rewriting its cached SVG in place)."""

from __future__ import annotations

import os
import subprocess
import sys

from forge.util import REPO

DRAW = """
import os, sys
sys.path.insert(0, {scripts!r}); sys.path.insert(0, {lecture!r})
from export_scene import share_caches
share_caches()
import nolatex
nolatex.install()
from manim import MarkupText, MathTex, Text
for i in range(12):
    Text(f"Horizontal balance gives T one sine theta equals fifty {{i}}")
    MarkupText(f"<b>Tension</b> {{i}}")
    MathTex(rf"T_1 \\sin\\theta = 50 + {{i}}")
print("drawn")
"""


def test_parallel_builds_share_the_cache_without_breaking_each_other(tmp_path):
    script = tmp_path / "draw.py"
    script.write_text(DRAW.format(scripts=str(REPO / "harness" / "scripts"), lecture=str(REPO / "harness" / "lecture")))
    env = {**os.environ, "PANIM_MANIM_CACHE": str(tmp_path / "cache")}
    runs = [subprocess.Popen([sys.executable, str(script)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True) for _ in range(5)]
    for run in runs:
        out, err = run.communicate(timeout=600)
        assert run.returncode == 0 and "drawn" in out, err[-1500:]
    files = [p for p in (tmp_path / "cache").rglob("*") if p.is_file() and p.name != ".panim.lock"]
    assert files and not [p for p in files if p.stat().st_size == 0]
    assert not [p for p in files if p.name.endswith(".tmp") or ".svg." in p.name]   # no scratch left behind
