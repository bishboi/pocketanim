"""The map's places: seas, gulfs, straits and peaks from Natural Earth; the rest found by the map agent
(harness/lecture/map_agent.py) and drawn from the script's own "places"."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from forge.util import LECTURE  # noqa: F401 -- puts harness/lecture on the path

import compile_lecture as cl  # noqa: E402
import map_agent  # noqa: E402
import pocket_lecture as pl  # noqa: E402

REGION = {"country": "Sri Lanka"}


def _script(places=None):
    beats = [
        {"say": "Sri Lanka lies across the Gulf of Mannar and the Palk Strait from India.",
         "do": [{"op": "marker", "place": "Gulf of Mannar"}, {"op": "marker", "place": "Palk Strait"},
                {"op": "marker", "place": "Bay of Bengal"}]},
        {"say": "A chain of shoals, Adam's Bridge, almost joins the two.",
         "do": [{"op": "marker", "place": "Adam's Bridge"}]},
        {"say": "The highest peak is Pidurutalagala, in the Central Highlands.",
         "do": [{"op": "marker", "place": "Pidurutalagala"}, {"op": "relief", "names": ["Central Highlands"]}]},
        {"say": "The south-west is the Wet Zone; the north and east are the Dry Zone.",
         "do": [{"op": "state", "name": "Wet Zone"}, {"op": "state", "name": "Dry Zone"}]},
    ]
    script = {"title": "Sri Lanka", "style": "atlas", "auto_visuals": False, "place_figures": False,
              "region": dict(REGION), "chapters": [{"title": "The island", "beats": beats}]}
    if places is not None:
        script["places"] = places
    return script


@pytest.fixture(autouse=True)
def _no_places():
    yield
    pl.set_places({})


def test_seas_straits_and_peaks_come_from_natural_earth():
    bounds = pl.map_bounds(REGION)
    for name in ("Gulf of Mannar", "Palk Strait", "Pidurutalagala"):
        assert pl._inside(pl.place(name, "Sri Lanka", bounds), bounds), name
    # A sea that reaches far off the map is named where it is on the map.
    lon, lat = pl.place("Bay of Bengal", "Sri Lanka", bounds)
    assert pl._inside((lon, lat), bounds) and lat > 7.5 and lon > 80.5
    assert pl.area_shape("Bay of Bengal").area > 10


def test_the_agent_is_asked_only_what_the_gazetteers_cannot_find():
    script = _script()
    missing = [e["name"] for e in map_agent.map_names(script) if not map_agent.found_here(e, script)]
    assert missing == ["Adam's Bridge", "Central Highlands", "Wet Zone", "Dry Zone"]


def test_the_scripts_own_places_are_drawn_and_checked():
    places = {"Adam's Bridge": {"lonlat": [79.55, 9.12]},
              "Wet Zone": {"states": ["Colombo", "Galle", "Kalutara", "Ratnapura"]},
              "Dry Zone": {"outline": [[79.6, 9.9], [80.3, 9.9], [81.9, 7.3], [81.5, 6.3], [80.9, 7.6], [79.8, 8.0]]},
              "Central Highlands": {"outline": [[80.4, 7.5], [81.0, 7.5], [81.1, 6.8], [80.5, 6.6]],
                                    "kind": "mountains"},
              "Nowhere": {"lonlat": "here"}}
    script = _script(places)
    errors, warnings = cl.lint(json.loads(json.dumps(script)))
    assert not errors
    assert not any("no place named" in w or "off this map" in w for w in warnings), warnings
    assert any("'Nowhere'" in w and "left out" in w for w in warnings)
    source = cl.compile_script(json.loads(json.dumps(script)))
    assert "set_places({" in source and "'Wet Zone'" in source and "Nowhere" not in source
    pl.set_places(places, "Sri Lanka")
    wet, dry = pl.area_shape("Wet Zone", "Sri Lanka"), pl.area_shape("Dry Zone", "Sri Lanka")
    assert wet.area > 0.3 and dry.area > 0.5 and not dry.buffer(-0.01).intersects(pl._box((79.0, 4.0, 79.55, 6.0)))
    assert dry.within(pl.country("Sri Lanka").buffer(0.01))           # an outline is cut to the land
    assert map_agent._range_known("Central Highlands", pl.map_bounds(REGION))


def _serve(replies):
    """A local model: each POST gets the next reply; the requests it got."""
    got = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got.append((self.path, body))
            reply = replies[min(len(got) - 1, len(replies) - 1)]
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", got, server


def _call(i, tool, **args):
    return {"id": f"c{i}", "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}


def test_the_agent_places_what_is_missing_through_openrouter(tmp_path, monkeypatch):
    monkeypatch.setattr(map_agent, "CACHE", tmp_path / "places.json")
    calls = [_call(1, "provinces"),
             _call(2, "set_place", name="Adam's Bridge", lonlat=[79.55, 9.12], source="Wikidata Q1137089"),
             _call(3, "set_place", name="Wet Zone", lonlat=[80.0, 6.8], source="a guess"),          # an area: refused
             _call(4, "set_place", name="Wet Zone", states=["Colombo", "Gampaha", "Kalutara", "Galle", "Matara",
                                                             "Ratnapura", "Kegalle"], source="Wikipedia: Wet zone"),
             _call(5, "set_place", name="Dry Zone", outline=[[79.6, 9.9], [80.3, 9.9], [81.9, 7.3], [81.5, 6.3],
                                                             [80.9, 7.6], [79.8, 8.0]], source="Wikipedia: Dry zone"),
             _call(6, "give_up", name="Central Highlands", why="no outline found")]
    replies = [{"choices": [{"message": {"content": "", "tool_calls": calls}}], "usage": {"cost": 0.002}},
               {"choices": [{"message": {"content": "Done."}}], "usage": {"cost": 0.001}}]
    url, got, server = _serve(replies)
    monkeypatch.setenv("OPENROUTER_URL", url)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PANIM_MAP_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setattr(map_agent, "nominatim", lambda *a, **k: [])
    try:
        script = _script()
        log: list = []
        report = map_agent.resolve(script, log)
        # Kept for the next build, which asks only what was not found.
        again = _script()
        second = map_agent.resolve(again)
    finally:
        server.shutdown()
    assert report["asked"] == ["Adam's Bridge", "Central Highlands", "Wet Zone", "Dry Zone"]
    assert set(report["resolved"]) == {"Adam's Bridge", "Wet Zone", "Dry Zone"}
    assert report["gave_up"] == {"Central Highlands": "no outline found"}
    assert report["usd"] == pytest.approx(0.002) and report["model"] == "google/gemini-2.5-flash"
    assert script["places"]["Wet Zone"]["states"][0] == "Colombo"
    assert script["places"]["Adam's Bridge"]["source"] == "Wikidata Q1137089"
    first = got[0][1]
    assert first["plugins"] == [{"id": "web", "max_results": 5}]          # it may search the web
    assert {t["function"]["name"] for t in first["tools"]} == {"search_place", "provinces", "set_place", "give_up"}
    assert "Adam's Bridge" in first["messages"][1]["content"]
    results = {entry["call"]: entry["result"] for entry in log if "call" in entry}
    assert "Trincomalee" in results["provinces"]                         # the provinces by their English names
    refused = [e for e in log if e.get("call") == "set_place" and e["result"].startswith("error")]
    assert refused and "area" in refused[0]["result"]
    assert second["asked"] == ["Central Highlands"] and again["places"]["Wet Zone"]["states"]
    assert "Central Highlands" in map_agent.summary(second) and "Wet Zone (provinces" in map_agent.summary(second)


def test_the_agent_uses_openais_web_search_for_an_openai_model(tmp_path, monkeypatch):
    monkeypatch.setattr(map_agent, "CACHE", tmp_path / "places.json")
    first = {"output": [{"type": "web_search_call", "id": "ws1", "status": "completed",
                         "action": {"type": "search", "query": "Adam's Bridge coordinates"}},
                        {"type": "function_call", "id": "fc1", "call_id": "call1", "name": "set_place",
                         "arguments": json.dumps({"name": "Adam's Bridge", "lonlat": [79.55, 9.12],
                                                  "source": "en.wikipedia.org/wiki/Adam's_Bridge"})}],
             "usage": {"input_tokens": 1000, "output_tokens": 100}}
    last = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}],
            "usage": {"input_tokens": 1200, "output_tokens": 20}}
    url, got, server = _serve([first, last])
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_BASE_URL", url)
    monkeypatch.setenv("PANIM_MAP_MODEL", "openai/gpt-6-luna")
    try:
        script = _script()
        script["chapters"][0]["beats"] = script["chapters"][0]["beats"][1:2]          # only Adam's Bridge
        log: list = []
        report = map_agent.resolve(script, log)
    finally:
        server.shutdown()
    assert report["resolved"]["Adam's Bridge"]["lonlat"] == [79.55, 9.12]
    path, body = got[0]
    assert path == "/responses" and body["model"] == "gpt-6-luna" and {"type": "web_search"} in body["tools"]
    assert body["reasoning"] == {"effort": "low"} and "reasoning.encrypted_content" in body["include"]
    assert len(got) == 1                                     # every name placed: no turn more
    assert any(e.get("call") == "set_place" and e["result"].startswith("kept") for e in log)
    assert {"search": "Adam's Bridge coordinates"} in log
