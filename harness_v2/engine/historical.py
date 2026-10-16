"""Historical borders: the world's states as they stood in a given year, so a map of 1600 shows the Mughal Empire,
not today's India.

The borders are the historical-basemaps project's (github.com/aourednik/historical-basemaps, GPL-3.0): one GeoJSON
file a year, from 2000 BC to 2010. They are not kept in this repository; each year's file is downloaded the first time
a lecture asks for it (or ahead of time: `python historical.py --fetch [YEAR ...]`) into data/historical/, or
PANIM_HISTORICAL_DIR.

    empire("Mughal Empire", 1605)   -> (shape, "Mughal Empire", 1600)
    names(1600)                     -> every state on the 1600 map
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

SOURCE = "https://raw.githubusercontent.com/aourednik/historical-basemaps/master/geojson/world_{name}.geojson"
CREDIT = "Historical borders: historical-basemaps (A. Ourednik), GPL-3.0"

# The years the project has a map for (negative: BC).
YEARS = (-2000, -1000, -500, -323, -200, -1, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1279,
         1300, 1400, 1492, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914, 1920, 1930,
         1938, 1945, 1960, 1994, 2000, 2010)

# Names a script may use for a state the maps call otherwise.
ALIASES = {
    "ming dynasty": "ming chinese empire", "ming china": "ming chinese empire", "qing dynasty": "manchu empire",
    "qing empire": "manchu empire", "ottoman empire": "ottoman empire", "ottomans": "ottoman empire",
    "mughals": "mughal empire", "maurya": "mauryan empire", "maurya empire": "mauryan empire", "mughal": "mughal empire", "british raj": "british raj",
    "maratha empire": "maratha confederacy", "marathas": "maratha confederacy", "hre": "holy roman empire",
    "safavids": "safavid empire", "safavid persia": "safavid empire", "roman empire": "roman empire",
    "rome": "roman empire", "byzantium": "byzantine empire", "eastern roman empire": "byzantine empire",
}


def folder() -> Path:
    return Path(os.environ.get("PANIM_HISTORICAL_DIR") or Path(__file__).resolve().parent / "data" / "historical")


def _file_name(year: int) -> str:
    return f"bc{-year}" if year < 0 else str(year)


def nearest(year: int) -> int:
    """The map year closest to `year`; on a tie the earlier one (a state is drawn as it was, not as it became)."""
    return min(YEARS, key=lambda y: (abs(y - int(year)), y))


def path(year: int, fetch: bool = True) -> Path | None:
    """The file of the map nearest `year`, downloaded if it is not here yet (None when it cannot be had)."""
    y = nearest(year)
    out = folder() / f"world_{_file_name(y)}.geojson"
    if out.exists() and out.stat().st_size > 1000:
        return out
    if not fetch or os.environ.get("PANIM_HISTORICAL_FETCH") == "0":
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(SOURCE.format(name=_file_name(y)), timeout=60) as response:
            data = response.read()
        json.loads(data)
    except Exception as error:  # noqa: BLE001 -- no network, or a bad file: no historical map
        print(f"historical borders for {y}: {type(error).__name__}: {error}", file=sys.stderr)
        return None
    tmp = out.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(out)
    return out


@lru_cache(None)
def _features(year: int) -> tuple:
    file = path(year)
    if file is None:
        return ()
    from shapely.geometry import shape

    out = []
    for feature in json.loads(file.read_text(encoding="utf-8")).get("features") or []:
        props = feature.get("properties") or {}
        try:
            geom = shape(feature["geometry"])
        except Exception:  # noqa: BLE001 -- a broken feature is skipped
            continue
        out.append((props, geom))
    return tuple(out)


def _norm(text) -> str:
    from pocket_lecture import _norm as norm

    return norm(text)


def names(year: int) -> list[str]:
    """Every state named on the map nearest `year`."""
    return sorted({str(p.get("NAME")) for p, _ in _features(nearest(year)) if p.get("NAME")})


def empire(name: str, year: int):
    """(shape, the map's name for it, the map's year) for a state as it stood in `year`, or None. A state is found by
    its name, or as the overlord its parts are subject to (SUBJECTO): the Mughal Empire with its vassals."""
    y = nearest(year)
    feats = _features(y)
    if not feats:
        return None
    want = _norm(name)
    want = ALIASES.get(want, want)
    found = [(p, g) for p, g in feats if _norm(p.get("NAME")) == want or
             (want and (_norm(p.get("SUBJECTO")) == want or _norm(p.get("PARTOF")) == want))]
    if not found:
        # A shorter or longer form ("Inca" for "Inca Empire", "Mauryan" for "Mauryan Empire").
        found = [(p, g) for p, g in feats if p.get("NAME") and len(want) >= 4 and
                 (want in _norm(p.get("NAME")).split() or _norm(p.get("NAME")).startswith(want) or
                  want.startswith(_norm(p.get("NAME")) + " "))]
    if not found:
        return None
    from shapely.ops import unary_union

    from pocket_lecture import _valid

    shape = unary_union([_valid(g) for _, g in found])
    best = max(found, key=lambda pg: pg[1].area)[0].get("NAME")
    return shape, str(best), y


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        wanted = [int(a) for a in sys.argv[2:]] or list(YEARS)
        for year in wanted:
            got = path(year)
            print(f"{nearest(year)}: {got or 'FAILED'}")
    else:
        print(__doc__)
