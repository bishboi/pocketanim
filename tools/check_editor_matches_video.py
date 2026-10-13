"""The editor's player against the video, beat by beat, for a lecture script.

The editor and the phone play the exported program; the download is Manim's render. Where the two disagree, a
student sees something in the editor the video does not have: a part left behind over the next scene, a highlight
that never came, a picture that came apart when it moved aside. This renders the lecture both ways and compares the
end of every beat.

    python -m tools.check_editor_matches_video <script.json> <out_dir> [build_workers]

It renders the lecture with Manim, saving the frame and scene time at the end of each beat; exports it as the app
does (export_scene.py, chapters built side by side); renders the program at those times, taking the closest frame
within 2.5 s (a sim's phase, a small timing offset, is not a fault: a thing left behind or missing persists); and
writes diff-<beat>.png (video left, program right) for each beat that still differs, with a report. REUSE=1 keeps
an earlier render and export in out_dir.
"""
import json, os, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable
script, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
workers = sys.argv[3] if len(sys.argv) > 3 else "3"
out.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "PYTHONPATH": str(REPO / "harness/lecture"), "PANIM_VOICE": "silent", "PANIM_IMAGE_FAKE": "1",
       "PANIM_IMAGE_CACHE": str(out.parent / "imgcache"), "OPENROUTER_API_KEY": "test",
       "PANIM_MANIM_CHECK": os.environ.get("PANIM_MANIM_CHECK", "off"), "PANIM_BUILD_WORKERS": workers}

sys.path.insert(0, str(REPO / "harness/lecture"))
os.environ.update(env)
import compile_lecture as cl  # noqa: E402

code = cl.compile_script(json.loads(script.read_text()))
(out / "scene.py").write_text(code)
shots = out / "shots"
shots.mkdir(exist_ok=True)
(out / "shots.py").write_text(code + f'''

class Shots(GeneratedScene):
    def _shot(self, label):
        from PIL import Image as _I
        n = getattr(self, "_n", 0) + 1
        self._n = n
        _I.fromarray(self.renderer.get_frame()).convert("RGB").save({str(shots)!r} + f"/{{n:03d}}.png")
        with open({str(shots)!r} + "/times.txt", "a") as f:
            f.write(f"{{n}} {{self.renderer.time:.4f}} {{label}}\\n")

    def beat(self, text, *a, **kw):
        out = super().beat(text, *a, **kw)
        self._shot(str(text)[:50].replace(chr(10), " "))
        return out

    def free(self, key, text, *a, **kw):
        out = super().free(key, text, *a, **kw)
        self._shot(str(text)[:50].replace(chr(10), " "))
        return out
''')
reuse = os.environ.get("REUSE") and (out / "build").is_dir() and (shots / "times.txt").stat().st_size > 0
if not reuse:
    (shots / "times.txt").write_text("")
video = None if reuse else subprocess.Popen([PY, "-m", "manim", "-ql", "--disable_caching", "--media_dir", str(out / "media"),
                          str(out / "shots.py"), "Shots"], cwd=out, env=env, stdout=open(out / "manim.log", "w"),
                         stderr=subprocess.STDOUT)
build = out / "build"
exp = subprocess.CompletedProcess([], 0, '{"tier": "reused"}', "") if reuse else subprocess.run([PY, str(REPO / "harness/scripts/export_scene.py"), str(out / "scene.py"), "GeneratedScene",
                      str(build)], cwd=out, env=env, capture_output=True, text=True)
(out / "export.err").write_text(exp.stderr)
result = json.loads(exp.stdout.strip().splitlines()[-1])
if video is not None:
    video.wait()
if video is not None and video.returncode:
    print("manim failed", (out / "manim.log").read_text()[-1500:])
    sys.exit(1)

probe = f'''
import sys, os, json
sys.path.insert(0, {str(REPO)!r})
os.chdir({str(build)!r})
import numpy as np
from PIL import Image, ImageFilter
from dsl.interpret import load_program
from dsl.export_dsl import PROGRAM_FPS
from exporter.reference_render import render_frame
ir = load_program("dsl/generated/GeneratedScene.panim")
n = len(ir.records)
rows = []
for line in open({str(shots / "times.txt")!r}):
    k, t, label = line.split(" ", 2)
    f0 = min(n - 1, max(0, int(round(float(t) * PROGRAM_FPS)) - 1))
    vid = Image.open({str(shots)!r} + f"/{{int(k):03d}}.png").convert("RGB").resize((640, 360))
    b = np.asarray(vid.filter(ImageFilter.BoxBlur(2)).resize((320, 180)), dtype=int)
    best = None
    span = int(2.5 * PROGRAM_FPS)
    for f in sorted(range(max(0, f0 - span), min(n, f0 + span + 1), 5), key=lambda x: abs(x - f0)):
        a = np.asarray(Image.fromarray(render_frame(ir, f, 320, 180)).convert("RGB").filter(ImageFilter.BoxBlur(1)),
                       dtype=int)
        bad = float((np.abs(a - b).max(axis=2) > 60).mean())
        if best is None or bad < best[0]:
            best = (bad, f)
        if bad < 0.002:
            break
    bad, f = best
    prog = Image.fromarray(render_frame(ir, f, 640, 360)).convert("RGB")
    rows.append((int(k), float(t), f, bad, label.strip()))
    if bad > 0.004:
        s = Image.new("RGB", (1280, 360)); s.paste(vid, (0, 0)); s.paste(prog, (640, 0))
        s.save({str(out)!r} + f"/diff-{{int(k):03d}}.png")
print(json.dumps({{"frames": n, "rows": rows}}))
'''
run = subprocess.run([PY, "-c", probe], capture_output=True, text=True)
if run.returncode:
    print(run.stderr[-2000:])
    sys.exit(1)
report = json.loads(run.stdout.strip().splitlines()[-1])
bad = [r for r in report["rows"] if r[3] > 0.004]
print(f"{script.name}: tier {result.get('tier')} frames {report['frames']} beats {len(report['rows'])} "
      f"differing {len(bad)}")
for k, t, f, b, label in bad:
    print(f"  beat {k:3d} t={t:7.2f} frame {f:5d} (at {f / 30 - t:+.2f}s) differs {b * 100:5.2f}%  {label}")
