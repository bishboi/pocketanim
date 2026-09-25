"""Locate a real feature inside a Natural Earth region.

Marks on a map have to come from this, not from a guessed coordinate.
Prints one JSON object: the official name, a point inside the region, and
for a river or a range the coordinates of that feature clipped to the region.

Usage:
    python harness/scripts/locate_feature.py "Rajasthan" "Thar Desert"
"""

from __future__ import annotations

import json
import re
import sys

# Generic words that are not the place. "Aravalli Range" and "Arvalli Ra."
# are the same feature once these are gone.
STOP = {"the", "of", "range", "ra", "desert", "river", "rivers", "lake", "mount", "mt", "mountains"}

LAYERS = (
    ("physical", "geography_regions_polys", "10m", ("NAME", "NAME_EN", "NAMEALT")),
    ("physical", "geography_regions_points", "10m", ("name", "name_en", "name_alt")),
    ("physical", "rivers_lake_centerlines", "10m", ("name", "name_en", "name_alt")),
    ("cultural", "populated_places", "10m", ("NAME", "NAMEASCII", "NAMEALT")),
)


def words(value: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", value.lower()) if word not in STOP]


def skeleton(value: str) -> str:
    return "".join(ch for ch in "".join(words(value)) if ch not in "aeiou")


def names_of(attrs: dict, fields: tuple[str, ...]) -> list[str]:
    found = []
    for field in fields:
        text = str(attrs.get(field) or "").strip()
        if text and text not in found:
            found.append(text)
    return found


def same_place(query: str, candidate: str) -> bool:
    if skeleton(query) and skeleton(query) == skeleton(candidate):
        return True
    left, right = words(query), words(candidate)
    return bool(left) and bool(right) and (left == right or " ".join(left) in " ".join(right) or " ".join(right) in " ".join(left))


def region_geometry(place: str):
    import cartopy.io.shapereader as shpreader
    from shapely.ops import unary_union

    query = place.strip().lower()
    datasets = (
        ("admin_1_states_provinces", "name"),
        ("admin_0_countries", "NAME"),
    )
    for dataset, field in datasets:
        fn = shpreader.natural_earth(resolution="50m", category="cultural", name=dataset)
        parts = []
        for record in shpreader.Reader(fn).records():
            if str(record.attributes.get(field) or "").strip().lower() == query:
                parts.append(record.geometry)
        if parts:
            return unary_union(parts)
    return None


def sample(geom, limit: int = 24) -> list[list[float]]:
    coords = []
    if geom.geom_type in ("LineString", "LinearRing"):
        coords = list(geom.coords)
    elif geom.geom_type == "MultiLineString":
        for part in geom.geoms:
            coords.extend(part.coords)
    elif geom.geom_type == "Polygon":
        coords = list(geom.exterior.coords)
    elif geom.geom_type == "MultiPolygon":
        largest = max(geom.geoms, key=lambda part: part.area)
        coords = list(largest.exterior.coords)
    elif geom.geom_type == "Point":
        return [[round(geom.x, 4), round(geom.y, 4)]]
    else:
        point = geom.representative_point()
        return [[round(point.x, 4), round(point.y, 4)]]
    if len(coords) > limit:
        step = max(1, len(coords) // limit)
        coords = coords[::step]
    return [[round(lon, 4), round(lat, 4)] for lon, lat in coords]


def locate(region_name: str, feature: str) -> dict:
    import cartopy.io.shapereader as shpreader

    region = region_geometry(region_name)
    if region is None:
        return {"found": False, "region": region_name, "feature": feature, "error": "region not found"}

    best = None
    for category, dataset, resolution, fields in LAYERS:
        fn = shpreader.natural_earth(resolution=resolution, category=category, name=dataset)
        for record in shpreader.Reader(fn).records():
            labels = names_of(record.attributes, fields)
            if not any(same_place(feature, label) for label in labels):
                continue
            piece = record.geometry.intersection(region)
            if piece.is_empty:
                continue
            point = piece.representative_point()
            if not region.buffer(0.05).covers(point):
                continue
            size = piece.length if piece.geom_type.endswith("LineString") or piece.geom_type == "MultiLineString" else piece.area
            if best is None or size > best["size"]:
                best = {
                    "size": size,
                    "name": labels[0],
                    "kind": piece.geom_type,
                    "lon": round(point.x, 4),
                    "lat": round(point.y, 4),
                    "path": sample(piece),
                }
    if best is None:
        return {
            "found": False,
            "region": region_name,
            "feature": feature,
            "error": "No Natural Earth feature by that name lies inside the region. Do not mark it.",
        }
    best.pop("size")
    return {"found": True, "region": region_name, "feature": feature, **best}


def main() -> int:
    if len(sys.argv) != 3:
        print(json.dumps({"found": False, "error": "usage: locate_feature.py <region> <feature>"}))
        return 2
    try:
        print(json.dumps(locate(sys.argv[1], sys.argv[2])))
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"found": False, "region": sys.argv[1], "feature": sys.argv[2], "error": f"{type(error).__name__}: {error}"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
