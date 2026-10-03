"""Open illustration libraries: hand-drawn drawings of things, free to use, for diagram nodes and definitions.

Emoji packs draw the same few hundred symbols; a lecture needs illustrations. These libraries are drawn by
illustrators, released under CC0, and downloaded once (fetch_all.py does it):

  CocoMaterial  cocomaterial.com, by Kaleidos: 3,000+ hand-drawn illustrations in 17 categories (animals, plants,
                buildings, people, food, school, science, tech...), dark outlines with flat colour: the board's
                whiteboard style. Its coloured version where one exists.
  Drawing Open  Arcadia Science's organism library (Zenodo 17203578): professional drawings of organisms (model
                organisms, plants, animals, microbes, viruses), the tricolour stroke version.

Ids are "coco:<id>-<name>" and "arcadia:<name>". Bioicons (bioicons.py) adds science drawings.

    .venv/bin/python harness/lecture/drawlib.py --fetch          # into data/drawlib (about 40 MB)
    .venv/bin/python harness/lecture/drawlib.py cow "solar panel"  # search, as JSON
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "data" / "drawlib"
COCO_API = "https://cocomaterial.com/api/vectors/?page_size=100&page={page}"
ARCADIA_RECORD = "https://zenodo.org/api/records/17203578"
AGENT = {"User-Agent": "pocketanim-lecture/0.5"}
NAMES = {"coco": "CocoMaterial (CC0)", "arcadia": "Drawing Open, Arcadia Science (CC0)"}
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
    return FOLDER.is_dir() and any(FOLDER.glob("*/*.svg"))


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
    return [{"id": r["id"], "name": r["name"], "set": r["set"]} for _, r in scored[:limit]]


def best(query: str) -> str | None:
    """The id of the drawing that shows the whole query, or None: a drawing of only part of it is not the thing."""
    words = _words(query)
    for found in search(query, 1):
        row = next(r for r in _index() if r["id"] == found["id"])
        forms = [{w, w[:-1] if w.endswith("s") else w, w[:-2] if w.endswith("es") else w} for w in words]
        if all(f & (row["words"] | row["more"]) for f in forms):
            return found["id"]
    return None


def is_id(name: str) -> bool:
    return str(name).split(":", 1)[0] in NAMES and ":" in str(name)


def file(drawing_id: str) -> Path:
    """The SVG of a "coco:..." or "arcadia:..." id."""
    library, stem = drawing_id.split(":", 1)
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
    else:
        print(json.dumps({q: search(q) for q in sys.argv[1:]}, indent=1))
