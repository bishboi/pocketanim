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


# Models that refused this compile (not available in this region, no access, no such model, not an image model):
# model -> why. Not asked again in the same compile: one refusal is reported for every picture, not 70 calls.
REFUSED: dict[str, str] = {}


def configured() -> str:
    """The image model the settings name (PANIM_IMAGE_MODEL), whether or not it works."""
    return os.environ.get("PANIM_IMAGE_MODEL") or MODEL_DEFAULT


def model() -> str:
    """The image model asked: the one the settings name (PANIM_IMAGE_MODEL). There is no fallback: a model that
    refuses is reported, never swapped for another."""
    return configured()


def _refusal(error: str) -> bool:
    """Whether an error means the model will refuse every picture (not a passing failure such as a timeout)."""
    return bool(re.search(r"HTTP (?:400|401|402|403|404)\b|not available in your region|returned no image|"
                          r"No endpoints found|not a valid model", error, re.I))


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


def prompt_for(what: str, style: str | None = None, realistic: bool = False, parts=None) -> str:
    """The words the model is given: the subject alone, richly detailed, as a cutout, no border, no text (labels are
    the board's own, drawn beside it: a model's lettering is garbled). `parts`: what will be labelled, each to be
    shown clearly where it can be pointed at."""
    look = ("as a realistic photograph-like image" if realistic
            else LOOKS.get(style or "", "in a clean, colourful educational illustration style"))
    named = [str(p).strip() for p in parts or [] if str(p).strip()]
    show = (f" Show each of these clearly and in its true place, easy to point at: {', '.join(named)}." if named else "")
    return (f"{what.strip()}, {look}. Richly detailed and accurate, like a plate in a good textbook: the real shapes, "
            "materials, textures and small features a student should notice, with clean outlines and clear areas of "
            f"colour.{show} One subject only, shown whole and centred, isolated as a CUTOUT on a plain, flat, "
            "pure white background: no border, no frame, no rounded card, no drop shadow box, no background scene, "
            "no floor or horizon. No words, letters, numbers or labels anywhere in the image. "
            "For a school lesson. If it is a real person, an illustrated portrait, not a photograph.")


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


# Tracing settings, most detailed first: (longest side in pixels, smallest speck kept, colour precision, layer
# difference). The first whose tracing stays under PANIM_TRACE_MAX_PATHS shapes is kept, so a richly detailed
# illustration keeps its detail and a photograph-like one is not thousands of shapes on the phone.
TRACE_LEVELS = [(720, 4, 6, 16), (600, 6, 6, 20), (512, 8, 5, 24), (384, 12, 4, 32)]


def trace_most() -> int:
    try:
        return int(os.environ.get("PANIM_TRACE_MAX_PATHS", "2200"))
    except ValueError:
        return 2200


def vectorize(png: bytes, most: int | None = None) -> str | None:
    """A cutout traced into vector shapes (vtracer: colour regions as filled paths, stacked from the largest to the
    finest; the transparent background is left out), so the phone draws it as it draws everything else, not as a
    raster frame, and the board can draw it in shape by shape. As detailed as stays under PANIM_TRACE_MAX_PATHS
    shapes (TRACE_LEVELS); `most` forces one size. None when the tracer is missing or fails."""
    try:
        import vtracer
        from PIL import Image
    except ImportError:
        return None
    levels = [(most, 8, 5, 24)] if most else TRACE_LEVELS
    svg = None
    for size, speck, colours, layers in levels:
        try:
            image = Image.open(io.BytesIO(png)).convert("RGBA")
            image.thumbnail((size, size))
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            svg = vtracer.convert_raw_image_to_svg(buffer.getvalue(), img_format="png", colormode="color",
                                                   hierarchical="stacked", mode="spline", filter_speckle=speck,
                                                   color_precision=colours, layer_difference=layers,
                                                   corner_threshold=60, length_threshold=4.0, max_iterations=10,
                                                   splice_threshold=45, path_precision=2)
        except Exception:  # noqa: BLE001 -- an image the tracer cannot read stays a PNG
            return None
        if svg.count("<path") <= trace_most():
            break
    return svg if svg and "<path" in svg else None


def _vector(target: Path) -> Path:
    """The traced SVG beside a cutout PNG, made when missing: the file a lecture shows (the PNG when tracing fails)."""
    svg = target.with_suffix(".svg")
    if not svg.exists() and target.exists():
        traced = vectorize(target.read_bytes())
        if traced:
            svg.write_text(traced, encoding="utf-8")
    return svg if svg.exists() else target


# How each model was found to answer this run (a route below), so it is asked that way straight away next time.
_ROUTE: dict[str, str] = {}
# The ways OpenRouter's image models are asked, in the order they are tried:
#   chat        chat completions, image and text out (Gemini's image models and the like)
#   chat-image  chat completions, image out only (image-only models: Recraft, FLUX and the like refuse "text")
#   images      the Image API, /api/v1/images (models OpenRouter serves only there)
ROUTES = ("chat", "chat-image", "images")
# What OpenRouter says when a model is not served the way it was asked (the next route is tried).
WRONG_ROUTE = re.compile(r"requested output modalities|/images\b|images endpoint|image generation model|"
                         r"chat/completions", re.I)


def proxy() -> str | None:
    """The proxy the image model's calls go through (PANIM_IMAGE_PROXY, e.g. http://user:pass@host:8080), for
    testing only: nothing else the harness calls uses it. Unset in production, where the server itself is where the
    model is served, and the calls go out directly (or through the machine's usual HTTPS_PROXY)."""
    return (os.environ.get("PANIM_IMAGE_PROXY") or "").strip() or None


def proxy_shown() -> str | None:
    """The proxy without its password, for the log and the test button."""
    from urllib.parse import urlsplit

    address = proxy()
    if not address:
        return None
    parts = urlsplit(address if "://" in address else f"http://{address}")
    return f"{parts.scheme}://{parts.hostname}" + (f":{parts.port}" if parts.port else "")


def _open(request, timeout: float, proxied: bool = True):
    """urlopen through PANIM_IMAGE_PROXY when it is set (for http and https alike), else as usual. `proxied`
    False: a call that is not the image model's (the label finder) goes direct."""
    import urllib.request

    address = proxy() if proxied else None
    if not address:
        return urllib.request.urlopen(request, timeout=timeout)
    address = address if "://" in address else f"http://{address}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": address, "https": address}))
    return opener.open(request, timeout=timeout)


def _post(url: str, body: dict, proxied: bool = True, who: str | None = None) -> dict:
    """POST JSON to OpenRouter; an HTTP error is raised with the provider's own message."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    try:
        with _open(request, 180, proxied) as response:
            reply = json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:400]
        try:
            detail = json.loads(detail).get("error", {}).get("message") or detail
        except (ValueError, AttributeError):
            pass
        raise RuntimeError(f"HTTP {error.code} from {who or 'the image model ' + model()}: {detail}") from None
    if isinstance(reply, dict) and reply.get("error"):
        raise RuntimeError(f"{who or 'the image model ' + model()} refused: "
                           f"{(reply['error'] or {}).get('message') or reply['error']}")
    return reply


def _chat_url() -> str:
    return os.environ.get("OPENROUTER_URL") or "https://openrouter.ai/api/v1/chat/completions"


def _images_url() -> str:
    """OpenRouter's Image API, beside chat completions (OPENROUTER_IMAGES_URL to set it outright)."""
    if os.environ.get("OPENROUTER_IMAGES_URL"):
        return os.environ["OPENROUTER_IMAGES_URL"]
    chat = _chat_url()
    return re.sub(r"chat/completions/?$", "images", chat) if chat.rstrip("/").endswith("chat/completions") \
        else chat.rstrip("/") + "/images"


def _image_bytes(ref: str) -> bytes:
    """An image the API returned: a data URL, bare base64, or a link to fetch."""
    if ref.startswith("data:image"):
        return base64.b64decode(ref.split(",", 1)[1])
    if ref.startswith("http"):
        with _open(ref, 120) as response:
            return response.read()
    return base64.b64decode(ref)


def _ask_images(prompt: str) -> tuple[bytes, float]:
    """The Image API (/api/v1/images): {model, prompt} in, the picture in data[0].b64_json (or .url) out. The way
    image-only models (meta/muse-image and the like) are asked."""
    reply = _post(_images_url(), {"model": model(), "prompt": prompt})
    items = reply.get("data") or reply.get("images") or []
    first = items[0] if items else {}
    ref = (first.get("b64_json") or first.get("url") or (first.get("image_url") or {}).get("url") or "") \
        if isinstance(first, dict) else str(first or "")
    usd = float((reply.get("usage") or {}).get("cost") or 0.0)
    if not ref:
        raise RuntimeError(f"{model()} returned no image from the Image API: {json.dumps(reply)[:200]}")
    return _image_bytes(ref), usd


def _ask_chat(prompt: str, outputs=("image", "text")) -> tuple[bytes, float]:
    """Chat completions with image output: ("image", "text") for models that also write (Gemini's image models),
    ("image",) for image-only models."""
    reply = _post(_chat_url(), {"model": model(), "modalities": list(outputs), "usage": {"include": True},
                                "messages": [{"role": "user", "content": prompt}]})
    message = ((reply.get("choices") or [{}])[0]).get("message") or {}
    data_url = next((((i.get("image_url") or {}).get("url")) for i in message.get("images") or []
                     if ((i.get("image_url") or {}).get("url") or "")), None)
    usd = float((reply.get("usage") or {}).get("cost") or 0.0)
    if not data_url:
        said = str(message.get("content") or "")[:200]
        raise RuntimeError(f"{model()} returned no image (is it an image model? On OpenRouter, an image model "
                           f"lists \"image\" as an output)" + (f"; it said: {said}" if said else ""))
    return _image_bytes(data_url), usd


def _ask_route(route: str, prompt: str) -> tuple[bytes, float]:
    if route == "images":
        return _ask_images(prompt)
    return _ask_chat(prompt, ("image",) if route == "chat-image" else ("image", "text"))


def _ask(prompt: str) -> tuple[bytes, float]:
    """The image the model makes for a prompt, and what it cost. The model is asked the way it answered before in
    this run; else each way in turn (ROUTES) while OpenRouter says it is not served that way ("No endpoints found
    that support the requested output modalities", "use the /api/v1/images endpoint"), and the way that works is
    remembered. PANIM_IMAGE_API = chat, chat-image or images asks one way only."""
    forced = os.environ.get("PANIM_IMAGE_API", "").strip().lower()
    if forced in ROUTES:
        return _ask_route(forced, prompt)
    known = _ROUTE.get(model())
    order = [known] + [r for r in ROUTES if r != known] if known else list(ROUTES)
    last: RuntimeError | None = None
    for route in order:
        try:
            got = _ask_route(route, prompt)
        except RuntimeError as error:
            if not WRONG_ROUTE.search(str(error)):
                raise
            last = error
            continue
        _ROUTE[model()] = route
        return got
    raise last or RuntimeError(f"{model()} is not served as an image model on OpenRouter")


def label_model() -> str:
    """The model that finds where a picture's labelled parts are: one that reads images (PANIM_LABEL_MODEL, else
    the SVG drawings' model, else the script's)."""
    return (os.environ.get("PANIM_LABEL_MODEL") or os.environ.get("OPENROUTER_SVG_MODEL")
            or os.environ.get("OPENROUTER_MODEL") or "google/gemini-2.5-flash")


def _spread(labels: list[str]) -> list[list]:
    """Where labels go when nothing can look at the picture (offline, PANIM_IMAGE_FAKE): spaced down its middle."""
    n = max(len(labels), 1)
    return [[label, 0.35 if k % 2 == 0 else 0.65, (k + 0.5) / n] for k, label in enumerate(labels)]


def locate(png_path: str, labels) -> list[list] | None:
    """Where each labelled part is in a picture: [[label, x, y], ...], x and y from 0 to 1 across and down the
    picture (the cutout as traced, so the board's shapes line up). A model that reads images is shown the picture
    and asked; the answer is kept beside it. Parts it cannot see are left out; None when it cannot be asked."""
    labels = [str(x).strip()[:40] for x in labels or [] if str(x).strip()][:8]
    path = Path(str(png_path))
    if not labels or not path.is_file():
        return None
    key = hashlib.sha256(f"{label_model()}|{'|'.join(labels)}".encode()).hexdigest()[:12]
    kept = path.with_name(f"{path.stem}.labels-{key}.json")
    if kept.exists():
        try:
            return json.loads(kept.read_text())
        except ValueError:
            pass
    if _fake():
        found = _spread(labels)
    elif not os.environ.get("OPENROUTER_API_KEY"):
        return None
    else:
        image = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
        ask = ("This is a picture for a school lesson. For each part named below, give the point to draw a label's "
               "pointer to: on the part itself, as x and y from 0 to 1 (x from the left edge, y from the top edge "
               "of the image). Reply with JSON only: {\"points\": [{\"label\": ..., \"x\": ..., \"y\": ...}]}. "
               "Leave out a part that is not in the picture.\nParts: " + "; ".join(labels))
        try:
            reply = _post(_chat_url(), {"model": label_model(), "temperature": 0,
                                        "messages": [{"role": "user", "content": [
                                            {"type": "image_url", "image_url": {"url": image}},
                                            {"type": "text", "text": ask}]}]},
                          proxied=False, who=f"the label finder {label_model()}")
            text = str((((reply.get("choices") or [{}])[0]).get("message") or {}).get("content") or "")
            data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        except Exception as error:  # noqa: BLE001 -- the picture is shown without its labels, and said why
            _failed(f"labels for {path.name}", str(error) or type(error).__name__)
            return None
        wanted = {label.lower(): label for label in labels}
        found = []
        for point in data.get("points") or []:
            try:
                name = wanted.get(str(point.get("label", "")).strip().lower())
                x, y = float(point["x"]), float(point["y"])
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
            if name and 0 <= x <= 1 and 0 <= y <= 1 and all(f[0] != name for f in found):
                found.append([name, round(x, 3), round(y, 3)])
    kept.write_text(json.dumps(found))
    return found


def _failed(what: str, error: str) -> None:
    FAILED.append({"what": what, "model": model(), "error": error})


def generate(what: str, style: str | None = None, realistic: bool = False, parts=None) -> dict | None:
    """A cutout picture of `what`, made by the image model (or found made already): its row, with `file` (a
    transparent PNG), `title`, `description`, `credit`, `source` "generated", `prompt`, `model`, and `usd` (what
    it cost now) or `paid` (what it cost when it was made). None when it cannot be made."""
    what = re.sub(r"\s+", " ", str(what or "")).strip()
    if not what:
        return None
    import mapguard

    if mapguard.is_map(what):
        return None              # a map is drawn on the map (Cartopy), never imagined by a model
    prompt = prompt_for(what, style, realistic, parts)
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
    if model() in REFUSED:
        _failed(what, REFUSED[model()])          # refused already this run: not asked again
        return None
    try:
        data, usd = (_stand_in(what), 0.0) if _fake() else _ask(prompt)
    except Exception as error:  # noqa: BLE001 -- offline, refused, no key: the picture is left out, and said why
        why = str(error) or type(error).__name__
        if _refusal(why):
            REFUSED[model()] = why
        _failed(what, why)
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
    out = {"model": model(), "proxy": proxy_shown(), "asked": len(ASKED), "cached": sum(1 for a in ASKED if a["cached"]),
           "made": sum(1 for m in MADE if m.get("made")), "failed": FAILED}
    return out


def check(what: str = "a red apple with one green leaf") -> dict:
    """A real call to the image model, never from the cache: whether it works, which model, how long, what it
    cost, and the picture as the model made it (PNG) and as the phone draws it (traced SVG). The app's "test"
    button on the Pictures row runs it, so a lecture with no pictures can be told apart from a model that fails."""
    import time

    out = {"model": model(), "proxy": proxy_shown(), "key": bool(os.environ.get("OPENROUTER_API_KEY")), "fake": _fake(),
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
