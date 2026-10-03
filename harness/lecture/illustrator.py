"""Illustrations drawn for a lecture: one vector drawing of a thing, in the board's whiteboard style.

A diagram's node, a definition or a comparison column shows a thing (a cow, a volcano, a pulley). Emoji packs draw
the same few hundred things, as symbols; a lecture needs illustrations of whatever it teaches. This asks an image model
for an SVG illustration of the thing, in one fixed style (thick dark outlines, flat bright fills, no text, plain
background), and keeps it: the next lecture that needs a cow uses the same drawing, and pays nothing.

The model is Recraft V4.1 Vector through OpenRouter (the key the lecture writer already uses), which draws real SVG
paths rather than tracing a picture, so Manim draws each outline and then fills it, as on a board.

Settings (environment, or harness/app/.env.local):
  OPENROUTER_API_KEY   the key (shared with the lecture writer)
  PANIM_DRAW_MODEL     the model (recraft/recraft-v4.1-vector; recraft/recraft-v4.1-pro-vector is finer and dearer)
  PANIM_DRAWINGS       "generate" (default when a key is set): draw what the libraries lack; "library": never draw
  PANIM_DRAW_PRICE     US dollars an image, for the cost shown (default: the model's list price)
  OPENROUTER_URL       the endpoint (a test points it at a stand-in)

    .venv/bin/python harness/lecture/illustrator.py "a cow grazing" cow.svg
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from chirp import _env

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "data" / "drawings"
MODEL = "recraft/recraft-v4.1-vector"
URL = "https://openrouter.ai/api/v1/chat/completions"
PRICES = {"recraft/recraft-v4.1-vector": 0.08, "recraft/recraft-v4.1-pro-vector": 0.30,
          "recraft/recraft-v4-vector": 0.08, "recraft/recraft-v4-pro-vector": 0.30}
# One style for every drawing, so a lecture's drawings belong together: the reference's whiteboard illustration.
STYLE = ("A single educational illustration for a school lecture, in a clean whiteboard explainer style: thick dark "
         "outlines of even weight, flat bright fills, simple friendly shapes, the whole object or scene centred, no "
         "text, no letters, no numbers, no labels, no shadows, no gradients, no background, no frame. Subject: ")
TRIES = 4
_lock = threading.Lock()


def model() -> str:
    return _env("PANIM_DRAW_MODEL") or MODEL


def enabled() -> bool:
    """A drawing can be made here: a key, and drawings not switched off."""
    return bool(_env("OPENROUTER_API_KEY")) and (_env("PANIM_DRAWINGS") or "generate") != "library"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "drawing"


def path_for(subject: str) -> Path:
    """Where the drawing of a subject is kept (named by the subject, the model and the style)."""
    key = hashlib.md5(f"{model()}|{STYLE}|{subject.strip().lower()}".encode()).hexdigest()[:10]
    return FOLDER / f"{_slug(subject)}-{key}.svg"


def cost_of(subject: str) -> float | None:
    """What a kept drawing cost when it was made, or None when it is not made."""
    meta = path_for(subject).with_suffix(".json")
    try:
        return float(json.loads(meta.read_text()).get("usd", 0.0))
    except (OSError, ValueError):
        return None


def _svg_of(reply: dict) -> bytes:
    """The SVG in an OpenRouter reply: message.images[].image_url.url (a data URL), or SVG in the message text."""
    message = ((reply.get("choices") or [{}])[0].get("message") or {})
    for image in message.get("images") or []:
        url = str((image.get("image_url") or {}).get("url") or image.get("url") or "")
        if url.startswith("data:"):
            head, _, data = url.partition(",")
            raw = base64.b64decode(data) if ";base64" in head else urllib.parse.unquote(data).encode()
            if b"<svg" in raw[:2000]:
                return raw
            raise RuntimeError(f"the drawing came back as {head[5:].split(';')[0]}, not SVG: use a vector model")
        if url.startswith("http"):
            with urllib.request.urlopen(url, timeout=60) as response:
                raw = response.read()
            if b"<svg" in raw[:2000]:
                return raw
    text = message.get("content") or ""
    found = re.search(r"<svg\b.*?</svg>", text if isinstance(text, str) else "", re.S)
    if found:
        return found.group(0).encode()
    raise RuntimeError("the model returned no drawing")


def draw(subject: str) -> Path:
    """The SVG drawing of a subject ("a cow", "a pulley lifting a box"), made once and kept. Raises RuntimeError."""
    out = path_for(subject)
    if out.exists() and out.stat().st_size > 100:
        return out
    key = _env("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("no OPENROUTER_API_KEY: drawings cannot be made")
    body = {"model": model(), "modalities": ["image"],
            "messages": [{"role": "user", "content": STYLE + subject.strip()}],
            "image_config": {"aspect_ratio": "1:1"}}
    last = ""
    for attempt in range(TRIES):
        request = urllib.request.Request(_env("OPENROUTER_URL") or URL, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                reply = json.loads(response.read())
            if reply.get("error"):
                raise RuntimeError(str(reply["error"].get("message") or reply["error"]))
            svg = _svg_of(reply)
            usage = reply.get("usage") or {}
            usd = float(usage.get("cost") or _env("PANIM_DRAW_PRICE") or PRICES.get(model(), 0.08))
            FOLDER.mkdir(parents=True, exist_ok=True)
            with _lock:
                out.write_bytes(svg)
                out.with_suffix(".json").write_text(json.dumps(
                    {"subject": subject, "model": model(), "usd": usd, "made": int(time.time())}))
            return out
        except urllib.error.HTTPError as error:
            last = error.read().decode("utf-8", "replace")[:300]
            if error.code in (429, 500, 502, 503, 504) and attempt < TRIES - 1:
                time.sleep(min(30, 2 ** attempt * 3))
                continue
            raise RuntimeError(f"{model()} {error.code}: {last}") from None
        except urllib.error.URLError as error:
            last = str(error.reason)
            if attempt < TRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"{model()} unreachable: {last}") from None
    raise RuntimeError(f"{model()} failed: {last}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    made = draw(sys.argv[1])
    Path(sys.argv[2]).write_bytes(made.read_bytes())
    print(f"wrote {sys.argv[2]} ({made.stat().st_size} bytes, ${cost_of(sys.argv[1]) or 0:.3f})")
