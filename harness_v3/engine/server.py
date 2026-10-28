"""harness_v3's web app: runs, their steps, their calls and costs, the score and the video.

    ../.venv3/bin/python engine/server.py [--port 8300]      then open http://localhost:8300

The API (JSON):
    GET  /api/runs                         every run (newest first): id, title, cost, tokens, status, seconds
    POST /api/runs                         {title, narration, model, voice, quality, critic, speed, pause, score?}:
                                           a new run, started
    GET  /api/runs/<id>                    the run (settings, steps, calls), its narration, words, storyboard, score
    POST /api/runs/<id>/step               {step, shot?}: run again from that step (one shot's score with `shot`)
    PUT  /api/runs/<id>/score              {text}: the score changed by hand, rendered again
    GET  /files/<id>/<name>                a run's file (the video in byte ranges, so it seeks)
    GET  /api/config                       the models, voices and whether a key is set

    GET  /api/books                        every book (newest first): id, title, pages, videos, cost with its videos'
    POST /api/books                        the PDF as the body (header X-Filename): kept and read
    GET  /api/books/<id>                   the book (sections, scripts, calls), each video's run beside it, the totals
    GET  /api/books/<id>/pages?from=&to=   the pages' text
    POST /api/books/<id>/script            {from, to, model, videos, seconds, notes}: a script of those pages, started
    PUT  /api/books/<id>/scripts/<s>/<k>   {title, narration}: a video's narration changed by hand
    DELETE /api/books/<id>/scripts/<s>     a script dropped (its runs stay)
    POST /api/books/<id>/build             {script, video?, model, voice, quality, critic, speed, pause}: one video
                                           (or every one not built yet) made as runs
    GET  /books/<id>/source.pdf            the PDF
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

import books  # noqa: E402
import runs  # noqa: E402
from urllib.parse import parse_qs, unquote  # noqa: E402

PAGE = HERE / "ui.html"
VOICES = sorted(p.stem for p in (HERE.parent / ".cache" / "voices").glob("*.onnx"))
MODELS = ["anthropic/claude-haiku-4.5", "google/gemini-2.5-flash", "openai/gpt-4.1-mini", "qwen/qwen3-30b-a3b",
          "meta-llama/llama-3.3-70b-instruct"]
SERVED = {"video.mp4", "voice.wav", "words.json", "storyboard.json", "video.score", "narration.txt", "shots.json"}


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
                self._json({"models": MODELS, "default_model": runs.DEFAULT_MODEL, "voices": VOICES,
                            "key": bool(os.environ.get("OPENROUTER_API_KEY"))})
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
                self._json({"run": run, "busy": rid in runs._busy, "narration": read("narration.txt"),
                            "words": words, "storyboard": json.loads(read("storyboard.json") or "null"),
                            "score": read("video.score"), "video": (d / "video.mp4").exists()})
            elif m := re.fullmatch(r"/files/([\w-]+)/([\w.]+)", path):
                name = m.group(2)
                if name not in SERVED and not re.fullmatch(r"critic-[\d.]+\.jpg", name):
                    return self._json({"error": "not served"}, 404)
                self._file(runs.run_dir(m.group(1)) / name)
            else:
                self._json({"error": "not found"}, 404)
        except FileNotFoundError:
            self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, 500)

    def _file(self, p: Path) -> None:
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
            if m := re.fullmatch(r"/api/books/([\w-]+)/script", path):
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8300)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    runs.RUNS.mkdir(parents=True, exist_ok=True)
    books.BOOKS.mkdir(parents=True, exist_ok=True)
    print(f"harness_v3 on http://{a.host}:{a.port}" + ("" if os.environ.get("OPENROUTER_API_KEY")
                                                       else "  (no OPENROUTER_API_KEY: runs need a score given by hand)"))
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
