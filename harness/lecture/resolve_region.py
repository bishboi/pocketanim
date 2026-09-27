"""Find the place a piece of content is about, as a lecture REGION.

The offline fixture has no model to ask, so it reads the content for the
first-level division or country it names, preferring the more specific one:
"The Thar desert of Rajasthan" is Rajasthan, in India. Prints one JSON object:

    {"region": {"state": "Rajasthan", "country": "India"}}   or   {"region": null}

Usage:
    python harness/lecture/resolve_region.py "text ..."
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Words that are also place names but almost never mean the place in a lesson.
COMMON = {"georgia", "chad", "jordan", "turkey", "guinea", "niger", "china", "victoria", "washington",
          "delhi", "punjab"}


def resolve(text: str) -> dict | None:
    from pocket_lecture import _norm, _records

    # A place is named with a capital: "the rivers of India" is not Rivers
    # State, Nigeria. Match on the capitalised words only, lower-cased.
    proper = " ".join(w for w in re.findall(r"[A-Za-z][\w'-]*", text) if w[0].isupper())
    words = f" {_norm(proper)} "

    states = []
    for attrs, _geom in _records("admin_1_states_provinces"):
        name = _norm(attrs.get("name"))
        if len(name) >= 4 and name not in COMMON and f" {name} " in words:
            states.append((len(name), str(attrs.get("name")), str(attrs.get("admin"))))
    countries = []
    for attrs, _geom in _records("admin_0_countries"):
        if any(len(n) >= 4 and f" {n} " in words for n in (_norm(attrs.get("ADMIN")), _norm(attrs.get("NAME")))):
            countries.append(str(attrs.get("ADMIN")))

    # The most specific place, as long as it sits in a country the text
    # names -- or the text names no country at all.
    for _length, name, parent in sorted(states, reverse=True):
        if not countries or _norm(parent) in {_norm(c) for c in countries}:
            return {"state": name, "country": parent}
    if countries:
        region = {"country": countries[0]}
        if countries[0] == "India":
            region["view"] = "ind"
        return region
    return None


def main() -> int:
    text = " ".join(sys.argv[1:]) or sys.stdin.read()
    try:
        print(json.dumps({"region": resolve(text)}))
    except Exception as error:  # noqa: BLE001 -- no map is an answer, not a crash
        print(json.dumps({"region": None, "error": f"{type(error).__name__}: {error}"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
