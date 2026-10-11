"""Pictures made by an image model, as cutouts: the only kind of picture a lecture takes that is not drawn as an SVG
(lib/drawings.ts) or built in Manim. Nothing is searched for on the web.

A picture is asked for in words ("a steam locomotive, side view", "Mahatma Gandhi"). The model is asked for the
subject alone, isolated on plain white, with no border, frame, background scene or text; the white around it is
then made transparent and the picture trimmed to the subject (cutout), so it sits on the board like a sticker;
and it is traced into vector shapes (vectorize), so the phone draws it like the rest of the board.

Each is made once: cached by its words, style and model (.cache/images/gen-<key>.png, its cost beside it). What
this process made, and what it cost, is in MADE (compile_lecture --json reports it; the app bills it).

    python genimage.py "a steam locomotive, side view"        # makes one, prints its row
    python genimage.py --realistic "Taj Mahal, front view"    # photograph-like (a book's photo made again)
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("PANIM_IMAGE_CACHE") or (HERE / ".cache" / "images"))
MODEL_DEFAULT = "google/gemini-2.5-flash-image"
# What this process made: [{path, prompt, model, usd}], for the bill.
MADE: list[dict] = []
# Pictures asked for that the model did not make, and why: [{what, model, error}] (compile_lecture --json reports
# them, so a lecture says "the image model failed: HTTP 404 ..." instead of quietly showing fewer pictures).
FAILED: list[dict] = []
# Every picture a script asked the image model for, made now or found made already: [{what, cached}].
ASKED: list[dict] = []

LOOKS = {
    "parchment": "drawn like an engraved plate in an old textbook, sepia ink",
    "lab": "in a clean, modern science-textbook style",
    "cosmos": "in a clean, bright illustration style",
    "chalkboard": "in a clean, colourful illustration style that reads well on a dark board",
    "blueprint": "in a clean technical-illustration style",
}


def model() -> str:
    return os.environ.get("PANIM_IMAGE_MODEL") or MODEL_DEFAULT


def enabled() -> bool:
    """Whether pictures can be made here: a key for the image model (or the offline stand-in, PANIM_IMAGE_FAKE=1),
    and not turned off (PANIM_IMAGES=0)."""
    return (bool(os.environ.get("OPENROUTER_API_KEY")) or _fake()) and os.environ.get("PANIM_IMAGES", "1") != "0"


def _fake() -> bool:
    """PANIM_IMAGE_FAKE=1: a plain stand-in picture instead of the model's (tests, and building offline)."""
    return os.environ.get("PANIM_IMAGE_FAKE") == "1"


def _stand_in(what: str) -> bytes:
    """A coloured disc on white, its colour from the words: what the model would be asked for, offline."""
    from PIL import Image, ImageDraw

    shade = int(hashlib.md5(what.encode()).hexdigest()[:6], 16)
    image = Image.new("RGB", (320, 240), (255, 255, 255))
    ImageDraw.Draw(image).ellipse((60, 20, 260, 220), fill=((shade >> 16) & 255, (shade >> 8) & 255, shade & 255))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def most() -> int:
    """At most this many new pictures a process (PANIM_IMAGE_MAX, 40): a runaway script cannot run up a bill."""
    try:
        return int(os.environ.get("PANIM_IMAGE_MAX", "40"))
    except ValueError:
        return 40


def prompt_for(what: str, style: str | None = None, realistic: bool = False) -> str:
    """The words the model is given: the subject alone, as a cutout, no border, no text."""
    look = ("as a realistic photograph-like image" if realistic
            else LOOKS.get(style or "", "in a clean, colourful educational illustration style"))
    return (f"{what.strip()}, {look}. One subject only, shown whole and centred, isolated as a CUTOUT on a plain, flat, "
            "pure white background: no border, no frame, no rounded card, no drop shadow box, no background scene, "
            "no floor or horizon. No words, letters, numbers or labels anywhere in the image. Accurate and clear, "
            "for a school lesson. If it is a real person, an illustrated portrait, not a photograph.")


def cutout(data: bytes, tolerance: int = 28) -> bytes:
    """The picture with the plain background around its subject made transparent and the rest trimmed away: the
    pixels near the corners' colour that are connected to the edge go (white inside the subject stays), with a
    soft one-pixel edge. PNG bytes."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage

    image = Image.open(io.BytesIO(data)).convert("RGBA")
    pixels = np.asarray(image).astype(np.int16)
    rgb = pixels[..., :3]
    h, w = rgb.shape[:2]
    corners = np.array([rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]])
    background = np.median(corners, axis=0)
    near = np.abs(rgb - background).max(axis=2) <= tolerance
    labels, _ = ndimage.label(near)
    edge = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    outside = np.isin(labels, list(edge)) if edge else np.zeros_like(near)
    alpha = np.where(outside, 0, 255).astype(np.uint8)
    # A soft edge: the subject's outermost pixels half transparent, so it does not look cut with scissors.
    grown = ndimage.binary_dilation(alpha == 0, iterations=1) & (alpha == 255)
    alpha[grown] = 160
    out = np.dstack([pixels[..., :3].astype(np.uint8), alpha])
    picture = Image.fromarray(out, "RGBA")
    box = picture.getbbox()
    if box:
        pad = 6
        picture = picture.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad)))
    buffer = io.BytesIO()
    picture.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def vectorize(png: bytes, most: int = 512) -> str | None:
    """A cutout traced into vector shapes (vtracer: colour regions as filled paths; the transparent background is
    left out), so the phone draws it as it draws everything else, not as a raster frame. Shrunk to `most` pixels
    first and fine speckle dropped, so it stays a few dozen paths. None when the tracer is missing or fails."""
    try:
        import vtracer
        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        image.thumbnail((most, most))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        svg = vtracer.convert_raw_image_to_svg(buffer.getvalue(), img_format="png", colormode="color",
                                               hierarchical="stacked", mode="spline", filter_speckle=8,
                                               color_precision=5, layer_difference=24, corner_threshold=60,
                                               length_threshold=4.0, max_iterations=10, splice_threshold=45,
                                               path_precision=2)
    except Exception:  # noqa: BLE001 -- an image the tracer cannot read stays a PNG
        return None
    return svg if "<path" in svg else None


def _vector(target: Path) -> Path:
    """The traced SVG beside a cutout PNG, made when missing: the file a lecture shows (the PNG when tracing fails)."""
    svg = target.with_suffix(".svg")
    if not svg.exists() and target.exists():
        traced = vectorize(target.read_bytes())
        if traced:
            svg.write_text(traced, encoding="utf-8")
    return svg if svg.exists() else target


def _ask(prompt: str) -> tuple[bytes | None, float]:
    """The image the model returns for a prompt (OpenRouter), and what it cost."""
    import urllib.request

    url = os.environ.get("OPENROUTER_URL") or "https://openrouter.ai/api/v1/chat/completions"
    body = json.dumps({"model": model(), "modalities": ["image", "text"], "usage": {"include": True},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    request = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    import urllib.error

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            reply = json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:400]
        try:
            detail = json.loads(detail).get("error", {}).get("message") or detail
        except (ValueError, AttributeError):
            pass
        raise RuntimeError(f"HTTP {error.code} from the image model {model()}: {detail}") from None
    if reply.get("error"):
        raise RuntimeError(f"the image model {model()} refused: {(reply['error'] or {}).get('message') or reply['error']}")
    message = ((reply.get("choices") or [{}])[0]).get("message") or {}
    data_url = next((((i.get("image_url") or {}).get("url")) for i in message.get("images") or []
                     if ((i.get("image_url") or {}).get("url") or "").startswith("data:image")), None)
    usd = float((reply.get("usage") or {}).get("cost") or 0.0)
    if not data_url:
        said = str(message.get("content") or "")[:200]
        raise RuntimeError(f"{model()} returned no image (is it an image model? OpenRouter's image models list "
                           f"\"image\" in their output modalities)" + (f"; it said: {said}" if said else ""))
    return base64.b64decode(data_url.split(",", 1)[1]), usd


def _failed(what: str, error: str) -> None:
    FAILED.append({"what": what, "model": model(), "error": error})


def generate(what: str, style: str | None = None, realistic: bool = False) -> dict | None:
    """A cutout picture of `what`, made by the image model (or found made already): its row, with `file` (a
    transparent PNG), `title`, `description`, `credit`, `source` "generated", `prompt`, `model`, and `usd` (what
    it cost now) or `paid` (what it cost when it was made). None when it cannot be made."""
    what = re.sub(r"\s+", " ", str(what or "")).strip()
    if not what:
        return None
    import mapguard

    if mapguard.is_map(what):
        return None              # a map is drawn on the map (Cartopy), never imagined by a model
    prompt = prompt_for(what, style, realistic)
    key = hashlib.sha256(f"{model()}|{prompt}".encode()).hexdigest()[:20]
    target = CACHE / f"gen-{key}.png"
    row = {"id": f"gen:{key}", "title": what[:200], "description": what[:500], "source": "generated",
           "license": "generated", "artist": model(), "credit": f"made with {model()}", "prompt": prompt,
           "model": model(), "png": str(target)}
    ASKED.append({"what": what, "cached": target.exists()})
    if target.exists():
        shown = _vector(target)
        row.update(file=str(shown), path=str(shown))
        try:
            paid = float(json.loads(target.with_suffix(".json").read_text()).get("usd") or 0.0)
        except (OSError, ValueError):
            paid = None
        return {**row, "paid": paid}
    if not enabled():
        _failed(what, "the image model is off (PANIM_IMAGES=0)" if os.environ.get("PANIM_IMAGES") == "0"
                else "no OPENROUTER_API_KEY in the compiler's environment")
        return None
    if sum(1 for m in MADE if m.get("made")) >= most():
        _failed(what, f"the limit of {most()} new pictures a lecture was reached (PANIM_IMAGE_MAX)")
        return None
    try:
        data, usd = (_stand_in(what), 0.0) if _fake() else _ask(prompt)
    except Exception as error:  # noqa: BLE001 -- offline, refused, no key: the picture is left out, and said why
        _failed(what, str(error) or type(error).__name__)
        return None
    try:
        data = cutout(data)
    except Exception:  # noqa: BLE001 -- an image the cutout cannot read is kept as the model made it
        pass
    CACHE.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.with_suffix(".json").write_text(json.dumps({"what": what, "prompt": prompt, "model": model(), "style": style,
                                                       "realistic": realistic, "usd": usd}))
    shown = _vector(target)
    MADE.append({"path": str(shown), "png": str(target), "what": what, "prompt": prompt, "model": model(), "usd": usd,
                 "made": True})
    return {**row, "file": str(shown), "path": str(shown), "usd": usd, "made": True}


def report() -> dict:
    """What this process asked of the image model: how many pictures, how many made now, found made, failed (and
    why), and which model, for the lecture's log (compile_lecture --json "images")."""
    return {"model": model(), "asked": len(ASKED), "cached": sum(1 for a in ASKED if a["cached"]),
            "made": sum(1 for m in MADE if m.get("made")), "failed": FAILED}


def check(what: str = "a red apple with one green leaf") -> dict:
    """A real call to the image model, never from the cache: whether it works, which model, how long, what it
    cost, and the picture as the model made it (PNG) and as the phone draws it (traced SVG). The app's "test"
    button on the Pictures row runs it, so a lecture with no pictures can be told apart from a model that fails."""
    import time

    out = {"model": model(), "key": bool(os.environ.get("OPENROUTER_API_KEY")), "fake": _fake(),
           "off": os.environ.get("PANIM_IMAGES") == "0", "ok": False}
    if not out["key"] and not out["fake"]:
        return {**out, "error": "OPENROUTER_API_KEY is not set where the compiler runs (harness/app/.env.local)"}
    started = time.time()
    try:
        data, usd = (_stand_in(what), 0.0) if _fake() else _ask(prompt_for(what))
    except Exception as error:  # noqa: BLE001 -- reported, not raised
        return {**out, "error": str(error) or type(error).__name__, "seconds": round(time.time() - started, 1)}
    out.update(seconds=round(time.time() - started, 1), usd=usd, bytes=len(data))
    try:
        png = cutout(data)
    except Exception as error:  # noqa: BLE001
        return {**out, "error": f"the model's picture could not be cut out: {error}"}
    svg = vectorize(png)
    out.update(ok=True, png="data:image/png;base64," + base64.b64encode(png).decode(),
               svg=svg, paths=svg.count("<path") if svg else 0,
               traced=bool(svg), note=None if svg else "vtracer is missing: the picture stays a PNG (tier 3)")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--check" in args:
        print(json.dumps(check(" ".join(a for a in args if a != "--check") or "a red apple with one green leaf")))
        sys.exit(0)
    realistic = "--realistic" in args
    args = [a for a in args if a != "--realistic"]
    print(json.dumps(generate(" ".join(args), realistic=realistic), ensure_ascii=False))
