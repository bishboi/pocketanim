"""Open illustration libraries: hand-drawn drawings of things, free to use, for diagram nodes and definitions.

Emoji packs draw the same few hundred symbols; a lecture needs illustrations. These libraries are drawn by
illustrators, released under CC0, and downloaded once (fetch_all.py does it):

  CocoMaterial  cocomaterial.com, by Kaleidos: 3,000+ hand-drawn illustrations in 17 categories (animals, plants,
                buildings, people, food, school, science, tech...), dark outlines with flat colour: the board's
                whiteboard style. Its coloured version where one exists.
  Drawing Open  Arcadia Science's organism library (Zenodo 17203578): professional drawings of organisms (model
                organisms, plants, animals, microbes, viruses), the tricolour stroke version.
  OpenClipart   openclipart.org: 178,000 public-domain drawings by thousands of artists, everything from a bullock
                cart, a diya and a rangoli to a volcano and a pulley. Read once from its Hugging Face copy
                (nyuuzyou/openclipart, 22 GB of zstd JSON lines), keeping only coloured drawings small enough
                to draw on a board, with no text or pasted photos in them: about 300 MB, in a SQLite file
                with a full-text index of titles and tags.

Ids are "coco:<id>-<name>", "arcadia:<name>" and "clip:<n>". Bioicons (bioicons.py) adds science drawings.

    .venv/bin/python harness/lecture/drawlib.py --fetch          # CocoMaterial and Drawing Open (about 40 MB)
    .venv/bin/python harness/lecture/drawlib.py --openclipart    # OpenClipart (a long download; resumes)
    .venv/bin/python harness/lecture/drawlib.py cow "solar panel"  # search, as JSON
"""

from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
import zipfile
import zlib
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "data" / "drawlib"
COCO_API = "https://cocomaterial.com/api/vectors/?page_size=100&page={page}"
ARCADIA_RECORD = "https://zenodo.org/api/records/17203578"
CLIP_SHARD = "https://huggingface.co/datasets/nyuuzyou/openclipart/resolve/main/openclipart_{n:02d}.jsonl.zst"
AGENT = {"User-Agent": "pocketanim-lecture/0.5"}
NAMES = {"coco": "CocoMaterial (CC0)", "arcadia": "Drawing Open, Arcadia Science (CC0)",
         "clip": "OpenClipart (public domain)"}
# What a board drawing is not: a pattern, a frame, lettering, a colouring page or a silhouette.
CLIP_UNFIT = re.compile(r"\b(pattern|seamless|background|wallpaper|texture|border|frame|font|alphabet|letters?|"
                        r"text|logo|label|sticker|banner|button|icon set|colou?ring|line ?art|outline|silhouette|"
                        r"qr|barcode|ornament|divider|tile)\b", re.I)
CLIP_MAX = 60_000                       # bytes of SVG: more is a detailed picture, slow to draw and busy on a board
# Words in a file's name that say which version it is, not what it shows.
_VERSION = re.compile(r"\b(tricolou?r|stroke|silhouette|color|colou?red|outline|final|v\d+)\b")


def _get(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=timeout) as response:
        return response.read()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "drawing"


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 1]


def available() -> bool:
    return FOLDER.is_dir() and (any(FOLDER.glob("*/*.svg")) or (FOLDER / "openclipart.db").is_file())


def fetch_coco() -> int:
    """Every CocoMaterial drawing (its coloured SVG where there is one), with its name and tags."""
    folder = FOLDER / "coco"
    folder.mkdir(parents=True, exist_ok=True)
    index, page = [], 1
    while True:
        data = json.loads(_get(COCO_API.format(page=page)))
        for row in data.get("results") or []:
            svg = row.get("colored_svg_content") or row.get("svg_content")
            if not svg:
                link = row.get("colored_svg") or row.get("svg")
                svg = _get(link).decode("utf-8", "replace") if link else ""
            if "<svg" not in svg[:3000]:
                continue
            name = _slug(row.get("name") or str(row.get("tags") or "").split(",")[0] or str(row["id"]))
            stem = f"{row['id']}-{name}"
            (folder / f"{stem}.svg").write_text(svg, encoding="utf-8")
            index.append({"stem": stem, "name": (row.get("name") or name).replace("-", " "),
                          "tags": [t.strip() for t in str(row.get("tags") or "").split(",") if t.strip()]})
        if not data.get("next"):
            break
        page += 1
    (folder / "index.json").write_text(json.dumps(index, ensure_ascii=False))
    return len(index)


def fetch_arcadia() -> int:
    """Arcadia's organism drawings: one SVG an organism, the tricolour stroke drawing before the silhouette."""
    folder = FOLDER / "arcadia"
    folder.mkdir(parents=True, exist_ok=True)
    record = json.loads(_get(ARCADIA_RECORD))
    archives = [f for f in record.get("files") or [] if str(f.get("key", "")).endswith(".zip")]
    if not archives:
        raise RuntimeError("the Drawing Open record has no archive")
    data = _get(archives[0]["links"]["self"], timeout=600)
    best: dict[str, tuple[int, str]] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.namelist():
            if not member.lower().endswith(".svg") or "__MACOSX" in member:
                continue
            path = member.lower()
            rank = 0 if ("tricolor" in path or "stroke" in path) else 2 if "silhouette" in path else 1
            name = _slug(_VERSION.sub(" ", Path(member).stem.lower().replace("_", " ")))
            if name not in best or rank < best[name][0]:
                best[name] = (rank, member)
        for name, (_, member) in best.items():
            (folder / f"{name}.svg").write_bytes(archive.read(member))
    return len(best)


def _clip_db(create: bool = False) -> sqlite3.Connection | None:
    path = FOLDER / "openclipart.db"
    if not create and not path.is_file():
        return None
    FOLDER.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS clip (id INTEGER PRIMARY KEY, title TEXT, tags TEXT, artist TEXT, svg BLOB);
        CREATE VIRTUAL TABLE IF NOT EXISTS clip_fts USING fts5(title, tags, content='clip', content_rowid='id');
        CREATE TABLE IF NOT EXISTS shard (n INTEGER PRIMARY KEY, kept INTEGER);
    """)
    return db


def clip_fit(record: dict) -> bool:
    """An OpenClipart drawing a board can use: titled, coloured, small, no text or embedded photo in it."""
    svg, title = str(record.get("svg_content") or ""), str(record.get("title") or "").strip()
    if not title or not svg or len(svg) > CLIP_MAX or CLIP_UNFIT.search(title):
        return False
    if re.search(r"<(image|text|flowRoot|foreignObject)\b", svg):
        return False
    colours = set(re.findall(r"fill(?:=\"|:)\s*(#[0-9a-fA-F]{3,6})", svg))
    return len(colours) >= 3                        # a coloured drawing, not a one-colour shape


def fetch_openclipart(shards: int | None = None) -> int:
    """Read OpenClipart's shards in turn, without storing them, and keep the drawings that fit (clip_fit).
    Resumes: a shard read before is skipped. The number of drawings kept so far."""
    import zstandard

    db = _clip_db(create=True)
    done = {n for (n,) in db.execute("SELECT n FROM shard")}
    limit = shards if shards is not None else int(os.environ.get("PANIM_OPENCLIPART_SHARDS", "99"))
    for n in range(limit):
        if n in done:
            continue
        request = urllib.request.Request(CLIP_SHARD.format(n=n), headers=AGENT)
        try:
            response = urllib.request.urlopen(request, timeout=600)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                break                                 # past the last shard
            raise
        kept = 0
        with response, zstandard.ZstdDecompressor().stream_reader(response) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8", errors="replace"):
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not clip_fit(record):
                    continue
                tags = record.get("tags") or []
                tags = " ".join(tags) if isinstance(tags, list) else str(tags)
                cur = db.execute("INSERT INTO clip (title, tags, artist, svg) VALUES (?, ?, ?, ?)",
                                 (record["title"].strip(), tags, str(record.get("artist_name") or ""),
                                  zlib.compress(record["svg_content"].encode("utf-8"), 9)))
                db.execute("INSERT INTO clip_fts (rowid, title, tags) VALUES (?, ?, ?)",
                           (cur.lastrowid, record["title"].strip(), tags))
                kept += 1
        db.execute("INSERT INTO shard (n, kept) VALUES (?, ?)", (n, kept))
        db.commit()
        print(f"openclipart shard {n:02d}: {kept} drawings kept", file=sys.stderr, flush=True)
    total = db.execute("SELECT count(*) FROM clip").fetchone()[0]
    db.close()
    _clip.cache_clear()
    return total


@lru_cache(None)
def _clip() -> sqlite3.Connection | None:
    return _clip_db()


def _clip_search(words: list[str], limit: int) -> list[dict]:
    db = _clip()
    if db is None or not words:
        return []
    forms = [sorted({w, w[:-1] if w.endswith("s") else w, w[:-2] if w.endswith("es") else w}) for w in words]
    match = " AND ".join("(" + " OR ".join(f'"{f}"' for f in group) + ")" for group in forms)
    rows = db.execute("SELECT clip.id, clip.title, clip.tags FROM clip_fts JOIN clip ON clip.id = clip_fts.rowid "
                      "WHERE clip_fts MATCH ? ORDER BY bm25(clip_fts, 8.0, 1.0) LIMIT ?", (match, limit * 4)).fetchall()
    out = []
    for rowid, title, tags in rows:
        named = set(_words(title))
        in_title = sum(bool(set(g) & named) for g in forms)
        # The title says what is drawn; tags are broad ("cow" on a farm scene). Short exact titles first.
        out.append((-(in_title * 100) + len(named), {"id": f"clip:{rowid}", "name": title, "set": "clip",
                                                       "title_match": in_title == len(forms)}))
    out.sort(key=lambda pair: pair[0])
    return [row for _, row in out[:limit]]


def fetch() -> dict:
    """Download every library; {library: drawings, or the error}."""
    out = {}
    for name, step in (("coco", fetch_coco), ("arcadia", fetch_arcadia)):
        try:
            out[name] = step()
        except Exception as error:  # noqa: BLE001 - one library down does not stop the other
            out[name] = f"failed: {error}"
    _index.cache_clear()
    return out


@lru_cache(None)
def _index() -> list[dict]:
    rows = []
    coco = FOLDER / "coco"
    meta = {}
    if (coco / "index.json").is_file():
        meta = {r["stem"]: r for r in json.loads((coco / "index.json").read_text(encoding="utf-8"))}
    for svg in sorted(coco.glob("*.svg")) if coco.is_dir() else []:
        row = meta.get(svg.stem) or {"name": svg.stem.split("-", 1)[-1].replace("-", " "), "tags": []}
        rows.append({"id": f"coco:{svg.stem}", "name": row["name"], "set": "coco", "path": svg,
                     "words": set(_words(row["name"])), "more": set(_words(" ".join(row["tags"])))})
    arcadia = FOLDER / "arcadia"
    for svg in sorted(arcadia.glob("*.svg")) if arcadia.is_dir() else []:
        name = svg.stem.replace("-", " ")
        rows.append({"id": f"arcadia:{svg.stem}", "name": name, "set": "arcadia", "path": svg,
                     "words": set(_words(name)), "more": set()})
    return rows


def search(query: str, limit: int = 8) -> list[dict]:
    """Drawings for a query, best first: every word of it in the name, then in the tags, then some of it."""
    words = _words(query)
    if not words:
        return []
    forms = [{w, w[:-1] if w.endswith("s") else w, w[:-2] if w.endswith("es") else w} for w in words]
    scored = []
    for row in _index():
        hits = sum(bool(f & row["words"]) for f in forms)
        tags = sum(bool(f & row["more"]) for f in forms)
        if not hits and not tags:
            continue
        score = (100 if hits == len(forms) else 30 * hits / len(forms)) + (40 if tags == len(forms) else 8 * tags)
        scored.append((score - len(row["words"]), row))
    scored.sort(key=lambda pair: -pair[0])
    out = [{"id": r["id"], "name": r["name"], "set": r["set"]} for _, r in scored[:limit]]
    if len(out) < limit:                # CocoMaterial and Arcadia first: one style; then OpenClipart's many
        out += [{k: v for k, v in r.items() if k != "title_match"} for r in _clip_search(words, limit - len(out))]
    return out


def best(query: str) -> str | None:
    """The id of the drawing that shows the whole query, or None: a drawing of only part of it is not the thing.
    A CocoMaterial or Arcadia drawing first; an OpenClipart one whose title names all of it."""
    words = _words(query)
    forms = [{w, w[:-1] if w.endswith("s") else w, w[:-2] if w.endswith("es") else w} for w in words]
    rows = {r["id"]: r for r in _index()}
    for found in search(query, 1):
        row = rows.get(found["id"])
        if row and all(f & (row["words"] | row["more"]) for f in forms):
            return found["id"]
    for found in _clip_search(words, 1):
        if found["title_match"]:
            return found["id"]
    return None


def is_id(name: str) -> bool:
    return str(name).split(":", 1)[0] in NAMES and ":" in str(name)


def file(drawing_id: str) -> Path:
    """The SVG of a "coco:...", "arcadia:..." or "clip:<n>" id."""
    library, stem = drawing_id.split(":", 1)
    if library == "clip":
        path = FOLDER / "clip" / f"{stem}.svg"
        if not path.is_file():
            db = _clip()
            found = db.execute("SELECT svg FROM clip WHERE id = ?", (int(stem),)).fetchone() if db and stem.isdigit() else None
            if not found:
                raise KeyError(f"no drawing {drawing_id!r}" + ("" if db else " (run drawlib.py --openclipart)"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zlib.decompress(found[0]))
        return path
    path = FOLDER / library / f"{stem}.svg"
    if not path.is_file():
        raise KeyError(f"no drawing {drawing_id!r}" + ("" if available() else " (run drawlib.py --fetch)"))
    return path


def credit(drawing_ids) -> str:
    sets = sorted({NAMES[i.split(":", 1)[0]] for i in drawing_ids if is_id(i)})
    return "Illustrations: " + ", ".join(sets) if sets else ""


if __name__ == "__main__":
    if sys.argv[1:] == ["--fetch"]:
        print(json.dumps(fetch()))
    elif sys.argv[1:2] == ["--openclipart"]:
        print(json.dumps({"openclipart": fetch_openclipart(int(sys.argv[2]) if len(sys.argv) > 2 else None)}))
    else:
        print(json.dumps({q: search(q) for q in sys.argv[1:]}, indent=1))
