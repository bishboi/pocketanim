"""A real photograph like a book's: the web's counterpart of a photo printed in the book (a scan, often small, grey
or blurred), for the lecture to show instead.

The book's photo is looked at by a vision model (harness/app/lib/figures.ts), which says what it shows in search
words ("Taj Mahal Agra front view white marble"). This finds candidates for those words -- Wikipedia's picture of
the subject, then Commons photographs (reusable licences only, never maps or logos) -- and keeps small copies, so
the model can compare them with the book's photo and pick the one most like it, or none. The pick is then fetched
at full size, with its credit.

    python lookalike.py candidates "<search words>" [--subject "<name>"] [--limit 8] --out DIR
        -> [{id, title, description, credit, license, thumb}]   (thumb: a small local copy)
    python lookalike.py fetch "<id>"
        -> {file, title, credit, license}   or null
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import images  # noqa: E402

PHOTO = re.compile(r"\.(?:jpe?g)(?:$|\?)", re.I)


def _small(url: str, width: int = 400) -> str:
    """A Commons thumbnail URL at another width (…/1600px-Name.jpg -> …/400px-Name.jpg)."""
    return re.sub(r"/\d+px-", f"/{width}px-", url)


def candidates(query: str, subject: str | None = None, limit: int = 8, out: Path | None = None) -> list[dict]:
    """Photographs for the search words (Wikipedia's picture of the subject first), each with a small local copy.
    Only photographs (JPEGs): a drawing or a chart is not the realistic picture wanted."""
    rows: list[dict] = []
    seen: set[str] = set()
    if subject:
        row = images.portrait(subject)
        if row and not images.is_map_row(row):
            rows.append(row)
            seen.add(row["id"])
    for row in images.search(query, limit=limit * 2):
        if row["id"] in seen or images.NOT_EDUCATIONAL.search(row.get("title", "")):
            continue
        seen.add(row["id"])
        rows.append(row)
    rows = [r for r in rows if PHOTO.search(str(r.get("url") or ""))][:limit]
    if out is None:
        return rows
    out.mkdir(parents=True, exist_ok=True)
    kept = []
    for row in rows:
        target = out / f"{hashlib.md5(row['id'].encode()).hexdigest()[:12]}.jpg"
        try:
            if not target.exists():
                target.write_bytes(images._get(_small(str(row["url"])), timeout=30))
        except Exception:  # noqa: BLE001 -- a candidate that will not download is left out
            continue
        kept.append({k: row.get(k) for k in ("id", "title", "description", "credit", "license")} | {"thumb": str(target)})
    return kept


def fetch(image_id: str) -> dict | None:
    """The chosen photograph at full size (cached), with its credit."""
    row = images.fetch(image=image_id)
    if not row or images.is_map_row(row):
        return None
    return {k: row.get(k) for k in ("file", "title", "credit", "license")}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("query")
    c.add_argument("--subject")
    c.add_argument("--limit", type=int, default=8)
    c.add_argument("--out", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("id")
    args = parser.parse_args()
    if args.cmd == "candidates":
        print(json.dumps(candidates(args.query, args.subject, args.limit, Path(args.out)), ensure_ascii=False))
    else:
        print(json.dumps(fetch(args.id), ensure_ascii=False))


if __name__ == "__main__":
    main()
