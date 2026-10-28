"""Pictures a score asks for, made by an image model (OpenRouter's Image API) and kept, so the engine draws real
objects, not only line icons.

    pic "PROMPT"     an object, cut out of its background, with a soft shadow under it (a banknote, a temple, a
                     farmer, a stack of coins)
    photo "PROMPT"   a picture in a white border with a shadow, as a print laid on the paper (a scene, a place)
    flag CODE        a country's flag (ISO 3166 code: jp, us, in...), from the flag-icons set: exact, never made

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
KINDS = ("pic", "photo")

# The house style each look asks the image model for (appended to every prompt).
STYLE = {
    "editorial": "editorial illustration in a realistic print style, muted warm colours, soft even studio light, "
                 "slight paper grain",
    "paper": "flat editorial illustration, warm muted colours, soft light",
}
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
    return CACHE / f"{kind}-{key(kind, prompt, look, model or DEFAULT_MODEL)}.png"


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
        if len(toks) >= 4 and toks[0] == "ent" and toks[2] in KINDS:
            pics[toks[1]] = (toks[2], toks[3], look)
        if len(toks) >= 4 and toks[0] == "ent" and toks[2] == "labels" and "on" in toks:
            i = toks.index("on")
            pic = toks[i + 1] if i + 1 < len(toks) else ""
            if pic in pics:
                names = [t for t in toks[3:i] if "@" not in t]
                out.setdefault(pics[pic], [])
                out[pics[pic]] += [n for n in names if n not in out[pics[pic]]]
    return [(k, p, lk, names) for (k, p, lk), names in out.items() if names]


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
        if len(toks) >= 4 and toks[0] == "ent" and toks[2] in KINDS:
            item = (toks[2], toks[3], look)
            if item not in out:
                out.append(item)
    return out


def prompt_for(kind: str, prompt: str, look: str) -> str:
    return f"{prompt.strip().rstrip('.')}. {STYLE.get(look, STYLE['paper'])}. {HOW[kind]}"


def generate(kind: str, prompt: str, look: str, model: str | None = None) -> tuple[Path, dict]:
    """Make the picture (one Image API call) and keep it, finished (cut out, shadowed, framed). Returns its path and
    the call's usage (cost, tokens)."""
    model = model or DEFAULT_MODEL
    key_ = os.environ.get("OPENROUTER_API_KEY")
    if not key_:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    body = {"model": model, "prompt": prompt_for(kind, prompt, look), "n": 1, "output_format": "png",
            "aspect_ratio": "1:1" if kind == "pic" else "4:3", "quality": os.environ.get("V3_IMAGE_QUALITY", "medium")}
    if kind == "pic":
        body["background"] = "transparent"     # where the model can; else we cut it out ourselves
    req = urllib.request.Request("https://openrouter.ai/api/v1/images", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key_}", "Content-Type": "application/json",
                                          "User-Agent": "harness-v3/1.0", "HTTP-Referer": "https://github.com/bishboi/pocketanim",
                                          "X-Title": "harness v3"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        said = e.read()[:600].decode(errors="replace")
        try:
            said = json.loads(said).get("error", {}).get("message") or said
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"the image model refused ({e.code}): {said}") from e
    if out.get("error"):
        raise RuntimeError(f"the image model: {out['error'].get('message') or out['error']}")
    data = (out.get("data") or [{}])[0]
    raw = data.get("b64_json")
    if not raw and data.get("url", "").startswith("data:"):
        raw = data["url"].split(",", 1)[1]
    if not raw:
        raise RuntimeError(f"the image model gave no picture: {str(out)[:300]}")
    img = _open(base64.b64decode(raw))
    done = cutout(img) if kind == "pic" else framed(img)
    p = path_for(kind, prompt, look, model)
    CACHE.mkdir(parents=True, exist_ok=True)
    done.save(p)
    return p, out.get("usage") or {}


def _open(b: bytes):
    from PIL import Image
    return Image.open(io.BytesIO(b)).convert("RGBA")


# ---------------------------------------------------------------- finishing ------------------------------------------

def cutout(img, tol: int = 26):
    """The object alone: its own transparency when the model gave one, else the plain background taken away from
    the edges inwards (so white inside the object stays), then trimmed, with a soft shadow under it."""
    import numpy as np
    from PIL import Image, ImageFilter

    img = img.convert("RGBA")
    a = np.asarray(img).copy()
    if a[..., 3].min() > 250:                          # no transparency: flood the background away from the edges
        rgb = a[..., :3].astype(int)
        edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        bg = np.median(edge, axis=0)
        near = (np.abs(rgb - bg).max(axis=2) <= tol)
        from scipy import ndimage
        parts, _ = ndimage.label(near)                 # the background's pieces that touch the edge are taken away
        edge_ids = np.unique(np.concatenate([parts[0], parts[-1], parts[:, 0], parts[:, -1]]))
        seen = np.isin(parts, edge_ids[edge_ids > 0])
        alpha = np.where(seen, 0, 255).astype("uint8")
        alpha = np.asarray(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(1.2)))   # a soft edge
        a[..., 3] = alpha
    cut = Image.fromarray(a)
    box = cut.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    if box:
        cut = cut.crop(box)
    return with_shadow(cut)


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
