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
            who = "OpenAI" if providers.direct(model_id) else "OpenRouter"
            last = f"{who} {error.code}: {error.read().decode('utf-8', 'replace')[:200]}"
            if error.code in (401, 403):
                last += " " + providers.auth_hint(model_id)
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


# ---------------- an agent: a model calling this step's own tools, with web search ----------------
# OpenAI's own models (OPENAI_API_KEY) are asked through the Responses API with its web_search tool; any other model
# through OpenRouter's chat completions with its web plugin (a search on the conversation, added to each request).
# PANIM_AGENT_WEB=off asks without the web.


def _post(url: str, headers: dict, body: dict, model_id: str, tries: int = 3) -> tuple[dict, str | None]:
    data = json.dumps(body).encode()
    last = None
    for attempt in range(tries):
        request = urllib.request.Request(url, data=data, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read()), None
        except urllib.error.HTTPError as error:
            who = "OpenAI" if providers.direct(model_id) else "OpenRouter"
            last = f"{who} {error.code}: {error.read().decode('utf-8', 'replace')[:300]}"
            if error.code in (401, 403):
                return {}, last + " " + providers.auth_hint(model_id)
            if error.code not in (408, 429, 500, 502, 503, 504):
                return {}, last
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last = f"the model could not be reached: {error}"
        time.sleep(2 * (attempt + 1))
    return {}, last


def web_enabled() -> bool:
    return (_env("PANIM_AGENT_WEB") or "on").strip().lower() not in ("off", "0", "no")


def agent(model_id: str, system: str, user: str, tools: list[dict], handle, done=lambda: False,
          turns: int = 16, log: list | None = None) -> tuple[str, float, str | None]:
    """Run a model with function tools until it stops calling them, `done()` says so, or `turns` replies.

    `tools`: [{"name", "description", "parameters"}]; `handle(name, args) -> str` runs one call and says what came
    of it. `log` gets each call, its result and each search the model made. Returns (its last words, US dollars
    spent, the error that stopped it or None)."""
    log = log if log is not None else []
    if not (providers.direct(model_id) or _env("OPENROUTER_API_KEY")):
        return "", 0.0, "no OPENROUTER_API_KEY or OPENAI_API_KEY"
    if providers.direct(model_id):
        return _agent_responses(model_id, system, user, tools, handle, done, turns, log)
    return _agent_chat(model_id, system, user, tools, handle, done, turns, log)


def _agent_responses(model_id, system, user, tools, handle, done, turns, log):
    base = (_env("OPENAI_BASE_URL") or providers.OPENAI_BASE).rstrip("/")
    headers = {"Authorization": f"Bearer {_env('OPENAI_API_KEY')}", "Content-Type": "application/json"}
    model = model_id.removeprefix("openai/")
    specs = [{"type": "function", "name": t["name"], "description": t["description"], "parameters": t["parameters"]}
             for t in tools]
    if web_enabled():
        specs.append({"type": "web_search"})
    items: list = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    spent, words = 0.0, ""
    for _ in range(turns):
        body = {"model": model, "input": items, "tools": specs, "store": False}
        if providers.reasoning_model(model):
            body["reasoning"] = {"effort": "low"}
            body["include"] = ["reasoning.encrypted_content"]       # handed back with the next turn (no store)
        reply, error = _post(f"{base}/responses", headers, body, model_id)
        if error:
            return words, spent, error
        usage = reply.get("usage") or {}
        spent += providers.cost(model_id, {"prompt_tokens": usage.get("input_tokens"),
                                           "completion_tokens": usage.get("output_tokens")})
        output = reply.get("output") or []
        items += output
        calls = [o for o in output if o.get("type") == "function_call"]
        for o in output:
            if o.get("type") == "web_search_call":
                log.append({"search": (o.get("action") or {}).get("query") or "(web search)"})
            if o.get("type") == "message":
                words = " ".join(c.get("text", "") for c in o.get("content") or [] if c.get("type") == "output_text")
        if not calls:
            return words, spent, None
        for call in calls:
            result = _run(handle, call.get("name"), call.get("arguments"), log)
            items.append({"type": "function_call_output", "call_id": call.get("call_id"), "output": result})
        if done():
            return words, spent, None
    return words, spent, None


def _agent_chat(model_id, system, user, tools, handle, done, turns, log):
    specs = [{"type": "function", "function": t} for t in tools]
    messages: list = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    spent, words = 0.0, ""
    for turn in range(turns):
        body = {"model": model_id, "messages": messages, "tools": specs, "usage": {"include": True}}
        if web_enabled() and turn == 0:
            body["plugins"] = [{"id": "web", "max_results": 5}]       # searched once, on the names asked about
        url, headers, sent = providers.chat(body)
        reply, error = _post(url, headers, sent, model_id)
        if error:
            return words, spent, error
        spent += providers.cost(model_id, reply.get("usage"))
        message = ((reply.get("choices") or [{}])[0].get("message") or {})
        words = str(message.get("content") or words)
        for note in message.get("annotations") or []:
            if note.get("type") == "url_citation":
                log.append({"search": (note.get("url_citation") or {}).get("url")})
        calls = message.get("tool_calls") or []
        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls} if calls
                        else {"role": "assistant", "content": message.get("content") or ""})
        if not calls:
            return words, spent, None
        for call in calls:
            fn = call.get("function") or {}
            result = _run(handle, fn.get("name"), fn.get("arguments"), log)
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": result})
        if done():
            return words, spent, None
    return words, spent, None


def _run(handle, name, arguments, log) -> str:
    try:
        args = json.loads(arguments or "{}")
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
    except ValueError as error:
        result = f"error: the arguments were not a JSON object ({error})"
    else:
        try:
            result = str(handle(str(name), args))
        except Exception as error:  # noqa: BLE001 -- told to the model, which can try again
            result = f"error: {type(error).__name__}: {error}"
    log.append({"call": name, "args": arguments if len(str(arguments)) < 2000 else str(arguments)[:2000],
                "result": result[:1500]})
    return result
