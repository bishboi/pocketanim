"""harness_v3's web app: runs, their steps, their calls and costs, the score and the video.

    ../.venv3/bin/python engine/server.py [--port 8300]      then open http://localhost:8300

The API (JSON):
    GET  /api/runs                         every run (newest first): id, title, cost, tokens, status, seconds
    POST /api/runs                         {title, narration, model, voice, quality, critic, speed, pause, score?}:
                                           a new run, started
    GET  /api/runs/<id>                    the run (settings, steps, calls), its narration, words, storyboard, score
    POST /api/runs/<id>/export             an MP4 made from the player, compared with the render (run.export)
    GET  /play/<id>                        the player, playing the run's timeline
    POST /api/runs/<id>/stop               stop a run (its voice or render killed; a queued one dropped)
    POST /api/stop                         stop every run
    POST /api/runs/<id>/step               {step, shot?}: run again from that step (one shot's score with `shot`)
    PUT  /api/runs/<id>/score              {text}: the score changed by hand, rendered again
    GET  /files/<id>/<name>                a run's file (the video in byte ranges, so it seeks)
    GET  /api/config                       the models, voices and whether a key is set

    GET  /api/books                        every book (newest first): id, title, pages, videos, cost with its videos'
    POST /api/books                        the PDF as the body (header X-Filename): kept, and read by Datalab
    GET  /api/books/<id>                   the book (sections, scripts, calls), each video's run beside it, the totals
    GET  /api/books/<id>/pages?from=&to=   the pages' text
    POST /api/books/<id>/read              the PDF read again (after a failed read)
    POST /api/books/<id>/script            {from, to, model, videos, seconds, notes}: a script of those pages, started
    PUT  /api/books/<id>/scripts/<s>/<k>   {title, narration}: a video's narration changed by hand
    DELETE /api/books/<id>/scripts/<s>     a script dropped (its runs stay)
    POST /api/books/<id>/build             {script, video?, model, voice, quality, critic, speed, pause}: one video
                                           (or every one not built yet) made as runs
    GET  /books/<id>/source.pdf            the PDF
    GET  /assets/<file>.png                a made picture (the image model's, kept in .cache/assets)
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import env  # noqa: E402,F401 -- the keys from .env files, before anything reads them
import assets  # noqa: E402
import books  # noqa: E402
import runs  # noqa: E402
from urllib.parse import parse_qs, unquote  # noqa: E402

PAGE = HERE / "ui.html"
import tts_gemini  # noqa: E402
PIPER_VOICES = sorted(p.stem for p in (HERE.parent / ".cache" / "voices").glob("*.onnx"))
# Gemini TTS voices first (GEMINI_API_KEY), then the offline Piper ones
VOICES = [f"gemini:{v}" for v in tts_gemini.VOICES] + PIPER_VOICES
MODELS = ["anthropic/claude-haiku-4.5", "google/gemini-2.5-flash", "openai/gpt-4.1-mini", "qwen/qwen3-30b-a3b",
          "meta-llama/llama-3.3-70b-instruct"]
SERVED = {"video.mp4", "voice.wav", "words.json", "storyboard.json", "video.score", "narration.txt", "shots.json",
          "player.mp4", "compare.json"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet: only errors
        pass

    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/config":
                extra = [m.strip() for m in os.environ.get("V3_MODELS", "").split(",") if m.strip()]
                models = list(dict.fromkeys([runs.DEFAULT_MODEL, *extra, *MODELS]))
                self._json({"models": models, "default_model": runs.DEFAULT_MODEL, "problems": problems(),
                            "steps": runs.STEPS, "step_models": runs.step_models(), "render_mp4": runs.RENDER_MP4,
                            "script_model": os.environ.get("V3_MODEL_SCRIPT") or runs.DEFAULT_MODEL, "voices": VOICES,
                            "default_voice": runs.default_voice(), "languages": runs.LANGUAGES,
                            "key": bool(os.environ.get("OPENROUTER_API_KEY")),
                            "datalab": bool(os.environ.get("DATALAB_API_KEY", "").strip())})
            elif path == "/api/runs":
                self._json(runs.listing())
            elif path == "/api/books":
                self._json(books.listing())
            elif m := re.fullmatch(r"/api/books/([\w-]+)", path):
                self._json(books.view(m.group(1)))
            elif m := re.fullmatch(r"/api/books/([\w-]+)/pages", path):
                q = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                a, b = int(q.get("from", ["1"])[0]), int(q.get("to", ["1"])[0])
                texts = books.pages(m.group(1))
                self._json([{"page": k, "text": texts[k - 1]} for k in range(max(1, a), min(len(texts), b) + 1)])
            elif m := re.fullmatch(r"/assets/((?:pic|photo|flag)-[\w-]+\.png)", path):
                self._file(assets.CACHE / m.group(1))
            elif m := re.fullmatch(r"/books/([\w-]+)/source\.pdf", path):
                self._file(books.book_dir(m.group(1)) / "source.pdf")
            elif m := re.fullmatch(r"/api/runs/([\w-]+)", path):
                rid = m.group(1)
                d = runs.run_dir(rid)
                run = runs.load(rid)

                def read(name):
                    p = d / name
                    return p.read_text() if p.exists() else None
                words = json.loads(read("words.json") or "null")
                score_text = read("video.score") or ""
                pictures = []
                for kind, prompt, lk in assets.wants(score_text):
                    p = assets.path_for(kind, prompt, lk if lk in ("editorial", "paper") else "paper")
                    pictures.append({"kind": kind, "prompt": prompt, "file": p.name if p.exists() else None,
                                     "model": assets.made_with(p) if p.exists() else None})
                self._json({"run": run, "busy": rid in runs._busy, "narration": read("narration.txt"), "pictures": pictures,
                            "words": words, "storyboard": json.loads(read("storyboard.json") or "null"),
                            "score": read("video.score"), "video": (d / "video.mp4").exists(),
                            "player": (d / "player" / "timeline.json").exists() or (d / "player" / "parts.json").exists(), "player_mp4": (d / "player.mp4").exists()})
            elif m := re.fullmatch(r"/play/([\w-]+)", path):
                body = (HERE / "player.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif m := re.fullmatch(r"/files/([\w-]+)/player/((?:p\d+/)?(?:timeline\.json|parts\.json|voice\.wav|"
                                   r"soundtrack\.wav|img-[0-9a-f]+\.png))", path):
                self._file(runs.run_dir(m.group(1)) / "player" / m.group(2))
            elif m := re.fullmatch(r"/files/([\w-]+)/([\w.\-]+)", path):
                name = m.group(2)
                if name not in SERVED and not re.fullmatch(r"(critic|cmp)-[\d.]+\.jpg", name):
                    return self._json({"error": "not served"}, 404)
                self._file(runs.run_dir(m.group(1)) / name)
            else:
                self._json({"error": "not found"}, 404)
        except FileNotFoundError:
            self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, 500)

    def _file(self, p: Path) -> None:
        if p.suffix == ".json" and "gzip" in (self.headers.get("Accept-Encoding") or "") and p.stat().st_size > 200_000:
            gz = p.with_name(p.name + ".gz")      # a timeline is large and compresses well: sent compressed
            if not gz.exists() or gz.stat().st_mtime < p.stat().st_mtime:
                import gzip
                gz.write_bytes(gzip.compress(p.read_bytes(), 6))
            body = gz.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        size = p.stat().st_size
        kind = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        rng = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range") or "")
        start, end = (int(rng.group(1)), int(rng.group(2)) if rng and rng.group(2) else size - 1) if rng else (0, size - 1)
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", kind)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with p.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 16, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/books":
                n = int(self.headers.get("Content-Length") or 0)
                if not n or n > 200 << 20:
                    return self._json({"error": "upload a PDF (at most 200 MB)"}, 400)
                book = books.add(unquote(self.headers.get("X-Filename") or "book.pdf"), self.rfile.read(n))
                return self._json({"id": book["id"]})
            b = self._body()
            if m := re.fullmatch(r"/api/books/([\w-]+)/read", path):
                books.reread(m.group(1))
                self._json({"ok": True})
            elif m := re.fullmatch(r"/api/books/([\w-]+)/script", path):
                self._json({"script": books.script(m.group(1), b.get("from") or 1, b.get("to") or 1, b)})
            elif m := re.fullmatch(r"/api/books/([\w-]+)/build", path):
                v = b.get("video")
                self._json({"runs": books.build(m.group(1), str(b["script"]), int(v) if v is not None else None, b)})
            elif path == "/api/runs":
                if not str(b.get("narration") or "").strip():
                    return self._json({"error": "the narration is empty"}, 400)
                run = runs.create(str(b.get("title") or ""), str(b["narration"]), b)
                runs.start(run["id"], "voice")
                self._json({"id": run["id"]})
            elif path == "/api/stop":
                self._json({"stopped": runs.stop_all()})
            elif m := re.fullmatch(r"/api/runs/([\w-]+)/export", path):
                runs.export(m.group(1))
                self._json({"ok": True})
            elif m := re.fullmatch(r"/api/runs/([\w-]+)/stop", path):
                self._json({"stopped": runs.stop(m.group(1))})
            elif m := re.fullmatch(r"/api/runs/([\w-]+)/step", path):
                shot = b.get("shot")
                runs.start(m.group(1), str(b.get("step") or "voice"), int(shot) if shot is not None else None)
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, 400)

    def do_PUT(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            if m := re.fullmatch(r"/api/runs/([\w-]+)/score", path):
                runs.set_score(m.group(1), str(self._body().get("text") or ""))
                self._json({"ok": True})
            elif m := re.fullmatch(r"/api/books/([\w-]+)/scripts/(\w+)/(\d+)", path):
                b = self._body()
                books.set_video(m.group(1), m.group(2), int(m.group(3)), str(b.get("title") or ""),
                                str(b.get("narration") or ""))
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, 400)


    def do_DELETE(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            if m := re.fullmatch(r"/api/books/([\w-]+)/scripts/(\w+)", path):
                books.delete_script(m.group(1), m.group(2))
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, 400)


def problems() -> list[str]:
    """What is missing from the setup (./setup.sh makes it), said once at start."""
    import importlib.util
    import shutil
    out = []
    if not (3, 10) <= sys.version_info[:2] <= (3, 13):
        out.append(f"this Python is {sys.version.split()[0]}; the voice needs 3.10-3.13: "
                   "rm -r ../.venv3 && brew install python@3.12 && ./setup.sh")
    missing = [m for m in ("manim", "piper", "faster_whisper") if importlib.util.find_spec(m) is None]
    if missing:
        out.append(f"Python packages missing ({', '.join(missing)}): run ./setup.sh")
    if not VOICES:
        out.append("no voices in .cache/voices: run ./setup.sh")
    if not (HERE.parent / ".cache" / "package" / "icons").is_dir():
        out.append("no icons in .cache/package: run ./setup.sh")
    if not (HERE.parent / ".cache" / "flagpkg" / "package" / "flags").is_dir() or not list((HERE.parent / ".cache" / "fonts").glob("*.ttf")):
        out.append("the kit's fonts or flags are missing: run ./setup.sh")
    if importlib.util.find_spec("playwright") is None:
        out.append("playwright is missing (the player's MP4 export): run ./setup.sh")
    if importlib.util.find_spec("cairosvg") is None:
        out.append("cairosvg is missing (flags): run ./setup.sh")
    if not shutil.which("ffmpeg"):
        out.append("ffmpeg is not on the PATH (macOS: brew install ffmpeg)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8300)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    runs.RUNS.mkdir(parents=True, exist_ok=True)
    books.BOOKS.mkdir(parents=True, exist_ok=True)
    left = runs.recover() + books.recover()
    if left:
        print(f"{len(left)} run(s) or book(s) were cut off when the server last stopped: marked stopped")
    import subprocess
    try:
        rev = subprocess.run(["git", "-C", str(HERE), "log", "-1", "--format=%h %s"], capture_output=True, text=True,
                             timeout=5).stdout.strip()
        print(f"code: {rev}" if rev else "code: (not a git checkout)")
    except Exception:  # noqa: BLE001 -- no git: nothing to say
        pass
    for p in problems():
        print("SETUP: " + p)
    if env.LOADED:
        print("settings read from " + ", ".join(env.LOADED))
    print(f"harness_v3 on http://{a.host}:{a.port}" + ("" if os.environ.get("OPENROUTER_API_KEY")
                                                       else "  (no OPENROUTER_API_KEY: runs need a score given by hand)"))
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
