"""Icons for lectures: search the downloaded Iconify sets, and write an icon as an SVG file.

The sets live in data/icons/<set>.json (harness/scripts/fetch_icons.py). An
icon is named "set:name" ("game-icons:sugar-cane"), or by a plain word that
search() resolves ("sugarcane"). Single-colour icons are drawn in
`currentColor`, so a lecture fills them with its style's colour; colour
emoji keep their own colours.

    python harness/lecture/icons.py sugarcane wheat coal     # search from the shell, as JSON
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICONS = HERE / "data" / "icons"
CACHE = HERE / ".cache" / "icons"

# Search order: silhouettes first (they take the style's colour), then colour emoji.
SETS = ["game-icons", "fluent-emoji-flat", "openmoji", "noto", "mdi", "healthicons"]
CREDITS = {
    "game-icons": "game-icons.net (CC BY 3.0)", "fluent-emoji-flat": "Microsoft Fluent Emoji (MIT)",
    "openmoji": "OpenMoji (CC BY-SA 4.0)", "noto": "Google Noto Emoji (Apache 2.0)",
    "mdi": "Material Design Icons (Apache 2.0)", "healthicons": "Health Icons (MIT)",
}
# Words a lecture uses that the icon names spell differently.
SYNONYMS = {
    "sugarcane": "sugar-cane", "maize": "corn", "paddy": "sheaf-of-rice", "rice": "sheaf-of-rice",
    "cattle": "cow", "livestock": "cow", "dairy": "cow", "industry": "factory", "industries": "factory",
    "petroleum": "oil-drum", "crude oil": "oil-drum", "mining": "mine-truck", "minerals": "gold-mine",
    "iron ore": "ore", "hydroelectric": "dam", "hydropower": "dam", "rainfall": "rain", "monsoon": "rain",
    "desert": "cactus", "forests": "forest", "wildlife": "tiger", "fishing": "fish", "fisheries": "fish",
    "tourism": "camera", "port": "anchor", "railway": "train", "pilgrimage": "hindu-temple",
    "textiles": "sewing-machine", "textile": "sewing-machine", "jute": "sheaf-of-rice", "pulses": "beans",
    "oilseeds": "sunflower", "mustard": "flower", "sugar": "sugar-cane", "wheat": "wheat",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


@lru_cache(None)
def _set(name: str) -> dict:
    path = ICONS / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def available() -> list[str]:
    return [s for s in SETS if (ICONS / f"{s}.json").exists()]


@lru_cache(None)
def _names() -> dict[str, list[str]]:
    """Every icon name and alias, per set, in search order."""
    out = {}
    for prefix in available():
        data = _set(prefix)
        out[prefix] = list(data.get("icons", {})) + list(data.get("aliases", {}))
    return out


def _body(prefix: str, name: str) -> tuple[str, float, float] | None:
    data = _set(prefix)
    icons, aliases = data.get("icons", {}), data.get("aliases", {})
    seen = 0
    while name in aliases and name not in icons and seen < 5:
        name = aliases[name]["parent"]
        seen += 1
    icon = icons.get(name)
    if not icon:
        return None
    return icon["body"], float(icon.get("width", data.get("width", 16))), float(icon.get("height", data.get("height", 16)))


def is_mono(icon_id: str) -> bool:
    """A single-colour icon: every fill and stroke is currentColor (or none)."""
    prefix, name = icon_id.split(":", 1)
    found = _body(prefix, name)
    if not found:
        return False
    colours = set(re.findall(r'(?:fill|stroke)="([^"]+)"', found[0])) - {"none", "currentColor"}
    return not colours


def search(query: str, limit: int = 8) -> list[dict]:
    """Icons for a word or phrase, best first: exact name, then every word, then any word."""
    q = _norm(SYNONYMS.get(str(query).lower().strip(), query))
    if not q:
        return []
    if ":" in str(query):
        prefix, name = str(query).split(":", 1)
        return [_row(prefix, name)] if _body(prefix, name) else []
    words = [w for w in q.split("-") if len(w) > 1]
    scored = []
    for rank, (prefix, names) in enumerate(_names().items()):
        for name in names:
            parts = name.split("-")
            if name == q:
                score = 100
            elif q in parts or name.startswith(q + "-") or name.endswith("-" + q):
                score = 60 - len(parts)
            elif words and all(w in parts for w in words):
                score = 50 - len(parts)
            elif words and len(q) > 3 and q in name:
                score = 30 - len(parts)
            else:
                continue
            if name.endswith(("-dark", "-light", "-medium", "-medium-dark", "-medium-light")):
                score -= 20
            scored.append((score - rank * 0.5, prefix, name))
    scored.sort(key=lambda row: -row[0])
    out, seen = [], set()
    for _score, prefix, name in scored:
        if (prefix, name) not in seen:
            seen.add((prefix, name))
            out.append(_row(prefix, name))
        if len(out) >= limit:
            break
    return out


def _row(prefix: str, name: str) -> dict:
    icon_id = f"{prefix}:{name}"
    return {"id": icon_id, "set": prefix, "name": name, "mono": is_mono(icon_id)}


def resolve(name: str) -> str | None:
    """The icon id a script's name means, or None."""
    found = search(name, limit=1)
    return found[0]["id"] if found else None


def svg_file(icon_id: str, color: str | None = None) -> Path:
    """The icon as an SVG file, a single-colour one filled with `color`. Cached by content."""
    prefix, name = icon_id.split(":", 1)
    found = _body(prefix, name)
    if not found:
        raise KeyError(f"no icon {icon_id!r}")
    body, width, height = found
    if color:
        body = body.replace("currentColor", color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
           f'width="{width:g}" height="{height:g}">{body}</svg>')
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{_norm(icon_id)}-{hashlib.md5(svg.encode()).hexdigest()[:8]}.svg"
    if not path.exists():
        path.write_text(svg, encoding="utf-8")
    return path


def credit(icon_ids) -> str:
    sets = sorted({i.split(":", 1)[0] for i in icon_ids})
    return "Icons: " + ", ".join(CREDITS.get(s, s) for s in sets) if sets else ""


if __name__ == "__main__":
    if not available():
        print(json.dumps({"error": "no icon sets; run harness/scripts/fetch_icons.py"}))
        raise SystemExit(1)
    print(json.dumps({q: search(q) for q in sys.argv[1:]}, indent=1))
