"""Pictures a score asks for, made by an image model (OpenRouter's Image API) and kept, so the engine draws real
objects, not only line icons.

    pic "PROMPT"     an object, cut out of its background, with a soft shadow under it (a banknote, a temple, a
                     farmer, a stack of coins)
    photo "PROMPT"   a picture in a white border with a shadow, as a print laid on the paper (a scene, a place)
    flag CODE        a country's flag (ISO 3166 code: jp, us, in...), from the flag-icons set: exact, never made

    photo commons "WORDS"   a real picture from Wikimedia Commons (a painting, a manuscript page, a photograph of a
                     place or an object): searched, the best of the candidates chosen by the vision model, kept with
                     its licence and author beside it (NAME.credit.json) and credited on screen when its licence asks
                     (also `pic commons "..."`, `card ... img "commons:..."`, `portrait ... img "commons:..."`)

A picture is made once for its look's style, its kind and its words, and kept in harness_v3/.cache/assets/ by a hash
of those (the image model too): a score rendered again, or another video asking the same, costs nothing. Text never
goes into a made picture (models garble letters); the engine sets every word.

The model is V3_IMAGE_MODEL (any OpenRouter model with image output); the key is OPENROUTER_API_KEY. A picture that
cannot be made is drawn as a placeholder card naming it, and said in the notes.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shlex
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "assets"
FLAGS = ROOT / ".cache" / "flagpkg" / "package" / "flags" / "4x3"
DEFAULT_MODEL = os.environ.get("V3_IMAGE_MODEL", "google/gemini-2.5-flash-image")
# Three kinds of picture, a model each (blank: V3_IMAGE_MODEL): pictures (photos, backdrops, portraits); small things
# (cut-out objects and icons, made six to a sheet: a smaller, cheaper model does); pictures whose parts are labelled
# (they must show each named part clearly: a stronger model).
SMALL_MODEL = os.environ.get("V3_IMAGE_MODEL_SMALL", "").strip()
LABELED_MODEL = os.environ.get("V3_IMAGE_MODEL_LABELED", "").strip()
# Pictures from Wikimedia Commons (`photo commons "..."`): off unless V3_IMAGE_SEARCH=1; when off, such a picture is
# made by the image model from the same words.
SEARCH = os.environ.get("V3_IMAGE_SEARCH", "0").strip() == "1"
KINDS = ("pic", "photo")

# The house style each look asks the image model for (appended to every prompt).
STYLE = {
    "editorial": "editorial illustration in a realistic print style, muted warm colours, soft even studio light, "
                 "slight paper grain",
    "paper": "flat editorial illustration, warm muted colours, soft light",
}
# Small things (`pic`, and what were icons) are drawn by hand, not photographed: a realistic object or person cut out
# looks pasted on, a drawing sits on the paper. V3_SMALL_STYLE says otherwise.
SMALL_STYLE = os.environ.get("V3_SMALL_STYLE", "").strip() or (
    "a simple hand-drawn illustration, like a doodle in a sketchbook: clean dark ink outlines, a few flat muted colour "
    "washes, no shading gradients, no realism, no photographic detail; people drawn as simple friendly stick-like "
    "figures with round heads")
SMALL_KEY = "sketch1"          # in the small pictures' key: a change of style makes them anew


def style_for(kind: str, look: str) -> str:
    return SMALL_STYLE if kind == "pic" else STYLE.get(look, STYLE["paper"])


HOW = {
    "pic": "One single object, centred, whole and uncropped, seen straight on, isolated on a plain flat light grey "
           "background (#DDDDDD) with nothing else in the picture: no shadow, no floor, no frame, no text, no "
           "letters, no numbers, no logos.",
    "photo": "A single clear photograph-like picture filling the frame, no border, no text, no letters, no logos, "
             "no watermark.",
}


def key(kind: str, prompt: str, look: str, model: str) -> str:
    return hashlib.sha1(f"{model}|{look}|{kind}|{prompt.strip().lower()}".encode()).hexdigest()[:16]


def path_for(kind: str, prompt: str, look: str, model: str | None = None) -> Path:
    """Where a picture is kept: by its kind, words and look (the model that made it is kept beside it, NAME.model.txt,
    so the render finds it whichever of the image models made it). `model` is not used (kept for old callers)."""
    if is_archive(prompt):                  # a picture from the archive is the same whatever the look or model
        return CACHE / f"commons-{key(kind, archive_query(prompt), 'commons', 'commons')}.png"
    return CACHE / f"{kind}-{key(kind, prompt, look + ('|' + SMALL_KEY if kind == 'pic' else ''), '')}.png"


def old_path(kind: str, prompt: str, look: str, model: str) -> Path:
    """Where a picture was kept before the model left the key (each model's own file)."""
    return CACHE / f"{kind}-{key(kind, prompt, look, model)}.png"


def adopt(kind: str, prompt: str, look: str, models) -> bool:
    """A picture kept under an old key (made by one of `models`) moved to its key now, with what is beside it."""
    new = path_for(kind, prompt, look)
    if new.exists() or is_archive(prompt) or kind == "pic":     # (old small pictures were realistic: made anew)
        return new.exists()
    for m in dict.fromkeys(x for x in models if x):
        old = old_path(kind, prompt, look, m)
        if old.exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            old.replace(new)
            for ext in (".spots.json", ".prompt.txt"):
                if old.with_suffix(ext).exists():
                    old.with_suffix(ext).replace(new.with_suffix(ext))
            keep_model(new, m)
            return True
    return False


def keep_model(p: Path, model: str) -> None:
    p.with_suffix(".model.txt").write_text(model)


def made_with(p: Path) -> str | None:
    f = p.with_suffix(".model.txt")
    return f.read_text().strip() if f.exists() else None


def is_archive(prompt: str) -> bool:
    return str(prompt).strip().lower().startswith("commons:")


def archive_query(prompt: str) -> str:
    return str(prompt).split(":", 1)[1].strip()


def spots(path: Path) -> dict:
    """Where a picture's named parts are (`labels` on it): {part: (x, y)}, 0..1 from its top left, as a vision
    model found them (kept beside the picture: NAME.spots.json)."""
    f = path.with_suffix(".spots.json")
    try:
        return {k: tuple(v) for k, v in json.loads(f.read_text()).items() if v} if f.exists() else {}
    except (ValueError, TypeError):
        return {}


def labelled(score_text: str) -> list[tuple[str, str, str, list[str]]]:
    """The pictures whose parts a score names (`ent X labels "spire" "portal" on PIC`): (kind, prompt, look, the
    parts not placed by hand), each picture once."""
    look, pics, out = "paper", {}, {}
    for raw in score_text.splitlines():
        try:
            toks = shlex.split(raw, comments=True)
        except ValueError:
            continue
        if len(toks) >= 2 and toks[0] == "look":
            look = toks[1]
        if len(toks) >= 4 and toks[0] == "ent" and toks[2] in KINDS + ("backdrop",):
            words = f"commons:{toks[4]}" if toks[3] == "commons" and len(toks) > 4 else toks[3]
            pics[toks[1]] = ("photo" if toks[2] == "backdrop" else toks[2], words, look)
        if len(toks) >= 4 and toks[0] == "ent" and toks[2] == "labels" and "on" in toks:
            i = toks.index("on")
            pic = toks[i + 1] if i + 1 < len(toks) else ""
            if pic in pics:
                names = [t for t in toks[3:i] if "@" not in t]
                out.setdefault(pics[pic], [])
                out[pics[pic]] += [n for n in names if n not in out[pics[pic]]]
    return [(k, p, lk, names) for (k, p, lk), names in out.items() if names]


def labelled_pictures(score_text: str) -> set[tuple[str, str]]:
    """Every picture a `labels` entity is put on: (kind, the score's words), as `wants` gives them."""
    pics, out = {}, set()
    for raw in score_text.splitlines():
        try:
            toks = shlex.split(raw, comments=True)
        except ValueError:
            continue
        if len(toks) >= 4 and toks[0] == "ent" and toks[2] in KINDS + ("backdrop",):
            words = f"commons:{toks[4]}" if toks[3] == "commons" and len(toks) > 4 else toks[3]
            pics[toks[1]] = ("photo" if toks[2] == "backdrop" else toks[2], words)
        if len(toks) >= 4 and toks[0] == "ent" and toks[2] == "labels" and "on" in toks:
            i = toks.index("on")
            if i + 1 < len(toks) and toks[i + 1] in pics:
                out.add(pics[toks[i + 1]])
    return out


def find_prompt(names: list[str]) -> tuple[str, str]:
    system = ("You find things in a picture. For each part named, give where its middle is in the picture, as x and "
              "y from 0 to 1 (x from the left edge, y from the top edge). Answer only lines `PART | X | Y`, or "
              "`PART | none` when it is not in the picture.")
    return system, "PARTS:\n" + "\n".join(n.replace("_", " ") for n in names)


def read_spots(text: str, names: list[str]) -> dict:
    """The answer's lines -> {part key: [x, y]} (none: null), for the parts asked about."""
    import kit
    want = {kit.key(n): n for n in names}
    out = {}
    for line in text.splitlines():
        bits = [b.strip(" `*-") for b in line.split("|")]
        if len(bits) < 2 or kit.key(bits[0]) not in want:
            continue
        try:
            x, y = float(bits[1]), float(bits[2])
            if x > 1.5 or y > 1.5:              # given in 0..100 or 0..1000
                k = 100.0 if max(x, y) <= 100 else 1000.0
                x, y = x / k, y / k
            out[kit.key(bits[0])] = [min(1.0, max(0.0, x)), min(1.0, max(0.0, y))]
        except (ValueError, IndexError):
            out[kit.key(bits[0])] = None
    return out


def keep_spots(path: Path, found: dict) -> None:
    f = path.with_suffix(".spots.json")
    try:
        have = json.loads(f.read_text()) if f.exists() else {}
    except ValueError:
        have = {}
    have.update(found)
    f.write_text(json.dumps(have))


def data_url(path: Path, side: int = 768) -> str:
    """A picture as a JPEG data URL, at most `side` pixels on its longest side, on the paper colour."""
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    k = min(1.0, side / max(img.size))
    img = img.resize((round(img.width * k), round(img.height * k)))
    bg = Image.new("RGB", img.size, (239, 228, 200))
    bg.paste(img, mask=img.split()[3])
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def wants(score_text: str) -> list[tuple[str, str, str]]:
    """The pictures a score asks for: (kind, prompt, look), each once."""
    look, out = "paper", []
    for raw in score_text.splitlines():
        try:
            toks = shlex.split(raw, comments=True)
        except ValueError:
            continue
        if len(toks) >= 2 and toks[0] == "look":
            look = toks[1]
        if len(toks) < 4 or toks[0] not in ("ent", "cast"):     # (a cast line makes a character once)
            continue
        found = []
        if toks[2] == "backdrop":                  # a photo behind a whole shot
            found.append(("photo", f"commons:{toks[4]}" if toks[3] == "commons" and len(toks) > 4 else toks[3]))
        if toks[2] in KINDS:
            # `photo commons "WORDS"`: from the archive
            found.append((toks[2], f"commons:{toks[4]}" if toks[3] == "commons" and len(toks) > 4 else toks[3]))
        for i, t in enumerate(toks[:-1]):
            if t == "img" and i >= 3:            # a card's or a portrait's picture
                found.append(("pic" if toks[2] in ("card", "isotype") else "photo", toks[i + 1]))
        if toks[2] in ("portrait", "who") and "img" not in toks:   # a person with no picture named: one made of them
            found.append(("photo", toks[3] if toks[2] == "portrait" else f"a portrait of {toks[3]}"))
        if toks[2] == "icon" and os.environ.get("V3_ICONS", "0").strip() != "1":
            import look as kit_look                # what was an icon is a small hand-drawn picture
            found.append(("pic", kit_look.icon_words(toks[3])))
        if toks[2] == "polaroids":                 # prints: each its own photo
            stop = next((i for i, t in enumerate(toks) if i > 2 and t in ("at", "size", "layer", "rot", "x")), len(toks))
            found += [("photo", t) for t in toks[3:stop]]
        for kind, prompt in found:
            if (kind, prompt, look) not in out:
                out.append((kind, prompt, look))
    return out


# ---------------------------------------------------------------- the archive (Wikimedia Commons) -------------------

COMMONS = "https://commons.wikimedia.org/w/api.php"
UA = "pocketanim-harness/3.0 (https://github.com/bishboi/pocketanim; explainer videos)"


def _get(url: str, params: dict | None = None, tries: int = 4) -> bytes:
    """A GET to Wikimedia with its User-Agent, waiting as it asks when it is busy (429, 503)."""
    import time
    import urllib.parse
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    for n in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and n < tries - 1:
                time.sleep(min(60, int(e.headers.get("retry-after") or 5 * (n + 1))))
                continue
            raise RuntimeError(f"Wikimedia Commons said {e.code}") from e
    raise RuntimeError("Wikimedia Commons is busy: try again in a minute")


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def commons_candidates(query: str, n: int = 8) -> list[dict]:
    """Pictures on Commons for the words, in its order of relevance: freely licensed bitmaps big enough to show."""
    d = json.loads(_get(COMMONS, {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                                  "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": n * 2, "prop": "imageinfo",
                                  "iiprop": "url|size|mime|extmetadata"}))
    out = []
    for p in sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = _plain((meta.get("LicenseShortName") or {}).get("value", ""))
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/tiff", "image/webp") or "fair" in lic.lower():
            continue
        if min(ii.get("width", 0), ii.get("height", 0)) < 400 or not ii.get("url"):
            continue
        out.append({"title": p.get("title", ""), "url": thumb(ii["url"], ii.get("width", 0), 1280),
                    "original": ii["url"], "width": ii.get("width", 0), "page": ii.get("descriptionurl", ""),
                    "license": lic or "see the file's page", "artist": _plain((meta.get("Artist") or {}).get("value", ""))[:120],
                    "needs_credit": not re.search(r"public domain|^pd|cc0", lic, re.I)})
        if len(out) >= n:
            break
    return out


# The thumbnail widths Wikimedia serves to anyone (others, and the original files, are rate-limited for programs).
WIDTHS = (330, 500, 960, 1280, 1920)


def thumb(original: str, width: int, want: int) -> str:
    """A Commons file's thumbnail URL at the largest standard width up to `want` that the file has."""
    url = original.split("?", 1)[0]
    w = max([x for x in WIDTHS if x <= min(want, width)] or [WIDTHS[0]])
    m = re.match(r"^(https://upload\.wikimedia\.org/wikipedia/commons)/(.+?)/([^/]+)$", url)
    if not m or "/thumb/" in url:
        return re.sub(r"/\d+px-", f"/{w}px-", url)
    name = m.group(3)
    return f"{m.group(1)}/thumb/{m.group(2)}/{name}/{w}px-{name}" + (".png" if name.lower().endswith((".tif", ".tiff")) else "")


def small(url: str, width: int = 330) -> str:
    """A Commons thumbnail's URL at a small standard width (to show a model the candidates)."""
    return re.sub(r"/\d+px-", f"/{max([x for x in WIDTHS if x <= width] or [WIDTHS[0]])}px-", url)


def from_commons(kind: str, prompt: str, chosen: dict) -> Path:
    """The chosen archive picture, kept as a print (a `photo`) or, on a plain light ground, cut out (a `pic`), with
    its credit beside it."""
    img = _open(_get(chosen["url"]))
    path = path_for(kind, prompt, "", "")
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "pic" and _plain_ground(img):
        out = with_shadow(cutout(img))
    else:
        out = framed(img)
    out.save(path)
    path.with_suffix(".credit.json").write_text(json.dumps(chosen, indent=1))
    return path


def _plain_ground(img) -> bool:
    import numpy as np
    a = np.asarray(img.convert("RGB")).astype(int)
    corners = np.concatenate([a[:8, :8].reshape(-1, 3), a[:8, -8:].reshape(-1, 3), a[-8:, :8].reshape(-1, 3),
                              a[-8:, -8:].reshape(-1, 3)])
    return corners.min() > 200 and corners.std() < 12


def credit(path: Path) -> dict | None:
    f = path.with_suffix(".credit.json")
    try:
        return json.loads(f.read_text()) if f.exists() else None
    except ValueError:
        return None


def choose_prompt(query: str, n: int) -> tuple[str, str]:
    return ("You choose pictures for an educational video. You see numbered pictures found in an archive for a "
            "subject. Answer only the number of the one that shows the subject best and most clearly (a real "
            "depiction, not a map, diagram, document scan or logo unless the subject is one), or `none`."), \
        f"SUBJECT: {query}\nPICTURES: 1 to {n}, in order."


def prompt_for(kind: str, prompt: str, look: str) -> str:
    return f"{prompt.strip().rstrip('.')}. {style_for(kind, look)}. {HOW[kind]}"


# The optional settings each image model refused, learned from its answers ({model: {setting}}): sent no more to it.
# Some models take only the prompt and the shape (FLUX: "does not support: output_format, quality, background").
OPTIONAL = ("output_format", "quality", "background", "aspect_ratio", "n")
_refused: dict[str, set] = {}


def _refusal(said: str) -> set:
    """The settings a refusal names as not supported (`does not support: output_format, quality, background`)."""
    m = re.search(r"(?:does not|doesn't|do not) support[s]?\s*:?\s*(.+)", said, re.I)
    if not m:
        return set()
    names = set(re.findall(r"[a-z_]+", m.group(1).lower()))
    return {n for n in names if n in OPTIONAL}


def _image(model: str, prompt: str, aspect: str, transparent: bool = False):
    """One Image API call: the picture (PIL, RGBA) and the call's usage (cost, tokens). A setting the model says it does
    not support is left out and the call made again (and not sent to that model again)."""
    key_ = os.environ.get("OPENROUTER_API_KEY")
    if not key_:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    want = {"n": 1, "output_format": "png", "aspect_ratio": aspect, "quality": os.environ.get("V3_IMAGE_QUALITY", "medium")}
    if transparent:
        want["background"] = "transparent"     # where the model can; else we cut it out ourselves
    for _ in range(3):
        body = {"model": model, "prompt": prompt,
                **{k: v for k, v in want.items() if k not in _refused.get(model, set())}}
        req = urllib.request.Request("https://openrouter.ai/api/v1/images", data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {key_}", "Content-Type": "application/json",
                                              "User-Agent": "harness-v3/1.0",
                                              "HTTP-Referer": "https://github.com/bishboi/pocketanim", "X-Title": "harness v3"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            said = e.read()[:600].decode(errors="replace")
            try:
                said = json.loads(said).get("error", {}).get("message") or said
            except Exception:  # noqa: BLE001
                pass
            drop = _refusal(said) - _refused.get(model, set())
            if e.code == 400 and drop & set(body):
                _refused.setdefault(model, set()).update(drop)     # asked again without them
                continue
            raise RuntimeError(f"the image model refused ({e.code}): {said}") from e
    else:
        raise RuntimeError(f"the image model kept refusing its settings: {sorted(_refused.get(model, set()))}")
    if out.get("error"):
        raise RuntimeError(f"the image model: {out['error'].get('message') or out['error']}")
    data = (out.get("data") or [{}])[0]
    raw = data.get("b64_json")
    url = data.get("url") or ""
    if not raw and url.startswith("data:"):
        raw = url.split(",", 1)[1]
    if not raw and url.startswith("http"):         # some models answer with a link to the picture
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "harness-v3/1.0"}),
                                    timeout=120) as r:
            return _open(r.read()), out.get("usage") or {}
    if not raw:
        raise RuntimeError(f"the image model gave no picture: {str(out)[:300]}")
    return _open(base64.b64decode(raw)), out.get("usage") or {}


def generate(kind: str, prompt: str, look: str, model: str | None = None, said: str | None = None) -> tuple[Path, dict]:
    """Make the picture (one Image API call) and keep it, finished (cut out, shadowed, framed). `said`: the words the
    image model is given (a better prompt written for it); the picture is kept under the score's own words. Returns
    its path and the call's usage (cost, tokens)."""
    model = model or DEFAULT_MODEL
    img, usage = _image(model, prompt_for(kind, said or prompt, look), "1:1" if kind == "pic" else "4:3", kind == "pic")
    done = cutout(img) if kind == "pic" else framed(img)
    p = path_for(kind, prompt, look)
    CACHE.mkdir(parents=True, exist_ok=True)
    done.save(p)
    keep_said(p, said)
    keep_model(p, model)
    return p, usage


def keep_said(p: Path, said: str | None) -> None:
    if said:
        p.with_suffix(".prompt.txt").write_text(said)


# ---------------------------------------------------------------- a sheet of small things ----------------------------
# Small cut-out objects are asked for several at a time, laid out in a grid on one picture, and cut apart: one call
# instead of six, and the six in one hand. A cell where the grid was not kept (its object touching the cell's edge,
# or nothing in it) is made again on its own.

SHEET = max(1, int(os.environ.get("V3_IMAGE_SHEET", "6")))
# How many go on a sheet -> (columns, rows, aspect): the cells about square.
GRIDS = {2: (2, 1, "16:9"), 3: (2, 2, "1:1"), 4: (2, 2, "1:1"), 5: (3, 2, "3:2"), 6: (3, 2, "3:2")}
ORDINAL = ["first", "second", "third", "fourth", "fifth", "sixth"]


def sheet_prompt(things: list[str], look: str) -> tuple[str, int, int, str]:
    """The words for a sheet of `things` (2 to 6): the image model's prompt, and the grid it asks for."""
    cols, rows, aspect = GRIDS[len(things)]
    where = []
    for i, t in enumerate(things):
        r, c = divmod(i, cols)
        row = "top" if r == 0 and rows > 1 else "bottom" if rows > 1 else "single"
        side = ["left", "middle", "right"][c] if cols == 3 else ["left", "right"][c]
        where.append(f"{ORDINAL[i]} cell ({row} row, {side}): {t.strip().rstrip('.')}")
    prompt = (f"A reference sheet of {len(things)} separate objects arranged in an even grid of {cols} columns and "
              f"{rows} row{'s' if rows > 1 else ''}, each object alone in the middle of its own equal cell, whole and "
              "uncropped, filling about two thirds of its cell and never reaching into another cell, with wide empty "
              "space between the objects. One plain flat light grey background (#DDDDDD) everywhere; no grid lines, "
              "no borders, no frames, no shadows, no floor, no square, panel, card or backdrop behind an object (each "
              "drawn straight on the grey), no text, no letters, no numbers, no labels. All in the "
              f"same style: {SMALL_STYLE}.\n" + "\n".join(where))
    return prompt, cols, rows, aspect


def split_sheet(img, cols: int, rows: int, n: int) -> list:
    """The sheet cut into its cells: each cell's object cut out (with its shadow), or None where the cell holds no
    object or its object runs to the cell's edge (the model did not keep to the grid)."""
    import numpy as np
    W, H = img.size
    out = []
    for i in range(n):
        r, c = divmod(i, cols)
        x0, x1 = round(W * c / cols), round(W * (c + 1) / cols)
        y0, y1 = round(H * r / rows), round(H * (r + 1) / rows)
        cell = img.crop((x0, y0, x1, y1)).convert("RGBA")
        a = np.asarray(cell)
        if a[..., 3].min() > 250:
            rgb = a[..., :3].astype(int)
            bg = np.median(np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]), axis=0)
            thing = np.abs(rgb - bg).max(axis=2) > 26
        else:
            thing = a[..., 3] > 20
        ys, xs = np.nonzero(thing)
        h, w = thing.shape
        if len(xs) < 0.01 * w * h:
            out.append(None)                            # an empty cell
            continue
        m = 3
        if xs.min() <= m or ys.min() <= m or xs.max() >= w - 1 - m or ys.max() >= h - 1 - m:
            out.append(None)                            # cut by the cell's edge: not kept to the grid
            continue
        out.append(cutout(cell, strict=True))
    return out


def generate_sheet(items: list[tuple[str, str]], look: str, model: str | None = None) -> tuple[dict, list, dict]:
    """Small objects (`pic`) made on one sheet and cut apart. `items`: (the score's words, the words given to the
    image model). Returns ({score words: path}, [score words not cut cleanly], usage)."""
    model = model or DEFAULT_MODEL
    prompt, cols, rows, aspect = sheet_prompt([said for _, said in items], look)
    img, usage = _image(model, prompt, aspect, transparent=False)
    made, missed = {}, []
    CACHE.mkdir(parents=True, exist_ok=True)
    for (words, said), cut in zip(items, split_sheet(img, cols, rows, len(items))):
        if cut is None:
            missed.append(words)
            continue
        p = path_for("pic", words, look)
        cut.save(p)
        keep_said(p, said if said != words else None)
        keep_model(p, model)
        made[words] = p
    return made, missed, usage


# ---------------------------------------------------------------- better words for the image model -------------------

REFINE = """You write prompts for an image model that makes the pictures of an educational explainer video. Each
picture was asked for in a few words by the video's writer; rewrite each into the exact picture wanted, using the
narration and the shot it is in, so the model draws the right thing of the right time and place.

Write 25 to 50 words for each: what it is, exactly (its kind, period and place, e.g. "a 13th-century English iron
plough share" not "a plough"); its materials, colours and condition; its pose or how it is seen (straight on, three
quarters, from above); for a person, their age, clothes of the period, what they hold and do. For a `pic`: ONE object
or one person, whole, nothing else. For a `photo`: the scene, the viewpoint, the time of day and the light. Be
historically and factually accurate; nothing modern unless the subject is. Never ask for words, letters, numbers,
labels or signs in the picture, and do not name an art style (the style is added).

Answer only lines `ID | PROMPT`, one per picture, in the order given."""


def shots_of(score_text: str) -> dict:
    """Each entity's shot plan (the `# ---- name: plan` line a generated score puts over its shot)."""
    plan, out = "", {}
    for raw in score_text.splitlines():
        line = raw.strip()
        m = re.match(r"^#\s*-+\s*(.*?)\s*-*$", line)
        if m:
            plan = m.group(1)
            continue
        try:
            toks = shlex.split(line, comments=True)
        except ValueError:
            continue
        if len(toks) >= 4 and toks[0] == "ent":
            out[(toks[2], toks[3])] = plan
            if toks[3] == "commons" and len(toks) > 4:
                out[(toks[2], toks[4])] = plan
    return out


def refine_prompt(items: list[tuple[str, str, str]], narration: str) -> tuple[str, str]:
    """(kind, the score's words, its shot's plan) for each picture -> the call that writes better words."""
    rows = "\n".join(f"{i + 1} | {kind} | {archive_query(words) if is_archive(words) else words} | shot: {plan[:160]}"
                     for i, (kind, words, plan) in enumerate(items))
    return REFINE, f"NARRATION:\n{narration[:6000]}\n\nPICTURES (ID | kind | asked for | shot):\n{rows}"


def read_refined(text: str, n: int) -> dict:
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*\**\s*(\d+)\s*[|.:)]\s*(.+?)\s*$", line)
        if m and 1 <= int(m.group(1)) <= n and len(m.group(2)) > 8:
            out[int(m.group(1)) - 1] = m.group(2).strip().strip('"')
    return out


def _open(b: bytes):
    from PIL import Image
    return Image.open(io.BytesIO(b)).convert("RGBA")


# ---------------------------------------------------------------- finishing ------------------------------------------

def cutout(img, tol: int = 26, strict: bool = False):
    """The object alone: its own transparency when the model gave one, else the plain background taken away from
    the edges inwards (so white inside the object stays); then a flat panel drawn behind it (a grey square the object
    sits on) taken away the same way, specks and strays from a neighbouring cell dropped, trimmed, and laid on its
    paper edge with a soft shadow. `strict` (a cell of a sheet): None when what is left is too little to be the
    object, so it is made on its own."""
    import numpy as np
    from PIL import Image, ImageFilter
    from scipy import ndimage

    img = img.convert("RGBA")
    a = np.asarray(img).copy()
    rgb = a[..., :3].astype(int)

    def flood(colour, alpha):
        """Take away what is near `colour` and joined to the edge of what is left."""
        near = (np.abs(rgb - colour).max(axis=2) <= tol) & (alpha > 20)
        ys, xs = np.nonzero(alpha > 20)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        parts, _ = ndimage.label(near)
        ring = np.concatenate([parts[y0, x0:x1 + 1], parts[y1, x0:x1 + 1], parts[y0:y1 + 1, x0], parts[y0:y1 + 1, x1]])
        ids = np.unique(ring)
        gone = np.isin(parts, ids[ids > 0])
        return np.where(gone, 0, alpha)

    if a[..., 3].min() > 250:                          # no transparency: flood the background away from the edges
        edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        alpha = flood(np.median(edge, axis=0), np.full(a.shape[:2], 255, dtype="uint8"))
    else:
        alpha = a[..., 3].copy()
    def main_piece(alpha):
        """The object: its biggest piece, and any piece near its size (two hands, a pair of shoes); specks and
        strays from a neighbouring cell go."""
        parts, n = ndimage.label(alpha > 40)
        if n <= 1:
            return alpha
        sizes = ndimage.sum(np.ones_like(parts), parts, index=range(1, n + 1))
        keep = np.isin(parts, [i + 1 for i, s_ in enumerate(sizes) if s_ >= 0.2 * sizes.max()])
        return np.where(keep | ((alpha <= 40) & ndimage.binary_dilation(keep, iterations=3)), alpha, 0)

    alpha = main_piece(alpha)
    for _ in range(2):
        # a flat panel the object was drawn on: what is left still has a straight, even edge all round
        ys, xs = np.nonzero(alpha > 20)
        if not len(xs):
            break
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        ring_a = np.concatenate([alpha[y0, x0:x1 + 1], alpha[y1, x0:x1 + 1], alpha[y0:y1 + 1, x0], alpha[y0:y1 + 1, x1]])
        ring_c = np.concatenate([rgb[y0, x0:x1 + 1], rgb[y1, x0:x1 + 1], rgb[y0:y1 + 1, x0], rgb[y0:y1 + 1, x1]])
        if (ring_a > 20).mean() < 0.85 or ring_c.std(axis=0).max() > 14:
            break
        flooded = flood(np.median(ring_c, axis=0), alpha)
        if (flooded > 20).sum() < 0.12 * (alpha > 20).sum():
            break                                       # it was the object itself (a flat, square thing): kept
        alpha = flooded
    alpha = main_piece(alpha)
    if strict and (alpha > 40).sum() < 0.04 * alpha.size:
        return None
    alpha = np.asarray(Image.fromarray(alpha.astype("uint8")).filter(ImageFilter.GaussianBlur(1.0)))   # a soft edge
    a[..., 3] = alpha
    cut = Image.fromarray(a)
    box = cut.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    if box:
        cut = cut.crop(box)
    return with_shadow(paper_edge(cut))


def paper_edge(img, share: float = 0.05):
    """The cut-out on a paper die-cut: a cream border following its outline (rounded), as a sticker cut from a sheet,
    with a hairline at its edge."""
    from PIL import Image, ImageFilter
    img = img.convert("RGBA")
    W, H = img.size
    r = max(6, int(max(W, H) * share))
    big = Image.new("RGBA", (W + 2 * r, H + 2 * r), (0, 0, 0, 0))
    big.paste(img, (r, r), img)
    solid = big.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    grown = solid.filter(ImageFilter.GaussianBlur(r * 0.9)).point(lambda v: 255 if v > 22 else 0)   # round, gaps filled
    grown = grown.filter(ImageFilter.GaussianBlur(1.0))
    edge = Image.new("RGBA", big.size, (196, 184, 158, 0))
    edge.putalpha(grown)
    inner = grown.filter(ImageFilter.MinFilter(3))
    sheet = Image.new("RGBA", big.size, (251, 248, 240, 0))
    sheet.putalpha(inner)
    out = Image.alpha_composite(edge, sheet)
    return Image.alpha_composite(out, big)


def with_shadow(img, blur: int = 18, dx: int = 10, dy: int = 16, strength: float = 0.32):
    """A soft drop shadow from the picture's own shape, baked in (a cut-out laid on paper)."""
    from PIL import Image, ImageFilter
    img = img.convert("RGBA")
    if max(img.size) > 900:
        k = 900 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    pad = blur * 3
    w, h = img.width + pad * 2, img.height + pad * 2
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mask = img.getchannel("A").point(lambda v: int(v * strength))
    shade = Image.new("RGBA", img.size, (40, 30, 20, 255))
    shade.putalpha(mask)
    sh.paste(shade, (pad + dx, pad + dy), shade)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh.alpha_composite(img, (pad, pad))
    return sh


def framed(img, border: int = 22):
    """A print: the picture in a white border, a hair of grey edge, a soft shadow."""
    from PIL import Image, ImageDraw
    img = img.convert("RGB")
    if max(img.size) > 860:
        k = 860 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    card = Image.new("RGBA", (img.width + border * 2, img.height + border * 2), (251, 248, 240, 255))
    card.paste(img, (border, border))
    ImageDraw.Draw(card).rectangle([0, 0, card.width - 1, card.height - 1], outline=(214, 206, 190, 255), width=2)
    return with_shadow(card, blur=16, dx=8, dy=14, strength=0.38)


# ---------------------------------------------------------------- flags ----------------------------------------------

def flag(code: str) -> Path:
    """A country's flag as a picture (flag-icons, drawn once to PNG): `jp`, `us`, `in`..."""
    code = re.sub(r"[^a-z\-]", "", code.lower())
    out = CACHE / f"flag-{code}.png"
    if out.exists():
        return out
    src = FLAGS / f"{code}.svg"
    if not src.exists():
        raise ValueError(f"no flag {code!r} (an ISO code: jp, us, in, gb...)")
    import cairosvg
    CACHE.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(url=str(src), write_to=str(out), output_width=480)
    return out
