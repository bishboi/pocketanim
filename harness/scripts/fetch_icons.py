"""Download the icon sets lectures draw from (Iconify JSON packages, from npm).

About 45,000 icons. Colour sets come first: Fluent Emoji, Twemoji, Streamline Emojis,
Noto, EmojiOne, OpenMoji, Firefox emoji and Meteocons (weather). Single-colour
silhouettes (game-icons, mdi, healthicons) are a fallback that a lecture fills
with its style's colours. Each set keeps its own licence; a lecture
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
# Colour sets first (illustrations and map icons), then single-colour silhouettes as a fallback.
# fluent-emoji (Microsoft's shaded 3-D emoji, 100 MB) is optional: --sets fluent-emoji
DEFAULT = ["fluent-emoji-flat", "twemoji", "streamline-emojis", "noto", "emojione", "openmoji", "fxemoji",
           "meteocons", "game-icons", "mdi", "healthicons", "streamline-plump-color"]


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
    ap.add_argument("--missing", action="store_true", help="only the default sets not downloaded yet")
    args = ap.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    failed = 0
    names = [s.strip() for s in args.sets.split(",") if s.strip()]
    if args.missing:
        names = [n for n in names if not (TARGET / f"{n}.json").exists()]
    for name in names:
        try:
            row = fetch(name)
            print(f"{row['set']:20} {row['icons']:6,} icons  {row['license']}", flush=True)
        except Exception as error:  # noqa: BLE001
            print(f"{name}: {error}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
