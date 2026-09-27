"""Region packs at runtime: the focus, anchors, features and gazetteer of a place.

A curated pack lives in regions/<id>/region.yaml. Any other country or state a
job names gets an automatic pack built from Natural Earth (region.build),
cached by name, so scripts can always name places instead of coordinates.
"""

from __future__ import annotations

import re
from functools import lru_cache

from forge import registry
from forge.util import CACHE, digest, read_json, write_json


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def find(query: str) -> list[dict]:
    """Region packs matching a name, curated first; builds one when none match."""
    q = _norm(query)
    hits = []
    for rid, spec in registry.regions().items():
        names = {_norm(rid), _norm(spec.get("name"))} | {_norm(a) for a in spec.get("aliases", [])}
        if q in names or any(n and (n in q.split() or f" {n} " in f" {q} ") for n in names):
            hits.append({"id": rid, "name": spec.get("name"), "curated": True,
                         "battlefield": bool(spec.get("battlefield"))})
    if hits:
        return hits
    built = build(query)
    return [{"id": built["id"], "name": built["name"], "curated": False, "battlefield": False}] if built else []


def build(query: str) -> dict | None:
    """region.build: an automatic pack for the country or state a text names."""
    from resolve_region import resolve  # harness/lecture

    key = digest("region", query)
    cached = read_json(CACHE / "regions" / f"{key}.json")
    if cached is not None:
        return cached or None
    focus = resolve(query)
    if not focus:
        write_json(CACHE / "regions" / f"{key}.json", {})
        return None
    name = focus.get("state") or focus.get("country")
    pack = {"id": f"auto_{_norm(name).replace(' ', '_')}", "name": name, "focus": focus, "anchors": {},
            "features": {"paths": {}}, "auto": True}
    write_json(CACHE / "regions" / f"{key}.json", pack)
    write_json(CACHE / "regions" / f"{pack['id']}.json", pack)
    return pack


def load(region_id: str) -> dict:
    if region_id in registry.regions():
        return registry.load_region(region_id)
    cached = read_json(CACHE / "regions" / f"{region_id}.json")
    if cached:
        return cached
    raise KeyError(f"no region pack {region_id!r}")


@lru_cache(None)
def _geometry(region_id: str):
    import pocket_lecture as pl

    focus = load(region_id)["focus"]
    if focus.get("state"):
        return pl.state(focus["state"], focus.get("country"))
    return pl.country(focus["country"], focus.get("view"))


def bounds(region_id: str, margin: float = 0.25) -> tuple:
    lon0, lat0, lon1, lat1 = _geometry(region_id).bounds
    pad = max(lon1 - lon0, lat1 - lat0) * margin
    return (lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)


@lru_cache(None)
def gazetteer(region_id: str, limit: int = 400) -> list[dict]:
    """Populated places inside the region's box, most populous first."""
    import pocket_lecture as pl

    lon0, lat0, lon1, lat1 = bounds(region_id, 0.05)
    rows = []
    for attrs, _geom in pl._records("populated_places"):
        lon, lat = float(attrs["LONGITUDE"]), float(attrs["LATITUDE"])
        if lon0 <= lon <= lon1 and lat0 <= lat <= lat1:
            rows.append({"name": str(attrs.get("NAME")), "ascii": str(attrs.get("NAMEASCII") or ""),
                         "lonlat": [round(lon, 4), round(lat, 4)], "pop": int(attrs.get("POP_MAX") or 0),
                         "country": str(attrs.get("ADM0NAME") or "")})
    rows.sort(key=lambda r: -r["pop"])
    return rows[:limit]


@lru_cache(None)
def rivers(region_id: str) -> list[str]:
    """Names of Natural Earth rivers that cross the region."""
    import pocket_lecture as pl
    from shapely.geometry import box

    frame = box(*bounds(region_id, 0.05))
    names = set()
    for attrs, geom in pl._records("rivers_lake_centerlines", "physical"):
        name = attrs.get("name") or attrs.get("name_en")
        if name and geom is not None and geom.intersects(frame):
            names.add(str(name))
    return sorted(names)


def lookup(place: str, region_id: str | None = None) -> dict | None:
    """gazetteer.lookup: an anchor, then a place in the region, then anywhere."""
    q = _norm(place)
    if region_id:
        pack = load(region_id)
        for name, lonlat in (pack.get("anchors") or {}).items():
            if _norm(name) == q or _norm(name.replace("_", " ")) == q:
                return {"id": name, "name": name.replace("_", " ").title(), "lonlat": list(lonlat), "kind": "anchor"}
        for row in gazetteer(region_id):
            if q in (_norm(row["name"]), _norm(row["ascii"])):
                return {"id": row["name"], "name": row["name"], "lonlat": row["lonlat"], "kind": "place"}
    try:
        import pocket_lecture as pl

        lon, lat = pl.place(place)
        return {"id": place, "name": place, "lonlat": [round(lon, 4), round(lat, 4)], "kind": "place"}
    except KeyError:
        return None


def index(region_id: str) -> dict:
    """region.index: everything a script may name in this region."""
    pack = load(region_id)
    return {
        "id": region_id, "name": pack.get("name"), "focus": pack.get("focus"),
        "anchors": sorted((pack.get("anchors") or {})),
        "features": sorted(((pack.get("features") or {}).get("paths") or {})),
        "units": [u["id"] for u in ((pack.get("battlefield") or {}).get("units") or [])],
        "places": [r["name"] for r in gazetteer(region_id)[:60]],
        "rivers": rivers(region_id)[:60],
    }
