"""Download the icon sets lectures draw from (Iconify JSON packages, from npm).

About 30,000 icons: single-colour silhouettes (game-icons, mdi, healthicons),
which a lecture fills with its style's colours, and flat colour emoji
(fluent-emoji-flat, openmoji, noto). Each set keeps its own licence; a lecture
that uses one credits it.

    .venv/bin/python harness/scripts/fetch_icons.py [--sets game-icons,fluent-emoji-flat,...]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "lecture" / "data" / "icons"
REGISTRY = "https://registry.npmjs.org/@iconify-json/{name}/latest"
DEFAULT = ["game-icons", "fluent-emoji-flat", "openmoji", "noto", "mdi", "healthicons"]


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "pocketanim-lecture/0.4"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def fetch(name: str) -> dict:
    meta = json.loads(_get(REGISTRY.format(name=name)))
    with tarfile.open(fileobj=io.BytesIO(_get(meta["dist"]["tarball"])), mode="r:gz") as archive:
        data = json.load(archive.extractfile("package/icons.json"))
        info = json.load(archive.extractfile("package/info.json")) if "package/info.json" in archive.getnames() else {}
    data["info"] = {**info, **(data.get("info") or {})}
    (TARGET / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    licence = (data["info"].get("license") or {}).get("title", "see package")
    return {"set": name, "version": meta["version"], "icons": len(data["icons"]), "license": licence}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sets", default=",".join(DEFAULT))
    args = ap.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name in [s.strip() for s in args.sets.split(",") if s.strip()]:
        try:
            row = fetch(name)
            print(f"{row['set']:20} {row['icons']:6,} icons  {row['license']}", flush=True)
        except Exception as error:  # noqa: BLE001
            print(f"{name}: {error}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
