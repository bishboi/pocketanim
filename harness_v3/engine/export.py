"""An MP4 made from the player (player.html drawing a timeline.json), and how it differs from the renderer's MP4.

    python export.py player_dir out.mp4 [--quality m] [--jobs N] [--compare video.mp4 --report report.json]

The player is opened in headless Chromium (Playwright) on a small local server, asked for each frame in turn
(`drawFrame(f)`, then the canvas as JPEG) and the frames are piped to ffmpeg; long videos are cut into chunks made at
once (as render.py does), then joined, with the voice laid under them.

With --compare, both videos are compared frame by frame (PSNR, as ffmpeg measures it): the report gives the mean,
the share of frames that differ visibly, and the moments that differ most, each with the two frames side by side
(cmp-<seconds>.jpg beside the report), so a difference can be seen, said and fixed.
"""

from __future__ import annotations

import argparse
import base64
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = {"h": (1920, 1080, 30), "m": (1280, 720, 30), "l": (854, 480, 15)}


def chromium(p):
    """Playwright's own Chromium, else one named by PW_CHROMIUM (or a preinstalled one)."""
    try:
        return p.chromium.launch()
    except Exception:  # noqa: BLE001
        for exe in (os.environ.get("PW_CHROMIUM"), "/opt/pw-browsers/chromium"):
            if exe and Path(exe).exists():
                return p.chromium.launch(executable_path=exe)
        raise RuntimeError("no Chromium for the player export: run ./setup.sh (python -m playwright install chromium)")


class _Files(SimpleHTTPRequestHandler):
    """/player.html from the engine, everything else from the player folder."""
    def __init__(self, *a, data: Path, **k):
        self.data = data
        super().__init__(*a, directory=str(data), **k)

    def translate_path(self, path):
        if path.split("?", 1)[0] == "/player.html":
            return str(HERE / "player.html")
        return super().translate_path(path)

    def log_message(self, *a):
        pass


def serve(data: Path) -> tuple[ThreadingHTTPServer, int]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Files, data=data))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def chunk(data: Path, out: Path, f0: int, f1: int, quality: str) -> None:
    """Frames f0..f1 of the player into out (no sound)."""
    from playwright.sync_api import sync_playwright
    w, h, fps = RES[quality]
    srv, port = serve(data)
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg",
                            "-framerate", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                            "-preset", "veryfast", str(out)], stdin=subprocess.PIPE)
    try:
        with sync_playwright() as p:
            b = chromium(p)
            page = b.new_page(viewport={"width": w, "height": h})
            page.goto(f"http://127.0.0.1:{port}/player.html?export=1&src=/&w={w}&h={h}")
            page.wait_for_function("window.__ready !== undefined")
            page.evaluate("window.__ready")
            tfps = page.evaluate("info().fps")
            every = max(1, (f1 - f0) // 100)
            for f in range(f0, f1):
                page.evaluate(f"drawFrame({f * tfps / fps})")       # the timeline's frame at this video frame's time
                url = page.evaluate("grab(0.93)")
                enc.stdin.write(base64.b64decode(url.split(",", 1)[1]))
                if (f - f0) % every == 0 or f == f1 - 1:
                    print(f"progress: {f - f0 + 1}/{f1 - f0} frames", flush=True)
            b.close()
    finally:
        enc.stdin.close()
        enc.wait()
        srv.shutdown()
    if enc.returncode != 0:
        raise RuntimeError("ffmpeg could not encode the player's frames")


def meta(data: Path) -> dict:
    """The video's frames, rate, size and soundtrack: a long video's parts.json, else its timeline.json."""
    p = data / "parts.json"
    return json.loads((p if p.exists() else data / "timeline.json").read_text())


def stills(data: Path, shots: dict, width: int = 640) -> None:
    """Frames of the player at given seconds, as JPEGs ({seconds: path}): what the critic looks at when there is no
    MP4."""
    from playwright.sync_api import sync_playwright
    tl = meta(data)
    w, h = width, round(width * tl["size"][1] / tl["size"][0])
    srv, port = serve(data)
    try:
        with sync_playwright() as p:
            b = chromium(p)
            page = b.new_page(viewport={"width": w, "height": h})
            page.goto(f"http://127.0.0.1:{port}/player.html?export=1&src=/&w={w}&h={h}")
            page.wait_for_function("window.__ready !== undefined")
            page.evaluate("window.__ready")
            for t, path in shots.items():
                page.evaluate(f"drawFrame({t * tl['fps']})")
                Path(path).write_bytes(base64.b64decode(page.evaluate("grab(0.9)").split(",", 1)[1]))
            b.close()
    finally:
        srv.shutdown()


def export(data: Path, out: Path, quality: str = "m", jobs: int | None = None) -> None:
    tl = meta(data)
    w, h, fps = RES[quality]
    total = int(round(tl["frames"] * fps / tl["fps"]))
    jobs = max(1, min(jobs or max(1, min(8, (os.cpu_count() or 2) // 2)), max(1, total // (fps * 5))))
    parts = out.parent / ".player-parts"
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir(parents=True)
    cuts = [round(total * k / jobs) for k in range(jobs + 1)]
    print(f"drawing {total} frames from the player in {jobs} chunk(s) at once", flush=True)
    procs = [subprocess.Popen([sys.executable, __file__, str(data), str(parts / f"part{k}.mp4"), "--quality", quality,
                               "--frames", f"{cuts[k]}:{cuts[k + 1]}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, bufsize=1, env={**os.environ, "PYTHONUNBUFFERED": "1"}) for k in range(jobs)]
    done, errs = [0] * jobs, [[] for _ in range(jobs)]

    def pump(k: int, stream, buf) -> None:
        for line in iter(stream.readline, ""):
            m = re.match(r"^progress: (\d+)/(\d+)", line)
            if m:
                done[k] = int(m.group(1))
            elif buf is not None:
                buf.append(line)
        stream.close()

    readers = [threading.Thread(target=pump, args=(k, p.stdout, None), daemon=True) for k, p in enumerate(procs)]
    readers += [threading.Thread(target=pump, args=(k, p.stderr, errs[k]), daemon=True) for k, p in enumerate(procs)]
    for t in readers:
        t.start()
    import time
    last = -1
    while any(p.poll() is None for p in procs):
        time.sleep(0.5)
        if sum(done) != last:
            last = sum(done)
            print(f"progress: {last}/{total} frames drawn by the player", flush=True)
    for t in readers:
        t.join(timeout=5)
    for k, p in enumerate(procs):
        if p.returncode != 0:
            raise RuntimeError(f"a chunk of the player export failed:\n{''.join(errs[k])[-1500:]}")
    print("joining the chunks and laying the voice under them", flush=True)
    (parts / "list.txt").write_text("".join(f"file 'part{k}.mp4'\n" for k in range(jobs)))
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(parts / "list.txt")]
    voice = data / (tl.get("audio") or "voice.wav")
    if voice.exists():
        cmd += ["-i", str(voice), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k"]
    subprocess.run(cmd + ["-c:v", "copy", str(out)], check=True)
    shutil.rmtree(parts, ignore_errors=True)


def compare(a: Path, b: Path, out_dir: Path, worst: int = 6) -> dict:
    """The renderer's video (a) against the player's (b), frame by frame."""
    stats = out_dir / "psnr.txt"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(a), "-i", str(b), "-lavfi",
                    f"[1:v][0:v]scale2ref[b][a];[a][b]psnr=stats_file={stats}", "-f", "null", "-"], check=True)
    vals = []
    for line in stats.read_text().splitlines():
        m = re.search(r"psnr_avg:(\S+)", line)
        if m:
            vals.append(99.0 if m.group(1) == "inf" else float(m.group(1)))
    stats.unlink(missing_ok=True)
    fps = 30.0
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                            "-of", "csv=p=0", str(a)], capture_output=True, text=True).stdout.strip()
        n, d = r.split("/")
        fps = float(n) / float(d)
    except Exception:  # noqa: BLE001
        pass
    for old in out_dir.glob("cmp-*.jpg"):
        old.unlink()
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    picked: list[int] = []
    for i in order:
        if len(picked) >= worst or vals[i] >= 40:
            break
        if all(abs(i - j) > fps * 1.5 for j in picked):
            picked.append(i)
    moments = []
    for i in sorted(picked):
        t = i / fps
        name = f"cmp-{t:.1f}.jpg"
        # the very frame compared (a seek by time can land a frame apart in the two files)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(a), "-i", str(b), "-filter_complex",
                        f"[0:v]select=eq(n\\,{i})[a0];[1:v]select=eq(n\\,{i})[b0];[b0][a0]scale2ref[b][a];"
                        "[a][b]hstack,scale=1280:-2", "-frames:v", "1", str(out_dir / name)], check=True)
        moments.append({"t": round(t, 2), "psnr": round(vals[i], 1), "image": name})
    real = [v for v in vals if v < 99]
    return {"frames": len(vals), "mean_psnr": round(sum(real) / len(real), 1) if real else 99.0,
            "under_30db": round(sum(1 for v in vals if v < 30) / max(1, len(vals)), 3),
            "under_35db": round(sum(1 for v in vals if v < 35) / max(1, len(vals)), 3),
            "worst": moments}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--quality", default="m")
    ap.add_argument("--jobs", type=int)
    ap.add_argument("--frames", help=argparse.SUPPRESS)
    ap.add_argument("--compare")
    ap.add_argument("--report")
    a = ap.parse_args()
    if a.frames:
        f0, f1 = (int(x) for x in a.frames.split(":"))
        chunk(Path(a.data), Path(a.out), f0, f1, a.quality)
        return
    export(Path(a.data), Path(a.out), a.quality, a.jobs)
    print(f"wrote {a.out}")
    if a.compare:
        print("comparing the player's MP4 with the render's, frame by frame", flush=True)
        rep = compare(Path(a.compare), Path(a.out), Path(a.report).parent if a.report else Path(a.out).parent)
        if a.report:
            Path(a.report).write_text(json.dumps(rep, indent=1))
        print("compare:", json.dumps(rep))


if __name__ == "__main__":
    main()
