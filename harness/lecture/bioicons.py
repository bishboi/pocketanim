"""Bioicons: open science illustrations (cells, organs, lab apparatus, molecules, organisms), as SVG.

bioicons.com, github.com/duerrsimon/bioicons: about 2,500 drawings by scientists and illustrators, each under CC0,
CC BY, CC BY-SA or MIT (the licence is the first folder of its path). Where a lecture needs a drawing that is right
as well as clear (a neuron, a mitochondrion, a burette), this is the library to choose from. Downloaded once:

    .venv/bin/python harness/lecture/bioicons.py --fetch          # into data/bioicons (about 30 MB)
    .venv/bin/python harness/lecture/bioicons.py neuron burette  # search, as JSON
"""

from __future__ import annotations

import io
import json
import re
import sys
import tarfile
import urllib.request
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "data" / "bioicons"
ARCHIVE = "https://codeload.github.com/duerrsimon/bioicons/tar.gz/refs/heads/main"
LICENCES = {"cc-0": "CC0", "cc0": "CC0", "cc-by-3.0": "CC BY 3.0", "cc-by-4.0": "CC BY 4.0", "cc-by": "CC BY",
            "cc-by-sa-3.0": "CC BY-SA 3.0", "cc-by-sa-4.0": "CC BY-SA 4.0", "mit": "MIT", "bsd": "BSD"}


def available() -> bool:
    return FOLDER.is_dir() and any(FOLDER.rglob("*.svg"))


def fetch() -> int:
    """Download the library's SVGs into data/bioicons; the number of drawings."""
    request = urllib.request.Request(ARCHIVE, headers={"User-Agent": "pocketanim-lecture/0.5"})
    with urllib.request.urlopen(request, timeout=600) as response:
        data = response.read()
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = member.name.split("/")
            if not member.isfile() or not member.name.endswith(".svg") or "static" not in parts:
                continue
            rel = parts[parts.index("static") + 2:] if parts[parts.index("static") + 1] == "icons" else None
            if not rel or len(rel) < 2:
                continue
            target = FOLDER.joinpath(*rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
            count += 1
    _index.cache_clear()
    return count


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.lower().replace("_", "-")) if len(w) > 1]


@lru_cache(None)
def _index() -> list[dict]:
    rows = []
    for svg in sorted(FOLDER.rglob("*.svg")) if FOLDER.is_dir() else []:
        rel = svg.relative_to(FOLDER).parts
        licence, category, author = (rel + ("", "", ""))[:3] if len(rel) >= 4 else (rel[0], "", "")
        name = svg.stem
        rows.append({"id": "bioicons:" + "/".join(rel)[:-4], "name": name.replace("_", " ").replace("-", " "),
                     "category": category.replace("_", " "), "author": author.replace("_", " "),
                     "licence": LICENCES.get(licence.lower(), licence), "words": set(_words(name)),
                     "more": set(_words(category))})
    return rows


def search(query: str, limit: int = 8) -> list[dict]:
    """Drawings for a query, best first: every word of it in the name, then any, then in the category."""
    words = _words(query)
    if not words:
        return []
    forms = [{w, w[:-1] if w.endswith("s") else w, w[:-2] if w.endswith("es") else w} for w in words]
    scored = []
    for row in _index():
        hits = sum(bool(f & row["words"]) for f in forms)
        side = sum(bool(f & row["more"]) for f in forms)
        if not hits and not side:
            continue
        score = (100 if hits == len(forms) else 30 * hits / len(forms)) + 5 * side - len(row["words"])
        scored.append((score, row))
    scored.sort(key=lambda pair: -pair[0])
    return [{k: v for k, v in row.items() if k not in ("words", "more")} for _, row in scored[:limit]]


def file(icon_id: str) -> Path:
    """The SVG of a "bioicons:licence/category/author/name" id."""
    rel = icon_id.split(":", 1)[1]
    path = FOLDER / f"{rel}.svg"
    if not path.is_file():
        raise KeyError(f"no Bioicons drawing {icon_id!r}" + ("" if available() else " (run bioicons.py --fetch)"))
    return path


def credit(icon_ids) -> str:
    """The credits line for the drawings used: CC BY asks for the author's name."""
    rows = {r["id"]: r for r in _index()}
    names = sorted({f"{rows[i]['author']} ({rows[i]['licence']})" for i in icon_ids if i in rows and rows[i]["author"]})
    return "Science drawings: Bioicons" + (f", by {', '.join(names)}" if names else "") if icon_ids else ""


if __name__ == "__main__":
    if sys.argv[1:] == ["--fetch"]:
        print(f"{fetch()} drawings in {FOLDER}")
    else:
        print(json.dumps({q: search(q) for q in sys.argv[1:]}, indent=1))
