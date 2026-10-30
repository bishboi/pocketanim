"""The illustration library: pictures kept to be used again, before any is made by the image model.

    harness_v3/library/index.json      every picture: {id, file, title, tags, kind, source, license, credit, page,
                                       finished}
    harness_v3/library/files/          the pictures
    harness_v3/library/inbox/          drop your own illustrations here (a PNG, JPG or WebP; its file name says what it
                                       is: "a-farmer-ploughing-with-two-oxen.png"); they are taken in at the next run,
                                       or by `python engine/library.py import`

Where the pictures come from: your own (the inbox); illustrations found outside (Wikimedia Commons by default; Openverse
and Pixabay too: V3_LIBRARY_SOURCES), public domain or CC0 so the video needs no credit; and every picture the image
model makes, kept here so the next video that needs
the same thing uses it. A picture a score asks for is looked for here first (assets step, runs.py): the closest by
their words, and a vision model chooses the one that truly shows it (an illustration, never an icon), or none.

    python engine/library.py import            the inbox taken in
    python engine/library.py seed              every picture made before (the asset cache) taken in
    python engine/library.py search WORDS      what the library has for them
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "library"
INDEX = LIB / "index.json"
FILES = LIB / "files"
INBOX = LIB / "inbox"
ON = os.environ.get("V3_LIBRARY", "1").strip() != "0"
_lock = threading.RLock()

STOP = set("a an the of in on at to for with and or by from as is are was were be its it this that these those his her "
           "their our your one two three some any no not very small large big old new little whole each into over "
           "under near side seen view front top bottom plain white background cut out drawn drawing illustration "
           "picture image style hand painted".split())


def _words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z]+", str(text).lower()):
        if w in STOP or len(w) < 3:
            continue
        w = re.sub(r"(ies)$", "y", w)
        w = re.sub(r"(?<=[^s])s$", "", w)       # (plurals: oxen stays, coins -> coin)
        out.append(w)
    return out


def load() -> list[dict]:
    with _lock:
        if not INDEX.exists():
            return []
        try:
            return json.loads(INDEX.read_text())
        except ValueError:
            return []


def _save(rows: list[dict]) -> None:
    LIB.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=1))
    tmp.replace(INDEX)


def add(src, title: str, kind: str = "pic", tags: list[str] | None = None, source: str = "own",
        license: str = "", credit: str = "", page: str = "", finished: bool = False) -> dict:
    """A picture put in the library (a path, or a PIL image): its entry. The same picture twice is kept once."""
    from PIL import Image
    img = src if not isinstance(src, (str, Path)) else Image.open(src)
    img = img.convert("RGBA")
    h = hashlib.sha1(img.tobytes()).hexdigest()[:16]
    with _lock:
        rows = load()
        old = next((r for r in rows if r["id"] == h), None)
        if old:
            return old
        FILES.mkdir(parents=True, exist_ok=True)
        f = FILES / f"{h}.png"
        img.save(f)
        row = {"id": h, "file": f.name, "title": str(title).strip(), "tags": sorted(set(tags or [])), "kind": kind,
               "source": source, "license": license, "credit": credit, "page": page, "finished": finished,
               "added": time.time(), "size": list(img.size)}
        rows.append(row)
        _save(rows)
        return row


def path(row: dict) -> Path:
    return FILES / row["file"]


def search(query: str, kind: str = "pic", n: int = 6) -> list[dict]:
    """The library's pictures closest to the words (each word weighed by how rare it is in the library); only those
    sharing at least half the query's own words, best first."""
    rows = [r for r in load() if r.get("kind", "pic") == kind and path(r).exists()]
    q = list(dict.fromkeys(_words(query)))
    if not rows or not q:
        return []
    docs = [set(_words(r["title"] + " " + " ".join(r.get("tags", [])))) for r in rows]
    df = {w: sum(1 for d in docs if w in d) for w in q}
    idf = {w: math.log(1 + len(rows) / (1 + df[w])) for w in q}
    scored = []
    for r, d in zip(rows, docs):
        hit = [w for w in q if w in d]
        if len(hit) * 2 < min(len(q), 4):
            continue
        scored.append((sum(idf[w] for w in hit) / (1 + 0.05 * len(d)), r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:n]]


def take_inbox() -> list[dict]:
    """The inbox's pictures put in the library (named by their file names), then moved out of the inbox."""
    if not INBOX.exists():
        return []
    out = []
    done = INBOX / "taken"
    for f in sorted(INBOX.iterdir()):
        if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp") or not f.is_file():
            continue
        title = re.sub(r"[-_]+", " ", f.stem).strip()
        kind = "photo" if title.lower().startswith(("photo ", "scene ")) else "pic"
        try:
            out.append(add(f, title, kind, source="own", license="yours"))
            done.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), done / f.name)
        except Exception as e:  # noqa: BLE001 -- a file that is no picture: left where it is, said
            print(f"library: could not take {f.name}: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- outside sources -----------------------------------
# Where illustrations are searched for beyond the library (V3_LIBRARY_SOURCES, in order; each search kept on disk, so
# the same words never ask twice, and asked one at a time, politely):
#   commons     Wikimedia Commons (the default): drawings, engravings, paintings, illustrations; no key, no quota
#   openverse   Openverse (WordPress's search of open images: Rawpixel, museums, Flickr...): no key, 1 a second
#               (OPENVERSE_CLIENT_ID and OPENVERSE_CLIENT_SECRET for a registered app's higher rate)
#   pixabay     Pixabay's illustrations and vector art (PIXABAY_API_KEY)
# Only what needs no credit in the video (public domain, CC0; Pixabay's licence) unless V3_LIBRARY_FREE_ONLY=0.
SOURCES = [x.strip() for x in os.environ.get("V3_LIBRARY_SOURCES", "commons").split(",") if x.strip()]
FREE_ONLY = os.environ.get("V3_LIBRARY_FREE_ONLY", "1").strip() != "0"
SEEN = HERE.parent / ".cache" / "library-search"
_ask = threading.Lock()
_last = {"t": 0.0}


def _cached(name: str, query: str, fetch) -> list[dict]:
    """A source's answer for the words, from disk when asked before; asked one at a time, a second apart."""
    SEEN.mkdir(parents=True, exist_ok=True)
    f = SEEN / f"{name}-{hashlib.sha1(query.encode()).hexdigest()[:16]}.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except ValueError:
            pass
    with _ask:
        wait = 1.05 - (time.time() - _last["t"])
        if wait > 0:
            time.sleep(wait)
        try:
            out = fetch()
        except Exception as e:  # noqa: BLE001 -- the source is down or refused: nothing from it this time
            print(f"library: {name} search failed: {str(e)[:120]}", file=sys.stderr)
            out = None
        _last["t"] = time.time()
    if out is not None:
        f.write_text(json.dumps(out))
    return out or []


def _terms(query: str) -> list[str]:
    """The words a search is made of: what the thing is, in order (15th kept; small words left out)."""
    return [w for w in re.findall(r"[A-Za-z0-9]+", str(query).lower()) if w not in STOP and len(w) > 2]


def commons(query: str, kind: str = "pic", n: int = 6) -> list[dict]:
    """Wikimedia Commons' illustrations for the words: drawings, engravings, paintings. Every word must match
    there, so too few found is asked again with fewer: the longest (most telling) words."""
    terms = _terms(query)
    tries = [terms[:6], sorted(terms, key=len, reverse=True)[:3], sorted(terms, key=len, reverse=True)[:2]]
    out, seen = [], set()
    for t in tries:
        if not t:
            continue
        for c in _commons(" ".join(t), kind, n):
            if c["url"] not in seen:
                seen.add(c["url"])
                out.append(c)
        if len(out) >= max(2, n // 2):
            break
    return out[:n]


def _commons(q: str, kind: str, n: int) -> list[dict]:
    import assets

    def fetch():
        # drawings first (SVG illustrations, clean to cut out), then pictures (engravings, prints, paintings): the
        # vision model leaves out what is a photograph, an icon or a diagram
        pages = []
        for kind_ in (("drawing", "bitmap") if kind == "pic" else ("bitmap", "drawing")):
            d = json.loads(assets._get(assets.COMMONS, {
                "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                "gsrsearch": f"{q} filetype:{kind_}", "gsrlimit": n * 3, "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 640}))
            pages += sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        out, seen = [], set()
        for p in pages:
            if p.get("title") in seen:
                continue
            seen.add(p.get("title"))
            ii = (p.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata") or {}
            lic = assets._plain((meta.get("LicenseShortName") or {}).get("value", ""))
            free = bool(re.search(r"public domain|^pd|cc0|cc-zero", lic, re.I))
            if ii.get("mime") not in ("image/jpeg", "image/png", "image/svg+xml", "image/webp") or "fair" in lic.lower():
                continue
            if (FREE_ONLY and not free) or min(ii.get("width", 0), ii.get("height", 0)) < 300:
                continue
            big = ii.get("thumburl", "").replace("/640px-", "/1280px-") if ii.get("width", 0) >= 1280 else ii.get("thumburl")
            out.append({"url": ii.get("thumburl") or ii.get("url"), "large": big or ii.get("url"),
                        "title": re.sub(r"^File:|\.\w+$", "", p.get("title", "")).replace("_", " "),
                        "tags": [], "page": ii.get("descriptionurl", ""), "license": lic,
                        "user": assets._plain((meta.get("Artist") or {}).get("value", ""))[:120], "source": "commons",
                        "free": free})
            if len(out) >= n:
                break
        return out
    return _cached("commons2", f"{kind}|{q}|{FREE_ONLY}", fetch)


def _openverse_token() -> str | None:
    cid, sec = os.environ.get("OPENVERSE_CLIENT_ID", ""), os.environ.get("OPENVERSE_CLIENT_SECRET", "")
    if not (cid and sec):
        return None
    import urllib.request
    req = urllib.request.Request("https://api.openverse.org/v1/auth_tokens/token/", method="POST",
                                 data=urllib.parse.urlencode({"client_id": cid, "client_secret": sec,
                                                              "grant_type": "client_credentials"}).encode(),
                                 headers={"User-Agent": "pocketanim-harness/3.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("access_token")


def openverse(query: str, kind: str = "pic", n: int = 6) -> list[dict]:
    """Openverse's illustrations for the words (public domain and CC0 unless V3_LIBRARY_FREE_ONLY=0)."""
    import urllib.request
    q = " ".join(_words(query)[:6]) or query

    def fetch():
        params = {"q": q, "category": "illustration,digitized_artwork", "page_size": min(20, n * 2)}
        params["license"] = "cc0,pdm" if FREE_ONLY else "cc0,pdm,by,by-sa"
        headers = {"User-Agent": "pocketanim-harness/3.0 (https://github.com/bishboi/pocketanim)"}
        tok = _openverse_token()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        req = urllib.request.Request("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params),
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
        return [{"url": x.get("thumbnail") or x.get("url"), "large": x.get("url"), "title": x.get("title") or q,
                 "tags": [t.get("name", "") for t in x.get("tags") or []][:12], "page": x.get("foreign_landing_url", ""),
                 "license": f"{x.get('license', '')} {x.get('license_version', '')}".strip(),
                 "user": x.get("creator") or "", "source": "openverse",
                 "free": x.get("license") in ("cc0", "pdm")} for x in d.get("results") or []][:n]
    return _cached("openverse", f"{kind}|{q}|{FREE_ONLY}", fetch)


def pixabay(query: str, kind: str = "pic", n: int = 6) -> list[dict]:
    """Pixabay's illustrations and vector art for the words (PIXABAY_API_KEY; none without it)."""
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    import assets
    q = " ".join(_words(query)[:6]) or query

    def fetch():
        out = []
        for image_type in (("vector", "illustration") if kind == "pic" else ("illustration",)):
            url = "https://pixabay.com/api/?" + urllib.parse.urlencode(
                {"key": key, "q": q[:95], "image_type": image_type, "safesearch": "true", "per_page": max(3, n),
                 "order": "popular"})
            for h in json.loads(assets._get(url)).get("hits") or []:
                out.append({"url": h.get("webformatURL") or h.get("previewURL"),
                            "large": h.get("largeImageURL") or h.get("webformatURL"), "title": h.get("tags", ""),
                            "tags": [t.strip() for t in str(h.get("tags", "")).split(",")],
                            "page": h.get("pageURL", ""), "user": h.get("user", ""), "source": "pixabay",
                            "license": "Pixabay Content License", "free": True})
        return out
    return _cached("pixabay", f"{kind}|{q}", fetch)[:n]


def outside(query: str, kind: str = "pic", n: int = 4) -> list[dict]:
    """The outside sources' candidates for the words, in V3_LIBRARY_SOURCES' order (and Pixabay when its key is set)."""
    found = {"commons": commons, "openverse": openverse, "pixabay": pixabay}
    names = SOURCES + (["pixabay"] if os.environ.get("PIXABAY_API_KEY") and "pixabay" not in SOURCES else [])
    out = []
    for name in names:
        if name in found and len(out) < n:
            out += found[name](query, kind, n - len(out))
    return out[:n]


CHOOSE = """You choose pictures for an animated explainer video drawn as illustrations (hand-drawn or flat
illustration, cut-out objects and people on a paper background). You see numbered candidates and the words of the
picture wanted. Answer the number of the candidate that truly shows that thing, as an illustration of the right kind,
time and place (a 15th-century press, not a modern one; an Indian village, not a European one); never an icon, a
logo, a symbol, a diagram or a photograph (for a scene, a painted or drawn scene). If none truly fits, answer `none`.
Only the number, or `none`."""


def choose_prompt(words: str, n: int) -> tuple[str, str]:
    return CHOOSE, f"THE PICTURE WANTED: {words}\nCANDIDATES: 1 to {n}, in order."


def seed() -> int:
    """Every picture the image model has made before (the asset cache, with the words it was made from) taken in."""
    import assets
    n = 0
    for p in sorted(assets.CACHE.glob("*.png")):
        kind = p.name.split("-", 1)[0]
        said = p.with_suffix(".prompt.txt")
        if kind not in ("pic", "photo") or not said.exists():
            continue
        try:
            add(p, said.read_text().strip()[:300], kind, source="made", license="made for this harness", finished=True)
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "seed":
        print(f"{seed()} picture(s) made before taken in; {len(load())} in the library")
    elif len(sys.argv) >= 2 and sys.argv[1] == "import":
        for r in take_inbox():
            print(f"taken: {r['title']} ({r['kind']})")
        print(f"{len(load())} picture(s) in the library")
    elif len(sys.argv) >= 3 and sys.argv[1] == "search":
        for r in search(" ".join(sys.argv[2:])):
            print(f"{r['id']}  {r['source']:8} {r['title'][:90]}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
