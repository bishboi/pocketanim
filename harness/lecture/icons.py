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
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICONS = HERE / "data" / "icons"
CACHE = HERE / ".cache" / "icons"

# Search order: colour sets first, so illustrations and map icons come in colour. PANIM_ICON_FAMILY puts
# one set ahead of the rest (e.g. fluent-emoji for Microsoft's shaded 3-D style, an optional 100 MB download).
COLOUR = ["fluent-emoji-flat", "twemoji", "streamline-emojis", "noto", "emojione", "openmoji", "fxemoji",
          "meteocons", "fluent-emoji"]
# Single-colour silhouettes: used only when no colour icon fits, filled with a colour from the style's palette.
MONO = ["game-icons", "mdi", "healthicons"]
# Whiteboard drawings (sketch()): dark outlines and flat colour fills, drawn in on the board.
SKETCH = ["openmoji", "streamline-plump-color"]
SKETCH_ONLY = ["streamline-plump-color"]
# The sets drawings come from, best first: flat colour drawings that, drawn with ink outlines (pocket_lecture.
# sketch_mob), read as one whiteboard style. About 15,000 drawings between them.
DRAWINGS = ["fluent-emoji-flat", "openmoji", "twemoji", "noto", "streamline-emojis", "streamline-plump-color"]
_SKIN = re.compile(r"-(light|medium-light|medium|medium-dark|dark)(-skin-tone)?$")


def drawings(query: str, limit: int = 12) -> list[dict]:
    """Drawings for a query, best first, across DRAWINGS: [{"id", "name", "set"}], one per thing (the same emoji's
    name in several sets is one thing, its best set's drawing), for a model to choose from. Every word of the query
    in the name first ("evergreen tree", "palm tree" for "tree"), then names with any one of its words."""
    words = [w for w in _norm(query).split("-") if len(w) > 1]
    if not words:
        return []
    forms = [{w, *_variants(w)} for w in words]
    names = _names()
    first = sketch(query)
    scored = []
    for rank, prefix in enumerate(DRAWINGS):
        for name in names.get(prefix, []):
            if prefix == "streamline-plump-color" and name.endswith("-flat"):
                continue
            if SYMBOLIC.search(name) or UNFIT.search(name) or _SKIN.search(name):
                continue
            parts = set(name.split("-"))
            hits = sum(bool(f & parts) for f in forms)
            if not hits:
                continue
            whole = hits == len(forms)
            score = (100 if whole else 40 * hits / len(forms)) - len(parts) * 2 - rank
            if f"{prefix}:{name}" == first:
                score += 1000
            scored.append((score, prefix, name))
    scored.sort(key=lambda row: -row[0])
    rows, seen = [], set()
    for _score, prefix, name in scored:
        if name in seen:
            continue
        seen.add(name)
        rows.append({"id": f"{prefix}:{name}", "name": name.replace("-", " "), "set": prefix})
        if len(rows) >= limit:
            break
    return rows


# Not for a classroom diagram, whatever the word ("atom" is not an atom bomb).
UNFIT = re.compile(r"(^|-)(bomb|gun|pistol|knife|dagger|skull|coffin|cigarette|syringe)(-|$)")
_first = os.environ.get("PANIM_ICON_FAMILY", "").strip()
SETS = ([_first] if _first else []) + [s for s in COLOUR + MONO + SKETCH if s != _first]
CREDITS = {
    "game-icons": "game-icons.net (CC BY 3.0)", "fluent-emoji-flat": "Microsoft Fluent Emoji (MIT)",
    "fluent-emoji": "Microsoft Fluent Emoji (MIT)", "twemoji": "Twemoji by X/Twitter (CC BY 4.0)",
    "streamline-emojis": "Streamline Emojis (CC BY 4.0)", "emojione": "EmojiOne (CC BY 4.0)",
    "fxemoji": "Firefox OS Emoji (Apache 2.0)", "meteocons": "Meteocons by Bas Milius (MIT)",
    "openmoji": "OpenMoji (CC BY-SA 4.0)", "noto": "Google Noto Emoji (Apache 2.0)",
    "mdi": "Material Design Icons (Apache 2.0)", "healthicons": "Health Icons (MIT)",
    "streamline-plump-color": "Streamline Plump (CC BY 4.0)",
}
# What fetch_icons.py downloads by default; a library missing any of these is fetched again.
REQUIRED = ["fluent-emoji-flat", "twemoji", "streamline-emojis", "noto", "emojione", "openmoji", "fxemoji",
            "meteocons", "game-icons", "mdi", "healthicons", "streamline-plump-color"]
# Words a lecture uses that the icon names spell differently.
SYNONYMS = {
    "sugarcane": "sugar-cane", "atom": "atom-symbol", "atoms": "atom-symbol", "maize": "corn", "paddy": "sheaf-of-rice", "rice": "sheaf-of-rice",
    "cattle": "cow", "livestock": "cow", "dairy": "cow", "industry": "factory", "industries": "factory",
    "petroleum": "oil-drum", "crude oil": "oil-drum", "mining": "mine-truck", "minerals": "gold-mine",
    "iron ore": "ore", "hydroelectric": "dam", "hydropower": "dam", "rainfall": "rain", "monsoon": "rain",
    "desert": "cactus", "forests": "forest", "wildlife": "tiger", "fishing": "fish", "fisheries": "fish",
    "tourism": "camera", "port": "anchor", "railway": "train", "pilgrimage": "hindu-temple",
    "textiles": "sewing-machine", "textile": "sewing-machine", "jute": "sheaf-of-rice", "pulses": "beans",
    "oilseeds": "sunflower", "mustard": "flower", "sugar": "sugar-cane", "wheat": "wheat",
    "tree": "deciduous-tree", "trees": "deciduous-tree", "forest": "deciduous-tree", "woods": "deciduous-tree",
    "water": "droplet", "villagers": "family", "villager": "person", "village": "hut", "rain": "cloud-with-rain",
    "storm": "cloud-with-lightning-and-rain", "sun": "sun", "sunlight": "sun", "plant": "potted-plant",
    "plants": "seedling", "seed": "seedling", "seeds": "seedling", "bird": "bird", "birds": "bird",
    "temple": "hindu-temple", "temples": "hindu-temple", "fort": "castle", "forts": "castle",
    "leaves": "leaf-fluttering-in-wind", "leaf": "leaf-fluttering-in-wind",
    "insects": "bug", "insect": "bug", "bacteria": "microbe", "microbes": "microbe", "germs": "microbe",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


@lru_cache(None)
def _set(name: str) -> dict:
    path = ICONS / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def available() -> list[str]:
    return [s for s in SETS if (ICONS / f"{s}.json").exists()]


def missing() -> list[str]:
    """The default sets not downloaded yet (an older library lacks the newer colour sets)."""
    return [s for s in REQUIRED if not (ICONS / f"{s}.json").exists()]


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


def _variants(word: str) -> list[str]:
    """Simpler forms of a word to try when it finds nothing: villagers -> villager -> village, berries -> berry."""
    w = str(word).lower().strip()
    out = []
    for suffix, repl in (("ies", "y"), ("es", ""), ("s", ""), ("ers", ""), ("er", ""), ("ing", "")):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            out.append(w[: -len(suffix)] + repl)
    return [v for i, v in enumerate(out) if v != w and v not in out[:i]]


def search(query: str, limit: int = 8) -> list[dict]:
    """Icons for a word or phrase, best first; a plural or -er word falls back to its simpler form."""
    found = _search(query, limit)
    if not found and ":" not in str(query) and " " not in str(query).strip():
        for variant in _variants(query):
            found = _search(variant, limit)
            if found:
                break
    return found


def _search(query: str, limit: int = 8) -> list[dict]:
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
        if prefix in SKETCH_ONLY and prefix not in str(query):
            continue                   # whiteboard drawings for diagrams only (sketch()), not map or panel icons
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
            if prefix in MONO:
                score -= 30    # a silhouette only when no colour icon fits well
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


# Sets whose names are things (a tiger, a factory). mdi and healthicons are
# interface symbols ("crop" is the crop tool), so an automatic pick skips them.
PICTORIAL = [s for s in SETS if s not in ("mdi", "healthicons")]
# Sets an automatic pick may use: Unicode emoji (concrete things) and game-icons. OpenMoji and Firefox emoji
# add logos and UI glyphs ("edge" is a browser, "down" a pointing hand), so only an explicit search finds those.
AUTO = [s for s in PICTORIAL if s not in ("openmoji", "fxemoji", "meteocons")]
# Names that are symbols, gestures or signs rather than things to picture.
SYMBOLIC = re.compile(r"(^|-)(arrow|arrows|button|sign|symbol|keycap|flag|letter|finger|pointing|hand|hands|"
                      r"backhand|index|up|down|left|right|logo|squared|circled|mark)(-|$)")


@lru_cache(None)
def _exact_index() -> dict[str, str]:
    index: dict[str, str] = {}
    names = _names()
    for prefix in AUTO:
        for name in names.get(prefix, []):
            if not SYMBOLIC.search(name):
                index.setdefault(name, f"{prefix}:{name}")
    return index


# Words too general to picture on their own.
VAGUE = set("""
state area part region people time year years way place world side line point form type kind number level one two
three four five first last main large small high low long north south east west chapter about and the with for from
into onto over under many much more most some any all each every this that these those there here their they them
its his her our your who what when where which while also only very just even still such than then thus heart belt
center centre face hand head key home light power star back front top bottom end start case use set run turn fall
spring rest ground field base range cover mark sign show order note cross close open wide deep rich poor great good
bad new old young big little best better same other another since until after before during between across along
around among against without within above below near far even rather quite almost always never often sometimes
edge down up out off break keep make made give take get got put let tiny huge whole half full empty
""".split())


def exact(word: str) -> str | None:
    """The icon whose name is this word (or its synonym, or its singular), fast; None otherwise."""
    w = str(word).lower().strip()
    if len(w) < 3 or w in VAGUE:
        return None
    index = _exact_index()
    for candidate in (SYNONYMS.get(w, w), w[:-3] + "y" if w.endswith("ies") else None,
                      w[:-1] if w.endswith("s") else None, w[:-2] if w.endswith("es") else None):
        if candidate and _norm(candidate) in index:
            return index[_norm(candidate)]
    return None


def picture_words(text: str, limit: int = 5) -> list[str]:
    """Icons for the concrete nouns of a sentence, in order: what an auto-illustration draws."""
    out: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z-]{2,}", text or ""):
        found = exact(word)
        if found and found not in out:
            out.append(found)
        if len(out) >= limit:
            break
    return out


# Lecture headings and the picture that stands for each (all present in the downloaded sets).
TOPICS = {
    "climate": "sun-behind-cloud", "weather": "sun-behind-cloud", "population": "family", "people": "family",
    "resources": "gem-stone", "minerals": "gem-stone", "economy": "money-bag", "history": "scroll",
    "aftermath": "scroll", "culture": "performing-arts", "water": "water-drop", "rivers": "water-wave",
    "land": "mountains", "landforms": "mountains", "relief": "mountains", "soils": "seedling", "soil": "seedling",
    "agriculture": "farmer", "farming": "farmer", "farms": "farmer", "transport": "train", "trade": "cargo-ship",
    "cities": "cityscape", "health": "hospital", "education": "books", "energy": "high-voltage",
    "war": "crossed-swords", "battle": "crossed-swords", "forces": "crossed-swords", "science": "atom-symbol",
    "biology": "dna", "location": "world-map", "extent": "world-map", "introduction": "open-book",
    "recap": "memo", "intrigue": "spy", "march": "footprints", "wildlife": "tiger", "vegetation": "deciduous-tree",
    "forests": "deciduous-tree", "forest": "deciduous-tree", "industry": "factory", "industries": "factory",
}


def topic(title: str) -> list[str]:
    """Icons for a heading ("Climate", "Resources & People"): the topic table, then the best pictorial match."""
    out = []
    index = _exact_index()
    for word in re.findall(r"[A-Za-z]{3,}", title or ""):
        named = TOPICS.get(word.lower())
        if named and named in index:
            if index[named] not in out:
                out.append(index[named])
            continue
        if word.lower() in VAGUE:
            continue
        hit = next((r["id"] for r in search(word, 12) if r["set"] in AUTO and not SYMBOLIC.search(r["name"])), None)
        if hit and hit not in out:
            out.append(hit)
    return out[:3]


def resolve(name: str) -> str | None:
    """The icon id a script's name means, or None."""
    found = search(name, limit=1)
    return found[0]["id"] if found else None


def sketch(name: str) -> str | None:
    """The whiteboard drawing for a name: outlined, flat-coloured, the style a diagram draws in (an outline first,
    then its colours). The same thing the plain search finds, in OpenMoji's outlined drawing when OpenMoji has it
    (Unicode emoji share their names across sets), else Streamline Plump's, else the plain pick, which is drawn with
    outlines too. An explicit "set:name" is kept."""
    if ":" in str(name):
        return resolve(name)
    plain = resolve(name)
    names = _names()
    if plain and plain.split(":", 1)[0] in DRAWINGS and not UNFIT.search(plain):
        return plain                   # a flat colour drawing: drawn with outlines, it is a whiteboard drawing
    if plain:
        base = plain.split(":", 1)[1]
        if base in names.get("openmoji", []) and not SYMBOLIC.search(base):
            return f"openmoji:{base}"
    # OpenMoji's own best match, when the plain pick is a silhouette or names nothing OpenMoji has ("car" is
    # mdi:car, an interface glyph; OpenMoji draws an automobile).
    if not plain or plain.split(":", 1)[0] in MONO:
        words = {_norm(SYNONYMS.get(str(name).lower().strip(), name)), *(_norm(v) for v in _variants(str(name)))}
        hit = next((r["id"] for r in search(name, 30) if r["set"] == "openmoji" and not SYMBOLIC.search(r["name"])
                    and not UNFIT.search(r["name"]) and words & set(r["name"].split("-"))), None)
        if hit:
            return hit
    q = _norm(SYNONYMS.get(str(name).lower().strip(), name))
    plump = [n for n in names.get("streamline-plump-color", []) if not n.endswith("-flat")]
    for candidate in (q, *(_norm(v) for v in _variants(q))):
        hits = sorted((n for n in plump if n == candidate or candidate in n.split("-")[:1]), key=len)
        if hits:
            return f"streamline-plump-color:{hits[0]}"
    return plain


_GRADIENT = re.compile(r"<(linearGradient|radialGradient)\b([^>]*?)(/>|>(.*?)</\1>)", re.S)
_STOP = re.compile(r"<stop\b[^>]*>", re.S)


def _hex(colour: str) -> tuple[int, int, int] | None:
    c = colour.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{3}", c):
        c = "".join(ch * 2 for ch in c)
    if re.fullmatch(r"[0-9a-fA-F]{6}", c):
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+).*\)", colour.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def flatten_gradients(body: str) -> str:
    """Gradient fills as one solid colour each (their stops' mean), so Manim draws them.

    Manim's SVG loader has no gradients: a gradient-filled shape comes out
    black or empty. Shaded sets (Noto, Fluent Emoji) keep their colours this way.
    """
    if "Gradient" not in body:
        return body
    stops: dict[str, list[tuple[int, int, int]]] = {}
    links: dict[str, str] = {}
    for m in _GRADIENT.finditer(body):
        attrs, inner = m[2], m[4] or ""
        gid = re.search(r'\bid="([^"]+)"', attrs)
        if not gid:
            continue
        href = re.search(r'href="#([^"]+)"', attrs)
        if href:
            links[gid[1]] = href[1]
        colours = []
        for stop in _STOP.findall(inner):
            c = re.search(r'stop-color[=:]\s*"?([^";]+)', stop)
            rgb = _hex(c[1]) if c else None
            if rgb:
                colours.append(rgb)
        stops[gid[1]] = colours

    def mean(gid: str, depth: int = 0) -> str | None:
        colours = stops.get(gid) or []
        if not colours and gid in links and depth < 5:
            return mean(links[gid], depth + 1)
        if not colours:
            return None
        r, g, b = (round(sum(c[i] for c in colours) / len(colours)) for i in range(3))
        return f"#{r:02x}{g:02x}{b:02x}"

    def swap(m):
        solid = mean(m[1])
        return solid or "none"

    body = _GRADIENT.sub("", body)
    return re.sub(r"url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)", swap, body)


def svg_file(icon_id: str, color: str | None = None) -> Path:
    """The icon as an SVG file, a single-colour one filled with `color`. Cached by content."""
    prefix, name = icon_id.split(":", 1)
    found = _body(prefix, name)
    if not found:
        raise KeyError(f"no icon {icon_id!r}")
    body, width, height = found
    body = flatten_gradients(body)
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
    if sys.argv[1:2] == ["--drawings"]:
        # icons.py --drawings cow "solar panel"      drawings a model may choose from, as JSON
        print(json.dumps({q: drawings(q) for q in sys.argv[2:]}, ensure_ascii=False))
        raise SystemExit(0)
    if not available():
        print(json.dumps({"error": "no icon sets; run harness/scripts/fetch_icons.py"}))
        raise SystemExit(1)
    print(json.dumps({q: search(q) for q in sys.argv[1:]}, indent=1))
