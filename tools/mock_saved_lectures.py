"""Serve packed phone libraries as the harness's Supabase project would, for testing the player's Saved list.

The phone reads its catalog from Supabase's REST API (the view phone_lectures) and a lecture's files from Storage's
public bucket `lectures`: builds/<id>/library.zip (the library without its narration, as Save uploads it),
builds/<id>/library.json, and builds/<id>/audio/<scene>.ogg (the narration, streamed). This answers those same
paths, with Range requests (a stream seeks), so the player's streaming can be checked without a project.

    python -m tools.mock_saved_lectures <packed library dir> [--port 8787] [--series "Ray optics"] [--copies 2]
                                       [--audio-kbps 0]

--copies lists the library as that many lectures of one series (Lecture 1 of N, ...), for "Up next". --audio-kbps
throttles the narration (0: as fast as it goes), to see the player buffer.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def zipped_without_audio(library: Path) -> bytes:
    """The library as Save uploads it (harness/app/lib/pocketanim.ts zipLibrary): library/..., no audio/."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(library):
            for name in sorted(files):
                full = Path(folder) / name
                rel = full.relative_to(library).as_posix()
                if rel.startswith("audio/"):
                    continue
                z.write(full, "library/" + rel)
    return out.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("library", type=Path)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--series", default="Ray optics")
    parser.add_argument("--copies", type=int, default=2)
    parser.add_argument("--audio-kbps", type=float, default=0.0)
    args = parser.parse_args()

    library = args.library.resolve()
    manifest = json.loads((library / "library.json").read_text())
    scene = manifest["scenes"][0]
    bundle = zipped_without_audio(library)
    frames = int(scene.get("frames") or 0)
    rows = []
    for k in range(1, args.copies + 1):
        rows.append({
            "build_id": f"fixture-{k}", "project_id": "fixture", "series": args.series, "subject": "physics",
            "language": "en", "lecture": k, "lectures": args.copies, "title": f"Lecture {k}: Part {k} of the series",
            "minutes": round(frames / 30 / 60, 2), "library_path": f"builds/fixture-{k}",
            "library_bytes": len(bundle) + sum(p.stat().st_size for p in (library / "audio").glob("*")),
            "program_bytes": scene.get("program_bytes", 0), "frame_count": frames, "fps": 30,
            "narrated": bool(scene.get("audio")), "saved_at": f"2026-10-13T10:0{k}:00Z",
        })

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):  # noqa: N802 -- one line per request, to stderr
            sys.stderr.write("%s %s\n" % (self.command, self.path))

        def send_bytes(self, data: bytes, kind: str, throttle: float = 0.0) -> None:
            start, end = 0, len(data) - 1
            ranged = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if ranged and (ranged.group(1) or ranged.group(2)):
                if ranged.group(1):
                    start = int(ranged.group(1))
                    end = int(ranged.group(2)) if ranged.group(2) else end
                else:
                    start = max(0, len(data) - int(ranged.group(2)))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            if self.command == "HEAD":
                return
            body = data[start:end + 1]
            step = 4096
            for i in range(0, len(body), step):
                try:
                    self.wfile.write(body[i:i + step])
                except (BrokenPipeError, ConnectionResetError):
                    return
                if throttle > 0:
                    time.sleep(step * 8 / (throttle * 1000))

        def not_found(self) -> None:
            body = b'{"statusCode":"404","error":"not_found","message":"Object not found"}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self):  # noqa: N802
            self.do_GET()

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/rest/v1/phone_lectures":
                return self.send_bytes(json.dumps(rows).encode(), "application/json")
            match = re.match(r"^/storage/v1/object/public/lectures/builds/(fixture-\d+)/(.+)$", path)
            if not match:
                return self.not_found()
            rel = match.group(2)
            if rel == "library.zip":
                return self.send_bytes(bundle, "application/zip")
            target = (library / rel).resolve()
            if library not in target.parents or not target.is_file():
                return self.not_found()
            audio = rel.startswith("audio/")
            return self.send_bytes(target.read_bytes(), "audio/ogg" if audio else "application/octet-stream",
                                   args.audio_kbps if audio else 0.0)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving {library} as {args.copies} saved lecture(s) on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
