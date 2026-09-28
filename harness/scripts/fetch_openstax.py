"""Index the figures of OpenStax's free textbooks, so lectures can show real textbook diagrams.

OpenStax publishes every book's source on GitHub (github.com/openstax/osbooks-*): pages as CNXML with
each figure's image, alt text and caption. This reads them and writes one searchable collection per book
under harness/lecture/data/illustrations/openstax-<book>/ -- captions and image URLs only; an image is
downloaded the first time a lecture shows it.

Licences: most OpenStax books are CC BY-NC-SA 4.0 (non-commercial, share-alike); a few are CC BY 4.0.
Non-commercial books are left out unless you pass --non-commercial, and even then a lecture uses them only
with PANIM_ALLOW_NC=1 (see harness/SETUP.md). Figures whose caption credits someone else (a photographer, an
agency) carry that person's licence rather than OpenStax's, so they are skipped: what remains are
OpenStax's own drawings and diagrams.

    .venv/bin/python harness/scripts/fetch_openstax.py                   # the CC BY books
    .venv/bin/python harness/scripts/fetch_openstax.py --non-commercial  # every book (for non-commercial use)
    .venv/bin/python harness/scripts/fetch_openstax.py --books physics,biology-2e
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAW = os.environ.get("OPENSTAX_RAW", "https://raw.githubusercontent.com/openstax")
TARGET = Path(__file__).resolve().parents[1] / "lecture" / "data" / "illustrations"
# The book repositories (each may hold several books: META-INF/books.xml lists them).
REPOS = ["osbooks-physics", "osbooks-biology-bundle", "osbooks-chemistry-bundle", "osbooks-college-physics-bundle",
         "osbooks-university-physics-bundle", "osbooks-astronomy", "osbooks-anatomy-physiology",
         "osbooks-microbiology", "osbooks-principles-economics-bundle", "osbooks-us-history", "osbooks-world-history",
         "osbooks-introduction-sociology", "osbooks-psychology", "osbooks-american-government"]
UA = "pocketanim-lecture/0.6 (educational lectures; https://github.com/bishboi/pocketanim)"

FIGURE = re.compile(r"<figure\b[^>]*>(.*?)</figure>", re.S)
ALT = re.compile(r'<media\b[^>]*\balt="([^"]*)"', re.S)
IMAGE = re.compile(r'<image\b[^>]*\bsrc="(?:\.\./)*media/([^"]+)"', re.S)
CAPTION = re.compile(r"<caption>(.*?)</caption>", re.S)
TITLE = re.compile(r"<title>(.*?)</title>", re.S)
# A caption crediting someone else: "(credit: ...)", or a trailing "(Name/Source)" as OpenStax writes them.
THIRD_PARTY = re.compile(r"\(\s*credit|\([^()]*(/|Flickr|Wikimedia|NASA|NOAA|USGS|Getty|Shutterstock)[^()]*\)\s*$", re.I)


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _licence(url: str) -> tuple[str, bool]:
    """('CC BY 4.0', non_commercial) from a Creative Commons licence URL."""
    m = re.search(r"licenses/([a-z-]+)/([\d.]+)", url)
    if not m:
        return "see book", True
    kind, version = m.groups()
    return f"CC {kind.upper()} {version}", "nc" in kind


def figures_of(repo: str, module: str) -> tuple[str, list[dict]]:
    """(page title, [{title, caption, alt, url}]) for one page of a book."""
    try:
        text = _get(f"{RAW}/{repo}/main/modules/{module}/index.cnxml")
    except Exception:  # noqa: BLE001 -- a page that will not load is skipped, not fatal
        return "", []
    page = _text((TITLE.search(text) or [None, ""])[1]) if TITLE.search(text) else ""
    out = []
    for block in FIGURE.findall(text):
        image = IMAGE.search(block)
        if not image or not image.group(1).lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        caption = _text((CAPTION.search(block) or [None, ""])[1]) if CAPTION.search(block) else ""
        if THIRD_PARTY.search(caption):
            continue
        alt = html.unescape((ALT.search(block) or [None, ""])[1]) if ALT.search(block) else ""
        out.append({"title": caption[:120] or alt[:120], "caption": caption, "alt": alt, "page": page,
                    "url": f"{RAW}/{repo}/main/media/{image.group(1)}"})
    return page, out


def index_book(repo: str, href: str, slug: str, non_commercial: bool) -> dict | None:
    collection = _get(f"{RAW}/{repo}/main/{href}")
    licence_url = (re.search(r'<md:license url="([^"]+)"', collection) or [None, ""])[1]
    licence, nc = _licence(licence_url)
    title = _text((re.search(r"<md:title>(.*?)</md:title>", collection) or [None, slug])[1])
    if nc and not non_commercial:
        return {"book": slug, "title": title, "license": licence, "skipped": "non-commercial licence"}
    modules = re.findall(r'<col:module document="(m\d+)"', collection)
    rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for _page, figures in pool.map(lambda m: figures_of(repo, m), modules):
            rows.extend(figures)
    folder = TARGET / f"openstax-{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "collection.json").write_text(json.dumps({
        "name": f"OpenStax {title}", "source": "openstax", "license": licence, "non_commercial": nc,
        "credit": f"OpenStax, {title}, {licence}", "url": f"https://openstax.org/details/books/{slug}",
    }, indent=1), encoding="utf-8")
    (folder / "index.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return {"book": slug, "title": title, "license": licence, "pages": len(modules), "figures": len(rows)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--non-commercial", action="store_true", help="also index CC BY-NC-SA books")
    ap.add_argument("--books", help="only these book slugs, comma-separated (e.g. physics,biology-2e)")
    args = ap.parse_args()
    wanted = {b.strip() for b in args.books.split(",")} if args.books else None
    failed = 0
    for repo in REPOS:
        try:
            books = re.findall(r'<book slug="([^"]+)"[^>]*href="\.\./([^"]+)"', _get(f"{RAW}/{repo}/main/META-INF/books.xml"))
        except Exception as error:  # noqa: BLE001
            print(f"{repo}: {error}", file=sys.stderr)
            failed += 1
            continue
        for slug, href in books:
            if wanted and slug not in wanted:
                continue
            try:
                row = index_book(repo, href, slug, args.non_commercial)
            except Exception as error:  # noqa: BLE001
                print(f"{slug}: {error}", file=sys.stderr)
                failed += 1
                continue
            if row.get("skipped"):
                print(f"{slug:40} {row['license']:16} skipped ({row['skipped']}; --non-commercial to include)")
            else:
                print(f"{slug:40} {row['license']:16} {row['figures']:5} figures from {row['pages']} pages", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
