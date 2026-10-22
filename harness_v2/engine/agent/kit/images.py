"""Pictures: the look's treatment of a photograph or a drawing (vox: black-and-white cutouts on paper with torn
edges; blueprint: duotone in the blueprint's blues), the stage's surface (paper grain, drafting grid), and public
domain pictures from Wikimedia Commons.

    p = photo("assets/ricci.jpg", height=4)                 # treated in the look, with its frame and shadow
    p = photo("assets/map.png", how="color", frame="none")  # untouched
    path = commons("Matteo Ricci portrait")                  # a public-domain picture into assets/, its licence beside it

Treated pictures are cached (PANIM_KIT_CACHE, default ~/.cache/panim-kit), keyed by the file and the treatment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from manim import DOWN, LEFT, PI, RIGHT, UP, ImageMobject, Rectangle, VGroup, config

from .base import PictureGroup
from .look import L

CACHE = Path(os.environ.get("PANIM_KIT_CACHE") or Path.home() / ".cache" / "panim-kit")


def _cache(key: str, suffix: str = ".png") -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / (hashlib.sha1(key.encode()).hexdigest()[:20] + suffix)


def _hex(c: str) -> np.ndarray:
    c = str(c).lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


# ---------------------------------------------------------------- the stage's surface ------------------------------
def surface_png(look=None, w: int = 1920, h: int = 1080) -> Path | None:
    """The look's stage as a picture: paper grain with a soft vignette (vox), a drafting grid (blueprint), or None
    for a plain colour."""
    from PIL import Image, ImageFilter

    look = look or L()
    if look.surface == "plain":
        return None
    out = _cache(f"surface|{look.name}|{look.bg}|{look.faint}|{look.surface}|{w}x{h}|v2")
    if out.exists():
        return out
    rng = np.random.default_rng(7)
    base = _hex(look.bg)
    yy, xx = np.mgrid[0:h, 0:w]
    vignette = 1 - 0.16 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    if look.surface == "paper":
        noise = rng.normal(0, 6, (h, w, 1)).astype(np.float32)
        fib = np.array(Image.fromarray((rng.random((h // 4, w // 4)) * 255).astype(np.uint8)).resize((w, h))
                       .filter(ImageFilter.GaussianBlur(2)), dtype=np.float32)[..., None]
        blot = np.array(Image.fromarray((rng.random((h // 60, w // 60)) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
                        .filter(ImageFilter.GaussianBlur(40)), dtype=np.float32)[..., None]
        img = (base + noise + (fib - 128) * 0.05 + (blot - 128) * 0.06) * vignette[..., None]
    else:
        img = np.tile(base, (h, w, 1)) * (0.9 + 0.1 * vignette[..., None])
        faint = _hex(look.faint)
        unit = w / config.frame_width          # pixels per scene unit
        minor, major = unit * 0.5, unit * 2.0
        for step, alpha, width in ((minor, 0.35, 1), (major, 0.8, 2)):
            for x in np.arange(w / 2 % step, w, step):
                img[:, int(x):int(x) + width] = img[:, int(x):int(x) + width] * (1 - alpha) + faint * alpha
            for y in np.arange(h / 2 % step, h, step):
                img[int(y):int(y) + width, :] = img[int(y):int(y) + width, :] * (1 - alpha) + faint * alpha
        img += rng.normal(0, 3, (h, w, 1)).astype(np.float32)
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out)
    return out


def surface(look=None):
    """The stage surface as a mobject the size of the frame (KitScene puts it behind everything and keeps it on the
    camera)."""
    look = look or L()
    path = surface_png(look)
    if path is None:
        return Rectangle(width=config.frame_width, height=config.frame_height, stroke_width=0, fill_color=look.bg,
                         fill_opacity=1)
    im = ImageMobject(str(path))
    im.set_resampling_algorithm(2)
    im.stretch_to_fit_width(config.frame_width).stretch_to_fit_height(config.frame_height)
    return im


# ---------------------------------------------------------------- treating a picture -------------------------------
TREATMENTS = ("cutout", "bw", "color", "duotone", "halftone", "sepia")
FRAMES = ("torn", "sticker", "polaroid", "border", "none")


def _torn_mask(w: int, h: int, depth: int, seed: int):
    """An alpha mask with ragged edges (paper torn by hand)."""
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(seed)

    def edge(n, d):
        steps = rng.normal(0, d * 0.35, n).cumsum()
        steps = steps - np.linspace(steps[0], steps[-1], n)
        return np.clip(d + steps, d * 0.2, d * 1.8)

    top, bottom = edge(w // 6 + 2, depth), edge(w // 6 + 2, depth)
    left, right = edge(h // 6 + 2, depth), edge(h // 6 + 2, depth)
    pts = [(x * 6, top[x]) for x in range(len(top))]
    pts += [(w - right[y], y * 6) for y in range(len(right))]
    pts += [(w - x * 6, h - bottom[x]) for x in range(len(bottom))]
    pts += [(left[y], h - y * 6) for y in range(len(left))]
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m.filter(ImageFilter.GaussianBlur(0.8))


def treat(path: str | Path, how: str | None = None, frame: str | None = None, max_px: int = 1400, seed: int = 1,
          shadow: bool | None = None) -> Path:
    """A picture made over in the look: `how` (TREATMENTS) and `frame` (FRAMES) default to the look's; the drop
    shadow is drawn into the picture. Returns the new PNG's path."""
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

    look = L()
    how = how or look.photo
    frame = frame or ("torn" if look.name == "vox" else "border")
    shadow = look.shadow if shadow is None else shadow
    src = Path(path)
    key = f"treat|{src.resolve()}|{src.stat().st_mtime}|{how}|{frame}|{look.name}|{look.bg}|{look.ink}|{shadow}|{seed}|v3"
    out = _cache(key)
    if out.exists():
        return out
    im = Image.open(src).convert("RGBA")
    im.thumbnail((max_px, max_px))
    rgb, alpha = im.convert("RGB"), im.getchannel("A")
    has_alpha = alpha.getextrema()[0] < 250

    if how in ("cutout", "bw", "halftone"):
        g = ImageOps.autocontrast(rgb.convert("L"), cutoff=1)
        g = ImageEnhance.Contrast(g).enhance(1.25)
        if how == "halftone":
            arr = np.array(g, dtype=np.float32) / 255
            cell = max(4, im.width // 160)
            yy, xx = np.mgrid[0:im.height, 0:im.width]
            cy, cx = (yy // cell) * cell + cell / 2, (xx // cell) * cell + cell / 2
            dark = 1 - arr[(np.clip(cy, 0, im.height - 1)).astype(int), (np.clip(cx, 0, im.width - 1)).astype(int)]
            dist = np.hypot(yy - cy, xx - cx) / (cell * 0.72)
            dots = (dist < np.sqrt(dark)).astype(np.float32)
            g = Image.fromarray((255 * (1 - dots * 0.9)).astype(np.uint8))
        paper = _hex("#F4EEE2" if look.name == "vox" else look.bg)
        ink = _hex("#1E1B18")
        a = np.array(g, dtype=np.float32)[..., None] / 255
        rgb = Image.fromarray((ink + (paper - ink) * a).astype(np.uint8))
    elif how == "duotone":
        a = np.array(ImageOps.autocontrast(rgb.convert("L"), cutoff=1), dtype=np.float32)[..., None] / 255
        dark, light = _hex(look.bg) * 0.75, _hex(look.ink)
        rgb = Image.fromarray((dark + (light - dark) * a).astype(np.uint8))
    elif how == "sepia":
        a = np.array(rgb.convert("L"), dtype=np.float32)[..., None] / 255
        dark, light = _hex("#3B2A1A"), _hex("#F2E3C6")
        rgb = Image.fromarray((dark + (light - dark) * a).astype(np.uint8))
    # how == "color": as it is

    W, H = rgb.size
    pad = max(10, W // 40)
    if frame == "sticker" or (has_alpha and frame in ("torn", "polaroid")):
        # A cutout with its own outline: a white border grown round its shape.
        grown = alpha.filter(ImageFilter.MaxFilter(2 * (pad // 2) + 1))
        base = Image.new("RGBA", (W, H), (255, 255, 255, 0))
        base.putalpha(grown)
        body = rgb.convert("RGBA")
        body.putalpha(alpha)
        canvas = Image.alpha_composite(base, body)
        cut = grown
    elif frame == "torn":
        bw, bh = W + 2 * pad, H + 2 * pad
        canvas = Image.new("RGBA", (bw, bh), (247, 242, 232, 255))
        canvas.paste(rgb, (pad, pad))
        cut = _torn_mask(bw, bh, max(6, pad // 1.5), seed)
        canvas.putalpha(ImageChops.multiply(cut, Image.new("L", (bw, bh), 255)))
    elif frame == "polaroid":
        bw, bh = W + 2 * pad, H + pad + pad * 5
        canvas = Image.new("RGBA", (bw, bh), (250, 248, 243, 255))
        canvas.paste(rgb, (pad, pad))
        cut = canvas.getchannel("A")
    elif frame == "border":
        line = tuple(int(v) for v in _hex(look.ink)) + (255,)
        b = max(3, W // 300)
        canvas = Image.new("RGBA", (W + 2 * b, H + 2 * b), line)
        canvas.paste(rgb, (b, b))
        if has_alpha:
            canvas = rgb.convert("RGBA")
            canvas.putalpha(alpha)
        cut = canvas.getchannel("A")
    else:
        canvas = rgb.convert("RGBA")
        canvas.putalpha(alpha)
        cut = alpha

    if shadow:
        off = max(6, canvas.width // 70)
        blur = max(6, canvas.width // 60)
        full = Image.new("RGBA", (canvas.width + off + 2 * blur, canvas.height + off + 2 * blur), (0, 0, 0, 0))
        sh = Image.new("RGBA", canvas.size, tuple(int(v) for v in _hex(look.shadow_color)) + (0,))
        sh.putalpha(cut.point(lambda v: int(v * 0.45)))
        full.alpha_composite(sh, (blur + off, blur + off))
        full = full.filter(ImageFilter.GaussianBlur(blur * 0.6))
        full.alpha_composite(canvas, (blur, blur))
        canvas = full
    canvas.save(out)
    return out


class Photo(PictureGroup):
    enter_kind = "shape"


def photo(path: str | Path, height: float = 3.5, width: float | None = None, how: str | None = None,
          frame: str | None = None, tilt: float | None = None, tape: bool | None = None, caption: str | None = None,
          seed: int = 1) -> Photo:
    """A picture on the stage, treated in the look (treat()), scaled to `height` (or `width`), tilted by `tilt`
    degrees (default the look's casual tilt), with tape on its top corners (vox) and a caption under it."""
    from .text import text

    look = L()
    out = treat(path, how=how, frame=frame, seed=seed)
    im = ImageMobject(str(out))
    if width:
        im.scale_to_fit_width(width)
    else:
        im.scale_to_fit_height(height)
    p = Photo(im)
    p.name_part("image", im)
    if tape if tape is not None else look.name == "vox" and (frame or "torn") != "sticker":
        strips = VGroup()
        for corner, ang in ((im.get_corner(UP + LEFT), 30), (im.get_corner(UP + RIGHT), -30)):
            s = Rectangle(width=0.9, height=0.28, stroke_width=0, fill_color="#F3E7C4", fill_opacity=0.82)
            s.rotate(ang * PI / 180).move_to(corner + DOWN * 0.12 + (RIGHT if ang > 0 else LEFT) * 0.12)
            strips.add(s)
        p.add(strips)
        p.name_part("tape", strips)
    if caption:
        cap = text(caption, size=22, role="hand" if look.name == "vox" else "mono", color=look.ink, width=im.width)
        cap.next_to(im, DOWN, buff=0.12)
        p.add(cap)
        p.name_part("caption", cap)
    t = look.tilt if tilt is None else tilt
    if t:
        p.rotate(t * PI / 180 * (1 if seed % 2 else -1))
    return p


# ---------------------------------------------------------------- public-domain pictures ---------------------------
UA = {"User-Agent": "pocketanim-kit/1.0 (https://github.com/bishboi/pocketanim) python-urllib"}


def _api(**params):
    params["format"] = "json"
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    for k in range(6):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(4 * (k + 1))
    raise RuntimeError("Wikimedia Commons is rate limiting; try again in a minute")


FREE = re.compile(r"public domain|cc0|cc[- ]by(?!.*nc)|pd[- ]|no restrictions", re.I)


def commons_search(query: str, n: int = 8) -> list[dict]:
    """Pictures on Wikimedia Commons for a query: [{title, license, date, width, height, url}], free licences
    only."""
    d = _api(action="query", generator="search", gsrsearch=query, gsrnamespace=6, gsrlimit=n, prop="imageinfo",
             iiprop="url|extmetadata|size", iiurlwidth=1200)
    rows = []
    for page in (d.get("query", {}).get("pages") or {}).values():
        ii = page["imageinfo"][0]
        meta = ii.get("extmetadata", {})
        lic = re.sub("<[^>]+>", "", meta.get("LicenseShortName", {}).get("value", ""))
        if not FREE.search(lic) or not re.search(r"\.(jpe?g|png|tiff?)$", page["title"], re.I):
            continue
        rows.append({"title": page["title"], "license": lic, "url": ii.get("thumburl") or ii["url"],
                     "page": ii.get("descriptionurl"), "width": ii["width"], "height": ii["height"],
                     "date": re.sub("<[^>]+>", "", meta.get("DateTimeOriginal", {}).get("value", ""))[:40],
                     "artist": re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", ""))[:120]})
    return rows


def commons(query_or_title: str, out_dir: str | Path = "assets", name: str | None = None) -> Path:
    """Download a freely licensed picture from Wikimedia Commons (a "File:..." title, or the best hit for a query)
    into `out_dir`, with its licence and source beside it (<name>.json). Returns the picture's path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if query_or_title.startswith("File:"):
        d = _api(action="query", titles=query_or_title, prop="imageinfo", iiprop="url|extmetadata|size", iiurlwidth=1200)
        page = next(iter(d["query"]["pages"].values()))
        ii = page["imageinfo"][0]
        meta = ii.get("extmetadata", {})
        row = {"title": page["title"], "url": ii.get("thumburl") or ii["url"], "page": ii.get("descriptionurl"),
               "license": re.sub("<[^>]+>", "", meta.get("LicenseShortName", {}).get("value", ""))}
    else:
        hits = commons_search(query_or_title)
        if not hits:
            raise LookupError(f"no freely licensed picture on Commons for {query_or_title!r}")
        row = hits[0]
    stem = name or re.sub(r"[^\w]+", "_", row["title"].split(":", 1)[-1].rsplit(".", 1)[0]).strip("_")[:60]
    ext = Path(urllib.parse.urlparse(row["url"]).path).suffix.lower() or ".jpg"
    path = out_dir / f"{stem}{ext}"
    for k in range(5):
        try:
            path.write_bytes(urllib.request.urlopen(urllib.request.Request(row["url"], headers=UA), timeout=60).read())
            break
        except Exception:
            if k == 4:
                raise
            time.sleep(3 * (k + 1))
    (out_dir / f"{stem}.json").write_text(json.dumps(row, ensure_ascii=False, indent=1))
    return path
