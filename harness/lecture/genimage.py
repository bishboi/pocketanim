"""Pictures made by image models: every picture a lecture shows that is not built in Manim. Two models: the
illustration model (PANIM_IMAGE_MODEL) for people, places, objects and scenes, and the diagram model
(PANIM_DIAGRAM_MODEL) for detailed diagrams, labelled pictures and the book's diagrams redrawn. Nothing is searched
for on the web, and nothing is drawn as an SVG.

A picture is asked for in words ("a steam locomotive, side view", "Mahatma Gandhi"). The model is asked for the
subject alone, isolated on plain white, with no border, frame, background scene or text; the white around it is
then made transparent and the picture trimmed to the subject (cutout), so it sits on the board like a sticker.
The phone draws the PNG itself (the program's `image` lines), so it is shown as it was made.

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
import threading
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("PANIM_IMAGE_CACHE") or (HERE / ".cache" / "images"))
MODEL_DEFAULT = "google/gemini-2.5-flash-image"
# What this process made: [{path, prompt, model, usd}], for the bill.
MADE: list[dict] = []
# When the image models were at work in this process ([start, end], ms since the epoch): a compile's picture time,
# for the lecture's timing (compile_lecture --json "image_spans").
SPANS: list[list[float]] = []
# Every request to an image model or a model that reads images, for the lecture's timing log: what it was for
# (the picture's subject, a figure), which model, when, how it ended.
CALLS: list[dict] = []


def _about() -> str:
    return getattr(_LOCAL, "about", "") or ""


@contextmanager
def about(what: str):
    """The requests inside are for `what` (a picture's subject, a figure's caption), in the timing log."""
    before = _about()
    _LOCAL.about = str(what)[:120]
    try:
        yield
    finally:
        _LOCAL.about = before


@contextmanager
def _timed():
    start = time.time() * 1000
    try:
        yield
    finally:
        SPANS.append([start, time.time() * 1000])
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
# Models that take words only (no picture in the request): asked once with a reference picture, they said so; from
# then on, this run, they are asked in words alone (NO_REFERENCE).
NO_REFERENCE: set[str] = set()
IMAGE_INPUT_REFUSED = re.compile(r"support(?:s|ed)? (?:the requested )?(?:image input|input modalit)|"
                                 r"image input|does not support images?|vision (?:is )?not supported", re.I)


def configured() -> str:
    """The illustration model the settings name (PANIM_IMAGE_MODEL), whether or not it works: people, places,
    objects and scenes, made quickly and cheaply."""
    return os.environ.get("PANIM_IMAGE_MODEL") or MODEL_DEFAULT


def diagram_model() -> str:
    """The model for detailed diagrams (PANIM_DIAGRAM_MODEL, else the illustration model): the book's figures redrawn
    in the lecture's style with every label kept, and labelled pictures whose parts must be right. A slower,
    more careful model that writes words well and follows a reference picture."""
    return os.environ.get("PANIM_DIAGRAM_MODEL") or configured()


# Which of the two models the calls below are for ("illustration" or "diagram"): set by using().
# Per thread: pictures are made several at once (prefetch), each thread asking its own model.
_LOCAL = threading.local()


def _stack(name: str, first: list) -> list:
    if not hasattr(_LOCAL, name):
        setattr(_LOCAL, name, list(first))
    return getattr(_LOCAL, name)


class _Stack:
    """A list per thread, used as the module's _KIND and _PIN were (append, pop, [-1], truth)."""

    def __init__(self, name: str, first: list):
        self.name, self.first = name, first

    def _list(self) -> list:
        return _stack(self.name, self.first)

    def append(self, value) -> None:
        self._list().append(value)

    def pop(self):
        return self._list().pop()

    def __getitem__(self, index):
        return self._list()[index]

    def __bool__(self) -> bool:
        return bool(self._list())

    def __len__(self) -> int:
        return len(self._list())


_KIND = _Stack("kind", ["illustration"])


@contextmanager
def using(kind: str):
    """The calls inside go to the diagram model (kind "diagram") or the illustration model."""
    _KIND.append("diagram" if kind == "diagram" else "illustration")
    try:
        yield
    finally:
        _KIND.pop()


# A model the calls inside are pinned to (a fallback being asked): set by _pinned().
_PIN = _Stack("pin", [])


@contextmanager
def _pinned(name: str):
    _PIN.append(name)
    try:
        yield
    finally:
        _PIN.pop()


def model() -> str:
    """The image model asked now: the illustration model, or the diagram model inside using("diagram"), or a
    fallback model while it is being asked (fallbacks())."""
    if _PIN:
        return _PIN[-1]
    return diagram_model() if _KIND[-1] == "diagram" else configured()


def fallbacks() -> list[str]:
    """The models asked, in order, when the model for this kind of picture refuses one or its filter blocks it:
    PANIM_DIAGRAM_FALLBACK_MODELS for diagrams and the book's figures, PANIM_IMAGE_FALLBACK_MODELS for
    illustrations (comma-separated OpenRouter ids). None by default: nothing is swapped unless they are set."""
    name = "PANIM_DIAGRAM_FALLBACK_MODELS" if _KIND[-1] == "diagram" else "PANIM_IMAGE_FALLBACK_MODELS"
    first = diagram_model() if _KIND[-1] == "diagram" else configured()
    out: list[str] = []
    for item in re.split(r"[,\s]+", os.environ.get(name, "")):
        if item and item != first and item not in out:
            out.append(item)
    return out


# The model's content filter blocked this one picture (the words or the reference): not a refusal of every
# picture, so the next is still asked; this one is asked again in plainer words, then of the fallbacks.
FILTERED = re.compile(r"content (?:management )?polic|content[_ ]?filter|filtered|moderation|safety (?:system|"
                      r"filter|policy)|responsible ?ai|prohibited content|flagged", re.I)


def _refusal(error: str) -> bool:
    """Whether an error means the model will refuse every picture (not a passing failure such as a timeout, nor a
    content filter that blocked one picture)."""
    if FILTERED.search(error):
        return False
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


SCENE_FRAME = ("A whole SCENE, not a cutout: the setting drawn edge to edge in a wide 16:9 landscape composition (the "
               "place, its ground and sky, the people in it doing what the lesson tells of), a clear main subject near "
               "the centre, few small details at the edges. No border or frame. No words, letters, numbers or labels "
               "anywhere in the image. For a school lesson.")


def prompt_for(what: str, style: str | None = None, realistic: bool = False, parts=None,
               context: str | None = None, scene: bool = False, like: str | None = None) -> str:
    """The words the model is given: the subject alone, richly detailed, as a cutout, no border, no text (labels are
    the board's own, drawn beside it: a model's lettering is garbled). `parts`: what will be labelled, each to be
    shown clearly where it can be pointed at."""
    look = ("as a realistic photograph-like image" if realistic
            else LOOKS.get(style or "", "in a clean, colourful educational illustration style"))
    named = [str(p).strip() for p in parts or [] if str(p).strip()]
    show = (f" Show each of these clearly and in its true place, easy to point at: {', '.join(named)}." if named else "")
    # What it is for: the lesson, the chapter, what the teacher says while it is on screen (the teacher's words may
    # be in Hindi or Hinglish). The picture shows what the lesson needs the student to see there, true to its
    # time, place and subject.
    purpose = (f" WHAT IT IS FOR: {context.strip()} Draw what the student needs to see at this moment of the lesson, "
               "accurate to the time, place and subject described (clothing, buildings, tools, landscape of that "
               "period and region)." if context and context.strip() else "")
    # The same person or thing as a picture made before in this lecture (the reference image sent with this one).
    same = (f" THE REFERENCE IMAGE shows {like.strip()} as already drawn in this lesson: draw the SAME one (the same "
            "face, hair, beard, build, clothing and colours, in the same art style), only as this picture asks."
            if like else "")
    if scene:
        return (f"{what.strip()}, {look}.{purpose}{same} Richly detailed and accurate, like a painted plate in a good "
                f"textbook.{show} {SCENE_FRAME}")
    return (f"{what.strip()}, {look}.{purpose}{same} Richly detailed and accurate, like a plate in a good textbook: the real shapes, "
            "materials, textures and small features a student should notice, with clean outlines and clear areas of "
            f"colour.{show} One subject only, shown whole and centred, isolated as a CUTOUT on a plain, flat, "
            "pure white background: no border, no frame, no rounded card, no drop shadow box, no background scene, "
            "no floor or horizon. No words, letters, numbers or labels anywhere in the image. "
            "For a school lesson. If it is a real person, an illustrated portrait, not a photograph.")


def flat_background(data: bytes, tolerance: int = 28) -> bool:
    """Whether a picture stands on one flat colour (its four corners alike): only then is there a background to cut
    away; a photograph or a scene keeps its own."""
    import numpy as np
    from PIL import Image

    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).astype(np.int16)
    h, w = rgb.shape[:2]
    corners = np.array([rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]])
    return bool((np.abs(corners - np.median(corners, axis=0)).max(axis=1) <= tolerance).all())


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
    start = time.time() * 1000
    error = None
    try:
        with _timed():
            return _post_now(url, body, proxied, who)
    except Exception as failure:  # noqa: BLE001 -- recorded, then raised as it was
        error = str(failure)[:200]
        raise
    finally:
        CALLS.append({"for": _about(), "who": who or "image", "model": str(body.get("model") or ""),
                      "route": "images" if url.rstrip("/").endswith("/images") else "chat",
                      "start": start, "end": time.time() * 1000, **({"error": error} if error else {})})


def _post_now(url: str, body: dict, proxied: bool = True, who: str | None = None) -> dict:
    import urllib.error
    import urllib.request

    import providers

    if providers.direct(body.get("model")):
        # An OpenAI model, with an OpenAI key: asked of OpenAI itself (providers.py). Its pictures come from its
        # image generation (no reference picture: that is an edit, which this does not send).
        url, headers, body = providers.images(body) if url.rstrip("/").endswith("/images") else providers.chat(body)
    else:
        headers = {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                   "Content-Type": "application/json"}
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
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


def _ask_images(prompt: str, reference: bytes | None = None) -> tuple[bytes, float]:
    """The Image API (/api/v1/images): {model, prompt} in, the picture in data[0].b64_json (or .url) out. The way
    image-only models (meta/muse-image and the like) are asked. `reference`: a picture sent with the words in
    input_references (image to image), e.g. the book's figure to redraw."""
    import providers

    body: dict = {"model": model(), "prompt": prompt}
    if reference:
        url = "data:image/png;base64," + base64.b64encode(reference).decode()
        body["input_references"] = [{"type": "image_url", "image_url": {"url": url}}]
    reply = _post(_images_url(), body)
    items = reply.get("data") or reply.get("images") or []
    first = items[0] if items else {}
    ref = (first.get("b64_json") or first.get("url") or (first.get("image_url") or {}).get("url") or "") \
        if isinstance(first, dict) else str(first or "")
    usage = reply.get("usage") or {}
    # OpenAI's own Image API says its tokens, not its cost: priced at the model's list prices (providers.cost).
    usd = float(usage["cost"]) if usage.get("cost") is not None else providers.cost(model(), {
        "prompt_tokens": usage.get("input_tokens"), "completion_tokens": usage.get("output_tokens")}) if usage else 0.0
    if not ref:
        raise RuntimeError(f"{model()} returned no image from the Image API: {json.dumps(reply)[:200]}")
    return _image_bytes(ref), usd


def _ask_chat(prompt: str, outputs=("image", "text"), reference: bytes | None = None) -> tuple[bytes, float]:
    """Chat completions with image output: ("image", "text") for models that also write (Gemini's image models),
    ("image",) for image-only models. `reference`: a picture made before, sent with the words, for the model to
    draw the same person or thing again."""
    content: object = prompt
    if reference:
        url = "data:image/png;base64," + base64.b64encode(reference).decode()
        content = [{"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": prompt}]
    reply = _post(_chat_url(), {"model": model(), "modalities": list(outputs), "usage": {"include": True},
                                "messages": [{"role": "user", "content": content}]})
    message = ((reply.get("choices") or [{}])[0]).get("message") or {}
    data_url = next((((i.get("image_url") or {}).get("url")) for i in message.get("images") or []
                     if ((i.get("image_url") or {}).get("url") or "")), None)
    usd = float((reply.get("usage") or {}).get("cost") or 0.0)
    if not data_url:
        said = str(message.get("content") or "")[:200]
        raise RuntimeError(f"{model()} returned no image (is it an image model? On OpenRouter, an image model "
                           f"lists \"image\" as an output)" + (f"; it said: {said}" if said else ""))
    return _image_bytes(data_url), usd


def _ask_route(route: str, prompt: str, reference: bytes | None = None) -> tuple[bytes, float]:
    if route == "images":
        return _ask_images(prompt, reference)  # the reference goes in input_references
    return _ask_chat(prompt, ("image",) if route == "chat-image" else ("image", "text"), reference)


def _ask(prompt: str, reference: bytes | None = None) -> tuple[bytes, float]:
    """The image the model makes for a prompt, and what it cost. The model is asked the way it answered before in
    this run; else each way in turn (ROUTES) while OpenRouter says it is not served that way ("No endpoints found
    that support the requested output modalities", "use the /api/v1/images endpoint"), and the way that works is
    remembered. PANIM_IMAGE_API = chat, chat-image or images asks one way only."""
    forced = os.environ.get("PANIM_IMAGE_API", "").strip().lower()
    if forced in ROUTES:
        return _ask_route(forced, prompt, reference)
    import providers

    if providers.direct(model()):
        return _ask_route("images", prompt, reference)          # OpenAI makes pictures only by image generation
    known = _ROUTE.get(model())
    order = [known] + [r for r in ROUTES if r != known] if known else list(ROUTES)
    last: RuntimeError | None = None
    for route in order:
        try:
            got = _ask_route(route, prompt, reference)
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
    the figures' model, else the script's)."""
    return (os.environ.get("PANIM_LABEL_MODEL") or os.environ.get("OPENROUTER_FIGURE_MODEL")
            or os.environ.get("OPENROUTER_SVG_MODEL")
            or os.environ.get("OPENROUTER_MODEL") or "google/gemini-2.5-flash")


def _spread(labels: list[str]) -> list[list]:
    """Where labels go when nothing can look at the picture (offline, PANIM_IMAGE_FAKE): spaced down its middle."""
    n = max(len(labels), 1)
    return [[label, 0.35 if k % 2 == 0 else 0.65, (k + 0.5) / n] for k, label in enumerate(labels)]


def locate(png_path: str, labels) -> list[list] | None:
    """Where each labelled part is in a picture: [[label, x, y], ...], x and y from 0 to 1 across and down the
    picture (the cutout as the board shows it). A model that reads images is shown the picture
    and asked; the answer is kept beside it. Parts it cannot see are left out; None when it cannot be asked."""
    labels = [str(x).strip()[:40] for x in labels or [] if str(x).strip()][:8]
    path = Path(str(png_path))
    if not labels or not path.is_file():
        return None
    if _COLLECT is not None:
        hit = re.match(r"collect-(\d+)$", path.stem)
        if hit and int(hit.group(1)) < len(_COLLECT):
            _COLLECT[int(hit.group(1))]["labels"].append(labels)
        return _spread(labels)
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


# ---------------- reuse: one picture per thing ----------------
# Words that say how a picture is drawn, not what it shows: two requests that differ only in these are the same
# picture.
_HOW = re.compile(r"\b(?:an?|the|of|in|on|with|and|to|for|at|by|its|his|her|their|from|as|is|are|"
                  r"illustrat\w*|cut-?outs?|pictures?|images?|drawings?|drawn|style|styled|simple|clean|detailed|"
                  r"historically|grounded|accurate|realistic|colou?rful|educational|no|without|background|words|"
                  r"text|labels?|border|centred|centered|full|figure|whole|shown|showing|view|portrait)\b", re.I)


def _words(what: str) -> set[str]:
    """What a request shows, as its content words (lower case, no drawing words)."""
    plain = _HOW.sub(" ", re.sub(r"[^\w\s-]", " ", what.lower()))
    return {w.strip("-") for w in plain.split() if len(w.strip("-")) > 2}


def _names(what: str) -> set[str]:
    """The proper names in a request (a person, a place): its capitalised words, but for an opening article."""
    tokens = re.findall(r"[A-Za-z][\w'-]*", what)
    return {t.lower() for k, t in enumerate(tokens)
            if t[0].isupper() and not (k == 0 and t.lower() in ("a", "an", "the", "one", "two", "three"))}


def _same_thing(asked: str, made: str) -> float:
    """How surely a picture made for `made` shows what `asked` wants (0: not at all): the same words; all the
    asked words in the made picture's; the same named person (or place) with nothing more asked of the picture
    (two or more names shared: one other word allowed); or nearly all words shared."""
    a, m = _words(asked), _words(made)
    if not a or not m:
        return 0.0
    if a == m:
        return 1.0
    if len(a) >= 2 and a <= m:
        return 0.9
    shared = _names(asked) & _names(made)
    if shared and (_names(asked) <= _names(made) or _names(made) <= _names(asked)):
        extra = a - m
        if not extra or (len(shared) >= 2 and len(extra) <= 1):
            return 0.85
    overlap = len(a & m) / len(a | m)
    return overlap if overlap >= 0.7 else 0.0


def _made_pictures() -> list[dict]:
    """Every picture made before, with what it shows: the notes kept beside each (gen-<key>.json)."""
    out = []
    for meta in CACHE.glob("gen-*.json"):
        if ".labels-" in meta.name:
            continue
        try:
            row = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        png = meta.with_suffix(".png")
        if png.exists() and row.get("what"):
            out.append({**row, "png": png})
    return out


def _reusable(what: str, style: str | None, realistic: bool, parts, scene: bool = False) -> Path | None:
    """A picture already made of the same thing, in the same style by the same model, showing every part this one
    must label: the best match, or None. So a person, a building or an animal is one picture all through a lecture
    (and the lectures after it), however the script words it each time."""
    wanted = {str(p).strip().lower() for p in parts or [] if str(p).strip()}
    best = None
    for row in _made_pictures():
        if row.get("model") != model() or (row.get("style") or None) != (style or None) \
                or bool(row.get("realistic")) != bool(realistic) or bool(row.get("scene")) != bool(scene):
            continue
        if not wanted <= {str(p).strip().lower() for p in row.get("parts") or []}:
            continue
        score = _same_thing(what, str(row["what"]))
        if score and (best is None or score > best[0]):
            best = (score, row["png"])
    return best[1] if best else None


def reference_for(what: str, style: str | None, realistic: bool) -> dict | None:
    """A picture made before of the same named person (or place, or thing) as `what`, in the same style by the same
    model: the one a new picture of them is drawn to match (Akbar's portrait, then Akbar on horseback), so a person
    looks the same in every picture of a lecture. A cutout first (it shows them whole), the earliest made."""
    names = _names(what)
    if not names or os.environ.get("PANIM_IMAGE_REFERENCE") == "0":
        return None
    found = [row for row in _made_pictures()
             if row.get("model") == model() and (row.get("style") or None) == (style or None)
             and bool(row.get("realistic")) == bool(realistic) and names & _names(str(row["what"]))]
    if not found:
        return None
    found.sort(key=lambda row: (bool(row.get("scene")), row["png"].stat().st_mtime))
    return found[0]


def generate(what: str, style: str | None = None, realistic: bool = False, parts=None,
             context: str | None = None, scene: bool = False, match: bool = True, kind: str | None = None) -> dict | None:
    """A picture of `what` (see _generate), by the illustration model, or by the diagram model when it names parts
    to label (or kind="diagram"): a labelled picture's parts must be there and right."""
    kind = kind or ("diagram" if any(str(p).strip() for p in parts or []) else "illustration")
    if _COLLECT is not None:
        return _collected(dict(what=what, style=style, realistic=realistic, parts=parts, context=context,
                               scene=scene, match=match, kind=kind))
    with using(kind), about(what):
        return _generate(what, style, realistic, parts, context, scene, match)


# ---------------- making a compile's pictures at once ----------------
# The compiler asks for its pictures one by one as it writes the code: each a call of 10-40 s, one after another.
# First the script is run through once with the pictures only noted down (collect), then they are made several at
# once (prefetch), and the real pass finds every one made. PANIM_IMAGE_PARALLEL (6) at once.
_COLLECT: list[dict] | None = None
_COLLECT_DIR: Path | None = None


def _collected(request: dict) -> dict | None:
    """In the noting-down pass: the request kept, and a stand-in row so the compile goes on as if it were made."""
    what = re.sub(r"\s+", " ", str(request.get("what") or "")).strip()
    if not what:
        return None
    import mapguard

    if mapguard.is_map(what):
        return None
    index = len(_COLLECT)
    _COLLECT.append({**request, "labels": []})
    png = _COLLECT_DIR / f"collect-{index}.png"
    if not png.exists():
        png.write_bytes(_stand_in(what))
    return {"id": f"gen:collect-{index}", "title": what[:200], "description": what[:500], "source": "generated",
            "license": "generated", "credit": "", "model": model(), "png": str(png), "file": str(png),
            "path": str(png)}


@contextmanager
def collecting():
    """Inside, generate() only notes what is asked (and locate() which labels), returning stand-ins; the requests
    are yielded as a list, for prefetch()."""
    import tempfile

    global _COLLECT, _COLLECT_DIR
    requests: list[dict] = []
    with tempfile.TemporaryDirectory() as folder:
        _COLLECT, _COLLECT_DIR = requests, Path(folder)
        try:
            yield requests
        finally:
            _COLLECT, _COLLECT_DIR = None, None


def parallel() -> int:
    try:
        return max(1, min(12, int(os.environ.get("PANIM_IMAGE_PARALLEL", "6"))))
    except ValueError:
        return 6


# What the last prefetch did: pictures asked for at once, how many came back made and how many failed (with the
# first reason), how long it took, and the slowest one (seconds).
PREFETCHED: dict = {}


def prefetch(requests: list[dict]) -> None:
    """The pictures noted down (collecting), made several at once, each then its labels found, so the compile's
    real pass finds them all made. A picture of a person or thing already in an earlier one waits only for that
    first picture (it is drawn to match it: reference_for); every other starts straight away."""
    if not requests or not enabled():
        return
    from concurrent.futures import ThreadPoolExecutor

    seen, todo = set(), []
    for request in requests:
        key = (str(request["what"]).strip().lower(), request.get("style"), bool(request.get("realistic")),
               tuple(request.get("parts") or []), bool(request.get("scene")), request.get("kind"))
        if key not in seen:
            seen.add(key)
            todo.append(request)
    began = time.time()
    slowest = [0.0]
    made = [0]
    counting = threading.Lock()

    def make(request) -> None:
        start = time.time()
        try:
            row = generate(**{k: v for k, v in request.items() if k != "labels"})
            if row and row.get("png"):
                with counting:
                    made[0] += 1
                for labels in request.get("labels") or []:
                    locate(row["png"], labels)
        except Exception:  # noqa: BLE001 -- the real pass asks again and says why
            pass
        slowest[0] = max(slowest[0], time.time() - start)

    asked, failed = len(ASKED), len(FAILED)
    firsts: dict[str, object] = {}                  # a name -> the future of its first picture
    with ThreadPoolExecutor(max_workers=parallel()) as pool:
        futures = []
        for request in todo:
            names = _names(str(request["what"]))
            before = [firsts[n] for n in names if n in firsts]

            def run(request=request, before=before):
                for future in before:
                    future.result()
                make(request)

            future = pool.submit(run) if before else pool.submit(make, request)
            for n in names:
                firsts.setdefault(n, future)
            futures.append(future)
        for future in futures:
            future.result()
    errors = [str(f.get("error") or "") for f in FAILED[failed:]]
    PREFETCHED.update(pictures=len(todo), made=made[0], failed=len(todo) - made[0],
                      error=next((e for e in errors if e), None),
                      seconds=round(time.time() - began, 1), slowest=round(slowest[0], 1))
    # The real pass asks for each again (found made now) and says what failed: counted there, once.
    del ASKED[asked:]
    del FAILED[failed:]


def _generate(what: str, style: str | None = None, realistic: bool = False, parts=None,
              context: str | None = None, scene: bool = False, match: bool = True) -> dict | None:
    """A cutout picture of `what`, made by the image model (or found made already): its row, with `file` (a
    transparent PNG), `title`, `description`, `credit`, `source` "generated", `prompt`, `model`, and `usd` (what
    it cost now) or `paid` (what it cost when it was made). None when it cannot be made."""
    what = re.sub(r"\s+", " ", str(what or "")).strip()
    if not what:
        return None
    import mapguard

    if mapguard.is_map(what):
        return None              # a map is drawn on the map (Cartopy), never imagined by a model
    prompt = prompt_for(what, style, realistic, parts, context, scene)
    # Kept by what it shows (not by the lines said over it, which the prompt also carries): the same thing asked
    # for again, in the same words or others, is the picture already made.
    named = sorted({str(p).strip().lower() for p in parts or [] if str(p).strip()})
    key = hashlib.sha256(f"{model()}|{style or ''}|{bool(realistic)}|{' '.join(sorted(_words(what)))}|"
                         f"{','.join(named)}{'|scene' if scene else ''}".encode()).hexdigest()[:20]
    target = CACHE / f"gen-{key}.png"
    if not target.exists():
        same = _reusable(what, style, realistic, parts, scene)
        if same is not None:
            target = same
            key = same.stem[len("gen-"):]
    row = {"id": f"gen:{key}", "title": what[:200], "description": what[:500], "source": "generated",
           "license": "generated", "artist": model(), "credit": f"made with {model()}", "prompt": prompt,
           "model": model(), "png": str(target)}
    ASKED.append({"what": what, "cached": target.exists()})
    if target.exists():
        row.update(file=str(target), path=str(target))
        try:
            paid = float(json.loads(target.with_suffix(".json").read_text()).get("usd") or 0.0)
        except (OSError, ValueError):
            paid = None
        return {**row, "paid": paid}
    if not enabled():
        _failed(what, "the image model is off (PANIM_IMAGES=0)" if os.environ.get("PANIM_IMAGES") == "0"
                else "no OPENROUTER_API_KEY in the compiler's environment")
        return None
    if model() in REFUSED and not fallbacks():
        _failed(what, REFUSED[model()])          # refused already this run: not asked again
        return None
    like = reference_for(what, style, realistic) if match and not target.exists() and model() not in NO_REFERENCE \
        else None
    plain = prompt
    reference = None
    if like is not None:
        try:
            reference = like["png"].read_bytes()
            prompt = prompt_for(what, style, realistic, parts, context, scene, like=str(like["what"]))
            row["prompt"] = prompt
            row["like"] = str(like["what"])
        except OSError:
            reference = None
    used = model()

    def ask_one() -> tuple[bytes, float]:
        nonlocal reference, prompt
        if model() in REFUSED:
            raise RuntimeError(REFUSED[model()])
        try:
            return (_stand_in(what), 0.0) if _fake() else _ask(prompt, reference if model() not in NO_REFERENCE
                                                              else None)
        except RuntimeError as error:
            if reference is None or not IMAGE_INPUT_REFUSED.search(str(error)):
                raise
            # A model that takes words only: asked again without the reference picture (and never sent one again).
            NO_REFERENCE.add(model())
            reference, prompt = None, plain
            row["prompt"] = prompt
            row.pop("like", None)
            return _ask(prompt, None)

    whys: list[str] = []
    data = None
    for name in [model(), *fallbacks()]:
        with _pinned(name):
            try:
                data, usd = ask_one()
                used = name
                break
            except Exception as error:  # noqa: BLE001 -- offline, refused, filtered: the next model, else left out
                why = str(error) or type(error).__name__
                if _refusal(why):
                    REFUSED[name] = why
                whys.append(why if not whys else f"{name}: {why}")
    if data is None:
        _failed(what, "; then ".join(whys)[:600])
        return None
    if used != row["model"]:
        row.update(model=used, artist=used, credit=f"made with {used} (fallback)")
    try:
        # A scene keeps its setting; anything else is cut out of its plain background.
        data = data if scene else cutout(data)
    except Exception:  # noqa: BLE001 -- an image the cutout cannot read is kept as the model made it
        pass
    CACHE.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.with_suffix(".json").write_text(json.dumps({"what": what, "prompt": prompt, "model": used, "style": style,
                                                       "realistic": realistic, "parts": named, "usd": usd,
                                                       "scene": bool(scene), "like": row.get("like")}))
    MADE.append({"path": str(target), "png": str(target), "what": what, "prompt": prompt, "model": used, "usd": usd,
                 "made": True})
    return {**row, "file": str(target), "path": str(target), "usd": usd, "made": True}


# ---------------- the book's diagrams, redrawn by the diagram model ----------------
DIAGRAM_VERSION = 3

# How each art style (artstyle.py) is told to the diagram model, so a redrawn figure looks like the rest of the
# lecture's pictures.
ART_LOOKS = {
    "clean": "a polished flat-design vector illustration: solid flat colour fills, crisp even outlines, no texture",
    "detailed": "a polished, richly detailed textbook illustration: shapes shaded with soft gradients, highlights "
                "and rim light, crisp dark outlines",
    "blueprint": "a precise technical line drawing: fine exact lines, faint translucent fills, light construction "
                 "marks",
    "chalk": "a neat chalk drawing: soft pastel chalk strokes with a slight hand-drawn wobble",
    "sketch": "a neat hand-drawn pencil-and-ink sketch: confident ink outlines, cross-hatched shading",
    "neon": "glowing neon line art: bright luminous lines with a soft glow, translucent filled shapes",
    "watercolour": "a watercolour illustration: layered translucent washes, soft edges, thin ink outlines",
}


def _template_look(style: str | None, art: str | None = None) -> dict:
    """The template's look for a redrawn figure: its board colour (drawn on, then cut away), its ink, its accent
    colours, its art style and that style's lettering."""
    look = {"bg": "#FFFFFF", "ink": "#111111", "accents": [], "art": "clean", "font": None}
    try:
        import artstyle
        import pocket_lecture as pl

        theme = pl.THEMES.get(style or "") or pl.THEMES["atlas"]
        pal = theme["pal"]
        look.update(bg=str(theme["bg"]), ink=str(pal.get("CREAM", "#111111")),
                    accents=[str(pal[k]) for k in ("SAND", "RIVER", "TEAL", "GREEN", "ROSE", "TERRA") if pal.get(k)])
        name = (art or "auto").strip().lower()
        name = "watercolour" if name == "watercolor" else name
        if name in ("", "auto", "default") or name not in artstyle.ART_STYLES:
            name = artstyle.TEMPLATE_ART.get(style or "", "clean")
        look.update(art=name, font=artstyle.ART_FONTS.get(name))
    except Exception:  # noqa: BLE001 -- no engine here: a white page and black ink
        pass
    return look


def _board_colours(style: str | None) -> tuple[str, str]:
    """(background, ink) of a lecture style's board, for a diagram drawn to sit on it."""
    look = _template_look(style)
    return look["bg"], look["ink"]


def redraw_prompt(caption: str, style: str | None, context: str | None = None, fix: str | None = None,
                  art: str | None = None, plain: bool = False, faithful: bool = False, how: str | None = None) -> str:
    """What the diagram model is told when it redraws a book's figure from the figure itself: the same diagram, its
    parts and labels kept, beautifully drawn in the template's look (its art style, ink and colours), on the board's
    flat colour, which is then cut away: the figure stands on the board with no background of its own.

    Worded as a new educational illustration made from a reference sketch: words such as "exact copy", "textbook",
    "watermark" or "logo" make image models' content filters block it as copying. `plain`: the shortest form, asked
    when the filter blocked the full one (no lesson text, no fix). `faithful`: the figure must look as it does in
    the book (the figure model said so): redrawn close to its own drawing, colours and detail, only cleaned, not
    restyled; it keeps its own background when it has one. `how`: the figure model's note on this figure."""
    look = _template_look(style, art)
    note = f" NOTE ON THIS FIGURE: {how.strip()[:300]}" if how and how.strip() else ""
    if faithful:
        what = (caption.strip() or "a figure")[:160]
        if plain:
            return (f"An educational figure for a school lesson: {what}. Make a clean, sharp version of the attached "
                    "reference image that looks just like it: the same drawing, colours, parts and labels. Only the "
                    "figure itself.")
        return (
            "Make a clean, sharp version of the attached REFERENCE IMAGE for a video lesson that LOOKS JUST LIKE IT: "
            f"what it shows is taught by how it looks. What it shows: {what}."
            + (f" WHAT IT IS FOR: {context.strip()[:500]}" if context and context.strip() else "") + note
            + " KEEP ITS OWN LOOK: the same drawing style, colours, shading, textures, proportions and fine detail, "
            "the same layout, every part in its place, every arrow and line, every number and unit, and EVERY LABEL "
            "with the same words and spelling beside the same part. Do NOT restyle it, simplify it, recolour it or "
            "add anything. If it is a photograph, keep it photographic and true. ONLY CLEAN IT: sharp and clear, "
            "labels crisp and readable on a phone, without blur, grain, stains, yellowed paper or uneven light, and "
            "show only the figure itself: leave out everything around it that is not part of it (any page, border, "
            "caption, figure number, title, page number, stamp, mark or stray text)."
            f" If the figure has no background of its own, it stands on a single plain, flat colour {look['bg']} "
            "filling the rest of the image edge to edge, no frame, card or shadow; if it has one (a photograph, a "
            "scene, a microscope field), keep it. Fill the frame with the figure."
            + (f" YOUR LAST TRY WAS WRONG: {fix.strip()[:600]} Fix exactly that, and keep everything else the same."
               if fix and fix.strip() else "")
        )
    drawn = ART_LOOKS.get(look["art"], ART_LOOKS["clean"])
    what = (caption.strip() or "a diagram")[:160]
    if plain:
        return (f"An educational diagram for a school science lesson: {what}. Make a new, clean illustration of the "
                f"diagram in the attached reference image, drawn as {drawn}: the same parts in the same places, the "
                "same arrows and the same labels with the same words. Only the diagram, on a plain flat background "
                f"of colour {look['bg']}, lines and words in {look['ink']}.")
    accents = ", ".join(look["accents"][:5])
    lettering = (f"lettered in a style like the {look['font']} font, large and clear" if look["font"]
                 else "in a large, plain, clear font")
    return (
        "Make a new, clean EDUCATIONAL ILLUSTRATION for a video lesson from the attached REFERENCE IMAGE (a sketch of "
        f"a diagram), drawn BEAUTIFULLY as {drawn}: polished, professional, crisp and well made. What it shows: "
        f"{what}."
        + (f" WHAT IT IS FOR: {context.strip()[:500]}" if context and context.strip() else "") + note
        + " KEEP THE DIAGRAM FAITHFUL to the reference: the same layout, the same parts in the same places and "
        "proportions, every arrow, line, connection and direction, every number and unit, and EVERY LABEL with the "
        "same words and spelling, beside the same part (never translate, reword, add, drop or move a label). If the "
        "reference is a photograph, make a faithful illustration of what it shows, from the same view. Nothing "
        "added, nothing left out, nothing rearranged."
        " SHOW ONLY THE DIAGRAM ITSELF: leave out everything around it that is not part of the diagram (any page, "
        "border, caption, figure number, title, page number, stamp, mark or stray text) and any blur, stains or "
        f"grain. Lines, shapes and colours redrawn in that style, outlines and words in {look['ink']}, colours from "
        f"this palette where the diagram has colour ({accents or 'clear, rich colours'}), labels {lettering}, "
        "readable on a phone."
        f" NO BACKGROUND: the diagram stands alone on a single plain, flat, solid colour {look['bg']} that fills the "
        "whole rest of the image edge to edge; no paper, panel, card, box, frame, border, vignette, gradient, "
        "texture, drop shadow, floor or scenery behind or around it. The diagram's own parts keep their fills. Fill "
        "the frame with the diagram."
        + (f" YOUR LAST TRY WAS WRONG: {fix.strip()[:600]} Fix exactly that, and keep everything else the same."
           if fix and fix.strip() else "")
    )


def verify(source: bytes, made: bytes, caption: str) -> dict:
    """Whether a redrawn diagram is true to the book's: a model that reads images is shown both and lists the
    labels missing or changed, and whether the parts and arrows are the same. {"ok": True/False/None, "missing",
    "wrong", "notes"}; ok None when nothing could check (offline, no key)."""
    if _fake():
        return {"ok": True, "missing": [], "wrong": [], "notes": "stand-in"}
    if not os.environ.get("OPENROUTER_API_KEY"):
        return {"ok": None, "missing": [], "wrong": [], "notes": "not checked: no OPENROUTER_API_KEY"}

    def url(data: bytes) -> str:
        return "data:image/png;base64," + base64.b64encode(data).decode()

    ask = ("Image A is a figure from a school textbook" + (f" ({caption.strip()[:160]})" if caption.strip() else "")
           + ". Image B is a redrawing of it for a lesson. List every text label in A (leave out a figure number, "
           "caption, title or page number). For each, is it in B with the same words and spelling, beside the same "
           "part? Are A's parts, arrows and layout kept in B, with nothing wrong added? Reply with JSON only: "
           '{"labels": [...every label in A...], "missing": [...labels of A not in B...], "wrong": [...labels of A '
           'misspelled, changed or misplaced in B...], "structure_ok": true or false, "notes": "what else is wrong, '
           'in one sentence"}')
    try:
        reply = _post(_chat_url(), {"model": label_model(), "temperature": 0, "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Image A:"}, {"type": "image_url", "image_url": {"url": url(source)}},
            {"type": "text", "text": "Image B:"}, {"type": "image_url", "image_url": {"url": url(made)}},
            {"type": "text", "text": ask}]}]}, proxied=False, who=f"the diagram checker {label_model()}")
        text = str((((reply.get("choices") or [{}])[0]).get("message") or {}).get("content") or "")
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    except Exception as error:  # noqa: BLE001 -- unchecked, and said so
        return {"ok": None, "missing": [], "wrong": [], "notes": f"not checked: {str(error)[:200]}"}
    missing = [str(x) for x in data.get("missing") or []][:20]
    wrong = [str(x) for x in data.get("wrong") or []][:20]
    ok = not missing and not wrong and data.get("structure_ok") is not False
    return {"ok": ok, "missing": missing, "wrong": wrong, "labels": [str(x) for x in data.get("labels") or []][:40],
            "notes": str(data.get("notes") or "")[:300]}


def _as_png(data: bytes) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((1600, 1600))
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def diagram_tries() -> int:
    try:
        return max(1, int(os.environ.get("PANIM_DIAGRAM_TRIES", "4")))
    except ValueError:
        return 4


def _redraw_tries(reference: bytes, source: Path, caption: str, style, context, art, faithful: bool = False,
                  how: str | None = None) -> dict:
    """The tries of one model (model()) at a redraw: drawn, checked against the book's figure, drawn again with what
    was wrong, up to PANIM_DIAGRAM_TRIES; the closest kept. When its content filter blocks the request, asked once
    more in the plainest words. {"png", "check", "prompt", "model", "usd"} or {"error", "usd"}."""
    if model() in REFUSED:
        return {"error": REFUSED[model()]}
    if model() in NO_REFERENCE:
        return {"error": f"the diagram model {model()} cannot be shown the book's figure (it takes words only); "
                         "pick one that takes images (PANIM_DIAGRAM_MODEL)"}
    usd, fix, best, plain, attempt, prompt = 0.0, None, None, False, 0, ""
    while attempt < diagram_tries():
        prompt = redraw_prompt(caption, style, context, fix, art, plain=plain, faithful=faithful, how=how)
        try:
            data, cost = (_stand_in(caption or source.name), 0.0) if _fake() else _ask(prompt, reference)
        except RuntimeError as error:
            why = str(error)
            if IMAGE_INPUT_REFUSED.search(why):
                NO_REFERENCE.add(model())
                return {"error": f"the diagram model {model()} cannot be shown the book's figure (it takes words "
                                 "only); pick one that takes images (PANIM_DIAGRAM_MODEL)", "usd": usd}
            if FILTERED.search(why) and not plain:
                plain = True                 # blocked by its content filter: once more, in the plainest words
                continue
            if best is not None:
                break                        # a later try failed: the closest so far is kept
            if _refusal(why):
                REFUSED[model()] = why
            return {"error": why[:300], "usd": usd}
        attempt += 1
        usd += cost
        png = _as_png(data)
        check = verify(reference, png, caption)
        faults = len(check.get("missing") or []) + len(check.get("wrong") or []) + (check.get("ok") is False)
        if best is None or faults < best[0]:
            best = (faults, png, check, prompt)
        if check.get("ok") is not False:
            break
        fix = None if plain else "; ".join(x for x in [
            f"labels missing: {', '.join(check['missing'])}" if check.get("missing") else "",
            f"labels wrong or misplaced: {', '.join(check['wrong'])}" if check.get("wrong") else "",
            check.get("notes") or ""] if x)
    _, png, check, prompt = best
    return {"png": png, "check": check, "prompt": prompt, "model": model(), "usd": usd}


def redraw(source_path: str, caption: str = "", style: str | None = None, context: str | None = None,
           art: str | None = None, faithful: bool = False, how: str | None = None) -> dict:
    """A book's figure redrawn by the diagram model in the lecture's style, from the figure itself (sent as the
    reference), every label kept, then checked against it (verify) and redrawn with what was wrong, up to
    PANIM_DIAGRAM_TRIES (4) times. The book's own picture is never shown: when no try passes the check, the
    closest one (the fewest labels missing or wrong) is kept, and its check says what is still off. Kept beside the
    other pictures, by the figure and the style. Returns a row with `file` (the PNG), `png`, `ok`, `check`, `usd`;
    or {"error": why} only when the model made nothing (no key, refused, offline).

    `faithful`: the figure must look as in the book (the figure model decided so): redrawn close to its own look,
    only cleaned, not restyled. `how`: the figure model's note on how to redraw it."""
    source = Path(str(source_path))
    if not source.is_file():
        return {"error": f"no figure file {source}"}
    with using("diagram"), about(f"book figure {caption or source.name}"):
        raw = source.read_bytes()
        try:
            reference = _as_png(raw)
        except Exception:  # noqa: BLE001
            reference = raw
        way = "faithful" if faithful else f"{style or ''}|{_template_look(style, art)['art']}"
        key = hashlib.sha256(f"{model()}|{way}|{DIAGRAM_VERSION}|".encode() + hashlib.sha256(raw).digest()
                             ).hexdigest()[:20]
        target = CACHE / f"gen-diagram-{key}.png"
        meta = target.with_suffix(".json")
        if target.exists() and meta.exists():
            row = json.loads(meta.read_text())
            return {**row, "file": str(target), "png": str(target), "usd": 0.0, "paid": row.get("usd")}
        if not enabled():
            return {"error": "the image model is off (no OPENROUTER_API_KEY, or PANIM_IMAGES=0)"}
        # The diagram model, then each fallback (PANIM_DIAGRAM_FALLBACK_MODELS) while one makes nothing.
        usd, whys, got = 0.0, [], None
        for name in [model(), *fallbacks()]:
            with _pinned(name):
                got = _redraw_tries(reference, source, caption, style, context, art, faithful, how)
            usd += got.get("usd") or 0.0
            if "error" not in got:
                break
            whys.append(got["error"] if not whys else f"{name}: {got['error']}")
            got = None
        if got is None:
            return {"error": "; then ".join(whys)[:600], "usd": usd}
        used, png, check, prompt = got["model"], got["png"], got["check"], got["prompt"]
        # The closest try: the book's picture is never shown instead.
        CACHE.mkdir(parents=True, exist_ok=True)
        # No background: the flat colour around the figure is cut away (checked before, on the whole); a figure
        # with a background of its own (a photograph, a scene) keeps it.
        try:
            if flat_background(png):
                png = cutout(png)
        except Exception:  # noqa: BLE001 -- kept as drawn
            pass
        target.write_bytes(png)
        row = {"what": f"diagram: {caption}"[:300], "title": caption[:200], "model": used, "style": style,
               "source": str(source), "check": check, "ok": check.get("ok"), "usd": usd, "diagram": True,
               "faithful": bool(faithful),
               "credit": f"redrawn with {used} from the book's figure"
                         + (" (fallback)" if used != model() else "")}
        meta.write_text(json.dumps(row, ensure_ascii=False))
        MADE.append({"path": str(target), "png": str(target), "what": row["what"], "prompt": prompt, "model": used,
                     "usd": usd, "made": True})
        return {**row, "file": str(target), "png": str(target)}


def report() -> dict:
    """What this process asked of the image model: how many pictures, how many made now, found made, failed (and
    why), and which model, for the lecture's log (compile_lecture --json "images")."""
    out = {"model": configured(), "diagram_model": diagram_model(), "proxy": proxy_shown(), "asked": len(ASKED), "cached": sum(1 for a in ASKED if a["cached"]),
           "made": sum(1 for m in MADE if m.get("made")), "failed": FAILED}
    return out


def check(what: str = "a red apple with one green leaf") -> dict:
    """A real call to the image model, never from the cache: whether it works, which model, how long, what it
    cost, and the picture (PNG, as the board and the phone show it). The app's "test"
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
    out.update(ok=True, png="data:image/png;base64," + base64.b64encode(png).decode())
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--check" in args:
        print(json.dumps(check(" ".join(a for a in args if a != "--check") or "a red apple with one green leaf")))
        sys.exit(0)
    if "--redraw" in args:
        # genimage.py --redraw FIGURE.png [--style S] [--art A] [--faithful] [--how H] [--caption C] [--context X]: the book's figure redrawn.
        def value(flag):
            return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None
        print(json.dumps(redraw(value("--redraw"), value("--caption") or "", value("--style"), value("--context"),
                                value("--art"), "--faithful" in args, value("--how")),
                         ensure_ascii=False))
        sys.exit(0)
    realistic = "--realistic" in args
    args = [a for a in args if a != "--realistic"]
    print(json.dumps(generate(" ".join(args), realistic=realistic), ensure_ascii=False))
