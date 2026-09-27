"""Photos and illustrations from Wikimedia Commons, for lectures.

Only files whose licence lets a video reuse them are returned (public domain,
CC0, CC BY, CC BY-SA), each with the credit line it needs. A lecture names an
image by its Commons title ("File:Sugarcane field.jpg") or by a search query;
the compiler downloads it once into .cache/images and the scene draws the
local file, so a render never waits on the network.

    python harness/lecture/images.py "sugarcane field" "Ganges at Varanasi"    # search, as JSON

PANIM_IMAGES=0 turns internet images off (a lecture then draws its stage
from icons and document figures only). COMMONS_API overrides the endpoint.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("PANIM_IMAGE_CACHE") or (HERE / ".cache" / "images"))
UA = "pocketanim-lecture/0.4 (educational map lectures; https://github.com/bishboi/pocketanim)"
ALLOWED = re.compile(r"^(public domain|pd\b|cc0|cc[- ]by(-sa)?[- ]?\d|cc[- ]by(-sa)?$)", re.I)


def api() -> str:
    return os.environ.get("COMMONS_API", "https://commons.wikimedia.org/w/api.php")


def enabled() -> bool:
    return os.environ.get("PANIM_IMAGES", "1") != "0"


def _get(url: str, timeout: float = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _text(value) -> str:
    """Commons metadata is HTML: strip tags and entities."""
    return html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()


def _row(page: dict) -> dict | None:
    info = (page.get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata") or {}
    licence = _text((meta.get("LicenseShortName") or {}).get("value"))
    if not ALLOWED.match(licence):
        return None
    if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
        return None
    if (info.get("width") or 0) < 640:
        return None
    artist = _text((meta.get("Artist") or {}).get("value")) or "unknown author"
    return {
        "id": page["title"],
        "title": page["title"].removeprefix("File:").rsplit(".", 1)[0],
        "description": _text((meta.get("ImageDescription") or {}).get("value"))[:200],
        "width": info.get("width"), "height": info.get("height"),
        "url": info.get("thumburl") or info.get("url"),
        "license": licence, "artist": artist[:80],
        "credit": f"{artist[:60]}, {licence}, via Wikimedia Commons",
    }


def _query(params: dict) -> list[dict]:
    base = {"action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "1600"}
    data = json.loads(_get(f"{api()}?{urllib.parse.urlencode({**base, **params})}"))
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return [row for row in (_row(p) for p in pages) if row]


def search(query: str, limit: int = 6) -> list[dict]:
    """Reusable photos for a query, best first. [] when offline or disabled."""
    if not enabled():
        return []
    try:
        rows = _query({"generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": "6",
                       "gsrlimit": str(max(limit * 3, 10))})
    except Exception:  # noqa: BLE001 -- offline or blocked: the lecture falls back to icons
        return []
    return rows[:limit]


def lookup(title: str) -> dict | None:
    """One Commons file by title, if its licence allows reuse."""
    if not enabled():
        return None
    title = title if title.startswith("File:") else f"File:{title}"
    try:
        rows = _query({"titles": title})
    except Exception:  # noqa: BLE001
        return None
    return rows[0] if rows else None


def fetch(image: str | None = None, query: str | None = None) -> dict | None:
    """Download an image (by title, else the best match for a query) into the cache.

    Returns its row with `file` set, or None when nothing reusable was found.
    The row is cached next to the image, so a second compile is offline.
    """
    key = hashlib.md5(f"{image or ''}|{query or ''}".encode()).hexdigest()[:16]
    meta_path = CACHE / f"{key}.json"
    if meta_path.exists():
        row = json.loads(meta_path.read_text(encoding="utf-8"))
        if row and Path(row.get("file", "")).exists():
            return row
    row = lookup(image) if image else (search(query, 1) or [None])[0] if query else None
    if not row:
        return None
    suffix = Path(urllib.parse.urlparse(row["url"]).path).suffix.lower() or ".jpg"
    target = CACHE / f"{key}{suffix if suffix in ('.jpg', '.jpeg', '.png', '.webp') else '.jpg'}"
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_get(row["url"], timeout=60))
    except Exception:  # noqa: BLE001
        return None
    row["file"] = str(target)
    meta_path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    return row


def credit(rows) -> str:
    names = sorted({f"{r['title']} ({r['credit']})" for r in rows if r})
    return "Photos: " + "; ".join(names) if names else ""


if __name__ == "__main__":
    print(json.dumps({q: search(q) for q in sys.argv[1:]}, indent=1, ensure_ascii=False))
