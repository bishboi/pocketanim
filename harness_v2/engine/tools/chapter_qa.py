"""Build one chapter as the app does and judge it: what the QA loop runs on every chapter of its test set.

    .venv/bin/python harness_v2/engine/tools/chapter_qa.py <script.json|scene.py> <out_dir>
        [--voice fake|real] [--pictures fake|real] [--every 2] [--quality l]

A beat script is compiled by the engine's compiler (compile_motion.py, as the Scenes tab compiles it); a scene is
taken as it is. It is then built as the Scenes tab builds a chapter (no title slide, no closing fade, so the credits come over
the last picture), spoken (`fake`: sync_probe's stand-in voice, whose word times are exact, free and offline; `real`:
the voice PANIM_TTS names, through prespeak.py, cached in <out_dir>/audio), rendered with Manim, exported for the
phone and the web player (export_scene.py), and checked:

- compile: errors (fail) and warnings;
- pictures left out by the engine ("skipped" in the beat log: fail);
- leftovers: anything of a picture that has left the stage still drawn after a line or under the credits
  (MotionLecture._m_leftovers, "leftover" in the beat log: fail);
- the export: tier 1 with no blockers (else fail);
- the players against the video: a frame every `--every` seconds drawn from the exported program by the reference
  renderer and compared with Manim's (phone_check.py), the two clocks lined up by where each line's voice starts
  on each (MotionLecture's "voice" log, the export's "clips"); a frame over its limit fails;
- timing (sync_probe.py): animations on their words, readable in time, still seconds a minute (warnings);
- the engine's visual check (PANIM_CHECK_LOG: small text, words over words: warnings).

Writes <out_dir>/report.json ({"ok", "fail": [...], "warn": [...], ...}) and, when frames differ, <out_dir>/sheet.png
(each differing frame: the players' left, Manim's right). The last line of stdout is the report's summary as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ENGINE = TOOLS.parent
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(TOOLS))

ANCHORS_ON_TIME = 0.8          # share of anchored animations on their words below which timing is a warning
STILL_PER_MINUTE = 8.0         # still seconds a minute of speech above which it is a warning


def _run(args: list, cwd: Path, env: dict, log: Path, timeout: int = 3600) -> subprocess.CompletedProcess:
    r = subprocess.run([str(a) for a in args], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    log.write_text(f"$ {' '.join(map(str, args))}\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}")
    return r


def _last_json(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {}


def _chapter_source(source: str) -> str:
    """As the Scenes tab renders a chapter (lib/scenes.ts): no title slide, no closing fade."""
    return "\n".join(l for l in source.split("\n") if not re.search(r"self\.(title_slide|outro_fade)\(", l)) + "\n"


def _sheet(pairs: list, out: Path) -> None:
    from PIL import Image, ImageDraw

    w, h = 480, 270
    sheet = Image.new("RGB", (w * 2, h * len(pairs)), "white")
    for k, (t, phone, manim) in enumerate(pairs):
        for col, path in enumerate((phone, manim)):
            try:
                im = Image.open(path).convert("RGB").resize((w, h))
            except OSError:
                continue
            ImageDraw.Draw(im).text((6, 6), f"{t:.1f}s {'players' if col == 0 else 'manim'}", fill="red")
            sheet.paste(im, (col * w, k * h))
    sheet.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--voice", choices=("fake", "real"), default="fake")
    ap.add_argument("--pictures", choices=("fake", "real"), default="fake")
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--quality", default="l")
    # The players' programs run at 30 frames a second; the video at the same rate rounds each play to the same whole
    # frames (at 15, a chapter's clocks drifted a second apart, and a picture's idle drift with them).
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()
    src, out = Path(args.script).resolve(), Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    started = time.time()
    report: dict = {"script": str(src), "voice": args.voice, "pictures": args.pictures, "fail": [], "warn": []}
    env = {**os.environ, "PYTHONPATH": str(ENGINE)}
    if args.pictures == "fake":
        env.update(PANIM_IMAGE_FAKE="1", PANIM_IMAGE_MODEL=env.get("PANIM_IMAGE_MODEL") or "stand-in")
    env.setdefault("PANIM_IMAGE_CACHE", str(out / "images"))

    def finish() -> int:
        report["ok"] = not report["fail"]
        report["seconds"] = round(time.time() - started, 1)
        (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
        print(json.dumps({k: report.get(k) for k in ("ok", "fail", "warn", "seconds")}, ensure_ascii=False))
        return 0 if report["ok"] else 1

    # ---- compile
    if src.suffix == ".json":
        r = _run([py, ENGINE / "compile_motion.py", src, "--json"], out, {**env, "PANIM_VOICE": "silent"},
                 out / "compile.log", 900)
        made = _last_json(r.stdout)
        report["compile"] = {"errors": made.get("errors") or [], "warnings": made.get("warnings") or []}
        if not made.get("source"):
            report["fail"].append(f"compile: {(made.get('errors') or [r.stderr[-400:]])[:3]}")
            return finish()
        report["fail"] += [f"compile error: {e}" for e in report["compile"]["errors"][:5]]
        report["warn"] += [f"compile warning: {w}" for w in report["compile"]["warnings"][:5]]
        source = made["source"]
    else:
        source = src.read_text()
    source = _chapter_source(source)
    scene = out / "scene.py"
    scene.write_text(source)

    # ---- voice
    if args.voice == "fake":
        import sync_probe

        sync_probe.fake_voice(source)                       # sets PANIM_TTS, PANIM_VOICE, PANIM_AUDIO_DIR here
        env.update({k: os.environ[k] for k in ("PANIM_TTS", "PANIM_VOICE", "ELEVENLABS_API_KEY", "PANIM_AUDIO_DIR",
                                                "PANIM_VOICE_DIRECTOR")})
    else:
        env.setdefault("PANIM_AUDIO_DIR", str(out / "audio"))
        r = _run([py, TOOLS / "prespeak.py", scene], out, env, out / "voice.log", 1800)
        spoke = _last_json(r.stdout)
        if not spoke.get("ok"):
            report["fail"].append(f"voice: {spoke.get('error') or r.stderr[-400:]}")
            return finish()

    # ---- render (Manim) and export (the players), side by side
    beats, checks = out / "beats.jsonl", out / "checks.jsonl"
    for f in (beats, checks):
        f.unlink(missing_ok=True)
    shutil.rmtree(out / "media", ignore_errors=True)
    shutil.rmtree(out / "export", ignore_errors=True)
    renv = {**env, "PANIM_BEAT_LOG": str(beats), "PANIM_CHECK_LOG": str(checks)}
    render = subprocess.Popen([py, "-m", "manim", "render", f"-q{args.quality}", "--fps", str(args.fps),
                               "--disable_caching", "--progress_bar",
                               "none", "-v", "WARNING", str(scene), "GeneratedScene", "--media_dir", str(out / "media")],
                              cwd=out, env=renv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    r = _run([py, TOOLS / "export_scene.py", scene, "GeneratedScene", out / "export"], out, env, out / "export.log",
             3600)
    rout, rerr = render.communicate(timeout=3600)
    (out / "render.log").write_text(f"--- stdout\n{rout}\n--- stderr\n{rerr}")
    exported = _last_json(r.stdout)
    report["export"] = {"tier": exported.get("tier"), "blockers": exported.get("blockers"),
                        "error": exported.get("error")}
    if exported.get("tier") != 1 or exported.get("blockers"):
        report["fail"].append(f"export: tier {exported.get('tier')}, blockers {exported.get('blockers')}, "
                              f"{exported.get('error') or ''}".strip(", "))
    videos = sorted((out / "media").rglob("GeneratedScene.mp4"))
    if render.returncode or not videos:
        report["fail"].append(f"render: exit {render.returncode}: {rerr.strip()[-400:]}")
        return finish()
    video = videos[-1]

    # ---- the engine's own logs
    logged = [json.loads(l) for l in beats.read_text().splitlines() if l.strip()] if beats.exists() else []
    for row in logged:
        if row.get("kind") == "skipped":
            report["fail"].append(f"picture skipped: {row.get('error') or row.get('what')}")
        elif row.get("kind") == "leftover":
            report["fail"].append(f"leftover at {row['start']:.1f}s ({row.get('where')}): {row.get('count')} piece(s) "
                                  f"of earlier pictures still drawn {row.get('what') or ''} after {row.get('line')!r}")
    if checks.exists():
        for l in checks.read_text().splitlines():
            try:
                row = json.loads(l)
            except ValueError:
                continue
            for issue in row.get("issues") or []:
                report["warn"].append(f"visual check: {issue}")

    # ---- the players against the video, their clocks lined up by where each line's voice starts on each (the
    # program's verbs run whole frames, so over a chapter its clock drifts from the video's; the players place the
    # voice on the program's clock, so on a phone voice and picture keep together)
    seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(video)], capture_output=True, text=True).stdout.strip() or 0)
    clips: dict = {}
    for at, path in exported.get("clips") or []:
        clips.setdefault(str(Path(path).resolve()), []).append(float(at))
    pairs = []
    for row in logged:
        if row.get("kind") == "voice":
            heard = clips.get(str(Path(row["wav"]).resolve()))
            if heard:
                pairs.append((float(row["at"]), heard.pop(0)))
    pairs.sort()
    report["clock"] = {"lines": len(pairs), "drift": round(max((abs(p - m) for m, p in pairs), default=0.0), 3)}

    def program(t: float) -> float:
        # Between two lines' voices, the video's time is spread over the program's (the drift of the plays between
        # them shared out, not all of it at the next line's start); before the first and after the last, offset.
        if not pairs:
            return t
        for (m0, p0), (m1, p1) in zip(pairs, pairs[1:]):
            if m0 <= t <= m1 and m1 - m0 > 1e-6:
                return p0 + (t - m0) * (p1 - p0) / (m1 - m0)
        m, p = pairs[0] if t < pairs[0][0] else pairs[-1]
        return max(0.0, p + (t - m))

    times, t = [], min(1.0, args.every)
    while t < seconds - 0.3:
        times.append(round(t, 2))
        t += args.every
    times.append(round(max(0.0, seconds - 0.4), 2))
    asked = [f"{t}@{round(program(t), 3)}" for t in times]
    # Lined up to within a frame or two (the program loses its frames at particular plays, not evenly): the closest
    # of the program's frames three either side is judged.
    r = _run([py, TOOLS / "phone_check.py", out / "export", "GeneratedScene", video, out / "frames", *asked,
              "--slack", "3"], out, env,
             out / "phone.log", 3600)
    compared = _last_json(r.stdout)
    frames = compared.get("frames") or []
    bad = [f for f in frames if f.get("ok") is False]
    report["players"] = {"frames": len(frames), "differ": [[f["t"], round(f["mean"], 1), round(f["differ"], 3)]
                                                            for f in bad]}
    if not frames:
        report["fail"].append(f"players: no frames compared: {r.stderr[-300:]}")
    # A difference that is gone half a second either side is a moment of a move played a little apart (a picture
    # fading in a few frames later): a warning. One still there is a picture the players show and the video does
    # not, or the other way about (a leftover, a picture that vanished): a failure.
    lasting = set()
    if bad:
        near = [f"{round(f['t'] + d, 2)}@{round(program(f['t'] + d), 3)}" for f in bad for d in (-0.5, 0.5)
                if 0 <= f["t"] + d < seconds]
        r2 = _run([py, TOOLS / "phone_check.py", out / "export", "GeneratedScene", video, out / "frames-near", *near,
                   "--slack", "3"], out, env, out / "phone-near.log", 3600)
        around = {round(g["t"], 2): g.get("ok") for g in _last_json(r2.stdout).get("frames") or []}
        for f in bad:
            if any(around.get(round(f["t"] + d, 2)) is False for d in (-0.5, 0.5)):
                lasting.add(f["t"])
    for f in bad:
        what = (f"players differ from the video at {f['t']:.1f}s (mean {f['mean']:.1f}, "
                f"{100 * f['differ']:.0f}% of pixels)")
        if f["t"] in lasting:
            report["fail"].append(what)
        else:
            report["warn"].append(f"{what}, only for a moment")
    if bad:
        _sheet([(f["t"], f["phone"], f["manim"]) for f in bad[:12]], out / "sheet.png")
        report["sheet"] = str(out / "sheet.png")

    # ---- timing
    r = _run([py, TOOLS / "sync_probe.py", scene, "--json"], out, env, out / "sync.log", 1800)
    sync = _last_json(r.stdout)
    if sync:
        anchors = sync.get("anchors") or {}
        report["sync"] = {"anchors": anchors.get("count"), "on_time": anchors.get("on_time"),
                          "late": anchors.get("late"), "still_per_minute": (sync.get("still") or {}).get("per_minute"),
                          "worst": (anchors.get("worst") or [])[:3]}
        if anchors.get("count") and (anchors.get("on_time") or 0) / anchors["count"] < ANCHORS_ON_TIME:
            report["warn"].append(f"timing: {anchors.get('on_time')} of {anchors['count']} anchored animations on "
                                  f"their words")
        still = (sync.get("still") or {}).get("per_minute")
        if still is not None and still > STILL_PER_MINUTE:
            report["warn"].append(f"timing: {still:.1f} still seconds a minute")
    else:
        report["warn"].append(f"timing: the probe failed: {r.stderr[-300:]}")
    return finish()


if __name__ == "__main__":
    raise SystemExit(main())
