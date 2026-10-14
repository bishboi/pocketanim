"""Where a model's request goes: OpenRouter, or OpenAI's own API for an OpenAI model when there is a key for it.

Every AI step names its model the OpenRouter way ("openai/gpt-5.1", "google/gemini-2.5-flash"). A model named
openai/... is asked of OpenAI directly when OPENAI_API_KEY is set (PANIM_OPENAI_DIRECT=off keeps it on OpenRouter):
the prefix comes off, and the request is put in OpenAI's form -- OpenRouter's own fields out (usage, provider,
plugins, transforms), its reasoning setting as OpenAI's reasoning_effort, max_tokens as max_completion_tokens, no
temperature for a reasoning model, the usage asked for when streaming. OpenAI does not say what a request cost:
it is priced from its tokens -- cached input at its lower rate -- at the model's list prices, read from
OpenRouter's model list (openrouter.ai/api/v1/models, no key needed) and kept a day in .cache/model_prices.json
(shared with the web app, harness/app/lib/providers.ts). PANIM_OPENAI_PRICES ({"gpt-5.1": [in, out]} or
[in, out, cached in], US dollars per million tokens) sets a model's own; a model priced by neither counts as 0.

OPENAI_BASE_URL points at another OpenAI-compatible endpoint (a test's mock, Azure's).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from chirp import _env

OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions"
OPENAI_BASE = "https://api.openai.com/v1"
OPENROUTER_ONLY = ("usage", "provider", "plugins", "transforms", "models", "route")


def direct(model: str | None) -> bool:
    """Whether this model is asked of OpenAI itself."""
    return bool(model and str(model).startswith("openai/") and _env("OPENAI_API_KEY")
                and (_env("PANIM_OPENAI_DIRECT") or "on").strip().lower() not in ("off", "0", "no"))


def reasoning_model(model_id: str) -> bool:
    """OpenAI's reasoning models (o1..., gpt-5 and every gpt after it): they take reasoning_effort, refuse a
    temperature, and spend part of their output on thinking."""
    gpt = re.match(r"^gpt-(\d+)", model_id)
    return bool(re.match(r"^o\d", model_id)) or (gpt is not None and int(gpt.group(1)) >= 5)


# A reasoning model's output includes its thinking: a cap smaller than this leaves it nothing to answer with.
THINKING_ROOM = 4000


def openai_body(body: dict) -> dict:
    """An OpenRouter chat request in OpenAI's form."""
    out = {k: v for k, v in body.items() if k not in OPENROUTER_ONLY}
    model_id = str(out.get("model", "")).removeprefix("openai/")
    out["model"] = model_id
    reasoning = out.pop("reasoning", None)
    effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
    if reasoning_model(model_id):
        # Not with function tools: OpenAI's newer models refuse the two together on chat completions.
        if effort and not out.get("tools"):
            out["reasoning_effort"] = effort
        out.pop("temperature", None)
        out.pop("top_p", None)
    if "max_tokens" in out:
        cap = int(out.pop("max_tokens"))
        out["max_completion_tokens"] = max(cap, THINKING_ROOM) if reasoning_model(model_id) else cap
    if out.get("stream"):
        out["stream_options"] = {"include_usage": True}
    return out


def chat(body: dict, openrouter_url: str | None = None) -> tuple[str, dict, dict]:
    """(url, headers, body) for a chat completion with this body's model."""
    if direct(body.get("model")):
        base = (_env("OPENAI_BASE_URL") or OPENAI_BASE).rstrip("/")
        return (f"{base}/chat/completions", {"Authorization": f"Bearer {_env('OPENAI_API_KEY')}",
                                             "Content-Type": "application/json"}, openai_body(body))
    url = openrouter_url or _env("OPENROUTER_URL") or OPENROUTER_CHAT
    return url, {"Authorization": f"Bearer {_env('OPENROUTER_API_KEY') or ''}",
                 "Content-Type": "application/json"}, body


def images(body: dict) -> tuple[str, dict, dict]:
    """(url, headers, body) for OpenAI's image generation, from an Image API request ({model, prompt})."""
    base = (_env("OPENAI_BASE_URL") or OPENAI_BASE).rstrip("/")
    out = {"model": str(body.get("model", "")).removeprefix("openai/"), "prompt": body.get("prompt", ""), "n": 1}
    return (f"{base}/images/generations", {"Authorization": f"Bearer {_env('OPENAI_API_KEY')}",
                                           "Content-Type": "application/json"}, out)


PRICE_LIST = "https://openrouter.ai/api/v1/models"
PRICE_DAYS = 1
_listed: dict | None = None
_unpriced: set = set()


def _price_file() -> Path:
    return Path(_env("PANIM_PRICE_CACHE") or Path(__file__).resolve().parent / ".cache" / "model_prices.json")


def prices_from_list(data: dict) -> dict:
    """OpenAI's models' prices from OpenRouter's model list (per token there): {id: {"in", "out", "cachedIn"?}} in
    US dollars per million tokens."""
    out = {}
    for m in (data or {}).get("data") or []:
        mid, pricing = str(m.get("id") or ""), m.get("pricing") or {}
        if not mid.startswith("openai/"):
            continue
        try:
            price = {"in": float(pricing["prompt"]) * 1e6, "out": float(pricing["completion"]) * 1e6}
        except (KeyError, TypeError, ValueError):
            continue
        if pricing.get("input_cache_read") not in (None, ""):
            price["cachedIn"] = float(pricing["input_cache_read"]) * 1e6
        out[mid.removeprefix("openai/")] = price
    return out


def _price_list() -> dict:
    """The list prices, from the cache when it is under a day old, else fetched (once a process; on failure the
    last list kept, or none)."""
    global _listed
    if _listed is not None:
        return _listed
    try:
        kept = json.loads(_price_file().read_text())
    except (OSError, ValueError):
        kept = None
    _listed = (kept or {}).get("models") or {}
    if kept and time.time() * 1000 - float(kept.get("fetched") or 0) < PRICE_DAYS * 86_400_000:
        return _listed
    try:
        import urllib.request

        with urllib.request.urlopen(_env("PANIM_PRICE_LIST_URL") or PRICE_LIST, timeout=15) as reply:
            models = prices_from_list(json.loads(reply.read()))
        if models:
            _listed = models
            _price_file().parent.mkdir(parents=True, exist_ok=True)
            _price_file().write_text(json.dumps({"fetched": time.time() * 1000, "models": models}, indent=1))
    except Exception as error:  # noqa: BLE001 -- no list: the kept one, or $0 with a note
        print(f"[cost] OpenAI's prices could not be read ({error}); "
              + ("using the last list kept." if _listed else "OpenAI requests count as $0."), file=sys.stderr)
    return _listed


def price(model: str | None) -> dict | None:
    """A model's price (US dollars per million tokens): PANIM_OPENAI_PRICES's, else the list's; None for neither."""
    mid = str(model or "").removeprefix("openai/")
    try:
        own = json.loads(_env("PANIM_OPENAI_PRICES") or "{}").get(mid)
    except (ValueError, AttributeError):
        own = None
    if isinstance(own, (list, tuple)) and len(own) >= 2:
        return {"in": float(own[0]), "out": float(own[1]), **({"cachedIn": float(own[2])} if len(own) > 2 else {})}
    listed = _price_list()
    return listed.get(mid) or listed.get(re.sub(r"-\d{4}-\d{2}-\d{2}$", "", mid))


def cost(model: str | None, usage: dict | None) -> float:
    """What a reply cost: OpenRouter's own figure, else (an OpenAI reply) its tokens at the model's prices, cached
    input at the cached rate."""
    usage = usage or {}
    if usage.get("cost") is not None:
        return float(usage["cost"])
    rate = price(model)
    if not rate:
        if model and model not in _unpriced:
            _unpriced.add(model)
            print(f"[cost] no price for {model}: its requests count as $0 (PANIM_OPENAI_PRICES prices it).",
                  file=sys.stderr)
        return 0.0
    prompt = float(usage.get("prompt_tokens") or 0)
    cached = min(float((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0), prompt)
    return ((prompt - cached) * rate["in"] + cached * rate.get("cachedIn", rate["in"])
            + float(usage.get("completion_tokens") or 0) * rate["out"]) / 1e6


def auth_hint(model: str | None) -> str:
    """What to do when a provider refuses a request's key (401, 403)."""
    model = str(model or "")
    if direct(model):
        return "OpenAI refused the key: check OPENAI_API_KEY in harness/app/.env.local."
    if model.startswith("openai/"):
        return (f"{model} went through OpenRouter because OPENAI_API_KEY is not set: set it in "
                "harness/app/.env.local to ask OpenAI directly (or set a working OPENROUTER_API_KEY).")
    return f"{model} is asked through OpenRouter: it needs a working OPENROUTER_API_KEY in harness/app/.env.local."
