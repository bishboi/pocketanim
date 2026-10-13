"""Figures that fail while the video is drawn (they passed the compile's check): the build names each failed block
by its figure and beat, the Manim model is sent them with the build's reasons after the build (manimcoder.ts
repairBuiltManim, app/api/export), and the lecture built again with the mended blocks draws them."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from forge.util import REPO

sys.path.insert(0, str(REPO / "harness" / "lecture"))

import compile_lecture as cl  # noqa: E402

APP = REPO / "harness" / "app"
BUILD = "box = Square(side_length=1.2, color=INK)\nself.play(Create(box))"


def _export(scene, out):
    env = {**os.environ, "PANIM_VOICE": "silent", "PANIM_BUILD_WORKERS": "2"}
    done = subprocess.run([sys.executable, str(REPO / "harness" / "scripts" / "export_scene.py"), str(scene),
                           "GeneratedScene", str(out)], capture_output=True, text=True, timeout=900, env=env)
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result["tier"] == 1, done.stderr[-1500:]
    return result


def test_figures_that_fail_in_the_build_are_mended_after_it(tmp_path, monkeypatch):
    tsc = APP / "node_modules" / ".bin" / "tsc"
    if not tsc.exists() or not shutil.which("node"):
        pytest.skip("no TypeScript compiler")
    monkeypatch.setenv("PANIM_MANIM_CHECK", "off")      # as a block the check let through
    script = {"title": "Free", "style": "chalkboard", "teaching_rules": False, "auto_visuals": False,
              "place_figures": False, "chapters": [{"title": "One", "map": False, "beats": [
                  {"say": "We draw a box.", "do": [{"op": "manim", "id": "fig", "code": "def make():\n"
                                                    "    g = Square()\n    return g\nself.play(Create(make()))"}]},
                  {"say": "And it pulses.", "do": [{"op": "manim", "id": "fig", "code": "self.play(Indicate(g))"}]},
                  {"say": "A ring.", "do": [{"op": "manim", "id": "ring", "code": "self.play(Create(Circle(width=2)))"}]},
              ]}]}
    source = cl.compile_script(script)
    first = tmp_path / "first.py"
    first.write_text(source)
    skipped = _export(first, tmp_path / "b1").get("skipped") or []
    # Each failure names its figure and the beat of it; an error deep in Manim also names the block's own line.
    assert any(s.startswith("manim block 'fig' beat 2: NameError") for s in skipped), skipped
    ring = next(s for s in skipped if s.startswith("manim block 'ring' beat 1: TypeError"))
    assert "called from <ring>:1" in ring, ring

    out = tmp_path / "ts"
    built = subprocess.run([str(tsc), "lib/manimcoder.ts", "--outDir", str(out), "--module", "commonjs", "--target",
                            "es2022", "--skipLibCheck", "--esModuleInterop"], cwd=APP, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    # The Manim model, as a stand-in: what it is told, and the blocks it answers with.
    mended = {"fig": [BUILD, "self.play(Indicate(box))"], "ring": ["self.play(Create(Circle(radius=1)))"]}
    node = f"""
const m = require({json.dumps(str(out / 'manimcoder.js'))});
const asked = [];
globalThis.fetch = async (url, init) => {{
  const text = JSON.parse(init.body).messages[1].content[0].text;
  asked.push(text);
  const id = /The figure's id: (\\w+)/.exec(text)[1];
  const blocks = {json.dumps(mended)}[id];
  return {{ ok: true, json: async () => ({{ choices: [{{ message: {{ content: JSON.stringify({{ blocks }}) }} }}],
    usage: {{ cost: 0.01 }} }}) }};
}};
const source = require('fs').readFileSync({json.dumps(str(first))}, 'utf8');
let usd = 0;
m.repairBuiltManim(source, {json.dumps(skipped)}, {{ key: 'k', model: 'x/y', onCost: (c) => {{ usd += c; }} }})
  .then((r) => console.log(JSON.stringify({{ ...r, asked, usd, calls: m.freeCalls(r.source).length }})));
"""
    done = subprocess.run(["node", "-e", node], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    assert sorted(result["fixed"]) == ["fig", "ring"] and result["usd"] == pytest.approx(0.02)
    told = next(a for a in result["asked"] if "fig" in a.split("The figure's id: ")[1][:4])
    assert "FAILED when the whole video was drawn" in told and "Beat 2's block: NameError" in told
    assert result["calls"] == 3
    second = tmp_path / "second.py"
    second.write_text(result["source"])
    assert "Circle(radius=1)" in result["source"] and "Circle(width=2)" not in result["source"]
    assert not _export(second, tmp_path / "b2").get("skipped")
