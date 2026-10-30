"""Real maps: countries, coasts, seas, rivers and towns from Natural Earth; the world's states as they stood in a year
from historical-basemaps; places found by name. What look.py draws a `map` (and its `region`s and `pin`s) from.

The data is fetched once into .cache/geo (setup.sh fetches today's; a year's borders come the first time a score asks
for that year):
    Natural Earth (public domain)                  github.com/nvkelso/natural-earth-vector
    historical-basemaps (A. Ourednik, GPL-3.0)      github.com/aourednik/historical-basemaps

    geo.bounds("europe")                    -> (lon0, lat0, lon1, lat1)   (a region, a country, or "LON0,LAT0,LON1,LAT1")
    geo.countries(bounds)                   -> [(name, shape)]            today's countries on that window
    geo.states(1300, bounds)                -> [(name, shape)]            the states of the map nearest 1300
    geo.shape("France", 1300)               -> (shape, its name on the map)  a country, or a state in a year
    geo.place("Constantinople", bounds)     -> (lon, lat)
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / ".cache" / "geo"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{name}.geojson"
HIST = "https://raw.githubusercontent.com/aourednik/historical-basemaps/master/geojson/world_{name}.geojson"
LAYERS = ("ne_50m_admin_0_countries", "ne_50m_admin_0_map_units", "ne_10m_admin_0_countries", "ne_10m_populated_places_simple",
          "ne_50m_rivers_lake_centerlines", "ne_10m_geography_marine_polys", "ne_50m_geography_regions_points")

# The years historical-basemaps has a map for (negative: BC).
YEARS = (-2000, -1000, -500, -323, -200, -1, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1279,
         1300, 1400, 1492, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914, 1920, 1930,
         1938, 1945, 1960, 1994, 2000, 2010)

# Windows a score names (lon0, lat0, lon1, lat1). Anything else is a country's own extent, or four numbers.
REGIONS = {
    "world": (-170, -56, 180, 78), "europe": (-12, 34, 42, 71), "western europe": (-11, 35, 20, 60),
    "northern europe": (-11, 49, 32, 71), "central europe": (4, 43, 26, 56), "eastern europe": (14, 41, 50, 62),
    "southern europe": (-10, 35, 30, 48), "british isles": (-11, 49.5, 2.5, 59.5), "britain": (-6.5, 49.8, 2, 59),
    "england": (-6, 49.8, 2, 55.9), "scandinavia": (4, 54, 32, 71.5), "iberia": (-10, 35.8, 4, 44),
    "italy": (6, 36.5, 19, 47.2), "france": (-5.5, 41.3, 9.8, 51.3), "germany": (5.5, 47, 15.5, 55.2),
    "low countries": (2, 49.4, 7.3, 53.7), "balkans": (13, 36, 30, 47), "mediterranean": (-10, 29, 40, 47),
    "middle east": (24, 12, 64, 42), "near east": (24, 26, 50, 42), "anatolia": (25, 35.5, 45, 42.5),
    "north africa": (-17, 18, 35, 38), "africa": (-20, -36, 53, 38), "east asia": (95, 17, 148, 50),
    "china": (72, 17, 136, 54), "japan": (127, 29, 147, 46), "korea": (124, 33, 131, 43.5), "india": (66, 6, 98.5, 38),
    "south asia": (60, 4, 100, 38), "southeast asia": (92, -11, 142, 28), "central asia": (45, 30, 90, 56),
    "eurasia": (-12, 0, 150, 62), "silk road": (8, 18, 128, 56), "russia": (25, 40, 180, 78),
    "north america": (-170, 12, -50, 72), "south america": (-85, -57, -32, 14), "americas": (-170, -56, -30, 72),
    "usa": (-126, 23, -65, 50), "united states": (-126, 23, -65, 50), "caribbean": (-90, 9, -59, 27),
    "atlantic": (-100, -40, 25, 65), "indian ocean": (30, -45, 120, 28), "pacific": (100, -50, 290, 60),
    "australia": (110, -45, 156, -9),
}

# Old names and other spellings of a place, to the name the data knows it by.
ALIASES = {
    "constantinople": "istanbul", "byzantium": "istanbul", "edo": "tokyo", "peking": "beijing", "canton": "guangzhou",
    "bombay": "mumbai", "calcutta": "kolkata", "madras": "chennai", "rangoon": "yangon", "saigon": "ho chi minh city",
    "batavia": "jakarta", "danzig": "gdansk", "konigsberg": "kaliningrad", "lemberg": "lviv", "pressburg": "bratislava",
    "ragusa": "dubrovnik", "smyrna": "izmir", "christiania": "oslo", "leningrad": "saint petersburg",
    "petrograd": "saint petersburg", "st petersburg": "saint petersburg", "stalingrad": "volgograd",
    "tsaritsyn": "volgograd", "breslau": "wroclaw", "aix la chapelle": "aachen", "cologne": "koln",
    "londinium": "london", "lutetia": "paris", "eboracum": "york", "mediolanum": "milan", "massilia": "marseille",
    "tenochtitlan": "mexico city", "new amsterdam": "new york", "leopoldville": "kinshasa",
    "persia": "iran", "siam": "thailand", "ceylon": "sri lanka", "burma": "myanmar", "holland": "netherlands",
    "bohemia": "czechia", "prussia": "kaliningrad", "flanders": "ghent", "nyc": "new york", "delhi": "new delhi",
}

# Places of the past the towns layer has no row for (lon, lat).
OLD_PLACES = {
    "troy": (26.24, 39.96), "carthage": (10.32, 36.85), "babylon": (44.42, 32.54), "nineveh": (43.15, 36.36),
    "ur": (46.10, 30.96), "memphis egypt": (31.25, 29.85), "thebes": (32.65, 25.70), "persepolis": (52.89, 29.93),
    "pompeii": (14.49, 40.75), "mycenae": (22.76, 37.73), "knossos": (25.16, 35.30), "antioch": (36.16, 36.20),
    "jericho": (35.44, 31.87), "mohenjo daro": (68.14, 27.33), "harappa": (72.86, 30.63), "angkor": (103.87, 13.41),
    "cuzco": (-71.97, -13.53), "machu picchu": (-72.55, -13.16), "timbuktu": (-3.00, 16.77),
    "great zimbabwe": (30.93, -20.27), "hastings": (0.57, 50.86), "agincourt": (2.13, 50.46),
    "crecy": (1.88, 50.25), "runnymede": (-0.56, 51.44), "wittenberg": (12.65, 51.87), "canterbury": (1.08, 51.28),
    "avignon": (4.81, 43.95), "kaffa": (35.38, 45.03), "caffa": (35.38, 45.03), "champagne": (4.03, 48.95),
    "flanders fields": (2.88, 50.85), "hanseatic lubeck": (10.69, 53.87), "lubeck": (10.69, 53.87),
    "novgorod": (31.27, 58.52), "aachen": (6.08, 50.78), "cluny": (4.66, 46.43), "chartres": (1.49, 48.45),
    "bruges": (3.22, 51.21), "ghent": (3.72, 51.05), "genoa": (8.93, 44.41), "messina": (15.55, 38.19),
    "marseille": (5.37, 43.30), "york": (-1.08, 53.96), "winchester": (-1.31, 51.06), "salisbury": (-1.79, 51.07),
    "xativa": (-0.52, 38.99), "jativa": (-0.52, 38.99), "fabriano": (12.90, 43.34), "subiaco": (13.09, 41.92),
    "wittenberg": (12.65, 51.87), "westminster": (-0.13, 51.50), "strasbourg": (7.75, 48.58),
    "antwerp": (4.40, 51.22), "mainz": (8.27, 50.00),
}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"^the ", "", s)


# ---------------------------------------------------------------- the data -------------------------------------------

def _fetch(url: str, file: Path) -> Path:
    """A data file, downloaded once: by curl (the system's certificates and proxy, a time limit), else urllib."""
    if not file.exists():
        import shutil
        import subprocess
        file.parent.mkdir(parents=True, exist_ok=True)
        tmp = file.with_suffix(".part")
        print(f"fetching map data: {file.name}", flush=True)
        ok = False
        if shutil.which("curl"):
            ok = subprocess.run(["curl", "-sfL", "--connect-timeout", "15", "--max-time", "180", "-o", str(tmp), url]
                                ).returncode == 0
        if not ok:
            req = urllib.request.Request(url, headers={"User-Agent": "pocketanim-v3"})
            with urllib.request.urlopen(req, timeout=30) as r:
                tmp.write_bytes(r.read())
        tmp.replace(file)
    return file


def fetch_all() -> None:
    """Today's layers, ahead of time (setup.sh)."""
    for name in LAYERS:
        _fetch(NE.format(name=name), DATA / f"{name}.geojson")


@lru_cache(None)
def _layer(name: str) -> tuple:
    """A layer's features: ((properties, shape), ...)."""
    from shapely.geometry import shape
    if name.startswith("world_"):
        file = _fetch(HIST.format(name=name[6:]), DATA / f"{name}.geojson")
    else:
        file = _fetch(NE.format(name=name), DATA / f"{name}.geojson")
    out = []
    for f in json.loads(file.read_text(encoding="utf-8")).get("features") or []:
        try:
            g = shape(f["geometry"])
        except Exception:  # noqa: BLE001 -- a broken feature is passed over
            continue
        if not g.is_valid:
            g = g.buffer(0)
        out.append((f.get("properties") or {}, g))
    return tuple(out)


def _country_names(p: dict) -> set[str]:
    return {_norm(p.get(k)) for k in ("NAME", "NAME_LONG", "ADMIN", "NAME_EN", "ABBREV", "NAME_ALT", "SOVEREIGNT",
                                      "FORMAL_EN") if p.get(k)} - {""}


def nearest(year: int) -> int:
    """The map year closest to `year`; on a tie the earlier one."""
    return min(YEARS, key=lambda y: (abs(y - year), y))


def _year_layer(year: int) -> tuple:
    y = nearest(year)
    return _layer(f"world_{'bc' + str(-y) if y < 0 else y}")


# ---------------------------------------------------------------- windows and shapes ---------------------------------

def bounds(region: str) -> tuple[float, float, float, float]:
    """A window by name (REGIONS), a country's own extent (its biggest part, with some of round it), or
    "LON0,LAT0,LON1,LAT1"."""
    r = str(region).strip()
    nums = re.findall(r"-?\d+(?:\.\d+)?", r)
    if len(nums) == 4 and re.fullmatch(r"[\s\d.,\-]+", r):
        a, b, c, d = (float(v) for v in nums)
        return (min(a, c), min(b, d), max(a, c), max(b, d))
    key = _norm(r.replace("_", " ").replace("-", " "))
    if key in REGIONS:
        return REGIONS[key]
    found = _country(key)
    if found is None:
        raise KeyError(f"no region {region!r}: name one of {', '.join(sorted(REGIONS))}, a country, or LON0,LAT0,LON1,LAT1")
    g = _biggest(found[1])
    lon0, lat0, lon1, lat1 = g.bounds
    pad = max(lon1 - lon0, lat1 - lat0) * 0.25 + 1
    return (lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)


def _biggest(g):
    parts = list(getattr(g, "geoms", [g]))
    big = max(parts, key=lambda p: p.area)
    # The main land and what lies near it (Japan's islands, not France's overseas parts).
    near = [p for p in parts if p.distance(big) < max(3.0, math.sqrt(big.area) * 0.6)]
    from shapely.ops import unary_union
    return unary_union(near)


# Whose view of disputed borders the countries are drawn in. Made for India: India's official borders by default
# (Natural Earth's point-of-view layer `ind`: the whole of Jammu and Kashmir and Ladakh, Aksai Chin included).
# V3_MAP_VIEW=none: Natural Earth's own (de facto); another country's code for its view (Natural Earth's
# point-of-view layers, at the fine detail only: chn, pak, usa, gbr, fra, deu, jpn, ...).
def view() -> str:
    v = re.sub(r"[^a-z]", "", os.environ.get("V3_MAP_VIEW", "ind").lower())[:4]
    return "" if v in ("none", "") else v[:3]


def countries_layer(b=None) -> str:
    return f"ne_10m_admin_0_countries_{view()}" if view() else f"ne_{detail(b) if b else '50m'}_admin_0_countries"


def detail(b) -> str:
    return "10m" if max(b[2] - b[0], b[3] - b[1]) < 100 else "50m"  # (the finer data wherever a camera may zoom in)


def countries(b) -> list[tuple[str, object]]:
    """Today's countries that show in the window (their whole shapes)."""
    from shapely.geometry import box
    clip = box(b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2)
    return [(str(p.get("NAME")), g) for p, g in _layer(countries_layer(b)) if g.intersects(clip)]


def states(year: int, b) -> list[tuple[str, object]]:
    """The states on the map nearest `year` that show in the window."""
    from shapely.geometry import box
    clip = box(b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2)
    return [(str(p.get("NAME")), g) for p, g in _year_layer(year) if p.get("NAME") and g.intersects(clip)]


ADMIN1 = "ne_10m_admin_1_states_provinces"


def _province_names(p: dict) -> set[str]:
    names = {_norm(p.get(k)) for k in ("name", "name_en", "gn_name", "woe_name")}
    names |= {_norm(x) for x in str(p.get("name_alt") or "").split("|")}
    return names - {""}


@lru_cache(None)
def _view_country(admin: str):
    """A country's whole shape in the map view (None: not in the layer)."""
    for p, g in _layer(countries_layer()):
        if admin in (p.get("ADMIN"), p.get("NAME"), p.get("NAME_LONG")):
            return g.buffer(0)
    return None


@lru_cache(None)
def _admin1() -> tuple:
    """Every state and province (name, country, shape), as the map view has them: each cut to its country's borders
    in that view; in India's, the land Pakistan holds of Kashmir is Jammu and Kashmir's and Gilgit-Baltistan and
    Aksai Chin are Ladakh's, as India's official map has them."""
    rows = [(str(p.get("name")), str(p.get("admin")), g.buffer(0)) for p, g in _layer(ADMIN1)]
    if not view():
        return tuple(rows)
    from shapely.ops import unary_union
    out = []
    for name, admin, g in rows:
        c = _view_country(admin)
        if c is not None:
            try:
                g = g.intersection(c)
            except Exception:  # noqa: BLE001
                pass
        if not g.is_empty:
            out.append([name, admin, g])
    if view() == "ind":
        india = _view_country("India")
        mine = [r for r in out if r[1] == "India"]
        if india is not None and mine:
            gap = india.difference(unary_union([r[2] for r in mine]))
            ajk = unary_union([g for n, a, g in rows if a == "Pakistan" and n == "Azad Kashmir"]).buffer(0.02)
            for r in mine:
                if r[0] == "Jammu and Kashmir":
                    r[2] = unary_union([r[2], gap.intersection(ajk)])
                elif r[0] == "Ladakh":
                    r[2] = unary_union([r[2], gap.difference(ajk)])
    return tuple(tuple(r) for r in out)


def provinces(b, of: set[str] | None = None) -> list[tuple[str, str, object]]:
    """The states and provinces (Natural Earth admin-1) that show in the window: (name, country, shape); `of`:
    only those of these countries."""
    from shapely.geometry import box
    clip = box(*b)
    return [(n, a, g) for n, a, g in _admin1() if (of is None or a in of) and g.intersects(clip)]


def province(key: str, b=None):
    """A state or province by name (Uttar Pradesh, Bavaria, Texas), the one in the window when two share a name."""
    shapes = {(n, a): g for n, a, g in _admin1()}
    hit = [(p, shapes.get((str(p.get("name")), str(p.get("admin"))), g)) for p, g in _layer(ADMIN1)
           if key in _province_names(p)]
    if not hit:
        return None
    if b is not None and len(hit) > 1:
        from shapely.geometry import box
        clip = box(*b)
        hit.sort(key=lambda pg: -pg[1].intersection(clip).area)
    return hit[0][1], str(hit[0][0].get("name"))


def land(b):
    """All the land in the window, one shape (the coast, with no borders drawn in it)."""
    from shapely.ops import unary_union
    return unary_union([g for _, g in countries(b)])


def _country(key: str):
    for p, g in _layer(countries_layer()):
        if key in _country_names(p):
            return str(p.get("NAME")), g
    return None


def shape(name: str, year: int | None = None, b=None):
    """(shape, its name on the map): today's country, or with `year` the state of that time (by its name, a shorter
    form of it, or the overlord its parts are subject to), else a sea by name. KeyError naming what there is."""
    key = _norm(name.replace("_", " "))
    key = {"england": "english territory"}.get(key, key) if year is not None else key
    from shapely.ops import unary_union
    if year is not None:
        feats = [(p, g) for p, g in _year_layer(year) if p.get("NAME")]
        hit = [(p, g) for p, g in feats if _norm(p["NAME"]) == key or _norm(p.get("SUBJECTO")) == key
               or _norm(p.get("PARTOF")) == key]
        if not hit and len(key) >= 4:
            hit = [(p, g) for p, g in feats if key in _norm(p["NAME"]).split() or _norm(p["NAME"]).startswith(key)
                   or key.startswith(_norm(p["NAME"]) + " ") or _norm(p["NAME"]).endswith(" " + key)]
        if hit:
            # (several states made one: the slivers the data leaves between neighbours closed, no spikes inside)
            g = unary_union([g.buffer(0.06) for _, g in hit]).buffer(-0.06) if len(hit) > 1 else hit[0][1]
            return g, str(max(hit, key=lambda pg: pg[1].area)[0]["NAME"])
    if b is not None and detail(b) == "10m":
        for p, g in _layer(countries_layer(b) if view() else "ne_10m_admin_0_countries"):
            if key in _country_names(p):
                return g, str(p.get("NAME"))
    found = _country(key)
    if found:
        return found[1], found[0]
    for p, g in _layer("ne_50m_admin_0_map_units"):     # a country's parts: England, Scotland, Flanders...
        if key in {_norm(p.get(k)) for k in ("NAME", "NAME_LONG", "GEOUNIT", "NAME_EN")}:
            return g, str(p.get("NAME"))
    found = province(key, b)                        # a state or province: Uttar Pradesh, Bavaria, Texas
    if found:
        return found
    for p, g in _layer("ne_10m_geography_marine_polys"):
        if key in {_norm(p.get("name")), _norm(p.get("name_en")), _norm(p.get("namealt"))} - {""}:
            return g, str(p.get("name"))
    have = sorted({n for n, _ in states(year, b)}) if (year is not None and b) else []
    raise KeyError(f"no country or state {name!r}" + (f" in {nearest(year)}; that map has: {', '.join(have)[:600]}"
                                                       if have else ""))


def rivers(b) -> list[tuple[str, object]]:
    from shapely.geometry import box
    clip = box(*b)
    return [(str(p.get("name") or ""), g) for p, g in _layer("ne_50m_rivers_lake_centerlines") if g.intersects(clip)]


def river(name: str):
    key = _norm(name.replace("_", " "))
    key = re.sub(r"^river ", "", re.sub(r" river$", "", key))
    from shapely.ops import unary_union
    hit = [g for p, g in _layer("ne_50m_rivers_lake_centerlines")
           if key in {_norm(p.get("name")), _norm(p.get("name_en")), _norm(p.get("name_alt"))}]
    if not hit:
        raise KeyError(f"no river {name!r}")
    return unary_union(hit)


# ---------------------------------------------------------------- places ---------------------------------------------

@lru_cache(None)
def _towns() -> dict:
    out: dict = {}
    for p, g in _layer("ne_10m_populated_places_simple"):
        row = (float(p.get("longitude") or g.x), float(p.get("latitude") or g.y), float(p.get("pop_max") or 0))
        for k in ("name", "nameascii", "namealt", "namepar", "meganame", "ls_name"):
            for n in str(p.get(k) or "").split("|"):
                if _norm(n):
                    out.setdefault(_norm(n), []).append(row)
    return out


@lru_cache(None)
def _extra() -> dict:
    out = {}
    file = HERE / "data" / "places_extra.csv"
    if file.exists():
        rows = [ln for ln in file.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
        for r in csv.DictReader(rows):
            for n in [r["name"]] + [a for a in (r.get("aliases") or "").split("|") if a]:
                out.setdefault(_norm(n), (float(r["lon"]), float(r["lat"])))
    return out


def _inside(pt, b, pad: float = 0.0) -> bool:
    if not b:
        return True
    return b[0] - pad <= pt[0] <= b[2] + pad and b[1] - pad <= pt[1] <= b[3] + pad


def place(name: str, b=None) -> tuple[float, float]:
    """(lon, lat) of a place by name: a town (the most populous of that name, one on the map first), an old name,
    a site of the past, a sea or a region, a country's middle; else OpenStreetMap, asked once and cached."""
    key = _norm(name.replace("_", " "))
    keys = [key] + ([ALIASES[key]] if key in ALIASES else [])
    found = []
    for k in keys:
        if k in OLD_PLACES:
            found.append(OLD_PLACES[k])
        rows = sorted(_towns().get(k, []), key=lambda r: (_inside(r, b), r[2]), reverse=True)
        if rows:
            found.append(rows[0][:2])
        if k in _extra():
            found.append(_extra()[k])
    for p, g in _layer("ne_10m_geography_marine_polys") + _layer("ne_50m_geography_regions_points"):
        if key in {_norm(p.get("name")), _norm(p.get("name_en")), _norm(p.get("namealt"))} - {""}:
            pt = g.representative_point()
            found.append((pt.x, pt.y))
    for k in keys:
        c = _country(k)
        if c:
            pt = _biggest(c[1]).representative_point()
            found.append((pt.x, pt.y))
    for pt in found:
        if _inside(pt, b, 2):
            return pt
    if found:
        return found[0]
    pt = _nominatim(name, b)
    if pt:
        return pt
    raise KeyError(f"no place named {name!r}")


def _nominatim(name: str, b=None):
    """OpenStreetMap's answer for a name, once (cached in .cache/geo/places.json, misses too). V3_GEOCODE=0: off."""
    if os.environ.get("V3_GEOCODE", "1") == "0":
        return None
    file = DATA / "places.json"
    try:
        cache = json.loads(file.read_text()) if file.exists() else {}
    except ValueError:
        cache = {}
    key = f"{_norm(name)}|{','.join(f'{v:.0f}' for v in b) if b else ''}"
    if key in cache:
        return tuple(cache[key]) if cache[key] else None
    pt = None
    try:
        q = {"q": name.replace("_", " "), "format": "json", "limit": 5}
        if b:
            q["viewbox"] = f"{b[0]},{b[3]},{b[2]},{b[1]}"
        req = urllib.request.Request("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(q),
                                     headers={"User-Agent": "pocketanim-v3 (explainer maps)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            rows = json.loads(r.read().decode())
        rows.sort(key=lambda r: (_inside((float(r["lon"]), float(r["lat"])), b, 2),
                                 r.get("class") in ("place", "boundary", "historic", "natural"),
                                 float(r.get("importance") or 0)), reverse=True)
        if rows:
            pt = (float(rows[0]["lon"]), float(rows[0]["lat"]))
    except Exception:  # noqa: BLE001 -- offline: not found
        return None
    cache[key] = list(pt) if pt else None
    DATA.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(cache))
    return pt


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["--fetch"]:
        fetch_all()
        for y in sys.argv[2:]:
            _year_layer(int(y))
        print("map data in", DATA)
