"""Photos and illustrations from Wikimedia Commons, for lectures.

Only files whose licence lets a video reuse them are returned (public domain,
CC0, CC BY, CC BY-SA), each with the credit line it needs. A lecture names an
image by its Commons title ("File:Sugarcane field.jpg") or by a search query;
the compiler downloads it once into .cache/images and the scene draws the
local file, so a render never waits on the network.

    python harness/lecture/images.py "sugarcane field" "Ganges at Varanasi"    # search, as JSON
    python harness/lecture/images.py --illustrations "water cycle" "leaf cross section"

A named subject -- a person, a movement, a monument, an event, a place -- is
looked up on Wikipedia first (`portrait`): the picture its article leads with is
the one people know it by. That picture is used only when it lives on Commons
under a reusable licence (Wikipedia's local non-free posters and logos are not).
Hindi names are looked up on Hindi Wikipedia and followed to English.

PANIM_IMAGES=0 turns internet images off (a lecture then draws its stage
from icons and document figures only). COMMONS_API and WIKIPEDIA_API ("{lang}"
stands for the language) override the endpoints.
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


def _row(page: dict, drawings: bool = False) -> dict | None:
    info = (page.get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata") or {}
    licence = _text((meta.get("LicenseShortName") or {}).get("value"))
    if not ALLOWED.match(licence):
        return None
    svg = info.get("mime") == "image/svg+xml"
    if info.get("mime") not in ("image/jpeg", "image/png", "image/webp") and not (drawings and svg):
        return None
    # An SVG diagram is fetched as Commons' PNG rendering at 1600 px, whatever its nominal size.
    if (info.get("width") or 0) < 640 and not svg:
        return None
    if svg and not info.get("thumburl"):
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


def _query(params: dict, drawings: bool = False) -> list[dict]:
    base = {"action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "1600"}
    data = json.loads(_get(f"{api()}?{urllib.parse.urlencode({**base, **params})}"))
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return [row for row in (_row(p, drawings) for p in pages) if row]


def wiki_api(lang: str) -> str:
    return os.environ.get("WIKIPEDIA_API", "https://{lang}.wikipedia.org/w/api.php").replace("{lang}", lang)


def _wiki(lang: str, params: dict) -> dict:
    query = urllib.parse.urlencode({"format": "json", "formatversion": "2", **params})
    return json.loads(_get(f"{wiki_api(lang)}?{query}", timeout=15))


def _tokens(text: str) -> set[str]:
    """Words, lower-cased and singular (tractors -> tractor, species kept), for matching a title to a query."""
    words = re.findall(r"[\w\u0900-\u097F]+", str(text).lower())
    return {re.sub(r"(?<=[a-z]{3})(ies|es|s)$", "", w) if not w.endswith("ss") else w for w in words}


def _article(name: str, lang: str) -> dict | None:
    """{title, image, en} for the article a name means: the exact title (or a redirect), else the top search hit
    whose title shares most of the name's words."""
    params = {"action": "query", "prop": "pageimages|langlinks", "piprop": "name", "lllang": "en", "redirects": "1"}
    pages = (_wiki(lang, {**params, "titles": name}).get("query") or {}).get("pages") or []
    page = next((p for p in pages if not p.get("missing") and not p.get("invalid")), None)
    if page is None:
        hits = (_wiki(lang, {"action": "query", "list": "search", "srsearch": name, "srlimit": "3"})
                .get("query") or {}).get("search") or []
        want = _tokens(name)
        for hit in hits:
            if want and len(want & _tokens(hit["title"])) >= max(1, (len(want) + 1) // 2):
                pages = (_wiki(lang, {**params, "titles": hit["title"]}).get("query") or {}).get("pages") or []
                page = next((p for p in pages if not p.get("missing")), None)
                break
    if page is None:
        return None
    english = next((l.get("title") for l in page.get("langlinks") or [] if l.get("lang") == "en"), None)
    return {"title": page["title"], "image": page.get("pageimage"), "en": english}


def portrait(name: str) -> dict | None:
    """The picture Wikipedia's article on `name` leads with, if Commons has it under a reusable licence.

    For a person that is their portrait, for a movement its best-known photo,
    for a monument or place its photograph. None when offline, when there is
    no such article, or when its picture is not freely reusable.
    """
    if not enabled() or not str(name).strip():
        return None
    devanagari = bool(re.search(r"[\u0900-\u097F]", str(name)))
    try:
        article = _article(str(name).strip(), "hi" if devanagari else "en")
        if article and not article["image"] and article.get("en"):
            article = _article(article["en"], "en") or article      # a Hindi article without a picture
    except Exception:  # noqa: BLE001 -- offline or blocked: the lecture falls back to Commons search and icons
        return None
    if not article or not article.get("image"):
        return None
    row = lookup(article["image"])
    if row:
        row["subject"] = article["title"]
        row["source"] = "wikipedia"
    return row


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


# ---------------- educational illustrations and diagrams ----------------
# Not pictures of a subject but pictures that explain one: a labelled diagram of the water cycle, a cross-section of
# a leaf, a food web. Wikimedia Commons holds tens of thousands (SVG drawings and bitmap diagrams from textbooks,
# encyclopaedias and teachers); Openverse adds openly licensed illustrations from other collections.
NOT_EDUCATIONAL = re.compile(r"\b(logo|flag|coat of arms|emblem|seal|icon|signature|stamp|banner|wordmark|"
                             r"button|symbol|pictogram|clip ?art|cartoon|meme|screenshot)\b", re.I)
TEACHING = re.compile(r"\b(diagram|illustration|labell?ed|cycle|structure|process|cross[- ]section|anatomy|"
                      r"schematic|infographic|model|chart|web|layers?|parts|stages?)\b", re.I)


def openverse_api() -> str:
    return os.environ.get("OPENVERSE_API", "https://api.openverse.org/v1/images/")


OPENVERSE_LICENCES = {"cc0": "CC0", "pdm": "Public domain", "by": "CC BY", "by-sa": "CC BY-SA"}


def _openverse(query: str, limit: int = 8) -> list[dict]:
    """Openly licensed illustrations from Openverse (reusable licences only)."""
    params = {"q": query, "category": "illustration,digitized_artwork", "license": ",".join(OPENVERSE_LICENCES),
              "page_size": str(limit), "mature": "false"}
    data = json.loads(_get(f"{openverse_api()}?{urllib.parse.urlencode(params)}", timeout=15))
    rows = []
    for r in data.get("results") or []:
        licence = OPENVERSE_LICENCES.get(str(r.get("license", "")).lower())
        if not licence or (r.get("width") or 0) < 640 or not r.get("url"):
            continue
        if licence.startswith("CC BY"):
            licence += f" {r.get('license_version') or ''}".rstrip()
        artist = str(r.get("creator") or "unknown author")[:80]
        source = str(r.get("source") or r.get("provider") or "Openverse")
        rows.append({"id": f"openverse:{r.get('id')}", "title": str(r.get("title") or query)[:120],
                     "description": str(r.get("title") or "")[:200], "width": r.get("width"),
                     "height": r.get("height"), "url": r["url"], "license": licence, "artist": artist,
                     "credit": f"{artist[:60]}, {licence}, via {source} (Openverse)"})
    return rows


def illustrations(query: str, limit: int = 6, genre: str | None = None, style: str | None = None) -> list[dict]:
    """Educational illustrations and diagrams for a topic, best first, from the sources that suit the subject
    (illustrations.py: textbook figures, NASA, museums, Commons, Openverse). [] when offline or disabled."""
    import illustrations as _sources

    return _sources.find(query, genre=genre, limit=limit, style=style)


def commons_openverse(query: str, limit: int = 6) -> list[dict]:
    """Commons drawings (SVG, rendered to PNG), then Commons bitmap diagrams, then Openverse. Reusable
    licences only; ranked by how well each title matches the topic."""
    if not enabled() or not str(query).strip():
        return []
    rows: list[dict] = []
    searches = [({"gsrsearch": f"{query} filetype:drawing"}, True),
                ({"gsrsearch": f"{query} diagram filetype:bitmap"}, False)]
    for params, drawings in searches:
        try:
            rows += _query({"generator": "search", "gsrnamespace": "6", "gsrlimit": "24", **params}, drawings)
        except Exception:  # noqa: BLE001 -- offline or blocked: try the next source
            pass
    try:
        rows += _openverse(query)
    except Exception:  # noqa: BLE001
        pass
    want = _tokens(query)

    def score(index_row) -> float:
        index, row = index_row
        title = f"{row['title']} {row.get('description', '')}"
        overlap = len(want & _tokens(title)) / max(len(want), 1)
        return overlap * 3 + (1.0 if TEACHING.search(title) else 0.0) - index * 0.02

    seen, ranked = set(), []
    for _, row in sorted(enumerate(rows), key=score, reverse=True):
        if row["id"] in seen or NOT_EDUCATIONAL.search(row["title"]):
            continue
        if want and not want & _tokens(f"{row['title']} {row.get('description', '')}"):
            continue            # shares no word with the topic: a search engine's guess, not a diagram of it
        seen.add(row["id"])
        row["source"] = row.get("source") or "illustration"
        ranked.append(row)
    return ranked[:limit]


MISSES = CACHE / "_misses.json"


def _missed(key: str, add: bool = False) -> bool:
    """Subjects already looked up and not found, so a recompile does not ask the network again."""
    try:
        misses = json.loads(MISSES.read_text(encoding="utf-8")) if MISSES.exists() else []
    except ValueError:
        misses = []
    if add and key not in misses:
        CACHE.mkdir(parents=True, exist_ok=True)
        MISSES.write_text(json.dumps(misses[-5000:] + [key], ensure_ascii=False), encoding="utf-8")
    return key in misses


def fetch(image: str | None = None, query: str | None = None, subject: str | None = None,
          illustration: str | None = None, avoid: set | None = None, genre: str | None = None,
          style: str | None = None) -> dict | None:
    """Download an image into the cache: by Commons title, else the Wikipedia picture of a subject (falling back
    to a Commons search for it), else the best match for a query.

    Returns its row with `file` set, or None when nothing reusable was found.
    The row is cached next to the image, so a second compile is offline.
    """
    key = hashlib.md5(f"{image or ''}|{query or ''}|{subject or ''}|{illustration or ''}".encode()).hexdigest()[:16]
    meta_path = CACHE / f"{key}.json"
    if meta_path.exists():
        row = json.loads(meta_path.read_text(encoding="utf-8"))
        if row and Path(row.get("file", "")).exists() and row.get("id") not in (avoid or set()):
            return row
    if (subject or illustration) and not image and _missed(key):
        return None
    if image:
        row = lookup(image)
    elif illustration:
        # `avoid`: pictures the lecture already showed, so one diagram does not stand in for every topic.
        row = next((r for r in illustrations(illustration, genre=genre, style=style) if r["id"] not in (avoid or set())), None)
    elif subject:
        row = portrait(subject) or (search(subject, 1) or [None])[0]
    else:
        row = (search(query, 1) or [None])[0] if query else None
    if not row:
        if (subject or illustration) and enabled():
            _missed(key, add=True)
        return None
    if row.get("path"):
        # A local collection's own file (a downloaded pack) or an image already written (AI): used where it is.
        row["file"] = str(row["path"])
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
        return row
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


def find(query: str, limit: int = 6) -> list[dict]:
    """What find_image offers: Wikipedia's picture of the query when it names something, then Commons results."""
    rows = [r for r in [portrait(query)] if r]
    seen = {r["id"] for r in rows}
    return (rows + [r for r in search(query, limit) if r["id"] not in seen])[:limit]


if __name__ == "__main__":
    if sys.argv[1:2] == ["--illustrations"]:
        args = sys.argv[2:]
        genre = None
        if "--genre" in args:
            at = args.index("--genre")
            genre = args[at + 1] if at + 1 < len(args) else None
            del args[at:at + 2]
        print(json.dumps({q: illustrations(q, genre=genre) for q in args}, indent=1, ensure_ascii=False))
    else:
        print(json.dumps({q: find(q) for q in sys.argv[1:]}, indent=1, ensure_ascii=False))
