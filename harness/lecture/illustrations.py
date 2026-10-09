"""Educational illustrations for lectures: where each subject's best pictures come from.

A lecture needs pictures that explain -- a labelled diagram, a textbook figure, a museum object, a satellite
view -- and no single library has them all. `find(query, genre)` asks the sources that suit the subject, in
order, and returns reusable pictures only, each with the credit its licence asks for:

    local      collections on disk (harness/lecture/data/illustrations/<name>/): OpenStax textbook figures
               (fetch_openstax.py) and any pack you download and drop in (NIH BioArt, Servier Medical Art...)
    nasa       NASA Image and Video Library: earth, weather, climate, space (NASA media is not copyrighted)
    met        The Metropolitan Museum of Art: public-domain objects, paintings, manuscripts (CC0)
    smithsonian  Smithsonian Open Access: museum objects and documents marked CC0
    storyweaver  Pratham Books' StoryWeaver: thousands of illustrations by Indian illustrators of Indian life
               (villages, farms, markets, festivals, families, schools, animals), CC BY 4.0
    commons    Wikimedia Commons: SVG drawings and bitmap diagrams (public domain, CC0, CC BY, CC BY-SA)
    openverse  openly licensed illustrations from other collections
    ai         an illustration drawn for the beat by an image model through OpenRouter, last, when nothing
               else fits (OPENROUTER_API_KEY; PANIM_AI_ILLUSTRATIONS=0 turns it off)

Non-commercial collections (most OpenStax books are CC BY-NC-SA) are used only with PANIM_ALLOW_NC=1.

    .venv/bin/python harness/lecture/illustrations.py "water cycle" --genre geography
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import urllib.parse
from functools import lru_cache
from pathlib import Path

import images
from images import CACHE, _get, _tokens, enabled

HERE = Path(__file__).resolve().parent
LOCAL = Path(os.environ.get("PANIM_ILLUSTRATIONS_DIR") or (HERE / "data" / "illustrations"))

# Which sources a subject asks first. Commons and Openverse cover everything; the AI is the last resort.
ROUTES = {
    "biology": ["local", "commons", "openverse", "storyweaver", "ai"],
    "chemistry": ["local", "commons", "openverse", "ai"],
    "physics": ["local", "nasa", "commons", "openverse", "ai"],
    "mathematics": ["local", "commons", "openverse", "ai"],
    "economics": ["local", "storyweaver", "commons", "openverse", "ai"],
    "geography": ["local", "nasa", "storyweaver", "commons", "openverse", "ai"],
    "history": ["met", "smithsonian", "local", "storyweaver", "commons", "openverse", "ai"],
    "general": ["local", "storyweaver", "commons", "openverse", "met", "ai"],
}
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp")


def allow_nc() -> bool:
    return os.environ.get("PANIM_ALLOW_NC", "0") == "1"


SMALL = set("a an the of and or in on at to for with by from as is are its it this that into about how what why".split())


def _overlap(query: str, text: str) -> float:
    """The share of the query's meaningful words that the text contains."""
    want = _tokens(query) - SMALL
    return len(want & _tokens(text)) / max(len(want), 1)


# ---------------- local collections ----------------
@lru_cache(None)
def _collections() -> tuple:
    """(collection meta, rows) for each collection on disk; a folder of images without an index is indexed by
    its file names."""
    out = []
    if not LOCAL.is_dir():
        return ()
    for folder in sorted(p for p in LOCAL.iterdir() if p.is_dir()):
        meta_file = folder / "collection.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
        meta.setdefault("name", folder.name)
        meta.setdefault("license", "see collection")
        meta.setdefault("credit", meta["name"])
        index = folder / "index.json"
        if index.exists():
            rows = json.loads(index.read_text(encoding="utf-8"))
        else:
            rows = [{"title": re.sub(r"[-_]+", " ", p.stem), "caption": "", "alt": "", "file": str(p.relative_to(folder))}
                    for p in sorted(folder.rglob("*")) if p.suffix.lower() in IMAGE_TYPES]
        out.append((meta, folder, rows))
    return tuple(out)


def local(query: str, limit: int = 6) -> list[dict]:
    """Pictures from the collections on disk whose caption, alt text or file name matches the query."""
    found = []
    for meta, folder, rows in _collections():
        if meta.get("non_commercial") and not allow_nc():
            continue
        for index, row in enumerate(rows):
            text = f"{row.get('title', '')} {row.get('caption', '')} {row.get('alt', '')}"
            match = _overlap(query, text)
            if match < 0.6:            # most of the query's words in the caption, alt text or name
                continue
            score = match * 2 + _overlap(query, row.get("page", "")) * 0.5 \
                + (0.3 if images.TEACHING.search(text) else 0.0)
            item = {"id": f"{folder.name}:{row.get('file') or row.get('url')}", "title": row.get("title", "")[:120],
                    "description": (row.get("caption") or row.get("alt") or "")[:200], "width": 1600, "height": 1000,
                    "license": meta["license"], "artist": meta["name"], "credit": meta["credit"],
                    "source": meta.get("source", "local"), "score": score}
            if row.get("file"):
                item["path"] = str(folder / row["file"])
            else:
                item["url"] = row["url"]
            found.append(item)
    found.sort(key=lambda r: -r["score"])
    return found[:limit]


# ---------------- NASA ----------------
def nasa(query: str, limit: int = 6) -> list[dict]:
    """NASA Image and Video Library. NASA's own media is not copyrighted; anything marked as someone else's is
    skipped."""
    api = os.environ.get("NASA_IMAGES_API", "https://images-api.nasa.gov")
    data = json.loads(_get(f"{api}/search?{urllib.parse.urlencode({'q': query, 'media_type': 'image'})}", timeout=15))
    rows = []
    for item in (data.get("collection") or {}).get("items") or []:
        meta = (item.get("data") or [{}])[0]
        text = f"{meta.get('title', '')} {meta.get('description', '')}"
        if re.search(r"©|copyright|courtesy of (?!nasa)", text, re.I):
            continue
        links = [link.get("href", "") for link in item.get("links") or []]
        href = next((h for h in links if "~large." in h), None) or next((h for h in links if "~medium." in h), None) \
            or next((h for h in links if "~orig." in h), None) or next((h for h in links if h), None)
        if not href:
            continue
        who = meta.get("photographer") or meta.get("secondary_creator") or meta.get("center") or "NASA"
        rows.append({"id": f"nasa:{meta.get('nasa_id')}", "title": str(meta.get("title", ""))[:120],
                     "description": str(meta.get("description", ""))[:200], "width": 1600, "height": 1000,
                     "url": href, "license": "Public domain (NASA)", "artist": who,
                     "credit": f"NASA ({who})" if who != "NASA" else "NASA", "source": "nasa"})
        if len(rows) >= limit:
            break
    return rows


# ---------------- museums ----------------
def met(query: str, limit: int = 6) -> list[dict]:
    """The Met's public-domain objects (CC0): paintings, manuscripts, arms, coins, maps."""
    api = os.environ.get("MET_API", "https://collectionapi.metmuseum.org/public/collection/v1")
    found = json.loads(_get(f"{api}/search?{urllib.parse.urlencode({'hasImages': 'true', 'q': query})}", timeout=15))
    rows = []
    for object_id in (found.get("objectIDs") or [])[: limit * 3]:
        try:
            obj = json.loads(_get(f"{api}/objects/{object_id}", timeout=15))
        except Exception:  # noqa: BLE001
            continue
        if not obj.get("isPublicDomain") or not obj.get("primaryImage"):
            continue
        who = obj.get("artistDisplayName") or obj.get("culture") or "The Met"
        title = " ".join(x for x in (obj.get("title"), obj.get("objectDate")) if x)
        rows.append({"id": f"met:{object_id}", "title": str(title)[:120],
                     "description": str(obj.get("objectName") or obj.get("title") or "")[:200],
                     "width": 1600, "height": 1000, "url": obj["primaryImage"], "license": "CC0",
                     "artist": who, "credit": f"{who}, The Metropolitan Museum of Art (CC0)", "source": "met"})
        if len(rows) >= limit:
            break
    return rows


def smithsonian(query: str, limit: int = 6) -> list[dict]:
    """Smithsonian Open Access: only media marked CC0. Uses SMITHSONIAN_API_KEY (an api.data.gov key; DEMO_KEY
    works for a few searches an hour)."""
    api = os.environ.get("SMITHSONIAN_API", "https://api.si.edu/openaccess/api/v1.0")
    key = os.environ.get("SMITHSONIAN_API_KEY") or os.environ.get("DATA_GOV_API_KEY") or "DEMO_KEY"
    data = json.loads(_get(f"{api}/search?{urllib.parse.urlencode({'q': query, 'rows': str(limit * 3), 'api_key': key})}",
                           timeout=15))
    rows = []
    for row in (data.get("response") or {}).get("rows") or []:
        content = row.get("content") or {}
        described = content.get("descriptiveNonRepeating") or {}
        media = ((described.get("online_media") or {}).get("media")) or []
        picture = next((m for m in media if m.get("type") == "Images" and (m.get("usage") or {}).get("access") == "CC0"
                        and m.get("content")), None)
        if not picture:
            continue
        museum = described.get("data_source") or "Smithsonian Institution"
        rows.append({"id": f"si:{row.get('id')}", "title": str(row.get("title", ""))[:120],
                     "description": str(row.get("title", ""))[:200], "width": 1600, "height": 1000,
                     "url": picture["content"], "license": "CC0", "artist": museum,
                     "credit": f"{museum}, Smithsonian Open Access (CC0)", "source": "smithsonian"})
        if len(rows) >= limit:
            break
    return rows


# ---------------- StoryWeaver: Indian illustrators ----------------
def storyweaver(query: str, limit: int = 6) -> list[dict]:
    """Illustrations from Pratham Books' StoryWeaver, drawn by Indian illustrators for children's books: a
    village well, a farmer with oxen, a Diwali market, a classroom. Every one is CC BY 4.0, CC BY 3.0, CC0 or
    public domain; credited as CC BY 4.0, the strictest of them."""
    api = os.environ.get("STORYWEAVER_API", "https://storyweaver.org.in/api/v1")
    params = urllib.parse.urlencode({"query": query, "page": 1, "per_page": limit * 2})
    data = json.loads(_get(f"{api}/illustrations-search?{params}", timeout=15))
    rows = []
    for item in data.get("data") or []:
        sizes = [s for s in ((item.get("imageUrls") or [{}])[0].get("sizes") or []) if s.get("url")]
        if not sizes:
            continue
        size = max(sizes, key=lambda s: s.get("width") or 0)          # "large" before "search"
        url = urllib.parse.urljoin(api, size["url"])
        who = ", ".join(str(i.get("name")) for i in item.get("illustrators") or [] if isinstance(i, dict) and i.get("name"))
        publisher = (item.get("publisher") or {}).get("name") or "StoryWeaver"
        title = str(item.get("title") or query)
        rows.append({"id": f"sw:{item.get('id') or item.get('slug')}", "title": title[:120], "description": title[:200],
                     "width": size.get("width") or 1200, "height": size.get("height") or 900, "url": url,
                     "license": "CC BY 4.0", "artist": who or publisher,
                     "credit": f"{who + ', ' if who else ''}{publisher}, StoryWeaver (CC BY 4.0)", "source": "storyweaver"})
        if len(rows) >= limit:
            break
    return rows


# ---------------- an AI illustration, last ----------------
AI_MADE = {"count": 0, "usd": 0.0, "items": []}


def ai_enabled() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY")) and os.environ.get("PANIM_AI_ILLUSTRATIONS", "1") != "0"


def ai(query: str, limit: int = 1, style: str | None = None) -> list[dict]:
    """An illustration drawn for the topic by an image model (OpenRouter). Clean, textbook-like, no text in the
    image (labels in a generated picture come out garbled). At most PANIM_AI_MAX (6) a process, so a lecture's
    cost stays small. Never a real person's face: people and places come from Wikipedia and museums. Never a map."""
    if not ai_enabled() or AI_MADE["count"] >= int(os.environ.get("PANIM_AI_MAX", "6")):
        return []
    import mapguard

    if mapguard.is_map(query):
        return []                   # an image model's map is a guess at the world; maps are drawn on the map
    model = os.environ.get("PANIM_IMAGE_MODEL", "google/gemini-2.5-flash-image")
    key = hashlib.md5(f"{model}|{style}|{query}".encode()).hexdigest()[:16]
    target = CACHE / f"ai-{key}.png"
    row = {"id": f"ai:{key}", "title": query[:120], "description": f"AI illustration: {query}"[:200],
           "width": 1600, "height": 1000, "license": "AI-generated", "artist": model,
           "credit": f"illustration generated with {model}", "source": "ai", "path": str(target)}
    if target.exists():
        # Drawn by an earlier run: free now; what it cost then is kept beside it.
        try:
            paid = float(json.loads(target.with_suffix(".json").read_text()).get("usd") or 0.0)
        except (OSError, ValueError):
            paid = None
        return [{**row, "paid": paid}]
    look = {"parchment": "in the style of an old engraved textbook plate, sepia ink on parchment",
            "lab": "as a clean modern science-textbook diagram on white",
            "cosmos": "as a clear diagram on a dark blue background"}.get(style or "", "as a clean, colourful textbook illustration")
    prompt = (f"An educational illustration of {query}, {look}. Accurate, simple, uncluttered, suitable for a "
              "school lesson. No words, letters, numbers or labels anywhere in the image. No real, identifiable people.")
    url = os.environ.get("OPENROUTER_URL") or "https://openrouter.ai/api/v1/chat/completions"
    body = json.dumps({"model": model, "modalities": ["image", "text"], "usage": {"include": True},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    import urllib.request

    request = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json",
        "User-Agent": images.UA})
    with urllib.request.urlopen(request, timeout=120) as response:
        reply = json.loads(response.read())
    message = ((reply.get("choices") or [{}])[0]).get("message") or {}
    data_url = next((((i.get("image_url") or {}).get("url")) for i in message.get("images") or []
                     if ((i.get("image_url") or {}).get("url") or "").startswith("data:image")), None)
    if not data_url:
        return []
    CACHE.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    # What it cost (OpenRouter's usage), for the lecture's bill: on the row for the caller, and added up here
    # for a build (export_scene.py reports it).
    usd = float((reply.get("usage") or {}).get("cost") or 0.0)
    target.with_suffix(".json").write_text(json.dumps({"query": query, "model": model, "style": style, "usd": usd}))
    AI_MADE["count"] += 1
    AI_MADE["usd"] += usd
    AI_MADE["items"].append({"path": str(target), "query": query, "usd": usd, "model": model})
    return [{**row, "usd": usd, "made": True}]


# ---------------- all of them ----------------
SOURCES = {"local": local, "nasa": nasa, "met": met, "smithsonian": smithsonian, "storyweaver": storyweaver,
           "commons": lambda q, limit=6: images.commons_openverse(q, limit)}


def find(query: str, genre: str | None = None, limit: int = 6, style: str | None = None) -> list[dict]:
    """Reusable illustrations for a topic, from the sources that suit the subject, best source first. An AI
    illustration only when nothing else was found. [] when offline or disabled."""
    if not enabled() or not str(query).strip():
        return []
    route = ROUTES.get(genre or "general", ROUTES["general"])
    rows: list[dict] = []
    seen = set()
    for source in route:
        if source == "openverse":
            continue                    # searched together with Commons (images.commons_openverse)
        if source == "ai":
            if not rows:
                try:
                    rows += ai(query, style=style or os.environ.get("LECTURE_STYLE"))
                except Exception:  # noqa: BLE001 -- no key, offline, or the model drew nothing
                    pass
            break
        try:
            found = SOURCES[source](query, limit)
        except Exception:  # noqa: BLE001 -- a source that is down or blocked is skipped
            continue
        for row in found:
            if row["id"] in seen or images.NOT_EDUCATIONAL.search(row.get("title", "")) or images.is_map_row(row):
                continue
            if source in ("nasa", "met", "smithsonian", "storyweaver") and not _overlap(query, f"{row['title']} {row['description']}"):
                continue            # a museum's search is broad: keep what is actually about the topic
            seen.add(row["id"])
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows[:limit]


def reset() -> None:
    """Forget the local collections (after a download) and the AI budget (a new lecture)."""
    _collections.cache_clear()
    AI_MADE["count"] = 0
    AI_MADE["usd"] = 0.0
    AI_MADE["items"] = []


if __name__ == "__main__":
    args = sys.argv[1:]
    genre = None
    if "--genre" in args:
        at = args.index("--genre")
        genre = args[at + 1]
        del args[at:at + 2]
    print(json.dumps({q: find(q, genre=genre) for q in args}, indent=1, ensure_ascii=False))
