"""Deliver: chapter renders -> out/video.mp4 and everything that goes with it.

    out/video.mp4          chapters joined; speech + music (ducked under speech); -17 LUFS
    out/video.srt          one cue per beat, from the renders' beat logs
    out/chapters.txt       YouTube chapter marks
    out/thumbnail.png      the title slide
    out/contact_sheet.png  one frame per beat, labelled c3.b05
    qa/report.json         every gate and measurement, what was waived, cost
    out/phone/<chapter>/   the .panim programs, when the job asks for phone output
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from forge.engine import qa
from forge.engine.compile import line_ids
from forge.util import REPO, write_json

MUSIC = {
    # Low sine layers that breathe slowly: sits under a voice without a tune to follow.
    "drone": ("0.30*sin(2*PI*55*t)*(0.6+0.4*sin(2*PI*0.05*t))"
              "+0.20*sin(2*PI*82.41*t)*(0.6+0.4*sin(2*PI*0.037*t))"
              "+0.10*sin(2*PI*110*t+sin(2*PI*0.2*t))*(0.5+0.5*sin(2*PI*0.021*t))"),
    # The drone and a slow drum: a low thump every 0.75 s, a brush on the off-beat.
    "martial": ("0.22*sin(2*PI*55*t)*(0.6+0.4*sin(2*PI*0.05*t))"
                "+0.12*sin(2*PI*73.42*t)*(0.6+0.4*sin(2*PI*0.031*t))"
                "+0.55*sin(2*PI*58*t)*exp(-14*mod(t,0.75))"
                "+0.10*(random(0)*2-1)*exp(-30*mod(t+1.125,1.5))"),
}


def _run(args, timeout=3600):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, args[:6]))}...: {result.stderr[-1500:]}")
    return result


def _stamp(seconds: float, srt: bool = True) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}" if srt else (f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")


def music_track(preset: str, seconds: float, out: Path, level_lufs: float) -> Path | None:
    if preset not in MUSIC:
        return None
    raw = out.with_name("music_raw.wav")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
          f"aevalsrc=exprs='{MUSIC[preset]}':s=44100:d={seconds + 1:.2f}",
          "-af", f"lowpass=f=900,aecho=0.8:0.5:120:0.25,afade=t=in:d=3,afade=t=out:st={max(0.0, seconds - 4):.2f}:d=4",
          "-ac", "2", str(raw)])
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", f"loudnorm=I={level_lufs}:TP=-6:LRA=7",
          "-ar", "44100", "-ac", "2", str(out)])
    raw.unlink(missing_ok=True)
    return out


def deliver(job, template: dict, style: dict, renders: dict, gate_report: dict | None = None,
            phone: bool = False) -> dict:
    started = time.time()
    outline = job.read("outline.json")
    out = job.path("out")
    work = job.path("build", "assemble")
    out.mkdir(exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    order = [c["id"] for c in outline["chapters"] if c["id"] in renders and not renders[c["id"]].get("error")]
    if not order:
        raise RuntimeError("no chapter rendered")

    # ---- offsets, and one audio track per chapter padded to its video ----
    offsets, lengths, speech_parts = {}, {}, []
    clock = 0.0
    for cid in order:
        video = renders[cid]["video"]
        length = qa.duration(video)
        offsets[cid], lengths[cid] = clock, length
        clock += length
        part = work / f"{cid}.wav"
        if qa.has_audio(video):
            _run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vn", "-af", f"apad,atrim=0:{length:.3f}",
                  "-ar", "44100", "-ac", "2", str(part)])
        else:
            _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                  "anullsrc=r=44100:cl=stereo", "-t", f"{length:.3f}", str(part)])
        speech_parts.append(part)
    total = clock

    # ---- picture: the chapters' video streams, joined without re-encoding ----
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{renders[cid]['video']}'\n" for cid in order))
    picture = work / "picture.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-map", "0:v",
          "-c", "copy", str(picture)])

    # ---- sound: speech, music ducked under it, the whole levelled ----
    speech = work / "speech.wav"
    _run(["ffmpeg", "-y", "-loglevel", "error", *sum((["-i", str(p)] for p in speech_parts), []),
          "-filter_complex", "".join(f"[{i}:a]" for i in range(len(speech_parts)))
          + f"concat=n={len(speech_parts)}:v=0:a=1[a]", "-map", "[a]", str(speech)])
    music_cfg = {**{"preset": "drone", "duck_db": 15}, **(style.get("music") or {})}
    duck_db = float(music_cfg.get("duck_db", 15))
    music = music_track(music_cfg.get("preset", "none"), total, work / "music.wav", -17 - duck_db - 4)
    mixed = work / "mix.wav"
    ducked = work / "music_ducked.wav"
    if music:
        graph = ("[0:a]asplit=2[sc][sp];"
                 "[1:a][sc]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=600[duck];"
                 "[duck]asplit=2[d1][d2];"
                 "[sp][d1]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-17:TP=-1.5:LRA=11[mix]")
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(speech), "-i", str(music), "-filter_complex", graph,
              "-map", "[mix]", "-ar", "44100", str(mixed), "-map", "[d2]", str(ducked)])
    else:
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(speech), "-af", "loudnorm=I=-17:TP=-1.5:LRA=11",
              "-ar", "44100", str(mixed)])
    video = out / "video.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(picture), "-i", str(mixed), "-map", "0:v", "-map", "1:a",
          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(video)])

    # ---- subtitles and chapter marks, from the beat logs ----
    cues, marks, labels = [], [], {}
    for cid in order:
        chapter = next(c for c in outline["chapters"] if c["id"] == cid)
        labels[cid] = line_ids(chapter, job.script(cid))
        rows = [r for r in qa.read_log(renders[cid]["log"]) if r["kind"] == "beat"]
        marks.append((offsets[cid], chapter["title"] if marks else job.spec["title"]))
        for index, row in enumerate(rows):
            start = offsets[cid] + row["start"]
            nxt = offsets[cid] + rows[index + 1]["start"] if index + 1 < len(rows) else offsets[cid] + lengths[cid]
            end = min(start + row["seconds"] + 0.25, nxt - 0.05)
            cues.append((start, max(end, start + 0.5), row["text"]))
    srt = []
    for n, (start, end, text) in enumerate(cues, 1):
        body = "\n".join(textwrap.wrap(text, 44)[:3])
        srt.append(f"{n}\n{_stamp(start)} --> {_stamp(end)}\n{body}\n")
    (out / "video.srt").write_text("\n".join(srt), encoding="utf-8")
    (out / "chapters.txt").write_text("".join(f"{_stamp(t, srt=False)} {title}\n" for t, title in marks),
                                      encoding="utf-8")

    # ---- thumbnail and contact sheet ----
    first = renders[order[0]]["video"]
    qa.frame(first, min(2.6, lengths[order[0]] / 2), out / "thumbnail.png", width=1280)
    sheet = qa.contact_sheet(job, {cid: renders[cid] for cid in order}, labels, out / "contact_sheet.png")

    # ---- the output gate ----
    checks = qa.audio_check(video, speech, ducked if music else None,
                            target_seconds=outline["target_minutes"] * 60, duck_db=duck_db)

    # ---- phone programs ----
    phone_result = {}
    if phone:
        phone_result = export_phone(job, order)

    state = job.state
    report = {
        "job": job.id, "title": job.spec["title"], "template": template["id"], "template_version": template.get("version"),
        "style": style["id"], "style_version": style.get("version"), "engine": state.get("engine"),
        "voice": (job.read("timeline.json") or {}).get("voice"),
        "delivered": {"video": str(video), "srt": str(out / "video.srt"), "chapters": str(out / "chapters.txt"),
                      "thumbnail": str(out / "thumbnail.png"), "contact_sheet": sheet.get("file")},
        "chapters": [{"id": cid, "start": round(offsets[cid], 2), "seconds": round(lengths[cid], 2),
                      "cached": renders[cid].get("cached", False)} for cid in order],
        "failed_chapters": [cid for cid, r in renders.items() if r.get("error")],
        "output": checks,
        "gates": gate_report or {},
        "phonemes": job.read("qa/phonemes.json"),
        "phone": phone_result,
        "waived": state.get("waived", []), "open_questions": state.get("open_questions", []),
        "human_review": state.get("human_review", []),
        "tokens": state.get("tokens"), "cost_usd": state.get("cost_usd"), "timings": state.get("timings"),
        "assemble_seconds": round(time.time() - started, 1),
    }
    write_json(job.path("qa", "report.json"), report)
    shutil.copy(job.path("qa", "report.json"), out / "report.json")
    return report


def export_phone(job, order: list[str]) -> dict:
    """The chapters as one phone library: out/phone/library, plus a zip of it.

    Each chapter scene is exported to a .panim program in one shared export
    directory (so they share a glyph atlas and assets), speaking from the
    job's own voice cache, then packed with tools.build_library -- the layout
    the player opens: unzip and `adb push library ...`.
    """
    script = REPO / "harness" / "scripts" / "export_scene.py"
    export_dir = job.path("build", "phone")
    shutil.rmtree(export_dir, ignore_errors=True)
    export_dir.mkdir(parents=True)
    env = dict(os.environ)
    env.update({"PANIM_AUDIO_DIR": str(job.path("audio")),
                "PANIM_VOICE": (job.read("timeline.json") or {}).get("voice") or env.get("PANIM_VOICE", "auto")})
    results = {}
    for cid in order:
        copy = export_dir / f"{cid}.py"
        shutil.copy(job.path("build", f"{cid}.py"), copy)
        try:
            result = subprocess.run([sys.executable, str(script), str(copy), cid.upper(), str(export_dir)],
                                    capture_output=True, text=True, timeout=3600, env=env)
            reply = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
            results[cid] = {"ok": result.returncode == 0 and not reply.get("error"), "tier": reply.get("tier"),
                            "blockers": reply.get("blockers", [])[:5], "error": reply.get("error")}
        except Exception as error:  # noqa: BLE001 -- the video is the deliverable; the phone copy is extra
            results[cid] = {"ok": False, "error": str(error)}
    library = job.path("out", "phone", "library")
    shutil.rmtree(library.parent, ignore_errors=True)
    packed = subprocess.run([sys.executable, "-m", "tools.build_library", "--source",
                             str(export_dir / "dsl" / "generated"), "--out", str(library)],
                            cwd=REPO, capture_output=True, text=True, timeout=1800)
    out = {"chapters": results, "library": None}
    if packed.returncode == 0 and library.exists():
        out["library"] = str(library)
        out["zip"] = shutil.make_archive(str(job.path("out", f"{job.id}-phone")), "zip", library.parent, "library")
    else:
        out["error"] = (packed.stderr or packed.stdout)[-1500:]
    return out
