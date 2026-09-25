"""Find one Natural Earth region by name and print a Manim scene for it.

The map is that place, fitted to the frame — Rajasthan is Rajasthan, not the
world coastline. Prints one JSON object.

Usage:
    python harness/scripts/map_region.py "Rajasthan"
"""

from __future__ import annotations

import json
import sys

DATASETS = (
    ("admin_1_states_provinces", "name", "admin"),
    ("admin_0_countries", "NAME", "CONTINENT"),
)


def norm(value: object) -> str:
    return str(value or "").strip().lower()


def search(place: str) -> dict:
    import cartopy.io.shapereader as shpreader

    query = norm(place)
    hits = []
    for dataset, name_field, parent_field in DATASETS:
        fn = shpreader.natural_earth(resolution="50m", category="cultural", name=dataset)
        for record in shpreader.Reader(fn).records():
            attrs = record.attributes
            name = str(attrs.get(name_field) or "")
            parent = str(attrs.get(parent_field) or "")
            if query and (query == norm(name) or query in norm(name) or query in norm(parent)):
                hits.append({
                    "dataset": dataset,
                    "name": name,
                    "parent": parent,
                    "exact": query == norm(name),
                })
            if len(hits) >= 8:
                break
        exact = [hit for hit in hits if hit["exact"] and hit["dataset"] == dataset]
        if exact:
            hits = exact[:1]
            break
        if hits and dataset == "admin_1_states_provinces":
            # A state match beats a later country whose name merely contains the query.
            named = [hit for hit in hits if query == norm(hit["name"])]
            if named:
                hits = named[:1]
                break
    if not hits:
        return {"found": False, "place": place, "matches": []}
    exact = [hit for hit in hits if hit["exact"]]
    best = (exact or hits)[0]
    payload = {
        "found": bool(exact),
        "place": place,
        "dataset": best["dataset"],
        "name": best["name"],
        "parent": best["parent"],
        "matches": (exact or hits)[:8],
    }
    if exact:
        payload["scene"] = scene_source(best["dataset"], best["name"], best["parent"])
    return payload


def scene_source(dataset: str, name: str, parent: str) -> str:
    name_field = "name" if dataset == "admin_1_states_provinces" else "NAME"
    title = name if not parent or dataset == "admin_0_countries" else f"{name}, {parent}"
    return f'''from manim import *
import cartopy.io.shapereader as shpreader

NAME = {json.dumps(name)}
DATASET = {json.dumps(dataset)}
NAME_FIELD = {json.dumps(name_field)}


def parts(geom):
    if hasattr(geom, "geoms"):
        for part in geom.geoms:
            yield part
    else:
        yield geom


def ring_coords(geom):
    for part in parts(geom):
        if hasattr(part, "exterior"):
            yield np.asarray(part.exterior.coords)
        else:
            yield np.asarray(part.coords)


def build_region():
    fn = shpreader.natural_earth(resolution="50m", category="cultural", name=DATASET)
    raw = []
    xs, ys = [], []
    for record in shpreader.Reader(fn).records():
        if str(record.attributes.get(NAME_FIELD) or "") != NAME:
            continue
        for coords in ring_coords(record.geometry):
            if len(coords) < 2:
                continue
            raw.append(coords[:, :2])
            xs.extend(coords[:, 0])
            ys.extend(coords[:, 1])
    if not raw:
        raise RuntimeError("no geometry for " + NAME)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1e-6)
    # Leave a band at the top for the title so the outline cannot meet it.
    scale = 4.4 / span

    def project(lon, lat):
        return np.array([
            (lon - (min_x + max_x) / 2) * scale,
            (lat - (min_y + max_y) / 2) * scale - 0.35,
            0.0,
        ])

    group = VGroup()
    for coords in raw:
        pts = [project(lon, lat) for lon, lat in coords]
        line = VMobject(stroke_width=2.0, stroke_color="#58C4DD")
        line.set_points_as_corners(pts)
        group.add(line)
    return group, project


class GeneratedScene(Scene):
    def construct(self):
        title = Text({json.dumps(title)}, font_size=32, color="#F4F1EA").to_edge(UP, buff=0.4)
        region, project = build_region()
        self.add(title)
        self.play(FadeIn(region), run_time=1.4)
        self.wait(1)
'''


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"found": False, "error": "usage: map_region.py <place>"}))
        return 2
    try:
        print(json.dumps(search(sys.argv[1])))
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"found": False, "place": sys.argv[1], "error": f"{type(error).__name__}: {error}"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
