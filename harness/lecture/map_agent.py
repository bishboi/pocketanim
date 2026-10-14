"""The map agent: finds the places a lecture's map names that the gazetteers do not know, and how to draw them.

The writer names places as a teacher would: towns, seas, straits, peaks, a country's own names for its regions
("the Wet Zone", "the Central Highlands"), a chain of shoals ("Adam's Bridge"). Most are found without help:
Natural Earth's towns, seas, gulfs, straits, peaks and ranges, data/places_extra.csv, GeoNames, OpenStreetMap
(pocket_lecture.place, area_shape, relief). The rest went missing from the video ("no place named ...").

This step runs before the compile. It lists every place the script's map ops name, looks each one up as the
render will, and gives the ones not found to a model with tools to find them, as the Manim model is given the
figures to write:
  search_place(query)      the gazetteers here, then OpenStreetMap (Nominatim, Photon) and Wikidata's coordinates
  provinces()              the map country's first-level divisions, to build an area from (the Wet Zone: the
                           south-western provinces)
  set_place(name, ...)     a point [lon, lat]; an area from provinces or an outline of [lon, lat] points (cut to
                           the land); "kind": "mountains" for a range -- checked to lie on the map before kept
  give_up(name, why)
and the web (llm.agent: OpenAI's web_search, or OpenRouter's web plugin) to read what a name is and where.

What it finds goes into the script's "places" (pocket_lecture.set_places reads them), each with its source; it is
kept in .cache/map_places.json, so a rebuild asks nothing again. The model is PANIM_MAP_MODEL, else
PANIM_MANIM_MODEL, else OPENROUTER_MODEL. PANIM_MAP_AGENT=off turns the step off.

    .venv/bin/python harness/lecture/map_agent.py script.json [out.json]

reads a lecture script, writes it with its places to out.json (or back), keeps the whole log beside it
(out.json.map.json), and prints a summary as the last line of stdout: {"ok", "names", "found_here", "asked",
"resolved", "gave_up", "usd", "model", "seconds", "errors"}.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from chirp import _env  # noqa: E402

CACHE = HERE / ".cache" / "map_places.json"
TURNS = 18
UA = {"User-Agent": "pocketanim-lecture/0.4 (map lectures)"}


def enabled() -> bool:
    return (_env("PANIM_MAP_AGENT") or "on").strip().lower() not in ("off", "0", "no")


def model() -> str:
    import llm

    return _env("PANIM_MAP_MODEL") or _env("PANIM_MANIM_MODEL") or llm.model("PANIM_MAP_MODEL")


# ---------------- what the map names ----------------

def map_names(script: dict) -> list[dict]:
    """Every place the script's map ops name, once each: {"name", "kind" (point, area or mountains), "at", "said"}."""
    out: dict[str, dict] = {}

    def add(name, kind, at, said):
        if not isinstance(name, str) or not name.strip():
            return
        key = name.strip().lower()
        if key not in out:
            out[key] = {"name": name.strip(), "kind": kind, "at": at, "said": said}

    for ci, chapter in enumerate(script.get("chapters") or [], 1):
        if chapter.get("map") is False:
            continue
        for bi, beat in enumerate(chapter.get("beats") or [], 1):
            at, said = f"chapter {ci} beat {bi}", str(beat.get("say") or "")[:300]
            for op in beat.get("do") or []:
                if not isinstance(op, dict):
                    continue
                kind = op.get("op")
                if kind == "marker":
                    add(op.get("place"), "point", at, said)
                elif kind == "state":
                    add(op.get("name"), "area", at, said)
                elif kind == "relief":
                    for name in op.get("names") or []:
                        add(name, "mountains", at, said)
                elif kind == "journey":
                    for stop in op.get("stops") or []:
                        add(stop, "point", at, said)
                elif kind in ("arrow", "path"):
                    for point in op.get("points") or []:
                        add(point, "point", at, said)
                elif kind == "icon":
                    for spot in op.get("places") or []:
                        add(spot, "point", at, said)
    return list(out.values())


def _home(script: dict) -> str | None:
    region = script.get("region") if isinstance(script.get("region"), dict) else {}
    return region.get("country") if not (region.get("area") or region.get("continent")) else None


def found_here(entry: dict, script: dict) -> bool:
    """Whether the render will find this name on its map without help."""
    import pocket_lecture as pl

    region = script.get("region") or {}
    bounds = pl.map_bounds(region)
    home = _home(script)
    name, kind = entry["name"], entry["kind"]
    try:
        if kind == "point":
            return pl._inside(pl.place(name, home, bounds), bounds)
        if kind == "area":
            try:
                shape = pl.state(name, home)
            except KeyError:
                shape = pl.area_shape(name, home)
            return not bounds or shape.intersects(pl._box(bounds))
        return _range_known(name, bounds)
    except (KeyError, TypeError, ValueError):
        return False


def _range_known(name: str, bounds) -> bool:
    """A range relief() draws by this name on this map: Natural Earth's, or the lecture's own."""
    import pocket_lecture as pl

    if pl.own_place(name) and pl._own_shape(pl._norm(name)) is not None:
        return True
    wanted = pl._norm(name)
    box = pl._box(bounds) if bounds else None
    for attrs, geom in pl._records("geography_regions_polys", "physical", "10m"):
        if attrs.get("FEATURECLA") not in pl.MapLecture.RELIEF_KINDS or (box is not None and not geom.intersects(box)):
            continue
        own = pl._norm(attrs.get("NAME") or "")
        if wanted and (wanted in own or own in wanted):
            return True
    return False


# ---------------- the tools ----------------

def _get(url: str, timeout: float = 10) -> object:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def nominatim(query: str, bounds=None) -> list[dict]:
    params = {"q": query, "format": "json", "limit": 6, "extratags": 0}
    if bounds:
        params["viewbox"] = f"{bounds[0]},{bounds[3]},{bounds[2]},{bounds[1]}"
    rows = _get("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params))
    return [{"from": "OpenStreetMap", "name": r.get("display_name", "")[:120],
             "what": f"{r.get('class')}/{r.get('type')}",
             "lonlat": [round(float(r["lon"]), 4), round(float(r["lat"]), 4)],
             "bbox": [round(float(v), 3) for v in (r.get("boundingbox") or [])]} for r in rows or []]


def photon(query: str) -> list[dict]:
    data = _get("https://photon.komoot.io/api/?" + urllib.parse.urlencode({"q": query, "limit": 5}))
    out = []
    for f in (data or {}).get("features") or []:
        p, c = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or [None, None]
        if c[0] is None:
            continue
        out.append({"from": "Photon (OpenStreetMap)", "name": ", ".join(str(x) for x in (p.get("name"), p.get("state"),
                    p.get("country")) if x), "what": f"{p.get('osm_key')}/{p.get('osm_value')}",
                    "lonlat": [round(float(c[0]), 4), round(float(c[1]), 4)]})
    return out


def wikidata(query: str) -> list[dict]:
    found = _get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbsearchentities", "search": query, "language": "en", "format": "json", "limit": 5}))
    ids = [row["id"] for row in (found or {}).get("search") or []]
    if not ids:
        return []
    data = _get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|descriptions|claims", "languages": "en",
         "format": "json"}))
    out = []
    for qid in ids:
        entity = ((data or {}).get("entities") or {}).get(qid) or {}
        claims = (entity.get("claims") or {}).get("P625") or []
        value = (((claims[0] if claims else {}).get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        if "longitude" not in value:
            continue
        out.append({"from": f"Wikidata {qid}", "name": ((entity.get("labels") or {}).get("en") or {}).get("value", ""),
                    "what": ((entity.get("descriptions") or {}).get("en") or {}).get("value", ""),
                    "lonlat": [round(float(value["longitude"]), 4), round(float(value["latitude"]), 4)]})
    return out


class Session:
    """One script's unfound names, the tools the model calls on them, and what it decided."""

    def __init__(self, script: dict, wanted: list[dict]):
        import pocket_lecture as pl

        self.pl = pl
        self.script = script
        self.region = script.get("region") or {}
        self.home = _home(script)
        self.bounds = pl.map_bounds(self.region)
        self.wanted = {w["name"]: w for w in wanted}
        self.places: dict[str, dict] = {}
        self.gave_up: dict[str, str] = {}

    def done(self) -> bool:
        return all(n in self.places or n in self.gave_up for n in self.wanted)

    def handle(self, name: str, args: dict) -> str:
        if name == "search_place":
            return self.search(str(args.get("query") or ""))
        if name == "provinces":
            return self.provinces()
        if name == "set_place":
            return self.set_place(args)
        if name == "give_up":
            who = str(args.get("name") or "")
            if who not in self.wanted:
                return f"error: {who!r} is not one of the names to find ({', '.join(self.wanted)})"
            self.gave_up[who] = str(args.get("why") or "not found")
            return "noted: it is left off the map"
        return f"error: no tool {name!r}"

    def search(self, query: str) -> str:
        pl = self.pl
        if not query.strip():
            return "error: give a query"
        rows: list[dict] = []
        try:
            point = pl.place(query, self.home, self.bounds)
            rows.append({"from": "the gazetteer here", "name": query,
                         "lonlat": [round(point[0], 4), round(point[1], 4)]})
        except KeyError:
            pass
        feature = pl.physical_feature(query, self.bounds)
        if feature:
            p = pl._shape_point(feature[0], self.bounds)
            rows.append({"from": "Natural Earth", "name": query, "what": feature[1], "lonlat": list(p)})
        problems = []
        for source in (lambda: nominatim(query, self.bounds), lambda: photon(query), lambda: wikidata(query)):
            try:
                rows += source()
            except Exception as error:  # noqa: BLE001 -- one source down: the others still answer
                problems.append(f"{type(error).__name__}: {str(error)[:80]}")
        for row in rows:
            row["on_map"] = pl._inside(row["lonlat"], self.bounds)
        box = [round(v, 2) for v in self.bounds] if self.bounds else None
        out = {"map": {"region": self.region, "lon_lat_bounds": box}, "results": rows[:14]}
        if problems:
            out["unreachable"] = problems
        return json.dumps(out, ensure_ascii=False)

    def provinces(self) -> str:
        pl = self.pl
        if not self.home:
            return "error: this map is not of one country, so it has no provinces to build from"
        english = {}
        for attrs, _geom in pl._records("admin_1_states_provinces"):
            if pl._norm(self.home) in (pl._norm(attrs.get("admin")), pl._norm(attrs.get("adm0_a3"))):
                english[str(attrs.get("name"))] = (attrs.get("name_en"), attrs.get("type_en"), attrs.get("region"))
        rows = []
        for name, geom in pl.states_of(self.home):
            c = geom.representative_point()
            x0, y0, x1, y1 = geom.bounds
            en, kind, within = english.get(name, (None, None, None))
            row = {"name": en or name, "centre": [round(c.x, 3), round(c.y, 3)],
                   "bounds": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]}
            if en and en != name:
                row["local_name"] = name
            if kind:
                row["kind"] = kind
            if within:
                row["in"] = within
            rows.append(row)
        return json.dumps({"country": self.home, "provinces": rows}, ensure_ascii=False)

    def set_place(self, args: dict) -> str:
        pl = self.pl
        name = str(args.get("name") or "")
        if name not in self.wanted:
            return f"error: {name!r} is not one of the names to find ({', '.join(self.wanted)})"
        spec: dict = {}
        if args.get("lonlat") is not None:
            spec["lonlat"] = [float(v) for v in args["lonlat"]][:2]
        if args.get("states"):
            spec["states"] = [str(s) for s in args["states"]]
        if args.get("outline"):
            spec["outline"] = [[float(p[0]), float(p[1])] for p in args["outline"]]
        if args.get("kind") == "mountains" or self.wanted[name]["kind"] == "mountains":
            spec["kind"] = "mountains"
        if args.get("sea"):
            spec["sea"] = True
        if not ({"lonlat", "states", "outline"} & set(spec)):
            return "error: give lonlat [lon, lat], or states (province names), or outline ([[lon, lat], ...])"
        if self.wanted[name]["kind"] != "point" and "lonlat" in spec and not ({"states", "outline"} & set(spec)):
            return (f"error: {name!r} is shaded on the map as an area: give states or an outline, not one point")
        unknown = [s for s in spec.get("states", []) if not self._province(s)]
        if unknown:
            return f"error: no province {unknown[0]!r} in {self.home} (call provinces for their names)"
        # Checked as the render will draw it.
        previous = {v["_name"]: {k: x for k, x in v.items() if not k.startswith("_")} for v in pl.PLACES.values()}
        trial = {**previous, name: spec}
        pl.set_places(trial, self.home)
        try:
            if "lonlat" in spec and not ({"states", "outline"} & set(spec)):
                where = pl.place(name, self.home, self.bounds)
                if not pl._inside(where, self.bounds):
                    raise ValueError(f"{where} is off this map {self.bounds}")
                said = f"a point at {list(where)}"
            else:
                shape = pl._own_shape(pl._norm(name))
                if shape is None or shape.is_empty:
                    raise ValueError("it draws nothing (an outline off the land? give \"sea\": true for water)")
                if self.bounds and not shape.intersects(pl._box(self.bounds)):
                    raise ValueError(f"it is off this map {self.bounds}")
                x0, y0, x1, y1 = shape.bounds
                said = f"an area of {shape.area:.2f} square degrees, from {x0:.2f},{y0:.2f} to {x1:.2f},{y1:.2f}"
        except (ValueError, KeyError) as error:
            pl.set_places(previous, self.home)
            return f"error: not kept: {error}"
        spec["source"] = str(args.get("source") or "")[:300]
        self.places[name] = spec
        return f"kept: {name!r} as {said}"

    def _province(self, name: str) -> bool:
        try:
            self.pl.state(name, self.home)
            return True
        except KeyError:
            return False


TOOLS = [
    {"name": "search_place", "description": "Look a name up: the gazetteers here, OpenStreetMap (Nominatim, Photon) "
     "and Wikidata's coordinates. Returns candidates with [lon, lat] and whether each is on this map.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "provinces", "description": "The map country's first-level divisions (provinces, states, districts) with "
     "their centres and bounds: an area of the lecture is best built from them where it follows them.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "set_place", "description": "Keep where a name is. A point: lonlat [lon, lat]. An area (or range): "
     "states (province names from provinces) and/or outline (6-30 [lon, lat] points round it, in order; cut to the "
     "land unless sea is true); kind \"mountains\" for a range. Checked on the map: an error says why it was not "
     "kept.",
     "parameters": {"type": "object", "properties": {
         "name": {"type": "string", "description": "exactly as listed"},
         "lonlat": {"type": "array", "items": {"type": "number"}},
         "states": {"type": "array", "items": {"type": "string"}},
         "outline": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
         "kind": {"type": "string", "enum": ["point", "area", "mountains"]},
         "sea": {"type": "boolean"},
         "source": {"type": "string", "description": "where this comes from (a URL, Wikidata id, the gazetteer)"}},
         "required": ["name", "source"]}},
    {"name": "give_up", "description": "A name that cannot be placed truthfully: it is left off the map.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "why": {"type": "string"}},
                    "required": ["name", "why"]}},
]

SYSTEM = """You place names on the map of a narrated lecture. Each name below is one the lecture's map draws -- a \
point (a marker, a journey's stop), an area (shaded) or a range of mountains -- and that the gazetteers did not find. \
For each, find out what it is and where it really is (search the web, search_place, provinces), then set_place it, \
or give_up when it cannot be placed truthfully.

- A point: its real [lon, lat] from a source (Wikidata, OpenStreetMap, an encyclopedia); for a long feature (a \
chain of shoals, a bridge, a strait) its middle.
- An area: the provinces it is made of when it follows them; else an outline of 6-30 [lon, lat] points that traces \
it as the sources describe (the zone south-west of the hills, the land below 300 m...). It is cut to the land.
- A range: its outline, kind "mountains".
- Never guess a place you could not find; never move a name to a different thing. Say your source in set_place.
Finish when every name is set or given up. Be quick: a few searches a name."""


def _cache() -> dict:
    try:
        return json.loads(CACHE.read_text()) if CACHE.exists() else {}
    except ValueError:
        return {}


def _cache_key(script: dict, entry: dict) -> str:
    region = script.get("region") or {}
    where = "|".join(str(region.get(k) or "") for k in ("country", "state", "area", "continent"))
    return f"{where}|{entry['name'].lower()}|{entry['kind']}"


def resolve(script: dict, log: list | None = None) -> dict:
    """Find the script's unfound map names and put what is found in script["places"]. Returns the report."""
    import pocket_lecture as pl

    started = time.time()
    log = log if log is not None else []
    report = {"ok": True, "names": 0, "found_here": 0, "asked": [], "resolved": {}, "gave_up": {}, "usd": 0.0,
              "model": None, "errors": []}
    if not isinstance(script.get("region"), dict) or not script.get("region"):
        return report
    places = dict(script.get("places") or {}) if isinstance(script.get("places"), dict) else {}
    pl.set_places(places, _home(script))
    names = map_names(script)
    report["names"] = len(names)
    missing = []
    for entry in names:
        if found_here(entry, script):
            report["found_here"] += 1
        else:
            missing.append(entry)
    cache = _cache()
    asked = []
    for entry in missing:
        kept = cache.get(_cache_key(script, entry))
        if kept:
            places[entry["name"]] = kept
            report["resolved"][entry["name"]] = {**kept, "from": "cache"}
        else:
            asked.append(entry)
    report["asked"] = [e["name"] for e in asked]
    if asked and enabled():
        import llm

        if not llm.configured():
            report["errors"].append("no key for the map model (OPENROUTER_API_KEY or OPENAI_API_KEY)")
        else:
            pl.set_places(places, _home(script))
            session = Session(script, asked)
            report["model"] = model()
            lines = [f"The map: {json.dumps(script.get('region'))}, lon/lat bounds "
                     f"{[round(v, 2) for v in session.bounds] if session.bounds else 'the world'}.",
                     f"The lecture: {script.get('title', '')}.", "", "Names to place:"]
            for e in asked:
                lines.append(f"- {e['name']!r} ({e['kind']}), {e['at']}: \"{e['said']}\"")
            words, spent, error = llm.agent(report["model"], SYSTEM, "\n".join(lines), TOOLS, session.handle,
                                            session.done, TURNS, log)
            report["usd"] = round(spent, 5)
            if error:
                report["errors"].append(error)
            for name, spec in session.places.items():
                places[name] = spec
                report["resolved"][name] = spec
                cache[_cache_key(script, session.wanted[name])] = spec
            for name in session.wanted:
                if name not in session.places:
                    report["gave_up"][name] = session.gave_up.get(name) or (error or words or "not answered")[:200]
            try:
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
            except OSError:
                pass
    elif asked:
        report["gave_up"] = {e["name"]: "the map agent is off (PANIM_MAP_AGENT)" for e in asked}
    if places:
        script["places"] = places
    report["seconds"] = round(time.time() - started, 1)
    return report


def _how(spec: dict) -> str:
    if spec.get("states"):
        return "provinces " + ", ".join(spec["states"])
    return "an outline" if spec.get("outline") else f"at {spec.get('lonlat')}"


def summary(report: dict) -> str:
    """The report in a sentence, for the app's log and page."""
    if not report.get("names"):
        return "no places on the map"
    text = f"{report['names']} places on the map, {report['found_here']} found by the gazetteers"
    if report.get("resolved"):
        text += "; placed: " + ", ".join(f"{n} ({_how(s)})" for n, s in report["resolved"].items())
    if report.get("gave_up"):
        text += "; left off: " + ", ".join(f"{n} ({why[:80]})" for n, why in report["gave_up"].items())
    if report.get("model"):
        text += f" [{report['model']}, ${report.get('usd', 0):.4f}, {report.get('seconds', 0)} s]"
    if report.get("errors"):
        text += " Problems: " + " | ".join(report["errors"][:3])
    return text


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else source
    script = json.loads(source.read_text(encoding="utf-8"))
    style = script.get("style")
    if style:
        os.environ.setdefault("LECTURE_STYLE", str(style))
    log: list = []
    try:
        report = resolve(script, log)
    except Exception as error:  # noqa: BLE001 -- the lecture goes on without the agent; the reason is shown
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"[:400]}))
        return 0
    out.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    Path(f"{out}.map.json").write_text(json.dumps({**report, "log": log}, indent=1, ensure_ascii=False))
    print(json.dumps({**report, "summary": summary(report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
