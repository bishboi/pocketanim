"""One request to a chat model through OpenRouter, for the steps that run beside the build in Python: the voice
director (voice_director.py) and the timing of the animations to the voice (align_cues.py).

The model is the step's own setting, else OPENROUTER_MODEL (the app's), else a fast default; the key is
OPENROUTER_API_KEY (the environment or harness/app/.env.local); an openai/... model goes to OpenAI itself when
OPENAI_API_KEY is set (providers.py). OPENROUTER_URL points a test at a mock.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import providers
from chirp import _env

DEFAULT_MODEL = "google/gemini-2.5-flash"
TIMEOUT = 180


def model(setting: str) -> str:
    return _env(setting) or _env("OPENROUTER_MODEL") or DEFAULT_MODEL


def configured() -> bool:
    return bool(_env("OPENROUTER_API_KEY") or _env("OPENAI_API_KEY"))


def chat_json(model_id: str, system: str, user: str, tries: int = 3) -> tuple[dict, float]:
    """(the reply's JSON object, what the request cost in US dollars). Raises RuntimeError when no usable reply
    comes after `tries` requests."""
    if not (providers.direct(model_id) or _env("OPENROUTER_API_KEY")):
        raise RuntimeError("no OPENROUTER_API_KEY")
    url, headers, sent = providers.chat({
        "model": model_id, "usage": {"include": True}, "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    body = json.dumps(sent).encode()
    spent, last = 0.0, "no reply"
    for attempt in range(tries):
        request = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                reply = json.loads(response.read())
        except urllib.error.HTTPError as error:
            last = f"OpenRouter {error.code}: {error.read().decode('utf-8', 'replace')[:200]}"
            if error.code not in (408, 429, 500, 502, 503, 504):
                break
            time.sleep(2 * (attempt + 1))
            continue
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last = f"OpenRouter could not be reached: {error}"
            time.sleep(2 * (attempt + 1))
            continue
        spent += providers.cost(model_id, reply.get("usage"))
        text = str(((reply.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        try:
            parsed = json.loads(text[text.index("{"): text.rindex("}") + 1])
            if isinstance(parsed, dict):
                return parsed, spent
        except ValueError:
            pass
        last = "the reply was not JSON"
    raise RuntimeError(last)
