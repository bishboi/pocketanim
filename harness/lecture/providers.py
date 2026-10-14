"""Where a model's request goes: OpenRouter, or OpenAI's own API for an OpenAI model when there is a key for it.

Every AI step names its model the OpenRouter way ("openai/gpt-5.1", "google/gemini-2.5-flash"). A model named
openai/... is asked of OpenAI directly when OPENAI_API_KEY is set (PANIM_OPENAI_DIRECT=off keeps it on OpenRouter):
the prefix comes off, and the request is put in OpenAI's form -- OpenRouter's own fields out (usage, provider,
plugins, transforms), its reasoning setting as OpenAI's reasoning_effort, max_tokens as max_completion_tokens, no
temperature for a reasoning model, the usage asked for when streaming. OpenAI does not say what a request cost:
it is priced from its tokens with PANIM_OPENAI_PRICES ({"gpt-5.1": [in, out]}, US dollars per million tokens),
else counted as 0. The web app does the same (harness/app/lib/providers.ts).

OPENAI_BASE_URL points at another OpenAI-compatible endpoint (a test's mock, Azure's).
"""

from __future__ import annotations

import json
import re

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


def _prices() -> dict:
    try:
        return json.loads(_env("PANIM_OPENAI_PRICES") or "{}")
    except ValueError:
        return {}


def cost(model: str | None, usage: dict | None) -> float:
    """What a reply cost: OpenRouter's own figure, else (an OpenAI reply) its tokens at PANIM_OPENAI_PRICES."""
    usage = usage or {}
    if usage.get("cost") is not None:
        return float(usage["cost"])
    price = _prices().get(str(model or "").removeprefix("openai/"))
    if not price:
        return 0.0
    return (float(usage.get("prompt_tokens") or 0) * float(price[0])
            + float(usage.get("completion_tokens") or 0) * float(price[1])) / 1e6


def auth_hint(model: str | None) -> str:
    """What to do when a provider refuses a request's key (401, 403)."""
    model = str(model or "")
    if direct(model):
        return "OpenAI refused the key: check OPENAI_API_KEY in harness/app/.env.local."
    if model.startswith("openai/"):
        return (f"{model} went through OpenRouter because OPENAI_API_KEY is not set: set it in "
                "harness/app/.env.local to ask OpenAI directly (or set a working OPENROUTER_API_KEY).")
    return f"{model} is asked through OpenRouter: it needs a working OPENROUTER_API_KEY in harness/app/.env.local."
